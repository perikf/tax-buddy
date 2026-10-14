import io
import json
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.fixtures import FULL_STATEMENT

DATA = Path(__file__).parent.parent.parent / "data"
client = TestClient(app)


def _post(name, content, **form):
    data = {"start_date": "2024-04-06", "end_date": "2025-04-05", "period_label": "2024/25"}
    data.update(form)
    return client.post("/calculate", files={"file": (name, content, "text/csv")}, data=data)


def meta(resp):
    return json.loads(resp.headers["x-taxbuddy-meta"])


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["fx_rates_loaded"] is True


def test_calculate_fixture_end_to_end():
    r = _post("2024.csv", FULL_STATEMENT)
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="TaxBuddy_CGT_2024-25.xlsx"'
    m = meta(r)
    assert m["gaps"]["count"] == 0 and m["disposals"] == 1
    assert m["net_gain_gbp"] == pytest.approx(m["proceeds_gbp"] - m["costs_gbp"])
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["CGT Summary", "1 STOCKS", "Pool History", "FX Detail"]
    assert wb["CGT Summary"]["B10"].value == 1  # SA108 box 23


def test_unsafe_period_label_falls_back_to_dates():
    r = _post("a.csv", FULL_STATEMENT, period_label='24/25€"')
    assert r.status_code == 200
    assert "2024-04-06_to_2025-04-05" in r.headers["content-disposition"]


def test_error_responses():
    r = _post("a.csv", FULL_STATEMENT, start_date="2025-01-01", end_date="2024-01-01")
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_DATES")
    r = _post("x.txt", b"hi")
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_FILE_TYPE")
    r = _post("x.csv", b"name,age\nbob,3\n")
    assert (r.status_code, r.json()["error"]) == (400, "NOT_IBKR_FORMAT")


def test_spa_never_serves_outside_dist():
    for path in ("//etc/passwd", "/..%2f..%2fpyproject.toml", "/../backend/main.py"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html"), path


@pytest.mark.skipif(not (DATA / "U14562116_2024_2024.csv").exists(),
                    reason="local real statements not present")
def test_calculate_real_statements_combined_into_one_file():
    combined = (DATA / "U14562116_2024_2024.csv").read_bytes() + (DATA / "U14562116_2025_2025.csv").read_bytes()
    r = _post("full_history.csv", combined)
    assert r.status_code == 200
    m = meta(r)
    assert m["gaps"]["count"] == 0 and m["warnings"]["count"] >= 2
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"CGT Summary", "1 STOCKS", "Pool History", "FX Detail"} <= set(wb.sheetnames)
