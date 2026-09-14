# -*- coding: utf-8 -*-
"""加载 / 校验 strategy_params.json（策略可调参数，非回测区间）。"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from autoresearch.orchestrator_config import STRATEGY_PARAMS_EXAMPLE, STRATEGY_PARAMS_FILE

DEFAULT_MARKERS = (
    "# === AUTORESEARCH_TUNABLES ===",
    "# === END AUTORESEARCH_TUNABLES ===",
)


def load_strategy_params_config(path: Path | None = None) -> dict[str, Any]:
    p = path or STRATEGY_PARAMS_FILE
    if not p.is_file():
        raise FileNotFoundError(
            f"未找到 {p}。请复制 {STRATEGY_PARAMS_EXAMPLE.name} 为 strategy_params.json 并填写与策略一致的参数名。"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    if "params" not in data or "search_space" not in data:
        raise ValueError("strategy_params.json 需包含 params 与 search_space")
    return data


def params_snapshot(config: dict[str, Any]) -> dict[str, int | float]:
    raw = config.get("params") or {}
    return {k: raw[k] for k in raw}


def trial_param_sets_count(config: dict[str, Any]) -> int:
    sets = config.get("trial_param_sets")
    if not sets or not isinstance(sets, list):
        return 0
    return len(sets)


def iter_trial_param_sets(
    config: dict[str, Any], max_trials: int
) -> Iterator[tuple[int, dict[str, int | float], dict[str, Any]]]:
    """
    按 trial_param_sets 依次产出 (trial_no, 完整 params, meta)。
    每项可含 label；其余键与 params 合并（用于覆盖 MOM_SHORT 等）。
    """
    sets = config.get("trial_param_sets") or []
    base = params_snapshot(config)
    n = min(max_trials, len(sets))
    for trial_no in range(n):
        raw = sets[trial_no]
        if not isinstance(raw, dict):
            raise ValueError(f"trial_param_sets[{trial_no}] 必须是对象")
        label = raw.get("label", f"set_{trial_no + 1}")
        overrides = {k: v for k, v in raw.items() if k != "label"}
        merged = {**base, **overrides}
        meta: dict[str, Any] = {
            "action": "fixed_set",
            "label": label,
            "overrides": overrides,
        }
        yield trial_no, merged, meta


def patch_strategy_source(code: str, params: dict[str, int | float], config: dict[str, Any]) -> str:
    """在 AUTORESEARCH 标记块内替换 NAME = value 行。"""
    start = config.get("marker_start") or DEFAULT_MARKERS[0]
    end = config.get("marker_end") or DEFAULT_MARKERS[1]
    if start not in code or end not in code:
        raise ValueError(
            f"策略源码中未找到标记块：\n  {start}\n  {end}\n"
            "请在聚宽「自动化测试用」策略中加入上述两行及中间的可调常量。"
        )

    before, rest = code.split(start, 1)
    middle, after = rest.split(end, 1)
    block = middle
    for name, value in params.items():
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        repl = f"{name} = {value}"
        line_re = re.compile(rf"^(\s*{re.escape(name)}\s*=\s*).+$", re.MULTILINE)
        if not line_re.search(block):
            raise ValueError(f"标记块内未找到参数行：{name} = ...")
        block = line_re.sub(rf"\g<1>{value}", block, count=1)
    return before + start + block + end + after


def validate_params_in_search_space(
    params: dict[str, int | float], config: dict[str, Any]
) -> None:
    space = config.get("search_space") or {}
    for name, val in params.items():
        if name not in space:
            continue
        spec = space[name]
        lo, hi = spec.get("min"), spec.get("max")
        if lo is not None and val < lo:
            raise ValueError(f"{name}={val} 小于 search_space.min={lo}")
        if hi is not None and val > hi:
            raise ValueError(f"{name}={val} 大于 search_space.max={hi}")


def clone_config(config: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(config)
