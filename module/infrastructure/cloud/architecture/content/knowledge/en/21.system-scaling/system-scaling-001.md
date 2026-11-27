# Vertical Scaling, Horizontal Scaling, and Architectural Limits

An application that runs smoothly at a few hundred requests per minute can become slow when traffic increases tenfold. Adding CPU or RAM to a server can resolve an immediate resource shortage, but a larger machine still has hardware limits and creates a single point of failure. Adding more machines or containers distributes load, but only works effectively when the application, data, and dependencies can work across multiple instances simultaneously.

**Vertical scaling (scale-up)** increases the resources of an existing compute unit, such as CPU, RAM, IOPS, or network bandwidth. **Horizontal scaling (scale-out)** increases the number of processing units and distributes work across them, such as adding VMs, containers, pods, or workers. Both approaches can be combined; the choice depends on the bottleneck, state characteristics, platform limits, SLOs, and cost.

This lesson belongs to the **System Scaling** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to evaluate how a system responds to increasing load, identify limits at each tier, build a capacity plan, and choose between scale-up, scale-out, or architectural changes. The focus is on trade-offs across performance, reliability, security, cost, and operations following Well-Architected principles.

## 1. What Does System Scaling Mean?

Scaling is the ability to meet increasing or changing demand by adding, allocating, or reorganizing resources. Demand can grow along several dimensions:
- Number of concurrent users.
- Requests per second and complexity per request.
- Number of messages or events waiting to be processed.
- Data volume and read/write throughput.
- Number of tenants, geographic regions, or workloads.
- Model, file, or payload size.
- Availability, latency, and recovery requirements.

A system scales well when adding resources increases serving capacity or maintains SLOs at a reasonable cost. **Adding machines does not automatically produce linear capacity gains.** If every request has to wait on the same database lock, an external API with a low quota, or a hot partition, adding application servers can actually worsen the bottleneck.

### 1.1. Key Properties to Distinguish

- **Scalability:** the ability to increase capacity as demand grows.
- **Elasticity:** the ability to automatically scale resources up or down based on demand.
- **Capacity:** the maximum or safe workload a system can serve under defined conditions.
- **Headroom:** spare capacity available above the current load.
- **Bottleneck:** the component limiting the throughput or latency of the entire system.
- **Saturation:** the state where a resource approaches or hits its limit, causing queueing and latency to spike sharply.

A system can be scalable without being elastic if humans must manually add nodes. An elastic system can also fail to scale if the bottleneck sits in a dependency that does not scale alongside it.

## 2. Vertical Scaling (Scale-Up)

Scale-up increases the resources of an existing machine or instance.

~~~mermaid
flowchart TB
    A["Before: 1 application instance"] --> A1["2 vCPU / 4 GB RAM"]
    B["After: same instance"] --> B1["8 vCPU / 32 GB RAM"]
    A1 --> S["Processing capacity per instance increases"]
    B1 --> S
~~~

For example, the Booking API runs on a VM with 2 vCPU and 4 GB RAM. When traffic rises and CPU reaches 90%, you can upgrade it to 8 vCPU and 32 GB RAM to process more requests on the same instance.

### 2.1. Advantages

- Application architecture can remain unchanged.
- Minimal changes to routing, service discovery, and state distribution.
- Can add capacity quickly if the cloud provider supports appropriate resizing.
- Well-suited for databases or legacy software that are hard to partition.
- Easier to observe because there are fewer instances.

### 2.2. Limitations

- Bound by the maximum instance size or physical machine hardware ceiling.
- Price increases with instance tiers; larger configurations may have worse cost-to-throughput ratios.
- One large machine becomes a larger failure domain.
- Resizing may require restarts, downtime, or migration.
- Does not solve limits in databases, external services, networking, or locks.
- Large, underutilized resources can create waste.

Scale-up is often a good step to address a straightforward bottleneck or create headroom, but it does not replace root-cause analysis. If CPU is low while latency spikes due to an exhausted database connection pool, adding vCPUs may not help at all.

## 3. Horizontal Scaling (Scale-Out)

