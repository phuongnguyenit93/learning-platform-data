# Designing Multi-Region Active–Passive and Active–Active Architectures

When an application serves users across multiple countries or must continue operating when a cloud region experiences an outage, a single-region architecture may fail to meet latency and recovery objectives. Deploying across multiple regions makes it possible to distribute traffic closer to users, maintain service when a region loses availability, and satisfy geographic data placement requirements. However, multiple regions also increase the complexity of routing, replication, consistency, identity, security, operations, and cost.

Two common models are **active–passive** and **active–active**. In active–passive, one primary region handles workloads while the other region is maintained to take over when needed. In active–active, multiple regions simultaneously serve normal traffic. Neither model is universally better: the choice depends on RTO/RPO, latency, data characteristics, conflict-handling capabilities, business constraints, and operational maturity.

This lesson belongs to the **Global Architecture** chapter of the **Cloud Architecture** track. The track guides you through designing cloud applications from business requirements down to networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. This lesson focuses on choosing multi-region topologies, defining write ownership, routing users, recovering from outages, and validating through drills.

After this lesson, you will be able to:

- Distinguish active–passive, active–active, and hybrid variants.
- Select a model based on RTO, RPO, latency, data residency, and business continuity.
- Design global traffic management, health-based routing, and regional failover.
- Choose synchronous/asynchronous replication and define consistency boundaries.
- Design single-writer, home-region, partitioned ownership, or multi-writer architectures with conflict policies.
- Handle split-brain, stale replicas, failover, and failback.
- Separate the control plane from the data plane and avoid unnecessary global dependencies.
- Plan capacity, security, observability, cost, and DR testing across multiple regions.

## 1. Why Deploy Across Multiple Regions?

A region typically consists of multiple availability zones, yet it can still suffer region-wide failures such as control-plane faults, network disruptions, shared-service outages, or geographic disasters. Multi-region deployments can reduce reliance on a single region and improve the experience for distant users.

Common objectives include:

- **Business continuity:** continue serving when the primary region experiences an outage.
- **Lower user latency:** place compute and data closer to user populations.
- **Data residency:** keep data or processing within permitted jurisdictions.
- **Resilience:** reduce the blast radius of a failure in one region.
- **Capacity distribution:** partition workloads by geography or tenant.
- **Maintenance flexibility:** upgrade one region while another continues serving, if the architecture supports it.

Multi-region alone does not guarantee these objectives. If both regions share a single identity provider, DNS control plane, KMS dependency, or a database writer located in one place, a failure in that shared dependency can still disrupt the entire system.

## 2. What Is Active–Passive?

In the active–passive model, one region acts as primary/active and handles most or all normal write traffic. The passive region is prepared to take over when the primary can no longer serve.

The passive region can operate in different states:

- **Warm standby:** compute and core dependencies are already running at reduced capacity; they must scale up before taking full traffic.
- **Pilot light:** only essential data/identity or minimal core components run continuously; most compute is provisioned when a disaster occurs.
- **Cold standby:** resources are created only after an incident occurs; recovery time is longer.
- **Hot standby:** infrastructure and data remain ready near production scale; traffic can shift faster, at higher cost.

### 2.1. Active–Passive Topology

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global traffic manager"]
    G --> A["Region A: Active"]
    G -. "Standby target" .-> B["Region B: Passive"]
    subgraph RA["Primary region"]
        A --> APP_A["Application fleet"]
        APP_A --> DB_A[("Primary database")]
    end
    subgraph RB["Recovery region"]
        B --> APP_B["Warm standby application"]
        APP_B --> DB_B[("Replicated database")]
    end
    DB_A -. "Async replication" .-> DB_B
~~~

During normal operations, Region A accepts writes. Region B receives replication and may run read-only health checks or limited workloads. During failover, the system must establish authority, promote the data store in B, fence writer A, and shift traffic via a controlled procedure.

### 2.2. Advantages and Limitations

