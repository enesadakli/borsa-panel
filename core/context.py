"""Metrik bağlamı — sektör medyanı, yüzdelik dilim ve kendi trendi.

Tek başına "F/K = 12,8" bir şey söylemez. Aynı sektörün medyanı 6 ise başka,
25 ise başka bir tablo çıkar. Bu modül her metrik için dört bilgi üretir ve
skor kartıyla tarayıcıda bunlar **varsayılan olarak** görünür:

    kendi trendi      : şirketin 4 yıllık eğilimi (artış / düşüş / yatay)
    sektör medyanı    : aynı sektördeki şirketlerin ortası
    sektör yüzdeliği  : şirket sektör içinde nerede
    evren yüzdeliği   : şirket tüm evrende nerede

Yüzdelik dilim bir yargı değildir: "F/K'sı sektörün %80'inden yüksek" cümlesi
pahalı demek değil, konumu söylemektir. Yorum kullanıcıya aittir.

**Dışlama kuralları.** Bir metrik şirkette `sektorde_gecersiz` ise şirket o
metriğin medyanından tamamen çıkarılır (sıfır sayılmaz). Bankalar F-Skoru
medyanına hiç girmez, çünkü model onlar için tanımlı değildir. Sektörde beşten
az geçerli şirket varsa medyan ve yüzdelik `None` döner ve ekranda örneklem
büyüklüğü yazar.
"""

from __future__ import annotations

import bisect
import statistics
import time

from . import cache as cache_mod
from . import fundamentals as F
from . import health as H
from . import inflation as INF
from . import universe as U
from .yahoo import YahooError

TTL_BAGLAM = 7 * cache_mod.GUN

# Sektör medyanının anlamlı sayılması için gereken en az şirket sayısı.
MIN_ORNEKLEM = 5

# Trend sınıflaması: yıllık göreli değişim bu eşiğin altındaysa yatay.
TREND_ESIGI = 0.02

# (anahtar, ekran adı) — skor kartı ve tarayıcı bu sırayı kullanır.
METRIKLER = (
    ("fscore", "F-Skoru"),
    ("altman_z", "Altman Z"),
    ("roe", "ROE"),
    ("roa", "ROA"),
    ("gross_margin", "Brüt marj"),
    ("operating_margin", "Faaliyet marjı"),
    ("net_margin", "Net marj"),
    ("net_debt_ebitda", "Net borç/FAVÖK"),
    ("debt_to_equity", "Borç/özsermaye"),
    ("interest_coverage", "Faiz karşılama"),
    ("fcf_gap", "Kâr–nakit sapması"),
    ("real_revenue_growth", "Reel gelir büyümesi"),
    ("real_income_growth", "Reel net kâr büyümesi"),
    ("pe", "F/K"),
    ("pb", "PD/DD"),
    ("dividend_yield", "Temettü verimi"),
)

METRIK_ADLARI = dict(METRIKLER)


# ============================================================ metrik çıkarma


def extract_metrics(analysis: dict, profile: dict | None = None) -> dict:
    """Analiz çıktısından tek düzey metrik sözlüğü.

    Değer `None` ise metrik hesaplanamadı; `not_applicable` içindeyse sektörde
    tanımsız. İkisi farklı şeydir ve medyan hesabında farklı davranırlar.
    """
    values: dict[str, float | None] = {}
    not_applicable: set[str] = set()

    def take(key: str, node: dict | None):
        if not node:
            values[key] = None
            return
        if node.get("status") == H.GECERSIZ:
            values[key] = None
            not_applicable.add(key)
            return
        values[key] = node.get("value") if node.get("status") == H.OK else None

    fscore = analysis.get("fscore") or {}
    latest = fscore.get("latest")
    if not fscore.get("model_applicable"):
        values["fscore"] = None
        not_applicable.add("fscore")
    else:
        values["fscore"] = latest["score"] if latest else None

    take("altman_z", analysis.get("altman"))
    take("roe", (analysis.get("returns") or {}).get("roe"))
    take("roa", (analysis.get("returns") or {}).get("roa"))

    margins = analysis.get("margins") or {}
    for key, name in (("gross_margin", "gross"), ("operating_margin", "operating"),
                      ("net_margin", "net")):
        trend_node = margins.get(name + "_trend") or {}
        series = (margins.get("series") or {}).get(name) or []
        if trend_node.get("status") == H.GECERSIZ:
            values[key] = None
            not_applicable.add(key)
        else:
            values[key] = series[-1][1] if series else None

    debt = analysis.get("debt") or {}
    take("net_debt_ebitda", debt.get("net_debt_ebitda"))
    take("debt_to_equity", debt.get("debt_to_equity"))
    take("interest_coverage", debt.get("interest_coverage"))
    take("fcf_gap", (analysis.get("profit_quality") or {}).get("fcf_gap"))

    real = analysis.get("real_growth") or {}
    values["real_revenue_growth"] = (real.get("revenue") or {}).get("real")
    values["real_income_growth"] = (real.get("net_income") or {}).get("real")

    valuation = analysis.get("valuation") or {}
    take("pe", valuation.get("pe"))
    take("pb", valuation.get("pb"))

    values["dividend_yield"] = (profile or {}).get("dividend_yield")

    return {"values": values, "not_applicable": sorted(not_applicable)}


