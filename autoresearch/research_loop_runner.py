# -*- coding: utf-8 -*-

"""阶段 3.5/3.6：单浏览器会话内 回测 ↔ Agent 循环（3.6：Agent 多轮 send + session 记忆 + report）。"""



from __future__ import annotations



import json

from dataclasses import dataclass

from pathlib import Path

from typing import Any



from playwright.sync_api import Error as PlaywrightError

from playwright.sync_api import sync_playwright



import playwright练习 as jq

from autoresearch.agent_task import emit_agent_task

from autoresearch.backtest_session import run_upload_backtest_on_page

from autoresearch.goal_prompt import parse_goal_text
from autoresearch.metrics_display import format_metrics_line, strategy_annual_return_pct

from autoresearch.loop_agent_session import LoopAgentSession

from autoresearch.research_agent_runner import pick_next_strategy_path, run_research_agent_turn

from autoresearch.research_config import AgentResearchConfig

from autoresearch.research_log import append_research_run

from autoresearch.research_memory import ResearchMemory, record_backtest_round

from autoresearch.research_paths import RESEARCH_SESSIONS_DIR, REPORT_DIR

from autoresearch.research_report import build_final_synthesis_prompt, write_session_report

from autoresearch.research_session import ResearchSession

from autoresearch.session_init import prepare_research_session

from autoresearch.strategy_versions import validate_python_syntax





@dataclass

class RoundRecord:

    loop_round: int

    strategy_file: Path

    result_dir: Path

    manifest: dict

    score: float





@dataclass

class LoopSummary:

    session_id: str

    goal_text: str

    rounds: list[RoundRecord]

    best: RoundRecord

    stopped_reason: str

    report_md: Path | None = None

    report_json: Path | None = None





def score_manifest(manifest: dict, session: ResearchSession) -> float:

    """越大越接近目标；达标最高。"""

    ev = manifest.get("evaluation") or {}

    if ev.get("passed"):

        return 1e9

    m = manifest.get("metrics") or {}

    ret = strategy_annual_return_pct(m)
    if ret is None:
        ret = m.get("annual_return_pct")

    dd = m.get("max_drawdown_pct")

    hints = parse_goal_text(session.goal_text)

    if ret is None:

        return -1e9

    s = float(ret)

    if hints.max_drawdown_max is not None and dd is not None and dd > hints.max_drawdown_max:

        s -= (float(dd) - hints.max_drawdown_max) * 2.0

    elif dd is not None:

        s -= float(dd) * 0.3

    if hints.annual_return_min is not None:

        s -= max(0.0, hints.annual_return_min - float(ret)) * 0.5

    return s





