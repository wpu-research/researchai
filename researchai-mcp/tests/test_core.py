import asyncio

import pytest

from researchai_mcp import disclosure
from researchai_mcp.models import Paper
from researchai_mcp.normalize import clean_doi, norm, surname, title_match
from researchai_mcp.search import search_sources
from researchai_mcp.verify import Citation, score_match, verify_citation


def run(coro):
    return asyncio.run(coro)


# --- normalize ---
def test_turkish_normalization():
    assert norm("Çakıroğlu İŞ") == "cakiroglu is"
    assert surname("Çakıroğlu, E.") == "cakiroglu"
    assert surname("Refik Anadol") == "anadol"


def test_clean_doi():
    assert clean_doi("https://doi.org/10.1000/ABC_1.") == "10.1000/abc_1"
    assert clean_doi("doi:10.1000/x") == "10.1000/x"
    assert clean_doi(None) is None


def test_subtitle_dropped_is_full_match():
    assert title_match("Hyperobjects: Philosophy and ecology after the end of the world", "Hyperobjects") == 1.0
    assert title_match("Deep learning for art", "Quantum gravity in black holes") < 0.2


def test_short_subset_title_is_not_a_match():
    assert title_match("The digital sublime: Myth, power, and cyberspace", "Myth and Cyberspace") < 0.6
    assert title_match("The aesthetics of the sublime in recursive pigeon art", "The Aesthetics of the Sublime") < 0.8


def test_bilingual_record_title_matches_turkish_citation():
    cited = "Antroposen çağında ekolojik sanat: David Buckland, Terike Haapoja ve Mel Chin'in ekolojik sanat projeleri"
    found = ("Antroposen Çağında Ekolojik Sanat: David Buckland, Terike Haapoja ve Mel Chin’in Ekolojik Sanat Projeleri "
             "Ecological Art in the Anthropocene: Ecological Art Projects by David Buckland, Terike Haapoja and Mel Chin")
    assert title_match(cited, found) == 1.0
    # kısa atıf başlığı uzun alakasız kayıtta tam eşleşme sayılmamalı
    assert title_match("Atlas of AI", "Atlas of AI and the history of everything in modern data centres worldwide") < 0.8


def test_authorless_record_cannot_be_strong():
    rec = Paper(title="The Digital Sublime", authors=[], year=2004)
    sc = score_match(Citation("The digital sublime: Myth, power, and cyberspace", ["Kowalski, Z."], 2004), rec)
    assert sc["label"] == "partial" and "author_unverifiable" in sc["diffs"]


# --- verify (sahte konektörlerle) ---
REAL = Paper(title="Visual Indeterminacy in GAN Art", authors=["Hertzmann, Aaron"], year=2020, doi="10.1162/leon_a_01930")


def lookup_returning(p):
    async def f(doi):
        return p
    return f


def searcher(*papers):
    async def f(q, limit, y1, y2):
        return list(papers)
    return f


def test_doi_verified():
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020, "10.1162/leon_a_01930")
    r = run(verify_citation(cit, lookup=lookup_returning(REAL), searchers={}))
    assert r["status"] == "verified"


def test_doi_points_to_other_work_is_mismatch():
    other = Paper(title="Thermal PBE in warm dense matter", authors=["Ramakrishna, K."], year=2026)
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020, "10.1/x")
    r = run(verify_citation(cit, lookup=lookup_returning(other), searchers={}))
    assert r["status"] == "mismatch"


def test_changed_author_is_not_verified():
    # Gerçek başlık, yazarı değiştirilmiş atıf: sahte atıfların tipik biçimi
    cit = Citation("Visual indeterminacy in GAN art", ["Smith, J."], 2020)
    r = run(verify_citation(cit, lookup=lookup_returning(None), searchers={"x": searcher(REAL)}))
    assert r["status"] != "verified"


def test_year_off_by_many_is_uncertain():
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2012)
    r = run(verify_citation(cit, lookup=lookup_returning(None), searchers={"x": searcher(REAL)}))
    assert r["status"] == "uncertain"


def test_two_sources_give_high_confidence():
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020)
    r = run(verify_citation(cit, lookup=lookup_returning(None),
                            searchers={"a": searcher(REAL), "b": searcher(REAL)}))
    assert (r["status"], r["confidence"]) == ("verified", "high")


