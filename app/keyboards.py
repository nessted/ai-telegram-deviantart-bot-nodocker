from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Tuple


def back_btn(target: str = "menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{target}")


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧬 Создать персонажа", callback_data="gen:new")],
        [InlineKeyboardButton(text="🤖 Автопост", callback_data="custom:auto")],
        [InlineKeyboardButton(text="⚙️ Настройки генерации", callback_data="settings:open")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile:open")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help:open")],
    ])



def styles_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Реализм", callback_data="style:realism"),
            InlineKeyboardButton(text="🌸 Аниме", callback_data="style:anime"),
            InlineKeyboardButton(text="🧩 Мульт", callback_data="style:cartoon"),
        ],
        [back_btn("menu")],
    ])


def prompt_editor_kb(gen_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✍️ Править основной промпт", callback_data="editor:edit_main")],
        [InlineKeyboardButton(text="🛠 Править SD-промпт", callback_data="editor:edit_sd")],
        [InlineKeyboardButton(text="🚫 Править Negative", callback_data="editor:edit_negative")],
        [InlineKeyboardButton(text="▶️ Выбрать количество (Генерация)", callback_data="count:open")],
        [back_btn("styles")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gen_confirm_kb(gen_id: int, credits: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Запустить (≈ {credits:.2f} cr)", callback_data=f"img:run:{gen_id}")],
        [back_btn("editor")]
    ])


def image_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать на DeviantArt", callback_data="da:publish")],
        [back_btn("editor")]
    ])


def profile_kb(da_ok: bool = False, ta_ok: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура профиля с учётом статуса подключений.
    - DeviantArt: показываем Подключить/Отключить.
    - Tensor.Art: пока есть только кнопка добавления; если уже подключён — показываем Отключить.
    """
    rows = []

    # Tensor.Art
    if ta_ok:
        rows.append([InlineKeyboardButton(text="🔌 Отключить Tensor.Art", callback_data="profile:disconnect_ta")])
    else:
        rows.append([InlineKeyboardButton(text="🧪 Добавить Tensor.Art", callback_data="profile:add_tensorart")])

    # DeviantArt
    if da_ok:
        rows.append([InlineKeyboardButton(text="🔌 Отключить DeviantArt", callback_data="profile:disconnect_da")])
    else:
        rows.append([InlineKeyboardButton(text="🖼 Подключить DeviantArt", callback_data="profile:connect_da")])

    # Прочее
    rows.append([InlineKeyboardButton(text="⚙️ Настройки генерации", callback_data="settings:open")])
    rows.append([back_btn("menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# === Настройки (урезанный набор) ===

def settings_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Размер", callback_data="settings:size")],
        [InlineKeyboardButton(text="🧭 Steps (≤20)", callback_data="settings:steps")],
        [InlineKeyboardButton(text="🎚 CFG Scale (≤10)", callback_data="settings:cfg")],
        [back_btn("menu")],
    ])


def gallery_page_kb(items: List[Tuple[str, str, bool]], offset: int, limit: int, has_more: bool) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора галерей.
    items: список кортежей (folderid, name, выбран_или_нет)
    """
    rows: List[List[InlineKeyboardButton]] = []
    for fid, name, selected in items:
        mark = "✅ " if selected else "⬜️ "
        rows.append([InlineKeyboardButton(text=mark + name, callback_data=f"da:toggle:{fid}")])

    nav: List[InlineKeyboardButton] = []
    if offset > 0:
        prev_offset = max(0, offset - limit)
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"da:page:{prev_offset}"))
    if has_more:
        next_offset = offset + limit
        nav.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"da:page:{next_offset}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="✅ Сохранить", callback_data="da:save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="da:cancel_pick"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

def sizes_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="768×1152", callback_data="size:768x1152"),
            InlineKeyboardButton(text="1024×1024", callback_data="size:1024x1024"),
        ],
        [back_btn("settings")]
    ])


def steps_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="8", callback_data="steps:8"),
            InlineKeyboardButton(text="12", callback_data="steps:12"),
            InlineKeyboardButton(text="16", callback_data="steps:16"),
            InlineKeyboardButton(text="20", callback_data="steps:20"),
        ],
        [back_btn("settings")]
    ])


def cfg_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3.0", callback_data="cfg:3"),
            InlineKeyboardButton(text="5.0", callback_data="cfg:5"),
            InlineKeyboardButton(text="7.0", callback_data="cfg:7"),
            InlineKeyboardButton(text="10.0", callback_data="cfg:10"),
        ],
        [back_btn("settings")]
    ])


def models_kb(models: list[tuple[str, str]], selected_id: str | None) -> InlineKeyboardMarkup:
    rows = []
    for mid, name in models:
        mark = "✅ " if selected_id == mid else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{name}", callback_data=f"model:pick:{mid}")])
    rows.append([InlineKeyboardButton(text="➡️ Далее", callback_data="lora:open")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:editor")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def loras_kb(loras: list[tuple[str, str]], selected_ids: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for lid, name in loras:
        mark = "✅ " if lid in selected_ids else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{name}", callback_data=f"lora:toggle:{lid}")])
    rows.append([
        InlineKeyboardButton(text="➡️ Далее", callback_data="count:open"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="model:open"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def count_kb(current: int | None = None) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text=("✅ 1" if current == 1 else "1"), callback_data="count:pick:1"),
        InlineKeyboardButton(text=("✅ 2" if current == 2 else "2"), callback_data="count:pick:2"),
        InlineKeyboardButton(text=("✅ 3" if current == 3 else "3"), callback_data="count:pick:3"),
        InlineKeyboardButton(text=("✅ 4" if current == 4 else "4"), callback_data="count:pick:4"),
    ]]
    # Возврат из выбора количества — обратно в редактор
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:editor")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
