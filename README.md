# Borsa Analiz Paneli

Bir şirketin mali tablolarının ne anlattığını gösteren yerel araç. Yahoo
Finance'ten BIST ve ABD hisselerinin gelir tablosu, bilanço ve nakit akışını
çeker; Piotroski F-Skoru, Altman Z-Skoru, borç yapısı, kâr kalitesi ve
**enflasyon sonrası reel büyümeyi** hesaplar.

## Ne yapar, ne yapmaz

**Yapar**
- Şirketin son 4 yıllık mali tablosunu okur, kriter kriter finansal sağlık ölçer
- Çeyreklik ve yıllık raporları geçen yılın aynı dönemiyle karşılaştırır, rakamdan
  türeyen kural tabanlı yorum cümleleri üretir
- Her metriği sektör medyanı ve yüzdelik dilimle birlikte gösterir
- Senin yazdığın kurallarla tüm evreni tarar (616 BIST hissesi)
- Portföyünün maliyetini, kâr/zararını ve yapısal riskini hesaplar
- Nominal rakamları **TÜFE ile düzelterek** reel getiriyi öne çıkarır

**Yapmaz**
- Al/sat sinyali, hedef fiyat, "şu hisseyi öneriyorum" gibi çıktı üretmez.
  Yatırım danışmanlığı lisanslı bir iştir; bu araç lisanslı bir danışman değil.
- Fiyatın nereye gideceği hakkında tahmin yapmaz. Yalnızca geçmiş rakamların
  ne gösterdiğini söyler.
- Yüksek F-Skoru "iyi yatırım" demek değildir; "bu şirket şu finansal kriterleri
  geçmiş" demektir. Karar ve sonuçları kullanıcıya aittir.

## Kurulum

Harici paket **gerekmez** — yalnızca Python 3.11+ standart kütüphanesi.

```bash
python --version
```

Panel: `baslat.bat` dosyasına çift tıkla. İlk çalıştırmada BIST taraması
teklif edilir (~17 dk, bir kez); tarama olmadan da skor kartı ve rapor
okuyucu çalışır, sadece sektör medyanı/tarayıcı/piyasa bakışı beklemede kalır.

Elle çalıştırmak için:

```bash
python server.py
```

### Paneldeki ekranlar

| Ekran | Ne yapar |
|---|---|
| **Skor kartı** | Bir şirketin tam röntgeni: reel/nominal büyüme, uyarı bayrakları, kural tabanlı özet cümleleri, kriter kriter F-Skoru, sektör medyanı ve yüzdelik dilimle metrikler, kalite trendi, bugünün parasıyla gelir |
| **Rapor okuyucu** | Çeyreklik ve yıllık karşılaştırma: kalem kalem YoY/QoQ değişim, marj tablosu, rakamdan türeyen yorum cümleleri |
| **Kalite trendi** | F-Skoru, marjlar, net borç/FAVÖK ve reel büyümenin dönem dönem seyri; her seri kendi ölçeğinde, ortak zaman ekseninde |
| **Tarayıcı** | Hazır filtre örnekleri veya kendi kuralın; sonuçlar **eşleşen / kısmi / uygulanamaz** diye üç gruba ayrılır |
| **Portföy** | İşlem defteri, ortalama maliyet, kur getirisi ayrıştırması, risk röntgeni (yoğunlaşma, korelasyon, volatilite, en kötü düşüş, beta) ve kalite röntgeni |
| **Piyasa** | Evrenin sayısal fotoğrafı: medyanlar, F-Skoru histogramı, sektör tablosu, skoru en çok değişen şirketler |

Arayüz açık/koyu temayı işletim sisteminden alır. Tüm sayılar Türkçe biçimde
(binlik nokta, ondalık virgül) ve tablo hizasında gösterilir.

### Enflasyon verisi

Reel hesaplar için TÜFE serisi gerekir. Araç üç kaynağı katmanlı kullanır:

| Kaynak | Kapsam | Anahtar |
|---|---|---|
| TCMB EVDS | TL tablolar, aylık, tam geçmiş | ücretsiz anahtar gerekir |
| ABD BLS | USD tablolar, aylık, son ~3 yıl | gerekmez |
| Dünya Bankası | ikisi de, yıllık ortalama, derin geçmiş | gerekmez |

**Anahtar olmadan da çalışır** (yıllık ortalama bazında). Aylık hassasiyet için:

1. <https://evds2.tcmb.gov.tr> — ücretsiz üyelik
2. Profil → API Anahtarı
3. `data/config.json` içindeki `evds_api_key` alanına yapıştır

Önemli kural: hangi TÜFE'nin kullanılacağını şirketin **mali tablo para birimi**
belirler, borsası değil. THYAO bir BIST hissesi ama tablolarını USD açıkladığı
için US CPI ile düzeltilir.

## Kullanım

