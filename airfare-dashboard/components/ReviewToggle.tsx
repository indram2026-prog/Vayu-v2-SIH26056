"use client";

import { useState } from "react";

export function ReviewToggle({
  date,
  initiallyReviewed,
}: {
  date: string;
  initiallyReviewed: boolean;
}) {
  const [reviewed, setReviewed] = useState(initiallyReviewed);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleClick() {
    if (reviewed || pending) return;

    // Optimistic: flip the UI the instant the analyst clicks, don't wait
    // for the round trip. This action succeeds the overwhelming majority
    // of the time (it's an internal sign-off write, not a payment), so
    // making the analyst wait ~200ms staring at a spinner for that is pure
    // cost with no real benefit — reconcile in the background instead.
    setReviewed(true);
    setPending(true);
    setFailed(false);

    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date }),
      });
      if (!res.ok) throw new Error(`review POST failed: ${res.status}`);
    } catch (err) {
      // Roll back — this is the part a fire-and-forget "optimistic" button
      // usually skips, and then quietly lies to the user.
      setReviewed(false);
      setFailed(true);
      console.error("[ReviewToggle] rolling back:", err);
    } finally {
      setPending(false);
    }
  }

  if (reviewed) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-down dark:text-down-dark">
        reviewed{pending ? " (saving)" : ""}
      </span>
    );
  }

  return (
    <button onClick={handleClick} className="btn" disabled={pending}>
      {failed ? "retry sign-off" : "mark reviewed"}
    </button>
  );
}
