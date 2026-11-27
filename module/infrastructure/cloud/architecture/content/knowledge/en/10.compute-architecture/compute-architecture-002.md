# Sizing Resources by CPU, Memory, I/O, and Load Characteristics

## 1. Why Must Resource Sizing Be Evidence-Based?

When deploying applications in the cloud, choosing a VM, container, node, or serverless configuration that is too small can cause high latency, timeouts, out-of-memory errors, and reduced availability. Over-provisioning drives up fixed costs, wastes capacity, and makes budget forecasting difficult. The right configuration must be derived from **workload characteristics and service objectives**, then verified through measurements and load testing.

**Sizing (resource sizing)** is the process of estimating and validating compute, memory, storage, network capacity, and related limits so an application meets business goals under expected load. It is not just picking vCPUs and GB of RAM. A service can have spare CPU yet still run slowly due to database I/O; have plenty of RAM yet fail from file descriptor limits; or have enough compute yet bottleneck on network connections or quota limits.

This lesson belongs to the **Compute Architecture** chapter of the **CLOUD_ARCHITECTURE** module, connecting business requirements to compute selection and trade-offs across reliability, security, scalability, cost, and operations under **Well-Architected** principles.

After this lesson, you will be able to:

- Classify workloads as CPU-bound, memory-bound, I/O-bound, network-bound, and bursty vs. steady-state.
- Choose meaningful metrics rather than relying solely on average CPU.
- Estimate initial configurations from load, concurrency, latency, and headroom.
- Design benchmarks, load tests, stress tests, and post-failure load checks.
- Define resource limits, autoscaling, and post-deployment monitoring signals.

## 2. Starting from Demand and Load Shapes

Before selecting a configuration, describe **what the application does and how traffic arrives**. A booking system, a lookup API, and a video processor have completely different profiles even when running in the same cloud.

### 2.1. Intake Questionnaire

| Category | Questions | Example Data to Collect |
|---|---|---|
| Scale | How many active users, requests, or jobs per second/minute? | 120 requests/sec average, 400 requests/sec peak hours |
| Concurrency | How many requests/jobs are processed simultaneously? | 250 in-flight requests; 40 concurrent worker jobs |
| Latency | What are the p50/p95/p99 targets? | p95 under 300 ms for read APIs |
| Processing nature | Compute-heavy, large in-memory datasets, or waiting on I/O? | Image encoding, data analytics, database queries |
| Data size | How large are requests/responses, payloads, files, and working sets? | 20 KB JSON, 30 MB files, 4 GB cache working set |
| Load timing | Is load steady or spiky? | Time-of-day load, launch-window bursts |
| Growth | Over what horizon are users and data projected to grow? | 30% growth over 12 months, assumption to verify |
| Dependencies | What limits do databases, queues, or partner APIs have? | 1,000 max connections, partner API capped at 100 req/sec |
| Reliability | What happens when an instance or AZ is lost? | Surviving instances must absorb most of the load |

Separate **average load**, **peak load**, **burst load**, and **growth load**. A configuration that passes a 15-minute benchmark does not prove it will handle seasonal peaks, nor does it prove sufficient capacity remains if an AZ fails.

### 2.2. Common Load Shapes

| Shape | Characteristics | Sizing Implications |
|---|---|---|
| **Steady-state** | Relatively stable load with little variance | Can choose fairly fixed baseline capacity and optimize utilization |
| **Diurnal/seasonal** | Load varies by hour, day, or season | Requires cycle observation, scheduled scaling, or autoscaling |
| **Burst** | Rapid surges over short periods | Needs headroom, queues/buffers, fast scaling, and protective limits |
| **Spiky/event-driven** | Jobs arrive on events, potentially irregular | Scale by backlog, processing rate, and completion deadlines |
| **Long-running** | Individual tasks run long, holding memory or CPU | Evaluate runtime duration, concurrency, memory growth, and interruption |
| **Batch** | Processes large volumes within defined time windows | Optimize throughput, cost per job, and execution schedule |

One application can combine multiple shapes: an API takes bursty traffic while workers drain a queue at a steady pace. Size each workload separately instead of forcing all components onto the same configuration.

