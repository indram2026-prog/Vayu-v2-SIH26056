"use client";

import { SWRConfig, Cache, useSWRConfig } from "swr";
import { useEffect, useRef } from "react";

const STORAGE_KEY = "airfare-index:swr-cache:v1";

function readStoredCache(): Map<string, any> {
  try {
    return new Map(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
  } catch {
    return new Map();
  }
}

/** Persists only the actual payload for each cached key, never SWR's
 * internal { data, error, isValidating } wrapper — mutate(key, value,
 * false) expects `value` to be the plain data, not that wrapper. */
function persistCache(cache: Cache) {
  try {
    const entries: [string, any][] = [];
    for (const key of cache.keys()) {
      const entry: any = cache.get(key);
      if (entry && entry.data !== undefined) {
        entries.push([key, entry.data]);
      }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage can throw (private browsing, quota) — caching is a
    // nice-to-have, never something a page should break over.
  }
}

/** Runs once, AFTER hydration has already committed — never during the
 * first render. Seeds SWR's cache from localStorage via `mutate`, using
 * the plain payload persisted above, which is exactly the shape useSWR's
 * `data` is expected to have. This is a normal post-mount state update
 * (like any fetch completing late), not part of the hydration diff. */
function CacheHydrator({ children }: { children: React.ReactNode }) {
  const { cache, mutate } = useSWRConfig();

  useEffect(() => {
    const stored = readStoredCache();
    stored.forEach((value, key) => {
      mutate(key, value, false);
    });

    const handleUnload = () => persistCache(cache);
    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, [cache, mutate]);

  return <>{children}</>;
}

export function SWRProvider({ children }: { children: React.ReactNode }) {
  const providerRef = useRef<() => Cache>();
  if (!providerRef.current) {
    // Always start empty — identical on the server AND on the client's
    // first render — so hydration never sees a structural mismatch.
    // The persisted cache is layered on afterwards, in CacheHydrator.
    providerRef.current = () => new Map() as unknown as Cache;
  }

  return (
    <SWRConfig
      value={{
        provider: providerRef.current,
        revalidateOnFocus: false,
        dedupingInterval: 60_000,
      }}
    >
      <CacheHydrator>{children}</CacheHydrator>
    </SWRConfig>
  );
}