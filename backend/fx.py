"""GBP FX table: shipped CSV cache, freshness policy, lookups.
rate = GBP/CCY; convert = divide. Refresh the shipped file with scripts/fx_rates.py."""
import csv
import datetime as dt
import logging
from decimal import Decimal
from pathlib import Path

log = logging.getLogger("taxbuddy.fx")

CURRENCIES = ["AUD", "CAD", "CHF", "DKK", "EUR", "HKD", "JPY", "NOK", "PLN", "SEK", "USD"]
SUPPORTED = set(CURRENCIES) | {"GBP"}
CSV_PATH = Path(__file__).parent / "data" / "fx_rates.csv"
FX_START = dt.date(2015, 4, 2)
MAX_STEP_BACK_DAYS = 7


class FxTable:
    def __init__(self):
        self.rates: dict[dt.date, dict[str, Decimal]] = {}
        self._checked = False

    @property
    def loaded(self) -> bool:
        return bool(self.rates)

    @property
    def latest(self) -> dt.date | None:
        return max(self.rates) if self.rates else None

    def stale(self, today: dt.date) -> bool:
        return self.latest is None or (today - self.latest).days > MAX_STEP_BACK_DAYS

    def load(self, path: Path = CSV_PATH) -> None:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                day = dt.date.fromisoformat(row["date"])
                self.rates[day] = {c: Decimal(row[c]) for c in CURRENCIES if row.get(c)}

    def ensure_ready(self, today: dt.date | None = None) -> None:
        """Load the shipped cache; fetch newer days only if it is stale. Runs once per process."""
        if self._checked:
            return
        self._checked = True
        if not self.loaded:
            try:
                self.load()
            except OSError as e:
                log.error("FX cache missing: %s", e)
        if self.stale(today or dt.date.today()):
            try:
                self.top_up()
            except Exception as e:
                log.warning("FX top-up failed (continuing with cache): %s", e)

    def top_up(self) -> None:
        """Fetch business days after the cached latest into memory."""
        import requests

        start = (self.latest or FX_START) + dt.timedelta(days=1)
        end = dt.date.today()
        if start > end:
            return
        url = (f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}"
               f"?from=GBP&to={','.join(CURRENCIES)}")
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        new_days = resp.json().get("rates", {})
        for day_str, rates in new_days.items():
            self.rates[dt.date.fromisoformat(day_str)] = {
                c: Decimal(str(v)) for c, v in rates.items() if v is not None
            }
        log.info("FX top-up: %d new days", len(new_days))

    def get_rate(self, currency: str, day: dt.date) -> tuple[Decimal, dt.date] | None:
        """Trade-date rate, stepping back up to 7 calendar days. None if no hit."""
        if currency == "GBP":
            return Decimal(1), day
        for back in range(MAX_STEP_BACK_DAYS + 1):
            d = day - dt.timedelta(days=back)
            rate = self.rates.get(d, {}).get(currency)
            if rate is not None:
                return rate, d
        return None
