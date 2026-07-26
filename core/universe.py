"""Sembol evreni — BIST ve ABD hisse listeleri, sektör eşlemesi.

Liste elle tutulmuyor: Yahoo'nun screener ucundan piyasa değerine göre sıralı
çekiliyor (BIST 616, ABD 4278 hisse). Sektör bilgisi screener yanıtında yok,
sembol başına profile() çağrısı gerekiyor; bu yüzden sektör doldurma ayrı ve
kesintiye dayanıklı bir adım (`fill_sectors`) olarak duruyor.

Sektör iki yerde kritik:
  - sektör medyanı ve yüzdelik hesapları (context.py)
  - banka/finans kenar durumu: bankalarda FAVÖK, brüt kâr, dönen varlık ve
    kısa vadeli yükümlülük kalemleri Yahoo'da boş döner, dolayısıyla Altman Z,
    net borç/FAVÖK ve cari oran hesaplanamaz. Bunlar "veri yok" değil, "bu
    sektörde geçerli değil" olarak etiketlenir.
"""

from __future__ import annotations

import time

from . import cache as cache_mod
from .yahoo import YahooClient, YahooError, YahooNotFound

TTL_EVREN = 7 * cache_mod.GUN

MARKETS: dict[str, dict] = {
    "bist": {
        "label": "BIST",
        "exchanges": ("IST",),
        # BIST'te 616 hisse var; tamamını alıyoruz.
        "limit": 700,
        "index": "XU100.IS",
        "index_label": "BIST 100",
        "cpi_currency": "TRY",
    },
    "us": {
        "label": "ABD",
        "exchanges": ("NMS", "NYQ"),
        # ABD'de 4278 hisse var. Piyasa değerine göre ilk 500 alınıyor:
        # tamamı hem gereksiz hem de mali tablo çekmesi saatler sürer.
        "limit": 500,
        "index": "^GSPC",
        "index_label": "S&P 500",
        "cpi_currency": "USD",
    },
}

# Yahoo taksonomisinde finans sektörünün adı budur.
FINANS_SEKTORU = "Financial Services"

# Banka endüstri adları Yahoo'da tire biçimi değişebiliyor ("Banks—Regional",
# "Banks - Regional"), o yüzden tam eşleşme değil parça arama yapıyoruz.
BANKA_IPUCLARI = ("bank",)
SIGORTA_IPUCLARI = ("insurance", "reinsurance")


class UnknownMarket(KeyError):
    """Tanınmayan piyasa kimliği."""


def market_ids() -> tuple[str, ...]:
    return tuple(MARKETS)


def market_config(market: str) -> dict:
    try:
        return MARKETS[market]
    except KeyError as error:
        raise UnknownMarket(
            f"bilinmeyen piyasa: {market!r} (geçerli: {', '.join(MARKETS)})"
        ) from error


# --------------------------------------------------------------------- kurulum


def build(
    client: YahooClient,
    market: str,
    limit: int | None = None,
    progress=None,
) -> dict:
    """Evreni screener ucundan sayfalayarak kurar ve önbelleğe yazar.

    Sektör alanı bu adımda boş bırakılır; `fill_sectors` dolduruyor.
    """
    config = market_config(market)
    target = limit if limit is not None else config["limit"]

    entries: list[dict] = []
    seen: set[str] = set()
    total_reported = 0
    offset = 0
    page_size = 100

    while len(entries) < target:
        page = client.screener(
            config["exchanges"], size=page_size, offset=offset
        )
        total_reported = page["total"] or total_reported
        quotes = page["quotes"]
        if not quotes:
            break

        for quote in quotes:
            symbol = quote["symbol"]
            if symbol in seen:
                continue
            seen.add(symbol)
            entries.append(
                {
                    "symbol": symbol,
                    "name": quote["name"],
                    "exchange": quote["exchange"],
                    "price_currency": quote["price_currency"],
                    "financial_currency": quote["financial_currency"],
                    "market_cap": quote["market_cap"],
                    "sector": None,
                    "industry": None,
                }
            )
            if len(entries) >= target:
                break

        offset += page_size
        if progress:
            progress(len(entries), min(target, total_reported or target))
        if offset >= (total_reported or 0):
            break

    record = {
        "market": market,
        "label": config["label"],
        "built_at": time.time(),
        "total_reported": total_reported,
        "sectors_filled": 0,
        "entries": entries,
    }
    client.cache.set_record("universe", market, record)
    return record


def load(
    client: YahooClient,
    market: str,
    refresh: bool = False,
    ttl: float | None = TTL_EVREN,
) -> dict:
    """Önbellekteki evreni döndürür; yoksa veya bayatsa yeniden kurar."""
    if not refresh:
        cached = client.cache.get_record("universe", market, ttl=ttl)
        if cached is not None:
            return cached
    return build(client, market)


def symbols(client: YahooClient, market: str) -> list[str]:
    return [entry["symbol"] for entry in load(client, market)["entries"]]


