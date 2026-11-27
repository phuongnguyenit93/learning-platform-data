# Defining Latency, Throughput, and Resource Utilization Targets

## Context: Measuring Performance by Outcomes and System Limits

A compute service can run on VMs, containers, or serverless. Despite differences in deployment models, operators still need to answer three questions: how long each request takes, how much work the system processes per unit of time, and how much of its resources are being used. These three groups of metrics are **latency**, **throughput**, and **resource utilization**, respectively.

These metrics are interrelated. As load increases, throughput may increase until a resource or dependency reaches its limit. Beyond that point, queues typically grow longer, latency increases, and errors or timeouts appear. A system with high CPU utilization is not necessarily slow; a system with low CPU can still be constrained by storage, network, locks, or downstream services.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, setting performance targets helps choose the right CPU/RAM, storage, and network types, determine VM/container/serverless configurations, plan capacity, and design meaningful performance tests. Targets must be tied to the workload and the experience to be delivered, rather than choosing arbitrary resource thresholds.

## 1. The Three Core Metric Groups

| Group | Question | Common Units | Example |
|---|---|---|---|
| Latency | How long does an operation take? | ms, s | API completes in 180 ms |
| Throughput | How much work is processed per unit of time? | request/s, transaction/s, job/min, MiB/s | Service processes 2,000 request/s |
| Resource utilization | How much resource capacity is being used? | %, cores, GiB, IOPS, MiB/s | CPU usage 65%, RAM working set 7 GiB |

All three groups should be measured simultaneously. High throughput alone does not prove a system is healthy if latency is too high or the error rate is elevated. Low utilization does not prove a system has ample capacity if the workload is blocked by another limit. Low average latency can also mask a small group of very slow requests.

## 2. Latency: How Long Users Have to Wait

Latency is the time elapsed from a defined start point to a defined completion point. For an API, it may be measured from when the gateway receives a request until the response is sent; for a background task, from when the job is accepted until the result is ready. The start and end points must be agreed upon before comparing measurements.

### 2.1. Components of Latency

A request may go through several stages:

1. DNS lookup and TCP/TLS connection establishment (if the client needs to perform them).
2. Wait time at the load balancer, gateway, or queue.
3. Processing time in the application and CPU scheduling.
4. Wait time for database, cache, storage, or external APIs.
5. Time to transmit the response back to the client.

End-to-end latency reflects the total time experienced by the user. Server-side latency measures only part of the path and is useful for isolating causes. For example, an API that processes in 80 ms while the client receives the result after 600 ms may be due to DNS, TLS, network, or a proxy outside the application's measurement scope.

Do not sum the percentiles of individual components to infer the end-to-end percentile. For a single specific request, sequential durations can be summed; however, the database p95 plus the API p95 does not necessarily equal the overall request p95 because distributions and correlations differ. Measure end-to-end directly and use traces to break down individual spans.

### 2.2. Mean, Median, and Percentiles

Latency usually has a skewed distribution: most requests are fast, while some are slow due to cache misses, GC pauses, retries, contention, or dependencies. Therefore, using the mean alone is insufficient.

| Statistic | Meaning | Usage |
|---|---|---|
| Mean / average | Total latency divided by number of requests | Track overall trends; sensitive to outliers |
| p50 / median | 50% of requests are faster than or equal to this value | Represents the typical experience |
| p90 | 90% of requests are faster than or equal | Observe the moderately slow tail |
| p95 | 95% of requests are faster than or equal | Common level for tracking tail latency |
| p99 | 99% of requests are faster than or equal | Detect very slow experiences for a small group |
| p99.9 | 99.9% of requests are faster than or equal | Useful for large-scale services or strict requirements; requires enough samples |

For example, p95 = 250 ms means roughly 95% of requests in the measured population and window complete in at most 250 ms; the remaining 5% are slower. It does not mean every user experiences 250 ms.

### 2.3. Why Tail Latency Matters

A web page may need to call multiple services in parallel. If an aggregated request waits for all child services, completion time is typically determined by the slowest child service. Even if each service has a fairly good p99, the probability that at least one dependency is slow can rise when a single request calls many dependencies. Tail latency can therefore strongly impact the overall experience.

Common causes of tail latency:

- Queues growing when CPU, storage, or connection pools approach saturation.
- GC pauses, page faults, memory reclaim, or OOM pressure.
- Cache misses, cold starts, or image/container loading.
- Slow storage I/O, high queue depth, or volume throttling.
- Network retransmissions, packet loss, DNS, or TLS connections.
- Lock contention, exhausted thread pools, retry storms, or slow dependencies.

### 2.4. Setting Latency Targets

Targets need to specify the request type, measurement point, percentile or percentage under threshold, and time window. For example:

