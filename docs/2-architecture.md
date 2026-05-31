# Architecture

## Stack
| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI + uvicorn |
| Excel | openpyxl |
| Frontend | React 19 + Vite + Tailwind v4, TypeScript |
| Tests | pytest |

Pin all backend dependency versions.

## Running
`./run.sh` — uvicorn (`:8000`) + Vite dev (`:5173`) together; Ctrl-C stops both. Vite proxies `/calculate` and `/health` → `:8000`. Single-server prod: `npm run build` → backend serves `frontend/dist` via a catch-all SPA route (register it **after** the API routes so it doesn't shadow them).

## Request flow
```
upload → POST /calculate
  validate dates → check .csv → parse_ibkr_csv
  → convert trades to GBP (skip + warn if no rate)
  → run_engine (same-day → B&B → S104 → short)
  → validate_history (pool vs open positions)
  → generate_excel → stream xlsx + X-TaxBuddy-* headers
frontend: gaps? → warning screen (continue / re-upload) : results → download
```

## Target structure
```
tax-buddy/
├── run.sh                    # dev launcher: uvicorn :8000 + Vite :5173 together
├── pyproject.toml            # pinned deps
├── backend/
│   ├── main.py               # HTTP routing + /calculate orchestration only
│   ├── models.py             # dataclasses + exceptions
│   ├── parser.py             # parse_ibkr_csv
│   ├── fx.py                 # load CSV + get_rate + convert_to_gbp (no per-request network)
│   ├── engine.py             # HMRC matching + Section 104 pool
│   ├── excel.py              # generate_excel (lean styling)
│   ├── validator.py          # history-gap check (or fold into engine.py)
│   ├── data/fx_rates.csv     # shipped cache; topped up at startup
│   ├── scripts/fx_rates.py   # full-history FX rebuild (Frankfurter/ECB) → backend/data/fx_rates.csv
│   └── tests/
└── frontend/src/
    ├── main.tsx
    ├── App.tsx               # single-screen state machine
    ├── api.ts
    └── components/           # only if App.tsx grows unwieldy
```

## Keep it lean
- **FX rates load from `backend/data/fx_rates.csv` into memory at startup; a best-effort top-up then fetches any missing business days (up to the latest published ECB rate) into the table, persisting to the CSV when writable.** On network error, warn and run with the cached table. The request path stays pure — `get_rate`/`convert_to_gbp` read the in-memory table only, never the network. `backend/scripts/fx_rates.py` shares the same fetch for a full-history rebuild.
- **`excel.py`:** build the required tabs, columns, and totals; keep styling minimal — one small shared helper, no decoration.
- **Frontend:** one screen in `App.tsx` with the `upload → processing → warning? → results / error` state machine. Extract components only when reuse appears.

## Build order
1. `models.py` — dataclasses + exceptions (everything imports these).
2. `fx.py` — load the rate CSV, look up rates, and expose a best-effort top-up (fetch missing recent business days; warn + continue on failure). A populated CSV already exists at `data/fx_rates.csv`; copy it to `backend/data/`, or rebuild it with `backend/scripts/fx_rates.py`.
3. `parser.py` (parallel with 2).
4. `engine.py` — HMRC matching + Section 104 pool; highest risk; test incrementally: pool → same-day → B&B → shorts.
5. `validator.py` — history-gap check.
6. `excel.py` — workbook generation (lean styling).
7. `main.py` — wire the `/calculate` pipeline + `/health`; invoke the FX top-up at startup. Pass the period as a structured value (`is_tax_year` + dates), not by parsing `period_label` for `/`.
8. frontend — Vite scaffold, `api.ts`, single-screen `App.tsx`, proxy.
