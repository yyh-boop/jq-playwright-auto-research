"""
Playwright + Microsoft Edge 真实网页搜索练习

- 使用本机 Microsoft Edge（channel="msedge"）
- 登录状态保存在 edge_profile/，首次运行可手动登录，之后自动复用
- 默认使用 Bing 搜索（与 Edge 配合稳定）；可改为 "baidu"（可能触发验证码）
"""

from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
PROFILE_DIR = BASE_DIR / "edge_profile"

SEARCH_ENGINE = "bing"  # "bing" | "baidu"
SEARCH_KEYWORD = "Playwright 浏览器自动化"


def bing_search(page: Page, keyword: str) -> None:
    page.goto("https://cn.bing.com", wait_until="domcontentloaded", timeout=30000)
    search_box = page.locator("#sb_form_q")
    search_box.wait_for(state="visible", timeout=15000)
    search_box.fill(keyword)
    search_box.press("Enter")


def baidu_search(page: Page, keyword: str) -> None:
    page.goto("https://www.baidu.com", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    ai_input = page.locator("#chat-textarea")
    if ai_input.count() and ai_input.is_visible():
        ai_input.fill(keyword)
        page.locator("#chat-submit-button").click()
        return

    classic_input = page.locator("#kw")
    if classic_input.count():
        classic_input.click(force=True)
        classic_input.fill(keyword, force=True)
        page.locator("#su").click(force=True)
        return

    page.goto(f"https://www.baidu.com/s?wd={quote(keyword)}")


def print_search_results(page: Page, engine: str) -> None:
    if engine == "bing":
        results = page.locator("li.b_algo h2")
    else:
        results = page.locator("#content_left .c-container h3, #content_left .result h3")

    count = min(results.count(), 5)
    if count:
        print(f"前 {count} 条搜索结果：")
        for i in range(count):
            print(f"  {i + 1}. {results.nth(i).inner_text()}")
    else:
        print("未读取到搜索结果（可能遇到验证码或页面结构变化）")


def run(keyword: str = SEARCH_KEYWORD, engine: str = SEARCH_ENGINE) -> None:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    PROFILE_DIR.mkdir(exist_ok=True)

    search_fn = bing_search if engine == "bing" else baidu_search
    engine_label = "Bing" if engine == "bing" else "百度"

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

        page = context.pages[0] if context.pages else context.new_page()

        print(f"正在使用 Edge 打开 {engine_label} 并搜索：{keyword}")
        search_fn(page, keyword)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        print("页面标题：", page.title())
        print_search_results(page, engine)

        screenshot_path = SCREENSHOTS_DIR / f"{engine}_search.png"
        page.screenshot(path=str(screenshot_path))
        print(f"截图已保存 → {screenshot_path}")

        page.wait_for_timeout(2000)
        context.close()
        print("流程结束！")


if __name__ == "__main__":
    run()
