"""场地配置校验与车位供需推导测试。"""
import pytest

import parking_plan as pp


def _row(period, **counts):
    row = {"period": period}
    for direction in ("enter", "exit"):
        for cls in ("sedan", "suv", "truck", "bus"):
            row[f"{direction}_{cls}"] = 0
    row.update(counts)
    return row


def _zones():
    return {**pp.normalize_zones(pp.DEFAULT_ZONES), "source": "", "warnings": []}


def test_normalize_zones_filters_unknown_class_and_casts_slots():
    cfg = pp.normalize_zones({
        "site_name": "测试场地",
        "zones": [{"name": "A", "classes": ["sedan", "ufo"], "slots": "12"}],
    })
    z = cfg["zones"][0]
    assert z["classes"] == ["sedan"]
    assert z["slots"] == 12
    assert isinstance(z["slots"], int)
    assert cfg["site_name"] == "测试场地"


def test_validate_zones_rejects_negative_slots():
    data = {"zones": [{"name": "A", "classes": ["sedan"], "slots": -1}]}
    with pytest.raises(ValueError, match="不能为负数"):
        pp.validate_zones(data)


def test_validate_zones_rejects_empty_class_selection():
    data = {"zones": [{"name": "A", "classes": [], "slots": 10}]}
    with pytest.raises(ValueError, match="未选择任何适用车型"):
        pp.validate_zones(data)


def test_validate_zones_warns_about_uncovered_classes():
    cfg, warnings = pp.validate_zones({
        "zones": [{"name": "A", "classes": ["sedan"], "slots": 10}]
    })
    assert cfg["zones"][0]["classes"] == ["sedan"]
    assert any("未被任何分区覆盖" in w for w in warnings)


def test_load_zones_falls_back_to_builtin_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPUS_PARKING_ZONES", str(tmp_path / "missing.json"))
    cfg = pp.load_zones()
    assert cfg["source"] == ""
    assert cfg["site_name"] == "校园"
    assert len(cfg["zones"]) == 2


def test_save_and_load_zones_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "zones.json"
    monkeypatch.setenv("CAMPUS_PARKING_ZONES", str(path))
    data = {"site_name": "东门停车场", "zones": [
        {"id": "A", "name": "A 区", "classes": ["sedan"], "slots": 50},
    ]}
    cfg, warnings, saved = pp.save_zones(data)
    assert saved == str(path)
    assert any("未被任何分区覆盖" in w for w in warnings)
    loaded = pp.load_zones()
    assert loaded["site_name"] == "东门停车场"
    assert loaded["zones"][0]["slots"] == 50


def test_compute_peak_occupancy_and_supply_demand():
    rows = [
        _row("2026-11-09 08:00", enter_sedan=10, exit_sedan=2),
        _row("2026-11-09 09:00", exit_sedan=3),
    ]
    result = pp.compute(rows, zones=_zones())
    assert result["hours"] == 2
    assert result["per_class"]["sedan"]["peak_occupancy"] == 8
    assert result["groups"]["small"]["peak_occupancy"] == 8
    assert result["groups"]["small"]["recommended_slots"] == 10  # ceil(8 * 1.2)
    zone_a = result["zones"]["items"][0]
    assert zone_a["name"] == "A 区"
    assert zone_a["supply_slots"] == 360
    assert zone_a["gap_slots"] > 0
    assert zone_a["status"] == "供给充足"


def test_compute_reset_daily_prevents_cross_day_accumulation():
    rows = [
        _row("2026-11-09 08:00", enter_sedan=10),
        _row("2026-11-10 08:00", enter_sedan=5),
    ]
    with_reset = pp.compute(rows, zones=_zones(), reset_daily=True)
    without_reset = pp.compute(rows, zones=_zones(), reset_daily=False)
    assert with_reset["per_class"]["sedan"]["peak_occupancy"] == 10
    assert without_reset["per_class"]["sedan"]["peak_occupancy"] == 15
