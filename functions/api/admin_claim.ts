// functions/api/admin_claim.ts
import { Env, json, bad, requireAdmin, nowIso } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const body = await context.request.json().catch(() => ({}));
  const id = String(body?.id || "").trim();
  const claimed_by = String(body?.claimed_by || "desktop").trim();

  if (!id) return bad("Missing id");

  // Claim if it's in the active queue state (NEW or SCORED) AND not already claimed
  // (atomic-ish because of the WHERE clause)
  const res = await context.env.DB.prepare(`
    UPDATE submissions
    SET status='IN_REVIEW',
        claimed_by=?,
        claimed_at=?
    WHERE id=?
      AND status IN ('NEW','SCORED')
      AND (claimed_by IS NULL OR claimed_by = '')
  `).bind(claimed_by, nowIso(), id).run();

  if ((res.meta?.changes || 0) < 1) {
    return bad("Could not claim (maybe already claimed or not in queue)", 409);
  }

  // Return the claimed row so your app can immediately see paid_type/payment_status
  const row = await context.env.DB.prepare(`
    SELECT
      id, created_at, artist_name, track_title, genre, track_url, notes,
      status, claimed_by, claimed_at,
      payment_status, paid_type, stripe_session_id
    FROM submissions
    WHERE id=?
    LIMIT 1
  `).bind(id).first();

  return json({ ok: true, submission: row });
}
