#!/usr/bin/env python3
"""Normalize legacy single-collection and v4 multi-collection specifications."""

from __future__ import annotations

from typing import Any

from dataset_io import DatasetError


PRESERVE_HANDLINGS = {"preserve_reference", "preserve_documentation"}
VALID_HANDLINGS = {"generate", *PRESERVE_HANDLINGS}


def normalize_collections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    source = spec.get("source", {})
    generation = spec.get("generation", {})
    if not isinstance(source, dict) or not isinstance(generation, dict):
        raise DatasetError("source and generation must be objects")

    raw_source = source.get("collections")
    if raw_source is None:
        record_path = source.get("record_path", "")
        if not isinstance(record_path, str):
            raise DatasetError("source.record_path must be a string")
        return [
            {
                "record_path": record_path,
                "record_count": source.get("record_count"),
                "handling": "generate",
                "role": "logical record collection",
                "reason": "legacy single-collection specification",
                "generation": generation,
            }
        ]

    if not isinstance(raw_source, list) or not raw_source:
        raise DatasetError("source.collections must be a non-empty array")
    raw_generation = generation.get("collections")
    if not isinstance(raw_generation, list):
        raise DatasetError("generation.collections must be an array for a multi-collection spec")

    generated_by_path: dict[str, dict[str, Any]] = {}
    for item in raw_generation:
        if not isinstance(item, dict) or not isinstance(item.get("record_path"), str):
            raise DatasetError("Every generation collection requires a string record_path")
        path = item["record_path"]
        if path in generated_by_path:
            raise DatasetError(f"Duplicate generation collection path: {path!r}")
        generated_by_path[path] = item

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_source:
        if not isinstance(item, dict):
            raise DatasetError("Every source collection must be an object")
        path = item.get("record_path")
        handling = item.get("handling")
        if not isinstance(path, str):
            raise DatasetError("Every source collection requires a string record_path")
        if path in seen:
            raise DatasetError(f"Duplicate source collection path: {path!r}")
        seen.add(path)
        if handling not in VALID_HANDLINGS:
            raise DatasetError(
                f"Collection {path!r} handling must be one of {sorted(VALID_HANDLINGS)}"
            )
        reason = item.get("reason")
        role = item.get("role")
        if not isinstance(role, str) or not role.strip():
            raise DatasetError(f"Collection {path!r} requires a nonempty role")
        if handling in PRESERVE_HANDLINGS and (
            not isinstance(reason, str) or not reason.strip()
        ):
            raise DatasetError(
                f"Preserved collection {path!r} requires a nonempty evidence-backed reason"
            )
        generated = generated_by_path.get(path)
        if handling == "generate" and generated is None:
            raise DatasetError(f"Generated collection {path!r} has no generation contract")
        if handling != "generate" and generated is not None:
            raise DatasetError(f"Preserved collection {path!r} must not have a generation contract")
        result.append(
            {
                "record_path": path,
                "record_count": item.get("record_count"),
                "handling": handling,
                "role": role.strip(),
                "reason": reason.strip() if isinstance(reason, str) else "",
                "generation": generated,
            }
        )

    extras = sorted(set(generated_by_path) - seen)
    if extras:
        raise DatasetError(f"Generation collections are absent from source.collections: {extras}")
    return result


def generated_collections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in normalize_collections(spec) if item["handling"] == "generate"]


def collection_protected_fields(collection: dict[str, Any]) -> set[str]:
    generation = collection.get("generation") or {}
    protected = generation.get("protected_fields", [])
    fields = generation.get("fields", [])
    if not isinstance(protected, list) or any(
        not isinstance(path, str) or not path.startswith("/") for path in protected
    ):
        raise DatasetError(
            f"Collection {collection['record_path']!r} protected_fields must contain paths"
        )
    if not isinstance(fields, list):
        raise DatasetError(
            f"Collection {collection['record_path']!r} fields must be an array"
        )
    result = set(protected)
    for field in fields:
        if isinstance(field, dict) and field.get("corruption_prohibited") is True:
            result.add(field.get("path"))
    if any(not isinstance(path, str) or not path.startswith("/") for path in result):
        raise DatasetError("Protected fields must be nonempty JSON Pointer paths")
    return result
