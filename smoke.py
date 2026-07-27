"""Veri katmanı duman testi.

Kullanım:
    python smoke.py

5 BIST + 3 ABD sembolü için profil, fiyat serisi ve yıllık mali tabloları
çeker; hangi kalemlerin geldiğini ve hangilerinin boş olduğunu listeler.
Amaç, arayüze geçmeden veri katmanının gerçekten çalıştığını görmek.

Bu araç geçmiş finansal verileri analiz eder, gelecek getiri tahmini veya
yatırım tavsiyesi vermez.
"""

from __future__ import annotations

import sys
import time

from core import universe
from core.yahoo import YahooClient, YahooError

BIST = ["THYAO.IS", "AKBNK.IS", "SISE.IS", "ASELS.IS", "TUPRS.IS"]
ABD = ["AAPL", "MSFT", "KO"]
ENDEKSLER = ["XU100.IS", "^GSPC", "USDTRY=X"]

# F-Skoru ve borç metrikleri için olması gereken kalemler. Bankalarda bir
# kısmının boş dönmesi beklenen davranış.
KRITIK_KALEMLER = [
    "TotalRevenue",
    "GrossProfit",
    "EBITDA",
    "NetIncome",
    "TotalAssets",
    "CurrentAssets",
    "CurrentLiabilities",
    "LongTermDebt",
    "TotalDebt",
    "StockholdersEquity",
    "OperatingCashFlow",
    "FreeCashFlow",
    "OrdinarySharesNumber",
]


def para(value) -> str:
    """Kaba, ASCII-güvenli tutar gösterimi — yalnızca duman testi konsol çıktısı için.

    Eskiden `f"{v:,.2f}".replace(",", ".")` kullanılıyordu: bu, İngilizce binlik
    virgülünü VE ondalık noktasını aynı anda değiştirip yeterince büyük
    tutarlarda "1,500.00" -> "1.500.00" gibi belirsiz, iki noktalı bir sayı
    üretiyordu (S5 sınıfı — core.bicim.para() bu tuzağı çözmek için yazıldı,
    ama bu araç kasıtlı ASCII/nokta-ondalık çıktı istiyor, core.bicim'in
    Türkçe virgül kuralını istemiyor). Doğru düzeltme binlik ayracını hiç
    istememek: bölüm sonrası değerler zaten tek/iki/üç basamaklı, ayraca
    gerek yok.
    """
    if value is None:
        return "-"
    for limit, suffix in ((1e12, "T"), (1e9, "Mr"), (1e6, "Mn"), (1e3, "B")):
        if abs(value) >= limit:
            return f"{value / limit:.2f}{suffix}"
    return f"{value:.2f}"


def sembol_raporu(client: YahooClient, symbol: str) -> None:
    print(f"\n{'=' * 68}\n  {symbol}\n{'=' * 68}")

    # --- profil
    try:
        profile = client.profile(symbol)
    except YahooError as error:
        print(f"  PROFIL HATASI: {error}")
        profile = {}
    else:
        fc = profile.get("financial_currency")
        pc = profile.get("price_currency")
        uyari = "  <-- TABLO/FIYAT PARA BIRIMI FARKLI" if fc and pc and fc != pc else ""
        print(f"  {profile.get('name') or '?'}")
        print(f"  sektor        : {profile.get('sector')} / {profile.get('industry')}")
        print(f"  tablo parasi  : {fc}   fiyat parasi: {pc}{uyari}")
        print(f"  piyasa degeri : {para(profile.get('market_cap'))} {pc}")
        print(
            f"  F/K={profile.get('trailing_pe')}  PD/DD={profile.get('price_to_book')}"
            f"  ROE={profile.get('return_on_equity')}"
        )
        if universe.uses_bank_accounting(profile.get("sector"), profile.get("industry")):
            print("  NOT: banka/finans muhasebesi — FAVOK, brut kar, cari oran beklenmiyor")

    # --- fiyat serisi
    try:
        closes = client.series(symbol, first_range="2y")
    except YahooError as error:
        print(f"  SERI HATASI: {error}")
    else:
        if closes:
            print(
                f"  seri          : {len(closes)} bar, {closes[0][0]} -> {closes[-1][0]},"
                f" son kapanis {closes[-1][1]:.2f}"
            )
        else:
            print("  seri          : bos")

    # --- yıllık mali tablolar
    try:
        annual = client.fundamentals(symbol, "annual")
    except YahooError as error:
        print(f"  TABLO HATASI: {error}")
        return

    fields = annual["fields"]
    gelen = [name for name in KRITIK_KALEMLER if name in fields]
    eksik = [name for name in KRITIK_KALEMLER if name not in fields]
    print(f"  kalem         : {len(gelen)}/{len(KRITIK_KALEMLER)} geldi")
    if eksik:
        print(f"  EKSIK         : {', '.join(eksik)}")

    revenue = fields.get("TotalRevenue") or []
    if revenue:
        birimler = {point.get("currency") for point in revenue}
        print(f"  gelir serisi  : para birimi {birimler}")
        for point in revenue[-4:]:
            print(f"      {point['date']}  {para(point['value'])}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    started = time.monotonic()
    client = YahooClient()

    print("BORSA PANELI — VERI KATMANI DUMAN TESTI")
    print("Bu arac gecmis finansal verileri analiz eder, yatirim tavsiyesi vermez.")

    # Endeksler ve kur: bunlar chart ucundan gelir, crumb gerektirmez.
    print(f"\n{'-' * 68}\n  ENDEKS / KUR\n{'-' * 68}")
    for symbol in ENDEKSLER:
        try:
            chart = client.chart(symbol, range_="5d")
        except YahooError as error:
            print(f"  {symbol:12s} HATA: {error}")
        else:
            print(
                f"  {symbol:12s} {chart['last_price']} {chart['currency']}"
                f"  ({chart['exchange']})"
            )

    for symbol in BIST + ABD:
        sembol_raporu(client, symbol)

    # Evren: sadece toplam sayıları doğrula, tam listeyi kurmadan.
    print(f"\n{'-' * 68}\n  EVREN (screener ucu)\n{'-' * 68}")
    for market in universe.market_ids():
        config = universe.market_config(market)
        try:
            page = client.screener(config["exchanges"], size=5)
        except YahooError as error:
            print(f"  {market:5s} HATA: {error}")
        else:
            ilk = ", ".join(quote["symbol"] for quote in page["quotes"])
            print(
                f"  {market:5s} toplam {page['total']} hisse, "
                f"hedef {config['limit']} | ilk: {ilk}"
            )

    elapsed = time.monotonic() - started
    print(
        f"\n{'-' * 68}\n  {client.request_count} istek, {elapsed:.1f} saniye\n{'-' * 68}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
