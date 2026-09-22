# 量化 Auto-Research 框架说明

本仓库在 Playwright 聚宽回测自动化之上，搭建了一套 **「目标驱动 → 回测 → 评估 → 改码 → 再回测」** 的本地研究框架（`autoresearch`）。浏览器层说明见 [`README_PLAYWRIGHT.md`](README_PLAYWRIGHT.md)。

**推荐对外展示分支**：`feature/agent-research`（含阶段 3.x 完整链路与 ETF 动量策略迭代样例）。

---

## 1. 设计目标

- **真相源在本地**：策略以 `strategies/*.py` 为准，上传至聚宽同名策略运行。  
- **可重复的实验记录**：每次回测生成 `run_manifest.json`，多轮写入 `experiments/research_runs.jsonl`。  
- **目标可表达、可评估**：GUI / 文本目标解析为年化、回撤等阈值，写入 `evaluation`。  
- **Agent 可接入**：回测后自动生成 `agent_task.json`，由 Cursor Agent 读取 manifest 与路径改策略。  
- **单会话闭环**：同一 Edge 登录态内完成多轮「改码 + 回测」，并输出 `report/` 复盘报告。

---

## 2. 阶段演进（当前实现）

```text
阶段 1   指标解析 + ResearchGoal + run_manifest / evaluate_goal
阶段 2   orchestrator.py — 固定回测条件下多 trial（strategy_params.json 变异 或 pipeline-only）
阶段 3.0   配置、GUI 目标、research session 约定
阶段 3.1   research_run.py — 上传本地策略并单次回测
阶段 3.2   research_start.py — 一键：GUI 目标 → session → 上传 → 回测
阶段 3.3   agent_task.md/json — 为 Agent 组装路径与 system prompt
阶段 3.4   research_agent.py + Cursor SDK — 单轮 Agent 改 strategies/
阶段 3.5   单浏览器内回测 ↔ Agent（research_loop_runner 前身能力）
阶段 3.6   research_loop.py — 基线回测 → 多轮 Agent send + research_memory + report/
```

各阶段入口与环境变量注释见 [`.env.example`](.env.example)。

---

## 3. 目录与数据流

```text
strategies/              # 策略源码（含 baseline 与迭代变体，如 ETF动量_*.py）
experiments/
  sessions/<id>/         # 当次 GUI 目标、session.json（gitignore）
  research_runs.jsonl    # 跨 run 的研究流水（可选入库）
  experiments.jsonl      # 阶段 2 参数搜索记录
result/<策略名>/         # 单次回测产物 + run_manifest.json（gitignore）
report/<session_id>/     # 阶段 3.6 复盘 research_report.md/json（gitignore）
autoresearch/            # 框架核心包
```

### 3.1 一次回测的数据契约：`run_manifest.json`

由 [`autoresearch/manifest.py`](autoresearch/manifest.py) 生成，核心字段：

- `metrics` — 策略收益、年化、最大回撤等（与聚宽「收益概述」对齐，见 `overview_metrics`）  
- `goal` / `evaluation` — 是否 `passed`  
- `paths` — 截图、Excel、overview 文件相对路径  
- `extra.trial_meta` — `session_id`、`loop_round`、目标文本等  

### 3.2 研究会话：`ResearchSession`

[`autoresearch/session_init.py`](autoresearch/session_init.py) + [`autoresearch/goal_ui.py`](autoresearch/goal_ui.py)：

- 用户在 GUI 输入自然语言目标（如「年化 >60%，回撤尽量 <10%」）。  
- [`autoresearch/goal_prompt.py`](autoresearch/goal_prompt.py) 解析数值 hint，供打分与 Agent 提示。  
- 备份原始策略到 `experiments/sessions/.../original/`。

### 3.3 Agent 改码入口

[`autoresearch/agent_task.py`](autoresearch/agent_task.py) 根据 manifest 写出：

- 要读的文件列表（manifest、策略、session、可选 memory / jsonl）  
- [`autoresearch/agent_system_prompt.py`](autoresearch/agent_system_prompt.py) 中的研究助手约束（小步迭代、新文件命名、`NEW_STRATEGY_FILE:` 约定等）

