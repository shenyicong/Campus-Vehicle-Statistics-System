"""真实视频检测评估：检验模型在真实道路画面上的泛化能力。

重要：本脚本只评估「能不能检出车」，不做进出计数。
进出判定依赖「摄像机静止 + config.LINE_Y 虚拟线」；行车记录仪、
随车手机拍摄这类镜头在移动，虚拟线会失效，请勿用 main.py 统计进出。
需要进出统计时，请改用固定机位俯拍校门口的视频。

用法:
  python tools/eval_real_video.py --video data/real_road.mp4
  python tools/eval_real_video.py --video data/real_road.mp4 --out data/real_eval --every 10 --save-frames 12
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import cv2

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import config
from detector import TiledYoloOnnxDetector


def main():
    ap = argparse.ArgumentParser(description="真实视频检测评估（不做进出计数）")
    ap.add_argument("--video", required=True, help="本地视频路径 mp4/avi/mov")
    ap.add_argument("--out", default=os.path.join(config.DATA_DIR, "real_eval"),
                    help="结果输出目录")
    ap.add_argument("--every", type=int, default=10, help="每 N 帧抽 1 帧检测")
    ap.add_argument("--max-samples", type=int, default=120, help="最多检测多少帧")
    ap.add_argument("--save-frames", type=int, default=12, help="保存多少张带框可视化帧")
    ap.add_argument("--conf", type=float, default=config.CONF_THRES)
    ap.add_argument("--iou", type=float, default=config.IOU_THRES)
    ap.add_argument("--tile", default="auto", choices=["auto", "1", "0"],
                    help="分块推理: auto=竖屏自动 / 1=强制 / 0=关闭(整图)")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        raise SystemExit("视频不存在: " + args.video)
    if not os.path.exists(config.YOLO_ONNX):
        raise SystemExit("模型不存在: " + config.YOLO_ONNX)

    os.makedirs(args.out, exist_ok=True)
    frame_dir = os.path.join(args.out, "frames")
    os.makedirs(frame_dir, exist_ok=True)

    det = TiledYoloOnnxDetector(config.YOLO_ONNX, config.CLASSES,
                                conf=args.conf, iou=args.iou, mode=args.tile)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit("无法打开视频: " + args.video)

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total / fps if fps else 0
    print("视频  : %s" % args.video)
    print("规格  : %dx%d  fps=%.1f  总帧=%d  时长≈%.1fs" % (w, h, fps, total, duration))
    print("抽样  : 每 %d 帧取 1 帧，最多 %d 帧" % (args.every, args.max_samples))
    print("提示  : 移动机位只评估检测效果，不做进出计数\n")

    cls_counts = Counter()
    cls_confs = {c: [] for c in config.CLASSES}
    confs, per_frame, areas = [], [], []
    # 按框面积分档：区分「远景小车」与「近距特写」两种完全不同的尺度域。
    # 一段视频如果 huge 占比很高，说明多为局部特写，结论不能直接外推到俯拍监控。
    area_classes = {"small(<30%)": Counter(), "mid(30-60%)": Counter(), "huge(>60%)": Counter()}
    area_confs = defaultdict(list)
    saved, idx, samples = 0, 0, 0
    stride = max(1, args.max_samples // max(1, args.save_frames))

    while samples < args.max_samples:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % args.every == 0:
            boxes = det.detect(frame)
            per_frame.append(len(boxes))
            for b in boxes:
                x1, y1, x2, y2, cid, score = b
                cid = int(cid)
                name = config.CLASSES[cid] if 0 <= cid < len(config.CLASSES) else str(cid)
                cls_counts[name] += 1
                cls_confs.setdefault(name, []).append(float(score))
                confs.append(float(score))
                area = max(0, x2 - x1) * max(0, y2 - y1) / max(1, w * h)
                areas.append(area)
                key = "small(<30%)" if area < 0.30 else ("mid(30-60%)" if area <= 0.60 else "huge(>60%)")
                area_classes[key][name] += 1
                area_confs[key].append(float(score))

            if saved < args.save_frames and samples % stride == 0:
                vis = frame.copy()
                for b in boxes:
                    x1, y1, x2, y2, cid, score = [int(v) for v in b[:4]] + [int(b[4]), b[5]]
                    name = config.CLASSES[cid] if 0 <= cid < len(config.CLASSES) else str(cid)
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 165, 255), 2)
                    cv2.putText(vis, "%s %.2f" % (name, score), (x1, max(16, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)
                cv2.putText(vis, "frame %d  boxes %d" % (idx, len(boxes)), (12, 26),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 220, 60), 2)
                cv2.imwrite(os.path.join(frame_dir, "f%06d.jpg" % idx), vis)
                saved += 1
            samples += 1
            if samples % 20 == 0:
                print("  已检测 %d 帧，累计 %d 个框" % (samples, len(confs)))
        idx += 1
    cap.release()

    n = max(1, samples)
    total_boxes = len(confs)
    avg_conf = sum(confs) / total_boxes if total_boxes else 0.0
    med_conf = sorted(confs)[total_boxes // 2] if total_boxes else 0.0
    avg_area = sum(areas) / total_boxes * 100 if total_boxes else 0.0
    zero_frames = sum(1 for c in per_frame if c == 0)

    lines = [
        "真实视频检测评估报告",
        "=" * 46,
        "视频      : %s" % args.video,
        "规格      : %dx%d, fps=%.1f, 总帧=%d, 时长≈%.1fs" % (w, h, fps, total, duration),
        "抽样      : %d 帧（每 %d 帧取 1 帧）" % (samples, args.every),
        "模型      : %s" % os.path.basename(config.YOLO_ONNX),
        "置信度阈值: %.2f   NMS IoU: %.2f" % (args.conf, args.iou),
        "分块推理  : %s" % args.tile,
        "",
        "--- 总体 ---",
        "检出框总数      : %d" % total_boxes,
        "每帧平均框数    : %.2f" % (total_boxes / n),
        "零检出帧        : %d / %d (%.1f%%)" % (zero_frames, n, zero_frames / n * 100),
        "平均 / 中位置信度: %.3f / %.3f" % (avg_conf, med_conf),
        "平均框面积占画面: %.1f%%" % avg_area,
        "",
        "--- 分类别 ---",
    ]
    for c in config.CLASSES:
        cs = cls_confs[c]
        lines.append("%-8s %-4s : %4d 框, 平均置信度 %.3f" %
                     (c, config.CLASS_CN.get(c, ""), cls_counts[c],
                      sum(cs) / len(cs) if cs else 0.0))
    lines += ["", "--- 按框面积分档（判断是远景还是特写域）---"]
    for key in ("small(<30%)", "mid(30-60%)", "huge(>60%)"):
        cs = area_confs.get(key, [])
        lines.append("%-14s %3d 框, 平均置信度 %.3f, 类别 %s" %
                     (key, sum(area_classes[key].values()),
                      sum(cs) / len(cs) if cs else 0.0,
                      dict(area_classes[key])))
    lines += [
        "  注: huge 占比高 = 多为车头/车厢局部特写，与俯拍监控的尺度域不同，结论勿直接外推。",
        "",
        "--- 说明 ---",
        "本脚本仅评估检测泛化能力，不做进出计数。",
        "进出统计需要固定机位 + 虚拟线，请运行 main.py。",
        "带框可视化帧见 frames/ 目录。",
    ]
    text = "\n".join(lines)
    with open(os.path.join(args.out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")

    summary = {
        "video": args.video, "width": w, "height": h, "fps": fps,
        "total_frames": total, "duration_sec": round(duration, 1),
        "sampled_frames": samples, "sample_every": args.every,
        "conf": args.conf, "iou": args.iou, "tile": args.tile,
        "total_boxes": total_boxes, "avg_boxes_per_frame": round(total_boxes / n, 3),
        "zero_detect_frames": zero_frames, "avg_conf": round(avg_conf, 4),
        "median_conf": round(med_conf, 4), "avg_box_area_pct": round(avg_area, 2),
        "per_class": {c: cls_counts[c] for c in config.CLASSES},
        "area_buckets": {
            k: {"boxes": sum(area_classes[k].values()),
                "avg_conf": round(sum(area_confs[k]) / len(area_confs[k]), 4)
                if area_confs[k] else 0.0,
                "per_class": dict(area_classes[k])}
            for k in ("small(<30%)", "mid(30-60%)", "huge(>60%)")
        },
        "saved_frames": saved,
    }
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + text)
    print("\n结果已写入: %s" % args.out)


if __name__ == "__main__":
    main()
