from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from seedemu.layers import Base


try:
    import networkx as nx
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    nx = None


GraphModel = Union[str, Callable[..., Any]]


class TopologyGenerationError(Exception):
    """Raised when a transit AS topology cannot be generated or validated."""


def _require_networkx():
    if nx is None:
        raise TopologyGenerationError("Transit AS topology generation requires networkx")
    return nx


def _call_graph_model(model: GraphModel, n: int, params: Dict[str, Any], seed: Optional[int]):
    nx_mod = _require_networkx()
    params = dict(params or {})

    if callable(model):
        return model(n=n, seed=seed, **params)

    model_name = str(model).strip().lower()
    registry: Dict[str, Callable[[], Any]] = {
        "cycle": lambda: nx_mod.cycle_graph(n),
        "path": lambda: nx_mod.path_graph(n),
        "complete": lambda: nx_mod.complete_graph(n),
        "random": lambda: nx_mod.erdos_renyi_graph(n=n, seed=seed, **params),
        "erdos_renyi": lambda: nx_mod.erdos_renyi_graph(n=n, seed=seed, **params),
        "gnp_random": lambda: nx_mod.gnp_random_graph(n=n, seed=seed, **params),
        "regular": lambda: nx_mod.random_regular_graph(n=n, seed=seed, **params),
        "random_regular": lambda: nx_mod.random_regular_graph(n=n, seed=seed, **params),
        "small_world": lambda: nx_mod.connected_watts_strogatz_graph(n=n, seed=seed, **params),
        "watts_strogatz": lambda: nx_mod.watts_strogatz_graph(n=n, seed=seed, **params),
        "connected_watts_strogatz": lambda: nx_mod.connected_watts_strogatz_graph(n=n, seed=seed, **params),
        "scale_free": lambda: nx_mod.barabasi_albert_graph(n=n, seed=seed, **params),
        "barabasi_albert": lambda: nx_mod.barabasi_albert_graph(n=n, seed=seed, **params),
        "powerlaw_cluster": lambda: nx_mod.powerlaw_cluster_graph(n=n, seed=seed, **params),
    }

    if model_name not in registry:
        raise TopologyGenerationError("unsupported NetworkX graph model: {}".format(model))

    try:
        return registry[model_name]()
    except TypeError as exc:
        raise TopologyGenerationError("invalid parameters for graph model {}: {}".format(model, exc)) from exc


