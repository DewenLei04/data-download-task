# Data download tasks

Three reference-style synthetic data websites and seven draft ALE download tasks. The website is complete
and deployed at https://data-download-task.vercel.app. Production browser downloads
have been verified. Seven tasks passed ALE container untouched/oracle validation against
the identical site served on a local Docker bridge. A real ALE model run completed
each of the seven tasks against the production website.

- **TLC Trip Record Data** — `/v1/transport`, three monthly green taxi Parquet extracts.
- **Historical Climate Data** — `/v1/climate`, Toronto and Vancouver daily CSV exports.
- **CORGIS JSON Datasets** — `/v1/corgis`, 2015 airline statistics in a nested JSON file.
- **Collections** — `/`, a starting page linking all three websites.

All six public files are skill-generated synthetic dirty datasets, not copied source
files. The original field schemas are retained. There are 1,798 generated records and
21 intentionally dirty records in total. Source data, clean counterparts, error locations
and audit sidecars are kept outside the web deployment.

## Run locally

```bash
uv sync --frozen
uv run flask --app website/app run --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. No ALE installation, portal, database, API key or Vercel
account is needed to use the website. Keep the server running for GUI tests.

```bash
uv run pytest -q
uv run playwright install chromium
uv run python scripts/test_gui.py
```

The website tests run independently. Verifier tests additionally use the sibling
`../ale` checkout; they explicitly skip when it is absent. Linux systems missing
browser libraries may need Playwright's browser dependency installation.

## Current validation

| Check | Result |
| --- | --- |
| Supplied skill: v4 validation + semantic audit | 6/6 passed |
| Website, image integrity and real ALE verifier API tests | 24 passed |
| Production Chromium clicks and downloaded-file hashes | 26 downloads passed |
| Desktop review and mobile overflow checks | Passed |
| ALE task lint at `04b0599` | 7 task folders passed |
| ALE container `validate` | 7/7 passed against local bridge site (14 episodes) |
| Production-origin ALE `validate` | Earlier CORGIS image revision passed; updated reference run timed out on this host's Vercel route |
| ALE model-driven GUI run | 7/7 tasks passed against production; 12 requested files matched exact hashes |
| Vercel deployment | Live; anonymous access and all six file hashes verified |

The interfaces reproduce the reference sites’ page structure, colors and typography.
See [visual references and limits](docs/visual-reference.md).

The ALE result above exercised sandbox browser startup, headed oracle navigation and
file verification against the same six release files served from the local website.
All seven shipped tasks still use the production URL above. Full current-revision ALE
validation against that URL is pending: this host intermittently cannot connect to its
Vercel edge. Network policy is an explicitly documented draft limitation, not final
benchmark admission. The seven real model runs used local test images with
preinstalled Codex CLI 0.139.0 or 0.146.0 because npm native-binary downloads failed
on this host. ALE marks local task paths as non-reportable. The model navigated and
downloaded through the visible GUI; one run also used two read-only terminal checks
after the GUI interaction. See the
[model run report](reports/model-gui-validation.json) for the exact evidence and scope.

## Repository layout

```text
website/                 only directory to deploy to Vercel
  app.py                 Flask routes and filtering
  public/downloads/v1/   immutable synthetic release files
  templates/             reference-style transport, climate and CORGIS interfaces
scripts/                 source acquisition, skill pipeline, release and task builders
  apply_authored_patches.py  exact, reviewed corruption edits; evaluator material
tasks/                   seven self-contained ALE task folders; evaluator material
tooling/                 vendored user skill and task templates
tests/                   website behavior and negative verifier cases
docs/                    development, provenance, ALE review and handoff
reports/                 public-safe verification summaries
```

Local, ignored `data/raw/`, `data/generated/` and `data/releases/private/` preserve the
source snapshots and complete skill artifacts. `reports/screenshots/` contains the
actual browser captures. These directories are not backed up by a normal Git push.

The GitHub repository is public and has been pushed with the owner's authorization.
The deployed website exposes only `website/public/` assets and application routes;
task references and generation scripts belong to the research repository. Ignored
source snapshots, audit artifacts and screenshots remain local, not GitHub backups.

See [handoff](docs/handoff.md) for deployment, ALE setup and merging into other tasks;
[source provenance](docs/provenance.md) for dataset generation details; and the
[ALE integration review](docs/ale-integration-review.md) for reviewed contracts, and
[Chinese ALE quickstart](docs/ale-quickstart.zh-CN.md) for validation commands and scope.
