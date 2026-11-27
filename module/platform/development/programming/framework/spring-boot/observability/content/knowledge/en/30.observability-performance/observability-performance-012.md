# Load Testing with Instrumentation Enabled in Spring Boot

**Load testing with instrumentation enabled** is a controlled load test designed to measure the performance impact of metrics, distributed tracing, and logging on an application. The goal is to quantify instrumentation overhead, identify throughput/latency limits, observe CPU/heap/network consumption, and verify telemetry export behavior as load increases. The results help choose a configuration that provides sufficient incident investigation capability while meeting service SLOs.

In the **SPRING_BOOT_OBSERVABILITY** module, this lesson connects Micrometer Observation with performance testing methodology. The content belongs to the **Observability Performance** chapter, focusing on baselines and instrumentation variants, workload design, open/closed load models, measurements at the application/Collector/backend layers, statistical analysis, failure injection, acceptance criteria, and a repeatable benchmarking process.

## 1. Why Load Test Instrumentation?

Instrumentation adds work to both the request path and the telemetry pipeline:
- Creating Observations, Spans, events, and key-value metadata.
- Reading/writing context and injecting/extracting trace headers.
- Updating meters and histogram buckets.
- Serializing, batching, compressing, and exporting telemetry.
- Writing logs, formatting structured fields, and shipping to a log collector.
- Maintaining queues/buffers when the exporter or backend slows down.

A small per-request cost can become significant at high request rates. Conversely, disabling instrumentation to maximize throughput can strip away signals needed during incident investigation. Load testing measures this trade-off on realistic workloads.

### 1.1. Questions to Answer

1. How much does instrumentation increase p95/p99 latency?
2. How does maximum throughput change before and after enabling telemetry?
3. How do CPU, allocation rate, heap, and GC change?
4. Does the exporter keep up with span/log creation rates?
5. Do queues grow continuously or drop telemetry under peak load?
6. Does the Collector/backend become a bottleneck?
7. Do sampling and cardinality stay within budget as traffic changes?
8. Do business requests continue operating when the telemetry backend is slow or unavailable?

## 2. Establishing a Baseline and Test Variants

A baseline is a measurement using the exact same application and workload with instrumentation reduced to the minimum needed as a reference point. Do not alter business logic, JVM options, database datasets, or infrastructure between baseline and instrumented runs.

A test matrix might include:

| Run | Configuration | Purpose |
| --- | --- | --- |
| A | Minimal instrumentation, standard log level | Baseline |
| B | Metrics enabled, trace export off | Measure metrics overhead |
| C | Metrics + tracing, 100% sampling in lab | Measure upper-bound trace volume |
| D | Metrics + tracing with target sampling | Evaluate production-like policy |
| E | Metrics + tracing + structured logs | Measure combined signal cost |
| F | Instrumented, Collector slow or unavailable | Verify queue/backpressure/failure behavior |

100% sampling should only be used in lab environments under controlled load; it reveals maximum volume, yet can overload a backend. Never use those numbers as a production recommendation.

### 2.1. Keep Test Variables Independent

Change one configuration group per run. Changing sampling, batch size, compression, and log level at the same time makes it impossible to attribute differences to any single factor.

Keep fixed:
- Application build and dependency versions.
- JVM version, heap settings, and container limits.
- CPU/memory quotas and node types.
- Dataset, database state, and cache warmness.
- Load generator location/network.
- Request mix and payload distribution.
- Collector/backend capacity while measuring application overhead.

## 3. Designing a Representative Workload

The workload must reflect the real request mix, not just hit one trivial endpoint. A Spring Boot application may have varied execution paths:
- HTTP requests hitting cache only.
- HTTP requests querying the database.
- Requests writing data and publishing messages.
- Requests calling downstream HTTP services.
- Requests failing validation or business rules.
- Requests with large response payloads.
- Background jobs or scheduled tasks.

