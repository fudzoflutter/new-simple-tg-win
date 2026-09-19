"""
Barcha foydalanuvchiga ko'rinadigan matnlar BITTA faylda (o'zbek tilida).

Har qanday xabar / tugma yozuvini shu yerda o'zgartirsangiz, butun botda
o'zgaradi — handler fayllarini ochib o'tirishga hojat yo'q.  HTML teglardan
foydalanish mumkin (parse mode – HTML).

Premium emoji: xabar ICHIDA animatsion (custom) emoji chiqarish uchun
`tg_e(id, fallback)` ishlatilgan.  Bot akkauntida Premium bo'lmasa, xabar
oddiy emoji bilan qayta yuboriladi.

Premium / obuna matnlari OLIB TASHLANGAN (yangi talab); kirish nazorati
matnlari (ruxsat so'rash / rad etish / ban) fayl oxirida.
"""

from __future__ import annotations

from app.emoji_config import EMOJI

# ---------------------------------------------------------------------------
# Xabarlar ICHIDAGI premium (custom) emoji – HAMMASI app/emoji_config.py da.
# IDlarni O'SHA FAYLDA almashtiring — bu yerda faqat qisqa nomlar.
# ---------------------------------------------------------------------------
E_STATS = EMOJI.stats
E_USER = EMOJI.user
E_ID = EMOJI.idcard
E_LINK = EMOJI.link
E_EDIT = EMOJI.edit
E_TRASH = EMOJI.trash
E_INFO = EMOJI.info_tag
E_CHAT = EMOJI.chat
E_CLOCK = EMOJI.clock
E_MISSED = EMOJI.missed

# ---------------------------------------------------------------------------
# /start – asosiy menyu
# ---------------------------------------------------------------------------
WELCOME = (
    f"👋 <b>Assalomu alaykum! </b>\n\n"
    "Men sizning shaxsiy faoliyat-nazorat botingizman.\n"
    "Meni Telegram akkauntingizga ulang — suhbatdoshingiz yuborgan xabarlar "
    "tahrirlanganda yoki o'chirilganda darhol xabar beraman (matn, stiker, "
    "rasm, video, GIF, ovozli xabar va dumaloq video).\n\n"
    "Shuningdek, istalgan havolani tozalab beraman va botdan nechta odam "
    "foydalanayotganini ko'rsataman."
)

MENU_HINT = "Quyidagi amallardan birini tanlang 👇"

# /start bosilganda, foydalanuvchi ALLAQACHON ulangan bo'lsa.
ALREADY_CONNECTED = (
    f"{EMOJI.online_dot.tag} <b>Siz allaqachon ulangansiz!</b>\n\n"
    "Bot akkauntingizga muvaffaqiyatli ulangan — kuzatuv ishlamoqda.\n"
    "Uzish uchun <i>Telegram Business → Chatbotlar</i> bo'limidan meni o'chirishingiz mumkin."
)

# ---------------------------------------------------------------------------
# "Ulanish"
# ---------------------------------------------------------------------------
CONNECT_TITLE = (
    f"{EMOJI.connect_title.tag} <b>Botni ulash</b>\n\n"
    "Quyidagi bosqichlarni bajaring (~30 soniya):\n\n"
    "1️⃣ «⚙️ Sozlamalarni ochish» tugmasini bosing\n"
    "2️⃣ <b>Telegram Business</b> bo'limini oching\n"
    "3️⃣ <b>Chatbotlar</b> bandida\n"
    "4️⃣ <b>Bot qo'shish</b>ni tanlab, <b>@{bot_username}</b> ni tanlang\n\n"
    f"{EMOJI.ok.tag} Tayyor! Meni ulashingiz bilan shu yerga tasdiq xabari keladi — "
    "aloqa uzilsa ham darhol xabar beraman."
)

# ---------------------------------------------------------------------------
# "Statistika" — premium emoji bilan bezatilgan
# ---------------------------------------------------------------------------
STATS_TITLE = f"{E_STATS} <b>Sizning statistikangiz</b>\n\n{{body}}"

