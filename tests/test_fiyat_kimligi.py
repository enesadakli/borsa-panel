"""`_profil_kaydi()` ve `bicim.fiyat_zamani()` testleri.

İkisi de F13 C2'nin parçası: fiyata bir kimlik (ne zamana ait olduğu)
kazandırıyor. `regularMarketTime`/`marketState` önceden hiç okunmuyordu;
arayüz fiyatı koşulsuz "son kapanış" diye etiketliyordu — seans açıkken bu
etiket yanlıştı, o an bir anlık fiyattır.

Testler ağsız: `_profil_kaydi()` saf bir fonksiyon (Yahoo bloğu → sözlük),
`fiyat_zamani()` saf bir biçimlendirici. Sabit epoch + sabit ofset
kullanılıyor — makinenin kendi saat diliminden bağımsız olması için.
"""

from __future__ import annotations

from core import bicim as B
from core.yahoo import PROFIL_SURUM, _profil_kaydi

#: 2026-07-31 18:09 (TR, UTC+3) — bu oturumda gerçek Yahoo yanıtından
#: doğrulanmış bir epoch. Sabit tutulması testin makine saat diliminden
#: bağımsız kalmasını sağlıyor.
_EPOCH = 1785510595
_TR_OFSET_MS = 10800000  # +03:00


def _blok(**price_ustler) -> dict:
    price = {"regularMarketTime": _EPOCH, "marketState": "CLOSED",
             "gmtOffSetMilliseconds": _TR_OFSET_MS, "currency": "TRY",
             "regularMarketPrice": {"raw": 41.74}}
    price.update(price_ustler)
    return {"price": price, "assetProfile": {"sector": "Industrials"}}


# ------------------------------------------------------------ _profil_kaydi


def test_profil_kaydi_tam_blokta_beklenen_alanlari_tasiyor():
    kayit = _profil_kaydi("TEST.IS", _blok())
    assert kayit["price_time"] == _EPOCH
    assert kayit["market_state"] == "CLOSED"
    assert kayit["gmt_offset_ms"] == _TR_OFSET_MS
    assert kayit["last_price"] == 41.74
    assert kayit["_surum"] == PROFIL_SURUM


def test_profil_kaydi_bos_blokta_ayni_anahtar_kumesi():
    """Boş blok / `price` modülü yok — anahtar kümesi değişmemeli, yalnızca
    değerler `None` olmalı. Dala göre alan kaybolmasın diye."""
    tam = set(_profil_kaydi("TEST.IS", _blok()))
    bos = set(_profil_kaydi("TEST.IS", {}))
    fiyatsiz = set(_profil_kaydi("TEST.IS", {"assetProfile": {"sector": "Industrials"}}))
    assert tam == bos == fiyatsiz


def test_profil_kaydi_bos_blokta_fiyat_alanlari_none():
    kayit = _profil_kaydi("TEST.IS", {})
    assert kayit["price_time"] is None
    assert kayit["market_state"] is None
    assert kayit["gmt_offset_ms"] is None
    assert kayit["last_price"] is None


def test_profil_kaydi_raw_sarmali_ve_ciplak_sayi_ikisi_de_cozuluyor():
    """Yahoo bazı alanları `{"raw":..,"fmt":..}` sarmalında, bazılarını çıplak
    verir — `_raw()` ikisini de aynı şekilde çözmeli."""
    sarmalli = _profil_kaydi("TEST.IS", _blok(regularMarketTime={"raw": _EPOCH, "fmt": "x"}))
    ciplak = _profil_kaydi("TEST.IS", _blok(regularMarketTime=_EPOCH))
    assert sarmalli["price_time"] == ciplak["price_time"] == _EPOCH


# -------------------------------------------------------------- fiyat_zamani


def test_fiyat_zamani_kapali_seansta_tarih_ve_saat_yaziyor():
    etiket = B.fiyat_zamani(_EPOCH, _TR_OFSET_MS, "CLOSED")
    assert etiket == "2026-07-31 18:09 kapanışı"


def test_fiyat_zamani_acik_seansta_kapanis_demiyor():
    """Açık seansta değer bir anlık fiyattır; 'kapanış' yanlış olur."""
    etiket = B.fiyat_zamani(_EPOCH, _TR_OFSET_MS, "REGULAR")
    assert "kapanış" not in etiket
    assert "18:09" in etiket
    assert "açık seans" in etiket


def test_fiyat_zamani_zaman_yoksa_none():
    """`price_time` yoksa bugünün saati YAZILMAMALI — None dönmeli."""
    assert B.fiyat_zamani(None, _TR_OFSET_MS, "CLOSED") is None


def test_fiyat_zamani_ofset_yoksa_utcye_dusup_isaretliyor():
    """Ofset bilinmiyorsa UTC'ye düşülür ve bu **görünür** olmalı — sessizce
    yanlış saat göstermek, hiç göstermemekten kötüdür."""
    etiket = B.fiyat_zamani(_EPOCH, None, "CLOSED")
    assert "(UTC)" in etiket
    assert "15:09" in etiket  # TR ofseti (+3) düşülünce UTC 15:09 olur
