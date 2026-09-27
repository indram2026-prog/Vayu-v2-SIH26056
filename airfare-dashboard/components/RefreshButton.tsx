"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { IndexPayload, ScrapeRunStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 5000;
const POLL_TIMEOUT_MS = 6 * 60 * 1000; // a "quick" (top-20) pipeline run is a few minutes; give it 6 before giving up

type ScrapeState = "idle" | "queuing" | "running" | "completed" | "failed" | "unconfigured";

export function RefreshButton() {
  const { mutate } = useSWRConfig();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [scrapeState, setScrapeState] = useState<ScrapeState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollDeadline = useRef<number>(0);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  // The "instant" refresh: re-fetch the latest committed numbers from
  // Supabase right now, bypassing the 5-minute HTTP cache (?fresh=1 — see
  // app/api/index-data/route.ts). This does NOT scrape anything new; it
  // just guarantees you're looking at the most recent number the pipeline
  // has already computed, which is instant and fully Vercel-native.
  async function refreshFromSupabase() {
    setIsRefreshing(true);
    try {
      const fresh: IndexPayload = await fetch("/api/index-data?fresh=1", { cache: "no-store" }).then((r) => r.json());
      await mutate("/api/index-data", fresh, false);
    } finally {
      setIsRefreshing(false);
    }
  }

  function stopPolling() {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }

  async function pollOnce() {
    const res = await fetch("/api/rescrape/status", { cache: "no-store" });
    const status: ScrapeRunStatus = await res.json();

    if (!status.configured) {
      setScrapeState("unconfigured");
      setMessage("Live re-scrape needs Supabase connected first.");
      stopPolling();
      return;
    }
    if (status.status === "running") {
      setScrapeState("running");
      setMessage(`Scraping ${status.mode ?? ""} basket… (${status.target ?? "google_flights"})`);
    } else if (status.status === "completed") {
      setScrapeState("completed");
      setMessage(
        `Done — ${status.routes_scraped ?? 0} route(s) scraped` +
          (status.routes_anomalous ? `, ${status.routes_anomalous} filtered as anomalies` : "") +
          "."
      );
      stopPolling();
      await refreshFromSupabase();
    } else if (status.status === "failed") {
      setScrapeState("failed");
      setMessage(status.error ? `Scrape failed: ${status.error}` : "Scrape failed.");
      stopPolling();
    }

    if (Date.now() > pollDeadline.current) {
      stopPolling();
      setScrapeState("failed");
      setMessage("Timed out waiting for the scrape to finish — check the GitHub Actions tab directly.");
    }
  }

  async function runLiveScrape() {
    setScrapeState("queuing");
    setMessage("Queuing a live scrape…");
    const res = await fetch("/api/rescrape", { method: "POST" });
    const body = await res.json();

    if (!body.queued) {
      setScrapeState(res.status === 501 ? "unconfigured" : "failed");
      setMessage(body.error ?? "Could not start a live scrape.");
      return;
    }

    setScrapeState("running");
    setMessage("Scrape queued — this can take a few minutes.");
    pollDeadline.current = Date.now() + POLL_TIMEOUT_MS;
    pollTimer.current = setInterval(pollOnce, POLL_INTERVAL_MS);
  }

  const isBusy = scrapeState === "queuing" || scrapeState === "running";

  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={refreshFromSupabase}
          disabled={isRefreshing}
          className="rounded-md border border-line px-2.5 py-1 text-xs font-medium hover:border-accent disabled:opacity-50 dark:border-line-dark dark:hover:border-accent-dark"
        >
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
        <button
          onClick={runLiveScrape}
          disabled={isBusy}
          title="Kicks off a real scrape of the top 20 routes right now (takes a few minutes)"
          className="rounded-md border border-line px-2.5 py-1 text-xs font-medium hover:border-accent disabled:opacity-50 dark:border-line-dark dark:hover:border-accent-dark"
        >
          {isBusy ? "Scraping…" : "Run live scrape"}
        </button>
      </div>
      {message && (
        <p
          className={`text-xs ${
            scrapeState === "failed" || scrapeState === "unconfigured"
              ? "text-down dark:text-down-dark"
              : "text-muted dark:text-muted-dark"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
