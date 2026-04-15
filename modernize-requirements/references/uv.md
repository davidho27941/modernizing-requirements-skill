# uv workflow — Phases 3–8

Continue here after completing Phases 0–2 in SKILL.md.

---

## Phase 3 — Write `requirements.in` and verify with `pip-compile`

`requirements.in` captures intent; `requirements.compiled.txt` is the
resolved output. This intermediate step validates that the dependency set
resolves cleanly before committing to `pyproject.toml`.

1. Create `requirements.in` with only direct runtime dependencies,
   preserving the exact version pins from `requirements.txt`:
   ```text
   # Direct runtime dependencies (versions from requirements.txt)
   fastapi==0.115.12
   pydantic==2.11.1
   httpx==0.28.1
   ```
   - Preserve the pinned versions (`==`) from `requirements.txt`. Do not
     loosen them to `>=` — the user's pinned versions represent a tested,
     working configuration.
   - Keep VCS/URL installs in their PEP 440 form:
     `mypackage @ git+https://github.com/org/mypackage@v1.2.3`

2. Create `requirements-dev.in` for dev dependencies, starting with
   `-r requirements.in` on the first line.

3. Compile:
   ```bash
   pip-compile --resolver=backtracking --strip-extras \
       --output-file=requirements.compiled.txt requirements.in
   pip-compile --resolver=backtracking \
       --output-file=requirements-dev.compiled.txt requirements-dev.in
   ```

4. Verify in a clean venv:
   ```bash
   python -m venv .venv-check
   .venv-check/bin/pip install -r requirements.compiled.txt
   .venv-check/bin/python -c "import <key_package>"  # smoke test
   ```
   If this fails, revisit Phase 2 for missed dependencies.

---

## Phase 4 — Create or update `pyproject.toml`

uv uses **PEP 621** standard fields. Dependencies go in `[project].dependencies`,
not in any tool-specific section.

### If `pyproject.toml` does not exist

