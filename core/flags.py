"""Kırmızı / sarı bayraklar.

Her bayrak, önceden tanımlanmış bir eşiğin aşılıp aşılmadığını söyler. Renk
bir yargı değil, hangi kuralın tetiklendiğinin göstergesidir:

    KIRMIZI : tanımlı bir kuralın eşiği aşıldı
    SARI    : dikkat edilmesi gereken bir birleşim veya veri sorunu

Ekranda renkle birlikte **her zaman metin etiket** gösterilir; renk tek başına
anlam taşımaz (renk körlüğü ve yazıcı çıktısı için).

Bankalarda dört kural yapısal olarak uygulanamaz (R3, R6, Y1, Y2). Bunlar
sessizce düşmez; `applied=False` ve gerekçesiyle listede kalır — kuralın
çalıştırılmadığını görmek, çalıştırılıp geçtiğini sanmaktan iyidir.
"""

from __future__ import annotations

from . import bicim as B
from . import fundamentals as F
from . import health as H
from .fundamentals import BAYAT_AY

KIRMIZI = "kirmizi"
SARI = "sari"
BILGI = "bilgi"

EFSANE = (
    "Kırmızı = tanımlı bir kuralın eşiği aşıldı. Sarı = dikkat edilmesi gereken "
    "birleşim veya veri sorunu. Mavi = tüm şirketler için geçerli bağlam notu. "
    "Bunlar hisse hakkında bir yargı değil, rakamların tetiklediği kurallardır."
)

# --- eşikler (bayrak kalibrasyonunda bu sabitler gözden geçirilir)
FSKOR_DUSUS_ESIGI = 3          # R2: kaç puanlık düşüş çöküş sayılır
BORC_ARTIS_ESIGI = 1.0         # R3: net borç/FAVÖK'te mutlak artış
KISA_VADE_ARTIS_PUAN = 0.05    # R3: kısa vadeli borç payında +5 puan
CAPEX_KAT = 2.0                # Y2: capex/gelir oranı 3 yıl ortalamasının kaç katı
# Y3: PD/DD eşiği. İlk taslakta 15'ti ama kalibrasyonda Apple'ı (PD/DD 45,9)
# "mantık dışı" diye işaretledi — oysa geri alımlar özsermayeyi eritince bu
# değer gerçek. Oranı artık kendimiz hesapladığımız için para birimi kaynaklı
# şişme de kalmadı; eşik yalnızca açık veri hatasını yakalayacak seviyede.
PD_DD_SUPHE = 100.0
EKSIK_KRITER_ESIGI = 2         # Y4: kaç kriter hesaplanamazsa uyarı

# Y3: bu büyümenin üstü ya veri hatasıdır ya da şirket o kadar değişmiştir ki
# geçen yılla karşılaştırma anlam taşımaz. Kalibrasyonda BIST'te %16.016 ve
# %7.212 reel büyüme gösteren şirketler çıktı ve tarayıcı listesinin başına
# oturuyorlardı. %300'de evrenin %8'i, %500'de %5'i tetikleniyor; net
# artefaktları yakalayıp gerçekten hızlı büyüyen küçük şirketleri boğmamak için
# %500 seçildi.
BUYUME_SUPHE = 5.0

# R4: reel daralma eşiği. İlk sürümde "iki dönem üst üste herhangi bir reel
# küçülme" idi ve kalibrasyonda BIST'in %64,5'inde tetikliyordu — yüksek
# enflasyonda reel küçülme kural değil norm olduğu için bu bir uyarı değil
# durum tespitiydi. Ölçülen alternatifler: eşik %-10 → %51,5, %-15 → %44,5,
# %-20 → %34,6. İki yıl üst üste %20 reel küçülme, reel gelirin yaklaşık üçte
# birini kaybetmek demek; ayırt edici ve açıklanabilir.
REEL_DARALMA_ESIGI = -0.20
TMS29_SINIR = "2023-01-01"     # Y6: enflasyon muhasebesine geçiş


