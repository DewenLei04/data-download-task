---
name: generate-contextual-dirty-data
description: Infer the format, structure, semantics, constraints, distributions, and data-production context of a user-supplied structured dataset, then generate a source-conditioned dataset and inject a context-appropriate amount of realistic dirty data. Use for CSV, TSV, JSON, JSONL, Excel, Parquet, or YAML inputs when the user wants synthetic test data, data-quality fixtures, dirty-data augmentation, corruption benchmarks, or clean/dirty dataset pairs without supplying a separate scenario description.
---

# Generate Contextual Dirty Data

Create a newly generated, source-conditioned clean dataset and a controlled dirty counterpart from a user-supplied structured data file. Infer the scenario without asking the user for a domain description.

## Non-negotiable rules

- Treat the source as the primary empirical description of the world the output must inhabit. Learn its structure, vocabulary, value support, ranges, distributions, dependencies, temporal regime, repetition, and ordering before deciding how to generate.
- "Generate from scratch" means construct materially new content through a declared generation process rather than editing or lightly perturbing the source in place. Individual observed values, identifiers, phrases, combinations, or rows may be reused when the source model supports them, but a data-bearing generated collection must not be an unchanged or near-copy of the source as a whole. Field-name identity is a structural requirement and never a reason to preserve field values.
- Operate only on files the user supplies. Do not discover websites, authenticate to portals, crawl pages, or download datasets.
- The agent must infer and declare the source-conditioned generation model. Python may measure evidence, sample or recombine observed distributions under that model, perform exact derivations, assemble records, serialize, and validate; it must not substitute generic Faker-style values or arbitrary randomness for semantic inference.
- Let the agent select the dirty-record rate from the inferred data-production context. Do not ask the user to choose a rate or expose it as a required input.
- Treat `0.05` as a hard maximum dirty-record rate. Python must reject a larger value.
- Count dirty records, not dirty cells, as the primary metric. Report dirty-cell counts separately.
- Use Python for physical inspection, source-conditioned sampling or recombination explicitly authorized by the source model, exact derivation, serialization, batch assembly, target selection, patch application, and validation. Do not use a post-generation permutation or shuffle to repair representation that the agent should have generated correctly.
- Treat field cardinality, value predictability, and physical record order as separate properties. Never infer that a unique value should be serialized as a row counter, or that equal values should be contiguous, unless whole-column source evidence supports those properties.
- Preserve the source field-name schema exactly in both generated datasets. Field and column names, their spelling and case, header order, nested key paths, and sheet names must remain source-identical. Dirty values themselves may change in content, format, type, nullability, or collection contents when the scenario and physical format allow it. Never add, remove, rename, suffix, or prefix a field, and never add marker fields such as `sync`, `dirty`, `error`, `status`, or provenance metadata unless that exact field already belongs to the source schema.
- Keep the clean and dirty datasets. Never overwrite the source.
- Keep the output container readable. A dirty semantic value may be invalid for the domain, but it must remain serializable by the physical format.
- Cover every logical collection in a container. Every workbook sheet or discovered nested record collection must be declared as generated, preserved reference material, or preserved documentation. Never silently pass through a data-bearing collection merely because one collection was selected as the primary record path.

## Workflow

### 1. Establish paths

Treat each input file as a separate dataset. Create a dedicated output directory. Preserve the source extension for both generated datasets.

Set the path to this skill directory as `SKILL_DIR` for the commands below.

### 2. Inspect the source

Run:

```bash
python3 "$SKILL_DIR/scripts/inspect_dataset.py" INPUT_FILE \
  --output OUTPUT_DIR/structure-report.json
```

For a nested container or multi-sheet workbook, the report includes a `collections` profile for every discovered collection. Use RFC 6901 JSON Pointer for JSON or YAML and `sheet:SHEET_NAME` for Excel. Review every collection; `--record-path` changes only the top-level navigation view and does not waive full-container coverage.

Read the source and `structure-report.json`. Infer the scenario from filenames, container names, field names, units, value shapes, relations, distributions, physical row-order signals, and local metadata. Do not request a scenario description from the user.

Model the source at multiple levels rather than as independent columns: dataset regime, record unit, field value support, cross-field dependencies, repeated entities, within-group structure, temporal or other sequence behavior, and physical representation. Read enough of the entire source to distinguish stable conditions from incidental examples; do not extrapolate the first few rows into a rule.

For every primary identifier, grouping key, ordinal, and other field carrying an observable row-order signal, explicitly distinguish:

- whether values are unique or repeated;
- whether repetition represents a relationship, a legitimate duplicate, or a data-quality defect;
- whether numeric or numeric-suffix values are monotonic, sequential, or non-monotonic in physical row order;
- whether repeated entities are grouped, interleaved, or unordered.

Use `representation_summary` plus the per-field `representation` statistics and their `cardinality_class`, `sequence_class`, and `layout_class` in `structure-report.json`; do not draw an ordering conclusion from field names or the first few sample rows. Do not hardcode schema-specific names or naming suffixes; profiles use JSON Pointer paths and apply to any field in any supported format.

