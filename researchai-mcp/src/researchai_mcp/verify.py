"""Atıf doğrulama. Araç sahte atıfı KANITLAMAZ; şüpheyi ve kanıtı gösterir.

Durumlar: verified | uncertain | mismatch | not_found.
uncertain ve mismatch kayıtları otomatik silinmez, insana gösterilir.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .connectors import crossref, dergipark, openalex, semantic_scholar, trdizin
from .models import Paper
from .normalize import authors_match, clean_doi, surname, title_match


@dataclass
class Citation:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None


def score_match(cit: Citation, found: Paper) -> dict:
    t = max(title_match(cit.title, x) for x in [found.title, *found.alt_titles])
    a = authors_match([surname(x) for x in cit.authors], found.authors)
    yd = abs(cit.year - found.year) if cit.year and found.year else None
    diffs = []
    if a is False:
        diffs.append("author_mismatch")
    if yd is not None and yd > 1:
        diffs.append(f"year_differs_by_{yd}")
    if t < 0.8:
        diffs.append(f"title_overlap_{t:.2f}")
    if a is None:
        diffs.append("author_unverifiable")
    strong = t >= 0.8 and a is True and (yd is None or yd <= 1)
    partial = t >= 0.6 and a is not False
    label = "strong" if strong else "partial" if partial else "none"
    return {"label": label, "title": round(t, 2), "author_ok": a, "year_delta": yd, "diffs": diffs}


def _ev(source: str, found: Paper, sc: dict) -> dict:
    return {"source": source, "found_title": found.title[:120], "found_year": found.year,
            "found_authors": found.authors[:3], "doi": found.doi, **sc}


async def verify_citation(cit: Citation, lookup=None, searchers: dict | None = None) -> dict:
    lookup = lookup or crossref.lookup_doi
    default_searchers = {"crossref": crossref.search, "openalex": openalex.search,
                         "semantic_scholar": semantic_scholar.search, "trdizin": trdizin.search}
    searchers_given = searchers is not None
    searchers = searchers if searchers_given else default_searchers
    if not searchers_given and dergipark.available():  # yerel dizin doluysa üçüncü TR kaynağı olarak ekle
        default_searchers["dergipark"] = dergipark.search
    evidence: list[dict] = []
    notes: list[str] = []
    doi = clean_doi(cit.doi)

    if doi:
        found = None
        try:
            found = await lookup(doi)
        except Exception as ex:
            notes.append(f"doi_lookup_error: {type(ex).__name__}")
        if found:
            sc = score_match(cit, found)
            evidence.append(_ev("crossref_doi", found, sc))
            if sc["label"] == "strong":
                return {"status": "verified", "confidence": "high", "evidence": evidence, "notes": notes}
            if sc["label"] == "partial":
                return {"status": "uncertain", "confidence": "low", "evidence": evidence, "notes": notes}
            notes.append("doi_resolves_to_different_work")
            return {"status": "mismatch", "confidence": "medium", "evidence": evidence, "notes": notes}
        notes.append("doi_not_resolved_in_crossref")  # başka kayıt kuruluşunda olabilir, başlık aramasına düş

    query = f"{cit.title} {cit.authors[0] if cit.authors else ''}".strip()

    async def run(name: str, fn):
        try:
            return name, await fn(query, 5, None, None)
        except Exception as ex:
            notes.append(f"{name}_error: {type(ex).__name__}")
            return name, []

    results = await asyncio.gather(*(run(n, f) for n, f in searchers.items()))
    strong_sources, best_partial = set(), None
    for name, papers in results:
        best = None
        for p in papers:
            sc = score_match(cit, p)
            if sc["label"] != "none" and (best is None or sc["title"] > best[1]["title"]):
                best = (p, sc)
        if best:
            evidence.append(_ev(name, *best))
            if best[1]["label"] == "strong":
                strong_sources.add(name)
            else:
                best_partial = best_partial or best
    if strong_sources:
        conf = "high" if len(strong_sources) >= 2 else "medium"
        return {"status": "verified", "confidence": conf, "evidence": evidence, "notes": notes}
    if best_partial:
        return {"status": "uncertain", "confidence": "low", "evidence": evidence, "notes": notes}
    return {"status": "not_found", "confidence": "low", "evidence": evidence,
            "notes": notes + ["not_found_in_searched_sources_does_not_mean_fabricated"]}
