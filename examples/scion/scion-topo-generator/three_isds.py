#!/usr/bin/env python3
"""
Topology: three ISDs with a full core triangle between them.

  ISD 1            ISD 2            ISD 3
  [AS110]---Core---[AS210]---Core---[AS170]
     |  \___________________________/  |
     |            Core                 |
  [AS111]                           [AS171]
  [AS112]       [AS211]             [AS172]
                [AS212]

Core ASes form a triangle: 110 <-> 210 <-> 310 <-> 110
Each ISD has 2 leaf ASes.

Path diversity: AS111 can reach AS171 via:
  - 110 -> 170
  - 110 -> 210 -> 170

9 ASes, 3 ISDs, varied MTUs.
"""

import os
from unittest.mock import patch

from seedemu.compiler import ScionTopoCompiler
from seedemu.core import Emulator
from seedemu.layers import ScionBase, ScionRouting, ScionIsd, Scion
from seedemu.layers.Scion import LinkType as ScLinkType

_HERE = os.path.dirname(os.path.abspath(__file__))

emu = Emulator()
base = ScionBase()
routing = ScionRouting()
scion_isd = ScionIsd()
scion = Scion()

base.createIsolationDomain(1)
base.createIsolationDomain(2)
base.createIsolationDomain(3)

# IX layout:
#   ix100: AS110 <-> AS210  (Core, cross-ISD)
#   ix101: AS210 <-> AS170  (Core, cross-ISD)
#   ix102: AS170 <-> AS110  (Core, cross-ISD)
#   ix103: AS110 -> AS111   (Transit)
#   ix104: AS110 -> AS112   (Transit)
#   ix105: AS210 -> AS211   (Transit)
#   ix106: AS210 -> AS212   (Transit)
#   ix107: AS170 -> AS171   (Transit)
#   ix108: AS170 -> AS172   (Transit)
ix_mtus = {100: 1280, 101: 1350, 102: 1400, 103: 1500, 104: 1500, 105: 1500, 106: 1500, 107: 1450, 108: 1450}
for ix, mtu in ix_mtus.items():
    base.createInternetExchange(ix, create_rs=False).getNetwork().setMtu(mtu)

# ISD 1 — Core AS 110 (MTU 1400)
as110 = base.createAutonomousSystem(110)
scion_isd.addIsdAs(1, 110, is_core=True)
as110.createNetwork('net0').setMtu(1400)
as110.createControlService('cs1').joinNetwork('net0')
as110.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')  # to ISD 2
as110.createRouter('br1').joinNetwork('net0').joinNetwork('ix102')  # to ISD 3
as110.createRouter('br2').joinNetwork('net0').joinNetwork('ix103')  # to AS111
as110.createRouter('br3').joinNetwork('net0').joinNetwork('ix104')  # to AS112

# ISD 2 — Core AS 210 (MTU 1280)
as210 = base.createAutonomousSystem(210)
scion_isd.addIsdAs(2, 210, is_core=True)
as210.createNetwork('net0').setMtu(1280)
as210.createControlService('cs1').joinNetwork('net0')
as210.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')  # to ISD 1
as210.createRouter('br1').joinNetwork('net0').joinNetwork('ix101')  # to ISD 3
as210.createRouter('br2').joinNetwork('net0').joinNetwork('ix105')  # to AS211
as210.createRouter('br3').joinNetwork('net0').joinNetwork('ix106')  # to AS212

# ISD 3 — Core AS 170 (MTU 1500)
as170 = base.createAutonomousSystem(170)
scion_isd.addIsdAs(3, 170, is_core=True)
as170.createNetwork('net0')
as170.createControlService('cs1').joinNetwork('net0')
as170.createRouter('br0').joinNetwork('net0').joinNetwork('ix101')  # to ISD 2
as170.createRouter('br1').joinNetwork('net0').joinNetwork('ix102')  # to ISD 1
as170.createRouter('br2').joinNetwork('net0').joinNetwork('ix107')  # to AS171
as170.createRouter('br3').joinNetwork('net0').joinNetwork('ix108')  # to AS172

# ISD 1 leaves
for asn, ix in {111: 103, 112: 104}.items():
    as_ = base.createAutonomousSystem(asn)
    scion_isd.addIsdAs(1, asn, is_core=False)
    scion_isd.setCertIssuer((1, asn), issuer=110)
    as_.createNetwork('net0').setMtu(1350)
    as_.createControlService('cs1').joinNetwork('net0')
    as_.createRouter('br0').joinNetwork('net0').joinNetwork(f'ix{ix}')

# ISD 2 leaves
for asn, ix in {211: 105, 212: 106}.items():
    as_ = base.createAutonomousSystem(asn)
    scion_isd.addIsdAs(2, asn, is_core=False)
    scion_isd.setCertIssuer((2, asn), issuer=210)
    as_.createNetwork('net0')
    as_.createControlService('cs1').joinNetwork('net0')
    as_.createRouter('br0').joinNetwork('net0').joinNetwork(f'ix{ix}')

# ISD 3 leaves
for asn, ix in {171: 107, 172: 108}.items():
    as_ = base.createAutonomousSystem(asn)
    scion_isd.addIsdAs(3, asn, is_core=False)
    scion_isd.setCertIssuer((3, asn), issuer=170)
    as_.createNetwork('net0').setMtu(1450)
    as_.createControlService('cs1').joinNetwork('net0')
    as_.createRouter('br0').joinNetwork('net0').joinNetwork(f'ix{ix}')

# Core triangle between ISDs
scion.addIxLink(100, (1, 110), (2, 210), ScLinkType.Core)
scion.addIxLink(101, (2, 210), (3, 170), ScLinkType.Core)
scion.addIxLink(102, (3, 170), (1, 110), ScLinkType.Core)

# Transit links within each ISD
scion.addIxLink(103, (1, 110), (1, 111), ScLinkType.Transit)
scion.addIxLink(104, (1, 110), (1, 112), ScLinkType.Transit)
scion.addIxLink(105, (2, 210), (2, 211), ScLinkType.Transit)
scion.addIxLink(106, (2, 210), (2, 212), ScLinkType.Transit)
scion.addIxLink(107, (3, 170), (3, 171), ScLinkType.Transit)
scion.addIxLink(108, (3, 170), (3, 172), ScLinkType.Transit)

emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(scion_isd)
emu.addLayer(scion)

with patch.object(ScionIsd, 'render', return_value=None), \
     patch.object(ScionRouting, '_ScionRouting__install_scion', return_value=None), \
     patch.object(ScionRouting, 'render', return_value=None):
    emu.render()

emu.compile(ScionTopoCompiler(), os.path.join(_HERE, 'output-three-isds'), override=True)
