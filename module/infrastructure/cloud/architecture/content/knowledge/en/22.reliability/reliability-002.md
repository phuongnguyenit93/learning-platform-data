# Designing Failure Domains and Limiting Blast Radius

A cloud system can span multiple servers, availability zones, and managed services yet still suffer widespread outages if components share too many resources or depend tightly on one another. A minor bug in a database connection pool, queue, routing configuration, or authentication service can bring down multiple features together. Therefore, reliability design is not just about adding replicas or deploying across multiple availability zones. You must identify **failure domains** and proactively limit the **blast radius** of every incident.

A failure domain is the scope of infrastructure or components that can be affected together by a single root cause. Blast radius describes the scope of users, data, services, or features impacted when a failure occurs. Good architecture establishes sensible independent boundaries, caps shared resources, controls failure propagation paths, and keeps critical functions running in an intentional degraded mode.

This lesson belongs to the **Reliability** chapter of the **Cloud Architecture** track. The track teaches how to design cloud applications from business requirements to networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. This content focuses on translating those goals into failure domain boundaries, isolation policies, and verifiable recovery procedures.

After this lesson, you will be able to:

- Distinguish failure domain, fault containment boundary, blast radius, availability zone, and region.
- Map dependencies, shared resources, and failure propagation paths.
- Design isolation by zone, region, service, tenant, cell, and workload.
- Apply bulkheads, timeouts, circuit breakers, load shedding, and graceful degradation.
- Bound concurrency, connections, queues, and quotas to prevent one workload from exhausting shared resources.
- Design data replication, failover, and recovery with consistency awareness.
- Define SLOs, error budgets, and recovery criteria by impact tier.
- Test failure scenarios and measure actual impact scope.

## 1. Failure Domain and Blast Radius

A **failure domain** is a set of resources that can simultaneously lose availability due to a common cause. Examples include virtual machines on the same power rack, workloads sharing an availability zone, or multiple services depending on a single database cluster.

**Blast radius** is the extent of impact an incident creates. It can be measured by the number of tenants/users, percentage of requests, number of features, number of records, or duration of degraded service.

The two concepts are related but distinct: a failure domain describes where failures can occur together; blast radius describes how far the consequences spread. A large failure domain can have a small blast radius if strong isolation layers exist. Conversely, a failure in a small component can have a large blast radius if it sits on every execution path.

### 1.1. Simple Example

Suppose an application consists of an API, booking service, payment service, and notification worker. If all of them share a single database connection pool, a hung query can consume all connections and halt all four functions. The failure starts in one workload but spreads to multiple features because resources are shared without limits.

If each workload has its own pool with quotas, timeouts, and concurrency limits, the failing query may still affect the booking service but is far less likely to exhaust connections for payment or notification. This is how fault containment narrows the blast radius.

### 1.2. Mental Model

~~~mermaid
flowchart TB
    subgraph SHARED["No isolation boundary"]
        S["Shared database / connection pool"]
        A["Booking"]
        B["Payment"]
        C["Notification"]
        A --> S
        B --> S
        C --> S
        S --> X["Shared resource failure"]
    end
~~~

~~~mermaid
flowchart TB
    subgraph ISOLATED["With resource boundaries"]
        A["Booking"] --> PA["Pool / quota A"]
        B["Payment"] --> PB["Pool / quota B"]
        C["Notification"] --> PC["Pool / quota C"]
        PA --> DB[("Database with total limit")]
        PB --> DB
        PC --> DB
    end
    X["Failure in workload A"] -. "Bounded within quota" .-> PA
~~~

Application-level isolation does not automatically create independent databases; total quotas must still fit within the database's actual capacity. The goal is to allocate capacity and prevent one caller from consuming resources meant for other functions.

## 2. Failure Domain Layers in the Cloud

Failure domains exist across multiple layers, from hardware to applications and data.

