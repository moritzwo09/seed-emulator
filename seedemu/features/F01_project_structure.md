# F01 — Project Structure

## Goal

Add a `ScionTopoCompiler` that takes a fully-rendered SEED emulation (containing
`ScionBase`, `ScionIsd`, and `Scion` layers) and writes a standards-compliant
SCION `.topo` file to the output directory.

## Motivation

The existing `ScionIsd.__gen_topofile()` generates only the `ASes:` block of a
`.topo` file, and only for internal use by `scion-pki testcrypto`. No public
compiler exists that produces the full topology file (with the `links:` block)
that external SCION tools, documentation, or reproducibility workflows require.

## Usage

```python
emu.render()
emu.compile(ScionTopoCompiler(), './output')
# produces: ./output/topology.topo
```

## Architecture

```
emu.render()
  └── configure() pass on all layers
        ├── ScionIsd.configure() → sets core/non-core attributes on ScionAutonomousSystem
        ├── ScionRouting.configure() → derives AS MTU, promotes routers to ScionRouter
        └── Scion.configure() → allocates IFIDs, creates ScionRouter interfaces

emu.compile(ScionTopoCompiler(), './output')
  └── ScionTopoCompiler._doCompile(emulator)
        ├── Read ScionBase + ScionIsd layers → ASes section
        ├── Read ScionRouter.getScionInterfaces() on all rnodes → links section
        └── Write topology.topo
```

## Files Involved

| File | Role |
|---|---|
| `seedemu/compiler/ScionTopoCompiler.py` | New compiler class |
| `seedemu/compiler/__init__.py` | Export `ScionTopoCompiler` |
| `seedemu/core/ScionAutonomousSystem.py` | Add `getMtu()` public getter |
| `seedemu/layers/Scion.py` | Add `getXcLinks()`, `getIxLinks()` |
| `seedemu/features/F02_as_section.md` | Spec: ASes block generation |
| `seedemu/features/F03_router_letter_mapping.md` | Spec: multi-router letter notation |
| `seedemu/features/F04_links_section.md` | Spec: links block generation |
| `seedemu/features/F05_link_properties.md` | Spec: optional link properties |
| `seedemu/features/F06_integration_testing.md` | Spec: integration and tests |

## Output Format

See `seedemu/topology/tiny.topo` and `default.topo` for reference. The output
follows the SCION `.topo` YAML schema:

```yaml
ASes:
  "<ISD>-<ASN>":
    core: true        # core ASes
    voting: true
    authoritative: true
    issuing: true
    mtu: 1400         # optional
  "<ISD>-<ASN>":
    cert_issuer: <ISD>-<ASN>   # non-core ASes

links:
  - {a: "<IA>#<IFID>", b: "<IA>-B#<IFID>", linkAtoB: CHILD}
  - {a: "<IA>#<IFID>", b: "<IA>#<IFID>", linkAtoB: CORE, mtu: 1280}
```
