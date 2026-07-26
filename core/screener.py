"""Kural tabanlı tarayıcı.

Kuralı kullanıcı kurar, araç evreni tarar. Filtre motoru **yapısaldır**:
`eval()` veya benzeri bir şey yok. Bir kural şu iki şeyden biridir:

    koşul : {"field": "fscore", "op": ">=", "value": 7}
    grup  : {"operator": "AND"|"OR", "operands": [koşul veya grup, ...]}

Sonuç satırlarında **her kriterin ayrı ayrı sonucu** görünür
(`4/4 · F-Skoru ✓8 · FCF ✓ · NB/FAVÖK ✓1,3`). Veri eksikse kriter `?` olarak
işaretlenir ve satır "kısmi" sayılır: eksik veriyi geçmiş gibi göstermek de,
kalmış gibi göstermek de yanlış olur.

Sıralamanın başında olmak "iyi yatırım" demek değildir — "seçtiğin finansal
kriterleri geçmiş" demektir. Hazır şablonlar bu yüzden "filtre örneği"
etiketiyle gelir.
"""

from __future__ import annotations

import json
import os

from . import bicim as B
from . import context as C
from . import health as H

# Yön alanlarının kabul ettiği değerler. Şablonlar ve kullanıcı kuralları bu
# kümeye karşı doğrulanır; aksi halde "düşüş" gibi başka bir modülün sözlüğünden
# gelen bir değer yazıldığında filtre sessizce hiçbir şeyi elemez.
YON_DEGERLERI: dict[str, tuple[str, ...]] = {
    "operating_margin_direction": H.MARJ_YONLERI,
    "gross_margin_direction": H.MARJ_YONLERI,
}

