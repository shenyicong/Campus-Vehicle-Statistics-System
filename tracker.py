# 轻量多目标跟踪: 基于 IoU 匹配的简易跟踪器（无第三方依赖）
def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / (area_a + area_b - inter + 1e-6)


class IoUTracker:
    def __init__(self, iou_thresh=0.3, max_miss=30):
        self.tracks = []      # {id, bbox, cls, conf, miss}
        self.next_id = 1
        self.iou_thresh = iou_thresh
        self.max_miss = max_miss

    def update(self, dets):
        # dets: [[x1,y1,x2,y2,cls,conf], ...]
        if not self.tracks:
            for d in dets:
                self.tracks.append({"id": self.next_id, "bbox": d[:4], "cls": d[4], "conf": d[5], "miss": 0})
                self.next_id += 1
            return self.tracks

        used_det = set()
        for t in self.tracks:
            best_i, best_v = -1, self.iou_thresh
            for i, d in enumerate(dets):
                if i in used_det:
                    continue
                v = iou(t["bbox"], d[:4])
                if v > best_v:
                    best_v, best_i = v, i
            if best_i >= 0:
                t["bbox"] = dets[best_i][:4]
                t["cls"] = dets[best_i][4]
                t["conf"] = dets[best_i][5]
                t["miss"] = 0
                used_det.add(best_i)
            else:
                t["miss"] += 1

        for i, d in enumerate(dets):
            if i not in used_det:
                self.tracks.append({"id": self.next_id, "bbox": d[:4], "cls": d[4], "conf": d[5], "miss": 0})
                self.next_id += 1

        self.tracks = [t for t in self.tracks if t["miss"] <= self.max_miss]
        return self.tracks
