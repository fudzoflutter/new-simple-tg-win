"""
Admin (ega) boshqaruv handlerlari — ruxsat berish, rad etish, ban, unban.

Bu yerdagi hammasi FAQAT ``ADMIN_ID`` uchun: boshqa odam bossa «faqat admin
uchun» ogohlantirishi chiqadi.

Ikki ekran:

* **So'rov kartasi** — yangi foydalanuvchi murojaat qilganda adminga
  «✅ Ruxsat berish / ❌ Rad etish» tugmalari bilan keladi;
* **«👥 Foydalanuvchilar»** — ro'yxat; har bir qatorda BITTA amal tugmasi:
  ruxsatli odam uchun «🚫 Ban», so'rov kutayotganiga «✅ Ruxsat berish»,
  banlanganiga «✅ Blokdan chiqarish».

Ro'yxat ikki manbadan BIRLASHTIRILADI: ``users`` (botdan foydalanganlar) va
``access`` (ruxsat/ban yozuvlari).  Shu tufayli yangi tasdiqlangan odam —
u hali ``users`` jadvaliga yozilib ulgurmagan yoki /start bosmagan bo'lsa
ham — DARHOL ro'yxatda ko'rinadi.

TEZLIK: har bir callback AVVAL ``cb.answer()`` qiladi (spinner darhol
to'xtaydi), so'ng holat keshga yoziladi va ekran yangilanadi.  Yozuv ketishi
uchun kutish faqat adminning o'ziga ta'sir qiladi, oddiy update'larga emas.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from app.config import settings
from app.database import db
from app.emoji_config import EMOJI
from app.keyboards import access_kb, user_kb
from app.services import access
from app.utils import texts
from app.utils.formatting import fmt_number, mention_by_id
from app.utils.timeutils import is_online

router = Router(name="admin")
logger = logging.getLogger(__name__)

# Bir sahifada nechta foydalanuvchi ko'rsatiladi.
PAGE_SIZE = 6


# ---------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------
def _is_admin(cb: CallbackQuery) -> bool:
    return cb.from_user.id == settings.admin_id


async def _not_admin(cb: CallbackQuery) -> None:
    await cb.answer("Bu bo'lim faqat admin uchun", show_alert=True)


def _int_at(data: str, index: int, default: int = 0) -> int:
    """Callback ma'lumotidagi N-qismni butun songa aylantiradi (xavfsiz)."""
    try:
        return int((data or "").split(":")[index])
    except (IndexError, ValueError):
        return default


def _action_for(user_id: int) -> str:
    """Ro'yxatdagi tugma turi: ``ban`` / ``grant`` / ``unban``."""
    if access.can_use(user_id):
        return "ban"
    if access.status(user_id) in (access.BANNED, access.DENIED):
        return "unban"
    return "grant"


# ---------------------------------------------------------------------------
# So'rov kartasi: ✅ Ruxsat berish / ❌ Rad etish
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith(f"{access_kb.CB_ALLOW}:"))
async def allow_user(cb: CallbackQuery, bot: Bot) -> None:
    """Ruxsat berish tugmasi (so'rov kartasi)."""
    await _decide(cb, bot, allowed=True)


@router.callback_query(F.data.startswith(f"{access_kb.CB_DENY}:"))
async def deny_user(cb: CallbackQuery, bot: Bot) -> None:
    """Rad etish tugmasi (so'rov kartasi)."""
    await _decide(cb, bot, allowed=False)


async def _decide(cb: CallbackQuery, bot: Bot, *, allowed: bool) -> None:
    """Qarorni qo'llaydi: kesh + baza, foydalanuvchiga xabar, kartani yangilash."""
    if not _is_admin(cb):
        await _not_admin(cb)
        return

    user_id = _int_at(cb.data, 2)
    if not user_id:
        await cb.answer("Foydalanuvchi IDsi topilmadi", show_alert=True)
        return

    # TEZLIK: javob DARHOL (baza yozuvi ~1.2 s olsa ham tugma kutmaydi).
    # Alert matnida premium emoji ishlamaydi — oddiy emoji ishlatiladi.
    await cb.answer(
        f"{EMOJI.access_allowed.fallback} Ruxsat berildi"
        if allowed
        else f"{EMOJI.access_rejected.fallback} Rad etildi"
    )

    await access.set_status(
        user_id,
        access.ALLOWED if allowed else access.DENIED,
        decided_by=cb.from_user.id,
    )
    # Ruxsat berilganda foydalanuvchi darhol ishlatishi uchun menyu ham ketadi.
    await access.notify_user(
        bot,
        user_id,
        texts.USER_APPROVED if allowed else texts.USER_DENIED,
        with_menu=allowed,
    )

    # Kartadagi tugmalarni olib tashlaymiz va qarorni tepasiga yozamiz.
    try:
        head = (
            texts.ACCESS_REQUEST_ALLOWED if allowed else texts.ACCESS_REQUEST_DENIED
        )
        old = cb.message.text or ""
        await cb.message.edit_text(f"{head}\n\n{old}", reply_markup=access_kb.empty())
    except Exception:  # noqa: BLE001 – xabar juda eski bo'lishi mumkin
        logger.exception("So'rov kartasi yangilanmadi")


