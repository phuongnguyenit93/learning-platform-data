# Capacity Planning and Resource Redundancy

A cloud application may run smoothly on a normal day yet fail precisely when demand surges or an infrastructure zone goes down. Sometimes the root cause is not an algorithm or software bug: CPU hit its ceiling, the database ran out of connections, queues grew faster than workers could drain them, quotas blocked scaling, or reserve capacity could not carry the load when a failure domain disappeared.

**Capacity planning** is the process of forecasting resource demand and verifying that the system can satisfy that demand under expected conditions. **Resource redundancy** is provisioning enough spare components or surviving capacity so the system maintains or recovers service when a component fails or undergoes maintenance.

Both must be designed together. A system with enough compute for ordinary days that runs out of capacity when a zone fails does not meet availability goals. Conversely, blindly doubling every resource without forecasting load inflates bills, adds complexity, and still fails to protect shared databases, quotas, or dependencies.

This lesson belongs to the **Compute Architecture** chapter of the **CLOUD_ARCHITECTURE** module. Its goal is turning business requirements into load models, forecasting compute and related limits, selecting scaling and redundancy mechanisms, and evaluating trade-offs across reliability, security, performance, cost, and operations under Well-Architected principles.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Translate user counts, transactions, traffic, and growth rates into resource demand models.
2. Distinguish **capacity**, **utilization**, **throughput**, **concurrency**, **headroom**, **quota**, and **saturation**.
3. Estimate demand for compute, memory, network, storage IOPS, database connections, and queue processing.
4. Distinguish scale up, scale out, autoscaling, load balancing, and N+1/N+2 redundancy models.
5. Determine surviving capacity required after losing an instance, node, zone, or region per RTO/RPO/SLO targets.
6. Design load, stress, soak, and failover drills to validate capacity assumptions.
7. Plan quotas, rollouts, warm-ups, maintenance, budgets, and alerts for stable operations.

## 2. Foundational Capacity Concepts

### 2.1. Capacity and Utilization

- **Capacity (maximum usable capacity):** the load a resource or system can serve while still meeting defined latency, error rate, correctness, and stability requirements.
- **Utilization:** the share of capacity currently consumed, e.g., 65% CPU, 70% memory, or 80% DB connection pool.
- **Throughput:** work completed per unit of time, such as 2,000 requests/second or 500 transactions/minute.
- **Concurrency:** requests, sessions, workers, or tasks actively in progress at the same instant.
- **Headroom:** unconsumed capacity kept to absorb variance, peaks, scaling lag, or partial degradation.
- **Saturation:** the state where a resource or system cannot accept additional load at acceptable quality, often showing up as rising queues, latency, and errors.

No single utilization threshold fits every resource. Running 80% CPU briefly can be fine for batch processing, whereas sustained 95% memory is dangerous if the app needs heap headroom or the OS begins reclaiming/swapping. Database connections at 90% can also signal exhaustion even while CPU remains low.

### 2.2. Provisioned Specs vs. Effective Capacity

A VM provisioned with 8 vCPUs and 32 GiB RAM does not automatically serve a fixed request rate. Usable capacity depends on:

- CPU generation, architecture, burst/credit limits, single-thread speed, and platform configuration.
- Memory working set, caches, heap, garbage collection, thread/process counts, and buffers.
- I/O patterns, request sizes, DB queries, external service calls, and cache hit ratios.
- Connection limits, file descriptors, ephemeral ports, sockets, queues, IOPS, bandwidth, and quotas.
- Latency targets, acceptable error rates, retry behavior, and load shape over time.

Capacity must therefore be established via **real workloads or grounded simulations**, not from vCPU/RAM specs on a price sheet.

### 2.3. Essential Formulas

~~~text
Utilization = Resources currently used / Available capacity
Headroom = Available capacity - Current demand
Preliminary instance count = ceil(Load demand / Effective capacity per instance)
~~~

Here `ceil` rounds up. Effective capacity per instance must come from benchmarks measured at target latency and error thresholds—not the raw limit right before collapse.

For fault-tolerant systems, compute formulas over the **surviving instances** after losing a failure domain, not across all healthy instances combined.

## 3. Translating Business Requirements into a Load Model

### 3.1. Start from User Behavior

Never begin capacity planning by asking "how many servers do we need?" First understand who the application serves and which actions generate load.

Example for a booking platform:

| Business Activity | Input Metrics | Impacted Resources |
| --- | --- | --- |
| User opens search page | Visits, searches per session | CDN, frontend, Search API, cache |
| Views listing details | Requests/session, payload size, image load rate | API, object storage, CDN, read database |
| Creates booking | Transactions/sec, retry rate, workflow steps | Booking API, write database, queue, Payment API |
| Sends email/notification | Event volume and emission timing | Workers, broker, external delivery provider |
| End-of-day reporting | Execution time, dataset size, query pattern | Read database, batch workers, storage |

