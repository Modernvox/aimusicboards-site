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

  // ✅ Public media paths (site visitors must be able to play these)
  const isPreview = key.startsWith("previews/");
  const isUpload = key.startsWith("uploads/");

  // ✅ Only non-public paths require admin
  if (!isPreview && !isUpload) {
    const err = requireAdmin(request, env);
    if (err) return new Response("Unauthorized", { status: 401, headers: cors });
  }

  const rangeHeader = request.headers.get("Range") || undefined;

  // IMPORTANT: Replace BUCKET name with your actual binding name:
  // e.g. env.R2_BUCKET, env.AIMB_BUCKET, etc.
  const bucket = (env as any).R2_BUCKET;
  if (!bucket) {
    return new Response("Server misconfigured: missing R2 bucket binding", {
      status: 500,
      headers: cors,
    });
  }

  const obj = await bucket.get(key, rangeHeader ? { range: rangeHeader } : undefined);

  if (!obj) {
    return new Response("Not found", { status: 404, headers: cors });
  }

  const headers = new Headers(cors);
  obj.writeHttpMetadata(headers);

  // Helpful for players + caching behavior
  headers.set("Accept-Ranges", "bytes");
  if (obj.httpEtag) headers.set("ETag", obj.httpEtag);

  headers.set(
    "Cache-Control",
    (isPreview || isUpload) ? "public, max-age=3600" : "no-store"
  );

  // If this was a range request, return 206
  const isRange = !!rangeHeader;
  const status = isRange ? 206 : 200;

  if (request.method === "HEAD") return new Response(null, { status, headers });

  return new Response(obj.body, { status, headers });
}
