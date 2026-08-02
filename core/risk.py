"""Portföy risk ve kalite röntgeni.

İki ayrı bakış:

**Risk röntgeni** — portföyün *yapısı*. Asıl para kaybettiren şey genelde
yanlış hisse değil, yanlış dağılımdır: tek hisseye yüklenmek, hepsi aynı
sektörde olmak, hepsinin aynı yöne hareket etmesi. Ölçüler: ağırlıklar, HHI
yoğunlaşma endeksi, sektör/para birimi dağılımı, hisseler arası korelasyon,
ağırlıklı portföy volatilitesi, tarihsel en kötü düşüş ve endekse göre beta.

**Kalite röntgeni** — portföyün *içeriği*. F-Skoru dağılımı, ağırlıklı ortalama
kalite, kâr kalitesi zayıf olanların payı, reel büyümesi negatif olanların payı
ve sektör medyanıyla karşılaştırma.

Her iki bakışta da **kapsam oranı** zorunlu olarak raporlanır: "portföyün
%78'i üzerinden hesaplandı" demeden ağırlıklı ortalama vermek, eksik verili
pozisyonları sessizce yok saymak olur.
"""

from __future__ import annotations

import math

from . import bicim as B
from . import universe as U
from .yahoo import YahooError

ISLEM_GUNU = 252          # yıllıklandırma çarpanı
MIN_ORTAK_GUN = 60        # korelasyon/volatilite için gereken en az ortak gün
GERI_BAKIS_GUN = 750      # ~3 yıl

# F-Skoru kovaları (Katman 5)
KOVALAR = (("yuksek", 7, 9, "7–9"), ("orta", 4, 6, "4–6"), ("dusuk", 0, 3, "0–3"))


def _etiket(ad: str, terim: str | None = None) -> dict:
    """Arayüz başlığı + (varsa) core.sozluk anahtarı — tek yerden.

    Eskiden bu başlıklar (ör. "Yıllık volatilite", "Beta") yalnızca app.js'te
    sabit metin olarak duruyordu; sözlük anahtarına bağlamak isteyince
    uydurma bir eşleme kurmak gerekiyordu. Artık burada, verinin kendisiyle
    aynı yerde tanımlı.
    """
    return {"ad": ad, "terim": terim}


RISK_ETIKETLERI = {
    "largest": _etiket("En büyük pozisyon"),
    "top3_share": _etiket("İlk 3 pozisyon"),
    "effective_positions": _etiket("Etkin pozisyon sayısı", "etkin_pozisyon"),
    "hhi": _etiket("HHI", "hhi"),
    "volatility": _etiket("Yıllık volatilite", "volatilite"),
    "drawdown": _etiket("Tarihsel en kötü düşüş", "en_kotu_dusus"),
    "beta": _etiket("Beta", "beta"),
    "correlation": _etiket("Korelasyon", "korelasyon"),
}

KALITE_ETIKETLERI = {
    "weighted_fscore": _etiket("Ağırlıklı F-Skoru", "agirlikli_fskor"),
    "coverage": _etiket("kapsam", "kapsam"),
    "weak_cash_conversion_weight": _etiket("Kâr kalitesi zayıf"),
    "real_shrinking_weight": _etiket("Reel küçülen"),
    "sector_median_fscore": _etiket("Sektör medyanı", "sektor_medyani"),
}


# ============================================================== fiyat serileri


def _returns(client, symbol: str) -> dict[str, float]:
    """Günlük getiri sözlüğü {tarih: getiri}. Seri yoksa boş döner."""
    try:
        closes = client.series(symbol, first_range="5y")
    except YahooError:
        return {}
    closes = closes[-GERI_BAKIS_GUN:]
    out = {}
    for (_, before), (date, after) in zip(closes, closes[1:]):
        if before:
            out[date] = after / before - 1.0
    return out