## 3. Identifying CPU-Bound, Memory-Bound, I/O-Bound, and Network-Bound Workloads

This classification helps form initial hypotheses about bottlenecks. In practice, a workload can be constrained by multiple resources simultaneously or by an external dependency.

### 3.1. CPU-Bound

A **CPU-bound** workload is one whose execution time is primarily limited by compute power. Examples: encryption/decryption, image compression, simulations, heavy JSON parsing, inference, or analytical algorithms.

Common symptoms:

- High process or node CPU utilization under load; rising run queues and requests waiting for CPU.
- Increasing concurrent requests fails to increase throughput proportionally, while p95/p99 latency climbs.
- Profiling shows time concentrated in computation, serialization, compression, or garbage collection.

Mitigation: optimize algorithms and code first; then check CPU generation, vCPU count, single-core performance, parallelism, and CPU quota limits. More vCPUs do not always help a single-threaded app; the software must be able to exploit parallelism.

### 3.2. Memory-Bound

A **memory-bound** workload requires large RAM capacity or high memory bandwidth. Examples: in-memory caches, large table processing, large-heap JVMs, data analytics, or high worker concurrency.

Symptoms:

- Working set approaches the limit; processes hit OOM or containers are OOMKilled.
- Paging/swapping increases, garbage collection runs frequently, or pause times lengthen.
- Latency spikes when datasets exceed cache size or concurrency rises.
- RSS/heap climbs steadily over time, potentially indicating a memory leak.

Memory sizing must include not just business data, but also heap/runtime, native memory, thread stacks, buffers, caches, sidecars/agents, and OS overhead. For containers, the **memory limit** is a hard ceiling enforced by the runtime/orchestrator; setting the limit right at the peak observed in a short test can trigger OOMs when traffic shifts.

### 3.3. I/O-Bound

An **I/O-bound** workload spends its time waiting on storage reads/writes or responses from databases, queues, or filesystems. CPU may look low while requests remain slow.

Metrics to inspect:

- IOPS (read/write operations per second).
- Throughput (MB/s or GB/s).
- Read/write latency, especially p95/p99.
- Queue depth, I/O wait time, cache hit rate.
- Database connection count and query duration.

Example: a lookup API reading many records may not benefit from extra vCPUs if the database has hit its IOPS ceiling or queries lack indexes. Optimize queries, indexes, caching, data partitioning, or upgrade storage tiers before adding API compute.

### 3.4. Network-Bound

A **network-bound** workload is constrained by bandwidth, latency, connection counts, packet rates, or external network dependencies. Examples: APIs calling multiple SaaS services, large file transfers, streaming, or high-hop microservice chains.

Symptoms:

- Low CPU while requests stall in connect/TLS/remote responses.
- Network throughput, packet drops, retransmissions, or connection counts approach limits.
- Latency jumps sharply when remote dependencies slow down; connection pools exhaust.
- Timeout, DNS, or NAT/egress gateway errors appear under high load.

Distinguish **in-app processing time** from **network wait time**. Inspect distributed traces, network metrics, DNS/TLS timings, connection pools, and partner service limits. Adding vCPUs will not fix an external API that responds slowly.

### 3.5. Quick Comparison Table

| Bottleneck Type | CPU | RAM | I/O/Network | Priority Checks |
|---|---|---|---|---|
| CPU-bound | Often high or quota-throttled | Usually normal | Not the primary limit | CPU profiling, parallelism, vCPU/clock speed |
| Memory-bound | May be moderate | Near limit/working set | May rise due to paging | RSS/heap, GC, cache, memory limits |
| Storage/database I/O-bound | May be low | Usually normal | High IOPS/latency/queue depth | Query plans, storage tier, IOPS, caching |
| Network-bound | May be low | Usually normal | Latency/packets/connections/bandwidth | Traces, DNS/TLS, egress, pools, dependencies |

Never diagnose a bottleneck from a single metric. For example, high CPU can be caused by a retry storm triggered by a slow database; high RAM may reflect a healthy cache rather than a memory leak. Correlate metrics, traces, logs, and controlled experiments.

