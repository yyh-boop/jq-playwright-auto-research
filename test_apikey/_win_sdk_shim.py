# -*- coding: utf-8 -*-
"""Windows + Python 3.11：cursor-sdk 本地 Bridge 需要 os.get_blocking（3.12+ / Unix）。"""

from __future__ import annotations

import os
import sys


def apply() -> None:
    if sys.platform == "win32":
        if not hasattr(os, "get_blocking"):
            os.get_blocking = lambda _fd: True  # type: ignore[attr-defined]
        if not hasattr(os, "set_blocking"):
            os.set_blocking = lambda _fd, _blocking: None  # type: ignore[attr-defined]
