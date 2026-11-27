# Building a Performance Baseline and Capacity Plan

A system can run fast on test day yet become sluggish when user traffic grows, a promotional campaign starts, or an Availability Zone experiences an outage. Sizing servers by intuition easily puts operations teams in one of two traps: under-provisioning resources so the application bottlenecks, or over-provisioning so Azure costs rise without a corresponding improvement in performance.

In the **Performance and Operations** chapter of the **CLOUD_PROVIDERS_AZURE** track, this lesson explains how to measure a **performance baseline** and build a verifiable **capacity plan**. The methodology applies to Microsoft Azure architectures across subscriptions, resource groups, networking, compute, storage, data, monitoring, security, and cost control. Examples use an ordering application running on Azure Kubernetes Service (AKS), Azure Container Apps, or Azure App Service, connected to Azure SQL Database/Storage and dependent services.

A baseline must answer: **how much traffic is the system currently handling, at what latency, error rate, and resource utilization, and under what conditions?** A capacity plan must answer: **when traffic changes, how many resources are needed, how long does it take to provision more, what is the expected cost, and can the system continue operating during a failure?**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish baseline, benchmark, SLI, SLO, capacity, headroom, forecast, and capacity plan.
2. Collect throughput, latency, error rate, saturation, concurrency, and business signals from Azure Monitor, Application Insights, and application telemetry.
3. Define realistic workloads, build repeatable load test scenarios, and identify saturation points.
4. Estimate initial capacity using measured throughput, Little's Law, headroom, growth rate, and fault-tolerance requirements.
5. Plan resources across compute, databases, caches, message queues, storage, and networking rather than only adding instances.
6. Tie the capacity plan to autoscale, Azure quotas, SLOs, cost budgets, and infrastructure change workflows.
7. Present a plan complete with assumptions, data sources, action thresholds, owners, and a review schedule.

## 2. Foundational Concepts

| Concept | Meaning | Illustrative Question |
| --- | --- | --- |
| **Performance baseline** | Performance metric reference point for a defined configuration and workload | At 120 requests/second, what are p95 and CPU utilization? |
| **Benchmark** | Measurement with controlled procedure, conditions, and comparison target | Does the new release handle the same workload faster or slower? |
| **Capacity** | Load level that can be served within performance and correctness constraints | What is the maximum requests/second while p95 still meets the SLO? |
| **Headroom** | Reserve capacity available for traffic spikes or resource loss | Is there enough spare capacity to absorb a burst before scaling out? |
| **Capacity forecast** | Projection of traffic and resource demand over time | If peak RPS grows 30% next quarter, how many replicas will be needed? |
| **Capacity plan** | Decisions on resources, limits, provisioning timing, cost, risks, and validation | When must quotas, node pools, and RU/s be increased? |
| **SLI** | Quantitative service level indicator, e.g., successful request ratio | What percentage of valid requests succeeded over 30 days? |
| **SLO** | Target set for an SLI, e.g., 99.9% valid requests succeeding | What service level must be guaranteed? |

A baseline is not synonymous with **peak capacity**. A baseline is a contextualized snapshot of normal behavior or a chosen load level. Peak capacity must be discovered through benchmarks/load tests with stop criteria evaluated against SLOs.

**Example:** API p95 is 300 ms on a normal day, but when traffic doubles, p95 jumps to 1.8 seconds and 503 errors climb. You cannot conclude the system has double the capacity just because average CPU is 40%, because the bottleneck may lie in the database connection pool, storage IOPS, network, or another dependency.

## 3. Defining the Workload Before Measuring

### 3.1. Classifying User Journeys

An e-commerce application has journeys with different load profiles:

| Journey | Example Endpoint | Primary Resources | Risk Under Increased Load |
| --- | --- | --- | --- |
| Browse products | GET /products | Cache, database read, outbound HTTP | Cache misses, hot keys, read latency |
| Search | GET /search | Search/index, CPU, network | Expensive queries, fan-out |
| View cart | GET /cart | Session store, cache, database | Hot partitions, locking |
| Place order | POST /orders | Database write, transaction, queue | Lock contention, duplicate writes, backlog |
| Process payment | Webhook/worker | Queue, payment API, database | Rate limits, retry storms, pending jobs |
| Run reports | Background job | CPU, database, storage | Resource contention with online transactions |

Measuring a single **total RPS** figure is not enough. For example, 1,000 cache read requests can be lighter than 100 order creation requests involving multiple data transactions. Each benchmark should record the **mix of business operations**, payload size, cache hit rate, read/write ratio, downstream call count, and concurrent users.

### 3.2. Identifying Traffic Shape

Minimum analysis:

- **Baseline level:** traffic by minute/hour and day of week.
- **Peak hours:** peaks across 1-, 5-, or 15-minute windows; examine per-second bursts if needed.
- **Seasonality/events:** paydays, sales events, period closes, batch runs, campaign launches.
- **Growth rate:** weekly/monthly/quarterly trends, separating organic growth from one-off events.
- **Geographic distribution:** user locations, latency across the Internet and between Azure regions.
- **Version changes:** feature flags, builds, cache policies, or new database schemas.

If the system has no production traffic yet, use product forecasts and load tests to establish an initial baseline, then update it once real traffic arrives. Explicitly note the lower confidence of assumption-derived baselines.

### 3.3. Workload Description Template

Illustrative example, **not measured metrics from an actual Azure system**:

~~~yaml
workload: orders-api
environment: production
region: southeastasia
release: 2026.11.example
measurementWindow: "14 representative days"
traffic:
  normalRps: 70
  peak15mRps: 220
  burstRps: 350
  readPercent: 75
  writePercent: 25
dependencies:
  inventoryCallsPerRequest: 0.8
  paymentCallsPerRequest: 0.12
  cacheHitRate: 0.82
objectives:
  availabilitySloPercent: 99.9
  latencyP95TargetMs: 500
