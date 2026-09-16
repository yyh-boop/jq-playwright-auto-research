# -*- coding: utf-8 -*-
"""
根据 result/<策略名>/ 内已有文件重新生成 run_manifest.json。

优先 overview_metrics.json（聚宽收益概述抓取）；否则按回测长度从 Excel 选 12/6 个月列。
用法：python refresh_run_manifest.py result/ETF动量
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoresearch.manifest import finalize_manifest_from_result_dir, write_run_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新 run_manifest.json 指标")
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    rd = args.result_dir.resolve()
    if not rd.is_dir():
        print(f"目录不存在：{rd}", file=sys.stderr)
        return 1
    old = rd / "run_manifest.json"
    if not old.is_file():
        print(f"缺少 {old}", file=sys.stderr)
        return 1
    data = json.loads(old.read_text(encoding="utf-8"))
    manifest = finalize_manifest_from_result_dir(
        rd,
        strategy=str(data.get("strategy", "")),
        backtest=data.get("backtest") or {},
        trial_meta=(data.get("extra") or {}).get("trial_meta"),
    )
    write_run_manifest(rd, manifest)
    m = manifest.get("metrics") or {}
    print(
        f"已更新 {rd / 'run_manifest.json'}\n"
        f"  策略收益={m.get('strategy_return_pct')}% "
        f"策略年化={m.get('strategy_annual_return_pct')}% "
        f"最大回撤={m.get('max_drawdown_pct')}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
