# Overview

## What
A stateless web app that turns an IBKR CSV Activity Statement into a downloadable UK Capital Gains Tax report (Excel), applying HMRC matching rules with GBP FX conversion. No accounts, no storage.

## Who
UK retail investors / active traders self-filing Self Assessment, holding stocks/ETFs/options (mostly US-listed) via Interactive Brokers.

## Why
IBKR reports gains FIFO (US rules) — non-compliant with UK law. By hand it's 4–8 hrs; an accountant is £300–800. Target: correct, auditable CGT in **under 10s**.

## In scope
- Parse IBKR multi-section CSV, no user pre-processing.
- HMRC matching chain: same-day → 30-day bed & breakfast → Section 104 pool.
- Pool built from **full history across all tax years**; output filtered to the chosen period.
- Reporting period: UK tax year (2015/16+) or custom range — both resolve to one `(start, end)` pair.
- Incomplete-history detection (pool qty vs IBKR open positions); warn, never block.
- Asset categories supported: Stocks
- Multi-currency → GBP at trade-date ECB rate.
- Excel: disposals per product, pool history, CGT summary (SA108), FX detail.

## Out of scope (first version)
Dividends/income, Equity and Index Options, Futures, Options on Futures, Bonds, US Treasury Bills, crypto, CFDs/spread betting, corporate actions (skip + warn), HMRC submission, multi-broker, accounts/auth/persistence, mobile UI, PDF.

## Success criteria
| Metric | Target |
|---|---|
| Accuracy vs manual (test suite) | 100% |
| p95 processing (10k rows) | < 10s |
| Uploaders who download a result | > 90% |
| History-warning correctness (fixtures) | 100% |
| Unhandled exceptions | < 1% |
