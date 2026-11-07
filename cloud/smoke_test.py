#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端训练冒烟测试：验证 ROCm + torch + ultralytics 整条训练链路可用。

从内置 yaml 构建模型（不下载预训练权重），跑 1 个极小 epoch，
能暴露 AMP、NMS、GPU kernel、数据加载等兼容性问题。

用法:
  python /workspace/tools/smoke_test.py            # 默认 amp=True
  python /workspace/tools/smoke_test.py --no-amp  # ROCm 上半精度报错时改用这个
"""
import sys

sys.path.insert(0, "/workspace/tools")
from rocm_compat import apply

apply()  # 必须在 import ultralytics 之前：绕开 ROCm 上缺失的 torchvision GPU NMS
import torch
from ultralytics import YOLO

amp = "--no-amp" not in sys.argv
print("torch:", torch.__version__, "| cuda:", torch.cuda.is_available(), "| amp:", amp, flush=True)
assert torch.cuda.is_available(), "GPU 不可用"

model = YOLO("yolo11n.yaml")
model.train(
    data="/workspace/datasets/car_det/data.yaml",
    epochs=1,
    imgsz=320,
    batch=2,
    device=0,
    workers=1,
    project="/workspace/runs",
    name="smoke",
    exist_ok=True,
    amp=amp,
    verbose=False,
)
print("SMOKE_OK", flush=True)
