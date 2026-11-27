# Load Distribution, Skew, and Bottleneck Mitigation

> **Chapter:** System Scaling  
> **Scope:** Designing cloud application architectures from business requirements through network, compute, data, and deployment choices. This lesson focuses on distributing traffic and work, identifying load skew, locating bottlenecks, and mitigating them to maintain reliability, performance, scalability, cost, and operability using Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of load balancers, routing, partitioning, queues, and autoscaling in load distribution.
2. Identify types of skew: hot keys, hot partitions, skewed tenants, skewed queries, overloaded regions/availability zones, and uneven resource consumption.
3. Read latency, throughput, saturation, queue age, utilization, and error rate metrics to locate bottlenecks along a request path.
4. Distinguish bottlenecks at the edge, network, compute, connection pool, database, broker, and external dependencies.
5. Select throttling, balancing, splitting, or isolation techniques; evaluate impacts on consistency, ordering, reliability, and cost.
6. Plan load testing, fault testing, capacity forecasting, and post-change measurement.

## 1. Load Distribution Is an End-to-End Architectural Problem

A system can have many servers and replicas and still be slow if requests are not distributed effectively. For example, a booking application has 20 API replicas, yet relies on a single database primary, one queue partition receiving most bookings, or one tenant running heavy reports. Adding API replicas will not fix those bottlenecks.

**Load distribution** is how requests, jobs, messages, or data are directed to resources capable of handling them in alignment with latency, throughput, resilience, fairness, and cost goals.

Distinguish three concepts:

- **Load balancing:** distributing requests or connections across backends.
- **Work partitioning:** dividing datasets or workloads into units that can be processed in parallel.
- **Load shedding/admission control:** rejecting or deferring load that exceeds safe serving capacity.

A load balancer is only one component in a load distribution system. It cannot automatically fix slow DB queries, lock contention, hot keys, underpowered queue consumers, or rate-limited external dependencies.

### Where Does a Request Travel?

~~~mermaid
flowchart LR
    U["Client"] --> CDN["DNS / CDN / WAF"]
    CDN --> LB["Load balancer / API gateway"]
    LB --> APP["API replicas"]
    APP --> CACHE["Cache"]
    APP --> DB[("Database")]
    APP --> Q["Queue / broker"]
    Q --> W["Worker pool"]
    W --> DB
    DB --> EXT["External services / data stores"]
~~~

Actual paths vary, but every hop can introduce latency, queueing, errors, and capacity limits. When measuring performance, capture both per-layer timings and end-to-end duration.

## 2. Load Balancing at the Network and Application Layers

### 2.1. What Does a Load Balancer Do?

A load balancer accepts connections or requests and selects a backend based on an algorithm and health status. It can distribute at the network layer (L4) or understand application protocols like HTTP (L7).

| Type | Scope | Typical Capabilities | Considerations |
| --- | --- | --- | --- |
| L4 load balancing | TCP/UDP flows | Distributes connections/flows by IP and port | Long-lived connections can create skew even if connection counts look balanced |
| L7 load balancing | HTTP/gRPC requests | Routes by host, path, header, cookie, rule | Must manage TLS, timeouts, headers, retries, and request semantics |
| Global traffic management | Multi-region/edge | Steers traffic by health, latency, geography, or policy | DNS caching, failover convergence, and cross-region data |
| Internal load balancing | Service-to-service | Distributes traffic between internal backends | Service discovery, identity, network policies, and telemetry |

A backend marked unhealthy should be removed from rotation according to designed health checks. However, overly deep health checks can trigger cascading failures: a flaky database causes every API pod to fail health checks even when they can still serve other paths. Separate liveness, readiness, and dependency health.

### 2.2. Common Distribution Algorithms

| Algorithm | How Backend Is Chosen | Advantages | Limitations |
| --- | --- | --- | --- |
| Round robin | Sequentially down the list | Simple, fair by request count when loads are similar | Unaware of request cost and backend state |
| Weighted round robin | By configured weights | Fits backends with differing capacities | Static weights can go stale as load shifts |
| Least connections | Prefers backend with fewest connections | Useful for varying connection lifetimes | Connection count does not always reflect CPU/request cost |
| Least requests / least outstanding | Prefers backend with fewest active requests | Adapts to short vs long requests | Depends on accurate in-flight tracking |
| Random / power of two choices | Random selection, optionally comparing two backends | Reduces hotspots and scales easily | Does not replace health/capacity policies |
| Consistent hashing | Maps keys stably to backends | Preserves locality/cache affinity, minimizes remapping | Hot keys still concentrate on one backend |
| Latency/health-aware | Prefers backends using observed signals | Avoids degraded backends | Lagging/noisy telemetry can cause oscillation or feedback loops |

