"""Metin normalizasyonu: Türkçe karakterler, DOI, başlık/yazar karşılaştırma yardımcıları."""
from __future__ import annotations

import re
import unicodedata

_TR = str.maketrans({"ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s",
                     "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ç": "c", "Ç": "c"})
_STOP = {"the", "and", "of", "for", "with", "from", "into", "that", "this",
         "bir", "ile", "ve", "icin", "den", "dan", "des", "der", "die", "das", "und"}


def norm(text: str) -> str:
    text = (text or "").translate(_TR).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {w for w in norm(text).split() if len(w) > 2 and w not in _STOP}


def clean_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    doi = doi.strip().rstrip(".,;)")
    return doi.lower() or None


def surname(author: str) -> str:
    """'Soyad, Ad' ya da 'Ad Soyad' biçiminden soyadı çıkarır (normalize)."""
    author = (author or "").strip()
    if "," in author:
        part = author.split(",")[0]
    else:
        parts = author.split()
        part = parts[-1] if parts else ""
    words = norm(part).split()
    return words[-1] if words else ""


def _main_title(t: str) -> str:
    return re.split(r"[:?—–]", t or "", maxsplit=1)[0]


def title_match(cited: str, found: str) -> float:
    """0..1. Alt başlık atılmışsa ana başlık tam eşleşme sayılır ('Hyperobjects: ...' ~ 'Hyperobjects').
    Kısa bir başlığın atıf başlığının rastgele altkümesi olması tam eşleşme DEĞİLDİR."""
    a, b = tokens(cited), tokens(found)
    if not a or not b:
        return 0.0
    if a == b or tokens(_main_title(cited)) == b or tokens(_main_title(found)) == a:
        return 1.0
    # İki dilli kayıt başlığı ("TR başlık EN başlık"): atıftaki başlık bütünüyle içeride ve kayıt çok uzun değil
    if len(a) >= 4 and a <= b and len(b) <= 3 * len(a):
        return 1.0
    return len(a & b) / len(a | b)


def authors_match(cited_surnames: list[str], found_authors: list[str]) -> bool | None:
    """Atıftaki ilk yazarın soyadı kayıttaki yazarlar arasında mı? Kayıtta yazar yoksa None."""
    if not found_authors:
        return None
    if not cited_surnames:
        return None
    found = {surname(a) for a in found_authors}
    return cited_surnames[0] in found


def dedupe_key(doi: str | None, title: str, first_author: str, year: int | None) -> str:
    if doi:
        return "doi:" + (clean_doi(doi) or doi)
    return f"t:{' '.join(sorted(tokens(title)))[:120]}|{surname(first_author)}|{year or ''}"