def extract_trends(analysis: dict) -> dict:
    """Şirketin kendi 4 yıllık eğilimleri (seri hâlinde gelen metrikler için)."""
    trends: dict[str, dict] = {}
    margins = (analysis.get("margins") or {}).get("series") or {}
    for key, name in (("gross_margin", "gross"), ("operating_margin", "operating"),
                      ("net_margin", "net")):
        trends[key] = trend([value for _, value in margins.get(name) or []])

    debt_history = [
        row["net_debt_ebitda"]
        for row in (analysis.get("debt") or {}).get("history", [])
        if row.get("net_debt_ebitda") is not None
    ]
    trends["net_debt_ebitda"] = trend(debt_history)

    fscore_points = [p["score"] for p in (analysis.get("fscore") or {}).get("usable_points", [])]
    trends["fscore"] = trend(fscore_points)

    revenue_history = [
        step["real"]
        for step in ((analysis.get("real_growth") or {}).get("revenue") or {}).get("history", [])
        if step.get("real") is not None
    ]
    trends["real_revenue_growth"] = trend(revenue_history)
    return trends


def extract_screen_fields(analysis: dict) -> dict:
    """Tarayıcının kullandığı, medyanı alınmayan ek alanlar.

    Bunlar sektör medyanına girmez (çoğu boolean veya değişim miktarı) ama
    filtrelerde gerekir. Bağlam kaydında tutulmazsa tarayıcı her sorguda
    yüzlerce mali tablo paketini diskten okumak zorunda kalır.
    """
    out: dict = {}

    quality = analysis.get("profit_quality") or {}
    history = quality.get("history") or []
    if history:
        son = history[-1]
        fcf = son.get("free_cash_flow")
        net_income = son.get("net_income")
        out["free_cash_flow"] = fcf
        out["net_income"] = net_income
        out["fcf_positive"] = None if fcf is None else fcf > 0
        out["fcf_ge_net_income"] = (
            None if (fcf is None or net_income is None) else fcf >= net_income
        )

    debt_history = [
        row["net_debt_ebitda"]
        for row in (analysis.get("debt") or {}).get("history", [])
        if row.get("net_debt_ebitda") is not None
    ]
    if len(debt_history) >= 2:
        out["net_debt_ebitda_delta"] = debt_history[-1] - debt_history[0]
        out["net_debt_ebitda_delta_yoy"] = debt_history[-1] - debt_history[-2]

    fscore = analysis.get("fscore") or {}
    points = fscore.get("usable_points") or []
    if fscore.get("model_applicable") and len(points) >= 2:
        out["fscore_change"] = points[-1]["score"] - points[0]["score"]
        out["fscore_change_yoy"] = points[-1]["score"] - points[-2]["score"]
        out["fscore_span_years"] = (
            int(points[-1]["date"][:4]) - int(points[0]["date"][:4])
        )

    margins = analysis.get("margins") or {}
    for key, name in (("gross", "gross"), ("operating", "operating"), ("net", "net")):
        node = margins.get(name + "_trend") or {}
        out[f"{key}_margin_direction"] = node.get("direction")

    real = analysis.get("real_growth") or {}
    revenue_history = [
        step for step in (real.get("revenue") or {}).get("history", [])
        if step.get("real") is not None
    ]
    if len(revenue_history) >= 2:
        # Son dönemden geriye doğru **ardışık** negatif dönem sayısı. İlk
        # pozitif dönemde durmak şart: tüm negatifleri toplamak [-5, +3, -2]
        # serisine "2 dönem üst üste küçüldü" dedirtir, oysa seri 1.
        streak = 0
        for step in reversed(revenue_history):
            if step["real"] < 0:
                streak += 1
            else:
                break
        out["real_revenue_negative_streak"] = streak

    # Tazelik: tarayıcıda filtrelenebilir olması ve Y7 taban oranının
    # hesaplanabilmesi için bağlam kaydında tutuluyor.
    tazelik = analysis.get("freshness") or {}
    out["data_age_months"] = tazelik.get("age_months")
    out["last_period"] = tazelik.get("latest_period")
    out["data_fresh"] = (
        None if not tazelik.get("level") or tazelik["level"] == "bilinmiyor"
        else tazelik["level"] == "taze"
    )

    out["altman_zone"] = (analysis.get("altman") or {}).get("zone")
    out["equity_negative"] = (
        (analysis.get("debt") or {}).get("equity_negative") or {}
    ).get("value")
    return out


