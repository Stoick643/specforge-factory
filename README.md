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
git clone https://github.com/Stoick643/specforge-factory.git
cd specforge-factory
pip install -e .
```

## Three Ways to Use

### 1. CLI with Pi (no API key needed!)

If you have [Pi](https://github.com/mariozechner/pi-coding-agent) installed with a Claude Max plan:

```bash
specforge generate spec.md --provider pi --output ./my-service
```

### 2. CLI with API key

```bash
cp .env.example .env
# Edit .env and set your API key

specforge generate spec.md --model gpt-4o --output ./my-service
```

Supported: OpenAI, Anthropic, Moonshot/Kimi, DeepSeek, OpenRouter.

### 3. Web UI (browser)

```bash
python -m web.run
# Open http://localhost:8080
```

Write your spec in the editor, enter your API key, click Generate. Watch live progress as agents work, then browse the generated files or download as ZIP.

## CLI Usage

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

### Built-in Example: URL Shortener

```bash
# Generate with Pi (no API key needed)
specforge generate specforge/examples/advanced-shortener-sqlite.md \
  --output ./my-shortener --provider pi --clean

# Run it
cd my-shortener
cp .env.example .env
docker-compose up --build
# Visit http://localhost:8000/docs
```

## Web UI

The Web UI provides a browser-based interface:

- **Left panel**: Markdown editor with template dropdown
- **Right panel**: Live progress log during generation
- **File browser**: Tree view + Monaco editor (VS Code's editor) for code preview
- **Download**: Get the generated project as a ZIP

```bash
python -m web.run
```

Then open http://localhost:8080

## Project Structure

```
specforge/                  # Core engine (CLI + agents)
    cli.py                  # Typer CLI
    config.py               # Model/provider config
    events.py               # Progress event system
    models.py               # SystemDesign, AgentState, TestResult
    workflow.py             # LangGraph: Architect -> Coder -> Tester
    agents/                 # Architect, Coder, Tester
    providers/              # LlmProvider: API + Pi RPC
    prompts/                # Agent prompt templates
    examples/               # Built-in example specs
    utils/                  # Rich console helpers
web/                        # Web UI
    backend/main.py         # FastAPI server + WebSocket
    frontend/index.html     # Single-page app
    run.py                  # Start script
tests/                      # 122+ unit tests
```

## License

MIT
