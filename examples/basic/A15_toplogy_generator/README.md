# A15 Transit AS Topology Generator

This example demonstrates `TransitAsTopologyGenerator`, a NetworkX-based helper
for generating the internal topology of a transit AS.

The example creates:

```text
AS2: generated transit AS
IX100, IX101, IX102: external peering LANs
AS150, AS151, AS152: stub ASes connected through AS2
```

The generated AS2 topology has edge routers named after IXes, such as `r100`,
`r101`, and `r102`, plus internal routers such as `core0` and `core1`.
Internal link network names are kept compact, such as `n_c10_c5`, because Linux
interface names inside containers must be no longer than 15 characters.

## Basic Run

```sh
python examples/basic/A15_toplogy_generator/topology_generator.py --seed 42
```

The script writes two topology artifacts into the output folder:

```text
output/topology.json
output/topology.txt
```

These files record the generated routers, links, IX attachments, seed, graph
model, and graph parameters.

## Command-Line Controls

Important options:

- `--seed N`: make the random topology reproducible.
- `--asn N`: transit AS number, default `2`.
- `--ixes 100,101,102`: IXes where the transit AS has edge routers.
- `--stub-asns 150,151,152`: stub ASes connected to those IXes.
- `--internal-routers N`: number of generated internal routers.
- `--graph-model MODEL`: NetworkX model or alias.
- `--graph-param KEY=VALUE`: parameter passed to the graph model. Can be repeated.
- `--edge-attach-policy spread|round_robin|random|degree`: how edge routers attach to internal routers.

Example using a scale-free-style core:

```sh
python examples/basic/A15_toplogy_generator/topology_generator.py \
  --seed 7 \
  --internal-routers 6 \
  --graph-model barabasi_albert \
  --graph-param m=2 \
  --edge-attach-policy degree
```

Example using an Erdos-Renyi graph:

```sh
python examples/basic/A15_toplogy_generator/topology_generator.py \
  --seed 12 \
  --internal-routers 6 \
  --graph-model erdos_renyi \
  --graph-param p=0.4 \
  --edge-attach-policy random
```

Example with a larger AS:

```sh
python examples/basic/A15_toplogy_generator/topology_generator.py \
  --ixes 100,101,102,103,104 \
  --stub-asns 150,151,152,153,154 \
  --asn 3 \
  --internal-routers 20 \
  --hosts-per-stub 2
```

This example intentionally keeps the default SEED `Ibgp()` behavior, which
creates full-mesh iBGP among routers in the generated transit AS.

## Code Pattern

The core pattern is:

```python
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
```

The generator first creates a reusable topology object. The topology can be
validated, exported, inspected, and then applied to the SEED `Base` layer.

## TestRunner Lifecycle

Run from the repository root:

```sh
python seedemu/testing/cli.py clean examples/basic/A15_toplogy_generator/example.yaml
python seedemu/testing/cli.py compile examples/basic/A15_toplogy_generator/example.yaml
python seedemu/testing/cli.py build examples/basic/A15_toplogy_generator/example.yaml
python seedemu/testing/cli.py all examples/basic/A15_toplogy_generator/example.yaml
```

The runtime test checks that generated AS2 routers start BIRD, that the edge
routers receive generated eBGP peerings, and that traffic can cross the
generated AS2 transit topology from AS150 to AS152.
