"""Run adjacent shell resources for k8sTools Python entrypoints."""
from __future__ import annotations

import subprocess
from pathlib import Path


def runAdjacentShell(script_path: Path, argv: list[str]) -> int:
    """Execute the .sh file next to a Python entrypoint.

    Args:
        script_path: Path to the Python entrypoint being executed.
        argv: Arguments passed by the caller.
    """
    shell_path = script_path.resolve().with_suffix(".sh")
    if not shell_path.is_file():
        raise FileNotFoundError(f"Missing shell resource: {shell_path}")
    completed = subprocess.run(["bash", str(shell_path), *argv])
    return int(completed.returncode)
