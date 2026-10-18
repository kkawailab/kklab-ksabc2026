-- 企業診断ＡＢＣ 2026（河合担当分）アンケート集計 API のスキーマ（Cloudflare D1 / SQLite）
-- 適用: npx wrangler d1 execute kklab-ksabc2026-survey --remote --config api/wrangler.jsonc --file api/schema.sql

-- 各回の受付状態。行がなければ open=1（受付中）, revealed=0（集計は非公開）として扱う
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,                 -- "06"〜"10"
  open INTEGER NOT NULL DEFAULT 1,     -- 1: 回答受付中, 0: 締切
  revealed INTEGER NOT NULL DEFAULT 0, -- 1: 集計結果を公開, 0: 非公開（回答数のみ）
  updated_at TEXT
);

-- 回答。匿名。端末ごとの client_id（UUID）で同じ回の再送信は上書きする
CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session TEXT NOT NULL,
  client_id TEXT NOT NULL,
  answers TEXT NOT NULL,               -- JSON: {"q1":"a","q2":"c",...}
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (session, client_id)
);
CREATE INDEX IF NOT EXISTS idx_responses_session ON responses (session);