Each action carries a distinct resource cost. One search page might trigger 5 API requests, 2 cache lookups, and 1 query; one booking might spawn multiple transactions and events. Counting logged-in users alone misses the actual workload.

### 3.2. Load Types to Forecast

| Load Type | Question | Example |
| --- | --- | --- |
| **Average load** | What is the mean demand over a period? | 400 requests/second average |
| **Peak load** | What is the hourly/daily/event peak? | 2,000 requests/second during launch window |
| **Burst load** | How sharply does load spike? | 500 to 1,800 requests/second in 30 seconds |
| **Sustained load** | How long does elevated load persist? | 1,200 requests/second for 3 hours |
| **Seasonal load** | What cycles drive traffic changes? | Weekends or holiday travel seasons |
| **Growth load** | How fast are users and data growing? | 12% monthly growth |
| **Failure load** | How much load shifts onto survivors during outages? | Zone loss shifts traffic to remaining zones |
| **Recovery load** | What surge arises during recovery? | Queue backlogs, cold caches, data sync |

Record peak duration, rate of change, and sustained windows. Autoscaling tuned for gradual ramps may fail on sudden spikes.

### 3.3. Deriving Request Rates from Behavior

Suppose a system has 100,000 active users per day, averaging 20 API requests per user/day:

~~~text
Total requests/day = 100,000 * 20 = 2,000,000
Average requests/second = 2,000,000 / 86,400
                        ≈ 23.15 requests/second
~~~

This daily average is useless for production sizing. If 30% of requests concentrate into one peak hour:

~~~text
Requests in peak hour = 2,000,000 * 30% = 600,000
Requests/second in peak hour ≈ 600,000 / 3,600
                             ≈ 166.7 requests/second
~~~

If traffic triples during a promotional event, load can briefly hit ~500 requests/second. Realistic models break traffic down by endpoint, operation type, and time distribution instead of applying one flat multiplier everywhere.

### 3.4. Concurrency and Processing Time

Under steady-state conditions, Little's Law applies:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests/jobs inside the system (concurrency).
- \(\lambda\): average throughput (requests/second).
- \(W\): average time a request spends in the system (seconds).

For example, if an API serves 200 requests/second with an average duration of 0.25 seconds:

\[
L = 200 \times 0.25 = 50
\]

Average concurrency is roughly 50 requests. This is a steady-state estimate; never derive thread counts or connection pools directly from it when tail latency is heavy, load swings wildly, or queues are unstable.

## 4. Estimating Per-Instance Capacity

### 4.1. Benchmark at Acceptable Service Quality

Suppose one Booking API instance on a chosen compute profile sustains **120 requests/second** at p95 latency under 200 ms and error rates below target. Beyond that point, p95 climbs steeply and connection pools saturate.

120 requests/second is the **effective capacity** for that specific benchmarked workload—not a permanent constant for every instance of that size. Whenever code, data, dependencies, or instance types change, re-benchmark.

### 4.2. Initial Instance Count Formula

~~~text
N = ceil(Peak request rate / Tested sustainable RPS per instance)
~~~

With a 500 requests/second peak and 120 requests/second effective capacity:

~~~text
N = ceil(500 / 120) = 5 instances
~~~

Five instances barely cover peak load when all five are healthy under benchmark conditions. To survive losing an instance, add explicit redundancy.

### 4.3. N+1 Redundancy Calculation

For N+1 survivability when one instance is lost:

\[
(N-1)\times C \geq D
\]

Where \(C\) is effective capacity per instance and \(D\) is design load demand.

With \(C = 120\) RPS and \(D = 500\) RPS:

\[
N \geq \lceil 500/120 \rceil + 1 = 6
\]

Six instances leave five surviving after losing one, providing 600 RPS of benchmarked capacity. Yet six instances may still fall short if a zone outage takes down multiple instances at once.

### 4.4. Post-Zone-Loss Capacity Calculation

Suppose six instances sit evenly across three zones, two per zone. Losing one zone leaves four instances:

\[
4\times120 = 480\ \text{RPS}
\]

480 RPS is below the 500 RPS design demand. The layout satisfies instance N+1 yet **fails single-zone-loss survivability**.

To survive losing one of three zones at the same load:

\[
(3-1)\times k\times120 \geq 500
\]

Where \(k\) is instances per zone:

\[
k \geq \lceil 500/(2\times120) \rceil = 3
\]

You need at least three instances per zone, totaling nine instances under this simplified model. This assumes traffic distributes evenly and all dependencies survive zone loss—verify networking, load balancers, databases, and dependencies before claiming HA.

