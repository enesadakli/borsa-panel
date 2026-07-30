"""LLM-okunur şirket raporu — Markdown.

Bir LLM'in panelin arayüzünü scrape etmesine gerek kalmasın diye tek istekte
şirketin tüm analizini düz metin/Markdown olarak döner. `/api/llm-rapor`
ucunun arkasında durur; admin anahtarı yapılandırılmışsa yalnızca doğru
`X-Admin-Anahtar` başlığıyla erişilir (bkz. `server.admin_dogrula`).

İki katman kasıtlı ayrı:
    olustur()      — ağ/önbellek erişimi olan taraf, uc_sirket ile aynı boru
                     hattını kullanır.
    bicimlendir()  — saf, ağsız Markdown üretici; testler bunu doğrudan
                     sentetik bir paketle çağırır.

Sözlük buraya GÖMÜLMEZ: okuyucu bir LLM, terim tanımına ihtiyacı yok
(gerekirse `/api/sozluk`'a ayrıca bakar). Bunun yerine "Yöntem notları"
bölümü, bir insanın değil bir modelin ihtiyaç duyacağı örtük varsayımları
(ondalık ayracı, hangi TÜFE, TTM esası, kaynağın doğrulanmamış olması) açık
yazar.
"""

from __future__ import annotations

from . import bicim as B
from . import context as C
from . import flags as FL
from . import fundamentals as F
from . import health as H
from . import inflation as INF
from . import market as M
from . import narrative as N
from . import reports as R
from . import risk as RISK
from . import universe as U
from .sozluk import UYARI


def olustur(client, symbol: str, bolumler=None) -> str:
    """`uc_sirket` ile aynı boru hattı + `quality_timeline`; tek Markdown metni.

    `bolumler` verilirse yalnızca o bölümler basılır (bkz. `BOLUM_ADLARI`).
    Veri toplama tam yapılır; filtreleme yalnızca çıktıdadır — bölüm seçmek
    hesabı değil, metni kısaltır.
    """
    market = U.find_market(client, symbol)
    profile = client.profile(symbol)
    pack = F.load(client, symbol, profile)
    cpi = INF.series_for_pack(client.cache, pack)
    analysis = H.analyze(client, symbol, pack, cpi)
    reports = R.analyze_reports(client, symbol, pack, cpi)
    context = C.load_context(client, market)
    bayraklar = FL.evaluate_flags(client, symbol, analysis, pack, context)
    ozet = N.generate_company_summary(symbol, analysis, reports, cpi, pack)
    kalite = H.quality_timeline(client, symbol, analysis, pack)

    paket = {
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
            "hisse_sayisi": profile.get("shares_outstanding"),
        },
        "banka_muhasebesi": pack.get("bank_accounting", False),
        "freshness": analysis.get("freshness") or {},
        "ozet": ozet,
        "bayraklar": bayraklar,
        "fscore": analysis.get("fscore") or {},
        "metrikler": _metrik_paketi(analysis, profile, context, symbol),
        "baglam_var": context is not None,
        "baglam_yasi_saat": C.context_age_hours(client, market) if context else None,
        "kalite": kalite,
        "rapor": reports,
        "data_quality": ozet.get("data_quality") or {},
        # --- analiz düğümleri: v1'de buraya hiç girmiyorlardı, rapordan düşüyorlardı
        "altman": analysis.get("altman") or {},
        "degerleme": analysis.get("valuation") or {},
        "getiriler": analysis.get("returns") or {},
        "marjlar": analysis.get("margins") or {},
        "borc": analysis.get("debt") or {},
        "kar_kalitesi": analysis.get("profit_quality") or {},
        "reel_buyume": analysis.get("real_growth") or {},
        "para_birimi": analysis.get("currency"),
        "piyasa": M.market_snapshot(context) if context else {},
        "fiyat": _fiyat_paketi(client, symbol, cpi, profile),
    }
    return bicimlendir(paket, bolumler)


#: Farkı `B.sayi` ile basılacak metrikler (kat/skor cinsi, yüzde değil).
_FARK_SAYI = {"fscore": 1, "altman_z": 1, "net_debt_ebitda": 2,
              "debt_to_equity": 2, "interest_coverage": 2, "pe": 2, "pb": 2}
#: Değeri **zaten puan ölçeğinde** tutulan metrikler. `context.extract_metrics`
#: marj serisini `×100` yaparak alır; farkına `B.yuzde` uygulanırsa 100 kat
#: şişer ("%+4,6" yerine "%+460,0"). Bunlar `B.puan`tan geçer.
_FARK_PUAN = {"gross_margin", "operating_margin", "net_margin"}
#: Gerçekten kesir ölçeğinde kalan metrikler (0,039 = %3,9) — `B.yuzde` doğru
#: dönüştürüyor. Bu üçüncü küme, `_FARK_SAYI`/`_FARK_PUAN` dışında kalan her
#: metriğin **kontrol edilmeden** kesir sayılmasını (eski `else` dalı)
#: engellemek için var: yarın puan ölçekli yeni bir metrik eklenirse ve
#: buraya eklenmezse, aşağıdaki muhafız testi düşer — 100 kat hatası sessizce
#: geri gelmez.
_FARK_KESIR = {"roe", "roa", "fcf_gap", "real_revenue_growth",
               "real_income_growth", "dividend_yield"}


def _fark(metrik: str, v1, v2) -> str:
    """İki değerin farkı, metriğin kendi ölçeğinde."""
    if v1 is None or v2 is None:
        return "—"
    diff = v1 - v2
    if metrik in _FARK_SAYI:
        return B.sayi(diff, _FARK_SAYI[metrik], isaretli=True)
    if metrik in _FARK_PUAN:
        return B.puan(diff, 1, isaretli=True) + " puan"
    if metrik in _FARK_KESIR:
        return B.yuzde(diff, 1, isaretli=True) + " puan"
    raise ValueError(
        f"'{metrik}' hiçbir ölçek sınıfında değil (_FARK_SAYI/_FARK_PUAN/"
        f"_FARK_KESIR). Sessizce B.yuzde'ye düşseydi puan ölçekli bir metrik "
        f"100 kat hatalı basılabilirdi — önce doğru sınıfa eklenmeli."
    )


