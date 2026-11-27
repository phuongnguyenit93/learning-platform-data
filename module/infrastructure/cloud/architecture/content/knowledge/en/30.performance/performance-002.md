# Throughput, Concurrency, Latency, and Queueing Relationships

## 1. Four Core Quantities Describing System Performance

When evaluating a cloud service, you need to understand how much work the system completes, how many operations are running concurrently, how long each operation takes, and how long work waits before being processed. These four concepts are tightly coupled:

- **Throughput:** the rate at which a system completes work per unit of time, such as requests/second, transactions/second, or messages/second.
- **Concurrency:** the number of operations currently being processed or present in the system at the same time, depending on how it is measured.
- **Latency:** the time from when an operation starts until its corresponding result is returned or the work finishes.
- **Queue:** a holding place for work waiting for resources or the next processing step.

Queues help absorb bursts and decouple producer rates from consumer rates. However, queues do not create infinite capacity. When arrival rates exceed processing rates over sustained periods, backlogs and wait times grow. A high-throughput system can still exhibit terrible latency if the number of waiting requests builds up rapidly.

In the **CLOUD_ARCHITECTURE** module, the **Performance** chapter treats these quantities as an interrelated system. Decisions around compute, databases, networking, caching, and workers must be grounded in workload characteristics, SLOs, resource limits, and behavior under increasing load.

After this lesson, learners will be able to:

1. Distinguish between throughput, concurrency, latency, queue depth, and queue wait.
2. Apply Little's Law to estimate average concurrent work.
3. Explain how utilization, service time, and arrival rate affect wait times.
4. Analyze queue backlogs, drain times, and instability points.
5. Choose concurrency limits, worker counts, connection pools, and queue policies.
6. Design backpressure, admission control, timeouts, and retry budgets.
7. Read p50/p95/p99 percentiles and detect tail latency and saturation.
8. Build workload models and repeatable performance tests.

## 2. Define Metrics Precisely Before Measuring

Metrics are only meaningful when measurement boundaries are clearly defined.

| Quantity | Question | Common units |
| --- | --- | --- |
| Arrival rate (λ) | How much work arrives each second? | requests/s, messages/s |
| Throughput (X) | How much work completes each second? | requests/s, jobs/s |
| Concurrency (L) | How much work is currently inside the system? | requests, jobs, sessions |
| Response time (W) | How long does one piece of work stay in the system? | ms, s |
| Service time (S) | How long does a resource actively process the work? | ms, s |
| Queue depth (Q) | How many items are currently waiting? | messages, jobs |
| Queue wait (Wq) | How long does an item wait before service starts? | ms, s |
| Utilization (U) | What fraction of time/capacity is a resource busy? | ratio, % |

Throughput does not necessarily equal arrival rate. In a long-term stable system, throughput can track close to arrival rate if work is not dropped, rejected, or accumulated in a backlog. When load exceeds capacity, throughput typically hits a ceiling while arrival rate continues to rise.

Latency must specify exact start and end points: from client request send to response receipt, from gateway to service, or purely database processing time. Never compare numbers that use different measurement boundaries.

## 3. Little's Law

Little's Law relates the average number of items in a stable system to the average throughput and the average time each item spends in the system:

```text
L = λ × W

L: average number of items in the system
λ: average throughput / arrival rate in steady state
W: average time in the system
```

For example, if a system completes 200 requests/s and each request spends an average of 0.25 seconds in the system:

```text
L = 200 requests/s × 0.25 s
  = 50 requests
```

On average, about 50 requests are present in the system. This represents average concurrency within the chosen boundary, not directly the number of threads or connections to configure.

### 3.1. Conditions for Application

Little's Law applies to a stable system over a suitable observation window, with consistent flow definitions:
- The system does not accumulate an unbounded backlog over the measurement interval.
- Arrivals and departures are measured over the same population.
- Time in system is measured from when an item enters to when it leaves the same boundary.
- Averages are computed over the same measurement window.

If arrival rate is rising and the backlog is continuously growing, multiplying λ by W over a short snapshot may not describe steady state. The formula remains a flow relationship, but care is needed with measurement windows and transient behavior.

### 3.2. Solving for Other Quantities

```text
Throughput: λ = L / W
Time in system: W = L / λ
Average concurrency: L = λ × W
```