def evaluate_flags(client, symbol: str, analysis: dict | None = None,
                   pack: dict | None = None, context: dict | None = None) -> dict:
    """Tüm bayrak kurallarını çalıştırır.

    `context` verilirse bazı bayraklar açıklamasına **taban oranı** ekler:
    "bu durum taranan 616 şirketin %57'sinde görülüyor". Kalibrasyon,
    R4'ün BIST'in yarısından fazlasında tetiklendiğini gösterdi — yüksek
    enflasyonda bu beklenen bir olgu, ama taban oranı yazılmadan okuyan kişi
    bunu şirkete özgü bir alarm sanır.
    """
    if pack is None:
        pack = F.load(client, symbol)
    if analysis is None:
        analysis = H.analyze(client, symbol, pack)

    bank = pack.get("bank_accounting", False)
    equity_negative = bool(
        (analysis["debt"].get("equity_negative") or {}).get("value")
    )

    rules = [
        _r1_kar_nakde_donmuyor(pack, bank),
        _r2_fskor_cokusu(analysis),
        _r3_borc_sikismasi(pack, bank, equity_negative),
        _r4_reel_daralma(analysis, context),
        _r5_negatif_ozsermaye(analysis, pack),
        _r6_faiz_karsilama(analysis, bank),
        _y1_marj_ve_borc(analysis, pack, bank, equity_negative),
        _y2_tek_seferlik_nakit(pack, bank),
        _y3_supheli_oran(analysis, pack),
        _y4_veri_eksik(analysis),
        _y5_para_birimi(pack),
        _y6_tms29(pack),
        _y7_veri_bayat(analysis, context),
    ]

    triggered = [rule for rule in rules if rule.get("triggered")]
    skipped = [rule for rule in rules if not rule.get("applied", True)]

    # Bilgi seviyesi bayrak listesinden ayrılır. Kalibrasyonda Y6 şirketlerin
    # %89'unda tetikleniyordu: herkeste olan bir uyarı ayırt edici değil, ortak
    # bir bağlam notudur. Uyarı listesini sulandırmasın diye ayrı duruyor.
    uyarilar = [rule for rule in triggered if rule["level"] in (KIRMIZI, SARI)]
    notlar = [rule for rule in triggered if rule["level"] == BILGI]

    return {
        "symbol": symbol,
        "legend": EFSANE,
        "flags": uyarilar,
        "notes": notlar,
        "not_applied": skipped,
        "evaluated": [rule["id"] for rule in rules],
        "red_count": sum(1 for rule in uyarilar if rule["level"] == KIRMIZI),
        "yellow_count": sum(1 for rule in uyarilar if rule["level"] == SARI),
    }


def _flag(id_, level, title, triggered, explanation, sources=None,
          applied=True, approximate=False, skip_reason=None) -> dict:
    return {
        "id": id_,
        "level": level,
        "title": title,
        "triggered": bool(triggered) and applied,
        "applied": applied,
        "approximate": approximate,
        "explanation": explanation,
        "skip_reason": skip_reason,
        "sources": sources or [],
    }


def _src(item, period, value=None) -> dict:
    return {"item": item, "period": period, "value": value}


# ==================================================================== KIRMIZI


def _r1_kar_nakde_donmuyor(pack: dict, bank: bool) -> dict:
    title = "Kâr nakde dönmüyor"
    if bank:
        return _flag("R1_KAR_NAKDE_DONMUYOR", KIRMIZI, title, False, None,
                     applied=False,
                     skip_reason="Banka nakit akışı bilanço hareketiyle belirlenir")

    rows = F.rows(pack, "annual")[-2:]
    if len(rows) < 2:
        return _flag("R1_KAR_NAKDE_DONMUYOR", KIRMIZI, title, False, None,
                     applied=False, skip_reason="İki tam yıl verisi yok")

    hits = []
    for row in rows:
        ni = row["values"].get("NetIncome")
        fcf = row["values"].get("FreeCashFlow")
        if ni is None or fcf is None:
            return _flag("R1_KAR_NAKDE_DONMUYOR", KIRMIZI, title, False, None,
                         applied=False, skip_reason="Net kâr veya serbest nakit akışı yok")
        if ni > 0 and fcf < 0:
            hits.append((row["date"], ni, fcf))

    triggered = len(hits) == 2
    explanation = None
    sources = []
    if triggered:
        explanation = (
            f"Son iki yılda da net kâr pozitif, serbest nakit akışı negatif "
            f"({hits[0][0][:4]} ve {hits[1][0][:4]}). Kâr kâğıt üstünde oluşuyor "
            "ama kasaya para girmiyor."
        )
        sources = [_src("NetIncome", d, ni) for d, ni, _ in hits] + \
                  [_src("FreeCashFlow", d, fcf) for d, _, fcf in hits]
    return _flag("R1_KAR_NAKDE_DONMUYOR", KIRMIZI, title, triggered, explanation, sources)


