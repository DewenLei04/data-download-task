# Configure and validate the ALE download tasks

The website is deployed at https://data-download-task.vercel.app. In all seven `task.yaml` files, `params.site_url` points to this address. No further Vercel configuration is needed.

Each `tasks/<task-name>/` directory can be submitted to ALE independently:

- `task.yaml`: website URL, resources, timeout, and network policy.
- `instruction.md`: instructions for the agent.
- `image/`: installs Chromium and Playwright.
- `setup/`: starts the visible browser and configures `/home/user/output/` as the download directory.
- `oracle/`: reference solution that downloads through the website.
- `verify/`: checks filenames, sizes, and SHA-256 hashes.

## Validation without a model key

Run these commands from the adjacent `ale/` checkout. The seven committed tasks use the production domain:

```bash
uv run ale lint ../data-download-task/tasks
uv run ale validate ../data-download-task/tasks/corgis-airlines \
  --runs-dir ../data-download-task/reports/runs
# Validate all seven tasks
uv run ale validate ../data-download-task/tasks \
  --runs-dir ../data-download-task/reports/runs
```

`lint` checks task structure. `validate` creates containers and runs both the no-op baseline and the reference solution. The expected result is 0 for every no-op criterion and 1 for every oracle criterion, with matching criterion names. Results are saved in `reports/runs/validate-*/validation.json`, alongside logs and trajectories. The full run directories are ignored by Git and must be archived separately; public summaries are in `reports/`.

As of 2026-09-25, all seven tasks passed full container validation against a local instance of the same website after the desktop startup fix. The run ID is `validate-5a12c9be`. An earlier CORGIS task passed oracle validation directly against the production domain. A later production-domain CORGIS oracle attempt was interrupted by a timeout connecting this host to the Vercel edge. All seven real model episodes subsequently downloaded from the production site. See [ALE validation results](../reports/ale-validation.json).

These commands require a working ALE desktop base image. Pulling the public GHCR image returned HTTP 401 here, so the base image was built locally from ALE source. See [base-image provenance](../reports/ale-base-provenance.json). Docker images are not included in this GitHub repository; another machine must obtain or build its own base image.

To reproduce the successful local-container validation, bind Flask to the Docker bridge address and create temporary task copies with `scripts/build_tasks.py --base-url http://DOCKER_BRIDGE_IP:8765 --output .local/tasks`. Then run `ale validate` on `.local/tasks`. See [handoff notes](handoff.md). Do not submit the temporary bridge URL as a production task URL.

## Run a real GUI agent with a Codex subscription

ALE's [subscription-auth guide](https://github.com/AgentsLastExam/ale/blob/04b0599928317191ca6557847a456a70ab2d0438/docs/guides/subscription-auth.md) uses a login file dedicated to the ALE checkout. On a new machine, run this once from `ale/`:

```bash
mkdir -p .ale/auth/codex-cli
CODEX_HOME="$PWD/.ale/auth/codex-cli" codex login
chmod 0600 .ale/auth/codex-cli/auth.json
CODEX_HOME="$PWD/.ale/auth/codex-cli" codex login status
```

If a WSL browser reports that `localhost` refused the connection, use `CODEX_HOME="$PWD/.ale/auth/codex-cli" codex login --device-auth`. Never share the login file or token, or copy the normal `~/.codex` login file. Then run:

```bash
uv run ale run ../data-download-task/tasks/corgis-airlines \
  --agent codex-cli --auth subscription --model gpt-5.6-luna \
  --set 'agent.mcp_servers=[{ builtin = "cua-desktop" }]' \
  --runs-dir ../data-download-task/reports/runs
```

`cua-desktop` provides screenshots, clicks, and keyboard input. The task instructions require downloads through the visible browser. Inspect the score, desktop tool calls and screenshots in `trajectory.json`, and the files in `/home/user/output/`. Matching hashes alone do not establish that the agent used the GUI. The task images install Openbox; setup switches window managers and starts the desktop driver because the GNOME layer of the locally built ALE base image previously obscured the browser.

On 2026-09-25, seven real `gpt-5.6-luna` episodes downloaded from the production website: three single-file tasks used Codex CLI `0.139.0` and four multi-file tasks used `0.146.0`. All seven ALE scores were `1.0`, and SHA-256 matched for all 12 requested files. The agent navigated using visible desktop screenshots, clicks, scrolling, and typing. The `transport-comparison` episode also made two read-only terminal checks of downloaded files; it did not acquire data through the terminal. In the four newer CLI episodes, desktop calls were wrapped in `functions.exec`, and ALE did not retain the nested PNG images in its trajectory; the three older episodes retained screenshots. See [model GUI validation results](../reports/model-gui-validation.json).

These episodes used temporary local task copies with the same instructions and verification rules as the public tasks. Because this host repeatedly failed to download the Codex Linux executable component from npm, the temporary images preinstalled the local CLI and a stable CLI obtained from the official OpenAI release. Each task succeeded in one real model episode, but ALE marks local task paths as ineligible for a formally reportable, reproducible benchmark result.

## Use another model provider

In the reviewed ALE revision `04b0599`, the `computer-use` harness expects an Anthropic Messages-compatible computer-use service. After choosing a service URL and supported model, set its API key in the host environment and run:

```bash
uv run ale run ../data-download-task/tasks/corgis-airlines \
  --agent computer-use --model MODEL_NAME \
  --base-url MODEL_ENDPOINT --api-key-env MODEL_API_KEY \
  --runs-dir ../data-download-task/reports/runs
```

`MODEL_API_KEY` is an environment-variable name; never commit the key to the website, tasks, or Git. `--base-url` is the model-service URL, not the Vercel website URL. Inspect the score, downloaded files, screenshots, and click actions in `trajectory.json`. A passing oracle does not prove that a model can pass, and file hashes alone do not prove that the entire download used the GUI.

## Before handing the tasks over for integration

Record the task commit, ALE commit, image identifiers, website URL, data hashes, and actual run records. The tasks currently use `network.mode: open`; see [handoff notes](handoff.md) for the reason and limitations. Confirm the network policy before formal benchmark inclusion, and rerun validation after merging these tasks with downstream analysis tasks.
