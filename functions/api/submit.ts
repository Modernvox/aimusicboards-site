import { Env, json, bad, getSetting, nowIso, uuid } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const open = (await getSetting(context.env, "submissions_open")) === "1";
  if (!open) return bad("Submissions are only accepted during broadcasting.", 403);

  let body: any;
  try {
    body = await context.request.json();
  } catch {
    return bad("Invalid JSON");
  }

  const artist_name = String(body.artist_name || "").trim();
  const track_title = String(body.track_title || "").trim();
  const genre = String(body.genre || "").trim();
  const track_url = String(body.track_url || "").trim();
  const notes = String(body.notes || "").trim();

  if (!artist_name || !track_title || !genre || !track_url) {
    return bad("Missing required fields");
  }

  // basic URL sanity
  try { new URL(track_url); } catch { return bad("Track link must be a valid URL"); }

  // ✅ Duplicate protection (no schema changes)
  const normArtist = artist_name.toLowerCase().replace(/\s+/g, " ").trim();
  const normTitle  = track_title.toLowerCase().replace(/\s+/g, " ").trim();

  const dupeUrl = await context.env.DB
    .prepare(
      "SELECT id FROM submissions WHERE track_url = ? AND status IN ('NEW','IN_REVIEW') LIMIT 1"
    )
    .bind(track_url)
    .first<{ id: string }>();

  if (dupeUrl) {
    return bad("Duplicate: that track link is already in the queue.", 409);
  }

  const dupeName = await context.env.DB
    .prepare(
      `SELECT id FROM submissions
       WHERE LOWER(TRIM(artist_name)) = ? AND LOWER(TRIM(track_title)) = ?
         AND status IN ('NEW','IN_REVIEW')
       LIMIT 1`
    )
    .bind(normArtist, normTitle)
    .first<{ id: string }>();

  if (dupeName) {
    return bad("Duplicate: that artist + track title is already in the queue.", 409);
  }

  const id = uuid();
  const created_at = nowIso();

  await context.env.DB.prepare(`
    INSERT INTO submissions
      (id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'NEW')
  `).bind(id, created_at, artist_name, track_title, genre, track_url, notes || null).run();

  return json({ ok: true, id });
}
