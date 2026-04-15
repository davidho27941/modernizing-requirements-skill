# modernize-requirements

A Claude Code skill that migrates Python projects from `requirements.txt` to modern `pyproject.toml` + lockfile setup, with either **uv** or **Poetry** as the package manager.

## What it does

1. **AST-based import scanning** — Analyzes your Python source code to separate direct dependencies from transitive ones (the ones `pip freeze` dumps in but your code never imports)
2. **Generates clean `pyproject.toml`** — PEP 621 format for uv, or `[tool.poetry]` format for Poetry
3. **Produces lockfiles** — `uv.lock` or `poetry.lock` for reproducible installs
4. **Migrates Dockerfiles** — Rewrites `pip install -r requirements.txt` to `uv sync` or `poetry install`
5. **Handles `pkg_resources` build failures** — Includes setuptools constraint workarounds for older packages broken by setuptools 82+; asks the user for help when workarounds are insufficient instead of upgrading packages
6. **Preserves pinned versions** — Migrates structure, not content: exact version pins from `requirements.txt` are carried over to `pyproject.toml` without loosening or upgrading
7. **Documents everything** — Generates `plan.md` before starting and `summary.md` after, with old-vs-new command comparison tables
8. **Smart source discovery** — Locates package directories via `setup.py`/`setup.cfg` rather than blindly scanning the project root; asks the user when no config exists
9. **Security-conscious** — Skips dot-directories and dotfiles (`.env`, `.git`, `.secrets`, etc.) by default to avoid leaking credentials or sensitive config; only `.claude` and `.venv` are allowed
10. **Robust Python version detection** — Determines `requires-python` from project config files (`setup.py`, `setup.cfg`, `Dockerfile`, `.python-version`) instead of assuming the system Python is correct; asks the user to confirm when no config is found

## Install

Copy the skill directory into your Claude Code skills folder:

```bash
# Project-specific (current project only)
cp -r modernize-requirements .claude/skills/

# Or personal (available in all projects)
cp -r modernize-requirements ~/.claude/skills/
```

Claude Code automatically discovers skills once the files are in place — no restart needed.

## Usage

Just ask Claude to migrate your project. Examples:

- "Migrate my requirements.txt to pyproject.toml with uv"
- "Convert this project to use Poetry, including the Dockerfile"
- "Clean up my pip freeze output and set up proper dependency management"
- "I inherited this old Flask project, modernize the deps"

The skill will ask you to choose between uv and Poetry, then walk through the migration phases.

## Workflow

The migration runs in 9 phases:

| Phase | Description | Scope |
|-------|-------------|-------|
| 0 | Plan & backup — generates `plan.md` for user review | Common |
| 1 | Inventory `requirements.txt` into structured JSON | Common |
| 2 | AST scan to classify direct vs transitive dependencies | Common |
| 3 | Verify resolved dependencies | Tool-specific |
| 4 | Create or update `pyproject.toml` | Tool-specific |
| 5 | Generate lockfile | Tool-specific |
| 6 | Migrate Dockerfiles | Tool-specific |
| 7 | CI integration notes | Tool-specific |
| 8 | Cleanup & summary | Tool-specific |

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

It walks `.py` files, extracts imports via `ast`, filters out stdlib/first-party, and maps import names to PyPI distribution names using a curated lookup table (handles mismatches like `PIL` → `pillow`, `cv2` → `opencv-python`, `yaml` → `pyyaml`, etc.). Hidden directories are skipped by default for security.
