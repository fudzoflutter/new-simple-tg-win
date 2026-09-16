"""
Minimal Telegram Business activity bot — the whole idea in ONE file.

What it does
  1. Learns a connection when someone adds it as a Business chatbot.
  2. Silently caches every message in the connected chats (text + media).
  3. Reports to the OWNER only when a PARTNER edits or deletes:
       edit          -> old -> new
       delete (text) -> the original text
       delete (media)-> the cached file, re-sent
     The owner's own edits/deletes are never reported.
  4. Cleans tracking params (?utm_*, fbclid, ...) from any link sent to it
     and shows the public user count.

Run:  BOT_TOKEN=123:ABC python minimal_bot.py

The cache is in memory, so it resets on restart — paste in SQLite/Supabase
if you need it to survive. Everything else here matches app/.
"""

from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

TOKEN = os.environ["BOT_TOKEN"]

OWNERS: dict[str, tuple[int, int]] = {}          # connection_id -> (owner, owner_chat)
CACHE: dict[tuple[int, int], list] = {}          # (chat_id, message_id) -> [kind, payload, sender, caption]
SEEN: set[int] = set()                            # /start users, for the public count

# Attribute name == Bot method suffix: send_photo(photo=...), send_voice(voice=...), ...
MEDIA = ("photo", "video", "animation", "voice", "video_note", "sticker")
NO_CAPTION = {"sticker", "video_note"}           # these reject a caption
TRACKING = {"fbclid", "gclid", "dclid", "yclid", "ysclid", "igshid", "igsh", "si", "ref",
            "ref_src", "mc_cid", "mc_eid", "mkt_tok", "ttclid", "msclkid", "twclid",
            "li_fat_id", "s_kwcid", "spm", "scm", "_openstat"}

router = Router()


def media_of(m: Message) -> tuple[str | None, str | None]:
    """(kind, file_id) for any media message, else (None, None)."""
    for kind in MEDIA:
        obj = getattr(m, kind, None)
        if obj:
            return kind, (obj[-1] if kind == "photo" else obj).file_id
    return None, None


def name_of(chat) -> str:
    return f"@{chat.username}" if getattr(chat, "username", None) else (
        getattr(chat, "title", None) or getattr(chat, "first_name", None) or "?"
    )


# --- 1. connection on / off ------------------------------------------------
@router.business_connection()
async def on_connection(c: BusinessConnection, bot: Bot) -> None:
    chat = c.user_chat_id or c.user.id
    if c.is_enabled:
        OWNERS[c.id] = (c.user.id, chat)
        await bot.send_message(chat, "✅ Business ulanish faol.")
    else:
        OWNERS.pop(c.id, None)
        await bot.send_message(chat, "🔴 Business ulanish uzildi.")


# --- 2. cache every message silently (never forwarded) ---------------------
@router.business_message()
async def on_message(m: Message, bot: Bot) -> None:
    if m.business_connection_id not in OWNERS:
        return
    kind, fid = media_of(m)
    payload = fid if kind else (m.text or m.caption or "(no text)")
    sender = m.from_user.id if m.from_user else 0
    CACHE[(m.chat.id, m.message_id)] = [kind or "text", payload, sender, m.caption or ""]


# --- 3a. partner edits TEXT -> old -> new ----------------------------------
@router.edited_business_message()
async def on_edited(m: Message, bot: Bot) -> None:
    conn = OWNERS.get(m.business_connection_id)
    if not conn:
        return
    owner_id, owner_chat = conn
    key = (m.chat.id, m.message_id)
    prev = CACHE.get(key)
    old = prev[1] if prev and prev[0] == "text" else "(older than cache)"
    kind, fid = media_of(m)
    if kind:                                     # media edits are cached silently
        CACHE[key] = [kind, fid, m.from_user.id, m.caption or ""]
        return
    new = m.text or m.caption or "(no text)"
    CACHE[key] = ["text", new, m.from_user.id, ""]
    if m.from_user and m.from_user.id != owner_id:
        await bot.send_message(
            owner_chat,
            f"✏️ Message edited\n\n👤 {name_of(m.from_user)}\n"
            f"📱 Default: {old}\n📲 Edited: {new}\n💬 {name_of(m.chat)}",
        )


# --- 3b. partner deletes -> show text / re-send media -----------------------
@router.deleted_business_messages()
async def on_deleted(d: BusinessMessagesDeleted, bot: Bot) -> None:
    conn = OWNERS.get(d.business_connection_id)
    if not conn:
        return
    owner_id, owner_chat = conn
    who = name_of(d.chat)
    for mid in d.message_ids:
        row = CACHE.pop((d.chat.id, mid), None)
        if not row or row[2] == owner_id:        # uncached, or the owner's own -> silent
            continue
        kind, payload, _sender, caption = row
        if kind == "text":
            await bot.send_message(owner_chat, f"🗑 Xabar o'chirildi\n\n👤 {who}\n📄 {payload}")
            continue
        header = f"🗑 {kind} o'chirildi\n\n👤 {who}" + (f"\n💬 {caption}" if caption else "")
        send = getattr(bot, f"send_{kind}")
        if kind in NO_CAPTION:                    # sticker/video_note: caption as its own message
            await send(owner_chat, **{kind: payload})
            await bot.send_message(owner_chat, header)
        else:
            await send(owner_chat, **{kind: payload}, caption=header)


# --- 4. link cleaner + public user count -----------------------------------
def clean_url(url: str) -> str:
    p = urlsplit(url)
    keep = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(keep), p.fragment))


@router.message(CommandStart())
async def on_start(m: Message) -> None:
    SEEN.add(m.from_user.id)
    await m.answer(
        f"👋 Salom!\n\n<b>Foydalanuvchilar:</b> {len(SEEN)}\n\n"
        "Menga havola yuboring — kuzatuv parametrlarini olib tashlayman.\n"
        "Ulash: Settings → Business → Chatbots.",
        parse_mode="HTML",
    )


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(m: Message) -> None:
    changed = [c for u, c in ((u, clean_url(u)) for u in re.findall(r"https?://\S+", m.text)) if c != u]
    if changed:
        await m.answer("\n".join(changed), disable_web_page_preview=True)


async def main() -> None:
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(Bot(TOKEN))


if __name__ == "__main__":
    asyncio.run(main())
