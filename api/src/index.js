/**
 * 企業診断ＡＢＣ 2026（河合担当分）アンケート集計 API
 * Cloudflare Workers + D1。講義サイト（GitHub Pages）の survey/ 配下のページから呼び出す。
 *
 * 公開エンドポイント
 *   GET  /api/health                          動作確認
 *   GET  /api/sessions/:id                    受付状況（open / revealed / 回答数）
 *   POST /api/sessions/:id/responses          回答の送信 { client_id, answers:{q1:"a",...} }（同じ client_id は上書き）
 *   GET  /api/sessions/:id/results            集計。revealed=1 のとき（または教員キー付きのとき）だけ内訳 tallies を返す
 * 教員用（Authorization: Bearer <SURVEY_ADMIN_KEY>）
 *   GET    /api/admin/ping                    キーの確認
 *   GET    /api/admin/sessions                全回の受付状況
 *   PATCH  /api/admin/sessions/:id            { open?: bool, revealed?: bool } を更新
 *   GET    /api/admin/sessions/:id/export     回答一覧（CSV、匿名）
 *   DELETE /api/admin/sessions/:id/responses  回答の全削除（リハーサル後のリセット用）
 */

const ALLOWED_ORIGINS = new Set([
  "https://kklab.mobi",
  "https://katzkawai.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);
const SESSION_IDS = ["06", "07", "08", "09", "10"]; // 河合担当回
const QUESTION_KEY = /^q([1-9]|10)$/;
const CHOICE_VALUE = /^[a-h]$/;
const CLIENT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BODY_BYTES = 4096;

function cors(origin) {
  const h = { "Cache-Control": "no-store", Vary: "Origin" };
  if (origin) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Content-Type, Authorization";
    h["Access-Control-Max-Age"] = "86400";
  }
  return h;
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...cors(origin) },
  });
}

function fail(status, message, origin) {
  return json({ ok: false, error: message }, status, origin);
}

function nowIso() {
  return new Date().toISOString();
}

function isSession(id) {
  return SESSION_IDS.includes(id);
}

async function sessionState(db, id) {
  const row = await db.prepare("SELECT open, revealed, updated_at FROM sessions WHERE id = ?1").bind(id).first();
  return {
    open: row ? Number(row.open) === 1 : true,
    revealed: row ? Number(row.revealed) === 1 : false,
    updated_at: row ? row.updated_at : null,
  };
}

async function responseCount(db, id) {
  const row = await db.prepare("SELECT COUNT(*) AS n FROM responses WHERE session = ?1").bind(id).first();
  return row ? Number(row.n) : 0;
}

// 設問ごと・選択肢ごとの回答数。answers(JSON) を json_each で展開して集計する
async function tallies(db, id) {
  const { results } = await db
    .prepare(
      "SELECT j.key AS q, j.value AS choice, COUNT(*) AS n " +
        "FROM responses r, json_each(r.answers) AS j WHERE r.session = ?1 GROUP BY j.key, j.value",
    )
    .bind(id)
    .all();
  const out = {};
  for (const row of results || []) {
    if (!out[row.q]) out[row.q] = {};
    out[row.q][row.choice] = Number(row.n);
  }
  return out;
}

function safeEqual(a, b) {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.byteLength !== eb.byteLength) return false;
  return crypto.subtle.timingSafeEqual(ea, eb);
}

function isAdmin(request, env) {
  if (!env.SURVEY_ADMIN_KEY) return false;
  const m = (request.headers.get("Authorization") || "").match(/^Bearer\s+(.+)$/i);
  return Boolean(m) && safeEqual(m[1].trim(), env.SURVEY_ADMIN_KEY);
}

// Rate Limiting バインディング（未設定・失敗時は制限しない）
async function limited(binding, key) {
  if (!binding || !key) return false;
  try {
    const { success } = await binding.limit({ key });
    return !success;
  } catch (e) {
    return false;
  }
}

function parseAnswers(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const keys = Object.keys(raw);
  if (keys.length === 0 || keys.length > 10) return null;
  const answers = {};
  for (const k of keys) {
    if (!QUESTION_KEY.test(k)) return null;
    const v = raw[k];
    if (typeof v !== "string" || !CHOICE_VALUE.test(v)) return null;
    answers[k] = v;
  }
  return answers;
}

function parseFlag(v) {
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v === 1 || v === 0) return v;
  return null;
}