Scale-out adds processing instances and distributes requests or work across them.

~~~mermaid
flowchart TB
    U["Users / clients"] --> LB["Load balancer"]
    LB --> A["App instance A"]
    LB --> B["App instance B"]
    LB --> C["App instance C"]
    A --> DB[("Shared data store")]
    B --> DB
    C --> DB
~~~

For example, the Booking API can run three identical containers behind a load balancer. When request volume increases, the orchestrator adds replicas; when load drops, it can remove replicas to save cost.

### 3.1. Advantages

- Increases total throughput by adding instances.
- Can tolerate the failure of an instance while continuing to serve through remaining instances.
- Easy to deploy across multiple zones or availability zones.
- Flexible scale-out and scale-in suited for fluctuating workloads.
- Enables isolating workload groups with different resource profiles or SLOs.

### 3.2. Limitations

- The application must support running multiple instances concurrently.
- State held in local memory cannot be shared across instances.
- Requires load balancing, health checks, service discovery, and graceful shutdown.
- A shared database, cache, queue, or API can become the new bottleneck.
- Adding nodes increases network calls, replication traffic, and operational overhead.
- Distributed systems introduce new failure modes: timeouts, retries, duplicates, partial failures, and consistency issues.

Scale-out works best when each request or job can be processed independently, or when state is managed by a dedicated, appropriate tier.

## 4. Comparing Scale-Up and Scale-Out

| Criterion | Scale-up | Scale-out |
|---|---|---|
| How capacity increases | Increase CPU/RAM/IOPS/bandwidth per instance | Increase number of instances/workers |
| Architectural changes | Usually minimal | Usually requires distributed design |
| Limits | Hardware/instance configuration ceiling | Distribution, coordination, and dependency limits |
| Failure domain | Can concentrate on one large machine | Can spread across multiple instances/zones |
| State | Easier to keep local state | Must handle shared state or partitioning |
| Scaling speed | Depends on resize operation and provider | Can be automated, but requires startup time |
| Cost | Large machines can be expensive and inflexible | Can right-size, but adds network/coordination overhead |
| Typical use cases | Legacy apps, databases, hard-to-split workloads | Stateless web/API, workers, independent services |

There is no single absolute choice. A system may scale up a database to increase single-node capacity, scale out the API to handle more requests, and partition batch workloads across multiple workers.

## 5. Stateless vs. Stateful: Key Prerequisites for Scale-Out

### 5.1. Stateless Applications

A stateless application instance does not retain session state or unique business data in local memory between requests. Any healthy instance can handle the next request as long as it receives sufficient input and has access to the required state store.

Examples:
- Authentication based on signed tokens verified against policy.
- Sessions stored in a distributed store or controlled client tokens.
- Booking data persisted in a database.
- Files stored in object storage rather than a container's local disk.

~~~mermaid
flowchart LR
    C["Client"] --> LB["Load balancer"]
    LB --> A["Stateless API A"]
    LB --> B["Stateless API B"]
    LB --> C2["Stateless API C"]
    A --> S[("Shared session / database / cache")]
    B --> S
    C2 --> S
~~~

Stateless does not mean the application has no state; it means the state needed across requests is stored in an appropriate external location rather than tied to a specific instance.

### 5.2. Stateful Applications

Stateful workloads keep state in process memory, on local disk, or in an identity-bound role. Examples:
- WebSocket connections or sessions pinned to a specific node.
- Database primary/replicas.
- Stateful stream processors maintaining partition state.
- Game servers holding active match state.
- Workers processing an ordered stream tied to a partition.

Stateful workloads can still scale out, but they require partitioning, replication, leader election, state transfer, affinity, or durable storage. Coordination and recovery costs are higher.

### 5.3. Do Sticky Sessions Solve State?

Sticky sessions configure the load balancer to route the same client to the same instance. This can reduce the need to transfer session data between nodes, but:
- Instance failure can lose local state.
- Scale-in and migration become harder.
- Load distribution can skew if one group of clients is heavily active.
- Requests are not guaranteed to hit the same node if cookies expire or routing changes.

