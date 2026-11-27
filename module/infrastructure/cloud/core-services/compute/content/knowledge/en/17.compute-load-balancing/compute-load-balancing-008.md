# Zone-Based and Regional Load Balancing and the Impact of Network Flows

A compute service can run across multiple virtual machines or nodes in multiple availability zones, or even multiple regions. Load balancers distribute requests to backends to increase serving capacity, utilize resources efficiently, and keep the service running when an instance or infrastructure zone fails. However, placing backends across multiple zones/regions does not automatically yield high availability. Request paths, return paths, DNS, health checks, session state, database connections, and data transfer costs all affect the outcome.

Distinguish two scopes: **intra-region load balancing** typically distributes traffic across zones to improve fault tolerance and utilize capacity; **multi-region load balancing** steers users to a service cluster in another geographic location for latency, disaster recovery, or data residency requirements. This lesson covers those models, how network flows affect performance and cost, and methods for design and testing.

## 1. Role of Load Balancing in Compute Architectures

A load balancer receives connections or requests from clients and forwards them to an eligible backend according to configured algorithms and policies. A backend can be a VM, container, node, service endpoint, or a lower-tier load balancer.

Primary goals:

- **Distribute load:** Avoid piling requests onto one instance while others sit idle.
- **Increase availability:** Exclude unhealthy backends from the traffic-serving pool.
- **Scale horizontally:** Allow adding or removing backends as demand changes.
- **Reduce latency:** Pick backends closer to clients or with available capacity.
- **Isolate faults:** Limit blast radius when an instance, zone, or region fails.
- **Steer traffic:** Apply routing by protocol, hostname, path, weights, or geography.

A load balancer does not fix application bugs on its own, replace data replication, or guarantee every request is safe to retry. It can only direct traffic to backends deemed eligible by health checks and routing rules.

## 2. Distinguishing Zones and Regions

An **Availability Zone (AZ)** is a relatively independent infrastructure fault domain within a region, typically designed to reduce the chance that a localized outage affects all zones simultaneously. How providers implement and map zones can vary across accounts or services.

A **Region** is a geographic area containing one or more zones. Regions usually have significant geographic separation, independent backbone connectivity, and a broader failure domain than a zone.

| Attribute | Multi-Zone Within One Region | Multi-Region |
|---|---|---|
| Common goals | Zone fault tolerance, maintenance, capacity scaling | Disaster recovery, geographic latency reduction, residency compliance |
| Inter-backend latency | Typically lower than cross-region, yet still traverses the network | Usually higher and more variable |
| Data replication | Can use synchronous or asynchronous replication depending on the system | Usually requires cross-region replication design and consistency handling |
| Network cost | May incur inter-zone charges depending on service/provider | Usually incurs cross-region transfer and data egress fees |
| Failover | Can shift to another zone in the same region | Shifts traffic and may require data recovery in another region |
| Complexity | Moderate | Higher due to DNS/global routing, data consistency, and multi-region ops |

Do not treat two zones as two independent regions. If an incident affects an entire region, deploying across multiple zones within that same region may still be insufficient to keep the service online.

## 3. Load Balancing Tiers

Production architectures often include multiple tiers of load balancing. Each tier operates at a different scope with different information.

| Tier | Placement | Routing Decisions Based On |
|---|---|---|
| Global traffic management | In front of regions | Geography, latency, health, weights, failover |
| Regional load balancer | Within one region | Backend pool, zone, health, distribution algorithm |
| Internal/service load balancer | Between services in a private network | Service endpoints, ports, protocols, and health |
| Host/container proxy | Close to the workload | Connections, requests, retries, timeouts, or internal routing |

For example, a user resolves the DNS name of a global service. Global routing selects the Singapore region. The regional load balancer in that region picks a backend in zone A or B. A reverse proxy or service mesh may then route further to an internal service.