| Layer | Failure domain examples | Potential consequences |
| --- | --- | --- |
| Hardware | Disk, host, rack, power supply | Server or group of machines stops |
| Network | Switch, router, link, DNS, NAT gateway | Connectivity loss or increased latency |
| Availability zone | Independent data center/zone per provider model | Partial loss of compute, network, or storage in the zone |
| Region | Cloud geographic region | Geographic-scale loss of service or connectivity |
| Control plane | Provider management/provisioning API | Cannot create/modify resources even if data plane still runs |
| Shared services | Identity, DNS, secrets, database, message broker | Many workloads depend on a single point |
| Application | A process, service, deployment, or cell | A faulty version affects requests routed to it |
| Tenant/workload | A tenant or heavy job | Noisy neighbor or isolated data errors |
| People/process | Misconfiguration, bad deploy, leaked credentials | Simultaneous changes impacting multiple environments |

An availability zone may be designed for independence across certain physical components, but that does not mean zero shared dependencies. Regions may also rely on certain global control planes or services. Verify the actual characteristics of the provider and services used.

## 3. Fault Containment Boundary

A **fault containment boundary** is an architectural boundary designed to stop failures from escaping a defined scope. It can be a separate process, dedicated queue, cloud account/project, network boundary, database cluster, cell, or region.

A useful boundary needs:

- Bounded resources and quotas.
- Clearly defined dependencies.
- Failure detection and handling mechanisms.
- Appropriate access permissions and credentials.
- Ability to deploy, roll back, or recover without impacting the entire system.
- Metrics indicating whether failures are contained within the boundary or leaking outside.

Not every boundary requires completely separate infrastructure. You can start with concurrency limits and pools, then increase isolation as availability or tenant isolation requirements grow.

## 4. Availability Zone and Region Isolation

### 4.1. Multi-Zone

Deploying across multiple availability zones reduces reliance on a single infrastructure area within a region. Applications typically need load balancers, compute distributed across zones, and databases/storage with an appropriate topology.

However, multi-zone only helps when the execution path can genuinely continue if a zone goes down:

- Load balancers and network routes can still serve traffic.
- Application instances remain available in other zones.
- Databases have suitable replicas/quorum or failover capability.
- Storage and queues are not confined to the failed zone.
- Subnet/IP capacity in remaining zones can handle the load.
- Internal dependencies and outbound connectivity still function.

If all app instances live in zone A, putting a database replica in zone B does not keep the application serving when zone A is lost.

### 4.2. Multi-Region

Multi-region can reduce the blast radius of a regional outage, support disaster recovery, or serve users across geographies. In return, it complicates consistency, replication, routing, data residency, identity, and operations.

Define the data model clearly:

- **Active-passive:** one region serves primary traffic, while the other stands by or serves limited traffic.
- **Active-active:** multiple regions serve traffic simultaneously; requires clear write partitioning, conflict resolution, or replication semantics.
- **Read-local/write-home:** users read from a nearby region but write to the data's home region.
- **Sharded-by-region:** each data group has a home region, minimizing cross-region writes.

Do not treat active-active as the default choice simply because multiple regions exist. For data with strong invariants, a single authoritative write region or clear sharding may be safer and easier to operate.

## 5. Shared Dependencies as Large Blast Radius Sources

A service shared by many applications can become a failure propagation point. For example:

- An identity provider outage causes every request requiring login to fail.
- DNS failure prevents services from resolving dependencies.
- Secrets manager outage blocks new workloads from starting up and fetching credentials.
- A shared database cluster allows one tenant/job to exhaust connections.
- A shared message broker hits full queues or quota limits.
- A shared NAT gateway or outbound proxy becomes overloaded.

List shared dependencies and determine their role in each business journey.

### 5.1. Critical vs. Optional Dependencies

| Dependency | When is it critical? | Mitigation strategies |
| --- | --- | --- |
| Identity/authentication | Every request requiring fresh authentication | Local token validation per policy, JWK caching with TTL, multiple supported endpoints |
| Profile service | Displaying supplementary information | Cache or fallback for non-sensitive fields |
| Payment provider | Creating payment transactions | Timeouts, idempotency, pending state, and reconciliation |
| Notification provider | Sending notifications | Durable queue, bounded retries, deferred processing |
| Analytics warehouse | Dashboards/reports | Decouple from the transaction path |
| Feature/config service | Controlling features or policies | Versioned cache with TTL; do not fall back to stale data for sensitive policies unless safe |