def trend(values: list[float]) -> dict:
    """En küçük kareler eğimi + yön sınıflaması.

    Yön, eğimin ortalama büyüklüğe oranına bakılarak belirlenir; böylece
    yüzde cinsinden marjla kat cinsinden borç oranı aynı ölçekte
    sınıflandırılabilir. Üç noktadan az veri varsa trend üretilmez.
    """
    values = [value for value in values if value is not None]
    if len(values) < 3:
        return {"slope": None, "direction": None, "n": len(values)}

    slope = H._slope(values)
    scale = sum(abs(value) for value in values) / len(values)
    relative = slope / scale if scale else 0.0

    if relative > TREND_ESIGI:
        direction = "artış"
    elif relative < -TREND_ESIGI:
        direction = "düşüş"
    else:
        direction = "yatay"
    return {"slope": slope, "relative": relative, "direction": direction, "n": len(values)}


# =============================================================== evren tarama


def build_metric_context(client, market: str, limit: int | None = None,
                         progress=None, skip_errors: bool = True) -> dict:
    """Evreni tarar, her şirketin metriklerini ve sektör istatistiklerini yazar.

    Panelin ilk açılışındaki uzun adım budur: sembol başına profil + yıllık +
    çeyreklik tablo çekilir (~4 istek). 616 BIST hissesi ~4 istek/sn ile
    yaklaşık 10 dakika sürer. Sonuç 7 gün önbellekte tutulur; tarayıcı ve
    piyasa bakışı tamamen bu kayıttan çalışır.
    """
    entries = U.load(client, market)["entries"]
    if limit is not None:
        entries = entries[:limit]

    symbols: dict[str, dict] = {}
    errors: list[dict] = []

    for index, entry in enumerate(entries, start=1):
        symbol = entry["symbol"]
        try:
            profile = client.profile(symbol)
            pack = F.load(client, symbol, profile)
            cpi = INF.series_for_pack(client.cache, pack)
            analysis = H.analyze(client, symbol, pack, cpi)
        except YahooError as error:
            errors.append({"symbol": symbol, "error": str(error)[:160]})
            if not skip_errors:
                raise
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            errors.append({"symbol": symbol, "error": f"{type(error).__name__}: {error}"[:160]})
            if not skip_errors:
                raise
        else:
            extracted = extract_metrics(analysis, profile)
            symbols[symbol] = {
                "sector": analysis.get("sector") or entry.get("sector"),
                "industry": analysis.get("industry") or entry.get("industry"),
                "name": analysis.get("name") or entry.get("name"),
                "currency": analysis.get("currency"),
                "bank_accounting": analysis.get("bank_accounting", False),
                "market_cap": entry.get("market_cap"),
                "metrics": extracted["values"],
                "not_applicable": extracted["not_applicable"],
                "trends": extract_trends(analysis),
                "screen": extract_screen_fields(analysis),
            }

        if progress:
            progress(index, len(entries), symbol)

    record = {
        "market": market,
        "built_at": time.time(),
        "count": len(symbols),
        "attempted": len(entries),
        "errors": errors,
        "symbols": symbols,
        "sector_stats": _sector_stats(symbols),
        "universe_stats": _universe_stats(symbols),
    }
    client.cache.set_record("context", market, record)
    return record


