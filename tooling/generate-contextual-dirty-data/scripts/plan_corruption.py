#!/usr/bin/env python3
"""Select exact corruption targets without generating replacement values."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any

from dataset_io import DatasetError, field_exists, load_dataset, read_json, sha256_file, write_json
from spec_collections import collection_protected_fields, generated_collections


HARD_MAX_RATE = Decimal("0.05")


def as_rate(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise DatasetError(f"{label} must be a number")
    try:
        rate = Decimal(str(value))
    except Exception as exc:
        raise DatasetError(f"{label} must be a number") from exc
    if not rate.is_finite():
        raise DatasetError(f"{label} must be finite")
    return rate


def weighted_choice(rng: random.Random, items: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(float(item["weight"]) for item in items)
    marker = rng.random() * total
    cumulative = 0.0
    for item in items:
        cumulative += float(item["weight"])
        if marker <= cumulative:
            return item
    return items[-1]


def compatible_error_types(
    record: dict[str, Any],
    record_path: str,
    protected: set[str],
    error_types: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    compatible = []
    for error_type in error_types:
        allowed_collections = error_type.get("eligible_record_paths")
        if allowed_collections is not None and record_path not in allowed_collections:
            continue
        fields = [
            path
            for path in error_type["eligible_fields"]
            if field_exists(record, path)
            and not any(
                path == protected_path or path.startswith(f"{protected_path}/")
                for protected_path in protected
            )
        ]
        if fields:
            compatible.append({**error_type, "eligible_fields": fields})
    return compatible


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean", type=Path, help="Agent-generated clean dataset")
    parser.add_argument("spec", type=Path, help="Agent-authored generation specification")
    parser.add_argument("--output", type=Path, required=True, help="Output corruption plan")
    parser.add_argument("--seed", type=int, help="Override generation.random_seed")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = read_json(args.spec)
    if not isinstance(spec, dict):
        raise DatasetError("The generation specification must be a JSON object")

    source_spec = spec.get("source", {})
    generation = spec.get("generation", {})
    policy = spec.get("dirty_policy", {})
    scenario = spec.get("scenario_inference", {})
    if not all(isinstance(section, dict) for section in (source_spec, generation, policy, scenario)):
        raise DatasetError(
            "source, scenario_inference, generation, and dirty_policy must be objects"
        )

    confidence = scenario.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise DatasetError("scenario_inference.confidence must be between 0 and 1")
    evidence = scenario.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise DatasetError("scenario_inference.evidence must contain at least one statement")
    rationale = policy.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise DatasetError("dirty_policy.rationale must explain the agent-selected rate")

    contracts = generated_collections(spec)
    if not contracts:
        raise DatasetError("At least one collection must use handling='generate'")
    collection_states = []
    record_count = 0
    for contract in contracts:
        dataset = load_dataset(args.clean, contract["record_path"])
        if source_spec.get("physical_format") != dataset.format_name:
            raise DatasetError(
                "The clean dataset format does not match source.physical_format in the specification"
            )
        declared_source_count = contract.get("record_count")
        declared_generation_count = (contract.get("generation") or {}).get("record_count")
        if declared_source_count != len(dataset.records):
            raise DatasetError(
                f"Collection {contract['record_path']!r} has {len(dataset.records)} records; "
                f"source declared {declared_source_count!r}"
            )
        if declared_generation_count != len(dataset.records):
            raise DatasetError(
                f"Collection {contract['record_path']!r} has {len(dataset.records)} records; "
                f"generation declared {declared_generation_count!r}"
            )
        protected = collection_protected_fields(contract)
        collection_states.append(
            {"contract": contract, "dataset": dataset, "protected": protected}
        )
        record_count += len(dataset.records)

    intended_count = generation.get("record_count")
    if not isinstance(intended_count, int) or isinstance(intended_count, bool) or intended_count < 0:
        raise DatasetError("generation.record_count must be a nonnegative integer")
    if record_count != intended_count:
        raise DatasetError(
            f"Generated collections have {record_count} records; generation.record_count is "
            f"{intended_count}"
        )

    max_rate = as_rate(policy.get("max_rate"), "dirty_policy.max_rate")
    selected_rate = as_rate(policy.get("selected_rate"), "dirty_policy.selected_rate")
    if max_rate != HARD_MAX_RATE:
        raise DatasetError("dirty_policy.max_rate must be the fixed hard cap 0.05")
    if selected_rate < 0 or selected_rate > max_rate:
        raise DatasetError("dirty_policy.selected_rate must be between 0 and max_rate")
    if policy.get("unit") != "record":
        raise DatasetError("dirty_policy.unit must be 'record'")

    target_count = int((Decimal(record_count) * selected_rate).to_integral_value(rounding=ROUND_FLOOR))
    raw_error_types = policy.get("error_types", [])
    if not isinstance(raw_error_types, list):
        raise DatasetError("dirty_policy.error_types must be an array")

    error_types: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in raw_error_types:
        if not isinstance(item, dict):
            raise DatasetError("Every error type must be an object")
        name = item.get("name")
        fields = item.get("eligible_fields")
        weight = item.get("weight")
        if not isinstance(name, str) or not name:
            raise DatasetError("Every error type requires a nonempty name")
        if name in names:
            raise DatasetError(f"Duplicate error type name: {name}")
        names.add(name)
        if not isinstance(fields, list) or not fields or any(
            not isinstance(path, str) or not path.startswith("/") for path in fields
        ):
            raise DatasetError(f"Error type {name!r} requires eligible field paths")
        eligible_record_paths = item.get("eligible_record_paths")
        if eligible_record_paths is not None and (
            not isinstance(eligible_record_paths, list)
            or not eligible_record_paths
            or any(not isinstance(path, str) for path in eligible_record_paths)
        ):
            raise DatasetError(
                f"Error type {name!r} eligible_record_paths must be a nonempty array of strings"
            )
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0:
            raise DatasetError(f"Error type {name!r} requires a positive finite weight")
        error_types.append(item)

    if target_count and not error_types:
        raise DatasetError("At least one error type is required when the target count is positive")

    raw_coverage = policy.get("collection_coverage", {"mode": "random_global"})
    if not isinstance(raw_coverage, dict):
        raise DatasetError("dirty_policy.collection_coverage must be an object")
    coverage_mode = raw_coverage.get("mode", "random_global")
    if coverage_mode not in {"random_global", "all_eligible_when_feasible"}:
        raise DatasetError(
            "dirty_policy.collection_coverage.mode must be 'random_global' or "
            "'all_eligible_when_feasible'"
        )

    seed = args.seed if args.seed is not None else generation.get("random_seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise DatasetError("generation.random_seed must be an integer")
    rng = random.Random(seed)
    positions = []
    eligible_by_path: dict[str, list[int]] = {}
    for state in collection_states:
        record_path = state["contract"]["record_path"]
        eligible_by_path[record_path] = []
        for record_index in range(len(state["dataset"].records)):
            global_index = len(positions)
            positions.append((state, record_index))
            record = state["dataset"].records[record_index]
            if compatible_error_types(
                record, record_path, state["protected"], error_types
            ):
                eligible_by_path[record_path].append(global_index)

    eligible_positions = [
        index for indices in eligible_by_path.values() for index in indices
    ]
    if target_count > len(eligible_positions):
        raise DatasetError(
            f"Requested {target_count} dirty records but only {len(eligible_positions)} "
            "records have an eligible unprotected field"
        )
    eligible_paths = [path for path, indices in eligible_by_path.items() if indices]
    if coverage_mode == "all_eligible_when_feasible" and target_count:
        collection_slots = min(target_count, len(eligible_paths))
        if collection_slots == len(eligible_paths):
            selected_paths = eligible_paths
        else:
            selected_paths = rng.sample(eligible_paths, collection_slots)
        reserved = [rng.choice(eligible_by_path[path]) for path in selected_paths]
        remaining_pool = [index for index in eligible_positions if index not in set(reserved)]
        indices = sorted(
            reserved + rng.sample(remaining_pool, target_count - len(reserved))
        )
    else:
        indices = sorted(rng.sample(eligible_positions, target_count))

    targets = []
    for sequence, global_record_index in enumerate(indices, start=1):
        state, record_index = positions[global_record_index]
        dataset = state["dataset"]
        record_path = state["contract"]["record_path"]
        protected = state["protected"]
        record = dataset.records[record_index]
        compatible = compatible_error_types(
            record, record_path, protected, error_types
        )
        if not compatible:
            raise DatasetError(
                f"No error type has an eligible unprotected field in collection "
                f"{record_path!r} record {record_index}"
            )
        error_type = weighted_choice(rng, compatible)
        fields = list(error_type["eligible_fields"])
        suggested_field = rng.choice(fields)
        targets.append(
            {
                "patch_id": f"dirty-{sequence:06d}",
                "record_path": record_path,
                "record_index": record_index,
                "global_record_index": global_record_index,
                "error_type": error_type["name"],
                "suggested_field": suggested_field,
                "eligible_fields": fields,
                "constraint_violated": error_type.get("constraint_violated", ""),
            }
        )

    plan = {
        "version": 2 if len(collection_states) > 1 else 1,
        "clean_sha256": sha256_file(args.clean),
        "spec_sha256": sha256_file(args.spec),
        "record_path": collection_states[0]["contract"]["record_path"],
        "record_count": record_count,
        "selected_rate": float(selected_rate),
        "max_rate": float(max_rate),
        "target_count": target_count,
        "random_seed": seed,
        "collection_coverage": {
            "mode": coverage_mode,
            "eligible_record_paths": eligible_paths,
            "covered_record_paths": sorted({item["record_path"] for item in targets}),
            "all_eligible_coverage_feasible": target_count >= len(eligible_paths),
        },
        "protected_fields": (
            sorted(collection_states[0]["protected"])
            if len(collection_states) == 1
            else []
        ),
        "collections": [
            {
                "record_path": state["contract"]["record_path"],
                "record_count": len(state["dataset"].records),
                "protected_fields": sorted(state["protected"]),
            }
            for state in collection_states
        ],
        "targets": targets,
    }
    write_json(args.output, plan)
    print(f"Selected {target_count} dirty records out of {record_count}; wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
