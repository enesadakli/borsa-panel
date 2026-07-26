"""Enflasyon katmanı — TÜFE serileri ve reel büyüme.

Türkiye'de nominal büyüme rakamı tek başına yanıltıcıdır: %40 büyüme, %45
enflasyonda küçülmedir. Bu yüzden panelde reel rakam birincil, nominal
ikincildir.

**Hangi TÜFE?** Şirketin borsası değil, **mali tablo para birimi** belirler.
THYAO bir BIST hissesi ama tablolarını USD açıklıyor; gelirini Türkiye
TÜFE'siyle deflate etmek olmayan bir küçülme uydurmak olur.

Kaynaklar katmanlı, çünkü hiçbiri tek başına yetmiyor:

    aylık  TRY : TCMB EVDS TP.FG.J0    — tam geçmiş, ücretsiz anahtar ister
    aylık  USD : ABD BLS CUUR0000SA0   — anahtarsız ama yalnızca son ~3 yıl
                                         (yıl parametrelerini yok sayıyor)
    yıllık her ikisi : Dünya Bankası FP.CPI.TOTL — anahtarsız, derin geçmiş,
                                         ama son yılı geç yayımlıyor

**Kaynaklar tek hesapta karıştırılmaz.** Aylık endeks nokta değeridir
(Aralık→Aralık), Dünya Bankası yıllık *ortalamadır*; ikisini birleştirmek
sistematik sapma verir. Bir büyüme hesabının iki ucu da aylık seride varsa
aylık kullanılır; yoksa ikisi de yıllık seride varsa yıllık ortalama
kullanılır ve sonuç bu şekilde etiketlenir. Karışık olacaksa hesap yapılmaz.

Bu yapı sayesinde panel EVDS anahtarı olmadan da reel gösterim yapar (yıllık
ortalama bazında); anahtar eklenince aylık hassasiyete yükselir.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import cache as cache_mod
from .yahoo import USER_AGENT, build_ssl_context

EVDS_URL = "https://evds2.tcmb.gov.tr/service/evds/"
EVDS_SERI = "TP.FG.J0"  # TÜFE genel endeks
EVDS_ADI = "TÜFE (TCMB EVDS, aylık)"

BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SERI = "CUUR0000SA0"  # CPI-U, ABD kent ortalaması
BLS_ADI = "US CPI (BLS, aylık)"

WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/FP.CPI.TOTL"

BASLANGIC_YIL = 2015
TTL_TUFE = 7 * cache_mod.GUN

# Para birimi -> (aylık kaynak, Dünya Bankası ülke kodu).
#
# EUR bilerek burada YOK: Dünya Bankası'nda euro bölgesi agregatı bulunmuyor
# (EMU/XC kodları boş dönüyor — ölçüldü). EUR raporlayan şirketler için doğru
# ülke, şirketin `country` alanından (Yahoo profili) çözülüyor — bkz.
# `_eur_ulke_kodu`. Diğer tüm para birimleri tek bir ülkeye sabitlenebilir
# (CNY→Çin, JPY→Japonya gibi); yalnızca EUR birden fazla ülkeyi kapsıyor.
#
# Hiçbirinde aylık kaynak yok (`None`): EVDS/BLS gibi ücretsiz, anahtarsız
# aylık bir TÜFE API'si yalnızca TR ve ABD için bulundu. Bu para birimlerinde
# panel doğrudan Dünya Bankası'nın yıllık ortalamasına düşüyor — TRY'de
# EVDS anahtarı girilmediğinde zaten kullanılan yolun aynısı.
_PARA_KAYNAK = {
    "TRY": ("evds", "TUR"),
    "USD": ("bls", "USA"),
    "CAD": (None, "CAN"),
    "GBP": (None, "GBR"),
    "JPY": (None, "JPN"),
    "BRL": (None, "BRA"),
    "CNY": (None, "CHN"),
    "KRW": (None, "KOR"),
    "INR": (None, "IND"),
    "MXN": (None, "MEX"),
    "DKK": (None, "DNK"),
    "SEK": (None, "SWE"),
    "COP": (None, "COL"),
    "PEN": (None, "PER"),
}

# Dünya Bankası ülke kodu -> ekranda gösterilecek Türkçe ad.
WB_ULKE_ADI = {
    "TUR": "Türkiye", "USA": "ABD", "CAN": "Kanada", "GBR": "Birleşik Krallık",
    "JPN": "Japonya", "BRA": "Brezilya", "CHN": "Çin", "KOR": "Güney Kore",
    "IND": "Hindistan", "MEX": "Meksika", "DNK": "Danimarka", "SWE": "İsveç",
    "COL": "Kolombiya", "PER": "Peru",
    # Euro bölgesi (EUR şirketlerinin `country` alanından çözülüyor)
    "AUT": "Avusturya", "BEL": "Belçika", "HRV": "Hırvatistan", "CYP": "Kıbrıs",
    "EST": "Estonya", "FIN": "Finlandiya", "FRA": "Fransa", "DEU": "Almanya",
    "GRC": "Yunanistan", "IRL": "İrlanda", "ITA": "İtalya", "LVA": "Letonya",
    "LTU": "Litvanya", "LUX": "Lüksemburg", "MLT": "Malta", "NLD": "Hollanda",
    "PRT": "Portekiz", "SVK": "Slovakya", "SVN": "Slovenya", "ESP": "İspanya",
}

# Yahoo'nun assetProfile.country alanı İngilizce tam ülke adı döndürüyor
# ("Austria", "Germany" — DOCO ve benzer vakalarda ölçüldü). EUR raporlayan
# bir şirkette doğru TÜFE serisini seçmek için bu adı ISO3 koduna çeviriyoruz.
EURO_ULKE_ISO3 = {
    "austria": "AUT", "belgium": "BEL", "croatia": "HRV", "cyprus": "CYP",
    "estonia": "EST", "finland": "FIN", "france": "FRA", "germany": "DEU",
    "greece": "GRC", "ireland": "IRL", "italy": "ITA", "latvia": "LVA",
    "lithuania": "LTU", "luxembourg": "LUX", "malta": "MLT",
    "netherlands": "NLD", "portugal": "PRT", "slovakia": "SVK",
    "slovenia": "SVN", "spain": "ESP",
}

BASIS_AYLIK = "aylık endeks (dönem sonu)"
BASIS_YILLIK = "yıllık ortalama endeks"


def _eur_ulke_kodu(country: str | None) -> str | None:
    """EUR raporlayan bir şirketin ülkesinden Dünya Bankası ISO3 kodu.

    Ülke bilinmiyorsa veya euro bölgesinde değilse None döner; çağıran taraf
    bunu "kullanılamıyor" yoluna düşürür — TÜFE serisi uydurulmaz.
    """
    if not country:
        return None
    return EURO_ULKE_ISO3.get(country.strip().lower())


class InflationUnavailable(RuntimeError):
    """Bir TÜFE kaynağına ulaşılamadı."""


# ------------------------------------------------------------------- ayarlar


def config_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def evds_key() -> str | None:
    key = (load_config().get("evds_api_key") or "").strip()
    return key or None


# ---------------------------------------------------------------- seri çekme


def cpi_series(cache: cache_mod.Cache, currency: str | None, country: str | None = None) -> dict:
    """Para birimine göre katmanlı TÜFE serisi.

    `country` yalnızca EUR için kullanılır: Dünya Bankası'nda euro bölgesi
    agregatı olmadığı için (EMU/XC boş dönüyor) şirketin kendi ülkesinin
    serisi seçilir — DOCO.IS (Avusturya) bu yolun gerçek sınavıydı.

    Dönüş:
        {"currency", "monthly": {"2025-12": 3018.5}, "monthly_label",
         "annual": {"2025": 1784.3}, "annual_label",
         "available", "notes": [...]}
    """
    currency = (currency or "").upper()

    if currency == "EUR":
        iso3 = _eur_ulke_kodu(country)
        if iso3 is None:
            return {
                "currency": "EUR",
                "monthly": {}, "monthly_label": None,
                "annual": {}, "annual_label": None,
                "available": False,
                "notes": [
                    f"Şirketin ülkesi ({country or 'bilinmiyor'}) euro bölgesi "
                    "ülkeleri arasında tanınamadı; TÜFE serisi seçilemedi, "
                    "yalnızca nominal gösterilir."
                ],
            }
        entry = (None, iso3)
        cache_key = f"EUR_{iso3}"
    else:
        entry = _PARA_KAYNAK.get(currency)
        cache_key = currency

    if entry is None:
        return {
            "currency": currency or None,
            "monthly": {},
            "monthly_label": None,
            "annual": {},
            "annual_label": None,
            "available": False,
            "notes": [
                f"{currency or 'Bilinmeyen'} para biriminde tablo açıklayan şirketler "
                "için TÜFE serisi tanımlı değil; yalnızca nominal gösterilir."
            ],
        }

    cached = cache.get_record("cpi", cache_key, ttl=TTL_TUFE)
    if cached is not None:
        return cached

    monthly_source, wb_country = entry
    notes: list[str] = []

    monthly: dict[str, float] = {}
    monthly_label = None
    if monthly_source == "evds":
        try:
            monthly = _fetch_evds()
            monthly_label = EVDS_ADI
        except InflationUnavailable as error:
            notes.append(str(error))
    elif monthly_source == "bls":
        try:
            monthly = _fetch_bls()
            monthly_label = BLS_ADI
        except InflationUnavailable as error:
            notes.append(str(error))
    else:
        notes.append(
            f"{currency} için ücretsiz/anahtarsız aylık bir TÜFE kaynağı yok; "
            "yıllık ortalama kullanılıyor."
        )

    annual: dict[str, float] = {}
    annual_label = None
    ulke_adi = WB_ULKE_ADI.get(wb_country, wb_country)
    try:
        annual = _fetch_worldbank(wb_country)
        annual_label = f"{ulke_adi} TÜFE (Dünya Bankası, yıllık ortalama)"
    except InflationUnavailable as error:
        notes.append(str(error))

    if monthly:
        aylar = sorted(monthly)
        notes.append(
            f"Aylık seri: {aylar[0]} – {aylar[-1]} ({len(aylar)} ay, {monthly_label})."
        )
    if annual:
        yillar = sorted(annual)
        notes.append(
            f"Yıllık seri: {yillar[0]} – {yillar[-1]} ({annual_label})."
        )

    result = {
        "currency": currency,
        "monthly": monthly,
        "monthly_label": monthly_label,
        "annual": annual,
        "annual_label": annual_label,
        "available": bool(monthly or annual),
        "notes": notes,
    }

    # Hiçbir kaynak gelmediyse önbelleğe yazma: anahtar eklendiğinde veya ağ
    # düzeldiğinde bir sonraki çağrı yeniden denesin.
    if result["available"]:
        cache.set_record("cpi", cache_key, result)
    return result


def _fetch_evds() -> dict[str, float]:
    key = evds_key()
    if not key:
        raise InflationUnavailable(
            "TCMB EVDS anahtarı girilmemiş (data/config.json → 'evds_api_key'). "
            "TRY tablolarda aylık hassasiyet yok; yıllık ortalamayla devam ediliyor."
        )

    query = urllib.parse.urlencode(
        {
            "series": EVDS_SERI,
            "startDate": f"01-01-{BASLANGIC_YIL}",
            "endDate": "31-12-2035",
            "type": "json",
            "key": key,
        }
    )
    payload = _get_json(f"{EVDS_URL}?{query}", "EVDS")

    points: dict[str, float] = {}
    for item in payload.get("items") or []:
        month = _normalize_month(item.get("Tarih"))
        value = None
        for name, candidate in item.items():
            if name.replace("_", ".").upper().startswith(EVDS_SERI):
                value = candidate
                break
        number = _to_float(value)
        if month and number is not None:
            points[month] = number
    return points


def _fetch_bls() -> dict[str, float]:
    """BLS aylık CPI.

    Anahtarsız v1 ucu startyear/endyear parametrelerini **yok sayıyor** ve her
    durumda son ~3 yılı döndürüyor (ölçüldü: 2015-2024 istendiğinde de
    2024-01..2026-06 geldi). Derin geçmiş için Dünya Bankası yıllık serisi
    kullanılıyor.
    """
    payload = _get_json(f"{BLS_URL}{BLS_SERI}", "BLS")
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise InflationUnavailable(
            f"BLS isteği reddedildi: {payload.get('status')} "
            f"{'; '.join(payload.get('message') or [])}"
        )

    points: dict[str, float] = {}
    for series in (payload.get("Results") or {}).get("series") or []:
        for row in series.get("data") or []:
            period = row.get("period") or ""
            if not period.startswith("M") or period == "M13":  # M13 = yıllık ortalama
                continue
            month = f"{row.get('year')}-{period[1:].zfill(2)}"
            number = _to_float(row.get("value"))
            if number is not None:
                points[month] = number
    return points


def _fetch_worldbank(country: str) -> dict[str, float]:
    query = urllib.parse.urlencode(
        {"format": "json", "per_page": 200, "date": f"{BASLANGIC_YIL}:2035"}
    )
    payload = _get_json(f"{WB_URL.format(country=country)}?{query}", "Dünya Bankası")

    # Yanıt [meta, satırlar] biçiminde bir liste.
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise InflationUnavailable("Dünya Bankası yanıtı beklenen biçimde değil.")

    points: dict[str, float] = {}
    for row in payload[1]:
        year = str(row.get("date") or "")
        value = row.get("value")
        if year.isdigit() and value is not None:
            points[year] = float(value)
    return points


def _get_json(url: str, source_label: str):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=build_ssl_context())
    )
    try:
        with opener.open(request, timeout=40) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise InflationUnavailable(f"{source_label} HTTP {error.code} döndürdü.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise InflationUnavailable(f"{source_label} erişilemedi: {error}") from error

    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as error:
        raise InflationUnavailable(f"{source_label} yanıtı JSON değil.") from error


# --------------------------------------------------------------- hesaplamalar


def cpi_at(series: dict, iso_date: str | None):
    """Tarihin ayına ait aylık endeks; yoksa None.

    Mali dönem hangi ayda bitiyorsa o ayın endeksi kullanılır: Apple'ın
    Eylül'de biten yılı Eylül endeksiyle, BIST'in Aralık yılı Aralık
    endeksiyle karşılaştırılır.
    """
    if not iso_date:
        return None
    return (series.get("monthly") or {}).get(iso_date[:7])


def cpi_annual_at(series: dict, iso_date: str | None):
    """Tarihin takvim yılına ait yıllık ortalama TÜFE; yoksa None.

    Not: DOCO.IS gibi mali yılı Aralık dışında biten şirketlerde en GÜNCEL
    dönem (ör. "2026-03-31") çoğu zaman Dünya Bankası'nın henüz yayımlamadığı
    bir takvim yılına denk gelir — bu durumda reel büyüme o dönem için
    hesaplanamaz ("TÜFE verisi henüz yok"). Önceki yıla sessizce düşmek
    (denendi, sonra geri alındı) başka bir hataya yol açıyordu: karşılaştırı-
    lan iki dönem de aynı yedek yıla düşünce (start=2025→tam eşleşme,
    end=2026→2025'e düşer) ikisi de aynı sayı olup "enflasyon %0" gibi
    fabrike bir sonuç üretiyordu. Dönemin kendisi ölçülemiyor olması, komşu
    dönemi ölçülüyormuş gibi göstermekten iyidir; bu yüzden düşme yapılmıyor.
    """
    if not iso_date:
        return None
    return (series.get("annual") or {}).get(iso_date[:4])


def cpi_growth(series: dict, start_date: str | None, end_date: str | None) -> dict:
    """İki dönem arasındaki TÜFE artışı ve hangi tabandan hesaplandığı.

    Önce aylık seri denenir (iki uç da varsa). Olmazsa yıllık ortalama serisi
    denenir. İki seriyi karıştırmak yok — biri nokta değeri, diğeri ortalama.
    """
    before = cpi_at(series, start_date)
    after = cpi_at(series, end_date)
    if before and after is not None:
        return {
            "value": after / before - 1.0,
            "basis": BASIS_AYLIK,
            "label": series.get("monthly_label"),
        }

    before = cpi_annual_at(series, start_date)
    after = cpi_annual_at(series, end_date)
    if before and after is not None:
        return {
            "value": after / before - 1.0,
            "basis": BASIS_YILLIK,
            "label": series.get("annual_label"),
        }

    return {"value": None, "basis": None, "label": None}


def deflate(nominal_growth: float | None, cpi_growth_rate: float | None):
    """Nominal büyümeyi reele çevirir: (1+n)/(1+e)-1.

    Yaygın hata nominalden enflasyonu çıkarmaktır; yüksek enflasyonda sapar.
    %41 büyüme / %45 enflasyon: çıkarma −4,0 puan der, doğrusu −%2,76.
    """
    if nominal_growth is None or cpi_growth_rate is None:
        return None
    if cpi_growth_rate <= -1:
        return None
    return (1.0 + nominal_growth) / (1.0 + cpi_growth_rate) - 1.0


def real_growth(series: dict, nominal_growth, start_date, end_date) -> dict:
    """Dönem TÜFE'siyle düzeltilmiş büyüme + kullanılan enflasyon ve kaynağı."""
    inflation = cpi_growth(series, start_date, end_date)
    return {
        "real": deflate(nominal_growth, inflation["value"]),
        "nominal": nominal_growth,
        "cpi_growth": inflation["value"],
        "basis": inflation["basis"],
        "label": inflation["label"],
        "start": start_date,
        "end": end_date,
    }


def real_series(series: dict, points: list[tuple[str, float]], base_date: str | None = None) -> dict:
    """Tutar serisini sabit fiyatlara çevirir (taban: en son dönem).

    Tek bir taban seçilir ve **tüm noktalar aynı seriden** deflate edilir;
    bazı noktaları aylık, bazılarını yıllık endeksle düzeltmek seriyi bozar.
    TÜFE'si olmayan dönemler atlanır, hangi dönemlerin atlandığı döner.
    """
    empty = {"points": [], "basis": None, "label": None, "skipped": [], "base": None}
    if not points:
        return empty

    base = base_date or points[-1][0]

    for basis, getter, label_key in (
        (BASIS_AYLIK, cpi_at, "monthly_label"),
        (BASIS_YILLIK, cpi_annual_at, "annual_label"),
    ):
        base_index = getter(series, base)
        if not base_index:
            continue
        out, skipped = [], []
        for date, value in points:
            index = getter(series, date)
            if not index or value is None:
                skipped.append(date)
                continue
            out.append((date, value * base_index / index))
        if out:
            return {
                "points": out,
                "basis": basis,
                "label": series.get(label_key),
                "skipped": skipped,
                "base": base,
            }

    return empty


def series_for_pack(cache: cache_mod.Cache, pack: dict) -> dict:
    """Mali tablo paketinin para birimine uygun TÜFE serisi.

    Bu tek satır, "ABD hissesini Türkiye enflasyonuyla düzeltme" hatasının
    önündeki asıl bariyer: seçim borsaya değil `pack["currency"]`e bakıyor.
    `country` yalnızca EUR'da devreye girer (bkz. `cpi_series`).
    """
    return cpi_series(cache, pack.get("currency"), pack.get("country"))


# ------------------------------------------------------------------ yardımcı


def _normalize_month(raw) -> str | None:
    """EVDS'nin '2015-1' biçimini '2015-01' yapar."""
    if not raw or "-" not in str(raw):
        return None
    year, _, month = str(raw).partition("-")
    if not year.isdigit() or not month.isdigit():
        return None
    return f"{int(year):04d}-{int(month):02d}"


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None
