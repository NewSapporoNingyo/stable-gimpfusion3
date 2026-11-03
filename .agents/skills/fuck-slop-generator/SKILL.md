---
name: fuck-slop-generator
description: Audit and repair evidence-backed maintainability, correctness, safety, and performance slop without changing intended behavior. Use for sustainability passes covering duplicated logic, dead state, avoidable complexity, undefined behavior, unsafe bounds or ownership, repeated work, incomplete cache keys, confusing flow, or hidden crash/hang risks.
---

# Slop Fixer

## Audit before editing

1. Read `AGENTS.md`, current source, affected tests, and the relevant records in `doc/`.
2. Establish the requested scope and a clean baseline. Record existing `ruff`, `mypy`, or unittest failures before attributing them to new work.
3. Inspect read-only first and create an evidence ledger with:
   - candidate problem;
   - concrete code evidence;
   - user-visible or maintenance risk;
   - smallest safe repair;
   - validation that can disprove or confirm the repair.
4. Drop candidates that are speculative, intentional, generated, third-party, or merely stylistic.

## Review categories

- Equivalent production logic scattered across modules.
- Unused fields, helpers, state, or branches.
- Code that can be simplified without compressing lines or deleting useful comments.
- Undefined behavior, integer bounds, resource lifetime, or exception-boundary risks.
- Repeated image encode or decode, file I/O, JSON config reads, HTTP requests, thumbnail builds, or GTK widget rebuilds.
- Cache keys that omit visible inputs or invalidation with no clear owner.
- Thread or GTK main-loop paths that can exhaust resources, deadlock, or leave inconsistent state.
- Logic whose names or structure conceal the real invariant.
- Overdesigns, over-engineering, excessive safety measures and redundant design. Such as “significantly increasing code complexity for a boundary case that occurs only one in a thousand times.”
- Module boundaries are unclear; for example, “a function that sends a generation request is located in a GTK dialog module instead of `ApiClient` in `sg_structures.py`.”
- Fragmentation that forces one responsibility to be understood or changed across unrelated owners. File count alone is not evidence: the current split between the entry script, `sg_plugins/`, and `sg_structures.py` is intentional, and each module should retain the responsibility listed in `AGENTS.md`.
- The same set of operational logic uses inconsistent implementations; for example, “settings saving uses two different paths: one saves through `MyShelf` and another writes `stable_gimpfusion.json` directly.”

## Repair conservatively

1. Verify every finding against the current tree immediately before editing.
2. Do not add many patches directly to problematic code, as this leads to an accumulation of patch code, increased complexity, and reduced code readability. Instead, use a correct and efficient implementation to directly replace the problematic section.
3. Preserve GTK interaction, PDB procedure signatures, JSON config format, generation results written back as layers, and translated UI text.
4. Never claim improvement from deleted comments, combined lines, renamed whitespace, or moved code alone.
5. Count self-owned production code before and after. Exclude tests, `doc/`, `locale/`, and `.venv`. Explain any increase with measured correctness or performance value.
6. Keep behavior-changing proposals out of a slop-fix pass unless the user separately approves them.
7. Do not abandon a fix for a particular section simply because “the issue discovered is too severe.”

## Validate rigorously

1. Run `ruff check` on every modified file and `mypy` on files whose types changed.
2. Run the affected `unittest` modules in `test/`.
3. Use a real generation route against Forge for API or image conversion risk, and check the written layer against the source image.
4. Measure performance before and after on the same machine, image, prompt, generation parameters, model, and measurement kind; report median and p95. Use the affected generation or layer import path for the work under measurement.
5. Treat an unmet strict budget as unmet. Do not lower thresholds or repeat selectively to manufacture a pass.
6. If no problem is proven and no code changes, do not run unnecessary tests merely to create activity.

## Report honestly

List proven findings and fixes, rejected or deferred candidates, production-code counts, validation evidence, existing failures, and remaining manual checks. A successful slop-fix may legitimately make no code change.
