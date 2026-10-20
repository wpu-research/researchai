"""Sekiz aşamalı araştırma hattı. Her aşama arka planda çalışır, çıktısını stages.data'ya yazar.

İlkeler:
- Model kaynak uydurmaz: atıflar yalnız seçili kaynak kimlikleriyle ([i]) yapılır, sonra denetlenir.
- Veri uydurulmaz: Bulgular yalnız 4. aşamada yazarın girdiği sonuçlardan yazılır.
- Her LLM çağrısı YZ kullanım günlüğüne düşer; onay, aşamanın insan incelemesi kaydıdır.
"""
from __future__ import annotations

import asyncio
import csv
import io
import time

from researchai_mcp import disclosure
from researchai_mcp.normalize import dedupe_key
from researchai_mcp.search import search_sources
from researchai_mcp.verify import Citation, verify_citation

from . import db, llm, text

TOOL = "ResearchAI (Anthropic Claude)"


def label(n: int) -> str:
    return f"{n}. {db.STAGES[n]}"


def lang_name(lang: str) -> str:
    return "Türkçe" if lang == "tr" else "English"


async def ask_json(pid: str, n: int, purpose: str, system: str, user: str, **kw):
    data, rep = await llm.chat_json(system, user, **kw)
    _record(pid, n, purpose, rep)
    return data


async def ask_text(pid: str, n: int, purpose: str, system: str, user: str, **kw) -> str:
    rep = await llm.chat(system, user, **kw)
    _record(pid, n, purpose, rep)
    return rep.text.strip()


def _record(pid: str, n: int, purpose: str, rep: llm.Reply) -> None:
    db.add_usage(pid, n, rep.model, rep.prompt_tokens, rep.completion_tokens)
    disclosure.log_ai_use(pid, label(n), TOOL, rep.model, purpose, False)


def progress(pid: str, n: int, msg: str) -> None:
    db.set_stage(pid, n, progress=msg)


def _proj(pid: str) -> dict:
    with db.conn() as c:
        return dict(c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())


def _src_line(s: dict, with_notes: bool = True, abstract_chars: int = 500) -> str:
    p = s["paper"]
    au = ", ".join((p.get("authors") or [])[:3]) + (" vd." if len(p.get("authors") or []) > 3 else "")
    line = f"[{s['i']}] {p.get('title')} — {au} ({p.get('year') or 't.y.'}), {p.get('venue') or ''}"
    nt = s.get("notes") or {}
    if with_notes and nt.get("findings"):
        line += f"\n    Bulgular: {nt['findings']}\n    Yöntem: {nt.get('method') or '-'}"
    elif p.get("abstract"):
        line += f"\n    Özet: {p['abstract'][:abstract_chars]}"
    return line


# ---------------------------------------------------------------- 1. Fikir
async def stage1(pid: str, opts: dict) -> dict:
    pr = _proj(pid)
    progress(pid, 1, "Araştırma sorusu ve kapsam kartı hazırlanıyor")
    return await ask_json(pid, 1, "araştırma sorusu ve kapsam kartı", f"""Sen deneyimli bir araştırma danışmanısın.
Ham bir fikri, dergiye gidecek bir çalışmanın kapsam kartına çevir. Gerçekçi ol; tek bir makaleye sığacak kadar daralt.
Çıktı dili: {lang_name(pr['language'])} (search_queries hariç).""", f"""Alan: {pr['field'] or 'belirtilmedi'}
Ham fikir:
{pr['idea']}

Şu JSON'u döndür:
{{"title": "çalışma başlığı önerisi",
 "research_question": "tek cümlelik ana araştırma sorusu",
 "sub_questions": ["2-4 alt soru"],
 "scope": "kapsam (2-3 cümle)", "out_of_scope": "bilinçli olarak kapsam dışı (1-2 cümle)",
 "method_type": "empirical | humanities | review | mixed",
 "keywords": ["5-8 anahtar kelime"],
 "search_queries": ["literatür taraması için 4-6 kısa sorgu: çoğu İngilizce, 1-2'si Türkçe; her biri 2-5 sözcük"],
 "inclusion": ["dahil etme ölçütleri"], "exclusion": ["dışlama ölçütleri"],
 "year_from": yıl ya da null,
 "risks": ["bu çalışmanın 2-3 temel riski"]}}""")


