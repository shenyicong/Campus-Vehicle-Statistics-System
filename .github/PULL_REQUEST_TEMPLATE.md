## 变更说明

<!-- 一句话说明这个 PR 做了什么、为什么做 -->

关联 Issue：<!-- Closes #123 -->

## 变更类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 性能 / 精度改进
- [ ] 文档
- [ ] 工程化（CI / 依赖 / 测试 / 重构）

## 影响的模块

- [ ] 检测 `detector.py`
- [ ] 跟踪 / 计数 `tracker.py` `counter.py`
- [ ] 报表 / 停车规划 `reporter.py` `parking_plan.py`
- [ ] 看板 `web_dashboard.py`
- [ ] 工具脚本 `tools/` `cloud/`
- [ ] 文档 / 元数据

## 验证

```bash
pytest -q
ruff check --select E9,F63,F7,F82 .
python tools/check_docs_links.py
```

- [ ] 上述命令本地通过
- [ ] 用 `CAMPUS_DETECTOR=mock` 跑通端到端链路（如改动涉及运行时）
- [ ] 看板 `/`、`/api/stats`、`/api/parking_plan` 正常（如改动涉及看板）
- [ ] 新增/修改的行为有对应测试
- [ ] 未引入密钥、令牌、私有数据或大体积二进制文件

## 截图 / 输出（可选）

<!-- 看板或图表改动请附截图；命令行改动请附关键输出 -->
