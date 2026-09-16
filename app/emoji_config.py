"""
Barcha EMOJILAR BITTA JOYDA.

Premium (animatsion) emoji IDlarini shu faylda almashtirsangiz, butun botda
darhol almashadi — handlerlarni ochib o'tirish shart emas.

QANDAY ISHLAYDI:
  * har bir maydon 2 qismdan iborat: ID + fallback (oddiy emoji);
  * ID to'ldirilmagan bo'lsa (""), oddiy emoji ko'rinadi;
  * IDlar Telegram Premium emoji paketlaridan olinadi — bot akkaunti
    Premium/Fragment egasi bo'lsa animatsion ko'rinadi, aks holda Telegram
    o'zi oddiy emoji bilan almashtiradi.

Premium/obuna/admin-panel ekranlariga oid emojilar OLIB TASHLANGAN (yangi
talab) — faqat qolgan ekranlar (menyu, statistika, hisobotlar) uchun
yozuvlar bu yerda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# PREMIUM EMOJI YOQISH KALITI (muhim!)
#
# Telegram FAQAT Fragment'da qo'shimcha username/raqam sotib olgan botlarga
# xabar MATNIDA <tg-emoji> yuborishga ruxsat beradi.  Oddiy botda har qanday
# <tg-emoji> "Bad Request: DOCUMENT_INVALID" xatosini beradi — butun ekran
# ochilmaydi.  Shuning uchun standartda O'CHIQ.
#
# Bot akkountiga Fragment kolleksiyoni olganingizdan keyin True qiling.
# ---------------------------------------------------------------------------
ENABLE_PREMIUM_EMOJI_TAGS = False


def tg_e(emoji_id: str | None, fallback: str) -> str:
    """Premium emoji uchun <tg-emoji> tegi.

    Kalit o'chiq bo'lsa YOKI ID bo'sh bo'lsa — oddiy emoji qaytadi
    (Telegram xato bermasligi uchun)."""
    if not ENABLE_PREMIUM_EMOJI_TAGS or not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


@dataclass(frozen=True)
class EmojiEntry:
    """Bitta emoji: premium ID (bo'sh bo'lsa oddiy fallback ko'rinadi).

    ``emoji_id`` ni to'ldirsangiz: xabar ICHIDA ``<tg-emoji>`` ko'rinishida
    (kalit yoqilgan bo'lsa), tugmalarda esa ``icon_custom_emoji_id`` bo'lib
    chiqadi — kodni boshqa joyda o'zgartirish shart emas.
    """

    emoji_id: str
    fallback: str

    @property
    def tag(self) -> str:
        """HTML xabarlar ICHIDA ishlatiladigan ko'rinish."""
        return tg_e(self.emoji_id, self.fallback)

    @property
    def plain(self) -> str:
        """HTML BO'LMAGAN joylar uchun (alert, caption, tugma matni)."""
        return self.fallback


@dataclass(frozen=True)
class EmojiConfig:
    """Butun botdagi emoji yozuvlari — EKRAN BO'YICHA guruhlangan."""

    # ------------------------------------------------------------------
    # /start ASOSIY MENYU (tugma ikonkalari — `icon_custom_emoji_id`)
    # ------------------------------------------------------------------
    menu_stats: EmojiEntry = field(default_factory=lambda: EmojiEntry("5368324170671202286", "📊"))
    menu_connect: EmojiEntry = field(default_factory=lambda: EmojiEntry("5333163668629442693", "🔗"))
    menu_settings: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⚙️"))
    menu_back: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "🔙"))

    # ------------------------------------------------------------------
    # FOYDALANUVCHI EKRANLARI (xabar matni ichida — <tg-emoji>)
    # ------------------------------------------------------------------
    stats_header: EmojiEntry = field(default_factory=lambda: EmojiEntry("5368324170671202286", "📊"))
    inbox: EmojiEntry = field(default_factory=lambda: EmojiEntry("5472239203590888751", "📥"))
    info: EmojiEntry = field(default_factory=lambda: EmojiEntry("5368324170671202286", "ℹ️"))
    connect_title: EmojiEntry = field(default_factory=lambda: EmojiEntry("5333163668629442693", "🔗"))
    online_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟢"))
    offline_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🔴"))
    paused_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟡"))
    users: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "👥"))

    # ------------------------------------------------------------------
    # HISOBOTLAR (tahrirlandi / o'chirildi)
    # ------------------------------------------------------------------
    report_edit: EmojiEntry = field(default_factory=lambda: EmojiEntry("5395444784611480792", "✏️"))
    report_delete: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445267414562389170", "🗑"))
    report_user: EmojiEntry = field(default_factory=lambda: EmojiEntry("6145672251489391716", "👤"))
    report_id: EmojiEntry = field(default_factory=lambda: EmojiEntry("5837071798935492251", "🆔"))
    report_text: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "📝"))
    report_old: EmojiEntry = field(default_factory=lambda: EmojiEntry("5879841310902324730", "📱"))
    report_new: EmojiEntry = field(default_factory=lambda: EmojiEntry("5467523423989144592", "📲"))
    report_chat: EmojiEntry = field(default_factory=lambda: EmojiEntry("5443038326535759644", "💬"))
    report_clock: EmojiEntry = field(default_factory=lambda: EmojiEntry("5787488119490088755", "🕒"))

    # ------------------------------------------------------------------
    # HOLAT BELGILARI (oddiy emoji — semantik)
    # ------------------------------------------------------------------
    ok: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✅"))

    # ------------------------------------------------------------------
    # KIRISH NAZORATI: ruxsat / rad / ban (app/handlers/admin.py,
    # app/services/access.py, app/keyboards/access_kb.py)
    #
    # Bu yerga premium (animatsion) emoji IDlarini yozing — butun bo'lim
    # (matnlar, tugmalar, ro'yxat belgilari) SHU YERDAN yangilanadi.
    #
    #   access_request  🔔  adminga keladigan «Yangi ruxsat so'rovi» kartasi
    #   access_pending  ⏳  so'rov yuborilgan / tasdiq kutilmoqda
    #   access_denied   🔒  so'rov rad etilgan (foydalanuvchiga)
    #   access_banned   🚫  banlangan (matn + «Ban» tugmasi + ro'yxat belgisi)
    #   access_allowed  ✅  ruxsat berilgan (matn + tugma + ro'yxat belgisi)
    #   access_rejected ❌  «Rad etish» tugmasi / rad etilgan belgisi
    #   access_admin    👑  ro'yxatdagi admin belgisi
    #   page_prev/next  ⬅️ ➡️  ro'yxatni sahifalash
    # ------------------------------------------------------------------
    access_request: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🔔"))
    access_pending: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⏳"))
    access_denied: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🔒"))
    access_banned: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🚫"))
    access_allowed: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✅"))
    access_rejected: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "❌"))
    access_admin: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "👑"))
    page_prev: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⬅️"))
    page_next: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "➡️"))

    # ------------------------------------------------------------------
    # QULAYLIK: qisqa nomlar (texts.py ishlatadigan E_STATS, E_USER, ...)
    # ------------------------------------------------------------------
    @property
    def stats(self) -> str:
        return self.stats_header.tag

    @property
    def user(self) -> str:
        return self.report_user.tag

    @property
    def idcard(self) -> str:
        return self.report_id.tag

    @property
    def link(self) -> str:
        return self.connect_title.tag

    @property
    def edit(self) -> str:
        return self.report_edit.tag

    @property
    def trash(self) -> str:
        return self.report_delete.tag

    @property
    def info_tag(self) -> str:
        return self.info.tag

    @property
    def chat(self) -> str:
        return self.report_chat.tag

    @property
    def clock(self) -> str:
        return self.report_clock.tag


EMOJI = EmojiConfig()
"""Global emoji registry — `from app.emoji_config import EMOJI` qiling."""
