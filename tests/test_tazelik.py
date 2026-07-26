"""Veri tazeliği testi (F1) + karşılaştırılabilir-ikili regresyon testi (F3/F4).

NETCD vakası: en son mali tablo 19 ay eskiyken F-Skoru "9/9" ekranda hiçbir
yaş uyarısı olmadan gösteriliyordu. `core.fundamentals._freshness()` ve
`core.flags._y7_veri_bayat()` bu sınıfı kapatıyor — burada sentetik
paketlerle yaş hesabı, eşik sınırları ve bayrağın tetiklenmesi doğrulanır.

Ayrı bir sınıf: F-Skoru zaman çizgisinde ilk/son noktayı körlemesine
kıyaslamak yanlış bir "ölçüm genişledi" notu ya da yanlış bir "değişmedi"
iddiası üretebilir. `core.narrative._karsilastirilabilir_ikili` bunu eşit
kapsamlı çift arayarak çözüyor; burada iki senaryo doğrudan `_nar_fskor`
üzerinden test ediliyor (yalnızca denetim aracı üzerinden değil).
"""

from __future__ import annotations

from datetime import date, timedelta

from core import flags as FL
from core import fundamentals as F
from core import health as H
from core import narrative as N

# --------------------------------------------------------------- yaş hesabı


def _paket(ay_once: float | None, ceyrek_ay_once: float | None = None) -> tuple[list, list]:
    """Belirtilen ay kadar önce biten sentetik yıllık/çeyreklik dönem(ler)."""
    bugun = date.today()

    def tarih(ay):
        if ay is None:
            return []
        gun = round(ay * F.GUN_AY)
        return [{"date": (bugun - timedelta(days=gun)).isoformat()}]

    return tarih(ay_once), tarih(ceyrek_ay_once)


def test_veri_yoksa_bilinmiyor():
    tazelik = F._freshness([], [])
    assert tazelik["level"] == "bilinmiyor"
    assert tazelik["age_months"] is None
    assert tazelik["label"] is None


def test_taze_esik_altinda():
    annual, quarterly = _paket(None, F.BAYAT_AY - 1)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["level"] == "taze"


def test_bayat_esik_tam_sinirinda():
    """Yaş tam BAYAT_AY'a eşitse (>=) tetiklenmeli — sınır dahil."""
    annual, quarterly = _paket(None, F.BAYAT_AY)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["level"] == "bayat"


def test_cok_bayat_esik_tam_sinirinda():
    annual, quarterly = _paket(None, F.COK_BAYAT_AY)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["level"] == "cok_bayat"


def test_bayat_ile_cok_bayat_arasi_hala_bayat():
    annual, quarterly = _paket(None, F.COK_BAYAT_AY - 1)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["level"] == "bayat"


def test_yillik_ayri_olarak_eskiyebilir():
    """Çeyreklik tablo taze olsa bile yıllık (F-Skoru'nun dayandığı) tablo
    ayrıca eski olabilir — annual_stale bunu bağımsız işaretlemeli."""
    annual, _ = _paket(F.YILLIK_BAYAT_AY, None)
    _, quarterly = _paket(None, 1)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["annual_stale"] is True
    assert tazelik["level"] == "taze", "en güncel dönem çeyrekten geliyor, genel seviye taze olmalı"


def test_en_yeni_donem_ikisinden_buyugu_seciyor():
    annual, quarterly = _paket(12, 3)
    tazelik = F._freshness(annual, quarterly)
    assert tazelik["latest_period"] == quarterly[0]["date"]
    assert tazelik["last_annual"] == annual[0]["date"]


# ---------------------------------------------------------- Y7 bayrağı (flags.py)


def test_y7_tetikleniyor_bayat_seviyesinde():
    analiz = {"freshness": {
        "level": "bayat", "latest_period": "2025-06-30", "label": "10 ay önce",
        "last_annual": "2024-12-31", "annual_age_months": 10, "annual_stale": False,
    }}
    sonuc = FL._y7_veri_bayat(analiz, None)
    assert sonuc["triggered"] is True
    assert sonuc["applied"] is True
    assert "2025-06-30" in sonuc["explanation"]


def test_y7_tetiklenmiyor_tazeyken():
    analiz = {"freshness": {"level": "taze", "latest_period": "2026-06-30"}}
    sonuc = FL._y7_veri_bayat(analiz, None)
    assert sonuc["triggered"] is False


def test_y7_uygulanmiyor_yas_bilinmiyorsa():
    sonuc = FL._y7_veri_bayat({"freshness": {}}, None)
    assert sonuc["applied"] is False
    assert sonuc["triggered"] is False


