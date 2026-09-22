# Playwright 自动化说明

本文档介绍本仓库中 **Playwright + Microsoft Edge** 如何驱动 [聚宽 JoinQuant](https://www.joinquant.com) 网页，完成登录、策略编辑、回测与结果采集。核心实现集中在 [`playwright练习.py`](playwright练习.py)，上层量化流程见 [`README_QUANT_FRAMEWORK.md`](README_QUANT_FRAMEWORK.md)。

---

## 1. Playwright 在本项目中的角色

| 能力 | 用途 |
|------|------|
| **浏览器自动化** | 模拟用户在聚宽上的点击、填表、等待页面加载 |
| **持久化上下文** | 复用 Cookie，减少重复登录与验证码 |
| **DOM / 网络** | 抓取收益概述、jqGrid 表格、部分 API 响应 |
| **产物落盘** | 截图、Excel、`run_manifest.json` 供后续 Agent 与评估使用 |

技术栈：**Python 同步 API**（`playwright.sync_api`）、**Edge 渠道**（`channel="msedge"`）、**有头模式**（便于人工处理验证码）。

---

## 2. 环境与依赖

```bash
pip install -r requirements.txt
playwright install msedge   # 若本机 Edge 已可用，通常可直接 launch channel=msedge
```

账号配置：复制 [`.env.example`](.env.example) 为 `.env`，填写 `JOINQUANT_USERNAME` / `JOINQUANT_PASSWORD`（`.env` 已加入 `.gitignore`，勿提交）。

回测区间、资金、频率可在 [`backtest_config.py`](backtest_config.py) 或 `.env` 中配置。

---

## 3. 浏览器与会话设计

### 3.1 持久化用户目录 `edge_profile/`

```text
launch_persistent_context(user_data_dir=edge_profile, channel="msedge", ...)
```

- Cookie 与本地登录态保存在 `edge_profile/`，**不应提交到 Git**（已在 `.gitignore`）。
- 流程优先 **直接访问首页** 检测是否已登录；成功则跳过登录页，降低触发滑块验证码的概率。

### 3.2 反自动化检测（轻度）

- 关闭默认 `--enable-automation` 参数，并注入脚本隐藏 `navigator.webdriver`。
- 操作间 **随机等待 3～8 秒**（`step_delay`），输入使用 `press_sequentially` 模拟人工键入。

### 3.3 登录与验证码

1. `try_restore_session`：访问用户首页，判断是否已登录。  
2. 若失效：`perform_login` 打开密码登录页 → 填账号密码 → 点击登录。  
3. 若仍停留在登录页：`wait_for_manual_captcha` **阻塞等待用户手动完成滑块**（最长约 300 秒）。

这是有意为之：**验证码不做破解**，人机协作保证可维护性与合规性。

---

## 4. 聚宽回测主流程（单轮）

下列步骤对应 `playwright练习.py` 中的函数链，也是 `run_backtest_trial` / `run_backtest_from_local_file` 的骨架：

```text
ensure_logged_in
    → go_to_strategy_backtest / wait_for_strategy_list_page
    → open_existing_strategy（按 JOINQUANT_STRATEGY_NAME）
    → [可选] configure_backtest_params（区间、资金、频率）
    → apply_strategy_params_to_editor / 上传本地 .py 源码
    → run_backtest → wait_for_backtest_complete
    → collect_backtest_artifacts
```

### 4.1 导航与稳定性

- 策略列表、回测页 URL 与 DOM 结构会随站点改版变化；代码中使用 **多 selector 回退**、显式 `wait_for_*` 与超时重试（如 `wait_for_strategy_list_page`）。
- 弹窗（如「是否继续编辑」）通过 `dismiss_edit_prompt_if_present` 处理。

### 4.2 回测参数面板

- `CONFIGURE_BACKTEST_PANEL`（模块级常量，research 循环中常设为 `False` 以加速）：是否在页面上改回测条件。  
- 固定条件的多轮实验见阶段 2 [`orchestrator.py`](orchestrator.py) 的说明——**只改策略参数，不改回测区间**。

### 4.3 结果采集

| 产物 | 说明 |
|------|------|
| 收益概述 | `scrape_overview_metrics` + 可选截图 `overview.png` |
| 交易详情 / 每日持仓 | jqGrid 分页拉全量 → Excel |
| 性能分析 | 风险指标表格 → Excel |
| 元数据 | [`autoresearch/manifest.py`](autoresearch/manifest.py) 写入 `run_manifest.json`（指标、目标、`evaluation.passed`） |

`SAVE_BACKTEST_ARTIFACTS` 为 `False` 时可跳过截图与 Excel，仅保留概述指标与 manifest，用于 **research 循环提速**。

### 4.4 表格与 API

- **jqGrid**：`extract_jqgrid_rows`、`ensure_jqgrid_fully_loaded` 处理分页与加载态。  
- **持仓**：在部分场景下通过 `page.request` 调用聚宽内部 API（`fetch_all_positions_via_api`）补全数据。

---

## 5. 与上层模块的衔接

| 调用方 | 行为 |
|--------|------|
| [`research_run.py`](research_run.py) / [`research_start.py`](research_start.py) | 启动浏览器 → 上传本地策略 → 单次回测 |
| [`orchestrator.py`](orchestrator.py) | 同一浏览器上下文内多 trial（参数 mutator 或 pipeline-only） |
| [`autoresearch/backtest_session.py`](autoresearch/backtest_session.py) | **已登录的 `Page`** 上上传并回测，供 `research_loop` 复用 |
| [`autoresearch/research_loop_runner.py`](autoresearch/research_loop_runner.py) | **单浏览器会话**：基线回测 → Agent 改码 → 再回测，避免重复登录 |

要点：**长会话复用 `Page`** 是阶段 3.5/3.6 的关键，否则每轮 Agent 迭代都要重新登录。

---

## 6. 直接运行（练习 / 调试）

在项目根目录：

```bash
python playwright练习.py
```

默认策略名见脚本内 `DEFAULT_STRATEGY_NAME` 或环境变量 `JOINQUANT_STRATEGY_NAME`。  
结果目录默认在 `result/`（已 gitignore），截图在 `screenshots/`。

---

## 7. Playwright 实践要点（知识小结）

1. **Locator 优先于裸 CSS**：尽量用 `get_by_text`、`locator(...)`，便于应对 class 变更。  
2. **永远假设网络与 DOM 慢**：`wait_until="domcontentloaded"` + 业务级 `wait_for_*`，比固定 `sleep` 更稳；本仓库仍保留随机 sleep 以降低风控触发。  
3. **持久化 Context 适合「自有账号 + 长期脚本」**，与每次 `launch` 新 Context 相比，更省登录成本。  
4. **有头 + 人工验证码** 是金融类网站的现实选择；headless 适合稳定内网环境，聚宽场景下未作为默认。  
5. **把「页面操作」与「实验逻辑」分层**：页面在 `playwright练习.py`，实验记录、目标评估、Agent 在 `autoresearch/`，便于替换数据源或改用官方 API（若未来可用）。

---

## 8. 常见问题

| 现象 | 建议 |
|------|------|
| 登录后立即掉线 | 检查 `edge_profile` 是否可写；勿多开脚本抢同一 profile |
| 卡在验证码 | 在有头窗口完成滑块；超时截图见 `screenshots/login_captcha_timeout.png` |
| 找不到策略 | 聚宽策略名须与 `JOINQUANT_STRATEGY_NAME` 一致 |
| 回测超时 | 增大 `BACKTEST_TIMEOUT`；检查聚宽队列是否过长 |
| 概述指标为空 | 确认回测已完成且停留在「收益概述」Tab；查看 `overview_metrics.json` 是否生成 |

---

## 9. 相关文件索引

- [`playwright练习.py`](playwright练习.py) — 登录、回测、采集  
- [`backtest_config.py`](backtest_config.py) — 回测参数  
- [`autoresearch/overview_metrics.py`](autoresearch/overview_metrics.py) — 与聚宽概述字段对齐  
- [`autoresearch/parse_performance.py`](autoresearch/parse_performance.py) — 性能表解析  

量化闭环（目标 GUI、Agent 改策略、实验日志、复盘报告）请参阅 [**README_QUANT_FRAMEWORK.md**](README_QUANT_FRAMEWORK.md)。
