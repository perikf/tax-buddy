"""IBKR tagged-row CSV -> statements -> merged ParseResult. IBKR exports at most a
year per statement, so a full history arrives as several files (each may also hold
several statements back-to-back); merge() combines them all. Raises ApiError on
structural problems."""
import csv
import dataclasses
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import reduce
from operator import or_

from backend.fx import SUPPORTED
from backend.models import ApiError, Instrument, OpenPosition, ParseResult, Trade

REQUIRED_TRADE_COLUMNS = [
    "DataDiscriminator", "Asset Category", "Currency", "Symbol", "Date/Time",
    "Quantity", "T. Price", "C. Price", "Proceeds", "Comm/Fee", "Basis",
    "Realized P/L", "Realized P/L %", "MTM P/L", "Code",
]
DECIMAL_COLUMNS = ["Quantity", "T. Price", "Proceeds", "Comm/Fee"]
SUPPORTED_CATEGORIES = {"Stocks"}

DOMICILES = {
    "US": "United States", "IE": "Ireland", "GB": "United Kingdom", "JP": "Japan",
    "DE": "Germany", "FR": "France", "NL": "Netherlands", "CH": "Switzerland",
    "CA": "Canada", "AU": "Australia", "LU": "Luxembourg", "DK": "Denmark",
    "SE": "Sweden", "NO": "Norway", "PL": "Poland", "HK": "Hong Kong",
    "KY": "Cayman Islands", "BM": "Bermuda", "JE": "Jersey", "GG": "Guernsey",
}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding).replace("\ufeff", "")
        except UnicodeDecodeError:
            continue
    raise ApiError("INVALID_ENCODING", "File is neither UTF-8 nor Latin-1.")


def _separator(text: str) -> str:
    first = text.partition("\n")[0]
    return ";" if ";" in first and "," not in first else ","


def _dec(value: str) -> Decimal:
    return Decimal(value.replace(",", "").strip())


def _parse_dt(value: str) -> datetime:
    value = re.sub(r"\s+[A-Z]{2,5}$", "", value.strip())   # drop a trailing timezone token (EDT, BST…)
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(value)


def _domicile(isin: str) -> str:
    prefix = isin[:2]
    return DOMICILES.get(prefix, prefix) if prefix.isalpha() else ""


def _header_map(payload: list[str]) -> dict[str, int]:
    return {name.strip(): i for i, name in enumerate(payload)}


def _col(row: list[str], header: dict[str, int], name: str) -> str:
    idx = header.get(name)
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def parse(raw: bytes, filename: str = "") -> ParseResult:
    return merge(statements(raw, filename))


def statements(raw: bytes, filename: str = "") -> list[ParseResult]:
    """Every statement in one file, parsed separately."""
    text = _decode(raw)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=_separator(text))
            if len(r) >= 2 and r[0].strip() and r[1].strip()]
    if not rows:
        raise ApiError("NOT_IBKR_FORMAT", "No tagged section rows found — not an IBKR Activity Statement.")
    sections = {r[0].strip() for r in rows}
    if "Trades" not in sections:
        if "Statement" in sections:
            raise ApiError("MISSING_TRADES_SECTION", "Statement has no Trades section.")
        raise ApiError("NOT_IBKR_FORMAT", "No Trades or Statement section — not an IBKR Activity Statement.")

    starts = [i for i, r in enumerate(rows)
              if r[0].strip() == "Statement" and r[1].strip() == "Header"]
    bounds = starts or [0]
    chunks = [rows[s:e] for s, e in zip(bounds, bounds[1:] + [len(rows)])]
    tag = f" [{filename}]" if filename else ""
    return [_parse_statement(chunk, tag) for chunk in chunks]


def _parse_statement(rows: list[list[str]], tag: str) -> ParseResult:
    result = ParseResult()
    trades_header: dict[str, int] | None = None
    section_header: dict[str, int] = {}
    saw_full_header = False
    missing_columns: list[str] = []
    skips = Counter()

    for row in rows:
        section, rowtype, payload = row[0].strip(), row[1].strip(), row[2:]

        if section == "Trades":
            if rowtype == "Header":
                trades_header = _header_map(payload)
                missing_columns = [c for c in REQUIRED_TRADE_COLUMNS if c not in trades_header]
                saw_full_header = saw_full_header or not missing_columns
            elif rowtype == "Data" and trades_header:
                if missing_columns:
                    category = _col(payload, trades_header, "Asset Category")
                    if category in SUPPORTED_CATEGORIES:
                        raise ApiError("MISSING_REQUIRED_COLUMNS",
                                       f"Trades section missing columns: {', '.join(missing_columns)}")
                    skips[f"unsupported asset category '{category}'"] += 1
                else:
                    trade = _parse_trade(payload, trades_header, result.warnings, skips, tag)
                    if trade:
                        result.trades.append(trade)

        elif section == "Statement" and rowtype == "Data" and len(payload) >= 2:
            if payload[0].strip() == "Period":
                result.period = payload[1].strip()
            elif payload[0].strip() == "WhenGenerated":
                try:
                    result.when_generated = _parse_dt(payload[1])
                except ValueError:
                    pass

        elif section in ("Open Positions", "Financial Instrument Information"):
            if rowtype == "Header":
                section_header = _header_map(payload)
            elif rowtype == "Data" and section_header:
                if section == "Open Positions":
                    _parse_open_position(payload, section_header, result)
                else:
                    _parse_instrument(payload, section_header, result)

    if not saw_full_header:
        if trades_header is None:
            raise ApiError("MISSING_TRADES_SECTION", "Trades section has no Header row.")
        raise ApiError("MISSING_REQUIRED_COLUMNS",
                       f"Trades section missing columns: {', '.join(missing_columns)}")
    result.warnings.extend(f"Skipped {n} trade(s){tag}: {reason}." for reason, n in sorted(skips.items()))
    if not result.trades:
        raise ApiError("EMPTY_TRADES", "Trades section has no Order rows.")
    return result


