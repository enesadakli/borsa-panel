"""Gerçek portföy defteri.

İşlemler `data/portfolio.json` içinde tutulur. Her işlem: tarih, sembol, adet,
fiyat, komisyon, alım/satım. Maliyet **ağırlıklı ortalama** yöntemiyle
hesaplanır (Türkiye'de aracı kurumların ve vergi uygulamasının varsayılanı
budur; FIFO değil).

**Kur getirisi ayrıştırması.** ABD hisselerinde toplam TL getirisi iki
kaynaktan gelir: hissenin kendi getirisi ve kurun hareketi. Dolar bazında
zarardayken TL bazında kârlı görünmek en yaygın yanılgıdır, o yüzden ikisi
ayrı ayrı gösterilir ve toplamlarının toplam getiriye eşit olduğu testle
korunur:

    (1 + hisse_getirisi) × (1 + kur_getirisi) = 1 + toplam_getiri

Komisyon maliyete eklenir (alımda) ve hasılattan düşülür (satışta); "getiri"
her yerde komisyon sonrası nettir.
"""

from __future__ import annotations

import json
import os
import time

from . import fundamentals as F
from . import universe as U
from .yahoo import YahooError

ALIM = "alim"
SATIM = "satim"


class PortfolioError(ValueError):
    """İşlem kaydı geçersiz."""


def portfolio_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "portfolio.json")


# ------------------------------------------------------------------- defter


def load_trades() -> list[dict]:
    try:
        with open(portfolio_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    trades = data.get("trades") if isinstance(data, dict) else data
    if not isinstance(trades, list):
        return []
    return sorted(
        (trade for trade in trades if isinstance(trade, dict)),
        key=lambda trade: (trade.get("date") or "", trade.get("symbol") or ""),
    )


def save_trades(trades: list[dict]) -> None:
    payload = {"updated_at": time.time(), "trades": trades}
    os.makedirs(os.path.dirname(portfolio_path()), exist_ok=True)
    tmp = portfolio_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, portfolio_path())


def add_trade(trade: dict) -> list[dict]:
    trades = load_trades()
    trades.append(validate_trade(trade))
    save_trades(trades)
    return trades


def remove_trade(index: int) -> list[dict]:
    trades = load_trades()
    if not 0 <= index < len(trades):
        raise PortfolioError(f"işlem sırası geçersiz: {index}")
    trades.pop(index)
    save_trades(trades)
    return trades


def validate_trade(trade: dict) -> dict:
    symbol = (trade.get("symbol") or "").strip().upper()
    if not symbol:
        raise PortfolioError("sembol boş olamaz")

    side = (trade.get("side") or ALIM).strip().lower()
    if side not in (ALIM, SATIM):
        raise PortfolioError(f"işlem türü '{ALIM}' veya '{SATIM}' olmalı")

    try:
        quantity = float(trade.get("quantity"))
        price = float(trade.get("price"))
    except (TypeError, ValueError) as error:
        raise PortfolioError("adet ve fiyat sayı olmalı") from error
    if quantity <= 0:
        raise PortfolioError("adet sıfırdan büyük olmalı")
    if price <= 0:
        raise PortfolioError("fiyat sıfırdan büyük olmalı")

    commission = float(trade.get("commission") or 0.0)
    if commission < 0:
        raise PortfolioError("komisyon negatif olamaz")

    date = (trade.get("date") or "").strip()
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise PortfolioError("tarih YYYY-AA-GG biçiminde olmalı")

    return {
        "date": date,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "commission": commission,
        "fx_rate": trade.get("fx_rate"),  # işlem anındaki kur (varsa)
        "note": (trade.get("note") or "").strip() or None,
    }


# ------------------------------------------------------------------ pozisyon


