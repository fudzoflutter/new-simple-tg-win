"""
Barcha foydalanuvchiga ko'rinadigan matnlar BITTA faylda (o'zbek tilida).

Har qanday xabar / tugma yozuvini shu yerda o'zgartirsangiz, butun botda
o'zgaradi — handler fayllarini ochib o'tirishga hojat yo'q.  HTML teglardan
foydalanish mumkin (parse mode – HTML).

Premium emoji: xabar ICHIDA animatsion (custom) emoji chiqarish uchun
`tg_e(id, fallback)` ishlatilgan.  Bot akkauntida Premium bo'lmasa, xabar
oddiy emoji bilan qayta yuboriladi (app/handlers/user.py dagi fallback).
"""

from __future__ import annotations

from app.emoji_config import EMOJI
from app.utils.formatting import esc, fmt_number

# ---------------------------------------------------------------------------
# Xabarlar ICHIDAGI premium (custom) emoji – HAMMASI app/emoji_config.py da.
# IDlarni O'SHA FAYLDA almashtiring — bu yerda faqat qisqa nomlar.
# ---------------------------------------------------------------------------
E_STATS = EMOJI.stats
E_USER = EMOJI.user
E_ID = EMOJI.idcard
E_LINK = EMOJI.link
E_GEM = EMOJI.gem
E_EDIT = EMOJI.edit
E_TRASH = EMOJI.trash
E_INFO = EMOJI.info_tag
E_CHAT = EMOJI.chat
E_CLOCK = EMOJI.clock

# ---------------------------------------------------------------------------
# /start – asosiy menyu (1–2-bandlar)
# ---------------------------------------------------------------------------
WELCOME = (
    f"👋 <b>Assalomu alaykum! </b>\n\n"
    "Men sizning shaxsiy faoliyat-nazorat botingizman.\n"
    "Meni Telegram akkauntingizga ulang — sizga yuborib,tahrirlagan va "
    "o'chirgan xabarlaringizni, stiker, rasm va videolarni ham kuzatib boraman."
)

MENU_HINT = "Quyidagi amallardan birini tanlang 👇"

# /start bosilganda, foydalanuvchi banlangan bo'lsa.
BANNED = f"{EMOJI.ban.fallback} <b>Kirish cheklangan.</b>\nSizga bu botdan foydalanish taqiqlangan."

# /start bosilganda, foydalanuvchi ALLAQACHON ulangan bo'lsa (2-band, yangi talab).
ALREADY_CONNECTED = (
    f"{EMOJI.online_dot.tag} <b>Siz allaqachon ulangansiz!</b>\n\n"
    "Bot akkauntingizga muvaffaqiyatli ulangan — kuzatuv ishlamoqda.\n"
    "Uzish uchun <i>Telegram Business → Chatbotlar</i> bo'limidan meni o'chirishingiz mumkin."
)

# Callback (alert) uchun — HTML ishlamaydi, oddiy matn.
BAN_CALLBACK = f"{EMOJI.ban.fallback} Kirish cheklangan."

# ---------------------------------------------------------------------------
# "Ulanish" (1-band)
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
# "Statistika" (2-band) — premium emoji bilan bezatilgan
# ---------------------------------------------------------------------------
STATS_TITLE = f"{E_STATS} <b>Sizning statistikangiz</b>\n\n{{body}}"

STATS_BODY = (
    f"{E_USER} Profil: {{mention}}\n"
    f"{E_ID} ID: <code>{{user_id}}</code>\n\n"
    f"{E_LINK} Ulanish: {{connection_line}}\n"
    f"{E_GEM} Premium: {{premium_line}}\n\n"
    f"{EMOJI.inbox.tag} Yozib olingan xabarlar: <b>{{total}}</b>\n"
    f"{E_EDIT} Tahrirlar: <b>{{edits}}</b>\n"
    f"{E_TRASH} O'chirishlar: <b>{{deletes}}</b>"
)

PREMIUM_ACTIVE = "✅ faol, <b>{date}</b> gacha"
PREMIUM_INACTIVE = "❌ faol emas"

