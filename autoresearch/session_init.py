# -*- coding: utf-8 -*-
"""创建 research session（GUI 目标、_original 备份、jsonl）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autoresearch.goal_prompt import parse_goal_text
from autoresearch.goal_ui import prompt_research_goal
from autoresearch.research_config import AgentResearchConfig
from autoresearch.research_log import append_research_run
from autoresearch.research_session import ResearchSession
from autoresearch.strategy_versions import ensure_original_backup


@dataclass(frozen=True)
class SessionInitResult:
    session: ResearchSession
    session_path: Path
    original_backup: Path
    config: AgentResearchConfig


def prepare_research_session(*, goal_text: str | None = None) -> SessionInitResult | None:
    """
    弹出 GUI 输入目标（除非传入 goal_text），写入 session.json 与 research_runs.jsonl。
    用户取消 GUI 时返回 None。
    """
    cfg = AgentResearchConfig.from_env()
    cfg.validate()

    goal = goal_text
    if goal is None:
        goal = prompt_research_goal()
    if goal is None:
        return None

    hints = parse_goal_text(goal)
    orig = ensure_original_backup(cfg.strategy_file)

    session = ResearchSession.create(
        goal_text=goal,
        strategy_file=cfg.strategy_file,
        joinquant_strategy_name=cfg.joinquant_strategy_name,
        max_agent_rounds=cfg.max_agent_rounds,
        extra={
            "parsed_goal_hints": {
                "annual_return_min": hints.annual_return_min,
                "max_drawdown_max": hints.max_drawdown_max,
            },
        },
    )
    session_path = session.save()

    append_research_run(
        {
            "event": "session_start",
            "session_id": session.session_id,
            "goal_text": goal,
            "strategy_file": session.strategy_file,
            "original_backup": str(orig),
            "joinquant_strategy_name": cfg.joinquant_strategy_name,
            "max_agent_rounds": cfg.max_agent_rounds,
        }
    )

    return SessionInitResult(
        session=session,
        session_path=session_path,
        original_backup=orig,
        config=cfg,
    )