def _r2_fskor_cokusu(analysis: dict) -> dict:
    title = "F-Skoru çöküşü"
    fscore = analysis["fscore"]
    if not fscore["model_applicable"]:
        return _flag("R2_FSKOR_COKUSU", KIRMIZI, title, False, None, applied=False,
                     skip_reason="F-Skoru modeli finans şirketlerinde kıyaslanmaz")

    points = fscore["usable_points"]
    if len(points) < 2:
        return _flag("R2_FSKOR_COKUSU", KIRMIZI, title, False, None, applied=False,
                     skip_reason="Karşılaştırılabilir iki skor noktası yok")

    first, last = points[0], points[-1]
    drop = first["score"] - last["score"]
    triggered = drop >= FSKOR_DUSUS_ESIGI
    explanation = None
    if triggered:
        broken = [
            criterion["label"]
            for criterion in last["criteria"]
            if criterion["status"] == H.OK and not criterion["passed"]
        ]
        explanation = (
            f"F-Skoru {first['date'][:4]} → {last['date'][:4]} arasında "
            f"{first['score']}/9'dan {last['score']}/9'a indi ({drop} puan). "
            f"Şu an kalan kriterler: {', '.join(broken) if broken else '—'}."
        )
    return _flag("R2_FSKOR_COKUSU", KIRMIZI, title, triggered, explanation,
                 [_src("F-Skoru", last["date"], last["score"]),
                  _src("F-Skoru", first["date"], first["score"])])


def _r3_borc_sikismasi(pack: dict, bank: bool, equity_negative: bool) -> dict:
    title = "Borç sıkışması"
    if bank:
        return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                     skip_reason="Bankalarda FAVÖK ve net borç kavramı tanımlı değil")
    if equity_negative:
        return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                     skip_reason="Özsermaye negatif — oran bazlı borç kuralları bastırıldı")

    rows = F.rows(pack, "annual")[-2:]
    if len(rows) < 2:
        return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                     skip_reason="İki tam yıl verisi yok")

    ratios, shares, approximate = [], [], False
    for row in rows:
        values = row["values"]
        net_debt = values.get("NetDebt")
        ebitda = values.get("EBITDA")
        if net_debt is None or not ebitda or ebitda <= 0:
            return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                         skip_reason="Net borç veya pozitif FAVÖK yok")
        if not H.net_debt_ebitda_guvenilir(net_debt, ebitda):
            # ISSEN.IS vakası: FAVÖK bir dönem neredeyse sıfıra çökünce oran
            # 2.734'e fırlıyordu — gerçek bir borç sıkışması değil, paydanın
            # çökmesi. Aynı eşik health.py'de tanımlı, tek yerden yönetiliyor.
            return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                         skip_reason=(
                             f"FAVÖK {row['date']} döneminde şirketin ölçeğine göre "
                             "neredeyse sıfır; net borç/FAVÖK oranı bu dönemde anlamlı değil"
                         ))
        ratios.append(net_debt / ebitda)

        total_debt = values.get("TotalDebt")
        current_debt = values.get("CurrentDebt")
        if current_debt is None:
            # CurrentDebt gelmediğinde kısa vadeli yükümlülükle yaklaşık hesap.
            current_debt = values.get("CurrentLiabilities")
            approximate = True
        if current_debt is None or not total_debt:
            return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, False, None, applied=False,
                         skip_reason="Kısa vadeli borç payı hesaplanamıyor")
        shares.append(current_debt / total_debt)

    ratio_jump = ratios[1] - ratios[0]
    share_jump = shares[1] - shares[0]
    triggered = ratio_jump >= BORC_ARTIS_ESIGI and share_jump >= KISA_VADE_ARTIS_PUAN

    explanation = None
    if triggered:
        explanation = (
            f"Net borç/FAVÖK {B.oran(ratios[0])}'den {B.oran(ratios[1])}'e çıktı "
            f"({B.sayi(ratio_jump, 2, isaretli=True)}) ve aynı dönemde kısa vadeli "
            f"borcun payı {B.yuzde(shares[0], 0, False)}'den "
            f"{B.yuzde(shares[1], 0, False)}'e yükseldi. "
            "Borç hem büyümüş hem de vadesi kısalmış."
        )
    return _flag("R3_BORC_SIKISMASI", KIRMIZI, title, triggered, explanation,
                 [_src("NetDebt", rows[1]["date"], rows[1]["values"].get("NetDebt")),
                  _src("EBITDA", rows[1]["date"], rows[1]["values"].get("EBITDA")),
                  _src("CurrentDebt", rows[1]["date"], rows[1]["values"].get("CurrentDebt"))],
                 approximate=approximate)


