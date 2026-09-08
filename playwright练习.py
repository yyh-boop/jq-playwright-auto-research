# -*- coding: utf-8 -*-
"""
Playwright + Microsoft Edge 聚宽平台自动化练习（feature/backtest：策略回测）

流程：登录 → 策略回测 → 打开「自动化测试用」→ 关闭提示弹窗 → 编译运行
"""

import os
import random
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
PROFILE_DIR = BASE_DIR / "edge_profile"
ENV_FILE = BASE_DIR / ".env"

JOINQUANT_LOGIN_URL = "https://www.joinquant.com/user/login/index?type=login"
JOINQUANT_HOME_URL = "https://www.joinquant.com/view/user/floor?type=creditsdesc"
JOINQUANT_STRATEGY_LIST_URL = "https://www.joinquant.com/algorithm/index/list"
JOINQUANT_BASE_URL = "https://www.joinquant.com"
DEFAULT_STRATEGY_NAME = "自动化测试用"
MANUAL_LOGIN_TIMEOUT = 300
STEP_DELAY_MIN = 3
STEP_DELAY_MAX = 8


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_strategy_name() -> str:
    load_env()
    return os.getenv("JOINQUANT_STRATEGY_NAME", DEFAULT_STRATEGY_NAME).strip() or DEFAULT_STRATEGY_NAME


def get_credentials() -> tuple[str, str]:
    load_env()
    username = os.getenv("JOINQUANT_USERNAME", "").strip()
    password = os.getenv("JOINQUANT_PASSWORD", "").strip()
    if not username or not password:
        print("请先在 .env 文件中配置账号密码：")
        print("  JOINQUANT_USERNAME=你的手机号")
        print("  JOINQUANT_PASSWORD=你的密码")
        print(f"可参考 {BASE_DIR / '.env.example'}")
        sys.exit(1)
    return username, password


def create_browser_context(playwright):
    """启动 Edge，使用 edge_profile 持久化 Cookie。"""
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="msedge",
        headless=False,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    return context


def step_delay(page: Page, label: str = "") -> None:
    """每步操作后随机等待 3~8 秒。"""
    seconds = random.randint(STEP_DELAY_MIN, STEP_DELAY_MAX)
    if label:
        print(f"  等待 {seconds}s（{label}）")
    else:
        print(f"  等待 {seconds}s")
    page.wait_for_timeout(seconds * 1000)


def human_type(locator, text: str) -> None:
    locator.click()
    locator.fill("")
    locator.press_sequentially(text, delay=80)


def is_login_page(page: Page) -> bool:
    if "/user/login" in page.url:
        return True
    login_form = page.locator('input[name="username"]')
    return login_form.count() > 0 and login_form.first.is_visible()


def is_logged_in(page: Page) -> bool:
    return not is_login_page(page)


def try_restore_session(page: Page) -> bool:
    print(f"直接访问：{JOINQUANT_HOME_URL}")
    page.goto(JOINQUANT_HOME_URL, wait_until="domcontentloaded", timeout=30000)
    step_delay(page, "检测登录态")

    if is_logged_in(page):
        print("当前 URL：", page.url)
        return True

    print("Cookie 已失效或未登录，需要重新登录")
    return False


def wait_for_manual_captcha(page: Page) -> bool:
    print("\n" + "=" * 52)
    print("  已自动点击「登录」")
    print("  若出现滑块验证码，请在浏览器中手动拖动完成")
    print("  完成后脚本会自动继续")
    print(f"  最长等待 {MANUAL_LOGIN_TIMEOUT} 秒")
    print("=" * 52 + "\n")

    for i in range(MANUAL_LOGIN_TIMEOUT):
        if is_logged_in(page):
            print("登录成功")
            step_delay(page, "登录成功后")
            return True
        if i > 0 and i % 30 == 0:
            print(f"  仍在等待...（{i} 秒）")
        page.wait_for_timeout(1000)

    page.screenshot(path=str(SCREENSHOTS_DIR / "login_captcha_timeout.png"))
    return False


