"""Build hook: compile the Vite frontend into the package before packaging.

Packaging metadata lives entirely in pyproject.toml. This file only exists so
that `python -m build` / `pip install .` run `npm run build` and pick up the
generated bundle as package data (hexgame.server / static/overview/**).

Skip the frontend build with HEXGAME_SKIP_FRONTEND_BUILD=1 (useful for fast
editable installs once the bundle already exists, and for the Docker runtime
stage which has no Node and copies a pre-built bundle in).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"
BUNDLE_INDEX = ROOT / "src" / "hexgame" / "server" / "static" / "overview" / "index.html"


def build_frontend() -> None:
    if os.environ.get("HEXGAME_SKIP_FRONTEND_BUILD"):
        return
    if not (FRONTEND_DIR / "package.json").exists():
        # Building from an sdist: frontend/ was pruned and the bundle is
        # already vendored in the sdist — nothing to do.
        return
    npm = shutil.which("npm")
    if npm is None:
        if BUNDLE_INDEX.exists():
            print("hexgame: npm not found; reusing existing frontend bundle.", file=sys.stderr)
            return
        raise SystemExit(
            "npm is required to build the overview frontend and was not found on PATH.\n"
            "Install Node.js, or pre-build it with: cd frontend && npm ci && npm run build"
        )
    print("hexgame: building frontend bundle (npm ci && npm run build)...", file=sys.stderr)
    subprocess.run([npm, "ci"], cwd=FRONTEND_DIR, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)


class build_py(_build_py):
    def run(self) -> None:
        build_frontend()  # must happen before sources/package_data are collected
        super().run()


setup(cmdclass={"build_py": build_py})
