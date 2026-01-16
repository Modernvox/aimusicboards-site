import { Env, json, bad, requireAdmin, setSetting, getSetting } from "./_util";

export async function onRequest(context: { request: Request; env: Env }) {
  const err = requireAdmin(context.request, context.env);
  if (err) return bad(err, 401);

  if (context.request.method === "GET") {
    const open = (await getSetting(context.env, "submissions_open")) === "1";
    return json({ ok: true, submissions_open: open });
  }

  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const body = await context.request.json().catch(() => ({}));
  const open = body?.open === true;

  await setSetting(context.env, "submissions_open", open ? "1" : "0");
  return json({ ok: true, submissions_open: open });
}
