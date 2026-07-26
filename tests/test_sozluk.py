"""Sözlük kapsam testi.

Sözlüğün varlığı yetmez; arayüzün anahtar taşıyan her etiketi sözlükte
karşılık bulmalı, yoksa balon hiç çıkmaz ve eksik sessizce büyür. Bu test
üç anahtar uzayını (metrikler, F-Skoru kriterleri, tarayıcı alanları)
sözlüğe karşı kilitler.

Dil taraması ayrıca otomatik: core/sozluk.py, test_dil'in core/ taramasına
kendiliğinden girer — açıklamalarda yasak dil (değerleme yargısı, yönlendirme)
belirirse orası kırmızı yanar.
"""

from __future__ import annotations

import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from core import context as C  # noqa: E402
from core import health as H  # noqa: E402
from core import screener as S  # noqa: E402
from core.sozluk import SOZLUK, UYARI  # noqa: E402


def test_metrik_anahtarlari_sozlukte():
    """Her metrik sözlükte VE görünen ad context etiketiyle birebir aynı.

    Ad eşitliği kasıtlı olarak katı: 'Net borç / FAVÖK' vs 'Net borç/FAVÖK'
    türü sessiz kaymaları (F6'da yaşandı) kalıcı yakalar.
    """
    hatalar = []
    for anahtar, etiket in C.METRIKLER:
        giris = SOZLUK.get(anahtar)
        if giris is None:
            hatalar.append(f"{anahtar}: sözlükte yok")
        elif giris["ad"] != etiket:
            hatalar.append(f"{anahtar}: ad {giris['ad']!r} != context {etiket!r}")
    assert not hatalar, "Metrik/sözlük uyumsuz:\n   " + "\n   ".join(hatalar)


def test_kriter_anahtarlari_sozlukte():
    hatalar = []
    for kimlik, etiket in H.KRITERLER:
        giris = SOZLUK.get(kimlik)
        if giris is None:
            hatalar.append(f"{kimlik}: sözlükte yok")
        elif giris["ad"] != etiket:
            hatalar.append(f"{kimlik}: ad {giris['ad']!r} != health {etiket!r}")
    assert not hatalar, "Kriter/sözlük uyumsuz:\n   " + "\n   ".join(hatalar)


def test_tarayici_alanlari_sozlukte():
    eksik = [alan for alan in S.ALANLAR if alan not in SOZLUK]
    assert not eksik, f"Tarayıcı alanı sözlükte yok: {', '.join(eksik)}"


def test_genel_terimler_var():
    """Arayüzde elle bağlanan terimlerin çekirdek kümesi."""
    gerekli = (
        "reel", "nominal", "tufe", "ttm", "favok", "sektor_medyani",
        "yuzdelik_dilim", "tms29", "banka_muhasebesi",
        "volatilite", "beta", "hhi", "etkin_pozisyon", "korelasyon",
        "en_kotu_dusus", "agirlikli_fskor", "kapsam",
        "brut_kar", "faaliyet_kari", "faaliyet_nakit_akisi",
        "serbest_nakit_akisi", "net_borc", "ozsermaye",
    )
    eksik = [terim for terim in gerekli if terim not in SOZLUK]
    assert not eksik, f"Genel terim sözlükte yok: {', '.join(eksik)}"


def test_girisler_dolu():
    hatalar = []
    for anahtar, giris in SOZLUK.items():
        if not (giris.get("ad") or "").strip():
            hatalar.append(f"{anahtar}: ad boş")
        aciklama = (giris.get("aciklama") or "").strip()
        if not aciklama:
            hatalar.append(f"{anahtar}: açıklama boş")
        elif len(aciklama) > 400:
            hatalar.append(f"{anahtar}: açıklama {len(aciklama)} karakter (>400)")
    assert not hatalar, "Bozuk sözlük girişi:\n   " + "\n   ".join(hatalar)


def test_uyari_sozlukten_geliyor():
    """server.py kendi kopyasını tutmasın diye UYARI tek kaynaktan gelir."""
    import server

    assert server.UYARI is UYARI, "server.UYARI core.sozluk.UYARI'nın kendisi olmalı"
