# app/services/ai_text.py
from __future__ import annotations
import os, json, random, re
from typing import Optional, Dict, Any, List

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception

# ---------------- SD base (ГЛОБАЛЬНЫЕ НАСТРОЙКИ: добавляется в НАЧАЛО основного промпта при отправке в Tensor.Art) ----------------
SD_BASE = (
    "score_9, score_8_up, score_7_up, score_6_up, highly detailed, intricate, "
    "intricate details, highly detailed face, s1_dram, best quality, high resolution, "
    "4k, 8k, 16k, volumetric light, sharp focus, highly detailed, detalized eyes, "
    "beautiful lighting, pretty eyes"
)

# ---------------- utils ----------------
def _normalize_base_url(url: Optional[str]) -> str:
    u = (url or "").strip()
    if not u:
        return "https://api.openai.com/v1"
    if "://" not in u:
        u = "https://" + u
    return u.rstrip("/")

def _retry_filter(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response is not None and exc.response.status_code in (408, 429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TransportError, httpx.ReadTimeout, httpx.ConnectError))

class TextGenResult(dict):
    @property
    def prompt_tokens(self) -> int: return self.get("prompt_tokens", 0)
    @property
    def completion_tokens(self) -> int: return self.get("completion_tokens", 0)

def _json_block(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}

# ===== DeviantArt title/hashtags helpers =====
_BANNED_TOKENS = {
    "girl","boy","woman","man","female","male","character","portrait","art","image","picture",
    "chic","cute","pretty","adorable","blonde","brunette","redhead","model",
    "steampunk","cyberpunk","fantasy","gothic","streetwear","historical","sci-fi","anime","cartoon",
}

_FEMALE_NAMES = [
    "Elara","Lyra","Mira","Nova","Kira","Luna","Aria","Vera","Nina","Rin","Kei","Aya",
    "Noa","Yuna","Sora","Astra","Kaya","Rhea","Eira","Zara","Mina","Iris","Dana",
]
_MALE_NAMES = [
    "Kael","Orin","Riven","Arden","Jace","Kane","Orion","Evan","Darin","Ren","Aiden","Ezra",
    "Kieran","Lucian","Rowan","Silas","Zane","Leo","Nolan","Arlo","Cassian","Eli","Noel",
]

_ROLE_RULES = [
    (r"engineer|gear|steam|device|wrench", "Engineer"),
    (r"samurai|katana|ronin", "Samurai"),
    (r"mage|wizard|sorcer", "Mage"),
    (r"witch|coven|broom", "Witch"),
    (r"assassin|dagger|stealth", "Assassin"),
    (r"pilot|mech|mecha|cockpit", "Mech Pilot"),
    (r"warrior|knight|fighter|sword|shield", "Warrior"),
    (r"vampire|fang", "Vampire"),
    (r"archer|bow|arrow", "Archer"),
    (r"cyber|neon|augmented|implant|hacker", "Hacker"),
    (r"astronaut|space|orbit", "Astronaut"),
    (r"priestess|cleric|oracle", "Priestess"),
    (r"ninja|shuriken", "Ninja"),
    (r"goth|victorian|lace|veil", "Goth"),
]

def _guess_gender(text: str) -> str:
    t = f" {text or ''} ".lower()
    if any(x in t for x in (" male ", " man ", " his ", " him ", " boy ")):
        return "male"
    return "female"

def _pick_name(gender: str) -> str:
    pool = _MALE_NAMES if gender == "male" else _FEMALE_NAMES
    return random.choice(pool)

def _pick_role(text: str) -> Optional[str]:
    t = (text or "").lower()
    for rx, role in _ROLE_RULES:
        if re.search(rx, t):
            return role
    return None

def _is_bad_title(name: str) -> bool:
    if not name:
        return True
    if any(ch.isdigit() for ch in name):
        return True
    toks = re.findall(r"[A-Za-z][A-Za-z'-]*", name)
    if not toks:
        return True
    if any(tok.lower() in _BANNED_TOKENS for tok in toks):
        return True
    return len(toks) > 4