- Read API p50: under 80 ms.
- Read API p95: under 250 ms.
- 99% of valid requests complete within 500 ms.
- 95% of background jobs complete within 2 minutes of being accepted.

These are illustrative examples only. Real targets must be based on user needs, operation complexity, dependencies, historical measurements, and product requirements. For latency, an SLO based on the percentage of requests below a threshold is often easier to interpret than a single percentile number when calculating an error budget.

## 3. Throughput: Amount of Work Completed

Throughput is the rate at which a system completes work. Units must match the workload:

- Web/API: requests per second (RPS).
- Database: transactions per second (TPS), queries/s, or operations/s.
- Queue/worker: jobs per minute or messages/s.
- File/storage: MiB/s or GiB/s.
- Streaming: events/s or bytes/s.
- Batch: number of records or files completed within a time period.

Distinguish **offered load** (the amount of work sent in) from **achieved throughput** (the amount of work actually completed). When a system is overloaded, clients may keep sending 5,000 request/s while the server only completes 2,000 request/s; the rest wait, time out, or are rejected. Measuring only requests sent will misjudge capacity.

### 3.1. Throughput and Goodput

Goodput is the useful portion of throughput: valid work completed as required, after excluding duplicate retries, error responses, or data unusable by business definition.

For example, a worker receives 1,000 message/s, but 200 message/s are retried multiple times and 50 message/s go to a dead-letter queue. Internal processing throughput may be high, yet successful goodput is significantly lower. For uploads, bytes successfully transferred and checksum-verified are more meaningful than total bytes sent over the network.

When setting throughput targets, specify clearly:

- Are received requests, completed requests, or successfully committed transactions counted?
- Are retries counted separately or grouped by logical work item?
- Are failed, canceled, or timed-out requests included?
- Is the measurement an average over a window or a short-term peak?
- How long must the system sustain that rate?

### 3.2. Throughput and Latency Cannot Be Optimized in Isolation

Batching can increase throughput by processing many items in a single call, but often increases wait time to accumulate the batch. Increasing concurrency can utilize CPU and I/O better, but beyond serving capacity, queues and latency grow. Caching can reduce backend load and latency, but cache misses and consistency must be accounted for.

Targets should be set together, for example: handle at least 1,500 request/s while keeping p95 under 250 ms and error rate under 0.1%. A configuration that achieves 2,000 request/s while p95 rises to 3 seconds does not meet this target.

## 4. Concurrency, Queues, and Little's Law

Concurrency is the number of work items being processed or existing simultaneously in the system. Distinguish concurrent requests at the client, requests actively executing in the application, and requests waiting in a queue.

Little's Law describes the relationship between the average number of items in a system, throughput, and time spent in the system:

\[
L = \lambda W
\]

Where:

- `L`: average number of items in the system (in-flight or queued, depending on the measurement boundary).
- `λ`: average throughput, in items per second.
- `W`: average time an item spends in the system, in seconds.

For example, an API completes 200 request/s and the average time from receipt to completion is 0.25 seconds. The average number of requests in the system is:

\[
L = 200\times0.25=50\text{ requests}
\]

If throughput stays the same while latency increases to 1 second, the average number of requests in the system rises to about 200. Larger queues consume more memory and can cause timeouts to increase accordingly.

Little's Law describes average relationships under steady-state conditions and does not by itself determine maximum capacity or latency percentiles. When the system is unstable, queues grow continuously, and throughput cannot keep up with offered load, it must be treated as an overload condition.

## 5. Resource Utilization: How Much Resources Are Being Used?

Resource utilization is the ratio or level of usage of a resource relative to its provisioned capacity. However, utilization is only one perspective. To know whether a resource has become a bottleneck, also check **saturation** (contention/queueing level) and **errors** (failures due to exhaustion or exceeding limits).

Three signals are commonly used together:

- **Utilization:** the portion of capacity currently in use, such as 70% CPU or 80% volume capacity used.
- **Saturation:** work having to wait because a resource cannot respond immediately, such as CPU run queue, disk queue, or a full thread pool.
- **Errors:** operations failing due to resources or limits, such as OOM kill, disk full, throttling, packet drops, or request timeouts.

A CPU at 90% utilization with no significant run queue and stable latency may still serve well. Conversely, 40% average CPU where a single core is saturated can slow down a processing thread. Therefore, a single utilization threshold should not be applied across all resource types and workloads.

## 6. Resource Metrics to Monitor

### 6.1. CPU

Useful metrics:

- CPU utilization machine-wide, per core, and per process/container.
- User, system, idle, iowait, and steal time on Linux.
- Run queue or number of runnable threads waiting for CPU.
- Container CPU throttling when hitting quota/limit.
- Context switches, interrupt rate, and CPU frequency when deep analysis is needed.

