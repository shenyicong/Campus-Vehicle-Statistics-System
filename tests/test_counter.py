"""虚拟线进出判定与计数测试。"""
from counter import Counter

CLASSES = ["sedan", "suv", "truck", "bus"]
H = 100  # 用 100px 高的虚拟画面，便于用归一化 y 直接构造框


def _track(tid, cy, cls=0):
    center = cy * H
    return {"id": tid, "bbox": [0, center - 5, 10, center + 5], "cls": cls}


def test_crossing_down_counts_as_enter():
    c = Counter(line_y=0.5, classes=CLASSES, min_move=0.03)
    c.update([_track(1, 0.40)], H)
    c.update([_track(1, 0.60)], H)
    assert c.snapshot()["enter"]["sedan"] == 1
    assert c.snapshot()["exit"]["sedan"] == 0


def test_crossing_up_counts_as_exit():
    c = Counter(line_y=0.5, classes=CLASSES, min_move=0.03)
    c.update([_track(1, 0.60)], H)
    c.update([_track(1, 0.40)], H)
    assert c.snapshot()["exit"]["sedan"] == 1
    assert c.snapshot()["enter"]["sedan"] == 0


def test_enter_when_up_reverses_direction():
    c = Counter(line_y=0.5, enter_when="up", classes=CLASSES, min_move=0.03)
    c.update([_track(1, 0.60)], H)
    c.update([_track(1, 0.40)], H)
    assert c.snapshot()["enter"]["sedan"] == 1


def test_small_jitter_does_not_create_false_crossing():
    # 静止车流的框抖动约 0.001~0.01，MIN_TRACK_MOVE 应压住假过车
    c = Counter(line_y=0.5, classes=CLASSES, min_move=0.03)
    for cy in (0.490, 0.495, 0.500, 0.505, 0.510):
        c.update([_track(1, cy)], H)
    assert sum(c.grand["enter"]) == 0
    assert sum(c.grand["exit"]) == 0


def test_class_goes_to_correct_bucket():
    c = Counter(line_y=0.5, classes=CLASSES, min_move=0.03)
    c.update([_track(1, 0.40, cls=2)], H)
    c.update([_track(1, 0.60, cls=2)], H)
    snap = c.snapshot()
    assert snap["enter"]["truck"] == 1
    assert snap["enter"]["sedan"] == 0


def test_pop_increment_resets_but_grand_total_persists():
    c = Counter(line_y=0.5, classes=CLASSES, min_move=0.03)
    c.update([_track(1, 0.40)], H)
    c.update([_track(1, 0.60)], H)
    inc = c.pop_increment()
    assert inc["enter"][0] == 1
    assert c.pop_increment()["enter"][0] == 0
    assert c.snapshot()["enter"]["sedan"] == 1
