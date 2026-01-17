import { Env, json, bad, requireAdmin, nowIso } from "./_util";

type Body = {
  id: string;
  status: "REJECTED" | "SKIPPED" | "DONE" | "ARCHIVED";
  reason?: string;
};

export async function onRequestPost(context: { env: Env; request: Request }) {
  const { env, request } = context;

  // Admin auth
  const err = requireAdmin(request, env);
  if (err) return bad(err, 401);

  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return bad("Invalid JSON body", 400);
  }

  const id = (body?.id || "").trim();
  const status = (body?.status || "").trim().toUpperCase() as Body["status"];
  const reason = (body?.reason || "").trim();

  if (!id) return bad("Missing id", 400);
  if (!status) return bad("Missing status", 400);

  const allowed = new Set(["REJECTED", "SKIPPED", "DONE", "ARCHIVED"]);
  if (!allowed.has(status)) return bad("Invalid status", 400);

  // Update so it disappears from admin_queue (which filters NEW/IN_REVIEW)
  await env.DB
    .prepare(
      `UPDATE submissions
       SET status = ?,
           claimed_by = NULL,
           claimed_at = NULL
       WHERE id = ?`
    )
    .bind(status, id)
    .run();

  return json({ ok: true, id, status, reason: reason || null, updated_at: nowIso() });
}
