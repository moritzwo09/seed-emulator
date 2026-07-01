# F05 — Link Properties (Optional Fields)

## Goal

Emit optional per-link fields (`mtu`, `bw`, `underlay`) in link entries where
the data is available in the configured emulation.

## Supported Properties

### `mtu`

**Source:** `iface['mtu']` on either interface endpoint (both sides store the
network MTU set in `Scion.__create_link()` as `net.getMtu()`).

**When to emit:** Always include the link MTU. The `.topo` consumer uses it to
configure the SCION border router's MTU for that interface.

```yaml
  - {a: "1-ff00:0:110#1", b: "1-ff00:0:111#41", linkAtoB: CHILD, mtu: 1280}
```

### `bw` (bandwidth)

**Status: NOT SUPPORTED in initial version.**

The `Network.getDefaultLinkProperties()` API can store bandwidth, but this
value is not threaded into `ScionRouter` interface dicts by `Scion.__create_link()`.
Adding support requires:
1. Storing `bw` in the `iface` dict inside `__create_link()`
2. Reading it in the compiler

Future work. Document as a gap.

### `underlay`

**Status: NOT SUPPORTED in initial version.**

Per-link `underlay: UDP/IPv6` appears in some reference `.topo` files. In SEED,
the underlay protocol is not currently stored per SCION interface. The
`Network.underlay` setting exists but is not propagated into interface dicts.

Future work. Document as a gap.

### Per-AS `underlay`

**Status: NOT SUPPORTED.**

`ScionAutonomousSystem` has no AS-level underlay field. This would require a
new API method and corresponding rendering logic.

## Current Implementation

The compiler emits:
- `mtu` — always, from `iface['mtu']`

The compiler does **not** emit:
- `bw` — not available in interface dicts
- `underlay` — not available in interface dicts or AS objects

## Known Gaps Summary

| Field | .topo support | SEED API | Compiler support |
|---|---|---|---|
| `mtu` (link) | yes | via `iface['mtu']` | **yes** |
| `mtu` (AS) | yes | via `getMtu()` | **yes** |
| `bw` | yes | not in iface dict | no — future work |
| `underlay` (link) | yes | not in iface dict | no — future work |
| `underlay` (AS) | yes | not in AS object | no — future work |
| `dispatched_ports` | yes | hardcoded | no — not needed for topology |
| `latency` | theoretical | not in iface dict | no — future work |
