"""FCF marjı, FCF payout ve işletme sermayesi değişimi testleri.

Üçü de sentetik paketle sınanıyor, canlı Yahoo verisiyle değil: bunlar
oran hesapları ve asıl risk kenar durumlarda (negatif payda, sıfır payda,
eksik kalem, banka yolu). Canlı veri bu durumların çoğunu hiç üretmez,
üretse de tekrarlanabilir olmaz.

Sabitlenen şey beklenen bir sayı değil, **davranış**: hangi girdide hangi
durum kodunun döndüğü ve payda işaretinin nasıl ele alındığı.
"""

from __future__ import annotations

from core import health as H

OK = "ok"
EKSIK = "eksik_veri"
GECERSIZ = "sektorde_gecersiz"


def _satir(tarih: str, **degerler) -> dict:
    return {"date": tarih, "values": degerler}


def _paket(*satirlar) -> dict:
    return {"annual": list(satirlar), "quarterly": [], "ttm": {}}


#: Bütün kalemleri dolu, tek dönemlik taban. Testler yalnızca ilgilendikleri
#: kalemi değiştirip geri kalanı sabit tutuyor.
_TAM = dict(
    NetIncome=100.0, OperatingCashFlow=120.0, FreeCashFlow=80.0,
    TotalAssets=1000.0, TotalRevenue=500.0, CashDividendsPaid=-30.0,
    CurrentAssets=300.0, CurrentLiabilities=200.0,
)


def _kar_kalitesi(**ustler) -> dict:
    degerler = dict(_TAM)
    degerler.update(ustler)
    return H.profit_quality(_paket(_satir("2025-12-31", **degerler)), bank=False)


# ------------------------------------------------------------------ FCF marjı


def test_fcf_marji_hesabi():
    """FCF marjı = serbest nakit akışı / gelir."""
    node = _kar_kalitesi()["fcf_margin"]
    assert node["status"] == OK
    assert abs(node["value"] - 0.16) < 1e-9, "80 / 500 = 0,16 olmalı"
    # Seviye olduğu için işaretsiz basılıyor ("%16,0"), marjlarla aynı biçim.
    assert "%16,0" in node["detail"]
    assert "+" not in node["detail"], "marj seviyesi işaretli basılmamalı"


def test_fcf_marji_negatif_olabilir():
    """Nakit yakan şirkette marj negatif çıkar; bu eksik veri değil."""
    node = _kar_kalitesi(FreeCashFlow=-50.0)["fcf_margin"]
    assert node["status"] == OK
    assert node["value"] < 0


def test_fcf_marji_gelir_yoksa_eksik():
    """Gelir sıfır/None ise sıfıra bölme yerine eksik veri dönmeli."""
    for gelir in (None, 0.0):
        node = _kar_kalitesi(TotalRevenue=gelir)["fcf_margin"]
        assert node["status"] == EKSIK, f"gelir={gelir} için eksik beklenir"
        assert node["value"] is None


def test_fcf_marji_nakit_akisi_yoksa_eksik():
    node = _kar_kalitesi(FreeCashFlow=None)["fcf_margin"]
    assert node["status"] == EKSIK


# ---------------------------------------------------------------- FCF payout


def test_fcf_payout_temettu_isaretini_normallestiriyor():
    """Yahoo temettüyü **negatif** verir (nakit çıkışı).

    Mutlak değer alınmazsa oran negatif çıkar ve "kârının %-37'sini dağıttı"
    gibi anlamsız bir cümle üretilir. Bu test o normalleştirmeyi kilitliyor.
    """
    node = _kar_kalitesi(CashDividendsPaid=-30.0)["fcf_payout"]
    assert node["status"] == OK
    assert node["value"] > 0, "temettü negatif gelse de oran pozitif olmalı"
    assert abs(node["value"] - 0.375) < 1e-9, "30 / 80 = 0,375 olmalı"


def test_fcf_payout_pozitif_temettu_ayni_sonucu_veriyor():
    """Kaynak işareti pozitif verirse de sonuç değişmemeli."""
    eksili = _kar_kalitesi(CashDividendsPaid=-30.0)["fcf_payout"]["value"]
    artili = _kar_kalitesi(CashDividendsPaid=30.0)["fcf_payout"]["value"]
    assert eksili == artili


def test_fcf_payout_negatif_nakit_akisinda_tanimsiz():
    """FCF negatifken oran anlamsız; sayı üretmek yerine sebebi yazılmalı.

    30 / -80 = -0,375 "temettü dağıtmamış" gibi okunurdu; oysa şirket nakit
    yakarken temettü dağıtmış, yani dağıtım borç/nakit stokundan gelmiş.
    """
    node = _kar_kalitesi(FreeCashFlow=-80.0)["fcf_payout"]
    assert node["status"] == EKSIK
    assert node["value"] is None
    assert "negatif" in node["detail"]


def test_fcf_payout_sifir_nakit_akisinda_tanimsiz():
    """FCF tam sıfırsa sıfıra bölünmemeli."""
    node = _kar_kalitesi(FreeCashFlow=0.0)["fcf_payout"]
    assert node["status"] == EKSIK


def test_fcf_payout_temettu_verisi_yoksa_eksik():
    node = _kar_kalitesi(CashDividendsPaid=None)["fcf_payout"]
    assert node["status"] == EKSIK


# ------------------------------------------------- banka / boş tablo yolları


