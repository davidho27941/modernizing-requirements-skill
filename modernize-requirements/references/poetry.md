# Poetry workflow — Phases 3–8

Continue here after completing Phases 0–2 in SKILL.md.

---

## Phase 3 — Verify dependencies with Poetry's resolver

Unlike the uv workflow, Poetry has its own resolver built in, so there is no
need for `pip-compile` as a separate verification step. Instead, you verify
by letting Poetry resolve directly.

1. Create a temporary `requirements.in` with only direct runtime dependencies.
   This is not consumed by Poetry — it serves as a human-readable record of
   the dependency set you identified in Phase 2:
   ```text
   # Direct runtime dependencies
   fastapi>=0.110
   pydantic>=2
   httpx
   ```
   Use loose version specifiers (`>=`) to give the resolver room.

2. Similarly, create `requirements-dev.in` listing dev-only dependencies.

These files are reference artifacts. Poetry reads `pyproject.toml`, not `.in`
files, so the actual verification happens in Phase 5 after you write the
pyproject.toml.

---

## Phase 4 — Create or update `pyproject.toml`

Poetry uses its own `[tool.poetry]` section for project metadata and
dependencies. If the user is on Poetry 2.x and prefers PEP 621
(`[project].dependencies`), that is supported — ask them. The default here
assumes the more common Poetry-native format.

### If `pyproject.toml` does not exist

