"""Terim sözlüğü — arayüzdeki finansal terimlerin sade Türkçe açıklamaları.

Tek kaynak: arayüz balonları (`/api/sozluk` ucu üzerinden), CLI araçları ve
testler hep bu sözlükten okur. Acemi bir kullanıcı "PD/DD" ya da "FAVÖK"
gördüğünde üstüne gelip ne olduğunu buradan öğrenir.

Yazım kuralı (test_dil bunu tarar): her açıklama yalnızca terimin NEYİ
ölçtüğünü anlatır; hangi değerin arzu edilir olduğunu asla söylemez. Yorum
kullanıcıya aittir — bu, aracın değişmez sınırıdır.

Anahtar uzayı tek düz sözlüktür ve çakışmaz: metrik anahtarları küçük harfli
(`fscore`), F-Skoru kriter kimlikleri büyük harfli (`ROA_POZITIF`).
"""

from __future__ import annotations

# Panel genelindeki zorunlu uyarı cümlesi. Burada TEK yerde tanımlıdır;
# server.py ve araçlar import eder (test_uyari_metni_tek_yerde_tanimli
# kopyalanmasını engeller).
UYARI = (
    "Bu araç geçmiş finansal verileri analiz eder, gelecek getiri tahmini veya "
    "yatırım tavsiyesi vermez."
)


def _g(ad: str, aciklama: str) -> dict:
    return {"ad": ad, "aciklama": aciklama}