## 5. Planning Across the Full Resource Chain

Compute does not operate in isolation. An API can have spare CPU yet stop serving because databases, caches, networks, brokers, or quotas ran out of capacity.

### 5.1. CPU and Memory

**CPU:**

- Track average and p95/p99 utilization over time windows.
- Distinguish CPU-bound vs. I/O-bound workloads; low CPU can mean threads waiting on I/O or stalled connections.
- Watch container CPU throttling, burstable instance CPU credits, and garbage collection time.
- Check single-threaded bottlenecks if hot threads or lock contention exist.

**Memory:**

- Measure resident set/working set, heap, non-heap, caches, buffers, and memory limits.
- Track OOM kills, swap, paging, GC pauses, and memory leaks over time.
- For containers, requests/limits drive scheduling and hard ceilings; setting limits too low triggers OOMs even with free node RAM.
- Budget for sidecars, agents, log buffers, and OS/runtime overhead—not just the app process.

### 5.2. Network and Connections

Limits to calculate:

- Ingress/egress bandwidth and NIC or instance-type throughput caps.
- Concurrent connections, connection churn, TLS handshakes, and ephemeral ports.
- Connection limits on load balancers, NAT gateways, firewalls, API gateways, and service meshes.
- Egress and inter-zone/inter-region transfer, including replication, telemetry, and backup traffic.
- Impact of retries, large payloads, WebSockets/streaming, and idle connections.

A CPU-rich system can stall on NAT port exhaustion or API gateway connection caps. Scaling out instances sometimes multiplies connections against a constrained choke point, making outages worse.

### 5.3. Databases and Storage

Do not track GB capacity alone. Monitor:

| Metric | Meaning | Impact of Capacity Exhaustion |
| --- | --- | --- |
| IOPS | Read/write operations per second | I/O queues build; query latency spikes |
| Throughput | Data transferred per second | Scans, backups, or large jobs slow down |
| Connection count | Concurrent DB connections | API timeouts or pool wait queues |
| Transaction rate | Transactions per second | Locks, contention, and WAL/log pressure |
| Storage growth | Rate of data accumulation | Disk full or slower backup/restore windows |
| Replication lag | Replica delay behind primary | Stale reads; degraded DR RPO |
| Cache hit ratio | Share of requests served by cache | Rising misses dump load onto DB |
| Queue depth / disk latency | I/O wait queue and response time | Reads/writes back up |

Adding API compute can flood the database with more requests and turn it into the bottleneck. Capacity planning must cover the full dependency graph and shared service caps.

### 5.4. Queues and Workers

If producers enqueue work faster than consumers process it, queue depth climbs. An approximate model:

~~~text
Backlog growth rate = Producer rate - Consumer processing rate

Approx. backlog drain time
  = Backlogged messages / Net drain rate once intake is controlled
~~~

For example, producers emit 900 messages/second while workers process 700 messages/second. Backlog grows by ~200 messages/second. After 10 minutes, nearly 120,000 messages accumulate unless throttled or scaled.

Autoscaling workers by queue depth or oldest-message age helps, provided database and external API concurrency limits are respected. Unbounded consumer scaling can overload dependencies and trigger retry storms.

### 5.5. Dependency-Wide Capacity Table

A capacity table should document:

| Component | Design Demand | Measured Capacity / Limit | Bottleneck | Redundancy |
| --- | --- | --- | --- | --- |
| API compute | 500 RPS peak | 120 RPS/instance benchmarked | CPU, p95 latency | N+1 and single-zone loss |
| Database | 1,000 queries/s, 150 write txns/s | Per benchmark and DB quota | IOPS, connections, locks | HA, replicas, backups |
| Workers | 800 messages/s | 250 messages/s/worker | CPU and downstream API | Queue buffer, worker pool |
| Cache | 20,000 ops/s | Per instance/cluster benchmark | Memory, network, hot keys | Replication and failover |
| NAT/egress | 4 Gbps and peak connections | Service quota/throughput | Ports, bandwidth, quotas | Multi-gateway/egress paths if supported |

These numbers are illustrative examples, not provider benchmarks or quotas.

## 6. Resource Redundancy and N+1 Models

### 6.1. Redundancy by Failure Unit

Do not simply ask "how many instances?" Ask which failure level you must survive:

- **Process/instance:** a single process or VM fails.
- **Node:** a physical host or worker node goes down.
- **Rack/power/network segment:** resources sharing physical power or networking.
- **Availability zone:** a failure domain within a region.
- **Region:** an entire cloud region or regional service disruption.
- **Provider/dependency:** an external service or cloud provider outage.

