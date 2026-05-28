# CGT Engine

The numerical core. HMRC rules are law — implement them exactly. Section 104 pool operations live inside the engine (no separate pool module).

## Asset identity
Key = `symbol|currency` (e.g. `AAPL|USD`). One Section 104 pool + one short pool per key. Group all trades by key, sort ascending by date, process per asset.

## Period handling
Pool is built from **all** trades (lifetime running average). Only the **output** is filtered: a disposal appears iff `start <= disposal_date <= end` (inclusive). B&B may legitimately match an acquisition in a later tax year.

## Matching order (disposals)
For each sell, `remaining = abs(qty)`. Apply in this fixed order; each step only if `remaining > 0`:

1. **Same-day** — acquisitions on the same date.
2. **30-day bed & breakfast** — acquisitions in `[date+1 .. date+30]` (inclusive), earliest first.
3. **Section 104 pool** — at pool average cost; `match = min(remaining, pool.qty)`.
4. **Excess → open short** — whatever remains opens a short position.

Same-day and B&B-matched acquisitions are consumed **before they ever enter the pool**.

## How B&B look-ahead works
Pre-create an acquisition "slot" for every buy up front (`remaining_qty`, `eligible_after = buy.date + 30d`). A slot enters the Section 104 pool only when **flushed** — at the start of a later trade whose date `>= eligible_after`, or at end-of-asset. Therefore:
- A buy is poolable for a disposal only if `disposal.date >= buy.date + 30`.
- Same-day / in-window buys are matched while still in their slot and never reach the pool.

## Acquisitions (buys) — close shorts first
On a buy: if shorts are outstanding, cover them first, and subtract the covered qty from **this buy's slot** so it can't also enter the long pool. The remainder stays in its slot → enters the pool later via flush.

Short-close matching (reverse order): (1) same-day short-opens, then (2) short pool at average proceeds. *(See Decisions for the optional 30-day reverse-B&B step.)*

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
Short pool is symmetric on `total_proceeds_gbp` / `avg_proceeds` (add on short-open, remove on short-close).

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
| Cache | static `backend/data/fx_rates.csv`, cols `date,AUD,…,USD`, from 2015-04-06 |

Ship the rate CSV static; load once and look up. No runtime network fetch — see [architecture.md](architecture.md).

## History-gap validation
Run after pools are built, before download. For each IBKR Open Position, compare to its pool (key `symbol|currency`):
- **Gap when `pool_qty < open_qty`** → missing buys → cost understated → gains overstated (HIGH).
- Also flag **first trade for a symbol is a sell** → an acquisition is missing (HIGH).
- `gap = open_qty - pool_qty`.
- No Open Positions section → skip the check + warn.

Surface gaps to the UI before download; user can re-upload or continue. **Never block.**

## Decisions to make (resolve before building)
- **Short-side 30-day B&B:** HMRC symmetry suggests applying the 30-day rule to short closes too. Decide whether to implement it, or match short closes with same-day + short-pool only.
- **Asset key:** use `symbol|currency` (handles the same ticker held in two currencies); make the validator use the same key.
- **Options exercise/assignment:** not yet handled — options are treated as generic open/close. Implement only if you have sample CSVs to test against.
- **No `B&B Removal` pool event:** B&B-matched acquisitions never enter the pool, so there is nothing to emit — do not add such an event.
