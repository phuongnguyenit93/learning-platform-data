# Optimizing Compute Placement, Data Locality, and Geographic Distance

## 1. Deployment Location Is a Performance Decision

A request can traverse many hops: the user's device, ISP network, CDN or edge, load balancer, application service, cache, database, and third-party services. Even if each individual component is fast, total duration can still be large if components are far apart or a request makes repeated data transfers.

**Placement** is the decision of where to put compute, data, and infrastructure components: edge locations, availability zones (AZs), regions, countries, data centers, or locations near on-premises systems. The goal is not merely to shrink geographic distance, but to reduce end-to-end latency while satisfying data correctness, availability, security, residency, cost, and operability.

In the **CLOUD_ARCHITECTURE** module, cloud application architecture is designed from business requirements through network, compute, data, and deployment models. Placement decisions must therefore rest on latency budgets and actual workloads, while weighing trade-offs across reliability, security, scalability, cost, and operations under Well-Architected thinking.

After this lesson, you will be able to:

- Analyze latency across each network hop and compute/data access.
- Choose regions, AZs, edge locations, and CDNs based on user distribution and business requirements.
- Apply data locality and data gravity to reduce cross-region data transfer.
- Select multi-AZ, multi-region, active-active, or active-passive strategies.
- Evaluate replication lag, consistency, cache locality, and write locality.
- Design edge processing for workloads requiring fast responses or processing near data sources.
- Balance performance against data residency, security, DR, and egress costs.
- Verify placement using latency telemetry, load tests, and failover exercises.

## 2. Measure Distance with a Latency Budget, Not Just a Map

### 2.1. End-to-End Latency

The time a user waits typically consists of multiple components:

\[
T_{\text{total}} =
T_{\text{client}} +
T_{\text{network}} +
T_{\text{queue}} +
T_{\text{compute}} +
T_{\text{data}} +
T_{\text{external}}
\]

Where:

- Client: DNS lookup, connection setup, TLS handshake, and on-device processing.
- Network: propagation, routing, packet loss, and retransmission.
- Queue: waiting at load balancers, workers, connection pools, or brokers.
- Compute: CPU, memory, serialization, application logic.
- Data: cache/database reads and writes, locks, replication, and storage I/O.
- External: time calling payment, identity, analytics, or third-party APIs.

Separate these components to see which placement change actually improves performance. If 80% of latency comes from database locks, moving the API to a region closer to users may help very little.

### 2.2. Latency Budget

Suppose BookingCloud sets a p95 target for GET catalog under 250 ms:

| Component | Illustrative budget |
|---|---:|
| DNS/connection/TLS and client overhead | 35 ms |
| Client to edge/origin and network routing | 55 ms |
| API gateway and application compute | 45 ms |
| Cache/database read | 65 ms |
| Serialization and response transfer | 25 ms |
| Variance reserve | 25 ms |
| **Total** | **250 ms** |

These numbers are target budgets, not fixed latencies for a region or provider. When a component exceeds its budget, the team must understand how that cascades into the SLO.

### 2.3. p50, p95, and p99

Geographic distance affects every request, while queueing, routing, and load create a long tail in the latency distribution. Measuring only averages can hide remote users or requests hitting cross-region hops.

- p50 shows the typical experience.
- p95 shows the noticeably slower group of requests.
- p99 surfaces tail latency, which is often sensitive to queues, retries, cross-region dependencies, and cold paths.

Segment metrics by user region, serving region, endpoint, workload class, and cache status. Avoid high-cardinality labels like individual user or request IDs.

## 3. Physical Distance and Types of Network Delay

### 3.1. Propagation Delay

Signals take time to travel across fiber cables, network routes, intermediate devices, and peering points. Longer paths generally have higher propagation delay, though real network paths are not straight lines on a map; routing, peering, congestion, and topology have major effects.

Do not estimate latency purely from great-circle distance. Two nearby regions may have very different routing; an edge PoP close to users may still have to reach back to a distant origin for dynamic data.

### 3.2. Connection Setup

A new request can spend significant time on DNS, TCP handshake, TLS handshake, and authentication. Connection reuse, HTTP/2 or HTTP/3, keep-alive, and connection pooling reduce this overhead, though you must manage pool limits, idle timeouts, and stale connections.