~~~

Measurement documentation must specify **where RPS is measured**: requests at ingress, valid requests after authentication, business transactions, or actual attempts reaching downstream services. These are not necessarily equal due to retries, caching, polling, and fan-out.

## 4. Minimum Baseline Metric Set

### 4.1. Traffic, Latency, Errors, Saturation

The four signal groups commonly used in service operations are **traffic**, **latency**, **errors**, and **saturation**:

| Group | Metrics to Record | How to Interpret |
| --- | --- | --- |
| **Traffic** | Requests/second, transactions/second, bytes/s, messages/s | Actual work arriving at the system |
| **Latency** | p50, p95, p99; breakdown by dependency | How slow the experience is for a large share of users |
| **Errors** | 5xx, timeouts, business errors, throttled requests, failed dependencies | Distinguishes app failures from intentional rejections |
| **Saturation** | CPU, memory, GC, thread pool, connection pool, queue depth, IOPS, RU/s | Which resource is nearing its limit |

Add **concurrent request count**, completed throughput, backlog growth/drain, retry rate, cache hit/miss ratio, and successful work per resource unit. Business metrics such as **completed orders/minute** can matter more than total HTTP 200 count.

**Do not draw conclusions from CPU alone.** 30% CPU can still coincide with a 5-second p99 if the app is waiting on a database or external connection. Conversely, rising CPU while throughput and latency stay stable can be acceptable if headroom remains and the app has not breached SLOs.

### 4.2. Percentiles vs. Averages

Suppose out of 100 requests, 95 respond under 200 ms and 5 take nearly 3 seconds. The average may look reasonably good, yet users hitting tail latency still suffer a very poor experience.

- **p50** is the latency that roughly half of requests do not exceed.
- **p95** is the latency that roughly 95% of requests do not exceed.
- **p99** reveals the slowest tail, especially valuable for latency-sensitive services.

Always state the **percentile calculation window** and request set. **Never average per-instance or per-hour p95 values and call it the system-wide p95.** Overall percentiles must be computed from the underlying latency distribution or properly mergeable histograms; if only sampled logs exist, check the sampling policy before inferring exact percentiles.

### 4.3. Defining a Successful Request

HTTP 200 does not always mean a business transaction completed. An API may return 202 Accepted while the order still sits in a queue. Business baselines need statuses for **processed, pending, failed, refunded/reconciled**. For queued systems, throughput should measure both messages received and **messages actually completed**, along with the age of the oldest message.

## 5. Instrumenting Telemetry in an Azure Architecture

A typical observability architecture:

~~~mermaid
flowchart LR
    C["Client"] --> G["Front Door / API Management / Ingress"]
    G --> A["App on App Service, AKS, or Container Apps"]
    A --> D["Database / Cache / Storage"]
    A --> Q["Service Bus / background workers"]
    G -. "Request metrics" .-> M["Azure Monitor"]
    A -. "OpenTelemetry / Application Insights" .-> M
    D -. "Resource metrics / logs" .-> M
    Q -. "Queue metrics / logs" .-> M
    M --> L["Log Analytics, dashboards, and alerts"]
~~~

**Azure Monitor** ingests metrics and logs depending on enabled services/features. **Application Insights** tracks requests, dependencies, exceptions, traces, and application telemetry; many systems integrate **OpenTelemetry** to unify trace context. A **Log Analytics workspace** lets you query telemetry with Kusto Query Language (KQL). AKS can use appropriate container and node observability tools alongside platform/application metrics.

### 5.1. Dimensions to Attach

A measurement becomes meaningful when paired with metadata:

| Dimension | Example | Benefit |
| --- | --- | --- |
| Environment | dev, staging, prod | Avoid mixing test load with production load |
| Service/operation | orders-api / POST /orders | Identify the flow causing bottlenecks |
| Region/zone | southeastasia / assigned zone | Analyze regional latency and localized incidents |
| Deployment version | commit SHA or release ID | Compare before/after deployment |
| Instance/replica | Pod, container, App Service instance | Detect uneven load distribution |
| Dependency | Azure SQL, Redis, Inventory API | Distinguish app bugs from downstream issues |
| Response class | 2xx, 4xx, 5xx, timeout | Count errors per service contract |

Never attach user IDs, tokens, emails, payment data, or extremely high-cardinality values as **metric labels** just for performance analysis. Use traces/logs governed by data protection policies when per-request tracing is needed.

### 5.2. Resolution and Data Quality

Choose resolution according to purpose: hourly data suits trend analysis, yet can hide a 30-second burst that caused errors. Therefore, maintain **long-term aggregations** alongside **short-window views** for peaks, errors, and autoscale.

Verify:

1. Time synchronization and timezone settings when building reports.
2. Whether telemetry is sampled or dropped when the system is overloaded.
3. Whether deployments, scaling events, failovers, and config changes are annotated.
4. Whether application metrics and Azure metrics use matching time units and windows.
5. Whether telemetry ingestion/retention costs fit within budget.

## 6. Collecting Baselines with Azure Monitor and KQL

### 6.1. Example Request Query

In a **workspace-based Application Insights** resource with the **AppRequests** table, you can start with the following query:

~~~kusto
AppRequests
| where TimeGenerated >= ago(14d)
| where Name has "/orders"
| summarize
    rawRows = count(),
    estimatedRequests = sum(ItemCount),
    failedRows = countif(Success == false),
    avgDurationMs = avg(DurationMs),
    p95DurationMs = percentile(DurationMs, 95),
    p99DurationMs = percentile(DurationMs, 99)
  by bin(TimeGenerated, 1h), Name
| extend approxRps = estimatedRequests / 3600.0
| order by TimeGenerated asc
~~~

**Usage notes:**

