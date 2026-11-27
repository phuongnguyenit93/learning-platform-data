# Design Connectivity, DNS, and Routing Across Environments

## Learning Objectives

A hybrid cloud architecture connects an on-premises environment with one or more clouds. A multi-cloud architecture connects workloads running across multiple cloud providers. In both cases, applications often need to access services, data, and identity systems located across different network domains. Successful connectivity is not just about creating a tunnel or a route: DNS must resolve names accurately, paths must have appropriate symmetry, security policies must restrict access, capacity must meet load, and the system must have a plan when a link or environment fails.

An inconsistent design can cause hard-to-investigate issues: clients resolving hostnames to unreachable private IPs; routes advertising the wrong CIDR and sending traffic to the wrong cloud; firewalls allowing outbound traffic while blocking return traffic; DNS forwarding loops; two sites using overlapping CIDRs; failover changing routes while resolvers still cache old addresses; or redundant connections existing on a diagram yet sharing the same conduit and failure domain as the primary connection.

This lesson explains how to design **connectivity, DNS, and routing across environments** in hybrid and multi-cloud architectures. It covers business requirements, topology, IP planning, private connectivity, VPN, transit hubs, routing, DNS architecture, segmentation, resiliency, observability, troubleshooting, and change operations. Each choice must be evaluated on latency, throughput, availability, security, data residency, scalability, cost, and operational complexity.

After this lesson, you will be able to:

- Distinguish between hybrid cloud, multi-cloud, private connectivity, overlay networks, and underlay networks.
- Identify flows, trust boundaries, latency, throughput, and availability requirements.
- Design a scalable IP address plan that avoids overlaps and supports route summarization.
- Choose between site-to-site VPN, dedicated private connections, and SD-WAN.
- Design hub-and-spoke, transit gateway, virtual WAN, or controlled mesh topologies.
- Design route propagation, static/dynamic routing, BGP, filtering, and path preference.
- Design DNS namespaces, resolvers, conditional forwarding, private zones, and split-horizon DNS.
- Prevent DNS forwarding loops, stale caches, and cross-environment resolver risks.
- Build segmentation by environment, application, data classification, and trust level.
- Design redundant paths, failover, health checks, and capacity for site/link outage scenarios.
- Observe network/DNS health using flow logs, resolver logs, telemetry, and synthetic probes.
- Build runbooks, change control, incident response, and end-to-end connectivity tests.

## 1. Why Hybrid and Multi-Cloud Connectivity Is an Architectural Problem

An organization might run ERP in a data center, new APIs on Cloud A, analytics on Cloud B, and a shared identity provider. A single business transaction may traverse an API gateway, application services, databases, payment providers, and message brokers across different network domains.

When environments are interconnected, the system forms a distributed network with multiple control layers:
- Physical/underlay networks of the data center, carriers, and cloud providers.
- Overlay networks such as IPsec tunnels, SD-WAN, or virtual networks.
- Routing domains and route advertisements.
- Firewalls, security groups, NACLs, and network policies.
- DNS resolvers, private zones, and service discovery.
- Identity and workload authentication.
- Observability, incident response, and change governance.

A route existing does not prove an application can work. Name resolution, route selection, firewalls, TLS, authentication, service health, and application policies must all be verified together.

### 1.1. Connectivity Models

| Model | Characteristics | Best-fit scenarios |
| --- | --- | --- |
| On-premises to one cloud | Data center/VPN connects to one VPC/VNet | Extending an existing system to the cloud |
| Hybrid hub-and-spoke | Transit hub connects multiple spokes and data centers | Many workloads needing centralized connectivity |
| Multi-cloud hub | A network hub or routing domain connects multiple providers | Workloads distributed across clouds |
| Cloud-to-cloud direct | Two clouds connected via VPN/private interconnect | Data transfers or service dependencies between two clouds |
| SD-WAN overlay | Controls connectivity across sites/carriers/clouds via policy | Many branches and diverse transport links |
| Application-level connectivity | APIs, message brokers, service mesh, or secure proxies | Only capability integration is needed, without broad network extension |

Not every hybrid application needs layer-3 network extension between two environments. For some integrations, an API gateway, private service endpoint, message broker, or file transfer service can provide a narrower trust boundary and simpler operations.

### 1.2. Network Connectivity vs. Application Connectivity

Network connectivity provides packet delivery between endpoints. Application connectivity also includes:
- Correct DNS hostname resolution.
- Valid TLS certificates and trust chains.
- Authentication/authorization.
- Protocols/ports and application policies.
- Service discovery and endpoint health.
- Retries, timeouts, and idempotency.
- Data classification and auditing.

When troubleshooting an incident, do not conclude “the network is up” just because ping or a TCP handshake succeeds. The application can still fail due to TLS, identity, DNS, proxies, or policies.

## 2. Gather Requirements Before Drawing the Topology

Design starts with business flows, not with picking a VPN appliance or transit gateway product.

### 2.1. Build a Flow Matrix

Each flow should describe source, destination, protocol, port, direction, data classification, traffic profile, and owner.

| Flow | Source | Destination | Protocol | Criticality |
| --- | --- | --- | --- | --- |
| Booking API to legacy ERP | Cloud A app subnet | ERP private subnet | HTTPS | High |
| Cloud A app to on-prem database | Private workload | Database subnet | TCP database port | Very high |
| Cloud B analytics to Cloud A object API | Analytics subnet | Private service endpoint | HTTPS | Scheduled |
| On-prem DNS to cloud private zone | Corporate resolver | Cloud resolver | DNS TCP/UDP 53 | High |
| Cloud workloads to identity | Private workload | Identity endpoints | HTTPS/LDAPS depending on design | Very high |
| Monitoring to network devices | Monitoring subnet | Network management subnet | Approved management protocols | High |

