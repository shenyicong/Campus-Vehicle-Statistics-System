.PHONY: help install lint test check run dashboard snapshot links clean

help:            ## 显示可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:         ## 安装运行时 + 开发依赖
	python -m pip install --upgrade pip
	python -m pip install -r requirements.txt -r requirements-dev.txt

lint:            ## 静态检查（致命规则）
	ruff check --select E9,F63,F7,F82 .

test:            ## 运行单元测试
	pytest -q

links:           ## 校验文档内的本地链接
	python tools/check_docs_links.py

check: lint test links ## 提交前完整自检
	python -m compileall -q .

run:             ## 端到端统计（需模型；mock 模式见 README）
	python main.py --max_frames 600

dashboard:       ## 启动数据驾驶舱 http://127.0.0.1:5000
	python web_dashboard.py

snapshot:        ## 生成零依赖静态看板快照
	python tools/make_dashboard_snapshot.py

clean:           ## 清理缓存（不碰数据与报表）
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache','.ruff_cache','.mypy_cache','htmlcov']]"
	python -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
