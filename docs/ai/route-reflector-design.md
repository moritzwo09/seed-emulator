# Design: Route Reflector

## Goal

Revise the implemenation of the route reflector in the emulator


## Design Principles 

- Keep the configuration of route reflector structure inside the `AutonomousSystem` class, not in the ibgp layer.


## API design

- Introduce an API called `completeIbgpSetup()` inside the `AutonomousSystem` class. It inspects the `AutonomousSystem` object and all the routers inside this AS, finding any place where ibgp setup is incomplete, and complete it. 
- The reason for this API: Users might not set up the route reflector structure inside the AS completely, we need to automatically complete the setup. 
- Who invokes this API?  When `ibgp` starts rendering for an AS, it first calls this API to complete the ibgp setup within the AS. 
- Principle: We choose to do this within the AS class, not at the ibgp layer, because we want all the ibgp-related setup to be done inside the AS, and the ibgp layer's job only focuses on rendering, i.e., turning the setup into actual system setup.
 


## Required Behavior

- Ensure at least one cluster ID is created for the AS. If users do not set one, a deterministic default cluster ID must be created. The first created cluster ID is set as the default. 
- Each cluster must have at least one route reflector, if users do not set one, a determininistic router is selected as the RR. The first router that joins the cluster is set as the default RR (a cluster might have multiple RR).
- Each router must join one cluster ID; if users do not set one, the router joins the default one of the AS.
- Each router must have one RR; if users do not set one, the default RR in the cluster is used. 
- A cluster allows multiple route reflectors, with one being the default. All the route reflectors within the same cluster must peer with one another.
- The default cluster ID must be decided by the AS. Use an ASN-derived IPv4-style string, for example `"10.{asn}.0.1"`, and ensure it does not conflict.

