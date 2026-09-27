import { DataQuality } from "@/lib/types";
import { InfoTooltip } from "./Tooltip";

export function DataQualityPanel({ dq }: { dq: DataQuality }) {
  const sl = dq.source_layer;
  const stats: [string, string, string][] = [
    ["Raw records scraped", sl.total_raw_records.toLocaleString("en-IN"), "Every fare record any scraper returned before cleaning, across all sources."],
    [
      "Usable observations",
      `${sl.usable_observations.toLocaleString("en-IN")} (${(sl.usable_rate * 100).toFixed(1)}%)`,
      "Records that passed both parsing and the anomaly filter and were used in the index.",
    ],
    ["Anomalies filtered", `${sl.statistical_anomalies_removed}`, "Fares flagged as statistical outliers vs. the same carrier on other sources, same route, bucket and day."],
    ["Sold out or no fare", `${sl.null_fare_or_sold_out}`, "No price could be captured: sold out, or the source didn't return one."],
    ["Parse failures", `${sl.parse_failed}`, "Records outside the plausible fare band (₹500 to ₹60,000), likely a scraper glitch rather than a real price."],
    [
      "Route-days imputed",
      `${dq.imputed_via_carry_forward} (${(dq.imputation_rate * 100).toFixed(1)}%)`,
      "Missing route/day cells filled by carrying forward the last known price, never invented.",
    ],
  ];

  return (
    <div className="grid grid-cols-2 gap-5 sm:grid-cols-3">
      {stats.map(([label, value, help]) => (
        <div key={label}>
          <div className="nums text-xl font-semibold">{value}</div>
          <div className="flex items-center text-xs text-muted dark:text-muted-dark">
            {label}
            <InfoTooltip label={help} />
          </div>
        </div>
      ))}
    </div>
  );
}