def _compose_title(main_prompt: str, raw_title: str, *, limit: int = 50) -> str:
    prefix = "[OPEN!] ADOPTABLE - "
    name_part = (raw_title or "").strip()

    if name_part.lower().startswith(prefix.lower()):
        name_part = name_part[len(prefix):].strip()

    if _is_bad_title(name_part):
        gender = _guess_gender(main_prompt)
        name = _pick_name(gender)
        role = _pick_role(main_prompt)
        name_part = f"{name} {role}" if role else name

    avail = max(5, limit - len(prefix))
    if len(name_part) > avail:
        first = name_part.split()[0]
        name_part = first[:avail].rstrip("-–— •.,")
    return prefix + name_part

def _clean_hashtags(tags, main_prompt: str) -> List[str]:
    tags = tags if isinstance(tags, list) else []
    clean, seen = [], set()
    for t in tags:
        s = str(t or "").strip()
        if not s:
            continue
        if not s.startswith("#"):
            s = "#" + s.lstrip("#")
        s = s.replace(" ", "")
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        clean.append(s)
        if len(clean) >= 30:
            break
    for must in ("#adoptable", "#adaptable"):
        if must not in (x.lower() for x in clean):
            clean.append(must)
    if len(clean) < 30:
        for w in re.findall(r"[a-zA-Z0-9]+", (main_prompt or "").lower()):
            tag = "#" + w
            if tag.lower() in (x.lower() for x in clean):
                continue
            clean.append(tag)
            if len(clean) >= 30:
                break
    return clean[:30]

def _inject_notice(desc: str) -> str:
    notice = (") This adopt is generated by AI Midjourney after buy, u got clear image without watermark "
              "Everyone can also order custom work-commission art:3 You can use anything you want if you buy it! 💖 "
              "Paypal accepted WHEN YOU BUY, NO RETURNS, you need to make sure you like it and there will be no problems in the future.")
    d = (desc or "").strip()
    if not d.startswith(")"):
        return notice + ("\n\n" + d if d else "")
    return d

# ---------------- OpenAI client ----------------
THEME_POOL = [
    "knight","samurai","cyborg","android","elf","vampire","witch","mage","mecha pilot",
    "steampunk engineer","hacker","astronaut","archer","priestess","ninja","demon",
    "angel","dragonborn","catgirl","foxgirl","mermaid","fairy","pirate","assassin",
    "paladin","druid","necromancer","robot"
]

class OpenAITextClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = _normalize_base_url(base_url or os.getenv("OPENAI_API_BASE"))
        self.model = (model or os.getenv("TEXT_MODEL") or "gpt-4o-mini").strip()
        fb_env = os.getenv("TEXT_MODEL_FALLBACKS", "")
        self.fallback_models: List[str] = [m.strip() for m in fb_env.split(",") if m.strip()]
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        self.last_model_used: Optional[str] = None

    def _extract_text(self, data: Dict[str, Any]) -> str:
        ch = data.get("choices")
        if isinstance(ch, list) and ch:
            msg = (ch[0] or {}).get("message") or {}
            txt = (msg.get("content") or "").strip()
            if txt:
                return txt
        if "output_text" in data and data["output_text"]:
            return str(data["output_text"]).strip()
        out = data.get("output")
        if isinstance(out, list):
            parts = []
            for item in out:
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if c.get("type") in ("output_text", "text") and c.get("text"):
                            parts.append(c["text"])
            if parts:
                return "".join(parts).strip()
        return ""

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _chat_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        r = await self._client.post("chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

    async def _chat_any(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chain: List[str] = []
        if self.model:
            chain.append(self.model)
        for m in self.fallback_models:
            if m and m not in chain:
                chain.append(m)

        last_err: Optional[Exception] = None
        for m in chain:
            payload["model"] = m
            try:
                data = await self._chat_raw(payload)
                data["_model_used"] = m
                self.last_model_used = m
                return data
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response is not None else None
                if code in (400, 404):
                    last_err = e
                    continue
                raise
        if last_err:
            raise last_err
        raise RuntimeError("No model to try")

    @retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3), retry=retry_if_exception(_retry_filter))
    async def _chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 240,
        temperature: float = 1.05,
        top_p: Optional[float] = 0.95,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if presence_penalty:
            payload["presence_penalty"] = presence_penalty
        if frequency_penalty:
            payload["frequency_penalty"] = frequency_penalty
        data = await self._chat_any(payload)
        if not self.last_model_used:
            self.last_model_used = (payload.get("model") or self.model)
        return data

    # ---------- Генерация по ИДЕЕ: одна строка; добавлены SEED/тематика/penalties ----------
    @retry(wait=wait_exponential(min=1, max=6), stop=stop_after_attempt(2), retry=retry_if_exception(_retry_filter))
    async def refine_from_idea(self, idea: str, *, max_words: int = 9999) -> str:
        seed = random.randint(1, 10**9)
        suggested_theme = random.choice(THEME_POOL)
        base_instruction = (
            "generate prompt like this example, return me back just prompt, nothing extra "
            "(correct the information in curly brackets to the character's characteristics for the prompt, "
            "embed information that will be related to each other. do not create contradictions in the prompt. "
            "don't be afraid to make fictional characters, but don't overuse it) "
            "1female, solo, woman, {age_number} years old, {maturity}, {appearance_style}, {face_shape}, "
            "{emotion_expression}, {extra_trait} {hair_color}, {hairstyle}, {clothing_top}, {clothing_bottom}, "
            "{footwear}, {accessories}, {pose}, {arms_position}, {body_trait}, {breast_size}, {eye_state}, "
            "{blush_expression}, {attitude}, {background_type}, {background_style}"
        )
        sys_msg = (
            "Return EXACTLY the prompt(s) in English, nothing else. "
            "Generate 3 DIVERSE candidates, each on its own line, no numbering. "
            "Replace all placeholders with short tokens (1–3 words). "
            "Use the provided SEED to break ties and encourage variety. "
            "Keep age_number >= 19. Ensure maturity matches age (19–29: adult, 30+: mature). "
            "THEME: infer from IDEA; if not obvious, PICK EXACTLY ONE from this list and reflect it CONSISTENTLY "
            "across the prompt (role/species/augments/accessories/clothing/background): "
            + ", ".join(THEME_POOL) + ". "
            "No curly braces must remain."
        )
        user_msg = (
            f"SEED: {seed}\n"
            f"SUGGESTED_THEME: {suggested_theme}\n"
            f"IDEA:\n{(idea or '').strip()}\n\n"
            f"{base_instruction}\n"
            "Make the chosen theme evident (e.g., 'samurai armor', 'cybernetic arm', 'elf ears', 'vampire fangs', "
            "'witch hat', 'mecha cockpit', 'holy robes', 'ninja mask', etc.). "
            "Avoid plain modern casual unless the IDEA demands it."
        )
        data = await self._chat(
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            max_tokens=280,
            temperature=1.35,
            top_p=0.9,
            presence_penalty=0.7,
            frequency_penalty=0.6,
        )
        raw = (self._extract_text(data) or "").strip()
        choices = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        out = random.choice(choices) if choices else raw
        return " ".join(out.split())

    # ---------- Случайный промпт (3 варианта + SEED + случайная тема) ----------
    @retry(wait=wait_exponential(min=1, max=6), stop=stop_after_attempt(2), retry=retry_if_exception(_retry_filter))
    async def random_prompt(self, *, max_words: int = 9999) -> str:
        seed = random.randint(1, 10**9)
        suggested_theme = random.choice(THEME_POOL)
        base_instruction = (
            "generate prompt like this example, return me back just prompt, nothing extra "
            "(correct the information in curly brackets to the character's characteristics for the prompt, "
            "embed information that will be related to each other. do not create contradictions in the prompt. "
            "don't be afraid to make fictional characters, but don't overuse it) "
            "1female, solo, woman, {age_number} years old, {maturity}, {appearance_style}, {face_shape}, "
            "{emotion_expression}, {extra_trait} {hair_color}, {hairstyle}, {clothing_top}, {clothing_bottom}, "
            "{footwear}, {accessories}, {pose}, {arms_position}, {body_trait}, {breast_size}, {eye_state}, "
            "{blush_expression}, {attitude}, {background_type}, {background_style}"
        )
        sys_msg = (
            "Return EXACTLY the prompt(s) in English, nothing else. "
            "Generate 3 DIVERSE candidates, each on its own line, no numbering. "
            "Replace all placeholders with short tokens (1–3 words). "
            "Use the provided SEED to break ties and encourage variety. "
            "Keep age_number >= 19. Ensure maturity matches age (19–29: adult, 30+: mature). "
            "Pick EXACTLY ONE THEME from the list and reflect it consistently "
            "(role/species/augments/accessories/clothing/background): "
            + ", ".join(THEME_POOL) + ". "
            "No curly braces must remain."
        )
        user_msg = (
            f"SEED: {seed}\n"
            f"THEME: {suggested_theme}\n\n"
            f"{base_instruction}\n"
            "Make the chosen theme evident (e.g., 'samurai armor', 'cybernetic arm', 'elf ears', 'vampire fangs', "
            "'witch hat', 'mecha cockpit', 'holy robes', 'ninja mask', etc.). "
            "Avoid plain modern casual."
        )
        data = await self._chat(
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            max_tokens=280,
            temperature=1.4,
            top_p=0.9,
            presence_penalty=0.75,
            frequency_penalty=0.65,
        )
        raw = (self._extract_text(data) or "").strip()
        choices = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        out = random.choice(choices) if choices else raw
        return " ".join(out.split())

    # ---------- Обёртка для совместимости ----------
    async def generate(self, style_hint: str | None = None) -> TextGenResult:
        line = await self.random_prompt()
        return TextGenResult({
            "idea": style_hint or "",
            "title": "Custom Portrait",
            "description": "Autogenerated character prompt.",
            "tags_csv": "portrait,girl,generation",
            "main_prompt": line,
            "sd_prompt": SD_BASE,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "provider": "openai",
            "model_used": self.last_model_used or "",
        })

    # ---------- DeviantArt pack ----------
    @retry(wait=wait_exponential(min=1, max=6), stop=stop_after_attempt(2), retry=retry_if_exception(_retry_filter))
    async def deviantart_pack(self, main_prompt: str) -> Dict[str, Any]:
        """
        Возвращает {"title": str, "description": str, "hashtags": List[str]}.
        """
        sys_msg = (
            "Respond STRICTLY as minified JSON with keys: "
            "title (string), description (string), hashtags (array of 30 strings). "
            "Title must be a short human name (first name, optionally + role), no digits, no styles; "
            "DO NOT include the '[OPEN!] ADOPTABLE - ' prefix. "
            "Description: 2–4 short sentences about the character. "
            "Hashtags: 30 items, start with '#', lowercase, no spaces, no duplicates."
        )
        user_msg = "PROMPT:\n" + (main_prompt or "").strip() + "\nReturn ONLY JSON."

        data = await self._chat(
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            max_tokens=320,
            temperature=0.9,
            top_p=0.95,
            presence_penalty=0.2,
            frequency_penalty=0.1,
        )
        raw = _json_block(self._extract_text(data)) or {}
        raw_title = str(raw.get("title") or "").strip()
        raw_desc  = str(raw.get("description") or "").strip()
        raw_tags  = raw.get("hashtags") or []

        title = _compose_title(main_prompt, raw_title, limit=50)
        tags  = _clean_hashtags(raw_tags, main_prompt)
        desc  = _inject_notice(raw_desc or main_prompt or "Adoptable character.")

        return {"title": title, "description": desc, "hashtags": tags}

