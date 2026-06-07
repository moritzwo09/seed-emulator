#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List

import yaml


ASN_LABEL = "org.seedsecuritylabs.seedemu.meta.asn"
NODE_LABEL = "org.seedsecuritylabs.seedemu.meta.nodename"
ADDRESS_LABEL = "org.seedsecuritylabs.seedemu.meta.net.0.address"


def load_compose(compose_file: Path) -> Dict[str, object]:
    with compose_file.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def find_service(compose: Dict[str, object], asn: int, node: str) -> Dict[str, str]:
    for name, service in compose.get("services", {}).items():
        labels = service.get("labels", {})
        if str(labels.get(ASN_LABEL)) == str(asn) and labels.get(NODE_LABEL) == node:
            address = str(labels.get(ADDRESS_LABEL, "")).split("/", 1)[0]
            return {"name": str(name), "address": address}
    raise KeyError("service for AS{} node {} not found".format(asn, node))


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


def check(compose_file: Path, name: str, service: str, command: str, retries: int = 20, interval: int = 3) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for attempt in range(1, retries + 1):
        result = compose_exec(compose_file, service, command)
        if result["exit"] == 0:
            break
        if attempt < retries:
            time.sleep(interval)
    result["name"] = name
    result["attempts"] = attempt
    result["status"] = "passed" if result["exit"] == 0 else "failed"
    return result


def structural_check(name: str, passed: bool, message: str) -> Dict[str, object]:
    return {
        "name": name,
        "service": "<output>",
        "command": "inspect generated docker-compose.yml",
        "exit": 0 if passed else 1,
        "stdout": message,
        "stderr": "",
        "status": "passed" if passed else "failed",
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

    compose = load_compose(compose_file)
    results: List[Dict[str, object]] = []

    required_nodes = [
        (151, "web-2"),
        (154, "web"),
        (154, "router0"),
        (154, "router1"),
        (154, "router2"),
        (102, "ix102"),
    ]

    discovered: Dict[str, Dict[str, str]] = {}
    for asn, node in required_nodes:
        try:
            discovered["{}:{}".format(asn, node)] = find_service(compose, asn, node)
            results.append(structural_check("AS{} {} is generated".format(asn, node), True, "found"))
        except KeyError as exc:
            results.append(structural_check("AS{} {} is generated".format(asn, node), False, str(exc)))

    web151 = discovered.get("151:web-2")
    web154 = discovered.get("154:web")
    if web151 and web154:
        results.extend(
            [
                check(compose_file, "AS151 added web service is ready", web151["name"], "curl -fsS http://127.0.0.1 >/dev/null"),
                check(compose_file, "AS154 added web service is ready", web154["name"], "curl -fsS http://127.0.0.1 >/dev/null"),
                check(
                    compose_file,
                    "AS154 reaches added AS151 web service",
                    web154["name"],
                    "curl -fsS http://{} >/dev/null".format(web151["address"]),
                ),
                check(
                    compose_file,
                    "AS151 added web service reaches AS154",
                    web151["name"],
                    "curl -fsS http://{} >/dev/null".format(web154["address"]),
                ),
            ]
        )

    summary = {
        "compose_file": str(compose_file),
        "results": results,
        "failures": [item["name"] for item in results if item["status"] == "failed"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if artifact_dir:
        path = Path(artifact_dir) / "a05-components-runtime-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
