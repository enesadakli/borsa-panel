"""Anlatı denetim aracı — bayrak kalibrasyonunun narratif karşılığı.

Kural tabanlı cümleler tekil örnekle test edildiğinde çalışıyor gibi
görünebilir ama evrenin geneline uygulanınca gürültüye ya da çelişkiye
dönüşebilir. NETCD vakası tam buydu: "F-Skoru 7'den 9'a çıktı ama kriterler
değişmedi" cümlesi tek başına mantıklı görünüyordu; düzeltmenin ilk hâli de
aynı şekilde tek örnekle test edilip **her şirkette** aynı gürültü notunu
üretmeye başlamıştı (kapsam-genişlemesi notu evrenin tamamında çıkıyordu).

Bu araç iki şeyi arar:

1. **Frekans:** her `rule_id`'nin kaç şirkette göründüğü. Bir cümle
   şirketlerin çoğunda birebir aynıysa (Y6/TMS-29 vakası gibi) o cümle
   ayırt edici değildir, gürültüdür.
2. **Yapısal değişmezler:** cümle sayısı sınırları, kaynak eksikliği,
   çelişkili ifadeler ("değişmedi" derken skor farklıysa), sayı biçimi
   sızıntıları (nokta ondalık, None, eksi sıfır), yasak dil.

Kullanım:
    python tools/anlati_denetim.py bist
    python tools/anlati_denetim.py bist us --limit 200

Önbellekten çalışır, mali tablo indirmez; tüm evren ~birkaç dakikada biter
(narrative + reports üretimi CPU'da, ağa çıkmaz).
"""

from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import context as C
from core import fundamentals as F
from core import health as H
from core import inflation as INF
from core import narrative as N
from core import reports as R
from core.yahoo import YahooClient, YahooError

# Bir anlatı cümlesi (rule_id) şirketlerin bu oranından fazlasında BİREBİR
# AYNI metinle çıkıyorsa gürültü sayılır. Y6/TMS-29 kalibrasyonunda bu %89
# çıkmıştı ve bilgi seviyesine indirilmişti; aynı testi anlatı cümlelerine
# de uyguluyoruz.
COK_SIK_AYNI = 0.60

# Yasak dil — test_dil.py ile aynı liste, ama burada üretilen her cümlenin
# üzerinden geçiyoruz (kaydedilmiş şablon yerine gerçek üretilen metin).
YASAK = [
    (r"hedef fiyat", "hedef fiyat"),
    (r"\b(al|sat|alım|satım)\s+sinyali", "al/sat sinyali"),
    (r"\bucuz\b", "değerleme yargısı"),
    (r"\bpahalı\b", "değerleme yargısı"),
    (r"\bcazip\b", "değerleme yargısı"),
    (r"alın(malı|abilir)\b", "alım yönlendirmesi"),
]

# Sayı biçimi sızıntıları: nokta ondalık (İngilizce), None sızıntısı,
# eksi sıfır. Tarih kalıplarını (2025-12-31, 2024-09) yakalamamak için
# negatif bakış kullanılıyor.
#
# Dikkat: "%+1.281,1" TAMAMEN doğru Türkçe biçimdir — nokta binlik ayracı,
# virgül ondalık ayracı. Bu regex'in ilk sürümü "1.281" kısmını yanlışlıkla
# "İngilizce ondalık" sanıp 27 şirkette sahte ihlal üretti. Ayırt edici kural:
# Türkçe binlik grubu HER ZAMAN tam 3 basamaktır (1.281, 12.345). Gerçek bir
# İngilizce ondalık sızıntısı ise `.1f`/`.2f` formatından gelir, yani nokta
# sonrası 1-2 basamak olur (9.00, 12.7). 3 basamaklı grup güvenlidir; 1-2 ya
# da 4+ basamaklı grup şüphelidir. Bu ayrım tek regex'e sığmadığı için
# aşağıda Python kodunda, yakalanan basamak sayısına bakılarak yapılıyor.
NOKTA_ONDALIK = re.compile(r"(?<!\d)\d+\.(\d+)(?!\d)")
EKSI_SIFIR = re.compile(r"[-−]0[.,]0\b")
NONE_SIZINTISI = re.compile(r"\bNone\b")


def _nokta_ondalik_sizintisi(metin: str):
    """Gerçek bir İngilizce ondalık noktası mı, yoksa Türkçe binlik grubu mu?

    Binlik grubu tam 3 basamaklıdır ve genelde art arda gelir (1.234.567).
    Sızıntı ise 1-2 basamaklı (yuvarlanmış oran/yüzde) ya da 3'ten farklı
    uzunlukta olur.
    """
    for eslesme in NOKTA_ONDALIK.finditer(metin):
        if len(eslesme.group(1)) != 3:
            return eslesme.group()
    return None


