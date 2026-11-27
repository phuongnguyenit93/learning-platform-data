# Designing Cross-Environment Connectivity, DNS, and Routing

Hybrid and multicloud infrastructure connects systems running in data centers, offices, Google Cloud, and potentially AWS or Azure. A working network connection is not merely two machines being able to ping each other. Applications need to resolve the right service names, packets must have proper forward and return paths, firewalls must allow the right traffic, and a single link failure must not disconnect the entire system.

On Google Cloud, key components include VPC, HA VPN, Cloud Interconnect, Cloud Router, Cloud DNS, firewalls, and managed resource connectivity mechanisms. This lesson guides you through designing them into a scalable architecture: defining IP ranges, selecting connectivity technologies, building routing policies, designing bidirectional DNS resolution, and testing recovery capabilities. The ultimate goal is to enable applications deployed on Compute Engine, GKE, Cloud Run, and data services to communicate with the right destination, with the right permissions, and with appropriate reliability and cost.

## 1. Start From Connectivity Requirements, Not From Products

Before creating tunnels or configuring DNS, network and application teams must agree on which systems genuinely need to connect. A solid design records sources, destinations, protocols, traffic demands, latency expectations, and ownership of that connection.

| Question | Example to clarify | Architectural impact |
| --- | --- | --- |
| Where are source and destination? | Production GKE to on-premises Oracle | Are bidirectional routes and private DNS required? |
| What kind of traffic? | HTTPS, database TCP, DNS UDP/TCP, replication | Firewall rules and MTU verification |
| Bandwidth and latency? | Steady load or large batch transfers | Choosing VPN or Interconnect and capacity |
| Availability level? | Must survive loss of a device, tunnel, or zone | Number of physical links, BGP peers, and failover approach |
| Security boundaries? | Production must not access dev directly | Segmentation, IAM, routing, and firewalls |
| How are services discovered? | Internal name `db.corp.example.com` | Private DNS zones, conditional forwarding, resolvers |
| Who operates it? | Network team manages BGP, platform team manages DNS | Change permissions and runbooks |

Not every system needs private IP reachability across environments. If an application only needs to call one specific API, an HTTPS, gateway, or supported Private Service Connect approach can limit connectivity scope far more effectively than a fully routed network. Choose the minimal connectivity level that satisfies the business need.

## 2. Hybrid and Multicloud Reference Architecture

A sample architecture includes a data center with routers, DNS, and a database; a Google Cloud VPC with GKE/Compute Engine workloads; and a network in another cloud provider. Connections between them require explicit decisions on security, IP addressing, route advertisement, and DNS.

~~~mermaid
flowchart LR
  subgraph DC["Data center"]
    DR["Routers / firewalls A, B"]
    DNSDC["Internal DNS"]
    DBDC["Internal database"]
  end
  subgraph GCP["Google Cloud"]
    CR["Cloud Router / BGP"]
    VPC["Production VPC"]
    DNSG["Cloud DNS private / forwarding"]
    APP["GKE / VM / Cloud Run"]
  end
  subgraph OTHER["Other cloud"]
    RTR["VPN gateway / cloud router"]
    SVC["Workloads / resolver"]
  end
  DR <-->|"HA VPN or Interconnect"| CR
  CR --- VPC
  VPC --- APP
  VPC --- DNSG
  DR --- DNSDC
  DR --- DBDC
  RTR <-->|"VPN or supported private connectivity"| VPC
  RTR --- SVC
~~~

This diagram shows logical flows, not a configuration spec covering every port and device. In real deployments, explicitly separate redundant links, physical termination points, BGP sessions, route limits, and security policies. Do not treat a link to another cloud as an automatic backup path for the data center unless that transit capability has been designed and tested.

Three layers must be evaluated independently:

1. **Connectivity (underlay):** are IPsec tunnels or dedicated circuits up and provisioned with sufficient capacity?
2. **Routing:** which prefixes are learned and advertised, which next hop is selected, and does a return path exist?
3. **Name resolution (DNS):** which resolver resolves service names, and do private records point to current addresses?

An application can still fail even when physical links and BGP are healthy—for example, if DNS returns a stale IP or a firewall allows outbound packets while dropping return traffic.

## 3. IPAM: Designing Addressing Before Connecting

