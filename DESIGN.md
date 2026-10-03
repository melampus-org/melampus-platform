---
name: Melampus Local Tracing Platform
description: Dense local intent tracing and check evidence explorer
colors:
  ink: "#242333"
  muted: "#676579"
  subtle: "#f7f7fa"
  paper: "#fff"
  line: "#e4e3ec"
  violet: "#633da5"
  violet-dark: "#36234f"
  violet-soft: "#f0ebf8"
  nav: "#282035"
  green: "#23754d"
  green-soft: "#e9f5ee"
  red: "#b93247"
  red-soft: "#fff0f2"
  amber: "#94611a"
  amber-soft: "#fcf3e3"
  error: "#a64f14"
  primary-hover: "#4e2c88"
  control-border: "#d8d5e2"
  nav-active: "#634293"
  nav-hover: "#3b2d4b"
  traffic: "#9779c4"
  error-bar: "#bd713f"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "23px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-.025em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "13px"
    lineHeight: 1.5
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "11px"
    lineHeight: 1.5
  metric:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.3
  code:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "11px"
    lineHeight: 1.8
rounded:
  bar: "2px"
  count: "3px"
  badge: "4px"
  control: "5px"
  overview: "6px"
spacing:
  compact-gap: "6px"
  control-gap: "8px"
  cell-inline: "10px"
  cell-block: "11px"
  mobile-gutter: "18px"
  panel-gutter: "22px"
  page-gutter: "28px"
components:
  button-primary:
    backgroundColor: "{colors.violet}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-small:
    rounded: "{rounded.control}"
    padding: "6px 9px"
    typography: "{typography.label}"
  button-text:
    textColor: "{colors.violet}"
    padding: "3px 0"
    typography: "{typography.label}"
  search:
    rounded: "{rounded.control}"
    padding: "6px 10px"
  navigation-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "11px 10px"
  filter-chip:
    backgroundColor: "{colors.violet-soft}"
    textColor: "{colors.violet-dark}"
    rounded: "{rounded.badge}"
    padding: "3px 6px"
    typography: "{typography.label}"
  overview:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.overview}"
---

# Design System: Melampus Local Tracing Platform

## Overview

**Creative North Star: "The failure-first intent tracing workbench"**

The platform is a compact operating surface for developers investigating code execution. Pale reading fields, dark violet navigation, fine rules, and restrained purple actions keep dense evidence legible. The user pinned the Datadog tracing explorer vocabulary; the identity and terminology are Melampus.

This record applies only to `src/melampus_platform/static/`. The separate `site/` OPSWAT marketing identity is outside scope. Evidence comes from `style.css`, `index.html`, and `app.js`, with confirmed language from `PRODUCT.md` and `.impeccable/surfaces/src-melampus-platform-static-index-html.md`. The build is code-led, with no approved raster comp or shipping raster assets.

**Key Characteristics:**

- Dense tables and facets with persistent investigation context.
- Labeled outcomes, mono identifiers, and tabular numeric evidence.
- Flat reading surfaces; structural elevation for trace detail.

## Colors

A pale neutral field supports violet navigation and actions, with separate evidence colors.

### Primary

- **Workbench Violet** (`violet`): primary actions, selected tabs, focus outlines, and service markers. `violet-soft` marks selected rows and filter chips.
- **Deep Violet** (`violet-dark`, `nav`): chip text, transient feedback, and navigation. Navigation preserves its own active and hover shades.
- **Traffic Violet** (`traffic`): histogram traffic, distinct from action fill.

### Secondary

- **Failure Red** (`red`, `red-soft`): failed checks and intent drift.
- **Execution Orange** (`error`, `error-bar`): execution and check errors.
- **Incomplete Amber** (`amber`, `amber-soft`): incomplete, suppressed, or unexecuted evidence.
- **Evaluated Green** (`green`, `green-soft`): aligned and passed evidence.

### Neutral

- **Ink** and **Muted Ink**: primary and supporting information.
- **Paper**, **Quiet Field**, and **Fine Rule**: reading surface, table headers, and boundaries.
- **Control Border**: input and button strokes.

**The Labeled Evidence Rule.** Pair outcome colors with text labels; failures, errors, incomplete evidence, and evaluated passes remain distinct.

## Typography

**Body Font:** the native sans stack recorded above.
**Label/Mono Font:** SFMono-Regular, Consolas, Liberation Mono, monospace.

Type is fixed and compact for operational reading. There is no display role. Ordinary headings use the native UI stack; the existing system-font wordmark does not establish a display-font convention.

### Hierarchy

- **Headline:** 23px, 650, 1.3; reduced to 20px at 520px.
- **Panel heading:** 20px, 600, 1.4, -.02em; wrapping trace title.
- **Title:** 13px, 600; compact section headings. Function introduction uses 17px; setup heading uses 22px, reduced to 20px on phones.
- **Body:** 13px, 1.5; descriptions and detail text also use 12px.
- **Label:** 11px; facets, metadata, badges, and chart labels. Table headings use 500; facet summaries use 600.
- **Metric:** 19px, 600, 1.3; reduced to 17px at 800px.
- **Code:** 11px mono, with 1.8 code-block line-height and 1.7 hash line-height. Endpoint text uses 12px mono.

