"""Mali tabloların normalize edilmesi.

Bu modül ham Yahoo çıktısını, oran hesaplayan modüllerin (health, reports,
flags) güvenle kullanabileceği tek bir pakete çevirir. Üç işi var:

1. **Para birimi çözümleme.** Yahoo'nun kalem bazlı `currencyCode` etiketi
   güvenilmez: THYAO'nun yıllık gelir serisinde etiket TRY/USD arasında
   zıplarken değerler homojen USD kalıyor. Doğru kaynak profildeki
   `financialCurrency`; etiket tutarsızlığı ancak değerlerde gerçek bir
   büyüklük sıçraması varsa ciddiye alınıyor (bkz. `_has_magnitude_break`).

2. **Dönem hizalama ve TTM.** Kalemler ayrı ayrı gelir; burada tarihe göre
   hizalanıp tek satır haline getirilir. TTM'de akış kalemleri (gelir, kâr,
   nakit akışı) son 4 çeyreğin toplamı, stok kalemleri (varlık, borç,
   özsermaye) son çeyreğin değeridir — ikisini karıştırmak klasik hatadır.

3. **Türetilmiş kalemler.** Yahoo'nun vermediği ama aritmetikle çıkan
   kalemler (toplam yükümlülük, net borç, serbest nakit akışı) hesaplanır ve
   `derived` listesinde işaretlenir; ekranda "hesaplandı" diye gösterilebilsin
   ve uydurma veriyle karışmasın diye.

Eksik kalem asla sıfır sayılmaz: `values` sözlüğünde hiç bulunmaz, `missing`
listesinde adı geçer.
"""

from __future__ import annotations

from . import bicim as B
from . import cache as cache_mod
from . import universe
from .yahoo import YahooClient, YahooError

# Akış kalemleri: dönem boyunca birikir. TTM = son 4 çeyreğin toplamı.
AKIS_KALEMLERI = frozenset(
    {
        "TotalRevenue",
        "GrossProfit",
        "OperatingIncome",
        "EBIT",
        "EBITDA",
        "NetIncome",
        "NetIncomeCommonStockholders",
        "PretaxIncome",
        "TaxProvision",
        "InterestExpense",
        "OperatingCashFlow",
        "FreeCashFlow",
        "CapitalExpenditure",
        "CashDividendsPaid",
        "BasicEPS",
        "DilutedEPS",
    }
)

# Stok kalemleri: belirli bir andaki durum. TTM = en son çeyreğin değeri.
STOK_KALEMLERI = frozenset(
    {
        "TotalAssets",
        "CurrentAssets",
        "CurrentLiabilities",
        "TotalLiabilitiesNetMinorityInterest",
        "StockholdersEquity",
        "RetainedEarnings",
        "LongTermDebt",
        "CurrentDebt",
        "TotalDebt",
        "CashAndCashEquivalents",
        "CashCashEquivalentsAndShortTermInvestments",
        "Inventory",
        "AccountsReceivable",
        "WorkingCapital",
        "OrdinarySharesNumber",
        "ShareIssued",
    }
)

# Bir kalem yoksa sırayla denenecek karşılıklar. Yalnızca gerçekten eşdeğer
# olanlar; "yaklaşık aynı" sayılan kalemler buraya konmaz.
YEDEK_KALEMLER: dict[str, tuple[str, ...]] = {
    "EBIT": ("EBIT", "OperatingIncome"),
    "OperatingIncome": ("OperatingIncome", "EBIT"),
    "NetIncome": ("NetIncome", "NetIncomeCommonStockholders"),
    "CashAndCashEquivalents": (
        "CashAndCashEquivalents",
        "CashCashEquivalentsAndShortTermInvestments",
    ),
}

# Gerçek para birimi değişimi ardışık değerlerde 30-50 kat sıçrama yaratır
# (USD/TRY ~47). Normal yıllık büyüme yüksek enflasyonda bile 3-4 katı geçmez.
# 8 kat eşiği ikisini rahatça ayırıyor.
BUYUKLUK_SICRAMA_ESIGI = 8.0

TTL_KUR = 12 * cache_mod.SAAT


