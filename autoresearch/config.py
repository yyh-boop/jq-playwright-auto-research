# -*- coding: utf-8 -*-
"""
autoresearch 目标与默认配置（阶段 1）。

可通过 .env 覆盖：
  AUTORESEARCH_GOAL_ANNUAL_RETURN_MIN=30
  AUTORESEARCH_GOAL_MAX_DRAWDOWN_MAX=10
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file() -> None:
    """与 playwright练习.py 相同：读取项目根目录 .env（不覆盖已有环境变量）。"""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return float(raw)


@dataclass(frozen=True)
class ResearchGoal:
    """回测达标条件（可按项目调整）。"""

    annual_return_min: float  # 策略收益阈值（%，与 performance 表一致）
    max_drawdown_max: float  # 最大回撤上限（%，取绝对值比较）

    @classmethod
    def from_env(cls) -> "ResearchGoal":
        load_env_file()
        return cls(
            annual_return_min=_float_env("AUTORESEARCH_GOAL_ANNUAL_RETURN_MIN", 30.0),
            max_drawdown_max=_float_env("AUTORESEARCH_GOAL_MAX_DRAWDOWN_MAX", 10.0),
        )

    def as_dict(self) -> dict:
        return {
            "annual_return_min": self.annual_return_min,
            "max_drawdown_max": self.max_drawdown_max,
        }
