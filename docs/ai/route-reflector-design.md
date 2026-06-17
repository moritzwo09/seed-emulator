# AS-level iBGP Mode Prompt

**Follow the prompt below:**

Move iBGP mode selection and default Route Reflector configuration in SeedEMU
up into the `AutonomousSystem` class, instead of continuing to let the `Ibgp`
layer infer the mode from whether an RR exists.

## Background

Original related code locations:

- `seedemu/core/AutonomousSystem.py`
  - `createBgpCluster(address)` registers an RR cluster ID.
  - `_aggregateBgpClusters()` aggregates cluster, RR, and client membership.
  - The current implicit default cluster ID is hard-coded as `"10.0.0.0"`.
- `seedemu/core/Node.py`
  - `Router.makeRouteReflector()` records whether a router is an RR.
  - `Router.joinBgpCluster(cluster_id)` records the cluster a router belongs to.
- `seedemu/layers/Ibgp.py`
  - `configure()` currently calls `asobj._aggregateBgpClusters()`.
  - It currently uses `has_rr = any(len(rrs) > 0 ...)` to decide whether to use
    RR mode or full mesh mode.
  - `_render_rr_mode()` writes RR/client session intent into routers.
  - `_render_full_mesh_mode()` keeps the legacy full mesh behavior.
- `seedemu/layers/_bgp_metadata.py`
  - `route_reflector_client` and `route_reflector_cluster_id` are BGP intent
    fields.
  - BIRD renders `rr client` and `rr cluster id ...`.
- `seedemu/layers/Routing.py`
  - FRR renders `bgp cluster-id ...` and
    `neighbor ... route-reflector-client`.

## Goal

Add an AS-level `ibgp_mode` configuration to `AutonomousSystem`. The only valid
values are:

- `"full-mesh"`
- `"route-reflector"`

The default behavior must remain compatible: when there is no explicit
configuration, a normal AS still uses full mesh. Existing old RR usage through
`createBgpCluster()`, `joinBgpCluster()`, and `makeRouteReflector()` must not be
broken.

When a user sets an AS to `"route-reflector"` but does not manually create a
cluster and does not manually specify a Route Reflector, `AutonomousSystem`
must automatically provide:

- A deterministic default cluster ID.
- A deterministic default Route Reflector.
- Default cluster membership, where the selected RR acts as the reflector and
  all other routers act as clients.

However, when the user configures multiple cluster IDs and multiple Route
Reflectors, they must use `joinBgpCluster()` to explicitly specify which
cluster ID each router belongs to. Otherwise, an error must be raised.

These defaults and mode decisions must be defined inside `AutonomousSystem`.
The `Ibgp` layer should only consume the result provided by `AutonomousSystem`
and render sessions.

`__ibgp_mode` should default to `"full-mesh"`. `setIbgpMode()` must validate
the input. Invalid values should directly raise `ValueError` or
`AssertionError`, and the error message must include the valid values.

The default cluster ID must be decided by the AS, not left in the `Ibgp` layer.
Use an ASN-derived IPv4-style string, for example `"10.{asn}.0.1"`, and ensure
it does not conflict.

The default Route Reflector must be decided by the AS. By default, select the
first router after sorting router names in ascending order.

## Behavior Requirements

1. `Ibgp.configure()` must no longer infer the mode by itself using `has_rr`.
2. `Ibgp.configure()` should get the effective iBGP mode from
   `AutonomousSystem`:
   - `"full-mesh"` calls `_render_full_mesh_mode()`.
   - `"route-reflector"` calls `_render_rr_mode()`.
3. RR cluster aggregation, the default cluster ID, and default RR selection
   must all be completed inside `AutonomousSystem`.
4. For an AS to enter effective `"route-reflector"` mode, the user must
   explicitly call `setIbgpMode("route-reflector")`. Only after that should the
   following APIs be callable:
   - `createBgpCluster()`.
   - `makeRouteReflector(True)`.
   - `joinBgpCluster(cluster_id)`.
5. If the user explicitly sets `"full-mesh"`, that setting should be respected
   unless RR-specific configuration already exists. If there is a conflict, do
   not silently ignore it. Raise a clear error, for example:
   `"AS2 has route-reflector cluster/router configuration but ibgp_mode is full-mesh"`.
6. Multi-cluster RR must still validate that every cluster has an RR and
   clients. The default RR is only used when the user selected
   `"route-reflector"` and did not provide any RR configuration.
7. Do not change the intent schema in `_bgp_metadata.py`. Continue using the
   existing fields `route_reflector_client` and `route_reflector_cluster_id`.
8. Do not change BIRD/FRR rendering semantics. BIRD should still render RR
   configuration through `_bgp_metadata.py`, and FRR should still render
   cluster-id and route-reflector-client through `Routing.py`.
