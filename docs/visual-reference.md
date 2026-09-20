# Reference-style website implementation

The interface contract is to reproduce the source sites' recognizable layout,
typography, colors and navigation, simplifying only unrelated services and unavailable
data. The download contents remain the previously audited skill-generated v1 files.

## Canada Historical Data

Reference: https://climate.weather.gc.ca/historical_data/search_historic_data_e.html

Captured successfully with Chromium at 1440 × 1080. The full-page screenshot and
computed styles are retained in `reports/screenshots/reference/`. The implementation
matches the 1170px outer container, 1140px content area, government-signature header,
search box, dark menu, breadcrumbs, red-underlined title and bordered search tabs.
Measured original title: x=150, y=249.14, width=1140, Lato 700 at 38px. Local title:
x=150, y=249, width=1140, the same bundled Lato face and size. Noto Sans is used for
body text and form controls. These measurements establish specific matched properties,
not a claimed pixel-identical score for the entire page.

Station-name and province search work, including contains/begins-with name matching.
The unsupported proximity search is replaced by a link to all available stations.
Date controls are restricted to the actual 2023 daily exports. The footer omits the
many unrelated federal service links. Results and detail pages follow the same GCWeb
visual language; they are adapted for the two synthetic station exports, not claimed
as exact copies of every upstream results/detail page.

## NYC TLC Trip Record Data

Reference: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

Direct Chromium and wget requests returned 403. The current text structure was
retrieved with the web tool, and the visual layout was checked against existing page
screenshots at:

- https://rsangole.github.io/oman-rusers-arrow/images/nyc.jpg
- https://datatalks.club/docs/assets/images/data-engineering-zoomcamp/launch/taxi-data.jpg

These are older secondary screenshots, not a successful capture of the current live
page. The black utility bar, centered yellow NYC mark, gray main navigation, blue/yellow
secondary navigation, left sidebar, blue title and document-style download archive are
reproduced. Arial/Helvetica is used to approximate the sans-serif typography visible
in those references; the current TLC computed font could not be verified.

The archive expands by year and provides per-month Parquet links. Only the available
synthetic 2023 months are shown. Unrelated agency services, translation and document
links are simplified. A current live screenshot would allow a tighter final comparison;
the page is not labeled as a pixel-verified reproduction.

## Local assets

Fonts and marks are served locally: no Google Fonts or government-hosted resources
are requested by the deployed page at runtime. Asset URLs and checksums are recorded
in `visual-assets.json`. Noto Sans and Lato OFL notices are retained with the fonts.
The Canada marks come from the reference site's GCWeb distribution. The NYC SVG
comes from CityOfNewYork/nyc-core-framework with its MIT notice retained; its color
is supplied by CSS in the header.
These marks identify the reference appearance; the page explicitly says it is an
independent research replica, not an official government service.

## Validation

- Host Chromium covers the year accordion, expand/collapse controls, station-name and
  province tabs, keyboard tab navigation, header search, menu and all download surfaces.
- All six tasks' shipped oracle navigation functions run against the local website.
- 23 download events match the unchanged release file hashes.
- No external runtime requests, browser script errors or 390px document overflow.
- These are host browser checks. ALE container/model validation remains separately
  pending as described in `handoff.md`.
