#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 X-AnyLabeling「YOLO HBB」导出遗漏的旋转框。

背景：HBB 导出器只处理 shape_type=rectangle，rotation 类型的框会被静默跳过，
      导致对应 .txt 为空 —— 训练时该图会被当成"无目标背景图"(错误负样本)。
做法：直接读源 .json，对任意 shape 取点集的外接水平矩形(AABB)，按
      classes.txt 的行顺序映射 class_id，重新生成标准 YOLO 格式 .txt。
      不修改任何源标注 json，只重写导出目录里的 .txt。

用法:
  python fix_rotation_labels.py --json-dir D:/car --out-dir D:/car_export
"""
import argparse
import json
import os

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", default=r"D:\car", help="源标注 json 目录")
    ap.add_argument("--out-dir", default=r"D:\car_export", help="YOLO 导出目录(将被重写的 .txt 所在处)")
    args = ap.parse_args()

    cpath = os.path.join(args.out_dir, "classes.txt")
    if not os.path.exists(cpath):
        cpath = os.path.join(args.json_dir, "classes.txt")
    with open(cpath, encoding="utf-8-sig") as f:
        classes = [ln.strip() for ln in f if ln.strip()]
    label2id = {c: i for i, c in enumerate(classes)}
    print("classes.txt:", classes)

    jsons = sorted(f for f in os.listdir(args.json_dir) if f.lower().endswith(".json"))
    total_boxes = 0
    fixed_files = []
    unknown = set()
    skipped = []

    for jf in jsons:
        stem = os.path.splitext(jf)[0]
        with open(os.path.join(args.json_dir, jf), encoding="utf-8-sig") as f:
            d = json.load(f)
        W, H = d.get("imageWidth"), d.get("imageHeight")
        if not W or not H:
            skipped.append(jf + "(缺图像尺寸)")
            continue

        lines, had_rotation = [], False
        for s in d.get("shapes", []):
            lab = s.get("label")
            if lab not in label2id:
                unknown.add(str(lab))
                continue
            pts = s.get("points") or []
            if len(pts) < 2:
                continue
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            x1, x2 = max(0.0, min(xs)), min(float(W), max(xs))
            y1, y2 = max(0.0, min(ys)), min(float(H), max(ys))
            if x2 <= x1 or y2 <= y1:
                continue
            cx, cy = (x1 + x2) / 2.0 / W, (y1 + y2) / 2.0 / H
            w, h = (x2 - x1) / W, (y2 - y1) / H
            lines.append("%d %.6f %.6f %.6f %.6f" % (label2id[lab], cx, cy, w, h))
            if s.get("shape_type") == "rotation":
                had_rotation = True
        total_boxes += len(lines)

        out = os.path.join(args.out_dir, stem + ".txt")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        if had_rotation:
            fixed_files.append((stem, len(lines)))

    print("\n重写 .txt 文件数:", len(jsons))
    print("总框数:", total_boxes)
    print("含旋转框并被修复的文件 %d 个:" % len(fixed_files))
    for stem, n in fixed_files:
        print("   %-14s -> %d 个框" % (stem, n))
    if unknown:
        print("警告: classes.txt 里没有的标签:", unknown)
    if skipped:
        print("跳过:", skipped)
    print("\n完成。接着跑 validate_yolo_export.py 复核。")


if __name__ == "__main__":
    main()
