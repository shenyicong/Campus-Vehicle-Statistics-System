"""小时 / 日报表聚合与 CSV 输出测试。"""
import csv
from datetime import datetime

from reporter import Reporter

CLASSES = ["sedan", "suv"]


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def test_hourly_buckets_and_daily_aggregation(tmp_path):
    hourly = tmp_path / "hourly.csv"
    daily = tmp_path / "daily.csv"
    r = Reporter(str(hourly), str(daily), CLASSES)

    r.record(datetime(2026, 11, 9, 8, 10), [2, 1], [0, 1])
    r.record(datetime(2026, 11, 9, 8, 50), [1, 0], [1, 0])
    r.record(datetime(2026, 11, 9, 9, 0), [0, 0], [0, 0])
    r.record(datetime(2026, 11, 10, 7, 0), [3, 0], [0, 0])
    r.flush()

    rows = _read(hourly)
    assert rows[0] == ["period", "enter_sedan", "enter_suv", "exit_sedan", "exit_suv"]
    assert len(rows) == 4  # 表头 + 3 个小时桶
    assert rows[1] == ["2026-11-09 08:00", "3", "1", "1", "1"]
    assert rows[-1] == ["2026-11-10 07:00", "3", "0", "0", "0"]

    drows = _read(daily)
    assert drows[1] == ["2026-11-09", "3", "1", "1", "1"]
    assert drows[2] == ["2026-11-10", "3", "0", "0", "0"]


def test_empty_report_still_writes_header(tmp_path):
    r = Reporter(str(tmp_path / "hourly.csv"), str(tmp_path / "daily.csv"), CLASSES)
    r.flush()
    assert _read(tmp_path / "hourly.csv") == [
        ["period", "enter_sedan", "enter_suv", "exit_sedan", "exit_suv"]
    ]


def test_creates_report_directory(tmp_path):
    nested = tmp_path / "reports" / "nested"
    Reporter(str(nested / "hourly.csv"), str(nested / "daily.csv"), CLASSES)
    assert nested.is_dir()
