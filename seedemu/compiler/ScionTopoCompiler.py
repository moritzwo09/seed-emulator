from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from seedemu.core import Emulator
from seedemu.core.Compiler import Compiler, OptionHandling
from seedemu.core.ScionAutonomousSystem import IA, ScionAutonomousSystem
from seedemu.layers import ScionBase
from seedemu.layers.ScionIsd import ScionIsd


class ScionTopoCompiler(Compiler):
    """!
    @brief Compiles a rendered SCION emulation into a standard .topo file.

    Produces a single `topology.topo` file in the output directory that follows
    the SCION topology file format (see seedemu/topology/*.topo for examples).

    Usage::

        emu.render()
        emu.compile(ScionTopoCompiler(), './output')
        # ./output/topology.topo is created
    """

    def getName(self) -> str:
        return 'ScionTopo'

    def optionHandlingCapabilities(self) -> OptionHandling:
        return OptionHandling.UNSUPPORTED

    @staticmethod
    def _to_scion_ia(ia_str: str) -> str:
        """Convert an ISD-AS string to SCION-native colon-hex format.

        BGP-range decimal ASNs (e.g. '1-150') are mapped to the equivalent
        SCION-native ff00:0:hex representation ('1-ff00:0:96') so that the
        generated .topo file is accepted by SCION tooling that requires the
        colon-hex format.  Already-converted strings (containing ':') are
        returned unchanged.
        """
        if ':' in ia_str:
            return ia_str
        isd, asn_str = ia_str.split('-', 1)
        return f"{isd}-ff00:0:{int(asn_str):x}"

    def _doCompile(self, emulator: Emulator) -> None:
        reg = emulator.getRegistry()
        base_layer: ScionBase = reg.get('seedemu', 'layer', 'Base')
        scion_isd: ScionIsd = reg.get('seedemu', 'layer', 'ScionIsd')

        letter_map = self._build_letter_map(reg)
        all_ifaces = self._collect_interfaces(reg, scion_isd)

        with open('topology.topo', 'w') as f:
            self._write_ases(f, base_layer, scion_isd)
            self._write_links(f, all_ifaces, letter_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_ia(self, asn: int, scion_isd: ScionIsd) -> IA:
        isds = scion_isd.getAsIsds(asn)
        assert len(isds) == 1, f"AS {asn} must belong to exactly one ISD"
        isd, _ = isds[0]
        return IA(isd, asn)

    def _build_letter_map(self, reg) -> Dict[Tuple[int, str], str]:
        """Map (asn, router_name) -> letter suffix ('' when only one SCION router in AS)."""
        routers_by_asn: Dict[int, List[str]] = defaultdict(list)
        for (_, type_, _), node in reg.getAll().items():
            if type_ != 'rnode':
                continue
            if not node.hasExtension('ScionRouter'):
                continue
            if not node.getScionInterfaces():
                continue
            routers_by_asn[node.getAsn()].append(node.getName())

        letter_map: Dict[Tuple[int, str], str] = {}
        for asn, names in routers_by_asn.items():
            names.sort()
            if len(names) == 1:
                letter_map[(asn, names[0])] = ''
            else:
                for i, name in enumerate(names):
                    letter_map[(asn, name)] = chr(ord('A') + i)
        return letter_map

    def _collect_interfaces(self, reg, scion_isd: ScionIsd) -> Dict[str, List]:
        """Build ia_str -> sorted [(ifid, iface_dict, rnode)] from all SCION border routers."""
        result: Dict[str, List] = defaultdict(list)
        for (_, type_, _), node in reg.getAll().items():
            if type_ != 'rnode':
                continue
            if not node.hasExtension('ScionRouter'):
                continue
            ifaces = node.getScionInterfaces()
            if not ifaces:
                continue
            ia_str = str(self._get_ia(node.getAsn(), scion_isd))
            for ifid, iface in ifaces.items():
                result[ia_str].append((ifid, iface, node))
        for ia_str in result:
            result[ia_str].sort(key=lambda x: x[0])
        return result

    def _format_endpoint(self, ia_str: str, rnode, ifid: int,
                         letter_map: Dict[Tuple[int, str], str]) -> str:
        letter = letter_map.get((rnode.getAsn(), rnode.getName()), '')
        if letter:
            return f"{ia_str}-{letter}#{ifid}"
        return f"{ia_str}#{ifid}"

    def _write_ases(self, f, base_layer: ScionBase, scion_isd: ScionIsd) -> None:
        f.write("ASes:\n")
        for asn in sorted(base_layer.getAsns()):
            as_: ScionAutonomousSystem = base_layer.getAutonomousSystem(asn)
            isds = scion_isd.getAsIsds(asn)
            assert len(isds) == 1, f"AS {asn} must belong to exactly one ISD"
            isd, is_core = isds[0]
            ia_str = self._to_scion_ia(str(IA(isd, asn)))

            f.write(f'  "{ia_str}":\n')
            if is_core: # if it a core AS, write the attributes in the .topo file
                attrs = as_.getAsAttributes(isd)
                for attr in ['core', 'voting', 'authoritative', 'issuing']:
                    if attr in attrs:
                        f.write(f'    {attr}: true\n')
            else: # if not, then just write the cert_issuer
                issuer_asn = scion_isd.getCertIssuer((isd, asn))
                if issuer_asn is not None:
                    issuer_ia = self._to_scion_ia(str(IA(isd, issuer_asn)))
                    f.write(f'    cert_issuer: {issuer_ia}\n')

            mtu = as_.getMtu()
            if mtu is not None:
                f.write(f'    mtu: {mtu}\n')

            underlay = as_.getUnderlay()
            if underlay is not None:
                f.write(f'    underlay: {underlay}\n')

    def _write_links(self, f, all_ifaces: Dict[str, List],
                     letter_map: Dict[Tuple[int, str], str]) -> None:
        f.write("links:\n")

        _PARTNER = {'CHILD': 'PARENT', 'CORE': 'CORE', 'PEER': 'PEER'}
        _ATO_B = {'CHILD': 'CHILD', 'CORE': 'CORE', 'PEER': 'PEER'}

        emitted: Set[Tuple[str, int]] = set()

        for local_ia_str in sorted(all_ifaces): # go over all interfaces for all border routers
            for ifid, iface, rnode in all_ifaces[local_ia_str]:
                if (local_ia_str, ifid) in emitted:
                    continue

                link_to = iface['link_to'] # find out what type of link it is (CHILD, CORE, PEER, PARENT)
                if link_to == 'PARENT':
                    emitted.add((local_ia_str, ifid))
                    continue
                if link_to not in _PARTNER:
                    continue

                remote_ia_str = iface['isd_as'] # find remote link's ISD-AS string
                partner_link_to = _PARTNER[link_to] # find out what type of link the remote side has

                candidates = [ # find all remote interfaces that match the local interface's link type and ISD-AS
                    (r_ifid, r_iface, r_rnode)
                    for (r_ifid, r_iface, r_rnode) in all_ifaces.get(remote_ia_str, [])
                    if r_iface['isd_as'] == local_ia_str
                    and r_iface['link_to'] == partner_link_to
                    and (remote_ia_str, r_ifid) not in emitted
                ]
                if not candidates:
                    self._log(f"Warning: no partner found for {local_ia_str}#{ifid} ({link_to})")
                    continue

                r_ifid, r_iface, r_rnode = candidates[0] # take the first one

                emitted.add((local_ia_str, ifid)) # marks as emitted so that we don't emit the same link twice
                emitted.add((remote_ia_str, r_ifid)) # mark the remote interface as emitted as well

                local_out = self._to_scion_ia(local_ia_str)
                remote_out = self._to_scion_ia(remote_ia_str)
                a_ep = self._format_endpoint(local_out, rnode, ifid, letter_map)
                b_ep = self._format_endpoint(remote_out, r_rnode, r_ifid, letter_map)
                link_ato_b = _ATO_B[link_to]
                mtu = iface.get('mtu')

                parts = [f'a: "{a_ep}"', f'b: "{b_ep}"', f'linkAtoB: {link_ato_b}']
                if mtu is not None:
                    parts.append(f'mtu: {mtu}')
                underlay_type = iface.get('underlay_type')
                if underlay_type is not None:
                    parts.append(f'underlay: {underlay_type}')

                f.write(f"  - {{{', '.join(parts)}}}\n")