def _r4_reel_daralma(analysis: dict, context: dict | None = None) -> dict:
    title = "Sürekli ve belirgin reel daralma"
    history = (analysis["real_growth"].get("revenue") or {}).get("history") or []
    usable = [step for step in history if step.get("real") is not None]
    if len(usable) < 2:
        return _flag("R4_REEL_DARALMA", KIRMIZI, title, False, None, applied=False,
                     skip_reason="İki dönemlik reel büyüme hesaplanamadı (TÜFE verisi yetersiz)")

    last_two = usable[-2:]
    triggered = all(step["real"] < REEL_DARALMA_ESIGI for step in last_two)
    explanation = None
    if triggered:
        birlesik = 1.0
        for step in last_two:
            birlesik *= 1.0 + step["real"]
        explanation = (
            "Gelir üst üste iki dönem reel olarak "
            f"{B.yuzde(abs(REEL_DARALMA_ESIGI), 0, False)}'den fazla küçüldü: "
            + ", ".join(
                f"{step['date'][:4]} {B.yuzde(step['real'])}" for step in last_two
            )
            + f". İki dönemin bileşik etkisi {B.yuzde(birlesik - 1)}: nominal "
            "rakam artmış olsa bile enflasyon sonrası hacim belirgin şekilde geriliyor."
        )
        taban = _base_rate(context, _r4_kosulu)
        if taban:
            explanation += (
                f" Karşılaştırma için: bu durum reel büyümesi ölçülebilen "
                f"{taban['n']} şirketin {B.yuzde(taban['share'], 0, False)} kadarında "
                "görülüyor — yüksek enflasyon döneminde yaygın bir tablo."
            )
    return _flag("R4_REEL_DARALMA", KIRMIZI, title, triggered, explanation,
                 [_src("Reel gelir büyümesi", step["date"], step["real"]) for step in last_two])


def _r4_kosulu(row: dict) -> bool | None:
    """Bağlam kaydından R4 taban oranı koşulu.

    Bağlam kaydında dönem dönem reel büyüme tutulmuyor, yalnızca ardışık negatif
    dönem sayısı ve son dönemin reel büyümesi var. Taban oranı bu yüzden
    "üst üste en az iki dönem reel küçülme **ve** son dönem eşiğin altında"
    şeklinde yaklaşık hesaplanır; bayrağın kendisi tam kuralı uygular.
    """
    screen = row.get("screen") or {}
    streak = screen.get("real_revenue_negative_streak")
    son = (row.get("metrics") or {}).get("real_revenue_growth")
    if streak is None or son is None:
        return None
    return streak >= 2 and son < REEL_DARALMA_ESIGI


