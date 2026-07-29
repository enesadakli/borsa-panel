# REVİZE PLAN v2 — yerel model kısıtına göre

*(Orijinal plan v1 aşağıda, ayraçtan sonra, olduğu gibi duruyor.)*

## Donanım ve model kararı

**Donanım:** RTX 4050 6GB VRAM · Ryzen 7 7735HS · 16GB RAM.
**Kısıt:** model ağırlığı + KV cache ≤ ~5,5GB olmalı; aşarsa katmanlar RAM'e
taşar ve hız 5-10 kat düşer.

**Seçilen model: Qwen3-8B abliterated, Q4_K_M** (~4,9GB) + 8K bağlam ≈ 5,7GB.
VRAM'e tam sığar, ~30-40 tok/s. Anass "Türkçe önemli değil, İngilizce de olur"
dedi — ama bu, **raporun dilini değiştirmiyor**: rapor Türkçe kalacak (tüm
`core/` modülleri, `test_dil` yasak kelime listesi ve 59 girdilik sözlük Türkçe
üretiyor; İngilizceye çevirmek sistemin tamamını çevirmek demek, bu planın
kapsamı değil). Değişen tek şey **beklenti**: model Türkçe raporu *anlayacak*,
cevabını Türkçe ya da İngilizce verebilir. Anlama, üretmekten kolaydır; bu
kısıtın gevşemesi 8B sınıfında rahat çalışmamızı sağlıyor.

**LM Studio ayarı:** `n_ctx = 8192`, GPU offload = tüm katmanlar (`-ngl 99`).
Rapor ~11-13 KB ≈ 4.000 token olacağı için 8K'da soru+cevaba yer kalır.

## RAG değerlendirmesi — kurulmayacak, gerekçesi

Anass "RAG da yapabiliriz" dedi. Değerlendirdim: **bu proje için RAG yanlış
araç.** Üç sebep:

1. **Sıfır pip kuralı.** Gerçek RAG embedding modeli (+1-2GB VRAM) ve vektör
   deposu ister. Projenin değişmez sınırı sadece stdlib.
2. **Ölçek yok.** RAG'in faydası binlerce dokümanda arama; burada tek şirketin
   tek raporu var ve zaten 32K bağlama rahat sığıyor.
3. **Asıl sorun erişim değil, dikkat.** 8B model 4.000 token'ı *okuyabiliyor*
   ama yoğun sayısal metinde ortadaki bilgiyi kaçırıyor. Bunun çözümü parça
   getirmek değil, **metni modelin okuyabileceği biçimde yazmak.**

**Yerine: bölüm parametresi (`?bolum=`).** RAG'in faydasının çoğunu sıfır
bağımlılıkla veriyor — `GET /api/llm-rapor?sembol=SISE.IS&bolum=borc,reel`
yalnızca istenen bölümleri döndürür (varsayılan: hepsi). Bölümler zaten `## `
başlıklarıyla ayrılmış durumda, filtreleme birkaç satır. Kullanıcı dar bir
soru soracaksa (ör. "borcu nasıl?") modele 13 KB yerine 2 KB verir.

## Değişiklikler (v1 → v2)

**D1 — Metrik tablosu: 8 sütunlu tablo → satır bazlı, hazır karşılaştırmalı**
- *Eski:* `| Metrik | Değer | Durum | Trend | Sektör medyanı (n) | Sektör % | Evren medyanı | Evren % |` (8 sütun × 16 satır)
- *Yeni:* metrik başına tek satır, karşılaştırma **cümlenin içinde hazır**:
  `- F-Skoru: 5/9 — sektör medyanı 4/9 (n=34), sektörün %68'lik diliminde (medyanın üstünde); kendi trendi yatay`
- *Neden:* 8B model 8 sütunlu tabloda satır kaydırıyor; ayrıca "5 > 4 demek ki
  üstünde" çıkarımını 16 metrik × 4 karşılaştırma boyunca kendisi yapmak zorunda
  kalıyor ve hata biriktiriyor. "Medyanın üstünde/altında" ifadesi sunucuda
  hesaplanır. **Yargı değil** — hangi yönün iyi olduğunu söylemiyor, yalnızca
  konumu düz Türkçeyle yazıyor (`test_dil` güvenli).

