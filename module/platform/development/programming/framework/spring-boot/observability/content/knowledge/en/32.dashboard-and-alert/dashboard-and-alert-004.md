# Saturation Dashboard

A Spring Boot service has an average CPU of 55% and a stable request rate, yet its p99 latency climbs rapidly. The cause may be a nearly exhausted connection pool, a growing executor queue, or threads waiting on locks. Looking at CPU alone does not reveal how much capacity the service has left to absorb more traffic. A saturation dashboard lets you observe resource utilization, queued work, and errors raised when the system approaches its limits.

The lesson **Saturation Dashboard** belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understand context propagation, tags/cardinality, exporters, sampling, and correlate signals to investigate errors, latency, and application behavior in production environments.

> **Principle:** A saturation dashboard must answer three questions: which resources are being used, what work is waiting, and has the system started rejecting or slowing down requests? Apply the USE model (Utilization, Saturation, Errors) to each resource; combine with application-layer latency/throughput to see user impact. Do not use a single CPU threshold as a proxy for every form of saturation.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain saturation and distinguish it from utilization.
2. Apply the USE method to resources in Spring Boot.
3. Choose metrics for CPU, memory, threads, executors, connection pools, and queues.
4. Interpret backlog, pending tasks, pool wait, and resource exhaustion.
5. Design a dashboard combining saturation with request rate, errors, and latency.
6. Distinguish capacity shortages from slow downstream dependencies.
7. Select appropriate aggregations, time windows, and thresholds.
8. Avoid misleading dashboards where averages hide spikes or high cardinality causes issues.
9. Design alerts based on symptoms and saturation signals.
10. Build an investigation playbook and validate the dashboard using load tests.

## 2. What Is Saturation?

Saturation describes the degree to which a resource or subsystem is overloaded relative to its capacity to serve current work. Utilization tells you how busy a resource is; saturation tells you how much work is forced to wait or gets rejected because the resource cannot keep up.

For example:
- 95% CPU utilization shows the CPU is almost always busy; a high run queue shows runnable threads are still waiting for CPU.
- Connection pool active reaching max with rising pending indicates requests must wait for a connection.
- Growing executor queue indicates tasks arrive faster than workers can process them.
- High heap occupancy does not necessarily mean saturation yet; allocation pressure, GC pauses, and approaching the memory limit can cause latency or OOM.

### 2.1 USE method

USE is a checklist for inspecting each resource:

| Component | Question | Example |
|---|---|---|
| Utilization | What percentage/time is the resource busy? | CPU usage, pool active/max |
| Saturation | How much work is waiting or queued? | CPU run queue, executor queue, pool pending |
| Errors | Are errors occurring because the resource cannot keep up? | Rejected tasks, acquisition timeout, OOM |

Not every resource has all three metrics. If no queue metric exists, find an appropriate proxy or add instrumentation. Do not infer saturation from utilization alone.

~~~mermaid
flowchart TD
    A["Resource"] --> B["Utilization"]
    A --> C["Saturation"]
    A --> D["Errors"]
    B --> E["Is the resource busy?"]
    C --> F["Is work waiting?"]
    D --> G["Are tasks rejected/failing?"]
    E --> H["Correlate with latency and throughput"]
    F --> H
    G --> H
~~~

## 3. Saturation at the Application Layer

A dashboard should start with service impact before drilling into resources:
- Request rate: is traffic increasing or decreasing?
- Error rate: are requests failing or timing out?
- Latency: how are p50/p95/p99 changing?
- In-flight requests: are many requests being processed concurrently?
- Queue wait: how long do requests/tasks wait before processing?
- Rejected requests/tasks: has the system hit its limit?

A service with high latency but low CPU may be waiting on a database, HTTP dependency, lock, or connection pool. A service with high CPU but low latency may still have enough capacity at the current load. Signals must be read together.

### 3.1 RED and USE complement each other

RED (Rate, Errors, Duration) describes service behavior from the request perspective. USE describes resource pressure.

