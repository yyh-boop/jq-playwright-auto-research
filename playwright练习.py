# -*- coding: utf-8 -*-
"""
Playwright + Microsoft Edge 聚宽平台自动化练习（feature/backtest：策略回测）

流程：登录 → 策略回测 → 打开策略 → 设置参数 → 运行回测 → 收益概述截图 → 交易详情/每日持仓/性能分析 Excel → run_manifest.json

回测参数在 backtest_config.py 中修改；达标目标见 autoresearch/config.py 或 .env。
"""

import os
import random
import re
import sys
from dataclasses import dataclass
from typing import Any
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from autoresearch.manifest import finalize_manifest_from_result_dir, write_run_manifest
from autoresearch.result_dirs import allocate_result_dir, strategy_label_from_trial_meta
from backtest_config import (
    BACKTEST_END_DATE,
    BACKTEST_FREQUENCY,
    BACKTEST_INITIAL_CAPITAL,
    BACKTEST_START_DATE,
)

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
RESULT_DIR = BASE_DIR / "result"
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
BACKTEST_TIMEOUT = 300

# 阶段 3.2：False = 不截图、不导出 Excel（加快 research；改 True 可恢复完整落盘）
SAVE_BACKTEST_ARTIFACTS = True
# 阶段 3.2：False = 不在聚宽面板改回测区间/资金/频度（用页面上已有设置）
CONFIGURE_BACKTEST_PANEL = True

TRANSACTION_COLUMNS = [
    ("date", "日期"),
    ("time", "委托时间"),
    ("security", "品种"),
    ("stock", "标的"),
    ("transaction", "交易类型"),
    ("type", "下单类型"),
    ("amount", "成交数量"),
    ("price", "成交价"),
    ("total", "成交额"),
    ("orderAmount", "委托数量"),
    ("limitPrice", "委托价格"),
    ("status", "状态"),
    ("gains", "平仓盈亏"),
    ("commission", "手续费"),
    ("matchTime", "最后更新时间"),
]

POSITION_COLUMNS = [
    ("date", "日期"),
    ("security", "品种"),
    ("stock", "标的"),
    ("side", "多空"),
    ("amount", "数量"),
    ("closeableAmount", "可卖数量"),
    ("price", "价格"),
    ("value", "市值"),
    ("gain", "浮动盈亏"),
    ("avgCost", "累计成本"),
    ("holdCost", "持仓成本"),
    ("margin", "保证金"),
    ("dailyGains", "当日收益"),
    ("todayAmount", "当日买卖"),
    ("positionPersent", "仓位占比"),
    ("gainPercentStr", "盈亏比例"),
]

PERIOD_RETURN_COLUMNS = [
    ("date", "日期"),
    ("1month", "1个月"),
    ("3month", "3个月"),
    ("6month", "6个月"),
    ("12month", "12个月"),
]

PERFORMANCE_METRICS: list[tuple[str, str]] = [
    ("策略收益", "#tab-algorithm_period_return"),
    ("基准收益", "#tab-benchmark_period_return"),
    ("阿尔法", "#tab-alpha"),
    ("贝塔", "#tab-beta"),
    ("夏普比率", "#tab-sharpe"),
    ("索提诺比率", "#tab-sortino"),
    ("信息比率", "#tab-information"),
    ("波动率", "#tab-algo_volatility"),
    ("基准波动率", "#tab-benchmark_volatility"),
    ("最大回撤", "#tab-max_drawdown"),
]

EXTRACT_JQGRID_JS = """
(gridId) => {
  const grid = window.jQuery ? window.jQuery('#' + gridId) : null;
  if (!grid || !grid.length || !grid.jqGrid) return [];
  const stripHtml = (value) => {
    const el = document.createElement('div');
    el.innerHTML = value ?? '';
    return (el.textContent || el.innerText || '').trim();
  };
  return grid.jqGrid('getDataIDs').map(id => {
    const row = grid.jqGrid('getRowData', id);
    const cleaned = {};
    for (const [key, value] of Object.entries(row)) {
      cleaned[key] = stripHtml(String(value));
    }
    return cleaned;
  });
}
"""