# ---------------------------------------------------------------- 2. Literatür
async def stage2(pid: str, opts: dict) -> dict:
    card = db.stage(pid, 1)["data"]
    queries = [q for q in (card.get("search_queries") or []) if q.strip()][:8]
    if not queries:
        raise ValueError("1. aşamada arama sorgusu yok")
    yf = card.get("year_from") if isinstance(card.get("year_from"), int) else None
    merged: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for k, q in enumerate(queries, 1):  # sıralı: kaynakların hız sınırlarına saygı
        progress(pid, 2, f"Arama {k}/{len(queries)}: {q}")
        res = await search_sources(q, limit=8, year_from=yf)
        for name, err in res["errors"].items():
            errors[name] = err
        for p in res["results"]:
            key = dedupe_key(p.get("doi"), p["title"], (p.get("authors") or [""])[0], p.get("year"))
            if key in merged:
                merged[key]["found_in"] = sorted(set(merged[key]["found_in"]) | set(p["found_in"]))
                merged[key]["queries"].append(q)
            else:
                merged[key] = {**p, "queries": [q]}
    cands = sorted(merged.values(), key=lambda p: (-len(p["found_in"]) - len(p["queries"]), not p.get("abstract")))[:60]
    if not cands:
        raise ValueError("hiç aday bulunamadı; sorguları düzenleyip yeniden deneyin. Kaynak hataları: " + str(errors))

    rq = card.get("research_question", "")
    crit = "Dahil: " + "; ".join(card.get("inclusion") or []) + "\nDışla: " + "; ".join(card.get("exclusion") or [])
    sem = asyncio.Semaphore(3)
    scores: dict[int, dict] = {}
    batches = [cands[i:i + 10] for i in range(0, len(cands), 10)]
    done = 0

    async def screen(off: int, batch: list[dict]):
        nonlocal done
        listing = "\n".join(f"#{off + j}: {p['title']} ({p.get('year') or 't.y.'}). "
                            f"{(p.get('abstract') or 'özet yok')[:450]}" for j, p in enumerate(batch))
        async with sem:
            out = await ask_json(pid, 2, "aday kaynak eleme (başlık+özet)", """Sistematik derlemede eleme yapan titiz bir araştırmacısın.
Her adayı araştırma sorusuna ilgisine göre 0-3 puanla: 3=doğrudan ilgili, 2=ilgili, 1=dolaylı, 0=ilgisiz.
Yalnız verilen başlık ve özete dayan; özet yoksa temkinli puanla.""", f"""Araştırma sorusu: {rq}
{crit}

Adaylar:
{listing}

JSON dizi döndür: [{{"id": numara, "score": 0-3, "reason": "en çok 15 sözcük gerekçe"}}]""",
                                  max_tokens=1500)
        for r in out if isinstance(out, list) else out.get("items", []):
            try:
                scores[int(r["id"])] = r
            except (KeyError, TypeError, ValueError):
                continue
        done += 1
        progress(pid, 2, f"Eleme {done}/{len(batches)} grup")

    await asyncio.gather(*(screen(i * 10, b) for i, b in enumerate(batches)))
    rows = []
    for idx, p in enumerate(cands):
        sc = scores.get(idx, {})
        score = sc.get("score")
        rows.append({"paper": p, "score": int(score) if isinstance(score, (int, float)) else None,
                     "reason": sc.get("reason") or "puanlanamadı"})
    ranked = sorted(rows, key=lambda r: -(r["score"] or 0))
    chosen = {id(r) for r in ranked if (r["score"] or 0) >= 2}
    chosen = {id(r) for r in ranked[:20] if id(r) in chosen}
    for r in rows:
        r["selected"] = id(r) in chosen
    db.replace_sources(pid, rows)
    return {"queries": queries, "errors": errors, "candidates": len(cands), "raw": len(merged),
            "auto_selected": len(chosen)}


