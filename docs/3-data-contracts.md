# Data Contracts

## Input — IBKR CSV Activity Statement
Tagged-row CSV: every row is `section, rowtype, payload…`. Many sections in one file. Rows with < 2 cols or blank section/rowtype are skipped.

**File checks:** max 20 MB each, at most 10 files (enforce at the upload boundary, before buffering); reject empty. Decode utf-8 then latin-1, stripping BOMs anywhere in the file (concatenated statements carry one per boundary). Separator `;` only if line 1 has `;` and no `,`, else `,`.

**Trades section** — required: a `Trades` section with a `Header` row + ≥1 `Data` row. Columns accessed by name; payload starts at col index 2. A statement carries **several Trades subsections**, each introduced by its own `Header` row — reset the column map on every one. Required columns (all, in at least one subsection): `DataDiscriminator, Asset Category, Currency, Symbol, Date/Time, Quantity, T. Price, C. Price, Proceeds, Comm/Fee, Basis, Realized P/L, Realized P/L %, MTM P/L, Code`. A subsection missing required columns is an error only if it contains supported-category rows; otherwise its rows are skipped + warned (e.g. the Forex subsection, whose header differs).

Only rows with `DataDiscriminator == "Order"` become trades (SubTotal / Total / ClosedLot ignored).
| Field | Description | Rule |
|---|---|---|
| Asset Category | Instrument type | must be supported (1) else skip + warn |
| Currency | Trade currency | must be supported (12) else skip + warn |
| Symbol | Ticker / identifier | non-empty string; blank → skip + warn |
| Date/Time | Execution timestamp | `%Y-%m-%d, %H:%M:%S`, fallback date-only; else skip row + warn |
| Quantity | Units traded | Decimal (strip `,`); > 0 Buy, < 0 Sell; zero or invalid → skip + warn |
| T. Price | Execution price per unit | Decimal (strip `,`); invalid → skip + warn |
| C. Price | Closing / settlement price | Decimal (strip `,`); invalid → skip + warn |
| Proceeds | Net cash from trade | Decimal (strip `,`); invalid → skip + warn |
| Comm/Fee | Commission and fees, signed (negative = cost, positive = rebate) | Decimal (strip `,`); invalid → skip + warn |
| Basis | Cost basis of the position | Decimal (strip `,`); invalid → skip + warn |
| Realized P/L | Realized profit / loss | Decimal (strip `,`); invalid → skip + warn |
| Realized P/L % | Realized P/L as a percentage | Decimal (strip `,`); invalid → skip + warn |
| MTM P/L | Mark-to-market P/L | Decimal (strip `,`); invalid → skip + warn |
| Code | Semicolon-separated trade flags | blank → `""` (keep row) |

Supported currencies (12): AUD CAD CHF DKK EUR GBP HKD JPY NOK PLN SEK USD
Supported asset categories (1): Stocks
Skip + warn messages are aggregated per reason (one warning with a count, not one per row); row-specific detail only for data-quality skips (bad date, invalid number, blank symbol).

**Open Positions section** (optional) — `Header` + `Data` rows; use rows with `DataDiscriminator == "Summary"` and a supported Asset Category. Columns: `Asset Category, Currency, Symbol, Quantity`. Feeds the history-gap check; absent → skip the check + warn.

**Financial Instrument Information section** (optional) — `Header` + `Data` rows for supported categories. Columns: `Asset Category, Symbol` (may hold several comma-separated symbols), `Description, Conid, Security ID`. Supplies description, ISIN (falling back to Conid) and domicile (from the ISIN country prefix).

**Multiple statements** — one IBKR statement covers at most a year, so the pool needs the full history: several yearly files, or one file holding several statements back-to-back. Split a file into statements on its `Statement,Header` rows, parse each separately (capturing the Statement section's `Period` and `WhenGenerated`), then merge all statements from all files:
- A reissued statement for the same `Period` supersedes the older one wholesale (newest `WhenGenerated` wins) + warn — amended trades never double-count.
- Trades identical across the remaining statements (same symbol, currency, timestamp, quantity, price, proceeds, commission, code) collapse to the **maximum per-statement count** — partial overlaps never double-count, while genuinely identical same-second fills within one statement survive. Warn when duplicates were collapsed. Merged trades are independent copies (the engine may track per-lot state by object).
- Open Positions come from the statement with the latest trade date that has the section (each statement snapshots its own holdings — only the latest is current).

## Output — Excel workbook
Tabs in order (conditional ones only when data exists):
| # | Sheet | When | Contents |
|---|---|---|---|
| 0 | CGT Summary | always | period info; per-product gains/losses/net + TOTAL; SA108 figures |
| 1 | `1 STOCKS` | disposals exist | summary box; disposal-lot table (20 cols), grouped by `symbol\|isin_conid` with a bold group-total Gain/Loss on each group's last row |
| 2 | Pool History | always | Date, Asset, Product, Event, Qty Δ, Cost Δ GBP, Pool Qty, Pool Cost, Avg Cost/Unit |
| 3 | FX Detail | always | Trade Date, Asset, Type, Currency, Orig Amount, Rate, Rate Date, GBP Amount, Note |
| 4 | Data Quality Warning | gaps exist | Asset, Product, Pool Qty, IBKR Held Qty, Gap, First-Trade-is-Sell |

`1 STOCKS` columns (20): Broker, Product, Domicile, Ticker, Description, ISIN/Conid, Trade Date, Type, Open/Close, Currency, Quantity, Proceeds (CCY), FX Rate, FX Rate Date, Proceeds GBP, Allowable Cost GBP, Commission GBP, Gain/Loss GBP, Matching Rule, Acquisition Date.
Pool History and FX Detail cover the **full uploaded history**; only disposals are period-filtered.
Number formats: GBP `£#,##0.00`; date `DD-MMM-YYYY`; rate `#,##0.000000`.
Filename: `TaxBuddy_CGT_2024-25.xlsx` when `period_label` matches `\d{4}/\d{2}` exactly (anything else is unsafe in a `Content-Disposition` header); else `TaxBuddy_CGT_<start>_to_<end>.xlsx`.

## API
**POST /calculate** (multipart): `files` (one or more .csv), `start_date`, `end_date` (ISO, `start <= end` — the disposal filter is inclusive, so a one-day range is valid), `period_label?`.
→ `200` xlsx stream with headers: `Content-Disposition` (filename) and `X-TaxBuddy-Meta` — one bounded JSON object: `{warning_count, warnings (first 30), warnings_truncated, gap_count, gaps (first 30, each {symbol, pool_qty, open_qty, gap, first_trade_is_sell}; open_qty/gap null when there was no Open Positions section to compare against), gaps_truncated, history_verified}`. Full lists always live in the workbook. CORS must expose exactly `X-TaxBuddy-Meta` and `Content-Disposition`. The heavy pipeline runs off the event loop (thread pool).

**GET /health** → `{status:"ok", …fx health}` (or `{status:"ok", fx_rates_loaded:false}`).

## Errors (HTTP 400, body `{error, message}`)
`INVALID_DATES` (non-ISO or start > end) · `INVALID_FILE_TYPE` (not .csv / empty) · `FILE_TOO_LARGE` (> 20 MB per file) · `TOO_MANY_FILES` (> 10 files) · `INVALID_ENCODING` · `NOT_IBKR_FORMAT` · `MISSING_TRADES_SECTION` · `EMPTY_TRADES` · `MISSING_REQUIRED_COLUMNS` (lists the missing ones). Any other → 500.