High CPU utilization can indicate that the workload is making good use of resources. However, a growing run queue, sustained throttling, and rising latency together indicate CPU may be a bottleneck. For VMs, high steal time indicates vCPUs are waiting for the hypervisor to schedule CPU time; this signal may relate to host contention or instance characteristics.

Containers can be CPU-limited by quota. If an application needs short CPU bursts while its quota is low, it can be throttled even when the node still has idle CPU. Both usage and throttling must be examined, not just node CPU.

Example Linux commands:

```bash
# Overview of CPU and run queue over time
vmstat 1

# Per-core CPU usage
mpstat -P ALL 1

# Processes using the most CPU
top
```

Commands require the corresponding tool packages (`sysstat` for `mpstat`) and appropriate permissions. On Windows, Processor\% Processor Time, Processor Queue Length, and process-level CPU can be monitored using Performance Monitor.

### 6.2. Memory

Do not look only at used RAM. Operating systems may use RAM as page cache, which can be reclaimed when applications need it. Metrics to observe:

- Application working set or resident set.
- Available memory and memory pressure.
- Swap in/out, major page faults, and page reclaim.
- OOM kills or container memory limit exceeded.
- Heap, garbage collection, and allocation rate for managed runtimes.
- Cache hit/miss and memory used per container/VM.

RAM near full is not necessarily an incident if most of it is reclaimable cache. However, heavy swap activity, rising major page faults, OOM kills, or prolonged GC latency indicate memory pressure. For containers, memory limits can trigger OOM kills even if the host still has free RAM; check limits at the exact cgroup/container level.

### 6.3. Storage and Filesystem

Storage can be constrained by IOPS, throughput, latency, queue depth, or capacity. Metrics to monitor:

- Read/write IOPS and MiB/s.
- Read/write latency, especially p95/p99 if provided by the service.
- Queue depth and I/O wait time.
- Device utilization or provisioned throughput/IOPS limits.
- Filesystem space, inodes, and data growth rate.
- Burst balance/credits or throttling if the volume type uses a burst mechanism.

A volume may still have 70% free space yet already hit its IOPS limit. Conversely, a full volume can cause application errors even while I/O latency remains low. Both performance and capacity must be monitored.

Example Linux commands:

```bash
# Per-device I/O, queue, and latency
iostat -xz 1

# Filesystem space and inodes
df -h
df -i
```

### 6.4. Network

Network metrics include inbound/outbound throughput, packets per second, RTT, packet loss, retransmissions, connection errors, socket states, and bandwidth limits. For cloud VMs, check network limits by instance type, NIC, flow, or service; some instances have maximum bandwidth based on load or machine size.

Low throughput does not always mean the network lacks bandwidth. The application may be limited by request rate, TCP window, packet loss, connection setup, DNS, or a remote server. Increasing packet retransmissions and RTT can degrade latency even if the interface has not exhausted its bandwidth.

### 6.5. GPUs and Accelerators

For AI or accelerated computing workloads, monitor:

- GPU utilization and utilization of each compute engine.
- VRAM used/free and peak memory allocation.
- Memory bandwidth or memory controller utilization if supported by tools.
- Power, temperature, clocks, and throttling.
- GPU queue, number of waiting jobs, and GPU allocation wait time.
- PCIe/NVLink transfers and driver/runtime errors.

Low GPU utilization can happen because the data loader, CPU preprocessing, network, or storage is not feeding data fast enough. Full VRAM can limit batch/context size before compute engines reach high utilization. End-to-end workload throughput and latency must be measured alongside GPU metrics.

### 6.6. Resources in Containers and Serverless

Containers: monitor requests/limits, usage, CPU throttling, memory working set, OOMs, restarts, pending pods, node pressure, and scheduling time. Setting requests too low can cause the scheduler to pack too many workloads onto a node; setting limits too low causes throttling or OOMs.

Serverless: monitor invocation count, duration, concurrency, throttling, cold starts, configured/used memory, timeouts, and retries. Concurrency limits can block requests even when compute in other services is available. Cold starts increase latency for a subset of invocations, so inspect latency distributions and cold-start rates rather than looking only at average duration.

## 7. Identifying Bottlenecks from Metric Relationships

Do not conclude a bottleneck from a single metric. Look for correlated changes across latency, throughput, utilization, saturation, and errors.

| Observed Symptom | Possibility to Investigate | Additional Evidence |
|---|---|---|
| Throughput stops rising, latency increases, CPU run queue grows | CPU-bound or low CPU quota | Per-core usage, throttling, profiles, and CPU time/request |
| Latency rises, memory pressure/swap/major faults increase | Insufficient RAM or growing working set | OOMs, GC pauses, allocations, cache, and page faults |
| Database latency rises, disk queue/IOPS high | Storage-bound | Read/write patterns, volume limits, DB wait events |
| Request timeouts, retransmissions/RTT increase | Network or dependency path | Packet loss, DNS, connection pool, and traces |
| Node has free CPU but pod is pending | Scheduling constraints or other resource shortage | Memory requests, taints/tolerations, affinity, GPU, IPs, and quotas |
| Low GPU utilization, high data wait | Data feeding pipeline is the bottleneck | CPU loader, storage reads, network, and GPU queue |
| Error rate rises when concurrency hits a limit | Thread/connection/concurrency cap | Pool exhaustion, 429s, throttling, and queue length |

