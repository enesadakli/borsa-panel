"""Portföy matematiği testi.

Elle hesaplanmış senaryolarla karşılaştırma yapılır — motorun kendi çıktısına
bakıp "doğru görünüyor" demek yeterli değil, beklenen sayı önceden bilinmeli.

Kritik test `test_kur_ayristirmasi_toplama_esit`: hisse getirisi ile kur
getirisinin bileşimi toplam getiriye eşit olmalı. Dolar bazında zarardayken TL
bazında kârlı görünmek en yaygın yanılgı, bu yüzden ayrıştırmanın kimliği
testle korunuyor.

Bu testler ağa çıkmaz; işlem listeleri doğrudan fonksiyonlara verilir.
"""

from __future__ import annotations

from core import portfolio as P


def _islem(date, symbol, side, quantity, price, commission=0.0, fx_rate=None):
    return {
        "date": date, "symbol": symbol, "side": side, "quantity": quantity,
        "price": price, "commission": commission, "fx_rate": fx_rate,
    }


# ----------------------------------------------------- ortalama maliyet / K/Z


def test_agirlikli_ortalama_maliyet():
    """100 adet 10 TL + 100 adet 20 TL → ortalama 15 TL."""
    trades = [
        _islem("2026-01-05", "TEST.IS", P.ALIM, 100, 10.0),
        _islem("2026-02-05", "TEST.IS", P.ALIM, 100, 20.0),
    ]
    pozisyon = P.build_positions(trades)["positions"]["TEST.IS"]
    assert pozisyon["quantity"] == 200
    assert abs(pozisyon["avg_cost"] - 15.0) < 1e-9, f"beklenen 15,00 geldi {pozisyon['avg_cost']}"
    assert abs(pozisyon["cost_total"] - 3000.0) < 1e-9


def test_komisyon_maliyete_ekleniyor():
    """100 × 10 TL + 25 TL komisyon → birim maliyet 10,25 TL."""
    trades = [_islem("2026-01-05", "TEST.IS", P.ALIM, 100, 10.0, commission=25.0)]
    pozisyon = P.build_positions(trades)["positions"]["TEST.IS"]
    assert abs(pozisyon["cost_total"] - 1025.0) < 1e-9
    assert abs(pozisyon["avg_cost"] - 10.25) < 1e-9


def test_kismi_satis_elle_hesapla():
    """Plandaki senaryo: 2 alım farklı fiyattan + 1 kısmi satış + komisyon.

    Alım 1: 100 × 10,00 + 5 komisyon  = 1005 TL
    Alım 2: 100 × 20,00 + 5 komisyon  = 2005 TL
    Toplam maliyet 3010 TL / 200 adet = 15,05 TL birim
    Satış:  50 × 25,00 − 5 komisyon   = 1245 TL hasılat
    Satılanın maliyeti 50 × 15,05     = 752,50 TL
    Gerçekleşmiş kâr = 1245 − 752,50  = 492,50 TL
    Kalan: 150 adet, maliyet 3010 − 752,50 = 2257,50 TL (birim 15,05 TL)
    """
    trades = [
        _islem("2026-01-05", "TEST.IS", P.ALIM, 100, 10.0, commission=5.0),
        _islem("2026-02-05", "TEST.IS", P.ALIM, 100, 20.0, commission=5.0),
        _islem("2026-03-05", "TEST.IS", P.SATIM, 50, 25.0, commission=5.0),
    ]
    pozisyon = P.build_positions(trades)["positions"]["TEST.IS"]

    assert pozisyon["quantity"] == 150
    assert abs(pozisyon["realized"] - 492.50) < 1e-6, (
        f"gerçekleşmiş K/Z beklenen 492,50 geldi {pozisyon['realized']:.2f}"
    )
    assert abs(pozisyon["cost_total"] - 2257.50) < 1e-6
    assert abs(pozisyon["avg_cost"] - 15.05) < 1e-9, (
        "kısmi satış ortalama maliyeti değiştirmemeli"
    )


def test_fazla_satis_uyari_uretiyor():
    trades = [
        _islem("2026-01-05", "TEST.IS", P.ALIM, 100, 10.0),
        _islem("2026-02-05", "TEST.IS", P.SATIM, 150, 12.0),
    ]
    sonuc = P.build_positions(trades)
    assert sonuc["warnings"], "elde olandan fazla satış uyarı üretmeli"
    assert sonuc["positions"]["TEST.IS"]["quantity"] == 0, "adet negatife düşmemeli"


def test_tam_satis_pozisyonu_kapatiyor():
    trades = [
        _islem("2026-01-05", "TEST.IS", P.ALIM, 100, 10.0),
        _islem("2026-02-05", "TEST.IS", P.SATIM, 100, 15.0),
    ]
    pozisyon = P.build_positions(trades)["positions"]["TEST.IS"]
    assert pozisyon["quantity"] == 0
    assert abs(pozisyon["realized"] - 500.0) < 1e-9
    assert abs(pozisyon["cost_total"]) < 1e-9, "kapanan pozisyonda maliyet sıfırlanmalı"