- Table and column names depend on Application Insights mode, workspace, and schema. Classic mode/queries may use the **requests** table with **timestamp**, **duration**, and **name**. Verify the schema before running.
- **ItemCount** reflects the count represented by a record in configurations with sampling; traffic and error estimation must align with the sampling policy.
- Percentiles computed directly over remaining records are **not automatically accurate percentiles of all requests** when sampling is weighted or non-uniform. Use histograms/appropriate metrics or unsampled test data for critical baselines.
- Grouping by one-hour bins can hide 1-minute peaks. Add a **bin(TimeGenerated, 1m)** report when evaluating bursts, while avoiding percentile inference from bins with too few samples.
- The filter **Name has "/orders"** is only an example. Filter on actual endpoints/operations and exclude probes, bots, or synthetic requests if they are outside the SLI.

### 6.2. Downstream Latency Query

~~~kusto
AppDependencies
| where TimeGenerated >= ago(7d)
| summarize
    calls = count(),
    failures = countif(Success == false),
    p95Ms = percentile(DurationMs, 95)
  by Target, Type, bin(TimeGenerated, 1h)
| order by failures desc
~~~

Compare dependency p95 with end-to-end p95: if total latency rises while dependencies remain unchanged, check CPU, thread pools, serialization, or internal queues. If Azure SQL/Storage processing time increases specifically during peak hours, inspect database resource metrics, throughput, throttling, and potential contention.

### 6.3. Documenting the Baseline

Example **illustrative baseline table** after a measurement run:

| Metric | Normal Hours | Peak Hours | Target / Interpretation |
| --- | ---: | ---: | --- |
| Ingress RPS | 70 | 220 | Verify exact sampling interval |
| Request p50 | 95 ms | 140 ms | Observe typical experience |
| Request p95 | 260 ms | 430 ms | Target p95 no more than 500 ms |
| Request p99 | 580 ms | 960 ms | Monitor tail latency |
| Technical error rate | 0.1% | 0.3% | Clearly define the denominator |
| Avg CPU per replica | 36% | 62% | Do not conclude capacity from CPU alone |
| Memory working set | 690 MiB | 880 MiB | Compare against limit and leak trends |
| Inventory API p95 | 90 ms | 210 ms | Could become a dependency bottleneck |
| Queue backlog | Near 0 | Short-lived spike | Verify backlog drain time |

Always record **data source, measurement date, application version, VM/node/plan SKU, database configuration, replica count, region, cache state, and request mix**. If these factors change, do not compare two p95 numbers as if conditions were identical.

## 7. Designing Benchmarks and Load Tests

### 7.1. Test Types to Distinguish

| Test Type | Load Profile | Purpose |
| --- | --- | --- |
| **Baseline load test** | Steady load at normal levels | Measure reference p95, error rate, and resource usage |
| **Capacity/step test** | Step-wise RPS increases with hold intervals | Find where throughput stops scaling or SLOs break |
| **Stress test** | Controlled load beyond expected capacity | Observe how the system rejects, degrades, and recovers |
| **Spike test** | Sudden short-duration surge | Check headroom, autoscale lag, connection pools |
| **Soak/endurance test** | Extended load to observe accumulation | Detect memory leaks, GC pressure, pool leaks, growing backlog |
| **Scale/failover test** | Add/remove replicas, fail a component in test env | Measure scale time, fault tolerance, and post-failure capacity |

**Azure Load Testing** is one option for running load tests on Azure; depending on features and service version, it can run Apache JMeter-based scripts while observing Azure resource metrics. Other suitable load testing tools can also be used. Tool selection should depend on protocol support, authentication support, traffic generation capacity, cost, and reporting needs.

### 7.2. Benchmark Run Sequence

1. **Lock conditions:** record commit, image digest, CPU/memory requests/limits, node SKU, database tier, replica count, region, and feature flags.
2. **Prepare data:** dataset size and key distribution close to production, synthetic or approved data; avoid using real secrets or customer data.
3. **Prepare load generators:** ensure the generator itself is not the bottleneck; monitor generator CPU/network.
4. **Warm-up:** allow JIT, connection pools, caches, and scaling to reach a state appropriate for the test goal.
5. **Measure baseline:** hold steady load long enough, recording sample counts and metrics with aligned timestamps.
6. **Step up load:** for example 50 → 100 → 150 → 200 → 250 RPS, adjusted to actual capacity.
7. **Stop at guardrails:** p95 breaches SLO, errors spike, data integrity is at risk, or resource usage exceeds allowed limits.
8. **Ramp down and observe recovery:** measure backlog, pools, GC, health checks, and time to return to normal.
9. **Repeat:** check variance across runs and cross-check root causes.

### 7.3. Distinguishing Load Generation Models

**Closed-loop** tests typically simulate a number of virtual users: each waits for a response before sending the next request. When the system slows down, total request rate drops automatically, risking masking the arrival load production will keep sending.

**Open-loop** tests emit requests at a configured arrival rate, useful for evaluating systems under incoming traffic independent of response speed. If the target is 220 RPS, measure the **actual achieved RPS**, not just the tool's configured target.

Both models are useful, but never compare numbers without specifying load generation mode, think time, session model, and business journey ratios. For write tests, handle idempotency/cleanup to avoid polluting state.

## 8. Finding the Usable Capacity Point

Load capacity is not the point where CPU hits 100%. A system's **usable capacity** is the highest level that still satisfies error, latency, correctness, and operational targets.

Example measurements on one application replica, with identical configuration and request mix:

| Load/replica | Avg CPU | p95 | Error rate | Notes |
| ---: | ---: | ---: | ---: | --- |
| 18 RPS | 35% | 190 ms | 0.0% | Ample headroom |
| 28 RPS | 48% | 260 ms | 0.1% | Meets target |
| 35 RPS | 61% | 340 ms | 0.1% | Level chosen for planning |
| 42 RPS | 76% | 530 ms | 0.4% | p95 breaches 500 ms target |
| 50 RPS | 90% | 1,200 ms | 2.1% | Approaching saturation |

