from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)  # "Soyad, Ad" ya da düz ad
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    url: str | None = None
    source: str = ""
    oa_url: str | None = None
    alt_titles: list[str] = field(default_factory=list)  # iki dilli kayıtlarda diğer dildeki başlıklar

    def to_dict(self) -> dict:
        return asdict(self)
