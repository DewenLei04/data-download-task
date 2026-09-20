"""Execute the agent-declared source model, then the vendored skill planner.

Patch values are authored separately after examining planner targets. This script
never invents dirty values. Run from the repository root with `uv run`.
"""

import csv
import json
import random
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "tooling/generate-contextual-dirty-data/scripts"
KEYS = [f"green-2023-{m:02}" for m in range(1, 4)] + ["toronto-2023", "vancouver-2023"]


def pointer(name):
    return "/" + name.replace("~", "~0").replace("/", "~1")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def source_path(key):
    return ROOT / "data/raw" / (key + ("-sample.parquet" if key.startswith("green") else ".csv"))


def read_rows(path):
    if path.suffix == ".parquet":
        return pq.read_table(path).to_pylist()
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def skill(script, *args):
    subprocess.run(
        [sys.executable, str(SKILL / script), *map(str, args)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def generate(key, seed):
    path = source_path(key)
    out = ROOT / "data/generated" / key
    skill("inspect_dataset.py", path, "--output", out / "structure-report.json")
    profile = json.loads((out / "structure-report.json").read_text())
    source = read_rows(path)
    taxi = key.startswith("green")
    names = list(source[0])
    categorical = (
        [
            "VendorID",
            "store_and_fwd_flag",
            "RatecodeID",
            "PULocationID",
            "DOLocationID",
            "payment_type",
            "trip_type",
        ]
        if taxi
        else names[:9] + [x for x in names if x.endswith("Flag")]
    )
    representation_names = (
        [
            "VendorID",
            "PULocationID",
            "DOLocationID",
            "RatecodeID",
            "trip_type",
            "store_and_fwd_flag",
            "lpep_pickup_datetime",
            "lpep_dropoff_datetime",
        ]
        if taxi
        else names[:8] + ["Max Temp (°C)", "Min Temp (°C)"]
    )
    protected = categorical + (["lpep_pickup_datetime"] if taxi else [])
    dimensions = [
        dict(
            name="regime",
            scope="dataset",
            paths=[],
            evidence=f"{len(source)} records; filename {path.name}; complete profile in structure-report.json",
            constraint_kind="hard",
            generation_strategy="generate_conditionally",
            generation_rule="Keep source month, taxi service, or station and calendar year. These are small synthetic samples, not reconstructions of actual observations.",
        ),
        dict(
            name="reference_vocabulary",
            scope="group",
            paths=[pointer(n) for n in categorical],
            evidence="Whole-column closed category, station metadata, calendar and flag profiles.",
            constraint_kind="hard",
            generation_strategy="reuse_observed",
            generation_rule="Use canonical metadata and category placement from the source as the scaffold, while generating measurements and transactions anew. Keys retain observed equality and physical layout.",
        ),
        dict(
            name="joint_measurements",
            scope="relation",
            paths=[pointer(n) for n in names if n not in categorical],
            evidence="Numeric ranges, null patterns and category strata measured across all input rows.",
            constraint_kind="soft",
            generation_strategy=["recombine_conditionally", "derive"],
            generation_rule=(
                "Choose two same-rate, same-trip-type trips at final row positions. Convexly combine distance, duration and fare. Sample extra and tax jointly from a same-vendor, same-rate and same six-hour time-band donor; preserve zone-related fees. Recalculate cash/card-compatible tips from a single observed ratio and exact component total. New pickup times inhabit the same calendar/time-of-day regime."
                if taxi
                else "Choose two days from the same month and the same complete quality-flag and snow-state stratum. Convexly combine min/max temperature and nonnegative rain/snow/precipitation, retaining joint precipitation ratios. Derive mean and degree days at base 18 C. Recombine gust pairs and snow depth from one compatible donor. Preserve incomplete-observation flags."
            ),
        ),
        dict(
            name="physical_placement",
            scope="sequence",
            paths=[pointer(n) for n in representation_names],
            evidence=profile["representation_summary"],
            constraint_kind="hard",
            generation_strategy="generate_conditionally",
            generation_rule="Generate each output directly at its final source-relative slot. Retain daily calendar cadence or taxi categorical scaffold; do not shuffle generated records.",
        ),
    ]
    fields = []
    by_path = {f["path"]: f for f in profile["fields"]}
    for name in names:
        p = by_path[pointer(name)]
        fields.append(
            dict(
                path=pointer(name),
                meaning=name,
                physical_type=list(p["physical_types"]),
                nullable=p["null_or_empty_count"] > 0,
                generation_guidance="Canonical scaffold"
                if name in categorical
                else dimensions[2]["generation_rule"],
                corruption_prohibited=name in protected,
            )
        )
    rule = dict(
        name="chronology" if taxi else "temperature_bounds",
        kind="comparison",
        left=pointer("lpep_dropoff_datetime" if taxi else "Max Temp (°C)"),
        operator=">=",
        right=pointer("lpep_pickup_datetime" if taxi else "Min Temp (°C)"),
        coerce="string" if taxi else "number",
        allow_null=not taxi,
    )
    spec = dict(
        version=4,
        source=dict(
            physical_format=path.suffix[1:],
            collections=[
                dict(
                    record_path="",
                    record_count=len(source),
                    role="trip transactions" if taxi else "daily station observations",
                    handling="generate",
                )
            ],
        ),
        scenario_inference=dict(
            domain="transport" if taxi else "climate",
            dataset_role="synthetic downloadable research extract",
            record_meaning="one taxi trip" if taxi else "one station-day",
            producer="metered service export" if taxi else "curated weather station export",
            curation_level="medium",
            confidence=0.93,
            evidence=[path.name, "Full-column inspection report"],
            assumptions=[
                "A compact sample is sufficient for download tasks; not a scientifically representative simulation.",
                "Fixed canonical references retain their real labels; all published observations are synthetic.",
            ],
        ),
        generation=dict(
            record_count=len(source),
            random_seed=seed,
            source_model=dict(default_source_reuse="allow", dimensions=dimensions),
            collections=[
                dict(
                    record_path="",
                    record_count=len(source),
                    primary_identifiers=[] if taxi else [pointer("Date/Time")],
                    grouping_keys=[
                        pointer(n)
                        for n in (
                            ["VendorID", "PULocationID", "DOLocationID"]
                            if taxi
                            else ["Station Name", "Month"]
                        )
                    ],
                    protected_fields=[pointer(n) for n in protected],
                    fields=fields,
                    representation=dict(
                        generation_mode="direct",
                        record_order=dict(
                            policy="match_source",
                            generation_guidance=dimensions[3]["generation_rule"],
                        ),
                        field_profiles=[
                            dict(
                                path=pointer(n),
                                value_role="reference_or_sequence",
                                cardinality="match_source",
                                sequence_policy="match_source",
                                record_layout="match_source",
                                linked_paths=[],
                                direct_generation_guidance=dimensions[3]["generation_rule"],
                            )
                            for n in representation_names
                        ],
                    ),
                    novelty=dict(
                        minimum_changed_value_ratio=0.5,
                        high_similarity_threshold=0.8,
                        maximum_high_similarity_record_ratio=0.5,
                        exemptions=[
                            dict(
                                path=pointer(n),
                                reason="Canonical category/reference/quality vocabulary or calendar coordinate; not a measured outcome.",
                            )
                            for n in categorical
                        ],
                    ),
                    hard_constraints=[
                        "Exact source schema and counts",
                        "Valid chronology and component-sum total; nonnegative distance and tips"
                        if taxi
                        else "Min <= mean <= max; degree days derived from mean; precipitation nonnegative; flags coherent with missingness",
                    ],
                    soft_constraints=[
                        "Preserve empirical source regimes and conditional measurement support"
                    ],
                    machine_rules=[rule],
                )
            ],
        ),
        dirty_policy=dict(
            unit="record",
            max_rate=0.05,
            selected_rate=0.02 if taxi else 0.01,
            rationale="Small residual arithmetic errors in a curated transaction export."
            if taxi
            else "Rare derived-field transcription errors in a curated scientific export.",
            collection_coverage=dict(mode="all_eligible_when_feasible"),
            error_types=[
                dict(
                    name="total_component_mismatch" if taxi else "degree_day_mismatch",
                    weight=1,
                    eligible_record_paths=[""],
                    eligible_fields=[pointer("total_amount" if taxi else "Heat Deg Days (°C)")],
                    constraint_violated="Derived amount must match its inputs.",
                )
            ],
        ),
        quality=dict(
            source_row_overlap_policy="allow",
            source_identifier_overlap_policy="allow",
            require_exact_record_count=True,
        ),
    )
    write_json(out / "generation-spec.json", spec)
    rng = random.Random(seed)
    generated = []
    for template in source:
        row = dict(template)
        if taxi:
            pool = [
                r
                for r in source
                if r["RatecodeID"] == template["RatecodeID"]
                and r["trip_type"] == template["trip_type"]
            ]
            a, b = rng.choice(pool), rng.choice(pool)
            w = rng.uniform(0.25, 0.75)
            row["trip_distance"] = round(w * a["trip_distance"] + (1 - w) * b["trip_distance"], 2)
            row["fare_amount"] = round(w * a["fare_amount"] + (1 - w) * b["fare_amount"], 2)
            row["passenger_count"] = rng.choice(pool)["passenger_count"]
            # Keep the time-of-day window, but instantiate new trip timestamps.
            row["lpep_pickup_datetime"] = template["lpep_pickup_datetime"].replace(
                second=rng.randrange(60), microsecond=0
            )
            duration = (
                w * (a["lpep_dropoff_datetime"] - a["lpep_pickup_datetime"]).total_seconds()
                + (1 - w) * (b["lpep_dropoff_datetime"] - b["lpep_pickup_datetime"]).total_seconds()
            )
            row["lpep_dropoff_datetime"] = row["lpep_pickup_datetime"] + timedelta(
                seconds=max(1, round(duration))
            )
            tip_donor = rng.choice(pool)
            row["tip_amount"] = (
                round(
                    row["fare_amount"]
                    * (tip_donor["tip_amount"] / max(tip_donor["fare_amount"], 1)),
                    2,
                )
                if template["payment_type"] == 1
                else 0.0
            )
            fee_pool = [
                r
                for r in pool
                if r["VendorID"] == template["VendorID"]
                and r["lpep_pickup_datetime"].hour // 6
                == template["lpep_pickup_datetime"].hour // 6
            ]
            fee_donor = rng.choice(fee_pool)
            row["extra"], row["mta_tax"] = fee_donor["extra"], fee_donor["mta_tax"]
            # Bound the empirical ratio using observed tip support.
            row["tip_amount"] = min(row["tip_amount"], max(r["tip_amount"] for r in source))
            row["total_amount"] = round(
                sum(
                    row[n] or 0
                    for n in [
                        "fare_amount",
                        "extra",
                        "mta_tax",
                        "tip_amount",
                        "tolls_amount",
                        "improvement_surcharge",
                        "congestion_surcharge",
                        "ehail_fee",
                    ]
                ),
                2,
            )
        else:
            flags = [n for n in names if n.endswith("Flag")]

            def snow(r):
                return bool(r["Total Snow (cm)"] and float(r["Total Snow (cm)"]) > 0)

            pool = [
                r
                for r in source
                if r["Month"] == template["Month"]
                and all(r[n] == template[n] for n in flags)
                and snow(r) == snow(template)
            ]
            a, b = rng.choice(pool), rng.choice(pool)
            w = rng.uniform(0.2, 0.8)
            for n in [
                "Max Temp (°C)",
                "Min Temp (°C)",
                "Total Rain (mm)",
                "Total Snow (cm)",
                "Total Precip (mm)",
            ]:
                row[n] = f"{w * float(a[n]) + (1 - w) * float(b[n]):.1f}" if a[n] and b[n] else ""
            # A second compatible day supplies an observed joint wind/depth state.
            for n in ["Dir of Max Gust (10s deg)", "Spd of Max Gust (km/h)", "Snow on Grnd (cm)"]:
                row[n] = a[n]
            if row["Max Temp (°C)"] and row["Min Temp (°C)"]:
                mean = round((float(row["Max Temp (°C)"]) + float(row["Min Temp (°C)"])) / 2, 1)
                row["Mean Temp (°C)"] = f"{mean:.1f}"
                row["Heat Deg Days (°C)"] = f"{max(18 - mean, 0):.1f}"
                row["Cool Deg Days (°C)"] = f"{max(mean - 18, 0):.1f}"
            else:
                for n in ["Mean Temp (°C)", "Heat Deg Days (°C)", "Cool Deg Days (°C)"]:
                    row[n] = ""
        generated.append(row)
    clean = out / ("synthetic-clean" + path.suffix)
    if taxi:
        pq.write_table(pa.Table.from_pylist(generated, schema=pq.read_schema(path)), clean)
    else:
        with clean.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=names)
            writer.writeheader()
            writer.writerows(generated)
    skill(
        "plan_corruption.py",
        clean,
        out / "generation-spec.json",
        "--output",
        out / "corruption-plan.json",
    )
    plan = json.loads((out / "corruption-plan.json").read_text())
    for target in plan["targets"]:
        print(
            key,
            json.dumps(target),
            json.dumps(generated[target["record_index"]], default=str, ensure_ascii=False),
        )


if __name__ == "__main__":
    for i, key in enumerate(KEYS):
        generate(key, 4100 + i)
