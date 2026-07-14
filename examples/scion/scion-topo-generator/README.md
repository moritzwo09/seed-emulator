# SEED - SCION Compiler

A compiler for the SEED emulator that translates a rendered SCION emulation
into a standards-compliant `.topo` file — the format used by SCION's own
tooling (`scion-pki`, topology generators) to describe a network.

## What Was Built

`ScionTopoCompiler` is a new compiler class (~170 lines) added to the SEED
emulator framework. It takes a fully rendered SEED emulation with SCION
layers and produces a `topology.topo` file that follows the official SCION
topology file format.

**Usage:**

```python
emu.render()
emu.compile(ScionTopoCompiler(), './output')
# produces: ./output/topology.topo
```

**Motivation:** The existing SEED framework had no public compiler that
generates the full `.topo` format with both an `ASes:` block and a `links:`
block. The internal `ScionIsd.__gen_topofile()` method only produces a
partial ASes section for use by `scion-pki testcrypto` — it cannot be used
by external SCION tools, documentation, or reproducibility workflows.

## Background: The `.topo` File Format

A `.topo` file is a YAML document with two top-level sections. There are a
couple python files defining its structure in `scion/patches/tools/topology/`.

```yaml
ASes:
  "1-ff00:0:110":       # ISD-ASN identifier
    core: true          # core ASes carry all four flags
    voting: true
    authoritative: true
    issuing: true
    mtu: 1400           # optional AS-wide MTU
  "1-ff00:0:111":
    cert_issuer: 1-ff00:0:110   # non-core ASes name their cert issuer

links:
  - {a: "1-ff00:0:110#1", b: "1-ff00:0:111#41", linkAtoB: CHILD, mtu: 1280}
  - {a: "1-ff00:0:120-A#6", b: "1-ff00:0:130-B#104", linkAtoB: CORE}
```

**Link endpoint notation:** `IA#IFID` or `<ISD>-<ASN>#<IFID>`. When an AS
has multiple border routers, a letter suffix distinguishes them:
`<ISD>-<ASN>-A#<IFID>`, `<ISD>-<ASN>-B#<IFID>`, etc.

**Link types:**

| Type | Meaning | Direction |
|---|---|---|
| `CORE` | Link between two core ASes | Symmetric |
| `CHILD` | Transit link, written from the parent's perspective | Parent → Child |
| `PEER` | Peering link between non-core ASes | Symmetric |

