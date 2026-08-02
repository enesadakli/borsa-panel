"""`risk.symbol_price_stats()` testleri.

Asıl regresyon kilidi: fonksiyon önbelleği **doğrudan** okumak yerine
`client.series()` üzerinden (gerektiğinde tazeleyerek) okumalı. Eskiden
`client.cache.closes(symbol)` kullanıyordu — bu, yalnızca smoke.py'nin
sembol listesindeki 9 şirkette veri buluyordu; kalan ~1100 şirkette
`available: False` dönüyor ve LLM raporundaki `## Fiyat serisi` bölümü
hiçbir iz bırakmadan kayboluyordu.

Sahte istemcide bilerek `.cache` özniteliği yok — kod hâlâ
`client.cache.closes(...)` çağırıyorsa test `AttributeError` ile düşer.
"""

from __future__ import annotations

from core import risk as RISK
from core.yahoo import YahooError, YahooNotFound


class _SahteIstemci:
    """`.series()` var, `.cache` yok — eski koda dönüş sessizce yakalanır."""

    def __init__(self, seri=None, hata=None):
        self._seri = seri
        self._hata = hata
        self.cagrilar = []

    def series(self, symbol: str, first_range: str = "2y"):
        self.cagrilar.append((symbol, first_range))
        if self._hata is not None:
            raise self._hata
        return self._seri


def _seri(gun_sayisi: int, baslangic_fiyat: float = 100.0) -> list[tuple[str, float]]:
    """`gun_sayisi` günlük sahte kapanış serisi, hafif dalgalanmalı.

    Tamamen deterministik ama sabit oranlı DEĞİL — sabit oranlı bir seri
    varyansı tam sıfır yapar, `annual_volatility` da (kod `if sapma else None`
    yazdığı için) `None` döner. Gerçek piyasa verisinde bu durum oluşmaz;
    testin gerçekçi olması için art arda +%0,3 / −%0,1 değişim veriliyor.
    """
    out = []
    fiyat = baslangic_fiyat
    for i in range(gun_sayisi):
        fiyat *= 1.003 if i % 2 == 0 else 0.999
        out.append((f"2025-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}", fiyat))
    return out


def test_onbellek_degil_seri_metodu_cagriliyor():
    """Kök düzeltme: `client.series()` kullanılıyor, `client.cache.closes()` değil.

    Sahte istemcide `.cache` hiç yok; eski koda dönülseydi bu test
    AttributeError ile düşerdi.
    """
    istemci = _SahteIstemci(seri=_seri(120))
    sonuc = RISK.symbol_price_stats(istemci, "TEST.IS")
    assert sonuc["available"] is True
    assert istemci.cagrilar, "client.series() hiç çağrılmadı"


def test_yeterli_gecmis_varsa_hesaplaniyor():
    istemci = _SahteIstemci(seri=_seri(252))
    sonuc = RISK.symbol_price_stats(istemci, "TEST.IS")
    assert sonuc["available"] is True
    assert sonuc["days"] == 252
    assert sonuc["annual_volatility"] is not None
    assert sonuc["max_drawdown"] is not None


def test_yetersiz_gecmiste_sebep_yaziyor():
    """60 günden az geçmişte `available: False` dönmeli, sebep boş olmamalı."""
    istemci = _SahteIstemci(seri=_seri(30))
    sonuc = RISK.symbol_price_stats(istemci, "TEST.IS")
    assert sonuc["available"] is False
    assert sonuc["reason"], "sebep boş olmamalı"
    assert "geçmiş" in sonuc["reason"]


def test_yahoo_hatasinda_sebep_ag_kaynak_diyor():
    """`YahooError` (ve alt sınıfları) ayrı, tanınabilir bir sebep vermeli."""
    istemci = _SahteIstemci(hata=YahooNotFound("404: yok"))
    sonuc = RISK.symbol_price_stats(istemci, "YOKSEMBOL.IS")
    assert sonuc["available"] is False
    assert "ağ/kaynak" in sonuc["reason"]


def test_beklenmeyen_hatada_da_rapor_dusmuyor():
    """`YahooError` dışı bir hata da yutulmalı — fiyat bölümü isteğe bağlı,
    rapor bu yüzden hiç çökmemeli."""
    istemci = _SahteIstemci(hata=ValueError("beklenmeyen"))
    sonuc = RISK.symbol_price_stats(istemci, "TEST.IS")
    assert sonuc["available"] is False
    assert sonuc["reason"]


def test_bes_yillik_pencere_isteniyor():
    """`_returns()` ile aynı pencere (`first_range='5y'`) istenmeli — tutarlılık."""
    istemci = _SahteIstemci(seri=_seri(252))
    RISK.symbol_price_stats(istemci, "TEST.IS")
    assert istemci.cagrilar[0][1] == "5y"
