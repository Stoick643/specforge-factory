You are an expert AI software engineer. Build "SpecForge" -- a Spec-Driven Multi-Agent Microservice Factory (CLI version) exactly as described.

Project goal: CLI tool that takes a Markdown product spec and generates a complete, tested, Docker-ready FastAPI microservice using a self-correcting 3-agent loop (Architect -> Coder -> Tester, max 4 iterations).

CLI example:
specforge generate advanced-shortener-sqlite.md --output ./my-shortener

## Architecture Overview

Three agents connected via LangGraph stateful workflow:

```
Architect --> Coder --> Tester
                ^         |
                |  fails  |
                +---------+
              (max 4 iterations)
```

- **Architect Agent**: Reads Markdown spec -> outputs structured `SystemDesign`
- **Coder Agent**: Takes `SystemDesign` (+ error feedback) -> generates all project files as `{filepath: content}`
- **Tester Agent**: Writes files to disk, runs `pytest` subprocess, parses results, produces feedback on failure

## LLM Providers

SpecForge supports two provider modes:

### API Provider (default)
Direct LLM API calls via langchain. Requires an API key.
```bash
specforge generate spec.md --model gpt-4o
specforge generate spec.md --model claude-sonnet-4-20250514
specforge generate spec.md --model kimi-k2.5
```

Supported: OpenAI, Anthropic, Moonshot/Kimi, DeepSeek, OpenRouter (org/model format).

### Pi Provider (no API key needed!)
Uses Pi's RPC mode as a subprocess. Leverages the user's existing Claude access (e.g. Max plan).
```bash
specforge generate spec.md --provider pi
```

Architecture:
```
specforge --> PiRpcClient --> subprocess(pi --mode rpc --no-session) --> Claude via user's auth
```

- Spawns `pi --mode rpc --no-session` as a subprocess
- Sends prompts via JSON stdin, reads responses via JSON stdout
- One Pi process per run (start once, reuse for all agent calls, stop at end)
- Always uses manual JSON parse (no structured output through RPC)
- Pi provider ignores `--model` flag (uses whatever model Pi is configured with)

## Provider Abstraction

All agents use `LlmProvider` protocol instead of calling langchain directly:

```python
class LlmProvider(Protocol):
    def invoke(self, system_prompt: str, user_prompt: str) -> str: ...
```

- `ApiProvider` -- wraps langchain ChatOpenAI/ChatAnthropic (needs API key)
- `PiProvider` -- wraps PiRpcClient subprocess (no API key needed)

Factory: `get_provider(provider_name, model) -> LlmProvider`

## Build Plan

### Phase 1: Project Setup (DONE)
- Package structure: `specforge/` with all subdirectories
- `pyproject.toml` with dependencies
- `.env.example` for API keys
- Built-in example spec: `specforge/examples/advanced-shortener-sqlite.md`

### Phase 2: Pydantic Models (DONE)
- `specforge/models.py` -- SystemDesign, Endpoint, DatabaseModel, EnvVariable, DockerConfig, etc.
- AgentState (TypedDict for LangGraph)
- TestResult

### Phase 3: Agents (DONE)
- `specforge/prompts/` -- prompt templates for all 3 agents
- `specforge/agents/architect.py` -- spec -> SystemDesign (structured output + manual parse fallback)
- `specforge/agents/coder.py` -- SystemDesign -> project files (batch generation for large projects)
- `specforge/agents/tester.py` -- runs pytest, parses results, LLM failure analysis

### Phase 4: LangGraph Workflow (DONE)
- `specforge/workflow.py` -- architect -> coder -> tester -> (loop or done)
- Conditional edges: error handling after architect, self-correction loop after tester

### Phase 5: CLI (DONE)
- `specforge/cli.py` -- Typer CLI with generate and example commands
- `--model` flag for model selection
- `--provider` flag: `api` (default) or `pi`
- Rich console output, API key validation

### Phase 6: Config & Providers (DONE for API, IN PROGRESS for Pi)
- `specforge/config.py` -- model detection, API key validation, get_llm()
- Multi-provider support: OpenAI, Anthropic, Moonshot, DeepSeek, OpenRouter

### Phase 7: Pi RPC Provider (DONE)
- `specforge/providers/__init__.py` -- LlmProvider protocol, ApiProvider, PiProvider, RunConfig, factory
- `specforge/providers/pi_rpc.py` -- PiRpcClient (subprocess management, JSON protocol)
- Update agents to use LlmProvider instead of get_llm() directly
- Update CLI with --provider flag
- Auto-detect Pi installation path (Windows/Mac/Linux)
- Error handling: Pi not installed, process crash, timeout

### Phase 8: Integration & Testing (DONE)
- Unit tests for SpecForge (86 passing, 1 skipped)
- E2E test with API provider (Kimi: 22/31 tests passed on iteration 1, self-correction working)
- E2E test with Pi provider
- Fix any issues found

### Phase 9: Polish (DONE)
- README.md with install, usage, both provider examples
- Clean error messages and Rich formatting

### Phase 10: Generalization Improvements (DONE)
- Dynamic batch generation from SystemDesign (no more hardcoded file names)
- Generic prompts (library choices come from SystemDesign.dependencies)
- RunConfig for thread-safe provider access (Web UI concurrency)
- Venv isolation for generated project dependencies
- Project validation after generation
- Configurable timeouts (SPECFORGE_PIP_TIMEOUT, SPECFORGE_PYTEST_TIMEOUT)
- Removed dead code (pydantic-ai dep, unused REPAIR_PROMPT import)
- Renamed TestResult → TestRunResult to avoid pytest collection warning

## Project Structure

```
specforge/
    __init__.py
    __main__.py
    cli.py              # Typer CLI
    config.py           # Model/provider config
    models.py           # Pydantic models (SystemDesign, AgentState, etc.)
    workflow.py          # LangGraph workflow
    agents/
        __init__.py
        architect.py     # Spec -> SystemDesign
        coder.py         # SystemDesign -> project files
        tester.py        # Run tests, parse results
    providers/
        __init__.py      # LlmProvider protocol, ApiProvider, PiProvider, factory
        pi_rpc.py        # Pi RPC subprocess client
    prompts/
        __init__.py
        architect.py     # Architect prompt templates
        coder.py         # Coder prompt templates
        tester.py        # Tester prompt templates
    examples/
        advanced-shortener-sqlite.md
    utils/
        __init__.py
        console.py       # Rich console helpers
tests/
    __init__.py
    test_models.py
    test_config.py
    test_coder_parse.py
    test_tester_parse.py
pyproject.toml
README.md
.env.example
CLAUDE.md
CLAUDE.original.md       # Original spec preserved for evaluation
```

## Key Libraries

| Library          | Purpose                                              |
|------------------|------------------------------------------------------|
| LangGraph        | Stateful agent workflow graph with conditional edges  |
| langchain-openai | LLM provider integration (API mode)                  |
| Typer            | CLI framework (`specforge generate ...`)             |
| Rich             | Beautiful terminal output (spinners, panels, colors) |
| Pydantic         | Structured models for SystemDesign                   |
| python-dotenv    | Environment variable loading                         |
