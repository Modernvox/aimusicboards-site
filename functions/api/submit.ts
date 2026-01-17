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

  // We now expect an R2 object key like "uploads/<uuid>.mp3".
  // Allow legacy clients that might still send "track_url" as either:
  //   - the key itself ("uploads/..."), OR
  //   - a full URL containing "/r2/uploads/..."
  let track_key = String(body.track_key || body.track_url || "").trim();

  const notes = String(body.notes || "").trim();

  if (!artist_name || !track_title || !genre || !track_key) {
    return bad("Missing required fields");
  }

  // Normalize legacy full URL to an R2 key if possible
  // Example legacy: https://aimusicboards.com/r2/uploads/<uuid>.mp3
  if (track_key.startsWith("http://") || track_key.startsWith("https://")) {
    try {
      const u = new URL(track_key);
      const m = u.pathname.match(/\/r2\/(uploads\/.+)$/);
      if (m && m[1]) track_key = m[1];
    } catch {
      // If it's not a valid URL, we'll fail key validation below
    }
  }

  // Key validation: must be in uploads/ and must end with an allowed extension
  const allowedExt = new Set(["mp3", "m4a", "wav", "aac", "ogg"]);
  const ext = (track_key.split(".").pop() || "").toLowerCase();
  if (!track_key.startsWith("uploads/") || !allowedExt.has(ext)) {
    return bad("Invalid track_key (must be like uploads/<id>.mp3)", 400);
  }

  // ✅ Duplicate protection
  const normArtist = artist_name.toLowerCase().replace(/\s+/g, " ").trim();
  const normTitle = track_title.toLowerCase().replace(/\s+/g, " ").trim();

  // Dupe by exact uploaded object key while still active
  const dupeKey = await context.env.DB
    .prepare(
      "SELECT id FROM submissions WHERE track_url = ? AND status IN ('NEW','IN_REVIEW') LIMIT 1"
    )
    .bind(track_key)
    .first<{ id: string }>();

  if (dupeKey) {
    return bad("Duplicate: that track is already in the queue.", 409);
  }

  // Dupe by same artist+title while still active
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

  // Store the R2 key in track_url column for now (no schema change needed)
  await context.env.DB.prepare(`
    INSERT INTO submissions
      (id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'NEW')
  `).bind(id, created_at, artist_name, track_title, genre, track_key, notes || null).run();

  return json({ ok: true, id });
}
