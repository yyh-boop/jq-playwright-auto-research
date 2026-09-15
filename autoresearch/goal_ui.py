# -*- coding: utf-8 -*-
"""阶段 3 启动：小窗口 GUI 输入本次研究目标。"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext


def prompt_research_goal(
    *,
    title: str = "autoresearch 阶段 3",
    hint: str = "请输入本次回测/研究目标（可含：年化≥30%、最大回撤≤10% 等）",
) -> str | None:
    """
    模态小窗口；确定返回目标文本，取消返回 None。
    """
    result: list[str | None] = [None]

    root = tk.Tk()
    root.title(title)
    root.geometry("480x220")
    root.resizable(True, True)

    tk.Label(root, text=hint, wraplength=440, justify="left").pack(padx=12, pady=(12, 6), anchor="w")

    box = scrolledtext.ScrolledText(root, height=6, width=56, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
    box.pack(padx=12, pady=6, fill=tk.BOTH, expand=True)
    box.focus_set()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=(0, 12))

    def on_ok() -> None:
        text = box.get("1.0", tk.END).strip()
        if not text:
            return
        result[0] = text
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    tk.Button(btn_frame, text="开始", width=10, command=on_ok).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(side=tk.LEFT, padx=6)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()
    return result[0]