IP Address Management (IPAM) is the most important step to avoid architectural rework later. Address spaces routed to each other must not overlap unless an explicit address translation design is in place. You must account for ranges that applications do not see directly: GKE secondary ranges, private service ranges, VPN appliance networks, and address ranges in other clouds.

Example planning table for a test environment:

| Network or function | Example range | Notes |
| --- | --- | --- |
| On-premises | 10.10.0.0/16 | Application and database subnets at the DC |
| GCP production - primary subnet | 10.20.0.0/16 | Split into smaller subnets by region and tier |
| GKE Pod secondary range | 10.21.0.0/16 | Used when GKE is configured as VPC-native |
| GKE Service secondary range | 10.22.0.0/20 | ClusterIP range; verify actual demand |
| Private services access | 10.23.0.0/16 | Reserved if the architecture uses PSA-backed services |
| GCP staging | 10.30.0.0/16 | Separate policies and routes from production |
| AWS or other cloud | 10.40.0.0/16 | Non-overlapping with the networks above |
| Azure or other cloud | 10.50.0.0/16 | Non-overlapping with the networks above |

These ranges illustrate allocation structure only, not default settings or sufficient sizing for every workload. Actual plans must consider growth, regional subnets, IPs for GKE nodes and Pods, service VIPs, private endpoint IPs, and product-specific technical limits.

Key principles:

- Reserve CIDRs by administrative domain and environment before creating subnets, rather than allocating ad hoc per project.
- Do not inspect only primary subnet ranges; check secondary ranges, service-allocated ranges, and on-premises networks as well.
- Establish clear authority for allocating or reclaiming CIDRs; every change must update IPAM.
- Evaluate IPv6 separately if the system uses dual-stack; route advertisement rules and product support may differ from IPv4.
- Use NAT to handle overlapping addresses only when renumbering is impossible and you accept the added complexity in logging, firewalls, DNS, and troubleshooting.

When networks in two clouds share the same CIDR, BGP does not automatically resolve conflicts. Overlapping destination routes can send traffic to the wrong location or break return paths. If overlapping addresses must remain, design an address translation layer or intermediate gateway with unique translated addresses and test end-to-end per application.

## 4. Choosing Connectivity: HA VPN, Interconnect, or Other Options?

No single connectivity service is optimal for every requirement. HA VPN generally suits IPsec connectivity needs with fast provisioning and bandwidth within supported limits. Cloud Interconnect suits requirements for predictable capacity and dedicated circuits. Some multicloud models can use Cross-Cloud Interconnect or partner provider connectivity where supported by region, provider, and product.

| Option | Characteristics | When to consider |
| --- | --- | --- |
| HA VPN | IPsec connectivity over the internet or supported paths, using BGP with Cloud Router | Building secure hybrid connectivity with tunnel and peer redundancy |
| Dedicated Interconnect | Dedicated physical connectivity at a supported colocation facility | High, steady traffic requiring physical connection control |
| Partner Interconnect | Connectivity via a supported service provider | No direct colocation presence or prefer using a partner |
| Cross-Cloud Interconnect | Dedicated connectivity with supported cloud providers | Multicloud needing high capacity and private paths per availability |
| Cross-cloud VPN | IPsec and BGP gateways across two clouds | Moderate traffic needing flexible deployment |
| Application-level connectivity | HTTPS, API gateways, proxies, or PSC where appropriate | Only need access to a single service, avoiding full network exposure |

**HA** must be designed from the outset: two links or two tunnels do not guarantee independence if they rely on the same router, firewall appliance, power source, or provider. With Interconnect, reliability design typically requires multiple connections across appropriate locations and failure domains, paired with corresponding VLAN attachments and BGP sessions.

Measure actual application bandwidth—especially in heavy-transfer directions—and compare it against per-link limits. Also evaluate data transfer fees, port/attachment/tunnel charges, egress fees, and partner fees before deciding. A VPN that is the right choice initially may no longer fit if replication traffic grows several-fold.

## 5. Cloud Router and BGP Operate at the Routing Layer

Cloud Router is a service that controls dynamic route exchange via BGP with supported gateways or connections. Cloud Router is **not** a traditional packet-forwarding appliance: data packets are forwarded by Google Cloud's network infrastructure and connectivity components, while Cloud Router manages routing information.

A BGP session requires compatible parameters on both ends: ASN, peering addresses, IPv4/IPv6 capability per product, timers, and policies. Advertised prefixes must be ranges that the receiving side is genuinely permitted and able to reach.

Concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| Learned routes | Prefixes Google Cloud learns from the peer router via BGP |
| Advertised routes | Prefixes Cloud Router advertises to the peer |
| Regional dynamic routing | Scopes dynamic route application according to the VPC's regional mode |
| Global dynamic routing | Allows dynamic route application across multiple regions per network policy, requiring attention to route priority rules |
| BGP base advertised priority | Priority signal for advertised routes in the design; does not override peer-side policy |
| Route next hop | The actual connection or resource through which traffic is forwarded |

Check the VPC dynamic routing mode, especially when workloads span multiple regions. A design verified only from a subnet in one region may overlook that subnets in another region do not use routes as expected.

Do not advertise a default `0.0.0.0/0` route across the connection just to fix an access issue. A default route can send internet-bound or unintended traffic back through the data center, increasing latency and cost while creating bottlenecks or unsafe paths. Apply it only when it is an explicit architectural goal—such as centralized egress—and both return paths and security zones are designed accordingly.

## 6. Designing Route Priority and Failover

A system may have multiple paths: two VPN tunnels, two Interconnect attachments, or a primary Interconnect with a backup VPN. What matters is not only having multiple routes, but knowing which route is selected under what conditions and what happens when a BGP session drops.

Example policies:

| Scenario | Desired behavior | Verification |
| --- | --- | --- |
| Both connections healthy | Select primary path or load-balance per design | Observe chosen routes and traffic flows |
| One tunnel or BGP peer fails | Shift to the alternate path without advertising wrong CIDRs | Verify updated routes and successful requests |
| On-prem loses primary router | Do not lose all DNS and application connectivity | Test backup firewall/router failover |
| One region has an outage | Workloads in another region remain reachable if architecture permits | Check routing mode and remaining capacity |
| Backup link has lower capacity | Priority services continue operating without saturation | Measure throughput and enforce traffic prioritization |

Do not confuse "BGP session UP" with "application reachable." BGP can remain UP even while a firewall blocks TCP 443 or DNS is broken. Conversely, BGP DOWN indicates a routing-layer issue to investigate, not necessarily the direct cause of every outage if an alternate path remains active.

To steer traffic, study Google Cloud's route selection order, route priorities, BGP advertised priorities, and peer policies. Do not assume setting a priority value on one side controls both outbound and return paths. Asymmetric routing designs must also be evaluated against stateful firewalls and NAT devices at both ends.

## 7. Routing Across Multiple VPCs and Multiple Clouds

Google Cloud VPC Network Peering supports communication between peered VPCs subject to product routing rules and route import/export options. However, **VPC Peering does not provide automatic transitive routing**: if VPC A peers with B, and B peers with C, A cannot reach C through B.

For multi-spoke architectures or large-scale hybrid connectivity, evaluate Network Connectivity Center (NCC) and supported spoke types to organize a hub-and-spoke topology. Explicitly configure site-to-site data transfer modes, spoke groups, route exchange, and supported features per spoke type and region; do not assume every pair of spokes automatically exchanges all routes.

For AWS and Azure, the peer side has its own routing components, gateways, and route tables. The design must clearly specify:

- Which CIDRs in each VPC/VNet and subnet genuinely require routes.
- Whether routes are propagated automatically or must be declared statically on the peer side.
- Whether the combination of BGP ASNs, tunnels, and networks is supported by both providers.
- Firewalls, security groups, network security groups, or policies in each cloud.
- Whether any intermediate NAT or gateway rewrites source IPs used by the receiving side for access control.
- Which routes are permitted to act as transit paths between on-prem, GCP, AWS, and Azure.

A multicloud network needs least-privilege route exchange policies. For instance, GCP production needing access to a reporting service in AWS does not mean AWS should learn the entire GCP staging network or the entire on-premises management network.

## 8. DNS Is a Separate Design Plane

IP routing and DNS resolution are two distinct problems. Routing may work cleanly while applications still fail because internal names fail to resolve, records are stale, or resolvers return wrong public addresses.

In Google Cloud, Cloud DNS can provide:

