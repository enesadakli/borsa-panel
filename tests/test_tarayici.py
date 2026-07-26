"""Tarayıcı motoru testi.

Sahte (sentetik) bir bağlam kaydı üzerinde çalışır: ağa çıkmaz, Yahoo verisi
değiştiğinde kırılmaz ve kenar durumlar (eksik veri, sektörde tanımsız) kasten
kurulabilir.

En önemli davranış üç değerli mantık: bir koşul `True`, `False` veya
**değerlendirilemedi** olabilir. Eksik veriyi `False` saymak şirketi haksız
yere eler, `True` saymak da geçmemiş şirketi listeye sokar. İkisi de yanlış;
satır "kısmi" olarak işaretlenir.
"""

from __future__ import annotations

from core import screener as S


def _sirket(symbol, sector="Industrials", **kwargs):
    """Test için tek satırlık bağlam kaydı."""
    metrics = {
        "fscore": kwargs.get("fscore"),
        "net_debt_ebitda": kwargs.get("net_debt_ebitda"),
        "real_revenue_growth": kwargs.get("real_revenue_growth"),
        "pe": kwargs.get("pe"),
        "roe": kwargs.get("roe"),
    }
    screen = {
        "fcf_positive": kwargs.get("fcf_positive"),
        "fcf_ge_net_income": kwargs.get("fcf_ge_net_income"),
        "net_debt_ebitda_delta": kwargs.get("net_debt_ebitda_delta"),
        "fscore_change": kwargs.get("fscore_change"),
        "operating_margin_direction": kwargs.get("operating_margin_direction"),
    }
    if "operating_margin_direction" in kwargs:
        from core import health as H

        assert kwargs["operating_margin_direction"] in H.MARJ_YONLERI, (
            "test verisi de gerçek sözlüğü kullanmalı"
        )
    return {
        "name": f"{symbol} A.Ş.",
        "sector": sector,
        "currency": "TRY",
        "market_cap": kwargs.get("market_cap", 1e9),
        "bank_accounting": kwargs.get("bank_accounting", False),
        "metrics": metrics,
        "screen": screen,
        "not_applicable": kwargs.get("not_applicable", []),
        "trends": {},
    }


def _baglam():
    return {
        "market": "test",
        "symbols": {
            # tüm kriterleri geçen
            "SAGLAM.IS": _sirket("SAGLAM", fscore=8, net_debt_ebitda=0.9,
                                 fcf_positive=True, fcf_ge_net_income=True,
                                 real_revenue_growth=0.05, market_cap=5e9,
                                 operating_margin_direction="genişleme",
                                 net_debt_ebitda_delta=-0.3, fscore_change=3),
            # F-Skoru düşük
            "ZAYIF.IS": _sirket("ZAYIF", fscore=3, net_debt_ebitda=4.2,
                                fcf_positive=False, fcf_ge_net_income=False,
                                real_revenue_growth=-0.12, market_cap=2e9,
                                operating_margin_direction="daralma",
                                net_debt_ebitda_delta=1.4, fscore_change=-2),
            # F-Skoru yüksek ama FCF verisi yok → kısmi
            "EKSIK.IS": _sirket("EKSIK", fscore=8, net_debt_ebitda=1.1,
                                fcf_positive=None, market_cap=3e9),
            # banka: F-Skoru sektörde tanımsız
            "BANKA.IS": _sirket("BANKA", sector="Financial Services",
                                bank_accounting=True, fcf_positive=True,
                                market_cap=9e9,
                                not_applicable=["fscore", "net_debt_ebitda"]),
        },
        "sector_stats": {},
        "universe_stats": {},
    }


# ------------------------------------------------------------- kural doğrulama


def test_gecersiz_kurallar_reddediliyor():
    hatali = [
        {},
        {"field": "yok_boyle_alan", "op": ">", "value": 1},
        {"field": "fscore", "op": "=~", "value": 1},
        {"field": "fscore", "op": ">"},                      # değer yok
        {"operator": "XOR", "operands": [{"field": "fscore", "op": ">", "value": 1}]},
        {"operator": S.VE, "operands": []},                  # boş grup
    ]
    for kural in hatali:
        try:
            S.validate(kural)
        except S.RuleError:
            continue
        raise AssertionError(f"geçersiz kural kabul edildi: {kural}")


def test_gecerli_kural_dogrulaniyor():
    S.validate(
        {
            "operator": S.VE,
            "operands": [
                {"field": "fscore", "op": ">=", "value": 7},
                {"operator": S.VEYA, "operands": [
                    {"field": "pe", "op": "<", "value": 15},
                    {"field": "roe", "op": ">", "value": 0.2},
                ]},
            ],
        }
    )


def test_tum_sablonlar_gecerli():
    for sablon in S.SABLONLAR:
        S.validate(sablon["rule"])
        assert sablon["note"] == "Filtre örneği — tavsiye değil.", (
            f"{sablon['id']}: şablon etiketi eksik veya farklı"
        )
        assert sablon["explanation"], f"{sablon['id']}: açıklama yok"