FETCH_ALL_POSITIONS_JS = """
async () => {
  const api = window.backtestAPI?.positionInfo;
  const id = window.backtestId;
  if (!api || !id) return { error: '未找到 positionInfo 接口' };

  const all = [];
  let offset = 0;
  let dateOffset = '';
  let rounds = 0;

  while (rounds < 200) {
    rounds += 1;
    const qs = new URLSearchParams({
      backtestId: id,
      offset: String(offset),
      dateOffset: dateOffset,
    });
    const resp = await fetch(api + '?' + qs.toString(), { credentials: 'include' })
      .then(r => r.json());
    if (resp.code === 403) return { error: '无权限查看持仓数据' };

    const batch = resp.data?.position || [];
    if (batch.length === 0) {
      const dates = all.map(r => r.date).filter(Boolean).sort();
      return {
        rows: all,
        total: all.length,
        minDate: dates[0] || '',
        maxDate: dates[dates.length - 1] || '',
        rounds,
      };
    }

    all.push(...batch);
    offset = all.length;
    dateOffset = batch[batch.length - 1].date;
  }

  const dates = all.map(r => r.date).filter(Boolean).sort();
  return {
    rows: all,
    total: all.length,
    minDate: dates[0] || '',
    maxDate: dates[dates.length - 1] || '',
    rounds,
    truncated: true,
  };
}
"""

HTML_TAG_RE = re.compile(r"<[^>]+>")


FREQUENCY_LABEL_TO_VALUE = {
    "每天": "day",
    "分钟": "minute",
    "tick": "tick",
}
FREQUENCY_VALUE_TO_LABEL = {v: k for k, v in FREQUENCY_LABEL_TO_VALUE.items()}

SET_BACKTEST_DATES_JS = """
({ start, end }) => {
  const startInput = document.querySelector('#startTime');
  const endInput = document.querySelector('#endTime');
  if (!startInput || !endInput) return null;
  startInput.value = start + ' 00:00:00';
  endInput.value = end + ' 23:59:59';
  startInput.dispatchEvent(new Event('change', { bubbles: true }));
  endInput.dispatchEvent(new Event('change', { bubbles: true }));
  return { start: startInput.value, end: endInput.value };
}
"""


@dataclass(frozen=True)
class BacktestParams:
    start_date: str
    end_date: str
    initial_capital: int
    frequency: str  # 每天 | 分钟 | tick

    def __post_init__(self) -> None:
        if self.frequency not in FREQUENCY_LABEL_TO_VALUE:
            allowed = "、".join(FREQUENCY_LABEL_TO_VALUE)
            raise ValueError(f"回测频度必须是 {allowed}，当前为：{self.frequency}")


def get_backtest_params() -> BacktestParams:
    """读取回测参数：优先 .env，否则使用 backtest_config.py。"""
    load_env()
    frequency = os.getenv("JOINQUANT_BACKTEST_FREQUENCY", BACKTEST_FREQUENCY).strip()
    start_date = os.getenv("JOINQUANT_BACKTEST_START_DATE", BACKTEST_START_DATE).strip()
    end_date = os.getenv("JOINQUANT_BACKTEST_END_DATE", BACKTEST_END_DATE).strip()
    capital_raw = os.getenv(
        "JOINQUANT_BACKTEST_INITIAL_CAPITAL",
        str(BACKTEST_INITIAL_CAPITAL),
    ).strip()
    return BacktestParams(
        start_date=start_date,
        end_date=end_date,
        initial_capital=int(capital_raw.replace(",", "").replace("_", "")),
        frequency=frequency,
    )


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


def maybe_configure_backtest_panel(page: Page, params: BacktestParams) -> bool:
    """CONFIGURE_BACKTEST_PANEL=False 时不改聚宽回测面板。"""
    if not CONFIGURE_BACKTEST_PANEL:
        print("\n  （已跳过设置回测区间/资金/频度，使用聚宽当前面板上的值）")
        return True
    return configure_backtest_params(page, params)