| DNS component | Purpose |
| --- | --- |
| Private managed zone | Stores private DNS records and serves queries only to authorized VPCs |
| Forwarding zone | Forwards queries for a domain suffix to target DNS servers |
| DNS peering zone | Allows one VPC to use another VPC's DNS resolution pipeline where supported |
| Inbound forwarding policy | Provides query entry points so external networks, such as on-prem, can query the VPC's Cloud DNS resolver |
| DNS server policy and outbound forwarding | Controls how matching names are forwarded to external DNS servers |
| Public managed zone | Publishes public records; never replaces private zones when internal data needs restricted access |

Private zones are bound to authorized VPCs. Network connectivity or VPC Peering does not mean private records automatically appear in every VPC. Check private DNS access per VPC and choose peering or forwarding where needed.

DNS services help applications locate private workloads, but the existence of a record does not grant access to the service. After name resolution, firewalls, routing, ingress, IAM, and authentication must still be checked.

## 9. Designing Namespaces and Domain Ownership

Define a clear naming structure to avoid overlaps and query loops. Example:

| Namespace | Authoritative location or governance | Use case |
| --- | --- | --- |
| corp.example.com. | On-premises DNS | Internal hosts and databases |
| gcp.corp.example.com. | Cloud DNS private zone | Google Cloud private services |
| aws.corp.example.com. | AWS environment DNS | Internal services on AWS |
| azure.corp.example.com. | Azure environment DNS | Internal services on Azure |

These names are illustrative. In production systems, align on organization-controlled domains, public/private DNS policies, and record management workflows. Never create two authoritative zones with the same name and conflicting records without an explicit resolution strategy.

**Split-horizon DNS** can return different answers for the same name depending on who queries it. This pattern is useful when internal users should receive private IPs and external users should receive public IPs, but introduces troubleshooting complexity when resolvers cache differently.

Document:

- Which team owns which domains and subdomains.
- Which resolvers clients in GCP, on-prem, and other clouds query.
- Which records are allowed in public DNS vs. private-only DNS.
- TTL policies, record change workflows, and rollback procedures.
- Handling procedures when authoritative servers or forwarding targets become unavailable.

## 10. DNS From Google Cloud to On-Premises

Suppose a GKE workload needs to query `database.corp.example.com`, managed by an on-premises DNS server. A Cloud DNS forwarding zone can forward queries for the `corp.example.com.` suffix to the internal DNS server if connectivity and routing rules permit.

Conceptual flow:

~~~mermaid
sequenceDiagram
  participant App as GKE / VM
  participant Google as Cloud DNS resolver
  participant DC as On-prem DNS
  App->>Google: A database.corp.example.com?
  Google->>DC: Forward query per zone
  DC-->>Google: A 10.10.20.15
  Google-->>App: Return private IP
  App->>DC: TCP to 10.10.20.15 over VPN/Interconnect
~~~

Example creating a forwarding zone in a test VPC:

~~~bash
gcloud dns managed-zones create corp-forward \
  --project=PROJECT_ID \
  --description="Forward on-prem namespace" \
  --dns-name=corp.example.com. \
  --visibility=private \
  --networks=prod-vpc \
  --forwarding-targets=10.10.1.10
~~~

This is a reference configuration using an illustrative on-prem DNS server at `10.10.1.10`. Before using it, ensure Cloud DNS can reach the forwarding target over a supported connection, the DNS server accepts the queries, and the return path works. Forwarding may originate from a special Cloud DNS source IP range, so on-prem firewalls and return routing must follow current Cloud DNS forwarding documentation rather than relying solely on workload subnet CIDRs.

Check both UDP and TCP port 53 as appropriate. DNS can require TCP for large responses, fallback, or specific flows. If a query returns NXDOMAIN, verify the zone suffix, authoritative records, and caches before concluding the network link is broken.

## 11. DNS From On-Premises Into Google Cloud

Suppose a server in the data center needs to look up `api.gcp.corp.example.com`, a record in a Google Cloud private zone. The on-prem resolver can configure a conditional forwarder for `gcp.corp.example.com.` pointing to the Cloud DNS inbound forwarding entry point.

Design steps:

1. Create the private managed zone `gcp.corp.example.com.` and authorize the right Google Cloud VPCs.
2. Create a DNS policy enabling inbound forwarding for the VPC as supported.
3. Retrieve the list of inbound forwarding entry point addresses provided by Google Cloud.
4. Configure the on-prem DNS server conditional forwarder for that suffix toward those inbound addresses.
5. Allow DNS traffic and verify forward/return routes across the appropriate connection.
6. Query a sample name from the DC; confirm the returned IP matches the intended VPC or private endpoint.

