# jq-playwright-auto-research

基于 **Playwright（Microsoft Edge）** 驱动 [聚宽 JoinQuant](https://www.joinquant.com) 网页回测，并在本地搭建 **目标驱动 → 回测 → 评估 → Agent 改策略 → 再回测** 的 auto-research 闭环。

适合展示：**浏览器自动化**、**量化回测流水线**、**策略迭代与实验记录**。

---

## 文档

| 文档 | 说明 |
|------|------|
| [**README_PLAYWRIGHT.md**](README_PLAYWRIGHT.md) | Playwright 登录/回测/采集、会话与验证码、与上层模块衔接 |
| [**README_QUANT_FRAMEWORK.md**](README_QUANT_FRAMEWORK.md) | `autoresearch` 阶段演进、数据契约、一键 `research_loop`、后续路线图 |

---

## 快速开始

```bash
pip install -r requirements.txt
copy .env.example .env   # Windows；填写聚宽账号与可选 CURSOR_API_KEY
```

- **多轮 auto-research（推荐）**：`python research_loop.py`  
- **单次上传回测**：`python research_start.py`  
- **底层 Playwright 练习**：`python playwright练习.py`  

详细环境变量与命令见 [README_QUANT_FRAMEWORK.md §4、§10](README_QUANT_FRAMEWORK.md)。

---

## 仓库结构（概要）

```text
playwright练习.py      # 聚宽页面自动化（登录、回测、产物落盘）
autoresearch/          # 目标、manifest、Agent、research 循环
strategies/            # 本地策略源码（如 ETF 动量及迭代变体）
research_loop.py       # 阶段 3.6 一键多轮研究
```

`result/`、`report/`、`.env`、`edge_profile/` 等为本地运行产物或敏感配置，见 [`.gitignore`](.gitignore)，默认不提交。

---

## 分支说明

完整 **Agent Research** 链路在 **`feature/agent-research`**（或当前默认分支）。若默认分支较旧，请在 GitHub **Settings → General → Default branch** 中切换。

---

## 许可与声明

个人研究与学习用途；使用聚宽请遵守平台服务条款。勿将 `.env` 或账号信息提交到公开仓库。
