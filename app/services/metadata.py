# app/services/metadata.py
from __future__ import annotations
import re
from typing import List, Dict, Optional

# простые стоп-слова; при желании расширь
_STOP = {
    "a","an","the","and","or","with","of","in","on","to","for","by","from",
    "this","that","these","those","beautiful","highly","detailed","best",
    "quality","4k","8k","16k","photorealistic","ultra","hd","high","resolution"
}

def _words(s: str) -> List[str]:
    toks = re.findall(r"[A-Za-zА-Яа-я0-9][\w\-']{1,}", s or "")
    return [t.strip("-_.'").lower() for t in toks if t]

def _top_keywords(prompt: str, limit: int = 6) -> List[str]:
    # берём содержательные слова, убираем цифры/техтеги/стоп-слова
    kws: List[str] = []
    seen = set()
    for w in _words(prompt):
        if w in _STOP: 
            continue
        if w.isdigit(): 
            continue
        if len(w) < 3: 
            continue
        if re.match(r"^\d+k$", w): 
            continue
        if w in seen: 
            continue
        seen.add(w)
        kws.append(w)
    return kws[:limit] or ["art"]

def make_title(prompt: str, idx: int, total: int) -> str:
    kws = _top_keywords(prompt, limit=4)
    base = ", ".join(k.capitalize() for k in kws[:2])
    if not base:
        base = "Artwork"
    # если пачек >1 — добавим различитель
    suffix = f" — Set {idx+1}/{total}" if total > 1 else ""
    return f"{base}{suffix}"

def make_description(prompt: str, negative: Optional[str] = None) -> str:
    desc = f"{prompt.strip()}"
    if negative:
        neg = negative.strip()
        if neg:
            desc += f"\n\n— Negative prompt: {neg}"
    return desc

def make_hashtags(prompt: str, max_tags: int = 15) -> List[str]:
    kws = _top_keywords(prompt, limit=max_tags)
    # превратим в теги без пробелов/знаков
    tags = []
    for k in kws:
        tag = re.sub(r"[^A-Za-zА-Яа-я0-9]+", "", k)
        if tag:
            tags.append(tag)
    # добавим общие
    base = ["aiart", "digitalart", "deviantart"]
    for b in base:
        if b not in tags:
            tags.append(b)
    return tags[:max_tags]

def build_metadata_for_batch(prompt: str, idx: int, total: int, negative: Optional[str] = None) -> Dict[str, str]:
    title = make_title(prompt, idx, total)
    description = make_description(prompt, negative)
    tags = make_hashtags(prompt)
    hashtags_line = " ".join(f"#{t}" for t in tags)
    return {
        "title": title,
        "description": f"{description}\n\n{hashtags_line}",
        "hashtags_line": hashtags_line,
    }
