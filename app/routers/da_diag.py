# app/routers/da_diag.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from app.db import async_session
from app.models import User, ApiCredentials
from app.crypto import fernet_decrypt
from app.services.deviantart import DeviantArtClient

router = Router()

async def _get_or_create_user(tg_id: int, username: str | None):
    async with async_session() as s:
        r = await s.execute(select(User).where(User.tg_id == tg_id))
        u = r.scalar_one_or_none()
        if not u:
            u = User(tg_id=tg_id, username=username)
            s.add(u)
            await s.commit()
            await s.refresh(u)
        return u

async def _check_da_for_user(tg_id: int, username: str | None) -> str:
    u = await _get_or_create_user(tg_id, username)
    async with async_session() as s:
        r = await s.execute(
            select(ApiCredentials).where(
                ApiCredentials.user_id == u.id,
                ApiCredentials.service == "deviantart",
            )
        )
        cred = r.scalar_one_or_none()

    if not cred:
        return "DeviantArt не подключён. Откройте профиль → «🖼 Подключить DeviantArt» и завершите вход."

    access_token = fernet_decrypt(cred.access_token_enc)

    async with DeviantArtClient(access_token) as da:
        try:
            ok = (await da.placebo()).get("status") == "success"
            who = await da.whoami()
            name = who.get("username") or (who.get("user") or {}).get("username")
            return f"DA OK: {ok}\nАккаунт: {name or '—'}"
        except Exception as e:
            return f"Ошибка DeviantArt: {e!r}"

@router.message(F.text == "/da_check")
async def da_check_cmd(msg: Message):
    await msg.answer(await _check_da_for_user(msg.from_user.id, msg.from_user.username))

@router.callback_query(F.data.in_({"profile:check_da", "da:check"}))
async def da_check_cb(cb: CallbackQuery):
    await cb.message.answer(await _check_da_for_user(cb.from_user.id, cb.from_user.username))
    await cb.answer()