If you only know a concurrency limit and a latency budget, you can estimate feasible average throughput via L/W. This is an average-case flow estimate; it does not yet account for CPU, I/O, locks, fan-out, or downstream service capacity.

## 4. Separating Queue Wait and Service Time

An operation's response time can consist of multiple components:

```text
Response time =
    queue wait
  + service processing
  + downstream wait
  + network / serialization / scheduling overhead
```

In a simple worker queue:

```text
W = Wq + S

Wq: time waiting before service
S: service time after a worker starts
```

For example, a job takes 120 ms to process but waits 1.8 seconds in the queue. Optimizing the algorithm to reduce service time from 120 ms to 80 ms yields only a small improvement; the primary issue lies in queue wait or consumer capacity.

You must measure each component using traces/spans or queue telemetry rather than looking only at end-to-end latency.

## 5. Arrival Rate, Service Rate, and Stability Conditions

Let:
- λ be the work arrival rate.
- μ be the processing rate of a single worker.
- c be the number of workers running in parallel.

Theoretical processing capacity:

```text
Service capacity ≈ c × μ
```

In a simple model with identical workers, the system can remain stable when λ is less than total service capacity. If λ exceeds capacity for a sustained period, the backlog grows roughly at the difference rate.

```text
Backlog growth rate ≈ λ - c × μ
when λ > c × μ
```

For example, producers enqueue 500 jobs/s, each worker processes 100 jobs/s, and there are 4 workers:

```text
Total service capacity = 4 × 100 = 400 jobs/s
Backlog growth = 500 - 400 = 100 jobs/s
```

After 10 minutes, under simplified conditions with no drops/scaling/retries, the backlog grows by roughly 60,000 jobs. A queue only delays the onset of overload when capacity shortfalls persist.

## 6. Utilization and Wait Time

Utilization measures the fraction of capacity currently in use. In an ideal model with c identical workers:

```text
ρ = λ / (c × μ)

ρ: utilization ratio
```

As ρ approaches 1, the system has little spare capacity to absorb fluctuations. Queue wait can grow rapidly even when throughput increases only slightly. Because arrivals and service times vary, operating near 100% utilization typically degrades tail latency.

### 6.1. Intuitive Example

A worker has a capacity of 100 jobs/s:
- Load at 50 jobs/s: ample capacity remaining for bursts.
- Load at 80 jobs/s: 80% utilization, less headroom.
- Load at 98 jobs/s: 98% utilization, a small burst or slow job can create a long queue.
- Sustained load at 110 jobs/s: backlog grows because arrivals exceed service capacity.

There is no single utilization threshold that fits every system. Databases, CPU-bound services, network I/O, and queue workers have different profiles. Establish ceilings from load tests and SLOs rather than applying a universal percentage.

### 6.2. Service Time Variability

When service times have high variance, occasional slow jobs hold workers longer, forcing subsequent jobs to wait. Two systems with the same average service time but different variance can have very different queue latencies.

Always inspect the service time distribution, not just the average. Heavy-tailed workloads, lock contention, garbage collection, cold caches, and downstream timeouts all amplify tail behavior.

## 7. Queueing Models and M/M/1 Intuition

M/M/1 is a foundational queueing model with:
- Arrivals following a Poisson process.
- Exponentially distributed service times.
- A single server/worker.
- System stability when λ < μ.

In this model:

```text
ρ = λ / μ

Average time in system:
W = 1 / (μ - λ)

Average number in system:
L = λ / (μ - λ)

Average queue wait:
Wq = ρ / (μ - λ)
```

For example, μ = 100 jobs/s.

| Arrival rate λ | Utilization ρ | Average time in system W |
| ---: | ---: | ---: |
| 50 jobs/s | 50% | 20 ms |
| 80 jobs/s | 80% | 50 ms |
| 90 jobs/s | 90% | 100 ms |
| 95 jobs/s | 95% | 200 ms |
| 99 jobs/s | 99% | 1 s |

The table shows that as utilization nears 100%, average time in the system grows nonlinearly in the model. This provides useful intuition, not a direct forecasting formula for every production service.

### 7.1. M/M/c and Model Limitations

With multiple workers, queueing behavior depends on server count, arrival/service distributions, and the scheduler. M/M/c can estimate wait probabilities and queueing delays under simplified assumptions.