**D2 — Rapor başına `## Özet` bloğu (YENİ, en üstte)**
- *Eski:* `# SEMBOL — Ad` → doğrudan Kimlik.
- *Yeni:* başlıktan hemen sonra 8-12 satırlık yoğun özet: şirket/sektör/para
  birimi/dönem+yaş · F-Skoru · Altman bölgesi · reel gelir büyümesi · net
  borç/FAVÖK · ROE · tetiklenen bayrak sayısı **ve id listesi** · tek satır veri
  kalitesi.
- *Neden:* "lost in the middle" — 8B model dokümanın başını ve sonunu iyi,
  ortasını kötü hatırlıyor. En kritik bilgi başa alınıyor.

**D3 — Tarihçe tabloları ≤4 sütun**
- *Eski:* borç tarihçesi 6 sütun (Dönem/Toplam borç/Net borç/FAVÖK/Özsermaye/Oran)
- *Yeni:* `| Dönem | Net borç | FAVÖK | Net borç/FAVÖK |` — yalnızca o bölümün
  anlattığı sayı + türediği girdiler. Toplam borç ve özsermaye zaten Son
  çeyrek / Yıllık karşılaştırma bloklarında var.
- *Neden:* sütun sayısı 8B için en riskli değişken; tekrarı da kesiyor.

**D4 — Uzunluk hedefi ~15 KB → ~11-13 KB**
- D1 ve D3 zaten küçültüyor. 8K bağlamda soru+cevaba yer bırakır.
- Rapor sonuna makine-okunur satır: `<!-- boyut: 12,4 KB · ~4100 token -->`

**D5 — Bölüm parametresi (YENİ, RAG yerine)**
- `?bolum=ozet,borc,reel` → yalnızca o bölümler + başlık + UYARI dipnotu.
- Varsayılan (parametresiz) = tam rapor, v1'deki davranış.
- `bicimlendir(paket, bolumler=None)` imzası; her bölüm üreticisi zaten ayrı
  fonksiyon olduğu için filtreleme tek `if`.

**D6 — `## Fiyat serisi`: abliterated model için çift sınır**
- *Eski:* bölüm başında kapsam cümlesi.
- *Yeni:* başta **ve sonda** sınır cümlesi. Güvenlik eğitimi kaldırılmış bir
  model bu bölümden tavsiye üretmeye en meyilli; sınırı iki kez yazmak
  bağlamda tutma ihtimalini artırır.

**D7 — Yöntem notları 5 madde → 3 madde**
- 8B model uzun yöntem listesini okumuyor. Kalan: ondalık ayracı, hangi TÜFE,
  kaynak doğrulanmamış.

**Adımlara etkisi:** Adım 2'nin *mantığı* aynı (analiz-öncelikli metrik paketi),
yalnızca `_metrikler` renderer'ı tablo yerine satır basıyor. Adım 3'te tarihçe
tabloları daraltılıyor. Adım 6'da piyasa bağlamı da satır bazlı (tablo değil).
Adım 7'ye kapanış sınır cümlesi ekleniyor. Adım 5 (Yıllık karşılaştırma) ve
Adım 8 (testler) değişmiyor; testlere D5 için bölüm-filtresi testi ekleniyor.

## Yeni riskler (v1'in 7 riskine ek)

8. **Model tavsiye üretir** (abliterated, güvenlik eğitimi yok). Rapor bunu
   engelleyemez — bu bir kod riski değil, kullanım riski. Elden gelen: raporda
   tavsiye dili olmaması + iki yerde sınır cümlesi + UYARI dipnotu. Kalanı
   kullanıcının promptunda.
9. **Markdown tablo hizalama hatası** — 8B modeller geniş tabloları satır
   kaydırarak okur. D1/D3 bunu azaltıyor; kalan tablolar ≤4 sütun.
10. **VRAM sınırı** — 8B Q4 + 8K bağlam 5,7GB, kartın 6GB'ına yakın. Başka bir
    GPU tüketicisi (tarayıcı donanım hızlandırma) varsa taşabilir. Test
    sırasında `nvidia-smi` ile doğrulanmalı.

## Doğrulama eklemeleri

- [ ] SISE.IS raporu **11-13 KB** (≥16 KB ise D1/D3 tam uygulanmamış)
- [ ] Hiçbir tablo 4 sütundan geniş değil:
      `grep -o '^|.*|$' rapor.md | awk -F'|' 'NF>6'` boş dönmeli
