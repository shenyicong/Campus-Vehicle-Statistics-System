#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 X-AnyLabeling 导出的标注整理成 Ultralytics YOLO 标准数据集，并生成 data.yaml。

本机(Windows)与云端(Linux)都能跑，纯标准库、零第三方依赖。

兼容两种源布局:
  1) 平铺:   <src>/xxx.jpg + <src>/xxx.txt        (本项目 D:/car_export)
  2) 分离:   <src>/images/xxx.jpg + <src>/labels/xxx.txt

输出:
  <dst>/images/train, <dst>/images/val
  <dst>/labels/train, <dst>/labels/val
  <dst>/data.yaml

用法:
  python split_dataset.py --src D:/car_export --dst D:/datasets/car_det --ratio 0.8 --classes "轿车,SUV,货车,客车"

注意:
  --classes 顺序就是 class_id(0,1,2...), 必须与 classes.txt 逐行一致!
  在云端运行时, data.yaml 首行 path 会被写成本脚本收到的 --dst 绝对路径。
"""
import argparse
import glob
import os
import random
import shutil

# 这些是说明/类别文件，不是标注，必须排除
SKIP_TXT = {"classes.txt", "sources.txt", "readme.txt", "notes.txt"}


def find_pairs(img_dir, lbl_dir):
    """返回 [(stem, img_path), ...]，只保留 图+非空标签 都存在的配对。"""
    pairs = []
    if not os.path.isdir(lbl_dir):
        raise SystemExit("缺少标签目录: %s" % lbl_dir)
    for txt in sorted(glob.glob(os.path.join(lbl_dir, "*.txt"))):
        name = os.path.basename(txt)
        if name.lower() in SKIP_TXT:
            continue
        stem = os.path.splitext(name)[0]
        if os.path.getsize(txt) == 0:
            continue  # 空标签 = 错误负样本，跳过
        imgs = [p for p in glob.glob(os.path.join(img_dir, stem + ".*"))
                if p.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))]
        if imgs:
            pairs.append((stem, imgs[0]))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="源目录(平铺 或 含 images/ labels/)")
    ap.add_argument("--dst", required=True, help="输出数据集根目录")
    ap.add_argument("--ratio", type=float, default=0.8, help="训练集比例(默认0.8)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--classes", default=None, help="逗号分隔的类别名, 顺序=class_id")
    args = ap.parse_args()

    img_dir = os.path.join(args.src, "images") if os.path.isdir(os.path.join(args.src, "images")) else args.src
    lbl_dir = os.path.join(args.src, "labels") if os.path.isdir(os.path.join(args.src, "labels")) else args.src

    pairs = find_pairs(img_dir, lbl_dir)
    if not pairs:
        raise SystemExit("没有可用的 图+标签 配对, 请检查 images/ 与 labels/ 是否对应、标签是否非空")

    random.seed(args.seed)
    random.shuffle(pairs)
    n_train = max(1, int(len(pairs) * args.ratio))
    splits = {"train": pairs[:n_train], "val": pairs[n_train:]}

    for split, items in splits.items():
        os.makedirs(os.path.join(args.dst, "images", split), exist_ok=True)
        os.makedirs(os.path.join(args.dst, "labels", split), exist_ok=True)
        for stem, img_path in items:
            shutil.copy(img_path, os.path.join(args.dst, "images", split, os.path.basename(img_path)))
            shutil.copy(os.path.join(lbl_dir, stem + ".txt"),
                        os.path.join(args.dst, "labels", split, stem + ".txt"))

    print("切分完成: 共 %d 对 | 训练 %d | 验证 %d" % (len(pairs), len(splits["train"]), len(splits["val"])))
    print("输出目录: %s" % args.dst)

    names = [c.strip() for c in args.classes.split(",")] if args.classes else []
    yaml_path = os.path.join(args.dst, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write("path: %s\n" % os.path.abspath(args.dst))
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write("nc: %d\n" % len(names))
        if names:
            f.write("names:\n")
            for i, n in enumerate(names):
                f.write("  %d: %s\n" % (i, n))
        else:
            f.write("# 请按 classes.txt 的顺序补充 names\n")
    print("已生成 data.yaml: %s" % yaml_path)


if __name__ == "__main__":
    main()
