# -*- coding: utf-8 -*-
"""experiments/research_runs.jsonl — 阶段 3 每轮回测/Agent 记录。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.research_paths import RESEARCH_RUNS_JSONL


def append_research_run(record: dict[str, Any], path: Path | None = None) -> Path:
    out = path or RESEARCH_RUNS_JSONL
    out.parent.mkdir(parents=True, exist_ok=True)
    if "logged_at" not in record:
        record = {**record, "logged_at": datetime.now(timezone.utc).isoformat()}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out
