/* Borsa Paneli — arayüz.
 *
 * Tüm analiz sunucuda (core/ modülleri). Buradaki iş yalnızca API'den geleni
 * göstermek. Bu dosyada eşik, formül veya yorum kuralı yok — olursa iki yerde
 * iki farklı gerçek doğar.
 *
 * Üç kural:
 *  1. Renk asla tek başına anlam taşımaz; her renkli öğenin metin etiketi var.
 *  2. Her sayının kaynağı gösterilir (kaynak satırları, dönem etiketleri).
 *  3. Reel rakam birincil (büyük), nominal ikincil (küçük ve soluk).
 */

"use strict";

const API = {
  async al(yol) {
    const yanit = await fetch(yol, { headers: { Accept: "application/json" } });
    const govde = await yanit.json().catch(() => ({ hata: "yanıt okunamadı" }));
    if (!yanit.ok) {
      const hata = new Error(govde.hata || `HTTP ${yanit.status}`);
      hata.durum = yanit.status;
      throw hata;
    }
    return govde;
  },
};

/* ═══════════════════════════════════════════════════════ biçimlendirme */

const kacir = (metin) =>
  String(metin ?? "").replace(/[&<>"']/g, (k) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[k]));

const TR = (deger, basamak = 2) => {
  if (deger === null || deger === undefined || Number.isNaN(deger)) return "—";
  // Yuvarlanınca sıfıra düşen negatifler "-0,0" diye görünmesin.
  const esik = 0.5 * 10 ** -basamak;
  const temiz = Math.abs(deger) < esik ? 0 : deger;
  return temiz.toLocaleString("tr-TR", {
    minimumFractionDigits: basamak,
    maximumFractionDigits: basamak,
  });
};

/** Oran (0,415) → "%+41,5". */
const yuzde = (deger, isaretli = true) => {
  if (deger === null || deger === undefined) return "—";
  const govde = TR(deger * 100, 1);
  return isaretli && deger > 0 ? `%+${govde}` : `%${govde}`;
};

/** Zaten puan cinsinden gelen değer (27,61) → "%27,6". */
const puan = (deger) => (deger === null || deger === undefined ? "—" : `%${TR(deger, 1)}`);

const para = (deger, birim = "") => {
  if (deger === null || deger === undefined) return "—";
  for (const [limit, ek] of [[1e12, "T"], [1e9, "Mr"], [1e6, "Mn"], [1e3, "B"]]) {
    if (Math.abs(deger) >= limit) return `${TR(deger / limit, 2)} ${ek} ${birim}`.trim();
  }
  return `${TR(deger, 0)} ${birim}`.trim();
};

/* Her metriğin gösterim biçimi. Sunucudaki context.METRIKLER ile aynı
 * anahtarlar; biçim bilgisi burada çünkü tamamen sunum meselesi. */
/* Altman Z'de 2,99 üstü "güvenli bölge"dir; ötesindeki hassasiyet anlam
 * taşımaz. NETCD'nin 61,34'ü DOCO'nun 4,95'inden "12 kat güvenli" demek
 * değil — formülde bir terim piyasa değerini toplam yükümlülüğe bölüyor ve
 * yükümlülük sıfıra yaklaşınca sonuç patlıyor. 10 üstünü tavanlıyoruz. */
const ALTMAN_TAVAN = 10;

const METRIK_BICIM = {
  fscore: (d) => `${TR(d, 0)}/9`,
  altman_z: (d) => (d > ALTMAN_TAVAN ? `${ALTMAN_TAVAN}+` : TR(d, 2)),
  roe: (d) => yuzde(d, false),
  roa: (d) => yuzde(d, false),
  gross_margin: puan,
  operating_margin: puan,
  net_margin: puan,
  net_debt_ebitda: (d) => TR(d, 2),
  debt_to_equity: (d) => TR(d, 2),
  interest_coverage: (d) => `${TR(d, 1)} kat`,
  fcf_gap: (d) => yuzde(d, false),
  real_revenue_growth: (d) => yuzde(d),
  real_income_growth: (d) => yuzde(d),
  pe: (d) => TR(d, 2),
  pb: (d) => TR(d, 2),
  dividend_yield: (d) => yuzde(d, false),
};

const bicimle = (metrik, deger) =>
  deger === null || deger === undefined
    ? "—"
    : (METRIK_BICIM[metrik] || ((d) => TR(d, 2)))(deger);

const yonSinifi = (yon) =>
  ({ artış: "e-artis", genişleme: "e-artis", düşüş: "e-dusus", daralma: "e-dusus" }[yon] || "e-yatay");

const isaretRengi = (deger) =>
  deger === null || deger === undefined ? "" : deger > 0 ? "yesil" : deger < 0 ? "kirmizi" : "";

/* ═══════════════════════════════════════════════════════ terim sözlüğü */

/* Aşamalı iyileştirme: sözlük /api/sozluk'tan bir kez çekilir; gelmezse
 * hiçbir şey bozulmaz, etiketler düz metin kalır. Balon tek ve document.body
 * üzerindedir — #ekran innerHTML ile yeniden çizilse de yaşar. */

let SOZLUK = null;

async function sozlukYukle() {
  try {
    const veri = await API.al("/api/sozluk");
    SOZLUK = veri.terimler || null;
    if (SOZLUK) document.body.classList.add("sozluk-hazir");
  } catch {
    /* sözlük süsleme katmanıdır; hata sessizce yutulur */
  }
}

/** Etiketi, sözlükte karşılığı varsa balonlu bir span'e sarar. */
function terim(anahtar, etiket) {
  if (!SOZLUK || !SOZLUK[anahtar]) return kacir(etiket);
  return `<span class="terim" data-terim="${kacir(anahtar)}" tabindex="0">${kacir(etiket)}</span>`;
}

function terimBalonuKur() {
  const balon = document.createElement("div");
  balon.id = "terim-balon";
  balon.setAttribute("role", "tooltip");
  balon.hidden = true;
  document.body.appendChild(balon);

  let acikHedef = null;      // balonu açık tutan .terim öğesi
  let sabitlendi = false;    // tıklama/dokunmayla mı açıldı (hover'dan farklı)

  const kapat = () => {
    if (!acikHedef) return;
    acikHedef.removeAttribute("aria-describedby");
    acikHedef = null;
    sabitlendi = false;
    balon.hidden = true;
  };

  const ac = (hedef, sabit) => {
    const giris = SOZLUK && SOZLUK[hedef.dataset.terim];
    if (!giris) return;
    kapat();
    balon.textContent = "";
    const bas = document.createElement("b");
    bas.textContent = giris.ad;
    balon.appendChild(bas);
    balon.appendChild(document.createTextNode(giris.aciklama));
    balon.hidden = false;

    // Önce görünür yap ki ölçüsü alınabilsin, sonra konumlandır.
    const kutu = hedef.getBoundingClientRect();
    const b = balon.getBoundingClientRect();
    let ust = kutu.bottom + 8;
    if (ust + b.height > window.innerHeight - 8) ust = kutu.top - b.height - 8;
    let sol = Math.min(Math.max(8, kutu.left), window.innerWidth - b.width - 8);
    balon.style.top = `${Math.max(8, ust)}px`;
    balon.style.left = `${sol}px`;

    hedef.setAttribute("aria-describedby", "terim-balon");
    acikHedef = hedef;
    sabitlendi = Boolean(sabit);
  };

  document.addEventListener("mouseover", (olay) => {
    const hedef = olay.target.closest(".terim");
    if (hedef && hedef !== acikHedef) ac(hedef, false);
  });
  document.addEventListener("mouseout", (olay) => {
    if (sabitlendi) return;
    const hedef = olay.target.closest(".terim");
    if (hedef && hedef === acikHedef && !hedef.contains(olay.relatedTarget)) kapat();
  });
  document.addEventListener("focusin", (olay) => {
    const hedef = olay.target.closest(".terim");
    if (hedef) ac(hedef, false);
  });
  document.addEventListener("focusout", (olay) => {
    if (!sabitlendi && olay.target.closest(".terim")) kapat();
  });
  document.addEventListener("click", (olay) => {
    const hedef = olay.target.closest(".terim");
    if (!hedef) { kapat(); return; }        // dışarı tıklama kapatır
    if (hedef === acikHedef && sabitlendi) kapat();  // yeniden dokunma kapatır
    else ac(hedef, true);                    // dokunma açar ve sabitler (mobil)
  });
  document.addEventListener("keydown", (olay) => {
    if (olay.key === "Escape") kapat();
  });
  document.addEventListener("scroll", kapat, { passive: true });
  window.addEventListener("hashchange", kapat);
}

/* ═══════════════════════════════════════════════════════════════ SVG */

/** Çok şeritli zaman serisi grafiği.
 *
 * Her seri kendi şeridinde, kendi ölçeğinde; zaman ekseni ortak. Farklı
 * birimdeki serileri (0–9 skor, % marj, kat borç oranı) tek eksene bindirmek
 * çizgilerin kesişmesine anlam yükletirdi.
 */
function seritGrafik(seriler, genislik = 700) {
  const gecerli = seriler.filter((s) => s.noktalar.filter((n) => n.deger !== null).length >= 2);
  if (!gecerli.length) return "";

  const solPay = 126, sagPay = 20, seritY = 44, bosluk = 14, ustPay = 8, altPay = 24;
  const yukseklik = ustPay + gecerli.length * (seritY + bosluk) + altPay;

  const tarihler = [...new Set(gecerli.flatMap((s) => s.noktalar.map((n) => n.tarih)))].sort();
  const xOf = (tarih) => {
    const i = tarihler.indexOf(tarih);
    if (tarihler.length === 1) return solPay + (genislik - solPay - sagPay) / 2;
    return solPay + (i / (tarihler.length - 1)) * (genislik - solPay - sagPay);
  };

  let svg = `<svg class="grafik" viewBox="0 0 ${genislik} ${yukseklik}" role="img"
    aria-label="Kalite metriklerinin dönem dönem seyri">`;

  gecerli.forEach((seri, sira) => {
    const ust = ustPay + sira * (seritY + bosluk);
    const alt = ust + seritY;
    const degerler = seri.noktalar.filter((n) => n.deger !== null).map((n) => n.deger);
    const enAz = Math.min(...degerler), enCok = Math.max(...degerler);
    const aralik = enCok - enAz || 1;
    const yOf = (d) => alt - ((d - enAz) / aralik) * (seritY - 10) - 5;

    svg += `<line x1="${solPay}" y1="${alt}" x2="${genislik - sagPay}" y2="${alt}"
      stroke="currentColor" stroke-width="1" opacity="0.14"/>`;
    svg += `<text x="0" y="${ust + 14}" font-size="12" font-weight="600"
      fill="currentColor">${kacir(seri.ad)}</text>`;
    svg += `<text x="0" y="${ust + 30}" font-size="10.5" fill="currentColor" opacity="0.5"
      >${kacir(seri.aralikMetni || `${seri.bicim(enAz)} – ${seri.bicim(enCok)}`)}</text>`;

    const noktalar = seri.noktalar.filter((n) => n.deger !== null);
    svg += `<polyline points="${noktalar.map((n) => `${xOf(n.tarih)},${yOf(n.deger)}`).join(" ")}"
      fill="none" stroke="${seri.renk}" stroke-width="2.5" stroke-linejoin="round"
      stroke-linecap="round"/>`;
    noktalar.forEach((n) => {
      svg += `<circle cx="${xOf(n.tarih)}" cy="${yOf(n.deger)}" r="4" fill="${seri.renk}"/>`;
      svg += `<text x="${xOf(n.tarih)}" y="${yOf(n.deger) - 9}" font-size="10.5"
        text-anchor="middle" fill="currentColor" font-weight="600" opacity="0.85"
        >${kacir(seri.bicim(n.deger))}</text>`;
    });
  });

  tarihler.forEach((tarih) => {
    svg += `<text x="${xOf(tarih)}" y="${yukseklik - 6}" font-size="11.5" text-anchor="middle"
      fill="currentColor" opacity="0.5">${kacir(tarih.slice(0, 4))}</text>`;
  });

  return svg + "</svg>";
}

/** Sütun grafiği — reel tutar serisi için. */
function sutunGrafik(noktalar, birim, genislik = 700) {
  if (!noktalar.length) return "";
  const yukseklik = 200, altPay = 28, ustPay = 20;
  const enCok = Math.max(...noktalar.map((n) => n.deger));
  const bosluk = 16;
  const sutunG = (genislik - bosluk * (noktalar.length - 1)) / noktalar.length;

  let svg = `<svg class="grafik" viewBox="0 0 ${genislik} ${yukseklik}" role="img"
    aria-label="Enflasyona göre düzeltilmiş gelir">`;
  noktalar.forEach((nokta, sira) => {
    const oran = enCok > 0 ? nokta.deger / enCok : 0;
    const yuksek = Math.max(4, oran * (yukseklik - altPay - ustPay));
    const x = sira * (sutunG + bosluk);
    const y = yukseklik - altPay - yuksek;
    svg += `<rect x="${x}" y="${y}" width="${sutunG}" height="${yuksek}" rx="7"
      fill="var(--vurgu)"/>`;
    svg += `<text x="${x + sutunG / 2}" y="${y - 7}" font-size="13" font-weight="700"
      text-anchor="middle" fill="currentColor">${kacir(para(nokta.deger, birim))}</text>`;
    svg += `<text x="${x + sutunG / 2}" y="${yukseklik - 8}" font-size="11.5"
      text-anchor="middle" fill="currentColor" opacity="0.5"
      >${kacir(nokta.tarih.slice(0, 4))}</text>`;
  });
  return svg + "</svg>";
}

/* ═══════════════════════════════════════════════════════════ durum barı */

let DURUM = null;

// Veri bu kadar saatten eskiyse üst bar "Güncelle" bağlantısı gösterir (7 gün).
const TARAMA_GUNCEL_SINIRI_SAAT = 7 * 24;

async function durumuYukle() {
  try {
    DURUM = await API.al("/api/durum");
  } catch (hata) {
    document.getElementById("tazelik").textContent = `durum alınamadı: ${hata.message}`;
    return;
  }
  const parcalar = DURUM.evrenler.map((e) => {
    if (e.tarama_gerekli) {
      return `${kacir(e.label)}: taranmadı ·
        <button type="button" class="baglanti-dugme" data-tarama-baslat-durum="${kacir(e.id)}"
          >şimdi tara</button>`;
    }
    const yas = e.tarama_yasi_saat;
    const ek = yas === null || yas === undefined ? "" : yas < 1 ? " · yeni" : ` · ${Math.round(yas)} sa`;
    const eski = !e.tarama_calisiyor && yas !== null && yas !== undefined && yas > TARAMA_GUNCEL_SINIRI_SAAT;
    const guncelle = eski
      ? ` · <button type="button" class="baglanti-dugme" data-tarama-baslat-durum="${kacir(e.id)}"
          >Güncelle</button>`
      : "";
    return `${kacir(e.label)} ${e.taranan}${kacir(ek)}${guncelle}`;
  });
  if (!DURUM.evds_anahtari_var) parcalar.push("EVDS anahtarı yok");
  document.getElementById("tazelik").innerHTML = parcalar.join("   ·   ");

  // Sayfa yeniden açıldığında (ya da başka bir sekmeden) zaten sürmekte olan
  // bir tarama varsa ilerleme çubuğunu sessizce devam ettir — kullanıcı
  // düğmeye tekrar basmak zorunda kalmasın.
  const suren = DURUM.evrenler.find((e) => e.tarama_calisiyor);
  if (suren) taramaTakipEt(suren.id);
}

/* ═══════════════════════════════════════════════════════════ panel taraması
 *
 * Tarama ~15-17 dakika sürüyor; sunucu tarafı kendi YahooClient'ıyla arka
 * planda çalışıyor (bkz. server.py TaramaYoneticisi — global kilidi tutmuyor,
 * bu yüzden tarama sürerken diğer ekranlar donmuyor). Burada yapılan tek şey
 * ilerlemeyi 2 saniyede bir yoklamak; ilerleme durumu üst bardaki tek bir
 * göstergede toplanıyor ki hangi ekranda olursa olsun görünsün.
 */

let TARAMA_YOKLAMA_ZAMANLAYICI = null;

async function taramaBaslat(evren) {
  const kapsayici = document.getElementById("tarama-durumu");
  const metin = document.getElementById("tarama-metin");
  kapsayici.hidden = false;
  metin.textContent = `${evren}: başlatılıyor…`;
  try {
    const yanit = await fetch("/api/tarama/baslat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ evren }),
    });
    const govde = await yanit.json().catch(() => ({}));
    if (!yanit.ok) throw new Error(govde.hata || `HTTP ${yanit.status}`);
  } catch (hata) {
    metin.textContent = `${evren}: başlatılamadı — ${hata.message}`;
    setTimeout(() => { kapsayici.hidden = true; }, 6000);
    return;
  }
  taramaTakipEt(evren);
}

function taramaTakipEt(evren) {
  clearTimeout(TARAMA_YOKLAMA_ZAMANLAYICI);
  const kapsayici = document.getElementById("tarama-durumu");
  const metin = document.getElementById("tarama-metin");
  const bar = document.getElementById("tarama-bar-ic");
  const iptalDugmesi = document.getElementById("tarama-iptal");
  kapsayici.hidden = false;
  iptalDugmesi.hidden = false;
  iptalDugmesi.disabled = false;
  iptalDugmesi.textContent = "İptal";

  const bitir = (gecikme) => {
    iptalDugmesi.hidden = true;
    setTimeout(() => { kapsayici.hidden = true; }, gecikme);
  };

  const adim = async () => {
    let durum;
    try {
      durum = await API.al("/api/tarama/durum");
    } catch (hata) {
      metin.textContent = `${evren}: durum alınamadı, tekrar deneniyor…`;
      TARAMA_YOKLAMA_ZAMANLAYICI = setTimeout(adim, 4000);
      return;
    }
    if (durum.calisiyor) {
      const oran = durum.toplam ? Math.round((durum.index / durum.toplam) * 100) : 0;
      metin.textContent = `${kacir(durum.evren || evren)}: ${durum.index}/${durum.toplam}` +
        (durum.son_sembol ? ` · ${kacir(durum.son_sembol)}` : "");
      bar.style.width = `${oran}%`;
      TARAMA_YOKLAMA_ZAMANLAYICI = setTimeout(adim, 2000);
    } else if (durum.iptal_edildi) {
      metin.textContent = `${evren}: tarama iptal edildi — önceki veri korunuyor`;
      bar.style.width = "0%";
      bitir(5000);
    } else if (durum.hata) {
      metin.textContent = `${evren}: tarama hata ile bitti — ${durum.hata}`;
      bar.style.width = "0%";
      bitir(8000);
    } else {
      metin.textContent = `${evren}: tarama tamamlandı`;
      bar.style.width = "100%";
      durumuYukle().then(() => yonlendir());
      bitir(5000);
    }
  };
  adim();
}

async function taramaIptalEt() {
  const iptalDugmesi = document.getElementById("tarama-iptal");
  iptalDugmesi.disabled = true;
  iptalDugmesi.textContent = "İptal ediliyor…";
  try {
    const yanit = await fetch("/api/tarama/iptal", { method: "POST" });
    if (!yanit.ok) {
      const govde = await yanit.json().catch(() => ({}));
      throw new Error(govde.hata || `HTTP ${yanit.status}`);
    }
  } catch (hata) {
    document.getElementById("tarama-metin").textContent = `iptal edilemedi: ${hata.message}`;
    iptalDugmesi.disabled = false;
    iptalDugmesi.textContent = "İptal";
  }
  // Sonucu taramaTakipEt'in zaten süren yoklama döngüsü işleyecek.
}

/* ═══════════════════════════════════════════════════════════════ arama */

let aramaZaman = null;

function aramayiKur() {
  const girdi = document.getElementById("arama-girdi");
  const kutu = document.getElementById("oneriler");
  const kapat = () => { kutu.innerHTML = ""; };

  girdi.addEventListener("input", () => {
    clearTimeout(aramaZaman);
    const sorgu = girdi.value.trim();
    if (sorgu.length < 2) return kapat();
    aramaZaman = setTimeout(async () => {
      try {
        const sonuc = await API.al(`/api/ara?q=${encodeURIComponent(sorgu)}`);
        kutu.innerHTML = sonuc.sonuclar.length
          ? sonuc.sonuclar.map((s) => `<button type="button" data-sembol="${kacir(s.symbol)}">
                <b>${kacir(s.symbol)}</b>
                <span>${kacir(s.name || "")} · ${kacir(s.sector || s.market)}</span>
              </button>`).join("")
          : `<button type="button" disabled>sonuç yok</button>`;
      } catch (hata) {
        kutu.innerHTML = `<button type="button" disabled>arama hatası: ${kacir(hata.message)}</button>`;
      }
    }, 220);
  });

  kutu.addEventListener("click", (olay) => {
    const dugme = olay.target.closest("button[data-sembol]");
    if (!dugme) return;
    girdi.value = ""; kapat();
    aramadanSecildi(dugme.dataset.sembol);
  });

  girdi.addEventListener("keydown", (olay) => {
    if (olay.key === "Escape") { girdi.value = ""; kapat(); }
    if (olay.key === "Enter") {
      const ilk = kutu.querySelector("button[data-sembol]");
      const sembol = ilk ? ilk.dataset.sembol : girdi.value.trim().toUpperCase();
      if (sembol) { girdi.value = ""; kapat(); aramadanSecildi(sembol); }
    }
  });

  document.addEventListener("click", (olay) => {
    if (!olay.target.closest(".arama")) kapat();
  });
}

/** Arama sonucundan bir sembol seçilince ne olacağı ekrana göre değişir:
 * karşılaştırma ekranındaysa mevcut listeye eklenir (en çok KARS_MAKS,
 * yinelenen eklenmez), diğer ekranlarda mevcut sembolün yerini alır. */
function aramadanSecildi(sembol) {
  const { ekran, sembol: mevcutHam } = hashCoz();
  if (ekran !== "karsilastir") { git(ekran, sembol); return; }
  const mevcut = (mevcutHam || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!mevcut.includes(sembol) && mevcut.length < KARS_MAKS) mevcut.push(sembol);
  git(ekran, mevcut.join(","));
}

/* ═══════════════════════════════════════════════════════════ yönlendirme */

const EKRANLAR = {};

const git = (ekran, sembol) => {
  location.hash = sembol ? `#/${ekran}/${encodeURIComponent(sembol)}` : `#/${ekran}`;
};

function hashCoz() {
  const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { ekran: p[0] || "skor", sembol: p[1] ? decodeURIComponent(p[1]) : null };
}

function durumKarti(baslik, aciklama, komut, hatali = false, taramaEvreni = null) {
  return `<section><div class="durum${hatali ? " hatali" : ""}">
      <h3>${kacir(baslik)}</h3>
      <p>${kacir(aciklama)}</p>
      ${komut ? `<code>${kacir(komut)}</code>` : ""}
      ${taramaEvreni ? `<div style="margin-top:14px">
          <button type="button" class="dugme" data-tarama-baslat="${kacir(taramaEvreni)}"
            >Taramayı panelden başlat</button>
        </div>` : ""}
    </div></section>`;
}

async function yonlendir() {
  const { ekran, sembol } = hashCoz();
  document.querySelectorAll("#nav button").forEach((d) => {
    if (d.dataset.ekran === ekran) d.setAttribute("aria-current", "page");
    else d.removeAttribute("aria-current");
  });

  const kap = document.getElementById("ekran");
  kap.innerHTML = `<div class="yuklenirken">yükleniyor…</div>`;

  const cizici = EKRANLAR[ekran];
  if (!cizici) {
    kap.innerHTML = durumKarti(
      "Bu ekran henüz yapılmadı",
      "Skor kartı ekranı ilk sırada bitirildi. Diğer ekranlar sırayla ekleniyor.",
      null,
    );
    return;
  }

  try {
    await cizici(kap, sembol);
  } catch (hata) {
    // 409 yalnızca bağlam taraması gerektiren ekranlarda (piyasa, tarayıcı)
    // oluşur; ikisi de kendi evren seçimini ayrı bir durum değişkeninde tutuyor
    // (PIYASA_EVREN / TARAYICI.evren) — hangi ekranda olduğumuza göre doğru
    // evreni seçiyoruz. Önceden ikisi de her zaman "bist" yazıyordu.
    const evrenIcin = ekran === "piyasa" ? PIYASA_EVREN : ekran === "tarayici" ? TARAYICI.evren : null;
    kap.innerHTML = durumKarti(
      "Veri alınamadı",
      hata.message,
      hata.durum === 409 && evrenIcin ? `python tools/tarama.py ${evrenIcin}` : null,
      true,
      hata.durum === 409 ? evrenIcin : null,
    );
  }
}

/* ═══════════════════════════════════════════════════════════ SKOR KARTI */

EKRANLAR.skor = async function (kap, sembol) {
  if (!sembol) { kap.innerHTML = karsilama(); return; }

  const [veri, rapor] = await Promise.all([
    API.al(`/api/sirket?sembol=${encodeURIComponent(sembol)}`),
    API.al(`/api/rapor?sembol=${encodeURIComponent(sembol)}`).catch(() => null),
  ]);

  kap.innerHTML = [
    sirketBasligi(veri),
    istatistikSeridi(veri),
    uyarilar(veri),
    ozetPaneli(veri),
    ikiSutun(fskorPaneli(veri), ceyrekPaneli(rapor)),
    metrikPaneli(veri),
    kalitePaneli(veri),
    reelGelirPaneli(veri),
  ].join("");
};

const ikiSutun = (sol, sag) =>
  sol && sag ? `<section class="iki">${sol}${sag}</section>`
    : sol || sag ? `<section>${sol || sag}</section>` : "";

function karsilama(baslik = "Bir şirket seç") {
  const ornekler = ["SISE.IS", "THYAO.IS", "AKBNK.IS", "ASELS.IS", "TUPRS.IS", "AAPL", "MSFT"];
  const izleme = izlemeListesi();
  return `<section><div class="durum">
      <h3>${kacir(baslik)}</h3>
      <p>Arama kutusuna sembol veya şirket adı yaz. Araç o şirketin son dört yıllık mali
         tablosunu okur, finansal sağlık kriterlerini hesaplar ve rakamların ne gösterdiğini
         anlatır — enflasyon sonrası reel değerlerle.</p>
      ${izleme.length ? `<p class="not" style="margin-top:18px;margin-bottom:8px">İzleme listen:</p>
        <div class="ornek-dugmeler">
          ${izleme.map((s) => `<button type="button" data-ornek="${kacir(s)}">★ ${kacir(s)}</button>`).join("")}
        </div>` : ""}
      <p class="not" style="margin-top:18px;margin-bottom:8px">Örnekler:</p>
      <div class="ornek-dugmeler">
        ${ornekler.map((s) => `<button type="button" data-ornek="${s}">${s}</button>`).join("")}
      </div>
    </div></section>`;
}

/* ═══════════════════════════════════════════════════════════ izleme listesi
 *
 * Sunucu tarafında hiçbir karşılığı yok — tamamen localStorage'da, tarayıcı
 * başına. Portföyden ayrı bir kavram: portföy gerçek işlemleri tutar, izleme
 * listesi yalnızca "bunu takip ediyorum" işareti.
 */

const IZLEME_ANAHTARI = "borsa_panel_izleme_listesi";

function izlemeListesi() {
  try {
    const ham = localStorage.getItem(IZLEME_ANAHTARI);
    const liste = ham ? JSON.parse(ham) : [];
    return Array.isArray(liste) ? liste : [];
  } catch {
    return [];
  }
}

function izlemedeMi(sembol) {
  return izlemeListesi().includes(sembol);
}

/** Ekler/çıkarır, yeni durumu (true = artık izleniyor) döner. */
function izlemeyeEkleCikar(sembol) {
  const liste = izlemeListesi();
  const index = liste.indexOf(sembol);
  if (index === -1) liste.push(sembol);
  else liste.splice(index, 1);
  try {
    localStorage.setItem(IZLEME_ANAHTARI, JSON.stringify(liste));
  } catch {
    /* localStorage kapalı/dolu olabilir — sessizce geç, kritik değil */
  }
  return index === -1;
}

function izlemeYildizi(sembol) {
  const aktif = izlemedeMi(sembol);
  return `<button type="button" class="izleme-yildiz${aktif ? " aktif" : ""}"
      data-izleme="${kacir(sembol)}"
      title="${aktif ? "İzleme listesinden çıkar" : "İzleme listesine ekle"}"
      aria-pressed="${aktif}">${aktif ? "★" : "☆"}</button>`;
}

function sirketBasligi(veri) {
  const p = veri.profil;
  const bas = (veri.symbol || "").replace(/\..*$/, "").slice(0, 2).toUpperCase();

  const rozetler = [];
  if (p.sektor) rozetler.push(`<span class="rozet">${kacir(p.sektor)}</span>`);
  if (p.endustri) rozetler.push(`<span class="rozet">${kacir(p.endustri)}</span>`);
  if (p.tablo_para) rozetler.push(`<span class="rozet">Tablolar ${kacir(p.tablo_para)}</span>`);

  // Dönem rozeti yaşı da taşır: "Dönem 2024-12-31" tek başına okuyana bir şey
  // söylemiyor, "19 ay önce" söylüyor. Bayatsa rozet uyarı rengine geçer.
  const taze = veri.saglik.freshness || {};
  if (taze.latest_period) {
    const bayat = taze.level === "bayat" || taze.level === "cok_bayat";
    rozetler.push(`<span class="rozet${bayat ? " rozet-uyari" : ""}">Dönem
      ${kacir(taze.latest_period)}${taze.label ? ` · ${kacir(taze.label)}` : ""}</span>`);
  } else if (veri.ozet.as_of) {
    rozetler.push(`<span class="rozet">Dönem ${kacir(veri.ozet.as_of)}</span>`);
  }
  if (veri.banka_muhasebesi) rozetler.push(`<span class="rozet rozet-uyari">${terim("banka_muhasebesi", "Banka muhasebesi")}</span>`);
  if (p.tablo_para && p.fiyat_para && p.tablo_para !== p.fiyat_para) {
    rozetler.push(`<span class="rozet rozet-uyari">Tablo ${kacir(p.tablo_para)} / fiyat ${kacir(p.fiyat_para)}</span>`);
  }

  const notlar = [];
  if (p.tablo_para && p.fiyat_para && p.tablo_para !== p.fiyat_para) {
    notlar.push(`Şirket tablolarını ${kacir(p.tablo_para)} açıklıyor, hissesi ${kacir(p.fiyat_para)}
      işlem görüyor. Oranlar ${kacir(p.tablo_para)} bazına çevrilerek hesaplandı.`);
  }
  if (p.piyasa_degeri_guvenilir === false && p.piyasa_degeri_notu) notlar.push(kacir(p.piyasa_degeri_notu));
  if (veri.banka_muhasebesi) {
    notlar.push(`Banka/finans şirketi: FAVÖK, brüt kâr, cari oran ve Altman Z bu sektörde
      tanımsız olduğu için hesaplanmadı.`);
  }

  return `<section>
    <div class="sirket">
      <div class="sirket-ikon">${kacir(bas)}</div>
      <div>
        <div class="sirket-kod">${kacir(veri.symbol)} ${izlemeYildizi(veri.symbol)}</div>
        <div class="sirket-ad">${kacir(p.ad || "")}</div>
        <div class="rozetler">${rozetler.join("")}</div>
      </div>
      <div class="sirket-fiyat">
        <b>${kacir(TR(p.fiyat, 2))} ${kacir(p.fiyat_para || "")}</b>
        <small>son kapanış</small>
        <small>piyasa değeri ${kacir(para(p.piyasa_degeri, p.fiyat_para || ""))}</small>
        <small><a class="baglanti-dugme" href="/api/llm-rapor?sembol=${encodeURIComponent(veri.symbol)}"
          target="_blank" rel="noopener">LLM raporu ↗</a></small>
      </div>
    </div>
    ${notlar.length ? `<div class="uyari-kart u-sari" style="margin-top:12px">
        ${notlar.map((n) => `<p style="margin-top:0">${n}</p>`).join("")}
      </div>` : ""}
  </section>`;
}

/** Üstteki hero şerit: reel büyüme birincil, değerleme ikincil. */
function istatistikSeridi(veri) {
  const rg = veri.saglik.real_growth || {};
  const val = veri.saglik.valuation || {};
  const debt = veri.saglik.debt || {};
  const fscore = veri.saglik.fscore || {};
  const baglam = new Map((veri.baglam || []).map((b) => [b.metric, b]));

  const kiyas = (metrik) => {
    const b = baglam.get(metrik);
    if (!b || !b.available || b.sector_median === null || b.sector_median === undefined) return "";
    return `sektör ${bicimle(metrik, b.sector_median)}`;
  };

  const kartlar = [];

  for (const [anahtar, etiketReel] of [
    ["revenue", "Gelir · reel"],
    ["net_income", "Net kâr · reel"],
  ]) {
    const d = rg[anahtar];
    if (!d) continue;
    const [govde, tur] = etiketReel.split(" · ");  // "Gelir · reel" -> ["Gelir", "reel"]
    if (d.real === null || d.real === undefined) {
      kartlar.push(`<div class="serit-kart">
          <div class="serit-etiket">${kacir(govde)} · ${terim("nominal", "nominal")}</div>
          <div class="serit-deger buyuk ${isaretRengi(d.nominal)}">${kacir(yuzde(d.nominal))}</div>
          <div class="serit-alt">reel karşılığı hesaplanamadı</div>
          <div class="serit-kaynak">${kacir(d.detail || "Dönemi kapsayan TÜFE verisi yok")}</div>
        </div>`);
    } else {
      kartlar.push(`<div class="serit-kart">
          <div class="serit-etiket">${kacir(govde)} · ${terim("reel", tur)}</div>
          <div class="serit-deger buyuk ${isaretRengi(d.real)}">${kacir(yuzde(d.real))}</div>
          <div class="serit-alt">${terim("nominal", "nominal")} ${kacir(yuzde(d.nominal))} ·
            ${terim("tufe", "enflasyon")} ${kacir(yuzde(d.cpi_growth, false))}</div>
          <div class="serit-kaynak">${kacir(d.label || "")}</div>
        </div>`);
    }
  }

  const son = fscore.latest;
  if (son) {
    kartlar.push(`<div class="serit-kart">
        <div class="serit-etiket">${terim("fscore", "F-Skoru")}</div>
        <div class="serit-deger">${son.score} <span class="gri" style="font-size:16px">/ 9</span></div>
        <div class="serit-alt">${kacir(kiyas("fscore") || son.label)}</div>
      </div>`);
  }

  for (const [metrik, etiket, node] of [
    ["pe", "F/K", val.pe],
    ["pb", "PD/DD", val.pb],
    ["net_debt_ebitda", "Net borç/FAVÖK", debt.net_debt_ebitda],
  ]) {
    if (!node) continue;
    if (node.status !== "ok" || node.value === null || node.value === undefined) {
      kartlar.push(`<div class="serit-kart">
          <div class="serit-etiket">${terim(metrik, etiket)}</div>
          <div class="serit-deger gri" style="font-size:20px">—</div>
          <div class="serit-alt">${kacir(node.detail || "hesaplanamadı")}</div>
        </div>`);
      continue;
    }
    const b = baglam.get(metrik);
    const ustunde = b && b.sector_median !== null && b.sector_median !== undefined
      && node.value > b.sector_median;
    kartlar.push(`<div class="serit-kart">
        <div class="serit-etiket">${terim(metrik, etiket)}</div>
        <div class="serit-deger ${metrik === "net_debt_ebitda" && ustunde ? "kirmizi" : ""}"
          >${kacir(bicimle(metrik, node.value))}</div>
        <div class="serit-alt">${kacir(kiyas(metrik) || node.basis || "")}</div>
      </div>`);
  }

  if (!kartlar.length) return "";
  return `<section><div class="serit">${kartlar.join("")}</div></section>`;
}

function uyarilar(veri) {
  const b = veri.bayraklar;
  const siniflar = { kirmizi: "u-kirmizi", sari: "u-sari", bilgi: "u-bilgi" };
  const turler = { kirmizi: "Kırmızı", sari: "Sarı", bilgi: "Bilgi" };

  const ciz = (bayrak) => `<div class="uyari-kart ${siniflar[bayrak.level] || "u-bilgi"}">
      <div class="bas">
        <span class="tur">${turler[bayrak.level] || kacir(bayrak.level)}</span>
        <span>${kacir(bayrak.title)}${bayrak.approximate ? " · yaklaşık hesap" : ""}</span>
      </div>
      <p>${kacir(bayrak.explanation || "")}</p>
      <div class="kaynak">${kacir(bayrak.id)}${bayrak.sources && bayrak.sources.length
        ? " · " + bayrak.sources.slice(0, 3).map((k) =>
            `${kacir(k.item)}@${kacir(k.period || "—")}`).join(", ")
        : ""}</div>
    </div>`;

  const uyari = (b.flags || []).map(ciz).join("");
  const notlar = (b.notes || []).map(ciz).join("");

  return `<section>
    <div class="panel">
      <div class="panel-bas">Uyarılar
        <small>${b.red_count} kırmızı · ${b.yellow_count} sarı${
          (b.notes || []).length ? ` · ${b.notes.length} bilgi notu` : ""}</small>
      </div>
      <div class="panel-ic">
        ${uyari || notlar
          ? uyari + notlar
          : `<p class="not">Tanımlı kurallardan hiçbiri tetiklenmedi.</p>`}
        <p class="not" style="margin-top:12px">${kacir(b.legend)}</p>
        ${(b.not_applied || []).length ? `<details>
            <summary>Çalıştırılmayan kurallar (${b.not_applied.length})</summary>
            <ul>${b.not_applied.map((k) =>
              `<li><span class="mono">${kacir(k.id)}</span> — ${kacir(k.skip_reason || "")}</li>`).join("")}</ul>
          </details>` : ""}
      </div>
    </div>
  </section>`;
}

function ozetPaneli(veri) {
  const cumleler = veri.ozet.sentences || [];
  if (!cumleler.length) return "";
  const dq = veri.ozet.data_quality || {};
  return `<section>
    <div class="panel">
      <div class="panel-bas">Rakamlar ne diyor <small>kural tabanlı özet</small></div>
      <div class="panel-ic">
        ${cumleler.map((c) => `<div class="cumle">
            ${kacir(c.text).replace(/reel olarak (%[\d.,]+ (?:küçüldü|büyüdü))/,
              '<mark>reel olarak $1</mark>')}
            <div class="kaynak">${kacir(c.rule_id)}${c.sources && c.sources.length
              ? " · " + c.sources.slice(0, 3).map((k) =>
                  `${kacir(k.item)}@${kacir(k.period || "—")}`).join(", ")
              : ""}</div>
          </div>`).join("")}
      </div>
      <div class="panel-dip">
        <span class="not">Para birimi doğrulandı: ${dq.currency_verified ? "evet" : "hayır"} ·
          TÜFE serisi: ${dq.cpi_available ? "var" : "yok"} ·
          kaynakta eksik kalem: ${(dq.missing_items || []).length}</span>
      </div>
    </div>
  </section>`;
}

function fskorPaneli(veri) {
  const f = veri.saglik.fscore;
  if (!f || !f.points || !f.points.length) return "";
  const son = f.latest;

  // F-Skoru yıllık tablodan gelir; o tablo eskiyse skorun hangi tarihe ait
  // olduğunu panelin içinde söylemek gerekiyor — rozet kaydırılınca görünmez.
  const taze = veri.saglik.freshness || {};
  const yasNotu = taze.annual_stale && taze.last_annual
    ? `Bu skor <b>${kacir(taze.last_annual)}</b> yıllık tablosundan hesaplandı
       (${kacir(taze.label || "")}); bugünkü durumu değil o dönemi anlatıyor.`
    : "";

  const isaretler = {
    ok: (k) => k.passed ? ["i-gecti", "✓"] : ["i-kaldi", "✗"],
    eksik_veri: () => ["i-eksik", "?"],
    sektorde_gecersiz: () => ["i-na", "–"],
  };

  const oran = son ? (son.score / 9) * 100 : 0;
  const renk = son && son.score >= 7 ? "var(--yesil)" : son && son.score >= 4 ? "var(--sari)" : "var(--kirmizi)";

  const gecmis = f.points.map((n) =>
    `${n.date.slice(0, 4)}: ${n.usable ? n.score + "/9" : "—"}`).join("  →  ");

  return `<div class="panel">
    <div class="panel-bas">Piotroski F-Skoru
      <small>${son ? kacir(son.date) : ""}</small></div>
    <div class="panel-ic">
      ${f.model_note ? `<p class="not" style="margin-bottom:14px">${kacir(f.model_note)}</p>` : ""}
      ${yasNotu ? `<p class="not" style="margin-bottom:14px">${yasNotu}</p>` : ""}
      <div class="skor-duzen">
        ${son ? `<div class="skor-cember"
            style="background:conic-gradient(${renk} 0 ${oran}%, var(--cizgi) ${oran}% 100%)">
            <div class="skor-ic"><b>${son.score}/9</b><span>F-Skoru</span></div>
          </div>` : ""}
        <div class="kriter-liste">
          ${son ? son.criteria.map((k) => {
            const [sinif, im] = (isaretler[k.status] || isaretler.eksik_veri)(k);
            return `<div class="kriter">
                <span class="isaret ${sinif}">${im}</span>
                <span>${terim(k.id, k.label)}</span>
                <span class="detay">${kacir(k.detail || "")}</span>
              </div>`;
          }).join("") : ""}
        </div>
      </div>
    </div>
    <div class="panel-dip">
      <span class="not">${kacir(gecmis)} · ${kacir(f.note)}</span>
    </div>
  </div>`;
}

/* Çeyreklik kalem anahtarı -> sözlük terimi. Sözlükte karşılığı olmayan
 * kalemler (Gelir, Net kâr, Toplam borç) düz etikete düşer. */
const KALEM_TERIM = {
  GrossProfit: "brut_kar",
  OperatingIncome: "faaliyet_kari",
  EBITDA: "favok",
  OperatingCashFlow: "faaliyet_nakit_akisi",
  FreeCashFlow: "serbest_nakit_akisi",
  NetDebt: "net_borc",
  StockholdersEquity: "ozsermaye",
};

const kalemEtiketi = (s) =>
  KALEM_TERIM[s.key] ? terim(KALEM_TERIM[s.key], s.label) : kacir(s.label);

function ceyrekPaneli(rapor) {
  if (!rapor) return "";
  const c = rapor.quarterly;
  if (!c || !c.available) return "";

  const degisim = (d) => {
    if (!d || d.pct === null || d.pct === undefined) {
      return d && d.note ? `<span class="na">${kacir(d.note)}</span>` : "—";
    }
    return `<span class="${isaretRengi(d.pct)}">${kacir(yuzde(d.pct))}</span>`;
  };

  return `<div class="panel">
    <div class="panel-bas">Son çeyrek
      <small>${kacir(c.current_date)}${c.compare_date ? ` vs ${kacir(c.compare_date)}` : ""}</small></div>
    <div class="kaydir">
      <table>
        <thead><tr><th class="metin">Kalem</th><th>Tutar</th><th>Yıllık</th></tr></thead>
        <tbody>${c.lines.slice(0, 7).map((s) => `<tr>
            <td class="metin">${kalemEtiketi(s)}</td>
            <td>${kacir(para(s.value, rapor.currency || ""))}</td>
            <td>${degisim(s.yoy)}</td>
          </tr>`).join("")}</tbody>
      </table>
    </div>
    ${(c.comments || []).length ? `<div class="panel-ic">
        ${c.comments.slice(0, 3).map((y) => `<div class="cumle">
            ${kacir(y.text).replace(/\*\*(.+?)\*\*/g, "<mark>$1</mark>")}
            <div class="kaynak">${kacir(y.rule_id)}</div>
          </div>`).join("")}
      </div>` : ""}
  </div>`;
}

function metrikPaneli(veri) {
  if (!veri.baglam_var) {
    return `<section>${durumKarti(
      "Sektör bağlamı için tarama gerekli",
      "Sektör medyanı ve yüzdelik dilim, evrenin taranmasını gerektiriyor. Tarama bir kez " +
        "yapılır ve 7 gün geçerlidir.",
      `python tools/tarama.py ${veri.market}`,
    ).replace(/^<section>|<\/section>$/g, "")}</section>`;
  }

  const satirlar = veri.baglam.map((item) => {
    if (item.not_applicable) {
      return `<tr><td class="metin">${terim(item.metric, item.label)}</td>
        <td colspan="6" class="na" style="text-align:left">bu sektörde tanımsız</td></tr>`;
    }
    if (!item.available) return "";
    const yon = (item.trend || {}).direction;
    const sp = item.sector_percentile, up = item.universe_percentile;
    const tavanli = item.metric === "altman_z" && item.value > ALTMAN_TAVAN;
    return `<tr>
        <td class="metin">${terim(item.metric, item.label)}</td>
        <td${tavanli ? ` title="tam değer: ${kacir(TR(item.value, 2))}"` : ""}
          >${kacir(bicimle(item.metric, item.value))}</td>
        <td>${yon ? `<span class="etiket ${yonSinifi(yon)}">${kacir(yon)}</span>`
          : `<span class="etiket e-yatay">—</span>`}</td>
        <td>${kacir(bicimle(item.metric, item.sector_median))}</td>
        <td>${sp === null || sp === undefined
          ? `<span class="na">${kacir(item.sector_note || "örneklem yetersiz")}</span>`
          : `<span class="ray" title="şirket %${Math.round(sp)} · sektör medyanı %50">
               <i style="left:${Math.min(98, Math.max(2, sp))}%"></i><u style="left:50%"></u>
             </span>`}</td>
        <td>${sp === null || sp === undefined ? "—" : Math.round(sp)}</td>
        <td>${up === null || up === undefined ? "—" : Math.round(up)}</td>
      </tr>`;
  }).join("");

  return `<section>
    <div class="panel">
      <div class="panel-bas">Metrikler ve sektör bağlamı
        <small>${kacir((DURUM?.evrenler || []).find((e) => e.id === veri.market)?.label || "")} ·
          ${(DURUM?.evrenler || []).find((e) => e.id === veri.market)?.taranan || "?"} şirket</small></div>
      <div class="kaydir">
        <table>
          <thead><tr>
            <th class="metin">Metrik</th><th>Değer</th><th>Kendi trendi</th>
            <th>${terim("sektor_medyani", "Sektör medyanı")}</th><th>Konum</th>
            <th>${terim("yuzdelik_dilim", "Sektör %")}</th>
            <th>${terim("yuzdelik_dilim", "Evren %")}</th>
          </tr></thead>
          <tbody>${satirlar}</tbody>
        </table>
      </div>
      <div class="panel-dip">
        <div class="aciklama">
          <span><i class="nokta" style="background:var(--metin);border-radius:50%"></i> şirketin konumu</span>
          <span><i class="nokta" style="background:var(--vurgu);width:3px;height:11px;border-radius:1px"></i> sektör medyanı</span>
        </div>
        <p class="not" style="margin-top:6px">Yüzdelik dilim bir yargı değildir — yalnızca şirketin
          nerede durduğunu gösterir; hangi yönün iyi olduğu metriğe ve amaca göre değişir.
          Altman Z'de ${ALTMAN_TAVAN} üstü "${ALTMAN_TAVAN}+" gösterilir: model 2,99'un üstünü
          tek bir "güvenli bölge" sayar, bu eşiğin çok ötesindeki farklar (ör. borcu neredeyse
          sıfır bir şirkette 5 ile 60 arası) anlam taşımaz.</p>
      </div>
    </div>
  </section>`;
}

function kalitePaneli(veri) {
  const s = veri.saglik;
  const marjlar = (s.margins && s.margins.series) || {};
  const cevir = (dizi) => (dizi || []).map(([tarih, deger]) => ({ tarih, deger }));

  const cizim = seritGrafik([
    {
      ad: "F-Skoru", renk: "var(--vurgu)", bicim: (d) => `${d}/9`, aralikMetni: "0–9 arası",
      noktalar: (s.fscore.usable_points || []).map((n) => ({ tarih: n.date, deger: n.score })),
    },
    { ad: "Faaliyet marjı", renk: "var(--kirmizi)", bicim: puan, noktalar: cevir(marjlar.operating) },
    { ad: "Brüt marj", renk: "var(--yesil)", bicim: puan, noktalar: cevir(marjlar.gross) },
    {
      ad: "Net borç/FAVÖK", renk: "var(--sari)", bicim: (d) => TR(d, 2),
      noktalar: (s.debt.history || []).map((r) => ({ tarih: r.date, deger: r.net_debt_ebitda })),
    },
  ]);

  if (!cizim) return "";
  return `<section>
    <div class="panel">
      <div class="panel-bas">Kalite trendi <small>dönem dönem seyir</small></div>
      <div class="panel-ic">${cizim}</div>
      <div class="panel-dip">
        <p class="not">Her seri kendi ölçeğinde, ortak zaman ekseninde; solda serinin adı ve değer
          aralığı yazılı. Farklı birimdeki serileri tek eksene bindirmek çizgilerin kesişmesine
          anlam yükletirdi.${s.fscore.note ? " " + kacir(s.fscore.note) : ""}</p>
      </div>
    </div>
  </section>`;
}

function reelGelirPaneli(veri) {
  const seri = (veri.saglik.real_growth || {}).real_revenue_series;
  if (!seri || !seri.points || seri.points.length < 2) return "";
  const noktalar = seri.points.map(([tarih, deger]) => ({ tarih, deger }));
  return `<section>
    <div class="panel">
      <div class="panel-bas">Gelir · bugünün parasıyla
        <small>${kacir(seri.label || "")} · taban ${kacir(seri.base || "")}</small></div>
      <div class="panel-ic">${sutunGrafik(noktalar, veri.saglik.currency || "")}</div>
      <div class="panel-dip">
        <p class="not">Nominal rakamlar enflasyondan arındırılıp aynı alım gücüne
          çevrildi${(seri.skipped || []).length
            ? `; TÜFE verisi olmayan ${seri.skipped.length} dönem atlandı` : ""}.
          ${kacir(seri.basis || "")}</p>
      </div>
    </div>
  </section>`;
}

/* ═══════════════════════════════════════════════════════════ KARŞILAŞTIR */

const KARS_MAKS = 3;

// context.py'nin METRIKLER sabitiyle aynı sıra — sunucu veri.baglam'ı bu
// sırada döndürüyor, burada yalnızca satır sırasını sabitlemek için
// anahtarlar tekrarlanıyor (etiketler sunucudan geliyor, burada değil).
const KARS_METRIK_SIRASI = [
  "fscore", "altman_z", "roe", "roa", "gross_margin", "operating_margin",
  "net_margin", "net_debt_ebitda", "debt_to_equity", "interest_coverage",
  "fcf_gap", "real_revenue_growth", "real_income_growth", "pe", "pb", "dividend_yield",
];

function karsilamaKarsilastir() {
  const ciftler = [["SISE.IS", "EREGL.IS"], ["AKBNK.IS", "GARAN.IS"], ["AAPL", "MSFT"]];
  return `<section><div class="durum">
      <h3>İki veya üç şirketi yan yana koy</h3>
      <p>Arama kutusundan bir şirket daha aratıp öneriler listesinden seçince
         karşılaştırmaya eklenir (en çok ${KARS_MAKS} şirket). Aynı sektörden ya da
         birbirine rakip iki şirketle başlamak en anlamlısı.</p>
      <div class="ornek-dugmeler">
        ${ciftler.map(([a, b]) =>
          `<button type="button" data-ornek-cift="${a},${b}">${a} · ${b}</button>`).join("")}
      </div>
    </div></section>`;
}

EKRANLAR.karsilastir = async function (kap, sembol) {
  const semboller = [...new Set((sembol || "").split(",").map((s) => s.trim()).filter(Boolean))]
    .slice(0, KARS_MAKS);
  if (!semboller.length) { kap.innerHTML = karsilamaKarsilastir(); return; }

  const sonuclar = await Promise.all(semboller.map((s) =>
    API.al(`/api/sirket?sembol=${encodeURIComponent(s)}`)
      .then((veri) => ({ ok: true, symbol: s, veri }))
      .catch((hata) => ({ ok: false, symbol: s, hata: hata.message }))));

  const basarili = sonuclar.filter((s) => s.ok);

  kap.innerHTML = [
    karsBasliklar(sonuclar),
    karsDonemUyarisi(basarili),
    basarili.length ? karsBuyumeKartlari(basarili) : "",
    basarili.length ? karsMetrikTablosu(basarili) : "",
    basarili.length ? karsFskorMatrisi(basarili) : "",
    basarili.length ? karsKaliteTrendi(basarili) : "",
  ].join("");

  kap.querySelectorAll("button[data-kaldir]").forEach((b) =>
    b.addEventListener("click", () => {
      const kalan = semboller.filter((s) => s !== b.dataset.kaldir);
      git("karsilastir", kalan.join(","));
    }));
};

function karsBasliklar(sonuclar) {
  const kartlar = sonuclar.map((s) => {
    if (!s.ok) {
      return `<div class="kars-kart">
          <button class="kars-kaldir" data-kaldir="${kacir(s.symbol)}" title="Karşılaştırmadan çıkar">✕</button>
          <div class="sirket-kod">${kacir(s.symbol)}</div>
          <p class="not" style="margin-top:8px">Veri alınamadı: ${kacir(s.hata)}</p>
        </div>`;
    }
    const p = s.veri.profil;
    const taze = s.veri.saglik.freshness || {};
    const bayat = taze.level === "bayat" || taze.level === "cok_bayat";
    return `<div class="kars-kart">
        <button class="kars-kaldir" data-kaldir="${kacir(s.symbol)}" title="Karşılaştırmadan çıkar">✕</button>
        <div class="sirket-kod">${kacir(s.symbol)}</div>
        <div class="sirket-ad">${kacir(p.ad || "")}</div>
        <div class="rozetler">
          ${p.sektor ? `<span class="rozet">${kacir(p.sektor)}</span>` : ""}
          ${p.tablo_para ? `<span class="rozet">${kacir(p.tablo_para)}</span>` : ""}
          ${taze.latest_period ? `<span class="rozet${bayat ? " rozet-uyari" : ""}">
              Dönem ${kacir(taze.latest_period)}${taze.label ? ` · ${kacir(taze.label)}` : ""}</span>` : ""}
        </div>
        <div style="margin-top:12px"><b class="mono" style="font-size:19px"
          >${kacir(TR(p.fiyat, 2))} ${kacir(p.fiyat_para || "")}</b></div>
      </div>`;
  });

  if (sonuclar.length < KARS_MAKS) {
    kartlar.push(`<div class="kars-ekle">Arama kutusundan bir şirket daha ekle
      (${sonuclar.length}/${KARS_MAKS})</div>`);
  }

  return `<section><div class="kars-grid">${kartlar.join("")}</div></section>`;
}

/** As-of tarihleri arasında fark varsa açıkça uyarır — Faz 1'in tazelik
 * verisini kullanır. NETCD/DOCO karşılaştırmasının elle yapıldığı ilk turda
 * bu uyarı yoktu; iki tablo farklı dönemleri anlatırken kullanıcı ikisini
 * aynı "şimdi" gibi okuyordu. */
function karsDonemUyarisi(basarili) {
  if (basarili.length < 2) return "";
  const donemler = basarili
    .map((s) => ({ symbol: s.symbol, taze: s.veri.saglik.freshness || {} }))
    .filter((d) => d.taze.latest_period);
  if (donemler.length < 2) return "";

  const tarihler = donemler.map((d) => new Date(d.taze.latest_period).getTime());
  const farkGun = (Math.max(...tarihler) - Math.min(...tarihler)) / 86400000;
  const biriBayat = donemler.some((d) => d.taze.level === "bayat" || d.taze.level === "cok_bayat");

  // Farklı mali yıl sonu: dönem tarihlerinin ayı şirketten şirkete değişiyorsa
  // (ör. Aralık'a karşı Mart) aynı takvim dönemini anlatmıyorlar demektir.
  const aylar = new Set(donemler.map((d) => d.taze.latest_period.slice(5, 7)));

  if (farkGun <= 183 && !biriBayat && aylar.size <= 1) return "";

  const parcalar = [];
  parcalar.push(donemler.map((d) =>
    `${kacir(d.symbol)}: ${kacir(d.taze.latest_period)}${d.taze.label ? ` (${kacir(d.taze.label)})` : ""}`
  ).join(" · "));
  if (aylar.size > 1) {
    parcalar.push("Şirketlerin mali yıl sonu farklı ayda bitiyor; tablolar aynı takvim dönemini kapsamıyor.");
  }
  if (biriBayat) {
    parcalar.push("En az bir şirketin son tablosu eski; o şirketteki metrikler bugünkü durumu yansıtmıyor olabilir.");
  }

  return `<section><div class="uyari-kart u-sari">
      <div class="bas"><span class="tur">Dikkat</span><span>Bu şirketlerin tabloları aynı dönemi anlatmıyor</span></div>
      <p>${parcalar.join(" ")}</p>
    </div></section>`;
}

function karsBuyumeKartlari(basarili) {
  const satir = (baslik, anahtar) => {
    const hucreler = basarili.map((s) => {
      const d = (s.veri.saglik.real_growth || {})[anahtar];
      if (!d) return `<td>—</td>`;
      if (d.real === null || d.real === undefined) {
        return `<td class="deger ${isaretRengi(d.nominal)}">${kacir(yuzde(d.nominal))}
          <span class="alt-not">nominal</span></td>`;
      }
      return `<td class="deger ${isaretRengi(d.real)}">${kacir(yuzde(d.real))}
        <span class="alt-not">nominal ${kacir(yuzde(d.nominal))}</span></td>`;
    });
    return `<tr><td class="metin">${kacir(baslik)}</td>${hucreler.join("")}</tr>`;
  };

  const fskorSatir = `<tr><td class="metin">F-Skoru</td>${basarili.map((s) => {
    const son = (s.veri.saglik.fscore || {}).latest;
    return `<td class="deger">${son ? `${kacir(son.score)}/9` : "—"}</td>`;
  }).join("")}</tr>`;

  return `<section><div class="panel">
      <div class="panel-bas">Büyüme ve skor <small>reel varsa reel, yoksa nominal gösterilir</small></div>
      <div class="kaydir"><table class="kars-tablo">
        <thead><tr><th class="metin">Metrik</th>
          ${basarili.map((s) => `<th>${kacir(s.symbol)}</th>`).join("")}</tr></thead>
        <tbody>
          ${satir("Gelir", "revenue")}
          ${satir("Net kâr", "net_income")}
          ${fskorSatir}
        </tbody>
      </table></div>
    </div></section>`;
}

function karsMetrikTablosu(basarili) {
  // Her şirketin veri.baglam'ı context.py'nin METRIKLER sırasında, sabit
  // 16 elemanlı geliyor (uygulanamaz olanlar da dahil) — anahtara göre harita
  // kurmak, bir şirketin bağlamı hiç gelmediğinde (baglam_var=false) diğerlerini
  // bozmadan "—" basmaya izin veriyor.
  const haritalar = basarili.map((s) => new Map((s.veri.baglam || []).map((b) => [b.metric, b])));
  const etiketler = new Map();
  haritalar.forEach((h) => h.forEach((b, metrik) => { if (!etiketler.has(metrik)) etiketler.set(metrik, b.label); }));

  const satirlar = KARS_METRIK_SIRASI
    .filter((m) => etiketler.has(m))
    .map((metrik) => {
      const hucreler = haritalar.map((harita) => {
        const item = harita.get(metrik);
        if (!item) return `<td>—</td>`;
        if (item.not_applicable) return `<td class="na">sektörde tanımsız</td>`;
        if (!item.available) return `<td>—</td>`;
        const sp = item.sector_percentile;
        return `<td class="deger">${kacir(bicimle(metrik, item.value))}
          ${sp === null || sp === undefined ? "" : `<span class="alt-not">sektör %${Math.round(sp)}</span>`}</td>`;
      });
      return `<tr><td class="metin">${terim(metrik, etiketler.get(metrik))}</td>${hucreler.join("")}</tr>`;
    }).join("");

  if (!satirlar) return "";
  return `<section><div class="panel">
      <div class="panel-bas">Metrikler <small>değer + sektör yüzdeliği</small></div>
      <div class="kaydir"><table class="kars-tablo">
        <thead><tr><th class="metin">Metrik</th>
          ${basarili.map((s) => `<th>${kacir(s.symbol)}</th>`).join("")}</tr></thead>
        <tbody>${satirlar}</tbody>
      </table></div>
      <div class="panel-dip"><p class="not">Sektör yüzdeliği bir yargı değil, yalnızca konum
        bilgisi — hangi yönün iyi olduğu metriğe göre değişir.</p></div>
    </div></section>`;
}

function karsFskorMatrisi(basarili) {
  const canonical = basarili.map((s) => (s.veri.saglik.fscore || {}).latest).find((f) => f && f.criteria);
  if (!canonical) return "";

  const isaretler = {
    ok: (k) => k.passed ? ["i-gecti", "✓"] : ["i-kaldi", "✗"],
    eksik_veri: () => ["i-eksik", "?"],
    sektorde_gecersiz: () => ["i-na", "–"],
  };

  const satirlar = canonical.criteria.map((kriter) => {
    const hucreler = basarili.map((s) => {
      const son = (s.veri.saglik.fscore || {}).latest;
      const k = son && son.criteria.find((c) => c.id === kriter.id);
      if (!k) return `<td>—</td>`;
      const [sinif, im] = (isaretler[k.status] || isaretler.eksik_veri)(k);
      return `<td class="isaret ${sinif}" style="text-align:center">${im}</td>`;
    });
    return `<tr><td class="metin">${terim(kriter.id, kriter.label)}</td>${hucreler.join("")}</tr>`;
  }).join("");

  return `<section><div class="panel">
      <div class="panel-bas">F-Skoru kriter kriter</div>
      <div class="kaydir"><table class="kars-tablo">
        <thead><tr><th class="metin">Kriter</th>
          ${basarili.map((s) => `<th>${kacir(s.symbol)}</th>`).join("")}</tr></thead>
        <tbody>${satirlar}</tbody>
      </table></div>
      <div class="panel-dip"><p class="not">✓ geçti · ✗ kalmadı · ? veri yok · – bu sektörde tanımsız</p></div>
    </div></section>`;
}

/** Her şirketin kalite trendini (F-Skoru, marjlar, net borç/FAVÖK) yan yana
 * çizer. Ek bir ağ isteği gerekmiyor — `/api/sirket` zaten çekilirken gelen
 * `saglik` alanı `kalitePaneli()`'nin (tekil şirket ekranı) kullandığı aynı
 * seriler; burada yalnızca daha dar bir genişlikte, kars-grid içinde çiziliyor. */
function karsKaliteTrendi(basarili) {
  const kartlar = basarili.map((s) => {
    const st = s.veri.saglik;
    const marjlar = (st.margins && st.margins.series) || {};
    const cevir = (dizi) => (dizi || []).map(([tarih, deger]) => ({ tarih, deger }));

    const cizim = seritGrafik([
      {
        ad: "F-Skoru", renk: "var(--vurgu)", bicim: (d) => `${d}/9`, aralikMetni: "0–9 arası",
        noktalar: (st.fscore.usable_points || []).map((n) => ({ tarih: n.date, deger: n.score })),
      },
      { ad: "Faaliyet marjı", renk: "var(--kirmizi)", bicim: puan, noktalar: cevir(marjlar.operating) },
      { ad: "Brüt marj", renk: "var(--yesil)", bicim: puan, noktalar: cevir(marjlar.gross) },
      {
        ad: "Net borç/FAVÖK", renk: "var(--sari)", bicim: (d) => TR(d, 2),
        noktalar: (st.debt.history || []).map((r) => ({ tarih: r.date, deger: r.net_debt_ebitda })),
      },
    ], 360);

    return `<div class="panel">
        <div class="panel-bas">${kacir(s.symbol)} <small>kalite trendi</small></div>
        <div class="panel-ic">${cizim || `<p class="not">Yeterli geçmiş dönem yok.</p>`}</div>
      </div>`;
  });

  return `<section>
      <div class="kars-grid">${kartlar.join("")}</div>
      <p class="not" style="margin-top:8px">Her seri kendi ölçeğinde, ortak zaman ekseninde —
        bkz. tekil şirket ekranındaki kalite trendi paneli.</p>
    </section>`;
}

/* ═══════════════════════════════════════════════════════ RAPOR OKUYUCU */

let RAPOR_DONEM = "quarterly";

EKRANLAR.rapor = async function (kap, sembol) {
  if (!sembol) { kap.innerHTML = karsilama("Rapor okuyucu için bir şirket seç"); return; }
  const veri = await API.al(`/api/rapor?sembol=${encodeURIComponent(sembol)}`);
  kap.dataset.sembol = sembol;
  ciz();

  function ciz() {
    const d = veri[RAPOR_DONEM];
    kap.innerHTML = `
      <section>
        <div class="panel">
          <div class="panel-bas">
            <span>${kacir(veri.symbol)} · rapor karşılaştırması</span>
            <small>${kacir(veri.currency || "")}${veri.bank_accounting ? " · banka muhasebesi" : ""}</small>
          </div>
          <div class="panel-ic">
            <div class="cipler">
              <button class="cip" type="button" data-donem="quarterly"
                aria-pressed="${RAPOR_DONEM === "quarterly"}">Çeyreklik
                <small>geçen yılın aynı çeyreğiyle</small></button>
              <button class="cip" type="button" data-donem="annual"
                aria-pressed="${RAPOR_DONEM === "annual"}">Yıllık
                <small>bir önceki mali yılla</small></button>
            </div>
          </div>
        </div>
      </section>
      ${d && d.available ? raporGovde(d, veri) : durumKarti(
        "Bu dönem için karşılaştırma yok",
        (d && d.reason) || "Kaynakta yeterli dönem bulunmuyor.",
        null,
      )}`;

    kap.querySelectorAll("button[data-donem]").forEach((b) =>
      b.addEventListener("click", () => { RAPOR_DONEM = b.dataset.donem; ciz(); }));
  }
};

function raporGovde(d, veri) {
  const degisim = (x) => {
    if (!x || x.pct === null || x.pct === undefined) {
      return x && x.note ? `<span class="na">${kacir(x.note)}</span>` : "—";
    }
    return `<span class="${isaretRengi(x.pct)}">${kacir(yuzde(x.pct))}</span>`;
  };

  const marjSatirlari = Object.values(d.margins || {}).map((m) => `<tr>
      <td class="metin">${kacir(m.label)}</td>
      <td>${kacir(puan(m.now))}</td>
      <td>${kacir(puan(m.before))}</td>
      <td>${m.delta === null || m.delta === undefined ? "—"
        : `<span class="${isaretRengi(m.delta)}">${kacir(TR(m.delta, 1))} puan</span>`}</td>
    </tr>`).join("");

  const rr = d.real_revenue;

  return `
    ${rr && rr.real !== null && rr.real !== undefined ? `<section><div class="serit">
        <div class="serit-kart">
          <div class="serit-etiket">Gelir · reel değişim</div>
          <div class="serit-deger buyuk ${isaretRengi(rr.real)}">${kacir(yuzde(rr.real))}</div>
          <div class="serit-alt">nominal ${kacir(yuzde(rr.nominal))} ·
            enflasyon ${kacir(yuzde(rr.cpi_growth, false))}</div>
          <div class="serit-kaynak">${kacir(rr.label || "")} · ${kacir(rr.basis || "")}</div>
        </div>
      </div></section>` : ""}

    <section>
      <div class="panel">
        <div class="panel-bas">Kalemler
          <small>${kacir(d.current_date)}${d.compare_date ? ` vs ${kacir(d.compare_date)}` : ""}</small></div>
        <div class="kaydir">
          <table>
            <thead><tr><th class="metin">Kalem</th><th>Tutar</th>
              <th>${d.period === "quarterly" ? "Yıllık (YoY)" : "Önceki yıl"}</th>
              ${d.period === "quarterly" ? "<th>Çeyreklik (QoQ)</th>" : ""}</tr></thead>
            <tbody>${d.lines.map((s) => `<tr>
                <td class="metin">${kacir(s.label)}</td>
                <td>${kacir(para(s.value, veri.currency || ""))}</td>
                <td>${degisim(s.yoy)}</td>
                ${d.period === "quarterly" ? `<td>${degisim(s.qoq)}</td>` : ""}
              </tr>`).join("")}</tbody>
          </table>
        </div>
      </div>
    </section>

    ${marjSatirlari ? `<section><div class="panel">
        <div class="panel-bas">Marjlar <small>dönem karşılaştırması</small></div>
        <div class="kaydir"><table>
          <thead><tr><th class="metin">Marj</th><th>Bu dönem</th><th>Karşılaştırma</th><th>Fark</th></tr></thead>
          <tbody>${marjSatirlari}</tbody>
        </table></div>
      </div></section>` : ""}

    ${(d.comments || []).length ? `<section><div class="panel">
        <div class="panel-bas">Rakamlar ne diyor <small>kural tabanlı yorum</small></div>
        <div class="panel-ic">
          ${d.comments.map((y) => `<div class="cumle">
              ${kacir(y.text).replace(/\*\*(.+?)\*\*/g, "<mark>$1</mark>")}
              <div class="kaynak">${kacir(y.rule_id)}${y.sources && y.sources.length
                ? " · " + y.sources.slice(0, 3).map((k) =>
                    `${kacir(k.item)}@${kacir(k.period || "—")}`).join(", ")
                : ""}</div>
            </div>`).join("")}
        </div>
      </div></section>` : ""}`;
}

/* ════════════════════════════════════════════════════════ KALİTE TRENDİ */

EKRANLAR.kalite = async function (kap, sembol) {
  if (!sembol) { kap.innerHTML = karsilama("Kalite trendi için bir şirket seç"); return; }
  const d = await API.al(`/api/kalite?sembol=${encodeURIComponent(sembol)}`);

  const cevir = (dizi) => (dizi || []).map(([tarih, deger]) => ({ tarih, deger }));
  const noktaCevir = (dizi) => (dizi || []).map((n) => ({ tarih: n.date, deger: n.value }));

  const cizim = seritGrafik([
    { ad: "F-Skoru", renk: "var(--vurgu)", bicim: (v) => `${v}/9`, aralikMetni: "0–9 arası",
      noktalar: noktaCevir(d.fscore) },
    { ad: "Faaliyet marjı", renk: "var(--kirmizi)", bicim: puan, noktalar: cevir((d.margins || {}).operating) },
    { ad: "Brüt marj", renk: "var(--yesil)", bicim: puan, noktalar: cevir((d.margins || {}).gross) },
    { ad: "Net marj", renk: "#a855f7", bicim: puan, noktalar: cevir((d.margins || {}).net) },
    { ad: "Net borç/FAVÖK", renk: "var(--sari)", bicim: (v) => TR(v, 2), noktalar: noktaCevir(d.net_debt_ebitda) },
    { ad: "Reel gelir büyümesi", renk: "#0ea5e9", bicim: (v) => yuzde(v), noktalar: noktaCevir(d.real_revenue_growth) },
  ]);

  const tabloSatir = (ad, noktalar, bicim) => {
    const g = (noktalar || []).filter((n) => n.value !== null && n.value !== undefined);
    if (!g.length) return "";
    return `<tr><td class="metin">${kacir(ad)}</td>
      ${g.map((n) => `<td>${kacir(bicim(n.value))}</td>`).join("")}</tr>`;
  };

  const donemler = (d.fscore || []).map((n) => n.date);

  kap.innerHTML = `
    <section>
      <div class="panel">
        <div class="panel-bas">${kacir(d.symbol)} · kalite trendi
          <small>${kacir(d.currency || "")}</small></div>
        ${d.model_note ? `<div class="panel-ic"><p class="not">${kacir(d.model_note)}</p></div>` : ""}
        <div class="panel-ic">${cizim || `<p class="not">Yeterli geçmiş dönem yok.</p>`}</div>
        <div class="panel-dip"><p class="not">${kacir(d.axis_note || "")}</p></div>
      </div>
    </section>

    ${d.summary ? `<section><div class="panel">
        <div class="panel-bas">Ne değişti <small>${kacir(d.summary.rule_id)}</small></div>
        <div class="panel-ic"><p style="font-size:15px">${kacir(d.summary.text)}</p></div>
      </div></section>` : ""}

    ${donemler.length ? `<section><div class="panel">
        <div class="panel-bas">Dönem dönem <small>F-Skoru karşılaştırma noktaları</small></div>
        <div class="kaydir"><table>
          <thead><tr><th class="metin">Metrik</th>
            ${donemler.map((t) => `<th>${kacir(t.slice(0, 4))}</th>`).join("")}</tr></thead>
          <tbody>
            ${tabloSatir("F-Skoru", d.fscore, (v) => `${v}/9`)}
            ${tabloSatir("Net borç/FAVÖK", d.net_debt_ebitda, (v) => TR(v, 2))}
            ${tabloSatir("Reel gelir büyümesi", d.real_revenue_growth, (v) => yuzde(v))}
            ${tabloSatir("Reel net kâr büyümesi", d.real_net_income_growth, (v) => yuzde(v))}
          </tbody>
        </table></div>
      </div></section>` : ""}`;
};

/* ═══════════════════════════════════════════════════════════ TARAYICI */

const TARAYICI = { evren: "bist", sablon: null, kosullar: [], baglac: "AND", alanlar: null, sonuc: null };

EKRANLAR.tarayici = async function (kap) {
  if (!TARAYICI.alanlar) {
    const [alanlar, kurallar] = await Promise.all([
      API.al("/api/tarayici/alanlar"),
      API.al("/api/tarayici/kurallar"),
    ]);
    TARAYICI.alanlar = alanlar.alanlar;
    TARAYICI.operatorler = alanlar.operatorler;
    TARAYICI.kurallar = kurallar.kurallar;
  }
  ciz(kap);
};

function ciz(kap) {
  const sablonlar = (TARAYICI.kurallar || []).map((s) => `
    <button class="cip" type="button" data-sablon="${kacir(s.id)}"
      aria-pressed="${TARAYICI.sablon === s.id}">
      ${kacir(s.name)}<small>${kacir(s.note || "")}</small>
    </button>`).join("");

  const evrenler = (DURUM?.evrenler || []).map((e) => `
    <button class="cip" type="button" data-evren="${kacir(e.id)}"
      aria-pressed="${TARAYICI.evren === e.id}">${kacir(e.label)}
      <small>${e.tarama_gerekli ? "taranmadı" : e.taranan + " şirket"}</small></button>`).join("");

  kap.innerHTML = `
    <section>
      <div class="panel">
        <div class="panel-bas">Tarayıcı <small>kuralı sen kur, araç evreni tarasın</small></div>
        <div class="panel-ic">
          <label class="alan" style="margin-bottom:12px"><span style="font-size:11.5px;font-weight:600;color:var(--sonuk)">Evren</span></label>
          <div class="cipler">${evrenler}</div>
        </div>
        <div class="panel-ic">
          <p class="not" style="margin-bottom:10px">Hazır filtre örnekleri — <b>tavsiye değil</b>,
            başlangıç noktası:</p>
          <div class="cipler">${sablonlar}</div>
        </div>
        <div class="panel-ic">
          <p class="not" style="margin-bottom:10px">Ya da kendi kuralını kur:</p>
          <div id="kosullar">${TARAYICI.kosullar.map(kosulSatiri).join("")}</div>
          <div class="form-satir" style="margin-top:10px">
            <button class="dugme ikincil" type="button" id="kosul-ekle">+ Koşul ekle</button>
            ${TARAYICI.kosullar.length > 1 ? `
              <div class="alan"><label>Koşullar arası</label>
                <select id="baglac">
                  <option value="AND"${TARAYICI.baglac === "AND" ? " selected" : ""}>hepsi (VE)</option>
                  <option value="OR"${TARAYICI.baglac === "OR" ? " selected" : ""}>herhangi biri (VEYA)</option>
                </select></div>` : ""}
            ${TARAYICI.kosullar.length ? `<button class="dugme" type="button" id="tara">Tara</button>` : ""}
          </div>
        </div>
      </div>
    </section>
    <div id="sonuc">${TARAYICI.sonuc ? tarayiciSonuc(TARAYICI.sonuc) : ""}</div>`;

  kap.querySelectorAll("button[data-evren]").forEach((b) =>
    b.addEventListener("click", () => {
      TARAYICI.evren = b.dataset.evren; TARAYICI.sonuc = null; ciz(kap);
    }));

  kap.querySelectorAll("button[data-sablon]").forEach((b) =>
    b.addEventListener("click", async () => {
      TARAYICI.sablon = b.dataset.sablon;
      TARAYICI.kosullar = [];
      await calistir(kap, `/api/tarayici?sablon=${encodeURIComponent(b.dataset.sablon)}` +
        `&evren=${TARAYICI.evren}&limit=40`);
    }));

  const ekle = kap.querySelector("#kosul-ekle");
  if (ekle) ekle.addEventListener("click", () => {
    TARAYICI.kosullar.push({ field: "fscore", op: ">=", value: "7" });
    TARAYICI.sablon = null;
    ciz(kap);
  });

  const baglac = kap.querySelector("#baglac");
  if (baglac) baglac.addEventListener("change", () => { TARAYICI.baglac = baglac.value; });

  kap.querySelectorAll("[data-kosul]").forEach((el) => {
    const index = Number(el.dataset.kosul);
    el.querySelectorAll("select,input").forEach((girdi) =>
      girdi.addEventListener("change", () => {
        TARAYICI.kosullar[index][girdi.dataset.parca] = girdi.value;
        if (girdi.dataset.parca === "field") ciz(kap);
      }));
    const sil = el.querySelector(".sil");
    if (sil) sil.addEventListener("click", () => {
      TARAYICI.kosullar.splice(index, 1); ciz(kap);
    });
  });

  const tara = kap.querySelector("#tara");
  if (tara) tara.addEventListener("click", async () => {
    const kural = kuraliDerle();
    await calistir(kap, `/api/tarayici?evren=${TARAYICI.evren}&limit=40`, { kural });
  });
}

function kosulSatiri(kosul, index) {
  const secili = (TARAYICI.alanlar || []).find((a) => a.field === kosul.field);
  const bool = secili && secili.format === "bool";
  const metin = secili && secili.format === "text";
  return `<div class="kosul" data-kosul="${index}">
      <select data-parca="field">
        ${(TARAYICI.alanlar || []).map((a) => `<option value="${kacir(a.field)}"
          ${a.field === kosul.field ? "selected" : ""}>${kacir(a.label)}</option>`).join("")}
      </select>
      ${secili ? `<span class="kosul-terim">${terim(secili.field, "?")}</span>` : ""}
      <select data-parca="op">
        ${["&gt;", "&gt;=", "&lt;", "&lt;=", "==", "!="].map((o, i) => {
          const gercek = [">", ">=", "<", "<=", "==", "!="][i];
          return `<option value="${gercek}" ${gercek === kosul.op ? "selected" : ""}>${o}</option>`;
        }).join("")}
      </select>
      ${bool
        ? `<select data-parca="value">
            <option value="true"${kosul.value === "true" ? " selected" : ""}>var</option>
            <option value="false"${kosul.value === "false" ? " selected" : ""}>yok</option>
          </select>`
        : metin
          ? `<select data-parca="value">
              ${["genişleme", "daralma", "yatay"].map((y) =>
                `<option value="${y}"${kosul.value === y ? " selected" : ""}>${y}</option>`).join("")}
            </select>`
          : `<input data-parca="value" type="text" inputmode="decimal" style="width:110px"
              value="${kacir(kosul.value)}">`}
      <button class="dugme silik sil" type="button">Sil</button>
    </div>`;
}

function kuraliDerle() {
  const operands = TARAYICI.kosullar.map((k) => {
    const secili = (TARAYICI.alanlar || []).find((a) => a.field === k.field) || {};
    let deger = k.value;
    if (secili.format === "bool") deger = k.value === "true";
    else if (secili.format !== "text") {
      const sayi = Number(String(k.value).replace(",", "."));
      deger = Number.isNaN(sayi) ? k.value : sayi;
    }
    return { field: k.field, op: k.op, value: deger };
  });
  return operands.length === 1 ? operands[0] : { operator: TARAYICI.baglac, operands };
}

async function calistir(kap, yol, govde) {
  const hedef = kap.querySelector("#sonuc");
  hedef.innerHTML = `<div class="yuklenirken">taranıyor…</div>`;
  try {
    const sonuc = govde
      ? await (async () => {
          const yanit = await fetch(yol, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(govde),
          });
          const veri = await yanit.json();
          if (!yanit.ok) { const h = new Error(veri.hata); h.durum = yanit.status; throw h; }
          return veri;
        })()
      : await API.al(yol);
    TARAYICI.sonuc = sonuc;
    hedef.innerHTML = tarayiciSonuc(sonuc);
    hedef.querySelectorAll("button[data-git]").forEach((b) =>
      b.addEventListener("click", () => git("skor", b.dataset.git)));
  } catch (hata) {
    hedef.innerHTML = durumKarti(
      "Tarama yapılamadı", hata.message,
      hata.durum === 409 ? `python tools/tarama.py ${TARAYICI.evren}` : null, true,
      hata.durum === 409 ? TARAYICI.evren : null);
  }
}

