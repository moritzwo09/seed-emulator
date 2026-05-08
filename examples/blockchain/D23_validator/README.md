
# D23 Validator (Validator-at-Running)

This example demonstrates:

- Bootstrapping an Ethereum PoS  (based on D01_ethereum_pos)
- Launching an additional `validator-at-running` (vcatrunning) container
- Adding a validator after the chain has started via the vc_start_at_running.sh script
- Observing validator state transitions from pending to active, as well as balance changes
## 1. Adding a validator-at-running container

Use the following code to create a validator-at-running container in the PoS example. The vcatrunning container is essentially a VcNode.
```python
vc_at_running_1: PoSVcServer = blockchain.createVcNode("vcnodeAtruning")
vc_at_running_1.appendClassName("Ethereum-POS-Validator-Atruning")
vc_at_running_1.connectToBeaconNode("beaconnode0")
vc_at_running_1.enablePOSValidatorAtRunning()
```

## 2. Start the emulator environment

Run the following commands on the host machine:

```bash
cd /home/seed/seed-emulator
python3 examples/blockchain/D23_validator/validator.py 
cd output
dcbuild
dcup
```


## 3. Run vc_start_at_running.sh to generate validator keys, start the validator, and stake 32 ETH to the deposit contract

Copy the script into the container:
```bash
docker cp vc_start_at_running.sh <vcatrunning_container_name>:/tmp/
```
Then execute it:
```bash
docker exec -it <vcatrunning_container_name> bash /tmp/vc_start_at_running.sh
```

During execution, a mnemonic will be generated first. Save it, as it is required for generating validator keys. The script will then start the Lighthouse VC automatically, and finally stake 32 ETH to the deposit contract.


The Lighthouse VC runtime logs are written to `/tmp/lighthouse-vc.log`. Use:
```bash
tail -f /tmp/lighthouse-vc.log
```
to follow the Lighthouse VC logs.

When you see the following entries in the logs, it indicates the VC has started participating in block proposal and attestation.

```bash
May 08 03:34:21.002 INFO Requesting unsigned block               slot: 370, service: block
May 08 03:34:21.009 INFO Received unsigned block                 slot: 370, service: block
May 08 03:34:21.011 INFO Publishing signed block                 signing_time_ms: 2, slot: 370, service: block
May 08 03:34:21.028 INFO Successfully published block            slot: 370, graffiti: None, attestations: 0, deposits: 0, block_type: Full, service: block
```
You can also query the Beacon API to observe the validator-at-running status:
```bash
curl -s http://10.151.0.73:8000/eth/v1/beacon/states/head/validators | jq
```
In practice, after roughly 5 epochs the validator state becomes pending, and after roughly 11 epochs it becomes active.
