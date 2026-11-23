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


# ---- 创新点 3 A/B：轨迹级车型众数投票 ----

def test_A_cls_vote_off_uses_latest_frame():
    """A 组（默认）保持原行为：车型取当前帧检测类别。"""
    t = IoUTracker(cls_vote=False)
    t.update([_det(0, 0, 10, 10, cls=0)])
    out = t.update([_det(1, 1, 11, 11, cls=1)])
    assert out[0]["cls"] == 1


def test_B_majority_vote_corrects_single_frame_error():
    """B 组：3 帧中 2 帧为货车、1 帧误判为轿车，整条轨迹应判为货车。"""
    t = IoUTracker(cls_vote=True)
    t.update([_det(0, 0, 10, 10, cls=2)])
    t.update([_det(1, 1, 11, 11, cls=2)])
    out = t.update([_det(2, 2, 12, 12, cls=0)])
    assert out[0]["cls"] == 2           # 众数纠正单帧错检
    assert out[0]["last_cls"] == 0      # 同时保留本帧原始检测，供平票回退
    assert out[0]["cls_votes"] == {2: 2, 0: 1}


def test_B_tie_falls_back_to_latest_detection():
    """平票时退化为最近一帧检测类别，与 A 组语义一致。"""
    t = IoUTracker(cls_vote=True)
    t.update([_det(0, 0, 10, 10, cls=1)])
    out = t.update([_det(1, 1, 11, 11, cls=2)])
    assert out[0]["cls"] == 2


def test_missed_frame_does_not_cast_vote():
    """未匹配的帧不应投票，否则轨迹停滞时会把静止类别越投越多。"""
    t = IoUTracker(cls_vote=True, max_miss=5)
    t.update([_det(0, 0, 10, 10, cls=0)])
    t.update([])
    t.update([_det(1, 1, 11, 11, cls=0)])
    assert t.tracks[0]["cls_votes"] == {0: 2}


def test_votes_are_isolated_per_track():
    """多条轨迹各自投票，不能相互串票。"""
    t = IoUTracker(cls_vote=True)
    t.update([_det(0, 0, 10, 10, cls=0), _det(50, 50, 60, 60, cls=1)])
    t.update([_det(1, 1, 11, 11, cls=0), _det(51, 51, 61, 61, cls=0)])
    out = t.update([_det(2, 2, 12, 12, cls=0), _det(52, 52, 62, 62, cls=1)])
    assert sorted(o["cls"] for o in out) == [0, 1]
    assert out[1]["cls_votes"] == {1: 2, 0: 1}
