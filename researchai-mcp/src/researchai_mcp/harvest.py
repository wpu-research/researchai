"""DergiPark OAI-PMH toplayıcı (komut satırı: researchai-harvest).

Kurallar: istekler arası varsayılan 2 sn, 429/5xx'te geri çekilme, tanımlayıcı kullanıcı-ajanı,
tarih pencereli ve devam ettirilebilir toplama. Yalnızca /api/public/oai/ kullanılır
(robots.txt yasağı olan /search ve /login'e dokunulmaz).
"""
from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator

import httpx

from .connectors import dergipark as dp
from .http import user_agent

BASE = "https://dergipark.org.tr/api/public/oai/"
O = dp.O


class OAIError(RuntimeError):
    pass


def _http_fetch(params: dict) -> tuple[int, str, dict]:
    r = httpx.get(BASE, params=params, headers={"User-Agent": user_agent()}, timeout=90.0, follow_redirects=True)
    return r.status_code, r.text, dict(r.headers)


class Harvester:
    def __init__(self, fetch: Callable[[dict], tuple[int, str, dict]] | None = None, interval: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep, retries: int = 3, log: Callable[[str], None] = print):
        self.fetch, self.interval, self.sleep, self.retries, self.log = fetch or _http_fetch, interval, sleep, retries, log
        self._last = 0.0
        self.requests = 0

    def _get(self, params: dict) -> ET.Element:
        for attempt in range(self.retries + 1):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                status, text, headers = self.fetch(params)
            except httpx.HTTPError as ex:
                status, text, headers = 599, "", {}
                self.log(f"  ağ hatası ({type(ex).__name__}), yeniden deneniyor")
            if status == 200:
                try:
                    return ET.fromstring(text)
                except ET.ParseError as ex:
                    raise OAIError(f"geçersiz XML: {ex}") from ex
            if status in (429, 503, 599) or status >= 500:
                ra = headers.get("Retry-After", "")
                delay = min(float(ra), 120.0) if ra.isdigit() else 5.0 * (3 ** attempt)
                if attempt < self.retries:
                    self.log(f"  HTTP {status}, {delay:.0f} sn sonra yeniden denenecek")
                    self.sleep(delay)
                    continue
            raise OAIError(f"HTTP {status}")
        raise OAIError("yeniden deneme hakkı bitti")

    def list_sets(self) -> list[tuple[str, str]]:
        out, params = [], {"verb": "ListSets"}
        while True:
            root = self._get(params)
            self._raise_on_error(root)
            out += [(s.findtext(O + "setSpec", "").strip(), s.findtext(O + "setName", "").strip())
                    for s in root.iter(O + "set")]
            tok = root.find(".//" + O + "resumptionToken")
            if tok is None or not (tok.text or "").strip():
                return out
            params = {"verb": "ListSets", "resumptionToken": tok.text.strip()}

    @staticmethod
    def _raise_on_error(root: ET.Element) -> bool:
        """True: kayıt yok (noRecordsMatch, hata değil). Diğer OAI hataları OAIError fırlatır."""
        err = root.find(O + "error")
        if err is None:
            return False
        if err.get("code") == "noRecordsMatch":
            return True
        raise OAIError(f"OAI hatası {err.get('code')}: {(err.text or '').strip()[:120]}")

    def records(self, max_pages: int | None = None, **extra) -> Iterator[tuple[ET.Element | None, int]]:
        """Sayfa sayfa <record> üretir. Her sayfa sonunda (None, sayfa_no) yayınlar."""
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", **{k: v for k, v in extra.items() if v}}
        page = 0
        while True:
            root = self._get(params)
            page += 1
            if self._raise_on_error(root):
                yield None, page
                return
            for rec in root.iter(O + "record"):
                yield rec, page
            yield None, page
            tok = root.find(".//" + O + "resumptionToken")
            if tok is None or not (tok.text or "").strip() or (max_pages and page >= max_pages):
                return
            params = {"verb": "ListRecords", "resumptionToken": tok.text.strip()}


def harvest(h: Harvester, con, journals: set[str] | None = None, max_pages: int | None = None, **extra) -> dict:
    seen = stored = pages = 0
    for rec, page in h.records(max_pages=max_pages, **extra):
        pages = page
        if rec is None:
            con.commit()
            continue
        seen += 1
        r = dp.parse_record(rec)
        if r is None or (journals and r["journal"] not in journals):
            continue
        dp.upsert(con, r)
        stored += 1
    con.commit()
    return {"pages": pages, "seen": seen, "stored": stored}


def _filt(journals: set[str] | None, set_spec: str | None = None) -> str:
    return f"set:{set_spec}" if set_spec else (",".join(sorted(journals)) if journals else "*")