There is no single fallback for every dependency. For auth, a stale fallback can grant unauthorized access; for thumbnails, a placeholder fallback is usually fine. Each use case must define acceptable staleness/fallback levels.

## 6. Dependency Graphs and Failure Propagation Paths

A service may be healthy on its own yet fail when a dependency slows down. For instance, the API waits on the booking service; booking waits on inventory; inventory waits on the database. Without allocated timeouts, each tier can hold requests and connections longer than necessary.

Draw dependency graphs by user journey, not just deployment diagrams. Include synchronous calls, queues, databases, DNS, secrets, external providers, and control planes needed during operation.

~~~mermaid
flowchart LR
    U["Client"] --> API["API"]
    API --> B["Booking"]
    B --> I["Inventory"]
    B --> P["Payment"]
    I --> DB[("Database")]
    P --> PSP["Payment provider"]
    B --> ID["Identity/config"]
    B --> Q["Event queue"]
    Q --> N["Notification"]
~~~

For each edge, document timeout, retry, concurrency, criticality, ownership, and failure behavior. Synchronous edges create latency chains and risk direct failure propagation; queues decouple processing time but introduce backlogs and durability requirements.

### 6.1. Computing the Critical Path

A synchronous request completes only when all mandatory dependencies complete. If the API needs booking and inventory concurrently, latency approximates the slowest call plus overhead; if called sequentially, times add up. Many parallel dependencies also raise the probability that at least one dependency fails.

Therefore, reducing dependencies on the critical path typically shrinks blast radius and latency. Work that can happen later should be moved to appropriate queues/workflows with clear status tracking.

## 7. Bulkhead: Preventing One Workload from Exhausting Resources

The **Bulkhead pattern** partitions resources into independent bounded pools, like watertight compartments on a ship. A failing or surging request group cannot consume every thread, connection, or worker in the system.

Types of bulkheads:

- Separate thread pools per dependency or workload.
- Separate connection pools per functional group.
- Separate queues for tasks with different priority levels.
- Concurrency limits per tenant or operation.
- CPU/memory quotas per container/process.
- Dedicated accounts, projects, or clusters for workloads needing strong isolation.

For example, the payment flow should not share an unbounded executor with thumbnail generation jobs. If thumbnail workers hang, payment requests still need protected threads, connections, and quotas.

### 7.1. Trade-Offs

Bulkheads increase configuration overhead and can leave resources idle in one partition while another is overloaded. Splitting into too many tiny pools causes fragmentation. Pool sizes and resource ratios should be based on workloads, SLOs, and downstream limits.

## 8. Timeouts and Deadline Propagation

Timeouts prevent requests from holding resources indefinitely when a dependency does not respond. However, independent per-tier timeouts can leave callers timed out while downstream services keep processing.

Use end-to-end **deadlines** across requests: the caller has an overall time budget; each dependency receives the remaining budget minus safety overhead.

Example of an API with an 800 ms deadline:

| Component | Example budget |
| --- | ---: |
| Gateway/auth | 80 ms |
| Booking logic | 120 ms |
| Inventory query | 180 ms |
| Payment status read | 180 ms |
| Serialize/response | 60 ms |
| Network/variance buffer | 180 ms |
| Total | 800 ms |

These numbers are illustrative. If inventory times out at 180 ms, the API should not keep retrying multiple times if insufficient total deadline remains. Cancel downstream work when possible and release connections/permits.

A timeout does not prove an operation failed. For commands with side effects, the client may not know whether the commit occurred. Use idempotency keys, operation states, and reconciliation instead of retrying blindly.

## 9. Circuit Breaker: Stopping Calls to Failing Dependencies

A circuit breaker tracks errors or timeouts and temporarily blocks new calls to a dependency when thresholds are breached.

Three common states:

- **Closed:** allows requests through and monitors results.
- **Open:** fails fast or returns a fallback during a cooldown period.
- **Half-open:** lets a few probe requests through to check if the dependency has recovered.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error/timeout threshold exceeded
    Open --> HalfOpen: Cooldown elapsed
    HalfOpen --> Closed: Probe succeeds
    HalfOpen --> Open: Probe fails
~~~