## 4. Measure Before Choosing a Configuration

### 4.1. Metrics to Collect

Measure across **application**, **process/container/VM**, and **dependent services**.

| Layer | Useful Metrics |
|---|---|
| Request | Requests/s, throughput, in-flight requests, errors by type, p50/p95/p99 latency |
| CPU | Utilization, throttling, load/run queue, CPU time per process |
| Memory | Working set/RSS, heap, cache, allocation rate, GC pauses, OOMs |
| Disk/storage | IOPS, throughput, read/write latency, queue depth, capacity and growth |
| Network | Bytes/s, packets/s, packet loss/retransmits, connection count, connect/TLS time |
| Runtime | Thread count, event-loop lag, connection pools, queue backlog, worker concurrency |
| Dependency | Database query latency, DB connections, cache hit rate, partner API latency/errors |

Collect measurements over the same time window and tag metadata such as app version, instance type, AZ, workload, replica count, and load level. Looking only at 5-minute dashboard averages can hide spikes lasting a few seconds; pick metric granularity suited to the incidents you need to catch.

### 4.2. Latency Percentiles Matter More Than Averages

- **p50** describes the experience of the median request.
- **p95** shows the threshold exceeded by the slowest 5% of requests.
- **p99** reveals the slow tail, often critical for responsive transactions.

For example, p50 = 80 ms, p95 = 250 ms, and p99 = 3 seconds can indicate a subset of requests delayed by large queries, GC pauses, cold starts, or dependency timeouts. Reporting only "100 ms average latency" hides that user segment's experience.

### 4.3. Measuring Concurrent Load

Throughput and concurrency are linked by Little's Law:

\[
L = \lambda W
\]

Where:

- \(L\) is the average number of requests in the system (concurrency).
- \(\lambda\) is the average throughput (requests/second).
- \(W\) is the average time a request spends in the system (seconds).

For example, if an API processes 200 requests/second and average time in the system is 0.25 seconds, average concurrency is approximately:

\[
L = 200 \times 0.25 = 50
\]

This holds only in steady state and uses **average latency**, not p95. It provides an initial estimate of concurrent in-flight/queued requests, but does not tell you how many vCPUs or how much RAM are required. You must combine actual CPU time per request, memory per request, I/O, and application parallelism.

## 5. Estimating Initial CPU and Memory Configurations

### 5.1. Estimating CPU from CPU Time per Request

If you have measured that one request consumes an average of \(t_{cpu}\) CPU-seconds and the target throughput is \(R\) requests/second, ideal CPU core consumption is roughly:

\[
C_{\text{needed}} = R \times t_{cpu}
\]

Example: benchmarks show each request takes 0.012 CPU-seconds; target load is 300 requests/second:

\[
C_{\text{needed}} = 300 \times 0.012 = 3.6 \text{ cores}
\]

If the organization targets roughly 60% CPU utilization at target load, the initial estimate is:

\[
C_{\text{provisioned}} \approx \frac{3.6}{0.60}=6 \text{ vCPUs}
\]

This is a rough estimate for **one workload assuming representative benchmarks**. Add demand from agents/sidecars, background tasks, bursts, and runtime overhead, and verify whether the utilization target still meets latency goals. Targeting 60% does not mean 60% CPU is optimal for every app; decide based on p95/p99 measurements and fault tolerance.

### 5.2. Estimating Memory

A basic estimation model:

\[
M_{\text{total}} =
M_{\text{runtime}}+
M_{\text{working set}}+
M_{\text{concurrency}}+
M_{\text{cache}}+
M_{\text{sidecars}}+
M_{\text{headroom}}
\]

Each component must be measured or estimated from runtime settings. For Java, distinguish **heap** from **RSS/total process memory**: heap does not cover metaspace, code cache, direct/native buffers, thread stacks, or native libraries. For containers, verify total usable memory fits within the actual memory limit.

Example: an application measures 450 MB runtime/native overhead, 1.1 GB working set, 0.8 GB cache, 0.3 GB concurrency buffers, and 0.2 GB sidecars. Baseline total is 2.85 GB. Adding 25% headroom yields about 3.56 GB; you can test a 4 GB configuration under benchmarks and spike tests. These numbers are **illustrative**, not universal sizing recommendations.