def load_context(client, market: str, ttl: float | None = TTL_BAGLAM) -> dict | None:
    return client.cache.get_record("context", market, ttl=ttl)


def context_age_hours(client, market: str):
    age = client.cache.record_age("context", market)
    return None if age is None else age / 3600.0


# ============================================================== istatistikler


def _collect(symbols: dict, metric: str, sector: str | None = None) -> list[float]:
    """Bir metrik için geçerli değerleri toplar.

    `not_applicable` olan şirketler tamamen atlanır — bankaları F-Skoru
    medyanına 0 diye sokmak medyanı aşağı çeker ve sektör karşılaştırmasını
    bozar.
    """
    out = []
    for row in symbols.values():
        if sector is not None and row.get("sector") != sector:
            continue
        if metric in (row.get("not_applicable") or ()):
            continue
        value = (row.get("metrics") or {}).get(metric)
        if value is None:
            continue
        out.append(float(value))
    return out


def _stats(values: list[float]) -> dict:
    if len(values) < MIN_ORNEKLEM:
        return {"median": None, "n": len(values), "sufficient": False}
    ordered = sorted(values)
    return {
        "median": statistics.median(ordered),
        "n": len(ordered),
        "sufficient": True,
        "p25": ordered[len(ordered) // 4],
        "p75": ordered[(3 * len(ordered)) // 4],
        "min": ordered[0],
        "max": ordered[-1],
        "values": ordered,
    }


def _sector_stats(symbols: dict) -> dict:
    sectors = {row.get("sector") for row in symbols.values() if row.get("sector")}
    out = {}
    for sector in sorted(sectors):
        out[sector] = {
            metric: _stats(_collect(symbols, metric, sector))
            for metric, _ in METRIKLER
        }
    return out


def _universe_stats(symbols: dict) -> dict:
    return {metric: _stats(_collect(symbols, metric)) for metric, _ in METRIKLER}


def percentile(ordered: list[float], value: float) -> float:
    """Değerin sıralı listedeki yüzdelik konumu (0–100)."""
    if not ordered:
        return None
    position = bisect.bisect_right(ordered, value)
    return position / len(ordered) * 100.0


# ================================================================== sorgulama


def get_metric_context(context: dict, symbol: str, metric: str) -> dict:
    """Tek metrik için bağlam paketi."""
    row = (context.get("symbols") or {}).get(symbol)
    if not row:
        return {"available": False, "reason": "Şirket bağlam taramasında yok"}

    if metric in (row.get("not_applicable") or ()):
        return {
            "available": False,
            "reason": "Bu metrik şirketin sektöründe tanımlı değil",
            "not_applicable": True,
            "label": METRIK_ADLARI.get(metric, metric),
        }

    value = (row.get("metrics") or {}).get(metric)
    sector = row.get("sector")
    sector_stat = ((context.get("sector_stats") or {}).get(sector) or {}).get(metric) or {}
    universe_stat = (context.get("universe_stats") or {}).get(metric) or {}

    out = {
        "available": value is not None,
        "label": METRIK_ADLARI.get(metric, metric),
        "value": value,
        "sector": sector,
        "sector_median": sector_stat.get("median"),
        "sector_n": sector_stat.get("n", 0),
        "sector_sufficient": sector_stat.get("sufficient", False),
        "universe_median": universe_stat.get("median"),
        "universe_n": universe_stat.get("n", 0),
        "trend": (row.get("trends") or {}).get(metric),
    }

    if value is not None:
        if sector_stat.get("sufficient"):
            out["sector_percentile"] = percentile(sector_stat.get("values") or [], value)
        if universe_stat.get("sufficient"):
            out["universe_percentile"] = percentile(universe_stat.get("values") or [], value)

    if not sector_stat.get("sufficient"):
        out["sector_note"] = (
            f"Sektör örneklemi yetersiz (n={sector_stat.get('n', 0)}, "
            f"en az {MIN_ORNEKLEM} gerekiyor)"
        )
    return out


def all_metric_contexts(context: dict, symbol: str) -> list[dict]:
    """Skor kartının kullandığı tam bağlam listesi (tanımlı sırada)."""
    return [
        {"metric": metric, **get_metric_context(context, symbol, metric)}
        for metric, _ in METRIKLER
    ]