# -- "Mening obunam" (4-band, yangi talab) -------------------------------------
MY_SUB_TITLE = f"{E_GEM} <b>Mening obunam</b>\n\n{{body}}"
MY_SUB_ACTIVE = (
    f"{E_GEM} Holati: ✅ <b>faol</b>\n"
    f"{E_ID} Tugaydi: <b>{{date}}</b>\n"
    f"🕒 Qolgan vaqt: <b>{{left}}</b>"
)
MY_SUB_INACTIVE = (
    f"{E_GEM} Holati: ❌ <b>faol emas</b>\n\n"
    "Obuna olish uchun Premium bo'limiga kiring."
)

# Admin foydalanuvchiga OBUNA berganda / olganda (yangi talab).
PREMIUM_GRANTED_USER = (
    "🎁 <b>Sovg'a!</b>\n\n"
    "💎 Premium obunangiz admin tomonidan faollashtirildi.\n"
    "<b>{date}</b> gacha faol."
)

# KUNLIK CHEKLOV haqidagi foydalanuvchi xabarlari (premium funksiya).
LIMIT_REACHED_USER = (
    "⏳ <b>Kunlik cheklovga yetdingiz.</b>\n\n"
    "Bugun allaqachon <b>{limit}</b> ta xabar nusxalandi. Cheklov ertaga "
    "yangilanadi.\n💎 Premium bilan cheklov YO'Q — barcha xabarlar "
    "nusxalanadi."
)
LIMIT_SET_USER = (
    "⏳ <b>Yangi cheklov</b>: kuniga <b>{limit}</b> ta xabar.\n"
    "💎 Premium bu cheklovni olib tashlaydi."
)
LIMIT_REMOVED_USER = (
    "⏳ Kunlik cheklov olib tashlandi — endi barcha xabarlar nusxalanadi."
)
PREMIUM_EXTENDED_USER = (
    "💎 <b>Premium uzaytirildi!</b>\n\n"
    "Endi obunangiz <b>{date}</b> gacha faol."
)
PREMIUM_REMOVED_USER = (
    "💎 <b>Premium obuna o'chirildi.</b>\n\n"
    "Savollar bo'lsa, admin bilan bog'laning."
)

CONNECTED_LINE = "🟢 ulangan"
NOT_CONNECTED_LINE = "⚪️ ulanmagan"

# ---------------------------------------------------------------------------
# Bot qanday ishlaydi (2-band — Statistika ostidagi izoh)
# MUHIM: hisobotlar faqat o'zining botiga keladi (shaxsiylik, yangi talab).
# ---------------------------------------------------------------------------
HOW_IT_WORKS = (
    f"{E_INFO} <b>Bot qanday ishlaydi?</b>\n\n"
    "1. Meni <i>Telegram Business → Chatbotlar</i> orqali ulaysiz.\n"
    "2. Shundan so'ng chatlaringizdagi har bir xabarni jim qayd etaman — "
    "yuborilgan xabarlar SIZGA forvard qilinmaydi.\n"
    "3. Suhbatdoshingiz xabarni <b>tahrirlaganida</b> yoki <b>o'chirganida</b> "
    "aynan nima o'zgargani haqida xabar keladi. Rasm, video, GIF va "
    "stikerlar esa faqat <b>o'chirilganda</b> qayta yuboriladi.\n"
    "4. Har bir foydalanuvchining ma'lumotlari alohida va faqat uning "
    "o'ziga ko'rinadi. Hech qanday ma'lumot uchinchi shaxslarga berilmaydi."
)

# ---------------------------------------------------------------------------
# Premium (5-band — foydalanuvchi tomoni)
# ---------------------------------------------------------------------------
PREMIUM_TITLE = (
    "💎 <b>Premium</b>\n\n"
    "Cheksiz imkoniyatlar.\n"
    "Kerakli tarifni tanlang 👇"
)

PREMIUM_NO_PLANS = (
    "💎 <b>Premium</b>\n\n"
    "Hozircha tariflar mavjud emas — keyinroq qayta tekshiring."
)

PREMIUM_ALREADY = "💎 Premiumingiz allaqachon faol, <b>{date}</b> gacha."

