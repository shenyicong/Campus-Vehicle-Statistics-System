# 检测器封装: 基类 + Mock(场景模拟) + YOLO-ONNX(预留真实模型)
import os


class Detector:
    def detect(self, frame):
        raise NotImplementedError

    def close(self):
        pass


class ScenarioMockDetector(Detector):
    """模拟校门口车辆: 几辆虚拟车按轨迹跨过判定线，用于验证全链路"""
    def __init__(self, w, h, classes):
        self.w, self.h = w, h
        self.classes = classes
        # 每辆车: 类别索引, 归一化位置, 速度, 剩余寿命(帧)
        self.cars = [
            {"cls": 0, "x": 0.30, "y": 0.15, "vx": 0.0020, "vy": 0.010, "life": 200},
            {"cls": 3, "x": 0.62, "y": 0.85, "vx": -0.0015, "vy": -0.011, "life": 200},
            {"cls": 1, "x": 0.46, "y": 0.12, "vx": 0.0000, "vy": 0.010, "life": 180},
            {"cls": 2, "x": 0.75, "y": 0.90, "vx": -0.0020, "vy": -0.009, "life": 160},
        ]

    def detect(self, frame):
        out = []
        for c in self.cars:
            if c["life"] <= 0:
                continue
            c["life"] -= 1
            c["x"] += c["vx"]
            c["y"] += c["vy"]
            bw, bh = 0.06, 0.09
            x1 = int((c["x"] - bw) * self.w); y1 = int((c["y"] - bh) * self.h)
            x2 = int((c["x"] + bw) * self.w); y2 = int((c["y"] + bh) * self.h)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(self.w - 1, x2), min(self.h - 1, y2)
            out.append([x1, y1, x2, y2, c["cls"], 0.95])
        return out


class YoloOnnxDetector(Detector):
    """真实 YOLO11/YOLOv8 检测（ONNX Runtime，CPU 即可运行）。

    模型由 Ultralytics `format=onnx` 导出，本项目的 4 类模型结构为：
        输入 images  [1, 3, 640, 640]   RGB、0~1、letterbox
        输出 output0 [1, 4+nc, 8400]   前 4 行 cx,cy,w,h（输入图坐标），
                                        后 nc 行为各类别分数（无 objectness）
    返回给跟踪器: [x1, y1, x2, y2, cls_id, conf]，坐标为原图像素。
    """
    def __init__(self, onnx_path, classes, conf=0.25, iou=0.45):
        import numpy as np
        import cv2
        import onnxruntime as ort
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"模型不存在: {onnx_path}")
        self.np, self.cv2 = np, cv2
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.classes = classes
        self.conf = conf
        self.iou = iou
        inp = self.session.get_inputs()[0]
        self.inp = inp.name
        shape = inp.shape  # [1, 3, H, W]；动态轴时回退 640
        self.in_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.in_w = int(shape[3]) if isinstance(shape[3], int) else 640

    def _letterbox(self, frame):
        """等比缩放 + 灰边填充到模型输入尺寸，返回 (图, scale, (pad_w, pad_h))"""
        h, w = frame.shape[:2]
        r = min(self.in_h / h, self.in_w / w)
        nw, nh = int(round(w * r)), int(round(h * r))
        resized = (self.cv2.resize(frame, (nw, nh), interpolation=self.cv2.INTER_LINEAR)
                   if (nw, nh) != (w, h) else frame)
        dw, dh = (self.in_w - nw) / 2.0, (self.in_h - nh) / 2.0
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        padded = self.cv2.copyMakeBorder(resized, top, bottom, left, right,
                                         self.cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return padded, r, (dw, dh)

    def detect(self, frame):
        np, cv2 = self.np, self.cv2
        if frame is None or frame.size == 0:
            return []

        # --- 预处理 ---
        img, r, (dw, dh) = self._letterbox(frame)
        blob = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None]
        blob = np.ascontiguousarray(blob.astype(np.float32) / 255.0)

        # --- 推理 ---
        pred = self.session.run(None, {self.inp: blob})[0]   # [1, 4+nc, N]
        if pred.ndim == 3:
            pred = pred[0]
        pred = pred.T                                         # [N, 4+nc]

        # --- 解码：取每框最高类别分数，过滤低置信 ---
        scores = pred[:, 4:]
        cls_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        mask = confs >= self.conf
        if not mask.any():
            return []
        xywh, cls_ids, confs = pred[mask, :4], cls_ids[mask], confs[mask]

        cx, cy, bw, bh = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
        x1 = (cx - bw / 2 - dw) / r
        y1 = (cy - bh / 2 - dh) / r
        x2 = (cx + bw / 2 - dw) / r
        y2 = (cy + bh / 2 - dh) / r
        h, w = frame.shape[:2]
        x1, y1 = np.clip(x1, 0, w), np.clip(y1, 0, h)
        x2, y2 = np.clip(x2, 0, w), np.clip(y2, 0, h)

        # --- 按类别分别 NMS（不同车型的框紧挨时不会互相抑制）---
        out = []
        for c in range(len(self.classes)):
            idx = np.where(cls_ids == c)[0]
            if idx.size == 0:
                continue
            rects = [[float(x1[i]), float(y1[i]),
                      float(x2[i] - x1[i]), float(y2[i] - y1[i])] for i in idx]
            score_c = [float(confs[i]) for i in idx]
            nms = cv2.dnn.NMSBoxes(rects, score_c, self.conf, self.iou)
            if nms is None or len(nms) == 0:
                continue
            for j in np.array(nms).reshape(-1):
                i = idx[int(j)]
                out.append([int(x1[i]), int(y1[i]), int(x2[i]), int(y2[i]),
                            c, float(confs[i])])
        return out


