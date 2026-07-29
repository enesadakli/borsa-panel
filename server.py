"""Yerel panel sunucusu — stdlib `http.server`.

Sadece iki iş yapar: `web/` altındaki statik dosyaları servis eder ve `/api/*`
altında JSON döner. Tüm analiz `core/` modüllerinde; burada iş mantığı yok.

Kullanım:
    python server.py            # http://127.0.0.1:8737
    python server.py --port 9000 --no-browser

Yalnızca 127.0.0.1'e bağlanır: bu bir kişisel araç, ağa açılması gerekmiyor.

Uçlar
-----
GET /api/durum                          panel durumu, önbellek tazeliği
GET /api/sirket?sembol=SISE.IS          skor kartı: analiz + bayraklar + narratif + bağlam
GET /api/rapor?sembol=SISE.IS           çeyreklik/yıllık rapor karşılaştırması
GET /api/kalite?sembol=SISE.IS          kalite zaman çizgisi (SVG verisi)
GET /api/tarayici/alanlar               filtre kurucusunun alan kataloğu
GET /api/tarayici/kurallar              hazır şablonlar + kayıtlı kurallar
GET /api/tarayici?sablon=bilanco_kalitesi   şablonu çalıştır
POST /api/tarayici                      gövdede kural JSON'u ile tara
POST /api/tarayici/kaydet               kullanıcı kuralını kaydet
GET /api/portfoy                        portföy özeti + risk + kalite röntgeni
POST /api/portfoy/islem                 işlem ekle
POST /api/portfoy/sil                   işlem sil (gövdede {"index": n})
POST /api/portfoy/ice-aktar             CSV'den toplu işlem ekle (gövdede {"csv": "..."})
GET /api/portfoy/sablon                 örnek CSV şablonu (indirilebilir)
GET /api/piyasa?evren=bist              piyasa genel bakışı
GET /api/ara?q=sise                     sembol arama (bağlam kaydından)
POST /api/tarama/baslat                 arka planda evren taraması başlat (gövdede {"evren": "bist"})
GET /api/tarama/durum                   çalışan taramanın ilerlemesi
POST /api/tarama/iptal                  çalışan taramayı iptal et
GET /api/sozluk                         terim sözlüğü (arayüz balonları için)
GET /api/llm-rapor?sembol=SISE.IS       LLM-okunur Markdown rapor (admin anahtarı ayarlıysa korumalı)
    &bolum=borc,reel                    isteğe bağlı: yalnızca seçilen bölümler
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

KOK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KOK)

from core import cache as cache_mod          # noqa: E402
from core import context as C                # noqa: E402
from core import flags as FL                 # noqa: E402
from core import fundamentals as F           # noqa: E402
from core import health as H                 # noqa: E402
from core import inflation as INF            # noqa: E402
from core import llm_rapor as LLM            # noqa: E402
from core import market as M                 # noqa: E402
from core import narrative as N              # noqa: E402
from core import portfolio as PF             # noqa: E402
from core import reports as R                # noqa: E402
from core import risk as RISK                # noqa: E402
from core import screener as S               # noqa: E402
from core import universe as U               # noqa: E402
from core.yahoo import YahooClient, YahooError  # noqa: E402

from core.sozluk import SOZLUK, UYARI  # noqa: E402

WEB = os.path.join(KOK, "web")
VARSAYILAN_PORT = 8737

FAVICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect width='32' height='32' rx='7' fill='#3b5bfd'/>"
    "<path d='M7 22 L13 15 L18 19 L25 9' stroke='white' stroke-width='2.6' "
    "fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>"
)

_client = YahooClient()
_kilit = threading.Lock()   # YahooClient tek çerez/crumb durumu tutuyor


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class MetinYanit:
    """Bir uç işleyicinin JSON değil düz metin döndürdüğünü işaretler.

    `_api()` bunu `isinstance` ile tanıyıp `_metin()`e dallanır; her hata
    yolu (ApiError, YahooError, beklenmeyen istisna) yine JSON kalır — yalnızca
    başarılı yanıt gövdesi metin olur.
    """

    def __init__(self, metin: str, tur: str = "text/markdown; charset=utf-8") -> None:
        self.metin = metin
        self.tur = tur


def admin_anahtari() -> str | None:
    """config.json'daki 'admin_anahtari'; boşsa None (bkz. INF.evds_key aynı örüntü)."""
    key = (INF.load_config().get("admin_anahtari") or "").strip()
    return key or None


