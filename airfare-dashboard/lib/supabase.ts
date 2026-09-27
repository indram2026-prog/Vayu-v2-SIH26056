import { createClient, SupabaseClient } from "@supabase/supabase-js";

let cachedClient: SupabaseClient | null = null;

/** Returns null (not a throw) when unconfigured, so callers can cleanly fall
 * back to sample data instead of every route handler needing its own
 * try/catch around a missing-env-var crash. */
export function getSupabaseServerClient(): SupabaseClient | null {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;

  if (!cachedClient) {
    cachedClient = createClient(url, key, {
      auth: { persistSession: false },
    });
  }
  return cachedClient;
}
