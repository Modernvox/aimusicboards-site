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

export const onRequestGet = async ({ env, request }: { env: Env; request: Request }) => {
  const origin = request.headers.get("Origin");
  const url = new URL(request.url);

  // You can tune these later; for now default to no minimum
  const minVotes = Math.max(0, Number(url.searchParams.get("minVotes") || 0));

  const rows = await env.DB.prepare(
    `
    SELECT
      v.submission_id,
      sub.artist_name,
      sub.track_title,
      sub.genre,
      ROUND(AVG(v.rating), 2) AS fan_avg,
      COUNT(*) AS fan_votes,
      sc.total AS judge_total
    FROM votes v
    JOIN submissions sub ON sub.id = v.submission_id
    JOIN scores sc ON sc.submission_id = v.submission_id
    WHERE sc.total >= 40
    GROUP BY v.submission_id
    HAVING COUNT(*) >= ?
    ORDER BY fan_avg DESC, fan_votes DESC
    LIMIT 50;
    `
  ).bind(minVotes).all<any>();

  return json({ ok: true, items: rows?.results || [] }, 200, origin);
};