def entry_for(client: YahooClient, market: str, symbol: str) -> dict | None:
    for entry in load(client, market)["entries"]:
        if entry["symbol"] == symbol:
            return entry
    return None


def find_market(client: YahooClient, symbol: str) -> str | None:
    """Sembolün hangi evrende olduğunu söyler; hiçbirinde yoksa None.

    Önbellekte evren yoksa kurmaya kalkışmaz — sembol son ekinden tahmin eder.
    """
    for market in MARKETS:
        cached = client.cache.get_record("universe", market, ttl=None)
        if cached and any(e["symbol"] == symbol for e in cached["entries"]):
            return market
    return "bist" if symbol.upper().endswith(".IS") else "us"


# ----------------------------------------------------------------- sektör doldurma


def fill_sectors(
    client: YahooClient,
    market: str,
    limit: int | None = None,
    progress=None,
    save_every: int = 25,
) -> dict:
    """Eksik sektör/endüstri alanlarını profile() ile doldurur.

    Kesintiye dayanıklı: her `save_every` sembolde evren kaydı diske yazılır,
    böylece yarıda kesilen doldurma baştan başlamaz. profile() zaten 12 saat
    önbellekli olduğu için tekrar çalıştırmak ağ maliyeti getirmez.

    Sembol başına bir istek gerekiyor; 616 BIST hissesi ~4 istek/sn ile
    yaklaşık 2,5 dakika sürer. Bu, panelin ilk açılışındaki tek uzun adım.
    """
    record = load(client, market)
    pending = [e for e in record["entries"] if not e.get("sector")]
    if limit is not None:
        pending = pending[:limit]

    done = 0
    for index, item in enumerate(pending, start=1):
        try:
            profile = client.profile(item["symbol"])
        except (YahooNotFound, YahooError) as error:
            # Sektörü alınamayan sembol evrenden atılmaz; sektör bazlı
            # hesaplardan dışlanır ve nedeni kayda geçer.
            item["profile_error"] = str(error)[:120]
        else:
            item["sector"] = profile.get("sector")
            item["industry"] = profile.get("industry")
            # Screener'ın piyasa değeri ile profile'ın değeri arasında fark
            # olabilir; profile daha güncel, onu tercih ediyoruz.
            if profile.get("market_cap"):
                item["market_cap"] = profile["market_cap"]
            if profile.get("financial_currency"):
                item["financial_currency"] = profile["financial_currency"]
            if profile.get("price_currency"):
                item["price_currency"] = profile["price_currency"]
            item.pop("profile_error", None)
            done += 1

        if index % save_every == 0:
            record["sectors_filled"] = _filled_count(record)
            client.cache.set_record("universe", market, record)
        if progress:
            progress(index, len(pending), item["symbol"])

    record["sectors_filled"] = _filled_count(record)
    client.cache.set_record("universe", market, record)
    return {"market": market, "attempted": len(pending), "filled": done}


def _filled_count(record: dict) -> int:
    return sum(1 for entry in record["entries"] if entry.get("sector"))


# ---------------------------------------------------------------- sınıflandırma


def is_financial(sector: str | None) -> bool:
    """Finans sektörü mü? Altman Z ve borç oranları burada anlamsızdır."""
    return (sector or "").strip().lower() == FINANS_SEKTORU.lower()


def is_bank(industry: str | None) -> bool:
    text = (industry or "").lower()
    return any(hint in text for hint in BANKA_IPUCLARI)


def is_insurance(industry: str | None) -> bool:
    text = (industry or "").lower()
    return any(hint in text for hint in SIGORTA_IPUCLARI)


def uses_bank_accounting(sector: str | None, industry: str | None) -> bool:
    """Bilanço kalemleri klasik işletme mantığıyla okunamayan şirketler.

    Bankalarda dönen varlık / kısa vadeli yükümlülük ayrımı yoktur, brüt kâr ve
    FAVÖK açıklanmaz. Sigortada da benzer durum geçerli. Bu şirketlerde ilgili
    metrikler "hesaplanamadı" değil "bu sektörde geçerli değil" olarak
    işaretlenir — ölçüm kalitesi ile sektör yapısı karıştırılmasın.
    """
    return is_bank(industry) or is_insurance(industry) or is_financial(sector)


def sector_groups(entries: list[dict]) -> dict[str, list[str]]:
    """Sektör -> sembol listesi. Sektörü bilinmeyenler dahil edilmez."""
    groups: dict[str, list[str]] = {}
    for item in entries:
        sector = item.get("sector")
        if not sector:
            continue
        groups.setdefault(sector, []).append(item["symbol"])
    return groups


# ------------------------------------------------------------------- doğrulama


def validate(client: YahooClient, symbols_to_check) -> dict:
    """Elle girilen sembolleri (ör. portföy) doğrular.

    Screener'dan gelen liste zaten geçerli olduğu için bu yalnızca kullanıcı
    girdisi için gerekli.
    """
    valid, invalid = [], []
    for symbol in symbols_to_check:
        (valid if client.symbol_exists(symbol) else invalid).append(symbol)
    return {"valid": valid, "invalid": invalid}