Do not create any-to-any rules simply because flows have not been cataloged yet. Missing information must become an action item to verify owners and application behavior.

### 2.2. Dimensions to Quantify

- Latency: round-trip time, p95/p99, and application deadlines.
- Throughput: peak Mbps/Gbps, packet rate, bursts, and concurrency.
- Availability: flow SLO, maintenance windows, and failure tolerance.
- Data volume: bytes/day, peak replication, and growth.
- Direction: ingress, egress, symmetric/asymmetric.
- Security: trust level, encryption, data classification, source identity.
- Residency: which regions/countries data is allowed to traverse.
- Recovery: RTO/RPO, failover time, and acceptable data lag.
- Cost: port/connectivity fees, VPN, egress, NAT, inspection, and operations.
- Ownership: teams managing source, destination, resolvers, and routes.

### 2.3. Critical Paths vs. Optional Paths

Separate synchronous flows required to complete a request from asynchronous/background flows. An application should not depend on the analytics network to confirm a booking if analytics can process later. Reducing synchronous dependencies can lower cross-environment availability and latency requirements.

## 3. IP Address Planning and Avoiding CIDR Overlap

An IP plan is the foundation of routing. CIDR overlaps between data centers, VPCs/VNets, and cloud providers can make routes indistinguishable or force complex NAT workarounds.

### 3.1. Build Structured Addressing

A plan can partition address space by:
- Organization/business domain.
- Environment: production, staging, development.
- Region/site.
- Network zone: ingress, application, data, management.
- Shared services.
- Future expansion and reserved blocks.

Illustrative example:

| Scope | Example CIDR | Role |
| --- | --- | --- |
| On-prem primary | 10.10.0.0/16 | Primary data center |
| On-prem DR | 10.11.0.0/16 | Recovery site |
| Cloud A production | 10.40.0.0/16 | Primary workloads |
| Cloud A staging | 10.41.0.0/16 | Testing/staging |
| Cloud B production | 10.60.0.0/16 | Analytics/other services |
| Shared services | 10.80.0.0/16 | DNS, monitoring, security |

These CIDRs are examples only and must be checked against all existing networks, partner networks, and future acquisitions before use.

### 3.2. Reserve and Summarize

Do not allocate the entire address space upfront. Keep reserved blocks for new regions/sites, subnet growth, IPv6, and transitions. Designs can summarize routes at the environment or region level to reduce advertised route counts; however, overly broad summaries can attract traffic into a network without an actual destination or mask a more specific route that should take priority.

### 3.3. Check for Overlaps

Before interconnecting:
1. Collect CIDRs from data centers, VPCs/VNets, Kubernetes pod/service networks, and partners.
2. Standardize prefixes and owners.
3. Calculate overlaps, including subnets not yet advertised in routing.
4. Identify CIDRs that are reserved but unused.
5. Evaluate IPv4/IPv6 dual stack.
6. Store an IPAM registry as the source of truth.
7. Block overlapping allocations via policy/process.

Kubernetes Pod CIDRs and Service CIDRs are frequently overlooked in IP inventories; when connecting clusters to external networks, overlaps can make routing or service discovery unpredictable.

### 3.4. When Addresses Cannot Be Changed

If two environments already have overlapping CIDRs, options include:
- Re-addressing one network under a migration plan.
- Using NAT/prefix translation where supported.
- Placing an application proxy or gateway instead of direct routing.
- Separating routing domains/VRFs and publishing only required service endpoints.
- Shifting to application-level connectivity.

NAT solves some addressing problems but complicates logs, source identity, troubleshooting, and return paths. Do not deploy broad NAT without documenting mappings and ownership.

## 4. Connectivity Options

### 4.1. Site-to-Site IPsec VPN

A site-to-site VPN creates an encrypted tunnel over the Internet or an intermediate network. The tunnel endpoints are typically a customer gateway and a cloud VPN endpoint.

Advantages:
- Relatively fast to deploy.
- Flexible across many sites and providers.
- Initial investment is usually lower than dedicated links.
- Can serve as a backup path.

Trade-offs:
- Throughput/latency are affected by the Internet and tunnel endpoints.
- Requires managing IKE/IPsec, keys/certificates, rekeying, and MTU.
- Can encounter fragmentation or MSS issues.
- Quality and routing failover depend on configuration at both ends.
- Internet paths may traverse multiple uncontrolled carriers.

VPN fits workloads with moderate requirements, temporary links, backup connectivity, or locations lacking dedicated circuits. Benchmark actual throughput instead of relying solely on nominal tunnel speeds.

### 4.2. Dedicated Private Connectivity

Dedicated connectivity uses circuits/ports or interconnects through a provider/partner to connect a private network to the cloud.

Advantages:
- Throughput and latency are typically more consistent than Internet VPN.
- Well-suited for large data transfers and latency-sensitive workloads.
- Can reduce Internet exposure along the network path.
- Supports various private routing models.

Trade-offs:
- Longer provisioning lead times.
- Port, cross-connect, carrier, and data transfer costs.
- Requires redundant circuits/sites/providers.
- A private connection does not automatically provide end-to-end encryption.
- Still requires firewalls, IAM, TLS, and segmentation.

