# -*- coding: utf-8 -*-
"""
阶段 3.4：根据 agent_task.json 调用 Cursor Agent 分析并新建 strategies/ 改进版。

用法：
  python research_agent.py --result result/20260915_134935
  python research_agent.py --task result/20260915_134935/agent_task.json
"""

from __future__ import annotations

import argparse
import sys

from autoresearch.research_agent_runner import resolve_agent_task_path, run_research_agent
from autoresearch.research_paths import BASE_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="阶段 3.4：Cursor Agent 策略改进")
    parser.add_argument(
        "--result",
        type=str,
        default=None,
        help="回测结果目录，默认读取其下 agent_task.json",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="agent_task.json 路径（优先于 --result）",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="覆盖 .env 中 AUTORESEARCH_AGENT_RETRIES",
    )
    args = parser.parse_args(argv)

    from pathlib import Path

    task_path = resolve_agent_task_path(
        result_dir=Path(args.result) if args.result else None,
        task_json=Path(args.task) if args.task else None,
    )
    print(f"阶段 3.4 Agent 任务：{task_path.relative_to(BASE_DIR)}")
    print("正在调用 Cursor 本地 Agent（可能需数分钟）…\n")

    try:
        outcome = run_research_agent(task_path, max_retries=args.max_retries)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"status: {outcome.status}")
    print(f"回复已保存：{outcome.response_path}")
    if outcome.new_strategy_files:
        print("检测到 strategies/ 下新增或更新的文件：")
        for p in outcome.new_strategy_files:
            print(f"  - {p.relative_to(BASE_DIR)}")
    else:
        print("未检测到新的 .py 文件；请查看 agent 回复是否已写文件。")
    if outcome.parsed_new_file:
        print(f"解析 NEW_STRATEGY_FILE: {outcome.parsed_new_file.relative_to(BASE_DIR)}")
    print("\n--- Agent 回复摘要（前 800 字）---")
    print(outcome.response_text[:800])
    if len(outcome.response_text) > 800:
        print("…")
    print("\n下一步：将 .env 中 AUTORESEARCH_STRATEGY_FILE 指向新策略后运行 research_run.py 或 research_start.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