def _parse_trade(row: list[str], header: dict[str, int], warnings: list[str],
                 skips: Counter, tag: str) -> Trade | None:
    if _col(row, header, "DataDiscriminator") != "Order":
        return None
    category = _col(row, header, "Asset Category")
    currency = _col(row, header, "Currency")
    symbol = _col(row, header, "Symbol")
    label = f"{symbol or '?'} {_col(row, header, 'Date/Time')}{tag}"

    if category not in SUPPORTED_CATEGORIES:
        skips[f"unsupported asset category '{category}'"] += 1
        return None
    if currency not in SUPPORTED:
        skips[f"unsupported currency '{currency}'"] += 1
        return None
    if not symbol:
        warnings.append(f"Skipped trade on {_col(row, header, 'Date/Time')}{tag}: blank symbol.")
        return None
    try:
        dt = _parse_dt(_col(row, header, "Date/Time"))
    except ValueError:
        warnings.append(f"Skipped {label}: unparseable Date/Time.")
        return None
    try:
        quantity, price, proceeds, commission = (_dec(_col(row, header, c)) for c in DECIMAL_COLUMNS)
    except (InvalidOperation, ValueError):
        warnings.append(f"Skipped {label}: invalid numeric field.")
        return None
    if quantity == 0:
        warnings.append(f"Skipped {label}: zero quantity.")
        return None

    return Trade(asset_category=category, currency=currency, symbol=symbol, dt=dt,
                 quantity=quantity, price=price, proceeds=proceeds, commission=commission,
                 code=_col(row, header, "Code"))


def _parse_open_position(row: list[str], header: dict[str, int], result: ParseResult) -> None:
    result.has_open_positions_section = True
    if header.get("DataDiscriminator") is not None and _col(row, header, "DataDiscriminator") != "Summary":
        return
    if _col(row, header, "Asset Category") not in SUPPORTED_CATEGORIES:
        return
    try:
        qty = _dec(_col(row, header, "Quantity"))
    except (InvalidOperation, ValueError):
        return
    result.open_positions.append(OpenPosition(
        symbol=_col(row, header, "Symbol"), currency=_col(row, header, "Currency"), quantity=qty,
    ))


def _parse_instrument(row: list[str], header: dict[str, int], result: ParseResult) -> None:
    if _col(row, header, "Asset Category") not in SUPPORTED_CATEGORIES:
        return
    isin = _col(row, header, "Security ID")
    for symbol in _col(row, header, "Symbol").split(","):
        symbol = symbol.strip()
        if symbol:
            result.instruments[symbol] = Instrument(
                description=_col(row, header, "Description"),
                isin_conid=isin or _col(row, header, "Conid"),
                domicile=_domicile(isin),
            )


def _latest_trade_dt(r: ParseResult) -> datetime:
    return max((t.dt for t in r.trades), default=datetime.min)


def _drop_superseded(results: list[ParseResult], warnings: list[str]) -> list[ParseResult]:
    """Keep only the newest issue (WhenGenerated) of each Period."""
    by_period: dict[str, ParseResult] = {}
    kept = []
    for r in results:
        if not r.period:
            kept.append(r)
            continue
        other = by_period.get(r.period)
        if other is None:
            by_period[r.period] = r
            continue
        if (r.when_generated or datetime.min) > (other.when_generated or datetime.min):
            by_period[r.period] = r
        warnings.append(f"Statement for {r.period} uploaded twice — kept the newest issue.")
    return kept + list(by_period.values())


def merge(results: list[ParseResult]) -> ParseResult:
    """Merge statements from any number of files, in any order. Trades identical across
    statements collapse to the max per-statement count; kept trades are independent
    copies; Open Positions come from the statement with the latest trade date."""
    if len(results) == 1:
        return results[0]

    merged = ParseResult()
    results = _drop_superseded(results, merged.warnings)
    for r in results:
        merged.warnings.extend(r.warnings)
        merged.instruments.update(r.instruments)

    counters = []
    by_key: dict[tuple, Trade] = {}
    for r in results:
        counter = Counter()
        for t in r.trades:
            k = (t.symbol, t.currency, t.dt, t.quantity, t.price, t.proceeds, t.commission, t.code)
            counter[k] += 1
            by_key[k] = t
        counters.append(counter)

    kept = reduce(or_, counters, Counter())
    total, kept_total = sum(sum(c.values()) for c in counters), sum(kept.values())
    for k, n in kept.items():
        merged.trades.extend(dataclasses.replace(by_key[k]) for _ in range(n))
    if total > kept_total:
        merged.warnings.append(
            f"Overlapping statements: {total - kept_total} duplicate trade rows collapsed.")

    merged.trades.sort(key=lambda t: t.dt)
    latest = max((r for r in results if r.has_open_positions_section),
                 key=_latest_trade_dt, default=None)
    if latest:
        merged.open_positions = latest.open_positions
        merged.has_open_positions_section = True
    return merged
