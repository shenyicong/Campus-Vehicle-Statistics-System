#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定回归测试：每次重训后跑一遍，用同一批真实图对比模型是否真的变好。

为什么不用 val mAP：v1 的 train/val 都来自同一批「单车特写」图，mAP 0.799
是在简单分布上测出来的，无法反映多车同框 / 远景小车 / 非车干扰。
本脚本用真实场景图做固定测试集，这类图【绝不能放进训练集】。

用法:
  python tools/regression_test.py --out D:/YOLO/ab_test/round1
  python tools/regression_test.py --images a.jpg b.jpg --out D:/YOLO/ab_test/round2
  set CAMPUS_ONNX=D:\\path\\to\\new.onnx   # 可指定新导出的权重
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

import config
from detector import YoloOnnxDetector, TiledYoloOnnxDetector

DEFAULT_IMAGES = [
    r"C:\Users\Q2730\.workbuddy\clipboard-images\clipboard-2026-11-09T08-39-13-462Z-9a4d915d.jpg",
    r"C:\Users\Q2730\.workbuddy\clipboard-images\clipboard-2026-11-09T08-39-13-464Z-0c1cc990.jpg",
]
EXPECT = {
    "B_三车拼图": "3 个独立框（1 SUV + 2 轿车），玩具车不应被框",
    "A_成排微卡": ">=6 个框，且大多为货车",
}


def run_one(img, cls, tag, kw, out_dir, stem):
    d = cls(config.YOLO_ONNX, config.CLASSES, iou=config.IOU_THRES, **kw)
    dets = d.detect(img)
    d.close()
    vis = img.copy()
    rows = []
    for x1, y1, x2, y2, c, s in dets:
        cname = config.CLASS_CN.get(config.CLASSES[int(c)], str(c))
        cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
        cv2.putText(vis, "%s %.2f" % (cname, float(s)),
                    (int(x1), max(18, int(y1) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
        rows.append({"cls": cname, "conf": round(float(s), 3),
                     "box": [int(x1), int(y1), int(x2), int(y2)]})
    cv2.imwrite(os.path.join(out_dir, "%s_%s.jpg" % (stem, tag)), vis)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=DEFAULT_IMAGES)
    ap.add_argument("--out", default=r"D:\YOLO\ab_test\regression")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    variants = [
        ("whole", YoloOnnxDetector, dict(conf=args.conf)),
        ("grid", TiledYoloOnnxDetector,
         dict(conf=args.conf, mode="grid", tile_size=config.TILE_SIZE,
              overlap=config.TILE_OVERLAP)),
    ]
    summary = {"onnx": config.YOLO_ONNX, "conf": args.conf, "cases": {}}
    for i, path in enumerate(args.images):
        if not os.path.isfile(path):
            print("跳过（文件不存在）:", path)
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        stem = "case%02d" % (i + 1)
        print("\n=== %s  %s  %dx%d ===" % (stem, os.path.basename(path), img.shape[1], img.shape[0]))
        entry = {"path": path, "size": [img.shape[1], img.shape[0]]}
        for tag, cls, kw in variants:
            rows = run_one(img, cls, tag, kw, args.out, stem)
            entry[tag] = rows
            counts = {}
            for r in rows:
                counts[r["cls"]] = counts.get(r["cls"], 0) + 1
            print("  %-8s 框数 %2d  %s" % (tag, len(rows), counts))
        summary["cases"][stem] = entry

    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("\n结果目录:", args.out)
    print("目标参考:", json.dumps(EXPECT, ensure_ascii=False))


if __name__ == "__main__":
    main()
