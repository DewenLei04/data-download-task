#!/usr/bin/env python3
"""Apply exact agent-authored dirty-data patches to a clean dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dataset_io import (
    DatasetError,
    field_name_structure,
    get_pointer,
    json_safe,
    load_dataset,
    read_json,
    save_collection_datasets,
    set_pointer,
    sha256_file,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean", type=Path, help="Agent-generated clean dataset")
    parser.add_argument("patches", type=Path, help="Agent-authored patch file")
    parser.add_argument("--plan", type=Path, required=True, help="Corruption plan used to author patches")
    parser.add_argument("--output", type=Path, required=True, help="Output dirty dataset")
    parser.add_argument("--manifest", type=Path, required=True, help="Output change manifest")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.resolve() == args.clean.resolve():
        raise DatasetError("The dirty output must not overwrite the clean dataset")

    plan = read_json(args.plan)
    patch_document = read_json(args.patches)
    if not isinstance(plan, dict) or not isinstance(patch_document, dict):
        raise DatasetError("The plan and patch document must be JSON objects")
    if plan.get("clean_sha256") != sha256_file(args.clean):
        raise DatasetError("The clean dataset no longer matches the corruption plan")

    raw_collections = plan.get("collections")
    if raw_collections is None:
        raw_collections = [
            {
                "record_path": plan.get("record_path", ""),
                "record_count": plan.get("record_count"),
                "protected_fields": plan.get("protected_fields", []),
            }
        ]
    if not isinstance(raw_collections, list) or not raw_collections:
        raise DatasetError("Plan collections must be a nonempty array")
    states: dict[str, dict[str, Any]] = {}
    for item in raw_collections:
        if not isinstance(item, dict) or not isinstance(item.get("record_path"), str):
            raise DatasetError("Every plan collection requires a string record_path")
        record_path = item["record_path"]
        if record_path in states:
            raise DatasetError(f"Duplicate plan collection path: {record_path!r}")
        protected_fields = item.get("protected_fields", [])
        if not isinstance(protected_fields, list) or any(
            not isinstance(path, str) or not path.startswith("/")
            for path in protected_fields
        ):
            raise DatasetError("Plan protected_fields must contain JSON Pointer paths")
        dataset = load_dataset(args.clean, record_path)
        if item.get("record_count") != len(dataset.records):
            raise DatasetError(
                f"Plan collection {record_path!r} record count does not match clean data"
            )
        states[record_path] = {
            "dataset": dataset,
            "protected_fields": protected_fields,
        }
    planned_targets = plan.get("targets")
    patches = patch_document.get("patches")
    if not isinstance(planned_targets, list) or not isinstance(patches, list):
        raise DatasetError("Plan targets and dirty patches must be arrays")
    if len(patches) != len(planned_targets):
        raise DatasetError(
            f"Expected {len(planned_targets)} patches from the plan, received {len(patches)}"
        )

    target_by_id = {}
    for target in planned_targets:
        if not isinstance(target, dict) or not isinstance(target.get("patch_id"), str):
            raise DatasetError("Every plan target requires a patch_id")
        target_by_id[target["patch_id"]] = target
    if len(target_by_id) != len(planned_targets):
        raise DatasetError("Plan patch IDs must be unique")

    seen_patch_ids: set[str] = set()
    manifest_records = []
    for patch in patches:
        if not isinstance(patch, dict):
            raise DatasetError("Every patch must be an object")
        patch_id = patch.get("patch_id")
        if patch_id not in target_by_id:
            raise DatasetError(f"Unknown patch_id: {patch_id!r}")
        if patch_id in seen_patch_ids:
            raise DatasetError(f"Duplicate patch_id: {patch_id!r}")
        seen_patch_ids.add(patch_id)
        target = target_by_id[patch_id]
        record_path = target.get("record_path", plan.get("record_path", ""))
        if record_path not in states:
            raise DatasetError(f"Patch {patch_id} has an unknown record_path {record_path!r}")
        patch_record_path = patch.get("record_path", record_path)
        if patch_record_path != record_path:
            raise DatasetError(f"Patch {patch_id} changed its planned record_path")
        dataset = states[record_path]["dataset"]
        protected_fields = states[record_path]["protected_fields"]
        if patch.get("record_index") != target.get("record_index"):
            raise DatasetError(f"Patch {patch_id} changed its planned record_index")
        if patch.get("error_type") != target.get("error_type"):
            raise DatasetError(f"Patch {patch_id} changed its planned error_type")
        explanation = patch.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            raise DatasetError(f"Patch {patch_id} requires a nonempty explanation")

        record_index = target["record_index"]
        if not isinstance(record_index, int) or not 0 <= record_index < len(dataset.records):
            raise DatasetError(f"Patch {patch_id} has an invalid record index")
        changes = patch.get("changes")
        if not isinstance(changes, list) or not changes:
            raise DatasetError(f"Patch {patch_id} requires at least one change")
        change_paths = [change.get("path") for change in changes if isinstance(change, dict)]
        if len(change_paths) != len(changes) or any(not isinstance(path, str) or not path for path in change_paths):
            raise DatasetError(f"Patch {patch_id} has an invalid change path")
        if len(change_paths) != len(set(change_paths)):
            raise DatasetError(f"Patch {patch_id} repeats a change path")
        protected_changes = [
            path
            for path in change_paths
            if any(
                path == protected_path or path.startswith(f"{protected_path}/")
                for protected_path in protected_fields
            )
        ]
        if protected_changes:
            raise DatasetError(f"Patch {patch_id} changes protected fields: {protected_changes}")
        eligible_fields = target.get("eligible_fields", [])
        unexpected_paths = sorted(set(change_paths) - set(eligible_fields))
        if unexpected_paths:
            raise DatasetError(
                f"Patch {patch_id} changes paths outside its planned eligible fields: "
                f"{unexpected_paths}"
            )

        record = dataset.records[record_index]
        original_structure = field_name_structure(record)
        applied_changes = []
        for change in changes:
            path = change["path"]
            if "value" not in change:
                raise DatasetError(f"Patch {patch_id} change {path!r} has no value")
            old_value = get_pointer(record, path)
            new_value: Any = change["value"]
            if field_name_structure(old_value) != field_name_structure(new_value):
                raise DatasetError(
                    f"Patch {patch_id} change {path!r} adds, removes, or renames contained "
                    "field names"
                )
            if dataset.format_name in {"csv", "tsv"}:
                if isinstance(new_value, (dict, list)):
                    raise DatasetError(f"Patch {patch_id} uses a non-scalar delimited value")
                new_value = "" if new_value is None else str(new_value)
            if old_value == new_value:
                raise DatasetError(f"Patch {patch_id} does not change {path!r}")
            set_pointer(record, path, new_value)
            applied_changes.append(
                {"path": path, "clean_value": json_safe(old_value), "dirty_value": json_safe(new_value)}
            )
        if field_name_structure(record) != original_structure:
            raise DatasetError(f"Patch {patch_id} changes field names or record structure")
        manifest_records.append(
            {
                "patch_id": patch_id,
                "record_path": record_path,
                "record_index": record_index,
                "error_type": patch["error_type"],
                "explanation": explanation.strip(),
                "changes": applied_changes,
            }
        )

    if seen_patch_ids != set(target_by_id):
        missing = sorted(set(target_by_id) - seen_patch_ids)
        raise DatasetError(f"Missing planned patches: {missing}")

    save_collection_datasets(
        [state["dataset"] for state in states.values()],
        args.output,
    )
    dirty_cell_count = sum(len(item["changes"]) for item in manifest_records)
    total_record_count = sum(len(state["dataset"].records) for state in states.values())
    manifest = {
        "version": 2 if len(states) > 1 else 1,
        "clean_sha256": sha256_file(args.clean),
        "dirty_sha256": sha256_file(args.output),
        "plan_sha256": sha256_file(args.plan),
        "record_path": next(iter(states)),
        "record_count": total_record_count,
        "collections": [
            {
                "record_path": path,
                "record_count": len(state["dataset"].records),
            }
            for path, state in states.items()
        ],
        "dirty_record_count": len(manifest_records),
        "dirty_cell_count": dirty_cell_count,
        "actual_dirty_record_rate": (
            len(manifest_records) / total_record_count if total_record_count else 0.0
        ),
        "records": sorted(
            manifest_records,
            key=lambda item: (item["record_path"], item["record_index"]),
        ),
    }
    write_json(args.manifest, manifest)
    print(f"Applied {len(manifest_records)} dirty-record patches; wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
