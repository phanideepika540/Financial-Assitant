import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight, BriefcaseBusiness, LoaderCircle, Plus, Trash2 } from "lucide-react";

type AssetClass = "Stocks" | "Bonds" | "Cash" | "Real estate" | "Other";
type Sector =
  | "Technology"
  | "Healthcare"
  | "Financials"
  | "Consumer discretionary"
  | "Consumer staples"
  | "Industrials"
  | "Energy"
  | "Materials"
  | "Utilities"
  | "Communication services"
  | "Real estate"
  | "Diversified / not applicable";

type Holding = {
  id?: number;
  name: string;
  asset_class: AssetClass;
  sector: Sector;
  market_value: number;
};

type HoldingTemplate = {
  name: string;
  assetClass: AssetClass;
  sector: Sector;
};

const ASSET_CLASSES: AssetClass[] = ["Stocks", "Bonds", "Cash", "Real estate", "Other"];
const HOLDING_TEMPLATES: HoldingTemplate[] = [
  { name: "Broad-market stock fund", assetClass: "Stocks", sector: "Diversified / not applicable" },
  { name: "International stock fund", assetClass: "Stocks", sector: "Diversified / not applicable" },
  { name: "Individual company stock", assetClass: "Stocks", sector: "Diversified / not applicable" },
  { name: "Bond index fund", assetClass: "Bonds", sector: "Diversified / not applicable" },
  { name: "U.S. Treasury securities", assetClass: "Bonds", sector: "Diversified / not applicable" },
  { name: "Cash or savings", assetClass: "Cash", sector: "Diversified / not applicable" },
  { name: "Real estate fund", assetClass: "Real estate", sector: "Real estate" },
];
const SECTORS: Sector[] = [
  "Technology",
  "Healthcare",
  "Financials",
  "Consumer discretionary",
  "Consumer staples",
  "Industrials",
  "Energy",
  "Materials",
  "Utilities",
  "Communication services",
  "Real estate",
  "Diversified / not applicable",
];
const COLORS = [
  "#0f766e",
  "#f59e0b",
  "#6366f1",
  "#ec4899",
  "#14b8a6",
  "#f97316",
  "#8b5cf6",
  "#84a51b",
  "#e05252",
  "#3b82f6",
  "#a855f7",
  "#64748b",
];

