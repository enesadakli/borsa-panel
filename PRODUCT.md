# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Plain static HTML/CSS/JS served by `server.py` (Python standard library). No build step, no framework.
`web/app.js` renders every screen as HTML strings into `#ekran`; Chart.js 4.5.1 is vendored under
`web/vendor/` and is the only JavaScript dependency. Everything must work offline (no CDN, no remote
fonts at runtime).

## Users

- **Primary (as of 2026-09-27): interview audience.** Anass (Ali Enes Adaklı, Computer Engineering,
  Ege University) shows the panel for about 2 minutes inside his live interview demo deck
  (`~/Developer/demo-deck`, iframe at `#/skor/SISE.IS`). Viewers are an HR screener and/or a software
  engineer watching a shared screen over Zoom/Teams. They must grasp in seconds that this is a serious,
  well-made equity analysis tool.
- **Secondary: Anass himself**, reading a company's financial statements for BIST and US stocks.

## Product Purpose

Show what a company's financial statements say: revenue, balance sheet and cash flow from Yahoo Finance,
turned into Piotroski F-Score, Altman Z, debt structure, earnings quality and **inflation-adjusted real
growth**. Success in an interview: the viewer reads the scorecard as a trustworthy, modern stock app
and remembers the real-vs-nominal growth idea.

## Positioning

Not a trading app. It never gives buy/sell signals, price targets or forecasts, and says so on screen.
Its distinct mechanism: the CPI used for real growth is chosen by the **statement's currency**, not the
exchange (THYAO trades on BIST in TRY but reports in USD, so US CPI applies). Data-quality honesty is
part of the product: missing data is never counted as zero, currency mismatches are flagged, metrics
that do not apply to a sector (banks: no EBITDA) are marked "uygulanamaz", not "kısmi".

## Screens

Skor Kartı (company scorecard, the demo screen), LLM Raporu, Kalite Trendi, Tarayıcı (rule screener
with eşleşen / kısmi / uygulanamaz groups), Karşılaştır (2–3 companies), Portföy (ledger, cost, FX
decomposition, risk), Piyasa (universe snapshot). Several depend on a BIST universe scan (~17 min);
their empty states must stay honest and useful.

## Terminology and format

- UI language Turkish. Numbers in Turkish format: thousands `.`, decimal `,`, percent as `%34,9`.
- Terms with tooltips come from one glossary (`core/sozluk.py`, `/api/sozluk`): F-Skoru, PD/DD, F/K,
  FAVÖK, Net borç/FAVÖK, reel/nominal.
- Flag severities: kırmızı (rule threshold crossed), sarı (needs attention / data issue), mavi (context
  note for all companies).

## Brand commitments

- Visual reference bar (user, 2026-09-27): modern consumer brokers such as Midas and Robinhood —
  clean, airy, big numbers. Keep the identity of a stock app; the current navy + indigo/emerald glass
  look is judged "AI slop and dated" and is to be replaced, not polished. A fully black-and-white
  pass was then judged "aşırı sade": the brand colour and meaning colours are part of the identity.
- The disclaimer "geçmiş veriyi analiz eder, tahmin veya tavsiye vermez" stays visible.
- Data source line (Yahoo Finance; TCMB EVDS, US BLS, World Bank) stays.

## Evidence on hand

165 tests, zero pip dependencies, 629 BIST symbols in the universe (2026-09-27 scan), US top 500, 21 API endpoints.

## Open decisions

- Dark theme: deferred (2026-09-27); the light theme ships first.
