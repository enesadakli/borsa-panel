# Proje durumu — yapay zekâ asistanı için bağlam notu

Bu dosya, projeye başka bir araçla (ör. Claude Code / Antigravity) devam edecek bir yapay zekâ asistanının hızlıca bağlam kazanması için yazıldı. README.md projenin *ne olduğunu* anlatır; bu dosya *şu an nerede kalındığını* anlatır.

## Tamamlanan işler (kronolojik)

- **F8** — `core/llm_rapor.py` + `/api/llm-rapor` uç noktası + sözlük/tooltip
- **F9** — tarama iptal düğmesi, karşılaştırmada kalite trendi grafikleri, izleme listesi, portföy CSV içe aktarımı
- **F10 — Antigravity Oturumu İyileştirmeleri (Tamamlandı)**
  - **Veri Katmanı (`health.py`, `fundamentals.py`, `yahoo.py`):**
    - `fcf_margin` ve `fcf_payout` (FCF Dağıtım Oranı) metrikleri eklendi.
    - `nwc_change` (İşletme Sermayesi İhtiyacı Değişimi) hesaplaması eklendi.
    - `CashDividendsPaid` Yahoo akış verilerine dahil edildi.
  - **LLM Raporlama Katmanı (`llm_rapor.py`):**
    - `_borc` ve `_marj` için tablo öncesi maddeli trend özetleri (`2022: X -> 2025: Y`) eklendi.
    - `_fskoru` bölümüne sektör medyanı ve sektör yüzde dilim metni eklendi.
    - `_capraz_inceleme` (Çapraz Metrik Kuralları) eklendi:
      - *Operasyonel Baskı:* Brüt Marj > %20 & Faaliyet Marjı < %5 ise uyarı.
      - *Nakit Kalitesi Çelişkisi:* Kâr Büyümesi > %10 & Serbest Nakit Akışı < 0 ise uyarı.
  - **Karşılaştırma Ucu (`server.py` & `llm_rapor.py`):**
    - `karsilastir(client, s1, s2)` fonksiyonu yazıldı.
    - `GET /api/llm-karsilastir?s1=X&s2=Y` uç noktası oluşturuldu ve `KORUNAN_UCLAR` arasına eklendi.
