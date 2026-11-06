# 统计报表: 每小时/每日 CSV（Excel 可直接打开 CSV）
import csv
import os
from datetime import datetime


class Reporter:
    def __init__(self, hourly_csv, daily_csv, classes):
        self.hourly_csv = hourly_csv
        self.daily_csv = daily_csv
        self.classes = classes
        self.hourly = {}   # {(date, hour): {"enter":[...], "exit":[...]}}
        self.daily = {}    # {date: {...}}
        os.makedirs(os.path.dirname(hourly_csv), exist_ok=True)

    def record(self, ts: datetime, enter_counts, exit_counts):
        key_h = (ts.strftime("%Y-%m-%d"), ts.hour)
        bucket = self.hourly.setdefault(key_h, {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)})
        for i in range(len(self.classes)):
            bucket["enter"][i] += enter_counts[i]
            bucket["exit"][i] += exit_counts[i]

    def flush(self):
        self._write(self.hourly_csv, self.hourly, by_hour=True)
        self._write(self.daily_csv, self._aggregate_daily(), by_hour=False)

    def export_excel(self):
        """导出 Excel(.xlsx)。需要 openpyxl：uv pip install openpyxl"""
        try:
            from openpyxl import Workbook
        except ImportError:
            print("[warn] openpyxl 未安装，跳过 Excel 导出（uv pip install openpyxl）")
            return
        wb = Workbook()
        for idx, (name, data, by_hour) in enumerate([
            ("hourly", self.hourly, True),
            ("daily", self._aggregate_daily(), False),
        ]):
            ws = wb.active if idx == 0 else wb.create_sheet(name)
            ws.title = name
            header = ["period"] + [f"enter_{c}" for c in self.classes] + [f"exit_{c}" for c in self.classes]
            ws.append(header)
            for key in sorted(data.keys()):
                period = f"{key[0]} {key[1]:02d}:00" if by_hour else key
                ws.append([period] + data[key]["enter"] + data[key]["exit"])
        path = os.path.join(os.path.dirname(self.hourly_csv), "report.xlsx")
        wb.save(path)
        print("Excel 报表已生成:", path)

    def _aggregate_daily(self):
        daily = {}
        for (date, hour), v in self.hourly.items():
            b = daily.setdefault(date, {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)})
            for i in range(len(self.classes)):
                b["enter"][i] += v["enter"][i]
                b["exit"][i] += v["exit"][i]
        return daily

    def _write(self, path, data, by_hour):
        header = ["period"] + [f"enter_{c}" for c in self.classes] + [f"exit_{c}" for c in self.classes]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(header)
            for key in sorted(data.keys()):
                period = f"{key[0]} {key[1]:02d}:00" if by_hour else key
                row = [period] + data[key]["enter"] + data[key]["exit"]
                w.writerow(row)