| RED symptom | USE clue | Investigation direction |
|---|---|---|
| Request latency increases | Executor queue grows | Worker capacity or blocking tasks |
| Error rate increases | Pool pending and timeouts increase | Connection pool/DB dependency |
| Throughput drops | High CPU utilization, high run queue | CPU saturation |
| Latency increases, CPU low | High pool wait | DB/connection capacity |
| 5xx increases | Memory pressure/GC pauses | Heap, allocation, and GC |

## 4. Dashboard Overview: Recommended Panels

A practical saturation dashboard can be organized into rows:

| Row | Panels | Purpose |
|---|---|---|
| Service impact | Request rate, error ratio, p95/p99 latency | Determine whether users are impacted |
| CPU | CPU usage, process CPU, run queue/load | Spot CPU pressure |
| Memory/GC | Heap used/max, old-gen, GC pause/allocation | Spot memory pressure |
| Threads | Live/peak threads, blocked threads, thread states | Spot thread starvation/locks |
| Executors | Active/max workers, queue depth, rejected tasks | Spot task backlogs |
| Database pool | Active/idle/max/pending, acquire timeout/wait | Spot connection starvation |
| Messaging | Queue depth, oldest age, consumer lag, in-flight | Spot async backlogs |
| Dependency | HTTP client latency/errors, DB latency/errors | Distinguish local vs. downstream pressure |

Do not cram every metric onto a single screen. Keep the overview concise, then create detailed dashboards per resource or dependency.

## 5. CPU Saturation

Commonly useful metrics:
- Process CPU usage.
- System CPU usage.
- CPU cores/available processors.
- Load average or runnable queue if exposed by the host/platform.
- Request throughput and latency to observe impact.

Process CPU usage reflects the CPU consumed by the JVM process; system CPU usage reflects the host. Container CPU limits may be lower than the host's core count, so inspect quota/throttling metrics from the container runtime or platform.

### 5.1 CPU utilization is not the whole story of saturation

Sustained high CPU usage can indicate capacity pressure, but the run queue or throttling tells you whether work is actually delayed due to CPU. In containers, CPU throttling can occur even when the host has idle CPU because of the container's quota.

Panels should:
- Compare process CPU against the CPU limit/quota.
- Track throttled time/periods if provided by the platform.
- Compare p95/p99 latency and request rate.
- Display a long enough trend to recognize sustained pressure.

Do not alert solely on a brief CPU spike. Use a time window and corresponding symptoms.

## 6. Memory and Garbage Collection Pressure

Memory panels should separate:
- Heap used vs. heap max.
- Old generation/tenured usage if exposed by the JVM.
- Non-heap/metaspace.
- Allocation rate.
- GC count and pause duration.
- Container memory working set/limit.
- OOM/restart events from the platform.

High heap used does not automatically mean an impending OOM; the garbage collector can reclaim memory. Observe post-GC trends, allocation rate, pause times, and headroom to the container memory limit.

~~~mermaid
flowchart LR
    A["Allocation rate increases"] --> B["GC frequency/pauses increase"]
    B --> C["CPU spent on GC increases"]
    C --> D["Request latency increases"]
    A --> E["Heap/container memory pressure"]
    E --> F["OOM or restart risk"]
~~~

If a container is OOM-killed, the JVM may not have a chance to log an OutOfMemoryError. Combine process metrics with platform/container events.

## 7. Thread and Executor Saturation

Spring Boot services have several types of threads: servlet request threads, async executors, scheduler threads, messaging consumers, and framework worker pools.

Metrics to observe:
- Active threads and maximum/peak threads.
- Thread states: runnable, blocked, waiting.
- Executor active workers.
- Executor pool size/max size.
- Queue depth/remaining capacity.
- Rejected task count.
- Task queue wait and execution duration.

If active workers hit max, the queue grows continuously, and task wait p99 rises, the executor is saturated. If blocked threads rise, there may be lock contention or threads waiting on a synchronized section.

Do not just increase max pool size. With blocking tasks, more threads can increase memory usage, context switching, and pressure on downstream dependencies.

