"""真实视频端到端评估：一次推理同时产出检测统计、进出计数、报表与演示图。

与 tools/eval_real_video.py（只抽样评估检测）和 main.py（只做计数）不同，
本脚本逐帧遍历视频并一次完成两件事，避免对同一段高分辨率视频重复跑
分块推理（grid 模式每帧 15 次推理，重复跑代价很高）。

适用前提：固定机位、镜头不动、连续无剪辑、车流持续通过。
换视频后请先用 tools/calibrate_line.py 标定 --line-y。

用法:
  python tools/eval_count_video.py --video <视频> --tile grid --line-y 0.65
  python tools/eval_count_video.py --video <视频> --out data/real_eval_demo --save-frames 12

输出:
  <out>/summary.txt, summary.json
  <out>/frames/*.jpg            带检测框 + 虚拟线 + 累计计数的可视化帧
  <out>/overview.jpg            4 帧缩略拼图（报告素材）
  <out>/reports/hourly.csv, daily.csv, report.xlsx
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

import cv2
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import config
from detector import TiledYoloOnnxDetector
from tracker import IoUTracker
from counter import Counter as LineCounter
from reporter import Reporter


def main():
    ap = argparse.ArgumentParser(description="固定机位真实视频：检测评估 + 进出计数 + 报表")
    ap.add_argument("--video", default=config.TEST_VIDEO, help="本地视频路径")
    ap.add_argument("--out", default=os.path.join(config.DATA_DIR, "real_eval_full"),
                    help="结果输出目录")
    ap.add_argument("--tile", default=config.TILE_MODE, choices=["auto", "grid", "1", "0"],
                    help="分块推理模式；grid 远景召回最高但慢约 3 倍")
    ap.add_argument("--conf", type=float, default=config.CONF_THRES)
    ap.add_argument("--line-y", type=float, default=config.LINE_Y,
                    help="虚拟线归一化 y，务必先用 calibrate_line.py 标定")
    ap.add_argument("--min-move", type=float, default=config.MIN_TRACK_MOVE,
                    help="跨线最小净位移，抑制框抖动假过车")
    ap.add_argument("--max-frames", type=int, default=0, help="0=处理整段视频")
    ap.add_argument("--save-frames", type=int, default=12, help="保存多少张可视化帧")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        raise SystemExit("视频不存在: " + args.video)
    if not os.path.exists(config.YOLO_ONNX):
        raise SystemExit("模型不存在: " + config.YOLO_ONNX)

    out = args.out
    frame_dir = os.path.join(out, "frames")
    report_dir = os.path.join(out, "reports")
    os.makedirs(frame_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit("无法打开视频: " + args.video)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limit = args.max_frames if args.max_frames > 0 else total
    limit = min(limit, total) if total else limit

    det = TiledYoloOnnxDetector(config.YOLO_ONNX, config.CLASSES,
                                conf=args.conf, iou=config.IOU_THRES,
                                mode=args.tile, tile_size=config.TILE_SIZE,
                                overlap=config.TILE_OVERLAP)
    trk = IoUTracker(iou_thresh=0.3, max_miss=30)
    cnt = LineCounter(line_y=args.line_y, enter_when=config.ENTER_WHEN,
                      classes=config.CLASSES, min_move=args.min_move)
    rep = Reporter(os.path.join(report_dir, "hourly.csv"),
                   os.path.join(report_dir, "daily.csv"), config.CLASSES)
    # 报表时间轴：把短视频映射到当天 12:00 起，便于看「每小时」分桶
    t0 = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

    print("视频  : %s" % args.video)
    print("规格  : %dx%d  fps=%.1f  总帧=%d  处理帧=%d" % (w, h, fps, total, limit))
    print("配置  : tile=%s conf=%.2f line_y=%.2f min_move=%.3f\n"
          % (args.tile, args.conf, args.line_y, args.min_move))

    cls_counts, cls_confs = Counter(), defaultdict(list)
    confs, areas, per_frame = [], [], []
    area_classes = {"small(<30%)": Counter(), "mid(30-60%)": Counter(), "huge(>60%)": Counter()}
    area_confs = defaultdict(list)
    stride = max(1, limit // max(1, args.save_frames))
    saved, frame_i, line_px = 0, 0, int(h * args.line_y)

    while frame_i < limit:
        ok, frame = cap.read()
        if not ok:
            break
        frame_i += 1
        boxes = det.detect(frame)
        tracks = trk.update(boxes)
        cnt.update(tracks, h)
        if frame_i % max(1, int(fps)) == 0:
            inc = cnt.pop_increment()
            rep.record(t0 + datetime.timedelta(seconds=frame_i / fps),
                       inc["enter"], inc["exit"])

        per_frame.append(len(boxes))
        for x1, y1, x2, y2, cid, score in boxes:
            name = config.CLASSES[int(cid)] if 0 <= int(cid) < len(config.CLASSES) else str(cid)
            cls_counts[name] += 1
            cls_confs[name].append(float(score))
            confs.append(float(score))
            area = max(0, x2 - x1) * max(0, y2 - y1) / max(1, w * h)
            areas.append(area)
            key = "small(<30%)" if area < 0.30 else ("mid(30-60%)" if area <= 0.60 else "huge(>60%)")
            area_classes[key][name] += 1
            area_confs[key].append(float(score))

        if saved < args.save_frames and frame_i % stride == 0:
            snap = cnt.snapshot()
            n_in, n_out = sum(snap["enter"].values()), sum(snap["exit"].values())
            vis = frame.copy()
            cv2.line(vis, (0, line_px), (w, line_px), (0, 0, 255), 3)
            cv2.putText(vis, "LINE_Y=%.2f" % args.line_y, (12, line_px - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            for x1, y1, x2, y2, cid, score in boxes:
                name = config.CLASSES[int(cid)] if 0 <= int(cid) < len(config.CLASSES) else str(cid)
                cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 165, 255), 2)
                cv2.putText(vis, "%s %.2f" % (name, score),
                            (int(x1), max(16, int(y1) - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)
            cv2.putText(vis, "frame %d  boxes %d  IN %d  OUT %d" % (frame_i, len(boxes), n_in, n_out),
                        (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (60, 220, 60), 2)
            cv2.imwrite(os.path.join(frame_dir, "f%06d.jpg" % frame_i), vis)
            saved += 1
        if frame_i % 30 == 0:
            print("  已处理 %d/%d 帧，累计 %d 个框" % (frame_i, limit, len(confs)))
    cap.release()
    det.close()

    n = max(1, frame_i)
    nb = len(confs)
    avg_conf = sum(confs) / nb if nb else 0.0
    zero = sum(1 for c in per_frame if c == 0)
    snap = cnt.snapshot()
    n_in, n_out = sum(snap["enter"].values()), sum(snap["exit"].values())

    lines = [
        "真实视频端到端评估（检测 + 进出计数）",
        "=" * 52,
        "视频        : %s" % args.video,
        "规格        : %dx%d, fps=%.1f, 总帧=%d, 处理帧=%d, 时长≈%.1fs"
        % (w, h, fps, total, frame_i, frame_i / fps),
        "配置        : tile=%s, conf=%.2f, LINE_Y=%.2f, MIN_TRACK_MOVE=%.3f"
        % (args.tile, args.conf, args.line_y, args.min_move),
        "",
        "--- 检测 ---",
        "检出框总数        : %d" % nb,
        "每帧平均框数      : %.2f" % (nb / n),
        "零检出帧          : %d / %d (%.1f%%)" % (zero, n, zero / n * 100),
        "平均置信度        : %.3f" % avg_conf,
        "平均框面积占画面  : %.2f%%" % (sum(areas) / nb * 100 if nb else 0),
    ]
    for c in config.CLASSES:
        cs = cls_confs[c]
        lines.append("%-8s %-4s : %5d 框, 平均置信度 %.3f"
                     % (c, config.CLASS_CN.get(c, ""), cls_counts[c],
                        sum(cs) / len(cs) if cs else 0.0))
    lines += ["", "--- 进出计数（虚拟线 LINE_Y=%.2f）---" % args.line_y,
              "累计进 / 出 : %d / %d" % (n_in, n_out)]
    for c in config.CLASSES:
        lines.append("  %-6s %-4s 进 %3d  出 %3d"
                     % (c, config.CLASS_CN.get(c, ""), snap["enter"][c], snap["exit"][c]))
    lines += ["", "--- 按框面积分档 ---"]
    for key in ("small(<30%)", "mid(30-60%)", "huge(>60%)"):
        cs = area_confs.get(key, [])
        lines.append("%-14s %5d 框, 平均置信度 %.3f, 类别 %s"
                     % (key, sum(area_classes[key].values()),
                        sum(cs) / len(cs) if cs else 0.0, dict(area_classes[key])))
    lines += ["", "报表: reports/hourly.csv, reports/daily.csv, reports/report.xlsx",
              "可视化: frames/ 与 overview.jpg"]
    text = "\n".join(lines)
    with open(os.path.join(out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")

    summary = {
        "video": args.video, "width": w, "height": h, "fps": fps,
        "total_frames": total, "processed_frames": frame_i,
        "duration_sec": round(frame_i / fps, 1),
        "tile": args.tile, "conf": args.conf, "line_y": args.line_y,
        "min_move": args.min_move,
        "detection": {
            "total_boxes": nb, "avg_boxes_per_frame": round(nb / n, 3),
            "zero_detect_frames": zero, "zero_rate_pct": round(zero / n * 100, 2),
            "avg_conf": round(avg_conf, 4),
            "avg_box_area_pct": round(sum(areas) / nb * 100, 2) if nb else 0.0,
            "per_class": {c: cls_counts[c] for c in config.CLASSES},
            "area_buckets": {
                k: {"boxes": sum(area_classes[k].values()),
                    "avg_conf": round(sum(area_confs[k]) / len(area_confs[k]), 4)
                    if area_confs[k] else 0.0,
                    "per_class": dict(area_classes[k])}
                for k in ("small(<30%)", "mid(30-60%)", "huge(>60%)")},
        },
        "counting": {"enter": snap["enter"], "exit": snap["exit"],
                     "total_enter": n_in, "total_exit": n_out},
        "saved_frames": saved,
    }
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 4 帧缩略拼图，可直接放进课程报告
    files = sorted(f for f in os.listdir(frame_dir) if f.endswith(".jpg"))
    if files:
        picks = [files[int(i * (len(files) - 1) / 3)] for i in range(4)] if len(files) >= 4 else files
        thumbs = [cv2.resize(cv2.imread(os.path.join(frame_dir, f)), (270, 480)) for f in picks]
        while len(thumbs) < 4:
            thumbs.append(thumbs[-1].copy())
        overview = np.vstack([np.hstack(thumbs[:2]), np.hstack(thumbs[2:])])
        cv2.imwrite(os.path.join(out, "overview.jpg"), overview,
                    [cv2.IMWRITE_JPEG_QUALITY, 85])

    rep.flush()
    rep.export_excel()
    print("\n" + text)
    print("\n结果已写入: %s" % out)


if __name__ == "__main__":
    main()
