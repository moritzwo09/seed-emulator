#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List


def compose_exec(compose_file: Path, service: str, command: str, timeout: int = 60) -> Dict[str, object]:
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
            "name": "AS150 reaches AS152 through AS2",
            "service": "hnode_150_host_0",
            "command": "ping -c 3 10.152.0.71 >/dev/null",
        },
        {
            "name": "AS171 reaches AS154 customized host",
            "service": "hnode_171_host_0",
            "command": "ping -c 3 10.154.0.129 >/dev/null",
        },
        {
            "name": "AS2 r100 has MPLS/LDP enabled on internal links",
            "service": "brdnode_2_r100",
            "command": "grep -q '^net_100_101$' /mpls_ifaces.txt && grep -q '^net_100_105$' /mpls_ifaces.txt && grep -q 'mpls ldp' /etc/frr/frr.conf",
        },
        {
            "name": "AS2 r101 has MPLS/LDP enabled on internal links",
            "service": "brdnode_2_r101",
            "command": "grep -q '^net_100_101$' /mpls_ifaces.txt && grep -q '^net_101_102$' /mpls_ifaces.txt && grep -q 'mpls ldp' /etc/frr/frr.conf",
        },
        {
            "name": "AS2 r102 has MPLS/LDP enabled on internal links",
            "service": "brdnode_2_r102",
            "command": "grep -q '^net_101_102$' /mpls_ifaces.txt && grep -q 'mpls ldp' /etc/frr/frr.conf",
        },
        {
            "name": "AS2 r105 has MPLS/LDP enabled on internal links",
            "service": "brdnode_2_r105",
            "command": "grep -q '^net_100_105$' /mpls_ifaces.txt && grep -q 'mpls ldp' /etc/frr/frr.conf",
        },
        {
            "name": "AS3 remains a non-MPLS transit AS",
            "service": "brdnode_3_r103",
            "command": "test ! -e /mpls_ifaces.txt",
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
        path = Path(artifact_dir) / "b31-mpls-runtime-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
