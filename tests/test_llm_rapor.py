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

import copy
import inspect
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
        },
        # `olustur()` bunu `ozet.get("data_quality")`'den okuyup üst düzeye
        # taşıyor (bkz. llm_rapor.py:80); tüketiciler (`_ozet_blok`,
        # `_veri_kalitesi`) hep üst düzeyden okur. Burada da üst düzeyde
        # olmalı — bir ara `ozet` içine gömülüydü ve dört dal hiç tetiklenmedi.
        "data_quality": {
            "missing_items": ["EBITDA"], "currency_verified": True,
            "tms29_boundary_crossed": False, "cpi_available": True,
        },
        "bayraklar": {
            "flags": [{"id": "R1_KAR_NAKDE_DONMUYOR", "level": "kirmizi",
                       "title": "Kâr nakde dönmüyor", "explanation": "Test açıklaması."}],
            "notes": [],
            "not_applied": [{"id": "R3_BORC_SIKISMASI", "skip_reason": "veri yok"}],
            "red_count": 1, "yellow_count": 0,
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
        "metrikler": [
            {"metric": "fscore", "label": "F-Skoru", "value": 6, "trend": "artış",
             "sector_median": 5, "sector_n": 40, "sector_percentile": 70,
             "universe_median": 5, "universe_percentile": 65},
            {"metric": "roe", "label": "ROE", "value": 0.084},
            {"metric": "net_debt_ebitda", "label": "Net borç/FAVÖK",
             "not_applicable": True},
            {"metric": "pe", "label": "F/K", "value": None},
        ],
        "baglam_var": True,
        "baglam_yasi_saat": 26.0,
        "altman": {
            "value": 1.67, "status": "ok", "detail": "Z = 1,67", "sources": [],
            "zone": "sıkışma bölgesi",
            "components": {"X1": 0.12, "X2": 0.31, "X3": 0.04, "X4": 0.55, "X5": 0.43},
        },
        "degerleme": {
            "pe": {"value": 12.7, "status": "ok", "detail": "12,69 (TTM kâr tabanlı)",
                   "sources": [], "basis": "TTM"},
            "pb": {"value": 0.5, "status": "ok", "detail": "0,50 (çeyrek özsermaye tabanlı)",
                   "sources": [], "basis": "çeyrek"},
            "market_cap_statement_currency": 128_560_000_000, "currency": "TRY",
            "converted": False,
        },
        "getiriler": {
            "roe": {"value": 0.039, "status": "ok", "detail": "%3,9 (TTM kâr)",
                    "sources": []},
            "roa": {"value": 0.019, "status": "ok", "detail": "%1,9", "sources": []},
        },
        "marjlar": {
            "series": {
                "gross": [("2024-12-31", 22.6), ("2025-12-31", 27.6)],
                "operating": [("2024-12-31", 5.1), ("2025-12-31", 0.0)],
                "net": [("2024-12-31", 3.0), ("2025-12-31", 4.4)],
            },
            "operating_trend": {"value": -4.8, "status": "ok",
                                "detail": "Yılda -4,8 puan", "sources": [],
                                "direction": "daralma"},
        },
        "borc": {
            "debt_to_equity": {"value": 0.66, "status": "ok",
                               "detail": "0,66", "sources": []},
            "net_debt_ebitda": {"value": 2.2, "status": "ok",
                                "detail": "2,20 (TTM FAVÖK)",
                                "sources": []},
            "nwc_change": {"value": -0.592, "status": "ok",
                           "detail": "Bir önceki yıla göre %-59,2 "
                                     "(cari varlık − cari yükümlülük)",
                           "sources": []},
            "history": [
                {"date": "2024-12-31", "net_debt": 100_920_000_000,
                 "ebitda": 53_430_000_000, "net_debt_ebitda": 1.89},
                {"date": "2025-12-31", "net_debt": 123_780_000_000,
                 "ebitda": 57_450_000_000, "net_debt_ebitda": 2.15},
            ],
        },
        "kar_kalitesi": {
            "fcf_gap": {"value": 0.604, "status": "ok",
                        "detail": "Net kârın %60 kadarı nakde dönmemiş", "sources": []},
            "accrual_ratio": {"value": None, "status": "eksik_veri",
                              "detail": "Veri yok", "sources": []},
            "fcf_margin": {"value": 0.017, "status": "ok",
                           "detail": "Gelirin %1,7 kadarı serbest nakde dönüşmüş",
                           "sources": []},
            "fcf_payout": {"value": 0.673, "status": "ok",
                           "detail": "Serbest nakit akışının %67,3 kadarı "
                                     "temettü olarak dağıtılmış",
                           "sources": []},
            "history": [
                {"date": "2025-12-31", "net_income": 9_880_000_000,
                 "operating_cash_flow": 39_730_000_000,
                 "free_cash_flow": 3_900_000_000},
            ],
        },
        "reel_buyume": {
            "revenue": {
                "real": -0.315, "nominal": -0.076, "cpi_growth": 0.349,
                "label": "TÜFE (Dünya Bankası, yıllık ortalama)", "sources": [],
                "history": [
                    {"date": "2024-12-31", "real": -0.302, "cpi_growth": 0.484},
                    {"date": "2025-12-31", "real": -0.315, "cpi_growth": 0.349},
                ],
            },
            "net_income": {"real": 0.114, "nominal": 0.503, "cpi_growth": 0.349,
                           "sources": [], "history": []},
            "real_revenue_series": {
                "points": [("2024-12-31", 143_250_000_000),
                           ("2025-12-31", 138_660_000_000)],
                "base": "2025-12-31", "label": "TÜFE (Dünya Bankası)", "skipped": [],
            },
        },
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
                     "yoy": {"pct": 0.1}, "qoq": {"pct": -0.05}},
                ],
                "margins": {
                    "operating": {"label": "Faaliyet marjı", "now": 8.2, "before": 6.1,
                                  "delta": 2.1},
                },
                "comments": [{"rule_id": "REP_GELIR_NOMINAL", "text": "Gelir arttı."}],
            },
            "annual": {
                "available": True, "current_date": "2025-12-31", "compare_date": "2024-12-31",
                "lines": [
                    {"key": "TotalRevenue", "label": "Gelir", "value": 224_530_000_000,
                     "yoy": {"pct": -0.076}},
                ],
                "real_revenue": {"real": -0.315, "nominal": -0.076, "cpi_growth": 0.349},
                "comments": [{"rule_id": "REP_GELIR_REEL", "text": "Gelir reel küçüldü."}],
            },
        },
        "fiyat": {
            "available": True, "start": "2025-07-30", "end": "2026-07-27", "days": 252,
            "last": 43.62, "low": 32.88, "high": 52.35, "position": 0.55,
            "change": 0.176, "real_change": -0.128, "cpi_growth": 0.349,
            "annual_volatility": 0.386, "max_drawdown": -0.247, "currency": "TRY",
        },
        "piyasa": {
            "available": True, "market": "bist", "scanned": 616, "error_count": 0,
            "headline": [
                {"key": "fscore", "label": "Medyan F-Skoru", "value": 5.0, "n": 502,
                 "format": "score", "excludes_financials": False},
                {"key": "pozitif_fcf", "label": "Serbest nakit akışı pozitif olan şirket oranı",
                 "value": 0.537, "n": 501, "format": "share"},
            ],
            "sectors": [
                {"sector": "Industrials", "count": 122, "metrics": {
                    "fscore": {"label": "F-Skoru", "median": 5, "n": 111, "sufficient": True},
                }},
            ],
            "note": "Bu ekran evrenin sayısal fotoğrafını gösterir.",
        },
    }