执行器：[`autoresearch/research_agent_runner.py`](autoresearch/research_agent_runner.py)（Cursor Agent SDK，需 `CURSOR_API_KEY`）。

### 3.4 多轮循环与记忆

[`autoresearch/research_loop_runner.py`](autoresearch/research_loop_runner.py)：

1. `prepare_research_session`  
2. 打开 Playwright，**基线回测**（`AUTORESEARCH_STRATEGY_FILE`）  
3. 循环：`run_research_agent_turn` → 语法校验 → 上传新策略 → 回测 → `ResearchMemory` 记录  
4. `pick_next_strategy_path` / `score_manifest` 选优  
5. [`autoresearch/research_report.py`](autoresearch/research_report.py) 生成复盘 Markdown  

记忆与建议：[`autoresearch/research_memory.py`](autoresearch/research_memory.py)（实验摘要、下一步方向、`RESEARCH_INSIGHT` / `MEMORY_UPDATE_JSON` 等约定）。

---

## 4. 快速开始（阶段 3.6）

1. 配置 `.env`（聚宽账号、`AUTORESEARCH_STRATEGY_FILE`、`CURSOR_API_KEY` 等）。  
2. 在聚宽创建与本地一致的策略名（`JOINQUANT_STRATEGY_NAME`）。  
3. 运行：

```bash
python research_loop.py
# 或限制轮数
python research_loop.py --max-rounds 5
```

4. 查看 `result/` 下各轮 manifest、`report/` 下 `research_report.md`（本地生成，默认不提交 Git）。

**仅单次回测（无 Agent）**：

```bash
python research_start.py
```

**阶段 2 参数网格（不改整文件，只改标记块内常量）**：

```bash
cp autoresearch/strategy_params.etf_momentum.example.json strategy_params.json
python orchestrator.py --max-trials 3
```

---

## 5. 策略与实验样例（ETF 动量）

`strategies/` 下包含一条可展示的迭代线（名称示意）：

| 文件 | 方向 |
|------|------|
| `ETF动量.py` | Baseline：动量打分 + 趋势过滤 |
| `ETF动量_趋势入场与追踪止损.py` | 入场/止损结构优化 |
| `ETF动量_广度风控与动量轮动.py` | 广度/环境过滤 + 轮动 |
| `ETF动量_*_去频繁换仓.py` | 降低换手 |
| `ETF动量_收紧退出与广度门槛.py` | 退出与广度门槛 |

复盘示例结构可参考本地一次 session 报告（字段含各轮 score、标签、Agent 总结）。报告文件在 `report/` 目录，默认 gitignore。

---

## 6. 评估与打分逻辑（简述）

- **硬目标**：[`autoresearch/evaluate_goal.py`](autoresearch/evaluate_goal.py) + `ResearchGoal`（默认年化 ≥30%、回撤 ≤10%，可用 `.env` 覆盖）。  
- **循环内排序**：`score_manifest` — 优先 `evaluation.passed`，否则在收益与回撤间权衡（见 `research_loop_runner` / `orchestrator` 内 `_score`）。  
- **指标来源**：优先概述 DOM / `overview_metrics.json`，并与 Excel 性能表交叉验证（`parse_performance`）。

---

## 7. 模块地图（`autoresearch/`）

| 模块 | 职责 |
|------|------|
| `config` / `research_config` | 目标与环境配置 |
| `backtest_runner` / `backtest_session` | 封装 Playwright 回测 |
| `editor` / `strategy_versions` | 策略读写、备份、语法校验 |
| `mutate` / `strategy_params` | 阶段 2 参数变异 |
| `experiment_log` / `research_log` | jsonl 实验流水 |
| `cursor_client` | Cursor Agent SDK 封装 |
| `metrics_display` / `overview_metrics` | 展示与聚宽对齐 |
| `result_dirs` | 结果目录命名（按策略文件名等） |

---

## 8. 后续开发计划（持续完善）