def _y7_veri_bayat(analysis: dict, context: dict | None = None) -> dict:
    """Son rapor eskimiş — metriklerin hepsi o kadar eski demektir.

    NETCD vakası: Temmuz 2026'da bakıldığında en son tablo 2024-12'ydi. F-Skoru
    9/9 çıkıyordu ve rakam doğruydu; ama 19 aylık bir tablodan geliyordu ve
    ekranda hiçbir yerde bu yazmıyordu. Kullanıcı "bu şirket şu an 9/9" diye
    okuyordu. Bayrağın işi rakamı çürütmek değil, **hangi tarihe ait olduğunu**
    görünür kılmak.
    """
    title = "Son rapor eski"
    tazelik = analysis.get("freshness") or {}
    seviye = tazelik.get("level")

    if not seviye or seviye == "bilinmiyor":
        return _flag("Y7_VERI_BAYAT", SARI, title, False, None, applied=False,
                     skip_reason="Dönem tarihi okunamadı, yaş hesaplanamadı")

    triggered = seviye in ("bayat", "cok_bayat")
    explanation = None
    if triggered:
        parcalar = [
            f"En son mali tablo dönemi {tazelik.get('latest_period')} — "
            f"{tazelik.get('label')}. Bu ekrandaki bütün metrikler o tarihe ait; "
            "aradaki dönemde şirkette olanları göstermiyor."
        ]
        if tazelik.get("annual_stale") and tazelik.get("last_annual"):
            parcalar.append(
                f"F-Skoru ve yıllık karşılaştırmalar {tazelik['last_annual']} "
                "tablosundan geliyor."
            )
        if seviye == "cok_bayat":
            parcalar.append(
                "Bir yıllık raporlama dönemi kaçırılmış görünüyor; kaynakta veri "
                "eksik olabileceği gibi şirket bildirimini geciktirmiş de olabilir."
            )
        taban = _base_rate(context, _y7_kosulu)
        if taban:
            parcalar.append(
                f"Karşılaştırma için: taranan {taban['n']} şirketin "
                f"{B.puan(taban['share'] * 100, 0)} kadarında son rapor "
                f"{BAYAT_AY} aydan eski."
            )
        explanation = " ".join(parcalar)

    return _flag("Y7_VERI_BAYAT", SARI, title, triggered, explanation,
                 [_src("Son dönem", tazelik.get("latest_period"), tazelik.get("age_months"))])


def _y7_kosulu(row: dict) -> bool | None:
    """Bağlam kaydından Y7 taban oranı koşulu."""
    yas = (row.get("screen") or {}).get("data_age_months")
    return None if yas is None else yas >= BAYAT_AY


def _base_rate(context: dict | None, predicate) -> dict | None:
    """Bir koşulun evrendeki görülme oranı. Bağlam yoksa None."""
    if not context or not context.get("symbols"):
        return None
    evet = hayir = 0
    for row in context["symbols"].values():
        sonuc = predicate(row)
        if sonuc is None:
            continue
        if sonuc:
            evet += 1
        else:
            hayir += 1
    toplam = evet + hayir
    if toplam < 30:  # küçük örneklemde taban oranı yazmak yanıltıcı olur
        return None
    return {"share": evet / toplam, "n": toplam, "count": evet}


def _r5_negatif_ozsermaye(analysis: dict, pack: dict) -> dict:
    title = "Negatif özsermaye"
    node = analysis["debt"].get("equity_negative") or {}
    if node.get("status") != H.OK:
        return _flag("R5_NEGATIF_OZSERMAYE", KIRMIZI, title, False, None, applied=False,
                     skip_reason="Özsermaye verisi yok")
    triggered = bool(node.get("value"))
    equity = F.stock_value(pack, "StockholdersEquity")
    explanation = None
    if triggered:
        # Sayı biçimlendirmesi yalnızca sayıya uygulanır: cümlenin tamamına
        # .replace(",", ".") çağırmak metindeki virgülleri de noktaya çeviriyordu.
        explanation = (
            f"Özsermaye {equity['end']} itibarıyla negatif "
            f"({F._tr_sayi(equity['value'])} {pack.get('currency')}). Bu durumda "
            "borç/özsermaye, PD/DD ve ROE gibi oranlar tanımsızdır; diğer oran "
            "bazlı kurallar bastırıldı."
        )
    return _flag("R5_NEGATIF_OZSERMAYE", KIRMIZI, title, triggered, explanation,
                 [_src("StockholdersEquity", equity["end"], equity["value"])])