Illustrative command enabling an inbound forwarding policy:

~~~bash
gcloud dns policies create prod-inbound \
  --project=PROJECT_ID \
  --networks=prod-vpc \
  --enable-inbound-forwarding \
  --description="Enable DNS queries from connected networks"
~~~

After creating the policy, inspect the policy details and the network's inbound resolver addresses to configure the DC side. Never hardcode inbound DNS addresses from an example into production. Having an inbound IP does not automatically grant network access: firewalls, routes, and DNS permissions must be properly designed.

Cloud DNS private zones must never be converted to public just so on-prem can find records. Use inbound forwarding, DNS peering, or a compatible name-resolution mechanism scoped to requirements.

## 12. DNS Across VPCs and Across Clouds

In organizations using Shared VPC, applications in a service project may use the host project's network. Clarify which VPC actually performs DNS queries and where private zones are administered. Do not confuse the project owning the application with the VPC boundary governing DNS.

Across multiple VPCs, consider:

- Attaching a private zone to multiple VPCs if the goal is sharing that exact zone and policies permit.
- Using a DNS peering zone to delegate resolution to another VPC without duplicating zone data.
- Using a forwarding zone when a specific DNS resolver is responsible for a namespace.
- Creating separate zones per production/staging environment when name and permission isolation is needed.

DNS peering is not equivalent to IP routing. One VPC may successfully resolve a name in another VPC yet lack routes or firewall rules to reach the resolved IP. Verify both planes independently.

With AWS, private DNS integration commonly involves Route 53 Resolver and properly configured inbound/outbound endpoints; with Azure, Azure DNS Private Resolver and forwarding rulesets can be used where supported. When connecting over GCP VPN/Interconnect, design query direction, source IPs, return routes, ACLs, and administrative ownership across both clouds. Never assume a partner cloud's private hosted zone can be resolved directly from GCP without appropriate forwarding or resolver mechanisms.

A common mistake is configuring bidirectional forwarding for the same suffix when neither side is truly authoritative. Queries can then loop between resolvers until they time out. Explicitly document which side is the source of truth for each namespace and use forwarding solely to direct queries toward that side.

## 13. Resolution Order and Handling Name Conflicts

When public zones, private zones, peering zones, forwarding zones, and multiple resolvers coexist in the same environment, how names match can heavily affect behavior. Zones with more specific suffixes typically take precedence under applicable resolution rules, though exact behavior depends on Cloud DNS mechanics and network policies.

For example, if both exist:

- A forwarding zone for `corp.example.com.` to the DC.
- A private zone `gcp.corp.example.com.` in GCP.

A query for `api.gcp.corp.example.com.` should be handled by the more specific zone and appropriate resolver configuration rather than forwarding everything under `corp.example.com.` back to the DC. During implementation, verify how Cloud DNS selects zones and what overlap rules are supported.

Test at least these cases:

| Case | What to verify |
| --- | --- |
| Record exists in GCP private zone | Returns expected private IP |
| Record exists on-prem | GCP forwards to the intended target DNS server |
| Record does not exist | Returns valid NXDOMAIN with no loops |
| Same name exists in private and public | Resolver returns the appropriate answer for each side |
| Primary DNS target fails | Queries fail over to backup target if configured and supported |
| TTL lowered before cutover | Clients and resolvers pick up the new record within expected window |

DNS caching can delay the effect of record changes. Both TTL and negative caching matter: a query that fails before a record is created can keep returning a negative response for some time. Plan DNS changes ahead of cutover rather than lowering TTL mid-incident and expecting all caches to clear immediately.

## 14. Securing Connectivity, DNS, and Network Segmentation

VPN encrypts traffic at the tunnel layer using IPsec. Private physical connectivity does not automatically mean packets are encrypted end-to-end. Whether using Interconnect or VPN, protocols carrying sensitive data still require TLS/mTLS, application authentication, and appropriate access controls.

Example network policy table:

| Source | Destination | Protocol | Purpose | Principle |
| --- | --- | --- | --- | --- |
| GKE app subnet | On-prem database | Database TCP port | Business queries | Only authorized subnets/identities |
| On-prem DNS resolver | Cloud DNS inbound entry point | UDP/TCP 53 | Resolve GCP private names | Only authorized resolvers |
| Cloud DNS forwarding | On-prem DNS | UDP/TCP 53 | Resolve DC internal names | Allow documented forwarding source |
| Admin subnet | Bastion or management endpoint | SSH/HTTPS per architecture | Controlled administration | Never open to the entire network |