~~~mermaid
flowchart TD
    U[Users] --> G[Global DNS / Global Load Balancer]
    G --> R1[Regional Load Balancer - Region A]
    G --> R2[Regional Load Balancer - Region B]
    subgraph A[Region A]
      R1 --> A1[Backend Zone A]
      R1 --> A2[Backend Zone B]
    end
    subgraph B[Region B]
      R2 --> B1[Backend Zone A]
      R2 --> B2[Backend Zone B]
    end
~~~

Define which tier owns each decision. If global routing sends traffic to an unhealthy region while the regional load balancer still looks locally healthy, users can still hit errors. Health signals must accurately reflect service status at the scope each routing tier needs to observe.

## 4. Load Balancing at Layer 4 and Layer 7

### 4.1. Layer 4

An L4 load balancer distributes connections using transport-layer metadata such as IP, port, and TCP/UDP. It does not need to understand HTTP content.

Advantages:

- Suited for TCP/UDP and non-HTTP protocols.
- Can have lower overhead.
- Useful for long-lived connections or traffic requiring protocol preservation.
- Can forward at the connection level without parsing requests.

Limitations:

- Hard to route by hostname, URL path, or HTTP headers.
- Health checks usually focus on connectivity or endpoints; separate application checks are needed.
- A TCP connection typically stays bound to the chosen backend for the life of the connection.

### 4.2. Layer 7

An L7 load balancer understands application protocols such as HTTP/HTTPS and can route by host, path, headers, cookies, or request properties.

Examples:

