"""Publish only reviewed dirty artifacts; never export source/clean/answer sidecars."""

import hashlib
import json
import shutil
from generate_data import KEYS, ROOT, read_rows, source_path, write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release():
    catalog = []
    for key in KEYS:
        folder = ROOT / "data/generated" / key
        ext = source_path(key).suffix
        audit = json.loads((folder / "semantic-audit.json").read_text())
        validation = json.loads((folder / "validation-report.json").read_text())
        if not (audit["passed"] and validation["passed"]):
            raise ValueError(f"Unapproved dataset: {key}")
        for name, digest in audit["artifact_hashes"].items():
            if sha(folder / name) != digest:
                raise ValueError(f"Stale audit: {key}/{name}")
        filename = f"{key}-v1{ext}"
        dest = ROOT / "website/public/downloads/v1" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and sha(dest) != sha(folder / ("synthetic-dirty" + ext)):
            raise ValueError(f"Immutable v1 release differs: {filename}; create a new version")
        shutil.copyfile(folder / ("synthetic-dirty" + ext), dest)
        taxi = key.startswith("green")
        place = key.split("-")[0]
        catalog.append(
            dict(
                id=key,
                site="transport" if taxi else "climate",
                title=(
                    ["January", "February", "March"][int(key[-2:]) - 1] + " 2023 · Green taxi trips"
                )
                if taxi
                else place.title() + " International A · 2023",
                period=key[6:] if taxi else "2023",
                station="" if taxi else place,
                province="" if taxi else ("Ontario" if place == "toronto" else "British Columbia"),
                format=ext[1:].upper(),
                rows=len(read_rows(dest)),
                filename=filename,
                url="/downloads/v1/" + filename,
                bytes=dest.stat().st_size,
                sha256=sha(dest),
                columns=list(read_rows(dest)[0]),
            )
        )
    write_json(ROOT / "website/catalog.json", catalog)
    print(f"Published {len(catalog)} audited synthetic datasets.")


if __name__ == "__main__":
    release()
