# SpecForge Evaluation — February 23, 2026

## 1. What Is It About

SpecForge is a CLI tool (with optional Web UI) that takes a Markdown product specification as input and automatically generates a complete, tested, Docker-ready FastAPI microservice. It uses a multi-agent AI pipeline: Architect → Coder → Tester, orchestrated by LangGraph, with up to 4 self-correction iterations.

Write a Markdown requirements doc → get a fully working API with tests, Docker, and docs.

---

## 2. What Changed Since Last Evaluation (Feb 22)

The previous evaluation identified 13 issues. Here's what was addressed:

| Previous Issue | Status | Details |
|---|---|---|
| Hardcoded batch structure (🔴 High) | ✅ **Fixed** | `_build_dynamic_batches()` now derives file structure from SystemDesign — endpoint groups, auth detection, model descriptions all come from the design. No more URL-shortener-specific file names. |
| Global mutable state (🔴 High) | ✅ **Fixed** | `RunConfig` dataclass introduced. Each generation run can get its own config and provider. All agents prefer `run_config` from state, fall back to global. CLI still uses global convenience API (acceptable for single-threaded CLI use). |
| No dependency isolation (🟡 Medium) | ✅ **Fixed** | `_create_venv()` creates a `.venv` inside the generated project. `_install_dependencies()` and `_run_pytest()` use the venv's Python. User's environment stays clean. |
| Prompt/code coupling (🟡 Medium) | ✅ **Fixed** | `_build_batch_system_prompt()` reads dependencies from SystemDesign to determine ORM tips, auth library, password hashing. No more hardcoded "use SQLModel, use python-jose". |
| REPAIR_PROMPT unused (🟡 Low) | ✅ **Fixed** | REPAIR_PROMPT still exists in `prompts/coder.py` but is no longer imported anywhere. Dead *import* removed. The prompt template itself remains as a reference/template — minor. |
| pydantic-ai dependency (🟡 Low) | ✅ **Fixed** | Removed from `pyproject.toml`. |
| TestResult name collision (🟡 Low) | ✅ **Fixed** | Renamed to `TestRunResult` with `__test__ = False`. |
| No timeout config (🟡 Low) | ✅ **Fixed** | `SPECFORGE_PIP_TIMEOUT` and `SPECFORGE_PYTEST_TIMEOUT` env vars. |
| No generated project validation (🟡 Low) | ✅ **Fixed** | `_validate_project()` in tester + full 6-check `VerificationReport` system. |
| No streaming/incremental output | ⬜ Not addressed | Still spinner-based, no token streaming. |
| Error context truncation | ✅ **Improved** | `_deduplicate_errors()` collapses repeated errors with counts (×78), sends top-15 unique errors instead of raw truncated output. Smarter context selection. |
| Web UI security (env var leak) | ❌ **Not fixed** | `_run_generation()` still sets `os.environ["OPENAI_API_KEY"]` globally. |
| Web UI _jobs dict cleanup | ❌ **Not fixed** | In-memory dict with no TTL or cleanup. |

**Net: 9 of 13 issues fixed.** The two remaining unfixed issues are Web UI-specific.

---

## 3. Technical Evaluation

### ✅ What's Good

| Area | Details |
|---|---|
| **Dynamic batch generation** | The biggest improvement. `_build_dynamic_batches()` + `_extract_endpoint_groups()` + helper functions derive the entire file structure from SystemDesign. Endpoint groups are discovered by tag or path segment. Auth files only generated when auth endpoints exist. This makes SpecForge genuinely generic — any spec should work now. |
| **Verifier system** | New `verifier.py` (270+ lines) runs 6 post-generation checks: tests pass, app starts (subprocess smoke test), Docker builds, spec coverage (route matching with prefix resolution), test meaningfulness (heuristic: ≥1 test/endpoint), project structure. The spec coverage check is particularly thorough — it parses `include_router` prefixes from `main.py`, matches them against router files, and handles path parameter variations. |
| **Provider abstraction** | Clean `LlmProvider` Protocol with `ApiProvider` and `PiProvider`. `RunConfig` dataclass for thread-safe per-run config. Lazy provider initialization (`_ensure_started`). Pi RPC integration is creative — subprocess-based, no API key needed. |
| **Error deduplication** | `_deduplicate_errors()` is smart: collapses 78 identical bcrypt errors into `(×78) ValueError: password cannot be loaded`. Top-15 unique errors. Much better than raw truncation for feeding back to the Coder. |
| **Dependency conflict mitigation** | `_fix_known_dep_conflicts()` patches `requirements.txt` for the passlib/bcrypt≥4.1 incompatibility. The batch system prompt also warns about this. Pragmatic defense against a known real-world issue. |
| **Design condensation** | `_condense_system_design()` produces a ~2KB summary from potentially 70KB+ JSON. Full SystemDesign is not dumped into every batch prompt — only the relevant details per batch. Good token management. |
| **Venv isolation** | Generated projects get their own `.venv`. Pip installs and pytest both use it. User's Python environment stays untouched. Cross-platform (Windows/Unix python paths). |
| **LangGraph workflow** | Still clean and simple (~80 lines). Conditional edges handle errors and the retry loop. No over-engineering. |
| **Test suite** | 112 passing tests, 1 skipped. Covers parsing, models, dynamic batches, venv isolation, verifier checks, events, repair fixes, run config, web backend. Solid coverage. Previous eval had 51 tests — more than doubled. |
| **CLI UX** | Rich panels, spinners, colored tables, verification report table. New `verify` command lets you re-run checks on an already-generated project. |
| **~4,600 lines total** | Up from ~2,600 but the additions (verifier, dynamic batches, tests) are all substantive. No bloat. |

