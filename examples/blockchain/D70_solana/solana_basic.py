#!/usr/bin/env python3
# encoding: utf-8

"""Minimal SolanaService example: a private, self-contained Solana cluster.

Topology: a small Internet (10 stub ASes) on top of which we deploy a private
Agave/Solana cluster consisting of one bootstrap (genesis) validator and two
joining validators, each in a different Autonomous System.

This mirrors the structure of the Monero example (D60_monero): build the base
Internet with Makers, attach a blockchain service, bind its virtual nodes to
hosts, render, and compile to Docker.

NOTE: Agave publishes pre-built binaries for x86_64 (amd64) only, so this
example targets the AMD64 platform. Before compiling, build the base image once:

    docker build -t seedemu-solana ../../../docker_images/seedemu-solana
"""

from __future__ import annotations

import os
import sys

from seedemu import Binding, Filter, Makers
from seedemu.compiler import Docker, Platform
from seedemu.services.SolanaService import SolanaService


def _bind(emu, vnode: str, asn: int, host_index: int) -> None:
    """Bind a Solana virtual node to host_<host_index> in the given AS."""
    emu.addBinding(Binding(vnode, filter=Filter(asn=asn, nodeName=f"^host_{host_index}$")))


###############################################################################
# Select the platform (Agave is amd64-only; arm is accepted but will warn).
script_name = os.path.basename(__file__)

if len(sys.argv) == 1:
    platform = Platform.AMD64
elif len(sys.argv) == 2:
    if sys.argv[1].lower() == 'amd':
        platform = Platform.AMD64
    elif sys.argv[1].lower() == 'arm':
        platform = Platform.ARM64
    else:
        print(f"Usage:  {script_name} amd|arm")
        sys.exit(1)
else:
    print(f"Usage:  {script_name} amd|arm")
    sys.exit(1)

###############################################################################
# Build the base topology: 10 stub ASes, each with 2 hosts.
hosts_per_stub_as = 2
emu = Makers.makeEmulatorBaseWith10StubASAndHosts(hosts_per_stub_as=hosts_per_stub_as)

###############################################################################
# Create a private Solana cluster.
solana = SolanaService()
blockchain = solana.createBlockchain("seed-solana")

# AS150 / host_0: the bootstrap (genesis) validator. It builds the genesis
# ledger, runs the faucet, and is the gossip entrypoint for the rest of the
# cluster.
boot = blockchain.createBootstrapValidator("sol-boot-150")
boot.setDisplayName("Solana-Bootstrap-150")
_bind(emu, "sol-boot-150", asn=150, host_index=0)

# AS150 / host_1: a validator in the SAME AS as the bootstrap. Being on the same
# network, it reaches the bootstrap directly and joins reliably.
v_same = blockchain.createValidator("sol-validator-150b")
v_same.setDisplayName("Solana-Validator-150b")
_bind(emu, "sol-validator-150b", asn=150, host_index=1)

# AS151 / host_0: a validator in a DIFFERENT AS. It reaches the bootstrap over
# inter-domain (BGP) routing, demonstrating a cluster that spans the emulated
# Internet.
v_xas = blockchain.createValidator("sol-validator-151")
v_xas.setDisplayName("Solana-Validator-151")
_bind(emu, "sol-validator-151", asn=151, host_index=0)

###############################################################################
# Add the Solana service as a layer, then render.
emu.addLayer(solana)
emu.render()

###############################################################################
# Compile docker-compose and the build context into ./output.
docker = Docker(internetMapEnabled=True, platform=platform)
emu.compile(docker, "./output", override=True)
