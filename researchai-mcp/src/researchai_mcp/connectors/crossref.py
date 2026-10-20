from __future__ import annotations

import re

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://api.crossref.org/works"


def _year(msg: dict) -> int | None:
    for k in ("issued", "published-print", "published-online", "created"):
        parts = (msg.get(k) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def to_paper(msg: dict) -> Paper:
    people = msg.get("author") or msg.get("editor") or []
    authors = [", ".join(x for x in (p.get("family"), p.get("given")) if x) for p in people]
    abstract = re.sub(r"<[^>]+>", "", msg.get("abstract") or "") or None
    return Paper(
        title=" ".join(msg.get("title") or [""]).strip(),
        authors=authors, year=_year(msg),
        venue=(msg.get("container-title") or [None])[0],
        doi=clean_doi(msg.get("DOI")), abstract=abstract,
        url=msg.get("URL"), source="crossref",
    )


async def lookup_doi(doi: str) -> Paper | None:
    r = await get(f"{BASE}/{doi}")  # '/' kodlanmamalı
    if r.status_code != 200:
        return None
    return to_paper(r.json()["message"])


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params = {"query.bibliographic": query, "rows": str(limit)}
    flt = []
    if year_from:
        flt.append(f"from-pub-date:{year_from}")
    if year_to:
        flt.append(f"until-pub-date:{year_to}")
    if flt:
        params["filter"] = ",".join(flt)
    r = await get(BASE, params=params)
    r.raise_for_status()
    return [to_paper(m) for m in r.json()["message"]["items"]]