### ⚠️ What's Not So Good

| Area | Issue | Severity |
|---|---|---|
| **Web UI still uses globals for API keys** | `_run_generation()` sets `os.environ["OPENAI_API_KEY"] = api_key` — visible process-wide, persists after the call. Multiple concurrent WebSocket users would overwrite each other's keys. Should pass API key through `RunConfig` or thread-local storage. | 🔴 High |
| **Web UI doesn't use RunConfig** | Despite `RunConfig` being designed for thread-safe concurrency, `web/backend/main.py` still calls `set_model()` and `set_provider_type()` (global functions) instead of passing a `RunConfig` to `run_workflow()`. The fix infrastructure exists but isn't wired up in the Web UI. | 🔴 High |
| **Web UI event handlers are global** | `events.add_handler()` / `remove_handler()` use a global `_handlers` list. With concurrent WebSocket connections, all handlers receive all events — users see each other's progress. Events need scoping (e.g., by job ID or handler receives events only for its run). | 🟡 Medium |
| **REPAIR_PROMPT is dead code** | `specforge/prompts/coder.py` still contains `REPAIR_PROMPT` template. It's never imported or used. Repair logic is inline in `_generate_in_batches()`. Should be either used or removed. | 🟡 Low |
| **No streaming/incremental output** | Users see a spinner for potentially minutes per batch. No token-level streaming or progress indication during LLM generation. For 4 batches × 4 iterations, that's up to 16 long waits. | 🟡 Medium |
| **No cost tracking** | No token usage or cost reporting. A single run with GPT-4o across 4 iterations × 4 batches could cost several dollars. Users should see estimated cost. | 🟡 Medium |
| **Architect prompts still mention specific libraries** | `prompts/architect.py` SYSTEM_PROMPT says "List ALL Python packages needed (fastapi, uvicorn, sqlmodel, python-jose, passlib, etc.)". This biases the Architect toward these specific libraries even for specs where they're not appropriate. The Coder batch prompt was fixed to be generic, but the Architect prompt wasn't fully updated. | 🟡 Low |
| **README says "51 unit tests"** | README still says `tests/ # 51 unit tests` but there are now 112+ passing tests. Minor doc drift. | 🟡 Low |
| **Web UI _jobs dict has no cleanup** | In-memory store with no TTL. Long-running server accumulates all generated projects forever. Should have expiry or LRU eviction. | 🟡 Low |
| **Single example spec** | Only one built-in example (URL shortener). For a "generic factory" claim, having 2-3 diverse examples (e.g., todo app, chat API, inventory system) would validate generality and help users understand capabilities. | 🟡 Low |
| **No integration test for dynamic batches** | `test_dynamic_batches.py` tests the batch *structure* generation but doesn't test that a non-shortener spec actually produces a working project through the full pipeline. The generality claim is untested E2E. | 🟡 Medium |

### 🔍 Architectural Observations

1. **The biggest leap is generalization** — The move from hardcoded URL-shortener batches to dynamic `_build_dynamic_batches()` is the single most impactful change. It transforms SpecForge from "a URL shortener generator" to "a microservice generator". The endpoint grouping, auth detection, and model description helpers are well-designed.

2. **Verifier is a real quality gate** — The 6-check verification system (especially spec coverage with prefix resolution and app smoke test) catches issues that just "pytest passes" wouldn't. It's the kind of thing that turns a prototype into a useful tool.

3. **RunConfig is the right abstraction, but incomplete adoption** — The `RunConfig` dataclass with lazy provider creation is exactly right for thread-safe concurrent use. But the Web UI — the only concurrent user — doesn't use it. The CLI doesn't need it (single-threaded). So the infrastructure is built but the actual consumer isn't wired up.

4. **The Coder is doing the heavy lifting** — `coder.py` at 470+ lines is the largest and most complex module. It handles batch generation, dynamic prompts, error deduplication, dependency conflict patching, JSON parsing with 3 fallback strategies, and retry logic. It might benefit from being split into smaller modules (e.g., `coder/batches.py`, `coder/parser.py`, `coder/fixups.py`).

5. **Good engineering judgment persists** — Subprocess for pytest, venv isolation, condensed system design for token management, deduplicated errors, known-conflict patching — these are all pragmatic choices that show understanding of real-world failure modes.

6. **The Web UI is the weakest part** — It works as a demo but has the most unresolved issues (global state, no event scoping, no job cleanup, API key leaking). It was presumably added as a nice-to-have and shows less polish than the core CLI pipeline.

---

## 4. Summary

| Aspect | Rating | Change |
|---|---|---|
| Code quality & readability | ⭐⭐⭐⭐ | Same |
| Architecture & separation of concerns | ⭐⭐⭐⭐ | Same |
| Generality (works for any spec) | ⭐⭐⭐⭐ | ⬆️ from ⭐⭐ |
| Production readiness | ⭐⭐½ | ⬆️ from ⭐⭐ |
| Innovation / creative value | ⭐⭐⭐⭐ | Same |
| Test coverage | ⭐⭐⭐⭐ | ⬆️ from ⭐⭐⭐ |
| Web UI quality | ⭐⭐ | New category |

**Bottom line:** Significant improvement over the previous evaluation. The core issues (hardcoded batches, global state, no venv isolation, prompt coupling) have been addressed. SpecForge is now genuinely a *generic* microservice generator, not just a URL shortener generator. The verifier adds real quality assurance. Test count more than doubled. The remaining issues are concentrated in the Web UI (which isn't the primary interface) and polish items. The highest-impact next steps would be: (1) wire RunConfig into the Web UI, (2) add 1-2 more example specs and E2E test them, (3) add cost/token tracking.
