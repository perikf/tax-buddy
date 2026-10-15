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
upload yearly .csv files (POST /calculate)
  → validate dates 
  → check .csv 
  → parse each file into statements, merge
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
├── run.sh                    # dev launcher: uvicorn + Vite together
├── pyproject.toml            # the only dependency list (requirements.txt points at it for Vercel)
├── vercel.json               # frontend build + asset cache headers; Vercel's FastAPI preset serves api/
├── api/index.py              # Vercel entry: imports backend.main.app
├── .github/workflows/        # fx-refresh: weekday ECB top-up committed to the repo
├── backend/
│   ├── main.py               # HTTP routing + /calculate orchestration; SPA serving for self-host only
│   ├── models.py             # dataclasses, rule/event vocabulary, exceptions
│   ├── parser.py             # IBKR CSV → statements → merged ParseResult
│   ├── fx.py                 # FxTable: shipped cache, freshness policy, get_rate
│   ├── engine.py             # HMRC matching + Section 104 pools + history-gap validation + totals
│   ├── excel.py              # generate_excel (lean styling)
│   ├── data/fx_rates.csv     # shipped ECB cache
│   ├── scripts/fx_rates.py   # FX top-up (Frankfurter/ECB) → backend/data/fx_rates.csv
│   └── tests/                # fixtures.py shared by the test modules
└── frontend/
    ├── index.html
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx           # single-screen state machine
        ├── ui.tsx            # Card, Stat, useCountUp, class-name constants
        ├── period.ts         # tax-year ranges, GBP formatting
        ├── api.ts
        └── index.css         # theme + motion keyframes
```

Dependencies are one-way: `models ← {fx, parser, engine, excel} ← main`.

## Notes
- **FX freshness:** the `FX refresh` workflow (weekdays, after the ECB publication) runs `backend/scripts/fx_rates.py` to top up `backend/data/fx_rates.csv` and commits it, so every deploy ships complete rates. `FxTable.ensure_ready()` loads the shipped cache and fetches only when it is staler than the 7-day step-back window — at most once per process, off the event loop. `get_rate` reads the in-memory table only.

## Running
See the [README](../README.md) for dev, test, deploy and self-host commands. The SPA catch-all in `main.py` is registered only when `frontend/dist` exists (self-host); on Vercel the static layer serves the frontend and only `/calculate` and `/health` reach the function.
