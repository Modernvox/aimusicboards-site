import { requireAdmin, bad, json } from "./_util";

export async function onRequest(context) {
  const { request, env } = context;

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

  const MAX_BYTES = 6 * 1024 * 1024;
  if (file.size > MAX_BYTES) return bad("Preview file too large", 400);

  const originalName = (file.name || "").trim().toLowerCase();
  const ext = (originalName.split(".").pop() || "").toLowerCase();
  const allowed = new Set(["mp3", "m4a", "wav", "aac", "ogg"]);
  if (!allowed.has(ext)) return bad("Unsupported preview type", 400);

  const key = `previews/${submission_id}.mp3`;

  await env.AIMB_BUCKET.put(key, file.stream(), {
    httpMetadata: { contentType: "audio/mpeg" },
  });

  await env.DB.prepare(`UPDATE scores SET preview_key=? WHERE submission_id=?`)
    .bind(key, submission_id)
    .run();

  return json({ ok: true, preview_key: key, preview_url: `/r2/${key}` });
}
