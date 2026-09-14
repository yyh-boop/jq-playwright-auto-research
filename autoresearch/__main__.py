# -*- coding: utf-8 -*-
"""
对已有一次回测结果目录补生成 / 刷新 run_manifest.json。

用法：
  python -m autoresearch result/20260908_113757
  python -m autoresearch result/20260908_113757 --strategy 自动化测试用
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoresearch.config import ResearchGoal
from autoresearch.manifest import finalize_manifest_from_result_dir, write_run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 result 目录生成 run_manifest.json")
    parser.add_argument("result_dir", type=Path, help="回测结果目录（含 performance_metrics.xlsx）")
    parser.add_argument("--strategy", default="自动化测试用", help="策略名称")
    parser.add_argument("--start", default="", help="回测开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="回测结束日期 YYYY-MM-DD")
    parser.add_argument("--capital", type=int, default=0, help="初始资金")
    parser.add_argument("--frequency", default="", help="回测频度")
    args = parser.parse_args(argv)

    if not args.result_dir.is_dir():
        print(f"目录不存在：{args.result_dir}", file=sys.stderr)
        return 1

    backtest = {
        "start": args.start or None,
        "end": args.end or None,
        "initial_capital": args.capital or None,
        "frequency": args.frequency or None,
    }

    manifest = finalize_manifest_from_result_dir(
        args.result_dir,
        strategy=args.strategy,
        backtest=backtest,
        goal=ResearchGoal.from_env(),
    )
    out = write_run_manifest(args.result_dir, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\n已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
