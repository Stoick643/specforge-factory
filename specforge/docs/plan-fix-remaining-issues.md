# Plan: Fix Remaining Evaluation Issues

Based on evaluation-02.23.md, 4 issues remain (2 high, 1 low, 1 low).
Plus a few quick cleanups.

---

## Issues to Fix

### F1: Web UI uses globals for API keys (🔴 High)

**Problem:** `_run_generation()` in `web/backend/main.py` sets `os.environ["OPENAI_API_KEY"]` globally. Multiple concurrent WebSocket users would overwrite each other's keys.

**Fix:** Create a `RunConfig` per WebSocket connection with the API key, pass it into `run_workflow()` via `AgentState["run_config"]`. Remove all `os.environ` key setting. The `RunConfig` already supports this — it holds a provider instance which gets the key at construction time.

**Files:** `web/backend/main.py`, possibly `specforge/providers/__init__.py` (ensure `ApiProvider` accepts key at init)

**Test:** Unit test that two concurrent `_run_generation` calls with different keys don't interfere.

---

### F2: Web UI doesn't use RunConfig (🔴 High)

**Problem:** Web UI calls `set_model()` and `set_provider_type()` (global functions) instead of using `RunConfig`. This is the same root cause as F1.

**Fix:** Replace `set_model()` / `set_provider_type()` / `os.environ` calls with a single `RunConfig(provider_type=..., model=..., api_key=...)` passed to `run_workflow()`. The workflow already reads `state.get("run_config")`.

**Files:** `web/backend/main.py`

**Test:** Same as F1 — covered together.

**Note:** F1 and F2 are really one fix. Create `RunConfig` → pass to workflow → done.

---

### F3: Web UI event handlers are global (🟡 Medium)

**Problem:** `events.add_handler()` uses a global `_handlers` list. With concurrent WebSocket connections, all handlers receive all events — users see each other's progress.

**Fix:** Add a `run_id` field to `ProgressEvent`. Each `emit()` call includes the run_id. Handlers can filter by run_id. The WebSocket handler only forwards events matching its job's run_id.

**Files:** `specforge/events.py`, `web/backend/main.py`, agents that call `events.emit()`

**Test:** Unit test that two handlers with different run_ids only receive their own events.

**Alternative (simpler):** Instead of changing the event system, pass a per-run callback directly through `RunConfig`. Agents call `run_config.on_progress(event)` instead of `events.emit()`. Web UI sets the callback to the WebSocket sender. CLI sets it to Rich console printer. No global handlers needed.

**Decision:** Go with the simpler alternative — add `on_progress: Callable | None` to `RunConfig`. Less invasive, cleaner.

---

### F4: REPAIR_PROMPT is dead code (🟡 Low)

**Problem:** `specforge/prompts/coder.py` contains `REPAIR_PROMPT` template that's never imported or used.

**Fix:** Delete it.

**Files:** `specforge/prompts/coder.py`

**Test:** Existing tests still pass (nothing references it).

---

### F5: Architect prompt biases toward specific libraries (🟡 Low)

**Problem:** `prompts/architect.py` SYSTEM_PROMPT says:
> "List ALL Python packages needed (fastapi, uvicorn, sqlmodel, python-jose, passlib, etc.)"

This biases the Architect toward SQLModel + python-jose + passlib even for specs where they don't apply (e.g., a spec with no auth, or one that should use plain SQLAlchemy).

**Fix:** Change to generic guidance:
> "List ALL Python packages needed. Always include fastapi and uvicorn. Add database, auth, and other libraries as appropriate for the spec."

Also remove the hardcoded "duplicate slugs, expired links" edge case mention — that's URL-shortener-specific.

**Files:** `specforge/prompts/architect.py`

**Test:** No code behavior change — prompt quality improvement.

---

### F6: README says "51 unit tests" (🟡 Low)

**Problem:** README.md still says `tests/ # 51 unit tests` but there are 122+ passing tests.

**Fix:** Update the count.

**Files:** `README.md`

**Test:** N/A.

---

### F7: Web UI _jobs dict has no cleanup (🟡 Low)

**Problem:** In-memory `_jobs` dict accumulates forever.

**Fix:** Add a `max_jobs` limit (e.g., 100). When exceeded, drop the oldest. Or add a timestamp and TTL (1 hour). Simple approach: use `OrderedDict` and pop oldest when over limit.

**Files:** `web/backend/main.py`

**Test:** Unit test that old jobs get evicted.

---

## Execution Order

| Step | Issue | Effort | Dependencies |
|------|-------|--------|-------------|
| 1 | F4: Delete REPAIR_PROMPT | 1 min | None |
| 2 | F5: Generic architect prompt | 5 min | None |
| 3 | F6: Update README test count | 1 min | None |
| 4 | F1+F2: RunConfig in Web UI | 20 min | None |
| 5 | F3: Per-run event scoping | 15 min | F1+F2 |
| 6 | F7: Jobs dict cleanup | 10 min | None |
| 7 | Tests + commit | 10 min | All above |

**Total estimate:** ~1 hour

## Evaluation Criteria

After all fixes:
- [ ] `python -m pytest tests/` — all pass
- [ ] No `os.environ` key-setting in `web/backend/main.py`
- [ ] No `set_model()` / `set_provider_type()` calls in `web/backend/main.py`
- [ ] `REPAIR_PROMPT` gone from codebase
- [ ] Architect prompt has no URL-shortener-specific language
- [ ] README test count matches actual
- [ ] `_jobs` dict has size limit
- [ ] Events are scoped per-run (or per-run callback via RunConfig)
- [ ] `specforge generate` CLI still works (no regression)
