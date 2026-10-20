from __future__ import annotations

import xml.etree.ElementTree as ET

from ..http import get
from ..models import Paper
from ..normalize import clean_doi

BASE = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def parse(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall("a:entry", NS):
        title = " ".join((e.findtext("a:title", "", NS) or "").split())
        published = e.findtext("a:published", "", NS) or ""
        doi = e.findtext("x:doi", None, NS)
        link = e.findtext("a:id", None, NS)
        out.append(Paper(
            title=title,
            authors=[a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue="arXiv", doi=clean_doi(doi),
            abstract=" ".join((e.findtext("a:summary", "", NS) or "").split()) or None,
            url=link, source="arxiv", oa_url=link,
        ))
    return out


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    r = await get(BASE, params={"search_query": f"all:{query}", "max_results": str(limit),
                                "sortBy": "relevance"})
    r.raise_for_status()
    papers = parse(r.text)
    return [p for p in papers if (not year_from or (p.year or 0) >= year_from)
            and (not year_to or (p.year or 9999) <= year_to)]