## 8. Database Connection Pool Saturation

For HikariCP or other pools, dashboards should include:
- Active connections.
- Idle connections.
- Maximum connections.
- Pending/waiting threads.
- Connection acquisition duration.
- Connection timeout count.
- Connection usage duration if available.

A high active/max ratio at a single point in time is not enough to conclude saturation. Stronger signals are active staying near max, rising pending threads, rising acquisition wait, and timeouts appearing.

Conceptual PromQL examples:

~~~promql
max by (service) (hikaricp_connections_active)
/
clamp_min(max by (service) (hikaricp_connections_max), 1)
~~~

~~~promql
max by (service) (hikaricp_connections_pending)
~~~

Exact metric names depend on the Micrometer binder, registry naming convention, and version. Check `/actuator/metrics` or scrape output before using queries.

If active is near max and query duration is also rising, the DB or transactions may be holding connections too long. If pending rises while DB query latency is normal, check pool sizing, connection leaks, and transaction boundaries.

## 9. Messaging and Task Queue Saturation

For Kafka, RabbitMQ, or task executors, queue depth alone is insufficient. Monitor:
- Queue depth/backlog.
- Oldest message age.
- Consumer lag (Kafka offset lag).
- Arrival rate and completion throughput.
- Consumer concurrency/active workers.
- In-flight/unacked messages.
- Retry/dead-letter rate.
- Queue wait time and processing duration.

Kafka offset lag is a count of records/offset distance, not wait time directly. Combine lag with throughput and record age. RabbitMQ ready/unacked counts reflect different queue states; understand broker semantics before setting thresholds.

A queue with large depth but low oldest age and fast draining throughput may just be a normal burst. Queue depth and age rising continuously together is a backlog signal worth attention.

## 10. Downstream Saturation and Dependency Pressure

A service can appear saturated due to a slow dependency:
- HTTP client connection pool exhaustion.
- Increased remote API latency.
- Slow database locks/queries.
- DNS/TLS/connect timeouts.
- Rate limits or 429/503 responses from dependencies.

Dependency panels should display client request rate, error rate, latency percentiles, timeout/retry counts, and pool wait. Traces help determine whether requests spend time in local queues, client pools, or downstream servers.

Do not attribute every latency increase to CPU or thread pools. A request thread waiting on I/O can push active thread count high while process CPU stays low.

## 11. Choosing Aggregations and Time Windows

Saturation dashboards need multiple aggregation types:

| Aggregation | When to Use | Notes |
|---|---|---|
| Rate | Counters like errors/rejections | Use rate instead of absolute count when traffic changes |
| Ratio | Active/max, errors/requests | Ensure denominator is non-zero |
| Average | General trend | Can hide outliers |
| p95/p99 | Latency and wait time | Requires appropriate histogram/buckets |
| Max | Spikes or peak gauges | Can be sensitive to a single data point |
| Sum | Total backlog/rejections across fleet | Avoid summing gauges with incompatible semantics |
| Per-instance | Spot an outlier pod/node | Keep dimension bounded |

Use short windows to detect spikes and longer windows to confirm sustained saturation. Alerts usually need a `for` duration to prevent flapping; dashboards can show both raw series and smoothed trends.

Do not average per-instance percentiles to derive a fleet-wide percentile. Use aggregatable histogram buckets or a query backend supporting distribution aggregation.

## 12. Thresholds and Alert Design

Thresholds must be based on baseline, capacity, and SLOs. Starting examples for experimentation, not defaults for every system:

| Signal | Reference Alert Condition | Confirm With |
|---|---|---|
| CPU pressure | CPU near quota for several minutes | Throttling, run queue, latency |
| Heap/container memory | Memory approaching limit and rising continuously | GC pauses, OOM/restarts |
| Executor saturation | Queue growing and active workers at max | Task wait, rejections |
| DB pool saturation | High active/max alongside rising pending/wait | Acquire timeouts, DB latency |
| Messaging backlog | Oldest age exceeds processing SLO | Arrival/completion rate, consumer lag |
| Rejected work | Rejection rate elevated above baseline | Thread/queue capacity and request errors |

