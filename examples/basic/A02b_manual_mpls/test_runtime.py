#!/usr/bin/env python3

from __future__ import annotations

from seedemu.testing import ComposeRuntimeTest


def main() -> int:
    test = ComposeRuntimeTest(__file__)

    web151 = test.require_service(151, "web")
    web152 = test.require_service(152, "web")
    web153 = test.require_service(153, "web")
    e1 = test.require_service(2, "e1")
    e2 = test.require_service(2, "e2")
    e3 = test.require_service(2, "e3")
    r1 = test.require_service(2, "r1")
    r2 = test.require_service(2, "r2")
    r3 = test.require_service(2, "r3")

    if web151 and web152:
        test.exec_check("AS151 fetches AS152 web service", web151, "curl -fsS http://{} >/dev/null".format(web152.address))
        test.exec_check("AS152 reaches AS151 by ICMP", web152, "ping -c 3 {} >/dev/null".format(web151.address))
    if web151 and web153:
        test.exec_check("AS151 fetches AS153 web service", web151, "curl -fsS http://{} >/dev/null".format(web153.address))
        test.exec_check("AS153 reaches AS151 by ICMP", web153, "ping -c 3 {} >/dev/null".format(web151.address))

    if r1:
        test.exec_check(
            "r1 installs manual push and pop labels",
            r1,
            "test -x /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 200' /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 210' /manual_mpls_setup.sh && "
            "grep -q 'route replace 300 via inet 10.2.101.253 dev net_e1_r1' /manual_mpls_setup.sh && "
            "grep -q 'route replace 400 via inet 10.2.101.253 dev net_e1_r1' /manual_mpls_setup.sh && "
            "test -s /manual_mpls_table.txt && test ! -e /mpls_ifaces.txt",
        )
    if r2:
        test.exec_check(
            "r2 installs manual push and pop labels",
            r2,
            "test -x /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 300' /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 310' /manual_mpls_setup.sh && "
            "grep -q 'route replace 200 via inet 10.2.102.253 dev net_e2_r2' /manual_mpls_setup.sh && "
            "grep -q 'route replace 410 via inet 10.2.102.253 dev net_e2_r2' /manual_mpls_setup.sh && "
            "test -s /manual_mpls_table.txt && test ! -e /mpls_ifaces.txt",
        )
    if r3:
        test.exec_check(
            "r3 installs manual push and pop labels",
            r3,
            "test -x /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 400' /manual_mpls_setup.sh && "
            "grep -q 'encap mpls 410' /manual_mpls_setup.sh && "
            "grep -q 'route replace 210 via inet 10.2.103.253 dev net_e3_r3' /manual_mpls_setup.sh && "
            "grep -q 'route replace 310 via inet 10.2.103.253 dev net_e3_r3' /manual_mpls_setup.sh && "
            "test -s /manual_mpls_table.txt && test ! -e /mpls_ifaces.txt",
        )

    for router in (r1, r2, r3):
        if router:
            test.exec_check(
                "{} does not use LDP".format(router.name),
                router,
                "test ! -e /etc/frr/frr.conf || ! grep -q 'mpls ldp' /etc/frr/frr.conf",
            )

    for router in (e1, e2, e3):
        if router:
            test.exec_check(
                "{} is a BGP edge router, not a manual MPLS core router".format(router.name),
                router,
                "test ! -e /manual_mpls_setup.sh && test ! -e /mpls_ifaces.txt",
            )

    test.write_summary("a02b-manual-mpls-runtime-test.json")
    return test.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
