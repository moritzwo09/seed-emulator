# Control Plane Design Related to IBGP and MPLS

- We want to support the following four modes:
  - Full mesh among core and edge
  - Route reflector among core and edge
  - Full mesh among edge + BGP-free core
  - Route reflector among edge + BGP-free core

- Inside the Autonomous System class, we set the following. Ibgp and mpls layers will then use the setting to configure each routers accordinginly.

```
ibgp_mode = "full-mesh" | "route-reflector"
bgp_scope = "all-routers" | "edge-only"
core_forwarding = "plain-ip" | "mpls" | "sr" | "tunnel" | "redistribute"
```

- For the route reflector mode, if users does not creat cluster ID or designate route reflector, the AS class should decide the default values. The decision should be done inside the AS, not inside the ibgp layer. 


- We want to clearly separate the duties of AS class and the ibgp/mpls layers. The AS object provides the intent on how it wants the internal routing to work, and then set up the routers accordingly. The ibgp/mpls layer will then implement the intent. The ibgp/mpls layers should not modify the intent or properties of the AS object. 