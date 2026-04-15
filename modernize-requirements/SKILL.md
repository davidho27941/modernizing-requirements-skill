---
name: modernize-requirements
description: >
  Use this skill when the user wants to migrate or convert a Python project's
  requirements.txt to pyproject.toml, whether they use words like "modernize",
  "migrate", "convert", "move to", "switch to", or "clean up". Covers adopting
  uv or Poetry as a package manager, sorting out direct vs transitive
  dependencies from pip-freeze output, generating lockfiles, and updating
  Dockerfiles for the new setup. Trigger for any request involving a Python
  project that currently has requirements.txt and wants pyproject.toml —
  including messy inherited projects, CI pipeline modernization, or fixing
  build issues (like pkg_resources errors) as part of a dependency overhaul.
  Works with any spoken language. Do NOT trigger for: writing Dockerfiles from
  scratch, new project setup, non-Python packaging, scripting/analyzing
  requirements without migration, or projects already on pyproject.toml.
---

# Modernize Requirements: `requirements.txt` → `pyproject.toml`

This skill converts a legacy `pip freeze`-style `requirements.txt` into a
modern Python dependency setup: `pyproject.toml` as the source of truth,
paired with a reproducible lockfile.

The user chooses between two target package managers:

| | **uv** | **Poetry** |
|---|---|---|
| Lockfile | `uv.lock` | `poetry.lock` |
| pyproject.toml style | PEP 621 `[project]` | `[tool.poetry]` (Poetry-native) or PEP 621 (Poetry 2.x) |
| Dev deps | `[dependency-groups]` (PEP 735) | `[tool.poetry.group.dev.dependencies]` |
| Build backend | `hatchling` (or any PEP 517 backend) | `poetry-core` |
| Install command | `uv sync` | `poetry install` |

The core insight is the same for both: `requirements.txt` from `pip freeze`
mixes direct dependencies (what the code actually imports) with transitive
ones (pulled in automatically). This skill uses AST static analysis to
separate them, so the resulting `pyproject.toml` is clean and intentional.

---

## Before you start

1. **Ask the user which package manager they want**: `uv` or `Poetry`.
   If they are unsure, recommend `uv` — it is faster, uses standard PEP 621
   format, and has simpler mental model. But respect their preference.

2. Confirm prerequisites based on their choice:

   **For uv:**
   - `uv` is installed (`uv --version`). If not: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - `pip-tools` is available (`pip-compile --version`). If not: `python -m pip install pip-tools`

   **For Poetry:**
   - `poetry` is installed (`poetry --version`). If not: `curl -sSL https://install.python-poetry.org | python3 -`
   - Poetry 1.2+ is required for dependency groups.

3. Confirm the project has a `requirements.txt` to migrate.

**Important constraints — these apply regardless of tool choice:**
- Never modify the project's source code. This skill only touches dependency
  and configuration files.
- Preserve the original `requirements.txt` — the user may need it for rollback.
- **Do not access dot-directories or dotfiles** (e.g., `.env`, `.git`,
  `.github`, `.secrets`). The only exceptions are `.claude` (skill resources)
  and `.venv` (virtual environment detection). Dotfiles often contain secrets,
  credentials, or sensitive configuration — reading them is unnecessary for
  dependency migration and risks leaking private data. If the project has a
  `.python-version` file, you may read it solely to determine the Python
  version constraint.

**Heads-up: `pkg_resources` removal in setuptools 82+**

Since setuptools 82.0.0 (Feb 2026), `pkg_resources` has been fully removed.
Both uv and Poetry use build isolation by default — meaning they pull the
latest setuptools when building packages from source. Old packages whose
`setup.py` imports `pkg_resources` will fail to build. The tool-specific
reference files (Phase 5) contain detailed troubleshooting for this, but be
aware of it upfront: if the project depends on older packages, build
failures in Phase 5 are likely and the reference files explain how to fix
them.

---

## Workflow overview

The migration has 7 phases. Phases 0–2 are identical regardless of tool
choice. Phases 3–7 diverge — follow the appropriate reference file.

```
Phase 0  → Plan & backup                          (common)
Phase 1  → Inventory the existing requirements.txt (common)
Phase 2  → AST scan to find direct dependencies    (common)
Phase 3  → Verify resolved dependencies             (tool-specific)
Phase 4  → Create or update pyproject.toml          (tool-specific)
Phase 5  → Generate lockfile                        (tool-specific)
Phase 6  → Migrate Dockerfiles                      (tool-specific)
Phase 7  → CI integration notes                     (tool-specific)
Phase 8  → Cleanup & summary                        (tool-specific)
```

After completing Phase 2, read the appropriate reference file for Phases 3–8:
- **uv** → `references/uv.md`
- **Poetry** → `references/poetry.md`

---

## Phase 0 — Plan & backup

**Before doing anything else**, produce a `plan.md` in the project root. This
file is for the user to review and approve before you proceed. It should
contain:
- Which package manager was selected (uv or Poetry)
- Each phase you intend to execute and what it will do
- Which files you will scan (source directories, test directories)
- Which files you will create or modify
- Any questions or ambiguities you need the user to clarify