Advantages include simpler write ownership, fewer conflicts, and easier enforcement of data invariants. Compute costs in the passive region can be lower when using pilot light or warm standby.

Limitations are that distant users still call the active region during normal operations; failover can lose committed data not yet replicated under asynchronous replication; passive capacity may be insufficient; and failback requires a separate plan.

## 3. What Is Active–Active?

In active–active, two or more regions simultaneously receive normal traffic. Traffic can be routed by user location, latency, tenant ownership, or load-balancing algorithms.

Active–active does not necessarily mean every piece of data can be freely written in every region. You can have active–active at the stateless/API layer while keeping a single-writer data tier, or partitioned write ownership by tenant/aggregate. You must specify accurately which layers are active–active.

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global traffic manager"]
    G --> A["Region A: Active"]
    G --> B["Region B: Active"]
    subgraph RA["Region A"]
        A --> APP_A["Application fleet A"]
        APP_A --> DB_A[("Regional data A")]
    end
    subgraph RB["Region B"]
        B --> APP_B["Application fleet B"]
        APP_B --> DB_B[("Regional data B")]
    end
    DB_A <-->|"Replication / conflict policy"| DB_B
~~~

### 3.1. Advantages and Limitations

Active–active can lower latency for users across multiple regions, utilize capacity across regions during normal operations, and reduce the need to scale up a passive region after a disaster.

In return, routing, data ownership, and consistency become more complex. If multiple locations write to the same entity, you need a protocol to resolve concurrent updates. Otherwise, the system risks lost updates, duplicate bookings, double spending, or split-brain.

## 4. Distinguishing Models by Layer

A common mistake is calling an entire system active–active simply because application instances run in two regions. The topology must be described per layer.

| Layer | Active–passive | Active–active |
| --- | --- | --- |
| Global DNS/traffic | Routes to primary, standby when needed | Routes concurrently to multiple regions |
| Web/API compute | Primary serves traffic; passive scales on failover | Multiple regions process requests |
| Database write | One primary | Multi-writer or partitioned/single-writer by ownership |
| Database read | Replica/standby reads if safe | Regional read replicas or local data |
| Queue/worker | Primary processes; passive stands by | Multiple regions consume/produce by partition |
| Cache | Primary or warm passive cache | Local cache per region, requiring an invalidation strategy |
| Identity | Has a recovery path | Federated/local verification or HA global dependency |
| Control plane | Can be managed from primary | Manages multiple regions; must avoid runtime dependencies |
| Observability | Can be centralized | Regional collection and multi-region aggregation |

A system may choose active–active compute, an active–passive database writer, and local read replicas. This is often a sensible hybrid when read latency matters while write consistency needs to stay simple.

## 5. Choosing Based on RTO and RPO

**RTO (Recovery Time Objective)** is the target duration to restore service. **RPO (Recovery Point Objective)** is the maximum acceptable data loss, typically measured as the time window of data that may be lost.

Active–passive can achieve a low RTO with hot/warm standby and automated failover, but RPO depends on replication mode and log durability. Active–active can keep serving traffic in another region when one fails, yet RPO is not automatically zero: asynchronous replication still has lag and concurrent writes can still conflict.

| Requirement | Potentially Suitable Model | What to Verify |
| --- | --- | --- |
| Long RTO, low DR cost | Pilot light/cold standby | Do provisioning and restore times fit within RTO? |
| Medium RTO, low RPO | Warm standby + frequent replication | Lag and promotion procedure |
| Very low RTO, single writer | Hot standby + automated failover with fencing | Writer authority, capacity, and route propagation |
| Low latency across multiple regions | Active–active compute/reads | Data ownership and regional dependencies |
| Local writes across multiple regions | Active–active data | Conflict semantics, ordering, and business invariants |
| Per-tenant data residency | Home-region/partitioned ownership | Do replication and support access comply? |

