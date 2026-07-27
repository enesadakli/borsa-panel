"""Evren taraması — bağlam tablolarını doldurur.

Kullanım:
    python tools/tarama.py bist
    python tools/tarama.py us --limit 200

Panelin ilk açılışındaki uzun adım budur. Sembol başına profil + yıllık tablo +
çeyreklik tablo çekilir (~3 istek). 616 BIST hissesi ~4 istek/sn ile yaklaşık
10-15 dakika sürer. Sonuç 7 gün önbellekte tutulur; tarayıcı, piyasa bakışı ve
sektör medyanları tamamen bu kayıttan çalışır.

Yarıda kesilirse kaybedilen tek şey bağlam tablosudur: tek tek çekilen profil
ve mali tablolar diskte kaldığı için ikinci çalıştırma çok daha hızlı biter.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import context as C
from core import universe as U
from core.yahoo import YahooClient


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    market = argv[0] if argv else "bist"
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])

    client = YahooClient()
    config = U.market_config(market)

    print(f"[{market}] evren kuruluyor ({config['label']})...", flush=True)
    entries = U.load(client, market)["entries"]
    hedef = min(limit, len(entries)) if limit else len(entries)
    print(f"[{market}] {len(entries)} sembol bulundu, {hedef} taranacak", flush=True)

    basladi = time.monotonic()

    def ilerleme(index: int, total: int, symbol: str) -> None:
        if index % 25 and index != total:
            return
        gecen = time.monotonic() - basladi
        hiz = index / gecen if gecen else 0
        kalan = (total - index) / hiz if hiz else 0
        print(
            f"[{market}] {index}/{total} ({index / total:.0%})  "  # bicim-istisna: canlı ilerleme metası
            f"gecen {gecen / 60:.1f} dk  tahmini kalan {kalan / 60:.1f} dk  "  # bicim-istisna: konsol metası
            f"son: {symbol}",
            flush=True,
        )

    record = C.build_metric_context(client, market, limit=limit, progress=ilerleme)
    sure = time.monotonic() - basladi

    print(
        f"\n[{market}] BITTI: {record['count']}/{record['attempted']} sembol, "
        f"{sure / 60:.1f} dk, {client.request_count} istek",  # bicim-istisna: konsol metası
        flush=True,
    )
    if record["errors"]:
        print(f"[{market}] {len(record['errors'])} sembolde hata:", flush=True)
        for hata in record["errors"][:12]:
            print(f"    {hata['symbol']}: {hata['error']}", flush=True)

    sektor_sayisi = len(record["sector_stats"])
    yeterli = sum(
        1
        for stats in record["sector_stats"].values()
        if (stats.get("fscore") or {}).get("sufficient")
    )
    print(
        f"[{market}] {sektor_sayisi} sektör, bunların {yeterli} tanesinde "
        f"F-Skoru medyanı için yeterli örneklem var",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