# ---------------------------------------------------------------- 3. Sentez
async def _ensure_notes(pid: str, n: int) -> list[dict]:
    sel = db.sources(pid, selected_only=True)
    need = [s for s in sel if not s.get("notes")]
    no_abs = [s for s in need if not s["paper"].get("abstract")]
    for s in no_abs:
        db.update_source(pid, s["i"], notes={"findings": None, "method": None,
                                             "note": "Özet yok; içerik yazarca okunmalı."})
    todo = [s for s in need if s["paper"].get("abstract")]
    sem = asyncio.Semaphore(3)

    async def extract(batch):
        listing = "\n\n".join(f"[{s['i']}] {s['paper']['title']}\nÖzet: {s['paper']['abstract'][:1500]}" for s in batch)
        async with sem:
            out = await ask_json(pid, n, "kaynak özetlerinden yapılandırılmış not çıkarma", """Kaynak özetlerinden yapılandırılmış not çıkar.
Yalnız özette yazanı aktar; özette olmayan bulgu ekleme.""", f"""{listing}

JSON dizi döndür: [{{"id": kaynak numarası, "findings": "1-2 cümle ana bulgu/iddia", "method": "yöntem/veri (kısa)",
"limits": "özette belirtilen sınırlılık ya da null"}}]""", max_tokens=2000)
        for r in out if isinstance(out, list) else []:
            try:
                db.update_source(pid, int(r["id"]), notes={k: r.get(k) for k in ("findings", "method", "limits")})
            except (KeyError, TypeError, ValueError):
                continue

    batches = [todo[i:i + 5] for i in range(0, len(todo), 5)]
    if batches:
        progress(pid, n, f"{len(todo)} kaynaktan not çıkarılıyor")
        await asyncio.gather(*(extract(b) for b in batches))
    return db.sources(pid, selected_only=True)


async def stage3(pid: str, opts: dict) -> dict:
    pr, card = _proj(pid), db.stage(pid, 1)["data"]
    sel = await _ensure_notes(pid, 3)
    if len(sel) < 3:
        raise ValueError("Sentez için en az 3 seçili kaynak gerekir (2. aşamada seçin)")
    progress(pid, 3, "Temalar, boşluklar ve hipotezler çıkarılıyor")
    listing = "\n".join(_src_line(s) for s in sel)
    out = await ask_json(pid, 3, "tema sentezi, boşluk haritası, hipotez önerisi", f"""Literatür sentezi yapan kıdemli bir araştırmacısın.
Yalnız verilen kaynak notlarına dayan ve her iddiayı kaynak numarasıyla bağla. Kaynakta olmayan bilgi uydurma.
Boşluk: kaynakların test etmediği ya da çeliştiği nokta. Çıktı dili: {lang_name(pr['language'])}.""", f"""Araştırma sorusu: {card.get('research_question')}
Alt sorular: {'; '.join(card.get('sub_questions') or [])}
Yöntem türü: {card.get('method_type')}

Kaynaklar:
{listing}

JSON döndür:
{{"themes": [{{"name": "tema", "summary": "2-3 cümle", "sources": [numaralar]}}],
 "gaps": [{{"gap": "boşluk", "why": "neden boşluk (kaynaklara dayanarak)", "sources": [numaralar]}}],
 "hypotheses": [{{"id": "H1", "text": "sınanabilir hipotez ya da çözümleme önermesi", "rationale": "dayanak", "test": "nasıl sınanır/incelenir"}}],
 "tensions": ["kaynaklar arası çelişki/gerilim (varsa)"]}}""", max_tokens=3500)
    hyps = out.get("hypotheses") or []
    out["chosen"] = [hyps[0]["id"]] if hyps and isinstance(hyps[0], dict) and hyps[0].get("id") else []
    return out