def load(client: YahooClient, symbol: str, profile: dict | None = None) -> dict:
    """Sembol için normalize edilmiş mali tablo paketi döndürür."""
    if profile is None:
        try:
            profile = client.profile(symbol)
        except YahooError:
            profile = {}

    annual_table = client.fundamentals(symbol, "annual")
    try:
        quarterly_table = client.fundamentals(symbol, "quarterly")
    except YahooError:
        quarterly_table = {"fields": {}}

    currency, currency_source, notes = _resolve_currency(
        profile, (annual_table, quarterly_table)
    )

    annual_rows = _align(annual_table)
    quarterly_rows = _align(quarterly_table)

    available = sorted(
        set(annual_table.get("fields", {})) | set(quarterly_table.get("fields", {}))
    )
    expected = AKIS_KALEMLERI | STOK_KALEMLERI
    missing = sorted(expected - set(available))

    sector = profile.get("sector")
    industry = profile.get("industry")

    pack = {
        "symbol": symbol,
        "name": profile.get("name"),
        "sector": sector,
        "industry": industry,
        # Ülke, EUR raporlayan şirketlerde hangi ülkenin TÜFE'siyle deflate
        # edileceğini belirler (euro bölgesi agregatı veri kaynağında yok).
        "country": profile.get("country"),
        "bank_accounting": universe.uses_bank_accounting(sector, industry),
        "currency": currency,
        "currency_source": currency_source,
        "currency_notes": notes,
        "price_currency": profile.get("price_currency"),
        "market_cap": profile.get("market_cap"),
        "last_price": profile.get("last_price"),
        "shares_outstanding": profile.get("shares_outstanding"),
        "annual": annual_rows,
        "quarterly": quarterly_rows,
        "ttm": _compute_ttm(quarterly_rows),
        "available": available,
        "missing": missing,
    }
    reliable, note = _market_cap_reliable(pack)
    pack["market_cap_reliable"] = reliable
    pack["market_cap_note"] = note
    pack["freshness"] = _freshness(annual_rows, quarterly_rows)
    return pack


# Tazelik eşikleri (ay). Bir şirketin son raporu bu kadar eskiyse, hesaplanan
# her metrik o kadar eski demektir — skorun kendisi doğru olsa bile "bugünkü
# durum" değildir.
BAYAT_AY = 8          # çeyrek raporlayan bir şirkette 2 dönem gecikme
COK_BAYAT_AY = 14     # bir yıllık raporu bile kaçırmış
YILLIK_BAYAT_AY = 15  # F-Skoru'nun dayandığı yıllık tablo eskimiş

GUN_AY = 30.44  # ortalama ay uzunluğu


def _freshness(annual_rows: list[dict], quarterly_rows: list[dict]) -> dict:
    """Paketin ne kadar güncel olduğu.

    NETCD vakası: son yıllık tablo 2024-12, son çeyrek 2025-09 — Temmuz
    2026'da bakıldığında F-Skoru 19 aylık bir tablodan geliyordu ama ekranda
    hiçbir yerde bu yazmıyordu. "9/9" rakamı doğruydu, sunumu yanıltıcıydı.

    Yaş, bugünden **dönem sonuna** göre ölçülür. Şirketler raporlarını dönem
    bitiminden 1-3 ay sonra yayımladığı için 3-4 aylık bir yaş normaldir;
    eşikler buna göre seçildi.
    """
    from datetime import date

    def yas_ay(iso: str | None):
        if not iso:
            return None
        try:
            gun = (date.today() - date.fromisoformat(iso)).days
        except (TypeError, ValueError):
            return None
        return round(gun / GUN_AY, 1)

    son_yillik = annual_rows[-1]["date"] if annual_rows else None
    son_ceyrek = quarterly_rows[-1]["date"] if quarterly_rows else None

    adaylar = [d for d in (son_yillik, son_ceyrek) if d]
    en_son = max(adaylar) if adaylar else None

    yas = yas_ay(en_son)
    yillik_yas = yas_ay(son_yillik)

    if yas is None:
        seviye = "bilinmiyor"
    elif yas >= COK_BAYAT_AY:
        seviye = "cok_bayat"
    elif yas >= BAYAT_AY:
        seviye = "bayat"
    else:
        seviye = "taze"

    return {
        "last_annual": son_yillik,
        "last_quarterly": son_ceyrek,
        "latest_period": en_son,
        "age_months": yas,
        "annual_age_months": yillik_yas,
        "level": seviye,
        "annual_stale": bool(yillik_yas is not None and yillik_yas >= YILLIK_BAYAT_AY),
        "label": _tazelik_etiketi(yas),
    }


def _tazelik_etiketi(yas) -> str | None:
    """İnsan okunur yaş: "10 ay önce"."""
    if yas is None:
        return None
    if yas < 1.5:
        return "bu ay"
    if yas < 24:
        return f"{B.sayi(yas, 0)} ay önce"
    return f"{B.sayi(yas / 12, 1)} yıl önce"