def admin_dogrula(headers) -> None:
    """Anahtar yapılandırılmamışsa geçer (yerel tek kullanıcı = admin).

    Yapılandırılmışsa `X-Admin-Anahtar` başlığı `hmac.compare_digest` ile
    karşılaştırılır — zamanlama saldırılarına karşı `==`'den daha güvenli,
    burada asıl değeri olan şey modülerlik: ileride panel çok kullanıcılı bir
    uygulamaya dönüşürse tek yapılacak şey anahtarı doldurmak.
    """
    yapilandirilan = admin_anahtari()
    if yapilandirilan is None:
        return
    verilen = headers.get("X-Admin-Anahtar") or ""
    if not hmac.compare_digest(verilen, yapilandirilan):
        raise ApiError("admin anahtarı eksik veya yanlış", status=403)


# Anahtar yapılandırıldığında admin_dogrula'dan geçmesi gereken uçlar.
KORUNAN_UCLAR = {"/api/llm-rapor", "/api/llm-karsilastir"}


class _TaramaIptalEdildi(Exception):
    """`ilerleme()` geri çağrısından fırlatılır; `hata` değil `iptal_edildi` olarak işaretlenir."""


class TaramaYoneticisi:
    """Panelden tetiklenen arka plan evren taraması.

    `core.context.build_metric_context` sembol başına ~4 istek yapan, BIST'te
    ~15-17 dakika süren bir işlemdir. Bunu mevcut `_api()` akışındaki `_kilit`
    altında çalıştırmak — yani normal bir uç gibi ele almak — bu süre boyunca
    panelin HER isteğini (skor kartı dahil) kilitlerdi; `_kilit` "YahooClient
    çerez/crumb durumunu tek seferde bir istek işlensin diye" paylaşıyor ve
    tarama o paylaşılan istemciyi tutarsa aynı kısıtlamaya girer.

    Bu yüzden tarama ayrı bir arka plan thread'inde, **kendi** `YahooClient`
    örneğiyle (kendi çerez kavanozu, kendi crumb'ı — `_client`'a hiç dokunmuyor)
    çalışır ve `_kilit`i hiç görmez. Diskteki önbellek yazımları zaten atomik
    (`cache._atomic_write` → `os.replace`), o yüzden tarama sürerken normal
    istekler eski (ama tutarlı) önbellek durumunu okumaya devam eder; tarama
    bitince tek seferde yeni `context` kaydı yerine geçer.

    Sadece tek bir eşzamanlı tarama desteklenir (`_durum["calisiyor"]` bayrağı
    ile korunur) — iki taramanın aynı anda aynı diske yazması anlamsız ve
    istek oranını gereksiz ikiye katlar.

    İptal, `build_metric_context`'in kendi `progress` geri çağrısından bir
    `_TaramaIptalEdildi` fırlatarak yapılıyor — döngünün ortasından çıkmanın
    başka yolu yok, fonksiyon dıştan durdurulabilir tasarlanmamış. Yarıda
    kesilen bir tarama `client.cache.set_record(...)` satırına hiç ulaşmaz
    (o satır döngünün sonunda), yani eski `context` kaydı olduğu gibi kalır —
    kısmi/bozuk bir kayıt yazılma riski yok.
    """

    def __init__(self) -> None:
        self._kilit = threading.Lock()  # yalnızca birkaç sayacı korur, ms mertebesinde
        self._iptal_bayragi = threading.Event()
        self._durum: dict = {
            "calisiyor": False, "evren": None, "index": 0, "toplam": 0,
            "son_sembol": None, "hata": None, "iptal_edildi": False,
        }

    def durum(self) -> dict:
        with self._kilit:
            return dict(self._durum)

    def baslat(self, market: str) -> None:
        with self._kilit:
            if self._durum["calisiyor"]:
                raise ApiError(
                    f"zaten bir tarama çalışıyor ({self._durum['evren']})", status=409
                )
            self._iptal_bayragi.clear()
            self._durum = {
                "calisiyor": True, "evren": market, "index": 0, "toplam": 0,
                "son_sembol": None, "hata": None, "iptal_edildi": False,
            }
        threading.Thread(target=self._calistir, args=(market,), daemon=True).start()

    def iptal_et(self) -> None:
        with self._kilit:
            if not self._durum["calisiyor"]:
                raise ApiError("çalışan bir tarama yok", status=409)
        self._iptal_bayragi.set()

    def _calistir(self, market: str) -> None:
        client = YahooClient()  # ayrı örnek: global _client/_kilit'e dokunmaz

        def ilerleme(index: int, total: int, symbol: str) -> None:
            with self._kilit:
                self._durum["index"] = index
                self._durum["toplam"] = total
                self._durum["son_sembol"] = symbol
            if self._iptal_bayragi.is_set():
                raise _TaramaIptalEdildi()

        hata = None
        iptal = False
        try:
            C.build_metric_context(client, market, progress=ilerleme)
        except _TaramaIptalEdildi:
            iptal = True
        except Exception as error:  # noqa: BLE001 — arka plan thread'i, sessizce ölmesin
            hata = f"{type(error).__name__}: {error}"
        with self._kilit:
            self._durum["calisiyor"] = False
            self._durum["hata"] = hata
            self._durum["iptal_edildi"] = iptal


