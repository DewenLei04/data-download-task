# Artifact contracts

All artifacts use UTF-8 JSON with two-space indentation. JSON Pointer paths follow RFC 6901 and are relative to one logical record unless stated otherwise.

`synthetic-clean` and `synthetic-dirty` have an exact-field-name contract: source field names, case, header order, nested key paths, and sheet names are immutable. Dirty field values are expected to change and may differ in content, format, type, nullability, or collection contents when serializable. Generation or corruption metadata belongs in sidecar JSON and must never appear as an added `sync`, `dirty`, `error`, `status`, provenance, or similarly invented data field.

## `generation-spec.json` version 4

New runs must use version 4. It makes collection coverage and substantive content novelty explicit:

```json
{
  "version": 4,
  "source": {
    "physical_format": "excel",
    "collections": [
      {
        "record_path": "sheet:Events",
        "record_count": 1000,
        "role": "operational event records",
        "handling": "generate"
      },
      {
        "record_path": "sheet:Codebook",
        "record_count": 20,
        "role": "authoritative closed code lookup",
        "handling": "preserve_reference",
        "reason": "The codes define the schema vocabulary and are not sampled observations"
      },
      {
        "record_path": "sheet:Read me",
        "record_count": 8,
        "role": "human-readable workbook documentation",
        "handling": "preserve_documentation",
        "reason": "The sheet contains instructions rather than logical output records"
      }
    ]
  },
  "scenario_inference": {
    "domain": "application telemetry",
    "dataset_role": "multi-sheet operational export",
    "record_meaning": "one application event",
    "producer": "application service",
    "curation_level": "medium",
    "confidence": 0.9,
    "evidence": ["Workbook and field evidence supports the event interpretation"],
    "assumptions": []
  },
  "generation": {
    "record_count": 1000,
    "random_seed": 731942,
    "source_model": {
      "default_source_reuse": "allow",
      "dimensions": [
        {
          "name": "event_process",
          "scope": "relation",
          "paths": ["/event_id", "/status"],
          "evidence": "Whole-source profiling shows one identifier per event and a closed status vocabulary",
          "constraint_kind": "hard",
          "generation_strategy": "generate_conditionally",
          "generation_rule": "Generate each event under the observed identifier and status relationship"
        }
      ]
    },
    "collections": [
      {
        "record_path": "sheet:Events",
        "record_count": 1000,
        "primary_identifiers": ["/event_id"],
        "grouping_keys": [],
        "protected_fields": ["/event_id"],
        "representation": {
          "generation_mode": "direct",
          "record_order": {
            "policy": "match_source",
            "generation_guidance": "Author records directly in the source-supported final layout"
          },
          "field_profiles": [
            {
              "path": "/event_id",
              "value_role": "surrogate_identifier",
              "cardinality": "unique",
              "sequence_policy": "match_source",
              "record_layout": "preserve",
              "linked_paths": [],
              "direct_generation_guidance": "Generate unique identifiers directly in the source-supported final order"
            }
          ]
        },
        "novelty": {
          "minimum_changed_value_ratio": 0.5,
          "high_similarity_threshold": 0.9,
          "maximum_high_similarity_record_ratio": 0.25,
          "exemptions": [
            {
              "path": "/status",
              "reason": "A closed two-value operational vocabulary must be reused"
            }
          ]
        },
        "hard_constraints": [],
        "soft_constraints": [],
        "fields": [
          {
            "path": "/event_id",
            "meaning": "event identifier",
            "physical_type": "string",
            "nullable": false,
            "unique": true,
            "generation_guidance": "Generate a new identifier with the inferred syntax",
            "corruption_prohibited": true
          }
        ],
        "machine_rules": []
      }
    ]
  },
  "dirty_policy": {
    "unit": "record",
    "max_rate": 0.05,
    "selected_rate": 0.02,
    "collection_coverage": {
      "mode": "all_eligible_when_feasible"
    },
    "rationale": "The inferred production process supports a small residual error rate.",
    "error_types": [
      {
        "name": "invalid_status",
        "weight": 1.0,
        "eligible_record_paths": ["sheet:Events"],
        "eligible_fields": ["/status"],
        "constraint_violated": "Status must use the closed operational vocabulary"
      }
    ]
  },
  "quality": {
    "source_row_overlap_policy": "allow",
    "source_identifier_overlap_policy": "allow",
    "require_exact_record_count": true
  }
}
```