# Yahoo'nun hisse sayısı ile tablo hisse sayısı arasında bu kattan fazla fark
# varsa iki kaynak farklı bir menkul kıymetten bahsediyor demektir.
HISSE_SAYISI_TUTARSIZLIK_KATI = 5.0


def _market_cap_reliable(pack: dict) -> tuple[bool, str | None]:
    """Piyasa değeri bu şirkette güvenilir mi?

    ISBTR.IS (İş Bankası kurucu senetleri) vakası: kurucu senedinden yalnızca
    29.000 adet var ve tanesi ~499.000 TL. Yahoo bu fiyatı bankanın 25 milyar
    adetlik normal hisse sayısıyla çarpıyor ve piyasa değerini 12,5 katrilyon
    TL gösteriyor — PD/DD 29.628 çıkıyor.

    Test iki koşulu birlikte arar:
      1. Bildirilen piyasa değeri, fiyat × **tablo** hisse sayısına eşit
         (yani Yahoo tablo hisse sayısını kullanmış), ve
      2. Yahoo'nun kendi `sharesOutstanding` değeri tablo hisse sayısından
         5 kattan fazla farklı (yani doğru sayı bu değil).

    İkisi birlikte olmadan bayrak kalkmaz; ADR'lerde hisse sayıları meşru
    olarak farklıdır ama piyasa değeri fiyat × tablo hisse sayısına eşit
    çıkmaz, dolayısıyla yanlışlıkla elenmezler.
    """
    market_cap = pack.get("market_cap")
    price = pack.get("last_price")
    reported_shares = pack.get("shares_outstanding")
    statement_shares = stock_value(pack, "OrdinarySharesNumber")["value"]

    if not market_cap or not price or not statement_shares or not reported_shares:
        return True, None

    implied = price * statement_shares
    used_statement_shares = abs(implied - market_cap) / market_cap < 0.02
    share_gap = max(reported_shares, statement_shares) / min(reported_shares, statement_shares)

    if used_statement_shares and share_gap > HISSE_SAYISI_TUTARSIZLIK_KATI:
        return False, (
            f"Piyasa değeri güvenilmez: kaynak, {_tr_sayi(price, 2)} birim fiyatı "
            f"{_tr_sayi(statement_shares)} adetlik tablo hisse sayısıyla çarpmış, ama "
            f"bildirilen dolaşımdaki hisse sayısı {_tr_sayi(reported_shares)}. "
            "Muhtemelen aynı şirketin farklı bir pay sınıfı (ör. kurucu senedi). "
            "Piyasa değerine dayanan oranlar (F/K, PD/DD, Altman Z) hesaplanmadı."
        )
    return True, None


def tr_sayi(value, ondalik: int = 0, isaretli: bool = False) -> str:
    """Türkçe sayı biçimi: binlik nokta, ondalık virgül.

    Biçimlendirme yalnızca sayıya uygulanır. Daha önce hazır cümlenin tamamına
    `.replace(",", ".")` çağrılıyordu ve cümledeki virgüller de noktaya
    dönüşüp "kaynak. 498.992.50 ... çarpmış. ama" gibi bozuk metin çıkıyordu.

    Ondalık ayracının virgül olması şart: arayüz sayıları Türkçe biçimde
    gösterirken metin cümleleri "%-7.6" derse aynı ekranda iki farklı sayı
    yazımı görünüyor.
    """
    if value is None:
        return "—"
    bicim = "+,." if isaretli else ",."
    text = f"{value:{bicim}{ondalik}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# Eski ad, iç kullanım için korunuyor.
_tr_sayi = tr_sayi


# ------------------------------------------------------------- para birimi


# Yahoo bazı BIST sembollerinde (ör. MCARD.IS) kalem etiketlerini hâlâ
# 2005 redenominasyonu öncesi eski ISO koduyla ("TRL") damgalıyor. Bu bir
# farklı para birimi değil, aynı liranın eski adı — normalize edilmezse
# şirket yanlışlıkla "para birimi belirsiz" (Y5) sayılır.
PARA_BIRIMI_TAKMA_ADLAR = {"TRL": "TRY"}


