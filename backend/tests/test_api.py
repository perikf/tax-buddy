import io
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.fixtures import FULL_STATEMENT, STATEMENT_2024, STATEMENT_2025

client = TestClient(app)


def _post(*uploads, **form):
    data = {"start_date": "2024-04-06", "end_date": "2025-04-05", "period_label": "2024/25"}
    data.update(form)
    return client.post("/calculate", data=data,
                       files=[("files", (name, content, "text/csv")) for name, content in uploads])


def meta(resp):
    return json.loads(resp.headers["x-taxbuddy-meta"])


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["fx_rates_loaded"] is True


def test_calculate_fixture_end_to_end():
    r = _post(("2024.csv", FULL_STATEMENT))
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="TaxBuddy_CGT_2024-25.xlsx"'
    m = meta(r)
    assert m["gaps"]["count"] == 0 and m["disposals"] == 1
    assert m["net_gain_gbp"] == pytest.approx(m["proceeds_gbp"] - m["costs_gbp"])
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["CGT Summary", "1 STOCKS", "Pool History", "FX Detail"]
    assert wb["CGT Summary"]["B10"].value == 1  # SA108 box 23


def test_yearly_files_merge_in_any_order():
    for uploads in ((("2024.csv", STATEMENT_2024), ("2025.csv", STATEMENT_2025)),
                    (("2025.csv", STATEMENT_2025), ("2024.csv", STATEMENT_2024))):
        r = _post(*uploads)
        assert r.status_code == 200, r.text
        m = meta(r)
        assert m["disposals"] == 1 and m["gaps"]["count"] == 0  # pool 60 == latest snapshot


def test_upload_caps():
    r = _post(*[(f"{i}.csv", STATEMENT_2024) for i in range(26)])
    assert (r.status_code, r.json()["error"]) == (400, "TOO_MANY_FILES")
    r = _post(("big.csv", b"x" * (int(4.5 * 1024 * 1024) + 1)))
    assert (r.status_code, r.json()["error"]) == (400, "FILE_TOO_LARGE")


def test_unsafe_period_label_falls_back_to_dates():
    r = _post(("a.csv", FULL_STATEMENT), period_label='24/25€"')
    assert r.status_code == 200
    assert "2024-04-06_to_2025-04-05" in r.headers["content-disposition"]


def test_error_responses():
    r = _post(("a.csv", FULL_STATEMENT), start_date="2025-01-01", end_date="2024-01-01")
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_DATES")
    r = _post(("x.txt", b"hi"))
    assert (r.status_code, r.json()["error"]) == (400, "INVALID_FILE_TYPE")
    r = _post(("x.csv", b"name,age\nbob,3\n"))
    assert (r.status_code, r.json()["error"]) == (400, "NOT_IBKR_FORMAT")


def test_spa_never_serves_outside_dist():
    for path in ("//etc/passwd", "/..%2f..%2fpyproject.toml", "/../backend/main.py"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html"), path