Targets must tie back to business journeys. A payment ledger, bookings, search indexes, and notifications may have different RPO/RTO values. Avoid setting a single blanket RPO/RTO across the entire platform when datasets have different characteristics.

## 6. Global Traffic Management

A global traffic manager decides which region a client is directed to. Common methods include:

- **Geo routing:** routes based on geographic location or data residency policies.
- **Latency-based routing:** chooses the endpoint with the lowest measured latency.
- **Weighted routing:** distributes fixed or gradually increasing traffic proportions.
- **Failover routing:** prefers the primary and shifts to standby when health policies fail.
- **Anycast/global edge:** directs clients to the nearest entry point, then routes internally.
- **Tenant/home-region routing:** always directs a tenant to the region that owns its data.

### 6.1. Health Checks Must Reflect Serving Capability

Health checks that only verify a process is alive are insufficient. A region can return HTTP 200 while its database writer, queue, or identity dependency is unavailable. Conversely, a health check that depends on every optional service can take an entire region out of rotation even while core functionality still works.

Distinguish between:

- **Liveness:** does the process need to be restarted?
- **Readiness:** can this instance accept this request?
- **Regional service health:** can the region satisfy critical paths and capacity?
- **Dependency health:** are required dependencies still operational?
- **Synthetic business check:** does a representative business journey succeed?

Prevent health checks from causing failover oscillation: shifting traffic raises load, health checks in the new region fail, and traffic bounces back. Use appropriate hysteresis, cooldowns, thresholds, and manual overrides.

## 7. DNS, TTL, and Connection Behavior

DNS failover is not instantaneous for all clients. Resolvers, browsers, operating systems, proxies, and connection pools can cache addresses; already-open connections can continue hitting the old endpoint.

Understand:

- DNS TTLs and negative caching.
- Whether resolvers/clients honor TTLs.
- Health propagation times in load balancers/global accelerators.
- Whether HTTP keep-alive, HTTP/2 connections, and gRPC channels are drained/reconnected.
- Mobile clients that may stay offline for long periods before reconnecting.
- Callbacks/webhooks that may call back to an old endpoint.
- Whether certificates/SANs match the hostname after failover.

Do not rely on a low DNS TTL as a fencing mechanism. DNS only steers traffic; it does not revoke the old writer's write authority or close existing connected sessions.

## 8. Data Replication: Synchronous and Asynchronous

Replication copies data from one region/node to another. The two main approaches have different trade-offs.

### 8.1. Synchronous Replication

A write is acknowledged only after the required replicas confirm durability according to system semantics. This can reduce RPO, but adds network latency and dependency on inter-region links.

If the inter-region link slows down or drops, writes may block or lose availability depending on the protocol. You must understand quorum, acknowledgment levels, and actual failure behavior.

### 8.2. Asynchronous Replication

The primary acknowledges writes before replicas in other regions receive all the data. This keeps write latency low in the primary region and increases write availability when links are slow, but introduces replication lag and risks losing some data if the primary fails abruptly.

### 8.3. Comparison

| Criterion | Synchronous | Asynchronous |
| --- | --- | --- |
| Write latency | Typically higher due to round trips | Typically lower at the primary |
| Data loss on failover | Can be lower depending on commit/quorum guarantees | May lose unreplicated logs |
| Inter-region network dependency | High | Lower on the write path |
| Availability during partitions | Writes may stall if quorum cannot be reached | Primary can continue depending on architecture |
| Complexity | Quorum/commit semantics | Lag monitoring and recovery points |
| Use cases | Data requiring strict durability within supported scope | DR, read replicas, analytics, or lag-tolerant use cases |

There is no "zero data loss" guarantee from the synchronous label alone. Inspect the database/provider, failure model, quorum rules, and when the client receives commit confirmation.

## 9. Data Write Authority: Single-Writer, Home-Region, and Multi-Writer

This is the most critical decision in an active–active architecture.