A practical investigation approach:

1. Confirm whether latency/throughput of the user journey changed.
2. Identify the affected endpoints, workloads, regions/zones, and versions.
3. Compare resource utilization against saturation and errors over the same period.
4. Use traces to find slow spans; use logs to find errors; use profiles to find CPU/memory costs inside the application.
5. Check dependencies and cloud service limits, not just VM resources.
6. Test a change with a clear hypothesis, re-measure, and compare against the baseline.

## 8. Profiling the Workload Before Setting Targets

Different workloads prioritize different metrics:

| Workload | Characteristics | Typically Critical Metrics |
|---|---|---|
| Interactive API | Short requests, user waits for response | p95/p99 latency, success rate, RPS, concurrency |
| Batch processing | Large volume, may run on a schedule | Total completion time, records/s, CPU/GPU hours, cost/job |
| Queue worker | Asynchronous processing, has backlog | Jobs/s, oldest message age, completion deadline, retries |
| Database | Random I/O, transactions, and contention | TPS, query latency, IOPS, disk queue, connection pool |
| Streaming | Continuous event stream | Events/s, lag, processing latency, dropped events |
| AI inference | Prefill/decode, batching, and KV cache | TTFT, tokens/s, p95 latency, VRAM, GPU utilization |
| File/object transfer | Large data transfers | MiB/s, request latency, errors/retries, egress |

Before choosing targets, describe the workload using these attributes:

- Request/job mix and share of each type.
- Payload, record, file, or context sizes.
- Arrival rate over time, peaks, and seasonality.
- Concurrency and average processing time.
- Read/write ratio, cache hit ratio, and access patterns.
- Dependencies, retries, timeouts, and external limits.
- Latency, throughput, accuracy, and completion time targets.

A benchmark sending only small requests, with a warm cache, to a single endpoint does not represent a production system with diverse request types and dependencies. A workload profile ensures tests reflect real conditions.

## 9. Translating Product Requirements into Measurable Targets

Performance targets should be testable and verifiable. Instead of writing "the API must be fast" or "CPU must not be too high," define the population, load, thresholds, and time window.

Example targets for a production API:

| Attribute | Illustrative Target |
|---|---|
| Offered load | 1,500 request/s with representative request mix |
| Goodput | At least 1,490 request/s completed successfully |
| Latency | p95 under 250 ms, p99 under 600 ms |
| Error rate | Under 0.1% during steady-state test |
| CPU | No sustained throttling; fleet CPU retains headroom for peak |
| Memory | No OOM/swap thrashing; working set has headroom |
| Storage | p95 I/O latency and queue depth within workload thresholds |
| Network | No abnormal packet loss/retransmissions; bandwidth has spare margin |

These numbers only illustrate how to write targets. There is no universal CPU or RAM threshold that fits all applications. Targets must be agreed upon with the product owner, operations team, and service owners.

### 9.1. Setting Targets for Normal Load and Peak Load

A system may handle average load yet fail during peak. Distinguish between:

- **Normal load:** load typically seen most of the time.
- **Peak load:** highest expected load during normal operations or seasonal events.
- **Burst load:** sudden short-duration spike in load.
- **Growth scenario:** expected load after user base or data grows.
- **Degraded mode:** minimum acceptable service level when a dependency or failure domain has an incident.

Targets should state how long peak must be sustained and how the system recovers after a burst. A system may handle a 2,000 RPS burst for 30 seconds but only sustain 1,200 RPS for one hour; both behaviors need testing if both matter.

### 9.2. Setting Targets per Request Type

Cache read requests and database write requests have different costs. Aggregating everything into a single latency percentile can hide failures in a critical flow. Separate targets can be set for login, search, checkout, or upload; keep one overall SLI to reflect the service and detailed SLIs for investigation.

When grouping, avoid creating too many metric types or high-cardinality labels. Split only along operationally or business-meaningful flows.

## 10. Capacity, Saturation, and Headroom

Capacity is the amount of work a system can handle under defined conditions while still meeting latency and error rate targets. Capacity should not be defined simply as the point where CPU hits 100%. Bottlenecks can occur in connection pools, disk IOPS, network packet rate, memory, or downstream services before CPU is full.

### 10.1. Finding the Saturation Point

When increasing offered load in steps, three regions are typically observed:

