export interface HistoryGap {
  symbol: string;
  pool_qty: string;
  open_qty: string | null;
  gap: string | null;
  first_trade_is_sell: boolean;
}

export interface CalcResult {
  blob: Blob;
  filename: string;
  warningCount: number;
  warnings: string[];
  warningsTruncated: boolean;
  gapCount: number;
  gaps: HistoryGap[];
  gapsTruncated: boolean;
  historyVerified: boolean;
  proceeds: number;
  costs: number;
  netGain: number;
  disposals: number;
}

export async function calculate(
  file: File,
  startDate: string,
  endDate: string,
  periodLabel: string
): Promise<CalcResult> {
  const form = new FormData();
  form.append("file", file);
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
    warningCount: meta.warning_count ?? 0,
    warnings: meta.warnings ?? [],
    warningsTruncated: meta.warnings_truncated ?? false,
    gapCount: meta.gap_count ?? 0,
    gaps: meta.gaps ?? [],
    gapsTruncated: meta.gaps_truncated ?? false,
    historyVerified: meta.history_verified ?? true,
    proceeds: Number(meta.proceeds_gbp ?? 0),
    costs: Number(meta.costs_gbp ?? 0),
    netGain: Number(meta.net_gain_gbp ?? 0),
    disposals: Number(meta.disposals ?? 0),
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