Each category produces different counts of spans, logs, and database calls. Record the share of each category so results remain explainable.

### 3.1. Arrival Rate and Concurrency

Two common load modeling approaches:

- **Open model:** issues requests at a defined arrival rate regardless of whether prior responses have completed. Suits systems receiving external traffic and helps expose queue buildup.
- **Closed model:** maintains a fixed number of virtual users/concurrent clients; each client sends its next request after the previous completes. Suits certain user-driven workloads, yet can mask saturation as latency climbs.

Pick the model matching actual traffic. Document arrival rate, concurrency, think time, and request timeouts.

### 3.2. Avoiding Coordinated Omission

If a load generator only sends a new request after the previous one finishes, a latency spike causes the generator to slow down its send rate and under-report the wait times a real system would experience. Use an appropriate load model and histogram correction to avoid underestimating tail latency.

## 4. Warm-Up and Run Duration

The JVM needs warm-up for JIT compilation, class loading, connection pools, and caches to stabilize. Measuring immediately after startup rarely reflects steady state.

A test run should include:
1. Startup and readiness.
2. Low-load warm-up.
3. Ramp-up through selected steps.
4. A steady-state window long enough to collect reliable metrics.
5. A peak/burst phase if applicable.
6. Ramp-down and shutdown/flush.
7. Cool-down before the next run.

Exact durations depend on the application. Make steady state long enough to observe GC cycles, periodic exports, and backend ingestion lag.

## 5. Application-Layer Metrics

Never look only at average latency. Capture at minimum:

| Metric | Meaning |
| --- | --- |
| Throughput (requests/s) | Requests completed per second |
| p50 latency | Typical experience |
| p95 latency | Tail latency for slower requests |
| p99 latency | More severe tail latency |
| Error rate | Fraction of errored/timed-out requests |
| CPU utilization | Overall processing cost |
| Heap used/committed | Memory pressure |
| Allocation rate | Object allocation velocity |
| GC count/pauses | Garbage collection cost |
| Thread/event-loop saturation | Capacity for concurrent work |
| Connection pool wait | Dependency contention |

Break down by endpoint/request class using normalized dimensions. Never build metric tags from user IDs, raw URLs, or request-specific values.

### 5.1. Separating Application Latency from Dependency Latency

If a database or downstream service slows down, total request latency climbs even when instrumentation is not the cause. Combine server metrics with database/pool metrics, client spans, and downstream measurements to isolate application time from dependency time.

## 6. Measuring Metrics Overhead

Metrics typically incur overhead from meter lookups, tag evaluation, histogram recording, and export. With Micrometer, meter state is updated inside the application process; the registry/exporter scrapes or pushes according to configuration.

Check:
- Number of meter names and time series.
- Tag combinations/cardinality.
- Histogram bucket count.
- Scrape interval or push step.
- CPU/allocations when recording timers/counters.
- Export latency and registry contention, if any.

### 6.1. Histograms and Percentiles

Histogram buckets enable percentile aggregation on the backend, though each bucket adds series. Enable only buckets suited to your SLOs and target latency range.

Client-side percentiles can consume memory and do not aggregate across instances the way histogram buckets do. Choose the percentile type based on dashboard/alerting goals.

### 6.2. Cardinality Stress Test

In the lab, generate traffic with many route IDs or query parameters while ensuring route templates stay normalized. Verify series counts do not scale with ID counts. Check top tag values and series counts before/after enabling custom dimensions.

## 7. Measuring Tracing Overhead

Tracing can generate many spans per request: server, client, database, messaging, and custom operations. Cost depends on spans/request, attributes/span, events/span, sampling ratio, and exporter batch settings.

Record:
- Spans created/sec and spans exported/sec.
- Bytes exported/sec.
- Span attribute/event counts.
- Effective sampling ratio.
- Export success/failure/drop counts.
- Batch queue occupancy.
- Export latency.
- CPU/allocations from context propagation and serialization.