Real-world systems commonly involve:
- Multiple request types with differing costs.
- Separate worker pools.
- Downstream dependencies.
- Batch processing.
- Retries and timeouts.
- Rate limits and admission control.
- Autoscaling with lag.

Use queueing models to form hypotheses, then validate them with workload tests and real telemetry.

## 8. Concurrency Is Not Synonymous with Thread Count

Concurrency describes the number of operations existing or in progress at the same time. Thread count is one specific implementation mechanism, not the definition of concurrency.

An asynchronous runtime can keep many requests waiting on I/O using few threads. Conversely, many threads may exist while most sit idle or contend on locks.

Distinguish among:
- **In-flight requests:** requests received but not yet completed.
- **Active execution:** requests currently using CPU or a worker.
- **Waiting operations:** requests waiting on a database, network, lock, or queue.
- **Open connections:** existing connections, not necessarily actively processing.
- **Threads/tasks:** execution units managed by the runtime.

Do not blindly increase thread counts just to handle higher concurrency. If the bottleneck is database connections or downstream quotas, adding threads can worsen contention and memory consumption.

## 9. Latency Distribution and Tail Latency

Average latency can mask poor experiences for a subset of requests. Track percentiles:

- **p50:** median; half of requests finish faster than or equal to this value.
- **p90/p95:** most requests finish within this bound; useful for SLOs.
- **p99/p99.9:** the tail, showing the experience of the slowest requests.
- **Max:** heavily influenced by outliers and sample size; should not be used alone.

Example:

| Metric | Search API |
| --- | ---: |
| p50 | 45 ms |
| p95 | 180 ms |
| p99 | 1.4 s |
| Max | 4.8 s |

A good median alongside a high p99 can indicate hot partitions, GC pauses, locks, retries, cache misses, or downstream tail latency.

### 9.1. Percentiles Do Not Add Simply

If a request calls multiple services sequentially, end-to-end latency is the sum of components per individual request. You cannot add service A's p99 to service B's p99 and treat that as end-to-end p99, because those percentiles may come from different requests.

Use distributed tracing or end-to-end histograms to see which path requests actually take and which components drive the tail.

### 9.2. Coordinated Omission

A load generator might send a new request only after the previous one finishes. When the system slows down, the generator automatically lowers offered load and skips the timestamps when requests should have been sent; latency reports therefore underestimate the tail.

Use open-loop or schedule-aware load generation when you need to simulate arrival rates independent of response times, while ensuring the load generator itself does not become a bottleneck.

## 10. Queue Depth, Queue Age, and Queue Wait

Queue depth is the number of waiting items. However, depth alone does not reveal wait time because service rates and work sizes vary.

Track:
- Queue depth/backlog.
- Oldest message age.
- Enqueue rate and dequeue/completion rate.
- Processing duration.
- Retry count and visibility timeout.
- Dead-letter queue depth.
- Estimated drain time.
- Per-tenant or per-priority backlog when appropriate.

### 10.1. Queue Age Often Reflects Experience Better

A queue with 10,000 messages and consumers processing 20,000/s can drain quickly. Another queue with 100 messages where each message takes 30 seconds to process still leaves the oldest message waiting a long time.

For business deadlines, oldest age and estimated wait are often more informative than depth alone.

## 11. Calculating Backlog Drain Time

If a backlog has B items, stable arrival rate λ, and total service capacity μ_total, with μ_total > λ:

```text
Net drain rate = μ_total - λ

Approximate drain time = B / (μ_total - λ)
```

For example, a queue has 90,000 jobs, producers continue sending 100 jobs/s, and workers process 400 jobs/s in total:

```text
Net drain rate = 400 - 100 = 300 jobs/s

Drain time = 90,000 / 300
           = 300 seconds
           = 5 minutes
```

If producers stop completely, drain time is approximately B/μ_total. If the processing rate does not exceed the arrival rate, the backlog will not drain.

This is an estimate assuming steady rates and roughly uniform job costs. With multiple priorities, retries, batches, and variable service times, simulation or live measurement is needed.

## 12. Backpressure and Admission Control

**Backpressure** is a mechanism that signals or throttles upstream senders when downstream cannot accept more work. **Admission control** decides which requests are allowed into the system based on capacity, priority, and policy.

