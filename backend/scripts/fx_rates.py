"""Top up backend/data/fx_rates.csv with missing ECB business days (full fetch when
the file is absent). Run from the repo root: .venv/bin/python backend/scripts/fx_rates.py"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.fx import CSV_PATH, CURRENCIES, FxTable


def main() -> None:
    table = FxTable()
    if CSV_PATH.exists():
        table.load()
        print(f"Loaded {len(table.rates)} days (latest {table.latest})")
    table.top_up()
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date"] + CURRENCIES)
        for day in sorted(table.rates):
            row = table.rates[day]
            writer.writerow([day.isoformat()] + [row.get(c, "") for c in CURRENCIES])
    print(f"Wrote {len(table.rates)} days to {CSV_PATH} (latest {table.latest})")


if __name__ == "__main__":
    main()
