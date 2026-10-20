"""Deterministik metin araçları: atıf ayrıştırma, yerel benzerlik, BibTeX/APA/LaTeX çıktısı."""
from __future__ import annotations

import re
import unicodedata

_CITE = re.compile(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ\"“(\[])")


def cite_numbers(s: str) -> list[int]:
    """'[3]', '[2, 5]', '[4-6]' → sayı listesi (sırayı korur, tekrarsız)."""
    out: list[int] = []
    for grp in _CITE.findall(s):
        for part in re.split(r"\s*[,;]\s*", grp):
            m = re.match(r"(\d+)\s*[–-]\s*(\d+)$", part)
            nums = range(int(m.group(1)), int(m.group(2)) + 1) if m and int(m.group(2)) - int(m.group(1)) < 20 \
                else [int(x) for x in re.findall(r"\d+", part)]
            for x in nums:
                if x not in out:
                    out.append(x)
    return out


def sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        para = para.strip()
        if not para or para.startswith("#"):
            continue
        out += [s.strip() for s in _SENT.split(para) if s.strip()]
    return out


def _words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s).lower()
    s = _CITE.sub(" ", s)
    return re.findall(r"\w+", s)


def shingles(s: str, k: int = 5) -> set[tuple]:
    w = _words(s)
    return {tuple(w[i:i + k]) for i in range(len(w) - k + 1)}


def similarity_report(draft_sentences: list[str], sources: dict[int, str], k: int = 5,
                      threshold: float = 0.35) -> list[dict]:
    """Taslak cümlesinin 5'li sözcük dizilerinin kaynak metinlerde geçme oranı (içerme).

    Yalnız erişilebilen özet/not metinleriyle karşılaştırır; tam metin intihal servisi değildir.
    """
    src_sh = {i: shingles(t, k) for i, t in sources.items() if t}
    flags = []
    for idx, s in enumerate(draft_sentences):
        sh = shingles(s, k)
        if len(sh) < 3:
            continue
        best_i, best = None, 0.0
        for i, ssh in src_sh.items():
            c = len(sh & ssh) / len(sh)
            if c > best:
                best_i, best = i, c
        if best >= threshold:
            flags.append({"sentence_index": idx, "sentence": s, "source": best_i, "overlap": round(best, 2)})
    return flags


# --- kaynakça biçimleri ---

def _split_name(a: str) -> tuple[str, str]:
    a = a.strip()
    if "," in a:
        last, first = [x.strip() for x in a.split(",", 1)]
    else:
        parts = a.split()
        last, first = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (a, "")
    return last, first


def _initials(first: str) -> str:
    return " ".join(p[0] + "." for p in re.split(r"[\s-]+", first) if p)


def apa(p: dict) -> str:
    names = [_split_name(a) for a in (p.get("authors") or [])]
    au = [f"{l}, {_initials(f)}".strip(", ") for l, f in names]
    if len(au) > 20:
        au = au[:19] + ["…", au[-1]]
    authors = ", ".join(au[:-1]) + (", & " if len(au) > 1 else "") + au[-1] if au else ""
    year = f"({p['year']})" if p.get("year") else "(t.y.)"
    title = (p.get("title") or "").rstrip(".")
    venue = f" *{p['venue']}*." if p.get("venue") else ""
    link = f" https://doi.org/{p['doi']}" if p.get("doi") else (f" {p['url']}" if p.get("url") else "")
    return f"{authors} {year}. {title}.{venue}{link}".strip()


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def bibkey(p: dict, used: set[str]) -> str:
    last = _split_name((p.get("authors") or ["anon"])[0])[0]
    first_word = next((w for w in _words(p.get("title") or "") if len(w) > 3), "x")
    base = re.sub(r"[^a-z0-9]", "", _ascii(f"{last}{p.get('year') or ''}{first_word}").lower()) or "ref"
    key, n = base, 1
    while key in used:
        n += 1
        key = f"{base}{chr(96 + n)}"
    used.add(key)
    return key


def _bibesc(s: str) -> str:
    return (s or "").replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}").replace("&", "\\&") \
        .replace("%", "\\%").replace("$", "\\$").replace("#", "\\#").replace("_", "\\_")


def bibtex(p: dict, key: str) -> str:
    f = {"title": "{" + _bibesc(p.get("title") or "") + "}",
         "author": " and ".join(_bibesc(a) for a in p.get("authors") or []),
         "year": str(p.get("year") or ""), "journal": _bibesc(p.get("venue") or ""),
         "doi": p.get("doi") or "", "url": p.get("url") or ""}
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in f.items() if v)  # başlık çift süslü: büyük harf korunur
    return f"@article{{{key},\n{body}\n}}"


def renumber(sections: list[dict]) -> tuple[list[dict], list[int]]:
    """Kaynak kimliklerini ([i]) metindeki ilk geçiş sırasına göre [1..n]'ye çevirir."""
    order: list[int] = []
    for s in sections:
        for i in cite_numbers(s.get("text", "")):
            if i not in order:
                order.append(i)
    m = {i: k + 1 for k, i in enumerate(order)}

    def sub(match):
        nums = cite_numbers(match.group(0))
        return "[" + ", ".join(str(m[x]) for x in nums if x in m) + "]"

    return [{**s, "text": _CITE.sub(sub, s.get("text", ""))} for s in sections], order


_LATEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                  "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def latex_escape(s: str) -> str:
    return "".join(_LATEX_SPECIAL.get(ch, ch) for ch in s)


def to_latex(title: str, abstract: str, sections: list[dict], keys: dict[int, str], lang: str) -> str:
    """[i] atıflarını \\cite{key}'e çevirir; biblatex + references.bib ile derlenir."""
    def body(t: str) -> str:
        out = []
        for para in re.split(r"\n\s*\n", t.strip()):
            esc = latex_escape(para.strip())
            esc = re.sub(r"\*\*(.+?)\*\*", lambda m: r"\textbf{" + m.group(1) + "}", esc)
            esc = re.sub(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]",
                         lambda m: r"\cite{" + ",".join(keys[i] for i in cite_numbers(m.group(0)) if i in keys) + "}",
                         esc)
            out.append(esc)
        return "\n\n".join(out)

    babel = "turkish" if lang == "tr" else "english"
    secs = "\n\n".join(f"\\section{{{latex_escape(s['title'])}}}\n{body(s.get('text', ''))}" for s in sections)
    return f"""\\documentclass[12pt]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage[{babel}]{{babel}}
\\usepackage[style=apa,backend=biber]{{biblatex}}
\\addbibresource{{references.bib}}
\\title{{{latex_escape(title)}}}
\\date{{}}
\\begin{{document}}
\\maketitle
\\begin{{abstract}}
{latex_escape(abstract or '')}
\\end{{abstract}}

{secs}

\\printbibliography
\\end{{document}}
"""
