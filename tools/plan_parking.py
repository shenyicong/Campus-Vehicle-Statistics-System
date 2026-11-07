"""把分车型进出报表换算成停车资源规划建议（大 / 小车位配比与用地）。

用法:
  python tools/plan_parking.py
  python tools/plan_parking.py --hourly data/real_eval_cq_full/reports/hourly.csv \
      --out-dir data/real_eval_cq_full/reports --reserve 0.2
  python tools/plan_parking.py --no-reset-daily   # 跨日连续在场（如不夜间清场）

输出（--out-dir 下）:
  parking_plan.md              可直接放进课程设计报告的说明
  parking_plan.csv             大 / 小车位配比汇总表
  parking_plan_timeline.csv    逐小时在场数与通行量
  parking_plan.xlsx            以上两张表的 Excel 版（需 openpyxl）
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
    args = ap.parse_args()

    rows = parking_plan.load_hourly(args.hourly)
    if not rows:
        raise SystemExit("报表为空，请先运行 main.py 生成 hourly.csv: " + args.hourly)
    result = parking_plan.compute(
        rows, classes=config.CLASSES, reserve=args.reserve,
        aisle_factor=args.aisle_factor, reset_daily=not args.no_reset_daily)
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
            ("车位配比", group_header, group_rows),
            ("逐小时在场数", tl_header, tl_rows),
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
    print("输出目录:", args.out_dir)


if __name__ == "__main__":
    main()
