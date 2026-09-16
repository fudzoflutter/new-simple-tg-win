# 👁 Telegram Activity Monitor Bot

An **aiogram 3** bot that connects to users through *Telegram for Business*
and reports message activity to the bot owner: edits and deletions of their
chat partners' messages (sent messages are cached silently and never
forwarded; photos / videos / GIFs / stickers / voice messages / circular
videos are re-sent only when deleted).

The bot is intentionally **lean**: it also **cleans links** (strips tracking
parameters) for anyone and shows **how many people use the bot**. The owner
keeps control through two inline-button screens — **allow / deny** approval
requests and **ban / unban** — while premium and subscriptions stay out of
the codebase.

---

## ✨ Features

| # | Feature |
|---|---------|
| 1 | **Connect** button guides the user into *Telegram Settings → Business → Chatbots* |
| 2 | **Statistics** button — your own numbers only (messages cached, edits, deletions, users), no long explanations |
| 3 | Instant ✅/❌ notifications to the user when the business connection is established or lost |
| 4 | Reports only for activity that matters: partner message **edits** (old → new) and **deletions** — cached media (photos, videos, GIFs, stickers, **voice messages, circular videos**) is re-sent when deleted. Sent messages are cached silently, never forwarded; the owner's own actions are never reported |
| 5 | **Link cleaner** — send any link and get it back without tracking params (`utm_*`, `fbclid`, `gclid`, …). Works for everyone, no admin panel |
| 6 | **User count** — anyone can see how many people use the bot (+ how many were active in the last 2 minutes) |
| 7 | **Access control** — a stranger who writes to the bot triggers an approval card in the owner's chat (**✅ Ruxsat berish / ❌ Rad etish**); the *Foydalanuvchilar* screen lists everyone with a **🚫 Ban** / **✅ Ruxsat berish** / **✅ Blokdan chiqarish** button (all four icons live in the emoji registry). The decision applies instantly — the check is a pure in-memory lookup, adding **no** database round-trip to any update |

Extras: colored inline buttons (`style=` — Bot API 9.4+), premium emoji icons
(`icon_custom_emoji_id`), anti-flood, a synchronous access cache (no I/O on
the hot path), Supabase storage with a local SQLite fallback.

---

## 🚀 Setup

```bash
# 1. Python 3.11+ required
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Dependencies
pip install -r requirements.txt

# 3. Configuration
cp .env.example .env             # Windows: copy .env.example .env
#   -> put your BOT_TOKEN (from @BotFather) and your ADMIN_ID (from @userinfobot)

# 4. Run
python run.py
```

> A second key file, `env.txt`, is also read (and wins over `.env`).  Either
> works; keep your real keys out of version control (both are gitignored).

### 🐘 Switching to Supabase (cloud database)

