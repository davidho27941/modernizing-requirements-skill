#!/usr/bin/env python3
"""
scan_imports.py — AST-based import scanner for Python projects.

Walks a project tree, parses every .py file via the `ast` module, and extracts
top-level import names. Then maps those import names to their PyPI distribution
names using a curated lookup table + importlib.metadata as a fallback.

Output: a sorted list of distribution names that represent the project's
**direct** dependencies (as opposed to transitive ones pulled in by pip freeze).

Usage
-----
    python scan_imports.py [PROJECT_ROOT] [--json] [--first-party PKG1,PKG2]

If PROJECT_ROOT is omitted, the current directory is used.

Flags
    --json                  Print results as JSON instead of plain text.
    --first-party PKG1,PKG2 Comma-separated list of first-party package names
                            to exclude (e.g. your own project's packages).
    --include-dev           Also tag likely dev-only imports (pytest, mypy, …).
    --show-unknown          Print imports that could not be resolved separately.
"""

from __future__ import annotations

import ast
import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# 1.  Import-name  →  PyPI distribution name
#
# Python's import system does not enforce any naming convention between the
# module you `import` and the package you `pip install`.  This table covers
# the most common mismatches so the scanner can work without a live env.
# ---------------------------------------------------------------------------

IMPORT_TO_DIST: dict[str, str] = {
    # --- Imaging / Vision ---
    "PIL": "pillow",
    "cv2": "opencv-python",
    "skimage": "scikit-image",
    "fitz": "PyMuPDF",

    # --- Data science / ML ---
    "sklearn": "scikit-learn",
    "xgb": "xgboost",
    "lgb": "lightgbm",
    "tf": "tensorflow",
    "paddle": "paddlepaddle",

    # --- Serialization / Parsing ---
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "toml": "tomli",
    "ujson": "ujson",
    "rapidjson": "python-rapidjson",
    "msgpack": "msgpack",

    # --- Web / Networking ---
    "websocket": "websocket-client",
    "socks": "PySocks",
    "dns": "dnspython",
    "whois": "python-whois",
    "jwt": "PyJWT",
    "jose": "python-jose",
    "multipart": "python-multipart",
    "oauthlib": "oauthlib",

    # --- Crypto / Security ---
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodome",
    "nacl": "PyNaCl",
    "OpenSSL": "pyOpenSSL",
    "certifi": "certifi",
    "passlib": "passlib",
    "bcrypt": "bcrypt",

    # --- Database / Storage ---
    "pymongo": "pymongo",
    "bson": "pymongo",
    "redis": "redis",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "mysql": "mysql-connector-python",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "alembic",
    "botocore": "botocore",
    "boto3": "boto3",

    # --- Document / Office ---
    "docx": "python-docx",
    "pptx": "python-pptx",
    "openpyxl": "openpyxl",
    "xlrd": "xlrd",
    "xlsxwriter": "XlsxWriter",
    "reportlab": "reportlab",
    "weasyprint": "weasyprint",

    # --- CLI / System ---
    "dotenv": "python-dotenv",
    "click": "click",
    "typer": "typer",
    "rich": "rich",
    "tqdm": "tqdm",
    "colorama": "colorama",
    "psutil": "psutil",

    # --- Date / Time ---
    "dateutil": "python-dateutil",
    "pytz": "pytz",
    "arrow": "arrow",
    "pendulum": "pendulum",

    # --- Messaging / Async ---
    "zmq": "pyzmq",
    "celery": "celery",
    "kombu": "kombu",
    "pika": "pika",

    # --- Encoding / Compression ---
    "chardet": "chardet",
    "charset_normalizer": "charset-normalizer",

    # --- Testing / Dev tools (flagged as dev) ---
    "pytest": "pytest",
    "mypy": "mypy",
    "ruff": "ruff",
    "black": "black",
    "isort": "isort",
    "flake8": "flake8",
    "pylint": "pylint",
    "coverage": "coverage",
    "hypothesis": "hypothesis",
    "factory": "factory-boy",
    "faker": "faker",
    "responses": "responses",
    "freezegun": "freezegun",

    # --- Science ---
    "Bio": "biopython",
    "scipy": "scipy",
    "statsmodels": "statsmodels",
    "sympy": "sympy",

    # --- Config / Env ---
    "decouple": "python-decouple",
    "dynaconf": "dynaconf",
    "pydantic_settings": "pydantic-settings",
    "envparse": "envparse",

    # --- Misc ---
    "attr": "attrs",
    "attrs": "attrs",
    "git": "GitPython",
    "magic": "python-magic",
    "serial": "pyserial",
    "usb": "pyusb",
    "ldap": "python-ldap",
    "Levenshtein": "python-Levenshtein",
    "rapidfuzz": "rapidfuzz",
    "enchant": "pyenchant",
    "wx": "wxPython",
    "Xlib": "python-xlib",
    "pkg_resources": "setuptools",
    "setuptools": "setuptools",

    # --- Google Cloud (top-level) ---
    "google": "google-api-core",
}