Headroom must reflect **peak scenarios and growth**, not merely a fixed percentage added to averages. Track OOMs, RSS, allocations, and GC during soak tests to catch memory leaks or upward drift over time.

### 5.3. Single-Core, Multi-Core, and CPU Architecture

Two machines with the same vCPU count do not necessarily perform equally. Check:

- CPU generation, per-vCPU performance, clock speed/architecture, and burst credits if using burstable instances.
- Whether the application parallelizes well; a single bottlenecked thread cannot utilize many vCPUs.
- CPU sharing/oversubscription ratios and quotas in containers/orchestrators.
- Compatibility with instruction sets, runtimes, and native libraries.
- Hourly/unit compute pricing, regional limits, and capacity reservation availability.

Select a few candidate sizes from small to large within the same family, benchmark on equivalent workloads, and compare **cost per completed request/job** rather than hourly price alone.

## 6. Sizing I/O, Storage, and Network

### 6.1. Disk and Storage I/O

Estimate demand from both **throughput** and **IOPS**. Sequential reads of large files may need high throughput with low IOPS; an OLTP database with many small transactions may need high IOPS and low latency despite modest MB/s throughput.

| Workload | Typical Demand | Sizing Questions |
|---|---|---|
| OLTP Database | Many small reads/writes, low latency, steady IOPS | Peak IOPS? Write amplification? Log/WAL volume? |
| Data warehouse/analytics | Large file scans, high throughput | Required MB/s? Can object storage/columnar formats be used? |
| File/media processing | Large file reads/writes | File sizes, concurrent jobs, shared vs. ephemeral storage? |
| Cache | Fast access, working set in RAM or dedicated storage | Hit rate, eviction, durability, and warm-up speed? |
| Batch | Many files or bulk datasets | Processing window, total bytes, worker count, completion time? |

Examine volume, instance, filesystem, database, and network IOPS/throughput limits together. Raising volume IOPS will not help if instance bandwidth is capped or the database accepts too few connections.

### 6.2. Network and Connections

Estimate traffic:

\[
B_{\text{network}} \approx R \times S_{\text{avg}}
\]

Where \(R\) is requests/second and \(S_{avg}\) is average bytes transferred per request (inspect both inbound and outbound directions separately). For example, 300 requests/second with an average 40 KB response creates roughly 12,000 KB/s, or ~12 MB/s before protocol overhead, TLS, retries, and background traffic.

For connections, account for:

- Concurrent connections to databases, caches, and external APIs.
- Per-replica pool size: **max total pool = pool per replica × replica count**. Autoscaling replicas up can push databases past connection limits.
- Timeouts, keepalives, retries, DNS/TLS handshakes, ephemeral ports, and NAT/egress limits if applicable.
- Actual throughput and bandwidth caps per instance type/network interface.

An API scaling from 4 to 30 replicas can multiply connection pools 30× if each replica uses a fixed pool. Set global concurrency/pool limits, use proper pooling, and verify the database handles post-scale-out load.

## 7. Benchmarking and Load Testing Process

Do not pick machine sizes from marketing numbers or a single uncontrolled benchmark run. Build a repeatable process:

1. **Define objectives:** throughput, p95/p99 latency, error rate, job duration, load level, and completion deadlines.
2. **Create representative data:** realistic payload sizes, working sets, key distributions, cache hit/miss ratios, and tenant counts.
3. **Hold test variables constant:** same app version, runtime, region, network, database tier, replica count, and load generator.
4. **Warm-up:** avoid drawing conclusions from cold caches/JIT initialization if production runs warm; also measure cold starts separately when realistic.
5. **Step up load:** ramp from baseline to expected peak and stress levels; record where throughput plateaus or latency breaches SLOs.
6. **Compare configurations:** vary CPU/RAM/I/O intentionally one factor at a time to understand impact; avoid changing too many variables at once.
7. **Soak test:** run long enough to uncover memory leaks, file descriptor leaks, cache churn, and gradual degradation.
8. **Failure/load test:** verify losing a replica/AZ, slow dependencies, retries, queue backlogs, and scale-out speed.
9. **Record results and cost:** p50/p95/p99, throughput, errors, CPU, RSS, I/O, network, and cost for equal work completed.