The bot runs fine on local SQLite, but with a free [Supabase](https://supabase.com)
project your data lives in the cloud (and survives machine reinstalls):

1. Supabase Dashboard → your project → green **Connect** button →
   **Connection pooling** → copy the URI
   (`postgresql://postgres.xxxx:PASSWORD@aws-0-region.pooler.supabase.com:6543/postgres`).
2. Uncomment `SUPABASE_DB_URL=` in `.env` and paste it.
3. Restart the bot. Tables are created automatically and the existing
   `bot.db` rows are **imported once** (tracked in `supabase_migrations`).
4. Verify before/after switching with the integration suite:

   ```bash
   SUPABASE_DB_URL="postgresql://..." python tests/supabase_test.py
   ```

> The pooler URI (port 6543) is required — the code disables prepared
> statements for it (`statement_cache_size=0`).  The direct URI (5432)
> also works if you prefer.

### Requirements for full functionality

* **Premium emoji** — every icon lives in `app/emoji_config.py`.  Button
  icons (`icon_custom_emoji_id`) are carried as IDs and animate as soon as
  the *bot account* has Telegram Premium or a Fragment username; until then
  Telegram shows the plain fallback emoji.
* **Premium emoji inside message text** needs one extra switch:
  `ENABLE_PREMIUM_EMOJI_TAGS = True` in `app/emoji_config.py`.  It is off by
  default because Telegram rejects `<tg-emoji>` from a non-Premium bot
  (`DOCUMENT_INVALID`), which would stop the whole screen from rendering;
  with the switch off the same texts render with plain emoji.
* **Business updates** — the connecting user needs a Telegram Business
  account (free features are enough to add a chatbot).
* In **@BotFather → /mybots → Bot Settings → Group/Business Privacy** make
  sure business access is allowed.

---

## 🗂 Project structure

```
bot.db                  # SQLite database (auto-created, fallback storage)
run.py                  # launcher: python run.py
logs/bot.log            # rotating runtime log (auto-created, 2 MB x 3 files)
app/
├── config.py           # ALL settings (.env / env.txt)
├── database.py         # schema + every SQL query (Database facade + Postgres)
├── storage_sqlite.py   # SQLite backend (offline fallback, identical API)
├── main.py             # wiring: bot, dispatcher, routers, middleware
├── middlewares.py      # registration + activity + anti-flood
├── handlers/
│   ├── user.py         # /start menu, statistics, connect, link cleaning
│   ├── admin.py        # allow / deny / ban / unban screens (owner only)
│   └── business.py     # connection notices + activity capture
├── keyboards/
│   ├── user_kb.py      # user keyboards + callback constants
│   └── access_kb.py    # approval card + ban/unban panel buttons
├── services/
│   ├── access.py       # in-memory access cache (sync check, no I/O hot path)
│   ├── reporter.py     # builds the owner report messages
│   ├── instance_lock.py# DB lock: only ONE copy may poll Telegram at a time
│   ├── duplicate_watch.py # turns silent 409 conflicts into an owner alert
│   ├── linkcleaner.py  # strips tracking params from links
│   └── watchdog.py     # daily DB housekeeping
└── utils/
    ├── formatting.py   # HTML escaping, mentions, date/number formats
    ├── logger.py       # logging setup
    ├── texts.py        # EVERY user-facing text (edit messages here)
    └── ui.py           # colored button factory
```

The bot only uses **five tables**: `users`, `events` (the message cache that
lets deleted content be re-sent), `connections`, `access` (who may use the bot
— read into memory once at startup) and `instance_lock` (which copy of the bot
is polling Telegram right now).

---

## 🛠 Customization cheat-sheet

| I want to change… | Go to |
|---|---|
| Bot texts / wording / language | `app/utils/texts.py` |
| Premium emoji icons (menus, reports, **access control**) | `app/emoji_config.py` — single registry, grouped per screen; paste an emoji ID and both the message text and button icons update |
| Button colors | `style=` args in `app/keyboards/*.py` (`danger`/`success`/`primary`) |
| "Online" window | `ONLINE_WINDOW_SECONDS` / `window_seconds` in `app/handlers/user.py` |
| Who may use the bot (approval vs open) | `TEST_MODE` in `env.txt` / `.env` (`1` = approve each new user, `0` = open, banning still works) |
| Running two copies at once / 409 errors | `FORCE_POLL=1` in `env.txt` (disables the single-instance lock — see below) |
| Access texts (request / deny / ban) | the `ACCESS_*` block at the end of `app/utils/texts.py` |
| Access rules (statuses, caching) | `app/services/access.py` |
| Link cleaning rules | `TRACKING_EXACT` / `TRACKING_PREFIXES` in `app/services/linkcleaner.py` |
| Report times (timezone) | `REPORT_UTC_OFFSET_HOURS` in `app/utils/timeutils.py` (default `5` = Tashkent; report times never follow the server clock, so a UTC container still shows local time) |
| Report text limits | `MAX_TEXT` in `app/services/reporter.py` |
| Report rules (what gets reported) | `report_incoming` / `report_edited` / `report_deleted` in `app/services/reporter.py` |

---

## 🧭 How it works

* **Business connection** — `/start` shows the menu; the **Connect** button
  walks the user through *Telegram Business → Chatbots*. The bot is notified
  the moment the connection is created or lost.
* **Reports** — while connected, every incoming business message is cached
  silently. The owner is only notified when a **partner** edits or deletes:
  * edit → `✏️ Xabar tahrirlandi` with 📱 Default (old) → 📲 Edited (new);
  * delete (text) → the full original text;
  * delete (media) → the cached file is re-sent (photo / video / GIF /
    sticker / voice / circular video).
  The user's own edits/deletes are never reported.
* **Link cleaner** — any message containing a link gets the tracking
  parameters stripped; the cleaned link is returned (only when something was
  actually removed, so plain chat text is ignored).
* **User count** — the **Foydalanuvchilar** button shows the total number of
  users and how many were active recently. For the **owner** the same screen
  becomes a management panel: every user gets a 🚫 **Ban** / ✅ **Unban**
  button, and messages from a banned or not-yet-approved user never reach a
  handler (they get ⏳ *please wait* / 🔒 *no access* / 🚫 *banned*).
* **Access control** — with `TEST_MODE=1` a stranger's first message is not
  refused flatly: the bot sends the owner an approval card (**✅ Ruxsat
  berish / ❌ Rad etish**) and remembers the answer. The card is sent **once**
  per user, so a spammer cannot flood the owner's chat. With `TEST_MODE=0`
  everyone is welcome and banning still works.

### ⚠️ Only ONE copy may run at a time (409)

Telegram delivers updates of one bot token to **one** `getUpdates` connection
at a time. If a second copy is polling (an old terminal window, VS Code, or a
server deployment of the same token), the two copies **take turns**: aiogram
hides the `409 Conflict` inside its retry loop, so the bot *looks* healthy
while a random share of the updates goes to the other copy. The visible symptom
is exactly *"the bot sees some messages and not others"* — and, if that other
copy runs older code, the newest content types (voice / circular video) are
silently skipped there.

Two layers now prevent that:

* **Single-instance lock** (`app/services/instance_lock.py`) — every copy
  writes a heartbeat into `instance_lock`; if another copy is alive (heartbeat
  younger than 60 s), the new copy does **not** start polling and prints the
  other copy's host / PID / start time with clear instructions. A hard-killed
  process frees the lock by itself once its heartbeat goes stale. `FORCE_POLL=1`
  disables the check.
* **409 watcher** (`app/services/duplicate_watch.py`) — a copy running *older*
  code cannot see the lock, so `aiogram.dispatcher` is monitored instead: three
  `409` errors within a minute send the owner a Telegram alert (at most once
  per 10 minutes) telling exactly where to look. A silent, half-working bot is
  no longer possible.

### Performance

The connection used to be re-read from the database on **every** business
update (~200 ms each on a remote Supabase). It is now cached in memory
(`_connection_cache` in `app/services/reporter.py`), so an incoming message
costs a **single** DB write. The cache is dropped whenever Telegram sends a
`business_connection` change (connect / disconnect / permission change), so
even a reconnect takes effect on the very next update; a 5-minute TTL is a
safety net in case an event is ever missed. Disconnected or unknown
connections are never cached.

The access check is just as cheap: every user's status lives in an in-memory
dictionary (`app/services/access.py`) loaded in a single query at startup, so
deciding whether an update may proceed costs one dictionary lookup — no
`await`, no query. Rows are touched only when the owner taps a button or a
new user asks for access (and even then the cache is updated first, so the
tap never waits for Supabase).
