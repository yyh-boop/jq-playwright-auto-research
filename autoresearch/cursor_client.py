# -*- coding: utf-8 -*-
"""Cursor SDK 封装：.env 密钥、Windows 兼容、本地 Agent 调用。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from autoresearch.config import load_env_file
from autoresearch.research_paths import BASE_DIR


def apply_win_sdk_shim() -> None:
    if sys.platform == "win32":
        if not hasattr(os, "get_blocking"):
            os.get_blocking = lambda _fd: True  # type: ignore[attr-defined]
        if not hasattr(os, "set_blocking"):
            os.set_blocking = lambda _fd, _blocking: None  # type: ignore[attr-defined]


def get_cursor_api_key() -> str:
    load_env_file()
    key = os.getenv("CURSOR_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "未设置 CURSOR_API_KEY。请在 .env 中添加 User API Key（Dashboard → API & SSH Keys）。"
        )
    return key


def get_agent_model() -> str:
    load_env_file()
    return os.getenv("AUTORESEARCH_AGENT_MODEL", "composer-2.5").strip() or "composer-2.5"


@dataclass(frozen=True)
class AgentRunResult:
    status: str | None
    text: str


def run_local_agent_prompt(prompt: str, *, cwd: Path | None = None) -> AgentRunResult:
    apply_win_sdk_shim()
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

    work = cwd or BASE_DIR
    api_key = get_cursor_api_key()
    model = get_agent_model()
    raw = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=str(work.resolve())),
        ),
    )
    status = getattr(raw, "status", None)
    text = getattr(raw, "result", None) or getattr(raw, "output", None) or str(raw)
    return AgentRunResult(status=str(status) if status is not None else None, text=str(text))
