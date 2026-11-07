# 校园车辆智能统计系统 (Campus Vehicle Statistics System)

基于 YOLO 目标检测的校园校门车辆智能统计系统：自动统计校门监控视频中 **轿车 / SUV / 货车 / 客车** 四类车辆的进出数量，按小时、按日生成统计报表，并提供网页实时看板，为校门口拥堵治理与校园停车资源规划提供数据依据。

## 功能特性

- **四类车型检测**：轿车(sedan)、SUV(suv)、货车(truck)、客车(bus)
- **真实 YOLO 模型**：已接入自训练 YOLO11n ONNX，CPU 即可推理（letterbox 预处理 + 按类别 NMS 后处理）
- **视频溯源**：支持本地视频文件与 RTSP 实时流（一行配置切换）
- **轨迹跟踪**：轻量 IoU 跟踪器，跨帧关联同一车辆
- **进出判定**：基于虚拟检测线 + 穿越方向，判定进校 / 出校
- **统计分析**：按小时 / 按日聚合，输出 CSV 与 Excel
- **实时看板**：Flask + Chart.js 网页仪表盘，定时刷新
- **可复现训练**：AMD Radeon Cloud / ROCm 一键脚本（上传 → 切分 → 训练 → 导出 ONNX）

## 系统架构

```
视频源 → 检测器 → 跟踪器(IoU) → 进出判定 → 计数器 → 报表(CSV/Excel) → 网页看板
```

## 目录结构

```
campus_vehicle_system/
├── config.py                  # 全局配置（路径/类别/虚拟线/视频源/端口）
├── video_input.py             # 视频输入：本地文件 或 RTSP 实时流
├── detector.py                # Mock 检测器 + YOLO-ONNX（预处理/解码/NMS 已实现）
├── tracker.py                 # 轻量 IoU 跟踪器
├── counter.py                 # 虚拟线进出判定与计数
├── reporter.py                # 每小时 / 每日 CSV 与 Excel 报表
├── main.py                    # 端到端串联入口
├── make_test_video.py         # 用车型图片合成模拟校门监控测试视频
├── web_dashboard.py           # Flask + Chart.js 实时看板（端口 5000）
├── cloud/
│   ├── upload_dataset.sh      # 本机：打包上传数据集与云端脚本
│   ├── train_car_yolo.sh      # 云端：自检 → 切分 → 训练 → 导出 ONNX
│   ├── train_car_yolo.py      # 训练入口（NMS 补丁 + 训练 + 导出）
│   ├── rocm_compat.py         # ROCm 的 torchvision GPU NMS 兼容补丁
│   └── smoke_test.py          # 1 epoch 冒烟测试
├── tools/
│   ├── split_dataset.py       # 8:2 切分 + 生成 data.yaml
│   ├── validate_yolo_export.py# 导出结果校验（配对/class_id/坐标）
│   └── fix_rotation_labels.py # 修复 YOLO HBB 导出跳过旋转框导致空标签
├── cloud_setup_yolo26_env.sh  # 兜底：从零重建 ROCm 训练环境
├── models/.gitkeep            # 放 car_yolo.onnx（模型文件不入库）
├── data/
│   ├── .gitkeep
│   ├── test_monitor.mp4       # 测试视频（运行生成，不入库）
│   └── reports/               # 报表输出（运行生成，不入库）
├── requirements.txt
├── .gitignore
└── LICENSE
```

## 快速开始

### 1. 准备环境

```bash
python -m venv .venv
pip install -r requirements.txt
# 关键依赖：opencv-python / numpy / onnxruntime / flask / openpyxl
```

### 2. 放入模型

把训练好的 ONNX 放到 `models/car_yolo.onnx`（路径由 `config.YOLO_ONNX` 指定）。

### 3. 运行统计（默认真实模型）

```bash
python main.py --max_frames 600
```

运行后会在 `data/reports/` 生成 `hourly.csv`、`daily.csv` 与 `report.xlsx`。

没有模型或想验证全链路时切回模拟数据：

```bash
# Windows
set CAMPUS_DETECTOR=mock && python main.py --max_frames 600
# macOS / Linux
CAMPUS_DETECTOR=mock python main.py --max_frames 600
```

### 4. 启动网页看板

```bash
python web_dashboard.py
# 浏览器打开 http://127.0.0.1:5000
```

## 配置说明（config.py 关键字段）