Beyond VPC firewalls, inspect DC firewalls/routers, GKE network policies, resolver ACLs, and security controls in other clouds. Binding a DNS name to a resource does not replace IAM or application authentication; DNS is an address discovery mechanism, not an access grant.

Recommended controls:

- Block unauthorized name resolution or connectivity between dev, staging, and production.
- Restrict changes to Cloud DNS zones, Cloud Router, VPN tunnels, and route advertisements via separation of duties.
- Audit logs for IAM, DNS, firewall, and connectivity changes; enforce audit logging and change management.
- Never expose a DNS resolver as an open recursive service to arbitrary internet addresses.
- Avoid embedding sensitive data in DNS query names or unprotected logs.
- Where possible, use private endpoints and service identities instead of broad routes just to reach one API.

## 15. Cloud NAT, Private Service Connect, and Managed Services

Not every Google Cloud service with a private IP behaves like a VM in a subnet. When designing connectivity to Cloud SQL, services via Private Services Access (PSA), Private Service Connect (PSC), or other managed services, verify that service's addressing and routing model.

| Component | Key role and limitations |
| --- | --- |
| Cloud NAT | Enables certain workloads to reach external endpoints without public IPs; does not create VPNs or inbound routes into a DC |
| Private Services Access | Private connectivity to supported Google services via service networking, using dedicated allocated IP ranges |
| Private Service Connect | Private endpoint or published service model depending on product type; requires matching DNS and IAM/acceptance |
| Serverless VPC Access / Direct VPC egress | Mechanisms for serverless workloads to use VPC networking per configuration and support |

For Cloud Run accessing an on-prem database, check the VPC egress mechanism, network, subnet, and routes to the destination IP. Never assume Cloud Run uses network addresses directly like a VM; choose Direct VPC egress or a service-supported VPC connectivity mechanism and verify the path.

With PSA or PSC, clarify who owns the endpoint, which IP ranges need routing or advertisement, and whether access from on-prem is supported. Do not blindly advertise every service-allocated range over BGP just because you see a private IP; check the service's specific routing guidance.

## 16. Example Configuration and Verification Workflow

Suppose VPC `prod-vpc` in region `asia-southeast1` needs to connect on-prem via HA VPN. Below are illustrative commands to create foundational components and inspect status; this is **not** a complete procedure for creating dual gateways, tunnels, and BGP peers.

Create the Cloud Router and HA VPN gateway:

~~~bash
gcloud compute routers create prod-router \
  --project=PROJECT_ID \
  --network=prod-vpc \
  --region=asia-southeast1 \
  --asn=64514

gcloud compute vpn-gateways create prod-ha-vpn \
  --project=PROJECT_ID \
  --network=prod-vpc \
  --region=asia-southeast1
~~~

You must still add peer VPN gateways, external IPs, shared secrets, tunnel mappings, and BGP interfaces/peers according to the specific topology. Both ends must align on tunnel parameters, BGP peering addresses, and route policies; never deploy a tunnel to production from an example lacking redundancy parameters.

Check Cloud Router status:

~~~bash
gcloud compute routers get-status prod-router \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

List VPN tunnels in the region:

~~~bash
gcloud compute vpn-tunnels list \
  --project=PROJECT_ID \
  --filter="region:asia-southeast1"
~~~

Verify that BGP sessions are in the expected state, check learned/advertised prefix counts, confirm proper next hops, and verify there are no unintended routes. Then run tests from workloads to the target application IP. Healthy tunnel status alone does not prove service ports are permitted.

For DNS, verify separately:

~~~bash
nslookup database.corp.example.com
nslookup api.gcp.corp.example.com
~~~

When targeting specific resolvers:

~~~bash
dig @DNS_SERVER_IP database.corp.example.com A
dig @CLOUD_DNS_INBOUND_IP api.gcp.corp.example.com A
~~~

These commands are examples run from an authorized host/client with matching routes; replace names and IPs accordingly. On systems without `dig`, use an equivalent DNS tool. Also test TCP connectivity to the resolved IP to distinguish DNS issues from network issues.

## 17. Testing Routing, DNS, and Failover