1. **Underutilized:** resources have spare capacity, throughput scales nearly linearly with load, and latency is relatively stable.
2. **Efficient operating region:** throughput increases while queues and latency become more sensitive to load; the system still meets targets.
3. **Saturation/overload:** throughput plateaus or barely increases, queues/latency rise rapidly, and throttling and errors appear.

The saturation point is where the system can no longer simultaneously meet throughput, latency, and error targets. Operate below this point to absorb fluctuations and component failures.

### 10.2. Headroom

Headroom is spare capacity reserved to absorb bursts, growth, single-node/zone failures, and scale-out time. Headroom must be calculated per resource and failure scenario. For example, if running three replicas and the service must still serve when one replica is lost, the remaining two replicas must be able to handle the required load.

A simple estimation formula:

```text
required_capacity = peak_demand / target_utilization
headroom = required_capacity - peak_demand
```

For example, if a workload is expected to need 60 CPU capacity units at peak and operators want to keep utilization around 70% under normal conditions:

```text
required_capacity = 60 / 0.70 = 85.7 capacity units
headroom           = 85.7 - 60 = 25.7 units
```

This is a simple linear sizing calculation. In practice, account for node/zone loss, instance limits, autoscaling delay, quotas, uneven load distribution, and overhead. The 70% target utilization in the example is not a fixed recommendation.

### 10.3. Do Not Use One Utilization Threshold for All Resources

CPU can operate efficiently at high utilization if latency remains stable and burst capacity remains. RAM needs room for sudden allocations and page cache; storage needs spare IOPS/throughput to avoid queue growth; network needs spare bandwidth and packet rate. GPUs must account for both VRAM and compute utilization.

Alert thresholds should combine utilization with saturation and SLIs. For example, sustained 85% CPU may be a warning; CPU throttling paired with p95 latency exceeding target may require paging. For filesystems, 90% capacity may warrant an early warning even while I/O latency is normal because data growth could fill the volume before the next maintenance window.

## 11. Rough Resource Estimation from Workload

The calculations below provide a starting point before benchmarking. They do not replace actual load testing because caching, locks, batching, runtimes, and dependencies make performance nonlinear.

### 11.1. Estimating CPU

If each request consumes an average of `c` CPU seconds and the system must process `R` requests per second:

\[
CPU\ cores\ (ideal) = R\times c
\]

For example, each request uses 5 ms of CPU and the target is 1,000 request/s:

\[
1000\times0.005=5\text{ CPU cores}
\]

This is the ideal CPU time to process that load, excluding OS overhead, sidecars, background tasks, request mix variation, and headroom. If aiming for roughly 70% peak utilization under defined conditions, capacity can be estimated at around `5 / 0.7 = 7.14` cores, then rounded to a suitable instance configuration and tested.

### 11.2. Estimating Concurrency

Using Little's Law, if the system receives 800 request/s and average time in the system is 0.15 seconds:

\[
L=800\times0.15=120\text{ requests}
\]

The application needs to manage roughly 120 in-flight requests on average at that load. Peak concurrency can be higher; examine latency distributions, bursts, and thread/connection pool limits. Do not increase thread count indefinitely because each thread has overhead and can worsen contention.

### 11.3. Estimating Network Throughput

If the average response is 10 KiB and the goodput target is 2,000 response/s:

\[
2000\times10\text{ KiB}=19.53\text{ MiB/s}
\]

This figure accounts only for response payloads, excluding request bodies, protocol overhead, TLS, retransmissions, replication, or inter-service traffic. Measure both ingress and egress, and check NIC/instance and link limits.

### 11.4. Estimating Memory

For a server handling concurrent requests, memory may consist of runtime baseline, fixed working set, caches, buffers, and growth proportional to in-flight requests. A rough model can be used:

```text
memory_required ~= baseline
                 + (memory_per_inflight_request x concurrency)
                 + cache_and_buffer
                 + operating_headroom
```

For example, baseline 1.5 GiB, each in-flight request holds 2 MiB on average, concurrency 200, and cache/buffer 1 GiB:

```text
1.5 GiB + (2 MiB x 200) + 1 GiB ~= 2.89 GiB
```

This is only an approximate model; memory per request can vary by payload, runtime, object lifetime, and GC. Measure peak working set under representative load rather than checking RAM right after startup.

## 12. Designing Performance Tests to Measure the Right Targets

A valuable test must reproduce the workload closely enough to production, generate controlled load, and collect metrics on both client and server sides. If the load generator becomes the bottleneck, results will not reflect the target system's capacity.

### 12.1. Types of Load Tests

| Test Type | How Load Is Generated | Question to Answer |
|---|---|---|
| Baseline | Low, steady load | What is the baseline performance and initial overhead? |
| Load test | Expected load under normal/peak conditions | Does the system meet SLOs at target load? |
| Stress test | Load increased beyond expected levels | What is the saturation point and degradation behavior? |
| Spike test | Sudden increase/decrease in load | How does the system respond to bursts and autoscaling? |
| Soak test | Sustained load over a long duration | Are there memory leaks, queue buildup, connection leaks, or degradation? |
| Capacity test | Stepped load increases to find limits | What is the maximum throughput that still meets latency/error targets? |

