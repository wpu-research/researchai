"""DOAJ: hakemli açık erişim dergilerin makaleleri (tüm alanlar, çok dilli)."""
from __future__ import annotations

from urllib.parse import quote

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://doaj.org/api/search/articles/"


def to_paper(item: dict) -> Paper:
    b = item.get("bibjson") or {}
    doi = next((i.get("id") for i in b.get("identifier") or [] if i.get("type") == "doi"), None)
    link = next((l.get("url") for l in b.get("link") or [] if l.get("type") == "fulltext"), None)
    year = b.get("year")
    return Paper(
        title=(b.get("title") or "").strip(),
        authors=[a.get("name", "") for a in b.get("author") or [] if a.get("name")],
        year=int(year) if str(year or "").isdigit() else None,
        venue=(b.get("journal") or {}).get("title"), doi=clean_doi(doi), abstract=b.get("abstract"),
        url=link or (f"https://doaj.org/article/{item['id']}" if item.get("id") else None),
        source="doaj", oa_url=link,
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    r = await get(BASE + quote(query, safe=""), params={"pageSize": str(limit)})
    r.raise_for_status()
    papers = [to_paper(i) for i in r.json().get("results", [])]
    return [p for p in papers if (not year_from or (p.year or 0) >= year_from)
            and (not year_to or (p.year or 9999) <= year_to)]
