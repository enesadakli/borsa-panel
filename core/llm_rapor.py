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
from . import narrative as N
from . import reports as R
from . import universe as U
from .sozluk import UYARI


def olustur(client, symbol: str) -> str:
    """`uc_sirket` ile aynı boru hattı + `quality_timeline`; tek Markdown metni."""
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
    }
    return bicimlendir(paket)


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


def bicimlendir(paket: dict) -> str:
    """Saf Markdown üretici — ağ çağrısı yapmaz, yalnızca `paket`i okur."""
    p = paket.get("profil") or {}
    satirlar: list[str] = []

    satirlar.append(f"# {paket.get('symbol', '?')} — {p.get('ad') or ''}".rstrip())
    satirlar.append("")

    satirlar.extend(_ozet_blok(paket, p))
    satirlar.extend(_kimlik(paket, p))
    satirlar.extend(_tazelik(paket))
    satirlar.extend(_ozet(paket))
    satirlar.extend(_bayraklar(paket))
    satirlar.extend(_metrikler(paket))
    satirlar.extend(_fskoru(paket))
    satirlar.extend(_altman(paket))
    satirlar.extend(_degerleme(paket))
    satirlar.extend(_karlilik(paket))
    satirlar.extend(_borc(paket))
    satirlar.extend(_kar_kalitesi(paket))
    satirlar.extend(_reel_buyume(paket))
    satirlar.extend(_kalite(paket))
    satirlar.extend(_ceyrek(paket))
    satirlar.extend(_veri_kalitesi(paket))
    satirlar.extend(_yontem_notlari(paket))

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
    out.append(f"- Skor: {son['score']}/9 ({son.get('date') or '—'}) — {son.get('label') or ''}".rstrip())
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
                            ("Özsermaye durumu", "equity_negative")):
        satir = _metrik_node(etiket, b.get(anahtar))
        if satir:
            out.append(satir)

    gecmis = b.get("history") or []
    if gecmis:
        out.extend(_tarihce(
            ["Dönem", "Net borç", "FAVÖK", "Net borç/FAVÖK"],
            [[r.get("date") or "—", B.para(r.get("net_debt")), B.para(r.get("ebitda")),
              B.oran(r["net_debt_ebitda"], 2) if r.get("net_debt_ebitda") is not None else "—"]
             for r in gecmis],
        ))
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
                            ("Tahakkuk oranı (Sloan)", "accrual_ratio")):
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
    rapor = paket.get("rapor") or {}
    c = rapor.get("quarterly") or {}
    if not c.get("available"):
        return []
    out = ["## Son çeyrek", ""]
    out.append(f"- Dönem: {c.get('current_date') or '—'}" + (
        f" (karşılaştırma: {c['compare_date']})" if c.get("compare_date") else ""
    ))
    out.append("")
    out.append("| Kalem | Tutar | Yıllık değişim |")
    out.append("|---|---|---|")
    for satir in (c.get("lines") or [])[:10]:
        yoy = (satir.get("yoy") or {})
        yoy_metin = B.yuzde(yoy.get("pct")) if yoy.get("pct") is not None else (yoy.get("note") or "—")
        tutar = f"{B.para(satir.get('value'))} {rapor.get('currency') or ''}".strip()
        out.append(f"| {satir['label']} | {tutar} | {yoy_metin} |")
    yorumlar = c.get("comments") or []
    if yorumlar:
        out.append("")
        for y in yorumlar[:5]:
            out.append(f"- {y['text']} [{y['rule_id']}]")
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