Circuit breakers prevent holding threads and connections waiting on an already broken dependency. However, thresholds and windows must be tuned carefully. Too sensitive causes false opens on brief error bursts; too loose allows the system to keep amplifying load.

Circuit breakers do not replace retry policies, timeouts, or bulkheads. These mechanisms work together to protect different layers.

## 10. Load Shedding and Graceful Degradation

When a system nears capacity, continuing to accept every request can cause all functions to collapse together. **Load shedding** proactively rejects or drops part of the load to protect the rest. **Graceful degradation** allows the system to provide a reduced yet still useful set of features.

Example of an equipment rental platform:

| Feature | Under overload | Degradation policy |
| --- | --- | --- |
| Payment confirmation | High priority | Reserve dedicated capacity; return pending state when needed |
| Create booking | High priority | Controlled rate limiting; never confirm unless committed |
| View order history | Medium priority | Read from cache/replica with published freshness |
| Product recommendations | Deferrable | Disable or return default content |
| Send email | Asynchronous | Retain in queue and send later |
| Large reports | Low priority | Defer or reduce concurrency |

A degradation mechanism must define which data may be stale, which operations are disabled, and which statuses are returned to users. Never fake success or show incorrect default results for critical transactions.

## 11. Admission Control and Resource Limits

Admission control decides whether to accept additional work based on current capacity and policy. It acts before queues, executors, or databases fill up.

Limits to consider:

- Maximum request rate per tenant/API key.
- Maximum concurrent requests per service.
- Connection pools and query concurrency for databases.
- Maximum inflight messages and queue depth.
- CPU/memory limits for workloads.
- External API quotas.
- Maximum job duration and payload size.
- Priority quotas and reserved capacity for critical tasks.

When rejecting, return appropriate errors and retry guidance such as 429/503 with `Retry-After` if possible. For message producers, brokers/consumers need clear retry and dead-letter semantics. Never return accepted before work is durably persisted as committed.

### 11.1. Avoiding Cascading Resource Exhaustion

One API request may trigger 10 downstream calls. Receiving 1,000 concurrent requests can generate 10,000 calls to dependencies. Limit fan-out, batch sizes, concurrency, and retry counts along the entire path; rate limiting only at the gateway is not enough.

## 12. Tenant Isolation and Noisy Neighbors

In multi-tenant SaaS, a large or misconfigured tenant can consume resources needed by other tenants. This is a workload-level blast radius.

Countermeasures:

- Request, storage, compute, and job quotas per tenant.
- Concurrency limits and fairness policies.
- Partitioned queues or dedicated queues based on required isolation.
- Rate limits for exports, reports, and bulk operations.
- Always scope cache keys and database queries with tenant context.
- Limit connections and long-running queries per tenant.
- Alert on anomalous usage and throttle automatically.
- Tiered isolation for tenants with high compliance or SLO requirements.

Dedicated infrastructure is not required for every tenant. Shared infrastructure with quotas is often more efficient, while tenants with massive workloads or strict isolation needs may require dedicated cells/databases/clusters.

## 13. Cell-Based Architecture

**Cell architecture** splits a large system into multiple relatively independent deployment units. Each cell serves a subset of tenants or data partitions and contains its own compute, queues, databases, and quotas within the cell boundary.

~~~mermaid
flowchart TB
    G["Global routing / tenant directory"] --> C1["Cell A"]
    G --> C2["Cell B"]
    G --> C3["Cell C"]
    subgraph CELL_A["Failure boundary A"]
        C1 --> A1[("App + DB + Queue A")]
    end
    subgraph CELL_B["Failure boundary B"]
        C2 --> B1[("App + DB + Queue B")]
    end
    subgraph CELL_C["Failure boundary C"]
        C3 --> C1DB[("App + DB + Queue C")]
    end
~~~

If cell B fails, tenants in cell B may be affected while cells A and C continue operating. Global routing and the tenant directory remain shared dependencies that must be designed for HA/cached fallback; if they break, independent cells can still be impacted during tenant lookup.

### 13.1. Cell Sizing Criteria

Cells can be partitioned by:

- Target number of tenants per cell.
- Total workload and quotas.
- Region/data residency.
- Tenant tier/SLO.
- Data partition or tenant hash.
- Maximum blast radius acceptable to the organization.

