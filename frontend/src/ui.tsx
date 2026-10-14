import { useEffect, useRef, useState, type ReactNode } from "react";
import { gbp } from "./period";

export const card =
  "spotlight-card relative overflow-hidden rounded-2xl bg-white/[0.03] ring-1 ring-white/10 p-6 backdrop-blur-sm transition " +
  "shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_1px_2px_rgba(0,0,0,0.4),0_16px_48px_rgba(0,0,0,0.5)] " +
  "hover:ring-white/[0.14]";
export const badge =
  "mr-2.5 inline-flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-b from-white to-neutral-300 " +
  "text-xs font-bold text-black ring-1 ring-white/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_2px_8px_rgba(0,0,0,0.6)] align-[2px]";
export const input =
  "h-10 rounded-lg bg-white/[0.05] ring-1 ring-white/10 px-3 text-neutral-200 outline-none transition focus:ring-[#0070f3]";
export const panel = {
  rose: "animate-fade-up rounded-2xl bg-rose-500/[0.07] p-6 ring-1 ring-rose-500/20",
  amber: "animate-fade-up rounded-2xl bg-amber-500/[0.07] p-6 ring-1 ring-amber-500/20",
  emerald: "animate-fade-up rounded-2xl bg-emerald-500/[0.07] p-6 ring-1 ring-emerald-500/20",
};
export const primaryBtn = {
  amber: "rounded-lg bg-gradient-to-b from-amber-300 to-amber-500 px-4 py-2 font-semibold text-amber-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
  emerald: "rounded-lg bg-gradient-to-b from-emerald-300 to-emerald-500 px-4 py-2 font-semibold text-emerald-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.4),0_4px_16px_rgba(0,0,0,0.4)] transition hover:brightness-105",
};
export const ghostBtn = {
  amber: "rounded-lg px-4 py-2 font-semibold text-amber-200 ring-1 ring-amber-400/30 transition hover:bg-amber-400/10",
  emerald: "rounded-lg px-4 py-2 font-semibold text-emerald-200 ring-1 ring-emerald-400/30 transition hover:bg-emerald-400/10",
};

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function useCountUp(target: number, duration = 1000): number {
  const [val, setVal] = useState(0);
  useEffect(() => {
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
  }, [target, duration]);
  return val;
}

export function Card({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const rect = useRef<DOMRect | null>(null);
  return (
    <section
      ref={ref}
      onPointerEnter={() => { rect.current = ref.current?.getBoundingClientRect() ?? null; }}
      onPointerMove={(e) => {
        const r = rect.current;
        if (!r || !ref.current) return;
        ref.current.style.setProperty("--mx", `${e.clientX - r.left}px`);
        ref.current.style.setProperty("--my", `${e.clientY - r.top}px`);
      }}
      className={`${card} animate-fade-up`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="relative z-[1]">{children}</div>
    </section>
  );
}

export function Stat({ label, value, format = gbp, tone = "neutral", hero = false }: {
  label?: string;
  value: number;
  format?: (n: number) => string;
  tone?: "neutral" | "net";
  hero?: boolean;
}) {
  const v = useCountUp(value, hero ? 1100 : 1000);
  const color =
    tone === "net" ? (value >= 0 ? "text-emerald-300" : "text-rose-300") : "text-neutral-100";
  if (hero) {
    return <p className={`mt-1 text-5xl font-extrabold tracking-tight tabular-nums ${color}`}>{format(v)}</p>;
  }
  return (
    <div className="rounded-xl bg-black/30 ring-1 ring-white/10 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${color}`}>{format(v)}</p>
    </div>
  );
}
