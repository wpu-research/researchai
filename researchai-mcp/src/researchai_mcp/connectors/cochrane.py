"""Cochrane Sistematik Derlemeler Veritabanı (CDSR), Europe PMC dizini üzerinden."""
from __future__ import annotations

from . import europepmc
from ..models import Paper

JOURNAL = 'JOURNAL:"Cochrane Database Syst Rev"'


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    papers = await europepmc.query(f"TITLE_ABS:({query}) AND {JOURNAL}", limit, year_from, year_to)
    for p in papers:
        p.source = "cochrane"
        p.venue = "Cochrane Database of Systematic Reviews"
    return papers