def windows(start: date, end: date, days: int) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        out.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return out


def run_windows(h: Harvester, con, start: date, end: date, days: int = 30, journals: set[str] | None = None,
                max_pages: int | None = None, force: bool = False, today: date | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc).date()
    filt, results = _filt(journals), []
    for a, b in windows(start, end, days):
        key = (a.isoformat(), b.isoformat(), filt)
        row = con.execute("SELECT status FROM windows WHERE win_from=? AND win_until=? AND filt=?", key).fetchone()
        if row and row["status"] == "done" and not force:
            h.log(f"{a}..{b}: tamamlanmış, atlandı")
            continue
        h.log(f"{a}..{b}: toplanıyor")
        res = harvest(h, con, journals, max_pages, **{"from": a.isoformat(), "until": b.isoformat()})
        status = "done" if b < today and not (max_pages and res["pages"] >= max_pages) else "open"
        con.execute("INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?,?,?)",
                    (*key, status, res["pages"], res["stored"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        h.log(f"  sayfa {res['pages']}, görülen {res['seen']}, saklanan {res['stored']} ({status})")
        results.append({"window": key[:2], **res, "status": status})
    return results


def run_sets(h: Harvester, con, specs: list[str], start: str | None = None, end: str | None = None) -> list[dict]:
    out = []
    for spec in specs:
        h.log(f"küme {spec}: toplanıyor")
        res = harvest(h, con, None, None, set=spec, **{"from": start, "until": end})
        con.execute("INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?,?,?)",
                    ("*", "*", f"set:{spec}", "done", res["pages"], res["stored"],
                     datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
        h.log(f"  sayfa {res['pages']}, saklanan {res['stored']}")
        out.append({"set": spec, **res})
    return out


def status(con) -> dict:
    n = con.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
    by = con.execute("SELECT journal, COUNT(*) c FROM records GROUP BY journal ORDER BY c DESC LIMIT 15").fetchall()
    yrs = con.execute("SELECT MIN(year) a, MAX(year) b FROM records").fetchone()
    wins = con.execute("SELECT status, COUNT(*) c FROM windows GROUP BY status").fetchall()
    return {"records": n, "years": (yrs["a"], yrs["b"]), "top_journals": [(r["journal"], r["c"]) for r in by],
            "windows": {r["status"]: r["c"] for r in wins}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="researchai-harvest", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sets", help="OAI küme listesi").add_argument("--grep", default="")
    w = sub.add_parser("window", help="tarih pencereleriyle genel toplama (devam ettirilebilir)")
    w.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
    w.add_argument("--until", dest="end", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    w.add_argument("--window-days", type=int, default=30)
    w.add_argument("--journals", default="", help="virgülle dergi kodları (URL'deki /pub/<kod>); boşsa hepsi")
    w.add_argument("--max-pages", type=int, default=None, help="pencere başına sayfa sınırı (deneme için)")
    w.add_argument("--force", action="store_true")
    st = sub.add_parser("set", help="listelenen kümeleri (dergileri) tamamen çek")
    st.add_argument("specs", nargs="+")
    sub.add_parser("status", help="dizin durumu")
    q = sub.add_parser("search", help="yerel dizinde ara")
    q.add_argument("query")
    for p in (w, st):
        p.add_argument("--interval", type=float, default=2.0, help="istekler arası sn (varsayılan 2)")
    a = ap.parse_args(argv)

    with closing(dp.connect()) as con:
        if a.cmd == "status":
            print(status(con))
            return 0
        if a.cmd == "search":
            for p in dp.search_sync(a.query, 10):
                print(f"{p.year} | {p.title[:90]} | {', '.join(p.authors[:2])} | {p.doi or '-'} | {p.venue}")
            return 0
        h = Harvester(interval=getattr(a, "interval", 2.0))
        try:
            if a.cmd == "sets":
                for spec, name in h.list_sets():
                    if a.grep.lower() in f"{spec} {name}".lower():
                        print(f"{spec}\t{name}")
            elif a.cmd == "set":
                run_sets(h, con, a.specs)
            elif a.cmd == "window":
                end = date.fromisoformat(a.end) if a.end else datetime.now(timezone.utc).date()
                jr = {x.strip().lower() for x in a.journals.split(",") if x.strip()} or None
                run_windows(h, con, date.fromisoformat(a.start), end, a.window_days, jr, a.max_pages, a.force)
        except OAIError as ex:
            print(f"HATA: {ex}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("Kesildi; tamamlanan pencereler kayıtlı, aynı komutla devam edilir.", file=sys.stderr)
            return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
