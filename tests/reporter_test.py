"""
Offline unit test for the activity reporter (no Telegram network, no DB).

Run from the project root:

    python tests/reporter_test.py

It plugs a FakeBot + FakeDB into Reporter and checks the STRICT rules:

1. business_message (sent)          -> NO report, only cached (text & media)
2. owner edits own text             -> NO report (cache refreshed)
3. owner edits own media caption    -> NO report (cache refreshed)
4. partner edits text               -> ✏️ report (📱 Default old / 📲 Edited new)
5. partner edits media caption      -> NO report (cache refreshed only)
6. owner deletes own message        -> NO report
7. partner deletes text             -> 🗑 report with the FULL original text
8. partner deletes media            -> cached file RE-SENT
                                       (photo/video/GIF/sticker/voice/circular video)
9. delete of unknown (pre-connect)  -> silently skipped
10. Who shows @username when available, name/mention otherwise
11. connection lookup is cached (1 DB read) and invalidated on a
    business_connection change
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import reporter as rep  # noqa: E402
from app.services.reporter import Reporter, invalidate_connection  # noqa: E402

OWNER_ID = 1000
PARTNER_ID = 2000
OWNER_CHAT = 1000
CHAT_ID = 555


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeMessage:
    """Minimal stand-in for aiogram Message."""

    def __init__(
        self,
        mid: int,
        from_id: int,
        text: Optional[str] = None,
        media: Optional[dict] = None,
        caption: Optional[str] = None,
        first_name: str = "Partner",
        username: Optional[str] = "juratbek",
    ):
        self.message_id = mid
        self.business_connection_id = "conn-1"
        self.chat = SimpleChat(CHAT_ID, first_name=first_name, username=username)
        self.from_user = SimpleUser(from_id, first_name, username)
        self.text = text
        self.caption = caption
        self._media = media or {}

    def __getattr__(self, name: str) -> Any:
        # aiogram messages simply lack absent content attributes.
        if name in {"sticker", "animation", "photo", "video", "voice", "video_note"}:
            return self._media.get(name)
        raise AttributeError(name)


class SimpleChat:
    def __init__(self, cid: int, first_name: str = "", username: Optional[str] = None):
        self.id = cid
        self.type = "private"
        self.title = None
        self.first_name = first_name
        self.username = username


class SimpleUser:
    def __init__(self, uid: int, first_name: str = "", username: Optional[str] = None):
        self.id = uid
        self.first_name = first_name
        self.username = username


class SimpleDeleted:
    def __init__(self, mids: list[int]):
        self.business_connection_id = "conn-1"
        self.chat = SimpleChat(CHAT_ID, first_name="Partner", username="juratbek")
        self.message_ids = mids


class FakeBot:
    """Records every outbound call instead of touching Telegram."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []  # (method, caption/text)

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> None:
        self.sent.append(("message", text))

    async def send_photo(self, chat_id: int, photo: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("photo", caption))

    async def send_video(self, chat_id: int, video: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("video", caption))

    async def send_animation(self, chat_id: int, animation: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("animation", caption))

    async def send_sticker(self, chat_id: int, sticker: str, **kw: Any) -> None:
        self.sent.append(("sticker", ""))

    async def send_voice(self, chat_id: int, voice: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("voice", caption))

    async def send_video_note(self, chat_id: int, video_note: str, **kw: Any) -> None:
        # Dumaloq videoga caption yozib bo'lmaydi — izoh alohida xabar bo'ladi.
        self.sent.append(("video_note", ""))


