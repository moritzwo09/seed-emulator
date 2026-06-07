# Transit AS Manual MPLS

This example demonstrates manual MPLS label-table setup. It is the companion to
`A02a_transit_as_mpls`, which uses LDP to distribute labels automatically.

The topology has one transit AS and three stub ASes. `AS2` has three BGP edge
routers and three internal MPLS core routers:

```text
             AS151
               |
             IX101
               |
              e1
               |
              r1
             /  \
            /    \
          r2 ---- r3
          |       |
          e2      e3
          |       |
        IX102   IX103
          |       |
        AS152   AS153
```

`e1`, `e2`, and `e3` are AS2's BGP edge routers:

- `e1`: `IX101`, connected to `AS151`.
- `e2`: `IX102`, connected to `AS152`.
- `e3`: `IX103`, connected to `AS153`.

`r1`, `r2`, and `r3` are internal AS2 routers. They form the triangle MPLS
core and do not connect directly to any IX:

- `e1 -- r1`
- `e2 -- r2`
- `e3 -- r3`
- `r1 -- r2`
- `r2 -- r3`
- `r3 -- r1`

The example uses normal BGP/OSPF routing, but it does not use the SEED Emulator
`Mpls` layer and does not use LDP. Instead, each internal AS2 router installs
static MPLS routes from `/manual_mpls_setup.sh`. The edge routers exchange BGP
routes with external ASes, while the internal routers steer traffic across the
provider core with manual labels.

## Manual Labels

The labels are directional:

| Traffic | Ingress Action | Egress Action |
| --- | --- | --- |
| AS151 to AS152 | `r1` pushes `200` to `r2` | `r2` pops `200`, then forwards to `e2` |
| AS151 to AS153 | `r1` pushes `210` to `r3` | `r3` pops `210`, then forwards to `e3` |
| AS152 to AS151 | `r2` pushes `300` to `r1` | `r1` pops `300`, then forwards to `e1` |
| AS152 to AS153 | `r2` pushes `310` to `r3` | `r3` pops `310`, then forwards to `e3` |
| AS153 to AS151 | `r3` pushes `400` to `r1` | `r1` pops `400`, then forwards to `e1` |
| AS153 to AS152 | `r3` pushes `410` to `r2` | `r2` pops `410`, then forwards to `e2` |

The Docker host must support Linux MPLS:

```sh
sudo modprobe mpls_router
sudo modprobe mpls_iptunnel
sudo modprobe mpls_gso
```

GitHub-hosted runners may not provide these modules, so this example is not
included in the default CI workflow.

## Standard Arguments

```sh
python examples/basic/A02b_manual_mpls/manual_mpls.py amd
python examples/basic/A02b_manual_mpls/manual_mpls.py --platform amd --output examples/basic/A02b_manual_mpls/output
python examples/basic/A02b_manual_mpls/manual_mpls.py --dumpfile examples/basic/A02b_manual_mpls/manual_mpls.bin
```

Supported arguments:

- `amd|arm`: optional legacy platform argument.
- `--platform amd|arm`: named platform argument.
- `--output PATH`: output folder for Docker compiler results.
- `--dumpfile PATH`: save a serialized emulator instead of compiling Docker output.
- `--override` / `--no-override`: control whether existing output is replaced.
- `--skip-render`: compile without calling `emu.render()` first.

## TestRunner Lifecycle

```sh
python seedemu/testing/cli.py all examples/basic/A02b_manual_mpls/example.yaml --artifact-dir ci-artifacts/a02b-manual-mpls
```

The runtime test uses `ComposeRuntimeTest`. It verifies cross-AS reachability,
checks that the expected manual labels are installed on `r1`, `r2`, and `r3`,
confirms that LDP is not used, and confirms that `e1`, `e2`, and `e3` are edge
routers rather than manual MPLS core routers.

## Learning Activities

- Trace AS151 to AS152 and identify label `200`.
- Trace AS151 to AS153 and identify label `210`.
- Break one label in `/manual_mpls_setup.sh` and observe which destination fails.
- Compare this example with `A02a_transit_as_mpls` to see what LDP automates.
