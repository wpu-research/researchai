"""ResearchAI MCP sunucusu (stdio)."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import disclosure
from .search import search_sources as _search
from .verify import Citation, verify_citation as _verify

mcp = MCPServer(
    "researchai",
    instructions=(
        "Akademik kaynak arama, atıf doğrulama ve YZ kullanım beyanı araçları. "
        "verify_citation sahte atıfı kanıtlamaz; uncertain/mismatch/not_found sonuçlarını "
        "kullanıcıya göster, kendi başına silme veya karar verme."
    ),
)


@mcp.tool()
async def search_sources(query: str, sources: list[str] | None = None, limit: int = 10,
                         year_from: int | None = None, year_to: int | None = None) -> dict:
    """Çok kaynaklı akademik arama (openalex, crossref, semantic_scholar, arxiv, trdizin). Sonuçlar
    tekilleştirilir; her satır hangi kaynaklarda bulunduğunu (found_in) taşır. Kaynak hataları
    `errors` içinde döner, diğer kaynaklar etkilenmez."""
    return await _search(query, sources, limit, year_from, year_to)


@mcp.tool()
async def verify_citation(title: str, authors: list[str] | None = None, year: int | None = None,
                          doi: str | None = None) -> dict:
    """Bir atıfı Crossref/OpenAlex/Semantic Scholar/TR Dizin'e karşı doğrular. Çıktı: status
    (verified|uncertain|mismatch|not_found), confidence, evidence, notes. not_found veya
    mismatch, atıfın uydurma olduğunu kanıtlamaz; insan kontrolü gerekir."""
    return await _verify(Citation(title=title, authors=authors or [], year=year, doi=doi))


@mcp.tool()
def log_ai_use(run_id: str, stage: str, tool: str, model: str, purpose: str,
               human_review: bool, notes: str = "") -> dict:
    """Bir aşamada kullanılan YZ aracını koşu günlüğüne kaydeder (runs/<run_id>/ai_use_log.jsonl).
    human_review yalnız insan gerçekten gözden geçirdiyse true olmalı."""
    return disclosure.log_ai_use(run_id, stage, tool, model, purpose, human_review, notes)


@mcp.tool()
def generate_disclosure(run_id: str, language: str = "tr", venue_profile: str | None = None) -> dict:
    """Günlükten YZ kullanım beyanı üretir (tr|en). İnsan incelemesi kaydedilmemiş aşamalar
    beyanda açıkça belirtilir ve warnings içinde döner."""
    return disclosure.generate_disclosure(run_id, language, venue_profile)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
