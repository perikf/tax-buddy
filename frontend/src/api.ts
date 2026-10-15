export interface HistoryGap {
  symbol: string;
  pool_qty: string;
  open_qty: string | null;
  gap: string | null;
  first_trade_is_sell: boolean;
}

export interface Capped<T> {
  items: T[];
  count: number;
  truncated: boolean;
}

export interface CalcResult {
  blob: Blob;
  filename: string;
  warnings: Capped<string>;
  gaps: Capped<HistoryGap>;
  proceeds: number;
  costs: number;
  netGain: number;
  disposals: number;
}

const EMPTY = { items: [], count: 0, truncated: false };

export async function calculate(
  files: File[],
  startDate: string,
  endDate: string,
  periodLabel: string
): Promise<CalcResult> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("start_date", startDate);
  form.append("end_date", endDate);
  if (periodLabel) form.append("period_label", periodLabel);

  const resp = await fetch("/calculate", { method: "POST", body: form });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.message ?? `Server error (${resp.status})`);
  }
  const filename =
    resp.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ??
    "TaxBuddy_CGT.xlsx";
  const meta = JSON.parse(resp.headers.get("X-TaxBuddy-Meta") ?? "{}");
  return {
    blob: await resp.blob(),
    filename,
    warnings: meta.warnings ?? EMPTY,
    gaps: meta.gaps ?? EMPTY,
    proceeds: meta.proceeds_gbp ?? 0,
    costs: meta.costs_gbp ?? 0,
    netGain: meta.net_gain_gbp ?? 0,
    disposals: meta.disposals ?? 0,
  };
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