def _r6_faiz_karsilama(analysis: dict, bank: bool) -> dict:
    title = "Faiz gideri kârdan büyük"
    if bank:
        return _flag("R6_FAIZ_KARSILAMA", KIRMIZI, title, False, None, applied=False,
                     skip_reason="Bankalarda faiz gideri faaliyetin kendisidir")
    node = analysis["debt"].get("interest_coverage") or {}
    if node.get("status") != H.OK or node.get("value") is None:
        return _flag("R6_FAIZ_KARSILAMA", KIRMIZI, title, False, None, applied=False,
                     skip_reason=node.get("detail") or "Faiz karşılama oranı hesaplanamadı")
    triggered = node["value"] < 1.0
    explanation = None
    if triggered:
        explanation = (
            f"Faaliyet kârı faiz giderinin yalnızca {B.kat(node['value'], 2)}; "
            "şirket borcunun faizini faaliyet kârıyla karşılayamıyor."
        )
    return _flag("R6_FAIZ_KARSILAMA", KIRMIZI, title, triggered, explanation,
                 node.get("sources"))


# ======================================================================= SARI


def _y1_marj_ve_borc(analysis: dict, pack: dict, bank: bool, equity_negative: bool) -> dict:
    title = "Marj daralması ve borç artışı birlikte"
    if bank:
        return _flag("Y1_MARJ_VE_BORC", SARI, title, False, None, applied=False,
                     skip_reason="Bankalarda faaliyet marjı bu şekilde tanımlı değil")
    if equity_negative:
        return _flag("Y1_MARJ_VE_BORC", SARI, title, False, None, applied=False,
                     skip_reason="Özsermaye negatif — borç/özsermaye karşılaştırması yapılmadı")

    margins = analysis["margins"]["series"].get("operating") or []
    if len(margins) < 3:
        return _flag("Y1_MARJ_VE_BORC", SARI, title, False, None, applied=False,
                     skip_reason="Faaliyet marjı için üç dönem gerekiyor")

    falling = margins[-1][1] < margins[-2][1] < margins[-3][1]

    rows = F.rows(pack, "annual")[-2:]
    debt_ratios = []
    for row in rows:
        debt = row["values"].get("TotalDebt")
        equity = row["values"].get("StockholdersEquity")
        if debt is None or not equity or equity <= 0:
            return _flag("Y1_MARJ_VE_BORC", SARI, title, False, None, applied=False,
                         skip_reason="Borç/özsermaye iki dönem için hesaplanamadı")
        debt_ratios.append(debt / equity)

    rising = debt_ratios[1] > debt_ratios[0]
    triggered = falling and rising
    explanation = None
    if triggered:
        explanation = (
            f"Faaliyet marjı üç dönemdir geriliyor ({B.puan(margins[-3][1])} → "
            f"{B.puan(margins[-1][1])}) ve aynı dönemde borç/özsermaye "
            f"{B.oran(debt_ratios[0])}'den {B.oran(debt_ratios[1])}'e çıktı."
        )
    return _flag("Y1_MARJ_VE_BORC", SARI, title, triggered, explanation,
                 [_src("Faaliyet marjı", margins[-1][0], margins[-1][1]),
                  _src("TotalDebt", rows[1]["date"], rows[1]["values"].get("TotalDebt"))])


