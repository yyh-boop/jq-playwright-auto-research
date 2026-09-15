# -*- coding: utf-8 -*-
"""
向 Cursor Agent 发送自定义问题（验证 CURSOR_API_KEY + cursor-sdk）。

用法（在 playwright练习 目录）：
  python test_apikey/check_cursor_api_key.py              # 小窗口输入问题
  python test_apikey/check_cursor_api_key.py --cli        # 终端输入问题
  python test_apikey/check_cursor_api_key.py -q "1+1等于几"
  python test_apikey/check_cursor_api_key.py --dry-run    # 不调用 API
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# 从 test_apikey/ 运行时，需把项目根加入 path 才能 import autoresearch
_ROOT = str(PROJECT_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def load_dotenv() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def apply_win_sdk_shim() -> None:
    from autoresearch.cursor_client import apply_win_sdk_shim as _shim

    _shim()


def mask_key(key: str) -> str:
    key = key.strip()
    if len(key) <= 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def prompt_question_gui() -> str | None:
    import tkinter as tk
    from tkinter import scrolledtext

    result: list[str | None] = [None]
    root = tk.Tk()
    root.title("Cursor API 探测")
    root.geometry("480x200")
    tk.Label(root, text="输入要问 Agent 的问题：", anchor="w").pack(padx=12, pady=(12, 4), fill="x")
    box = scrolledtext.ScrolledText(root, height=5, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
    box.pack(padx=12, pady=4, fill=tk.BOTH, expand=True)
    box.focus_set()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=(0, 12))

    def on_send() -> None:
        text = box.get("1.0", tk.END).strip()
        if not text:
            return
        result[0] = text
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    tk.Button(btn_frame, text="发送", width=10, command=on_send).pack(side=tk.LEFT, padx=6)
    tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(side=tk.LEFT, padx=6)
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()
    return result[0]


def prompt_question_cli() -> str | None:
    print("请输入要问 Agent 的问题（单行，Ctrl+C 取消）：")
    try:
        text = input("> ").strip()
    except KeyboardInterrupt:
        return None
    return text or None


def resolve_question(args: argparse.Namespace) -> str | None:
    if args.question:
        return args.question.strip() or None
    if args.cli:
        return prompt_question_cli()
    return prompt_question_gui()


def call_agent(question: str, api_key: str) -> tuple[str | None, str]:
    from autoresearch.cursor_client import run_local_agent_prompt

    os.environ.setdefault("CURSOR_API_KEY", api_key)
    out = run_local_agent_prompt(question, cwd=PROJECT_ROOT)
    return out.status, out.text


def main() -> int:
    parser = argparse.ArgumentParser(description="向 Cursor Agent 发送自定义问题")
    parser.add_argument("-q", "--question", default=None, help="直接传入问题，不弹窗")
    parser.add_argument("--cli", action="store_true", help="在终端输入问题（默认用小窗口 GUI）")
    parser.add_argument("--dry-run", action="store_true", help="仅检查密钥与 cursor_sdk，不调用 API")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("未设置 CURSOR_API_KEY。请在项目根目录 .env 中添加。", file=sys.stderr)
        return 1

    print(f"Python：{sys.executable}")
    try:
        apply_win_sdk_shim()
        import cursor_sdk  # noqa: F401
    except ImportError as exc:
        if "autoresearch" in str(exc):
            print(f"导入失败：{exc}", file=sys.stderr)
            print("请在 playwright练习 目录下运行本脚本。", file=sys.stderr)
            return 1
        print("未安装 cursor-sdk。请对【上面这一行同一个 Python】执行：", file=sys.stderr)
        print(f'  "{sys.executable}" -m pip install cursor-sdk', file=sys.stderr)
        print(f"（原始错误：{exc}）", file=sys.stderr)
        return 1

    print(f"项目根目录：{PROJECT_ROOT}")
    print(f"CURSOR_API_KEY：{mask_key(api_key)}")

    if args.dry_run:
        print("\n[dry-run] 跳过 API 调用。")
        return 0

    question = resolve_question(args)
    if question is None:
        print("已取消。")
        return 0

    print(f"\n你的问题：{question}")
    print("\n正在请求 Agent…")
    try:
        status, answer = call_agent(question, api_key)
    except Exception as exc:
        print(f"\nAPI 调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        if sys.platform == "win32" and "get_blocking" in str(exc):
            print("提示：请使用已含 Windows 补丁的本脚本，或升级 Python 3.12+。", file=sys.stderr)
        return 2

    print(f"\n--- status: {status} ---\n")
    print(answer)
    print("\n--- 结束 ---")

    if status and str(status).lower() in ("failed", "error", "cancelled"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
