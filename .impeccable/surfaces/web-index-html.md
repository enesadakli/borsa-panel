---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: []
---

# Surface brief: Skor Kartı (web/index.html → #/skor/<sembol>)

Mode: Operate. Audience: interview viewers on a shared Zoom screen (≈2 min, inside the demo deck iframe at ~1280×670), then Anass himself.
Task: read one company's financial health in seconds; remember the real-vs-nominal idea.
Constraints: plain HTML/CSS/JS, no build, offline (no remote fonts), Turkish number format, glossary tooltips, disclaimer and data-source line stay.
Scope: Skor Kartı first; shared CSS restyles the other six screens only as far as needed to not look broken. Dark theme deferred.

## Direction contract

THESIS: Every metric reads like a lab result: the value, the sector's middle-half reference band, the median tick, and an out-of-band marker only when it applies. Refuses the navy glass dashboard of equal KPI cards.

OWN-WORLD: One light ground (#F7F8F7) with ink (#0E1411) and hairline rules instead of cards. Exactly four inks: ground, ink, positive (#087A42), negative (#C62A22); every other tone is an ink tint. Green/red only on signed change or a crossed threshold. Every signed value carries a drawn ▲▼ mark. Archivo (self-hosted, shared with the deck) at normal width for UI, semi-condensed heavy for numbers; tabular figures everywhere.

STORY: The viewer sees the company and price, then a huge real revenue growth figure with its nominal and inflation parts, then which rules fired, then where each metric sits against its sector. They conclude: a serious, honest tool that does not give advice.

FIRST VIEWPORT: Top: wordmark, search pill, underline tabs, one quiet disclaimer line. Company row: symbol at 40px heavy, name and period as one text line; price 40px right. Hero row: left 5/12 "Reel gelir" at ~76px with nominal/enflasyon line beneath and reel net kâr at 40px; right 7/12 fired flags as rows with severity condition bars. Below: a ruled valuation row (F-Skoru, F/K, PD/DD, Net borç/FAVÖK), then the lab table begins.

FORM: Tahlil Sonucu (grounded list position 3 of 7), seed bb13ba0b. Signature interaction: on render, each company dot slides from the sector median to its percentile along the reference band, once, expo-out; hovering a row highlights its band. Raises: four-ink law; colour is law; one shared period row; F-Skoru as numbered 1–9 column; flags as severity-filled bars; glyph-not-colour signalling.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
