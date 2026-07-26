"""Terminalden tarayıcı.

Kullanım:
    python tools/filtre.py                          hazır şablonları listeler
    python tools/filtre.py bilanco_kalitesi         şablonu çalıştırır
    python tools/filtre.py reel_buyuyen --evren us
    python tools/filtre.py --alanlar                filtrelenebilir alanları listeler
    python tools/filtre.py --kural kural.json       dosyadan kural çalıştırır
    python tools/filtre.py bilanco_kalitesi --sirala fscore --limit 30

Kural dosyası biçimi (eval yok, yapısal):

    {"operator": "AND", "operands": [
        {"field": "fscore", "op": ">=", "value": 7},
        {"operator": "OR", "operands": [
            {"field": "pe", "op": "<", "value": 10},
            {"field": "pb", "op": "<", "value": 1}
        ]}
    ]}

Sonuç listesi seçilen kriterleri geçen şirketleri gösterir. Sıralamada üstte
olmak gelecek getiri hakkında bilgi taşımaz.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bicim as B
from core import context as C
from core import screener as S
from core import universe as U
from core.yahoo import YahooClient

GENISLIK = 96


def sablonlari_listele() -> None:
    print("\nHazır şablonlar:\n")
    for sablon in S.SABLONLAR:
        print(f"  {sablon['id']}")
        print(f"    {sablon['name']} — {sablon['note']}")
        print(f"    {sablon['explanation']}")
        print(f"    kural: {_kural_metni(sablon['rule'])}\n")


def alanlari_listele() -> None:
    print("\nFiltrelenebilir alanlar:\n")
    for item in S.field_catalog():
        izinli = S.YON_DEGERLERI.get(item["field"])
        ek = f"   degerler: {', '.join(izinli)}" if izinli else ""
        print(f"  {item['field']:32s} {item['label']:32s} [{item['format']}]{ek}")
    print(f"\nOperatörler: {', '.join(sorted(S.OPERATORLER))}")
    print(f"Bağlaçlar:   {S.VE}, {S.VEYA}\n")


def _kural_metni(node: dict) -> str:
    if "operator" in node:
        baglac = " VE " if node["operator"] == S.VE else " VEYA "
        return "(" + baglac.join(_kural_metni(o) for o in node["operands"]) + ")"
    tanim = S.ALANLAR.get(node["field"], {})
    return f"{tanim.get('label', node['field'])} {node['op']} {node['value']}"


def _isaret(sonuc) -> str:
    return "✓" if sonuc is True else ("?" if sonuc is None else "✗")


def yazdir(sonuc: dict, evren: str) -> None:
    sablon = sonuc.get("template")
    if sablon:
        print(f"\n{'═' * GENISLIK}")
        print(f"  {sablon['name']}   [{sablon['note']}]")
        print(f"  {sablon['explanation']}")
        print(f"{'═' * GENISLIK}")
    else:
        print(f"\n{'═' * GENISLIK}\n  Özel kural\n{'═' * GENISLIK}")

    yas = sonuc.get("veri_yasi_saat")
    print(f"  {evren}: {sonuc['scanned']} şirket tarandı"
          + (f", veriler {B.sayi(yas, 0)} saat önce güncellendi" if yas else ""))
    print(f"  {len(sonuc['matched'])} eşleşen, "
          f"{sonuc['partial_count']} kısmi (veri eksik), "
          f"{sonuc.get('not_applicable_count', 0)} uygulanamaz (sektörde tanımsız)\n")

    if not sonuc["matched"]:
        print("  Hiçbir şirket kriterleri geçmedi.\n")
    for sira, kayit in enumerate(sonuc["matched"], start=1):
        ad = (kayit.get("name") or "")[:34]
        print(f"  {sira:3d}. {kayit['symbol']:11s} {ad:34s} "
              f"{kayit['score']}/{kayit['total']}")
        detay = "  ·  ".join(
            f"{c['label']} {_isaret(c['result'])}{c['display']}"
            for c in kayit["checks"]
        )
        print(f"       {detay}")

    if sonuc["partial"]:
        print("\n  Kısmi — veri eksik olduğu için karar verilemedi, "
              "kriterleri geçmiş olabilirler:")
        for kayit in sonuc["partial"][:10]:
            eksikler = ", ".join(
                c["label"] for c in kayit["checks"] if c["reason"] == "veri yok"
            )
            print(f"    {kayit['symbol']:11s} veri yok: {eksikler}")

    if sonuc.get("not_applicable"):
        ornek = ", ".join(k["symbol"] for k in sonuc["not_applicable"][:8])
        print(f"\n  Uygulanamaz — bu kural {sonuc['not_applicable_count']} şirkette "
              f"sektör yapısı gereği tanımsız (banka/finans): {ornek}"
              + (" ..." if sonuc["not_applicable_count"] > 8 else ""))

    print(f"\n  {sonuc['note']}\n")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if "--alanlar" in argv:
        alanlari_listele()
        return 0

    evren = "bist"
    if "--evren" in argv:
        evren = argv[argv.index("--evren") + 1].lower()
        if evren not in U.market_ids():
            print(f"Bilinmeyen evren: {evren}  (geçerli: {', '.join(U.market_ids())})")
            return 1

    limit = 20
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])

    sirala = "market_cap"
    if "--sirala" in argv:
        sirala = argv[argv.index("--sirala") + 1]
        if sirala not in S.ALANLAR and sirala != "market_cap":
            print(f"Bilinmeyen sıralama alanı: {sirala}")
            return 1

    kural_dosyasi = None
    if "--kural" in argv:
        kural_dosyasi = argv[argv.index("--kural") + 1]

    konumsal = [
        arg for index, arg in enumerate(argv)
        if not arg.startswith("--")
        and (index == 0 or not argv[index - 1].startswith("--"))
    ]

    if not konumsal and not kural_dosyasi:
        sablonlari_listele()
        alanlari_listele()
        return 0

    client = YahooClient()
    context = C.load_context(client, evren)
    if context is None:
        print(f"\n'{evren}' evreni için bağlam taraması yok.")
        print(f"Önce: python tools/tarama.py {evren}\n")
        return 1

    try:
        if kural_dosyasi:
            with open(kural_dosyasi, "r", encoding="utf-8") as handle:
                kural = json.load(handle)
            if "rule" in kural:  # kaydedilmiş kural dosyası
                kural = kural["rule"]
            S.validate(kural)
            sonuc = S.screen(context, kural, sort_by=sirala, limit=limit)
        else:
            sonuc = S.run_template(context, konumsal[0], sort_by=sirala, limit=limit)
    except S.RuleError as error:
        print(f"\nKural hatası: {error}\n")
        return 1
    except (OSError, ValueError) as error:
        print(f"\nKural dosyası okunamadı: {error}\n")
        return 1

    sonuc["veri_yasi_saat"] = C.context_age_hours(client, evren)
    yazdir(sonuc, U.market_config(evren)["label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
