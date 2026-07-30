"""Finansal sağlık motoru.

Yayınlanmış, objektif çerçeveleri mali tablolardan hesaplar: Piotroski
F-Skoru, Altman Z-Skoru, kâr kalitesi, borç yapısı, marj trendi ve reel
büyüme. Hiçbiri "al/alma" demez; şirketin geçmiş rakamlarının hangi ölçüte
göre nerede durduğunu söyler.

Üç kural bu modülün her yerinde geçerli:

1. **Eksik veri sıfır değildir.** Hesaplanamayan kriter `eksik_veri`
   durumundadır; F-Skoru `6/9 (2 kriter veri yok)` diye raporlanır, 6/9 yerine
   6/7 gibi şişirilmiş bir orana da çevrilmez.
2. **Sektörde geçersiz olan, eksik olan değildir.** Bankalarda FAVÖK, brüt kâr
   ve cari oran yoktur; bunlar `sektorde_gecersiz` ile işaretlenir, veri
   kalitesi sorunu gibi gösterilmez.
3. **Her sayının izi sürülebilir.** Her metrik hangi kalemlerden, hangi
   dönemlerden hesaplandığını `sources` içinde taşır; narratif ve bayrak
   modülleri cümlelerin altına bunu yazar.
"""

from __future__ import annotations

from . import bicim as B
from . import fundamentals as F
from . import inflation as INF

OK = "ok"
EKSIK = "eksik_veri"
GECERSIZ = "sektorde_gecersiz"

# Net borç/FAVÖK, FAVÖK sıfıra yaklaştıkça patlar. Ölçülen vaka: ISSEN.IS'te
# FAVÖK 2024'te 345 milyon iken 2025'te 1,2 milyona çöktü (şirketin ölçeğine
# göre neredeyse sıfır); oran 4,94'ten 2.734,27'e çıktı. Bu gerçek bir borç
# artışı değil, paydanın çökmesi — anlatı denetim aracı yakaladı. Eşik tek
# yerden tanımlanıyor çünkü aynı hesap debt_profile(), R3 bayrağı, NAR_BORC
# ve kalite zaman çizgisinde ayrı ayrı tekrarlanıyordu.
NET_BORC_FAVOK_SUPHE = 50


def net_debt_ebitda_guvenilir(net_debt, ebitda) -> bool:
    """Net borç/FAVÖK oranı anlamlı bir aralıkta mı?"""
    if net_debt is None or not ebitda or ebitda <= 0:
        return False
    return abs(net_debt / ebitda) <= NET_BORC_FAVOK_SUPHE

# Piotroski'nin eşiği: hisse sayısındaki %1'lik oynama (çalışan opsiyonları,
# küsurat) sermaye artırımı sayılmaz.
HISSE_TOLERANSI = 0.01

# Marj trendi sınıflaması: yılda ±1 puandan küçük değişim yatay sayılır.
MARJ_TREND_ESIGI = 1.0

# Marj trendi sözlüğü. Sabit olarak duruyor çünkü tarayıcı şablonları bu
# değerlerle karşılaştırma yapıyor: context.trend() farklı bir sözlük
# ("artış/düşüş/yatay") kullanıyor ve ikisi karışınca filtre sessizce hiçbir
# şeyi elemiyor — kural doğru görünür, hiç eşleşmez.
MARJ_GENISLEME = "genişleme"
MARJ_DARALMA = "daralma"
MARJ_YATAY = "yatay"
MARJ_YONLERI = (MARJ_GENISLEME, MARJ_DARALMA, MARJ_YATAY)

ALTMAN_GUVENLI = 2.99
ALTMAN_SIKISMA = 1.81

# Bir F-Skoru noktasının kullanılabilir sayılması için en az bu kadar kriterin
# değerlendirilebilmiş olması gerekir. Yahoo'nun en eski yılı çoğu şirkette
# neredeyse boş geliyor (AAPL 2022: 9 kriterden 8'i hesaplanamıyor) ve o
# noktayı skor gibi göstermek "1/9'dan 8/9'a çıkmış" gibi sahte bir iyileşme
# anlatısı üretir. Kullanılamayan noktalar grafikte ve özette yer almaz.
MIN_DEGERLENDIRILEN_KRITER = 5

# Bankalarda dört kriter yapısal olarak uygulanamadığı için eşik daha düşük;
# skor yine gösterilir ama `model_applicable=False` ile birlikte.
BANKA_MIN_KRITER = 3


def metric(value, status=OK, detail=None, sources=None, **extra) -> dict:
    out = {"value": value, "status": status, "detail": detail, "sources": sources or []}
    out.update(extra)
    return out


def source(item: str, period: str | None, value=None) -> dict:
    return {"item": item, "period": period, "value": value}


# ============================================================== ana giriş


def analyze(client, symbol: str, pack: dict | None = None, cpi: dict | None = None) -> dict:
    """Sembol için tüm sağlık metriklerini hesaplar."""
    if pack is None:
        pack = F.load(client, symbol)
    if cpi is None:
        cpi = INF.series_for_pack(client.cache, pack)

    bank = pack.get("bank_accounting", False)

    result = {
        "symbol": symbol,
        "name": pack.get("name"),
        "currency": pack.get("currency"),
        "country": pack.get("country"),
        "sector": pack.get("sector"),
        "industry": pack.get("industry"),
        "bank_accounting": bank,
        # Tazelik analizin bir parçası, dipnotu değil: 19 aylık bir tablodan
        # çıkan F-Skoru doğru olsa bile "bugünkü durum" değildir.
        "freshness": pack.get("freshness") or {},
        "periods": F.period_dates(pack),
        "fscore": fscore_series(pack, bank),
        "altman": altman_z(client, pack, bank),
        "profit_quality": profit_quality(pack, bank),
        "debt": debt_profile(pack, bank),
        "margins": margin_profile(pack, bank),
        "returns": return_profile(pack),
        "real_growth": real_growth_profile(pack, cpi),
        "valuation": valuation(client, pack),
        "cpi": {
            "available": cpi.get("available", False),
            "notes": cpi.get("notes", []),
        },
        "currency_notes": pack.get("currency_notes", []),
    }
    return result


