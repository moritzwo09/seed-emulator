#!/usr/bin/env python3
"""
Topology: core triangle — 1 ISD, 3 core ASes in a full mesh, 6 leaf ASes.

  [AS150, mtu=1400]---Core---[AS151, mtu=1280]
         |  \               /  |
        Core  \           /   Core
         |     \         /     |
  [AS153]  [AS154-multi-homed] [AS155]
  mtu=1500   mtu=1350          mtu=1500
                 |
  [AS152, mtu=1500]---Core---+
         |                    |
    [AS156] [AS157]        (completes
    mtu=1500 mtu=1450       triangle)

Full core mesh: 150 <-> 151 <-> 152 <-> 150
Leaves per core:
  AS150 -> AS153, AS156 (via 152 subtree for AS156)
  AS151 -> AS155
  AS152 -> AS156, AS157

Special: AS154 is multi-homed — Transit from AS150 AND AS151,
giving it two independent uplinks to the core.

10 ASes, 1 ISD, varied MTUs, rich path diversity.
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

# IX layout:
#   ix100: AS150 <-> AS151  (Core)
#   ix101: AS151 <-> AS152  (Core)
#   ix102: AS152 <-> AS150  (Core)
#   ix103: AS150 -> AS153   (Transit)
#   ix104: AS150 -> AS154   (Transit, uplink 1 for multi-homed)
#   ix105: AS151 -> AS154   (Transit, uplink 2 for multi-homed)
#   ix106: AS151 -> AS155   (Transit)
#   ix107: AS152 -> AS156   (Transit)
#   ix108: AS152 -> AS157   (Transit)
ix_mtus = {100: 1280, 101: 1350, 102: 1400, 103: 1500, 104: 1350, 105: 1350, 106: 1500, 107: 1500, 108: 1450}
for ix, mtu in ix_mtus.items():
    base.createInternetExchange(ix, create_rs=False).getNetwork().setMtu(mtu)

# Core AS 150 (MTU 1400)
as150 = base.createAutonomousSystem(150)
scion_isd.addIsdAs(1, 150, is_core=True)
as150.createNetwork('net0').setMtu(1400)
as150.createControlService('cs1').joinNetwork('net0')
as150.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')  # <-> AS151
as150.createRouter('br1').joinNetwork('net0').joinNetwork('ix102')  # <-> AS152
as150.createRouter('br2').joinNetwork('net0').joinNetwork('ix103')  # -> AS153
as150.createRouter('br3').joinNetwork('net0').joinNetwork('ix104')  # -> AS154

# Core AS 151 (MTU 1280)
as151 = base.createAutonomousSystem(151)
scion_isd.addIsdAs(1, 151, is_core=True)
as151.createNetwork('net0').setMtu(1280)
as151.createControlService('cs1').joinNetwork('net0')
as151.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')  # <-> AS150
as151.createRouter('br1').joinNetwork('net0').joinNetwork('ix101')  # <-> AS152
as151.createRouter('br2').joinNetwork('net0').joinNetwork('ix105')  # -> AS154
as151.createRouter('br3').joinNetwork('net0').joinNetwork('ix106')  # -> AS155

# Core AS 152 (MTU 1500)
as152 = base.createAutonomousSystem(152)
scion_isd.addIsdAs(1, 152, is_core=True)
as152.createNetwork('net0')
as152.createControlService('cs1').joinNetwork('net0')
as152.createRouter('br0').joinNetwork('net0').joinNetwork('ix101')  # <-> AS151
as152.createRouter('br1').joinNetwork('net0').joinNetwork('ix102')  # <-> AS150
as152.createRouter('br2').joinNetwork('net0').joinNetwork('ix107')  # -> AS156
as152.createRouter('br3').joinNetwork('net0').joinNetwork('ix108')  # -> AS157

# Leaf AS 153 — single-homed under AS150
as153 = base.createAutonomousSystem(153)
scion_isd.addIsdAs(1, 153, is_core=False)
scion_isd.setCertIssuer((1, 153), issuer=150)
as153.createNetwork('net0')
as153.createControlService('cs1').joinNetwork('net0')
as153.createRouter('br0').joinNetwork('net0').joinNetwork('ix103')

# Leaf AS 154 (MTU 1350) — multi-homed: Transit from AS150 AND AS151
as154 = base.createAutonomousSystem(154)
scion_isd.addIsdAs(1, 154, is_core=False)
scion_isd.setCertIssuer((1, 154), issuer=150)
as154.createNetwork('net0').setMtu(1350)
as154.createControlService('cs1').joinNetwork('net0')
as154.createRouter('br0').joinNetwork('net0').joinNetwork('ix104')  # uplink to AS150
as154.createRouter('br1').joinNetwork('net0').joinNetwork('ix105')  # uplink to AS151

# Leaf AS 155 — single-homed under AS151
as155 = base.createAutonomousSystem(155)
scion_isd.addIsdAs(1, 155, is_core=False)
scion_isd.setCertIssuer((1, 155), issuer=151)
as155.createNetwork('net0')
as155.createControlService('cs1').joinNetwork('net0')
as155.createRouter('br0').joinNetwork('net0').joinNetwork('ix106')

# Leaf AS 156 — single-homed under AS152
as156 = base.createAutonomousSystem(156)
scion_isd.addIsdAs(1, 156, is_core=False)
scion_isd.setCertIssuer((1, 156), issuer=152)
as156.createNetwork('net0')
as156.createControlService('cs1').joinNetwork('net0')
as156.createRouter('br0').joinNetwork('net0').joinNetwork('ix107')

# Leaf AS 157 (MTU 1450) — single-homed under AS152
as157 = base.createAutonomousSystem(157)
scion_isd.addIsdAs(1, 157, is_core=False)
scion_isd.setCertIssuer((1, 157), issuer=152)
as157.createNetwork('net0').setMtu(1450)
as157.createControlService('cs1').joinNetwork('net0')
as157.createRouter('br0').joinNetwork('net0').joinNetwork('ix108')

# Core triangle
scion.addIxLink(100, (1, 150), (1, 151), ScLinkType.Core)
scion.addIxLink(101, (1, 151), (1, 152), ScLinkType.Core)
scion.addIxLink(102, (1, 152), (1, 150), ScLinkType.Core)

# Transit links
scion.addIxLink(103, (1, 150), (1, 153), ScLinkType.Transit)
scion.addIxLink(104, (1, 150), (1, 154), ScLinkType.Transit)
scion.addIxLink(105, (1, 151), (1, 154), ScLinkType.Transit)
scion.addIxLink(106, (1, 151), (1, 155), ScLinkType.Transit)
scion.addIxLink(107, (1, 152), (1, 156), ScLinkType.Transit)
scion.addIxLink(108, (1, 152), (1, 157), ScLinkType.Transit)

emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(scion_isd)
emu.addLayer(scion)

with patch.object(ScionIsd, 'render', return_value=None), \
     patch.object(ScionRouting, '_ScionRouting__install_scion', return_value=None), \
     patch.object(ScionRouting, 'render', return_value=None):
    emu.render()

emu.compile(ScionTopoCompiler(), os.path.join(_HERE, 'output-core-triangle'), override=True)
