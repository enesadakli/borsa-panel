"""Şirket özet narratifi.

`health.py` ve `reports.py` çıktılarından 4–6 cümlelik kural tabanlı bir özet
üretir. Her cümlenin bir `rule_id`si ve hangi kalemden/dönemden geldiğini
gösteren `sources` listesi vardır; ekranda cümlenin altında bu kaynak durur.

Cümleler yalnızca rakamın ne gösterdiğini söyler. Bu modülde "ucuz", "pahalı",
"iyi", "kötü", "cazip", "alınabilir" gibi kelimeler geçmez; şablon havuzunda
tanımlı bile değildir.

Sıra, en çok bilgi taşıyandan başlar: reel büyüme → marj → kâr kalitesi →
borç → F-Skoru → veri kalitesi notu.
"""

from __future__ import annotations

from . import bicim as B
from . import fundamentals as F
from . import health as H

MAKS_CUMLE = 6


def generate_company_summary(symbol: str, health_data: dict, reports_data: dict,
                             inflation_data: dict, pack: dict | None = None) -> dict:
    """Şirket için kural tabanlı özet."""
    bank = health_data.get("bank_accounting", False)
    currency = health_data.get("currency")
    equity_negative = bool(
        (health_data["debt"].get("equity_negative") or {}).get("value")
    )
    currency_uncertain = _currency_uncertain(health_data, pack)

    builders = [
        _nar_reel_buyume,
        _nar_kar_reel,
        _nar_negatif_ozsermaye,
        _nar_marj_trend,
        _nar_kar_kalitesi,
        _nar_borc,
        _nar_banka_kapsam,
        _nar_fskor,
        _nar_veri_notu,
    ]

    context = {
        "symbol": symbol,
        "health": health_data,
        "reports": reports_data,
        "inflation": inflation_data,
        "pack": pack,
        "bank": bank,
        "currency": currency,
        "equity_negative": equity_negative,
        "currency_uncertain": currency_uncertain,
    }

    sentences = []
    for builder in builders:
        sentence = builder(context)
        if sentence:
            sentences.append(sentence)

    # Negatif özsermaye cümlesi zorunlu; sığmıyorsa başka bir cümle düşer.
    mandatory = [s for s in sentences if s["rule_id"] == "NAR_NEGATIF_OZSERMAYE"]
    others = [s for s in sentences if s["rule_id"] != "NAR_NEGATIF_OZSERMAYE"]
    chosen = (mandatory + others)[:MAKS_CUMLE]
    for order, sentence in enumerate(chosen, start=1):
        sentence["order"] = order

    return {
        "symbol": symbol,
        "name": health_data.get("name"),
        "currency": currency,
        "as_of": _as_of(health_data),
        "sentences": chosen,
        "data_quality": {
            "missing_items": (pack or {}).get("missing", []),
            "currency_verified": not currency_uncertain,
            "tms29_boundary_crossed": _tms29_crossed(pack),
            "cpi_available": (inflation_data or {}).get("available", False),
        },
    }


# ------------------------------------------------------------------ cümleler


def _sentence(rule_id: str, text: str, sources=None) -> dict:
    return {"rule_id": rule_id, "text": text, "sources": sources or []}


def _nar_reel_buyume(ctx: dict):
    growth = (ctx["health"]["real_growth"] or {}).get("revenue") or {}
    nominal = growth.get("nominal")
    if nominal is None:
        return None

    if growth.get("real") is None:
        return _sentence(
            "NAR_REEL_BUYUME",
            f"Gelir son dönemde nominal olarak {_yuzde(nominal)} değişti; "
            "bu dönem için TÜFE verisi bulunmadığından reel karşılığı hesaplanamadı.",
            growth.get("sources"),
        )

    real = growth["real"]
    yon = "büyüdü" if real > 0 else "küçüldü"
    return _sentence(
        "NAR_REEL_BUYUME",
        f"Gelir nominal {_yuzde(nominal)} değişti; dönem enflasyonu "
        f"{_yuzde(growth.get('cpi_growth'))} olduğu için reel olarak "
        f"{_buyukluk(real)} {yon}. ({growth.get('label')}, {growth.get('basis')})",
        growth.get("sources"),
    )


