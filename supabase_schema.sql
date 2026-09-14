-- ============================================================================
-- Telegram Activity Monitor Bot — Supabase schema
--
-- QANDAY ISHLATILADI (2 usul):
--
-- 1) AVTOMATIK (tavsiya etiladi): shunchaki botni ishga tushiring —
--    app/database.py dagi PostgresDatabase.init() aynan shu DDL ni
--    bajarmoqda (CREATE TABLE IF NOT EXISTS — qayta ishga xavfsiz).
--
-- 2) QO'LDA: Supabase Dashboard → SQL Editor → New query → shu fayl
--    tarkibini to'liq joylashtiring → RUN.
--
-- Fayl idempotent: bir necha marta ishga tushirilsa, hech narsani
-- buzmaydi (mavjud jadvallar/indexlar qayta yaratilmaydi).
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    last_name      TEXT,
    is_banned      BOOLEAN NOT NULL DEFAULT FALSE,
    access_status  TEXT NOT NULL DEFAULT 'pending',
    reviewed_by    BIGINT,
    reviewed_at    TEXT,
    is_admin       BOOLEAN NOT NULL DEFAULT FALSE,
    premium_until  TEXT,
    connected_at   TEXT,
    last_activity  TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    duration_days  INTEGER NOT NULL,
    price          BIGINT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL,
    plan_id          BIGINT NOT NULL,
    receipt_file_id  TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL,
    reviewed_at      TEXT,
    reviewed_by      BIGINT
);

CREATE TABLE IF NOT EXISTS events (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    sender_id    BIGINT,
    chat_id      BIGINT,
    chat_title   TEXT,
    event_type   TEXT NOT NULL,
    message_id   BIGINT,
    details      TEXT NOT NULL DEFAULT '',
    occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    business_connection_id TEXT PRIMARY KEY,
    user_id                BIGINT NOT NULL,
    user_chat_id           BIGINT,
    is_enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    connected_at           TEXT,
    disconnected_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_time         ON events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type         ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_user         ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_chat_message ON events (chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_payments_stat       ON payments (status);

-- Bir martalik SQLite import markeri (bot o'zi boshqaradi).
CREATE TABLE IF NOT EXISTS supabase_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Bot sozlamalari (kalit-qiymat) + boshlang'ich qiymat:
-- Premium bo'limi YOPIQ boshlanadi (admin panelda yoqiladi).
CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO bot_settings (key, value) VALUES ('premium_enabled', '0')
ON CONFLICT (key) DO NOTHING;