### 7.1. Different Test Types

| Test Type | Goal | Load Pattern |
|---|---|---|
| **Load test** | Verify expected load targets | Sustain target load for a sufficient duration |
| **Stress test** | Find limits and degradation modes | Ramp beyond target load until errors spike or throughput stops rising |
| **Spike test** | Verify response to sudden surges | Jump rapidly from low baseline to high load |
| **Soak/endurance test** | Detect leaks or long-term degradation | Hold steady load for hours or an appropriate cycle |
| **Capacity test** | Determine true capacity of a configuration | Increment load in controlled steps, measuring the last point meeting SLOs |
| **Failover test** | Verify remaining capacity after resource loss | Isolate a replica/AZ/dependency as planned |

Every test must have **stop criteria** to avoid accidentally exhausting databases, firing real transactions, or disrupting shared services. Use sandboxes and synthetic data whenever possible; if testing in production, require approval and blast-radius limits.

### 7.2. Sample Benchmark Results

Suppose an API is tested across three compute configurations with the same database and the same 250 requests/second load:

| Tested Config | CPU p95 | Peak RAM | API p95 Latency | Error Rate | Relative Cost/Hour |
|---|---:|---:|---:|---:|---:|
| 2 vCPU / 4 GB | 92% | 3.4 GB | 720 ms | 1.8% | 1.0 |
| 4 vCPU / 8 GB | 61% | 3.6 GB | 280 ms | 0.15% | 1.9 |
| 8 vCPU / 16 GB | 34% | 3.8 GB | 250 ms | 0.10% | 3.6 |

These are **simulated exercise figures**. If the SLO is p95 under 300 ms and error rate under 0.2%, the 4 vCPU / 8 GB configuration meets targets under test load at lower cost than 8 vCPU / 16 GB. The larger configuration cuts latency by another 30 ms at nearly double the cost; evaluate headroom, bursts, and single-replica loss before finalizing.

Remember this benchmark only measured the API and database under specific conditions. If the database, queue, or third-party services experience different load in production, results may not repeat.

## 8. Selecting Compute Type and Deployment Configuration

Sizing depends on the compute model because each option defines resource boundaries differently:

| Model | Sizing Unit | Characteristics | Risks to Check |
|---|---|---|---|
| VM | vCPU, RAM, disk, network bandwidth | Full OS control, customizable runtime | Patching, capacity, OS tuning, scaling, and HA |
| Container service | CPU/memory requests, limits, replicas, node capacity | Packages workloads and scales per service | CPU throttling, OOMs, bin packing, node pressure |
| Kubernetes | Pod requests/limits, node type/count, autoscaler | Orchestrates diverse services and workloads | Bad requests/limits, unschedulable pods, node pool exhaustion |
| Serverless function | Allocated memory/CPU profile, timeout, concurrency/quotas | No server management, suits supported event/API patterns | Cold starts, concurrency, timeouts, memory, execution limits |
| Batch/job | CPU/RAM per job, parallelism, I/O, completion time | Optimized for batch processing, can use spot/ephemeral resources | Job retries, intermediate data, deadlines, interruptions |

### 8.1. Container Requests and Limits

In an orchestrator such as Kubernetes:

- **CPU request** guides the scheduler in placing pods; **CPU limit** can throttle workloads when exceeded.
- **Memory request** affects scheduling; **memory limit** can cause containers to be OOMKilled if exceeded.
- Setting requests too low causes node overcommit and contention; setting them too high prevents the scheduler from placing pods and wastes capacity.
- Measure percentile usage, peak load, and sidecar overhead before setting requests/limits.

Illustrative configuration example:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "1500m"
    memory: "1536Mi"
