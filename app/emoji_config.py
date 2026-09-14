"""
Barcha EMOJILAR BITTA JOYDA (yangi talab).

Premium (animatsion) emoji IDlarini shu faylda almashtirsangiz, butun botda
darhol almashadi — handlerlarni ochib o'tirish shart emas.

QANDAY ISHLAYDI:
  * har bir maydon 2 qismdan iborat: ID + fallback (oddiy emoji);
  * ID to'ldirilmagan bo'lsa (\"\"), oddiy emoji ko'rinadi;
  * IDlar Telegram Premium emoji paketlaridan olinadi — bot akkaunti
    Premium/Fragment egasi bo'lsa animatsion ko'rinadi, aks holda Telegram
    o'zi oddiy emoji bilan almashtiradi.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def tg_e(emoji_id: str | None, fallback: str) -> str:
    """Premium emoji uchun <tg-emoji> tegi (ID bo'sh bo'lsa — oddiy emoji)."""
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


@dataclass(frozen=True)
class EmojiEntry:
    """Bitta emoji: premium ID (bo'sh bo'lsa oddiy fallback ko'rinadi)."""

    emoji_id: str
    fallback: str

    @property
    def tag(self) -> str:
        """HTML xabarlar ICHIDA ishlatiladigan ko'rinish.

        ID to'ldirilgan bo'lsa — <tg-emoji> (premium animatsion),
        bo'sh bo'lsa — oddiy fallback emoji.
        """
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
    menu_premium: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "💎"))
    menu_my_sub: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "💎"))
    menu_settings: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⚙️"))
    menu_back: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "🔙"))

    # ------------------------------------------------------------------
    # FOYDALANUVCHI EKRANLARI (xabar matni ichida — <tg-emoji>)
    # ------------------------------------------------------------------
    stats_header: EmojiEntry = field(default_factory=lambda: EmojiEntry("5368324170671202286", "📊"))
    inbox: EmojiEntry = field(default_factory=lambda: EmojiEntry("5472239203590888751", "📥"))
    info: EmojiEntry = field(default_factory=lambda: EmojiEntry("5368324170671202286", "ℹ️"))
    premium_title: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "💎"))
    money: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "💰"))
    card: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "💳"))
    receipt_ok: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✅"))
    warn: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⚠️"))
    connect_title: EmojiEntry = field(default_factory=lambda: EmojiEntry("5333163668629442693", "🔗"))
    online_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟢"))
    offline_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🔴"))
    paused_dot: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟡"))

    # ------------------------------------------------------------------
    # HISOBOTLAR (tahrirlandi / o'chirildi — 4-band)
    # ------------------------------------------------------------------
    report_edit: EmojiEntry = field(default_factory=lambda: EmojiEntry("5395444784611480792", "✏️"))
    report_delete: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445267414562389170", "🗑"))
    report_user: EmojiEntry = field(default_factory=lambda: EmojiEntry("6145672251489391716", "👤"))
    report_id: EmojiEntry = field(default_factory=lambda: EmojiEntry("5837071798935492251", "🆔"))
    report_text: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "📝"))
    report_old: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "📱"))
    report_new: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "📲"))
    report_caption: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "💬"))
    report_chat: EmojiEntry = field(default_factory=lambda: EmojiEntry("5443038326535759644", "💬"))
    report_clock: EmojiEntry = field(default_factory=lambda: EmojiEntry("5787488119490088755", "🕒"))

    # ------------------------------------------------------------------
    # ADMIN PANEL (sarlavha + ko'rsatkichlar)
    # ------------------------------------------------------------------
    admin_panel: EmojiEntry = field(default_factory=lambda: EmojiEntry("5455669926782445014", "🛡"))
    admin_users: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "👥"))
    admin_online: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟢"))
    admin_premium: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "💎"))
    admin_premium_state: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "👁"))
    admin_connected: EmojiEntry = field(default_factory=lambda: EmojiEntry("5333163668629442693", "🔗"))
    admin_banned: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⛔️"))

    # ADMIN PANEL TUGMALARI (`icon_custom_emoji_id`)
    btn_users: EmojiEntry = field(default_factory=lambda: EmojiEntry("5455669926782445014", "👥"))
    btn_online: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🟢"))
    btn_plans: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "🗓"))
    btn_payments: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "💳"))
    btn_broadcast: EmojiEntry = field(default_factory=lambda: EmojiEntry("5455669926782445014", "📣"))
    btn_premium_toggle: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "💎"))
    btn_back: EmojiEntry = field(default_factory=lambda: EmojiEntry("5445585590822480435", "🔙"))

    # ADMIN: TARIFLAR / KARTOCHKA / OMMVIY XABAR TUGMALARI
    btn_plan_add: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "➕"))
    btn_plan_edit: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✏️"))
    btn_plan_toggle: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "👁"))
    btn_plan_delete: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🗑"))
    btn_profile: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🔗"))
    btn_grant: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🎁"))
    btn_prem_off: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🗑"))
    btn_ban: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "⛔️"))
    btn_unban: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✅"))
    btn_cancel: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "❌"))
    btn_send_all: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🚀"))
    btn_nav_prev: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "◀️"))
    btn_nav_next: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "▶️"))

    # ------------------------------------------------------------------
    # BANLASH / HOLAT BELGILARI (oddiy emoji — semantik, o'zgartirmang)
    # ------------------------------------------------------------------
    ban: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "🚫"))
    ok: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "✅"))
    fail: EmojiEntry = field(default_factory=lambda: EmojiEntry("", "❌"))

    # ------------------------------------------------------------------
    # QULAYLIK: eski nomlar bilan moslik (app/utils/texts.py va
    # keyboards ishlatgan E_STATS, E_USER, CustomEmoji.STATS va h.k.)
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
    def gem(self) -> str:
        return self.premium_title.tag

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