class TiledYoloOnnxDetector(YoloOnnxDetector):
    """按画面长边方向切块的推理：解决 letterbox 压缩导致远景小车漏检。

    长条画面整图送进 640x640 模型时，短边被大幅压缩，远景小车会缩到几像素
    而漏检。本类沿**长边**切成若干重叠块，逐块调用父类 detect，坐标平移回
    原图后按类别再做一次 NMS 合并，不需要重新训练模型。

    - 竖屏 (h >= ratio*w)：沿高度切横块，如 1080x1920 -> 5 块 1080x640
    - 宽幅横屏 (w >= ratio*h)：沿宽度切竖块，如 1280x720 -> 3 块 640x720
    - 近方形：不切块，直接整图推理
    - mode="grid"：横纵两个方向都切 640x640 网格（1080x1920 -> 3x5=15 块）。
      一维分块只把短边从 ~360px 恢复到 640px，网格分块则让两个方向都不被
      压缩，远景小车召回进一步显著提升，代价是推理次数约 3 倍。

    实测竖屏固定机位视频检出框 125 -> 623；横屏密集车流单帧 1 -> 10、
    20 -> 36。重庆内环高速俯拍 frame0+180：整图 14 框 -> 一维 24 框 ->
    网格 41 框（conf 0.15 时 56 框），新增框均为真车。
    注意「沿高度切横块」用在横屏上会加重压缩，方向必须按长边选。
    """
    def __init__(self, onnx_path, classes, conf=0.25, iou=0.45,
                 mode="auto", tile_size=640, overlap=0.4, min_ratio=1.4):
        super().__init__(onnx_path, classes, conf=conf, iou=iou)
        self.mode = mode              # auto / 1 / 0
        self.tile_size = int(tile_size)
        self.overlap = float(overlap)
        self.min_ratio = float(min_ratio)

    def _starts(self, length):
        """沿单轴生成重叠滑窗起点，返回 (起点列表, 实际窗口边长)"""
        ts = min(self.tile_size, length)
        step = max(1, int(ts * (1 - self.overlap)))
        starts = list(range(0, max(0, length - ts) + 1, step))
        if not starts or starts[-1] != length - ts:
            starts.append(length - ts)
        return sorted(set(s for s in starts if 0 <= s <= length - ts)), ts

    def _grid_detect(self, frame):
        """二维网格分块：横纵都切，块接近 640x640，缩放系数≈1，无压缩损失"""
        h, w = frame.shape[:2]
        ys, tsh = self._starts(h)
        xs, tsw = self._starts(w)
        raw = []
        for sy in ys:
            for sx in xs:
                crop = frame[sy:sy + tsh, sx:sx + tsw]
                for b in super().detect(crop):
                    b = list(b)
                    b[0] += sx
                    b[2] += sx
                    b[1] += sy
                    b[3] += sy
                    raw.append(b)
        return self._merge_nms(raw)

    def detect(self, frame):
        if frame is None or frame.size == 0:
            return []
        h, w = frame.shape[:2]
        if self.mode == "0":
            return super().detect(frame)
        if self.mode == "grid":
            return self._grid_detect(frame)

        portrait = h >= w * self.min_ratio
        landscape = w >= h * self.min_ratio
        if self.mode != "1" and not (portrait or landscape):
            return super().detect(frame)

        # 沿长边切块：竖屏切横块，宽幅横屏切竖块；近方形强制模式沿用旧的纵向切法
        axis = "y" if portrait else ("x" if landscape else "y")
        length = h if axis == "y" else w
        ts = min(self.tile_size, length)
        step = max(1, int(ts * (1 - self.overlap)))
        starts = list(range(0, max(0, length - ts) + 1, step))
        if not starts or starts[-1] != length - ts:
            starts.append(length - ts)
        starts = sorted(set(s for s in starts if 0 <= s <= length - ts))

        raw = []
        for s in starts:
            if axis == "y":
                crop, dx, dy = frame[s:s + ts, 0:w], 0, s
            else:
                crop, dx, dy = frame[0:h, s:s + ts], s, 0
            for b in super().detect(crop):
                b = list(b)
                b[0] += dx
                b[2] += dx
                b[1] += dy
                b[3] += dy
                raw.append(b)
        return self._merge_nms(raw)

    def _merge_nms(self, boxes):
        if not boxes:
            return []
        cv2, np = self.cv2, self.np
        out = []
        for c in range(len(self.classes)):
            group = [b for b in boxes if int(b[4]) == c]
            if not group:
                continue
            rects = [[float(b[0]), float(b[1]),
                      float(b[2] - b[0]), float(b[3] - b[1])] for b in group]
            scores = [float(b[5]) for b in group]
            keep = cv2.dnn.NMSBoxes(rects, scores, 0.0, self.iou)
            if keep is None or len(keep) == 0:
                continue
            for j in np.array(keep).reshape(-1):
                out.append(group[int(j)])
        return out