function csvCell(v) {
  const s = String(v ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const reqOrigin = request.headers.get("Origin");
    const origin = reqOrigin && ALLOWED_ORIGINS.has(reqOrigin) ? reqOrigin : null;
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const method = request.method.toUpperCase();
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";

    if (method === "OPTIONS") {
      return new Response(null, { status: origin ? 204 : 403, headers: cors(origin) });
    }
    // ブラウザからの呼び出しで Origin が許可リスト外なら拒否（Origin のない curl 等は通す）
    if (reqOrigin && !origin) return fail(403, "origin not allowed", null);

    if (path === "/api/health" && method === "GET") {
      return json({ ok: true, time: nowIso() }, 200, origin);
    }

    let m;

    // ---------- 公開 ----------
    if ((m = path.match(/^\/api\/sessions\/(\d{2})$/)) && method === "GET") {
      const id = m[1];
      if (!isSession(id)) return fail(404, "unknown session", origin);
      const [state, count] = await Promise.all([sessionState(env.DB, id), responseCount(env.DB, id)]);
      return json({ ok: true, session: id, ...state, count }, 200, origin);
    }

    if ((m = path.match(/^\/api\/sessions\/(\d{2})\/responses$/)) && method === "POST") {
      const id = m[1];
      if (!isSession(id)) return fail(404, "unknown session", origin);
      if (await limited(env.POST_LIMITER, ip)) return fail(429, "too many requests", origin);
      if (Number(request.headers.get("Content-Length") || 0) > MAX_BODY_BYTES) {
        return fail(413, "payload too large", origin);
      }
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return fail(400, "invalid json", origin);
      }
      const clientId = typeof body.client_id === "string" ? body.client_id.toLowerCase() : "";
      if (!CLIENT_ID.test(clientId)) return fail(400, "invalid client_id", origin);
      const answers = parseAnswers(body.answers);
      if (!answers) return fail(400, "invalid answers", origin);

      const state = await sessionState(env.DB, id);
      if (!state.open) return fail(409, "closed", origin);

      const t = nowIso();
      await env.DB.prepare(
        "INSERT INTO responses (session, client_id, answers, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?4) " +
          "ON CONFLICT(session, client_id) DO UPDATE SET answers = excluded.answers, updated_at = excluded.updated_at",
      )
        .bind(id, clientId, JSON.stringify(answers), t)
        .run();
      const count = await responseCount(env.DB, id);
      return json({ ok: true, session: id, count, revealed: state.revealed }, 200, origin);
    }

    if ((m = path.match(/^\/api\/sessions\/(\d{2})\/results$/)) && method === "GET") {
      const id = m[1];
      if (!isSession(id)) return fail(404, "unknown session", origin);
      const admin = isAdmin(request, env);
      const [state, count] = await Promise.all([sessionState(env.DB, id), responseCount(env.DB, id)]);
      const payload = { ok: true, session: id, ...state, count, admin };
      if (state.revealed || admin) payload.tallies = await tallies(env.DB, id);
      return json(payload, 200, origin);
    }

    // ---------- 教員用 ----------
    if (path.startsWith("/api/admin/")) {
      if (await limited(env.AUTH_LIMITER, ip)) return fail(429, "too many requests", origin);
      if (!isAdmin(request, env)) return fail(401, "unauthorized", origin);

      if (path === "/api/admin/ping" && method === "GET") {
        return json({ ok: true }, 200, origin);
      }

      if (path === "/api/admin/sessions" && method === "GET") {
        const sessions = [];
        for (const id of SESSION_IDS) {
          const [state, count] = await Promise.all([sessionState(env.DB, id), responseCount(env.DB, id)]);
          sessions.push({ session: id, ...state, count });
        }
        return json({ ok: true, sessions }, 200, origin);
      }

      if ((m = path.match(/^\/api\/admin\/sessions\/(\d{2})$/)) && method === "PATCH") {
        const id = m[1];
        if (!isSession(id)) return fail(404, "unknown session", origin);
        let body;
        try {
          body = await request.json();
        } catch (e) {
          return fail(400, "invalid json", origin);
        }
        const open = parseFlag(body.open);
        const revealed = parseFlag(body.revealed);
        if (open === null && revealed === null) return fail(400, "nothing to update", origin);
        await env.DB.prepare(
          "INSERT INTO sessions (id, open, revealed, updated_at) VALUES (?1, COALESCE(?2, 1), COALESCE(?3, 0), ?4) " +
            "ON CONFLICT(id) DO UPDATE SET open = COALESCE(?2, open), revealed = COALESCE(?3, revealed), updated_at = excluded.updated_at",
        )
          .bind(id, open, revealed, nowIso())
          .run();
        const [state, count] = await Promise.all([sessionState(env.DB, id), responseCount(env.DB, id)]);
        return json({ ok: true, session: id, ...state, count }, 200, origin);
      }

      if ((m = path.match(/^\/api\/admin\/sessions\/(\d{2})\/responses$/)) && method === "DELETE") {
        const id = m[1];
        if (!isSession(id)) return fail(404, "unknown session", origin);
        const r = await env.DB.prepare("DELETE FROM responses WHERE session = ?1").bind(id).run();
        return json({ ok: true, session: id, deleted: r.meta ? r.meta.changes : null }, 200, origin);
      }

      if ((m = path.match(/^\/api\/admin\/sessions\/(\d{2})\/export$/)) && method === "GET") {
        const id = m[1];
        if (!isSession(id)) return fail(404, "unknown session", origin);
        const { results } = await env.DB.prepare(
          "SELECT answers, created_at, updated_at FROM responses WHERE session = ?1 ORDER BY created_at",
        )
          .bind(id)
          .all();
        const rows = (results || []).map((r) => ({ ...r, answers: JSON.parse(r.answers) }));
        const qs = new Set();
        rows.forEach((r) => Object.keys(r.answers).forEach((k) => qs.add(k)));
        const qcols = [...qs].sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
        const lines = [["no", "created_at", "updated_at", ...qcols].join(",")];
        rows.forEach((r, i) => {
          lines.push([i + 1, r.created_at, r.updated_at, ...qcols.map((q) => r.answers[q] || "")].map(csvCell).join(","));
        });
        return new Response("﻿" + lines.join("\r\n") + "\r\n", {
          status: 200,
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": `attachment; filename="ksabc2026-survey${id}.csv"`,
            ...cors(origin),
          },
        });
      }

      return fail(404, "not found", origin);
    }

    return fail(404, "not found", origin);
  },
};
