"""Çeyreklik ve yıllık rapor okuyucu.

Son dönemi iki referansla karşılaştırır:

    YoY : geçen yılın aynı dönemi  — mevsimsellikten arınmış asıl karşılaştırma
    QoQ : bir önceki çeyrek        — hızlanma/yavaşlama göstergesi

Karşılaştırmanın üstüne, rakamlardan türetilen kural tabanlı yorum cümleleri
eklenir. Her cümlenin `rule_id`si ve hangi kalemden geldiğini gösteren
`sources` listesi vardır; ekranda cümlenin altında bu kaynak yazar.

Cümleler yalnızca rakamın ne gösterdiğini söyler. "Ucuz", "pahalı", "iyi",
"kötü", "alınabilir" gibi ifadeler bu modülde tanımlı değildir.
"""

from __future__ import annotations

from . import bicim as B
from . import fundamentals as F
from . import health as H
from . import inflation as INF

# YoY eşleşmesinde takvim kaymalarına izin verilen aralık (gün).
YIL_ALT, YIL_UST = 300, 430

# Marj değişimini "kayda değer" saymak için gereken puan farkı.
MARJ_ESIGI_PUAN = 2.0


def analyze_reports(client, symbol: str, pack: dict | None = None, cpi: dict | None = None) -> dict:
    """Çeyreklik ve yıllık rapor karşılaştırmaları + yorumlar."""
    if pack is None:
        pack = F.load(client, symbol)
    if cpi is None:
        cpi = INF.series_for_pack(client.cache, pack)

    bank = pack.get("bank_accounting", False)
    quarterly = _compare(pack, cpi, "quarterly", bank)
    annual = _compare(pack, cpi, "annual", bank)

    return {
        "symbol": symbol,
        "currency": pack.get("currency"),
        "bank_accounting": bank,
        "quarterly": quarterly,
        "annual": annual,
    }


# ------------------------------------------------------------- karşılaştırma


def _compare(pack: dict, cpi: dict, period: str, bank: bool) -> dict:
    rows = F.rows(pack, period)
    if not rows:
        return {"available": False, "reason": "Dönem verisi yok", "lines": [], "comments": []}

    current = rows[-1]
    previous = rows[-2] if len(rows) >= 2 else None
    year_ago = _find_year_ago(rows, current["date"]) if period == "quarterly" else previous

    lines = []
    for key, label in _KALEMLER:
        if bank and key in _BANKA_DISI:
            continue
        value = current["values"].get(key)
        if value is None:
            continue
        lines.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "yoy": _change(value, (year_ago or {}).get("values", {}).get(key)),
                "qoq": _change(value, (previous or {}).get("values", {}).get(key)),
            }
        )

    margins = _margins(current["values"], (year_ago or {}).get("values", {}), bank)

    real = None
    if year_ago:
        change = _change(
            current["values"].get("TotalRevenue"),
            year_ago["values"].get("TotalRevenue"),
        )
        # _change() sözlük döndürür; deflate'e oranın kendisi gider.
        if change and change.get("pct") is not None:
            real = INF.real_growth(cpi, change["pct"], year_ago["date"], current["date"])

    comments = _comments(current, year_ago, previous, margins, real, bank, period)

    return {
        "available": True,
        "period": period,
        "current_date": current["date"],
        "compare_date": (year_ago or {}).get("date"),
        "previous_date": (previous or {}).get("date"),
        "lines": lines,
        "margins": margins,
        "real_revenue": real,
        "comments": comments,
    }


_KALEMLER = (
    ("TotalRevenue", "Gelir"),
    ("GrossProfit", "Brüt kâr"),
    ("OperatingIncome", "Faaliyet kârı"),
    ("EBITDA", "FAVÖK"),
    ("NetIncome", "Net kâr"),
    ("OperatingCashFlow", "Faaliyet nakit akışı"),
    ("FreeCashFlow", "Serbest nakit akışı"),
    ("TotalDebt", "Toplam borç"),
    ("NetDebt", "Net borç"),
    ("StockholdersEquity", "Özsermaye"),
)

# Bankalarda anlamsız olan kalemler rapordan tamamen çıkarılır.
_BANKA_DISI = {"GrossProfit", "EBITDA", "FreeCashFlow", "NetDebt"}


def _find_year_ago(rows: list[dict], date: str) -> dict | None:
    """Geçen yılın aynı çeyreğini bulur (takvim kaymasına toleranslı)."""
    from datetime import date as date_cls

    try:
        target = date_cls.fromisoformat(date)
    except (TypeError, ValueError):
        return None

    for row in reversed(rows[:-1]):
        try:
            other = date_cls.fromisoformat(row["date"])
        except (TypeError, ValueError):
            continue
        gap = (target - other).days
        if YIL_ALT <= gap <= YIL_UST:
            return row
    return None


def _change(now, before) -> dict | None:
    if now is None or before is None:
        return None
    out = {"from": before, "to": now, "delta": now - before}
    out["pct"] = (now / before - 1.0) if before and before > 0 else None
    if before < 0 < now:
        out["note"] = "Zarardan kâra geçiş"
    elif now < 0 < before:
        out["note"] = "Kârdan zarara geçiş"
    return out


