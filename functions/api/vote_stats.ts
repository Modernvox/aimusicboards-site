export interface Env {
  DB: D1Database;
}

function corsHeaders(origin: string | null) {
  return {
    "Access-Control-Allow-Origin": origin ?? "*",
    "Access-Control-Allow-Methods": "GET,HEAD,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(data: any, status = 200, origin: string | null = null) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      ...corsHeaders(origin),
    },
  });
}

export const onRequestOptions = async ({ request }: { request: Request }) => {
  const origin = request.headers.get("Origin");
  return new Response(null, { status: 204, headers: corsHeaders(origin) });
};

function parseCookies(request: Request): Record<string, string> {
  const raw = request.headers.get("Cookie") || "";
  const out: Record<string, string> = {};
  raw.split(";").forEach(part => {
    const idx = part.indexOf("=");
    if (idx === -1) return;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (k) out[k] = decodeURIComponent(v);
  });
  return out;
}

export const onRequestGet = async ({ env, request }: { env: Env; request: Request }) => {
  const origin = request.headers.get("Origin");
  const url = new URL(request.url);
  const submission_id = (url.searchParams.get("submission_id") || "").trim();

  if (!submission_id) {
    return json({ ok: false, error: "missing_submission_id" }, 400, origin);
  }

  const stats = await env.DB.prepare(
    `SELECT
        ROUND(AVG(rating), 2) AS avg_rating,
        COUNT(*) AS vote_count
     FROM votes
     WHERE submission_id = ?`
  ).bind(submission_id).first<{ avg_rating: number; vote_count: number }>();

  // if voter cookie exists, check if they voted
  const cookies = parseCookies(request);
  const voter_id = (cookies["voter_id"] || "").trim();

  let your_vote: number | null = null;
  if (voter_id) {
    const row = await env.DB.prepare(
      "SELECT rating FROM votes WHERE submission_id = ? AND voter_id = ?"
    ).bind(submission_id, voter_id).first<{ rating: number }>();
    if (row && Number.isFinite(Number(row.rating))) your_vote = Number(row.rating);
  }

  return json({
    ok: true,
    submission_id,
    avg_rating: Number(stats?.avg_rating ?? 0),
    vote_count: Number(stats?.vote_count ?? 0),
    your_vote,
  }, 200, origin);
};