### 7.1. Sampling Matrix

Test target sampling ratios—for example, 0%, 1%, 10%, and 100% in the lab. Do not compare volume alone; verify trace continuity, error visibility, and retention of high-latency traces.

With parent-based sampling, confirm downstream services honor the sampled decision. With tail sampling, remember spans must reach the Collector before the Collector decides to keep a trace.

### 7.2. Span Density

A request producing 2 spans and another producing 30 spans do not share the same tracing cost. Track spans/request by route or operation category using low-cardinality dimensions. Look for duplicate instrumentation if span density spikes unexpectedly.

## 8. Measuring Logging Overhead

Logs can drive allocations/string formatting and I/O. Async logging reduces blocking on the caller path, yet typically uses a queue that may drop or block when full depending on implementation.

Test configurations:
- INFO baseline.
- DEBUG scoped to a controlled package.
- Structured logging with Trace ID/Span ID.
- Exception logs on error paths.
- Async appender and queue behavior, if used.

Measure log events/sec, bytes/sec, CPU, queue utilization, dropped events, and backend ingestion. Never enable application-wide DEBUG under production-like load without capping data and capacity.

### 8.1. Duplicate Logging

A single exception may get logged in the repository, service, controller advice, and global handler. Duplicate logs inflate cost and obscure the root event. Choose one boundary to own logging the event while other layers enrich context or propagate the exception.

## 9. Exporter, Collector, and Backend Metrics

When telemetry export is enabled, measure each hop separately:
- Application creates records.
- Exporter sends records.
- Collector receiver accepts records.
- Collector processors batch/filter/sample.
- Collector exporter forwards.
- Backend completes ingest/indexing.

Compare rates across tiers. If the app exports 10,000 spans while the backend ingests only 7,000, determine whether the remaining 3,000 records are queued, dropped, retried, or filtered.

### 9.1. Queues and Backpressure

Monitor queue occupancy over time, not just an end-of-run snapshot. Continuously rising queues mean downstream throughput is lower than the producer rate. When full, processors may drop records or apply other implementation-specific behavior.

Never let a synchronous exporter block request threads indefinitely. Configure bounded queues, timeouts, bounded retries, and a shutdown flush budget.

### 9.2. Collector Saturation

High Collector CPU/memory, receiver refused records, or growing export queues can indicate a bottleneck. Try scaling the Collector or adding controlled capacity, while keeping capacity constant across runs comparing application overhead.

## 10. Testing Behavior When the Telemetry Backend Is Slow

Instrumentation must tolerate telemetry pipeline failures according to policy. In the lab, simulate:
- Slow Collector responses.
- Temporary Collector unavailability.
- Network latency/packet loss.
- Backend ingest throttling.
- DNS/connectivity failures.
- Export timeouts.

Observe business request latency, queue growth, dropped telemetry, and recovery time. The business path must never block indefinitely due to a slow telemetry backend.

### 10.1. Failure Isolation

If tracing and metrics exporters use separate pipelines, one signal failing should not halt the other. Test each pipeline and custom handler. Avoid custom `ObservationHandler` implementations making synchronous network calls on request threads.

## 11. Designing Load Test Scripts and Data

Version-control load scripts alongside benchmark configurations. Document endpoints, payloads, headers, authentication setup, arrival rates, durations, ramp-up, and assertions.

Test data:
- Matches realistic payload size distributions.
- Yields realistic cache hit/miss ratios.
- Uses key distributions that avoid unintended single hot keys.
- Provides a large enough database dataset so tests do not measure cache only.
- Contains zero PII or production secrets.
- Has a reset/seed procedure so runs are repeatable.

Run the load generator on a separate machine or isolated node so generator CPU never contends with the application. Approximate the production network path if possible.

## 12. Analyzing Results and Reliability

A single run can be skewed by GC, noisy neighbors, network jitter, or backend compaction. Run multiple iterations, compare medians/percentiles across runs, and record environment details.