def _nar_kar_reel(ctx: dict):
    growth = (ctx["health"]["real_growth"] or {}).get("net_income") or {}
    if growth.get("real") is None:
        return None
    real = growth["real"]
    nominal = growth.get("nominal")
    return _sentence(
        "NAR_KAR_REEL",
        f"Net kâr nominal {_yuzde(nominal)} değişirken reel olarak "
        f"{_yuzde(real)} oldu.",
        growth.get("sources"),
    )


def _nar_negatif_ozsermaye(ctx: dict):
    if not ctx["equity_negative"]:
        return None
    pack = ctx["pack"]
    equity = F.stock_value(pack, "StockholdersEquity") if pack else {"value": None, "end": None}
    return _sentence(
        "NAR_NEGATIF_OZSERMAYE",
        f"Özsermaye {equity['end']} itibarıyla negatif. Bu durumda borç/özsermaye, "
        "PD/DD ve ROE gibi oranlar tanımsız olduğu için bu özette kullanılmadı.",
        [{"item": "StockholdersEquity", "period": equity["end"], "value": equity["value"]}],
    )


def _nar_marj_trend(ctx: dict):
    if ctx["bank"]:
        return None
    trend = ctx["health"]["margins"].get("operating_trend") or {}
    if trend.get("status") != H.OK or trend.get("value") is None:
        return None
    series = ctx["health"]["margins"]["series"].get("operating") or []
    if len(series) < 3:
        return None
    yon = trend.get("direction")
    return _sentence(
        "NAR_MARJ_TREND",
        f"Faaliyet marjı {series[0][0][:4]}–{series[-1][0][:4]} arasında "
        f"{B.puan(series[0][1])}'den {B.puan(series[-1][1])}'e geldi; "
        f"yılda ortalama {B.sayi(trend['value'], 1, isaretli=True)} puan, yani {yon}.",
        trend.get("sources"),
    )


def _nar_kar_kalitesi(ctx: dict):
    gap = ctx["health"]["profit_quality"].get("fcf_gap") or {}
    if gap.get("status") != H.OK or gap.get("value") is None:
        return None
    share = gap["value"]
    ni = gap.get("net_income")
    fcf = gap.get("free_cash_flow")

    if ni is not None and fcf is not None and ni > 0 > fcf:
        text = (
            f"Son yıl net kâr pozitif ama serbest nakit akışı negatif: kâr nakde "
            "dönüşmemiş. Alacak/stok artışı veya yüksek yatırım harcaması bu farkı yaratır."
        )
    elif share > 0.5:
        text = (
            f"Net kârın yaklaşık {B.puan(share * 100, 0)} kadarı serbest nakde dönüşmemiş; "
            "kârın önemli bir kısmı kasaya girmemiş görünüyor."
        )
    elif share < 0:
        text = (
            f"Serbest nakit akışı net kârın {B.puan(-share * 100, 0)} üzerinde; "
            "dönem kârı nakit tarafında da karşılanmış."
        )
    else:
        text = (
            f"Net kârın {B.puan(share * 100, 0)} kadarı serbest nakde dönüşmemiş — "
            "kâr ile nakit akışı büyük ölçüde örtüşüyor."
        )
    return _sentence("NAR_KAR_KALITESI", text, gap.get("sources"))


