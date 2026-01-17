import { Env, requireAdmin } from "../api/_util";

export async function onRequest(context: { request: Request; env: Env; params: any }) {
  const { request, env, params } = context;

  const cors: Record<string, string> = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,HEAD,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Range",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, ETag",
  };

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: cors });
  }

  const parts = params.key || [];
  const key = Array.isArray(parts) ? parts.join("/") : String(parts || "");

  if (!key) {
    return new Response("Missing key", { status: 400, headers: cors });
  }

  // ✅ Only previews are public. Everything else (uploads/) requires admin auth.
  const isPreview = key.startsWith("previews/");

  if (!isPreview) {
    const err = requireAdmin(request, env);
    if (err) return new Response("Unauthorized", { status: 401, headers: cors });
  }

  // ✅ Support byte-range requests (required for audio duration/seek)
  const range = request.headers.get("Range");
  const obj = await env.AIMB_BUCKET.get(key, range ? { range } : undefined);

  if (!obj) return new Response("Not found", { status: 404, headers: cors });

  const headers = new Headers(cors);
  obj.writeHttpMetadata(headers);

  // Helpful for players + caching behavior
  headers.set("Accept-Ranges", "bytes");
  headers.set("ETag", obj.httpEtag);

  headers.set("Cache-Control", isPreview ? "public, max-age=3600" : "no-store");

  // If this was a range request, R2 returns partial content — respond 206
  if (range) {
    // Some clients rely on Content-Range/Length; R2 includes these via writeHttpMetadata when ranged.
    return new Response(obj.body, { status: 206, headers });
  }

  if (request.method === "HEAD") return new Response(null, { headers });

  return new Response(obj.body, { headers });
}