STATS_BODY = (
    f"{E_USER} Profil: {{mention}}\n"
    f"{E_ID} ID: <code>{{user_id}}</code>\n\n"
    f"{E_LINK} Ulanish: {{connection_line}}\n\n"
    f"{EMOJI.users.tag} Bot foydalanuvchilari: <b>{{users}}</b>\n"
    f"{EMOJI.inbox.tag} Yozib olingan xabarlar: <b>{{total}}</b>\n"
    f"{E_EDIT} Tahrirlar: <b>{{edits}}</b>\n"
    f"{E_TRASH} O'chirishlar: <b>{{deletes}}</b>"
)

CONNECTED_LINE = "🟢 ulangan"
NOT_CONNECTED_LINE = "⚪️ ulanmagan"

# ---------------------------------------------------------------------------
# Foydalanuvchilar soni — HAMMA uchun (admin panel shart emas)
# ---------------------------------------------------------------------------
USERS_COUNT = (
    f"{EMOJI.users.tag} <b>Foydalanuvchilar</b>\n\n"
    "Hozirda botdan jami <b>{total}</b> ta foydalanuvchi foydalanmoqda.\n"
    f"{EMOJI.online_dot.tag} Oxirgi 2 daqiqada faol: <b>{{online}}</b>"
)



# ---------------------------------------------------------------------------
# Ulanish haqidagi xabarlar
# ---------------------------------------------------------------------------
BUSINESS_CONNECTED = (
    f"{EMOJI.online_dot.tag} <b>Ulanish amalga oshdi!</b>\n\n"
    "Endi men sizning Telegram akkauntingizga ulanganman.\n\n"
    "Xabar faoliyatingiz (tahrirlash, o'chirish, stiker, rasm, video) endi "
    "shaxsiy hisobotlar bilan SHU chatga keladi — barcha ma'lumotlar faqat "
    "sizning botingizda, alohida saqlanadi.\n\n"
    "Xohlagan vaqtda <i>Telegram Business → Chatbotlar</i> bo'limidan "
    "uzishingiz mumkin."
)

BUSINESS_DISCONNECTED = (
    f"{EMOJI.offline_dot.tag} <b>Ulanish uzildi!</b>\n\n"
    "Akkauntingiz bilan bog'lanish faol emas, kuzatuv to'xtadi.\n"
    "Qayta ulash uchun <i>Telegram Business → Chatbotlar</i> bo'limidan "
    "meni qayta ulang."
)

BUSINESS_ENABLED_AGAIN = (
    f"{EMOJI.online_dot.tag} <b>Ulanish tiklandi!</b>\n\n"
    "Kuzatuv yana ishlayapti."
)

BUSINESS_DISABLED = (
    f"{EMOJI.paused_dot.tag} <b>Ulanish to'xtatildi.</b>\n\n"
    "Bot akkauntingizga nisbatan huquqlarini yo'qotdi. Bu sizning "
    "xohishingiz bo'lmasa, chatbot sozlamalarini tekshiring."
)

# ---------------------------------------------------------------------------
# Hisobotlar.
#
#   * Yuborilgan xabarlar FORVARD qilinmaydi — ular jim keshlanadi.
#   * Matn xabari  -> faqat TAHRIRLANDI yoki O'CHIRILDI deb xabar qilinadi.
#   * Media        -> faqat O'CHIRILDI deb xabar qilinadi (fayl qayta
#     yuboriladi).
#   * Hisobot faqat SUHBATDOSH hodisalari uchun: eganing o'z
#     tahrirlash/o'chirishlari hech qachon xabar qilib berilmaydi.
#
# Format services/reporter.py da yig'iladi, ushbu shablonlar shu yerda.
# ---------------------------------------------------------------------------
REPORT_EDIT = (
    f"{E_EDIT} <b>Xabar tahrirlandi</b>\n\n"
    f"{E_USER} Kim: {{who}}\n"
    f"{EMOJI.report_old.tag} Default: {{old}}\n"
    f"{EMOJI.report_new.tag} Edited: {{new}}"
)

