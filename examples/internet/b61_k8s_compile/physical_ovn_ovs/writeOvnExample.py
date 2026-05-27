#!/usr/bin/env python3
"""Generate the physical-node + Kube-OVN/OVS K8sPre example.

The script writes setup/ and running/ directories. It does not install K3s,
install Kube-OVN, download image caches, build images, or deploy workloads.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
SUITE_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SCRIPT_DIR / "configK3sOvn.yaml"


def findRepoRoot(start: Path) -> Path:
    """Find the SeedEMU source tree that contains this example."""
    for candidate in (start, *start.parents):
        if (candidate / "seedemu").is_dir() and (candidate / "setup.py").is_file():
            return candidate
    raise RuntimeError(f"Cannot find SeedEMU repository root above {start}")


REPO_ROOT = findRepoRoot(SCRIPT_DIR)
sys.path = [path for path in sys.path if path != str(REPO_ROOT)]
sys.path.insert(0, str(REPO_ROOT))

from seedemu.k8spre import K8sPre  # noqa: E402


def portablePath(path: Path, base_dir: Path) -> str:
    """Return a relative path when the target is near the generated YAML."""
    path = path.expanduser().resolve()
    base_dir = base_dir.expanduser().resolve()
    common = Path(os.path.commonpath([str(path), str(base_dir)]))
    if common == Path(path.anchor):
        return str(path)
    relative = Path(os.path.relpath(path, start=base_dir))
    if len(relative.parts) <= 8:
        return relative.as_posix()
    return str(path)


def writeSeedemuDockerDir(config_path: Path) -> None:
    """Pin generated YAML to this source tree's Docker build contexts."""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    seedemu = data.get("seedemu")
    if seedemu is None:
        seedemu = {}
        data["seedemu"] = seedemu
    if not isinstance(seedemu, dict):
        raise ValueError(f"{config_path}: seedemu must be a mapping")
    seedemu["dockerImagesDir"] = portablePath(
        REPO_ROOT / "docker_images" / "multiarch",
        config_path.parent,
    )
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def parseArgs() -> argparse.Namespace:
    """Parse example generation options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=SCRIPT_DIR,
        help="Directory that will receive setup/ and running/.",
    )
    parser.add_argument(
        "--compile-output",
        type=Path,
        default=SUITE_DIR / "emulate" / "output",
        help="Native Kubernetes compiler output consumed by running/.",
    )
    return parser.parse_args()


def writeOvnExample(output_root: Path, compile_output: Path) -> None:
    """Write setup/running scripts for the physical-node Kube-OVN/OVS flow."""
    k8spre = K8sPre()
    setup_dir = k8spre.writePhysicalNodeScripts(
        output_root,
        config=CONFIG_PATH,
        connection="ovn",
        overwrite=True,
    )
    writeSeedemuDockerDir(setup_dir / "configK3s.yaml")
    setup_dir = k8spre.writeK3sBuildScripts(output_root, overwrite=True)
    running_dir = k8spre.writeRunningScripts(
        output_root,
        output_dir=compile_output,
        overwrite=True,
    )

    print("Physical-node + Kube-OVN/OVS example generated.")
    print(f"setup_dir={setup_dir}")
    print(f"running_dir={running_dir}")
    print("Manual full-flow commands:")
    print(f"  cd {SUITE_DIR}")
    print("  python3 ./compileK8sMiniInternet.py")
    print(f"  cd {setup_dir}")
    print("  bash ./preparePhysicalNodes.sh ./configK3s.yaml")
    print("  bash ./buildK3sCluster.sh")
    print("  bash ./ovn/validateKubeOvnFabric.sh ./configK3s.yaml")
    print(f"  cd {running_dir}")
    print("  make preflight")
    print("  make build")
    print("  make up")


def main() -> int:
    """CLI entrypoint."""
    args = parseArgs()
    writeOvnExample(
        args.output_root.expanduser().resolve(),
        args.compile_output.expanduser().resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