function tarayiciSonuc(s) {
  const rozet = (c) => {
    const sinif = c.result === true ? "kr-gecti" : c.result === false ? "kr-kaldi" : "kr-eksik";
    const im = c.result === true ? "✓" : c.result === false ? "✗" : "?";
    return `<span class="kriter-rozet ${sinif}">${im} ${kacir(c.label)} ${kacir(c.display)}</span>`;
  };

  const satirlar = (liste) => liste.map((k) => `<tr>
      <td class="metin"><button class="sembol-baglanti" data-git="${kacir(k.symbol)}"
        >${kacir(k.symbol)}</button>
        <div class="not">${kacir((k.name || "").slice(0, 42))}</div></td>
      <td class="metin">${kacir(k.sector || "—")}</td>
      <td>${kacir(para(k.market_cap, ""))}</td>
      <td class="metin">${k.checks.map(rozet).join("")}</td>
    </tr>`).join("");

  return `
    <section>
      <div class="panel">
        <div class="panel-bas">
          ${s.template ? kacir(s.template.name) : "Özel kural"}
          <small>${s.scanned} şirket tarandı${s.veri_yasi_saat !== null && s.veri_yasi_saat !== undefined
            ? ` · veriler ${Math.round(s.veri_yasi_saat)} saat önce güncellendi` : ""}</small>
        </div>
        ${s.template ? `<div class="panel-ic"><p class="not">${kacir(s.template.explanation)}</p></div>` : ""}
        <div class="panel-ic">
          <div class="serit" style="margin:0">
            <div class="serit-kart"><div class="serit-etiket">Eşleşen</div>
              <div class="serit-deger">${s.matched_count ?? s.matched.length}</div>
              <div class="serit-alt">tüm kriterleri geçti${s.truncated
                ? ` · ilk ${s.matched.length} gösteriliyor` : ""}</div></div>
            <div class="serit-kart"><div class="serit-etiket">Kısmi</div>
              <div class="serit-deger">${s.partial_count}</div>
              <div class="serit-alt">veri eksik, geçmiş olabilir</div></div>
            <div class="serit-kart"><div class="serit-etiket">Uygulanamaz</div>
              <div class="serit-deger">${s.not_applicable_count || 0}</div>
              <div class="serit-alt">sektöründe tanımsız</div></div>
          </div>
        </div>
        ${s.matched.length ? `<div class="kaydir"><table>
            <thead><tr><th class="metin">Sembol</th><th class="metin">Sektör</th>
              <th>Piyasa değeri</th><th class="metin">Kriterler</th></tr></thead>
            <tbody>${satirlar(s.matched)}</tbody>
          </table></div>`
          : `<div class="panel-ic"><p class="not">Hiçbir şirket kriterleri geçmedi.</p></div>`}
        <div class="panel-dip"><p class="not">${kacir(s.note)}</p></div>
      </div>
    </section>

    ${s.partial && s.partial.length ? `<section><div class="panel">
        <div class="panel-bas">Kısmi <small>veri eksikliği yüzünden karar verilemedi</small></div>
        <div class="kaydir"><table>
          <thead><tr><th class="metin">Sembol</th><th class="metin">Ölçülemeyen kriter</th></tr></thead>
          <tbody>${s.partial.slice(0, 15).map((k) => `<tr>
              <td class="metin"><button class="sembol-baglanti" data-git="${kacir(k.symbol)}"
                >${kacir(k.symbol)}</button></td>
              <td class="metin">${kacir(k.checks.filter((c) => c.reason === "veri yok")
                .map((c) => c.label).join(", "))}</td>
            </tr>`).join("")}</tbody>
        </table></div>
      </div></section>` : ""}`;
}