def kiyaslama_matrisi(s1: str, s2: str, degerler1: dict, degerler2: dict) -> list[str]:
    """İki metrik sözlüğünü yan yana koyan tablo. Saf — ağ çağrısı yapmaz."""
    out = ["## Kıyaslama Matrisi", ""]
    out.append(f"| Metrik | {s1} | {s2} | Fark ({s1} - {s2}) |")
    out.append("|---|---|---|---|")
    for metrik, etiket in C.METRIKLER:
        v1 = degerler1.get(metrik)
        v2 = degerler2.get(metrik)
        if v1 is None and v2 is None:
            continue
        out.append(
            f"| {etiket} | {_metrik_deger(metrik, v1)} | {_metrik_deger(metrik, v2)} "
            f"| {_fark(metrik, v1, v2)} |"
        )
    out.append("")
    return out


def _metrik_degerleri(client, symbol: str) -> dict:
    """Tek sembolün 16 metriğinin ham değerleri."""
    profile = client.profile(symbol)
    pack = F.load(client, symbol, profile)
    cpi = INF.series_for_pack(client.cache, pack)
    analysis = H.analyze(client, symbol, pack, cpi)
    return C.extract_metrics(analysis, profile).get("values") or {}


def karsilastir(client, s1: str, s2: str, bolumler=None) -> str:
    """İki şirketin tam raporu + doğrudan kıyaslama matrisi.

    Not: `olustur()` analizi zaten yapıyor, `_metrik_degerleri()` ikinci kez
    yapıyor. Önbellek ağ trafiğini kurtarıyor ama hesap iki kez dönüyor;
    `olustur()` paketi de döndürecek şekilde ayrılırsa bu tekrar kalkar.
    """
    out = [
        f"# {s1} ve {s2} Karşılaştırması",
        "",
        "Bu rapor iki şirketin bireysel analizlerini ve ardından doğrudan "
        "kıyaslama matrisini içerir.",
        "",
        "---",
        "",
        olustur(client, s1, bolumler).strip(),
        "",
        "---",
        "",
        olustur(client, s2, bolumler).strip(),
        "",
        "---",
        "",
    ]
    out.extend(kiyaslama_matrisi(
        s1, s2, _metrik_degerleri(client, s1), _metrik_degerleri(client, s2)
    ))
    out.append(f"> {UYARI}")
    return "\n".join(out)


def _fiyat_paketi(client, symbol: str, cpi: dict, profile: dict) -> dict:
    """Fiyat istatistiği + reel karşılığı.

    TÜFE kasıtlı olarak `risk.py`'ye girmiyor (katman temizliği): reel bacak
    burada, `cpi` zaten elimizdeyken hesaplanıyor.
    """
    stats = RISK.symbol_price_stats(client, symbol)
    if not stats.get("available"):
        return stats
    stats["currency"] = profile.get("price_currency")
    if stats.get("change") is not None:
        reel = INF.real_growth(cpi, stats["change"], stats["start"], stats["end"])
        stats["real_change"] = reel.get("real")
        stats["cpi_growth"] = reel.get("cpi_growth")
    return stats


def _metrik_paketi(analysis: dict, profile: dict, context: dict | None,
                   symbol: str) -> list[dict]:
    """16 metriği **her koşulda** üretir; bağlam yalnızca karşılaştırma ekler.

    v1'in kırılganlığı buradaydı: tablo yalnızca `C.all_metric_contexts()`'ten
    besleniyordu ve o fonksiyon (a) evren hiç taranmamışsa **veya** (b) sembol
    tarama kaydında yoksa boş dönüyordu — rapor da ROE/Altman/marj/borç
    oranlarını tamamen kaybediyordu. Artık değer ve trend **analizden** gelir
    (her zaman var); sektör/evren sütunları yalnızca zenginleştirmedir.

    Tarama kaydı 7 güne kadar eski olabilirken `analysis` az önce hesaplandı;
    bu yüzden bağlam **asla** `value`/`trend` üzerine yazmaz — canlı analiz
    kazanır, yüzdelik biraz eski bir dağılıma göre ölçülmüş olur (bu fark
    "Veri kalitesi notları"nda yazılıdır).
    """
    temel = C.extract_metrics(analysis, profile)
    degerler = temel.get("values") or {}
    gecersiz = set(temel.get("not_applicable") or ())
    trendler = C.extract_trends(analysis)

    kayitli = bool(context and symbol in (context.get("symbols") or {}))

    satirlar = []
    for metrik, etiket in C.METRIKLER:
        deger = degerler.get(metrik)
        satir = {
            "metric": metrik,
            "label": etiket,
            "value": deger,
            "not_applicable": metrik in gecersiz,
            "trend": (trendler.get(metrik) or {}).get("direction"),
        }
        if kayitli:
            b = C.get_metric_context(context, symbol, metrik)
            for alan in ("sector_median", "sector_n", "sector_percentile",
                         "universe_median", "universe_n", "universe_percentile",
                         "sector_note"):
                if b.get(alan) is not None:
                    satir[alan] = b[alan]
        satirlar.append(satir)
    return satirlar


# Bölüm anahtarı -> üretici. `?bolum=` parametresi bu anahtarları kabul eder;
# sıra burada tanımlı ve raporun okuma sırasıdır.
BOLUMLER: tuple[tuple[str, object], ...] = ()  # aşağıda, fonksiyonlar tanımlandıktan sonra dolduruluyor


def bicimlendir(paket: dict, bolumler=None) -> str:
    """Saf Markdown üretici — ağ çağrısı yapmaz, yalnızca `paket`i okur.

    `bolumler` verilirse yalnızca o bölümler basılır (bkz. `BOLUMLER`
    anahtarları). Dar bir soruda ("borcu nasıl?") modele 14 KB yerine 2 KB
    vermeyi sağlıyor — gerçek bir RAG kurmadan, sıfır bağımlılıkla.
    """
    p = paket.get("profil") or {}
    satirlar: list[str] = []

    satirlar.append(f"# {paket.get('symbol', '?')} — {p.get('ad') or ''}".rstrip())
    satirlar.append("")

    istenen = set(bolumler) if bolumler else None
    for anahtar, uretici in BOLUMLER:
        if istenen is not None and anahtar not in istenen:
            continue
        satirlar.extend(uretici(paket, p) if anahtar in ("ozet", "kimlik") else uretici(paket))

    satirlar.append(f"> {UYARI}")
    return "\n".join(satirlar) + "\n"


# ----------------------------------------------------------- ortak yardımcılar


def _kaynaklar(sources, limit: int = 4) -> str:
    """`kalem@dönem` listesi. Beş ayrı yerde satır içi tekrarlanıyordu."""
    return ", ".join(
        f"{k.get('item')}@{k.get('period') or '—'}" for k in (sources or [])[:limit]
    )


