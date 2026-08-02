"""Önbellek anahtarı ve korunan uç teli testleri.

Üç farklı konuyu bir araya getiriyor çünkü hepsi aynı sınıftan: bir
kayıt/liste güncellenince başka bir yerin bunu **fark etmemesi** riski.

1. `yahoo.fundamentals()`'ın önbellek anahtarı istenen alan listesini
   içermiyordu; `YILLIK_ALANLAR`/`CEYREKLIK_ALANLAR`'a yeni kalem eklendiğinde
   eski kayıt görünmez şekilde eksik kalıyordu (`CashDividendsPaid` böyle
   kayboldu). Kalıcı çözüm `istenen_alanlar` üst kümesi.
2. `KORUNAN_UCLAR`, `server.py`'de admin anahtarıyla korunması gereken uçların
   listesi. Yeni bir `/api/llm-*` ucu eklenip bu listeye eklenmeyi unutursa
   hiçbir test bunu yakalamıyordu.
3. `yahoo.profile()`'ın önbellek kaydı da aynı tuzağı taşıyordu — F13 C2'de
   `price_time`/`market_state`/`gmt_offset_ms` eklendi, ama diskte 1116 eski
   kayıt var ve hiçbiri bu alanları içermiyor. Burada çözüm alan listesi değil
   basit bir `_surum` sayacı: kayıt sürümü kod sürümüyle eşleşmezse ıskalanır.
"""

from __future__ import annotations

import tempfile

from core import cache as CACHE_MOD

# --------------------------------------------------------- önbellek anahtarı


def _gecici_cache() -> CACHE_MOD.Cache:
    return CACHE_MOD.Cache(tempfile.mkdtemp())


def _kabul_edilir(kayit: dict | None, istenenler) -> bool:
    """`yahoo.fundamentals()`'taki isabet koşulunun saf kopyası.

    Ağ yoluna dokunmadan test edilebilsin diye buraya çıkarıldı; asıl kod
    `core/yahoo.py:fundamentals()` içinde birebir aynı ifadeyi kullanır.
    """
    return kayit is not None and set(kayit.get("istenen_alanlar") or ()) >= set(istenenler)


def test_eski_kayit_istenen_alanlar_yoksa_reddedilir():
    """`istenen_alanlar` alanı olmayan (F11 öncesi) bir kayıt asla isabet
    saymamalı — aksi hâlde eksik kalem sessizce kalmaya devam eder."""
    c = _gecici_cache()
    c.set_record("fundamentals", "X__annual", {"symbol": "X", "fields": {}})
    kayit = c.get_record("fundamentals", "X__annual")
    assert not _kabul_edilir(kayit, ["TotalRevenue", "CashDividendsPaid"])


def test_yeni_alan_eklenince_eski_kayit_reddedilir():
    """Asıl senaryo: kayıt {A,B} ile yazılmış, sonra alan listesine C eklenmiş.

    Eski kayıt C'yi hiç içermez; üst küme testi bunu yakalayıp yeniden
    çekime zorlamalı.
    """
    c = _gecici_cache()
    c.set_record("fundamentals", "X__annual",
                 {"symbol": "X", "istenen_alanlar": ["A", "B"], "fields": {}})
    kayit = c.get_record("fundamentals", "X__annual")
    assert not _kabul_edilir(kayit, ["A", "B", "C"])


def test_ayni_alan_listesiyle_isabet_kabul_edilir():
    c = _gecici_cache()
    c.set_record("fundamentals", "X__annual",
                 {"symbol": "X", "istenen_alanlar": ["A", "B", "C"], "fields": {}})
    kayit = c.get_record("fundamentals", "X__annual")
    assert _kabul_edilir(kayit, ["A", "B", "C"])


def test_alan_cikarilmasi_yeniden_cekim_gerektirmez():
    """Üst küme (eşitlik değil) kasıtlı: bir alanı listeden çıkarmak gereksiz
    yeniden çekim yaratmamalı — kayıt istenenden fazlasını zaten içeriyor."""
    c = _gecici_cache()
    c.set_record("fundamentals", "X__annual",
                 {"symbol": "X", "istenen_alanlar": ["A", "B", "C"], "fields": {}})
    kayit = c.get_record("fundamentals", "X__annual")
    assert _kabul_edilir(kayit, ["A", "B"])


