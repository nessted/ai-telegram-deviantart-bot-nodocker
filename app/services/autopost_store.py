# app/services/autopost_store.py
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_JSON = DATA_DIR / "autopost_store.json"


def _atomic_write(p: Path, payload: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _read_all() -> Dict[str, Any]:
    if not STORE_JSON.exists():
        return {}
    try:
        return json.loads(STORE_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _write_all(data: Dict[str, Any]) -> None:
    _atomic_write(STORE_JSON, data)


def ap_clear(user_id: int) -> None:
    data = _read_all()
    data[str(user_id)] = {
        "images": [],             # список tg_file_id
        "raw_name": "",
        "title": "",
        "keywords": "",
        "pack": {},               # {"title","description","hashtags":[]}
        "gallery_ids": [],
        "last_preview": "",
        "ts": int(time.time()),
    }
    _write_all(data)


def ap_add_image(user_id: int, tg_file_id: str) -> None:
    data = _read_all()
    obj = data.get(str(user_id))
    if not obj:
        ap_clear(user_id)
        data = _read_all()
        obj = data.get(str(user_id))
    imgs: List[str] = list(obj.get("images") or [])
    imgs.append(tg_file_id)
    obj["images"] = imgs
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_set_name(user_id: int, name: str) -> None:
    data = _read_all()
    obj = data.get(str(user_id)) or {}
    obj["raw_name"] = name.strip()
    obj["title"] = f'[OPEN!] ADOPTABLE - {obj["raw_name"]}'
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_set_keywords(user_id: int, keywords: str) -> None:
    data = _read_all()
    obj = data.get(str(user_id)) or {}
    obj["keywords"] = keywords.strip()
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_set_pack(user_id: int, pack: Dict[str, Any]) -> None:
    # гарантируем, что заголовок = нашему title
    data = _read_all()
    obj = data.get(str(user_id)) or {}
    obj["pack"] = dict(pack or {})
    if obj.get("title"):
        obj["pack"]["title"] = obj["title"]
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_set_gallery_ids(user_id: int, gallery_ids: List[str]) -> None:
    data = _read_all()
    obj = data.get(str(user_id)) or {}
    obj["gallery_ids"] = list(gallery_ids or [])
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_set_preview(user_id: int, preview_html: str) -> None:
    data = _read_all()
    obj = data.get(str(user_id)) or {}
    obj["last_preview"] = preview_html
    obj["ts"] = int(time.time())
    data[str(user_id)] = obj
    _write_all(data)


def ap_get(user_id: int) -> Dict[str, Any]:
    data = _read_all()
    return data.get(str(user_id)) or {
        "images": [],
        "raw_name": "",
        "title": "",
        "keywords": "",
        "pack": {},
        "gallery_ids": [],
        "last_preview": "",
        "ts": 0,
    }
