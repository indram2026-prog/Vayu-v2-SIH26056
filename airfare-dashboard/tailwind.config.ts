import type { Config } from "tailwindcss";

// Palette + type chosen for this brief specifically: a government statistical
// bulletin, not a startup product. No cream+terracotta, no rounded-card kit,
// no serif/mono combo — see app/globals.css header comment for the full
// rationale. Price semantics are directional (fare up = red, down = green),
// kept separate from the single neutral ink/accent used for the chart line
// and headline number so "the index moved" and "prices are bad/good" don't
// get visually conflated.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: "#F2F3EF", dark: "#15191C" },
        ink: { DEFAULT: "#171B1E", dark: "#E7E9E6" },
        muted: { DEFAULT: "#5B6670", dark: "#9AA3AA" },
        line: { DEFAULT: "#D8DCD6", dark: "#2B3236" },
        accent: { DEFAULT: "#22344F", dark: "#93A8C7" }, // chart line + headline number
        up: { DEFAULT: "#9A2B1E", dark: "#D97B6C" },      // fare increased
        down: { DEFAULT: "#1F6F5C", dark: "#6FBBA4" },    // fare decreased
        // Deliberately separate from up/down above: those two encode
        // "did the fare get worse or better" (a value judgment); these two
        // encode "is this row real data or a placeholder" (a provenance
        // fact). Reusing up/down for this would make a cheaper "sample" row
        // read as good news and a pricier "scraped" row read as bad news,
        // which has nothing to do with what the color is meant to show.
        live: { DEFAULT: "#1B7A3D", dark: "#5FD182" },     // route_daily_detail.source = 'scraped'
        sample: { DEFAULT: "#2563AC", dark: "#7FB2E8" },   // route_daily_detail.source = 'sample'
      },
      fontFamily: {
        sans: ["var(--font-public-sans)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
