from __future__ import annotations

import asyncio
import html
import re
from typing import Any, Dict, List, Tuple

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.db import async_session
from app.models import User, ApiCredentials
from app.crypto import fernet_decrypt
from app.services.deviantart import DeviantArtClient, DeviantArtError
from app.services.custom_pack import generate_custom_pack
from app.services.gallery_prefs import get_galleries
from app.services.autopost_store import (
    ap_clear, ap_add_image, ap_set_name, ap_set_keywords,
    ap_set_pack, ap_set_preview, ap_get,
)

router = Router()

BUYERS_TITLE = "for buyers"
BUYERS_DESC = (
    "High-resolution file for buyers.\n"
    "You will receive a clean, full-size image without watermarks."
)


class AutopostStates(StatesGroup):
    waiting_images = State()
    waiting_name = State()
    waiting_keywords = State()


def _normalize_hashtags(tags: List[str] | None) -> List[str]:
    out: List[str] = []
    seen = set()
    for t in tags or []:
        t = (t or "").strip().lstrip("#")
        if not t:
            continue
        t = re.sub(r"[^A-Za-z0-9_]+", "_", t)
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t[:50])
        if len(out) >= 30:
            break
    if not any(x.lower() == "adoptable" for x in out):
        out.append("adoptable")
    return out[:30]


def _image_input_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="autopost:done_images")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="autopost:cancel")],
    ])


def _preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗂 Выбрать галерею", callback_data="custom:pick_gallery")],
        [InlineKeyboardButton(text="🚀 Опубликовать на DeviantArt", callback_data="autopost:do_publish")],
        [InlineKeyboardButton(text="🏠 На главную", callback_data="back:menu")],
    ])


def _safe_ack(cb: CallbackQuery):
    try:
        return cb.answer()
    except TelegramBadRequest:
        return None


async def _get_user(tg_id: int, username: str | None) -> User:
    async with async_session() as s:
        r = await s.execute(select(User).where(User.tg_id == tg_id))
        u = r.scalar_one_or_none()
        if not u:
            u = User(tg_id=tg_id, username=username)
            s.add(u)
            await s.commit()
            await s.refresh(u)
        return u


async def _get_da_client_for_user(user_id: int) -> DeviantArtClient | None:
    async with async_session() as s:
        r = await s.execute(
            select(ApiCredentials).where(
                ApiCredentials.user_id == user_id,
                ApiCredentials.service == "deviantart",
            )
        )
        cred = r.scalar_one_or_none()
    if not cred:
        return None
    access = fernet_decrypt(cred.access_token_enc)
    refresh = fernet_decrypt(getattr(cred, "refresh_token_enc", None))
    return DeviantArtClient(access_token=access, refresh_token=refresh, user_id=user_id)


async def _download_tg_file(bot: Bot, file_id: str) -> Tuple[bytes, str]:
    file = await bot.get_file(file_id)
    bio = await bot.download_file(file.file_path)
    data = bio.read()
    return data, "image.png"