```bash
python server.py                    # paneli aç (http://127.0.0.1:8737)
python tools/tarama.py bist         # BIST evrenini tara (~17 dk, 7 gün geçerli)
python tools/tarama.py us           # ABD ilk 500 (~18 dk)
python tools/kalibrasyon.py bist    # bayrak eşiklerini evren üzerinde ölç
python smoke.py                     # veri katmanı duman testi
python tests/run.py                 # testler (46 test)
```

### Terminalden kullanım

Arayüz olmadan da aracın tamamı çalışır:

```bash
python tools/rapor.py SISE.IS               # tam şirket raporu
python tools/rapor.py THYAO.IS AAPL         # birden fazla sembol
python tools/filtre.py                      # hazır şablonları ve alanları listeler
python tools/filtre.py bilanco_kalitesi     # şablonu çalıştır
python tools/filtre.py reel_buyuyen --evren us --limit 30
python tools/filtre.py bilanco_kalitesi --sirala fscore
python tools/filtre.py --kural kendi_kuralim.json
```

`tools/rapor.py` panelin skor kartındaki her şeyi metin olarak basar: kural
tabanlı özet, bayraklar, kriter kriter F-Skoru, sektör medyanı ve yüzdelik
dilimle metrikler, blok karakterli kalite zaman çizgisi ve son çeyrek raporu.

`tools/filtre.py` sonuçları üç gruba ayırır ve bu ayrım önemli:

- **eşleşen** — kriterlerin hepsini geçti
- **kısmi** — bir kriter veri eksikliğinden ölçülemedi, geçmiş olabilir
- **uygulanamaz** — kural o şirkette sektör yapısı gereği tanımsız
  (bankalarda FAVÖK, brüt kâr, cari oran yok)

Bankaları "kısmi" saymak, kullanıcıya yapabileceği bir şey varmış izlenimi
verirdi; veri eksikliği bir gün kapanabilir, sektör yapısı kapanmaz.

## Yapı

```
core/
  yahoo.py          Yahoo istemcisi (çerez+crumb, throttle, retry)
  cache.py          disk önbelleği: TTL'li kayıtlar + kalıcı fiyat serileri
  universe.py       sembol evreni, sektör eşlemesi, banka tespiti
  fundamentals.py   para birimi çözümleme, dönem hizalama, TTM
  inflation.py      EVDS + BLS + Dünya Bankası, reel hesaplar
  health.py         F-Skoru, Altman Z, borç, marj, kâr kalitesi
  reports.py        çeyreklik/yıllık karşılaştırma + yorum
  flags.py          6 kırmızı + 6 sarı kural
  narrative.py      4–6 cümlelik şirket özeti
  context.py        sektör medyanı, yüzdelik, trend
  screener.py       yapısal filtre motoru (eval yok)
  portfolio.py      işlem defteri, ortalama maliyet, kur ayrıştırması
  risk.py           yoğunlaşma, korelasyon, volatilite, kalite röntgeni
  market.py         piyasa genel bakışı (yorum cümlesi yok)
server.py           yerel HTTP sunucusu + JSON API (16 uç)
tools/
  tarama.py         evren tarayıcı (bağlam tablolarını doldurur)
  rapor.py          terminalden tam şirket raporu
  filtre.py         terminalden tarayıcı
  kalibrasyon.py    bayrak eşiklerini evren üzerinde ölçer
tests/run.py        test koşucusu (pytest gerekmez)
```

## Veri kaynağı uyarıları

Yahoo'nun BIST verisi güvenilmez noktalar içeriyor; araç bunları tespit edip
işaretliyor, sessizce yanlış rakam göstermiyor:

- **Kalem para birimi etiketi tutarsız.** THYAO'nun gelir serisinde etiket
  TRY/USD arasında zıplarken değerler homojen USD. Araç `financialCurrency`'yi
  esas alıyor, etiketi ancak değerlerde 8 kattan büyük sıçrama varsa dikkate alıyor.
- **Yahoo'nun hazır oranları bozuk olabilir.** THYAO için Yahoo PD/DD 19,7 diyor;
  TRY piyasa değerini USD bilançoya böldüğü için. Doğrusu 0,41. Araç tüm oranları
  kendisi hesaplıyor.
- **TTM'de eksik çeyrek.** AKBNK'ta 2025-Q3 gelmiyor; son dört satırı toplamak
  ortası boş bir "12 ay" üretir. Araç ardışıklığı kontrol ediyor, bozuksa yıllık
  tabana düşüp bunu ekranda etiketliyor.
- **Yanlış pay sınıfı piyasa değeri.** ISBTR.IS (İş Bankası kurucu senedi) için
  Yahoo, 499.000 TL'lik birim fiyatı bankanın 25 milyar normal hissesiyle çarpıp
  12,5 katrilyon TL buluyor. Araç bu tutarsızlığı yakalayıp piyasa değerine dayalı
  oranları hesaplamıyor.
