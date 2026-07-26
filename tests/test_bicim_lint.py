"""Biçim lint — ham sayı biçimlendirme kalıplarının geri gelmemesi testi.

S5 sınıfı: `tools/rapor.py`'de nokta ondalık ("9.00") çıkması, CLI araçlarının
`core.bicim`'i atlayıp kendi `:.2f` gibi ham biçimlerini kullanmasından
kaynaklanıyordu. F2'de düzeltildi ama düzeltme yalnızca o dosyaya uygulandı;
bu test aynı hatanın *başka bir dosyada* sessizce geri gelmesini engeller.

Taranan dosyalar `core/{narrative,flags,reports,health,risk,market}.py` +
`tools/{rapor,filtre}.py` — kullanıcıya sayı gösteren tüm modüller. Aranan
kalıp `:.<N>f`, `:.<N>%`, `:,.<N>f` gibi Python'ın kendi sayı biçimleyicisi;
bunlar Türkçe virgül/nokta dönüşümünden geçmez. Bilinçli bir istisna
gerekiyorsa satırın sonuna `# bicim-istisna` yorumu eklenir ve bu tarama onu
atlar — ama böyle bir satır bugün yok, hedef sıfır.
"""

from __future__ import annotations

import os
import re

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOSYALAR = (
    "core/narrative.py", "core/flags.py", "core/reports.py",
    "core/health.py", "core/risk.py", "core/market.py",
    "tools/rapor.py", "tools/filtre.py",
)

# Python'ın kendi sayı biçimi: isteğe bağlı işaret/ayraç + nokta + basamak
# sayısı + tip harfi (f/F/e/E/g/G/%). `{sira:3d}` gibi hizalama amaçlı tam
# sayı genişlik belirteçleri kasıtlı olarak dışarıda — onlar tablo hizalar,
# ondalık/yüzde biçimlendirmez.
HAM_KALIP = re.compile(r":[-+ ]?[,_]?\.[0-9]+[fFeEgG%]")

ISTISNA_YORUMU = "# bicim-istisna"


def _ihlaller(path: str) -> list[str]:
    hatalar = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if ISTISNA_YORUMU in line:
                continue
            if HAM_KALIP.search(line):
                hatalar.append(f"{lineno}: {line.strip()}")
    return hatalar


def test_ham_bicim_kalibi_yok():
    hatalar = []
    for gorunen in DOSYALAR:
        path = os.path.join(KOK, gorunen)
        if not os.path.isfile(path):
            continue
        for satir in _ihlaller(path):
            hatalar.append(f"{gorunen}:{satir}")
    assert not hatalar, (
        "Ham sayı biçimi bulundu — core.bicim üzerinden geçmeli veya "
        f"'{ISTISNA_YORUMU}' ile bilinçli işaretlenmeli:\n   "
        + "\n   ".join(hatalar)
    )


def test_istisna_yorumu_tarama_disi_birakiyor():
    """Lint mekanizmasının kendisi çalışıyor mu — pozitif kontrol."""
    ornek = 'x = f"%{deger:.0f}"  # bicim-istisna\n'
    assert HAM_KALIP.search(ornek), "kalıp gerçek bir ham biçimi yakalamıyor"
    with_comment_ok = ISTISNA_YORUMU in ornek
    assert with_comment_ok


def test_kalip_gercek_ihlali_yakaliyor():
    assert HAM_KALIP.search('f"%{x:.0f}"')
    assert HAM_KALIP.search('f"{x:,.2f}"')
    assert HAM_KALIP.search('f"{x:.1%}"')
    # Tam sayı hizalama (tablo sütunu) yanlış yakalanmamalı.
    assert not HAM_KALIP.search('f"{sira:3d}. {ad}"')
