#!/usr/bin/env python3
"""Validate format, structure, declared source conditioning, and dirty-data accounting."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any

from dataset_io import (
    Dataset,
    DatasetError,
    field_name_structure,
    get_pointer,
    json_safe,
    leaf_paths,
    load_dataset,
    normalized_record_fingerprint,
    read_json,
    sha256_file,
    structural_paths,
    write_json,
)
from inspect_dataset import physical_order_profile


HARD_MAX_RATE = Decimal("0.05")
SOURCE_MODEL_SCOPES = {"dataset", "field", "relation", "group", "sequence", "representation"}
SOURCE_MODEL_STRATEGIES = {
    "reuse_observed",
    "sample_empirical",
    "recombine_conditionally",
    "bounded_extension",
    "generate_conditionally",
    "derive",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--dirty", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def check(self, name: str, passed: bool, evidence: Any, severity: str = "error") -> None:
        status = "passed" if passed else ("warning" if severity == "warning" else "failed")
        self.checks.append({"name": name, "status": status, "evidence": json_safe(evidence)})
        if not passed:
            message = f"{name}: {evidence}"
            if severity == "warning":
                self.warnings.append(message)
            else:
                self.errors.append(message)


def as_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise DatasetError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise DatasetError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise DatasetError(f"{label} must be finite")
    return result


def schema_paths(dataset: Dataset) -> list[str]:
    if dataset.format_name in {"csv", "tsv", "excel", "parquet"}:
        columns = dataset.metadata.get("columns", [])
        return ["/" + str(column).replace("~", "~0").replace("/", "~1") for column in columns]
    return sorted({path for record in dataset.records for path in structural_paths(record)})


def dataset_shape(dataset: Dataset) -> dict[str, Any]:
    result = {
        "format": dataset.format_name,
        "record_path": dataset.record_path,
        "schema_paths": schema_paths(dataset),
    }
    if dataset.format_name in {"csv", "tsv"}:
        result["delimiter"] = dataset.metadata.get("delimiter")
    if dataset.format_name == "excel":
        result["sheet_names"] = dataset.metadata.get("sheet_names")
    return result


def scalar_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def changed_paths(clean: Any, dirty: Any, base: str = "") -> set[str]:
    if isinstance(clean, dict) and isinstance(dirty, dict):
        changes: set[str] = set()
        keys = set(clean) | set(dirty)
        for key in keys:
            token = str(key).replace("~", "~0").replace("/", "~1")
            path = f"{base}/{token}"
            if key not in clean or key not in dirty:
                changes.add(path)
            else:
                changes.update(changed_paths(clean[key], dirty[key], path))
        return changes
    if clean != dirty:
        return {base}
    return set()


def comparable_value(value: Any, format_name: str) -> Any:
    if format_name in {"csv", "tsv"}:
        return "" if value is None else str(value)
    return json_safe(value)


def identifier_values(dataset: Dataset, paths: list[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {path: set() for path in paths}
    for record in dataset.records:
        for path in paths:
            try:
                value = get_pointer(record, path)
            except DatasetError:
                continue
            if value in (None, ""):
                continue
            result[path].add(
                json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
    return result


def check_declared_fields(report: Report, clean: Dataset, fields: Any) -> None:
    if not isinstance(fields, list):
        report.check("declared_field_types", False, "generation.fields must be an array")
        return
    violations: list[str] = []
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get("path"), str):
            violations.append("Invalid field declaration")
            continue
        path = field["path"]
        expected = field.get("physical_type")
        allowed = {expected} if isinstance(expected, str) else set(expected or [])
        nullable = field.get("nullable") is True
        values: list[Any] = []
        for index, record in enumerate(clean.records):
            try:
                value = get_pointer(record, path)
            except DatasetError:
                violations.append(f"record {index} is missing {path}")
                continue
            values.append(value)
            observed = scalar_type(value)
            is_null = value in (None, "")
            if is_null and nullable:
                continue
            if is_null and not nullable:
                violations.append(f"record {index} field {path} is null or empty")
                continue
            if allowed and observed not in allowed:
                violations.append(
                    f"record {index} field {path} has type {observed}; expected {sorted(allowed)}"
                )
            allowed_values = field.get("allowed_values")
            if isinstance(allowed_values, list) and value not in allowed_values:
                violations.append(f"record {index} field {path} is outside allowed_values")
            pattern = field.get("pattern")
            if isinstance(pattern, str) and re.fullmatch(pattern, str(value)) is None:
                violations.append(f"record {index} field {path} does not match its pattern")
            if "minimum" in field or "maximum" in field:
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    violations.append(f"record {index} field {path} is not numeric for range validation")
                else:
                    if "minimum" in field and numeric_value < float(field["minimum"]):
                        violations.append(f"record {index} field {path} is below its minimum")
                    if "maximum" in field and numeric_value > float(field["maximum"]):
                        violations.append(f"record {index} field {path} is above its maximum")
            if len(violations) >= 25:
                break
        if field.get("unique") is True:
            comparable = [
                json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True)
                for value in values
                if value not in (None, "")
            ]
            if len(comparable) != len(set(comparable)):
                violations.append(f"field {path} contains duplicate non-null values")
        if len(violations) >= 25:
            break
    report.check(
        "declared_clean_field_constraints",
        not violations,
        "All machine-checkable clean field constraints match" if not violations else violations,
    )


def check_machine_rules(report: Report, clean: Dataset, rules: Any) -> None:
    if rules is None:
        rules = []
    if not isinstance(rules, list):
        report.check("declared_clean_machine_rules", False, "generation.machine_rules must be an array")
        return
    violations: list[str] = []
    operators = {
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
    }
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("kind") != "comparison":
            violations.append("Only object rules with kind 'comparison' are supported")
            continue
        name = rule.get("name", "unnamed comparison")
        left_path = rule.get("left")
        right_path = rule.get("right")
        operator = rule.get("operator")
        coercion = rule.get("coerce", "string")
        if not isinstance(left_path, str) or not isinstance(right_path, str) or operator not in operators:
            violations.append(f"Rule {name!r} has invalid paths or operator")
            continue
        for index, record in enumerate(clean.records):
            try:
                left = get_pointer(record, left_path)
                right = get_pointer(record, right_path)
                if left in (None, "") or right in (None, ""):
                    if rule.get("allow_null") is True:
                        continue
                    raise ValueError("null operand")
                if coercion == "number":
                    left, right = float(left), float(right)
                elif coercion != "string":
                    raise ValueError(f"unsupported coercion {coercion!r}")
                else:
                    left, right = str(left), str(right)
                passed = operators[operator](left, right)
            except (DatasetError, TypeError, ValueError) as exc:
                violations.append(f"record {index} rule {name!r} could not be evaluated: {exc}")
                continue
            if not passed:
                violations.append(f"record {index} violates rule {name!r}")
            if len(violations) >= 25:
                break
        if len(violations) >= 25:
            break
    report.check(
        "declared_clean_machine_rules",
        not violations,
        "All declared clean machine rules pass" if not violations else violations,
    )


def check_source_model_contract(report: Report, source_model: Any, required: bool = True) -> None:
    violations: list[str] = []
    if not isinstance(source_model, dict):
        report.check(
            "declared_source_model",
            False,
            "generation.source_model must be an object",
            severity="error" if required else "warning",
        )
        return
    reuse = source_model.get("default_source_reuse", "allow")
    if reuse not in {"allow", "restrict"}:
        violations.append("default_source_reuse must be 'allow' or 'restrict'")
    dimensions = source_model.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        violations.append("dimensions must be a non-empty array")
        dimensions = []
    names: set[str] = set()
    for index, dimension in enumerate(dimensions):
        label = f"dimension {index}"
        if not isinstance(dimension, dict):
            violations.append(f"{label} must be an object")
            continue
        name = dimension.get("name")
        if not isinstance(name, str) or not name.strip():
            violations.append(f"{label} requires a non-empty name")
        elif name in names:
            violations.append(f"duplicate dimension name {name!r}")
        else:
            names.add(name)
        if dimension.get("scope") not in SOURCE_MODEL_SCOPES:
            violations.append(f"{label} has unsupported scope {dimension.get('scope')!r}")
        paths = dimension.get("paths", [])
        if not isinstance(paths, list) or any(
            not isinstance(path, str) or (path and not path.startswith("/")) for path in paths
        ):
            violations.append(f"{label} paths must be JSON Pointer strings")
        evidence = dimension.get("evidence")
        if evidence in (None, "", [], {}):
            violations.append(f"{label} requires source evidence")
        if dimension.get("constraint_kind") not in {"hard", "soft"}:
            violations.append(f"{label} constraint_kind must be 'hard' or 'soft'")
        strategies = dimension.get("generation_strategy")
        if isinstance(strategies, str):
            strategies = [strategies]
        if not isinstance(strategies, list) or not strategies or any(
            strategy not in SOURCE_MODEL_STRATEGIES for strategy in strategies
        ):
            violations.append(f"{label} has an invalid generation_strategy")
        rule = dimension.get("generation_rule")
        if not isinstance(rule, str) or not rule.strip():
            violations.append(f"{label} requires a non-empty generation_rule")
    report.check(
        "declared_source_model",
        not violations,
        {
            "dimension_count": len(dimensions),
            "default_source_reuse": reuse,
            "violations": violations[:25],
        },
    )


def values_at_path(dataset: Dataset, path: str) -> list[Any]:
    values: list[Any] = []
    for record in dataset.records:
        try:
            values.append(get_pointer(record, path))
        except DatasetError:
            continue
    return values


def check_representation(
    report: Report,
    source: Dataset,
    clean: Dataset,
    representation: Any,
    primary_identifiers: Any,
    grouping_keys: Any,
    require_direct_generation: bool = False,
) -> None:
    required_paths = set()
    for collection in (primary_identifiers, grouping_keys):
        if isinstance(collection, list):
            required_paths.update(
                path for path in collection if isinstance(path, str) and path.startswith("/")
            )
    if representation is None:
        report.check(
            "representation_profile_declared",
            not required_paths and not require_direct_generation,
            (
                "No primary identifiers require a representation profile"
                if not required_paths and not require_direct_generation
                else {
                    "missing_field_profiles": sorted(required_paths),
                    "reason": (
                        "Version 3 requires direct representation generation instructions"
                        if require_direct_generation
                        else "Cardinality alone does not preserve sequence or grouping behavior"
                    ),
                }
            ),
        )
        return
    if not isinstance(representation, dict):
        report.check(
            "representation_profile_declared",
            False,
            "generation.representation must be an object",
        )
        return
    profiles = representation.get("field_profiles", [])
    if not isinstance(profiles, list):
        report.check(
            "representation_profile_declared",
            False,
            "generation.representation.field_profiles must be an array",
        )
        return

    if require_direct_generation:
        direct_violations: list[str] = []
        if representation.get("generation_mode") != "direct":
            direct_violations.append("generation_mode must be 'direct'")
        record_order = representation.get("record_order")
        if not isinstance(record_order, dict):
            direct_violations.append("record_order must be an object")
        else:
            if record_order.get("policy") not in {"match_source", "explicit"}:
                direct_violations.append("record_order.policy must be 'match_source' or 'explicit'")
            order_guidance = record_order.get("generation_guidance")
            if not isinstance(order_guidance, str) or not order_guidance.strip():
                direct_violations.append("record_order requires nonempty generation_guidance")
        for index, profile in enumerate(profiles):
            if not isinstance(profile, dict):
                continue
            guidance = profile.get("direct_generation_guidance")
            if not isinstance(guidance, str) or not guidance.strip():
                direct_violations.append(
                    f"field profile {index} requires nonempty direct_generation_guidance"
                )
        report.check(
            "direct_representation_generation_declared",
            not direct_violations,
            {
                "generation_mode": representation.get("generation_mode"),
                "record_order": representation.get("record_order"),
                "violations": direct_violations[:25],
            },
        )

    declared_paths = {
        profile.get("path")
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get("path"), str)
    }
    report.check(
        "representation_profile_declared",
        required_paths.issubset(declared_paths),
        {
            "required_profile_paths": sorted(required_paths),
            "profiled_paths": sorted(path for path in declared_paths if isinstance(path, str)),
            "missing": sorted(required_paths - declared_paths),
        },
    )

    violations: list[str] = []
    evidence: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict) or not isinstance(profile.get("path"), str):
            violations.append("A field profile is missing a string path")
            continue
        path = profile["path"]
        source_values = values_at_path(source, path)
        clean_values = values_at_path(clean, path)
        observed = physical_order_profile(clean_values)
        source_observed = physical_order_profile(source_values)
        item_evidence = {"path": path, "source": source_observed, "clean": observed}

        cardinality = profile.get("cardinality", "match_source")
        if cardinality == "unique" and observed.get("duplicate_occurrence_count") != 0:
            violations.append(f"{path} must be unique")
        elif cardinality == "repeated" and observed.get("duplicate_occurrence_count", 0) == 0:
            violations.append(f"{path} must preserve repeated relational values")
        elif (
            cardinality == "match_source"
            and observed.get("cardinality_class") != source_observed.get("cardinality_class")
        ):
            violations.append(
                f"{path} cardinality class {observed.get('cardinality_class')!r} does not "
                f"match source class {source_observed.get('cardinality_class')!r}"
            )
        elif cardinality not in ("match_source", "unique", "repeated"):
            violations.append(f"{path} has unsupported cardinality {cardinality!r}")

        sequence_policy = profile.get("sequence_policy", "match_source")
        source_sequence = source_observed.get("sequence_class", "not_applicable")
        clean_sequence = observed.get("sequence_class", "not_applicable")
        expected_sequence = {
            "non_sequential": "non_monotonic",
            "sequential_ascending": "sequential_ascending",
            "sequential_descending": "sequential_descending",
            "monotonic_ascending": "monotonic_ascending",
            "monotonic_descending": "monotonic_descending",
            "constant": "constant",
        }
        if sequence_policy == "match_source":
            if source_sequence != "not_applicable" and clean_sequence != source_sequence:
                violations.append(
                    f"{path} sequence class {clean_sequence!r} does not match source class "
                    f"{source_sequence!r}"
                )
        elif sequence_policy in expected_sequence:
            if clean_sequence != expected_sequence[sequence_policy]:
                violations.append(
                    f"{path} sequence class {clean_sequence!r} does not satisfy "
                    f"{sequence_policy!r}"
                )
        elif sequence_policy != "preserve":
            violations.append(f"{path} has unsupported sequence_policy {sequence_policy!r}")

        record_layout = profile.get("record_layout", "match_source")
        source_layout = source_observed.get("layout_class", "not_applicable")
        clean_layout = observed.get("layout_class", "not_applicable")
        if record_layout == "match_source":
            if source_layout not in ("not_applicable", "unique") and clean_layout != source_layout:
                violations.append(
                    f"{path} layout class {clean_layout!r} does not match source class "
                    f"{source_layout!r}"
                )
        elif record_layout in ("interleaved", "grouped", "mixed"):
            if clean_layout != record_layout:
                violations.append(
                    f"{path} layout class {clean_layout!r} does not satisfy {record_layout!r}"
                )
        elif record_layout != "preserve":
            violations.append(f"{path} has unsupported record_layout {record_layout!r}")

        maximum = profile.get("max_adjacent_equal_ratio")
        if maximum is not None:
            if (
                isinstance(maximum, bool)
                or not isinstance(maximum, (int, float))
                or not 0 <= float(maximum) <= 1
            ):
                violations.append(f"{path} has invalid max_adjacent_equal_ratio")
            elif observed.get("adjacent_equal_ratio", 0.0) > float(maximum):
                violations.append(
                    f"{path} adjacent equal ratio "
                    f"{observed.get('adjacent_equal_ratio', 0.0):.4f} exceeds {float(maximum):.4f}"
                )
        evidence.append(item_evidence)

    report.check(
        "declared_representation_constraints",
        not violations,
        evidence if not violations else {"violations": violations[:25], "profiles": evidence},
    )


def main() -> int:
    args = parse_args()
    spec = read_json(args.spec)
    manifest = read_json(args.manifest)
    if not isinstance(spec, dict) or not isinstance(manifest, dict):
        raise DatasetError("Specification and manifest must be JSON objects")
    source_spec = spec.get("source", {})
    generation = spec.get("generation", {})
    policy = spec.get("dirty_policy", {})
    quality = spec.get("quality", {})
    if not all(isinstance(item, dict) for item in (source_spec, generation, policy, quality)):
        raise DatasetError("Invalid generation specification sections")

    record_path = source_spec.get("record_path", "")
    if not isinstance(record_path, str):
        raise DatasetError("source.record_path must be a string")
    source = load_dataset(args.source, record_path)
    clean = load_dataset(args.clean, record_path)
    dirty = load_dataset(args.dirty, record_path)
    report = Report()

    report.check(
        "physical_format_preserved",
        source.format_name == clean.format_name == dirty.format_name,
        {"source": source.format_name, "clean": clean.format_name, "dirty": dirty.format_name},
    )
    declared_format = source_spec.get("physical_format")
    report.check(
        "declared_physical_format",
        declared_format == source.format_name,
        {"declared": declared_format, "observed": source.format_name},
    )

    source_shape = dataset_shape(source)
    clean_shape = dataset_shape(clean)
    dirty_shape = dataset_shape(dirty)
    report.check(
        "source_clean_structure_preserved",
        source_shape == clean_shape,
        {"source": source_shape, "clean": clean_shape},
    )
    report.check(
        "clean_dirty_structure_preserved",
        clean_shape == dirty_shape,
        {"clean": clean_shape, "dirty": dirty_shape},
    )
    source_fields = schema_paths(source)
    clean_fields = schema_paths(clean)
    dirty_fields = schema_paths(dirty)
    report.check(
        "source_clean_field_names_preserved",
        source_fields == clean_fields,
        {"source": source_fields, "clean": clean_fields},
    )
    record_structure_mismatches = [
        index
        for index, (clean_record, dirty_record) in enumerate(zip(clean.records, dirty.records))
        if field_name_structure(clean_record) != field_name_structure(dirty_record)
    ]
    report.check(
        "clean_dirty_field_names_preserved",
        clean_fields == dirty_fields
        and len(clean.records) == len(dirty.records)
        and not record_structure_mismatches,
        {
            "clean": clean_fields,
            "dirty": dirty_fields,
            "record_structure_mismatch_indices": record_structure_mismatches[:25],
        },
    )

    declared_source_count = source_spec.get("record_count")
    intended_count = generation.get("record_count")
    report.check(
        "source_record_count_matches_spec",
        isinstance(declared_source_count, int) and declared_source_count == len(source.records),
        {"declared": declared_source_count, "actual": len(source.records)},
    )
    report.check(
        "generated_record_count",
        isinstance(intended_count, int)
        and len(clean.records) == intended_count
        and len(dirty.records) == intended_count,
        {"intended": intended_count, "clean": len(clean.records), "dirty": len(dirty.records)},
    )
    spec_version = spec.get("version", 1)
    source_model_required = (
        isinstance(spec_version, int) and not isinstance(spec_version, bool) and spec_version >= 2
    )
    check_source_model_contract(
        report,
        generation.get("source_model"),
        required=source_model_required,
    )
    check_declared_fields(report, clean, generation.get("fields", []))
    check_machine_rules(report, clean, generation.get("machine_rules", []))
    check_representation(
        report,
        source,
        clean,
        generation.get("representation"),
        generation.get("primary_identifiers", []),
        generation.get("grouping_keys", []),
        require_direct_generation=(
            isinstance(spec_version, int)
            and not isinstance(spec_version, bool)
            and spec_version >= 3
        ),
    )

    max_rate = as_decimal(policy.get("max_rate"), "dirty_policy.max_rate")
    selected_rate = as_decimal(policy.get("selected_rate"), "dirty_policy.selected_rate")
    report.check(
        "dirty_rate_policy",
        Decimal("0") <= selected_rate <= max_rate == HARD_MAX_RATE,
        {"selected_rate": float(selected_rate), "max_rate": float(max_rate), "hard_max": 0.05},
    )
    expected_dirty_count = int(
        (Decimal(len(clean.records)) * selected_rate).to_integral_value(rounding=ROUND_FLOOR)
    )

    actual_dirty_indices = {
        index
        for index, (clean_record, dirty_record) in enumerate(zip(clean.records, dirty.records))
        if normalized_record_fingerprint(clean_record) != normalized_record_fingerprint(dirty_record)
    }
    manifest_records = manifest.get("records", [])
    if not isinstance(manifest_records, list):
        raise DatasetError("Manifest records must be an array")
    manifest_indices = {
        item.get("record_index") for item in manifest_records if isinstance(item, dict)
    }
    manifest_indices_valid = all(
        isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(clean.records)
        for index in manifest_indices
    ) and len(manifest_indices) == len(manifest_records)
    report.check(
        "exact_dirty_record_count",
        len(actual_dirty_indices) == expected_dirty_count,
        {"expected": expected_dirty_count, "actual": len(actual_dirty_indices)},
    )
    report.check(
        "manifest_dirty_records",
        manifest_indices_valid and manifest_indices == actual_dirty_indices,
        {"manifest_indices": sorted(index for index in manifest_indices if isinstance(index, int)), "actual_indices": sorted(actual_dirty_indices)},
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

    protected = set(generation.get("protected_fields", []))
    for field in generation.get("fields", []):
        if isinstance(field, dict) and field.get("corruption_prohibited") is True:
            protected.add(field.get("path"))
    protected.discard(None)
    manifest_failures = []
    dirty_cell_count = 0
    for item in manifest_records:
        if not isinstance(item, dict):
            manifest_failures.append("A manifest record is not an object")
            continue
        index = item.get("record_index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(clean.records):
            manifest_failures.append(f"Invalid manifest record index: {index!r}")
            continue
        changes = item.get("changes", [])
        if not isinstance(changes, list):
            manifest_failures.append(f"Record {index} has invalid changes")
            continue
        expected_paths = set()
        for change in changes:
            dirty_cell_count += 1
            if not isinstance(change, dict) or not isinstance(change.get("path"), str):
                manifest_failures.append(f"Record {index} has an invalid change")
                continue
            path = change["path"]
            expected_paths.add(path)
            if any(path == protected_path or path.startswith(f"{protected_path}/") for protected_path in protected):
                manifest_failures.append(f"Record {index} changes protected field {path}")
            try:
                clean_value = comparable_value(get_pointer(clean.records[index], path), clean.format_name)
                dirty_value = comparable_value(get_pointer(dirty.records[index], path), dirty.format_name)
            except DatasetError as exc:
                manifest_failures.append(f"Record {index} path {path}: {exc}")
                continue
            if comparable_value(change.get("clean_value"), clean.format_name) != clean_value:
                manifest_failures.append(f"Record {index} clean manifest value disagrees at {path}")
            if comparable_value(change.get("dirty_value"), dirty.format_name) != dirty_value:
                manifest_failures.append(f"Record {index} dirty manifest value disagrees at {path}")
        actual_paths = changed_paths(clean.records[index], dirty.records[index])
        if expected_paths != actual_paths:
            manifest_failures.append(
                f"Record {index} manifest paths {sorted(expected_paths)} differ from actual paths {sorted(actual_paths)}"
            )
    report.check(
        "manifest_change_evidence",
        not manifest_failures,
        "Every changed value matches the manifest" if not manifest_failures else manifest_failures[:25],
    )
    report.check(
        "manifest_hashes",
        manifest.get("clean_sha256") == sha256_file(args.clean)
        and manifest.get("dirty_sha256") == sha256_file(args.dirty),
        {
            "clean_hash_matches": manifest.get("clean_sha256") == sha256_file(args.clean),
            "dirty_hash_matches": manifest.get("dirty_sha256") == sha256_file(args.dirty),
        },
    )
    manifest_rate = manifest.get("actual_dirty_record_rate")
    report.check(
        "manifest_summary_counts",
        manifest.get("record_count") == len(clean.records)
        and manifest.get("dirty_record_count") == len(actual_dirty_indices)
        and manifest.get("dirty_cell_count") == dirty_cell_count
        and isinstance(manifest_rate, (int, float))
        and not isinstance(manifest_rate, bool)
        and math.isclose(float(manifest_rate), len(actual_dirty_indices) / len(clean.records) if clean.records else 0.0),
        {
            "manifest_record_count": manifest.get("record_count"),
            "manifest_dirty_record_count": manifest.get("dirty_record_count"),
            "manifest_dirty_cell_count": manifest.get("dirty_cell_count"),
            "manifest_rate": manifest_rate,
        },
    )

    source_fingerprints = {normalized_record_fingerprint(record) for record in source.records}
    clean_fingerprints = [normalized_record_fingerprint(record) for record in clean.records]
    overlapping_rows = sum(fingerprint in source_fingerprints for fingerprint in clean_fingerprints)
    row_overlap_policy = quality.get("source_row_overlap_policy")
    if row_overlap_policy is None:
        legacy_row_policy = quality.get("require_zero_source_row_overlap")
        row_overlap_policy = "reject" if legacy_row_policy is True else "allow"
    valid_row_overlap_policy = row_overlap_policy in {"allow", "reject"}
    report.check(
        "source_row_overlap_policy",
        valid_row_overlap_policy and (row_overlap_policy == "allow" or overlapping_rows == 0),
        {"exact_overlapping_rows": overlapping_rows, "policy": row_overlap_policy},
    )

    identifier_paths = generation.get("primary_identifiers", [])
    if not isinstance(identifier_paths, list) or any(
        not isinstance(path, str) or not path.startswith("/") for path in identifier_paths
    ):
        report.check("source_identifier_overlap_policy", False, "generation.primary_identifiers must be an array of paths")
    elif identifier_paths:
        source_ids = identifier_values(source, identifier_paths)
        clean_ids = identifier_values(clean, identifier_paths)
        overlaps = {
            path: len(source_ids[path].intersection(clean_ids[path])) for path in identifier_paths
        }
        identifier_overlap_policy = quality.get("source_identifier_overlap_policy")
        if identifier_overlap_policy is None:
            legacy_identifier_policy = quality.get("require_zero_identifier_overlap")
            identifier_overlap_policy = "reject" if legacy_identifier_policy is True else "allow"
        valid_identifier_overlap_policy = identifier_overlap_policy in {"allow", "reject"}
        report.check(
            "source_identifier_overlap_policy",
            valid_identifier_overlap_policy
            and (identifier_overlap_policy == "allow" or all(count == 0 for count in overlaps.values())),
            {"overlap_counts": overlaps, "policy": identifier_overlap_policy},
        )
    else:
        report.check(
            "source_identifier_overlap_policy",
            False,
            "No primary identifier paths were declared",
            severity="warning",
        )

    actual_rate = len(actual_dirty_indices) / len(clean.records) if clean.records else 0.0
    output = {
        "version": 1,
        "passed": not report.errors,
        "summary": {
            "source_record_count": len(source.records),
            "clean_record_count": len(clean.records),
            "dirty_record_count": len(actual_dirty_indices),
            "dirty_cell_count": dirty_cell_count,
            "selected_dirty_record_rate": float(selected_rate),
            "actual_dirty_record_rate": actual_rate,
            "max_dirty_record_rate": float(max_rate),
            "error_type_counts": dict(manifest_error_types),
            "exact_source_row_overlap_count": overlapping_rows,
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
