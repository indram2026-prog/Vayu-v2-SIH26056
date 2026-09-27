import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServerClient } from "@/lib/supabase";

// The one real mutation in this app: a MoSPI analyst signing off that a
// day's index number has been checked before it's treated as final. This is
// what the optimistic-rendering UI (components/ReviewToggle.tsx) is
// optimistic ABOUT — the client flips to "Reviewed" instantly on click, then
// this call either confirms it or the client rolls the UI back.
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const date = body?.date;
  if (!date || typeof date !== "string") {
    return NextResponse.json({ ok: false, error: "missing 'date'" }, { status: 400 });
  }

  const supabase = getSupabaseServerClient();
  if (!supabase) {
    // No backend configured (e.g. local demo) — simulate success so the
    // optimistic-UI flow is still demoable, but never claim it persisted.
    return NextResponse.json({ ok: true, date, persisted: false });
  }

  const { error } = await supabase
    .from("daily_index_review")
    .upsert({ observation_date: date, reviewed_at: new Date().toISOString() });

  if (error) {
    console.error("[api/review] upsert failed:", error);
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, date, persisted: true });
}