/* ═══════════════════════════════════════════════════════════ PORTFÖY */

EKRANLAR.portfoy = async function (kap) {
  const veri = await API.al("/api/portfoy");
  const o = veri.ozet;

  kap.innerHTML = `
    ${o.empty ? "" : portfoyOzet(veri)}
    <section>
      <div class="panel">
        <div class="panel-bas">İşlem ekle <small>veriler yalnızca bu bilgisayarda tutulur</small></div>
        <div class="panel-ic">
          <div class="form-satir">
            <div class="alan"><label for="i-tarih">Tarih</label>
              <input id="i-tarih" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
            <div class="alan"><label for="i-sembol">Sembol</label>
              <input id="i-sembol" type="text" placeholder="SISE.IS" style="text-transform:uppercase"></div>
            <div class="alan"><label for="i-tur">İşlem</label>
              <select id="i-tur"><option value="alim">Alım</option><option value="satim">Satım</option></select></div>
            <div class="alan"><label for="i-adet">Adet</label>
              <input id="i-adet" type="number" step="any" min="0" placeholder="100"></div>
            <div class="alan"><label for="i-fiyat">Fiyat</label>
              <input id="i-fiyat" type="number" step="any" min="0" placeholder="43,42"></div>
            <div class="alan"><label for="i-komisyon">Komisyon</label>
              <input id="i-komisyon" type="number" step="any" min="0" value="0"></div>
            <div class="alan"><label for="i-kur">İşlem anındaki kur</label>
              <input id="i-kur" type="number" step="any" min="0" placeholder="yalnızca yabancı hisse"></div>
            <button class="dugme" type="button" id="islem-ekle">Ekle</button>
          </div>
          <p class="not" style="margin-top:10px">Yabancı hissede <b>işlem anındaki kuru</b> girersen
            araç hisse getirisi ile kur getirisini ayrı ayrı gösterebilir. Boş bırakılırsa
            ayrıştırma yapılmaz — uydurulmuş bir giriş kuru yanlış "kur kazancı" üretirdi.</p>
          <div id="islem-mesaj"></div>
          <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--cizgi)">
            <p class="not" style="margin-bottom:8px">Çok sayıda işlemin mi var? Aracı kurumun
              ekstresinden CSV hazırlayıp toplu ekleyebilirsin.</p>
            <button class="dugme ikincil" type="button" id="csv-ice-aktar">CSV'den içe aktar</button>
            <a class="baglanti-dugme" href="/api/portfoy/sablon" download="ornek_islemler.csv"
              style="margin-left:10px">örnek şablonu indir</a>
            <input type="file" id="csv-dosya" accept=".csv,text/csv" hidden>
            <div id="csv-mesaj"></div>
          </div>
        </div>
        ${(veri.islemler || []).length ? `<div class="kaydir"><table>
            <thead><tr><th class="metin">Tarih</th><th class="metin">Sembol</th><th class="metin">İşlem</th>
              <th>Adet</th><th>Fiyat</th><th>Komisyon</th><th></th></tr></thead>
            <tbody>${veri.islemler.map((t, i) => `<tr>
                <td class="metin">${kacir(t.date)}</td>
                <td class="metin">${kacir(t.symbol)}</td>
                <td class="metin">${t.side === "alim" ? "Alım" : "Satım"}</td>
                <td>${kacir(TR(t.quantity, 0))}</td>
                <td>${kacir(TR(t.price, 2))}</td>
                <td>${kacir(TR(t.commission, 2))}</td>
                <td><button class="dugme silik" type="button" data-sil="${i}">Sil</button></td>
              </tr>`).join("")}</tbody>
          </table></div>` : ""}
      </div>
    </section>
    ${o.empty ? durumKarti(
      "Henüz işlem girilmedi",
      "Yukarıdaki formdan aldığın hisseleri ekle. Araç maliyetini, kâr/zararını, portföyünün " +
      "yapısal riskini ve içerdiği şirketlerin finansal kalitesini hesaplar.", null) : ""}`;

  kap.querySelector("#islem-ekle").addEventListener("click", async () => {
    const oku = (id) => kap.querySelector(id).value.trim();
    const govde = {
      date: oku("#i-tarih"),
      symbol: oku("#i-sembol").toUpperCase(),
      side: oku("#i-tur"),
      quantity: Number(oku("#i-adet").replace(",", ".")),
      price: Number(oku("#i-fiyat").replace(",", ".")),
      commission: Number(oku("#i-komisyon").replace(",", ".") || 0),
    };
    const kur = oku("#i-kur");
    if (kur) govde.fx_rate = Number(kur.replace(",", "."));

    const mesaj = kap.querySelector("#islem-mesaj");
    try {
      const yanit = await fetch("/api/portfoy/islem", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(govde),
      });
      const sonuc = await yanit.json();
      if (!yanit.ok) throw new Error(sonuc.hata);
      yonlendir();
    } catch (hata) {
      mesaj.innerHTML = `<div class="uyari-kart u-kirmizi" style="margin-top:10px">
        <div class="bas"><span class="tur">Hata</span><span>İşlem eklenemedi</span></div>
        <p>${kacir(hata.message)}</p></div>`;
    }
  });

  kap.querySelectorAll("button[data-sil]").forEach((b) =>
    b.addEventListener("click", async () => {
      await fetch("/api/portfoy/sil", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: Number(b.dataset.sil) }),
      });
      yonlendir();
    }));

  kap.querySelectorAll("button[data-git]").forEach((b) =>
    b.addEventListener("click", () => git("skor", b.dataset.git)));

  const csvMesaj = kap.querySelector("#csv-mesaj");
  const csvDosya = kap.querySelector("#csv-dosya");
  kap.querySelector("#csv-ice-aktar").addEventListener("click", () => csvDosya.click());

  csvDosya.addEventListener("change", async () => {
    const dosya = csvDosya.files[0];
    csvDosya.value = "";  // aynı dosyayı üst üste seçebilsin diye
    if (!dosya) return;

    let metin;
    try {
      metin = await dosya.text();
    } catch {
      csvMesaj.innerHTML = `<div class="uyari-kart u-kirmizi" style="margin-top:10px">
        <div class="bas"><span class="tur">Hata</span><span>Dosya okunamadı</span></div></div>`;
      return;
    }

    csvMesaj.innerHTML = `<p class="not" style="margin-top:10px">İçe aktarılıyor…</p>`;
    try {
      const yanit = await fetch("/api/portfoy/ice-aktar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv: metin }),
      });
      const sonuc = await yanit.json();
      if (!yanit.ok) throw new Error(sonuc.hata || `HTTP ${yanit.status}`);

      const hataVar = (sonuc.hatalar || []).length > 0;
      csvMesaj.innerHTML = `<div class="uyari-kart ${hataVar ? "u-sari" : "u-bilgi"}" style="margin-top:10px">
          <div class="bas"><span class="tur">${hataVar ? "Kısmi" : "Tamam"}</span>
            <span>${sonuc.eklenen} işlem eklendi${hataVar ? `, ${sonuc.hatalar.length} satır atlandı` : ""}</span></div>
          ${hataVar ? `<ul style="margin-top:6px;padding-left:18px">
              ${sonuc.hatalar.slice(0, 10).map((h) => `<li>${kacir(h)}</li>`).join("")}
            </ul>` : ""}
        </div>`;
      // yonlendir() tüm ekranı yeniden çiziyor — hemen çağrılırsa yukarıdaki
      // mesaj görünür olmadan silinirdi. Okunacak kadar bekleyip sonra
      // tazeleniyor; hata listesi varsa daha uzun süre kalsın.
      if (sonuc.eklenen > 0) setTimeout(() => yonlendir(), hataVar ? 6000 : 2500);
    } catch (hata) {
      csvMesaj.innerHTML = `<div class="uyari-kart u-kirmizi" style="margin-top:10px">
        <div class="bas"><span class="tur">Hata</span><span>İçe aktarılamadı</span></div>
        <p>${kacir(hata.message)}</p></div>`;
    }
  });
};

