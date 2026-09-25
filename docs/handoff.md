# Deployment and next steps

The current local site is at http://127.0.0.1:8765 while the Flask process is running.
Start it again with the README command when needed. The production site is
https://data-download-task.vercel.app and can be accessed without logging in.

## Vercel deployment

Use **one Vercel project** with Root Directory **`website`**. All three sites live at the
same origin under `/v1/transport`, `/v1/climate` and `/v1/corgis`; additional sites can follow the
same pattern. A separate Vercel address per site is unnecessary unless independent
projects/domains are desired.

The app follows [Vercel's Flask deployment convention](https://vercel.com/docs/frameworks/backend/flask):
`app.py` exposes `app`, `requirements.txt` declares Flask, and `public/` holds static
assets. `vercel.json` adds download and immutable-cache headers. No custom build command
or secrets are required. The owner connected GitHub and deployed the project with
`website/` as its root. Pushing changes to the connected branch updates the deployment.

Production checks passed: anonymous page access, all six immutable download hashes,
26 browser download events, seven shipped oracle navigation functions and 390px
document overflow checks. Source/audit/task paths return 404. Reports are in
`reports/gui-validation.json` and `reports/vercel-validation.json`. To repeat:

```bash
uv run python scripts/test_gui.py --base-url https://data-download-task.vercel.app
uv run python scripts/build_tasks.py --base-url https://data-download-task.vercel.app
```

The task builder updates configuration/reference material, not released file contents.
Do not use a changing preview URL for benchmark releases.

## ALE integration

Reviewed engine revision: `04b0599928317191ca6557847a456a70ab2d0438`.
Each folder in `tasks/` is self-contained and can be transferred into a task collection.
All seven shipped task manifests now point to the production domain.

| Task | Required downloads |
| --- | --- |
| corgis-airlines | 2015 airport-month statistics JSON, 29 airports |
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
through Playwright, but is a scripted reference solver, not a model. Its navigation
functions have been exercised for all seven tasks in host Chromium and in ALE's headed
Docker sandbox against the local copy of the same website and release files.

The image adds SHA-256 verified Playwright 1.63.0 wheels and its Chromium browser to
ALE's desktop base. The browser and oracle honor `HTTPS_PROXY` when one is supplied.
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

- `ale lint` passes. After the desktop setup change, all seven tasks passed full
  `ale validate` against the same site and released files on
  `http://172.17.0.1:8765`: seven untouched episodes scored all zero and seven headed
  oracle episodes scored all one. The current run is
  `reports/runs/validate-5a12c9be`; its public summary is `reports/ale-validation.json`.
- The published ALE desktop base returned 401 from anonymous GHCR access. A local
  source build succeeded using checksum-verified cached assets and the original desktop
  services. `reports/ale-base-provenance.json` records its changes and observed ID.
  This is a local build, not proof of the published image's digest.
- An earlier CORGIS task image passed a direct production-origin ALE reference run
  with no host proxy. The updated image's CORGIS reference run passed the untouched
  case but timed out loading the production page in the oracle. This host's route to
  some Vercel edge addresses is intermittent. Full production-origin reference
  validation remains pending a stable connection. Production host Chromium completed
  26 download events, and three real model GUI runs against production passed.
- Networking is temporarily `open`. At this engine revision the setup browser does
  not inherit the agent-phase authenticated proxy, and CLI validation does not provide
  the oracle proxy. This is recorded in task metadata. Before benchmark admission,
  adapt the runner/browser proxy flow and verify an allowlist for the hosted origin,
  or have the benchmark owner explicitly accept the open-network task design.
- ALE checkout-local ChatGPT subscription login is configured on this host. Three real
  `gpt-5.6-luna` / Codex CLI GUI episodes completed against the production CORGIS,
  TLC and climate pages: each overall reward is 1.0, all JSON/Parquet/CSV hashes
  match, and every agent tool call used CUA. See `reports/model-gui-validation.json`.
  The remaining four multi-file or cross-collection tasks have no model run yet.
  This local-path result is not reportable as a re-fetchable benchmark RunLock.
- This host repeatedly lost the npm Linux Codex executable download, so that model
  episode used a test-only local image with preinstalled Codex CLI 0.139.0. The local
  ALE base's GNOME desktop layer obscured application windows; Openbox resolved that
  in screenshot preflight and is now installed and started by all seven task images.
  The task setup also starts Cua Driver before the agent begins. Exact commands and
  GUI evidence checks are in `docs/ale-quickstart.zh-CN.md`.
- Alternatively, use a computer-use-compatible Anthropic-messages endpoint and its
  supported model (do not invent a model name):

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

The public research repository has been pushed with the owner's authorization. Full
source snapshots, generated clean/dirty pairs, semantic audits and screenshots remain
in ignored local directories. The ignored private evidence bundles are local storage,
not remote backups. The CORGIS additions are described in `corgis-json.md`.