Two instances on the same node are not equivalent to two instances across separate nodes. Two nodes in the same zone do not survive a zone failure. Independence claims must rest on verified topology and service SLAs.

### 6.2. N, N+1, and N+2

- **N:** minimum capacity units needed to meet design load when everything is healthy.
- **N+1:** one extra unit to survive a single-unit failure within the defined scope.
- **N+2:** two extra units to survive two independent failures in the same scope, or simultaneous maintenance plus a failure.

N+1 never means "the system cannot go down." It only describes surviving capacity assuming one unit fails. If two instances sit in the same zone and that zone fails, both can drop simultaneously.

### 6.3. Active-Active vs. Active-Passive

| Model | How It Works | Advantages | Trade-offs |
| --- | --- | --- | --- |
| **Active-active** | Multiple units serve traffic concurrently | Uses reserve capacity during normal traffic; can route closer to users | Must manage state, sync, routing, and correlated failures |
| **Active-passive** | One unit serves; the other stands by or runs minimally | Simpler write-path control in some architectures | Standby resources still cost money; failover activation and data checks take time |
| **Warm standby** | Standby runs scaled-down and scales up on failover | Balances cost and recovery time | Scale-up can lag; failover capacity may be constrained |
| **Pilot light** | Keeps only minimal core foundations; launches compute on DR | Lower ongoing cost | RTO depends on provisioning steps, quotas, startup, and checks |
| **Backup/restore** | Restores from backups into a fresh environment | Protects against data corruption and major disasters | Longest RTO; requires readable backups, active keys, and tested runbooks |

No redundancy model fits every workload. Weigh business criticality, RTO/RPO, data statefulness, operational capability, and budget.

### 6.4. Redundant Compute with Ignored Dependencies

An N+1 API cluster still fails when:

- The database has a single instance or runs out of connections.
- Brokers, DNS, NAT, secret managers, or identity endpoints fail.
- Load balancer quotas fall below failover traffic.
- Standby regions lack approved instance or IP quotas.
- Data replicas lag beyond RPO.
- Images/containers are uncached and startup depends on an unreachable artifact registry.
- Autoscalers or control planes degrade right when scaling is needed.

Analyze redundancy across **dependencies and failure modes**, not just compute boxes on a diagram.

## 7. Scaling: Growing Capacity the Right Way

### 7.1. Vertical Scaling (Scale Up)

Increase CPU, RAM, IOPS, or size of a single node/instance.

**Best for:** hard-to-shard workloads, databases, or legacy apps needing simple short-term capacity boosts.

**Limits:** instance size ceilings, downtime/restarts on resize, steep cost curves, single points of failure, and workloads unable to exploit extra cores.

### 7.2. Horizontal Scaling (Scale Out)

Add identical instances/nodes/workers to share the load.

**Best for:** stateless APIs, splittable workers, and workloads with independent requests.

**Limits:** sessions/state must be externalized or rebuilt; databases and downstreams can bottleneck; orchestration complexity rises.

### 7.3. Autoscaling

Autoscaling adjusts resource counts or sizes by policy. Common modes:

| Scaling Type | Signal | When Used |
| --- | --- | --- |
| Target tracking | CPU, memory, requests/instance, custom metrics | Holding a metric near a chosen target |
| Step scaling | Metrics crossing tiered thresholds | Reacting aggressively to steep surges |
| Scheduled scaling | Known calendar schedules | Events, business hours, recurring batches |
| Predictive scaling | Historical load patterns and forecasts | Predictably periodic traffic |
| Queue-based scaling | Queue depth, message age, processing lag | Async workers |
| Manual scaling | Operator decision | Special events or static environments |

Autoscaling always has lag: detecting load, making scaling decisions, provisioning compute, pulling images, booting apps, warming caches, and passing health checks. Never rely purely on reactive autoscaling to absorb instantaneous spikes.

### 7.4. Min/Max, Warm Pools, and Scaling Bounds

Every policy must define:

- **Minimum capacity:** floor to preserve availability and baseline responsiveness.
- **Maximum capacity:** ceiling to guard budgets, quotas, and downstreams.
- **Desired capacity:** currently targeted unit count.
- **Cooldown/stabilization:** prevents thrashing up and down on noisy metrics.
- **Warm pools/pre-warmed instances:** cuts startup delay for latency-sensitive workloads.
- **Scale-in protection/draining:** blocks terminating instances mid-transaction or mid-job.

Scale-out and scale-in need symmetric safety: scale-out must pass health checks before taking traffic; scale-in must drain connections, finish/requeue work, and preserve valid sessions.

## 8. Buffer Capacity and Headroom Principles

### 8.1. Why Never Run Continuously Near Limits?

When utilization nears 100%, a tiny load bump grows queues, spikes latency, and triggers client retries that add even more load. Slow requests hold connections open longer, inflating concurrency and creating a cascading overload spiral.

