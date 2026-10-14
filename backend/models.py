"""Dataclasses and API exceptions."""
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


class ApiError(Exception):
    """Maps to an HTTP 400 with body {error, message}."""

    def __init__(self, error: str, message: str):
        self.error = error
        self.message = message
        super().__init__(message)


@dataclass
class Trade:
    asset_category: str
    currency: str
    symbol: str
    dt: dt.datetime
    quantity: Decimal          # > 0 buy, < 0 sell
    price: Decimal             # T. Price, trade currency
    proceeds: Decimal
    commission: Decimal        # signed: negative = cost, positive = rebate
    code: str
    # set by FX conversion
    price_gbp: Decimal | None = None
    commission_gbp: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_rate_date: dt.date | None = None
    # derived once; hot fields for the engine
    date: dt.date = field(init=False)
    key: str = field(init=False)

    def __post_init__(self):
        self.date = self.dt.date()
        self.key = f"{self.symbol}|{self.currency}"


@dataclass
class Instrument:
    symbol: str
    description: str = ""
    isin_conid: str = ""
    domicile: str = ""


@dataclass
class OpenPosition:
    symbol: str
    currency: str
    quantity: Decimal

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.currency}"


@dataclass
class ParseResult:
    trades: list[Trade] = field(default_factory=list)
    open_positions: list[OpenPosition] = field(default_factory=list)
    instruments: dict[str, Instrument] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    has_open_positions_section: bool = False
    period: str = ""           # Statement section: Period
    when_generated: str = ""   # Statement section: WhenGenerated


@dataclass
class DisposalResult:
    disposal_date: dt.date
    symbol: str
    asset_category: str
    quantity_disposed: Decimal
    matching_rule: str         # Same-Day | Bed & Breakfast | Section 104 | Short Close
    acquisition_date: dt.date | None
    proceeds_gbp: Decimal
    allowable_cost_gbp: Decimal
    commission_gbp: Decimal
    gain_loss_gbp: Decimal
    orig_currency: str
    proceeds_orig: Decimal
    fx_rate: Decimal | None
    fx_rate_date: dt.date | None
    description: str = ""
    isin_conid: str = ""
    domicile: str = ""


@dataclass
class PoolEvent:
    date: dt.date
    symbol: str
    asset_category: str
    event_type: str            # Acquisition | Disposal | Short Open | Short Close
    quantity_delta: Decimal
    cost_delta_gbp: Decimal
    pool_quantity_after: Decimal
    pool_cost_after_gbp: Decimal
    average_cost_after_gbp: Decimal


@dataclass
class FxRecord:
    trade_date: dt.date
    symbol: str
    trade_type: str            # Buy | Sell
    currency: str
    orig_amount: Decimal
    rate: Decimal | None
    rate_date: dt.date | None
    gbp_amount: Decimal | None
    note: str = ""


@dataclass
class HistoryGap:
    symbol: str
    pool_qty: Decimal
    open_qty: Decimal | None   # None: no Open Positions section to compare against
    gap: Decimal | None
    first_trade_is_sell: bool = False