An end-to-end checklist should progress from name resolution to application connectivity, and only then test link failures.

| Test case | How to test | Expected result |
| --- | --- | --- |
| GCP to DC by IP | TCP to an authorized test endpoint | Succeeds with expected source/destination |
| GCP to DC by name | GCP resolver queries on-prem name | Returns right private IP and connects cleanly |
| DC to GCP by name | DC resolver queries GCP private suffix | Returns right record from Cloud DNS |
| Disallowed prefix | Test source or destination outside policy | Blocked at the boundary, logged as appropriate |
| Loss of one tunnel/peer | Controlled state change on test path | Backup route takes over per design |
| Loss of one DNS target | Stop test target per procedure | Resolver recovers via configured redundancy |
| DNS record change | Lower TTL ahead of plan, apply change | Clients switch to new IP within expected window |
| High traffic | Increase load within allowed limits | Does not exceed provisioned bandwidth, sessions, or quotas |
| Cut link then restore | Observe routes, latency, and app errors | System does not get stuck on the wrong path |

With stateful firewalls or NAT devices, asymmetric forward and return paths can break TCP connections even when ICMP works in some places. Use `traceroute`/`tcpdump` or equivalent diagnostic tools at authorized points; combine firewall logs and BGP state to locate where packets are dropped.

Google Cloud's Network Intelligence Center and connectivity diagnostic tools can help analyze configured paths within supported scope, but simulated results do not completely replace end-to-end testing across partner networks. Observe logs and metrics on the on-prem or partner cloud side as well.

## 18. Reliability Monitoring and Incident Troubleshooting

Observability for hybrid connectivity should capture both infrastructure and application signals:

- VPN tunnel status, BGP sessions, and changes in learned/advertised routes.
- Inbound/outbound bandwidth, packet loss, RTT, jitter, and application error rates.
- DNS error counts, DNS response latency, forwarding failures, and abnormal NXDOMAIN spikes.
- Firewall denies, NAT state, drop counters, and recent policy changes near incident onset.
- SLOs for critical journeys, such as a GKE application accessing an on-prem database.

Example runbook when an application cannot reach the database by name:

1. Determine whether DNS lookup returns NXDOMAIN, times out, or returns an incorrect IP.
2. If DNS fails, query the designated resolver directly; inspect private/forwarding zones, targets, and UDP/TCP 53 paths.
3. If DNS returns the right IP, test direct connectivity to the IP and port.
4. Check BGP sessions, learned routes, route priorities, and return paths.
5. Check firewalls in both GCP and DC, as well as NAT or stateful inspection devices.
6. Correlate error onset with changes in DNS TTL, VPN, route advertisements, or workload scaling.
7. If the issue is isolated to one link, fail over per runbook and monitor service health afterward.

Never resolve an incident by temporarily opening all firewall rules or advertising a default route without understanding the blast radius. Emergency changes require approval, logging, an expiration time, and a rollback plan.

## 19. Cost, Latency, and Long-Term Operations

Connectivity infrastructure carries both fixed and usage-based costs. VPN incurs tunnel and data charges; Interconnect incurs port/attachment and data transfer charges; partner providers have separate fees. Costs also arise from inter-region/cross-cloud traffic, DNS queries, and monitoring systems.

When choosing an architecture, evaluate:

- Primary/backup link costs and bandwidth scalability.
- Egress traffic between cloud and on-prem or between clouds.
- RTT and its impact on chatty protocols such as database transactions.
- DNS forwarding query volume, cache effectiveness, and peer resolver load.
- Operational cost of maintaining multiple routers, BGP peers, firewall policies, and configurations across two or more clouds.
- Vendor lock-in level, failover difficulty, rollback capability, and on-call staffing.

Not all traffic should cross environments synchronously in real time. For analytics or bulk data, consider batch sync, event-driven patterns, or appropriate data transfer services instead of routing every user request across a distant link. This reduces round trips and isolates failure domains.

A very high-bandwidth link remains unreliable if DNS and applications lack failover capability. Evaluate cost alongside SLOs and resilience, not merely price per GB.

## 20. Lab: Designing Hybrid Database Access

**Scenario:** A company maintains an internal database in its DC, while a Spring Boot API runs on GKE in Google Cloud. The API must connect to the database using `database.corp.example.com`, and the DC operations team needs to query a private GCP management endpoint via `admin.gcp.corp.example.com`.

