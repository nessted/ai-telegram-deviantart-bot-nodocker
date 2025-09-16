from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, delete

from app.db import async_session
from app.models import User, ApiCredentials
from app.keyboards import profile_kb
from app.config import settings
from app.crypto import fernet_encrypt

router = Router()


# ===== FSM =====
class ProfileStates(StatesGroup):
    waiting_tensorart_key = State()


# ===== utils =====
async def _safe_ack(cb: CallbackQuery) -> None:
    try:
        await cb.answer()
    except TelegramBadRequest:
        pass


async def _get_or_create_user(tg_id: int, username: Optional[str]) -> User:
    async with async_session() as s:
        res = await s.execute(select(User).where(User.tg_id == tg_id))
        u = res.scalar_one_or_none()
        if not u:
            u = User(tg_id=tg_id, username=username)
            s.add(u)
            await s.commit()
            await s.refresh(u)
        return u


async def _has_cred(user_id: int, service: str) -> bool:
    async with async_session() as s:
        res = await s.execute(
            select(ApiCredentials).where(
                ApiCredentials.user_id == user_id,
                ApiCredentials.service == service,
            )
        )
        return res.scalar_one_or_none() is not None


# ===== open profile =====
@router.callback_query(F.data == "profile:open")
async def open_profile(cb: CallbackQuery):
    await _safe_ack(cb)
    user = await _get_or_create_user(cb.from_user.id, cb.from_user.username)
    da_ok = await _has_cred(user.id, "deviantart")
    ta_ok = await _has_cred(user.id, "tensorart")

    text = (
        "<b>👤 Профиль</b>\n\n"
        f"DeviantArt: {'✅ подключён' if da_ok else '❌ не подключён'}\n"
        f"Tensor.Art: {'✅ подключён' if ta_ok else '❌ не подключён'}\n"
    )
    await cb.message.edit_text(text, reply_markup=profile_kb(da_ok=da_ok, ta_ok=ta_ok))


# ===== DeviantArt connect / disconnect =====
@router.callback_query(F.data == "profile:connect_da")
async def connect_deviantart(cb: CallbackQuery):
    await _safe_ack(cb)
    # Соберём URL OAuth авторизации
    scope = "stash publish browse user gallery"  # при необходимости скорректируй
    state = f"tg:{cb.from_user.id}"
    params = {
        "response_type": "code",
        "client_id": settings.DA_CLIENT_ID,
        "redirect_uri": settings.DA_REDIRECT_URI,
        "scope": scope,
        "state": state,
    }
    auth_url = "https://www.deviantart.com/oauth2/authorize?" + urlencode(params)
    await cb.message.answer(
        "Для подключения DeviantArt перейдите по ссылке и подтвердите доступ:\n" + auth_url
    )


@router.callback_query(F.data == "profile:disconnect_da")
async def disconnect_deviantart(cb: CallbackQuery):
    await _safe_ack(cb)
    user = await _get_or_create_user(cb.from_user.id, cb.from_user.username)
    async with async_session() as s:
        await s.execute(
            delete(ApiCredentials).where(
                ApiCredentials.user_id == user.id,
                ApiCredentials.service == "deviantart",
            )
        )
        await s.commit()
    await cb.message.answer("DeviantArt отключён.")
    # Обновим профиль
    await open_profile(cb)


# ===== Tensor.Art connect / disconnect =====
@router.callback_query(F.data == "profile:add_tensorart")
async def add_tensorart(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    await state.set_state(ProfileStates.waiting_tensorart_key)
    await cb.message.answer(
        "🔑 Пришлите Tensor.Art API ключ.\n"
        "Можно целиком как «Bearer …», можно только сам токен — я пойму."
    )


@router.message(ProfileStates.waiting_tensorart_key)
async def save_tensorart_key(msg: Message, state: FSMContext):
    raw = (msg.text or "").strip()
    token = raw
    # принимаем форматы: "Bearer XXX", "bearer XXX", или просто "XXX"
    if raw.lower().startswith("bearer "):
        token = raw.split(None, 1)[1].strip()
    if not token or len(token) < 10:
        await msg.answer("❌ Ключ выглядит подозрительно коротким. Пришлите ещё раз или /cancel.")
        return

    user = await _get_or_create_user(msg.from_user.id, msg.from_user.username)
    enc = fernet_encrypt(token)

    async with async_session() as s:
        # проверим — есть ли уже запись
        res = await s.execute(
            select(ApiCredentials).where(
                ApiCredentials.user_id == user.id,
                ApiCredentials.service == "tensorart",
            )
        )
        cred = res.scalar_one_or_none()
        if cred:
            cred.access_token_enc = enc
            s.add(cred)
        else:
            cred = ApiCredentials(
                user_id=user.id,
                service="tensorart",
                access_token_enc=enc,
                refresh_token_enc=None,
            )
            s.add(cred)
        await s.commit()

    await state.clear()
    await msg.answer("✅ Tensor.Art ключ сохранён. Теперь можно генерировать изображения!")


@router.callback_query(F.data == "profile:disconnect_ta")
async def disconnect_tensorart(cb: CallbackQuery):
    await _safe_ack(cb)
    user = await _get_or_create_user(cb.from_user.id, cb.from_user.username)
    async with async_session() as s:
        await s.execute(
            delete(ApiCredentials).where(
                ApiCredentials.user_id == user.id,
                ApiCredentials.service == "tensorart",
            )
        )
        await s.commit()
    await cb.message.answer("Tensor.Art отключён.")
    await open_profile(cb)


# ===== back to main menu =====
@router.callback_query(F.data == "back:menu")
async def back_menu(cb: CallbackQuery):
    await _safe_ack(cb)
    # импорт внутри, чтобы избежать циклических импортов
    from app.routers.start import show_main_menu
    await show_main_menu(cb)