Sticky sessions are a routing technique, not a substitute for durable state design or replication.

## 6. Finding Bottlenecks Before Adding Resources

End-to-end throughput and latency are bounded by the weakest tier or the resource that saturates first.

~~~mermaid
flowchart LR
    C["Client"] --> GW["Gateway"]
    GW --> APP["Application"]
    APP --> CACHE["Cache"]
    APP --> DB["Database"]
    APP --> EXT["External API"]
    APP --> Q["Queue"]
    Q --> W["Workers"]
    W --> DB
~~~

Measure every tier:
- Gateway/load balancer: request rate, connection limits, TLS CPU, queueing.
- Application: CPU, memory, thread pool, connection pool, GC, event loop.
- Cache: hit/miss ratio, hot keys, memory, evictions, network latency.
- Database: CPU, IOPS, locks, slow queries, connection count, replication lag.
- Queue: depth, oldest message age, publish/consume rate, retries, and DLQ.
- External API: latency, quota, rate limits, error rate.
- Network: bandwidth, packet loss, DNS, cross-zone traffic, and connection setup.

### 6.1. CPU Bottleneck

Symptoms include high CPU utilization, growing run queues, compute-intensive requests, and latency climbing with load. Actions: profile code, optimize algorithms, cache appropriate results, increase CPU, or add replicas.

### 6.2. Memory Bottleneck

Symptoms include memory pressure, GC pauses, swapping, OOM kills, and abnormal cache evictions. Distinguish between memory leaks, undersized heaps, oversized payloads, and growing working sets. Adding RAM may help temporarily, but it will not fix a leak.

### 6.3. Database Bottleneck

An application with many replicas can generate excessive connections and queries against a single database. Inspect query plans, indexes, lock contention, pool size, read/write ratio, and storage IOPS. Mitigations include query optimization, connection pooling, appropriate caching, read replicas, partitioning, or changing the write model.

### 6.4. Network or External Dependency Bottleneck

Adding application instances will not help if an external API has a fixed quota or network hops dominate latency. Use batching, connection reuse, asynchronous processing, rate limiting, circuit breakers, and capacity agreements with the provider.

## 7. Capacity Planning and Headroom

Capacity planning estimates the resources needed to handle current load, growth, and failure scenarios.

Simple example:
- One Booking API replica handles 200 requests/second stably within the p95 SLO.
- Expected peak is 1,200 requests/second.
- Operational target is at most 70% of benchmark capacity to preserve headroom.

Usable capacity per replica in the calculation:

\[
200 \times 0.70 = 140\ requests/s
\]

Estimated replica count:

\[
N = \lceil 1200 / 140 \rceil = 9
\]

Additional capacity is needed for failure scenarios. To still meet peak load when one replica is lost, you need at least 10 replicas under this simple model, or calculate precisely based on distribution and autoscaling policies. Benchmarks must be measured using the same model, request size, feature dependencies, and production-like configuration.

### 7.1. Elements a Capacity Plan Must Include

- Baseline, average, and peak traffic.
- Burst rate and ramp-up speed.
- Request/job mix and resource consumption per type.
- Latency, error, and availability SLOs.
- Target resource utilization and headroom.
- Detection, scaling, and warm-up times.
- Capacity during node/zone loss.
- Cloud quotas and resource provisioning lead times.
- Growth forecasts by tenant, region, or seasonality.
- Budget and cost constraints.

### 7.2. Do Not Use Utilization as the Sole Target

90% CPU can signal saturation, but 30% CPU does not prove the system has spare capacity if the database connection pool is exhausted. Track utilization alongside latency, queueing, errors, throughput, and dependency metrics.

## 8. Queueing and Why Latency Spikes Near Saturation

As load approaches serving capacity, requests have to wait in a queue. Latency can rise much faster than traffic growth.

A simple queueing model:
- Arrival rate: the rate at which requests arrive.
- Service rate: the rate at which the system processes requests.
- Utilization: the ratio of demand to serving capacity.

\[
\rho = \frac{\lambda}{\mu}
\]

