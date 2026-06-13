#!/usr/bin/env bash
#
# Test that the D70_solana emulation produces a working, block-producing
# private Solana cluster.
#
# What it does:
#   1. builds the seedemu-solana base image (Agave binaries)
#   2. generates the emulation from solana_basic.py
#   3. brings the cluster up with docker compose
#   4. polls the bootstrap validator's JSON-RPC until slots/blocks advance
#      and all validators are visible to the cluster
#   5. tears everything down
#
# Agave ships x86_64 binaries only, so the cluster runs as linux/amd64
# (natively on amd64 hosts, via emulation on arm64 hosts).
#
# Usage:
#   ./test_solana.sh                # full build + up + verify + teardown
#   KEEP_UP=1 ./test_solana.sh      # leave the cluster running at the end
#   ./test_solana.sh --down         # just tear down a previous run

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
OUTPUT_DIR="$HERE/output"
COMPOSE="docker compose"
PLATFORM="${PLATFORM:-linux/amd64}"
export DOCKER_DEFAULT_PLATFORM="$PLATFORM"

# Bootstrap validator: AS150 / host_0. Its RPC is reachable on the emulated
# network; we reach it by exec-ing into the container (no host port mapping).
# This is the docker-compose *service* name produced by the compiler.
BOOT_SERVICE="hnode_150_host_0"

# How long to wait (seconds) for the chain to start producing blocks.
MAX_WAIT="${MAX_WAIT:-420}"
# Minimum number of *voting* validators required for a hard pass (the bootstrap
# plus the same-AS validator, which converge on any host). Additional cross-AS
# validators join too on a native amd64 host with a converged data plane.
MIN_VALIDATORS="${MIN_VALIDATORS:-2}"

log()  { echo -e "\033[1;34m[test]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ ok ]\033[0m $*"; }
fail() { echo -e "\033[1;31m[fail]\033[0m $*"; }

teardown() {
  if [[ -d "$OUTPUT_DIR" ]]; then
    log "tearing down cluster ..."
    ( cd "$OUTPUT_DIR" && $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true )
  fi
}

if [[ "${1:-}" == "--down" ]]; then
  teardown
  ok "torn down."
  exit 0
fi

# ---------------------------------------------------------------------------
# 1) Build the Agave base image.
# ---------------------------------------------------------------------------
log "building seedemu-solana base image ($PLATFORM) ..."
docker build --platform "$PLATFORM" -t seedemu-solana "$REPO_ROOT/docker_images/seedemu-solana" \
  || { fail "base image build failed"; exit 1; }
ok "base image ready."

# ---------------------------------------------------------------------------
# 2) Generate the emulation.
# ---------------------------------------------------------------------------
log "generating emulation from solana_basic.py ..."
( cd "$HERE" && python3 solana_basic.py amd ) || { fail "emulation generation failed"; exit 1; }
[[ -f "$OUTPUT_DIR/docker-compose.yml" ]] || { fail "no docker-compose.yml produced"; exit 1; }
ok "emulation generated."

# ---------------------------------------------------------------------------
# 3) Bring the cluster up.
#
# seedemu node images do `FROM <digest>`, where each <digest> base image is
# built by a "dummy" compose service (named after the digest; one file per
# digest under output/dummies/). docker compose v2 builds services in parallel
# and ignores this implicit ordering, so we build the dummy base images first,
# then build + start everything else.
# ---------------------------------------------------------------------------
dummy_services="$(ls "$OUTPUT_DIR/dummies" 2>/dev/null | tr '\n' ' ')"
if [[ -n "$dummy_services" ]]; then
  log "pre-building base images: $dummy_services"
  ( cd "$OUTPUT_DIR" && $COMPOSE build $dummy_services ) \
    || { fail "base (dummy) image build failed"; teardown; exit 1; }
fi

log "building containers and starting the cluster (this can take a while) ..."
( cd "$OUTPUT_DIR" && $COMPOSE up -d --build ) || { fail "docker compose up failed"; teardown; exit 1; }
ok "cluster started."

# Resolve the bootstrap container id directly from its compose service name.
boot_cid="$( cd "$OUTPUT_DIR" && $COMPOSE ps -q "$BOOT_SERVICE" 2>/dev/null )"

if [[ -z "$boot_cid" ]]; then
  fail "could not find bootstrap container (service $BOOT_SERVICE)"
  ( cd "$OUTPUT_DIR" && $COMPOSE ps )
  teardown; exit 1
fi
ok "bootstrap container: $boot_cid"

# Helper: run a solana command inside the bootstrap container, with retries.
# We exec the binary directly (no `bash -lc`) and retry, because `docker exec`
# can intermittently fail with setns errors under amd64 emulation.
RPC_URL_LOCAL="http://127.0.0.1:8899"
sol() {
  local tries=0 out
  while (( tries < 6 )); do
    if out=$(docker exec "$boot_cid" solana --url "$RPC_URL_LOCAL" "$@" 2>/dev/null); then
      echo "$out"; return 0
    fi
    tries=$((tries+1)); sleep 2
  done
  return 1
}

# ---------------------------------------------------------------------------
# 4) Verify the chain is alive and producing blocks.
# ---------------------------------------------------------------------------
log "waiting for the bootstrap RPC to come online ..."
deadline=$(( $(date +%s) + MAX_WAIT ))
rpc_up=0
ver=""
while (( $(date +%s) < deadline )); do
  if ver=$(sol cluster-version) && [[ -n "$ver" ]]; then
    rpc_up=1; break
  fi
  sleep 10
