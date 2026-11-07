"""停车资源规划推导：从分车型进出报表换算车位需求，并与场地实有车位对比。

系统统计的是「通过虚拟线的分车型进 / 出流量」，本模块把它进一步换算成
停车资源规划依据：

    某小时末在场数 = 上一小时在场数 + 该小时进入数 - 该小时驶出数
    分组峰值在场数 = 该组车辆在场数的时间序列最大值
    建议泊位数     = ceil(分组峰值在场数 × (1 + 周转余量))
    规划用地面积   = 建议泊位数 × 单车位面积 × 通道系数

两条数据线，缺一不可：
  * 供给侧（实际有多少车位）：由**本地人员**按场地录入 `data/parking_zones.json`，
    例如校园 A 区（轿车 / SUV）360 位、B 区（客车 / 货车）180 位。
    分区数量、名称、服务的车型、车位数量全部可自定义，系统不写死。
  * 需求侧（需要多少车位）：由通行流量推算，是本模块的输出。

对每个分区按它服务的车型逐小时求和得到「分区峰值在场数」，再与录入的
实有车位比较，给出余量 / 缺口 / 饱和度 / 状态，用于判断是否够用、
是否需要扩建或调整分区用途。

分档（内置 GROUPS 仅用于「建议泊位数 / 用地」的需求侧参考口径）：
    small 小车位 : sedan(轿车) + suv(SUV)
    large 大车位 : truck(货车) + bus(客车)

注意：需求侧是**由通行流量推算的泊位需求下限**，不是车位级占用检测。
前提是所有出入口都被同一套系统统计到；若只统计单个入口，
净流量会持续累加而高估，必须配合出场数据或每日清零。
"""
import csv
import json
import math
import os

SMALL_CLASSES = ("sedan", "suv")
LARGE_CLASSES = ("truck", "bus")
GROUPS = {"small": SMALL_CLASSES, "large": LARGE_CLASSES}
GROUP_CN = {"small": "小车位（轿车 / SUV）", "large": "大车位（货车 / 客车）"}
# 单车位占地面积（㎡，含标线不含通道）：小型位 2.5×5.0，大型位 3.5×12.0
SLOT_AREA_SQM = {"small": 12.5, "large": 42.0}

# 车型中文名兜底（调用方可传入 config.CLASS_CN）
CLASS_CN_FALLBACK = {"sedan": "轿车", "suv": "SUV", "truck": "货车", "bus": "客车"}

# 场地车位配置模板：本地人员按实际情况修改，仓库内该文件即默认配置
DEFAULT_ZONES = {
    "site_name": "校园",
    "note": "本地人员按实际场地填写：每个分区服务哪些车型、共有多少个车位。",
    "zones": [
        {"id": "A", "name": "A 区", "classes": ["sedan", "suv"],
         "slots": 360, "note": "小车位：轿车 / SUV"},
        {"id": "B", "name": "B 区", "classes": ["truck", "bus"],
         "slots": 180, "note": "大车位：客车 / 货车"},
    ],
}


def default_zones_path():
    """场地配置路径；可用 CAMPUS_PARKING_ZONES 指向其他场地文件"""
    return os.environ.get(
        "CAMPUS_PARKING_ZONES",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "parking_zones.json"))


def normalize_zones(data, classes=("sedan", "suv", "truck", "bus")):
    """清洗配置：补全字段、过滤未知车型、车位数量转非负整数。

    返回纯配置 dict（只含 site_name / note / zones），供保存与计算共用。
    """
    if not isinstance(data, dict):
        raise ValueError("场地配置必须是 JSON 对象")
    raw_zones = data.get("zones")
    if not isinstance(raw_zones, list):
        raise ValueError("缺少 zones 列表")
    known = set(classes)
    zones = []
    for i, z in enumerate(raw_zones):
        if not isinstance(z, dict):
            raise ValueError("第 %d 个分区不是对象" % (i + 1))
        members = [c for c in (z.get("classes") or []) if c in known]
        zones.append({
            "id": str(z.get("id") or ("Z%d" % (i + 1))),
            "name": str(z.get("name") or ("分区 %d" % (i + 1))).strip(),
            "classes": members,
            "slots": int(z.get("slots") or 0),
            "note": str(z.get("note") or ""),
        })
    return {
        "site_name": str(data.get("site_name") or "未命名场地").strip(),
        "note": str(data.get("note") or ""),
        "zones": zones,
    }