Where lambda is the arrival rate and mu is the service rate in a single-server model. As rho approaches 1, wait time can increase sharply; when lambda exceeds mu over a sustained period, the queue continues to grow.

For example, a worker processing 100 jobs/second while receiving 95 jobs/second has far less headroom than one receiving 50 jobs/second. A short burst can be absorbed by a queue, but if arrival rate stays above processing rate, the backlog will not clear on its own.

Key practices:
- Set alerts on queue depth and oldest message age.
- Implement backpressure or admission control.
- Cap concurrency and batch size.
- Scale workers based on queue depth/age where appropriate.
- Set a retry budget to prevent retry amplification.
- Define actions when backlog exceeds business-acceptable timeframes.

## 9. Autoscaling: Adjusting Resources to Demand

Autoscaling automatically adjusts instance counts or resources based on metrics and policies.

### 9.1. Metric-Driven Scaling

Common signals:
- CPU/memory utilization.
- Requests per second or active connections.
- Request concurrency and latency.
- Queue depth/oldest message age.
- Custom metrics such as outstanding jobs or GPU utilization.
- Schedules for predictable periodic load.

Not every metric fits every workload. CPU-based scaling may react poorly if the app is waiting on a database; queue-based scaling suits asynchronous workers better; latency-based scaling requires caution because latency is a lagging indicator and may rise only after the system is already saturated.

### 9.2. Scale-Out and Scale-In

Scale-out must account for end-to-end provisioning time:
1. Metric crosses threshold.
2. Autoscaler detects the breach.
3. Cloud provisions compute.
4. Instance pulls the container/image.
5. Runtime starts and loads configs/models.
6. Health/readiness checks succeed.
7. Load balancer routes traffic to the instance.

If this sequence takes 2 minutes, a 20-second traffic burst requires baseline capacity or a queue to absorb it.

Scale-in must be graceful:
- Stop accepting new requests.
- Complete or hand off in-flight requests/jobs.
- Drain connections.
- Deregister the node from the load balancer.
- Terminate only after it is safe to do so.

Scaling in too abruptly causes connection resets, duplicate jobs, or lost state.

### 9.3. Cooldown, Stabilization, and Hysteresis

If scale-out/scale-in thresholds are too sensitive, the system will oscillate continuously (flapping). Use cooldown/stabilization windows, multiple metric samples, asymmetric scale-up/scale-down thresholds, or rate-limiting policies. Avoid scaling in immediately after a burst if backlog or latency has not stabilized yet.

## 10. Database Scaling: Limits Often Surface After the Application Tier

Adding application replicas increases request intake capacity, but also increases database connections and queries. The database is usually harder to scale horizontally than the application tier.

Common options:

| Technique | Goal | Trade-off |
|---|---|---|
| Vertical scale database | Increase CPU/RAM/IOPS on one node | Instance ceiling, cost, and single failure domain |
| Connection pooling | Reduce physical connections | Pool too small creates queueing; too large pressures DB |
| Read replicas | Distribute read workloads | Replication lag and eventual consistency |
| Caching | Reduce repeated queries | Staleness, invalidation, and cache failure modes |
| Partitioning | Split data/volume by key | Cross-partition queries and operational complexity |
| Sharding | Distribute data across multiple databases | Harder routing, rebalancing, transactions, and joins |
| CQRS/materialized views | Optimize read models per use case | Eventual consistency and extra pipelines |

Do not add a read replica and assume all reads can be routed to it by default. Operations requiring read-after-write consistency or authoritative state must read from the primary or use an appropriate synchronization mechanism.

### 10.1. Sharding and Choosing a Partition Key

A partition key must distribute load evenly enough, support primary queries, and avoid hot partitions. For instance, sharding by tenant works well if tenants are balanced, but a very large tenant can become a hotspot. Time-based sharding helps retention and range scans, but concentrates new writes on the current partition.

Considerations:
- Key cardinality and distribution.
- Whether queries access one or multiple partitions.
- Joins, transactions, and uniqueness constraints.
- Rebalancing when adding shards.
- Cross-shard reporting and backup/restore.
- Data locality and tenant isolation.