# Imports that are almost certainly dev-only dependencies.
DEV_IMPORTS: set[str] = {
    "pytest", "mypy", "ruff", "black", "isort", "flake8", "pylint",
    "coverage", "hypothesis", "factory", "faker", "responses",
    "freezegun", "nox", "tox", "pre_commit", "sphinx",
    "pytest_cov", "pytest_mock", "pytest_asyncio", "pytest_xdist",
}

# Directories to skip when walking the project tree.
SKIP_DIRS: set[str] = {
    ".venv", "venv", "env", ".env",
    "build", "dist", ".tox", ".nox",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "site-packages", "node_modules",
    ".git", ".hg", ".svn",
    "egg-info",
}


class ScanResult(NamedTuple):
    direct: set[str]
    dev: set[str]
    unknown: set[str]
    first_party: set[str]
    stdlib: set[str]
    errors: list[str]


def _get_stdlib_names() -> set[str]:
    """Return the set of standard-library top-level module names."""
    if sys.version_info >= (3, 10):
        return set(sys.stdlib_module_names)  # type: ignore[attr-defined]
    # Fallback for 3.9 — use a known list (not exhaustive but good enough).
    import pkgutil
    return {m.name for m in pkgutil.iter_modules() if m.ispkg is False} | {
        "os", "sys", "re", "json", "math", "datetime", "pathlib",
        "collections", "itertools", "functools", "typing", "abc",
        "io", "logging", "unittest", "http", "urllib", "email",
        "html", "xml", "csv", "sqlite3", "subprocess", "shutil",
        "tempfile", "glob", "fnmatch", "hashlib", "hmac", "secrets",
        "socket", "ssl", "select", "signal", "threading", "multiprocessing",
        "concurrent", "asyncio", "contextvars", "dataclasses", "enum",
        "copy", "pprint", "textwrap", "string", "struct", "codecs",
        "base64", "binascii", "pickle", "shelve", "marshal",
        "warnings", "traceback", "inspect", "dis", "gc", "weakref",
        "types", "importlib", "pkgutil", "zipimport",
        "argparse", "configparser", "tomllib",
        "ctypes", "platform", "sysconfig",
        "pdb", "profile", "timeit", "trace",
        "decimal", "fractions", "random", "statistics",
        "operator", "array", "queue", "heapq", "bisect",
        "mmap", "fcntl", "termios", "tty", "pty",
        "token", "tokenize", "keyword", "ast", "symtable", "compileall",
        "zipfile", "tarfile", "gzip", "bz2", "lzma", "zlib",
        "difflib", "filecmp", "fileinput",
        "calendar", "time", "locale", "gettext",
        "turtle", "tkinter",
        "test", "doctest",
        "_thread", "posixpath", "ntpath", "posix", "nt",
    }