def run_research_loop(

    *,

    max_rounds: int | None = None,

    goal_text: str | None = None,

) -> LoopSummary:

    cfg = AgentResearchConfig.from_env()

    cfg.validate()

    n_rounds = max_rounds if max_rounds is not None else cfg.max_agent_rounds



    init = prepare_research_session(goal_text=goal_text)

    if init is None:

        raise RuntimeError("已取消会话（未输入目标）")

    session = init.session

    current_strategy = cfg.strategy_file.resolve()

    memory = ResearchMemory.create(session, current_strategy)

    memory.save()



    jq.SCREENSHOTS_DIR.mkdir(exist_ok=True)

    jq.RESULT_DIR.mkdir(exist_ok=True)

    jq.PROFILE_DIR.mkdir(exist_ok=True)

    REPORT_DIR.mkdir(exist_ok=True)



    username, password = jq.get_credentials()

    records: list[RoundRecord] = []

    stopped_reason = "max_rounds"

    loop_agent: LoopAgentSession | None = None

    agent_turn = 0



    print("阶段 3.6 research loop（Agent 多轮会话 + 实验记忆）")

    print(f"  目标：{session.goal_text}")

    print(f"  基线策略：{current_strategy.name}")

    print(f"  最大回测轮数：{n_rounds}")

    print(f"  会话记忆：{memory.path}\n")



    append_research_run(

        {

            "event": "loop_start",

            "phase": "3.6",

            "session_id": session.session_id,

            "goal_text": session.goal_text,

            "baseline_strategy": str(current_strategy),

            "max_rounds": n_rounds,

            "research_memory": str(memory.path),

        }

    )

    with sync_playwright() as p:

            context = jq.create_browser_context(p)

            page = context.pages[0] if context.pages else context.new_page()



            if not jq.ensure_logged_in(page, username, password):

                raise RuntimeError("登录失败")



            if not jq.go_to_strategy_backtest(page):

                raise RuntimeError("未能进入策略回测")



            if not jq.open_existing_strategy(page, cfg.joinquant_strategy_name):

                raise RuntimeError(f"未能打开策略「{cfg.joinquant_strategy_name}」")



            jq.dismiss_edit_prompt_if_present(page)

            editor_url = page.url

            backtest_params = jq.get_backtest_params()



            for round_idx in range(n_rounds):

                print(f"\n========== Loop 回测轮 {round_idx + 1}/{n_rounds} ==========")

                print(f"  策略：{current_strategy.name}")



                try:

                    bt = run_upload_backtest_on_page(

                        page,

                        joinquant_strategy_name=cfg.joinquant_strategy_name,

                        editor_url=editor_url,

                        backtest_params=backtest_params,

                        strategy_path=current_strategy,

                        session=session,

                        loop_round=round_idx,

                        configure_backtest=(round_idx == 0),

                    )

                except (PlaywrightError, RuntimeError, ValueError, SyntaxError) as exc:

                    append_research_run(

                        {

                            "event": "loop_backtest_error",

                            "session_id": session.session_id,

                            "loop_round": round_idx,

                            "error": str(exc),

                        }

                    )

                    raise RuntimeError(f"回测失败（轮 {round_idx + 1}）：{exc}") from exc



                if bt is None:

                    raise RuntimeError(f"回测失败（轮 {round_idx + 1}）：run_backtest 返回 None")



                sc = score_manifest(bt.manifest, session)

                record_backtest_round(

                    memory,

                    loop_round=round_idx,

                    strategy_path=current_strategy,

                    result_dir=bt.result_dir,

                    manifest=bt.manifest,

                    score=sc,

                )

                memory.save()

                emit_agent_task(bt.result_dir, session=session)



                rec = RoundRecord(

                    loop_round=round_idx,

                    strategy_file=current_strategy,

                    result_dir=bt.result_dir,

                    manifest=bt.manifest,

                    score=sc,

                )

                records.append(rec)



                metrics = bt.manifest.get("metrics") or {}

                print(

                    f"  结果：{bt.result_dir.name}  "

                    f"{format_metrics_line(metrics)}  "

                    f"passed={bt.manifest.get('passed')}"

                )



                if bt.manifest.get("passed"):

                    stopped_reason = "goal_passed"

                    print("\n已达标，结束循环。")

                    break



                if round_idx >= n_rounds - 1:

                    print("\n已达最大轮数，不再调用 Agent。")

                    break



                print("\n  调用 Cursor Agent（同会话 send）生成下一版策略…")

                try:

                    if loop_agent is None:

                        loop_agent = LoopAgentSession.open(name=f"research-{session.session_id[:20]}")

                        memory.cursor_agent_id = loop_agent.agent_id

                        memory.save()

                    agent_out = run_research_agent_turn(

                        loop_agent,

                        bt.agent_task_json,

                        memory,

                        agent_turn=agent_turn,

                        loop_round=round_idx,

                    )

                    agent_turn += 1

                    current_strategy = pick_next_strategy_path(agent_out)

                except Exception as exc:

                    append_research_run(

                        {

                            "event": "loop_agent_fatal",

                            "session_id": session.session_id,

                            "loop_round": round_idx,

                            "error": str(exc),

                        }

                    )

                    stopped_reason = "agent_failed"

                    raise RuntimeError(f"Agent 失败，整轮循环终止：{exc}") from exc



                validate_python_syntax(

                    current_strategy.read_text(encoding="utf-8"),

                    str(current_strategy),

                )

                print(f"  下一轮策略：{current_strategy.name}")

                append_research_run(

                    {

                        "event": "loop_next_strategy",

                        "session_id": session.session_id,

                        "loop_round": round_idx,

                        "next_strategy": str(current_strategy),

                        "agent_turn": agent_turn,

                    }

                )



            print("\n浏览器保持打开。按 Enter 关闭...")

            input()

            jq.safe_close_context(context)

    if not records:

        raise RuntimeError("未完成任何回测轮次")



    best = max(records, key=lambda r: r.score)

    summary = LoopSummary(

        session_id=session.session_id,

        goal_text=session.goal_text,

        rounds=records,

        best=best,

        stopped_reason=stopped_reason,

    )

    _write_loop_summary(session, summary)



    agent_synthesis: str | None = None

    if loop_agent is not None and agent_turn > 0:

        print("\n正在请求 Agent 撰写总体复盘（同一会话）…")

        try:

            agent_synthesis = loop_agent.send(build_final_synthesis_prompt(memory, summary)).text

        except Exception as exc:

            append_research_run(

                {

                    "event": "loop_report_agent_error",

                    "session_id": session.session_id,

                    "error": str(exc),

                }

            )

            print(f"（总体复盘 Agent 调用失败，仍写入脚本报告：{exc}）")

        finally:

            loop_agent.close()

            loop_agent = None



    md_path, json_path = write_session_report(

        summary=summary, memory=memory, agent_synthesis=agent_synthesis

    )

    summary.report_md = md_path

    summary.report_json = json_path



    append_research_run(

        {

            "event": "loop_complete",

            "phase": "3.6",

            "session_id": session.session_id,

            "stopped_reason": stopped_reason,

            "best_strategy": str(best.strategy_file),

            "best_result_dir": str(best.result_dir),

            "best_score": best.score,

            "report_md": str(md_path),

            "cursor_agent_id": memory.cursor_agent_id,

        }

    )

    return summary





