# -*- coding: utf-8 -*-
"""在已登录的 Playwright 会话内上传策略并回测（供 research_loop 复用）。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

import playwright练习 as jq
from autoresearch.agent_task import emit_agent_task
from autoresearch.goal_prompt import parse_goal_text
from autoresearch.research_log import append_research_run
from autoresearch.research_session import ResearchSession
from autoresearch.strategy_versions import read_strategy_source, validate_python_syntax


@dataclass(frozen=True)
class UploadBacktestOutcome:
    result_dir: Path
    manifest: dict
    agent_task_json: Path
    strategy_file: Path


def build_trial_meta(
    session: ResearchSession | None,
    *,
    phase: str,
    loop_round: int,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "phase": phase,
        "action": "upload_and_backtest",
        "loop_round": loop_round,
    }
    if session:
        meta["session_id"] = session.session_id
        meta["goal_text"] = session.goal_text
        hints = parse_goal_text(session.goal_text)
        meta["parsed_goal_hints"] = {
            "annual_return_min": hints.annual_return_min,
            "max_drawdown_max": hints.max_drawdown_max,
        }
    return meta


def run_upload_backtest_on_page(
    page: Page,
    *,
    joinquant_strategy_name: str,
    editor_url: str,
    backtest_params: jq.BacktestParams,
    strategy_path: Path,
    session: ResearchSession | None = None,
    loop_round: int = 0,
    configure_backtest: bool = False,
) -> UploadBacktestOutcome | None:
    path = strategy_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"策略文件不存在：{path}")

    code = read_strategy_source(path)
    validate_python_syntax(code, str(path))

    trial_meta = build_trial_meta(session, phase="3.5", loop_round=loop_round)
    trial_meta["local_strategy_file"] = str(path)

    outcome = jq.run_backtest_from_local_file(
        page,
        joinquant_strategy_name,
        backtest_params,
        editor_url,
        path,
        trial_meta=trial_meta,
        configure_backtest=configure_backtest,
    )
    if outcome is None:
        return None

    shutil.copy2(path, outcome.result_dir / "strategy_used.py")
    task_paths = emit_agent_task(outcome.result_dir, session=session)

    manifest = outcome.manifest
    append_research_run(
        {
            "event": "backtest_complete",
            "session_id": session.session_id if session else None,
            "loop_round": loop_round,
            "strategy_file": str(path),
            "run_id": manifest.get("run_id"),
            "result_dir": str(outcome.result_dir),
            "metrics": manifest.get("metrics"),
            "evaluation": manifest.get("evaluation"),
            "passed": manifest.get("passed"),
        }
    )
    append_research_run(
        {
            "event": "agent_task_written",
            "session_id": session.session_id if session else None,
            "loop_round": loop_round,
            "run_id": manifest.get("run_id"),
            "agent_task_md": str(task_paths.markdown),
        }
    )

    return UploadBacktestOutcome(
        result_dir=outcome.result_dir,
        manifest=manifest,
        agent_task_json=task_paths.json_file,
        strategy_file=path,
    )
