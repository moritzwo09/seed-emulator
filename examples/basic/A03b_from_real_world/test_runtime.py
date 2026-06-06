#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List


def compose_exec(compose_file: Path, service: str, command: str, timeout: int = 45) -> Dict[str, object]:
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
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def find_openvpn_outputs(output_dir: Path) -> List[str]:
    matches = []
    for dockerfile in output_dir.glob("*/Dockerfile"):
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        if "/ovpn-server.conf" in text and "/ovpn_startup" in text:
            matches.append(dockerfile.parent.name)
    return sorted(matches)


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
            "command": "curl -fsS http://10.152.0.79 >/dev/null",
        },
        {
            "name": "AS152 fetches AS151 web service",
            "service": "hnode_152_web",
            "command": "curl -fsS http://10.151.0.79 >/dev/null",
        },
    ]

    results: List[Dict[str, object]] = []
    for check in checks:
        result = compose_exec(compose_file, str(check["service"]), str(check["command"]))
        result["name"] = check["name"]
        result["status"] = "passed" if result["exit"] == 0 else "failed"
        results.append(result)

    openvpn_outputs = find_openvpn_outputs(compose_file.parent)
    results.append(
        {
            "name": "OpenVPN bridge nodes are generated",
            "service": "<output>",
            "command": "scan generated Dockerfiles for /ovpn-server.conf and /ovpn_startup",
            "exit": 0 if len(openvpn_outputs) >= 2 else 1,
            "stdout": ", ".join(openvpn_outputs),
            "stderr": "",
            "status": "passed" if len(openvpn_outputs) >= 2 else "failed",
        }
    )

    real_world_outputs = [
        path.parent.name
        for path in compose_file.parent.glob("*/Dockerfile")
        if "/rw_configure_script" in path.read_text(encoding="utf-8", errors="replace")
    ]
    results.append(
        {
            "name": "Real-world router is absent from from-real-world example",
            "service": "<output>",
            "command": "scan generated Dockerfiles for /rw_configure_script",
            "exit": 0 if not real_world_outputs else 1,
            "stdout": ", ".join(sorted(real_world_outputs)),
            "stderr": "",
            "status": "passed" if not real_world_outputs else "failed",
        }
    )

    summary = {
        "compose_file": str(compose_file),
        "results": results,
        "failures": [item["name"] for item in results if item["status"] == "failed"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if artifact_dir:
        path = Path(artifact_dir) / "a03b-runtime-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
