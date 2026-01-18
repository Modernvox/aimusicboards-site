export interface Env {
  DB: D1Database;
  VOTE_SALT: string; // <-- add this secret in Pages/Workers env vars
}

function corsHeaders(origin: string | null) {
  return {
    "Access-Control-Allow-Origin": origin ?? "*",
    "Access-Control-Allow-Methods": "GET,HEAD,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(data: any, status = 200, origin: string | null = null, extraHeaders: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      ...corsHeaders(origin),
      ...extraHeaders,
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

function makeVoterId(): string {
  // Cloudflare runtime supports crypto.randomUUID()
  return crypto.randomUUID();
}

function setVoterCookie(voterId: string) {
  // 1 year
  const maxAge = 60 * 60 * 24 * 365;
  // SameSite=Lax so it works on normal browsing; Secure for HTTPS.
  return `voter_id=${encodeURIComponent(voterId)}; Path=/; Max-Age=${maxAge}; SameSite=Lax; Secure`;
}

function getClientIp(request: Request): string {
  // Cloudflare provides this header
  return request.headers.get("CF-Connecting-IP")
    || request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim()
    || "0.0.0.0";
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map(b => b.toString(16).padStart(2, "0")).join("");
}

function clampInt(n: any, min: number, max: number): number | null {
  const x = Number(n);
  if (!Number.isFinite(x)) return null;
  const i = Math.trunc(x);
  if (i < min || i > max) return null;
  return i;
}

async function isLeaderboardSong(env: Env, submissionId: string): Promise<boolean> {
  // Leaderboard-only rule: must have a score total >= 40
  const row = await env.DB.prepare(
    "SELECT total FROM scores WHERE submission_id = ?"
  ).bind(submissionId).first<{ total: number }>();

  return !!row && Number(row.total || 0) >= 40;
}

export const onRequestPost = async ({ env, request }: { env: Env; request: Request }) => {
  const origin = request.headers.get("Origin");

  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return json({ ok: false, error: "invalid_body" }, 400, origin);
  }

  const submission_id = String((body as any).submission_id || "").trim();
  const rating = clampInt((body as any).rating, 1, 10);

  if (!submission_id || !rating) {
    return json({ ok: false, error: "missing_fields" }, 400, origin);
  }

  // ✅ leaderboard-only enforcement
  const allowed = await isLeaderboardSong(env, submission_id);
  if (!allowed) {
    return json({ ok: false, error: "not_eligible" }, 403, origin);
  }

  // voter_id via cookie (browser UUID)
  const cookies = parseCookies(request);
  let voter_id = (cookies["voter_id"] || "").trim();
  let setCookieHeader: string | null = null;

  if (!voter_id) {
    voter_id = makeVoterId();
    setCookieHeader = setVoterCookie(voter_id);
  }

  // ip_hash = sha256(ip + salt)
  const ip = getClientIp(request);
  const salt = env.VOTE_SALT || "fallback_salt_change_me";
  const ip_hash = await sha256Hex(`${ip}:${salt}`);
  const created_at = new Date().toISOString();

  // ✅ Enforce one vote per IP per song (as requested)
  // If you decide this is too strict, remove this block (and the vote_ip_locks table usage).
  try {
    await env.DB.prepare(
      "INSERT INTO vote_ip_locks (submission_id, ip_hash, created_at) VALUES (?, ?, ?)"
    ).bind(submission_id, ip_hash, created_at).run();
  } catch (e: any) {
    const msg = String(e?.message || e || "");
    if (msg.toLowerCase().includes("unique") || msg.toLowerCase().includes("constraint")) {
      return json(
        { ok: false, error: "already_voted_ip" },
        409,
        origin,
        setCookieHeader ? { "Set-Cookie": setCookieHeader } : {}
      );
    }
    return json({ ok: false, error: "db_error_ip" }, 500, origin);
  }

  // ✅ Enforce one-and-done per browser UUID per song
  try {
    await env.DB.prepare(
      "INSERT INTO votes (submission_id, voter_id, rating, ip_hash, created_at) VALUES (?, ?, ?, ?, ?)"
    ).bind(submission_id, voter_id, rating, ip_hash, created_at).run();
  } catch (e: any) {
    // If this fails, also remove the ip lock we just inserted (so we don't block other voters on same IP)
    try {
      await env.DB.prepare(
        "DELETE FROM vote_ip_locks WHERE submission_id = ? AND ip_hash = ?"
      ).bind(submission_id, ip_hash).run();
    } catch {}

    const msg = String(e?.message || e || "");
    if (msg.toLowerCase().includes("unique") || msg.toLowerCase().includes("constraint")) {
      return json(
        { ok: false, error: "already_voted" },
        409,
        origin,
        setCookieHeader ? { "Set-Cookie": setCookieHeader } : {}
      );
    }
    return json({ ok: false, error: "db_error_vote" }, 500, origin);
  }

  // Return updated stats for this song
  const stats = await env.DB.prepare(
    `SELECT
        ROUND(AVG(rating), 2) AS avg_rating,
        COUNT(*) AS vote_count
     FROM votes
     WHERE submission_id = ?`
  ).bind(submission_id).first<{ avg_rating: number; vote_count: number }>();

  return json(
    {
      ok: true,
      submission_id,
      your_vote: rating,
      avg_rating: Number(stats?.avg_rating ?? 0),
      vote_count: Number(stats?.vote_count ?? 0),
    },
    200,
    origin,
    setCookieHeader ? { "Set-Cookie": setCookieHeader } : {}
  );
};
