# ResearchAI

Ham fikirden hedef dergiye gönderilebilir taslak makaleye giden, insan onay kapılı ve yapay zekâ kullanımını kayda geçiren araştırma hattı. Amaç yazarın yerine geçmek değil, kararlarını hızlandırmak ve her adımı denetlenebilir kılmaktır (bkz. `PRD.md`).

## Alt projeler
- `researchai-mcp/`: MCP sunucusu (stdio). Araçlar: `search_sources` (OpenAlex, Crossref, Semantic Scholar, arXiv, TR Dizin), `verify_citation` (atıf doğrulama), `log_ai_use`, `generate_disclosure` (TR/EN YZ kullanım beyanı). DergiPark için yerel FTS5 dizini (`researchai-harvest`).
- `researchai-web/`: 8 aşamalı web arayüzü (fikir, literatür, sentez, deney/veri, taslak, görsel, doğrulama, gönderim). Sentez, deney ve doğrulama aşamaları insan onayı ister. Çıktılar: .md, .tex, .bib, YZ beyanı.
- `AutoResearchClaw/`: ayrı, MIT lisanslı harici bir proje. Kendi `.git` deposu vardır ve bu depoya dahil değildir; burada içeriği ele alınmaz.
- `pilot-menekse/`: pilot çalışma çıktıları (atıf raporu, pilot raporu, doğrulama betiği)
- `PRD.md`, `MCP-TASARIM.md`, `TR-KAYNAKLAR.md`: gereksinim, MCP tasarımı ve Türkçe kaynak erişimi araştırması

## Teknoloji
Python >= 3.11, FastAPI + Uvicorn, SQLite, httpx, `mcp` SDK, Anthropic SDK; derlemesiz (build adımsız) arayüz. Docker imajı kökteki `Dockerfile` ile oluşturulur (Railway dağıtımı için hazırlanmış).

## Kurulum ve çalıştırma
```bash
# MCP sunucusu
cd researchai-mcp && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && python -m pytest -q

# Web arayüzü
cd researchai-web && python3 -m venv .venv && .venv/bin/pip install -e ../researchai-mcp -e ".[dev]"
RESEARCHAI_DATA=./data .venv/bin/uvicorn app.main:app --port 8765
```
Ayrıntılar alt projelerin kendi README dosyalarındadır.

## Ortam değişkenleri
Yalnızca adlar:
- `ANTHROPIC_API_KEY` (web için zorunlu), `ANTHROPIC_WORKSPACE_ID`
- `RESEARCHAI_MODEL`, `RESEARCHAI_MODEL_FAST`, `RESEARCHAI_MODEL_REVIEWER`
- `RESEARCHAI_DATA`, `RESEARCHAI_DB`, `RESEARCHAI_RUNS_DIR`, `RESEARCHAI_MAILTO`
- `S2_API_KEY`, `OPENALEX_API_KEY`
- `DERGIPARK_SETS`, `DERGIPARK_AUTOHARVEST`

## Bilinen sınırlar
Web uygulamasında erişim koruması yoktur (alt README'ye göre); atıf ve benzerlik denetimleri her bayrak için insan kontrolü gerektirir.

Lisans: kök için belirtilmemiş. `AutoResearchClaw/` kendi MIT lisansı altındadır.
