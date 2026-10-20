"""Ortak HTTP istemcisi: kullanıcı-ajanı, yeniden deneme, bellek önbelleği.

İletişim e-postası yalnızca kullanıcı RESEARCHAI_MAILTO ortam değişkenini açıkça
ayarlarsa gönderilir. Varsayılan olarak hiçbir kişisel veri gönderilmez.
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx

_CACHE: dict[str, tuple[float, httpx.Response]] = {}
_TTL = 3600.0


def user_agent() -> str:
    mail = os.environ.get("RESEARCHAI_MAILTO", "").strip()
    return "researchai-mcp/0.1" + (f" (mailto:{mail})" if mail else "")


async def get(url: str, params: dict | None = None, headers: dict | None = None,
              retries: int = 2, timeout: float = 25.0) -> httpx.Response:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    h = {"User-Agent": user_agent(), **(headers or {})}
    last: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            last = await client.get(url, params=params, headers=h)
            if last.status_code == 429 or last.status_code >= 500:
                retry_after = last.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else 2.0 * (attempt + 1)
                if wait > 30:  # uzun bekleme: bekleme, çağırana hata dön
                    break
                await asyncio.sleep(wait)
                continue
            break
    assert last is not None
    if last.status_code == 200:
        _CACHE[key] = (time.time(), last)
    return last