### 3.3. Network Path

Traffic may traverse:

- ISPs and the public Internet.
- CDN/edge points of presence (PoPs).
- Cloud backbones or inter-region links.
- NAT gateways, firewalls, proxies, and service mesh sidecars.
- Private endpoints, VPNs, transit gateways, or peering.

Each hop can introduce latency and failure modes. Placement reviews should trace the actual path, verifying DNS resolution, routing, TLS termination, and egress instead of looking only at region names.

## 4. Choosing Regions Based on User Distribution and Business Requirements

### 4.1. Deciding Factors

| Factor | Questions to answer |
|---|---|
| User geography | Where are the primary users located? Is load evenly distributed? |
| Latency objective | What p95/p99 must be achieved? Are there real-time interactions? |
| Data residency | Which data must be stored or processed within a specific country or region? |
| Service availability | Does the region offer all required services, SKUs, quotas, and features? |
| Resilience | Is there a suitable secondary region for DR or failover? |
| Dependencies | Where are payment, identity, on-premises, and partner endpoints located? |
| Cost | What are the compute, storage, cross-region transfer, egress, and support costs? |
| Operations | Can the operations team support the timezones, incidents, and compliance scope? |

Choosing the region closest to users is not automatically optimal if core data resides elsewhere, an external dependency only exposes endpoints in one area, or transferring data violates residency policies.

### 4.2. Geographically Distributed Workloads

BookingCloud has 75% of users in Vietnam, 15% in Singapore, and 10% in other markets. One option is placing primary application and data in a region serving the majority of customers while using a CDN for static assets. However, you must measure actual latency to candidate regions, verify provider service availability, and confirm data requirements.

If user distribution shifts seasonally or by campaign, do not rely on a short snapshot. Analyze by day, hour, campaign, and operation type.

### 4.3. Region Selection Matrix

| Criterion | Region A | Region B | Evaluation method |
|---|---|---|---|
| User p95 latency | 75 ms | 125 ms | Synthetic/user telemetry |
| Database latency | 8 ms | 2 ms | Data locality |
| Service/SKU coverage | Complete | Missing one service | Provider capability |
| Data residency | Compliant | Needs legal review | Data classification |
| DR pairing | Available | Available | Failover test |
| Monthly cost | Moderate | Higher | Full cost model |

Values are illustrative only. Final decisions must rest on verified measurements and policies, not assumptions from region names.

## 5. Availability Zones and Intra-Region Placement

### 5.1. When to Use Multi-AZ?

Multi-AZ spreads workloads across multiple independent failure domains within the same region. The goal is typically to reduce the risk of losing an AZ and raise availability without incurring the geographic latency of multi-region deployments.

Notes:

- Load balancers need health checks and must route requests only to healthy targets.
- Databases need tested replication and failover semantics.
- Caches, queues, and session state must have appropriate sharing or replication models.
- Cross-AZ network transfers can increase costs.
- Subnets, IPs, security policies, KMS, and endpoints must exist across the required AZs.

### 5.2. Synchronous Replication and Latency

If a database writes synchronously to a replica in another AZ, commit latency can increase by the network round trip and storage acknowledgement. In return, failover can reduce data loss depending on the mechanism.

Not every system needs synchronous replication for all data. You can separate tiers:

- Critical transactions requiring durable acknowledgement and strict consistency.
- Read replicas that can update asynchronously.
- Caches or search indexes that tolerate eventual consistency.
- Analytics/event projections that can tolerate greater lag.

Choose based on business invariants, not benchmarks alone.

### 5.3. AZ Affinity and Anti-Affinity

Schedulers can pack replicas close together for locality or deliberately spread them to reduce correlated failures. For stateless services, zone/host anti-affinity is usually desirable; for data-intensive workloads, weigh locality against replica placement.

Never place all replicas of a service in a single AZ just because nodes are cheaper or container images are already warm there.

## 6. Data Locality and Data Gravity

### 6.1. Data Locality

Data locality means placing compute close to the data it reads and writes frequently. When applications and databases sit far apart, each query or transaction may incur one or more network round trips. A workflow with multiple sequential queries amplifies latency.

