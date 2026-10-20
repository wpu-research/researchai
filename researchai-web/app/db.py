"""SQLite depolama: projeler, aşamalar, kaynaklar, token kullanımı."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, idea TEXT NOT NULL, field TEXT, language TEXT DEFAULT 'tr',
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS stages (
  project_id TEXT, n INTEGER, status TEXT DEFAULT 'idle', data TEXT DEFAULT '{}', error TEXT,
  progress TEXT, updated_at REAL, approved_at REAL, approval_note TEXT,
  PRIMARY KEY (project_id, n)
);
CREATE TABLE IF NOT EXISTS sources (
  project_id TEXT, i INTEGER, paper TEXT, score INTEGER, reason TEXT, selected INTEGER DEFAULT 0,
  notes TEXT, verify TEXT, manual INTEGER DEFAULT 0,
  PRIMARY KEY (project_id, i)
);
CREATE TABLE IF NOT EXISTS usage (
  project_id TEXT, stage INTEGER, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, ts REAL
);
"""

STAGES = {1: "Fikir", 2: "Literatür", 3: "Sentez / Hipotez", 4: "Deney / Veri", 5: "Taslak",
          6: "Görsel", 7: "Doğrulama", 8: "Gönderim"}
GATES = {3, 4, 7}  # yazılı onay notu isteyen insan kapıları


def data_dir() -> Path:
    d = Path(os.environ.get("RESEARCHAI_DATA", "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path() -> Path:
    return data_dir() / "researchai.sqlite"


@contextmanager
def conn():
    c = sqlite3.connect(_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        # yarıda kalan işler: süreç yeniden başladıysa koşu kaybolmuştur
        c.execute("UPDATE stages SET status='error', error='Sunucu yeniden başladı; aşamayı tekrar çalıştırın.'"
                  " WHERE status='running'")


def create_project(title: str, idea: str, field: str, language: str) -> str:
    pid = time.strftime("%Y%m%d") + "-" + secrets.token_hex(3)
    now = time.time()
    with conn() as c:
        c.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?)", (pid, title, idea, field, language, now, now))
        for n in STAGES:
            c.execute("INSERT INTO stages (project_id, n, updated_at) VALUES (?,?,?)", (pid, n, now))
    return pid


def list_projects() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT p.*, (SELECT MAX(n) FROM stages s WHERE s.project_id=p.id AND s.approved_at IS NOT NULL)"
                         " AS done FROM projects p ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_project(pid: str) -> dict | None:
    with conn() as c:
        p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not p:
            return None
        st = c.execute("SELECT * FROM stages WHERE project_id=? ORDER BY n", (pid,)).fetchall()
        src = c.execute("SELECT * FROM sources WHERE project_id=? ORDER BY selected DESC, score DESC, i", (pid,)).fetchall()
        us = c.execute("SELECT model, SUM(prompt_tokens) p, SUM(completion_tokens) c, COUNT(*) n FROM usage"
                       " WHERE project_id=? GROUP BY model", (pid,)).fetchall()
    out = dict(p)
    out["stages"] = [{**dict(s), "data": json.loads(s["data"] or "{}"), "name": STAGES[s["n"]],
                      "gate": s["n"] in GATES} for s in st]
    out["sources"] = [source_row(s) for s in src]
    out["usage"] = [dict(u) for u in us]
    return out


def source_row(s) -> dict:
    return {"i": s["i"], "paper": json.loads(s["paper"]), "score": s["score"], "reason": s["reason"],
            "selected": bool(s["selected"]), "notes": json.loads(s["notes"]) if s["notes"] else None,
            "verify": json.loads(s["verify"]) if s["verify"] else None, "manual": bool(s["manual"])}


def delete_project(pid: str) -> None:
    with conn() as c:
        for t, col in (("projects", "id"), ("stages", "project_id"), ("sources", "project_id"), ("usage", "project_id")):
            c.execute(f"DELETE FROM {t} WHERE {col}=?", (pid,))


def touch(c, pid: str) -> None:
    c.execute("UPDATE projects SET updated_at=? WHERE id=?", (time.time(), pid))


def stage(pid: str, n: int) -> dict:
    with conn() as c:
        s = c.execute("SELECT * FROM stages WHERE project_id=? AND n=?", (pid, n)).fetchone()
    return {**dict(s), "data": json.loads(s["data"] or "{}")}


def set_stage(pid: str, n: int, **fields) -> None:
    if "data" in fields:
        fields["data"] = json.dumps(fields["data"], ensure_ascii=False)
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE stages SET {cols} WHERE project_id=? AND n=?", (*fields.values(), pid, n))
        touch(c, pid)


def unapprove_from(pid: str, n: int) -> None:
    """n. aşama değişince n ve sonrasının onayı düşer (veri korunur)."""
    with conn() as c:
        c.execute("UPDATE stages SET approved_at=NULL, approval_note=NULL WHERE project_id=? AND n>=?", (pid, n))


def approved(pid: str, n: int) -> bool:
    with conn() as c:
        r = c.execute("SELECT approved_at FROM stages WHERE project_id=? AND n=?", (pid, n)).fetchone()
    return bool(r and r["approved_at"])


def add_usage(pid: str, n: int, model: str, p: int, cpl: int) -> None:
    with conn() as c:
        c.execute("INSERT INTO usage VALUES (?,?,?,?,?,?)", (pid, n, model, p, cpl, time.time()))


def replace_sources(pid: str, rows: list[dict]) -> None:
    """Otomatik bulunanları değiştirir, elle eklenenleri korur."""
    with conn() as c:
        c.execute("DELETE FROM sources WHERE project_id=? AND manual=0", (pid,))
        start = (c.execute("SELECT MAX(i) m FROM sources WHERE project_id=?", (pid,)).fetchone()["m"] or 0) + 1
        for k, r in enumerate(rows):
            c.execute("INSERT INTO sources (project_id, i, paper, score, reason, selected) VALUES (?,?,?,?,?,?)",
                      (pid, start + k, json.dumps(r["paper"], ensure_ascii=False), r.get("score"), r.get("reason"),
                       int(r.get("selected", False))))


def add_source(pid: str, paper: dict, selected: bool = True) -> int:
    with conn() as c:
        i = (c.execute("SELECT MAX(i) m FROM sources WHERE project_id=?", (pid,)).fetchone()["m"] or 0) + 1
        c.execute("INSERT INTO sources (project_id, i, paper, score, reason, selected, manual) VALUES (?,?,?,?,?,?,1)",
                  (pid, i, json.dumps(paper, ensure_ascii=False), None, "elle eklendi", int(selected)))
    return i


def update_source(pid: str, i: int, **fields) -> None:
    for k in ("notes", "verify", "paper"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    if "selected" in fields:
        fields["selected"] = int(bool(fields["selected"]))
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE sources SET {cols} WHERE project_id=? AND i=?", (*fields.values(), pid, i))


def sources(pid: str, selected_only: bool = False) -> list[dict]:
    q = "SELECT * FROM sources WHERE project_id=?" + (" AND selected=1" if selected_only else "") + " ORDER BY i"
    with conn() as c:
        return [source_row(s) for s in c.execute(q, (pid,)).fetchall()]