class FakeDB:
    """In-memory mirror of only the DB calls Reporter makes."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._next_id = 1
        # Ulanish holati (test ichida o'zgartiriladi) + nechta marta
        # o'qilgani — kesh ishlayotganini isbotlash uchun.
        self.connection_calls = 0
        self.connection_enabled = True
        self.connection_user_id = OWNER_ID
        self.connection_chat_id = OWNER_CHAT

    # -- parallel helper + settings (limit disabled by default) -------------
    async def gather(self, *aws: Any) -> list[Any]:
        return list(await asyncio.gather(*aws))

    async def get_setting_cached(self, key: str, default: str = "") -> str:
        return default  # limit:{id} default "0" = unlimited

    async def count_user_events_since(
        self, user_id: int, since: Any, event_types: Optional[list[str]] = None
    ) -> int:
        return 0  # limit check always passes in this test

    # -- connections/users (owner approved, partner known) -----------------
    async def get_connection(self, cid: str) -> Optional[dict]:
        self.connection_calls += 1
        return {
            "user_id": self.connection_user_id,
            "user_chat_id": self.connection_chat_id,
            "is_enabled": self.connection_enabled,
        }

    async def get_user(self, user_id: int) -> Optional[dict]:
        if user_id == OWNER_ID:
            return {"user_id": OWNER_ID, "username": "owner",
                    "first_name": "Owner", "access_status": "approved"}
        if user_id == PARTNER_ID:
            return {"user_id": PARTNER_ID, "username": "juratbek",
                    "first_name": "Juratbek", "access_status": "approved"}
        return None

    # -- events -------------------------------------------------------------
    async def add_event(
        self, user_id: int, event_type: str, details: str,
        chat_id: Optional[int] = None, chat_title: Optional[str] = None,
        message_id: Optional[int] = None, sender_id: Optional[int] = None,
    ) -> None:
        self.events.append({
            "id": self._next_id, "user_id": user_id, "event_type": event_type,
            "details": details, "chat_id": chat_id, "chat_title": chat_title,
            "message_id": message_id, "sender_id": sender_id,
        })
        self._next_id += 1

    async def get_event_by_message(
        self, chat_id: int, message_id: int
    ) -> Optional[dict]:
        for row in reversed(self.events):
            if (
                row["chat_id"] == chat_id
                and row["message_id"] == message_id
            ):
                return row
        return None

    async def update_event_details(
        self, chat_id: int, message_id: int, details: str
    ) -> bool:
        row = await self.get_event_by_message(chat_id, message_id)
        if row:
            row["details"] = details
            return True
        return False


# --------------------------------------------------------------------------
# Test scenarios
# --------------------------------------------------------------------------
async def run_all() -> None:
    # Scenario A: partner sends text, then edits it, then deletes it.
    r = Reporter(FakeBot())
    monkeypatch_db = FakeDB()
    rep.db = monkeypatch_db  # type: ignore[assignment]

    incoming = FakeMessage(11, PARTNER_ID, text="Okay, darling")
    await r.report_incoming(incoming)
    assert r.bot.sent == [], "sent messages must NOT be reported"
    cached = await monkeypatch_db.get_event_by_message(CHAT_ID, 11)
    assert cached and cached["details"] == "Okay, darling", "text must be cached"

    # Partner edits the text.
    edited = FakeMessage(11, PARTNER_ID, text="Okay, darling!")
    await r.report_edited(edited)
    msgs = [t for kind, t in r.bot.sent if kind == "message"]
    assert len(msgs) == 1, f"exactly one edit report expected, got {len(msgs)}"
    report = msgs[0]
    assert "tahrirlandi" in report and "Okay, darling" in report
    assert "📱 Default: Okay, darling" in report
    assert "📲 Edited: Okay, darling!" in report
    assert "@juratbek" in report, "Who must show the username"
    assert "Chat: <b>Partner</b>" in report and "Vaqt: <b>" in report
    row = await monkeypatch_db.get_event_by_message(CHAT_ID, 11)
    assert row["details"] == "Okay, darling!", "cache must hold the latest text"

    # Partner deletes the (edited) message -> report shows the latest text.
    dels = SimpleDeleted([11])
    await r.report_deleted(dels)
    msgs = [t for kind, t in r.bot.sent if kind == "message"]
    assert len(msgs) == 2, "delete report expected"
    assert "o'chirildi" in msgs[1] and "Okay, darling!" in msgs[1]

    # Scenario B: owner's OWN actions must be silent.
    r2 = Reporter(FakeBot())
    own = FakeMessage(21, OWNER_ID, text="my own words")
    await r2.report_incoming(own)
    await r2.report_edited(FakeMessage(21, OWNER_ID, text="my own words!"))
    await r2.report_deleted(SimpleDeleted([21]))
    assert r2.bot.sent == [], "owner's own edits/deletes must not be reported"
    row = await monkeypatch_db.get_event_by_message(CHAT_ID, 21)
    assert row and row["details"] == "my own words!", "owner cache must refresh"

    # Scenario C: partner media -> only a DELETE triggers a report (re-send).
    r3 = Reporter(FakeBot())
    photo = FakeMessage(
        31, PARTNER_ID,
        media={"photo": [SimplePhoto("fid_31")]},
        caption="look at this",
    )
    await r3.report_incoming(photo)
    assert r3.bot.sent == [], "photo send must NOT be reported"
    await r3.report_edited(
        FakeMessage(31, PARTNER_ID, media={"photo": [SimplePhoto("fid_31")]},
                    caption="look at this (edit)")
    )
    assert r3.bot.sent == [], "media caption edit must NOT be reported"
    await r3.report_deleted(SimpleDeleted([31]))
    kinds = [kind for kind, _ in r3.bot.sent]
    assert kinds == ["photo"], f"cached photo must be re-sent, got {kinds}"
    assert "@juratbek" in r3.bot.sent[0][1]
    assert "o'chirildi" in r3.bot.sent[0][1]

    # Video / GIF / sticker / voice / circular video deletions re-send their kind.
    for kind, method in (
        ("video", "video"),
        ("animation", "animation"),
        ("sticker", "sticker"),
        ("voice", "voice"),
        ("video_note", "video_note"),
    ):
        r4 = Reporter(FakeBot())
        media_obj = SimplePhoto(f"fid_{kind}")
        m = FakeMessage(40 + hash(kind) % 7, PARTNER_ID, media={kind: media_obj})
        await r4.report_incoming(m)
        assert r4.bot.sent == [], f"{kind} send must NOT be reported"
        await r4.report_deleted(SimpleDeleted([m.message_id]))
        expected = (
            # sticker/video_note cannot carry a caption -> it goes as its own message
            [method, "message"] if method in {"sticker", "video_note"}
            else [method]
        )
        assert [k for k, _ in r4.bot.sent] == expected, kind

    # Scenario F: voice keeps its caption; the kind label says what was deleted.
    r7 = Reporter(FakeBot())
    await r7.report_incoming(
        FakeMessage(71, PARTNER_ID, media={"voice": SimplePhoto("fid_v")},
                    caption="eslab qol")
    )
    assert r7.bot.sent == [], "voice send must NOT be reported"
    await r7.report_deleted(SimpleDeleted([71]))
    assert [k for k, _ in r7.bot.sent] == ["voice"], r7.bot.sent
    assert "Voice o'chirildi" in r7.bot.sent[0][1]
    assert "eslab qol" in r7.bot.sent[0][1], "voice caption must be preserved"

    r8 = Reporter(FakeBot())
    await r8.report_incoming(
        FakeMessage(72, PARTNER_ID, media={"video_note": SimplePhoto("fid_n")})
    )
    assert r8.bot.sent == [], "circular video send must NOT be reported"
    await r8.report_deleted(SimpleDeleted([72]))
    assert [k for k, _ in r8.bot.sent] == ["video_note", "message"], r8.bot.sent
    assert "Video note o'chirildi" in r8.bot.sent[1][1]

    # Scenario D: uncached (pre-connect) deletes are silent.
    r5 = Reporter(FakeBot())
    await r5.report_deleted(SimpleDeleted([999]))
    assert r5.bot.sent == [], "uncached deletes must be skipped"

    # Scenario E: Who falls back to name/mention when username is missing.
    r6 = Reporter(FakeBot())
    await r6.report_incoming(FakeMessage(61, PARTNER_ID, text="hi",
                                         username=None, first_name="Juratbek"))
    await r6.report_edited(FakeMessage(61, PARTNER_ID, text="hi!",
                                       username=None, first_name="Juratbek"))
    report = [t for kind, t in r6.bot.sent if kind == "message"][0]
    assert "Juratbek" in report, report

    # Scenario G: connection lookup is cached (one DB read per connection) and
    # dropped when the connection changes.
    invalidate_connection()  # butun kesh tozalanadi (toza boshlanish)
    gdb = FakeDB()
    rep.db = gdb  # type: ignore[assignment]

    rg = Reporter(FakeBot())
    for mid in (81, 82, 83):
        await rg.report_incoming(FakeMessage(mid, PARTNER_ID, text=f"m{mid}"))
    assert gdb.connection_calls == 1, (
        f"connection must be read once, got {gdb.connection_calls}"
    )

    # Ulan/uz hodisasi keshni tozalaydi -> keyingi update qayta o'qiydi.
    invalidate_connection("conn-1")
    await Reporter(FakeBot()).report_incoming(
        FakeMessage(84, PARTNER_ID, text="m84")
    )
    assert gdb.connection_calls == 2, (
        "invalidate_connection must force a fresh read"
    )

    # Uzilgan ulanish keshlanmaydi: hisobot yo'q, keyingi update yana o'qiydi.
    gdb.connection_enabled = False
    invalidate_connection("conn-1")
    rb = Reporter(FakeBot())
    await rb.report_incoming(FakeMessage(91, PARTNER_ID, text="after off"))
    assert rb.bot.sent == [], "disabled connection must not report"
    assert gdb.connection_calls == 3

    gdb.connection_enabled = True
    await Reporter(FakeBot()).report_incoming(
        FakeMessage(92, PARTNER_ID, text="back on")
    )
    assert gdb.connection_calls == 4, (
        "a disabled connection must not be cached - next update re-reads it"
    )
    row = await gdb.get_event_by_message(CHAT_ID, 92)
    assert row and row["details"] == "back on", "re-enabled connection caches again"

    print("REPORTER RULES TEST PASSED ✅  "
          "(silent sends, edit/delete-only reports, partner-only, usernames, "
          "connection cache)")


class SimplePhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


if __name__ == "__main__":
    asyncio.run(run_all())