Analysis steps:
1. Verify the actual workload hit the target arrival rate.
2. Exclude startup/warm-up windows from steady-state analysis.
3. Compare throughput and latency distributions.
4. Compare CPU, heap, allocations, and GC.
5. Compare telemetry volume/queues/drops.
6. Check application error rate and dependency health.
7. Identify changes exceeding normal run-to-run noise.
8. Repeat runs when anomalies occur.

Do not blame instrumentation for latency simply because run B was slower than run A if database state or node contention also differed.

### 12.1. Relative Overhead

Compute relative overhead as:

```text
overhead_percent = ((instrumented - baseline) / baseline) * 100
```

Compute separately for p95 latency, CPU/request, or allocations/request. For throughput, interpret the sign inversely: lower throughput is degradation. Always state units and workload alongside calculations.

### 12.2. Confidence and Noise

Use multiple runs and distribution ranges instead of a single mean. If differences are smaller than run-to-run variance, there is insufficient evidence to attribute them to instrumentation. Record commit hash, image digest, JVM flags, node type, and telemetry backend configuration.

## 13. Acceptance Criteria Aligned with SLOs and Budgets

Define criteria before running tests rather than picking thresholds after seeing results. Example service-adjusted criteria:
- p95/p99 stays within SLOs.
- Error rate does not increase noticeably.
- Throughput meets target arrival rate.
- CPU/memory retain headroom for traffic bursts.
- GC pauses do not cause abnormal tail latency.
- Telemetry queues do not grow continuously.
- Export/drop rates remain within budget.
- Cardinality and storage growth stay within limits.
- Collector/backend do not saturate.
- When the telemetry backend fails, business requests keep operating per policy.

A setup with low CPU overhead that drops nearly all traces cannot pass if the objective is investigating distributed failures.

## 14. Troubleshooting Load Tests with Instrumentation Enabled

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| p95 jumps sharply when tracing is enabled | High span density/attributes/serialization | Compare spans/request and CPU profile |
| Throughput drops without CPU rising | Blocking export, network wait, or dependency | Inspect request threads and network |
| Heap/GC increases | Allocations, batch queues, or large payloads | Check allocation profile and queues |
| Metric series grow quickly | Dynamic tags/raw URIs | Inspect cardinality per meter |
| Export queue rises continuously | Low Collector/backend throughput | Compare rates across each pipeline hop |
| Dropped spans increase | Full queue, timeouts, or retry failures | Check processor/exporter diagnostics |
| Log volume spikes | DEBUG/duplicate exception logs | Inspect log levels and event duplication |
| p99 rises when Collector is slow | Sync handler/export or queue contention | Check thread dumps and export path |
| CPU climbs with compression enabled | High compression cost | Benchmark compressed vs. uncompressed |
| Low trace coverage | Overly strict sampling/filtering or export loss | Cross-check request counts and spans |
| Wide run-to-run variance | Noisy node, warm-up, or unstable workload | Re-run in a fixed environment |
| Load generator misses target | Generator bottleneck | Monitor generator CPU/network |
| Backend lags while app export looks steady | Downstream Collector/backend saturation | Compare accepted/exported/ingested counts |
| Records lost on shutdown | Short flush timeout/grace period | Inspect provider close lifecycle |

### Investigation Workflow

1. Verify the load generator hit the target arrival rate.
2. Check workload mix and warm-up.
3. Compare baseline against each instrumentation variant.
4. Inspect p50/p95/p99, throughput, and error rate.
5. Check CPU, allocations, heap, GC, and threads.
6. Check metric series/cardinality.
7. Check spans/request, sampling, and payload size.
8. Monitor exporter/Collector queues, failures, and drops.
9. Check backend ingest/index lag.
10. Re-run after changing exactly one factor.

## 15. Lab Exercise: Benchmarking Instrumentation

