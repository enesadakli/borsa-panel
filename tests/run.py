"""Test koşucusu — pytest yok, sıfır bağımlılık.

Kullanım:
    python tests/run.py              # tüm testler
    python tests/run.py dil fskor    # yalnızca adı eşleşenler
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import traceback

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

MODULLER = ("test_dil", "test_fskor", "test_reel", "test_portfoy", "test_tarayici",
            "test_anlati", "test_tazelik", "test_bicim_lint")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    secim = [arg.lower() for arg in argv]
    gecen = dusen = atlanan = 0
    basladi = time.monotonic()

    for modul_adi in MODULLER:
        if secim and not any(parca in modul_adi for parca in secim):
            continue
        try:
            modul = importlib.import_module(f"tests.{modul_adi}")
        except ModuleNotFoundError as error:
            print(f"\n[ATLA] {modul_adi}: {error}")
            atlanan += 1
            continue

        print(f"\n{'=' * 66}\n  {modul_adi}\n{'=' * 66}")
        for isim in sorted(dir(modul)):
            if not isim.startswith("test_"):
                continue
            fonksiyon = getattr(modul, isim)
            if not callable(fonksiyon):
                continue
            try:
                fonksiyon()
            except AssertionError as error:
                dusen += 1
                print(f"  DUSTU  {isim}")
                print(f"         {error}")
            except Exception:  # noqa: BLE001 — beklenmeyen hatayı da raporla
                dusen += 1
                print(f"  HATA   {isim}")
                for satir in traceback.format_exc().strip().splitlines()[-4:]:
                    print(f"         {satir}")
            else:
                gecen += 1
                print(f"  gecti  {isim}")

    sure = time.monotonic() - basladi
    print(f"\n{'-' * 66}")
    print(f"  {gecen} gecti, {dusen} dustu"
          + (f", {atlanan} modul atlandi" if atlanan else "")
          + f"  ({sure:.1f} sn)")
    print(f"{'-' * 66}")
    return 1 if dusen else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