Cells that are too large expand blast radius; cells that are too small increase cost, operational overhead, and resource inefficiency. Tenant count is not the only criterion: ten large tenants can generate more load than thousands of small ones.

### 13.2. Cell Independence

A cell is only independent if it can serve committed functions when global dependencies degrade. Consider auth/token validation, config caches, tenant mapping, secrets, observability ingestion, deployment control, and data replication. You do not need to duplicate every control plane, but you must separate runtime-required capabilities from admin-only capabilities.

## 14. Data Boundaries and Replication Failures

Databases and storage can create large blast radii if multiple services or tenants share tables, schemas, or clusters without resource guardrails.

Define clearly:

- Data ownership by domain/tenant.
- Transaction boundaries and invariants.
- Connection/query quotas.
- Partition/shard or database-per-tenant where appropriate.
- Replication topology and lag tolerance.
- Backup/restore boundaries.
- Failover/fencing and promotion authority.
- Behavior when storage or the data plane fails.

Replication does not replace backups. If an accidental deletion is replicated, replicas may delete the data too. If a replica lags, failing over to it can lose unshipped data. Architecture needs matching RPO/RTO targets and recovery tests.

### 14.1. Do Not Expand Blast Radius with Cross-Domain Transactions

A synchronous transaction spanning multiple databases or services creates tight coupling. When one dependency slows down, all participants can hold resources. For long-running flows, consider sagas/workflows, intermediate states, and compensation. However, compensation is a new business action, not a clean ACID rollback.

## 15. Shared Control Plane and Data Plane

Cloud and SaaS systems typically have a **control plane** for provisioning, configuration, authorization, and deployment; and a **data plane** for handling business requests. A control plane outage should not necessarily halt the data plane.

For example, if the control plane managing features/config is unavailable, runtime can continue using the latest validated config version for a period. However, if a policy involves revoking access permissions, keeping stale config may be unsafe.

For each config type, specify:

- How long can last-known-good be used?
- Should it fail-open or fail-closed?
- Which changes must take effect immediately?
- Are local caching and signatures/versions required?
- How does recovery work when the config store returns?
- How do you avoid thundering herds when many instances refresh simultaneously?

Do not apply a single fallback policy across branding, entitlements, and security policies.

## 16. Deployments, Config Changes, and Human Error

Blast radius often stems more from software/config changes than hardware failures. A buggy release rolled out to all tenants simultaneously can cause a widespread outage even while multi-zone infrastructure stays healthy.

Mitigation mechanisms:

- Canary deployments and progressive rollouts.
- Feature flags with owners, expiry, and kill switches.
- Deployments by cell/cohort.
- Automated health gates and stop conditions.
- Expand–migrate–contract for schemas.
- Config validation and staged publication.
- Rehearsed rollbacks/forward-fixes.
- Separation of duties for sensitive changes.
- Immutable artifacts and release metadata.
- Rollout velocity limits to avoid simultaneous impact.

Application rollbacks do not always reverse database migrations or written data. Backward compatibility and forward-fix plans are essential.

## 17. Recovery Strategy: Recover Within Which Boundary?

When failure strikes, you must know whether to recover in place, shift traffic, promote a replica, or fail over an entire region. Choose the strategy based on root cause and failure scope.

| Failure scope | Common strategies to consider | What to verify |
| --- | --- | --- |
| A process/container | Restart/replace instance | Startup, readiness, and idempotent jobs |
| A service version | Rollback/stop canary | Schema and data compatibility |
| A host/zone | Reschedule or fail over to another zone | Capacity, subnets, data quorum |
| A database node | Failover/promote per engine | Replication lag, fencing, unknown commits |
| A cell | Reroute tenants or restore cell | Tenant directory, data ownership, and RTO |
| A region | DR failover or shard-based failover | RPO, DNS/routing, data residency |
| An external dependency | Degrade, queue, or manual process | Business state and reconciliation |

Do not shift traffic elsewhere if the target lacks up-to-date data, necessary credentials, or sufficient capacity. Automated failover without proper preconditions can worsen an outage.

## 18. Measuring Blast Radius and Reliability

