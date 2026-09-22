from jqdata import *

# === AUTORESEARCH_TUNABLES ===
HISTORY_DAYS = 130
MA_PERIOD = 120
MOM_SHORT = 20
MOM_MID = 45
MOM_MID_WEIGHT = 1.5
BREADTH_MIN = 8
MIN_TOP_SCORE = 0.04
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
    run_daily(market_close_check, time="14:50")


def market_close_check(context):
    score_list = []
    etf_snap = {}

    for etf in g.etf_list:
        price = attribute_history(etf, HISTORY_DAYS, "1d", ["close"])
        if len(price) < MA_PERIOD:
            continue

        close = price["close"]
        price_now = close[-1]
        pct_20 = (price_now / close[-MOM_SHORT]) - 1
        pct_45 = (price_now / close[-MOM_MID]) - 1
        ma120 = close[-MA_PERIOD:].mean()
        etf_snap[etf] = (price_now, pct_20, ma120)

        if pct_20 > 0 and pct_45 > 0:
            score_list.append((etf, pct_20 + MOM_MID_WEIGHT * pct_45))

    score_list.sort(key=lambda x: x[1], reverse=True)

    for etf in list(context.portfolio.positions.keys()):
        if etf not in etf_snap:
            order_target(etf, 0)
            continue
        price_now, pct_20, ma120 = etf_snap[etf]
        if price_now < ma120 or pct_20 < 0:
            order_target(etf, 0)

    market_ok = len(score_list) >= BREADTH_MIN and score_list[0][1] >= MIN_TOP_SCORE
    if not market_ok:
        for etf in list(context.portfolio.positions.keys()):
            order_target(etf, 0)
        return

    if len(score_list) > 0 and len(context.portfolio.positions) == 0:
        target_etf = score_list[0][0]
        cash = context.portfolio.available_cash
        current_price = get_price(target_etf, count=1, end_date=context.current_dt)["close"][0]
        amount = int(cash / current_price / 100) * 100
        if amount > 0:
            order_target(target_etf, amount)
