"""Yahoo Finance istemcisi — yalnızca standart kütüphane.

Üç ayrı uç kullanılıyor:

  chart                    : fiyat/OHLC. Kimlik doğrulaması gerektirmez.
  quoteSummary             : profil, sektör, para birimi, piyasa değeri, oranlar.
                             Doğrudan çağrıldığında 401 döner; çerez + "crumb"
                             gerekir.
  fundamentals-timeseries  : yıllık ve çeyreklik mali tablolar. Aynı şekilde
                             crumb ister. Asıl analiz bu uçtan beslenir.

Crumb akışı: fc.yahoo.com'dan çerez alınır (istek 404 dönse de çerez düşer),
sonra /v1/test/getcrumb ile jeton çekilir ve her isteğe eklenir. Jeton
eskidiğinde uç 401 döndürür; istemci jetonu bir kez yenileyip isteği tekrarlar.

Önemli: bu uç, mali tablo kalemlerinin para birimini kalem bazında
`currencyCode` alanında verir. THYAO gibi bazı BIST şirketleri tablolarını USD
açıklar ama hisse TRY işlem görür; ikisini karıştırmak F/K'yı 47 kat yanlış
hesaplatır. Bu yüzden para birimi burada okunup yukarıya taşınır, atılmaz.
"""

from __future__ import annotations

import gzip
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from . import cache as cache_mod

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
TIMESERIES_URL = (
    "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
)
SCREENER_URL = "https://query2.finance.yahoo.com/v1/finance/screener"
CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"
COOKIE_URLS = ("https://fc.yahoo.com/", "https://finance.yahoo.com/")

# Mali tablo kalemleri. Yahoo'nun tip adları "annual"/"quarterly" ön ekiyle
# istenir; yanıtta da aynı adla döner. Ön ek sökülüp temiz ada çevriliyor.
#
# Bu liste THYAO ve SISE üzerinde test edildi: bankalarda GrossProfit, EBITDA,
# CurrentAssets, CurrentLiabilities ve LongTermDebt boş döner. Eksik kalem
# hesapta sıfır sayılmaz, "değerlendirilemedi" olur (bkz. health.py).
GELIR_TABLOSU = (
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
    "BasicEPS",
    "DilutedEPS",
)

BILANCO = (
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
)

NAKIT_AKISI = (
    "OperatingCashFlow",
    "FreeCashFlow",
    "CapitalExpenditure",
    "CashDividendsPaid",
)

YILLIK_ALANLAR = GELIR_TABLOSU + BILANCO + NAKIT_AKISI

# Çeyreklikte daha dar bir set yeterli: rapor okuyucu bu kalemleri kullanıyor.
CEYREKLIK_ALANLAR = (
    "TotalRevenue",
    "GrossProfit",
    "OperatingIncome",
    "EBIT",
    "EBITDA",
    "NetIncome",
    "InterestExpense",
    "TotalAssets",
    "CurrentAssets",
    "CurrentLiabilities",
    "StockholdersEquity",
    "LongTermDebt",
    "CurrentDebt",
    "TotalDebt",
    "CashAndCashEquivalents",
    "OperatingCashFlow",
    "FreeCashFlow",
    "CapitalExpenditure",
    "OrdinarySharesNumber",
    "CashDividendsPaid",
)

PROFIL_MODULLERI = (
    "assetProfile",
    "price",
    "financialData",
    "summaryDetail",
    "defaultKeyStatistics",
)

# Önbellek süreleri
TTL_PROFIL = 12 * cache_mod.SAAT
TTL_MALI_TABLO = 7 * cache_mod.GUN
TTL_SERI_TAZELIK = 15 * cache_mod.DAKIKA


def build_ssl_context() -> ssl.SSLContext:
    """Sertifika doğrulaması açık, RFC katı modu kapalı bir SSL bağlamı.

    Python 3.13 ile birlikte `create_default_context()` varsayılan olarak
    VERIFY_X509_STRICT bayrağını açıyor. Bu makinede kurulu yerel kök
    sertifika (antivirüs HTTPS taraması) RFC 5280'e tam uymadığı için katı mod
    "Basic Constraints of CA cert not marked critical" diyerek her isteği
    reddediyor.

    Sadece bu katılık bayrağını kaldırıyoruz: sertifika zinciri doğrulaması,
    hostname kontrolü ve son kullanma tarihi kontrolü açık kalır. Doğrulamayı
    tamamen kapatmak (CERT_NONE) aynı sorunu çözerdi ama araya girme
    saldırılarına kapı açardı; onu yapmıyoruz.
    """
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


class YahooError(RuntimeError):
    """Yahoo isteği başarısız oldu."""


class YahooNotFound(YahooError):
    """Sembol yok (404). Evren doğrulaması bunu yakalayıp sembolü düşürür."""


