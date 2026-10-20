from __future__ import annotations

import os

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://api.openalex.org/works"


def _abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos)) or None


def to_paper(w: dict) -> Paper:
    loc = w.get("primary_location") or {}
    return Paper(
        title=(w.get("title") or w.get("display_name") or "").strip(),
        authors=[(a.get("author") or {}).get("display_name", "") for a in w.get("authorships") or []],
        year=w.get("publication_year"),
        venue=((loc.get("source") or {}).get("display_name")),
        doi=clean_doi(w.get("doi")), abstract=_abstract(w.get("abstract_inverted_index")),
        url=w.get("id"), source="openalex",
        oa_url=((w.get("open_access") or {}).get("oa_url")),
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params = {"search": query, "per-page": str(limit)}
    flt = []
    if year_from:
        flt.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        flt.append(f"to_publication_date:{year_to}-12-31")
    if flt:
        params["filter"] = ",".join(flt)
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    r = await get(BASE, params=params)
    r.raise_for_status()
    return [to_paper(w) for w in r.json().get("results", [])]