```

These values are **not universal recommendations**; base them on profilers and load tests. Also verify how the runtime/orchestrator enforces CPU limits, memory enforcement, and pod QoS classes.

### 8.2. JVM and Container Memory

For Java applications, `-Xmx` must not equal the entire container memory limit. Total RSS includes heap, metaspace, code cache, thread stacks, direct buffers, native libraries, and agents. If a container has a 2 GiB limit and heap is set right at 2 GiB, the process can easily hit OOM even before heap reaches `-Xmx`.

Measure heap occupancy, GC pauses, allocation rate, native memory, and RSS at peak load. Test realistic thread/concurrency counts; adding threads increases stack memory and context switching. Leave adequate runtime headroom and validate with soak tests.

## 9. Autoscaling, Headroom, and Capacity During Failures

### 9.1. Autoscaling Does Not Replace Sizing

Autoscaling adjusts resource counts as load signals change, but still depends on **baseline capacity, scaling speed, quotas, startup time, and dependency limits**.

| Scaling Method | Suitable Signal | Considerations |
|---|---|---|
| CPU-based | Compute-bound workloads where CPU correlates with throughput | Poor fit if CPU is low while requests wait on DB/network |
| Memory-based | Workloads whose working set scales with load | Scale-out does not immediately free memory on existing replicas |
| Request/concurrency-based | APIs handling independent requests | Pick metrics reflecting serving capacity and safe concurrency |
| Queue-depth-based | Workers processing events/jobs | Combine backlog, processing rate, and per-job deadlines |
| Scheduled | Predictable periodic load | Must adjust when traffic behavior shifts |

### 9.2. Capacity and Headroom

If two normal replicas each handle 50% of traffic, losing one forces the surviving replica to absorb the entire load. Post-failure capacity cannot be calculated from healthy cluster-wide capacity alone.

A simple check:

\[
C_{\text{surviving}} \geq D_{\text{peak}}
\]

Where \(C_{surviving}\) is total capacity of surviving replicas under the required failure scenario and \(D_{peak}\) is peak demand to sustain. If the goal is only keeping core functionality alive in degraded mode, explicitly define what is shed or degraded.

For multi-AZ deployments, simulate losing an AZ and verify surviving capacity, database connections, queue consumers, cache warm-up, and egress. For multi-region, add DR region capacity, quotas, and appropriate data promotion mechanisms.

### 9.3. Preventing Scaling from Breaking Dependencies

Suppose an API scales from 5 to 50 replicas, each holding a database pool of up to 30 connections. Theoretical connections jump from 150 to 1,500, exceeding database limits. Before scaling out, calculate total connections across replicas, size pools sensibly, use connection proxies/pooling where suitable, and enforce application concurrency caps.

Rapid scaling can also trigger cold starts, simultaneous cache misses, database load surges, and retry storms. Design rate limits, queues, jitter/backoff, circuit breakers, and warm-up procedures.

## 10. End-to-End Example: Sizing a Booking API

Suppose a system includes a booking API and an email worker:

- Expected load: 200 requests/second normal, 300 requests/second peak.
- Benchmarks show one request uses an average of 0.01 CPU-seconds and each replica's working set is roughly 1.2 GB at target concurrency.
- The API needs p95 under 300 ms; the worker sends emails asynchronously.
- Operational requirement: if one replica or one AZ is lost, remaining replicas must continue serving core transactions.

### 10.1. Estimating CPU for the API

\[
C_{needed}=300 \times 0.01 = 3 \text{ cores}
\]

Targeting 60% utilization at peak load:

\[
C_{provisioned}=\frac{3}{0.60}=5 \text{ vCPUs}
\]

The team could start by testing 2 replicas × 3 vCPUs (6 vCPUs total) as a baseline. However, if the goal is **meeting peak even after losing one replica**, each surviving replica must handle 300 RPS alone. That requires at least ~5 vCPUs per surviving replica under the assumptions above, before overhead and headroom; total healthy provisioned capacity may need to be higher. If spread across two AZs with one replica per AZ, size each replica for AZ loss or adopt an approved degraded mode.

### 10.2. Estimating Memory

Assuming 1.2 GB working set/replica, 0.45 GB runtime/native overhead, 0.15 GB sidecar, and 25% headroom:

\[
M=(1.2+0.45+0.15)\times1.25=2.25\text{ GB}
\]

An initial test configuration could be 3 GB or the nearest supported platform tier, then verify RSS, GC, and OOM behavior at peak concurrency. If caching grows with request volume or data is retained longer, update the estimate.

### 10.3. Workers Need Different Sizing Than APIs

The email worker is more I/O-bound than CPU-bound, and provider wait times can be long. Size it by **queue backlog, average processing time, and deadlines**. If one worker handles 8 messages/second within allowed p95 latency and the queue receives 40 messages/second, at least 5 workers are needed for ideal throughput; test higher counts for headroom and check provider rate limits.

Worker scaling must not cause retry storms. Failed messages need backoff and a DLQ; email sending should be idempotent by booking/event ID to handle duplicate deliveries.

### 10.4. Initial Decision Summary

| Component | Test Configuration | Rationale | Conditions to Verify |
|---|---|---|---|
| Booking API | Managed containers, 2 replicas across AZs; test 5–6 vCPU, 3 GB RAM each | Sized for peak and single-replica loss | Benchmark 1 replica at 300 RPS; p95/error rate; memory/GC |
| Email worker | Scaled separately by queue, moderate CPU, RAM sized for in-flight messages | Mostly waiting on network/provider | Messages/s, backlog, timeouts, rate limits, duplicates |
| Database | Select tier for queries/connections/IOPS and matching HA | API compute cannot solve DB bottlenecks | Slow queries, connection limits, failover, backup/restore |
| Cache (if present) | Measured working set and hit rate | Reduce repeated queries if data allows | Memory eviction, consistency, warm-up, HA |

This is a **starting point for testing**, not a final production spec. Re-measure with representative data, actual pricing, and limits in the target region, then refine sizing from the results.

## 11. Cost Optimization: Balancing Capacity Against Cost

Do not optimize by merely picking the cheapest instance. Compare candidates using:

- **Cost per unit of work:** cost per 1,000 successful requests, per job, or per GB processed.
- **Utilization and performance:** excess or insufficient CPU/RAM, throughput, p95/p99, and error rates.
- **Baseline costs:** always-on resources, licenses, storage, networking, NAT, logs, monitoring.
- **Redundancy costs:** multi-AZ replicas, DR capacity, quotas, and operating costs during failures.
- **Operational costs:** engineering hours, OS/runtime updates, on-call response, upgrades, and debugging.

### 11.1. Cost per 1,000 Requests Example

Suppose two options achieve identical functionality during testing:

| Configuration | Hypothetical Monthly Cost | Successful Requests/Month | Cost per 1,000 Requests |
|---|---:|---:|---:|
| A: many small replicas | 9 million VND | 20 million | 450 VND |
| B: fewer larger replicas | 7.5 million VND | 20 million | 375 VND |

Numbers are **illustrative examples**. If configuration B suffers high p99 latency upon losing a replica or fails AZ-loss survivability, it may violate reliability requirements despite lower unit cost. Compare options under identical SLOs and load scenarios.

### 11.2. Lifecycle Right-Sizing

- **Downsize** when utilization stays persistently low and SLOs retain ample headroom; monitor before and after changes.
- **Upsize** only after confirming the bottleneck is resource capacity rather than queries, locks, retries, or dependencies.
- **Scale-to-zero/scheduled shutdown** for dev/test/batch when startup time and availability allow.
- **Use better-suited compute generations/families** when benchmarks prove better price-performance and runtime compatibility.
- **Review periodically** whenever load, code, runtimes, databases, or traffic patterns change.

Never automatically downsize production based solely on average CPU. Check p95/p99, peaks, failover capacity, memory, I/O, queue backlogs, and rare load windows.

## 12. Well-Architected and Sizing Operations

| Pillar | Sizing Questions |
|---|---|
| **Operational Excellence** | Are baselines, dashboards, alerts, periodic load tests, and capacity owners in place? Can configs be reproduced via IaC? |
| **Security** | Are agents, sidecars, encryption, and logging accounted for in resource budgets? Do quotas/limits prevent resource exhaustion? |
| **Reliability** | Does enough capacity remain after losing an instance/AZ? Can databases/queues/networks absorb scale-out? |
| **Performance Efficiency** | Are CPU, RAM, IOPS, throughput, and latency measured on realistic workloads? Is cost per unit compared? |
| **Cost Optimization** | Are right-sizing, non-prod shutdowns, budgets, appropriate reservations/commitments, and growth forecasts applied? |
| **Sustainability** | Are idle resources minimized, over-provisioning avoided, and hardware used efficiently while meeting SLOs? |

Sizing is a **continuous process**, not a one-time pre-production step. As traffic grows, endpoints are added, queries shift, or runtimes upgrade, resource profiles change. Track and adjust based on telemetry.

### 12.1. Minimum Capacity Dashboard

A per-service/environment dashboard should include:

- Request rate, concurrent requests, p50/p95/p99 latency, and error rate.
- CPU utilization/throttling and CPU time per replica.
- RSS/working set/heap, GC pauses, OOMs/restarts.
- Disk IOPS/throughput/latency and used capacity.
- Network bytes/packets, connection counts, retransmissions, and timeouts.
- Database connection/query latency, queue depth/backlog, cache hit rate.
- Replica/node counts, autoscaling events, quotas, post-AZ-failure capacity.
- Cost by service, environment, and unit of work.

Alerts should trigger on **user-impacting symptoms** and relevant resource saturation. One minute at 85% CPU may not warrant paging if SLOs hold and the burst is brief; conversely, rising p99, error rates, and queue backlogs together require immediate action.

## 13. Sizing Record Template and Checklist

The YAML template below records **assumptions and verification plans**. Field names are project documentation examples, not a standard cloud provider schema:

```yaml
service: booking-api
environment: production
workload_profile:
  steady_rps: 200
  peak_rps: 300
  payload_avg_kb: 20
  target_p95_ms: 300
  failure_scenario: one_replica_or_az_unavailable