**Conclusion for the example:** select **35 RPS/replica** as the initial operational capacity because this load is tested, stays below the 500 ms p95 target, and leaves margin for variance. Do not extrapolate RPS at 100% CPU by linear multiplication: bottlenecks, GC, locks, connection pools, and queues typically make performance non-linear near saturation.

The **35 RPS/replica** figure applies only to the measured configuration. If VM size, CPU request, runtime, database tier, application version, or business mix changes, it must be re-evaluated.

### 8.1. Throughput, Arrival Rate, and Wait Time

In a steady system, completed throughput roughly equals arrival rate. If arrival rate exceeds processing capacity for an extended period, backlog grows. Metrics to watch simultaneously:

- Incoming request rate.
- Succeeded/failed completion rate.
- Queued or rejected request count.
- Queue depth and oldest request age.
- Per-tier latency: ingress, app, database, queue consumer.

A throughput of 200 RPS is not a good result if another 100 RPS is accumulating in a queue. Conversely, controlled backpressure returning 429/503 can protect the availability of the rest of the system.

### 8.2. Little's Law for Estimating Concurrency

For a stable system within the same measurement boundary:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of requests inside the system.
- \(\lambda\): average request completion rate, in requests/second.
- \(W\): average time a request spends in the system, in seconds.

If each replica handles **35 RPS** with an average duration of **180 ms = 0.18 seconds**:

\[
L = 35 \times 0.18 = 6.3
\]

On average, each replica has about **6–7 requests in flight or waiting within the measured boundary**. This figure is not p95 latency multiplied by RPS, because Little's Law uses **average time**, nor does it mean the thread pool only needs 7 threads: you must account for bursts, fan-out, blocking I/O, pool limits, and backlogs.

Do not apply the formula blindly when queues grow continuously, workloads are unstable, or time units are inconsistent.

## 9. Calculating Replica Count and Fault-Tolerance Reserve

Using the illustrative dataset:

- Observed peak: **220 RPS**.
- Tested safe capacity: **35 RPS/replica**.
- Forecast peak growth: **30%**.
- Objective: p95 at most 500 ms on the tested workload.

### 9.1. Minimum Capacity at Current Peak

\[
N_{peak} = \left\lceil \frac{220}{35} \right\rceil = 7
\]

At least **7 replicas with equivalent processing capability** are needed under ideal conditions, assuming even traffic distribution and sufficient dependency capacity.

To maintain one spare replica under an **N+1 (single-replica loss)** assumption:

\[
N_{N+1} = 7 + 1 = 8
\]

However, **8 replicas do not automatically survive losing an entire Availability Zone**. If multiple replicas reside in the failed zone, fewer than 7 may remain.

### 9.2. Capacity After 30% Growth

\[
RPS_{forecast} = 220 \times 1.30 = 286
\]

\[
N_{forecast} = \left\lceil \frac{286}{35} \right\rceil = 9
\]

With single-replica redundancy, consider at least **10 replicas** at the new peak, before accounting for zone loss, platform limits, startup time, and other risks.

### 9.3. Losing an Entire Availability Zone

Suppose the workload and supporting services span **3 zones**, load is evenly distributed, and all replicas share the same safe capacity:

| Scenario | Example Distribution | Remaining if Largest Zone Fails | Enough Capacity per Assumptions? |
| --- | --- | ---: | --- |
| 8 replicas, 220 RPS peak | 3 / 3 / 2 | 5 | **No**, need 7 |
| 12 replicas, 220 RPS peak | 4 / 4 / 4 | 8 | **Yes**, 8 ≥ 7 |
| 10 replicas, 286 RPS peak | 4 / 3 / 3 | 6 | **No**, need 9 |
| 15 replicas, 286 RPS peak | 5 / 5 / 5 | 10 | **Yes**, 10 ≥ 9 |

This is purely **arithmetic capacity**, not proof that the real system will survive a zone outage. You must also verify Pod/instance zone placement, node availability, quotas, database failover, connections, DNS, health probes, traffic shifting time, and the ability to launch replacement replicas.

**N+1 replicas** and **zone resilience** are distinct redundancy levels. If regional disaster recovery is required, a separate capacity calculation is needed for **multi-region**, replication, and RTO/RPO.

## 10. Capacity Is a Chain of Bottlenecks, Not Just Compute

A request traverses multiple tiers. If compute can handle 300 RPS but the database holds its SLO only up to 180 RPS, **the effective capacity of the entire flow remains constrained by the database**.

~~~mermaid
flowchart LR
    C["220 RPS from clients"] --> G["Gateway / ingress"]
    G --> A["Compute replicas"]
    A --> D["Azure SQL / Cosmos DB"]
    A --> K["Cache"]
    A --> Q["Service Bus"]
    D --> S["Storage / network / IO"]
~~~

### 10.1. Azure SQL Database

Monitor CPU/vCore or DTU depending on model, memory/IO where available, connection count, query latency, deadlocks, lock waits, log writes, and resource-heavy queries. Capacity can be improved via index tuning, reducing query count, appropriate caching, pooling, architectural read scaling, or selecting an appropriate tier/compute size.

Do not upgrade the SQL tier merely because request latency rose. First examine query plans, indexes, lock contention, application bugs, or N+1 query patterns. When the database tier changes, re-benchmark with matching data and request mix.

### 10.2. Azure Cosmos DB

Capacity must account for **request units per second (RU/s)** and **partition-level load distribution**. A rough initial estimate:

\[
RU/s_{estimate} = \sum_i (operationRate_i \times averageRU_i)
\]

For example, **150 reads/s × 3 RU/read** and **50 writes/s × 8 RU/write**:

\[
RU/s = 150 \times 3 + 50 \times 8 = 850
\]

**850 RU/s is an assumed average compute demand**, excluding bursts, document/query size variance, indexing, background load, partition imbalance, or hot-partition effects. Measure **RequestCharge**, **429** throttling, normalized RU consumption, and actual latency before choosing manual or autoscale throughput, and verify account and partition limits/capabilities.

