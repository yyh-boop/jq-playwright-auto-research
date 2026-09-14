# -*- coding: utf-8 -*-
"""
阶段 2：固定回测条件，多轮回测 → 记录 experiments.jsonl。

用法（在 playwright练习 目录）：
  python orchestrator.py --pipeline-only --max-trials 2   # 不改代码，只验证多轮流水线
  python orchestrator.py --max-trials 3                   # 按 strategy_params.json 改标记块内常量

阶段 3 将用 editor.apply_strategy_from_file 写入整份策略，无需 AUTORESEARCH 标记块。

前置（带 mutator 时）：
  1. 复制 autoresearch/strategy_params.etf_momentum.example.json → strategy_params.json
  2. 聚宽「自动化测试用」与 strategies/ETF动量.py 一致（含标记块）
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Iterator

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import playwright练习 as jq
from autoresearch.experiment_log import append_experiment
from autoresearch.mutate import StrategyParamMutator
from autoresearch.orchestrator_config import OrchestratorConfig
from autoresearch.strategy_params import (
    iter_trial_param_sets,
    load_strategy_params_config,
    trial_param_sets_count,
)


def _score(manifest: dict) -> float:
    """越大越好：优先达标，其次看策略收益。"""
    ev = manifest.get("evaluation") or {}
    if ev.get("passed"):
        return 1e9
    m = manifest.get("metrics") or {}
    ret = m.get("annual_return_pct")
    dd = m.get("max_drawdown_pct")
    if ret is None:
        return -1e9
    penalty = (dd or 0) * 0.5
    return float(ret) - penalty


def _pipeline_trials(max_trials: int) -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
    for trial_no in range(max_trials):
        yield trial_no, {}, {"action": "pipeline_only", "changed": None}


def run_orchestrator(max_trials: int | None = None, *, pipeline_only: bool = False) -> int:
    cfg = OrchestratorConfig.from_env()
    sp_config: dict[str, Any] | None = None
    mutator: StrategyParamMutator | None = None
    trial_iter: Iterator[tuple[int, dict[str, Any], dict[str, Any]]]
    mode_line = ""

    if pipeline_only:
        if max_trials is not None:
            cfg = OrchestratorConfig(
                max_trials=max_trials,
                stop_on_pass=cfg.stop_on_pass,
                patience=cfg.patience,
                fixed_backtest=cfg.fixed_backtest,
            )
        trial_iter = _pipeline_trials(cfg.max_trials)
        mode_line = "模式：--pipeline-only（不修改策略代码，仅多轮回测 + 落盘）"
    else:
        sp_config = load_strategy_params_config()
        fixed_n = trial_param_sets_count(sp_config)

        if fixed_n > 0:
            n_trials = max_trials if max_trials is not None else fixed_n
            cfg = OrchestratorConfig(
                max_trials=n_trials,
                stop_on_pass=cfg.stop_on_pass,
                patience=cfg.patience,
                fixed_backtest=cfg.fixed_backtest,
            )
            mode_line = f"模式：trial_param_sets 固定 {min(cfg.max_trials, fixed_n)} 组参数"

            def _fixed_trials() -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
                assert sp_config is not None
                yield from iter_trial_param_sets(sp_config, cfg.max_trials)

            trial_iter = _fixed_trials()
        else:
            if max_trials is not None:
                cfg = OrchestratorConfig(
                    max_trials=max_trials,
                    stop_on_pass=cfg.stop_on_pass,
                    patience=cfg.patience,
                    fixed_backtest=cfg.fixed_backtest,
                )
            mutator = StrategyParamMutator(sp_config)
            mode_line = "模式：strategy_params.json 标记块内常量 ±step"

            def _mutator_trials() -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
                assert mutator is not None
                for _ in range(cfg.max_trials):
                    yield mutator.next_trial()

            trial_iter = _mutator_trials()

    username, password = jq.get_credentials()

    jq.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    jq.RESULT_DIR.mkdir(exist_ok=True)
    jq.PROFILE_DIR.mkdir(exist_ok=True)

    print("阶段 2 orchestrator：回测条件固定")
    print(f"  {mode_line}")
    print(f"  最大轮数：{cfg.max_trials}  stop_on_pass={cfg.stop_on_pass}\n")

    best_score = float("-inf")
    no_improve = 0

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

        strategy_name = jq.get_strategy_name()
        if not jq.open_existing_strategy(page, strategy_name):
            print(f"未能打开策略「{strategy_name}」")
            jq.safe_close_context(context)
            return 1

        jq.dismiss_edit_prompt_if_present(page)
        editor_url = page.url
        backtest_params = jq.get_backtest_params()
        print(
            f"固定回测：{backtest_params.start_date} ~ {backtest_params.end_date} "
            f"资金={backtest_params.initial_capital} 频度={backtest_params.frequency}"
        )

        for trial_no, params, meta in trial_iter:
            print(f"\n========== Trial {trial_no + 1}/{cfg.max_trials} ==========")
            if params:
                print(f"  策略参数：{params}  meta={meta}")
            else:
                print(f"  meta={meta}")

            try:
                outcome = jq.run_backtest_trial(
                    page,
                    strategy_name,
                    backtest_params,
                    editor_url,
                    strategy_params=params if params else None,
                    sp_config=sp_config,
                    trial_meta={"trial": trial_no, **meta},
                    configure_backtest=(trial_no == 0),
                )
            except (PlaywrightError, RuntimeError, ValueError) as exc:
                print(f"  Trial 失败：{exc}")
                append_experiment(
                    {
                        "trial": trial_no,
                        "strategy_params": params or None,
                        "meta": meta,
                        "error": str(exc),
                        "passed": False,
                    }
                )
                continue

            if outcome is None:
                append_experiment(
                    {
                        "trial": trial_no,
                        "strategy_params": params or None,
                        "meta": meta,
                        "error": "run_backtest_trial returned None",
                        "passed": False,
                    }
                )
                continue

            manifest = outcome.manifest
            record = {
                "trial": trial_no,
                "run_id": manifest.get("run_id"),
                "strategy_params": params or None,
                "meta": meta,
                "metrics": manifest.get("metrics"),
                "evaluation": manifest.get("evaluation"),
                "passed": manifest.get("passed"),
                "result_dir": str(outcome.result_dir),
            }
            append_experiment(record)
            print("  已追加 experiments.jsonl")

            if cfg.stop_on_pass and manifest.get("passed"):
                print("\n目标已达成，停止循环。")
                break

            if pipeline_only or mutator is None:
                continue

            sc = _score(manifest)
            if sc > best_score + 1e-6:
                best_score = sc
                no_improve = 0
                mutator.note_improvement(params)
            else:
                no_improve += 1
                if cfg.patience > 0 and no_improve >= cfg.patience:
                    print(f"\n连续 {cfg.patience} 轮无改进，停止。")
                    break

        print("\n浏览器保持打开。按 Enter 关闭...")
        input()
        jq.safe_close_context(context)

    print("orchestrator 结束。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="autoresearch 阶段 2 循环")
    parser.add_argument("--max-trials", type=int, default=None, help="覆盖 AUTORESEARCH_MAX_TRIALS")
    parser.add_argument(
        "--pipeline-only",
        action="store_true",
        help="不读 strategy_params.json、不改代码；仅验证登录→多轮回测→manifest→jsonl",
    )
    args = parser.parse_args()
    return run_orchestrator(max_trials=args.max_trials, pipeline_only=args.pipeline_only)


if __name__ == "__main__":
    sys.exit(main())