Example of an application in Region A calling a database in Region B:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant A as App Region A
    participant B as Database Region B
    U->>A: API request
    A->>B: Query 1
    B-->>A: Result 1
    A->>B: Query 2
    B-->>A: Result 2
    A->>B: Query 3
    B-->>A: Result 3
    A-->>U: Response
    Note over A,B: Each round trip adds network latency
~~~

If each DB round trip adds 40 ms and a request runs three sequential queries, networking alone can add roughly 120 ms before even counting query execution. Batching, joins, redesigning data access, or colocating service and data can be far more effective than moving the entire database.

### 6.2. Data Gravity

When datasets grow large and many systems depend on them, moving compute to the data is usually easier than moving data to compute. This is a practical interpretation of data gravity.

Consider:

- Dataset size and growth rate.
- Number of services reading/writing frequently.
- Egress and replication costs.
- Data residency and encryption/key locations.
- Sync and recovery times.
- Ability to keep caches, indexes, or materialized views near consumers.

### 6.3. Data Locality Does Not Mean a Single Copy

You can maintain a canonical data store alongside regional read models or replicas near users. However, you must define the source of truth, update path, freshness SLA, invalidation, conflict handling, and behavior when inter-region links fail.

Do not create copies arbitrarily. Every copy adds cost, data to protect, deletion/retention scope, and risk of divergence.

## 7. Choosing Placement Strategies for Applications and Data

### 7.1. Colocation

Place application services and primary data stores in the same region, and in the nearest AZ when needed. The benefits are fewer round trips and simpler consistency. The trade-off is higher latency for distant users and making the region a larger failure domain.

### 7.2. Regional Read Replicas

Keep the primary write database in one region and create read replicas or projections in other regions. Reads near users are served locally; writes go back to the primary.

Trade-offs:

- Replication lag can cause read-after-write queries to return stale data.
- Failover/replica promotion requires procedures to avoid split-brain.
- Cross-region transfers and extra storage increase costs.
- Queries may not immediately see data just committed.

### 7.3. Regional Write Ownership

For workloads requiring local writes, partition ownership by region, tenant, or entity. Each record has one authoritative home so two regions do not write uncoordinatedly to the same record.

For example, Vietnamese tenants write in Region A while Singaporean tenants write in Region B; cross-region access reads via controlled APIs. You must design for tenant migration, cross-region collaboration, and disaster recovery.

### 7.4. Active-Active Multi-Region

Multiple regions serve traffic and accept writes simultaneously. This improves proximity to users and resilience, but adds complexity around consistency, conflict resolution, global identity, replication ordering, idempotency, and failover.

Choose active-active only when latency or availability requirements strongly justify the complexity. Do not call a setup with "two regions" active-active if all writes still route to a single primary.

### 7.5. Active-Passive

One region handles primary traffic; a second region stays on standby or runs a minimal footprint. On failover, traffic shifts and data is promoted/recovered per RTO/RPO. This is simpler than active-active, though failover can be slower and the DR region needs pre-allocated quotas and capacity.

~~~mermaid
flowchart TB
    USERS["Users in multiple locations"] --> ROUTER["Global traffic manager"]
    ROUTER --> RA["Primary region"]
    ROUTER -. "Failover" .-> RB["DR region"]
    RA --> APPA["Application"]
    APPA --> DBA[("Primary database")]
    DBA -. "Replication" .-> DBB[("Standby replica")]
    RB --> APPB["Warm standby application"]
    APPB --> DBB
~~~

## 8. Replication, Consistency, and Read-After-Write

### 8.1. Replication Lag

Asynchronous replication confirms writes at the primary before replicas receive and apply them. Lag fluctuates with write rates, network conditions, log shipping, and replica capacity.

Key metrics:

- Replication lag in time and bytes/LSN/offsets.
- Apply throughput and queue/backlog.
- Cross-region network errors.
- Oldest unreplicated event.
- Failover readiness and estimated data loss.

### 8.2. Read-After-Write

A user updates a booking in Region A, and their next request routes to a read replica in Region B. If the replica has not yet applied the update, the user can see stale state.

Options:

- Short-lived sticky/session routing to the primary.
- Reading from the primary when operations require read-after-write consistency.
- Returning a version/commit token and waiting until the replica reaches that version.
- Bounded waiting followed by fallback to the primary or returning a pending state.
- Accepting eventual consistency when business logic allows.