def configure_backtest_params(page: Page, params: BacktestParams) -> bool:
    """在编辑器顶栏设置回测区间、初始资金、回测频度。"""
    print("\n【步骤 6】设置回测参数...")
    print(f"  区间：{params.start_date} 至 {params.end_date}")
    print(f"  初始资金：{params.initial_capital:,} 元")
    print(f"  回测频度：{params.frequency}")

    page.wait_for_selector("#startTime", timeout=15000)
    page.wait_for_selector("#endTime", timeout=15000)

    dates = page.evaluate(
        SET_BACKTEST_DATES_JS,
        {"start": params.start_date, "end": params.end_date},
    )
    if not dates:
        print("未能设置回测日期")
        return False
    step_delay(page, "设置回测区间")

    capital_input = page.locator("input[name='backtest[baseCapital]']")
    capital_input.wait_for(state="visible", timeout=10000)
    capital_input.click()
    capital_input.fill("")
    capital_input.fill(str(params.initial_capital))
    step_delay(page, "设置初始资金")

    freq_container = page.locator(".frequency-selector-ide")
    freq_container.locator(".dropdown-toggle").click()
    page.wait_for_timeout(500)
    freq_container.locator(".dropdown-menu li").filter(has_text=params.frequency).first.click()
    step_delay(page, "设置回测频度")

    expected_freq = FREQUENCY_LABEL_TO_VALUE[params.frequency]
    actual_freq = page.locator("input[name='backtest[frequency]']").input_value()
    actual_start = page.locator("#startTime").input_value()
    actual_end = page.locator("#endTime").input_value()
    actual_capital = page.locator("input[name='backtest[baseCapital]']").input_value()

    print(
        f"  平台当前值：{actual_start[:10]} ~ {actual_end[:10]}，"
        f"{int(float(actual_capital)):,} 元，"
        f"频度={FREQUENCY_VALUE_TO_LABEL.get(actual_freq, actual_freq)}"
    )

    if actual_freq != expected_freq:
        print(f"回测频度设置失败，期望 {params.frequency}，实际 {actual_freq}")
        return False

    page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_params_set.png"))
    return True


def create_result_dir(
    *,
    strategy_label: str | None = None,
    trial_meta: dict[str, Any] | None = None,
    joinquant_strategy_name: str | None = None,
) -> Path:
    """为本次回测创建结果目录，默认以本地策略文件名（stem）命名。"""
    if strategy_label is None:
        if joinquant_strategy_name is not None:
            strategy_label = strategy_label_from_trial_meta(joinquant_strategy_name, trial_meta)
        else:
            strategy_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    return allocate_result_dir(RESULT_DIR, strategy_label)


def run_backtest(page: Page) -> bool:
    """点击「运行回测」启动完整回测。"""
    print("\n【步骤 7】运行回测...")
    run_btn = page.get_by_text("运行回测", exact=True)
    run_btn.first.wait_for(state="visible", timeout=15000)
    run_btn.first.click()
    step_delay(page, "点击运行回测")
    return True


def wait_for_backtest_complete(page: Page) -> bool:
    """等待跳转到回测详情页并出现「回测完成」。"""
    print("\n【步骤 8】等待回测完成...")
    print(f"  最长等待 {BACKTEST_TIMEOUT} 秒")

    try:
        page.wait_for_url("**/algorithm/backtest/detail**", timeout=BACKTEST_TIMEOUT * 1000)
    except PlaywrightError:
        print("回测超时：未进入回测详情页")
        page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_run_timeout.png"))
        return False

    try:
        page.get_by_text("回测完成", exact=False).first.wait_for(
            state="visible", timeout=BACKTEST_TIMEOUT * 1000
        )
    except PlaywrightError:
        print("回测超时：未检测到「回测完成」")
        page.screenshot(path=str(SCREENSHOTS_DIR / "backtest_complete_timeout.png"))
        return False

    try:
        page.locator(".highcharts-container").first.wait_for(state="visible", timeout=30000)
    except PlaywrightError:
        print("  图表加载较慢，继续截图...")

    step_delay(page, "回测完成")
    print("回测详情页：", page.url)
    return True


def ensure_overview_tab(page: Page) -> None:
    """确保当前展示「收益概述」（回测完成后通常已是默认页）。"""
    active = page.locator("li.active").filter(has_text="收益概述")
    if active.count() and active.first.is_visible():
        return

    overview_link = page.locator("li").filter(has_text="收益概述").locator("a").first
    if overview_link.count() and overview_link.is_visible():
        overview_link.click()
        step_delay(page, "切换到收益概述")


