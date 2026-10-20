"""YZ kullanım günlüğü ve beyan üretimi.

Beyan gerçeği yansıtır, gerçeği iyileştirmez: insan incelemesi kaydedilmemiş
aşamalar beyanda öyle yazılır ve uyarı üretir.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def runs_dir() -> Path:
    return Path(os.environ.get("RESEARCHAI_RUNS_DIR", "runs")).resolve()


def run_path(run_id: str) -> Path:
    if not _RUN_ID.match(run_id) or ".." in run_id:
        raise ValueError("run_id yalnız harf, rakam, '.', '_' ve '-' içerebilir (en çok 64 karakter)")
    root = runs_dir()
    p = (root / run_id).resolve()
    if root not in p.parents:
        raise ValueError("geçersiz run_id")
    return p


def log_ai_use(run_id: str, stage: str, tool: str, model: str, purpose: str,
               human_review: bool, notes: str = "") -> dict:
    d = run_path(run_id)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "ai_use_log.jsonl"
    n = sum(1 for _ in f.open(encoding="utf-8")) if f.exists() else 0
    entry = {"entry_id": f"{run_id}-{n + 1}", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             "stage": stage, "tool": tool, "model": model, "purpose": purpose,
             "human_review": bool(human_review), "notes": notes}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"entry_id": entry["entry_id"]}


def read_log(run_id: str) -> list[dict]:
    f = run_path(run_id) / "ai_use_log.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


_T = {
    "tr": {
        "intro": "Bu çalışmanın hazırlanmasında şu yapay zekâ araçları kullanılmıştır:",
        "row": "{tool} ({model}): {stage}, {purpose}.",
        "reviewed": "Aşağıdaki aşamalarda çıktılar yazar(lar) tarafından gözden geçirilmiştir: {s}.",
        "unreviewed": "Aşağıdaki aşamalar için yazar incelemesi kaydedilmemiştir: {s}.",
        "all": "Tüm yapay zekâ çıktıları yazar(lar) tarafından gözden geçirilmiş ve doğrulanmıştır.",
        "none": "Bu çalışmada yapay zekâ aracı kullanıldığına dair kayıt bulunmamaktadır.",
        "cols": "| Aşama | Araç | Model | Amaç | İnsan incelemesi |",
        "yes": "evet", "no": "hayır",
        "warn": "'{s}' aşaması için insan incelemesi kaydedilmemiş; beyan bu durumu açıkça yazar.",
    },
    "en": {
        "intro": "The following artificial intelligence tools were used in preparing this work:",
        "row": "{tool} ({model}): {stage}, {purpose}.",
        "reviewed": "Outputs from the following stages were reviewed by the author(s): {s}.",
        "unreviewed": "No author review is recorded for the following stages: {s}.",
        "all": "All AI-generated output was reviewed and verified by the author(s).",
        "none": "No use of AI tools is recorded for this work.",
        "cols": "| Stage | Tool | Model | Purpose | Human review |",
        "yes": "yes", "no": "no",
        "warn": "No human review recorded for stage '{s}'; the statement says so explicitly.",
    },
}


def generate_disclosure(run_id: str, language: str = "tr", venue_profile: str | None = None) -> dict:
    t = _T.get(language, _T["tr"])
    log = read_log(run_id)
    if not log:
        return {"statement_md": t["none"], "table_md": "", "warnings": ["no_log_entries"]}
    rows = "\n".join(f"- {t['row'].format(**e)}" for e in log)
    rev = sorted({e["stage"] for e in log if e["human_review"]})
    unrev = sorted({e["stage"] for e in log if not e["human_review"]})
    parts = [t["intro"], rows]
    if not unrev:
        parts.append(t["all"])
    else:
        if rev:
            parts.append(t["reviewed"].format(s=", ".join(rev)))
        parts.append(t["unreviewed"].format(s=", ".join(unrev)))
    table = "\n".join([t["cols"], "|---|---|---|---|---|"] + [
        f"| {e['stage']} | {e['tool']} | {e['model']} | {e['purpose']} | {t['yes'] if e['human_review'] else t['no']} |"
        for e in log])
    warnings = [t["warn"].format(s=s) for s in unrev]
    if venue_profile:
        warnings.append(f"venue_profile '{venue_profile}' henüz tanımlı değil; genel biçim kullanıldı")
    return {"statement_md": "\n\n".join(parts), "table_md": table, "warnings": warnings}
