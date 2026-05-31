# Data Contracts

## Input — IBKR CSV Activity Statement
Tagged-row CSV: every row is `section, rowtype, payload…`. Many sections in one file. Rows with < 2 cols or blank section/rowtype are skipped.

**File checks:** max 20 MB; reject empty. Decode utf-8, then latin-1. Separator `;` only if line 1 has `;` and no `,`, else `,`.

**Trades section** — required: a `Trades` section with a `Header` row + ≥1 `Data` row. Columns accessed by name; payload starts at col index 2.
Required columns (all): `DataDiscriminator, Asset Category, Currency, Symbol, Description, Date/Time, Quantity, T. Price, Comm/Fee, Proceeds, Basis, Realized P/L, Code, Open/Close` — plus at least one of `{ISIN, ConId}`.

Only rows with `DataDiscriminator == "Order"` become trades (SubTotal / Total / ClosedLot ignored).
| Field | Rule |
|---|---|
| Date/Time | `%Y-%m-%d, %H:%M:%S`, fallback date-only; else skip row + warn |
| Quantity | Decimal (strip `,`); > 0 Buy, < 0 Sell; invalid → skip |
| T. Price | Decimal; invalid → skip |
| Currency | must be supported (12) else skip + warn |
| Asset Category | must be supported (6) else skip + warn |
| Comm/Fee, Proceeds, Realized P/L | Decimal; blank/invalid → 0 (keep row) |

Supported currencies (12): AUD CAD CHF DKK EUR GBP HKD JPY NOK PLN SEK USD.
Supported asset categories (6): Stocks, Equity and Index Options, Futures, Options on Futures, Bonds, US Treasury Bills.

**Open Positions** (optional): section `Open Positions`, rows `DataDiscriminator == "Summary"`, cols `{Symbol, Asset Category, Currency, Quantity}`. Missing → warn + skip the history check. Feeds validation.

## Output — Excel workbook
Tabs in order (conditional ones only when data exists):
| # | Sheet | When | Contents |
|---|---|---|---|
| 0 | Data Quality Warning | gaps exist | Asset, Product, Pool Qty, IBKR Held Qty, Gap, First-Trade-is-Sell |
| 1..6 | `<n> <PRODUCT>` (e.g. `1 STOCKS`) | per product with in-period disposals | trade table (20 cols); grouped by `symbol\|isin_conid`; Gain/Loss on the group's last row; summary box on the first product sheet |
| N | Pool History | always | Date, Asset, Product, Event, Qty Δ, Cost Δ GBP, Pool Qty, Pool Cost, Avg Cost/Unit |
| N+1 | CGT Summary | always | period info; per-product gains/losses/net + TOTAL; SA108 figures |
| N+2 | FX Detail | always | Trade Date, Asset, Type, Currency, Orig Amount, Rate, Rate Date, GBP Amount, Note |
| N+3 | Warnings | warnings exist | Severity, Message |

Product order: Stocks 1, Equity and Index Options 2, Futures 3, Options on Futures 4, Bonds 5, US Treasury Bills 6.
Number formats: GBP `£#,##0.00`; date `DD-MMM-YYYY`; rate `#,##0.000000`.
Filename: `TaxBuddy_CGT_2024-25.xlsx` when `period_label` has `/` and len ≤ 7; else `TaxBuddy_CGT_<start>_to_<end>.xlsx`.

## API
**POST /calculate** (multipart): `file` (.csv only), `start_date`, `end_date` (ISO, `start < end`), `period_label?`.
→ `200` xlsx stream with headers: `Content-Disposition` (filename), `X-TaxBuddy-Warnings` (count), `X-TaxBuddy-HistoryGaps` (JSON array of `{symbol, pool_qty, open_qty, gap}`). CORS must expose both `X-TaxBuddy-*` headers.

**GET /health** → `{status:"ok", …fx health}` (or `{status:"ok", fx_rates_loaded:false}`).

## Errors (HTTP 400, body `{error, message}`)
`INVALID_DATES` (non-ISO or start ≥ end) · `INVALID_FILE_TYPE` (not .csv / empty) · `FILE_TOO_LARGE` (> 20 MB) · `INVALID_ENCODING` · `NOT_IBKR_FORMAT` · `MISSING_TRADES_SECTION` · `EMPTY_TRADES` · `MISSING_REQUIRED_COLUMNS` (lists the missing ones). Any other → 500.

## Implementation notes
- Warnings tab: Severity + Message (2 columns).
- History gaps: render in the Data Quality tab; the response header carries only a count.
- Period: pass as a structured value (`is_tax_year` + dates), not by parsing the label string for `/`.
- File size: enforce the 20 MB limit at the upload boundary, before buffering the whole file.
