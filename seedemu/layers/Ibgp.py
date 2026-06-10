from __future__ import annotations
from seedemu.core.enums import NetworkType, NodeRole
from .Base import Base
from seedemu.core import ScopedRegistry, Node, Graphable, Emulator, Layer
from typing import Dict, List, Set, Tuple

IbgpFileTemplates: Dict[str, str] = {}

IbgpFileTemplates['ibgp_peer'] = '''
    # debug {{states,events}};
    # hold time 36000;
    # keepalive time 60;
    ipv4 {{
        table t_bgp;
        import all;
        export all;
        igp table t_ospf;
    }};
    local {localAddress} as {asn};
    neighbor {peerAddress} as {asn};
'''

IbgpFileTemplates['ibgp_client'] = '''
    # debug {{states,events}};
    # hold time 36000;
    # keepalive time 60;
    ipv4 {{
        table t_bgp;
        import all;
        export all;
        igp table t_ospf;
        next hop self;
    }};
    local {localAddress} as {asn};
    neighbor {peerAddress} as {asn};
'''

IbgpFileTemplates['ibgp_rr_server'] = '''
    # debug {{states,events}};
    # hold time 36000;
    # keepalive time 60;
    passive yes;
    ipv4 {{
        table t_bgp;
        import all;
        export all;
        igp table t_ospf;
    }};
    local {localAddress} as {asn};
    neighbor {peerAddress} as {asn};
    rr client;
    rr cluster id {clusterId};
'''