Do not assume a dedicated circuit is encrypted by default. If data classification requires confidentiality in transit, evaluate IPsec or TLS over the dedicated connection.

### 4.3. SD-WAN

SD-WAN steers overlay traffic across sites and clouds based on policy, link quality, application class, or SLA. It can combine multiple Internet links and private circuits.

It fits enterprises with many branches needing centralized policy and dynamic path selection. However, controllers/orchestrators, edge devices, licensing, and integrations add operational dependencies.

### 4.4. Cloud Transit Services

Cloud providers offer transit gateways, virtual WANs, cloud routers, or hub networking services. These connect multiple VPCs/VNets, VPNs, and dedicated links through a centralized routing domain.

Advantages include fewer point-to-point connections and centralized route control. Trade-offs include quota limits, attachment/data processing charges, a shared failure domain, and the risk of becoming a choke point.

### 4.5. High-Level Comparison

| Criterion | VPN | Dedicated connection | SD-WAN | Cloud transit hub |
| --- | --- | --- | --- | --- |
| Provisioning | Fast | Slower | Depends on overlay/edge | Relatively fast in cloud |
| Latency consistency | Internet-dependent | Usually more stable | Policy selects path | Depends on attachment/region |
| Throughput | Per tunnel/Internet | Can be high | Depends on underlay | Per quota/service limits |
| Encryption | IPsec | Not by default | Depends on overlay | Depends on service/path |
| Site scaling | Tunnels/routes grow | Requires circuits/sites | Policy-driven | Attachment-driven |
| Cost | Low to medium | Medium to high | Licenses/edge/transport | Attachment/data processing |
| Use case | Backup/low-medium traffic | High-volume/critical | Multi-site policy | Cloud hub-and-spoke |

## 5. Topologies: Hub-and-Spoke, Mesh, and Transit

### 5.1. Point-to-Point Mesh

In a full mesh, every network connects directly to every other network. With N sites, the number of connection pairs scales as N(N-1)/2. This can yield short paths but becomes hard to operate as sites grow.

Advantages:
- Direct paths.
- Can optimize latency per pair.
- No central hub required for every flow.

Limitations:
- Tunnel/circuit and route counts grow rapidly.
- Segmentation is difficult to manage.
- Network changes must be synchronized in many places.
- Troubleshooting and ownership become complex.

### 5.2. Hub-and-Spoke

Spokes connect to one or more hubs. The hub performs transit routing, inspection, logging, or hosts shared services.

~~~mermaid
flowchart TB
    DC["On-prem data center"] --> HUB["Transit hub / firewall"]
    A["Cloud A production VPC"] --> HUB
    B["Cloud A staging VPC"] --> HUB
    C["Cloud B workload network"] --> HUB
    HUB --> SHARED["DNS / identity / monitoring"]
    HUB --> PARTNER["Partner private network"]
~~~

Advantages:
- Centralized routing and security inspection.
- Fewer point-to-point connections.
- Easier to apply shared DNS/egress.
- Connectivity can be managed per spoke attachment.

Risks:
- The hub becomes a bottleneck or shared failure domain.
- East-west traffic may hairpin through the hub, adding latency/cost.
- Route tables and propagation become complex.
- A single policy error can impact many spokes.

Multiple hubs can be deployed by region, environment, or trust domain. Avoid letting production and sandbox automatically route to each other simply because they attach to the same transit network.

### 5.3. Domain-Based Transit and Segmentation

A design can separate:
- Production hub.
- Non-production hub.
- Shared services hub.
- Partner/external connectivity hub.
- Restricted data zone.

Inter-hub connectivity is opened only for approved flows. This narrows the blast radius and reduces lateral movement risk.

### 5.4. Hybrid Transit Across Multiple Clouds

Each cloud can connect to a colocation/transit provider or an organization-operated network hub. When doing so, determine:
- Who manages the underlay/circuits?
- Who advertises routes?
- Which route propagation between providers is permitted?
- Where do DNS resolvers reside?
- Where are egress inspection and data loss controls located?
- If one cloud/provider has an outage, can the remaining clouds stay connected?
- Is there dependence on a single control plane or single carrier?

Do not build a global flat network just so clouds can “see each other.” Publish specific service paths instead.

## 6. Routing Fundamentals

Routing determines which next hop receives a packet based on destination prefix, route table, policy, and metrics.

### 6.1. Static Routing

Static routes are configured manually or via IaC. They are easy to understand for small topologies and stable prefixes, but require manual updates when networks change and do not adapt well to link failures without health automation.

### 6.2. Dynamic Routing and BGP

BGP exchanges routes between autonomous systems or routing domains. In hybrid cloud, BGP is commonly used to advertise prefixes between customer networks and cloud routers/VPNs/dedicated gateways.

Key concepts to understand:
- Prefix: the advertised network.
- AS number: autonomous system identifier.
- Neighbor/peer: routers exchanging BGP.
- Local preference: outbound path selection within an AS.
- AS path: sequence of ASes a route has traversed.
- MED: hint for preference across entry points; semantics depend on policy.
- Communities: metadata used to apply route policies.
- Prefix filters: limits on accepted/advertised routes.

Do not simply enable BGP and accept every route. Implement prefix allowlists, max-prefix limits, community policies, and route change reviews.

