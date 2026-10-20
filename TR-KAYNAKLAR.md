# TR kaynak bağlayıcıları: erişim araştırması

Tarih: 2026-10-20 · Bağlı belgeler: `MCP-TASARIM.md` (§2), `PRD.md` (F8)

Yöntem: web araması + resmî uç noktalara az sayıda, salt-okunur, tanımlayıcı kullanıcı-ajanlı istek (araştırma sırasında toplam birkaç düzine istek, aralarda ≥2 sn). Kimlik doğrulaması gereken veya şart ihlali olabilecek hiçbir şey denenmedi.

## Özet

| Kaynak | Makinece erişim | Doğrulandı mı | Öneri |
|---|---|---|---|
| **TR Dizin** | Belgeli JSON arama API'si | ✅ Canlı denendi | **İlk bağlayıcı bu** |
| **DergiPark** | OAI-PMH (toplama protokolü, arama yok) | ✅ Canlı denendi | İkinci: seçili dergileri yerel dizine çekmek için |
| **YÖK Ulusal Tez Merkezi** | Resmî API/belge bulunamadı | ❌ | **Otomatik bağlayıcı yazma**; yalnız bağlantı üretici + elle içe aktarma |

## 1. TR Dizin (TÜBİTAK ULAKBİM)

**Resmî belge:** [TR Dizin entegrasyon geliştirme belgesi](https://development.trdizin.gov.tr/). Belge, arayüzdeki tüm verilerin "raw data" olarak JSON erişimine açık olduğunu söylüyor.

**Doğrulanan uç noktalar** (canlı yanıt alındı):
- Arama: `https://search.trdizin.gov.tr/api/defaultSearch/{publication|journal|author|institution}/?q=<sorgu>&order=relevance-DESC&page=1&limit=20`
  - `limit`: 10/20/50/100. `order`, `page`, `limit` zorunlu. URL'ler büyük/küçük harfe duyarlı. Facet filtreleri (`facet-publication_year`, `facet-database` …) var.
  - Yanıt Elasticsearch biçiminde: `hits.total.value`, `hits.hits[]._source`, `aggregations`.
- DOI ile arama: `q=<doi>` çalışıyor (örnek: `10.21602/sduarte.1480840` → Coşkun 2024, Art-e Sanat Dergisi).
- Belgedeki `…/api/public/{veriTipi}/{sorgu}/{değer}` (`?doi=`, `?issn=`, `?orcid=`) biçimini denedim: 404 döndü. Kesin yol belirsiz, **`q=` aramasını kullan**.

**Kayıt alanları (`_source`):** `doi`, `publicationYear`, `authors[].inPublicationName` (+ kurum), `abstracts[].title/abstract/keywords/language`, `journal{name,issn,eissn}`, `databases` (SCIENCE/SOCIAL), `accessType` (OPEN/…), `docType`, `language`, `references[]` (kaynakça), `citedReferences`, `otherCitations` (CrossRef/OpenAlex atıf sayıları), `downloadCount`, `viewCount`.

**Dikkat:**
- `orderTitle` boşlukları yutuyor ("Sanatve Tasarım…"). Başlık için `abstracts[].title` kullan.
- Arama bulanık: "Özselçuk" sorgusu 14.692 sonuç döndürdü, çoğu "Selçuk". Yazar/başlık eşleşmesini bizim `verify` katmanımız yapmalı.
- Kayıt gövdeleri büyük (3 sonuç ≈ 330 KB, `references` yüzünden). `limit` küçük tut.
- Çevrimiçi bir listede geçen OAI adresi (`oai-service.trdizin.gov.tr`) 20 sn'de zaman aşımı verdi: **doğrulanamadı**, gerekmiyor.
- **Şartlar:** belgede hız sınırı, kullanım şartı veya kimlik doğrulama bilgisi yok. robots.txt yalnız `/wp-admin/`'i kısıtlıyor (API alt alanını kapsamıyor). Belge "değişiklikleri takip et" aboneliği sunuyor, API değişebilir. Üretimde kullanmadan önce ULAKBİM'e kullanım koşullarını sormak doğru olur.

**Menekşe makalesi için yan bulgular (canlı sorgular):**
- Hedef dergi **Sanat & Tasarım Dergisi** (e-ISSN 2146-9059) TR Dizin'de kayıtlı ve etkin (`id: 1021`, ilk yayın 2011). Bu, "TR Dizin" iddiasını destekler. **ESCI'yi göstermez**; o hâlâ Clarivate MJL'de teyit edilmeli.
- **Özselçuk (2023)** TR Dizin'de bulunamadı. DergiPark'ta elle bakmak gerekiyor (kontrol listesinde zaten ilk sırada).

## 2. DergiPark

**Uç nokta:** `https://dergipark.org.tr/api/public/oai/` (OAI-PMH 2.0, yönetici: `oai@dergipark.org.tr`). Üçüncü taraf bir MCP projesinin README'sinde de aynı yol geçiyor, resmî belge bulamadım.

**Doğrulanan fiiller:** `Identify`, `ListMetadataFormats` (`oai_dc`, `oai_etdms`…), `ListSets` (≈83 KB, dergi başına bir set: `mulkiye` = Mülkiye Dergisi …), `ListRecords&metadataPrefix=oai_dc&from=…` (≈600 KB sayfa; başlık TR+EN, yazar, konu, özet, anahtar kelime). `GetRecord` denenmedi.

**robots.txt:** `/search`, `/login` yasak; `/api/public/oai/` yasak değil. Yani sitenin arama sayfasını **kazımak yasak/uygunsuz**, OAI kullanımı serbest görünüyor.

**Sınır:** OAI-PMH **arama değil toplama protokolü**: anahtar kelimeyle sorgulama yok. İki kullanım:
1. **Yerel dizin:** ilgili dergilerin setlerini toplayıp SQLite FTS5'e koy, `from=` ile artımlı güncelle. İlk toplama pahalı (sayfa başı ~600 KB) ve nazik hızla yapılmalı. Önce 3–5 hedef dergi (örn. sanat/tasarım) ile sınanmalı.
2. **Tek kayıt doğrulama:** makale kimliği biliniyorsa `GetRecord` (denenmedi).

**Not:** TR Dizin DergiPark dergilerinin çoğunu zaten indeksliyor. Arama için TR Dizin yeterli olabilir; DergiPark OAI yalnız TR Dizin'de olmayan dergiler için gerekir.

## 3. YÖK Ulusal Tez Merkezi

- Resmî API/toplu veri belgesi **bulunamadı**. `robots.txt` yok (404). SSS sayfasında otomatik erişim, bot, API veya yeniden kullanım hakkında **hiçbir ifade yok**; altbilgide "Tüm hakları saklıdır" var.
- Üçüncü taraf bir GitHub aracı (`mytunca/theses`) tarayıcıda kazıma yapıyor ve kendi notunda YÖK kullanım koşullarına uyulması gerektiğini söylüyor. Tek aramada en fazla 2000 sonuç döndüğü belirtilmiş.
- Tam metin yalnız yazarın izin verdiği tezlerde açık; künye ve özet herkese açık.

**Karar:** Şartlar belirsiz ve resmî bir makine arayüzü yok, bu yüzden **otomatik tarama bağlayıcısı yazmıyoruz.** Yapılacaklar:
- Sorgu için tez arama bağlantısı üretmek (kullanıcı tarayıcıda kendisi arar).
- Kullanıcının elle aktardığı tez künyelerini (BibTeX/CSV) `verify_citation` ve beyan akışına almak.
- İsteğe bağlı: YÖK Dokümantasyon Dairesi'ne API/toplu erişim talebi göndermek.

## Önerilen yapım sırası
1. **`trdizin` bağlayıcısı** (`search_sources` kaynağı olarak): `defaultSearch/publication`, `limit≤20`, başlığı `abstracts[].title`'dan al, DOI/yazar/yıl/dergi/özet eşle. İstekler arası ≥1 sn, 429/5xx'te geri çekilme, tanımlayıcı kullanıcı-ajanı.
2. **`verify_citation` TR yedeği:** Crossref/OpenAlex'te bulunmayan Türkçe atıfları TR Dizin'de ara. Altın küme için Özselçuk, Çakıroğlu, Çelenk & Kurak Açıcı gibi gerçek Türkçe atıflar kullanılabilir.
3. **DergiPark OAI toplayıcı** (ayrı komut, `harvest`): seçili setler → SQLite FTS5, artımlı `from`.
4. **YÖK:** yalnız bağlantı üretici + elle içe aktarma.

## Açık sorular
- ULAKBİM: TR Dizin API'si için yazılı kullanım koşulu/hız sınırı var mı? (e-posta ile sorulabilir)
- DergiPark: OAI için hız sınırı ve toplu toplama politikası? (`oai@dergipark.org.tr`)
- YÖK: otomatik künye erişimi için izin veya API var mı?