_tarama = TaramaYoneticisi()


# =============================================================== uç işleyiciler


def _sembol(params: dict) -> str:
    symbol = (params.get("sembol") or [""])[0].strip().upper()
    if not symbol:
        raise ApiError("'sembol' parametresi gerekli")
    return symbol


def _evren(params: dict) -> str:
    market = (params.get("evren") or ["bist"])[0].strip().lower()
    if market not in U.market_ids():
        raise ApiError(f"bilinmeyen evren: {market}")
    return market


def _baglam(market: str) -> dict | None:
    return C.load_context(_client, market)


def uc_durum(params: dict) -> dict:
    out = {"uyari": UYARI, "evrenler": []}
    tarama_durumu = _tarama.durum()
    for market in U.market_ids():
        config = U.market_config(market)
        cached = _client.cache.get_record("universe", market, ttl=None)
        context = C.load_context(_client, market, ttl=None)
        yas = C.context_age_hours(_client, market)
        out["evrenler"].append(
            {
                "id": market,
                "label": config["label"],
                "index": config["index"],
                "sembol_sayisi": len(cached["entries"]) if cached else 0,
                "taranan": (context or {}).get("count", 0),
                "tarama_yasi_saat": yas,
                "tarama_gerekli": context is None,
                "tarama_calisiyor": tarama_durumu["calisiyor"] and tarama_durumu["evren"] == market,
            }
        )
    tufe = {}
    for para in ("TRY", "USD"):
        seri = INF.cpi_series(_client.cache, para)
        tufe[para] = {
            "available": seri["available"],
            "aylik_nokta": len(seri["monthly"]),
            "yillik_nokta": len(seri["annual"]),
            "notlar": seri["notes"],
        }
    out["tufe"] = tufe
    out["evds_anahtari_var"] = bool(INF.evds_key())
    return out


