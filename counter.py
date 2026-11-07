# 进出判定与计数: 根据车辆轨迹跨越虚拟线的方向判定进/出
class Counter:
    def __init__(self, line_y=0.5, enter_when="down", classes=None, min_move=0.03):
        self.line_y = line_y
        self.enter_when = enter_when   # "down"=向下为进校
        self.classes = classes or ["obj"]
        self.min_move = float(min_move)  # 最小净位移，抑制框抖动造成的假跨线
        self.prev_y = {}               # id -> 上一帧归一化中心y
        self.ref_y = {}                # id -> 上次计数/首次出现时的参考y
        self.total = {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)}
        self.grand = {"enter": [0] * len(self.classes), "exit": [0] * len(self.classes)}

    def update(self, tracks, frame_h):
        for t in tracks:
            x1, y1, x2, y2 = t["bbox"]
            cy = ((y1 + y2) / 2.0) / frame_h   # 归一化中心y
            pid = self.prev_y.get(t["id"])
            ref = self.ref_y.get(t["id"], cy)
            # 只有轨迹相对参考点产生足够净位移才允许判定跨线。
            # 静止车流中检测框会上下抖动 0.001~0.01，若无此门限，
            # 把虚拟线放在车辆密集区就会反复产生「假过车」。
            if pid is not None and abs(cy - ref) >= self.min_move:
                crossed_down = pid < self.line_y <= cy
                crossed_up = pid > self.line_y >= cy
                hit = None
                if self.enter_when == "down":
                    if crossed_down:
                        hit = "enter"
                    elif crossed_up:
                        hit = "exit"
                else:
                    if crossed_up:
                        hit = "enter"
                    elif crossed_down:
                        hit = "exit"
                if hit:
                    self._add(hit, t["cls"])
                    ref = cy     # 计数后重置参考点，避免同一轨迹重复计数
            self.ref_y[t["id"]] = ref
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
