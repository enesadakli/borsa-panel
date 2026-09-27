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
  deger === null || deger === undefined ? "" : deger > 0 ? "text-primary" : deger < 0 ? "text-error" : "";

/* Çizili işaretler ve ikonlar: tek çizgi kalınlığı, tek dil. Unicode glif
 * (▲ ★ ✓) yazı tipine göre değişiyor; bunlar her yerde aynı çiziliyor. */
const SVG_ISARET = {
  yukari: '<svg class="isaret-svg" viewBox="0 0 10 10" aria-hidden="true"><path d="M5 1.2 9.4 8.8H.6z"/></svg>',
  asagi: '<svg class="isaret-svg" viewBox="0 0 10 10" aria-hidden="true"><path d="M5 8.8 .6 1.2h8.8z"/></svg>',
};
const IKON = {
  yildiz: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m10 2.6 2.3 4.8 5.2.7-3.8 3.6.9 5.2L10 14.4l-4.6 2.5.9-5.2-3.8-3.6 5.2-.7z"/></svg>',
  onay: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.2 8.4 3 3 6.6-7"/></svg>',
  carpi: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
  eksi: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 8h8"/></svg>',
  soru: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 6.2a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.3v.4M8 12.2v.1"/></svg>',
  disari: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4.5 2.5h5v5M9.5 2.5 3 9"/></svg>',
};

/** İşaretli değer (puan, skor farkı, tutar): çizili ▲/▼ + renk + verilen metin. */
const isaretliMetin = (deger, metin) => {
  if (deger === null || deger === undefined) return "—";
  const glif = deger > 0 ? SVG_ISARET.yukari : deger < 0 ? SVG_ISARET.asagi : "";
  const okunan = deger > 0 ? "artış " : deger < 0 ? "düşüş " : "";
  return `<span class="${isaretRengi(deger)}">${glif}<span class="gorunmez">${okunan}</span>${kacir(metin)}</span>`;
};

/** Kriter işareti: geçti / kaldı / veri eksik / sektörde geçersiz, çizili ikonla. */
const kriterIkonu = (durum) => ({
  gecti: `<span class="isaret i-gecti" role="img" aria-label="geçti">${IKON.onay}</span>`,
  kaldi: `<span class="isaret i-kaldi" role="img" aria-label="kaldı">${IKON.carpi}</span>`,
  eksik: `<span class="isaret i-eksik" role="img" aria-label="veri eksik">${IKON.soru}</span>`,
  na: `<span class="isaret i-na" role="img" aria-label="sektörde tanımsız">${IKON.eksi}</span>`,
}[durum]);

/** İşaretli yüzde: çizili ▲/▼, renk ve metin birlikte; renk tek sinyal değil. */
const isaretliYuzde = (deger) => {
  if (deger === null || deger === undefined) return "—";
  const glif = deger > 0 ? SVG_ISARET.yukari : deger < 0 ? SVG_ISARET.asagi : "";
  const okunan = deger > 0 ? "artış " : deger < 0 ? "düşüş " : "";
  return `<span class="${isaretRengi(deger)}">${glif}<span class="gorunmez">${okunan}</span>${
    kacir(yuzde(Math.abs(deger), false))}</span>`;
};

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

/* ═══════════════════════════════════════════════════════════ grafikler */

/** Chart.js'e ekran talep ederken verilen `var(--x)` rengini gerçek renge
 * çözer. Canvas 2D bağlamı CSS özel özelliklerini DOM gibi çözmez; tarayıcı
 * temasına göre değişen tema renklerimiz `getComputedStyle` ile okunmalı. */
function renkCoz(deger) {
  const es = /^var\((--[a-z-]+)\)$/.exec((deger || "").trim());
  if (!es) return deger;
  return getComputedStyle(document.documentElement).getPropertyValue(es[1]).trim() || deger;
}

/** Ekranda o an çizili Chart.js grafiklerinin kaydı. Bir ekrandan diğerine
 * geçildiğinde (`yonlendir()`) hepsi `destroy()` edilir — aksi hâlde her ekran
 * değişiminde eski canvas'lar DOM'dan silinse bile Chart.js'in iç kaydında
 * yaşamaya devam eder ve bellek/CPU sızıntısı birikir. */
let AKTIF_GRAFIKLER = [];

if (window.Chart) {
  Chart.defaults.font.family = '"Archivo", "Helvetica Neue", Arial, sans-serif';
  Chart.defaults.color = "#66706a";
  Chart.defaults.plugins.tooltip.backgroundColor = "#0e1411";
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.padding = 10;
}

function grafikleriTemizle() {
  AKTIF_GRAFIKLER.forEach((g) => g.destroy());
  AKTIF_GRAFIKLER = [];
}

let GRAFIK_SAYAC = 0;

/** `yonlendir()` başlangıçta iki ayrı yerden (sözlük + durum yüklenince)
 * çağrılıyor — SVG'de zararsızdı, Chart.js'te yarış durumu yaratıyor: ikinci
 * çağrı `grafikleriTemizle()`'yi ilk çağrının grafikleri henüz KURULMADAN
 * çalıştırıyor, sonra ilk çağrının ertelenmiş kurulumu araya girip artık
 * ekranda olmayan canvas'lara bağlanıyor — hayalet grafik. Her `yonlendir()`
 * çağrısı kendi "nesil" numarasını alır; kurulum anında nesil değişmişse
 * (araya yeni bir gezinme girmişse) canvas DOM'da olsa bile kurulum iptal
 * edilir. */
