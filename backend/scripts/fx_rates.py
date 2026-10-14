"""Full-history GBP FX rebuild (Frankfurter/ECB) -> backend/data/fx_rates.csv.
Run from the repo root: .venv/bin/python backend/scripts/fx_rates.py"""
import csv
import datetime as dt
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.fx import CSV_PATH, CURRENCIES, FX_START


def main() -> None:
    rates: dict[str, dict] = {}
    chunk = FX_START
    today = dt.date.today()
    while chunk <= today:
        end = min(chunk + dt.timedelta(days=180), today)
        url = (f"https://api.frankfurter.app/{chunk.isoformat()}..{end.isoformat()}"
               f"?from=GBP&to={','.join(CURRENCIES)}")
        print(f"GET {url}")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        rates.update(resp.json().get("rates", {}))
        chunk = end + dt.timedelta(days=1)

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date"] + CURRENCIES)
        for day in sorted(rates):
            writer.writerow([day] + [rates[day].get(c, "") for c in CURRENCIES])
    print(f"Wrote {len(rates)} business days to {CSV_PATH}")


if __name__ == "__main__":
    main()