def test_yon_alaninda_yanlis_sozluk_reddediliyor():
    """Sessiz hata koruması.

    `operating_margin_direction` alanı health.py'nin sözlüğünü kullanır
    ("genişleme/daralma/yatay"). context.trend() ise "artış/düşüş/yatay" der.
    İkisi karışınca kural hiç eşleşmez ama hata da vermez — filtre çalışıyor
    görünür, hiçbir şeyi elemez. Bu test o kaymayı yakalar.
    """
    from core import health as H

    try:
        S.validate({"field": "operating_margin_direction", "op": "!=", "value": "düşüş"})
    except S.RuleError:
        pass
    else:
        raise AssertionError("yanlış sözlükten gelen değer kabul edildi")

    # Doğru sözlükteki her değer kabul edilmeli.
    for yon in H.MARJ_YONLERI:
        S.validate({"field": "operating_margin_direction", "op": "!=", "value": yon})


def test_sablonlar_dogru_yon_sozlugunu_kullaniyor():
    from core import health as H

    for sablon in S.SABLONLAR:
        for kosul in _kosullari(sablon["rule"]):
            izinli = S.YON_DEGERLERI.get(kosul.get("field"))
            if izinli:
                assert kosul["value"] in izinli, (
                    f"{sablon['id']}: {kosul['field']} için geçersiz değer "
                    f"{kosul['value']!r}; izinli: {izinli}"
                )
    assert S.YON_DEGERLERI["operating_margin_direction"] == H.MARJ_YONLERI


def _kosullari(node):
    if "operator" in node:
        for operand in node["operands"]:
            yield from _kosullari(operand)
    else:
        yield node


def test_ic_ice_kural_sinirli():
    kural = {"field": "fscore", "op": ">", "value": 1}
    for _ in range(12):
        kural = {"operator": S.VE, "operands": [kural]}
    try:
        S.validate(kural)
    except S.RuleError:
        return
    raise AssertionError("aşırı iç içe kural reddedilmeliydi")


# ------------------------------------------------------------ üç değerli mantık


def test_eksik_veri_kismi_sayiliyor():
    row = _baglam()["symbols"]["EKSIK.IS"]
    sonuc = S.evaluate(row, S.SABLONLAR[0]["rule"])  # bilanço kalitesi

    assert sonuc["partial"] is True, "eksik veri kısmi olarak işaretlenmeli"
    assert sonuc["passed"] is False, "kısmi satır 'geçti' sayılmamalı"
    fcf = next(check for check in sonuc["checks"] if check["field"] == "fcf_positive")
    assert fcf["result"] is None
    assert fcf["reason"] == "veri yok"
    assert fcf["display"] == "?", "eksik değer '?' olarak gösterilmeli"


def test_sektorde_tanimsiz_ayri_gerekce():
    row = _baglam()["symbols"]["BANKA.IS"]
    sonuc = S.evaluate(row, {"field": "fscore", "op": ">=", "value": 7})
    check = sonuc["checks"][0]
    assert check["result"] is None
    assert check["reason"] == "bu sektörde tanımsız", (
        "sektörde tanımsız olan, veri eksikliğinden ayrı raporlanmalı"
    )
    assert check["display"] == "NA"


def test_ve_baglaci_kesin_false_ile_kisa_devre():
    """Bir koşul kesin False ise eksik veri sonucu değiştirmez."""
    row = _baglam()["symbols"]["EKSIK.IS"]
    kural = {
        "operator": S.VE,
        "operands": [
            {"field": "fscore", "op": "<", "value": 5},        # False (8 < 5 değil)
            {"field": "fcf_positive", "op": "==", "value": True},  # None
        ],
    }
    sonuc = S.evaluate(row, kural)
    assert sonuc["result"] is False, (
        "kesin False varsa grup False olmalı, kararsız kalmamalı"
    )


def test_veya_baglaci_kesin_true_ile_kisa_devre():
    row = _baglam()["symbols"]["EKSIK.IS"]
    kural = {
        "operator": S.VEYA,
        "operands": [
            {"field": "fscore", "op": ">=", "value": 7},           # True
            {"field": "fcf_positive", "op": "==", "value": True},  # None
        ],
    }
    sonuc = S.evaluate(row, kural)
    assert sonuc["result"] is True, (
        "VEYA grubunda bir koşul kesin geçtiyse eksik veri sonucu bozmamalı"
    )
    assert sonuc["passed"] is True, "kural sağlandı, kısmi olsa da geçmiş sayılmalı"
    assert sonuc["partial"] is True, "eksik kriter yine de işaretlenmeli"


# -------------------------------------------------------------------- tarama


