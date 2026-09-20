"""Materialize six self-contained ALE tasks for a specified deployment URL."""

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    (
        "transport-january",
        ["green-2023-01"],
        "Find the Metro Data green taxi trip extract for January 2023 and download its Parquet file.",
    ),
    (
        "transport-quarter",
        ["green-2023-01", "green-2023-02", "green-2023-03"],
        "Collect the Metro Data green taxi trip extracts for the first quarter of 2023. Download all three monthly Parquet files.",
    ),
    (
        "transport-comparison",
        ["green-2023-01", "green-2023-03"],
        "Prepare the Metro Data green taxi extracts for a January-versus-March 2023 comparison. Download the two monthly Parquet files.",
    ),
    (
        "climate-toronto",
        ["toronto-2023"],
        "Find the Northstar daily climate dataset for Toronto International A in Ontario for 2023. Download its CSV file.",
    ),
    (
        "climate-two-stations",
        ["toronto-2023", "vancouver-2023"],
        "Collect the Northstar 2023 daily climate CSV files for Toronto International A in Ontario and Vancouver International A in British Columbia.",
    ),
    (
        "cross-collection",
        ["green-2023-01", "toronto-2023"],
        "Collect two inputs for separate analyses: the Metro Data January 2023 green taxi Parquet extract and the Northstar Toronto International A 2023 daily climate CSV. The transport and climate records refer to different cities; no geographic join is requested.",
    ),
]


def build(base_url, destination):
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "Provide an HTTP(S) website base URL without credentials, query or fragment"
        )
    catalog = {d["id"]: d for d in json.loads((ROOT / "website/catalog.json").read_text())}
    for name, keys, instruction in TASKS:
        folder = destination / name
        shutil.copytree(ROOT / "tooling/task-template", folder, dirs_exist_ok=True)
        manifest = dict(
            spec_type="core/v1",
            name=name,
            environment="core/standard",
            os="linux",
            image=dict(kind="container"),
            resources=dict(cpus=2, memory_mb=3072),
            network=dict(mode="open"),
            timeouts=dict(setup=120, agent=900, verify=120),
            artifacts=["/home/user/output"],
            params=dict(site_url=base_url.rstrip("/")),
            metadata=dict(
                tags=["data-download", "browser", "synthetic-data"],
                status="draft-pending-container-and-model-validation",
                network_justification="The task inherently downloads from a hosted website. At ALE 04b0599, allowlist proxy settings are not inherited by the setup-launched GUI browser and CLI validate does not provision an oracle proxy. Open networking is a temporary integration limitation; narrow it before benchmark admission.",
            ),
        )
        (folder / "task.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
        (folder / "instruction.md").write_text(
            "# Download research data\n\nStart at ${site_url}.\n\n"
            + instruction
            + "\n\nSave the original downloaded files in `/home/user/output/`, keeping the filenames offered by the website. Do not edit or re-export the contents. The browser is configured to download into this directory. Additional files do not affect the score; each requested file receives equal credit.\n\nThe website contains synthetic research fixtures, not official observations.\n"
        )
        selected = [catalog[k] for k in keys]
        (folder / "verify/expected.json").write_text(
            json.dumps(
                [{k: d[k] for k in ("id", "filename", "bytes", "sha256")} for d in selected],
                indent=2,
            )
            + "\n"
        )
        (folder / "oracle/solution.json").write_text(
            json.dumps(
                [
                    {
                        k: d[k]
                        for k in ("site", "period", "station", "province", "format", "filename")
                    }
                    for d in selected
                ],
                indent=2,
            )
            + "\n"
        )
        for file in folder.glob("*/run.sh"):
            file.chmod(0o755)
    print(f"Wrote {len(TASKS)} ALE tasks to {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "tasks")
    args = parser.parse_args()
    build(args.base_url, args.output)