**Headroom** absorbs spikes, forecast errors, scale-up lag, latency variance, and single-component failures. However, there is no universal percentage—derive headroom from load tests, failure scenarios, and scaling lead times.

### 8.2. Example Headroom Calculation by Load

Suppose each instance provides 120 RPS effective capacity and you target operating at up to 70% of that under normal peaks:

~~~text
Target capacity per instance = 120 * 70% = 84 RPS
Peak demand = 500 RPS
Instances for target utilization = ceil(500 / 84) = 6
~~~

To survive losing one instance independently, you may need at least 7; to survive zone loss, recalculate over surviving instances after a zone drops. The 70% figure is illustrative—pick targets only after testing confirms latency and stability.

### 8.3. Tie Headroom to Scaling Lead Time

If demand climbs 20% per minute and the autoscaler takes 3 minutes to launch ready instances, reserve enough headroom to absorb 3 minutes of growth. Likewise, on zone loss, surviving capacity must absorb the traffic immediately if RTO does not allow waiting for scale-out.

Plans can combine:

- Provisioned baseline for minimum load and availability targets.
- Headroom covering normal variance and scaling lag.
- Scheduled pre-scaling for predictable peaks.
- Rate limits/backpressure beyond max capacity.
- Load shedding or disabling non-critical features to protect core business flows.

## 9. Autoscaling Does Not Replace Load Design

### 9.1. Prerequisites for Effective Scale-Out

Applications should be stateless or store state externally; instances must boot independently, fetch configs/secrets safely, pass health checks, and serve consistently. If startup runs lengthy migrations or slow cache warming, scale-out arrives too late.

### 9.2. Picking the Right Signals

CPU is easy to measure but often the wrong signal. For I/O-bound APIs, requests per instance, active requests, latency, or queue depth reflect demand better. For workers, oldest-message age signals business delay far better than worker CPU.

Never scale on noisy or heavily lagging metrics. Tie signals directly to bottlenecks and evaluate alongside dependency limits.

### 9.3. Backpressure, Rate Limiting, and Load Shedding

When load exceeds serving capacity:

- **Backpressure:** slow producers or reject new intake when consumers fall behind.
- **Rate limiting:** cap requests by user, tenant, token, or operation type.
- **Queue buffering:** absorb short spikes for deferrable work.
- **Load shedding:** drop low-priority work to preserve resources for critical paths.
- **Graceful degradation:** disable secondary features, serve cached results, reduce detail, or defer reports.

For example, during a search traffic spike, return recent cached results or disable heavy filters while protecting booking creation/cancellation. Degradation rules must be business-approved and surfaced clearly in the UI.

## 10. Cloud Quotas and Service Limits

Theoretical capacity means nothing if cloud quotas block scaling:

- vCPUs, instances, nodes, or IP addresses per region.
- Load balancers, target groups, NAT gateways, public IPs, and connections.
- API request rates, control-plane rate limits, DB connections, storage throughput.
- Volumes, total storage, snapshots, queues, subscriptions, or concurrent functions.
- Network routes, security rules, attachments, and global resources.

**Service quotas differ from capacity benchmarks.** Benchmarks tell you what a workload handles under test; quotas tell you how many resources the platform lets you create or use. Both must be sufficient.

### 10.1. Planning Quotas for Failure Scenarios

If each region normally runs 20 instances and losing one region shifts all traffic to the survivor, the standby region may need double capacity. Request quotas for **failover peaks**, not average usage. Audit quotas by account/project, region, instance type, and dependent services.

Never wait until an outage to request quota increases; approvals and propagation take time. Some quotas adjust automatically, while others require support tickets.

### 10.2. Third-Party Dependency Quotas

Payment APIs, email, SMS, maps, identity providers, and external data feeds also enforce limits. Scaling APIs or workers can breach partner rate limits. Inventory these dependencies, enforce concurrency caps, backoff, circuit breakers, and fallback plans when third-party quotas exhaust.

## 11. Load Testing and Capacity Verification

### 11.1. Test Types

| Test Type | Goal | Execution |
| --- | --- | --- |
| **Load test** | Verify behavior at target load | Ramp to expected load and observe latency/errors |
| **Stress test** | Find limits and failure modes | Push past design load in controlled steps |
| **Spike test** | Verify bursts and scale speed | Surge suddenly, hold briefly, measure reaction time |
| **Soak/endurance test** | Catch long-run degradation | Sustain steady load for hours; watch leaks, queues, storage |
| **Volume test** | Test large datasets | Use production-like storage/row volumes |
| **Failover test** | Verify surviving capacity on failure | Remove instances/nodes/zones or inject dependency faults |
| **Recovery test** | Validate post-outage restoration | Restore DB, workers, queues, caches and measure timings |

