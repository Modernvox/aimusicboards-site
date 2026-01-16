import { Env, json, cors, readJson, bad } from "./_util";

type PaidType = "REGULAR" | "SUPER";

const PRICE = {
  REGULAR: { amount: 500, label: "Skip the Line" },   // $5.00
  SUPER:   { amount: 2000, label: "Super Skip" },     // $20.00
};

export async function onRequest(context: { request: Request; env: Env }) {
  const { request, env } = context;

  if (request.method === "OPTIONS") return cors(request);

  if (request.method !== "POST") {
    return bad("Method not allowed", 405);
  }

  const body = await readJson(request);

  const paid_type = (body.paid_type || "").toString().toUpperCase() as PaidType;
  if (paid_type !== "REGULAR" && paid_type !== "SUPER") {
    return bad("Invalid paid_type. Use REGULAR or SUPER.");
  }

  if (body.lyrics_confirmed !== true) {
    return bad("Lyrics acknowledgement is required.");
  }

  const artist_name = (body.artist_name || "").toString().trim();
  const track_title = (body.track_title || "").toString().trim();
  const genre = (body.genre || "").toString().trim();
  const track_url = (body.track_url || "").toString().trim();
  const notes = (body.notes || "").toString().trim();

  if (!artist_name || !track_title || !genre || !track_url) {
    return bad("Missing required fields.");
  }

  const id = crypto.randomUUID();
  const created_at = new Date().toISOString();

  // Insert pending submission
  await env.DB.prepare(`
    INSERT INTO submissions
      (id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status, payment_status, paid_type)
    VALUES
      (?, ?, ?, ?, ?, ?, ?, 0, 1, 'PENDING_PAYMENT', 'PENDING', ?)
  `).bind(
    id, created_at, artist_name, track_title, genre, track_url, notes || null, paid_type
  ).run();

  const stripeKey = (env as any).STRIPE_SECRET_KEY;
  const baseUrl = (env as any).PUBLIC_BASE_URL || "https://aimusicboards.com";

  if (!stripeKey) return bad("Server missing STRIPE_SECRET_KEY.");

  const { amount, label } = PRICE[paid_type];

  // Create Stripe Checkout Session
  const form = new URLSearchParams();
  form.set("mode", "payment");
  form.set("success_url", `${baseUrl}/submit.html?paid=1&session_id={CHECKOUT_SESSION_ID}`);
  form.set("cancel_url", `${baseUrl}/submit.html?paid=0`);
  form.set("metadata[submission_id]", id);
  form.set("metadata[paid_type]", paid_type);

  // line item
  form.set("line_items[0][quantity]", "1");
  form.set("line_items[0][price_data][currency]", "usd");
  form.set("line_items[0][price_data][unit_amount]", String(amount)); // cents :contentReference[oaicite:4]{index=4}
  form.set("line_items[0][price_data][product_data][name]", `${label} • AI Music Board`);

  const resp = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${stripeKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: form.toString(),
  });

  const data = await resp.json<any>();
  if (!resp.ok) {
    // keep row for debugging but mark failed
    await env.DB.prepare(
      "UPDATE submissions SET payment_status='FAILED' WHERE id=?"
    ).bind(id).run();
    return bad(data?.error?.message || "Stripe error");
  }

  // Save Stripe session id for webhook lookup
  await env.DB.prepare(
    "UPDATE submissions SET stripe_session_id=? WHERE id=?"
  ).bind(data.id, id).run();

  return json({ ok: true, checkout_url: data.url });
}