- **Single-writer:** one authoritative writer for the entire dataset or cluster.
- **Home-region per tenant/aggregate:** each tenant or aggregate has one region owning its writes.
- **Partitioned ownership:** data is sharded/partitioned; each partition has a clear owner.
- **Multi-writer:** multiple regions can write the same data, with conflict-resolution protocols/semantics.
- **Read-local/write-home:** reads are served in the nearby region; writes are forwarded to the owning region.

For bookings, inventory, and ledgers, single-writer/home-region is usually much easier for preserving invariants. For profiles/preferences or data with commutative merge operations, multi-writer may fit better if conflict semantics are proven.

### 9.1. Home-Region Routing

A tenant directory can map each tenant to a home region. Requests are routed to that region for writes; other regions serve reads according to policy. When migrating a home region, data migration, writer fencing, and versioned routing updates are required.

The directory is a critical dependency. Cache signed/versioned mappings, ensure HA, and define behavior when lookups fail. Stale caches must never allow two regions to believe they are both the home writer.

## 10. Consistency and Conflict Resolution

When two regions receive updates, define the semantics:

- **Strong consistency:** operations observe a consistent order per the system's guarantees, usually requiring coordination and potentially increasing latency or reducing availability during partitions.
- **Eventual consistency:** replicas converge after updates propagate, though stale reads can occur in the meantime.
- **Causal consistency:** preserves causal order within a defined scope.
- **Read-your-writes:** a client sees its own updates after writing within a session/context.
- **Monotonic reads:** a client does not regress to an older version within a session.

Conflict policies may use optimistic concurrency, version checks, domain-specific resolution, CRDTs for suitable structures, or manual reconciliation. Last-write-wins should never be applied blindly to financial state, bookings, or inventory.

## 11. Preventing Split-Brain and Fencing

Split-brain occurs when two nodes/regions simultaneously believe they hold authoritative write permission for the same data. DNS failover or health timeouts are not enough to prevent this.

Controls:

- Quorum/consensus or a coordinator with clear authority.
- Monotonically increasing leader epochs/generations.
- Leases with clearly understood semantics and clock assumptions.
- Fencing tokens verified at the target storage resource.
- Restricting the database writer endpoint/role to a single authority.
- Revoking sessions/credentials/network paths of the old writer.
- Never promoting a standby before verifying the old writer has been fenced.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Region A writer
    participant B as Region B candidate
    participant D as Protected database

    C->>A: Grant epoch 17
    A->>D: Write with epoch 17
    D-->>A: Accepted
    Note over A,B: Network partition
    C->>B: Grant epoch 18 after authority decision
    B->>D: Register epoch 18
    D-->>B: Accepted
    A->>D: Delayed write with epoch 17
    D-->>A: Reject stale epoch
~~~

If the storage/database does not support fencing tokens directly, you must enforce promotion/revocation/network/credential mechanisms at another layer and prove they genuinely block the old writer. Never open writes while authority is ambiguous.

## 12. Stateless Compute and Regional Data

Active–active compute is typically easier to deploy than active–active data if the application is stateless or externalizes state out of process. Each region can run the same application version and receive traffic independently.

Ensure:

- Identical or compatible images, configurations, and versions.
- Sessions do not depend on local memory; use tokens or shared/replicated session stores per policy.
- Regional endpoints and secrets/certificates work properly.
- Feature flags/configs maintain appropriate consistency.
- Background jobs do not run twice unintentionally.
- Scheduled tasks have a leader/lease or partitioned ownership.
- Rate limits/quotas have clear global or regional policies.
- Dependencies have sufficient capacity during failover.

Stateless does not mean there is no state; state is offloaded to databases, caches, queues, object storage, or external services. Each of those requires its own topology and recovery design.

## 13. Multi-Region Caching and Sessions

Local caches reduce latency but can become stale or out of sync. Define which data types tolerate eventual consistency and establish an invalidation mechanism.

Patterns:

- Per-region local cache with TTL.
- Global distributed cache or regional replication.
- Cache-aside backed by a centralized source of truth.
- Versioned cache keys or invalidation events.
- Stateless session tokens with signatures/expiry.
- Home-region session stores.

