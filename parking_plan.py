"""停车资源规划推导：从分车型进出报表换算大 / 小车位需求。

系统统计的是「通过虚拟线的分车型进 / 出流量」，本模块把它进一步换算成
停车资源规划依据：

    某小时末在场数 = 上一小时在场数 + 该小时进入数 - 该小时驶出数
    分组峰值在场数 = 该组车辆在场数的时间序列最大值
    建议泊位数     = ceil(分组峰值在场数 × (1 + 周转余量))
    规划用地面积   = 建议泊位数 × 单车位面积 × 通道系数

分档（对应「大区域停货车 / 客车，小车位停 SUV / 轿车」）：
    small 小车位 : sedan(轿车) + suv(SUV)
    large 大车位 : truck(货车) + bus(客车)

注意：这是**由通行流量推算的泊位需求下限**，不是车位级占用检测。
前提是所有出入口都被同一套系统统计到；若只统计单个入口，
净流量会持续累加而高估，必须配合出场数据或每日清零。
"""
import csv
import math
import os

SMALL_CLASSES = ("sedan", "suv")
LARGE_CLASSES = ("truck", "bus")
GROUPS = {"small": SMALL_CLASSES, "large": LARGE_CLASSES}
GROUP_CN = {"small": "小车位（轿车 / SUV）", "large": "大车位（货车 / 客车）"}
# 单车位占地面积（㎡，含标线不含通道）：小型位 2.5×5.0，大型位 3.5×12.0
SLOT_AREA_SQM = {"small": 12.5, "large": 42.0}


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
            reserve=0.20, aisle_factor=1.35, reset_daily=True):
    """由每小时分车型进出量推导泊位需求，返回可直接 JSON 序列化的 dict。

    reserve       : 周转余量，默认 20%（应对峰值波动 / 临时停放）
    aisle_factor  : 通道与转弯空间系数，默认 1.35
    reset_daily   : 每天开始时在场数归零（模拟夜间清场 / 避免跨日累计误差）
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

    return {
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
    cn = class_cn or {"sedan": "轿车", "suv": "SUV", "truck": "货车", "bus": "客车"}
    g = result["groups"]
    lines = [
        "# 停车资源规划建议（由分车型进出报表推导）",
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
        "- **建议泊位合计**：%d 个（小车位 %d / 大车位 %d），规划用地约 **%.1f ㎡**"
        % (result["total_recommended_slots"], g["small"]["recommended_slots"],
           g["large"]["recommended_slots"], result["total_area_sqm"]),
    ]
    if result["peak_hour"]:
        lines.append("- **高峰通行时段**：`%s`，该小时进出合计 %d 辆次（拥堵治理依据）"
                     % (result["peak_hour"]["period"], result["peak_hour"]["throughput"]))
    lines += [
        "",
        "## 方法与边界",
        "",
        "```text",
        "在场数(第 t 小时) = max(0, 在场数(t-1) + 进入数(t) - 驶出数(t))",
        "分组峰值在场数   = max(该组两类车在场数之和)",
        "建议泊位数       = ceil(分组峰值 × (1 + 周转余量))",
        "规划用地面积     = 建议泊位数 × 单车位面积 × 通道系数",
        "```",
        "",
        "本结果是由**通行流量**推算的泊位需求下限，不是车位级占用检测：",
        "所有出入口必须都被系统统计到；短视频 / 统计中断会低估；",
        "实际规划还需叠加夜间停放、消防通道、无障碍位与校园规划规范。",
    ]
    return "\n".join(lines) + "\n"