def _metrik_node(etiket: str, node: dict | None, bicim=None) -> str | None:
    """Tek bir `health.metric()` sözlüğünü tek satıra basar.

    `detail` metni değeri **ve tabanını** birlikte taşıyor ("ROE = %8,4
    (TTM kâr)"), o yüzden değer ayrıca yazılmıyor — aynı sayıyı iki kez
    yazmamak bu raporun verimlilik kuralı. `bicim` yalnızca `detail` yoksa
    devreye giriyor.
    """
    if not node:
        return None
    durum = node.get("status")
    detay = node.get("detail")
    if durum == H.GECERSIZ:
        return f"- {etiket}: sektörde tanımsız" + (f" ({detay})" if detay else "")
    if durum == H.EKSIK or node.get("value") is None:
        return f"- {etiket}: —" + (f" ({detay})" if detay else " (hesaplanamadı)")

    govde = detay or (bicim(node["value"]) if bicim else B.sayi(node["value"], 2))
    kaynak = _kaynaklar(node.get("sources"))
    return f"- {etiket}: {govde}" + (f" — kaynak: {kaynak}" if kaynak else "")


def _tarihce(basliklar: list[str], satirlar: list[list[str]]) -> list[str]:
    """≤4 sütunlu Markdown tablosu. Geniş tablolar 8B modellerde satır kaydırıyor."""
    if not satirlar:
        return []
    out = ["", "| " + " | ".join(basliklar) + " |", "|" + "---|" * len(basliklar)]
    out.extend("| " + " | ".join(hucre) + " |" for hucre in satirlar)
    return out


# ------------------------------------------------------------------- bölümler


#: Brüt marj bu eşiğin üstünde, faaliyet marjı alttakinin altındaysa aradaki
#: fark gider tarafında eriyor demektir (puan cinsinden, marj serisiyle aynı ölçek).
CAPRAZ_BRUT_ESIGI = 20.0
CAPRAZ_FAALIYET_ESIGI = 5.0
#: Net kâr bundan hızlı büyürken serbest nakit akışı negatifse büyüme nakde dönmüyor.
CAPRAZ_KAR_BUYUME_ESIGI = 0.10


def _marj_seviyesi(marjlar: dict, ad: str):
    """Son dönemin marj **seviyesi** (puan cinsinden), yoksa None.

    `*_trend` düğümünün `value` alanı marj değil, `health._slope()`'tan gelen
    **eğimdir** (yılda kaç puan değişim). Seviye yalnızca `series`te durur;
    ikisini karıştırmak sessiz ve tespiti zor bir hata üretir.
    """
    noktalar = (marjlar.get("series") or {}).get(ad) or []
    return noktalar[-1][1] if noktalar else None


def _capraz_inceleme(paket: dict) -> list[str]:
    """Tek başına bakıldığında normal, birlikte bakıldığında anlam değiştiren
    metrik çiftleri. Yorum değil, iki rakamın aynı cümlede durması."""
    out = []

    marjlar = paket.get("marjlar") or {}
    brut = _marj_seviyesi(marjlar, "gross")
    faaliyet = _marj_seviyesi(marjlar, "operating")
    if (brut is not None and faaliyet is not None
            and brut > CAPRAZ_BRUT_ESIGI and faaliyet < CAPRAZ_FAALIYET_ESIGI):
        out.append(
            f"- Operasyonel baskı: brüt marj {B.puan(brut, 1)}, buna karşılık "
            f"faaliyet marjı {B.puan(faaliyet, 1)}. Brüt kârla faaliyet kârı "
            f"arasındaki fark faaliyet giderlerinde eriyor."
        )

    rapor = (paket.get("rapor") or {}).get("annual") or {}
    satirlar = rapor.get("lines") or []
    kar_satiri = next((s for s in satirlar if s.get("key") == "NetIncome"), None)
    kar_buyume = (kar_satiri.get("yoy") or {}).get("pct") if kar_satiri else None
    gecmis = (paket.get("kar_kalitesi") or {}).get("history") or []
    fcf = gecmis[-1].get("free_cash_flow") if gecmis else None

    if (kar_buyume is not None and fcf is not None
            and kar_buyume > CAPRAZ_KAR_BUYUME_ESIGI and fcf < 0):
        out.append(
            f"- Nakit kalitesi çelişkisi: net kâr yıllık {B.yuzde(kar_buyume)} "
            f"artarken son dönem serbest nakit akışı negatif ({B.para(fcf)}). "
            f"Büyüyen kâr aynı dönemde nakde dönmemiş."
        )

    if not out:
        return []
    return ["## Çapraz İnceleme Notları", ""] + out + [""]


def _kimlik(paket: dict, p: dict) -> list[str]:
    out = ["## Kimlik", ""]
    out.append(f"- Piyasa: {paket.get('market') or '—'}")
    out.append(f"- Sektör: {p.get('sektor') or '—'}")
    out.append(f"- Endüstri: {p.get('endustri') or '—'}")
    out.append(f"- Mali tablo para birimi: {p.get('tablo_para') or '—'}")
    out.append(f"- Fiyat para birimi: {p.get('fiyat_para') or '—'}")
    if p.get("fiyat") is not None:
        out.append(f"- Son kapanış: {B.sayi(p['fiyat'], 2)} {p.get('fiyat_para') or ''}".rstrip())
    if p.get("piyasa_degeri") is not None:
        guven = "" if p.get("piyasa_degeri_guvenilir", True) else " (güvenilirlik şüpheli — " + (p.get("piyasa_degeri_notu") or "") + ")"
        out.append(f"- Piyasa değeri: {B.para(p['piyasa_degeri'])}{guven}")
    if paket.get("banka_muhasebesi"):
        out.append(
            "- Banka/finans muhasebesi: brüt kâr, FAVÖK, cari oran, net borç "
            "bu sektörde tanımsız — hesaplanmadı."
        )
    out.append("")
    return out


def _tazelik(paket: dict) -> list[str]:
    taze = paket.get("freshness") or {}
    if not taze.get("latest_period"):
        return []
    out = ["## Veri tazeliği", ""]
    out.append(f"- Son dönem: {taze['latest_period']} ({taze.get('label') or 'yaş bilinmiyor'})")
    out.append(f"- Tazelik seviyesi: {taze.get('level') or '—'}")
    if taze.get("annual_stale") and taze.get("last_annual"):
        out.append(
            f"- F-Skoru ve yıllık karşılaştırmalar {taze['last_annual']} tablosundan "
            "geliyor; bu tarih güncel değil."
        )
    out.append("")
    return out


