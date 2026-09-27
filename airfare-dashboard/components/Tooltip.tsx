"use client";

import { useState, useId } from "react";

export function InfoTooltip({ label }: { label: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        aria-describedby={id}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
        className="ml-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-muted/50
                   text-[9px] leading-none text-muted hover:border-ink hover:text-ink
                   dark:hover:border-ink-dark dark:hover:text-ink-dark transition-colors"
      >
        i
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-10 mb-1.5 w-52 -translate-x-1/2 rounded-md
                     border border-line dark:border-line-dark bg-card dark:bg-card-dark
                     px-2.5 py-1.5 text-xs font-sans leading-snug text-ink dark:text-ink-dark shadow-sm"
        >
          {label}
        </span>
      )}
    </span>
  );
}
