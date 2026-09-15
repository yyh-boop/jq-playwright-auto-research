# -*- coding: utf-8 -*-
"""
阶段 3.1 入口：本地 strategies/ → 聚宽 → 单次回测。

用法：
  python research_run.py
  python research_run.py --session experiments/sessions/<id>/session.json
"""

from __future__ import annotations

import sys

from autoresearch.backtest_runner import main

if __name__ == "__main__":
    sys.exit(main())