### 11.2. Test Data Must Be Representative

Benchmarking against an empty table and warm cache produces misleadingly rosy numbers. Simulate realistic payloads, query distributions, cache hit/miss ratios, tenant counts, hot keys, concurrency, large datasets, and retry storms.

Never run heavy load tests against production or third-party partners without explicit approval and safeguards. Use isolated environments, respect provider limits, and scrub unnecessary real user data.

### 11.3. Observe Multiple Layers During One Run

At minimum, monitor:

- Request rate, completed throughput, error rate, and p50/p95/p99 latency.
- CPU, memory, throttling, restarts, GC, threads, and active requests.
- Database CPU, IOPS, locks, connection pools, slow queries, storage, and replication lag.
- Queue depth, oldest-message age, consumer lag, retries, and DLQs.
- Network throughput, retransmissions, connection counts, gateway/NAT saturation.
- Autoscaler decisions, provisioning lag, boot, health checks, warm-up, and scale-in.
- Cost and resource footprint generated during the test.

Identify the **first bottleneck** and the next bottleneck uncovered once the first is fixed. Adding API capacity often exposes DB limits; scaling the DB often exposes network or lock contention.

## 12. Capacity During Rollouts, Maintenance, and Recovery

### 12.1. Rolling Deployments

During rolling updates, some instances leave the pool while new versions boot. Surviving capacity must handle live load throughout the rollout.

For example, a 10-instance group allowing 2 unavailable instances during rollout loses 20% capacity. If normal traffic already consumes ~100% of 10 instances, deployments cause overload. Account for surge capacity, `maxUnavailable`/`maxSurge`, startup duration, readiness, and draining time.

### 12.2. Blue-Green and Canary

- **Blue-green:** runs two environments and shifts traffic. Fast traffic rollback, but temporarily doubles compute spend and requires dual-compatible DB migrations.
- **Canary:** shifts a slice of traffic to the new release. Needs capacity for both versions, per-version error tracking, and enough traffic for statistically valid signals.
- **Rolling:** replaces instances incrementally. Saves idle overhead, but requires spare capacity and version compatibility.

### 12.3. Maintenance and Incidents

Capacity budgets must absorb drained nodes, unavailable zones, managed service upgrades, backups, restores, and post-outage recovery surges. Background batches or re-indexing can compete with online requests for CPU, I/O, and connections. Enforce schedules, priorities, throttling, and resource caps on background work.

During recovery, drained queue backlogs can create a **second traffic spike**. Launching all workers at full throttle can overwhelm the database or external APIs. Recovery runbooks need controlled replay/consumer ramp-up rates and abort criteria.

## 13. End-to-End Example: Capacity Planning for a Booking Platform

Suppose a booking platform has illustrative targets:

- 500 requests/second peak traffic.
- One Booking API instance sustains 120 RPS within agreed latency/error thresholds.
- Must survive losing one availability zone.
- Three zones can distribute resources evenly and the load balancer shifts traffic to surviving zones.
- The database is a multi-zone HA managed service, though its throughput must be benchmarked independently.

### 13.1. Computing API Capacity

If sizing solely for healthy load across three zones:

~~~text
Minimum N for throughput = ceil(500 / 120) = 5 instances
Balanced 3-zone layout: 2 + 2 + 1
~~~

Losing a zone holding two instances leaves three instances:

~~~text
Surviving capacity = 3 * 120 = 360 RPS
~~~

That falls short of 500 RPS. Using 3 + 3 + 3:

~~~text
After losing 1 zone: 2 zones * 3 instances = 6 instances
Surviving capacity = 6 * 120 = 720 RPS
~~~

Nine instances satisfy the simplified 500 RPS single-zone-loss model. However, targeting 70% utilization leaves post-zone-loss design capacity at:

~~~text
6 * 120 * 70% = 504 RPS
~~~

That barely clears 500 RPS, meaning benchmark variance, request skew, or background load could erase headroom. You may need higher per-zone capacity, larger instances, extra instances per zone, or explicit peak rate limits.

### 13.2. Checking the Database

Never infer DB capacity from API instance count. Measure read/write queries per request. If an average request runs 3 read queries and 1 write transaction:

~~~text
Database read QPS = 500 * 3 = 1,500
Database write txn/s = 500 * 1 = 500
~~~

If only 15% of requests write, write txns/s is closer to 75. Distinguish SQL statements, transactions, and physical disk writes. Benchmarks must validate connection pooling, locks, IOPS, indexes, and peak latency.

### 13.3. Checking Workers and Queues

Suppose 20% of requests emit an event. At 500 RPS:

