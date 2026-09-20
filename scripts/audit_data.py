"""Measure semantic evidence; publishing requires a separately reviewed audit."""

import json
from generate_data import KEYS, ROOT, read_rows, source_path, write_json

FEE_FIELDS = [
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "congestion_surcharge",
    "ehail_fee",
]


def evidence(key):
    out = ROOT / "data/generated" / key
    ext = source_path(key).suffix
    source = read_rows(source_path(key))
    clean = read_rows(out / ("synthetic-clean" + ext))
    dirty = read_rows(out / ("synthetic-dirty" + ext))
    patches = json.loads((out / "dirty-patches.json").read_text())["patches"]
    errors = []
    taxi = key.startswith("green")
    for i, r in enumerate(clean):
        if taxi:
            ok = (
                r["lpep_dropoff_datetime"] >= r["lpep_pickup_datetime"]
                and r["trip_distance"] > 0
                and r["tip_amount"] >= 0
                and abs(r["total_amount"] - sum(r[n] or 0 for n in FEE_FIELDS)) < 0.011
            )
            ok = (
                ok
                and r["lpep_pickup_datetime"].strftime("%Y-%m") == key[6:]
                and (r["payment_type"] == 1 or r["tip_amount"] == 0)
            )
        elif r["Mean Temp (°C)"]:
            low, high, mean = [
                float(r[n]) for n in ["Min Temp (°C)", "Max Temp (°C)", "Mean Temp (°C)"]
            ]
            ok = (
                low <= mean <= high
                and abs(mean - (low + high) / 2) <= 0.051
                and abs(float(r["Heat Deg Days (°C)"]) - max(18 - mean, 0)) < 0.011
                and abs(float(r["Cool Deg Days (°C)"]) - max(mean - 18, 0)) < 0.011
            )
        else:
            ok = True
        if not taxi:
            ok = ok and all(
                not r[n] or float(r[n]) >= 0
                for n in [
                    "Total Rain (mm)",
                    "Total Snow (cm)",
                    "Total Precip (mm)",
                    "Snow on Grnd (cm)",
                ]
            )
            ok = ok and r["Date/Time"] == f"{r['Year']}-{r['Month']}-{r['Day']}"
            for flag in [n for n in r if n.endswith("Flag")]:
                # Every quality code remains at its supported calendar position.
                ok = ok and r[flag] == source[i][flag]
        if not ok:
            errors.append(i)
    numeric = (
        ["trip_distance", "fare_amount", "total_amount"]
        if taxi
        else ["Max Temp (°C)", "Min Temp (°C)", "Total Precip (mm)"]
    )
    ranges = {}
    for n in numeric:
        src = [float(r[n]) for r in source if r[n] not in (None, "")]
        new = [float(r[n]) for r in clean if r[n] not in (None, "")]
        ranges[n] = {
            "source": [min(src), max(src)],
            "clean": [min(new), max(new)],
            "mean_source": round(sum(src) / len(src), 3),
            "mean_clean": round(sum(new) / len(new), 3),
        }
    patch_checks = []
    for p in patches:
        i = p["record_index"]
        r = dirty[i]
        violated = (
            abs(r["total_amount"] - sum(r[n] or 0 for n in FEE_FIELDS)) > 0.01
            if taxi
            else abs(float(r["Heat Deg Days (°C)"]) - max(18 - float(r["Mean Temp (°C)"]), 0))
            > 0.01
        )
        patch_checks.append(
            dict(
                patch_id=p["patch_id"],
                record_index=i,
                passed=violated,
                evidence=p["explanation"],
                changes=p["changes"],
            )
        )
    targeted = {p["record_index"] for p in patches}
    unchanged = all(a == b for i, (a, b) in enumerate(zip(clean, dirty)) if i not in targeted)
    report = json.loads((out / "validation-report.json").read_text())
    result = dict(
        key=key,
        clean_constraint_failures=errors,
        numeric_evidence=ranges,
        patch_checks=patch_checks,
        untargeted_unchanged=unchanged,
        validation_passed=report["passed"],
        novelty=report["summary"]["novelty"][""]["changed_value_ratio"],
        source_overlap=report["summary"]["exact_source_row_overlap_counts"][""],
    )
    write_json(out / "semantic-evidence.json", result)
    return result


if __name__ == "__main__":
    for key in KEYS:
        print(json.dumps(evidence(key), ensure_ascii=False))
