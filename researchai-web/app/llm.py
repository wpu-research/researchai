"""NVIDIA NIM (OpenAI uyumlu) istemcisi.

Her çağrı token kullanımını döndürür; JSON isteyen çağrılarda yanıt sağlamca ayrıştırılır.
Birincil model zaman aşımına uğrar ya da hata verirse yedek modele geçilir.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass

import httpx

URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions"


def model_main() -> str:
    return os.environ.get("RESEARCHAI_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")


def model_fast() -> str:
    return os.environ.get("RESEARCHAI_MODEL_FAST", "nvidia/nemotron-3.5-lightning-30b-a3b")


def model_reviewer() -> str:
    """Hakem simülasyonunda ikinci, farklı aileden model (kör ve bağımsız görüş için)."""
    return os.environ.get("RESEARCHAI_MODEL_REVIEWER", "openai/gpt-oss-20b")


def enabled() -> bool:
    return bool(os.environ.get("NVIDIA_API_KEY", "").strip())


class LLMError(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def json(self):
        return parse_json(self.text)


def parse_json(text: str):
    """Model yanıtından ilk geçerli JSON nesnesini/dizisini çıkarır (kod çiti ve ön söz toleranslı)."""
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                return dec.raw_decode(t[i:])[0]
            except json.JSONDecodeError:
                continue
    raise LLMError("modelden geçerli JSON gelmedi: " + t[:160])


async def _call(model: str, messages: list[dict], max_tokens: int, temperature: float, timeout: float) -> Reply:
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise LLMError("NVIDIA_API_KEY ayarlı değil")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False}}
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in range(3):
            r = await c.post(URL, json=body, headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            break
    if r.status_code != 200:
        raise LLMError(f"{model}: HTTP {r.status_code} {r.text[:160]}")
    d = r.json()
    msg = d["choices"][0]["message"]
    text = msg.get("content") or ""
    if not text.strip():
        raise LLMError(f"{model}: boş yanıt")
    u = d.get("usage") or {}
    return Reply(text, d.get("model") or model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


async def chat(system: str, user: str, model: str | None = None, max_tokens: int = 2000,
               temperature: float = 0.3, timeout: float = 150.0, fallback: bool = True) -> Reply:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    first = model or model_main()
    try:
        return await _call(first, messages, max_tokens, temperature, timeout)
    except (LLMError, httpx.HTTPError) as ex:
        alt = model_fast() if first != model_fast() else model_main()
        if not fallback or alt == first:
            raise LLMError(str(ex)) from ex
        try:
            return await _call(alt, messages, max_tokens, temperature, timeout)
        except (LLMError, httpx.HTTPError) as ex2:
            raise LLMError(f"{ex}; yedek de başarısız: {ex2}") from ex2


async def chat_json(system: str, user: str, **kw):
    """JSON döndürmesi gereken çağrı; geçersiz JSON'da bir kez daha ister."""
    sys2 = system + "\n\nYanıtın YALNIZCA geçerli JSON olmalı; açıklama, kod çiti veya ön söz yazma."
    rep = await chat(sys2, user, **kw)
    try:
        return rep.json(), rep
    except LLMError:
        rep2 = await chat(sys2, user + "\n\nÖnceki yanıtın geçerli JSON değildi. Yalnız JSON döndür.", **kw)
        rep2.prompt_tokens += rep.prompt_tokens
        rep2.completion_tokens += rep.completion_tokens
        return rep2.json(), rep2