No algorithm is best in every case. Round robin fits stateless APIs with uniform requests; least outstanding fits workloads with variable processing times. Hashing helps when locality matters, but hot keys must be handled separately.

### 2.3. Sticky Sessions and Statelessness

Sticky sessions pin a client to a single backend for a period of time. This preserves local caches/sessions and supports legacy applications, yet breaks even distribution when some clients are much heavier, and reduces flexibility during backend failures or scaling.

For scalable cloud systems, prefer externalized session/state data (such as a session store or controlled stateless tokens) so backends remain replaceable. If affinity is still required, define TTLs, failure behavior when a backend dies, and how session data loss is prevented.

## 3. Load Distribution Does Not Mean Equal Request Counts

Counting requests arriving at each replica is not enough to conclude load is balanced. A lightweight search request might take 5 ms, whereas a report-generation request takes 5 seconds and far more CPU/IO. One tenant might send fewer requests but run expensive queries.

Consider:

- **Request rate:** requests per second.
- **Concurrency/in-flight requests:** number of jobs currently running.
- **Resource cost:** CPU, memory, IO, connections, network, or processing time.
- **Latency distribution:** p50, p95, p99 rather than averages alone.
- **Queue age:** how long the oldest job has been waiting.
- **Error/rejection rate:** whether backends are rejecting, timing out, or retrying.
- **Fairness:** whether one tenant group or priority stream starves others.

### Simple Example

Two backends both receive 100 requests/second. Backend A averages 10 ms per request; Backend B receives heavier requests averaging 300 ms. Request counts are identical, yet CPU time, connections, and concurrent in-flight work differ dramatically.

Little's Law describes the relationship in a stable system:

\[
L = \lambda W
\]

Where:

- \(L\): average number of work items inside the system (in-flight or queued, depending on measurement boundary).
- \(\lambda\): average throughput (items/second).
- \(W\): average time an item spends in the system (seconds).

For example, at 200 requests/second with 0.25 seconds spent inside the system, average concurrent requests at that boundary are roughly 50. If latency climbs while throughput holds steady, in-flight requests and memory/connection pressure can rise rapidly.

This relationship holds for stable systems within properly defined boundaries; do not use it directly to infer maximum capacity or ignore latency distributions.

## 4. What Is Skew?

**Skew** is an uneven distribution of load, data, or processing time across components. Certain nodes, partitions, or tenants receive or process significantly more work than the rest.

Skew commonly appears when:

- A very popular key (hot key) receives most requests/events.
- A hash or partition key distributes unevenly.
- One tenant generates far more load than other tenants.
- One partition holds more data or heavier queries.
- One region/availability zone has most users or better network paths.
- Jobs vary widely in size or data complexity while being split evenly by record count.
- Cache keys have skewed cardinality/popularity, concentrating cache misses on specific objects.

### 4.1. Distinguishing Skew From System-Wide Overload

| Symptom | Indicator | Initial Mitigation |
| --- | --- | --- |
| Total load exceeds capacity | Almost all backends are saturated | Scale the right tier, admission control, optimize work |
| Skew | A few backends/partitions are hot while others sit idle | Adjust keys/partitions, spread hot workloads |
| Dependency bottleneck | Many backends wait on the same DB/external API | Optimize dependency, pooling, caching, or cap concurrency |
| Queue backlog | Producer outpaces consumer | Scale consumers, optimize sink, apply backpressure |
| Thundering herd | Many simultaneous requests hit one resource | Request coalescing, jitter, caching, rate limiting |

Scaling the entire system when only one partition is hot increases cost without relieving the bottleneck. Always check for skew before adding capacity.

## 5. Hot Keys, Hot Partitions, and Partitioning Strategies

### 5.1. Hot Keys

In a cache, database, or broker, an overly accessed key becomes a hotspot. Examples include a trending event page, a promo code, or a major tenant receiving disproportionately high traffic.

Mitigations depending on data type:

- Cache read-only copies across multiple nodes/edge locations if consistency permits.
- Pair short-TTL local caches with a centralized cache.
- Separate read and write paths if the workload allows.
- For continuously incrementing counters, shard counters across sub-keys and aggregate.
- Apply dedicated throttling or quotas for hot keys/tenants.
- Precompute/materialize results rather than recalculating on every request.

Do not arbitrarily replicate data with concurrent writes or global ordering requirements. For inventory or remaining seat counts, sharding counters without proper reservation/synchronization protocols can cause overselling.

### 5.2. Hot Partitions in Streams/Brokers

If messages are partitioned by key and one key accounts for most events, one partition can overload while others sit idle. Adding consumers cannot help if partition count or key distribution is the limiting factor.

Options:

