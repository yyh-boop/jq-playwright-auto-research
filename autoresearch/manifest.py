# -*- coding: utf-8 -*-
"""生成 run_manifest.json（单次回测实验记录）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.config import ResearchGoal
from autoresearch.evaluate_goal import evaluate_goal
from autoresearch.parse_performance import parse_performance_metrics


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def build_run_manifest(
    *,
    run_id: str,
    strategy: str,
    backtest: dict[str, Any],
    paths: dict[str, str | None],
    metrics: dict[str, Any] | None = None,
    goal: ResearchGoal | None = None,
    evaluation: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal = goal or ResearchGoal.from_env()
    if evaluation is None and metrics is not None:
        evaluation = evaluate_goal(metrics, goal)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "backtest": backtest,
        "paths": paths,
        "metrics": metrics or {},
        "goal": goal.as_dict(),
        "evaluation": evaluation or {},
        "passed": bool((evaluation or {}).get("passed")),
    }
    if extra:
        manifest["extra"] = extra
    if extra and extra.get("strategy_params") is not None:
        manifest["strategy_params"] = extra["strategy_params"]
    return manifest


def finalize_manifest_from_result_dir(
    result_dir: Path | str,
    *,
    strategy: str,
    backtest: dict[str, Any],
    paths: dict[str, Path | str | None] | None = None,
    goal: ResearchGoal | None = None,
    strategy_params: dict[str, Any] | None = None,
    trial_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    从 result 目录读取 performance_metrics.xlsx，生成完整 manifest。
    run_id 默认取结果目录名（通常为本地策略文件名 stem）。
    """
    d = Path(result_dir)
    run_id = d.name
    perf = d / "performance_metrics.xlsx"

    path_map: dict[str, str | None] = {}
    if paths:
        for k, v in paths.items():
            if v is None:
                path_map[k] = None
            else:
                path_map[k] = _rel(Path(v), d.parent)
    else:
        for name in (
            "overview_full.png",
            "trade_details.xlsx",
            "daily_positions.xlsx",
            "performance_metrics.xlsx",
        ):
            p = d / name
            path_map[name.replace(".", "_")] = name if p.is_file() else None

    metrics = parse_performance_metrics(perf) if perf.is_file() else {}
    evaluation = evaluate_goal(metrics, goal) if metrics else {}

    extra: dict[str, Any] = {}
    if strategy_params is not None:
        extra["strategy_params"] = strategy_params
    if trial_meta is not None:
        extra["trial_meta"] = trial_meta

    return build_run_manifest(
        run_id=run_id,
        strategy=strategy,
        backtest=backtest,
        paths=path_map,
        metrics=metrics,
        goal=goal,
        evaluation=evaluation,
        extra=extra or None,
    )


def write_run_manifest(result_dir: Path | str, manifest: dict[str, Any]) -> Path:
    d = Path(result_dir)
    out = d / "run_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
