# -*- coding: utf-8 -*-
"""本地策略版本：_original 备份与按改动方向命名的新文件。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from autoresearch.research_paths import ORIGINAL_SUFFIX, STRATEGIES_DIR

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_\u4e00-\u9fff]+")


def stem_from_path(path: Path) -> str:
    return path.stem


def original_path_for(main_file: Path) -> Path:
    """strategies/foo.py → strategies/foo_original.py"""
    return main_file.parent / f"{main_file.stem}{ORIGINAL_SUFFIX}{main_file.suffix}"


def slugify_direction(label: str, max_len: int = 48) -> str:
    """将 Agent 给出的改动方向转为安全文件名片段。"""
    s = label.strip().replace(" ", "_")
    s = _SLUG_RE.sub("_", s).strip("_")
    if not s:
        s = "revision"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def iteration_path(main_file: Path, direction_slug: str, round_no: int | None = None) -> Path:
    """
    strategies/ETF动量.py + 收紧止损 → strategies/ETF动量_收紧止损.py
    若重名则追加 _r2 等。
    """
    slug = slugify_direction(direction_slug)
    base = main_file.parent / f"{main_file.stem}_{slug}{main_file.suffix}"
    if round_no is not None and round_no > 1:
        candidate = main_file.parent / f"{main_file.stem}_{slug}_r{round_no}{main_file.suffix}"
        if not candidate.exists():
            return candidate
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = main_file.parent / f"{main_file.stem}_{slug}_r{i}{main_file.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法分配迭代文件名：{main_file.stem}_{slug}")


def ensure_original_backup(main_file: Path, *, force: bool = False) -> Path:
    """
    若不存在 _original，则从 main_file 复制一份（仅首次）。
    返回 original 路径。
    """
    main_file = main_file.resolve()
    orig = original_path_for(main_file)
    if orig.is_file() and not force:
        return orig
    if not main_file.is_file():
        raise FileNotFoundError(main_file)
    orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_file, orig)
    return orig


def read_strategy_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_strategy_source(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return path


def validate_python_syntax(code: str, filename: str = "<strategy>") -> None:
    compile(code, filename, "exec")
