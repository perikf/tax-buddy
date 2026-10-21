import pytest
from decimal import Decimal

from backend.models import ApiError
from backend.parser import merge, parse
from backend.tests.fixtures import FII_HDR, HDR, OPEN_HDR, csv_bytes, fii_row, open_row, row


def test_parse_happy_path_with_bom():
    r = parse(csv_bytes(HDR, row(), row(qty="-5", dt="2024-06-01, 09:00:00")))
    assert len(r.trades) == 2
    assert r.trades[0].quantity == Decimal(10)
    assert r.trades[0].commission == Decimal("-1")


def test_skip_rules_aggregate_warnings():
    r = parse(csv_bytes(
        HDR, row(), row(cat="Forex"), row(cat="Forex"), row(ccy="ZAR"),
        row(dt="bad-date"), row(qty="abc"), row(qty="0"), row(disc="SubTotal")))
    assert len(r.trades) == 1
    joined = " ".join(r.warnings)
    assert "Skipped 2 trade(s)" in joined and "'Forex'" in joined
    assert "'ZAR'" in joined and "Date/Time" in joined
    assert "invalid numeric" in joined and "zero quantity" in joined


def test_sections_open_positions_and_instruments():
    r = parse(csv_bytes(HDR, row(), OPEN_HDR, open_row(), open_row(sym="", disc="Total"),
                        FII_HDR, fii_row()))
    assert [(p.symbol, p.quantity) for p in r.open_positions] == [("AAPL", Decimal(25))]
    inst = r.instruments["AAPL"]
    assert (inst.isin_conid, inst.domicile) == ("US0378331005", "United States")


def test_error_codes():
    with pytest.raises(ApiError) as e:
        parse(b"name,age\nbob,3\n")
    assert e.value.error == "NOT_IBKR_FORMAT"
    with pytest.raises(ApiError) as e:
        parse(csv_bytes())
    assert e.value.error == "MISSING_TRADES_SECTION"
    with pytest.raises(ApiError) as e:
        parse(csv_bytes(HDR))
    assert e.value.error == "EMPTY_TRADES"
    bad_hdr = HDR.replace("Comm/Fee", "Comm in GBP")
    with pytest.raises(ApiError) as e:
        parse(csv_bytes(bad_hdr, row()))
    assert e.value.error == "MISSING_REQUIRED_COLUMNS"
    with pytest.raises(ApiError) as e:  # only a deficient header, no supported rows
        parse(csv_bytes(bad_hdr, row(cat="Forex")))
    assert e.value.error == "MISSING_REQUIRED_COLUMNS"


def test_deficient_subsection_tolerated_for_unsupported_rows():
    alt = "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,,Proceeds,Comm in GBP,,,,MTM in GBP,Code"
    r = parse(csv_bytes(HDR, row(), alt, row(cat="Forex", sym="GBP.USD")))
    assert len(r.trades) == 1
    assert any("Forex" in w for w in r.warnings)


def test_merge_dedupes_and_emits_independent_copies():
    twin = csv_bytes(HDR, row(), row())            # two identical fills, one statement
    overlap = csv_bytes(HDR, row(), row(sym="MSFT"))
    r = merge([parse(twin), parse(overlap)])
    aapl = [t for t in r.trades if t.symbol == "AAPL"]
    assert sorted(t.symbol for t in r.trades) == ["AAPL", "AAPL", "MSFT"]  # max-count kept
    assert aapl[0] is not aapl[1]
    assert any("duplicate" in w for w in r.warnings)


def test_concatenated_statements_keep_latest_positions_snapshot():
    stale = csv_bytes(OPEN_HDR, open_row(qty="10"), open_row(sym="MSFT", qty="5"), HDR, row())
    fresh = csv_bytes(OPEN_HDR, open_row(qty="5"),
                      HDR, row(qty="-5", dt="2025-05-01, 10:00:00"), bom=False)
    for combined in (stale + fresh, fresh + stale):   # either concatenation order
        r = parse(combined)
        assert len(r.trades) == 2
        assert [(p.symbol, p.quantity) for p in r.open_positions] == [("AAPL", Decimal(5))]


def test_reissued_statement_supersedes_same_period():
    original = csv_bytes(HDR, row(price="100"),
                         period="January 1, 2024 - December 31, 2024",
                         generated="2025-01-10, 08:00:00")
    amended = csv_bytes(HDR, row(price="101"),
                        period="January 1, 2024 - December 31, 2024",
                        generated="2025-03-01, 08:00:00")
    r = parse(original + amended)
    assert [t.price for t in r.trades] == [Decimal(101)]
    assert any("newest issue" in w for w in r.warnings)


def test_when_generated_with_timezone_suffix():
    r = parse(csv_bytes(HDR, row(), period="January 1, 2026 - October 14, 2026",
                        generated="2026-10-15, 01:59:40 EDT"))
    assert r.when_generated is not None and r.when_generated.hour == 1


def test_corporate_actions_are_flagged_not_applied():
    r = parse(csv_bytes(HDR, row(),
                        "Corporate Actions,Header,Asset Category,Currency,Report Date,Date/Time,Description,Quantity",
                        'Corporate Actions,Data,Stocks,USD,2024-06-10,"2024-06-07, 20:25:00",NVDA SPLIT 10 FOR 1,1440'))
    assert len(r.trades) == 1
    assert any("corporate action" in w for w in r.warnings)
