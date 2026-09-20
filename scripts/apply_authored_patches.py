"""Replay exact agent-authored patches after checking the selected clean values."""

import json
from generate_data import KEYS, ROOT, read_rows, skill, source_path, write_json

# Authored after reading all 18 selected records. Values are not random corruption.
PATCHES = {
    "green-2023-01": [
        (65, 14.77, 13.77, "The total omits the 1.00 improvement surcharge."),
        (157, 15.24, 12.49, "The total omits the 2.75 congestion surcharge."),
        (214, 19.91, 16.36, "The total omits the 3.55 tip."),
        (221, 25.06, 23.56, "The total omits the 1.50 tax."),
    ],
    "green-2023-02": [
        (134, 13.82, 12.82, "The total omits the 1.00 improvement surcharge."),
        (149, 36.52, 33.77, "The total omits the 2.75 congestion surcharge."),
        (198, 18.87, 17.87, "The total omits the 1.00 improvement surcharge."),
        (207, 11.57, 11.07, "The total omits the 0.50 tax."),
    ],
    "green-2023-03": [
        (130, 37.95, 31.03, "The total omits the 6.92 tip."),
        (150, 23.03, 22.03, "The total omits the 1.00 improvement surcharge."),
        (168, 11.19, 8.69, "The total omits the 2.50 extra charge."),
        (221, 24.62, 24.12, "The total omits the 0.50 tax."),
    ],
    "toronto-2023": [
        (
            71,
            "18.6",
            "1.8",
            "A decimal transcription gives 1.8 instead of 18.6 heating degree days for a mean of -0.6 C.",
        ),
        (80, "14.5", "145.0", "A decimal-place error scales 14.5 heating degree days by ten."),
        (
            238,
            "0.0",
            "1.4",
            "Cooling degree days were copied into heating degree days despite a mean above 18 C.",
        ),
    ],
    "vancouver-2023": [
        (37, "12.1", "121.0", "A decimal-place error scales heating degree days by ten."),
        (246, "1.9", "19.0", "A decimal-place error scales heating degree days by ten."),
        (359, "8.2", "2.8", "Transposed digits conflict with the 9.8 C mean and 18 C base."),
    ],
}

if __name__ == "__main__":
    for key in KEYS:
        out = ROOT / "data/generated" / key
        ext = source_path(key).suffix
        clean = out / ("synthetic-clean" + ext)
        rows = read_rows(clean)
        plan = json.loads((out / "corruption-plan.json").read_text())
        patches = []
        for target, (index, before, after, why) in zip(plan["targets"], PATCHES[key], strict=True):
            assert target["record_index"] == index
            field = target["suggested_field"][1:]
            assert rows[index][field] == before, (key, index, rows[index][field], before)
            patches.append(
                {k: target[k] for k in ["patch_id", "record_path", "record_index", "error_type"]}
                | {
                    "changes": [{"path": target["suggested_field"], "value": after}],
                    "explanation": why,
                }
            )
        write_json(out / "dirty-patches.json", dict(version=1, patches=patches))
        skill(
            "apply_patches.py",
            clean,
            out / "dirty-patches.json",
            "--plan",
            out / "corruption-plan.json",
            "--output",
            out / ("synthetic-dirty" + ext),
            "--manifest",
            out / "dirty-manifest.json",
        )
        try:
            skill(
                "validate_collections.py",
                "--source",
                source_path(key),
                "--clean",
                clean,
                "--dirty",
                out / ("synthetic-dirty" + ext),
                "--spec",
                out / "generation-spec.json",
                "--manifest",
                out / "dirty-manifest.json",
                "--output",
                out / "validation-report.json",
            )
        except Exception:
            report = json.loads((out / "validation-report.json").read_text())
            print(key, json.dumps(report.get("errors"), ensure_ascii=False)[:3500])
            raise
        else:
            print(key, "PASS")
