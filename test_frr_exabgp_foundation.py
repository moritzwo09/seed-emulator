from __future__ import annotations

import importlib

import pytest

from seedemu.core import Binding, Emulator, Filter
from seedemu.layers import Base, Ebgp, Ibgp, Ospf, PeerRelationship, Routing
from seedemu.layers._bgp_metadata import set_bgp_backend
from seedemu.services import ExaBgpService


def _file_content(node, path: str) -> str:
    for file in node.getFiles():
        file_path, content = file.get()
        if file_path == path:
            return content
    return ""


def test_router_backend_default_and_legacy_rejection():
    as2 = Base().createAutonomousSystem(2)
    assert as2.createRouter("default").getRoutingBackend() == "bird"
    assert as2.createRouter("frr", routingBackend="frr").getRoutingBackend() == "frr"

    with pytest.raises(AssertionError, match="unsupported routing backend"):
        as2.createRouter("exabgp", routingBackend="exabgp")
    with pytest.raises(AssertionError, match="unsupported routing backend"):
        as2.createRouter("external", routingBackend="external")


def test_frr_bgp_layer_shim_is_not_exported():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("seedemu.layers.FrrBgp")
    assert not hasattr(importlib.import_module("seedemu.layers"), "FrrBgp")


def test_route_server_peering_renders_from_intent_in_routing_layer():
    emu = Emulator()
    base = Base()
    routing = Routing()
    ebgp = Ebgp()

    base.createInternetExchange(100)
    as150 = base.createAutonomousSystem(150)
    as150.createNetwork("net0")
    as150.createRouter("router0").joinNetwork("net0").joinNetwork("ix100")

    ebgp.addRsPeer(100, 150)

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(ebgp)
    emu.render()

    route_server = emu.getRegistry().get("ix", "rs", "ix100")
    router = emu.getRegistry().get("150", "rnode", "router0")

    rs_conf = _file_content(route_server, "/etc/bird/bird.conf")
    router_conf = _file_content(router, "/etc/bird/bird.conf")

    assert "protocol bgp p_as150" in rs_conf
    assert "rs client" in rs_conf
    assert "neighbor 10.100.0.150 as 150" in rs_conf
    assert "protocol bgp p_rs100" in router_conf
    assert "neighbor 10.100.0.100 as 100" in router_conf
    assert "bgp_large_community.add(PEER_COMM)" in router_conf


def test_frr_route_server_backend_is_explicitly_rejected():
    emu = Emulator()
    base = Base()
    routing = Routing()
    ebgp = Ebgp()

    ix = base.createInternetExchange(100)
    set_bgp_backend(ix.getRouteServerNode(), "frr")
    as150 = base.createAutonomousSystem(150)
    as150.createNetwork("net0")
    as150.createRouter("router0").joinNetwork("net0").joinNetwork("ix100")

    ebgp.addRsPeer(100, 150)

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(ebgp)

    with pytest.raises(NotImplementedError, match="FRR route-server nodes are not supported yet"):
        emu.render()


def test_frr_backend_renders_frr_config_for_selected_router():
    emu = Emulator()
    base = Base()
    routing = Routing()
    ospf = Ospf()
    ibgp = Ibgp()
    ebgp = Ebgp()

    base.createInternetExchange(100)
    base.createInternetExchange(101)

    as2 = base.createAutonomousSystem(2)
    as2.createNetwork("net0")
    as2.createRouter("r1").joinNetwork("net0").joinNetwork("ix100")
    as2.createRouter("r2", routingBackend="frr").joinNetwork("net0").joinNetwork("ix101")

    as151 = base.createAutonomousSystem(151)
    as151.createNetwork("net0")
    as151.createRouter("router0").joinNetwork("net0").joinNetwork("ix100")

    as152 = base.createAutonomousSystem(152)
    as152.createNetwork("net0")
    as152.createRouter("router0").joinNetwork("net0").joinNetwork("ix101")

    ebgp.addPrivatePeering(100, 2, 151, abRelationship=PeerRelationship.Provider)
    ebgp.addPrivatePeering(101, 2, 152, abRelationship=PeerRelationship.Provider)

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(ospf)
    emu.addLayer(ibgp)
    emu.addLayer(ebgp)
    emu.render()

    r1 = emu.getRegistry().get("2", "rnode", "r1")
    r2 = emu.getRegistry().get("2", "rnode", "r2")

    assert any(cmd == "bird -d" for cmd, _ in r1.getStartCommands())
    assert not any(cmd == "bird -d" for cmd, _ in r2.getStartCommands())
    assert _file_content(r2, "/etc/bird/bird.conf") == ""

    frr_conf = _file_content(r2, "/etc/frr/frr.conf")
    assert "router bgp 2" in frr_conf
    assert "neighbor 10.101.0.152 remote-as 152" in frr_conf
    assert "RM_CONNECTED_TO_BGP" in frr_conf
    assert "LC_LOCAL_OR_CUSTOMER" in frr_conf
    assert "router ospf" in frr_conf
    assert "interface net0" in frr_conf