def _y2_tek_seferlik_nakit(pack: dict, bank: bool) -> dict:
    title = "Olağandışı yatırım harcaması şüphesi"
    if bank:
        return _flag("Y2_TEK_SEFERLIK_NAKIT_CIKISI", SARI, title, False, None,
                     applied=False, skip_reason="Bankalarda yatırım harcaması bu ölçüyle okunmaz")

    rows = F.rows(pack, "annual")
    if len(rows) < 4:
        return _flag("Y2_TEK_SEFERLIK_NAKIT_CIKISI", SARI, title, False, None,
                     applied=False, skip_reason="Dört yıllık capex geçmişi yok")

    last = rows[-1]["values"]
    cfo = last.get("OperatingCashFlow")
    fcf = last.get("FreeCashFlow")
    capex = last.get("CapitalExpenditure")
    revenue = last.get("TotalRevenue")
    if cfo is None or fcf is None or capex is None or not revenue:
        return _flag("Y2_TEK_SEFERLIK_NAKIT_CIKISI", SARI, title, False, None,
                     applied=False, skip_reason="Nakit akışı veya capex verisi eksik")

    ratios = []
    for row in rows[-4:-1]:
        prior_capex = row["values"].get("CapitalExpenditure")
        prior_revenue = row["values"].get("TotalRevenue")
        if prior_capex is None or not prior_revenue:
            continue
        ratios.append(abs(prior_capex) / prior_revenue)
    if not ratios:
        return _flag("Y2_TEK_SEFERLIK_NAKIT_CIKISI", SARI, title, False, None,
                     applied=False, skip_reason="Geçmiş capex oranı hesaplanamadı")

    average = sum(ratios) / len(ratios)
    current = abs(capex) / revenue
    triggered = cfo > 0 > fcf and average > 0 and current > average * CAPEX_KAT

    explanation = None
    if triggered:
        explanation = (
            f"Faaliyet nakit akışı pozitif ama serbest nakit akışı negatif; "
            f"yatırım harcaması geliri oranı {B.yuzde(current, 1, False)} ile önceki üç "
            f"yılın ortalamasının ({B.yuzde(average, 1, False)}) "
            f"{B.kat(current / average)}. "
            "Tek seferlik büyük bir yatırım olabilir."
        )
    return _flag("Y2_TEK_SEFERLIK_NAKIT_CIKISI", SARI, title, triggered, explanation,
                 [_src("CapitalExpenditure", rows[-1]["date"], capex),
                  _src("FreeCashFlow", rows[-1]["date"], fcf)])


def _y3_supheli_oran(analysis: dict, pack: dict) -> dict:
    title = "Mantık dışı oran"
    reasons, sources = [], []

    pb = (analysis["valuation"].get("pb") or {})
    if pb.get("status") == H.OK and pb.get("value") and pb["value"] > PD_DD_SUPHE:
        reasons.append(f"PD/DD = {B.sayi(pb['value'], 1)}")
        sources.extend(pb.get("sources") or [])

    for name, node in (("Brüt", analysis["margins"]["series"].get("gross")),
                       ("Faaliyet", analysis["margins"]["series"].get("operating")),
                       ("Net", analysis["margins"]["series"].get("net"))):
        if node and abs(node[-1][1]) > 100:
            reasons.append(f"{name} marj {B.puan(node[-1][1], 0)}")

    ebitda = F.flow_value(pack, "EBITDA")
    net_income = F.flow_value(pack, "NetIncome")
    if ebitda["value"] is not None and net_income["value"] is not None:
        if ebitda["value"] < 0 < net_income["value"]:
            reasons.append("FAVÖK negatifken net kâr pozitif")
            sources.append(_src("EBITDA", ebitda["end"], ebitda["value"]))

    if pack.get("market_cap_reliable") is False:
        reasons.append("piyasa değeri yanlış pay sınıfı üzerinden hesaplanmış")
        sources.append(_src("Piyasa değeri", None, pack.get("market_cap")))

    for anahtar, ad in (("revenue", "gelir"), ("net_income", "net kâr")):
        buyume = (analysis.get("real_growth") or {}).get(anahtar) or {}
        reel = buyume.get("real")
        if reel is not None and abs(reel) > BUYUME_SUPHE:
            reasons.append(f"reel {ad} büyümesi {B.yuzde(reel, 0)}")
            sources.extend(buyume.get("sources") or [])

    triggered = bool(reasons)
    explanation = None
    if triggered:
        explanation = (
            "Şu değer(ler) olağan aralığın dışında: " + "; ".join(reasons) +
            ". Genellikle veri kaynağındaki bir tutarsızlığa ya da şirketin "
            "yapısının tamamen değişmesine (bölünme, birleşme, faaliyete yeni "
            "başlama) işaret eder. Rakam karar için kullanılmadan önce KAP "
            "bildirimiyle doğrulanmalı."
        )
    return _flag("Y3_SUPHELI_ORAN", SARI, title, triggered, explanation, sources)


