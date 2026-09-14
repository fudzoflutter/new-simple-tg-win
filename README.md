# 👁 Telegram Activity Monitor Bot

An **aiogram 3** bot that connects to users through *Telegram for Business*
and reports message activity to the bot owner: edits and deletions of their
chat partners' messages (sent messages are cached silently and never
forwarded; photos/videos/GIFs/stickers are re-sent only when deleted).
Includes a full **admin panel** with premium
subscriptions, manual payment confirmation, user management and broadcasts.

---

## ✨ Features

| Spec | Feature |
|------|---------|
| 1 | **Connect** button guides the user into *Telegram Settings → Business → Chatbots* |
| 2 | **Statistics** button + "how it works" explanation + Admin panel (Premium button visible to everyone, panel admin-only) |
| 3 | Instant ✅/❌ notifications to the user when the business connection is established or lost |
| 4 | Reports only for activity that matters: partner message **edits** (old → new) and **deletions** — cached media (photos, videos, GIFs, stickers) is re-sent when deleted. Sent messages are cached silently, never forwarded; the owner's own actions are never reported |
| 5 | Admin panel: subscription plans (duration/price/description), receipt approval, user list with online status + restrict, broadcast with media & premium emoji |

Extras: colored inline buttons (`style=` — Bot API 9.4+), premium emoji icons
(`icon_custom_emoji_id`), copy-on-tap card number, anti-flood, banned-user
guard, SQLite storage.

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

   Without the variable it still validates the full CRUD matrix offline.

> The pooler URI (port 6543) is required — the code disables prepared
> statements for it (`statement_cache_size=0`).  The direct URI (5432)
> also works if you prefer.

### Requirements for full functionality

* **Premium emoji on buttons** — the *bot account* must have Telegram
  Premium or own a Fragment username; otherwise Telegram shows plain text
  (IDs stay in place and render the day you upgrade).
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
├── config.py           # ALL settings (card number, emoji IDs, .env)
├── database.py         # schema + every SQL query (Database class)
├── main.py             # wiring: bot, dispatcher, routers, middlewares
├── states.py           # FSM dialogs (plan wizard, broadcast)
├── filters/__init__.py # IsAdmin filter
├── handlers/
│   ├── user.py         # /start menu, statistics, connect, premium, receipts
│   ├── business.py     # connection notices + activity capture
│   ├── admin_panel.py  # dashboard, users, online, restrict
│   ├── admin_plans.py  # create/edit/delete premium plans
│   ├── admin_payments.py # approve/reject receipts
│   └── admin_broadcast.py # advertisements to all users
├── keyboards/
│   ├── user_kb.py      # user keyboards + callback constants
│   └── admin_kb.py     # admin keyboards + callback constants
├── services/
│   ├── reporter.py     # builds the owner report messages
│   ├── broadcaster.py  # mass-send logic
│   └── watchdog.py     # daily DB housekeeping
└── utils/
    ├── formatting.py   # HTML escaping, mentions, date/number formats
    ├── logger.py       # logging setup
    ├── texts.py        # EVERY user-facing text (edit messages here)
    └── ui.py           # premium emoji IDs + colored button factory
```

---

## 🛠 Customization cheat-sheet

| I want to change… | Go to |
|---|---|
| Bot texts / wording / language | `app/utils/texts.py` |
| Card number, cardholder | `app/config.py` → `payment_*` |
| Premium emoji icons on buttons | `app/utils/ui.py` → `CustomEmoji` (or `.env`) |
| Button colors | `style=` args in `app/keyboards/*.py` (`danger`/`success`/`primary`) |
| "Online" window | `ONLINE_WINDOW_SECONDS` in `app/handlers/admin_panel.py` |
| Broadcast speed | `THROTTLE_SECONDS` in `app/services/broadcaster.py` |
| Report text limits | `MAX_TEXT` in `app/services/reporter.py` |
| Report rules (what gets reported) | `report_incoming` / `report_edited` / `report_deleted` in `app/services/reporter.py` |

---

## 🧭 How the admin panel works

* `/admin` command (owner only) opens the panel.
* **Users** — paginated list 🟢online/⚪️offline; tap a user → profile card
  with *Open profile* link and *Restrict / Unrestrict*.
* **Premium plans** — ➕ Create plan wizard: *title → days → price →
  description*. Tap a plan's name in the list to open its card: **edit**
  any field (title/days/price/description), hide/show, or delete it.
  Plans appear instantly on the user's Premium screen.
* **Payments** — users send receipt screenshots → admin gets them with
  ✅ Approve (activates premium, notifies user) / ❌ Reject buttons.
* **Broadcast** — send any post (text with links, photo, video, sticker,
  premium emoji) → confirm → delivered to all active users with a summary.
