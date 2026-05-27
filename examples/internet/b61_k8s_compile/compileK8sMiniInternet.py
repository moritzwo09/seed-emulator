#!/usr/bin/env python3
"""Compile a small SeedEMU Internet topology to native Kubernetes manifests.

Outputs are written to emulate/output by default:
- k8s.kube-ovn.yaml: Kubernetes namespace, Kube-OVN Vpc/Subnet,
  NetworkAttachmentDefinitions, Deployments.
- images.yaml: image build contexts consumed by the generated running/ stage.
- per-node Docker build contexts and optional base_images/ contexts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "emulate" / "output"
IMAGE_REGISTRY_PREFIX = "seedemu"
NAMESPACE = "seedemu-k8s-b61"


def findRepoRoot(start: Path) -> Path:
    """Find the SeedEMU source tree that contains this example."""
    for candidate in (start, *start.parents):
        if (candidate / "seedemu").is_dir() and (candidate / "setup.py").is_file():
            return candidate
    raise RuntimeError(f"Cannot find SeedEMU repository root above {start}")


REPO_ROOT = findRepoRoot(SCRIPT_DIR)
sys.path = [path for path in sys.path if path != str(REPO_ROOT)]
sys.path.insert(0, str(REPO_ROOT))

from seedemu.compiler import NativeKubernetesCompiler, Platform  # noqa: E402
from seedemu.core import Emulator  # noqa: E402
from seedemu.layers import Base, Ebgp, Ibgp, Ospf, PeerRelationship, Routing  # noqa: E402


def parseArgs() -> argparse.Namespace:
    """Parse compile options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for Kubernetes manifests and image contexts.",
    )
    parser.add_argument(
        "--platform",
        choices=("amd64", "arm64"),
        default="amd64",
        help="Target platform for Docker build contexts.",
    )
    return parser.parse_args()


def buildSmallInternet() -> Emulator:
    """Build a compact Internet topology used by both K8sPre examples."""
    base = Base()
    base.createInternetExchange(100)
    base.createInternetExchange(101)

    as2 = base.createAutonomousSystem(2)
    as2.createNetwork("net0")
    as2.createNetwork("net1")
    as2.createNetwork("net2")
    as2.createRouter("r1").joinNetwork("net0").joinNetwork("ix100")
    as2.createRouter("r2").joinNetwork("net0").joinNetwork("net1")
    as2.createRouter("r3").joinNetwork("net1").joinNetwork("net2")
    as2.createRouter("r4").joinNetwork("net2").joinNetwork("ix101")

    as151 = base.createAutonomousSystem(151)
    as151.createNetwork("net0")
    as151.createRouter("router0").joinNetwork("net0").joinNetwork("ix100")
    as151.createHost("host0").joinNetwork("net0")

    as152 = base.createAutonomousSystem(152)
    as152.createNetwork("net0")
    as152.createRouter("router0").joinNetwork("net0").joinNetwork("ix101")
    as152.createHost("host0").joinNetwork("net0")

    as153 = base.createAutonomousSystem(153)
    as153.createNetwork("net0")
    as153.createRouter("router0").joinNetwork("net0").joinNetwork("ix101")
    as153.createHost("host0").joinNetwork("net0")

    ebgp = Ebgp()
    ebgp.addPrivatePeering(100, 2, 151, abRelationship=PeerRelationship.Provider)
    ebgp.addPrivatePeering(101, 2, 152, abRelationship=PeerRelationship.Provider)
    ebgp.addPrivatePeering(101, 2, 153, abRelationship=PeerRelationship.Provider)
    ebgp.addPrivatePeering(101, 152, 153, abRelationship=PeerRelationship.Peer)

    emu = Emulator()
    emu.addLayer(base)
    emu.addLayer(Routing())
    emu.addLayer(ebgp)
    emu.addLayer(Ibgp())
    emu.addLayer(Ospf())
    emu.render()
    return emu


def main() -> int:
    """Compile the example topology."""
    args = parseArgs()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    platform = Platform.AMD64 if args.platform == "amd64" else Platform.ARM64

    compiler = NativeKubernetesCompiler(
        platform=platform,
        image_registry_prefix=IMAGE_REGISTRY_PREFIX,
        namespace=NAMESPACE,
        cni_type="kube-ovn",
    )
    buildSmallInternet().compile(compiler, str(output_dir), override=True)

    print("Native Kubernetes compilation complete.")
    print(f"output_dir={output_dir}")
    print(f"manifest={output_dir / 'k8s.kube-ovn.yaml'}")
    print(f"images={output_dir / 'images.yaml'}")
    print(f"namespace={NAMESPACE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