Every discovered collection must appear exactly once in `source.collections`. `handling: generate`
requires a matching entry in `generation.collections`. `preserve_reference` and
`preserve_documentation` prohibit a generation entry and require a nonempty reason. The global
`generation.record_count` is the sum of records in generated collections only.

Each generated collection requires a `novelty` contract. `minimum_changed_value_ratio` must be
`0.5`–`1.0`; `high_similarity_threshold` must be `0.8`–less than `1.0`; and
`maximum_high_similarity_record_ratio` must be `0.0`–`0.5`. Exemptions require both a path and a
source-supported reason. Missing/missing aligned cells do not count in the denominator. The
validator reports aggregate and per-field change ratios.

The planner samples across the union of all generated collections. Version 2 plans, patches, and
manifests identify records by the pair `(record_path, record_index)`.

`dirty_policy.collection_coverage.mode` may be `random_global` or
`all_eligible_when_feasible`. Prefer the latter for multi-collection containers. It reserves one
target in each eligible generated collection when the target count permits, otherwise it maximizes
the number of covered collections without changing the declared rate. The plan and validation
report list eligible, covered, and unavoidably uncovered record paths.

## Legacy `generation-spec.json` version 3

Version 3 remains readable for existing single-collection artifacts but must not be authored for
new runs. Its minimum shape is retained below for compatibility.

```json
{
  "version": 3,
  "source": {
    "physical_format": "csv",
    "record_path": "",
    "record_count": 1000
  },
  "scenario_inference": {
    "domain": "cybersecurity",
    "dataset_role": "curated vulnerability priority catalog",
    "record_meaning": "one published vulnerability assessment",
    "producer": "multi-source automated feed with analyst review",
    "curation_level": "high",
    "confidence": 0.91,
    "evidence": [
      "Fields include vulnerability identifiers, severity scores, and publication dates",
      "Severity and score values exhibit a documented cross-field relationship"
    ],
    "assumptions": []
  },
  "generation": {
    "record_count": 1000,
    "random_seed": 731942,
    "source_model": {
      "default_source_reuse": "allow",
      "dimensions": [
        {
          "name": "operational_time_regime",
          "scope": "sequence",
          "paths": ["/published_at", "/updated_at"],
          "evidence": "Whole-source ranges and pairwise offsets describe one recent operational window",
          "constraint_kind": "soft",
          "generation_strategy": "sample_empirical",
          "generation_rule": "Keep generated dates in the observed recency regime and preserve their offset distribution"
        },
        {
          "name": "severity_score_relationship",
          "scope": "relation",
          "paths": ["/severity", "/score"],
          "evidence": "Observed severity bands condition the score distribution",
          "constraint_kind": "hard",
          "generation_strategy": "recombine_conditionally",
          "generation_rule": "Generate score values only inside the band compatible with severity"
        }
      ]
    },
    "primary_identifiers": ["/vulnerability_id"],
    "grouping_keys": [],
    "protected_fields": ["/vulnerability_id"],
    "representation": {
      "generation_mode": "direct",
      "record_order": {
        "policy": "match_source",
        "generation_guidance": "Assign each record to its final physical position during generation; reproduce source sort keys, tie behavior, grouping, or unordered layout"
      },
      "field_profiles": [
        {
          "path": "/vulnerability_id",
          "value_role": "surrogate_identifier",
          "cardinality": "unique",
          "sequence_policy": "match_source",
          "record_layout": "preserve",
          "linked_paths": [],
          "direct_generation_guidance": "Generate a unique opaque identifier independently for each final row; never derive it from row number or batch order"
        }
      ]
    },
    "hard_constraints": [
      "Every vulnerability_id is unique and matches the inferred identifier syntax"
    ],
    "soft_constraints": [
      "High severity records tend to have higher priority scores"
    ],
    "fields": [
      {
        "path": "/vulnerability_id",
        "meaning": "synthetic vulnerability identifier",
        "physical_type": "string",
        "nullable": false,
        "pattern": "^SYN-[A-Z0-9-]+$",
        "unique": true,
        "generation_guidance": "Create a unique synthetic identifier without reusing source identifiers",
        "corruption_prohibited": true
      }
    ],
    "machine_rules": [
      {
        "name": "update_not_before_publication",
        "kind": "comparison",
        "left": "/updated_at",
        "operator": ">=",
        "right": "/published_at",
        "coerce": "string",
        "allow_null": false
      }
    ]
  },
  "dirty_policy": {
    "unit": "record",
    "max_rate": 0.05,
    "selected_rate": 0.012,
    "rationale": "The inferred catalog is highly curated, so a low residual error rate is appropriate.",
    "error_types": [
      {
        "name": "score_severity_conflict",
        "weight": 0.4,
        "eligible_fields": ["/severity", "/score"],
        "constraint_violated": "Severity must agree with score band"
      },
      {
        "name": "temporal_inconsistency",
        "weight": 0.3,
        "eligible_fields": ["/published_at", "/updated_at"],
        "constraint_violated": "updated_at must not precede published_at"
      },
      {
        "name": "invalid_category",
        "weight": 0.3,
        "eligible_fields": ["/status"],
        "constraint_violated": "Status must belong to the inferred controlled vocabulary"
      }
    ]
  },
  "quality": {
    "source_row_overlap_policy": "allow",
    "source_identifier_overlap_policy": "allow",
    "require_exact_record_count": true
  }
}
```

