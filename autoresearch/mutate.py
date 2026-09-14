# -*- coding: utf-8 -*-
"""
阶段 2 参数变异：只改 strategy_params，不改回测区间/资金/频度。

策略：轮流选一个参数，在 search_space 内按 step 上下试探（类似坐标下降）。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from autoresearch.strategy_params import clone_config, params_snapshot


class StrategyParamMutator:
    def __init__(self, config: dict[str, Any]) -> None:
        self._base = clone_config(config)
        self._current = clone_config(config)
        self._param_names = list((config.get("search_space") or {}).keys())
        self._trial_index = 0
        self._direction: dict[str, int] = {k: 1 for k in self._param_names}

    @property
    def baseline(self) -> dict[str, int | float]:
        return params_snapshot(self._base)

    def current(self) -> dict[str, int | float]:
        return params_snapshot(self._current)

    def next_trial(self) -> tuple[int, dict[str, int | float], dict[str, Any]]:
        """
        返回 (trial_no, params_dict, meta)。
        trial 0 使用 baseline，之后每次只调整一个参数。
        """
        trial_no = self._trial_index
        self._trial_index += 1

        if trial_no == 0:
            return trial_no, self.current(), {"action": "baseline", "changed": None}

        if not self._param_names:
            return trial_no, self.current(), {"action": "noop", "changed": None}

        name = self._param_names[(trial_no - 1) % len(self._param_names)]
        spec = self._current["search_space"][name]
        step = float(spec.get("step", 1))
        lo = float(spec.get("min", -1e18))
        hi = float(spec.get("max", 1e18))
        cur = float(self._current["params"][name])
        direction = self._direction.get(name, 1)
        nxt = cur + direction * step

        if nxt > hi:
            nxt = cur - step
            direction = -1
        elif nxt < lo:
            nxt = cur + step
            direction = 1

        nxt = max(lo, min(hi, nxt))
        if isinstance(self._current["params"][name], int):
            nxt = int(round(nxt))

        self._direction[name] = direction
        self._current["params"][name] = nxt
        return trial_no, self.current(), {
            "action": "mutate",
            "changed": name,
            "from": cur,
            "to": nxt,
        }

    def note_improvement(self, params: dict[str, int | float]) -> None:
        """若本轮指标更优，可将 current 固定为新的基点（阶段 2 可选）。"""
        for k, v in params.items():
            if k in self._current.get("params", {}):
                self._current["params"][k] = v
