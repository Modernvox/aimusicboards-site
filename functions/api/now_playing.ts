export interface Env {
  DB: D1Database;
  ADMIN_TOKEN: string;
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

function isAuthorized(request: Request, env: Env) {
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return !!env.ADMIN_TOKEN && token === env.ADMIN_TOKEN;
}

export const onRequestOptions = async ({ request }: { request: Request }) => {
  const origin = request.headers.get("Origin");
  return new Response(null, { status: 204, headers: corsHeaders(origin) });
};

function normalizeAudioUrl(request: Request, link: any) {
  if (!link || typeof link !== "string") return null;

  // already absolute
  if (link.startsWith("http://") || link.startsWith("https://")) return link;

  // handle "uploads/..." or "/uploads/..."
  const base = new URL(request.url).origin;
  const path = link.startsWith("/") ? link : `/${link}`;
  return `${base}${path}`;
}

export const onRequestGet = async ({ env, request }: { env: Env; request: Request }) => {
  const origin = request.headers.get("Origin");

  const row = await env.DB.prepare(
    "SELECT updated_at, payload FROM now_playing WHERE id = 1"
  ).first<{ updated_at: string; payload: string }>();

  if (!row) {
    return json({ ok: true, updated_at: null, now_playing: null }, 200, origin);
  }

  let payloadObj: any = {};
  try {
    payloadObj = JSON.parse(row.payload || "{}");
  } catch {
    payloadObj = {};
  }

  // ✅ Always provide a clean, absolute URL for clients to play
  const link = payloadObj.link ?? payloadObj.audio ?? payloadObj.audio_path ?? null;
  const audio_url = normalizeAudioUrl(request, link);
  if (audio_url) payloadObj.audio_url = audio_url;

  return json({ ok: true, updated_at: row.updated_at, now_playing: payloadObj }, 200, origin);
};

export const onRequestPost = async ({ env, request }: { env: Env; request: Request }) => {
  const origin = request.headers.get("Origin");

  if (!isAuthorized(request, env)) {
    return json({ ok: false, error: "unauthorized" }, 401, origin);
  }

  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return json({ ok: false, error: "invalid_body" }, 400, origin);
  }

  const payload = JSON.stringify(body);
  const updatedAt = new Date().toISOString();

  // ✅ UPSERT so it works even if row doesn't exist yet
  await env.DB.prepare(`
    INSERT INTO now_playing (id, updated_at, payload)
    VALUES (1, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      updated_at = excluded.updated_at,
      payload = excluded.payload
  `).bind(updatedAt, payload).run();

  return json({ ok: true, updated_at: updatedAt }, 200, origin);
};
