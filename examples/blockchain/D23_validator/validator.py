#!/usr/bin/env python3
# encoding: utf-8

from seedemu import *
from examples.blockchain.D01_ethereum_pos import ethereum_pos
import os, sys




def run(dumpfile = None, total_beacon_nodes=3, vc_per_beacon=3):
    ###############################################################################
    # Set the platform information
    platform = Platform.AMD64
    if dumpfile is None:
        script_name = os.path.basename(__file__)
        if len(sys.argv) == 2:
            if sys.argv[1].lower() == 'amd':
                platform = Platform.AMD64
            elif sys.argv[1].lower() == 'arm':
                platform = Platform.ARM64
            else:
                print(f"Usage:  {script_name} amd|arm")
                sys.exit(1)
        elif len(sys.argv) > 2:
            print(f"Usage:  {script_name} amd|arm")
            sys.exit(1)

    emu = Emulator()

    local_dump_path = "./blockchain_pos.bin"
    ethereum_pos.run(
        dumpfile=local_dump_path,
        total_beacon_nodes=total_beacon_nodes,
        vc_per_beacon=vc_per_beacon,
    )
    emu.load(local_dump_path)

    eth = emu.getLayer("EthereumService")
    blockchain = eth.getBlockchainByName(eth.getBlockchainNames()[0])
    # Create a validator-at-running container
    vc_at_running_1: PoSVcServer = blockchain.createVcNode("vcnodeAtRunning")
    vc_at_running_1.appendClassName("Ethereum-POS-Validator-AtRunning")
    vc_at_running_1.connectToBeaconNode("beaconnode0")
    vc_at_running_1.enablePOSValidatorAtRunning()
    emu.getVirtualNode("vcnodeAtruning").setDisplayName("Ethereum-POS-Validator-AtRunning-1")

    

    emu.addBinding(Binding("vcnodeAtRunning", filter=Filter(nodeName="host_*"), action=Action.FIRST))
    # emu.addBinding(Binding("vcnodeAtRunning2", filter=Filter(nodeName="host_*"), action=Action.FIRST))
        
    # Generate the emulator output
    if dumpfile is not None:
        emu.dump(dumpfile)
    else:
        emu.render()
        docker = Docker(internetMapEnabled=True, etherViewEnabled=True, platform=platform)
        emu.compile(docker, './output', override=True)

if __name__ == "__main__":
    run()