Do not use stale local caches for sensitive decisions such as access permissions, payment authorization, or inventory reservation if semantics disallow it. TTL bounds staleness over time but does not guarantee instant invalidation.

## 14. Multi-Region Queues, Events, and Background Processing

Queues can be deployed per region or backed by a multi-region broker. Define message ownership, ordering, duplicate handling, and failover semantics.

Options:

- Regional queues with local producers/consumers; replicate events to other regions.
- Global broker with a well-defined partition/replication topology.
- Per-tenant home-region queues.
- Authoritative outbox/event log in one region.
- Cross-region forwarding with idempotent consumers.

Do not let two regions process the same scheduled job or message partition without ownership, leases, or idempotency. During failover, inspect offsets/checkpoints and messages acknowledged before replication.

## 15. Control Plane and Data Plane

The control plane manages provisioning, configuration, routing policies, deployments, and governance. The data plane processes business requests. A resilient design should not depend on a global control plane for every runtime request.

For example, if the global control plane becomes temporarily unreachable, regions can continue serving using validated configuration and cached policies within safe limits. However, sensitive changes such as revoking permissions or transferring a writer must be coordinated properly.

Define:

- Which capabilities must continue working if the control plane goes down?
- Which configs may use last-known-good values and for how long?
- How are routing policy versions distributed?
- Who has authority to switch writers or change home regions?
- How do you prevent two independent control planes from granting conflicting authority?
- Where are recovery metadata and audit logs stored?

## 16. Multi-Region Security and Identity

Multi-region expands security boundaries: identity, secrets, KMS, certificates, networking, and operator access must operate across regions without unnecessarily spreading credentials.

Principles:

- Separate workload identities per region/environment.
- Least privilege per service and resource.
- Secret replication with explicit policies and scopes.
- Key policies/replica keys compliant with data residency requirements.
- TLS certificate SANs and trust chains compatible with global and regional endpoints.
- mTLS identities between services and regions.
- Centralized audit logs while retaining local copies per policy if required.
- Time-bound, audited break-glass operator access.
- Regional network segmentation and egress controls.
- Controls over cross-region data transfers and support access.

Do not replicate all secrets to every region if workloads there do not need them. Failover must have a valid path to issue credentials without granting broader access than necessary.

## 17. Data Residency and Sovereignty

A tenant may require data to remain within a specific country or region. This affects primary storage, replicas, backups, logs, analytics, key material, support access, and processing.

Determine exactly which data is in scope: content, metadata, backups, telemetry, support artifacts, or derived data. Do not assume keeping only the primary database in the local region is enough if logs or backups are shipped globally.

Models:

- Home-region per tenant, without replicating sensitive data outside the boundary.
- Cross-region replication within an approved geography.
- Replicating de-identified metadata/aggregates only.
- DR within the same legal jurisdiction across distinct zones.
- Using regional key boundaries or appropriate customer-managed keys.

Data residency can conflict with DR goals if no eligible recovery region exists. Pre-define approved DR regions and the achievable recovery times.

## 18. Capacity Planning and Failover Readiness

Active–passive requires the passive region to have enough capacity to absorb failover load. Active–active requires each region to maintain headroom to absorb traffic shifted from another region.

For instance, two regions split traffic 50/50. If one region fails, the surviving region must handle nearly double the normal load—or the system must proactively shed features/traffic. You cannot assume autoscaling will add capacity instantaneously; quotas, warm-up times, image pulls, connection limits, and database capacity can all become bottlenecks.

Test:

- Normal traffic distribution.
- Peaks/bursts.
- N-1 regional failures.
- Dependency degradation within one region.
- Scale-up times and quota availability.
- Database/queue throughput under concentrated load.
- Cache cold starts and connection surges.
- Cost of maintaining warm/hot standby.

### 18.1. Headroom for Active–Active

