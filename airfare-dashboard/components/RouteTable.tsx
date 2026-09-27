"use client";

import { useMemo, useState } from "react";
import { RouteDetail } from "@/lib/types";

function fmtINR(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

export function RouteTable({ routes }: { routes: RouteDetail[] }) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return routes;
    return routes.filter((r) => {
      return (
        r.route_id.toLowerCase().includes(q) ||
        r.origin_name?.toLowerCase().includes(q) ||
        r.destination_name?.toLowerCase().includes(q)
      );
    });
  }, [routes, query]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="relative w-full max-w-xs">
          <svg
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted dark:text-muted-dark"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <circle cx="9" cy="9" r="6.5" />
            <path d="M14 14L18 18" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search route or city (e.g. DEL-BOM, Chennai)"
            aria-label="Search routes"
            className="w-full rounded-md border border-line bg-transparent py-1.5 pl-8 pr-3 text-sm outline-none placeholder:text-muted focus:border-accent dark:border-line-dark dark:placeholder:text-muted-dark dark:focus:border-accent-dark"
          />
        </div>
        <span className="shrink-0 text-xs text-muted dark:text-muted-dark">
          {filtered.length === routes.length
            ? `${routes.length} routes`
            : `${filtered.length} of ${routes.length} routes`}
        </span>
      </div>

      <div className="mb-2 flex items-center gap-4 text-xs text-muted dark:text-muted-dark">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-live dark:bg-live-dark" /> Live scraped data
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-sample dark:bg-sample-dark" /> Sample / last known
        </span>
      </div>

      <div className="max-h-[28rem] overflow-y-auto rounded-md border border-line dark:border-line-dark">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-paper dark:bg-paper-dark">
            <tr className="text-left text-xs text-muted dark:text-muted-dark">
              <th className="py-1.5 pl-2 font-medium">Route</th>
              <th className="py-1.5 text-right font-medium">Weight</th>
              <th className="py-1.5 text-right font-medium">Base fare</th>
              <th className="py-1.5 text-right font-medium">Latest fare</th>
              <th className="py-1.5 pr-2 text-right font-medium">Change</th>
            </tr>
          </thead>
          <tbody className="nums">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 text-center text-xs text-muted dark:text-muted-dark">
                  No routes match &ldquo;{query}&rdquo;.
                </td>
              </tr>
            )}
            {filtered.map((r) => {
              const rel = r.price_relative;
              const relClass = rel == null ? "" : rel >= 1 ? "text-up dark:text-up-dark" : "text-down dark:text-down-dark";
              const relText = rel == null ? "—" : `${rel >= 1 ? "+" : ""}${((rel - 1) * 100).toFixed(2)}%`;
              const cityPair =
                r.origin_name && r.destination_name ? `${r.origin_name} – ${r.destination_name}` : undefined;
              const isLive = r.source === "scraped";
              return (
                <tr key={r.route_id} className="border-t border-line dark:border-line-dark">
                  <td className="py-1.5 pl-2">
                    <div className="flex items-center gap-1.5">
                      <span
                        title={isLive ? "Live scraped data" : "Sample / last known price"}
                        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                          isLive ? "bg-live dark:bg-live-dark" : "bg-sample dark:bg-sample-dark"
                        }`}
                      />
                      {r.route_id}
                    </div>
                    {cityPair && (
                      <div className="text-xs font-normal text-muted dark:text-muted-dark">{cityPair}</div>
                    )}
                  </td>
                  <td className="py-1.5 text-right">{(r.weight * 100).toFixed(r.weight < 0.001 ? 2 : 0)}%</td>
                  <td className="py-1.5 text-right">{fmtINR(r.base_price)}</td>
                  <td className="py-1.5 text-right">{fmtINR(r.latest_price)}</td>
                  <td className={`py-1.5 pr-2 text-right ${relClass}`}>{relText}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
