# -*- coding: utf-8 -*-
"""单次 research 会话：GUI 输入的目标与元数据（不写 .env）。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.research_paths import RESEARCH_SESSIONS_DIR, SCHEMA_VERSION_RESEARCH


@dataclass
class ResearchSession:
    schema_version: int
    session_id: str
    created_at: str
    goal_text: str
    strategy_file: str
    joinquant_strategy_name: str
    max_agent_rounds: int
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        goal_text: str,
        strategy_file: Path,
        joinquant_strategy_name: str,
        max_agent_rounds: int,
        extra: dict[str, Any] | None = None,
    ) -> "ResearchSession":
        goal_text = goal_text.strip()
        if not goal_text:
            raise ValueError("研究目标不能为空")
        return cls(
            schema_version=SCHEMA_VERSION_RESEARCH,
            session_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_"
            + uuid.uuid4().hex[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            goal_text=goal_text,
            strategy_file=str(strategy_file.resolve()),
            joinquant_strategy_name=joinquant_strategy_name,
            max_agent_rounds=max_agent_rounds,
            extra=extra or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, directory: Path | None = None) -> Path:
        out_dir = directory or (RESEARCH_SESSIONS_DIR / self.session_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "session.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "ResearchSession":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            session_id=str(data["session_id"]),
            created_at=str(data["created_at"]),
            goal_text=str(data["goal_text"]),
            strategy_file=str(data["strategy_file"]),
            joinquant_strategy_name=str(data["joinquant_strategy_name"]),
            max_agent_rounds=int(data["max_agent_rounds"]),
            extra=dict(data.get("extra") or {}),
        )
