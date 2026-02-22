# SpecForge Improvement Plan

Based on evaluation from `evaluation-02.22.md`. Goal: turn SpecForge from a URL-shortener-specific demo into a truly generic microservice factory.

---

## P0-A: Make Coder's batch generation dynamic ⭐ HIGHEST IMPACT

**Problem:** `_generate_in_batches()` in `coder.py` has 4 hardcoded batches with URL-shortener-specific filenames (`links.py`, `admin.py`, `auth.py`). Any non-URL-shortener spec produces garbage.

**Fix:** Build batches dynamically from `SystemDesign`:

### Batch 1 — Core (always present, content derived from SystemDesign)
- `app/__init__.py`
- `app/config.py` — derived from `SystemDesign.env_variables`
- `app/database.py` — async engine setup
- `app/models.py` — derived from `SystemDesign.database_models` (list actual model names, fields)
- `app/schemas.py` — derived from `SystemDesign.endpoints` (request/response schemas)
- `app/dependencies.py` — shared deps (get_db, etc.)

### Batch 2 — Routers + Main (derived from endpoints)
- `app/main.py` — always present
- `app/routers/__init__.py` — always present
- `app/routers/{group}.py` — one per endpoint group. Group endpoints by tag or path prefix (e.g., `/users/*` → `users.py`, `/products/*` → `products.py`)
- `app/auth.py` — only if any endpoint has `auth_required=True`

### Batch 3 — Tests (mirrors routers)
- `tests/__init__.py`
- `tests/conftest.py` — fixtures
- `tests/test_health.py` — always present
- `tests/test_{group}.py` — one per router from batch 2

### Batch 4 — Infra (always the same)
- `requirements.txt` — derived from `SystemDesign.dependencies`
- `Dockerfile` — derived from `SystemDesign.docker`
- `docker-compose.yml` — derived from `SystemDesign.docker`
- `.env.example` — derived from `SystemDesign.env_variables`
- `README.md`

### Implementation steps:
1. Write `_build_dynamic_batches(system_design: dict) -> list[dict]` function
2. Extract endpoint groups: group `SystemDesign.endpoints` by tag or first path segment
3. Generate batch instructions that reference actual model names, endpoint paths, field names
4. Replace hardcoded `batches` list in `_generate_in_batches()` with call to `_build_dynamic_batches()`
5. Update tests for the new batch structure

### New tests:
- `test_build_dynamic_batches_todo_app()` — SystemDesign with `/tasks/*` endpoints → generates `routers/tasks.py`, `test_tasks.py`
- `test_build_dynamic_batches_multi_router()` — SystemDesign with `/users/*` + `/products/*` + `/orders/*` → three routers, three test files
- `test_build_dynamic_batches_with_auth()` — endpoints with `auth_required=True` → includes `app/auth.py`
- `test_build_dynamic_batches_no_auth()` — no auth endpoints → no `app/auth.py`
- `test_build_dynamic_batches_always_has_health()` — always includes `test_health.py` regardless of spec

**Files changed:** `specforge/agents/coder.py`, `tests/test_dynamic_batches.py` (new)

---

## P0-B: Remove hardcoded tech choices from prompts

**Problem:** The `batch_system` prompt in `coder.py` and `SYSTEM_PROMPT` in `prompts/coder.py` hardcode "SQLModel", "python-jose", "passlib", "async patterns". The Architect already picks appropriate libraries in `SystemDesign.dependencies` — these hardcoded choices override/conflict with that.

**Fix:**
1. Make `batch_system` prompt reference `SystemDesign.dependencies` for library choices
2. Make `SYSTEM_PROMPT` in `prompts/coder.py` generic — describe patterns (ORM, auth, async) but let the specific libraries come from SystemDesign
3. Keep SQLModel-specific tips (like the `foreign_key` vs `sa_column` rule) only when SQLModel is in the dependency list

### New tests:
- `test_batch_system_prompt_includes_dependencies()` — verify system prompt mentions libraries from SystemDesign.dependencies, not hardcoded ones
- `test_batch_system_prompt_sqlmodel_tips_conditional()` — SQLModel tips only present when `sqlmodel` is in dependencies

**Files changed:** `specforge/agents/coder.py`, `specforge/prompts/coder.py`, `tests/test_dynamic_batches.py`

---

## P2-A: Quick cleanups

Small fixes that can be done in minutes:

