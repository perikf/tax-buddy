# tax-buddy

A stateless web app that turns IBKR CSV Activity Statements into a downloadable UK Capital
Gains Tax report (Excel), applying HMRC matching rules (same-day → 30-day bed & breakfast →
Section 104) with GBP conversion at trade-date ECB rates. No accounts, no storage.

See [docs](docs/) for the full specification.

## Run

```
./run.sh
```

Starts the FastAPI backend on `:8000` and the Vite dev server on `:5173` (first run creates
`.venv` and installs dependencies — needs Python 3.12+ and Node 20+). Open http://localhost:5173,
drop in one IBKR Activity Statement CSV exported for your full history (date range from
your first trade to today), pick a tax year, download the report.

## Test

```
.venv/bin/pytest backend/tests
```

## Production

Vercel (stable URL): the repo deploys as-is — `vercel.json` builds the frontend and routes
`/calculate` + `/health` to the FastAPI function in `api/index.py`; `requirements.txt`
mirrors the runtime dependencies from `pyproject.toml` for Vercel's Python builder.

```
npx vercel --prod
```

Self-hosted alternative:

```
npm --prefix frontend run build
.venv/bin/uvicorn backend.main:app --port 8000
```

The backend serves the built frontend from `frontend/dist` on the same port.

## Maintenance

`backend/data/fx_rates.csv` ships with GBP/ECB rates from April 2015; startup fetches any
newer days in memory. Refresh the shipped file with `.venv/bin/python backend/scripts/fx_rates.py`.