function portfoyOzet(veri) {
  const o = veri.ozet, risk = veri.risk, kalite = veri.kalite, reel = veri.reel_getiri;
  const pb = o.base_currency;

  const pozisyonlar = o.positions.filter((p) => p.quantity > 0).map((p) => `<tr>
      <td class="metin"><button class="sembol-baglanti" data-git="${kacir(p.symbol)}"
        >${kacir(p.symbol)}</button></td>
      <td>${kacir(TR(p.quantity, 0))}</td>
      <td>${kacir(TR(p.avg_cost, 2))}</td>
      <td>${kacir(TR(p.price, 2))}</td>
      <td>${kacir(para(p.value_base, pb))}</td>
      <td>${kacir(yuzde(p.weight, false))}</td>
      <td class="${isaretRengi(p.unrealized_pct)}">${kacir(yuzde(p.unrealized_pct))}</td>
    </tr>${p.fx_split && p.fx_split.available ? `<tr><td colspan="7" class="metin not"
      style="padding-top:0">↳ hisse getirisi ${kacir(yuzde(p.fx_split.share_return))} ·
      kur getirisi ${kacir(yuzde(p.fx_split.fx_return))} ·
      toplam ${kacir(yuzde(p.fx_split.total_return))}</td></tr>` : ""}`).join("");

  return `
    <section>
      <div class="serit">
        <div class="serit-kart"><div class="serit-etiket">Toplam değer</div>
          <div class="serit-deger">${kacir(para(o.total_value, pb))}</div>
          <div class="serit-alt">${o.open_positions} açık pozisyon</div></div>
        <div class="serit-kart"><div class="serit-etiket">Gerçekleşmemiş K/Z</div>
          <div class="serit-deger ${isaretRengi(o.total_unrealized)}"
            >${kacir(yuzde(o.total_unrealized_pct))}</div>
          <div class="serit-alt">${kacir(para(o.total_unrealized, pb))}</div></div>
        ${reel && reel.available
          ? `<div class="serit-kart">
              <div class="serit-etiket">Reel getiri</div>
              <div class="serit-deger buyuk ${isaretRengi(reel.real)}">${kacir(yuzde(reel.real))}</div>
              <div class="serit-alt">nominal ${kacir(yuzde(reel.nominal))} ·
                enflasyon ${kacir(yuzde(reel.cpi_growth, false))}</div>
              <div class="serit-kaynak">${kacir(reel.label || "")}</div>
            </div>`
          : `<div class="serit-kart">
              <div class="serit-etiket">Reel getiri</div>
              <div class="serit-deger gri" style="font-size:19px">—</div>
              <div class="serit-alt">${kacir((reel && reel.reason) || "TÜFE verisi yok")}</div>
            </div>`}
        ${o.total_realized ? `<div class="serit-kart">
            <div class="serit-etiket">Gerçekleşmiş K/Z</div>
            <div class="serit-deger ${isaretRengi(o.total_realized)}"
              >${kacir(para(o.total_realized, pb))}</div>
            <div class="serit-alt">satışlardan</div></div>` : ""}
      </div>
    </section>

    ${(o.warnings || []).length ? `<section><div class="uyari-kart u-sari">
        <div class="bas"><span class="tur">Uyarı</span><span>Veri girişi kontrolü</span></div>
        ${o.warnings.map((u) => `<p>${kacir(u)}</p>`).join("")}
      </div></section>` : ""}

    <section>
      <div class="panel">
        <div class="panel-bas">Pozisyonlar <small>${kacir(o.as_of)} · ${kacir(pb)} bazında</small></div>
        <div class="kaydir"><table>
          <thead><tr><th class="metin">Sembol</th><th>Adet</th><th>Ort. maliyet</th><th>Fiyat</th>
            <th>Değer</th><th>Ağırlık</th><th>K/Z</th></tr></thead>
          <tbody>${pozisyonlar}</tbody>
        </table></div>
      </div>
    </section>

    ${risk && risk.available ? riskPaneli(risk) : ""}
    ${kalite && kalite.available ? kalitePanel(kalite) : kalite ? `<section>
      ${durumKarti("Kalite röntgeni için tarama gerekli", kalite.reason || "",
        `python tools/tarama.py ${veri.baglam_evreni}`)}</section>` : ""}`;
}

