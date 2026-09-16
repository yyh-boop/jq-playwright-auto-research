# -*- coding: utf-8 -*-
"""阶段 3.6：session 结束后的总体复盘报告（report/ 目录）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataclasses import asdict

from typing import TYPE_CHECKING

from autoresearch.metrics_display import (
    format_metrics_line,
    max_drawdown_pct,
    strategy_annual_return_pct,
    strategy_return_pct,
)
from autoresearch.research_memory import ResearchMemory, render_memory_for_prompt
from autoresearch.research_paths import BASE_DIR, REPORT_DIR

if TYPE_CHECKING:
    from autoresearch.research_loop_runner import LoopSummary


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def write_session_report(
    *,
    summary: "LoopSummary",
    memory: ResearchMemory,
    agent_synthesis: str | None = None,
) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = REPORT_DIR / summary.session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    best = summary.best
    payload: dict[str, Any] = {
        "schema_version": 1,
        "session_id": summary.session_id,
        "goal_text": summary.goal_text,
        "stopped_reason": summary.stopped_reason,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_strategy": {
            "name": best.strategy_file.name,
            "path": str(best.strategy_file),
            "result_dir": str(best.result_dir),
            "metrics": best.manifest.get("metrics"),
            "score": best.score,
            "passed": best.manifest.get("passed"),
        },
        "strategies": [],
        "promising_directions": [asdict(d) for d in memory.promising_directions],
        "abandoned_directions": [asdict(d) for d in memory.abandoned_directions],
        "agent_notes": list(memory.agent_notes),
        "cursor_agent_id": memory.cursor_agent_id,
        "research_memory": _rel(memory.path),
    }

    for r in summary.rounds:
        m = r.manifest.get("metrics") or {}
        mem_round = next((x for x in memory.rounds if x.loop_round == r.loop_round), None)
        payload["strategies"].append(
            {
                "loop_round": r.loop_round,
                "name": r.strategy_file.name,
                "path": str(r.strategy_file),
                "result_dir": str(r.result_dir),
                "strategy_return_pct": strategy_return_pct(m),
                "strategy_annual_return_pct": strategy_annual_return_pct(m),
                "max_drawdown_pct": max_drawdown_pct(m),
                "score": r.score,
                "passed": r.manifest.get("passed"),
                "direction_slug": mem_round.direction_slug if mem_round else None,
                "auto_tags": mem_round.auto_tags if mem_round else [],
                "agent_insight": mem_round.agent_insight if mem_round else None,
            }
        )

    json_path = out_dir / "research_report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = _render_markdown(summary, memory, agent_synthesis, payload)
    md_path = out_dir / "research_report.md"
    md_path.write_text(md, encoding="utf-8")
    return md_path, json_path


def _render_markdown(
    summary: "LoopSummary",
    memory: ResearchMemory,
    agent_synthesis: str | None,
    payload: dict[str, Any],
) -> str:
    best = summary.best
    bm = best.manifest.get("metrics") or {}
    lines = [
        f"# Research 复盘报告",
        "",
        f"- **Session**: `{summary.session_id}`",
        f"- **目标**: {summary.goal_text}",
        f"- **停止原因**: {summary.stopped_reason}",
        f"- **最优策略**: `{best.strategy_file.name}`",
        f"- **最优指标（与聚宽收益概述一致）**: {format_metrics_line(bm)}",
        "",
        "## 各策略概览",
        "",
        "| 轮次 | 策略文件 | 方向 | 策略收益% | 策略年化% | 最大回撤% | score | 标签 |",
        "|------|----------|------|-----------|-----------|-----------|-------|------|",
    ]
    for item in payload["strategies"]:
        tags = ",".join(item.get("auto_tags") or [])
        lines.append(
            f"| {item['loop_round'] + 1} | `{item['name']}` | {item.get('direction_slug') or '-'} | "
            f"{item.get('strategy_return_pct')} | {item.get('strategy_annual_return_pct')} | "
            f"{item.get('max_drawdown_pct')} | {item.get('score')} | {tags} |"
        )

    lines.append("\n## 各策略说明（简要）\n")
    for item in payload["strategies"]:
        insight = item.get("agent_insight") or "（无 Agent 单行摘要）"
        lines.append(f"### 轮{item['loop_round'] + 1} `{item['name']}`\n")
        lines.append(f"- 方向 slug：`{item.get('direction_slug')}`")
        lines.append(f"- 结果目录：`{item.get('result_dir')}`")
        lines.append(
            f"- 概述指标：策略收益 **{item.get('strategy_return_pct')}%** · "
            f"策略年化 **{item.get('strategy_annual_return_pct')}%** · "
            f"最大回撤 **{item.get('max_drawdown_pct')}%**"
        )
        lines.append(f"- Agent/脚本备注：{insight}\n")

    if memory.promising_directions:
        lines.append("## 值得保留的方向（promising）\n")
        for d in memory.promising_directions:
            lines.append(f"- **{d.direction}**（{d.source}，轮{(d.loop_round or 0) + 1}）：{d.reason}")

    if memory.abandoned_directions:
        lines.append("\n## 已降权/避免的方向（abandoned）\n")
        for d in memory.abandoned_directions:
            lines.append(f"- **{d.direction}**（{d.source}，轮{(d.loop_round or 0) + 1}）：{d.reason}")

    if agent_synthesis:
        lines.append("\n## Agent 总体复盘\n")
        lines.append(agent_synthesis.strip())

    lines.append(f"\n---\n详细 JSON：`report/{summary.session_id}/research_report.json`\n")
    return "\n".join(lines)


def build_final_synthesis_prompt(memory: ResearchMemory, summary: "LoopSummary") -> str:
    best = summary.best
    bm = best.manifest.get("metrics") or {}
    return (
        "本会话所有回测与改码已结束。请基于你在本会话中的全部上下文，"
        "写一份**中文总体复盘**（无需再改代码），包含：\n"
        "1. 目标与 baseline 对比结论\n"
        "2. 各策略版本尝试脉络（哪些有效、哪些无效）\n"
        "3. 你认为最有价值的 2～4 个改动方向及原因\n"
        "4. 若继续研究，下一步建议（1 段）\n"
        "不要输出 NEW_STRATEGY_FILE。可选末尾：`RESEARCH_INSIGHT: 一句话`。\n\n"
        f"当前最优：`{best.strategy_file.name}` {format_metrics_line(bm)}\n\n"
        + render_memory_for_prompt(memory)
    )
