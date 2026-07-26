"""Piyasa genel bakışı.

Bu modül bilinçli olarak **hiç yorum cümlesi üretmez**. Yalnızca sayısal
fotoğraf verir: evren medyanları, sektör tablosu, oranlar ve örneklem
büyüklükleri. "İyi piyasa / kötü piyasa" gibi bir ifade şablon havuzunda
tanımlı bile değil — piyasanın geneli hakkında yargı üretmek, tek tek
şirketler hakkında üretmekten daha az değil daha çok spekülatif olur.

Ağ isteği yapmaz; tamamen `context.py`'ın bıraktığı bağlam kaydından çalışır.
"""

from __future__ import annotations

import statistics

from . import context as C

MIN_ORNEKLEM = C.MIN_ORNEKLEM

# Sektör tablosunda gösterilecek metrikler.
SEKTOR_METRIKLERI = (
    "fscore",
    "net_debt_ebitda",
    "operating_margin",
    "roe",
    "real_revenue_growth",
    "pe",
    "pb",
)

# Bankalarda tanımsız olduğu için ayrıca raporlanan metrikler.
BANKA_DISI_METRIKLER = ("net_debt_ebitda", "altman_z", "gross_margin")

EN_COK_SAYISI = 10


def market_snapshot(context: dict) -> dict:
    """Evrenin sayısal fotoğrafı."""
    symbols = context.get("symbols") or {}
    if not symbols:
        return {
            "available": False,
            "reason": (
                "Bağlam taraması yapılmamış. Önce `python tools/tarama.py bist` "
                "çalıştırılmalı."
            ),
        }

    evren = context.get("universe_stats") or {}

    return {
        "available": True,
        "market": context.get("market"),
        "scanned": len(symbols),
        "attempted": context.get("attempted"),
        "error_count": len(context.get("errors") or []),
        "headline": _headline(symbols, evren),
        "sectors": _sector_table(context),
        "movers": _movers(symbols),
        "distributions": _distributions(symbols),
        "note": (
            "Bu ekran evrenin sayısal fotoğrafını gösterir. Tabloların hiçbiri "
            "piyasa yönü veya beklenti bildirmez; her satırda örneklem büyüklüğü "
            "(n) yazılıdır."
        ),
    }


# ---------------------------------------------------------------- üst rakamlar


def _headline(symbols: dict, evren: dict) -> list[dict]:
    """Üstte duran birkaç medyan ve oran."""
    out: list[dict] = []

    for metrik, etiket, bicim in (
        ("fscore", "Medyan F-Skoru", "score"),
        ("net_debt_ebitda", "Medyan net borç/FAVÖK", "ratio"),
        ("operating_margin", "Medyan faaliyet marjı", "points"),
        ("pe", "Medyan F/K", "ratio"),
        ("pb", "Medyan PD/DD", "ratio"),
    ):
        stats = evren.get(metrik) or {}
        out.append(
            {
                "key": metrik,
                "label": etiket,
                "value": stats.get("median"),
                "n": stats.get("n", 0),
                "sufficient": stats.get("sufficient", False),
                "format": bicim,
                "excludes_financials": metrik in BANKA_DISI_METRIKLER,
            }
        )

    out.append(_share(symbols, "Serbest nakit akışı pozitif olan şirket oranı",
                      "pozitif_fcf", lambda row: (row.get("screen") or {}).get("fcf_positive")))
    out.append(
        _share(
            symbols,
            "Geliri reel olarak büyüyen şirket oranı",
            "reel_buyuyen",
            lambda row: _bool_or_none((row.get("metrics") or {}).get("real_revenue_growth"), 0.0),
        )
    )
    out.append(
        _share(
            symbols,
            "Verisi güncel olan şirket oranı",
            "veri_guncel",
            lambda row: (row.get("screen") or {}).get("data_fresh"),
        )
    )
    out.append(
        _share(
            symbols,
            "F-Skoru 7 ve üzeri olan şirket oranı",
            "fskor_yuksek",
            lambda row: (
                None
                if "fscore" in (row.get("not_applicable") or ())
                or (row.get("metrics") or {}).get("fscore") is None
                else (row["metrics"]["fscore"] >= 7)
            ),
        )
    )
    return out


def _bool_or_none(value, threshold: float):
    return None if value is None else value > threshold