let GRAFIK_NESIL = 0;

/** Canvas henüz DOM'a girmeden Chart.js kurulamıyor; `cizim` HTML string
 * olarak döndürülüp çağıran taraf onu `innerHTML`'e yazdıktan hemen sonra
 * `setTimeout(…, 0)` ile (bir sonraki tik'te, DOM zaten güncellenmişken)
 * gerçek grafik kuruluyor. Çağıran taraflar hiç değişmedi. */
function _ertelenmisKur(fn) {
  const nesil = GRAFIK_NESIL;
  setTimeout(() => {
    if (nesil !== GRAFIK_NESIL) return; // araya yeni bir gezinme girdi, vazgeç
    try { fn(); } catch (hata) { console.error("grafik kurulamadı:", hata); }
  }, 0);
}

/** Çok şeritli zaman serisi grafiği — her seri kendi küçük grafiğinde, kendi
 * ölçeğinde; zaman ekseni ortak. Farklı birimdeki serileri (0–9 skor, % marj,
 * kat borç oranı) tek eksene bindirmek çizgilerin kesişmesine anlam
 * yükletirdi — bu yüzden tek büyük grafik değil, N tane küçük grafik.
 */
function seritGrafik(seriler, genislik = 700) {
  const gecerli = seriler.filter((s) => s.noktalar.filter((n) => n.deger !== null).length >= 2);
  if (!gecerli.length) return "";

  const tarihler = [...new Set(gecerli.flatMap((s) => s.noktalar.map((n) => n.tarih)))].sort();
  const idler = gecerli.map(() => `grafik-${++GRAFIK_SAYAC}`);

  const html = gecerli.map((seri, sira) => {
    const degerler = seri.noktalar.filter((n) => n.deger !== null).map((n) => n.deger);
    const enAz = Math.min(...degerler), enCok = Math.max(...degerler);
    const aralikMetni = seri.aralikMetni || `${seri.bicim(enAz)} – ${seri.bicim(enCok)}`;
    return `<div class="grafik-serit">
        <div class="grafik-serit-bas">
          <span>${kacir(seri.ad)}</span>
          <span class="text-muted">${kacir(aralikMetni)}</span>
        </div>
        <div class="grafik-kutu" style="max-width:${genislik}px">
          <canvas id="${idler[sira]}"></canvas>
        </div>
      </div>`;
  }).join("");

  _ertelenmisKur(() => {
    gecerli.forEach((seri, sira) => {
      const canvas = document.getElementById(idler[sira]);
      if (!canvas) return;
      const seriTarihi = new Map(seri.noktalar.map((n) => [n.tarih, n.deger]));
      const renk = renkCoz(seri.renk);
      AKTIF_GRAFIKLER.push(new Chart(canvas, {
        type: "line",
        data: {
          labels: tarihler.map((t) => t.slice(0, 4)),
          datasets: [{
            data: tarihler.map((t) => (seriTarihi.has(t) ? seriTarihi.get(t) : null)),
            borderColor: renk, backgroundColor: renk,
            spanGaps: true, tension: 0.25, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2.5,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 250 },
          interaction: { intersect: false, mode: "index" },
          scales: {
            y: { display: false },
            x: {
              display: sira === gecerli.length - 1,
              grid: { display: false },
              ticks: { color: renkCoz("var(--sonuk)"), font: { size: 11 } },
            },
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ctx.parsed.y === null ? "veri yok" : seri.bicim(ctx.parsed.y),
              },
            },
          },
        },
      }));
    });
  });

  return html;
}

/** Sütun grafiği — reel tutar serisi için. */
function sutunGrafik(noktalar, birim, genislik = 700) {
  if (!noktalar.length) return "";
  const id = `grafik-${++GRAFIK_SAYAC}`;

  _ertelenmisKur(() => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    AKTIF_GRAFIKLER.push(new Chart(canvas, {
      type: "bar",
      data: {
        labels: noktalar.map((n) => n.tarih.slice(0, 4)),
        datasets: [{
          data: noktalar.map((n) => n.deger),
          backgroundColor: renkCoz("var(--vurgu)"),
          borderRadius: 5, maxBarThickness: 64,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 250 },
        scales: {
          y: { display: false },
          x: { grid: { display: false }, ticks: { color: renkCoz("var(--sonuk)"), font: { size: 11.5 } } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => para(ctx.parsed.y, birim) } },
        },
      },
    }));
  });

  return `<div class="grafik-kutu grafik-kutu-buyuk" style="max-width:${genislik}px">
      <canvas id="${id}"></canvas>
    </div>`;
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
        <button type="button" class="btn-ghost" data-tarama-baslat-durum="${kacir(e.id)}"
          >şimdi tara</button>`;
    }
    const yas = e.tarama_yasi_saat;
    const ek = yas === null || yas === undefined ? "" : yas < 1 ? " · yeni" : ` · ${Math.round(yas)} sa`;
    const eski = !e.tarama_calisiyor && yas !== null && yas !== undefined && yas > TARAMA_GUNCEL_SINIRI_SAAT;
    const guncelle = eski
      ? ` · <button type="button" class="btn-ghost" data-tarama-baslat-durum="${kacir(e.id)}"
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
          <button type="button" class="btn-primary" data-tarama-baslat="${kacir(taramaEvreni)}"
            >Taramayı panelden başlat</button>
        </div>` : ""}
    </div></section>`;
}

