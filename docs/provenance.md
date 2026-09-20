# Source and synthesis provenance

Reference retrieval dates: 2026-09-19 (TLC/climate), 2026-09-20 (CORGIS). Exact URLs, byte counts and SHA-256 hashes are in
[source-snapshots.json](source-snapshots.json). Acquisition is separate from the skill.
The skill works only on the resulting local input files.

## Website prototypes

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page):
  monthly archives, service selection and downloadable Parquet files. Reviewed through
  web retrieval. Direct HTML acquisition returned HTTP 403; no local full-page snapshot
  is claimed. The three public CloudFront Parquet objects downloaded successfully.
- [ECCC Historical Data](https://climate.weather.gc.ca/historical_data/search_historic_data_e.html):
  station/province/date selection and daily CSV exports. Its HTML is retained privately.

- [CORGIS Airlines JSON](https://corgis-edu.github.io/corgis/json/airlines/):
  JSON catalog, dataset overview, visible `.json` download and nested-field dictionary.
  Both catalog and detail reference pages were captured with Chromium.

The interfaces follow the reference page layouts, navigation, typography and colors.
The Canada header marks and NYC wordmark are stored locally with source attribution;
fonts are bundled with their OFL notices. Each page identifies the site as a research
replica and the observations as synthetic. See [visual-reference.md](visual-reference.md)
for screenshot evidence, exact assets, and the limits of the TLC reference.

## Local skill inputs

| Input | Original rows | Skill input/output rows | Seed | Dirty rows |
| --- | ---: | ---: | ---: | ---: |
| Green taxi January 2023 | 68,211 | 240 | 4100 | 4 |
| Green taxi February 2023 | 64,809 | 240 | 4101 | 4 |
| Green taxi March 2023 | 72,044 | 240 | 4102 | 4 |
| Toronto International A 2023 | 365 | 365 | 4103 | 3 |
| Vancouver International A 2023 | 365 | 365 | 4104 | 3 |
| CORGIS Airlines, complete 2015 panel | 4,408 | 348 | 4105 | 3 |

Traffic sampling first requires the requested pickup month, non-reversed timestamps,
0 < distance < 100 miles, 0 < fare < 500, and nonzero location codes. From eligible rows,
240 evenly spaced physical positions are selected without reordering. Eligible counts:
64,694 / 61,727 / 68,427. These are small test extracts, not population estimates.
Climate inputs are station IDs 51459 and 51442, daily timeframe 2, year 2023.

The supplied [generate-contextual-dirty-data skill](../tooling/generate-contextual-dirty-data/SKILL.md)
is vendored unchanged. Its SHA-256 is recorded with source snapshots. Each dataset has
its own v4 specification, profile, clean output, planner targets, agent-authored patches,
dirty output, manifest, deterministic report, semantic evidence and semantic audit.
All required artifacts remain in `data/generated/<dataset-id>/` locally.

## Declared generation model

Taxi records use canonical category placement as a scaffold. New distance, fare and
duration values are combined within service/rate strata. Extras and taxes are sampled
jointly within vendor/rate/time-band strata. Tips use observed ratios; total amounts
are recalculated. Both timestamps and measured transaction values are newly instantiated.
The model is intentionally compact and does not guarantee geographic route realism.

Climate records preserve station/calendar references and quality codes. Measurements
are combined within month, quality-flag and snow-state strata. Mean temperature and
18-degree-base heating/cooling degree days are recalculated; wind pairs are sampled
jointly. Sparse strata can reuse observed rows, as allowed by the skill contract:
32 Toronto and 27 Vancouver rows overlap exactly with source rows. The collections
as a whole are materially new; no original source file is served as a download.

Airlines generation uses two distinct same-airport/quarter donors and a common convex
weight for all statistical components. Flight totals, delay-minute totals and roster
counts are derived. Every airport/calendar scaffold remains in source-relative order.
See [CORGIS JSON details](corgis-json.md) for source anomalies, audit and reproduction.

Non-exempt changed-value ratios are approximately 51.8%, 52.6%, 52.1%, 63.7%, 64.4% and 92.7%.
All exceed the unchanged 50% skill minimum. Canonical references, calendar coordinates
and controlled vocabularies have explicit, evidence-backed novelty exemptions.
Convex mixing compresses extreme tails; these data are for workflow evaluation, not
scientific conclusions about actual weather or trips.

The selected dirty-record rates are 2% for traffic and 1% for climate/airlines, reflecting
residual errors in curated exports. The skill floors record counts, so actual rates
are 4/240 = 1.67% 3/365 = 0.82%, and 3/348 = 0.86%, below the 5% cap. Exact corruption values were
authored after reading all 21 planner-selected records. Traffic errors omit a fee or
tip from a total; climate errors mistranscribe a derived heating-degree-day value.
Airline errors omit cancelled or diverted flights from a total.
Every targeted record was reviewed, and every untargeted record matches its clean pair.

## Reproduce and release

```bash
uv run python scripts/acquire_sources.py
uv run python scripts/generate_data.py
uv run python scripts/apply_authored_patches.py
uv run python scripts/audit_data.py
uv run python scripts/generate_airlines.py prepare
uv run python scripts/generate_airlines.py apply
```

The acquisition script refuses upstream bytes that differ from the pinned snapshots.
The patch script refuses targets whose reviewed clean values changed. Deterministic
validation failures are fatal. A human/agent must review `semantic-evidence.json` and
write the required `semantic-audit.json` following the skill; the code does not
silently approve a new semantic audit. Existing audited v1 artifacts are already
available locally.

```bash
uv run python scripts/release_data.py
```

Publication checks both validation and audit success, binds the audit to artifact
hashes and refuses to replace a v1 file with different bytes. A changed dataset needs
a new release path and updated task references. Only synthetic dirty files are copied
to `website/public/`; all clean files, plans, patches and manifests stay private.