# Karşılaştırma operatörleri. Hepsi saf fonksiyon; kullanıcı girdisi asla
# koda dönüşmez.
OPERATORLER = {
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

VE, VEYA = "AND", "OR"

# Filtrelenebilir alanlar: anahtar -> (ekran adı, kaynak, biçim)
# kaynak "metric" ise context.metrics, "screen" ise context.screen,
# "trend" ise context.trends[...]["direction"], "meta" ise satırın kendisi.
ALANLAR: dict[str, dict] = {
    # --- finansal sağlık
    "fscore": {"label": "F-Skoru", "source": "metric", "format": "score"},
    "fscore_change": {"label": "F-Skoru değişimi (tüm dönem)", "source": "screen", "format": "delta"},
    "fscore_change_yoy": {"label": "F-Skoru değişimi (son yıl)", "source": "screen", "format": "delta"},
    "altman_z": {"label": "Altman Z", "source": "metric", "format": "ratio"},
    "roe": {"label": "ROE", "source": "metric", "format": "percent"},
    "roa": {"label": "ROA", "source": "metric", "format": "percent"},
    # --- kâr kalitesi
    "fcf_positive": {"label": "Serbest nakit akışı pozitif", "source": "screen", "format": "bool"},
    "fcf_ge_net_income": {"label": "FCF ≥ net kâr", "source": "screen", "format": "bool"},
    "fcf_gap": {"label": "Kâr–nakit sapması", "source": "metric", "format": "percent"},
    # --- borç
    "net_debt_ebitda": {"label": "Net borç/FAVÖK", "source": "metric", "format": "ratio"},
    "net_debt_ebitda_delta": {"label": "Net borç/FAVÖK değişimi", "source": "screen", "format": "delta"},
    "debt_to_equity": {"label": "Borç/özsermaye", "source": "metric", "format": "ratio"},
    "interest_coverage": {"label": "Faiz karşılama", "source": "metric", "format": "ratio"},
    # --- marj
    "gross_margin": {"label": "Brüt marj", "source": "metric", "format": "points"},
    "operating_margin": {"label": "Faaliyet marjı", "source": "metric", "format": "points"},
    "net_margin": {"label": "Net marj", "source": "metric", "format": "points"},
    "operating_margin_direction": {"label": "Faaliyet marjı trendi", "source": "screen", "format": "text"},
    "gross_margin_direction": {"label": "Brüt marj trendi", "source": "screen", "format": "text"},
    # --- büyüme
    "real_revenue_growth": {"label": "Reel gelir büyümesi", "source": "metric", "format": "percent"},
    "real_income_growth": {"label": "Reel net kâr büyümesi", "source": "metric", "format": "percent"},
    # --- değerleme
    "pe": {"label": "F/K", "source": "metric", "format": "ratio"},
    "pb": {"label": "PD/DD", "source": "metric", "format": "ratio"},
    "dividend_yield": {"label": "Temettü verimi", "source": "metric", "format": "percent"},
    # --- veri tazeliği
    # "9/9 aldı" ile "19 ay önce 9/9 almış" aynı şey değil; tarayıcıda eski
    # veriyi eleyebilmek gerekiyor.
    "data_age_months": {"label": "Veri yaşı (ay)", "source": "screen", "format": "ay"},
    "data_fresh": {"label": "Verisi güncel", "source": "screen", "format": "bool"},
    # --- meta
    "market_cap": {"label": "Piyasa değeri", "source": "meta", "format": "money"},
    "sector": {"label": "Sektör", "source": "meta", "format": "text"},
}

# Hazır şablonlar. Hepsi "filtre örneği" — tavsiye değil.
SABLONLAR: list[dict] = [
    {
        "id": "bilanco_kalitesi",
        "name": "Bilanço kalitesi yüksek",
        "note": "Filtre örneği — tavsiye değil.",
        "explanation": (
            "Piotroski F-Skoru 7 ve üzeri, serbest nakit akışı pozitif, net borç "
            "FAVÖK'ün iki katının altında olan şirketler."
        ),
        "rule": {
            "operator": VE,
            "operands": [
                {"field": "fscore", "op": ">=", "value": 7},
                {"field": "fcf_positive", "op": "==", "value": True},
                {"field": "net_debt_ebitda", "op": "<", "value": 2.0},
            ],
        },
    },
    {
        "id": "reel_buyuyen",
        "name": "Reel büyüyen + marjını koruyan",
        "note": "Filtre örneği — tavsiye değil.",
        "explanation": (
            "Geliri enflasyon sonrası artan ve faaliyet marjı trendi düşüş "
            "olmayan şirketler."
        ),
        "rule": {
            "operator": VE,
            "operands": [
                {"field": "real_revenue_growth", "op": ">", "value": 0.0},
                {"field": "operating_margin_direction", "op": "!=", "value": H.MARJ_DARALMA},
            ],
        },
    },
    {
        "id": "borc_artmayan",
        "name": "Borç yükü artmayan + kâr kalitesi iyi",
        "note": "Filtre örneği — tavsiye değil.",
        "explanation": (
            "Net borç/FAVÖK oranı dönem başına göre artmamış ve serbest nakit "
            "akışı net kâra en az eşit olan şirketler."
        ),
        "rule": {
            "operator": VE,
            "operands": [
                {"field": "net_debt_ebitda_delta", "op": "<=", "value": 0.0},
                {"field": "fcf_ge_net_income", "op": "==", "value": True},
            ],
        },
    },
    {
        "id": "kalite_yukselen",
        "name": "Kalite skoru yükselen",
        "note": "Filtre örneği — tavsiye değil.",
        "explanation": (
            "F-Skoru elimizdeki en eski karşılaştırma noktasına göre en az 2 puan "
            "artmış şirketler."
        ),
        "rule": {
            "operator": VE,
            "operands": [{"field": "fscore_change", "op": ">=", "value": 2}],
        },
    },
]


class RuleError(ValueError):
    """Kural yapısı geçersiz."""


# ------------------------------------------------------------------ değer okuma


def field_value(row: dict, field: str):
    """Bağlam satırından alan değeri. Sektörde geçersizse ("NA") döner."""
    tanim = ALANLAR.get(field)
    if tanim is None:
        raise RuleError(f"bilinmeyen alan: {field}")

    if field in (row.get("not_applicable") or ()):
        return "NA"

    source = tanim["source"]
    if source == "metric":
        return (row.get("metrics") or {}).get(field)
    if source == "screen":
        return (row.get("screen") or {}).get(field)
    if source == "meta":
        return row.get(field)
    return None


# ---------------------------------------------------------------- kural işletme


def evaluate(row: dict, rule: dict) -> dict:
    """Kuralı tek şirkete uygular.

    Dönüş:
        result  : True / False / None — üç değerli sonuç. None "kararsız",
                  yani eksik veri yüzünden karar verilemedi demektir.
        passed  : yalnızca `result is True` ise doğru.
        partial : en az bir kriter değerlendirilemedi (sonucu değiştirmemiş
                  olabilir; VEYA grubunda bir koşul kesin geçtiyse kural yine
                  sağlanmış sayılır).

    `result`'ı boolean'a çevirmemek önemli: `bool(None)` False verir ve
    "kararsız" ile "kesin geçmedi" aynı kovaya düşer. O zaman eksik verili
    şirketler kısmi listeye hiç giremez, sessizce elenirler.
    """
    checks: list[dict] = []
    result = _walk(row, rule, checks)

    # Kararsızlığın iki farklı sebebi var ve kullanıcının yapabileceği şey
    # farklı: veri eksikse beklemek/başka kaynağa bakmak anlamlı, sektörde
    # tanımsızsa yapılacak bir şey yok — o kural o şirkete hiç uygulanamaz.
    # İkisini "kısmi" diye tek kovaya atmak, bankaları her F-Skoru filtresinde
    # "geçmiş olabilir" diye listelemeye yol açıyordu.
    eksik = [c for c in checks if c["reason"] == "veri yok"]
    sektor = [c for c in checks if c["reason"] == "bu sektörde tanımsız"]

    return {
        "result": result,
        "passed": result is True,
        "partial": bool(eksik),
        "sector_blocked": bool(sektor),
        "checks": checks,
        "score": sum(1 for check in checks if check["result"] is True),
        "total": len(checks),
        "undecided": sum(1 for check in checks if check["result"] is None),
        "missing_fields": [c["field"] for c in eksik],
        "not_applicable_fields": [c["field"] for c in sektor],
    }


def _walk(row: dict, node: dict, checks: list[dict]):
    if "operator" in node:
        operator = node["operator"]
        operands = node.get("operands") or []
        if operator not in (VE, VEYA):
            raise RuleError(f"bilinmeyen bağlaç: {operator}")
        if not operands:
            raise RuleError("boş grup")

        sonuclar = [_walk(row, operand, checks) for operand in operands]
        if operator == VE:
            if any(sonuc is False for sonuc in sonuclar):
                return False
            return None if any(sonuc is None for sonuc in sonuclar) else True
        if any(sonuc is True for sonuc in sonuclar):
            return True
        return None if any(sonuc is None for sonuc in sonuclar) else False

    return _check(row, node, checks)


def _check(row: dict, condition: dict, checks: list[dict]):
    field = condition.get("field")
    op = condition.get("op")
    expected = condition.get("value")

    if op not in OPERATORLER:
        raise RuleError(f"bilinmeyen operatör: {op}")
    tanim = ALANLAR.get(field)
    if tanim is None:
        raise RuleError(f"bilinmeyen alan: {field}")

    value = field_value(row, field)

    if value == "NA":
        result = None
        reason = "bu sektörde tanımsız"
    elif value is None:
        result = None
        reason = "veri yok"
    else:
        try:
            result = bool(OPERATORLER[op](value, expected))
        except TypeError:
            result = None
            reason = "tip uyuşmuyor"
        else:
            reason = None

    checks.append(
        {
            "field": field,
            "label": tanim["label"],
            "op": op,
            "expected": expected,
            "value": None if value == "NA" else value,
            "result": result,
            "reason": reason,
            "format": tanim["format"],
            "display": _bicimle(value, tanim["format"]),
        }
    )
    return result


def _bicimle(value, format_: str) -> str:
    """Sayısal biçimlendirmenin tamamı core.bicim'e devredilir.

    Eski hâlinde her dal kendi `.replace(".", ",")` çevirisini yapıyordu; bu
    hem tekrar hem de kayma riski taşıyordu — ör. "money" dalı 1 milyonun
    altındaki tutarlarda binlik ayracı hiç uygulamıyordu, oysa aynı sayı başka
    bir panelde `core.bicim.para` ile binlik noktalı görünüyordu.
    """
    if value == "NA":
        return "NA"
    if value is None:
        return "?"
    if format_ == "bool":
        return "var" if value else "yok"
    if format_ == "text":
        return str(value)
    if format_ == "percent":
        return B.yuzde(value, 1, True)
    if format_ == "points":
        return B.puan(value, 1)
    if format_ == "score":
        return f"{B.sayi(value, 0)}/9"
    if format_ == "ay":
        return f"{B.sayi(value, 0)} ay"
    if format_ == "delta":
        return B.sayi(value, 2, True)
    if format_ == "money":
        # Kısaltılmış (kompakt) biçim: bu dar bir tablo hücresi, cümle değil.
        # web/app.js'in kendi para() fonksiyonu da aynı T/Mr/Mn/B kısaltmalarını
        # kullanıyor — ikisi kasıtlı olarak aynı kompakt sözleşmeyi paylaşıyor.
        return B.para_kisa(value)
    return B.sayi(value, 2)


# --------------------------------------------------------------------- tarama


def screen(context: dict, rule: dict, include_partial: bool = True,
           sort_by: str | None = None, descending: bool = True,
           limit: int | None = None) -> dict:
    """Evreni kurala göre tarar.

    `include_partial` True ise eksik verili satırlar da döner ama `partial`
    işaretiyle ve ayrı sayılır — sessizce elenmeleri, filtreyi geçmediklerini
    sanmaya yol açardı.
    """
    symbols = context.get("symbols") or {}
    esleşen, kismi, uygulanamaz = [], [], []

    for symbol, row in symbols.items():
        sonuc = evaluate(row, rule)
        kayit = {
            "symbol": symbol,
            "name": row.get("name"),
            "sector": row.get("sector"),
            "currency": row.get("currency"),
            "market_cap": row.get("market_cap"),
            "bank_accounting": row.get("bank_accounting", False),
            **sonuc,
        }
        if sonuc["passed"]:
            esleşen.append(kayit)
        elif sonuc["result"] is None and sonuc["sector_blocked"]:
            # Kural bu şirkete yapısal olarak uygulanamıyor (banka/finans).
            # "Geçmiş olabilir" demek yanlış olur; hiç değerlendirilemez.
            uygulanamaz.append(kayit)
        elif sonuc["result"] is None:
            # Kararsız: eksik veri olmasa geçebilirdi. Sessizce elemek yerine
            # ayrı listede, hangi kriterin ölçülemediği görünür şekilde durur.
            kismi.append(kayit)

    anahtar = sort_by or "market_cap"

    def sirala(kayit: dict):
        if anahtar == "market_cap":
            return kayit.get("market_cap") or 0
        row = symbols.get(kayit["symbol"]) or {}
        value = field_value(row, anahtar) if anahtar in ALANLAR else None
        return value if isinstance(value, (int, float)) else float("-inf")

    esleşen.sort(key=sirala, reverse=descending)
    kismi.sort(key=sirala, reverse=descending)
    uygulanamaz.sort(key=sirala, reverse=descending)

    # Sayılar limitten **önce** alınır: arayüz "40 eşleşen" yazarken bu gerçek
    # sayı olmalı, gösterilen satır sayısı değil.
    eslesen_sayisi = len(esleşen)
    kismi_sayisi = len(kismi)
    uygulanamaz_sayisi = len(uygulanamaz)
    if limit:
        esleşen = esleşen[:limit]
        kismi = kismi[:limit]
        uygulanamaz = uygulanamaz[:limit]

    return {
        "market": context.get("market"),
        "scanned": len(symbols),
        "matched": esleşen,
        "matched_count": eslesen_sayisi,
        "truncated": bool(limit and eslesen_sayisi > len(esleşen)),
        "partial": kismi if include_partial else [],
        "partial_count": kismi_sayisi,
        "not_applicable": uygulanamaz,
        "not_applicable_count": uygulanamaz_sayisi,
        "note": (
            "Bu liste seçilen finansal kriterleri geçen şirketleri gösterir. "
            "Sıralamada üstte olmak gelecek getiri hakkında bilgi taşımaz."
        ),
    }


def run_template(context: dict, template_id: str, **kwargs) -> dict:
    """Hazır şablonu çalıştırır."""
    sablon = next((item for item in SABLONLAR if item["id"] == template_id), None)
    if sablon is None:
        raise RuleError(f"bilinmeyen şablon: {template_id}")
    sonuc = screen(context, sablon["rule"], **kwargs)
    sonuc["template"] = {
        "id": sablon["id"],
        "name": sablon["name"],
        "note": sablon["note"],
        "explanation": sablon["explanation"],
    }
    return sonuc


# ------------------------------------------------------------ kural kaydetme


def rules_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "rules.json")


