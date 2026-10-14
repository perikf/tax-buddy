import { useCallback, useMemo, useRef, useState } from "react";
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

const card =
  "rounded-2xl bg-white/[0.03] ring-1 ring-white/10 p-6 backdrop-blur-sm transition " +
  "shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_1px_2px_rgba(0,0,0,0.4),0_16px_48px_rgba(0,0,0,0.5)] " +
  "hover:ring-white/[0.14]";
const badge =
  "mr-2.5 inline-flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-b from-white to-neutral-300 " +
  "text-xs font-bold text-black ring-1 ring-white/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_2px_8px_rgba(0,0,0,0.6)] align-[2px]";
const input =
  "rounded-lg bg-white/[0.05] ring-1 ring-white/10 px-3 py-2 text-neutral-200 outline-none transition focus:ring-[#0070f3]";
const primaryBtn = {
  amber: "rounded-lg bg-gradient-to-b from-amber-300 to-amber-500 px-4 py-2 font-semibold text-amber-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
  emerald: "rounded-lg bg-gradient-to-b from-emerald-300 to-emerald-500 px-4 py-2 font-semibold text-emerald-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
};
const ghostBtn = {
  amber: "rounded-lg px-4 py-2 font-semibold text-amber-200 ring-1 ring-amber-400/30 transition hover:bg-amber-400/10",
  emerald: "rounded-lg px-4 py-2 font-semibold text-emerald-200 ring-1 ring-emerald-400/30 transition hover:bg-emerald-400/10",
};

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

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* ambient glow + dot grid */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div
          className="absolute inset-0 [background-image:radial-gradient(rgba(255,255,255,0.09)_1px,transparent_1px)] [background-size:26px_26px]
                     [mask-image:radial-gradient(ellipse_60%_45%_at_50%_0%,black,transparent)]"
        />
        <div className="absolute -top-40 left-1/2 h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-white/[0.06] blur-[140px]" />
        <div className="absolute bottom-0 right-0 h-[300px] w-[420px] rounded-full bg-white/[0.03] blur-[120px]" />
      </div>

      <div className="relative mx-auto max-w-2xl px-6 py-14">
        <header className="text-center mb-10">
          <h1 className="text-[2.75rem] font-extrabold tracking-tighter text-white">
            🧾 Tax
            <span className="bg-gradient-to-r from-[#007cf0] to-[#00dfd8] bg-clip-text text-transparent">
              Buddy
            </span>
          </h1>
          <p className="mt-3 text-neutral-400">
            IBKR statements in. HMRC-ready capital gains out.{" "}
            <span className="font-medium text-neutral-200">Under 10 seconds.</span>
          </p>
        </header>

        <main className="space-y-6">
          {/* Step 1 — upload */}
          <section className={card}>
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
              className={`cursor-pointer rounded-xl border border-dashed p-8 text-center transition
                ${dragging
                  ? "border-[#0070f3] bg-[#0070f3]/10 shadow-[0_0_40px_rgba(0,112,243,0.15)_inset]"
                  : "border-white/15 hover:border-white/30 hover:bg-white/[0.03]"}`}
            >
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-b from-white/[0.1] to-white/[0.02]
                              text-2xl ring-1 ring-white/15 shadow-[inset_0_1px_0_rgba(255,255,255,0.15),0_4px_16px_rgba(0,0,0,0.5)]">
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
                <li className="flex items-center gap-2 rounded-full bg-white/[0.06] px-3 py-1 text-sm text-neutral-300 ring-1 ring-white/[0.12]">
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
          </section>

          {/* Step 2 — period */}
          <section className={card}>
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
            {mode === "tax-year" ? (
              <div>
                <select value={year} onChange={(e) => setYear(e.target.value)} className={`w-36 ${input}`}>
                  {years.map((y) => (
                    <option key={y.label} value={y.label} className="bg-[#111114]">
                      {y.label}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-sm text-neutral-500">
                  {period.start} → {period.end}
                </p>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} className={input} />
                <span className="text-neutral-500">to</span>
                <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} className={input} />
              </div>
            )}
          </section>

          {/* Step 3 — go */}
          <button onClick={submit} disabled={!ready || busy}
            className="w-full rounded-2xl bg-gradient-to-b from-white to-neutral-200 py-4 text-lg font-bold tracking-tight text-black
                       ring-1 ring-white/20 transition
                       shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_0_40px_rgba(255,255,255,0.12),0_12px_32px_rgba(0,0,0,0.5)]
                       hover:from-neutral-100 hover:to-neutral-300 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_0_64px_rgba(255,255,255,0.2),0_12px_32px_rgba(0,0,0,0.5)]
                       active:scale-[0.99]
                       disabled:from-white/[0.06] disabled:to-white/[0.04] disabled:text-neutral-500 disabled:ring-white/10 disabled:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] disabled:cursor-not-allowed">
            {busy ? (
              <span className="inline-flex items-center gap-3">
                <span className="h-5 w-5 animate-spin rounded-full border-2 border-black/70 border-t-transparent" />
                Applying HMRC matching rules…
              </span>
            ) : (
              "Calculate my gains →"
            )}
          </button>

          {error && (
            <section className="rounded-2xl bg-red-500/[0.07] p-5 text-red-300 ring-1 ring-red-500/20">
              <p className="font-semibold text-red-200">Something went wrong</p>
              <p className="mt-1 text-sm">{error}</p>
            </section>
          )}

          {result && hasGaps && (
            <section className="rounded-2xl bg-amber-500/[0.07] p-6 ring-1 ring-amber-500/20">
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

          {result && !hasGaps && (
            <section className="rounded-2xl bg-emerald-500/[0.07] p-6 ring-1 ring-emerald-500/20">
              <h3 className="font-bold text-emerald-200">✅ Done — your report is ready</h3>
              <p className="mt-1 text-sm text-emerald-200/70">
                <strong className="text-emerald-100">{result.filename}</strong> — CGT summary with SA108
                boxes, per-disposal workings, Section 104 pool history and FX detail.
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
            <details className="rounded-xl bg-white/[0.03] p-4 text-sm text-neutral-400 ring-1 ring-white/10">
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
