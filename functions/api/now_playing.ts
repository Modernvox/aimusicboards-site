export interface Env {
    DB: D1Database;
    ADMIN_TOKEN: string;
}

function corsHeaders(origin: string | null) {
    return {
        "Access-Control-Allow-Origin": origin ?? "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "86400",
    };
}

function json(data: any, status = 200, origin: string | null = null) {
    return new Response(JSON.stringify(data), {
        status,
        headers: {
            "Content-Type": "application/json; charset=utf-8",
            ...corsHeaders(origin),
        },
    });
}

function isAuthorized(request: Request, env: Env) {
    const auth = request.headers.get("Authorization") || "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
    return !!env.ADMIN_TOKEN && token === env.ADMIN_TOKEN;
}

export const onRequestOptions = async ({ request }: { request: Request }) => {
    const origin = request.headers.get("Origin");
    return new Response(null, { status: 204, headers: corsHeaders(origin) });
};

export const onRequestGet = async ({ env, request }: { env: Env; request: Request }) => {
    const origin = request.headers.get("Origin");

    const row = await env.DB.prepare(
        "SELECT updated_at, payload FROM now_playing WHERE id = 1"
    ).first<{ updated_at: string; payload: string }>();

    if (!row) {
        return json({ ok: true, updated_at: null, now_playing: null }, 200, origin);
    }

    let payloadObj: any = {};
    try {
        payloadObj = JSON.parse(row.payload || "{}");
    } catch {
        payloadObj = {};
    }

    return json({ ok: true, updated_at: row.updated_at, now_playing: payloadObj }, 200, origin);
};

export const onRequestPost = async ({ env, request }: { env: Env; request: Request }) => {
    const origin = request.headers.get("Origin");

    if (!isAuthorized(request, env)) {
        return json({ ok: false, error: "unauthorized" }, 401, origin);
    }

    const body = await request.json().catch(() => null);
    if (!body || typeof body !== "object") {
        return json({ ok: false, error: "invalid_body" }, 400, origin);
    }

    // Store the whole object as JSON text
    const payload = JSON.stringify(body);
    const updatedAt = new Date().toISOString();

    await env.DB.prepare(
        "UPDATE now_playing SET updated_at = ?, payload = ? WHERE id = 1"
    ).bind(updatedAt, payload).run();

    return json({ ok: true, updated_at: updatedAt }, 200, origin);
};
