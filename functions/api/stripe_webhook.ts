import Stripe from "stripe";
import { Env, json } from "./_util";

export const onRequestPost: PagesFunction = async ({ request, env }: { request: Request; env: Env }) => {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: "2023-10-16" });

  const sig = request.headers.get("stripe-signature");
  const body = await request.text();

  if (!sig) {
    return new Response("Missing Stripe signature", { status: 400 });
  }

  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(body, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch (err: any) {
    console.error("Webhook signature verification failed:", err.message);
    return new Response("Invalid signature", { status: 400 });
  }

  // We only care about successful checkout completion
  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;

    if (!session.id) {
      return new Response("Missing session id", { status: 400 });
    }

    try {
      await env.DB.prepare(`
        UPDATE submissions
        SET payment_status = 'PAID'
        WHERE stripe_session_id = ?
      `).bind(session.id).run();

      console.log("Payment confirmed for session:", session.id);
    } catch (dbErr) {
      console.error("DB update failed:", dbErr);
      return new Response("Database update failed", { status: 500 });
    }
  }

  return json({ received: true });
};
