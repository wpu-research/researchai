"""Europe PMC: PubMed/MEDLINE, PMC ve ön baskılar (yaşam bilimleri, tıp, psikoloji)."""
from __future__ import annotations

import re

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def to_paper(d: dict) -> Paper:
    authors = [a.get("fullName", "") for a in (d.get("authorList") or {}).get("author", [])]
    venue = (((d.get("journalInfo") or {}).get("journal") or {}).get("title"))
    abstract = re.sub(r"<[^>]+>", " ", d.get("abstractText") or "")
    pmcid = d.get("pmcid")
    return Paper(
        title=(d.get("title") or "").strip().rstrip("."),
        authors=[a for a in authors if a],
        year=int(d["pubYear"]) if str(d.get("pubYear", "")).isdigit() else None,
        venue=venue or ("Preprint" if d.get("source") == "PPR" else None),
        doi=clean_doi(d.get("doi")), abstract=" ".join(abstract.split()) or None,
        url=f"https://europepmc.org/article/{d.get('source')}/{d.get('id')}", source="europepmc",
        oa_url=f"https://europepmc.org/article/PMC/{pmcid}" if pmcid else None,
    )


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    q = query
    if year_from or year_to:
        q += f" AND PUB_YEAR:[{year_from or 1800} TO {year_to or 3000}]"
    r = await get(BASE, params={"query": q, "format": "json", "pageSize": str(limit), "resultType": "core"})
    r.raise_for_status()
    return [to_paper(d) for d in (r.json().get("resultList") or {}).get("result", [])]