def screenshot_overview(page: Page, result_dir: Path) -> Path:
    """截取收益概述整页（指标 + 回测曲线 + 每日盈亏 + 每日买卖）。"""
    print("\n【步骤 9】截图收益概述...")
    ensure_overview_tab(page)
    page.wait_for_timeout(2000)

    outfile = result_dir / "overview_full.png"
    page.screenshot(path=str(outfile), full_page=True)
    step_delay(page, "截图完成")
    print(f"截图已保存：{outfile}")
    return outfile


def open_detail_tab(page: Page, tab_selector: str, tab_name: str) -> None:
    """打开回测详情左侧标签页。"""
    tab = page.locator(tab_selector)
    tab.wait_for(state="visible", timeout=15000)
    tab.click()
    step_delay(page, f"切换到{tab_name}")


def extract_jqgrid_rows(page: Page, grid_id: str) -> list[dict]:
    """从 jqGrid 表格读取全部行数据。"""
    rows = page.evaluate(EXTRACT_JQGRID_JS, grid_id)
    return rows if isinstance(rows, list) else []


def ensure_jqgrid_fully_loaded(page: Page, grid_id: str, label: str = "") -> int:
    """
    滚动 jqGrid 虚拟列表，触发懒加载，直到行数达到 records 或不再增长。

    聚宽「每日持仓&收益」等表格初次只渲染部分行，向下滑动后才会加载剩余数据。
    """
    body_selector = f"#gview_{grid_id} .ui-jqgrid-bdiv"
    prefix = f"  [{label}] " if label else "  "

    try:
        page.wait_for_selector(body_selector, timeout=15000)
    except PlaywrightError:
        info = page.evaluate(
            """
            (gridId) => {
              const grid = window.jQuery('#' + gridId);
              if (!grid.length) return { ids: 0, records: 0 };
              return {
                ids: grid.jqGrid('getDataIDs').length,
                records: grid.jqGrid('getGridParam', 'records') || 0,
              };
            }
            """,
            grid_id,
        )
        return info.get("ids", 0)

    last_count = -1
    stable_rounds = 0

    for _ in range(40):
        page.evaluate(
            """
            (gridId) => {
              const body = document.querySelector('#gview_' + gridId + ' .ui-jqgrid-bdiv');
              if (body) body.scrollTop = body.scrollHeight;
            }
            """,
            grid_id,
        )
        page.wait_for_timeout(600)

        info = page.evaluate(
            """
            (gridId) => {
              const grid = window.jQuery('#' + gridId);
              return {
                ids: grid.jqGrid('getDataIDs').length,
                records: grid.jqGrid('getGridParam', 'records') || 0,
              };
            }
            """,
            grid_id,
        )
        ids = info["ids"]
        records = info["records"]

        if records > 0 and ids >= records:
            print(f"{prefix}已加载全部 {ids} 行")
            return ids

        if ids == last_count:
            stable_rounds += 1
            if stable_rounds >= 3:
                print(f"{prefix}行数稳定在 {ids}（records={records}）")
                return ids
        elif last_count >= 0 and ids > last_count:
            print(f"{prefix}滚动加载：{last_count} → {ids} 行")

        last_count = ids
        stable_rounds = 0

    print(f"{prefix}达到最大滚动次数，当前 {last_count} 行")
    return last_count


def normalize_grid_row(row: dict) -> dict:
    """清理 jqGrid / API 行里的 HTML 标签，统一为字符串。"""
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if value is None:
            normalized[key] = ""
        elif isinstance(value, str):
            normalized[key] = HTML_TAG_RE.sub("", value).strip()
        else:
            normalized[key] = str(value)
    return normalized


def normalize_grid_rows(rows: list[dict]) -> list[dict]:
    """批量清理 jqGrid / API 行数据。"""
    return [normalize_grid_row(row) for row in rows]


def tab_href_to_grid_id(href: str) -> str:
    """性能分析 tab href → jqGrid 表格 id，如 #tab-alpha → table-alpha。"""
    return "table-" + href.removeprefix("#tab-")