### 6.3. Route Propagation and Isolation

A transit hub can automatically propagate routes from one attachment to another. Without limits, staging may learn routes to production or a partner network may see unrelated internal prefixes.

Design practices:
- Separate route tables per trust domain.
- Explicit association/propagation.
- Prefix allowlists/denylists.
- Controlled summarization.
- Default routes only via appropriate inspection/egress paths.
- Do not advertise management networks to spokes that do not need them.
- Audit all route table and BGP changes.

### 6.4. Asymmetric Routing

Asymmetric routing occurs when the forward and return paths differ. Stateful firewalls/NATs may drop packets if the return path bypasses the same stateful device or lacks proper session synchronization.

For example, outbound traffic goes through firewall hub A while return traffic comes back via hub B. TCP sessions can fail even though routes exist in both directions. You should:
- Identify path symmetry requirements.
- Verify bidirectional route tables.
- Consider firewall insertion/service chaining.
- Check NAT state and session behavior.
- Test failover when one path goes down.

### 6.5. MTU, MSS, and Fragmentation

Encapsulation from IPsec/VXLAN/SD-WAN reduces usable payload size relative to underlay MTU. Large packets may be fragmented or dropped if path MTU discovery is blocked. A common symptom is that TCP connections open successfully, but sending large payloads hangs.

You should:
- Determine end-to-end MTU.
- Adjust TCP MSS where appropriate.
- Permit ICMP required for PMTUD per policy.
- Test packet sizes/throughput bidirectionally.
- Account for overhead from multiple tunnel layers.

## 7. DNS in Hybrid and Multi-Cloud Architectures

DNS is a critical control plane for connectivity. Applications typically call hostnames; DNS maps hostnames to addresses and service records/metadata. Private DNS must be designed across environments rather than creating duplicate zones without ownership.

### 7.1. Public DNS and Private DNS

- Public DNS serves names resolved from the Internet.
- Private DNS serves internal names within associated networks/domains.
- Split-horizon DNS returns different answers depending on resolver/source context.
- Conditional forwarding sends queries for a namespace to a designated resolver.
- Delegation assigns management authority for a zone/subdomain to another name server.

Do not publish private endpoints or internal hostnames in public DNS without explicit intent and a security review.

### 7.2. Namespaces and Zone Ownership

You can divide namespaces into:
- Public domain, e.g., example.com.
- Internal namespace, e.g., corp.example.internal.
- Environment subdomain, e.g., prod.corp.example.internal.
- Service discovery zone, e.g., svc.cluster.local (cluster-scoped).
- Cloud private zones per region/account if needed.

Decide the owner for each zone, who can create records, naming conventions, TTLs, lifecycle, and record conflict handling. Avoid having multiple resolvers authoritative for the same namespace without clear delegation.

### 7.3. Resolver Architecture

~~~mermaid
flowchart TB
    ONP["On-prem client"] --> OR["Corporate DNS resolver"]
    OR -->|Conditional forward| CR["Cloud DNS resolver"]
    CR --> PZ["Cloud private zone"]
    CR -->|Forward corp zone| OR
    W["Cloud workload"] --> WR["VPC/VNet resolver"]
    WR --> PZ
    WR -->|Forward legacy zone| OR
~~~

The diagram illustrates bidirectional flows that can be used, but configuration must prevent forwarding loops. If the corporate resolver forwards the entire internal zone to the cloud while the cloud resolver forwards the same zone back to corporate, queries can loop until timeout.

### 7.4. Conditional Forwarding

Examples:
- Queries for corp.example.com from cloud are forwarded to corporate DNS.
- Queries for cloud.internal.example.com from on-prem are forwarded to the cloud resolver.
- Queries for public domains use a managed recursive resolver.
- Queries for service namespaces are handled by cluster/service resolvers.

Specify exact zone suffixes, redundant forwarding targets, timeouts, retries, and recursion policies. Do not forward the root zone or overly broad domains unless necessary.

### 7.5. Private DNS Visibility

Private zones are usually visible only within associated/linked VPCs/VNets or resolver contexts. Multi-account/multi-region setups require association and authorization processes. A private DNS record may resolve from one environment but not another if a zone link or forwarding rule is missing.

### 7.6. DNS Caching and TTL

Low TTLs help record changes take effect sooner, but do not guarantee every client updates immediately. Resolvers, OSes, JVMs, browsers, connection pools, and service meshes may cache with their own semantics.

Consider:
- Authoritative TTL.
- Recursive resolver caches.
- Negative caching.
- JVM/OS DNS caches.
- Long-lived connections.
- Application endpoint caches.
- Health checks and failover propagation.

Do not assume a 30-second TTL means all traffic shifts within 30 seconds.

## 8. DNS Failover and Service Discovery

### 8.1. DNS-Based Failover

DNS health checks can swap records or return healthy endpoints. This works for certain public/private endpoints if clients honor TTLs and the DNS architecture supports it.

Limitations:
- Caches may retain old IPs.
- Resolver health checks do not always reflect business health.
- Existing client connections do not automatically move.
- DNS updates and data consistency are two separate problems.
- Private zones/conditional forwarders may not stay synchronized with public failover.

### 8.2. Service Discovery

In cloud-native environments, service discovery can use:
- Kubernetes Service DNS.
- Cloud service registries.
- Internal load balancers.
- Service mesh control planes.
- Application config/service catalogs.

