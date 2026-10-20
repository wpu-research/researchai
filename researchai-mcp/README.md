# researchai-mcp

Akademik kaynak arama, atıf doğrulama ve YZ kullanım beyanı için MCP sunucusu (stdio). Tasarım: `../MCP-TASARIM.md`, gereksinimler: `../PRD.md`.

## Araçlar
| Araç | Ne yapar |
|---|---|
| `search_sources` | OpenAlex, Crossref, Semantic Scholar, arXiv ve **TR Dizin**'de arar; tekilleştirir; kaynak hatalarını yalıtır |
| `verify_citation` | Atıfı DOI veya başlık+yazar+yıl ile doğrular: `verified` / `uncertain` / `mismatch` / `not_found` |
| `log_ai_use` | Aşama başına YZ kullanımını `runs/<run_id>/ai_use_log.jsonl` dosyasına yazar |
| `generate_disclosure` | Günlükten TR/EN beyan metni ve tablo üretir; insan incelemesi olmayan aşamaları açıkça yazar |

## Kurulum ve çalıştırma
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q                 # çevrimdışı birim testler
python golden/run_golden.py         # canlı altın küme (ağ gerekir)
```
Claude Code'a eklemek (isteğe bağlı, kullanıcı ayarını değiştirir):
```bash
claude mcp add researchai -- /home/wpu/Desktop/Urunler/ResearchAI/researchai-mcp/.venv/bin/python -m researchai_mcp.server
```

## Ortam değişkenleri (hepsi isteğe bağlı)
`S2_API_KEY`, `OPENALEX_API_KEY` (hız sınırı için), `RESEARCHAI_MAILTO` (Crossref/OpenAlex "polite pool"; ayarlanmazsa hiçbir e-posta gönderilmez), `RESEARCHAI_RUNS_DIR` (varsayılan `./runs`).

## Doğrulama kuralları
- Güçlü eşleşme: başlık ≥0,8, **yazar doğrulanmış**, yıl farkı ≤1. Yazarı olmayan kayıt güçlü eşleşme sayılmaz.
- `not_found` ve `mismatch`, atıfın uydurma olduğunu **kanıtlamaz**; insan kontrolü gerekir.
- Yüksek güven için en az 2 bağımsız kaynak gerekir.

## Altın küme sonucu (24 atıf, 2026-10-20)
- Geçerli 13 atıf (3'ü Türkçe): 9 `verified`, 4 `uncertain` (basım yılı farkı: Koerner, Nye, Palinkas; yazarsız Crossref kaydı: Çelenk & Kurak Açıcı).
- Yazarı değiştirilmiş 7 atıf ve uydurma 4 atıf (1'i Türkçe): hepsi `not_found`, yanlış `verified` yok.
- Küme küçük ve çoğunlukla bu makalenin atıflarından oluşuyor; genel başarı oranı olarak okunmamalı.

## DergiPark yerel dizini
OAI-PMH arama yapmadığı için seçili dergiler önce `data/dergipark.sqlite` (FTS5) içine toplanır. Dizin doluysa `search_sources` ve `verify_citation` onu otomatik olarak kullanır.
```bash
researchai-harvest set marustd akademiksanat   # dergi kodu = URL'deki /pub/<kod>
researchai-harvest status
researchai-harvest search "Osmanlı minyatür"
```
- `ListSets` sunucuda 100 kümede kesiliyor ve token vermiyor. Listede olmayan dergiler de `set <kod>` ile çekilebilir.
- `from/until` süzgeci datestamp'e göre tutarlı çalışmıyor. Bu yüzden dergi bazlı `set` toplaması önerilir.
- Bazı kayıtlarda `dc:date` bozuk (`0201`, `1067`) ya da boş. 1900–2100 dışındaki yıllar boş bırakılır.
- Deneme (2026-10-20): 5 sanat/tasarım dergisi, 1355 kayıt, yaklaşık 30 sn, hata yok. DOI'siz 1967 tarihli bir makale yalnız bu dizinle `verified` çıktı.

## Bilinen sınırlar
- Kitap ve galeri/web kaynakları çoğunlukla Crossref'te yok, `uncertain`/`not_found` çıkar.
- `check_claim_support` ve `venue_profile` henüz yok. YÖK Tez için otomatik bağlayıcı bilerek yazılmadı (bkz. `../TR-KAYNAKLAR.md`).
- TR Dizin: belgede hız sınırı/şart yok, bağlayıcı istekler arası ≥1 sn bekler. Noktalamalı sorgulara sonuç vermediği için sorgu temizlenir; tüm terimleri birlikte aradığından (AND) boş sonuçta en uzun 3, sonra 2 sözcükle yeniden denenir; arama bulanıktır, eşleştirmeyi `verify_citation` yapar.
- Ön bellek yalnız bellekte (süreç ömrü boyunca).
