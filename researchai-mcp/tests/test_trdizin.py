import asyncio
import json
import time

import httpx

from researchai_mcp.connectors import trdizin
from researchai_mcp.verify import Citation, verify_citation


def run(coro):
    return asyncio.run(coro)


def hit(i, title, year, doi=None, authors=("Ayşe Yılmaz",), lang="TUR", order_title=None):
    return {"_source": {
        "id": i, "publicationYear": year, "doi": doi, "language": lang,
        "orderTitle": order_title or title.replace(" ", "", 1),  # gerçek veride boşluk yutulur
        "abstracts": [{"title": "English title", "abstract": "en abstract", "language": "ENG"},
                      {"title": title, "abstract": "özet", "language": "TUR"}],
        "authors": [{"inPublicationName": a, "duty": "AUTHOR"} for a in authors]
                   + [{"inPublicationName": "Editor X", "duty": "EDITOR"}],
        "journal": {"name": "Art-e Sanat Dergisi", "eissn": "2564-6745"},
    }}


def fake_get(hits, calls):
    async def f(url, params=None, headers=None, **kw):
        calls.append((time.monotonic(), params))
        body = {"hits": {"total": {"value": len(hits)}, "hits": hits}}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))
    return f


def test_to_paper_uses_abstract_title_and_filters_editors():
    p = trdizin.to_paper(hit(7, "Sanat ve tasarım alanında üretken yapay zeka", 2024, "10.21602/X.1")["_source"])
    assert p.title == "Sanat ve tasarım alanında üretken yapay zeka"  # orderTitle değil
    assert p.doi == "10.21602/x.1" and p.year == 2024 and p.source == "trdizin"
    assert p.authors == ["Ayşe Yılmaz"] and p.venue == "Art-e Sanat Dergisi"
    assert p.url.endswith("/detay/7") and p.abstract == "özet"


def test_title_falls_back_to_order_title():
    src = {"id": 1, "orderTitle": "Yalnız Sıralama Başlığı", "abstracts": [], "authors": []}
    assert trdizin.to_paper(src).title == "Yalnız Sıralama Başlığı"


def test_limit_maps_to_allowed_values():
    assert [trdizin._page_limit(n) for n in (1, 10, 11, 20, 21, 51, 500)] == [10, 10, 20, 20, 50, 100, 100]


def test_search_slices_and_filters_year(monkeypatch):
    calls = []
    hits = [hit(i, f"Başlık {i} sanat", 2018 + i) for i in range(6)]
    monkeypatch.setattr(trdizin, "get", fake_get(hits, calls))
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    out = run(trdizin.search("sanat", limit=3, year_from=2020))
    assert [p.year for p in out] == [2020, 2021, 2022]
    assert calls[0][1]["limit"] == "10" and calls[0][1]["q"] == "sanat" and calls[0][1]["order"] == "relevance-DESC"


def test_requests_are_spaced(monkeypatch):
    calls = []
    monkeypatch.setattr(trdizin, "get", fake_get([], calls))
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.3)
    trdizin._last = 0.0

    async def both():
        await asyncio.gather(trdizin.search("a"), trdizin.search("b"))
    run(both())
    assert calls[1][0] - calls[0][0] >= 0.25


def test_http_error_raises(monkeypatch):
    async def bad(url, params=None, headers=None, **kw):
        return httpx.Response(503, request=httpx.Request("GET", url))
    monkeypatch.setattr(trdizin, "get", bad)
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    try:
        run(trdizin.search("x"))
        assert False, "hata beklenirdi"
    except httpx.HTTPStatusError:
        pass


def test_verify_turkish_citation_via_trdizin(monkeypatch):
    calls = []
    monkeypatch.setattr(trdizin, "get", fake_get(
        [hit(1, "Sanat ve tasarım alanında üretken yapay zeka sistemleri", 2024, authors=("Cumhur Coşkun",))], calls))
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)

    async def nothing(q, l, a, b):
        return []

    async def lookup(doi):
        return None
    cit = Citation("Sanat ve tasarım alanında üretken yapay zeka sistemleri", ["Coşkun, C."], 2024)
    r = run(verify_citation(cit, lookup=lookup, searchers={"crossref": nothing, "trdizin": trdizin.search}))
    assert r["status"] == "verified" and r["evidence"][0]["source"] == "trdizin"


def test_clean_query_strips_punctuation_and_initials():
    q = "Antroposen çağında ekolojik sanat: David Buckland, Mel Chin'in projeleri Çakıroğlu, E."
    c = trdizin.clean_query(q)
    assert ":" not in c and "," not in c and "'" not in c and " E " not in f" {c} "
    assert "Çakıroğlu" in c and "Chin in" in c


def test_search_sends_cleaned_query(monkeypatch):
    calls = []
    monkeypatch.setattr(trdizin, "get", fake_get([], calls))
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    run(trdizin.search("Tasarımda yeni yaklaşımlar: Refik Anadol, Çelenk, A."))
    assert calls[0][1]["q"] == "Tasarımda yeni yaklaşımlar Refik Anadol Çelenk"


def test_empty_result_retries_with_fewer_terms(monkeypatch):
    seen = []

    async def f(url, params=None, headers=None, **kw):
        seen.append(params["q"])
        hits = [] if len(params["q"].split()) > 3 else [hit(1, "Antroposen estetiği", 2022)]
        return httpx.Response(200, json={"hits": {"hits": hits}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(trdizin, "get", f)
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    out = run(trdizin.search("antroposen dijital sanat estetik"))
    assert len(seen) == 2 and len(seen[1].split()) == 3 and len(out) == 1


def test_no_retry_when_query_already_short(monkeypatch):
    seen = []

    async def f(url, params=None, headers=None, **kw):
        seen.append(params["q"])
        return httpx.Response(200, json={"hits": {"hits": []}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(trdizin, "get", f)
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    assert run(trdizin.search("antroposen sanat")) == [] and len(seen) == 1


def test_fallback_goes_down_to_two_terms(monkeypatch):
    seen = []

    async def f(url, params=None, headers=None, **kw):
        seen.append(params["q"])
        hits = [hit(1, "Dijital Antroposen", 2022)] if len(params["q"].split()) == 2 else []
        return httpx.Response(200, json={"hits": {"hits": hits}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(trdizin, "get", f)
    monkeypatch.setattr(trdizin, "MIN_INTERVAL", 0.0)
    out = run(trdizin.search("antroposen dijital sanat estetik"))
    assert [len(x.split()) for x in seen] == [4, 3, 2] and len(out) == 1