**Assumed requirements:**

- GCP production uses subnet `10.20.10.0/24`; the DC database is at `10.10.20.15`.
- No database access from staging or the public internet.
- Two independent connection paths within feasible technical constraints.
- Losing one path has a documented failover procedure; DNS failures must not cause query loops.
- Every route and DNS configuration change has an owner and a rollback method.

Deliverables to build:

1. An IPAM table covering primary/secondary ranges and advertised ranges.
2. A diagram showing dual paths, Cloud Router/BGP peer placement, firewalls, and resolvers.
3. Lists of routes GCP needs to learn from the DC and routes the DC needs to learn from GCP.
4. A firewall matrix from the application subnet to the database and between both DNS systems.
5. Private DNS zone `gcp.corp.example.com.`, forwarding zone `corp.example.com.`, and conditional forwarders at the DC.
6. A test suite distinguishing IP connectivity, DNS resolution, application TCP, and failover.
7. A list of metrics, alerts, costs, and rollback procedures if cutover fails.

**Evaluation criteria:** the design has no overlapping CIDRs; forward and return routes are explicit; each DNS namespace has one authoritative source; no overly broad routes are advertised; genuine path redundancy exists; policies allow only required sources and ports; and tests prove the application works by hostname rather than merely IP ping.

## 21. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only primary subnets and forgetting GKE secondary/PSA | Overlapping CIDRs, broken routing | Centralize IPAM across all address ranges |
| Running two VPN tunnels with a single point of failure | Losing one device still drops all connectivity | Design distinct failure domains and true redundant paths |
| Assuming BGP UP means applications work | DNS/firewalls or ports may still fail | Run application-level end-to-end tests |
| Using a default route to fix one missing prefix | Unrelated traffic gets redirected | Advertise minimal prefixes and inspect route tables |
| Assuming VPC Peering is automatically transitive | Workloads cannot reach a third VPC | Use explicitly supported topologies/routing |
| Attaching a private DNS zone to only one VPC | Other VPCs cannot resolve names | Check authorization and DNS peering/forwarding |
| Unconditional bidirectional DNS forwarding | Query loops and timeouts | Assign one authoritative owner per namespace |
| Opening only UDP 53 or forgetting return routes | Some DNS queries fail | Verify TCP/UDP, forwarding source IPs, and bidirectional routing |
| Ignoring stateful firewalls or NAT | Asymmetric return path drops connections | Verify symmetry/translation and state handling |
| Measuring only intra-GCP latency | Ignores RTT to DC and other clouds | Measure application paths from real sources |
| Skipping failover drills | Redundancy exists only on paper | Run periodic drills with safe abort criteria |

## 22. Pre-Production Design Checklist

- Approved architecture diagram with environments, sources/destinations, and application requirements.
- IPAM covers VPC subnets, GKE secondary ranges, PSA/PSC endpoints, and partner networks.
- Connectivity technology chosen based on bandwidth, security, supportability, and cost.
- Redundant connections do not share an unacceptable single point of failure.
- BGP ASNs, peers, learned/advertised prefixes, and routing mode documented.
- Forward/return routes verified, avoiding broad routes when only specific IP ranges are needed.
- No assumptions that VPC Peering or multicloud gateways route transitively by default.
- DNS namespaces have clear owners, with properly scoped private/forwarding/peering zones.
- On-prem resolvers and Cloud DNS inbound/outbound forwarding have proper return routing.
- Firewalls, DNS UDP/TCP 53, applications, and authentication mechanisms verified.
- Failover, DNS outages, TTL changes, traffic spikes, and link recovery tested.
- Dashboards, alerts, runbooks, change reviews, and on-call owners established.
- Cost estimates cover connectivity links, traffic, DNS, and operational overhead.
- No temporary routes, records, or permissions left behind after testing.

Reliable hybrid and multicloud connectivity is the coordination of three planes: a network capable of carrying packets, routing that selects the right paths, and DNS that returns the right service addresses. With Google Cloud, HA VPN or Interconnect provides the connectivity foundation, Cloud Router exchanges routing information, Cloud DNS helps environments resolve the right names, and firewalls, IAM, and end-to-end testing protect the application path. When every IP range, prefix, namespace, and backup path has an owner and verified test evidence, an organization can scale across environments while keeping operational risk under control.