# Kıyaslama matrisi fikstürü. Marjlar **puan** ölçeğinde (22,6 = %22,6),
# ROE/reel büyüme **kesir** ölçeğinde (0,039 = %3,9) — ikisinin farkı farklı
# biçimlendiriciden geçmeli, `test_karsilastirma_marj_farki_puan_olceginde`
# tam olarak bunu kilitliyor.
_METRIK_A = {
    "fscore": 7, "altman_z": 1.67, "roe": 0.039,
    "gross_margin": 22.6, "operating_margin": 8.2, "net_margin": 2.7,
    "net_debt_ebitda": 2.2, "real_revenue_growth": -0.315,
}
_METRIK_B = {
    "fscore": 5, "altman_z": 2.90, "roe": 0.061,
    "gross_margin": 18.0, "operating_margin": 4.0, "net_margin": 1.5,
    "net_debt_ebitda": 1.1, "real_revenue_growth": -0.120,
}


def test_fark_olcek_siniflari_metrikleri_eksiksiz_kapliyor():
    """`_fark`'ın üç ölçek kümesi `C.METRIKLER`'i tam örtmeli — iki yönde de.

    Bir metrik hiçbirinde yoksa `_fark` artık sessizce `B.yuzde`'ye düşmüyor,
    `ValueError` fırlatıyor (aşağıdaki pozitif kontrol). Bu test ise
    sürüklenmeyi commit zamanında yakalıyor: yeni metrik eklenip
    sınıflanmazsa, ya da silinen metriğin sınıfı unutulup kalırsa düşer.
    """
    beklenen = {k for k, _ in C.METRIKLER}
    siniflanan = set(LLM._FARK_SAYI) | LLM._FARK_PUAN | LLM._FARK_KESIR
    assert beklenen == siniflanan, (
        f"sınıflanmamış: {beklenen - siniflanan}; "
        f"fazladan sınıflanmış: {siniflanan - beklenen}"
    )


