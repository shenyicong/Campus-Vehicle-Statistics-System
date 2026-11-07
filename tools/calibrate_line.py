"""虚拟线标定工具：找出画面里车辆的实际 y 分布，避免把 LINE_Y 放在空白区。

背景：固定机位俯拍画面里，上半部常是天空/建筑，车辆中心 cy 往往全部 > 0.55。
若沿用默认 LINE_Y=0.5，虚拟线落在空白区，进出计数会永远是 0。

用法:
  python tools/calibrate_line.py --video <视频> --frames 120
  CAMPUS_VIDEO=<视频> python tools/calibrate_line.py

输出各候选线位置的跨线次数，并判断车流是否近似静止（静止时的"跨线"
多为检测框抖动，不能当作真实过车）。
"""
import argparse
import os
import sys
from collections import defaultdict

import cv2
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import config
from detector import TiledYoloOnnxDetector
from tracker import IoUTracker

CANDIDATES = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def main():
    ap = argparse.ArgumentParser(description="虚拟线标定（找车辆 y 分布）")
    ap.add_argument("--video", default=config.TEST_VIDEO)
    ap.add_argument("--frames", type=int, default=120, help="分析前 N 帧")
    ap.add_argument("--conf", type=float, default=config.CONF_THRES)
    args = ap.parse_args()

    if not os.path.exists(args.video):
        raise SystemExit("视频不存在: " + args.video)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit("无法打开视频: " + args.video)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    det = TiledYoloOnnxDetector(config.YOLO_ONNX, config.CLASSES,
                                conf=args.conf, iou=config.IOU_THRES,
                                mode=config.TILE_MODE)
    tracker = IoUTracker()
    hist = defaultdict(list)   # track id -> [(frame_idx, cy), ...]
    all_cy = []
    used = 0
    for i in range(args.frames):
        ok, frame = cap.read()
        if not ok:
            break
        used += 1
        for t in tracker.update(det.detect(frame)):
            y1, y2 = t["bbox"][1], t["bbox"][3]
            cy = ((y1 + y2) / 2.0) / h
            hist[t["id"]].append((i, cy))
            all_cy.append(cy)
    cap.release()

    print("视频      : %s" % args.video)
    print("规格      : %dx%d   分析帧数: %d   当前 LINE_Y: %.2f" % (w, h, used, config.LINE_Y))
    if not all_cy:
        raise SystemExit("未检出任何车辆，无法标定")
    a = np.array(all_cy)
    pct = np.percentile(a, [0, 10, 25, 50, 75, 90, 100])
    print("车辆 cy   : min %.3f  p10 %.3f  p25 %.3f  中位 %.3f  p75 %.3f  p90 %.3f  max %.3f" % tuple(pct))
    print("跟踪 ID   : %d   平均每帧框数: %.1f" % (len(hist), len(all_cy) / max(1, used)))

    moves = []
    for seq in hist.values():
        seq.sort()
        for (f0, c0), (f1, c1) in zip(seq, seq[1:]):
            if f1 - f0 == 1:
                moves.append(abs(c1 - c0))
    med_move = float(np.median(moves)) if moves else 0.0
    print("连续帧|dy|: 中位 %.4f  均值 %.4f  最大 %.4f" %
          (med_move, float(np.mean(moves)) if moves else 0.0,
           float(np.max(moves)) if moves else 0.0))

    print("\n=== 各候选虚拟线的跨线次数（仅连续帧）===")
    for line in CANDIDATES:
        down = up = 0
        for seq in hist.values():
            seq.sort()
            for (f0, c0), (f1, c1) in zip(seq, seq[1:]):
                if f1 - f0 != 1:
                    continue
                if c0 < line <= c1:
                    down += 1
                elif c0 > line >= c1:
                    up += 1
        flag = "  <- 当前" if abs(line - config.LINE_Y) < 1e-6 else ""
        print("  LINE_Y=%.2f -> 向下(进) %3d  向上(出) %3d%s" % (line, down, up, flag))

    print("\n=== 判定 ===")
    if config.LINE_Y < pct[0]:
        print("  ❌ 当前虚拟线 %.2f 低于车辆 cy 最小值 %.3f，落在空白区，必然计 0。" %
              (config.LINE_Y, pct[0]))
        print("     建议设到车辆分布内，例如 p25~中位之间: CAMPUS_LINE_Y=%.2f" % round(float(pct[2]), 2))
    else:
        print("  ✅ 当前虚拟线位于车辆分布内。")
    if med_move < 0.002:
        print("  ⚠️ 车流近似静止（连续帧位移中位 %.4f），上表跨线数多为检测框抖动，" % med_move)
        print("     不能当作真实过车。请换一段车流持续通过的固定机位视频再统计。")
    else:
        print("  ✅ 车流有持续位移，跨线数可作为参考。")


if __name__ == "__main__":
    main()
