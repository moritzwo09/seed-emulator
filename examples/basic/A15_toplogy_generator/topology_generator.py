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
from seedemu.utilities import Makers, AutonomousSystemTopologyGenerator


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
    parser = argparse.ArgumentParser(description="Build a transit AS with a generated internal topology.")
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
    parser.add_argument("--ebgp-routers", type=int)
    parser.add_argument("--hosts-per-stub", type=int, default=1)
    parser.add_argument("--internal-routers", type=int, default=4)
    parser.add_argument("--graph-model", default="small_world")
    parser.add_argument("--graph-param", action="append", type=parse_graph_param, default=[])
    parser.add_argument(
        "--ebgp-attach-policy",
        choices=["spread", "round_robin", "random", "degree"],
        default="spread",
    )
    parser.add_argument(
        "--internal-routing",
        choices=["full-mesh", "rr", "route-reflector"],
        default="full-mesh",
        help="iBGP design inside the generated AS.",
    )
    parser.add_argument(
        "--route-reflector",
        help="Router name to use as the route reflector in rr mode. Defaults to a high-degree internal router.",
    )

    args = parser.parse_args()
    args.platform = args.platform or args.legacy_platform or "amd"
    args.graph_params = dict(args.graph_param)
    args.ebgp_routers = args.ebgp_routers or len(args.ixes)
    if args.internal_routing == "route-reflector":
        args.internal_routing = "rr"
    if len(args.ixes) != len(args.stub_asns):
        parser.error("--ixes and --stub-asns must contain the same number of entries")
    if args.ebgp_routers != len(args.ixes):
        parser.error("this example maps one eBGP router to one IX, so --ebgp-routers must match --ixes")
    return args


def resolve_platform(name: str) -> Platform:
    return Platform.AMD64 if name == "amd" else Platform.ARM64


def build_emulator(args: argparse.Namespace):
    emu = Emulator()
    base = Base()
    ebgp = Ebgp()

    for ix in args.ixes:
        base.createInternetExchange(ix)

    topology = AutonomousSystemTopologyGenerator(
        ebgp_router_count=args.ebgp_routers,
        internal_router_count=args.internal_routers,
        graph_model=args.graph_model,
        graph_params=args.graph_params,
        ebgp_attach_policy=args.ebgp_attach_policy,
        seed=args.seed,
    ).generate()

    transit_as = apply_topology(base, topology, args.asn, args.ixes)
    internal_routing = configure_internal_routing(
        transit_as,
        topology,
        mode=args.internal_routing,
        route_reflector=args.route_reflector,
    )

    for stub_asn, ix in zip(args.stub_asns, args.ixes):
        Makers.makeStubAsWithHosts(emu, base, stub_asn, ix, args.hosts_per_stub)
        ebgp.addPrivatePeering(ix, args.asn, stub_asn, PeerRelationship.Provider)

    emu.addLayer(base)
    emu.addLayer(Routing())
    emu.addLayer(ebgp)
    emu.addLayer(Ibgp())
    emu.addLayer(Ospf())
    return emu, topology, internal_routing


def apply_topology(base: Base, topology, asn: int, ixes: List[int]):
    transit_as = base.createAutonomousSystem(asn)
    routers = {name: transit_as.createRouter(name) for name in topology.routers()}

    for ebgp_router, ix in zip(topology.ebgp_routers(), ixes):
        routers[ebgp_router].joinNetwork("ix{}".format(ix))

    for left, right, network in topology.link_networks():
        transit_as.createNetwork(network)
        routers[left].joinNetwork(network)
        routers[right].joinNetwork(network)

    return transit_as


def configure_internal_routing(transit_as, topology, mode: str, route_reflector: str = None) -> Dict[str, Any]:
    mode = mode.lower()
    if mode == "full-mesh":
        return {
            "mode": "full-mesh",
            "route_reflector": None,
            "description": "default SEED Ibgp() full mesh among AS routers",
        }

    if mode != "rr":
        raise ValueError("unsupported internal routing mode: {}".format(mode))

    rr_name = route_reflector or choose_route_reflector(topology)
    if rr_name not in set(topology.routers()):
        raise ValueError("unknown route reflector router: {}".format(rr_name))

    cluster_id = route_reflector_cluster_id(transit_as.getAsn())
    transit_as.createBgpCluster(cluster_id)
    for router_name in topology.routers():
        router = transit_as.getRouter(router_name).joinBgpCluster(cluster_id)
        if router_name == rr_name:
            router.makeRouteReflector()

    return {
        "mode": "rr",
        "route_reflector": rr_name,
        "cluster_id": cluster_id,
        "description": "one generated router is the route reflector; all other AS routers are clients",
    }


def choose_route_reflector(topology) -> str:
    graph = topology.graph()
    candidates = topology.internal_routers() or topology.routers()
    return sorted(candidates, key=lambda router: (-graph.degree(router), router))[0]


def route_reflector_cluster_id(asn: int) -> str:
    return "10.{}.{}.1".format((int(asn) // 256) % 256, int(asn) % 256)


def write_topology_artifacts(topology, output_dir: Path, internal_routing: Dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = topology.to_dict()
    data["internal_routing"] = internal_routing
    with open(output_dir / "topology.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)

    with open(output_dir / "topology.txt", "w", encoding="utf-8") as file:
        file.write(topology.summary())
        file.write("\n")
        file.write("internal routing: {}".format(internal_routing["mode"]))
        if internal_routing.get("route_reflector"):
            file.write(" via {} cluster {}".format(
                internal_routing["route_reflector"],
                internal_routing["cluster_id"],
            ))
        file.write("\n")


def main() -> int:
    args = parse_args()
    emu, topology, internal_routing = build_emulator(args)

    if args.dumpfile:
        emu.dump(args.dumpfile)
        return 0

    if args.render:
        emu.render()

    output_dir = Path(args.output).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    emu.compile(Docker(platform=resolve_platform(args.platform)), str(output_dir), override=args.override)
    write_topology_artifacts(topology, output_dir, internal_routing)
    print(topology.summary())
    print("Internal routing mode: {}".format(internal_routing["mode"]))
    if internal_routing.get("route_reflector"):
        print("Route reflector: {} ({})".format(
            internal_routing["route_reflector"],
            internal_routing["cluster_id"],
        ))
    print("Generated A15 Docker output in {}".format(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