def build_positions(trades: list[dict]) -> dict:
    """İşlemleri pozisyonlara çevirir (ağırlıklı ortalama maliyet).

    Satışta ortalama maliyet **değişmez**; satılan adet maliyetiyle birlikte
    düşülür ve gerçekleşmiş kâr/zarar oradan çıkar. Elde kalan adetten fazla
    satış varsa uyarı üretilir (veri girişi hatası) ama hesap durmaz.
    """
    positions: dict[str, dict] = {}
    warnings: list[str] = []

    for trade in trades:
        symbol = trade["symbol"]
        position = positions.setdefault(
            symbol,
            {
                "symbol": symbol,
                "quantity": 0.0,
                "cost_total": 0.0,       # elde kalan adetin toplam maliyeti
                "avg_cost": 0.0,
                "realized": 0.0,         # komisyon sonrası gerçekleşmiş K/Z
                "commission_total": 0.0,
                "trades": 0,
                "first_date": trade["date"],
                "last_date": trade["date"],
                "fx_at_buy": [],         # (adet, kur) — kur etkisi için
            },
        )
        position["trades"] += 1
        position["last_date"] = trade["date"]
        position["commission_total"] += trade["commission"]

        if trade["side"] == ALIM:
            position["cost_total"] += trade["quantity"] * trade["price"] + trade["commission"]
            position["quantity"] += trade["quantity"]
            if trade.get("fx_rate"):
                position["fx_at_buy"].append((trade["quantity"], float(trade["fx_rate"])))
        else:
            if trade["quantity"] > position["quantity"] + 1e-9:
                warnings.append(
                    f"{symbol}: {trade['date']} tarihinde elde olandan fazla satış "
                    f"({trade['quantity']:g} > {position['quantity']:g}); "
                    "eksik alım kaydı olabilir"
                )
            satilan = min(trade["quantity"], position["quantity"])
            birim_maliyet = (
                position["cost_total"] / position["quantity"] if position["quantity"] else 0.0
            )
            maliyet = birim_maliyet * satilan
            hasilat = satilan * trade["price"] - trade["commission"]
            position["realized"] += hasilat - maliyet
            position["cost_total"] -= maliyet
            position["quantity"] -= satilan

        position["avg_cost"] = (
            position["cost_total"] / position["quantity"] if position["quantity"] > 1e-9 else 0.0
        )

    return {"positions": positions, "warnings": warnings}


def _weighted_fx(position: dict):
    """Alımların adet-ağırlıklı ortalama kuru; kayıt yoksa None."""
    kayitlar = position.get("fx_at_buy") or []
    toplam_adet = sum(adet for adet, _ in kayitlar)
    if not toplam_adet:
        return None
    return sum(adet * kur for adet, kur in kayitlar) / toplam_adet


# -------------------------------------------------------------------- özet


def summary(client, base_currency: str = "TRY", trades: list[dict] | None = None) -> dict:
    """Portföyün güncel durumu, tek para biriminde (varsayılan TL)."""
    if trades is None:
        trades = load_trades()

    built = build_positions(trades)
    warnings = list(built["warnings"])
    rows: list[dict] = []

    total_value = total_cost = total_realized = 0.0

    for symbol, position in sorted(built["positions"].items()):
        satir = {
            "symbol": symbol,
            "quantity": position["quantity"],
            "avg_cost": position["avg_cost"],
            "cost_total": position["cost_total"],
            "realized": position["realized"],
            "commission_total": position["commission_total"],
            "trades": position["trades"],
            "first_date": position["first_date"],
        }

        try:
            profile = client.profile(symbol)
        except YahooError as error:
            satir["error"] = f"fiyat alınamadı: {str(error)[:80]}"
            rows.append(satir)
            warnings.append(f"{symbol}: güncel fiyat alınamadı, değeri hesaba katılmadı")
            continue

        price = profile.get("last_price")
        price_currency = profile.get("price_currency") or base_currency
        satir["name"] = profile.get("name")
        satir["price"] = price
        satir["currency"] = price_currency
        satir["sector"] = profile.get("sector")
        satir["is_financial"] = U.uses_bank_accounting(
            profile.get("sector"), profile.get("industry")
        )

        rate = F.fx_rate(client, price_currency, base_currency) or 1.0
        satir["fx_rate"] = rate

        if price and position["quantity"] > 1e-9:
            value_local = price * position["quantity"]
            satir["value_local"] = value_local
            satir["value_base"] = value_local * rate
            satir["cost_base"] = position["cost_total"] * rate
            satir["unrealized"] = value_local - position["cost_total"]
            satir["unrealized_pct"] = (
                value_local / position["cost_total"] - 1.0
                if position["cost_total"] > 0
                else None
            )
            total_value += satir["value_base"]
            total_cost += satir["cost_base"]

            if price_currency != base_currency:
                satir["fx_split"] = _fx_split(position, price, rate)
        else:
            satir["value_local"] = 0.0
            satir["value_base"] = 0.0
            satir["unrealized"] = 0.0

        total_realized += position["realized"] * rate
        rows.append(satir)

    for satir in rows:
        satir["weight"] = (
            satir.get("value_base", 0.0) / total_value if total_value else 0.0
        )

    return {
        "base_currency": base_currency,
        "as_of": time.strftime("%Y-%m-%d %H:%M"),
        "positions": rows,
        "open_positions": sum(1 for satir in rows if satir["quantity"] > 1e-9),
        "total_value": total_value,
        "total_cost": total_cost,
        "total_unrealized": total_value - total_cost,
        "total_unrealized_pct": (total_value / total_cost - 1.0) if total_cost else None,
        "total_realized": total_realized,
        "trade_count": len(trades),
        "warnings": warnings,
        "empty": not trades,
    }


