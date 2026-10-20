# ResearchAI MCP — Tasarım Taslağı

Sürüm: 0.1 · Tarih: 2026-10-20 · Bağlı belge: `PRD.md`

Amaç: Hazır araçların vermediği üç şeyi tek bir MCP sunucusu (`researchai-mcp`) ve ona eşlik eden bir skill olarak eklemek:

1. **Kaynak katmanı** (TR + uluslararası, tek arayüz)
2. **Atıf denetimi** (ikinci, bağımsız denetçi)
3. **Beyan modülü** (AI kullanım kaydı ve dergi formatında beyan)

AutoResearchClaw bu araçları MCP üzerinden çağırabilir (`researchclaw mcp` komutu var) ve Claude Code doğrudan kullanabilir.

## 1. Araçlar (tools)

### 1.1 `search_sources`
```
girdi : { query, sources[] = ["semantic_scholar","openalex","arxiv","crossref","dergipark","trdizin","yok_tez"],
          year_from?, year_to?, lang?, limit=40 }
çıktı : [{ id, title, authors[], year, venue, doi?, abstract?, url, source, oa_url? }]
```
- Kaynaklar arası tekilleştirme: önce DOI, yoksa normalize başlık + ilk yazar + yıl.
- Hız sınırı ve önbellek (SQLite). Her sonuç hangi kaynaktan geldiğini taşır.

### 1.2 `verify_citation`
```
girdi : { bibtex | {title, authors[], year, venue?, doi?} }
çıktı : { status: "verified" | "mismatch" | "not_found" | "uncertain",
          evidence: [{ source, matched_fields[], diff[] }], confidence }
```
Doğrulama sırası (hepsi kayıt altında):
1. DOI varsa Crossref/DataCite çözümlemesi.
2. Başlık + yazar eşleşmesi Semantic Scholar ve OpenAlex'te.
3. **Yazar uyuşmazlığı güçlü sinyal olarak** ağırlıklandırılır. Literatürde sahte atıfların çoğu yazar uyuşmazlığıyla yakalanıyor, başlık benzerliği tek başına zayıf.
4. Yalnız çelişki varsa LLM ile ilgi/bağlam puanı.

Kurallar:
- `uncertain` ve `mismatch` çıktıları **otomatik silinmez**, insana gösterilir. Doğrulayıcılar hem kaçırır hem yanlış işaretler (HALLMARK bulgusu).
- Atıfın cümleyi gerçekten desteklediği ayrıca kontrol edilir: `check_claim_support`.

### 1.3 `check_claim_support`
```
girdi : { sentence, citation_id }
çıktı : { supported: yes | partial | no | cannot_access, passage?, note }
```
Kaynağın tam metni (açık erişim) veya özeti çekilir. Erişilemiyorsa `cannot_access`, tahmin üretilmez.

### 1.4 `log_ai_use`
```
girdi : { run_id, stage, tool, model, purpose, human_review: bool, notes? }
çıktı : { entry_id }
```
Her aşama bittiğinde (elle veya hook ile) çağrılır. Kayıt koşu klasöründe `ai_use_log.jsonl` olarak tutulur.

### 1.5 `generate_disclosure`
```
girdi : { run_id, venue_profile?, language = "tr" | "en" }
çıktı : { statement_md, table_md, warnings[] }
```
- Günlükten **tarafsız bir beyan metni** üretir: hangi aşamada hangi araç/model kullanıldı, insanın neyi gözden geçirdiği.
- `venue_profile` verilirse dergi biçimine uyar (ör. Methods bölümü cümlesi, teşekkür notu).
- `warnings`: insan incelemesi işaretlenmemiş aşama varsa uyarır. Beyan metni gerçeği yansıtmak zorundadır, gerçeği iyileştiren bir araç değildir.

### 1.6 `venue_profile` (iyi olur)
Dergi/konferans için şablon, kelime sınırı, atıf stili ve AI politikası tutar. Politika metni **kaynak URL ve tarihle** saklanır, süresi geçen kayıt uyarı verir.

## 2. Kaynak bağlayıcıları

| Bağlayıcı | Yol | Durum |
|---|---|---|
| Semantic Scholar, OpenAlex, arXiv, Crossref | Resmî REST API | Hazır, düşük risk |
| DergiPark | Dergi başına OAI-PMH uç noktası olması muhtemel | ⚠️ Doğrulanmadı. Arama sonuç vermedi, belgeyi/uç noktayı elle teyit et |
| TR Dizin | Bilinmiyor | ⚠️ API/toplu erişim koşulları doğrulanmadı |
| YÖK Ulusal Tez Merkezi | Bilinmiyor | ⚠️ Otomatik erişim kullanım koşullarına tabidir, taramadan önce şartları oku. Gerekirse yalnız elle arama + içe aktarma |

**İlk iş:** Bu üç TR kaynağı için resmî erişim yolunu ve kullanım şartlarını teyit et (yarım gün). Sonuca göre yalnız OAI-PMH/API ile ilerle, şartlara aykırı kazıma yapma.

## 3. Mimari

```
Claude Code ─┐
             ├─ MCP (stdio) ─ researchai-mcp ─┬─ connectors/  (s2, openalex, arxiv, crossref, tr_*)
AutoResearchClaw ─┘                            ├─ verify/      (atıf + iddia denetimi)
                                               ├─ disclosure/  (günlük + üretici)
                                               └─ store/       (SQLite önbellek, runs/<id>/)
```

- Dil: Python (AutoResearchClaw ile aynı ekosistem), resmî MCP SDK.
- Taşıma: stdio (yerel). Uzak sunucu gerekmez.
- Tüm çıktılar `runs/<run_id>/` altında JSON olarak saklanır, beyan ve doğrulama izlenebilir.

## 4. Skill: `research-pipeline`

MCP araçlarının ne zaman, hangi sırayla çağrılacağını anlatan skill:

1. Fikir kartı → `search_sources`
2. Her taslak bölümü sonrası → `verify_citation` + `check_claim_support`
3. Her aşama sonunda → `log_ai_use`
4. Gönderim öncesi → `generate_disclosure`, uyarı varsa durur
5. `uncertain` / `mismatch` sonuçlarını **kullanıcıya listeler**, kendisi karar vermez

## 5. Test planı

- **Altın küme:** Bilinen doğru 50 atıf + bilinen sahte 50 atıf (uydurma yazar/başlık, yazar değiştirilmiş gerçek başlık, yıl/venue hatası). Hedef: sahte yakalama ve yanlış alarm oranı ölçülür, eşik buna göre ayarlanır.
- Dış referans: HALLMARK ve CiteAudit benzeri açık kıyaslama kümeleri.
- Birim testler: tekilleştirme, DOI çözümleme, yazar normalizasyonu (Türkçe karakterler: ı/İ, ğ, ş, ö, ü, ç).

## 6. Yapım sırası

1. İskele + `search_sources` (S2, OpenAlex, arXiv, Crossref)
2. `verify_citation` + altın küme testi
3. `log_ai_use` + `generate_disclosure`
4. TR bağlayıcıları (erişim teyidinden sonra)
5. `check_claim_support`, `venue_profile`
6. Skill ve AutoResearchClaw MCP bağlantısı

## 7. Sınırlar

- Araç sahte atıfı **kanıtlayamaz**, yalnız şüpheyi ve kanıtı gösterir.
- Beyan modülü yazarın sorumluluğunu devretmez. Metni yazar gözden geçirir ve imzalar.
- Türkçe kaynaklarda bibliyografik veri kalitesi değişken olabilir, `uncertain` oranı yüksek çıkabilir.
