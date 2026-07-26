"""Terminalden tam şirket raporu.

Kullanım:
    python tools/rapor.py SISE.IS
    python tools/rapor.py AKBNK.IS THYAO.IS AAPL

Panelin skor kartında görünecek her şeyi metin olarak basar: kural tabanlı
özet, bayraklar, bağlamlı metrikler, kalite zaman çizgisi ve son çeyrek
raporu. Arayüz hazır olmadan da aracın tamamı kullanılabilir olsun diye var.

Bu araç geçmiş finansal verileri analiz eder, gelecek getiri tahmini veya
yatırım tavsiyesi vermez.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bicim as B
from core import context as C
from core import flags as FL
from core import fundamentals as F
from core import health as H
from core import inflation as INF
from core import narrative as N
from core import reports as R
from core import universe as U
from core.yahoo import YahooClient, YahooError

GENISLIK = 78
BLOKLAR = "▁▂▃▄▅▆▇█"

UYARI = (
    "Bu arac gecmis finansal verileri analiz eder, gelecek getiri tahmini veya "
    "yatirim tavsiyesi vermez."
)


def cizgi(karakter: str = "─") -> str:
    return karakter * GENISLIK


def baslik(metin: str, karakter: str = "═") -> None:
    print(f"\n{karakter * GENISLIK}\n  {metin}\n{karakter * GENISLIK}")


def alt_baslik(metin: str) -> None:
    print(f"\n  {metin}\n  {cizgi('─')[:GENISLIK - 2]}")


def sparkline(values: list[float]) -> str:
    """Sayı dizisini tek satır blok grafiğe çevirir."""
    temiz = [v for v in values if v is not None]
    if len(temiz) < 2:
        return ""
    en_az, en_cok = min(temiz), max(temiz)
    aralik = en_cok - en_az
    if aralik == 0:
        return BLOKLAR[len(BLOKLAR) // 2] * len(temiz)
    return "".join(
        BLOKLAR[min(len(BLOKLAR) - 1, int((v - en_az) / aralik * (len(BLOKLAR) - 1)))]
        for v in temiz
    )


# Yüzde/sayı/para biçimlendirmesi core.bicim'e devredildi. Eski hallerinde
# iki ayrı hata vardı: (1) ondalık ayracı İngilizce nokta kalıyordu ("9.00"),
# arayüzün Türkçe virgülüyle aynı ekranda çelişiyordu; (2) para() içindeki
# `,.2f` + `.replace(",", ".")` ikilisi binlik ayracı VE ondalık noktasını
# aynı anda değiştiriyordu — "1.234,56" gibi bir tutar sessizce "1.234.56"
# olurdu (S5 sınıfı: biçim tek kaynaktan gelmeyince böyle hatalar doğar).
def yuzde(value, isaretli: bool = True) -> str:
    return B.yuzde(value, 1, isaretli)


def sayi(value, basamak: int = 2) -> str:
    return B.sayi(value, basamak)


def para(value) -> str:
    return B.para(value)


def rapor(client: YahooClient, symbol: str) -> None:
    try:
        profile = client.profile(symbol)
        pack = F.load(client, symbol, profile)
    except YahooError as error:
        print(f"\n{symbol}: veri alinamadi — {error}")
        return

    cpi = INF.series_for_pack(client.cache, pack)
    analysis = H.analyze(client, symbol, pack, cpi)
    reports = R.analyze_reports(client, symbol, pack, cpi)

    market = U.find_market(client, symbol)
    context = C.load_context(client, market)
    bayraklar = FL.evaluate_flags(client, symbol, analysis, pack, context)
    ozet = N.generate_company_summary(symbol, analysis, reports, cpi, pack)

    # ---------------------------------------------------------------- başlık
    baslik(f"{symbol} — {profile.get('name') or '?'}")
    print(f"  {profile.get('sector') or '?'} / {profile.get('industry') or '?'}")
    fiyat_para = profile.get("price_currency")
    tablo_para = pack.get("currency")
    print(f"  fiyat {sayi(profile.get('last_price'))} {fiyat_para}   "
          f"piyasa degeri {para(profile.get('market_cap'))} {fiyat_para}")
    if tablo_para and fiyat_para and tablo_para != fiyat_para:
        print(f"  DIKKAT: mali tablolar {tablo_para}, hisse {fiyat_para} isliyor — "
              f"oranlar {tablo_para} bazina cevrildi")
    if pack.get("market_cap_reliable") is False:
        print(f"  UYARI: {pack['market_cap_note'][:200]}")
    if pack.get("bank_accounting"):
        print("  Banka/finans muhasebesi: FAVOK, brut kar, cari oran ve Altman Z "
              "bu sektorde tanimsiz")

    tazelik = pack.get("freshness") or {}
    if tazelik.get("latest_period"):
        bayat = tazelik.get("level") in ("bayat", "cok_bayat")
        onek = "DIKKAT: " if bayat else ""
        print(f"  {onek}son donem {tazelik['latest_period']} "
              f"({tazelik.get('label') or '?'})"
              + ("  — butun metrikler bu tarihe ait" if bayat else ""))

    # -------------------------------------------------------------- özet
    alt_baslik("OZET")
    for cumle in ozet["sentences"]:
        print(f"  {cumle['order']}. {cumle['text']}")
        if cumle["sources"]:
            kaynak = ", ".join(
                f"{k['item']}@{k['period']}" for k in cumle["sources"][:3]
            )
            print(f"     kaynak: {kaynak}")
    dq = ozet["data_quality"]
    print(f"\n  veri kalitesi: para birimi dogrulandi={dq['currency_verified']}  "
          f"TUFE={dq['cpi_available']}  eksik kalem={len(dq['missing_items'])}")

    # ---------------------------------------------------------- bayraklar
    alt_baslik(f"BAYRAKLAR  (kirmizi {bayraklar['red_count']}, "
               f"sari {bayraklar['yellow_count']})")
    if not bayraklar["flags"]:
        print("  Tanimli kurallardan hicbiri tetiklenmedi.")
    for bayrak in bayraklar["flags"]:
        etiket = "KIRMIZI" if bayrak["level"] == FL.KIRMIZI else "SARI   "
        yaklasik = " [yaklasik hesap]" if bayrak["approximate"] else ""
        print(f"  [{etiket}] {bayrak['title']}{yaklasik}")
        for satir in _sar(bayrak["explanation"] or "", GENISLIK - 14):
            print(f"            {satir}")
    for note in bayraklar.get("notes", []):
        print(f"  [bilgi  ] {note['title']}")
        for satir in _sar(note["explanation"] or "", GENISLIK - 14):
            print(f"            {satir}")
    if bayraklar["not_applied"]:
        print(f"\n  Calistirilmayan kurallar ({len(bayraklar['not_applied'])}):")
        for bayrak in bayraklar["not_applied"]:
            print(f"    {bayrak['id']:32s} {bayrak['skip_reason']}")

    # ------------------------------------------------------------- F-Skoru
    fscore = analysis["fscore"]
    alt_baslik("F-SKORU")
    if fscore["model_note"]:
        print(f"  NOT: {fscore['model_note']}")
    for nokta in fscore["points"]:
        isaret = " " if nokta["usable"] else "×"
        print(f"  {isaret} {nokta['date']}  {nokta['label']}")
    son = fscore["latest"]
    if son:
        print()
        for kriter in son["criteria"]:
            if kriter["status"] == H.OK:
                durum = "GECTI" if kriter["passed"] else "KALDI"
            elif kriter["status"] == H.GECERSIZ:
                durum = " NA  "
            else:
                durum = " ?   "
            print(f"    {durum}  {kriter['label']:36s} {kriter.get('detail') or ''}")

    # ------------------------------------------------------- metrik bağlamı
    alt_baslik("METRIKLER" + ("" if context else "  (sektor baglami icin tarama gerekli)"))
    if context:
        print(f"  {'metrik':24s} {'deger':>10s} {'trend':>8s} "
              f"{'sektor med':>11s} {'sektor%':>8s} {'evren%':>7s}")
        for item in C.all_metric_contexts(context, symbol):
            if item.get("not_applicable"):
                print(f"  {item['label']:24s} {'—':>10s}   sektorde tanimsiz")
                continue
            if not item.get("available"):
                continue
            trend = (item.get("trend") or {}).get("direction") or "—"
            sp = item.get("sector_percentile")
            up = item.get("universe_percentile")
            # Altman Z'de tavanın üstü "10+" gösterilir (bkz. core.bicim.altman);
            # diğer tüm metrikler normal iki basamak.
            deger_bicimi = B.altman if item["metric"] == "altman_z" else B.sayi
            print(
                f"  {item['label']:24s} {deger_bicimi(item['value']):>10s} {trend:>8s} "
                f"{deger_bicimi(item.get('sector_median')):>11s} "
                f"{B.sayi(sp, 0):>8s} "
                f"{B.sayi(up, 0):>7s}"
            )
        yetersiz = [
            item["label"]
            for item in C.all_metric_contexts(context, symbol)
            if item.get("sector_note")
        ]
        if yetersiz:
            print(f"\n  Sektor ornekleminin yetersiz oldugu metrikler: "
                  f"{', '.join(yetersiz[:6])}")
    else:
        for anahtar, etiket in (
            ("pe", "F/K"), ("pb", "PD/DD"),
        ):
            node = analysis["valuation"].get(anahtar) or {}
            print(f"  {etiket:24s} {sayi(node.get('value')):>10s}  {node.get('detail') or ''}")

    # ------------------------------------------------------ kalite çizgisi
    timeline = H.quality_timeline(client, symbol, analysis, pack)
    alt_baslik("KALITE ZAMAN CIZGISI")
    fs = [nokta["value"] for nokta in timeline["fscore"]]
    if fs:
        print(f"  F-Skoru            {sparkline(fs):10s}  "
              f"{' → '.join(str(v) for v in fs)}")
    for ad, anahtar in (("Brut marj", "gross"), ("Faaliyet marji", "operating"),
                        ("Net marj", "net")):
        seri = [v for _, v in timeline["margins"].get(anahtar) or []]
        if seri:
            print(f"  {ad:18s} {sparkline(seri):10s}  "
                  f"{' → '.join(B.sayi(v, 1) for v in seri)}")
    nd = [n["value"] for n in timeline["net_debt_ebitda"] if n["value"] is not None]
    if nd:
        print(f"  {'Net borc/FAVOK':18s} {sparkline(nd):10s}  "
              f"{' → '.join(B.sayi(v, 2) for v in nd)}")
    rr = [n["value"] for n in timeline["real_revenue_growth"] if n["value"] is not None]
    if rr:
        print(f"  {'Reel gelir buyume':18s} {sparkline(rr):10s}  "
              f"{' → '.join(yuzde(v) for v in rr)}")
    print(f"\n  {timeline['axis_note']}")
    print(f"  Ozet: {timeline['summary']['text']}")

    # ------------------------------------------------------- çeyrek raporu
    ceyrek = reports["quarterly"]
    if ceyrek.get("available"):
        alt_baslik(f"SON CEYREK  {ceyrek['current_date']}  "
                   f"(karsilastirma: {ceyrek.get('compare_date')})")
        print(f"  {'kalem':24s} {'tutar':>16s} {'YoY':>9s} {'QoQ':>9s}")
        for satir in ceyrek["lines"]:
            yoy = satir["yoy"] or {}
            qoq = satir["qoq"] or {}
            print(
                f"  {satir['label']:24s} {para(satir['value']):>16s} "
                f"{(yuzde(yoy.get('pct')) if yoy.get('pct') is not None else '—'):>9s} "
                f"{(yuzde(qoq.get('pct')) if qoq.get('pct') is not None else '—'):>9s}"
            )
        print()
        for yorum in ceyrek["comments"]:
            for index, satir in enumerate(_sar(yorum["text"], GENISLIK - 6)):
                print(f"  {'•' if index == 0 else ' '} {satir}")
            print(f"    [{yorum['rule_id']}]")

    print(f"\n{cizgi('─')}\n  {UYARI}\n{cizgi('─')}")


def _sar(metin: str, genislik: int) -> list[str]:
    """Basit satır sarma — textwrap yerine, uzun kelimeleri bölmeden."""
    kelimeler = (metin or "").replace("**", "").split()
    satirlar, mevcut = [], ""
    for kelime in kelimeler:
        if len(mevcut) + len(kelime) + 1 > genislik:
            satirlar.append(mevcut)
            mevcut = kelime
        else:
            mevcut = f"{mevcut} {kelime}".strip()
    if mevcut:
        satirlar.append(mevcut)
    return satirlar or [""]


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not argv:
        print(__doc__)
        return 1

    client = YahooClient()
    for symbol in argv:
        rapor(client, symbol.strip().upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
