# -*- coding: utf-8 -*-
"""根据 metrics 与 ResearchGoal 判断是否达标。"""

from __future__ import annotations

from typing import Any

from autoresearch.config import ResearchGoal


def evaluate_goal(
    metrics: dict[str, Any],
    goal: ResearchGoal | None = None,
) -> dict[str, Any]:
    """
    返回 evaluation 结构，供 run_manifest 使用。

    passed：年化（策略收益）与最大回撤同时满足时为 True
    gaps：未达标时的差距说明
    """
    goal = goal or ResearchGoal.from_env()
    annual = (
        metrics.get("strategy_annual_return_pct")
        or metrics.get("strategy_return_pct")
        or metrics.get("annual_return_pct")
    )
    drawdown = metrics.get("max_drawdown_pct")

    missing: list[str] = []
    if annual is None:
        missing.append("annual_return_pct")
    if drawdown is None:
        missing.append("max_drawdown_pct")

    gaps: dict[str, Any] = {}
    checks: dict[str, bool] = {}

    if annual is not None:
        ok = annual >= goal.annual_return_min
        checks["annual_return"] = ok
        if not ok:
            gaps["annual_return"] = {
                "actual": annual,
                "required_min": goal.annual_return_min,
                "delta": round(annual - goal.annual_return_min, 4),
            }

    if drawdown is not None:
        ok = drawdown <= goal.max_drawdown_max
        checks["max_drawdown"] = ok
        if not ok:
            gaps["max_drawdown"] = {
                "actual": drawdown,
                "required_max": goal.max_drawdown_max,
                "delta": round(drawdown - goal.max_drawdown_max, 4),
            }

    passed = bool(checks) and all(checks.values()) and not missing

    return {
        "passed": passed,
        "checks": checks,
        "gaps": gaps,
        "missing_metrics": missing,
        "goal": goal.as_dict(),
    }
