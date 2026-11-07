#!/bin/bash
# =============================================================
# 云端一键重建 YOLO 训练环境（AMD Radeon Cloud / ROCm）
# 用法： bash /workspace/cloud_setup_yolo26_env.sh
# 覆盖（新镜像版本不同时）：
#   ROCM_TAG=rocm7.14.1 TORCH_INDEX_URL=https://repo.amd.com/rocm/whl-multi-arch/ \
#     bash /workspace/cloud_setup_yolo26_env.sh
#
# 背景：这个平台的实例到点会【自动销毁且删除临时工作区】，
#       所以新建实例后 /workspace 通常是空的，需要重新拉起整套环境。
#       关键是 torch wheel 的 ROCm 版本必须与系统底座一致，
#       否则 GPU 算子加载失败（hipErrorInvalidImage）。
# =============================================================
set -e

UV=/opt/venv/bin/uv
VENV=/workspace/.venv-yolo26
REPO=/workspace/yolo26-rocm-day1-labs

echo "[0/4] 探测系统 ROCm 与 GPU"
SYS_ROCM=$(cat /opt/rocm/.info/version 2>/dev/null || echo unknown)
echo "  系统 ROCm : $SYS_ROCM"
rocminfo 2>/dev/null | grep -m1 -i "gfx" || true

case "$SYS_ROCM" in
  7.2*)  DEFAULT_TAG=rocm7.2 ;;
  7.14*) DEFAULT_TAG=rocm7.14.1 ;;
  7.1*)  DEFAULT_TAG=rocm7.1 ;;
  6.4*)  DEFAULT_TAG=rocm6.4 ;;
  *)     DEFAULT_TAG=rocm7.2 ;;
esac
ROCM_TAG=${ROCM_TAG:-$DEFAULT_TAG}
if [ -n "${TORCH_INDEX_URL:-}" ]; then
  INDEX_URL=$TORCH_INDEX_URL
elif [ "${ROCM_TAG#rocm7.14}" != "$ROCM_TAG" ]; then
  INDEX_URL="https://repo.amd.com/rocm/whl-multi-arch/"
else
  INDEX_URL="https://download.pytorch.org/whl/$ROCM_TAG/"
fi
TORCH_SPEC=${TORCH_SPEC:-"torch==2.12.0+$ROCM_TAG"}
TV_SPEC=${TV_SPEC:-"torchvision==0.27.0+$ROCM_TAG"}
echo "  选用 wheel : $TORCH_SPEC"
echo "  索引       : $INDEX_URL"
echo "  ⚠ torch 的 ROCm 版本若与系统 $SYS_ROCM 不匹配，GPU 会 hipErrorInvalidImage"

echo "[1/4] 创建 venv (若不存在)"
if [ ! -f "$VENV/bin/python" ]; then
  $UV venv "$VENV" --python 3.12
fi

echo "[2/4] 安装 torch / torchvision / ultralytics / ipykernel / onnx"
# --index-strategy unsafe-best-match：绕开 uv 默认「首个索引优先」把 torch 锁到 PyPI 的行为
if ! "$VENV/bin/python" -c "import torch, ultralytics" 2>/dev/null; then
  EXTRA=""
  [ -f "$REPO/requirements-course.txt" ] && EXTRA="-r $REPO/requirements-course.txt"
  $UV pip install --python "$VENV" \
    --index-url "$INDEX_URL" \
    --extra-index-url "https://pypi.org/simple/" \
    --index-strategy unsafe-best-match \
    "$TORCH_SPEC" "$TV_SPEC" \
    ultralytics ipykernel onnx $EXTRA
else
  echo "  torch 与 ultralytics 已存在，跳过安装"
fi

echo "[3/4] 注册 Jupyter 内核"
"$VENV/bin/python" -m ipykernel install --user \
  --name yolo26-rocm7141 --display-name "YOLO26 - AMD ROCm 7.14.1"

echo "[4/4] GPU 自检 (nms)"
set +e
"$VENV/bin/python" - <<'PY'
import torch
from torchvision.ops import nms
assert torch.cuda.is_available(), "torch.cuda 不可用"
b = torch.tensor([[0, 0, 10, 10], [1, 1, 9, 9]], dtype=torch.float, device="cuda")
s = torch.tensor([0.9, 0.8], device="cuda")
print("  torch   :", torch.__version__)
print("  GPU     :", torch.cuda.get_device_name(0))
print("  nms     :", nms(b, s, 0.5).tolist())
print("  NMS_OK")
PY
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  echo "!! GPU 自检失败：大概率是 torch wheel 与系统 ROCm 版本不匹配。"
  echo "   用 ROCM_TAG=<系统实际版本> 或 TORCH_INDEX_URL=... 重跑本脚本。"
  exit 1
fi

echo "DONE. 环境可用，接下来：上传数据集 -> 切分 -> 训练 -> 导出 ONNX"