def _ozet(paket: dict) -> list[str]:
    cumleler = (paket.get("ozet") or {}).get("sentences") or []
    if not cumleler:
        return []
    out = ["## Kural tabanlı özet", ""]
    for c in cumleler:
        kaynaklar = ", ".join(
            f"{k.get('item')}@{k.get('period') or '—'}" for k in (c.get("sources") or [])[:4]
        )
        satir = f"- {c['text']} [{c['rule_id']}]"
        if kaynaklar:
            satir += f" — kaynak: {kaynaklar}"
        out.append(satir)
    out.append("")
    return out


def _bayraklar(paket: dict) -> list[str]:
    b = paket.get("bayraklar") or {}
    tetiklenen = (b.get("flags") or []) + (b.get("notes") or [])
    out = ["## Bayraklar", ""]
    if not tetiklenen:
        out.append("- Tanımlı kurallardan hiçbiri tetiklenmedi.")
    for bayrak in tetiklenen:
        out.append(f"- **[{bayrak['level']}] {bayrak['id']} — {bayrak['title']}**")
        if bayrak.get("explanation"):
            out.append(f"  {bayrak['explanation']}")
    calismayan = b.get("not_applied") or []
    if calismayan:
        out.append("")
        out.append("Çalıştırılmayan kurallar:")
        for k in calismayan:
            out.append(f"- {k['id']}: {k.get('skip_reason') or '—'}")
    out.append("")
    return out


def _fskoru(paket: dict) -> list[str]:
    fscore = paket.get("fscore") or {}
    son = fscore.get("latest")
    if not son:
        return []
    out = ["## Piotroski F-Skoru", ""]
    taban = f"{son['score']}/9"
    etiket = son.get("label") or ""
    ek = etiket[len(taban):].strip() if etiket.startswith(taban) else etiket
    satir = f"- Skor: {taban} ({son.get('date') or '—'})"
    
    metrikler = paket.get("metrikler") or []
    f_metrik = next((m for m in metrikler if m.get("metric") == "fscore"), None)
    if f_metrik and f_metrik.get("sector_median") is not None:
        medyan = f_metrik.get("sector_median")
        yuzdelik = f_metrik.get("sector_percentile")
        konum = _konum(son["score"], medyan)
        dilim = f", sektörün %{round(yuzdelik)}'lik diliminde" if yuzdelik is not None else ""
        satir += f" — sektör medyanı {B.sayi(medyan, 0)}/9 (n={f_metrik.get('sector_n', 0)}){dilim} ({konum})"

    if ek:
        satir += f" {ek}"
    out.append(satir)
    if fscore.get("model_note"):
        out.append(f"- Model notu: {fscore['model_note']}")
    out.append("")
    out.append("| Kriter | Durum | Detay |")
    out.append("|---|---|---|")
    for k in son.get("criteria") or []:
        durum = {"ok": "geçti" if k.get("passed") else "kalmadı",
                 "eksik_veri": "veri yok", "sektorde_gecersiz": "sektörde tanımsız"}.get(
            k.get("status"), k.get("status") or "—"
        )
        out.append(f"| {k['id']} | {durum} | {k.get('detail') or '—'} |")
    out.append("")
    gecmis = fscore.get("usable_points") or []
    if len(gecmis) >= 2:
        seri = " → ".join(f"{n['date'][:4]}:{n['score']}/9" for n in gecmis)
        out.append(f"- Geçmiş: {seri}")
        out.append("")
    return out


# Metrik anahtarı -> gösterim biçimi. web/app.js'teki METRIK_BICIM'in Python
# karşılığı; iki ayrı yüzey (arayüz/rapor) olduğu için kasıtlı olarak ayrı
# tutulur, ama ikisi de core.bicim'den geçer (tek gerçek kaynak orada).
_METRIK_BICIM = {
    "fscore": lambda v: f"{B.sayi(v, 0)}/9",
    "altman_z": B.altman,
    "roe": lambda v: B.yuzde(v, 1, False),
    "roa": lambda v: B.yuzde(v, 1, False),
    "gross_margin": lambda v: B.puan(v, 1),
    "operating_margin": lambda v: B.puan(v, 1),
    "net_margin": lambda v: B.puan(v, 1),
    "net_debt_ebitda": lambda v: B.oran(v, 2),
    "debt_to_equity": lambda v: B.oran(v, 2),
    "interest_coverage": lambda v: B.kat(v, 1),
    "fcf_gap": lambda v: B.yuzde(v, 1, False),
    "real_revenue_growth": B.yuzde,
    "real_income_growth": B.yuzde,
    "pe": lambda v: B.oran(v, 2),
    "pb": lambda v: B.oran(v, 2),
    "dividend_yield": lambda v: B.yuzde(v, 1, False),
}


def _metrik_deger(metrik: str, value) -> str:
    if value is None:
        return "—"
    fn = _METRIK_BICIM.get(metrik)
    return fn(value) if fn else B.sayi(value, 2)


def _metrikler(paket: dict) -> list[str]:
    """Satır bazlı metrik listesi — karşılaştırma **hazır yazılmış** olarak.

    Eskiden 8 sütunlu bir tabloydu; 8B sınıfı yerel modeller geniş Markdown
    tablolarında satır kaydırıyor ve "5 > 4, demek ki üstünde" çıkarımını 16
    metrik boyunca kendileri yapmak zorunda kalıp hata biriktiriyorlar.
    Konum artık burada hesaplanıp cümleye yazılıyor. Bu bir **yargı değil**:
    hangi yönün arzu edilir olduğu söylenmiyor, yalnızca nerede durduğu.
    """
    satirlar = paket.get("metrikler") or []
    if not satirlar:
        return []
    out = ["## Metrikler ve sektör bağlamı", ""]
    out.append(
        "Değer ve kendi trendi bu isteğe ait analizden gelir; sektör/evren "
        "karşılaştırmaları yalnızca evren taraması yapılmışsa doldurulur."
    )
    out.append("")

    for item in satirlar:
        metrik = item.get("metric")
        etiket = item.get("label") or metrik
        if item.get("not_applicable"):
            out.append(f"- {etiket}: sektörde tanımsız")
            continue

        deger = item.get("value")
        if deger is None:
            out.append(f"- {etiket}: — (hesaplanamadı)")
            continue

        parca = [f"- {etiket}: {_metrik_deger(metrik, deger)}"]
        medyan = item.get("sector_median")
        if medyan is not None:
            konum = _konum(deger, medyan)
            yuzdelik = item.get("sector_percentile")
            dilim = (f", sektörün %{round(yuzdelik)}'lik diliminde"
                     if yuzdelik is not None else "")
            parca.append(
                f" — sektör medyanı {_metrik_deger(metrik, medyan)} "
                f"(n={item.get('sector_n', 0)}){dilim} ({konum})"
            )
        elif item.get("sector_note"):
            parca.append(f" — {item['sector_note']}")

        evren = item.get("universe_median")
        if evren is not None:
            up = item.get("universe_percentile")
            parca.append(
                f"; evren medyanı {_metrik_deger(metrik, evren)}"
                + (f" (%{round(up)}'lik dilim)" if up is not None else "")
            )
        trend = item.get("trend")
        if trend:
            parca.append(f"; kendi trendi {trend}")
        out.append("".join(parca))

    out.append("")
    return out