# Tarif tugmasi bosilgandagi to'lov oynasi (5-band namunasi).
PREMIUM_CHECKOUT = (
    "💎💎 <b>{title}</b>\n\n"
    "💰 Narxi: <b>{price}</b>\n"
    "💳 Karta raqami: <code>{card}</code>  <i>(nusxalash uchun bosing)</i>\n"
    "👤 Karta egasi: <b>{holder}</b>\n\n"
    "{description}\n\n"
    "To'lovdan so'ng to'lov cheki (skrinshot)ni shu chatga yuboring. "
    "Admin tasdiqlagach, tarif faollashadi. ✅"
)

RECEIPT_RECEIVED = (
    "✅ <b>Chek qabul qilindi!</b>\n\n"
    "Admin tez orada to'lovingizni ko'rib chiqadi.\n"
    "Premium faollashishi bilanoq shu yerga xabar olasiz."
)

RECEIPT_NOT_PHOTO = "⚠️ Iltimos, to'lov chekining <b>rasmini</b> yuboring (foto yoki picture)."

# Chek yuborilganda tarif topilmasa (o'chirilgan yoki FSM yo'qolgan).
RECEIPT_NO_PLAN = (
    "⚠️ Bu tarif endi mavjud emas. "
    "Iltimos, <b>Premium</b> bo'limiga qaytib boshqa tarifni tanlang."
)

PREMIUM_APPROVED_USER = (
    "✅ <b>To'lov tasdiqlandi!</b>\n\n"
    "💎 Premium endi <b>{date}</b> gacha faol.\n"
    "Cheksiz imkoniyatlardan bahramand bo'ling!"
)

PREMIUM_REJECTED_USER = (
    "❌ <b>To'lov rad etildi.</b>\n\n"
    "Chekingiz qabul qilinmadi. Admin bilan bog'laning yoki qaytadan urinib ko'ring."
)

# ---------------------------------------------------------------------------
# Ulanish haqidagi xabarlar (3-band)
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
# Hisobotlar (4-band — YANGI talab).
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

# Rasm/video/GIF/stiker o'chirilganda — SAQLANGAN MEDIA QAYTA YUBORILADI,
# bu sarlavha media bilan birga boradi (reporter._resend_media).
REPORT_DELETED_MEDIA_CAPTION = (
    f"{E_TRASH} <b>{{kind}} o'chirildi</b>\n\n"
    f"{E_USER} Kim: {{who}}"
)

REPORT_FOOTER = f"\n{E_CHAT} Chat: <b>{{chat}}</b>\n{E_CLOCK} Vaqt: <b>{{time}}</b>"

# Matn bo'sh yoki juda uzun bo'lganda.
NO_TEXT = "<i>(matn yo'q)</i>"
TRUNCATED = "…"

# "Kim"ni aniqlab bo'lmaganda (suhbatdosh haqida ma'lumot yo'q).
WHO_UNKNOWN = "Noma'lum"
# Chat nomi mavjud bo'lmaganda.
UNKNOWN_CHAT = "Noma'lum chat"

# ---------------------------------------------------------------------------
# Admin panel (5-band)
# ---------------------------------------------------------------------------
ADMIN_TITLE = (
    f"{EMOJI.admin_panel.tag} <b>Admin panel</b>\n\n"
    f"{EMOJI.admin_users.tag} Foydalanuvchilar: <b>{{users}}</b>\n"
    f"{EMOJI.admin_online.tag} Hozir onlayn: <b>{{online}}</b>\n"
    f"{EMOJI.admin_premium.tag} Premium: <b>{{premium}}</b>\n"
    f"{EMOJI.admin_premium_state.tag} Premium bo'limi: {{premium_state}}\n"
    f"{EMOJI.admin_connected.tag} Ulangan: <b>{{connected}}</b>\n"
    f"{EMOJI.admin_banned.tag} Banlangan: <b>{{banned}}</b>"
)

ADMIN_DENIED = "🛡 Bu bo'lim faqat admin uchun."

# -- Premium bo'limini yoqish/o'chirish (yangi talab) ------------------------
# Premium tugmasi standartda YASHIRIN.  Admin panelda bitta tugma orqali
# hammaga ko'rinadigan qilinadi.
PREMIUM_STATE_ON = "✅ yoqil (hamma ko'radi)"
PREMIUM_STATE_OFF = "❌ o'chiq (yashirin)"
PREMIUM_HIDDEN_USER = "💎 Premium bo'limi hozircha o'chirilgan."
ADMIN_PREMIUM_ON = "💎 Premium bo'limi YOQILDI — endi hammaga ko'rinadi."
ADMIN_PREMIUM_OFF = "💎 Premium bo'limi O'CHIRILDI — menyudan yashirindi."

