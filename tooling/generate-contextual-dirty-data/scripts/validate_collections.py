#!/usr/bin/env python3
"""Validate v4 multi-collection generation, novelty, and dirty-data accounting."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any

from dataset_io import (
    Dataset,
    DatasetError,
    discover_record_paths,
    field_exists,
    field_name_structure,
    get_pointer,
    json_safe,
    leaf_paths,
    load_dataset,
    normalized_record_fingerprint,
    read_json,
    sha256_file,
    write_json,
)
from spec_collections import collection_protected_fields, normalize_collections
from validate_dataset import (
    HARD_MAX_RATE,
    Report,
    as_decimal,
    changed_paths,
    check_declared_fields,
    check_machine_rules,
    check_representation,
    check_source_model_contract,
    comparable_value,
    dataset_shape,
    identifier_values,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--dirty", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def values_equal(left: Any, right: Any) -> bool:
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    return json_safe(left) == json_safe(right)


def collection_content(dataset: Dataset) -> Any:
    if dataset.format_name == "excel":
        worksheet = dataset.root[dataset.record_path[6:]]
        return [
            [json_safe(cell.value) for cell in row]
            for row in worksheet.iter_rows(
                min_row=1,
                max_row=worksheet.max_row,
                max_col=worksheet.max_column,
            )
        ]
    if dataset.format_name in {"json", "yaml"}:
        return json_safe(get_pointer(dataset.root, dataset.record_path))
    return json_safe(dataset.records)


def novelty_metrics(
    source: Dataset,
    clean: Dataset,
    novelty: Any,
) -> tuple[bool, dict[str, Any], list[str]]:
    violations: list[str] = []
    if not isinstance(novelty, dict):
        return False, {}, ["novelty must be an object"]
    raw_exemptions = novelty.get("exemptions", [])
    if not isinstance(raw_exemptions, list):
        return False, {}, ["novelty.exemptions must be an array"]
    exempt_paths: set[str] = set()
    for item in raw_exemptions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not item["path"].startswith("/")
            or not isinstance(item.get("reason"), str)
            or not item["reason"].strip()
        ):
            violations.append("Every novelty exemption requires a path and nonempty reason")
            continue
        exempt_paths.add(item["path"])

    minimum_changed = novelty.get("minimum_changed_value_ratio")
    similarity_threshold = novelty.get("high_similarity_threshold")
    maximum_high_similarity = novelty.get("maximum_high_similarity_record_ratio")
    if (
        isinstance(minimum_changed, bool)
        or not isinstance(minimum_changed, (int, float))
        or not 0.5 <= float(minimum_changed) <= 1.0
    ):
        violations.append("minimum_changed_value_ratio must be between 0.5 and 1.0")
    if (
        isinstance(similarity_threshold, bool)
        or not isinstance(similarity_threshold, (int, float))
        or not 0.8 <= float(similarity_threshold) < 1.0
    ):
        violations.append("high_similarity_threshold must be between 0.8 and 1.0")
    if (
        isinstance(maximum_high_similarity, bool)
        or not isinstance(maximum_high_similarity, (int, float))
        or not 0.0 <= float(maximum_high_similarity) <= 0.5
    ):
        violations.append(
            "maximum_high_similarity_record_ratio must be between 0.0 and 0.5"
        )
    if violations:
        return False, {}, violations

    paths = [
        path
        for path in sorted(
            {
                path
                for record in source.records
                for path in leaf_paths(record)
            }
        )
        if path not in exempt_paths
    ]
    comparable_cells = 0
    changed_cells = 0
    high_similarity_records = 0
    evaluated_records = 0
    exact_aligned_records = 0
    per_field: dict[str, dict[str, int]] = {
        path: {"comparable": 0, "changed": 0} for path in paths
    }
    for source_record, clean_record in zip(source.records, clean.records):
        record_cells = 0
        equal_cells = 0
        for path in paths:
            try:
                source_value = get_pointer(source_record, path)
                clean_value = get_pointer(clean_record, path)
            except DatasetError:
                continue
            if source_value in (None, "") and clean_value in (None, ""):
                continue
            record_cells += 1
            comparable_cells += 1
            per_field[path]["comparable"] += 1
            if values_equal(source_value, clean_value):
                equal_cells += 1
            else:
                changed_cells += 1
                per_field[path]["changed"] += 1
        if record_cells:
            evaluated_records += 1
            similarity = equal_cells / record_cells
            if similarity >= float(similarity_threshold):
                high_similarity_records += 1
            if equal_cells == record_cells:
                exact_aligned_records += 1

    changed_ratio = changed_cells / comparable_cells if comparable_cells else 0.0
    high_similarity_ratio = (
        high_similarity_records / evaluated_records if evaluated_records else 1.0
    )
    observed = {
        "exempt_paths": sorted(exempt_paths),
        "comparable_value_count": comparable_cells,
        "changed_value_count": changed_cells,
        "changed_value_ratio": changed_ratio,
        "minimum_changed_value_ratio": float(minimum_changed),
        "evaluated_record_count": evaluated_records,
        "exact_aligned_record_count": exact_aligned_records,
        "high_similarity_threshold": float(similarity_threshold),
        "high_similarity_record_count": high_similarity_records,
        "high_similarity_record_ratio": high_similarity_ratio,
        "maximum_high_similarity_record_ratio": float(maximum_high_similarity),
        "per_field": {
            path: {
                **counts,
                "changed_ratio": (
                    counts["changed"] / counts["comparable"]
                    if counts["comparable"]
                    else 0.0
                ),
            }
            for path, counts in per_field.items()
            if counts["comparable"]
        },
    }
    passed = (
        comparable_cells > 0
        and changed_ratio >= float(minimum_changed)
        and high_similarity_ratio <= float(maximum_high_similarity)
    )
    if comparable_cells == 0:
        violations.append("No non-exempt comparable values remain")
    if changed_ratio < float(minimum_changed):
        violations.append("Observed changed-value ratio is below the declared minimum")
    if high_similarity_ratio > float(maximum_high_similarity):
        violations.append("Observed high-similarity record ratio exceeds the declared maximum")
    return passed, observed, violations


def main() -> int:
    args = parse_args()
    spec = read_json(args.spec)
    manifest = read_json(args.manifest)
    if not isinstance(spec, dict) or not isinstance(manifest, dict):
        raise DatasetError("Specification and manifest must be JSON objects")
    if spec.get("version") != 4:
        raise DatasetError("validate_collections.py requires generation specification version 4")

    source_spec = spec.get("source", {})
    generation = spec.get("generation", {})
    policy = spec.get("dirty_policy", {})
    quality = spec.get("quality", {})
    if not all(isinstance(item, dict) for item in (source_spec, generation, policy, quality)):
        raise DatasetError("Invalid generation specification sections")
    contracts = normalize_collections(spec)
    generated = [item for item in contracts if item["handling"] == "generate"]
    if not generated:
        raise DatasetError("At least one collection must use handling='generate'")

    report = Report()
    declared_paths = [item["record_path"] for item in contracts]
    discovered_source = discover_record_paths(args.source)
    discovered_clean = discover_record_paths(args.clean)
    discovered_dirty = discover_record_paths(args.dirty)
    report.check(
        "all_collections_declared",
        set(declared_paths) == set(discovered_source),
        {"declared": declared_paths, "discovered": discovered_source},
    )
    report.check(
        "collection_paths_preserved",
        discovered_source == discovered_clean == discovered_dirty,
        {
            "source": discovered_source,
            "clean": discovered_clean,
            "dirty": discovered_dirty,
        },
    )

    states: dict[str, dict[str, Any]] = {}
    generated_record_count = 0
    novelty_summary: dict[str, Any] = {}
    source_overlap: dict[str, int] = {}
    for contract in contracts:
        path = contract["record_path"]
        source = load_dataset(args.source, path)
        clean = load_dataset(args.clean, path)
        dirty = load_dataset(args.dirty, path)
        states[path] = {"contract": contract, "source": source, "clean": clean, "dirty": dirty}
        report.check(
            f"structure_preserved:{path}",
            dataset_shape(source) == dataset_shape(clean) == dataset_shape(dirty),
            {
                "source": dataset_shape(source),
                "clean": dataset_shape(clean),
                "dirty": dataset_shape(dirty),
            },
        )
        report.check(
            f"source_record_count:{path}",
            contract.get("record_count") == len(source.records),
            {"declared": contract.get("record_count"), "actual": len(source.records)},
        )
        if contract["handling"] != "generate":
            preserved = (
                collection_content(source)
                == collection_content(clean)
                == collection_content(dirty)
            )
            report.check(
                f"explicit_preservation:{path}",
                preserved,
                {
                    "handling": contract["handling"],
                    "reason": contract["reason"],
                    "content_identical": preserved,
                },
            )
            continue

        collection_generation = contract["generation"]
        generated_record_count += len(clean.records)
        report.check(
            f"generated_record_count:{path}",
            collection_generation.get("record_count")
            == len(clean.records)
            == len(dirty.records),
            {
                "declared": collection_generation.get("record_count"),
                "clean": len(clean.records),
                "dirty": len(dirty.records),
            },
        )
        check_declared_fields(report, clean, collection_generation.get("fields", []))
        check_machine_rules(report, clean, collection_generation.get("machine_rules", []))
        check_representation(
            report,
            source,
            clean,
            collection_generation.get("representation"),
            collection_generation.get("primary_identifiers", []),
            collection_generation.get("grouping_keys", []),
            require_direct_generation=True,
        )
        novelty_passed, novelty_evidence, novelty_violations = novelty_metrics(
            source,
            clean,
            collection_generation.get("novelty"),
        )
        novelty_summary[path] = novelty_evidence
        report.check(
            f"substantive_content_novelty:{path}",
            novelty_passed,
            {"metrics": novelty_evidence, "violations": novelty_violations},
        )
        source_fingerprints = {
            normalized_record_fingerprint(record) for record in source.records
        }
        source_overlap[path] = sum(
            normalized_record_fingerprint(record) in source_fingerprints
            for record in clean.records
        )

    report.check(
        "generated_record_count_total",
        generation.get("record_count") == generated_record_count,
        {"declared": generation.get("record_count"), "actual": generated_record_count},
    )
    check_source_model_contract(report, generation.get("source_model"), required=True)

    max_rate = as_decimal(policy.get("max_rate"), "dirty_policy.max_rate")
    selected_rate = as_decimal(policy.get("selected_rate"), "dirty_policy.selected_rate")
    report.check(
        "dirty_rate_policy",
        Decimal("0") <= selected_rate <= max_rate == HARD_MAX_RATE,
        {"selected_rate": float(selected_rate), "max_rate": float(max_rate)},
    )
    expected_dirty_count = int(
        (Decimal(generated_record_count) * selected_rate).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    actual_dirty_keys: set[tuple[str, int]] = set()
    for contract in generated:
        path = contract["record_path"]
        clean = states[path]["clean"]
        dirty = states[path]["dirty"]
        actual_dirty_keys.update(
            (path, index)
            for index, (clean_record, dirty_record) in enumerate(
                zip(clean.records, dirty.records)
            )
            if normalized_record_fingerprint(clean_record)
            != normalized_record_fingerprint(dirty_record)
        )
    manifest_records = manifest.get("records", [])
    if not isinstance(manifest_records, list):
        raise DatasetError("Manifest records must be an array")
    manifest_keys = {
        (item.get("record_path"), item.get("record_index"))
        for item in manifest_records
        if isinstance(item, dict)
    }
    report.check(
        "exact_dirty_record_count",
        len(actual_dirty_keys) == expected_dirty_count,
        {"expected": expected_dirty_count, "actual": len(actual_dirty_keys)},
    )
    report.check(
        "manifest_dirty_records",
        len(manifest_keys) == len(manifest_records) and manifest_keys == actual_dirty_keys,
        {
            "manifest": sorted(manifest_keys),
            "actual": sorted(actual_dirty_keys),
        },
    )

    raw_coverage = policy.get("collection_coverage", {"mode": "random_global"})
    coverage_mode = (
        raw_coverage.get("mode", "random_global")
        if isinstance(raw_coverage, dict)
        else None
    )
    eligible_paths: list[str] = []
    for contract in generated:
        path = contract["record_path"]
        protected = collection_protected_fields(states[path]["contract"])
        eligible = False
        for record in states[path]["clean"].records:
            for error_type in policy.get("error_types", []):
                if not isinstance(error_type, dict):
                    continue
                allowed = error_type.get("eligible_record_paths")
                if allowed is not None and path not in allowed:
                    continue
                for field_path in error_type.get("eligible_fields", []):
                    if (
                        isinstance(field_path, str)
                        and field_exists(record, field_path)
                        and not any(
                            field_path == protected_path
                            or field_path.startswith(f"{protected_path}/")
                            for protected_path in protected
                        )
                    ):
                        eligible = True
                        break
                if eligible:
                    break
            if eligible:
                break
        if eligible:
            eligible_paths.append(path)
    covered_paths = sorted({path for path, _ in actual_dirty_keys})
    coverage_valid = coverage_mode in {
        "random_global",
        "all_eligible_when_feasible",
    }
    if coverage_mode == "all_eligible_when_feasible":
        expected_covered_count = min(expected_dirty_count, len(eligible_paths))
        coverage_valid = coverage_valid and len(covered_paths) == expected_covered_count
        if expected_dirty_count >= len(eligible_paths):
            coverage_valid = coverage_valid and set(covered_paths) == set(eligible_paths)
    report.check(
        "dirty_collection_coverage",
        coverage_valid,
        {
            "mode": coverage_mode,
            "eligible_record_paths": eligible_paths,
            "covered_record_paths": covered_paths,
            "all_eligible_coverage_feasible": expected_dirty_count >= len(eligible_paths),
        },
    )

    allowed_error_types = {
        item.get("name")
        for item in policy.get("error_types", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    manifest_error_types = Counter(
        item.get("error_type") for item in manifest_records if isinstance(item, dict)
    )
    report.check(
        "contextual_error_types",
        set(manifest_error_types).issubset(allowed_error_types),
        {"allowed": sorted(allowed_error_types), "actual_counts": dict(manifest_error_types)},
    )
    manifest_failures: list[str] = []
    dirty_cell_count = 0
    for item in manifest_records:
        if not isinstance(item, dict):
            manifest_failures.append("A manifest record is not an object")
            continue
        path = item.get("record_path")
        index = item.get("record_index")
        if path not in states or states[path]["contract"]["handling"] != "generate":
            manifest_failures.append(f"Invalid manifest collection: {path!r}")
            continue
        clean = states[path]["clean"]
        dirty = states[path]["dirty"]
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(clean.records):
            manifest_failures.append(f"Invalid manifest record index: {index!r}")
            continue
        protected = collection_protected_fields(states[path]["contract"])
        expected_paths: set[str] = set()
        changes = item.get("changes", [])
        if not isinstance(changes, list):
            manifest_failures.append(f"Record {path}:{index} has invalid changes")
            continue
        for change in changes:
            dirty_cell_count += 1
            if not isinstance(change, dict) or not isinstance(change.get("path"), str):
                manifest_failures.append(f"Record {path}:{index} has an invalid change")
                continue
            field_path = change["path"]
            expected_paths.add(field_path)
            if any(
                field_path == protected_path
                or field_path.startswith(f"{protected_path}/")
                for protected_path in protected
            ):
                manifest_failures.append(
                    f"Record {path}:{index} changes protected field {field_path}"
                )
            try:
                clean_value = comparable_value(
                    get_pointer(clean.records[index], field_path), clean.format_name
                )
                dirty_value = comparable_value(
                    get_pointer(dirty.records[index], field_path), dirty.format_name
                )
            except DatasetError as exc:
                manifest_failures.append(f"Record {path}:{index} {field_path}: {exc}")
                continue
            if comparable_value(change.get("clean_value"), clean.format_name) != clean_value:
                manifest_failures.append(
                    f"Record {path}:{index} clean manifest value disagrees at {field_path}"
                )
            if comparable_value(change.get("dirty_value"), dirty.format_name) != dirty_value:
                manifest_failures.append(
                    f"Record {path}:{index} dirty manifest value disagrees at {field_path}"
                )
        actual_paths = changed_paths(clean.records[index], dirty.records[index])
        if expected_paths != actual_paths:
            manifest_failures.append(
                f"Record {path}:{index} manifest paths differ from actual paths"
            )
        if field_name_structure(clean.records[index]) != field_name_structure(dirty.records[index]):
            manifest_failures.append(f"Record {path}:{index} changes field names")
    report.check(
        "manifest_change_evidence",
        not manifest_failures,
        "Every changed value matches the manifest"
        if not manifest_failures
        else manifest_failures[:25],
    )
    manifest_rate = manifest.get("actual_dirty_record_rate")
    report.check(
        "manifest_hashes_and_counts",
        manifest.get("clean_sha256") == sha256_file(args.clean)
        and manifest.get("dirty_sha256") == sha256_file(args.dirty)
        and manifest.get("record_count") == generated_record_count
        and manifest.get("dirty_record_count") == len(actual_dirty_keys)
        and manifest.get("dirty_cell_count") == dirty_cell_count
        and isinstance(manifest_rate, (int, float))
        and not isinstance(manifest_rate, bool)
        and math.isclose(
            float(manifest_rate),
            len(actual_dirty_keys) / generated_record_count if generated_record_count else 0.0,
        ),
        {
            "clean_hash_matches": manifest.get("clean_sha256") == sha256_file(args.clean),
            "dirty_hash_matches": manifest.get("dirty_sha256") == sha256_file(args.dirty),
            "record_count": manifest.get("record_count"),
            "dirty_record_count": manifest.get("dirty_record_count"),
            "dirty_cell_count": manifest.get("dirty_cell_count"),
        },
    )

    row_policy = quality.get("source_row_overlap_policy", "allow")
    report.check(
        "source_row_overlap_policy",
        row_policy in {"allow", "reject"}
        and (row_policy == "allow" or all(count == 0 for count in source_overlap.values())),
        {"overlap_counts": source_overlap, "policy": row_policy},
    )
    identifier_policy = quality.get("source_identifier_overlap_policy", "allow")
    identifier_overlaps: dict[str, dict[str, int]] = {}
    identifiers_valid = identifier_policy in {"allow", "reject"}
    for contract in generated:
        path = contract["record_path"]
        identifier_paths = contract["generation"].get("primary_identifiers", [])
        if not isinstance(identifier_paths, list) or any(
            not isinstance(item, str) or not item.startswith("/")
            for item in identifier_paths
        ):
            identifiers_valid = False
            continue
        source_ids = identifier_values(states[path]["source"], identifier_paths)
        clean_ids = identifier_values(states[path]["clean"], identifier_paths)
        identifier_overlaps[path] = {
            item: len(source_ids[item].intersection(clean_ids[item]))
            for item in identifier_paths
        }
    report.check(
        "source_identifier_overlap_policy",
        identifiers_valid
        and (
            identifier_policy == "allow"
            or all(
                count == 0
                for collection in identifier_overlaps.values()
                for count in collection.values()
            )
        ),
        {"overlap_counts": identifier_overlaps, "policy": identifier_policy},
    )

    actual_rate = len(actual_dirty_keys) / generated_record_count if generated_record_count else 0.0
    output = {
        "version": 2,
        "passed": not report.errors,
        "summary": {
            "collection_count": len(contracts),
            "generated_collection_count": len(generated),
            "preserved_collection_count": len(contracts) - len(generated),
            "generated_record_count": generated_record_count,
            "dirty_record_count": len(actual_dirty_keys),
            "dirty_cell_count": dirty_cell_count,
            "selected_dirty_record_rate": float(selected_rate),
            "actual_dirty_record_rate": actual_rate,
            "max_dirty_record_rate": float(max_rate),
            "error_type_counts": dict(manifest_error_types),
            "dirty_collection_coverage": {
                "mode": coverage_mode,
                "eligible_record_paths": eligible_paths,
                "covered_record_paths": covered_paths,
            },
            "exact_source_row_overlap_counts": source_overlap,
            "novelty": novelty_summary,
        },
        "checks": report.checks,
        "errors": report.errors,
        "warnings": report.warnings,
    }
    write_json(args.output, output)
    print(f"Validation {'passed' if output['passed'] else 'failed'}; wrote {args.output}")
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