def _resolve_currency(profile: dict, tables) -> tuple[str | None, str, list[str]]:
    """(para_birimi, kaynak, notlar) döndürür.

    Kaynak "profile" ise `financialCurrency` kullanıldı; "labels" ise profil
    boştu ve kalem etiketlerinin çoğunluğuna bakıldı; None ise belirlenemedi.
    """
    notes: list[str] = []
    labels: dict[str, int] = {}
    for table in tables:
        for points in (table.get("fields") or {}).values():
            for point in points:
                code = point.get("currency")
                if code:
                    code = PARA_BIRIMI_TAKMA_ADLAR.get(code, code)
                    labels[code] = labels.get(code, 0) + 1

    declared = profile.get("financial_currency")
    if declared:
        declared = PARA_BIRIMI_TAKMA_ADLAR.get(declared, declared)
    label_set = set(labels)
    mixed = len(label_set) > 1

    if mixed:
        if _has_magnitude_break(tables):
            notes.append(
                "Kalem para birimi etiketleri değişiyor ve değerlerde buna uyan "
                "bir büyüklük sıçraması var: seri gerçekten karışık, mutlak "
                "tutarlar güvenilmez."
            )
            return declared, "profile" if declared else "belirsiz", notes
        notes.append(
            "Kalem para birimi etiketleri dönemden döneme değişiyor ama "
            "değerlerde büyüklük sıçraması yok; seri homojen kabul edildi "
            f"({', '.join(sorted(label_set))} etiketleri görüldü)."
        )

    if declared:
        if label_set and declared not in label_set:
            notes.append(
                f"Profil {declared} diyor, kalem etiketleri "
                f"{', '.join(sorted(label_set))} diyor; profil esas alındı."
            )
        return declared, "profile", notes

    if labels:
        winner = max(labels, key=labels.get)
        notes.append("Profilde para birimi yok; kalem etiketlerinin çoğunluğu alındı.")
        return winner, "labels", notes

    notes.append("Para birimi belirlenemedi.")
    return None, "belirsiz", notes


# Büyüklük sıçraması testi yalnızca bu kalemlerde çalışır. Gerçek bir şirkette
# bunlar yıldan yıla 8 kat zıplamaz; capex, faiz gideri veya vergi karşılığı
# gibi oynak kalemler ise iş sebepleriyle zıplayabilir. İlk sürümde test tüm
# kalemlere uygulanıyordu ve THYAO gibi verisi aslında tutarlı olan şirketlere
# yanlışlıkla "para birimi belirsiz" damgası vuruyordu.
ISTIKRARLI_KALEMLER = ("TotalRevenue", "TotalAssets", "StockholdersEquity")


def _has_magnitude_break(tables) -> bool:
    """Etiket değişimiyle birlikte gerçek bir büyüklük sıçraması var mı?

    Sadece etiketin değişmesi yetmez — Yahoo etiketi sallıyor. Ancak istikrarlı
    bir toplam kalemde, etiketin değiştiği yerde değer de 8 kattan fazla
    zıplıyorsa seri gerçekten karışık demektir.
    """
    for table in tables:
        fields = table.get("fields") or {}
        for name in ISTIKRARLI_KALEMLER:
            points = fields.get(name) or []
            for previous, current in zip(points, points[1:]):
                if previous.get("currency") == current.get("currency"):
                    continue
                before, after = previous.get("value"), current.get("value")
                if not before or not after:
                    continue
                ratio = abs(after) / abs(before)
                if ratio > BUYUKLUK_SICRAMA_ESIGI or ratio < 1 / BUYUKLUK_SICRAMA_ESIGI:
                    return True
    return False


# ------------------------------------------------------------ dönem hizalama


def _align(table: dict) -> list[dict]:
    """Kalemleri tarihe göre hizalayıp satır listesi yapar (artan sırada)."""
    fields = table.get("fields") or {}
    index: dict[str, dict[str, float]] = {}
    for name, points in fields.items():
        for point in points:
            date = point.get("date")
            if not date:
                continue
            index.setdefault(date, {})[name] = point["value"]

    rows = []
    for date in sorted(index):
        values = dict(index[date])
        derived = _add_derived(values)
        rows.append({"date": date, "values": values, "derived": derived})
    return rows