# -- foydalanuvchilar --------------------------------------------------------
ADMIN_USERS_TITLE = (
    "👥 <b>Foydalanuvchilar</b> ({page}/{pages}-sahifa)\n\n"
    "Foydalanuvchini bosing — uning kartochkasi ochiladi."
)

ADMIN_USER_EMPTY = "👥 Hozircha foydalanuvchilar yo'q."

# Ro'yxatdagi bitta qator oxirida turgan ban belgisi (ADMIN_USER_CARD dan alohida,
# chunki ro'yxat qatorlari _user_line tomonidan yig'iladi).
USER_LINE_BAN_MARK = " ⛔️"

# Onlayn ro'yxatdagi banlangan foydalanuvchi qatori uchun holat so'zi.
STATUS_ONLINE_BANNED = "⛔️ (banlangan)"

# Yuborilgan matn NUSXASI (kesh) — ko'rish uchun ekrani.
ADMIN_LAST_TEXT = (
    "\n\n💬 <b>Oxirgi nusxalangan xabar:</b>\n<i>{text}</i>"
)

ADMIN_USER_NOT_FOUND = "⚠️ Foydalanuvchi topilmadi."

ADMIN_USER_CARD = (
    "{E_USER} <b>{name}</b>\n\n"
    "{E_ID} ID: <code>{user_id}</code>\n"
    "🔗 Username: {username}\n"
    "💎 Premium: {premium}\n"
    "🟢 Oxirgi faollik: {last_seen}\n"
    "📅 Ro'yxatdan o'tgan: {registered}\n"
    "📊 Yozib olingan hodisalar: {events}\n"
    "🔗 Ulanishlar: {connections}\n\n"
    "Holati: {status}"
)

STATUS_ACTIVE = "🟢 faol"
STATUS_BANNED = "⛔️ banlangan"

ADMIN_USER_BANNED_DONE = "🚫 {name} <b>banlandi</b>."
ADMIN_USER_UNBANNED_DONE = "✅ {name} bandan chiqarildi."
ADMIN_CANNOT_BAN_OWNER = "⚠️ Egani banlash mumkin emas."

ADMIN_ONLINE_TITLE = "🟢 <b>Oxirgi 2 daqiqada onlayn</b>\n\n{list}"
ADMIN_ONLINE_EMPTY = "Hozircha hech kim botdan foydalanmayapti."

# -- tariflar ------------------------------------------------------------------
ADMIN_PLANS_TITLE = (
    "🗓 <b>Premium tariflar</b>\n\n"
    "{list}"
    "\nQuyidagi tugmalar orqali boshqaring."
)

ADMIN_PLANS_EMPTY = "Hozircha tariflar yaratilmagan."
ADMIN_PLAN_LINE = "💎 <b>{title}</b> — {days} kun — {price}{active}\n"
ADMIN_PLAN_ACTIVE_MARK = " ✅"
ADMIN_PLAN_HIDDEN_MARK = " (yashirin)"

ADMIN_PLAN_CREATED = "✅ <b>{title}</b> tarifi yaratildi."

# Tarifni TAHRIRLASH (yangi talab): har bir qadamda joriy qiymat ko'rsatiladi,
# "-" yuborilsa qiymat o'zgarmaydi.
ADMIN_PLAN_EDIT_TITLE = "✏️ <b>Tarif tahrirlanmoqda</b> — {title}\n\nYangi NOMNI yuboring (yoki <code>-</code> — o'zgartirmaslik):"
ADMIN_PLAN_EDIT_DURATION = "🗓 Davomiylik: hozir <b>{days}</b> kun.\n\nYangi kun sonini yuboring (yoki <code>-</code>):"
ADMIN_PLAN_EDIT_PRICE = "💰 Narx: hozir <b>{price}</b>.\n\nYangi narxni yuboring (yoki <code>-</code>):"
ADMIN_PLAN_EDIT_DESC = "📝 Tavsif: <i>{description}</i>\n\nYangi tavsifni yuboring (<code>-</code> — o'zgartirmaslik, <code>0</code> — tavsifsiz):"
ADMIN_PLAN_EDIT_DONE = "✅ Tarif yangilandi."
ADMIN_PLAN_DETAILS = (
    "💎 <b>{title}</b>\n\n"
    "🗓 Davomiylik: <b>{days}</b> kun\n"
    "💰 Narx: <b>{price}</b>\n"
    "📝 Tavsif: {description}\n"
    "Holati: {status}"
)

