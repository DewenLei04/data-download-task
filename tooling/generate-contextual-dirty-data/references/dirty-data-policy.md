# Contextual dirty-data policy

Use this reference to choose the dirty-record rate and corruption mix. The agent makes both decisions; Python enforces them.

## Select the rate

Set `max_rate` to `0.05`. Select `selected_rate` from `0.0` through `0.05` after inferring how the data is produced and curated.

Use these ranges as guidance, not fixed mappings:

| Inferred production context | Typical selected rate |
| --- | ---: |
| Highly reviewed reference or regulated master data | 0.005-0.010 |
| Curated scientific, administrative, or official extract | 0.010-0.020 |
| Automated application, API, log, or telemetry output | 0.020-0.030 |
| Manual entry, spreadsheet workflow, or multi-source integration | 0.030-0.050 |

Adjust within the range using evidence about validation controls, manual handling, integration complexity, repeated transformations, and expected downstream use. Use a lower rate when inference confidence is low. Explain the selected value in one or two dataset-specific sentences.

The primary rate is:

```text
unique dirty logical records / total logical records
```

Compute the exact target count with `floor(record_count * selected_rate)`. Do not round up. For fewer than 20 records, a 5% cap may permit zero dirty records.

## Cover multi-collection containers

For a workbook or nested container, normally declare `dirty_policy.collection_coverage.mode` as `all_eligible_when_feasible`. A collection is eligible when it is handled as `generate` and at least one record contains an eligible, unprotected corruption field. The planner reserves one target per eligible collection before allocating the remainder across the combined record population. If fewer targets exist than eligible collections, maximize the number of distinct collections covered and report which ones remain uncovered. Reference and documentation collections are never eligible. Do not raise the selected rate or exceed the 5% cap to manufacture full coverage.

## Select error types

Choose only errors that could plausibly arise in the inferred production process and that can be evaluated from the specification. Assign positive weights that sum to any positive number; the planner normalizes them.

Useful categories include:

- `missing_value`: replace an expected value with the format's valid missing representation;
- `invalid_category`: use a plausible but unsupported label, spelling variant, or stale code;
- `format_violation`: damage identifier, date, unit, or code formatting while keeping the file readable;
- `range_violation`: use a domain-invalid but physically serializable value;
- `precision_or_unit_error`: apply an incorrect scale, unit, sign, or decimal placement;
- `cross_field_conflict`: create a contradiction between fields in one record;
- `temporal_inconsistency`: violate chronology, cadence, or effective-date relationships;
- `referential_inconsistency`: use a syntactically valid but unresolved generated key;
- `duplicate_semantics`: create a logical duplicate using a new physical record representation;
- `text_noise`: introduce truncation, whitespace, encoding-like artifacts, or a realistic typo;
- `aggregation_mismatch`: make a subtotal or derived value disagree with its components.

Rename or specialize categories when domain-specific names improve auditability. For example, a vulnerability catalog may use `cvss_severity_conflict`, while a laboratory table may use `detection_limit_violation`.

## Protect structure and sensitive fields

Corruption changes data values while preserving every source field or column name exactly, including spelling, case, order, and nested path. Values may become missing, malformed, mistyped, out of range, inconsistent, or otherwise dirty. Never add a marker column or key such as `sync`, `dirty`, `error`, `status`, or a suffixed copy of an existing name. Never remove or rename a field. Store corruption metadata only in the patch, manifest, and validation sidecars.

An object or array value may be changed when useful, but any field names contained within it must remain unchanged. A replacement must not use a new nested key to encode the error.

Do not corrupt:

- fields required to locate or patch a record;
- primary keys unless key corruption is an explicitly selected, safely auditable error type;
- serialization-critical container fields;
- partition or sheet routing fields when corruption would make the file unreadable;
- fields for which the scenario is too uncertain to define an invalid value.

Prefer one conceptual error per target record. A conceptual cross-field error may change multiple cells in the same record and still counts as one dirty record.

## Author values with the agent

The planner selects record indices, error types, and suggested fields. It never invents replacement values. Inspect each selected clean record and author an exact patch that:

- differs from the clean value;
- matches the assigned error type;
- violates a documented clean constraint or expectation;
- remains serializable;
- does not reproduce a source value merely to create an error;
- includes a short explanation of why the value is dirty in this scenario;
- uses only existing paths listed in that target's `eligible_fields` and leaves all field names unchanged.

Do not insert arbitrary symbols or nulls when a more realistic domain error is available.