def test_banka_yolunda_dort_metrik_de_isaretli_donuyor():
    """Banka için metrik **yok olmamalı**, "geçersiz" diye işaretlenmeli.

    Anahtarı hiç döndürmemek, ölçülüp bulunamadı ile hiç ölçülmedi ayrımını
    siliyordu; okuyucu metriğin denenip denenmediğini göremiyordu.
    """
    sonuc = H.profit_quality(_paket(_satir("2025-12-31", **_TAM)), bank=True)
    for anahtar in ("accrual_ratio", "fcf_gap", "fcf_margin", "fcf_payout"):
        assert anahtar in sonuc, f"banka yolunda {anahtar} anahtarı düşmüş"
        assert sonuc[anahtar]["status"] == GECERSIZ


def test_yillik_tablo_yoksa_dort_metrik_de_eksik_donuyor():
    sonuc = H.profit_quality({"annual": []}, bank=False)
    for anahtar in ("accrual_ratio", "fcf_gap", "fcf_margin", "fcf_payout"):
        assert anahtar in sonuc, f"boş tabloda {anahtar} anahtarı düşmüş"
        assert sonuc[anahtar]["status"] == EKSIK


def test_kar_kalitesi_anahtarlari_her_yolda_ayni():
    """Üç çıkış yolu da aynı sözleşmeyi döndürmeli.

    Bu test, ileride yeni bir metrik eklenip yalnızca normal yola konursa
    (banka/boş yollar unutulursa) kırmızı yanar.
    """
    normal = H.profit_quality(_paket(_satir("2025-12-31", **_TAM)), bank=False)
    banka = H.profit_quality(_paket(_satir("2025-12-31", **_TAM)), bank=True)
    bos = H.profit_quality({"annual": []}, bank=False)
    assert set(normal) == set(banka) == set(bos)


def test_gecmis_temettuyu_tasiyor():
    """Tarihçe satırlarında temettü kalemi de bulunmalı."""
    sonuc = H.profit_quality(_paket(_satir("2025-12-31", **_TAM)), bank=False)
    assert sonuc["history"][0]["cash_dividends_paid"] == -30.0


# ----------------------------------------------- işletme sermayesi değişimi


def _nwc(onceki: tuple, simdiki: tuple, bank: bool = False) -> dict:
    """(CurrentAssets, CurrentLiabilities) çiftlerinden nwc_change düğümü."""
    def _degerler(cift):
        temel = dict(_TAM)
        if cift is None:
            temel.pop("CurrentAssets", None)
            temel.pop("CurrentLiabilities", None)
        else:
            temel["CurrentAssets"], temel["CurrentLiabilities"] = cift
        return temel

    paket = _paket(
        _satir("2024-12-31", **_degerler(onceki)),
        _satir("2025-12-31", **_degerler(simdiki)),
    )
    return H.debt_profile(paket, bank)["nwc_change"]


def test_nwc_degisimi_hesabi():
    """NWC = cari varlık − cari yükümlülük; değişim önceki döneme oranla."""
    node = _nwc((300.0, 200.0), (350.0, 200.0))   # 100 -> 150
    assert node["status"] == OK
    assert abs(node["value"] - 0.5) < 1e-9
    assert "%+50,0" in node["detail"]


def test_nwc_azalisi_negatif_isaretli():
    node = _nwc((300.0, 200.0), (250.0, 200.0))   # 100 -> 50
    assert node["status"] == OK
    assert abs(node["value"] + 0.5) < 1e-9
    assert "%-50,0" in node["detail"]


def test_nwc_negatif_tabanda_yon_dogru():
    """Önceki NWC negatifken payda mutlak değer alınıyor.

    −100'den −50'ye gitmek işletme sermayesi açığının **kapanması**, yani
    pozitif bir değişim. Payda ham (−100) bırakılsaydı işaret ters dönüp
    iyileşme kötüleşme gibi okunurdu.
    """
    node = _nwc((200.0, 300.0), (200.0, 250.0))   # -100 -> -50
    assert node["status"] == OK
    assert node["value"] > 0, "açığın kapanması pozitif değişim olmalı"
    assert abs(node["value"] - 0.5) < 1e-9


def test_nwc_negatife_derinlesme_negatif():
    node = _nwc((200.0, 250.0), (200.0, 300.0))   # -50 -> -100
    assert node["value"] < 0


def test_nwc_onceki_donem_sifirsa_eksik():
    """Sıfıra bölünme yerine sebebi yazılmalı."""
    node = _nwc((200.0, 200.0), (250.0, 200.0))   # 0 -> 50
    assert node["status"] == EKSIK
    assert node["value"] is None
    assert "sıfır" in node["detail"]


def test_nwc_kalem_eksikse_eksik():
    node = _nwc(None, (350.0, 200.0))
    assert node["status"] == EKSIK
    assert "eksik" in node["detail"].lower()


def test_nwc_tek_donemde_eksik():
    """Değişim iki dönem ister; tek dönemlik tabloda hesaplanamaz."""
    paket = _paket(_satir("2025-12-31", **_TAM))
    node = H.debt_profile(paket, False)["nwc_change"]
    assert node["status"] == EKSIK


def test_nwc_bankada_gecersiz():
    """Bankada cari varlık/yükümlülük ayrımı sanayi şirketiyle aynı anlamı
    taşımaz; eksik veri değil, tanımsız olarak işaretlenmeli."""
    node = _nwc((300.0, 200.0), (350.0, 200.0), bank=True)
    assert node["status"] == GECERSIZ
