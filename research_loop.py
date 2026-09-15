# -*- coding: utf-8 -*-
"""
阶段 3.5 一键 auto-research：GUI 目标 → 基线回测 → Agent 改码 → 再回测（单浏览器登录）。

用法：
  python research_loop.py
  python research_loop.py --max-rounds 5

.env：
  AUTORESEARCH_STRATEGY_FILE=strategies/ETF动量.py   # 第 1 轮 baseline
  AUTORESEARCH_MAX_AGENT_ROUNDS=5
"""

from __future__ import annotations

import argparse
import sys

from autoresearch.research_loop_runner import print_loop_summary, run_research_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 3.5 research 循环")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="回测轮数上限（默认 .env AUTORESEARCH_MAX_AGENT_ROUNDS，建议 5）",
    )
    args = parser.parse_args()

    try:
        summary = run_research_loop(max_rounds=args.max_rounds)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    print_loop_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
