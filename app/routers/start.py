from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from app.keyboards import main_menu_kb

router = Router()

async def show_main_menu(target):
    # target может быть Message или CallbackQuery
    if isinstance(target, Message):
        await target.answer(
            "Привет! Я помогу сгенерировать персонажа, создать изображение и опубликовать на DeviantArt.",
            reply_markup=main_menu_kb()
        )
    else:
        # CallbackQuery
        await target.message.edit_text(
            "Главное меню",
            reply_markup=main_menu_kb()
        )
        await target.answer()

@router.message(F.text == "/start")
async def cmd_start(msg: Message):
    await show_main_menu(msg)

# Старый alias
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_legacy(cb: CallbackQuery):
    await show_main_menu(cb)

# Новый универсальный “Назад в меню”
@router.callback_query(F.data == "back:menu")
async def back_to_menu(cb: CallbackQuery):
    await show_main_menu(cb)
