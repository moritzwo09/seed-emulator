# F04 — Links Section Generation

## Goal

Generate the `links:` block by iterating over SCION interface data stored in
`ScionRouter` extensions after `configure()` has run.

## Data Model

After `Scion._configure_links()` runs, each border router node has SCION
interfaces registered via `ScionRouter.addScionInterface(ifid, iface)`.

Each `iface` dict contains:
```python
{
    "underlay": {"local": "ip:port", "remote": "ip:port"},
    "isd_as": "1-ff00:0:151",   # remote AS IA string
    "link_to": "CHILD",          # CHILD | PARENT | CORE | PEER
    "mtu": 1400,
}
# For PEER links only:
#   "remote_interface_id": 42
```

Link type semantics:
- `CHILD`: parent side of a Transit link → emit as `linkAtoB: CHILD`
- `PARENT`: child side of a Transit link → **skip** (link is emitted from CHILD side)
- `CORE`: one end of a Core link → emit once (deduplicate)
- `PEER`: one end of a Peer link → emit once (deduplicate)

## Interface Lookup Structure

```
all_ifaces: Dict[ia_str, List[(ifid, iface_dict, rnode)]]
```
Built by iterating all `rnode` entries in the registry and collecting their
SCION interfaces, keyed by the local IA string. Each list is sorted by IFID.

## Deduplication Strategy

A set `emitted: Set[(ia_str, ifid)]` tracks which local interfaces have been
included in a link entry.

For each `(local_ia_str, ifid, iface, rnode)` (processed in sorted order):
1. Skip if already in `emitted`.
2. If `link_to == PARENT`: mark emitted and skip.
3. Otherwise find the **first unmatched** partner interface in the remote AS:
   - `remote_ia_str = iface['isd_as']`
   - partner `link_to`: CHILD→PARENT, CORE→CORE, PEER→PEER
   - Filter: remote interface must have `isd_as == local_ia_str`, matching `link_to`, and not yet emitted
   - Sort candidates by IFID; take the first → stable matching for parallel links
4. Add both `(local_ia_str, local_ifid)` and `(remote_ia_str, remote_ifid)` to `emitted`.
5. Emit the link entry.

## Link Entry Format

```python
a_ep = format_endpoint(local_ia_str, rnode, ifid, letter_map)
b_ep = format_endpoint(remote_ia_str, r_rnode, r_ifid, letter_map)
link_ato_b = {'CHILD': 'CHILD', 'CORE': 'CORE', 'PEER': 'PEER'}[link_to]
```

Output:
```yaml
  - {a: "1-ff00:0:150-A#1", b: "1-ff00:0:151#1", linkAtoB: CHILD}
```

## Parallel Links

When two ASes have N parallel links (count > 1 in `addXcLink`/`addIxLink`),
they appear as N separate `(local_ia, ifid)` entries pointing to the same
remote AS. The deduplication algorithm pairs them by sorted IFID index, which
matches the allocation order in `Scion.__create_link()`.

## Required Code Changes

No changes to existing layer classes are strictly required. The compiler reads
data already accessible via:
- `registry.getAll()` → iterate all nodes
- `node.hasExtension('ScionRouter')` → check for SCION capability
- `node.getScionInterfaces()` → get `Dict[int, Dict]`

(Optional future improvement: expose `Scion.getXcLinks()` / `Scion.getIxLinks()`
for a layer-data-driven approach. Not needed for the initial implementation.)
