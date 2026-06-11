#!/usr/bin/env python3

from __future__ import annotations

from seedemu.testing import ComposeRuntimeTest


def main() -> int:
    test = ComposeRuntimeTest(__file__)

    router = test.require_service(2, "r100")
    speaker = test.require_service(180, "exabgp")
    host150 = test.require_service(150, "host_0")
    host152 = test.require_service(152, "host_0")

    if router:
        test.exec_check("AS2 r100 starts BIRD", router, "pgrep -x bird >/dev/null")
        test.exec_check(
            "AS2 r100 peers with AS180 ExaBGP speaker",
            router,
            "grep -q 'neighbor 10.100.0.180 as 180' /etc/bird/bird.conf",
        )
        test.exec_check(
            "AS2 r100 receives AS180 announcement",
            router,
            "birdc show route 198.51.100.0/24 | grep -q '198.51.100.0/24'",
        )

    if speaker:
        test.exec_check("ExaBGP speaker process is running", speaker, "pgrep -f 'exabgp /etc/exabgp/exabgp.conf' >/dev/null")
        test.exec_check("ExaBGP manual control FIFO is available", speaker, "test -p /run/exabgp/manual.in")
        test.exec_check(
            "ExaBGP config peers with AS2 r100",
            speaker,
            "grep -q 'neighbor 10.100.0.2' /etc/exabgp/exabgp.conf",
        )
        test.exec_check(
            "ExaBGP config enables manual-control process",
            speaker,
            "grep -q 'processes \\[ manual-control \\]' /etc/exabgp/exabgp.conf",
        )
        test.exec_check(
            "ExaBGP config announces static IPv4 route",
            speaker,
            "grep -q 'route 198.51.100.0/24 next-hop self' /etc/exabgp/exabgp.conf",
        )
        test.exec_check("ExaBGP speaker reaches AS2 r100", speaker, "ping -c 3 10.100.0.2 >/dev/null")

    if host150 and host152:
        test.exec_check("B00 mini Internet reachability is preserved", host150, "ping -c 3 {} >/dev/null".format(host152.address))

    test.write_summary("b32-runtime-test.json")
    return test.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