def validate_zones(data, classes=("sedan", "suv", "truck", "bus")):
    """校验本地人员录入的场地配置，返回 (纯配置, 提示列表)。

    覆盖关系只给提示不报错：同一车型被多个区服务时，需求会在各区各算一次，
    属于口径重复，需由本地人员确认；未覆盖的车型则不计入任何区的供需对比。
    """
    cfg = normalize_zones(data, classes)
    warnings = []
    if not cfg["zones"]:
        warnings.append("尚未配置任何分区，请至少添加一个")
    seen = {}
    for z in cfg["zones"]:
        if z["slots"] < 0:
            raise ValueError("分区「%s」的车位数量不能为负数" % z["name"])
        if z["slots"] > 1000000:
            raise ValueError("分区「%s」的车位数量超出合理范围" % z["name"])
        if not z["classes"]:
            raise ValueError("分区「%s」未选择任何适用车型" % z["name"])
        if z["slots"] == 0:
            warnings.append("分区「%s」车位数量为 0，将显示为未配置车位" % z["name"])
        for c in z["classes"]:
            seen[c] = seen.get(c, 0) + 1
    known = set(classes)
    dup = sorted(c for c, n in seen.items() if n > 1)
    miss = sorted(known - set(seen))
    if dup:
        warnings.append("车型 %s 被多个分区服务，需求会重复计入，请确认"
                        % "/".join(CLASS_CN_FALLBACK.get(c, c) for c in dup))
    if miss:
        warnings.append("车型 %s 未被任何分区覆盖，不参与供需对比"
                        % "/".join(CLASS_CN_FALLBACK.get(c, c) for c in miss))
    return cfg, warnings


def load_zones(path=None):
    """读取本地人员维护的场地配置；文件不存在或出错时回退到内置示例。

    返回 dict 含 site_name / note / zones / source / warnings。
    source 为空字符串表示用的是内置示例（未找到配置文件）。
    """
    p = path or default_zones_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                cfg, warnings = validate_zones(json.load(f))
            return {**cfg, "source": p, "warnings": warnings}
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            cfg = normalize_zones(DEFAULT_ZONES)
            return {**cfg, "source": "", "warnings": ["配置文件读取失败(%s)，已回退到内置示例" % exc]}
    return {**normalize_zones(DEFAULT_ZONES), "source": "",
            "warnings": ["未找到场地配置文件，当前使用内置示例；请在看板中保存一次以生成本地配置"]}


def save_zones(data, path=None, classes=("sedan", "suv", "truck", "bus")):
    """校验并保存场地配置到 JSON（本地人员设置落盘），返回 (配置, 提示, 路径)"""
    cfg, warnings = validate_zones(data, classes)
    p = path or default_zones_path()
    parent = os.path.dirname(os.path.abspath(p))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return cfg, warnings, p


