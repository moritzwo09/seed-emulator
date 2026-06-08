#!/usr/bin/env python3

from __future__ import annotations

from typing import List

from seedemu.testing import ComposeRuntimeTest, ComposeService
from seedemu.testing.runtime import ADDRESS_LABEL, ASN_LABEL, NODE_LABEL


EXPECTED_BORDER_ROUTER_COUNT = 27

BIRD_PROTOCOL_HEALTH_COMMAND = (
    "birdc show protocols | awk '"
    "NR <= 2 { next } "
    "$4 != \"up\" { print; bad=1 } "
    "$2 == \"BGP\" && $NF != \"Established\" { print; bad=1 } "
    "END { exit bad }"
    "'"
)

RR_IBGP_NAME_COMMAND = (
    "birdc show protocols | awk '"
    "NR <= 2 { next } "
    "$2 == \"BGP\" && $1 ~ /^Ibgp/ { seen=1; if (tolower($1) !~ /rr/) { print; bad=1 } } "
    "END { if (!seen) { print \"no iBGP protocols found\"; exit 1 } exit bad }"
    "'"
)


def discover_border_routers(test: ComposeRuntimeTest) -> List[ComposeService]:
    """Return generated brdnode services sorted by AS and node name."""
    services: List[ComposeService] = []

    for name, service in test.compose.get("services", {}).items():
        if not str(name).startswith("brdnode_"):
            continue

        labels = dict(service.get("labels", {}))
        address = str(labels.get(ADDRESS_LABEL, "")).split("/", 1)[0]
        services.append(ComposeService(name=str(name), address=address, labels=labels))

    services.sort(
        key=lambda service: (
            int(str(service.labels.get(ASN_LABEL, "0"))),
            str(service.labels.get(NODE_LABEL, service.name)),
        )
    )
    return services


def service_label(service: ComposeService) -> str:
    """Return a compact AS/node label for a generated service."""
    return "AS{} {}".format(service.labels.get(ASN_LABEL, "?"), service.labels.get(NODE_LABEL, service.name))


def main() -> int:
    test = ComposeRuntimeTest(__file__)

    border_routers = discover_border_routers(test)
    test.structural_check(
        "A62 generates all border router services",
        len(border_routers) == EXPECTED_BORDER_ROUTER_COUNT,
        "found {} brdnode services".format(len(border_routers)),
    )

    for router in border_routers:
        test.exec_check(
            "{} BIRD protocols are healthy".format(service_label(router)),
            router,
            BIRD_PROTOCOL_HEALTH_COMMAND,
            retries=40,
            interval=3,
            timeout=60,
        )

    host150 = test.require_service(150, "host_0")
    host152 = test.require_service(152, "host_0")
    host154 = test.require_service(154, "host_0")
    host160 = test.require_service(160, "host_0")
    host171 = test.require_service(171, "host_0")

    reachability_pairs = [
        ("AS150 reaches AS152 across the RR mini Internet", host150, host152),
        ("AS152 reaches AS150 across the RR mini Internet", host152, host150),
        ("AS150 reaches AS160 through AS3 RR clusters", host150, host160),
        ("AS160 reaches AS150 through AS3 RR clusters", host160, host150),
        ("AS171 reaches AS154 across transit ASes", host171, host154),
        ("AS154 reaches AS171 across transit ASes", host154, host171),
    ]
    for name, source, target in reachability_pairs:
        if source and target:
            test.exec_check(
                name,
                source,
                "ping -c 3 {} >/dev/null".format(target.address),
                retries=40,
                interval=5,
                timeout=45,
            )

    rr_routers = [
        test.require_service(3, "r100"),
        test.require_service(3, "r103"),
        test.require_service(3, "r104"),
        test.require_service(3, "r105"),
        test.require_service(12, "r101"),
        test.require_service(12, "r104"),
    ]
    for router in rr_routers:
        if router:
            test.exec_check(
                "{} RR iBGP protocol names contain rr".format(service_label(router)),
                router,
                RR_IBGP_NAME_COMMAND,
                retries=20,
                interval=3,
                timeout=45,
            )

    test.write_summary("a62-route-reflector-runtime-test.json")
    return test.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
