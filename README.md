# 校园车辆智能统计系统 (Campus Vehicle Statistics System)

基于 YOLO 目标检测的校园校门车辆智能统计系统：自动统计校门监控视频中 **轿车 / SUV / 货车 / 客车** 四类车辆的进出数量，按小时、按日生成统计报表，并提供网页实时看板，为校门口拥堵治理与校园停车资源规划提供数据依据。

## 功能特性

- **四类车型检测**：轿车(sedan)、SUV(suv)、货车(truck)、客车(bus)
- **视频溯源**：支持本地视频文件与 RTSP 实时流（一行配置切换）
- **轨迹跟踪**：轻量 IoU 跟踪器，跨帧关联同一车辆
- **进出判定**：基于虚拟检测线 + 穿越方向，判定进校 / 出校
- **统计分析**：按小时 / 按日聚合，输出 CSV 与 Excel
- **实时看板**：Flask + Chart.js 网页仪表盘，定时刷新
- **可训练**：预留 YOLO-ONNX 推理接口，配套 AMD 云端 ROCm 训练环境脚本

## 系统架构

```
视频源 → 检测器 → 跟踪器(IoU) → 进出判定 → 计数器 → 报表(CSV/Excel) → 网页看板
```

## 目录结构

```
campus_vehicle_system/
├── config.py                  # 全局配置（路径/类别/虚拟线/视频源/端口）
├── video_input.py             # 视频输入：本地文件 或 RTSP 实时流
├── detector.py                # 检测器封装：Mock(全链路验证) + YOLO-ONNX(预留)
├── tracker.py                 # 轻量 IoU 跟踪器
├── counter.py                 # 虚拟线进出判定与计数
├── reporter.py                # 每小时 / 每日 CSV 与 Excel 报表
├── main.py                    # 端到端串联入口
├── make_test_video.py         # 用车型图片合成模拟校门监控测试视频
├── web_dashboard.py           # Flask + Chart.js 实时看板（端口 5000）
├── cloud_setup_yolo26_env.sh  # 云端(AMD ROCm)一键重建训练环境
├── data/
│   ├── .gitkeep
│   ├── test_monitor.mp4       # 测试视频(由 make_test_video.py 生成，不入库)
│   └── reports/               # 报表输出(运行生成，不入库)
├── requirements.txt
├── .gitignore
└── LICENSE
```

## 快速开始

### 1. 准备环境

```bash
python -m venv .venv
pip install -r requirements.txt
# 或用 uv： uv pip install -r requirements.txt
```

### 2. 生成测试视频（可选，使用你标注的车型图片）

默认图片源为 `D:\car`，可用环境变量覆盖：

```bash
# Windows
set CAMPUS_CAR_DIR=D:\car
# macOS / Linux
export CAMPUS_CAR_DIR="$HOME/car"
python make_test_video.py
```

### 3. 运行统计（mock 模式，开箱即跑通全链路）

```bash
python main.py --max_frames 600
```

运行后会在 `data/reports/` 生成 `hourly.csv`、`daily.csv` 与 `report.xlsx`。

### 4. 启动网页看板

```bash
python web_dashboard.py
# 浏览器打开 http://127.0.0.1:5000
```

## 配置说明（config.py 关键字段）

| 字段 | 说明 |
| --- | --- |
| `CLASSES` | 类别列表，顺序即模型输出类别顺序，须与标注 / 训练一致 |
| `DETECTOR` | `mock` 模拟检测 / `yolo_onnx` 真实 YOLO 模型 |
| `YOLO_ONNX` | ONNX 模型路径 |
| `USE_RTSP` / `RTSP_URL` | 视频源切换：本地文件 或 RTSP 实时流 |
| `LINE_Y` | 进出判定虚拟线（归一化 y，0=顶 1=底） |
| `ENTER_WHEN` | 穿越方向：`down`=向下为进校 |
| `WEB_HOST` / `WEB_PORT` | 看板监听地址 / 端口（默认 127.0.0.1:5000） |

## 接入真实模型

1. **标注数据**：用 X-AnyLabeling 对校门车辆图片标注四类，导出 YOLO 格式 txt；
2. **训练**：在 AMD 云端 ROCm 环境运行 `cloud_setup_yolo26_env.sh` 拉起训练环境，训练 4 类 YOLO；
3. **导出 ONNX**：将 `config.DETECTOR` 改为 `yolo_onnx`、`config.YOLO_ONNX` 指向模型；
4. **补全推理**：在 `detector.py` 的 `YoloOnnxDetector.detect` 中实现预处理 + 推理 + NMS 后处理（接口已预留）。

## 云端训练环境

`cloud_setup_yolo26_env.sh` 针对 AMD Radeon Cloud（ROCm 7.2.1，W7900 / gfx1100）一键重建课程训练环境（torch 2.12.0+rocm7.2 + torchvision + ultralytics + Jupyter 内核），上传到云端 `/workspace` 执行即可。

## 许可证

[MIT](LICENSE)
