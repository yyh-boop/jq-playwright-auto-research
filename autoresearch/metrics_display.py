# -*- coding: utf-8 -*-
"""聚宽概述三指标的统一读取（manifest metrics）。"""

from __future__ import annotations

from typing import Any


def strategy_return_pct(metrics: dict[str, Any] | None) -> float | None:
    if not metrics:
        return None
    v = metrics.get("strategy_return_pct")
    return float(v) if v is not None else None


def strategy_annual_return_pct(metrics: dict[str, Any] | None) -> float | None:
    if not metrics:
        return None
    v = metrics.get("strategy_annual_return_pct")
    if v is not None:
        return float(v)
    v = metrics.get("annual_return_pct")
    return float(v) if v is not None else None


def max_drawdown_pct(metrics: dict[str, Any] | None) -> float | None:
    if not metrics:
        return None
    v = metrics.get("max_drawdown_pct")
    return float(v) if v is not None else None


def format_metrics_line(metrics: dict[str, Any] | None) -> str:
    return (
        f"策略收益≈{strategy_return_pct(metrics)}% "
        f"策略年化≈{strategy_annual_return_pct(metrics)}% "
        f"最大回撤≈{max_drawdown_pct(metrics)}%"
    )
