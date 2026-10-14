import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { calculate, saveBlob, type CalcResult } from "./api";

const FIRST_TAX_YEAR = 2015;

function taxYears(): { label: string; start: string; end: string }[] {
  const today = new Date();
  const currentStart =
    today >= new Date(today.getFullYear(), 3, 6) ? today.getFullYear() : today.getFullYear() - 1;
  const years = [];
  for (let y = currentStart; y >= FIRST_TAX_YEAR; y--) {
    years.push({
      label: `${y}/${String(y + 1).slice(2)}`,
      start: `${y}-04-06`,
      end: `${y + 1}-04-05`,
    });
  }
  return years;
}

const gbp = (n: number) =>
  n.toLocaleString("en-GB", { style: "currency", currency: "GBP" });

const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function useCountUp(target: number, run: boolean, duration = 1000): number {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!run) return;
    if (reducedMotion()) { setVal(target); return; }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      setVal(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, duration]);
  return val;
}

const card =
  "spotlight-card relative overflow-hidden rounded-2xl bg-white/[0.03] ring-1 ring-white/10 p-6 backdrop-blur-sm transition " +
  "shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_1px_2px_rgba(0,0,0,0.4),0_16px_48px_rgba(0,0,0,0.5)] " +
  "hover:ring-white/[0.14]";
const badge =
  "mr-2.5 inline-flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-b from-white to-neutral-300 " +
  "text-xs font-bold text-black ring-1 ring-white/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_2px_8px_rgba(0,0,0,0.6)] align-[2px]";
const input =
  "h-10 rounded-lg bg-white/[0.05] ring-1 ring-white/10 px-3 text-neutral-200 outline-none transition focus:ring-[#0070f3]";
const primaryBtn = {
  amber: "rounded-lg bg-gradient-to-b from-amber-300 to-amber-500 px-4 py-2 font-semibold text-amber-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
  emerald: "rounded-lg bg-gradient-to-b from-emerald-300 to-emerald-500 px-4 py-2 font-semibold text-emerald-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
};
const ghostBtn = {
  amber: "rounded-lg px-4 py-2 font-semibold text-amber-200 ring-1 ring-amber-400/30 transition hover:bg-amber-400/10",
  emerald: "rounded-lg px-4 py-2 font-semibold text-emerald-200 ring-1 ring-emerald-400/30 transition hover:bg-emerald-400/10",
};