class TransitAsTopology:
    """A generated transit AS topology that can be validated and applied to Base."""

    def __init__(
        self,
        asn: int,
        graph: Any,
        edge_attachments: Dict[str, List[int]],
        edge_to_internal: Dict[str, str],
        seed: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        _require_networkx()
        self.asn = int(asn)
        self._graph = graph.copy()
        self._edge_attachments = {str(router): [int(ix) for ix in ixes] for router, ixes in edge_attachments.items()}
        self._edge_to_internal = {str(edge): str(internal) for edge, internal in edge_to_internal.items()}
        self.seed = seed
        self.metadata = dict(metadata or {})

    @classmethod
    def from_networkx(
        cls,
        asn: int,
        internal_graph: Any,
        ixes: Optional[List[int]] = None,
        edge_attachments: Optional[Dict[str, List[int]]] = None,
        edge_attach_policy: str = "spread",
        edge_to_internal: Optional[Dict[str, str]] = None,
        edge_router_prefix: str = "r",
        seed: Optional[int] = None,
    ) -> "TransitAsTopology":
        generator = TransitAsTopologyGenerator(
            asn=asn,
            ixes=ixes,
            edge_attachments=edge_attachments,
            internal_graph=internal_graph,
            edge_attach_policy=edge_attach_policy,
            edge_to_internal=edge_to_internal,
            edge_router_prefix=edge_router_prefix,
            seed=seed,
        )
        return generator.generate()

    def graph(self):
        return self._graph.copy()

    def to_networkx(self):
        return self.graph()

    def internal_graph(self):
        nx_mod = _require_networkx()
        return self._graph.subgraph(self.internal_routers()).copy()

    def routers(self) -> List[str]:
        return sorted(str(node) for node in self._graph.nodes)

    def edge_routers(self) -> List[str]:
        return sorted(str(node) for node, data in self._graph.nodes(data=True) if data.get("role") == "edge")

    def internal_routers(self) -> List[str]:
        return sorted(str(node) for node, data in self._graph.nodes(data=True) if data.get("role") == "internal")

    def links(self) -> List[Tuple[str, str]]:
        return sorted((str(a), str(b)) for a, b in self._graph.edges)

    def ix_attachments(self) -> Dict[str, List[int]]:
        return {router: list(ixes) for router, ixes in self._edge_attachments.items()}

    def edge_to_internal(self) -> Dict[str, str]:
        return dict(self._edge_to_internal)

    def validate(self) -> None:
        nx_mod = _require_networkx()

        if len(self._graph.nodes) == 0:
            raise TopologyGenerationError("AS{} topology has no routers".format(self.asn))

        if not nx_mod.is_connected(self._graph):
            raise TopologyGenerationError("AS{} topology is not connected".format(self.asn))

        if list(nx_mod.selfloop_edges(self._graph)):
            raise TopologyGenerationError("AS{} topology contains self loops".format(self.asn))

        router_names = self.routers()
        if len(router_names) != len(set(router_names)):
            raise TopologyGenerationError("AS{} topology contains duplicate router names".format(self.asn))

        internal = set(self.internal_routers())
        edges = set(self.edge_routers())
        if not internal:
            raise TopologyGenerationError("AS{} topology has no internal routers".format(self.asn))
        if not edges:
            raise TopologyGenerationError("AS{} topology has no edge routers".format(self.asn))

        for edge_router, ixes in self._edge_attachments.items():
            if edge_router not in edges:
                raise TopologyGenerationError("edge attachment references unknown edge router {}".format(edge_router))
            if not ixes:
                raise TopologyGenerationError("edge router {} has no IX attachment".format(edge_router))

        for edge_router in edges:
            if edge_router not in self._edge_to_internal:
                raise TopologyGenerationError("edge router {} is not attached to an internal router".format(edge_router))
            internal_router = self._edge_to_internal[edge_router]
            if internal_router not in internal:
                raise TopologyGenerationError(
                    "edge router {} attaches to unknown internal router {}".format(edge_router, internal_router)
                )
            if not self._graph.has_edge(edge_router, internal_router):
                raise TopologyGenerationError(
                    "edge router {} is missing graph link to {}".format(edge_router, internal_router)
                )

    def apply_to(self, base: Base):
        self.validate()
        transit_as = base.createAutonomousSystem(self.asn)

        routers = {}
        for router_name in self.routers():
            routers[router_name] = transit_as.createRouter(router_name)

        for edge_router, ixes in self._edge_attachments.items():
            for ix in ixes:
                routers[edge_router].joinNetwork("ix{}".format(ix))

        for a, b in self.links():
            net_name = self._network_name(a, b)
            transit_as.createNetwork(net_name)
            routers[a].joinNetwork(net_name)
            routers[b].joinNetwork(net_name)

        return transit_as

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asn": self.asn,
            "seed": self.seed,
            "metadata": dict(self.metadata),
            "edge_routers": {router: {"ixes": ixes} for router, ixes in self._edge_attachments.items()},
            "internal_routers": self.internal_routers(),
            "edge_to_internal": self.edge_to_internal(),
            "links": [list(link) for link in self.links()],
        }

    def to_yaml(self, path: Union[str, Path]) -> None:
        import yaml

        with open(path, "w", encoding="utf-8") as file:
            yaml.safe_dump(self.to_dict(), file, sort_keys=False)

    def to_dot(self, path: Union[str, Path]) -> None:
        nx_mod = _require_networkx()
        nx_mod.drawing.nx_pydot.write_dot(self._graph, path)

    def summary(self) -> str:
        return "AS{}: {} edge routers, {} internal routers, {} links".format(
            self.asn,
            len(self.edge_routers()),
            len(self.internal_routers()),
            len(self.links()),
        )

    def _network_name(self, a: str, b: str) -> str:
        left, right = sorted([a, b])
        name = "n_{}_{}".format(self._short_router_name(left), self._short_router_name(right))
        assert len(name) <= 15, "generated network name is too long for a Linux interface: {}".format(name)
        return name

    def _short_router_name(self, name: str) -> str:
        if name.startswith("core"):
            return "c{}".format(name[4:])
        return name.replace("-", "_")


