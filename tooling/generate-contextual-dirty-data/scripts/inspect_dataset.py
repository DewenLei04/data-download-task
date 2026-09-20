#!/usr/bin/env python3
"""Inspect a structured dataset without generating semantic content."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dataset_io import (
    DatasetError,
    discover_record_paths,
    get_pointer,
    json_safe,
    leaf_paths,
    load_dataset,
    normalized_record_fingerprint,
    sha256_file,
    write_json,
)


PATTERNS = {
    "email": re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$"),
    "url": re.compile(r"^https?://", re.IGNORECASE),
    "uuid": re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    ),
    "iso_date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "iso_datetime": re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
    "integer_text": re.compile(r"^[+-]?\d+$"),
    "decimal_text": re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$"),
}

TRAILING_INTEGER = re.compile(r"([0-9]+)$")


def quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def physical_type(value: Any) -> str:
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


def stable_value_key(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def physical_order_profile(values: list[Any]) -> dict[str, Any]:
    """Describe value cardinality and row-order signals without inferring semantics."""
    present = [value for value in values if value not in (None, "")]
    if not present:
        return {
            "non_null_count": 0,
            "unique_ratio": 0.0,
            "duplicate_value_count": 0,
            "duplicate_occurrence_count": 0,
            "cardinality_class": "empty",
            "layout_class": "not_applicable",
            "sequence_class": "not_applicable",
        }

    keys = [stable_value_key(value) for value in present]
    counts = Counter(keys)
    profile: dict[str, Any] = {
        "non_null_count": len(present),
        "unique_ratio": len(counts) / len(present),
        "duplicate_value_count": sum(count > 1 for count in counts.values()),
        "duplicate_occurrence_count": sum(count - 1 for count in counts.values()),
        "cardinality_class": "unique" if len(counts) == len(present) else "repeated",
        "layout_class": "unique" if len(counts) == len(present) else "grouped",
    }

    if len(keys) > 1:
        adjacent_pairs = list(zip(keys, keys[1:]))
        profile["adjacent_equal_ratio"] = sum(
            left == right for left, right in adjacent_pairs
        ) / len(adjacent_pairs)

        runs_by_value: Counter[str] = Counter()
        previous: str | None = None
        for key in keys:
            if key != previous:
                runs_by_value[key] += 1
                previous = key
        profile["values_split_across_multiple_runs"] = sum(
            run_count > 1 for run_count in runs_by_value.values()
        )
        repeated_value_count = profile["duplicate_value_count"]
        if repeated_value_count == 0:
            profile["layout_class"] = "unique"
        else:
            split_ratio = profile["values_split_across_multiple_runs"] / repeated_value_count
            profile["repeated_values_split_ratio"] = split_ratio
            if split_ratio >= 0.8:
                profile["layout_class"] = "interleaved"
            elif split_ratio <= 0.1:
                profile["layout_class"] = "grouped"
            else:
                profile["layout_class"] = "mixed"

        comparable: list[Any] = []
        if all(isinstance(value, str) for value in present):
            comparable = present
        elif all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in present
        ):
            comparable = [float(value) for value in present]
        if comparable:
            comparable_pairs = list(zip(comparable, comparable[1:]))
            profile["value_order"] = {
                "increase_ratio": sum(right > left for left, right in comparable_pairs)
                / len(comparable_pairs),
                "decrease_ratio": sum(right < left for left, right in comparable_pairs)
                / len(comparable_pairs),
                "equal_ratio": sum(right == left for left, right in comparable_pairs)
                / len(comparable_pairs),
            }

    suffixes: list[int] = []
    for value in present:
        if isinstance(value, int) and not isinstance(value, bool):
            suffixes.append(value)
        elif isinstance(value, str):
            match = TRAILING_INTEGER.search(value)
            if match:
                suffixes.append(int(match.group(1)))
    profile["trailing_integer_parse_ratio"] = len(suffixes) / len(present)
    if len(suffixes) > 1 and len(suffixes) == len(present):
        suffix_pairs = list(zip(suffixes, suffixes[1:]))
        profile["trailing_integer_order"] = {
            "increase_ratio": sum(right > left for left, right in suffix_pairs)
            / len(suffix_pairs),
            "decrease_ratio": sum(right < left for left, right in suffix_pairs)
            / len(suffix_pairs),
            "equal_ratio": sum(right == left for left, right in suffix_pairs)
            / len(suffix_pairs),
            "plus_one_ratio": sum(right - left == 1 for left, right in suffix_pairs)
            / len(suffix_pairs),
            "minus_one_ratio": sum(right - left == -1 for left, right in suffix_pairs)
            / len(suffix_pairs),
        }
    value_order = profile.get("value_order")
    suffix_order = profile.get("trailing_integer_order", {})
    if isinstance(value_order, dict):
        increasing = value_order["increase_ratio"]
        decreasing = value_order["decrease_ratio"]
        equal = value_order["equal_ratio"]
        if len(counts) == 1:
            profile["sequence_class"] = "constant"
        elif suffix_order.get("plus_one_ratio", 0.0) >= 0.9 and increasing + equal >= 0.98:
            profile["sequence_class"] = "sequential_ascending"
        elif suffix_order.get("minus_one_ratio", 0.0) >= 0.9 and decreasing + equal >= 0.98:
            profile["sequence_class"] = "sequential_descending"
        elif increasing + equal >= 0.98 and increasing > 0:
            profile["sequence_class"] = "monotonic_ascending"
        elif decreasing + equal >= 0.98 and decreasing > 0:
            profile["sequence_class"] = "monotonic_descending"
        else:
            profile["sequence_class"] = "non_monotonic"
    elif isinstance(suffix_order, dict) and suffix_order:
        if suffix_order["plus_one_ratio"] >= 0.9:
            profile["sequence_class"] = "sequential_ascending"
        elif suffix_order["minus_one_ratio"] >= 0.9:
            profile["sequence_class"] = "sequential_descending"
        elif suffix_order["increase_ratio"] + suffix_order["equal_ratio"] >= 0.98:
            profile["sequence_class"] = "monotonic_ascending"
        elif suffix_order["decrease_ratio"] + suffix_order["equal_ratio"] >= 0.98:
            profile["sequence_class"] = "monotonic_descending"
        else:
            profile["sequence_class"] = "non_monotonic"
    else:
        profile["sequence_class"] = "not_applicable"
    return profile


def profile_fields(records: list[dict[str, Any]], sample_limit: int) -> list[dict[str, Any]]:
    all_paths = sorted({path for record in records for path in leaf_paths(record)})
    profiles: list[dict[str, Any]] = []
    for path in all_paths:
        values: list[Any] = []
        missing_count = 0
        for record in records:
            try:
                values.append(get_pointer(record, path))
            except DatasetError:
                missing_count += 1

        type_counts = Counter(physical_type(value) for value in values)
        null_count = sum(value is None or value == "" for value in values)
        unique_keys = {stable_value_key(value) for value in values if value not in (None, "")}
        examples: list[Any] = []
        seen: set[str] = set()
        for value in values:
            if value in (None, ""):
                continue
            key = stable_value_key(value)
            if key not in seen:
                seen.add(key)
                examples.append(json_safe(value))
            if len(examples) >= sample_limit:
                break

        strings = [value for value in values if isinstance(value, str) and value]
        numeric_values: list[float] = []
        for value in values:
            if isinstance(value, bool) or value in (None, ""):
                continue
            try:
                numeric_values.append(float(value))
            except (TypeError, ValueError):
                continue

        pattern_counts: dict[str, int] = defaultdict(int)
        for value in strings:
            stripped = value.strip()
            for name, pattern in PATTERNS.items():
                if pattern.search(stripped):
                    pattern_counts[name] += 1

        profile: dict[str, Any] = {
            "path": path,
            "physical_types": dict(sorted(type_counts.items())),
            "missing_key_count": missing_count,
            "null_or_empty_count": null_count,
            "non_null_unique_count": len(unique_keys),
            "sample_values": examples,
            "representation": physical_order_profile(values),
        }
        present_values = [value for value in values if value not in (None, "")]
        if present_values:
            value_by_key = {stable_value_key(value): value for value in present_values}
            frequencies = Counter(stable_value_key(value) for value in present_values)
            value_distribution: dict[str, Any] = {
                "non_null_count": len(present_values),
                "unique_ratio": len(frequencies) / len(present_values),
            }
            if len(frequencies) <= 50 or frequencies.most_common(1)[0][1] > 1:
                value_distribution["most_frequent"] = [
                    {
                        "value": json_safe(value_by_key[key]),
                        "count": count,
                        "ratio": count / len(present_values),
                    }
                    for key, count in frequencies.most_common(20)
                ]
            profile["value_distribution"] = value_distribution
        if strings:
            lengths = [len(value) for value in strings]
            profile["string_length"] = {"min": min(lengths), "max": max(lengths)}
        if numeric_values and len(numeric_values) >= max(1, len(values) - null_count):
            ordered = sorted(numeric_values)
            profile["numeric_distribution"] = {
                "min": ordered[0],
                "p05": quantile(ordered, 0.05),
                "p25": quantile(ordered, 0.25),
                "median": quantile(ordered, 0.5),
                "p75": quantile(ordered, 0.75),
                "p95": quantile(ordered, 0.95),
                "max": ordered[-1],
            }
            profile["numeric_range"] = {"min": ordered[0], "max": ordered[-1]}
        iso_dates = [value.strip() for value in strings if PATTERNS["iso_date"].fullmatch(value.strip())]
        iso_datetimes = [
            value.strip() for value in strings if PATTERNS["iso_datetime"].search(value.strip())
        ]
        temporal_values = iso_dates if len(iso_dates) == len(strings) else iso_datetimes
        if temporal_values and len(temporal_values) == len(strings):
            profile["temporal_lexical_range"] = {
                "min": min(temporal_values),
                "max": max(temporal_values),
            }
        if pattern_counts:
            profile["recognized_patterns"] = dict(sorted(pattern_counts.items()))
        profiles.append(profile)
    return profiles


def representation_summary(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    sequence_classes: dict[str, list[str]] = defaultdict(list)
    layout_classes: dict[str, list[str]] = defaultdict(list)
    cardinality_classes: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        path = profile["path"]
        representation = profile.get("representation", {})
        sequence_classes[str(representation.get("sequence_class", "not_applicable"))].append(path)
        layout_classes[str(representation.get("layout_class", "not_applicable"))].append(path)
        cardinality_classes[str(representation.get("cardinality_class", "empty"))].append(path)
    return {
        "sequence_classes": dict(sorted(sequence_classes.items())),
        "layout_classes": dict(sorted(layout_classes.items())),
        "cardinality_classes": dict(sorted(cardinality_classes.items())),
        "agent_note": (
            "Classifications are field-name independent. Declare semantic key roles separately, "
            "then use match_source unless a source defect or domain invariant justifies an override."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Structured dataset to inspect")
    parser.add_argument("--output", type=Path, required=True, help="Output structure report")
    parser.add_argument(
        "--record-path",
        help="RFC 6901 pointer for JSON/YAML or sheet:SHEET_NAME for Excel",
    )
    parser.add_argument("--sample-records", type=int, default=5)
    parser.add_argument("--sample-values", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.sample_records < 0 or args.sample_values < 0:
        raise DatasetError("Sample limits must be nonnegative")

    dataset = load_dataset(args.input, args.record_path)
    metadata = {
        key: value
        for key, value in dataset.metadata.items()
        if key not in {"arrow_schema", "row_numbers"}
    }
    field_profiles = profile_fields(dataset.records, args.sample_values)
    row_fingerprints = [normalized_record_fingerprint(record) for record in dataset.records]
    row_counts = Counter(row_fingerprints)
    report = {
        "version": 1,
        "source": {
            "path": str(args.input),
            "size_bytes": args.input.stat().st_size,
            "sha256": sha256_file(args.input),
        },
        "physical_format": dataset.format_name,
        "record_path": dataset.record_path,
        "record_count": len(dataset.records),
        "record_repetition": {
            "unique_record_count": len(row_counts),
            "exact_duplicate_occurrence_count": sum(count - 1 for count in row_counts.values()),
            "duplicated_record_value_count": sum(count > 1 for count in row_counts.values()),
        },
        "container": json_safe(metadata),
        "fields": field_profiles,
        "representation_summary": representation_summary(field_profiles),
        "sample_records": json_safe(dataset.records[: args.sample_records]),
        "agent_note": (
            "Samples are navigation aids, not the source model. Infer conditions from whole-source "
            "statistics and direct source review. Reuse of observed values, combinations, identifiers, "
            "or rows is allowed when the generation specification supports it."
        ),
    }
    collection_paths = discover_record_paths(args.input)
    if len(collection_paths) > 1:
        collections = []
        for collection_path in collection_paths:
            collection = load_dataset(args.input, collection_path)
            collection_metadata = {
                key: value
                for key, value in collection.metadata.items()
                if key not in {"arrow_schema", "row_numbers"}
            }
            collection_profiles = profile_fields(collection.records, args.sample_values)
            collection_fingerprints = [
                normalized_record_fingerprint(record) for record in collection.records
            ]
            collection_counts = Counter(collection_fingerprints)
            collections.append(
                {
                    "record_path": collection.record_path,
                    "record_count": len(collection.records),
                    "container": json_safe(collection_metadata),
                    "record_repetition": {
                        "unique_record_count": len(collection_counts),
                        "exact_duplicate_occurrence_count": sum(
                            count - 1 for count in collection_counts.values()
                        ),
                        "duplicated_record_value_count": sum(
                            count > 1 for count in collection_counts.values()
                        ),
                    },
                    "fields": collection_profiles,
                    "representation_summary": representation_summary(collection_profiles),
                    "sample_records": json_safe(
                        collection.records[: args.sample_records]
                    ),
                }
            )
        report["collections"] = collections
        report["collection_coverage_required"] = True
        report["collection_agent_note"] = (
            "Every discovered collection must be classified in generation-spec.json as "
            "generate, preserve_reference, or preserve_documentation. Data-bearing collections "
            "must not pass through silently."
        )
    write_json(args.output, report)
    print(f"Wrote structure report for {len(dataset.records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
