#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YOLO 导出结果校验（训练前必跑，零第三方依赖）

用法:
  python validate_yolo_export.py --data D:/car_export
  python validate_yolo_export.py --data D:/car_export --json-dir D:/car --gen-yaml D:/car_export/data.yaml

说明:
  --data      导出目录（X-AnyLabeling 的 export root，不能是图片目录本身）
  --json-dir  原始标注 json 所在目录（默认 D:\\car），交叉核对 class_id 顺序时用它

自动兼容四种导出布局:
  1) 图片与 txt 同目录:   xxx.jpg + xxx.txt
  2) images/ + labels/ 分离
  3) 只有 labels/（图片留在源目录）
  4) 只有 images/（标签在根目录）
"""
import argparse
import json
import os
import sys
from collections import Counter

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def resolve_layout(data):
    """返回 (图片目录, 标签目录)，自动探测 X-AnyLabeling 的各种导出布局"""
    img_sub = os.path.join(data, "images")
    lbl_sub = os.path.join(data, "labels")
    has_images = os.path.isdir(img_sub)
    has_labels = os.path.isdir(lbl_sub)
    if has_images and has_labels:      # images/ + labels/ 标准分离布局
        return img_sub, lbl_sub
    if has_labels:                     # 只导出了标签，图片仍在根目录
        return data, lbl_sub
    if has_images:                     # 只复制了图片，标签在根目录
        return img_sub, data
    return data, data                  # 图片与 txt 全混在根目录


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"D:\car_export", help="YOLO 导出目录（export root）")
    ap.add_argument("--json-dir", default=r"D:\car", help="原始标注 json 目录，用于交叉核对 class_id 顺序")
    ap.add_argument("--gen-yaml", default="", help="可选：按 classes.txt 顺序生成 data.yaml 的路径")
    args = ap.parse_args()

    img_dir, lbl_dir = resolve_layout(args.data)
    print("图片目录:", img_dir)
    print("标签目录:", lbl_dir)

    imgs = {os.path.splitext(f)[0]: f for f in os.listdir(img_dir)
            if f.lower().endswith(IMG_EXT)}
    # classes.txt / sources.txt 不是标注标签，必须排除，否则会误报"孤儿标签"和非法行
    skip = {"sources.txt", "classes.txt"}
    txts = {os.path.splitext(f)[0]: f for f in os.listdir(lbl_dir)
            if f.lower().endswith(".txt") and f.lower() not in skip}

    # 读取类别文件（YOLO 导出通常会生成，决定 class_id 顺序）
    classes = []
    for cand in (os.path.join(args.data, "classes.txt"),
                 os.path.join(lbl_dir, "classes.txt")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8-sig") as f:
                classes = [ln.strip() for ln in f if ln.strip()]
            print("类别文件:", cand, "->", classes)
            break
    if not classes:
        print("[警告] 未找到 classes.txt，无法核对类别顺序（请保留导出时生成的该文件）")

    missing = sorted(set(imgs) - set(txts))
    orphan = sorted(set(txts) - set(imgs))
    print("\n图片 %d 张 / 标签 %d 个" % (len(imgs), len(txts)))
    print("缺标签的图片: %d %s" % (len(missing), missing[:10] if missing else ""))
    print("无对应图片的标签: %d %s" % (len(orphan), orphan[:10] if orphan else ""))

    per_cls, bad, empty = Counter(), [], []
    for stem, fn in txts.items():
        with open(os.path.join(lbl_dir, fn), encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        if not lines:
            empty.append(fn)
        for i, ln in enumerate(lines, 1):
            parts = ln.split()
            if len(parts) != 5:
                bad.append("%s:%d 字段数=%d" % (fn, i, len(parts)))
                continue
            try:
                cid = int(parts[0])
                vals = [float(x) for x in parts[1:]]
            except ValueError:
                bad.append("%s:%d 非数值" % (fn, i))
                continue
            if classes and not (0 <= cid < len(classes)):
                bad.append("%s:%d class_id=%d 越界" % (fn, i, cid))
            if any(not (0.0 <= v <= 1.0) for v in vals):
                bad.append("%s:%d 坐标未归一化/越界 %s" % (fn, i, vals))
            per_cls[cid] += 1

    print("\n=== 各类别框数 ===")
    for cid in sorted(per_cls):
        name = classes[cid] if 0 <= cid < len(classes) else "<id %d>" % cid
        print("  %d: %-10s %d 个框" % (cid, name, per_cls[cid]))
    print("总框数:", sum(per_cls.values()))

    # 检查导出软件有没有擅自改写 classes.txt 的顺序（必须与项目 config.CLASSES 对齐）
    EXPECTED = ["轿车", "SUV", "货车", "客车"]  # = sedan / suv / truck / bus
    order_bad = []
    if not classes:
        order_bad.append("未找到 classes.txt")
    elif classes != EXPECTED:
        order_bad.append("classes.txt 顺序=%s，期望=%s；软件可能覆盖了它" % (classes, EXPECTED))
    print("\n=== 类别顺序检查 ===")
    if order_bad:
        print("  ❌ " + "; ".join(order_bad))
    else:
        print("  ✅ classes.txt = %s，与 config.CLASSES(sedan/suv/truck/bus) 对齐" % classes)

    # 交叉核对：源目录 json 里的中文标签 -> classes.txt 行号，必须与 txt 的 class_id 一致
    # 这一步能抓出"导出时类别顺序被软件改乱"的隐蔽错误，否则训练出的模型会认错车
    map_bad, checked = [], 0
    if classes:
        label2id = {c: i for i, c in enumerate(classes)}
        for stem, fn in txts.items():
            jp = None
            for cand in (os.path.join(args.json_dir, stem + ".json"),
                         os.path.join(args.data, stem + ".json"),
                         os.path.join(img_dir, stem + ".json")):
                if os.path.exists(cand):
                    jp = cand
                    break
            if jp is None:
                continue
            try:
                with open(jp, encoding="utf-8-sig") as f:
                    shapes = json.load(f).get("shapes", [])
            except (ValueError, OSError):
                continue
            checked += 1
            want = sorted(label2id.get(s.get("label"), -1) for s in shapes)
            got = []
            with open(os.path.join(lbl_dir, fn), encoding="utf-8-sig") as f:
                for ln in f:
                    parts = ln.split()
                    if parts:
                        try:
                            got.append(int(parts[0]))
                        except ValueError:
                            pass
            if sorted(got) != want:
                map_bad.append("%s(json=%s, txt=%s)" % (fn, want, sorted(got)))
    print("\n=== 标签↔class_id 交叉核对（已比对 %d 张源 json）===" % checked)
    if not classes:
        print("  跳过：无 classes.txt")
    elif checked == 0:
        print("  警告：未找到可配对的源 json（用 --json-dir 指定标注目录，默认 D:\\car）")
    elif map_bad:
        print("  ❌ 不一致 %d 个（类别顺序可能乱了）: %s" % (len(map_bad), map_bad[:8]))
    else:
        print("  ✅ 全部一致，class_id 顺序与 classes.txt 对齐")

    print("\n=== 异常 ===")
    print("空标签 %d %s" % (len(empty), empty[:10] if empty else ""))
    print("非法行 %d %s" % (len(bad), bad[:10] if bad else ""))

    ok = not (missing or orphan or bad or map_bad or order_bad)
    print("\n结论:", "OK 校验通过，可上传训练" if ok else "存在问题，请按上面修正")

    if args.gen_yaml and classes:
        with open(args.gen_yaml, "w", encoding="utf-8") as f:
            f.write("# 由 validate_yolo_export.py 生成；names 顺序与导出 classes.txt 一致\n")
            f.write("path: %s\n" % args.data.replace("\\", "/"))
            f.write("train: images/train\n")
            f.write("val: images/val\n")
            f.write("nc: %d\n" % len(classes))
            f.write("names: [" + ", ".join("'%s'" % c for c in classes) + "]\n")
        print("已生成:", args.gen_yaml)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