def _align(series_map: dict[str, dict[str, float]]) -> tuple[list[str], dict[str, list[float]]]:
    """Ortak tarihleri bulup her sembol için aynı uzunlukta getiri listesi üretir."""
    if not series_map:
        return [], {}
    ortak = None
    for returns in series_map.values():
        keys = set(returns)
        ortak = keys if ortak is None else (ortak & keys)
    dates = sorted(ortak or [])
    return dates, {
        symbol: [returns[date] for date in dates] for symbol, returns in series_map.items()
    }


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _covariance(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (len(xs) - 1)


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    cov = _covariance(xs, ys)
    sx, sy = _stdev(xs), _stdev(ys)
    if cov is None or not sx or not sy:
        return None
    return cov / (sx * sy)


def _max_drawdown(values: list[float]) -> float | None:
    """En yüksek tepeden en derin dibe düşüş (negatif oran)."""
    if len(values) < 2:
        return None
    zirve = values[0]
    en_kotu = 0.0
    for value in values:
        zirve = max(zirve, value)
        if zirve > 0:
            en_kotu = min(en_kotu, value / zirve - 1.0)
    return en_kotu


# ================================================================ risk röntgeni


def analyze(client, summary_data: dict, index_symbol: str | None = None) -> dict:
    """Portföyün yapısal riski."""
    acik = [
        satir for satir in summary_data.get("positions", [])
        if satir.get("quantity", 0) > 1e-9 and satir.get("value_base")
    ]
    if not acik:
        return {
            "available": False,
            "reason": "Açık pozisyon yok — işlem girildiğinde risk röntgeni hesaplanır",
        }

    toplam = sum(satir["value_base"] for satir in acik)
    agirliklar = {satir["symbol"]: satir["value_base"] / toplam for satir in acik}

    # --- yoğunlaşma
    sirali = sorted(agirliklar.items(), key=lambda item: -item[1])
    hhi = sum(weight ** 2 for weight in agirliklar.values())
    yogunlasma = {
        "weights": [{"symbol": symbol, "weight": weight} for symbol, weight in sirali],
        "largest": sirali[0] if sirali else None,
        "top3_share": sum(weight for _, weight in sirali[:3]),
        "hhi": hhi,
        "effective_positions": 1.0 / hhi if hhi else None,
        "note": (
            "HHI ağırlıkların karelerinin toplamıdır. 1/HHI 'etkin pozisyon sayısı' "
            "verir: 10 hisseniz olsa da biri portföyün %80'iyse etkin sayı 1'e yakın "
            "çıkar."
        ),
    }

    # --- dağılımlar
    sektorler: dict[str, float] = {}
    paralar: dict[str, float] = {}
    for satir in acik:
        sektor = satir.get("sector") or "bilinmiyor"
        sektorler[sektor] = sektorler.get(sektor, 0.0) + agirliklar[satir["symbol"]]
        para = satir.get("currency") or "bilinmiyor"
        paralar[para] = paralar.get(para, 0.0) + agirliklar[satir["symbol"]]

    # --- getiri serileri
    series_map = {satir["symbol"]: _returns(client, satir["symbol"]) for satir in acik}
    series_map = {symbol: returns for symbol, returns in series_map.items() if returns}
    dates, aligned = _align(series_map)

    kapsam = sum(agirliklar[symbol] for symbol in aligned) if aligned else 0.0
    yeterli = len(dates) >= MIN_ORTAK_GUN

    korelasyon = None
    volatilite = None
    dusus = None
    beta = None

    if aligned and yeterli:
        semboller = list(aligned)

        # korelasyon matrisi
        korelasyon = {
            "symbols": semboller,
            "matrix": [
                [
                    1.0 if a == b else _correlation(aligned[a], aligned[b])
                    for b in semboller
                ]
                for a in semboller
            ],
            "days": len(dates),
        }
        ciftler = [
            (a, b, _correlation(aligned[a], aligned[b]))
            for index, a in enumerate(semboller)
            for b in semboller[index + 1:]
        ]
        gecerli = [(a, b, value) for a, b, value in ciftler if value is not None]
        if gecerli:
            korelasyon["average"] = sum(value for _, _, value in gecerli) / len(gecerli)
            korelasyon["highest"] = max(gecerli, key=lambda item: item[2])
            korelasyon["lowest"] = min(gecerli, key=lambda item: item[2])

        # ağırlıklı portföy volatilitesi (kovaryans matrisinden)
        yeniden = {symbol: agirliklar[symbol] / kapsam for symbol in semboller}
        varyans = 0.0
        for a in semboller:
            for b in semboller:
                cov = _covariance(aligned[a], aligned[b])
                if cov is None:
                    varyans = None
                    break
                varyans += yeniden[a] * yeniden[b] * cov
            if varyans is None:
                break
        if varyans is not None and varyans >= 0:
            volatilite = {
                "daily": math.sqrt(varyans),
                "annual": math.sqrt(varyans * ISLEM_GUNU),
                "coverage": kapsam,
                "days": len(dates),
                "note": (
                    "Portföy volatilitesi tek tek hisselerin volatilitesinin ortalaması "
                    "değildir; hisseler aynı yöne hareket ettikçe yükselir, "
                    "birbirini dengeledikçe düşer."
                ),
            }

        # tarihsel düşüş simülasyonu (bugünkü ağırlıklarla)
        seri = [1.0]
        for index in range(len(dates)):
            gunluk = sum(yeniden[symbol] * aligned[symbol][index] for symbol in semboller)
            seri.append(seri[-1] * (1.0 + gunluk))
        dusus = {
            "max_drawdown": _max_drawdown(seri),
            "period": f"{dates[0]} – {dates[-1]}" if dates else None,
            "days": len(dates),
            "note": (
                "Bugünkü ağırlıklar geçmişe uygulanarak hesaplandı: bu portföy o "
                "dönemde tutulmuş olsaydı zirveden ne kadar geri çekilirdi."
            ),
        }

        # endekse göre beta
        index_symbol = index_symbol or _index_for(acik)
        index_returns = _returns(client, index_symbol)
        if index_returns:
            ortak = [date for date in dates if date in index_returns]
            if len(ortak) >= MIN_ORTAK_GUN:
                portfoy = [
                    sum(yeniden[symbol] * series_map[symbol][date] for symbol in semboller)
                    for date in ortak
                ]
                endeks = [index_returns[date] for date in ortak]
                cov = _covariance(portfoy, endeks)
                var = _covariance(endeks, endeks)
                if cov is not None and var:
                    beta = {
                        "value": cov / var,
                        "index": index_symbol,
                        "days": len(ortak),
                        "note": (
                            "Beta 1 ise portföy endeksle birlikte hareket ediyor, "
                            "1'in üstünde daha oynak, altında daha sakin demektir."
                        ),
                    }

    return {
        "available": True,
        "concentration": yogunlasma,
        "sectors": [
            {"sector": sektor, "weight": weight}
            for sektor, weight in sorted(sektorler.items(), key=lambda item: -item[1])
        ],
        "currencies": [
            {"currency": para, "weight": weight}
            for para, weight in sorted(paralar.items(), key=lambda item: -item[1])
        ],
        "correlation": korelasyon,
        "volatility": volatilite,
        "drawdown": dusus,
        "beta": beta,
        "coverage": kapsam,
        "coverage_note": (
            f"Fiyat serisi bulunan pozisyonlar portföyün {B.puan(kapsam * 100, 0)} kadarını "
            "oluşturuyor; oran bazlı ölçüler bu kısım üzerinden hesaplandı."
        )
        if aligned
        else "Hiçbir pozisyon için yeterli fiyat serisi bulunamadı.",
        "insufficient_history": bool(aligned) and not yeterli,
        "etiketler": RISK_ETIKETLERI,
    }


def symbol_price_stats(client, symbol: str, days: int = ISLEM_GUNU) -> dict:
    """Tek sembol için geçmiş fiyat istatistiği — tanımlayıcı, tahmin değil.

    Portföy röntgeninin volatilite/düşüş hesaplarını tek hisseye uygular.
    LLM raporunun fiyat bölümü bunu kullanıyor: rapor aksi hâlde tamamen
    fiyat-körü, oysa PD/DD ve Altman'ın X4 terimi piyasa değeri içeriyor —
    bir okuyucu, PD/DD 0,50'nin %60 düşüş sonrası mı yoksa zirvede mi
    olduğunu bilmeden o sayıyı doğru okuyamıyor.

    Ağ hatası veya yetersiz geçmişte `available: False` döner; çağıran taraf
    bölümü sessizce atlar, rapor bu yüzden hiç düşmez.

    `client.series()` kullanılır (`_returns()` ile aynı yol) — önbelleği
    doğrudan okumak yerine gerektiğinde tazeler. Önbellek doğrudan okunursa
    (eski hâli) yalnızca daha önce farklı bir sebeple (ör. `_returns()`)
    çekilmiş sembollerde veri bulunur; ilk kez bakılan bir sembolde bölüm
    hiçbir iz bırakmadan kaybolurdu.
    """
    try:
        kapanislar = client.series(symbol, first_range="5y")
    except YahooError:
        return {"available": False, "reason": "Fiyat serisi çekilemedi (ağ/kaynak hatası)"}
    except Exception:  # noqa: BLE001 — fiyat verisi bölümü isteğe bağlı, rapor düşmemeli
        return {"available": False, "reason": "Fiyat serisi okunurken beklenmeyen bir hata oluştu"}

    kapanislar = kapanislar[-days:]
    if len(kapanislar) < MIN_ORTAK_GUN:
        return {
            "available": False,
            "reason": f"Yeterli fiyat geçmişi yok (en az {MIN_ORTAK_GUN} gün gerekiyor)",
        }

    seviyeler = [deger for _, deger in kapanislar]
    tarihler = [tarih for tarih, _ in kapanislar]

    getiriler = []
    for onceki, sonraki in zip(seviyeler, seviyeler[1:]):
        if onceki:
            getiriler.append(sonraki / onceki - 1.0)

    sapma = _stdev(getiriler)
    en_dusuk, en_yuksek, son = min(seviyeler), max(seviyeler), seviyeler[-1]
    aralik = en_yuksek - en_dusuk

    return {
        "available": True,
        "start": tarihler[0],
        "end": tarihler[-1],
        "days": len(kapanislar),
        "last": son,
        "low": en_dusuk,
        "high": en_yuksek,
        # aralığın alt ucundan ne kadar yukarıda (0 = dip, 1 = zirve)
        "position": ((son - en_dusuk) / aralik) if aralik else None,
        "change": (son / seviyeler[0] - 1.0) if seviyeler[0] else None,
        "annual_volatility": (sapma * math.sqrt(ISLEM_GUNU)) if sapma else None,
        # _max_drawdown SEVİYE serisi bekliyor (value/peak - 1), getiri değil
        "max_drawdown": _max_drawdown(seviyeler),
    }


def _index_for(rows: list[dict]) -> str:
    """Ağırlığın çoğunluğu hangi piyasadaysa o piyasanın endeksi."""
    tr = sum(1 for satir in rows if str(satir["symbol"]).upper().endswith(".IS"))
    return U.MARKETS["bist" if tr >= len(rows) / 2 else "us"]["index"]


# ============================================================= kalite röntgeni


def portfolio_quality(summary_data: dict, context: dict | None) -> dict:
    """Portföyün içeriğinin finansal kalitesi (Katman 5)."""
    acik = [
        satir for satir in summary_data.get("positions", [])
        if satir.get("quantity", 0) > 1e-9 and satir.get("value_base")
    ]
    if not acik:
        return {"available": False, "reason": "Açık pozisyon yok"}
    if not context or not context.get("symbols"):
        return {
            "available": False,
            "reason": (
                "Bağlam taraması yapılmamış. Kalite karşılaştırması için önce "
                "`python tools/tarama.py bist` çalıştırılmalı."
            ),
        }

    toplam = sum(satir["value_base"] for satir in acik)
    symbols = context["symbols"]

    kovalar = {anahtar: {"label": etiket, "weight": 0.0, "count": 0, "symbols": []}
               for anahtar, _, _, etiket in KOVALAR}
    kapsanan = disarida_banka = 0.0
    fskor_toplam = fskor_agirlik = 0.0
    altman_toplam = altman_agirlik = 0.0
    zayif_nakit = reel_negatif = 0.0
    eksik: list[str] = []
    taranmamis: list[str] = []
    taranmamis_agirlik = 0.0

    for satir in acik:
        symbol = satir["symbol"]
        weight = satir["value_base"] / toplam
        row = symbols.get(symbol)
        if not row:
            # Pozisyon taranan evrenin dışında (ör. portföyde ABD hissesi var
            # ama yalnızca BIST taranmış). Bunu "veri eksik" ile karıştırmamak
            # gerekir: çözümü farklı, o evreni taramak.
            taranmamis.append(symbol)
            taranmamis_agirlik += weight
            continue

        metrics = row.get("metrics") or {}
        na = set(row.get("not_applicable") or ())
        screen = row.get("screen") or {}

        if "fscore" in na:
            disarida_banka += weight
        else:
            fscore = metrics.get("fscore")
            if fscore is None:
                eksik.append(symbol)
            else:
                kapsanan += weight
                fskor_toplam += weight * fscore
                fskor_agirlik += weight
                for anahtar, alt, ust, _ in KOVALAR:
                    if alt <= fscore <= ust:
                        kovalar[anahtar]["weight"] += weight
                        kovalar[anahtar]["count"] += 1
                        kovalar[anahtar]["symbols"].append(symbol)
                        break

        if "altman_z" not in na and metrics.get("altman_z") is not None:
            altman_toplam += weight * metrics["altman_z"]
            altman_agirlik += weight

        if screen.get("fcf_ge_net_income") is False:
            zayif_nakit += weight
        if (metrics.get("real_revenue_growth") or 0) < 0:
            reel_negatif += weight

    sektor_karsilastirma = _sector_comparison(acik, toplam, context)

    return {
        "available": fskor_agirlik > 0,
        "buckets": [kovalar[anahtar] for anahtar, _, _, _ in KOVALAR],
        "weighted_fscore": (fskor_toplam / fskor_agirlik) if fskor_agirlik else None,
        "weighted_altman": (altman_toplam / altman_agirlik) if altman_agirlik else None,
        "altman_coverage": altman_agirlik,
        "excluded_financial_weight": disarida_banka,
        "weak_cash_conversion_weight": zayif_nakit,
        "real_shrinking_weight": reel_negatif,
        "coverage": kapsanan,
        "coverage_note": _kapsam_notu(
            kapsanan, disarida_banka, taranmamis_agirlik, taranmamis, eksik
        ),
        "unscanned_symbols": sorted(set(taranmamis)),
        "unscanned_weight": taranmamis_agirlik,
        "missing_symbols": sorted(set(eksik)),
        "sector_comparison": sektor_karsilastirma,
        "note": (
            "F-Skoru geçmiş mali tablolardan hesaplanan bir ölçüttür; yüksek skor "
            "gelecek getiri hakkında bilgi taşımaz."
        ),
        "etiketler": KALITE_ETIKETLERI,
    }


def _kapsam_notu(kapsanan, banka, taranmamis_agirlik, taranmamis, eksik) -> str:
    """Ağırlıklı ortalamanın neyi kapsamadığını açıkça söyler.

    Kapsamın dışında kalan üç ayrı sebep var ve çözümleri farklı: finans
    şirketleri (model tanımsız), taranmamış evren (tarama çalıştırılmalı),
    eksik veri (kaynakta yok). Hepsini tek "%25" rakamına gömmek, kullanıcının
    neyi düzeltebileceğini gizler.
    """
    parcalar = [
        f"Ağırlıklı ortalama F-Skoru portföyün {B.puan(kapsanan * 100, 0)} kadarı "
        "üzerinden hesaplandı"
    ]
    if banka:
        parcalar.append(
            f"{B.puan(banka * 100, 0)} kadarı finans şirketi olduğu için modelin tanımı "
            "gereği dışarıda"
        )
    if taranmamis_agirlik:
        liste = ", ".join(sorted(set(taranmamis))[:4])
        parcalar.append(
            f"{B.puan(taranmamis_agirlik * 100, 0)} kadarı taranmamış bir evrende ({liste}) "
            "— o piyasanın taraması çalıştırılırsa hesaba katılır"
        )
    if eksik:
        parcalar.append(
            f"{len(set(eksik))} pozisyonda skor hesaplanamadı (kaynakta veri yok)"
        )
    return "; ".join(parcalar) + "."


def _sector_comparison(rows: list[dict], toplam: float, context: dict) -> list[dict]:
    """Portföy ağırlığı ile o sektörün kalite medyanını yan yana koyar."""
    symbols = context["symbols"]
    sector_stats = context.get("sector_stats") or {}

    gruplar: dict[str, dict] = {}
    for satir in rows:
        row = symbols.get(satir["symbol"])
        sektor = (row or {}).get("sector") or satir.get("sector") or "bilinmiyor"
        grup = gruplar.setdefault(
            sektor, {"sector": sektor, "weight": 0.0, "symbols": [], "portfolio_fscore": []}
        )
        grup["weight"] += satir["value_base"] / toplam
        grup["symbols"].append(satir["symbol"])
        fscore = ((row or {}).get("metrics") or {}).get("fscore")
        if fscore is not None and "fscore" not in ((row or {}).get("not_applicable") or ()):
            grup["portfolio_fscore"].append(fscore)

    out = []
    for sektor, grup in sorted(gruplar.items(), key=lambda item: -item[1]["weight"]):
        stats = (sector_stats.get(sektor) or {}).get("fscore") or {}
        kendi = grup["portfolio_fscore"]
        out.append(
            {
                "sector": sektor,
                "weight": grup["weight"],
                "symbols": grup["symbols"],
                "portfolio_median_fscore": (
                    sorted(kendi)[len(kendi) // 2] if kendi else None
                ),
                "sector_median_fscore": stats.get("median"),
                "sector_n": stats.get("n", 0),
                "sufficient": stats.get("sufficient", False),
            }
        )
    return out
