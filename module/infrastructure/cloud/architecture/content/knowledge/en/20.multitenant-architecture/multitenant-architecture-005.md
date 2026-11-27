# Preventing Noisy Neighbors with Quotas and Resource Allocation

## 1. Noisy Neighbors Are a Resource-Sharing Problem

In a multi-tenant architecture, many tenants share compute, databases, caches, networks, queues, object storage, or search clusters. Sharing boosts resource utilization and reduces cost, but one tenant experiencing a traffic spike or abnormal behavior can consume most of the shared capacity. Other tenants then see elevated latency, request timeouts, queue backlogs, or errors even though their own load did not increase.

This phenomenon is commonly called a **noisy neighbor**. The cause is not necessarily a malicious tenant; a large data import, heavy report, broken retry loop, or successful marketing campaign can also generate demand beyond projections.

The architectural goal is **controlled sharing**: each tenant gets resource entitlements matching their service tier/policy; the platform protects shared capacity; a high-load tenant does not break other tenants' SLOs; and critical work can still proceed while load is being throttled.

In the **CLOUD_ARCHITECTURE** module, this ties into compute, networking, data, and deployment models. Designs must balance **reliability, security, performance, scalability, cost, and operations** through a Well-Architected lens.

Running example: a booking SaaS platform has thousands of tenants. Each tenant manages properties, bookings, users, and reports. Tenant A starts importing hundreds of thousands of records and running full-year reports; if all requests share a single connection pool and worker pool, Tenant B may fail to log in or look up bookings.

## 2. Distinguishing Quota, Rate Limit, Concurrency, and Resource Allocation

| Mechanism | What It Limits | Example |
| --- | --- | --- |
| Quota | Total usage within a billing period/plan | 100,000 API calls/day, 500 GB storage |
| Rate limit | Rate of requests/operations over a window | 20 requests/second per tenant |
| Burst allowance | Short-term spike volume accepted | Burst of 50 requests before throttling |
| Concurrency limit | Number of operations running simultaneously | Max 5 heavy reports per tenant |
| Resource reservation | Guaranteed or dedicated capacity | Minimum 2 worker slots for priority tenants |
| Resource cap | Maximum a tenant can consume | No more than 4 vCPUs or 8 active jobs |
| Fair scheduling | Rules dividing capacity under contention | Weighted fair queueing by tenant weight |
| Admission control | Deciding whether to accept, defer, or reject new work | Reject new jobs when the database is saturated |

A tenant can stay under its monthly quota yet still cause noisy-neighbor issues by firing a massive burst of requests within seconds. Conversely, a steady tenant might hit its total quota without ever creating instantaneous load spikes. Therefore, you must combine **cumulative quotas, rate limits, concurrency limits, and capacity allocation**.

## 3. Identifying Resources to Protect

Fair limits cannot be set by counting HTTP requests alone. A cache read differs drastically in cost from a report export, complex search, or large file import.

| Resource | Contention Type | Suitable Metrics |
| --- | --- | --- |
| API gateway/compute | CPU, threads, connections, request bursts | RPS, CPU time, active requests, p95/p99 |
| Database | Connection pools, IOPS, CPU, locks, transactions | Query time, active connections, rows scanned, lock waits |
| Cache | Memory, hot keys, network, evictions | Memory per tenant/keyspace, hit ratio, ops/s |
| Queue/worker | Consumer slots, backlogs, execution time | Queue age, job count, worker-seconds, retries |
| Search | Query complexity, shards, aggregations | Query latency, shard work, bytes/rows examined |
| Object storage | Capacity, requests, listings, egress | GB, PUT/GET/LIST, bytes transferred |
| Network | Bandwidth, cross-region traffic, egress | Bytes/s, connection count, transfer cost |
| External providers | API quotas, concurrency, transaction fees | Calls, throttling, latency, provider quotas |

