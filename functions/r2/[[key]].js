export async function onRequest(context) {
  const { request, env, params } = context;

  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,HEAD,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: cors });
  }

  const parts = params.key || [];
  const key = Array.isArray(parts) ? parts.join("/") : String(parts || "");

  if (!key) {
    return new Response("Missing key", { status: 400, headers: cors });
  }

  const obj = await env.AIMB_BUCKET.get(key);

  if (!obj) {
    return new Response("Not found", { status: 404, headers: cors });
  }

  const headers = new Headers(cors);
  obj.writeHttpMetadata(headers);
  headers.set("Cache-Control", "public, max-age=3600");

  if (request.method === "HEAD") {
    return new Response(null, { headers });
  }

  return new Response(obj.body, { headers });
}