Never assume a replica is fresh enough just because it runs in the same cloud provider.

### 8.3. Conflicts and Ownership

In multi-writer setups, two regions can update the same entity concurrently. Define conflict resolution: single-writer per key, version/vector clocks, last-write-wins (only safe for certain data), CRDTs, or domain-specific merges.

For booking slots, last-write-wins can cause double bookings; transactions/locking or an authoritative inventory service are required. Never pick a replication model solely based on database sync features.

## 9. Edge and CDN: Processing Near Users

### 9.1. CDN

CDNs cache content at edge PoPs near users. Common fits:

- Static assets: JS, CSS, images, fonts.
- Public product images and public content.
- Certain API responses with explicit caching policies.
- Large file delivery and streaming.

CDNs reduce origin load and round trips on cache hits. Cache misses still reach the origin; dynamic/private content requires proper Cache-Control headers, vary keys, authorization, invalidation, and TTLs.

Never cache responses containing private user data in a shared cache unless the cache key includes security scope and policies guarantee strict isolation.

### 9.2. Edge Compute

Edge compute runs logic close to users/devices, for example:

- Redirects, routing, and request normalization.
- Authentication token validation or appropriate policy checks.
- A/B testing and non-sensitive personalization.
- Image transformations, compression, and content filtering.
- Lightweight API aggregation or cache lookups.
- IoT protocol translation and processing near event sources.

### 9.3. Workloads Not to Push Arbitrarily to the Edge

- Transactions requiring atomicity with a central data store.
- Business logic heavily reliant on authoritative state.
- Workflows requiring globally consistent state.
- Functions needing large secrets or overly broad access across many PoPs.
- Residency-restricted data if edge locations sit outside permitted jurisdictions.

Edge execution cuts latency for specific steps, but can complicate deployment, debugging, secret distribution, version consistency, and data governance.

## 10. Placement for Specific Workloads

| Workload | Suggested placement | Notes |
|---|---|---|
| Public static content | CDN/edge | Cache keys, TTL, purging, and origin protection |
| Read-heavy API | Region near users + local cache/read replica | Freshness, replication lag, and invalidation |
| Transactional writes | Near authoritative database/leader | Consistency and idempotency |
| Batch analytics | Near data lake/warehouse | Move compute to large datasets |
| Video/image processing | Edge ingress or compute near object storage | Egress, GPU capacity, and object transfer |
| IoT ingestion | Regional ingress near devices | Buffering, local processing, and link outages |
| Payment integration | Aligned with provider endpoints/contracts and data policies | Idempotency, auditing, and secure egress |
| Search/vector indexes | Near consumers or regional partitions | Index freshness and reindexing costs |
| DR/backup | Separate regional failure domain | RPO/RTO, key availability, and restore tests |

## 11. Placement and Data Residency / Security

Low latency must never weaken data protection requirements.

### 11.1. Data Classification

Before picking regions, classify:

- Public content.
- Internal business data.
- Personal data.
- Financial/payment metadata.
- Authentication/identity data.
- Security logs/audit records.
- Backups, replicas, caches, and derived data.

Residency rules can apply to storage, processing, backups, support access, or transfers. Verify legal and contractual obligations per data type and market; do not infer compliance solely from where the primary database lives.

### 11.2. Replication Is Also Data Transfer

Cross-region replication, log shipping, backup copies, analytics exports, and cache fills all move data outside a region. Verify encryption, keys, destination authorization, retention, and legal basis.

### 11.3. Edge Locations and Data

Edge code may process metadata or payloads across many countries. Know what request bodies, logs, caches, and secrets are stored at PoPs; retention durations; who has access; and what data must be sent back to the origin.

## 12. Costs of Placement and Geographic Distribution

An architecture closer to users can cut latency while raising costs due to multiple regions, replicas, data transfers, endpoints, and operations.

### 12.1. Cost Components

- Compute and standby capacity in each region.
- Database replicas, storage, and backup copies.
- Inter-AZ and inter-region data transfers.
- Internet egress, CDN origin fetches, and cache fills.
- Private endpoints, NAT gateways, and transit traffic.
- Replication logs, streams, and broker throughput.
- Monitoring, log ingestion, and trace exports.
- On-call/support and operational complexity.