def _nar_borc(ctx: dict):
    if ctx["bank"] or ctx["equity_negative"]:
        return None
    debt = ctx["health"]["debt"]
    ratio = debt.get("net_debt_ebitda") or {}
    history = [
        row for row in debt.get("history", [])
        if row.get("net_debt_ebitda") is not None
    ]

    if len(history) >= 2:
        # Karşılaştırmanın iki ucu da yıllık tablodan: en son değeri TTM
        # FAVÖK'le hesaplayıp geçmişi yıllık FAVÖK'le hesaplamak farklı
        # tabanları yan yana koyar ve olmayan bir sıçrama gösterirdi.
        first, last = history[0], history[-1]
        text = (
            f"Net borç/FAVÖK {first['date'][:4]} yılında "
            f"{B.oran(first['net_debt_ebitda'])} iken {last['date'][:4]} yılında "
            f"{B.oran(last['net_debt_ebitda'])}."
        )
        if ratio.get("status") == H.OK and ratio.get("value") is not None:
            text += f" Son 12 ay üzerinden ise {B.oran(ratio['value'])}."
        return _sentence(
            "NAR_BORC",
            text,
            [{"item": "NetDebt/EBITDA", "period": last["date"],
              "value": last["net_debt_ebitda"]},
             {"item": "NetDebt/EBITDA", "period": first["date"],
              "value": first["net_debt_ebitda"]}],
        )

    leverage = debt.get("debt_to_equity") or {}
    if leverage.get("status") == H.OK and leverage.get("value") is not None:
        return _sentence(
            "NAR_BORC",
            f"FAVÖK verisi olmadığı için borç yükü özsermayeye göre ölçüldü: "
            f"borç/özsermaye {B.oran(leverage['value'])}.",
            leverage.get("sources"),
        )
    return None


def _nar_banka_kapsam(ctx: dict):
    if not ctx["bank"]:
        return None
    return _sentence(
        "NAR_BANKA_KAPSAM",
        "Bu bir banka/finans şirketi: brüt marj, FAVÖK, net borç ve cari oran "
        "bu sektörde açıklanmaz veya tanımsızdır, o yüzden bu özette "
        "kullanılmadı. Piotroski F-Skoru da finans dışı şirketler için "
        "tanımlıdır; skor bu sebeple diğer şirketlerle kıyaslanmamalı.",
        [],
    )


def _nar_fskor(ctx: dict):
    fscore = ctx["health"]["fscore"]
    points = fscore.get("usable_points") or []
    if len(points) < 2:
        return None

    first, last = _karsilastirilabilir_ikili(points)
    if first is None:
        return None
    broken, fixed = [], []
    before = {c["id"]: c for c in first["criteria"]}
    for criterion in last["criteria"]:
        old = before.get(criterion["id"])
        if not old or old["status"] != H.OK or criterion["status"] != H.OK:
            continue
        if old["passed"] and not criterion["passed"]:
            broken.append(criterion["label"])
        elif not old["passed"] and criterion["passed"]:
            fixed.append(criterion["label"])

    parts = [
        f"F-Skoru {first['date'][:4]} yılında {first['score']}/9 iken "
        f"{last['date'][:4]} yılında {last['score']}/9."
    ]
    if broken:
        parts.append("Bozulan: " + ", ".join(broken) + ".")
    if fixed:
        parts.append("İyileşen: " + ", ".join(fixed) + ".")

    kapsam_farki = last["evaluated"] - first["evaluated"]
    if kapsam_farki > 0:
        # Karşılaştırılabilir ikili bulunamadığında (ör. yalnızca iki nokta var
        # ve kapsamları farklı) skorun bir kısmı ölçüm genişlemesinden gelir.
        parts.append(
            f"Skorun {kapsam_farki} puanı şirketteki bir iyileşmeden değil, ölçüm "
            f"kapsamının genişlemesinden geliyor: {first['date'][:4]} yılında veri "
            "yetersizliğinden değerlendirilemeyen kriterler sonraki dönemde ölçülebildi."
        )
    elif not broken and not fixed:
        if first["score"] == last["score"]:
            parts.append("Kriterlerin geçme/kalma durumu değişmedi.")
        else:
            # "evaluated" sayısı eşit olsa bile HANGİ kriterlerin ölçüldüğü
            # dönemden döneme değişmiş olabilir (biri EKSİK'ten OK'a geçerken
            # başka biri tersine geçmiş olabilir) — bu durumda kriter kriter
            # eşleşme bulunamaz ama skor yine de değişir. "Değişmedi" demek
            # burada tam da bu planın ortaya çıkışına sebep olan çelişki
            # sınıfını üretirdi: sayı değişti, cümle "değişmedi" derdi.
            parts.append(
                "Hangi kriter(ler)in bu değişikliğe yol açtığı kalem bazında "
                "ayırt edilemedi."
            )

    return _sentence(
        "NAR_FSKOR",
        " ".join(parts),
        [{"item": "F-Skoru", "period": last["date"], "value": last["label"]}],
    )