### 10.3. Azure Cache for Redis or Chosen Cache Service

Monitor cache hit ratio, memory pressure, evictions, network throughput, CPU, connection count, and p95 latency. Raising cache hit rate can reduce database load, but cache warming and cache stampedes after restarts or failovers can generate heavy spikes.

Distinguish **cache capacity by data size** from **capacity by operations/second**. A cache with plenty of RAM can still bottleneck on network or CPU.

### 10.4. Azure Service Bus, Event Hubs, and Background Workers

For asynchronous pipelines, measure:

- Message arrival rate and completion rate.
- Queue depth, message age, dead-letter count.
- Consumer count and concurrency per consumer.
- Average/p95 processing time, retry rate, lock timeouts, or throttling.
- Throughput limits and quotas of the selected tier/namespace.

If messages arrive at **500/s** while workers process **400/s**, the backlog grows by roughly **100 messages/s** while that rate persists. After 10 minutes:

\[
backlog \approx 100 \times 600 = 60,000 \text{ messages}
\]

Even after traffic drops, calculate **backlog drain time**. If workers process 600/s while 500/s still arrive, net drain capacity is 100/s; clearing 60,000 messages takes roughly 600 seconds, assuming steady speed and no errors.

### 10.5. Storage and Networking

Monitor Azure Storage transactions, ingress/egress, latency, throttling, capacity, throughput, and IOPS appropriate to the storage type. For partitioned designs, inspect hot partitions and account/resource limits.

Networking must account for bandwidth, connection count, SNAT port consumption for outbound traffic through NAT components, new connections/second, round-trip time, gateway services, and cross-region traffic. SNAT exhaustion can manifest as connection timeouts while CPU remains low.

### 10.6. Quotas and Subscriptions

**Autoscale cannot bypass quotas and platform limits.** Check vCPU quotas by family/region, IP counts, node/Pod limits, subnet IP capacity, database/queue resources, and service-specific quotas. Account for lead time to request quota increases and regional capacity availability; do not wait until campaign day to request quota.

## 11. Scenario-Based Capacity Forecasting

Forecasts must separate **demand projection** from **resource provisioning capability**. An initial model can use:

\[
Demand_{future} = BaselinePeak \times (1 + growthRate) \times eventFactor
\]

For example, with a current peak of **220 RPS**, 30% growth, and an event day peaking at **1.5×** the grown peak:

\[
Demand = 220 \times 1.30 \times 1.5 = 429 \text{ RPS}
\]

If safe capacity remains 35 RPS/replica, the theoretical replica count is:

\[
\left\lceil 429 / 35 \right\rceil = 13
\]

The number 13 does not include replica/zone redundancy, nor does it prove the database or queue can sustain 429 RPS. Short events require checking **autoscale ramp-up time**: if traffic spikes in 30 seconds while provisioning nodes and warming up takes several minutes, you need **pre-scaling** or sufficient headroom ahead of the event.

### 11.1. Three Scenarios to Present to Operations

| Scenario | Traffic Input | Actions to Verify |
| --- | --- | --- |
| **Base** | Measured 220 RPS peak | Maintain SLO, observe normal metrics |
| **Growth** | 30% peak growth to 286 RPS | Adjust min/max replicas, compute, database, quotas |
| **Event / stress** | Short 429 RPS peak | Pre-scale, rate limits, caching, queues, load-shedding policies |

To avoid underestimating risk, add a scenario for **losing an instance, zone, or dependency** during high load. Forecasts should include uncertainty ranges—such as 20–40% growth or expected traffic bands—rather than presenting a single number as a certainty.

### 11.2. Headroom and Reaction Time

There are two types of headroom to consider:

- **Performance headroom:** spare capacity relative to tested load, below SLO thresholds.
- **Provisioning headroom:** available quotas, nodes, IP addresses, database throughput, and budget to scale further.

If autoscale takes 5 minutes to add enough replicas while a spike starts in 20 seconds, headroom must absorb traffic during that wait. For queues, also calculate backlog limits and maximum acceptable wait time.

## 12. Integrating the Capacity Plan with Azure Autoscale

### 12.1. Choosing Scaling Signals Matched to the Bottleneck

| Platform | Common Mechanisms | Metrics to Consider |
| --- | --- | --- |
| **AKS** | Horizontal Pod Autoscaler (HPA), node autoscaling, appropriate event-driven scalers | CPU, memory, custom/external metrics, pending Pods |
| **Azure Container Apps** | Scale rules on HTTP, events/queues, or supported custom scalers | Concurrent HTTP requests, queue depth, latency |
| **Azure App Service** | App Service autoscale/automatic scaling depending on plan and features | CPU, memory, HTTP queue, schedules, appropriate metrics |
| **Azure Functions** | Plan/trigger-based scaling and concurrency settings | Queue backlog, trigger throughput, execution duration |
| **Azure SQL/Cosmos DB** | Adjusting compute/tier or throughput via supported mechanisms | Query latency, CPU/DTU, RU consumption, throttling |

No single autoscale policy fits every part of a system. For example, CPU-based scaling poorly detects I/O-bound or database-waiting bottlenecks. Queue-depth scaling can suit workers but must factor in processing speed and downstream limits.

### 12.2. AKS HPA Example

The following snippet illustrates a CPU-based HPA:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 4
  maxReplicas: 15
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

**Prerequisites:** the **orders-api** deployment exists, containers specify appropriate **CPU requests**, resource metrics are available, and the node pool can schedule additional Pods. HPA CPU utilization is evaluated relative to CPU **requests**, not percentage of total physical node CPU. For example, if a container requests **500m**, a 65% target corresponds to an average of roughly **325m** CPU usage per Pod as calculated by HPA metric logic.