REPORT_DELETED_MEDIA = (
    f"{E_TRASH} <b>{{kind}} o'chirildi</b>\n\n"
    f"{E_USER} Kim: {{who}}\n"
    f"{E_ID} Xabar: <code>{{mid}}</code>"
)

# Matn xabari o'chirilganda — ASL MATN bilan.
REPORT_DELETED_TEXT = (
    f"{E_TRASH} <b>Xabar o'chirildi</b>\n\n"
    f"{E_USER} Kim: {{who}}\n"
    f"{EMOJI.report_text.tag} Asl matn: {{original}}"
)

# Media o'chirilganda SAQLANGAN MEDIA QAYTA YUBORILADI — bu sarlavha media
# bilan birga boradi (reporter._resend_media).
REPORT_DELETED_MEDIA_CAPTION = (
    f"{E_TRASH} <b>{{kind}} o'chirildi</b>\n\n"
    f"{E_USER} Kim: {{who}}"
)

# Hisobot oxiridagi qatorlar.
#   REPORT_FOOTER         — tahrirlash hisoboti uchun (vaqt = tahrirlangan payt)
#   REPORT_FOOTER_DELETED — o'chirish hisoboti uchun (vaqt = O'CHIRILGAN payt)
# Ikkala vaqt ham Toshkent (UTC+5) mintaqasida ko'rsatiladi — hisob
# app/utils/timeutils.py da (REPORT_UTC_OFFSET_HOURS).
REPORT_FOOTER = f"\n{E_CHAT} Chat: <b>{{chat}}</b>\n{E_CLOCK} Vaqt: <b>{{time}}</b>"
REPORT_FOOTER_DELETED = (
    f"\n{E_CHAT} Chat: <b>{{chat}}</b>\n{E_CLOCK} O'chirilgan: <b>{{time}}</b>"
)

# Diagnostika: hisobot shabloni yig'ilib bo'ldi, lekin uni YUBORIB bo'lmadi.
# Sabab Telegramdan keladi (masalan "VOICE_MESSAGES_FORBIDDEN") va jim
# yutilmaydi — aks holda "ovozli xabar qaytmadi" ning sababi ko'rinmasdi.
REPORT_RESEND_FILE_FORM = (
    f"\n{E_MISSED} <i>Asl ko'rinishda yuborilmadi ({{reason}}) — "
    f"fayl sifatida yuborildi.</i>"
)
REPORT_RESEND_FAILED = (
    f"\n{E_MISSED} <i>Faylni ham yuborib bo'lmadi: {{reason}}</i>"
)

# Sabab qabul qiluvchining O'Z Telegram sozlamasi bo'lganda (ovozli xabar /
# dumaloq video bloklangan) — qaysi sozlamani ochish kerakligi aytiladi.
# Bir soatda ko'pi bilan bir marta qo'shiladi (reporter._voice_hint_due).
REPORT_VOICE_SETTING_HINT = (
    f"\n{E_INFO} <i>Telegram sozlamasi: Sozlamalar → Maxfiylik va xavfsizlik "
    f"→ Ovozli xabarlar → «Hamma».  Shundan keyin ovozli xabar va dumaloq "
    f"video ASL ko'rinishida keladi.\n"
    f"Yuborilgan fayl ichida AYNAN o'sha ovoz (OGG/OPUS) — istalgan "
    f"pleyerda ochiladi.</i>"
)

# Diagnostika: o'chirish keldi, lekin xabar keshda YO'Q — hisobot chiqmaydi.
# Sabab ikkitadan biri: (a) xabarni BOSHQA nusxa (eski build / server deploy)
# qabul qilgan, (b) xabar bot ishga tushishidan oldin yuborilgan.
# Jim qolish o'rniga admin bir marta ogohlantiriladi (reporter._warn_uncached).
REPORT_UNCACHED = (
    f"{E_MISSED} <b>O'chirilgan xabar keshda topilmadi</b>\n\n"
    f"{E_CHAT} Chat: <b>{{chat}}</b>\n"
    f"{E_ID} Xabarlar: <code>{{ids}}</code> — {{count}} ta\n"
    f"{E_CLOCK} O'chirilgan: <b>{{time}}</b>\n\n"
    f"<i>Bot bu xabarni umuman ko'rmagan, shuning uchun hisobot yo'q.\n"
    f"Sabab: xabar boshqa nusxa tomonidan qabul qilingan (eski build) yoki "
    f"bot ishga tushishidan oldin yuborilgan.</i>"
)