## 11. Caching, Replication, and Partitioning at Other Tiers

Scaling is rarely isolated to the application tier. Other tiers have limits as well.

### Cache
- Scaling up cache node memory/compute expands the working set.
- Scaling out a cache cluster partitions keys across nodes, but adds routing and replication overhead.
- A hot key can overload a single shard even when overall cluster capacity looks idle.
- Cache stampedes can hit the database with sudden traffic spikes on cache misses.

### Object Storage
Object storage generally scales capacity and request rate as a managed service, yet still has quotas, request pattern limits, prefix/partition behavior, egress costs, and lifecycle rules. Verify actual provider limits rather than assuming infinite scale.

### Queues and Event Streaming
Adding consumers only helps if the queue or partitions can distribute more work. In partitioned streams, parallel active consumers are typically capped by the number of partitions or ordering keys. Increasing partition counts may require migration and alter ordering semantics.

### External APIs
If a provider enforces a 500 requests/second quota, scaling clients out to 20 replicas will not make the provider accept more than its quota; it may only increase HTTP 429 errors. Use a shared rate limiter, queues, batching, valid caching, and capacity negotiation.

## 12. Distributed Coordination and Scale-Out Limits

With multiple instances, certain tasks require coordination:
- Leader election for single-executor tasks.
- Distributed locks to coordinate conflicting operations.
- Idempotency to guard against duplicate processing.
- Consensus or quorums for state with strong consistency requirements.
- Replication and conflict resolution for multi-location data.

Coordination adds latency and new failure modes. A distributed lock can expire while the original process is still running; leases and fencing tokens should be considered for critical resources. Do not use locks as a substitute for partitionable data design or idempotent processing.

A system scales better when coordination is minimized:
- Split work by tenant or aggregate key.
- Enforce clear partition ownership.
- Design operations to be independent and idempotent.
- Accept eventual consistency where the business domain allows.
- Aggregate results asynchronously instead of using cross-service distributed transactions.

## 13. Resilience, Availability, and Failure Domains

Scale-out can improve availability if instances are spread across multiple failure domains and the application tolerates losing part of its capacity.

Checklist:
- Are replicas distributed across multiple availability zones?
- Does the load balancer perform health checks and connection draining?
- Do databases, caches, and queues share the same failure domain as the app?
- When a zone goes down, can remaining capacity serve minimum required load?
- Does the autoscaler depend on a control plane or quota in the failed zone?
- Is there a degradation mode when resources are constrained?

Running 10 replicas on a single node or in one zone is not equivalent to spreading 10 replicas across multiple failure domains. However, multi-zone distribution introduces cross-zone latency and network costs; balance this against SLOs and data consistency requirements.

### N+1 Capacity

If a system needs N replicas to serve peak load, you can provision one or more extra replicas to keep serving when an instance fails. However, N+1 only holds if other tiers also have sufficient capacity. If the database can barely handle peak load when every app replica is healthy, losing a zone and triggering retries can overload the DB.

Test realistic failure scenarios rather than relying purely on replica counts.

## 14. Security During Scale-Out

Increasing instance counts expands the number of workload identities, network endpoints, and places holding configs or secrets. Security must scale alongside the system:

- Assign each workload or workload group its own least-privilege identity.
- Fetch secrets from a secret manager or secure provisioning mechanism; never bake them into images.
- Enforce network policies restricting traffic flows between tiers.
- Use TLS/mTLS where peer authentication and data protection are required.
- Ensure autoscaling groups and pod templates use vetted images with verified artifact provenance.
- Never log PII, tokens, or secrets in logs/metrics.
- Apply quotas and rate limits to prevent abuse when autoscaling raises intake capacity.
- Ensure scale-to-zero and scale-in revoke or clean up local credentials and sessions according to lifecycle rules.

Never grant every new replica broader permissions just because manual permission management is cumbersome. Use controlled policy and identity automation.

## 15. Cost and Right-Sizing