Alerts should combine resource signals with user impact:
- Warning when resource pressure is prolonged.
- Critical when pressure coincides with latency/error SLO breaches or rejected work.
- Include inhibition/deduplication to avoid multiple alerts for the same root cause.

Do not fire critical alerts solely for high utilization if the service still meets its SLOs and has capacity headroom.

## 13. Cardinality and Dashboard Performance

Dashboards can become slow or backends expensive if grouped by unbounded dimensions:
- user/customer/order ID.
- raw URL or query string.
- exception message.
- message ID or trace ID.
- dynamic tenant identifiers.
- unbounded SQL statements.

Prefer service, environment, coarse region, operation, route template, outcome, and bounded `error.type`. Use dashboard drill-downs to traces/logs to investigate a specific request; do not create a separate metric series per request.

Per-instance panels can be helpful but require limiting series count and retention. For large fleets, use top-k or filter by service/cluster before drilling down.

## 14. Designing User-Friendly Dashboards

A good dashboard should:
1. Have service/environment selectors with bounded values.
2. Place request rate, error ratio, and p95/p99 in the top row.
3. Place resource utilization next to corresponding saturation/backlog metrics.
4. Display capacity limits alongside usage (active/max, used/limit).
5. Use the same time range and timezone across related panels.
6. Clearly state units, aggregations, and metric definitions.
7. Include links to traces/logs/runbooks for drill-down.
8. Use annotations for deployments/config changes.
9. Avoid excessive panels and unreadable legends.
10. Include a missing/no-data panel to distinguish zero from absent telemetry.

Name panels after operational questions, such as "DB connections waiting" instead of just "Gauge 4". Clarify that queue depth is an instantaneous gauge, error rate is a rate, and latency is a histogram quantile.

## 15. Validating Dashboards with Load Tests

Use a staging or performance environment to create repeatable scenarios:
- Increase CPU-bound workload.
- Reduce executor worker count and build a task backlog.
- Constrain the connection pool or hold connections in a controlled manner.
- Slow down a database query in the test environment.
- Increase message arrival rate beyond consumer throughput.
- Induce downstream HTTP latency/429/503 responses.
- Create safe levels of memory allocation pressure.

For each scenario, verify:
1. Utilization panels reflect busy resources.
2. Saturation panels reflect queue/pending/wait.
3. Error panels reflect rejections/timeouts.
4. RED panels reflect user impact.
5. Alerts trigger within the expected time window.
6. Runbooks point to the right resource group to investigate.

Do not generate uncontrolled overload in production. Use load limits, stop conditions, and a rollback plan in the test environment.

## 16. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Low CPU but high latency | I/O wait, pool wait, locks, or slow downstream | Check queue/pool waits and distributed traces |
| High CPU but low queue | CPU-bound work still within capacity | Monitor latency/SLO and run queue |
| High active threads, low CPU | Threads blocked/waiting on I/O/locks | Inspect thread states and traces |
| Executor active=max, queue growing | Insufficient worker capacity or slow tasks | Inspect processing duration, blocking, and downstream |
| DB active=max, pending rising | Pool saturation or long-held connections | Check acquisition wait, usage duration, and DB spans |
| High heap but effective GC | Heap occupancy after allocation spike | Check post-GC trend, allocation, and pauses |
| Container OOM despite JVM heap below max | Native memory/sidecar/direct buffers/container limit | Compare process RSS, container working set, and heap |
| Kafka lag rising but low age | High topic throughput | Check records/sec and record timestamps |
| High queue depth with no impact | Burst being drained quickly | Check oldest age and completion throughput |
| Rejections rising but low CPU | Pool/queue limit or overly small bulkhead | Inspect resource-specific capacity and dependencies |
| Fleet average normal but one pod slow | Single-instance hotspot | Drill down per-instance and check deployment placement |
| Dashboard has no data | Missing meter/binder or scrape/filter error | Check registry, endpoint, and exporter pipeline |

