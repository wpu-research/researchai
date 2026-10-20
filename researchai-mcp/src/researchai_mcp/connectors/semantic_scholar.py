from __future__ import annotations

import os

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,venue,externalIds,abstract,url,openAccessPdf"


def to_paper(p: dict) -> Paper:
    return Paper(
        title=(p.get("title") or "").strip(),
        authors=[a.get("name", "") for a in p.get("authors") or []],
        year=p.get("year"), venue=p.get("venue") or None,
        doi=clean_doi((p.get("externalIds") or {}).get("DOI")),
        abstract=p.get("abstract"), url=p.get("url"), source="semantic_scholar",
        oa_url=(p.get("openAccessPdf") or {}).get("url"),
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params = {"query": query, "limit": str(limit), "fields": FIELDS}
    if year_from or year_to:
        params["year"] = f"{year_from or ''}-{year_to or ''}"
    headers = {}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    r = await get(BASE, params=params, headers=headers)
    r.raise_for_status()
    return [to_paper(p) for p in r.json().get("data", [])]