def _add_derived(values: dict) -> list[str]:
    """Aritmetikle çıkarılabilen kalemleri ekler, adlarını döndürür."""
    derived: list[str] = []

    if "TotalLiabilitiesNetMinorityInterest" in values:
        values.setdefault("TotalLiabilities", values["TotalLiabilitiesNetMinorityInterest"])
    elif "TotalAssets" in values and "StockholdersEquity" in values:
        values["TotalLiabilities"] = values["TotalAssets"] - values["StockholdersEquity"]
        derived.append("TotalLiabilities")

    if "TotalDebt" in values:
        cash = values.get("CashAndCashEquivalents")
        if cash is None:
            cash = values.get("CashCashEquivalentsAndShortTermInvestments")
        if cash is not None:
            values["NetDebt"] = values["TotalDebt"] - cash
            derived.append("NetDebt")

    if "WorkingCapital" not in values:
        if "CurrentAssets" in values and "CurrentLiabilities" in values:
            values["WorkingCapital"] = values["CurrentAssets"] - values["CurrentLiabilities"]
            derived.append("WorkingCapital")

    if "FreeCashFlow" not in values:
        # Yahoo'da CapitalExpenditure negatif gelir, o yüzden toplama.
        if "OperatingCashFlow" in values and "CapitalExpenditure" in values:
            values["FreeCashFlow"] = (
                values["OperatingCashFlow"] + values["CapitalExpenditure"]
            )
            derived.append("FreeCashFlow")

    return derived


def _compute_ttm(quarterly_rows: list[dict]) -> dict:
    """Son 12 ayın rakamları.

    İki kural var:

    - Akış kalemlerinde 4 çeyreğin tamamı gelmiyorsa kalem hiç üretilmez;
      eksik çeyreği yok saymak TTM'yi olduğundan küçük gösterirdi.
    - Son 4 çeyrek **ardışık** olmalı. AKBNK'ta Yahoo 2025-09-30'u atlıyor
      (`2025-06-30` sonrası doğrudan `2025-12-31` geliyor); son dört satırı
      körlemesine toplamak, ortasında delik olan sahte bir "12 ay" üretir.
      Ardışıklık bozuksa akış kalemleri hiç hesaplanmaz, sebebi `_note`'a
      yazılır ve çağıran taraf yıllık rakama düşer (bkz. `flow_value`).

    Stok kalemleri (varlık, borç, özsermaye) her hâlükârda en son çeyrekten
    alınır — bilanço oranları için doğru taban son yıllık değil son çeyrektir.
    """
    if not quarterly_rows:
        return {}

    window = quarterly_rows[-4:]
    ttm: dict[str, float] = {
        "_periods": len(window),
        "_end": window[-1]["date"],
        "_consecutive": True,
    }

    consecutive = len(window) == 4 and _quarters_consecutive(window)
    ttm["_consecutive"] = consecutive

    if len(window) == 4 and not consecutive:
        ttm["_note"] = (
            "Son dört çeyrek ardışık değil (Yahoo'da eksik dönem var); "
            "12 aylık akış kalemleri hesaplanmadı."
        )

    if consecutive:
        names: set[str] = set()
        for row in window:
            names |= set(row["values"])
        for name in names:
            if name not in AKIS_KALEMLERI and name != "FreeCashFlow":
                continue
            parts = [row["values"].get(name) for row in window]
            if all(part is not None for part in parts):
                ttm[name] = sum(parts)

    for name, value in window[-1]["values"].items():
        if name in STOK_KALEMLERI or name in ("TotalLiabilities", "NetDebt"):
            ttm[name] = value

    return ttm


def _quarters_consecutive(window: list[dict]) -> bool:
    """Pencerédeki çeyrekler gerçekten peş peşe mi?

    Çeyrek arası 60-125 gün beklenir; mali yıl kaymaları ve 52/53 haftalık
    takvimler bu aralığa sığar, atlanmış bir çeyrek sığmaz.
    """
    for previous, current in zip(window, window[1:]):
        gap = _days_between_iso(previous["date"], current["date"])
        if gap is None or not (60 <= gap <= 125):
            return False
    return True


def _days_between_iso(start: str, end: str) -> int | None:
    from datetime import date

    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ erişim


def rows(pack: dict, period: str = "annual") -> list[dict]:
    return pack.get("annual" if period == "annual" else "quarterly") or []


def series(pack: dict, field: str, period: str = "annual") -> list[tuple[str, float]]:
    """(tarih, değer) çiftleri. Yedek kalem eşlemesi uygulanır."""
    names = YEDEK_KALEMLER.get(field, (field,))
    out: list[tuple[str, float]] = []
    for row in rows(pack, period):
        for name in names:
            if name in row["values"]:
                out.append((row["date"], row["values"][name]))
                break
    return out


def value_at(pack: dict, field: str, index: int = -1, period: str = "annual"):
    """Belirli dönemdeki değer; index -1 en son dönem. Yoksa None."""
    points = series(pack, field, period)
    if not points:
        return None
    try:
        return points[index][1]
    except IndexError:
        return None