Aggregate availability metrics can hide severe impacts on a subset of tenants or a specific feature. Measure across multiple dimensions.

| Metric | Question |
| --- | --- |
| Affected request percentage | How many requests failed/timed out during the incident? |
| Affected tenant count | How many tenants were impacted and across which tiers? |
| Affected cell/zone/region | Did the incident cross boundaries? |
| Dependency fan-out | How many downstream calls does one request generate? |
| Error rate by dependency | Which dependency is propagating errors? |
| Queue age/backlog | Where is delayed work piling up? |
| Resource saturation | At which boundary are connections, CPU, memory, threads, or disk exhausted? |
| Recovery time | How long does it take to restore critical functions? |
| Data loss/duplication | Were transactions lost, duplicated, or in need of reconciliation? |
| Error budget burn | How fast is the SLO budget being consumed? |

Tracking by tenant, cell, region, and operation helps detect noisy neighbors and partition-specific failures. Avoid logging sensitive payloads just to measure blast radius; controlled metadata and identifiers usually suffice.

## 19. SLOs, Error Budgets, and Degradation Policies

SLOs should tie to user journeys, not just CPU or health checks. For example:

- 99.9% of booking creation requests are processed accurately within the target window.
- 99% of payments reach a deterministic outcome or a queryable pending state.
- 99.5% of tenants remain unaffected by a failure in another cell.
- After losing a zone, core functions recover within the target time.
- Notification jobs may be delayed but are never lost once durably acknowledged.

Error budgets help guide release velocity and reliability work prioritization. When the budget burns fast, the organization can pause risky rollouts, reduce changes, or focus on eliminating incident sources.

Explicitly state which features may degrade and which data may be stale. For example, recommendations can be disabled to protect booking; you cannot flip a payment state from unknown to failed just to give the UI a fast response.

## 20. Chaos Engineering and Failure Injection

Chaos engineering tests reliability hypotheses by injecting controlled failures under observable conditions. The goal is to uncover propagation paths and verify containment mechanisms.

Example experiments:

- Terminate an application instance.
- Inject latency or return errors from a dependency.
- Sever connectivity to a test replica or zone.
- Fill up queues in a test environment.
- Constrain database connections.
- Revoke simulated credentials.
- Deploy a bad config to a test cohort.
- Kill a worker mid-batch to test ack/checkpoint behavior.
- Simulate DNS/network degradation.

Before testing, define the hypothesis, scope, allowable blast radius, guardrails, abort mechanisms, and success criteria. Never start by injecting wide-scale production failures without proper controls and approvals.

### 20.1. Game Days

A game day is a scripted exercise with defined participants: facilitator, operators, observers, and business representatives. Measure detection time, decision time, recovery time, and internal communication quality; document gaps in runbooks and automation.

Do not declare a chaos experiment successful just because the system did not crash. The application might still return responses while violating latency, error budgets, or data correctness.

## 21. Design Example: Multi-Tenant Rental Booking Platform

Suppose a platform serves 3,000 tenants with booking, payment, inventory, notification, and analytics features. One large tenant runs reports and data exports during peak hours. An outage at the notification provider must never block customers from booking rentals.

### 21.1. Proposed Boundaries

- Partition tenants into cells by region and capacity; large tenants receive dedicated quotas or cells per SLO/contract.
- Booking and payment have reserved capacity, dedicated pools, and dedicated timeouts.
- Inventory enforces concurrency control over authoritative data.
- Notifications flow through a durable queue and rate-limited worker group.
- Analytics/exports run on a separate data platform with per-tenant quotas.
- Global routing/tenant directory uses HA, local versioned caches, and recovery procedures.
- Observability breaks down by tenant, cell, dependency, and operation.

