"""IoU 计算与轻量跟踪器的纯逻辑测试（不依赖模型 / 视频）。"""
import pytest

from tracker import IoUTracker, iou


def test_iou_identical_boxes():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0, abs=1e-3)


def test_iou_no_overlap():
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_iou_partial_overlap():
    # 交集 25，并集 100+100-25=175
    assert iou((0, 0, 10, 10), (5, 5, 15, 15)) == pytest.approx(25 / 175, abs=1e-3)


def _det(x1, y1, x2, y2, cls=0, conf=0.9):
    return [x1, y1, x2, y2, cls, conf]


def test_first_frame_assigns_ids():
    t = IoUTracker()
    out = t.update([_det(0, 0, 10, 10), _det(30, 30, 40, 40)])
    assert [o["id"] for o in out] == [1, 2]


def test_same_object_keeps_id_across_frames():
    t = IoUTracker()
    t.update([_det(0, 0, 10, 10, cls=2)])
    out = t.update([_det(1, 1, 11, 11, cls=2, conf=0.8)])
    assert len(out) == 1
    assert out[0]["id"] == 1
    assert out[0]["conf"] == 0.8


def test_unmatched_detection_creates_new_track():
    t = IoUTracker()
    t.update([_det(0, 0, 10, 10)])
    out = t.update([_det(0, 0, 10, 10), _det(300, 300, 320, 320)])
    assert {o["id"] for o in out} == {1, 2}


def test_missed_track_not_returned_as_active():
    # 僵尸轨迹若被返回，会虚增每帧框数并把连续帧位移中位压成 0
    t = IoUTracker(max_miss=3)
    t.update([_det(0, 0, 10, 10)])
    assert t.update([]) == []
    assert len(t.tracks) == 1


def test_track_pruned_after_max_miss():
    t = IoUTracker(max_miss=1)
    t.update([_det(0, 0, 10, 10)])
    t.update([])  # miss = 1
    t.update([])  # miss = 2 > max_miss
    assert t.tracks == []
