// functions/api/paid_checkout.ts
import { Env, json, bad } from "./_util";

function formEncode(params: Record<string, string | number | boolean | undefined | null>) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    usp.append(k, String(v));
  }
  return usp.toString();
}

export async function onRequest(context: { request: Request; env: Env }) {
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  let body: any;
  try {
    body = await context.request.json();
  } catch {
    return bad("Invalid JSON");
  }

  const submission_id = String(body.submission_id || "").trim();
  const paid_type = String(body.paid_type || "").trim().toUpperCase(); // "SKIP" | "UPNEXT"

  if (!submission_id) return bad("Missing submission_id");
  if (paid_type !== "SKIP" && paid_type !== "UPNEXT") return bad("Invalid paid_type");

  const secret = context.env.STRIPE_SECRET_KEY;
  const baseUrl = context.env.PUBLIC_BASE_URL;

  if (!secret) return bad("Server missing STRIPE_SECRET_KEY", 500);
  if (!baseUrl) return bad("Server missing PUBLIC_BASE_URL", 500);

  const amount = paid_type === "UPNEXT" ? 2000 : 500;
  const label = paid_type === "UPNEXT" ? "Up Next (Priority Review)" : "Skip the Line (Priority Review)";

  // Create a Stripe Checkout Session via Stripe API (no Stripe SDK)
  const stripeResp = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${secret}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: formEncode({
      mode: "payment",
      "payment_method_types[0]": "card",

      // line_items[0]
      "line_items[0][quantity]": 1,
      "line_items[0][price_data][currency]": "usd",
      "line_items[0][price_data][unit_amount]": amount,
      "line_items[0][price_data][product_data][name]": label,

      // Helpful metadata (optional but recommended)
      "metadata[submission_id]": submission_id,
      "metadata[paid_type]": paid_type,

      success_url: `${baseUrl}/submit.html?paid=success`,
      cancel_url: `${baseUrl}/submit.html?paid=cancel`,
    }),
  });

  const stripeJson: any = await stripeResp.json().catch(() => ({}));

  if (!stripeResp.ok) {
    const msg =
      stripeJson?.error?.message ||
      stripeJson?.error ||
      "Stripe checkout session create failed.";
    return bad(msg, 500);
  }

  const sessionId = String(stripeJson.id || "");
  const checkoutUrl = String(stripeJson.url || "");

  if (!sessionId || !checkoutUrl) {
    return bad("Stripe did not return a session URL.", 500);
  }

  // Mark submission as pending payment + store Stripe session id
  await context.env.DB.prepare(`
    UPDATE submissions
    SET payment_status = 'PENDING',
        paid_type = ?,
        stripe_session_id = ?
    WHERE id = ?
  `).bind(paid_type, sessionId, submission_id).run();

  return json({ ok: true, checkout_url: checkoutUrl, stripe_session_id: sessionId });
}