def ttm_value(pack: dict, field: str):
    ttm = pack.get("ttm") or {}
    for name in YEDEK_KALEMLER.get(field, (field,)):
        if name in ttm:
            return ttm[name]
    return None


def flow_value(pack: dict, field: str) -> dict:
    """Akış kalemi için en iyi 12 aylık değer ve hangi tabandan geldiği.

    Dönüş: `{"value", "basis", "end"}`. `basis` "TTM" ise son dört çeyreğin
    toplamı, "yıllık" ise son mali yıl. Ekranda bu etiket gösterilecek —
    kullanıcı rakamın hangi döneme ait olduğunu bilmeden oran okuyamaz.
    """
    value = ttm_value(pack, field)
    if value is not None:
        return {"value": value, "basis": "TTM", "end": (pack.get("ttm") or {}).get("_end")}
    points = series(pack, field, "annual")
    if points:
        return {"value": points[-1][1], "basis": "yıllık", "end": points[-1][0]}
    return {"value": None, "basis": None, "end": None}


def stock_value(pack: dict, field: str) -> dict:
    """Bilanço kalemi için en güncel değer: önce son çeyrek, sonra son yıl.

    Bilanço oranlarının (PD/DD, borç/özsermaye) tabanı son yıllık değil son
    çeyrek olmalı; aradan iki çeyrek geçmişse yıllık özsermaye eskimiştir.
    """
    ttm = pack.get("ttm") or {}
    for name in YEDEK_KALEMLER.get(field, (field,)):
        if name in ttm:
            return {"value": ttm[name], "basis": "çeyrek", "end": ttm.get("_end")}
    points = series(pack, field, "annual")
    if points:
        return {"value": points[-1][1], "basis": "yıllık", "end": points[-1][0]}
    return {"value": None, "basis": None, "end": None}


def has(pack: dict, field: str, period: str = "annual") -> bool:
    return bool(series(pack, field, period))


def period_dates(pack: dict, period: str = "annual") -> list[str]:
    return [row["date"] for row in rows(pack, period)]


def growth(pack: dict, field: str, period: str = "annual", lag: int = 1):
    """Nominal büyüme oranı (0,41 = %41). Hesaplanamıyorsa None.

    Negatif tabandan büyüme oranı anlamsızdır (zarardan zarara "%150 büyüme"
    gibi saçmalıklar çıkar), o yüzden taban pozitif değilse None döner.
    """
    points = series(pack, field, period)
    if len(points) <= lag:
        return None
    before = points[-1 - lag][1]
    after = points[-1][1]
    if before is None or after is None or before <= 0:
        return None
    return after / before - 1.0


# --------------------------------------------------------------------- kur


def fx_rate(client: YahooClient, base: str | None, quote: str | None):
    """1 birim `base` kaç `quote` eder? Bulunamazsa None."""
    if not base or not quote:
        return None
    if base == quote:
        return 1.0

    key = f"{base}_{quote}"
    cached = client.cache.get_record("fx", key, ttl=TTL_KUR)
    if cached is not None:
        return cached

    rate = None
    try:
        rate = client.chart(f"{base}{quote}=X", range_="5d")["last_price"]
    except YahooError:
        rate = None
    if not rate:
        try:
            inverse = client.chart(f"{quote}{base}=X", range_="5d")["last_price"]
            rate = 1.0 / inverse if inverse else None
        except YahooError:
            rate = None

    if rate:
        client.cache.set_record("fx", key, rate)
    return rate


def market_cap_in_statement_currency(client: YahooClient, pack: dict):
    """Piyasa değerini mali tabloların para birimine çevirir.

    THYAO gibi tabloları USD, hissesi TRY olan şirketlerde bu dönüşüm
    yapılmazsa F/K ve PD/DD ~47 kat yanlış çıkar. Yahoo'nun kendi
    `trailingPE`/`priceToBook` alanları tam bu hataya düşüyor, o yüzden onlar
    kullanılmıyor.
    """
    market_cap = pack.get("market_cap")
    if not market_cap:
        return None
    # Güvenilmez piyasa değeri tek noktadan kesilir; böylece F/K, PD/DD ve
    # Altman Z'nin hepsi otomatik olarak "hesaplanamadı" durumuna düşer.
    if pack.get("market_cap_reliable") is False:
        return None
    rate = fx_rate(client, pack.get("price_currency"), pack.get("currency"))
    if rate is None:
        return None
    return market_cap * rate
