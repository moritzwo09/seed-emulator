# A13 ExaBGP Control Plane

`A13` installs ExaBGP as a SEED service speaker through `ExaBgpService` and
`Binding`.

ExaBGP is not a `Routing` backend. The peer router keeps its normal BIRD or FRR
daemon, and the service records a router-facing BGP peer intent that `Routing`
renders for that router.

## What It Proves

- ExaBGP is installed on a bound host node.
- The ExaBGP node joins the IX peering LAN directly.
- `Routing` renders the peer session on the real router.
- Static IPv4 announcements are emitted from `/etc/exabgp/exabgp.conf`.

## Topology

- `AS2/router0` is a normal BIRD router on `ix100`.
- `AS180/exabgp` is a host on `ix100` at `10.100.0.180`.
- `AS180/exabgp` announces `198.51.100.0/24` to `AS2/router0`.

## Build

```bash
PYTHONPATH=. python3 examples/basic/A13_exabgp_control_plane/exabgp_control_plane.py
```

Runtime validation should check `/etc/exabgp/exabgp.conf` on the speaker and the
generated BGP peer on `AS2/router0`.