def test_fark_siniflanmamis_metrikte_sessizce_gecmiyor():
    """Pozitif kontrol: sınıflanmamış metrik `ValueError` ile durmalı.

    Geçmişte tam bu sessiz düşüş (`else: B.yuzde`) marj farkını 100 kat
    şişirmişti (bkz. `test_karsilastirma_marj_farki_puan_olceginde`).
    """
    try:
        LLM._fark("uydurma_metrik_boyle_biri_yok", 1.0, 2.0)
    except ValueError:
        pass
    else:
        raise AssertionError("sınıflanmamış metrik sessizce kabul edildi")


def test_metrik_bicim_metrikleri_eksiksiz_kapliyor():
    """`_METRIK_BICIM` de `C.METRIKLER`'i tam örtmeli.

    Bugün tam (16/16) ama onu orada tutan hiçbir mekanizma yoktu; bu test
    o örtüşmeyi kalıcı hâle getiriyor.
    """
    beklenen = {k for k, _ in C.METRIKLER}
    assert beklenen == set(LLM._METRIK_BICIM), (
        f"eksik: {beklenen - set(LLM._METRIK_BICIM)}; "
        f"fazla: {set(LLM._METRIK_BICIM) - beklenen}"
    )


def test_karsilastirma_marj_farki_puan_olceginde():
    """Marj farkı 100 kat şişmemeli.

    `context.extract_metrics` marj serisini `×100` yaparak alır, yani değer
    zaten puan cinsindedir. Farkına `B.yuzde` uygulanırsa 22,6 − 18,0 = 4,6
    puanlık gerçek fark "%+460,0" diye basılıyordu.
    """
    satirlar = LLM.kiyaslama_matrisi("A.IS", "B.IS", _METRIK_A, _METRIK_B)
    metin = "\n".join(satirlar)
    assert "%+4,6 puan" in metin, "brüt marj farkı puan ölçeğinde olmalı"
    assert "460" not in metin, "marj farkı 100 katına çıkmış"
    # Kesir ölçekli metrikler yüzdeye çevrilmeye devam etmeli: 0,039 − 0,061
    assert "%-2,2 puan" in metin, "ROE farkı kesirden yüzdeye çevrilmeli"