def uc_sozluk(params: dict) -> dict:
    """Terim sözlüğü — arayüz balonları bu ucu bir kez çekip önbellekler."""
    return {"uyari": UYARI, "terimler": SOZLUK}


def uc_llm_rapor(params: dict) -> MetinYanit:
    """Bir LLM'in arayüzü scrape etmeden okuyabileceği tek-şirket Markdown raporu.

    `?bolum=borc,reel` yalnızca istenen bölümleri döndürür — dar bir soruda
    yerel bir modele 14 KB yerine 2 KB vermeyi sağlar.
    """
    symbol = _sembol(params)
    ham = (params.get("bolum") or [""])[0].strip()
    bolumler = None
    if ham:
        bolumler = [b.strip() for b in ham.split(",") if b.strip()]
        bilinmeyen = [b for b in bolumler if b not in LLM.BOLUM_ADLARI]
        if bilinmeyen:
            raise ApiError(
                f"bilinmeyen bölüm: {', '.join(bilinmeyen)}. "
                f"Geçerli bölümler: {', '.join(LLM.BOLUM_ADLARI)}"
            )
    return MetinYanit(LLM.olustur(_client, symbol, bolumler))


def uc_llm_karsilastir(params: dict) -> MetinYanit:
    """İki şirketi karşılaştıran LLM raporu. ?s1=SISE.IS&s2=TRKCM.IS"""
    s1 = (params.get("s1") or [""])[0].strip().upper()
    s2 = (params.get("s2") or [""])[0].strip().upper()
    if not s1 or not s2:
        raise ApiError("'s1' ve 's2' parametreleri gerekli")
    
    ham = (params.get("bolum") or [""])[0].strip()
    bolumler = None
    if ham:
        bolumler = [b.strip() for b in ham.split(",") if b.strip()]
        bilinmeyen = [b for b in bolumler if b not in LLM.BOLUM_ADLARI]
        if bilinmeyen:
            raise ApiError(
                f"bilinmeyen bölüm: {', '.join(bilinmeyen)}. "
                f"Geçerli bölümler: {', '.join(LLM.BOLUM_ADLARI)}"
            )
    return MetinYanit(LLM.karsilastir(_client, s1, s2, bolumler))


def uc_tarama_baslat(params: dict, body: dict | None = None) -> dict:
    market = ((body or {}).get("evren") or "bist").strip().lower()
    if market not in U.market_ids():
        raise ApiError(f"bilinmeyen evren: {market}")
    _tarama.baslat(market)
    return {"basladi": True, "evren": market}


def uc_tarama_durum(params: dict) -> dict:
    return _tarama.durum()


def uc_tarama_iptal(params: dict, body: dict | None = None) -> dict:
    _tarama.iptal_et()
    return {"iptal_istendi": True}


def uc_sirket(params: dict) -> dict:
    symbol = _sembol(params)
    market = U.find_market(_client, symbol)

    profile = _client.profile(symbol)
    pack = F.load(_client, symbol, profile)
    cpi = INF.series_for_pack(_client.cache, pack)
    analysis = H.analyze(_client, symbol, pack, cpi)
    reports = R.analyze_reports(_client, symbol, pack, cpi)
    context = _baglam(market)
    bayraklar = FL.evaluate_flags(_client, symbol, analysis, pack, context)
    ozet = N.generate_company_summary(symbol, analysis, reports, cpi, pack)

    baglam = C.all_metric_contexts(context, symbol) if context else []

    return {
        "uyari": UYARI,
        "symbol": symbol,
        "market": market,
        "profil": {
            "ad": profile.get("name"),
            "sektor": profile.get("sector"),
            "endustri": profile.get("industry"),
            "fiyat": profile.get("last_price"),
            "fiyat_para": profile.get("price_currency"),
            "tablo_para": pack.get("currency"),
            "piyasa_degeri": profile.get("market_cap"),
            "piyasa_degeri_guvenilir": pack.get("market_cap_reliable", True),
            "piyasa_degeri_notu": pack.get("market_cap_note"),
        },
        "ozet": ozet,
        "saglik": analysis,
        "bayraklar": bayraklar,
        "baglam": baglam,
        "baglam_var": context is not None,
        "banka_muhasebesi": pack.get("bank_accounting", False),
    }


