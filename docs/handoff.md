# Local review and next steps

The current local site is at http://127.0.0.1:8765 while the Flask process is running.
Start it again with the README command when needed. Review the visible filters and
Download buttons before connecting Vercel.

## Vercel, when the owner is ready

Use **one Vercel project** with Root Directory **`website`**. Both sites live at the
same origin under `/v1/transport` and `/v1/climate`; additional sites can follow the
same pattern. A separate Vercel address per site is unnecessary unless independent
projects/domains are desired.

The app follows [Vercel's Flask deployment convention](https://vercel.com/docs/frameworks/backend/flask):
`app.py` exposes `app`, `requirements.txt` declares Flask, and `public/` holds static
assets. `vercel.json` adds download and immutable-cache headers. No custom build command
or secrets are required. Do not deploy the repository root. No Vercel account connection,
project creation or deployment was attempted in this session.

After deployment, confirm that protection does not require Vercel login for the agent.
Run the GUI test against the actual public HTTPS address to verify CDN headers and
browser downloads as well as Flask routes:

```bash
uv run python scripts/test_gui.py --base-url https://YOUR-PROJECT.vercel.app
uv run python scripts/build_tasks.py --base-url https://YOUR-PROJECT.vercel.app
```

This updates only task configuration/reference material, not released file contents.
Do not use a changing preview URL for benchmark releases.

## ALE integration

Reviewed engine revision: `04b0599928317191ca6557847a456a70ab2d0438`.
Each folder in `tasks/` is self-contained and can be transferred into a task collection.
Task templates deliberately use a non-routable `.invalid` hostname until configured.

| Task | Required downloads |
| --- | --- |
| transport-january | January green taxi Parquet |
| transport-quarter | January, February, March green taxi Parquet |
| transport-comparison | January and March green taxi Parquet |
| climate-toronto | Toronto 2023 daily CSV |
| climate-two-stations | Toronto and Vancouver 2023 daily CSV |
| cross-collection | January taxi + Toronto 2023 climate, separate analyses |

Every task instructs `/home/user/output/`, keeps website filenames and scores exact
release bytes, with equal partial credit per requested file. Wrong content, incomplete
files, wrong filenames, directories, pipes and symlinks cannot earn file credit.
Extra output files are permitted, as stated in the instructions.

The task instruction states the outcome; it does not claim the hash verifier proves
GUI-only behavior. Use ALE's `computer-use` harness to evaluate GUI capability and
review screenshots/actions in `trajectory.json`. The oracle uses actual browser links
through Playwright, but is a scripted reference solver, not a model.

The image adds pinned Playwright 1.63.0 and its Chromium browser to ALE's desktop base.
Setup configures a user-owned download directory and starts a visible browser. The
base still uses upstream `latest`; resolve and pin its digest before a benchmark release.

Run from the ALE checkout:

```bash
uv run ale lint ../data-download-task/tasks
uv run ale validate ../data-download-task/tasks --runs-dir ../data-download-task/reports/runs
```

For a local Docker trial, the browser cannot use the host's `127.0.0.1`. Discover the
Docker bridge's host gateway with `docker network inspect bridge`, bind Flask to that
host bridge address, and generate a separate configured task copy:

```bash
# Replace DOCKER_BRIDGE_IP with the actual host bridge IP, not a container IP.
uv run flask --app website/app run --host DOCKER_BRIDGE_IP --port 8765
uv run python scripts/build_tasks.py --base-url http://DOCKER_BRIDGE_IP:8765 --output .local/tasks
```

Then point ALE at `../data-download-task/.local/tasks`. Do not publish that machine-local
address as the production task URL.

## Observed blockers and acceptance gates

- `ale lint` passes. Full `ale validate` was attempted and failed **before either
  untouched or oracle execution**, while fetching the ALE desktop base: GHCR anonymous
  token request returned 401 Unauthorized. Building the original base locally also
  failed while fetching layers with `tls: bad record MAC`. Obtain authorized access
  to the original image or complete the original source build on a working connection;
  an arbitrary non-ALE replacement image is not an equivalent validation.
- Setup's headed Chromium process and the headed oracle have not yet run inside ALE.
  Host website GUI tests and verifier unit tests do not establish that they work there.
- Networking is temporarily `open`. At this engine revision the setup browser does
  not inherit the agent-phase authenticated proxy, and CLI validation does not provide
  the oracle proxy. This is recorded in task metadata. Before benchmark admission,
  adapt the runner/browser proxy flow and verify an allowlist for the hosted origin,
  or have the benchmark owner explicitly accept the open-network task design.
- No model service/key is configured. Once available, use a computer-use-compatible
  Anthropic-messages endpoint and its supported model (do not invent a model name):

```bash
uv run ale run ../data-download-task/tasks/transport-january \
  --agent computer-use --model MODEL_NAME \
  --base-url MODEL_ENDPOINT --api-key-env MODEL_API_KEY \
  --runs-dir ../data-download-task/reports/runs
```

Here `--base-url` is the **model API endpoint**, while task `params.site_url` is the
website address. Keep credentials in the host environment/ALE `.env`, never the task
or website. Inspect screenshots, click actions and output artifacts alongside rewards;
do not treat a count of screenshots as proof of a download interaction.

Local task paths are not reportable benchmark provenance at this revision. Record the
final task commit, image digest, deployment URL, dataset hashes and RunLock before
presenting model results as reproducible benchmark evidence.

## Merge into later tasks

Copy the necessary browser image/setup pieces into the downstream task, incorporate
the download requirement into its instruction, and feed `/home/user/output/<filename>`
into subsequent analysis. Combine file checks with downstream analysis checks and
update oracle/timeout/network policy accordingly. Run untouched and full oracle
validation again for the combined task; these draft folders are not already validated
compositions.

The current remote is public. Local progress can be committed safely without pushing.
Before uploading evaluator references or patches, choose a private research repository
or split the public website from private tasks/audits. The ignored private evidence
bundle is local storage, not a remote backup.