async function portfolioApi(holdings?: Holding[]): Promise<Holding[]> {
  const response = await fetch("/api/portfolio", {
    method: holdings ? "PUT" : "GET",
    credentials: "same-origin",
    headers: holdings ? { "Content-Type": "application/json" } : undefined,
    body: holdings
      ? JSON.stringify({
          holdings: holdings.map(({ name, asset_class, sector, market_value }) => ({
            name,
            asset_class,
            sector,
            market_value,
          })),
        })
      : undefined,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || "Could not load or save your portfolio.");
  }
  const result = (await response.json()) as { holdings: Holding[] };
  return result.holdings;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function PortfolioDashboard() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [selectedHolding, setSelectedHolding] = useState("");
  const [customHoldingName, setCustomHoldingName] = useState("");
  const [assetClass, setAssetClass] = useState<AssetClass>("Stocks");
  const [sector, setSector] = useState<Sector>("Diversified / not applicable");
  const [marketValue, setMarketValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    portfolioApi()
      .then((saved) => {
        if (active) setHoldings(saved);
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Could not load your portfolio.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function persist(next: Holding[]) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      setHoldings(await portfolioApi(next));
      setNotice("Your portfolio is saved to your account.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save your portfolio.");
    } finally {
      setSaving(false);
    }
  }

  function addHolding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(marketValue);
    const name = selectedHolding === "__custom__" ? customHoldingName.trim() : selectedHolding;
    if (!name || !Number.isFinite(value) || value <= 0) {
      setError("Enter a holding name and a market value greater than zero.");
      return;
    }
    if (holdings.length >= 100) {
      setError("A portfolio can contain at most 100 holdings.");
      return;
    }
    void persist([
      ...holdings,
      {
        name,
        asset_class: assetClass,
        sector,
        market_value: value,
      },
    ]);
    setSelectedHolding("");
    setCustomHoldingName("");
    setMarketValue("");
  }

  const total = holdings.reduce((sum, holding) => sum + holding.market_value, 0);
  const largestHolding = holdings.reduce<Holding | undefined>(
    (largest, holding) => (!largest || holding.market_value > largest.market_value ? holding : largest),
    undefined,
  );
  const largestWeight =
    largestHolding && total > 0 ? (largestHolding.market_value / total) * 100 : 0;
  const assetAllocation = useMemo(
    () => aggregate(holdings, (holding) => holding.asset_class),
    [holdings],
  );
  const sectorAllocation = useMemo(
    () => aggregate(holdings, (holding) => holding.sector).sort((a, b) => b.value - a.value),
    [holdings],
  );
  const holdingAllocation = useMemo(() => {
    const sorted = aggregate(holdings, (holding) => holding.name).sort(
      (a, b) => b.value - a.value,
    );
    if (sorted.length <= 8) return sorted;
    const visible = sorted.slice(0, 7);
    visible.push({
      label: "Other holdings",
      value: sorted.slice(7).reduce((sum, entry) => sum + entry.value, 0),
    });
    return visible;
  }, [holdings]);
  const gradient = makeDonutGradient(assetAllocation, total);
  const holdingPieGradient = makeDonutGradient(holdingAllocation, total);

  return (
    <section className="portfolio-section" id="portfolio">
      <div className="portfolio-heading">
        <div>
          <span className="conversation-kicker"><BriefcaseBusiness size={14} /> YOUR PORTFOLIO</span>
          <h2>Portfolio dashboard</h2>
          <p>Enter approximate holding values to explore how your portfolio is distributed.</p>
        </div>
        <span className="portfolio-private">Private to your account</span>
      </div>

      <div className="portfolio-disclaimer">
        <strong>For learning only.</strong> This dashboard uses values and classifications you enter. It does not connect to a brokerage, verify holdings, or recommend trades.
      </div>

      {error && <p className="portfolio-message error" role="alert">{error}</p>}
      {notice && <p className="portfolio-message success" role="status">{notice}</p>}
      {loading ? (
        <div className="portfolio-loading"><LoaderCircle className="spin" size={18} /> Loading saved holdings…</div>
      ) : (
        <>
          <div className="portfolio-summary-grid">
            <article className="portfolio-stat"><span>Total entered value</span><strong>{formatCurrency(total)}</strong><small>Based on your manual entries</small></article>
            <article className="portfolio-stat"><span>Holdings</span><strong>{holdings.length}</strong><small>Individual entries</small></article>
            <article className="portfolio-stat"><span>Largest holding</span><strong>{largestHolding ? `${largestWeight.toFixed(1)}%` : "—"}</strong><small>{largestHolding?.name ?? "Add holdings to begin"}</small></article>
          </div>

          <div className="portfolio-charts-grid">
            <article className="portfolio-card allocation-card">
              <div className="portfolio-card-heading"><div><span className="portfolio-overline">BY ASSET CLASS</span><h3>Asset allocation</h3></div></div>
              {total > 0 ? (
                <div className="donut-layout">
                  <div className="donut-chart" role="img" aria-label={`Asset-class allocation: ${assetAllocation.map((entry) => `${entry.label} ${((entry.value / total) * 100).toFixed(1)} percent`).join(", ")}`} style={{ background: gradient }}>
                    <div className="donut-center"><strong>{formatCurrency(total)}</strong><span>total value</span></div>
                  </div>
                  <ul className="chart-legend">
                    {assetAllocation.map((entry, index) => (
                      <li key={entry.label}><span className="legend-dot" style={{ background: COLORS[index % COLORS.length] }} /><span>{entry.label}</span><strong>{((entry.value / total) * 100).toFixed(1)}%</strong></li>
                    ))}
                  </ul>
                </div>
              ) : <ChartEmpty />}
            </article>

            <article className="portfolio-card">
              <div className="portfolio-card-heading"><div><span className="portfolio-overline">BY SECTOR</span><h3>Sector breakdown</h3></div></div>
              {total > 0 ? (
                <div className="portfolio-bars">
                  {sectorAllocation.map((entry, index) => (
                    <div className="portfolio-bar-row" key={entry.label}>
                      <div className="portfolio-bar-label"><span>{entry.label}</span><strong>{((entry.value / total) * 100).toFixed(1)}%</strong></div>
                      <div className="portfolio-bar-track"><span style={{ width: `${(entry.value / total) * 100}%`, background: COLORS[index % COLORS.length] }} /></div>
                    </div>
                  ))}
                </div>
              ) : <ChartEmpty />}
            </article>

            <article className="portfolio-card holdings-chart-card">
              <div className="portfolio-card-heading"><div><span className="portfolio-overline">BY HOLDING NAME</span><h3>Holding mix</h3></div></div>
              {total > 0 ? (
                <div className="pie-layout">
                  <div
                    className="pie-chart"
                    role="img"
                    aria-label={`Holding mix: ${holdingPieGradientLabel(holdingAllocation, total)}`}
                    style={{ background: holdingPieGradient }}
                  />
                  <ul className="chart-legend pie-legend">
                    {holdingAllocation.map((entry, index) => (
                      <li key={`${index}-${entry.label}`}>
                        <span className="legend-dot" style={{ background: COLORS[index % COLORS.length] }} />
                        <span title={entry.label}>{entry.label}</span>
                        <strong>{((entry.value / total) * 100).toFixed(1)}%</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : <ChartEmpty />}
              {holdingAllocation.length === 8 && aggregate(holdings, (holding) => holding.name).length > 8 && (
                <small className="chart-footnote">Smaller positions are grouped as Other holdings.</small>
              )}
            </article>

            <article className="portfolio-card diversification-card">
              <div className="portfolio-card-heading"><div><span className="portfolio-overline">A QUICK READ</span><h3>Diversification notes</h3></div></div>
              {total > 0 ? (
                <div className="diversification-notes">
                  <p><strong>{largestHolding?.name}</strong> is the largest entered position at <strong>{largestWeight.toFixed(1)}%</strong> of the total value.</p>
                  <p>Your entries span <strong>{assetAllocation.length}</strong> asset {assetAllocation.length === 1 ? "class" : "classes"} and <strong>{sectorAllocation.length}</strong> sector {sectorAllocation.length === 1 ? "category" : "categories"}.</p>
                  <p className="chart-footnote">These are descriptive concentration measures, not a complete diversification or risk assessment. Funds may contain overlapping underlying investments.</p>
                </div>
              ) : <ChartEmpty />}
            </article>
          </div>

          <article className="portfolio-card holdings-table-card">
            <div className="portfolio-card-heading"><div><span className="portfolio-overline">MANUAL ENTRIES</span><h3>Your holdings</h3></div><span className="holdings-count">{holdings.length} / 100</span></div>
            {holdings.length > 0 ? (
              <div className="holdings-table-wrap">
                <table className="holdings-table">
                  <thead><tr><th>Holding</th><th>Asset class</th><th>Sector</th><th>Market value</th><th><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>
                    {holdings.map((holding, index) => (
                      <tr key={holding.id ?? `${holding.name}-${index}`}>
                        <td>{holding.name}</td><td>{holding.asset_class}</td><td>{holding.sector}</td><td>{formatCurrency(holding.market_value)}</td>
                        <td><button className="holding-remove" type="button" disabled={saving} aria-label={`Remove ${holding.name}`} onClick={() => void persist(holdings.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="holdings-empty">No holdings yet. Add a manual entry below to see your charts.</p>}

            <form className="holding-form" onSubmit={addHolding}>
              <label>Holding name
                <select
                  value={selectedHolding}
                  onChange={(event) => {
                    const selected = event.target.value;
                    setSelectedHolding(selected);
                    const template = HOLDING_TEMPLATES.find((item) => item.name === selected);
                    if (template) {
                      setAssetClass(template.assetClass);
                      setSector(template.sector);
                    }
                  }}
                  required
                >
                  <option value="" disabled>Select an example</option>
                  {HOLDING_TEMPLATES.map((template) => <option key={template.name}>{template.name}</option>)}
                  <option value="__custom__">Custom holding name…</option>
                </select>
                <small className="holding-template-note">Examples only—not recommendations.</small>
                {selectedHolding === "__custom__" && (
                  <input
                    value={customHoldingName}
                    onChange={(event) => setCustomHoldingName(event.target.value)}
                    maxLength={80}
                    placeholder="Enter a custom holding name"
                    required
                  />
                )}
              </label>
              <label>Asset class<select value={assetClass} onChange={(event) => setAssetClass(event.target.value as AssetClass)}>{ASSET_CLASSES.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>Sector<select value={sector} onChange={(event) => setSector(event.target.value as Sector)}>{SECTORS.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>Market value (USD)<input type="number" value={marketValue} onChange={(event) => setMarketValue(event.target.value)} min="0.01" max="1000000000000" step="0.01" placeholder="e.g. 12500" required /></label>
              <button type="submit" className="primary-button holding-add" disabled={saving}><Plus size={15} />{saving ? "Saving…" : "Add holding"}</button>
            </form>
            {saving && <p className="portfolio-saving"><LoaderCircle className="spin" size={14} /> Saving portfolio…</p>}
          </article>
        </>
      )}
      <p className="portfolio-footnote"><ArrowRight size={13} /> Values are stored with your signed-in account. Do not enter account numbers or other sensitive identifiers.</p>
    </section>
  );
}

function aggregate(holdings: Holding[], category: (holding: Holding) => string) {
  const totals = new Map<string, number>();
  holdings.forEach((holding) => {
    totals.set(category(holding), (totals.get(category(holding)) ?? 0) + holding.market_value);
  });
  return Array.from(totals, ([label, value]) => ({ label, value }));
}

function holdingPieGradientLabel(entries: { label: string; value: number }[], total: number) {
  return entries
    .map((entry) => `${entry.label} ${((entry.value / total) * 100).toFixed(1)} percent`)
    .join(", ");
}

function makeDonutGradient(entries: { value: number }[], total: number): string {
  if (total <= 0) return "#e9e9e1";
  let start = 0;
  const slices = entries.map((entry, index) => {
    const end = start + (entry.value / total) * 100;
    const slice = `${COLORS[index % COLORS.length]} ${start}% ${end}%`;
    start = end;
    return slice;
  });
  return `conic-gradient(${slices.join(", ")})`;
}

function ChartEmpty() {
  return <div className="chart-empty"><BriefcaseBusiness size={20} /><p>Add holdings to see this visualization.</p></div>;
}

export default PortfolioDashboard;
