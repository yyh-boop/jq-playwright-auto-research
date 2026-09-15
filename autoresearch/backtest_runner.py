# -*- coding: utf-8 -*-
"""阶段 3.1：登录 → 上传本地策略 → 单次回测 → manifest。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import playwright练习 as jq
from autoresearch.agent_task import emit_agent_task
from autoresearch.goal_prompt import parse_goal_text
from autoresearch.research_config import AgentResearchConfig
from autoresearch.research_log import append_research_run
from autoresearch.research_session import ResearchSession
from autoresearch.strategy_versions import validate_python_syntax, read_strategy_source


def run_single_upload_backtest(
    strategy_path: Path,
    *,
    session: ResearchSession | None = None,
    joinquant_strategy_name: str | None = None,
) -> int:
    cfg = AgentResearchConfig.from_env()
    cfg.validate()
    jq_name = joinquant_strategy_name or cfg.joinquant_strategy_name
    path = strategy_path.resolve()
    if not path.is_file():
        print(f"策略文件不存在：{path}")
        return 1

    code = read_strategy_source(path)
    try:
        validate_python_syntax(code, str(path))
    except SyntaxError as exc:
        print(f"策略语法错误：{exc}")
        return 1

    trial_meta: dict[str, Any] = {
        "phase": "3.2" if session else "3.1",
        "action": "upload_and_backtest",
    }
    if session:
        trial_meta["session_id"] = session.session_id
        trial_meta["goal_text"] = session.goal_text
        hints = parse_goal_text(session.goal_text)
        trial_meta["parsed_goal_hints"] = {
            "annual_return_min": hints.annual_return_min,
            "max_drawdown_max": hints.max_drawdown_max,
        }

    jq.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    jq.RESULT_DIR.mkdir(exist_ok=True)
    jq.PROFILE_DIR.mkdir(exist_ok=True)

    username, password = jq.get_credentials()
    print(f"阶段 3.1：上传并回测\n  本地：{path}\n  聚宽策略：{jq_name}\n")

    with sync_playwright() as p:
        context = jq.create_browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        if not jq.ensure_logged_in(page, username, password):
            print("登录失败")
            jq.safe_close_context(context)
            return 1

        if not jq.go_to_strategy_backtest(page):
            print("未能进入策略回测")
            jq.safe_close_context(context)
            return 1

        if not jq.open_existing_strategy(page, jq_name):
            print(f"未能打开策略「{jq_name}」")
            jq.safe_close_context(context)
            return 1

        jq.dismiss_edit_prompt_if_present(page)
        editor_url = page.url
        backtest_params = jq.get_backtest_params()

        try:
            outcome = jq.run_backtest_from_local_file(
                page,
                jq_name,
                backtest_params,
                editor_url,
                path,
                trial_meta=trial_meta,
                configure_backtest=True,
            )
        except (PlaywrightError, RuntimeError, ValueError) as exc:
            print(f"回测失败：{exc}")
            append_research_run(
                {
                    "event": "backtest_error",
                    "session_id": session.session_id if session else None,
                    "strategy_file": str(path),
                    "error": str(exc),
                }
            )
            print("\n浏览器保持打开。按 Enter 关闭...")
            input()
            jq.safe_close_context(context)
            return 1

        if outcome is None:
            append_research_run(
                {
                    "event": "backtest_failed",
                    "session_id": session.session_id if session else None,
                    "strategy_file": str(path),
                }
            )
            print("\n浏览器保持打开。按 Enter 关闭...")
            input()
            jq.safe_close_context(context)
            return 1

        manifest = outcome.manifest
        append_research_run(
            {
                "event": "backtest_complete",
                "session_id": session.session_id if session else None,
                "strategy_file": str(path),
                "run_id": manifest.get("run_id"),
                "result_dir": str(outcome.result_dir),
                "metrics": manifest.get("metrics"),
                "evaluation": manifest.get("evaluation"),
                "passed": manifest.get("passed"),
            }
        )

        task_paths = emit_agent_task(outcome.result_dir, session=session)
        append_research_run(
            {
                "event": "agent_task_written",
                "session_id": session.session_id if session else None,
                "run_id": manifest.get("run_id"),
                "agent_task_md": str(task_paths.markdown),
            }
        )

        print(f"\n完成。结果目录：{outcome.result_dir}")
        print(f"manifest：{outcome.result_dir / 'run_manifest.json'}")
        print(f"Agent 任务：{task_paths.markdown}")
        print(f"阶段 3.4：python research_agent.py --result \"{outcome.result_dir.name}\"")
        print("\n浏览器保持打开。按 Enter 关闭...")
        input()
        jq.safe_close_context(context)

    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="阶段 3.1：本地策略上传聚宽并单次回测")
    parser.add_argument(
        "--strategy",
        type=Path,
        default=None,
        help="覆盖 .env 中 AUTORESEARCH_STRATEGY_FILE",
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="research_bootstrap 生成的 session.json，写入 manifest trial_meta",
    )
    args = parser.parse_args(argv)

    cfg = AgentResearchConfig.from_env()
    path = args.strategy or cfg.strategy_file
    session = ResearchSession.load(args.session) if args.session else None
    return run_single_upload_backtest(path, session=session)


if __name__ == "__main__":
    sys.exit(main())
