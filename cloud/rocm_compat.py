#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AMD ROCm 兼容补丁：绕开 torchvision GPU NMS 缺失。

问题
----
AMD OneClick Base 镜像自带的 torchvision 只编译了 CPU 版
`torchvision::nms` 算子；Ultralytics 在验证阶段
(ultralytics/utils/nms.py: `torchvision.ops.nms(boxes, scores, iou_thres)`)
会传入 CUDA 张量，随即抛：

    NotImplementedError: Could not run 'torchvision::nms' with arguments
    from the 'CUDA' backend.

方案
----
把 NMS 的两个输入临时搬到 CPU（CPU kernel 可用），算完把保留框索引
搬回原设备。每张图的候选框通常只有几百个，开销可忽略，且结果与
原生 NMS 完全一致。

用法（必须在 import ultralytics 之前）
------------------------------------
    sys.path.insert(0, "/workspace/tools")
    from rocm_compat import apply
    apply()
"""
import torch
import torchvision

_ORIGINAL_NMS = torchvision.ops.nms
_APPLIED = False


def _nms_rocm(boxes, scores, iou_threshold):
    device = boxes.device
    if device.type == "cpu":
        return _ORIGINAL_NMS(boxes, scores, iou_threshold)
    keep = _ORIGINAL_NMS(boxes.detach().cpu(), scores.detach().cpu(), iou_threshold)
    return keep.to(device)


def apply():
    """替换 torchvision.ops.nms 为 ROCm 兼容版本（幂等）。"""
    global _APPLIED
    if _APPLIED:
        return
    torchvision.ops.nms = _nms_rocm
    _APPLIED = True
    print("[rocm_compat] torchvision.ops.nms -> CPU offload 已启用", flush=True)


def self_check():
    """快速自检：GPU 张量调用 patched nms 不应报错。"""
    apply()
    if not torch.cuda.is_available():
        print("GPU 不可用，跳过自检")
        return
    boxes = torch.tensor([[0, 0, 10, 10], [1, 1, 9, 9], [30, 30, 40, 40]],
                         dtype=torch.float, device="cuda")
    scores = torch.tensor([0.9, 0.8, 0.7], device="cuda")
    keep = torchvision.ops.nms(boxes, scores, 0.5)
    print("NMS_OK device=cpu-safe keep=", keep.tolist(), flush=True)


if __name__ == "__main__":
    self_check()