# Matn bo'sh yoki juda uzun bo'lganda.
NO_TEXT = "<i>(matn yo'q)</i>"
TRUNCATED = "…"

# "Kim"ni aniqlab bo'lmaganda (suhbatdosh haqida ma'lumot yo'q).
WHO_UNKNOWN = "Noma'lum"
# Chat nomi mavjud bo'lmaganda.
UNKNOWN_CHAT = "Noma'lum chat"

# ---------------------------------------------------------------------------
# Turli
# ---------------------------------------------------------------------------
DUPLICATE_POLLER = (
    f"{EMOJI.paused_dot.tag} <b>Boshqa nusxa ham polling qilmoqda ({{count}} ta)</b>\n\n"
    "Update'lar ikki nusxa orasida bo'linib ketmoqda — ba'zi hisobotlar "
    "kelmayaapti.\n\n"
    "Nima qilish kerak:\n"
    "1. Yuqoridagi nusxani to'xtating (o'sha terminalda Ctrl+C yoki\n"
    "   taskkill //PID <PID> //F)\n"
    "2. Yoki ikkalasidan birini o'chirib qo'yib, yangi nusxani\n"
    "   ishga tushiring (faqat BITTA nusxa polling qilishi shart)."
)

UNKNOWN_ACTION = "🤔 Noma'lum amal — quyidagi menyudan foydalaning."
ERROR_USER = "😔 Xatolik yuz berdi. Keyinroq qayta urinib ko'ring."

# ---------------------------------------------------------------------------
# Kirish nazorati: ruxsat so'rash / rad etish / ban (app/services/access.py)
#
# EMOJILAR app/emoji_config.py dan olinadi ("KIRISH NAZORATI" bo'limi) —
# premium IDlarni FAQAT o'sha faylda almashtirasiz, bu yerda tegmasangiz
# ham bo'ladi.
# ---------------------------------------------------------------------------
E_ACCESS_REQUEST = EMOJI.access_request.tag
E_ACCESS_PENDING = EMOJI.access_pending.tag
E_ACCESS_DENIED = EMOJI.access_denied.tag
E_ACCESS_BANNED = EMOJI.access_banned.tag
E_ACCESS_ALLOWED = EMOJI.access_allowed.tag
E_ACCESS_REJECTED = EMOJI.access_rejected.tag

# Foydalanuvchi ruxsat so'rab murojaat qilganda.
ACCESS_PENDING = (
    f"{E_ACCESS_PENDING} <b>So'rovingiz yuborildi.</b>\n\n"
    "Admin tasdiqlashini kuting — ruxsat berilishi bilan shu yerga xabar "
    "keladi."
)

# So'rov rad etilganda.
ACCESS_DENIED = (
    f"{E_ACCESS_DENIED} <b>Ruxsat berilmagan.</b>\n\n"
    "Sizga bu botdan foydalanish uchun ruxsat berilmagan. Xatolik deb "
    "hisoblasangiz, admin bilan bog'laning."
)

# Banlanganda.
ACCESS_BANNED = (
    f"{E_ACCESS_BANNED} <b>Siz bloklangansiz.</b>\n\n"
    "Bu botdan foydalanish huquqingiz to'xtatilgan."
)

# -- ADMINGA (karta) --------------------------------------------------------
ACCESS_REQUEST_ADMIN = (
    f"{E_ACCESS_REQUEST} <b>Yangi ruxsat so'rovi</b>\n\n"
    f"{E_USER} Kim: {{who}}\n"
    f"{E_ID} ID: <code>{{user_id}}</code>\n"
    f"{E_LINK} Username: {{username}}\n\n"
    "Quyidagi tugmalar orqali ruxsat bering yoki rad eting."
)

