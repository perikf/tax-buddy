"""FastAPI app: /calculate orchestration, /health, and (self-host only) SPA serving."""
import json
import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from backend import engine, excel, parser
from backend.fx import FxTable
from backend.models import ApiError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("taxbuddy")

MAX_UPLOAD_BYTES = int(4.5 * 1024 * 1024)   # all files together
MAX_FILES = 25
META_LIST_CAP = 30
fx_table = FxTable()
DIST = (Path(__file__).parent.parent / "frontend" / "dist").resolve()

app = FastAPI(title="Tax Buddy")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-TaxBuddy-Meta", "Content-Disposition"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(status_code=400, content={"error": exc.error, "message": exc.message})


def _parse_dates(start_date: str, end_date: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError:
        raise ApiError("INVALID_DATES", "Dates must be ISO format (YYYY-MM-DD).")
    if start > end:
        raise ApiError("INVALID_DATES", "start_date must not be after end_date.")
    return start, end


async def _read_csvs(uploads: list[UploadFile]) -> list[tuple[bytes, str]]:
    if len(uploads) > MAX_FILES:
        raise ApiError("TOO_MANY_FILES", f"At most {MAX_FILES} files per upload.")
    payloads, total = [], 0
    for upload in uploads:
        name = upload.filename or ""
        if not name.lower().endswith(".csv"):
            raise ApiError("INVALID_FILE_TYPE", f"'{name}' is not a .csv file.")
        raw = await upload.read(MAX_UPLOAD_BYTES + 1)
        total += len(raw)
        if total > MAX_UPLOAD_BYTES:
            raise ApiError("FILE_TOO_LARGE", "Uploaded files exceed 4.5 MB in total.")
        if not raw:
            raise ApiError("INVALID_FILE_TYPE", f"'{name}' is empty.")
        payloads.append((raw, name))
    return payloads


def _capped(items: list) -> dict:
    return {"items": items[:META_LIST_CAP], "count": len(items), "truncated": len(items) > META_LIST_CAP}


def _pipeline(payloads: list[tuple[bytes, str]], start: date, end: date,
              period_label: str | None) -> tuple[bytes, str, dict]:
    fx_table.ensure_ready()
    parsed = parser.merge([s for raw, name in payloads for s in parser.statements(raw, name)])
    result = engine.run(parsed.trades, fx_table, parsed.instruments)
    gaps = engine.validate_history(result, parsed)
    warnings = parsed.warnings + result.warnings
    disposals = engine.filter_period(result.disposals, start, end)
    totals = engine.totals(disposals)

    workbook = excel.generate_excel(disposals, totals, result.pool_events, result.fx_records,
                                    gaps, period_label, start, end, warnings)
    meta = {
        "warnings": _capped(warnings),
        "gaps": _capped([{"symbol": g.symbol, "pool_qty": str(g.pool_qty),
                          "open_qty": None if g.open_qty is None else str(g.open_qty),
                          "gap": None if g.gap is None else str(g.gap),
                          "first_trade_is_sell": g.first_trade_is_sell} for g in gaps]),
        "proceeds_gbp": float(totals.proceeds),
        "costs_gbp": float(totals.costs),
        "net_gain_gbp": float(totals.net),
        "disposals": totals.n_disposals,
    }
    log.info("calculate: %d file(s), %d trades, %d disposal lots, %d warnings, %d gaps",
             len(payloads), len(parsed.trades), len(disposals), len(warnings), len(gaps))
    return workbook, excel.build_filename(period_label, start, end), meta


@app.post("/calculate")
async def calculate(
    files: list[UploadFile] = File(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    period_label: str = Form(None),
):
    start, end = _parse_dates(start_date, end_date)
    payloads = await _read_csvs(files)
    workbook, filename, meta = await run_in_threadpool(_pipeline, payloads, start, end, period_label)
    return Response(
        content=workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-TaxBuddy-Meta": json.dumps(meta),
        },
    )


@app.get("/health")
async def health():
    await run_in_threadpool(fx_table.ensure_ready)
    return {"status": "ok", "fx_rates_loaded": fx_table.loaded,
            "fx_latest": fx_table.latest.isoformat() if fx_table.latest else None}


if DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        target = (DIST / path).resolve() if path else DIST
        if not (target.is_relative_to(DIST) and target.is_file()):
            target = DIST / "index.html"
        return FileResponse(target, headers={"Cache-Control": "no-cache"})