def test_sablon_dogru_sirketi_buluyor():
    sonuc = S.run_template(_baglam(), "bilanco_kalitesi")
    eslesen = {kayit["symbol"] for kayit in sonuc["matched"]}
    assert eslesen == {"SAGLAM.IS"}, f"beklenen SAGLAM.IS, gelen {eslesen}"

    kismi = {kayit["symbol"] for kayit in sonuc["partial"]}
    assert "EKSIK.IS" in kismi, "eksik verili şirket kısmi listede olmalı"
    assert sonuc["template"]["note"] == "Filtre örneği — tavsiye değil."


def test_sektorde_tanimsiz_kismi_listesine_girmiyor():
    """Banka, F-Skoru filtresinde "geçmiş olabilir" diye listelenmemeli.

    İkisi de "karar verilemedi" ama sebepleri farklı: veri eksikse bir gün
    gelebilir, sektörde tanımsızsa asla. Bankaları her F-Skoru taramasının
    kısmi listesinde göstermek, kullanıcıya yapabileceği bir şey varmış
    izlenimi verir.
    """
    sonuc = S.run_template(_baglam(), "bilanco_kalitesi")

    kismi = {kayit["symbol"] for kayit in sonuc["partial"]}
    uygulanamaz = {kayit["symbol"] for kayit in sonuc["not_applicable"]}

    assert "BANKA.IS" in uygulanamaz, "banka uygulanamaz listesinde olmalı"
    assert "BANKA.IS" not in kismi, "banka kısmi listesinde olmamalı"
    assert "EKSIK.IS" in kismi, "veri eksikliği kısmi listesinde olmalı"
    assert "EKSIK.IS" not in uygulanamaz

    banka = next(k for k in sonuc["not_applicable"] if k["symbol"] == "BANKA.IS")
    assert banka["sector_blocked"] is True
    assert "fscore" in banka["not_applicable_fields"]

    eksik = next(k for k in sonuc["partial"] if k["symbol"] == "EKSIK.IS")
    assert eksik["partial"] is True
    assert "fcf_positive" in eksik["missing_fields"]
    assert not eksik["not_applicable_fields"]


def test_sonuc_satirinda_kriter_kriter_puan_var():
    sonuc = S.run_template(_baglam(), "bilanco_kalitesi")
    kayit = sonuc["matched"][0]
    assert kayit["total"] == 3, "üç kriterin hepsi raporlanmalı"
    assert kayit["score"] == 3
    for check in kayit["checks"]:
        assert check["label"], "kriterin ekran adı olmalı"
        assert check["display"], "kriterin değeri gösterilebilir olmalı"


def test_reel_buyuyen_sablonu_marj_dususunu_eliyor():
    sonuc = S.run_template(_baglam(), "reel_buyuyen")
    eslesen = {kayit["symbol"] for kayit in sonuc["matched"]}
    assert "SAGLAM.IS" in eslesen
    assert "ZAYIF.IS" not in eslesen, "marjı düşen şirket geçmemeli"


def test_siralama_ve_limit():
    baglam = _baglam()
    kural = {"field": "market_cap", "op": ">", "value": 0}
    sonuc = S.screen(baglam, kural, sort_by="market_cap", limit=2)
    assert len(sonuc["matched"]) == 2
    degerler = [kayit["market_cap"] for kayit in sonuc["matched"]]
    assert degerler == sorted(degerler, reverse=True), "azalan sıralama bozuk"


def test_sonuc_notu_siralama_yargisi_icermiyor():
    sonuc = S.run_template(_baglam(), "bilanco_kalitesi")
    assert "getiri hakkında bilgi taşımaz" in sonuc["note"]


def test_bilinmeyen_sablon_hata_veriyor():
    try:
        S.run_template(_baglam(), "olmayan_sablon")
    except S.RuleError:
        return
    raise AssertionError("bilinmeyen şablon hata vermeliydi")


# ------------------------------------------------------------------ biçimleme


def test_bicimleme():
    assert S._bicimle(None, "ratio") == "?"
    assert S._bicimle("NA", "ratio") == "NA"
    assert S._bicimle(True, "bool") == "var"
    assert S._bicimle(False, "bool") == "yok"
    assert S._bicimle(8, "score") == "8/9"
    assert S._bicimle(0.1234, "percent") == "%+12,3"
    assert S._bicimle(-0.5, "delta") == "-0,50"
    # core.bicim.para_kisa 2 basamak kullanıyor (core.bicim.para ile aynı
    # hassasiyet); eski hâli 1 basamaktı, iki ayrı formatlayıcı tek kaynağa
    # (core.bicim) indirgenirken hassasiyet de hizalandı.
    assert S._bicimle(2.5e9, "money") == "2,50Mr"


def test_alan_katalogu_tam():
    katalog = S.field_catalog()
    assert len(katalog) == len(S.ALANLAR)
    for item in katalog:
        assert item["label"], f"{item['field']}: ekran adı yok"
        assert item["format"], f"{item['field']}: biçim tanımı yok"