function Card({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <section
      ref={ref}
      onPointerMove={(e) => {
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${e.clientX - r.left}px`);
        el.style.setProperty("--my", `${e.clientY - r.top}px`);
      }}
      className={`${card} animate-fade-up`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="relative z-[1]">{children}</div>
    </section>
  );
}

function Stat({ label, value, tone = "neutral", run }:
  { label: string; value: number; tone?: "neutral" | "net"; run: boolean }) {
  const v = useCountUp(value, run);
  const color =
    tone === "net" ? (value >= 0 ? "text-emerald-300" : "text-rose-300") : "text-neutral-100";
  return (
    <div className="rounded-xl bg-black/30 ring-1 ring-white/10 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${color}`}>{gbp(v)}</p>
    </div>
  );
}

export default function App() {
  const years = useMemo(taxYears, []);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"tax-year" | "custom">("tax-year");
  const [year, setYear] = useState(years.length > 1 ? years[1].label : years[0].label);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFile = useCallback((incoming: FileList | File[]) => {
    const picked = Array.from(incoming).find((f) => f.name.toLowerCase().endsWith(".csv"));
    if (!picked) return;
    setFile(picked);
    setResult(null);
    setError("");
  }, []);

  const period = useMemo(() => {
    if (mode === "tax-year") {
      const y = years.find((v) => v.label === year)!;
      return { start: y.start, end: y.end, label: y.label };
    }
    return { start: customStart, end: customEnd, label: "" };
  }, [mode, year, customStart, customEnd, years]);

  const ready =
    file !== null && period.start !== "" && period.end !== "" && period.start <= period.end;

  async function submit() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await calculate(file!, period.start, period.end, period.label));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError("");
  }

  const hasGaps = (result?.gapCount ?? 0) > 0;
  const showStats = result !== null && !hasGaps;

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* animated aurora + dot grid */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-48 left-1/2 h-[560px] w-[760px] -translate-x-1/2 rounded-full bg-[#007cf0]/18 blur-[150px] [animation:drift-a_26s_ease-in-out_infinite]" />
        <div className="absolute top-1/3 -right-40 h-[440px] w-[520px] rounded-full bg-[#00dfd8]/12 blur-[150px] [animation:drift-b_32s_ease-in-out_infinite]" />
        <div className="absolute bottom-[-10%] left-[-10%] h-[460px] w-[560px] rounded-full bg-[#7c5cff]/14 blur-[150px] [animation:drift-c_30s_ease-in-out_infinite]" />
        <div className="absolute inset-0 [background-image:radial-gradient(rgba(255,255,255,0.09)_1px,transparent_1px)] [background-size:26px_26px] [mask-image:radial-gradient(ellipse_65%_50%_at_50%_0%,black,transparent)] [animation:grid-pan_6s_linear_infinite]" />
      </div>

      <div className="relative mx-auto max-w-2xl px-6 py-14">
        <header className="text-center mb-10 animate-fade-up">
          <h1 className="text-[2.75rem] font-extrabold tracking-tighter text-white">
            🧾 Tax<span className="wordmark">Buddy</span>
          </h1>
          <p className="mt-3 text-neutral-400">
            IBKR statements in. HMRC-ready capital gains out.{" "}
            <span className="font-medium text-neutral-200">Under 10 seconds.</span>
          </p>
        </header>

        <main className="space-y-6">
          {/* Step 1 — upload */}
          <Card delay={80}>
            <h2 className="font-semibold tracking-tight text-white mb-1">
              <span className={badge}>1</span>Upload your IBKR activity statement
            </h2>
            <p className="text-sm text-neutral-400 mb-4">
              One CSV <strong className="text-neutral-300">covering every year since your first purchase</strong> —
              HMRC matching needs your full history. Export it directly from IBKR as a single file:
              Performance &amp; Reports → Statements → Activity, date range from your first trade to today,
              format CSV. No need to merge files by hand.
            </p>
            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); addFile(e.dataTransfer.files); }}
              className={`group cursor-pointer rounded-xl border border-dashed p-8 text-center transition
                ${dragging
                  ? "border-[#0070f3] bg-[#0070f3]/10 shadow-[0_0_50px_rgba(0,112,243,0.2)_inset]"
                  : "border-white/15 hover:border-white/30 hover:bg-white/[0.03]"}`}
            >
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-b from-white/[0.1] to-white/[0.02]
                              text-2xl ring-1 ring-white/15 shadow-[inset_0_1px_0_rgba(255,255,255,0.15),0_4px_16px_rgba(0,0,0,0.5)]
                              [animation:float-y_4s_ease-in-out_infinite] group-hover:ring-[#00dfd8]/40">
                📂
              </div>
              <p className="font-medium text-neutral-200">Drop your CSV here or click to browse</p>
              <p className="text-sm text-neutral-500 mt-1">
                Activity Statement → CSV · one file with your full history · 4.5 MB max
              </p>
              <input
                ref={inputRef} type="file" accept=".csv" hidden
                onChange={(e) => { if (e.target.files) addFile(e.target.files); e.target.value = ""; }}
              />
            </div>
            {file && (
              <ul className="mt-4 flex flex-wrap gap-2">
                <li className="flex items-center gap-2 rounded-full bg-white/[0.06] px-3 py-1 text-sm text-neutral-300 ring-1 ring-white/[0.12] animate-fade-up">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#00dfd8]" />
                  <span>{file.name}</span>
                  <span className="text-neutral-500">{(file.size / 1024).toFixed(0)} KB</span>
                  <button
                    onClick={() => setFile(null)}
                    className="font-bold text-neutral-500 transition hover:text-white"
                    aria-label={`Remove ${file.name}`}>
                    ×
                  </button>
                </li>
              </ul>
            )}
          </Card>

          {/* Step 2 — period */}
          <Card delay={160}>
            <h2 className="font-semibold tracking-tight text-white mb-4">
              <span className={badge}>2</span>Pick the reporting period
            </h2>
            <div className="mb-4 flex gap-2">
              {(["tax-year", "custom"] as const).map((m) => (
                <button key={m} onClick={() => setMode(m)}
                  className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition
                    ${mode === m
                      ? "bg-white/10 text-white ring-1 ring-white/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]"
                      : "text-neutral-400 hover:bg-white/[0.05] hover:text-neutral-200"}`}>
                  {m === "tax-year" ? "UK tax year" : "Custom range"}
                </button>
              ))}
            </div>
            <div className="min-h-10">
              {mode === "tax-year" ? (
                <select value={year} onChange={(e) => setYear(e.target.value)} className={`max-w-full ${input}`}>
                  {years.map((y) => (
                    <option key={y.label} value={y.label} className="bg-[#111114]">
                      {y.label} &nbsp;·&nbsp; {y.start} → {y.end}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} className={input} />
                  <span className="text-neutral-500">to</span>
                  <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} className={input} />
                </div>
              )}
            </div>
          </Card>

          {/* Step 3 — go (with traveling light beam when ready) */}
          <div className="relative animate-fade-up overflow-hidden rounded-2xl p-[1.5px]" style={{ animationDelay: "240ms" }}>
            {ready && !busy && (
              <span aria-hidden className="absolute inset-[-150%] [background:conic-gradient(from_0deg,transparent_0_295deg,#00dfd8_330deg,#007cf0_355deg,transparent_360deg)] [animation:spin-slow_4s_linear_infinite]" />
            )}
            <button onClick={submit} disabled={!ready || busy}
              className="sheen-host relative w-full overflow-hidden rounded-[15px] bg-gradient-to-b from-white to-neutral-200 py-4 text-lg font-bold tracking-tight text-black
                         ring-1 ring-white/20 transition
                         shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_0_40px_rgba(255,255,255,0.1),0_12px_32px_rgba(0,0,0,0.5)]
                         hover:from-neutral-100 hover:to-neutral-300
                         active:scale-[0.99]
                         disabled:from-white/[0.06] disabled:to-white/[0.04] disabled:text-neutral-500 disabled:ring-white/10 disabled:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] disabled:cursor-not-allowed">
              <span aria-hidden className="sheen pointer-events-none absolute inset-y-0 -left-1/2 w-1/3 -skew-x-12 bg-white/50 blur-md" style={{ transform: "translateX(-260%) skewX(-16deg)" }} />
              {busy ? (
                <span className="relative inline-flex items-center gap-3">
                  <span className="h-5 w-5 animate-spin rounded-full border-2 border-black/70 border-t-transparent" />
                  Processing…
                </span>
              ) : (
                <span className="relative">Calculate my gains →</span>
              )}
            </button>
          </div>

          {error && (
            <section className="animate-fade-up rounded-2xl bg-rose-500/[0.07] p-5 text-rose-300 ring-1 ring-rose-500/20">
              <p className="font-semibold text-rose-200">Something went wrong</p>
              <p className="mt-1 text-sm">{error}</p>
            </section>
          )}

          {result && hasGaps && (
            <section className="animate-fade-up rounded-2xl bg-amber-500/[0.07] p-6 ring-1 ring-amber-500/20">
              <h3 className="font-bold text-amber-200">
                {result.historyVerified ? "⚠️ Your history looks incomplete" : "⚠️ History couldn't be verified"}
              </h3>
              <p className="mt-1 mb-4 text-sm text-amber-200/70">
                {result.historyVerified
                  ? "The rebuilt holdings don't match what IBKR says you hold — some statements are probably missing. Figures could be wrong."
                  : "These statements have no Open Positions section to check against, and some assets start with a sell — earlier buys are missing."}
              </p>
              <table className="mb-4 w-full text-sm">
                <thead>
                  <tr className="border-b border-amber-400/20 text-left text-amber-300/70">
                    <th className="py-1 pr-2 font-medium">Symbol</th>
                    <th className="font-medium">Rebuilt</th>
                    <th className="font-medium">IBKR holds</th>
                    <th className="font-medium">Gap</th>
                    <th className="font-medium">First trade is a sell</th>
                  </tr>
                </thead>
                <tbody>
                  {result.gaps.map((g) => (
                    <tr key={g.symbol} className="border-b border-amber-400/10 text-amber-100">
                      <td className="py-1 pr-2 font-medium">{g.symbol}</td>
                      <td>{g.pool_qty}</td>
                      <td>{g.open_qty ?? "—"}</td>
                      <td>{g.gap ?? "—"}</td>
                      <td>{g.first_trade_is_sell ? "yes" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.gapsTruncated && (
                <p className="mb-4 text-sm text-amber-300/70">
                  …and {result.gapCount - result.gaps.length} more — the full list is in the report's Data Quality tab.
                </p>
              )}
              <div className="flex gap-3">
                <button onClick={() => saveBlob(result.blob, result.filename)} className={primaryBtn.amber}>
                  Download anyway
                </button>
                <button onClick={reset} className={ghostBtn.amber}>
                  Upload a fuller history
                </button>
              </div>
            </section>
          )}

          {showStats && result && (
            <section className="animate-fade-up rounded-2xl bg-emerald-500/[0.07] p-6 ring-1 ring-emerald-500/20">
              <h3 className="font-bold text-emerald-200">✅ Done — your report is ready</h3>

              <div className="mt-5 text-center">
                <p className="text-xs uppercase tracking-wide text-neutral-400">
                  Net {result.netGain >= 0 ? "gain" : "loss"} · {period.label || "selected period"}
                </p>
                <Hero value={result.netGain} />
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3">
                <Stat label="Proceeds" value={result.proceeds} run={showStats} />
                <Stat label="Allowable costs" value={result.costs} run={showStats} />
                <div className="rounded-xl bg-black/30 ring-1 ring-white/10 px-4 py-3">
                  <p className="text-xs uppercase tracking-wide text-neutral-500">Disposals</p>
                  <p className="mt-1 text-lg font-semibold tabular-nums text-neutral-100">{result.disposals}</p>
                </div>
              </div>

              <p className="mt-5 text-sm text-emerald-200/70">
                <strong className="text-emerald-100">{result.filename}</strong> — SA108 summary,
                per-disposal workings, Section 104 pool history and FX detail.
              </p>
              <div className="mt-4 flex gap-3">
                <button onClick={() => saveBlob(result.blob, result.filename)} className={primaryBtn.emerald}>
                  Download report
                </button>
                <button onClick={reset} className={ghostBtn.emerald}>
                  Start over
                </button>
              </div>
            </section>
          )}

          {result && result.warningCount > 0 && (
            <details className="animate-fade-up rounded-xl bg-white/[0.03] p-4 text-sm text-neutral-400 ring-1 ring-white/10">
              <summary className="cursor-pointer font-medium text-neutral-300">
                {result.warningCount} processing note{result.warningCount === 1 ? "" : "s"}
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {result.warnings.map((w, i) => (<li key={i}>{w}</li>))}
                {result.warningsTruncated && (
                  <li>…and {result.warningCount - result.warnings.length} more, listed in the report's CGT Summary tab.</li>
                )}
              </ul>
            </details>
          )}
        </main>

        <footer className="mt-12 space-y-1 text-center text-xs text-neutral-500">
          <p>Stateless: your statements are processed in memory and never stored.</p>
          <p>TaxBuddy is not tax advice — check the workings (they're all in the spreadsheet) or ask a professional.</p>
        </footer>
      </div>
    </div>
  );
}

function Hero({ value }: { value: number }) {
  const v = useCountUp(value, true, 1100);
  return (
    <p className={`mt-1 text-5xl font-extrabold tracking-tight tabular-nums ${value >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
      {gbp(v)}
    </p>
  );
}