class TransitAsTopologyGenerator:
    """Generate transit AS topologies using NetworkX internal graph models."""

    def __init__(
        self,
        asn: int,
        ixes: Optional[List[int]] = None,
        edge_attachments: Optional[Dict[str, List[int]]] = None,
        internal_router_count: int = 4,
        graph_model: GraphModel = "small_world",
        graph_params: Optional[Dict[str, Any]] = None,
        internal_graph: Any = None,
        seed: Optional[int] = None,
        edge_attach_policy: str = "spread",
        edge_to_internal: Optional[Dict[str, str]] = None,
        edge_router_prefix: str = "r",
        internal_router_prefix: str = "core",
        require_connected: bool = True,
        max_attempts: int = 100,
    ):
        self.asn = int(asn)
        self.ixes = [int(ix) for ix in ixes] if ixes is not None else None
        self.edge_attachments = self._normalize_edge_attachments(edge_attachments) if edge_attachments else None
        self.internal_router_count = int(internal_router_count)
        self.graph_model = graph_model
        self.graph_params = dict(graph_params or self._default_graph_params(graph_model))
        self.internal_graph = internal_graph
        self.seed = seed
        self.edge_attach_policy = str(edge_attach_policy)
        self.edge_to_internal = {str(edge): str(internal) for edge, internal in edge_to_internal.items()} if edge_to_internal else None
        self.edge_router_prefix = str(edge_router_prefix)
        self.internal_router_prefix = str(internal_router_prefix)
        self.require_connected = bool(require_connected)
        self.max_attempts = int(max_attempts)

    @classmethod
    def from_graph(
        cls,
        asn: int,
        graph: Any,
        ixes: Optional[List[int]] = None,
        edge_attachments: Optional[Dict[str, List[int]]] = None,
        **kwargs,
    ) -> "TransitAsTopologyGenerator":
        return cls(asn=asn, ixes=ixes, edge_attachments=edge_attachments, internal_graph=graph, **kwargs)

    def generate(self) -> TransitAsTopology:
        nx_mod = _require_networkx()
        self._validate_inputs()

        edge_attachments = self._build_edge_attachments()
        internal_graph = self._generate_internal_graph()
        internal_graph = self._relabel_internal_graph(internal_graph)
        internal_routers = sorted(str(node) for node in internal_graph.nodes)
        edge_to_internal = self.edge_to_internal or self._select_edge_attachments(edge_attachments, internal_graph)

        graph = nx_mod.Graph()
        for router in internal_routers:
            graph.add_node(router, role="internal")
        for a, b in internal_graph.edges:
            graph.add_edge(str(a), str(b))

        for edge_router, ixes in edge_attachments.items():
            graph.add_node(edge_router, role="edge", ixes=list(ixes))
            internal_router = edge_to_internal[edge_router]
            graph.add_edge(edge_router, internal_router)

        topology = TransitAsTopology(
            asn=self.asn,
            graph=graph,
            edge_attachments=edge_attachments,
            edge_to_internal=edge_to_internal,
            seed=self.seed,
            metadata={
                "graph_model": self.graph_model if isinstance(self.graph_model, str) else getattr(self.graph_model, "__name__", "callable"),
                "graph_params": dict(self.graph_params),
                "edge_attach_policy": self.edge_attach_policy,
            },
        )
        topology.validate()
        return topology

    def _validate_inputs(self) -> None:
        if self.ixes is not None and self.edge_attachments is not None:
            raise TopologyGenerationError("use either ixes or edge_attachments, not both")
        if self.ixes is None and self.edge_attachments is None:
            raise TopologyGenerationError("either ixes or edge_attachments is required")
        if self.internal_graph is None and self.internal_router_count <= 0:
            raise TopologyGenerationError("internal_router_count must be positive")
        if self.max_attempts <= 0:
            raise TopologyGenerationError("max_attempts must be positive")

    def _build_edge_attachments(self) -> Dict[str, List[int]]:
        if self.edge_attachments is not None:
            return {router: list(ixes) for router, ixes in self.edge_attachments.items()}
        return {"{}{}".format(self.edge_router_prefix, ix): [ix] for ix in self.ixes or []}

    def _generate_internal_graph(self):
        nx_mod = _require_networkx()
        if self.internal_graph is not None:
            graph = nx_mod.Graph(self.internal_graph)
            if self.require_connected and not nx_mod.is_connected(graph):
                raise TopologyGenerationError("provided internal graph is not connected")
            return graph

        last_error = None
        for attempt in range(self.max_attempts):
            attempt_seed = None if self.seed is None else self.seed + attempt
            try:
                graph = nx_mod.Graph(
                    _call_graph_model(self.graph_model, self.internal_router_count, self.graph_params, attempt_seed)
                )
            except TopologyGenerationError as exc:
                last_error = exc
                break

            if not self.require_connected or nx_mod.is_connected(graph):
                return graph

        if last_error is not None:
            raise last_error
        raise TopologyGenerationError(
            "could not generate a connected internal graph after {} attempts".format(self.max_attempts)
        )

    def _relabel_internal_graph(self, graph):
        nx_mod = _require_networkx()
        mapping = {}
        for index, node in enumerate(sorted(graph.nodes, key=str)):
            name = str(node)
            if not name.startswith(self.internal_router_prefix):
                name = "{}{}".format(self.internal_router_prefix, index)
            mapping[node] = name
        return nx_mod.relabel_nodes(graph, mapping, copy=True)

    def _select_edge_attachments(self, edge_attachments: Dict[str, List[int]], internal_graph) -> Dict[str, str]:
        internal_routers = sorted(str(node) for node in internal_graph.nodes)
        if not internal_routers:
            raise TopologyGenerationError("cannot attach edge routers without internal routers")

        policy = self.edge_attach_policy.lower()
        if policy == "manual":
            raise TopologyGenerationError("edge_attach_policy=manual requires edge_to_internal")

        edge_routers = sorted(edge_attachments)
        if policy in {"spread", "round_robin"}:
            return {edge: internal_routers[index % len(internal_routers)] for index, edge in enumerate(edge_routers)}

        if policy == "random":
            rng = random.Random(self.seed)
            return {edge: rng.choice(internal_routers) for edge in edge_routers}

        if policy == "degree":
            ranked = sorted(internal_graph.degree, key=lambda item: (-item[1], str(item[0])))
            ranked_nodes = [str(node) for node, _degree in ranked]
            return {edge: ranked_nodes[index % len(ranked_nodes)] for index, edge in enumerate(edge_routers)}

        raise TopologyGenerationError("unsupported edge attachment policy: {}".format(self.edge_attach_policy))

    def _normalize_edge_attachments(self, edge_attachments: Dict[str, Iterable[int]]) -> Dict[str, List[int]]:
        return {str(router): [int(ix) for ix in ixes] for router, ixes in edge_attachments.items()}

    def _default_graph_params(self, graph_model: GraphModel) -> Dict[str, Any]:
        if not isinstance(graph_model, str):
            return {}

        model = graph_model.strip().lower()
        if model in {"random", "erdos_renyi", "gnp_random"}:
            return {"p": 0.4}
        if model in {"regular", "random_regular"}:
            return {"d": 2}
        if model in {"small_world", "connected_watts_strogatz", "watts_strogatz"}:
            return {"k": 2, "p": 0.25}
        if model in {"scale_free", "barabasi_albert"}:
            return {"m": 1}
        if model == "powerlaw_cluster":
            return {"m": 1, "p": 0.25}
        return {}
