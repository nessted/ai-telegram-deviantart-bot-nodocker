from __future__ import annotations

import asyncio
import json
import copy
from uuid import uuid4  # ← добавлен импорт наверху
from typing import Any, Dict, Iterable, List, Optional, Tuple
import logging
import httpx

logger = logging.getLogger(__name__)

class TensorArtError(RuntimeError):
    """Детальная ошибка работы с Tensor.Art (с агрегированием попыток)."""


def _mk_headers(api_key: str, app_id: Optional[str] = None) -> Dict[str, str]:
    # Пробуем оба варианта заголовка с App-Id — по опыту некоторых API-гейтов
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if app_id:
        headers["App-Id"] = app_id
        headers["X-App-Id"] = app_id
    return headers


class TensorArtClient:
    """
    Простой клиент Tensor.Art без шаблонов. Работает с «сырым» workflow:
    - POST /v1/jobs (основной)
    - POST /v1/jobs/workflow (в некоторых окружениях)
    и умеет ждать результат через:
    - GET /v1/jobs/{id}
    - GET /v1/workflows/jobs/{id}
    """

    def __init__(
        self,
        api_key: str,
        region_url: Optional[str] = None,
        app_id: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        # region_url например: https://ap-east-1.tensorart.cloud
        self.base_url = (region_url or "https://ap-east-1.tensorart.cloud").rstrip("/")
        self.api_key = api_key
        self.app_id = app_id
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------- Вспомогательные ----------

    async def _post_candidates(
        self,
        candidates: Iterable[str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Перебирает несколько путей POST, пробует добавить app_id/appId в query,
        собирает все ошибки и, если не удалось, бросает TensorArtError.
        """
        errors: List[str] = []
        headers = _mk_headers(self.api_key, self.app_id)

        for path in candidates:
            # 1) без query
            try:
                r = await self._client.post(path, json=payload, headers=headers)
                if r.status_code < 300:
                    return r.json()
                errors.append(self._format_error("POST", path, r))
            except httpx.HTTPError as ex:
                errors.append(f"POST {path} -> transport error: {repr(ex)}")

            # 2) с app_id в query (snake)
            if self.app_id:
                try:
                    r = await self._client.post(
                        path,
                        json=payload,
                        headers=headers,
                        params={"app_id": self.app_id},
                    )
                    if r.status_code < 300:
                        return r.json()
                    errors.append(self._format_error("POST", path, r, with_query=True))
                except httpx.HTTPError as ex:
                    errors.append(
                        f"POST {path}?app_id=… -> transport error: {repr(ex)}"
                    )

                # 3) с appId в query (camel) — некоторые шлюзы ждут именно так
                try:
                    r = await self._client.post(
                        path,
                        json=payload,
                        headers=headers,
                        params={"appId": self.app_id},
                    )
                    if r.status_code < 300:
                        return r.json()
                    errors.append(self._format_error("POST", path, r, with_query=True))
                except httpx.HTTPError as ex:
                    errors.append(
                        f"POST {path}?appId=… -> transport error: {repr(ex)}"
                    )

        raise TensorArtError("create_job failed:\n" + "\n".join(errors))

    async def _get_candidates(
        self,
        candidates: Iterable[str],
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        headers = _mk_headers(self.api_key, self.app_id)
        params = dict(params or {})
        for path in candidates:
            # 1) без query
            try:
                r = await self._client.get(path, headers=headers, params=params)
                if r.status_code < 300:
                    return r.json()
                errors.append(self._format_error("GET", path, r))
            except httpx.HTTPError as ex:
                errors.append(f"GET {path} -> transport error: {repr(ex)}")

            # 2) с app_id как query (snake)
            p2 = dict(params)
            if self.app_id:
                p2["app_id"] = self.app_id
            try:
                r = await self._client.get(path, headers=headers, params=p2)
                if r.status_code < 300:
                    return r.json()
                errors.append(self._format_error("GET", path, r, with_query=True))
            except httpx.HTTPError as ex:
                errors.append(
                    f"GET {path}?app_id=… -> transport error: {repr(ex)}"
                )

            # 3) с appId (camel)
            p3 = dict(params)
            if self.app_id:
                p3["appId"] = self.app_id
            try:
                r = await self._client.get(path, headers=headers, params=p3)
                if r.status_code < 300:
                    return r.json()
                errors.append(self._format_error("GET", path, r, with_query=True))
            except httpx.HTTPError as ex:
                errors.append(
                    f"GET {path}?appId=… -> transport error: {repr(ex)}"
                )

        raise TensorArtError("GET failed:\n" + "\n".join(errors))

    @staticmethod
    def _format_error(
        method: str, path: str, response: httpx.Response, *, with_query: bool = False
    ) -> str:
        tag = f"{method} {path}{'?app_id=…' if with_query else ''}"
        try:
            data = response.json()
        except Exception:
            data = response.text
        return f"{tag} -> {response.status_code}: {data}"

    # ---------- Публичные методы ----------

    async def create_job(self, stages: List[Dict[str, Any]]) -> str:
        """Создаёт задачу и возвращает её идентификатор (job_id)."""
        stages = copy.deepcopy(stages)

        # 1) Удаляем любые requestId/request_id из stage-объектов
        for st in stages:
            if isinstance(st, dict):
                st.pop("requestId", None)
                st.pop("request_id", None)

        # 2) Ровно один requestId на верхнем уровне (camelCase)
        rid = uuid4().hex
        payload: Dict[str, Any] = {"requestId": rid, "stages": stages}

        # На всякий случай — если кто-то ранее добавил snake_case
        payload.pop("request_id", None)

        # Полезно увидеть, что реально уходит
        try:
            logger.debug("Tensor.Art payload: %s", json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

        # Живые кандидаты на создание
        paths = ("/v1/jobs",)
        data = await self._post_candidates(paths, payload)

        # Нормализуем возможные ответы и извлекаем job_id
        job_id = (
            data.get("id")
            or data.get("job_id")
            or data.get("jobId")
            or data.get("data", {}).get("id")
            or data.get("data", {}).get("job_id")
            or data.get("job", {}).get("id")
        )
        if isinstance(job_id, str) and job_id:
            return job_id

        # иногда возвращают объект с ключом 'result' или 'task'
        for k in ("result", "task"):
            v = data.get(k)
            if isinstance(v, dict):
                j = v.get("id") or v.get("job_id") or v.get("jobId")
                if isinstance(j, str) and j:
                    return j

        raise TensorArtError(
            "create_job: unable to extract job id from response: "
            + json.dumps(data, ensure_ascii=False)
        )

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """Возвращает описание джоба по его ID (GET /v1/jobs/{id})."""
        return await self._get_candidates((f"/v1/jobs/{job_id}",))

    async def get_result_urls(self, job_id: str) -> List[str]:
        """Достаёт список URL-ов изображений для успешно завершённого джоба.
        Возвращает пустой список, если ещё не готово или нет картинок.
        """
        data = await self.get_job(job_id)
        urls: List[str] = []

        # Основной формат TAMS: {"job": {"status": "SUCCESS", "successInfo": {"images": [{"url": ...}, ...]}}}
        job = data.get("job") or {}
        succ = job.get("successInfo") or {}
        images = (
            succ.get("images")
            or succ.get("imageList")
            or data.get("images")
            or data.get("data", {}).get("images")
            or data.get("result", {}).get("images")
            or data.get("output", {}).get("images")
            or []
        )
        if isinstance(images, list):
            for it in images:
                if isinstance(it, str) and it.startswith("http"):
                    urls.append(it)
                elif isinstance(it, dict):
                    u = it.get("url") or it.get("image_url") or it.get("imageUrl")
                    if isinstance(u, str) and u.startswith("http"):
                        urls.append(u)

        # Иногда кладут одиночный URL напрямую
        for u in (
            data.get("url"),
            data.get("image_url"),
            data.get("data", {}).get("url"),
            data.get("data", {}).get("image_url"),
        ):
            if isinstance(u, str) and u.startswith("http"):
                urls.append(u)

        # Убираем дубли, сохраняем порядок
        seen = set()
        uniq = []
        for u in urls:
            if u not in seen:
                uniq.append(u)
                seen.add(u)
        return uniq

    async def download_image(self, url: str) -> bytes:
        """Скачивает изображение по подписанной ссылке Tensor.Art с редиректами."""
        r = await self._client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.content

    async def wait_result_urls(
        self,
        job_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: float = 180.0,
    ) -> List[str]:
        """Ждём завершения и возвращаем ВСЕ URL-ы изображений для этого job_id."""
        ready = {"succeeded", "completed", "done", "success", "finished"}
        running = {"queued", "pending", "processing", "running", "waiting"}
        deadline = asyncio.get_event_loop().time() + timeout
        last_snapshot: Optional[Dict[str, Any]] = None

        while asyncio.get_event_loop().time() < deadline:
            data = await self.get_job(job_id)
            last_snapshot = data
            job = data.get("job") or {}
            status = (job.get("status") or data.get("status") or "").lower()

            if status in ready:
                urls = await self.get_result_urls(job_id)
                if urls:
                    return urls
                # готово, но ссылки не нашли — отдадим ошибку с снимком
                break

            if status in running:
                await asyncio.sleep(poll_interval)
                continue

            # неизвестный статус — подождём ещё раз
            await asyncio.sleep(poll_interval)

        raise TensorArtError(
            "wait_result_urls: no image urls. Last observation: "
            + json.dumps(last_snapshot or {}, ensure_ascii=False)
        )

    async def wait_result_url(
        self,
        job_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: float = 180.0,
    ) -> str:
        """Совместимый обёртка: возвращает ПЕРВУЮ ссылку, либо бросает ошибку."""
        urls = await self.wait_result_urls(job_id, poll_interval=poll_interval, timeout=timeout)
        if urls:
            return urls[0]
        raise TensorArtError("wait_result_url: empty urls list")

# ---------- Конструктор «этапов» (txt2img) ----------

def build_txt2img_stages(
    *,
    # ВАЖНО: сюда теперь передаём ИМЕННО ОСНОВНОЙ промпт (из description)
    prompt: str,
    # А этот хвост (база) будет доклеен к основному промпту автоматически
    sd_tail: Optional[str] = None,

    negative: Optional[str],
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    clip_skip: Optional[int] = None,
    sd_model: Optional[str] = None,
    loras: Optional[List[Tuple[str, float]]] = None,
    count: int = 1,
    seed: int = -1,
    sampler: Optional[str] = None,
    sd_vae: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Формируем стадии TAMS для Basic Job ("/v1/jobs").
    Теперь prompt = ОСНОВНОЙ промпт, а sd_tail (если задан) доклеивается в конец.
    """
    # --- склейка основного промпта и базы-хвоста ---
    main_core = (prompt or "").strip().strip(",")
    tail = (sd_tail or "").strip().strip(",")

    if main_core and tail:
        final_prompt = f"{main_core}, {tail}"
    elif main_core:
        final_prompt = main_core
    else:
        # на всякий случай не оставляем пусто
        final_prompt = tail or "masterpiece"

    # 1) INPUT_INITIALIZE
    stages: List[Dict[str, Any]] = [
        {
            "type": "INPUT_INITIALIZE",
            "inputInitialize": {
                "seed": int(seed if seed is not None else -1),
                "count": int(count if count is not None else 1),
            },
        }
    ]

    # 2) DIFFUSION
    diffusion: Dict[str, Any] = {
        "width": width,
        "height": height,
        "prompts": [{"text": final_prompt}],
        "steps": steps,
        "cfgScale": cfg_scale,
    }
    if sampler:
        diffusion["sampler"] = sampler
    if sd_vae:
        diffusion["sdVae"] = sd_vae
    if clip_skip is not None:
        diffusion["clipSkip"] = int(clip_skip)

    # sdModel — строковый ID модели
    if sd_model is not None:
        diffusion["sdModel"] = str(sd_model).strip()

    if negative:
        diffusion["negativePrompts"] = [{"text": negative}]
    if loras:
        diffusion["loras"] = [{"loraModel": str(lid), "weight": float(w)} for lid, w in loras]

    stages.append({
        "type": "DIFFUSION",
        "diffusion": diffusion,
    })

    return stages