Measures include:
- Bounded queues instead of unbounded queues.
- Limiting in-flight requests and worker concurrency.
- Rate limiting by client/tenant/route.
- Returning 429/503 with appropriate retry guidance.
- Throttling queue producers based on quota or demand.
- Prioritizing critical workloads and deferring best-effort work.
- Load shedding when latency/queue depth crosses thresholds.
- Circuit breakers to stop sending traffic to failing dependencies.

Unbounded queues usually convert overload into severe latency and delayed memory exhaustion. Bounded queues make the system reject earlier and more clearly, protecting the rest of the system.

### 12.1. Bounded Queues

Choose queue capacity based on:
- Maximum wait time acceptable to the business.
- Consumer throughput and peak arrival rates.
- Per-item memory/disk budget.
- Durable persistence capabilities.
- Expected time to recover consumers.

Do not pick queue size under the assumption that "bigger is always safer." Very large queues can hold work past its deadline and create backlogs that are hard to drain after recovery.

## 13. Timeouts, Retries, and Retry Amplification

Timeouts bound waiting time; retries reattempt failed operations. Combining them poorly can spike load right when downstream is already overloaded.

For example, a request traversing three tiers where each tier independently retries three times can multiply call volume manyfold downstream. In practice, define an overall retry budget rather than only per-service max retries.

Principles:
- End-to-end deadlines are propagated down the service chain.
- Per-dependency timeouts are smaller than the remaining deadline.
- Exponential backoff and jitter.
- Retry only transient errors and safe/idempotent operations.
- Use idempotency keys for operations that produce side effects.
- Cap total retry attempts and retry rates.
- Do not retry simultaneously at every layer.
- Cancel work when the client cancels, if possible.
- Use circuit breakers and load shedding when dependencies lose capacity.

Retries do not make an unhealthy dependency healthier. Retries can bridge brief glitches, but during sustained degradation they increase queues and contention.

## 14. Connection Pools and Concurrency

Connection pools limit the number of connections to a database or downstream service. A pool that is too small causes pool wait; a pool that is too large can overload the database.

A service with 20 replicas, each configured with a max pool of 80 connections, can open up to 1,600 connections. When autoscaling raises replicas to 50, the theoretical maximum becomes 4,000, even though DB capacity did not increase.

Calculate the fleet-wide total:

```text
Maximum potential connections =
  replicas × pool size per replica
  + background workers
  + admin / migration reserve
```

You should:
- Cap pool size according to the DB budget.
- Configure connection timeouts and acquisition timeouts.
- Measure active, idle, pending waiters, and wait duration.
- Separate pools for critical vs. batch workloads if needed.
- Use proxies/pooling modes aligned with transaction semantics.
- Cap replica/autoscaling maximums based on downstream budgets.

## 15. Concurrency Control for Workers and Jobs

Worker count should not be chosen solely from CPU cores. Jobs can be CPU-bound, I/O-bound, or downstream-constrained.

| Workload | Characteristics | Sizing direction |
| --- | --- | --- |
| CPU-bound | Occupies CPU for most of service time | Benchmark against cores and CPU saturation |
| I/O-bound | Spends significant time waiting on network/storage | Higher concurrency may fit, but bound connections |
| Database-heavy | Many queries or locks | Size to DB capacity and query cost |
| External API | Constrained by external quotas/latency | Size to provider rate limits and deadlines |
| Long-running batch | Long service time, high memory use | Dedicated queue, bounded concurrency, and checkpoints |

If raising worker count fails to increase throughput while CPU, DB wait, or queue age climbs, the system has hit a dependency bottleneck or contention limit. Lowering concurrency can sometimes increase useful throughput by reducing contention.

## 16. Fan-out and Multiplicative Load

An API request may invoke multiple dependencies in parallel or in sequence. Fan-out makes the downstream operation rate higher than the ingress rate.

For example, each search request calls 4 services, and each service queries a shared catalog 3 times:

```text
Downstream calls per inbound request = 4 × 3 = 12

At 500 inbound requests/s:
  downstream call rate = 500 × 12 = 6,000 calls/s
```

Map out the call graph and cost per request. Caching, batching, query consolidation, and bounded fan-out can reduce load. Parallel fan-out lowers latency in some cases, but increases concurrency and instantaneous load across all dependencies.

## 17. Autoscaling on the Right Signals

CPU utilization does not reflect every queueing bottleneck. A service waiting on a database can have low CPU while latency and in-flight requests soar.

