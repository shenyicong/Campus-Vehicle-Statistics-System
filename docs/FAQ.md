# 常见问题

## 上手与环境

**Q：没有模型、没有视频、没有 GPU，能跑起来吗？**
能。安装 `requirements.txt` 后用 `CAMPUS_DETECTOR=mock`，`main.py` 会用模拟车流跑通「检测 → 跟踪 → 计数 → 报表」，`web_dashboard.py` 可以直接看图表。真实推理也只需 CPU（ONNX Runtime）。

**Q：模型放哪里？怎么导出？**
放到 `models/car_yolo.onnx`（由 `config.YOLO_ONNX` 指定）。导出时显式指定 `format=onnx`、`opset=12`、`imgsz=640`、`simplify=false`；平台默认命令尾部常带 `torchscript` / `simplify=true`，必须手动改。输出布局应为 `[1, 8, 8400]`，否则 `detector.py` 无法解析。模型权重不入库。

**Q：Windows 下环境变量怎么设？**
`set CAMPUS_DETECTOR=mock && python main.py --max_frames 60`（CMD）或 `$env:CAMPUS_DETECTOR="mock"; python main.py`（PowerShell）。Linux / macOS 用 `CAMPUS_DETECTOR=mock python main.py`。可用的变量见 [README 配置说明](../README.md#配置说明)。

**Q：看板打不开？**
默认地址是 `http://127.0.0.1:5000`，且只监听本机。若端口被占用，改 `config.WEB_HOST` / `WEB_PORT`。不想启动服务可以用 `python tools/make_dashboard_snapshot.py` 生成数据内联的静态 HTML。

## 检测与计数

**Q：计数一直是 0？**
多半是虚拟线位置不对。俯拍画面上半部常是天空 / 建筑，默认 `LINE_Y=0.5` 可能落在空白区。先运行：

```bash
python tools/calibrate_line.py --video "D:/path/to.mp4" --frames 240
```

再用 `set CAMPUS_LINE_Y=0.65` 之类覆盖。详见 [line_calibration.md](line_calibration.md)。

**Q：车没动却一直计数？**
静止车流的检测框会上下抖动 0.001~0.01，反复穿过虚拟线。`MIN_TRACK_MOVE`（默认 0.03）要求轨迹相对参考点有足够净位移才允许判定；可用 `CAMPUS_MIN_MOVE` 调整。

**Q：远景小车漏检？**
先用 `CAMPUS_TILE=auto`（默认，按画面长边一维切块）；俯拍密集小目标可试 `CAMPUS_TILE=grid`（横纵都切 640×640，召回最高但约 3 倍耗时）。这只是推理侧补救，根治要靠补充远景小目标训练样本。

**Q：同一辆车被算成两类？**
已知限制：NMS 按类别分别执行，同一辆车可能同时保留两个类别框；且 `tracker.py` 直接采用最新一帧的类别，单帧错分会计错类。修复方向是跨类 NMS + 轨迹级类别众数投票，见 [CHANGELOG](../CHANGELOG.md) 路线图。

**Q：置信度调低能解决漏检 / 错检吗？**
实测 `conf=0.15 / 0.25 / 0.40` 结果几乎不变，不少错检本身置信度很高（0.78 / 0.49）。根因是训练数据分布（v1 96.6% 是「一张图一辆大车」），不是阈值。应扩展数据集并用固定回归集验收。

**Q：怎么接 RTSP 摄像头？**
在 `config.py` 设 `USE_RTSP=True` 与 `RTSP_URL`，或改代码前先确认摄像头流可用。地址可能含账号密码，请勿提交到版本库（见 [SECURITY](../SECURITY.md)）。

## 报表与场地

**Q：CSV 用 Excel 打开中文乱码？**
报表写入使用 `utf-8-sig`（带 BOM），正常双击不会乱码。若用程序读取，指定 `encoding="utf-8-sig"`。

**Q：车位数据是从视频里检测出来的吗？**
不是。系统统计的是**通过虚拟线的分车型通行流量**；「实有多少车位」由本地人员按现场录入 `data/parking_zones.json`，「需要多少车位」由流量推算，两者做供需对比。口径与限制见 [parking_plan.md](parking_plan.md)。

**Q：为什么 12 秒视频会显示「车位明显富余」？**
样本太短，只有一个小时桶，峰值在场数被严重低估。规划结论需要连续多天、覆盖全部出入口的报表，不能用短片段下判断。

**Q：换一个场地要改代码吗？**
不用。改 `data/parking_zones.json`（或用 `CAMPUS_PARKING_ZONES` 指向另一份配置）即可；换机位只需重标定 `LINE_Y`。

## 训练与开发

**Q：本地能重训吗？**
本地环境只需 ONNX Runtime / OpenCV 做推理与评估，训练依赖 PyTorch，脚本在 `cloud/`（ROCm 云端）与 `tools/`（数据处理）。扩展数据分布用 `tools/augment_dataset_v2.py`，每次重训后用 `tools/regression_test.py` 在固定真实场景图上做 A/B，不要只看 val mAP。

**Q：怎么跑测试 / 提交前检查？**

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check --select E9,F63,F7,F82 .
python tools/check_docs_links.py
```

或 `make check`（需要 make）。CI 覆盖 Python 3.10 / 3.11 / 3.12。

**Q：发现安全漏洞怎么报告？**
不要在公开 Issue 里披露，按 [SECURITY.md](../SECURITY.md) 通过 GitHub 私人安全通告提交。