def load_rules() -> list[dict]:
    """Kayıtlı kullanıcı kuralları + hazır şablonlar."""
    try:
        with open(rules_path(), "r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        saved = []
    if not isinstance(saved, list):
        saved = []
    return SABLONLAR + [item for item in saved if isinstance(item, dict)]


def save_rule(rule: dict) -> list[dict]:
    """Kullanıcı kuralını kaydeder (şablonlar dosyaya yazılmaz)."""
    validate(rule.get("rule") or {})
    try:
        with open(rules_path(), "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if not isinstance(saved, list):
            saved = []
    except (OSError, ValueError):
        saved = []

    saved = [item for item in saved if item.get("id") != rule.get("id")]
    saved.append(rule)

    os.makedirs(os.path.dirname(rules_path()), exist_ok=True)
    tmp = rules_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(saved, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, rules_path())
    return saved


def validate(rule: dict, depth: int = 0) -> None:
    """Kural yapısını doğrular; hatalıysa RuleError atar."""
    if depth > 8:
        raise RuleError("kural fazla iç içe")
    if not isinstance(rule, dict):
        raise RuleError("kural sözlük olmalı")

    if "operator" in rule:
        if rule["operator"] not in (VE, VEYA):
            raise RuleError(f"bilinmeyen bağlaç: {rule['operator']}")
        operands = rule.get("operands")
        if not isinstance(operands, list) or not operands:
            raise RuleError("grup en az bir koşul içermeli")
        for operand in operands:
            validate(operand, depth + 1)
        return

    field = rule.get("field")
    if field not in ALANLAR:
        raise RuleError(f"bilinmeyen alan: {field}")
    if rule.get("op") not in OPERATORLER:
        raise RuleError(f"bilinmeyen operatör: {rule.get('op')}")
    if "value" not in rule:
        raise RuleError("koşulda değer yok")

    # Yön alanlarında yazım/sözlük hatasını kabul etmiyoruz: "düşüş" gibi başka
    # bir modülün sözlüğünden gelen bir değer, hiç eşleşmeyen ama hata da
    # vermeyen bir filtre üretir.
    izinli = YON_DEGERLERI.get(field)
    if izinli and rule["value"] not in izinli:
        raise RuleError(
            f"{field} alanı yalnızca şu değerleri alır: {', '.join(izinli)} "
            f"(verilen: {rule['value']!r})"
        )


def field_catalog() -> list[dict]:
    """Arayüzün filtre kurucusunda göstereceği alan listesi."""
    return [
        {"field": field, "label": tanim["label"], "format": tanim["format"]}
        for field, tanim in ALANLAR.items()
    ]
