"""Execute the declared CORGIS source model and the provided data skill.

Acquisition is separate. This script consumes only the local 2015 source extract.
Run `prepare`, inspect planner targets, then replay the separately authored patches.
A semantic audit must be reviewed separately before release.
"""

import argparse
import copy
import json
import random
from generate_data import ROOT, skill, write_json

KEY = "airlines-2015"
SOURCE = ROOT / "data/raw/airlines-2015-source.json"
OUT = ROOT / "data/generated" / KEY
SEED = 4105


def leaves(value, prefix=""):
    for key, child in value.items():
        path = prefix + "/" + key.replace("~", "~0").replace("/", "~1")
        if isinstance(child, dict):
            yield from leaves(child, path)
        else:
            yield path, child


def pool_for(source, row):
    return [
        r
        for r in source
        if r["Airport"]["Code"] == row["Airport"]["Code"]
        and (r["Time"]["Month"] - 1) // 3 == (row["Time"]["Month"] - 1) // 3
    ]


def prepare():
    skill("inspect_dataset.py", SOURCE, "--output", OUT / "structure-report.json")
    source = json.loads(SOURCE.read_text())
    profile = json.loads((OUT / "structure-report.json").read_text())
    canonical = [p for p, _ in leaves(source[0]) if p.startswith(("/Airport/", "/Time/"))]
    # Carrier names are a closed roster; its count is derived and is NOT novelty-exempt.
    canonical.append("/Statistics/Carriers/Names")
    placement = canonical[:-1]
    joint_rule = "At each final calendar/airport slot, sample two distinct observed months from the same airport and quarter. Blend all flight, cause-count and cause-minute components with one shared weight in [0.25, 0.75], rounding to integers; derive both totals. Select the first donor's valid roster and recalculate its count. This produces new multivariate observations, not individual-source-row perturbations."
    dimensions = [
        dict(
            name="regime",
            scope="dataset",
            paths=[],
            constraint_kind="hard",
            generation_strategy="reuse_observed",
            evidence="Complete 2015 extract: 348 records = 29 airports × 12 months; one root-array collection, 24 scalar leaf fields, no nested arrays.",
            generation_rule="Preserve the 2015 airport-month panel and exact nested field schema.",
        ),
        dict(
            name="reference_support",
            scope="group",
            paths=canonical,
            constraint_kind="hard",
            generation_strategy="reuse_observed",
            evidence="Airport code/name and month/label/name dependencies hold across all 348 records. Carrier rosters contain actual names and counts agree with comma-delimited roster lengths.",
            generation_rule="Retain the canonical airport/calendar scaffold; use a roster observed at that airport in the same quarter. These are reference labels, not synthetic observations.",
        ),
        dict(
            name="joint_statistics",
            scope="relation",
            paths=["/Statistics"],
            constraint_kind="soft",
            generation_strategy=["recombine_conditionally", "derive"],
            evidence="Quarter/airport pools each have three rows. Flight totals equal their four components in every source row. Cause counts differ from delayed-flight counts by -5..4, consistent with upstream rounding. Minute totals have +4 residuals at indices 23 and 66; clean totals will repair these.",
            generation_rule=joint_rule,
        ),
        dict(
            name="physical_placement",
            scope="sequence",
            paths=placement,
            constraint_kind="hard",
            generation_strategy="generate_conditionally",
            evidence=profile["representation_summary"],
            generation_rule="Emit directly in ascending month then airport-code order. Each airport repeats at interleaved positions; month values are grouped, year constant. No post-generation shuffle.",
        ),
    ]
    fields = []
    for f in profile["fields"]:
        fields.append(
            dict(
                path=f["path"],
                meaning=f["path"].strip("/").replace("/", " · "),
                physical_type=list(f["physical_types"]),
                nullable=False,
                corruption_prohibited=f["path"] in canonical,
                generation_guidance="Canonical reference scaffold or same-airport/quarter roster"
                if f["path"] in canonical
                else joint_rule,
                **({"minimum": 0} if "integer" in f["physical_types"] else {}),
            )
        )
    spec = dict(
        version=4,
        source=dict(
            physical_format="json",
            collections=[
                dict(
                    record_path="",
                    record_count=348,
                    role="airport-month statistics",
                    handling="generate",
                )
            ],
        ),
        scenario_inference=dict(
            domain="airline operations",
            dataset_role="synthetic monthly airport statistics extract",
            record_meaning="one airport-month",
            producer="curated transportation statistics export",
            curation_level="high",
            confidence=0.95,
            evidence=[
                "CORGIS local JSON snapshot",
                "structure-report.json",
                "complete 2015 panel and component arithmetic inspected",
            ],
            assumptions=[
                "Same-airport/quarter convex mixtures retain broad seasonal scale, not exact within-quarter weather events; this is a download fixture, not a scientific simulator.",
                "Months are 1-based in the data despite the upstream page's incorrect zero-based description.",
                "Cause counts tolerate rounding differences up to 7 after blending; they are not forced to exactly equal delayed flights.",
                "Repair the two source minute-total residuals by deriving all clean totals.",
            ],
        ),
        generation=dict(
            record_count=348,
            random_seed=SEED,
            source_model=dict(default_source_reuse="allow", dimensions=dimensions),
            collections=[
                dict(
                    record_path="",
                    record_count=348,
                    primary_identifiers=[],
                    grouping_keys=["/Airport/Code", "/Time/Label"],
                    protected_fields=canonical,
                    fields=fields,
                    representation=dict(
                        generation_mode="direct",
                        record_order=dict(
                            policy="match_source",
                            generation_guidance=dimensions[3]["generation_rule"],
                        ),
                        field_profiles=[
                            dict(
                                path=p,
                                value_role="reference_or_sequence",
                                cardinality="match_source",
                                sequence_policy="match_source",
                                record_layout="match_source",
                                linked_paths=[],
                                direct_generation_guidance=dimensions[3]["generation_rule"],
                            )
                            for p in placement
                        ],
                    ),
                    novelty=dict(
                        minimum_changed_value_ratio=0.5,
                        high_similarity_threshold=0.8,
                        maximum_high_similarity_record_ratio=0.5,
                        exemptions=[
                            dict(
                                path=p,
                                reason="Closed airport identity, calendar coordinate, or named carrier vocabulary; not a measured outcome.",
                            )
                            for p in canonical
                        ],
                    ),
                    hard_constraints=[
                        "Exact nested schema, integer nonnegative measurements, 348 unique airport-month pairs",
                        "Flight total equals cancelled + delayed + diverted + on time",
                        "Minute total equals its five cause components; carrier count equals roster length",
                        "All non-derived measurements lie within observed same-airport/quarter support",
                        "Absolute difference between sum of cause counts and delayed flights <= 7",
                    ],
                    soft_constraints=[
                        "Maintain airport scale, broad quarterly seasonal regime and multivariate dependencies through joint convex sampling"
                    ],
                    machine_rules=[
                        dict(
                            name="total_covers_delayed",
                            kind="comparison",
                            left="/Statistics/Flights/Total",
                            operator=">=",
                            right="/Statistics/Flights/Delayed",
                            coerce="number",
                            allow_null=False,
                        )
                    ],
                )
            ],
        ),
        dirty_policy=dict(
            unit="record",
            max_rate=0.05,
            selected_rate=0.01,
            rationale="A curated monthly statistical export can retain rare aggregation mistakes. One percent gives three manually authored omitted-component totals without damaging the JSON container.",
            collection_coverage=dict(mode="all_eligible_when_feasible"),
            error_types=[
                dict(
                    name="flight_total_component_omission",
                    weight=1,
                    eligible_record_paths=[""],
                    eligible_fields=["/Statistics/Flights/Total"],
                    constraint_violated="Flight total must equal all four outcome components",
                )
            ],
        ),
        quality=dict(
            source_row_overlap_policy="allow",
            source_identifier_overlap_policy="allow",
            require_exact_record_count=True,
        ),
    )
    write_json(OUT / "generation-spec.json", spec)
    rng = random.Random(SEED)
    generated = []
    for template in source:
        a, b = rng.sample(pool_for(source, template), 2)
        weight = rng.uniform(0.25, 0.75)
        row = copy.deepcopy(template)
        stats = row["Statistics"]
        for group in ("# of Delays", "Flights", "Minutes Delayed"):
            for name in stats[group]:
                if name != "Total":
                    stats[group][name] = round(
                        weight * a["Statistics"][group][name]
                        + (1 - weight) * b["Statistics"][group][name]
                    )
            if "Total" in stats[group]:
                stats[group]["Total"] = sum(v for k, v in stats[group].items() if k != "Total")
        stats["Carriers"]["Names"] = a["Statistics"]["Carriers"]["Names"]
        stats["Carriers"]["Total"] = len(stats["Carriers"]["Names"].split(","))
        generated.append(row)
    write_json(OUT / "synthetic-clean.json", generated)
    skill(
        "plan_corruption.py",
        OUT / "synthetic-clean.json",
        OUT / "generation-spec.json",
        "--output",
        OUT / "corruption-plan.json",
    )
    for target in json.loads((OUT / "corruption-plan.json").read_text())["targets"]:
        print(json.dumps(dict(target=target, record=generated[target["record_index"]])))


