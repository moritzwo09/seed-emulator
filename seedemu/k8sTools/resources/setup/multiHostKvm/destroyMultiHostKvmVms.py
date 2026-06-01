#!/usr/bin/env python3
"""Python entrypoint for destroyMultiHostKvmVms.sh.

The shell command body lives in the adjacent .sh resource so changes remain
reviewable and can be validated with bash -n. This wrapper keeps the Python
entrypoint used by k8sTools while preserving the script directory seen by bash.
"""
from __future__ import annotations

import sys
from pathlib import Path

from _embeddedShell import runAdjacentShell


def main(argv: list[str] | None = None) -> int:
    """Run this entrypoint with optional argv override for tests."""
    return runAdjacentShell(Path(__file__), list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
