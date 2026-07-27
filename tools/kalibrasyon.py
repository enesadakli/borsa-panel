"""Bayrak kalibrasyonu.

Her bayrak kuralının evrende kaç şirketi tetiklediğini sayar. Bir kural
evrenin %60'ını tetikliyorsa o eşik bilgi taşımıyor demektir — "herkeste var"
olan bir uyarı uyarı değildir. Hiç tetiklenmeyen kural da ölü koddur.

Kullanım:
    python tools/kalibrasyon.py bist
    python tools/kalibrasyon.py bist --limit 200

Bağlam taraması önbellekte olduğu için ağa yeni istek atmaz; mali tablolar
diskten okunur.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bicim as B
from core import context as C
from core import flags as FL
from core import fundamentals as F
from core import health as H
from core import inflation as INF
from core import universe as U
from core.yahoo import YahooClient, YahooError

# Bir kuralın "bilgi taşıdığı" kabul edilen tetiklenme aralığı.
COK_SIK = 0.60
COK_SEYREK = 0.005


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])

    marketler = [a for a in argv if not a.startswith("--") and not a.isdigit()]
    if not marketler:
        marketler = ["bist"]

    client = YahooClient()

    # Her evren ayrı ölçülür, sonra çapraz karşılaştırılır. Tek evrene bakmak
    # yanıltıyordu: Y5 ABD'de 0 tetikleniyor ve araç "eşik fazla dar" diyordu,
    # oysa ABD'de 500 şirketin hepsinin para birimi dolu — koşul hiç oluşmuyor.
    # BIST'te aynı kural %1,6 tetikliyor, yani eşik doğru.
    olcumler: dict[str, dict] = {}
    for market in marketler:
        olcum = _evreni_olc(client, market, limit)
        if olcum is None:
            return 1
        olcumler[market] = olcum

    return _raporla(olcumler)


def _evreni_olc(client, market: str, limit: int | None) -> dict | None:
    context = C.load_context(client, market)
    if context is None:
        print(f"'{market}' için bağlam taraması yok. Önce: python tools/tarama.py {market}")
        return None

    semboller = list(context["symbols"])
    if limit:
        semboller = semboller[:limit]

    print(f"[{market}] {len(semboller)} şirket üzerinde bayraklar hesaplanıyor...")
    basladi = time.monotonic()

    tetiklenme: dict[str, int] = {}
    uygulanmayan: dict[str, int] = {}
    seviye: dict[str, str] = {}
    baslik: dict[str, str] = {}
    ornekler: dict[str, list[str]] = {}
    hatali = 0
    degerlendirilen = 0

    for index, symbol in enumerate(semboller, start=1):
        try:
            pack = F.load(client, symbol)
            cpi = INF.series_for_pack(client.cache, pack)
            analysis = H.analyze(client, symbol, pack, cpi)
            sonuc = FL.evaluate_flags(client, symbol, analysis, pack)
        except (YahooError, KeyError, TypeError, ValueError, ZeroDivisionError):
            hatali += 1
            continue

        degerlendirilen += 1
        # Bilgi seviyesi notlar da sayılır: Y6 gibi bir kuralın kaç şirkette
        # tetiklendiğini görmek, onu neden bilgi seviyesine indirdiğimizin
        # gerekçesini korur.
        for bayrak in sonuc["flags"] + sonuc.get("notes", []):
            tetiklenme[bayrak["id"]] = tetiklenme.get(bayrak["id"], 0) + 1
            seviye[bayrak["id"]] = bayrak["level"]
            baslik[bayrak["id"]] = bayrak["title"]
            ornekler.setdefault(bayrak["id"], [])
            if len(ornekler[bayrak["id"]]) < 4:
                ornekler[bayrak["id"]].append(symbol)
        for bayrak in sonuc["not_applied"]:
            uygulanmayan[bayrak["id"]] = uygulanmayan.get(bayrak["id"], 0) + 1
            seviye.setdefault(bayrak["id"], bayrak["level"])
            baslik.setdefault(bayrak["id"], bayrak["title"])

        if index % 100 == 0:
            print(f"  ... {index}/{len(semboller)}", flush=True)

    sure = time.monotonic() - basladi
    print(
        f"[{market}] {degerlendirilen} şirket değerlendirildi"
        + (f", {hatali} şirket atlandı" if hatali else "")
        + f"  ({sure:.0f} sn)"  # bicim-istisna: konsol metası, finansal rakam değil
    )

    return {
        "market": market,
        "tetiklenme": tetiklenme,
        "uygulanmayan": uygulanmayan,
        "seviye": seviye,
        "baslik": baslik,
        "ornekler": ornekler,
        "degerlendirilen": degerlendirilen,
    }


def _oran(olcum: dict, kural: str) -> tuple[int, int, float]:
    adet = olcum["tetiklenme"].get(kural, 0)
    atlanan = olcum["uygulanmayan"].get(kural, 0)
    uygulanan = max(0, olcum["degerlendirilen"] - atlanan)
    return adet, uygulanan, (adet / uygulanan if uygulanan else 0.0)


def _raporla(olcumler: dict[str, dict]) -> int:
    marketler = list(olcumler)
    tum_kurallar = sorted(
        set(_bilinen_kurallar())
        | {k for o in olcumler.values() for k in o["tetiklenme"]}
        | {k for o in olcumler.values() for k in o["uygulanmayan"]}
    )

    genislik = 34 + len(marketler) * 22 + 34
    print("\n" + "=" * genislik)
    baslik_satiri = f"{'KURAL':32s} "
    for market in marketler:
        baslik_satiri += f"{market.upper() + ' (tetik/uygulanan)':>21s} "
    print(baslik_satiri + " DURUM")
    print("-" * genislik)
    print("  Oran = tetiklenen / kuralin uygulanabildigi sirket sayisi.")
    if len(marketler) > 1:
        print("  Bir kural bir evrende hic tetiklenmiyorsa, digerinde tetikleniyor mu")
        print("  diye bakilir: kosul o evrende hic olusmuyorsa esik dogrudur.\n")
    else:
        print("  Tek evren olculdu; 'hic tetiklenmedi' sonucu ikinci bir evrenle")
        print("  dogrulanmali (ornek: python tools/kalibrasyon.py bist us).\n")

    sorunlu: list[tuple[str, str]] = []
    for kural in tum_kurallar:
        satir = f"{kural:32s} "
        oranlar = {}
        for market in marketler:
            adet, uygulanan, oran = _oran(olcumler[market], kural)
            oranlar[market] = (adet, uygulanan, oran)
            hucre = f"{adet}/{uygulanan} ({B.puan(oran * 100, 1)})"
            satir += f"{hucre:>21s} "

        seviye = next(
            (o["seviye"].get(kural) for o in olcumler.values() if o["seviye"].get(kural)),
            "-",
        )
        uygulanabilir_var = any(u for _, u, _ in oranlar.values())
        tetiklenen_var = any(a for a, _, _ in oranlar.values())
        en_yuksek = max((o for _, _, o in oranlar.values()), default=0.0)

        if not uygulanabilir_var:
            durum = "hicbir evrende uygulanabilir degil"
        elif en_yuksek > COK_SIK and seviye == FL.BILGI:
            durum = f"sik ({B.puan(en_yuksek * 100, 0)}) — bilgi seviyesi, uyari listesinde degil"
        elif en_yuksek > COK_SIK:
            durum = f"COK SIK — esik bilgi tasimiyor ({B.puan(en_yuksek * 100, 0)})"
            sorunlu.append((kural, durum))
        elif not tetiklenen_var:
            durum = "HIC TETIKLENMEDI — esik fazla dar olabilir"
            sorunlu.append((kural, durum))
        elif en_yuksek < COK_SEYREK:
            durum = f"cok seyrek (en yuksek {B.puan(en_yuksek * 100, 2)})"
            sorunlu.append((kural, durum))
        else:
            sessizler = [m for m, (a, u, _) in oranlar.items() if u and not a]
            durum = "makul"
            if sessizler:
                durum += f" — {', '.join(sessizler)} evreninde kosul olusmuyor"

        print(satir + f" {durum}")
        ornek = next(
            (o["ornekler"].get(kural) for o in olcumler.values() if o["ornekler"].get(kural)),
            None,
        )
        if ornek:
            print(f"{'':32s} ornek: {', '.join(ornek)}")

    print("\n" + "=" * genislik)
    if sorunlu:
        print("GOZDEN GECIRILMESI GEREKEN ESIKLER:")
        for kural, durum in sorunlu:
            print(f"  {kural}: {durum}")
    else:
        print("Tum esikler makul araliklarda.")

    print("\nNot: 'uygulanan' sayisi, kuralin o evrende kac sirkette")
    print("hesaplanabildigini gosterir; bankalarda tanimsiz kurallar dusulmustur.")
    return 0


def _bilinen_kurallar() -> list[str]:
    """flags.py'daki tüm kural kimlikleri — hiç tetiklenmeyenler de görünsün."""
    return [
        "R1_KAR_NAKDE_DONMUYOR", "R2_FSKOR_COKUSU", "R3_BORC_SIKISMASI",
        "R4_REEL_DARALMA", "R5_NEGATIF_OZSERMAYE", "R6_FAIZ_KARSILAMA",
        "Y1_MARJ_VE_BORC", "Y2_TEK_SEFERLIK_NAKIT_CIKISI", "Y3_SUPHELI_ORAN",
        "Y4_VERI_EKSIK", "Y5_PARA_BIRIMI_BELIRSIZ", "Y6_TMS29_KIRILMASI",
    ]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
