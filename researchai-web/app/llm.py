"""Anthropic Claude istemcisi (resmi `anthropic` SDK).

Her çağrı token kullanımını döndürür; JSON isteyen çağrılarda yanıt sağlamca ayrıştırılır.
Birincil model zaman aşımına uğrar ya da hata verirse yedek modele geçilir.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import anthropic

# Güvenlik sınıflandırıcısı reddederse API isteği aynı çağrı içinde uygun modelde yeniden çalıştırır.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Düşünme (thinking) çıktı bütçesinden yer; çağıranın istediği metin uzunluğunun üstüne eklenir.
THINKING_HEADROOM = 16000


def model_main() -> str:
    return os.environ.get("RESEARCHAI_MODEL", "claude-opus-5-5")


def model_fast() -> str:
    return os.environ.get("RESEARCHAI_MODEL_FAST", "claude-haiku-5-5")


def model_reviewer() -> str:
    """Hakem simülasyonunda ikinci, farklı model (kör ve bağımsız görüş için)."""
    return os.environ.get("RESEARCHAI_MODEL_REVIEWER", "claude-sonnet-5-5")


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _client(timeout: float) -> anthropic.AsyncAnthropic:
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    return anthropic.AsyncAnthropic(timeout=timeout, max_retries=3,
                                    default_headers={"anthropic-workspace-id": ws} if ws else None)


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


async def _call(model: str, system: str, user: str, max_tokens: int, timeout: float) -> Reply:
    if not enabled():
        raise LLMError("ANTHROPIC_API_KEY ayarlı değil")
    kw = {}
    if not model.startswith("claude-haiku"):
        kw = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    effort = "low" if model.startswith("claude-haiku") else "medium"
    try:
        async with _client(timeout) as c:
            async with c.beta.messages.stream(
                model=model, max_tokens=max_tokens + THINKING_HEADROOM, system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort}, **kw,
            ) as stream:
                msg = await stream.get_final_message()
    except anthropic.APIStatusError as ex:
        raise LLMError(f"{model}: HTTP {ex.status_code} {str(ex.message)[:160]}") from ex
    except anthropic.APIConnectionError as ex:
        raise LLMError(f"{model}: bağlantı hatası ({ex})") from ex
    if msg.stop_reason == "refusal":
        raise LLMError(f"{model}: istek reddedildi")
    text = "".join(b.text for b in msg.content if b.type == "text")
    if not text.strip():
        raise LLMError(f"{model}: boş yanıt")
    return Reply(text, msg.model, msg.usage.input_tokens, msg.usage.output_tokens)


async def chat(system: str, user: str, model: str | None = None, max_tokens: int = 2000,
               temperature: float | None = None, timeout: float = 300.0, fallback: bool = True) -> Reply:
    """`temperature` geriye uyumluluk için kabul edilir; güncel Claude modelleri örnekleme ayarı almaz."""
    first = model or model_main()
    try:
        return await _call(first, system, user, max_tokens, timeout)
    except LLMError as ex:
        alt = model_fast() if first != model_fast() else model_main()
        if not fallback or alt == first:
            raise
        try:
            return await _call(alt, system, user, max_tokens, timeout)
        except LLMError as ex2:
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
