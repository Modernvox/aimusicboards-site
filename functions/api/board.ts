import { Env, json } from "./_util";

export async function onRequest(context: { env: Env }) {
  const { results } = await context.env.DB.prepare(`
    SELECT
      s.submission_id,
      sub.artist_name,
      sub.track_title,
      sub.genre,
      sub.track_url,
      s.total,
      s.scored_at
    FROM scores s
    JOIN submissions sub ON sub.id = s.submission_id
    WHERE s.approved = 1
    ORDER BY s.total DESC, s.scored_at DESC
    LIMIT 200
  `).all();

  return json({ ok: true, items: results });
}