def fetch_all_positions_via_api(page: Page) -> list[dict]:
    """
    通过聚宽 positionInfo 接口分页拉取完整「每日持仓&收益」。

    页面 jqGrid 只懒加载到约 4 月，完整数据需走与 addPosition 相同的 API。
    """
    print("  通过 positionInfo 接口分页拉取...")
    result = page.evaluate(FETCH_ALL_POSITIONS_JS)
    if not isinstance(result, dict):
        raise RuntimeError("持仓接口返回异常")

    if result.get("error"):
        raise RuntimeError(str(result["error"]))

    rows = normalize_grid_rows(result.get("rows", []))
    if not rows:
        raise RuntimeError("每日持仓&收益为空")

    print(
        f"  共 {len(rows)} 条，日期 {result.get('minDate', '')} ~ {result.get('maxDate', '')}"
        f"（{result.get('rounds', 0)} 次请求）"
    )
    if result.get("truncated"):
        print("  警告：达到最大分页次数，数据可能不完整")
    return rows


def save_grid_to_excel(
    rows: list[dict],
    columns: list[tuple[str, str]],
    outfile: Path,
    sheet_name: str,
) -> None:
    """将 jqGrid 行数据按列定义保存为 Excel（单 sheet）。"""
    save_grids_to_excel([(sheet_name, rows, columns)], outfile)


def save_grids_to_excel(
    sheets: list[tuple[str, list[dict], list[tuple[str, str]]]],
    outfile: Path,
) -> None:
    """将多组 jqGrid 行数据保存为 Excel 多 sheet。"""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, rows, columns in sheets:
        ws = wb.create_sheet(title=sheet_name[:31])
        ws.append([label for _, label in columns])
        for row in rows:
            ws.append([row.get(key, "") for key, _ in columns])
    wb.save(outfile)


def save_transactions_to_excel(rows: list[dict], outfile: Path) -> None:
    """将交易详情保存为 Excel。"""
    save_grid_to_excel(rows, TRANSACTION_COLUMNS, outfile, "交易详情")


def save_trade_details(page: Page, result_dir: Path) -> Path:
    """进入「交易详情」并保存为 Excel。"""
    print("\n【步骤 10】保存交易详情...")
    open_detail_tab(page, "#transactions-tab", "交易详情")

    page.wait_for_selector("#table-transactioninfo tr.jqgrow", timeout=30000)
    page.wait_for_timeout(1000)

    ensure_jqgrid_fully_loaded(page, "table-transactioninfo", "交易详情")
    rows = extract_jqgrid_rows(page, "table-transactioninfo")
    if not rows:
        print("未读取到交易记录")
        page.screenshot(path=str(result_dir / "trade_details_empty.png"))
        raise RuntimeError("交易详情为空")

    outfile = result_dir / "trade_details.xlsx"
    save_transactions_to_excel(rows, outfile)
    step_delay(page, "保存交易详情")
    print(f"交易详情已保存：{outfile}（共 {len(rows)} 条）")
    return outfile


def save_daily_positions(page: Page, result_dir: Path) -> Path:
    """进入「每日持仓&收益」并通过 API 保存完整 Excel。"""
    print("\n【步骤 11】保存每日持仓&收益...")
    open_detail_tab(page, "#positions-tab", "每日持仓&收益")

    page.wait_for_selector("#table-positioninfo", timeout=30000)
    page.wait_for_timeout(1000)

    try:
        rows = fetch_all_positions_via_api(page)
    except RuntimeError as exc:
        print(exc)
        page.screenshot(path=str(result_dir / "daily_positions_empty.png"))
        raise

    outfile = result_dir / "daily_positions.xlsx"
    save_grid_to_excel(rows, POSITION_COLUMNS, outfile, "每日持仓收益")
    step_delay(page, "保存每日持仓&收益")
    print(f"每日持仓&收益已保存：{outfile}（共 {len(rows)} 条）")
    return outfile


def open_risk_metric(page: Page, href: str, name: str) -> None:
    """在收益概述页切换到左侧性能分析子项。"""
    ensure_overview_tab(page)
    link = page.locator(f"a.risk[href='{href}']")
    link.wait_for(state="visible", timeout=15000)
    link.click()
    step_delay(page, f"切换到{name}")


def fetch_risk_metric_rows(page: Page, grid_id: str) -> list[dict]:
    """读取性能分析 jqGrid 表格并统一清理行数据。"""
    page.wait_for_selector(f"#{grid_id} tr.jqgrow", timeout=30000)
    page.wait_for_timeout(500)
    rows = extract_jqgrid_rows(page, grid_id)
    return normalize_grid_rows(rows)


