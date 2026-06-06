#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Sequence


DEFAULT_CHECKS = [
    {
        "name": "show container IPv4 routes",
        "command": "ip -4 route",
        "required": False,
    },
    {
        "name": "resolve example.com over IPv4",
        "command": "getent ahostsv4 example.com | head -n 5",
        "required": True,
    },
    {
        "name": "fetch deterministic Akamai IPv4 address",
        "command": "curl -4 -fsS --connect-timeout 5 --max-time 20 http://23.192.228.80/ >/dev/null",
        "required": True,
    },
    {
        "name": "fetch example.com over IPv4",
        "command": "curl -4 -fsS --connect-timeout 5 --max-time 20 http://example.com/ >/dev/null",
        "required": True,
    },
]


def compose_exec(compose_file: Path, service: str, command: str, timeout: int) -> Dict[str, object]:
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "exec", "-T", service, "sh", "-lc", command],
        cwd=str(compose_file.parent),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "service": service,
        "command": command,
        "exit": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def parse_args() -> argparse.Namespace:
    example_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Manually test whether A03a can reach the real Internet from inside the emulator."
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path(os.environ.get("TEST_RUNNER_COMPOSE_FILE", example_dir / "output" / "docker-compose.yml")),
        help="Path to the generated docker-compose.yml file.",
    )
    parser.add_argument(
        "--service",
        default="hnode_151_web",
        help="Container service to run the outside-reachability checks from.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=os.environ.get("TEST_RUNNER_ARTIFACT_DIR"),
        help="Optional directory for writing real-world-reachability.json.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Timeout in seconds for each docker compose exec check.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="URL",
        help="Additional URL to fetch with curl -4. Can be used more than once.",
    )
    return parser.parse_args()


def build_checks(extra_targets: Sequence[str]) -> List[Dict[str, object]]:
    checks = [dict(check) for check in DEFAULT_CHECKS]
    for target in extra_targets:
        checks.append(
            {
                "name": "fetch custom target {}".format(target),
                "command": "curl -4 -fsS --connect-timeout 5 --max-time 20 {} >/dev/null".format(target),
                "required": True,
            }
        )
    return checks


def main() -> int:
    args = parse_args()
    compose_file = args.compose_file.resolve()
    checks = build_checks(args.target)

    results: List[Dict[str, object]] = []
    for check in checks:
        result = compose_exec(compose_file, args.service, str(check["command"]), args.timeout)
        result["name"] = check["name"]
        result["required"] = check["required"]
        result["status"] = "passed" if result["exit"] == 0 else "failed"
        results.append(result)

    failures = [item["name"] for item in results if item["required"] and item["status"] == "failed"]
    summary = {
        "compose_file": str(compose_file),
        "service": args.service,
        "results": results,
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.artifact_dir:
        path = args.artifact_dir / "real-world-reachability.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