# ---------------------------------------------------------------- 4. Deney / Veri
async def stage4(pid: str, opts: dict) -> dict:
    pr, card, syn = _proj(pid), db.stage(pid, 1)["data"], db.stage(pid, 3)["data"]
    prev = db.stage(pid, 4)["data"]
    chosen = [h for h in syn.get("hypotheses") or [] if h.get("id") in (syn.get("chosen") or [])]
    progress(pid, 4, "Yöntem ve veri planı hazırlanıyor")
    plan = await ask_json(pid, 4, "yöntem ve veri planı önerisi", f"""Araştırma yöntemi danışmanısın. Seçili hipotez(ler)i sınamak ya da
incelemek için uygulanabilir bir plan yaz. Türkiye'ye özgü veri kaynakları (TÜİK, YÖK, DergiPark, arşivler, kurum verisi,
saha) uygunsa öner; bunlar çalışmanın ayırt edici avantajı olabilir. Gerçekçi ol; sonuç uydurma, yalnız plan yaz.
Çıktı dili: {lang_name(pr['language'])}.""", f"""Araştırma sorusu: {card.get('research_question')}
Yöntem türü: {card.get('method_type')}
Seçili hipotezler: {chosen or syn.get('hypotheses')}

JSON döndür:
{{"design": "araştırma deseni (2-3 cümle)",
 "units": ["değişkenler ya da inceleme birimleri/örneklem/derlem"],
 "data_sources": [{{"name": "kaynak", "why": "neden", "tr_specific": true/false, "access": "erişim yolu"}}],
 "analysis": "çözümleme yöntemi", "steps": ["uygulama adımları"],
 "ethics": "etik/izin gereksinimleri", "threats": ["geçerlik tehditleri ve önlemleri"]}}""", max_tokens=2500)
    # yazarın girdiği sonuçlar korunur; plan yeniden üretilse de silinmez
    return {"plan": plan, "results": prev.get("results", ""), "csv": prev.get("csv", "")}


# ---------------------------------------------------------------- 5. Taslak
SECTIONS = {
    "empirical": ["Giriş", "Literatür Taraması", "Yöntem", "Bulgular", "Tartışma", "Sonuç"],
    "humanities": ["Giriş", "Kuramsal Çerçeve", "Literatür", "Çözümleme", "Tartışma", "Sonuç"],
    "review": ["Giriş", "Yöntem", "Bulgular", "Tartışma", "Sonuç"],
}
SECTIONS_EN = {"Giriş": "Introduction", "Literatür Taraması": "Literature Review", "Yöntem": "Method",
               "Bulgular": "Findings", "Tartışma": "Discussion", "Sonuç": "Conclusion",
               "Kuramsal Çerçeve": "Theoretical Framework", "Literatür": "Literature", "Çözümleme": "Analysis"}
DATA_SECTIONS = {"Bulgular", "Çözümleme"}