### 12.2. Cost per Request and Latency Value

Compare using:

\[
\text{Cost per successful request} =
\frac{\text{Total placement-related cost}}
{\text{Successful requests}}
\]

Evaluate alongside p95/p99, conversion rates, booking completion, or business outcomes. Shaving 30 ms of latency is not necessarily worthwhile if it requires two expensive additional database regions the business does not need.

### 12.3. Data Transfer Amplification

A small API request can trigger multiple queries, large query results, log/trace exports, and cache replication. Total cross-region bytes can be several times larger than the client payload. Measure bytes by source, destination, and workload rather than looking only at the aggregate egress bill.

## 13. Measuring and Verifying Placement

### 13.1. Instrument by User Region and Processing Region

Capture safe attributes:

- Client region/country at an appropriate aggregate level.
- Serving region/AZ.
- Origin/data region.
- CDN PoP/cache status.
- Dependency region/endpoint.
- Request route and workload version.
- Cross-region bytes and latency.

Do not log detailed IPs or precise user locations without legitimate purpose and consent; use regional geolocation or sampling.

### 13.2. Network Testing

- Synthetic probes from key user regions.
- DNS resolution and TLS handshake durations.
- TCP connect, packet loss, retransmissions, and routing.
- Application request p50/p95/p99.
- Cross-region round-trip benchmarks.
- Throughput tests for transfers/replication.

### 13.3. Database/Data Testing

- Query latency from each app region.
- Connection pool wait and query plans.
- Replication lag under peak writes.
- Read-after-write correctness.
- Failover RTO/RPO and split-brain prevention.
- Cache hit ratios, freshness, and invalidation delays.

### 13.4. Before/After Comparison

When changing placement, hold workload mix, dataset, request distribution, and observation window constant. Compare:

| Metric | Baseline | After change |
|---|---:|---:|
| User p95 latency | Measured live | Measured under same conditions |
| p99 latency | Measured live | Measured under same conditions |
| Database round trips | Count/query | Count/query |
| Cross-region bytes | Bytes/period | Bytes/period |
| Replication lag | p95/max | p95/max |
| Error/timeout rate | Rate | Rate |
| Cost per request | Cost/request | Cost/request |

Only declare a placement better if improvements are meaningful and do not violate consistency, availability, security, or cost objectives.

## 14. Reference Architecture for BookingCloud

Suppose most users live in one primary market, another group resides in a nearby region, and the system serves a read-heavy catalog alongside transactional bookings.

~~~mermaid
flowchart TB
    U1["Users: primary market"] --> EDGE1["Nearby CDN / edge"]
    U2["Users: nearby markets"] --> EDGE2["Regional CDN / edge"]
    EDGE1 --> ROUTE["Global / regional routing"]
    EDGE2 --> ROUTE
    ROUTE --> APP["Primary application region"]
    APP --> DB[("Authoritative booking DB")]
    APP --> CACHE["Regional cache"]
    APP --> OBJ[("Object storage")]
    APP -. "Async read replication" .-> READ["Regional read model"]
    EDGE1 --> STATIC["Cached public assets"]
    EDGE2 --> STATIC
    READ --> APPNEAR["Regional read API"]
~~~

Separating flows:

- Catalog and static content can be served from CDNs and caches close to users.
- Booking writes go to the authoritative service/database to protect inventory invariants.
- Read models can be replicated closer to other user cohorts when freshness permits.
- Payments call appropriate endpoints per provider contracts without adding unnecessary cross-region hops.
- Backups/DR sit in a failure domain meeting RPO/RTO and residency rules.

## 15. Lab Exercise: Optimizing Placement for BookingCloud

BookingCloud serves users across three regions. Currently, both the application and database sit in Region A. Some users in Region C experience a 420 ms p95 API latency. The catalog is read-heavy; booking writes must prevent double-booking. The database has a read replica in Region C, but lag fluctuates between 0.5 and 8 seconds. Cross-region data transfer costs are climbing.

Complete the following:

**Task 1 — Latency decomposition:** measure DNS/TLS, network, compute, cache/database, and external calls; identify what drives the 420 ms p95.

**Task 2 — User geography:** analyze traffic by market, peak hours, and endpoints. Choose regions/edge locations based on p95/p99 rather than map distance.