## 17. Playbook: p99 Increases Despite Moderate CPU

**Scenario:** Order Service p99 triples while process CPU stays below 60%.

1. Confirm request rate, error ratio, and p95/p99 by route.
2. Check servlet/request threads and blocked/waiting states.
3. Inspect executor active/max, queue depth, task queue wait, and rejected count.
4. Check HikariCP active/idle/max/pending and acquisition duration.
5. Check HTTP client pool wait, downstream latency, timeouts, and retries.
6. Open slow traces to identify whether time is spent in local queues, DB, remote HTTP, or locks.
7. Check messaging backlog/oldest age if requests await async results.
8. Compare per-instance to locate an anomalous pod/node.
9. Make a controlled change at the identified bottleneck; do not enlarge every pool at once.
10. Verify p99, queue wait, pending, and rejections return to baseline after the change.

Low CPU does not rule out saturation. Threads and connections can be held while waiting on I/O, driving up latency without keeping CPU busy.

## 18. Self-Check Exercises

**Exercise 1 — USE.** Distinguish utilization and saturation for a connection pool. Which metric shows busy connections and which shows waiting requests?

**Exercise 2 — CPU.** CPU utilization is 90%, but the run queue is low and latency is stable. Is there enough evidence for a critical alert? Why or why not?

**Exercise 3 — Executor.** Active workers equal max, the queue grows steadily, and rejected tasks appear. Which additional metrics would you inspect to determine the cause?

**Exercise 4 — Database pool.** Active connections are near max, but pending is 0. Is this definitely saturation? What additional signals are needed?

**Exercise 5 — Messaging.** Why can't a Kafka lag of 10,000 records be directly interpreted as 10,000 seconds of queue wait?

**Exercise 6 — Memory.** Heap used is high, but post-GC usage is stable. Why shouldn't you conclude OOM risk based solely on heap percentage?

**Exercise 7 — Aggregation.** Why shouldn't you average the p99 of each pod to calculate fleet-wide p99?

**Exercise 8 — Diagnosis.** p99 increases, CPU is low, DB pool pending rises, and DB span duration is high. Propose an investigation order.

### Suggested Answers

1. Utilization is active/max; saturation is pending/waiting work or acquisition wait.
2. Not yet. Check CPU quota/throttling, run queue, latency, and SLO over a sufficiently long window.
3. Task queue wait, processing duration, bounded task type, blocked threads, and downstream latency.
4. Not necessarily; the pool may be nearly full without requests waiting yet. Check pending, acquisition latency, and timeouts.
5. Lag is offset distance; wait time depends on arrival/consume throughput and record timestamps.
6. GC may be reclaiming most allocations; inspect post-GC trend, allocation rate, pauses, and container limits.
7. Percentiles are not linearly additive; aggregate histogram buckets/raw observations in the backend.
8. Inspect queries/locks and DB capacity, connection usage duration, transaction boundaries, then cross-check pool sizing and traffic concurrency.

## 19. Official References

- [USE Method](https://www.brendangregg.com/usemethod.html): utilization, saturation, and errors for every resource.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer binders, JVM, datasource, and application metrics.
- [Spring Boot — Actuator Metrics Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.metrics): exploring meters and measurements.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): duration, histograms, and percentiles.
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): gauge semantics and lifecycle.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): active/idle/pending connections and pool behavior.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag and broker/consumer metrics.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, ready/unacked, and consumer metrics.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): histogram aggregation and quantile caveats.
- [Kubernetes — Resource Metrics](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests, limits, and container resource behavior.

**Key Takeaways:** Saturation is work waiting or being rejected when a resource cannot keep up with load. Apply USE to CPU, memory, threads, executors, connection pools, and queues; combine with RED to see request impact. Always inspect usage alongside pending/backlog, errors, and latency. Use baseline/SLO-based thresholds, drill down by instance and dependency, and confirm with traces. Do not increase pools or concurrency across the board before identifying where the resource bottleneck lies.