def uc_rapor(params: dict) -> dict:
    symbol = _sembol(params)
    pack = F.load(_client, symbol)
    cpi = INF.series_for_pack(_client.cache, pack)
    return {"uyari": UYARI, **R.analyze_reports(_client, symbol, pack, cpi)}


def uc_kalite(params: dict) -> dict:
    symbol = _sembol(params)
    pack = F.load(_client, symbol)
    cpi = INF.series_for_pack(_client.cache, pack)
    analysis = H.analyze(_client, symbol, pack, cpi)
    return {"uyari": UYARI, **H.quality_timeline(_client, symbol, analysis, pack)}


def uc_tarayici_alanlar(params: dict) -> dict:
    return {
        "alanlar": S.field_catalog(),
        "operatorler": sorted(S.OPERATORLER),
        "baglaclar": [S.VE, S.VEYA],
    }


def uc_tarayici_kurallar(params: dict) -> dict:
    return {"kurallar": S.load_rules(), "uyari": UYARI}


def uc_tarayici(params: dict, body: dict | None = None) -> dict:
    market = _evren(params)
    context = _baglam(market)
    if context is None:
        raise ApiError(
            f"'{market}' evreni için bağlam taraması yok. "
            "Önce `python tools/tarama.py " + market + "` çalıştırılmalı.",
            status=409,
        )

    limit = int((params.get("limit") or ["200"])[0])
    sirala = (params.get("sirala") or ["market_cap"])[0]

    sablon_id = (params.get("sablon") or [None])[0]
    if sablon_id:
        sonuc = S.run_template(context, sablon_id, sort_by=sirala, limit=limit)
    else:
        rule = (body or {}).get("kural")
        if not rule:
            raise ApiError("gövdede 'kural' yok (veya 'sablon' parametresi verilmeli)")
        S.validate(rule)
        sonuc = S.screen(context, rule, sort_by=sirala, limit=limit)

    sonuc["uyari"] = UYARI
    sonuc["veri_yasi_saat"] = C.context_age_hours(_client, market)
    return sonuc


def uc_tarayici_kaydet(params: dict, body: dict | None = None) -> dict:
    if not body or "id" not in body or "rule" not in body:
        raise ApiError("gövdede 'id' ve 'rule' gerekli")
    kayitli = S.save_rule(
        {
            "id": str(body["id"]),
            "name": str(body.get("name") or body["id"]),
            "note": "Kullanıcı kuralı.",
            "explanation": str(body.get("explanation") or ""),
            "rule": body["rule"],
        }
    )
    return {"kaydedildi": True, "kural_sayisi": len(kayitli)}


def uc_portfoy(params: dict) -> dict:
    base = (params.get("para") or ["TRY"])[0].upper()
    trades = PF.load_trades()
    ozet = PF.summary(_client, base_currency=base, trades=trades)

    risk = RISK.analyze(_client, ozet)

    market = "bist"
    if ozet["positions"]:
        usd_agirlik = sum(
            satir.get("value_base", 0.0)
            for satir in ozet["positions"]
            if not str(satir["symbol"]).endswith(".IS")
        )
        if ozet["total_value"] and usd_agirlik > ozet["total_value"] / 2:
            market = "us"
    context = _baglam(market)
    kalite = RISK.portfolio_quality(ozet, context)

    cpi = INF.cpi_series(_client.cache, base)
    reel = PF.real_return(ozet, cpi)

    return {
        "uyari": UYARI,
        "ozet": ozet,
        # Ham işlem listesi arayüzde silme için gerekli: pozisyon özeti
        # işlemleri birleştirdiği için tek bir işleme geri dönülemiyor.
        "islemler": trades,
        "risk": risk,
        "kalite": kalite,
        "reel_getiri": reel,
        "baglam_evreni": market,
    }