The planner requires `generation.record_count`, `generation.random_seed`, `dirty_policy.max_rate`, `dirty_policy.selected_rate`, and at least one error type when the selected rate produces targets. Each error type requires a name, positive weight, and at least one eligible field.

The validator recognizes these optional field constraints: `allowed_values`, `pattern`, `minimum`, `maximum`, and `unique`. It recognizes `comparison` machine rules with `left`, `operator`, `right`, `coerce` (`string` or `number`), and `allow_null`. The agent must audit constraints that cannot be expressed with these primitives.

`generation.source_model.dimensions` is deliberately schema-independent. A dimension may use `dataset`, `field`, `relation`, `group`, `sequence`, or `representation` scope and may reference zero or more JSON Pointer paths. Use any concise evidence representation that identifies the whole-source observation behind the rule. Supported generation strategy names are `reuse_observed`, `sample_empirical`, `recombine_conditionally`, `bounded_extension`, `generate_conditionally`, and `derive`; a dimension may list more than one when necessary. The agent must audit each declared dimension even when no deterministic validator exists for it.

`generation.source_model.default_source_reuse` is `allow` or `restrict`. Use `allow` by default. `restrict` requires a user request, privacy requirement, or data-semantic reason recorded in the specification; it is not implied by the words synthetic or from scratch.

`quality.source_row_overlap_policy` and `quality.source_identifier_overlap_policy` are `allow` or `reject`. Omit them to allow overlap. Overlap is always measured and reported. Select `reject` only when the user, privacy requirements, or an inferred domain rule requires source independence; novelty is not an implicit property of generation from scratch. The legacy booleans `require_zero_source_row_overlap` and `require_zero_identifier_overlap` remain accepted for older specifications.

`generation.representation.field_profiles` uses JSON Pointer paths and is independent of field names and physical format. It is required for every declared primary identifier and grouping key; also include ordinals or other fields needed to reproduce observable physical ordering. Supported values are:

- `value_role`: a semantic representation role such as `surrogate_identifier`, `ordinal`, `timestamp`, `category`, or `measurement`;
- `cardinality`: `match_source`, `unique`, or `repeated`;
- `sequence_policy`: `match_source`, `preserve`, `non_sequential`, `sequential_ascending`, `sequential_descending`, `monotonic_ascending`, `monotonic_descending`, or `constant`;
- `record_layout`: `match_source`, `preserve`, `interleaved`, `grouped`, or `mixed`;
- `max_adjacent_equal_ratio`: optional domain-supported threshold from `0.0` to `1.0`; do not invent one when class matching is sufficient;
- `linked_paths`: optional paths whose equality or reference relationship must be maintained during direct generation;
- `direct_generation_guidance`: required in version 3; an evidence-backed instruction for producing this field in its final rows without later permutation.

Version 3 requires `generation.representation.generation_mode` to be `direct`. It also requires `record_order.policy` (`match_source` or `explicit`) and a nonempty `record_order.generation_guidance`. The guidance describes how final row positions will reproduce observed sort keys, tie groups, interleaving, grouping, or unordered layout. The generation seed may make direct choices reproducible, but it is not a post-generation shuffle instruction.

Prefer `match_source` so validation compares the source and generated `cardinality_class`, `sequence_class`, and `layout_class`. Override it only to repair an inferred source defect in clean data or to enforce a supported domain rule. Derive direct-generation instructions from whole-column source evidence: meaningful sorted data stays sorted, non-monotonic identifiers are authored non-monotonically, and unordered exports are assigned directly across final positions.

## `corruption-plan.json`

The planner writes this file. Do not edit target identities after creation.

