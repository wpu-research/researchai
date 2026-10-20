# ResearchAI — Ürün Gereksinim Belgesi (PRD)

Sürüm: 0.1 taslak · Tarih: 2026-10-20 · Sahip: Murat Arslan

## 1. Amaç

Ham fikirden hedef dergiye gönderilebilir taslak makaleye kadar giden, **insan kapılı** ve **AI kullanımını dürüstçe kayda geçiren** bir araştırma hattı. Araç yazarın yerine geçmez. Yazarın kararlarını hızlandırır ve her adımı denetlenebilir kılar.

## 2. Problem

- Literatür, deney, yazım ve doğrulama ayrı araçlara dağılmış durumda.
- LLM'ler sahte atıf üretiyor. NeurIPS 2025'te hakem denetiminden geçmiş makalelerde bile 100 uydurma atıf bulundu.
- Dergi ve arXiv politikaları sıkılaşıyor (arXiv: denetlenmemiş AI içeriğine bir yıl yasak). Beyan çoğu zaman elle ve eksik yapılıyor.
- Türkçe/yerel kaynaklar (DergiPark, TR Dizin, YÖK Tez) uluslararası araçlarda yok.

## 3. Hedef kullanıcı

Birincil: Murat (araştırmacı mühendis). Örnek projeler: Jana (ECtHR makalesi), Menekşe hoca makalesi, Sexual Education SLR, MIYOKAP. İkincil: ileride ekip arkadaşları.

## 4. Kapsam

### Kapsam içi
| # | Aşama | Çekirdek yetenek |
|---|---|---|
| 1 | Fikir | Tezgâh/vault'tan araştırma sorusu ve kapsam kartı |
| 2 | Literatür | Çoklu kaynak tarama, tekilleştirme, eleme, yapılandırılmış çıkarım |
| 3 | Sentez/Hipotez | Boşluk haritası, hipotez önerisi |
| 4 | Deney/Veri | Sandbox'ta deney (Docker), tekrarlanabilir kayıt |
| 5 | Taslak | Kanıta bağlı taslak (her cümle bir kaynak pasajına bağlı) |
| 6 | Görsel | Metodoloji şeması, istatistik grafik |
| 7 | Doğrulama | Atıf denetimi, benzerlik raporu, çok model hakem simülasyonu |
| 8 | Gönderim | BibTeX, dergi şablonu, AI kullanım beyanı |

### Kapsam dışı (bilinçli)
- **AI-tespit atlatma / "footprint removal"**. Kural olarak yapılmaz.
- Yazarın yerine otomatik gönderim.
- Fikri mülkiyet gerektiren kapalı veri tabanlarının kaçak kullanımı.

## 5. Mimari karar: kur, yazma

Sıfırdan yazmak yerine mevcut araçları sarmalıyoruz:

| Katman | Araç | Rol |
|---|---|---|
| Orkestrasyon | AutoResearchClaw (23 aşama, ACP ile Claude Code) | Ana boru hattı |
| Literatür | Semantic Scholar, OpenAlex, arXiv; PaperQA2 / Elicit (isteğe bağlı) | Kaynak ve sentez |
| Deney | AutoResearchClaw sandbox; gerekirse AI Scientist-v2 | Kod/deney |
| Görsel | PaperBanana (diyagram), matplotlib (grafik) | Şekiller |
| Doğrulama | AutoResearchClaw CITATION_VERIFY + ek denetçi (bkz. MCP-TASARIM.md) | Atıf güvenliği |
| Hafıza | obsidian-mind vault, Cognee | Bulgu ve karar kaydı |
| **Bizim ekleyeceğimiz** | Kaynak katmanı (TR), beyan modülü, hakem simülasyonu | Ayırt edici değer |

## 6. Özellik gereksinimleri

**Z = zorunlu, İ = iyi olur.**

| ID | Gereksinim | Öncelik |
|---|---|---|
| F1 | Her koşu için tek klasör: girdi, ara çıktılar, kaynaklar, günlük | Z |
| F2 | Onay kapıları: literatür seçimi, deney tasarımı, son kalite | Z |
| F3 | Her atıf en az iki bağımsız kaynakta (DOI/başlık+yazar) doğrulanır; doğrulanamayan atıf metinden çıkarılmaz, **işaretlenir** | Z |
| F4 | Maliyet sınırı: koşu başına USD bütçesi, aşınca duraklar | Z |
| F5 | AI kullanım beyanı: hangi aşama AI, hangisi insan; dergi formatında metin üretir | Z |
| F6 | Çok model hakem simülasyonu (en az 2 farklı model, kör) | İ |
| F7 | Hedef dergi profili: şablon, kelime sınırı, atıf stili, AI politikası | İ |
| F8 | DergiPark / TR Dizin / YÖK Tez kaynakları | İ |
| F9 | Koşuyu kaldığı yerden sürdürme (`--resume`) | Z |
| F10 | Benzerlik raporu (harici servis veya yerel yaklaşım) | İ |

## 7. Başarı ölçütleri

- Pilot koşuda **sıfır doğrulanamayan atıf** taslağa insan onayı olmadan girmez.
- Fikirden ilk taslağa süre, elle yapıdan en az yarı yarıya kısalır (pilotta ölçülecek).
- Her koşu için beyan metni tek komutla üretilir.
- Koşu başına maliyet ve süre kayıtlı.

## 8. Riskler

| Risk | Etki | Önlem |
|---|---|---|
| Sahte/zayıf atıf | Yüksek | F3, ikinci denetçi, insan kontrolü |
| Kontrolsüz maliyet | Orta | F4, düşük varsayılan bütçe |
| Araçların aşırı iddiaları (kendi testleri) | Orta | Pilotta kendi ölçümümüz; körü körüne güvenme |
| Politika değişimi (arXiv, dergiler) | Orta | F7, politika alanı güncellenebilir |
| Fork/benzer isimli sahte siteler | Düşük | Yalnız birincil repo ve arXiv makalesi |
| Ev dizininin git deposu olması | Düşük | Kurulum dışı dosyaları commit etmeden önce `.gitignore` |

## 9. Yol haritası

1. **Pilot (1 hafta):** AutoResearchClaw `gate-only`, küçük konu, bütçe 10 USD. Çıktı kalitesi ve atıf doğruluğu ölçülür.
2. **Doğrulama katmanı (1–2 hafta):** İkinci atıf denetçisi + beyan modülü (MCP-TASARIM.md).
3. **TR kaynak katmanı (2 hafta):** DergiPark/TR Dizin bağlayıcısı.
4. **Hakem simülasyonu ve dergi profili (1–2 hafta).**
5. **Gerçek proje:** Menekşe hoca makalesi veya Jana üzerinde uçtan uca.

## 10. Açık sorular

- Pilot konusu ne olsun?
- Deney aşaması hangi projelerde gerçekten gerekli (sosyal bilim makalelerinde literatür/sentez ağırlıklı mı)?
- Benzerlik raporu için hangi servis (iThenticate erişimi var mı)?
- Hafıza için tek kaynak vault mu, Cognee mi?