resource_hypothesis:
  compute:
    vcpu_per_replica: 5
    replica_count: 2
  memory:
    gb_per_replica: 3
  storage:
    iops: pending_benchmark
  network:
    egress_allowlist: approved_dependencies
measurements:
  cpu_seconds_per_request: 0.01
  working_set_gb: 1.2
assumptions:
  - "Representative workload and database response time are validated"
verification:
  - "Peak load test"
  - "p95/p99 latency and error rate"
  - "One replica/AZ failure capacity"
  - "Database connection and I/O saturation"
review_trigger:
  - "Traffic increases beyond forecast"
  - "Runtime or major dependency changes"
  - "SLO or budget changes"
```

Values in the example are purely assumptions from the booking scenario. Never promote them to production configuration without benchmarking and budget approval.

### Pre-Approval Checklist

- [ ] Documented steady, peak, burst, concurrency, and periodic growth profiles.
- [ ] Identified bottlenecks via metrics/traces/profiling, separating CPU, RAM, I/O, network, and dependencies.
- [ ] Measured p50/p95/p99 latency, throughput, and error rates on representative data.
- [ ] CPU/RAM configurations account for runtime, sidecars, concurrency, and headroom.
- [ ] Disk sizing covers IOPS, throughput, latency, and capacity; network covers throughput/connections/egress.
- [ ] Verified pools/concurrency and quotas across databases, queues, NAT, endpoints, and dependencies.
- [ ] Executed appropriate load/stress/spike/soak/failover tests with clear stop criteria and safe test isolation.
- [ ] Autoscaling uses appropriate signals, caps, baseline capacity, and slow-scale-out mitigation.
- [ ] Single-replica/AZ loss scenario meets approved targets or follows an explicit degraded mode.
- [ ] Compared cost per unit of work and TCO under identical SLO conditions.
- [ ] Established dashboards, alerts, IaC, designated owners, and re-sizing triggers.

**Guiding principle:** size from **measured workloads**, validate against required traffic and failure scenarios, and compare costs at equal quality targets. CPU, memory, I/O, and networking must be viewed as an interdependent system; adding a resource only helps when it addresses the confirmed bottleneck.
