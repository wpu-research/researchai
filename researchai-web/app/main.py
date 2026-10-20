"""ResearchAI web: API + statik arayüz."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, llm, pipeline, text

log = logging.getLogger("researchai")
STATIC = Path(__file__).parent / "static"
TASKS: dict[tuple[str, int], asyncio.Task] = {}
DERGIPARK_SETS = os.environ.get("DERGIPARK_SETS", "marustd,akademiksanat,artium,ataunigsfd,iusty").split(",")
HARVEST = {"running": False, "last": None, "error": None}


def _env_defaults() -> None:
    d = db.data_dir()
    os.environ.setdefault("RESEARCHAI_RUNS_DIR", str(d / "runs"))
    os.environ.setdefault("RESEARCHAI_DB", str(d / "dergipark.sqlite"))


def _harvest(sets: list[str]) -> None:
    from researchai_mcp import harvest as hv
    from researchai_mcp.connectors import dergipark as dp
    HARVEST.update(running=True, error=None)
    try:
        with closing(dp.connect()) as con:
            hv.run_sets(hv.Harvester(interval=2.0, log=log.info), con, sets)
        HARVEST["last"] = time.time()
    except Exception as ex:
        HARVEST["error"] = f"{type(ex).__name__}: {ex}"
    finally:
        HARVEST["running"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _env_defaults()
    db.init()
    from researchai_mcp.connectors import dergipark as dp
    if not dp.available() and os.environ.get("DERGIPARK_AUTOHARVEST", "1") == "1":
        threading.Thread(target=_harvest, args=([s for s in DERGIPARK_SETS if s],), daemon=True).start()
    yield


app = FastAPI(title="ResearchAI", lifespan=lifespan)


# ---------------------------------------------------------------- modeller
class NewProject(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    idea: str = Field(min_length=10, max_length=8000)
    field: str = Field(default="", max_length=200)
    language: str = Field(default="tr", pattern="^(tr|en)$")


class RunOpts(BaseModel):
    venue: str | None = None


class StageEdit(BaseModel):
    data: dict


class Approval(BaseModel):
    note: str = ""


class SourcePatch(BaseModel):
    selected: bool


class ManualSource(BaseModel):
    title: str = Field(min_length=3)
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None


# ---------------------------------------------------------------- yardımcılar
def _need(pid: str) -> dict:
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404, "Proje bulunamadı")
    return p


def _check_n(n: int) -> None:
    if n not in db.STAGES:
        raise HTTPException(404, "Aşama yok")


async def _run(pid: str, n: int, opts: dict) -> None:
    try:
        data = await pipeline.RUNNERS[n](pid, opts)
        db.set_stage(pid, n, status="ready", data=data, error=None, progress=None)
    except asyncio.CancelledError:
        db.set_stage(pid, n, status="error", error="İptal edildi", progress=None)
        raise
    except Exception as ex:
        log.exception("aşama %s/%s", pid, n)
        db.set_stage(pid, n, status="error", error=f"{type(ex).__name__}: {str(ex)[:500]}", progress=None)
    finally:
        TASKS.pop((pid, n), None)


# ---------------------------------------------------------------- API
@app.get("/api/meta")
def meta():
    from researchai_mcp.connectors import dergipark as dp
    n = 0
    if dp.available():
        with closing(dp.connect()) as con:
            n = con.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
    return {"llm": llm.enabled(), "models": {"main": llm.model_main(), "fast": llm.model_fast(),
                                             "reviewer": llm.model_reviewer()},
            "stages": db.STAGES, "gates": sorted(db.GATES),
            "dergipark": {"records": n, "sets": DERGIPARK_SETS, **HARVEST}}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/projects")
def projects():
    return db.list_projects()


@app.post("/api/projects")
def create(p: NewProject):
    return {"id": db.create_project(p.title.strip(), p.idea.strip(), p.field.strip(), p.language)}


@app.get("/api/projects/{pid}")
def project(pid: str):
    p = _need(pid)
    for s in p["stages"]:
        s["running"] = (pid, s["n"]) in TASKS
    return p


@app.delete("/api/projects/{pid}")
def delete(pid: str):
    _need(pid)
    for (p, n), t in list(TASKS.items()):
        if p == pid:
            t.cancel()
    db.delete_project(pid)
    return {"ok": True}


@app.post("/api/projects/{pid}/stages/{n}/run")
async def run_stage(pid: str, n: int, opts: RunOpts | None = None):
    _need(pid)
    _check_n(n)
    if not llm.enabled():
        raise HTTPException(503, "LLM anahtarı (ANTHROPIC_API_KEY) ayarlı değil")
    if n > 1 and not db.approved(pid, n - 1):
        raise HTTPException(409, f"Önce {n - 1}. aşama onaylanmalı")
    if (pid, n) in TASKS:
        raise HTTPException(409, "Bu aşama zaten çalışıyor")
    db.unapprove_from(pid, n)
    db.set_stage(pid, n, status="running", error=None, progress="Başlatılıyor")
    TASKS[(pid, n)] = asyncio.create_task(_run(pid, n, (opts.model_dump() if opts else {})))
    return {"ok": True}


@app.post("/api/projects/{pid}/stages/{n}/cancel")
def cancel_stage(pid: str, n: int):
    t = TASKS.get((pid, n))
    if t:
        t.cancel()
    return {"ok": bool(t)}


@app.put("/api/projects/{pid}/stages/{n}")
def edit_stage(pid: str, n: int, e: StageEdit):
    _need(pid)
    _check_n(n)
    if (pid, n) in TASKS:
        raise HTTPException(409, "Aşama çalışırken düzenlenemez")
    st = db.stage(pid, n)
    db.unapprove_from(pid, n)
    status = "ready" if e.data else st["status"]
    if n == 5 and "sections" in e.data:  # elle düzenlenen taslakta eski iddia denetimi geçersiz
        old = st["data"].get("sections")
        if old != e.data["sections"]:
            e.data["claims_stale"] = True
    db.set_stage(pid, n, data={**st["data"], **e.data}, status=status)
    return {"ok": True}


@app.post("/api/projects/{pid}/stages/{n}/approve")
def approve(pid: str, n: int, a: Approval):
    _need(pid)
    _check_n(n)
    st = db.stage(pid, n)
    if st["status"] != "ready":
        raise HTTPException(409, "Onaylanacak hazır bir çıktı yok")
    if n > 1 and not db.approved(pid, n - 1):
        raise HTTPException(409, f"Önce {n - 1}. aşama onaylanmalı")
    note = a.note.strip()
    if n in db.GATES and len(note) < 15:
        raise HTTPException(422, "İnsan kapısı: neyi incelediğinizi ve neden onayladığınızı en az 15 karakterle yazın")
    if n == 2 and not db.sources(pid, selected_only=True):
        raise HTTPException(422, "En az bir kaynak seçin")
    from researchai_mcp import disclosure
    db.set_stage(pid, n, approved_at=time.time(), approval_note=note)
    disclosure.log_ai_use(pid, pipeline.label(n), "yazar", "", "inceleme ve onay", True, note)
    return {"ok": True}


@app.put("/api/projects/{pid}/sources/{i}")
def patch_source(pid: str, i: int, s: SourcePatch):
    _need(pid)
    db.update_source(pid, i, selected=s.selected)
    db.unapprove_from(pid, 2)
    return {"ok": True}


@app.post("/api/projects/{pid}/sources")
def add_source(pid: str, s: ManualSource):
    _need(pid)
    i = db.add_source(pid, {**s.model_dump(), "source": "elle", "found_in": ["elle"]})
    db.unapprove_from(pid, 2)
    return {"i": i}


# ---------------------------------------------------------------- dışa aktarım
def _bundle(pid: str):
    p = _need(pid)
    draft = db.stage(pid, 5)["data"]
    fin = db.stage(pid, 8)["data"]
    sections, order = text.renumber(draft.get("sections") or [])
    src = {s["i"]: s["paper"] for s in db.sources(pid)}
    refs = [src[i] for i in order if i in src]
    return p, fin, sections, order, src, refs


@app.get("/api/projects/{pid}/export/{kind}")
def export(pid: str, kind: str, lang: str = "tr"):
    from researchai_mcp import disclosure
    p, fin, sections, order, src, refs = _bundle(pid)
    slug = pid
    if kind == "bib":
        used: set[str] = set()
        body = "\n\n".join(text.bibtex(r, text.bibkey(r, used)) for r in refs)
        return PlainTextResponse(body, headers={"Content-Disposition": f'attachment; filename="{slug}.bib"'})
    if kind == "disclosure":
        d = disclosure.generate_disclosure(pid, lang if lang in ("tr", "en") else "tr")
        md = d["statement_md"] + ("\n\n" + d["table_md"] if d["table_md"] else "")
        return {"markdown": md, "warnings": d["warnings"]}
    title = fin.get(f"title_{p['language']}") or db.stage(pid, 1)["data"].get("title") or p["title"]
    abstract = fin.get(f"abstract_{p['language']}", "")
    if kind == "md":
        kw = ", ".join(fin.get(f"keywords_{p['language']}") or [])
        parts = [f"# {title}", f"**Öz.** {abstract}" if abstract else "", f"**Anahtar kelimeler:** {kw}" if kw else ""]
        parts += [f"## {s['title']}\n\n{s['text']}" for s in sections]
        parts.append("## Kaynakça\n\n" + "\n".join(f"{k}. {text.apa(r)}" for k, r in enumerate(refs, 1)))
        d = disclosure.generate_disclosure(pid, p["language"])
        parts.append("## Yapay zekâ kullanım beyanı\n\n" + d["statement_md"])
        return PlainTextResponse("\n\n".join(x for x in parts if x),
                                 headers={"Content-Disposition": f'attachment; filename="{slug}.md"'})
    if kind == "tex":
        draft_secs = db.stage(pid, 5)["data"].get("sections") or []
        used = set()
        keys = {i: text.bibkey(src[i], used) for i in order if i in src}
        return PlainTextResponse(text.to_latex(title, abstract, draft_secs, keys, p["language"]),
                                 headers={"Content-Disposition": f'attachment; filename="{slug}.tex"'})
    raise HTTPException(404, "Bilinmeyen biçim")


@app.post("/api/dergipark/harvest")
def harvest_now():
    if HARVEST["running"]:
        raise HTTPException(409, "Toplama zaten sürüyor")
    threading.Thread(target=_harvest, args=([s for s in DERGIPARK_SETS if s],), daemon=True).start()
    return {"ok": True}


# ---------------------------------------------------------------- arayüz
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