def denetle_evren(client: YahooClient, market: str, limit: int | None = None,
                  sessiz: bool = False) -> list[str] | None:
    """Tek evrenin anlatı denetimi. `None` döner: bağlam taraması yok demektir.

    `tests/test_anlati.py` bu fonksiyonu doğrudan çağırır — CLI çıktısını
    (`main()`) değil, saf sonucu almak için. `sessiz=True` ilerleme satırlarını
    bastırır.
    """
    context = C.load_context(client, market)
    if context is None:
        return None

    semboller = list(context["symbols"])
    if limit:
        semboller = semboller[:limit]

    if not sessiz:
        print(f"\n[{market}] {len(semboller)} şirket üzerinde anlatı denetleniyor...")
    basladi = time.monotonic()

    # rule_id -> [(symbol, text), ...] — frekans analizi için
    narratif_metinleri: dict[str, list[tuple[str, str]]] = {}
    yorum_metinleri: dict[str, list[tuple[str, str]]] = {}
    yapisal_ihlaller: list[str] = []
    cumle_dagilimi: dict[int, int] = {}
    hatali = 0

    for index, symbol in enumerate(semboller, start=1):
        try:
            pack = F.load(client, symbol)
            cpi = INF.series_for_pack(client.cache, pack)
            analysis = H.analyze(client, symbol, pack, cpi)
            reports = R.analyze_reports(client, symbol, pack, cpi)
            ozet = N.generate_company_summary(symbol, analysis, reports, cpi, pack)
        except (YahooError, KeyError, TypeError, ValueError, ZeroDivisionError):
            hatali += 1
            continue

        yapisal_ihlaller.extend(_yapisal_kontrol(symbol, ozet, analysis))
        n = len(ozet["sentences"])
        cumle_dagilimi[n] = cumle_dagilimi.get(n, 0) + 1

        for cumle in ozet["sentences"]:
            narratif_metinleri.setdefault(cumle["rule_id"], []).append(
                (symbol, cumle["text"])
            )

        for donem_adi in ("quarterly", "annual"):
            donem = reports.get(donem_adi) or {}
            for yorum in donem.get("comments") or []:
                yorum_metinleri.setdefault(yorum["rule_id"], []).append(
                    (symbol, yorum["text"])
                )

        if not sessiz and index % 100 == 0:
            print(f"  ... {index}/{len(semboller)}", flush=True)

    sure = time.monotonic() - basladi
    degerlendirilen = len(semboller) - hatali

    if not sessiz:
        print(f"[{market}] {degerlendirilen} şirket değerlendirildi"
              + (f", {hatali} atlandı" if hatali else "")
              + f"  ({sure:.0f} sn)")
        az_veri = sum(v for n, v in cumle_dagilimi.items() if n < 4)
        print(f"[{market}] cümle sayısı dağılımı (0-3 arası '{az_veri}' şirkette "
              "veri kısıtlı, bu bir ihlal değil — bilgi amaçlı):")
        for n in sorted(cumle_dagilimi):
            print(f"   {n} cümle: {cumle_dagilimi[n]} şirket")

    ihlaller: list[str] = []
    ihlaller.extend(f"[{market}] {msg}" for msg in yapisal_ihlaller)
    ihlaller.extend(_frekans_raporu(market, "narratif", narratif_metinleri,
                                     degerlendirilen, sessiz))
    ihlaller.extend(_frekans_raporu(market, "rapor yorumu", yorum_metinleri,
                                     degerlendirilen, sessiz))
    return ihlaller


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    marketler = [a for a in argv if not a.startswith("--")]
    if not marketler:
        marketler = ["bist"]
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])

    client = YahooClient()
    ihlaller: list[str] = []

    for market in marketler:
        sonuc = denetle_evren(client, market, limit)
        if sonuc is None:
            print(f"'{market}' için bağlam taraması yok. Önce: python tools/tarama.py {market}")
            return 1
        ihlaller.extend(sonuc)

    print(f"\n{'=' * 90}")
    if ihlaller:
        print(f"{len(ihlaller)} İHLAL BULUNDU:\n")
        for msg in ihlaller:
            print(f"  - {msg}")
        print(f"\n{'=' * 90}")
        return 1

    print("İhlal bulunamadı: cümle sayısı, kaynaklar, çelişkiler ve dil temiz.")
    print("=" * 90)
    return 0


# ------------------------------------------------------------- yapısal denetim


