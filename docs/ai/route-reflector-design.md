# AS-level iBGP Mode Prompt

**Follow the prompt below:**

Move iBGP mode selection and default Route Reflector configuration in SeedEMU
up into the `AutonomousSystem` class, instead of continuing to let the `Ibgp`
layer infer the mode from whether an RR exists.

## Goal

Add an AS-level `ibgp_mode` configuration to `AutonomousSystem`. The only valid
values are:

- `"full-mesh"`
- `"route-reflector"`

The default behavior must remain compatible: when there is no explicit
configuration, a normal AS still uses full mesh.

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

`__ibgp_mode` should default to `"full-mesh"`.

The default cluster ID must be decided by the AS, not left in the `Ibgp` layer.
Use an ASN-derived IPv4-style string, for example `"10.{asn}.0.1"`, and ensure
it does not conflict.

The default Route Reflector must be decided by the AS. By default, select the
first router after sorting router names in ascending order.
