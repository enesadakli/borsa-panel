"""F-Skoru testi.

İki şey doğrulanıyor:

1. **Bağımsız yeniden hesap.** Testin içinde 9 kriter, health.py'den tamamen
   ayrı bir kod yoluyla, doğrudan formüllerle hesaplanıyor ve sonuç
   karşılaştırılıyor. Aynı veriden iki bağımsız yol aynı skoru vermiyorsa
   implementasyonda hata var.
2. **Eksik veri sıfır sayılmıyor.** Bir kalem kasten silinip skorun
   "değerlendirilemedi" olarak raporlandığı, "kaldı" sayılmadığı doğrulanıyor.

Skor beklenen bir sayıya (ör. 7) sabitlenmiyor: Yahoo verisi güncellendiğinde
gerçek skor değişebilir ve bu bir hata değil. Sabitlenen şey, iki hesap
yolunun birbirine eşitliği ve kenar durumların davranışı.
"""

from __future__ import annotations

import copy

from core import fundamentals as F
from core import health as H
from core.yahoo import YahooClient

SEMBOL = "SISE.IS"
BANKA = "AKBNK.IS"

_client = None
_paketler: dict[str, dict] = {}


def _pack(symbol: str) -> dict:
    global _client
    if _client is None:
        _client = YahooClient()
    if symbol not in _paketler:
        _paketler[symbol] = F.load(_client, symbol)
    return copy.deepcopy(_paketler[symbol])


# ------------------------------------------- bağımsız referans hesaplayıcı


def _oran(pay, bolen):
    if pay is None or not bolen:
        return None
    return pay / bolen


def referans_fskor(rows: list[dict], index: int) -> dict:
    """health.py'den bağımsız, doğrudan formüllerle F-Skoru.

    Piotroski'nin tanımı: kârlılık 4, kaldıraç/likidite 3, verimlilik 2 kriter.
    Dönem başı varlık kullanılır (t−1 yılının toplam varlığı).
    """
    now = rows[index]["values"]
    prev = rows[index - 1]["values"]
    older = rows[index - 2]["values"] if index >= 2 else {}

    roa_now = _oran(now.get("NetIncome"), prev.get("TotalAssets"))
    roa_prev = _oran(prev.get("NetIncome"), older.get("TotalAssets")) if older else None
    cfo = now.get("OperatingCashFlow")
    ni = now.get("NetIncome")

    kaldirac_now = _oran(now.get("LongTermDebt"), now.get("TotalAssets"))
    kaldirac_prev = _oran(prev.get("LongTermDebt"), prev.get("TotalAssets"))
    cari_now = _oran(now.get("CurrentAssets"), now.get("CurrentLiabilities"))
    cari_prev = _oran(prev.get("CurrentAssets"), prev.get("CurrentLiabilities"))
    hisse_now = now.get("OrdinarySharesNumber")
    hisse_prev = prev.get("OrdinarySharesNumber")

    brut_now = _oran(now.get("GrossProfit"), now.get("TotalRevenue"))
    brut_prev = _oran(prev.get("GrossProfit"), prev.get("TotalRevenue"))
    devir_now = _oran(now.get("TotalRevenue"), prev.get("TotalAssets"))
    devir_prev = _oran(prev.get("TotalRevenue"), older.get("TotalAssets")) if older else None

    testler = [
        ("ROA_POZITIF", None if roa_now is None else roa_now > 0),
        ("CFO_POZITIF", None if cfo is None else cfo > 0),
        ("ROA_ARTIYOR", None if (roa_now is None or roa_prev is None) else roa_now > roa_prev),
        ("NAKIT_KARDAN_BUYUK",
         None if (cfo is None or ni is None or not prev.get("TotalAssets")) else cfo > ni),
        ("KALDIRAC_AZALIYOR",
         None if (kaldirac_now is None or kaldirac_prev is None) else kaldirac_now < kaldirac_prev),
        ("CARI_ORAN_ARTIYOR",
         None if (cari_now is None or cari_prev is None) else cari_now > cari_prev),
        ("HISSE_IHRACI_YOK",
         None if (not hisse_now or not hisse_prev) else (hisse_now / hisse_prev - 1) <= 0.01),
        ("BRUT_MARJ_ARTIYOR",
         None if (brut_now is None or brut_prev is None) else brut_now > brut_prev),
        ("DEVIR_HIZI_ARTIYOR",
         None if (devir_now is None or devir_prev is None) else devir_now > devir_prev),
    ]
    return {
        "score": sum(1 for _, gecti in testler if gecti is True),
        "evaluated": sum(1 for _, gecti in testler if gecti is not None),
        "detay": dict(testler),
    }