def load_hourly(path):
    """读取 Reporter 输出的 hourly.csv（支持 utf-8-sig BOM）"""
    if not os.path.exists(path):
        raise FileNotFoundError("报表不存在: %s" % path)
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _int(row, key):
    try:
        return int(float(row.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def compute(rows, classes=("sedan", "suv", "truck", "bus"),
            reserve=0.20, aisle_factor=1.35, reset_daily=True, zones=None):
    """由每小时分车型进出量推导泊位需求，并与场地实有车位对比。

    返回可直接 JSON 序列化的 dict：
      groups  = 需求侧内置大 / 小车位口径（建议泊位数与用地）
      zones   = 供给侧录入的分区配置 + 逐区供需对比（余量 / 缺口 / 饱和度）

    reserve       : 周转余量，默认 20%（应对峰值波动 / 临时停放）
    aisle_factor  : 通道与转弯空间系数，默认 1.35
    reset_daily   : 每天开始时在场数归零（模拟夜间清场 / 避免跨日累计误差）
    zones         : 场地配置 dict（load_zones() 的返回），None 时自动读取本地配置
    """
    classes = tuple(classes)
    occ = {c: 0 for c in classes}
    peaks = {c: 0 for c in classes}
    peak_at = {c: "" for c in classes}
    totals = {c: {"enter": 0, "exit": 0} for c in classes}
    timeline = []
    cur_date = None

    for row in rows:
        period = str(row.get("period", ""))
        date = period.split(" ")[0]
        if reset_daily and cur_date is not None and date != cur_date:
            occ = {c: 0 for c in classes}   # 新的一天，场内重新计数
        cur_date = date

        throughput = 0
        for c in classes:
            e, x = _int(row, f"enter_{c}"), _int(row, f"exit_{c}")
            totals[c]["enter"] += e
            totals[c]["exit"] += x
            throughput += e + x
            occ[c] = max(0, occ[c] + e - x)
            if occ[c] > peaks[c]:
                peaks[c], peak_at[c] = occ[c], period

        small = sum(occ[c] for c in SMALL_CLASSES if c in occ)
        large = sum(occ[c] for c in LARGE_CLASSES if c in occ)
        timeline.append({
            "period": period, "small_occupancy": small, "large_occupancy": large,
            "throughput": throughput,
            **{"%s_occupancy" % c: occ.get(c, 0) for c in classes},
        })

    peak_hour = max(timeline, key=lambda t: t["throughput"]) if timeline else None
    groups = {}
    for g, members in GROUPS.items():
        key = g + "_occupancy"
        peak = max((t[key] for t in timeline), default=0)
        slots = math.ceil(peak * (1.0 + reserve))
        area = slots * SLOT_AREA_SQM[g] * aisle_factor
        groups[g] = {
            "classes": [c for c in members if c in classes],
            "label": GROUP_CN[g],
            "peak_occupancy": peak,
            "recommended_slots": slots,
            "slot_area_sqm": SLOT_AREA_SQM[g],
            "area_with_aisle_sqm": round(area, 1),
        }

    total_slots = sum(v["recommended_slots"] for v in groups.values())
    for g, v in groups.items():
        v["share_pct"] = round(v["recommended_slots"] / total_slots * 100, 1) if total_slots else 0.0

    # ---- 供给侧：按本地人员录入的分区，把逐小时在场数聚合成该区的需求 ----
    zone_cfg = zones if zones is not None else load_zones()
    zone_items, cover = [], {}
    for z in zone_cfg.get("zones", []):
        members = [c for c in z.get("classes", []) if c in occ]
        series = [sum(t["%s_occupancy" % c] for c in members) for t in timeline]
        peak = max(series, default=0)
        required = math.ceil(peak * (1.0 + reserve))
        supply = int(z.get("slots") or 0)
        gap = supply - required
        saturation = round(peak / supply * 100, 1) if supply else 0.0
        if supply <= 0:
            status = "未配置车位"
        elif peak > supply:
            status = "已超负荷"
        elif required > supply:
            status = "周转余量不足"
        elif saturation >= 80:
            status = "接近饱和"
        else:
            status = "供给充足"
        zone_items.append({
            "id": z.get("id", ""), "name": z.get("name", ""),
            "classes": members,
            "classes_cn": [CLASS_CN_FALLBACK.get(c, c) for c in members],
            "note": z.get("note", ""),
            "supply_slots": supply,
            "peak_occupancy": peak,
            "required_slots": required,
            "gap_slots": gap,
            "saturation_pct": saturation,
            "utilization_pct": round(required / supply * 100, 1) if supply else 0.0,
            "status": status,
        })
        for c in members:
            cover[c] = cover.get(c, 0) + 1

    supply_total = sum(i["supply_slots"] for i in zone_items)
    required_total = sum(i["required_slots"] for i in zone_items)
    peak_total = sum(i["peak_occupancy"] for i in zone_items)
    uncovered = sorted(c for c in classes if c not in cover)
    duplicate = sorted(c for c, n in cover.items() if n > 1)
    warnings = list(zone_cfg.get("warnings", []))
    for i in zone_items:
        if i["gap_slots"] < 0:
            warnings.append("分区「%s」车位缺口 %d 个，需扩建或调整车型分区"
                            % (i["name"], -i["gap_slots"]))
        elif i["supply_slots"] >= 20 and i["saturation_pct"] < 20:
            warnings.append("按当前样本，分区「%s」峰值饱和度仅 %.1f%%，车位明显富余，"
                            "可考虑改作他用或缩减规模（样本过短时会低估需求）"
                            % (i["name"], i["saturation_pct"]))
    if uncovered:
        warnings.append("车型 %s 未被任何分区覆盖，不参与供需对比"
                        % "/".join(CLASS_CN_FALLBACK.get(c, c) for c in uncovered))
    if duplicate:
        warnings.append("车型 %s 被多个分区服务，需求会重复计入"
                        % "/".join(CLASS_CN_FALLBACK.get(c, c) for c in duplicate))
    zones_result = {
        "site_name": zone_cfg.get("site_name", ""),
        "config_source": zone_cfg.get("source", ""),
        "items": zone_items,
        "supply_total": supply_total,
        "required_total": required_total,
        "gap_total": supply_total - required_total,
        "peak_total": peak_total,
        "saturation_pct": round(peak_total / supply_total * 100, 1) if supply_total else 0.0,
        "uncovered_classes": uncovered,
        "duplicate_classes": duplicate,
        "warnings": warnings,
    }

    return {
        "zones": zones_result,
        "hours": len(rows),
        "date_from": timeline[0]["period"] if timeline else "",
        "date_to": timeline[-1]["period"] if timeline else "",
        "reserve": reserve,
        "aisle_factor": aisle_factor,
        "reset_daily": reset_daily,
        "per_class": {
            c: {"peak_occupancy": peaks[c], "peak_at": peak_at[c],
                "total_enter": totals[c]["enter"], "total_exit": totals[c]["exit"]}
            for c in classes
        },
        "groups": groups,
        "total_recommended_slots": total_slots,
        "total_area_sqm": round(sum(v["area_with_aisle_sqm"] for v in groups.values()), 1),
        "peak_hour": ({"period": peak_hour["period"], "throughput": peak_hour["throughput"]}
                      if peak_hour else None),
        "timeline": timeline,
    }


def format_markdown(result, class_cn=None):
    """生成可直接放进课程设计的 Markdown 报告片段"""
    cn = class_cn or CLASS_CN_FALLBACK
    g = result["groups"]
    z = result.get("zones", {})
    lines = [
        "# 停车资源供需分析（场地实有车位 × 通行流量需求）",
        "",
        "样本时段：`%s` ~ `%s`，共 %d 个小时桶"
        % (result["date_from"], result["date_to"], result["hours"]),
        "参数：周转余量 %.0f%%，通道系数 %.2f，每日清零=%s"
        % (result["reserve"] * 100, result["aisle_factor"], result["reset_daily"]),
        "",
        "## 分车型峰值在场数",
        "",
        "| 车型 | 累计进入 | 累计驶出 | 峰值在场数 | 峰值时刻 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c, v in result["per_class"].items():
        lines.append("| %s | %d | %d | %d | %s |"
                     % (cn.get(c, c), v["total_enter"], v["total_exit"],
                        v["peak_occupancy"], v["peak_at"] or "-"))
    lines += [
        "",
        "## 车位配比建议",
        "",
        "| 分区 | 对应车型 | 峰值在场数 | 建议泊位数 | 单车位面积(㎡) | 含通道用地(㎡) | 占比 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in ("small", "large"):
        v = g[key]
        lines.append("| %s | %s | %d | **%d** | %.1f | %.1f | %.1f%% |"
                     % (v["label"], " / ".join(cn.get(c, c) for c in v["classes"]),
                        v["peak_occupancy"], v["recommended_slots"],
                        v["slot_area_sqm"], v["area_with_aisle_sqm"], v["share_pct"]))
    lines += [
        "",
        "## 场地车位配置与供需对比（本地人员录入）",
        "",
        "场地：**%s**；配置文件：`%s`"
        % (z.get("site_name", "-") or "-",
           z.get("config_source") or "未找到，使用内置示例"),
        "",
        "| 分区 | 适用车型 | 实有车位 | 峰值在场数 | 需求泊位(含余量) | 余量 / 缺口 | 峰值饱和度 | 需求占用率 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i in z.get("items", []):
        names = " / ".join(cn.get(c, c) for c in i["classes"]) or "-"
        gap = ("+%d" % i["gap_slots"]) if i["gap_slots"] >= 0 else str(i["gap_slots"])
        lines.append("| %s | %s | **%d** | %d | %d | **%s** | %.1f%% | %.1f%% | %s |"
                     % (i["name"], names, i["supply_slots"], i["peak_occupancy"],
                        i["required_slots"], gap, i["saturation_pct"],
                        i["utilization_pct"], i["status"]))
    lines += [
        "",
        "- **实有车位合计**：%d 个；**需求泊位合计**：%d 个；**总体余量**：%s 个，峰值饱和度 %.1f%%"
        % (z.get("supply_total", 0), z.get("required_total", 0),
           ("+%d" % z["gap_total"]) if z.get("gap_total", 0) >= 0 else str(z.get("gap_total", 0)),
           z.get("saturation_pct", 0.0)),
        "- **建议泊位合计（需求侧参考）**：%d 个（小车位 %d / 大车位 %d），规划用地约 **%.1f ㎡**"
        % (result["total_recommended_slots"], g["small"]["recommended_slots"],
           g["large"]["recommended_slots"], result["total_area_sqm"]),
    ]
    if result["peak_hour"]:
        lines.append("- **高峰通行时段**：`%s`，该小时进出合计 %d 辆次（拥堵治理依据）"
                     % (result["peak_hour"]["period"], result["peak_hour"]["throughput"]))
    warns = z.get("warnings", [])
    if warns:
        lines += ["", "### 配置提示", ""] + ["- " + w for w in warns]
    lines += [
        "",
        "## 方法与边界",
        "",
        "```text",
        "供给侧  实有车位       = 本地人员按场地录入（分区 / 适用车型 / 数量）",
        "需求侧  在场数(第 t 小时) = max(0, 在场数(t-1) + 进入数(t) - 驶出数(t))",
        "        分区峰值在场数 = max(该区适用车型逐小时在场数之和)",
        "        需求泊位数     = ceil(分区峰值 × (1 + 周转余量))",
        "        余量           = 实有车位 - 需求泊位数",
        "        峰值饱和度     = 分区峰值在场数 / 实有车位",
        "参考    规划用地面积   = 建议泊位数 × 单车位面积 × 通道系数",
        "```",
        "",
        "需求侧是由**通行流量**推算的泊位需求下限，不是车位级占用检测；",
        "供给侧由本地人员录入，代表场地实际可用泊位，两者口径不同不可混用。",
        "所有出入口必须都被系统统计到；短视频 / 统计中断会低估需求；",
        "实际规划还需叠加夜间停放、消防通道、无障碍位与校园规划规范。",
    ]
    return "\n".join(lines) + "\n"
