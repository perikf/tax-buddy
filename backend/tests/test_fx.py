from datetime import date
from decimal import Decimal

from backend.fx import FxTable


def _table(latest: date) -> FxTable:
    t = FxTable()
    t.rates = {latest: {"USD": Decimal("1.25")}}
    return t


def test_fresh_cache_never_fetches(monkeypatch):
    t = _table(date(2026, 1, 5))
    monkeypatch.setattr(t, "top_up", lambda: (_ for _ in ()).throw(AssertionError("must not fetch")))
    t.ensure_ready(today=date(2026, 1, 10))
    assert t.latest == date(2026, 1, 5)


def test_stale_cache_fetches_once_per_process(monkeypatch):
    t = _table(date(2025, 12, 1))
    calls = []
    monkeypatch.setattr(t, "top_up", lambda: calls.append(1))
    t.ensure_ready(today=date(2026, 1, 10))
    t.ensure_ready(today=date(2026, 1, 10))
    assert calls == [1]


def test_fetch_failure_is_swallowed(monkeypatch):
    t = _table(date(2025, 12, 1))
    monkeypatch.setattr(t, "top_up", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    t.ensure_ready(today=date(2026, 1, 10))
    assert t.loaded


def test_get_rate_steps_back_and_gbp_passthrough():
    t = _table(date(2026, 1, 2))
    assert t.get_rate("USD", date(2026, 1, 4)) == (Decimal("1.25"), date(2026, 1, 2))
    assert t.get_rate("USD", date(2026, 1, 20)) is None
    assert t.get_rate("GBP", date(2026, 1, 20)) == (Decimal(1), date(2026, 1, 20))
