# 校园车辆智能统计系统 - 全局配置
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(PROJECT_DIR, "data")
# 报表目录：看板与 main.py 共用；可用 CAMPUS_REPORT_DIR 指向某次真实视频评估的报表
REPORT_DIR  = os.environ.get("CAMPUS_REPORT_DIR", os.path.join(DATA_DIR, "reports"))
# 可用 set CAMPUS_VIDEO=D:\path\to.mp4 临时切换视频源，无需改代码
TEST_VIDEO  = os.environ.get("CAMPUS_VIDEO", os.path.join(DATA_DIR, "test_monitor.mp4"))
# 合成测试视频用的车型图片源：可用环境变量 CAMPUS_CAR_DIR 覆盖，默认 D:\car
SOURCE_DIR  = os.environ.get("CAMPUS_CAR_DIR", r"D:\car")

# 视频源: False=本地文件, True=RTSP实时流（一行切换，不返工）
USE_RTSP = False
RTSP_URL = ""   # 例如 "rtsp://admin:pass@192.168.1.64:554/stream"

# 车型类别（4类，与标注/训练保持一致）；索引顺序即模型输出类别顺序
CLASSES = ["sedan", "suv", "truck", "bus"]
CLASS_CN = {"sedan": "轿车", "suv": "SUV", "truck": "货车", "bus": "客车"}

# 检测器: "yolo_onnx" 真实YOLO模型(默认) / "mock" 模拟检测(跑通全链路)
# 想跑模拟数据: set CAMPUS_DETECTOR=mock
DETECTOR = os.environ.get("CAMPUS_DETECTOR", "yolo_onnx")
YOLO_ONNX = os.path.join(PROJECT_DIR, "models", "car_yolo.onnx")
# 检测置信度阈值；真实场景漏检多时可临时下调: set CAMPUS_CONF=0.15
CONF_THRES = float(os.environ.get("CAMPUS_CONF", "0.25"))
IOU_THRES = 0.45    # NMS IoU 阈值

# 分块推理（显著提升远景小车召回，无需重训模型）
# auto = 按长边一维切块(默认，快) / grid = 二维网格(远景小车召回最高，推理约3倍耗时)
# 1 = 强制一维切块 / 0 = 整图不切块
TILE_MODE = os.environ.get("CAMPUS_TILE", "auto")
TILE_SIZE = 640
TILE_OVERLAP = 0.4

# 进出判定虚拟线（归一化 y，0=顶部 1=底部）
# 换视频后务必用 tools/calibrate_line.py 标定：俯拍画面上半部常是天空/建筑，
# 默认 0.5 可能落在空白区导致计数恒为 0。可 set CAMPUS_LINE_Y=0.72 覆盖。
LINE_Y = float(os.environ.get("CAMPUS_LINE_Y", "0.5"))
# 车辆向下穿越=进校(enter)，向上=出校(exit)
ENTER_WHEN = "down"
# 抑制检测框抖动造成的假跨线：轨迹需相对参考点移动至少该幅度（占画面高度）
# 静止车流/延时视频建议保持默认；可 set CAMPUS_MIN_MOVE=0.02 调整
MIN_TRACK_MOVE = float(os.environ.get("CAMPUS_MIN_MOVE", "0.03"))

# 报表
HOURLY_CSV = os.path.join(REPORT_DIR, "hourly.csv")
DAILY_CSV  = os.path.join(REPORT_DIR, "daily.csv")

# 场地车位配置：由本地人员按实际场地维护（分区名 / 服务车型 / 实有车位数）
# 可在网页看板「场地车位设置」中编辑保存；也可用环境变量切换到别的场地文件
# set CAMPUS_PARKING_ZONES=D:\path\to\my_zones.json
PARKING_ZONES_JSON = os.environ.get(
    "CAMPUS_PARKING_ZONES", os.path.join(DATA_DIR, "parking_zones.json"))

# 网页仪表盘
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000
