# -*- coding: utf-8 -*-
"""聚宽回测 autoresearch：结构化结果、目标评估（阶段 1）。"""

from autoresearch.evaluate_goal import evaluate_goal
from autoresearch.manifest import build_run_manifest, write_run_manifest
from autoresearch.parse_performance import parse_performance_metrics

__all__ = [
    "parse_performance_metrics",
    "evaluate_goal",
    "build_run_manifest",
    "write_run_manifest",
]
