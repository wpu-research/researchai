"""HAL: Fransa merkezli çok disiplinli açık arşiv (beşeri/sosyal bilimler dahil)."""
from __future__ import annotations

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://api.archives-ouvertes.fr/search/"
FIELDS = "title_s,authFullName_s,producedDateY_i,doiId_s,abstract_s,uri_s,journalTitle_s,fileMain_s"


def to_paper(d: dict) -> Paper:
    titles = d.get("title_s") or [""]
    return Paper(
        title=titles[0].strip(), authors=d.get("authFullName_s") or [], year=d.get("producedDateY_i"),
        venue=d.get("journalTitle_s"), doi=clean_doi(d.get("doiId_s")),
        abstract=(d.get("abstract_s") or [None])[0], url=d.get("uri_s"), source="hal",
        oa_url=d.get("fileMain_s"), alt_titles=titles[1:],
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params = {"q": query, "wt": "json", "rows": str(limit), "fl": FIELDS}
    if year_from or year_to:
        params["fq"] = f"producedDateY_i:[{year_from or '*'} TO {year_to or '*'}]"
    r = await get(BASE, params=params)
    r.raise_for_status()
    return [to_paper(d) for d in (r.json().get("response") or {}).get("docs", [])]
