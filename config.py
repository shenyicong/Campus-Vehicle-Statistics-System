# 校园车辆智能统计系统 - 全局配置
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(PROJECT_DIR, "data")
REPORT_DIR  = os.path.join(DATA_DIR, "reports")
TEST_VIDEO  = os.path.join(DATA_DIR, "test_monitor.mp4")
# 合成测试视频用的车型图片源：可用环境变量 CAMPUS_CAR_DIR 覆盖，默认 D:\car
SOURCE_DIR  = os.environ.get("CAMPUS_CAR_DIR", r"D:\car")

# 视频源: False=本地文件, True=RTSP实时流（一行切换，不返工）
USE_RTSP = False
RTSP_URL = ""   # 例如 "rtsp://admin:pass@192.168.1.64:554/stream"

# 车型类别（4类，与标注/训练保持一致）；索引顺序即模型输出类别顺序
CLASSES = ["sedan", "suv", "truck", "bus"]
CLASS_CN = {"sedan": "轿车", "suv": "SUV", "truck": "货车", "bus": "客车"}

# 检测器: "mock" 模拟检测(跑通全链路) / "yolo_onnx" 真实YOLO模型
DETECTOR = "mock"
YOLO_ONNX = os.path.join(DATA_DIR, "yolov8n.onnx")

# 进出判定虚拟线（归一化 y，0=顶部 1=底部）
LINE_Y = 0.5
# 车辆向下穿越=进校(enter)，向上=出校(exit)
ENTER_WHEN = "down"

# 报表
HOURLY_CSV = os.path.join(REPORT_DIR, "hourly.csv")
DAILY_CSV  = os.path.join(REPORT_DIR, "daily.csv")

# 网页仪表盘
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000