def test_y7_cok_bayatta_ek_not_ekleniyor():
    analiz = {"freshness": {
        "level": "cok_bayat", "latest_period": "2024-01-31", "label": "2,5 yıl önce",
        "last_annual": "2024-01-31", "annual_age_months": 30, "annual_stale": True,
    }}
    sonuc = FL._y7_veri_bayat(analiz, None)
    assert sonuc["triggered"] is True
    assert "kaçırılmış" in sonuc["explanation"]
    assert "F-Skoru" in sonuc["explanation"], "annual_stale iken F-Skoru notu da eklenmeli"


# ------------------------------------- karşılaştırılabilir-ikili regresyonu


def _kriter(id_, label, passed):
    return {"id": id_, "label": label, "status": H.OK, "passed": passed}


def test_netcd_vakasi_kapsam_farkli_iki_nokta_kapsam_cumlesi_uretir():
    """NETCD vakası: yalnızca 2 F-Skoru noktası var, kapsamları farklı (ilk
    nokta 7 kriter, son nokta 9 kriter ölçülmüş) — eşit kapsamlı bir çift
    YOK. İlk/son noktaya düşülür ve kapsam farkı cümlede açıkça yazılmalı;
    yoksa skordaki artış (5→7) tamamen şirket iyileşmesi gibi okunur, oysa
    2 puanı yalnızca ölçüm genişlemesinden geliyor."""
    ctx = {"health": {"fscore": {"usable_points": [
        {"date": "2024-12-31", "score": 5, "evaluated": 7, "label": "5/9",
         "criteria": [_kriter("c1", "Cari oran", True)]},
        {"date": "2025-12-31", "score": 7, "evaluated": 9, "label": "7/9",
         "criteria": [_kriter("c1", "Cari oran", True)]},
    ]}}}
    cumle = N._nar_fskor(ctx)
    assert cumle is not None
    assert "kapsamının genişlemesinden" in cumle["text"], (
        f"kapsam farkı açıklanmadı: {cumle['text']!r}"
    )


def test_doco_vakasi_esit_kapsamli_cift_varken_kapsam_cumlesi_yok():
    """DOCO/MAGEN vakası: 3 nokta var; ilk nokta farklı kapsamda (7 kriter)
    ama son iki nokta eşit kapsamda (9 kriter) ve skorları eşit (4/9).
    `_karsilastirilabilir_ikili` bu eşit çifti seçmeli — kapsam-genişlemesi
    cümlesi HİÇ üretilmemeli (üretilseydi her yıl aynı sahte notu tekrarlar,
    F3'te anlatı denetim aracının ilk sürümünün düştüğü tuzak buydu)."""
    ctx = {"health": {"fscore": {"usable_points": [
        {"date": "2023-12-31", "score": 3, "evaluated": 7, "label": "3/9", "criteria": []},
        {"date": "2024-12-31", "score": 4, "evaluated": 9, "label": "4/9", "criteria": []},
        {"date": "2025-12-31", "score": 4, "evaluated": 9, "label": "4/9", "criteria": []},
    ]}}}
    cumle = N._nar_fskor(ctx)
    assert cumle is not None
    assert "kapsamının genişlemesinden" not in cumle["text"], (
        f"eşit kapsamlı çift varken kapsam cümlesi üretilmemeliydi: {cumle['text']!r}"
    )
    assert "değişmedi" in cumle["text"]


def test_esit_kapsamli_cift_gercek_celiskiyi_hala_yakaliyor():
    """Pozitif kontrol: eşit kapsamlı çift seçilirken skor gerçekten
    farklıysa (kod hatası sonucu ya da kriter kimlik uyuşmazlığı) 'değişmedi'
    asla yazılmamalı — test körleştirilmemiş.

    Bu senaryo (evaluated eşit ama `criteria` boş, dolayısıyla kriter kriter
    eşleşme hiç kurulamıyor) doğrudan `_nar_fskor`'u çağırırken gerçek bir
    hata ortaya çıkardı: skor 4→7 değiştiği hâlde broken/fixed boş kaldığı
    için eski kod "Kriterlerin geçme/kalma durumu değişmedi." diyordu — tam
    da bu planın çıkış noktası olan çelişki. Düzeltme: "değişmedi" yalnızca
    skor da eşitse yazılıyor; aksi hâlde dürüst bir "ayırt edilemedi" notu."""
    ctx = {"health": {"fscore": {"usable_points": [
        {"date": "2024-12-31", "score": 4, "evaluated": 9, "label": "4/9", "criteria": []},
        {"date": "2025-12-31", "score": 7, "evaluated": 9, "label": "7/9", "criteria": []},
    ]}}}
    cumle = N._nar_fskor(ctx)
    assert cumle is not None
    assert "değişmedi" not in cumle["text"], f"skor değiştiği hâlde 'değişmedi' dendi: {cumle['text']!r}"
    assert "kapsamının genişlemesinden" not in cumle["text"], (
        "kapsam eşit olduğu için genişleme notu yanlış olurdu"
    )
    assert "ayırt edilemedi" in cumle["text"]