Create it from scratch:
```toml
[project]
name = "<project-name>"
version = "0.1.0"
description = ""
requires-python = ">=3.11"  # based on Phase 0 Python version check
readme = "README.md"
dependencies = [
    # from requirements.in — preserve pinned versions
    "fastapi==0.115.12",
    "pydantic==2.11.1",
    "httpx==0.28.1",
]

[dependency-groups]  # PEP 735
dev = [
    "pytest==8.3.5",
    "ruff==0.9.1",
    "mypy==1.14.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### If `pyproject.toml` already exists

- Do NOT touch `[build-system]`, `[tool.*]`, or other existing config.
- Replace `[project].dependencies` with the Phase 3 direct dependency list.
- Move dev dependencies to `[dependency-groups].dev`.
- If the project currently uses Poetry or PDM format, the user needs to decide
  whether to fully migrate to PEP 621. During transition, `uv` reads
  `[project]` as its source of truth.

### Consistency check

Verify that the set of package names in `pyproject.toml` `dependencies`
matches `requirements.in` exactly (version specifiers may differ, but no
package should be missing from either side).

---

## Phase 5 — Generate `uv.lock`

```bash
uv sync          # reads pyproject.toml, creates .venv, writes uv.lock
```

Verify:
```bash
uv run python -c "import <key_packages>"   # spot-check
uv run pytest                                # if tests exist
```

Cross-check against the pip-compile output:
```bash
uv export --format requirements-txt --no-hashes > reports/uv_export.txt
diff <(sort requirements.compiled.txt) <(sort reports/uv_export.txt)
```

Minor differences (marker formatting, etc.) are expected. Substantive version
differences mean something is off — revisit Phase 3.

### Troubleshooting: `pkg_resources` / setuptools build failures

When `uv sync` builds a package from source, it uses **build isolation** —
a fresh environment with the latest setuptools. Since setuptools 82.0.0
(Feb 2026) removed `pkg_resources` entirely, any package whose `setup.py`
does `import pkg_resources` will fail with:

```
ModuleNotFoundError: No module named 'pkg_resources'
```

This is common with older or unmaintained packages. There are two approaches,
and you may need both depending on the package.

**Approach 1: Constrain setuptools version (try this first)**

Add a build constraint in `pyproject.toml` to force an older setuptools
during the isolated build of the problematic package:

```toml
[tool.uv]
constraint-dependencies = [
    "setuptools<82",
]
```

If `<82` is not enough (some very old packages rely on deprecated setuptools
internals removed earlier), try `<65`.

**Approach 2: Disable build isolation for specific packages**

If constraining setuptools does not help — for instance, when the package
has undeclared build dependencies that are not in its `[build-system].requires`
— you need to disable build isolation so the package builds against your
existing environment:

```bash
uv sync --no-build-isolation-package <package-name>
```

Or persistently in `pyproject.toml`:

```toml
[tool.uv]
no-build-isolation-package = ["<package-name>"]
```

When build isolation is disabled for a package, uv does a two-phase install:
first it installs all isolated packages (so their modules are available),
then it builds the non-isolated packages using the same environment. This
means the non-isolated package's build dependencies must already be in your
dependency tree.

**Approach 3: Combine both**

For the trickiest cases, you may need both: constrain setuptools AND disable
isolation for specific packages. For example, a package that does
`import pkg_resources` AND also imports another package at build time that
is not declared in its `[build-system].requires`.

**Diagnosing which packages are affected**

If `uv sync` fails, the error message will name the package that failed to
build. Check its `setup.py` or `setup.cfg` on PyPI/GitHub:
- If it contains `import pkg_resources` or `from pkg_resources import …`
  → setuptools constraint needed
- If it imports other packages at build time without declaring them
  → build isolation needs to be disabled

Present the user with the failing package(s) and the recommended fix before
applying it.

**If the build still fails after trying all approaches above**, do not attempt
to upgrade the package to a different version. The user's pinned versions
represent a tested configuration. Instead, report the failure clearly —
include the package name, the error message, and which approaches you tried —
and ask the user how they want to proceed. They may know of a workaround,
have access to a private wheel, or may decide to upgrade the package themselves.

---

## Phase 6 — Migrate Dockerfiles

Search the project for Dockerfiles (`Dockerfile`, `Dockerfile.*`,
`*.dockerfile`, and files inside `docker/` or `.docker/` directories).
If none are found, skip this phase.

For each Dockerfile that contains dependency-installation instructions
(`pip install`, `COPY requirements.txt`, etc.), migrate them to use `uv`.

### What to look for

Scan each Dockerfile for these patterns — they are the lines you need to
rewrite:

- `COPY requirements.txt .` (or similar `COPY` of requirements files)
- `RUN pip install -r requirements.txt`
- `RUN pip install --no-cache-dir -r requirements.txt`
- `RUN pip install -e .`
- `RUN pip install <packages>`
- Multi-line `RUN` blocks that chain `pip install` with `&&`

### Migration strategy

**1. Install uv in the image**

Add this near the top of the Dockerfile (after `FROM`):
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
```
This is the recommended approach — it uses a multi-stage copy so `curl` is
not needed in the image.

**2. Copy dependency files instead of requirements.txt**

Replace:
```dockerfile
COPY requirements.txt .
```
With:
```dockerfile
COPY pyproject.toml uv.lock ./
```

**3. Replace pip install with uv sync**

Replace:
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
With:
```dockerfile
RUN uv sync --frozen --no-dev --no-install-project
```

- `--frozen` ensures the lockfile is used as-is (no re-resolving).
- `--no-dev` skips dev dependencies in production images.
- `--no-install-project` installs only dependencies, not the project itself.
  Omit this flag if the project should be installed too.

If the original Dockerfile installed the project in editable mode
(`pip install -e .`), replace with:
```dockerfile
COPY . .
RUN uv sync --frozen --no-dev
```

**4. Leverage layer caching**

A well-structured Dockerfile copies dependency files first (for caching),
then copies the full source. The pattern:
```dockerfile
# -- deps layer (cached unless pyproject.toml or uv.lock changes) --
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# -- app layer --
COPY . .
RUN uv sync --frozen --no-dev
```