ADMIN_PLAN_CONFIRM_DELETE = (
    "⚠️ <b>{title}</b> tarifini o'chirasizmi? Foydalanuvchilar uni ko'rmay qoladi."
)

ADMIN_PLAN_DELETED = "🗑 Tarif o'chirildi."
ADMIN_VISIBILITY_CHANGED = "✅ Ko'rinish o'zgartirildi."

# Tarif yaratish ustasi (FSM) so'rovlari:
WIZARD_PLAN_CREATE_ASK = (
    "➕ <b>Tarif yaratilmoqda</b>\n\n"
    "Menga tarifning <b>nomini</b> yuboring "
    "(masalan: <i>Premium</i> yoki <i>VIP</i>):"
)
WIZARD_PLAN_DURATION_ASK = (
    "🗓 <b>Davomiyligi</b>\n\n"
    "Tarif necha kun davom etadi? (masalan <code>7</code>, <code>30</code>, <code>365</code>):"
)
WIZARD_PLAN_PRICE_ASK = (
    "💰 <b>Narxi</b>\n\n"
    "Narxni yuboring (butun son, masalan <code>10000</code>):"
)
WIZARD_PLAN_DESC_ASK = (
    "📝 <b>Tavsif</b>\n\n"
    "To'lov oynasida ko'rinadigan qisqa tavsif yuboring "
    "(yoki <code>-</code> — tavsifsiz):"
)
WIZARD_PLAN_DAYS_INVALID = "⚠️ Iltimos, 1 dan 3650 gacha bo'lgan kun sonini yuboring."
WIZARD_PLAN_PRICE_INVALID = "⚠️ Iltimos, narxni butun son sifatida yuboring."

# -- to'lovlar ----------------------------------------------------------------
ADMIN_PAYMENTS_TITLE = "💳 <b>Kutilayotgan to'lovlar</b>\n\n{list}"
ADMIN_PAYMENTS_EMPTY = "Hozircha kutilayotgan to'lov yo'q."

# Ro'yxatdagi BITTA to'lov qatori (tarif nomi + davomiyligi bilan).
ADMIN_PAYMENT_LINE = (
    "💳 #{payment_id} — {user}\n"
    "💎 {plan} ({days} kun)\n"
    "🕒 {created}\n"
)
ADMIN_PAYMENT_PLAN_GONE = "tarif o'chirilgan"
ADMIN_PAYMENT_ZERO_DAYS = (
    "⚠️ #{payment_id} belgilandi, lekin tarif topilmadi (0 kun) — "
    "PREMIUM BERILMADI. Tarifni tiklab, qayta yuboring."
)

ADMIN_PAYMENT_CARD = (
    "💳 <b>To'lov #{payment_id}</b>\n\n"
    "👤 Kimdan: {user}\n"
    "💎 Tarif: {plan}\n"
    "🕒 Yuborilgan: {created}\n\n"
    "Chekni tekshirib, qaror qabul qiling:"
)

ADMIN_PAYMENT_APPROVED = (
    "✅ #{payment_id} to'lov tasdiqlandi — Premium {date} gacha faollashtirildi."
)
ADMIN_PAYMENT_REJECTED = "❌ #{payment_id} to'lov rad etildi."

ADMIN_PAYMENT_GONE = "⚠️ Bu to'lov allaqachon ko'rib chiqilgan."