Create it from scratch:
```toml
[tool.poetry]
name = "<project-name>"
version = "0.1.0"
description = ""
readme = "README.md"
authors = ["Your Team"]

[tool.poetry.dependencies]
python = ">=3.11"
# from Phase 2 direct dependencies
fastapi = ">=0.110"
pydantic = ">=2"
httpx = "*"

[tool.poetry.group.dev.dependencies]
pytest = ">=8"
ruff = "*"
mypy = "*"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Key differences from PEP 621 (uv) format:**
- Version specifiers use `=` not `==`, and `*` means "any version".
- The `python` dependency is declared explicitly in
  `[tool.poetry.dependencies]`.
- Dev dependencies go under `[tool.poetry.group.dev.dependencies]` (Poetry
  1.2+), not `[dependency-groups]`.
- Build backend is `poetry-core`, not `hatchling`.

**VCS / URL dependencies** use Poetry's specific syntax:
```toml
[tool.poetry.dependencies]
mypackage = { git = "https://github.com/org/mypackage.git", tag = "v1.2.3" }
```

**Optional extras:**
```toml
[tool.poetry.dependencies]
uvicorn = { version = ">=0.29", extras = ["standard"] }
```

### If `pyproject.toml` already exists

- If it already has `[tool.poetry]` sections, update dependencies in place.
- Do NOT touch `[tool.poetry.scripts]`, `[tool.poetry.plugins]`, or other
  existing Poetry config that is unrelated to dependencies.
- If the project uses PEP 621 `[project]` format and the user wants to keep
  it, Poetry 2.x supports that — add dependencies under `[project].dependencies`
  instead and set `build-backend = "poetry.core.masonry.api"`.
- If the project uses a non-Poetry format (e.g., setuptools, hatchling),
  the user needs to decide whether to switch the build backend to
  `poetry-core`. Ask them.

### Consistency check

Verify that the set of package names in `pyproject.toml` dependencies
(either `[tool.poetry.dependencies]` or `[project].dependencies`) matches
`requirements.in` exactly. Package names must not be missing from either side,
though version specifier syntax will naturally differ.

---

## Phase 5 — Generate `poetry.lock`

```bash
poetry lock          # resolves dependencies, writes poetry.lock
poetry install       # installs into .venv from the lockfile
```

If `poetry lock` fails with a resolution error, the dependency set from
Phase 2 has a conflict. Common causes:
- Two packages require incompatible versions of a shared transitive dep
- A VCS dependency pins a version that conflicts with another requirement

In that case, review the error output, adjust version specifiers in
`pyproject.toml`, and re-run `poetry lock`.

Verify:
```bash
poetry run python -c "import <key_packages>"   # spot-check
poetry run pytest                                # if tests exist
```

Cross-check — export Poetry's resolved set and compare to the old
requirements.txt:
```bash
poetry export -f requirements.txt --without-hashes -o reports/poetry_export.txt
diff <(sort requirements.txt.bak) <(sort reports/poetry_export.txt)
```

This diff shows what changed between the old pinned world and the new
resolved world. Review it with the user — large version jumps or missing
packages are worth investigating.

### Troubleshooting: `pkg_resources` / setuptools build failures

When `poetry install` builds a package from source, it uses **build
isolation** — a fresh environment with the latest setuptools. Since
setuptools 82.0.0 (Feb 2026) removed `pkg_resources` entirely, any package
whose `setup.py` does `import pkg_resources` will fail with:

```
ModuleNotFoundError: No module named 'pkg_resources'
```

This is common with older or unmaintained packages.

**Approach 1: Use build constraints (Poetry 2.1+, recommended)**

Poetry 2.1 introduced `[tool.poetry.build-constraints]`, which lets you
constrain the setuptools version used in the isolated build environment on
a per-package basis:

```toml
[tool.poetry.build-constraints]
problematic-package = { setuptools = "<82" }
```

If `<82` is not enough (some very old packages rely on deprecated setuptools
internals removed earlier), try `<65`.

You can constrain multiple packages:
```toml
[tool.poetry.build-constraints]
old-package-a = { setuptools = "<82" }
old-package-b = { setuptools = "<65" }
```

**Approach 2: Use pre-built wheels**

If a wheel exists for the user's platform and Python version, Poetry will
use it and skip the source build entirely. Check PyPI for wheel availability.
If the package author has not published wheels, the user can:
- Build the wheel themselves: `pip wheel <package>==<version> -w ./wheels/`
- Point Poetry at the local wheel directory via a supplemental source in
  `pyproject.toml`:
  ```toml
  [[tool.poetry.source]]
  name = "local-wheels"
  url = "file:///path/to/wheels"
  priority = "supplemental"
  ```

**Approach 3: Pin to a version that ships wheels**

Sometimes a slightly newer or older version of the same package provides
pre-built wheels. Check PyPI's "Download files" page for the package to find
a version with `.whl` files for the user's platform.

**Important: Poetry has NO `--no-build-isolation` flag**

Unlike uv and pip, Poetry does not support disabling build isolation. The
Poetry maintainers consider this the upstream package's responsibility
(the package should declare its build dependencies correctly). If build
constraints and pre-built wheels do not solve the problem, the fallback is
to build the wheel with pip outside Poetry and then install it as described
in Approach 2.

**Diagnosing which packages are affected**

If `poetry install` fails, the error message will name the package that
failed to build. Check its `setup.py` or `setup.cfg` on PyPI/GitHub:
- If it contains `import pkg_resources` or `from pkg_resources import …`
  → build constraint needed
- If it has undeclared build dependencies and no wheel is available,
  build the wheel externally with pip

Present the user with the failing package(s) and the recommended fix before
applying it.

---

## Phase 6 — Migrate Dockerfiles

Search the project for Dockerfiles (`Dockerfile`, `Dockerfile.*`,
`*.dockerfile`, and files inside `docker/` or `.docker/` directories).
If none are found, skip this phase.

For each Dockerfile that contains dependency-installation instructions
(`pip install`, `COPY requirements.txt`, etc.), migrate them to use Poetry.

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

**1. Install Poetry in the image**

Add this near the top of the Dockerfile (after `FROM`):
```dockerfile
ENV POETRY_VERSION=2.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN python -m pip install --no-cache-dir "poetry==$POETRY_VERSION"
```

Setting `POETRY_VIRTUALENVS_IN_PROJECT=true` makes Poetry create the venv
inside the project directory (`.venv/`), which is easier to manage in
Docker and makes the final image more predictable.

**2. Copy dependency files instead of requirements.txt**

Replace:
```dockerfile
COPY requirements.txt .
```
With:
```dockerfile
COPY pyproject.toml poetry.lock ./
```

**3. Replace pip install with poetry install**

Replace:
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
With:
```dockerfile
RUN poetry install --no-interaction --only main --no-root
```

- `--no-interaction` prevents prompts during build.
- `--only main` skips dev dependencies in production images.
- `--no-root` installs only dependencies, not the project itself.
  Omit this flag if the project should be installed too.

If the original Dockerfile installed the project in editable mode
(`pip install -e .`), replace with:
```dockerfile
COPY . .
RUN poetry install --no-interaction --only main
```

**4. Leverage layer caching**

Copy dependency files first (for caching), then copy the full source:
```dockerfile
# -- deps layer (cached unless pyproject.toml or poetry.lock changes) --
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --only main --no-root

