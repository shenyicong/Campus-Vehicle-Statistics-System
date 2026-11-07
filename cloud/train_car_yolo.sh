#!/usr/bin/env bash
# =============================================================
# 云端 AMD ROCm 实例一键脚本：环境自检 -> 切分 -> 训练 -> 导出 ONNX
# 运行位置：云端 /workspace/tools/train_car_yolo.sh
# 前置：本机已运行 cloud/upload_dataset.sh
# 用法： bash /workspace/tools/train_car_yolo.sh
#        EPOCHS=50 BATCH=8 MODEL=yolo11n.pt bash /workspace/tools/train_car_yolo.sh
#        AMP=0 bash /workspace/tools/train_car_yolo.sh   # 半精度报错时
#
# 重要：复用镜像自带的 /opt/venv（torch 2.9.1+hip、GPU 可用），
#       不再下载 5.8GiB 的 torch rocm7.2 wheel；
#       torchvision 缺 GPU NMS，由 rocm_compat.py 打补丁绕开。
# =============================================================
set -euo pipefail

ROOT=/workspace
RAW=$ROOT/data/car
DS=$ROOT/datasets/car_det
PY=${PY:-/opt/venv/bin/python}
PROJECT=$ROOT/runs/car_yolo

MODEL=${MODEL:-yolo11n.pt}
EPOCHS=${EPOCHS:-100}
IMGSZ=${IMGSZ:-640}
BATCH=${BATCH:-16}
CLASSES=${CLASSES:-"轿车,SUV,货车,客车"}

echo "========== [0/3] 环境自检 =========="
if [ ! -x "$PY" ]; then
  echo "!! $PY 不存在，请先在本机运行 cloud/upload_dataset.sh 并检查镜像"
  exit 1
fi
"$PY" - <<'PY'
import torch, ultralytics
print("torch      :", torch.__version__)
print("ultralytics:", ultralytics.__version__)
print("GPU        :", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "不可用")
assert torch.cuda.is_available(), "GPU 不可用"
PY
PYTHONPATH=$ROOT/tools "$PY" "$ROOT/tools/rocm_compat.py"   # NMS 补丁自检

echo "========== [1/3] 切分数据集 (8:2) =========="
mkdir -p "$(dirname "$DS")"
"$PY" "$ROOT/tools/split_dataset.py" \
    --src "$RAW" --dst "$DS" --ratio 0.8 --seed 42 --classes "$CLASSES"
echo "--- data.yaml ---"
cat "$DS/data.yaml"

echo "========== [2/3] 训练 + 导出 ONNX =========="
ARGS=(--data "$DS/data.yaml" --model "$MODEL" --epochs "$EPOCHS"
      --imgsz "$IMGSZ" --batch "$BATCH" --project "$PROJECT" --name exp)
if [ "${AMP:-1}" = "0" ]; then ARGS+=(--no-amp); fi
PYTHONPATH=$ROOT/tools "$PY" "$ROOT/tools/train_car_yolo.py" "${ARGS[@]}"

echo "========== 完成 =========="
echo "ONNX: $PROJECT/exp/weights/best.onnx"
echo "下一步：下载回本地 D:/YOLO/campus_vehicle_system/models/car_yolo.onnx"
echo "       并在 detector.py 补全 YoloOnnxDetector.detect 的预处理 + NMS 后处理"
