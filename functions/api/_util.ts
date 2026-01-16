export type Env = {
  DB: D1Database;
  ADMIN_TOKEN?: string;
};

export function json(data: any, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export function bad(msg: string, status = 400) {
  return json({ ok: false, error: msg }, status);
}

export async function getSetting(env: Env, key: string): Promise<string | null> {
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = ?")
    .bind(key)
    .first<{ value: string }>();
  return row?.value ?? null;
}

export async function setSetting(env: Env, key: string, value: string) {
  await env.DB.prepare("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    .bind(key, value)
    .run();
}

export function requireAdmin(request: Request, env: Env): string | null {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!env.ADMIN_TOKEN) return "ADMIN_TOKEN not configured";
  if (token !== env.ADMIN_TOKEN) return "Unauthorized";
  return null;
}

export function nowIso() {
  return new Date().toISOString();
}

export function uuid() {
  // good-enough for IDs in this app
  return crypto.randomUUID();
}