function riskPaneli(risk) {
  const k = risk.concentration;
  // Başlıklar core/risk.py'nin RISK_ETIKETLERI tablosundan geliyor — eskiden
  // yalnızca burada sabit metin olarak duruyordu, sözlük anahtarına bağlamak
  // için uydurma bir eşleme kurmak gerekiyordu.
  const etiketler = risk.etiketler || {};
  const e = (anahtar, yedek) => {
    const giris = etiketler[anahtar];
    return giris ? terim(giris.terim, giris.ad) : kacir(yedek);
  };
  const dagilim = (liste, anahtar) => {
    const renkler = ["var(--vurgu)", "var(--yesil)", "var(--sari)", "var(--kirmizi)", "#a855f7", "#0ea5e9"];
    return `<div class="dagilim">${liste.map((s, i) =>
      `<span style="width:${(s.weight * 100).toFixed(1)}%;background:${renkler[i % renkler.length]}"
        title="${kacir(s[anahtar])} ${yuzde(s.weight, false)}"
        >${s.weight > 0.12 ? kacir(yuzde(s.weight, false)) : ""}</span>`).join("")}</div>
      <div class="aciklama">${liste.map((s, i) =>
        `<span><i class="nokta" style="background:${renkler[i % renkler.length]}"></i>
          ${kacir(s[anahtar])} ${kacir(yuzde(s.weight, false))}</span>`).join("")}</div>`;
  };

  return `<section>
    <div class="panel">
      <div class="panel-bas">Risk röntgeni <small>portföyün yapısı</small></div>
      <div class="panel-ic">
        <div class="serit" style="margin:0">
          <div class="serit-kart"><div class="serit-etiket">${e("largest", "En büyük pozisyon")}</div>
            <div class="serit-deger">${k.largest ? kacir(yuzde(k.largest[1], false)) : "—"}</div>
            <div class="serit-alt">${k.largest ? kacir(k.largest[0]) : ""}</div></div>
          <div class="serit-kart"><div class="serit-etiket">${e("top3_share", "İlk 3 pozisyon")}</div>
            <div class="serit-deger">${kacir(yuzde(k.top3_share, false))}</div>
            <div class="serit-alt">toplam ağırlık</div></div>
          <div class="serit-kart"><div class="serit-etiket">${e("effective_positions", "Etkin pozisyon sayısı")}</div>
            <div class="serit-deger">${kacir(TR(k.effective_positions, 1))}</div>
            <div class="serit-alt">${e("hhi", "HHI")} ${kacir(TR(k.hhi, 3))}</div></div>
          ${risk.volatility ? `<div class="serit-kart"><div class="serit-etiket">${e("volatility", "Yıllık volatilite")}</div>
            <div class="serit-deger">${kacir(yuzde(risk.volatility.annual, false))}</div>
            <div class="serit-alt">${risk.volatility.days} gün · kapsam
              ${kacir(yuzde(risk.volatility.coverage, false))}</div></div>` : ""}
          ${risk.drawdown ? `<div class="serit-kart"><div class="serit-etiket">${e("drawdown", "Tarihsel en kötü düşüş")}</div>
            <div class="serit-deger kirmizi">${kacir(yuzde(risk.drawdown.max_drawdown))}</div>
            <div class="serit-alt">${kacir(risk.drawdown.period || "")}</div></div>` : ""}
          ${risk.beta ? `<div class="serit-kart"><div class="serit-etiket">${e("beta", "Beta")}</div>
            <div class="serit-deger">${kacir(TR(risk.beta.value, 2))}</div>
            <div class="serit-alt">${kacir(risk.beta.index)}</div></div>` : ""}
        </div>
      </div>
      <div class="panel-ic">
        <p class="not" style="margin-bottom:6px"><b>Sektör dağılımı</b></p>
        ${dagilim(risk.sectors, "sector")}
        <p class="not" style="margin:14px 0 6px"><b>Para birimi dağılımı</b></p>
        ${dagilim(risk.currencies, "currency")}
      </div>
      ${risk.correlation && risk.correlation.average !== undefined ? `<div class="panel-ic">
          <p class="not"><b>${e("correlation", "Korelasyon")}:</b> ortalama ${kacir(TR(risk.correlation.average, 2))}
            (${risk.correlation.days} gün). En yüksek
            ${kacir(risk.correlation.highest[0])}–${kacir(risk.correlation.highest[1])}
            ${kacir(TR(risk.correlation.highest[2], 2))}. Hisseler aynı yöne hareket ettikçe
            portföy volatilitesi yükselir; birbirini dengelediklerinde düşer.</p>
        </div>` : ""}
      <div class="panel-dip"><p class="not">${kacir(k.note)} ${kacir(risk.coverage_note || "")}</p></div>
    </div>
  </section>`;
}

