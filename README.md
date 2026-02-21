# SpecForge

**Spec-Driven Multi-Agent Microservice Factory**

Generate complete, tested, Docker-ready FastAPI microservices from Markdown specs using a self-correcting 3-agent loop.

## How It Works

```
Architect --> Coder --> Tester
                ^         |
                |  fails  |
                +---------+
              (max 4 iterations)
```

1. **Architect** - Analyzes your Markdown spec, produces a structured SystemDesign
2. **Coder** - Takes the SystemDesign, generates all project files (app, tests, Docker, etc.)
3. **Tester** - Runs pytest on the generated code, if tests fail sends feedback back to Coder

The loop runs up to 4 iterations until all tests pass.

## Installation

```bash
pip install -e .
```

## Two Ways to Run

### Option 1: Pi Provider (no API key needed!)

If you have [Pi](https://github.com/mariozechner/pi-coding-agent) installed with a Claude Max plan:

```bash
specforge generate spec.md --provider pi --output ./my-service
```

This spawns Pi as a subprocess and uses your existing Claude access. No API key required!

### Option 2: API Provider (needs API key)

Set your API key in `.env`:

```bash
cp .env.example .env
# Edit .env and set your API key
```

Supported providers:
- **OpenAI**: `OPENAI_API_KEY` (models: gpt-4o, gpt-4o-mini)
- **Anthropic**: `ANTHROPIC_API_KEY` (models: claude-sonnet-4-20250514)
- **Moonshot/Kimi**: `MOONSHOT_API_KEY` (models: kimi-k2.5)
- **DeepSeek**: `DEEPSEEK_API_KEY` (models: deepseek-chat)
- **OpenRouter**: `OPENROUTER_API_KEY` (models: org/model format)

```bash
specforge generate spec.md --model gpt-4o --output ./my-service
specforge generate spec.md --model kimi-k2.5 --output ./my-service
```

## Usage

### Generate a microservice from a spec

```bash
specforge generate path/to/spec.md --output ./my-service
```

### Options

```bash
specforge generate spec.md \
  --output ./out \
  --provider pi \
  --max-iterations 4 \
  --clean
```

| Flag | Description | Default |
|------|-------------|---------|
| `--output, -o` | Output directory | `./output` |
| `--provider, -p` | `api` or `pi` | `api` |
| `--model` | LLM model (api provider only) | `gpt-4o` |
| `--max-iterations, -m` | Max Coder->Tester loops | `4` |
| `--clean` | Remove output dir first | `false` |

### View the built-in example spec

```bash
specforge example
specforge example --copy-to my-spec.md
```

### Built-in Example: URL Shortener

```bash
# Copy the example spec
specforge example --copy-to shortener.md

# Generate with Pi (no API key needed)
specforge generate shortener.md --output ./my-shortener --provider pi --clean

# Or with an API key
specforge generate shortener.md --output ./my-shortener --model gpt-4o --clean

# Run it
cd my-shortener
docker-compose up --build
# Visit http://localhost:8000/docs
```

## Project Structure

```
specforge/
    __init__.py, __main__.py
    cli.py              # Typer CLI
    config.py           # Model/provider config
    models.py           # SystemDesign, AgentState, TestResult
    workflow.py          # LangGraph: Architect -> Coder -> Tester
    agents/
        architect.py     # Spec -> SystemDesign
        coder.py         # SystemDesign -> project files (batch generation)
        tester.py        # Run pytest, analyze failures
    providers/
        __init__.py      # LlmProvider protocol, ApiProvider, PiProvider
        pi_rpc.py        # Pi RPC subprocess client
    prompts/
        architect.py, coder.py, tester.py
    examples/
        advanced-shortener-sqlite.md
    utils/
        console.py       # Rich console helpers
```

## License

MIT
