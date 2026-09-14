# -*- coding: utf-8 -*-
"""阶段 2：循环实验配置（回测区间/资金/频度固定，只调策略参数）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from autoresearch.config import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = BASE_DIR / "experiments"
EXPERIMENTS_JSONL = EXPERIMENTS_DIR / "experiments.jsonl"
STRATEGY_PARAMS_FILE = BASE_DIR / "strategy_params.json"
STRATEGY_PARAMS_EXAMPLE = Path(__file__).resolve().parent / "strategy_params.example.json"


def _int_env(name: str, default: int) -> int:
    load_env_file()
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _bool_env(name: str, default: bool) -> bool:
    load_env_file()
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class OrchestratorConfig:
    max_trials: int
    stop_on_pass: bool
    patience: int  # 连续无改进轮数（可选停止，0=禁用）
    fixed_backtest: bool  # 阶段 2 恒为 True：不改回测区间/资金/频度

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        return cls(
            max_trials=_int_env("AUTORESEARCH_MAX_TRIALS", 5),
            stop_on_pass=_bool_env("AUTORESEARCH_STOP_ON_PASS", True),
            patience=_int_env("AUTORESEARCH_PATIENCE", 0),
            fixed_backtest=True,
        )
