import { Env, json, bad, requireAdmin, nowIso } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const body = await context.request.json().catch(() => ({}));
  const id = String(body?.id || "");
  const claimed_by = String(body?.claimed_by || "desktop");

  if (!id) return bad("Missing id");

  // only claim if NEW (atomic-ish: update with WHERE status='NEW')
  const res = await context.env.DB.prepare(`
    UPDATE submissions
    SET status='IN_REVIEW', claimed_by=?, claimed_at=?
    WHERE id=? AND status='NEW'
  `).bind(claimed_by, nowIso(), id).run();

  if ((res.meta?.changes || 0) < 1) {
    return bad("Could not claim (maybe already claimed)", 409);
  }

  return json({ ok: true });
}