def top_level_imports(path: Path) -> tuple[set[str], str | None]:
    """Parse a single .py file and return its top-level import names."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return set(), f"SyntaxError in {path}: {exc}"

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names, None


def _should_skip(path: Path) -> bool:
    """Return True if this path should be skipped."""
    return any(part in SKIP_DIRS for part in path.parts) or any(
        part.endswith(".egg-info") for part in path.parts
    )


def scan(
    root: Path,
    first_party: set[str] | None = None,
    include_dev: bool = False,
) -> ScanResult:
    """
    Walk the project tree and classify every imported name.

    Returns a ScanResult with direct deps, dev deps, unknowns, etc.
    """
    stdlib = _get_stdlib_names()
    first_party = first_party or set()
    all_imports: set[str] = set()
    errors: list[str] = []

    for py_file in root.rglob("*.py"):
        if _should_skip(py_file):
            continue
        names, err = top_level_imports(py_file)
        all_imports |= names
        if err:
            errors.append(err)

    # Also scan for dynamic imports as a warning.
    # (We just flag them; we can't resolve them automatically.)
    dynamic_patterns = ("import_module", "__import__")
    for py_file in root.rglob("*.py"):
        if _should_skip(py_file):
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in dynamic_patterns:
            if pat in text:
                errors.append(
                    f"Possible dynamic import in {py_file} (found '{pat}'). "
                    "Review manually — AST scanning cannot catch these."
                )

    # Classify
    external = all_imports - stdlib - first_party
    direct: set[str] = set()
    dev: set[str] = set()
    unknown: set[str] = set()

    # Try importlib.metadata if available
    dist_mapping: dict[str, list[str]] = {}
    try:
        from importlib.metadata import packages_distributions
        dist_mapping = packages_distributions()
    except ImportError:
        pass

    for name in sorted(external):
        # Resolve to distribution name
        dist_name: str | None = None
        if name in IMPORT_TO_DIST:
            dist_name = IMPORT_TO_DIST[name]
        elif name in dist_mapping:
            dist_name = dist_mapping[name][0]
        else:
            dist_name = None

        is_dev = name in DEV_IMPORTS

        if dist_name:
            if is_dev and include_dev:
                dev.add(dist_name)
            elif is_dev:
                dev.add(dist_name)
            else:
                direct.add(dist_name)
        else:
            unknown.add(name)

    return ScanResult(
        direct=direct,
        dev=dev,
        unknown=unknown,
        first_party=first_party,
        stdlib=stdlib & all_imports,
        errors=errors,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan Python project imports and resolve to distribution names."
    )
    parser.add_argument(
        "root", nargs="?", default=".",
        help="Project root directory (default: current dir)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Output as JSON instead of plain text",
    )
    parser.add_argument(
        "--first-party", default="",
        help="Comma-separated first-party package names to exclude",
    )
    parser.add_argument(
        "--include-dev", action="store_true",
        help="Separately list dev-only dependencies",
    )
    parser.add_argument(
        "--show-unknown", action="store_true",
        help="Show imports that could not be mapped to a distribution",
    )
    args = parser.parse_args()

    first_party = {n.strip() for n in args.first_party.split(",") if n.strip()}
    result = scan(Path(args.root), first_party=first_party, include_dev=args.include_dev)

    if args.as_json:
        data = {
            "direct": sorted(result.direct),
            "dev": sorted(result.dev),
            "unknown": sorted(result.unknown) if args.show_unknown else [],
            "errors": result.errors,
        }
        print(json.dumps(data, indent=2))
    else:
        print("# Direct dependencies")
        for name in sorted(result.direct):
            print(f"  {name}")

        if result.dev:
            print("\n# Dev dependencies")
            for name in sorted(result.dev):
                print(f"  {name}")

        if args.show_unknown and result.unknown:
            print("\n# Unknown (could not resolve — review manually)")
            for name in sorted(result.unknown):
                print(f"  {name}")

        if result.errors:
            print(f"\n# Warnings ({len(result.errors)})")
            for err in result.errors:
                print(f"  - {err}")


if __name__ == "__main__":
    main()
