#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创新点 3 A/B 验核：车型混淆矩阵（零外部依赖，PIL 仅用于出图）。

同一批样本同时跑两组，输出并排混淆矩阵，直接量化"轨迹级众数投票纠正错检"
的收益：
  A 组 = 车型取当前帧检测结果（原 tracker 行为）
  B 组 = 车型取整条轨迹生命周期的众数（cls_vote=True）

模式一 --demo（默认，无 --gt 时）：
  合成已知真值的多帧轨迹，按 --noise 概率注入单帧车型误判；由 --seed 固定
  结果，完全离线、不依赖模型/视频/标注，可现场演示投票为何有效。
  A 组取"计数触发那一帧"的车型，正是系统跨线判定时刻的实际数据来源。

模式二 --gt <json>：
  在真实图片上评估。JSON 示例见 docs/examples/cls_gt_example.json：
    {"classes": ["sedan","suv","truck","bus"],
     "samples": [{"image": "路径", "labels": [1, 0, 0]}]}
  B 组把每张图的检测结果重复 --vote-frames 帧并注入 --noise 类别噪声，
  模拟同一辆车在视频中的连续观测；A 组直接用原始检测结果。
  其余变量（conf / tile / 图片）两组完全相同。

输出 <out>/confusion.txt, confusion.csv, confusion.png, summary.json
"""
import argparse
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from tracker import IoUTracker


def _det_for_cls(c):
    """固定 bbox 的单帧检测，保证相邻帧 IoU=1，轨迹稳定匹配。"""
    return [0, 0, 10, 10, c, 0.9]


def vote_predict(frame_classes):
    """把一串逐帧车型序列喂给 B 组跟踪器，返回轨迹众数车型。"""
    t = IoUTracker(cls_vote=True)
    out = []
    for c in frame_classes:
        out = t.update([_det_for_cls(c)])
    return out[0]["cls"] if out else frame_classes[-1]


def build_demo(ncls, per_class, frames, noise, seed):
    """构造已知真值的合成轨迹：每类 per_class 条，每条 frames 帧。"""
    rng = random.Random(seed)
    samples = []
    for c in range(ncls):
        for _ in range(per_class):
            seq = []
            for f in range(frames):
                if f > 0 and rng.random() < noise:
                    others = [x for x in range(ncls) if x != c]
                    seq.append(rng.choice(others))
                else:
                    seq.append(c)
            samples.append({"true": c, "frames": seq})
    return samples


def match_counts(gt_labels, pred_labels):
    """按类别计数贪心配对：优先同类，剩余异类配对计入混淆矩阵非对角。

    返回 (pairs, 多余预测数FP, 未匹配真值数FN)。
    """
    rem = list(pred_labels)
    pairs = []
    for g in gt_labels:
        if not rem:
            break
        p = int(g) if int(g) in rem else rem[0]
        rem.remove(p)
        pairs.append((int(g), int(p)))
    return pairs, len(rem), max(0, len(gt_labels) - len(pairs))


def run_gt(args, names):
    """真实图片模式：检测一次，A 组用原始类别，B 组用重复帧投票类别。"""
    import cv2
    from detector import YoloOnnxDetector, TiledYoloOnnxDetector

    with open(args.gt, encoding="utf-8") as f:
        gt = json.load(f)
    samples = gt.get("samples", [])
    ncls = len(names)
    factory = YoloOnnxDetector if args.tile == "0" else TiledYoloOnnxDetector
    kw = dict(conf=args.conf, iou=config.IOU_THRES)
    if factory is TiledYoloOnnxDetector:
        kw.update(mode=args.tile, tile_size=config.TILE_SIZE,
                  overlap=config.TILE_OVERLAP)
    det = factory(config.YOLO_ONNX, names, **kw)
    rng = random.Random(args.seed)

    pairs_a, pairs_b = [], []
    fp = fn = 0
    for s in samples:
        img = cv2.imread(s["image"])
        if img is None:
            print("跳过（读不到图片）:", s["image"])
            continue
        boxes = det.detect(img)

        # A/B 必须经历完全相同的噪声帧序列：A 组取跨线那一帧的车型，
        # B 组取整条伪轨迹的众数。若 A 组直接用原始无噪声检测就不公平，
        # 会因为没承受误判而虚高，导致结论不可信。
        trk_a = IoUTracker(cls_vote=False)
        trk_b = IoUTracker(cls_vote=True)
        pred_a, pred_b = [], []
        for f in range(args.vote_frames):
            frame_dets = []
            for b in boxes:
                bb = list(b)
                if f > 0 and rng.random() < args.noise:
                    others = [x for x in range(ncls) if x != int(b[4])]
                    bb[4] = rng.choice(others)
                frame_dets.append(bb)
            out_a = trk_a.update(frame_dets)
            out_b = trk_b.update(frame_dets)
            if f == args.vote_frames - 1:
                pred_a = [int(x["cls"]) for x in out_a]
                pred_b = [int(x["cls"]) for x in out_b]

        pa, fp_a, fn_a = match_counts(s.get("labels", []), pred_a)
        pb, fp_b, fn_b = match_counts(s.get("labels", []), pred_b)
        pairs_a += pa
        pairs_b += pb
        fp += fp_a + fp_b
        fn += fn_a + fn_b
    det.close()
    return pairs_a, pairs_b, {"fp": fp, "fn": fn, "images": len(samples)}


def make_matrix(pairs, ncls):
    m = [[0] * ncls for _ in range(ncls)]
    for true, pred in pairs:
        if 0 <= true < ncls and 0 <= pred < ncls:
            m[true][pred] += 1
    return m


def metrics(m, names):
    n = len(names)
    correct = sum(m[i][i] for i in range(n))
    total = sum(sum(row) for row in m)
    per = []
    for i in range(n):
        tp = m[i][i]
        fp = sum(m[r][i] for r in range(n) if r != i)
        fn = sum(m[i][c] for c in range(n) if c != i)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per.append({"class": names[i], "support": tp + fn,
                    "precision": round(p, 4), "recall": round(r, 4),
                    "f1": round(f1, 4)})
    return {"matrix": m, "per_class": per, "n": total,
            "accuracy": round(correct / total, 4) if total else 0.0}


def format_table(m, names, title):
    head = "%-10s" % "" + "".join("%10s" % n[:9] for n in names)
    lines = [title, "行=真值  列=预测", head]
    for i, n in enumerate(names):
        lines.append("%-10s" % n[:9] + "".join("%10d" % v for v in m[i]))
    return "\n".join(lines)


def format_metrics(res, title):
    lines = [title, "%-10s %8s %10s %10s %8s" %
             ("车型", "样本数", "精确率", "召回率", "F1")]
    for r in res["per_class"]:
        lines.append("%-10s %8d %10.3f %10.3f %8.3f" %
                     (r["class"][:9], r["support"], r["precision"],
                      r["recall"], r["f1"]))
    lines.append("总体准确率: %.2f%%  (%d 个预测样本)" %
                 (res["accuracy"] * 100, res["n"]))
    return "\n".join(lines)


def draw_png(m_a, m_b, names, path):
    """并排画两张混淆矩阵热力图；无 PIL 时静默跳过。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    cell, left, top = 56, 104, 52
    n = len(names)
    w = left + n * cell + 16
    h = top + n * cell + 28
    canvas = Image.new("RGB", (2 * w + 16, h), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    for idx, (m, title) in enumerate(((m_a, "A: per-frame cls"),
                                      (m_b, "B: trajectory vote"))):
        ox = idx * (w + 16)
        mx = max(max(row) for row in m) or 1
        d.text((ox + 8, 8), title, fill=(20, 20, 20))
        for j, name in enumerate(names):
            d.text((ox + left + j * cell + 8, top - 18), name[:8], fill=(20, 20, 20))
        for i, name in enumerate(names):
            d.text((ox + 6, top + i * cell + 18), name[:9], fill=(20, 20, 20))
            for j in range(n):
                v = m[i][j]
                k = v / mx
                if i == j:
                    col = (int(232 - 130 * k), int(246 - 110 * k), int(232 - 130 * k))
                else:
                    col = (int(250 - 60 * k), int(240 - 160 * k), int(240 - 160 * k))
                x, y = ox + left + j * cell, top + i * cell
                d.rectangle([x, y, x + cell - 1, y + cell - 1],
                            fill=col, outline=(190, 190, 190))
                d.text((x + cell // 2 - 6, y + cell // 2 - 6), str(v), fill=(0, 0, 0))
    canvas.save(path)
    return True


def main():
    ap = argparse.ArgumentParser(description="车型混淆矩阵 A/B：逐帧判定 vs 轨迹众数投票")
    ap.add_argument("--gt", default=None,
                    help="真值 JSON；不给则跑离线合成 demo")
    ap.add_argument("--out", default=os.path.join(config.DATA_DIR, "cls_ab"),
                    help="结果目录")
    ap.add_argument("--classes", default=None,
                    help="逗号分隔的车型名，默认取 config.CLASSES")
    ap.add_argument("--demo-per-class", type=int, default=40,
                    help="demo 模式每类生成的轨迹条数")
    ap.add_argument("--frames", type=int, default=12,
                    help="demo 模式每条轨迹的帧数")
    ap.add_argument("--noise", type=float, default=0.25,
                    help="单帧车型误判概率")
    ap.add_argument("--seed", type=int, default=42, help="随机种子，保证可复现")
    ap.add_argument("--vote-frames", type=int, default=8,
                    help="真实图片模式：每张图重复投票的帧数")
    ap.add_argument("--conf", type=float, default=config.CONF_THRES)
    ap.add_argument("--tile", default=config.TILE_MODE,
                    choices=["auto", "grid", "1", "0"])
    args = ap.parse_args()

    names = [x.strip() for x in args.classes.split(",")] if args.classes else list(config.CLASSES)
    ncls = len(names)
    os.makedirs(args.out, exist_ok=True)

    extra = {}
    if args.gt:
        pairs_a, pairs_b, extra = run_gt(args, names)
        mode = "gt"
    else:
        samples = build_demo(ncls, args.demo_per_class, args.frames,
                             args.noise, args.seed)
        pairs_a = [(s["true"], s["frames"][-1]) for s in samples]
        pairs_b = [(s["true"], vote_predict(s["frames"])) for s in samples]
        mode = "demo"
        extra = {"per_class": args.demo_per_class, "frames": args.frames,
                 "noise": args.noise, "seed": args.seed}

    m_a = make_matrix(pairs_a, ncls)
    m_b = make_matrix(pairs_b, ncls)
    res_a = metrics(m_a, names)
    res_b = metrics(m_b, names)

    text = "\n\n".join([
        "车型混淆矩阵 A/B（%s）" % mode,
        format_table(m_a, names, "A 组：逐帧车型判定"),
        format_table(m_b, names, "B 组：轨迹级众数投票"),
        format_metrics(res_a, "A 组指标"),
        format_metrics(res_b, "B 组指标"),
        "准确率提升: %+.2f 个百分点" %
        ((res_b["accuracy"] - res_a["accuracy"]) * 100),
    ])
    with open(os.path.join(args.out, "confusion.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")

    with open(os.path.join(args.out, "confusion.csv"), "w",
              newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["group", "true", "pred", "count"])
        for g, m in (("A", m_a), ("B", m_b)):
            for i in range(ncls):
                for j in range(ncls):
                    w.writerow([g, names[i], names[j], m[i][j]])
        w.writerow([])
        w.writerow(["group", "accuracy", "n"])
        w.writerow(["A", res_a["accuracy"], res_a["n"]])
        w.writerow(["B", res_b["accuracy"], res_b["n"]])

    png_ok = draw_png(m_a, m_b, names, os.path.join(args.out, "confusion.png"))

    summary = {"mode": mode, "classes": names, "extra": extra,
               "A": {k: v for k, v in res_a.items()},
               "B": {k: v for k, v in res_b.items()},
               "accuracy_gain": round(res_b["accuracy"] - res_a["accuracy"], 4),
               "png": png_ok}
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(text)
    if res_a["n"] < 30:
        print("\n提示: 预测样本仅 %d 个（<30），A/B 差异不具统计意义；"
              "请增加真值图片后再下结论。" % res_a["n"])
    print("\n结果目录:", args.out)
    if not png_ok:
        print("提示: 未安装 PIL，跳过 confusion.png（文本/CSV 已生成）")


if __name__ == "__main__":
    main()
