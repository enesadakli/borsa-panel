"""`core/health.py` analiz fonksiyonlarının şekil (anahtar kümesi) tutarlılığı.

F11 planı `health.py`'de aynı sınıftan üç latent hata buldu: bir analiz
fonksiyonu dalına göre (banka / veri yok / normal) FARKLI anahtar kümeleri
döndürüyordu — `profit_quality`'nin `fcf_margin`/`fcf_payout`'u banka ve boş
tablo yollarında hiç dönmüyordu (bkz. `tests/test_nakit_metrikleri.py`, o
hata zaten patlamıştı ve orada düzeltildi). Tüketiciler hep `.get()`
kullandığı için şans eseri ayakta kalıyordu; bu test o şansı ortadan
kaldırıyor.

Yöntem: fonksiyonların "tüm dallarını" elle listelemek yerine, gerçekçi bir
senaryo matrisi (boş tablo / tek dönem / iki dönem / üç dönem / eksik kalem /
piyasa değeri yok / negatif özsermaye, her biri banka açık-kapalı) üzerinden
koşturup her fonksiyonun BÜTÜN senaryolarda aynı anahtar kümesini
döndürdüğünü doğruluyoruz — hem üst düzeyde hem her metrik düğümünün kendi
içinde (`metric()`'in `**extra` kwargs'ı bir dalda var, diğerinde yoksa
yakalanır).

`client=None` yeterli, stub gerekmiyor: `altman_z` ve `valuation` client'a
yalnızca `fundamentals.fx_rate` üzerinden dokunuyor, o da `base == quote`
olduğunda (burada hep TRY/TRY) hemen `1.0` dönüp ağa hiç çıkmıyor.

İyi örnek (karşılaştırma kılavuzu): `debt_profile["nwc_change"]` hiçbir dalda
ekstra alan geçirmiyor, o yüzden bedavaya doğru çıktı. Kötü örnek:
`altman_z`'nin `zone`/`components`'i yalnızca başarı yolunda vardı.
"""

from __future__ import annotations

from core import health as H
from core import inflation as INF


def _satir(tarih: str, **degerler) -> dict:
    return {"date": tarih, "values": degerler}


def _paket(*satirlar, **ust) -> dict:
    p = {"annual": list(satirlar), "quarterly": [], "ttm": {}}
    p.update(ust)
    return p


#: Altı fonksiyonun ihtiyaç duyduğu kalemlerin birleşimi. Testler yalnızca
#: ilgilendikleri kalemi değiştirip geri kalanı sabit tutuyor.
_TAM = dict(
    NetIncome=100.0, OperatingCashFlow=120.0, FreeCashFlow=80.0,
    TotalAssets=1000.0, TotalRevenue=500.0, CashDividendsPaid=-30.0,
    CurrentAssets=300.0, CurrentLiabilities=200.0,
    TotalDebt=300.0, NetDebt=250.0, EBITDA=150.0, EBIT=120.0,
    InterestExpense=-20.0, CurrentDebt=80.0,
    StockholdersEquity=600.0, RetainedEarnings=50.0,
    GrossProfit=200.0, OperatingIncome=60.0,
    WorkingCapital=100.0, TotalLiabilities=400.0,
)

#: Piyasa değeri para birimleri eşitken `fx_rate` client'a hiç dokunmuyor.
_UST_TAM = dict(market_cap=5_000.0, currency="TRY", price_currency="TRY")


def _donemler(n: int, **degisiklik) -> list[dict]:
    kalemler = dict(_TAM)
    kalemler.update(degisiklik)
    tarihler = ["2023-12-31", "2024-12-31", "2025-12-31"][-n:] if n else []
    return [_satir(t, **kalemler) for t in tarihler]


SENARYOLAR = (
    ("boş tablo", _paket(**_UST_TAM)),
    ("tek dönem", _paket(*_donemler(1), **_UST_TAM)),
    ("iki dönem", _paket(*_donemler(2), **_UST_TAM)),
    ("üç dönem", _paket(*_donemler(3), **_UST_TAM)),
    ("eksik kalem (varlık yok)", _paket(*_donemler(3, TotalAssets=None), **_UST_TAM)),
    ("piyasa değeri yok", _paket(*_donemler(3))),
    ("negatif özsermaye", _paket(*_donemler(3, StockholdersEquity=-100.0), **_UST_TAM)),
)

#: Tek tip `(pack, bank) -> dict` imzası. `return_profile`/`valuation` `bank`
#: almıyor; adaptör bunu yutuyor.
FONKSIYONLAR = (
    ("profit_quality", lambda p, b: H.profit_quality(p, b)),
    ("debt_profile", lambda p, b: H.debt_profile(p, b)),
    ("margin_profile", lambda p, b: H.margin_profile(p, b)),
    ("return_profile", lambda p, b: H.return_profile(p)),
    ("altman_z", lambda p, b: H.altman_z(None, p, b)),
    ("valuation", lambda p, b: H.valuation(None, p)),
)

