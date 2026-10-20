"""DergiPark yerel dizini: OAI-PMH kayıtlarını ayrıştırır, SQLite FTS5'te saklar ve arar.

OAI-PMH bir toplama protokolüdür (anahtar kelimeyle arama yok); bu yüzden kayıtlar önce
`researchai-harvest` ile yerel dizine çekilir, arama yerelde yapılır.
Dizin yolu: RESEARCHAI_DB ortam değişkeni, varsayılan ./data/dergipark.sqlite
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path

from ..models import Paper
from ..normalize import clean_doi, norm

O = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_DOI = re.compile(r"doi\.org/(10\.\S+)", re.I)
_JOURNAL = re.compile(r"dergipark\.org\.tr/(?:\w\w/)?pub/([^/\s?#]+)", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  oai_id TEXT UNIQUE NOT NULL, datestamp TEXT, journal TEXT, source TEXT, publisher TEXT,
  year INTEGER, doi TEXT, url TEXT, language TEXT,
  titles TEXT, authors TEXT, subjects TEXT, abstract TEXT
);
CREATE INDEX IF NOT EXISTS records_journal ON records(journal);
CREATE INDEX IF NOT EXISTS records_year ON records(year);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS windows (
  win_from TEXT, win_until TEXT, filt TEXT, status TEXT, pages INTEGER, records INTEGER, finished_at TEXT,
  PRIMARY KEY (win_from, win_until, filt)
);
"""


def db_path() -> Path:
    return Path(os.environ.get("RESEARCHAI_DB", "data/dergipark.sqlite"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def available(path: Path | None = None) -> bool:
    path = path or db_path()
    if not path.exists():
        return False
    try:
        with closing(sqlite3.connect(path)) as con:
            return con.execute("SELECT 1 FROM records LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False


def _texts(rec: ET.Element, tag: str) -> list[tuple[str, str]]:
    out = []
    for e in rec.iter(DC + tag):
        t = (e.text or "").strip()
        if t:
            out.append((e.get(XML_LANG, ""), t))
    return out


def _year(date: str) -> int | None:
    """dc:date'in ilk 4 hanesi; DergiPark'ta 0201, 1067 gibi bozuk tarihler var, makul aralık dışı None."""
    y = int(date[:4]) if date[:4].isdigit() else None
    return y if y and 1900 <= y <= 2100 else None


def parse_record(rec: ET.Element) -> dict | None:
    """<record> -> sözlük. Silinmiş/metadatasız kayıtlar için None."""
    header = rec.find(O + "header")
    if header is None or header.get("status") == "deleted" or rec.find(O + "metadata") is None:
        return None
    titles = [t for _, t in _texts(rec, "title")]
    if not titles:
        return None
    ids = [t for _, t in _texts(rec, "identifier")] + [t for _, t in _texts(rec, "relation")]
    doi = next((clean_doi(m.group(1)) for i in ids if (m := _DOI.search(i))), None)
    url = next((i for i in ids if "/article/" in i and "dergipark.org.tr" in i), None)
    journal = next((m.group(1).lower() for i in ids if (m := _JOURNAL.search(i))), None)
    date = (_texts(rec, "date") or [("", "")])[0][1]
    descs = _texts(rec, "description")
    abstract = next((t for l, t in descs if l.lower().startswith("tr")), None) or (descs[0][1] if descs else None)
    return {
        "oai_id": header.findtext(O + "identifier", "").strip(),
        "datestamp": header.findtext(O + "datestamp", "").strip(),
        "journal": journal, "source": (_texts(rec, "source") or [("", None)])[0][1],
        "publisher": (_texts(rec, "publisher") or [("", None)])[0][1],
        "year": _year(date), "doi": doi, "url": url,
        "language": (_texts(rec, "language") or [("", None)])[0][1],
        "titles": titles, "authors": [t for _, t in _texts(rec, "creator")],
        "subjects": [t for _, t in _texts(rec, "subject")], "abstract": abstract,
    }


def upsert(con: sqlite3.Connection, r: dict) -> None:
    row = con.execute("SELECT rowid FROM records WHERE oai_id=?", (r["oai_id"],)).fetchone()
    vals = (r["datestamp"], r["journal"], r["source"], r["publisher"], r["year"], r["doi"], r["url"],
            r["language"], json.dumps(r["titles"], ensure_ascii=False),
            json.dumps(r["authors"], ensure_ascii=False), " | ".join(r["subjects"]), r["abstract"])
    text = norm(" ".join([*r["titles"], *r["authors"], *r["subjects"], r["abstract"] or ""]))
    if row:
        rid = row["rowid"]
        con.execute("UPDATE records SET datestamp=?, journal=?, source=?, publisher=?, year=?, doi=?, url=?,"
                    " language=?, titles=?, authors=?, subjects=?, abstract=? WHERE rowid=?", (*vals, rid))
        con.execute("DELETE FROM fts WHERE rowid=?", (rid,))
    else:
        rid = con.execute("INSERT INTO records (oai_id, datestamp, journal, source, publisher, year, doi, url,"
                          " language, titles, authors, subjects, abstract) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (r["oai_id"], *vals)).lastrowid
    con.execute("INSERT INTO fts(rowid, text) VALUES (?,?)", (rid, text))


def _fts_query(query: str, mode: str) -> str:
    terms = [w for w in norm(query).split() if len(w) > 1]
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms]
    return (" AND " if mode == "and" else " OR ").join(quoted)


def _row_to_paper(row: sqlite3.Row) -> Paper:
    titles = json.loads(row["titles"])
    return Paper(title=titles[0], alt_titles=titles[1:], authors=json.loads(row["authors"]), year=row["year"],
                 venue=row["source"], doi=row["doi"], abstract=row["abstract"], url=row["url"], source="dergipark")


def search_sync(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None,
                path: Path | None = None) -> list[Paper]:
    q_and, q_or = _fts_query(query, "and"), _fts_query(query, "or")
    if not q_and:
        return []
    with closing(connect(path)) as con:
        for q in dict.fromkeys([q_and, q_or]):  # AND, boşsa OR (bm25 sıralı)
            sql = ("SELECT r.* FROM fts JOIN records r ON r.rowid = fts.rowid WHERE fts MATCH ?"
                   " AND (? IS NULL OR r.year >= ?) AND (? IS NULL OR r.year <= ?) ORDER BY bm25(fts) LIMIT ?")
            rows = con.execute(sql, (q, year_from, year_from, year_to, year_to, limit)).fetchall()
            if rows:
                return [_row_to_paper(r) for r in rows]
    return []


async def search(query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    if not available():
        raise RuntimeError("DergiPark yerel dizini boş; önce `researchai-harvest` ile doldurun")
    return await asyncio.to_thread(search_sync, query, limit, year_from, year_to)
