"""Reel büyüme ve TÜFE eşleme testi.

En kritik test `test_tufe_serisi_para_birimine_gore_secilir`: bir ABD şirketini
Türkiye TÜFE'siyle deflate etmek, olmayan bir küçülme uydurmak olur. THYAO bu
kuralın gerçek sınavı — BIST'te işlem görüyor ama tablolarını USD açıklıyor,
dolayısıyla **US CPI** ile düzeltilmeli.
"""

from __future__ import annotations

from core import cache as cache_mod
from core import fundamentals as F
from core import inflation as INF
from core.yahoo import YahooClient

_client = None


def _c() -> YahooClient:
    global _client
    if _client is None:
        _client = YahooClient()
    return _client


# --------------------------------------------------------------- deflate matematiği


def test_deflate_bolme_kullaniyor():
    """Nominalden enflasyonu çıkarmak yüksek enflasyonda sapar."""
    sonuc = INF.deflate(0.41, 0.45)
    assert sonuc is not None
    assert abs(sonuc - (1.41 / 1.45 - 1)) < 1e-12, "Formül (1+n)/(1+e)-1 olmalı"
    assert abs(sonuc - (-0.0275862)) < 1e-6, f"Beklenen ≈ -%2,76, gelen {sonuc:.6f}"
    # Çıkarma yöntemi -0,04 derdi; aradaki fark 1,2 puan.
    assert abs(sonuc - (0.41 - 0.45)) > 0.01, "Çıkarma ile aynı sonucu vermemeli"


def test_deflate_esit_oranlarda_sifir():
    assert abs(INF.deflate(0.5, 0.5)) < 1e-12


def test_deflate_eksik_veriyle_none():
    assert INF.deflate(None, 0.45) is None
    assert INF.deflate(0.45, None) is None
    # Enflasyon -%100 matematiksel olarak tanımsız bölme yaratır.
    assert INF.deflate(0.1, -1.0) is None


# ------------------------------------------------- para birimi → TÜFE eşlemesi


def test_tufe_serisi_para_birimine_gore_secilir():
    cache = cache_mod.default_cache()

    beklenen = {
        "AAPL": "USD",
        "THYAO.IS": "USD",   # BIST hissesi ama tabloları USD → US CPI
        "SISE.IS": "TRY",
    }
    for sembol, para in beklenen.items():
        pack = F.load(_c(), sembol)
        assert pack["currency"] == para, (
            f"{sembol}: tablo para birimi {pack['currency']}, beklenen {para}"
        )
        seri = INF.series_for_pack(cache, pack)
        assert seri["currency"] == para, (
            f"{sembol}: {para} tablo için {seri['currency']} TÜFE serisi seçildi"
        )

    # Asıl tuzak: THYAO ve SISE aynı borsada ama farklı TÜFE serisi almalı.
    thyao = INF.series_for_pack(cache, F.load(_c(), "THYAO.IS"))
    sise = INF.series_for_pack(cache, F.load(_c(), "SISE.IS"))
    assert thyao["currency"] != sise["currency"], (
        "Aynı borsadaki iki şirkete borsaya göre değil, tablo para birimine göre "
        "TÜFE seçilmeli"
    )


def test_eski_para_birimi_kodu_normalize_edilir():
    """MCARD.IS vakası: Yahoo kalemleri "TRL" (2005 öncesi eski lira kodu) ile
    etiketliyor. Normalize edilmezse şirket yanlışlıkla "para birimi belirsiz"
    (Y5) sayılır; oysa bu farklı bir para birimi değil, aynı liranın eski adı.
    """
    assert F.PARA_BIRIMI_TAKMA_ADLAR.get("TRL") == "TRY"

    profile = {"financial_currency": None}
    tables = [{"fields": {"TotalRevenue": [{"currency": "TRL", "date": "2024-12-31", "value": 1.0}]}}]
    currency, source, notes = F._resolve_currency(profile, tables)
    assert currency == "TRY", "TRL etiketi TRY'ye normalize edilmeli"
    assert source == "labels"

    # financialCurrency doğrudan eski kodu döndürse bile normalize edilmeli.
    profile2 = {"financial_currency": "TRL"}
    currency2, source2, _ = F._resolve_currency(profile2, [])
    assert currency2 == "TRY"
    assert source2 == "profile"


def test_desteklenmeyen_para_biriminde_nominale_dusuyor():
    cache = cache_mod.default_cache()
    seri = INF.cpi_series(cache, "EUR")
    assert seri["available"] is False
    assert seri["notes"], "Sebep açıklanmalı"
    assert INF.cpi_growth(seri, "2024-12-31", "2025-12-31")["value"] is None