def save_performance_metrics(page: Page, result_dir: Path) -> Path:
    """保存收益概述下「策略收益」至「最大回撤」共 10 项性能分析表格。"""
    print("\n【步骤 12】保存性能分析（策略收益~最大回撤）...")
    ensure_overview_tab(page)

    sheets: list[tuple[str, list[dict], list[tuple[str, str]]]] = []
    for name, href in PERFORMANCE_METRICS:
        grid_id = tab_href_to_grid_id(href)
        open_risk_metric(page, href, name)
        rows = fetch_risk_metric_rows(page, grid_id)
        if not rows:
            page.screenshot(path=str(result_dir / f"perf_{grid_id}_empty.png"))
            raise RuntimeError(f"「{name}」数据为空")
        sheets.append((name, rows, PERIOD_RETURN_COLUMNS))
        print(f"  {name}：{len(rows)} 行")

    outfile = result_dir / "performance_metrics.xlsx"
    save_grids_to_excel(sheets, outfile)
    step_delay(page, "保存性能分析")
    print(f"性能分析已保存：{outfile}（共 {len(sheets)} 个指标）")
    return outfile


def safe_close_context(context) -> None:
    try:
        context.close()
    except PlaywrightError:
        pass


@dataclass
class BacktestRunResult:
    result_dir: Path
    manifest: dict
    editor_url: str


def apply_strategy_params_to_editor(
    page: Page,
    editor_url: str,
    sp_config: dict[str, Any],
    params: dict[str, int | float],
) -> None:
    """将可调参数写入聚宽编辑器（需策略内含 AUTORESEARCH 标记块）。"""
    from autoresearch.editor import (
        ensure_on_editor,
        read_strategy_code,
        save_and_compile_strategy,
        write_strategy_code,
    )
    from autoresearch.strategy_params import patch_strategy_source, validate_params_in_search_space

    validate_params_in_search_space(params, sp_config)
    ensure_on_editor(page, editor_url)
    code = read_strategy_code(page)
    patched = patch_strategy_source(code, params, sp_config)
    write_strategy_code(page, patched)
    save_and_compile_strategy(page)
    print(f"  已写入策略参数：{params}")


def collect_backtest_artifacts(page: Page, result_dir: Path) -> dict[str, Path | None]:
    """回测完成后导出截图与 Excel；SAVE_BACKTEST_ARTIFACTS=False 时全部跳过。"""
    if not SAVE_BACKTEST_ARTIFACTS:
        print("\n  （已跳过收益概述截图与 Excel 导出，仅写 manifest 骨架）")
        return {
            "overview_png": None,
            "trade_details_xlsx": None,
            "daily_positions_xlsx": None,
            "performance_metrics_xlsx": None,
        }
    overview_path = screenshot_overview(page, result_dir)
    trade_path = save_trade_details(page, result_dir)
    positions_path = save_daily_positions(page, result_dir)
    performance_path = save_performance_metrics(page, result_dir)
    return {
        "overview_png": overview_path,
        "trade_details_xlsx": trade_path,
        "daily_positions_xlsx": positions_path,
        "performance_metrics_xlsx": performance_path,
    }


def run_backtest_trial(
    page: Page,
    strategy_name: str,
    backtest_params: BacktestParams,
    editor_url: str,
    *,
    strategy_params: dict[str, int | float] | None = None,
    sp_config: dict[str, Any] | None = None,
    trial_meta: dict[str, Any] | None = None,
    configure_backtest: bool = False,
) -> BacktestRunResult | None:
    """
    在已登录且位于策略编辑器的前提下，执行一轮回测并生成 manifest。
    configure_backtest=True 时设置回测区间/资金/频度（阶段 2 仅首轮一次）。
    """
    if strategy_params and sp_config:
        apply_strategy_params_to_editor(page, editor_url, sp_config, strategy_params)
    else:
        from autoresearch.editor import ensure_on_editor

        ensure_on_editor(page, editor_url)

    if configure_backtest:
        if not maybe_configure_backtest_panel(page, backtest_params):
            print("回测参数设置失败")
            return None

    result_dir = create_result_dir(
        trial_meta=trial_meta,
        joinquant_strategy_name=strategy_name,
    )
    print(f"\n本次结果目录：{result_dir}")

    if not run_backtest(page):
        print("未能点击运行回测")
        return None
    if not wait_for_backtest_complete(page):
        print("回测未在预期时间内完成")
        return None

    try:
        artifact_paths = collect_backtest_artifacts(page, result_dir)
    except RuntimeError as exc:
        print(exc)
        return None

    manifest = finalize_manifest_from_result_dir(
        result_dir,
        strategy=strategy_name,
        backtest={
            "start": backtest_params.start_date,
            "end": backtest_params.end_date,
            "initial_capital": backtest_params.initial_capital,
            "frequency": backtest_params.frequency,
        },
        paths=artifact_paths,
        strategy_params=strategy_params,
        trial_meta=trial_meta,
    )
    write_run_manifest(result_dir, manifest)

    ev = manifest.get("evaluation") or {}
    metrics = manifest.get("metrics") or {}
    print(
        f"  指标：策略收益≈{metrics.get('annual_return_pct')}% "
        f"最大回撤≈{metrics.get('max_drawdown_pct')}% "
        f"passed={ev.get('passed')}"
    )
    return BacktestRunResult(result_dir=result_dir, manifest=manifest, editor_url=editor_url)