- api.example.com to API backends.
- /images/* to the media service.
- /v2/* to the new API version.
- A small percentage of traffic to canary backends.

The advantage is rich routing policy plus optional TLS termination, WAF, or request-level health checks. In exchange, L7 must parse application protocols, which can add latency and requires managing certificates, headers, timeouts, and connection behavior.

### 4.3. Choosing the Right Layer

Use L4 when distributing TCP/UDP or preserving protocols end-to-end. Use L7 when you need content-based HTTP routing, TLS termination, or per-request policies. A system can combine an L7 public ingress with L4 internal services for other protocols.

## 5. Load Balancing Across Zones

A regional load balancer can distribute across backends in multiple zones. Two common perspectives exist:

- **Zone-aware / zone-local:** Prefers backends in the same zone or keeps traffic close to its point of entry.
- **Cross-zone:** Allows a load balancer node or traffic entry point to distribute to backends in other zones.

Naming and default behavior depend on the service. Some services offer a cross-zone toggle, while others distribute across zones automatically or create zonal endpoints.

### 5.1. Zone-Local Routing

In a zone-local model, traffic entering one zone is typically handled by backends in that same zone if they are healthy and have sufficient capacity.

Benefits:

- Reduces inter-zone traffic.
- Can lower latency and inter-zone data transfer fees.
- Keeps traffic close to co-located compute and data in the same zone.
- Reduces dependence on inter-zone networking when another zone has issues.

Risks:

- A zone with fewer backends or higher load can saturate while other zones have spare capacity.
- If zone-local backends are unhealthy, fallback to another zone is required.
- Zonal entry points may need separate health checks and failover.
- Must ensure remaining capacity is sufficient when a zone is taken out of service.

### 5.2. Cross-Zone Routing

Cross-zone allows traffic received in one zone to be forwarded to backends in another zone.

Benefits:

- Distributes load more evenly across the entire backend pool.
- Reduces the risk of one zone running short of backends while another has excess capacity.
- Helpful when backend counts or capacities are uneven across zones.
- Can improve service continuity when one zone degrades, given appropriate routing and health checks.

Trade-offs:

- Requests may traverse inter-zone links, increasing latency.
- Can incur inter-zone data transfer charges depending on provider and service.
- If a backend calls a database or cache in another zone, traffic may cross multiple inter-zone hops.
- Must evaluate failure modes when inter-zone networking degrades.

### 5.3. Comparing Zone-Local and Cross-Zone

| Criterion | Zone-Local | Cross-Zone |
|---|---|---|
| Path | Prefers backends in the same zone | Can reach healthy backends in any zone |
| Capacity balance | Can skew if zonal traffic is uneven | Usually easier to balance across the shared pool |
| Latency | Potentially lower when backends are in-zone | May increase due to inter-zone hops |
| Network cost | Potentially reduces inter-zone traffic | May incur inter-zone transfer fees |
| Impact of one zone failing | Must fail over to another zone or reject traffic | Can spread load to remaining zones if capacity suffices |
| Complexity | Requires zonal capacity and fallback management | Requires tracking inter-zone costs and paths |

Neither option is universally better. If zones receive uneven traffic or have heterogeneous backends, cross-zone can raise overall utilization. If workloads are latency-sensitive and data is partitioned by zone, zone-local may fit better. Measure against real traffic patterns.

## 6. Load Balancing Across Regions

Global load balancing steers users or connections to one of several regional endpoints. Common patterns include:

### 6.1. Geo-Based Routing

Selects a region based on the client's geographic location or country. Useful for serving users close to their region or meeting data residency rules.

Client IP addresses do not always reflect true user location, especially with VPNs, proxies, or mobile carrier networks. Understand geolocation accuracy and fallback policies.

### 6.2. Latency-Based Routing

Selects the region predicted to offer lower latency for the client. Results depend on DNS resolver placement, ISP routing, peering, and time of day. DNS-based latency routing may evaluate the location of the DNS resolver rather than the end device, so it does not always choose the optimal path for every user.

### 6.3. Weighted Routing

Distributes by weight, such as 90% of traffic to region A and 10% to region B. Used for canaries, migrations, or capacity testing. DNS weights do not guarantee exact request splits due to DNS caching, connection reuse, and client distribution.

### 6.4. Failover Routing

Normally uses a primary region; when health checks or service signals fail, shifts traffic to a standby region. Failover must explicitly define:

- What conditions trigger regional failover.
- Whether health checks verify an endpoint or business-level serving capability.
- Detection time and traffic shift time.
- DNS TTL and resolver/client caching behavior.
- Whether data in the target region is fresh enough to accept writes.
- How to prevent split-brain when the old region recovers.

### 6.5. Anycast and Global Networks

Some global services use Anycast or private backbone networks to land clients at a nearby point of presence. From there, traffic is forwarded to regions/backends per provider policy. Anycast improves network ingress paths, but does not solve data consistency, application health, or target region capacity on its own.

## 7. Active-Active and Active-Passive

### Active-Active

Multiple regions serve production traffic concurrently. Global routing distributes requests among them.

Advantages:
- Utilizes compute capacity across multiple regions.
- Serves users in multiple geographies with better latency.
- When one region fails, traffic can shift to remaining regions.

Challenges:
- Requires multi-region write handling and consistency design.
- Requires idempotency during retries or failovers.
- Must avoid duplicate job or transaction execution.
- Must synchronize configs, secrets, schemas, and app versions.
- Must provision spare capacity so surviving regions handle load when one region drops.

### Active-Passive

One primary region serves traffic; a standby region is kept warm, pilot-light, or cold depending on RTO targets.

Advantages:
- Easier control over primary data writes.
- Can lower costs when the standby region does not run at full capacity.
- Suits systems that do not yet support multi-region writes.

Challenges:
- Failover can take time to scale up, boot, and shift traffic.
- Must verify data replicas and replication lag.
- The standby region must be drilled regularly, not just configured on paper.

| Criterion | Active-Active | Active-Passive |
|---|---|---|
| Normal traffic | Multiple regions serve requests | Primary region serves requests |
| Standby capacity | Actively utilized | Can run at reduced level or off |
| Data complexity | Higher, may require conflict resolution | Usually simpler with a single primary writer |
| Cost | Typically higher with multiple active regions | Potentially lower, though DR still carries cost |
| Failover | Shift traffic share away from failed region | Promote standby region and shift traffic |
| Best fit | Global services with multi-region architecture | Systems needing DR without multi-region writes yet |

## 8. Request and Response Flow Across Multiple Tiers

To understand network impact, trace both the outbound and return paths. For example, a user API request may pass through:

1. DNS resolver looking up the global endpoint.
2. Client connecting to the edge/global entry point.
3. Global routing selecting a regional endpoint.
4. Regional load balancer picking a backend.
5. Backend calling a database, cache, or downstream service.
6. Backend returning the response over the established network path.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Global routing
    participant R as Regional LB
    participant A as App backend
    participant D as Database
    C->>G: DNS / connect to endpoint
    G->>R: Select healthy region
    R->>A: Select healthy backend
    A->>D: Query over private network
    D-->>A: Result
    A-->>C: Response over connection
~~~

Every hop adds latency, timeout exposure, and data transfer cost. If a request lands on a backend in zone A while the database sits in zone B, internal flows still cross zones even if the load balancer picked a backend near the client. Database, cache, and dependency topologies must therefore be evaluated together.

## 9. Impact of Network Flows on Latency

End-to-end latency is the sum of multiple components, not just VM processing time:

\[
T_{total} =
T_{DNS} + T_{connect} + T_{TLS} +
T_{LB} + T_{network} + T_{backend} +
T_{dependency} + T_{response}
\]

This formula is a conceptual model; some phases may overlap or be amortized by connection pooling. In production analysis, use traces/spans to measure each leg.

Factors that increase latency:

- Clients located far from the chosen region.
- Requests traversing multiple proxies, firewalls, or gateways.
- Cross-zone/cross-region hops.
- Repeated DNS lookups or TLS handshakes.
- Backends making multiple sequential dependency calls.
- Network congestion, retransmissions, or packet loss.
- Load balancer queuing or backend saturation.
- Lack of connection reuse.

Do not choose regions purely by geographic proximity. Internet routing, ISP peering, DNS resolver placement, and backbone conditions can give a geographically closer region higher real-world latency. Measure from representative user locations.

## 10. Impact of Network Flows on Cost

Network charges can arise at several points:

- Inter-zone data transfer.
- Inter-region data transfer.
- Internet egress from cloud to clients or external services.
- NAT gateway or firewall processing.
- Load balancer capacity/processed bytes or rule evaluations.
- Private connectivity and transit gateways.
- Cross-region data replication.
- Logging, backups, and telemetry shipped across the network.

Pricing models vary by provider, service, region, and traffic class. Never assume all inter-zone traffic is free or all traffic through load balancers is billed identically.

An estimation model:

\[
C_{network} =
\sum_i (Bytes_i \times Rate_i) +
C_{NAT} + C_{LB} + C_{transit}
\]

Where Rate_i is the unit price for each transfer path, taken from actual environment pricing tables and billing exports.

### 10.1. Example of Cross-Zone Impact

Suppose an application exchanges 2 TB of data daily between backends and dependent services. If most traffic crosses zones, transfer costs can become substantial depending on unit pricing and provider billing rules. Co-locating backends and data dependencies in the same zone or using zone-local routing can cut inter-zone bytes.

However, placing database replicas or caches in every zone alongside every backend can raise replication costs and operational complexity. Measure total network cost rather than optimizing one leg only to inflate traffic on another.

## 11. Asymmetric Routing and Stateful Firewalls

Asymmetric routing occurs when forward and return packets travel different network paths or appliances. This can break stateful firewalls or network appliances because a device sees only half of the session and cannot recognize connection state.

Example:
- A request from backend A passes through firewall X to the database.
- The response from the database returns through firewall Y.
- Firewall Y lacks session state and may drop the response.

Common causes:
- Different route tables or next hops across subnets.
- NAT placed in multiple locations.
- Complex multi-region peering or transit routing.
- ECMP or inconsistent route propagation.
- Failover altering the return path before firewall state syncs.

Mitigations:
- Diagram both the forward path and return path.
- Inspect route tables, NAT mappings, security groups, and firewall sessions.
- Enforce symmetric routing architectures wherever stateful inspection requires it.
- Verify source/destination IPs after NAT.
- Check MTU, fragmentation, and path MTU discovery if connections hang or large payloads fail.

Not every system requires symmetric paths. However, whenever stateful firewalls, NAT, or proxies are present, confirm explicitly which device holds session state.

## 12. SNAT, Port Exhaustion, and Outbound Connections

When many backends connect out to the Internet or an endpoint through NAT, source addresses may be translated using SNAT. A NAT gateway has a finite number of port mappings per IP address and deployment. Under high concurrent connections or high new-connection rates, port exhaustion or mapping shortages can occur.

Symptoms:

- Backends fail to open new outbound connections even though DNS works.
- Connection failures spike during scale-out or traffic surges.
- Timeouts cluster around outbound calls.
- NAT metrics report port allocation errors or high connection counts.
- Some destinations succeed while others time out.

Mitigations:

- Reuse connections via HTTP keep-alive and connection pools.
- Avoid opening a fresh connection for every request.
- Scale NAT capacity per service guidance, such as adding source IPs or allocating NAT per subnet/zone where appropriate.
- Bound concurrency and connection creation rates.
- Monitor port utilization, dropped connections, and NAT errors.
- Prefer private endpoints for cloud services where appropriate to avoid unnecessary Internet/NAT hops.

Adding NAT gateways or public IPs increases capacity but also changes cost and architecture. Allocate NAT per zone so a single NAT does not become a single point of failure or bottleneck.

## 13. Session Affinity and Application State

Some load balancers support session affinity (sticky sessions), attempting to route subsequent requests from the same client to the same backend.

Sticky sessions can help applications that store sessions in local memory, but introduce trade-offs:

- Traffic may distribute unevenly.
- Backend failures can lose sessions if state is not shared.
- Scale-in or deployments can force clients onto another backend.
- Session affinity does not replace durable state storage.

Stateless architectures are generally easier to balance across zones/regions. Storing sessions in a distributed cache or database lets any backend serve requests, though the cache/data tier also needs appropriate HA, latency, and replication.

In multi-region setups, regional session affinity can reduce round trips to a session store, but complicates failover. If the primary region goes down, sessions may need to be recreated or recovered from a replicated store.

## 14. Health Checks and Right-Scoped Failover

Health checks determine whether a backend or region is eligible to receive traffic. Overly shallow health checks report healthy when the app cannot process business logic; overly deep checks mark all backends unhealthy when a minor dependency fails.

Distinguish:

- **Liveness:** Is the process alive and not deadlocked to the point of needing a restart?
- **Readiness:** Can the instance accept new requests?
- **Dependency health:** Are databases, caches, or external services responsive?
- **Regional health:** Can the region serve critical business flows?

Health endpoints should evaluate only essential dependencies, enforce timeouts, and avoid heavy load. For global failover, use multi-location health checks or multiple signals to avoid false positives from a single failing prober location.

### 14.1. Failover with Hysteresis

If health fluctuates near a threshold, global routing can bounce traffic back and forth between regions (flapping). Use thresholds, consecutive failure counts, recovery windows, and cooldowns to avoid unnecessary switching.

Check detection times, DNS TTLs, resolver caching, and client connection reuse. DNS failover cannot immediately sever open connections or force every resolver to refresh simultaneously.

## 15. Data Consistency in Multi-Region Load Balancing

Load balancing only steers traffic. Data requires its own design.

Critical questions:

- Which region is the primary writer for each dataset?
- Is replication synchronous or asynchronous?
- What is the maximum acceptable replication lag?
- On failover, can un-replicated writes be lost?
- Can two regions accepting writes concurrently create conflicts?
- Are idempotency keys needed to prevent duplicate transactions on client retries?
- When the old region recovers, what is the rejoin and data reconciliation procedure?

With asynchronous replication, the target region may lack the latest transactions. RPO depends on replication lag at the moment of failure. With synchronous replication, write latency rises due to cross-region acknowledgement waits. Choose a model based on business requirements and geographic distance.

Never automatically shift write traffic to a standby region without clearly defining writer/leader ownership and split-brain prevention.

## 16. Multi-Zone and Multi-Region Architecture Example

Suppose an API serves users in Southeast Asia and a group of users in Europe. The service needs intra-region HA and DR if a region fails.

A reference architecture:

1. Global DNS or a global load balancer picks the region by latency/health.
2. Each region has a regional load balancer spreading backends across two or more zones.
3. Backends are stateless, storing sessions and business data in appropriate stateful services.
4. Databases replicate cross-region per defined RPO/RTO.
5. Egress to cloud services uses private endpoints where appropriate.
6. Regional health checks validate critical business endpoints.
7. When a zone fails, the regional LB shifts traffic to surviving zones.
8. When an entire region fails, global routing shifts traffic to the standby region per runbook.
9. After failover, verify data, queues, scheduled jobs, and write state before opening full traffic.

~~~mermaid
flowchart TB
    C[Clients] --> G[Global traffic manager]
    G -->|Latency / health| L1[Region Singapore LB]
    G -->|Failover / policy| L2[Region Europe LB]
    subgraph SG[Region Singapore]
      L1 --> SGA[App Zone A]
      L1 --> SGB[App Zone B]
      SGA --> SGD[(Regional data endpoint)]
      SGB --> SGD
    end
    subgraph EU[Region Europe]
      L2 --> EUA[App Zone A]
      L2 --> EUB[App Zone B]
      EUA --> EUD[(Regional data endpoint)]
      EUB --> EUD
    end
    SGD <-->|Replication| EUD
~~~

This diagram is conceptual only. Replication and write ownership must be designed for your specific database. Not every database supports active-active multi-region writes or automatic failover.

## 17. Cloud Platforms and Implementation Options

Providers offer functionally comparable services with different names, scopes, and billing models.

| Platform | Intra-Region/Zone Load Balancing | Cross-Region Coordination |
|---|---|---|
| AWS | Elastic Load Balancing with ALB/NLB/GWLB types and service-dependent cross-zone options | Route 53 routing policies, AWS Global Accelerator, and multi-region patterns |
| Azure | Azure Load Balancer, Application Gateway, and related services with SKU-dependent zone/region configs | Azure Traffic Manager, Azure Front Door, and global routing patterns |
| Google Cloud | Cloud Load Balancing with regional/global, external/internal types and service-specific backend scopes | Global external Application Load Balancer, Cloud DNS routing policies, and multi-region architectures |

Do not assume every product within one platform shares identical cross-zone behavior or pricing. Before deploying, check:

- Whether the load balancer is regional or global.
- Which zones/regions backends may reside in.
- Whether cross-zone is enabled by default or requires configuration.
- Where health checks originate and over which protocol.
- Whether source IP is preserved or requires PROXY protocol/forwarded headers.
- TLS termination and certificate scope.
- Costs for processed bytes, inter-zone transfer, inter-region transfer, and egress.
- Limits on connections, throughput, and backend count.

## 18. Testing and Failover Drills

Do not conclude a multi-zone/multi-region architecture works merely because backends exist. Test actual paths and failure scenarios.

A test plan might include:

1. Send steady load to all backends and verify distribution matches policy.
2. Stop one backend and verify health checks eject it.
3. Simulate losing a zone in a test environment and measure traffic shift time.
4. Check latency, error rates, and capacity in surviving zones.
5. Generate controlled inter-zone traffic to measure bytes and network fees.
6. Simulate placing a dependency in another zone and measure round-trip latency.
7. Test NAT/SNAT as outbound connection counts rise.
8. Test asymmetric routing across firewalls or network appliances.
9. Simulate an unavailable region and verify global failover.
10. Validate DNS caching, client retries, and existing open connections.
11. Verify data after failover, replication lag, and ability to resume writes.
12. Drill failback to the primary region and state reconciliation.

### 18.1. Metrics to Monitor

- Request counts and backend distribution by zone/region.
- Healthy/unhealthy host counts.
- Latency p50/p95/p99 by client location and backend zone.
- Error rates, timeouts, and retry rates.
- Cross-zone/cross-region bytes.
- NAT connection/port utilization and allocation errors.
- Load balancer active connections, processed bytes, and queues if applicable.
- Database replication lag, failover duration, and write errors.
- DNS response distribution and caching behavior.
- Capacity utilization after losing a zone or region.

## 19. Common Design Mistakes

**Deploying multi-zone without checking capacity when one zone fails.** Surviving zones can overload after failover. Verify N-1 capacity and scaling policies.

**Enabling cross-zone while ignoring cost and latency.** Traffic may cross inter-zone links more than expected. Measure inter-zone bytes and latency before deciding.

**Using zone-local without fallback.** If backends in one zone become unhealthy, traffic fails even while other zones have capacity. Define explicit fallback policies.

**Running multi-region with an unprotected single data writer.** Global routing may shift traffic while data in the target region is not ready to serve writes. Design replication, promotion, and RPO/RTO.

**Using DNS failover and assuming instant cutover.** Resolvers and clients cache records; open connections do not migrate automatically. Measure TTLs and actual client behavior.

**Health checks probing only a port.** An open port does not prove the app can execute business logic. Use proper readiness/health checks while avoiding overly deep checks.

**Ignoring the return path.** Stateful firewalls or NAT can drop responses under asymmetric routing. Verify both directions and session state.

**Not reusing outbound connections.** SNAT ports can exhaust when requests continually open fresh connections. Use keep-alive, connection pools, and monitor NAT.

**Sticky sessions skewing traffic unevenly.** Some backends overload while others sit idle. Prefer stateless designs or external session stores where appropriate.

**Failover without a failback plan.** Once the primary region recovers, data may diverge or traffic may snap back prematurely. Reconcile data, verify the writer, and shift traffic in a controlled manner.

## 20. Checklist for Zone/Region Load Balancing Design

- [ ] Defined the objective: latency, intra-zone HA, cross-region DR, or residency.
- [ ] Clearly distinguished zone and region scopes for every service.
- [ ] Selected L4/L7 matching protocol and routing needs.
- [ ] Distributed backends across zones with spare capacity.
- [ ] Decided between zone-local and cross-zone based on latency, capacity, and network cost.
- [ ] Configured fallback when a backend/zone becomes unhealthy.
- [ ] Global routing uses appropriate geo/latency/weighted/failover policies.
- [ ] Health checks reflect business serving capability and include hysteresis.
- [ ] Accounted for DNS TTLs, resolver caching, and client connection reuse.
- [ ] Verified forward paths and return paths across routes, NAT, and firewalls.
- [ ] Assessed SNAT port capacity and connection reuse.
- [ ] Sessions do not depend on a single backend if failover is required.
- [ ] Databases/queues have clear replication, writer policies, RPO, and RTO.
- [ ] Estimated inter-zone, inter-region, NAT, load balancer, and Internet egress costs.
- [ ] Dashboards exist per zone/region with alerts for skewed traffic distribution.
- [ ] Tested backend loss, zone loss, region loss, and failback.
- [ ] Runbook specifies owners, failover criteria, and failback criteria.

## 21. Conclusion

Zone-based load balancing distributes compute within a region and improves local fault tolerance; regional load balancing steers traffic across geographic regions to lower latency or recover when a region fails. Zone-local routing can curb inter-zone traffic but requires zonal capacity and fallback; cross-zone routing balances more flexibly but can increase latency and transfer fees. Multi-region routing also demands solutions for DNS, data replication, writer ownership, RPO/RTO, and failback.

To design effectively, trace both the request path and return path, account for network hops and costs, control NAT/SNAT and stateful firewalls, and measure latency from user locations. Health checks, spare capacity, and failover drills must reflect real serving ability. Load balancers deliver their full value only when compute, network, and data tiers are designed as one cohesive system.