def test_karsilastirma_tek_tarafli_metrigi_atlamiyor():
    """Bir tarafta değer varsa satır basılmalı, fark sütunu `—` olmalı."""
    satirlar = LLM.kiyaslama_matrisi("A.IS", "B.IS", {"pe": 8.4}, {})
    metin = "\n".join(satirlar)
    assert "F/K" in metin and "—" in metin


def test_capraz_inceleme_marj_seviyesini_okuyor():
    """Kural marj **seviyesini** okumalı, trend eğimini değil.

    `marjlar["*_trend"]["value"]` alanı `health._slope()` çıktısıdır (yılda
    kaç puan değişim); marj seviyesi yalnızca `series`te durur. Eğim okununca
    kural pratikte hiç tetiklenmiyordu.
    """
    paket = {"marjlar": {
        "series": {"gross": [("2025-12-31", 27.6)], "operating": [("2025-12-31", 0.0)]},
        # Eğim değerleri kasıtlı olarak eşiği geçecek şekilde yanıltıcı:
        # kural bunları okursa test düşer.
        "gross_trend": {"value": 99.0, "status": "ok"},
        "operating_trend": {"value": -4.8, "status": "ok"},
    }}
    metin = "\n".join(LLM._capraz_inceleme(paket))
    assert "## Çapraz İnceleme Notları" in metin
    assert "%27,6" in metin and "%0,0" in metin, "marj seviyeleri basılmalı"
    assert "99" not in metin, "eğim değeri marj sanılmış"


def test_capraz_inceleme_nakit_celiskisi():
    """Kâr büyürken serbest nakit akışı negatifse not düşülmeli."""
    paket = {
        "rapor": {"annual": {"lines": [{"key": "NetIncome", "yoy": {"pct": 0.42}}]}},
        "kar_kalitesi": {"history": [{"free_cash_flow": -1_200_000_000}]},
    }
    metin = "\n".join(LLM._capraz_inceleme(paket))
    assert "Nakit kalitesi çelişkisi" in metin
    assert "%+42,0" in metin


def test_capraz_inceleme_kural_yoksa_bolum_yok():
    """Hiçbir kural tetiklenmezse başlık da basılmamalı (boş bölüm olmasın)."""
    paket = {"marjlar": {"series": {"gross": [("2025-12-31", 30.0)],
                                    "operating": [("2025-12-31", 25.0)]}}}
    assert LLM._capraz_inceleme(paket) == []


def test_ozet_ve_veri_kalitesi_fiksturle_ayni_seyi_soyluyor():
    """Özet bloğu ve Veri kalitesi bölümü, fikstürün kendi verisiyle çelişmemeli.

    Bir ara `data_quality` fikstürde `ozet` içine gömülüydü; `olustur()`
    üst düzeye koyuyor (`llm_rapor.py:80`) ve tüketiciler üst düzeyden okuyor
    (`_ozet_blok:624`, `_veri_kalitesi:1063`). Yanlış yerdeyken bölümler
    `paket.get("data_quality")` üzerinden hep `{}` görüyordu; fikstür
    "1 kalem eksik, TÜFE var" dediği hâlde rapor "0 kalem eksik, TÜFE yok"
    basıyordu ve hiçbir assert bunu yakalamıyordu.
    """
    metin = LLM.bicimlendir(_sentetik_paket())
    assert "- Veri: 1 kalem eksik · TÜFE var · sektör bağlamı var" in metin
    assert "- Tetiklenen bayrak: 1 kırmızı, 0 sarı" in metin