Do not run only a short peak test. A soak test can uncover memory leaks or storage growth; a spike test validates scale-out and cold starts; a stress test reveals whether the system degrades gracefully or collapses abruptly.

### 12.2. Preparing the Workload and Environment

Before running:

1. Select representative request mixes, payload sizes, data, and dependencies.
2. Prepare an environment where compute, storage, network configurations, and versions match production in key aspects.
3. Isolate the load generator from the target system or ensure it has ample CPU, memory, and network capacity.
4. Define cache state: cold, warm, or realistic ratio; explicitly note if the benchmark measures warm cache only.
5. Synchronize clocks and enable required metrics/logs/traces.
6. Set timeouts, retries, and rate limits according to real application behavior.
7. Verify test data does not cause side effects or impact real users.

Record instance types, replica counts, image/container digests, runtime, region/zone, storage class, autoscaling policies, and dependency configurations so measurements are reproducible.

### 12.3. Ramp-up, Steady-State, and Ramp-down

A test should include a gradual load increase, a sufficiently long steady-state observation phase, and a controlled ramp-down. Skipping warm-up can skew results due to JIT compilation, cold caches, autoscalers, or connection pool initialization.

Example scenario:

| Phase | Load | Duration | Purpose |
|---|---:|---:|---|
| Warm-up | 10% target | 3 minutes | Initialize connections, caches, and runtime |
| Ramp-up | 10% to 100% | 10 minutes | Observe scaling and latency under rising load |
| Steady-state | 100% target | 20 minutes | Verify SLOs and utilization at target load |
| Peak | 130% target | 5 minutes | Evaluate headroom and burst behavior |
| Ramp-down | Gradually down to 0 | 3 minutes | Observe draining, queues, and scale-in |

Actual durations depend on the workload. Soak tests need to be much longer; cold-start tests require spinning up fresh environments or controlled scale-to-zero.

### 12.4. Closed-Loop vs. Open-Loop Load Generation

In a **closed-loop test**, each virtual user sends a request and waits for a response before sending the next. When the server slows down, the send rate drops automatically; this can mask the offered load that real users would continue generating.

In an **open-loop test**, the generator dispatches requests at a predetermined arrival rate, independent of response time. This model is suitable for simulating systems receiving continuous traffic and observing queues/latency when the server slows down. Bound the queue at the load generator to prevent the load tool itself from accumulating requests uncontrollably.

An important issue to watch for is **coordinated omission**: if the load generator only sends a new request after the previous one completes, it may fail to record the timestamps when new requests should have been sent while the system was slow. Latency results can therefore appear overly optimistic. Choose tools and load-generation modes that accurately record scheduled arrival times or correct for coordinated omission.

### 12.5. Measuring Percentiles Correctly

Do not average percentiles across multiple machines to compute a fleet-wide percentile. For example, VM A having p95 = 100 ms and VM B having p95 = 500 ms does not mean the system-wide p95 is 300 ms. Aggregate histogram buckets/counts or collect request data at a common measurement point and calculate percentiles over the target population.

