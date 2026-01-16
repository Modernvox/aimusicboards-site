// functions/api/admin_queue.ts
import { Env, json, bad, requireAdmin } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);

  const { results } = await context.env.DB.prepare(`
    SELECT
      id,
      created_at,
      artist_name,
      track_title,
      genre,
      track_url,
      notes,
      priority,
      paid,
      status,
      claimed_by,
      claimed_at,

      -- Stripe / paid queue fields
      payment_status,
      paid_type,
      stripe_session_id
    FROM submissions
    WHERE status IN ('NEW','IN_REVIEW')
    ORDER BY
      CASE
        WHEN payment_status='PAID' AND paid_type='UPNEXT' THEN 0
        WHEN payment_status='PAID' AND paid_type='SKIP'  THEN 1
        WHEN payment_status='PENDING' AND paid_type='UPNEXT' THEN 2
        WHEN payment_status='PENDING' AND paid_type='SKIP'  THEN 3
        ELSE 9
      END,
      created_at ASC
    LIMIT 200
  `).all();

  return json({ ok: true, items: results });
}