#: Şekil karşılaştırmasında atlanan anahtarlar: içerikleri senaryoya göre
#: değişmesi BEKLENEN veri, şekil değil. `components` (Altman X1-X5) da
#: buraya girer: anahtarın KENDİSİ her yolda olmalı (asıl kilitlenen şey),
#: ama değeri None mı yoksa 5 alanlı bir sözlük mü olduğu senaryoya bağlı —
#: `history`/`series`/`sources` ile aynı gerekçe.
_ICERIK_ANAHTARLARI = ("history", "series", "sources", "components")


def _sekil(deger, derinlik: int = 2):
    """Bir değerin `dict` anahtar ağacı, `derinlik` seviyeye kadar.

    Liste ve diğer yaprak değerler `"…"` ile eşitlenir — anahtarın VARLIĞI
    önemli, taşıdığı değer değil. İki şeklin `==` ile eşitliği, iki dict'in
    aynı anahtarları aynı yerlerde taşıdığı anlamına gelir.
    """
    if not isinstance(deger, dict) or derinlik <= 0:
        return "…"
    return {
        k: (_sekil(v, derinlik - 1) if k not in _ICERIK_ANAHTARLARI else "…")
        for k, v in deger.items()
    }


def test_sekil_karsilastirmasi_farkli_anahtar_kumesini_yakaliyor():
    """Pozitif kontrol: `_sekil` gerçekten anahtar eksikliğini fark ediyor mu?

    Bu test düşerse `_sekil` bozuk demektir — aşağıdaki asıl test o zaman
    hiçbir şeyi yakalamıyor olabilir, geçmesi güven vermez.
    """
    assert _sekil({"a": 1}) != _sekil({"a": 1, "b": 2})
    assert _sekil({"a": {"x": 1}}) != _sekil({"a": {"x": 1, "y": 2}})
    assert _sekil({"a": 1}) == _sekil({"a": 2}), "değer değil, anahtar karşılaştırılmalı"


def test_analiz_fonksiyonlari_her_senaryoda_ayni_sekli_donduruyor():
    """Her fonksiyon, denenen 7 senaryo × 2 banka durumunda aynı şekli vermeli.

    İyi örnek: `INF.real_series` her yolda sabit 5 anahtar döndürüyor
    (`points, basis, label, skipped, base`) — aşağıda ayrıca doğrulanıyor,
    bu testin beklediği davranışın canlı bir örneği olarak.
    """
    hatalar = []
    for ad, cagir in FONKSIYONLAR:
        referans_etiket = referans_sekil = None
        for senaryo_adi, paket in SENARYOLAR:
            for bank in (False, True):
                etiket = f"{senaryo_adi} (bank={bank})"
                try:
                    sekil = _sekil(cagir(paket, bank))
                except Exception as hata:  # noqa: BLE001 — şekil dışı bir çökme de bulgu
                    hatalar.append(f"{ad}: '{etiket}' çöktü: {hata!r}")
                    continue
                if referans_sekil is None:
                    referans_etiket, referans_sekil = etiket, sekil
                elif sekil != referans_sekil:
                    hatalar.append(
                        f"{ad}: '{etiket}' şekli '{referans_etiket}' şeklinden "
                        f"farklı.\n  {etiket}: {sekil}\n  {referans_etiket}: {referans_sekil}"
                    )
    assert not hatalar, "\n\n".join(hatalar)


def test_real_growth_profile_sekli_tutarli():
    """`real_growth_profile`'ın imzası farklı (`pack, cpi`), ayrı test ediyoruz.

    Üç yol var: `len(points) < 2` (2 anahtar döndürüyordu), TÜFE'nin
    kapsamadığı dönem, ve tam başarı. Üçü de artık aynı 11 anahtarı taşımalı.
    """
    cpi = {
        "monthly": {"2023-12": 100.0, "2024-12": 110.0, "2025-12": 121.0},
        "monthly_label": "TEST TÜFE",
    }
    cpi_bos = {"monthly": {}, "monthly_label": None}

    tam = H.real_growth_profile(_paket(*_donemler(3)), cpi)
    kisa = H.real_growth_profile(_paket(*_donemler(1)), cpi)
    tufesiz = H.real_growth_profile(_paket(*_donemler(3)), cpi_bos)

    sekil_tam = _sekil(tam["revenue"])
    sekil_kisa = _sekil(kisa["revenue"])
    sekil_tufesiz = _sekil(tufesiz["revenue"])
    assert sekil_tam == sekil_kisa == sekil_tufesiz, (
        f"tam={sekil_tam}\nkisa={sekil_kisa}\ntufesiz={sekil_tufesiz}"
    )
    assert tam["revenue"]["status"] == "ok"
    assert kisa["revenue"]["status"] == "eksik_veri"
    assert tufesiz["revenue"]["status"] == "eksik_veri"


def test_real_series_referans_sabit_sekil():
    """`INF.real_series` her yolda sabit 5 anahtar döndürüyor — iyi örnek."""
    dolu = INF.real_series(
        {"monthly": {"2024-12": 100.0, "2025-12": 110.0}, "monthly_label": "T"},
        [("2024-12-31", 100.0), ("2025-12-31", 120.0)],
    )
    bos = INF.real_series({"monthly": {}, "monthly_label": None}, [])
    assert set(dolu) == set(bos) == {"points", "basis", "label", "skipped", "base"}