SOZLUK: dict[str, dict] = {
    # ================================================= metrikler (context.METRIKLER)
    "fscore": _g(
        "F-Skoru",
        "Piotroski F-Skoru: şirketin mali tablolarına 9 basit soru sorar "
        "(kâr var mı, nakit üretiyor mu, borç azalıyor mu gibi) ve her evet "
        "1 puandır. 0–9 arası bir sayıdır; yalnızca geçen yıla göre değişimi "
        "ölçer, gelecek hakkında bir şey söylemez.",
    ),
    "altman_z": _g(
        "Altman Z",
        "Altman Z-Skoru: şirketin bilanço ve kârlılık kalemlerini birleştirip "
        "mali sıkıntı riskini tarihsel bir modelle ölçen skor. Modelin "
        "tanımına göre 2,99 üstü tek bir bölge sayılır; bu eşiğin çok "
        "üzerindeki farklar ek bilgi taşımaz.",
    ),
    "roe": _g(
        "ROE",
        "Özsermaye kârlılığı (Return on Equity): net kârın ortakların "
        "koyduğu özsermayeye oranı. Şirketin, sahiplerinin parasıyla bir "
        "yılda yüzde kaç kâr ürettiğini gösterir.",
    ),
    "roa": _g(
        "ROA",
        "Varlık kârlılığı (Return on Assets): net kârın toplam varlıklara "
        "oranı. Şirketin elindeki tüm kaynaklarla (fabrika, stok, nakit...) "
        "ne kadar kâr ürettiğini ölçer.",
    ),
    "gross_margin": _g(
        "Brüt marj",
        "Satış gelirinden yalnızca üretim/satın alma maliyeti düşüldükten "
        "sonra kalan kârın gelire oranı. Ürünün kendisinin ne kadar kazanç "
        "bıraktığını gösterir; kira, pazarlama gibi giderler henüz düşülmemiştir.",
    ),
    "operating_margin": _g(
        "Faaliyet marjı",
        "Şirketin ana işinden elde ettiği kârın (faiz ve vergi öncesi) satış "
        "gelirine oranı. Asıl faaliyetin kârlılığını ölçer; tek seferlik "
        "gelirler ve finansman etkileri dışarıdadır.",
    ),
    "net_margin": _g(
        "Net marj",
        "Tüm giderler, faiz ve vergi düşüldükten sonra kalan net kârın satış "
        "gelirine oranı. 100 liralık satıştan kasada kaç lira kaldığını söyler.",
    ),
    "net_debt_ebitda": _g(
        "Net borç/FAVÖK",
        "Net borcun (toplam borç eksi kasadaki nakit) FAVÖK'e oranı. Kabaca, "
        "şirket bugünkü kazanma gücüyle borcunu kaç yılda kapatabilir sorusuna "
        "karşılık gelir. FAVÖK sıfıra yaklaştığında oran anlamını yitirir ve "
        "panel bu durumda değeri göstermez.",
    ),
    "debt_to_equity": _g(
        "Borç/özsermaye",
        "Toplam borcun ortakların özsermayesine oranı. Şirketin kaynaklarının "
        "ne kadarının borçla, ne kadarının ortak parasıyla sağlandığını gösterir.",
    ),
    "interest_coverage": _g(
        "Faiz karşılama",
        "Faaliyet kârının (faiz ve vergi öncesi) ödenen faiz giderine oranı. "
        "Şirketin kazancının, borçlarının faizini kaç kez ödemeye yettiğini ölçer.",
    ),
    "fcf_gap": _g(
        "Kâr–nakit sapması",
        "Net kâr ile serbest nakit akışı arasındaki farkın kâra oranı. "
        "Muhasebe kârının ne kadarının gerçekten kasaya nakit olarak girdiğini "
        "gösterir; büyük sapma, kârın alacak veya stok gibi kalemlerde "
        "beklediğine işaret eder.",
    ),
    "real_revenue_growth": _g(
        "Reel gelir büyümesi",
        "Satış gelirindeki artışın enflasyondan arındırılmış hâli. Nominal "
        "büyüme yüzde 40 olsa bile enflasyon yüzde 45 ise alım gücü olarak "
        "gelir küçülmüştür; bu metrik tam olarak bunu ölçer.",
    ),
    "real_income_growth": _g(
        "Reel net kâr büyümesi",
        "Net kârdaki değişimin enflasyondan arındırılmış hâli. Şirketin kârı "
        "fiyat artışlarının üzerinde mi yoksa altında mı büyümüş, onu gösterir.",
    ),
    "pe": _g(
        "F/K",
        "Fiyat/Kazanç oranı: şirketin piyasa değerinin yıllık net kârına "
        "bölümü. Piyasanın, şirketin 1 liralık kârı için kaç lira ödediğini "
        "gösterir. Tipik aralık sektörden sektöre değişir; yorum kullanıcıya "
        "aittir.",
    ),
    "pb": _g(
        "PD/DD",
        "Piyasa Değeri/Defter Değeri: şirketin borsadaki toplam değerinin, "
        "bilançodaki özsermayesine oranı. Piyasa fiyatının muhasebe "
        "değerinden ne kadar farklılaştığını ölçer; hangi seviyenin normal "
        "olduğu sektöre göre değişir.",
    ),
    "dividend_yield": _g(
        "Temettü verimi",
        "Son bir yılda hisse başına dağıtılan kâr payının hisse fiyatına "
        "oranı. Hisseyi bugünkü fiyattan alan birinin geçen yılki dağıtımla "
        "yüzde kaç nakit getiri elde etmiş olacağını gösterir; gelecekte "
        "dağıtım yapılacağını garanti etmez.",
    ),
    # ============================================ yalnız tarayıcıda olan alanlar
    "fscore_change": _g(
        "F-Skoru değişimi (tüm dönem)",
        "Eldeki en eski F-Skoru noktası ile en yenisi arasındaki puan farkı. "
        "Skorun yıllar içinde hangi yöne gittiğini özetler.",
    ),
    "fscore_change_yoy": _g(
        "F-Skoru değişimi (son yıl)",
        "Son iki yıllık tablo arasındaki F-Skoru puan farkı.",
    ),
    "fcf_positive": _g(
        "Serbest nakit akışı pozitif",
        "Şirketin faaliyetlerinden ürettiği nakit, yatırım harcamalarını "
        "karşıladıktan sonra artıda mı? Evet/hayır alanıdır.",
    ),
    "fcf_ge_net_income": _g(
        "FCF ≥ net kâr",
        "Serbest nakit akışı net kâra eşit veya ondan büyük mü? Kârın nakit "
        "karşılığının tam olup olmadığını süzmek için kullanılır.",
    ),
    "net_debt_ebitda_delta": _g(
        "Net borç/FAVÖK değişimi",
        "Net borç/FAVÖK oranının bir önceki yıla göre değişimi. Artı değer "
        "borç yükünün kazanma gücüne göre arttığı, eksi değer azaldığı "
        "anlamına gelir.",
    ),
    "operating_margin_direction": _g(
        "Faaliyet marjı trendi",
        "Faaliyet marjının son dönemlerdeki yönü: genişleme, daralma veya "
        "yatay. Eğim küçükse yatay sayılır.",
    ),
    "gross_margin_direction": _g(
        "Brüt marj trendi",
        "Brüt marjın son dönemlerdeki yönü: genişleme, daralma veya yatay.",
    ),
    "data_age_months": _g(
        "Veri yaşı (ay)",
        "Şirketin en son mali tablosunun üzerinden geçen süre (ay). Ekrandaki "
        "bütün metrikler o tarihe aittir; yaş büyüdükçe tablo bugünü değil "
        "geçmişi anlatır.",
    ),
    "data_fresh": _g(
        "Verisi güncel",
        "Son mali tablo 8 aydan yeni mi? Evet/hayır alanıdır; eski veriyle "
        "hesaplanan skorları süzmek için kullanılır.",
    ),
    "market_cap": _g(
        "Piyasa değeri",
        "Hisse fiyatı ile toplam hisse sayısının çarpımı: piyasanın şirketin "
        "tamamına biçtiği güncel etiket.",
    ),
    "sector": _g(
        "Sektör",
        "Şirketin ana faaliyet alanı sınıflandırması (Yahoo Finance'in "
        "kategorileri). Sektör medyanları bu gruplara göre hesaplanır.",
    ),
    # ======================================= F-Skoru kriterleri (health.KRITERLER)
    "ROA_POZITIF": _g(
        "ROA pozitif",
        "Şirket bu yıl varlıklarına göre kâr etti mi? Net kârın dönem başı "
        "toplam varlıklara oranı sıfırın üzerindeyse kriter geçilir.",
    ),
    "CFO_POZITIF": _g(
        "Faaliyet nakit akışı pozitif",
        "Ana faaliyetlerden kasaya giren nakit artıda mı? Kâğıt üzerindeki "
        "kârdan bağımsız olarak gerçek nakit girişini kontrol eder.",
    ),
    "ROA_ARTIYOR": _g(
        "ROA artıyor",
        "Varlık kârlılığı geçen yıla göre yükseldi mi? Kârlılığın yönünü "
        "ölçer, seviyesini değil.",
    ),
    "NAKIT_KARDAN_BUYUK": _g(
        "Nakit akışı net kârdan büyük",
        "Faaliyet nakit akışı net kârı aşıyor mu? Aşıyorsa kâr nakit olarak "
        "da karşılanmış demektir; tersinde kârın bir kısmı henüz tahsil "
        "edilmemiş kalemlerde bekliyordur.",
    ),
    "KALDIRAC_AZALIYOR": _g(
        "Uzun vadeli borç yükü azalıyor",
        "Uzun vadeli borcun toplam varlıklara oranı geçen yıla göre düştü mü? "
        "Borçluluğun yönünü izler.",
    ),
    "CARI_ORAN_ARTIYOR": _g(
        "Cari oran artıyor",
        "Dönen varlıkların kısa vadeli yükümlülüklere oranı (cari oran) geçen "
        "yıla göre yükseldi mi? Kısa vadeli ödeme gücünün yönünü izler.",
    ),
    "HISSE_IHRACI_YOK": _g(
        "Yeni hisse ihracı yok",
        "Şirket geçen yıl yeni hisse basmadı mı? Yeni ihraç, mevcut "
        "ortakların şirketteki payını seyreltir; kriter bunu kontrol eder.",
    ),
    "BRUT_MARJ_ARTIYOR": _g(
        "Brüt marj artıyor",
        "Brüt marj geçen yıla göre yükseldi mi? Ürünün bıraktığı kazancın "
        "yönünü izler.",
    ),
    "DEVIR_HIZI_ARTIYOR": _g(
        "Varlık devir hızı artıyor",
        "Satış gelirinin toplam varlıklara oranı (devir hızı) geçen yıla "
        "göre yükseldi mi? Şirketin aynı varlıklarla daha çok satış üretip "
        "üretmediğini ölçer.",
    ),
    # ================================================= risk / portföy terimleri
    "volatilite": _g(
        "Yıllık volatilite",
        "Getirilerin gün gün ne kadar dalgalandığının yıllığa çevrilmiş "
        "ölçüsü. Yüksek volatilite, fiyatın kısa sürede iki yönde de sert "
        "hareket edebildiği anlamına gelir; yön hakkında bilgi vermez.",
    ),
    "beta": _g(
        "Beta",
        "Portföyün, karşılaştırma endeksi (ör. XU100) yüzde 1 oynadığında "
        "tarihsel olarak yüzde kaç oynadığı. 1 üzeri endeksten sert, 1 altı "
        "endeksten yumuşak hareket edildiğini gösterir; geçmişe dayalıdır.",
    ),
    "hhi": _g(
        "HHI yoğunlaşma endeksi",
        "Herfindahl-Hirschman endeksi: portföy ağırlıklarının karelerinin "
        "toplamı. Tek hisseye yığılmış bir portföyde 1'e, eşit dağılmış "
        "portföyde 1/n'e yaklaşır — yoğunlaşmanın tek sayılık özetidir.",
    ),
    "etkin_pozisyon": _g(
        "Etkin pozisyon sayısı",
        "1/HHI: portföy sanki kaç eşit ağırlıklı pozisyondan oluşuyormuş gibi "
        "davranıyor, onu söyler. 10 hisselik ama tek hissenin baskın olduğu "
        "bir portföyde bu sayı 2-3'e düşebilir.",
    ),
    "korelasyon": _g(
        "Korelasyon",
        "İki hissenin aynı günlerde aynı yönde hareket etme eğilimi (-1 ile "
        "+1 arası). Yüksek korelasyonlu hisseler birlikte düşüp birlikte "
        "çıkar; çeşitlendirme etkisini azaltır.",
    ),
    "en_kotu_dusus": _g(
        "Tarihsel en kötü düşüş",
        "Eldeki fiyat geçmişinde, bir tepe noktasından sonraki en derin dip "
        "noktasına kadar yaşanan kayıp yüzdesi. Geçmişte başa gelmiş en kötü "
        "senaryoyu gösterir; tekrarlanacağını ya da aşılmayacağını söylemez.",
    ),
    "agirlikli_fskor": _g(
        "Ağırlıklı F-Skoru",
        "Portföydeki şirketlerin F-Skorlarının, portföy ağırlıklarına göre "
        "ortalaması. Hangi kapsamla hesaplandığı (portföyün yüzde kaçı) her "
        "zaman yanında yazar.",
    ),
    "kapsam": _g(
        "Kapsam",
        "Bir portföy ölçüsünün, portföyün yüzde kaçlık kısmı üzerinden "
        "hesaplanabildiği. Kapsam dışı kalan kısmın sebebi ayrıca yazılır: "
        "finans şirketi (model tanımsız), taranmamış evren veya eksik veri.",
    ),
    # ======================================================== genel terimler
    "reel": _g(
        "Reel",
        "Enflasyondan arındırılmış demektir. Yüzde 40 nominal büyüme, yüzde "
        "45 enflasyon varken alım gücü olarak küçülmedir; reel rakam bu "
        "düzeltmeyi yapılmış hâlidir.",
    ),
    "nominal": _g(
        "Nominal",
        "Enflasyon düzeltmesi yapılmamış, ham parasal değişim. Yüksek "
        "enflasyon ortamında tek başına yanıltıcı olabilir; panel bu yüzden "
        "reel rakamı birincil gösterir.",
    ),
    "tufe": _g(
        "TÜFE",
        "Tüketici Fiyat Endeksi: genel fiyat seviyesinin resmi ölçüsü. Panel "
        "reel hesaplarda şirketin mali tablo para birimine uygun TÜFE "
        "serisini kullanır (TL için TCMB, dolar için ABD BLS, diğerleri için "
        "Dünya Bankası yıllık ortalaması).",
    ),
    "ttm": _g(
        "Son 12 ay (TTM)",
        "Trailing Twelve Months: son dört çeyreğin toplamı. Takvim yılını "
        "beklemeden en güncel 12 aylık fotoğrafı verir; panel çeyrek "
        "verisinde boşluk varsa TTM yerine yıllık tabana döner ve bunu belirtir.",
    ),
    "favok": _g(
        "FAVÖK",
        "Faiz, Amortisman ve Vergi Öncesi Kâr (EBITDA): şirketin ana "
        "faaliyetinden ürettiği kazancın, finansman ve muhasebe "
        "düzeltmelerinden önceki hâli. Borç ödeme kapasitesi ölçülerinde "
        "payda olarak kullanılır.",
    ),
    "sektor_medyani": _g(
        "Sektör medyanı",
        "Aynı sektördeki şirketler sıralandığında tam ortadaki değer. "
        "Ortalamadan farklı olarak uç değerlerden etkilenmez. Sektörde 5'ten "
        "az geçerli şirket varsa panel medyanı göstermez.",
    ),
    "yuzdelik_dilim": _g(
        "Yüzdelik dilim",
        "Şirketin bir metrikte, karşılaştırma grubundaki şirketlerin yüzde "
        "kaçından yüksek değerde olduğu. Bir konum bilgisidir, yargı "
        "değildir — hangi yönün arzu edilir olduğu metriğe ve amaca göre değişir.",
    ),
    "tms29": _g(
        "TMS-29 (enflasyon muhasebesi)",
        "Türkiye'de 2023 sonrası mali tablolar enflasyona göre düzeltilerek "
        "raporlanıyor; öncesi düzeltilmemiş. Bu sınırı aşan yıllar arası "
        "karşılaştırmalar iki farklı muhasebe rejimini yan yana koyar; panel "
        "bu durumda not düşer.",
    ),
    "banka_muhasebesi": _g(
        "Banka muhasebesi",
        "Bankaların bilançosu sanayi şirketlerinden yapısal olarak farklıdır: "
        "brüt kâr, FAVÖK, cari oran ve net borç gibi kavramlar ya açıklanmaz "
        "ya da tanımsızdır. Panel bu metrikleri bankalarda hesaplamaz ve "
        "bunu açıkça belirtir.",
    ),
    # ------------------------------------------------ çeyreklik kalem terimleri
    "brut_kar": _g(
        "Brüt kâr",
        "Satış gelirinden üretim/satın alma maliyeti düşüldükten sonra kalan "
        "kâr. Kira, pazarlama, yönetim giderleri henüz düşülmemiştir.",
    ),
    "faaliyet_kari": _g(
        "Faaliyet kârı",
        "Şirketin ana işinden elde ettiği kâr; faiz ve vergi etkilerinden "
        "öncedir. Tek seferlik gelir/giderler dışarıdadır.",
    ),
    "faaliyet_nakit_akisi": _g(
        "Faaliyet nakit akışı",
        "Ana faaliyetlerden dönem boyunca kasaya fiilen giren net nakit. "
        "Muhasebe kârından farklı olarak tahsilat gerçekleşmiş parayı sayar.",
    ),
    "serbest_nakit_akisi": _g(
        "Serbest nakit akışı",
        "Faaliyet nakit akışından yatırım harcamaları (makine, tesis...) "
        "düşüldükten sonra kalan nakit. Şirketin işini sürdürmek için "
        "harcaması gerekeni harcadıktan sonra elinde kalan paradır.",
    ),
    "net_borc": _g(
        "Net borç",
        "Toplam finansal borçtan kasadaki nakit ve benzerleri düşülünce "
        "kalan tutar. Şirket bütün nakdini borca kapatsa geriye ne kadar "
        "borç kalır sorusunun cevabıdır; eksi çıkması nakdin borçtan fazla "
        "olduğu anlamına gelir.",
    ),
    "ozsermaye": _g(
        "Özsermaye",
        "Şirketin varlıklarından tüm borçları düşülünce ortaklara kalan "
        "muhasebe değeri (defter değeri). Negatif özsermaye, borçların "
        "varlıkları aştığı anlamına gelir.",
    ),
}