def run_backtest_from_local_file(
    page: Page,
    strategy_name: str,
    backtest_params: BacktestParams,
    editor_url: str,
    strategy_path: Path,
    *,
    trial_meta: dict[str, Any] | None = None,
    configure_backtest: bool = True,
) -> BacktestRunResult | None:
    """阶段 3：将本地策略整文件写入聚宽编辑器后回测。"""
    from autoresearch.editor import apply_strategy_from_file

    meta = {"local_strategy_file": str(strategy_path.resolve())}
    if trial_meta:
        meta = {**trial_meta, **meta}
    apply_strategy_from_file(page, editor_url, strategy_path)
    return run_backtest_trial(
        page,
        strategy_name,
        backtest_params,
        editor_url,
        trial_meta=meta,
        configure_backtest=configure_backtest,
    )


def run() -> None:
    username, password = get_credentials()
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    RESULT_DIR.mkdir(exist_ok=True)
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

        backtest_params = get_backtest_params()
        if not maybe_configure_backtest_panel(page, backtest_params):
            print("回测参数设置失败")
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        result_dir = create_result_dir(joinquant_strategy_name=strategy_name)
        print(f"\n本次结果目录：{result_dir}")

        if not run_backtest(page):
            print("未能点击运行回测")
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        if not wait_for_backtest_complete(page):
            print("回测未在预期时间内完成")
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        try:
            artifact_paths = collect_backtest_artifacts(page, result_dir)
        except RuntimeError as exc:
            print(exc)
            print("按 Enter 关闭浏览器...")
            input()
            safe_close_context(context)
            sys.exit(1)

        manifest = finalize_manifest_from_result_dir(
            result_dir,
            strategy=strategy_name,
            backtest={
                "start": backtest_params.start_date,
                "end": backtest_params.end_date,
                "initial_capital": backtest_params.initial_capital,
                "frequency": backtest_params.frequency,
            },
            paths=artifact_paths,
        )
        manifest_path = write_run_manifest(result_dir, manifest)

        print(f"\n策略回测流程已完成（{strategy_name} + 运行回测）")
        if SAVE_BACKTEST_ARTIFACTS:
            print(f"收益概述截图：{artifact_paths.get('overview_png')}")
            print(f"交易详情 Excel：{artifact_paths.get('trade_details_xlsx')}")
            print(f"每日持仓 Excel：{artifact_paths.get('daily_positions_xlsx')}")
            print(f"性能分析 Excel：{artifact_paths.get('performance_metrics_xlsx')}")
        print(f"实验清单：{manifest_path}")
        ev = manifest.get("evaluation") or {}
        metrics = manifest.get("metrics") or {}
        print(
            f"指标摘要：策略收益≈{metrics.get('annual_return_pct')}% "
            f"最大回撤≈{metrics.get('max_drawdown_pct')}%"
        )
        if ev.get("passed"):
            print("目标评估：达标")
        else:
            print(f"目标评估：未达标（gaps={ev.get('gaps')}）")
        print(f"结果目录：{result_dir}")
        print("\n浏览器保持打开。按 Enter 关闭...")
        input()
        safe_close_context(context)
        print("流程结束！")


if __name__ == "__main__":
    run()
