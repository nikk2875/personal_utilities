# AGENTS.md

## Project
This project is a container for small utilities that can help me in my personal tasks.

## Setup
```bash
uv sync
```

Fallback without uv:
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .
```

## Implementation guidelines
- Code in Python, type hints on function signatures.
- Keep the code simple and readeable.
- Do not overuse functions.
- Standard library first; add a dependency only if it clearly earns it.
- f-strings, `logging` over `print`.
- Do not share code or functions. Every python script must be portable and must contain all code required. Assume dependant libraries are already there.
- Make temporary tests for every bug fix and new behavior. Run and show the results, then  clean them up.

## Layout
- `src/` — code, one python script per utility
- `docs/` — documentation and plans for agentic implementation
- `pyproject.toml` — dependencies and tool config (single source of truth)

## Notes
- Keep diffs small and focused; no drive-by refactors.
- Ask my approval before applying changes to any file.
