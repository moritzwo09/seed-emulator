#!/usr/bin/env python3
"""Validate SeedEMU native Kubernetes source files before PR build checks.

Inputs:
- repository source tree, defaulting to the current checkout.

Outputs:
- console diagnostics only.

Side effects:
- none; Python files are compiled to syntax trees in memory and shell scripts
  are checked with bash -n.

Expected context:
- GitHub-hosted or local developer machine with Python 3.10+ and bash.
"""
from __future__ import annotations

import argparse
import py_compile
import subprocess
import sys
from pathlib import Path

import yaml


SOURCE_ROOTS = (
    Path(".github/workflows/k8s-check.yaml"),
    Path("MANIFEST.in"),
    Path("setup.py"),
    Path("seedemu/compiler/kubernetes.py"),
    Path("seedemu/compiler/__init__.py"),
    Path("seedemu/k8sTools"),
    Path("examples/internet/b61_k8s_compile"),
    Path("tests/k8s"),
)
GENERATED_EXAMPLE_PREFIXES = (
    "examples/internet/b61_k8s_compile/output/",
    "examples/internet/b61_k8s_compile/configK3s.yaml",
    "examples/internet/b61_k8s_compile/configK3sTemplate.yaml",
    "examples/internet/b61_k8s_compile/kubeconfig.yaml",
)
TEXT_SUFFIXES = {".py", ".sh", ".yaml", ".yml", ".md", ".in"}
FORBIDDEN_TEXT = (str(Path("/home") / "lxl") + "/", str(Path("/home") / "lxl"))


def parseArgs() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="SeedEMU repository root.",
    )
    return parser.parse_args()


def relativePath(path: Path, repo_root: Path) -> str:
    """Return a POSIX relative path used for matching and diagnostics.

    Args:
        path: Absolute or repository-relative path.
        repo_root: Repository root directory.
    """
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def isGeneratedExamplePath(path: Path, repo_root: Path) -> bool:
    """Return true for generated B61 setup/running/output artifacts.

    Args:
        path: Source file candidate.
        repo_root: Repository root directory.
    """
    rel = relativePath(path, repo_root)
    return any(rel.startswith(prefix) for prefix in GENERATED_EXAMPLE_PREFIXES)


def isIgnoredPath(path: Path, repo_root: Path) -> bool:
    """Return true for cache/build files that should not be source-checked.

    Args:
        path: Source file candidate.
        repo_root: Repository root directory.
    """
    parts = path.relative_to(repo_root).parts
    if "__pycache__" in parts:
        return True
    if path.name == "codex_worklog.md":
        return True
    return isGeneratedExamplePath(path, repo_root)


def iterSourceFiles(repo_root: Path) -> list[Path]:
    """Return source files under K8s-related paths.

    Args:
        repo_root: Repository root directory.
    """
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        candidate = repo_root / root
        if not candidate.exists():
            continue
        if candidate.is_file():
            files.append(candidate)
            continue
        files.extend(path for path in candidate.rglob("*") if path.is_file())
    return sorted(path for path in files if not isIgnoredPath(path, repo_root))


def validatePythonSyntax(paths: list[Path]) -> None:
    """Compile Python source files without importing them.

    Args:
        paths: Python files to validate.
    """
    for path in paths:
        py_compile.compile(str(path), doraise=True)


def validateShellSyntax(paths: list[Path]) -> None:
    """Run bash -n on shell scripts.

    Args:
        paths: Shell script paths to validate.
    """
    for path in paths:
        subprocess.run(["bash", "-n", str(path)], check=True)


def validateYamlSyntax(paths: list[Path]) -> None:
    """Parse YAML files without applying YAML 1.1 scalar coercions.

    Args:
        paths: YAML files to validate.
    """
    for path in paths:
        list(yaml.compose_all(path.read_text(encoding="utf-8")))


def validateNoHostLocalArtifacts(paths: list[Path], repo_root: Path) -> None:
    """Reject known host-local paths and checked-in image tarballs.

    Args:
        paths: K8s-related source files.
        repo_root: Repository root directory.
    """
    failures: list[str] = []
    for path in paths:
        rel = relativePath(path, repo_root)
        if path.suffix == ".tar":
            failures.append(f"{rel}: image tarball must not be checked in")
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"Makefile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in FORBIDDEN_TEXT:
            if token in text:
                failures.append(f"{rel}: contains host-local path {token}")
    if failures:
        raise SystemExit("\n".join(failures))


def main() -> int:
    """Run static validation for native K8s sources."""
    args = parseArgs()
    repo_root = args.repo_root.expanduser().resolve()
    files = iterSourceFiles(repo_root)
    python_files = [path for path in files if path.suffix == ".py"]
    shell_files = [path for path in files if path.suffix == ".sh"]
    yaml_files = [path for path in files if path.suffix in {".yaml", ".yml"}]

    validatePythonSyntax(python_files)
    validateShellSyntax(shell_files)
    validateYamlSyntax(yaml_files)
    validateNoHostLocalArtifacts(files, repo_root)

    print(
        "Validated "
        f"{len(python_files)} Python files, "
        f"{len(shell_files)} shell scripts, "
        f"and {len(yaml_files)} YAML files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