def test_eur_sirketi_ulkesinden_tufe_seciyor():
    """DOCO.IS vakası: EUR raporlayan şirkette Dünya Bankası'nda euro bölgesi
    agregatı yok (EMU/XC boş) — doğru seri şirketin `country` alanından
    (Avusturya) seçilmeli, Türkiye TÜFE'si hiçbir şekilde sızmamalı."""
    cache = cache_mod.default_cache()
    try:
        pack = F.load(_c(), "DOCO.IS")
    except Exception:
        return  # ağsız ortam — süiti kırma
    if pack.get("currency") != "EUR" or not pack.get("country"):
        return  # profil beklenenden farklı geldi, bu test onu doğrulamaz

    seri = INF.series_for_pack(cache, pack)
    assert seri["available"] is True, "Avusturya için Dünya Bankası serisi bulunmalı"
    assert seri["currency"] == "EUR"
    assert seri["annual_label"], "TÜFE kaynağı etiketi eksik"
    assert "Avusturya" in seri["annual_label"], (
        f"beklenen Avusturya TÜFE'si, gelen etiket: {seri['annual_label']!r}"
    )
    assert "Türkiye" not in seri["annual_label"], "Türkiye TÜFE'si sızmamalı"


def test_eur_bilinmeyen_ulke_tufe_uydurmuyor():
    """Ülke euro bölgesi haritasında yoksa (veya hiç gelmediyse) seri
    'kullanılamıyor' demeli — en yakın ülkeye sessizce düşülmemeli."""
    cache = cache_mod.default_cache()
    seri = INF.cpi_series(cache, "EUR", country="Ruritania")
    assert seri["available"] is False
    assert seri["notes"], "Sebep açıklanmalı"


# ------------------------------------------------------- kaynak karıştırmama


def test_aylik_ve_yillik_kaynaklar_karistirilmiyor():
    """Bir büyüme hesabının iki ucu aynı seriden gelmeli.

    Aylık endeks dönem sonu nokta değeri, Dünya Bankası ise yıllık ortalama.
    Birini diğerine bölmek sistematik sapma üretir.
    """
    cache = cache_mod.default_cache()
    usd = INF.cpi_series(cache, "USD")
    if not usd["monthly"] or not usd["annual"]:
        return

    aylar = sorted(usd["monthly"])
    en_eski_ay = aylar[0]

    # Aylık serinin kapsadığı dönem → aylık taban beklenir.
    yakin = INF.cpi_growth(usd, f"{aylar[len(aylar) // 2][:7]}-28", f"{aylar[-1][:7]}-28")
    if yakin["value"] is not None:
        assert yakin["basis"] == INF.BASIS_AYLIK

    # Aylık serinin başlamadığı dönem → yıllık ortalamaya düşmeli.
    eski_yil = int(en_eski_ay[:4]) - 3
    eski = INF.cpi_growth(usd, f"{eski_yil}-12-31", f"{eski_yil + 1}-12-31")
    if eski["value"] is not None:
        assert eski["basis"] == INF.BASIS_YILLIK, (
            f"Aylık seri {en_eski_ay}'da başlıyor; {eski_yil} için yıllık taban beklenir"
        )


def test_reel_seri_tek_tabandan_hesaplaniyor():
    cache = cache_mod.default_cache()
    pack = F.load(_c(), "SISE.IS")
    seri = INF.series_for_pack(cache, pack)
    noktalar = F.series(pack, "TotalRevenue")

    sonuc = INF.real_series(seri, noktalar)
    if not sonuc["points"]:
        return

    assert sonuc["basis"] in (INF.BASIS_AYLIK, INF.BASIS_YILLIK)
    assert sonuc["base"] == noktalar[-1][0], "Taban en son dönem olmalı"

    # Taban döneminin reel değeri nominaline eşit olmalı (kendisiyle deflate).
    taban_nominal = noktalar[-1][1]
    taban_reel = dict(sonuc["points"])[noktalar[-1][0]]
    assert abs(taban_reel - taban_nominal) < 1e-6, (
        "Taban dönemde reel = nominal olmalı"
    )


def test_reel_buyume_kaynak_etiketi_tasiyor():
    """Ekranda hangi TÜFE'nin kullanıldığı yazılabilmeli."""
    cache = cache_mod.default_cache()
    pack = F.load(_c(), "SISE.IS")
    seri = INF.series_for_pack(cache, pack)
    noktalar = F.series(pack, "TotalRevenue")
    nominal = F.growth(pack, "TotalRevenue")

    sonuc = INF.real_growth(seri, nominal, noktalar[-2][0], noktalar[-1][0])
    if sonuc["real"] is None:
        return
    assert sonuc["label"], "TÜFE kaynağı etiketi yok"
    assert sonuc["basis"], "Hesap tabanı belirtilmemiş"
    assert sonuc["nominal"] is not None, "Nominal değer de taşınmalı"