def perform_login(page: Page, username: str, password: str) -> bool:
    print(f"打开登录页：{JOINQUANT_LOGIN_URL}")
    page.goto(JOINQUANT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    step_delay(page, "打开登录页")

    page.get_by_text("密码登录", exact=True).click()
    step_delay(page, "切换密码登录")
    human_type(page.locator('input[name="username"]'), username)
    human_type(page.locator('input[name="pwd"]'), password)
    step_delay(page, "填写账号密码")

    agreement = page.locator("input[type='checkbox']:visible")
    if agreement.count() and not agreement.first.is_checked():
        agreement.first.check()

    print("自动点击「登录」...")
    page.locator("button.btnPwdSubmit").click()
    step_delay(page, "点击登录")

    if is_logged_in(page):
        return True

    return wait_for_manual_captcha(page)


def ensure_logged_in(page: Page, username: str, password: str) -> bool:
    print("【步骤 1】尝试复用 edge_profile 中已保存的登录态...")
    if try_restore_session(page):
        print("已复用登录态，跳过登录页（不会触发验证码）")
        return True

    print("\n【步骤 2】需要重新登录...")
    if not perform_login(page, username, password):
        return False

    page.goto(JOINQUANT_HOME_URL, wait_until="domcontentloaded", timeout=30000)
    step_delay(page, "登录后进入首页")
    return is_logged_in(page)


def go_to_strategy_backtest(page: Page) -> bool:
    """顶栏「量化研究平台」→「策略回测」，失败则直接跳转策略列表。"""
    print("\n【步骤 3】打开策略回测...")
    if "/view/user/floor" not in page.url:
        page.goto(JOINQUANT_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        step_delay(page, "进入首页")

    nav = page.locator("a").filter(has_text="量化研究平台").first
    backtest_href = "/algorithm/index/list"
    clicked = False

    if nav.count() and nav.is_visible():
        nav.hover()
        page.wait_for_timeout(800)
        backtest_link = page.locator(f"a[href='{backtest_href}']").filter(has_text="策略回测")
        if not backtest_link.count():
            backtest_link = page.locator(f"a[href='{backtest_href}']")
        try:
            backtest_link.first.wait_for(state="visible", timeout=5000)
            backtest_link.first.click()
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            step_delay(page, "点击策略回测")
            clicked = True
        except PlaywrightError:
            print("悬停后未能点击「策略回测」，改为直接访问策略列表")

    if not clicked:
        if not nav.count() or not nav.is_visible():
            print("未找到顶栏导航，改为直接访问策略列表")
        page.goto(JOINQUANT_STRATEGY_LIST_URL, wait_until="domcontentloaded", timeout=30000)
        step_delay(page, "进入策略列表")

    page.wait_for_selector("text=策略列表", timeout=15000)
    print("策略列表页：", page.url)
    page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_strategy_list.png"))
    return "/algorithm/index/list" in page.url


def open_existing_strategy(page: Page, strategy_name: str) -> bool:
    """在策略列表中打开已有策略，进入编辑器。"""
    print(f"\n【步骤 4】打开策略「{strategy_name}」...")
    page.wait_for_selector("text=策略列表", timeout=15000)

    strategy_link = page.locator("a[href*='/algorithm/index/edit']").filter(has_text=strategy_name)
    if not strategy_link.count():
        strategy_link = page.get_by_role("link", name=strategy_name)
    if not strategy_link.count():
        strategy_link = page.locator("table tbody tr").filter(has_text=strategy_name).locator("a")

    if not strategy_link.count():
        print(f"未在列表中找到策略「{strategy_name}」")
        page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_strategy_not_found.png"))
        return False

    href = strategy_link.first.get_attribute("href")
    if href:
        if not href.startswith("http"):
            href = JOINQUANT_BASE_URL + href
        print(f"进入编辑器：{href}")
        page.goto(href, wait_until="domcontentloaded", timeout=30000)
    else:
        strategy_link.first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)

    step_delay(page, "进入策略编辑器")

    if "/algorithm/index/edit" not in page.url:
        try:
            page.wait_for_url("**/algorithm/index/edit**", timeout=15000)
        except PlaywrightError:
            print("未能进入策略编辑器")
            page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_strategy_open_failed.png"))
            return False

    print("策略编辑器：", page.url)
    page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_strategy_editor.png"))
    return True


def dismiss_edit_prompt_if_present(page: Page) -> None:
    """检测编辑器「提示」弹窗，若有则点击「不再提示」。"""
    print("\n【步骤 5】检测提示弹窗...")

    dont_show_btn = page.get_by_role("button", name="不再提示")
    if not dont_show_btn.count():
        dont_show_btn = page.get_by_text("不再提示", exact=True)

    try:
        dont_show_btn.first.wait_for(state="visible", timeout=5000)
    except PlaywrightError:
        print("未检测到提示弹窗，继续执行")
        step_delay(page, "无弹窗，继续")
        return

    if dont_show_btn.count() and dont_show_btn.first.is_visible():
        print("检测到提示弹窗，点击「不再提示」...")
        dont_show_btn.first.click()
        step_delay(page, "关闭提示弹窗")
        return

    confirm_btn = page.get_by_role("button", name="确定")
    if not confirm_btn.count():
        confirm_btn = page.get_by_text("确定", exact=True)
    if confirm_btn.count() and confirm_btn.first.is_visible():
        print("未找到「不再提示」，改为点击「确定」关闭弹窗...")
        confirm_btn.first.click()
        step_delay(page, "关闭提示弹窗")
        return

    print("弹窗存在但未识别按钮，继续执行")
    step_delay(page, "弹窗处理结束")


def compile_and_run(page: Page) -> bool:
    """点击「编译运行」。"""
    print("\n【步骤 6】编译运行...")
    compile_btn = page.get_by_role("button", name="编译运行")
    if not compile_btn.count():
        compile_btn = page.get_by_text("编译运行", exact=True)
    compile_btn.first.wait_for(state="visible", timeout=15000)
    compile_btn.first.click()
    step_delay(page, "点击编译运行")

    page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_compile_run.png"))
    print("已点击「编译运行」，等待回测结果...")
    return True


def safe_close_context(context) -> None:
    try:
        context.close()
    except PlaywrightError:
        pass


def run() -> None:
    username, password = get_credentials()
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    PROFILE_DIR.mkdir(exist_ok=True)

    print(f"浏览器数据目录：{PROFILE_DIR}")
    print("（Cookie 保存在此，请勿删除，否则需重新登录）")
    print(f"每步随机等待 {STEP_DELAY_MIN}~{STEP_DELAY_MAX} 秒\n")

    with sync_playwright() as p:
        context = create_browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        if not ensure_logged_in(page, username, password):
            print("登录失败")
            page.screenshot(path=str(SCREENSHOTS_DIR / "joinquant_login_failed.png"))
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        print("\n登录验证通过")

        if not go_to_strategy_backtest(page):
            print("未能进入策略回测页面")
            page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_nav_failed.png"))
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        strategy_name = get_strategy_name()
        if not open_existing_strategy(page, strategy_name):
            print(f"未能打开策略「{strategy_name}」")
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        dismiss_edit_prompt_if_present(page)
        compile_and_run(page)

        print(f"\n策略回测流程已完成（{strategy_name} + 编译运行）")
        print(f"截图目录：{SCREENSHOTS_DIR}")
        print("\n浏览器保持打开。按 Enter 关闭...")
        input()
        safe_close_context(context)
        print("流程结束！")


if __name__ == "__main__":
    run()
