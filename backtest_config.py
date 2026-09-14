# -*- coding: utf-8 -*-
"""
回测参数配置 —— 修改此文件即可改变自动化在聚宽平台上设置的回测条件。

回测频度可选：「每天」「分钟」「tick」
"""

# 回测开始日期（YYYY-MM-DD）
BACKTEST_START_DATE = "2026-01-01"

# 回测结束日期（YYYY-MM-DD）
BACKTEST_END_DATE = "2026-09-01"

# 初始资金（元）
BACKTEST_INITIAL_CAPITAL = 100_000

# 回测频度：每天 | 分钟 | tick
BACKTEST_FREQUENCY = "每天"