Do not overuse DNS as a substitute for health-aware load balancing at the application layer. DNS is generally suited for discovery/endpoint resolution; health checks and traffic steering may require LBs or a service mesh.

### 8.3. Split-Brain and Stale Records

In DR, if both primary and secondary accept writes because DNS updated inconsistently, the system can enter split-brain. DNS is not a fencing mechanism. Leadership/quorum/fencing or read-only mode on the old site is required before opening a new writer.

## 9. Segmentation and Zero Trust Across Environments

Broad network connectivity increases blast radius. Segmentation controls which workloads can talk to which workloads; Zero Trust adds identity and policy verification for every access.

### 9.1. Segmentation Layers

- Physical/underlay boundaries.
- VPC/VNet/subnets.
- Route tables/VRFs.
- Firewalls/security groups/network ACLs.
- Kubernetes network policies.
- Workload identity and service-to-service authorization.
- Application/API policies.

Do not treat a private subnet as sufficient security. Private only means not directly routable from the Internet by topology; workloads inside still need identity, least privilege, and monitoring.

### 9.2. Environment Isolation

Production, staging, and development should have clear routing boundaries. If staging needs access to production data, use masked/approved datasets or policy-governed service interfaces; do not open full routes just for debugging.

### 9.3. Egress Control

Choose controlled egress points via firewalls/proxies/NAT gateways. You should have:
- Destination/domain/IP allowlists per workload.
- TLS inspection only when permitted by policy/law.
- DNS filtering/resolution policies.
- Logging and data loss monitoring.
- Quotas and bandwidth controls.
- Egress cost monitoring.

Centralized egress can improve visibility but creates bottlenecks and cost. Distributed regional egress with consistent policies can be used instead.

## 10. High Availability and Connectivity Redundancy

An HA architecture requires more than two tunnels terminating on a single router, carrier, or facility. Redundancy is only valuable when failure domains are sufficiently independent.

### 10.1. Redundancy Layers

- Two VPN tunnels to two distinct endpoints/gateways.
- Two circuits across diverse carriers or physical paths.
- Two edge routers/sites.
- Cloud gateway attachments across multiple AZs/regions per service design.
- Resolver redundancy.
- Multiple DNS forwarding targets.
- Redundant firewall/inspection paths.
- Independent management/control-plane access.

Verify how providers actually separate endpoints/failure domains. Two logical connections may still share a physical facility or carrier.

### 10.2. Failover Behavior

Mechanisms include:
- BGP route withdrawal on link down.
- Health checks and route policies.
- SD-WAN application-aware path selection.
- DNS failover for appropriate endpoints.
- Application retries/connection re-establishment.
- Traffic managers/global load balancing.

Do not use BGP route availability as the sole proxy for application health. A link may be up while packet loss/latency spikes or the destination service has failed.

### 10.3. Failover Capacity

If the primary link is 10 Gbps and the backup link is 1 Gbps, failover can congest all workloads. Calculate peak critical traffic, control traffic, replication, backup, and recovery workloads. Define which traffic classes must be preserved and which can be rate-limited or load-shed.

### 10.4. Failback

After the primary path recovers:
- Verify stability for a sufficient window.
- Check route preferences/metrics.
- Prevent route oscillation.
- Shift traffic in a controlled manner.
- Monitor session resets and packet loss.
- Check DNS/connection caches.
- Verify data replication backlogs.
- Keep a rollback option if the primary path remains unstable.

## 11. Connection Security and Trust Management

Private routing does not replace encryption, authentication, and authorization.

### 11.1. Encryption in Transit

Use TLS for application protocols; use IPsec for network tunnels where appropriate. Dedicated private circuits may still need encryption. Manage certificate/key lifecycles, rotation, revocation, trust stores, and clock synchronization.

### 11.2. Network Identity and Workload Identity

Do not identify sources solely by IP. IPs can change due to autoscaling, NAT, or migration. Combine:
- Workload identities/certificates.
- Mutual TLS where appropriate.
- IAM/service accounts.
- Network source/destination constraints.
- Application authorization.
- Short-lived credentials and rotation.

### 11.3. Route and Control-Plane Security

Protect BGP sessions, router management, cloud network APIs, DNS zone writes, and transit attachments. Use RBAC, MFA, auditing, and approvals. A route leak can expose wide areas even when application security groups remain unchanged.

### 11.4. DNS Security

- Restrict who can modify zones/records.
- Audit dynamic DNS updates.
- Use managed resolvers.
- Control recursion and forwarding targets.
- Protect zone transfers/delegations.
- Use DNSSEC for public zones where appropriate.
- Monitor anomalous queries and DNS tunneling.
- Avoid embedding sensitive data in hostnames/records.

## 12. Multi-Cloud Routing and Service Placement

Different providers have different VPC/VNet concepts, routing, private endpoints, and transit models. Do not assume services are completely equivalent or share identical semantics.

### 12.1. Cloud-to-Cloud Patterns

- Site-to-site VPN between cloud network endpoints.
- Dedicated interconnects via carrier/colocation providers.
- Organization-operated hub/transit networks.
- SD-WAN overlays.
- Application/API integration via private endpoints or gateways.
- Replication pipelines via managed data services.

Selection depends on traffic, latency, volume, security, provider support, regions, and cost.

### 12.2. Place Workloads Close to Dependencies

A service that reads a database frequently should be placed near that database if latency and data residency permit. Cross-cloud synchronous calls on the critical path can increase latency and reduce availability by depending on two providers simultaneously.

