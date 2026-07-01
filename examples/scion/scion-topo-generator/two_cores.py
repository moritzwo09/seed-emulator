#!/usr/bin/env python3
"""
Topology: two-core single ISD with a multi-homed leaf.

  ISD 1
                Core
  [AS150, mtu=1400] ------- [AS151, mtu=1280]
      |      \                  /      |
   Transit  Transit          Transit  Transit
      |        \            /          |
  [AS152]    [AS155 multi-homed]    [AS153]
  mtu=1500    mtu=1350              mtu=1500
                  |
               [AS154]
               mtu=1500  (child of 155)

AS155 is multi-homed: it has a Transit link to AS150 AND to AS151,
giving it two disjoint paths to any destination.
AS154 is a leaf of AS155 and inherits multi-path connectivity.

8 ASes, 1 ISD, varied MTUs.
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
#   ix101: AS150 -> AS152   (Transit)
#   ix102: AS150 -> AS155   (Transit, first uplink for multi-homed AS155)
#   ix103: AS151 -> AS153   (Transit)
#   ix104: AS151 -> AS155   (Transit, second uplink for multi-homed AS155)
#   ix105: AS155 -> AS154   (Transit)
ix_mtus = {100: 1280, 101: 1500, 102: 1350, 103: 1500, 104: 1350, 105: 1500}
for ix, mtu in ix_mtus.items():
    base.createInternetExchange(ix, create_rs=False).getNetwork().setMtu(mtu)

# Core AS 150 (MTU 1400) — participates in ix100, ix101, ix102
as150 = base.createAutonomousSystem(150)
scion_isd.addIsdAs(1, 150, is_core=True)
as150.createNetwork('net0').setMtu(1400)
as150.createControlService('cs1').joinNetwork('net0')
as150.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')
as150.createRouter('br1').joinNetwork('net0').joinNetwork('ix101')
as150.createRouter('br2').joinNetwork('net0').joinNetwork('ix102')

# Core AS 151 (MTU 1280) — participates in ix100, ix103, ix104
as151 = base.createAutonomousSystem(151)
scion_isd.addIsdAs(1, 151, is_core=True)
as151.createNetwork('net0').setMtu(1280)
as151.createControlService('cs1').joinNetwork('net0')
as151.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')
as151.createRouter('br1').joinNetwork('net0').joinNetwork('ix103')
as151.createRouter('br2').joinNetwork('net0').joinNetwork('ix104')

# Leaf AS 152 — single-homed under AS150
as152 = base.createAutonomousSystem(152)
scion_isd.addIsdAs(1, 152, is_core=False)
scion_isd.setCertIssuer((1, 152), issuer=150)
as152.createNetwork('net0')
as152.createControlService('cs1').joinNetwork('net0')
as152.createRouter('br0').joinNetwork('net0').joinNetwork('ix101')

# Leaf AS 153 — single-homed under AS151
as153 = base.createAutonomousSystem(153)
scion_isd.addIsdAs(1, 153, is_core=False)
scion_isd.setCertIssuer((1, 153), issuer=151)
as153.createNetwork('net0')
as153.createControlService('cs1').joinNetwork('net0')
as153.createRouter('br0').joinNetwork('net0').joinNetwork('ix103')

# Leaf AS 154 — child of AS155 (inherits multi-path via 155)
as154 = base.createAutonomousSystem(154)
scion_isd.addIsdAs(1, 154, is_core=False)
scion_isd.setCertIssuer((1, 154), issuer=155)
as154.createNetwork('net0')
as154.createControlService('cs1').joinNetwork('net0')
as154.createRouter('br0').joinNetwork('net0').joinNetwork('ix105')

# AS 155 (MTU 1350) — multi-homed: Transit to AS150 AND AS151
as155 = base.createAutonomousSystem(155)
scion_isd.addIsdAs(1, 155, is_core=False)
scion_isd.setCertIssuer((1, 155), issuer=150)
as155.createNetwork('net0').setMtu(1350)
as155.createControlService('cs1').joinNetwork('net0')
as155.createRouter('br0').joinNetwork('net0').joinNetwork('ix102')
as155.createRouter('br1').joinNetwork('net0').joinNetwork('ix104')
as155.createRouter('br2').joinNetwork('net0').joinNetwork('ix105')

# Links
scion.addIxLink(100, (1, 150), (1, 151), ScLinkType.Core)
scion.addIxLink(101, (1, 150), (1, 152), ScLinkType.Transit)
scion.addIxLink(102, (1, 150), (1, 155), ScLinkType.Transit)
scion.addIxLink(103, (1, 151), (1, 153), ScLinkType.Transit)
scion.addIxLink(104, (1, 151), (1, 155), ScLinkType.Transit)
scion.addIxLink(105, (1, 155), (1, 154), ScLinkType.Transit)

emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(scion_isd)
emu.addLayer(scion)

with patch.object(ScionIsd, 'render', return_value=None), \
     patch.object(ScionRouting, '_ScionRouting__install_scion', return_value=None), \
     patch.object(ScionRouting, 'render', return_value=None):
    emu.render()

emu.compile(ScionTopoCompiler(), os.path.join(_HERE, 'output-two-cores'), override=True)