- **Eksik veri sıfır sayılmaz.** F-Skoru `6/9 (2 kriter veri yok)` biçiminde
  raporlanır; payda küçültülmez, eksik kriter "kaldı" sayılmaz.
- **Bankalar farklı.** FAVÖK, brüt kâr ve cari oran bankalarda açıklanmaz;
  Altman Z ve Piotroski modelleri finans dışı şirketler için tanımlı. Bu metrikler
  "veri yok" değil "bu sektörde geçerli değil" olarak işaretlenir ve sektör
  medyanlarına girmez.
- **TMS-29 kırılması.** BIST tabloları 2023 sonrası enflasyon düzeltmeli, öncesi
  değil. Bu sınırı aşan karşılaştırmalarda uyarı gösterilir.

Rakamlar doğrulanmamıştır. Karar öncesi [KAP](https://www.kap.org.tr)
bildirimleriyle karşılaştırılmalıdır.

## Bayraklar ne sıklıkta tetikleniyor

Bir uyarının anlamı, ne kadar seyrek olduğuna bağlıdır. Tüm kurallar 616 BIST
şirketi üzerinde ölçüldü (`python tools/kalibrasyon.py bist`). Oran, kuralın
**uygulanabildiği** şirket sayısına bölünür — bankaları paydaya katmak, onlarda
tanımsız olan bir kuralı olduğundan seyrek gösterir:

| Kural | Seviye | Tetiklenme | Uygulanabilir |
|---|---|---|---|
| Kâr nakde dönmüyor | kırmızı | %11,1 | 495 |
| F-Skoru çöküşü | kırmızı | %7,9 | 491 |
| Borç sıkışması | kırmızı | %9,2 | 368 |
| Sürekli ve belirgin reel daralma | kırmızı | %34,6 | 546 |
| Negatif özsermaye | kırmızı | %1,2 | 583 |
| Faiz gideri kârdan büyük | kırmızı | %37,2 | 497 |
| Marj daralması + borç artışı | sarı | %18,8 | 448 |
| Olağandışı yatırım harcaması | sarı | %5,2 | 424 |
| Mantık dışı oran | sarı | %14,3 | 616 |
| F-Skoru veri eksiği | sarı | %5,1 | 573 |
| Para birimi belirsiz | sarı | %1,6 | 616 |
| Enflasyon muhasebesi sınırı | bilgi | %95,3 | 575 |

Kalibrasyonun değiştirdiği üç şey:

- **Reel daralma eşiği sıkılaştırıldı.** İlk kural "üst üste iki dönem herhangi
  bir reel küçülme" idi ve BIST'in %64,5'inde tetikliyordu — yüksek enflasyonda
  reel küçülme kural değil norm, dolayısıyla bu bir uyarı değil durum tespitiydi.
  Ölçülen alternatifler: eşik −%10 → %51,5, −%15 → %44,5, −%20 → %34,6. Eşik
  **−%20** seçildi: iki yıl üst üste bu kadar küçülmek reel gelirin yaklaşık üçte
  birini kaybetmek demek. Bayrak açıklamasında ayrıca taban oranı yazıyor.
- **Enflasyon muhasebesi sınırı uyarı olmaktan çıktı.** %95'te tetiklendiği için
  ayırt edici değil; TL raporlayan hemen her şirketin ortak dipnotu. Artık bilgi
  seviyesinde, uyarı listesinin dışında.
- **Aşırı büyüme kontrolü eklendi.** Tarayıcıda %+16.016 reel büyüme gösteren
  şirketler listenin başına oturuyordu. Bunlar ya veri hatası ya da şirketin
  tamamen dönüşmesi (bölünme, birleşme, faaliyete yeni başlama); %500 üstü
  büyümeler artık "mantık dışı oran" olarak işaretleniyor.

## Testler

```bash
python tests/run.py
```

- `test_dil.py` — kullanıcıya görünen tüm metinleri yasak dil listesine karşı
  tarar (al/sat sinyali, hedef fiyat, "ucuz/pahalı", öneri dili) ve zorunlu uyarı
  metninin her sayfada bulunduğunu doğrular
- `test_fskor.py` — 9 kriteri motordan bağımsız bir kod yoluyla yeniden hesaplayıp
  karşılaştırır; eksik kalemin sıfır sayılmadığını ve banka kenar durumunu test eder
- `test_reel.py` — `deflate` formülünü ve **para birimi → TÜFE eşlemesini** test
  eder (bir ABD şirketinin Türkiye TÜFE'siyle düzeltilmediği ayrıca kontrol edilir)
- `test_portfoy.py` — elle hesaplanmış senaryolarla ortalama maliyet, kısmi satış
  ve kur getirisi ayrıştırması

---

*Bu araç geçmiş finansal verileri analiz eder, gelecek getiri tahmini veya
yatırım tavsiyesi vermez.*