def _konum(deger, medyan) -> str:
    """Karşılaştırmayı okuyucu yerine burada yapar — 8B model çıkarım yapmasın."""
    if deger > medyan:
        return "medyanın üstünde"
    if deger < medyan:
        return "medyanın altında"
    return "medyanla aynı"


def _ozet_blok(paket: dict, p: dict) -> list[str]:
    """Raporun en başındaki yoğun özet.

    Uzun bir dokümanda 8B model başı ve sonu iyi, ortayı zayıf hatırlıyor
    ("lost in the middle"); en kritik bilgi bu yüzden en başta duruyor.
    Buradaki her sayı aşağıdaki bölümlerde ayrıntısıyla tekrar geçiyor —
    bu, kuralın bilinçli tek istisnası.
    """
    out = ["## Özet", ""]
    taze = paket.get("freshness") or {}
    out.append(
        f"- {paket.get('symbol')} · {p.get('sektor') or '—'} · "
        f"tablolar {p.get('tablo_para') or '—'} · "
        f"dönem {taze.get('latest_period') or '—'}"
        + (f" ({taze.get('label')})" if taze.get("label") else "")
    )

    degerler = {m.get("metric"): m for m in (paket.get("metrikler") or [])}

    def kisa(metrik: str, etiket: str) -> None:
        item = degerler.get(metrik) or {}
        if item.get("not_applicable"):
            out.append(f"- {etiket}: sektörde tanımsız")
        elif item.get("value") is not None:
            out.append(f"- {etiket}: {_metrik_deger(metrik, item['value'])}")

    kisa("fscore", "F-Skoru")
    altman = paket.get("altman") or {}
    if altman.get("zone"):
        out.append(f"- Altman Z: {B.altman(altman.get('value'))} ({altman['zone']})")
    kisa("real_revenue_growth", "Reel gelir büyümesi")
    kisa("net_debt_ebitda", "Net borç/FAVÖK")
    kisa("roe", "ROE")

    b = paket.get("bayraklar") or {}
    tetiklenen = b.get("flags") or []
    if tetiklenen:
        idler = ", ".join(f["id"] for f in tetiklenen)
        out.append(
            f"- Tetiklenen bayrak: {b.get('red_count', 0)} kırmızı, "
            f"{b.get('yellow_count', 0)} sarı — {idler}"
        )
    else:
        out.append("- Tetiklenen bayrak yok.")

    dq = paket.get("data_quality") or {}
    eksik = len(dq.get("missing_items") or [])
    out.append(
        f"- Veri: {eksik} kalem eksik · "
        f"TÜFE {'var' if dq.get('cpi_available') else 'yok'} · "
        f"sektör bağlamı {'var' if paket.get('baglam_var') else 'yok'}"
    )
    out.append("")
    return out


def _altman(paket: dict) -> list[str]:
    a = paket.get("altman") or {}
    if not a:
        return []
    out = ["## Altman Z-Skoru", ""]
    satir = _metrik_node("Z-Skoru", a, B.altman)
    if satir:
        out.append(satir)
    if a.get("zone"):
        out.append(f"- Modelin tanımına göre: {a['zone']}")
    bilesenler = a.get("components") or {}
    if bilesenler:
        out.append("")
        out.append("Bileşenler (Altman'ın beş terimi):")
        for anahtar in ("X1", "X2", "X3", "X4", "X5"):
            if anahtar in bilesenler:
                out.append(f"- {anahtar}: {B.oran(bilesenler[anahtar])}")
    out.append("")
    return out


def _degerleme(paket: dict) -> list[str]:
    d = paket.get("degerleme") or {}
    if not d:
        return []
    out = ["## Değerleme", ""]
    for etiket, anahtar, bicim in (("F/K", "pe", lambda v: B.oran(v, 2)),
                                   ("PD/DD", "pb", lambda v: B.oran(v, 2))):
        satir = _metrik_node(etiket, d.get(anahtar), bicim)
        if satir:
            taban = (d.get(anahtar) or {}).get("basis")
            out.append(satir + (f" (taban: {taban})" if taban else ""))
    if d.get("market_cap_statement_currency") is not None:
        cevrildi = " (fiyat para biriminden çevrildi)" if d.get("converted") else ""
        out.append(
            f"- Oranlarda kullanılan piyasa değeri: "
            f"{B.para(d['market_cap_statement_currency'])} "
            f"{d.get('currency') or ''}{cevrildi}".rstrip()
        )
    if d.get("market_cap_note"):
        out.append(f"- {d['market_cap_note']}")
    out.append("")
    return out


