"""
Fetch historical GBP FX rates from Frankfurter.app (ECB reference rates)
and export to Excel.

Base currency: GBP
Target currencies: USD, EUR, JPY, NOK, SEK, DKK
Date range: 6 April 2024 to today

The API returns all dates in bulk requests — runs in seconds.
"""

import requests
import datetime
import sys

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl is not installed. Run:  pip install openpyxl")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────
BASE_CURRENCY = "GBP"
TARGET_CURRENCIES = ["AUD", "CAD", "CHF", "DKK", "EUR", "HKD", "JPY", "NOK", "PLN", "SEK", "USD"]
START_DATE = datetime.date(2015, 4, 6)
END_DATE = datetime.date.today()
# For testing, uncomment the next two lines to fetch just one day:
# START_DATE = datetime.date(2024, 4, 8)
# END_DATE = datetime.date(2024, 4, 8)
OUTPUT_FILE = "GBP_FX_Rates.xlsx"


# ═══════════════════════════════════════════════════════════════════════
# Frankfurter.app  (ECB reference rates, business days only)
# ═══════════════════════════════════════════════════════════════════════
def fetch_frankfurter() -> list[dict]:
    """Fetch the full time-series, chunked in 6-month windows to avoid API limits."""
    all_rates = {}  # date_str -> {ccy: rate}
    chunk_start = START_DATE

    while chunk_start <= END_DATE:
        chunk_end = min(chunk_start + datetime.timedelta(days=180), END_DATE)
        url = (
            f"https://api.frankfurter.app/{chunk_start.isoformat()}..{chunk_end.isoformat()}"
            f"?from={BASE_CURRENCY}&to={','.join(TARGET_CURRENCIES)}"
        )
        print(f"  GET {url}")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for date_str, rates in data.get("rates", {}).items():
            all_rates[date_str] = rates

        chunk_start = chunk_end + datetime.timedelta(days=1)

    rows = []
    for date_str in sorted(all_rates):
        rates = all_rates[date_str]
        row = {"date": datetime.date.fromisoformat(date_str)}
        for ccy in TARGET_CURRENCIES:
            row[ccy] = rates.get(ccy)
        rows.append(row)

    print(f"  Frankfurter: {len(rows)} business-day rows returned")
    return rows


# ═══════════════════════════════════════════════════════════════════════
# Excel output
# ═══════════════════════════════════════════════════════════════════════
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center")
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")


def write_excel(data: list[dict]):
    wb = Workbook()
    ws = wb.active
    ws.title = "GBP FX Rates (ECB)"

    headers = ["Date"] + [f"GBP/{c}" for c in TARGET_CURRENCIES]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    for row_idx, row_data in enumerate(data, 2):
        date_cell = ws.cell(row=row_idx, column=1, value=row_data["date"])
        date_cell.number_format = "DD-MMM-YYYY"
        date_cell.border = THIN_BORDER
        date_cell.alignment = CENTER

        for col_idx, ccy in enumerate(TARGET_CURRENCIES, 2):
            val = row_data.get(ccy)
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.alignment = CENTER
            if val is not None:
                cell.number_format = "#,##0.00" if ccy == "JPY" else "#,##0.000000"

    # Column widths
    ws.column_dimensions["A"].width = 15
    for col_idx in range(2, len(TARGET_CURRENCIES) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    wb.save(OUTPUT_FILE)
    print(f"\nSaved to: {OUTPUT_FILE}")
    print(f"Total rows: {len(data)}")


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Fetching {BASE_CURRENCY} rates vs {', '.join(TARGET_CURRENCIES)}")
    print(f"Date range: {START_DATE} to {END_DATE}\n")

    print("Frankfurter.app (ECB rates)...")
    data = fetch_frankfurter()

    write_excel(data)
    print("Done!")