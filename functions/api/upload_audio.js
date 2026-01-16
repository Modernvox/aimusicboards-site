export async function onRequest(context) {
  const { request, env } = context;

  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: cors });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: cors });
  }

  const ct = request.headers.get("content-type") || "";
  if (!ct.includes("multipart/form-data")) {
    return new Response("Expected multipart/form-data", { status: 400, headers: cors });
  }

  const form = await request.formData();
  const file = form.get("file");

  if (!(file instanceof File)) {
    return new Response("Missing file field named 'file'", { status: 400, headers: cors });
  }

  // Limits (tune as you want)
  const MAX_BYTES = 15 * 1024 * 1024; // 15MB
  if (file.size > MAX_BYTES) {
    return new Response("File too large (max 15MB)", { status: 400, headers: cors });
  }

  // Allow only audio-ish extensions (content-type is often unreliable)
  const originalName = (file.name || "").trim();
  const ext = (originalName.split(".").pop() || "").toLowerCase();

  const allowedExt = new Set(["mp3", "m4a", "wav", "aac", "ogg"]);
  if (!allowedExt.has(ext)) {
    return new Response(
      "Unsupported file type. Allowed: mp3, m4a, wav, aac, ogg",
      { status: 400, headers: cors }
    );
  }

  // Store in your lifecycle-managed prefix:
  const key = `uploads/${crypto.randomUUID()}.${ext}`;

  // Best effort content-type
  let contentType = "application/octet-stream";
  if (ext === "mp3") contentType = "audio/mpeg";
  else if (ext === "m4a") contentType = "audio/mp4";
  else if (ext === "wav") contentType = "audio/wav";
  else if (ext === "aac") contentType = "audio/aac";
  else if (ext === "ogg") contentType = "audio/ogg";


  await env.AIMB_BUCKET.put(key, file.stream(), {
    httpMetadata: { contentType },
  });

  const origin = new URL(request.url).origin;
  const audio_url = `${origin}/r2/${key}`;

  return new Response(
    JSON.stringify({ ok: true, key, audio_url }),
    {
      headers: { ...cors, "Content-Type": "application/json" },
      status: 200,
    }
  );
}
