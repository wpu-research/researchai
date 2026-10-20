# researchai-web

Fikirden makaleye 8 aşamalı, insan kapılı araştırma hattı (FastAPI + SQLite + derlemesiz arayüz).
Kaynak arama, atıf doğrulama ve beyan için `../researchai-mcp` kütüphanesini kullanır.

Canlı: https://researchai-production-a364.up.railway.app (Railway projesi `researchai`, volume `/data`)

## Aşamalar
| # | Aşama | Ne yapar |
|---|---|---|
| 1 | Fikir | Kapsam kartı: araştırma sorusu, ölçütler, arama sorguları (düzenlenebilir) |
| 2 | Literatür | 6 kaynakta tarama, tekilleştirme, LLM ile 0-3 ilgi puanı; seçim elle |
| 3 | Sentez ⚑ | Özetlerden not, temalar, boşluk haritası, hipotez seçimi |
| 4 | Deney/Veri ⚑ | Yöntem planı önerisi; **sonuçları yazar girer** (deney kodu çalıştırılmaz) |
| 5 | Taslak | Bölüm bölüm yazım; iddia-kaynak denetimi + veri sadakati denetimi |
| 6 | Görsel | Mermaid metodoloji şeması, CSV'den Chart.js grafikleri |
| 7 | Doğrulama ⚑ | `verify_citation`, yerel 5-gram benzerlik, iki farklı modelle kör hakem |
| 8 | Gönderim | Başlık/öz/anahtar kelime; .md, .tex (biblatex APA), .bib, YZ beyanı |

⚑ İnsan kapısı: onay için en az 15 karakterlik gerekçe gerekir; not beyana girer.
Bir aşama yeniden çalıştırılır ya da düzenlenirse o ve sonraki aşamaların onayı düşer.

## Dürüstlük önlemleri
- Atıflar yalnız seçili kaynak numaralarıyla ([i]) yapılır; her atıflı cümle kaynağın özetiyle denetlenir.
- Bulgular/Çözümleme yöntem planını görmeden, yalnız yazarın girdiği sonuçlardan yazılır; atıfsız cümleler
  sonuçlarla karşılaştırılır ve karşılığı olmayan bulgu iddiaları işaretlenir.
- Benzerlik denetimi yalnız kaynak özetleriyle yapılır; tam metin intihal raporu yerine geçmez.
- Denetimler LLM tabanlıdır, kaçırabilir ve yanlış işaretleyebilir: her bayrağa insan bakmalıdır.

## Yerelde çalıştırma
```bash
python3 -m venv .venv && .venv/bin/pip install -e ../researchai-mcp -e ".[dev]"
set -a && . ./.env && set +a   # ANTHROPIC_API_KEY, ANTHROPIC_WORKSPACE_ID (git'e girmez)
RESEARCHAI_DATA=./data .venv/bin/uvicorn app.main:app --port 8765
.venv/bin/python -m pytest -q
```

## Ortam değişkenleri
`ANTHROPIC_API_KEY` (zorunlu), `ANTHROPIC_WORKSPACE_ID` (anahtar bir workspace'e bağlı değilse zorunlu),
`RESEARCHAI_MODEL` (varsayılan `claude-opus-5-5`) / `RESEARCHAI_MODEL_FAST` (`claude-haiku-5-5`) /
`RESEARCHAI_MODEL_REVIEWER` (`claude-sonnet-5-5`, Hakem B),
`RESEARCHAI_DATA` (varsayılan `data`), `DERGIPARK_SETS` (açılışta dizin boşsa toplanan dergiler),
`DERGIPARK_AUTOHARVEST=0` (otomatik toplamayı kapatır).

## Bilinen sınırlar
- Erişim koruması yok: adresi bilen herkes kullanabilir ve Anthropic API bakiyesini harcayabilir.
- Uzun işler süreç içinde çalışır; sunucu yeniden başlarsa yarıdaki aşama "hata" olur, yeniden çalıştırılır.
