"""把分车型进出报表换算成泊位需求，并与本地录入的场地实有车位做供需对比。

用法:
  python tools/plan_parking.py
  python tools/plan_parking.py --hourly data/real_eval_cq_full/reports/hourly.csv \
      --out-dir data/real_eval_cq_full/reports --reserve 0.2
  python tools/plan_parking.py --no-reset-daily   # 跨日连续在场（如不夜间清场）
  python tools/plan_parking.py --init-zones       # 生成一份场地配置模板供本地人员填写
  python tools/plan_parking.py --zones D:/my_zones.json  # 使用别的场地配置

场地配置（默认 data/parking_zones.json）由本地人员维护：分区名、适用车型、
实有车位数量。也可在网页看板的「场地车位设置」中编辑并保存。

输出（--out-dir 下）:
  parking_plan.md              可直接放进课程设计报告的供需分析说明
  parking_plan.csv             大 / 小车位配比汇总表（需求侧参考）
  parking_plan_zones.csv       场地分区供需对比表（供给侧）
  parking_plan_timeline.csv    逐小时在场数与通行量
  parking_plan.xlsx            以上各表的 Excel 版（需 openpyxl）
"""
import argparse
import csv
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import config
import parking_plan


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="由进出报表推导停车资源规划")
    ap.add_argument("--hourly", default=config.HOURLY_CSV, help="hourly.csv 路径")
    ap.add_argument("--out-dir", default=config.REPORT_DIR, help="输出目录")
    ap.add_argument("--reserve", type=float, default=0.20, help="周转余量，默认 0.20")
    ap.add_argument("--aisle-factor", type=float, default=1.35, help="通道系数，默认 1.35")
    ap.add_argument("--no-reset-daily", action="store_true", help="不在每日开始时清零在场数")
    ap.add_argument("--zones", default=config.PARKING_ZONES_JSON,
                    help="场地车位配置 JSON（默认 data/parking_zones.json）")
    ap.add_argument("--init-zones", action="store_true",
                    help="写出一份场地配置模板到 --zones 后退出")
    args = ap.parse_args()

    if args.init_zones:
        if os.path.exists(args.zones):
            # 保护本地人员已录入的车位数据，绝不静默覆盖
            print("场地配置已存在，未做任何修改:", args.zones)
            print("如需一份新模板，请用 --zones 指向另一个路径；如需重置，请先备份再删除原文件。")
            return
        cfg, warns, path = parking_plan.save_zones(
            parking_plan.DEFAULT_ZONES, args.zones, config.CLASSES)
        print("场地配置模板已生成:", path)
        print("请用文本编辑器按实际场地修改 zones（name / classes / slots），或到看板页面编辑。")
        for w in warns:
            print("  [提示]", w)
        return

    rows = parking_plan.load_hourly(args.hourly)
    if not rows:
        raise SystemExit("报表为空，请先运行 main.py 生成 hourly.csv: " + args.hourly)
    zone_cfg = parking_plan.load_zones(args.zones)
    result = parking_plan.compute(
        rows, classes=config.CLASSES, reserve=args.reserve,
        aisle_factor=args.aisle_factor, reset_daily=not args.no_reset_daily,
        zones=zone_cfg)
    os.makedirs(args.out_dir, exist_ok=True)

    md = parking_plan.format_markdown(result, config.CLASS_CN)
    md_path = os.path.join(args.out_dir, "parking_plan.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    g = result["groups"]
    group_rows = [
        [key, g[key]["label"], "/".join(g[key]["classes"]),
         g[key]["peak_occupancy"], g[key]["recommended_slots"],
         g[key]["slot_area_sqm"], g[key]["area_with_aisle_sqm"], g[key]["share_pct"]]
        for key in ("small", "large")
    ]
    group_header = ["group", "label", "classes", "peak_occupancy",
                    "recommended_slots", "slot_area_sqm", "area_with_aisle_sqm", "share_pct"]
    _write_csv(os.path.join(args.out_dir, "parking_plan.csv"), group_header, group_rows)

    z = result["zones"]
    zone_header = ["zone_id", "zone_name", "classes", "supply_slots", "peak_occupancy",
                   "required_slots", "gap_slots", "saturation_pct", "utilization_pct",
                   "status", "note"]
    zone_rows = [
        [i["id"], i["name"], "/".join(i["classes"]), i["supply_slots"],
         i["peak_occupancy"], i["required_slots"], i["gap_slots"],
         i["saturation_pct"], i["utilization_pct"], i["status"], i["note"]]
        for i in z["items"]
    ]
    _write_csv(os.path.join(args.out_dir, "parking_plan_zones.csv"), zone_header, zone_rows)

    tl = result["timeline"]
    tl_header = ["period"] + ["%s_occupancy" % c for c in config.CLASSES] + \
                ["small_occupancy", "large_occupancy", "throughput"]
    tl_rows = [[t["period"]] + [t["%s_occupancy" % c] for c in config.CLASSES] +
               [t["small_occupancy"], t["large_occupancy"], t["throughput"]] for t in tl]
    _write_csv(os.path.join(args.out_dir, "parking_plan_timeline.csv"), tl_header, tl_rows)

    try:
        from openpyxl import Workbook
        wb = Workbook()
        for idx, (name, header, data) in enumerate([
            ("场地供需", zone_header, zone_rows),
            ("车位配比", group_header, group_rows),
            ("逐小时在场数", tl_header, tl_rows),
            ("配置提示", ["提示"], [[w] for w in z["warnings"]] or [["无"]]),
        ]):
            ws = wb.active if idx == 0 else wb.create_sheet(name)
            ws.title = name
            ws.append(header)
            for r in data:
                ws.append(r)
        xlsx = os.path.join(args.out_dir, "parking_plan.xlsx")
        wb.save(xlsx)
        print("Excel 已生成:", xlsx)
    except ImportError:
        print("[warn] 未安装 openpyxl，跳过 Excel 导出")

    print()
    print(md)
    print("场地配置:", args.zones, "（由本地人员维护）")
    print("输出目录:", args.out_dir)


if __name__ == "__main__":
    main()