- **F10 sonrası kod incelemesi — iki ölçek hatası düzeltildi**
  - `_capraz_inceleme` marj **seviyesi** yerine `*_trend["value"]` alanını
    okuyordu; o alan `health._slope()` çıktısı, yani yıllık **eğim**. SISE.IS'te
    eğim -1,80 iken gerçek brüt marj 22,6 — `> 20` testi hep `False` dönüyordu,
    yani kural pratikte hiç tetiklenmiyordu. Artık `marjlar["series"][ad][-1][1]`
    okunuyor (`_marj_seviyesi()` yardımcısı; docstring'inde tuzak yazılı).
  - `karsilastir` marj farkını `B.yuzde` ile basıyordu, ama marj değerleri
    `context.extract_metrics`'te zaten `×100` yapılmış puan ölçeğinde. 4,6
    puanlık gerçek fark "%+460,0" diye görünüyordu. Fark hesabı `_fark()`
    fonksiyonuna ayrıldı; ölçek `_FARK_SAYI` / `_FARK_PUAN` sözlükleriyle
    belirleniyor.
  - `karsilastir` saf/veri diye ikiye ayrıldı: `kiyaslama_matrisi()` (ağsız,
    test edilebilir) + `_metrik_degerleri()`. Bu ayrım olmadan
    `## Kıyaslama Matrisi` başlığı testten geçirilemiyordu.
  - Beş yeni test; ikisi doğrudan bu hataların nöbetçisi
    (`test_karsilastirma_marj_farki_puan_olceginde`,
    `test_capraz_inceleme_marj_seviyesini_okuyor`). Süit: 106 geçti, 0 düştü.

## Yerel LLM Kararı ve Kullanım Notları

- **Model:** Qwen3-8B abliterated, Q4_K_M kuantizasyon (~4,9GB).
- **Donanım:** RTX 4050 6GB VRAM, Ryzen 7 7735HS, 16GB RAM.
- **LM Studio ayarı:** Context Length modeli yüklerken 8192 yapılmalı.

### Canlı sınav — GEÇTİ (2026-07-30)

`tools/run_canli_sinav.py` bu testi otomatikleştiriyor (LM Studio yerel sunucusu
açıksa API'den sorar, kapalıysa promptu `sinav_prompt_*.txt` olarak diske yazar).

**Sonuç: her iki modda da 5/5 doğru.** Model: `mlabonne_qwen3-8b-abliterated@q4_k_m`.

| Mod | Boyut | Sonuç |
|---|---|---|
| `--filtered` (ozet+bayraklar+fskor+borc+tazelik+metrikler) | ~6 KB | 5/5 |
| tam rapor | ~16 KB | 5/5 |

Böylece planın D4 maddesi (**raporu 11-13 KB'ye küçültme**) **gereksizleşti** —
rapor 15,5 KB'de kalabilir. Önceki oturumdaki "context length limit reached"
hatası raporun boyutundan değil, LM Studio'nun Context Length ayarının modeli
yüklerken 8192'ye çekilmemiş olmasından kaynaklanıyormuş.

Önceki oturumda modelin soruları cevaplamak yerine raporu özetlemesi de çözüldü:
sebep promptta görev talimatı olmamasıydı; `SYSTEM_PROMPT` + `RAPOR:`/`SORULAR:`
ayrımı bunu düzeltti.

**Kalan tek gözlem (kod hatası değil, kullanım notu):** tam raporda model 3.
soruya doğru cevap verdi ama gönüllü eklediği gerekçede "nominal büyüme %7,6"
dedi — raporda yazan **%-7,6**, yani eksi işaretini düşürüp daralmayı büyüme
sandı. Filtreli çalıştırmada bu hata yok. Uzun bağlamda model açıklama
süslemeye başlıyor ve süslerken işaret hatası yapabiliyor; sorulan sayıları
doğru veriyor ama "neden" cevaplarını rapordan teyit etmek gerekiyor.

## Bilinmesi gereken tuzak: önbellek anahtarı alan listesini içermiyor

`yahoo.py`'de `fundamentals()` önbellek anahtarı `{symbol}__{period_type}`.
Yani `YILLIK_ALANLAR` / `CEYREKLIK_ALANLAR` listesine **yeni bir kalem
eklendiğinde anahtar değişmiyor** ve eski kayıt (o kalem olmadan) TTL dolana
kadar servis edilmeye devam ediyor. Yeni kalem "Yahoo vermiyor" gibi görünür,
oysa istek hiç tazelenmemiştir.

Yeni kalem ekledikten sonra tek bir sembol için zorla tazele:

```python
YahooClient().fundamentals("SISE.IS", "annual", ttl=0)
```

`CashDividendsPaid` eklenirken tam olarak bu yaşandı. Kalıcı çözüm anahtara
alan listesinin bir özetini (hash) katmak olurdu.

## Sıradaki Adımlar (Gelecek Oturumlar)

F10'un asıl doğrulama adımı (canlı sınav) geçti; aşağıdakiler kalan işler.

1. **UX/UI İyileştirmeleri & Stitch Entegrasyonu:**
   - Arayüzü modernleştirmek için Stitch MCP / Tailwind / Vanilla CSS tasarımlarının yapılması.
   - Karşılaştırma uç noktasının arayüzde görselleştirilmesi.
3. **Genel Refactoring & Testler:**
   - Bu üç metrik artık **rapora bağlı** (`_kar_kalitesi` ve `_borc`
     bölümlerinde) ve `tests/test_nakit_metrikleri.py` ile test altında.
     `web/app.js` hâlâ okumuyor — arayüze de eklenecekse skor kartına
     eklenebilir.
   - `karsilastir` analizi iki kez yapıyor: `olustur()` zaten `H.analyze`
     çağırıyor, `_metrik_degerleri()` aynı işi tekrarlıyor. Önbellek ağ
     trafiğini kurtarıyor ama hesap boşa dönüyor; `olustur()` paketi de
     döndürecek şekilde ayrılırsa tekrar kalkar.
   - F-Skoru sektör medyanı iki yerde basılıyor (`_fskoru` ve `_metrikler`);
     hangisinin kalacağına karar verilmeli.