# ============================================================ Piotroski F-Skoru


def fscore_series(pack: dict, bank: bool) -> dict:
    """Her yıl için F-Skoru.

    Skor t yılını t−1 ile karşılaştırdığı için N yıllık tablodan **N−1** skor
    çıkar. 9. kriter (varlık devir hızı değişimi) t−2 yılının varlıklarını da
    istediğinden en eski skor noktasında değerlendirilemez ve `eksik_veri`
    olarak işaretlenir — sıfır sayılmaz.

    Piotroski modeli finans dışı şirketler için tanımlanmıştır. Bankalarda
    kriterlerin yarısı yapısal olarak uygulanamaz; skor yine hesaplanır ama
    `model_applicable` False döner ve şirketler arası karşılaştırmalarda
    (sektör medyanı, tarayıcı sıralaması) kullanılmaz.
    """
    rows = F.rows(pack, "annual")
    points = []
    for index in range(1, len(rows)):
        points.append(_fscore_at(rows, index, bank))

    usable = [point for point in points if point["usable"]]

    note = (
        f"{len(rows)} yıllık tablodan {len(points)} skor noktası çıkıyor "
        "(skor bir önceki yılla karşılaştırma gerektirir)."
    )
    threshold = BANKA_MIN_KRITER if bank else MIN_DEGERLENDIRILEN_KRITER
    dropped = len(points) - len(usable)
    if dropped:
        note += (
            f" {dropped} nokta yeterli kalem gelmediği için kullanılmadı "
            f"(en az {threshold} kriter değerlendirilebilmeli)."
        )

    return {
        "points": points,
        "usable_points": usable,
        "latest": usable[-1] if usable else None,
        "model_applicable": not bank,
        "model_note": (
            "Piotroski F-Skoru finans dışı şirketler için tanımlıdır; "
            "banka ve sigorta şirketlerinde kriterlerin bir kısmı uygulanamaz, "
            "bu yüzden skor diğer şirketlerle kıyaslanmaz."
            if bank
            else None
        ),
        "note": note,
    }


def _fscore_at(rows: list[dict], index: int, bank: bool) -> dict:
    now = rows[index]["values"]
    before = rows[index - 1]["values"]
    older = rows[index - 2]["values"] if index >= 2 else None
    date = rows[index]["date"]
    prev_date = rows[index - 1]["date"]

    criteria = [
        _c_roa(now, before, date, prev_date),
        _c_cfo(now, date, bank),
        _c_delta_roa(rows, index),
        _c_accruals(now, before, date, prev_date, bank),
        _c_leverage(now, before, date, prev_date, bank),
        _c_current_ratio(now, before, date, prev_date, bank),
        _c_shares(now, before, date, prev_date),
        _c_gross_margin(now, before, date, prev_date, bank),
        _c_asset_turnover(rows, index),
    ]

    passed = sum(1 for c in criteria if c["status"] == OK and c["passed"])
    evaluated = sum(1 for c in criteria if c["status"] == OK)
    missing = [c["id"] for c in criteria if c["status"] == EKSIK]
    invalid = [c["id"] for c in criteria if c["status"] == GECERSIZ]

    label = f"{passed}/9"
    tail = []
    if missing:
        tail.append(f"{len(missing)} kriter veri yok")
    if invalid:
        tail.append(f"{len(invalid)} kriter bu sektörde geçersiz")
    if tail:
        label += " (" + ", ".join(tail) + ")"

    return {
        "date": date,
        "score": passed,
        "max": 9,
        "evaluated": evaluated,
        "usable": evaluated >= (BANKA_MIN_KRITER if bank else MIN_DEGERLENDIRILEN_KRITER),
        "label": label,
        "missing": missing,
        "not_applicable": invalid,
        "criteria": criteria,
    }


# Kriter kimliği -> ekran etiketi, tek kaynak. Eskiden her kriterin etiketi
# eksik/geçersiz/ok dallarında 2-3 kez tekrarlanıyordu; biri değişince
# diğerleri sessizce geride kalabilirdi. Sözlük (core/sozluk.py) açıklamaları
# da bu kimlikler üzerinden eşleşir.
KRITERLER = (
    ("ROA_POZITIF", "ROA pozitif"),
    ("CFO_POZITIF", "Faaliyet nakit akışı pozitif"),
    ("ROA_ARTIYOR", "ROA artıyor"),
    ("NAKIT_KARDAN_BUYUK", "Nakit akışı net kârdan büyük"),
    ("KALDIRAC_AZALIYOR", "Uzun vadeli borç yükü azalıyor"),
    ("CARI_ORAN_ARTIYOR", "Cari oran artıyor"),
    ("HISSE_IHRACI_YOK", "Yeni hisse ihracı yok"),
    ("BRUT_MARJ_ARTIYOR", "Brüt marj artıyor"),
    ("DEVIR_HIZI_ARTIYOR", "Varlık devir hızı artıyor"),
)

KRITER_ADLARI = dict(KRITERLER)


def _criterion(id_, passed, status=OK, detail=None, sources=None) -> dict:
    return {
        "id": id_,
        "label": KRITER_ADLARI[id_],
        "passed": passed,
        "status": status,
        "detail": detail,
        "sources": sources or [],
    }


def _ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _c_roa(now, before, date, prev_date):
    ni = now.get("NetIncome")
    assets = before.get("TotalAssets")  # Piotroski: dönem başı varlık
    roa = _ratio(ni, assets)
    if roa is None:
        return _criterion("ROA_POZITIF", None, EKSIK,
                          "Net kâr veya dönem başı toplam varlık yok")
    return _criterion(
        "ROA_POZITIF", roa > 0, OK, f"ROA = {B.yuzde(roa, 2, False)}",
        [source("NetIncome", date, ni), source("TotalAssets", prev_date, assets)],
    )