Cross-cloud dependencies can be reduced via:
- Event-driven integration.
- Data replication with freshness contracts.
- Local caches/materialized views.
- Async command/response.
- Scheduled batch bulk data transfers.
- API boundaries with timeouts/retries/circuit breakers.

Do not replicate sensitive data to another provider just to reduce latency without evaluating residency, encryption, access, and retention.

### 12.3. Service Placement Decision Matrix

| Criterion | Questions |
| --- | --- |
| Latency | Where are users and dependencies? Is the critical path cross-cloud? |
| Data gravity | Where do large datasets live, and how much needs to move? |
| Residency | Are there country/region/provider restrictions? |
| Availability | Is there a single provider/network dependency? |
| Egress | What are the data transfer and API request costs? |
| Security | How are identity/keys/policies managed across providers? |
| Operations | Who is on-call, who debugs routing/DNS, and who runs incident command? |
| Portability | Is the workload genuinely portable or tied to managed services? |

## 13. Observability for Networking and DNS

A hybrid/multi-cloud design requires visibility across boundaries. Logs on only one side are insufficient to investigate packets dropped in transit.

### 13.1. Telemetry to Collect

| Layer | Telemetry |
| --- | --- |
| Connectivity | Tunnel state, circuit status, BGP neighbors, route counts |
| Routing | Route changes, prefixes, next hops, route propagation |
| Network flow | Source/destination, port/protocol, bytes, accept/reject |
| Firewall | Rule hits, denies, session counts, threat alerts |
| DNS | Queries, response codes, latency, forwarding targets, cache |
| Application | Connect timeouts, TLS errors, request latency, retries |
| Synthetic | DNS lookup, TCP connect, TLS handshake, business probes |
| Capacity | Throughput, packet loss, jitter, interface utilization |

Protect logs because IP addresses, hostnames, and flow patterns can reveal internal topology.

### 13.2. Synthetic End-to-End Probes

A useful probe should check in order:
1. Resolve the hostname from the proper network context.
2. Verify the record/TTL/target IP.
3. TCP connect to the required port.
4. TLS handshake/certificate validation.
5. Authentication with a test identity.
6. Call a health endpoint or safe transaction.
7. Record latency and the failure stage.

A probe running from an unrepresentative subnet cannot prove every network path works. Deploy probes in on-prem, Cloud A, Cloud B, and all required zones.

### 13.3. Connectivity SLOs

You can define:
- End-to-end private path availability.
- DNS resolution success rate.
- p95/p99 DNS latency.
- Packet loss/jitter/RTT.
- Tunnel/BGP recovery time.
- Failover time.
- Application transaction success.
- Route/DNS change error budget.

Network SLOs must tie to service outcomes. A tunnel at 100% uptime while the API is unreachable is still a failure for users.

## 14. Layered Troubleshooting

When a service cannot connect, investigating in order avoids random route/firewall changes.

### 14.1. DNS

- Query from the right host/resolver.
- Check search suffixes and record types.
- Inspect authoritative/recursive answers.
- Check conditional forwarding and zone links.
- Check negative caches/stale caches.
- Verify the returned IP belongs to the right environment.

### 14.2. Routing

- Verify source/destination CIDRs.
- Inspect route tables and longest-prefix match.
- Check BGP neighbors and advertised/received prefixes.
- Inspect route filters/propagation and next hops.
- Verify bidirectional routes/asymmetric paths.
- Check NAT mappings if present.

### 14.3. Transport and Policy

- TCP connect and port reachability.
- Firewalls/security groups/NACLs/host firewalls.
- MTU/MSS and fragmentation.
- Packet loss, retransmissions, jitter.
- TLS certificates, SNI, ciphers, and trust stores.
- Proxies, service meshes, and egress policies.

### 14.4. Application and Identity

- Authentication/authorization.
- Token audience/issuer/expiry.
- Service identity and certificate rotation.
- Timeouts/retries/circuit breakers.
- Application logs and dependency health.
- Data residency/tenant policies.

Ping failing does not always prove a service is unreachable; ICMP may be blocked while TCP works. Conversely, ping succeeding does not prove TLS/application requests succeed.

## 15. Change Management and Operations

Network/DNS changes carry a large blast radius, so clear change control and rollback are required.

### 15.1. Change Record

Every change should include:
- Change ID and business rationale.
- Source/destination flows.
- Affected CIDRs, routes, BGP policies, DNS zones/records.
- Security approval and data classification.
- Owners of both ends of the connection.
- Pre/post validation.
- Deployment window.
- Rollback configuration.
- Monitoring/alerts.
- Dependencies and affected environments.

### 15.2. Routing Changes

Before changing routes:
- Review the route table diff.
- Identify new/withdrawn prefixes.
- Check route summarization.
- Check maximum prefixes and policies.
- Use a canary/small route target if supported.
- Monitor flow logs and BGP stability.
- Prepare the revert.

A misadvertised route can cause multiple networks to blackhole traffic or create a route leak. Roll out per domain with bounded blast radius.

### 15.3. DNS Changes

Before changing records:
- Identify the authoritative owner.
- Check TTL and caching behavior.
- Lower TTL ahead of cutover if needed and with enough lead time.
- Confirm certificates/SNI match the new hostname.
- Test resolvers across environments.
- Prepare rollback records.
- Monitor query errors and synthetic probes.

### 15.4. Ownership and Support Model