def apply_and_measure():
    clean_path = OUT / "synthetic-clean.json"
    clean = json.loads(clean_path.read_text())
    plan = json.loads((OUT / "corruption-plan.json").read_text())
    # Authored after reading all three planner-selected records, not random edits.
    authored = [
        (59, 9498, 9082, "Total omits the 416 cancelled flights in BOS March."),
        (71, 12125, 12109, "Total omits the 16 diverted flights in LAS March."),
        (268, 9706, 9604, "Total omits the 102 cancelled flights in DTW October."),
    ]
    patches = []
    for target, (index, before, after, reason) in zip(plan["targets"], authored, strict=True):
        assert target["record_index"] == index
        assert clean[index]["Statistics"]["Flights"]["Total"] == before
        patches.append(
            {k: target[k] for k in ("patch_id", "record_path", "record_index", "error_type")}
            | dict(changes=[dict(path=target["suggested_field"], value=after)], explanation=reason)
        )
    write_json(OUT / "dirty-patches.json", dict(version=1, patches=patches))
    skill(
        "apply_patches.py",
        clean_path,
        OUT / "dirty-patches.json",
        "--plan",
        OUT / "corruption-plan.json",
        "--output",
        OUT / "synthetic-dirty.json",
        "--manifest",
        OUT / "dirty-manifest.json",
    )
    skill(
        "validate_collections.py",
        "--source",
        SOURCE,
        "--clean",
        clean_path,
        "--dirty",
        OUT / "synthetic-dirty.json",
        "--spec",
        OUT / "generation-spec.json",
        "--manifest",
        OUT / "dirty-manifest.json",
        "--output",
        OUT / "validation-report.json",
    )
    source = json.loads(SOURCE.read_text())
    dirty = json.loads((OUT / "synthetic-dirty.json").read_text())
    failures, support_failures, residuals = [], [], []
    for index, row in enumerate(clean):
        stats = row["Statistics"]
        pool = pool_for(source, row)
        residual = sum(stats["# of Delays"].values()) - stats["Flights"]["Delayed"]
        residuals.append(residual)
        valid = row["Airport"] == source[index]["Airport"] and row["Time"] == source[index]["Time"]
        valid &= abs(residual) <= 7
        valid &= stats["Carriers"]["Total"] == len(stats["Carriers"]["Names"].split(","))
        valid &= stats["Carriers"]["Names"] in {r["Statistics"]["Carriers"]["Names"] for r in pool}
        for group in ("# of Delays", "Flights", "Minutes Delayed"):
            valid &= all(type(v) is int and v >= 0 for v in stats[group].values())
            if "Total" in stats[group]:
                valid &= stats[group]["Total"] == sum(
                    v for k, v in stats[group].items() if k != "Total"
                )
            for name, value in stats[group].items():
                if name != "Total":
                    observed = [r["Statistics"][group][name] for r in pool]
                    if not min(observed) <= value <= max(observed):
                        support_failures.append([index, group, name])
        if not valid:
            failures.append(index)
    targets = {p["record_index"] for p in patches}
    report = json.loads((OUT / "validation-report.json").read_text())
    evidence = dict(
        clean_constraint_failures=failures,
        conditional_support_failures=support_failures,
        cause_residual_range=[min(residuals), max(residuals)],
        unique_airport_months=len({(r["Airport"]["Code"], r["Time"]["Label"]) for r in clean}),
        flight_totals={
            name: sum(r["Statistics"]["Flights"]["Total"] for r in rows)
            for name, rows in (("source", source), ("clean", clean))
        },
        novelty=report["summary"]["novelty"][""],
        source_overlap=report["summary"]["exact_source_row_overlap_counts"][""],
        untargeted_unchanged=all(
            a == b for i, (a, b) in enumerate(zip(clean, dirty, strict=True)) if i not in targets
        ),
        patch_checks=[
            dict(
                patch_id=p["patch_id"],
                record_index=p["record_index"],
                evidence=p["explanation"],
                passed=dirty[p["record_index"]]["Statistics"]["Flights"]["Total"]
                != clean[p["record_index"]]["Statistics"]["Flights"]["Total"],
            )
            for p in patches
        ],
    )
    write_json(OUT / "semantic-evidence.json", evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "apply"])
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else apply_and_measure()
