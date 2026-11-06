# 进出判定与计数: 根据车辆轨迹跨越虚拟线的方向判定进/出
class Counter:
    def __init__(self, line_y=0.5, enter_when="down", classes=None):
        self.line_y = line_y
        self.enter_when = enter_when   # "down"=向下为进校
        self.classes = classes or ["obj"]
        self.prev_y = {}               # id -> 上一帧归一化中心y
        self.total = {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)}
        self.grand = {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)}

    def update(self, tracks, frame_h):
        for t in tracks:
            x1, y1, x2, y2 = t["bbox"]
            cy = ((y1 + y2) / 2.0) / frame_h   # 归一化中心y
            pid = self.prev_y.get(t["id"])
            if pid is not None:
                crossed_down = pid < self.line_y <= cy
                crossed_up = pid > self.line_y >= cy
                if self.enter_when == "down":
                    if crossed_down:
                        self._add("enter", t["cls"])
                    elif crossed_up:
                        self._add("exit", t["cls"])
                else:
                    if crossed_up:
                        self._add("enter", t["cls"])
                    elif crossed_down:
                        self._add("exit", t["cls"])
            self.prev_y[t["id"]] = cy

    def _add(self, direction, cls_idx):
        self.total[direction][int(cls_idx)] += 1
        self.grand[direction][int(cls_idx)] += 1

    def pop_increment(self):
        """返回自上次调用以来的进出增量并清零，供报表按时间分桶记录"""
        inc = {"enter": list(self.total["enter"]), "exit": list(self.total["exit"])}
        self.total["enter"] = [0] * len(self.classes)
        self.total["exit"] = [0] * len(self.classes)
        return inc

    def snapshot(self):
        return {
            "enter": dict(zip(self.classes, self.grand["enter"])),
            "exit": dict(zip(self.classes, self.grand["exit"])),
        }
