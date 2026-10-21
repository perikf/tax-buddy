# tax-buddy

A stateless web app that turns an IBKR CSV Activity Statement into a downloadable UK Capital
Gains Tax report (Excel), applying HMRC matching rules (same-day → 30-day bed & breakfast →
Section 104) with GBP conversion at trade-date ECB rates. No accounts, no storage.

See [docs](docs/) for the specification.

## Run

```
./run.sh
```

Creates `.venv`, installs dependencies, and starts the FastAPI backend on `:8000` with the Vite
dev server on `:5173` (needs Python 3.12+ and Node 20+). Open http://localhost:5173, drop in your
IBKR Activity Statement CSVs — one per year since your first purchase (IBKR exports at most 365 days
per statement) — pick a tax year, download the report.

## Test

```
.venv/bin/pytest backend/tests
```

## Deploy

Vercel: the repo deploys as-is. `vercel.json` builds the frontend into `frontend/dist`; Vercel's
Python preset serves the FastAPI app from `api/index.py` for everything that isn't a static file.
`requirements.txt` just points at this project so `pyproject.toml` stays the only dependency list.

```
npx vercel --prod
```

Self-hosted: build the frontend, then run the backend — it serves `frontend/dist` itself.

```
npm --prefix frontend run build
.venv/bin/uvicorn backend.main:app --port 8000
```

## FX rates

`backend/data/fx_rates.csv` ships GBP/ECB rates from April 2015. The `FX refresh` GitHub Actions
workflow tops it up each weekday and commits; run it manually from the Actions tab or with
`.venv/bin/python backend/scripts/fx_rates.py`. The app only fetches rates itself when the shipped
cache is more than a week stale.

## License

[MIT](LICENSE)