- [ ] `## Özet` raporun ilk 1,5 KB'si içinde
- [ ] Metrik satırlarında "medyanın üstünde/altında" hazır yazılı
- [ ] `?bolum=borc` → yalnızca Borç profili + başlık + UYARI, <2 KB
- [ ] **Yerel modelle canlı sınav (asıl doğrulama):** raporu Qwen3-8B'ye verip
      5 soru — (1) F-Skoru kaç, sektöre göre nerede? (2) Kaç kırmızı bayrak,
      hangileri? (3) Gelir reel olarak büyüdü mü küçüldü mü? (4) Son mali tablo
      ne kadar eski? (5) Net borç/FAVÖK 4 yılda nasıl değişti? — **beşine de
      doğru cevap vermeli.** Yanlış cevap = o bölümün yapısı model için fazla
      karmaşık, biçim düzeltilir.
- [ ] `nvidia-smi` ile VRAM kullanımı < 6GB doğrulanır

═══════════════════════════════════════════════════════════════════

# ORİJİNAL PLAN v1 (değiştirilmedi)

## Bağlam — neden

Anass sordu: *"LLM raporu gerçekten en verimli şekilde mi rapor veriyor?
Verebileceği ve mantıklı olan tüm verileri ve yorumları gösteriyor mu? Bu çok
önemli, asıl projenin devamı ordan işleyecek."*

Kaynak kod üzerinden çıkarılan cevap: **hayır.** Rapor, sistemin ürettiği
verinin kabaca üçte birini gösteriyor. Kök sebep tek bir satırda:
`core/llm_rapor.py:49-73`'te `olustur()`, `H.analyze()`'ın döndürdüğü zengin
`analysis` sözlüğünden yalnızca `freshness` ve `fscore` alanlarını alıp paketi
kuruyor — geri kalan her şey biçimlendiriciye hiç ulaşmadan düşüyor.

**Analiz edilip hesaplanan ama rapora hiç girmeyenler:**

| Veri | Nerede üretiliyor | Rapordaki durumu |
|---|---|---|
| Altman Z + bölge + X1–X5 bileşenleri | `analysis.altman` | yok |
| Borç profili (5 metrik + 4 yıllık tarihçe) | `analysis.debt` | yok |
| Marj serileri + eğim/yön (3 marj) | `analysis.margins` | yok |
| ROE / ROA | `analysis.returns` | yok |
| Kâr kalitesi (Sloan tahakkuk, FCF açığı, tarihçe) | `analysis.profit_quality` | yok |
| Reel büyüme tarihçesi + sabit fiyatlı gelir serisi | `analysis.real_growth` | yok |
| Değerleme tabanı (TTM mi yıllık mı, kur çevrimi) | `analysis.valuation` | yok |
| **Yıllık dönem karşılaştırması** (tüm blok) | `reports["annual"]` | pakete giriyor, basılmıyor |
| Çeyreklik marjlar, QoQ, reel gelir | `reports["quarterly"]` | pakete giriyor, basılmıyor |
| Piyasa/evren bağlamı | `market.market_snapshot()` | hiç çağrılmıyor |
| Fiyat geçmişi | `client.series()` | hiç çağrılmıyor |

**Ayrıca bulunan kritik kırılganlık:** ROE, ROA, marjlar, Altman, borç oranları
ve F/K–PD/DD şu anda **yalnızca** "Metrikler ve sektör bağlamı" tablosunda
görünüyor. O tablo `C.all_metric_contexts(context, symbol)`'dan besleniyor ve
bu fonksiyon (a) evren taraması hiç yapılmamışsa **veya** (b) sembol tarama
kaydında yoksa (yeni listelenmiş, tarama sırasında hata almış, ya da yalnızca
BIST taranmışken bir ABD hissesi) boş dönüyor. `_metrikler` de `available`
olmayan satırları `continue` ile atlıyor. Sonuç: bu durumlarda rapor **başlığı
ve tablo başlığı basılı ama sıfır satırlı** bir tablo gösteriyor — verinin
kontrol edilip bulunamadığı izlenimi veriyor, oysa hiç sorulmamış. Bu, aracın
"eksik veri sıfır sayılmaz" ilkesinin rapor yüzeyinde ihlali.

**Amaç:** raporu, bir LLM'in şirketi tek istekte tam olarak anlayabileceği
kapsama çıkarmak ve metrikleri her koşulda üreten kaynağa (`analysis`)
bağlamak.

## Anass'ın kararları (soruldu)

1. **Fiyat serisi bölümü: evet**, dikkatli dille. Yalnızca geçmiş istatistik;
   yön/hedef ima eden tek kelime geçmeyecek, bölüm başında kapsam cümlesi
   duracak.
