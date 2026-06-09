# A12 BGP Mixed Backend

`A12` demonstrates mixed BIRD and FRRouting control planes in one IPv4 SEED topology.

The default router backend remains BIRD. Only routers created with
`routingBackend="frr"` receive FRR packages, `/etc/frr/frr.conf`, and `/frr_start`.

## What It Proves

- `Router` owns the routing backend choice.
- `Ebgp`, `Ibgp`, and `Ospf` describe routing intent.
- `Routing` renders BIRD or FRR from the same intent model.
- BIRD and FRR routers can coexist without changing old default examples.

## Topology

- `AS2/r1` uses the default BIRD backend and peers at `ix100`.
- `AS2/r2` uses FRR and peers at `ix101`.
- `AS151/router0` uses FRR.
- `AS152/router0` uses the default BIRD backend.

## Build

```bash
PYTHONPATH=. python3 examples/basic/A12_bgp_mixed_backend/bgp_mixed_backend.py
```

Runtime validation should check that FRR routers have `/etc/frr/frr.conf` and no
`bird -d` startup command, while BIRD routers still render `/etc/bird/bird.conf`.