class Ibgp(Layer, Graphable):
    """!
    @brief The Ibgp (iBGP) layer.

    This layer automatically sets up full-mesh iBGP or Route Reflector based
    iBGP sessions between routers within each AS.
    """
    __masked: Set[int]

    def __init__(self):
        """!
        @brief Ibgp (iBGP) layer constructor.
        """
        super().__init__()
        self.__masked = set()
        self.addDependency('Ospf', False, False)

    def __dfs(self, start: Node, visited: List[Node], netname: str = 'self'):
        """!
        @brief do a DFS and find all local routers to setup IBGP.

        @param start node to start from.
        @param visited list to store nodes.
        @param netname name of the net - for log only.
        """
        if start in visited:
            return
        
        self._log('found node: as{}/{} via {}'.format(start.getAsn(), start.getName(), netname))
        visited.append(start)

        for iface in start.getInterfaces():
            net = iface.getNet()

            if net.getType() != NetworkType.Local:
                continue

            neighs: List[Node] = net.getAssociations()

            for neigh in neighs:
                role = neigh.getRole()
                if role != NodeRole.Router and role != NodeRole.BorderRouter and role != NodeRole.OpenVpnRouter: 
                    continue
                
                self.__dfs(neigh, visited, net.getName())


    def getName(self) -> str:
        return 'Ibgp'

    def maskAsn(self, asn: int) -> Ibgp:
        """!
        @brief Mask an AS.

        By default, Ibgp layer will add iBGP peering for all ASes. Use this
        method to mask an AS and disable iBGP.

        @param asn AS to mask.

        @returns self, for chaining API calls.
        """
        self.__masked.add(asn)

        return self
    
    def getMaskedAsns(self) -> Set[int]:
        """!
        @brief Get set of masked ASNs.
        
        @return set of ASNs.
        """
        return self.__masked

    def render(self, emulator: Emulator):
        reg = emulator.getRegistry()
        base: Base = reg.get('seedemu', 'layer', 'Base')
        for asn in base.getAsns():
            if asn in self.__masked: continue

            self._log('setting up IBGP peering for as{}...'.format(asn))
            routers: List[Node] = ScopedRegistry(str(asn), reg).getByType('rnode')
            routers_map: Dict[str, Node] = {router.getName(): router for router in routers}

            clusters = base.getAutonomousSystem(asn)._aggregateBgpClusters()
            has_rr = any(len(rrs) > 0 for rrs, _ in clusters.values())

            if has_rr:
                self._render_rr_mode(asn, clusters, routers_map)
            else:
                self._render_full_mesh_mode(asn, routers)

    def _render_rr_mode(self, asn: int, clusters: Dict[str, Tuple[Set[str], Set[str]]], routers_map: Dict[str, Node]):
        """!
        @brief Render Route Reflector based iBGP sessions for one AS.

        @param asn AS number being rendered.
        @param clusters mapping from cluster ID to RR names and client names.
        @param routers_map mapping from router name to router node.
        """
        self._log('setting up IBGP (Route Reflector) for as{}...'.format(asn))

        all_rr_names: Set[str] = set()

        for cluster_id, (rr_names, client_names) in clusters.items():
            all_rr_names.update(rr_names)

            for rr_name in sorted(rr_names):
                if rr_name not in routers_map:
                    continue

                rr_node = routers_map[rr_name]
                rr_node.addTable('t_bgp')
                rr_node.addTablePipe('t_bgp')
                rr_node.addTablePipe('t_direct', 't_bgp')
                rr_address = rr_node.getLoopbackAddress()

                for client_name in sorted(client_names):
                    if client_name not in routers_map:
                        continue

                    client_node = routers_map[client_name]
                    client_node.addTable('t_bgp')
                    client_node.addTablePipe('t_bgp')
                    client_node.addTablePipe('t_direct', 't_bgp')
                    client_address = client_node.getLoopbackAddress()

                    rr_node.addProtocol('bgp', 'Ibgp_rr_client_{}'.format(client_name), IbgpFileTemplates['ibgp_rr_server'].format(
                        localAddress = rr_address,
                        peerAddress = client_address,
                        asn = asn,
                        clusterId = cluster_id
                    ))
                    client_node.addProtocol('bgp', 'Ibgp_rr_{}'.format(rr_name), IbgpFileTemplates['ibgp_client'].format(
                        localAddress = client_address,
                        peerAddress = rr_address,
                        asn = asn
                    ))

                    self._log(
                        'adding RR peering: {}(RR) <-> {}(client) cluster {} (as{})'.format(
                            rr_name, client_name, cluster_id, asn
                        )
                    )

        sorted_rrs = sorted(
            [routers_map[name] for name in all_rr_names if name in routers_map],
            key = lambda router: router.getName()
        )

        for i in range(len(sorted_rrs)):
            for j in range(i + 1, len(sorted_rrs)):
                node_a = sorted_rrs[i]
                node_b = sorted_rrs[j]

                node_a.addTable('t_bgp')
                node_a.addTablePipe('t_bgp')
                node_a.addTablePipe('t_direct', 't_bgp')

                node_b.addTable('t_bgp')
                node_b.addTablePipe('t_bgp')
                node_b.addTablePipe('t_direct', 't_bgp')

                node_a.addProtocol('bgp', 'Ibgp_rr_mesh_{}'.format(node_b.getName()), IbgpFileTemplates['ibgp_peer'].format(
                    localAddress = node_a.getLoopbackAddress(),
                    peerAddress = node_b.getLoopbackAddress(),
                    asn = asn
                ))
                node_b.addProtocol('bgp', 'Ibgp_rr_mesh_{}'.format(node_a.getName()), IbgpFileTemplates['ibgp_peer'].format(
                    localAddress = node_b.getLoopbackAddress(),
                    peerAddress = node_a.getLoopbackAddress(),
                    asn = asn
                ))

                self._log(
                    'adding RR mesh peering: {} <-> {} (as{})'.format(
                        node_a.getName(), node_b.getName(), asn
                    )
                )

    def _render_full_mesh_mode(self, asn: int, routers: List[Node]):
        """!
        @brief Render the legacy full-mesh iBGP sessions for one AS.

        @param asn AS number being rendered.
        @param routers routers participating in the legacy iBGP mesh.
        """
        self._log('setting up IBGP (Full Mesh) for as{}...'.format(asn))

        for local in routers:
            self._log('setting up IBGP peering on as{}/{}...'.format(asn, local.getName()))

            remotes = []
            self.__dfs(local, remotes)

            n = 1
            for remote in remotes:
                if local == remote:
                    continue

                laddr = local.getLoopbackAddress()
                raddr = remote.getLoopbackAddress()
                local.addTable('t_bgp')
                local.addTablePipe('t_bgp')
                local.addTablePipe('t_direct', 't_bgp')
                local.addProtocol('bgp', 'ibgp{}'.format(n), IbgpFileTemplates['ibgp_peer'].format(
                    localAddress = laddr,
                    peerAddress = raddr,
                    asn = asn
                ))

                n += 1

                self._log('adding peering: {} <-> {} (ibgp, as{})'.format(laddr, raddr, asn))

    def _doCreateGraphs(self, emulator: Emulator):
        base: Base = emulator.getRegistry().get('seedemu', 'layer', 'Base')
        for asn in base.getAsns():
            if asn in self.__masked: continue
            asobj = base.getAutonomousSystem(asn)
            asobj.createGraphs(emulator)
            l2graph = asobj.getGraph('AS{}: Layer 2 Connections'.format(asn))
            ibgpgraph = self._addGraph('AS{}: iBGP sessions'.format(asn), False)
            ibgpgraph.copy(l2graph)
            for edge in ibgpgraph.edges:
                edge.style = 'dotted'

            rtrs = ScopedRegistry(str(asn), emulator.getRegistry()).getByType('rnode').copy()
            
            while len(rtrs) > 0:
                a = rtrs.pop()
                for b in rtrs:
                    ibgpgraph.addEdge('Router: {}'.format(a.getName()), 'Router: {}'.format(b.getName()), style = 'solid')
            

    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += 'IbgpLayer:\n'

        indent += 4
        out += ' ' * indent
        out += 'Masked ASes:\n'

        indent += 4
        for asn in self.__masked:
            out += ' ' * indent
            out += '{}\n'.format(asn)

        return out
