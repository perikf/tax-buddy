from datetime import date, datetime, timedelta
from decimal import Decimal

from backend import engine
from backend.engine import EngineResult, filter_period, run, totals, validate_history
from backend.fx import FxTable
from backend.models import OpenPosition, ParseResult, Trade

D = Decimal
BASE = date(2024, 6, 3)


def T(day_offset, qty, price, comm="0", sym="TST", ccy="GBP", hour=10):
    d = BASE + timedelta(days=day_offset)
    return Trade(asset_category="Stocks", currency=ccy, symbol=sym,
                 dt=datetime(d.year, d.month, d.day, hour),
                 quantity=D(qty), price=D(price), proceeds=D(0), commission=D(comm), code="")


def fx():
    table = FxTable()
    table.rates = {BASE + timedelta(days=i): {"USD": D("1.25")} for i in range(-10, 400)}
    return table


def gains(result):
    return [(d.matching_rule, d.quantity_disposed, d.gain_loss_gbp) for d in result.disposals]


def test_s104_sell_within_30_days_of_buy_uses_pool():
    # buy then sell 10 days later: S104, never a phantom short
    r = run([T(0, "100", "10", "-5"), T(10, "-50", "12", "-3")], fx(), {})
    assert gains(r) == [("Section 104", D(50), D("94.50"))]
    assert r.net_quantities["TST|GBP"] == D(50)
    assert [e.event_type for e in r.pool_events] == ["Acquisition", "Disposal"]


def test_same_day_before_pool():
    r = run([T(0, "100", "10"), T(5, "60", "8", hour=15), T(5, "-60", "11", hour=9)], fx(), {})
    assert gains(r) == [("Same-Day", D(60), D(180))]  # 660 - 480, pool untouched
    assert r.net_quantities["TST|GBP"] == D(100)


def test_bb_window_boundaries_and_order():
    trades = [T(-40, "100", "10"), T(0, "-100", "12"),
              T(1, "30", "11"), T(30, "20", "11.5"), T(31, "50", "13")]
    r = run(trades, fx(), {})
    assert gains(r) == [
        ("Bed & Breakfast", D(30), D(30)),    # 360 - 330, earliest first
        ("Bed & Breakfast", D(20), D(10)),    # 240 - 230, day +30 still in window
        ("Section 104", D(50), D(100)),       # 600 - 500; day +31 buy pools instead
    ]
    assert r.net_quantities["TST|GBP"] == D(50) + D(50)
    assert r.disposals[0].acquisition_date == BASE + timedelta(days=1)


def test_short_open_close_and_remainder_pools():
    trades = [T(0, "-100", "10", "-2"), T(40, "60", "8", "-1"), T(45, "50", "9")]
    r = run(trades, fx(), {})
    assert gains(r) == [
        ("Short Close", D(60), D("117.80")),  # 598.80 proceeds - 481 cost
        ("Short Close", D(40), D("39.20")),   # 399.20 - 360
    ]
    assert r.net_quantities["TST|GBP"] == D(10)
    assert [e.event_type for e in r.pool_events] == ["Short Open", "Short Close", "Short Close", "Acquisition"]
    assert r.first_trade_is_sell["TST|GBP"] is True


def test_full_cascade_one_sell():
    trades = [T(-60, "40", "10"), T(0, "10", "11", hour=8), T(0, "-100", "12", hour=12),
              T(15, "20", "11")]
    r = run(trades, fx(), {})
    rules = [g[0] for g in gains(r)]
    assert rules == ["Same-Day", "Bed & Breakfast", "Section 104"]
    assert [g[1] for g in gains(r)] == [D(10), D(20), D(40)]
    # remaining 30 opened a short
    assert r.net_quantities["TST|GBP"] == D(-30)


def test_commission_rebate_signed():
    r = run([T(0, "100", "10", "2"), T(40, "-100", "10", "1")], fx(), {})
    assert gains(r) == [("Section 104", D(100), D(3))]  # cost 998, proceeds 1001


