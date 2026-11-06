# 端到端串联: 视频 -> 检测 -> 跟踪 -> 进出判定 -> 计数 -> 报表
import os
import sys
import datetime
import argparse
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from video_input import open_source
from detector import ScenarioMockDetector, YoloOnnxDetector
from tracker import IoUTracker
from counter import Counter
from reporter import Reporter


def build_detector(w, h):
    if config.DETECTOR == "yolo_onnx":
        return YoloOnnxDetector(config.YOLO_ONNX, config.CLASSES)
    return ScenarioMockDetector(w, h, config.CLASSES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max_frames", type=int, default=600, help="处理帧数上限(测试用)")
    args = ap.parse_args()

    cap = open_source(config.USE_RTSP, config.RTSP_URL, config.TEST_VIDEO)
    w = int(cap.get(3)); h = int(cap.get(4)); fps = int(cap.get(5) or 25)

    det = build_detector(w, h)
    trk = IoUTracker(iou_thresh=0.3, max_miss=30)
    cnt = Counter(line_y=config.LINE_Y, enter_when=config.ENTER_WHEN, classes=config.CLASSES)
    rep = Reporter(config.HOURLY_CSV, config.DAILY_CSV, config.CLASSES)

    start = datetime.datetime.now()
    frame_i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_i += 1
        tracks = trk.update(det.detect(frame))
        cnt.update(tracks, h)
        if frame_i % fps == 0:
            inc = cnt.pop_increment()
            rep.record(start + datetime.timedelta(seconds=frame_i / fps), inc["enter"], inc["exit"])
        if frame_i >= args.max_frames:
            break

    rep.flush()
    rep.export_excel()
    cap.release()
    det.close()
    print("处理帧数:", frame_i)
    print("累计计数:", cnt.snapshot())
    print("报表已生成:", config.HOURLY_CSV)
    print("            ", config.DAILY_CSV)


if __name__ == "__main__":
    main()