function kalitePanel(kalite) {
  const kovalar = kalite.buckets || [];
  const renkler = { "7–9": "var(--yesil)", "4–6": "var(--sari)", "0–3": "var(--kirmizi)" };
  // core/risk.py'nin KALITE_ETIKETLERI tablosundan — bkz. riskPaneli'ndeki e().
  const etiketler = kalite.etiketler || {};
  const e = (anahtar, yedek) => {
    const giris = etiketler[anahtar];
    return giris ? terim(giris.terim, giris.ad) : kacir(yedek);
  };
  return `<section>
    <div class="panel">
      <div class="panel-bas">Kalite röntgeni <small>portföyün içeriği</small></div>
      <div class="panel-ic">
        <div class="serit" style="margin:0">
          <div class="serit-kart"><div class="serit-etiket">${e("weighted_fscore", "Ağırlıklı F-Skoru")}</div>
            <div class="serit-deger buyuk">${kacir(TR(kalite.weighted_fscore, 2))}</div>
            <div class="serit-alt">${e("coverage", "kapsam")} ${kacir(yuzde(kalite.coverage, false))}</div></div>
          <div class="serit-kart"><div class="serit-etiket">${e("weak_cash_conversion_weight", "Kâr kalitesi zayıf")}</div>
            <div class="serit-deger">${kacir(yuzde(kalite.weak_cash_conversion_weight, false))}</div>
            <div class="serit-alt">portföy ağırlığı</div></div>
          <div class="serit-kart"><div class="serit-etiket">${e("real_shrinking_weight", "Reel küçülen")}</div>
            <div class="serit-deger">${kacir(yuzde(kalite.real_shrinking_weight, false))}</div>
            <div class="serit-alt">portföy ağırlığı</div></div>
        </div>
      </div>
      <div class="panel-ic">
        <p class="not" style="margin-bottom:6px"><b>F-Skoru dağılımı</b></p>
        <div class="dagilim">${kovalar.map((k) =>
          `<span style="width:${(k.weight * 100).toFixed(1)}%;background:${renkler[k.label] || "var(--sonuk)"}"
            >${k.weight > 0.1 ? kacir(k.label) : ""}</span>`).join("")}</div>
        <div class="aciklama">${kovalar.map((k) =>
          `<span><i class="nokta" style="background:${renkler[k.label] || "var(--sonuk)"}"></i>
            F-Skoru ${kacir(k.label)}: ${k.count} şirket, ${kacir(yuzde(k.weight, false))}</span>`).join("")}</div>
      </div>
      ${(kalite.sector_comparison || []).length ? `<div class="kaydir"><table>
          <thead><tr><th class="metin">Sektör</th><th>Portföy ağırlığı</th>
            <th>Portföydeki medyan F-Skoru</th><th>${e("sector_median_fscore", "Sektör medyanı")}</th></tr></thead>
          <tbody>${kalite.sector_comparison.map((s) => `<tr>
              <td class="metin">${kacir(s.sector)}</td>
              <td>${kacir(yuzde(s.weight, false))}</td>
              <td>${s.portfolio_median_fscore === null ? "—" : s.portfolio_median_fscore + "/9"}</td>
              <td>${s.sufficient ? TR(s.sector_median_fscore, 1) + "/9"
                : `<span class="na">örneklem yetersiz (n=${s.sector_n})</span>`}</td>
            </tr>`).join("")}</tbody>
        </table></div>` : ""}
      <div class="panel-dip"><p class="not">${kacir(kalite.coverage_note)} ${kacir(kalite.note)}</p></div>
    </div>
  </section>`;
}