def test_dust_guard_and_half_up_rounding():
    r = run([T(0, "3", "10", "-0.01"), T(40, "-1", "11"), T(50, "-1", "11"), T(60, "-1", "11")], fx(), {})
    costs = [d.allowable_cost_gbp for d in r.disposals]
    assert costs == [D("10.00"), D("10.01"), D("10.00")]  # avg 10.00333 kept unrounded
    assert r.net_quantities["TST|GBP"] == D(0)


def test_fractional_quantities():
    r = run([T(0, "0.5", "100"), T(40, "-0.25", "120")], fx(), {})
    assert gains(r) == [("Section 104", D("0.25"), D("5.00"))]


def test_fx_conversion_divide_and_records():
    r = run([T(0, "10", "125", sym="ACME", ccy="USD"), T(40, "-10", "150", sym="ACME", ccy="USD")], fx(), {})
    assert r.disposals[0].proceeds_gbp == D("1200.00")       # 1500 / 1.25
    assert r.disposals[0].allowable_cost_gbp == D("1000.00")
    assert len(r.fx_records) == 2 and r.fx_records[0].rate == D("1.25")


def test_no_rate_excludes_trade_loudly():
    table = FxTable()  # empty
    r = run([T(0, "10", "100", sym="ACME", ccy="USD")], table, {})
    assert not r.disposals and not r.net_quantities
    assert any("EXCLUDED" in w for w in r.warnings)
    assert r.fx_records[0].note.startswith("NO RATE")


def test_filter_period_inclusive():
    r = run([T(0, "100", "10"), T(40, "-10", "11"), T(50, "-10", "11")], fx(), {})
    start, end = BASE + timedelta(days=40), BASE + timedelta(days=50)
    assert len(filter_period(r.disposals, start, end)) == 2
    assert len(filter_period(r.disposals, start, start)) == 1
    assert not filter_period(r.disposals, end + timedelta(days=1), end + timedelta(days=9))


def test_validate_history_directions():
    result = EngineResult(net_quantities={"A|USD": D(50), "B|USD": D(10)},
                          first_trade_is_sell={"A|USD": False, "B|USD": False, "C|USD": True})
    parsed = ParseResult(open_positions=[OpenPosition("A", "USD", D(80)), OpenPosition("B", "USD", D(5))],
                         has_open_positions_section=True)
    by_symbol = {g.symbol: g for g in validate_history(result, parsed)}
    assert by_symbol["A"].gap == D(30)
    assert by_symbol["B"].gap == D(-5)
    assert any("OVERSTATED" in w for w in result.warnings) and any("UNDERSTATED" in w for w in result.warnings)


def test_validate_history_no_section_warns():
    result = EngineResult(net_quantities={"A|USD": D(5)}, first_trade_is_sell={"A|USD": True})
    gaps = validate_history(result, ParseResult())
    assert any("not verified" in w for w in result.warnings)
    assert gaps[0].first_trade_is_sell and gaps[0].open_qty is None and gaps[0].gap is None


def test_totals():
    r = run([T(0, "100", "10"), T(40, "-10", "12"), T(40, "-10", "8", hour=15), T(50, "-10", "11")], fx(), {})
    t = totals(r.disposals)
    assert (t.proceeds, t.costs, t.net) == (D(310), D(300), D(10))
    assert (t.gains, t.losses) == (D(30), D(20))
    assert t.n_disposals == 2  # two distinct (symbol, date)


def test_same_day_wins_over_short_cover_regardless_of_intraday_order():
    for sell_hour in (9, 11):  # sell before or after the same-day buy
        trades = [T(0, "-100", "10"), T(40, "50", "8", hour=10), T(40, "-50", "9", hour=sell_hour)]
        r = run(trades, fx(), {})
        assert [(d.matching_rule, d.quantity_disposed) for d in r.disposals] == [("Same-Day", D(50))]
        assert r.net_quantities["TST|GBP"] == D(-100)  # original short untouched


def test_identical_duplicate_fills_each_cover_shorts():
    # two equal-value but distinct Trade objects
    trades = [T(0, "-200", "10"), T(40, "100", "8"), T(40, "100", "8")]
    r = run(trades, fx(), {})
    assert [(d.matching_rule, d.quantity_disposed) for d in r.disposals] == [
        ("Short Close", D(100)), ("Short Close", D(100))]
    assert r.net_quantities["TST|GBP"] == D(0)
