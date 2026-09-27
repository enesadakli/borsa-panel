---
name: Borsa Paneli
description: Yerel hisse analiz paneli; her metrik bir tahlil satırı gibi okunur.
colors:
  ground: "#f7f8f7"
  ink: "#0e1411"
  positive: "#087a42"
  negative: "#c62a22"
  brand: "#1d4ed8"
  brand-deep: "#163da9"
  brand-tint: "#e9eefc"
  brand-band: "#d3ddf8"
  attention: "#a86200"
  attention-tint: "#fbefd9"
  ink-2: "#48524d"
  ink-3: "#66706a"
  rule: "#dce1de"
  rule-soft: "#e8ecea"
  band: "#dfe5e1"
  track: "#edf0ee"
  fill: "#eceff0"
  float: "#ffffff"
  positive-tint: "#e5f1ea"
  negative-tint: "#f8e7e5"
typography:
  display:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "84px"
    fontWeight: 850
    lineHeight: 0.88
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 72"
  headline:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "46px"
    fontWeight: 850
    lineHeight: 0.95
    letterSpacing: "-0.012em"
    fontVariation: "'wdth' 78"
  title:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 750
    lineHeight: 1.25
  body:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "'tnum'"
  label:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.4
  source:
    fontFamily: "JetBrains Mono, ui-monospace, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  bar: "3px"
  field: "8px"
  pill: "999px"
spacing:
  gutter: "28px"
  gutter-narrow: "16px"
  section: "40px"
  column-gap: "48px"
components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.float}"
    rounded: "{rounded.pill}"
    padding: "0 18px"
    height: "38px"
  button-ghost:
    backgroundColor: "{colors.fill}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "34px"
  input-search:
    backgroundColor: "{colors.fill}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 16px 0 38px"
    height: "38px"
  chip-selected:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.float}"
    rounded: "{rounded.field}"
  range-band:
    backgroundColor: "{colors.brand-band}"
    rounded: "{rounded.bar}"
    height: "10px"
---

# Design System: Borsa Paneli

## Overview

**Creative North Star: "Tahlil Sonucu" (the lab result)**

The panel reads a company the way a lab report reads a blood test: a value, the reference range it
should be judged against, and a marker only when it falls outside. One light ground, ink and hairline
rules, big condensed numerals, and colour that always means something: cobalt for the product's own
structure, green/red for the direction of a change, amber for attention. The navy glass dashboard of
equal KPI cards it replaced is the anti-reference; so is a colourless monochrome report (the user
rejected the first, fully black-and-white pass as "aşırı sade", 2026-09-27).

Density is honest rather than airy: tables stay tables, every number carries its source, and the
disclaimer that it gives no advice stays visible. Emphasis comes from scale and weight, never from
colour; colour is reserved for the sign of a change.