# -- app layer --
COPY . .
RUN poetry install --no-interaction --only main
```

**5. Handle `poetry run` vs direct `python`**

Because `POETRY_VIRTUALENVS_IN_PROJECT=true` creates a `.venv/` inside the
project, you can either:
- Set `ENV PATH="/app/.venv/bin:$PATH"` so `python` resolves to the venv
  Python directly (simpler, no `poetry` needed at runtime), or
- Use `CMD ["poetry", "run", "python", "app.py"]`

The first approach is preferred for production images because it means Poetry
itself doesn't need to be in the final stage of a multi-stage build.

**6. Multi-stage build optimization (optional)**

For smaller production images, suggest a multi-stage pattern:
```dockerfile
# --- build stage ---
FROM python:3.11-slim AS builder
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
RUN pip install --no-cache-dir poetry
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --only main --no-root
COPY . .
RUN poetry install --no-interaction --only main

# --- runtime stage ---
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY --from=builder /app .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "app.py"]
```
Only suggest this if the user's existing Dockerfile already uses multi-stage
builds or if they express interest in image size optimization. Don't force it.

### What NOT to change

- Do not touch non-dependency-related Dockerfile instructions (`EXPOSE`,
  `HEALTHCHECK`, `LABEL`, `WORKDIR`, app-specific `COPY`/`RUN`, etc.).
- Do not change the base image unless the user asks.
- Do not restructure multi-stage builds beyond what is needed for the
  dependency swap (unless the user asks for optimization).
- Preserve comments that explain why certain flags or layers exist.

### Show the diff

After making changes, present the user with a before/after comparison of each
modified Dockerfile so they can review the changes.

---

## Phase 7 — CI & deployment notes

Prepare notes for the user (include in `summary.md`):

- **Files to commit:** `pyproject.toml`, `poetry.lock`.
- **CI installation:**
  ```bash
  poetry install --no-interaction --no-root   # install deps only
  # or, for a full install including the project itself:
  poetry install --no-interaction
  ```
- **Reproducible installs:** Use `poetry install --no-interaction` with
  `poetry.lock` committed. Poetry will refuse to install if the lockfile is
  stale — run `poetry lock` to update it.
- **Deploy with requirements.txt:** If the deploy environment cannot use
  Poetry, export in CI:
  ```bash
  poetry export -f requirements.txt --without-hashes -o requirements.txt
  pip install -r requirements.txt
  ```
- **README:** Update install instructions from
  `pip install -r requirements.txt` to `poetry install`.

---

## Phase 8 — Cleanup & summary

After everything is verified, generate `summary.md` in the project root.
This file must be thorough and include:

### 1. All files created and their purpose

| File | Purpose |
|---|---|
| `pyproject.toml` | Authoritative dependency source (Poetry format) |
| `poetry.lock` | Reproducible lockfile |
| `requirements.in` | Human-readable direct runtime deps (reference only) |
| `requirements-dev.in` | Human-readable direct dev deps (reference only) |
| `reports/` | Analysis artifacts (old_requirements.json, direct_imports.json, etc.) |
| `Dockerfile` (modified) | Updated to use `poetry install` instead of `pip install` |

### 2. Dockerfile changes

If Dockerfiles were modified in Phase 6, list each one with a summary of
what changed (e.g., "replaced `pip install -r requirements.txt` with
`poetry install --only main`"). Include the before/after diff or a reference
to it.

### 3. Intermediate files that can be removed

Explain each file's purpose and tell the user they can delete them if not
needed. Do NOT delete them yourself:
- `requirements.in`, `requirements-dev.in` (reference artifacts — Poetry
  does not read these, but they document the dependency decisions made)
- `reports/` directory
- `*.bak` backup files

### 4. Original `requirements.txt` is preserved

Remind the user it is still there for rollback reference.

### 5. Command comparison: old vs new

| Old workflow | New workflow (Poetry) |
|---|---|
| `pip install -r requirements.txt` | `poetry install` |
| `pip freeze > requirements.txt` | `poetry lock` |
| `pip install <new-pkg>` | `poetry add <new-pkg>` |
| `pip install <dev-pkg>` | `poetry add --group dev <new-pkg>` |
| `pip install -e .` | `poetry install` (editable by default) |
| `pip-compile requirements.in` | `poetry lock` |
| `pip install --upgrade <pkg>` | `poetry add <pkg>@latest` |
| activate venv manually | `poetry shell` or `poetry run <cmd>` |

### 6. Direct vs transitive dependency summary

Report how many packages were in the original `requirements.txt`, how many
turned out to be direct, and how many were transitive.

Do NOT remove any intermediate files. Let the user decide what to clean up.