| 字段 | 说明 |
| --- | --- |
| `CLASSES` | 类别列表，顺序即模型输出类别顺序，须与标注 / 训练一致 |
| `DETECTOR` | `yolo_onnx` 真实模型（默认）/ `mock` 模拟检测；可用环境变量 `CAMPUS_DETECTOR` 覆盖 |
| `YOLO_ONNX` | ONNX 模型路径（默认 `models/car_yolo.onnx`） |
| `CONF_THRES` / `IOU_THRES` | 置信度阈值 / NMS IoU 阈值；`CONF_THRES` 可用 `CAMPUS_CONF` 覆盖 |
| `TEST_VIDEO` / `USE_RTSP` / `RTSP_URL` | 视频源：本地文件（可用 `CAMPUS_VIDEO` 覆盖）或 RTSP 实时流 |
| `TILE_MODE` / `TILE_SIZE` / `TILE_OVERLAP` | 竖屏长条画面分块推理：`auto` 自动 / `1` 强制 / `0` 关闭，可用 `CAMPUS_TILE` 覆盖 |
| `LINE_Y` | 进出判定虚拟线（归一化 y，0=顶 1=底） |
| `ENTER_WHEN` | 穿越方向：`down`=向下为进校 |
| `WEB_HOST` / `WEB_PORT` | 看板监听地址 / 端口（默认 127.0.0.1:5000） |

## 本次训练结果

- **数据**：298 张车图，311 个框（轿车 105 / SUV 52 / 货车 79 / 客车 75），8:2 切分为训练 238 / 验证 60
- **环境**：AMD Radeon Cloud，ROCm 7.2.1，W7900(gfx1100)，Ultralytics 8.4.203
- **配置**：YOLO11n 预训练权重，100 epoch，imgsz 640，batch 16
- **指标**：`mAP50 = 0.799`、`mAP50-95 = 0.569`、精确率 `0.725`、召回率 `0.788`
- **类别顺序**：`0 轿车 / 1 SUV / 2 货车 / 3 客车`，与 `CLASSES = sedan/suv/truck/bus` 一一对齐

## 真实场景评估

两段真实视频的评估数据、对比图与结论见 [`docs/real_video_eval.md`](docs/real_video_eval.md)，训练曲线见 [`docs/training_curves.png`](docs/training_curves.png)。

- 夜间行车记录仪视频：框住的都是真车但漏检明显，平均置信度由同域 0.848 降到 0.535。
- 白天固定机位俯拍竖屏视频：**首因是尺度压缩**——1080×1920 整图 letterbox 到 640×640 后有效宽度只剩约 360px，远景小车缩没。
- 为此实现 `TiledYoloOnnxDetector`（竖屏自动分块，横屏退化为整图）。同一视频同一阈值下：检出框 **125 → 623**、零检出帧 **39.3% → 0%**、平均置信度 **0.497 → 0.588**，未引入误检，**无需重训模型**。
- 仍待补数据：客车（蓝色大巴未认出）、极远景小车、夜间与车尾视角。
- 工具：`python tools/eval_real_video.py --video <路径>` 可对任意本地视频输出检出统计与带框可视化帧。

## 云端训练流程

1. **标注**：X-AnyLabeling 标注四类 → 导出 `YOLO HBB`（水平矩形框）。
   > 坑：旋转框会被 YOLO HBB 导出器静默跳过，生成空 txt（错误负样本），用 `tools/fix_rotation_labels.py` 修复。
2. **新建实例**：AMD Radeon Cloud 选 Notebook / 1 GPU / AMD OneClick Base，把新的 IP:端口写入 `~/.ssh/config`。
   > 平台到点**自动销毁并删除工作区**，训练产物必须及时下载回本地。
3. **上传**：本机运行 `bash cloud/upload_dataset.sh`（上传 `D:/car_export` 与全部云端脚本）。
4. **训练**：云端运行 `bash /workspace/tools/train_car_yolo.sh`。
5. **取回**：把 `best.onnx` 下载为 `models/car_yolo.onnx`。

关键实现说明：

- 复用镜像自带 `/opt/venv` 的 torch 2.9.1+hip（GPU 可用），**不下载 5.8 GiB 的 torch ROCm wheel**；`cloud_setup_yolo26_env.sh` 仅作兜底。
- 镜像的 torchvision 只有 CPU 版 NMS kernel，Ultralytics 验证阶段会在 CUDA 张量上调用 `torchvision.ops.nms` 并报错。`cloud/rocm_compat.py` 把 NMS 输入临时搬到 CPU、算完搬回原设备，行为与原生一致。
- 云端 `pypi.org` 很慢，安装统一走阿里云镜像。

## 许可证

[MIT](LICENSE)
