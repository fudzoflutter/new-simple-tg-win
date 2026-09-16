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
12. HAQIQIY aiogram yangiliklari (business_message JSON) — ovozli xabar va
    dumaloq video jim keshlanadi va o'chirilganda AYNAN o'sha file_id bilan
    qayta yuboriladi (foydalanuvchi shikoyati: "ovozli xabar va dumaloq
    video saqlanmayapti / qayta yuborilmayapti").
13. O'CHIRILISH VAQTI — hisobotlarda Toshkent (UTC+5) vaqtida ko'rsatiladi
    (server UTC bo'lsa ham 5 soatga surilmaydi), bir update uchun BIR MARTA
    olinadi va sekin DB/fayl yuklash uni o'zgartirib yubormaydi.
14. TEZ O'CHIRISH (asosiy xato): suhbatdosh xabarni yuborib DARHOL o'chirsa,
    o'chirish yangilamasi DB kesh yozuvidan OLDIN ishlanadi (aiogram
    update'larni parallel bajaradi).  Xotiradagi tezkor kesh tufayli hisobot
    baribir chiqadi — matn ham, ovozli xabar ham, dumaloq video ham.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.types import Update  # noqa: E402

from app.services import reporter as rep  # noqa: E402
from app.services.reporter import (  # noqa: E402
    Reporter,
    clear_instant_cache,
    invalidate_connection,
)

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
        # Qayta yuborilgan fayllar: (method, file_id) — fayl AYNAN o'sha
        # keshlangan file_id bilan ketganini isbotlash uchun.
        self.files: list[tuple[str, str]] = []
        self.fail_media = False  # True -> media yuborish xato beradi (fallback)

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> None:
        self.sent.append(("message", text))

    async def send_photo(self, chat_id: int, photo: str, caption: str = "", **kw: Any) -> None:
        if self.fail_media:
            raise RuntimeError("media yuborilmadi (test)")
        self.sent.append(("photo", caption))
        self.files.append(("photo", photo))

    async def send_video(self, chat_id: int, video: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("video", caption))
        self.files.append(("video", video))

    async def send_animation(self, chat_id: int, animation: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("animation", caption))
        self.files.append(("animation", animation))

    async def send_sticker(self, chat_id: int, sticker: str, **kw: Any) -> None:
        self.sent.append(("sticker", ""))
        self.files.append(("sticker", sticker))

    async def send_voice(self, chat_id: int, voice: str, caption: str = "", **kw: Any) -> None:
        self.sent.append(("voice", caption))
        self.files.append(("voice", voice))

    async def send_video_note(self, chat_id: int, video_note: str, **kw: Any) -> None:
        # Dumaloq videoga caption yozib bo'lmaydi — izoh alohida xabar bo'ladi.
        self.sent.append(("video_note", ""))
        self.files.append(("video_note", video_note))


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

    # Scenario D: uncached (pre-connect) deletes produce NO report — lekin jim
    # ham qolmaydi: nega hisobot yo'qligini aytadigan BITTA diagnostika
    # xabari boradi (15 daqiqa oralig'ida takrorlanmaydi).
    #
    # Sabab: bu nusxa xabarni umuman ko'rmagan — demak uni boshqa nusxa
    # (eski build / server) qabul qilgan yoki xabar bot ishga tushishidan
    # oldin yuborilgan.  Aynan shu holat "ovoz/dumaloq video qaytmadi"
    # shikoyatining sababi bo'lgani uchun endi ko'rinadi.
    rep._last_uncached_warning = 0.0
    r5 = Reporter(FakeBot())
    await r5.report_deleted(SimpleDeleted([999]))
    assert [k for k, _ in r5.bot.sent] == ["message"], r5.bot.sent
    diag = r5.bot.sent[0][1]
    assert "topilmadi" in diag and "999" in diag, diag
    assert "🗑" not in diag, f"bu hisobot EMAS, diagnostika: {diag}"

    # Takroriy ogohlantirish bo'lmaydi (shovqin qilmaslik uchun).
    await r5.report_deleted(SimpleDeleted([998]))
    assert len(r5.bot.sent) == 1, r5.bot.sent

    # Interval o'tgach yana bir marta aytiladi.
    rep._last_uncached_warning -= rep.UNCACHED_WARNING_INTERVAL + 1
    await r5.report_deleted(SimpleDeleted([997]))
    assert len(r5.bot.sent) == 2, r5.bot.sent
    assert "997" in r5.bot.sent[1][1]

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

    # Scenario H: HAQIQIY aiogram yangiliklari (JSON -> Update -> Message).
    # Bu qism aynan foydalanuvchi shikoyatini tekshiradi: "ovozli xabar va
    # dumaloq video saqlanmayapti va qayta yuborilmayapti".  Yo'q — ikkalasi
    # ham jim keshlanadi, o'chirilganda esa fayl AYNAN o'sha file_id bilan
    # qayta yuboriladi.
    def media_update(mid: int, kind: str, fid: str) -> dict:
        media = {"file_id": fid, "file_unique_id": f"u{mid}", "duration": 5,
                 "file_size": 1000}
        if kind == "video_note":
            media["length"] = 240
        return {
            "update_id": mid,
            "business_message": {
                "message_id": mid,
                "date": 1_760_000_000,
                "business_connection_id": "conn-1",
                "chat": {"id": CHAT_ID, "type": "private",
                         "first_name": "Partner", "username": "juratbek"},
                "from": {"id": PARTNER_ID, "is_bot": False,
                         "first_name": "Juratbek", "username": "juratbek"},
                kind: media,
            },
        }

    def delete_update(mid: int) -> dict:
        return {
            "update_id": 9000 + mid,
            "deleted_business_messages": {
                "business_connection_id": "conn-1",
                "chat": {"id": CHAT_ID, "type": "private",
                         "first_name": "Partner", "username": "juratbek"},
                "message_ids": [mid],
            },
        }

    hdb = FakeDB()
    rep.db = hdb  # type: ignore[assignment]
    invalidate_connection()
    rh = Reporter(FakeBot())

    for mid, kind, fid in ((501, "voice", "VOICE_FILE_ID"),
                           (502, "video_note", "NOTE_FILE_ID")):
        rh.bot.sent.clear()
        rh.bot.files.clear()

        incoming = Update.model_validate(media_update(mid, kind, fid)).business_message
        assert incoming is not None and getattr(incoming, kind) is not None, kind
        await rh.report_incoming(incoming)
        assert rh.bot.sent == [], f"{kind}: yuborish hisobot qilinmasligi kerak"

        row = await hdb.get_event_by_message(CHAT_ID, mid)
        assert row and row["event_type"] == kind, (kind, row)
        assert fid in row["details"], (kind, row)

        deleted = Update.model_validate(delete_update(mid)).deleted_business_messages
        assert deleted is not None
        await rh.report_deleted(deleted)
        assert [m for m, _ in rh.bot.files] == [kind], (kind, rh.bot.files)
        assert rh.bot.files[0][1] == fid, (
            f"{kind}: keshlangan file_id qayta yuborilishi kerak"
        )
        assert rh.bot.sent, f"{kind}: sarlavha (izoh) yuborilishi kerak"
        assert "o'chirildi" in " ".join(t for _, t in rh.bot.sent)

    # Voice izohi (caption) ham saqlanadi va qayta yuboriladi.
    rh.bot.sent.clear()
    rh.bot.files.clear()
    with_caption = media_update(503, "voice", "VOICE_FID_2")
    with_caption["business_message"]["caption"] = "eslab qol"
    await rh.report_incoming(
        Update.model_validate(with_caption).business_message
    )
    await rh.report_deleted(
        Update.model_validate(delete_update(503)).deleted_business_messages
    )
    assert rh.bot.files == [("voice", "VOICE_FID_2")], rh.bot.files
    assert "eslab qol" in rh.bot.sent[0][1], rh.bot.sent

    # Scenario I: O'CHIRILISH VAQTI — aniq va Toshkent (UTC+5) vaqtida.
    #
    # Foydalanuvchi shikoyati: "bot o'chirilgan media uchun noto'g'ri vaqt
    # ko'rsatyapti".  Sabab: vaqt `datetime.now()` (mashina/server soati)
    # bilan olinardi — Docker/Railway konteynerida bu UTC, ya'ni Toshkentdan
    # 5 soat ORQADA.  Endi vaqt Toshkent mintaqasida va update kelgan ZAHOTI
    # (DB so'rovlaridan oldin) bir marta olinadi.
    idb = FakeDB()
    rep.db = idb  # type: ignore[assignment]
    invalidate_connection()
    ri = Reporter(FakeBot())

    real_now = rep.now_report
    # "Soat" har chaqiriqda boshqa vaqt qaytaradi: hisobot BIRINCHI (eng
    # erta) qiymatni ishlatishi kerak, kechroq olinganini emas.
    stamps = [
        datetime(2026, 9, 16, 12, 34, 56, tzinfo=timezone.utc),  # -> 17:34:56
        datetime(2026, 9, 16, 15, 0, 0, tzinfo=timezone.utc),   # -> 20:00:00
        datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc),   # -> 23:00:00
    ]
    clock = {"calls": 0}

    def fake_now() -> datetime:
        value = stamps[min(clock["calls"], len(stamps) - 1)]
        clock["calls"] += 1
        return value

    rep.now_report = fake_now  # type: ignore[assignment]
    try:
        # (a) MATN o'chirilishi
        clock["calls"] = 0
        await ri.report_incoming(FakeMessage(601, PARTNER_ID, text="o'chiriladi"))
        await ri.report_deleted(SimpleDeleted([601]))
        text_report = [t for k, t in ri.bot.sent if k == "message"][0]
        assert "🕒 O'chirilgan: <b>17:34:56</b>" in text_report, text_report
        assert clock["calls"] == 1, (
            f"vaqt bir marta olinishi kerak, {clock['calls']} marta olingan"
        )

        # (b) MEDIA o'chirilishi (izohdagi vaqt ham AYNI)
        ri.bot.sent.clear()
        clock["calls"] = 0
        await ri.report_incoming(
            FakeMessage(602, PARTNER_ID, media={"voice": SimplePhoto("V1")})
        )
        await ri.report_deleted(SimpleDeleted([602]))
        caption = ri.bot.sent[0][1]
        assert "🕒 O'chirilgan: <b>17:34:56</b>" in caption, caption
        assert "20:00:00" not in caption and "23:00:00" not in caption, caption
        assert clock["calls"] == 1, clock["calls"]

        # (c) Media qayta yuborilmasa — matnli zaxira hisobot ham SHU vaqtni
        #     ko'rsatadi (fallback yo'lida ham vaqt yo'qolmaydi).
        fallback_bot = FakeBot()
        fallback_bot.fail_media = True
        rf = Reporter(fallback_bot)
        clock["calls"] = 0
        await rf.report_incoming(
            FakeMessage(603, PARTNER_ID, media={"photo": [SimplePhoto("P1")]})
        )
        await rf.report_deleted(SimpleDeleted([603]))
        body = [t for k, t in rf.bot.sent if k == "message"][0]
        assert "🕒 O'chirilgan: <b>17:34:56</b>" in body, body

        # (d) Bir yangilamada bir nechta xabar — hammasi AYNI vaqtni ko'rsatadi.
        ri.bot.sent.clear()
        clock["calls"] = 0
        await ri.report_incoming(FakeMessage(604, PARTNER_ID, text="bir"))
        await ri.report_incoming(FakeMessage(605, PARTNER_ID, text="ikki"))
        await ri.report_deleted(SimpleDeleted([604, 605]))
        times = [t for k, t in ri.bot.sent if k == "message"]
        assert len(times) == 2, times
        assert all("🕒 O'chirilgan: <b>17:34:56</b>" in t for t in times), times
        assert clock["calls"] == 1, clock["calls"]

        # (e) TAHRIRLASH hisoboti ham shu mintaqada (UTC+5).
        ri.bot.sent.clear()
        clock["calls"] = 0
        await ri.report_incoming(FakeMessage(606, PARTNER_ID, text="eski"))
        await ri.report_edited(FakeMessage(606, PARTNER_ID, text="yangi"))
        edit = [t for k, t in ri.bot.sent if k == "message"][0]
        assert "🕒 Vaqt: <b>17:34:56</b>" in edit, edit
    finally:
        rep.now_report = real_now  # type: ignore[assignment]

    # (f) Mashina soat mintaqasidan MUSTAQIL: UTC + 5 soat (Toshkentda DST yo'q).
    from app.utils.timeutils import REPORT_UTC_OFFSET_HOURS, TZ_REPORT, hms

    assert REPORT_UTC_OFFSET_HOURS == 5, REPORT_UTC_OFFSET_HOURS
    assert str(TZ_REPORT) == "UTC+05:00", TZ_REPORT
    assert hms(datetime(2026, 9, 16, 12, 34, 56)) == "17:34:56", "naive = UTC"
    assert hms(datetime(2026, 9, 16, 7, 4, 56, tzinfo=timezone.utc)) == "12:04:56"
    # Devor soati (wall clock) farqi: UTC + 5.  Diqqat: ikkala vaqt bir xil
    # oniy paytni bildiradi (astimezone), shuning uchun tzinfo'siz qiymatlar
    # taqqoslanadi.
    uz_clock = rep.now_report().replace(tzinfo=None)
    utc_clock = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (uz_clock - utc_clock).total_seconds()
    assert abs(delta - 5 * 3600) < 5, delta

    print("Scenario I (o'chirilish vaqti — Toshkent UTC+5, bir marta) OK ✅")

    # Scenario J: TEZ O'CHIRISH — kesh yozuvi hali bazaga tushmagan bo'lsa ham
    # hisobot chiqadi.  Bu HAQIQIY xato edi: aiogram update'larni parallel
    # bajaradi, Supabase yozuvi esa ~1.2 s — suhbatdosh xabarni darhol
    # o'chirsa, o'chirish yangilamasi "keshda yo'q" deb JIM o'tib ketardi
    # (aynan foydalanuvchi shikoyati: matn keladi, ovoz/dumaloq video kelmaydi).
    class SlowFakeDB(FakeDB):
        """add_event sekin (Supabase ~1.2 s ni simulyatsiya qiladi)."""

        async def add_event(self, *args: Any, **kwargs: Any) -> None:
            await asyncio.sleep(0.05)
            await super().add_event(*args, **kwargs)

    def cached_rows(slow_db: "SlowFakeDB", mid: int) -> list[dict]:
        return [e for e in slow_db.events if e["message_id"] == mid]

    slow = SlowFakeDB()
    rep.db = slow  # type: ignore[assignment]
    invalidate_connection()
    clear_instant_cache()
    rj = Reporter(FakeBot())

    async def start_incoming(mid: int, kw: dict) -> asyncio.Task:
        """Xabar handler'i ISHGA TUSHADI (xotiraga yozadi), DB yozuvi esa
        davom etmoqda.  Real hayotda ham shunday: xabar va o'chirish — alohida
        update'lar (alohida long-poll javoblari), shuning uchun handler har
        doim birinchi bo'lib ishga tushadi; xotiradagi yozuv esa handler'ning
        eng birinchi (await'siz) qadamidir.
        """
        kw = {"from_id": PARTNER_ID, **kw}
        task = asyncio.create_task(rj.report_incoming(FakeMessage(mid, **kw)))
        await asyncio.sleep(0)      # task boshlandi: xotira yozildi
        assert rep.recall(CHAT_ID, mid) is not None, "tezkor kesh darhol to'lishi kerak"
        return task

    # (a) OVOZLI XABAR: qayta yuborish tugashidan OLDIN o'chiriladi.
    sending = await start_incoming(801, {"media": {"voice": SimplePhoto("FAST_VOICE")}})
    assert cached_rows(slow, 801) == [], "DB yozuvi hali tugamagan bo'lishi kerak"
    await rj.report_deleted(SimpleDeleted([801]))
    assert rj.bot.files == [("voice", "FAST_VOICE")], (
        f"tez o'chirilgan ovoz qayta yuborilishi kerak, {rj.bot.files}"
    )
    # Hisobot aynan DB yozuvi YO'Q paytda chiqdi (yuqoridagi tekshiruv +
    # qayta yuborilgan fayl).  Orqa fondagi yozuv esa yo'qolmaydi.
    await sending
    assert cached_rows(slow, 801), "yozuv baribir bazaga tushadi (statistika)"

    # (b) DUMALOQ VIDEO — xuddi shunday.
    rj.bot.sent.clear()
    rj.bot.files.clear()
    sending = await start_incoming(802, {"media": {"video_note": SimplePhoto("FAST_NOTE")}})
    await rj.report_deleted(SimpleDeleted([802]))
    assert rj.bot.files == [("video_note", "FAST_NOTE")], rj.bot.files
    assert any("Video note o'chirildi" in t for k, t in rj.bot.sent if k == "message")
    await sending

    # (c) MATN — asl matn baribir ko'rsatiladi.
    rj.bot.sent.clear()
    sending = await start_incoming(803, {"text": "tez o'chdi"})
    await rj.report_deleted(SimpleDeleted([803]))
    # Matn HTML-escape qilinadi (o' -> &#x27;), shuning uchun bo'lak bo'yicha.
    assert any(
        "Asl matn" in t and "tez o" in t and "chdi" in t
        for k, t in rj.bot.sent
        if k == "message"
    ), rj.bot.sent
    await sending

    # (d) Egasining o'z xabari tez o'chirilsa ham JIM qoladi (talab).
    rj.bot.sent.clear()
    sending = await start_incoming(804, {"text": "o'zim yozdim", "from_id": OWNER_ID})
    await rj.report_deleted(SimpleDeleted([804]))
    assert rj.bot.sent == [], "ega o'z xabarini o'chirsa hisobot BO'LMASLIGI kerak"
    await sending

    # (e) Umuman keshda bo'lmagan xabar (aloqadan oldin yuborilgan) JIM o'tadi.
    rj.bot.sent.clear()
    await rj.report_deleted(SimpleDeleted([9999]))
    assert rj.bot.sent == [], "noma'lum xabar haqida hisobot bo'lmasligi kerak"

    clear_instant_cache()
    print("Scenario J (tez o'chirish — kesh poygasi) OK ✅")

    print("REPORTER RULES TEST PASSED ✅  "
          "(silent sends, edit/delete-only reports, partner-only, usernames, "
          "connection cache)")


class SimplePhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


if __name__ == "__main__":
    asyncio.run(run_all())