Measure meaningful consumption units rather than treating every request as one cost unit. For example: basic search equals 1 search unit; multi-dimensional aggregation equals 5 units; export jobs equal worker-seconds; storage equals GB-months; egress equals GB transferred. This is an internal metering model that must be calibrated from real data and does not necessarily mirror exact cloud bills.

## 4. Building Per-Tenant Quota Policies

Quotas should reflect service agreements and platform capacity. A policy typically defines base allowance, burst allowance, hard caps, concurrency caps, priority, overage behavior, and reset periods.

| Limit | Starter | Business | Enterprise |
| --- | ---: | ---: | ---: |
| API read calls/day | 20,000 | 200,000 | Per contract |
| Burst read RPS | 5 | 30 | Configured |
| Concurrent export jobs | 1 | 3 | Per pool/quota |
| Storage | 20 GB | 200 GB | Per contract |
| Concurrent import jobs | 1 | 2 | Can be dedicated |

These numbers are illustrative only. Never assume Enterprise tenants get unlimited resource consumption; every plan still needs platform-wide guardrails. A single aggregate quota is easy to understand but fails to reflect cost differences across API reads, exports, imports, and webhooks. Combine periodic quotas, per-route rate limits, concurrency caps for heavy jobs, storage/egress quotas, and hard safety caps.

## 5. Rate Limiting and Burst Control

| Algorithm | How It Works | Trade-offs |
| --- | --- | --- |
| Fixed window | Counts requests in a fixed window | Can burst across window boundaries |
| Sliding window | Calculates traffic over a sliding window | More accurate depending on implementation, higher state cost |
| Token bucket | Tokens refill at a steady rate; requests consume tokens | Allows bounded bursts |
| Leaky bucket | Drains work at a steady output rate | Smooths load but can increase wait time |

Token bucket example: refill rate 10 tokens/second, bucket capacity 30 tokens, each request consumes 1 token. A tenant can send bursts up to bucket capacity; over the long term, average throughput is capped by the refill rate. More expensive requests can consume more tokens if a validated cost model exists.

Rate limits can apply simultaneously per tenant, per user/API key, per route, by IP/source signals, and platform-wide. Limits must coordinate in a clear order. For HTTP APIs, `429 Too Many Requests` is appropriate when a caller exceeds rate limits; return `Retry-After` or reset times. When the entire system lacks capacity, `503 Service Unavailable` may fit better. Clients need backoff, jitter, retry limits, and idempotency for writes.

## 6. Concurrency Limits, Queues, and Admission Control

Rate limits control how fast operations start; concurrency limits control how many jobs consume resources at the same time. A tenant sending 2 requests/second where each runs for 60 seconds creates 120 concurrent tasks. Even a low rate can exhaust a connection pool without a concurrency cap.

| Category | Example | Appropriate Limits |
| --- | --- | --- |
| Interactive API | Reading bookings, looking up profiles | Short-lived rate and concurrency caps, latency-sensitive |
| Search | Search, filtering, aggregations | Cost-weighted rate, timeouts, complexity caps |
| Batch import | Importing property lists | Job concurrency, file size, worker-seconds |
| Export/report | Reports, large file generation | Concurrent job count and queue capacity |
| Webhook | Partner events | Dedicated limits, retry policies, and dead-letter queues |
| Admin operations | Bulk updates, tenant reindexing | Role-based admission and maintenance windows |

Queues can absorb bursts, but must not be unbounded. If arrival rate persistently exceeds processing rate, backlog and job age grow indefinitely. Set maximum queue depth/bytes, maximum queue age, per-tenant pending-job caps, total worker/concurrency limits, and queue-full behavior.

The admission controller decides whether to accept work based on system health and tenant policy. For example, accept new exports only when active workers are below threshold, the database retains headroom, and the tenant is below its concurrency cap. When unable to accept, return a clear response and avoid creating orphaned job records.

## 7. Fair Resource Allocation

Quotas define how much a tenant is permitted to consume; schedulers/fair allocators decide who gets resources under contention.