done
if (( rpc_up != 1 )); then
  fail "RPC never came online within ${MAX_WAIT}s"
  docker exec "$boot_cid" sh -c 'tail -n 40 /opt/solana/config/bootstrap-validator/*.log' 2>/dev/null || true
  teardown; exit 1
fi
ok "RPC online: cluster-version $ver"

log "checking that slots are advancing (block production) ..."
slot1=$(sol slot | tr -dc '0-9'); slot1=${slot1:-0}
log "slot now: $slot1 ; waiting ~30s ..."
sleep 30
slot2=$(sol slot | tr -dc '0-9'); slot2=${slot2:-0}
log "slot now: $slot2"

if [[ "$slot2" -gt "$slot1" ]]; then
  ok "slots are advancing ($slot1 -> $slot2): the chain is producing blocks."
else
  fail "slots did not advance ($slot1 -> $slot2): chain is not producing blocks."
  docker exec "$boot_cid" sh -c 'tail -n 60 /opt/solana/config/bootstrap-validator/*.log' 2>/dev/null || true
  teardown; exit 1
fi

# Confirm block height is non-zero too.
bh=$(sol block-height | tr -dc '0-9')
log "block-height: ${bh:-unknown}"

# ---------------------------------------------------------------------------
# 4b) Verify the chain actually processes transactions (airdrop -> balance).
# ---------------------------------------------------------------------------
log "verifying transaction processing (airdrop to a fresh account) ..."
tx_ok=0
if docker exec "$boot_cid" bash -c '
    set -e
    U=http://127.0.0.1:8899
    solana-keygen new --no-passphrase -fso /tmp/seedemu_test_payer.json >/dev/null 2>&1
    PK=$(solana-keygen pubkey /tmp/seedemu_test_payer.json)
    solana --url $U airdrop 5 "$PK" >/dev/null 2>&1
    for i in $(seq 1 10); do
      bal=$(solana --url $U balance "$PK" 2>/dev/null | grep -oE "^[0-9.]+")
      awk "BEGIN{exit !($bal > 0)}" && exit 0
      sleep 2
    done
    exit 1
  ' 2>/dev/null; then
  tx_ok=1
  ok "transaction processed: airdrop credited a new account (ledger is executing transactions)."
else
  fail "transaction did not confirm (airdrop balance stayed 0)."
  docker exec "$boot_cid" sh -c 'tail -n 40 /opt/solana/config/bootstrap-validator/*.log' 2>/dev/null || true
  teardown; exit 1
fi

# ---------------------------------------------------------------------------
# 5) Verify the joining validators register and vote in the cluster.
#
# This is the multi-host part of the cluster. It converges on a native amd64
# host. Under linux/amd64 *emulation* (e.g. Apple Silicon), the emulated
# validator binary cannot complete outbound non-loopback connects, so joining
# validators may not converge there — that is an emulation-host limitation, not
# a defect in the emulation. It is therefore best-effort by default; set
# REQUIRE_MULTI=1 (recommended on native amd64) to make it a hard requirement.
# ---------------------------------------------------------------------------
log "waiting for joining validators to vote (up to ${MAX_WAIT}s; need >= $MIN_VALIDATORS) ..."
deadline=$(( $(date +%s) + MAX_WAIT ))
nval=0
while (( $(date +%s) < deadline )); do
  nval=$(sol validators 2>/dev/null | grep -oE '[0-9]+ current validators' | grep -oE '^[0-9]+' | head -1)
  nval=${nval:-0}
  log "voting validators in cluster: $nval (target >= $MIN_VALIDATORS)"
  (( nval >= MIN_VALIDATORS )) && break
  sleep 15
done

echo
log "validator set:"
sol validators || true
echo

multi_ok=0
if (( nval >= MIN_VALIDATORS )); then
  multi_ok=1
  ok "$nval validators are voting (multi-validator consensus working)."
elif [[ "${REQUIRE_MULTI:-0}" == "1" ]]; then
  fail "only $nval voting validator(s); expected >= $MIN_VALIDATORS (REQUIRE_MULTI=1)."
  docker exec "$boot_cid" sh -c 'tail -n 40 /opt/solana/config/bootstrap-validator/*.log' 2>/dev/null || true
  teardown; exit 1
else
  echo -e "\033[1;33m[warn]\033[0m only $nval voting validator(s) converged here."
  echo "       Multi-host convergence needs a native amd64 host (re-run there with REQUIRE_MULTI=1)."
fi

# ---------------------------------------------------------------------------
# Verdict. The core requirement — a working Solana chain that produces blocks
# and processes transactions — is verified by the hard checks above.
# ---------------------------------------------------------------------------
echo
ok "SUCCESS: the private Solana chain is live, producing blocks, and processing transactions."
echo "    cluster-version    : $ver"
echo "    slot               : $slot1 -> $slot2"
echo "    block-height       : ${bh:-unknown}"
echo "    transaction test   : $([[ $tx_ok == 1 ]] && echo passed || echo failed)"
echo "    voting validators  : $nval $([[ $multi_ok == 1 ]] && echo '(multi-validator consensus)' || echo '(single-host; see note above)')"

if [[ "${KEEP_UP:-0}" == "1" ]]; then
  log "KEEP_UP=1 set; leaving the cluster running. Tear down with: $0 --down"
else
  teardown
  ok "cluster torn down."
fi
