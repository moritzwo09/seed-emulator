# Route Reflector Mini Internet

This example extends the `B00_mini_internet` topology with iBGP Route Reflector
configuration. It keeps the same IX, transit AS, stub AS, and eBGP peering
shape, then demonstrates three iBGP modes:

- `AS2`: no RR metadata, rendered as legacy full-mesh iBGP.
- `AS12`: one RR cluster with `r101` as the RR and `r104` as the client.
- `AS3`: two RR clusters with `r100` and `r103` as RRs, plus an RR-to-RR mesh.

## Files

- `route_reflector.py`: topology entrypoint. Supports the standard example
  arguments used by `seedemu/testing/cli.py`.
- `example.yaml`: test manifest for compile, build, runtime readiness, probes,
  and the custom runtime test.
- `test_runtime.py`: custom runtime validation using `ComposeRuntimeTest`.
- `output/`: generated Docker compiler output, removed by the clean command.

## Run

From the repository root:

```sh
python examples/basic/A62_route_reflector/route_reflector.py --platform amd --output examples/basic/A62_route_reflector/output
```

The legacy platform argument is also accepted:

```sh
python examples/basic/A62_route_reflector/route_reflector.py amd
```

## Test Runner

Use the standardized runner from the repository root:

```sh
python seedemu/testing/cli.py clean examples/basic/A62_route_reflector/example.yaml
python seedemu/testing/cli.py compile examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
python seedemu/testing/cli.py build examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
python seedemu/testing/cli.py up examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
python seedemu/testing/cli.py probe examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
python seedemu/testing/cli.py test examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
python seedemu/testing/cli.py down examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
```

The full lifecycle can also be run with:

```sh
python seedemu/testing/cli.py all examples/basic/A62_route_reflector/example.yaml --artifact-dir ci-artifacts/a62
```

## Runtime Checks

The manifest validates simple fixed runtime checks:

- all border router services and ping endpoint services used by the runtime
  checks are running;
- representative hosts can communicate across AS boundaries in both tested
  directions.

The custom `test_runtime.py` validates dynamic or example-specific behavior:

- generated routers have healthy BIRD protocols, with BGP sessions established;
- every generated `brdnode_*` service is discovered from Docker Compose
  metadata;
- routers in RR-enabled ASes (`AS3` and `AS12`) expose iBGP protocol names that
  contain `rr`.

## RR API Pattern

Use RR mode by registering a cluster on the AS, assigning routers to it, and
marking the RR router:

```python
as12 = base.getAutonomousSystem(12)
as12.createCluster("10.12.0.1")
as12.getRouter("r101").joinBgpCluster("10.12.0.1").makeRouteReflector()
as12.getRouter("r104").joinBgpCluster("10.12.0.1")
```

If an AS has no RR and only the implicit default cluster, `Ibgp` keeps the
legacy full-mesh behavior.
