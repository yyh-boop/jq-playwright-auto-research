# -*- coding: utf-8 -*-
"""阶段 3.4：读取 agent_task.json，调用 Cursor Agent 改 strategies/。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.cursor_client import run_local_agent_prompt
from autoresearch.research_config import AgentResearchConfig
from autoresearch.research_log import append_research_run
from autoresearch.research_paths import BASE_DIR, STRATEGIES_DIR
from autoresearch.strategy_versions import validate_python_syntax

_NEW_FILE_RE = re.compile(
    r"NEW_STRATEGY_FILE:\s*([^\s\n]+\.py)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResearchAgentOutcome:
    result_dir: Path
    agent_task_json: Path
    response_path: Path
    status: str | None
    response_text: str
    new_strategy_files: tuple[Path, ...]
    parsed_new_file: Path | None


def load_agent_task_payload(path: Path) -> dict[str, Any]:
    p = path.resolve()
    if not p.is_file():
        raise FileNotFoundError(f"未找到 agent_task：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


def build_agent_prompt_from_payload(payload: dict[str, Any]) -> str:
    """组合 system_prompt + 路径清单 + 执行指令（与 agent_task.md 一致）。"""
    paths = payload.get("paths_to_read") or {}
    ms = payload.get("metrics_summary") or {}
    lines = [
        payload.get("system_prompt", "").strip(),
        "",
        "---",
        f"工作区根目录（相对路径均相对此目录）：{payload.get('workspace_root', '.')}",
        f"run_id: {payload.get('run_id')}",
        f"研究目标: {payload.get('goal_text')}",
        "",
        "请按顺序阅读并分析：",
        f"1. {paths.get('run_manifest')}",
    ]
    if paths.get("session_json"):
        lines.append(f"2. {paths.get('session_json')}")
    if paths.get("strategy_current"):
        lines.append(f"- 当前策略: {paths.get('strategy_current')}")
    if paths.get("strategy_original"):
        lines.append(f"- 原始备份: {paths.get('strategy_original')}")
    if paths.get("research_runs_jsonl"):
        lines.append(f"- 可选实验日志: {paths.get('research_runs_jsonl')}")
    arts = paths.get("artifacts") or {}
    if any(arts.values()):
        lines.append("回测产物：")
        for k, v in arts.items():
            if v:
                lines.append(f"  - {k}: {v}")
    lines.extend(
        [
            "",
            f"指标摘要: has_metrics={ms.get('has_metrics')} "
            f"annual_return_pct={ms.get('annual_return_pct')} "
            f"max_drawdown_pct={ms.get('max_drawdown_pct')} passed={ms.get('passed')} gaps={ms.get('gaps')}",
            "",
            payload.get("agent_instructions_if_metrics_empty", ""),
            "",
            "## 执行",
            "在 strategies/ 下**新建**一份改进版 .py（勿改 *_original.py）。",
            "写完后在回复**最后一行**严格输出：",
            "NEW_STRATEGY_FILE: strategies/你的文件名.py",
            "",
            "并简要说明改动方向与关键逻辑变更。",
        ]
    )
    return "\n".join(lines)


def _strategy_snapshot() -> dict[str, float]:
    out: dict[str, float] = {}
    if not STRATEGIES_DIR.is_dir():
        return out
    for p in STRATEGIES_DIR.glob("*.py"):
        out[str(p.resolve())] = p.stat().st_mtime
    return out


def _new_files(before: dict[str, float], after: dict[str, float]) -> list[Path]:
    added: list[Path] = []
    for path, mtime in after.items():
        if path not in before or before[path] < mtime - 1e-6:
            if path not in before:
                added.append(Path(path))
    return sorted(added, key=lambda p: p.stat().st_mtime)


def _parse_new_file_line(text: str) -> Path | None:
    m = _NEW_FILE_RE.search(text)
    if not m:
        return None
    rel = m.group(1).replace("\\", "/")
    p = (BASE_DIR / rel).resolve()
    return p if p.is_file() else None


def run_research_agent(
    agent_task_path: Path,
    *,
    max_retries: int | None = None,
) -> ResearchAgentOutcome:
    cfg = AgentResearchConfig.from_env()
    retries = max_retries if max_retries is not None else cfg.agent_retries
    task_path = agent_task_path.resolve()
    payload = load_agent_task_payload(task_path)
    result_dir = task_path.parent
    prompt = build_agent_prompt_from_payload(payload)

    before = _strategy_snapshot()
    last_error: Exception | None = None
    result = None

    for attempt in range(max(1, retries + 1)):
        try:
            result = run_local_agent_prompt(prompt)
            if result.status and result.status.lower() in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Agent status={result.status}")
            break
        except Exception as exc:
            last_error = exc
            append_research_run(
                {
                    "event": "agent_run_error",
                    "run_id": payload.get("run_id"),
                    "attempt": attempt + 1,
                    "error": str(exc),
                }
            )
            if attempt >= retries:
                raise RuntimeError(f"Agent 调用失败（已重试 {retries} 次）: {exc}") from exc

    assert result is not None
    after = _strategy_snapshot()
    new_files = tuple(_new_files(before, after))
    parsed = _parse_new_file_line(result.text)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    response_path = result_dir / f"agent_response_{ts}.txt"
    response_path.write_text(result.text, encoding="utf-8")
    (result_dir / "agent_response_latest.txt").write_text(result.text, encoding="utf-8")

    validated: list[str] = []
    for p in new_files:
        try:
            validate_python_syntax(p.read_text(encoding="utf-8"), str(p))
            validated.append(str(p))
        except SyntaxError as exc:
            append_research_run(
                {
                    "event": "agent_new_file_syntax_error",
                    "path": str(p),
                    "error": str(exc),
                }
            )

    record = {
        "event": "agent_run_complete",
        "run_id": payload.get("run_id"),
        "result_dir": str(result_dir),
        "agent_task": str(task_path),
        "status": result.status,
        "response_file": str(response_path),
        "new_strategy_files": [str(p) for p in new_files],
        "parsed_new_strategy_file": str(parsed) if parsed else None,
        "syntax_ok_files": validated,
    }
    append_research_run(record)

    return ResearchAgentOutcome(
        result_dir=result_dir,
        agent_task_json=task_path,
        response_path=response_path,
        status=result.status,
        response_text=result.text,
        new_strategy_files=new_files,
        parsed_new_file=parsed,
    )


def pick_next_strategy_path(outcome: ResearchAgentOutcome) -> Path:
    if outcome.parsed_new_file is not None and outcome.parsed_new_file.is_file():
        return outcome.parsed_new_file.resolve()
    if outcome.new_strategy_files:
        return outcome.new_strategy_files[-1].resolve()
    raise RuntimeError(
        "Agent 未在 strategies/ 下产生新的 .py 文件（或未输出 NEW_STRATEGY_FILE 行），循环终止"
    )


def resolve_agent_task_path(*, result_dir: Path | None, task_json: Path | None) -> Path:
    if task_json is not None:
        p = task_json if task_json.is_absolute() else BASE_DIR / task_json
        return p.resolve()
    if result_dir is None:
        raise ValueError("请指定 --result 或 --task")
    rd = result_dir if result_dir.is_absolute() else BASE_DIR / result_dir
    rd = rd.resolve()
    candidate = rd / "agent_task.json"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"未找到 {candidate}。请先跑 research_start 或 build_agent_task.py {rd.name}"
        )
    return candidate