async def stage5(pid: str, opts: dict) -> dict:
    pr, card = _proj(pid), db.stage(pid, 1)["data"]
    syn, exp = db.stage(pid, 3)["data"], db.stage(pid, 4)["data"]
    sel = await _ensure_notes(pid, 5)
    ids = {s["i"] for s in sel}
    names = SECTIONS.get(card.get("method_type"), SECTIONS["empirical"])
    listing = "\n".join(_src_line(s) for s in sel)
    chosen = [h for h in syn.get("hypotheses") or [] if h.get("id") in (syn.get("chosen") or [])]
    results = (exp.get("results") or "").strip()
    sections: list[dict] = []
    for k, name in enumerate(names, 1):
        title = SECTIONS_EN.get(name, name) if pr["language"] == "en" else name
        progress(pid, 5, f"Bölüm {k}/{len(names)}: {title}")
        data_rule = (f"Bu bölümde YALNIZ yazarın girdiği şu sonuçlara dayan, yeni sayı/bulgu uydurma:\n{results}"
                     if results else "Yazar henüz sonuç girmedi: bulgu uydurma; yerine '[VERİ BEKLENİYOR: ...]' "
                                     "yer tutucusu ile hangi sonucun gerektiğini yaz.") if name in DATA_SECTIONS else (
            f"Çalışmanın kendi bulgularından söz edeceksen yalnız yazarın şu sonuçlarını kullan:\n{results}"
            if results else "Çalışmanın kendi bulgusu henüz yok; bulgu varmış gibi yazma.")
        data_rule += ("\nYöntem planında olup yazarın sonuçlarında geçmeyen veri toplama işlemlerini (ör. görüşme, gözlem) "
                      "yapılmış ya da bulgu vermiş gibi yazma; gerekiyorsa 'planlanmaktadır' de.")
        plan = exp.get("plan", {})
        plan_txt = "" if name in DATA_SECTIONS else (
            f"Yöntem planı (HENÜZ UYGULANMADI; yalnız yazarın sonuçlarında geçenler yapılmıştır): {plan.get('design')} "
            f"| Çözümleme: {plan.get('analysis')}")
        prior = "\n\n".join(f"## {s['title']}\n{s['text'][:1200]}" for s in sections[-2:])
        body = await ask_text(pid, 5, f"taslak bölümü: {title}", f"""Akademik makale yazarına taslak öneren bir yardımcısın.
Kurallar:
1. Olgusal her cümle, yalnız aşağıdaki listeden bir ya da daha fazla kaynak numarasıyla biter: [3] ya da [2, 5].
2. Listede olmayan kaynağa atıf yapma, yazar adı-yıl biçimi kullanma, kaynakça yazma.
3. Kaynağın notunda/özetinde olmayan iddiayı o kaynağa bağlama. Dayanak yoksa cümleyi '[kaynak gerekli]' ile bitir.
4. Akıcı, akademik, abartısız yaz. Başlık yazma; yalnız bölüm metnini paragraflar halinde yaz.
Dil: {lang_name(pr['language'])}.""", f"""Makale: {card.get('title')}
Araştırma sorusu: {card.get('research_question')}
Seçili hipotez/önerme: {chosen}
Temalar: {[t.get('name') for t in syn.get('themes') or []]}
Boşluklar: {[g.get('gap') for g in syn.get('gaps') or []]}
{plan_txt}
{data_rule}

Kaynak listesi:
{listing}

Önceki bölümlerden son kısım (tekrar etme):
{prior or '-'}

Şimdi '{title}' bölümünü yaz (yaklaşık {450 if name in ('Giriş', 'Sonuç') else 750} sözcük).""",
                              max_tokens=2600, temperature=0.4)
        sections.append({"title": title, "text": strip_heading(body, title)})
    claims = await check_claims(pid, 5, sections, sel, ids)
    await check_data_fidelity(pid, 5, sections, claims, results)
    return {"sections": sections, "claims": claims, "claims_summary": summarize_claims(claims)}


def strip_heading(body: str, title: str) -> str:
    """Modelin metne eklediği başlık satırlarını ('Tartışma', '## Tartışma') ayıklar."""
    lines = body.strip().splitlines()
    while lines and (lines[0].strip().lstrip("#").strip().rstrip(":").lower() == title.lower() or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).strip()


