# F03 — Router Letter Notation

## Goal

The `.topo` link format uses letter suffixes to distinguish multiple border
routers within the same AS: `1-ff00:0:120-A#6`, `1-ff00:0:120-B#3`. This
feature builds the mapping `(asn, router_name) -> letter_suffix`.

## When Letter Suffixes Apply

- AS has exactly **1** border router with SCION interfaces → **no suffix**: `1-ff00:0:110#1`
- AS has **2+** border routers with SCION interfaces → **letter suffix**: `1-ff00:0:120-A#6`

## Algorithm

Runs after `configure()` when `ScionRouter` extensions are installed on rnodes.

```
routers_by_asn = defaultdict(list)

for each (scope, type, name), node in registry.getAll():
    if type != 'rnode': continue
    if not node.hasExtension('ScionRouter'): continue
    if not node.getScionInterfaces(): continue          # skip routers with no SCION links
    routers_by_asn[node.getAsn()].append(name)

letter_map = {}
for asn, names in routers_by_asn.items():
    names.sort()                                       # alphabetical order → stable assignment
    if len(names) == 1:
        letter_map[(asn, names[0])] = ''              # single router: no letter
    else:
        for i, name in enumerate(names):
            letter_map[(asn, name)] = chr(ord('A') + i)  # A, B, C, ...
```

## How to Apply

```python
def format_endpoint(ia_str, rnode, ifid, letter_map):
    letter = letter_map.get((rnode.getAsn(), rnode.getName()), '')
    if letter:
        return f"{ia_str}-{letter}#{ifid}"
    return f"{ia_str}#{ifid}"
```

## Example

AS 150 has routers `br0`, `br1`, `br2`, `br3` — all with SCION interfaces:
```
letter_map[(150, 'br0')] = 'A'
letter_map[(150, 'br1')] = 'B'
letter_map[(150, 'br2')] = 'C'
letter_map[(150, 'br3')] = 'D'
```
→ endpoints: `1-ff00:0:150-A#1`, `1-ff00:0:150-B#2`, etc.

AS 151 has only `br0` → no letter:
```
letter_map[(151, 'br0')] = ''
```
→ endpoints: `1-ff00:0:151#1`

## Notes

- Router names are sorted alphabetically, so the assignment is deterministic.
- Routers that exist in the AS but have no SCION interfaces are not included
  (they don't appear in any link and need no letter).
- No new public APIs required — uses `node.hasExtension('ScionRouter')` and
  `node.getScionInterfaces()` which are already public.