### 3. Write the generation specification

Read [semantic-inference.md](references/semantic-inference.md), [dirty-data-policy.md](references/dirty-data-policy.md), and [artifact-contracts.md](references/artifact-contracts.md). Write a version 4 `generation-spec.json` before generating data.

Include:

- physical format and a complete `source.collections` inventory. Give each collection its record count, semantic role, and `handling`: `generate`, `preserve_reference`, or `preserve_documentation`. Preservation requires an evidence-backed reason and is appropriate only for canonical reference content or documentation, not ordinary data rows;
- inferred domain, dataset role, record meaning, evidence, confidence, and assumptions;
- field meanings, types, units, dependencies, hard constraints, soft distributions, and machine-checkable rules where possible;
- `generation.source_model`, containing evidence-backed dimensions at dataset, field, relation, group, or sequence scope; for each dimension record the observed condition, whether it is hard or soft, and the chosen generation strategy;
- a reuse policy for observed values and combinations. Default to allowing source reuse and row similarity; use restrictive overlap policies only when supported by the task or data semantics;
- total generated record count and a `generation.collections` contract for every collection handled as `generate`;
- per generated collection: record count, primary identifiers, grouping keys, fields that must not be corrupted, hard/soft constraints, field models, machine rules, and `representation` with `generation_mode: direct`;
- per generated collection: a `novelty` contract containing evidence-backed exemptions for genuinely canonical fields, `minimum_changed_value_ratio` from `0.5` through `1.0`, `high_similarity_threshold` from `0.8` up to but not including `1.0`, and `maximum_high_similarity_record_ratio` from `0.0` through `0.5`;
- an agent-selected dirty-record rate from `0.0` through `0.05`, with a scenario-specific rationale;
- weighted, context-specific error types and eligible fields;
- a reproducible integer random seed;
- source-fidelity and validation requirements.

Treat exact field-name identity as an unconditional artifact invariant, not as a configurable corruption type. This protects names and paths, not field values. Classify fields by semantic role: canonical/closed fields may be reused or exempted with a reason; open-ended, measured, transactional, entity, and derived fields must be newly instantiated, conditionally recombined, or recalculated at substantive coverage.

Proceed automatically when inference is uncertain. Choose a conservative, source-supported interpretation, record the uncertainty, and avoid unsupported factual claims. Do not make values deliberately unrealistic merely to signal that the output was generated. Apply privacy transformations only when requested or when the source contains personal or confidential data that should not be reproduced.

### 4. Generate the clean dataset from the source model

Generate the final clean dataset with the same physical format, complete collection inventory, field order, nested shape, sheet names, and per-collection record counts unless the user explicitly requested another count.

Reuse the source's exact field names. Do not introduce fields that explain generation, synchronization, dirtiness, provenance, confidence, or processing state inside `synthetic-clean` or `synthetic-dirty`; those details belong only in the JSON sidecar artifacts.

Honor the specification's hard constraints, soft distributions, and realistic cross-field relationships. Use the generation strategy declared for each modeled dimension: reuse observed support, sample its empirical distribution, recombine compatible values, extend within inferred bounds, generate conditionally, or derive from related fields. These are general strategies, not field-name rules.

Keep the source and its evidence available during generation. Closed or source-defined vocabularies normally reuse observed values. Open-ended values may reuse observed values or introduce nearby values only when their type, domain, and bounds are supported. Preserve joint behavior: do not independently combine fields when the source shows dependencies. An individual source-like row is not itself an error, but collection-wide high similarity is. Do not satisfy novelty by changing one convenient field in every otherwise copied row.

For containers with multiple collections, generate every collection marked `generate` into the same final container. A collection may remain value-identical only when it is explicitly marked `preserve_reference` or `preserve_documentation` with a source-supported reason. Before corruption planning, measure every generated collection against its aligned source records and repair any collection that fails its changed-value or high-similarity-record thresholds.

Before authoring the first record, turn the representation profiles into a full-output placement plan:

- If a field is sequential or monotonic, generate it in the observed direction and cadence.
- If a field is non-monotonic or random-looking, generate or select each value directly for its final row; do not create counters and plan to shuffle them later.
- If repeated values are grouped, interleaved, or mixed, plan their final row positions and equality groups first. Preserve linked-key equality while generating all related records.
- If records follow one or more explicit sort keys, record the sort precedence and generate rows in that final order. Model tie groups separately instead of globally shuffling the file.
- If the source is unordered, distribute records across final positions during generation using the declared seed and source-conditioned sampling policy.

Python may execute this already-declared placement, sampling, or derivation plan for large outputs. It must write `synthetic-clean.EXT` directly in final physical order. Do not create a knowingly sequential or grouped intermediate representation and correct it afterward. Complete clean generation before selecting corruption targets because all later artifacts use final physical record indices.

### 5. Select corruption targets

Run:

```bash
python3 "$SKILL_DIR/scripts/plan_corruption.py" \
  OUTPUT_DIR/synthetic-clean.EXT OUTPUT_DIR/generation-spec.json \
  --output OUTPUT_DIR/corruption-plan.json
```