class YahooAuthError(YahooError):
    """401 — crumb eskimiş veya çerez düşmemiş."""


class YahooClient:
    """Throttle'lı, yeniden denemeli, önbellekli Yahoo istemcisi."""

    def __init__(
        self,
        cache: cache_mod.Cache | None = None,
        min_interval: float = 0.25,
        max_retries: int = 4,
        timeout: float = 25.0,
    ) -> None:
        self.cache = cache if cache is not None else cache_mod.default_cache()
        self.min_interval = min_interval  # ~4 istek/sn
        self.max_retries = max_retries
        self.timeout = timeout

        self._jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=build_ssl_context()),
            urllib.request.HTTPCookieProcessor(self._jar),
        )
        self._crumb: str | None = None
        self._last_request = 0.0
        self.request_count = 0

    # --------------------------------------------------------------- alt katman

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_request
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_request = time.monotonic()

    def _fetch(
        self,
        url: str,
        retries: int | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        """Ham istek. 429/5xx/ağ hatalarında üstel geri çekilmeyle tekrar dener.

        `data` verilirse POST olur (screener ucu POST istiyor).
        """
        attempts = self.max_retries if retries is None else retries
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(attempts):
            self._throttle()
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Encoding": "gzip",
                "Accept-Language": "tr,en;q=0.8",
            }
            if content_type:
                headers["Content-Type"] = content_type
            request = urllib.request.Request(url, data=data, headers=headers)
            try:
                self.request_count += 1
                with self._opener.open(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        payload = gzip.decompress(payload)
                    return payload
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raise YahooNotFound(f"404: {url}") from error
                if error.code == 401:
                    raise YahooAuthError(f"401: {url}") from error
                if error.code not in (429, 500, 502, 503, 504):
                    raise YahooError(f"HTTP {error.code}: {url}") from error
                last_error = error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error

            if attempt < attempts - 1:
                time.sleep(delay)
                delay *= 2

        raise YahooError(f"{attempts} denemede alınamadı: {url} ({last_error})")

    def _fetch_json(
        self,
        url: str,
        needs_crumb: bool = False,
        payload: dict | None = None,
    ) -> dict:
        """JSON isteği. Crumb gerekiyorsa ekler, 401'de jetonu bir kez yeniler.

        `payload` verilirse gövdesi JSON olan bir POST atılır.
        """
        body = None
        content_type = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            content_type = "application/json"

        target = self._with_crumb(url) if needs_crumb else url
        try:
            raw = self._fetch(target, data=body, content_type=content_type)
        except YahooAuthError:
            if not needs_crumb:
                raise
            self._crumb = None  # jeton eskimiş, yenisini al ve bir kez daha dene
            raw = self._fetch(
                self._with_crumb(url), data=body, content_type=content_type
            )
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as error:
            raise YahooError(f"JSON çözümlenemedi: {url}") from error

    def _with_crumb(self, url: str) -> str:
        crumb = self._ensure_crumb()
        joiner = "&" if "?" in url else "?"
        return f"{url}{joiner}crumb={urllib.parse.quote(crumb)}"

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb

        # Çerez için: fc.yahoo.com 404 dönebilir, önemli olan Set-Cookie.
        for url in COOKIE_URLS:
            try:
                self._fetch(url, retries=1)
            except YahooError:
                pass
            if len(self._jar) > 0:
                break

        crumb = self._fetch(CRUMB_URL, retries=2).decode("utf-8").strip()
        # Onay (consent) sayfasına düşülürse HTML gelir, jeton değil.
        if not crumb or "<" in crumb or len(crumb) > 32:
            raise YahooError(f"Geçerli crumb alınamadı (gelen: {crumb[:40]!r})")
        self._crumb = crumb
        return crumb

    # ------------------------------------------------------------------- fiyat

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        """Fiyat serisi çeker ve düzleştirir. Önbelleğe dokunmaz."""
        query = urllib.parse.urlencode(
            {"range": range_, "interval": interval, "includePrePost": "false"}
        )
        url = f"{CHART_URL}{urllib.parse.quote(symbol)}?{query}"
        payload = self._fetch_json(url)

        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise YahooError(f"{symbol}: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise YahooNotFound(f"{symbol}: chart sonucu boş")

        result = results[0]
        meta = result.get("meta") or {}
        stamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]

        points: dict[str, list] = {}
        for index, stamp in enumerate(stamps):
            date = time.strftime("%Y-%m-%d", time.gmtime(stamp))
            row = [
                _pick(quote.get("open"), index),
                _pick(quote.get("high"), index),
                _pick(quote.get("low"), index),
                _pick(quote.get("close"), index),
                _pick(quote.get("volume"), index),
            ]
            if row[3] is None:  # kapanışı olmayan bar işe yaramaz
                continue
            points[date] = row

        return {
            "symbol": meta.get("symbol", symbol),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "last_price": meta.get("regularMarketPrice"),
            "points": points,
        }

    def refresh_series(self, symbol: str, first_range: str = "2y") -> dict:
        """Kayıtlı seriyi tazeler; yalnızca eksik dönemi çeker.

        Seri hiç yoksa `first_range` kadar geçmiş çekilir. Varsa son kayıtlı
        tarihe göre en küçük yeterli aralık seçilir — 1000 sembollük taramada
        her seferinde 2 yıllık veri çekmemek için.
        """
        age = self.cache.record_age("series", symbol)
        if age is not None and age < TTL_SERI_TAZELIK:
            return self.cache.get_series(symbol)

        last = self.cache.series_last_date(symbol)
        if last is None:
            range_ = first_range
        else:
            gap_days = _days_between(last, time.strftime("%Y-%m-%d", time.gmtime()))
            range_ = _range_for_gap(gap_days)

        chart = self.chart(symbol, range_=range_)
        return self.cache.merge_series(symbol, chart["points"], chart["currency"])

    def series(self, symbol: str, first_range: str = "2y") -> list[tuple[str, float]]:
        """(tarih, kapanış) listesi — gerekirse tazeleyerek."""
        self.refresh_series(symbol, first_range=first_range)
        return self.cache.closes(symbol)

    # ------------------------------------------------------------------ profil

    def profile(self, symbol: str, ttl: float | None = TTL_PROFIL) -> dict:
        """Sektör, para birimi, piyasa değeri ve temel oranlar.

        Dikkat: `financial_currency` mali tabloların para birimi,
        `price_currency` hissenin işlem gördüğü para birimi. THYAO'da bunlar
        farklıdır (USD tablo / TRY fiyat) ve oran hesaplarında karıştırılamaz.
        """
        cached = self.cache.get_record("profile", symbol, ttl=ttl)
        if cached is not None:
            return cached

        query = urllib.parse.urlencode({"modules": ",".join(PROFIL_MODULLERI)})
        url = f"{SUMMARY_URL}{urllib.parse.quote(symbol)}?{query}"
        payload = self._fetch_json(url, needs_crumb=True)

        results = ((payload.get("quoteSummary") or {}).get("result")) or []
        if not results:
            raise YahooNotFound(f"{symbol}: quoteSummary sonucu boş")
        block = results[0]

        asset = block.get("assetProfile") or {}
        price = block.get("price") or {}
        financial = block.get("financialData") or {}
        summary = block.get("summaryDetail") or {}
        stats = block.get("defaultKeyStatistics") or {}

        profile = {
            "symbol": symbol,
            "name": price.get("longName") or price.get("shortName"),
            "sector": asset.get("sector"),
            "industry": asset.get("industry"),
            "country": asset.get("country"),
            "employees": asset.get("fullTimeEmployees"),
            "financial_currency": financial.get("financialCurrency"),
            "price_currency": price.get("currency"),
            "market_cap": _raw(price.get("marketCap")),
            "last_price": _raw(price.get("regularMarketPrice")),
            "trailing_pe": _raw(summary.get("trailingPE")),
            "price_to_book": _raw(stats.get("priceToBook")),
            "return_on_equity": _raw(financial.get("returnOnEquity")),
            "dividend_yield": _raw(summary.get("dividendYield")),
            "shares_outstanding": _raw(stats.get("sharesOutstanding")),
        }
        self.cache.set_record("profile", symbol, profile)
        return profile

    # ------------------------------------------------------------- mali tablolar

    def fundamentals(
        self,
        symbol: str,
        period_type: str = "annual",
        ttl: float | None = TTL_MALI_TABLO,
    ) -> dict:
        """Yıllık veya çeyreklik mali tabloları çeker.

        Dönüş:
            {"symbol", "period_type",
             "fields": {"TotalRevenue": [{"date","value","currency","period"}...]}}

        Kalemler tarihe göre artan sırada gelir. Yahoo'nun döndürmediği kalem
        `fields` içinde hiç bulunmaz — çağıran taraf eksikliği bundan anlar ve
        sıfır saymaz.
        """
        if period_type not in ("annual", "quarterly"):
            raise ValueError("period_type 'annual' veya 'quarterly' olmalı")

        cache_key = f"{symbol}__{period_type}"
        cached = self.cache.get_record("fundamentals", cache_key, ttl=ttl)
        if cached is not None:
            return cached

        names = YILLIK_ALANLAR if period_type == "annual" else CEYREKLIK_ALANLAR
        types = ",".join(period_type + name for name in names)
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "type": types,
                "period1": 1420070400,  # 2015-01-01, Yahoo daha eskisini vermiyor
                "period2": int(time.time()) + 30 * 86400,
            }
        )
        url = f"{TIMESERIES_URL}{urllib.parse.quote(symbol)}?{query}"
        payload = self._fetch_json(url, needs_crumb=True)

        results = ((payload.get("timeseries") or {}).get("result")) or []
        fields: dict[str, list[dict]] = {}
        for block in results:
            prefixed = _type_of(block)
            if not prefixed:
                continue
            rows = block.get(prefixed) or []
            clean_name = prefixed[len(period_type):]
            points = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                reported = row.get("reportedValue") or {}
                value = reported.get("raw")
                if value is None:
                    continue
                points.append(
                    {
                        "date": row.get("asOfDate"),
                        "value": value,
                        "currency": row.get("currencyCode"),
                        "period": row.get("periodType"),
                    }
                )
            if points:
                points.sort(key=lambda item: item["date"] or "")
                fields[clean_name] = points

        table = {"symbol": symbol, "period_type": period_type, "fields": fields}
        self.cache.set_record("fundamentals", cache_key, table)
        return table

    # ------------------------------------------------------------------- evren

    def screener(
        self,
        exchanges,
        size: int = 100,
        offset: int = 0,
        quote_type: str = "EQUITY",
        sort_field: str = "intradaymarketcap",
        sort_type: str = "DESC",
    ) -> dict:
        """Borsa koduna göre hisse listesi çeker (POST + crumb).

        Sembol evrenini elle tutmak yerine buradan kuruyoruz: BIST için
        `("IST",)` 616 hisse, ABD için `("NMS", "NYQ")` 4278 hisse döndürüyor.
        Sayfa başına en fazla 250 kayıt gelir; sayfalama universe.py'de.

        Satırlarda sektör YOK — sektör için sembol başına profile() gerekir.
        Ama `financialCurrency` ve `marketCap` burada bedava geliyor, bu da
        para birimi normalizasyonu için baştan doğru bilgi demek.
        """
        if isinstance(exchanges, str):
            exchanges = (exchanges,)
        conditions = [
            {"operator": "eq", "operands": ["exchange", code]} for code in exchanges
        ]
        inner = conditions[0] if len(conditions) == 1 else {
            "operator": "or",
            "operands": conditions,
        }

        payload = {
            "size": min(int(size), 250),
            "offset": int(offset),
            "sortField": sort_field,
            "sortType": sort_type,
            "quoteType": quote_type,
            "query": {"operator": "AND", "operands": [inner]},
            "userId": "",
            "userIdType": "guid",
        }
        data = self._fetch_json(SCREENER_URL, needs_crumb=True, payload=payload)

        results = ((data.get("finance") or {}).get("result")) or []
        if not results:
            error = (data.get("finance") or {}).get("error")
            raise YahooError(f"screener sonucu boş: {error}")
        block = results[0]

        quotes = []
        for row in block.get("quotes") or []:
            symbol = row.get("symbol")
            if not symbol:
                continue
            quotes.append(
                {
                    "symbol": symbol,
                    "name": row.get("longName") or row.get("shortName"),
                    "exchange": row.get("exchange"),
                    "price_currency": row.get("currency"),
                    "financial_currency": row.get("financialCurrency"),
                    "market_cap": row.get("marketCap"),
                }
            )
        return {"total": block.get("total") or 0, "quotes": quotes}

    # ------------------------------------------------------------------ yardımcı

    def symbol_exists(self, symbol: str) -> bool:
        """Evren doğrulaması için hafif kontrol: 5 günlük chart çekilebiliyor mu."""
        try:
            self.chart(symbol, range_="5d")
            return True
        except YahooNotFound:
            return False
        except YahooError:
            # Ağ/oran hatası sembolün geçersizliğini kanıtlamaz; şüpheli sayıp
            # geçerli kabul etmek, yanlışlıkla evreni budamaktan iyidir.
            return True


# --------------------------------------------------------------- modül yardımcıları


def _pick(sequence, index):
    if not sequence or index >= len(sequence):
        return None
    return sequence[index]


def _raw(node):
    """Yahoo'nun {"raw":..,"fmt":..} sarmalından sayıyı çıkarır."""
    if isinstance(node, dict):
        return node.get("raw")
    return node


def _type_of(block: dict) -> str | None:
    meta = block.get("meta") or {}
    types = meta.get("type") or []
    return types[0] if types else None


def _days_between(start_iso: str, end_iso: str) -> int:
    fmt = "%Y-%m-%d"
    start = time.mktime(time.strptime(start_iso, fmt))
    end = time.mktime(time.strptime(end_iso, fmt))
    return max(0, int((end - start) // 86400))


def _range_for_gap(gap_days: int) -> str:
    for limit, range_ in ((4, "5d"), (25, "1mo"), (80, "3mo"), (170, "6mo"), (350, "1y"), (700, "2y")):
        if gap_days <= limit:
            return range_
    return "5y"
