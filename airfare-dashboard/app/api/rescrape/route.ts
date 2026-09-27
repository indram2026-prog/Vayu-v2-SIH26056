import { NextResponse } from "next/server";

// Triggers the etl-python pipeline via GitHub Actions' workflow_dispatch API,
// because that's the one place in this architecture that can actually run
// Scrapling's real headless browser: Vercel's serverless functions can't (no
// browser binary, ~60s execution ceiling, no persistent process). See
// DEPLOY_GUIDE.md, "Why GitHub Actions" for the full reasoning.
//
// Accepts an optional { mode: "quick" | "full" } JSON body from the caller.
// "quick" (default) scrapes the top 20 routes (a few minutes). "full"
// scrapes all 325 routes (can take a couple of hours).
//
// Needs three env vars set in Vercel (Project Settings -> Environment
// Variables), none of which are ever sent to the browser:
//   GITHUB_TOKEN          a fine-grained PAT with this repo's
//                         "Actions: write" permission
//   GITHUB_REPO           "your-username/your-repo"
//   GITHUB_WORKFLOW_FILE  defaults to "scrape.yml" if unset
export async function POST(request: Request) {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  const workflowFile = process.env.GITHUB_WORKFLOW_FILE || "scrape.yml";
  const ref = process.env.GITHUB_REF || "main";

  const body = await request.json().catch(() => ({}));
  const mode = body?.mode === "full" ? "full" : "quick";
  const top = mode === "full" ? "325" : "20";

  if (!token || !repo) {
    return NextResponse.json(
      {
        queued: false,
        error:
          "Live re-scrape isn't configured yet: GITHUB_TOKEN and GITHUB_REPO need to be set in Vercel's environment variables. See DEPLOY_GUIDE.md.",
      },
      { status: 501 }
    );
  }

  const res = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref,
        inputs: { mode, top },
      }),
    }
  );

  if (res.status !== 204) {
    const detail = await res.text();
    return NextResponse.json(
      { queued: false, error: `GitHub API returned ${res.status}: ${detail}` },
      { status: 502 }
    );
  }

  return NextResponse.json({ queued: true, mode });
}