def _c_cfo(now, date, bank):
    if bank:
        # Banka faaliyet nakit akışı mevduat ve kredi hacmiyle savrulur;
        # işareti kârlılık hakkında bilgi taşımaz.
        return _criterion("CFO_POZITIF", None, GECERSIZ,
                          "Banka nakit akışı mevduat/kredi hareketiyle belirlenir")
    cfo = now.get("OperatingCashFlow")
    if cfo is None:
        return _criterion("CFO_POZITIF", None, EKSIK,
                          "Faaliyet nakit akışı yok")
    return _criterion(
        "CFO_POZITIF", cfo > 0, OK,
        f"Faaliyet nakit akışı = {B.para(cfo)}",
        [source("OperatingCashFlow", date, cfo)],
    )


def _c_delta_roa(rows, index):
    now, before = rows[index]["values"], rows[index - 1]["values"]
    older = rows[index - 2]["values"] if index >= 2 else None
    roa_now = _ratio(now.get("NetIncome"), before.get("TotalAssets"))
    roa_before = _ratio(before.get("NetIncome"), older.get("TotalAssets")) if older else None
    if roa_now is None or roa_before is None:
        return _criterion("ROA_ARTIYOR", None, EKSIK,
                          "İki yıllık ROA karşılaştırması için yeterli dönem yok")
    return _criterion(
        "ROA_ARTIYOR", roa_now > roa_before, OK,
        f"ROA {B.yuzde(roa_before, 2, False)} → {B.yuzde(roa_now, 2, False)}",
        [source("NetIncome", rows[index]["date"], now.get("NetIncome")),
         source("NetIncome", rows[index - 1]["date"], before.get("NetIncome"))],
    )


def _c_accruals(now, before, date, prev_date, bank):
    if bank:
        return _criterion("NAKIT_KARDAN_BUYUK", None,
                          GECERSIZ,
                          "Banka nakit akışı bilanço büyümesine bağlıdır, kâr kalitesi ölçüsü değildir")
    cfo = now.get("OperatingCashFlow")
    ni = now.get("NetIncome")
    assets = before.get("TotalAssets")
    if cfo is None or ni is None or not assets:
        return _criterion("NAKIT_KARDAN_BUYUK", None,
                          EKSIK, "Nakit akışı, net kâr veya varlık verisi yok")
    return _criterion(
        "NAKIT_KARDAN_BUYUK", cfo > ni, OK,
        f"Nakit akışı {B.para(cfo)} / net kâr {B.para(ni)}",
        [source("OperatingCashFlow", date, cfo), source("NetIncome", date, ni)],
    )


def _c_leverage(now, before, date, prev_date, bank):
    if bank:
        return _criterion("KALDIRAC_AZALIYOR", None,
                          GECERSIZ, "Banka bilançosunda uzun vadeli borç ayrımı yok")
    lev_now = _ratio(now.get("LongTermDebt"), now.get("TotalAssets"))
    lev_before = _ratio(before.get("LongTermDebt"), before.get("TotalAssets"))
    if lev_now is None or lev_before is None:
        return _criterion("KALDIRAC_AZALIYOR", None,
                          EKSIK, "Uzun vadeli borç verisi yok")
    return _criterion(
        "KALDIRAC_AZALIYOR", lev_now < lev_before, OK,
        f"Uzun vadeli borç/varlık {B.yuzde(lev_before, 1, False)} → "
        f"{B.yuzde(lev_now, 1, False)}",
        [source("LongTermDebt", date, now.get("LongTermDebt")),
         source("LongTermDebt", prev_date, before.get("LongTermDebt"))],
    )


def _c_current_ratio(now, before, date, prev_date, bank):
    if bank:
        return _criterion("CARI_ORAN_ARTIYOR", None, GECERSIZ,
                          "Banka bilançosunda dönen varlık / kısa vadeli yükümlülük ayrımı yok")
    cr_now = _ratio(now.get("CurrentAssets"), now.get("CurrentLiabilities"))
    cr_before = _ratio(before.get("CurrentAssets"), before.get("CurrentLiabilities"))
    if cr_now is None or cr_before is None:
        return _criterion("CARI_ORAN_ARTIYOR", None, EKSIK,
                          "Dönen varlık veya kısa vadeli yükümlülük verisi yok")
    return _criterion(
        "CARI_ORAN_ARTIYOR", cr_now > cr_before, OK,
        f"Cari oran {B.oran(cr_before)} → {B.oran(cr_now)}",
        [source("CurrentAssets", date, now.get("CurrentAssets")),
         source("CurrentLiabilities", date, now.get("CurrentLiabilities"))],
    )


def _c_shares(now, before, date, prev_date):
    shares_now = now.get("OrdinarySharesNumber")
    shares_before = before.get("OrdinarySharesNumber")
    if not shares_now or not shares_before:
        return _criterion("HISSE_IHRACI_YOK", None, EKSIK,
                          "Hisse sayısı verisi yok")
    change = shares_now / shares_before - 1.0
    return _criterion(
        "HISSE_IHRACI_YOK", change <= HISSE_TOLERANSI, OK,
        f"Hisse sayısı değişimi {B.yuzde(change, 2)}",
        [source("OrdinarySharesNumber", date, shares_now),
         source("OrdinarySharesNumber", prev_date, shares_before)],
    )


def _c_gross_margin(now, before, date, prev_date, bank):
    if bank:
        return _criterion("BRUT_MARJ_ARTIYOR", None, GECERSIZ,
                          "Bankalar brüt kâr açıklamaz")
    gm_now = _ratio(now.get("GrossProfit"), now.get("TotalRevenue"))
    gm_before = _ratio(before.get("GrossProfit"), before.get("TotalRevenue"))
    if gm_now is None or gm_before is None:
        return _criterion("BRUT_MARJ_ARTIYOR", None, EKSIK,
                          "Brüt kâr verisi yok")
    return _criterion(
        "BRUT_MARJ_ARTIYOR", gm_now > gm_before, OK,
        f"Brüt marj {B.yuzde(gm_before, 1, False)} → {B.yuzde(gm_now, 1, False)}",
        [source("GrossProfit", date, now.get("GrossProfit")),
         source("TotalRevenue", date, now.get("TotalRevenue"))],
    )


