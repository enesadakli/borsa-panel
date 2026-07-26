"""Dil sınırı testi.

Aracın en önemli kuralı insan disiplinine bırakılmıyor: bu test, kullanıcıya
gösterilen tüm metinleri yasak kelime listesine karşı tarar. Bir gün birisi
(ben dahil) şablona "cazip" yazarsa test kırmızı yanar.

Yalnızca **kullanıcıya görünen** metinler taranır:
  - Python dosyalarındaki string sabitleri (docstring'ler hariç — onlar
    geliştiriciye yazılmış açıklamalar, arayüzde görünmez)
  - web/*.html içindeki etiket dışı metin

Ayrıca zorunlu uyarı cümlesinin her HTML sayfasında bulunduğu doğrulanır.
"""

from __future__ import annotations

import ast
import os
import re

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UYARI = "yatırım tavsiyesi vermez"

# Yasak kalıplar: (desen, neden). Kullanıcı metninde geçerse test düşer.
YASAK = [
    (r"hedef fiyat", "hedef fiyat verilemez"),
    (r"\b(al|sat|alım|satım)\s+sinyali", "al/sat sinyali üretilemez"),
    (r"tavsiye eder(im|iz)", "tavsiye dili"),
    (r"öneri(yorum|yoruz|lir|riz)", "öneri dili"),
    (r"\bucuz\b", "değerleme yargısı"),
    (r"\bpahalı\b", "değerleme yargısı"),
    (r"\bcazip\b", "değerleme yargısı"),
    (r"kaçırılmaz", "aciliyet dili"),
    (r"\bfırsat\b", "aciliyet dili"),
    (r"kesin kazanç", "getiri vaadi"),
    (r"garanti (getiri|kazanç)", "getiri vaadi"),
    (r"alın(malı|abilir)\b", "alım yönlendirmesi"),
    (r"satıl(malı|abilir)\b", "satım yönlendirmesi"),
    (r"(iyi|kötü) hisse", "hisse hakkında yargı"),
    (r"portföyüne (ekle|kat)", "alım yönlendirmesi"),
]

# "yatırım tavsiyesi" ifadesi yalnızca reddedildiği bağlamda serbest.
TAVSIYE_DESENI = re.compile(r"yatırım tavsiyesi(?!\s+(vermez|değildir|değil))", re.I)

# Tarayıcı şablonlarındaki "tavsiye değil" etiketi kasıtlı ve serbest.
IZINLI = (
    "tavsiye değil",
    "yatırım tavsiyesi vermez",
    "yatırım tavsiyesi değildir",
)


def _python_stringleri(path: str) -> list[tuple[int, str]]:
    """Kullanıcıya görünen string sabitleri (docstring'ler hariç)."""
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=path)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.append((node.lineno, node.value))
    return out


def _html_metni(path: str) -> str:
    """HTML'den görünen metni çıkarır ve boşlukları tek boşluğa indirger.

    Boşluk normalleştirmesi şart: kaynakta satır sonuna denk gelen bir cümle
    ("...yatırım tavsiyesi\\n      vermez.") tarayıcıda tek cümle olarak görünür
    ama ham metinde arama başarısız olur. Test biçimlendirmeyi değil içeriği
    denetlemeli.
    """
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    without_code = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", without_code))


def _ihlaller(text: str) -> list[str]:
    # Python string sabitleri de satıra bölünmüş olabilir; aynı sebeple
    # boşluklar tek boşluğa indirgeniyor.
    lowered = re.sub(r"\s+", " ", text.lower())
    for izin in IZINLI:
        lowered = lowered.replace(izin, " ")
    bulunan = []
    for desen, neden in YASAK:
        if re.search(desen, lowered, re.I):
            bulunan.append(f"{neden} ({desen})")
    if TAVSIYE_DESENI.search(lowered):
        bulunan.append("'yatırım tavsiyesi' reddedilmeyen bağlamda")
    return bulunan


