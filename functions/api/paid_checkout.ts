import { Env, json, bad, nowIso, uuid } from "./_util";

function formEncode(params: Record<string, string | number | boolean | undefined | null>) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    usp.append(k, String(v));
  }
  return usp.toString();
}

function normalizeBaseUrl(raw: string) {
  const trimmed = String(raw || "").trim();
  const noTrailingSlash = trimmed.replace(/\/+$/, "");
  let u: URL;
  try {
    u = new URL(noTrailingSlash);
  } catch {
    throw new Error("PUBLIC_BASE_URL must be a full URL like https://aimusicboards.com");
  }
  if (u.protocol !== "https:" && u.protocol !== "http:") {
    throw new Error("PUBLIC_BASE_URL must start with https:// (recommended) or http://");
  }
  return noTrailingSlash;
}

function normalizeTrackKey(track_key: string) {
  let key = String(track_key || "").trim();

  // Legacy full URL -> key
  if (key.startsWith("http://") || key.startsWith("https://")) {
    try {
      const u = new URL(key);
      const m = u.pathname.match(/\/r2\/(uploads\/.+)$/);
      if (m && m[1]) key = m[1];
    } catch {}
  }

  const allowedExt = new Set(["mp3", "m4a", "wav", "aac", "ogg"]);
  const ext = (key.split(".").pop() || "").toLowerCase();
  if (!key.startsWith("uploads/") || !allowedExt.has(ext)) {
    throw new Error("Invalid track_key (must be like uploads/<id>.mp3)");
  }

  return key;
}

export async function onRequest(context: { request: Request; env: Env }) {
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  let body: any;
  try {
    body = await context.request.json();
  } catch {
    return bad("Invalid JSON");
  }

  let submission_id = String(body.submission_id || "").trim();
  const paid_type = String(body.paid_type || "").trim().toUpperCase(); // "SKIP" | "UPNEXT"

  if (paid_type !== "SKIP" && paid_type !== "UPNEXT") return bad("Invalid paid_type");

  const secret = context.env.STRIPE_SECRET_KEY;
  const baseUrlRaw = String(context.env.PUBLIC_BASE_URL || "");

  if (!secret) return bad("Server missing STRIPE_SECRET_KEY", 500);
  if (!baseUrlRaw.trim()) return bad("Server missing PUBLIC_BASE_URL", 500);

  let baseUrl: string;
  try {
    baseUrl = normalizeBaseUrl(baseUrlRaw);
  } catch (e: any) {
    return bad(`Server misconfigured: ${e?.message || "Invalid PUBLIC_BASE_URL"}`, 500);
  }

  const successUrl = `${baseUrl}/submit.html?paid=success`;
  const cancelUrl = `${baseUrl}/submit.html?paid=cancel`;

  const amount = paid_type === "UPNEXT" ? 2000 : 500;
  const label =
    paid_type === "UPNEXT"
      ? "Up Next (Priority Review)"
      : "Skip the Line (Priority Review)";

  // ✅ If no submission_id provided, create a paid-intent submission now.
  if (!submission_id) {
    const artist_name = String(body.artist_name || "").trim();
    const track_title = String(body.track_title || "").trim();
    const genre = String(body.genre || "").trim();
    const notes = String(body.notes || "").trim();
    let track_key = String(body.track_key || body.track_url || "").trim();

    if (!artist_name || !track_title || !genre || !track_key) {
      return bad("Missing fields to create paid submission (artist_name, track_title, genre, track_key)");
    }

    try {
      track_key = normalizeTrackKey(track_key);
    } catch (e: any) {
      return bad(e?.message || "Invalid track_key", 400);
    }

    submission_id = uuid();
    const created_at = nowIso();

    // Priority: UPNEXT > SKIP
    const priority = paid_type === "UPNEXT" ? 2 : 1;

    // Create a paid-intent submission (paid=0 until webhook confirms payment)
    await context.env.DB.prepare(`
      INSERT INTO submissions
        (id, created_at, artist_name, track_title, genre, track_url, notes, priority, paid, status, payment_status, paid_type)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'NEW', 'PENDING', ?)
    `).bind(
      submission_id, created_at, artist_name, track_title, genre, track_key, notes || null, priority, paid_type
    ).run();
  } else {
    // Ensure it exists
    const exists = await context.env.DB
      .prepare(`SELECT id FROM submissions WHERE id = ? LIMIT 1`)
      .bind(submission_id)
      .first<{ id: string }>();
    if (!exists) return bad("submission_id not found", 404);
  }

  // Create Stripe Checkout Session (no Stripe SDK)
  const stripeResp = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: formEncode({
      mode: "payment",
      "payment_method_types[0]": "card",

      "line_items[0][quantity]": 1,
      "line_items[0][price_data][currency]": "usd",
      "line_items[0][price_data][unit_amount]": amount,
      "line_items[0][price_data][product_data][name]": label,

      // Metadata used by webhook
      "metadata[submission_id]": submission_id,
      "metadata[paid_type]": paid_type,

      success_url: successUrl,
      cancel_url: cancelUrl,
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

  // Mark submission pending payment + store Stripe session id
  await context.env.DB.prepare(`
    UPDATE submissions
    SET payment_status = 'PENDING',
        paid_type = ?,
        stripe_session_id = ?
    WHERE id = ?
  `).bind(paid_type, sessionId, submission_id).run();

  return json({ ok: true, checkout_url: checkoutUrl, stripe_session_id: sessionId, submission_id });
}