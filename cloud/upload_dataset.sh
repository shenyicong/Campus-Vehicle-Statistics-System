#!/usr/bin/env bash
# =============================================================
# 本机(Windows Git Bash)一键上传数据集到云端实例
# 用法： bash cloud/upload_dataset.sh
# 前置：云端实例已开机、SSH 别名 radeon-cloud 可连
# 传三个东西：数据集 tar 包、切分脚本、云端训练脚本
# =============================================================
set -euo pipefail

REMOTE=${REMOTE:-radeon-cloud}
SRC=${SRC:-D:/car_export}
REPO=${REPO:-D:/YOLO/campus_vehicle_system}
TARBALL=D:/car_dataset.tar.gz
RDIR=/workspace/data/car

echo "========== [0/4] 检查云端连通 =========="
ssh -o BatchMode=yes -o ConnectTimeout=10 "$REMOTE" "echo CONNECT_OK; hostname" || {
  echo "!! 连不上云端：先确认实例已开机、IP/端口是否变化"; exit 1;
}

echo "========== [1/4] 打包数据集 (排除模板 yaml / 备份目录) =========="
tar -czf "$TARBALL" -C "$SRC" --exclude='data.yaml' --exclude='_original_backup' .
echo "包大小: $(du -h "$TARBALL" | cut -f1)"

echo "========== [2/4] 创建远端目录并上传 =========="
ssh "$REMOTE" "mkdir -p $RDIR /workspace/tools /workspace/datasets /workspace/runs"
scp "$TARBALL" "$REMOTE:/workspace/data/car_dataset.tar.gz"
scp "$REPO/tools/split_dataset.py" "$REMOTE:/workspace/tools/split_dataset.py"
scp "$REPO/cloud/train_car_yolo.sh" "$REMOTE:/workspace/tools/train_car_yolo.sh"
scp "$REPO/cloud_setup_yolo26_env.sh" "$REMOTE:/workspace/tools/setup_yolo26_env.sh"

echo "========== [3/4] 远端解压 =========="
ssh "$REMOTE" "tar -xzf /workspace/data/car_dataset.tar.gz -C $RDIR && rm -f /workspace/data/car_dataset.tar.gz && sed -i 's/\r\$//' /workspace/tools/*.sh /workspace/tools/*.py && chmod +x /workspace/tools/train_car_yolo.sh"

echo "========== [4/4] 核对 =========="
ssh "$REMOTE" "cd $RDIR && echo jpg=\$(ls *.jpg 2>/dev/null | wc -l) txt=\$(ls *.txt 2>/dev/null | wc -l) && echo '--- classes.txt ---' && cat classes.txt && echo '--- 环境 ---' && /workspace/.venv-yolo26/bin/python -c 'import torch;print(torch.__version__, torch.cuda.is_available())' 2>&1 | tail -1"

echo "========== 完成 =========="
echo "训练： ssh $REMOTE 'bash /workspace/tools/train_car_yolo.sh'"
echo "建议后台跑： ssh $REMOTE 'nohup bash /workspace/tools/train_car_yolo.sh > /workspace/train.log 2>&1 &'"