**Task 3 — Data locality:** determine which queries can read from replicas and which must hit the primary; propose a read-after-write strategy.

**Task 4 — Placement alternatives:** compare single-region colocation, regional read replicas, regional write ownership, and active-active.

**Task 5 — Edge/CDN:** identify cacheable edge content; define cache keys, TTLs, invalidation, and data that must never enter a shared cache.

**Task 6 — Consistency:** handle the scenario where a user places a booking in Region A and is then routed to a lagging read replica in Region C.

**Task 7 — DR:** propose multi-AZ/multi-region, RTO/RPO, quota/capacity, and data replication; account for residency.

**Task 8 — Cost:** measure inter-region bytes, replica costs, CDN hit ratios, and cost per successful booking.

**Task 9 — Verification:** build synthetic probes, load tests, failover tests, and compare against baseline.

### Self-Check Framework

| Decision | Must prove |
|---|---|
| Moving compute closer to users | Actual network latency drops, not just geographic distance |
| Keeping writes at the primary | Consistency and booking invariants stay intact |
| Reading from distant replicas | Freshness bounds and fallback when lag exceeds thresholds |
| Moving content to a CDN | Caching policies do not leak private data |
| Multi-region | RTO/RPO, quotas, identity, keys, and residency are all viable |
| Reducing inter-region traffic | Fewer round trips/bytes without introducing stale or lost data |
| Optimizing cost | Cost per successful request and user-visible SLOs improve |

## 16. Well-Architected Review

| Perspective | Review question | Required evidence |
|---|---|---|
| **Operational Excellence** | Who owns placement maps, region routing, and replication health? | Service maps, synthetic probes, runbooks, failover exercises |
| **Security** | Do data transfers, edge processing, and replicas meet identity, encryption, and residency rules? | Data classification, routing policies, encryption, access audits |
| **Reliability** | How does the system behave when a region/link fails or replication lag spikes? | RTO/RPO, multi-AZ/region tests, authoritative write models |
| **Performance Efficiency** | Are compute and data positioned near request paths without redundant cross-region round trips? | Regional p95/p99, traces, network and query metrics |
| **Cost Optimization** | Do replicas, egress, CDNs, and standby capacity deliver proportional value? | Cost per request, bytes transferred, cache hits, utilization |
| **Sustainability** | Is data or compute over-replicated, or are unnecessary bytes transferred? | Data lifecycles, deduplication, placement utilization, egress trends |

Optimizing placement means optimizing the entire data journey. Compute placed near users with a distant database can slow requests down; a replica near users with high lag can return wrong results; a fast edge function that spreads sensitive data across countries can raise compliance risk.

## 17. Checklist Before Changing Placement

- [ ] A latency budget exists with network/queue/compute/data/external breakdowns.
- [ ] p50/p95/p99 are measured by user region, serving region, and endpoint.
- [ ] User distribution and temporal demand maps exist.
- [ ] Provider services/SKUs/quotas, network paths, and peering are verified.
- [ ] Compute is placed near authoritative data or backed by suitable read models.
- [ ] Read/write ownership, consistency, and replication lag are defined.
- [ ] Multi-AZ/region setups have RTO/RPO, failover paths, and reserved capacity/quotas.
- [ ] CDN/edge caches have clear keys, TTLs, invalidation, and privacy policies.
- [ ] Data residency, backups, logs, caches, and edge processing are reviewed.
- [ ] Cross-region transfer, NAT, endpoints, replication, and observability costs are calculated.
- [ ] Synthetic probes, load tests, and failover tests measured before and after.
- [ ] Fallbacks exist for replica lag, region outages, or DNS/routing unavailability.
- [ ] Monitoring tracks replication lag, cross-region bytes, p95/p99, and user impact.
- [ ] Runbooks and owners for global routing and data failover are updated.

Optimizing compute placement and data locality must be grounded in latency budgets, locality, and workload semantics. Moving compute closer to users cuts network delay; placing compute near data cuts round trips and transfer volume; edge/CDN tiers serve cacheable content faster. Yet every choice must preserve consistency, data residency, security, failover, and cost within agreed bounds. Only end-to-end measurement and failure testing prove a placement change truly delivers better performance.