1. **Remove unused `REPAIR_PROMPT` import** — `coder.py` imports it but never uses it
2. **Remove `pydantic-ai` dependency** — listed in `pyproject.toml` but never imported
3. **Fix `TestResult` name collision** — pytest tries to collect it as a test class. Either rename to `TestRunResult` or add `__test__ = False`
4. **Add generated project validation** — after generation, check that essential files exist (`app/main.py`, `requirements.txt` with `fastapi`). Warn if missing.

### New tests:
- Update all existing tests referencing `TestResult` → `TestRunResult`
- `test_project_validation_missing_main()` — validation warns when `app/main.py` missing
- `test_project_validation_missing_fastapi()` — validation warns when `requirements.txt` lacks `fastapi`
- `test_project_validation_pass()` — validation passes for a complete project

**Files changed:** `specforge/agents/coder.py`, `specforge/models.py`, `pyproject.toml`, `specforge/agents/tester.py`, `tests/test_project_validation.py` (new), update existing tests

---

## P1-A: Fix global mutable state

**Problem:** `_current_provider`, `_provider_type`, `_current_model` are module-level globals in `providers/__init__.py` and `config.py`. Not thread-safe — Web UI runs generations in threads, so concurrent requests stomp on each other's config.

**Fix:**
1. Create a `RunConfig` dataclass holding provider instance, model name, provider type
2. Pass `RunConfig` through `AgentState` (add a `config` key)
3. Each agent reads provider from `state["config"]` instead of calling `get_provider()`
4. Keep `get_provider()` as a convenience for CLI (single-threaded) but have it delegate to `RunConfig`
5. Web UI creates a fresh `RunConfig` per request

### New tests:
- `test_run_config_isolation()` — two RunConfig instances don't interfere with each other
- `test_run_config_creates_correct_provider()` — `api` → ApiProvider, `pi` → PiProvider

**Files changed:** `specforge/providers/__init__.py`, `specforge/config.py`, `specforge/agents/architect.py`, `specforge/agents/coder.py`, `specforge/agents/tester.py`, `specforge/workflow.py`, `specforge/cli.py`, `web/backend/main.py`, `tests/test_config.py` (updated)

---

## P1-B: Dependency isolation (venv)

**Problem:** `_install_dependencies()` runs `pip install -r requirements.txt` into the user's Python environment. Pollutes their env and can cause conflicts.

**Fix:**
1. Create a temporary venv inside the output directory (`{output_dir}/.venv`)
2. Install dependencies into that venv
3. Run pytest using the venv's Python (`{output_dir}/.venv/bin/python -m pytest`)
4. Optionally clean up venv after tests pass (or leave it for the user)

### New tests:
- `test_install_dependencies_creates_venv()` — verify venv is created in output dir (mocked subprocess)
- `test_pytest_runs_in_venv()` — verify pytest uses venv's Python, not system Python (mocked subprocess)

**Files changed:** `specforge/agents/tester.py`, `tests/test_tester_parse.py` (updated)

---

## P2-B: Configurable timeouts

**Problem:** Multiple hardcoded timeouts — Pi RPC (300s), pytest (120s), pip install (300s). None configurable.

**Fix:** Add optional CLI flags or env vars:
- `--pytest-timeout` (default 120s)
- `--pip-timeout` (default 300s)
- `SPECFORGE_PI_TIMEOUT` env var (default 300s)

Pass through `AgentState` or `RunConfig`.

**Files changed:** `specforge/cli.py`, `specforge/agents/tester.py`, `specforge/providers/pi_rpc.py`

---

## P3: Nice-to-haves (if time permits)

- **Token/cost tracking** — count tokens per agent call, estimate cost, show summary at end
- **Streaming progress** — show token-by-token output during LLM calls instead of just a spinner
- **Web UI security** — scope API keys per request instead of setting env vars; clean up `_jobs` dict
- **Smarter error context** — instead of truncating to 4000 chars, select the most relevant error lines

---

## Execution Order

| Step | Item | Effort | Impact | Status |
|------|------|--------|--------|--------|
| 1 | **P0-A** Dynamic batch generation | Large | 🔴 Critical | ✅ Done |
| 2 | **P0-B** Generic prompts | Medium | 🔴 Critical | ✅ Done |
| 3 | **P2-A** Quick cleanups | Small | 🟢 Easy wins | ✅ Done |
| 4 | **P1-A** Fix global state | Medium | 🟡 Important for Web UI | ✅ Done |
| 5 | **P1-B** Venv isolation | Medium | 🟡 Important for safety | ✅ Done |
| 6 | **P2-B** Configurable timeouts | Small | 🟢 Nice to have | ✅ Done |
| 7 | **P3** Nice-to-haves | Variable | ⚪ Optional | — |
