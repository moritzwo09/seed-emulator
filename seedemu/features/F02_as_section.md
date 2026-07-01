# F02 — ASes Section Generation

## Goal

Generate the `ASes:` block of the `.topo` file from `ScionBase` and `ScionIsd`
layer data available after `configure()` has run.

## Input Sources

| Data | Source |
|---|---|
| All ASNs | `ScionBase.getAsns()` |
| ISD membership + core status | `ScionIsd.getAsIsds(asn)` → `[(isd, is_core)]` |
| Core attributes | `ScionAutonomousSystem.getAsAttributes(isd)` |
| Non-core cert issuer | `ScionIsd.getCertIssuer((isd, asn))` → issuer ASN |
| AS MTU | `ScionAutonomousSystem.getMtu()` (new getter) |

## Algorithm

```
for asn in sorted(base_layer.getAsns()):
    as_ = base_layer.getAutonomousSystem(asn)
    [(isd, is_core)] = scion_isd.getAsIsds(asn)
    ia_str = str(IA(isd, asn))

    write: '  "<ia_str>":\n'

    if is_core:
        attrs = as_.getAsAttributes(isd)  # {'core','voting','authoritative','issuing'}
        for attr in ['core', 'voting', 'authoritative', 'issuing']:
            if attr in attrs:
                write: '    {attr}: true\n'
    else:
        issuer_asn = scion_isd.getCertIssuer((isd, asn))
        issuer_ia = str(IA(isd, issuer_asn))
        write: '    cert_issuer: {issuer_ia}\n'

    mtu = as_.getMtu()
    if mtu is not None:
        write: '    mtu: {mtu}\n'
```

## Required Code Changes

### `seedemu/core/ScionAutonomousSystem.py`

Add a public getter for MTU (currently stored in private `__mtu`):

```python
def getMtu(self) -> Optional[int]:
    """Get the AS-wide MTU (minimum of all internal network MTUs), or None before configure()."""
    return self.__mtu
```

### `seedemu/layers/ScionIsd.py`

`getCertIssuer()` already exists (line 106). No changes needed.

## Example Output

```yaml
ASes:
  "1-ff00:0:150":
    core: true
    voting: true
    authoritative: true
    issuing: true
    mtu: 1400
  "1-ff00:0:151":
    cert_issuer: 1-ff00:0:150
  "2-ff00:0:160":
    core: true
    voting: true
    authoritative: true
    issuing: true
```

## Notes

- Per the existing `ScionIsd` layer, each AS is restricted to exactly one ISD
  (multi-ISD membership raises an assertion error). The compiler enforces this too.
- `underlay: UDP/IPv6` at the AS level is not currently tracked in `ScionAutonomousSystem`
  and is excluded from this version (see F05).
