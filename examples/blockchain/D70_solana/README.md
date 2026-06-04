# D70_solana: Solana Blockchain Service Example

This example deploys a **private, self-contained Solana cluster** on top of an
emulated Internet. It runs the real [Agave](https://github.com/anza-xyz/agave)
validator software (the production Solana client maintained by Anza), so the
same tools and workflows used against real Solana clusters work here unchanged.

The example mirrors the structure of [`D60_monero`](../D60_monero): build a base
Internet, attach the blockchain service, bind its virtual nodes to hosts,
render, and compile to Docker.

> **Platform note.** Agave publishes pre-built binaries for **x86_64 (amd64)
> only**. On Apple Silicon / arm64 hosts the cluster runs under `linux/amd64`
> emulation (slower, but functional).

## What gets built

`solana_basic.py` builds a 10-stub-AS Internet (via `Makers`) and a private
Solana cluster of three nodes:

| Virtual node          | Role                | AS  | Host    |
| --------------------- | ------------------- | --- | ------- |
| `sol-boot-150`        | bootstrap validator | 150 | host_0  |
| `sol-validator-150b`  | validator           | 150 | host_1  |
| `sol-validator-151`   | validator           | 151 | host_0  |

- The **bootstrap validator** creates the genesis ledger with `solana-genesis`,
  stakes itself, runs `solana-faucet`, and is the gossip entrypoint.
- The **same-AS validator** (AS150/host_1) joins over the local network — the
  most direct path, so it converges reliably on any host.
- The **cross-AS validator** (AS151) joins over inter-domain (BGP) routing,
  demonstrating a cluster that spans the emulated Internet.

Each validator waits for the bootstrap RPC, generates its own identity and vote
keypairs, funds its identity with an airdrop (relayed through the bootstrap
RPC), creates a vote account, and joins the cluster via the bootstrap node's
gossip entrypoint.

All addresses (each node's own IP, and the bootstrap's gossip/RPC endpoint) are
resolved from the virtual-node bindings at render time — nothing is hard-coded
in the service (see the design notes below).

## Prerequisites

Build the Solana base image once (ships the pinned Agave binaries):

```bash
docker build -t seedemu-solana ../../../docker_images/seedemu-solana
```

## Build and run

```bash
# 1. Generate the emulation (amd64 platform)
python3 solana_basic.py amd

# 2. Build and start the cluster
cd output
# Build the local base images first. seedemu node images do `FROM <digest>`,
# where each base image is built by a "dummy" service (one per file under
# output/dummies/). docker compose v2 builds in parallel, so build these first:
docker compose build $(ls dummies)
docker compose up -d --build

# 3. Watch it converge (give it a couple of minutes the first time)
```

The simplest path is to just run `./test_solana.sh` (below), which handles the
build ordering for you.

## Interacting and verifying

The bootstrap validator's RPC listens on port `8899` inside the emulated
network. The cluster is not port-mapped to the host, so query it by exec-ing
into the bootstrap container (AS150 / host_0):

```bash
# Find the bootstrap container
BOOT=$(docker ps --format '{{.ID}} {{.Names}}' | grep hnode_150_host_0 | awk '{print $1}')

# Cluster software version (proves RPC is up)
docker exec "$BOOT" solana --url http://127.0.0.1:8899 cluster-version

# Current slot — run twice; it should increase (blocks are being produced)
docker exec "$BOOT" solana --url http://127.0.0.1:8899 slot
docker exec "$BOOT" solana --url http://127.0.0.1:8899 block-height

# Epoch info (slot, epoch, absolute slot, transaction count)
docker exec "$BOOT" solana --url http://127.0.0.1:8899 epoch-info

# Validators in the cluster (should list all three once converged)
docker exec "$BOOT" solana --url http://127.0.0.1:8899 validators

# Nodes seen over gossip
docker exec "$BOOT" solana --url http://127.0.0.1:8899 gossip
```

Raw JSON-RPC also works (e.g. `getSlot`, `getBlockHeight`, `getEpochInfo`):

```bash
docker exec "$BOOT" bash -lc \
  'curl -s http://127.0.0.1:8899 -X POST -H "Content-Type: application/json" \
     -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getSlot\"}"'
```

## Automated test

`test_solana.sh` builds the base image, generates the emulation, brings the
cluster up, and asserts that the chain produces blocks (slots advance) and that
the validators register in the cluster, then tears everything down:

```bash
./test_solana.sh                # full build + verify + teardown
KEEP_UP=1 ./test_solana.sh      # verify, then leave the cluster running
./test_solana.sh --down         # tear down a previous run
```

## Logs and troubleshooting

```bash
# Validator log (bootstrap)
docker exec "$BOOT" tail -n 100 -f /opt/solana/config/bootstrap-validator/*.log

# Faucet log
docker exec "$BOOT" cat /var/log/solana-faucet.log

# On a joining validator (AS151)
V=$(docker ps --format '{{.ID}} {{.Names}}' | grep hnode_151_host_0 | awk '{print $1}')
docker exec "$V" tail -n 100 -f /opt/solana/config/validator/*.log
```

Notes:
- The first startup is slow: containers build, the bootstrap creates genesis,
  then validators fetch genesis/snapshots over gossip and create vote accounts.
- A single staked validator already advances slots, so block production is
  visible even before the other validators finish joining.
- Solana validators are CPU/IO intensive; under arm64 emulation expect slower
  slot times. For larger clusters, prefer an amd64 host (see PRINCIPLES.md P9 on
  scale being a real, resource-bounded concern).
- **Inter-AS convergence under emulation:** on a native amd64 host all three
  nodes (including the cross-AS one) join. When the whole stack runs under
  `linux/amd64` emulation (e.g. Apple Silicon), the emulated kernel's rtnetlink
  layer can be flaky, which delays inter-domain data-plane convergence; the
  bootstrap and the same-AS validator (on-link) still converge reliably, so
  multi-validator consensus is demonstrable everywhere.

## Ports

| Port        | Purpose                                  |
| ----------- | ---------------------------------------- |
| 8899        | JSON-RPC                                 |
| 8900        | RPC PubSub (websocket)                   |
| 8001        | gossip                                   |
| 9900        | faucet (bootstrap only)                  |
| 8002–8030   | dynamic range (TPU / turbine / repair)   |

## Design notes (alignment with PRINCIPLES.md)

- **P1 (execution-agnostic):** the scenario never references Docker; only
  `emu.compile(Docker(), ...)` selects the backend.
- **P4 (virtual nodes + late binding):** validators are symbolic vnodes; their
  IPs and the bootstrap entrypoint are resolved from `Binding`s during
  `configure()`. No IPs/ASNs are hard-coded in the service.
- **P5 (real production software):** runs real `agave-validator` /
  `solana-genesis` / `solana-faucet`, pinned to a specific Agave release in
  `docker_images/seedemu-solana/Dockerfile`.
- **P6 (self-contained module):** `SolanaService` exposes a small high-level API
  (`createBlockchain`, `createBootstrapValidator`, `createValidator`) and hides
  all genesis/keypair/faucet boilerplate.
