# -*- coding: utf-8 -*-
"""阶段 3.3：从已有 result 目录生成 agent_task.md / agent_task.json。

用法：
  python build_agent_task.py result/20260915_133955
"""

from __future__ import annotations

import sys

from autoresearch.agent_task import main

if __name__ == "__main__":
    raise SystemExit(main())
