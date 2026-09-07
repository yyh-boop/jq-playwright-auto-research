"""
Playwright + Microsoft Edge 聚宽平台自动化练习

- 使用本机 Microsoft Edge（channel="msedge"）
- 登录状态保存在 edge_profile/，登录成功后 Cookie 会自动复用
- 打开聚宽登录页并用账号密码登录
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
PROFILE_DIR = BASE_DIR / "edge_profile"
ENV_FILE = BASE_DIR / ".env"

JOINQUANT_LOGIN_URL = "https://test.demo.joinquant.com/user/login/index?type=login"


def load_env() -> None:
    """从 .env 文件加载环境变量（若存在）。"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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


def login_joinquant(page: Page, username: str, password: str) -> None:
    """打开聚宽登录页，使用手机号 + 密码登录。"""
    print(f"打开登录页：{JOINQUANT_LOGIN_URL}")
    page.goto(JOINQUANT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    page.get_by_text("密码登录", exact=True).click()
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="pwd"]').fill(password)

    agreement = page.locator("input[type='checkbox']:visible")
    if agreement.count() and not agreement.first.is_checked():
        agreement.first.check()

    submit_btn = page.locator("button.btnPwdSubmit")
    submit_btn.wait_for(state="visible", timeout=10000)
    submit_btn.click()

    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)


def is_login_success(page: Page) -> bool:
    if "/user/login" in page.url:
        return False
    error = page.locator(".error, .err-msg, .login-error, .toast-error")
    if error.count() and error.first.is_visible():
        return False
    return True


def safe_close_context(context) -> None:
    """安全关闭浏览器，避免用户已手动关窗时再 close 报错。"""
    try:
        context.close()
    except PlaywrightError:
        pass


def run() -> None:
    username, password = get_credentials()
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

        print("【1/2】登录聚宽")
        login_joinquant(page, username, password)

        print("\n【2/2】检查登录结果")
        print("页面标题：", page.title())
        print("当前 URL：", page.url)

        if is_login_success(page):
            print("✓ 登录成功（已离开登录页）")
        else:
            print("✗ 登录可能失败，请检查账号密码或页面提示")
            page.screenshot(path=str(SCREENSHOTS_DIR / "joinquant_login_failed.png"))
            print(f"失败截图 → {SCREENSHOTS_DIR / 'joinquant_login_failed.png'}")

        page.screenshot(path=str(SCREENSHOTS_DIR / "joinquant_after_login.png"))
        print(f"当前页截图 → {SCREENSHOTS_DIR / 'joinquant_after_login.png'}")

        print("\n浏览器保持打开。查看完毕后：")
        print("  - 在终端按 Enter 关闭浏览器；或")
        print("  - 直接关闭浏览器窗口也可以")
        input()
        safe_close_context(context)
        print("流程结束！")


if __name__ == "__main__":
    run()