If each region must carry the full load when another fails, each region needs N-1 capacity. If degraded mode is acceptable, you can design specific features to be shed or queued. Crucially, degradation behavior must be documented in SLOs and tested.

## 19. Failover and Failback

Failover transfers service/authority to an alternate region. Failback transitions back to the original region or a new steady-state topology after remediation.

A safe failover sequence:

1. Detect and assess the scope of the incident.
2. Decide to fail over based on policy and business impact.
3. Fence the old writer or verify it no longer holds write authority.
4. Inspect replica freshness and recovery points.
5. Promote the new data store/cell with a new epoch/version.
6. Update routing and tenant/home-region mappings.
7. Ramp traffic by cohort/health gates.
8. Verify business invariants, queues, and payment reconciliation.
9. Monitor latency, errors, replication, and backlogs.
10. Record actual RPO/RTO and plan the failback decision.

Failback should not be triggered merely because the old region reports healthy. Data must be re-seeded/reconciled, writer authority re-established, and traffic transitioned in a controlled manner. A DNS switch is not data failback.

## 20. Multi-Region Observability

You must distinguish local incidents from global ones. Telemetry should include dimensions for region, zone, cell, service, tenant tier, and operation.

Useful signals:

- Availability/error rates by region.
- Latency p50/p95/p99 by user geography.
- Global routing decisions and health statuses.
- Replication lag/position and writer epochs.
- Cross-region bytes/latency/cost.
- Queue age/offset lag.
- Capacity headroom and autoscaling times.
- Failover/failback state and duration.
- Achieved RPO/RTO.
- Data reconciliation mismatches.
- Certificate/KMS/identity errors by region.

Clocks across regions must be synchronized well enough for reliable correlation and log analysis; however, never rely solely on timestamps to establish commit order. Use log sequences, versions, or causal metadata aligned with data semantics.

## 21. Cost and Complexity

Multi-region typically increases both cost and operational overhead:

- Compute and databases in secondary regions.
- Data replication and cross-region egress.
- Storage/backup duplication.
- Global networking, traffic management, and security services.
- Observability ingestion/retention.
- KMS/secret/certificate operations.
- On-call rotations, testing, runbooks, and operational skills.

Active–passive pilot light saves compute but can increase RTO. Hot standby costs more while cutting provisioning time. Active–active utilizes capacity for normal traffic, yet can be expensive due to replication and data conflict management.

Compare full-lifecycle costs against the business impact of downtime and data loss, rather than looking solely at the compute bill.

## 22. Common Design Pitfalls

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Calling a system active–active because two regions run the app | Data tier remains a single-region bottleneck | Describe topology layer by layer |
| DNS failover without fencing the writer | Split-brain and conflicting writes | Authority models, epochs, and fencing |
| Unmonitored async replica lag | RPO breaches upon promotion | Lag alerts and candidate thresholds |
| Under-provisioned passive region | Failover succeeds, then service overloads | N-1 capacity tests and warm-up |
| Active–active writes without a conflict policy | Lost updates/double bookings | Single-writer/ownership or domain conflict resolution |
| Using LWW for financial data | Loss of valid transactions | Domain-specific consistency |
| Global dependency without HA | Single dependency causes cross-region outage | Isolate/cache/replicate runtime dependencies |
| Overly sensitive health checks | Flapping and failover loops | Hysteresis, cooldowns, and business checks |
| Changing DNS while ignoring sessions/connections | Clients keep calling the old region | Draining, reconnecting, TTLs, and client handling |
| Replicating all data without checking residency | Policy/contractual violations | Data classification and regional placement |
| Keys/secrets unavailable in DR | Application cannot read data | DR identity/KMS testing |
| Rushed failback | Repeat outage or split-brain | Reconciliation, re-seeding, writer transfer |
| Never rehearsing region loss | RTO exists only on paper | Game days and full failover drills |
| Ignoring egress/ops costs | Multi-region architecture blows budget | Cost modeling and workload reviews |

