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

  const id = uuid();
  const created_at = nowIso();

  // IMPORTANT:
  // - payment_status defaults to 'NONE' (per your ALTER TABLE)
  // - paid_type defaults NULL
  // - stripe_session_id defaults NULL
  await context.env.DB.prepare(`
    INSERT INTO submissions
      (id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'NEW')
  `).bind(id, created_at, artist_name, track_title, genre, track_url, notes || null).run();

  return json({ ok: true, id });
}