def _c_asset_turnover(rows, index):
    now, before = rows[index]["values"], rows[index - 1]["values"]
    older = rows[index - 2]["values"] if index >= 2 else None
    turn_now = _ratio(now.get("TotalRevenue"), before.get("TotalAssets"))
    turn_before = _ratio(before.get("TotalRevenue"), older.get("TotalAssets")) if older else None
    if turn_now is None or turn_before is None:
        return _criterion("DEVIR_HIZI_ARTIYOR", None, EKSIK,
                          "Üç yıllık varlık/gelir karşılaştırması için yeterli dönem yok")
    return _criterion(
        "DEVIR_HIZI_ARTIYOR", turn_now > turn_before, OK,
        f"Devir hızı {B.oran(turn_before)} → {B.oran(turn_now)}",
        [source("TotalRevenue", rows[index]["date"], now.get("TotalRevenue")),
         source("TotalAssets", rows[index - 1]["date"], before.get("TotalAssets"))],
    )


# ================================================================ Altman Z


def _z_yok(detail: str, status=EKSIK, sources=None) -> dict:
    """`altman_z`'nin başarısız dönüşleri için ortak şekil.

    `zone`/`components` başarı yolunda `**extra` ile ekleniyordu ve yalnızca
    orada vardı; tüketiciler `.get()` kullandığı için şans eseri ayakta
    kalıyordu. Artık her dönüş aynı anahtar kümesini taşıyor.
    """
    return metric(None, status, detail, sources, zone=None, components=None)


