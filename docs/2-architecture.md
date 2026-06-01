# Architecture

## Stack
| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI + uvicorn |
| Frontend | React 19 + Vite + Tailwind v4, TypeScript |
| Excel | openpyxl |
| Tests | pytest |

## Workflow
```
upload .csv (POST /calculate)
  → validate dates 
  → check .csv 
  → parse .csv
  → convert trades to GBP (skip + warn if no rate)
  → run engine (same-day → B&B → S104 → short)
  → validate history (pool vs open positions)
  → generate excel 
  → stream xlsx
  → frontend: gaps → warning screen (continue / re-upload) : results → download
```

## Target structure
```
tax-buddy/
├── run.sh                    # dev launcher: uvicorn :8000 + Vite :5173 together
├── pyproject.toml            # pinned deps
├── backend/
│   ├── main.py               # HTTP routing + /calculate orchestration; FX top-up at startup;
│   ├── models.py             # dataclasses + exceptions
│   ├── parser.py             # parse ibkr csv
│   ├── fx.py                 # load CSV + get_rate + convert_to_gbp (no per-request network)
│   ├── engine.py             # HMRC matching + Section 104 pool; test order: pool → same-day → B&B → shorts
│   ├── excel.py              # generate_excel (lean styling)
│   ├── validator.py          # history-gap check (or fold into engine.py)
│   ├── data/fx_rates.csv     # shipped cache; topped up at startup
│   ├── scripts/fx_rates.py   # full-history FX rebuild (Frankfurter/ECB) → backend/data/fx_rates.csv
│   └── tests/
└── frontend/
    ├── main.tsx
    ├── App.tsx               # single-screen state machine
    ├── api.ts
    └── components/           # only if App.tsx grows unwieldy
```

## Notes
- **FX top-up:** fetches missing business days up to the latest ECB rate; persists to `backend/data/fx_rates.csv` when writable; on network error, warns and continues. `get_rate`/`convert_to_gbp` read the in-memory table only — no per-request network.

## Running
`./run.sh` — uvicorn (`:8000`) + Vite dev (`:5173`) together; Ctrl-C stops both. Vite proxies `/calculate` and `/health` → `:8000`. Single-server prod: `npm run build` → backend serves `frontend/dist` via a catch-all SPA route (register it **after** the API routes so it doesn't shadow them).