~~~text
Event rate = 500 * 20% = 100 events/s
~~~

One worker sustains 25 events/second within acceptable error rates. To survive losing one worker:

~~~text
N = ceil(100 / 25) = 4
N+1 = 5 workers
~~~

To survive losing a zone, distribute workers across zones, calculate surviving capacity, and check brokers, partitions, consumer groups, and downstream rate limits.

### 13.4. Sample Capacity Planning Table

| Component | Peak / Demand | Assumed Capacity | Planned Layout | Verification Scenario |
| --- | --- | --- | --- | --- |
| Booking API | 500 RPS | 120 RPS/instance benchmarked | 3 instances/zone, 3 zones | Lose 1 zone, sustain 500 RPS, check p95/p99 |
| Database | 1,500 read QPS; writes per txn ratio | Needs benchmark | Managed HA, capped pools | DB load, failover, connection recovery |
| Event workers | 100 events/s | 25 events/s/worker | Multi-zone spread with headroom | Worker/zone loss, backlog, replay |
| Broker | 100 events/s plus bursts/retries | Per partition/quota benchmark | Replication per service SLA | Broker node loss, consumer lag, DLQ |
| Network/API egress | Per payload and connections | Quotas, throughput, NAT benchmark | Sufficient gateways/paths per topology | Peak connections, TLS, failover |

All numbers are illustrative. Real projects must record benchmark sources, app versions, instance types, test datasets, timestamps, service limits, and approving owners.

### 13.5. Budget and Risk Acceptance

Nine instances across three zones cost more compute than five instances—yet five instances fail zone loss under these assumptions. The team can evaluate:

- Larger single instances, though benchmarked and weighed against single-point failures and scale-up limits.
- Reducing peak demand via caching, query tuning, or workload splitting.
- Degrading non-essential services during a zone outage.
- Scheduled/predictive scaling for known peaks, without relying on slow scaling for instant capacity.
- Adjusting SLOs or fault-tolerance targets only with explicit business owner sign-off and documented risk.

Never trim redundant capacity while keeping the exact same availability promise. Every trade-off must show post-failure capacity and cost under those terms.

## 14. Capacity Observability and Alerting

### 14.1. Essential Signal Set

| Group | Metrics / Alerts | Purpose |
| --- | --- | --- |
| Compute | CPU, working set memory, throttling, restarts, OOMs | Detect saturation or memory exhaustion |
| Application | RPS, concurrency, p95/p99 latency, error rates | Detect load exceeding effective capacity |
| Scaling | Desired/current/min/max, scaling events, provisioning lag | Catch autoscalers falling behind |
| Database | Connections, IOPS, locks, slow queries, storage, lag | Catch data-layer bottlenecks |
| Queue | Depth, oldest-message age, consumer lag, retries/DLQs | Detect growing backlogs and slow recovery |
| Network | Throughput, connections, retransmits, gateway saturation | Spot transport limits |
| Quotas | Usage/limit ratios, remaining headroom, quota requests | Prevent scaling failures from account limits |
| Cost | Compute hours, egress, storage, idle/warm resources | Track redundancy and variable load costs |

### 14.2. Time-Window and Trend-Based Thresholds

A static "CPU > 80%" alert can be too noisy or too late. Combine:

- Sustained utilization thresholds over a defined window.
- Growth trends and projected time-to-saturation.
- Correlation with request rate, latency, and errors.
- Current instance counts relative to maximum capacity.
- Remaining headroom when simulating single-zone loss.

For instance, alerting when queue age stays over 2 minutes for 5 consecutive minutes reflects business lag better than worker CPU alone. Base thresholds on SLOs and real processing profiles.

### 14.3. Periodic Capacity Reviews

An effective review covers:

1. Comparing forecasts against actual traffic, data growth, and utilization.
2. Reviewing peak loads and unexpected spikes in the recent period.
3. Inspecting autoscaling events, provisioning lead times, quotas, and dependency incidents.
4. Assessing surviving capacity under instance/zone/region failures and rollouts.
5. Forecasting 3–12 months ahead from growth trends and product roadmaps.
6. Updating costs, budget commitments, reserved capacity/commitments where appropriate, and residual risks.