# ------------------------------------------------------------ kur ayrıştırması


def test_kur_ayristirmasi_toplama_esit():
    """(1+hisse) × (1+kur) = 1+toplam kimliği korunmalı.

    Senaryo: 10 adet AAPL, 100 USD'den, kur 30. Şimdi fiyat 110 USD, kur 45.
    Hisse getirisi %10, kur getirisi %50 → toplam %65 (toplama %60 derdi).
    """
    trades = [_islem("2026-01-05", "AAPL", P.ALIM, 10, 100.0, fx_rate=30.0)]
    pozisyon = P.build_positions(trades)["positions"]["AAPL"]

    split = P._fx_split(pozisyon, price=110.0, current_rate=45.0)
    assert split["available"], split.get("reason")
    assert abs(split["share_return"] - 0.10) < 1e-9
    assert abs(split["fx_return"] - 0.50) < 1e-9

    beklenen = (1 + split["share_return"]) * (1 + split["fx_return"]) - 1
    assert abs(split["total_return"] - beklenen) < 1e-12
    assert abs(split["total_return"] - 0.65) < 1e-9, (
        f"toplam getiri %65 olmalı, geldi %{split['total_return'] * 100:.2f}"
    )
    # Toplama yöntemi %60 derdi; fark 5 puan.
    assert abs(split["total_return"] - 0.60) > 0.04


def test_dolar_bazinda_zarar_tl_bazinda_kar():
    """Asıl yanılgı: hisse dolar bazında düşmüş ama TL getirisi pozitif."""
    trades = [_islem("2026-01-05", "AAPL", P.ALIM, 10, 100.0, fx_rate=30.0)]
    pozisyon = P.build_positions(trades)["positions"]["AAPL"]

    split = P._fx_split(pozisyon, price=90.0, current_rate=45.0)
    assert split["share_return"] < 0, "hisse dolar bazında zararda"
    assert split["fx_return"] > 0
    assert split["total_return"] > 0, "TL bazında kârlı görünüyor"
    # Kazancın tamamı kurdan; ayrıştırma bunu görünür kılıyor.
    assert abs(split["total_return"] - (0.9 * 1.5 - 1)) < 1e-9


def test_kur_kaydi_yoksa_ayristirma_yapilmiyor():
    """Giriş kuru bilinmiyorsa uydurulmuş bir kur getirisi üretilmemeli."""
    trades = [_islem("2026-01-05", "AAPL", P.ALIM, 10, 100.0)]
    pozisyon = P.build_positions(trades)["positions"]["AAPL"]
    split = P._fx_split(pozisyon, price=110.0, current_rate=45.0)
    assert split["available"] is False
    assert "fx_rate" in split["reason"]


def test_agirlikli_giris_kuru():
    """Farklı kurlardan iki alım → adet-ağırlıklı ortalama kur."""
    trades = [
        _islem("2026-01-05", "AAPL", P.ALIM, 10, 100.0, fx_rate=30.0),
        _islem("2026-02-05", "AAPL", P.ALIM, 30, 100.0, fx_rate=40.0),
    ]
    pozisyon = P.build_positions(trades)["positions"]["AAPL"]
    # (10×30 + 30×40) / 40 = 37,5
    assert abs(P._weighted_fx(pozisyon) - 37.5) < 1e-9


# ------------------------------------------------------------------ doğrulama


def test_gecersiz_islemler_reddediliyor():
    hatali = [
        {"date": "2026-01-05", "symbol": "", "side": P.ALIM, "quantity": 1, "price": 1},
        {"date": "2026-01-05", "symbol": "X", "side": "kirala", "quantity": 1, "price": 1},
        {"date": "2026-01-05", "symbol": "X", "side": P.ALIM, "quantity": 0, "price": 1},
        {"date": "2026-01-05", "symbol": "X", "side": P.ALIM, "quantity": 1, "price": -5},
        {"date": "05.01.2026", "symbol": "X", "side": P.ALIM, "quantity": 1, "price": 1},
        {"date": "2026-01-05", "symbol": "X", "side": P.ALIM, "quantity": 1, "price": 1,
         "commission": -1},
    ]
    for trade in hatali:
        try:
            P.validate_trade(trade)
        except P.PortfolioError:
            continue
        raise AssertionError(f"geçersiz işlem kabul edildi: {trade}")


def test_sembol_buyuk_harfe_ceviriliyor():
    temiz = P.validate_trade(
        {"date": "2026-01-05", "symbol": " sise.is ", "side": "ALIM",
         "quantity": 10, "price": 40}
    )
    assert temiz["symbol"] == "SISE.IS"
    assert temiz["side"] == P.ALIM
