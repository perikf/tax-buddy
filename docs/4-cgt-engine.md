# CGT Engine

The numerical core — HMRC rules are law, implement them exactly. The Section 104 pool lives inside the engine (no separate module).

Each disposal's gain is **`proceeds − allowable cost`**. The whole job is deciding *which acquisition's cost* a sale draws on — HMRC fixes the order — then averaging whatever's left into a running pool. Everything is computed in GBP with `Decimal`.

## Pipeline
1. **Convert** every trade to GBP at its trade-date rate.
2. **Group** trades by asset (`symbol|currency`), oldest first.
3. **Match** each sale to acquisitions in the fixed order below; emit a gain/loss per matched lot.
4. **Filter** the output to the period — a disposal appears iff `start <= disposal_date <= end` (inclusive).

The pool is built from **all** trades (a lifetime running average); only the *output* is period-filtered. So bed & breakfast may legitimately match an acquisition in a later tax year.

## Asset identity
Key = `symbol|currency` (e.g. `AAPL|USD`) — one Section 104 pool and one short pool per key.

## Matching a disposal
For each sell, `remaining = abs(qty)`. Walk this fixed order, each step only while `remaining > 0`:

1. **Same-day** — acquisitions on the same date.
2. **Bed & breakfast (30-day)** — acquisitions in `[date+1 .. date+30]` (inclusive), earliest first.
3. **Section 104 pool** — at average cost; `match = min(remaining, pool.qty)`.
4. **Excess** — whatever remains opens a short position.

Same-day and B&B matches are consumed **before they ever enter the pool**.

### How the 30-day look-ahead works
Give every buy a "slot" up front (`remaining_qty`, `eligible_after = buy.date + 30d`). A slot enters the pool only when **flushed** — at the start of a later trade dated `>= eligible_after`, or at end-of-asset. So a buy is poolable for a disposal only if `disposal.date >= buy.date + 30`; same-day and in-window buys are matched straight from their slot and never reach the pool.

### Buys close shorts first
On a buy, cover any outstanding shorts before anything else, and subtract the covered qty from **this buy's slot** so it can't also enter the long pool. The remainder stays in the slot and pools later via flush. Short closes match in reverse: (1) same-day short-opens, then (2) short pool at average proceeds. *(See Decisions for the optional reverse 30-day step.)*

## Formulas (GBP, Decimal)
Per disposal lot of qty `q` from sell `D` (`proportion = q / abs(D.qty)`):
```
proceeds_gbp   = (q*D.price_gbp - |D.commission_gbp|*proportion).quantize(0.01, HALF_UP)
commission_gbp = (|D.commission_gbp|*proportion).quantize(0.01, HALF_UP)   # reported field
gain_loss_gbp  = proceeds_gbp - allowable_cost_gbp
proceeds_orig  = q*D.price_orig                                            # not rounded
```
Acquisition lot cost (buy `A`, qty `q`, `proportion = q/abs(A.qty)`):
```
total_cost = abs(A.qty)*A.price_gbp + |A.commission_gbp|     # commission ADDED to cost
cost_gbp   = (total_cost*proportion).quantize(0.01, HALF_UP)
```
Allowable cost per rule:
- Same-day / B&B disposal → `acq.cost_for_qty(match)` (per-lot, incl. commission).
- Section 104 disposal → `(pool.avg_cost * q).quantize(0.01, HALF_UP)`.

**Key rule: commission is added to acquisition cost and subtracted from disposal proceeds.**

## Section 104 pool ops
```
avg_cost = total_cost_gbp / quantity          # UNROUNDED, full precision; 0 if qty==0
add:    quantity += q;  total_cost_gbp += cost_gbp
remove: cost_removed = (avg_cost * q).quantize(0.01, HALF_UP)
        quantity -= q;  total_cost_gbp -= cost_removed
        if quantity == 0: total_cost_gbp = 0    # dust guard
```
The short pool is symmetric on `total_proceeds_gbp` / `avg_proceeds` (add on short-open, remove on short-close).

## Decimal invariants
- `Decimal` everywhere; never float.
- Quantize `0.01, ROUND_HALF_UP` at every GBP boundary (per-lot cost, proceeds, commission, pool removals).
- Averages held **unrounded**; round only when multiplied out per lot.
- Dust guard: when a pool hits qty 0, force its total cost/proceeds to 0.
- Fractional quantities flow through unchanged.

## Outputs
**DisposalResult** (per matched lot): `disposal_date, symbol, asset_category, quantity_disposed, matching_rule ∈ {Same-Day, Bed & Breakfast, Section 104, Short Close}, acquisition_date (None for S104 / short-pool), proceeds_gbp, allowable_cost_gbp, commission_gbp, gain_loss_gbp, orig_currency, proceeds_orig, fx_rate, fx_rate_date, description, isin_conid, domicile`.

**PoolEvent** (per pool mutation): `date, symbol, asset_category, event_type ∈ {Acquisition, Disposal, Short Open, Short Close}, quantity_delta, cost_delta_gbp, pool_quantity_after, pool_cost_after_gbp, average_cost_after_gbp`.

## FX conversion
| | |
|---|---|
| Base | GBP |
| Rate | trade-date ECB spot (source: frankfurter.app) |
| Semantics | `rate = GBP/CCY` (1 GBP → `rate` units of CCY) |
| Convert | `amount_gbp = amount_foreign / rate` (**divide**) |
| GBP | passthrough: rate = 1, no FX record |
| Weekend/holiday | step **back** up to 7 calendar days; first hit wins; record the actual rate date |
| No rate in window | skip that trade's GBP conversion + warn (trade still kept) |
| Currencies (11) | AUD CAD CHF DKK EUR HKD JPY NOK PLN SEK USD |
| Cache | `backend/data/fx_rates.csv` (shipped, topped up at startup), cols `date,AUD,…,USD`, from 2015-04-06 |

Load the CSV into memory at startup and look up; a best-effort startup top-up fills missing recent business days (network only at startup, never per request) — see [2-architecture.md](2-architecture.md).

## History-gap validation
Run after pools are built, before download. For each IBKR Open Position, compare to its pool (key `symbol|currency`):
- **Gap when `pool_qty < open_qty`** → missing buys → cost understated → gains overstated (HIGH).
- Also flag **first trade for a symbol is a sell** → an acquisition is missing (HIGH).
- `gap = open_qty - pool_qty`.
- No Open Positions section → skip the check + warn.

Surface gaps to the UI before download; user can re-upload or continue. **Never block.**

## Decisions to make (resolve before building)
- **Short-side 30-day B&B:** HMRC symmetry suggests applying the 30-day rule to short closes too. Decide whether to implement it, or match short closes with same-day + short-pool only.
- **Options exercise/assignment:** not yet handled — options are treated as generic open/close. Implement only if you have sample CSVs to test against.
- **No `B&B Removal` pool event:** B&B-matched acquisitions never enter the pool, so there is nothing to emit — do not add such an event.