**Key Characteristics:**
- One light ground (#f7f8f7), no cards, sections opened by a 2px ink rule.
- Cobalt brand (#1d4ed8, shared with the demo deck) for logo, active tab, links, range band and dots.
- The hero field takes the direction's colour: a red wash when real growth falls, green when it rises.
- Archivo condensed heavy for numbers, Archivo normal width for UI, tabular figures everywhere.
- The reference band (sector 25–75th percentile) with median tick and company dot is the signature.
- Signed values always carry a drawn ▲/▼ as well as colour.

## Colors

Light ground and ink, one brand cobalt, and three meaning colours: up, down, attention.

### Primary
- **Ledger Ink** (#0e1411): text, rules, the company dot, active tab underline, primary button.

### Brand
- **Deck Cobalt** (#1d4ed8, deep #163da9): logo mark, active tab underline, links, primary button, range band (tint #d3ddf8) and company dots, charts that carry no sign, info flags.

### Secondary
- **Gain Green** (#087a42): signed increases only (real growth up, nominal up, YoY up).
- **Loss Red** (#c62a22): signed decreases and a crossed rule threshold ("Eşik" flags) only.
- **Attention Amber** (#a86200, tint #fbefd9): "Dikkat" flags and the watchlist star.
- Green/red washes (#e5f1ea / #f8e7e5) fill the hero field by direction.

### Neutral
- **Report Paper** (#f7f8f7): the single page ground; the header shares it.
- **Graphite** (#48524d) and **Pencil** (#66706a): secondary and tertiary text.
- **Hairline** (#dce1de) / **Soft Hairline** (#e8ecea): row and section dividers.
- **Reference Band** (#dfe5e1) and **Track** (#edf0ee): the range bar's middle half and full axis.
- **Field Fill** (#eceff0): search pill, inputs, chips, ghost buttons.
- **Float White** (#ffffff): only floating layers (search suggestions, focused inputs).

### Named Rules
**The Meaning Colours Rule.** Cobalt is structure, green/red is direction, amber is attention. No other hue, and none of them as decoration.

**The Colour Is Law Rule.** Green and red appear only on a signed change, a pass/fail, or a crossed threshold, never as a "good/bad" verdict on a percentile. Trends and out-of-band markers stay ink or cobalt.

## Typography

**Display Font:** Archivo variable, self-hosted in `web/fonts` (fallback Helvetica Neue, Arial)
**Body Font:** Archivo at normal width
**Source Font:** JetBrains Mono, only for rule ids, data-source lines and shell commands (code)

**Character:** One grotesque stretched two ways: condensed and heavy for figures, open for reading.

### Hierarchy
- **Display** (850, 84px, 0.88, wdth 72): the hero real-growth figure. 68px on phones.
- **Headline** (850, 46px, 0.95, wdth 78): symbol, price, secondary real figure, F-Skoru total (58px).
- **Figure** (800, 34px, wdth 80): valuation row values.
- **Title** (750, 17px): section headings under the ink rule.
- **Body** (400, 15px, 1.5): sentences, capped near 88ch.
- **Label** (600, 12–12.5px): column heads, captions, the künye line.

### Named Rules
**The Tabular Rule.** Every number uses tabular figures and Turkish formatting (`%34,9`, `117,42 Mr`).

## Layout

A single centred column (max 1240px, 28px gutters, 16px under 760px). The scorecard's first
viewport is a 5/7 split: real growth left, fired flags right; below it a four-cell valuation row,
then the full-width lab table, then a two-column F-Skoru / last-quarter pair (48px gap). Sections
sit 40px apart. Under 760px everything stacks, the header stops being sticky, and the lab table
drops the median, position and trend columns so the range bar keeps its width.

## Elevation & Depth

Flat by default. Depth comes from rules, not shadows: a 2px ink rule opens a section, 1px
hairlines divide rows. The only shadows belong to floating layers (search suggestions,
glossary tooltip), soft and offset.

### Named Rules
**The Ruled Page Rule.** No cards, no bordered boxes; a section is a rule, a title and content.

## Shapes

Small, functional radii: 3px on bars and bands, 8px on fields and chips, full pills for the search
field and buttons. The company dot is a 12px circle ringed in ground colour.

## Components

### Buttons
- **Primary:** cobalt pill (38px high, 0 18px), white text; hover to deep cobalt.
- **Ghost:** field-fill pill (34px); hover to band colour.
- **Text link:** ink, semibold, underline on hover, with a drawn outward arrow for external links.

### Inputs
- **Search:** field-fill pill with drawn magnifier; focus turns white with a 1.5px inset ink ring.

### Navigation
- Cobalt logo mark before the wordmark. Text tabs 26px apart, tertiary ink; the active tab is ink with a 3px cobalt underline.

### Flag row
- A 72px severity bar plus label ("Eşik", "Dikkat", "Not") beside title, a one-line sentence and a collapsed full text + source. Severity is fill and colour: full red, half amber, thin cobalt.

### Hero field
- 16px-radius field washed in the direction's tint; the real figure at 84px beside a bar strip of revenue in today's money (older years at 28% opacity, latest solid).

### Reference band (signature)
- Axis 0–100 sector percentile; cobalt band 25–75; deep-cobalt median tick at 50; cobalt dot at the company's percentile. On render the dot slides once from the median to its place (0.8s expo-out, translate only, off under reduced motion). Position text: "alt çeyrek / orta yarı / üst çeyrek · N".

### F-Skoru column
- Big total, nine-segment bar (green passed, red failed, track unknown), then a numbered 1–9 list with drawn check / cross / dash / question marks.

### Criterion chip (Tarayıcı)
- Small pill with a drawn check / cross / question mark: passed on green tint, failed on red tint, unknown outlined.

### Result groups (Tarayıcı)
- Eşleşen / Kısmi / Uygulanamaz as a ruled stat strip, each cell topped by a 3px bar: green, amber, grey; the count takes the same colour.

### Categorical splits (Portföy)
- Sector and currency shares use a cobalt ramp (#1d4ed8, #4d72e0, #8aa3ec, #163da9, #bccbf5, grey), never green/red; F-Skoru buckets use green / amber / red because they carry a level.

## Do's and Don'ts

### Do:
- **Do** open every section with the 2px ink rule and a 17px title.
- **Do** put the real figure first and large, nominal and inflation beside it and small.
- **Do** draw icons and signs as SVG in one stroke weight.
- **Do** keep the disclaimer and data-source line visible.

### Don't:
- **Don't** reintroduce glass, glows, gradients, card grids or indigo/emerald accents.
- **Don't** strip the page back to black and white; the meaning colours are part of the identity.
- **Don't** colour a percentile, trend or out-of-band marker green/red; position is not a verdict.
- **Don't** use Unicode glyphs (▲ ★ ✓) or emoji as icons.
- **Don't** load fonts or scripts from a CDN; the panel must run offline.