**minReplicas: 4** and **maxReplicas: 15** only illustrate syntax. With a 220 RPS peak and the zone-loss requirement from Section 9, **4 starting replicas may lack capacity before scaling completes**. Production must recalculate minimum replicas, zone distribution, PodDisruptionBudgets/topology spread constraints, startup times, cluster autoscaler, and quotas.

HPA cannot create new nodes when a node pool runs out of room; the node autoscaler must also satisfy quotas, resource limits, and networking constraints. A CPU HPA may not resolve SQL throttling, and adding Pods can sometimes increase pressure on the database.

### 12.3. Scale Testing Scenario

An autoscale test plan should record:

1. The load level that crosses the metric threshold and when scaling begins.
2. Time for HPA to request new replicas.
3. Time for new nodes to become ready if needed.
4. Image pull, app startup, cache warm-up, and readiness time.
5. p95/error rate throughout the transition period.
6. Ramp-down duration and ability to scale down without disrupting active transactions.

**Scale-to-zero**, cold starts, and minimum replicas require special evaluation for interactive workloads. Never look only at the final replica count while ignoring user experience during the scaling lag.

## 13. SLOs, Error Budgets, and Capacity Guardrails

A capacity plan needs concrete **accept/reject** criteria. Illustrative SLOs:

- Over 30 days, **99.9% of valid requests are served successfully**, per the SLI definition.
- At a 220 RPS peak with the defined business mix, **end-to-end p95 is at most 500 ms**.
- Timeout or 5xx rates on test workloads do not exceed thresholds set by operations.
- When one replica is taken out of service, the system continues serving within agreed limits.

If you choose a **99.9%** availability SLO over valid requests, the nominal error budget is **0.1% of requests in the measurement window**. Do not automatically translate this into "43.2 minutes of downtime/month" for every system, because request-based SLIs and time-based SLIs are defined differently.

### 13.1. Load Test Guardrails

An illustrative guardrail set:

| Condition | Action |
| --- | --- |
| p95 exceeds 500 ms during steady measurement window | Record that load level as exceeding capacity criteria |
| 5xx/timeout rate spikes | Stop increasing load, inspect dependencies |
| Queue oldest-message age exceeds business limit | Stop increasing load and inspect workers/capacity |
| Memory rises without recovering when load drops | Run soak/profiling tests to find leaks |
| Database throttling surges | Do not blindly scale app replicas; check database throughput |
| Test data risks impacting systems outside scope | Abort test and isolate workload |

SLOs should be measured per critical journey, region, and environment. Do not use a single aggregated p95 to hide issues affecting specific user segments.

## 14. Cost Planning and Resource Efficiency

A capacity plan must demonstrate **affordability**. Azure costs can span compute, storage, databases, caching, networking/egress, log ingestion, monitoring, load testing, and redundancy mechanisms.

### 14.1. Illustrative Cost Formula

Assume **one compute unit equivalent to one replica costs $0.12/hour**, running **730 hours/month**. This is a **hypothetical price for learning calculations**, not an Azure quote, and does not apply verbatim to AKS/App Service/Container Apps.

~~~text
monthlyComputeCost = capacityUnits × unitCostPerHour × hoursPerMonth
~~~

| Scenario | Compute Units | Calculation | Hypothetical Monthly Cost |
| --- | ---: | --- | ---: |
| 220 RPS peak, N+1 | 8 | 8 × 0.12 × 730 | $700.80 |
| 220 RPS peak, survive one zone loss (assumed) | 12 | 12 × 0.12 × 730 | $1,051.20 |
| 286 RPS peak, survive one zone loss (assumed) | 15 | 15 × 0.12 × 730 | $1,314.00 |

**Important note:** Actual AKS costs typically depend on VMs/nodes, disks, networking, load balancers, and other components; a Pod/replica has no separate fixed price when sharing nodes. Container Apps and App Service have different billing models. Use the **Azure Pricing Calculator, Azure Cost Management**, and quotes applicable to your project's subscription/region to replace these assumptions with real pricing.

### 14.2. Efficiency and Redundancy

Cost cannot be optimized solely by reducing replica counts. Balance:

- Standing cost of minimum replicas vs. scale-up time during spikes.
- Node/zone counts for fault tolerance vs. required service levels.
- Database reserved capacity/tiers and necessary headroom.
- Cache hit rate, connection pooling, and query optimization.
- Log/trace ingestion costs and sampling matched to investigation needs.
- Cross-region or cross-zone egress costs when changing architecture.

One useful efficiency metric is **cost per 1,000 completed business transactions**. However, it must be paired with SLOs: lower cost means nothing if successful transactions drop sharply or latency exceeds thresholds.

## 15. Verifiable Capacity Plan Template

A capacity plan should be managed as an engineering decision with an accountable owner. Minimum template:

| Section | Content to Complete |
| --- | --- |
| Workload and scope | Service name, journeys, region, environment, measurement boundaries |
| Baseline evidence | Links to dashboards/test runs, measurement date, release, configuration |
| SLOs/guardrails | Availability, p95/p99, error, backlog, and stop thresholds |
| Current demand | Normal RPS, peak, burst, business operation mix |
| Forecast | Growth, seasonality, event scenarios, confidence level |
| Measured safe capacity | RPS/replica or transactions/tier under tested conditions |
| Dependency constraints | SQL/Cosmos/queue/cache/storage/network, quotas |
| Resilience requirement | Replica/zone/region loss, RTO/RPO where relevant |
| Scaling design | Min/max, triggers, cooldowns, lag, pre-scale |
| Resource changes | Node/instance counts, tiers, quota requests, deadlines |
| Cost estimate | Pricing assumptions, range, excluded cost components |
| Owner and review date | Decision maker, next review date, trigger events |

Example partial plan:

~~~yaml
service: orders-api
region: southeastasia
scope: "production / ingress / user checkout"
baseline:
  peakRps: 220
  measuredSafeRpsPerReplica: 35
  p95LimitMs: 500
  sampleStatus: "hypothetical-teaching-example"
