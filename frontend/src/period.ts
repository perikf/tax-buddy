export interface TaxYear {
  label: string;
  start: string;
  end: string;
}

const FIRST_TAX_YEAR = 2015;

export function taxYears(): TaxYear[] {
  const today = new Date();
  const currentStart =
    today >= new Date(today.getFullYear(), 3, 6) ? today.getFullYear() : today.getFullYear() - 1;
  const years: TaxYear[] = [];
  for (let y = currentStart; y >= FIRST_TAX_YEAR; y--) {
    years.push({ label: `${y}/${String(y + 1).slice(2)}`, start: `${y}-04-06`, end: `${y + 1}-04-05` });
  }
  return years;
}

const GBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
export const gbp = (n: number) => GBP.format(n);
