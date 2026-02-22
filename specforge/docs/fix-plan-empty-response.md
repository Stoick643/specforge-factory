# Fix Plan: Empty Responses + Repair Loop Failures

Based on the bookmark-manager E2E test (27 endpoints, 5 DB models, 34 generated files).

## Problems Found

### 1. ALL 78 test errors are ONE bug
`passlib 1.7.4` + `bcrypt 5.0.0` = incompatible (`bcrypt.__about__` removed in v5).
Every test that creates a user hits `ValueError: password cannot be loaded`.
19 tests pass because they only test validation (no password hashing).

### 2. Empty responses from Pi on repair iterations
Iterations 2-4 all fail with "Empty response from LLM" on the very first batch.
Root cause: the combined repair prompt is too large:
- System design JSON: ~5-15KB
- Error context (pytest output): 2,000 chars (capped)
- LLM feedback from `_analyze_failures()`: **unbounded** — could be 5-20KB for 78 errors
- Previously generated files: up to 8,000 chars
- Total: potentially 30-50KB per batch prompt

Pi/Claude either returns empty or times out on prompts this large.

### 3. Verification report not shown on final iteration
Verification should run on iteration 4 (the last). Either:
- A silent exception in the verifier is caught by the tester's broad `except Exception`
- Or `_analyze_failures` Pi call blocks/fails first, disrupting the flow

## Fixes

### Fix A: Known dependency conflicts (prevent the bcrypt issue)
Add common dependency version constraints to the batch system prompt as hints:
- `bcrypt<4.1` when passlib is used (or suggest `passlib[bcrypt]` with pinned bcrypt)
- This is a well-known issue the LLM should know about, but adding it to the prompt makes it reliable

**Also**: add a post-generation fixup step that scans `requirements.txt` for known bad combos and patches them automatically.

**Files:** `specforge/agents/coder.py` (batch system prompt), new `specforge/agents/dep_fixer.py`

### Fix B: Cap and deduplicate error feedback
1. Truncate `_analyze_failures()` output to 2,000 chars (same as pytest output)
2. Before sending pytest output to the LLM, deduplicate errors — extract unique error messages only. 78 identical `ValueError: password cannot be loaded` → 1 line with count
3. Cap total error_context to 4,000 chars (pytest + feedback combined)

**Files:** `specforge/agents/tester.py`, `specforge/agents/coder.py`

### Fix C: Condense SystemDesign on repair iterations
On iterations 2+, don't send the full SystemDesign JSON. Send a condensed version:
- Project name + description
- List of endpoint paths (one line each)
- List of model names + field names (one line each)
- List of dependencies
- Skip the full field descriptions, schemas, env vars, docker config

This could shrink the system design from 15KB to 2KB.

**Files:** `specforge/agents/coder.py` (new `_condense_system_design()` function)

### Fix D: Wrap verification in defensive try/except
The verification block in `tester_node` should never crash silently:
```python
try:
    verification_report = run_verification(...)
    print_verification_report(verification_report)
except Exception as e:
    console.print(f"[warning]Verification failed: {e}[/warning]")
```

**Files:** `specforge/agents/tester.py`

### Fix E: Log prompt sizes
Add debug output showing the character count of each prompt sent to the LLM:
```
    Generating core files... (prompt: 12,345 chars)
```
This helps diagnose future empty response issues.

**Files:** `specforge/agents/coder.py`

## New Tests

- `test_deduplicate_errors()` — 78 identical errors → 1 unique + count
- `test_condense_system_design()` — full design → condensed version is <3KB
- `test_feedback_truncation()` — LLM feedback gets capped at 2000 chars
- `test_known_dep_conflicts()` — passlib+bcrypt detected and fixed
- `test_verification_crash_handled()` — verifier exception doesn't crash tester

## Execution Order

| Step | Fix | Effort |
|------|-----|--------|
| 1 | **Fix B** Cap + deduplicate error feedback | Small |
| 2 | **Fix C** Condense SystemDesign on repair | Medium |
| 3 | **Fix D** Defensive verification try/except | Small |
| 4 | **Fix E** Log prompt sizes | Small |
| 5 | **Fix A** Known dependency conflicts | Medium |
| 6 | Run full test suite | — |
| 7 | Re-test bookmark-mng E2E | — |

## Evaluation Criteria

### Level 1: Unit tests pass (minimum bar)
All existing 106 tests + new tests for this fix pass.
Proves the internal functions (dedup, condense, truncation) work correctly.
Does NOT prove the LLM integration works — only a real E2E run does.

### Level 2: Bookmark-mng E2E test (the real proof)
Re-run the exact command that failed:
```bash
python -m specforge generate specforge/examples/bookmark-mng.md --output ./bookmark-mng --provider pi --clean
```

| Check | Before (broken) | Target (fixed) |
|-------|-----------------|----------------|
| Coder iteration 2+ produces files | ❌ Empty response, 3 retries, fail | ✅ Actually generates files |
| bcrypt/passlib error gone | ❌ 78 errors all same cause | ✅ No password hashing errors |
| Verification report shows | ❌ Not printed at all | ✅ 6-check table printed on final iteration |
| Prompt sizes logged | ❌ No visibility | ✅ Char count shown per batch |

### Level 3: Test pass rate improves
- Before: 19/98 passed (19%)
- Target: majority pass on iteration 1, or self-correction fixes remaining on iteration 2
- Stretch goal: all tests pass within 4 iterations

### What we CAN'T verify without running E2E
Fixes B + C reduce prompt size, but only a real Pi call proves it stops returning empty.
Unit tests verify the logic (truncation, dedup, condensing) but not the LLM behavior.
