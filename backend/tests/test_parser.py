import pytest
from decimal import Decimal

from backend.models import ApiError
from backend.parser import merge, parse

HDR = ("Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,"
       "Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,"
       "Realized P/L %,MTM P/L,Code")


def row(sym="AAPL", dt="2024-05-01, 10:00:00", qty="10", price="100", comm="-1",
        cat="Stocks", ccy="USD", disc="Order"):
    return (f'Trades,Data,{disc},{cat},{ccy},{sym},"{dt}",{qty},{price},99,'
            f"-1000,{comm},1000,0,0,0,O")


def csv_bytes(*lines, bom=True, period="", generated=""):
    head = "Statement,Header,Field Name,Field Value\nStatement,Data,BrokerName,IBKR\n"
    if period:
        head += f'Statement,Data,Period,"{period}"\n'
    if generated:
        head += f'Statement,Data,WhenGenerated,"{generated}"\n'
    return (("﻿" if bom else "") + head + "\n".join(lines) + "\n").encode()


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
    r = parse(csv_bytes(
        HDR, row(),
        "Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult",
        "Open Positions,Data,Summary,Stocks,USD,AAPL,25,1",
        "Open Positions,Data,Total,Stocks,USD,,25,1",
        "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Type",
        "Financial Instrument Information,Data,Stocks,AAPL,APPLE INC,265598,US0378331005,COMMON"))
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


def test_deficient_subsection_tolerated_for_unsupported_rows():
    alt = "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,,Proceeds,Comm in GBP,,,,MTM in GBP,Code"
    r = parse(csv_bytes(HDR, row(), alt, row(cat="Forex", sym="GBP.USD")))
    assert len(r.trades) == 1
    assert any("Forex" in w for w in r.warnings)


def test_merge_dedupes_and_emits_independent_copies():
    twin = csv_bytes(HDR, row(), row())            # two identical fills, one file
    overlap = csv_bytes(HDR, row(), row(sym="MSFT"))
    r = merge([parse(twin), parse(overlap)])
    aapl = [t for t in r.trades if t.symbol == "AAPL"]
    assert sorted(t.symbol for t in r.trades) == ["AAPL", "AAPL", "MSFT"]  # max-count kept
    assert aapl[0] is not aapl[1]                  # engine must see distinct objects
    assert any("duplicate" in w for w in r.warnings)


def test_concatenated_statements_keep_latest_positions_snapshot():
    open_pos = ["Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult"]
    stale = csv_bytes(*open_pos, "Open Positions,Data,Summary,Stocks,USD,AAPL,10,1",
                      "Open Positions,Data,Summary,Stocks,USD,MSFT,5,1", HDR, row())
    fresh = csv_bytes(*open_pos, "Open Positions,Data,Summary,Stocks,USD,AAPL,5,1",
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
    r = merge([parse(original), parse(amended)])
    assert [t.price for t in r.trades] == [Decimal(101)]
    assert any("newest issue" in w for w in r.warnings)