# -- obuna sovg'a qilish (yangi talab) ---------------------------------------
ADMIN_GRANT_ASK = (
    "🎁 <b>Obuna berish</b>\n\n"
    "{user} uchun necha KUN premium berilsin?\n"
    "(masalan <code>30</code>)"
)
ADMIN_GRANT_DAYS_INVALID = "⚠️ Iltimos, 1 dan 3650 gacha bo'lgan kun sonini yuboring."
ADMIN_GRANT_DONE = "✅ {name} uchun premium <b>{date}</b> gacha faollashtirildi."
ADMIN_PREMIUM_REMOVED_DONE = "💎 {name} dan premium olindi."
ADMIN_USER_IS_ADMIN = "⚠️ Admin/ega huquqli foydalanuvchini banlash mumkin emas."
ADMIN_AWAITING_TEXT = "📝 <b>Nusxalangan xabar ko'rsatilmoqda</b>\n\nYangi matn yuboring — shu xabar saqlanadi."
ADMIN_TEXT_UPDATED = "✅ Saqlangan xabar matni yangilandi."
ADMIN_TEXT_MISSING = "⚠️ Bu foydalanuvchidan hali nusxalangan xabar yo'q."
ADMIN_TEXT_REMOVED = "🗑 Saqlangan xabar o'chirildi."
ADMIN_LIMIT_SET = "⏳ {name} uchun kunlik cheklov: <b>{n} xabar</b>."
ADMIN_LIMIT_OFF = "⏳ {name} uchun cheklov OLIB TASHLANDI (cheksiz)."
ADMIN_LIMIT_INVALID = "⚠️ Raqam yuboring (masalan <code>50</code>) yoki <code>0</code> — cheklovsiz."
ADMIN_LIMIT_PARSING_FAILED = "⚠️ Cheklovni qo'llashda xatolik — qaytadan urinib ko'ring."
ADMIN_LIMIT_ASK = (
    "⏳ <b>Kunlik limit</b>\n\n"
    "{user} kuniga nechta xabar nusxalansin?\n"
    "Raqam yuboring (masalan <code>50</code>). <code>0</code> — cheklovsiz."
)
ADMIN_PREMIUM_LIMIT_DENIED = (
    "💎 Bu foydalanuvchida PREMIUM faol — limit qo'yish maqsiz. "
    "Avval obunani oling."
)
ADMIN_TEXT_ONLY = "⚠️ Iltimos, MATN yuboring (stiker/rasm emas)."
ADMIN_USER_NOT_REGISTERED = "⚠️ Bu foydalanuvchi hali botga /start qilmagan."

# -- ommaviy xabar ------------------------------------------------------------
ADMIN_BROADCAST_ASK = (
    "📣 <b>Ommaviy xabar</b>\n\n"
    "Barcha ulangan foydalanuvchilarga yuboriladigan postni yuboring.\n\n"
    "Qo'llanadi: matn (havola va formatlash bilan), rasm, video, stiker — "
    "premium emoji bilan birga aynan shu shaklida yetkaziladi."
)

ADMIN_BROADCAST_CONFIRM = (
    "📣 Yuqoridagi xabar <b>{count}</b> ta foydalanuvchiga yuboriladi.\n\n"
    "Boshlaymizmi?"
)

ADMIN_BROADCAST_STARTED = "🚀 Ommaviy yuborish boshlandi…"
ADMIN_BROADCAST_DONE = (
    "✅ Ommaviy yuborish tugadi.\n\n"
    "Yetkazildi: <b>{sent}</b>\n"
    "O'tkazib yuborildi: <b>{skipped}</b>"
)
ADMIN_BROADCAST_EMPTY = "⚠️ Yuborish uchun hech narsa yubormadingiz."
BROADCAST_NO_RECIPIENTS = "⚠️ Yuborish uchun faol foydalanuvchi yo'q."
BROADCAST_CANCELLED = "❌ Bekor qilindi."

# ---------------------------------------------------------------------------
# Turli
# ---------------------------------------------------------------------------
UNKNOWN_ACTION = "🤔 Noma'lum amal — quyidagi menyudan foydalaning."
ERROR_USER = "😔 Xatolik yuz berdi. Keyinroq qayta urinib ko'ring."


def plan_button_label(title: str, days: int, price: int) -> str:
    """Premium tarif tugmasidagi yozuv: '30 kun - 10 000'."""
    return f"{days} kun - {fmt_number(price)} • {esc(title)}"


def plan_checkout_title(title: str, days: int) -> str:
    """To'lov oynasidagi sarlavha: 'Premium — 30 kun'."""
    return f"{esc(title)} — {days} kun"
