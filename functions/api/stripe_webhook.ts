// functions/api/stripe_webhook.ts
import { Env, json, bad } from "./_util";

function parseStripeSig(sigHeader: string) {
  // Format: t=timestamp,v1=hexsig,v1=hexsig2,...
  const parts = sigHeader.split(",").map(s => s.trim());
  let t = "";
  const v1: string[] = [];
  for (const p of parts) {
    const [k, ...rest] = p.split("=");
    const v = rest.join("=");
    if (k === "t") t = v;
    if (k === "v1") v1.push(v);
  }
  return { t, v1 };
}

function hexToBytes(hex: string) {
  const clean = hex.trim();
  if (clean.length % 2 !== 0) throw new Error("Invalid hex length");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function bytesToHex(bytes: Uint8Array) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256Hex(secret: string, message: string) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return bytesToHex(new Uint8Array(sig));
}

function timingSafeEqual(a: string, b: string) {
  // Constant-time-ish compare for same-length strings
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

export async function onRequest(context: { request: Request; env: Env }) {
  if (context.request.method !== "POST") return bad("Method not allowed", 405);

  const secret = context.env.STRIPE_WEBHOOK_SECRET;
  if (!secret) return bad("Server missing STRIPE_WEBHOOK_SECRET", 500);

  const sigHeader = context.request.headers.get("stripe-signature");
  if (!sigHeader) return bad("Missing Stripe signature", 400);

  // IMPORTANT: Stripe signature must be verified against RAW body text
  const rawBody = await context.request.text();

  const { t, v1 } = parseStripeSig(sigHeader);
  if (!t || v1.length === 0) return bad("Invalid Stripe signature header", 400);

  // Optional: timestamp tolerance (5 minutes)
  const toleranceSec = 300;
  const nowSec = Math.floor(Date.now() / 1000);
  const ts = parseInt(t, 10);
  if (!Number.isFinite(ts) || Math.abs(nowSec - ts) > toleranceSec) {
    return bad("Stale Stripe signature timestamp", 400);
  }

  const signedPayload = `${t}.${rawBody}`;
  const expected = await hmacSha256Hex(secret, signedPayload);

  const ok = v1.some(sig => timingSafeEqual(sig, expected));
  if (!ok) return bad("Invalid Stripe signature", 400);

  // Signature verified — parse event
  let event: any;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return bad("Invalid JSON body", 400);
  }

  if (event?.type === "checkout.session.completed") {
    const session = event?.data?.object;
    const sessionId = String(session?.id || "");
    if (!sessionId) return bad("Missing session id", 400);

    // ✅ Grab metadata you set in paid_checkout.ts
    const paid_type = String(session?.metadata?.paid_type || "").toUpperCase(); // "SKIP" | "UPNEXT"

    // ✅ Priority rule (tweak if you want)
    // UPNEXT outranks SKIP
    const priority = paid_type === "UPNEXT" ? 2 : 1;

    await context.env.DB.prepare(`
      UPDATE submissions
      SET payment_status = 'PAID',
          paid = 1,
          priority = ?,
          paid_type = COALESCE(paid_type, ?)
          -- If you create paid-intent submissions with status='PAYMENT_PENDING',
          -- uncomment the next line to move them into the live queue after payment:
          -- , status = 'NEW'
      WHERE stripe_session_id = ?
    `)
      .bind(priority, paid_type, sessionId)
      .run();
  }

  return json({ received: true });
}