import { Env, json, getSetting } from "./_util";

export async function onRequest(context: { env: Env }) {
  const open = (await getSetting(context.env, "submissions_open")) === "1";

  const row = await context.env.DB
    .prepare("SELECT COUNT(*) as c FROM submissions WHERE status IN ('NEW','IN_REVIEW')")
    .first<{ c: number }>();

  const queue_count = Number(row?.c || 0);

  return json({
    ok: true,
    submissions_open: open,
    queue_count,
  });
}

