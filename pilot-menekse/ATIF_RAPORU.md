# Menekşe makalesi v3 — bağımsız atıf denetimi (2026-10-20)

Kaynak: `~/Downloads/menekse-konsey/makale_v3.md`, 52 kaynakça girdisi. Betik: `verify_refs.py`, ham sonuç: `refs_report.json`. Kaynak: Crossref API (DOI çözümleme, DOI yoksa bibliyografik arama).

| Sonuç | Adet | Anlamı |
|---|---|---|
| Doğrulandı | 36 | DOI Crossref'te var; başlık, yazar ve yıl uyuyor |
| Yıl farkı (kontrol) | 2 | Morton 2013 (Crossref 2010), Palinkas 2015 (Crossref 2013, çevrimiçi yayın). Basılı/çevrimiçi farkı olasıdır, sorun gibi görünmüyor |
| Otomatik doğrulanamadı | 10 | DOI'siz kitap/galeri/yerel kaynak, arama zayıf eşleşti. **Elle bakılmalı** |
| Ayrıştırılamadı | 4 | Web sayfası/künye girdileri (Lossin e-flux, Quayola, Refik Anadol Studio, Staatliche Museen) |

**Uydurma atıf belirtisi bulunmadı.** Ama 14 girdi araçla doğrulanmış değildir.

## Elle bakılacaklar
- Özselçuk (2023): Crossref'te bulunmadı. DergiPark'ta makalenin varlığı ve künyesi teyit edilmeli (en riskli kalem).
- Hamburger Kunsthalle (2023) kataloğu, Deseyve (2019): Alman yayınlar, Crossref dışı. Kütüphane/DNB kaydından teyit.
- bitforms (2021) Quayola: Storms metni ve Quayola/Anadol/Staatliche Museen web sayfaları: sayfa canlı mı, tarih ve içerik uyuyor mu.
- Demos (2017): Crossref 2019 kaydı gösterdi. Sternberg Press 2017 basımı ile MIT Press 2019 baskısı karışmış olabilir, doğrusu belirlenmeli.
- Zylinska (2020), Koerner (2009), Nye (1994), Burke (2008), McCormack & Dorin (2001): gerçek eserler; Crossref yanlış kaydı eşleştirdi. Künye (yayıncı/baskı yılı) kitap kaydından teyit edilebilir.

## Araç hakkında not
İlk koşuda 10 "uyuşmazlık" çıktı. Hepsi aracın sahte alarmıydı: Crossref kitap alt başlıklarını atıyor, basılı ve çevrimiçi yılı ayırmıyor. Ayrıca betiğimde DOI altçizgisini silen bir hata vardı. Bu yüzden **aracın her bayrağı insan kontrolünden geçmeli** (PRD F3). Eşikler ve altın küme testi MCP-TASARIM.md'de planlı.
