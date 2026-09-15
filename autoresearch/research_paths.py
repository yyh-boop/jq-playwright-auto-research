# -*- coding: utf-8 -*-
"""
阶段 3 路径与目录约定。

本地策略（真相源）：
  strategies/<stem>.py              当前主策略（.env AUTORESEARCH_STRATEGY_FILE 指向此文件）
  strategies/<stem>_original.py     首次 research 时从主文件复制，只读备份
  strategies/<stem>_<方向>.py       Agent 迭代产物（方向 slug，见 strategy_versions）

实验记录：
  experiments/experiments.jsonl       阶段 2 参数试验（保留）
  experiments/research_runs.jsonl     阶段 3 每轮 research（含 goal_text、strategy_file）
  experiments/sessions/               可选：跨步骤 session 快照（session.json）
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = BASE_DIR / "strategies"
EXPERIMENTS_DIR = BASE_DIR / "experiments"
EXPERIMENTS_JSONL = EXPERIMENTS_DIR / "experiments.jsonl"
RESEARCH_RUNS_JSONL = EXPERIMENTS_DIR / "research_runs.jsonl"
RESEARCH_SESSIONS_DIR = EXPERIMENTS_DIR / "sessions"
RESULT_DIR = BASE_DIR / "result"

ORIGINAL_SUFFIX = "_original"
SCHEMA_VERSION_RESEARCH = 1
