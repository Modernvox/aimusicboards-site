import { Env, bad, json, requireAdmin } from "./_util";

export async function onRequest(context: any) {
  const { request, env } = context as { request: Request; env: Env };

  const err = requireAdmin(request, env);
  if (err) return bad(err, 401);

  if (request.method !== "POST") return bad("Method not allowed", 405);

  const ct = request.headers.get("content-type") || "";
  if (!ct.includes("multipart/form-data")) return bad("Expected multipart/form-data", 400);

  const form = await request.formData();
  const file = form.get("file");
  const submission_id = String(form.get("submission_id") || "").trim();

  if (!submission_id) return bad("Missing submission_id", 400);
  if (!(file instanceof File)) return bad("Missing file field named 'file'", 400);

  // Only accept short previews (guard rails)
  const MAX_BYTES = 6 * 1024 * 1024; // 6MB
  if (file.size > MAX_BYTES) return bad("Preview file too large", 400);

  const name = (file.name || "").toLowerCase();
  const ext = (name.split(".").pop() || "").toLowerCase();
  const allowed = new Set(["mp3", "m4a", "wav", "aac", "ogg"]);
  if (!allowed.has(ext)) return bad("Unsupported preview type", 400);

  const key = `previews/${submission_id}.${ext}`;

  // @ts-ignore - your env binding must include AIMB_BUCKET
  await env.AIMB_BUCKET.put(key, file.stream(), {
    httpMetadata: { contentType: file.type || "application/octet-stream" },
  });

  // Save preview_key on the score record
  await env.DB.prepare(`
    UPDATE scores SET preview_key = ?
    WHERE submission_id = ?
  `).bind(key, submission_id).run();

  return json({ ok: true, preview_key: key, preview_url: `/r2/${key}` });
}
