#!/usr/bin/env bash
# =============================================================
# 云端 AMD ROCm 实例一键脚本：环境自检 -> 切分 -> 训练 -> 导出 ONNX
# 运行位置：云端 /workspace/tools/train_car_yolo.sh
# 前置：本机已把 D:/car_export 上传到 /workspace/data/car
# 用法： bash /workspace/tools/train_car_yolo.sh
#        EPOCHS=50 MODEL=yolov8n.pt bash /workspace/tools/train_car_yolo.sh
# =============================================================
set -euo pipefail

ROOT=/workspace
RAW=$ROOT/data/car                    # 上传的平铺数据集
DS=$ROOT/datasets/car_det             # 切分输出
PY=$ROOT/.venv-yolo26/bin/python
YOLO=$ROOT/.venv-yolo26/bin/yolo
PROJECT=$ROOT/runs/car_yolo

MODEL=${MODEL:-yolo26n.pt}            # 权重不存在时 Ultralytics 会自动下载
EPOCHS=${EPOCHS:-100}
IMGSZ=${IMGSZ:-640}
BATCH=${BATCH:-16}
CLASSES=${CLASSES:-"轿车,SUV,货车,客车"}

echo "========== [0/4] 环境自检 =========="
if [ ! -x "$PY" ]; then
  echo "!! venv 缺失，执行恢复脚本 ..."
  if [ -f "$ROOT/tools/setup_yolo26_env.sh" ]; then
    bash "$ROOT/tools/setup_yolo26_env.sh"
  else
    echo "!! 找不到 /workspace/tools/setup_yolo26_env.sh，请先在本机运行 cloud/upload_dataset.sh"
    exit 1
  fi
fi
"$PY" - <<'PY'
import torch, ultralytics
print("torch      :", torch.__version__)
print("ultralytics:", ultralytics.__version__)
print("GPU        :", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "不可用")
assert torch.cuda.is_available(), "GPU 不可用：检查 ROCm 版本与 torch wheel 是否匹配"
PY

echo "========== [1/4] 切分数据集 (8:2) =========="
mkdir -p "$(dirname "$DS")"
"$PY" "$ROOT/tools/split_dataset.py" \
    --src "$RAW" --dst "$DS" --ratio 0.8 --seed 42 --classes "$CLASSES"

echo "--- data.yaml ---"
cat "$DS/data.yaml"

echo "========== [2/4] 训练 =========="
# ROCm 上若 AMP 报 hip 相关错误，追加 AMP=0 到命令行环境
EXTRA=""
if [ "${AMP:-1}" = "0" ]; then EXTRA="amp=False"; fi
"$YOLO" detect train \
    model="$MODEL" data="$DS/data.yaml" \
    epochs="$EPOCHS" imgsz="$IMGSZ" batch="$BATCH" device=0 workers=2 \
    project="$PROJECT" name=exp exist_ok=True $EXTRA

echo "========== [3/4] 导出 ONNX =========="
BEST=$(find "$PROJECT/exp/weights" -name best.pt -print -quit)
if [ -z "$BEST" ]; then echo "!! 未找到 best.pt，训练可能失败"; exit 1; fi
echo "权重: $BEST"
"$YOLO" export model="$BEST" format=onnx imgsz="$IMGSZ" opset=12 simplify=False

echo "========== 完成 =========="
echo "ONNX: ${BEST%.pt}.onnx"
echo "下一步：下载回本地 D:/YOLO/campus_vehicle_system/models/car_yolo.onnx"
echo "       并在 detector.py 补全 YoloOnnxDetector.detect 的预处理 + NMS 后处理"
