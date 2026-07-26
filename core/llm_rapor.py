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
    baglam = C.all_metric_contexts(context, symbol) if context else []
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
        },
        "banka_muhasebesi": pack.get("bank_accounting", False),
        "freshness": analysis.get("freshness") or {},
        "ozet": ozet,
        "bayraklar": bayraklar,
        "fscore": analysis.get("fscore") or {},
        "baglam": baglam,
        "baglam_var": context is not None,
        "kalite": kalite,
        "rapor": reports,
        "data_quality": ozet.get("data_quality") or {},
    }
    return bicimlendir(paket)


def bicimlendir(paket: dict) -> str:
    """Saf Markdown üretici — ağ çağrısı yapmaz, yalnızca `paket`i okur."""
    p = paket.get("profil") or {}
    satirlar: list[str] = []

    satirlar.append(f"# {paket.get('symbol', '?')} — {p.get('ad') or ''}".rstrip())
    satirlar.append("")

    satirlar.extend(_kimlik(paket, p))
    satirlar.extend(_tazelik(paket))
    satirlar.extend(_ozet(paket))
    satirlar.extend(_bayraklar(paket))
    satirlar.extend(_fskoru(paket))
    satirlar.extend(_metrikler(paket))
    satirlar.extend(_kalite(paket))
    satirlar.extend(_ceyrek(paket))
    satirlar.extend(_veri_kalitesi(paket))
    satirlar.extend(_yontem_notlari(paket))

    satirlar.append(f"> {UYARI}")
    return "\n".join(satirlar) + "\n"


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
    baglam = paket.get("baglam") or []
    if not baglam:
        return []
    out = ["## Metrikler ve sektör bağlamı", ""]
    out.append("| Metrik | Değer | Kendi trendi | Sektör medyanı (n) | Sektör % | Evren % |")
    out.append("|---|---|---|---|---|---|")
    for item in baglam:
        metrik = item.get("metric")
        if item.get("not_applicable"):
            out.append(f"| {item.get('label') or metrik} | sektörde tanımsız | — | — | — | — |")
            continue
        if not item.get("available"):
            continue
        deger = _metrik_deger(metrik, item["value"])
        trend = (item.get("trend") or {}).get("direction") or "—"
        medyan = item.get("sector_median")
        medyan_metin = f"{_metrik_deger(metrik, medyan)} (n={item.get('sector_n', 0)})" if medyan is not None else (
            item.get("sector_note") or "—"
        )
        sp = item.get("sector_percentile")
        up = item.get("universe_percentile")
        out.append(
            f"| {item.get('label') or metrik} | {deger} | {trend} | {medyan_metin} | "
            f"{'—' if sp is None else round(sp)} | {'—' if up is None else round(up)} |"
        )
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