forecast:
  peakGrowthPercent: 30
  forecastPeakRps: 286
availability:
  zones: 3
  lossScenario: "one zone loses capacity"
capacity:
  peakNowReplicasForZoneLoss: 12
  forecastReplicasForZoneLoss: 15
  verifiedByFailoverTest: false
actions:
  - "verify zone placement and node capacity"
  - "verify SQL/queue/network at 286 RPS"
  - "increase quota before peak period"
  - "run load and failover tests"
owner: "platform-operations"
nextReview: "before next major release or high-load event"
~~~

The YAML file above is a **governance plan template**, not an Azure Deployment, Bicep, or HPA configuration to apply directly.

## 16. Integrating Capacity Planning into Operations

### 16.1. Recurring Cadence

A sensible cadence might include:

1. **Daily:** track SLOs, errors, p95/p99, resource saturation, backlogs, and anomalous spend.
2. **Weekly:** compare current baselines against the prior week under comparable conditions; note drift.
3. **Before major releases:** benchmark regressions with the new commit/configuration; compare p95 and safe RPS.
4. **Monthly or per planning cycle:** update forecasts, check quotas, and review cost plans.
5. **Before major events:** confirm pre-scaling, database capacity, quotas, and load-shedding drills.
6. **After incidents or architectural changes:** establish a new baseline and correct disproven assumptions.

This cadence is only a suggestion; adjust it for traffic volatility and criticality. A rapidly changing system may require evaluation multiple times a week.

### 16.2. Connecting CI/CD to Performance Regressions

In pipelines, smoke/performance tests can run in staging to compare the current build with the latest baseline. Comparisons must use identical resource types, datasets, and workload mixes; otherwise, results are only directional signals.

An illustrative review rule:

~~~text
If p95 increases > 20% vs. baseline under identical conditions
  or safe throughput drops > 15%
  or memory grows continuously during a soak test:
    require change review before promoting to production
~~~

The 20%/15% thresholds are **hypothetical examples**, not Azure standards. To avoid false positives, account for test run count, measurement variance, sample size, statistical confidence, and external dependency effects.

### 16.3. Action Trigger Thresholds

Instead of merely writing "monitor CPU," the plan should define **condition → action → owner**:

| Condition | Action | Owner |
| --- | --- | --- |
| Peak forecast exceeds 80% of tested capacity | Schedule load test and capacity review | SRE/Platform |
| Scale-out time exceeds spike onset time | Pre-scale or increase headroom | Operations |
| SQL p95 rises before app CPU rises | Profile/tune SQL and evaluate tier | Database owner |
| Queue age exceeds target despite low worker CPU | Check throttling, concurrency, locks, downstream | Backend team |
| Quota is below desired max scale | Request quota increase and check regional availability | Cloud admin |
| Cost/transaction rises after release | Analyze cache hits, retries, fan-out, resource allocation | Engineering + FinOps |

## 17. Real-World Scenario: Enough App Capacity Yet Still Slow

The development team sees `orders-api` at a 220 RPS peak with 55% CPU across 8 replicas, while p95 climbs to 1.6 seconds. They plan to scale to 16 replicas. Telemetry shows:

- Application CPU stays below 65%.
- 70% of request duration is spent in Azure SQL queries.
- The database exhibits lock waits and one query with high read counts.
- HTTP pools begin waiting on connections, while app memory remains plentiful.

Analysis:

1. Compute has not been proven to be the bottleneck. Adding replicas may increase connections/queries hitting SQL and worsen lock contention.
2. Locate slow queries, execution plans, indexes, transaction scopes, and connection pool settings.
3. Re-benchmark after SQL tuning while keeping workload and measurement setup constant.
4. If the database still hits tier limits, consider changing tier/capacity and testing before modifying production.
5. Update the baseline and capacity plan after finding the new saturation point.

**An infrastructure change is only right when it addresses a measured bottleneck.** Adding instances does not necessarily increase end-to-end business throughput.

## 18. Hands-On Exercise: Baseline and Forecast for `orders-api`

**Context:** The `orders-api` service runs in an authorized Azure test environment. Learners have permissions to read metrics, run non-destructive load tests, and do not use real customer data.

### Exercise A — Build a Measurable Baseline

1. Select 2–3 business journeys (browse products, view cart, create test order).
2. Record traffic share per journey, region, version, replica count, CPU/memory requests, and database tier.
3. Collect request/dependency latency (p50/p95/p99), errors, throughput, concurrent requests, and resource saturation.
4. Plot per-minute RPS and per-minute latency; annotate load change timestamps.
5. Summarize results into a baseline table with data sources and measurement timestamps.

**Completion criteria:** Enough context is included for someone else to reproduce the measurement; do not submit only a CPU screenshot or a single p95 number.

### Exercise B — Testing to Find Safe Capacity

1. Start at low load and run a warm-up.
2. Increase load in steps and record metrics over aligned steady windows.
3. Stop at error/latency thresholds or chosen guardrails.
4. Identify the highest load level still meeting targets.
5. Repeat to verify whether results are consistent.

**Completion criteria:** A **safe RPS/capacity unit** is identified along with constraints across database, network, cache, and load generation model.

### Exercise C — Creating a Forecast and Capacity Plan

Using the assumptions **220 RPS peak**, **35 RPS/replica**, **30% growth**:

1. Calculate replicas needed for current peak and post-growth peak.
2. Add N+1 and then evaluate losing one zone out of 3 zones.
3. Assume event traffic reaches 1.5× the grown peak; estimate demand and evaluate autoscale lag.
4. Verify whether database, queue, IPs, and quotas suffice for the new replica count.
5. Estimate cost using environment-specific quotes or explicitly stated hypothetical pricing.
6. Write a capacity plan document with owners, actions, deadlines, and verification conditions.

