# modernize-requirements

A Claude Code skill that migrates Python projects from `requirements.txt` to modern `pyproject.toml` + lockfile setup, with either **uv** or **Poetry** as the package manager.

## What it does

1. **AST-based import scanning** — Analyzes your Python source code to separate direct dependencies from transitive ones (the ones `pip freeze` dumps in but your code never imports)
2. **Generates clean `pyproject.toml`** — PEP 621 format for uv, or `[tool.poetry]` format for Poetry
3. **Produces lockfiles** — `uv.lock` or `poetry.lock` for reproducible installs
4. **Migrates Dockerfiles** — Rewrites `pip install -r requirements.txt` to `uv sync` or `poetry install`
5. **Handles `pkg_resources` build failures** — Includes setuptools constraint workarounds for older packages broken by setuptools 82+
6. **Documents everything** — Generates `plan.md` before starting and `summary.md` after, with old-vs-new command comparison tables

## Install

```bash
claude skill install modernize-requirements.skill
```

## Usage

Just ask Claude to migrate your project. Examples:

- "Migrate my requirements.txt to pyproject.toml with uv"
- "Convert this project to use Poetry, including the Dockerfile"
- "Clean up my pip freeze output and set up proper dependency management"

The skill will ask you to choose between uv and Poetry, then walk through the migration phases.

## Skill structure

```
modernize-requirements/
├── SKILL.md                 # Main workflow (phases 0–2 common, then tool handoff)
├── references/
│   ├── uv.md                # uv-specific phases 3–8
│   └── poetry.md            # Poetry-specific phases 3–8
├── scripts/
│   └── scan_imports.py      # Bundled AST scanner (90+ import-to-dist mappings)
└── evals/
    ├── evals.json            # Test case definitions
    └── fixtures/             # Sample projects for testing
```

## Bundled script

`scripts/scan_imports.py` can also be used standalone:

```bash
python scan_imports.py /path/to/project --json --include-dev --show-unknown
```

It walks `.py` files, extracts imports via `ast`, filters out stdlib/first-party, and maps import names to PyPI distribution names using a curated lookup table (handles mismatches like `PIL` → `pillow`, `cv2` → `opencv-python`, `yaml` → `pyyaml`, etc.).