With Prometheus histograms, an aggregated p95 query may look like:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket{
      service="orders-api",
      environment="perf"
    }[5m])
  )
)
```

This query assumes the application exports an `http_request_duration_seconds` histogram and matching labels. Histogram buckets need sufficient resolution around the target threshold; if buckets are too sparse, the percentile is only a rough approximation. With native histograms or other metrics systems, syntax may differ.

## 13. Baselines and How to Interpret Results

A baseline is a set of measurements under known configuration and conditions, used for comparison after changes. A useful baseline records:

- Workload profile and offered load.
- Goodput, error rate, and p50/p95/p99 latency.
- CPU, memory, storage, network, and saturation.
- Number of replicas/VMs, instance configuration, image/runtime, and dependencies.
- Warm-up, steady-state, and total test duration.
- Code/config versions, run date, and environment.

When comparing two runs, keep conditions equivalent. Changing instance type, database, cache, and request mix simultaneously makes it difficult to determine which change produced the result.

### 13.1. Reading Throughput Curves

Plot achieved goodput against offered load and latency against offered load. Initially, goodput usually rises nearly linearly. Near saturation, the goodput curve flattens while latency rises sharply. The operating point should lie within the SLO-compliant region, with headroom for bursts and component failures.

### 13.2. Reading Utilization Alongside Latency

Examples:

- CPU rises from 30% to 75%, goodput increases, and p95 stays stable: the system is utilizing additional capacity.
- CPU stays at 95%, goodput stops increasing, run queue and p99 climb: CPU limit may have been reached.
- CPU is only 40%, while disk queue and database latency rise: the bottleneck may be in storage/database.
- RAM grows steadily over hours and does not drop after load subsides: check for leaks or unbounded caches.

Do not draw conclusions solely from averaged charts. Break down by instance, endpoint, zone, container, and dependency to uncover hotspots hidden by aggregates.

## 14. Observability and Measurement Tools

| Scope | Common Tools / Data Sources | Used to Measure |
|---|---|---|
| Linux CPU/memory | `top`, `vmstat`, `mpstat`, `/proc`, cgroup metrics | CPU, run queue, memory pressure, processes |
| Linux storage | `iostat`, `iotop`, filesystem metrics | IOPS, throughput, queues, latency, disk usage |
| Linux network | `ss`, `sar -n`, `ethtool`, flow logs | Sockets, retransmissions, packets, interfaces |
| Windows | Performance Monitor, Resource Monitor, Event Viewer | CPU, memory, disk, network, processes |
| Container/Kubernetes | Metrics Server, Prometheus, kube-state-metrics, cAdvisor | Pod/node resources, throttling, restarts, pending |
| Cloud VM | Provider monitoring, instance metrics, audit/event logs | CPU, network, disk, status checks, throttling |
| Load testing | k6, JMeter, Gatling, Locust, or equivalent tools | Offered load, response time, errors, virtual users |
| Tracing | OpenTelemetry and tracing backends | Span latency, dependencies, request paths |

Tools must be selected according to platform and organizational policy. Not all metrics are available by default; disk I/O, memory working set, process metrics, or application histograms may require separate agents/instrumentation.

## 15. Practical Example: Defining Targets for a VM-Hosted API

Suppose an order API currently runs on two VMs behind a load balancer. Expected workload is 600 RPS normal and 1,200 RPS peak. The request mix consists of 70% reads, 25% writes, and 5% reporting queries.

### 15.1. Writing the Targets

- 1,200 RPS offered load during a 20-minute steady-state.
- Minimum goodput of 1,190 RPS.
- p95 latency under 250 ms; p99 under 600 ms.
- Error rate under 0.1%.
- System retains enough capacity when one VM is drained for maintenance.
- No OOMs, no sustained CPU throttling, no continuously growing storage queue.

### 15.2. Initial Estimation

Suppose profiling shows one request uses 4 ms of CPU on average:

\[
1200\times0.004=4.8\text{ cores}
\]

If aiming to keep CPU around 70% at peak, roughly:

\[
4.8/0.70\approx6.86\text{ cores}
\]

This is a fleet-level estimate. If peak must be sustained when one of the two VMs is drained, the remaining VM must have enough capacity or the system must have additional replicas. You cannot simply divide the ideal core count in half and conclude each VM is sufficient; failure scenarios and actual benchmarks must be accounted for.

### 15.3. Testing and Tuning

1. Measure baseline at 600 RPS and record latency, goodput, and resource metrics.
2. Ramp up to 900, 1,200, and 1,400 RPS; hold each step long enough to stabilize.
3. Observe where goodput stops scaling proportionally or p95/p99 exceeds targets.
4. Check per-core CPU, run queue, memory, disk, network, and database connections.
5. Drain one VM and re-run 1,200 RPS to verify headroom and HA.
6. Run a soak test to detect memory/queue growth over time.
7. Finalize configuration and alert thresholds after verifying across multiple runs.

If p95 exceeds the target while CPU is low and traces point to database waits, adding vCPUs to the API may not help. Address queries, connection pools, indexes, or database capacity instead. Every optimization must correspond to a measured bottleneck.

## 16. Optimizing Through Measurement Loops

Performance optimization should follow a hypothesis-and-measurement loop:

1. **Define targets:** latency, goodput, error rate, and resource guardrails.
2. **Measure baseline:** workload, configuration, version, and environment documented.
3. **Identify bottlenecks:** based on saturation, traces, profiles, and dependency metrics.
4. **Form a hypothesis:** for example, reducing query count will lower database waits and p95.
5. **Change a controlled set of variables:** indexes, caching, batch size, instance type, concurrency, or storage tier.
6. **Re-run the same workload:** compare goodput, latency distributions, errors, and resource usage.
7. **Evaluate trade-offs:** cost, complexity, consistency, durability, and operability.
8. **Record results:** update baseline, configuration, and deployment decisions.

A change may reduce latency while increasing CPU or memory; that can be a good trade-off if headroom remains and cost is acceptable. Conversely, increasing throughput via unbounded queues can increase wait times and memory usage, causing users to receive results later.

### 16.1. Common Optimization Directions

| Confirmed Bottleneck | Experiment Direction | Risks to Re-measure |
|---|---|---|
| CPU-bound | Optimize algorithms, reduce serialization, increase vCPU, or scale out | Cost, contention, and dependency limits |
| Memory pressure | Reduce allocations, bound caches, tune heap, or increase RAM | GC, cache hits, and OOMs |
| Storage-bound | Optimize queries/I/O, provision IOPS, cache, or change storage tier | Durability, cost, and write amplification |
| Network-bound | Reduce payloads, reuse connections, compress, or co-locate services | Compression CPU, egress cost, and TLS overhead |
| Queue/concurrency-bound | Tune worker count, pool size, batching, and backpressure | Dependency overload, tail latency, and duplicate work |
| Cold-start-bound | Keep warm capacity, shrink package/init, or choose another runtime | Idle cost and memory |

Do not increase concurrency without limits. Backpressure, queue limits, and admission control help the system reject early or slow producers when capacity is insufficient, rather than letting queues grow to cause cascading failures.

## 17. Cost and Performance per Unit of Work

When choosing cloud configurations, evaluate performance alongside cost. A larger instance may increase throughput but also raise cost; more smaller instances can improve scaling granularity and HA yet add network, orchestration, or licensing overhead.

Useful efficiency metrics:

- Cost per 1,000 successful requests.
- Cost per job or per million records processed.
- Tokens/s per GPU-hour or cost per million tokens.
- MiB/s per unit of storage/network cost.
- Achieved throughput at target latency and error rate.

Do not compare configurations solely by request/s if one configuration has a high error rate or exceeds latency targets. Count only goodput that meets the defined quality criteria.

## 18. Common Misconceptions

**Average latency represents every user's experience.** Distributions are typically skewed and tail latency can be very large. Track p50, p95, p99, and percentage of requests under threshold.

**Throughput is the number of requests sent.** Offered load differs from achieved throughput. Measure successfully completed requests/jobs and distinguish retries.

**High CPU utilization is always bad.** High CPU can reflect efficient utilization; check run queue, throttling, latency, and goodput.

**Low CPU means plenty of capacity remains.** Storage, network, memory, locks, or dependencies may be saturating before CPU.

**RAM used near 100% means out of RAM.** Page cache can be reclaimed; check available memory, swap, page faults, memory pressure, and OOMs.

**Increasing concurrency always increases throughput.** Beyond the saturation point, high concurrency can increase queues and latency without increasing goodput.

**Averaging per-VM p95/p99 yields the fleet percentile.** Percentiles do not combine linearly; aggregate histograms or request data.

**A single benchmark is enough to finalize configuration.** Results depend on warm-up, cache, request mix, load generator, duration, and dependencies. Repeat runs and test key failure scenarios.

**One utilization threshold fits all workloads.** Targets must be based on saturation points, SLOs, bursts, failure domains, and autoscaling delays.

## 19. Checklist for Target Setting and Performance Measurement

### Before Testing

- [ ] Defined user journeys and workload types.
- [ ] Defined end-to-end and server-side latency, goodput, and offered load.
- [ ] Selected percentiles/percentage-below-threshold, throughput, and error targets.
- [ ] Described request mix, payloads, arrival rate, concurrency, and dependencies.
- [ ] Selected representative environment, configuration, and test data.
- [ ] Load generator has enough capacity and will not become the bottleneck.

### During Testing

- [ ] Includes warm-up, ramp-up, steady-state, and ramp-down.
- [ ] Measures both client-side and server-side latency.
- [ ] Collects p50/p95/p99, goodput, errors, and offered load.
- [ ] Monitors CPU, memory, storage, network, GPU, and relevant saturation metrics.
- [ ] Distinguishes closed-loop/open-loop and handles coordinated omission.
- [ ] Checks autoscaling, queues, retries, and dependencies as load increases.

### After Testing

- [ ] Identified saturation point and headroom under required failure scenarios.
- [ ] Compared results against baseline under equivalent conditions.
- [ ] Confirmed bottlenecks using metrics, traces, or profiles.
- [ ] Documented hypothesis, results, and trade-offs for each optimization.
- [ ] Final configuration meets latency, goodput, error, and cost targets.
- [ ] Dashboards, alerts, and capacity plans reflect the verified configuration.

## Conclusion

Latency measures how long an operation takes; throughput measures how much work completes per unit of time; resource utilization shows how much resource capacity is being used. Read them together with concurrency, queues, saturation, and errors to locate the saturation point. Performance targets should be grounded in realistic workloads, latency distributions, goodput, normal/peak loads, and headroom under failure scenarios. Estimates from CPU time, Little's Law, payloads, and memory provide initial sizing; benchmarks with warm-up, ramp-up, steady-state, soak, and stress phases verify the configuration. By measuring baselines, identifying bottlenecks, and optimizing through hypothesis-driven iterations, operations teams can balance user experience, capacity, and cost across VMs, containers, and serverless.
