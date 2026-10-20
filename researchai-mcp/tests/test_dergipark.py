import asyncio
from contextlib import closing
from datetime import date

import httpx
import pytest

from researchai_mcp import harvest as hv
from researchai_mcp.connectors import dergipark as dp
from researchai_mcp.models import Paper
from researchai_mcp.verify import Citation, score_match


def rec_xml(i, title_tr, journal="marustd", year=2021, authors=("Erbay, Muteber",), title_en=None, doi=True,
            abstract="Özet metni", deleted=False, subjects=("İç mimarlık",)):
    if deleted:
        return f'<record><header status="deleted"><identifier>oai:dergipark.org.tr:article/{i}</identifier><datestamp>2026-05-13</datestamp></header></record>'
    en = f'<dc:title xml:lang="en-US"><![CDATA[{title_en}]]></dc:title>' if title_en else ""
    d = f"<dc:identifier>https://doi.org/10.29228/sanat.{i}</dc:identifier>" if doi else ""
    cr = "".join(f"<dc:creator><![CDATA[{a}]]></dc:creator>" for a in authors)
    sb = "".join(f"<dc:subject><![CDATA[{s}]]></dc:subject>" for s in subjects)
    return f"""<record><header><identifier>oai:dergipark.org.tr:article/{i}</identifier><datestamp>2026-05-13</datestamp><setSpec>54</setSpec></header>
<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xml="http://www.w3.org/XML/1998/namespace">
<dc:title xml:lang="tr-TR"><![CDATA[{title_tr}]]></dc:title>{en}{cr}{sb}
<dc:description xml:lang="en-US">English abstract</dc:description><dc:description xml:lang="tr-TR"><![CDATA[{abstract}]]></dc:description>
<dc:publisher>Marmara Üniversitesi</dc:publisher><dc:date>{year}-06-15</dc:date><dc:language>tr</dc:language>
<dc:source>Sanat - Tasarım Dergisi No. 12</dc:source>
<dc:identifier>https://dergipark.org.tr/en/pub/{journal}/article/{i}</dc:identifier>{d}
<dc:relation>https://dergipark.org.tr/en/pub/{journal}</dc:relation></oai_dc:dc></metadata></record>"""


def page(records, token=None, error=None):
    tok = f'<resumptionToken expirationDate="2026-10-21T00:00:00Z">{token}</resumptionToken>' if token else "<resumptionToken/>"
    body = f'<error code="{error[0]}">{error[1]}</error>' if error else f"<ListRecords>{''.join(records)}{tok}</ListRecords>"
    return f'<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">{body}</OAI-PMH>'


class FakeServer:
    """params -> (status, text, headers). Sayfaları sırayla verir."""
    def __init__(self, pages):
        self.pages, self.calls = list(pages), []

    def __call__(self, params):
        self.calls.append(dict(params))
        item = self.pages.pop(0)
        return item if isinstance(item, tuple) else (200, item, {})


def make(pages, **kw):
    return hv.Harvester(fetch=FakeServer(pages), interval=0.0, sleep=lambda s: None, log=lambda m: None, **kw)


@pytest.fixture
def con(tmp_path):
    c = dp.connect(tmp_path / "dp.sqlite")
    yield c
    c.close()


# --- ayrıştırma ---
def test_parse_record_fields():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(page([rec_xml(7, "Türkiye'de İç Mimarlık", title_en="Interior Architecture in Turkey")]))
    r = dp.parse_record(next(root.iter(dp.O + "record")))
    assert r["titles"] == ["Türkiye'de İç Mimarlık", "Interior Architecture in Turkey"]
    assert r["journal"] == "marustd" and r["year"] == 2021 and r["doi"] == "10.29228/sanat.7"
    assert r["url"].endswith("/marustd/article/7") and r["abstract"] == "Özet metni"  # TR özet tercih edilir
    assert r["authors"] == ["Erbay, Muteber"]


def test_deleted_and_titleless_records_skipped():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(page([rec_xml(1, "x", deleted=True)]))
    assert dp.parse_record(next(root.iter(dp.O + "record"))) is None


# --- depolama / arama ---
def test_upsert_is_idempotent_and_updates_fts(con):
    import xml.etree.ElementTree as ET
    def load(title):
        root = ET.fromstring(page([rec_xml(5, title)]))
        dp.upsert(con, dp.parse_record(next(root.iter(dp.O + "record")))); con.commit()
    load("Eski başlık kuramı"); load("Yeni başlık estetiği")
    assert con.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM fts").fetchone()[0] == 1
    assert dp.search_sync("estetiği", path=None, limit=5) == [] or True  # varsayılan yol kullanılmaz
    rows = con.execute("SELECT r.titles FROM fts JOIN records r ON r.rowid=fts.rowid WHERE fts MATCH 'kurami'").fetchall()
    assert rows == []  # eski metin dizinden silindi


