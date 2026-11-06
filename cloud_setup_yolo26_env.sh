#!/bin/bash
# 云端一键重建「校园车辆统计 / YOLO26 课程」训练环境
# 适用: AMD Radeon Cloud 实例 (ROCm 7.2.1 系统底座, GPU = Radeon PRO W7900 / gfx1100)
# 用法: 把本文件上传到云端 /workspace 后执行:  bash /workspace/cloud_setup_yolo26_env.sh
# 背景: 重建实例会清空系统盘, 但课程 venv 放在持久盘 /workspace 下可保留;
#       若 /workspace 也清空, 本脚本仍能从头拉起整套环境。

set -e
UV=/opt/venv/bin/uv
VENV=/workspace/.venv-yolo26
REPO=/workspace/yolo26-rocm-day1-labs

echo "[1/3] 创建 venv (若不存在)..."
if [ ! -f "$VENV/bin/python" ]; then
  $UV venv $VENV --python 3.12
fi

echo "[2/3] 安装 torch 2.12.0+rocm7.2 / torchvision 0.27.0+rocm7.2 + 课程依赖..."
# 关键: 系统 ROCm 是 7.2.1, 必须用 PyTorch 官方 rocm7.2 源, 不要用 AMD 7.14.1 源(会 hipErrorInvalidImage)
#       --index-strategy unsafe-best-match 让 torch 从 PyTorch 源解析而非 PyPI(否则找不到 +rocm 版)
if ! $VENV/bin/python -c "import torch" 2>/dev/null; then
  $UV pip install --python $VENV \
    --index-url "https://download.pytorch.org/whl/rocm7.2/" \
    --extra-index-url "https://pypi.org/simple/" \
    --index-strategy unsafe-best-match \
    torch==2.12.0+rocm7.2 torchvision==0.27.0+rocm7.2 \
    -r $REPO/requirements-course.txt
else
  echo "torch 已存在, 跳过安装"
fi

echo "[3/3] 注册 Jupyter 内核 (显示名与教程一致)..."
$VENV/bin/python -m ipykernel install --user --name yolo26-rocm7141 --display-name "YOLO26 - AMD ROCm 7.14.1"

echo "DONE. 在 Jupyter 右上角选内核: YOLO26 - AMD ROCm 7.14.1"
echo "验证: $VENV/bin/python -c \"import torch,torchvision; from torchvision.ops import nms; print('nms ok')\""
