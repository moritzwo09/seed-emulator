#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from seedemu.compiler import Docker, Platform
from seedemu.core import Emulator
from seedemu.layers import Base, Ebgp, Ibgp, Ospf, PeerRelationship, Routing
from seedemu.utilities import Makers, TransitAsTopologyGenerator


DEFAULT_IXES = [100, 101, 102]
DEFAULT_STUB_ASNS = [150, 151, 152]


def parse_graph_param(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("graph parameters must use KEY=VALUE")

    key, raw_value = value.split("=", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if not key:
        raise argparse.ArgumentTypeError("graph parameter key cannot be empty")

    if raw_value.lower() in {"true", "false"}:
        return key, raw_value.lower() == "true"

    try:
        return key, int(raw_value)
    except ValueError:
        pass

    try:
        return key, float(raw_value)
    except ValueError:
        return key, raw_value


def parse_csv_ints(value: str) -> List[int]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise argparse.ArgumentTypeError("value must contain at least one integer")
    return [int(item) for item in items]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AS2 transit network with a generated internal topology.")
    parser.add_argument("legacy_platform", nargs="?", choices=["amd", "arm"])
    parser.add_argument("--platform", choices=["amd", "arm"])
    parser.add_argument("--output", default=str(SCRIPT_DIR / "output"))
    parser.add_argument("--dumpfile")
    parser.add_argument("--override", dest="override", action="store_true", default=True)
    parser.add_argument("--no-override", dest="override", action="store_false")
    parser.add_argument("--skip-render", dest="render", action="store_false", default=True)

    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--asn", type=int, default=2)
    parser.add_argument("--ixes", type=parse_csv_ints, default=DEFAULT_IXES)
    parser.add_argument("--stub-asns", type=parse_csv_ints, default=DEFAULT_STUB_ASNS)
    parser.add_argument("--hosts-per-stub", type=int, default=1)
    parser.add_argument("--internal-routers", type=int, default=4)
    parser.add_argument("--graph-model", default="small_world")
    parser.add_argument("--graph-param", action="append", type=parse_graph_param, default=[])
    parser.add_argument(
        "--edge-attach-policy",
        choices=["spread", "round_robin", "random", "degree"],
        default="spread",
    )

    args = parser.parse_args()
    args.platform = args.platform or args.legacy_platform or "amd"
    args.graph_params = dict(args.graph_param)
    if len(args.ixes) != len(args.stub_asns):
        parser.error("--ixes and --stub-asns must contain the same number of entries")
    return args


def resolve_platform(name: str) -> Platform:
    return Platform.AMD64 if name == "amd" else Platform.ARM64


def build_emulator(args: argparse.Namespace):
    emu = Emulator()
    base = Base()
    ebgp = Ebgp()

    for ix in args.ixes:
        base.createInternetExchange(ix)

    topology = TransitAsTopologyGenerator(
        asn=args.asn,
        ixes=args.ixes,
        internal_router_count=args.internal_routers,
        graph_model=args.graph_model,
        graph_params=args.graph_params,
        edge_attach_policy=args.edge_attach_policy,
        seed=args.seed,
    ).generate()
    topology.apply_to(base)

    for stub_asn, ix in zip(args.stub_asns, args.ixes):
        Makers.makeStubAsWithHosts(emu, base, stub_asn, ix, args.hosts_per_stub)
        ebgp.addPrivatePeering(ix, args.asn, stub_asn, PeerRelationship.Provider)

    emu.addLayer(base)
    emu.addLayer(Routing())
    emu.addLayer(ebgp)
    emu.addLayer(Ibgp())
    emu.addLayer(Ospf())
    return emu, topology


def write_topology_artifacts(topology, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "topology.json", "w", encoding="utf-8") as file:
        json.dump(topology.to_dict(), file, indent=2, sort_keys=True)

    with open(output_dir / "topology.txt", "w", encoding="utf-8") as file:
        file.write(topology.summary())
        file.write("\n")


def main() -> int:
    args = parse_args()
    emu, topology = build_emulator(args)

    if args.dumpfile:
        emu.dump(args.dumpfile)
        return 0

    if args.render:
        emu.render()

    output_dir = Path(args.output).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    emu.compile(Docker(platform=resolve_platform(args.platform)), str(output_dir), override=args.override)
    write_topology_artifacts(topology, output_dir)
    print(topology.summary())
    print("Generated A15 Docker output in {}".format(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