Scale-up and scale-out have distinct cost profiles:
- Larger instances can escalate rapidly in price across tiers.
- Many small instances add overhead for networking, load balancing, logging, and orchestration.
- Keeping a high baseline to avoid cold starts increases idle cost.
- Overly sensitive autoscaling causes churn, repeated warm-up, and wasted resource billing.
- Cross-zone/cross-region traffic and replication can drive up data transfer fees.
- Database read replicas and shards increase storage, backup, and operational costs.
- Spare capacity reserved for failure scenarios must be factored into the budget.

Metrics to track:
- Cost per request/job or per successful transaction.
- Cost by tenant/workload.
- Average and peak utilization.
- Idle capacity and scale-to-zero time.
- Network egress and cross-zone transfer.
- Database cost per query/transaction.
- Cost of errors, retries, backlogs, and overprovisioning.

Optimization does not mean keeping CPU at 95%. If high utilization drives up tail latency and error rates, the cost per successful request can actually increase. Right-sizing should be driven by SLOs and cost per successful unit of work.

## 16. Process for Evaluating and Choosing a Scaling Strategy

A review can follow this sequence:

1. **Define demand:** establish baseline, peak, burst, growth projections, and SLOs.
2. **Measure current state:** throughput, percentile latencies, errors, queue age, and utilization per tier.
3. **Locate the bottleneck:** identify the limiting resource or dependency before adding capacity.
4. **Check instance limits:** evaluate whether scale-up fits within hardware ceilings and acceptable downtime.
5. **Assess scale-out readiness:** are requests/jobs independent? Where does state live? What partitioning or coordination is needed?
6. **Evaluate dependencies:** can databases, caches, queues, networks, and external APIs handle increased load?
7. **Calculate capacity/headroom:** benchmark per replica, failure scenarios, warm-up times, and cloud quotas.
8. **Design autoscaling:** choose metrics, thresholds, cooldowns, min/max bounds, scale-in behavior, and graceful draining.
9. **Design resilience/security:** multiple failure domains, identities, network policies, fallbacks, and recovery.
10. **Compare cost:** cost per request, idle capacity, data transfer, and operational overhead.
11. **Validate:** run load tests, burst tests, scaling events, and node/zone/dependency failure tests.
12. **Document an ADR:** record the choice, known limits, assumptions, owners, and revisit triggers.

### Quick Decision Matrix

| Scenario | Initial direction to consider |
|---|---|
| Single instance CPU is high, app is hard to distribute, and hardware ceiling remains | Scale-up after profiling |
| Stateless web/API, growing traffic, and independent requests | Scale-out behind a load balancer |
| Queue workers with growing backlog | Scale consumers by queue depth/age with downstream limits |
| DB queries/locks are the bottleneck | Optimize queries/indexes/pooling first; then evaluate replicas/partitioning |
| External provider hits quota | Rate limit, queue, batch, or negotiate quota; do not just add replicas |
| One key/partition receives most of the load | Address hot keys/partitions and redesign distribution |
| Predictable cyclical load | Scheduled/pre-scaling combined with autoscaling |
| Infrequent load without strict latency SLOs | Scale-to-zero or batch processing may fit |
| Local state tied to an instance | Externalize state or design partitioning/failover before scaling out |

## 17. Sample ADR — Scaling the Booking API

> **Context:** The Booking API runs on a single 4 vCPU, 8 GB RAM VM. During promotional campaigns, traffic jumps from 150 to 900 requests/second. CPU hits 95%, p95 latency spikes sharply, and database connections and query latency also rise.
>
> **Option A:** Upgrade the VM to 16 vCPU, 32 GB. Provides headroom quickly with minimal application changes, but remains a single failure domain and will not solve database limits if queries or connection pooling are the root cause.
>
> **Option B:** Run multiple API replicas behind a load balancer, keep the app stateless, and cap total database connections. Add query optimization, a connection pooler, and read replicas for eligible reads.
>
> **Sample Decision:** Profile first to separate CPU time from database wait time. If CPU is genuinely the bottleneck, temporarily scale up the instance to stabilize, then scale out the API. Cap maximum replicas based on database capacity rather than scaling unboundedly.
>
> **Autoscaling:** Scale out on request concurrency/CPU with an upper bound; scale in more slowly and drain in-flight requests.
>
> **Resilience:** Spread replicas across multiple zones; verify sufficient capacity remains if one replica or zone is lost. Booking writes continue through transactional/authoritative database paths.
>
> **Verification:** Load test at 900 requests/second, measure p95/p99 latency, DB connections, query latency, errors, and cost/request, and run a single-zone loss test.
>
> **Revisit Triggers:** If the database remains a bottleneck after optimization and read replicas, evaluate partitioning/sharding or changing the read/write model.

