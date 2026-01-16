import { Env, json, bad, requireAdmin } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);

  const { results } = await context.env.DB.prepare(`
    SELECT id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status, claimed_by, claimed_at
    FROM submissions
    WHERE status IN ('NEW','IN_REVIEW')
    ORDER BY priority DESC, created_at ASC
    LIMIT 200
  `).all();

  return json({ ok: true, items: results });
}