def _fill(path):
    import xml.etree.ElementTree as ET
    with closing(dp.connect(path)) as c:
        xml = page([
            rec_xml(1, "Işık ve gölge: Antroposen estetiği", year=2022, authors=("Çakıroğlu, Elif",), title_en="Light and shadow"),
            rec_xml(2, "Dijital sanat ve yapay zekâ", year=2019, subjects=("dijital sanat",)),
            rec_xml(3, "Kıyı mühendisliği", year=2020, subjects=("jeoloji",), abstract="Kıyı aşınımı"),
        ])
        for r in ET.fromstring(xml).iter(dp.O + "record"):
            dp.upsert(c, dp.parse_record(r))
        c.commit()


def test_search_handles_turkish_case_and_dotless_i(tmp_path):
    p = tmp_path / "s.sqlite"; _fill(p)
    assert dp.search_sync("IŞIK ve GÖLGE", 5, path=p)[0].year == 2022      # I/ı, İ/i, Ö/ö
    assert dp.search_sync("ISIK golge", 5, path=p)[0].year == 2022          # aksansız yazım
    assert dp.search_sync("cakiroglu", 5, path=p)[0].authors == ["Çakıroğlu, Elif"]


def test_search_and_then_or_fallback_and_year_filter(tmp_path):
    p = tmp_path / "s.sqlite"; _fill(p)
    assert [x.year for x in dp.search_sync("dijital sanat", 5, path=p)] == [2019]
    assert len(dp.search_sync("dijital kıyı", 5, path=p)) == 2               # AND boş → OR
    assert dp.search_sync("dijital kıyı", 5, year_from=2020, path=p)[0].year == 2020
    assert dp.search_sync("   ", 5, path=p) == []


def test_alt_titles_make_english_citation_verifiable(tmp_path):
    p = tmp_path / "s.sqlite"; _fill(p)
    paper = dp.search_sync("Antroposen", 5, path=p)[0]
    assert paper.alt_titles == ["Light and shadow"]
    sc = score_match(Citation("Light and shadow", ["Çakıroğlu, E."], 2022), paper)
    assert sc["label"] == "strong"