def _karsilastirilabilir_ikili(points: list[dict]) -> tuple[dict | None, dict]:
    """Karşılaştırılabilir en geniş aralığı seçer.

    F-Skorunun en eski noktası yapısal olarak iki kriteri ölçemez: "ROA artıyor"
    ve "varlık devir hızı artıyor" iki yıl öncesinin bilançosunu ister, o veri
    ilk noktada yoktur. Dolayısıyla ilk ve son noktayı körlemesine kıyaslamak
    **her şirkette** "skorun 2 puanı ölçüm genişlemesinden" notunu doğurur ve
    not gürültüye dönüşür.

    Bu yüzden önce son noktayla **aynı sayıda kriteri ölçülmüş** en eski nokta
    aranır; bulunursa karşılaştırma elma-elmadır. Bulunamazsa (ör. yalnızca iki
    nokta var ve kapsamları farklı) ilk noktaya düşülür ve çağıran taraf
    kapsam farkını açıkça yazar.
    """
    last = points[-1]
    esit = [p for p in points[:-1] if p["evaluated"] == last["evaluated"]]
    if esit:
        return esit[0], last
    return points[0], last


def _nar_veri_notu(ctx: dict):
    notlar = []
    pack = ctx["pack"] or {}

    if ctx["currency_uncertain"]:
        notlar.append("mali tabloların para birimi kesin doğrulanamadı")

    missing = pack.get("missing") or []
    if missing:
        gosterilen = ", ".join(missing[:4])
        if len(missing) > 4:
            gosterilen += f" ve {len(missing) - 4} kalem daha"
        notlar.append(f"şu kalemler Yahoo'dan gelmedi: {gosterilen}")

    if not (ctx["inflation"] or {}).get("available"):
        notlar.append("TÜFE serisi bu para birimi için kullanılamıyor, reel rakam yok")

    fscore_latest = ctx["health"]["fscore"].get("latest") or {}
    if fscore_latest.get("missing"):
        notlar.append(
            f"F-Skorunda {len(fscore_latest['missing'])} kriter veri eksikliğinden "
            "değerlendirilemedi (sıfır sayılmadı)"
        )

    if not notlar:
        return None
    return _sentence(
        "NAR_VERI_NOTU",
        "Veri notu: " + "; ".join(notlar) + ".",
        [],
    )


# ------------------------------------------------------------------ yardımcı


def _currency_uncertain(health_data: dict, pack: dict | None) -> bool:
    if not health_data.get("currency"):
        return True
    notes = (pack or {}).get("currency_notes") or health_data.get("currency_notes") or []
    return any("gerçekten karışık" in note for note in notes)


def _tms29_crossed(pack: dict | None) -> bool:
    if not pack or (pack.get("currency") or "").upper() != "TRY":
        return False
    dates = F.period_dates(pack, "annual")
    return bool([d for d in dates if d < "2023-01-01"] and [d for d in dates if d >= "2023-01-01"])


def _as_of(health_data: dict):
    periods = health_data.get("periods") or []
    return periods[-1] if periods else None


def _yuzde(value) -> str:
    """İşaretli yüzde: değişimin yönü rakamda görünsün."""
    if value is None:
        return "—"
    return f"%{F.tr_sayi(_sifirla(value * 100), 1, isaretli=True)}"


def _buyukluk(value) -> str:
    """İşaretsiz yüzde — yön cümlenin fiilinde ("küçüldü") söylendiğinde.

    İşareti hem rakama hem fiile koymak "%+31,5 küçüldü" gibi kendi kendisiyle
    çelişen bir ifade üretiyordu.
    """
    if value is None:
        return "—"
    return f"%{F.tr_sayi(abs(_sifirla(value * 100)), 1)}"


def _sifirla(value: float) -> float:
    """-0.0'ı 0.0 yapar; "%-0,0" gibi çıktılar oluşmasın."""
    return 0.0 if abs(value) < 0.05 else value
