"""Terminalden LLM-okunur Markdown rapor üretir.

Kullanım:
    python tools/llm_rapor.py SISE.IS
    python tools/llm_rapor.py SISE.IS --dosya sise.md
    python tools/llm_rapor.py AKBNK.IS THYAO.IS --dosya raporlar/

`/api/llm-rapor` ucuyla aynı `core.llm_rapor.olustur()` fonksiyonunu kullanır;
panel çalışmadan da bir LLM'e verilecek raporu terminalden üretmek için var.
`--dosya` bir dosya adıysa oraya yazar (tek sembolde), bir klasörse her
sembolü `<klasör>/<SEMBOL>.md` olarak kaydeder; verilmezse stdout'a basar.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import llm_rapor as LLM
from core.yahoo import YahooClient, YahooError


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dosya = None
    if "--dosya" in argv:
        i = argv.index("--dosya")
        dosya = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    semboller = [s.upper() for s in argv]
    if not semboller:
        print(__doc__)
        return 1

    client = YahooClient()
    hata_var = False
    for sembol in semboller:
        try:
            metin = LLM.olustur(client, sembol)
        except YahooError as error:
            print(f"[{sembol}] veri kaynağına erişilemedi: {error}", file=sys.stderr)
            hata_var = True
            continue

        if not dosya:
            print(metin)
            continue

        hedef = dosya
        if len(semboller) > 1 or os.path.isdir(dosya) or dosya.endswith(("/", "\\")):
            os.makedirs(dosya, exist_ok=True)
            hedef = os.path.join(dosya, f"{sembol}.md")
        with open(hedef, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        print(f"[{sembol}] yazıldı: {hedef}")

    return 1 if hata_var else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