**Completion criteria:** Do not return only a replica number; include SLOs, dependencies, scale timing, fault-tolerance requirements, and costs.

### Exercise D — Rehearsing a Bottleneck

In the test environment, simulate a slow SQL dependency or under-provisioned queue consumer with guardrails active. Observe that scaling app replicas may leave latency/backlog poor. Propose actions addressing the root cause and re-measure.

**Completion criteria:** The report distinguishes "insufficient compute" from "dependency bottleneck," rather than arbitrarily sizing up compute to make one metric look better.

## 19. Common Pitfalls When Building a Baseline

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Two benchmarks differ widely | Different workload mix, cache state, data, config, or load source | Lock conditions and repeat runs |
| Dashboard p95 differs from log query p95 | Different window, sampling, histogram, or request set | Align measurement boundaries and percentile logic |
| Low CPU yet slow app | Waiting on database, pools, queues, network, or locks | Use tracing, dependency metrics, profilers |
| RPS stops rising despite more virtual users | Generator bottleneck or closed-loop slowing with response time | Measure actual arrival RPS and generator utilization |
| Scaling many Pods leaves Pods Pending | Insufficient nodes/IPs/quotas/placement | Check scheduler events, node autoscaler, subnet |
| Autoscale misses spikes | Startup, image pull, metric lag, or cooldown | Pre-scale, add headroom, optimize startup |
| Cosmos DB 429s while app CPU is low | Insufficient RU/s or hot partitions | Check RequestCharge, partitions, throughput |
| Queue depth drops yet business work is incomplete | Consumers pull messages but fail or process slowly | Measure successful completions and message age |
| Cost rises while p95 stays flat | Bottleneck in another tier, overprovisioning | Compare before/after bottlenecks, cost per transaction |
| App meets SLO normally but fails on zone loss | Insufficient capacity in remaining zones | Test actual failover and placement |
| Baseline quickly becomes stale | Releases, traffic, data, or tiers changed | Version baselines and schedule updates |
| Only averages are stored | Hides tail latency and bursts | Collect p95/p99 and short-window peaks |

## 20. Knowledge Check

**Q1.** How do a performance baseline and a capacity plan differ?  
**A:** A baseline is a measurement under defined conditions; a capacity plan uses baselines, tests, and forecasts to decide resources, fault tolerance, autoscale, costs, and actions.

**Q2.** Why does 40% average CPU not prove 60% application capacity remains?  
**A:** Performance does not scale linearly with CPU, and the bottleneck may lie in databases, locks, queues, networking, or memory.

**Q3.** When 35 RPS/replica is the tested level meeting the SLO, what is the minimum replica count for a 220 RPS peak under ideal conditions?  
**A:** \(\lceil 220/35 \rceil = 7\) replicas, excluding redundancy.

**Q4.** If forecast peak is 286 RPS across three zones, do 10 total replicas guarantee surviving the loss of one zone?  
**A:** No. With a 4/3/3 split, losing the 4-replica zone leaves only 6, whereas calculation requires 9 replicas for the forecast peak. You must evaluate placement and higher redundancy, such as 15 replicas split 5/5/5 under the illustrative assumptions.

**Q5.** Does Little's Law use p95 latency or average latency?  
**A:** It uses the **average** residence time of a request in a stable system; p95 cannot be substituted directly for \(W\).

**Q6.** Why can you not average hourly p95 values to obtain a daily p95?  
**A:** Percentiles are properties of a distribution and do not combine linearly; you must merge distributions/histograms or compute over the full dataset.

**Q7.** Why might HPA adding Pods fail to help a slow API?  
**A:** HPA only increases Pods when scaling conditions trigger; nodes or quotas may be exhausted, or the bottleneck may be in the database, queue, or network.

**Q8.** When should you pre-scale instead of waiting for autoscale?  
**A:** When a spike is predictable and arrives faster than the time required for metrics to trigger, nodes to provision, images to pull, and enough replicas to start.

**Q9.** Can an estimated Cosmos DB RU/s value be used immediately as provisioned throughput?  
**A:** Not yet. You must measure RequestCharge, partition distribution, 429s, bursts, indexing, and account limits before deciding.

**Q10.** Is the $1,314/month cost in this lesson an Azure quote for 15 replicas?  
**A:** No. It is a calculation using hypothetical pricing and compute units; actual cost depends on service plan, nodes/VMs, storage, networking, region, and other components.

## 21. Checklist for Applying to an Azure Project

- [ ] Workload mix, peaks, bursts, seasonality, read/write ratio, dependencies, and concurrency are documented.
- [ ] Clear SLIs/SLOs exist for latency, availability, and business outcomes.
- [ ] Telemetry covers requests, dependencies, errors, CPU, memory, pools, queues, storage, databases, and networking.
- [ ] Baselines record timestamp, version, configuration, data source, deployment region, and sampling status.
- [ ] Benchmarks include adequate warm-up, multiple load steps, guardrails, and recovery checks.
- [ ] Safe capacity is chosen based on SLOs and real measurements, not linear extrapolation from CPU.
- [ ] Capacity plan accounts for growth, event traffic, headroom, and autoscale lag.
- [ ] N+1 is distinguished from zone/region loss requirements.
- [ ] Database, cache, queue, storage, network, IP, and Azure quota capacities are verified.
- [ ] Autoscale min/max, trigger metrics, reaction time, and scale-down behavior are tested.
- [ ] Projected costs include pricing sources/assumptions, budgets, and accountable owners.
- [ ] Action triggers, review cadence, and post-release or post-incident re-testing plans are established.

**Core takeaway:** A trustworthy baseline must be tied to a specific workload and measurement environment. A good capacity plan combines that baseline with load tests, forecasts, SLOs, dependency constraints, and fault-tolerance requirements to drive verifiable decisions. In Microsoft Azure, sustaining the loop of measure → forecast → provision → test → optimize keeps systems more reliable and anchors infrastructure spend in clear evidence.