## 15. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sizing to average load | Overloads on peaks and bursts | Forecast peak, burst, sustained, and failure loads |
| Relying on vCPU/RAM without benchmarks | Misjudges real usable capacity | Benchmark with representative data and SLOs |
| Achieving instance N+1 while ignoring zones | Zone failure wipes multiple instances at once | Calculate by failure domain |
| Autoscaling only the API | DB, broker, or quotas become the bottleneck | Plan capacity across all dependencies |
| Unbounded scale-out | Retry storms and downstream collapse | Max caps, backpressure, rate limits, load shedding |
| Ignoring startup time | Autoscaling reacts too slowly to spikes | Headroom, warm pools, scheduled scaling |
| Ignoring rollouts and maintenance | Deploys drop capacity below peak | Appropriate surge capacity and `maxUnavailable` |
| Forgetting standby region quotas | DR cannot launch enough resources | Audit and request quotas in advance |
| Watching CPU alone | Misses I/O, connection, memory, and queue saturation | Multi-signal dashboards and latency tracking |
| Skipping failover drills | Redundancy assumptions remain unproven | Game days, failover, and recovery tests |
| Blindly doubling everything | High spend with shared single points of failure | Risk analysis and targeted redundancy |
| Missing scale-in protection/draining | Requests or jobs get cut mid-flight | Graceful shutdown and queue visibility timeouts |

## 16. Applied Exercises

### Exercise A — Instance Count

An API has 720 RPS peak demand. Load tests confirm one instance sustains 150 RPS at target p95 latency. The system must survive losing one instance.

**Question:** How many instances are needed at minimum under N+1?

**Hint:** `N = ceil(720/150) = 5`. `N+1 = 6` instances. After losing one instance, five survivors provide 750 RPS of benchmarked capacity. Next, check zone distribution and other dependencies.

### Exercise B — Zone Loss

A cluster spans three zones with two instances per zone, each handling 100 RPS. Design peak is 450 RPS. The load balancer routes traffic to surviving zones.

**Question:** Does it survive losing one zone at peak?

**Hint:** Losing a zone leaves 4 instances providing 400 RPS nominal capacity, short of 450 RPS. Add instances per zone or improve per-instance capacity, then verify DB and network handling of concentrated traffic.

### Exercise C — Growing Queue Backlog

Producers emit 1,000 messages/s. Each worker handles 180 messages/s. Five workers currently run.

**Question:** Is the backlog growing or shrinking? How many workers match the arrival rate before redundancy?

**Hint:** Current capacity is `5 × 180 = 900` messages/s, so backlog grows by 100 messages/s. Minimum is `ceil(1,000/180) = 6` workers. Add headroom and check downstream limits before scaling to six or higher.

### Exercise D — Autoscaling Too Slow

An app jumps from 100 to 1,000 RPS in 15 seconds. The autoscaler takes ~90 seconds to boot instances and pass readiness probes.

**Question:** Why does merely raising max instances not solve this?

**Hint:** New capacity is not ready during the 15-second spike. You need baseline/headroom, pre-warmed or scheduled capacity for predictable events, rate limits/queues to buffer, faster startup, and dependency headroom.

### Exercise E — DR Cannot Launch Compute

The primary region runs 40 instances at peak. The DR region has an approved quota of only 20 instances and an autoscaler max of 30 instances.

**Question:** On full traffic failover, where is the bottleneck and what must happen before an incident?

**Hint:** DR can launch at most 20 (or 30) per actual quota, falling short of the 40 required. Audit regional/type quotas, recalculate optimized load, request quota increases, define controlled load shedding or degraded targets, and rehearse failover.

## 17. Pre-Approval Capacity Plan Checklist

- [ ] Modeled average, peak, burst, sustained, seasonal, growth, and failure loads.
- [ ] Classified endpoints/workloads by resource cost and business criticality.
- [ ] Measured per-instance capacity via representative benchmarks at target latency/errors.
- [ ] Forecasted CPU, memory, network, database, storage, IOPS, queues, and connections.
- [ ] Recalculated surviving resources after instance/node/zone/region loss per required failure domain.
- [ ] Sized headroom for load variance, scaling lag, and risk tolerance.
- [ ] Configured autoscaling min/max, proper metrics, cooldowns, warm-up, draining, and scale-in rules.
- [ ] Verified cloud provider and third-party quotas/rate limits at failover scale.
- [ ] Confirmed rolling deploys, backups, batches, recovery, and queue replays never starve critical paths.
- [ ] Executed load/stress/spike/soak/failover tests and archived benchmarks, environments, versions, and results.
- [ ] Deployed dashboards/alerts for saturation, latency, backlogs, replication lag, scaling, quotas, and cost.
- [ ] Implemented backpressure, rate limiting, load shedding, and graceful degradation beyond max capacity.
- [ ] Assigned owners, budgets, review cadences, and forecast-update processes.

**Key takeaway:** capacity planning answers **how much capacity the system needs for expected loads**; redundancy answers **whether enough capacity survives when an infrastructure scope fails**. Numbers are only trustworthy when measured on representative workloads, calculated per failure domain, and proven through drills. Good cloud architecture maintains headroom for user experience and recovery while bounding expansion through quotas, load controls, budgets, and clear operational ownership.
