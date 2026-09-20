# Semantic inference and clean generation

Use this reference while writing `generation-spec.json` and the synthetic clean dataset.

## Infer the dataset without user context

Build the scenario from observable evidence in this order:

1. File, workbook, sheet, table, and collection names.
2. Field names, abbreviations, units, and identifier prefixes.
3. Primitive types, formats, ranges, null patterns, and value cardinality.
4. Cross-field relations, temporal ordering, keys, and repeated entities.
5. Record ordering, grouping, aggregation level, and sampling cadence.
6. Nearby dictionaries, schemas, or metadata supplied with the input.

Do not treat a field name as conclusive evidence by itself. Reconcile multiple signals and record contradictory evidence.

## Classify the data-production context

Infer at least:

- domain;
- dataset role, such as reference catalog, operational transaction table, event log, time series, survey extract, experimental observations, or joined analytical table;
- logical record unit;
- likely producer, such as automated sensor, application service, analyst, form entry, or multi-source integration;
- likely curation level;
- whether records are independent, grouped, ordered, or relational.

Give the overall inference a confidence from `0.0` to `1.0`. Include concise evidence and assumptions. Low confidence does not block execution.

## Build a source model, not a list of field guesses

Treat the input as observations from a data-producing system. Model every level for which the source contains evidence:

1. **Dataset regime**: the domain, operational or historical horizon, curation level, population, and record granularity.
2. **Value support**: observed vocabularies, formats, units, ranges, missingness, and distribution shape.
3. **Relations**: functional dependencies, conditional categories, derived values, correlations, and valid combinations.
4. **Groups and repetition**: entity reuse, records per entity, duplicate behavior, and within-group variation.
5. **Sequences**: time windows, offsets, cadence, seasonality, monotonicity, event order, and other ordered processes.
6. **Representation**: identifier assignment and physical row layout.

This hierarchy is the general solution. Do not require all datasets to contain dates, categories, products, identifiers, or any other named field. Add a `generation.source_model.dimensions` entry only for a condition supported by the current input. Each entry identifies its scope and paths, summarizes whole-source evidence, classifies the condition as hard or soft, and declares how generated values will follow it.

Do not confuse an observed boundary with a universal domain law. For example, a recent date window may indicate a current operational snapshot, while another dataset may legitimately be historical or predictive. Infer the regime from combined evidence and keep generated values in that regime unless a recorded reason supports a shift.

## Model field semantics

For every generated field, record:

- path relative to a logical record;
- semantic meaning;
- physical and semantic type;
- unit or encoding when applicable;
- allowed values, range, or pattern;
- nullability;
- uniqueness or key role;
- dependencies on other fields;
- generation guidance;
- whether corruption is prohibited.

Express directly testable constraints with field properties such as `allowed_values`, `pattern`, `minimum`, `maximum`, and `unique`. Express simple cross-field comparisons in `generation.machine_rules`. Keep richer domain constraints in the human-readable hard and soft constraint lists for the agent semantic audit.

Separate hard constraints from soft tendencies. A hard constraint defines a valid clean record. A soft tendency improves realism but admits variation.

Examples of hard constraints include identifier syntax, valid timestamps, required foreign keys, nonnegative quantities, and chronological ordering. Examples of soft tendencies include skewed numeric distributions, common categories, seasonal effects, and correlations.

## Model representation separately from semantics

The same valid records can look unrealistic when values or physical rows are arranged differently from the source. Profile every leaf field mechanically, then retain representation rules for primary identifiers, grouping keys, ordinals, and any other field that provides meaningful ordering evidence. Infer and record four independent properties:

1. **Cardinality**: unique, repeated by relationship, or duplicated anomalously.
2. **Lexical shape**: prefix, width, alphabet, and whether numeric order carries domain meaning.
3. **Sequence policy**: monotonic/sequential, non-sequential, or opaque in physical row order.
4. **Record layout**: grouped, interleaved, explicitly sorted, or unordered/shuffled.

Use whole-column evidence. Compare unique ratios, duplicate occurrence counts, adjacent-equal ratios, lexical or numeric increase/decrease ratios, numeric-suffix order, and the ratio of adjacent values differing by exactly one. The inspection report classifies each field as `unique` or `repeated`, its sequence as sequential, monotonic, constant, non-monotonic, or not applicable, and repeated-value layout as grouped, mixed, or interleaved. A random-looking first-page sample is not enough, and neither is a field name or format alone.

Do not confuse legitimate key reuse with duplicate records. In a multi-record entity table, a record key may be unique while an entity key legitimately repeats. Preserve the latter equality relationship even when records are shuffled.

