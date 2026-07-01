#!/usr/bin/env python3
"""Test ScionTopoCompiler produces a valid .topo file from a SCION emulation."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add repo root to path when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import yaml

from seedemu.compiler import ScionTopoCompiler
from seedemu.core import Emulator
from seedemu.layers import ScionBase, ScionRouting, ScionIsd, Scion, Ospf
from seedemu.layers.Scion import LinkType

# Avoid importing unused Binding/Filter


def build_emulator() -> Emulator:
    """Build the scion_bgp_mixed topology (SCION-only variant, no BGP layers)."""
    emu = Emulator()
    base = ScionBase()
    routing = ScionRouting(static_routing=True)
    ospf = Ospf()
    scion_isd = ScionIsd()
    scion = Scion()

    base.createIsolationDomain(1)
    base.createIsolationDomain(2)

    base.createInternetExchange(100, create_rs=False)
    base.createInternetExchange(101, create_rs=False)
    base.createInternetExchange(102, create_rs=False)
    base.createInternetExchange(103, create_rs=False)
    base.createInternetExchange(104, create_rs=False)

    # Core AS 1-150 — one router per IX it participates in
    as150 = base.createAutonomousSystem(150)
    scion_isd.addIsdAs(1, 150, is_core=True)
    as150.createNetwork('net0')
    as150.createControlService('cs1').joinNetwork('net0')
    as150.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')
    as150.createRouter('br1').joinNetwork('net0').joinNetwork('ix101')
    as150.createRouter('br2').joinNetwork('net0').joinNetwork('ix102')
    as150.createRouter('br3').joinNetwork('net0').joinNetwork('ix103')

    # Non-core ASes in ISD 1
    for asn, ix in {151: 101, 152: 102, 153: 103}.items():
        as_ = base.createAutonomousSystem(asn)
        scion_isd.addIsdAs(1, asn, is_core=False)
        scion_isd.setCertIssuer((1, asn), issuer=150)
        as_.createNetwork('net0')
        as_.createControlService('cs1').joinNetwork('net0')
        as_.createRouter('br0').joinNetwork('net0').joinNetwork(f'ix{ix}')

    # Core AS 2-160
    as160 = base.createAutonomousSystem(160)
    scion_isd.addIsdAs(2, 160, is_core=True)
    as160.createNetwork('net0')
    as160.createControlService('cs1').joinNetwork('net0')
    as160.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')
    as160.createRouter('br1').joinNetwork('net0').joinNetwork('ix104')

    # Non-core AS in ISD 2
    as161 = base.createAutonomousSystem(161)
    scion_isd.addIsdAs(2, 161, is_core=False)
    scion_isd.setCertIssuer((2, 161), issuer=160)
    as161.createNetwork('net0')
    as161.createControlService('cs1').joinNetwork('net0')
    as161.createRouter('br0').joinNetwork('net0').joinNetwork('ix104')

    # SCION links
    scion.addIxLink(100, (1, 150), (2, 160), LinkType.Core)
    scion.addIxLink(101, (1, 150), (1, 151), LinkType.Transit)
    scion.addIxLink(102, (1, 150), (1, 152), LinkType.Transit)
    scion.addIxLink(103, (1, 150), (1, 153), LinkType.Transit)
    scion.addIxLink(104, (2, 160), (2, 161), LinkType.Transit)

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(ospf)
    emu.addLayer(scion_isd)
    emu.addLayer(scion)

    return emu


class TestScionTopoCompiler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        emu = build_emulator()
        # In a test environment without Docker or scion-pki:
        # - ScionIsd.render() calls scion-pki (not available) → no-op it
        # - ScionRouting.__install_scion() tries to build Docker images → no-op it
        # - ScionRouting.render() writes container config files → no-op it
        # configure() runs normally on all layers (sets attributes, promotes
        # routers to ScionRouter, allocates IFIDs).
        with patch.object(ScionIsd, 'render', return_value=None), \
             patch.object(ScionRouting, '_ScionRouting__install_scion', return_value=None), \
             patch.object(ScionRouting, 'render', return_value=None):
            emu.render()
        cls.tmpdir = tempfile.mkdtemp()
        emu.compile(ScionTopoCompiler(), cls.tmpdir, override=True)
        topo_path = os.path.join(cls.tmpdir, 'topology.topo')
        with open(topo_path) as f:
            cls.topo = yaml.safe_load(f)

    def test_output_file_exists(self):
        self.assertIn('topology.topo', os.listdir(self.tmpdir))

    def test_ases_section_present(self):
        self.assertIn('ASes', self.topo)

    def test_links_section_present(self):
        self.assertIn('links', self.topo)

    def test_core_as_isd1(self):
        ases = self.topo['ASes']
        self.assertIn('1-150', ases)
        as_entry = ases['1-150']
        self.assertTrue(as_entry.get('core'))
        self.assertTrue(as_entry.get('voting'))
        self.assertTrue(as_entry.get('authoritative'))
        self.assertTrue(as_entry.get('issuing'))

    def test_core_as_isd2(self):
        ases = self.topo['ASes']
        self.assertIn('2-160', ases)
        as_entry = ases['2-160']
        self.assertTrue(as_entry.get('core'))

    def test_non_core_as_has_cert_issuer(self):
        ases = self.topo['ASes']
        for ia_str in ['1-151', '1-152', '1-153']:
            self.assertIn(ia_str, ases, f"{ia_str} missing from ASes")
            entry = ases[ia_str]
            self.assertIn('cert_issuer', entry, f"{ia_str} missing cert_issuer")
            self.assertEqual(entry['cert_issuer'], '1-150')

    def test_non_core_as_isd2_has_cert_issuer(self):
        ases = self.topo['ASes']
        self.assertIn('2-161', ases)
        self.assertEqual(ases['2-161']['cert_issuer'], '2-160')

    def test_all_six_ases_present(self):
        ases = self.topo['ASes']
        expected = {'1-150', '1-151', '1-152', '1-153', '2-160', '2-161'}
        self.assertEqual(set(ases.keys()), expected)

    def test_link_count(self):
        # 5 links total: 1 CORE + 3 CHILD (isd1) + 1 CHILD (isd2)
        self.assertEqual(len(self.topo['links']), 5)

    def test_core_link_present(self):
        core_links = [l for l in self.topo['links'] if l['linkAtoB'] == 'CORE']
        self.assertEqual(len(core_links), 1)

    def test_child_links_present(self):
        child_links = [l for l in self.topo['links'] if l['linkAtoB'] == 'CHILD']
        self.assertEqual(len(child_links), 4)

    def test_link_endpoints_have_ifids(self):
        for link in self.topo['links']:
            self.assertIn('#', link['a'], f"missing IFID in a: {link['a']}")
            self.assertIn('#', link['b'], f"missing IFID in b: {link['b']}")

    def test_mtu_in_link(self):
        for link in self.topo['links']:
            if 'mtu' in link:
                self.assertIsInstance(link['mtu'], int)
                self.assertGreater(link['mtu'], 0)

    def test_multi_router_letter_notation(self):
        # AS 150 has br0..br3 (one per IX), so endpoints should use letter notation
        endpoints = [l['a'] for l in self.topo['links']] + [l['b'] for l in self.topo['links']]
        as150_eps = [ep for ep in endpoints if ep.startswith('1-150-')]
        self.assertGreater(len(as150_eps), 0, "AS 150 should have letter-suffixed endpoints")

    def test_single_router_no_letter(self):
        # AS 151 has only br0, so no letter suffix
        endpoints = [l['a'] for l in self.topo['links']] + [l['b'] for l in self.topo['links']]
        as151_eps = [ep for ep in endpoints if ep.startswith('1-151')]
        for ep in as151_eps:
            self.assertNotIn('-A#', ep, f"Single-router AS 151 should not have letter: {ep}")
            self.assertNotIn('-B#', ep, f"Single-router AS 151 should not have letter: {ep}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