| Strategy | Allocation Method | When Suitable | Limitations |
| --- | --- | --- | --- |
| First-come, first-served | Processed in arrival order | Low load, simple demands | High-volume tenants can monopolize the queue |
| Equal share | Each active tenant gets an equal share | Tenants with similar needs | Does not reflect service tiers |
| Weighted fair sharing | Divided by tenant weight | Differentiated service plans | Must manage weights and prevent starvation |
| Reserved capacity | Capacity set aside for a tenant/workload group | High SLOs or dedicated commitments | Can create idle capacity |
| Best-effort pool | Uses remaining spare capacity | Non-time-sensitive batch/reports | Can be delayed |
| Dedicated pool | Separates nodes/workers/databases per tenant | Strong isolation | Increases cost and fragments capacity |

Suppose Tenant A has weight 1, B weight 2, and C weight 1 in a worker pool. When all three have backlogs, target processing shares can follow a `1:2:1` ratio. This is a distribution target, not a second-by-second exact guarantee; real implementations must account for varying job execution times. Measure worker-seconds or cost units rather than just counting messages.

To prevent starvation, use weighted fair scheduling, deficit round robin, aging (raising priority as jobs wait longer), reserved minimum shares, caps on concurrent high-priority jobs, and deadline-aware scheduling.

## 8. Partitioning Resources to Reduce Blast Radius

~~~mermaid
flowchart TB
    T1["Tenant A"] --> G["Admission / Quota / Scheduler"]
    T2["Tenant B"] --> G
    T3["Tenant C"] --> G
    G --> S["Shared worker pool"]
    G --> P["Reserved pool: Premium"]
    G --> D["Dedicated pool: Large tenant"]
    S --> DB["Shared DB / Cache"]
    P --> DB
    D --> DDB["Isolated DB / Cache when needed"]
~~~

- **Shared pool:** multiple tenants share compute/databases/caches; optimizes cost, requires strong quotas and fairness.
- **Segmented pool:** tenants are grouped into pools by region, plan, workload, or risk; limits blast radius.
- **Dedicated pool:** one tenant or small group gets its own compute/data plane; stronger isolation, but increases cost, automation overhead, and capacity fragmentation.

You do not need to dedicate an entire stack for every large tenant. You can isolate just the contended import workers, search shard, or connection pool.

### 8.1. Protecting Databases, Caches, and Queues

A tenant running slow queries can hold connections open for a long time. Limit query concurrency per tenant/workload, enforce connection pool timeouts, statement duration/rows-scanned limits, offload analytics to read replicas/warehouses, and monitor connection/lock waits. Do not create separate physical pools for every tenant if tenant count is huge; total connections can exceed database limits.

Cache keys must include tenant context when data differs; memory quotas/evictions must prevent one tenant from evicting everyone else's cache. Search queries need caps on aggregations, page size, wildcards, and timeouts. Queues need per-tenant backlog caps and fairness; workers enforce per-tenant concurrency slots.

## 9. Soft, Hard, and Adaptive Limits

| Type | Behavior | Example |
| --- | --- | --- |
| Soft quota | Warns or bills overage without immediate rejection | Storage approaching limit |
| Hard quota | Rejects or blocks exceeding operations | Rejects uploads once storage cap is reached |
| Burst quota | Allows brief exceedance over baseline | Token bucket |
| Adaptive limit | Adjusts based on capacity and system health | Lowers export concurrency as DB saturation rises |
| Emergency system cap | Protects the entire platform regardless of tenant plan | Halts heavy jobs when infrastructure saturates |

Adaptive limits must not arbitrarily violate service commitments tenants purchased. Clearly distinguish product-level limits from incident protection measures, and define how degraded states are communicated.

## 10. Detecting Noisy Neighbors with Telemetry

To isolate the right tenant, telemetry must carry trusted tenant context. Never rely solely on client-sent tenant IDs; determine identity from verified authentication and propagate context through gateways, services, jobs, and database instrumentation.

