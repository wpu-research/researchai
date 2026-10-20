"""Çok kaynaklı arama: hata yalıtımlı, tekilleştirilmiş sonuç."""
from __future__ import annotations

import asyncio

from .connectors import arxiv, crossref, dergipark, openalex, semantic_scholar, trdizin
from .models import Paper
from .normalize import dedupe_key

CONNECTORS = {
    "crossref": crossref.search,
    "openalex": openalex.search,
    "semantic_scholar": semantic_scholar.search,
    "arxiv": arxiv.search,
    "trdizin": trdizin.search,
    "dergipark": dergipark.search,
}
DEFAULT_SOURCES = ["openalex", "crossref", "semantic_scholar", "arxiv", "trdizin"]


async def search_sources(query: str, sources: list[str] | None = None, limit: int = 10,
                         year_from: int | None = None, year_to: int | None = None,
                         connectors: dict | None = None) -> dict:
    conns = connectors or CONNECTORS
    names = sources or DEFAULT_SOURCES + (["dergipark"] if conns is CONNECTORS and dergipark.available() else [])
    unknown = [n for n in names if n not in conns]
    names = [n for n in names if n in conns]

    async def run(name: str):
        try:
            return name, await conns[name](query, limit, year_from, year_to), None
        except Exception as ex:  # tek kaynağın hatası diğerlerini düşürmez
            return name, [], f"{type(ex).__name__}: {str(ex)[:120]}"

    done = await asyncio.gather(*(run(n) for n in names))
    merged: dict[str, dict] = {}
    errors: dict[str, str] = {n: "bilinmeyen kaynak" for n in unknown}
    for name, papers, err in done:
        if err:
            errors[name] = err
        for p in papers:
            first = p.authors[0] if p.authors else ""
            key = dedupe_key(p.doi, p.title, first, p.year)
            if key in merged:
                row = merged[key]
                row["found_in"].append(name)
                for f in ("abstract", "oa_url", "venue", "doi"):
                    if not row.get(f) and getattr(p, f):
                        row[f] = getattr(p, f)
            else:
                row = p.to_dict()
                row["found_in"] = [name]
                merged[key] = row
    results = sorted(merged.values(), key=lambda r: -len(r["found_in"]))
    return {"results": results, "errors": errors, "count": len(results)}
