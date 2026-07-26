"""Sayı biçimlendirme — tek kaynak.

Ekranda görünen her sayı buradan geçer. Ayrı ayrı f-string'lerle
biçimlendirilince aynı ekranda iki farklı yazım oluşuyordu: arayüz "%-7,6"
derken Python'dan gelen cümle "%-7.6" diyordu.

Türkçe kural: binlik ayracı nokta, ondalık ayracı virgül.
"""

from __future__ import annotations

# Altman Z-Skoru 2,99 üstünü modelin tanımına göre tek bir "güvenli bölge"
# sayar; bu eşiğin çok ötesindeki farklar (5 ile 60 arası gibi) anlam
# taşımaz — formülde piyasa değeri/toplam yükümlülük terimi, yükümlülük
# sıfıra yaklaştıkça patlar. Arayüz ve CLI aynı tavanı kullanır.
ALTMAN_TAVAN = 10


def altman(value) -> str:
    """Altman Z gösterimi: tavanın üstünde '10+', tam değer çağıran tarafta."""
    if value is None:
        return "—"
    if value > ALTMAN_TAVAN:
        return f"{ALTMAN_TAVAN}+"
    return sayi(value, 2)


def sayi(value, ondalik: int = 2, isaretli: bool = False) -> str:
    """Türkçe biçimde sayı. None ise em dash."""
    if value is None:
        return "—"
    # Yuvarlanınca sıfır olan negatifler "-0,0" diye görünmesin.
    esik = 0.5 * 10 ** -ondalik
    if abs(value) < esik:
        value = 0.0
    bicim = "+,." if isaretli else ",."
    text = f"{value:{bicim}{ondalik}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def yuzde(value, ondalik: int = 1, isaretli: bool = True) -> str:
    """Oranı yüzdeye çevirir: 0,415 → "%+41,5"."""
    if value is None:
        return "—"
    return f"%{sayi(value * 100, ondalik, isaretli)}"


def puan(value, ondalik: int = 1, isaretli: bool = False) -> str:
    """Zaten puan cinsinden gelen değer: 27,61 → "%27,6"."""
    if value is None:
        return "—"
    return f"%{sayi(value, ondalik, isaretli)}"


def oran(value, ondalik: int = 2) -> str:
    """Kat cinsinden oran: 2,197 → "2,20"."""
    return sayi(value, ondalik)


def kat(value, ondalik: int = 1) -> str:
    """Çarpan: 37,47 → "37,5 kat"."""
    if value is None:
        return "—"
    return f"{sayi(value, ondalik)} kat"


def para(value, ondalik: int = 0) -> str:
    """Büyük tutarı okunur ölçeğe indirir: 39733712000 → "39,73 milyar".

    Cümle içi kullanım için (özet metinleri, tam genişlikli paneller). Dar
    tablo hücrelerinde `para_kisa` kullanılır — ikisi kasıtlı olarak farklı:
    biri okunurluk, diğeri yer tasarrufu önceliklidir.
    """
    if value is None:
        return "—"
    for limit, ek in ((1e12, " trilyon"), (1e9, " milyar"), (1e6, " milyon")):
        if abs(value) >= limit:
            return f"{sayi(value / limit, 2)}{ek}"
    return sayi(value, ondalik)


def para_kisa(value) -> str:
    """Tablo hücresi için kısaltılmış tutar: 2500000000 → "2,50Mr".

    `para()`'nın cümle-içi verbose biçiminin ("2,50 milyar") aksine, dar
    sütunlu tablolarda (tarayıcı sonuçları) kullanılan kompakt biçim. Bu iki
    biçim kasıtlı olarak ayrı tutuluyor; web/app.js'teki `para()` fonksiyonu
    da aynı kompakt kısaltmaları (T/Mr/Mn/B) kullanır.
    """
    if value is None:
        return "—"
    for limit, ek in ((1e12, "T"), (1e9, "Mr"), (1e6, "Mn"), (1e3, "B")):
        if abs(value) >= limit:
            return f"{sayi(value / limit, 2)}{ek}"
    return sayi(value, 0)