## 23. Multi-Region Architecture Design Process

1. **Define objectives:** latency, availability, RTO/RPO, data residency, and business continuity.
2. **Classify workloads/data:** stateless/stateful, read/write ratios, consistency, and rebuildability.
3. **Select topology:** active–passive, active–active, or hybrid per layer.
4. **Define write authority:** single writer, home region, partition owner, or multi-writer protocol.
5. **Design replication:** sync/async, lag limits, retention, and conflict handling.
6. **Design global routing:** geo/latency/weighted/failover/tenant routing and health semantics.
7. **Guard against split-brain:** quorum, epochs, fencing, and writer transitions.
8. **Design runtime dependencies:** identity, KMS, secrets, queues, caches, and control plane.
9. **Ensure capacity:** N-1 headroom, warm-up, quotas, bursts, and degraded modes.
10. **Protect data:** residency, encryption, backups, audits, and cross-region access.
11. **Establish observability/cost:** regional metrics, replication, egress, and failover tracking.
12. **Rehearse:** regional outages, network partitions, stale replicas, failover, failback, and reconciliation.
13. **Review periodically:** actual RPO/RTO, topology drift, cost, and provider lifecycle changes.

## 24. Example: Equipment Rental SaaS Platform

A platform serves customers in Southeast Asia and Europe. Enterprise tenants have bookings, inventory, payments, and reporting. Some tenants require data to stay in their home region; payments and bookings require strong consistency; reporting tolerates eventual consistency.

### 24.1. Workload Breakdown

| Workload | Candidate Model | Rationale |
| --- | --- | --- |
| Stateless Web/API | Active–active | Can route close to users and scale per region |
| Booking writes | Home-region per tenant | Maintains a single writer for booking invariants |
| Inventory allocation | Single authority per asset/partition | Prevents double reservations |
| Payment ledger | Single-writer/quorum-backed primary per policy | Preserves ordering and clear reconciliation |
| Search/reporting | Regional read models, async replication | Tolerates freshness lag |
| Notifications | Regional workers, durable queues, and idempotency | Can handle retries and backlogs |
| Static assets | CDN/global edge | Serves close to users, reduces origin load |

### 24.2. Conceptual Topology

~~~mermaid
flowchart TB
    U["Users across geographies"] --> G["Global traffic management"]
    G --> RA["Region A: Active"]
    G --> RB["Region B: Active"]
    RA --> DIR["Tenant home-region directory"]
    RB --> DIR
    DIR --> BA["Booking service / home writer A"]
    DIR --> BB["Booking service / home writer B"]
    BA --> DBA[("Region A primary data")]
    BB --> DBB[("Region B primary data")]
    DBA -. "Approved replication" .-> DBB
    DBB -. "Approved replication" .-> DBA
    RA --> READ_A["Regional read models"]
    RB --> READ_B["Regional read models"]
~~~

This topology illustrates per-tenant ownership. Do not interpret the two replication arrows as permitting both databases to write for the same tenant. Each tenant has only one home writer at any point in time; changing a home region requires fencing and a migration protocol.

### 24.3. Region A Outage Scenario

1. Global health policy confirms Region A cannot serve traffic.
2. For Region A home-region tenants, the control workflow decides DR actions based on RPO/RTO.
3. Fence writer A via database promotion/epoch or an equivalent mechanism.
4. Verify Region B has logs/replicas within the acceptable recovery point.
5. Promote the new writer and update the tenant mapping with a new version.
6. Route Region A tenants to Region B; keep other tenants in their respective home regions if topology allows.
7. Verify booking/inventory/payment invariants and reconciliation.
8. Monitor backlog/latency and capacity.
9. Once A recovers, re-seed or reconcile it as a replica first; fail back only after review.

