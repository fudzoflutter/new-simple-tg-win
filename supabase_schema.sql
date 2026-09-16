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
--
-- DIQQAT: bot faqat 3 jadval bilan ishlaydi — users, events, connections.
-- Premium / obuna / to'lov / admin-panel jadvallari (plans, payments,
-- bot_settings) OLIB TASHLANGAN.  Bu DDL mavjud jadvallarni O'CHIRMAYDI;
-- eski plans/payments jadvallari qolaversa hech narsaga zarari yo'q.
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    last_name      TEXT,
    connected_at   TEXT,
    last_activity  TEXT,
    created_at     TEXT NOT NULL
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

-- Bir martalik SQLite import markeri (bot o'zi boshqaradi).
CREATE TABLE IF NOT EXISTS supabase_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