def _y4_veri_eksik(analysis: dict) -> dict:
    title = "F-Skoru kriterlerinde veri eksiği"
    latest = analysis["fscore"].get("latest")
    if not latest:
        return _flag("Y4_VERI_EKSIK", SARI, title, False, None, applied=False,
                     skip_reason="Kullanılabilir F-Skoru noktası yok")
    missing = latest.get("missing") or []
    triggered = len(missing) >= EKSIK_KRITER_ESIGI
    explanation = None
    if triggered:
        labels = [
            criterion["label"]
            for criterion in latest["criteria"]
            if criterion["status"] == H.EKSIK
        ]
        explanation = (
            f"{len(missing)} kriter veri gelmediği için değerlendirilemedi: "
            f"{', '.join(labels)}. Skor bu eksiklerle birlikte okunmalı; "
            "eksik kriterler sıfır sayılmadı."
        )
    return _flag("Y4_VERI_EKSIK", SARI, title, triggered, explanation,
                 [_src("F-Skoru", latest["date"], latest["label"])])


def _y5_para_birimi(pack: dict) -> dict:
    title = "Para birimi belirsiz"
    notes = pack.get("currency_notes") or []
    triggered = not pack.get("currency") or any(
        "gerçekten karışık" in note for note in notes
    )
    explanation = None
    if triggered:
        explanation = (
            "Mali tabloların para birimi güvenle belirlenemedi: "
            + " ".join(notes)
            + " Mutlak tutarlar yerine yalnızca yüzde değişimlere bakılmalı."
        )
    return _flag("Y5_PARA_BIRIMI_BELIRSIZ", SARI, title, triggered, explanation,
                 [_src("financialCurrency", None, pack.get("currency"))])


def _y6_tms29(pack: dict) -> dict:
    """Enflasyon muhasebesi sınırı — uyarı değil, bağlam notu.

    Kalibrasyonda BIST'in %89'unda tetiklendi. Bu bir şirket sorunu değil: TL
    raporlayan hemen her şirketin 4 yıllık tablosu 2023 sınırını geçiyor. Uyarı
    olarak göstermek 12 kuralın en gürültülüsünü listenin başına koymak olurdu,
    o yüzden BILGI seviyesinde ayrı bölümde duruyor.
    """
    title = "Enflasyon muhasebesi kırılması"
    if (pack.get("currency") or "").upper() != "TRY":
        return _flag("Y6_TMS29_KIRILMASI", BILGI, title, False, None, applied=False,
                     skip_reason="TMS-29 yalnızca TL raporlayan şirketleri ilgilendirir")

    dates = F.period_dates(pack, "annual")
    if not dates:
        return _flag("Y6_TMS29_KIRILMASI", BILGI, title, False, None, applied=False,
                     skip_reason="Yıllık dönem yok")

    before = [date for date in dates if date < TMS29_SINIR]
    after = [date for date in dates if date >= TMS29_SINIR]
    triggered = bool(before and after)
    explanation = None
    if triggered:
        explanation = (
            f"Tabloda hem enflasyon muhasebesi öncesi ({', '.join(d[:4] for d in before)}) "
            f"hem sonrası ({', '.join(d[:4] for d in after)}) dönemler var. "
            "TMS-29 sonrası tablolar sabit alım gücüyle düzenlendiği için bu sınırı "
            "aşan karşılaştırmalar birebir kıyaslanabilir değildir."
        )
    return _flag("Y6_TMS29_KIRILMASI", BILGI, title, triggered, explanation,
                 [_src("Dönem aralığı", f"{dates[0]}..{dates[-1]}")])