```json
{
  "version": 1,
  "record_path": "",
  "record_count": 1000,
  "selected_rate": 0.012,
  "max_rate": 0.05,
  "target_count": 12,
  "random_seed": 731942,
  "protected_fields": ["/vulnerability_id"],
  "targets": [
    {
      "patch_id": "dirty-000001",
      "record_path": "sheet:Events",
      "record_index": 42,
      "error_type": "score_severity_conflict",
      "suggested_field": "/severity",
      "eligible_fields": ["/severity", "/score"]
    }
  ]
}
```

Record indices are zero-based within `record_path`. Version 2 plans also include a
`global_record_index` used only for reproducible sampling across generated collections.

## `dirty-patches.json`

The agent writes this file after reading the plan and targeted clean records.

```json
{
  "version": 1,
  "patches": [
    {
      "patch_id": "dirty-000001",
      "record_path": "sheet:Events",
      "record_index": 42,
      "error_type": "score_severity_conflict",
      "changes": [
        {
          "path": "/severity",
          "value": "LOW"
        }
      ],
      "explanation": "The new severity contradicts the generated score band."
    }
  ]
}
```

Use only the `set` behavior represented above. Every path must already exist in the targeted clean record and must belong to that plan target's `eligible_fields`. Express a missing value as an empty string or null when allowed by the container; do not delete keys. Object or array values may be replaced only without adding, removing, or renaming any contained field names. A cross-field error may contain multiple eligible changes.

## `dirty-manifest.json`

The patch application script writes the manifest. It records every changed value, including its clean and dirty representations, and the exact dirty-record and dirty-cell counts.

## `validation-report.json`

The validator writes:

- `passed`: overall boolean;
- `checks`: named checks with status and evidence;
- source, clean, and dirty format and record counts;
- requested and actual dirty-record rates;
- dirty-record and dirty-cell counts;
- exact source-row and identifier overlap findings and their declared policies;
- complete collection coverage and explicit preservation findings;
- per generated collection: changed-value ratio, exact aligned rows, high-similarity-record ratio,
  and per-field change ratios after justified novelty exemptions;
- declared identifier cardinality, sequence-leakage, and record-layout findings;
- errors and warnings.

A warning documents a limitation or ambiguous condition. An error makes `passed` false.

## `semantic-audit.json`

The agent writes this file after deterministic validation succeeds:

```json
{
  "version": 1,
  "passed": true,
  "scenario_consistency": {
    "passed": true,
    "evidence": ["Generated values represent the inferred record unit and producer"]
  },
  "source_fidelity_checks": [
    {
      "dimension": "severity_score_relationship",
      "passed": true,
      "evidence": "Conditional score ranges by severity remain inside the source-supported bands"
    }
  ],
  "clean_constraint_checks": [
    {
      "constraint": "Severity agrees with score band",
      "passed": true,
      "evidence": "All 1000 clean records were reviewed in bounded batches"
    }
  ],
  "dirty_patch_checks": [
    {
      "patch_id": "dirty-000001",
      "record_index": 42,
      "passed": true,
      "evidence": "The severity at /severity contradicts the score at /score"
    }
  ],
  "untargeted_record_check": {
    "passed": true,
    "evidence": "No untargeted record differs from the clean dataset"
  },
  "assumptions_reviewed": [],
  "failures": []
}
```

Set `passed` to true only when every nested check passes. Use concise evidence tied to actual fields and records; do not restate the specification without examining the output.

## Format notes

- CSV and TSV preserve header order and delimiter. Dirty values must remain scalar.
- Across every format, clean and dirty outputs preserve the source's exact field names; no error-marker or synchronization field is added to the data table.
- JSON and YAML may use an array at the root or a nested record collection selected by JSON Pointer.
- JSONL and NDJSON require one object per nonblank line.
- Excel uses `sheet:SHEET_NAME` as the record path. The reader uses the first nonempty row by
  default, but recognizes a substantially denser, unique, text-dominant row near the top as the
  table header when title or explanatory rows precede it. The detected one-based `header_row` is
  recorded in the container metadata. Completely blank trailing header cells are treated as sheet
  formatting, not invented data fields; unnamed cells between named columns retain stable internal
  placeholders so their physical positions are preserved.
- Parquet requires `pyarrow`; dirty values must remain compatible with the physical column schema.
- YAML requires `PyYAML`; Excel requires `openpyxl`.
- Unsupported or dependency-limited formats may be inspected directly by the agent, but deterministic validation must use an appropriate local parser before completion.
