"""
Playwright + Microsoft Edge 真实网页搜索练习

- 使用本机 Microsoft Edge（channel="msedge"）
- 登录状态保存在 edge_profile/，首次运行可手动登录，之后自动复用
- 使用 Bing 搜索（与 Edge 配合稳定）
"""

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
PROFILE_DIR = BASE_DIR / "edge_profile"

SEARCH_KEYWORD = "Playwright 浏览器自动化"


def bing_search(page: Page, keyword: str) -> None:
    page.goto("https://cn.bing.com", wait_until="domcontentloaded", timeout=30000)
    search_box = page.locator("#sb_form_q")
    search_box.wait_for(state="visible", timeout=15000)
    search_box.fill(keyword)
    search_box.press("Enter")


def print_search_results(page: Page) -> None:
    results = page.locator("li.b_algo h2")
    count = min(results.count(), 5)
    if count:
        print(f"前 {count} 条搜索结果：")
        for i in range(count):
            print(f"  {i + 1}. {results.nth(i).inner_text()}")
    else:
        print("未读取到搜索结果（页面结构可能变化）")


def run(keyword: str = SEARCH_KEYWORD) -> None:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    PROFILE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

        page = context.pages[0] if context.pages else context.new_page()

        print(f"正在使用 Edge 打开 Bing 并搜索：{keyword}")
        bing_search(page, keyword)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        print("页面标题：", page.title())
        print_search_results(page)

        screenshot_path = SCREENSHOTS_DIR / "bing_search.png"
        page.screenshot(path=str(screenshot_path))
        print(f"截图已保存 → {screenshot_path}")

        print("自动化已完成，浏览器保持打开。按 Enter 键关闭浏览器并结束程序...")
        input()
        context.close()
        print("流程结束！")


if __name__ == "__main__":
    run()