Appropriate signals depend on the workload:
- CPU/memory for compute saturation.
- Request concurrency/in-flight counts for APIs.
- Queue depth and oldest message age for workers.
- Completion rate and processing lag for streams.
- Connection pool wait for DB-bound services.
- Custom work units when request costs are heterogeneous.

### 17.1. Scale-out and Scale-in

Autoscaling needs:
- Thresholds and targets grounded in load tests.
- Cooldown/stabilization windows to prevent flapping.
- Maximum replicas aligned with downstream budgets.
- Minimum capacity to preserve baseline readiness.
- Scale-in protection for workers processing stateful tasks.
- Warm-up/readiness checks before receiving traffic.
- Quota, IP/subnet, and placement capacity checks.
- Safeguards against unbounded scale-out when a dependency is already overloaded.

Scaling compute without scaling or protecting the database can turn a minor bottleneck into a major incident.

## 18. Useful Throughput and Workload Mix

Not all completed requests carry equal value. Some requests may be duplicate retries, health checks, background polling, or operations that timed out before the client received the result.

Distinguish between:
- Offered load: volume of work sent by generators/clients.
- Accepted load: volume admitted by the system.
- Completed throughput: volume of work finished.
- Successful throughput: volume of operations finished according to contract.
- Useful throughput: completed work that produces valid business outcomes, excluding duplicates/failed work as defined.

In a booking platform, 1,000 requests/s where 30% are duplicate retries or 409 contention errors is not equivalent to 1,000 valid bookings/s.

### 18.1. Capacity by Cost Units

Request types can be converted into weighted units:

```text
Work units/s = Σ (rate_i × cost_weight_i)

Search: 400 req/s × 1 = 400 units/s
Booking: 80 req/s × 5 = 400 units/s
Export: 5 req/s × 20 = 100 units/s
Total = 900 units/s
```

Cost weights must be calibrated from measured CPU, DB queries, network, and service time. Do not rely on subjective weights long-term without benchmarking.

## 19. Saturation and Overload Behavior

Saturation occurs when a resource reaches its limit so additional demand no longer yields proportional throughput increases, while latency and errors rise.

Symptoms:
- High CPU run queues or throttling.
- Memory pressure, GC pauses, OOMs.
- DB connection waits, lock waits, IOPS saturation.
- Continuously rising queue age.
- Network retransmits/drops or bandwidth ceiling.
- Full thread pools or task queues.
- Increasing rate limits / 429 / 503 responses.
- Simultaneous increases in retries and timeouts.

Define an overload mode:
1. Preserve critical operations.
2. Reject over-budget requests early.
3. Throttle or pause background workloads.
4. Prevent retry storms.
5. Keep the system recoverable once load subsides.
6. Recover gradually instead of releasing the entire backlog at once.

## 20. Performance Measurement and Dashboards

| Group | Metrics to track |
| --- | --- |
| Load | Offered/accepted/completed/successful requests/s |
| Concurrency | In-flight requests, active workers, pool waiters |
| Latency | p50/p90/p95/p99 end-to-end and service time |
| Queue | Depth, oldest age, enqueue/dequeue rates, drain estimate |
| Resource | CPU, memory, GC, IOPS, bandwidth, connections |
| Dependency | Latency/errors/rate limits per downstream |
| Overload | 429/503, timeouts, retries, dropped/rejected work |
| Autoscaling | Detection, provisioning, readiness time, replica count |
| Business | Successful bookings/payments, duplicates, abandoned requests |

### 20.1. Dashboards Must Preserve Measurement Boundaries

Name metrics explicitly: API latency at the gateway vs. service; queue wait before worker vs. total job age; throughput as accepted requests vs. committed transactions. Use traces to correlate end-to-end duration with component spans.

Never rely solely on averages when tail latency governs user experience. Histogram buckets must align with SLO thresholds.

## 21. Performance and Queueing Testing

Test types:

- **Load test:** expected normal load and design peak.
- **Stress test:** ramp until saturation/overload.
- **Spike test:** sudden surges to verify burst handling.
- **Soak test:** sustained duration to uncover leaks, backlogs, and gradual degradation.
- **Capacity test:** find maximum throughput that still satisfies SLOs.
- **Queue recovery test:** induce a backlog and measure drain time.
- **Dependency degradation test:** slow down or rate-limit DB/APIs.
- **Concurrency test:** vary in-flight limits, worker counts, and connection pools.
- **Failover test:** lose a replica or zone while under peak load.

