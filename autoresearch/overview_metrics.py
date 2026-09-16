# -*- coding: utf-8 -*-
"""聚宽收益概述页指标（与截图一致）：策略收益、策略年化收益、最大回撤。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

PCT_RE = re.compile(r"-?\d+(?:\.\d+)?")

OVERVIEW_METRICS_FILENAME = "overview_metrics.json"


def parse_percent_text(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("％", "%")
    if not text or text in ("--", "-", "N/A", "nan"):
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1])
        except ValueError:
            pass
    m = PCT_RE.search(text)
    if not m:
        return None
    try:
        v = float(m.group(0))
    except ValueError:
        return None
    if abs(v) <= 1.5 and "%" not in text:
        return round(v * 100, 4)
    return v


def xlsx_max_drawdown_pct(metrics: dict[str, Any]) -> float | None:
    raw = (metrics.get("raw") or {}).get("最大回撤") or {}
    val = raw.get("worst_abs")
    if val is None:
        val = raw.get("primary_value")
    return parse_percent_text(val)


def _drawdown_suspect_equal_return(
    drawdown: float | None,
    strategy_return: float | None,
) -> bool:
    if drawdown is None or strategy_return is None:
        return False
    return abs(drawdown - strategy_return) < 0.05


def merge_overview_into_metrics(
    metrics: dict[str, Any],
    overview: dict[str, Any] | None,
    *,
    backtest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """overview 优先写入 canonical 字段；保留 Excel raw 作 fallback。"""
    if not overview:
        return metrics
    out = dict(metrics)
    src = overview.get("metrics") if isinstance(overview.get("metrics"), dict) else overview

    sr = parse_percent_text(src.get("strategy_return_pct"))
    sa = parse_percent_text(src.get("strategy_annual_return_pct"))
    dd = parse_percent_text(src.get("max_drawdown_pct"))

    if sr is not None:
        out["strategy_return_pct"] = sr
    if sa is not None:
        out["strategy_annual_return_pct"] = sa
    if dd is not None:
        out["max_drawdown_pct"] = dd

    source: dict[str, Any] = {
        "primary": "joinquant_overview",
        "overview_scraped_at": overview.get("scraped_at"),
        "page_url": overview.get("page_url"),
    }

    # 抓取错误时常见：最大回撤被填成与策略收益相同 → 用 Excel 最大回撤修正
    if _drawdown_suspect_equal_return(out.get("max_drawdown_pct"), out.get("strategy_return_pct")):
        dd_x = xlsx_max_drawdown_pct(out)
        if dd_x is not None and not _drawdown_suspect_equal_return(dd_x, out.get("strategy_return_pct")):
            out["max_drawdown_pct"] = dd_x
            source["max_drawdown_corrected_from_xlsx"] = True

    # 达标与 loop 打分：优先策略年化（与聚宽「策略年化收益」一致）
    if sa is not None:
        out["annual_return_pct"] = sa
    elif sr is not None:
        out["annual_return_pct"] = sr

    out["metrics_source"] = source
    return out


def load_overview_metrics_file(path: Path | str) -> dict[str, Any] | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_overview_metrics(result_dir: Path, payload: dict[str, Any]) -> Path:
    out = result_dir / OVERVIEW_METRICS_FILENAME
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def backtest_calendar_days(backtest: dict[str, Any] | None) -> int | None:
    if not backtest:
        return None
    start = str(backtest.get("start", "")).strip()
    end = str(backtest.get("end", "")).strip()
    if not start or not end:
        return None
    try:
        d0 = datetime.strptime(start[:10], "%Y-%m-%d")
        d1 = datetime.strptime(end[:10], "%Y-%m-%d")
        return max(0, (d1 - d0).days)
    except ValueError:
        return None


def apply_xlsx_period_fallback(metrics: dict[str, Any], backtest: dict[str, Any] | None) -> dict[str, Any]:
    """无 overview 时：按回测长度选 12/6 个月列，并填充 strategy_* 字段。"""
    if metrics.get("strategy_return_pct") is not None:
        return metrics
    raw = (metrics.get("raw") or {}).get("策略收益") or {}
    by_period = raw.get("by_period") or {}
    days = backtest_calendar_days(backtest)
    prefer_12 = days is not None and days >= 330
    key = "12month" if prefer_12 and by_period.get("12month") is not None else None
    if key is None:
        for k in ("6month", "12month", "3month", "1month"):
            if by_period.get(k) is not None:
                key = k
                break
    if key is None:
        return metrics
    val = by_period.get(key)
    if val is None:
        return metrics
    pct = parse_percent_text(val)
    if pct is None:
        return metrics
    out = dict(metrics)
    out["strategy_return_pct"] = pct
    if out.get("strategy_annual_return_pct") is None:
        out["strategy_annual_return_pct"] = pct if prefer_12 else out.get("annual_return_pct")
    if out.get("annual_return_pct") is None:
        out["annual_return_pct"] = out.get("strategy_annual_return_pct") or pct
    out.setdefault("metrics_source", {})["xlsx_return_period"] = key
    return out