@router.callback_query(F.data == "custom:auto")
async def start_autopost(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    ap_clear(cb.from_user.id)
    await state.set_state(AutopostStates.waiting_images)
    await state.update_data(photos=[])
    await cb.message.answer(
        "📸 Отправьте изображения для кастомного поста (можно фото или как файл).\nКогда закончите — нажмите «✅ Готово».",
        reply_markup=_image_input_kb()
    )


# 📸 Принимаем фото
@router.message(AutopostStates.waiting_images, F.photo)
async def receive_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos") or [])
    fid = msg.photo[-1].file_id
    photos.append(fid)
    await state.update_data(photos=photos)
    ap_add_image(msg.from_user.id, fid)
    await msg.answer(
        f"✅ Картинка добавлена. Сейчас {len(photos)} шт.\nДобавьте ещё или нажмите «✅ Готово».",
        reply_markup=_image_input_kb()
    )


# 📂 Принимаем изображение как документ (файл)
@router.message(AutopostStates.waiting_images, F.document)
async def receive_document(msg: Message, state: FSMContext):
    if not msg.document.mime_type or not msg.document.mime_type.startswith("image/"):
        await msg.answer("❌ Можно загружать только изображения (jpg, png).")
        return
    data = await state.get_data()
    photos = list(data.get("photos") or [])
    fid = msg.document.file_id
    photos.append(fid)
    await state.update_data(photos=photos)
    ap_add_image(msg.from_user.id, fid)
    await msg.answer(
        f"✅ Файл-изображение добавлен. Сейчас {len(photos)} шт.\nДобавьте ещё или нажмите «✅ Готово».",
        reply_markup=_image_input_kb()
    )


@router.callback_query(AutopostStates.waiting_images, F.data == "autopost:done_images")
async def done_images(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    data = await state.get_data()
    if not data.get("photos"):
        await cb.message.answer("❌ Вы не добавили ни одного изображения.")
        return
    await state.set_state(AutopostStates.waiting_name)
    await cb.message.answer("✏️ Напишите имя персонажа (например: Lily).")


@router.callback_query(AutopostStates.waiting_images, F.data == "autopost:cancel")
async def cancel_autopost(cb: CallbackQuery, state: FSMContext):
    await _safe_ack(cb)
    await state.clear()
    ap_clear(cb.from_user.id)
    await cb.message.answer("❌ Автопост отменён. Вернитесь в меню.")


@router.message(AutopostStates.waiting_name)
async def receive_name(msg: Message, state: FSMContext):
    name = (msg.text or "").strip()
    if not name:
        await msg.answer("⚠️ Имя не должно быть пустым. Введите ещё раз.")
        return
    ap_set_name(msg.from_user.id, name)
    await state.set_state(AutopostStates.waiting_keywords)
    await msg.answer("📝 Напишите ключевые слова для описания (через запятую).")


@router.message(AutopostStates.waiting_keywords)
async def receive_keywords(msg: Message, state: FSMContext):
    keywords = (msg.text or "").strip()
    ap_set_keywords(msg.from_user.id, keywords)

    store = ap_get(msg.from_user.id)
    pack = await generate_custom_pack(store.get("raw_name", "") or "Adoptable", keywords)

    tags_norm = _normalize_hashtags(pack.get("hashtags") or [])
    pack["hashtags"] = tags_norm
    pack["title"] = store.get("title") or pack.get("title") or "Adoptable"
    ap_set_pack(msg.from_user.id, pack)

    imgs = store.get("images") or []
    tags_preview = " ".join(tags_norm)
    preview = f"""<b>DeviantArt — предпросмотр кастомного поста</b>
<b>Кадров в пачке:</b> {len(imgs)}
<b>Title (нумерация при публикации):</b> {html.escape(pack['title'])} (1), (2), …

<b>Description:</b>
<code>{html.escape((pack.get('description') or '')[:2000])}</code>

<b>Hashtags ({len(tags_norm)}):</b> {tags_preview}"""
    ap_set_preview(msg.from_user.id, preview)

    await state.clear()
    await msg.answer(preview, reply_markup=_preview_kb())


@router.callback_query(F.data == "autopost:do_publish")
async def autopost_publish(cb: CallbackQuery, bot: Bot):
    await _safe_ack(cb)

    u = await _get_user(cb.from_user.id, cb.from_user.username)
    client = await _get_da_client_for_user(u.id)
    if not client:
        await cb.message.answer("❌ DeviantArt не подключён.")
        return

    try:
        await client.ensure_fresh()
    except DeviantArtError as e:
        await cb.message.answer(f"❌ Нужна повторная авторизация DeviantArt: {e}")
        await client.aclose()
        return

    store = ap_get(cb.from_user.id)
    images: List[str] = list(store.get("images") or [])
    pack = dict(store.get("pack") or {})
    if not images or not pack:
        await cb.message.answer("❌ Нет данных для публикации. Перезапустите автопост.")
        return

    tags_norm = _normalize_hashtags(pack.get("hashtags") or [])
    pack["hashtags"] = tags_norm

    prefs = get_galleries(u.id)
    gallery_ids: List[str] = list(store.get("gallery_ids") or []) or list(prefs.get("ids") or [])

    results: List[str] = []
    errors: List[str] = []

    contents: List[Tuple[bytes, str]] = []
    for idx, fid in enumerate(images, 1):
        try:
            contents.append(await _download_tg_file(bot, fid))
        except Exception as e:
            errors.append(f"[{idx}] download: {e}")
        await asyncio.sleep(0)

    try:
        for idx, (content, fname) in enumerate(contents, 1):
            try:
                # A) buyers
                await client.stash_submit(
                    file_bytes=content,
                    filename=fname,
                    title=BUYERS_TITLE,
                    artist_comments=BUYERS_DESC,
                    tags=None,
                    is_dirty=False,
                    is_ai_generated=True,
                    noai=False,
                )
                # B) временный item — НУМЕРАЦИЯ (idx)
                per_title = f"{pack.get('title') or 'Adoptable'} ({idx})"
                tmp_item = await client.stash_submit(
                    file_bytes=content,
                    filename=fname,
                    title=per_title,
                    artist_comments=pack.get("description") or "",
                    tags=tags_norm,  # уйдут как tags[]
                    is_dirty=False,
                    is_ai_generated=True,
                    noai=False,
                )
                tmp_id = str(tmp_item.get("itemid") or "")
                if not tmp_id:
                    raise DeviantArtError(f"Unexpected stash response: {tmp_item}")

                pub = await client.stash_publish(
                    itemid=tmp_id,
                    is_mature=False,
                    galleryids=gallery_ids or None,
                    tags=tags_norm,  # уйдут как tags[]
                    is_ai_generated=True,
                    noai=False,
                    add_watermark=True,
                    display_resolution=2,
                    feature=True,
                    allow_comments=True,
                    allow_free_download=False,
                )
                results.append(pub.get("url") or f"id:{pub.get('deviationid')}")
            except Exception as e:
                errors.append(f"[{idx}] publish: {e}")
    finally:
        await client.aclose()

    if results:
        txt = "Опубликовано ✅\n" + "\n".join(f"• {html.escape(x)}" for x in results)
        if errors:
            txt += "\n⚠️ Ошибки:\n" + "\n".join(errors)
        await cb.message.answer(txt)
        ap_clear(cb.from_user.id)
    else:
        await cb.message.answer("❌ Публикация не удалась.\n" + ("\n".join(errors) if errors else ""))
