# -*- coding: utf-8 -*-
"""
阶段 3.0：校验 .env、输入研究目标、初始化 session 与 _original 备份。

完整 Agent 循环在后续 research_loop.py；本脚本用于验证 3.0 约定。

用法：
  python research_bootstrap.py
"""

from __future__ import annotations

import json
import sys

from autoresearch.goal_prompt import parse_goal_text
from autoresearch.goal_ui import prompt_research_goal
from autoresearch.research_config import AgentResearchConfig
from autoresearch.research_log import append_research_run
from autoresearch.research_session import ResearchSession
from autoresearch.strategy_versions import ensure_original_backup


def main() -> int:
    try:
        cfg = AgentResearchConfig.from_env()
        cfg.validate()
    except (FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    goal = prompt_research_goal()
    if goal is None:
        print("已取消")
        return 0

    hints = parse_goal_text(goal)
    orig = ensure_original_backup(cfg.strategy_file)

    session = ResearchSession.create(
        goal_text=goal,
        strategy_file=cfg.strategy_file,
        joinquant_strategy_name=cfg.joinquant_strategy_name,
        max_agent_rounds=cfg.max_agent_rounds,
        extra={
            "parsed_goal_hints": {
                "annual_return_min": hints.annual_return_min,
                "max_drawdown_max": hints.max_drawdown_max,
            },
        },
    )
    session_path = session.save()

    append_research_run(
        {
            "event": "session_start",
            "session_id": session.session_id,
            "goal_text": goal,
            "strategy_file": session.strategy_file,
            "original_backup": str(orig),
            "joinquant_strategy_name": cfg.joinquant_strategy_name,
            "max_agent_rounds": cfg.max_agent_rounds,
        }
    )

    print("阶段 3.0 初始化完成")
    print(f"  聚宽策略：{cfg.joinquant_strategy_name}")
    print(f"  本地主文件：{cfg.strategy_file}")
    print(f"  原始备份：{orig}")
    print(f"  session：{session_path}")
    print(f"  目标：{goal}")
    if hints.has_numeric_hints():
        print(
            f"  解析到的数值提示：年化≥{hints.annual_return_min}% "
            f"回撤≤{hints.max_drawdown_max}%"
        )
    else:
        print("  （未从目标中解析到数值；停止将依赖 manifest 默认 goal 或后续 Agent 轮次上限）")
    print("\n会话内容预览：")
    print(json.dumps(session.to_dict(), ensure_ascii=False, indent=2))
    print(f"\n下一步（阶段 3.1 回测）：\n  python research_run.py --session \"{session_path}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