def _yapisal_kontrol(symbol: str, ozet: dict, analysis: dict) -> list[str]:
    """Tek şirket için yapısal değişmezleri kontrol eder."""
    msgs = []
    cumleler = ozet["sentences"]

    # "4-6 cümle" tasarımın hedefi, katı bir zorunluluk değil: her cümle
    # kendi verisi varsa üretilir, yoksa atlanır (bkz. narrative.py docstring).
    # Az veri içeren küçük/holding şirketlerde (ör. ENPRA — hiç mali tablo
    # alanı yok) 1-3 cümle tamamen beklenen bir sonuçtur; bunu "ihlal" say-
    # mak evrenin ~%15'ini yanlışlıkla "hatalı" işaretlerdi. Bilgi olarak
    # ayrı sayılıyor, çağıran taraf ihlallere eklemiyor.
    if len(cumleler) > 6:
        msgs.append(
            f"{symbol}: cümle sayısı {len(cumleler)} (6 üstü — tavan aşıldı)"
        )

    onceki_sira = 0
    for cumle in cumleler:
        if cumle["order"] != onceki_sira + 1:
            msgs.append(f"{symbol}: cümle sırası bozuk ({cumle['rule_id']} → {cumle['order']})")
        onceki_sira = cumle["order"]

        # NAR_VERI_NOTU ve NAR_BANKA_KAPSAM kasıtlı olarak kaynaksız: ikisi de
        # belirli bir sayıya değil, bir kategoriye ("bu bir banka", "şu kalem
        # eksik") işaret ediyor — tekil bir kaynak kalemi yok.
        if not cumle.get("sources") and cumle["rule_id"] not in (
            "NAR_VERI_NOTU", "NAR_BANKA_KAPSAM"
        ):
            msgs.append(f"{symbol}: {cumle['rule_id']} kaynaksız")

        metin = cumle["text"]
        for desen, sebep in YASAK:
            if re.search(desen, metin.lower()):
                msgs.append(f"{symbol}: {cumle['rule_id']} yasak dil içeriyor ({sebep})")

        sizinti = _nokta_ondalik_sizintisi(metin)
        if sizinti:
            msgs.append(
                f"{symbol}: {cumle['rule_id']} nokta ondalık sızıntısı: {sizinti!r}"
            )
        if EKSI_SIFIR.search(metin):
            msgs.append(f"{symbol}: {cumle['rule_id']} eksi sıfır sızıntısı")
        if NONE_SIZINTISI.search(metin):
            msgs.append(f"{symbol}: {cumle['rule_id']} None sızıntısı")

        # "Değişmedi" derken skor farkı sıfır olmayabilir — NETCD vakasının
        # kalıcı regresyon testi. DİKKAT: narrative.py ilk/son noktayı değil,
        # `_karsilastirilabilir_ikili()`'nin seçtiği (eşit kapsamlı) çifti
        # kullanıyor — ilk denemede burada da ilk/son karşılaştırıp MAGEN/
        # CMENT/KRSTL gibi 7 şirkette sahte ihlal üretmiştim. Aynı seçim
        # fonksiyonu burada da kullanılmalı, yoksa denetim aracı narrative.py
        # ile aynı çifte bakmamış olur.
        if cumle["rule_id"] == "NAR_FSKOR" and "değişmedi" in metin:
            fscore = analysis.get("fscore") or {}
            noktalar = fscore.get("usable_points") or []
            if len(noktalar) >= 2:
                ilk, son = N._karsilastirilabilir_ikili(noktalar)
                if ilk is not None and ilk["score"] != son["score"]:
                    msgs.append(
                        f"{symbol}: NAR_FSKOR 'değişmedi' diyor ama karşılaştırılan "
                        f"çiftte skor {ilk['score']}→{son['score']}"
                    )

    return msgs


# ------------------------------------------------------------- frekans denetimi


def _frekans_raporu(
    market: str, tur: str, metinler: dict[str, list[tuple[str, str]]], toplam: int,
    sessiz: bool = False,
) -> list[str]:
    """Bir rule_id'nin birebir aynı metinle çok sık çıkıp çıkmadığını denetler."""
    ihlaller = []
    if not sessiz:
        print(f"\n[{market}] {tur} frekans tablosu:")
    for rule_id, kayitlar in sorted(metinler.items()):
        n = len(kayitlar)
        birebir: dict[str, int] = {}
        for _, metin in kayitlar:
            # Tarihleri ve sayıları maskeleyip "kalıp" bazında say — sadece
            # gerçekten kelimesi kelimesine aynı metinler gürültü sayılır,
            # sayıları farklı ama yapısı aynı cümleler değil.
            birebir[metin] = birebir.get(metin, 0) + 1

        en_sik = max(birebir.values()) if birebir else 0
        oran = en_sik / toplam if toplam else 0.0
        if not sessiz:
            print(f"   {rule_id:24s} {n:4d} şirkette çıktı, en sık tekrar: "
                  f"{en_sik} ({oran * 100:.1f}%)")

        if oran > COK_SIK_AYNI:
            ornek_metin = max(birebir, key=birebir.get)
            ihlaller.append(
                f"{tur} {rule_id}: birebir aynı metin şirketlerin %{oran * 100:.0f}'inde "
                f"tekrarlanıyor — gürültü olabilir. Örnek: {ornek_metin[:100]!r}"
            )
    return ihlaller


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
