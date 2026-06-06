# Real-World Interaction

This example demonstrates two features related to the real world.

The first feature allows outside machines to connect to the emulator, so they
can participate in the emulation. This is done with OpenVPN remote access.

The second feature allows the emulation to include a real-world autonomous
system. A real-world AS announces real-world prefixes inside the emulator, and
packets reaching that AS can exit the emulator toward the real destination.

## Topology

The emulated topology has:

- `AS2`: transit AS between `IX100` and `IX101`.
- `AS151`: stub AS at `IX100`, with OpenVPN remote access enabled on `net0`.
- `AS152`: stub AS at `IX101`, with OpenVPN remote access enabled on `net0`.
- `AS20940`: Akamai real-world AS at `IX101`.

`example.com` is commonly served from Akamai infrastructure, so this example
uses Akamai to demonstrate real-world prefix injection. By default, the example
uses a deterministic Akamai prefix related to `example.com`:

```text
23.192.228.0/24
```

This makes CI and classroom tests more stable than fetching live prefixes from
the Internet every time. To fetch live prefixes for AS20940 instead, pass:

```sh
--live-prefixes
```

## OpenVPN Remote Access

The OpenVPN remote access provider is created with:

```python
ovpn = OpenVpnRemoteAccessProvider()
```

Remote access is enabled on a network by calling:

```python
as151.createNetwork("net0").enableRemoteAccess(ovpn)
```

The remote access provider creates an OpenVPN bridge node for the selected
network. It listens on a service network so the emulator host can forward a UDP
port to the VPN server. For details on how to connect to the OpenVPN server with
the built-in CA/certificate/key, see:

```text
misc/openvpn-remote-access
```

## Real-World AS

A real-world AS is still modeled as an autonomous system:

```python
as20940 = base.createAutonomousSystem(20940)
```

The special real-world router is created with:

```python
as20940.createRealWorldRouter(
    "rw",
    prefixes=["23.192.228.0/24"],
).joinNetwork("ix101", "10.101.0.209")
```

`createRealWorldRouter` accepts:

- `name`: name of the node.
- `hideHops`: whether to hide real-world hops from traceroute.
- `prefixes`: list of prefixes to announce. If `None`, prefixes are fetched
  from the real world for that ASN.

## Standard Arguments

The example accepts both the legacy platform argument and the newer named
arguments:

```sh
python examples/basic/A03_real_world/real_world.py amd
python examples/basic/A03_real_world/real_world.py --platform amd --output examples/basic/A03_real_world/output
python examples/basic/A03_real_world/real_world.py --dumpfile examples/basic/A03_real_world/real_world.bin
python examples/basic/A03_real_world/real_world.py --live-prefixes
```

Supported arguments:

- `amd|arm`: optional legacy platform argument.
- `--platform amd|arm`: named platform argument.
- `--output PATH`: output folder for Docker compiler results.
- `--dumpfile PATH`: save a serialized emulator instead of compiling Docker output.
- `--live-prefixes`: fetch live AS20940 prefixes instead of using the stable
  example prefix.
- `--override` / `--no-override`: control whether existing output is replaced.
- `--skip-render`: compile without calling `emu.render()` first.

## TestRunner Lifecycle

This example includes an `example.yaml` manifest for `seedemu.testing`. Run
these commands from the repository root:

```sh
python seedemu/testing/cli.py clean examples/basic/A03_real_world/example.yaml
python seedemu/testing/cli.py compile examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
python seedemu/testing/cli.py build examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
python seedemu/testing/cli.py up examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
python seedemu/testing/cli.py probe examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
python seedemu/testing/cli.py test examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
python seedemu/testing/cli.py down examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
```

The full lifecycle can also be run with:

```sh
python seedemu/testing/cli.py all examples/basic/A03_real_world/example.yaml --artifact-dir ci-artifacts/a03
```

The automatic tests intentionally avoid depending on external Internet
availability. They check:

- AS151 can reach the AS152 web service through AS2.
- AS152 can reach the AS151 web service through AS2.
- The Akamai real-world router exists and has the deterministic prefix.
- The real-world router has service-network route setup.

Manual lab activities can additionally test real outbound traffic and OpenVPN
client connectivity from outside the emulator.