| Group | Metric |
| --- | --- |
| Request | RPS, active requests, 429/503s, timeouts, p95/p99 by tenant and route |
| Compute | CPU time, memory, worker-seconds, thread/connection occupancy |
| Database | Query count/duration, rows scanned, lock waits, connection waits |
| Queue | Pending jobs, oldest job age, processing rate, retries, DLQs |
| Search | Query cost, shard work, aggregation buckets, timeouts |
| Storage/network | Bytes stored, request counts, egress, upload/download rates |
| Quota | Used, remaining, reset time, burst consumption, cap events |
| Fairness | Actual share vs. weight/reservation and queue wait time |

Tenant A having 10x the median tenant's RPS is not necessarily a noisy neighbor if its service plan and allocated capacity allow it. Look at **actual resource consumption relative to allowance, impact on shared resources, and impact on other tenants' SLOs**.

~~~text
tenantUtilizationRatio = measuredResourceUnits / allocatedResourceUnits
sharedPoolPressure = observedDemand / safePoolCapacity
~~~

These are conceptual ratios. Avoid collapsing CPU, I/O, network, and query cost into a single composite score without grounded weights. Keep per-resource metrics so you can pinpoint the exact bottleneck.

## 11. Fairness Does Not Mean Equal Outcomes for Every Tenant

Fairness must align with service agreements and consumption behavior. Tenants paying for higher throughput can receive higher weights; however, a large tenant must never erode the platform's minimum safety headroom.

Policies should distinguish entitlements (committed usage rights), actual usage, system safety caps, priority, overage, and isolation tiers. If a customer exceeds usage due to a platform bug such as an API retry storm, metering should distinguish system retries, internal tasks, and user actions where billing policies require.

## 12. Example Quota and Allocation Policy

The following illustrative policy expresses intent and is not a vendor-specific schema:

~~~yaml
tenantPolicy:
  plan: business
  limits:
    apiRead:
      sustainedPerSecond: 20
      burst: 60
    export:
      concurrentJobs: 2
      maxRowsPerJob: 500000
    import:
      concurrentJobs: 1
      maxFileSizeMB: 250
    storage:
      softLimitGB: 180
      hardLimitGB: 200
  scheduling:
    workerWeight: 2
    minimumSharePercent: 5
    bestEffortBurst: true
  behavior:
    rateExceeded: reject_with_retry_after
    concurrencyExceeded: enqueue_if_capacity
    hardQuotaExceeded: reject_and_explain
~~~

These numbers and field names are for learning purposes only. Production systems must define units, reset periods, cost calculations, multi-region concurrency, authoritative policy sources, and quota update propagation so instances do not enforce divergent policies for long.

## 13. Failure Modes of Quota Systems

Resource limiters are themselves critical dependencies. If a limiter fails, the system might swing wide open or reject every tenant.

| Failure Mode | Risk | Design Direction |
| --- | --- | --- |
| Quota store unavailable | Unable to determine usage | Local safety limits, versioned cached policies, and timeouts |
| Counter data loss | Tenants exceed quotas | Reconciliation, durable counters, or secondary limits |
| Counter double-counting | Tenants blocked unfairly | Idempotency keys, atomic increments, or event deduplication |
| Multi-region inconsistency | Regions collectively exceed total quota | Per-region quota slices or appropriate coordination |
| Policy rollout skew | Instances enforce different thresholds | Versioned policies, staged rollouts, and telemetry |
| Increased limiter latency | Every request stalls on the quota service | Local token buckets, batching, or async metering |
| Reset boundary race | Bursts at window transitions | Sliding windows/token buckets and boundary tests |
| Admin misconfiguration | Tenants locked out or over-consuming | Validation, audits, dry-runs, rollbacks |

### 13.1. Fail-Open or Fail-Closed?

