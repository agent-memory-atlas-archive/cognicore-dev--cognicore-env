# Cross-language canonical-JSON float rejection fixtures

These fixtures are shared across the **Python**, **Rust**, and **TypeScript**
implementations of the CogniCore ↔ mem0 transfer bundle format. Each file is a
JSON document that the float-rejection rule must reject (or, for
`clean_int.json`, must accept).

The rejection contract is **symmetric**: every runtime that signs bundle
payloads must refuse to canonicalize any document containing a `float` value
at any depth. The reason is that the byte-level representation of a float
differs across runtimes:

- Python's `json.dumps(1.0)` → `"1.0"`
- ECMAScript's `JSON.stringify(1.0)` → `"1"`
- Rust's `serde_json::to_string(&1.0_f64)` → `"1.0"`

If a runtime allowed floats through, the same logical payload would produce
**different Ed25519 signatures** in each runtime, defeating the
"deterministic signature" contract that the bundle format depends on.

## Fixtures

| File | Expected behavior | Why |
| --- | --- | --- |
| `integral_float.json` | **reject** | The motivating bug: `1.0` (Python) vs `1` (JS). |
| `confidence_field.json` | **reject** | A typical ML confidence score; the obvious case. |
| `nested_float.json` | **reject** | Float buried in nested dicts — guards against shallow walkers. |
| `list_of_floats.json` | **reject** | Float inside a list element — guards against dict-only walkers. |
| `clean_int.json` | **accept** | Negative case — must NOT trigger the rule (guards against over-eager rejection). |

## Mirror tests

Each consuming runtime ships a mirror test that loads these fixtures and
asserts the same expected behavior. The fixtures themselves must never be
modified without a coordinated bump across all three runtimes.

- Python: `tests/test_mem0_canonical_float_reject.py::TestCrossLanguageFixtures`
- Rust: `alethech-rs/tests/canonical_float_reject.rs` (pending)
- TypeScript: `alethech-ts/test/canonical_float_reject.test.ts` (pending)

## Origin

The rule and the fixtures were introduced in PR followup to
[cognicore-dev/cognicore-env#135](https://github.com/cognicore-dev/cognicore-env/issues/135),
item 3 (option 2 — exclusion, not normalization).

The choice of *exclusion over normalization* is deliberate: no JSON
canonicalization spec (RFC 8785 JCS, OLPC Canonical JSON) agrees on a
canonical float representation across runtimes, and silent normalization
is exactly the failure mode that defeated the reachability firing vector
in PR #136.