def uc_portfoy_islem(params: dict, body: dict | None = None) -> dict:
    if not body:
        raise ApiError("gövdede işlem bilgisi yok")
    trades = PF.add_trade(body)
    return {"eklendi": True, "islem_sayisi": len(trades)}


def uc_portfoy_sil(params: dict, body: dict | None = None) -> dict:
    if not body or "index" not in body:
        raise ApiError("gövdede 'index' gerekli")
    trades = PF.remove_trade(int(body["index"]))
    return {"silindi": True, "islem_sayisi": len(trades)}


def uc_portfoy_ice_aktar(params: dict, body: dict | None = None) -> dict:
    if not body or not (body.get("csv") or "").strip():
        raise ApiError("gövdede 'csv' alanı (metin) gerekli")
    return PF.import_csv(body["csv"])


def uc_portfoy_sablon(params: dict) -> MetinYanit:
    return MetinYanit(PF.CSV_SABLONU, tur="text/csv; charset=utf-8")


def uc_piyasa(params: dict) -> dict:
    market = _evren(params)
    context = _baglam(market)
    if context is None:
        raise ApiError(
            f"'{market}' evreni için bağlam taraması yok. "
            "Önce `python tools/tarama.py " + market + "` çalıştırılmalı.",
            status=409,
        )
    return {
        "uyari": UYARI,
        "veri_yasi_saat": C.context_age_hours(_client, market),
        **M.market_snapshot(context),
    }


# Türkçe karakter katlama: "sise" yazınca "Şişe", "turk" yazınca "Türk"
# bulunmalı. Şirket adları Yahoo'da Türkçe karakterli geliyor, kullanıcı ise
# genelde klavyeden düz harf yazar.
_KATLAMA = str.maketrans({
    "Ş": "S", "ş": "s", "İ": "I", "ı": "i", "Ğ": "G", "ğ": "g",
    "Ü": "U", "ü": "u", "Ö": "O", "ö": "o", "Ç": "C", "ç": "c",
})


def _katla(text: str) -> str:
    return (text or "").translate(_KATLAMA).upper()


def uc_ara(params: dict) -> dict:
    query = _katla((params.get("q") or [""])[0].strip())
    if len(query) < 2:
        return {"sonuclar": []}

    sonuclar = []
    for market in U.market_ids():
        cached = _client.cache.get_record("universe", market, ttl=None)
        for entry in (cached or {}).get("entries", []):
            ad = _katla(entry.get("name") or "")
            if query in _katla(entry["symbol"]) or query in ad:
                sonuclar.append(
                    {
                        "symbol": entry["symbol"],
                        "name": entry.get("name"),
                        "market": market,
                        "sector": entry.get("sector"),
                    }
                )
            if len(sonuclar) >= 25:
                break
    return {"sonuclar": sonuclar}


GET_UCLARI = {
    "/api/durum": uc_durum,
    "/api/sirket": uc_sirket,
    "/api/rapor": uc_rapor,
    "/api/kalite": uc_kalite,
    "/api/tarayici/alanlar": uc_tarayici_alanlar,
    "/api/tarayici/kurallar": uc_tarayici_kurallar,
    "/api/tarayici": uc_tarayici,
    "/api/portfoy": uc_portfoy,
    "/api/portfoy/sablon": uc_portfoy_sablon,
    "/api/piyasa": uc_piyasa,
    "/api/ara": uc_ara,
    "/api/tarama/durum": uc_tarama_durum,
    "/api/sozluk": uc_sozluk,
    "/api/llm-rapor": uc_llm_rapor,
    "/api/llm-karsilastir": uc_llm_karsilastir,
}