The objective is to quantify metrics, tracing, and logging overhead in a Spring Boot service.

### Preparation

- Spring Boot service with HTTP, a database, and one downstream call or message publish.
- Load generator supporting open/closed models.
- Actuator/Micrometer registry.
- Tracing bridge/exporter and lab Collector.
- Metrics/JVM monitoring for both application and Collector.
- Dataset free of production data.

### Step 1 — Define the Workload

Pick a request mix covering reads, writes, downstream calls, and error paths. Document target arrival rate, payload sizes, and concurrency.

### Step 2 — Run Baseline

Keep extra instrumentation minimal. Warm up, run steady state, and record throughput, p95/p99, CPU, heap, GC, and error rate.

### Step 3 — Enable Metrics

Enable meter handlers/export. Re-run the exact same workload. Record series count, sample rate, CPU, and latency.

### Step 4 — Enable Tracing

Enable producer/server/client/database instrumentation. Run 100% sampling in a bounded lab run, then test lower sampling ratios.

### Step 5 — Enable Structured Logs

Keep log levels and event sets clean. Measure log bytes/sec, CPU, allocations, and queue behavior.

### Step 6 — Test Combined Signals

Enable metrics, traces, and logs simultaneously. Confirm combined overhead stays within budget.

### Step 7 — Simulate a Slow Collector

Throttle the receiver or inject network delay. Observe business latency, exporter queues, and dropped telemetry.

### Step 8 — Check Cardinality

Generate many IDs against the same route template. Confirm metric series do not grow with ID count.

### Step 9 — Repeat the Benchmark

Re-run each variant multiple times in a stable environment. Calculate relative overhead and record variance.

### Step 10 — Finalize Configuration

Select sampling, batch, queue, log level, and Collector capacity aligned with SLOs, telemetry coverage, and cost budgets.

### Acceptance Checklist

| What to prove | Expected outcome |
| --- | --- |
| Baseline | Control run with a fixed workload |
| Workload | Representative request mix and arrival model |
| Warm-up | Startup excluded from steady-state results |
| Latency | Includes p50/p95/p99 |
| Throughput | Meets target arrival rate |
| Resources | Measures CPU, heap, allocations, and GC |
| Metrics | Measures series count and export rate |
| Tracing | Measures spans/request, sampling, and drops |
| Logging | Measures events/sec and bytes/sec |
| Pipeline | Measures exporter/Collector/backend throughput |
| Failure | Business path withstands telemetry outages |
| Repeatability | Multiple runs, environment/config recorded |

## 16. Key Principles to Remember

1. **Always have a control baseline.** Keep workload, build, JVM, and infrastructure fixed.
2. **Measure tail latency and throughput, not just averages.** p95/p99 reveal impact on slow requests.
3. **Isolate metrics, tracing, and logging.** Enable each signal individually before measuring the combined setup.
4. **Design a representative workload.** Request mix, dependency calls, and payload sizes determine telemetry volume.
5. **Observe the entire pipeline.** Successful application export does not prove complete Collector/backend ingestion.
6. **Control cardinality and span density.** Dynamic tags and duplicate instrumentation can sharply inflate costs.
7. **Keep queues bounded.** A slow telemetry backend must never block the business path indefinitely.
8. **Evaluate sampling on both cost and coverage.** Cut spans while preserving error/slow trace investigation capability.
9. **Repeat runs and document the environment.** Results must be reliable enough to compare across releases.
10. **Set SLO- and budget-driven acceptance criteria beforehand.** Never pick thresholds just to justify observed results.

Load testing with instrumentation enabled turns the assumption that "telemetry has low overhead" into verifiable data. With a clear baseline, representative workload, measurements across both the application and telemetry pipeline, and slow Collector/backend fault tests, engineering teams can select a Micrometer Observation, metrics, tracing, and logging configuration that meets SLOs while preserving enough data to operate and investigate incidents.