There is no universal choice. For low-sensitivity read APIs, local safety caps with bounded fail-open can preserve availability. For operations carrying high cost or data risk, fail-closed or allowing only a protective baseline allowance may be safer. Decide based on resource type, business impact, and local measurement capability.

## 14. Security and Preventing Quota Abuse

Quotas are not an authentication mechanism. Attackers can create multiple accounts/API keys to spread usage or spoof tenant IDs if the system trusts request headers.

- Tenant context is verified from identity and membership.
- API keys/tokens are bound to scoped tenants/clients with rotation and revocation.
- Never allow clients to modify plans, weights, or quotas themselves.
- Rate-limit pre-authentication by IP/risk signals and post-authentication by tenant/user.
- Audit quota increases, plan changes, burst grants, and telemetry access.
- Separate platform admin permissions from tenant admin permissions.
- Never expose another tenant's usage or quota status.
- Batch job service identities must also carry trusted tenant/actor context.

## 15. Incident Workflow When Detecting a Noisy Neighbor

~~~mermaid
flowchart TD
    A["Detect shared resource pressure / SLO regression"] --> B["Identify consuming tenant, route, and resource"]
    B --> C{"Policy breach or insufficient system capacity?"}
    C -->|Tenant exceeds limit| D["Apply rate/concurrency limit or queue"]
    C -->|Insufficient capacity| E["Scale, optimize, or move workload pool"]
    D --> F["Measure impact on other tenants and throttled tenant"]
    E --> F
    F --> G{"SLO recovered?"}
    G -->|No| B
    G -->|Yes| H["Document, tune quotas and capacity plan"]
~~~

Runbooks should cover: verifying SLO degradation and shared resource saturation; identifying the tenant/workload via verified telemetry; checking whether the tenant exceeded its allowance or platform capacity fell short; applying the least-disruptive mitigation; notifying per API contracts; measuring SLOs for both throttled and unaffected tenants; restoring normal policies post-incident; and following up on queries, quotas, pools, capacity, or retries.

Never automatically label a tenant abusive based solely on request rate; it could be an application bug or legitimate campaign. Classify root cause before enforcing contractual sanctions.

## 16. Capacity Planning and Reserve Allocation

If infrastructure has 100 worker slots, never allocate all 100 as hard tenant reservations. Reserve capacity for system workloads, incidents, rollouts, bursts, and recovery.

~~~text
Total worker capacity:       100 slots
Platform/system reserve:      10 slots
Premium reserved capacity:    20 slots
Shared fair-use pool:          60 slots
Best-effort burst headroom:    10 slots
~~~

Pools can borrow idle capacity per policy; unused reserved capacity can be lent to the shared pool as long as it can be reclaimed when owning tenants need it. This requires safe preemption or priority scheduling—never abruptly kill jobs that already produced partial side effects.

As large tenants grow, adjust quotas/weights after measuring demand; optimize queries/imports/exports; move heavy workloads to suitable queues/pools; split out contended search shards/databases/caches; or move to dedicated pools when isolation benefits justify the cost. Never raise quotas indefinitely to mask inefficient queries.

## 17. Practice Exercise: Preventing Noisy Neighbors on a SaaS Platform

**Hypothetical Context:** A platform has 2,000 tenants, 30,000 peak requests/second, shared PostgreSQL, Redis, a search cluster, and a worker pool. Tenant A runs a massive import and 10 concurrent reports; Tenant B sees API latency spike fivefold. Numbers are solely for exercise purposes, not default benchmarks.

### Tasks