Use `match_source` as the normal validation policy for valid source behavior. Convert the observed representation into a direct generation instruction before authoring rows. A non-monotonic identifier is generated non-monotonically at its final position; an interleaved grouping key is assigned across its planned final positions; a sorted timestamp is generated in its observed direction. Never generate a convenient counter or grouped block while intending to shuffle or remap it later.

Override source-relative matching only when the observed source property is itself dirty or conflicts with a supported domain invariant. Record that decision in the specification—for example, a source primary key may contain accidental duplicates while the synthetic clean key remains unique. This prevents source dirtiness from being mistaken for a distribution to preserve.

Plan representation at whole-output scope. Determine sort-key precedence, tie-group behavior, repeated-value equality classes, and linked-key relationships before generating the first batch. Batch boundaries must not reset counters, produce locally sorted blocks, group repeated entities, or otherwise leak generation order. Keep a cross-batch ledger of final positions and equality relationships.

Do not randomize a field merely because its values are unique. When lexical or numeric order has domain meaning, such as a version number, timestamp, rank, or ordered sequence, generate it under that rule. When whole-column evidence instead shows opaque or non-monotonic behavior, create values directly with that behavior while still preserving uniqueness and relationships.

## Choose a source-conditioned generation strategy

For each source-model dimension, choose one or more of these strategies:

- `reuse_observed`: retain observed values when the source defines the legitimate vocabulary, reference entities, canonical text, or reusable facts;
- `sample_empirical`: sample values or records according to their observed frequency, including duplicates when present;
- `recombine_conditionally`: form new combinations only inside observed or inferred compatibility relationships;
- `bounded_extension`: introduce nearby values inside source-supported semantic and statistical boundaries;
- `generate_conditionally`: author a new open-ended value using the record context and other fields;
- `derive`: calculate the value from declared relations, offsets, formulas, or sequence rules.

The choice is evidence-dependent, not tied to a field name. A category may be closed in one dataset and open in another. A date may stay near the source window, shift with an explicitly inferred simulation horizon, or be derived from another date. A product field may reuse observed products, sample the same product classes, or introduce a nearby product only when the source supports an open vocabulary.

Source reuse is allowed at the value, vocabulary, relationship, identifier, and individual-row level when supported by the inferred process. It is not permission to copy most aligned values in most rows or to pass through an entire data-bearing collection. A generated collection must contain substantive new instantiations across its non-exempt fields. Exact or highly similar individual rows may remain, but their aggregate share is bounded by the collection's novelty contract. Output-internal uniqueness remains a separate field constraint.

Classify each field before generation as one of these general roles:

- **canonical or closed**: standards, fixed lookup codes, controlled labels, or immutable reference text may reuse observed values and may be excluded from novelty measurement with a written reason;
- **relational key**: may be reused only when preserving an observed entity/reference relationship is supported; otherwise generate new keys while reproducing source cardinality and layout;
- **open-ended entity or text**: generate contextually new values or conditionally recombine compatible components;
- **measurement or transaction value**: sample, derive, or extend within source-conditioned distributions and dependencies;
- **derived value**: recalculate from the newly generated parent values rather than copying the source result.

Measure novelty after clean generation. For each aligned source/clean collection, exclude only explicitly justified canonical paths, ignore cells that are missing in both versions, and compute:

1. the fraction of comparable values that changed;
2. the fraction of records whose unchanged-value similarity meets the declared high-similarity threshold;
3. exact aligned records and exact overlap with any source record;
4. per-field change ratios so one frequently changed field cannot conceal copied content elsewhere.

Version 4 requires at least 50% of non-exempt comparable values to change and caps high-similarity records at 50%. These are safety boundaries, not aspirational targets. Choose stronger collection-specific thresholds when the source supports them, and do not exempt a field merely to obtain a pass.

For a container with several logical collections, classify every collection. Use `generate` for ordinary data-bearing tables or arrays. Use `preserve_reference` only for authoritative closed lookup/standard content, and `preserve_documentation` only for explanatory material; both require source evidence. A selected primary collection does not authorize silent pass-through of the rest of the container.

Do not make realistic values fictional merely to advertise synthetic provenance. If provenance labeling is needed, place it in artifact metadata or an explicit field instead of distorting dates, ranges, categories, URLs, names, or identifiers.

For large outputs, generate complete records in batches and keep aggregate ledgers for modeled dimensions so batches do not drift. Python may sample, recombine, derive, and assemble values according to the declared source model. The agent chooses and audits the model; Python does not infer semantic meaning by itself.

## Handle ambiguity conservatively

When several scenarios fit:

- select the interpretation best supported by combined evidence;
- reduce semantic specificity instead of inventing unsupported facts;
- stay close to observed support when extension is uncertain;
- record alternatives and assumptions in the specification;
- avoid domain errors that depend on an uncertain interpretation;
- favor structural, completeness, consistency, and formatting corruptions that remain meaningful under all likely interpretations.