def test_veri_kalitesi_dort_dali_da_tetikleniyor():
    """`_veri_kalitesi`'nin 4 gerçek dalı tek tek çalıştırılmalı.

    Ana fikstür hepsi temiz bir şirketi temsil ediyor (`test_dil` ve diğer
    ~15 testin üzerine kurulu olduğu şey); onu bozuk veriye çevirmek o
    testleri çarpıtır. Bunun yerine kopyasını al, tek bayrağı çevir.
    """
    taban = _sentetik_paket()

    eksik_kalemli = copy.deepcopy(taban)
    eksik_kalemli["data_quality"]["missing_items"] = ["EBITDA", "TotalDebt"]
    metin = LLM.bicimlendir(eksik_kalemli, bolumler=["veri_kalitesi"])
    assert "Yahoo'dan gelmeyen kalemler: EBITDA, TotalDebt" in metin

    para_dogrulanmamis = copy.deepcopy(taban)
    para_dogrulanmamis["data_quality"]["currency_verified"] = False
    metin = LLM.bicimlendir(para_dogrulanmamis, bolumler=["veri_kalitesi"])
    assert "para birimi kesin doğrulanamadı" in metin

    tufe_yok = copy.deepcopy(taban)
    tufe_yok["data_quality"]["cpi_available"] = False
    metin = LLM.bicimlendir(tufe_yok, bolumler=["veri_kalitesi"])
    assert "TÜFE serisi yok" in metin

    tms29_sinirinda = copy.deepcopy(taban)
    tms29_sinirinda["data_quality"]["tms29_boundary_crossed"] = True
    metin = LLM.bicimlendir(tms29_sinirinda, bolumler=["veri_kalitesi"])
    assert "TMS-29" in metin

    # Taban fikstür kasıtlı olarak 1 eksik kalem taşıyor (Adım 1: Özet ve Veri
    # kalitesi aynı şeyi söylesin diye) — "sorun yok" dalı için ayrıca
    # gerçekten temiz bir varyant gerekiyor.
    tertemiz = copy.deepcopy(taban)
    tertemiz["data_quality"]["missing_items"] = []
    temiz = LLM.bicimlendir(tertemiz, bolumler=["veri_kalitesi"])
    assert "Bilinen bir veri kalitesi sorunu yok" in temiz


def test_nakit_metrikleri_raporda_gorunuyor():
    """FCF marjı, temettü karşılığı ve NWC değişimi rapora basılmalı.

    Üçü de `health.py`'de hesaplanıyordu ama uzun süre hiçbir yüzey okumuyordu
    (ölü kod). Bu test onları bağlı tutuyor: biri satır listesinden düşerse
    hesap sağlam kalsa bile rapor sessizce eksilir.
    """
    metin = LLM.bicimlendir(_sentetik_paket())
    for etiket in ("FCF marjı", "Temettünün nakit karşılığı",
                   "İşletme sermayesi değişimi"):
        assert etiket in metin, f"{etiket} raporda yok"


# `- Etiket: detay` satırlarını yakalayan tarama. `_metrik_node` bu kalıpla
# basıyor; `health.py`'de canlı SISE.IS raporunda 7 satır kendi etiketini
# tekrarladığı bulundu (ör. "- F/K: F/K = 12,20 ..."). Etiketin sonundaki
# parantezli kısım atılıyor ("Tahakkuk oranı (Sloan)" → "Tahakkuk oranı")
# çünkü detay metni parantezsiz köke bakıyor.
_ETIKET_SATIRI = re.compile(r"^- ([^:\n]{2,60}): (.+)$", re.MULTILINE)
_PARANTEZ_SONU = re.compile(r"^(.*?)\s*\([^()]*\)$")


def _etiket_tekrarlari(metin: str) -> list[str]:
    bulunanlar = []
    for etiket, detay in _ETIKET_SATIRI.findall(metin):
        eslesme = _PARANTEZ_SONU.match(etiket)
        temel = eslesme.group(1).strip() if eslesme else etiket
        if temel and detay.startswith(temel):
            bulunanlar.append(f"- {etiket}: {detay}")
    return bulunanlar


def test_etiket_tekrari_taramasi_gercek_ihlali_yakaliyor():
    """Pozitif kontrol: tarama gerçekten bir tekrarı fark ediyor mu?

    Bu geçmezse asıl test hiçbir şeyi yakalamıyor olabilir, geçmesi güven
    vermez (bkz. `test_bicim_lint.py:test_kalip_gercek_ihlali_yakaliyor`
    ile aynı gerekçe).
    """
    sahte = "- F/K: F/K = 12,20 (TTM kâr tabanlı)\n- Özsermaye durumu: Özsermaye pozitif\n"
    bulunan = _etiket_tekrarlari(sahte)
    assert bulunan == ["- F/K: F/K = 12,20 (TTM kâr tabanlı)"], bulunan