~~~mermaid
flowchart TB
    U["Clients"] --> G["Global routing / tenant directory"]
    G --> CA["Cell A"]
    G --> CB["Cell B"]
    G --> CC["Cell C"]
    subgraph CELL_A["Cell A"]
        CA --> BA["Booking + Payment"]
        CA --> QA["Notification queue"]
        BA --> DBA[("Cell A data")]
        QA --> WA["Notification workers"]
    end
    subgraph CELL_B["Cell B"]
        CB --> BB["Booking + Payment"]
        CB --> QB["Notification queue"]
        BB --> DBB[("Cell B data")]
        QB --> WB["Notification workers"]
    end
    subgraph CELL_C["Cell C"]
        CC --> BC["Booking + Payment"]
        CC --> QC["Notification queue"]
        BC --> DBC[("Cell C data")]
        QC --> WC["Notification workers"]
    end
    X["Analytics platform"] -. "CDC / controlled export" .-> DBA
    X -. "CDC / controlled export" .-> DBB
    X -. "CDC / controlled export" .-> DBC
~~~

The diagram illustrates a sample topology. Actual database, queue, or cell splits depend on cloud provider capabilities, tenant placement, and cost. The key point is that export/notification work does not share unbounded resources with the booking/payment critical path.

### 21.2. Failure Scenarios

| Incident | Bounded scope | Desired behavior |
| --- | --- | --- |
| Tenant C runs oversized export | Tenant or cell C export quota/workers | Throttle export; bookings for other tenants continue |
| Notification provider outage | Notification workers/queue | Bookings still commit; notifications wait to be sent |
| A cell database loses connectivity | Corresponding cell | Tenants in other cells continue; failed cell recovers per runbook |
| Config service slows down | Config lookup path | Use last-known-good config per policy |
| Global routing fails | Tenant resolution path | Cached mappings and safe fallback; never misroute tenants |
| Payment provider times out | Payment operation | Pending/unknown state, idempotency, and reconciliation |

### 21.3. Acceptance Criteria

1. Overload tenant C exports; confirm booking and payment pools/queues are not exhausted.
2. Stop notification workers; confirm bookings commit and the queue retains messages durably.
3. Simulate database loss in one cell; confirm other cells do not suffer the same failure.
4. Make the config service unavailable; confirm which policies use cache and which fail closed.
5. Slow down global routing; confirm tenant context is never mis-mapped.
6. Disconnect payment at commit time; confirm idempotency and reconciliation.
7. Measure affected tenants/requests, queue age, latency, error rate, and recovery time.

## 22. Fault Containment Design Process

1. **Identify critical journeys:** booking, payment, login, search, notification, and reporting.
2. **Map the dependency graph:** synchronous, asynchronous, shared resources, external services, and control planes.
3. **List failure domains:** host, zone, region, DB, queue, tenant, cell, and human factors.
4. **Define acceptable blast radius:** max impacted tenants/requests/data and degradation duration.
5. **Choose boundaries:** process, pool, queue, cell, account/project, database, or region based on isolation value.
6. **Set quotas and admission control:** connections, concurrency, request rate, memory, storage, queues, and tenants.
7. **Design for failure:** timeouts/deadlines, circuit breakers, retries, load shedding, and graceful degradation.
8. **Design data recovery:** replication, backups, RPO/RTO, fencing, and reconciliation.
9. **Design rollouts:** canaries, cell-based deployment, config validation, and rollbacks.
10. **Establish observability:** metrics by tenant/cell/zone/dependency and error budgets.
11. **Rehearse:** dependency outages, zone loss, noisy neighbors, full queues, config errors, and restores.
12. **Update runbooks:** owners, triggers, escalation, stop conditions, and recovery evidence.

## 23. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Deploying multi-zone without checking dependencies | Database, DNS, or identity remains a shared failure point | Map and test the dependency graph |
| Using unbounded shared pools | One workload exhausts connections for the whole system | Apply bulkheads and quotas per workload |
| Retrying every failure immediately | Retry storms and outage amplification | Timeouts, backoff, jitter, and retry budgets |
| No end-to-end deadlines | Requests hold resources across tiers too long | Propagate deadlines and cancel work |
| Falling back to stale cache for all dependencies | Sensitive decisions rely on stale policy/state | Classify fail-open/fail-closed by business risk |
| Scaling infinitely as queues grow | Overloads downstream systems | Admission control and capacity-aware scaling |
| No per-tenant quotas | Noisy neighbors degrade other tenants | Fairness and usage limits |
| Cells share too many control dependencies | Global outage still impacts all cells | Design cached/local capabilities and recovery |
| Promoting replicas without freshness/fencing checks | Data loss or split brain | Failover runbooks and candidate criteria |
| Rolling out to all tenants at once | One bad release creates platform-wide blast radius | Canaries/cohorts and stop conditions |
| Degrading without clear semantics | UI shows wrong info or fake business confirmations | Contracts for stale/partial/unavailable states |
| No rehearsals | Runbooks, automation, and RTO exist only on paper | Game days and guarded failure injection |
| Measuring only aggregate availability | Outages for one cell/tenant stay hidden | Metrics per tenant, cell, region, and operation |