def _karlilik(paket: dict) -> list[str]:
    getiriler = paket.get("getiriler") or {}
    marjlar = paket.get("marjlar") or {}
    if not getiriler and not marjlar:
        return []
    out = ["## Kârlılık", ""]
    for etiket, anahtar in (("ROE", "roe"), ("ROA", "roa")):
        satir = _metrik_node(etiket, getiriler.get(anahtar))
        if satir:
            out.append(satir)
    for etiket, anahtar in (("Brüt marj eğilimi", "gross_trend"),
                            ("Faaliyet marjı eğilimi", "operating_trend"),
                            ("Net marj eğilimi", "net_trend")):
        node = marjlar.get(anahtar)
        satir = _metrik_node(etiket, node, lambda v: B.sayi(v, 1, True))
        if satir:
            yon = (node or {}).get("direction")
            out.append(satir + (f" — yön: {yon}" if yon else ""))

    seri = marjlar.get("series") or {}
    tarihler = [tarih for tarih, _ in (seri.get("operating") or seri.get("net") or [])]
    if tarihler:
        sozluk = {ad: dict(seri.get(ad) or []) for ad in ("gross", "operating", "net")}
        
        if len(tarihler) >= 2:
            ilk_tarih = tarihler[0]
            son_tarih = tarihler[-1]
            ilk_yil = ilk_tarih[:4]
            son_yil = son_tarih[:4]
            ilk_marj = sozluk["operating"].get(ilk_tarih)
            son_marj = sozluk["operating"].get(son_tarih)
            if ilk_marj is not None and son_marj is not None:
                out.append(f"- Faaliyet Marjı Tarihçesi: {ilk_yil}: {B.puan(ilk_marj, 1)} -> {son_yil}: {B.puan(son_marj, 1)}")
                out.append("")

        out.extend(_tarihce(
            ["Dönem", "Brüt marj", "Faaliyet marjı", "Net marj"],
            [[tarih,
              B.puan(sozluk["gross"].get(tarih), 1) if sozluk["gross"].get(tarih) is not None else "—",
              B.puan(sozluk["operating"].get(tarih), 1) if sozluk["operating"].get(tarih) is not None else "—",
              B.puan(sozluk["net"].get(tarih), 1) if sozluk["net"].get(tarih) is not None else "—"]
             for tarih in tarihler],
        ))
    out.append("")
    return out


def _borc(paket: dict) -> list[str]:
    b = paket.get("borc") or {}
    if not b:
        return []
    out = ["## Borç profili", ""]
    for etiket, anahtar in (("Borç/özsermaye", "debt_to_equity"),
                            ("Net borç/FAVÖK", "net_debt_ebitda"),
                            ("Faiz karşılama", "interest_coverage"),
                            ("Kısa vadeli borcun payı", "short_term_share"),
                            ("Özsermaye durumu", "equity_negative"),
                            ("İşletme sermayesi değişimi", "nwc_change")):
        satir = _metrik_node(etiket, b.get(anahtar))
        if satir:
            out.append(satir)

    gecmis = b.get("history") or []
    if gecmis:
        # Tablo öncesi kısa özet (Trend cümlesi)
        gecerli_oranlar = [r for r in gecmis if r.get("net_debt_ebitda") is not None]
        if len(gecerli_oranlar) >= 2:
            ilk = gecerli_oranlar[0]
            son = gecerli_oranlar[-1]
            ilk_yil = ilk.get("date", "")[:4]
            son_yil = son.get("date", "")[:4]
            ilk_oran = B.oran(ilk["net_debt_ebitda"], 2)
            son_oran = B.oran(son["net_debt_ebitda"], 2)
            out.append(f"- Net Borç/FAVÖK Tarihçesi: {ilk_yil}: {ilk_oran} -> {son_yil}: {son_oran}")
            out.append("")

        out.extend(_tarihce(
            ["Dönem", "Net borç", "FAVÖK", "Net borç/FAVÖK"],
            [[r.get("date") or "—", B.para(r.get("net_debt")), B.para(r.get("ebitda")),
              B.oran(r["net_debt_ebitda"], 2) if r.get("net_debt_ebitda") is not None else "—"]
             for r in gecmis],
        ))
        if any(r.get("net_debt_ebitda") is None for r in gecmis):
            out.append("")
            out.append(
                "Boş bir oran hücresi, FAVÖK'ün şirket ölçeğine göre sıfıra yaklaştığı "
                "ve oranın anlam taşımadığı dönemi gösterir."
            )
    out.append("")
    return out


def _kar_kalitesi(paket: dict) -> list[str]:
    k = paket.get("kar_kalitesi") or {}
    if not k:
        return []
    out = ["## Kâr kalitesi", ""]
    for etiket, anahtar in (("Kâr–nakit sapması", "fcf_gap"),
                            ("Tahakkuk oranı (Sloan)", "accrual_ratio"),
                            ("FCF marjı", "fcf_margin"),
                            ("Temettünün nakit karşılığı", "fcf_payout")):
        satir = _metrik_node(etiket, k.get(anahtar))
        if satir:
            out.append(satir)

    gecmis = k.get("history") or []
    if gecmis:
        out.extend(_tarihce(
            ["Dönem", "Net kâr", "Faaliyet nakit akışı", "Serbest nakit akışı"],
            [[r.get("date") or "—", B.para(r.get("net_income")),
              B.para(r.get("operating_cash_flow")), B.para(r.get("free_cash_flow"))]
             for r in gecmis],
        ))
    out.append("")
    return out


def _reel_buyume(paket: dict) -> list[str]:
    rg = paket.get("reel_buyume") or {}
    if not rg:
        return []
    out = ["## Reel büyüme", ""]
    out.append(
        "Nominal büyümeden dönem enflasyonu arındırılmıştır; kullanılan TÜFE "
        "serisi mali tablo para birimine göre seçilir."
    )
    out.append("")

    for etiket, anahtar in (("Gelir", "revenue"), ("Net kâr", "net_income")):
        d = rg.get(anahtar) or {}
        if d.get("real") is None:
            sebep = d.get("detail") or "reel karşılığı hesaplanamadı"
            nominal = d.get("nominal")
            nom = f" (nominal {B.yuzde(nominal)})" if nominal is not None else ""
            out.append(f"- {etiket}: —{nom} — {sebep}")
            continue
        out.append(
            f"- {etiket}: reel {B.yuzde(d['real'])} "
            f"(nominal {B.yuzde(d.get('nominal'))}, "
            f"TÜFE {B.yuzde(d.get('cpi_growth'), 1, False)})"
            + (f" — taban: {d['label']}" if d.get("label") else "")
        )
        kaynak = _kaynaklar(d.get("sources"))
        if kaynak:
            out.append(f"  kaynak: {kaynak}")

    gelir_gecmis = (rg.get("revenue") or {}).get("history") or []
    kar_gecmis = {r.get("date"): r for r in ((rg.get("net_income") or {}).get("history") or [])}
    if gelir_gecmis:
        out.extend(_tarihce(
            ["Dönem", "Gelir reel", "Net kâr reel", "TÜFE"],
            [[r.get("date") or "—", B.yuzde(r.get("real")),
              B.yuzde((kar_gecmis.get(r.get("date")) or {}).get("real")),
              B.yuzde(r.get("cpi_growth"), 1, False)]
             for r in gelir_gecmis],
        ))

    seri = rg.get("real_revenue_series") or {}
    noktalar = seri.get("points") or []
    if len(noktalar) >= 2:
        out.append("")
        out.append(
            f"Sabit fiyatlarla gelir (taban {seri.get('base') or '—'}"
            + (f", {seri['label']}" if seri.get("label") else "") + "):"
        )
        out.extend(_tarihce(
            ["Dönem", "Gelir (sabit fiyat)"],
            [[tarih, B.para(deger)] for tarih, deger in noktalar],
        ))
        atlanan = seri.get("skipped") or []
        if atlanan:
            out.append("")
            out.append(f"- TÜFE verisi olmadığı için atlanan dönem: {', '.join(atlanan)}")
    out.append("")
    return out


