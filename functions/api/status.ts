import { Env, json, getSetting } from "./_util";

export async function onRequest(context: { env: Env }) {
  const env = context.env;

  // Settings:
  // - submissions_mode: "auto" | "manual"  (default: "manual")
  // - submissions_max_queue: "50"          (default: "50")   // applies to FREE queue only
  // - submissions_open: "1" | "0"          (manual toggle)
  const mode = (await getSetting(env, "submissions_mode")) || "manual";
  const maxQueue = Number((await getSetting(env, "submissions_max_queue")) || "50");
  const manualOpen = (await getSetting(env, "submissions_open")) === "1";

  // FREE queue count (cap applies to this)
  const freeRow = await env.DB
    .prepare(
      "SELECT COUNT(*) as c FROM submissions WHERE paid = 0 AND status IN ('NEW','IN_REVIEW')"
    )
    .first<{ c: number }>();
  const free_queue_count = Number(freeRow?.c || 0);

  // Paid queue count (informational; not capped)
  const paidRow = await env.DB
    .prepare(
      "SELECT COUNT(*) as c FROM submissions WHERE paid = 1 AND status IN ('NEW','IN_REVIEW')"
    )
    .first<{ c: number }>();
  const paid_queue_count = Number(paidRow?.c || 0);

  // AUTO applies only to FREE. Paid is always available.
  const autoOpenFree = free_queue_count < maxQueue;
  const submissions_open_free = mode === "auto" ? autoOpenFree : manualOpen;

  return json({
    ok: true,

    // keep your old field meaning: "free submissions open?"
    submissions_open: submissions_open_free,

    // explicit fields (nice for UI)
    submissions_open_free,
    submissions_open_paid: true,

    free_queue_count,
    paid_queue_count,

    submissions_mode: mode,
    submissions_max_queue: maxQueue,
  });
}