def _fx_split(position: dict, price: float, current_rate: float) -> dict:
    """Toplam TL getirisini hisse getirisi ve kur getirisine ayırır.

    Kimlik: (1 + hisse) × (1 + kur) = 1 + toplam. Çıkarma yerine çarpım
    kullanılıyor; yüksek kur hareketlerinde toplamayla ayrıştırma sapar.

    İşlem anındaki kur kaydedilmemişse ayrıştırma yapılamaz — uydurulmuş bir
    giriş kuru, yanlış bir "kur kazancı" üretirdi.
    """
    entry_rate = _weighted_fx(position)
    if not entry_rate or not position["quantity"] or position["cost_total"] <= 0:
        return {
            "available": False,
            "reason": (
                "İşlem anındaki kur kaydedilmediği için hisse getirisi ile kur "
                "getirisi ayrıştırılamadı. İşleme 'fx_rate' eklenirse hesaplanır."
            ),
        }

    unit_cost_local = position["cost_total"] / position["quantity"]
    share_return = price / unit_cost_local - 1.0
    fx_return = current_rate / entry_rate - 1.0
    total_return = (1.0 + share_return) * (1.0 + fx_return) - 1.0

    return {
        "available": True,
        "share_return": share_return,
        "fx_return": fx_return,
        "total_return": total_return,
        "entry_rate": entry_rate,
        "current_rate": current_rate,
        "note": (
            "Hisse getirisi kendi para biriminde, kur getirisi kurun hareketinden. "
            "Toplam getiri ikisinin bileşimidir."
        ),
    }


def real_return(summary_data: dict, cpi_series: dict, since: str | None = None) -> dict:
    """Portföyün enflasyon sonrası getirisi.

    Nominal getiri TL cinsindendir; TÜFE ile düzeltilince satın alma gücü
    cinsinden gerçek getiri çıkar.
    """
    from . import inflation as INF

    nominal = summary_data.get("total_unrealized_pct")
    if nominal is None:
        return {"available": False, "reason": "Maliyet verisi olmadan getiri hesaplanamaz"}

    start = since or min(
        (satir.get("first_date") for satir in summary_data["positions"] if satir.get("first_date")),
        default=None,
    )
    if not start:
        return {"available": False, "reason": "İlk alım tarihi bilinmiyor"}

    end = time.strftime("%Y-%m-%d")
    growth = INF.cpi_growth(cpi_series, start, end)
    real = INF.deflate(nominal, growth["value"])

    return {
        "available": real is not None,
        "nominal": nominal,
        "cpi_growth": growth["value"],
        "real": real,
        "basis": growth["basis"],
        "label": growth["label"],
        "start": start,
        "end": end,
        "reason": None if real is not None else "Dönemi kapsayan TÜFE verisi yok",
    }