2. **Piyasa bağlamı: evet** — evren özeti + şirketin kendi sektör satırı.
   30 sektörlük tam tablo ve "en çok yükselen 10" listesi girmeyecek.
3. **Uzunluk: tek doküman, ~15 KB, her şey içinde.** Kısa/tam parametresi yok.

## Tasarım kararları

**Verimlilik = aynı sayıyı iki kez yazmamak, bölüm gizlemek değil.**
- Metrik tablosu: karşılaştırılabilir değer + kendi trendi + sektör/evren
  konumu. Taban bilgisi ve kaynak yok.
- Tematik bölümler: `detail` cümlesi (tabanı taşır: "ROE = %8,4 (TTM kâr)"),
  `sources`, bileşenler, tarihçe, ve eksikse **neden** eksik olduğu.
- **`## Kalite zaman çizgisi` kısalır**: marj/borç/reel serileri kendi
  bölümlerine taşındığı için orada tekrar edilmez. Net silme — değişikliğin en
  net "verimlilik" kazancı.
- `_ceyrek`'teki `[:10]` satır ve `[:5]` yorum kesme sınırları kalkar (sessiz
  kırpma, düzeltilen hatanın küçük hâli).

**Bölüm sırası** (mevcut 10 başlığın metni birebir korunur — testler onlara
bakıyor; yalnızca metrik tablosu yukarı taşınır):

Kimlik → Veri tazeliği → Kural tabanlı özet → Bayraklar → **Metrikler ve
sektör bağlamı** → Piotroski F-Skoru → *Altman Z-Skoru* → *Değerleme* →
*Kârlılık* → *Borç profili* → *Kâr kalitesi* → *Reel büyüme* → Kalite zaman
çizgisi (kısaltılmış) → Son çeyrek → *Yıllık karşılaştırma* → *Fiyat serisi* →
*Piyasa bağlamı* → Veri kalitesi notları → Yöntem notları → UYARI

*(italik = yeni)*. Altman doğrudan Piotroski'nin ardında: iki yayımlanmış model
yan yana olunca bir LLM "kalite"yi "sıkışma riski"yle aramadan karşılaştırıyor.

**Kod sözleşmesi:** bölüm başlıkları **düz string sabiti** olacak, asla
f-string — Q7'deki başlık-kapsama testi bunu şart koşuyor.

## Riskler

1. **`test_dil` × `## Fiyat serisi`** — tek gerçek yeni risk yüzeyi. `hedef`,
   fiyata bitişik `seviye`, giriş noktası çağrıştıran her şey yasak. Kullanılacak
   dil: *52 haftalık aralık*, *zirveden en derin geri çekilme*,
   *yıllıklandırılmış volatilite*; konum "aralığın alt ucundan %34 yukarıda"
   diye yazılır, "%34 seviyesinde" diye değil.
2. **`real_growth[key]` `history` anahtarı taşımayabilir** (`health.py:786`
   erken dönüş). Her okuma `.get("history") or []`.
3. **Banka yolu** — ~8 metrik ve 4 bayrak `GECERSIZ`/`not_applied`. Yeni
   bölümler bunları **basıp işaretlemeli**, yok saymamalı; yoksa düzeltilen hata
   her finans şirketi için geri gelir. Banka fikstürü bunu kilitler.
4. **Bayat tarama / taze analiz ayrışması** — canlı değer ile eski dağılımın
   yüzdeliği çelişebilir. Canlı kazanır, fark Veri kalitesi'nde açıkça yazılır.
5. **`test_ondalik_ayraci_turkce`** — yeni tarihçe tabloları dosyadaki en yoğun
   ham float birikimi; tek bir kaçan `B.*` çağrısı testi düşürür.
6. **`paket["baglam"]` → `paket["metrikler"]` adlandırması** — `server.py`'deki
   `baglam` farklı bir sözlük (uc_sirket JSON yanıtı), etkilenmiyor.
7. **Rapor ~2,7× büyüyor.** İleride bayt hassasiyeti doğarsa ilk kesilecek şey
   Piyasa bağlamı'nın sektör satırıdır, hiçbir yorum değil — kaynağa yorum
   düşülecek.

## Dokunulan dosyalar

- `core/llm_rapor.py` — ana değişiklik
- `core/risk.py` — tek yeni public fonksiyon (`symbol_price_stats`)
- `tests/test_llm_rapor.py` — fikstür yeniden yapılandırma + yeni testler

`core/context.py` olduğu gibi yeniden kullanılıyor (`extract_metrics`,
`extract_trends`), `server.py` değişmiyor.