1. Build a resource map covering APIs, DB, cache, search, queues, workers, storage, and network.
2. Classify at least five workloads by cost and priority level.
3. Design cumulative quotas, rate limits, burst caps, concurrency caps, and hard system caps for each plan.
4. Choose a fair scheduling strategy for the worker pool; explain how to prevent tenants with long-running jobs from hogging all slots.
5. Propose per-tenant limits for DB queries/connections, search complexity, cache memory, and queue backlogs.
6. Design shared, segmented, and dedicated pools; define thresholds for moving large tenants to dedicated pools.
7. Build a dashboard to detect noisy neighbors and distinguish quota violations from insufficient platform capacity.
8. Design behavior for quota service outages, counter resets, multi-region operation, and skewed policy rollout versions.
9. Run drills for Tenant A load spikes, DB saturation, queue backlogs, and limiter unavailability; measure Tenant A and B SLOs.
10. Write an ADR explaining trade-offs across fairness, isolation, performance, security, cost, and operations.

### Sample Policy Matrix

| Workload | Metering Unit | Tenant Limit | Shared System Guardrail | On Exceed |
| --- | --- | --- | --- | --- |
| Read API | Request/cost unit | Rate + burst | Global concurrency | `429` or backoff |
| Search | Search cost unit | Query rate + complexity | Timeout/shard capacity | Reject heavy queries |
| Import | Worker-seconds/records | Concurrent jobs + file size | Worker pool capacity | Queue or reject |
| Export | Worker-seconds/rows | Concurrent jobs | DB read budget | Defer/throttle |
| Storage | GB-months/requests | Soft/hard quotas | Account-level cap | Alert/deny new uploads |
| Egress | Bytes transferred | Monthly allowance | Network capacity | Throttle/overage policy |

### Completion Criteria

- Limits reflect resource cost, not mere request counts.
- Tenant context and metering cannot be spoofed from clients.
- Fairness policies exist and prevent starvation for lower-tier workloads.
- No single tenant can exhaust all workers, DB connections, or cache memory.
- Limiter failures neither leave the entire system unprotected nor unfairly block all tenants.
- Metrics distinguish noisy neighbors, legitimate high load, and insufficient capacity.
- Processes exist for quota increases, pool splits, and incident response with audits.
- Tests prove Tenant B maintains its SLO when Tenant A ramps load within simulated bounds.

## 18. Well-Architected Pre-Production Checklist for Quotas and Resource Isolation

- [ ] Shared resources are mapped and cost is measured by workload type.
- [ ] Periodic quotas, rate limits, bursts, concurrency limits, and system caps are clearly separated.
- [ ] Limits reflect service tiers and define owners, resets, and overage behavior.
- [ ] Contended pools use fair scheduling/weighted sharing rather than pure first-come, first-served.
- [ ] Minimum reserves exist for system workloads and recovery headroom.
- [ ] Bounded queues, backlog age, and per-tenant pending caps are enforced.
- [ ] Databases, caches, search, workers, storage, and egress have appropriate guardrails.
- [ ] Shared/segmented/dedicated pools are chosen based on isolation needs and cost.
- [ ] Tenant identity is verified; clients cannot self-elevate quotas/priorities or spoof tenant context.
- [ ] Per-tenant/workload telemetry enforces proper access controls, retention, and masking.
- [ ] Limiters define timeout strategies, fail-open/fail-closed behavior, local caps, and reconciliation.
- [ ] Multi-region quotas/counters define semantics and oversubscription handling.
- [ ] Retries/backoff/idempotency prevent load amplification against quotas and dependencies.
- [ ] Dashboards/alerts distinguish policy-violating tenants from inadequate capacity planning.
- [ ] Runbooks exist for throttling, quota increases, pool transitions, policy rollbacks, and audits.
- [ ] Noisy-neighbor tests verify other tenants' SLOs remain protected.
- [ ] ADRs explicitly document trade-offs across reliability, security, performance, cost, and operations.

**Core principle:** quotas state how much a tenant may consume; rate limits and concurrency control speed and simultaneous work; fair scheduling and resource pools govern how capacity is divided under contention. To sustainably prevent noisy neighbors, a system must **meter cost by workload, verify tenant context, enforce multi-layer limits, allocate fairly, and isolate when necessary**. Limits are only truly effective when proven against the SLOs of both heavy tenants and everyone else sharing the platform.