# ---------------- dummy ----------------
class DummyTextClient:
    """Простой фоллбэк без внешних запросов."""
    last_model_used: str = "dummy"

    async def aclose(self) -> None:
        return

    async def refine_from_idea(self, idea: str, *, max_words: int = 9999) -> str:
        return await self.random_prompt()

    async def random_prompt(self, *, max_words: int = 9999) -> str:
        def pick(xs): return random.choice(xs)
        age = random.randint(19, 32)
        maturity = "adult" if age < 30 else "mature"
        theme = pick(THEME_POOL)
        # делаем тему очевидной: добавим 1–2 токена в релевантные поля
        theme_style = {
            "samurai": ("samurai armor","katana","temple garden"),
            "knight": ("plate armor","longsword","castle courtyard"),
            "cyborg": ("cybernetic arm","optic implant","neon-lit background"),
            "android": ("synthetic skin","glowing circuits","lab interior"),
            "elf": ("elf ears","leaf brooch","enchanted forest"),
            "vampire": ("vampire fangs","goth choker","moonlit graveyard"),
            "witch": ("witch hat","rune pendant","arcane library"),
            "mage": ("arcane robe","spellbook","wizard tower"),
            "mecha pilot": ("pilot suit","cockpit harness","mecha hangar"),
        }.get(theme, ("stylized","unique accessory","cinematic background"))

        parts = [
            "1female, solo, woman",
            f"{age} years old",
            maturity,
            theme,  # appearance_style
            pick(["oval face","heart-shaped face","round face","diamond face"]),
            pick(["soft smile","serious","playful","confident","shy","calm","cheerful"]),
            theme_style[0],  # extra_trait (подмешиваем тему)
            pick(["blonde hair","brown hair","black hair","red hair","silver hair","pink hair"]),
            pick(["long wavy hairstyle","short bob","ponytail","braided hairstyle","curly hairstyle"]),
            pick(["blouse","corset","hoodie","kimono top","leather jacket","sleek jumpsuit","denim jacket"]),
            pick(["skirt","cargo pants","kimono skirt","leather pants","long skirt","shorts","black leggings"]),
            pick(["boots","sneakers","heels","sandals","ankle boots"]),
            pick(["necklace","choker","goggles","earrings","gloves","scarf","belt","sunglasses"]),
            pick(["three-quarter view","profile view","looking over shoulder","mid-leap","kneeling","standing"]),
            pick(["arms relaxed","arms crossed","one hand on hip","hands behind back"]),
            pick(["slim body","athletic build","curvy body"]),
            pick(["small breasts","medium breasts","large breasts"]),
            pick(["open eyes","half-closed eyes","winking","wide-eyed"]),
            pick(["none","light blush","smiling"]),
            pick(["confident","shy","playful","mysterious","approachable"]),
            pick(["outdoors","indoors","scenery","urban"]),
            theme_style[2],  # background_style
        ]
        line = f"{parts[0]}, {parts[1]}, {parts[2]}, {parts[3]}, {parts[4]}, {parts[5]}, {parts[6]} {parts[7]}, {parts[8]}, {parts[9]}, {parts[10]}, {parts[11]}, {parts[12]}, {parts[13]}, {parts[14]}, {parts[15]}, {parts[16]}, {parts[17]}, {parts[18]}, {parts[19]}, {parts[20]}, {parts[21]}"
        return " ".join(line.split())

    async def generate(self, style_hint: str | None = None) -> TextGenResult:
        line = await self.random_prompt()
        return TextGenResult({
            "idea": style_hint or "",
            "title": "Custom Portrait",
            "description": "Autogenerated character prompt.",
            "tags_csv": "portrait,girl,generation",
            "main_prompt": line,
            "sd_prompt": SD_BASE,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "provider": "dummy",
            "model_used": self.last_model_used
        })

    async def deviantart_pack(self, main_prompt: str) -> Dict[str, Any]:
        raw_title = "ChicBlonde24"
        title = _compose_title(main_prompt, raw_title, limit=50)
        desc  = _inject_notice(main_prompt or "Adoptable character.")
        tags  = _clean_hashtags(["#aiart","#digitalart"], main_prompt)
        return {"title": title, "description": desc, "hashtags": tags}