def test_metrik_satirlari_etiketi_tekrarlamiyor():
    """Hiçbir bölüm kendi etiketini tekrarlamamalı — tam render ve her
    `bolumler=[ad]` render'ı ayrı ayrı taranıyor, hiçbiri kaçmasın."""
    paket = _sentetik_paket()
    tekrarlar = _etiket_tekrarlari(LLM.bicimlendir(paket))
    for ad in LLM.BOLUM_ADLARI:
        tekrarlar.extend(_etiket_tekrarlari(LLM.bicimlendir(paket, bolumler=[ad])))
    assert not tekrarlar, "Etiket tekrarı bulundu:\n" + "\n".join(sorted(set(tekrarlar)))


def test_tum_bolumler_fikstur_tarafindan_tetikleniyor():
    """Kaynaktaki her `## ` başlığı fikstürle üretilebilmeli.

    Sabit bir "beklenen başlıklar" listesi çürümeye açıktı: yeni bir bölüm
    eklenip fikstür güncellenmeyince o bölüm sessizce hiç test edilmemiş
    oluyordu. Bu test başlıkları kaynaktan keşfediyor (test_dil ve
    test_bicim_lint'in dinamik dosya keşfiyle aynı ruh), böylece yeni bölüm
    fikstüre girene kadar süit kırmızı yanıyor.

    Şart: başlıklar düz string sabiti olmalı, f-string olursa regex görmez.

    Modülün iki ayrı üretim yüzeyi var — `bicimlendir()` (tek şirket) ve
    `kiyaslama_matrisi()` (iki şirket). Başlık ikisinden birinde çıkıyorsa
    yeterli; yoksa `## Kıyaslama Matrisi` hiçbir zaman tetiklenemezdi.
    """
    kaynak = inspect.getsource(LLM)
    basliklar = set(re.findall(r'"(## [^"]+)"', kaynak))
    assert basliklar, "kaynakta hiç bölüm başlığı bulunamadı — regex bozulmuş olabilir"

    uretilen = "\n".join([
        LLM.bicimlendir(_sentetik_paket()),
        "\n".join(LLM.kiyaslama_matrisi("A.IS", "B.IS", _METRIK_A, _METRIK_B)),
    ])
    eksik = sorted(b for b in basliklar if b not in uretilen)
    assert not eksik, f"fikstür şu bölümleri tetiklemiyor: {eksik}"


def test_zorunlu_alanlar_var():
    metin = LLM.bicimlendir(_sentetik_paket())
    assert "yatırım tavsiyesi vermez" in metin
    assert "TEST.IS" in metin
    assert metin.startswith("# TEST.IS")


def test_baglamsiz_paket_metrikleri_kaybetmiyor():
    """Asıl regresyon kilidi.

    v1'de metrikler yalnızca `all_metric_contexts()`'ten geliyordu; evren
    taranmamışsa ya da sembol tarama kaydında yoksa ROE/Altman/borç oranları
    rapordan tamamen düşüyordu. Artık analizden geliyorlar — tarama yalnızca
    karşılaştırma sütunlarını ekliyor.
    """
    paket = _sentetik_paket()
    paket["baglam_var"] = False
    paket["baglam_yasi_saat"] = None
    # tarama yok → karşılaştırma alanları hiç gelmez, değer ve trend kalır
    paket["metrikler"] = [
        {"metric": "fscore", "label": "F-Skoru", "value": 6, "trend": "artış"},
        {"metric": "roe", "label": "ROE", "value": 0.084},
        {"metric": "net_debt_ebitda", "label": "Net borç/FAVÖK", "not_applicable": True},
        {"metric": "pe", "label": "F/K", "value": None},
    ]
    metin = LLM.bicimlendir(paket)

    for beklenen in ("F-Skoru", "ROE", "Altman Z", "Borç profili", "Kâr kalitesi"):
        assert beklenen in metin, f"bağlamsız pakette kayboldu: {beklenen}"
    assert "%8,4" in metin, "ROE değeri basılmalı (tarama olmasa da)"
    assert "sektör bağlamı yok" in metin, "sebep Veri kalitesi'nde yazmalı"


