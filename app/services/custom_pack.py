# app/services/custom_pack.py
from __future__ import annotations
from typing import Dict, List
import re
from app.services.ai_text import OpenAITextClient, DummyTextClient


async def generate_custom_pack(name: str, keywords: str) -> Dict[str, str | List[str]]:
    """
    Generator for custom DeviantArt post.
    Accepts name and keywords → returns title, description, hashtags.
    """

    prompt = (
        f"You are a professional writer for DeviantArt adoptable posts.\n\n"
        f"Character name: {name}\n"
        f"Keywords: {keywords}\n\n"

        f"Requirements:\n"
        f"- Write a short artistic description in fantasy/gothic/anime tone if it fits.\n"
        f"- Divide it into paragraphs.\n"
        f"- Use keywords as the base, but keep text natural.\n"
        f"- Maximum length: 150 words.\n"
        f"- Do NOT include the name or '[OPEN!] ADOPTABLE' in the description.\n\n"

        f"After the description, output a block:\n"
        f"Hashtags: exactly 30 hashtags, in English, lowercase, without symbol # separated by commas."
    )

    try:
        client = OpenAITextClient()
        data = await client._chat(
            messages=[
                {"role": "system", "content": "You create short adoptable descriptions for DeviantArt."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.85,
            top_p=0.95,
        )
        text = client._extract_text(data)
    except Exception:
        client = DummyTextClient()
        text = await client.random_prompt()

    # Split description and hashtags
    desc = text.strip()
    hashtags: List[str] = []

    if "hashtags:" in text.lower():
        parts = re.split(r"hashtags:\s*", text, flags=re.I)
        desc = parts[0].strip()
        if len(parts) > 1:
            hashtags = [t.strip() for t in re.split(r"[,\n]", parts[1]) if t.strip()]

    # Normalize hashtags
    norm_tags, seen = [], set()
    for t in hashtags:
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t
        if t.lower() not in seen:
            seen.add(t.lower())
            norm_tags.append(t[:50].lower())
    # enforce exactly 30
    if len(norm_tags) > 30:
        norm_tags = norm_tags[:30]
    while len(norm_tags) < 30:
        norm_tags.append("#adoptable")

    await client.aclose()

    return {
        "title": f"[OPEN!] ADOPTABLE - {name}",
        "description": desc,
        "hashtags": norm_tags,
    }