# Qaror qabul qilingach karta TEPASIGA qo'shiladi (tugmalar olib tashlanadi).
ACCESS_REQUEST_ALLOWED = f"{E_ACCESS_ALLOWED} <b>Ruxsat berildi</b>"
ACCESS_REQUEST_DENIED = f"{E_ACCESS_REJECTED} <b>Rad etildi</b>"

# -- FOYDALANUVCHIGA (qaror haqida) -----------------------------------------
USER_APPROVED = (
    f"{E_ACCESS_ALLOWED} <b>Sizga ruxsat berildi!</b>\n\n"
    "Endi botdan to'liq foydalanishingiz mumkin."
)
USER_DENIED = (
    f"{E_ACCESS_REJECTED} <b>So'rovingiz rad etildi.</b>\n\n"
    "Botdan foydalanishga ruxsat berilmadi."
)
USER_BANNED = (
    f"{E_ACCESS_BANNED} <b>Siz botdan bloklandingiz.</b>\n\n"
    "Foydalanish huquqingiz admin tomonidan to'xtatildi."
)
USER_UNBANNED = (
    f"{E_ACCESS_ALLOWED} <b>Blokingiz olindi.</b>\n\n"
    "Botdan yana foydalanishingiz mumkin."
)

# -- ADMIN PANELI: foydalanuvchilar ro'yxati --------------------------------
USERS_PANEL_TITLE = (
    f"{EMOJI.users.tag} <b>Foydalanuvchilar boshqaruvi</b>\n\n"
    f"Jami: <b>{{total}}</b> · {EMOJI.online_dot.tag} Faol (2 daq): <b>{{online}}</b>\n\n"
    "{body}\n\n"
    "<i>{legend}</i>"
)
USERS_PANEL_LEGEND = (
    f"{E_ACCESS_ALLOWED} ruxsat · {E_ACCESS_PENDING} kutilyapti · {E_ACCESS_BANNED} ban"
)
USERS_PANEL_EMPTY = "<i>Hozircha foydalanuvchilar yo'q.</i>"
USERS_PANEL_LINE = "{badge} {mention} — <code>{user_id}</code>"
USERS_PANEL_PAGE = "Sahifa {page}/{pages}"

# ---------------------------------------------------------------------------
# IKKI NUSXA (409 Conflict) — faqat adminga (app/services/duplicate_watch.py)
#
# Aiogram 409 xatosini o'zi yutib qo'yadi, shu sababli bot "ishlayapti"
# ko'rinadi-yu, update'larning bir qismini boshqa nusxa olib ketadi.
# ---------------------------------------------------------------------------
DUPLICATE_POLLER = (
    "⚠️ <b>DIQQAT: botni IKKI nusxa poll qilmoqda</b>\n\n"
    "Telegram bitta token uchun faqat BITTA nusxaga xabar beradi, shuning "
    "uchun ikkinchi nusxa bilan navbatma-navbat to'qnashyapmiz "
    "(<code>409 Conflict</code>). Natijada update'lar ikki nusxa orasida "
    "bo'linib ketadi: bot ba'zi xabarlarni ko'radi, ba'zilarini ko'rmaydi "
    "va ba'zi hisobotlar umuman kelmaydi.\n\n"
    "Nima qilish kerak:\n"
    "1. Boshqa kompyuter / terminal / VS Code oynasidagi "
    "<code>python run.py</code> ni to'xtating.\n"
    "2. Serverga (Railway / Render / VPS) deploy qilingan nusxa bo'lsa — "
    "uni ham to'xtating yoki eng oxirgi kod bilan yangilang.\n"
    "3. Botni faqat BITTA joyda ishga tushiring.\n\n"
    "Aniqlangan <code>409</code> xatolari: <b>{count}</b>\n"
    "<i>Bu ogohlantirish 30 daqiqada bir martadan ko'p kelmaydi.</i>"
)