The script computes `floor(record_count * selected_rate)`, samples distinct records, and assigns weighted error types and suggested eligible fields. It does not generate data values.

For containers with multiple generated collections, set `dirty_policy.collection_coverage.mode` to `all_eligible_when_feasible` unless source evidence supports intentionally concentrating errors. The planner then gives every collection with at least one eligible unprotected field a target before allocating remaining targets globally. When the target count is smaller than the number of eligible collections, it maximizes collection coverage without exceeding the selected rate and records the uncovered collections; never increase the rate merely to force full coverage.

If the result is zero for a small dataset, keep it at zero. Never exceed the 5% cap merely to force one dirty record.

### 6. Author dirty patches

Read only the targeted clean records named in `corruption-plan.json`. Write `dirty-patches.json` with one patch per target. Preserve every `patch_id`, `record_path`, `record_index`, and `error_type` from the plan.

Use the agent to author each replacement value and explanation. Make each corruption plausible for the inferred production process, detectable under the specification, and different from its clean value. Do not corrupt protected fields. See [artifact-contracts.md](references/artifact-contracts.md) for the patch schema.

Every change path must already exist in the targeted clean record and must be one of that target's eligible fields. The replacement value may differ freely when it remains serializable and realizes the assigned error. If an object or array value is replaced, its contained field names must remain unchanged. Do not create a new path, delete a path, rename a key, or encode error metadata into a field name. Put the error type and explanation only in `dirty-patches.json` and `dirty-manifest.json`.

### 7. Apply patches mechanically

Run:

```bash
python3 "$SKILL_DIR/scripts/apply_patches.py" \
  OUTPUT_DIR/synthetic-clean.EXT OUTPUT_DIR/dirty-patches.json \
  --plan OUTPUT_DIR/corruption-plan.json \
  --output OUTPUT_DIR/synthetic-dirty.EXT \
  --manifest OUTPUT_DIR/dirty-manifest.json
```

The script copies the clean dataset, applies exact agent-authored values, and records before/after evidence. It must reject any patch that uses a path outside the target's eligible fields or changes field names, while allowing dirty values themselves to change.

### 8. Validate and repair

For the required version 4 collection-aware specification, run:

```bash
python3 "$SKILL_DIR/scripts/validate_collections.py" \
  --source INPUT_FILE \
  --clean OUTPUT_DIR/synthetic-clean.EXT \
  --dirty OUTPUT_DIR/synthetic-dirty.EXT \
  --spec OUTPUT_DIR/generation-spec.json \
  --manifest OUTPUT_DIR/dirty-manifest.json \
  --output OUTPUT_DIR/validation-report.json
```

The legacy single-collection validator remains available only for older version 3 artifacts:

```bash
python3 "$SKILL_DIR/scripts/validate_dataset.py" \
  --source INPUT_FILE \
  --clean OUTPUT_DIR/synthetic-clean.EXT \
  --dirty OUTPUT_DIR/synthetic-dirty.EXT \
  --spec OUTPUT_DIR/generation-spec.json \
  --manifest OUTPUT_DIR/dirty-manifest.json \
  --output OUTPUT_DIR/validation-report.json
```

Require a passing report. Repair generated data or patches and rerun validation if any required check fails. Do not weaken the 5% cap, collection coverage, novelty thresholds, format checks, count checks, field-name checks, manifest checks, protected-field checks, declared source-model checks, or representation checks to obtain a pass. A field-value difference is expected in targeted dirty records and must not be mistaken for a field-name violation. Source-row and identifier overlaps remain separately reported, while changed-value and high-similarity metrics are mandatory for every generated collection. Prefer `match_source` for cardinality, sequence, and layout policies when source behavior is valid; override it only when a source defect must be repaired in the clean dataset or domain semantics require another class. The validator must reject class drift such as a source `non_monotonic` field becoming sequential or a source `interleaved` field becoming grouped.

After Python validation passes, write `semantic-audit.json`. Re-evaluate every hard constraint and every source-model dimension against the clean data. Confirm that dataset-level regime, field support, distributions, dependencies, group structure, sequence behavior, and physical representation remain source-consistent; only evaluate dimensions that exist in the input. Confirm that each dirty patch realizes its assigned contextual error and that untargeted records remain semantically clean. Cite record indices, field paths, and aggregate evidence. Mark the audit failed if a generation rule lacks source evidence, a clean record falls outside the inferred world without justification, or a patch is merely arbitrary noise. Repair and repeat until both validations pass.

## Required output

Return these artifacts:

- `generation-spec.json`
- `synthetic-clean.EXT`
- `corruption-plan.json`
- `dirty-patches.json`
- `synthetic-dirty.EXT`
- `dirty-manifest.json`
- `validation-report.json`
- `semantic-audit.json`

Summarize the inferred scenario, confidence, source-model dimensions, reuse/overlap policy, selected dirty-record rate and rationale, exact dirty-record count, error mix, validation result, and any recorded assumptions.