> 本节为路线图，随实现进度更新；欢迎以 Issue / PR 跟踪。

### 8.1 迭代框架（核心）

- [ ] **统一「实验单元」抽象**：一次 trial =（策略版本 id、参数快照、回测配置 hash、manifest 引用），便于 diff 与复现。  
- [ ] **策略版本图（DAG）**：从 baseline 分支记录每次 Agent/人工改动的父节点、假设、结论，而不只依赖文件名。  
- [ ] **分离「结构改码」与「参数搜索」**：结构改动走 Agent + 新文件；参数走 orchestrator / 贝叶斯或网格，避免混在一轮 prompt 里。  
- [ ] **多目标优化**：显式 Pareto（收益、回撤、换手、暴露），而不只单一 `score`；GUI 目标映射到权重或约束。  
- [ ] **早停与 patience**：已部分存在于 orchestrator；扩展到 3.6 loop（连续 N 轮无改进则停，并写清 `stopped_reason`）。  
- [ ] **对照与消融**：强制 baseline + 单因子改动策略，减少 Agent 一次改太多的不可解释性。

### 8.2 Agent 与研究质量

- [ ] **更强 memory 检索**：按标签（`drawdown_up`、`meets_return_goal`）检索历史轮次，注入 few-shot 失败案例。  
- [ ] **改码后静态检查**：除语法外，增加 import/聚宽 API 白名单、最大杠杆与标的池约束。  
- [ ] **人工 checkpoint**：某轮 manifest 标记 `human_review` 后继续，适合求职展示「人机协作」。

### 8.3 工程与可复现

- [ ] **示例 report / manifest 脱敏入库**：在 `docs/examples/` 提供精简样例（无账号、无绝对路径），便于 GitHub 浏览。  
- [ ] **CI 子集**：对 `autoresearch` 纯函数与 manifest 解析做单元测试；Playwright 做可选 nightly（需密钥与人工验证码则跳过）。  
- [ ] **配置单一入口**：逐步把分散的模块级常量收敛到 `research_config` + `.env` 文档表。

### 8.4 数据与平台

- [ ] **回测条件版本化**：区间/基准/滑点与 manifest 绑定，防止改 `backtest_config` 后历史不可比。  
- [ ] **可选离线回测**：若未来接入 JoinQuant 本地 SDK 或导出数据，Playwright 仅作「上传校验」；架构上保持 `backtest_runner` 接口不变。  
- [ ] **多策略并行队列**：单账号串行回测排队，任务队列 + 失败重试策略。

### 8.5 文档与展示

- [ ] 根目录 `README.md` 索引（本文件 + Playwright 说明 + 架构图）。  
- [ ] 录制一次 `research_loop` 的终端 + 浏览器缩时，链接到 GitHub Profile / 简历。

---

## 9. 安全与仓库 hygiene

- 勿提交 `.env`、`edge_profile/`、`result/`、`report/`（见 [`.gitignore`](.gitignore)）。  
- `experiments/research_runs.jsonl` 若含本地绝对路径或敏感备注，推送前请审查或改为相对路径。  
- 聚宽账号仅用于个人研究，自动化频率请遵守平台服务条款。

---

## 10. 命令速查

| 命令 | 作用 |
|------|------|
| `python research_loop.py [--max-rounds N]` | 阶段 3.6 全自动多轮研究 |
| `python research_start.py` | GUI 目标 + 单次上传回测 |
| `python research_run.py` | 指定 session 单次回测 |
| `python research_agent.py --result result/<run_id>` | 对已有结果单轮 Agent |
| `python build_agent_task.py result/<run_id>` | 仅生成 agent_task |
| `python orchestrator.py [--pipeline-only] [--max-trials N]` | 阶段 2 多 trial |
| `python playwright练习.py` | 底层 Playwright 回测练习 |

---

如有问题或希望协作完善迭代框架，可在仓库 Issues 中按 **「阶段 x.x / 模块名 / 现象」** 描述，并附上对应 `run_manifest.json` 片段（脱敏后）。
