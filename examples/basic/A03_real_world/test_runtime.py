#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List


def compose_exec(compose_file: Path, service: str, command: str, timeout: int = 45) -> Dict[str, object]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "exec",
            "-T",
            service,
            "sh",
            "-lc",
            command,
        ],
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
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def main() -> int:
    example_dir = Path(
        os.environ.get("TEST_RUNNER_EMULATION_DIR")
        or os.environ.get("EXAMPLE_RUNNER_EXAMPLE_DIR")
        or Path(__file__).parent
    ).resolve()
    compose_file = Path(
        os.environ.get("TEST_RUNNER_COMPOSE_FILE")
        or os.environ.get("EXAMPLE_RUNNER_COMPOSE_FILE")
        or example_dir / "output" / "docker-compose.yml"
    ).resolve()
    artifact_dir = os.environ.get("TEST_RUNNER_ARTIFACT_DIR") or os.environ.get("EXAMPLE_RUNNER_ARTIFACT_DIR")

    checks = [
        {
            "name": "AS151 fetches AS152 web service",
            "service": "hnode_151_web",
            "command": "curl -fsS http://10.152.0.71 >/dev/null",
        },
        {
            "name": "AS152 fetches AS151 web service",
            "service": "hnode_152_web",
            "command": "curl -fsS http://10.151.0.71 >/dev/null",
        },
        {
            "name": "Akamai real-world router has deterministic example prefix",
            "service": "brdnode_20940_rw",
            "command": "grep -q '23.192.228.0/24' /etc/bird/bird.conf",
        },
        {
            "name": "Akamai real-world router has service-network route setup",
            "service": "brdnode_20940_rw",
            "command": "test -s /rw_configure_script && grep -q 'ip route add default' /rw_configure_script",
        },
    ]

    results: List[Dict[str, object]] = []
    for check in checks:
        result = compose_exec(compose_file, str(check["service"]), str(check["command"]))
        result["name"] = check["name"]
        result["status"] = "passed" if result["exit"] == 0 else "failed"
        results.append(result)

    summary = {
        "compose_file": str(compose_file),
        "results": results,
        "failures": [item["name"] for item in results if item["status"] == "failed"],
    }

    print(json.dumps(summary, indent=2, sort_keys=True))

    if artifact_dir:
        path = Path(artifact_dir) / "a03-real-world-runtime-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
