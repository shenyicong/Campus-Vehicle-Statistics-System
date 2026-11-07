#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端训练入口（AMD ROCm）：打 NMS 兼容补丁 -> 训练 4 类车 -> 导出 ONNX。

用法:
  PYTHONPATH=/workspace/tools python /workspace/tools/train_car_yolo.py \
      --data /workspace/datasets/car_det/data.yaml --epochs 100

说明:
  - 必须先 apply() 再 import ultralytics，否则验证阶段会命中 ROCm 上
    缺失的 torchvision GPU NMS。
  - 预训练权重下载失败时自动回退到内置 yaml 随机初始化，保证训练能跑完。
"""
import argparse
import os
import sys

sys.path.insert(0, "/workspace/tools")
from rocm_compat import apply

apply()

import torch
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/workspace/datasets/car_det/data.yaml")
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--project", default="/workspace/runs/car_yolo")
    ap.add_argument("--name", default="exp")
    ap.add_argument("--no-amp", action="store_true", help="ROCm 半精度报错时加这个")
    args = ap.parse_args()

    print("torch:", torch.__version__, "| cuda:", torch.cuda.is_available(), flush=True)
    assert torch.cuda.is_available(), "GPU 不可用"

    try:
        model = YOLO(args.model)
        print("使用权重:", args.model, flush=True)
    except Exception as e:
        cfg = args.model.replace(".pt", ".yaml")
        print("权重不可用(%s)，回退随机初始化: %s" % (e, cfg), flush=True)
        model = YOLO(cfg)

    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=0,
        workers=2,
        project=args.project,
        name=args.name,
        exist_ok=True,
        amp=not args.no_amp,
        verbose=False,
    )

    best = os.path.join(args.project, args.name, "weights", "best.pt")
    if not os.path.isfile(best):
        raise SystemExit("未找到 best.pt: %s" % best)
    print("训练完成，权重:", best, flush=True)

    YOLO(best).export(format="onnx", imgsz=args.imgsz, opset=12, simplify=False)
    print("ONNX:", best[:-3] + ".onnx", flush=True)
    print("TRAIN_OK", flush=True)


if __name__ == "__main__":
    main()
