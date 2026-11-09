# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中

- 轨迹级类别众数投票，降低单帧错分对分车型计数的影响
- 跨类 NMS，消除同一辆车被同时保留为两个类别的重复框
- 分车道双向虚拟线，适配双向车流场景
- 用 v2 数据集（多车同框 / 远景小目标 / 硬负样本）重训并以固定回归集验收

## [0.2.0] - 2026-11-09

### 新增

- README 明暗双主题 Hero Image 与 GitHub Social Preview 素材（含可编辑 HTML 源）
- `tools/augment_dataset_v2.py`：多车同框、远景小目标与硬负样本合成，扩展训练数据分布
- `tools/regression_test.py`：固定真实场景回归集，用于每次重训后的 A/B 验收
- `tools/upload_dataset_platform.py`：Ultralytics Platform 数据集 REST 上传全流程（含离线自检）
- v2 数据集切分与校验（train/val、类别 id、空标签、绝对路径检查）
- 网页看板深 / 浅双主题、纯 SVG 图表与场地车位设置抽屉
- `tools/make_dashboard_snapshot.py`：数据内联、无需启动服务的静态看板快照

### 修复

- `IoUTracker` 只返回本帧活跃轨迹，消除僵尸轨迹造成的重复计数与「运动车流被误判静止」
- `tools/calibrate_line.py` 虚拟线标定与 `MIN_TRACK_MOVE` 假跨线抑制
- 分块推理改为按画面长边自适应，修正竖屏 / 宽幅横屏的远景小车漏检

## [0.1.0] - 2026-11-07

### 新增

- 基于 YOLO11n ONNX 的四类车型 CPU 推理（letterbox 预处理 + 按类 NMS）
- 轻量 IoU 跟踪器与虚拟线进出判定、分车型计数
- 小时 / 日粒度 CSV 与 Excel 报表
- Flask 数据驾驶舱：KPI、分车型进出、车型结构、24 小时热力
- 场地车位本地配置、供需对比与规划报告（md / csv / xlsx）
- 云端 ROCm 训练脚本、导出 ONNX 与结果校验工具链
- 真实视频抽样评估、虚拟线标定、训练曲线绘制等 `tools/` 脚本
