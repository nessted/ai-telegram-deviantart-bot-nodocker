# app/services/gallery_prefs.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GALLERY_JSON = DATA_DIR / "gallery_prefs.json"


def _atomic_write(p: Path, payload: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def get_galleries(user_id: int) -> Dict[str, List[str]]:
    """
    Возвращает {"ids": [...], "names": [...]} либо пустые списки.
    """
    try:
        if not GALLERY_JSON.exists():
            return {"ids": [], "names": []}
        data = json.loads(GALLERY_JSON.read_text(encoding="utf-8") or "{}")
        obj = data.get(str(user_id)) or {}
        ids = list(obj.get("ids") or [])
        names = list(obj.get("names") or [])
        if len(ids) != len(names):
            # самовосстановление: лишнее отбрасываем
            n = min(len(ids), len(names))
            ids, names = ids[:n], names[:n]
        return {"ids": ids, "names": names}
    except Exception:
        return {"ids": [], "names": []}


def set_galleries(user_id: int, ids: List[str], names: List[str]) -> None:
    """
    Сохранение выбора. Длины списков должны совпадать.
    """
    if len(ids) != len(names):
        raise ValueError("ids and names length mismatch")

    data: Dict[str, dict] = {}
    if GALLERY_JSON.exists():
        try:
            data = json.loads(GALLERY_JSON.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}

    data[str(user_id)] = {"ids": list(ids), "names": list(names)}
    _atomic_write(GALLERY_JSON, data)


# --- совместимость со старым кодом при желании ---
def get_da_galleries(user_id: int) -> Dict[str, List[str]]:
    return get_galleries(user_id)

def set_da_galleries(user_id: int, ids: List[str], names: List[str]) -> None:
    return set_galleries(user_id, ids, names)
