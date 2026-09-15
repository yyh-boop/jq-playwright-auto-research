# -*- coding: utf-8 -*-
"""回测结果目录命名：与 strategies 下策略文件名（stem）对齐。"""

from __future__ import annotations

import re
from pathlib import Path

_WIN_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRIM_RE = re.compile(r"\s+")
_SAFE_FALLBACK = "strategy"


def sanitize_result_dir_name(label: str, *, max_len: int = 120) -> str:
    """将策略名转为可在 result/ 下使用的目录名（保留中文）。"""
    s = label.strip()
    s = _WIN_INVALID.sub("_", s)
    s = _TRIM_RE.sub("_", s).strip("._ ")
    if not s:
        s = _SAFE_FALLBACK
    if len(s) > max_len:
        s = s[:max_len].rstrip("._ ")
    return s or _SAFE_FALLBACK


def strategy_label_from_trial_meta(
    joinquant_strategy_name: str,
    trial_meta: dict | None,
) -> str:
    """优先用本地策略文件 stem，否则用聚宽策略名。"""
    if trial_meta:
        local = trial_meta.get("local_strategy_file")
        if local:
            return Path(str(local)).stem
    return joinquant_strategy_name.strip() or _SAFE_FALLBACK


def allocate_result_dir(results_root: Path, strategy_label: str) -> Path:
    """
    在 results_root 下创建目录，主名为策略名；已存在则 ETF动量_r2、_r3…
    """
    results_root.mkdir(parents=True, exist_ok=True)
    base = sanitize_result_dir_name(strategy_label)
    candidate = results_root / base
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    for i in range(2, 1000):
        candidate = results_root / f"{base}_r{i}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
    raise RuntimeError(f"无法分配结果目录名：{base}")