def _write_loop_summary(session: ResearchSession, summary: LoopSummary) -> None:

    out_dir = RESEARCH_SESSIONS_DIR / session.session_id

    out_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {

        "session_id": summary.session_id,

        "goal_text": summary.goal_text,

        "stopped_reason": summary.stopped_reason,

        "best": {

            "strategy_file": str(summary.best.strategy_file),

            "strategy_name": summary.best.strategy_file.name,

            "result_dir": str(summary.best.result_dir),

            "run_id": summary.best.manifest.get("run_id"),

            "score": summary.best.score,

            "metrics": summary.best.manifest.get("metrics"),

            "passed": summary.best.manifest.get("passed"),

        },

        "rounds": [

            {

                "loop_round": r.loop_round,

                "strategy_file": str(r.strategy_file),

                "strategy_name": r.strategy_file.name,

                "result_dir": str(r.result_dir),

                "score": r.score,

                "passed": r.manifest.get("passed"),

                "metrics": r.manifest.get("metrics"),

            }

            for r in summary.rounds

        ],

        "report_md": str(summary.report_md) if summary.report_md else None,

        "report_json": str(summary.report_json) if summary.report_json else None,

    }

    path = out_dir / "loop_summary.json"

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")





def print_loop_summary(summary: LoopSummary) -> None:

    best = summary.best

    bm = best.manifest.get("metrics") or {}

    print("\n" + "=" * 52)

    print("阶段 3.6 循环结束")

    print(f"  停止原因：{summary.stopped_reason}")

    print(f"  研究目标：{summary.goal_text}")

    print("\n  【最接近目标的策略版本】")

    print(f"    代码文件名：{best.strategy_file.name}")

    print(f"    完整路径：{best.strategy_file}")

    print(f"    回测结果目录：{best.result_dir}")

    print(

        f"    指标：{format_metrics_line(bm)}  passed={best.manifest.get('passed')}"

    )

    if summary.report_md:

        print(f"\n  【总体复盘报告】\n    {summary.report_md}")

    print("\n  各轮概览：")

    for r in summary.rounds:

        m = r.manifest.get("metrics") or {}

        print(

            f"    轮{r.loop_round + 1} {r.strategy_file.name} → {r.result_dir.name} "

            f"{format_metrics_line(m)}"

        )

    print("=" * 52)


