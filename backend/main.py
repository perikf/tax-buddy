"""FastAPI app: /calculate orchestration, /health, FX top-up at startup, SPA serving."""
import json
import logging
from contextlib import asynccontextmanager
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

MAX_FILE_BYTES = int(4.5 * 1024 * 1024)
META_LIST_CAP = 30
fx_table = FxTable()
DIST = (Path(__file__).parent.parent / "frontend" / "dist").resolve()


def ensure_fx() -> None:
    if fx_table.loaded:
        return
    try:
        fx_table.load()
    except OSError as e:
        log.error("FX cache missing: %s", e)
        return
    try:
        fx_table.top_up()
    except Exception as e:
        log.warning("FX top-up failed (continuing with cache): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_fx()
    yield


app = FastAPI(title="Tax Buddy", lifespan=lifespan)
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


async def _read_csv(upload: UploadFile) -> bytes:
    if not (upload.filename or "").lower().endswith(".csv"):
        raise ApiError("INVALID_FILE_TYPE", f"'{upload.filename}' is not a .csv file.")
    raw = await upload.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ApiError("FILE_TOO_LARGE", f"'{upload.filename}' exceeds 4.5 MB.")
    if not raw:
        raise ApiError("INVALID_FILE_TYPE", f"'{upload.filename}' is empty.")
    return raw


def _pipeline(raw: bytes, filename: str, start: date, end: date,
              period_label: str | None) -> tuple[bytes, str, dict]:
    ensure_fx()
    merged = parser.parse(raw, filename)
    result = engine.run(merged.trades, fx_table, merged.instruments)
    gaps = engine.validate_history(result.net_quantities, result.first_trade_is_sell,
                                   merged.open_positions, merged.has_open_positions_section,
                                   result.warnings)
    warnings = merged.warnings + result.warnings
    disposals = engine.filter_period(result.disposals, start, end)

    label = period_label or f"{start.isoformat()} to {end.isoformat()}"
    workbook = excel.generate_excel(disposals, result.pool_events, result.fx_records,
                                    gaps, label, start, end, warnings)
    meta = {
        "warning_count": len(warnings),
        "warnings": warnings[:META_LIST_CAP],
        "warnings_truncated": len(warnings) > META_LIST_CAP,
        "gap_count": len(gaps),
        "gaps": [{"symbol": g.symbol, "pool_qty": str(g.pool_qty),
                  "open_qty": None if g.open_qty is None else str(g.open_qty),
                  "gap": None if g.gap is None else str(g.gap),
                  "first_trade_is_sell": g.first_trade_is_sell} for g in gaps[:META_LIST_CAP]],
        "gaps_truncated": len(gaps) > META_LIST_CAP,
        "history_verified": merged.has_open_positions_section,
    }
    log.info("calculate: %d trades, %d disposal lots, %d warnings, %d gaps",
             len(merged.trades), len(disposals), len(warnings), len(gaps))
    return workbook, excel.build_filename(period_label, start, end), meta


@app.post("/calculate")
async def calculate(
    file: UploadFile = File(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    period_label: str = Form(None),
):
    start, end = _parse_dates(start_date, end_date)
    raw = await _read_csv(file)
    workbook, filename, meta = await run_in_threadpool(
        _pipeline, raw, file.filename or "", start, end, period_label)
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
    ensure_fx()
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
        return FileResponse(target)