**The Evidence Type Rule.** Use mono for code, function identifiers, and hashes; use tabular numerals for timing, counts, and trace facts.

## Layout

The desktop shell has a fixed 200px sidebar and a 47px topbar. Main content uses 28px horizontal gutters. The investigation grid pairs 182px facets with flexible results and an 18px results inset. The histogram is 97px high, with five summary columns. Tables use 9px 10px header padding and 11px 10px body padding. Named spacing steps record reused values, not a mathematical scale.

At 1150px the sidebar becomes a 58px icon rail and facets narrow to 160px. At 800px gutters become 18px, the toolbar wraps, search occupies a full row, and facets move into expandable Filters. At 520px the rail becomes 48px, summary totals use three columns with a second row, and the histogram becomes 75px high. Service, check-count, and start-time columns hide while trace, outcome, and duration remain. The Environment toolbar control hides, but the Environment facet remains available in Filters.

The right trace panel is `min(680px, 100vw)` wide. At 1550px and above the main content reserves its width. At 800px and below the panel becomes a modal dialog. The waterfall splits labels and timeline 46% / 54%. Phone panel gutters become 16px and attribute pairs stack.

## Elevation & Depth

Reading surfaces use tonal layering and thin rules. Structural shadows distinguish trace detail and transient feedback; search focus uses a tonal ring.

### Shadow Vocabulary

- **Trace panel:** `-8px 0 32px rgb(40 30 58 / .15)`.
- **Toast:** `0 5px 20px rgb(30 22 43 / .15)`.
- **Search focus:** `0 0 0 2px var(--violet-soft)`.

**The Flat Reading Rule.** Keep evidence tables and overview surfaces flat; reserve structural shadows for the trace panel and transient feedback.

## Shapes

Controls, selected navigation, and evidence callouts use 5px corners. Badges and filter chips use 4px; overview and toast use 6px. Count chips use 3px and timing bars 2px. Status markers are circles; service markers are squares. Tables and the trace panel keep straight structural edges. Icons are 18px inline SVG strokes, with 1.6 stroke width; compact controls use 14px SVGs.

## Components

### Buttons

White utility controls have a control-border stroke, 5px corners, and 8px 11px padding. Primary actions use violet and white; hover deepens to primary-hover. Secondary hover uses subtle fill and a lighter violet border. Small buttons use 11px type and 6px 9px padding; text actions underline on hover. Icon controls are 34px square. Disabled controls use opacity .48. Background and border transitions last 150ms. Keyboard focus uses a 2px violet outline with 3px offset.

### Chips and badges

Filter chips use violet-soft fill, deep violet text, a fine purple border, and 3px 6px padding. Outcome badges use labeled semantic colors and soft fills; source badges remain quieter. Phone badge padding is 2px 4px.

### Cards / Containers

The overview is a 6px frame with a 1px fine rule, compact chart, and divided totals. Evidence callouts use 5px corners, a soft status fill, and pale matching stroke. Tables remain contiguous and flat.

### Inputs / Fields

Search uses a 5px border, 6px 10px padding, 12px input, and mono shortcut hint. Focus-within changes its border to violet and adds a soft ring; the input removes its own outline. Select controls use 6px 8px padding and 11px selectors. Facets use native 12px checkboxes with violet accent color.

### Navigation

The dark violet sidebar uses light labels, 11px 10px item padding, and 5px selection shapes. Hover and active fills remain distinct. Below 1150px visible text hides while accessible labels remain. Investigation and detail tabs use violet text and a 2px selection underline.

### Trace table and waterfall

Trace names are buttons with ellipsis and supporting mono identifiers. Hover makes names violet and underlined; row hover is pale violet and selection uses violet-soft. Durations use 3px tracks. Waterfalls preserve hierarchy and proportional start/duration bars. Selecting a span reveals its checks. Hashes and detail headings wrap.

### Trace panel and feedback

The desktop panel is a complementary aside. At 800px and below it becomes a labeled modal dialog, focuses Close, contains Tab traversal, makes the main shell inert, and closes on Escape. Closing restores the matching trace control when available, with search as fallback. Refresh preserves matching filter, trace, histogram, and function focus. Toasts use deep violet, white text, and 6px corners. Reduced-motion preference removes transitions.

## Do's and Don'ts

### Do:

- **Do** preserve the dense explorer, facets, time controls, and proportional waterfall.
- **Do** keep Environment filtering available in mobile Filters.
- **Do** preserve visible focus and restore matching controls after updates.
- **Do** explicitly label synthetic traffic and platform self traces.
- **Do** distinguish missing and suppressed evidence from evaluated passes.

### Don't:

- **Don't** introduce ornamental hero typography or marketing layouts into investigation screens.
- **Don't** substitute color alone for an outcome label.
- **Don't** invent intent prose, arguments, results, or exception messages absent from SDK evidence.
- **Don't** apply this platform palette to the separate `site/` marketing surface.