/* ═══════════════════════════════════════════════════════════ PİYASA */

let PIYASA_EVREN = "bist";

EKRANLAR.piyasa = async function (kap) {
  const evrenler = (DURUM?.evrenler || []).map((e) => `
    <button class="cip" type="button" data-evren="${kacir(e.id)}"
      aria-pressed="${PIYASA_EVREN === e.id}">${kacir(e.label)}
      <small>${e.tarama_gerekli ? "taranmadı" : e.taranan + " şirket"}</small></button>`).join("");

  const secici = `<section><div class="panel"><div class="panel-ic">
      <div class="cipler">${evrenler}</div></div></div></section>`;

  kap.innerHTML = secici + `<div class="yuklenirken">yükleniyor…</div>`;
  kap.querySelectorAll("button[data-evren]").forEach((b) =>
    b.addEventListener("click", () => { PIYASA_EVREN = b.dataset.evren; yonlendir(); }));

  let d;
  try {
    d = await API.al(`/api/piyasa?evren=${PIYASA_EVREN}`);
  } catch (hata) {
    kap.innerHTML = secici + durumKarti("Piyasa bakışı için tarama gerekli", hata.message,
      `python tools/tarama.py ${PIYASA_EVREN}`, true, PIYASA_EVREN);
    kap.querySelectorAll("button[data-evren]").forEach((b) =>
      b.addEventListener("click", () => { PIYASA_EVREN = b.dataset.evren; yonlendir(); }));
    return;
  }

  const bicimliDeger = (h) => {
    if (h.value === null || h.value === undefined) return "—";
    if (h.format === "share") return yuzde(h.value, false);
    if (h.format === "score") return `${TR(h.value, 1)}/9`;
    if (h.format === "points") return puan(h.value);
    return TR(h.value, 2);
  };

  const hist = d.distributions.fscore_histogram;
  const enCok = Math.max(...hist.map((h) => h.count), 1);

  kap.innerHTML = secici + `
    <section>
      <div class="serit">
        ${d.headline.map((h) => `<div class="serit-kart">
            <div class="serit-etiket">${terim(h.key, h.label)}</div>
            <div class="serit-deger">${kacir(bicimliDeger(h))}</div>
            <div class="serit-alt">n=${h.n}${h.excludes_financials ? " · finans hariç" : ""}</div>
          </div>`).join("")}
      </div>
    </section>

    <section><div class="panel">
      <div class="panel-bas">F-Skoru dağılımı
        <small>${d.distributions.fscore_n} şirket · ${d.distributions.financials_excluded} finans şirketi dışarıda</small></div>
      <div class="panel-ic">
        <div class="histogram">
          ${hist.map((h) => `<div>
              <div class="adet">${h.count || ""}</div>
              <div class="bar" style="height:${(h.count / enCok) * 100}%"></div>
              <div class="etiket">${h.score}</div>
            </div>`).join("")}
        </div>
        <p class="not" style="margin-top:10px">Medyan ${kacir(TR(d.distributions.fscore_median, 1))}/9.
          ${kacir(d.distributions.note)}</p>
      </div>
    </div></section>

    <section><div class="panel">
      <div class="panel-bas">Sektörler <small>${d.sectors.length} sektör</small></div>
      <div class="kaydir"><table>
        <thead><tr><th class="metin">Sektör</th><th>Şirket</th><th>F-Skoru</th>
          <th>Net borç/FAVÖK</th><th>Faaliyet marjı</th><th>ROE</th><th>F/K</th></tr></thead>
        <tbody>${d.sectors.map((s) => {
          const m = (ad) => {
            const x = s.metrics[ad];
            if (!x || !x.sufficient) return `<span class="na">n=${x ? x.n : 0}</span>`;
            if (ad === "fscore") return `${TR(x.median, 1)}/9`;
            if (ad === "operating_margin") return puan(x.median);
            if (ad === "roe") return yuzde(x.median, false);
            return TR(x.median, 2);
          };
          return `<tr>
            <td class="metin">${kacir(s.sector)}</td>
            <td>${s.count}</td>
            <td>${m("fscore")}</td>
            <td>${m("net_debt_ebitda")}${s.financials_excluded
              ? `<div class="not">${s.financials_excluded} finans hariç</div>` : ""}</td>
            <td>${m("operating_margin")}</td>
            <td>${m("roe")}</td>
            <td>${m("pe")}</td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>
    </div></section>

    <section class="iki">
      ${moverPanel("F-Skoru en çok yükselen", d.movers.risers)}
      ${moverPanel("F-Skoru en çok düşen", d.movers.fallers)}
    </section>

    <section><div class="panel"><div class="panel-ic">
      <p class="not">${kacir(d.note)} ${kacir(d.movers.note)}</p>
    </div></div></section>`;

  kap.querySelectorAll("button[data-evren]").forEach((b) =>
    b.addEventListener("click", () => { PIYASA_EVREN = b.dataset.evren; yonlendir(); }));
  kap.querySelectorAll("button[data-git]").forEach((b) =>
    b.addEventListener("click", () => git("skor", b.dataset.git)));
};

function moverPanel(baslik, liste) {
  return `<div class="panel">
    <div class="panel-bas">${kacir(baslik)} <small>son yıl</small></div>
    ${liste.length ? `<div class="kaydir"><table>
        <thead><tr><th class="metin">Sembol</th><th class="metin">Sektör</th>
          <th>Değişim</th><th>Şimdi</th></tr></thead>
        <tbody>${liste.map((m) => `<tr>
            <td class="metin"><button class="sembol-baglanti" data-git="${kacir(m.symbol)}"
              >${kacir(m.symbol)}</button></td>
            <td class="metin not">${kacir((m.sector || "").slice(0, 22))}</td>
            <td class="${isaretRengi(m.change)}">${m.change > 0 ? "+" : ""}${m.change}</td>
            <td>${m.current}/9</td>
          </tr>`).join("")}</tbody>
      </table></div>` : `<div class="panel-ic"><p class="not">Kayıt yok.</p></div>`}
  </div>`;
}

/* ══════════════════════════════════════════════════════════════ başlat */

document.getElementById("nav").addEventListener("click", (olay) => {
  const dugme = olay.target.closest("button[data-ekran]");
  if (!dugme) return;
  const { ekran: mevcutEkran, sembol } = hashCoz();
  // Karşılaştır ekranı birden çok sembolü virgülle tutuyor; başka bir sekmeye
  // geçerken bu listenin tamamını sembol parametresi bekleyen bir uca
  // taşımak (ör. /api/sirket?sembol=A,B) hataya yol açar — yalnızca ilk
  // sembol taşınır.
  const tekSembol = mevcutEkran === "karsilastir" && sembol ? sembol.split(",")[0] : sembol;
  git(dugme.dataset.ekran, tekSembol);
});

document.getElementById("marka").addEventListener("click", () => git("skor"));

document.getElementById("ekran").addEventListener("click", (olay) => {
  const ornek = olay.target.closest("button[data-ornek]");
  if (ornek) git("skor", ornek.dataset.ornek);
  const cift = olay.target.closest("button[data-ornek-cift]");
  if (cift) git("karsilastir", cift.dataset.ornekCift);
  const taramaDugmesi = olay.target.closest("button[data-tarama-baslat]");
  if (taramaDugmesi) {
    taramaDugmesi.disabled = true;
    taramaDugmesi.textContent = "Başlatılıyor…";
    taramaBaslat(taramaDugmesi.dataset.taramaBaslat);
  }
  const yildiz = olay.target.closest("button[data-izleme]");
  if (yildiz) {
    const aktif = izlemeyeEkleCikar(yildiz.dataset.izleme);
    yildiz.textContent = aktif ? "★" : "☆";
    yildiz.classList.toggle("aktif", aktif);
    yildiz.title = aktif ? "İzleme listesinden çıkar" : "İzleme listesine ekle";
    yildiz.setAttribute("aria-pressed", String(aktif));
  }
});

// Üst bardaki "Güncelle" / "şimdi tara" bağlantısı — header sekme değişince
// yeniden çizilmediği için ayrı bir delegasyon gerekiyor.
document.querySelector("header").addEventListener("click", (olay) => {
  const dugme = olay.target.closest("button[data-tarama-baslat-durum]");
  if (dugme) {
    dugme.disabled = true;
    taramaBaslat(dugme.dataset.taramaBaslatDurum);
  }
});

document.getElementById("tarama-iptal").addEventListener("click", taramaIptalEt);

window.addEventListener("hashchange", yonlendir);

terimBalonuKur();
sozlukYukle().then(() => { if (SOZLUK) yonlendir(); });  // balonlar için tazele
durumuYukle().then(yonlendir);
aramayiKur();