- Choose a partition key with adequate cardinality and spread while preserving required ordering scope.
- For aggregation workloads, split hot keys into sub-keys/shards and aggregate downstream; design ordering/consistency explicitly.
- Isolate large tenants or priority streams into dedicated topics, partitions, or cells if justified.
- Monitor bytes/messages per partition and per-partition consumer lag, not just topic totals.
- Tune partition count, replication, and retention for both throughput and recovery time.

For instance, partitioning by `tenant_id` preserves per-tenant ordering, yet one huge tenant creates a hot partition. Adding a random suffix spreads writes but breaks global tenant ordering; if ordering is only needed per booking, use `booking_id` or a narrower key.

### 5.3. Choosing a Partition Key

A good key balances four goals:

1. **Distribution:** prevents a few keys from carrying most of the load.
2. **Ordering:** preserves order strictly at the required business scope.
3. **Locality:** keeps frequently co-queried data close together.
4. **Operability:** allows moving, splitting, merging, and mitigating hot shards.

No single key is optimal for every query pattern. Partitioning by `customer_id` works well for customer lookups but poorly for time-range reports or giant tenants. You may need separate read models/indexes or data layouts rather than forcing one partition key to serve all queries.

## 6. Tenant Skew and Noisy Neighbors

In multi-tenant SaaS, total load often follows a long-tail distribution: many small tenants and a few massive ones. If everyone shares the same connection pool, queue, or database, a heavy tenant can degrade SLOs for everyone else.

### Protection Layers

- **Quotas:** limit requests/second, concurrency, storage, jobs, or connections per tenant.
- **Fair scheduling:** allocate processing turns or weights across tenants.
- **Bulkheads:** isolate pools, queues, workers, or threads/resources by workload.
- **Priority classes:** protect critical transactions so batch/analytics never starve transactional capacity.
- **Cell architecture:** group tenants into isolated compute/data cells to cap blast radius.
- **Dedicated tier:** move ultra-large tenants onto dedicated resources when requirements and unit economics justify it.

~~~mermaid
flowchart TB
    GW["Gateway + tenant-aware limits"] --> SCHED["Fair scheduler"]
    SCHED --> C1["Pool / Cell A"]
    SCHED --> C2["Pool / Cell B"]
    SCHED --> D["Dedicated tier"]
    C1 --> DB1[("Data A")]
    C2 --> DB2[("Data B")]
    D --> DB3[("Dedicated data")]
~~~

Calculate limits based on real workload cost, not raw request counts. One tenant may send 100 very expensive requests while another sends 1,000 cheap cache hits.

Quotas must define explicit behavior upon breach: return `429`/`Retry-After`, defer jobs, degrade secondary features, or route to a separate queue. Never return generic failures blindly or impact unrelated tenants.

## 7. Queueing and Backpressure to Absorb Fluctuations

Queues decouple producer speed from consumer speed over short intervals. They absorb bursts, but do not create infinite processing capacity.

