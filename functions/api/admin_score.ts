import { Env, json, bad, requireAdmin, nowIso } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const body = await context.request.json().catch(() => ({}));
  const submission_id = String(body?.submission_id || "");
  const scored_by = String(body?.scored_by || "desktop");

  const lyrics = Number(body?.lyrics ?? NaN);
  const delivery = Number(body?.delivery ?? NaN);
  const production = Number(body?.production ?? NaN);
  const originality = Number(body?.originality ?? NaN);
  const replay = Number(body?.replay ?? NaN);
  const notes = String(body?.notes || "").trim();

  if (!submission_id) return bad("Missing submission_id");

  const parts = [lyrics, delivery, production, originality, replay];
  if (parts.some(n => !Number.isInteger(n) || n < 0 || n > 10)) {
    return bad("Scores must be integers 0-10");
  }

  const total = lyrics + delivery + production + originality + replay;
  const approved = total >= 40 ? 1 : 0;

  // Insert/update score (one final score)
  await context.env.DB.prepare(`
    INSERT INTO scores
      (submission_id, scored_at, scored_by, lyrics, delivery, production, originality, replay, total, approved, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(submission_id) DO UPDATE SET
      scored_at=excluded.scored_at,
      scored_by=excluded.scored_by,
      lyrics=excluded.lyrics,
      delivery=excluded.delivery,
      production=excluded.production,
      originality=excluded.originality,
      replay=excluded.replay,
      total=excluded.total,
      approved=excluded.approved,
      notes=excluded.notes
  `).bind(
    submission_id, nowIso(), scored_by,
    lyrics, delivery, production, originality, replay,
    total, approved, notes || null
  ).run();

  await context.env.DB.prepare(`
    UPDATE submissions SET status='SCORED' WHERE id=?
  `).bind(submission_id).run();

  return json({ ok: true, total, approved: approved === 1 });
}