# ----------------------------------------------------------------- testler


def test_bagimsiz_hesap_ayni_skoru_veriyor():
    pack = _pack(SEMBOL)
    rows = F.rows(pack, "annual")
    motor = H.fscore_series(pack, bank=False)

    assert motor["points"], "F-Skoru noktası üretilmedi"

    for nokta in motor["points"]:
        index = next(i for i, row in enumerate(rows) if row["date"] == nokta["date"])
        referans = referans_fskor(rows, index)

        assert nokta["score"] == referans["score"], (
            f"{nokta['date']}: motor {nokta['score']}, bağımsız hesap {referans['score']}"
        )
        assert nokta["evaluated"] == referans["evaluated"], (
            f"{nokta['date']}: değerlendirilen kriter sayısı uyuşmuyor "
            f"(motor {nokta['evaluated']}, referans {referans['evaluated']})"
        )

        for kriter in nokta["criteria"]:
            beklenen = referans["detay"][kriter["id"]]
            if kriter["status"] == H.OK:
                assert kriter["passed"] is beklenen, (
                    f"{nokta['date']} / {kriter['id']}: motor {kriter['passed']}, "
                    f"referans {beklenen}"
                )
            else:
                assert beklenen is None, (
                    f"{nokta['date']} / {kriter['id']}: motor hesaplayamadı ama "
                    "referans hesapladı"
                )


def test_her_kriterin_gerekcesi_var():
    pack = _pack(SEMBOL)
    son = H.fscore_series(pack, bank=False)["latest"]
    assert son, "Kullanılabilir skor noktası yok"
    assert len(son["criteria"]) == 9, "9 kriterin tamamı listelenmeli"
    for kriter in son["criteria"]:
        assert kriter["label"], f"{kriter['id']}: ekran adı yok"
        assert kriter["detail"], f"{kriter['id']}: gerekçe metni yok"
        if kriter["status"] == H.OK:
            assert kriter["sources"], f"{kriter['id']}: kaynak kalem listelenmemiş"


def test_eksik_kalem_sifir_sayilmiyor():
    """Brüt kâr silinince kriter 'kaldı' değil 'değerlendirilemedi' olmalı."""
    pack = _pack(SEMBOL)
    once = H.fscore_series(pack, bank=False)["latest"]
    brut_once = next(c for c in once["criteria"] if c["id"] == "BRUT_MARJ_ARTIYOR")

    if brut_once["status"] != H.OK:
        return  # veri zaten yok, test anlamsız

    for row in F.rows(pack, "annual"):
        row["values"].pop("GrossProfit", None)

    sonra = H.fscore_series(pack, bank=False)["latest"]
    brut_sonra = next(c for c in sonra["criteria"] if c["id"] == "BRUT_MARJ_ARTIYOR")

    assert brut_sonra["status"] == H.EKSIK, "Silinen kalem eksik_veri olarak işaretlenmeli"
    assert brut_sonra["passed"] is None, "Eksik kriter 'kaldı' sayılmamalı"
    assert sonra["evaluated"] == once["evaluated"] - 1, (
        f"Değerlendirilen kriter sayısı 1 azalmalıydı "
        f"({once['evaluated']} → {sonra['evaluated']})"
    )
    assert "BRUT_MARJ_ARTIYOR" in sonra["missing"], "Eksik kriter listede yok"
    assert "veri yok" in sonra["label"], f"Etiket eksikliği söylemiyor: {sonra['label']}"
    assert sonra["max"] == 9, "Payda 9 kalmalı, eksik kriterle küçültülmemeli"


def test_banka_kriterleri_sektorde_gecersiz():
    pack = _pack(BANKA)
    assert pack["bank_accounting"], "AKBNK banka muhasebesi olarak tanınmalı"

    seri = H.fscore_series(pack, bank=True)
    assert seri["model_applicable"] is False, "Bankada model uygulanabilir sayılmamalı"
    assert seri["model_note"], "Model uyarısı metni yok"

    son = seri["latest"]
    assert son, "Bankada da kısmi skor üretilmeli"
    gecersiz = {c["id"] for c in son["criteria"] if c["status"] == H.GECERSIZ}
    beklenen = {
        "CFO_POZITIF", "NAKIT_KARDAN_BUYUK", "KALDIRAC_AZALIYOR",
        "CARI_ORAN_ARTIYOR", "BRUT_MARJ_ARTIYOR",
    }
    assert gecersiz == beklenen, f"Sektörde geçersiz kriterler beklenenden farklı: {gecersiz}"
    assert "bu sektörde geçersiz" in son["label"], f"Etiket bunu söylemiyor: {son['label']}"