def _share(symbols: dict, label: str, key: str, getter) -> dict:
    """Bir boolean koşulun evrendeki oranı; kararsız (None) olanlar sayılmaz."""
    evet = hayir = 0
    for row in symbols.values():
        sonuc = getter(row)
        if sonuc is None:
            continue
        if sonuc:
            evet += 1
        else:
            hayir += 1
    toplam = evet + hayir
    return {
        "key": key,
        "label": label,
        "value": (evet / toplam) if toplam else None,
        "count": evet,
        "n": toplam,
        "sufficient": toplam >= MIN_ORNEKLEM,
        "format": "share",
    }


# ------------------------------------------------------------------- sektörler


def _sector_table(context: dict) -> list[dict]:
    symbols = context.get("symbols") or {}
    sector_stats = context.get("sector_stats") or {}

    sayimlar: dict[str, int] = {}
    for row in symbols.values():
        sektor = row.get("sector")
        if sektor:
            sayimlar[sektor] = sayimlar.get(sektor, 0) + 1

    tablo = []
    for sektor, adet in sorted(sayimlar.items(), key=lambda item: -item[1]):
        stats = sector_stats.get(sektor) or {}
        satir = {"sector": sektor, "count": adet, "metrics": {}}
        for metrik in SEKTOR_METRIKLERI:
            item = stats.get(metrik) or {}
            satir["metrics"][metrik] = {
                "label": C.METRIK_ADLARI.get(metrik, metrik),
                "median": item.get("median"),
                "n": item.get("n", 0),
                "sufficient": item.get("sufficient", False),
            }
        # Borç metrikleri finans şirketlerinde tanımsız; kaç şirketin dışlandığı yazılır.
        satir["financials_excluded"] = sum(
            1
            for row in symbols.values()
            if row.get("sector") == sektor and "net_debt_ebitda" in (row.get("not_applicable") or ())
        )
        tablo.append(satir)
    return tablo


# --------------------------------------------------------------- en çok değişen


def _movers(symbols: dict) -> dict:
    """F-Skoru en çok yükselen ve düşen şirketler.

    Yalnızca sembol, ad ve değişim miktarı listelenir. Sıralamada üstte olmak
    bir niteleme değildir; hangi şirketin skoru kaç puan oynadığını gösterir.
    """
    kayitlar = []
    for symbol, row in symbols.items():
        if "fscore" in (row.get("not_applicable") or ()):
            continue
        screen = row.get("screen") or {}
        degisim = screen.get("fscore_change_yoy")
        if degisim is None:
            continue
        kayitlar.append(
            {
                "symbol": symbol,
                "name": row.get("name"),
                "sector": row.get("sector"),
                "change": degisim,
                "current": (row.get("metrics") or {}).get("fscore"),
            }
        )

    kayitlar.sort(key=lambda item: item["change"], reverse=True)
    yukselenler = [item for item in kayitlar if item["change"] > 0][:EN_COK_SAYISI]
    dusenler = [item for item in reversed(kayitlar) if item["change"] < 0][:EN_COK_SAYISI]

    return {
        "risers": yukselenler,
        "fallers": dusenler,
        "n": len(kayitlar),
        "basis": "Son yıl ile bir önceki yılın F-Skoru karşılaştırması",
        "note": (
            "Bu liste yalnızca skor değişimini gösterir. Skorun yükselmesi geçmiş "
            "mali tablolardaki bir değişimi ifade eder, fiyat hakkında bilgi vermez."
        ),
    }


# ------------------------------------------------------------------ dağılımlar


def _distributions(symbols: dict) -> dict:
    """F-Skoru histogramı ve para birimi dağılımı."""
    histogram = {score: 0 for score in range(10)}
    finans = 0
    for row in symbols.values():
        if "fscore" in (row.get("not_applicable") or ()):
            finans += 1
            continue
        fscore = (row.get("metrics") or {}).get("fscore")
        if fscore is None:
            continue
        histogram[int(fscore)] += 1

    paralar: dict[str, int] = {}
    for row in symbols.values():
        para = row.get("currency") or "bilinmiyor"
        paralar[para] = paralar.get(para, 0) + 1

    skorlar = [
        score for score, adet in histogram.items() for _ in range(adet)
    ]

    return {
        "fscore_histogram": [
            {"score": score, "count": adet} for score, adet in sorted(histogram.items())
        ],
        "fscore_n": len(skorlar),
        "fscore_median": statistics.median(skorlar) if skorlar else None,
        "financials_excluded": finans,
        "currencies": [
            {"currency": para, "count": adet}
            for para, adet in sorted(paralar.items(), key=lambda item: -item[1])
        ],
        "note": (
            f"F-Skoru histogramı {len(skorlar)} şirket üzerinden; {finans} finans "
            "şirketi modelin tanımı gereği dışarıda."
        ),
    }