async function yonlendir() {
  GRAFIK_NESIL++;
  grafikleriTemizle();
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
    reelVeUyarilar(veri),
    degerlemeSatiri(veri),
    metrikPaneli(veri),
    ikiSutun(fskorPaneli(veri), ceyrekPaneli(rapor)),
    ozetPaneli(veri),
    kalitePaneli(veri),
    reelGelirPaneli(veri),
  ].join("");
  araliklariCanlandir(kap);
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
          ${izleme.map((s) => `<button type="button" data-ornek="${kacir(s)}"><span class="ornek-yildiz">${IKON.yildiz}</span>${kacir(s)}</button>`).join("")}
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
      aria-label="İzleme listesi" aria-pressed="${aktif}">${IKON.yildiz}</button>`;
}

function sirketBasligi(veri) {
  const p = veri.profil;

  // Künye tek satır metin: sektör, endüstri, tablo para birimi, dönem ve yaşı.
  // "Dönem 2024-12-31" tek başına bir şey söylemiyor, "19 ay önce" söylüyor;
  // bayatsa satır koyulaşır.
  const kunye = [];
  if (p.sektor) kunye.push(`<span>${kacir(p.sektor)}</span>`);
  if (p.endustri) kunye.push(`<span>${kacir(p.endustri)}</span>`);
  if (p.tablo_para) kunye.push(`<span>Tablolar ${kacir(p.tablo_para)}</span>`);
  const taze = veri.saglik.freshness || {};
  if (taze.latest_period) {
    const bayat = taze.level === "bayat" || taze.level === "cok_bayat";
    kunye.push(`<span${bayat ? ' class="uyari-metin"' : ""}>Dönem ${kacir(taze.latest_period)}${
      taze.label ? ` (${kacir(taze.label)})` : ""}</span>`);
  } else if (veri.ozet.as_of) {
    kunye.push(`<span>Dönem ${kacir(veri.ozet.as_of)}</span>`);
  }
  if (veri.banka_muhasebesi) {
    kunye.push(`<span class="uyari-metin">${terim("banka_muhasebesi", "Banka muhasebesi")}</span>`);
  }

  const notlar = [];
  if (p.tablo_para && p.fiyat_para && p.tablo_para !== p.fiyat_para) {
    notlar.push(`<b>Tablo ${kacir(p.tablo_para)}, fiyat ${kacir(p.fiyat_para)}.</b> Şirket tablolarını
      ${kacir(p.tablo_para)} açıklıyor, hissesi ${kacir(p.fiyat_para)} işlem görüyor. Oranlar
      ${kacir(p.tablo_para)} bazına çevrilerek hesaplandı.`);
  }
  if (p.piyasa_degeri_guvenilir === false && p.piyasa_degeri_notu) notlar.push(kacir(p.piyasa_degeri_notu));
  if (veri.banka_muhasebesi) {
    notlar.push(`Banka/finans şirketi: FAVÖK, brüt kâr, cari oran ve Altman Z bu sektörde
      tanımsız olduğu için hesaplanmadı.`);
  }

  return `<section style="margin-top:0">
    <div class="sirket">
      <div>
        <h1 class="sirket-kod">${kacir(veri.symbol)} ${izlemeYildizi(veri.symbol)}</h1>
        <div class="sirket-ad">${kacir(p.ad || "")}</div>
        <div class="sirket-kunye">${kunye.join("")}</div>
      </div>
      <div class="sirket-fiyat">
        <b>${kacir(TR(p.fiyat, 2))}<small>${kacir(p.fiyat_para || "")}</small></b>
        <small>son kapanış · piyasa değeri ${kacir(para(p.piyasa_degeri, p.fiyat_para || ""))}</small>
      </div>
    </div>
    <div class="sirket-alt">
      ${notlar.map((n) => `<p class="sirket-not">${n}</p>`).join("")}
      <a class="metin-baglanti" href="/api/llm-rapor?sembol=${encodeURIComponent(veri.symbol)}"
        target="_blank" rel="noopener">LLM raporunu aç ${IKON.disari}</a>
    </div>
  </section>`;
}

/* Bayrak seviyeleri renkle değil doluluk ve etiketle ayrılır: kırmızı dolu
 * (eşik aşıldı), sarı yarım (dikkat), bilgi ince (bağlam notu). Açıklama
 * cümlesi sunucunun lejantıyla aynı anlamı taşır, yalnız renk adları yerine
 * çubuk dilini kullanır. */
const BAYRAK_SEVIYE = {
  kirmizi: { sinif: "s-kirmizi", ad: "Eşik" },
  sari: { sinif: "s-sari", ad: "Dikkat" },
  bilgi: { sinif: "s-bilgi", ad: "Not" },
};
const BAYRAK_LEJANT = "Dolu kırmızı çubuk: tanımlı bir kuralın eşiği aşıldı. Yarım amber çubuk: dikkat " +
  "edilmesi gereken birleşim veya veri sorunu. İnce mavi çubuk: tüm şirketler için geçerli bağlam notu. " +
  "Bunlar hisse hakkında bir yargı değil, rakamların tetiklediği kurallardır.";

function bayrakSatiri(bayrak) {
  const s = BAYRAK_SEVIYE[bayrak.level] || BAYRAK_SEVIYE.bilgi;
  const kaynak = `${kacir(bayrak.id)}${bayrak.sources && bayrak.sources.length
    ? " · " + bayrak.sources.slice(0, 3).map((k) => `${kacir(k.item)}@${kacir(k.period || "—")}`).join(", ")
    : ""}`;
  return `<div class="bayrak">
      <div class="siddet ${s.sinif}"><i></i><span>${s.ad}</span></div>
      <div>
        <div class="bayrak-baslik">${kacir(bayrak.title)}${bayrak.approximate ? " · yaklaşık hesap" : ""}</div>
        ${bayrak.explanation ? `<p class="bayrak-ozet">${kacir(bayrak.explanation)}</p>` : ""}
        <details><summary>Tamamı ve kaynak</summary>
          ${bayrak.explanation ? `<p class="bayrak-tam">${kacir(bayrak.explanation)}</p>` : ""}
          <div class="kaynak">${kaynak}</div></details>
      </div>
    </div>`;
}

/** İlk görünümün kalbi: solda reel büyüme (birincil, dev), sağda tetiklenen kurallar. */
function reelVeUyarilar(veri) {
  const rg = veri.saglik.real_growth || {};

  // Gelir kahraman alanı: yönün rengini alır, yanında bugünün parasıyla gelir çubukları.
  const d = rg.revenue;
  const reelVar = d && d.real !== null && d.real !== undefined;
  const oncu = d ? (reelVar ? d.real : d.nominal) : null;
  const yon = oncu > 0 ? "artis" : oncu < 0 ? "dusus" : "";
  const seri = ((rg.real_revenue_series || {}).points || []).filter(([, v]) => v !== null && v > 0).slice(-6);
  const enCok = Math.max(...seri.map(([, v]) => v), 1);
  const cubuklar = seri.length >= 2 ? `<div class="reel-grafik">
      <div class="reel-cubuk-bas">Gelir, bugünün parasıyla · <b>${kacir(para(seri[seri.length - 1][1], veri.saglik.currency || ""))}</b></div>
      <div class="reel-cubuklar" role="img" aria-label="Bugünün parasıyla yıllık gelir: ${
        seri.map(([t, v]) => `${t.slice(0, 4)} ${kacir(para(v, veri.saglik.currency || ""))}`).join(", ")}">
        ${seri.map(([t, v]) => `<div><i style="--h:${Math.max(4, (v / enCok) * 100).toFixed(1)}%"></i><span>${t.slice(0, 4)}</span></div>`).join("")}
      </div></div>` : "";
  const gelir = d ? `<div class="reel-alan" data-yon="${yon}">
      <div class="reel-etiket">Gelir · ${terim(reelVar ? "reel" : "nominal", reelVar ? "reel" : "nominal")}</div>
      <span class="reel-deger">${isaretliYuzde(oncu)}</span>
      ${cubuklar}
      ${reelVar ? `<div class="reel-ayrisma">
          <span>${terim("nominal", "Nominal")} <b>${isaretliYuzde(d.nominal)}</b></span>
          <span>${terim("tufe", "Enflasyon")} <b>${kacir(yuzde(d.cpi_growth, false))}</b></span>
        </div>
        ${d.label ? `<div class="reel-kaynak">${kacir(d.label)}</div>` : ""}`
        : `<p class="reel-yok">Reel karşılığı hesaplanamadı: ${kacir(d.detail || "dönemi kapsayan TÜFE verisi yok")}.</p>`}
    </div>` : "";

  const b = veri.bayraklar;
  const satirlar = [...(b.flags || []), ...(b.notes || [])].map(bayrakSatiri).join("");
  const sayim = [`${b.red_count} eşik`, `${b.yellow_count} dikkat`];
  if ((b.notes || []).length) sayim.push(`${b.notes.length} not`);

  return `<section class="tahlil-ust">
    <div>
      ${gelir || `<p class="reel-yok">Büyüme hesaplanamadı.</p>`}
    </div>
    <div>
      <div class="bayrak-bas">Uyarılar <small>${sayim.join(" · ")}</small></div>
      ${satirlar || `<p class="bayrak-yok">Tanımlı kurallardan hiçbiri tetiklenmedi.</p>`}
      <div class="bayrak-alt">
      <details><summary>Çubuklar ne anlatır?</summary><p class="bayrak-lejant">${kacir(BAYRAK_LEJANT)}</p></details>
      ${(b.not_applied || []).length ? `<details>
          <summary>Çalıştırılmayan kurallar (${b.not_applied.length})</summary>
          <ul>${b.not_applied.map((k) =>
            `<li><span class="kaynak" style="display:inline">${kacir(k.id)}</span> ${kacir(k.skip_reason || "")}</li>`).join("")}</ul>
        </details>` : ""}
      </div>
    </div>
  </section>`;
}

/** Tek cetvelli satır: reel net kâr, F-Skoru ve değerleme; altlarında bağlam. */
function degerlemeSatiri(veri) {
  const kar = (veri.saglik.real_growth || {}).net_income;
  const val = veri.saglik.valuation || {};
  const debt = veri.saglik.debt || {};
  const fscore = veri.saglik.fscore || {};
  const baglam = new Map((veri.baglam || []).map((b) => [b.metric, b]));
  const kiyas = (metrik) => {
    const b = baglam.get(metrik);
    if (!b || !b.available || b.sector_median === null || b.sector_median === undefined) return "";
    return `sektör medyanı ${bicimle(metrik, b.sector_median)}`;
  };

  const hucreler = [];
  if (kar) {
    const reelVar = kar.real !== null && kar.real !== undefined;
    hucreler.push(`<div><dt>Net kâr · ${terim(reelVar ? "reel" : "nominal", reelVar ? "reel" : "nominal")}</dt>
        <dd>${isaretliYuzde(reelVar ? kar.real : kar.nominal)}</dd>
        <div class="alt">${reelVar
          ? `${terim("nominal", "nominal")} ${isaretliYuzde(kar.nominal)} · ${terim("tufe", "enflasyon")} ${kacir(yuzde(kar.cpi_growth, false))}`
          : "reel karşılığı hesaplanamadı"}</div></div>`);
  }
  const son = fscore.latest;
  if (son) {
    hucreler.push(`<div><dt>${terim("fscore", "F-Skoru")}</dt>
        <dd>${son.score}<small> / 9</small></dd>
        <div class="alt">${kacir(kiyas("fscore") || son.label)}</div></div>`);
  }
  for (const [metrik, etiket, node] of [
    ["pe", "F/K", val.pe],
    ["pb", "PD/DD", val.pb],
    ["net_debt_ebitda", "Net borç/FAVÖK", debt.net_debt_ebitda],
  ]) {
    if (!node) continue;
    if (node.status !== "ok" || node.value === null || node.value === undefined) {
      hucreler.push(`<div><dt>${terim(metrik, etiket)}</dt><dd class="bos">—</dd>
          <div class="alt">${kacir(node.detail || "hesaplanamadı")}</div></div>`);
      continue;
    }
    hucreler.push(`<div><dt>${terim(metrik, etiket)}</dt>
        <dd>${kacir(bicimle(metrik, node.value))}</dd>
        <div class="alt">${kacir(kiyas(metrik) || node.basis || "")}</div></div>`);
  }
  if (!hucreler.length) return "";
  return `<dl class="degerleme" style="--n:${hucreler.length}">${hucreler.join("")}</dl>`;
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
  // olduğunu panelin içinde söylemek gerekiyor.
  const taze = veri.saglik.freshness || {};
  const yasNotu = taze.annual_stale && taze.last_annual
    ? `Bu skor <b>${kacir(taze.last_annual)}</b> yıllık tablosundan hesaplandı
       (${kacir(taze.label || "")}); bugünkü durumu değil o dönemi anlatıyor.`
    : "";

  // Her kriter: çizili işaret, durum sınıfı ve adım çubuğundaki karşılığı.
  const durum = (k) => {
    if (k.status === "ok") return k.passed ? ["i-gecti", IKON.onay, "gecti", "geçti"] : ["i-kaldi", IKON.carpi, "kaldi", "kaldı"];
    if (k.status === "sektorde_gecersiz") return ["i-na", IKON.eksi, "", "sektörde geçersiz"];
    return ["i-eksik", IKON.soru, "", "veri eksik"];
  };

  const gecmis = f.points.map((n) =>
    `${n.date.slice(0, 4)}: ${n.usable ? n.score + "/9" : "—"}`).join("  →  ");

  return `<div class="panel">
    <div class="panel-bas">Piotroski F-Skoru <small>${son ? kacir(son.date) : ""}</small></div>
    <div class="panel-ic">
      ${f.model_note ? `<p class="not" style="margin-bottom:12px">${kacir(f.model_note)}</p>` : ""}
      ${yasNotu ? `<p class="not" style="margin-bottom:12px">${yasNotu}</p>` : ""}
      ${son ? `<div class="fskor-ozet"><b>${son.score}</b><span>/ 9 kriter geçti</span></div>
        <div class="fskor-adimlar" aria-hidden="true">
          ${son.criteria.map((k) => `<i class="${durum(k)[2]}"></i>`).join("")}
        </div>
        <ol class="kriter-liste">
          ${son.criteria.map((k) => {
            const [sinif, ikon, , ad] = durum(k);
            return `<li class="kriter">
                <span class="isaret ${sinif}" role="img" aria-label="${ad}">${ikon}</span>
                <span>${terim(k.id, k.label)}</span>
                <span class="detay">${kacir(k.detail || "")}</span>
              </li>`;
          }).join("")}
        </ol>` : ""}
    </div>
    <div class="panel-dip"><span class="not">${kacir(gecmis)} · ${kacir(f.note)}</span></div>
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
    return isaretliYuzde(d.pct);
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

