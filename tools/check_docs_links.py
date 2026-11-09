#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Markdown / HTML 文档中的本地链接与图片路径是否存在。

只检查仓库内相对路径；外链、锚点、mailto 一律跳过。用于 CI 与 `make links`。

用法:
    python tools/check_docs_links.py
    python tools/check_docs_links.py --root .   # 可指定仓库根目录
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "data", "models", "build", "dist", "node_modules"}

MD_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
HTML_SRC = re.compile(r"(?:src|srcset)\s*=\s*[\"']([^\"']+)[\"']")
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "data:", "//")


def is_external(target: str) -> bool:
    return target.startswith(EXTERNAL)


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0]


def iter_doc_files(root: Path):
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def iter_targets(text: str):
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in MD_LINK.finditer(line):
            yield match.group(1)
        for match in HTML_SRC.finditer(line):
            # srcset 可能含多个候选，用空格 / 逗号分隔
            for candidate in re.split(r"[,\s]+", match.group(1)):
                if candidate:
                    yield candidate


def main() -> int:
    ap = argparse.ArgumentParser(description="校验文档内的本地链接")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()

    root = Path(args.root).resolve()
    checked = 0
    broken: list[str] = []

    for doc in iter_doc_files(root):
        try:
            text = doc.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for raw in iter_targets(text):
            if not raw or is_external(raw) or raw.startswith("#"):
                continue
            rel = strip_anchor(raw)
            if not rel:
                continue
            checked += 1
            target = (doc.parent / rel).resolve()
            if not target.exists():
                broken.append(f"{doc.relative_to(root)} -> {raw}")

    if broken:
        print(f"[links] 检查 {checked} 个本地链接，发现 {len(broken)} 个失效：")
        for item in broken:
            print("  - " + item)
        return 1
    print(f"[links] 检查 {checked} 个本地链接，全部有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
