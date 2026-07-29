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

### Canlı sınav durumu

`tools/run_canli_sinav.py` bu testi otomatikleştiriyor (LM Studio yerel sunucusu
açıksa API'den sorar, kapalıysa promptu `sinav_prompt_*.txt` olarak diske yazar).

Şu ana kadarki bulgular:

- Tam rapor (~15,5 KB) + 5 soru → **context length limit** ile kesildi.
- `?bolum=` ile küçültülmüş rapor → context sorunu yok (`EOS token found`).
- Ancak model 5 soruya numaralı cevap vermek yerine raporu yeniden özetledi.
  Sebep: promptta rapor ile sorular arasında görev talimatı yoktu. Düzeltme
  `run_canli_sinav.py`'deki `SYSTEM_PROMPT` + `RAPOR:` / `SORULAR:` ayrımı ile
  yapıldı, **ama bu haliyle henüz tekrar denenmedi.**

**Sıradaki adım:** `python tools/run_canli_sinav.py` çalıştırıp 5 sorunun
cevabını `CEVAP_ANAHTARI` ile karşılaştırmak. 5/5 doğruysa plan doğrulanmış
sayılır; yanlış cevap varsa ilgili bölümün biçimi sadeleştirilir.

## Sıradaki Adımlar (Gelecek Oturumlar)

1. **Canlı sınavın tekrarı** (yukarıda) — F10'un asıl doğrulama adımı, hâlâ açık.
2. **UX/UI İyileştirmeleri & Stitch Entegrasyonu:**
   - Arayüzü modernleştirmek için Stitch MCP / Tailwind / Vanilla CSS tasarımlarının yapılması.
   - Karşılaştırma uç noktasının arayüzde görselleştirilmesi.
3. **Genel Refactoring & Testler:**
   - `nwc_change`, `fcf_margin`, `fcf_payout` için `tests/` altına birim test
     eklenmesi (bunların hiçbiri şu an test edilmiyor).
   - `karsilastir` analizi iki kez yapıyor: `olustur()` zaten `H.analyze`
     çağırıyor, `_metrik_degerleri()` aynı işi tekrarlıyor. Önbellek ağ
     trafiğini kurtarıyor ama hesap boşa dönüyor; `olustur()` paketi de
     döndürecek şekilde ayrılırsa tekrar kalkar.
   - F-Skoru sektör medyanı iki yerde basılıyor (`_fskoru` ve `_metrikler`);
     hangisinin kalacağına karar verilmeli.
