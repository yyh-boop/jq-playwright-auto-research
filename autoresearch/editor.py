# -*- coding: utf-8 -*-
"""聚宽策略编辑器：读取/写入源码，保存并编译。"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, Error as PlaywrightError

GET_EDITOR_CODE_JS = """
() => {
  const el = document.querySelector('.ace_editor');
  if (window.ace && el) {
    try {
      const ed = ace.edit(el);
      return { ok: true, code: ed.getValue(), via: 'ace' };
    } catch (e) {}
  }
  const pre = document.querySelector('#editor, .CodeMirror, textarea');
  if (pre && 'value' in pre) {
    return { ok: true, code: pre.value, via: 'textarea' };
  }
  return { ok: false, error: '未找到策略编辑器' };
}
"""

SET_EDITOR_CODE_JS = """
(code) => {
  const el = document.querySelector('.ace_editor');
  if (window.ace && el) {
    const ed = ace.edit(el);
    ed.setValue(code, -1);
    ed.clearSelection();
    return { ok: true, via: 'ace' };
  }
  const pre = document.querySelector('#editor, .CodeMirror, textarea');
  if (pre && 'value' in pre) {
    pre.value = code;
    pre.dispatchEvent(new Event('input', { bubbles: true }));
    return { ok: true, via: 'textarea' };
  }
  return { ok: false, error: '未找到策略编辑器' };
}
"""


def read_strategy_code(page: Page) -> str:
    raw = page.evaluate(GET_EDITOR_CODE_JS)
    if not isinstance(raw, dict) or not raw.get("ok"):
        raise RuntimeError(raw.get("error") if isinstance(raw, dict) else "读取编辑器失败")
    return str(raw["code"])


def write_strategy_code(page: Page, code: str) -> None:
    raw = page.evaluate(SET_EDITOR_CODE_JS, code)
    if not isinstance(raw, dict) or not raw.get("ok"):
        raise RuntimeError(raw.get("error") if isinstance(raw, dict) else "写入编辑器失败")


def save_and_compile_strategy(page: Page) -> None:
    """保存并编译（按钮文案因站点版本可能略有差异）。"""
    for label in ("保存", "编译"):
        btn = page.get_by_text(label, exact=True)
        if btn.count():
            try:
                btn.first.click(timeout=5000)
                page.wait_for_timeout(2000)
            except PlaywrightError:
                pass
    page.wait_for_timeout(1500)


def ensure_on_editor(page: Page, editor_url: str) -> None:
    if "/algorithm/index/edit" not in page.url:
        page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)


def apply_strategy_from_file(page: Page, editor_url: str, path: Path) -> None:
    """阶段 3：将本地整份策略写入编辑器（无需 AUTORESEARCH 标记块）。"""
    code = path.read_text(encoding="utf-8")
    ensure_on_editor(page, editor_url)
    write_strategy_code(page, code)
    save_and_compile_strategy(page)
    print(f"  已从本地文件写入策略：{path}")
