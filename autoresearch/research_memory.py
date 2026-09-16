# -*- coding: utf-8 -*-
"""阶段 3.6：单次 research session 实验记忆（供 Agent 多轮 send 与复盘）。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.goal_prompt import ParsedGoalHints, parse_goal_text
from autoresearch.research_paths import RESEARCH_SESSIONS_DIR
from autoresearch.research_session import ResearchSession

MEMORY_FILENAME = "research_memory.json"
_SCHEMA = 1

_INSIGHT_RE = re.compile(r"^RESEARCH_INSIGHT:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_MEMORY_JSON_RE = re.compile(
    r"MEMORY_UPDATE_JSON:\s*(\{.*?\})",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class DirectionNote:
    direction: str
    verdict: str  # promising | abandoned | neutral
    reason: str
    loop_round: int | None = None
    source: str = "auto"  # auto | agent


@dataclass
class MemoryRound:
    loop_round: int
    strategy_name: str
    strategy_file: str
    result_dir: str
    direction_slug: str
    metrics: dict[str, Any]
    score: float
    passed: bool
    delta_return_vs_prev: float | None = None
    delta_drawdown_vs_prev: float | None = None
    delta_return_vs_baseline: float | None = None
    delta_drawdown_vs_baseline: float | None = None
    auto_tags: list[str] = field(default_factory=list)
    agent_insight: str | None = None


@dataclass
class ResearchMemory:
    schema_version: int
    session_id: str
    goal_text: str
    baseline_strategy: str
    baseline_stem: str
    created_at: str
    updated_at: str
    rounds: list[MemoryRound] = field(default_factory=list)
    promising_directions: list[DirectionNote] = field(default_factory=list)
    abandoned_directions: list[DirectionNote] = field(default_factory=list)
    agent_notes: list[str] = field(default_factory=list)
    cursor_agent_id: str | None = None

    @classmethod
    def create(cls, session: ResearchSession, baseline_strategy: Path) -> "ResearchMemory":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            schema_version=_SCHEMA,
            session_id=session.session_id,
            goal_text=session.goal_text,
            baseline_strategy=str(baseline_strategy.resolve()),
            baseline_stem=baseline_strategy.stem,
            created_at=now,
            updated_at=now,
        )

    @property
    def path(self) -> Path:
        return RESEARCH_SESSIONS_DIR / self.session_id / MEMORY_FILENAME

    def save(self) -> Path:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    @classmethod
    def load(cls, path: Path) -> "ResearchMemory":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "goal_text": self.goal_text,
            "baseline_strategy": self.baseline_strategy,
            "baseline_stem": self.baseline_stem,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cursor_agent_id": self.cursor_agent_id,
            "rounds": [asdict(r) for r in self.rounds],
            "promising_directions": [asdict(d) for d in self.promising_directions],
            "abandoned_directions": [asdict(d) for d in self.abandoned_directions],
            "agent_notes": list(self.agent_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchMemory":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            session_id=str(data["session_id"]),
            goal_text=str(data["goal_text"]),
            baseline_strategy=str(data["baseline_strategy"]),
            baseline_stem=str(data["baseline_stem"]),
            created_at=str(data["created_at"]),
            updated_at=str(data.get("updated_at", data["created_at"])),
            cursor_agent_id=data.get("cursor_agent_id"),
            rounds=[MemoryRound(**item) for item in (data.get("rounds") or [])],
            promising_directions=[
                DirectionNote(**item) for item in (data.get("promising_directions") or [])
            ],
            abandoned_directions=[
                DirectionNote(**item) for item in (data.get("abandoned_directions") or [])
            ],
            agent_notes=list(data.get("agent_notes") or []),
        )


def direction_slug_from_path(strategy_path: Path, baseline_stem: str) -> str:
    stem = strategy_path.stem
    if stem == baseline_stem:
        return "baseline"
    prefix = f"{baseline_stem}_"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return stem


def _fmetric(metrics: dict[str, Any], key: str) -> float | None:
    v = metrics.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _auto_tag_round(
    *,
    hints: ParsedGoalHints,
    ret: float | None,
    dd: float | None,
    d_ret_prev: float | None,
    d_dd_prev: float | None,
    d_ret_base: float | None,
    d_dd_base: float | None,
) -> list[str]:
    tags: list[str] = []
    if d_ret_prev is not None and d_ret_prev > 0.5:
        tags.append("return_up_vs_prev")
    if d_ret_prev is not None and d_ret_prev < -2.0:
        tags.append("return_down_vs_prev")
    if d_dd_prev is not None and d_dd_prev < -0.3:
        tags.append("drawdown_down_vs_prev")
    if d_dd_prev is not None and d_dd_prev > 0.5:
        tags.append("drawdown_up_vs_prev")
    if d_ret_base is not None and d_ret_base > 0.5:
        tags.append("return_up_vs_baseline")
    if d_dd_base is not None and d_dd_base < -0.3:
        tags.append("drawdown_down_vs_baseline")
    if hints.annual_return_min is not None and ret is not None and ret >= hints.annual_return_min:
        tags.append("meets_return_goal")
    if hints.max_drawdown_max is not None and dd is not None and dd <= hints.max_drawdown_max:
        tags.append("meets_drawdown_goal")
    if not tags:
        tags.append("neutral")
    return tags


def _update_direction_lists(
    memory: ResearchMemory,
    *,
    loop_round: int,
    direction: str,
    tags: list[str],
) -> None:
    if direction in ("baseline", ""):
        return

    def _has(direction: str, verdict: str) -> bool:
        pool = memory.promising_directions if verdict == "promising" else memory.abandoned_directions
        return any(d.direction == direction and d.verdict == verdict for d in pool)

    if "return_down_vs_prev" in tags and "drawdown_down_vs_prev" not in tags:
        reason = "相对上一轮收益明显下降且回撤未同步改善"
        if not _has(direction, "abandoned"):
            memory.abandoned_directions.append(
                DirectionNote(
                    direction=direction,
                    verdict="abandoned",
                    reason=reason,
                    loop_round=loop_round,
                    source="auto",
                )
            )
    if "drawdown_down_vs_prev" in tags or "drawdown_down_vs_baseline" in tags:
        reason = "回撤改善，值得沿该方向继续微调"
        if not _has(direction, "promising"):
            memory.promising_directions.append(
                DirectionNote(
                    direction=direction,
                    verdict="promising",
                    reason=reason,
                    loop_round=loop_round,
                    source="auto",
                )
            )
    if "return_up_vs_prev" in tags or "return_up_vs_baseline" in tags:
        reason = "收益提升"
        if not _has(direction, "promising"):
            memory.promising_directions.append(
                DirectionNote(
                    direction=direction,
                    verdict="promising",
                    reason=reason,
                    loop_round=loop_round,
                    source="auto",
                )
            )


def record_backtest_round(
    memory: ResearchMemory,
    *,
    loop_round: int,
    strategy_path: Path,
    result_dir: Path,
    manifest: dict[str, Any],
    score: float,
) -> MemoryRound:
    hints = parse_goal_text(memory.goal_text)
    metrics = dict(manifest.get("metrics") or {})
    ret = (
        _fmetric(metrics, "strategy_annual_return_pct")
        or _fmetric(metrics, "strategy_return_pct")
        or _fmetric(metrics, "annual_return_pct")
    )
    dd = _fmetric(metrics, "max_drawdown_pct")
    direction = direction_slug_from_path(strategy_path, memory.baseline_stem)

    prev = memory.rounds[-1] if memory.rounds else None
    base = memory.rounds[0] if memory.rounds else None

    def _delta(cur: float | None, other_metrics: dict[str, Any] | None, key: str) -> float | None:
        if cur is None or not other_metrics:
            return None
        o = _fmetric(other_metrics, key)
        if o is None:
            return None
        return cur - o

    def _ret_from(m: dict[str, Any] | None) -> float | None:
        if not m:
            return None
        return (
            _fmetric(m, "strategy_annual_return_pct")
            or _fmetric(m, "strategy_return_pct")
            or _fmetric(m, "annual_return_pct")
        )

    prev_m = prev.metrics if prev else None
    base_m = base.metrics if base and loop_round > 0 else metrics
    d_ret_prev = (ret - _ret_from(prev_m)) if ret is not None and _ret_from(prev_m) is not None else None
    d_dd_prev = _delta(dd, prev_m, "max_drawdown_pct")
    d_ret_base = (ret - _ret_from(base_m)) if ret is not None and loop_round > 0 and _ret_from(base_m) is not None else None
    d_dd_base = _delta(dd, base.metrics if base and loop_round > 0 else metrics, "max_drawdown_pct")
    if loop_round == 0:
        d_ret_base = None
        d_dd_base = None

    tags = _auto_tag_round(
        hints=hints,
        ret=ret,
        dd=dd,
        d_ret_prev=d_ret_prev,
        d_dd_prev=d_dd_prev,
        d_ret_base=d_ret_base if loop_round > 0 else None,
        d_dd_base=d_dd_base if loop_round > 0 else None,
    )

    rec = MemoryRound(
        loop_round=loop_round,
        strategy_name=strategy_path.name,
        strategy_file=str(strategy_path.resolve()),
        result_dir=str(result_dir.resolve()),
        direction_slug=direction,
        metrics=metrics,
        score=score,
        passed=bool(manifest.get("passed")),
        delta_return_vs_prev=d_ret_prev,
        delta_drawdown_vs_prev=d_dd_prev,
        delta_return_vs_baseline=d_ret_base if loop_round > 0 else None,
        delta_drawdown_vs_baseline=d_dd_base if loop_round > 0 else None,
        auto_tags=tags,
    )
    memory.rounds.append(rec)
    _update_direction_lists(memory, loop_round=loop_round, direction=direction, tags=tags)
    return rec


def ingest_agent_response(memory: ResearchMemory, response_text: str, *, loop_round: int) -> None:
    m = _INSIGHT_RE.search(response_text)
    if m:
        insight = m.group(1).strip()
        if insight and insight not in memory.agent_notes:
            memory.agent_notes.append(insight)
        if memory.rounds:
            memory.rounds[-1].agent_insight = insight

    for block in _MEMORY_JSON_RE.finditer(response_text):
        try:
            obj = json.loads(block.group(1))
        except json.JSONDecodeError:
            continue
        direction = str(obj.get("direction", "")).strip()
        verdict = str(obj.get("verdict", "neutral")).strip().lower()
        reason = str(obj.get("reason", "")).strip() or "（Agent 未说明）"
        if not direction:
            continue
        note = DirectionNote(
            direction=direction,
            verdict=verdict if verdict in ("promising", "abandoned", "neutral") else "neutral",
            reason=reason,
            loop_round=loop_round,
            source="agent",
        )
        if note.verdict == "promising":
            memory.promising_directions.append(note)
        elif note.verdict == "abandoned":
            memory.abandoned_directions.append(note)


def render_memory_for_prompt(memory: ResearchMemory) -> str:
    lines = [
        "## 本会话实验记忆（research_memory.json，请严格遵守）",
        f"- 研究目标：{memory.goal_text}",
        f"- Baseline：{Path(memory.baseline_strategy).name}（勿无故退回 baseline 重开分支，除非记忆表明当前方向已放弃）",
        "",
        "### 各轮回测（脚本记录）",
    ]
    if not memory.rounds:
        lines.append("（尚无回测记录）")
    for r in memory.rounds:
        lines.append(
            f"- 轮{r.loop_round + 1} `{r.strategy_name}` 方向=`{r.direction_slug}` "
            f"策略收益≈{r.metrics.get('strategy_return_pct')}% "
            f"策略年化≈{r.metrics.get('strategy_annual_return_pct')}% "
            f"回撤≈{r.metrics.get('max_drawdown_pct')}% "
            f"score={r.score:.2f} tags={','.join(r.auto_tags)}"
        )
        if r.agent_insight:
            lines.append(f"  - Agent 备注：{r.agent_insight}")

    if memory.promising_directions:
        lines.append("\n### 值得深挖的方向（promising）")
        for d in memory.promising_directions[-8:]:
            lines.append(f"- `{d.direction}`（{d.source}）：{d.reason}")

    if memory.abandoned_directions:
        lines.append("\n### 建议避免/降权的方向（abandoned）")
        for d in memory.abandoned_directions[-8:]:
            lines.append(f"- `{d.direction}`（{d.source}）：{d.reason}")

    if memory.agent_notes:
        lines.append("\n### Agent 历史要点")
        for n in memory.agent_notes[-6:]:
            lines.append(f"- {n}")

    lines.extend(
        [
            "",
            "### 你的策略",
            "1. 若 promising 方向存在且近期 metrics 有改善，请在**当前 strategy_current** 基础上小步深挖 1～2 轮。",
            "2. 若同一方向连续 2 轮无明显靠近目标（score/收益/回撤），请换方向，并将旧方向标记为 abandoned。",
            "3. 回复末尾可选：`RESEARCH_INSIGHT: 一句话`；可选：`MEMORY_UPDATE_JSON: {\"direction\":\"…\",\"verdict\":\"promising|abandoned\",\"reason\":\"…\"}`",
        ]
    )
    return "\n".join(lines)
