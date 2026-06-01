# Data Contracts

## Input — IBKR CSV Activity Statement
Tagged-row CSV: every row is `section, rowtype, payload…`. Many sections in one file. Rows with < 2 cols or blank section/rowtype are skipped.

**File checks:** max 20 MB (enforce at the upload boundary, before buffering); reject empty. Decode utf-8, then latin-1. Separator `;` only if line 1 has `;` and no `,`, else `,`.

**Trades section** — required: a `Trades` section with a `Header` row + ≥1 `Data` row. Columns accessed by name; payload starts at col index 2.
Required columns (all): `DataDiscriminator, Asset Category, Currency, Symbol, Date/Time, Quantity, T. Price, C. Price, Proceeds, Comm/Fee, Basis, Realized P/L, Realized P/L %, MTM P/L, Code`.

Only rows with `DataDiscriminator == "Order"` become trades (SubTotal / Total / ClosedLot ignored).
| Field | Description | Rule |
|---|---|---|
| Asset Category | Instrument type | must be supported (1) else skip + warn |
| Currency | Trade currency | must be supported (12) else skip + warn |
| Symbol | Ticker / identifier | non-empty string; blank → skip + warn |
| Date/Time | Execution timestamp | `%Y-%m-%d, %H:%M:%S`, fallback date-only; else skip row + warn |
| Quantity | Units traded | Decimal (strip `,`); > 0 Buy, < 0 Sell; invalid → skip + warn |
| T. Price | Execution price per unit | Decimal (strip `,`); invalid → skip + warn |
| C. Price | Closing / settlement price | Decimal (strip `,`); invalid → skip + warn |
| Proceeds | Net cash from trade | Decimal (strip `,`); invalid → skip + warn |
| Comm/Fee | Commission and fees | Decimal (strip `,`); invalid → skip + warn |
| Basis | Cost basis of the position | Decimal (strip `,`); invalid → skip + warn |
| Realized P/L | Realized profit / loss | Decimal (strip `,`); invalid → skip + warn |
| Realized P/L % | Realized P/L as a percentage | Decimal (strip `,`); invalid → skip + warn |
| MTM P/L | Mark-to-market P/L | Decimal (strip `,`); invalid → skip + warn |
| Code | Semicolon-separated trade flags | blank → `""` (keep row) |

Supported currencies (12): AUD CAD CHF DKK EUR GBP HKD JPY NOK PLN SEK USD
Supported asset categories (1): Stocks

## Output — Excel workbook
Tabs in order (conditional ones only when data exists):
| # | Sheet | When | Contents |
|---|---|---|---|
| 0 | CGT Summary | always | period info; per-product gains/losses/net + TOTAL; SA108 figures |
| 1 | `1 STOCKS` | disposals exist | trade table (20 cols); grouped by `symbol\|isin_conid`; Gain/Loss on the group's last row; summary box |
| 2 | Pool History | always | Date, Asset, Product, Event, Qty Δ, Cost Δ GBP, Pool Qty, Pool Cost, Avg Cost/Unit |
| 3 | FX Detail | always | Trade Date, Asset, Type, Currency, Orig Amount, Rate, Rate Date, GBP Amount, Note |
| 4 | Data Quality Warning | gaps exist | Asset, Product, Pool Qty, IBKR Held Qty, Gap, First-Trade-is-Sell |

Number formats: GBP `£#,##0.00`; date `DD-MMM-YYYY`; rate `#,##0.000000`.
Filename: `TaxBuddy_CGT_2024-25.xlsx` when `period_label` has `/` and len ≤ 7; else `TaxBuddy_CGT_<start>_to_<end>.xlsx`.

## API
**POST /calculate** (multipart): `file` (.csv only), `start_date`, `end_date` (ISO, `start < end`), `period_label?`.
→ `200` xlsx stream with headers: `Content-Disposition` (filename), `X-TaxBuddy-Warnings` (count), `X-TaxBuddy-HistoryGaps` (JSON array of `{symbol, pool_qty, open_qty, gap}`). CORS must expose both `X-TaxBuddy-*` headers.

**GET /health** → `{status:"ok", …fx health}` (or `{status:"ok", fx_rates_loaded:false}`).

## Errors (HTTP 400, body `{error, message}`)
`INVALID_DATES` (non-ISO or start ≥ end) · `INVALID_FILE_TYPE` (not .csv / empty) · `FILE_TOO_LARGE` (> 20 MB) · `INVALID_ENCODING` · `NOT_IBKR_FORMAT` · `MISSING_TRADES_SECTION` · `EMPTY_TRADES` · `MISSING_REQUIRED_COLUMNS` (lists the missing ones). Any other → 500.
