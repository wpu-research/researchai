"""TR Dizin (TÜBİTAK ULAKBİM) bağlayıcısı.

Belge: https://development.trdizin.gov.tr/ . Uç nokta, arayüzün kullandığı JSON arama API'sidir.
Belgede hız sınırı veya kullanım şartı yoktur; bu yüzden istekler arası en az 1 sn beklenir.
Notlar:
- `limit` yalnız 10/20/50/100 kabul eder; en yakın üst değer istenip sonuç kesilir.
- `orderTitle` boşlukları yutar; başlık `abstracts[].title`'dan alınır.
- Tüm sorgu terimleri birlikte aranır (AND): ≥4 terimde çoğunlukla sonuç gelmez. Sonuç boşsa en uzun 3, sonra 2 sözcükle yeniden denenir.
- Arama bulanıktır ("Özselçuk" -> "Selçuk"); eşleştirme verify katmanında yapılır.
"""
from __future__ import annotations

import asyncio
import re
import time

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://search.trdizin.gov.tr/api/defaultSearch/publication/"
DETAIL = "https://search.trdizin.gov.tr/tr/yayin/detay/{id}"
ALLOWED_LIMITS = (10, 20, 50, 100)
MIN_INTERVAL = 1.0

_lock = asyncio.Lock()
_last = 0.0


def _page_limit(n: int) -> int:
    return next((x for x in ALLOWED_LIMITS if x >= max(1, n)), ALLOWED_LIMITS[-1])


def clean_query(q: str) -> str:
    """TR Dizin noktalamalı uzun sorgulara sonuç vermez; noktalama ve tek harfli parçaları at."""
    words = [w for w in re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE).split() if len(w) > 1]
    return " ".join(words)


def to_paper(src: dict) -> Paper:
    abstracts = [a for a in (src.get("abstracts") or []) if a]
    # Türkçe kayıtta Türkçe, yoksa ilk dolu başlık
    chosen = next((a for a in abstracts if a.get("title") and a.get("language") == src.get("language")), None) \
        or next((a for a in abstracts if a.get("title")), {})
    title = (chosen.get("title") or src.get("orderTitle") or "").strip()
    abstract = (chosen.get("abstract") or "").strip() or next(
        ((a.get("abstract") or "").strip() for a in abstracts if a.get("abstract")), None) or None
    authors = [a.get("inPublicationName", "").strip() for a in src.get("authors") or []
               if a.get("duty", "AUTHOR") == "AUTHOR" and a.get("inPublicationName")]
    pid = src.get("id")
    return Paper(
        title=title, authors=authors, year=src.get("publicationYear"),
        venue=(src.get("journal") or {}).get("name"), doi=clean_doi(src.get("doi")),
        abstract=abstract, url=DETAIL.format(id=pid) if pid else None, source="trdizin",
    )


async def _fetch(q: str, limit: int) -> list[dict]:
    global _last
    params = {"q": q, "order": "relevance-DESC", "page": "1", "limit": str(_page_limit(limit))}
    async with _lock:  # istekleri sıraya al, arada en az MIN_INTERVAL bekle
        wait = MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await get(BASE, params=params)
        finally:
            _last = time.monotonic()
    r.raise_for_status()
    return [h["_source"] for h in r.json().get("hits", {}).get("hits", []) if "_source" in h]


def _top_words(q: str, n: int = 3) -> str:
    words = q.split()
    keep = set(sorted(range(len(words)), key=lambda i: -len(words[i]))[:n])
    return " ".join(w for i, w in enumerate(words) if i in keep)


async def search(query: str, limit: int = 10, year_from: int | None = None,
                 year_to: int | None = None) -> list[Paper]:
    q = clean_query(query) or query
    hits = await _fetch(q, limit)
    for n in (3, 2):  # AND semantiği: sonuç boşsa terimleri kademeli azalt
        if hits or len(q.split()) <= n:
            break
        hits = await _fetch(_top_words(q, n), limit)
    papers = [to_paper(s) for s in hits]
    papers = [p for p in papers if p.title
              and (not year_from or (p.year or 0) >= year_from)
              and (not year_to or (p.year or 9999) <= year_to)]
    return papers[:limit]
