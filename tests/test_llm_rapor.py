"""LLM raporu testi.

`bicimlendir()` saf bir fonksiyon olduğu için sentetik bir paketle ağsız test
edilebiliyor — asıl amaç bu ayrımı korumak: rapor üretimi (`olustur`, ağ
gerektirir) ile biçimlendirme (`bicimlendir`, ağsız) birbirinden bağımsız
kalmalı ki testler önbellek olmadan da anlamlı kalsın.

`admin_dogrula` üç durumu (anahtar yok / yanlış / doğru) doğrudan `server`
modülünden çağrılarak test edilir — sunucuyu ayağa kaldırmadan, port
bağlamadan; `server.py`'yi import etmek yalnızca nesneleri kurar.
"""

from __future__ import annotations

import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from core import llm_rapor as LLM  # noqa: E402
from core import context as C  # noqa: E402
from core.yahoo import YahooClient  # noqa: E402

_client = None


def _c() -> YahooClient:
    global _client
    if _client is None:
        _client = YahooClient()
    return _client


def _sentetik_paket() -> dict:
    """Gerçekçi ama küçük bir paket — tüm bölümleri tetikleyecek kadar dolu."""
    return {
        "symbol": "TEST.IS",
        "market": "bist",
        "profil": {
            "ad": "Test Anonim Şirketi", "sektor": "Industrials", "endustri": "Test",
            "tablo_para": "TRY", "fiyat_para": "TRY", "fiyat": 12.5,
            "piyasa_degeri": 5_000_000_000, "piyasa_degeri_guvenilir": True,
            "piyasa_degeri_notu": None,
        },
        "banka_muhasebesi": False,
        "freshness": {
            "latest_period": "2025-12-31", "label": "3 ay önce", "level": "taze",
            "annual_stale": False, "last_annual": "2025-12-31",
        },
        "ozet": {
            "sentences": [
                {"rule_id": "NAR_REEL_BUYUME", "text": "Gelir nominal %10 arttı.",
                 "sources": [{"item": "TotalRevenue", "period": "2025-12-31"}]},
            ],
            "data_quality": {
                "missing_items": ["EBITDA"], "currency_verified": True,
                "tms29_boundary_crossed": False, "cpi_available": True,
            },
        },
        "bayraklar": {
            "flags": [{"id": "R1_KAR_NAKDE_DONMUYOR", "level": "kirmizi",
                       "title": "Kâr nakde dönmüyor", "explanation": "Test açıklaması."}],
            "notes": [],
            "not_applied": [{"id": "R3_BORC_SIKISMASI", "skip_reason": "veri yok"}],
        },
        "fscore": {
            "latest": {
                "score": 6, "date": "2025-12-31", "label": "6/9",
                "criteria": [
                    {"id": "ROA_POZITIF", "passed": True, "status": "ok", "detail": "ROA = %5,0"},
                    {"id": "CFO_POZITIF", "passed": False, "status": "ok", "detail": "CFO negatif"},
                ],
            },
            "usable_points": [
                {"date": "2024-12-31", "score": 5}, {"date": "2025-12-31", "score": 6},
            ],
            "model_note": None,
        },
        "baglam": [
            {"metric": "fscore", "label": "F-Skoru", "available": True, "value": 6,
             "trend": {"direction": "artış"}, "sector_median": 5, "sector_n": 40,
             "sector_percentile": 70, "universe_percentile": 65},
            {"metric": "net_debt_ebitda", "label": "Net borç/FAVÖK", "not_applicable": True},
        ],
        "baglam_var": True,
        "kalite": {
            "fscore": [{"date": "2024-12-31", "value": 5}, {"date": "2025-12-31", "value": 6}],
            "summary": {"rule_id": "QT_OZET", "text": "F-Skoru 5'ten 6'ya çıktı."},
            "axis_note": "3 nokta.",
        },
        "rapor": {
            "currency": "TRY",
            "quarterly": {
                "available": True, "current_date": "2026-03-31", "compare_date": "2025-03-31",
                "lines": [
                    {"key": "TotalRevenue", "label": "Gelir", "value": 1_000_000,
                     "yoy": {"pct": 0.1}},
                ],
                "comments": [{"rule_id": "REP_GELIR_NOMINAL", "text": "Gelir arttı."}],
            },
        },
    }


def test_bolumler_var():
    metin = LLM.bicimlendir(_sentetik_paket())
    beklenen_basliklar = (
        "## Kimlik", "## Veri tazeliği", "## Kural tabanlı özet", "## Bayraklar",
        "## Piotroski F-Skoru", "## Metrikler ve sektör bağlamı",
        "## Kalite zaman çizgisi", "## Son çeyrek", "## Veri kalitesi notları",
        "## Yöntem notları",
    )
    for baslik in beklenen_basliklar:
        assert baslik in metin, f"eksik bölüm: {baslik}"
    assert "yatırım tavsiyesi vermez" in metin
    assert "TEST.IS" in metin


def test_ondalik_ayraci_turkce():
    """İngilizce ondalık noktası (ör. '5.2') sızmamalı."""
    metin = LLM.bicimlendir(_sentetik_paket())
    ingilizce_ondalik = re.findall(r"(?<!\d)\d+\.\d{1,2}(?!\d)", metin)
    assert not ingilizce_ondalik, f"İngilizce ondalık sızıntısı: {ingilizce_ondalik}"


def test_sektorde_tanimsiz_metrik_isaretleniyor():
    metin = LLM.bicimlendir(_sentetik_paket())
    assert "sektörde tanımsız" in metin


def test_bos_kalite_bolumu_atlaniyor():
    """1 F-Skoru noktası + özet yoksa Kalite zaman çizgisi hiç basılmamalı."""
    paket = _sentetik_paket()
    paket["kalite"] = {"fscore": [{"date": "2025-12-31", "value": 6}], "summary": {}}
    metin = LLM.bicimlendir(paket)
    assert "## Kalite zaman çizgisi" not in metin


def test_admin_kapisi():
    import server

    # anahtar yapılandırılmamışsa geçer
    onceki = server.INF.load_config
    try:
        server.INF.load_config = lambda: {}
        server.admin_dogrula({})

        server.INF.load_config = lambda: {"admin_anahtari": "gizli"}
        try:
            server.admin_dogrula({})
            assert False, "anahtarsız geçmemeliydi"
        except server.ApiError as e:
            assert e.status == 403

        try:
            server.admin_dogrula({"X-Admin-Anahtar": "yanlis"})
            assert False, "yanlış anahtarla geçmemeliydi"
        except server.ApiError as e:
            assert e.status == 403

        server.admin_dogrula({"X-Admin-Anahtar": "gizli"})  # hata atmamalı
    finally:
        server.INF.load_config = onceki


def test_onbellekten_smoke():
    """Gerçek önbellekte veri varsa uçtan uca üretim de dener.

    Bağlam yoksa (ilk kurulum, ağsız makine) sessizce erken döner — koşucuda
    skip mekanizması yok, bu bilinçli bir ödünleşim (bkz. test_anlati.py).
    """
    if not C.load_context(_c(), "bist", ttl=None):
        return
    metin = LLM.olustur(_c(), "SISE.IS")
    assert metin.startswith("# SISE.IS")
    assert "## Kimlik" in metin
