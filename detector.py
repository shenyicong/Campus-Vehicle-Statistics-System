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
    """真实YOLO检测(ONNX)。模型就绪后把 config.DETECTOR 改为 'yolo_onnx' 即可启用。"""
    def __init__(self, onnx_path, classes, conf=0.25, iou=0.45):
        import onnxruntime as ort
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"模型不存在: {onnx_path}")
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.classes = classes
        self.conf = conf
        self.iou = iou
        self.inp = self.session.get_inputs()[0].name
        self.in_h = self.session.get_inputs()[0].shape[2]
        self.in_w = self.session.get_inputs()[0].shape[3]

    def detect(self, frame):
        # 预处理 + 推理 + 后处理(NMS)，输出 [x1,y1,x2,y2,cls,conf]
        # 注: 具体后处理按模型输出格式实现，模型就绪后补全
        raise NotImplementedError("YOLO ONNX 后处理待实现（模型就绪后补全）")