def _margins(current: dict, compare: dict, bank: bool) -> dict:
    out = {}
    revenue_now = current.get("TotalRevenue")
    revenue_before = compare.get("TotalRevenue")
    pairs = (("gross", "GrossProfit", "Brüt marj"),
             ("operating", "OperatingIncome", "Faaliyet marjı"),
             ("net", "NetIncome", "Net marj"))
    for key, field, label in pairs:
        if bank and key == "gross":
            continue
        now = _pct(current.get(field), revenue_now)
        before = _pct(compare.get(field), revenue_before)
        if now is None:
            continue
        out[key] = {
            "label": label,
            "now": now,
            "before": before,
            "delta": (now - before) if before is not None else None,
        }
    return out


def _pct(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return numerator / denominator * 100


# ------------------------------------------------------------------ yorumlar


def _comments(current, year_ago, previous, margins, real, bank, period) -> list[dict]:
    """Kural tabanlı yorum cümleleri. Her biri rakamdan türer, yargı içermez."""
    out: list[dict] = []
    values = current["values"]
    date = current["date"]
    donem = "çeyrek" if period == "quarterly" else "yıl"

    if year_ago is None:
        out.append(
            _comment(
                "REP_KARSILASTIRMA_YOK",
                f"Geçen yılın aynı dönemi tabloda yok; bu {donem} yalnızca "
                "kendi başına gösteriliyor.",
                [],
            )
        )
        return out

    before = year_ago["values"]
    ref = year_ago["date"]

    # --- gelir: nominal + reel
    revenue_change = _change(values.get("TotalRevenue"), before.get("TotalRevenue"))
    if revenue_change and revenue_change.get("pct") is not None:
        nominal = revenue_change["pct"]
        if real and real.get("real") is not None:
            out.append(
                _comment(
                    "REP_GELIR_REEL",
                    f"Gelir yıllık {_yuzde(nominal)} değişti; dönem enflasyonu "
                    f"{_yuzde(real['cpi_growth'])} olduğu için **reel {_yuzde(real['real'])}** "
                    f"{'büyüme' if real['real'] > 0 else 'küçülme'} anlamına geliyor.",
                    [_src("TotalRevenue", date, values.get("TotalRevenue")),
                     _src("TotalRevenue", ref, before.get("TotalRevenue")),
                     _src(real.get("label") or "TÜFE", f"{ref[:7]}..{date[:7]}",
                          real.get("cpi_growth"))],
                    basis=real.get("basis"),
                )
            )
        else:
            out.append(
                _comment(
                    "REP_GELIR_NOMINAL",
                    f"Gelir yıllık {_yuzde(nominal)} değişti. Bu dönem için TÜFE "
                    "verisi bulunmadığından reel karşılığı hesaplanamadı.",
                    [_src("TotalRevenue", date, values.get("TotalRevenue")),
                     _src("TotalRevenue", ref, before.get("TotalRevenue"))],
                )
            )

    # --- marj: gelir artarken kâr düşüyor mu?
    operating = margins.get("operating")
    if operating and operating.get("delta") is not None:
        delta = operating["delta"]
        income_change = _change(values.get("OperatingIncome"), before.get("OperatingIncome"))
        if delta <= -MARJ_ESIGI_PUAN:
            detail = ""
            if revenue_change and income_change and revenue_change.get("pct") is not None \
                    and income_change.get("pct") is not None \
                    and revenue_change["pct"] > 0 > income_change["pct"]:
                detail = (
                    f" Gelir {_yuzde(revenue_change['pct'])} artarken faaliyet kârı "
                    f"{_yuzde(income_change['pct'])} değişti: maliyet artışı geliri yutmuş."
                )
            out.append(
                _comment(
                    "REP_MARJ_DARALMASI",
                    f"Faaliyet marjı {B.puan(operating['before'])}'den "
                    f"{B.puan(operating['now'])}'e "
                    f"indi ({B.sayi(delta, 1, isaretli=True)} puan)." + detail,
                    [_src("OperatingIncome", date, values.get("OperatingIncome")),
                     _src("TotalRevenue", date, values.get("TotalRevenue"))],
                )
            )
        elif delta >= MARJ_ESIGI_PUAN:
            out.append(
                _comment(
                    "REP_MARJ_GENISLEME",
                    f"Faaliyet marjı {B.puan(operating['before'])}'den "
                    f"{B.puan(operating['now'])}'e "
                    f"çıktı ({B.sayi(delta, 1, isaretli=True)} puan).",
                    [_src("OperatingIncome", date, values.get("OperatingIncome")),
                     _src("TotalRevenue", date, values.get("TotalRevenue"))],
                )
            )

    # --- kâr nakde dönüyor mu?
    net_income = values.get("NetIncome")
    fcf = values.get("FreeCashFlow")
    if not bank and net_income is not None and fcf is not None:
        if net_income > 0 and fcf < 0:
            out.append(
                _comment(
                    "REP_KAR_NAKDE_DONMUYOR",
                    f"Dönem {_para(net_income)} net kârla kapandı ama serbest nakit akışı "
                    f"{_para(fcf)} — kâr nakde dönüşmemiş. Alacak veya stok artışı, ya da "
                    "yüksek yatırım harcaması bu farkı yaratabilir.",
                    [_src("NetIncome", date, net_income), _src("FreeCashFlow", date, fcf)],
                )
            )
        elif net_income > 0 and fcf > net_income:
            out.append(
                _comment(
                    "REP_NAKIT_KARDAN_BUYUK",
                    f"Serbest nakit akışı ({_para(fcf)}) net kârdan ({_para(net_income)}) "
                    "büyük; dönem kârı nakit tarafında da karşılanmış.",
                    [_src("NetIncome", date, net_income), _src("FreeCashFlow", date, fcf)],
                )
            )

    # --- zarar
    if net_income is not None and net_income < 0:
        out.append(
            _comment(
                "REP_ZARAR",
                f"Dönem {_para(abs(net_income))} zararla kapandı.",
                [_src("NetIncome", date, net_income)],
            )
        )

    # --- borç
    debt_now = values.get("NetDebt") if not bank else values.get("TotalDebt")
    debt_before = before.get("NetDebt") if not bank else before.get("TotalDebt")
    ebitda_now = values.get("EBITDA")
    ebitda_before = before.get("EBITDA")
    # Net borç/FAVÖK yalnızca yıllık karşılaştırmada hesaplanır: tek çeyreğin
    # FAVÖK'ünü yıl sonu borcuna bölmek oranı yaklaşık dört kat şişirir
    # (SISE'de çeyreklik 8,24 çıkarken yıllık taban 2,20 diyordu).
    if period == "annual" and not bank and debt_now is not None and ebitda_now \
            and ebitda_now > 0 and debt_before is not None and ebitda_before \
            and ebitda_before > 0 \
            and H.net_debt_ebitda_guvenilir(debt_now, ebitda_now) \
            and H.net_debt_ebitda_guvenilir(debt_before, ebitda_before):
        # Her iki dönemin de FAVÖK'ü güvenilir aralıkta olmalı — ISSEN.IS
        # vakası: bir dönem FAVÖK neredeyse sıfıra çökünce oran binlerce
        # çıkıyor, bu gerçek bir borç değişimi değil paydanın çökmesi.
        ratio_now = debt_now / ebitda_now
        ratio_before = debt_before / ebitda_before
        if abs(ratio_now - ratio_before) >= 0.5:
            out.append(
                _comment(
                    "REP_BORC_ORANI",
                    f"Net borç/FAVÖK {B.oran(ratio_before)}'den {B.oran(ratio_now)}'e "
                    f"{'yükseldi' if ratio_now > ratio_before else 'geriledi'}.",
                    [_src("NetDebt", date, debt_now), _src("EBITDA", date, ebitda_now)],
                )
            )
    elif debt_now is not None and debt_before:
        change = _change(debt_now, debt_before)
        if change and change.get("pct") is not None and abs(change["pct"]) >= 0.15:
            out.append(
                _comment(
                    "REP_BORC_TUTAR",
                    f"Toplam borç yıllık {_yuzde(change['pct'])} değişti.",
                    [_src("TotalDebt", date, debt_now), _src("TotalDebt", ref, debt_before)],
                )
            )

    # --- QoQ hızlanma/yavaşlama
    if previous is not None and period == "quarterly":
        qoq = _change(values.get("TotalRevenue"), previous["values"].get("TotalRevenue"))
        if qoq and qoq.get("pct") is not None and abs(qoq["pct"]) >= 0.10:
            out.append(
                _comment(
                    "REP_CEYREKLIK_HAREKET",
                    f"Bir önceki çeyreğe göre gelir {_yuzde(qoq['pct'])} değişti "
                    f"({previous['date']} → {date}). Çeyreklik karşılaştırma mevsimsellik "
                    "içerir, yıllık karşılaştırmayla birlikte okunmalı.",
                    [_src("TotalRevenue", date, values.get("TotalRevenue")),
                     _src("TotalRevenue", previous["date"],
                          previous["values"].get("TotalRevenue"))],
                )
            )

    return out


def _comment(rule_id: str, text: str, sources: list, **extra) -> dict:
    out = {"rule_id": rule_id, "text": text, "sources": sources}
    out.update(extra)
    return out


def _src(item: str, period, value=None) -> dict:
    return {"item": item, "period": period, "value": value}


def _yuzde(value) -> str:
    if value is None:
        return "—"
    # Sıfıra çok yakın değerler "%-0,0" gibi kendi kendisiyle çelişen bir
    # görünüm veriyor; yuvarlanınca sıfırsa işaretsiz sıfır yazılır.
    puan = value * 100
    if abs(puan) < 0.05:
        return "%0,0"
    return f"%{F.tr_sayi(puan, 1, isaretli=True)}"


def _para(value) -> str:
    if value is None:
        return "—"
    for limit, suffix in ((1e12, " trilyon"), (1e9, " milyar"), (1e6, " milyon")):
        if abs(value) >= limit:
            return f"{F.tr_sayi(value / limit, 2)}{suffix}"
    return F.tr_sayi(value, 0)
