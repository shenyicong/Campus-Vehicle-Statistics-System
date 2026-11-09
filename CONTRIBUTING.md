# 贡献指南

感谢你愿意改进本项目。无论修一个错字、补一条文档，还是重构检测链路，都欢迎提交 Pull Request。

## 快速搭建开发环境

需要 Python 3.10+（CI 覆盖 3.10 / 3.11 / 3.12）。

```bash
git clone https://github.com/shenyicong/Campus-Vehicle-Statistics-System.git
cd Campus-Vehicle-Statistics-System

python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

不需要 GPU，也不需要模型权重即可开发：`CAMPUS_DETECTOR=mock` 会用模拟车流跑通「检测 → 跟踪 → 计数 → 报表」全链路。

```bash
# Windows
set CAMPUS_DETECTOR=mock && python main.py --max_frames 60
# Linux / macOS
CAMPUS_DETECTOR=mock python main.py --max_frames 60
```

## 提交前自检

```bash
ruff check --select E9,F63,F7,F82 .   # 致命静态问题（未定义名、语法错误等）
python -m compileall -q .             # 全量语法编译
pytest -q                             # 单元测试
python tools/check_docs_links.py      # 文档内本地链接有效性
```

也可以直接运行 `make check`（需要 make）。

新增行为请补对应测试，放在 `tests/` 下，优先写不依赖模型、视频与外部服务的纯逻辑测试。

## 代码约定

- 保持零外部前端依赖：看板图表用内联 SVG，不引入 CDN / Chart.js。
- 检测输出统一为 `[x1, y1, x2, y2, cls_idx, conf]`（像素坐标）；类别顺序以 `config.CLASSES` 为唯一准绳。
- 配置优先走 `config.py` + `CAMPUS_*` 环境变量，不把绝对路径、场地信息写死在业务代码里。
- 脚本放在 `tools/`（本地评估与数据处理）或 `cloud/`（云端训练），并写清用法注释。
- 新依赖同时更新 `requirements.txt`（运行时）或 `requirements-dev.txt`（开发时），注明用途。

## 提交与 PR

- 提交信息推荐 [Conventional Commits](https://www.conventionalcommits.org/)：`feat: 增加分车道虚拟线`、`fix: 修正跨类重复框`、`docs: 补充 FAQ`。
- PR 请填写模板中的验证清单；涉及看板或图表时附截图，涉及算法时说明对既有评估指标的影响。
- 一个 PR 聚焦一件事，便于回归与审阅。

## 不要提交的内容

模型权重（`*.onnx` / `*.pt`）、测试视频、运行时报表、`__pycache__`、本地场地配置中的隐私信息、密钥 / 令牌，以及个人的课程作业文档。相关规则已写入 `.gitignore`。

## 报告问题

功能缺陷与功能建议请使用 [Issue 模板](https://github.com/shenyicong/Campus-Vehicle-Statistics-System/issues/new/choose)；使用与配置问题请先到 Discussions；安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

参与本项目即表示同意遵守 [行为准则](CODE_OF_CONDUCT.md)。
