"""HMRC CGT engine: GBP conversion, matching (same-day -> B&B -> S104 -> short),
Section 104 pools, pool events, history-gap validation, period totals. Decimal throughout."""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from backend.fx import FxTable
from backend.models import (ACQUISITION, BED_AND_BREAKFAST, DISPOSAL, SAME_DAY, SECTION_104,
                            SHORT_CLOSE, SHORT_OPEN, DisposalResult, FxRecord, HistoryGap,
                            Instrument, ParseResult, PoolEvent, Totals, Trade)

PENNY = Decimal("0.01")
BB_WINDOW = timedelta(days=30)


def q2(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def convert_trades(trades: list[Trade], fx: FxTable, warnings: list[str]) -> tuple[list[Trade], list[FxRecord]]:
    """GBP-convert in place; returns (converted trades, fx records). Trades with no rate
    are excluded from the engine and kept in FX Detail."""
    converted, records = [], []
    for t in trades:
        if t.currency == "GBP":
            t.price_gbp, t.commission_gbp, t.fx_rate, t.fx_rate_date = t.price, t.commission, Decimal(1), t.date
            converted.append(t)
            continue
        hit = fx.get_rate(t.currency, t.date)
        trade_type = "Buy" if t.quantity > 0 else "Sell"
        orig = abs(t.quantity) * t.price
        if hit is None:
            warnings.append(
                f"No {t.currency} rate within 7 days of {t.date} — {t.symbol} trade EXCLUDED from calculations.")
            records.append(FxRecord(t.date, t.symbol, trade_type, t.currency, orig,
                                    None, None, None, "NO RATE — trade excluded"))
            continue
        rate, rate_date = hit
        t.price_gbp, t.commission_gbp = t.price / rate, t.commission / rate
        t.fx_rate, t.fx_rate_date = rate, rate_date
        note = f"rate from {rate_date.isoformat()}" if rate_date != t.date else ""
        records.append(FxRecord(t.date, t.symbol, trade_type, t.currency, orig,
                                rate, rate_date, q2(orig / rate), note))
        converted.append(t)
    return converted, records


@dataclass
class Slot:
    """A buy's unmatched quantity, held out of the pool until processing passes its date."""
    trade: Trade
    remaining: Decimal

    def cost_for_qty(self, qty: Decimal) -> Decimal:
        t = self.trade
        total = abs(t.quantity) * t.price_gbp - t.commission_gbp
        return q2(total * qty / abs(t.quantity))


@dataclass
class Pool:
    """Section 104 pool; the short pool reuses it with cost meaning proceeds."""
    quantity: Decimal = Decimal(0)
    total_cost_gbp: Decimal = Decimal(0)

    @property
    def avg_cost(self) -> Decimal:
        return self.total_cost_gbp / self.quantity if self.quantity else Decimal(0)

    def add(self, qty: Decimal, cost_gbp: Decimal) -> None:
        self.quantity += qty
        self.total_cost_gbp += cost_gbp

    def remove(self, qty: Decimal) -> Decimal:
        cost_removed = q2(self.avg_cost * qty)
        self.quantity -= qty
        self.total_cost_gbp -= cost_removed
        if self.quantity == 0:
            self.total_cost_gbp = Decimal(0)
        return cost_removed


@dataclass
class EngineResult:
    disposals: list[DisposalResult] = field(default_factory=list)
    pool_events: list[PoolEvent] = field(default_factory=list)
    fx_records: list[FxRecord] = field(default_factory=list)
    net_quantities: dict[str, Decimal] = field(default_factory=dict)   # long − short, per key
    first_trade_is_sell: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def run(trades: list[Trade], fx: FxTable, instruments: dict[str, Instrument]) -> EngineResult:
    result = EngineResult()
    converted, result.fx_records = convert_trades(sorted(trades, key=lambda t: t.dt), fx, result.warnings)
    by_key: dict[str, list[Trade]] = {}
    for t in converted:
        by_key.setdefault(t.key, []).append(t)
    for key, asset_trades in sorted(by_key.items()):
        _process_asset(key, asset_trades, instruments, result)
    return result


def _process_asset(key: str, trades: list[Trade], instruments: dict[str, Instrument],
                   result: EngineResult) -> None:
    symbol = trades[0].symbol
    info = instruments.get(symbol, Instrument())
    pool, short_pool = Pool(), Pool()
    slots = [Slot(t, abs(t.quantity)) for t in trades if t.quantity > 0]
    slot_dates = [s.trade.date for s in slots]   # ascending; drives the window slices
    live = 0                                     # slots[:live] are flushed
    result.first_trade_is_sell[key] = trades[0].quantity < 0

    def emit_event(event_type: str, day: date, qty_delta: Decimal, cost_delta: Decimal, short: bool = False) -> None:
        p = short_pool if short else pool
        result.pool_events.append(PoolEvent(
            date=day, symbol=symbol, asset_category=trades[0].asset_category,
            event_type=event_type, quantity_delta=qty_delta, cost_delta_gbp=cost_delta,
            pool_quantity_after=-p.quantity if short else p.quantity,
            pool_cost_after_gbp=p.total_cost_gbp, average_cost_after_gbp=q2(p.avg_cost)))

    def emit_disposal(sell: Trade, qty: Decimal, rule: str, acq_date: date | None,
                      allowable: Decimal, proceeds: Decimal | None = None) -> None:
        proportion = qty / abs(sell.quantity)
        if proceeds is None:
            proceeds = q2(qty * sell.price_gbp + sell.commission_gbp * proportion)
        commission = q2(abs(sell.commission_gbp) * proportion)
        result.disposals.append(DisposalResult(
            disposal_date=sell.date, symbol=symbol, asset_category=sell.asset_category,
            quantity_disposed=qty, matching_rule=rule, acquisition_date=acq_date,
            proceeds_gbp=proceeds, allowable_cost_gbp=allowable, commission_gbp=commission,
            gain_loss_gbp=proceeds - allowable, orig_currency=sell.currency,
            proceeds_orig=qty * sell.price, fx_rate=sell.fx_rate, fx_rate_date=sell.fx_rate_date,
            description=info.description, isin_conid=info.isin_conid, domicile=info.domicile))

    def flush(up_to: date | None) -> None:
        """Move spent-date slots on: cover outstanding shorts first, pool the rest."""
        nonlocal live
        while live < len(slots) and (up_to is None or slot_dates[live] < up_to):
            slot = slots[live]
            live += 1
            if slot.remaining > 0 and short_pool.quantity > 0:
                match = min(slot.remaining, short_pool.quantity)
                proceeds = q2(short_pool.avg_cost * match)
                short_pool.remove(match)
                cost = slot.cost_for_qty(match)
                slot.remaining -= match
                emit_disposal(slot.trade, match, SHORT_CLOSE, None, allowable=cost, proceeds=proceeds)
                emit_event(SHORT_CLOSE, slot.trade.date, match, -proceeds, short=True)
            if slot.remaining > 0:
                cost = slot.cost_for_qty(slot.remaining)
                pool.add(slot.remaining, cost)
                emit_event(ACQUISITION, slot.trade.date, slot.remaining, cost)
                slot.remaining = Decimal(0)

    def take_from_slots(sell: Trade, remaining: Decimal, lo: int, hi: int, rule: str) -> Decimal:
        for slot in slots[lo:hi]:
            if remaining <= 0:
                break
            match = min(remaining, slot.remaining)
            if match <= 0:
                continue
            cost = slot.cost_for_qty(match)
            slot.remaining -= match
            remaining -= match
            emit_disposal(sell, match, rule, slot.trade.date, allowable=cost)
        return remaining

    for t in trades:
        flush(t.date)
        if t.quantity > 0:
            continue
        remaining = abs(t.quantity)
        # 1. same-day
        remaining = take_from_slots(t, remaining, bisect_left(slot_dates, t.date, lo=live),
                                    bisect_right(slot_dates, t.date, lo=live), SAME_DAY)
        # 2. bed & breakfast, earliest first
        remaining = take_from_slots(t, remaining, bisect_right(slot_dates, t.date, lo=live),
                                    bisect_right(slot_dates, t.date + BB_WINDOW, lo=live), BED_AND_BREAKFAST)
        # 3. section 104 pool
        if remaining > 0 and pool.quantity > 0:
            match = min(remaining, pool.quantity)
            cost = pool.remove(match)
            remaining -= match
            emit_disposal(t, match, SECTION_104, None, allowable=cost)
            emit_event(DISPOSAL, t.date, -match, -cost)
        # 4. excess opens a short
        if remaining > 0:
            proportion = remaining / abs(t.quantity)
            proceeds = q2(remaining * t.price_gbp + t.commission_gbp * proportion)
            short_pool.add(remaining, proceeds)
            emit_event(SHORT_OPEN, t.date, -remaining, proceeds, short=True)
    flush(None)

    result.net_quantities[key] = pool.quantity - short_pool.quantity


def validate_history(result: EngineResult, parsed: ParseResult) -> list[HistoryGap]:
    """Net position vs IBKR open positions; any mismatch or sell-first asset is flagged.
    Appends warnings to result.warnings. Never blocks."""
    nets, first_sell = result.net_quantities, result.first_trade_is_sell
    if not parsed.has_open_positions_section:
        result.warnings.append("No Open Positions section found — history completeness not verified.")
        return [HistoryGap(key.split("|")[0], nets[key], None, None, True)
                for key, is_sell in first_sell.items() if is_sell]

    gaps = []
    open_by_key = {p.key: p for p in parsed.open_positions}
    for key in sorted(set(nets) | set(open_by_key)):
        net_qty = nets.get(key, Decimal(0))
        open_qty = open_by_key[key].quantity if key in open_by_key else Decimal(0)
        if net_qty != open_qty or first_sell.get(key, False):
            gaps.append(HistoryGap(key.split("|")[0], net_qty, open_qty, open_qty - net_qty,
                                   first_sell.get(key, False)))
    for g in gaps:
        if g.gap and g.gap > 0:
            result.warnings.append(f"{g.symbol}: pool {g.pool_qty} < IBKR holds {g.open_qty} — "
                                   f"missing buys, gains may be OVERSTATED.")
        elif g.gap and g.gap < 0:
            result.warnings.append(f"{g.symbol}: pool {g.pool_qty} > IBKR holds {g.open_qty} — "
                                   f"missing sells, gains may be UNDERSTATED.")
        if g.first_trade_is_sell:
            result.warnings.append(f"{g.symbol}: first trade in history is a sell — earlier buys are missing.")
    return gaps


def filter_period(disposals: list[DisposalResult], start: date, end: date) -> list[DisposalResult]:
    return [d for d in disposals if start <= d.disposal_date <= end]


def totals(disposals: list[DisposalResult]) -> Totals:
    return Totals(
        proceeds=sum((d.proceeds_gbp for d in disposals), Decimal(0)),
        costs=sum((d.allowable_cost_gbp for d in disposals), Decimal(0)),
        gains=sum((d.gain_loss_gbp for d in disposals if d.gain_loss_gbp > 0), Decimal(0)),
        losses=sum((-d.gain_loss_gbp for d in disposals if d.gain_loss_gbp < 0), Decimal(0)),
        n_disposals=len({(d.symbol, d.disposal_date) for d in disposals}),
    )
