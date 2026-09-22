from jqdata import *

# === AUTORESEARCH_TUNABLES ===
HISTORY_DAYS = 130
MA_PERIOD = 120
MOM_SHORT = 20
MOM_MID = 45
MOM_MID_WEIGHT = 1.5
TRAIL_LOOKBACK = 15
TRAIL_STOP_PCT = 0.07
PORTFOLIO_DD_LIMIT = 0.10
# === END AUTORESEARCH_TUNABLES ===


def initialize(context):
    g.etf_list = [
        "512800.XSHG",
        "512880.XSHG",
        "512010.XSHG",
        "512170.XSHG",
        "512480.XSHG",
        "515050.XSHG",
        "512720.XSHG",
        "513050.XSHG",
        "515790.XSHG",
        "515030.XSHG",
        "512690.XSHG",
        "515170.XSHG",
        "512660.XSHG",
        "512400.XSHG",
        "515220.XSHG",
        "515210.XSHG",
        "512200.XSHG",
        "516950.XSHG",
        "512980.XSHG",
        "159825.XSHE",
    ]
    g.portfolio_peak = None
    run_daily(market_close_check, time="14:50")


def _liquidate_all(context):
    for etf in list(context.portfolio.positions.keys()):
        order_target(etf, 0)


def market_close_check(context):
    total = context.portfolio.total_value
    if g.portfolio_peak is None or total > g.portfolio_peak:
        g.portfolio_peak = total
    if g.portfolio_peak > 0 and total < g.portfolio_peak * (1 - PORTFOLIO_DD_LIMIT):
        _liquidate_all(context)
        g.portfolio_peak = total
        return

    current_holdings = list(context.portfolio.positions.keys())
    score_list = []

    for etf in g.etf_list:
        price = attribute_history(etf, HISTORY_DAYS, "1d", ["close"])
        if len(price) < MA_PERIOD:
            continue

        close = price["close"]
        price_now = close[-1]
        pct_20 = (price_now / close[-MOM_SHORT]) - 1
        pct_45 = (price_now / close[-MOM_MID]) - 1
        ma120 = close[-MA_PERIOD:].mean()

        if etf in current_holdings:
            lookback = min(TRAIL_LOOKBACK, len(close))
            recent_high = close[-lookback:].max()
            trail_hit = price_now < recent_high * (1 - TRAIL_STOP_PCT)
            if price_now < ma120 or pct_20 < 0 or trail_hit:
                order_target(etf, 0)

        if pct_20 > 0 and pct_45 > 0 and price_now >= ma120:
            score_list.append((etf, pct_20 + MOM_MID_WEIGHT * pct_45))

    score_list.sort(key=lambda x: x[1], reverse=True)

    if len(score_list) > 0 and len(context.portfolio.positions) == 0:
        target_etf = score_list[0][0]
        cash = context.portfolio.available_cash
        current_price = get_price(target_etf, count=1, end_date=context.current_dt)["close"][0]
        amount = int(cash / current_price / 100) * 100
        if amount > 0:
            order_target(target_etf, amount)
