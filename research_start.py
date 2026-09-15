# -*- coding: utf-8 -*-
"""
阶段 3.2 一键启动：GUI 输入目标 → session → 上传本地策略 → 单次回测。

用法：
  python research_start.py
"""

from __future__ import annotations

import json
import sys

from autoresearch.backtest_runner import run_single_upload_backtest
from autoresearch.goal_prompt import parse_goal_text
from autoresearch.session_init import prepare_research_session


def main() -> int:
    try:
        init = prepare_research_session()
    except (FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    if init is None:
        print("已取消")
        return 0

    session = init.session
    hints = parse_goal_text(session.goal_text)

    print("阶段 3.2 会话已创建，开始上传并回测…")
    print(f"  聚宽策略：{init.config.joinquant_strategy_name}")
    print(f"  本地主文件：{init.config.strategy_file}")
    print(f"  原始备份：{init.original_backup}")
    print(f"  session：{init.session_path}")
    print(f"  目标：{session.goal_text}")
    if hints.has_numeric_hints():
        print(
            f"  解析到的数值提示：年化≥{hints.annual_return_min}% "
            f"回撤≤{hints.max_drawdown_max}%"
        )

    code = run_single_upload_backtest(
        init.config.strategy_file,
        session=session,
    )
    if code == 0:
        print("\n阶段 3.2 完成。会话摘要：")
        print(json.dumps(session.to_dict(), ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
