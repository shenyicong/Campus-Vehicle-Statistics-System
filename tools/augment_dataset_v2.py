#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 v2 训练数据集：修复 v1「单车特写」分布缺陷。

v1 问题（实测）：298 张全为 640x640；288 张只有 1 个框；框中位尺寸
w=0.763 / h=0.671（目标约占画面一半）；面积<1% 的小框仅 1 个。
结果：多车同框被合并成巨框、远景小车漏检、非车物体被硬分到四类。

v2 做法（纯本地合成，不需要新标注）：
  multi_* : 以原图为背景（保留原有标签），叠加 1~3 辆缩小后的车 -> 多车同框
  small_* : 用 inpaint 抹掉原车得到纯背景，再贴 2~5 个小目标 -> 远景小目标
  干扰物  : 从失败案例里裁出玩具车/广告牌，贴入但【不标注】 -> 硬负样本
  原始 298 张全部保留，防止丢失清晰的车型特征

类别 id 严格保持 0=轿车 / 1=SUV / 2=货车 / 3=客车，不改动 config.CLASSES。
输出为平铺目录，可直接交给 tools/split_dataset.py 切分。

用法:
  python tools/augment_dataset_v2.py --src D:/car_export --dst D:/YOLO/car_export_v2
"""
import argparse
import glob
import os
import random
import shutil

import cv2
import numpy as np
from PIL import Image

SIZE = 640
SKIP_TXT = {"classes.txt", "sources.txt", "readme.txt", "notes.txt"}


def load_pairs(src):
    pairs = []
    for jpg in sorted(glob.glob(os.path.join(src, "*.jpg")) +
                      glob.glob(os.path.join(src, "*.png"))):
        txt = os.path.splitext(jpg)[0] + ".txt"
        if not os.path.isfile(txt):
            continue
        labels = []
        for line in open(txt, encoding="utf-8").read().splitlines():
            a = line.split()
            if len(a) == 5:
                labels.append([int(a[0])] + [float(x) for x in a[1:]])
        if not labels:
            continue
        img = cv2.imread(jpg)
        if img is None:
            continue
        img = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
        pairs.append((img, labels))
    return pairs


def box_to_xyxy(b):
    cx, cy, w, h = b[1:]
    return [int((cx - w / 2) * SIZE), int((cy - h / 2) * SIZE),
            int((cx + w / 2) * SIZE), int((cy + h / 2) * SIZE)]


def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(ua, 1)


def crop_patch(img, b, pad=0.04):
    x1, y1, x2, y2 = box_to_xyxy(b)
    pw, ph = (x2 - x1), (y2 - y1)
    x1 = max(0, int(x1 - pw * pad)); y1 = max(0, int(y1 - ph * pad))
    x2 = min(SIZE, int(x2 + pw * pad)); y2 = min(SIZE, int(y2 + ph * pad))
    if x2 - x1 < 20 or y2 - y1 < 20:
        return None
    return img[y1:y2, x1:x2].copy()


def blend(bg, patch, x, y, w, h, feather=22):
    """带边缘羽化的贴图，避免出现可被模型学到的硬矩形接缝。
    边缘 alpha 必须从 0 起，否则会留下可见的矩形轮廓。"""
    p = cv2.resize(patch, (w, h), interpolation=cv2.INTER_AREA)
    ph, pw = p.shape[:2]
    alpha = np.ones((ph, pw, 1), dtype=np.float32)
    r = np.linspace(0.0, 1.0, min(feather, ph // 2, pw // 2)).astype(np.float32)
    k = len(r)
    alpha[:k, :] *= r[:, None, None]
    alpha[-k:, :] *= r[::-1, None, None]
    alpha[:, :k] *= r[None, :, None]
    alpha[:, -k:] *= r[None, ::-1, None]
    roi = bg[y:y + ph, x:x + pw].astype(np.float32)
    bg[y:y + ph, x:x + pw] = (p.astype(np.float32) * alpha + roi * (1 - alpha)).astype(np.uint8)


def make_bg(img, labels):
    """从原图裁一块不含任何标注框的区域放大成纯背景，避免昂贵的 inpaint。"""
    boxes = [box_to_xyxy(b) for b in labels]
    # 标注框通常居中且很大，优先取四边条带 / 四角，命中无车区域概率最高
    k = int(SIZE * 0.26)
    cands = [
        [0, 0, SIZE, k], [0, SIZE - k, SIZE, SIZE],
        [0, 0, k, SIZE], [SIZE - k, 0, SIZE, SIZE],
        [0, 0, k, k], [SIZE - k, 0, SIZE, k],
        [0, SIZE - k, k, SIZE], [SIZE - k, SIZE - k, SIZE, SIZE],
    ]
    random.shuffle(cands)
    for cand in cands:
        if sum(iou(cand, b) for b in boxes) == 0:
            crop = img[cand[1]:cand[3], cand[0]:cand[2]].copy()
            bg = cv2.resize(crop, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
            return cv2.GaussianBlur(bg, (5, 5), 0)
    # 找不到干净背景就返回 None，绝不把残留未标注车辆的模糊图混进训练集
    return None


def place(bg, patch, boxes, target_frac):
    """随机放一个 patch，返回新标签行；放不下返回 None。"""
    ph, pw = patch.shape[:2]
    w = int(SIZE * target_frac)
    h = max(20, int(w * ph / pw))
    if h >= SIZE - 4:
        return None
    for _ in range(24):
        x = random.randint(2, SIZE - w - 2)
        y = random.randint(2, SIZE - h - 2)
        cand = [x, y, x + w, y + h]
        if all(iou(cand, b) < 0.04 for b in boxes):
            blend(bg, patch, x, y, w, h)
            boxes.append(cand)
            return [0, (x + w / 2) / SIZE, (y + h / 2) / SIZE, w / SIZE, h / SIZE]
    return None


def write_pair(dst, stem, img, labels):
    cv2.imwrite(os.path.join(dst, stem + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    with open(os.path.join(dst, stem + ".txt"), "w", encoding="utf-8") as f:
        for b in labels:
            f.write("%d %.6f %.6f %.6f %.6f\n" % (int(b[0]), b[1], b[2], b[3], b[4]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=r"D:\car_export")
    ap.add_argument("--dst", default=r"D:\YOLO\car_export_v2")
    ap.add_argument("--multi", type=int, default=260)
    ap.add_argument("--small", type=int, default=140)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--distractor",
                    default=r"C:\Users\Q2730\.workbuddy\clipboard-images\clipboard-2026-11-09T08-39-13-462Z-9a4d915d.jpg",
                    help="失败案例原图，从中裁出玩具车作为不标注的硬负样本")
    args = ap.parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    pairs = load_pairs(args.src)
    if not pairs:
        raise SystemExit("源数据集为空: " + args.src)
    print("载入原图 %d 张" % len(pairs))

    patches = []
    for img, labels in pairs:
        for b in labels:
            p = crop_patch(img, b)
            if p is not None:
                patches.append((p, int(b[0])))
    print("可复用车辆 patch %d 个" % len(patches))

    distractors = []
    if os.path.isfile(args.distractor):
        d = cv2.imread(args.distractor)
        if d is not None:
            H, W = d.shape[:2]
            # 玩具车位于画面中下部（约 x 0.39~0.60, y 0.62~1.00）
            toy = d[int(H * 0.62):H, int(W * 0.38):int(W * 0.60)]
            if toy.size:
                distractors.append(toy)
            # 顶部中文贴字，作为文字干扰
            txt = d[0:int(H * 0.14), int(W * 0.02):int(W * 0.35)]
            if txt.size:
                distractors.append(txt)
    print("干扰物 patch %d 个（贴入但不标注）" % len(distractors))

    dst = args.dst
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)

    kept = 0
    for i, (img, labels) in enumerate(pairs):
        write_pair(dst, "orig_%04d" % i, img, labels)
        kept += 1

    made_multi = made_small = 0
    n_distract = 0
    for i in range(args.multi):
        img, labels = random.choice(pairs)
        bg = img.copy()
        out = [list(b) for b in labels]
        boxes = [box_to_xyxy(b) for b in labels]
        for _ in range(random.randint(1, 3)):
            patch, cls = random.choice(patches)
            row = place(bg, patch, boxes, random.uniform(0.14, 0.42))
            if row:
                row[0] = cls
                out.append(row)
        if distractors and random.random() < 0.35:
            patch = random.choice(distractors)
            if place(bg, patch, boxes, random.uniform(0.10, 0.24)):
                n_distract += 1  # place 只贴图，不写入 out，故无需 pop
        write_pair(dst, "multi_%04d" % i, bg, out)
        made_multi += 1

    bg_pool = [b for b in (make_bg(img, lbs) for img, lbs in pairs) if b is not None]
    print("可用无车背景 %d 张" % len(bg_pool))
    for i in range(args.small):
        if not bg_pool:
            break
        bg = random.choice(bg_pool).copy()
        boxes = []
        out = []
        for _ in range(random.randint(2, 5)):
            patch, cls = random.choice(patches)
            row = place(bg, patch, boxes, random.uniform(0.06, 0.20))
            if row:
                row[0] = cls
                out.append(row)
        if not out:
            continue
        if distractors and random.random() < 0.30:
            patch = random.choice(distractors)
            if place(bg, patch, boxes, random.uniform(0.08, 0.18)):
                n_distract += 1
        write_pair(dst, "small_%04d" % i, bg, out)
        made_small += 1

    # 复制说明文件
    for name in ("classes.txt",):
        s = os.path.join(args.src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst, name))

    total = kept + made_multi + made_small
    print("\n=== v2 生成完成 ===")
    print("原始 %d + 多车 %d + 小目标 %d = %d 张" % (kept, made_multi, made_small, total))
    print("含干扰物（不标注）的合成图 %d 张" % n_distract)
    cnt = {}
    per = []
    for t in glob.glob(os.path.join(dst, "*.txt")):
        if os.path.basename(t).lower() in SKIP_TXT:
            continue
        lines = [l for l in open(t, encoding="utf-8").read().splitlines() if l.strip()]
        per.append(len(lines))
        for l in lines:
            c = int(l.split()[0]); cnt[c] = cnt.get(c, 0) + 1
    print("总框数 %d  每图均值 %.2f  最多 %d" % (sum(per), sum(per) / len(per), max(per)))
    print("类别分布:", dict(sorted(cnt.items())))
    small = 0
    for t in glob.glob(os.path.join(dst, "*.txt")):
        if os.path.basename(t).lower() in SKIP_TXT:
            continue
        for l in open(t, encoding="utf-8"):
            a = l.split()
            if len(a) == 5 and float(a[3]) * float(a[4]) < 0.01:
                small += 1
    print("面积<1%% 的小框: %d (%.1f%%)" % (small, small / max(sum(per), 1) * 100))
    print("输出目录:", dst)


if __name__ == "__main__":
    main()