Clarify who owns:
- Underlay/carrier circuits.
- VPN/SD-WAN edge.
- Cloud transit gateways.
- Route policies/BGP.
- DNS zones/resolvers.
- Firewalls/inspection.
- Workload endpoints and certificates.
- Incident command and provider escalation.

If a route crosses three teams and two providers, the runbook must contain specific contact/escalation chains, not just “network team.”

## 16. Case Study: Connecting On-Premises, Cloud A, and Cloud B

### 16.1. Context

An enterprise runs ERP and corporate DNS in a data center. Booking API and managed PostgreSQL run on Cloud A. Analytics and reporting run on Cloud B. Booking needs to read some ERP data; analytics receives events and batch exports from Cloud A.

Assumed requirements:
- Booking-to-ERP has a p95 RTT target of 40 ms under normal conditions.
- Critical transactions require redundant connectivity paths.
- Analytics transfers can run asynchronously.
- Production and staging must be isolated.
- Internal DNS must resolve from all three environments.
- Restricted data must not leave approved regions.

### 16.2. Proposed Topology

~~~mermaid
flowchart TB
    subgraph ONP["On-premises"]
      ERP["ERP services"]
      DNS["Corporate DNS"]
      EDGE["Redundant edge routers"]
      ERP --> EDGE
      DNS --> EDGE
    end
    subgraph A["Cloud A"]
      HUBA["Transit hub A"]
      APP["Booking API"]
      DB[("Managed PostgreSQL")]
      APP --> DB
      APP --> HUBA
    end
    subgraph B["Cloud B"]
      HUBB["Transit hub B"]
      ANALYTICS["Analytics workers"]
      LAKE[("Data lake")]
      ANALYTICS --> LAKE
      ANALYTICS --> HUBB
    end
    EDGE <-->|"Dedicated primary + IPsec backup"| HUBA
    EDGE <-->|"IPsec / private transit"| HUBB
    HUBA <-->|"Controlled inter-cloud routes"| HUBB
    DNS <-->|"Conditional DNS forwarding"| HUBA
~~~

The diagram illustrates one topology. Real-world configuration must analyze whether Cloud A and Cloud B should connect directly or via the data center/transit provider; avoid hairpinning all analytics traffic through Cloud A if an appropriate private interconnect is available.

### 16.3. DNS

- Corporate DNS is authoritative for erp.corp.example.com.
- Cloud A resolver forwards corp.example.com to corporate DNS over redundant paths.
- Corporate DNS conditionally forwards cloud.internal.example.com to the Cloud A resolver.
- Cloud B has its own resolver and forwards only required namespaces.
- Private zones are linked to the right VPCs/VNets.
- Synthetic probes test from on-prem, Cloud A, and Cloud B.
- Rules prevent forwarding loops and enable query logging.

### 16.4. Routing and Security

- IPAM confirms CIDRs do not overlap.
- Dedicated connection is primary for the booking critical path; IPsec is backup.
- BGP prefix filters advertise only approved networks.
- Production route tables are separated from staging.
- The ERP service accepts sources only from approved booking subnets/identity paths.
- Cloud B receives only required data exports via approved endpoints/service interfaces.
- TLS protects application traffic even over private connections.
- Firewall logs and flow logs are sent to the monitoring account.

### 16.5. Resilience and Operations

Dedicated link loss drill:
- BGP/health policies switch to VPN.
- Measure RTT, throughput, and packet loss.
- Verify booking transactions remain within SLO or enter degraded mode.
- Analytics batches are throttled if the backup link lacks sufficient bandwidth.
- When the primary link recovers, shift paths in a controlled manner.
- Verify DNS and long-lived connections do not retain stale endpoints.
- Record failover/failback times and cost.

### 16.6. Decisions to Record in the ADR

The ADR should explain:
- Why dedicated primary and VPN backup were chosen.
- Why Cloud B does not route all production CIDRs.
- DNS namespaces and zone owners.
- Prefix allowlists and route propagation.
- Permitted data flows between providers.
- Failover capacity and SLOs.
- Connectivity/egress costs.
- Residual risks and operational owners.

## 17. Anti-Patterns and Common Mistakes

| Anti-pattern | Consequence | Mitigation |
| --- | --- | --- |
| Flat network connecting all clouds | Broad blast radius/lateral movement | Segment by trust domain and publish flows |
| Unmanaged IPAM | CIDR overlaps, NAT workarounds | Central address registry and allocation policy |
| Full mesh without a scaling plan | Tunnels/routes grow rapidly | Transit hub or overlay policies |
| Single hub without redundancy | Shared failure domain | Multi-hub/region and diverse paths |
| BGP accepting all prefixes | Route leaks/blackholes | Prefix filtering, max-prefix, communities |
| Asymmetric bidirectional routes | Stateful firewall/NAT drops | Path symmetry design and packet testing |
| Testing only with ping | TLS/apps can still fail | End-to-end synthetic probes |
| Circular namespace DNS forwarding | Query timeouts | Explicit suffix ownership/forwarding graph |
| Assuming TTL dictates failover time | Clients keep stale caches/connections | Measure resolver/runtime/application caches |
| Using DNS for writer fencing | Split-brain | Dedicated quorum/lease/fencing |
| Unencrypted dedicated circuits | Confidentiality not guaranteed | TLS/IPsec per data classification |
| Shared transit open to all environments | Staging reaches production | Separate route domains and explicit policies |
| Under-sized failover link | Critical traffic congested | Capacity testing and traffic class priorities |
| No owners on both ends | Prolonged incidents | RACI, runbooks, and escalation |

