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

## Çözüldü: önbellek anahtarı artık istenen alan listesini biliyor (F11 Adım 5)

`yahoo.py`'de `fundamentals()` önbellek anahtarı hâlâ `{symbol}__{period_type}`,
ama artık kayıt kendi içinde `istenen_alanlar` listesini de taşıyor ve isabet
yalnızca bu liste `YILLIK_ALANLAR`/`CEYREKLIK_ALANLAR`'ın **üst kümesiyse**
sayılıyor. Yeni bir kalem eklenince eski kayıtlar bu testten geçemez, sembol
görüldükçe **tek seferlik, tembel** olarak yeniden çekilir — elle `ttl=0`
verilmesine gerek kalmadı.

`CashDividendsPaid` eklenirken bu mekanizma olmadığı için kalem 4 yıl boyunca
"Yahoo vermiyor" gibi göründü (aslında hiç sorulmamıştı — bkz. yukarıdaki
commit geçmişi). `tests/test_onbellek.py` bu davranışı sentetik olarak
kilitliyor.

Aynı sınıftan tuzak beş önbellek noktasında daha var (`profile`, `series`,
`cpi`, `universe`, `context`) — bilerek F11 kapsamına alınmadı. `context`
özellikle: onu geçersizleştirmek ~15 dakikalık tam evren taraması demek,
metrikler hâlâ sık değişirken oraya kendi kendini iyileştiren bir anahtar
koymak riskli olurdu.

## F12 — Grafikler Chart.js'e taşındı, sıfır-pip kuralı kontrollü gevşetildi

**Karar:** proje "sıfır pip" kuralını (Python backend) korumaya devam ediyor,
ama kullanıcıyla yapılan tartışma sonunda **yalnızca gözle görülür fark
yaratacak** yerde (grafikler) bir istisna yapıldı. Detaylı gerekçe
README.md → Kurulum bölümünde.

- `web/vendor/chart.umd.min.js` — Chart.js v4.5.1, MIT, lokale indirilmiş
  (CDN yok, tam offline). Projenin tek harici JS bağımlılığı.
- `web/app.js`'teki `seritGrafik()` (çok şeritli, her seri kendi ölçeğinde)
  ve `sutunGrafik()` elle-SVG yerine Chart.js kullanıyor. **Çağrı yerleri
  değişmedi** — üç kullanım da (Skor Kartı'nın kalite mini-paneli, Kalite
  Trendi ekranı, Karşılaştır'ın şirket başına mini grafiği) test edildi.
- Yaşam döngüsü: `AKTIF_GRAFIKLER` + `grafikleriTemizle()`, her ekran
  değişiminde (`yonlendir()`) eski Chart.js örneklerini `destroy()` ediyor —
  aksi hâlde canvas DOM'dan silinse bile Chart.js'in iç kaydı bellek/CPU
  sızdırır. Çoklu gezinmeyle sınandı, sızıntı yok.
- **Bulunan ve kök nedeniyle düzeltilen gerçek hata:** `app.js` başlangıçta
  `yonlendir()`'i iki bağımsız yerden (sözlük yüklenince + durum yüklenince)
  çağırıyordu. SVG'de zararsızdı, Chart.js'te yarış durumu yaratıp hayalet
  grafik örnekleri (6 yerine 12) bırakıyordu. `Promise.all([sozlukYukle(),
  durumuYukle()]).then(() => yonlendir())` ile birleştirilip kökten
  kapatıldı; ek savunma olarak `GRAFIK_NESIL` nesil sayacı da eklendi.
- **Test sırasında yakalanan yan hata:** `renkCoz()` fonksiyonunun
  docstring'inde "alınmalı" kelimesi `test_dil.py`'nin yasak
  `alın(malı|abilir)` kalıbına (alım yönlendirmesi) yanlışlıkla takıldı —
  "okunmalı" ile değiştirildi. Bu test yorum satırlarını da tarıyor, yalnızca
  kullanıcı arayüzü metnini değil.
- Süit: 146 geçti, 0 düştü.

## F13 — Veriye güven: varsayılan olarak doğru (devam ediyor)

Anass birikimini bu araçla değerlendirmek istiyor ama portföye tek işlem
girmedi — sebep: *"gerçek ve güncel verileri çektiğinden emin olamıyorum."*
Şüphe haklı çıktı: ölçünce `series/` önbelleğinde yalnızca 9 dosya (smoke.py'nin
sembol listesi) bulundu, 1108/1116 şirkette fiyat serisi bölümü sessizce
kayboluyordu. Tam plan: `.claude/plans/uan-llm-raporu-peki-sparkling-bonbon.md`
(en üstte, "F13" başlığı altında) — gerekçe, ölçülen veriler, 6 adımın
(C1-C6) tamamı orada.

**C1 — TAMAMLANDI, commit bekliyor.** `core/risk.py:symbol_price_stats()`
artık `client.cache.closes()` (doğrudan, tazelemeyen önbellek okuması) yerine
`client.series(symbol, first_range="5y")` kullanıyor — `_returns()` ile aynı
yol. Canlı doğrulandı: `GARAN.IS`'in önceden hiç `series/` kaydı yoktu, artık
çekiliyor ve LLM raporunda `## Fiyat serisi` bölümü doğru veriyle çıkıyor.

`YahooError` ayrı yakalanıp "ağ/kaynak hatası" sebebiyle işaretleniyor;
`core/llm_rapor.py:_fiyat()`'in `if not f.get("available"): return []` satırı
artık başlık + `- Bu bölüm hesaplanamadı: {sebep}` basıyor (paket'te `fiyat`
anahtarı hiç yoksa hâlâ `[]` — "denendi, bulunamadı" ile "hiç denenmedi"
ayrımı korunuyor).

Yeni testler: `tests/test_fiyat_serisi.py` (6 test — sahte istemcide `.cache`
öznitelik yok, eski koda dönülseydi `AttributeError` ile düşerdi) +
`tests/test_llm_rapor.py`'ye 2 test. Süit: 154 geçti, 0 düştü. `smoke.py` da
geçti.

**Kalan: C2-C6.** Fiyatın kimliği (zaman damgası), portföy/kur tazeliği,
"Fiyatı tazele" düğmesi, durum çubuğu tutarlılığı — hepsi plan dosyasında.
Kapsam dışı bırakılan: Yahoo'nun kendi oranlarını (P/E, P/B, ROE) yanına
koymak (aynı kaynağın ikinci ifadesi, bağımsız doğrulama değil — reddedildi),
KAP entegrasyonu (XBRL eşlemesi riskli, yerine tek satırlık "KAP'ta aç"
bağlantısı düşünülüyor).

## Sıradaki Adımlar (Gelecek Oturumlar)

1. `nwc_change`/`fcf_margin`/`fcf_payout` rapora bağlı
   (`_kar_kalitesi`/`_borc`) ve test altında, ama `web/app.js` hâlâ
   okumuyor — arayüze de eklenecekse skor kartına eklenebilir.
2. `karsilastir` analizi iki kez yapıyor: `olustur()` zaten `H.analyze`
   çağırıyor, `_metrik_degerleri()` aynı işi tekrarlıyor. Önbellek ağ
   trafiğini kurtarıyor ama hesap boşa dönüyor; `olustur()` paketi de
   döndürecek şekilde ayrılırsa tekrar kalkar.
3. F-Skoru sektör medyanı iki yerde basılıyor (`_fskoru` ve `_metrikler`);
   hangisinin kalacağına karar verilmeli.