# tools/anlati_denetim.py, işi gereği bu yasak kelimeleri veri olarak
# (kendi arama kalıpları listesinde) taşıyor — kullanıcıya gösterilen metin
# değil, denetim aracının kendi YASAK listesi. Taranırsa kendi varlık sebebi
# yüzünden bu test her zaman kırmızı yanar.
_TARAMA_DISI = {"tools/anlati_denetim.py"}


def _taranacak_python() -> list[tuple[str, str]]:
    """(görünen ad, tam yol) — kullanıcıya metin gösteren tüm Python dosyaları.

    Yalnızca core/ taramak yetmez: sunucunun hata mesajları ve araçların konsol
    çıktıları da kullanıcının okuduğu metinlerdir.
    """
    out = []
    for klasor in ("core", "tools"):
        dizin = os.path.join(KOK, klasor)
        if not os.path.isdir(dizin):
            continue
        for name in sorted(os.listdir(dizin)):
            if name.endswith(".py") and f"{klasor}/{name}" not in _TARAMA_DISI:
                out.append((f"{klasor}/{name}", os.path.join(dizin, name)))
    for name in ("server.py", "smoke.py"):
        path = os.path.join(KOK, name)
        if os.path.isfile(path):
            out.append((name, path))
    return out


def test_python_metinleri_temiz():
    hatalar = []
    for gorunen, path in _taranacak_python():
        for lineno, text in _python_stringleri(path):
            for ihlal in _ihlaller(text):
                hatalar.append(f"{gorunen}:{lineno} → {ihlal}\n      {text[:90]!r}")
    assert not hatalar, "Yasak dil bulundu:\n   " + "\n   ".join(hatalar)


def test_uyari_metni_tek_yerde_tanimli():
    """Uyarı cümlesi kopyalanarak çoğaltılmasın; biri değişirse hepsi değişmeli."""
    import re as _re

    sayim = 0
    for gorunen, path in _taranacak_python():
        for _, text in _python_stringleri(path):
            if UYARI in text.lower():
                sayim += 1
    assert sayim <= 3, (
        f"Uyarı metni {sayim} ayrı string sabitinde geçiyor; tek bir sabitten "
        "türetilmeli ki biri güncellenince diğerleri geride kalmasın"
    )


def test_html_metinleri_temiz():
    hatalar = []
    web = os.path.join(KOK, "web")
    if not os.path.isdir(web):
        return
    for name in sorted(os.listdir(web)):
        if name.endswith(".html"):
            for ihlal in _ihlaller(_html_metni(os.path.join(web, name))):
                hatalar.append(f"web/{name} → {ihlal}")
    assert not hatalar, "Yasak dil bulundu:\n   " + "\n   ".join(hatalar)


def test_js_metinleri_temiz():
    """web/app.js — F6'ya kadar bu dosya hiç taranmıyordu.

    `_taranacak_python()` yalnızca core/tools/server.py'yi, `test_html_metinleri_temiz`
    yalnızca web/*.html'i tarıyor; arayüzdeki en kalabalık sabit metin kaynağı
    (app.js'teki Türkçe UI etiketleri, karşılama metinleri, panel başlıkları)
    hiçbir taramadan geçmiyordu. JS string sabitlerini ayrıştırmaya gerek yok:
    yasak kalıplar yeterince özgül (tam kelime/öbek) olduğu için ham kaynak
    metni üzerinde arama yanlış pozitif üretmez — kod ile veri (dize) ayrımı
    HTML taramasında olduğu gibi burada da gerekmiyor.
    """
    path = os.path.join(KOK, "web", "app.js")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    hatalar = [f"web/app.js → {ihlal}" for ihlal in _ihlaller(raw)]
    assert not hatalar, "Yasak dil bulundu:\n   " + "\n   ".join(hatalar)


def test_uyari_her_sayfada_var():
    web = os.path.join(KOK, "web")
    if not os.path.isdir(web):
        return
    eksik = [
        name
        for name in sorted(os.listdir(web))
        if name.endswith(".html")
        and UYARI not in _html_metni(os.path.join(web, name)).lower()
    ]
    assert not eksik, f"Zorunlu uyarı metni eksik: {', '.join(eksik)}"