## 18. Practice Exercise

An enterprise has two data centers, Cloud A with three production VPCs, Cloud B with two analytics VPCs, and 20 branch offices. Systems use various RFC1918 ranges; two VPCs have overlapping CIDRs. Corporate DNS serves internal domains, and each cloud also has its own private zones. The Booking API on Cloud A needs to call the on-prem ERP; analytics only needs batch data ingestion. The enterprise wants two redundant connectivity paths and to keep production isolated from staging.

Complete the following:

1. Collect a flow matrix including source/destination/protocol/port/data class/owner/traffic.
2. Design an IPAM plan and a solution for the two overlapping VPC CIDRs; state trade-offs of re-addressing, NAT, or application proxies.
3. Compare VPN, dedicated connectivity, and SD-WAN for the 20 branches and two data centers.
4. Draw a hub-and-spoke or multi-hub topology; identify failure domains of carriers, edge routers, cloud gateways, and regions.
5. Design BGP prefix filters, route summarization, route propagation, and isolation between production/staging.
6. Explain how to prevent asymmetric routing when traffic traverses firewalls/NATs.
7. Design DNS namespaces, private zone ownership, and bidirectional conditional forwarding without loops.
8. Define TTL/cache/failover behavior for private endpoints and public services.
9. Design segmentation and egress controls by workload identity/data classification.
10. Calculate capacity needed on the backup link while keeping critical booking flows and control traffic operational.
11. Build synthetic probes checking DNS, TCP, TLS, auth, and business endpoints from every environment.
12. Write runbooks for link loss, route leaks, DNS outages, CIDR overlaps, and failback.
13. Define SLOs and dashboards for RTT, packet loss, DNS success, BGP stability, failover time, and transaction success.
14. Write an ADR covering topology, routing ownership, DNS authority, security, and connectivity costs.

**Self-assessment hint:** A strong solution inventories all flows, eliminates IP overlaps or defines safe transition measures, establishes a clear DNS authority/forwarding graph, enforces bidirectional segmented routing, validates independent redundancy, and uses end-to-end probes to prove applications can actually use the connectivity paths.

## 19. Pre-Production Checklist

- [ ] Business flows, owners, criticality, and data classification are inventoried.
- [ ] Latency, throughput, packet rate, availability, and recovery requirements are quantified.
- [ ] IPAM covers on-prem, cloud, Kubernetes, partners, and future allocations.
- [ ] CIDR overlaps are eliminated or have documented NAT/proxy designs.
- [ ] VPN/dedicated/SD-WAN choices have cost, encryption, and failure analyses.
- [ ] Transit topology has clear route domains and attachment ownership.
- [ ] BGP/static routes have prefix filters, policies, and auditing.
- [ ] Route propagation does not open unintended paths between environments.
- [ ] Asymmetric routing, NAT state, and MTU/MSS have been tested.
- [ ] DNS zones/resolvers/conditional forwarders have owners and no loops.
- [ ] Private DNS visibility and resolver authorization are verified.
- [ ] TTL, negative caching, runtime caches, and long-lived connections are accounted for.
- [ ] TLS, certificates, workload identities, and access policies are secured.
- [ ] Firewalls/SGs/NACLs/NetworkPolicies open only required flows.
- [ ] Redundant links/sites/edges/providers have appropriately independent failure domains.
- [ ] Failover capacity satisfies critical traffic and recovery workloads.
- [ ] DNS/routing failover and failback are rehearsed.
- [ ] Flow logs, resolver logs, BGP/tunnel telemetry, and synthetic probes have owners.
- [ ] Runbooks, RACI, escalation, and change rollbacks are verified.
- [ ] Data residency, egress costs, connectivity costs, and operational overhead are reviewed.

## 20. Well-Architected Assessment

| Pillar | Questions when reviewing hybrid/multi-cloud connectivity |
| --- | --- |
| **Operational Excellence** | Can IPAM, route/DNS ownership, change processes, telemetry, runbooks, and escalation be operated across teams/providers? |
| **Security** | Is the network segmented by trust domain; do private paths still use TLS/identity; do route/DNS changes have audit and least privilege? |
| **Reliability** | Are there diverse connectivity paths, redundant resolvers, failover/failback, capacity, and end-to-end recovery tests? |
| **Performance Efficiency** | Do placement, routing, DNS caching, and path selection meet latency/throughput without unnecessary hairpinning? |
| **Cost Optimization** | Are VPN, dedicated circuit, transit attachment, egress, NAT, and inspection costs attributed to workload/flow owners? |
| **Sustainability** | Are redundant data transfers, route hairpinning, and cross-region processing minimized while preserving resilience and residency? |

**Conclusion:** Hybrid and multi-cloud connectivity is a system spanning IP planning, underlay/overlay, routing, DNS, segmentation, identity, failover, and operations. Good design starts from business flows and trust boundaries; uses IPAM to prevent overlaps; selects VPN, dedicated connectivity, SD-WAN, and transit based on traffic/SLOs; controls route propagation and DNS forwarding; and tests forward paths, return paths, caches, and capacity during failover. An active tunnel or a correct DNS record alone does not prove an application works. Use end-to-end synthetic probes, change audits, and recovery drills to keep connectivity secure, reliable, scalable, and operable in the Well-Architected spirit.