### 21.1. Closed-Loop vs. Open-Loop Load

A closed-loop generator waits for a response before sending the next request; it fits simulating concurrent users, but the offered rate drops when the system slows down.

An open-loop generator dispatches requests on a schedule independent of responses; it fits testing arrival rates and queue growth, though the generator itself must be bounded and dropped sends must be measured.

Use both when answering different questions. Record offered load, accepted load, and completed throughput to detect whether clients or generators are unintentionally self-throttling.

### 21.2. Reliable Test Conditions

- Representative dataset and cache state.
- Production-like request mix.
- Real dependencies or mocks with equivalent latency/limits.
- Clear warm-up and steady-state windows.
- Load generator is never the bottleneck.
- Measure p95/p99 and business success.
- Record config, build, dataset, seed, and workload profile for reproducibility.
- Define safe stop criteria.
- Repeat tests and compare under identical conditions.

## 22. Bottleneck Analysis Workflow

1. Identify the user journey and violated SLO.
2. Compare offered load, accepted load, and completed throughput.
3. Examine how concurrency and queue depth/age change.
4. Decompose end-to-end latency into gateway, service, queue, and downstream waits.
5. Check utilization/saturation per resource.
6. Inspect service time distribution, p95/p99, and lock contention.
7. Identify whether the bottleneck is compute, DB, network, provider quota, or scheduler.
8. Test controlled changes: worker count, pool size, batching, caching, or queries.
9. Measure useful throughput, latency, and errors together.
10. Select a solution that sustains SLOs under design peak and overload.
11. Add alerts/limits/runbooks so the issue does not silently recur.

Do not conclude "we need more CPU" solely from high CPU; nor conclude "we need more workers" solely because a queue is deep. Pinpoint the resource or stage that actually constrains service capacity.

## 23. Practical Scenario: Rapidly Growing Booking Queue

**Context:** A booking platform receives 600 jobs/s into a queue during a campaign. Each worker processes an average of 80 jobs/s, and there are currently 5 workers. Initial queue depth starts at 12,000 jobs. The system must keep queue age under 2 minutes for booking jobs. Export jobs share the same worker pool and consume on average 4x the resources of a booking job.

### 23.1. Calculating Capacity and Backlog

Assuming 80 jobs/s is the per-worker rate for the current workload mix:

```text
Total service capacity = 5 × 80 = 400 jobs/s
Backlog growth = 600 - 400 = 200 jobs/s
```

The queue is growing, so adding workers or reducing arrival/admission load is required. Simply extending queue retention does not resolve the instability.

### 23.2. Calculating Drain Time When Load Drops

Suppose the campaign ends and the arrival rate drops to 100 jobs/s while worker capacity remains 400 jobs/s:

```text
Net drain rate = 400 - 100 = 300 jobs/s
Drain time for 12,000 jobs = 12,000 / 300 = 40 seconds
```

If the backlog grew by 200 jobs/s over a 5-minute campaign, an extra 60,000 jobs accumulated. After the campaign ends:

```text
Total backlog = 12,000 + 60,000 = 72,000 jobs
Drain time = 72,000 / 300 = 240 seconds = 4 minutes
```

Queue age can exceed the 2-minute deadline even though the queue eventually drains. Monitor oldest age and separate booking from export jobs.

### 23.3. Remediation Design

- Separate queues/worker pools for booking and export jobs.
- Enforce concurrency limits and weighted fair scheduling.
- Throttle or defer export jobs during campaigns.
- Scale booking consumers based on queue age and completion rate.
- Ensure new workers do not exceed the database connection budget.
- Use idempotency so retries do not create duplicate bookings.
- Rate-limit producers or return accepted/pending status when queues near capacity.
- Measure queue age, drain estimates, and successful booking throughput.

## 24. Sample ADR: Bounding Concurrency and Protecting Queues