~~~mermaid
flowchart LR
    P["Producers"] --> Q["Queue / broker"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> S["Sink / database"]
    W2 --> S
    W3 --> S
    S --> M["Metrics: age, lag, throughput, errors"]
~~~

Essential policies:

- **Bounded queues:** enforce size/time bounds to prevent unbounded backlogs.
- **Backpressure:** slow producers or throttle admission when consumers fall behind.
- **Retries with backoff/jitter:** prevent synchronized retry storms; route unrecoverable failures to a DLQ.
- **Visibility/ack timeouts:** long enough for processing, with heartbeats/extensions where supported; handle duplicates via idempotency.
- **Concurrency limits:** cap concurrent workers according to sink/dependency capacity.
- **Priority/fairness:** separate urgent flows from long batch jobs and prevent one tenant from hogging the queue.
- **Queue age alerts:** alert on oldest waiting message and SLA, not just message counts.

### Calculating Backlog

Suppose producers generate 1,200 jobs/second while the worker pool processes 900 jobs/second. The backlog grows by 300 jobs/second. After 15 minutes:

\[
B = (1{,}200 - 900)\times 900 = 270{,}000\text{ jobs}
\]

If producers stop while workers keep processing 900 jobs/second, draining just this backlog takes roughly 300 seconds (5 minutes), excluding load-dependent processing shifts and retry failures.

For the backlog to shrink while producers stay active, consumer throughput must exceed producer rate. For example, scaling workers to 1,500 jobs/second reduces the backlog by roughly 300 jobs/second, assuming stable efficiency and a sink that handles the load.

## 8. Finding Bottlenecks Systematically

### 8.1. Watch the Four Golden Signals

A standard triage approach monitors:

- **Latency:** response time, p50/p95/p99 distributions segmented by endpoint/tenant/region.
- **Traffic:** request rate, throughput, concurrency, and payload size.
- **Errors:** HTTP 4xx/5xx, timeouts, retries, rejected jobs, and dependency failures.
- **Saturation:** resource utilization/fullness across CPU, memory, disk, network, threads, connection pools, and queues.

Never diagnose a bottleneck purely from high or low CPU. An API with low CPU and high p99 may be blocked on database locks, networking, or connection pool waits.

### 8.2. Breaking Down Latency by Hop

~~~mermaid
flowchart LR
    A["Client / DNS / TLS"] --> B["CDN / WAF / Gateway"]
    B --> C["Load balancer"]
    C --> D["API processing"]
    D --> E["Cache / DB / broker"]
    E --> F["External dependency"]
    F --> G["Response"]
~~~

In distributed traces, measure spans per component. Total duration can include queueing, service time, serialization, network hops, and retries. A dependency averaging 20 ms that occasionally spikes to 2 seconds can dominate p99.

### 8.3. Signal and Bottleneck Hypothesis Table

| Signal | Hypothesis | Next Investigation |
| --- | --- | --- |
| High CPU, flat throughput | CPU-bound, lock contention, or excessive serialization | Profiling, flame graphs, thread states, locks |
| Low CPU, high latency | Waiting on I/O, DB, network, connection pools | Distributed traces, pool wait times, query latency |
| Steadily rising memory | Leak, unbounded cache, object retention | Heap profile, GC, cache cardinality |
| DB connection pool exhausted | Slow queries, connection leaks, high concurrency | Active/idle/wait counts, query plans, timeouts |
| High DB CPU/IO | Large scans, missing indexes, locks, write contention | Query plans, slow query logs, indexes/partitions |
| High lag on one partition | Hot key, consumer skew, poison message | Per-partition/key metrics, event age |
| Network retransmits/packet loss | Congestion, MTU, routing, or distant dependency | Network telemetry, flow logs, path tests |
| Rising 429/503 responses | Quotas, admission control, or backend capacity | Rate-limit metrics, autoscaling, provider quotas |
| Latency spike after autoscale | Warm-up, cold starts, cold caches, DB connection storm | Scaling timeline, startup logs, connection bursts |
| Only one tenant is slow | Tenant skew, query pattern, quota, or data volume | Segment latency/cost by tenant |
| Sudden cache misses | Deploy/purge, key fragmentation, synchronized TTLs | Hit ratio by key/path/PoP, invalidation events |
| Low worker throughput | CPU/IO, dependency, batch size, or concurrency | Profiling, queue age, sink latency |

### 8.4. Do Not Ignore Coordinated Omission and Tail Latency

A load test that only sends a new request after the previous one completes under-reports latency during slowdowns because it pauses load generation while waiting. Use load-testing tools/modes that model arrival rates accurately and understand how histograms are computed.

Never look solely at averages. If p50 is 80 ms while p99 is 2 seconds, a subset of users suffers terribly despite a healthy average. Slice by route, tenant, region, request size, and dependency to isolate tail latency sources.

## 9. Fixing Bottlenecks at the Right Layer

### 9.1. Edge, Gateway, and Load Balancer

If the bottleneck sits at the gateway/edge:

- Inspect connection limits, TLS handshakes, request body sizes, WAF rules, and rate limits.
- Enable keep-alive/connection reuse and avoid opening a fresh connection per request.
- Align timeouts and deadlines end-to-end; gateway timeouts must align with backend deadlines.
- Separate public, private, and differently prioritized API workloads.
- Consider CDN/caching for static and public read-only content; bypass private data.

### 9.2. Compute/Application

If the service is CPU-bound:
- Profile to optimize true CPU hotspots; cut serialization, algorithmic cost, or redundant work.
- Add replicas when the workload is stateless and dependencies have spare capacity.
- Use async I/O or bounded concurrency; never spawn unbounded threads or tasks.
- Separate CPU-heavy workloads from latency-sensitive APIs.
- Right-size CPU requests/limits and check for CPU throttling.

If memory-bound:
- Bound in-process caches, queues, and buffers; design explicit eviction.
- Analyze heap/GC behavior and object lifetimes.
- Avoid loading entire datasets into RAM when streaming or partitioning is possible.
- Verify memory limits, OOM kills, and rollout headroom.

### 9.3. Database

Databases frequently become bottlenecks when applications scale faster than read/write capacity:

- Optimize query plans, indexes, and N+1 query patterns.
- Cap connection pools per replica; combined connections across all replicas must stay within database capacity.
- Use read replicas or read models for read workloads that tolerate replication lag.
- Partition/shard when data volume and throughput demand distribution, defining keys and transaction boundaries upfront.
- Batch writes, queue writes, or use bulk operations to lower overhead where appropriate.
- Cache hot/read-only data with clear invalidation and freshness policies.
- Move analytics/reporting off the transactional path if they contend for resources.

Never raise connection pools unboundedly. Excessive connections consume DB memory and trigger context switching, making latency worse.

### 9.4. Network and External Dependencies

- Measure DNS, connect, TLS, TTFB, and dependency processing time.
- Set timeouts/deadlines within the end-to-end latency budget.
- Retry with exponential backoff and jitter; only retry idempotent operations or requests with idempotency keys.
- Use circuit breakers/bulkheads so slow dependencies do not exhaust system-wide resources.
- Cache or move to asynchronous flows when business semantics permit.
- Negotiate quotas/limits with providers and monitor rate-limit responses.

### 9.5. Queues and Workers

- Scale consumers by throughput and queue age, not CPU alone.
- Pick appropriate batch sizes; oversized batches increase memory/latency and make retries expensive.
- Separate job classes with differing durations so long jobs do not block short ones.
- Handle poison messages, retry storms, DLQs, and duplicates.
- Protect sinks with concurrency caps and bulkheads.
- Support pausing producers or throttling admission when sinks overload.

## 10. Autoscaling Cannot Replace Capacity Engineering

Autoscaling adjusts replica counts based on load signals, but you must still account for reaction lag and dependency limits.

### 10.1. Horizontal vs. Vertical Scaling

| Approach | How It Works | Best For | Limits |
| --- | --- | --- | --- |
| Scale up | Increase CPU/RAM/IOPS per instance | Hard-to-split workloads needing larger single-node resources | Instance ceilings, higher cost, may require restarts |
| Scale out | Add replicas/nodes/partitions | Distributable workloads with minimal local state | Dependencies, coordination, and data partitioning become bottlenecks |

Scale at the actual bottleneck: CPU-bound services can scale out; write-bound databases may need schema/partition optimization or data-flow changes rather than more API pods.

### 10.2. Autoscaling Signals

- CPU/memory for compute-correlated workloads.
- Request rate or in-flight concurrency for APIs.
- Queue age, lag, or backlog for workers.
- Custom business metrics when CPU does not mirror demand.
- Node capacity, pending pods, and regional quotas to catch compute shortages.

Scaling configs need min/max bounds, cooldown/stabilization windows, scale-up policies, scale-down behavior, warm capacity, and dependency limits. CPU autoscaling reacts slowly when queues spike fast; use queue age or predictive/pre-warming for clear seasonal peaks.

### 10.3. Connection Storms During Scale-Out

When adding replicas, each replica spins up a new DB pool. With a max pool of 50 scaling out to 100 replicas, theoretical connections hit 5,000. The DB can crash right as API autoscaling succeeds.

Calculate the system-wide connection budget including workers, migrations, admin tasks, and other apps. Use pool proxies, per-instance caps, connection reuse, and controlled rollouts where appropriate.

## 11. Caching and Read Load Distribution

Caching reduces database load, yet introduces skew and staleness risks:

- A hot key can hammer a single cache node without proper replication or sharding.
- Uniform TTLs can cause keys to expire simultaneously.
- Mass cache misses during deploys/purges can unleash a thundering herd on the origin.
- Caching too many variants fragments memory and lowers hit ratios.
- Negative caching can persist transient errors too long if misconfigured.

Mitigations:
- Jittered TTLs, request coalescing/single-flight, and stale-while-revalidate where safe.
- Replicate popular read-only entries or use edge caching appropriately.
- Bound key cardinality and memory with observable eviction policies.
- Versioned or event-driven invalidation where suitable.
- Controlled fallback if the cache fails; never treat a cache as the source of truth.

For inventory or payment status, cache only within business-approved freshness bounds. A fast cache hit returning stale state can cost far more than higher latency.

## 12. Load Shedding, Rate Limiting, and Admission Control

When demand exceeds capacity, trying to serve every request usually slows down and breaks the entire service. Admission control decides which work is accepted, deferred, or rejected.

- **Rate limiting:** cap request rates per user, tenant, API key, IP, or endpoint.
- **Concurrency limiting:** cap active requests/jobs in flight.
- **Load shedding:** drop low-priority or non-essential requests under overload.
- **Priority queues:** reserve capacity for critical transactions.
- **Graceful degradation:** disable recommendations, analytics, or secondary features to protect checkout.
- **Retry-After/backoff:** tell callers to slow down instead of retrying immediately.

~~~mermaid
flowchart TD
    R["Incoming requests"] --> A["Authenticate + classify"]
    A --> Q{"Quota / concurrency available?"}
    Q -->|"Yes"| P["Admit request"]
    Q -->|"No"| I{"Request priority?"}
    I -->|"Critical"| W["Wait bounded / reserved capacity"]
    I -->|"Best effort"| S["Shed / 429 + Retry-After"]
    P --> APP["Application"]
    W --> APP
~~~

Do not rely solely on IP-based rate limits when legitimate users share NATs. In SaaS, tenant-aware quotas are fairer once tenant context is authenticated.

Never retry endlessly on `429`/`503`. Retry storms turn brief incidents into prolonged outages.

## 13. Reliability: Bulkheads, Circuit Breakers, and Graceful Degradation

| Mechanism | Goal | Example |
| --- | --- | --- |
| Bulkhead | Contain failures/resources within a boundary | Separate pools for reports and checkout |
| Circuit breaker | Stop hammering failing dependencies | Temporarily halt payment provider calls after error threshold |
| Timeout/deadline | Prevent requests from hanging forever | API waits on dependency only within remaining budget |
| Backpressure | Throttle upstream speed to match downstream | Workers lower concurrency when DB lags |
| Retry + jitter | Retry transient failures without synchronization | Bounded exponential backoff retries |
| Graceful degradation | Preserve core business paths | Disable recommendations when search backend overloads |
| Health-aware routing | Avoid genuinely unready backends | Readiness checks verify traffic-serving ability |

Circuit breakers typically use open/half-open/closed states; avoid aggressive probing and avoid tripping on isolated transient errors. Health-aware routing also needs hysteresis so flapping metrics do not constantly add and drop backends.

## 14. Load Testing and Finding System Limits

A test plan must answer: how much load can the system handle within defined SLOs, where is the bottleneck, and how does it behave past capacity?

### 14.1. Test Types

- **Load test:** expected load under normal conditions.
- **Stress test:** steadily ramp load until targets break.
- **Spike test:** sudden traffic surge to evaluate autoscaling, queueing, and cold caches.
- **Soak test:** extended run to uncover memory leaks, backlog accumulation, GC issues, or resource exhaustion.
- **Concurrency test:** high simultaneous requests contending on identical keys/records.
- **Failover/fault test:** node/zone/dependency failures under load.
- **Skew test:** skewed key/tenant/partition distributions matching or exceeding production.

### 14.2. Workload Model

Simulate realistic endpoint mixes, payload sizes, read/write ratios, tenant distributions, cache hit rates, sessions, think times, and retry behavior. A test hammering one endpoint with tiny payloads misses hot keys, DB locks, and network egress limits.

### 14.3. Acceptance Criteria

| Category | Metrics |
| --- | --- |
| Performance | p50/p95/p99 by endpoint and tenant |
| Throughput | Requests/jobs/events per second |
| Stability | Error rate, timeouts, retries, rejected requests |
| Resources | CPU, memory, GC, disk/network, connection pools |
| Queues | Lag, oldest message age, backlog drain time |
| Data | Duplicates, ordering, reconciliation, consistency |
| Cost | Cost per 1,000 requests/jobs and at peak load |
| Reliability | Recovery time, availability, blast radius |

Do not record only the best run. Archive configs, versions, test datasets, cache warm/cold state, test origin, timestamps, and observed errors for future comparison.

## 15. Real-World Scenario: Booking Platform Slows Down During a Campaign

### 15.1. Symptoms

During a sales campaign, the system exhibits:
- Checkout p95 jumps from 250 ms to 1.8 seconds.
- Average API CPU stays around 45%.
- Database CPU hits 90%, and connection pool waits climb.
- One enterprise tenant runs heavy reporting queries.
- Notification queue backlog grows, though user bookings still succeed.
- One broker partition receives most events because messages are keyed by `tenant_id`.

These figures are hypothetical for exercise purposes. Never conclude from symptoms alone; gather traces, query plans, and per-partition metrics to prove causality.

### 15.2. Root Cause Analysis

| Symptom | Hypothesis | Verification |
| --- | --- | --- |
| Low API CPU, high p95 | API waiting on DB connections/queries | Trace spans, pool wait times, DB query latency |
| DB CPU at 90% | Report queries contending with checkout | Query plans, top SQL, locks/IO |
| One tenant runs heavy reports | Tenant skew/noisy neighbor | Per-tenant metrics, query cost |
| Notification queue lag | Consumers slower than producers or partition skew | Per-partition lag, worker throughput |
| `tenant_id` as partition key | Large tenant funnels events into one partition | Messages/bytes per partition |

### 15.3. Sequenced Mitigations

1. **Protect checkout:** cap report concurrency and shift batch reports to off-peak hours; isolate pools/priorities where possible.
2. **Relieve DB pressure:** optimize query plans/indexes, and route reports to a read replica or analytical projection where consistency allows.
3. **Control tenant skew:** enforce cost/concurrency quotas; isolate massive tenants to separate pools or cells when necessary.
4. **Fix partitioning:** pick a narrower key like `booking_id` if per-booking ordering suffices, or isolate the giant tenant to a dedicated topic/cell. Check impacts before changing partition counts.
5. **Drain queue backlog:** scale consumers within sink limits, split notification priorities, and track oldest message age; never let notifications slow down transactions.
6. **Re-test:** simulate the campaign with skewed key distributions, measuring checkout p95, DB load, per-partition lag, and cost.

Not every change needs to ship simultaneously. Measurable, phased rollouts avoid masking root causes or introducing compounding risks.

### 15.4. Diagram After Adjustments

~~~mermaid
flowchart TB
    U["Clients"] --> GW["Gateway: auth + tenant quota"]
    GW --> API["Checkout API pool"]
    GW --> SEARCH["Search API pool"]
    API --> TXDB[("Transactional DB")]
    REPORT["Report jobs"] --> RQ["Low-priority queue"]
    RQ --> RW["Report workers"]
    RW --> REPLICA[("Read replica / analytics model")]
    API --> EVT["Booking events"]
    EVT --> NQ["Notification topic"]
    NQ --> NW["Notification workers"]
    API -. "SLO / trace / saturation" .-> OBS["Observability"]
    RW -. "Lag / cost / tenant metrics" .-> OBS
    NW -. "Lag / retries" .-> OBS
~~~

## 16. From Load Distribution to Capacity Planning and TCO

Capacity planning must estimate not only averages, but also peaks, bursts, growth, and component failures:

- Concurrent users/requests and endpoint distribution.
- Request/job cost and processing duration.
- Database, connection, storage, network, and broker utilization.
- Redundancy for losing a node, AZ, or backend group.
- Autoscaling and image startup delays.
- Backlog buffered during dependency disruptions.
- Idle capacity cost for holding SLOs plus peak/DR costs.

One modeling approach:

\[
C_{\text{required}} \geq
\frac{\lambda_{\text{peak}}\times W_{\text{service}}}{U_{\text{target}}}
\]

Where \(\lambda_{\text{peak}}\) is peak work arrival rate, \(W_{\text{service}}\) is average resource units required per unit of work (units must be consistently defined), and \(U_{\text{target}}\) is target utilization. This formula is a simplified estimation model; real sizing must account for concurrency, multi-dimensional resource vectors, tail latency, dependencies, and failure headroom.

TCO includes compute, load balancers, caches, databases, brokers, network egress, observability, licensing, redundancy, operations, and incident costs. Good load balancing reduces waste, yet adding cache shards, queues, replicas, or cells raises baseline costs too.

## 17. Sample Architecture Decision Record

~~~markdown
# ADR-061: Load Distribution and Workload Isolation for the Booking Platform

Status: Proposed / Conditionally Approved
Decision owner: Architecture lead + SRE + Product
Date: YYYY-MM-DD

Context:
- Checkout p95 spikes sharply during campaigns.
- One tenant's reporting workload consumes DB capacity.
- Notification stream suffers from partition skew.
- Need to protect checkout SLOs and ensure tenant fairness.

Options:
A. Scale up all API/DB capacity.
B. Cap report concurrency, isolate read workloads,
   adjust partition keys, and enforce per-tenant quotas.
C. Move every tenant into dedicated deployments.

Proposed Decision:
- Implement Option B incrementally, measuring after each step.
- Consider dedicated cells for huge tenants if quotas/read models
  cannot sufficiently bound blast radius.

Trade-offs:
- Adds quota enforcement, routing, read models, and queue operations.
- Changing partition keys may require migration/replay.

Acceptance Evidence:
- Checkout p95/p99 and error rates at peak load.
- Lower DB connection wait/CPU/IO while reports still meet SLA.
- Balanced per-partition lag; notification age meets target.
- No increase in duplicates or broken business ordering.
- TCO/cost per transaction stays within budget.

Revisit Triggers:
- Major shift in load/tenant distribution;
  SLOs missed; hot partitions persist;
  cell/read-model costs exceed threshold.
~~~

The ADR should archive workload profiles, trace/query evidence, cost models, assumptions, and residual risks. Approve changes only with a clear rollback plan and verification tests.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Balancing solely by request count | Heavy requests pile onto one backend | Measure concurrency, service time, resource cost, and latency |
| Scaling APIs when DB is the bottleneck | Increases DB connections and load | Locate bottlenecks via traces and dependencies |
| Using consistent hashing to fix hot keys | Hot keys still map to one node | Replicate/read-cache, shard keys, or isolate hot workloads |
| Adding partitions without checking ordering | Alters ordering or key mapping | Document ordering scope and migration plans |
| Unbounded queues | Exhausts backlogs, retention, or storage | Bounded queues, backpressure, and admission control |
| Retrying immediately on error | Retry storms overwhelm dependencies further | Exponential backoff, jitter, and retry budgets |
| Oversized connection pools on every replica | Exhausts DB connections | Calculate total connection budget, use pool proxies and per-instance caps |
| Overly fast/unstable autoscaling | Oscillation, cold starts, and cache/DB storms | Stabilization, warm capacity, and tuned scaling policies |
| Monitoring only CPU | Misses IO, locks, queue age, and network issues | Per-tier metrics and distributed tracing |
| IP rate limits for SaaS | Blocks legitimate users sharing NAT | Tenant/user-aware quotas |
| Sharing one queue for critical jobs and long batches | Short jobs blocked by long ones | Priority queues and isolated worker pools/bulkheads |
| Caching strongly consistent data indefinitely | Stale state breaks business logic | Freshness policies, invalidation, and source-of-truth checks |
| Testing only average load | Misses spikes, skew, and tail latency | Run stress, spike, soak, skew, and fault tests |
| Adopting cells/dedicated tiers prematurely | High operational overhead | Base on measurements, triggers, and isolation value |

## 19. Hands-On Exercise

A booking platform runs 40 API replicas and 12 workers. During peak hours, checkout p99 exceeds 2 seconds even though API CPU is under 60%. The database connection pool frequently queues callers; one tenant accounts for nearly half of all reporting queries. The queue has 24 partitions, yet 3 partitions carry 70% of messages. An upcoming campaign is projected to triple traffic.

Complete the following:

1. Map the request path and data flow from clients through APIs, caches, DB, queues, workers, and external dependencies.
2. List at least six bottleneck hypotheses; for each, specify metrics and verification steps.
3. Identify whether skew lies in tenants, queries, queue partitions, or backends; separate total overload from skew.
4. Propose quotas/fair scheduling for large tenants and mechanisms to shield checkout from reporting workloads.
5. Choose a partition key for booking events; explain the ordering scope and how to handle hot tenants.
6. Design bounded queues, backpressure, retry budgets, DLQs, and consumer scaling.
7. Propose load shedding/rate limiting when peaks exceed capacity; specify which requests are prioritized or degraded.
8. Calculate backlog growth under explicit producer vs. consumer throughput assumptions.
9. Plan load/stress/spike/soak/skew/fault tests tracking p95/p99, errors, queue age, DB waits, and cost.
10. Draft an ADR recording chosen mitigations, residual risks, owners, and revisit triggers.

**Self-Evaluation Criteria:** A strong solution pinpoints bottlenecks with layer-by-layer evidence, addresses skew at the exact key/tenant/partition level, protects core business flows, and proves changes do not increase errors, data loss, or excessive cost.

## 20. Pre-Release Checklist for Load Distribution Changes

- [ ] Workload model covers endpoints, tenants, payloads, concurrency, and processing times.
- [ ] Defined p95/p99 SLOs, throughput, error rates, and capacity headroom.
- [ ] Load balancing algorithm matches request costs and connection lifecycles.
- [ ] Health checks, readiness, timeouts, and failover behavior are well-defined.
- [ ] Sticky sessions have clear justification, TTLs, and backend-failure plans.
- [ ] Partition keys satisfy distribution, ordering, locality, and operability.
- [ ] Dashboards show per-backend/partition/tenant metrics, not just aggregates.
- [ ] Hot keys, hot partitions, and noisy neighbors have been tested.
- [ ] Queues are bounded; backpressure, retries, DLQs, and idempotency are designed.
- [ ] Combined connection pools stay within database capacity.
- [ ] Autoscaling defines min/max, stabilization, quotas, warm capacity, and dependency checks.
- [ ] Rate limiting, fairness, load shedding, and graceful degradation are explicit.
- [ ] Distributed tracing, runbooks, and dependency owners are in place.
- [ ] Executed appropriate load, stress, spike, soak, skew, and fault tests.
- [ ] Measured before/after impact and calculated TCO for steady state, peak, and DR.
- [ ] ADR records trade-offs, assumptions, risks, rollback, and revisit triggers.

## Key Takeaways

Good load distribution does more than equalize request counts per machine. It distributes **work and processing cost** appropriately, preserves fairness across tenants, avoids hot keys/partitions, shields dependencies, and responds predictably when capacity is exceeded.

Follow the sequence: **measure the request path → find saturation and tail latency → isolate skew/bottlenecks → fix at the right layer → load and fault test → re-measure SLOs/TCO**. Scaling resources only pays off when it addresses the exact constraint limiting the system.