def test_hesaplanamayan_metrik_atlanmiyor():
    """`eksik_veri` satırı sessizce düşmemeli — denenip başarısız olduğu görünmeli."""
    metin = LLM.bicimlendir(_sentetik_paket())
    assert "F/K: — (hesaplanamadı)" in metin


def test_karsilastirma_hazir_yazilmis():
    """8B model 'değer > medyan' çıkarımını kendisi yapmak zorunda kalmamalı."""
    metin = LLM.bicimlendir(_sentetik_paket())
    assert "medyanın üstünde" in metin or "medyanın altında" in metin


def test_bolum_filtresi():
    """`?bolum=` yalnızca istenen bölümü döndürmeli; başlık ve UYARI kalmalı."""
    metin = LLM.bicimlendir(_sentetik_paket(), bolumler=["borc"])
    assert "## Borç profili" in metin
    assert "## Kimlik" not in metin
    assert "## Piyasa bağlamı" not in metin
    assert metin.startswith("# TEST.IS")
    assert "yatırım tavsiyesi vermez" in metin
    assert len(metin) < len(LLM.bicimlendir(_sentetik_paket())) / 2


def test_fiyat_bolumu_sebepsiz_kaybolmuyor():
    """`fiyat.available = False` iken bölüm hiç iz bırakmadan silinmemeli.

    Eskiden `if not f.get("available"): return []` idi — 1108/1116 şirkette
    (fiyat serisi önbelleği doğrudan okunduğu için) bu dal tetikleniyor ve
    okuyucu "hiç sorulmamış" ile "sorulmuş, bulunamamış" ayrımını
    yapamıyordu. Artık başlık + sebep basılıyor.
    """
    paket = copy.deepcopy(_sentetik_paket())
    paket["fiyat"] = {"available": False, "reason": "Fiyat serisi çekilemedi (ağ/kaynak hatası)"}
    metin = LLM.bicimlendir(paket)
    assert "## Fiyat serisi" in metin
    assert "Bu bölüm hesaplanamadı: Fiyat serisi çekilemedi (ağ/kaynak hatası)" in metin


def test_fiyat_bolumu_paket_hic_yoksa_bos():
    """`fiyat` anahtarı hiç yoksa (hiç denenmemiş) bölüm hâlâ atlanabilir —
    bu, "denendi ama başarısız" ile "hiç işlenmedi" ayrımını korur."""
    paket = copy.deepcopy(_sentetik_paket())
    del paket["fiyat"]
    assert LLM._fiyat(paket) == []


def test_bolum_adlari_kaydi_eksiksiz():
    """Her bölüm üreticisi kayıtta olmalı — kayda girmeyen bölüm filtrelenemez."""
    kaynak = inspect.getsource(LLM)
    basliklar = set(re.findall(r'"(## [^"]+)"', kaynak))
    tam = LLM.bicimlendir(_sentetik_paket())
    tekil = [LLM.bicimlendir(_sentetik_paket(), bolumler=[ad]) for ad in LLM.BOLUM_ADLARI]
    birlesik = "\n".join(tekil)
    eksik = sorted(b for b in basliklar if b in tam and b not in birlesik)
    assert not eksik, f"BOLUMLER kaydında olmayan bölüm: {eksik}"


def test_tablolar_dar():
    """Hiçbir tablo 4 sütundan geniş olmamalı (geniş tabloda 8B satır kaydırıyor)."""
    metin = LLM.bicimlendir(_sentetik_paket())
    genis = [
        satir for satir in metin.splitlines()
        if satir.startswith("|") and satir.count("|") > 5
    ]
    assert not genis, f"4 sütundan geniş tablo satırı: {genis[:3]}"


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