```text
ADR-164: Admission control and dedicated worker pool for bookings

Context:
- Campaigns cause arrival rates to spike rapidly.
- Booking and export jobs share the same worker pool.
- Exports have high cost, pushing booking queue age past its SLO.
- Scaling workers without bounds risks overloading the database.

Options:
A. Increase queue retention and let workers catch up gradually.
B. Increase worker count for all jobs.
C. Separate priority/workload pools, bound concurrency, and enforce admission control.

Decision:
- Choose C.
- Bookings get a dedicated worker pool and concurrency budget.
- Exports are throttled and can be deferred during peak periods.
- Queues are bounded; producers receive backpressure when exceeding budgets.
- Autoscaling triggers on queue age, completion rate, and dependency capacity.
- DB connection budgets are enforced across the entire fleet.

Trade-offs:
- Higher scheduling and operational complexity.
- Exports may wait longer during campaigns.
- Requires workload classification and fairness policies.

Verification:
- Peak load tests keep booking queue age within SLO.
- Exports cannot exhaust shared workers or DB connections.
- Retries do not produce duplicate bookings.
- Post-burst drain time meets the recovery objective.
- Overload returns errors or accepted states per API contract.

Review triggers:
- Traffic mix or job cost changes.
- Queue age/throughput SLOs change.
- Database or provider capacity changes.
```

## 25. Common Mistakes

1. **Equating throughput with latency:** processing many requests/s does not mean each request is fast.
2. **Equating concurrency with thread count:** async runtimes and I/O waits alter the relationship.
3. **Using average latency alone:** hides p99 and the slowest requests.
4. **Treating queues as capacity:** unbounded backlogs only defer overload.
5. **Not measuring queue age:** depth can be large yet drain fast, or small yet wait a long time.
6. **Scaling workers without bounds:** overloads databases, networks, or providers.
7. **Scaling connection pools per replica without fleet caps:** total connections exceed DB budgets.
8. **Autoscaling solely on CPU:** ignores queue wait and downstream saturation.
9. **Retrying at every tier:** causes retry amplification and storms.
10. **Leaving queues unbounded:** memory/disk exhausts before clear backpressure appears.
11. **Failing to isolate workloads of different costs:** batch/export jobs create noisy-neighbor impacts.
12. **Applying Little's Law outside steady state without caution:** leads to misinterpretation.
13. **Adding per-service percentiles:** does not yield accurate end-to-end percentiles.
14. **Using closed-loop tests for every goal:** load self-throttles when the system slows down.
15. **Ignoring coordinated omission:** tail latency is underestimated.
16. **Measuring only accepted requests:** misses dropped, rejected, or unsuccessful operations.
17. **Ignoring fan-out:** one inbound request can generate many downstream calls.
18. **Not testing backlog recovery:** queues keep growing after an incident ends.

## 26. Pre-Production Checklist

- [ ] Throughput, arrival rate, and successful throughput have consistent definitions.
- [ ] Concurrency distinguishes in-flight, active execution, waiting, and connections.
- [ ] Latency is measured end-to-end and across key stages.
- [ ] p50/p95/p99 metrics and appropriate SLO thresholds are in place.
- [ ] Little's Law is applied with consistent steady-state boundaries and units.
- [ ] Queue depth, oldest age, enqueue/dequeue rates, and drain estimates are monitored.
- [ ] Worker/service capacity is benchmarked with a realistic workload mix.
- [ ] Utilization ceilings and headroom are defined per resource.
- [ ] Queues are bounded and have retention/dead-letter policies.
- [ ] Admission control, backpressure, and load shedding have explicit contracts.
- [ ] Timeouts, retry budgets, backoff/jitter, and idempotency are designed.
- [ ] Connection pools are sized across the full fleet and autoscaling maximums.
- [ ] Fan-out and downstream cost per request are measured.
- [ ] Autoscaling uses appropriate signals and respects dependency budgets.
- [ ] Overload/degraded modes prioritize critical operations.
- [ ] Dashboards separate offered/accepted/completed/successful workloads.
- [ ] Load tests include open-loop/closed-loop, peak, spike, soak, and stress scenarios as needed.
- [ ] Tests verify tail latency, coordinated omission, and queue recovery.
- [ ] Owners and runbooks exist for saturation, backlogs, and dependency throttling.

---

**Key Takeaway:** Throughput tells you completion speed, concurrency tells you how much work is present, latency tells you how long completion takes, and queues expose work waiting for capacity. Little's Law links the three averages; utilization near saturation causes wait times to rise sharply. Performance design must bound queues, measure tail latency, control concurrency/retries, and test under representative workloads to sustain SLOs as load fluctuates.
