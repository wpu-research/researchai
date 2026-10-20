"""ERIC (ABD Eğitim Bakanlığı): eğitim bilimleri dergi makaleleri ve raporları."""
from __future__ import annotations

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://api.ies.ed.gov/eric/"
FIELDS = "id,title,author,publicationdateyear,description,source,url"


def to_paper(d: dict) -> Paper:
    eid = d.get("id", "")
    return Paper(
        title=(d.get("title") or "").strip(),
        authors=d.get("author") or [],
        year=d.get("publicationdateyear"),
        venue=d.get("source"), doi=clean_doi(d.get("url") if "doi.org" in (d.get("url") or "") else None),
        abstract=d.get("description"), url=f"https://eric.ed.gov/?id={eid}" if eid else None, source="eric",
        oa_url=f"https://files.eric.ed.gov/fulltext/{eid}.pdf" if eid.startswith("ED") else None,
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    r = await get(BASE, params={"search": query, "format": "json", "rows": str(limit), "fields": FIELDS})
    r.raise_for_status()
    papers = [to_paper(d) for d in (r.json().get("response") or {}).get("docs", [])]
    return [p for p in papers if (not year_from or (p.year or 0) >= year_from)
            and (not year_to or (p.year or 9999) <= year_to)]