def _kalite(paket: dict) -> list[str]:
    kalite = paket.get("kalite") or {}
    ozet = kalite.get("summary") or {}  # {"rule_id","text","sources"} — QT_OZET cümlesi
    fscore_serisi = kalite.get("fscore") or []
    if not ozet.get("text") and len(fscore_serisi) < 2:
        return []
    out = ["## Kalite zaman çizgisi", ""]
    if fscore_serisi:
        seri = " → ".join(f"{n['date'][:4]}:{n['value']}" for n in fscore_serisi)
        out.append(f"- F-Skoru serisi: {seri}")
    if ozet.get("text"):
        out.append(f"- {ozet['text']} [{ozet.get('rule_id', 'QT_OZET')}]")
    if kalite.get("axis_note"):
        out.append(f"- {kalite['axis_note']}")
    out.append("")
    return out


def _ceyrek(paket: dict) -> list[str]:
    return _donem_bloku(paket, "quarterly", "## Son çeyrek", qoq=True)


def _yillik(paket: dict) -> list[str]:
    """Yıllık karşılaştırma — v1'de hesaplanıyor ama hiç basılmıyordu.

    `REP_BORC_ORANI` yorumu **yalnızca** yıllık blokta üretiliyor; o kural
    v1 raporunda hiç görünmüyordu.
    """
    return _donem_bloku(paket, "annual", "## Yıllık karşılaştırma", qoq=False)


def _donem_bloku(paket: dict, anahtar: str, baslik: str, qoq: bool) -> list[str]:
    """Bir dönem karşılaştırmasını basar (çeyreklik ya da yıllık).

    Yıllıkta `year_ago == previous` olduğu için YoY ve QoQ aynı sayıdır;
    o yüzden `qoq` sütunu yalnızca çeyreklikte açılır.
    """
    rapor = paket.get("rapor") or {}
    d = rapor.get(anahtar) or {}
    if not d.get("available"):
        return []
    para_birimi = rapor.get("currency") or ""
    out = [baslik, ""]
    out.append(f"- Dönem: {d.get('current_date') or '—'}" + (
        f" (karşılaştırma: {d['compare_date']})" if d.get("compare_date") else ""
    ))

    reel = d.get("real_revenue") or {}
    if reel.get("real") is not None:
        out.append(
            f"- Gelir reel değişim: {B.yuzde(reel['real'])} "
            f"(nominal {B.yuzde(reel.get('nominal'))}, "
            f"TÜFE {B.yuzde(reel.get('cpi_growth'), 1, False)})"
        )

    basliklar = ["Kalem", "Tutar", "Yıllık değişim"] + (["Çeyreklik"] if qoq else [])
    satirlar = []
    for satir in d.get("lines") or []:
        hucre = [
            satir.get("label") or satir.get("key") or "—",
            f"{B.para(satir.get('value'))} {para_birimi}".strip(),
            _degisim(satir.get("yoy")),
        ]
        if qoq:
            hucre.append(_degisim(satir.get("qoq")))
        satirlar.append(hucre)
    out.extend(_tarihce(basliklar, satirlar))

    marjlar = d.get("margins") or {}
    if marjlar:
        out.extend(_tarihce(
            ["Marj", "Bu dönem", "Karşılaştırma", "Fark"],
            [[m.get("label") or ad, B.puan(m.get("now"), 1), B.puan(m.get("before"), 1),
              f"{B.sayi(m['delta'], 1, True)} puan" if m.get("delta") is not None else "—"]
             for ad, m in marjlar.items()],
        ))

    yorumlar = d.get("comments") or []
    if yorumlar:
        out.append("")
        for y in yorumlar:
            out.append(f"- {y['text']} [{y['rule_id']}]")
    out.append("")
    return out


def _degisim(node: dict | None) -> str:
    if not node:
        return "—"
    if node.get("pct") is not None:
        return B.yuzde(node["pct"])
    return node.get("note") or "—"


# market.py'nin dört `format` değeri -> core.bicim fonksiyonu.
_PIYASA_BICIM = {
    "score": lambda v: f"{B.sayi(v, 1)}/9",
    "ratio": lambda v: B.oran(v, 2),
    "points": lambda v: B.puan(v, 1),
    "share": lambda v: B.yuzde(v, 1, False),
}


def _piyasa(paket: dict) -> list[str]:
    """Evren bağlamı — "F-Skoru 7" ancak medyanın 5 olduğu bilinince yorumlanabilir.

    `market_snapshot()` ağsız: zaten yüklü bağlam sözlüğünden hesaplanıyor.
    Yalnızca başlık satırları + şirketin **kendi** sektör satırı basılıyor;
    30 sektörlük tam tablo ve "en çok yükselen 10" listesi tek şirketlik bir
    raporda yer kaplamaktan başka bir şey yapmaz.
    """
    piyasa = paket.get("piyasa") or {}
    if not piyasa.get("available"):
        return []
    out = ["## Piyasa bağlamı", ""]
    out.append(
        f"- Evren: {piyasa.get('market')} · {piyasa.get('scanned')} şirket tarandı"
        + (f" ({piyasa.get('error_count')} hata)" if piyasa.get("error_count") else "")
    )
    yas = paket.get("baglam_yasi_saat")
    if yas is not None:
        out.append(f"- Tarama yaşı: {B.sayi(yas, 0)} saat")

    for satir in piyasa.get("headline") or []:
        if satir.get("value") is None:
            continue
        bicim = _PIYASA_BICIM.get(satir.get("format"), lambda v: B.sayi(v, 2))
        out.append(
            f"- {satir.get('label')}: {bicim(satir['value'])} (n={satir.get('n', 0)})"
            + (" · finans hariç" if satir.get("excludes_financials") else "")
        )

    kendi_sektor = (paket.get("profil") or {}).get("sektor")
    for sektor in piyasa.get("sectors") or []:
        if sektor.get("sector") != kendi_sektor:
            continue
        out.append("")
        out.append(f"Şirketin sektörü ({kendi_sektor}, {sektor.get('count')} şirket) medyanları:")
        for anahtar, m in (sektor.get("metrics") or {}).items():
            if m.get("median") is None:
                continue
            out.append(
                f"- {m.get('label') or anahtar}: {_metrik_deger(anahtar, m['median'])} "
                f"(n={m.get('n', 0)})"
            )
        break

    if piyasa.get("note"):
        out.append("")
        out.append(f"- {piyasa['note']}")
    out.append("")
    return out


