# Live ingestion and rule support

Metadata fields exactly follow Annex B. Use a new doc_id for each version. `supersedes` contains a document ID or `doc_id#section` and must match the stored section ID (for example `7.2`). Scope lists use semicolons; batch scope supports a single year or `2023+`.

The MVP's restricted parser currently registers these phrases, case-insensitively:

```
Minimum attendance is 80%
Minimum CGPA is 7.0
Maximum active backlogs is 0
Minimum pass mark is 40
```

The values must be in allowed numeric ranges. The registry stores the matched wording and source section. Documents never execute instructions, define SQL, create tools or change identity.

## Critical limitation

An uploaded PDF saying "students must attend four fifths of classes" does not become an 80% rule with this parser. If it explicitly supersedes an existing numeric-rule document, ingestion rejects the unsupported amendment and publishes nothing. A table or exception also needs additional extraction/validation. This MVP is deliberately limited; arbitrary unseen policy updates are not solved. Before judging, extend extraction for the actual university's wording and test unknown updates. Do not present unsupported ingestion as authoritative calculator updates.

Add a validated extraction review path for broader clauses. Candidates need exact evidence spans, permitted parameters/operators, date/scope checks and an explicit unsupported-rule state. An LLM output alone is not proof that a rule was extracted correctly.

During a request, numeric rules are resolved over every matching registry entry, not just the top search hits. General procedural amendments are conservatively flagged for review; generalized clause-level conflict resolution is not implemented.

## Example metadata

```json
{
  "doc_id": "TEST-CIRC-02",
  "title": "Attendance update",
  "issuer": "Registrar",
  "authority_level": 2,
  "doc_type": "circular",
  "version": "2.0",
  "effective_from": "2026-10-01",
  "effective_to": "",
  "supersedes": "DEMO-CIRC#1",
  "scope_programmes": "ALL",
  "scope_batches": "ALL",
  "provenance": "Synthetic demo circular",
  "retrieved_on": "2026-10-10",
  "synthetic": "Y"
}
```