/* Tahlil satırı: şirketin sektör içindeki yüzdeliği bir aralık çubuğunda.
 * Eksen 0–100 yüzdelik; koyu bant sektörün orta yarısı (25–75), çentik medyan.
 * Bant dışı yalnız konumu söyler, yargı değildir: hangi yönün iyi olduğu
 * metriğe göre değişir, bu yüzden bant dışı renklenmez. */
function konumMetni(sp) {
  if (sp < 25) return { metin: "alt çeyrek", disarida: true };
  if (sp > 75) return { metin: "üst çeyrek", disarida: true };
  return { metin: "orta yarı", disarida: false };
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
      return `<tr class="tanimsiz"><td class="metrik-ad">${terim(item.metric, item.label)}</td>
        <td colspan="6" style="text-align:left">bu sektörde tanımsız</td></tr>`;
    }
    if (!item.available) return "";
    const yon = (item.trend || {}).direction;
    const yonGlif = { artış: SVG_ISARET.yukari, genişleme: SVG_ISARET.yukari,
      düşüş: SVG_ISARET.asagi, daralma: SVG_ISARET.asagi }[yon] || "";
    const sp = item.sector_percentile, up = item.universe_percentile;
    const tavanli = item.metric === "altman_z" && item.value > ALTMAN_TAVAN;
    const yerVar = sp !== null && sp !== undefined;
    const konum = yerVar ? konumMetni(sp) : null;
    return `<tr>
        <td class="metrik-ad">${terim(item.metric, item.label)}</td>
        <td class="deger"${tavanli ? ` title="tam değer: ${kacir(TR(item.value, 2))}"` : ""}
          >${kacir(bicimle(item.metric, item.value))}</td>
        <td class="medyan gizle-dar">${kacir(bicimle(item.metric, item.sector_median))}</td>
        <td class="aralik-hucre">${yerVar
          ? `<div class="aralik baslangic" style="--k:${Math.min(99, Math.max(1, sp)).toFixed(1)};--konum:${Math.min(99, Math.max(1, sp)).toFixed(1)}%"
               role="img" aria-label="sektör içinde ${Math.round(sp)}. yüzdelik, ${konum.metin}">
               <span class="bant"></span><span class="medyan-cizgi"></span><span class="sirket-nokta"></span>
             </div>`
          : `<span class="na">${kacir(item.sector_note || "örneklem yetersiz")}</span>`}</td>
        <td class="konum gizle-dar${konum && konum.disarida ? " disarida" : ""}">${konum
          ? `${kacir(konum.metin)} · ${Math.round(sp)}` : "—"}</td>
        <td class="trend gizle-dar">${yon ? `${yonGlif}${kacir(yon)}` : "—"}</td>
        <td class="gizle-dar">${up === null || up === undefined ? "—" : Math.round(up)}</td>
      </tr>`;
  }).join("");

  const evren = (DURUM?.evrenler || []).find((e) => e.id === veri.market);
  return `<section>
    <div class="panel">
      <div class="panel-bas">Tahlil: metrikler ve sektör aralığı
        <small>${kacir(veri.baglam[0]?.sector || "")}${evren ? ` · ${kacir(evren.label)} · ${evren.taranan || "?"} şirket` : ""}</small></div>
      <div class="kaydir">
        <table class="tahlil">
          <thead><tr>
            <th>Metrik</th><th>Değer</th>
            <th class="gizle-dar">${terim("sektor_medyani", "Sektör medyanı")}</th>
            <th class="aralik-bas">Sektör içindeki yeri
              <div class="aralik-olcek" aria-hidden="true"><span style="left:0">0</span><span style="left:50%">medyan</span><span style="left:100%">100</span></div></th>
            <th class="gizle-dar" style="text-align:left">${terim("yuzdelik_dilim", "Konum · yüzdelik")}</th>
            <th class="gizle-dar">Kendi trendi</th>
            <th class="gizle-dar">${terim("yuzdelik_dilim", "Evren %")}</th>
          </tr></thead>
          <tbody>${satirlar}</tbody>
        </table>
      </div>
      <div class="tahlil-lejant">
        <span><i class="ornek-bant"></i> sektörün orta yarısı (25–75. yüzdelik)</span>
        <span><i class="ornek-medyan"></i> sektör medyanı</span>
        <span><i class="ornek-nokta"></i> şirketin konumu</span>
      </div>
      <p class="not" style="margin-top:8px">Yüzdelik dilim bir yargı değildir; yalnızca şirketin
        nerede durduğunu gösterir, hangi yönün iyi olduğu metriğe ve amaca göre değişir.
        Altman Z'de ${ALTMAN_TAVAN} üstü "${ALTMAN_TAVAN}+" gösterilir: model 2,99'un üstünü
        tek bir "güvenli bölge" sayar, bu eşiğin çok ötesindeki farklar anlam taşımaz.</p>
    </div>
  </section>`;
}

