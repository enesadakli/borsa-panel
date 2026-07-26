"""Anlatı denetim testi — tools/anlati_denetim.py'nin kalıcı hâli.

`python tools/anlati_denetim.py bist us` elle çalıştırıldığında 616+500
şirket üzerinde sıfır ihlal buldu (26 Temmuz 2026). Bu testler o denetimi
sabitler: bir sonraki değişiklik narrative.py/reports.py'de yeni bir gürültü
ya da çelişki üretirse test kırmızı yanar.

Bağlam önbelleği yoksa (ilk kurulum, `python tools/tarama.py` hiç
çalıştırılmamış) testler atlanır — ağsız bir makinede süiti kırmasın diye.
Atlama sessiz değildir: `tests/run.py` çıktısında "geçti" olarak görünür ama
gerçekte hiçbir şey doğrulanmamıştır; bu bilinçli bir ödünleşim.
"""

from __future__ import annotations

import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from core import context as C  # noqa: E402
from core.yahoo import YahooClient  # noqa: E402
from tools import anlati_denetim as A  # noqa: E402

_client = None


def _c() -> YahooClient:
    global _client
    if _client is None:
        _client = YahooClient()
    return _client


def _baglam_var(market: str) -> bool:
    return C.load_context(_c(), market, ttl=None) is not None


def test_bist_anlati_ihlalsiz():
    if not _baglam_var("bist"):
        return  # tarama yapılmamış, ağsız ortamda süiti kırma
    ihlaller = A.denetle_evren(_c(), "bist", sessiz=True)
    assert ihlaller == [], "BIST anlatı denetimi ihlal buldu:\n   " + "\n   ".join(ihlaller)


def test_us_anlati_ihlalsiz():
    if not _baglam_var("us"):
        return
    ihlaller = A.denetle_evren(_c(), "us", sessiz=True)
    assert ihlaller == [], "ABD anlatı denetimi ihlal buldu:\n   " + "\n   ".join(ihlaller)


# --------------------------------------------------------- yardımcı fonksiyon testleri


def test_nokta_ondalik_turkce_binlik_grubu_yakalamiyor():
    """Asıl hata: '%+1.281,1' geçerli Türkçe biçimdir, '1.281' 3 basamaklı
    binlik grubudur — İngilizce ondalık değil. İlk sürüm bunu 27 şirkette
    yanlışlıkla sızıntı sayıyordu (HEDEF.IS, KCHOL.IS, TERA.IS, ...).
    """
    assert A._nokta_ondalik_sizintisi("Gelir %+1.281,1 değişti") is None
    assert A._nokta_ondalik_sizintisi("değer 12.345.678 oldu") is None

    # Gerçek sızıntılar: 1-2 basamaklı veya 3'ten farklı uzunlukta.
    assert A._nokta_ondalik_sizintisi("F-Skoru 9.00 oldu") == "9.00"
    assert A._nokta_ondalik_sizintisi("marj %12.7 oldu") == "12.7"


def test_banka_kapsam_kaynaksizlik_ihlal_sayilmiyor():
    """NAR_BANKA_KAPSAM ve NAR_VERI_NOTU kasıtlı olarak kaynaksız — bunlar
    tekil bir sayıya değil bir kategoriye işaret ediyor."""
    ozet = {
        "sentences": [
            {"rule_id": "NAR_BANKA_KAPSAM", "order": 1, "sources": [], "text": "x"},
        ]
    }
    msgs = A._yapisal_kontrol("TEST.IS", ozet, {})
    assert not any("kaynaksız" in m for m in msgs)


def test_fskor_degismedi_karsilastirilabilir_cifti_kullaniyor():
    """MAGEN.IS vakası: narrative.py ilk/son noktayı değil, eşit kapsamlı
    (karşılaştırılabilir) çifti kullanıyor. Denetim aracı da aynı çifte
    bakmalı — ilk sürüm ilk/son'a bakıp 7 şirkette sahte ihlal üretmişti.
    """
    # İlk nokta (2023) farklı kapsamda (evaluated=7, score=3); son iki nokta
    # (2024, 2025) eşit kapsamda (evaluated=9) ve skorları eşit (4). Narrative
    # bu ikisini karşılaştırıp "değişmedi" der — ki bu doğrudur.
    analysis = {
        "fscore": {
            "usable_points": [
                {"date": "2023-12-31", "score": 3, "evaluated": 7, "criteria": []},
                {"date": "2024-12-31", "score": 4, "evaluated": 9, "criteria": []},
                {"date": "2025-12-31", "score": 4, "evaluated": 9, "criteria": []},
            ]
        }
    }
    ozet = {
        "sentences": [
            {
                "rule_id": "NAR_FSKOR", "order": 1, "sources": [{"item": "x", "period": "y"}],
                "text": "F-Skoru 2024 yılında 4/9 iken 2025 yılında 4/9. "
                        "Kriterlerin geçme/kalma durumu değişmedi.",
            },
        ]
    }
    msgs = A._yapisal_kontrol("MAGEN.IS", ozet, analysis)
    assert not any("değişmedi" in m and "diyor ama" in m for m in msgs), (
        f"karşılaştırılabilir çift kullanılmalıydı, sahte ihlal üretildi: {msgs}"
    )


def test_fskor_gercek_celiski_yakalaniyor():
    """Karşılaştırılabilir çiftin skoru gerçekten farklıysa (kod hatası
    sonucu) 'değişmedi' cümlesi hâlâ çelişki olarak yakalanmalı — pozitif
    kontrol, testin kendisi köreltilmemiş."""
    analysis = {
        "fscore": {
            "usable_points": [
                {"date": "2024-12-31", "score": 4, "evaluated": 9, "criteria": []},
                {"date": "2025-12-31", "score": 7, "evaluated": 9, "criteria": []},
            ]
        }
    }
    ozet = {
        "sentences": [
            {
                "rule_id": "NAR_FSKOR", "order": 1, "sources": [{"item": "x", "period": "y"}],
                "text": "F-Skoru 2024 yılında 4/9 iken 2025 yılında 7/9. "
                        "Kriterlerin geçme/kalma durumu değişmedi.",
            },
        ]
    }
    msgs = A._yapisal_kontrol("SAHTE.IS", ozet, analysis)
    assert any("diyor ama" in m for m in msgs), "gerçek çelişki yakalanmadı"
