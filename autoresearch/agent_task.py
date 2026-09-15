# -*- coding: utf-8 -*-
"""
阶段 3.3：生成 Agent 入口文件 agent_task.md / agent_task.json（manifest 路径 + 系统 prompt，不内嵌整份源码）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoresearch.agent_system_prompt import AGENT_SYSTEM_PROMPT
from autoresearch.research_paths import BASE_DIR, RESEARCH_RUNS_JSONL, RESEARCH_SESSIONS_DIR
from autoresearch.research_session import ResearchSession
from autoresearch.strategy_versions import original_path_for


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(path.resolve())


def _load_manifest(result_dir: Path) -> dict[str, Any]:
    p = result_dir / "run_manifest.json"
    if not p.is_file():
        raise FileNotFoundError(f"未找到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _session_path_from_manifest(manifest: dict[str, Any]) -> Path | None:
    extra = manifest.get("extra") or {}
    meta = extra.get("trial_meta") or {}
    sid = meta.get("session_id")
    if not sid:
        return None
    p = RESEARCH_SESSIONS_DIR / str(sid) / "session.json"
    return p if p.is_file() else None


def _resolve_artifact_paths(manifest: dict[str, Any], result_dir: Path) -> dict[str, str | None]:
    paths = manifest.get("paths") or {}
    out: dict[str, str | None] = {}
    for key, val in paths.items():
        if not val:
            out[key] = None
            continue
        candidate = result_dir.parent / str(val)
        if candidate.is_file():
            out[key] = _rel(candidate)
        else:
            inner = result_dir / Path(str(val)).name
            out[key] = _rel(inner) if inner.is_file() else str(val)
    return out


@dataclass(frozen=True)
class AgentTaskPaths:
    markdown: Path
    json_file: Path
    result_dir: Path


def build_agent_task_payload(
    result_dir: Path,
    *,
    session: ResearchSession | None = None,
) -> dict[str, Any]:
    result_dir = result_dir.resolve()
    manifest = _load_manifest(result_dir)
    extra = manifest.get("extra") or {}
    trial_meta = extra.get("trial_meta") or {}

    session_path = _session_path_from_manifest(manifest)
    if session is None and session_path:
        session = ResearchSession.load(session_path)

    strategy_file: Path | None = None
    raw_sf = trial_meta.get("local_strategy_file")
    if raw_sf:
        strategy_file = Path(str(raw_sf))
    elif session:
        strategy_file = Path(session.strategy_file)

    original_file: str | None = None
    if strategy_file and strategy_file.is_file():
        orig = original_path_for(strategy_file)
        if orig.is_file():
            original_file = _rel(orig)

    artifacts = _resolve_artifact_paths(manifest, result_dir)
    metrics = manifest.get("metrics") or {}
    evaluation = manifest.get("evaluation") or {}
    goal_text = trial_meta.get("goal_text") or (session.goal_text if session else None)

    return {
        "schema_version": 1,
        "run_id": manifest.get("run_id"),
        "workspace_root": _rel(BASE_DIR),
        "system_prompt": AGENT_SYSTEM_PROMPT,
        "paths_to_read": {
            "run_manifest": _rel(result_dir / "run_manifest.json"),
            "session_json": _rel(session_path) if session_path else None,
            "strategy_current": _rel(strategy_file) if strategy_file and strategy_file.is_file() else None,
            "strategy_original": original_file,
            "research_runs_jsonl": _rel(RESEARCH_RUNS_JSONL) if RESEARCH_RUNS_JSONL.is_file() else None,
            "artifacts": artifacts,
        },
        "goal_text": goal_text,
        "metrics_summary": {
            "has_metrics": bool(metrics),
            "annual_return_pct": metrics.get("annual_return_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "passed": manifest.get("passed"),
            "gaps": evaluation.get("gaps"),
        },
        "agent_instructions_if_metrics_empty": (
            "manifest.metrics 为空：请打开 paths.artifacts.performance_metrics_xlsx（若存在）；"
            "若 artifacts 均为 null，说明本轮未导出 Excel/截图，请主要依据策略源码与 goal_text 提出改动，"
            "并建议用户将 playwright练习.py 中 SAVE_BACKTEST_ARTIFACTS 设为 True 后重跑。"
        ),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    paths = payload["paths_to_read"]
    lines = [
        "# Agent 任务",
        "",
        f"- **run_id**: `{payload.get('run_id')}`",
        f"- **研究目标**: {payload.get('goal_text') or '（见 manifest trial_meta）'}",
        "",
        "## 系统约束",
        "",
        payload["system_prompt"].strip(),
        "",
        "## 请先打开这些路径（相对仓库根）",
        "",
        f"- manifest: `{paths['run_manifest']}`",
    ]
    if paths.get("session_json"):
        lines.append(f"- session: `{paths['session_json']}`")
    if paths.get("strategy_current"):
        lines.append(f"- 当前策略: `{paths['strategy_current']}`")
    if paths.get("strategy_original"):
        lines.append(f"- 原始备份: `{paths['strategy_original']}`")
    if paths.get("research_runs_jsonl"):
        lines.append(f"- 实验日志: `{paths['research_runs_jsonl']}`（可选，最近几条）")
    lines.extend(["", "### 回测产物（若已导出）", ""])
    arts = paths.get("artifacts") or {}
    for k, v in arts.items():
        lines.append(f"- {k}: `{v}`" if v else f"- {k}: （未生成）")
    ms = payload.get("metrics_summary") or {}
    lines.extend(
        [
            "",
            "## 指标摘要（来自 manifest，可能为空）",
            "",
            f"- has_metrics: {ms.get('has_metrics')}",
            f"- annual_return_pct: {ms.get('annual_return_pct')}",
            f"- max_drawdown_pct: {ms.get('max_drawdown_pct')}",
            f"- passed: {ms.get('passed')}",
            f"- gaps: {ms.get('gaps')}",
            "",
            "## metrics 为空时",
            "",
            payload.get("agent_instructions_if_metrics_empty", ""),
            "",
            "## 完成后",
            "",
            "在 `strategies/` 新建改进版 `.py`，不要改 `_original.py`；告知新文件名与改动方向。",
            "",
        ]
    )
    return "\n".join(lines)


def emit_agent_task(
    result_dir: Path,
    *,
    session: ResearchSession | None = None,
    copy_to_session: bool = True,
) -> AgentTaskPaths:
    """写入 result/<run_id>/agent_task.md|.json，并可选复制到 session 目录。"""
    payload = build_agent_task_payload(result_dir, session=session)
    md = _render_markdown(payload)
    result_dir = result_dir.resolve()
    md_path = result_dir / "agent_task.md"
    json_path = result_dir / "agent_task.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    session_path = _session_path_from_manifest(_load_manifest(result_dir))
    if copy_to_session and session_path:
        session_dir = session_path.parent
        (session_dir / "agent_task_latest.md").write_text(md, encoding="utf-8")
        (session_dir / "agent_task_latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return AgentTaskPaths(markdown=md_path, json_file=json_path, result_dir=result_dir)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="阶段 3.3：从 result 目录生成 agent_task.md")
    parser.add_argument("result_dir", type=Path, help="如 result/ETF动量 或 result/ETF动量_收紧回撤")
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="可选 session.json，补全 goal 等",
    )
    args = parser.parse_args(argv)

    rd = args.result_dir
    if not rd.is_absolute():
        rd = BASE_DIR / rd
    session = ResearchSession.load(args.session) if args.session else None
    try:
        out = emit_agent_task(rd, session=session)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"已写入：{out.markdown}")
    print(f"已写入：{out.json_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
