# -*- coding: utf-8 -*-
"""experiments/experiments.jsonl 追加写入。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoresearch.orchestrator_config import EXPERIMENTS_DIR, EXPERIMENTS_JSONL


def append_experiment(record: dict[str, Any], path: Path | None = None) -> Path:
    out = path or EXPERIMENTS_JSONL
    out.parent.mkdir(parents=True, exist_ok=True)
    if "logged_at" not in record:
        record = {**record, "logged_at": datetime.now(timezone.utc).isoformat()}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out
