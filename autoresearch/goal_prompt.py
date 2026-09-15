# -*- coding: utf-8 -*-
"""
解析 GUI 输入的研究目标（自然语言），供后续 Agent 与可选数值停止条件使用。

阶段 3.0：轻量正则提取年化/回撤；未提取到时仅依赖 Agent 判断 + max_agent_rounds。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedGoalHints:
    raw: str
    annual_return_min: float | None  # %
    max_drawdown_max: float | None  # %

    def has_numeric_hints(self) -> bool:
        return self.annual_return_min is not None or self.max_drawdown_max is not None


_RE_ANNUAL = re.compile(
    r"(?:年化|年华|策略收益|收益)[^0-9]{0,12}(?:≥|>=|大于|不低于|至少|达到)?\s*(\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)
_RE_DRAWDOWN = re.compile(
    r"(?:最大回撤|回撤)[^0-9]{0,12}(?:≤|<=|小于|不超过|低于|至多)?\s*(\d+(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)


def parse_goal_text(goal_text: str) -> ParsedGoalHints:
    text = goal_text.strip()
    annual = None
    dd = None
    m = _RE_ANNUAL.search(text)
    if m:
        annual = float(m.group(1))
    m = _RE_DRAWDOWN.search(text)
    if m:
        dd = float(m.group(1))
    return ParsedGoalHints(raw=text, annual_return_min=annual, max_drawdown_max=dd)