## 24. Well-Architected Review

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Are failure domains clear? Is loss of a zone/tenant/dependency contained? Are bulkheads, failovers, backups, and recovery tests in place? |
| **Security** | Are tenant, secret, network, and admin boundaries isolated? How many workloads can a compromised credential reach? |
| **Performance Efficiency** | Are timeouts, concurrency, connections, and queues bounded? Can a slow dependency cascade latency? |
| **Cost Optimization** | Does isolation level match SLOs? Do dedicated cells/replicas have reasonable utilization? Are overprovisioning and retry waste avoided? |
| **Operational Excellence** | Are there dependency maps, blast radius metrics, runbooks, canaries, game days, and owners for each boundary? |

### Acceptance Checklist

- [ ] Failure domains and fault containment boundaries are mapped across infrastructure and business journeys.
- [ ] Blast radius is quantified by tenants, requests, features, data, and duration.
- [ ] Shared dependencies and shared resources have owners, quotas, health signals, and fallbacks.
- [ ] Critical workloads have protected pools, concurrency, and capacity.
- [ ] Timeouts/deadlines propagate through the call chain; retries are bounded and idempotent.
- [ ] Circuit breakers, load shedding, and graceful degradation have clear semantics.
- [ ] Tenant/cell isolation prevents noisy neighbors and cross-tenant impact.
- [ ] Multi-zone/region topologies have enough compute, data, network, and dependencies for failover.
- [ ] Failover defines candidate criteria, fencing, RPO/RTO, and reconciliation.
- [ ] Deployment/config changes have canaries, stop conditions, and rollback/forward-fix plans.
- [ ] Config/identity fallbacks are classified fail-open/fail-closed by risk level.
- [ ] Dashboards measure error rate, latency, saturation, queue age, and affected tenants per boundary.
- [ ] Failure injection/game days cover critical scenarios.
- [ ] Runbooks specify owners, escalation, stop conditions, and recovery evidence.

## 25. Applied Exercise

A SaaS platform serves 1,200 enterprises across three regions. Each tenant uses booking, payment, notification, and reporting. Databases are shared per region; a group of large tenants frequently runs bulk exports. Notifications use an external provider. The operations team wants other tenants to continue creating and managing bookings when one tenant or one zone experiences an outage.

Design:

1. What are the failure domains across host, zone, region, database, queue, tenant, and service?
2. Which shared components could create a region-wide blast radius?
3. What bulkheads/quotas are needed for booking, payment, notification, and export?
4. When should you choose a shared database with quotas, database sharding, or dedicated cells?
5. Design fallbacks when the identity/config service is unavailable; which policies fail open and which fail closed?
6. When the notification provider fails, how do booking state and the notification queue behave?
7. When a zone is lost, how do compute, database, network, and tenant routing recover?
8. How would you set RPO/RTO and SLOs for booking/payment, notification, and reporting?
9. How do you test noisy neighbors and determine actual blast radius?
10. Which metrics prove that a failure in one tenant/cell does not spread to other tenants?

A sound approach can start with per-tenant quotas, separate pools/queues for critical workloads, asynchronous notifications, and throttled exports. When a group of tenants generates heavy load or requires strong isolation, move them into dedicated cells/databases by cohort. Multi-zone designs must include data and network failover, while multi-region should only be chosen when RPO/RTO and data residency justify the cost and complexity.

**Core Takeaway:** Reliability does not come solely from having replicas in multiple locations; it also comes from keeping failures confined within a small domain. Define failure domains, cap shared resources, isolate tenants and workloads, design graceful degradation, and verify through rehearsals. The more clearly blast radius is measured and bounded, the more likely the system is to keep serving most users when a component fails.
