# modernize-requirements

**Stop hand-editing `pyproject.toml`. Let Claude do the migration for you.**

Most Python projects still ship a `requirements.txt` dumped from `pip freeze` — hundreds of pinned lines mixing the packages you actually import with every transitive dependency pip pulled in. Migrating to `pyproject.toml` by hand means guessing which packages are direct, re-learning PEP 621 syntax, wiring up lockfiles, and rewriting Dockerfiles. It's tedious, error-prone, and easy to get wrong.

**modernize-requirements** is a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that handles the entire migration in one conversation. Point it at a project with `requirements.txt`, pick **uv** or **Poetry**, and it walks through a structured 9-phase workflow — from planning to lockfile generation to Dockerfile rewrites — while you review and approve each step.

### Why use this over doing it manually?

| Manual migration | With this skill |
|---|---|
| Guess which of 200+ frozen packages your code actually imports | AST-based scanner analyzes every `.py` file and separates direct from transitive |
| Copy-paste version pins and hope you got the format right | Pinned versions carry over exactly — no silent upgrades or loosened constraints |
| Debug cryptic `pkg_resources` build failures alone | Built-in workarounds for setuptools 82+ breakage, with guided fallback when workarounds aren't enough |
| Write `pyproject.toml` from memory or Stack Overflow | Generates spec-compliant config: PEP 621 for uv, `[tool.poetry]` for Poetry |
| Forget to update the Dockerfile | Automatically rewrites `pip install -r requirements.txt` → `uv sync` / `poetry install` |

## Features

- **AST-based import scanning** — Separates direct dependencies from transitive ones using static analysis, not guesswork
- **Clean `pyproject.toml` generation** — PEP 621 format for uv, or `[tool.poetry]` format for Poetry
- **Reproducible lockfiles** — `uv.lock` or `poetry.lock`, generated and validated
- **Dockerfile migration** — Rewrites install commands for the new package manager
- **Version preservation** — Migrates structure, not content: your exact pins are carried over unchanged
- **Migration plans** — Generates a structured `plan.md` with executive summary, risk analysis, rollback strategy, and files inventory before touching anything
- **Smart source discovery** — Finds package directories via `setup.py`/`setup.cfg` instead of blindly scanning the project root
- **Security-conscious** — Skips dot-directories and dotfiles (`.env`, `.git`, `.secrets`) to avoid leaking credentials
- **Robust Python version detection** — Reads `setup.py`, `setup.cfg`, `Dockerfile`, `.python-version` to determine `requires-python` correctly
- **`pkg_resources` handling** — Workarounds for packages broken by setuptools 82+, with user-guided fallback

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