async def check_claims(pid: str, n: int, sections: list[dict], sel: list[dict], ids: set[int]) -> list[dict]:
    """Her atıflı cümlenin, atıf verdiği kaynağın özet/notunca desteklenip desteklenmediğini denetler."""
    claims = []
    for si, s in enumerate(sections):
        for t in text.sentences(s["text"]):
            refs = text.cite_numbers(t)
            claims.append({"section": si, "text": t, "refs": refs, "verdicts": {},
                           "flag": "needs_source" if "[kaynak gerekli]" in t.lower() else
                           ("unknown_ref" if any(r not in ids for r in refs) else None)})
    by_src: dict[int, list[int]] = {}
    for k, c in enumerate(claims):
        for r in c["refs"]:
            if r in ids:
                by_src.setdefault(r, []).append(k)
    src = {s["i"]: s for s in sel}
    sem = asyncio.Semaphore(3)
    total, done = len(by_src), 0

    async def judge(i: int, ks: list[int]):
        nonlocal done
        p, nt = src[i]["paper"], src[i].get("notes") or {}
        evidence = (p.get("abstract") or "").strip()
        if not evidence:
            for k in ks:
                claims[k]["verdicts"][str(i)] = {"v": "cannot_access", "note": "Kaynağın özeti yok; tahmin üretilmedi."}
            return
        listing = "\n".join(f"#{k}: {claims[k]['text']}" for k in ks)
        async with sem:
            out = await ask_json(pid, n, "iddia-kaynak desteği denetimi", """Atıf denetçisisin. Her cümlenin, verilen kaynağın
özetiyle desteklenip desteklenmediğini değerlendir. Yalnız özete dayan; genel bilgini kullanma.
yes = özet iddiayı açıkça destekliyor; partial = kısmen/daha zayıf; no = desteklemiyor ya da çelişiyor.""",
                                 f"""Kaynak [{i}]: {p.get('title')} ({p.get('year')})
Özet: {evidence[:2500]}
Not: {nt.get('findings') or '-'}

Cümleler:
{listing}

JSON dizi döndür: [{{"id": cümle numarası, "v": "yes|partial|no", "note": "en çok 15 sözcük"}}]""", max_tokens=1500)
        for r in out if isinstance(out, list) else []:
            try:
                k = int(r["id"])
                if k in ks:
                    claims[k]["verdicts"][str(i)] = {"v": r.get("v", "no"), "note": r.get("note", "")}
            except (KeyError, TypeError, ValueError):
                continue
        done += 1
        progress(pid, n, f"İddia-kaynak denetimi {done}/{total} kaynak")

    await asyncio.gather(*(judge(i, ks) for i, ks in by_src.items()))
    return claims