## 18. Hands-On Exercise: Finding Limits Before Scaling

A booking platform has the following architecture:
- API running on 2 containers.
- Redis used for cache/sessions.
- One relational database primary.
- Notification Worker reading from a queue.
- Payment provider with a 300 requests/second quota.

When traffic quadruples:
- API CPU reaches 85%.
- p95 latency jumps from 120 ms to 900 ms.
- Database connections hit their limit.
- Cache hit ratio drops from 92% to 60%.
- Queue oldest message age increases.
- Payment provider returns many HTTP 429 responses.

**Tasks:**
1. Rank the most likely bottlenecks and identify additional measurements to collect.
2. Specify what can be solved with scale-up versus what requires scale-out or architectural changes.
3. Design a total database connection limit when adding API replicas.
4. Propose a cache investigation for the drop in hit ratio and potential cache stampede.
5. Design worker autoscaling based on queue depth/oldest message age.
6. Handle the payment quota using rate limiting, queueing, or batching.
7. Calculate capacity/headroom and failure scenarios for the API.
8. Propose load tests and single-instance/zone failure tests.

### Solution Approach

- 85% CPU is a signal, but database connections are maxed out and p95 jumped sharply; trace individual requests, query plans, pool wait time, DB CPU/locks/IO, and cache miss paths to quantify each latency contributor.
- Adding API replicas before capping connections can overload the DB further. Calculate total connections: replica count × max pool size, plus workers/admin/replication and headroom; introduce a connection pooler and a system-wide cap.
- A drop in cache hit ratio may stem from key cardinality, a new working set, synchronized TTL expirations, hot keys, evictions, or invalidations; inspect metrics by namespace/endpoint before scaling cache nodes.
- Scale queue workers based on oldest message age/queue depth, but cap max concurrency to match database and provider capacity; handle poison messages and enforce bounded retries.
- For the 300 requests/second payment provider quota, use a distributed rate limiter or shared token bucket; queue requests where business rules permit, respect 429/`Retry-After` headers, and use idempotency keys. Adding replicas will not raise the quota.
- Base API capacity on per-replica benchmarks at target latency, peak traffic, and headroom; account for replica/zone loss and autoscaling warm-up time.
- Run load tests covering warm-up, ramp, burst, soak, and dependency faults; measure p95/p99 latency, errors, DB connections, queue age, cache hit ratio, payment throttling, and cost.

### Self-Check Questions

1. How do scale-up and scale-out differ in terms of limits and failure domains?
2. Why can adding application replicas make a database slower?
3. What types of state must a stateless application externalize?
4. Do sticky sessions guarantee no session loss when an instance fails?
5. Why does low resource utilization not prove a system has spare capacity?
6. How does queueing affect latency as arrival rate approaches service rate?
7. What stages must autoscaling account for before a new replica serves traffic?
8. When are read replicas appropriate, and when does replication lag make them unsafe?
9. Why can consumer count be capped by partition count in a stream?
10. How do you determine required capacity when losing an availability zone?
11. Why can concurrent retries and autoscaling trigger retry amplification?
12. Which metrics help decide whether to scale up, scale out, or optimize a bottleneck first?

A sound scaling architecture does more than add CPU or replicas. It **identifies the true bottleneck, distributes work effectively, manages state and dependencies, preserves headroom during failure scenarios, and proves that cost per unit of work remains reasonable**. Scale-up is a simple tool to boost single-node capacity; scale-out expands across multiple instances but requires distributed design. The right choice starts with measurements, workload profiles, and SLOs, and is validated through load testing and failure drills.