POST_UCLARI = {
    "/api/tarayici": uc_tarayici,
    "/api/tarayici/kaydet": uc_tarayici_kaydet,
    "/api/portfoy/islem": uc_portfoy_islem,
    "/api/portfoy/sil": uc_portfoy_sil,
    "/api/portfoy/ice-aktar": uc_portfoy_ice_aktar,
    "/api/tarama/baslat": uc_tarama_baslat,
    "/api/tarama/iptal": uc_tarama_iptal,
}


# ================================================================== HTTP katmanı


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=WEB, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._api(parsed.path, urllib.parse.parse_qs(parsed.query), GET_UCLARI)
            return
        if parsed.path == "/favicon.ico":
            # Sayfada ikon data URI olarak gömülü ama tarayıcılar yine de
            # /favicon.ico isteyebiliyor (özellikle önbellekteki eski HTML ile).
            # Karşılamak, her sayfa açılışında log'a 404 basılmasını önlüyor.
            self._ikon()
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _ikon(self) -> None:
        raw = FAVICON.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(404)
            return

        uzunluk = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(uzunluk) if uzunluk else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            self._json({"hata": "gövde geçerli JSON değil"}, status=400)
            return

        self._api(parsed.path, urllib.parse.parse_qs(parsed.query), POST_UCLARI, body)

    def _api(self, path: str, params: dict, tablo: dict, body: dict | None = None) -> None:
        yol = path.rstrip("/")
        handler = tablo.get(yol)
        if handler is None:
            self._json({"hata": f"bilinmeyen uç: {path}"}, status=404)
            return
        try:
            if yol in KORUNAN_UCLAR:
                admin_dogrula(self.headers)
            # YahooClient çerez ve crumb durumunu paylaştığı için tek seferde
            # bir istek işlenir; panel tek kullanıcılı, bu yeterli.
            with _kilit:
                if body is None:
                    sonuc = handler(params)
                else:
                    sonuc = handler(params, body)
        except ApiError as error:
            self._json({"hata": error.message}, status=error.status)
        except S.RuleError as error:
            # Bozuk kural istemci hatasıdır, sunucu hatası değil.
            self._json({"hata": f"kural geçersiz: {error}"}, status=400)
        except (PF.PortfolioError, U.UnknownMarket) as error:
            self._json({"hata": str(error)}, status=400)
        except YahooError as error:
            self._json({"hata": f"veri kaynağına erişilemedi: {error}"}, status=502)
        except Exception as error:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            self._json({"hata": f"{type(error).__name__}: {error}"}, status=500)
        else:
            if isinstance(sonuc, MetinYanit):
                self._metin(sonuc)
            else:
                self._json(sonuc)

    def _json(self, payload, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _metin(self, yanit: MetinYanit, status: int = 200) -> None:
        raw = yanit.metin.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", yanit.tur)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Statik dosya isteklerini susturup yalnızca API ve hataları göster.
        mesaj = format % args
        if "/api/" in mesaj or " 4" in mesaj or " 5" in mesaj:
            sys.stderr.write(f"  {mesaj}\n")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    port = VARSAYILAN_PORT
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])

    os.makedirs(WEB, exist_ok=True)
    adres = f"http://127.0.0.1:{port}"

    print(f"Borsa Paneli — {adres}")
    print(UYARI)

    eksik = [
        market
        for market in U.market_ids()
        if C.load_context(_client, market) is None
    ]
    if eksik:
        print(
            "\nBağlam taraması olmayan evren(ler): "
            + ", ".join(eksik)
            + "\nSektör medyanı, tarayıcı ve piyasa bakışı için:"
        )
        for market in eksik:
            print(f"    python tools/tarama.py {market}")

    if "--no-browser" not in argv:
        threading.Timer(0.7, lambda: webbrowser.open(adres)).start()

    sunucu = HTTPServer(("127.0.0.1", port), Handler)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatılıyor")
    finally:
        sunucu.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