async def check_data_fidelity(pid: str, n: int, sections: list[dict], claims: list[dict], results: str) -> None:
    """Atıfsız cümlelerdeki çalışma-içi bulgu/veri iddialarını yazarın girdiği sonuçlarla karşılaştırır.

    İddia-kaynak denetimi atıfsız cümleleri göremez; uydurma bulgu en çok burada saklanır.
    """
    sem = asyncio.Semaphore(3)

    async def judge(si: int):
        ks = [k for k, c in enumerate(claims) if c["section"] == si and not c["refs"] and not c["flag"]]
        if not ks:
            return
        listing = "\n".join(f"#{k}: {claims[k]['text']}" for k in ks)
        async with sem:
            out = await ask_json(pid, n, "veri sadakati denetimi (bulgu-sonuç karşılaştırması)", """Veri sadakati denetçisisin.
Her cümle için iki alan doldur:
1. "own": cümle, BU çalışmanın kendi verisi, örneklemi, ölçümü ya da tamamlanmış veri toplaması hakkında olgusal bir
   iddia mı? Amaç, gerekçe, plan ("yapılacak", "planlanmaktadır"), etik, öneri, sınırlılık, genel çerçeve,
   literatür özeti ve bölüm tanıtımı için false.
2. "in_results": own=true ise, iddia yazarın sonuçlarında açıkça karşılık buluyor mu? Basit doğru hesaplar
   (2/3 = %66,7) karşılık sayılır; yanlış hesap ya da sonuçlarda olmayan bulgu sayılmaz.""", f"""Yazarın sonuçları:
{results or '(yazar sonuç girmedi)'}

Bölüm: {sections[si]['title']}
Cümleler:
{listing}

JSON dizi döndür, her cümle için: [{{"id": numara, "own": true/false, "in_results": true/false, "note": "en çok 15 sözcük"}}]""",
                                 max_tokens=2500)
        for r in out if isinstance(out, list) else []:
            try:
                k = int(r["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if k in ks and r.get("own") is True and r.get("in_results") is False:
                claims[k]["flag"] = "not_in_results"
                claims[k]["note"] = r.get("note", "")

    progress(pid, n, "Veri sadakati denetimi")
    await asyncio.gather(*(judge(si) for si in range(len(sections))))


def summarize_claims(claims: list[dict]) -> dict:
    out = {"sentences": len(claims), "cited": 0, "yes": 0, "partial": 0, "no": 0, "cannot_access": 0,
           "needs_source": 0, "unknown_ref": 0, "not_in_results": 0}
    for c in claims:
        if c["refs"]:
            out["cited"] += 1
        if c["flag"]:
            out[c["flag"]] += 1
        for v in c["verdicts"].values():
            out[v["v"]] = out.get(v["v"], 0) + 1
    return out


# ---------------------------------------------------------------- 6. Görsel
def parse_csv(raw: str, max_rows: int = 500) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dialect = csv.Sniffer().sniff(raw[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))
    if len(rows) < 2:
        return None
    return {"columns": [c.strip() for c in rows[0]], "rows": rows[1:max_rows + 1]}


async def stage6(pid: str, opts: dict) -> dict:
    pr, card = _proj(pid), db.stage(pid, 1)["data"]
    exp, draft = db.stage(pid, 4)["data"], db.stage(pid, 5)["data"]
    progress(pid, 6, "Metodoloji şeması hazırlanıyor")
    method = next((s["text"] for s in draft.get("sections", []) if s["title"] in ("Yöntem", "Method")), "")
    dia = await ask_json(pid, 6, "metodoloji şeması (Mermaid)", f"""Akademik makaleler için metodoloji şeması çizen birisin.
Mermaid 'flowchart TD' sözdizimi kullan. Düğüm kimlikleri ASCII (A, B, C...), etiketler çift tırnak içinde,
etiketlerde parantez/köşeli parantez kullanma. 6-12 düğüm. Dil: {lang_name(pr['language'])}.""", f"""Araştırma sorusu: {card.get('research_question')}
Plan: {exp.get('plan')}
Yöntem bölümü: {method[:2500]}

JSON döndür: {{"mermaid": "flowchart TD\\n  A[\\"...\\"] --> B[\\"...\\"]", "caption": "şekil altyazısı"}}""",
                         max_tokens=1500)
    out = {"mermaid": dia.get("mermaid", ""), "mermaid_caption": dia.get("caption", ""), "charts": []}
    table = parse_csv(exp.get("csv", ""))
    if table:
        progress(pid, 6, "Veri grafikleri öneriliyor")
        sample = "\n".join([",".join(table["columns"])] + [",".join(r) for r in table["rows"][:15]])
        spec = await ask_json(pid, 6, "istatistik grafik önerisi", """Veri görselleştirme uzmanısın. Verilen tablo için
1-3 anlamlı grafik öner. Yalnız tablodaki sütun adlarını kullan.""", f"""Tablo (ilk satırlar):
{sample}

JSON döndür: {{"charts": [{{"type": "bar|line|scatter", "x": "sütun", "y": ["sütun"], "title": "başlık", "caption": "altyazı"}}]}}""",
                               max_tokens=1000)
        cols = set(table["columns"])
        out["charts"] = [c for c in spec.get("charts", []) if c.get("x") in cols and all(y in cols for y in c.get("y") or [])
                         and c.get("y")][:3]
        out["table"] = table
    return out


# ---------------------------------------------------------------- 7. Doğrulama
REVIEW_SYS = """Saygın bir dergide kör hakemlik yapıyorsun. Makaleyi titizlikle, yapıcı ama kayırmadan değerlendir.
Özellikle: araştırma sorusu-yöntem uyumu, kanıtların iddiaları taşıyıp taşımadığı, literatüre katkı, yazım ve yapı.
Atıfları [n] biçiminde görüyorsun; kaynakça ayrıca denetleniyor."""


async def stage7(pid: str, opts: dict) -> dict:
    pr, draft = _proj(pid), db.stage(pid, 5)["data"]
    sections = draft.get("sections") or []
    if not sections:
        raise ValueError("Önce 5. aşamada taslak üretilmeli")
    sel = db.sources(pid, selected_only=True)
    cited = {r for s in sections for r in text.cite_numbers(s["text"])}
    to_verify = [s for s in sel if s["i"] in cited]
    sem = asyncio.Semaphore(3)
    done = 0

    async def ver(s):
        nonlocal done
        p = s["paper"]
        async with sem:
            try:
                r = await verify_citation(Citation(title=p.get("title") or "", authors=p.get("authors") or [],
                                                   year=p.get("year"), doi=p.get("doi")))
            except Exception as ex:  # tek kaynağın hatası denetimi düşürmez
                r = {"status": "uncertain", "confidence": "low", "evidence": [], "notes": [f"hata: {ex}"]}
        db.update_source(pid, s["i"], verify=r)
        done += 1
        progress(pid, 7, f"Atıf doğrulama {done}/{len(to_verify)}")

    await asyncio.gather(*(ver(s) for s in to_verify))
    counts: dict[str, int] = {}
    for s in db.sources(pid, selected_only=True):
        if s["i"] in cited and s.get("verify"):
            counts[s["verify"]["status"]] = counts.get(s["verify"]["status"], 0) + 1

    progress(pid, 7, "Yerel benzerlik taraması")
    all_sents = [t for s in sections for t in text.sentences(s["text"])]
    # yalnız kaynağın kendi metni: bizim LLM notlarıyla örtüşme intihal riski değildir
    src_text = {s["i"]: s["paper"].get("abstract") or "" for s in sel}
    sim = text.similarity_report(all_sents, src_text)

    progress(pid, 7, "İki farklı modelle kör hakem simülasyonu")
    manuscript = "\n\n".join(f"## {s['title']}\n{s['text']}" for s in sections)[:28000]
    review_user = f"""Makale:
{manuscript}

JSON döndür:
{{"summary": "2-3 cümle özet", "strengths": ["..."], "weaknesses": ["..."], "questions": ["yazara sorular"],
 "decision": "accept | minor | major | reject", "required_changes": ["kabul için zorunlu değişiklikler"]}}
Dil: {lang_name(pr['language'])}."""

    async def review(model: str, name: str):
        try:
            r = await ask_json(pid, 7, f"hakem simülasyonu ({name})", REVIEW_SYS, review_user, model=model,
                               max_tokens=2500, fallback=False, timeout=240)
            return {"reviewer": name, "model": model, **r}
        except llm.LLMError as ex:
            return {"reviewer": name, "model": model, "error": str(ex)[:300]}

    reviews = await asyncio.gather(review(llm.model_main(), "Hakem A"), review(llm.model_reviewer(), "Hakem B"))
    return {"verification": counts, "cited": len(cited), "similarity": sim,
            "claims_summary": draft.get("claims_summary", {}), "reviews": list(reviews)}


# ---------------------------------------------------------------- 8. Gönderim
async def stage8(pid: str, opts: dict) -> dict:
    pr, card, draft = _proj(pid), db.stage(pid, 1)["data"], db.stage(pid, 5)["data"]
    prev = db.stage(pid, 8)["data"]
    venue = (opts.get("venue") or prev.get("venue") or "").strip()
    progress(pid, 8, "Başlık, öz ve anahtar kelimeler hazırlanıyor")
    manuscript = "\n\n".join(f"## {s['title']}\n{s['text']}" for s in draft.get("sections", []))[:20000]
    meta = await ask_json(pid, 8, "başlık, öz ve anahtar kelime önerisi", """Makaleyi dergiye hazırlayan bir editörsün.
Öz, metinde olmayan bulgu içermemeli; 150-250 sözcük.""", f"""Hedef dergi: {venue or 'belirtilmedi'}
Önerilen başlık: {card.get('title')}

Metin:
{manuscript}

JSON döndür: {{"title_tr": "...", "title_en": "...", "abstract_tr": "...", "abstract_en": "...",
"keywords_tr": ["3-6"], "keywords_en": ["3-6"]}}""", max_tokens=2500)
    return {**meta, "venue": venue, "generated_at": time.time()}


RUNNERS = {1: stage1, 2: stage2, 3: stage3, 4: stage4, 5: stage5, 6: stage6, 7: stage7, 8: stage8}