Wait for the user to confirm the plan before moving on.

Then create a working branch and back up existing files:
```bash
git checkout -b chore/modernize-deps
cp requirements.txt requirements.txt.bak
[ -f pyproject.toml ] && cp pyproject.toml pyproject.toml.bak
```

**Determine the Python version** for `requires-python` in pyproject.toml.
The virtual environment may not exist (the project might be inherited, the
CI environment might differ, or `.venv` may simply not have been created
yet), so do not assume `python --version` reflects the intended version.
Follow this order:

1. **Check project configuration files** — look for an explicit Python
   version in `setup.py` (`python_requires=`), `setup.cfg`
   (`python_requires =` under `[options]`), `Dockerfile` (`FROM python:X.Y`),
   or `.python-version`. These are the most authoritative sources because
   they represent what the project was designed for.
2. **If no configuration specifies a version** — check the system Python
   (`python3 --version`) as a reference point, but do not assume it is
   correct. Present the detected version to the user and ask them to
   confirm or choose a different one. For example: *"I didn't find a Python
   version constraint in any config file. The system Python is 3.11 —
   should I use `>=3.11`, or do you need to support a different version?"*

Getting this right matters because `requires-python` gates which Python
versions can install the package. Setting it too high locks out users on
older versions; setting it too low may allow installation on versions the
code doesn't actually support.

---

## Phase 1 — Inventory the existing `requirements.txt`

Parse every line of `requirements.txt` into structured data:
- Package name, version specifier, hashes, environment markers
- Flag special entries: VCS installs (`git+…`), URL installs, local paths
  (`-e .`), conditional markers (`; python_version < "3.11"`)

Save the inventory as `reports/old_requirements.json` with fields:
`name`, `pinned_version`, `is_vcs`, `is_local`, `markers`, `raw_line`.

This is your "old world" snapshot — you will diff against it later.

---

## Phase 2 — AST scan for direct dependencies

This is the core of the migration. A bundled scanner script does the heavy
lifting.

### 2.0 Locate the source directories to scan

Before running the scanner, you need to know which directories contain the
project's source code. Follow this order:

1. **Check for `setup.py` or `setup.cfg`** — if the project has one, parse it
   to find the package directories (look for `packages=`, `package_dir=`,
   `py_modules=`, or `find_packages()` calls). This is the most reliable
   signal for legacy projects that haven't been modernized yet.
2. **If no `setup.py`/`setup.cfg` exists** — ask the user which directories
   contain the target source code. Do not guess or scan the entire project
   tree blindly. For example: *"I don't see a `setup.py` — which directories
   contain your application code? (e.g., `src/`, `app/`, `myproject/`)"*

This matters because scanning the wrong directories (or the entire repo)
produces noisy results — it may pick up imports from vendored code, example
scripts, or unrelated utilities that aren't part of the package.

### 2.1 Run the scanner

The scanner lives at `scripts/scan_imports.py` (bundled with this skill).
Run it against the identified source directories (not blindly against the
project root):

```bash
python <skill-path>/scripts/scan_imports.py <source-directory> \
    --json \
    --first-party <comma-separated-first-party-packages> \
    --include-dev \
    --show-unknown
```

If there are multiple source directories (e.g., `src/` and `tests/`), run
the scanner once per directory and merge the results, tagging `tests/`
imports as dev dependencies.

The `--first-party` flag excludes the project's own packages. Determine these
from `setup.py`/`setup.cfg` metadata, `src/` layout, or by asking the user.

The script:
1. Walks all `.py` files (skipping `.venv`, `build`, `dist`, `__pycache__`, etc.)
2. Parses each file with `ast` and extracts `import` / `from … import` names
3. Filters out stdlib modules and first-party packages
4. Maps import names to PyPI distribution names using a curated lookup table
   (covers 90+ common mismatches like `PIL` → `pillow`, `cv2` → `opencv-python`)
5. Falls back to `importlib.metadata.packages_distributions()` for names not
   in the table
6. Flags dynamic imports (`importlib.import_module`, `__import__`) as warnings

### 2.2 Review the results

Compare the scanner output against `reports/old_requirements.json`:

- **In requirements.txt but NOT in scan results** → likely transitive.
  Confirm with the user before excluding.
- **In scan results but NOT in requirements.txt** → possibly missing or
  pulled in implicitly. Must be added as an explicit dependency.

Pay special attention to:
- **Dynamic imports** — the scanner flags these but cannot resolve them.
  Grep for `import_module` and `__import__` and ask the user about them.
- **Optional extras** — e.g., `uvicorn[standard]`, `pydantic[email]`.
  Check usage context to decide whether extras are needed.
- **CLI-only tools** — `ruff`, `mypy`, `pytest`, etc. belong in dev
  dependencies, not runtime.

Save the classified results to `reports/direct_imports.json`.

---

## Phases 3–7 — Tool-specific workflow

At this point, read the reference file for the chosen package manager:

- **uv** → Read `references/uv.md` and follow Phases 3–8 there.
- **Poetry** → Read `references/poetry.md` and follow Phases 3–8 there.

Do not mix instructions between the two — each reference file is
self-contained for Phases 3 through 8.