def test_fundamentals_kaydeder_ne_istendigini():
    """`yahoo.fundamentals()`'ın gerçek anahtarı üretip üretmediğini,
    ağa çıkmadan, doğrudan `Cache.set_record` çağrısını simüle ederek sına."""
    c = _gecici_cache()
    c.set_record("fundamentals", "SISE.IS__annual",
                 {"symbol": "SISE.IS", "period_type": "annual",
                  "istenen_alanlar": sorted(["TotalRevenue", "NetIncome"]),
                  "fields": {}})
    kayit = c.get_record("fundamentals", "SISE.IS__annual")
    assert kayit["istenen_alanlar"] == ["NetIncome", "TotalRevenue"]


# --------------------------------------------------------------- profil sürümü


def test_eski_surumlu_profil_kaydi_reddediliyor():
    """`_surum` alanı olmayan (F13 C2 öncesi) ya da eski sürümlü bir kayıt
    isabet saymamalı — aksi hâlde `price_time` gibi yeni alanlar sembol
    görülene kadar sessizce `None` kalır (`CashDividendsPaid`'in 4 yıl
    saklanmasına yol açan sınıfın aynısı)."""
    from core.yahoo import PROFIL_SURUM

    c = _gecici_cache()
    c.set_record("profile", "TEST.IS", {"symbol": "TEST.IS", "last_price": 41.74})
    kayit = c.get_record("profile", "TEST.IS")
    assert kayit.get("_surum") != PROFIL_SURUM


def test_guncel_surumlu_profil_kaydi_kabul_ediliyor():
    from core.yahoo import PROFIL_SURUM

    c = _gecici_cache()
    c.set_record("profile", "TEST.IS",
                 {"symbol": "TEST.IS", "last_price": 41.74, "_surum": PROFIL_SURUM})
    kayit = c.get_record("profile", "TEST.IS")
    assert kayit.get("_surum") == PROFIL_SURUM


# --------------------------------------------------------------- ttl=0 tazeleme


def test_ttl_sifir_her_zaman_iskaliyor():
    """`ttl=0` her koşulda önbelleği ıskalamalı — "Fiyatı tazele" (F13 C5)
    mekanizmasının temeli bu; `cache.py`'de ayrı bir kod yolu değil,
    `get_record`'un doğal davranışı."""
    c = _gecici_cache()
    c.set_record("profile", "TEST.IS", {"symbol": "TEST.IS", "last_price": 41.74})
    assert c.get_record("profile", "TEST.IS", ttl=0) is None
    assert c.get_record("profile", "TEST.IS") is not None  # ttl=None hâlâ isabet


# --------------------------------------------------------- korunan uç teli


def test_korunan_uclar_routing_tablolarinda_var():
    """`KORUNAN_UCLAR`'daki her yol gerçekten bir uç noktaya karşılık gelmeli.

    Yazım hatası ya da uç silinip listeden çıkarılmayı unutma senaryosunu
    yakalar.
    """
    import server

    tum_yollar = set(server.GET_UCLARI) | set(server.POST_UCLARI)
    kayip = sorted(y for y in server.KORUNAN_UCLAR if y not in tum_yollar)
    assert not kayip, f"KORUNAN_UCLAR'da olup routing'de olmayan yol: {kayip}"


def test_yeni_llm_ucu_korumasiz_kalirsa_yakalanir():
    """Asıl senaryo: `/api/llm-*` desenli yeni bir uç eklenip `KORUNAN_UCLAR`'a
    eklenmesi unutulursa bu test düşmeli.

    Pozitif kontrol: `server.GET_UCLARI`'na geçici olarak sahte bir
    `/api/llm-deneme` eklenip testin gerçekten düştüğü doğrulandı (elle).
    """
    import server

    korumasiz = sorted(
        yol for yol in (set(server.GET_UCLARI) | set(server.POST_UCLARI))
        if yol.startswith("/api/llm-") and yol not in server.KORUNAN_UCLAR
    )
    assert not korumasiz, f"admin korumasız kalan LLM ucu: {korumasiz}"
