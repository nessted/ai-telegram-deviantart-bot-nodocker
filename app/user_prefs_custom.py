from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

SETTINGS_JSON = Path(__file__).resolve().parent / "user_settings_custom.json"


def set_custom_galleries(user_id: int, ids: List[str], names: List[str]) -> None:
    """Сохраняем выбранные галереи для кастомных постов"""
    data: Dict[str, Dict] = {}
    if SETTINGS_JSON.exists():
        try:
            data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
    obj = data.get(str(user_id), {})
    obj["ids"] = ids
    obj["names"] = names
    data[str(user_id)] = obj
    SETTINGS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_custom_galleries(user_id: int) -> Dict[str, List[str]]:
    """Загружаем галереи для кастомных постов"""
    if SETTINGS_JSON.exists():
        try:
            data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
            return data.get(str(user_id), {})
        except Exception:
            return {}
    return {}
