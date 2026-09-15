# -*- coding: utf-8 -*-
"""
阶段 3 运行配置（从 .env 读取，不含当次 GUI 输入的研究目标）。

当次目标在 research_session 中由启动器写入，不写入 .env。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from autoresearch.config import load_env_file
from autoresearch.research_paths import BASE_DIR, STRATEGIES_DIR


def _int_env(name: str, default: int) -> int:
    load_env_file()
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _path_env(name: str, default: Path) -> Path:
    load_env_file()
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    p = Path(raw)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p.resolve()


@dataclass(frozen=True)
class AgentResearchConfig:
    """阶段 3 固定配置（换策略时改 .env）。"""

    joinquant_strategy_name: str
    strategy_file: Path
    max_agent_rounds: int
    agent_retries: int  # 编译/回测失败时同轮重试次数

    @classmethod
    def from_env(cls) -> "AgentResearchConfig":
        load_env_file()
        name = os.getenv("JOINQUANT_STRATEGY_NAME", "自动化测试用").strip() or "自动化测试用"
        default_strategy = STRATEGIES_DIR / "ETF动量.py"
        strategy_file = _path_env("AUTORESEARCH_STRATEGY_FILE", default_strategy)
        return cls(
            joinquant_strategy_name=name,
            strategy_file=strategy_file,
            max_agent_rounds=_int_env("AUTORESEARCH_MAX_AGENT_ROUNDS", 10),
            agent_retries=_int_env("AUTORESEARCH_AGENT_RETRIES", 2),
        )

    def validate(self) -> None:
        if not self.strategy_file.is_file():
            raise FileNotFoundError(
                f"本地策略不存在：{self.strategy_file}\n"
                f"请在 .env 设置 AUTORESEARCH_STRATEGY_FILE 或将策略放入 strategies/"
            )
        if self.max_agent_rounds < 1:
            raise ValueError("AUTORESEARCH_MAX_AGENT_ROUNDS 至少为 1")