/** Tahlil noktalarını medyandan kendi yerlerine bir kez kaydırır. */
function araliklariCanlandir(kap) {
  const araliklar = [...kap.querySelectorAll(".aralik.baslangic")];
  if (!araliklar.length) return;
  const birak = () => araliklar.forEach((a, i) => setTimeout(() => a.classList.remove("baslangic"), i * 40));
  requestAnimationFrame(() => requestAnimationFrame(birak));
  // Gizli sekmede rAF durur; nokta yine de yerine otursun.
  setTimeout(() => araliklar.forEach((a) => a.classList.remove("baslangic")), 1500);
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
    { ad: "Faaliyet marjı", renk: "var(--marka)", bicim: puan, noktalar: cevir(marjlar.operating) },
    { ad: "Brüt marj", renk: "var(--marka)", bicim: puan, noktalar: cevir(marjlar.gross) },
    {
      ad: "Net borç/FAVÖK", renk: "var(--marka)", bicim: (d) => TR(d, 2),
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
          <button class="kars-kaldir" data-kaldir="${kacir(s.symbol)}" title="Karşılaştırmadan çıkar" aria-label="Karşılaştırmadan çıkar">${IKON.carpi}</button>
          <div class="sirket-kod">${kacir(s.symbol)}</div>
          <p class="not" style="margin-top:8px">Veri alınamadı: ${kacir(s.hata)}</p>
        </div>`;
    }
    const p = s.veri.profil;
    const taze = s.veri.saglik.freshness || {};
    const bayat = taze.level === "bayat" || taze.level === "cok_bayat";
    return `<div class="kars-kart">
        <button class="kars-kaldir" data-kaldir="${kacir(s.symbol)}" title="Karşılaştırmadan çıkar" aria-label="Karşılaştırmadan çıkar">${IKON.carpi}</button>
        <div class="sirket-kod">${kacir(s.symbol)}</div>
        <div class="sirket-ad">${kacir(p.ad || "")}</div>
        <div class="rozetler">
          ${p.sektor ? `<span class="rozet">${kacir(p.sektor)}</span>` : ""}
          ${p.tablo_para ? `<span class="rozet">${kacir(p.tablo_para)}</span>` : ""}
          ${taze.latest_period ? `<span class="rozet${bayat ? " rozet-uyari" : ""}">
              Dönem ${kacir(taze.latest_period)}${taze.label ? ` · ${kacir(taze.label)}` : ""}</span>` : ""}
        </div>
        <div class="kars-fiyat">${kacir(TR(p.fiyat, 2))}<small>${kacir(p.fiyat_para || "")}</small></div>
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
        return `<td class="deger">${isaretliYuzde(d.nominal)}
          <span class="alt-not">nominal</span></td>`;
      }
      return `<td class="deger">${isaretliYuzde(d.real)}
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

  const durumu = (k) => k.status === "ok" ? (k.passed ? "gecti" : "kaldi")
    : k.status === "sektorde_gecersiz" ? "na" : "eksik";

  const satirlar = canonical.criteria.map((kriter) => {
    const hucreler = basarili.map((s) => {
      const son = (s.veri.saglik.fscore || {}).latest;
      const k = son && son.criteria.find((c) => c.id === kriter.id);
      if (!k) return `<td>—</td>`;
      return `<td class="kriter-hucre">${kriterIkonu(durumu(k))}</td>`;
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
      <div class="panel-dip"><p class="not ikon-lejant">${kriterIkonu("gecti")} geçti
        ${kriterIkonu("kaldi")} kalmadı ${kriterIkonu("eksik")} veri yok
        ${kriterIkonu("na")} bu sektörde tanımsız</p></div>
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
      { ad: "Faaliyet marjı", renk: "var(--marka)", bicim: puan, noktalar: cevir(marjlar.operating) },
      { ad: "Brüt marj", renk: "var(--marka)", bicim: puan, noktalar: cevir(marjlar.gross) },
      {
        ad: "Net borç/FAVÖK", renk: "var(--marka)", bicim: (d) => TR(d, 2),
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
    return isaretliYuzde(x.pct);
  };

  const marjSatirlari = Object.values(d.margins || {}).map((m) => `<tr>
      <td class="metin">${kacir(m.label)}</td>
      <td>${kacir(puan(m.now))}</td>
      <td>${kacir(puan(m.before))}</td>
      <td>${m.delta === null || m.delta === undefined ? "—"
        : isaretliMetin(m.delta, `${TR(Math.abs(m.delta), 1)} puan`)}</td>
    </tr>`).join("");

  const rr = d.real_revenue;

  return `
    ${rr && rr.real !== null && rr.real !== undefined ? `<section><div class="serit">
        <div class="serit-kart">
          <div class="serit-etiket">Gelir · reel değişim</div>
          <div class="serit-deger buyuk">${isaretliYuzde(rr.real)}</div>
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
    { ad: "Faaliyet marjı", renk: "var(--marka)", bicim: puan, noktalar: cevir((d.margins || {}).operating) },
    { ad: "Brüt marj", renk: "var(--marka)", bicim: puan, noktalar: cevir((d.margins || {}).gross) },
    { ad: "Net marj", renk: "var(--marka)", bicim: puan, noktalar: cevir((d.margins || {}).net) },
    { ad: "Net borç/FAVÖK", renk: "var(--marka)", bicim: (v) => TR(v, 2), noktalar: noktaCevir(d.net_debt_ebitda) },
    { ad: "Reel gelir büyümesi", renk: "var(--marka)", bicim: (v) => yuzde(v), noktalar: noktaCevir(d.real_revenue_growth) },
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
            <button class="btn-primary ikincil" type="button" id="kosul-ekle">+ Koşul ekle</button>
            ${TARAYICI.kosullar.length > 1 ? `
              <div class="alan"><label>Koşullar arası</label>
                <select id="baglac">
                  <option value="AND"${TARAYICI.baglac === "AND" ? " selected" : ""}>hepsi (VE)</option>
                  <option value="OR"${TARAYICI.baglac === "OR" ? " selected" : ""}>herhangi biri (VEYA)</option>
                </select></div>` : ""}
            ${TARAYICI.kosullar.length ? `<button class="btn-primary" type="button" id="tara">Tara</button>` : ""}
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
      <button class="btn-primary silik sil" type="button">Sil</button>
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
    const ikon = c.result === true ? IKON.onay : c.result === false ? IKON.carpi : IKON.soru;
    return `<span class="kriter-rozet ${sinif}">${ikon}${kacir(c.label)} ${kacir(c.display)}</span>`;
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
          <div class="serit sonuc-grup">
            <div class="serit-kart g-eslesen"><div class="serit-etiket">Eşleşen</div>
              <div class="serit-deger">${s.matched_count ?? s.matched.length}</div>
              <div class="serit-alt">tüm kriterleri geçti${s.truncated
                ? ` · ilk ${s.matched.length} gösteriliyor` : ""}</div></div>
            <div class="serit-kart g-kismi"><div class="serit-etiket">Kısmi</div>
              <div class="serit-deger">${s.partial_count}</div>
              <div class="serit-alt">veri eksik, geçmiş olabilir</div></div>
            <div class="serit-kart g-na"><div class="serit-etiket">Uygulanamaz</div>
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
            <button class="btn-primary" type="button" id="islem-ekle">Ekle</button>
          </div>
          <p class="not" style="margin-top:10px">Yabancı hissede <b>işlem anındaki kuru</b> girersen
            araç hisse getirisi ile kur getirisini ayrı ayrı gösterebilir. Boş bırakılırsa
            ayrıştırma yapılmaz — uydurulmuş bir giriş kuru yanlış "kur kazancı" üretirdi.</p>
          <div id="islem-mesaj"></div>
          <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--cizgi)">
            <p class="not" style="margin-bottom:8px">Çok sayıda işlemin mi var? Aracı kurumun
              ekstresinden CSV hazırlayıp toplu ekleyebilirsin.</p>
            <button class="btn-primary ikincil" type="button" id="csv-ice-aktar">CSV'den içe aktar</button>
            <a class="btn-ghost" href="/api/portfoy/sablon" download="ornek_islemler.csv"
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
                <td><button class="btn-primary silik" type="button" data-sil="${i}">Sil</button></td>
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
      <td>${isaretliYuzde(p.unrealized_pct)}</td>
    </tr>${p.fx_split && p.fx_split.available ? `<tr><td colspan="7" class="metin not"
      style="padding-top:0">hisse getirisi ${kacir(yuzde(p.fx_split.share_return))} ·
      kur getirisi ${kacir(yuzde(p.fx_split.fx_return))} ·
      toplam ${kacir(yuzde(p.fx_split.total_return))}</td></tr>` : ""}`).join("");

  return `
    <section>
      <div class="serit">
        <div class="serit-kart"><div class="serit-etiket">Toplam değer</div>
          <div class="serit-deger">${kacir(para(o.total_value, pb))}</div>
          <div class="serit-alt">${o.open_positions} açık pozisyon</div></div>
        <div class="serit-kart"><div class="serit-etiket">Gerçekleşmemiş K/Z</div>
          <div class="serit-deger">${isaretliYuzde(o.total_unrealized_pct)}</div>
          <div class="serit-alt">${kacir(para(o.total_unrealized, pb))}</div></div>
        ${reel && reel.available
          ? `<div class="serit-kart">
              <div class="serit-etiket">Reel getiri</div>
              <div class="serit-deger buyuk">${isaretliYuzde(reel.real)}</div>
              <div class="serit-alt">nominal ${kacir(yuzde(reel.nominal))} ·
                enflasyon ${kacir(yuzde(reel.cpi_growth, false))}</div>
              <div class="serit-kaynak">${kacir(reel.label || "")}</div>
            </div>`
          : `<div class="serit-kart">
              <div class="serit-etiket">Reel getiri</div>
              <div class="serit-deger gri">—</div>
              <div class="serit-alt">${kacir((reel && reel.reason) || "TÜFE verisi yok")}</div>
            </div>`}
        ${o.total_realized ? `<div class="serit-kart">
            <div class="serit-etiket">Gerçekleşmiş K/Z</div>
            <div class="serit-deger">${isaretliMetin(o.total_realized, para(Math.abs(o.total_realized), pb))}</div>
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
    // Kategoriler anlam taşımıyor: kobalt tonları, yeşil/kırmızı değil.
    const renkler = ["var(--marka)", "#4d72e0", "#8aa3ec", "var(--marka-derin)", "#bccbf5", "var(--murekkep-3)"];
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
        <div class="serit">
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
            <div class="serit-deger">${isaretliYuzde(risk.drawdown.max_drawdown)}</div>
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
  const renkler = { "7–9": "var(--pozitif)", "4–6": "var(--dikkat)", "0–3": "var(--negatif)" };
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
        <div class="serit">
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
            <td>${isaretliMetin(m.change, String(Math.abs(m.change)))}</td>
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
// İkisi de bağımsız başlatılır (paralel ağ isteği), ama ekran TEK SEFERDE
// çizilir. Eskiden ayrı ayrı `.then(yonlendir)` çağrılıyordu — SVG'de
// zararsızdı (iki kez çizmek sadece fazladan iş), Chart.js'te yarış durumu
// yaratıyordu: ikinci çağrının temizliği ilkinin grafikleri henüz
// kurulmadan çalışıyor, sonra ilkinin ertelenmiş kurulumu araya girip artık
// ekranda olmayan canvas'lara bağlanıyordu (hayalet grafik/bellek sızıntısı).
Promise.all([sozlukYukle(), durumuYukle()]).then(() => yonlendir());
aramayiKur();