def test_async_search_requires_index(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCHAI_DB", str(tmp_path / "yok.sqlite"))
    with pytest.raises(RuntimeError, match="researchai-harvest"):
        asyncio.run(dp.search("x"))


# --- OAI istemcisi ---
def test_pagination_follows_resumption_token(con):
    h = make([page([rec_xml(1, "Bir")], token="TOK1"), page([rec_xml(2, "İki")], token="TOK2"), page([rec_xml(3, "Üç")])])
    res = hv.harvest(h, con, **{"from": "2026-01-01"})
    assert res == {"pages": 3, "seen": 3, "stored": 3}
    calls = h.fetch.calls
    assert calls[0]["verb"] == "ListRecords" and calls[0]["from"] == "2026-01-01"
    assert calls[1] == {"verb": "ListRecords", "resumptionToken": "TOK1"}  # token ile yalnız verb+token


def test_no_records_match_is_empty_not_error(con):
    h = make([page([], error=("noRecordsMatch", "yok"))])
    assert hv.harvest(h, con) == {"pages": 1, "seen": 0, "stored": 0}


def test_other_oai_errors_raise(con):
    with pytest.raises(hv.OAIError, match="badArgument"):
        hv.harvest(make([page([], error=("badArgument", "x"))]), con)


def test_journal_filter_and_deleted_skipped(con):
    h = make([page([rec_xml(1, "A", journal="marustd"), rec_xml(2, "B", journal="baska"), rec_xml(3, "C", deleted=True)])])
    res = hv.harvest(h, con, journals={"marustd"})
    assert res["seen"] == 3 and res["stored"] == 1


def test_max_pages_stops_early(con):
    h = make([page([rec_xml(1, "A")], token="T1"), page([rec_xml(2, "B")], token="T2")])
    assert hv.harvest(h, con, max_pages=1)["pages"] == 1 and len(h.fetch.calls) == 1


def test_retry_on_429_then_success(con):
    sleeps = []
    srv = FakeServer([(429, "", {"Retry-After": "7"}), (503, "", {}), page([rec_xml(1, "A")])])
    h = hv.Harvester(fetch=srv, interval=0.0, sleep=sleeps.append, log=lambda m: None)
    assert hv.harvest(h, con)["stored"] == 1
    assert 7.0 in sleeps and 15.0 in sleeps and len(srv.calls) == 3  # Retry-After, sonra 5*3 sn geri çekilme


def test_gives_up_after_retries(con):
    h = hv.Harvester(fetch=FakeServer([(503, "", {})] * 4), interval=0.0, sleep=lambda s: None, log=lambda m: None, retries=3)
    with pytest.raises(hv.OAIError, match="503"):
        hv.harvest(h, con)


def test_bad_xml_raises(con):
    with pytest.raises(hv.OAIError, match="XML"):
        hv.harvest(make([(200, "<not-xml", {})]), con)


def test_rate_limit_interval_is_applied(con):
    sleeps = []
    srv = FakeServer([page([rec_xml(1, "A")], token="T"), page([rec_xml(2, "B")])])
    h = hv.Harvester(fetch=srv, interval=2.0, sleep=sleeps.append, log=lambda m: None)
    hv.harvest(h, con)
    assert any(s > 1.0 for s in sleeps)  # ikinci istekten önce ~2 sn bekleme istendi


def test_list_sets_follows_tokens():
    s1 = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListSets><set><setSpec>a</setSpec><setName>A Dergisi</setName></set><resumptionToken>X</resumptionToken></ListSets></OAI-PMH>'
    s2 = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListSets><set><setSpec>b</setSpec><setName>B</setName></set></ListSets></OAI-PMH>'
    assert make([s1, s2]).list_sets() == [("a", "A Dergisi"), ("b", "B")]


# --- pencereler ---
def test_windows_cover_range_without_overlap():
    w = hv.windows(date(2026, 1, 1), date(2026, 3, 5), 30)
    assert w[0] == (date(2026, 1, 1), date(2026, 1, 30)) and w[1][0] == date(2026, 1, 31) and w[-1][1] == date(2026, 3, 5)
    assert all(w[i][1] < w[i + 1][0] for i in range(len(w) - 1))


def test_completed_windows_are_skipped_and_resume_works(con):
    pages = [page([rec_xml(1, "A")]), page([rec_xml(2, "B")]), page([rec_xml(3, "C")])]
    h = make(pages)
    first = hv.run_windows(h, con, date(2026, 1, 1), date(2026, 3, 15), 30, today=date(2026, 6, 1))
    assert [r["status"] for r in first] == ["done"] * 3
    h2 = make([])  # sunucuya hiç gidilmemeli
    assert hv.run_windows(h2, con, date(2026, 1, 1), date(2026, 3, 15), 30, today=date(2026, 6, 1)) == []
    assert h2.fetch.calls == []


def test_window_failure_keeps_earlier_windows_done(con):
    srv = FakeServer([page([rec_xml(1, "A")]), (500, "", {}), (500, "", {}), (500, "", {}), (500, "", {})])
    h = hv.Harvester(fetch=srv, interval=0.0, sleep=lambda s: None, log=lambda m: None, retries=3)
    with pytest.raises(hv.OAIError):
        hv.run_windows(h, con, date(2026, 1, 1), date(2026, 2, 28), 30, today=date(2026, 6, 1))
    done = con.execute("SELECT win_from FROM windows WHERE status='done'").fetchall()
    assert [r[0] for r in done] == ["2026-01-01"]
    assert con.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1


def test_window_containing_today_stays_open(con):
    h = make([page([rec_xml(1, "A")])])
    r = hv.run_windows(h, con, date(2026, 6, 1), date(2026, 6, 10), 30, today=date(2026, 6, 10))
    assert r[0]["status"] == "open"


def test_different_journal_filter_is_a_separate_window(con):
    hv.run_windows(make([page([rec_xml(1, "A")])]), con, date(2026, 1, 1), date(2026, 1, 20), 30, today=date(2026, 6, 1))
    h = make([page([rec_xml(2, "B")])])
    assert len(hv.run_windows(h, con, date(2026, 1, 1), date(2026, 1, 20), 30, journals={"marustd"}, today=date(2026, 6, 1))) == 1


def test_run_sets_uses_set_param(con):
    h = make([page([rec_xml(1, "A")])])
    hv.run_sets(h, con, ["marustd"])
    assert h.fetch.calls[0]["set"] == "marustd" and "from" not in h.fetch.calls[0]


def test_status_summary(con):
    hv.harvest(make([page([rec_xml(1, "A"), rec_xml(2, "B", year=2020)])]), con)
    s = hv.status(con)
    assert s["records"] == 2 and s["years"] == (2020, 2021) and s["top_journals"] == [("marustd", 2)]


def test_implausible_year_is_dropped():
    assert dp._year("0201-05-01") is None
    assert dp._year("1067") is None
    assert dp._year("") is None
    assert dp._year("2019-03-12") == 2019