def test_exabgp_service_renders_speaker_and_router_peer():
    emu = Emulator()
    base = Base()
    routing = Routing()
    exabgp = ExaBgpService()

    base.createInternetExchange(100)

    as2 = base.createAutonomousSystem(2)
    as2.createNetwork("net0")
    as2.createRouter("router0").joinNetwork("net0").joinNetwork("ix100")

    as180 = base.createAutonomousSystem(180)
    as180.createHost("exabgp").joinNetwork("ix100", address="10.100.0.180")

    exabgp.install("as180_exabgp") \
        .setLocalAsn(180) \
        .addPeer("router0", router_asn=2, router_relationship="customer") \
        .addAnnouncement("198.51.100.0/24")
    emu.addBinding(Binding("as180_exabgp", filter=Filter(asn=180, nodeName="exabgp")))

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(exabgp)
    emu.render()

    speaker = emu.getRegistry().get("180", "hnode", "exabgp")
    router = emu.getRegistry().get("2", "rnode", "router0")

    exabgp_conf = _file_content(speaker, "/etc/exabgp/exabgp.conf")
    assert "neighbor 10.100.0.2" in exabgp_conf
    assert "local-as 180" in exabgp_conf
    assert "peer-as 2" in exabgp_conf
    assert "198.51.100.0/24" in exabgp_conf

    bird_conf = _file_content(router, "/etc/bird/bird.conf")
    assert "protocol bgp exabgp_180" in bird_conf
    assert "neighbor 10.100.0.180 as 180" in bird_conf
    assert "bgp_large_community.add(CUSTOMER_COMM)" in bird_conf
    assert "bgp_local_pref = 30" in bird_conf


def test_exabgp_service_renders_frr_router_peer_without_bird():
    emu = Emulator()
    base = Base()
    routing = Routing()
    exabgp = ExaBgpService()

    base.createInternetExchange(100)

    as2 = base.createAutonomousSystem(2)
    as2.createNetwork("net0")
    as2.createRouter("router0", routingBackend="frr").joinNetwork("net0").joinNetwork("ix100")

    as180 = base.createAutonomousSystem(180)
    as180.createHost("exabgp").joinNetwork("ix100", address="10.100.0.180")

    exabgp.install("as180_exabgp") \
        .setLocalAsn(180) \
        .addPeer("router0", router_asn=2, router_relationship="customer") \
        .addAnnouncement("198.51.100.0/24")
    emu.addBinding(Binding("as180_exabgp", filter=Filter(asn=180, nodeName="exabgp")))

    emu.addLayer(base)
    emu.addLayer(routing)
    emu.addLayer(exabgp)
    emu.render()

    speaker = emu.getRegistry().get("180", "hnode", "exabgp")
    router = emu.getRegistry().get("2", "rnode", "router0")

    assert _file_content(router, "/etc/bird/bird.conf") == ""
    frr_conf = _file_content(router, "/etc/frr/frr.conf")
    assert "router bgp 2" in frr_conf
    assert "neighbor 10.100.0.180 remote-as 180" in frr_conf
    assert "neighbor 10.100.0.180 description exabgp_180" in frr_conf
    assert "neighbor 10.100.0.180 next-hop-self" in frr_conf

    exabgp_conf = _file_content(speaker, "/etc/exabgp/exabgp.conf")
    assert "peer-as 2" in exabgp_conf
    assert "198.51.100.0/24" in exabgp_conf