def _fiyat(paket: dict) -> list[str]:
    """Geçmiş fiyat istatistiği.

    Sınır cümlesi bilerek **iki kez** yazılıyor (başta ve sonda): bu, raporun
    yön/tahmin çağrıştırmaya en yakın bölümü ve okuyan model kapsamı
    kaçırmamalı.
    """
    f = paket.get("fiyat") or {}
    if not f.get("available"):
        return []
    para_birimi = f.get("currency") or ""
    out = ["## Fiyat serisi", ""]
    out.append(
        "Bu bölüm yalnızca geçmiş fiyat hareketinin istatistiğidir; fiyat yönü "
        "veya gelecek getiri hakkında bilgi taşımaz."
    )
    out.append("")
    out.append(f"- Pencere: {f.get('start')} – {f.get('end')} ({f.get('days')} işlem günü)")
    out.append(f"- Son kapanış: {B.sayi(f.get('last'), 2)} {para_birimi}".rstrip())
    out.append(
        f"- 52 haftalık aralık: {B.sayi(f.get('low'), 2)} – "
        f"{B.sayi(f.get('high'), 2)} {para_birimi}".rstrip()
    )
    if f.get("position") is not None:
        out.append(
            f"- Son kapanış, bu aralığın alt ucundan "
            f"{B.puan(f['position'] * 100, 0)} yukarıda"
        )
    if f.get("change") is not None:
        satir = f"- Dönem içi değişim: nominal {B.yuzde(f['change'])}"
        if f.get("real_change") is not None:
            satir += (f"; dönem enflasyonu {B.yuzde(f.get('cpi_growth'), 1, False)} "
                      f"olduğu için reel {B.yuzde(f['real_change'])}")
        out.append(satir)
    if f.get("annual_volatility") is not None:
        out.append(
            f"- Yıllıklandırılmış volatilite: {B.yuzde(f['annual_volatility'], 1, False)} "
            "(günlük getirilerin standart sapması × √252)"
        )
    if f.get("max_drawdown") is not None:
        out.append(f"- Zirveden en derin geri çekilme: {B.yuzde(f['max_drawdown'])}")
    out.append("")
    out.append(
        "Yukarıdaki istatistikler geçmişi tanımlar; gelecekteki fiyat hakkında "
        "çıkarım yapmak için kullanılamaz."
    )
    out.append("")
    return out


def _veri_kalitesi(paket: dict) -> list[str]:
    out = ["## Veri kalitesi notları", ""]
    dq = paket.get("data_quality") or {}
    eksik = dq.get("missing_items") or []
    if eksik:
        out.append(f"- Yahoo'dan gelmeyen kalemler: {', '.join(eksik)}")
    if dq.get("currency_verified") is False:
        out.append("- Mali tabloların para birimi kesin doğrulanamadı.")
    if dq.get("cpi_available") is False:
        out.append("- Bu para birimi için TÜFE serisi yok; reel rakamlar hesaplanamadı.")
    if dq.get("tms29_boundary_crossed"):
        out.append(
            "- Karşılaştırma 2023 enflasyon muhasebesi (TMS-29) sınırını aşıyor; "
            "iki farklı muhasebe rejimi yan yana."
        )
    if not paket.get("baglam_var"):
        out.append("- Bu piyasa için sektör taraması yapılmamış; sektör bağlamı yok.")
    if len(out) == 2:
        out.append("- Bilinen bir veri kalitesi sorunu yok.")
    out.append("")
    return out


def _yontem_notlari(paket: dict) -> list[str]:
    return [
        "## Yöntem notları",
        "",
        "- Ondalık ayracı virgül, binlik ayracı nokta (Türkçe biçim); bu raporda da aynı kural geçerlidir.",
        "- \"Reel\" = enflasyondan arındırılmış. Kullanılan TÜFE, şirketin mali tablo para "
        "birimine göre seçilir (TL→TCMB EVDS, USD→ABD BLS, diğerleri→Dünya Bankası yıllık "
        "ortalaması); borsaya göre değil.",
        "- Çeyreklik veride ardışıklık bozuksa hesap yıllık tabana düşer; bu durum ilgili "
        "bölümde ayrıca belirtilir.",
        "- Kaynak Yahoo Finance'tir ve doğrulanmamıştır; kesin rakamlar için şirketin resmi "
        "(KAP/SEC) bildirimleriyle karşılaştırılmalıdır.",
        "- Bu rapor yalnızca geçmiş mali tabloların ne söylediğini özetler; fiyat tahmini "
        "veya yatırım kararı içermez.",
        "",
    ]


# Bölüm kaydı — `bicimlendir()` bu sırayla basar, `?bolum=` bu anahtarları alır.
# Fonksiyonlar yukarıda tanımlı olduğu için atama dosya sonunda.
BOLUMLER = (
    ("ozet", _ozet_blok),
    ("kimlik", _kimlik),
    ("tazelik", _tazelik),
    ("anlati", _ozet),
    ("capraz", _capraz_inceleme),
    ("bayraklar", _bayraklar),
    ("metrikler", _metrikler),
    ("fskor", _fskoru),
    ("altman", _altman),
    ("degerleme", _degerleme),
    ("karlilik", _karlilik),
    ("borc", _borc),
    ("kar_kalitesi", _kar_kalitesi),
    ("reel", _reel_buyume),
    ("kalite", _kalite),
    ("ceyrek", _ceyrek),
    ("yillik", _yillik),
    ("fiyat", _fiyat),
    ("piyasa", _piyasa),
    ("veri_kalitesi", _veri_kalitesi),
    ("yontem", _yontem_notlari),
)

BOLUM_ADLARI = tuple(anahtar for anahtar, _ in BOLUMLER)
