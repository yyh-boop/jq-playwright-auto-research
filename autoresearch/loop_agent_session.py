# -*- coding: utf-8 -*-
"""阶段 3.6：单次 research_loop 内复用的 Cursor Agent（create + 多轮 send）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoresearch.cursor_client import AgentRunResult, apply_win_sdk_shim, get_agent_model, get_cursor_api_key
from autoresearch.research_paths import BASE_DIR


@dataclass
class LoopAgentSession:
    """Wraps cursor_sdk Agent for one research_loop run."""

    agent: Any
    agent_id: str

    @classmethod
    def open(cls, *, cwd: Path | None = None, name: str | None = None) -> "LoopAgentSession":
        apply_win_sdk_shim()
        from cursor_sdk import Agent, LocalAgentOptions

        work = (cwd or BASE_DIR).resolve()
        agent = Agent.create(
            api_key=get_cursor_api_key(),
            model=get_agent_model(),
            name=name or "autoresearch-loop",
            local=LocalAgentOptions(cwd=str(work)),
        )
        return cls(agent=agent, agent_id=str(agent.agent_id))

    def close(self) -> None:
        try:
            self.agent.close()
        except Exception:
            pass

    def __enter__(self) -> "LoopAgentSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send(self, message: str) -> AgentRunResult:
        run = self.agent.send(message)
        run.wait()
        status = getattr(run, "status", None)
        text = run.text()
        if status and str(status).lower() in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Agent status={status}")
        return AgentRunResult(status=str(status) if status is not None else None, text=str(text))
