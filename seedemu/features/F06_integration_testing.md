# F06 — Compiler Integration & Testing

## Goal

Wire the `ScionTopoCompiler` into the framework and verify it against a known
SCION topology.

## Compiler Class

**File:** `seedemu/compiler/ScionTopoCompiler.py`

Inherits from `Compiler` (seedemu/core/Compiler.py). Implements:
- `getName()` → `'ScionTopoCompiler'`
- `optionHandlingCapabilities()` → `OptionHandling.UNSUPPORTED`
- `_doCompile(emulator)` — CWD is already set to the output folder by `compile()`

Output file: `topology.topo` in the output directory.

## Export

Add to `seedemu/compiler/__init__.py`:
```python
from .ScionTopoCompiler import ScionTopoCompiler
```

## Usage Example

```python
from seedemu.compiler import ScionTopoCompiler

emu.render()
emu.compile(ScionTopoCompiler(), './output')
# ./output/topology.topo is created
```

## Test

**File:** `tests/scion/test_scion_topo_compiler.py`

Use the topology from `tests/scion/scion_bgp_mixed/emulator-code/test-emulator.py`
(2 ISDs, 1 core AS per ISD, 3+1 non-core ASes, 5 IX links).

```python
import yaml, tempfile, os
from seedemu.compiler import ScionTopoCompiler
# ... build topology ...
emu.render()
with tempfile.TemporaryDirectory() as tmpdir:
    emu.compile(ScionTopoCompiler(), tmpdir, override=True)
    with open(os.path.join(tmpdir, 'topology.topo')) as f:
        topo = yaml.safe_load(f)

# Assert AS section
assert '1-ff00:0:150' in topo['ASes']
assert topo['ASes']['1-ff00:0:150']['core'] == True
assert '1-ff00:0:151' in topo['ASes']
assert 'cert_issuer' in topo['ASes']['1-ff00:0:151']

# Assert links section
links = topo['links']
link_ato_bs = {lnk['linkAtoB'] for lnk in links}
assert 'CORE' in link_ato_bs   # inter-ISD core link
assert 'CHILD' in link_ato_bs  # transit links
```

## Verification Steps

1. `source development.env && python tests/scion/test_scion_topo_compiler.py`
2. Manually inspect output against `seedemu/topology/tiny.topo` for format parity
3. `flake8 seedemu/compiler/ScionTopoCompiler.py`
4. Optional: feed output to `scion-pki testcrypto` to confirm SCION tooling accepts it

## Notes

- The test does not require a running Docker environment — it only builds and
  compiles the emulation object in memory (no `scion-pki` call, no Docker).
- ScionIsd's `render()` calls `scion-pki testcrypto` — to avoid this in tests,
  call `emu.render()` with the ScionIsd layer omitted, or mock the subprocess call.
  Alternatively, run with `ScionRouting` + `Scion` + `ScionBase` only (no `ScionIsd`)
  and skip crypto generation for the topology test.
