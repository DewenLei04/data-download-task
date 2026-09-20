# CORGIS JSON website and generated airline data

Reference catalog: https://corgis-edu.github.io/corgis/json/

Reference detail: https://corgis-edu.github.io/corgis/json/airlines/

Original JSON: https://corgis-edu.github.io/corgis/datasets/json/airlines/airlines.json

The third website is `/v1/corgis`. Its search box filters the catalog as the user
types; Enter also supports a server-rendered query. The Airlines card opens
`/v1/corgis/datasets/airlines-2015`, whose Download section contains a visible
`airlines-2015-v1.json` link that triggers a browser attachment download.
It shares the same Flask/Vercel project as the two existing websites.

## Source and skill process

Acquisition is performed separately from the user-provided
[generate-contextual-dirty-data skill](../tooling/generate-contextual-dirty-data/SKILL.md).
The downloaded source has 4,408 records. Select every record whose `Time.Year` is
2015, retaining physical order and every field, and pass that local 348-record JSON
extract to the skill. This is a complete year, not a truncated first-page sample.

The sole logical collection is the root array. Each record has three nested objects,
`Airport`, `Time` and `Statistics`, with 24 scalar leaf fields and no nested arrays.
The output has 29 airports × 12 months. Month blocks are ascending and airports are
alphabetical within each block; airport identifiers recur at interleaved positions.
Calendar, airport identities and historical carrier names are canonical references.

The declared seed is 4105. For each final airport-month position, two distinct months
from the same airport and quarter jointly supply a convex mixture of outcome counts,
delay causes and delay minutes. One common weight preserves multivariate relationships.
Totals are derived from generated components. Carrier rosters are sampled from an
observed compatible donor and their counts are recalculated. No shuffle is applied.

Source inspection found two minute totals exceeding their components by four minutes
(indices 23 and 66); the clean generator repairs this by deriving every total.
Cause counts and delayed-flight totals can differ slightly due to source rounding;
the generated residual is -4 through +4 and is deliberately retained. The actual
source month numbers are 1–12, despite a zero-based description on the original page.

The skill's version 4 specification is written before generation. Its planner selects
3 records at a 1% configured rate (`floor(348 × .01)`); actual rate is 0.8621%.
After reading each selected clean record, exact omitted-component patches are authored
and then applied with the skill. The published data changes only three total cells.
Clean/dirty counterparts, specification, plan, patches, manifest, validation, evidence
and semantic audit remain in ignored `data/generated/airlines-2015/`.

Mechanical validation and semantic audit pass: 92.7485% of non-exempt values changed,
zero exact source-row overlap, zero high-similarity records, no clean constraint or
conditional-support violations, and all 345 untargeted records unchanged from clean.
This is a source-conditioned download fixture, not a validated scientific simulator.

## Reproduction and release

```bash
uv run python scripts/acquire_sources.py
uv run python scripts/generate_airlines.py prepare
uv run python scripts/generate_airlines.py apply
```

Review `semantic-evidence.json` and author the skill's `semantic-audit.json`, including
hashes of the generation artifacts. The script does not automatically approve an
audit. Then run `uv run python scripts/release_data.py`; publication checks both
reports, artifact hashes and immutable v1 bytes. The existing five files are unchanged.

## GUI and ALE checks

The `corgis-airlines` task asks for the complete 2015 airport-month JSON. Its oracle
types in the visible search box, opens the Airlines card and clicks Download JSON.
The verifier uses the same exact-byte, regular-file checks as the existing tasks.

Host Chromium verifies the filename, SHA-256 and parsed nested JSON after an actual
download event. It also checks empty search, case-insensitive matching, restoring
results, the 24-field dictionary, desktop geometry and 390px document overflow.
The project has 22 passing pytest cases, 26 successful GUI downloads across all
surfaces/oracles, and seven task folders passing ALE lint.

These are host browser and verifier checks. A model GUI agent has not been run;
ALE container validation remains blocked by the previously observed base-image
access issue. Vercel deployment remains deferred by the owner.