# ---------------------------------------------------------------------------
# «👥 Foydalanuvchilar» — ro'yxat + ban / ruxsat berish / blokdan chiqarish
# ---------------------------------------------------------------------------
@router.callback_query(F.data == user_kb.CB_USERS)
async def show_users(cb: CallbackQuery) -> None:
    """Ro'yxatning birinchi sahifasi (faqat admin)."""
    if not _is_admin(cb):
        await _not_admin(cb)
        return
    await cb.answer()  # TEZLIK: spinner darhol to'xtaydi
    await _render_users(cb, page=1)


@router.callback_query(F.data.startswith(f"{access_kb.CB_USERS_PAGE}:"))
async def page_users(cb: CallbackQuery) -> None:
    """Sahifalash: ⬅️ / ➡️."""
    if not _is_admin(cb):
        await _not_admin(cb)
        return
    await cb.answer()
    await _render_users(cb, page=_int_at(cb.data, 3, 1))


@router.callback_query(F.data.startswith(f"{access_kb.CB_BAN}:"))
async def ban_user(cb: CallbackQuery, bot: Bot) -> None:
    """🚫 Ban — foydalanuvchi botdan foydalana olmaydi."""
    await _toggle_ban(cb, bot, ban=True)


@router.callback_query(F.data.startswith(f"{access_kb.CB_UNBAN}:"))
async def unban_user(cb: CallbackQuery, bot: Bot) -> None:
    """✅ Ruxsat berish / blokdan chiqarish — ayni tugma."""
    await _toggle_ban(cb, bot, ban=False)


async def _toggle_ban(cb: CallbackQuery, bot: Bot, *, ban: bool) -> None:
    """Ban yoki ruxsat berish (blokdan chiqarish) va ro'yxatni joyida yangilash."""
    if not _is_admin(cb):
        await _not_admin(cb)
        return

    user_id = _int_at(cb.data, 2)
    page = _int_at(cb.data, 3, 1)
    if not user_id:
        await cb.answer("Foydalanuvchi IDsi topilmadi", show_alert=True)
        return

    await cb.answer(
        f"{EMOJI.access_banned.fallback} Banlandi"
        if ban
        else f"{EMOJI.access_allowed.fallback} Ruxsat berildi"
    )

    await access.set_status(
        user_id,
        access.BANNED if ban else access.ALLOWED,
        decided_by=cb.from_user.id,
    )
    await access.notify_user(
        bot, user_id, texts.USER_BANNED if ban else texts.USER_UNBANNED
    )
    # Tugma holati almashishi uchun ro'yxatni qayta chizamiz.
    await _render_users(cb, page=page)


async def _render_users(cb: CallbackQuery, page: int) -> None:
    """Foydalanuvchilar ro'yxatini chizadi (amal tugmalari bilan)."""
    users, access_rows = await db.gather(db.all_users(), db.access_rows())

    # 1) ``users`` — botdan foydalanganlar.
    people: dict[int, dict] = {}
    for row in users:
        user_id = int(row["user_id"])
        people[user_id] = {
            "user_id": user_id,
            "username": row.get("username"),
            "first_name": row.get("first_name"),
            "created_at": row.get("created_at") or "",
            "last_activity": row.get("last_activity"),
        }

    # 2) ``access`` — boshqarilayotgan (so'rov/ban) odamlar, shu jumladan
    #    ``users`` jadvalida hali yo'q bo'lganlari (yangi tasdiqlangan).
    for row in access_rows:
        user_id = int(row["user_id"])
        entry = people.get(user_id)
        if entry is None:
            people[user_id] = {
                "user_id": user_id,
                "username": row.get("username"),
                "first_name": row.get("first_name"),
                "created_at": row.get("created_at") or "",
                "last_activity": None,
            }
            continue
        # Ism manbasi ikki joyda bo'lishi mumkin — bo'sh joyni to'ldiramiz.
        entry["username"] = entry.get("username") or row.get("username")
        entry["first_name"] = entry.get("first_name") or row.get("first_name")
        if not entry.get("created_at"):
            entry["created_at"] = row.get("created_at") or ""

    # Admin o'zini banlay olmasligi uchun ro'yxatdan chiqaramiz.
    people_list = [p for p in people.values() if p["user_id"] != settings.admin_id]
    people_list.sort(key=lambda p: (p["created_at"], p["user_id"]), reverse=True)

    total = len(people_list)
    # Online hisobi QO'SHIMCHA so'rovsiz (xotirada) — count_online bilan bir xil.
    online = sum(1 for p in people_list if is_online(p.get("last_activity")))

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(1, page), pages)
    chunk = people_list[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    lines: list[str] = []
    rows: list[tuple[int, str, str]] = []
    for person in chunk:
        user_id = person["user_id"]
        label = access_kb.short_label(
            person.get("username"), person.get("first_name"), user_id
        )
        lines.append(
            texts.USERS_PANEL_LINE.format(
                badge=access.badge(user_id),
                mention=mention_by_id(
                    user_id, person.get("first_name") or label, person.get("username")
                ),
                user_id=user_id,
            )
        )
        rows.append((user_id, label, _action_for(user_id)))

    body = "\n".join(lines) if lines else texts.USERS_PANEL_EMPTY
    text = texts.USERS_PANEL_TITLE.format(
        total=fmt_number(total),
        online=fmt_number(online),
        body=body,
        legend=texts.USERS_PANEL_LEGEND,
    )
    if pages > 1:
        text += "\n" + texts.USERS_PANEL_PAGE.format(page=page, pages=pages)

    await cb.message.edit_text(
        text, reply_markup=access_kb.users_panel(rows, page, pages)
    )