## 25. Well-Architected Review

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Are RTO/RPO measured? Do surviving regions have enough capacity? Do failover/failback have fencing, validation, and rehearsals? |
| **Security** | Are identity, secrets, KMS, logs, and data residency scoped by region/tenant? Is operator access audited? |
| **Performance Efficiency** | Does routing reduce latency? Does replication/coordination impact the write path? Are cross-region calls optimized? |
| **Cost Optimization** | Are warm/hot standby, replication, egress, and observability costs proportional to business impact? |
| **Operational Excellence** | Are there global dashboards, runbooks, routing policy owners, replication lag alerts, and game days? |

### Acceptance Checklist

- [ ] Latency, RTO, RPO, residency, and business continuity targets are defined per workload.
- [ ] Topology is documented separately for compute, data, queues, caches, identity, and control plane.
- [ ] Active–passive has a warm-up/capacity plan and full recovery dependencies.
- [ ] Active–active has explicit write ownership and conflict policies; never assumes all regions write freely.
- [ ] Replication mode, lag thresholds, and commit semantics have been verified.
- [ ] Global routing includes geo/latency/health policies, hysteresis, and manual overrides.
- [ ] DNS TTL, client connections, sessions, and webhook behaviors have been accounted for.
- [ ] Writer transitions use quorum/epochs/fencing or equivalent authority mechanisms.
- [ ] Tenant/home-region mappings are versioned, HA, and cannot grant dual writers.
- [ ] Queues/jobs have ownership, idempotency, ordering, and replay policies.
- [ ] Caches/sessions have freshness and invalidation semantics.
- [ ] Identity/KMS/secrets/certificates work in the DR region under least privilege.
- [ ] Data residency covers backups, logs, telemetry, derived data, and support access.
- [ ] N-1 capacity, quotas, warm-up, and degraded modes have been load tested.
- [ ] Dashboards measure regional health, latency, replication lag, writer epochs, RPO/RTO, and cost.
- [ ] Failover, failback, network partitions, and stale replicas have been rehearsed.

## 26. Applied Exercise

A SaaS platform has 2,000 tenants with users concentrated in Southeast Asia and Europe. Region A currently serves all write traffic. Region B maintains an asynchronous replica with a target RPO of 60 seconds and an RTO of 15 minutes. The product team wants to move to active–active to reduce latency; however, bookings and inventory must prevent double booking, the payment ledger requires strict transaction ordering, and search/reporting can tolerate data delayed by a few minutes.

Design:

1. Which components should be active–active and which should remain single-writer/home-region?
2. How should tenants be assigned to home regions based on residency, latency, and capacity?
3. What components are needed in global routing and the tenant directory?
4. How should synchronous/asynchronous replication be applied to bookings, the ledger, search, and reporting?
5. How do you migrate a tenant's home region without creating two writers?
6. How are quorum, epochs, fencing, and session revocation coordinated during a network partition?
7. If Region A fails abruptly with 45 seconds of replica lag, how do you evaluate the 60-second RPO before promotion?
8. Can Region B's capacity serve the shifted traffic within 15 minutes? Have cold caches, quotas, and connection surges been accounted for?
9. Once A recovers, how do you handle re-seeding/failback and reconciliation?
10. Which metrics and game days prove latency, RPO/RTO, consistency, and cost?

A sound solution can deploy active–active for stateless APIs and regional read models, retain home-region writers for bookings/inventory/payments, use async replication for lag-tolerant data, and apply stronger policies for the ledger. The tenant directory must enforce authority/fencing; during failover, promote only after the old writer is fenced and the candidate meets RPO. Reporting/search can be rebuilt or updated asynchronously; financial data must never resolve conflicts by timestamp alone.

**Core Takeaway:** active–passive prioritizes a single writer and controlled takeover; active–active distributes steady-state traffic but demands stricter ownership and consistency design. Choose topologies layer by layer, measure RTO/RPO/latency, protect write authority, provision capacity, and rehearse failover/failback. Multi-region only delivers reliability when data, identity, routing, dependencies, and operational procedures can all withstand failure within committed bounds.
