import { Env, json, getSetting } from "./_util";

export async function onRequest(context: { env: Env }) {
  const open = (await getSetting(context.env, "submissions_open")) === "1";
  return json({ ok: true, submissions_open: open });
}