def altman_z(client, pack: dict, bank: bool) -> dict:
    """Altman Z-Skoru (imalat/ticaret sürümü).

    Bankalarda ve sigortada model tanımsızdır (işletme sermayesi kavramı yok,
    kaldıraç yapısı tamamen farklı) — hesaplanmaz.
    """
    if bank:
        return _z_yok(
            "Altman Z modeli banka/finans bilançolarında tanımlı değil", GECERSIZ
        )

    rows = F.rows(pack, "annual")
    if not rows:
        return _z_yok("Yıllık tablo yok")

    date = rows[-1]["date"]
    values = rows[-1]["values"]
    assets = values.get("TotalAssets")
    if not assets:
        return _z_yok("Toplam varlık yok")

    working = values.get("WorkingCapital")
    retained = values.get("RetainedEarnings")
    ebit = values.get("EBIT") or values.get("OperatingIncome")
    revenue = values.get("TotalRevenue")
    liabilities = values.get("TotalLiabilities")
    market_cap = F.market_cap_in_statement_currency(client, pack)

    missing = [
        name
        for name, value in (
            ("WorkingCapital", working),
            ("RetainedEarnings", retained),
            ("EBIT", ebit),
            ("TotalRevenue", revenue),
            ("TotalLiabilities", liabilities),
            ("MarketCap", market_cap),
        )
        if value is None
    ]
    if missing:
        if "MarketCap" in missing and pack.get("market_cap_note"):
            return _z_yok(pack["market_cap_note"])
        return _z_yok(f"Eksik kalem: {', '.join(missing)}")

    x1 = working / assets
    x2 = retained / assets
    x3 = ebit / assets
    x4 = market_cap / liabilities if liabilities else None
    x5 = revenue / assets
    if x4 is None:
        return _z_yok("Toplam yükümlülük sıfır veya yok")

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    if z >= ALTMAN_GUVENLI:
        zone = "güvenli bölge"
    elif z >= ALTMAN_SIKISMA:
        zone = "gri bölge"
    else:
        zone = "sıkışma bölgesi"

    return metric(
        z, OK,
        f"Z = {B.oran(z)} → modelin tanımına göre {zone}",
        [source("TotalAssets", date, assets), source("EBIT", date, ebit),
         source("TotalLiabilities", date, liabilities),
         source("Piyasa değeri (tablo para birimine çevrildi)", date, market_cap)],
        zone=zone,
        components={"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5},
    )


# ============================================================== kâr kalitesi


def profit_quality(pack: dict, bank: bool = False) -> dict:
    """Net kâr ile nakit akışı arasındaki sapma.

    İki ölçü: Sloan tahakkuk oranı (kâr ne kadar muhasebe kalemi) ve serbest
    nakit akışı açığı (kârın ne kadarı kasaya girmemiş).

    Bankalarda ikisi de anlamsızdır: faaliyet nakit akışı kredi ve mevduat
    hacmiyle savrulur, kârlılıkla ilgisi yoktur. AKBNK'ta ölçüldüğünde "net
    kârın %155'i nakde dönüşmemiş" gibi tamamen yanıltıcı bir sonuç veriyordu.
    """
    if bank:
        sebep = (
            "Banka nakit akışı mevduat/kredi hareketiyle belirlenir; "
            "kâr kalitesi ölçüsü olarak kullanılamaz"
        )
        gecersiz = metric(None, GECERSIZ, sebep)
        # Dört metrik de dönmeli. Anahtarı hiç döndürmemek, metriği "banka için
        # geçersiz" diye işaretlemek yerine sessizce yok ediyordu; okuyucu
        # ölçülüp ölçülmediğini ayırt edemiyor (bkz. "eksik veri sıfır sayılmaz").
        # `fcf_gap` normal yolda `net_income`/`free_cash_flow` ekstralarını
        # taşıyor; burada da aynı anahtarları (boş) taşımalı, yoksa şekil
        # bank/normal arasında sessizce ayrışır.
        return {"accrual_ratio": gecersiz,
                "fcf_gap": metric(None, GECERSIZ, sebep, net_income=None, free_cash_flow=None),
                "fcf_margin": gecersiz, "fcf_payout": gecersiz, "history": []}

    rows = F.rows(pack, "annual")
    if not rows:
        sebep = "Yıllık tablo yok"
        yok = metric(None, EKSIK, sebep)
        return {"accrual_ratio": yok,
                "fcf_gap": metric(None, EKSIK, sebep, net_income=None, free_cash_flow=None),
                "fcf_margin": yok, "fcf_payout": yok, "history": []}

    date = rows[-1]["date"]
    values = rows[-1]["values"]
    ni = values.get("NetIncome")
    cfo = values.get("OperatingCashFlow")
    fcf = values.get("FreeCashFlow")
    assets = values.get("TotalAssets")

    if ni is None or cfo is None or not assets:
        accrual = metric(None, EKSIK, "Net kâr, nakit akışı veya varlık yok")
    else:
        ratio = (ni - cfo) / assets
        accrual = metric(
            ratio, OK,
            f"Tahakkuk oranı {B.yuzde(ratio, 2)} (net kâr − faaliyet nakit akışı) / varlık",
            [source("NetIncome", date, ni), source("OperatingCashFlow", date, cfo),
             source("TotalAssets", date, assets)],
        )

    revenue = values.get("TotalRevenue")
    if fcf is None or not revenue:
        fcf_margin = metric(None, EKSIK, "Serbest nakit akışı veya gelir yok")
    else:
        margin = fcf / revenue
        # Seviye, değişim değil: `B.puan` (işaretsiz), `B.yuzde` değil. Brüt/net
        # marjlar da böyle basılıyor; "%+16,0" bir marj için yanıltıcı okunuyor.
        fcf_margin = metric(
            margin, OK,
            f"Gelirin {B.puan(margin * 100, 1)} kadarı serbest nakde dönüşmüş",
            [source("FreeCashFlow", date, fcf), source("TotalRevenue", date, revenue)],
        )

    if ni is None or fcf is None or ni == 0:
        gap = metric(None, EKSIK, "Net kâr veya serbest nakit akışı yok",
                     net_income=None, free_cash_flow=None)
    else:
        share = (ni - fcf) / abs(ni)
        gap = metric(
            share, OK,
            f"Net kârın {B.puan(share * 100, 0)} kadarı serbest nakde dönüşmemiş"
            if share > 0 else
            f"Serbest nakit akışı net kârın {B.puan(-share * 100, 0)} üzerinde",
            [source("NetIncome", date, ni), source("FreeCashFlow", date, fcf)],
            net_income=ni, free_cash_flow=fcf,
        )

    div = values.get("CashDividendsPaid")
    if fcf is None or div is None:
        payout = metric(None, EKSIK, "Serbest nakit akışı veya temettü ödemesi verisi yok")
    else:
        div_paid = abs(div)
        if fcf > 0:
            payout_ratio = div_paid / fcf
            payout = metric(
                payout_ratio, OK,
                f"Serbest nakit akışının {B.puan(payout_ratio * 100, 1)} kadarı "
                f"temettü olarak dağıtılmış",
                [source("CashDividendsPaid", date, div), source("FreeCashFlow", date, fcf)],
            )
        else:
            payout = metric(
                None, EKSIK,
                "Serbest nakit akışı negatif olduğu için payout oranı tanımsız",
                [source("FreeCashFlow", date, fcf)],
            )

    history = []
    for row in rows:
        history.append(
            {
                "date": row["date"],
                "net_income": row["values"].get("NetIncome"),
                "operating_cash_flow": row["values"].get("OperatingCashFlow"),
                "free_cash_flow": row["values"].get("FreeCashFlow"),
                "cash_dividends_paid": row["values"].get("CashDividendsPaid"),
            }
        )

    return {"accrual_ratio": accrual, "fcf_gap": gap, "fcf_margin": fcf_margin, "fcf_payout": payout, "history": history}


# ================================================================ borç yapısı


def debt_profile(pack: dict, bank: bool) -> dict:
    rows = F.rows(pack, "annual")
    out: dict[str, dict] = {}

    equity = F.stock_value(pack, "StockholdersEquity")
    total_debt = F.stock_value(pack, "TotalDebt")
    net_debt = F.stock_value(pack, "NetDebt")
    ebitda = F.flow_value(pack, "EBITDA")
    ebit = F.flow_value(pack, "EBIT")
    interest = F.flow_value(pack, "InterestExpense")
    current_debt = F.stock_value(pack, "CurrentDebt")

    # borç / özsermaye
    if total_debt["value"] is None or not equity["value"]:
        out["debt_to_equity"] = metric(None, EKSIK, "Borç veya özsermaye verisi yok")
    elif equity["value"] < 0:
        out["debt_to_equity"] = metric(
            None, EKSIK,
            "Özsermaye negatif — borç/özsermaye oranı bu durumda anlam taşımaz",
        )
    else:
        ratio = total_debt["value"] / equity["value"]
        out["debt_to_equity"] = metric(
            ratio, OK, f"Borç/özsermaye = {B.oran(ratio)}",
            [source("TotalDebt", total_debt["end"], total_debt["value"]),
             source("StockholdersEquity", equity["end"], equity["value"])],
        )

    # net borç / FAVÖK
    if bank:
        out["net_debt_ebitda"] = metric(
            None, GECERSIZ, "Bankalarda FAVÖK açıklanmaz, net borç kavramı farklıdır"
        )
    elif net_debt["value"] is None or not ebitda["value"]:
        out["net_debt_ebitda"] = metric(None, EKSIK, "Net borç veya FAVÖK verisi yok")
    elif ebitda["value"] < 0:
        out["net_debt_ebitda"] = metric(
            None, EKSIK, "FAVÖK negatif — orana çevrilemez"
        )
    elif not net_debt_ebitda_guvenilir(net_debt["value"], ebitda["value"]):
        ratio = net_debt["value"] / ebitda["value"]
        out["net_debt_ebitda"] = metric(
            None, EKSIK,
            f"FAVÖK ({B.para(ebitda['value'])}) şirketin ölçeğine göre neredeyse "
            f"sıfıra düştüğü için oran anlamlı değil (ham hesap {B.oran(ratio)} çıkıyor)",
            [source("NetDebt", net_debt["end"], net_debt["value"]),
             source("EBITDA", ebitda["end"], ebitda["value"])],
        )
    else:
        ratio = net_debt["value"] / ebitda["value"]
        out["net_debt_ebitda"] = metric(
            ratio, OK, f"Net borç/FAVÖK = {B.oran(ratio)} ({ebitda['basis']} FAVÖK)",
            [source("NetDebt", net_debt["end"], net_debt["value"]),
             source("EBITDA", ebitda["end"], ebitda["value"])],
        )

    # faiz karşılama
    if bank:
        out["interest_coverage"] = metric(
            None, GECERSIZ, "Bankalarda faiz gideri faaliyetin kendisidir, örtü oranı tanımsız"
        )
    elif ebit["value"] is None or not interest["value"]:
        out["interest_coverage"] = metric(None, EKSIK, "FVÖK veya faiz gideri verisi yok")
    else:
        expense = abs(interest["value"])
        ratio = ebit["value"] / expense if expense else None
        if ratio is None:
            out["interest_coverage"] = metric(None, EKSIK, "Faiz gideri sıfır")
        else:
            out["interest_coverage"] = metric(
                ratio, OK,
                f"FVÖK faiz giderinin {B.kat(ratio)}",
                [source("EBIT", ebit["end"], ebit["value"]),
                 source("InterestExpense", interest["end"], interest["value"])],
            )

    # kısa vadeli borcun payı
    if bank:
        out["short_term_share"] = metric(
            None, GECERSIZ, "Banka bilançosunda kısa/uzun vade ayrımı bu şekilde yapılmaz"
        )
    elif current_debt["value"] is None or not total_debt["value"]:
        out["short_term_share"] = metric(None, EKSIK, "Kısa vadeli borç verisi yok")
    else:
        share = current_debt["value"] / total_debt["value"]
        out["short_term_share"] = metric(
            share, OK, f"Toplam borcun {B.puan(share * 100, 0)} kadarı kısa vadeli",
            [source("CurrentDebt", current_debt["end"], current_debt["value"]),
             source("TotalDebt", total_debt["end"], total_debt["value"])],
        )

    out["equity_negative"] = metric(
        bool(equity["value"] is not None and equity["value"] < 0),
        OK if equity["value"] is not None else EKSIK,
        "Özsermaye negatif" if (equity["value"] or 0) < 0 else "Özsermaye pozitif",
        [source("StockholdersEquity", equity["end"], equity["value"])],
    )

    if bank or len(rows) < 2:
        out["nwc_change"] = metric(None, GECERSIZ if bank else EKSIK, "NWC analizi yapılamıyor")
    else:
        now = rows[-1]["values"]
        prev = rows[-2]["values"]
        ca_now, cl_now = now.get("CurrentAssets"), now.get("CurrentLiabilities")
        ca_prev, cl_prev = prev.get("CurrentAssets"), prev.get("CurrentLiabilities")
        
        if ca_now is not None and cl_now is not None and ca_prev is not None and cl_prev is not None:
            nwc_now = ca_now - cl_now
            nwc_prev = ca_prev - cl_prev
            if nwc_prev == 0:
                out["nwc_change"] = metric(None, EKSIK, "Önceki dönem işletme sermayesi sıfır")
            else:
                change = (nwc_now - nwc_prev) / abs(nwc_prev)
                out["nwc_change"] = metric(
                    change, OK,
                    f"Bir önceki yıla göre {B.yuzde(change, 1)} "
                    f"(cari varlık − cari yükümlülük)",
                    [source("CurrentAssets", rows[-1]["date"], ca_now),
                     source("CurrentLiabilities", rows[-1]["date"], cl_now)],
                )
        else:
            out["nwc_change"] = metric(None, EKSIK, "Cari varlık/yükümlülük verisi eksik")

    out["history"] = [
        {
            "date": row["date"],
            "total_debt": row["values"].get("TotalDebt"),
            "net_debt": row["values"].get("NetDebt"),
            "ebitda": row["values"].get("EBITDA"),
            "equity": row["values"].get("StockholdersEquity"),
            "net_debt_ebitda": _safe_ratio_positive(
                row["values"].get("NetDebt"), row["values"].get("EBITDA")
            ),
        }
        for row in rows
    ]
    return out


def _safe_ratio_positive(numerator, denominator):
    """Zaman çizgisi ve NAR_BORC/QT_OZET için net borç/FAVÖK.

    Payda neredeyse sıfırsa (bkz. NET_BORC_FAVOK_SUPHE) None döner — grafikte
    ve anlatı cümlelerinde absürt bir sıçrama olarak görünmesin diye. Nokta
    sessizce atlanır, tıpkı gerçekten veri eksik olan dönemler gibi.
    """
    if numerator is None or not denominator or denominator < 0:
        return None
    if not net_debt_ebitda_guvenilir(numerator, denominator):
        return None
    return numerator / denominator


# ==================================================================== marjlar


def margin_profile(pack: dict, bank: bool) -> dict:
    rows = F.rows(pack, "annual")
    series = {"gross": [], "operating": [], "net": []}
    for row in rows:
        values = row["values"]
        revenue = values.get("TotalRevenue")
        if not revenue:
            continue
        gross = values.get("GrossProfit")
        operating = values.get("OperatingIncome") or values.get("EBIT")
        net = values.get("NetIncome")
        if gross is not None:
            series["gross"].append((row["date"], gross / revenue * 100))
        if operating is not None:
            series["operating"].append((row["date"], operating / revenue * 100))
        if net is not None:
            series["net"].append((row["date"], net / revenue * 100))

    out = {"series": series}
    for name in ("gross", "operating", "net"):
        points = series[name]
        if bank and name == "gross":
            out[name + "_trend"] = metric(None, GECERSIZ, "Bankalar brüt kâr açıklamaz",
                                          direction=None)
            continue
        if len(points) < 3:
            out[name + "_trend"] = metric(
                None, EKSIK, "Trend için en az 3 dönem gerekiyor", direction=None
            )
            continue
        slope = _slope([value for _, value in points])
        slope = 0.0 if abs(slope) < 0.05 else slope  # "-0,0 puan" görünmesin
        if slope > MARJ_TREND_ESIGI:
            label = MARJ_GENISLEME
        elif slope < -MARJ_TREND_ESIGI:
            label = MARJ_DARALMA
        else:
            label = MARJ_YATAY
        out[name + "_trend"] = metric(
            slope, OK,
            f"Yılda {B.sayi(slope, 1, isaretli=True)} puan → {label}",
            [source("Marj serisi", f"{points[0][0]}..{points[-1][0]}")],
            direction=label,
        )
    return out


def _slope(values: list[float]) -> float:
    """En küçük kareler eğimi (birim: değer / dönem)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(n))
    return numerator / denominator if denominator else 0.0


# ================================================================== getiriler


def return_profile(pack: dict) -> dict:
    equity = F.stock_value(pack, "StockholdersEquity")
    assets = F.stock_value(pack, "TotalAssets")
    net_income = F.flow_value(pack, "NetIncome")

    out = {}
    if net_income["value"] is None or not equity["value"] or equity["value"] < 0:
        out["roe"] = metric(None, EKSIK, "Net kâr yok veya özsermaye pozitif değil")
    else:
        value = net_income["value"] / equity["value"]
        out["roe"] = metric(
            value, OK, f"ROE = {B.yuzde(value, 1, False)} ({net_income['basis']} kâr)",
            [source("NetIncome", net_income["end"], net_income["value"]),
             source("StockholdersEquity", equity["end"], equity["value"])],
        )

    if net_income["value"] is None or not assets["value"]:
        out["roa"] = metric(None, EKSIK, "Net kâr veya varlık verisi yok")
    else:
        value = net_income["value"] / assets["value"]
        out["roa"] = metric(
            value, OK, f"ROA = {B.yuzde(value, 1, False)}",
            [source("NetIncome", net_income["end"], net_income["value"]),
             source("TotalAssets", assets["end"], assets["value"])],
        )
    return out


# ================================================================ reel büyüme


#: `INF.real_growth`'ün 7 sabit anahtarına `status`/`detail`/`sources`/`history`
#: eklenince tam şekil budur. `len(points) < 2` yolu yalnızca `status`/`detail`
#: dönüyordu (2 anahtar) — tam şeklin geri kalanı `None`/`[]` ile dolduruluyor.
_REEL_BUYUME_ANAHTARLARI = (
    "real", "nominal", "cpi_growth", "basis", "label", "start", "end",
)


def _reel_yok(detail: str) -> dict:
    out = {k: None for k in _REEL_BUYUME_ANAHTARLARI}
    out["status"] = EKSIK
    out["detail"] = detail
    out["sources"] = []
    out["history"] = []
    return out


def real_growth_profile(pack: dict, cpi: dict) -> dict:
    """Gelir ve net kârın nominal + reel büyümesi, ve reel seriler."""
    out = {}
    for key, field in (("revenue", "TotalRevenue"), ("net_income", "NetIncome")):
        points = F.series(pack, field)
        if len(points) < 2:
            out[key] = _reel_yok("En az iki dönem gerekiyor")
            continue

        nominal = F.growth(pack, field)
        growth = INF.real_growth(cpi, nominal, points[-2][0], points[-1][0])
        growth["status"] = OK if growth["real"] is not None else EKSIK
        if growth["real"] is None:
            growth["detail"] = (
                "TÜFE serisi bu dönemleri kapsamıyor; yalnızca nominal gösterilebilir"
                if nominal is not None
                else "Nominal büyüme hesaplanamadı (taban dönem pozitif değil)"
            )
        else:
            # Başarı yolunda `detail` hiç yazılmıyordu; diğer yolla aynı
            # anahtar kümesi için açıkça None.
            growth["detail"] = None
        growth["sources"] = [
            source(field, points[-1][0], points[-1][1]),
            source(field, points[-2][0], points[-2][1]),
            source(growth.get("label") or "TÜFE", f"{points[-2][0][:7]}..{points[-1][0][:7]}",
                   growth.get("cpi_growth")),
        ]
        out[key] = growth

        # Geçmiş dönemlerin reel büyüme dizisi (bayraklar iki yıl geriye bakıyor)
        history = []
        for index in range(1, len(points)):
            nominal_i = (
                points[index][1] / points[index - 1][1] - 1.0
                if points[index - 1][1] and points[index - 1][1] > 0
                else None
            )
            step = INF.real_growth(cpi, nominal_i, points[index - 1][0], points[index][0])
            history.append({"date": points[index][0], **step})
        out[key]["history"] = history

    out["real_revenue_series"] = INF.real_series(cpi, F.series(pack, "TotalRevenue"))
    return out


# ================================================================= değerleme


def valuation(client, pack: dict) -> dict:
    """F/K ve PD/DD — Yahoo'nun hazır alanları kullanılmadan.

    Yahoo `trailingPE` ve `priceToBook` alanlarını, mali tabloları farklı para
    biriminde açıklayan şirketlerde yanlış hesaplıyor (THYAO'da PD/DD 19,7
    diyor, doğrusu 0,41). Piyasa değeri burada tablo para birimine çevrilip
    oran kendimiz hesaplanıyor.
    """
    market_cap = F.market_cap_in_statement_currency(client, pack)
    out = {
        "market_cap_statement_currency": market_cap,
        "currency": pack.get("currency"),
        "price_currency": pack.get("price_currency"),
        "converted": pack.get("currency") != pack.get("price_currency"),
        # Yalnızca erken dönüşte (aşağıda) yazılıyordu; normal yol hiç
        # taşımıyordu. Şimdi her yolda var, dolu ya da None.
        "market_cap_note": pack.get("market_cap_note"),
    }

    net_income = F.flow_value(pack, "NetIncome")
    equity = F.stock_value(pack, "StockholdersEquity")

    if not market_cap:
        reason = pack.get("market_cap_note") or "Piyasa değeri çevrilemedi"
        out["pe"] = metric(None, EKSIK, reason, basis=None)
        out["pb"] = metric(None, EKSIK, reason, basis=None)
        return out

    if not net_income["value"] or net_income["value"] <= 0:
        out["pe"] = metric(
            None, EKSIK,
            "Dönem zararla kapandı veya net kâr yok — F/K tanımsız",
            basis=None,
        )
    else:
        value = market_cap / net_income["value"]
        out["pe"] = metric(
            value, OK, f"F/K = {B.oran(value)} ({net_income['basis']} kâr tabanlı)",
            [source("Piyasa değeri", None, market_cap),
             source("NetIncome", net_income["end"], net_income["value"])],
            basis=net_income["basis"],
        )

    if not equity["value"] or equity["value"] <= 0:
        out["pb"] = metric(None, EKSIK, "Özsermaye pozitif değil — PD/DD tanımsız",
                           basis=None)
    else:
        value = market_cap / equity["value"]
        out["pb"] = metric(
            value, OK, f"PD/DD = {B.oran(value)} ({equity['basis']} özsermaye tabanlı)",
            [source("Piyasa değeri", None, market_cap),
             source("StockholdersEquity", equity["end"], equity["value"])],
            basis=equity["basis"],
        )
    return out


# ============================================================ kalite zaman çizgisi


def quality_timeline(client, symbol: str, analysis: dict | None = None, pack: dict | None = None) -> dict:
    """Katman 4 için tek zaman ekseninde kalite serileri.

    F-Skoru ve reel büyüme yıl-üstü-yıl karşılaştırma gerektirdiği için
    marjlardan bir nokta eksik olur; eksende bu açıkça yazılır.
    """
    if pack is None:
        pack = F.load(client, symbol)
    if analysis is None:
        analysis = analyze(client, symbol, pack)

    # Yalnızca kullanılabilir noktalar çizilir: yeterli kalemi gelmemiş bir
    # yılın skoru grafikte gerçek bir düşüş/çıkış gibi görünür.
    fscore_points = [
        {"date": point["date"], "value": point["score"], "label": point["label"],
         "evaluated": point["evaluated"]}
        for point in analysis["fscore"]["usable_points"]
    ]
    dropped = [
        point["date"]
        for point in analysis["fscore"]["points"]
        if not point["usable"]
    ]
    debt_points = [
        {"date": row["date"], "value": row["net_debt_ebitda"]}
        for row in analysis["debt"].get("history", [])
    ]
    real_revenue = [
        {"date": step["date"], "value": step["real"]}
        for step in analysis["real_growth"].get("revenue", {}).get("history", [])
    ]
    real_income = [
        {"date": step["date"], "value": step["real"]}
        for step in analysis["real_growth"].get("net_income", {}).get("history", [])
    ]

    return {
        "symbol": symbol,
        "currency": pack.get("currency"),
        "fscore": fscore_points,
        "margins": analysis["margins"]["series"],
        "net_debt_ebitda": debt_points,
        "real_revenue_growth": real_revenue,
        "real_net_income_growth": real_income,
        "summary": _timeline_summary(analysis),
        "model_applicable": analysis["fscore"]["model_applicable"],
        "model_note": analysis["fscore"]["model_note"],
        "axis_note": (
            f"F-Skoru {len(fscore_points)} noktadan oluşuyor: skor bir önceki yılla "
            "karşılaştırma gerektirdiği için marjlardan bir dönem az."
            + (
                f" Yeterli kalem gelmediği için çizilmeyen dönem: {', '.join(dropped)}."
                if dropped
                else ""
            )
        ),
    }


def _timeline_summary(analysis: dict) -> dict:
    """QT_OZET — hangi kriterlerin değiştiğini söyleyen tek cümle.

    Nedensellik kurmaz, beklenti belirtmez; yalnızca ne değiştiğini yazar.
    """
    points = analysis["fscore"]["usable_points"]
    if len(points) < 2:
        return {
            "rule_id": "QT_OZET",
            "text": "Kalite skoru karşılaştırması için yeterli tam dönem yok.",
            "sources": [],
        }

    first, last = points[0], points[-1]
    changed = []
    before = {c["id"]: c for c in first["criteria"]}
    for criterion in last["criteria"]:
        old = before.get(criterion["id"])
        if not old or old["status"] != OK or criterion["status"] != OK:
            continue
        if old["passed"] and not criterion["passed"]:
            changed.append(("bozulan", criterion["label"]))
        elif not old["passed"] and criterion["passed"]:
            changed.append(("iyileşen", criterion["label"]))

    broke = [label for kind, label in changed if kind == "bozulan"]
    fixed = [label for kind, label in changed if kind == "iyileşen"]

    parts = [
        f"F-Skoru {first['date'][:4]} yılında {first['score']}/9 iken "
        f"{last['date'][:4]} yılında {last['score']}/9 oldu."
    ]
    if broke:
        parts.append("Bozulan kriterler: " + ", ".join(broke) + ".")
    if fixed:
        parts.append("İyileşen kriterler: " + ", ".join(fixed) + ".")
    if not broke and not fixed:
        parts.append("Kriterlerin geçme/kalma durumu değişmedi.")

    debt_history = [
        row for row in analysis["debt"].get("history", [])
        if row.get("net_debt_ebitda") is not None
    ]
    sources = [source("F-Skoru", last["date"], last["score"])]
    if len(debt_history) >= 2:
        parts.append(
            f"Aynı dönemde net borç/FAVÖK {B.oran(debt_history[0]['net_debt_ebitda'])} → "
            f"{B.oran(debt_history[-1]['net_debt_ebitda'])}."
        )
        sources.append(
            source("NetDebt/EBITDA", debt_history[-1]["date"],
                   debt_history[-1]["net_debt_ebitda"])
        )

    return {"rule_id": "QT_OZET", "text": " ".join(parts), "sources": sources}
