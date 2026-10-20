# Pilot raporu — Menekşe makalesi × AutoResearchClaw (2026-10-20)

## Ne yapıldı
1. **Atıf denetimi (kendi betiğimiz):** v3'ün 52 kaynağı Crossref ile denetlendi → `ATIF_RAPORU.md`. 36 doğrulandı, 14 elle bakılmalı, uydurma belirtisi yok.
2. **AutoResearchClaw literatür koşusu (aşama 1–5):** Claude Code (ACP) ile. Aşama 4'te durdu.

## AutoResearchClaw bulguları
- **Kurulum sürtünmesi:** `acpx` en güncel sürümde (0.19.6) `--max-turns` bayrağı yok, AutoResearchClaw bunu kullanıyor. 0.15.1'e sabitlemek gerekti. Pip ile PyTorch kurulumu 300 sn'de zaman aşımına uğradı, boru hattı bunu atlayıp devam etti.
- **Kaynak katmanı çöktü:** OpenAlex, varsayılan ortak e-posta yüzünden günlük kotayı doldurmuş (≈11,6 saat bekleme). Semantic Scholar anahtarsız 429 verdi. Sonuçta 506 aday **yalnızca arXiv'den** geldi.
- **Konu kaydı (en önemli bulgu):** Sanat kuramı konusu, boru hattının ML eğilimiyle yeniden çerçevelendi. Sorgular arasında "CLIP concept directions", "linear probing embedding space", "AVA aesthetic visual analysis" gibi konu dışı ML terimleri çıktı.
- **Aday kalitesi düşük:** 506 adayın baş kısmı alakasız (kuantum estetiği, romantik AI sohbet botları, "Burke Property" matematiği, "Sublime Transfer Printing"). Makalenin gerçek literatürü (Burke, Kant, Koerner, Nye, Mosco, Brady, Demos, Zylinska…) arXiv'de yok.
- **Onay kapısı:** Arka planda çalışınca 5. aşama kapısı girdi alamadı ve koşuyu "kullanıcı iptal etti" diye bitirdi. Kapılar için etkileşimli terminal veya `attach/approve` akışı gerekir.

## Sonuç
AutoResearchClaw bu tür bir makale (beşeri bilimler/sanat kuramı, deneysiz) için **uygun değil**: kaynak kapsamı arXiv/ML ağırlıklı, aşamalar deneye dönük, konuyu ML'ye çekiyor. Makale zaten v3'te olduğu için de boru hattının üretim değeri yok.

Daha değerli çıktılar: (a) bağımsız atıf denetimi (çalıştı), (b) beşeri bilimler kaynak katmanı (PRD F8, MCP-TASARIM), (c) beyan modülü.

## Önerilen sıradaki adımlar
- AutoResearchClaw'ı **deneysel/ML konuları** için sakla; beşeri bilimlerde yalnız parçalarını (atıf doğrulama mantığı, hakem aşaması) al.
- MCP iskeletine geç: `search_sources` (Crossref + OpenAlex + S2 + DergiPark), `verify_citation`, `generate_disclosure`.
- Ücretsiz Semantic Scholar ve OpenAlex API anahtarı alınırsa kaynak katmanı iyileşir (kullanıcı kaydı gerekir).