def test_fabricated_is_not_found_with_caveat():
    cit = Citation("Quantum aesthetics of recursive pigeon sublime", ["Nobody, X."], 2019)
    r = run(verify_citation(cit, lookup=lookup_returning(None), searchers={"a": searcher(REAL)}))
    assert r["status"] == "not_found"
    assert any("does_not_mean_fabricated" in n for n in r["notes"])


def test_unresolved_doi_falls_back_to_title_search():
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020, "10.9999/unknown")
    r = run(verify_citation(cit, lookup=lookup_returning(None), searchers={"a": searcher(REAL)}))
    assert r["status"] == "verified" and "doi_not_resolved_in_crossref" in r["notes"]


def test_connector_error_does_not_crash():
    async def boom(q, l, a, b):
        raise RuntimeError("429")
    cit = Citation("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020)
    r = run(verify_citation(cit, lookup=lookup_returning(None), searchers={"bad": boom, "ok": searcher(REAL)}))
    assert r["status"] == "verified" and any("bad_error" in n for n in r["notes"])


def test_score_match_labels():
    assert score_match(Citation("Visual indeterminacy in GAN art", ["Hertzmann"], 2020), REAL)["label"] == "strong"
    assert score_match(Citation("Totally different title here", ["Hertzmann"], 2020), REAL)["label"] == "none"


# --- search ---
def test_search_dedupes_and_isolates_errors():
    async def ok(q, l, a, b):
        return [Paper(title="Same Paper", authors=["A, B."], year=2020, doi="10.1/x")]

    async def ok2(q, l, a, b):
        return [Paper(title="Same Paper", authors=["A, B."], year=2020, doi="10.1/X", abstract="özet")]

    async def bad(q, l, a, b):
        raise RuntimeError("down")
    out = run(search_sources("q", ["a", "b", "c", "zzz"], connectors={"a": ok, "b": ok2, "c": bad}))
    assert out["count"] == 1
    assert sorted(out["results"][0]["found_in"]) == ["a", "b"]
    assert out["results"][0]["abstract"] == "özet"
    assert "c" in out["errors"] and "zzz" in out["errors"]


# --- disclosure ---
@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCHAI_RUNS_DIR", str(tmp_path))
    return tmp_path


def test_run_id_rejects_traversal(runs):
    for bad in ["../x", "a/b", "", "..", "x" * 80]:
        with pytest.raises(ValueError):
            disclosure.run_path(bad)


def test_disclosure_states_unreviewed_stage(runs):
    disclosure.log_ai_use("r1", "literatür", "Claude Code", "claude", "kaynak taraması", True)
    disclosure.log_ai_use("r1", "taslak", "Claude Code", "claude", "metin önerisi", False)
    out = disclosure.generate_disclosure("r1", "tr")
    assert "tüm" not in out["statement_md"].lower() or "gözden geçirilmiş ve doğrulanmıştır" not in out["statement_md"]
    assert "taslak" in out["statement_md"] and "kaydedilmemiştir" in out["statement_md"]
    assert out["warnings"] and "taslak" in out["warnings"][0]


def test_disclosure_all_reviewed(runs):
    disclosure.log_ai_use("r2", "literatür", "Claude Code", "claude", "tarama", True)
    out = disclosure.generate_disclosure("r2", "en")
    assert "reviewed and verified" in out["statement_md"] and out["warnings"] == []


def test_disclosure_empty_log(runs):
    out = disclosure.generate_disclosure("nolog", "tr")
    assert out["warnings"] == ["no_log_entries"]


def test_disclosure_review_covers_earlier_ai_use_in_same_stage(runs):
    disclosure.log_ai_use("r3", "taslak", "ResearchAI", "m1", "metin önerisi", False)
    disclosure.log_ai_use("r3", "taslak", "ResearchAI", "m1", "metin önerisi", False)
    disclosure.log_ai_use("r3", "taslak", "yazar", "", "inceleme ve onay", True)
    disclosure.log_ai_use("r3", "sentez", "ResearchAI", "m1", "boşluk haritası", True)
    disclosure.log_ai_use("r3", "sentez", "ResearchAI", "m1", "yeniden üretim", False)
    out = disclosure.generate_disclosure("r3", "tr")
    assert "incelemesi kaydedilmemiştir: sentez." in out["statement_md"]
    assert "gözden geçirilmiştir: taslak." in out["statement_md"]
    assert out["statement_md"].count("metin önerisi") == 1  # yinelenen kullanım tek satır
    assert "inceleme ve onay" not in out["table_md"]  # modelsiz inceleme kaydı YZ kullanımı değil