**5. Handle `uv run` vs direct `python`**

If the Dockerfile uses `CMD ["python", "app.py"]` or an entrypoint that
invokes Python directly, it will still work because `uv sync` installs into
the environment. However, if the Dockerfile previously activated a virtualenv
explicitly, you can either:
- Set `ENV UV_PROJECT_ENVIRONMENT=/app/.venv` and
  `ENV PATH="/app/.venv/bin:$PATH"`, or
- Use `CMD ["uv", "run", "python", "app.py"]`

### What NOT to change

- Do not touch non-dependency-related Dockerfile instructions (`EXPOSE`,
  `HEALTHCHECK`, `LABEL`, `WORKDIR`, app-specific `COPY`/`RUN`, etc.).
- Do not change the base image unless the user asks.
- Do not restructure multi-stage builds beyond what is needed for the
  dependency swap.
- Preserve comments that explain why certain flags or layers exist.

### Show the diff

After making changes, present the user with a before/after comparison of each
modified Dockerfile so they can review the changes.

---

## Phase 7 — CI & deployment notes

Prepare notes for the user (include in `summary.md`):

- **Files to commit:** `pyproject.toml`, `uv.lock`, optionally
  `requirements.in` and `requirements-dev.in`.
- **Deploy with requirements.txt:** If the deploy environment only accepts
  `requirements.txt`, generate it in CI with `uv export --format requirements-txt`
  rather than maintaining it by hand.
- **Deploy with uv:** Use `uv sync --frozen --locked` in CI — this fails if
  the lockfile is stale relative to `pyproject.toml`.
- **README:** Update install instructions from
  `pip install -r requirements.txt` to `uv sync`.

---

## Phase 8 — Cleanup & summary

After everything is verified, generate `summary.md` in the project root.
This file must be thorough and include:

### 1. All files created and their purpose

| File | Purpose |
|---|---|
| `pyproject.toml` | Authoritative dependency source (PEP 621) |
| `uv.lock` | Reproducible lockfile |
| `requirements.in` | Human-readable direct runtime deps (intent file) |
| `requirements-dev.in` | Human-readable direct dev deps (intent file) |
| `requirements.compiled.txt` | pip-compile output, used for verification |
| `requirements-dev.compiled.txt` | pip-compile output (dev), used for verification |
| `reports/` | Analysis artifacts (old_requirements.json, direct_imports.json, etc.) |
| `Dockerfile` (modified) | Updated to use `uv sync` instead of `pip install` |

### 2. Dockerfile changes

If Dockerfiles were modified in Phase 6, list each one with a summary of
what changed (e.g., "replaced `pip install -r requirements.txt` with
`uv sync --frozen --no-dev`"). Include the before/after diff or a reference
to it.

### 3. Intermediate files that can be removed

Explain each file's purpose and tell the user they can delete them if not
needed. Do NOT delete them yourself:
- `requirements.in`, `requirements-dev.in`
- `requirements.compiled.txt`, `requirements-dev.compiled.txt`
- `reports/` directory
- `.venv-check/` (the verification venv)
- `*.bak` backup files

### 4. Original `requirements.txt` is preserved

Remind the user it is still there for rollback reference.

### 5. Command comparison: old vs new

| Old workflow | New workflow (uv) |
|---|---|
| `pip install -r requirements.txt` | `uv sync` |
| `pip freeze > requirements.txt` | `uv lock` (or `uv add <pkg>`) |
| `pip install <new-pkg>` | `uv add <new-pkg>` |
| `pip install -e .` | `uv sync` (handles editable automatically) |
| `pip-compile requirements.in` | `uv lock` |
| `pip install --upgrade <pkg>` | `uv add <pkg>@latest` |

### 6. Direct vs transitive dependency summary

Report how many packages were in the original `requirements.txt`, how many
turned out to be direct, and how many were transitive.

Do NOT remove any intermediate files. Let the user decide what to clean up.
