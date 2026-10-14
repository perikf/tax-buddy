import io
import json
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.main import app, fx_table
from backend.tests.test_parser import HDR, csv_bytes, row

DATA = Path(__file__).parent.parent.parent / "data"
client = TestClient(app)

FIXTURE = csv_bytes(
    HDR,
    row(qty="100", price="100", dt="2024-05-01, 10:00:00"),
    row(qty="-40", price="120", dt="2024-07-01, 10:00:00"),
    "Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult",
    "Open Positions,Data,Summary,Stocks,USD,AAPL,60,1",
    "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Type",
    "Financial Instrument Information,Data,Stocks,AAPL,APPLE INC,265598,US0378331005,COMMON",
    period="January 1, 2024 - December 31, 2024", generated="2025-01-10, 08:00:00",
)


def setup_module():
    if not fx_table.loaded:
        fx_table.load()


def _post(uploads, **form):
    payload = [("files", (name, content, "text/csv")) for name, content in uploads]
    data = {"start_date": "2024-04-06", "end_date": "2025-04-05", "period_label": "2024/25"}
    data.update(form)
    return client.post("/calculate", files=payload, data=data)


def meta(resp):
    return json.loads(resp.headers["x-taxbuddy-meta"])


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["fx_rates_loaded"] is True


def test_calculate_fixture_end_to_end():
    r = _post([("2024.csv", FIXTURE)])
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="TaxBuddy_CGT_2024-25.xlsx"'
    m = meta(r)
    assert m["gap_count"] == 0 and m["history_verified"] is True
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["CGT Summary", "1 STOCKS", "Pool History", "FX Detail"]
    assert wb["CGT Summary"]["B10"].value == 1  # SA108 box 23


def test_unsafe_period_label_falls_back_to_dates():
    r = _post([("a.csv", FIXTURE)], period_label='24/25€"')
    assert r.status_code == 200
    assert "2024-04-06_to_2025-04-05" in r.headers["content-disposition"]


def test_error_responses():
    r = _post([("a.csv", FIXTURE)], start_date="2025-01-01", end_date="2024-01-01")
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_DATES")
    r = _post([("x.txt", b"hi")])
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_FILE_TYPE")
    r = _post([("x.csv", b"name,age\nbob,3\n")])
    assert (r.status_code, r.json()["error"]) == (400, "NOT_IBKR_FORMAT")
    r = _post([(f"{i}.csv", FIXTURE) for i in range(11)])
    assert (r.status_code, r.json()["error"]) == (400, "TOO_MANY_FILES")


def test_spa_never_serves_outside_dist():
    for path in ("//etc/passwd", "/..%2f..%2fpyproject.toml", "/../backend/main.py"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html"), path


@pytest.mark.skipif(not (DATA / "U14562116_2024_2024.csv").exists(),
                    reason="local real statements not present")
def test_calculate_real_statements():
    uploads = [(f.name, f.read_bytes())
               for f in (DATA / "U14562116_2024_2024.csv", DATA / "U14562116_2025_2025.csv")]
    r = _post(uploads)
    assert r.status_code == 200
    m = meta(r)
    assert m["gap_count"] == 0 and m["warning_count"] >= 2
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"CGT Summary", "1 STOCKS", "Pool History", "FX Detail"} <= set(wb.sheetnames)