Note: The child side of a Transit link has `PARENT` internally in SEED, but
the `.topo` format only uses `CHILD` (from the parent's perspective). The
compiler handles this mapping.

## SEED Framework Internals

Understanding where the data lives after `emu.render()` is key to
understanding the compiler.

### Rendering Pipeline

`emu.render()` runs two ordered passes: `configure()` then `render()`. The
SCION-relevant configure steps are:

1. **`Base.configure()`** — creates all nodes and networks, assigns IP
   addresses, calls `ScionAutonomousSystem.configure()` which computes the
   AS-wide MTU (minimum of all internal network MTUs). A network MTU
   (Maximum Transmission Unit) is the size of the largest data packet a
   device will accept and transmit across a network without fragmenting it.
2. **`ScionIsd.configure()`** — marks each AS as core or non-core within
   its ISD; sets the attribute set `{core, voting, authoritative, issuing}`
   on each `ScionAutonomousSystem`.
3. **`ScionRouting.configure()`** — identifies border routers (connected to
   IX or cross-connect networks) and promotes them to `ScionRouter` objects.
4. **`Scion.configure()`** — iterates all declared links (`addIxLink`,
   `addXcLink`), allocates Interface IDs (IFIDs) per AS, and calls
   `router.addScionInterface(ifid, iface_dict)` on each border router.

### Interface Data Structure

After configure, each border router has a `ScionRouter` extension.
`node.getScionInterfaces()` returns:

```python
{
  1: {                          # keyed by IFID
    "underlay": {"local": "10.101.0.150:50000", "remote": "10.101.0.151:50000"},
    "isd_as": "1-151",         # remote AS
    "link_to": "CHILD",        # CHILD | PARENT | CORE | PEER
    "mtu": 1500,
  },
  2: { ... },                   # second interface on same router
}
```

The `link_to` field encodes both link type and direction: the parent side
of a Transit link has `CHILD`, the child side has `PARENT`, and both sides
of a Core or Peer link have `CORE` / `PEER` respectively.

## How the Compiler Works

`ScionTopoCompiler._doCompile(emulator)` runs in three steps after
`emu.render()`.

### Step 1: Build the Router Letter Map

Some ASes have multiple border routers. The `.topo` format uses letter
suffixes (`-A`, `-B`, `-C`, …) to distinguish them. The compiler:

1. Iterates all `rnode` entries in the registry.
2. Filters to those with a `ScionRouter` extension **and** at least one
   SCION interface.
3. Groups router names by ASN and sorts them alphabetically.
4. Single router in AS → no suffix. Multiple routers → assign A, B, C, …
   in sorted order.

```python
# Result: Dict[(asn, router_name), letter_or_empty_string]
letter_map[(150, 'br0')] = 'A'
letter_map[(150, 'br1')] = 'B'
letter_map[(151, 'br0')] = ''   # single router, no letter
```

### Step 2: Write the ASes Section

For each ASN in the emulation (sorted):

1. Look up ISD membership via `ScionIsd.getAsIsds(asn)` → `[(isd, is_core)]`.
2. Construct the IA string: `str(IA(isd, asn))`.
3. **If core:** write `core/voting/authoritative/issuing: true` from
   `ScionAutonomousSystem.getAsAttributes(isd)`.
4. **If non-core:** write `cert_issuer: <issuer_IA>` from
   `ScionIsd.getCertIssuer((isd, asn))`.
5. **If MTU set:** write `mtu: <value>` from
   `ScionAutonomousSystem.getMtu()`.

### Step 3: Write the Links Section

This is the most complex step. Each physical link is stored twice in the
data — once per participating router. The compiler must emit each link
exactly once.

**Interface lookup table:** collect all SCION interfaces across all border
routers into `Dict[ia_str, List[(ifid, iface_dict, router_node)]]`, sorted
by IFID within each IA.

**Deduplication algorithm** using an `emitted: Set[(ia_str, ifid)]`:

For each interface (processed in sorted order by IA string, then IFID):

1. If already in `emitted` → skip.
2. If `link_to == PARENT` → mark emitted and skip (will be emitted from
   the parent's CHILD interface).
3. Otherwise (`CHILD`, `CORE`, or `PEER`):
   - Determine the partner's expected `link_to`: CHILD→PARENT, CORE→CORE,
     PEER→PEER.
   - Find the first unmatched interface in the remote AS that points back
     with the expected type.
   - Mark both endpoints as emitted.
   - Format endpoints using the letter map and write the link entry.

**Parallel links** (count > 1 in `addXcLink`/`addIxLink`) are correctly
paired by sorted IFID index, matching the allocation order in
`Scion.__create_link()`.

## Files Changed

| File | Change |
|---|---|
| `seedemu/compiler/ScionTopoCompiler.py` | New compiler class (~170 lines) |
| `seedemu/compiler/__init__.py` | Export `ScionTopoCompiler` |
| `seedemu/core/ScionAutonomousSystem.py` | Added `getMtu()`, `setUnderlay()`, `getUnderlay()` |
| `seedemu/layers/Scion.py` | Added `underlay_type` parameter to `addIxLink()`, `addXcLink()`, `_createLink()` |
| `tests/scion/scion_topo_generator/ScionTestCase.py` | Shared SCION test base class (moved from `tests/scion/`) |
| `tests/scion/scion_topo_generator/test-emulator/test_scion_topo_compiler.py` | 15 unit tests for `ScionTopoCompiler` |
| `examples/scion/scion-topo-generator/` | 3 example topology scripts (`two_cores.py`, `three_isds.py`, `core_triangle.py`) |

## Generating New Topologies

Example topology scripts live in this directory
(`examples/scion/scion-topo-generator/`). Each script builds a SEED SCION
emulation, renders it, and compiles it with `ScionTopoCompiler` to produce
a `topology.topo` file.
