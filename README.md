# Data download tasks

Two reference-style synthetic data websites and six draft ALE download tasks. The website is complete
and tested locally. Vercel deployment and model-driven ALE execution are deferred.

- **TLC Trip Record Data** — `/v1/transport`, three monthly green taxi Parquet extracts.
- **Historical Climate Data** — `/v1/climate`, Toronto and Vancouver daily CSV exports.
- **Collections** — `/`, a starting page linking both websites.

All five public files are skill-generated synthetic dirty datasets, not copied source
files. The original field schemas are retained. There are 1,450 generated records and
18 intentionally dirty records in total. Source data, clean counterparts, error locations
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
| Supplied skill: v4 validation + semantic audit | 5/5 passed |
| Website and real ALE verifier API tests | 19 passed |
| Chromium clicks and downloaded-file hashes | 23 downloads passed |
| Desktop review and mobile overflow checks | Passed |
| ALE task lint at `04b0599` | 6 task folders passed |
| ALE container `validate` | Blocked before execution: base image returns 401 |
| ALE model-driven GUI run | Not run; model service not configured |
| Vercel deployment | Not started, as requested |

The interfaces reproduce the reference sites’ page structure, colors and typography.
See [visual references and limits](docs/visual-reference.md).

Host verifier unit tests are **not** a substitute for the full ALE untouched/oracle
pipeline. The task image, sandbox browser startup and headed oracle remain unverified
inside ALE. Task URLs deliberately use `.invalid` until configured. Network policy is
an explicitly documented draft limitation, not final benchmark admission.

## Repository layout

```text
website/                 only directory to deploy to Vercel
  app.py                 Flask routes and filtering
  public/downloads/v1/   immutable synthetic release files
  templates/             reference-style transport and climate interfaces
scripts/                 source acquisition, skill pipeline, release and task builders
  apply_authored_patches.py  exact, reviewed corruption edits; evaluator material
tasks/                   six self-contained ALE task folders; evaluator material
tooling/                 vendored user skill and task templates
tests/                   website behavior and negative verifier cases
docs/                    development, provenance, ALE review and handoff
reports/                 public-safe verification summaries
```

Local, ignored `data/raw/`, `data/generated/` and `data/releases/private/` preserve the
source snapshots and complete skill artifacts. `reports/screenshots/` contains the
actual browser captures. These directories are not backed up by a normal Git push.

The remote repository was public when checked. No remote push was performed in this
work: `tasks/`, generation patches and private audits can reveal evaluator references.
Before sharing, make the research repository private, or publish only `website/` in a
separate public repository and retain evaluator materials privately.

See [handoff](docs/handoff.md) for deployment, ALE setup and merging into other tasks;
[source provenance](docs/provenance.md) for dataset generation details; and the
[ALE integration review](docs/ale-integration-review.md) for reviewed contracts.
