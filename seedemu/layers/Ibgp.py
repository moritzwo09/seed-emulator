from __future__ import annotations
from seedemu.core.enums import NetworkType, NodeRole
from .Base import Base
from seedemu.core import ScopedRegistry, Node, Graphable, Emulator, Layer
from seedemu.core.Node import ROUTER_BGP_ROLE_EDGE
from typing import Dict, List, Set, Tuple
from ._bgp_metadata import install_router_bgp_session

IBGP_MODE_FULL_MESH = "full-mesh"
IBGP_MODE_ROUTE_REFLECTOR = "route-reflector"
IBGP_MODE_DISABLED = "disabled"

IBGP_MODE_LEGACY_FULL_MESH = "legacy-full-mesh"
IBGP_MODE_EDGE_FULL_MESH = "edge-full-mesh"

IBGP_MODES = {
    IBGP_MODE_FULL_MESH,
    IBGP_MODE_ROUTE_REFLECTOR,
    IBGP_MODE_DISABLED,
}
IBGP_MODE_ALIASES = {
    IBGP_MODE_LEGACY_FULL_MESH: IBGP_MODE_FULL_MESH,
}


class Ibgp(Layer, Graphable):
    """!
    @brief The Ibgp (iBGP) layer.

    This layer automatically sets up full-mesh iBGP or Route Reflector based
    iBGP sessions between routers within each AS.
    """
    __masked: Set[int]
    __as_modes: Dict[int, str]
    __participants: Dict[int, Set[str]]
    __excluded: Dict[int, Set[str]]

    def __init__(self):
        """!
        @brief Ibgp (iBGP) layer constructor.
        """
        super().__init__()
        self.__masked = set()
        self.__as_modes = {}
        self.__participants = {}
        self.__excluded = {}
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

    def setAsMode(self, asn: int, mode: str) -> Ibgp:
        """!
        @brief Set the iBGP participation mode for an AS.

        The default mode is full-mesh. This layer-level API is kept for
        compatibility; new code should prefer AutonomousSystem.setIbgpMode().

        @param asn AS to configure.
        @param mode full-mesh, route-reflector, disabled, or a supported legacy alias.

        @returns self, for chaining API calls.
        """
        value = str(mode or IBGP_MODE_FULL_MESH).strip().lower()
        if value in IBGP_MODE_ALIASES:
            value = IBGP_MODE_ALIASES[value]
        assert value in IBGP_MODES or value == IBGP_MODE_EDGE_FULL_MESH, (
            "unsupported iBGP mode: {}. valid values: {}".format(
                mode, sorted(IBGP_MODES | {IBGP_MODE_LEGACY_FULL_MESH, IBGP_MODE_EDGE_FULL_MESH})
            )
        )
        self.__as_modes[int(asn)] = value
        if value == IBGP_MODE_DISABLED:
            self.__masked.add(int(asn))
        elif int(asn) in self.__masked:
            self.__masked.remove(int(asn))
        return self

    def getAsMode(self, asn: int) -> str:
        """!
        @brief Get the iBGP participation mode for an AS.

        @param asn AS to inspect.

        @returns configured mode, or full-mesh if unset.
        """
        if int(asn) in self.__masked:
            return IBGP_MODE_DISABLED
        return self.__as_modes.get(int(asn), IBGP_MODE_FULL_MESH)

    def getConfiguredAsMode(self, asn: int):
        """!
        @brief Get the compatibility-layer iBGP mode explicitly set here.

        New code should prefer AutonomousSystem.setIbgpMode(...). This method
        exists so layers that render before Ibgp can still honor legacy
        Ibgp.setAsMode(...) calls.
        """
        if int(asn) in self.__masked:
            return IBGP_MODE_DISABLED
        return self.__as_modes.get(int(asn))

    def addParticipant(self, asn: int, routerName: str) -> Ibgp:
        """!
        @brief Mark a router as participating in an opt-in iBGP mode.

        @param asn AS to configure.
        @param routerName router name.

        @returns self, for chaining API calls.
        """
        self.__participants.setdefault(int(asn), set()).add(str(routerName))
        return self

    def getParticipants(self, asn: int) -> Set[str]:
        """!
        @brief Get routers explicitly marked as iBGP participants for an AS.
        """
        return set(self.__participants.get(int(asn), set()))

    def excludeRouter(self, asn: int, routerName: str) -> Ibgp:
        """!
        @brief Exclude a router from generated iBGP sessions for an AS.

        @param asn AS to configure.
        @param routerName router name.

        @returns self, for chaining API calls.
        """
        self.__excluded.setdefault(int(asn), set()).add(str(routerName))
        return self

    def getExcludedRouters(self, asn: int) -> Set[str]:
        """!
        @brief Get routers excluded from generated iBGP sessions for an AS.
        """
        return set(self.__excluded.get(int(asn), set()))

    def addSession(self, asn: int, localRouterName: str, peerRouterName: str) -> Ibgp:
        """!
        @brief Deprecated placeholder for the removed explicit iBGP mode.

        @param asn AS to configure.
        @param localRouterName first router name.
        @param peerRouterName second router name.

        @returns self, for chaining API calls.
        """
        raise AssertionError(
            "explicit iBGP sessions are no longer a built-in mode; use full-mesh "
            "or route-reflector, or add a custom policy extension"
        )

    def getExplicitSessions(self, asn: int) -> List[Tuple[str, str]]:
        """!
        @brief Get explicit iBGP router pairs for an AS.
        """
        return []

    def __resolve_router_names(
        self,
        asn: int,
        routers_map: Dict[str, Node],
        names: Set[str],
        field: str
    ) -> Set[str]:
        for name in names:
            assert name in routers_map, "iBGP {} router as{}/{} does not exist".format(field, asn, name)
        return set(names)

    def __is_ibgp_disabled(self, router: Node) -> bool:
        return hasattr(router, "isControlPlaneDisabled") and router.isControlPlaneDisabled("ibgp")

    def __get_participant_names(self, asn: int, routers_map: Dict[str, Node]) -> Set[str]:
        names = self.__resolve_router_names(
            asn,
            routers_map,
            self.__participants.get(asn, set()),
            "participant",
        )
        excluded = self.__resolve_router_names(
            asn,
            routers_map,
            self.__excluded.get(asn, set()),
            "excluded",
        )
        disabled = {name for name, router in routers_map.items() if self.__is_ibgp_disabled(router)}
        return names - excluded - disabled

    def __get_edge_participant_names(self, asn: int, routers_map: Dict[str, Node]) -> Set[str]:
        names = self.__get_participant_names(asn, routers_map)
        if names:
            return names

        excluded = self.__resolve_router_names(
            asn,
            routers_map,
            self.__excluded.get(asn, set()),
            "excluded",
        )
        return {
            name
            for name, router in routers_map.items()
            if (
                hasattr(router, "getBgpRole")
                and router.getBgpRole() == ROUTER_BGP_ROLE_EDGE
                and name not in excluded
                and not self.__is_ibgp_disabled(router)
            )
        }

    def __get_legacy_router_list(self, asn: int, routers: List[Node], routers_map: Dict[str, Node]) -> List[Node]:
        excluded = self.__resolve_router_names(
            asn,
            routers_map,
            self.__excluded.get(asn, set()),
            "excluded",
        )
        return [
            router for router in routers
            if router.getName() not in excluded and not self.__is_ibgp_disabled(router)
        ]

    def __get_igp_table(self, emulator: Emulator, asn: int) -> str:
        reg = emulator.getRegistry()
        if reg.has('seedemu', 'layer', 'Mpls'):
            mpls = reg.get('seedemu', 'layer', 'Mpls')
            if hasattr(mpls, "getEnabled") and asn in mpls.getEnabled():
                return "master4"
        return "t_ospf"

    def __install_pair(self, asn: int, local: Node, remote: Node, name: str, next_hop_self: bool = False, igp_table: str = "t_ospf"):
        laddr = local.getLoopbackAddress()
        raddr = remote.getLoopbackAddress()
        install_router_bgp_session(
            local,
            {
                "name": name,
                "kind": "ibgp",
                "local_address": str(laddr),
                "local_asn": asn,
                "peer_address": str(raddr),
                "peer_asn": asn,
                "export_policy": "all",
                "next_hop_self": next_hop_self,
                "igp_table": igp_table,
            },
        )

    def __render_pair_mesh(self, asn: int, routers: List[Node], name_prefix: str, igp_table: str = "t_ospf"):
        for local in sorted(routers, key=lambda router: router.getName()):
            n = 1
            for remote in sorted(routers, key=lambda router: router.getName()):
                if local == remote:
                    continue
                self.__install_pair(asn, local, remote, "{}{}".format(name_prefix, n), igp_table=igp_table)
                n += 1
                self._log('adding peering: {} <-> {} (ibgp, as{})'.format(
                    local.getLoopbackAddress(), remote.getLoopbackAddress(), asn
                ))

    def configure(self, emulator: Emulator):
        reg = emulator.getRegistry()
        base: Base = reg.get('seedemu', 'layer', 'Base')
        for asn in base.getAsns():
            asobj = base.getAutonomousSystem(asn)
            if int(asn) in self.__as_modes:
                asobj.setIbgpMode(self.__as_modes[int(asn)])
            if int(asn) in self.__masked:
                asobj.setIbgpMode(IBGP_MODE_DISABLED)

            self.__apply_layer_participants_to_as(asn, asobj)
            asobj.completeIbgpSetup()
            mode = asobj.getIbgpMode()
            if mode == IBGP_MODE_DISABLED: continue

            self._log('setting up IBGP peering for as{}...'.format(asn))
            routers: List[Node] = ScopedRegistry(str(asn), reg).getByType('rnode')
            routers_map: Dict[str, Node] = {router.getName(): router for router in routers}
            participant_names = asobj.getIbgpParticipants()
            excluded = self.__resolve_router_names(
                asn,
                routers_map,
                self.__excluded.get(asn, set()),
                "excluded",
            )
            disabled = {name for name, router in routers_map.items() if self.__is_ibgp_disabled(router)}
            active_names = participant_names - excluded - disabled
            active_routers_map = {
                name: router for name, router in routers_map.items()
                if name in active_names
            }
            igp_table = self.__get_igp_table(emulator, asn)

            if mode == IBGP_MODE_ROUTE_REFLECTOR:
                clusters = asobj._aggregateBgpClusters()
                self._render_rr_mode(asn, clusters, active_routers_map, igp_table)
                continue

            self._render_full_mesh_mode(
                asn,
                [active_routers_map[name] for name in sorted(active_routers_map.keys())],
                igp_table,
            )

    def __apply_layer_participants_to_as(self, asn: int, asobj) -> None:
        """Apply compatibility-layer participant hints to AS router metadata."""
        for name in self.__participants.get(int(asn), set()):
            if name in asobj.getRouters():
                asobj.getRouter(name).setBgpRole(ROUTER_BGP_ROLE_EDGE)

    def _render_rr_mode(self, asn: int, clusters: Dict[str, Tuple[Set[str], Set[str]]], routers_map: Dict[str, Node], igp_table: str = "t_ospf"):
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
                rr_address = rr_node.getLoopbackAddress()

                for client_name in sorted(client_names):
                    if client_name not in routers_map:
                        continue

                    client_node = routers_map[client_name]
                    client_address = client_node.getLoopbackAddress()
                    install_router_bgp_session(
                        rr_node,
                        {
                            "name": "Ibgp_rr_client_{}".format(client_name),
                            "kind": "ibgp",
                            "local_address": str(rr_address),
                            "local_asn": asn,
                            "peer_address": str(client_address),
                            "peer_asn": asn,
                            "export_policy": "all",
                            "next_hop_self": False,
                            "igp_table": igp_table,
                            "passive": True,
                            "route_reflector_client": True,
                            "route_reflector_cluster_id": cluster_id,
                        },
                    )
                    install_router_bgp_session(
                        client_node,
                        {
                            "name": "Ibgp_rr_{}".format(rr_name),
                            "kind": "ibgp",
                            "local_address": str(client_address),
                            "local_asn": asn,
                            "peer_address": str(rr_address),
                            "peer_asn": asn,
                            "export_policy": "all",
                            "next_hop_self": True,
                            "igp_table": igp_table,
                        },
                    )

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

                install_router_bgp_session(
                    node_a,
                    {
                        "name": "Ibgp_rr_mesh_{}".format(node_b.getName()),
                        "kind": "ibgp",
                        "local_address": str(node_a.getLoopbackAddress()),
                        "local_asn": asn,
                        "peer_address": str(node_b.getLoopbackAddress()),
                        "peer_asn": asn,
                        "export_policy": "all",
                        "next_hop_self": False,
                        "igp_table": igp_table,
                    },
                )
                install_router_bgp_session(
                    node_b,
                    {
                        "name": "Ibgp_rr_mesh_{}".format(node_a.getName()),
                        "kind": "ibgp",
                        "local_address": str(node_b.getLoopbackAddress()),
                        "local_asn": asn,
                        "peer_address": str(node_a.getLoopbackAddress()),
                        "peer_asn": asn,
                        "export_policy": "all",
                        "next_hop_self": False,
                        "igp_table": igp_table,
                    },
                )

                self._log(
                    'adding RR mesh peering: {} <-> {} (as{})'.format(
                        node_a.getName(), node_b.getName(), asn
                    )
                )

    def _render_full_mesh_mode(self, asn: int, routers: List[Node], igp_table: str = "t_ospf"):
        """!
        @brief Render the legacy full-mesh iBGP sessions for one AS.

        @param asn AS number being rendered.
        @param routers routers participating in the legacy iBGP mesh.
        """
        self._log('setting up IBGP (Full Mesh) for as{}...'.format(asn))
        allowed_names = {router.getName() for router in routers}

        for local in routers:
            self._log('setting up IBGP peering on as{}/{}...'.format(asn, local.getName()))

            remotes = []
            self.__dfs(local, remotes)

            n = 1
            for remote in remotes:
                if local == remote:
                    continue
                if remote.getName() not in allowed_names:
                    continue

                laddr = local.getLoopbackAddress()
                raddr = remote.getLoopbackAddress()
                install_router_bgp_session(
                    local,
                    {
                        "name": "ibgp{}".format(n),
                        "kind": "ibgp",
                        "local_address": str(laddr),
                        "local_asn": asn,
                        "peer_address": str(raddr),
                        "peer_asn": asn,
                        "export_policy": "all",
                        "next_hop_self": False,
                        "igp_table": igp_table,
                    },
                )

                n += 1

                self._log('adding peering: {} <-> {} (ibgp, as{})'.format(laddr, raddr, asn))

    def render(self, emulator: Emulator):
        pass

    def _doCreateGraphs(self, emulator: Emulator):
        base: Base = emulator.getRegistry().get('seedemu', 'layer', 'Base')
        for asn in base.getAsns():
            asobj = base.getAutonomousSystem(asn)
            if int(asn) in self.__as_modes:
                asobj.setIbgpMode(self.__as_modes[int(asn)])
            if int(asn) in self.__masked:
                asobj.setIbgpMode(IBGP_MODE_DISABLED)
            self.__apply_layer_participants_to_as(asn, asobj)
            asobj.completeIbgpSetup()
            mode = asobj.getIbgpMode()
            if mode == IBGP_MODE_DISABLED: continue
            asobj.createGraphs(emulator)
            l2graph = asobj.getGraph('AS{}: Layer 2 Connections'.format(asn))
            ibgpgraph = self._addGraph('AS{}: iBGP sessions'.format(asn), False)
            ibgpgraph.copy(l2graph)
            for edge in ibgpgraph.edges:
                edge.style = 'dotted'

            scope = ScopedRegistry(str(asn), emulator.getRegistry())
            rtrs = scope.getByType('rnode').copy()
            routers_map: Dict[str, Node] = {router.getName(): router for router in rtrs}
            excluded = self.__resolve_router_names(
                asn,
                routers_map,
                self.__excluded.get(asn, set()),
                "excluded",
            )
            disabled = {name for name, router in routers_map.items() if self.__is_ibgp_disabled(router)}
            active_names = asobj.getIbgpParticipants() - excluded - disabled

            if mode == IBGP_MODE_ROUTE_REFLECTOR:
                clusters = asobj._aggregateBgpClusters()
                all_rrs: Set[str] = set()
                for _cluster_id, (rr_names, client_names) in clusters.items():
                    all_rrs.update(rr_names)
                    for rr_name in rr_names:
                        for client_name in client_names:
                            if rr_name in active_names and client_name in active_names:
                                ibgpgraph.addEdge(
                                    'Router: {}'.format(rr_name),
                                    'Router: {}'.format(client_name),
                                    style = 'solid'
                                )
                rtrs = [
                    routers_map[name]
                    for name in sorted(all_rrs)
                    if name in routers_map and name in active_names
                ]
            else:
                rtrs = [routers_map[name] for name in sorted(active_names) if name in routers_map]

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
