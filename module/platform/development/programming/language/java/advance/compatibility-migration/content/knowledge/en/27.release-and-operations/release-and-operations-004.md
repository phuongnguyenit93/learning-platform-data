# Monitoring Errors, Latency, Memory, and GC Behavior After Release

Upgrading the JDK, framework, or packaging mechanism is a change that can affect the application **even when all business code remains identical to the previous version**. A Java 21 release can start up and pass unit tests yet process requests slower at p99; a dependency change can increase 5xx errors; a new JVM can show a different heap graph than before; or a GC configuration change can reduce pause time while increasing CPU usage.

Therefore, **Java Advance Compatibility Migration does not end when the build succeeds**. The release and operations phase requires a measurement system that helps answer four questions:

1. **Errors:** Are users and integrated systems encountering more errors?
2. **Latency:** Has processing time in critical parts degraded, especially tail latency?
3. **Memory:** Do heap, non-heap, native memory, and container memory still have sufficient headroom?
4. **Garbage Collection (GC):** Have the frequency, duration, and impact of collection cycles changed adversely?

A conclusion cannot be drawn from a single isolated chart. For example, an increase in heap-used is not always a memory leak, an increase in GC count is not always an error, and an increase in p99 does not necessarily originate from GC. It is necessary to correlate **release metadata, workload, request traces, JVM metrics, GC events, and system resources** to distinguish normal changes from regressions.

This lesson builds an observability process **before – during – after release**, including baseline, Service Level Indicators (SLI), canary, dashboards, alert thresholds, error tracing, p95/p99 analysis, heap/native memory, GC logs, Java Flight Recorder (JFR), incident handling, and rollback. The illustrative numbers are only hypothetical data; real operational thresholds must be determined from the service's SLO, load, and characteristics.

---

## 1. Why Must Both the Application and JVM Be Measured After Migration?

### 1.1. Changing the JDK Can Change Many Things

Moving from an older JDK to a newer JDK can come with:

- A new compiler and bytecode target.
- A different default GC or GC flags.
- Changes to Java platform APIs and JDK internals.
- Updated TLS, security providers, certificates, locale, or timezone data.
- Upgraded frameworks, drivers, serializers, and bytecode agents.
- A different container base image or cgroup limits.
- Different threading, scheduling, and executor behavior.
- Changes in JVM startup, JIT compilation, warm-up, or class loading.
- Older libraries that only fail on a rarely used code path.

If errors appear after release, you should not automatically blame everything on GC or the JDK. There must be evidence of **which version is running**, **what changes were deployed**, and **which layer the symptoms belong to**.

### 1.2. Observing Across Three Layers

```text
                    User experience
            errors, response time, timeouts
                           |
                           v
                   Application / JVM
              request, trace, thread, heap
                 allocation, GC, safepoint
                           |
                           v
                  Infrastructure / OS
              CPU, RAM, cgroup, I/O, network
                    pod restarts, OOMKill
```

The three layers must be read together. For example, a user reporting timeouts may be caused by a backend GC pause, or by a slow database, a long queue, or network packet loss. A stable heap does not rule out native memory pressure leading to a container OOMKill.

### 1.3. Four Minimum Signal Groups

| Group | What to measure | Risk if omitted |
|---|---|---|
| Errors | Error rate, exception type, startup failures, timeouts | Service is "running" but business operations fail |
| Latency | p50/p95/p99, throughput, queue time | Average looks good but many requests are slow |
| Memory | Heap, non-heap, RSS/container, allocation, OOM | Failure to detect leaks or lack of headroom |
| GC | Pause duration, frequency, GC time ratio, old-gen trend | Unable to explain tail latency and CPU pressure |

In addition, there should be CPU, thread counts, connection pools, database latency, deployment version, and logs/tracing. Do not create a pretty "JVM dashboard" that cannot be linked to user impact.

## 2. First Step: Define Scope and Success Criteria

### 2.1. Migration Goals Must Be Measurable

Instead of writing:

```text
Upgrade Java 17 to Java 21.
Requirement: system runs stably.
```

you should set verifiable criteria:

```text
Application    : order-service
Old runtime    : JDK 17, recorded vendor/version
New runtime    : JDK 21, recorded vendor/version
Framework      : verified version/patch
Infrastructure : same CPU/RAM limits, or differences recorded
SLO            : per current contract
Release        : canary -> increase traffic -> full rollout
Criteria       : no error/latency/memory/GC degradation beyond thresholds
Rollback       : ready if thresholds are confirmed exceeded
```

Those values are structural templates. During actual deployment, you must identify the exact image digest, source revision, dependency versions, and runtime options.

### 2.2. Do Not Set Thresholds by Gut Feeling

For example, a service has a p99 SLO under 300 ms. After migration, p99 increases from 180 ms to 230 ms. This may be a regression worth investigating even though it has not violated the SLO yet. Conversely, p99 increasing from 10 ms to 12 ms might have no operational significance if the product allows a wide margin.

Two types of criteria should be managed:

- **SLO/customer impact:** thresholds that users or the service contract care about.
- **Regression guardrail:** a change relative to the baseline large enough to halt the rollout or investigate.

Guardrails must account for natural variance, sample size, and traffic mix. Not every difference of a few percent is enough to prove a regression.

### 2.3. Classifying Applications

Metrics should be selected based on workload:

| Application type | Core signals |
|---|---|
| HTTP API | Error rate, p95/p99 by route, request throughput, saturation |
| Batch job | Success/failure, job duration, records/sec, retries |
| Message consumer | Lag, processing latency, retry/dead-letter, rebalance |
| Desktop/CLI | Startup time, command duration, crashes, memory footprint |
| Streaming service | End-to-end lag, backpressure, throughput, tail latency |
| JVM library | Test matrix on consumer JDKs, allocation, performance regressions |
| Background scheduler | Missed schedules, execution delay, overlapping jobs |

Do not use HTTP request latency as the sole metric for a batch application or messaging worker.

## 3. Establish a Baseline Before Release

### 3.1. What Is a Baseline?

A **baseline** is the set of metrics and operating conditions recorded from a stably running version, used for comparison after release.

A minimum baseline needs to include:

- Application version and exact JDK vendor/full version.
- Runtime flags, GC collector, and heap/container limits.
- CPU, memory, OS, architecture, container image.
- Workload: request rate, payload sizes, tenant/route mix.
- Error rate and error categories.
- p50/p95/p99 by critical operation.
- JVM heap/non-heap, process RSS, and container memory.
- GC pause, frequency, and allocation rate if available.
- Threads, DB/HTTP connection pools, queue lengths.
- Peak/off-peak times and business-significant days/hours.

### 3.2. Compare Under the Same Load and Conditions

A misleading comparison example:

```text
Before release:
  100 request/s, mostly lightweight GET
  CPU 1 core, RAM 1 GiB

After release:
  300 request/s, many report-generation requests
  CPU 1 core, RAM 1 GiB

Conclusion "New JDK causes p99 increase" -> unfounded.
```

To make comparisons meaningful, variables such as request rate, mix, payload, database load, CPU quota, autoscaling, cache warm-up, instance age, and routing must be controlled or recorded.

A stronger approach is running **old and new canaries simultaneously** under equivalent traffic distribution. If not possible, use representative time windows and clearly state the limitations of the conclusion.

### 3.3. Avoid Taking a Baseline From Too Short a Window

A few minutes before release may not represent:

- Hourly/daily traffic cycles.
- End-of-day batch processing.
- Memory growth after many hours.
- Cron jobs and scheduled cleanup.
- Long GC cycles or rare full collections.
- TLS certificate refresh, connection pool reconfiguration.
- Infrequently called but critical features.

Choose the baseline window based on the actual cycle of the workload, rather than blindly applying a fixed number to every service.

### 3.4. Store Metadata for Comparison

A sample table:

| Attribute | Old release | Candidate release |
|---|---|---|
| App commit | Revision A | Revision B |
| Artifact SHA-256 | Checksum A | Checksum B |
| JDK vendor/build | JDK 17 update X | JDK 21 update Y |
| Collector | G1 as configured | G1 as configured |
| Heap limit | 768 MiB | 768 MiB |
| Container limit | 1.5 GiB | 1.5 GiB |
| CPU limit | 2 vCPU | 2 vCPU |
| Agent version | APM release A | APM release B |
| Traffic share | Stable | Canary |
| Framework | Framework release A | Framework release B |

Numbers and names in the table are illustrative only. Changing the JDK while simultaneously increasing the memory limit and upgrading the framework may be valid, but must be recorded to avoid wrong conclusions about root cause.

## 4. Designing Post-Release Operations Dashboards

### 4.1. Dashboards Must Answer Questions, Not Just Display Numbers

A useful layout:

```text
+-------------------------------------------------------------+
| Release: old vs canary | JDK version | traffic split | time |
+-------------------------------------------------------------+
| Error rate | request rate | SLO burn rate | restart count  |
+-------------------------------------------------------------+
| p50 latency | p95 latency | p99 latency | queue wait       |
+-------------------------------------------------------------+
| CPU | heap used/committed/max | RSS | container memory     |
+-------------------------------------------------------------+
| GC pause p95/p99 | GC time rate | allocation | old-gen     |
+-------------------------------------------------------------+
| Threads | connection pools | retry/dead-letter | logs/traces |
+-------------------------------------------------------------+
```

Most importantly, it must be able to slice by **service, environment, application version, JDK version, and instance/pod** when needed. Avoid creating excessive label/cardinality from request ID, raw URL, email, user ID, or payload.

### 4.2. Aggregate and Segmented Metrics Must Go Together

A service may have a stable overall error rate while one critical route has 20% errors. Therefore:

- Overview dashboard for detection.
- Per-endpoint/operation charts for scoping.
- Breakdown by status code, exception type, dependency.
- Old/canary comparison by release version.
- Drill-down to related traces/logs.

Do not group all latencies into a single chart if lightweight GETs and report generation have completely different latency distributions.

### 4.3. Attach Deployment Events

Dashboards should have markers showing:

```text
10:00 Canary 5%
10:30 Canary 20%
11:15 Canary 50%
12:00 Full rollout
12:20 JDK option changed
```

Timestamps are illustrative only. Markers help determine whether signals began changing right at release time, rather than relying on the on-call engineer's memory.

## 5. Monitoring Errors After Release

### 5.1. Error Rate and Error Budget

For an HTTP service, an SLI could be:

```text
Success ratio =
  number of valid requests completed successfully /
  total number of requests within SLI scope
```

Depending on the product, errors include 5xx, application-level failures, deadline exceeded, timeouts, or returning a "200 OK" response when business logic actually failed. Do not default to treating all 4xx as service errors; some are client input validation, though 429 or 408 may reflect overload depending on the SLI definition.

### 5.2. Errors Specifically Related to Java Migration

| Category | Examples | Investigation meaning |
|---|---|---|
| Linkage | `NoSuchMethodError`, `NoSuchFieldError` | Dependency/ABI mismatch |
| Bytecode | `UnsupportedClassVersionError` | Artifact class version too new |
| Classloading | `ClassNotFoundException`, `NoClassDefFoundError` | Missing JAR/module, init error |
| JPMS/reflection | `InaccessibleObjectException`, `IllegalAccessError` | Access policy/module |
| Resources | `OutOfMemoryError`, native OOM | Heap, metaspace, or native/container |
| TLS | `SSLHandshakeException` | Certificate/protocol/provider |
| Native | `UnsatisfiedLinkError` | JNI/OS/architecture/ABI |
| Concurrency | Deadlock, timeouts, rejected tasks | Threading/executor behavior |
| Framework | Initialization/configuration error | Library/plugin migration |
| Data | Serialization/schema mismatch | Protocol and payload compatibility |

Do not alert only on one specific exception name; production has many application errors that do not manifest as a Java exception or are mapped into a response by the framework.

### 5.3. Counting Errors With Context

Structured log example:

```json
{
  "timestamp": "2026-11-12T10:30:00Z",
  "level": "ERROR",
  "service": "order-service",
  "release": "2.4.0",
  "jdk": "21",
  "operation": "create-order",
  "error_type": "TimeoutException",
  "trace_id": "example-trace-id",
  "message": "downstream deadline exceeded"
}
```

This is a hypothetical log. Do not include raw customer IDs, credentials, or sensitive request bodies in logs. A trace ID can help correlate a failed request with the timing of GC pauses, database latency, and CPU spikes.

### 5.4. Error Increase Monitoring Patterns

| Signal | Observation level | Response |
|---|---|---|
| Error rate increases slightly within background noise | Monitor | Compare traffic mix, samples |
| Error rate exceeds guardrail across multiple windows | Rollout alert | Stop ramping traffic, analyze |
| Clear SLO impact or critical function failure | Incident | Consider immediate rollback per runbook |
| Crash loop after deploy | Severe incident | Check startup/JDK/dependency, restore |
| One canary instance fails, others stable | Partition investigation | Check config/image/node/arch |
| Low error rate because canary has no requests yet | Insufficient data | Do not conclude pass yet |

Specific thresholds must be tied to the SLO, error budget, traffic volume, and criticality of the feature.

## 6. Monitoring Latency: Do Not Use Average Alone

### 6.1. p50, p95, and p99

Latency percentiles represent the threshold below or at which a given percentage of requests complete:

- **p50:** median, showing the typical request.
- **p95:** the vast majority of requests, more sensitive to the tail of the distribution.
- **p99:** 99% of requests are at or below this mark; focuses on tail latency.
- **max:** the slowest request observed in the measurement set, easily skewed by outliers.

Hypothetical example:

| Version | p50 | p95 | p99 | Request rate |
|---|---:|---:|---:|---:|
| Java 17 | 40 ms | 110 ms | 230 ms | 200/s |
| Java 21 | 42 ms | 118 ms | 490 ms | 200/s |

Looking only at average or p50 misses the sharp p99 increase. However, before concluding a regression, confirm sample size, request types, warm-up duration, percentile computation, and traffic mix.

### 6.2. Percentiles Cannot Be Arbitrarily Summed or Averaged

A common mistake:

```text
p99(instance A) = 100 ms
p99(instance B) = 900 ms

Take average (100 + 900) / 2 = 500 ms
-> not necessarily the service-wide p99.
```

If latency is measured using histograms with cumulative buckets, percentiles can be computed from **the sum of appropriate bucket counts**. With client-side percentiles that cannot be simply aggregated across instances, an appropriate collection/distribution method is needed.

### 6.3. What Parts Make Up Total Latency?

A request may pass through:

```text
Ingress / proxy
  -> network queue
  -> server accept
  -> application queue
  -> business processing
  -> DB/HTTP downstream
  -> response serialization
  -> response to client
```

If a JVM application metric only measures from handler entry to handler exit, it does not include all the time observed by the user, such as ingress queue or network RTT. When investigating a regression, separate:

- End-to-end client latency.
- Server-side handler latency.
- Queue wait.
- Dependency call latency.
- Serialization/deserialization.
- GC pauses and safepoints.
- Thread/executor scheduling.

### 6.4. Tail Latency Can Increase Due to GC, But Not Only Due to GC

A slow request may coincide with a stop-the-world pause, or it may be caused by:

- Connection pool exhaustion.
- Database locks or slow queries.
- DNS/TLS handshake.
- Thread pool starvation.
- CPU throttling.
- Retry storms.
- Cache misses/warm-up.
- Synchronized contention.
- Virtual-thread pinning in certain workloads.
- Garbage collection or safepoints.

Correlation between timestamps, traces, and JVM diagnostics is required, rather than guessing from two charts rising together.

## 7. Histograms, Throughput, and Saturation

### 7.1. Choosing Meaningful Histogram Buckets

Suppose a service has a p99 SLO of 300 ms. The latency histogram should have sufficiently granular buckets around 100–300–500 ms to detect violations; if buckets are too sparse, the inferred p99 will be inaccurate.

A hypothetical distribution example:

```text
<= 50 ms    : majority
<= 100 ms   : many
<= 200 ms   : near SLO
<= 300 ms   : target
<= 500 ms   : slow
>  500 ms   : very slow
```

Do not use the same default histogram buckets for a 5 ms endpoint and a 30-minute batch job. Buckets must be based on the SLO and workload.

### 7.2. Throughput Is a Condition for Explaining Latency

A version achieving 200 ms p99 at 20 req/s cannot be claimed faster than a version with 230 ms p99 at 500 req/s.

Monitor alongside:

- Requests/messages/jobs per second.
- Number of concurrent in-flight operations.
- Queue length and queue wait.
- Errors/timeouts/retries.
- CPU usage and throttling.
- Connection pool utilization.
- Load shedding/rate limiting.

In load tests, clearly document warm-up, ramp-up, steady-state, duration, and stop criteria.

### 7.3. Measuring by Route Without Creating Cardinality Explosion

Avoid labels like:

```text
path="/users/12345/orders/98432"
```

If every URL generates a new time series, the metrics system can overload. Use a route template instead:

```text
route="/users/{userId}/orders/{orderId}"
```

Do not put user IDs, order IDs, tokens, or raw query parameters into labels.

## 8. Prometheus/Micrometer Patterns for Analysis

The PromQL examples below **assume** instrumentation emits histogram metrics named `http_server_requests_seconds_*` in Prometheus format and a `status` label containing the HTTP status code. Metric names, labels, classic/native histograms, and semantic conventions differ across Micrometer/OpenTelemetry/exporter versions; verify against real data before applying.

### 8.1. Request Throughput

```promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
```

This is the average rate over a 5-minute window, not the total number of requests in 5 minutes.

### 8.2. HTTP 5xx Ratio

```promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service",
    status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
```

When traffic is too low, the denominator may be 0 or the estimate noisy. Combine with absolute error counts and minimum traffic conditions, and clearly define application errors not reflected by 5xx.

### 8.3. p99 From Classic Histogram

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="order-service",
      uri="/orders/{id}"
    }[5m])
  )
)
```

This is a route-filter example where the `uri` label is only hypothetical. With multiple service instances, sum by `le` to compute the overall distribution; if breaking down by version, keep the version label in `sum by (...)` and split results by release.

### 8.4. Setting Thresholds Without Relying Solely on p99

p99 can fluctuate wildly when request volume is low. Dashboards should include:

- Total request count.
- Error count.
- p50/p95/p99.
- Histogram heatmap or bucket distribution.
- SLO violation ratio.
- Number of affected instances.
- Windows long enough to gather representative samples.

Queries must be verified against the real metrics system; do not deploy production alerts simply because they work on sample data.

## 9. JVM Memory: Understanding Each Region

### 9.1. Heap Used, Committed, and Max

Java heap has the following concepts:

- **Used:** bytes the JVM reports as currently in use in the heap.
- **Committed:** bytes the JVM has committed to the heap.
- **Max:** maximum heap limit per runtime configuration/capability.

Diagram:

```text
Heap max (e.g., 1024 MiB)
+-----------------------------------------+
| Committed (e.g., 768 MiB)               |
| +-------------------------------------+ |
| | Used (e.g., 420 MiB)                | |
| +-------------------------------------+ |
|                 free committed space    |
+-----------------------------------------+
                   uncommitted capacity
```

Used differs from committed; committed differs from RSS. An increasing heap committed graph does not automatically mean live objects are growing or there is a memory leak.

### 9.2. Non-Heap and Native Memory

Java applications use many memory regions outside the object heap:

| Region | Examples | Symptoms |
|---|---|---|
| Metaspace | Class metadata | Classloader leak, plugin redeploy |
| Code cache | JIT compiled code | Code cache pressure, compilation behavior |
| Direct buffers | NIO/Netty direct memory | RSS increases even while heap is stable |
| Thread stacks | Platform threads | Many threads increase native memory |
| JNI/native allocations | Native library, compression, crypto | Process RSS grows without full reflection in heap |
| Memory mapped files | Mapped buffers/files | Page/cache/virtual memory behavior |
| GC internal structures | Collector metadata/buffers | Different collector or heap sizing |
| JIT/runtime internals | Compiler, symbols | Native memory footprint |

Do not simply sum all metrics containing "memory" without understanding overlap. Some container metrics include page cache, whereas JVM heap metrics only describe memory managed by the JVM.

### 9.3. Process RSS and Container Memory

**RSS (resident set size)** is an OS-level view of physical memory currently resident for a process. **Container working set/usage** is a cgroup/container view, which may include different components and calculation methods than RSS.

Example:

```text
JVM heap used       : 500 MiB
JVM heap committed  : 700 MiB
Process RSS         : 950 MiB
Container working set: 1100 MiB
Container limit     : 1200 MiB
```

These numbers are hypothetical. Looking only at heap used = 500 MiB makes it very easy to miss that the container is approaching its memory limit.

### 9.4. Headroom

One way to think about it:

```text
Container memory limit
  -
memory consumption at steady state/peak
  =
headroom for spikes, startup, GC, native allocation
```

Do not assign the entire container limit to `-Xmx` and forget non-heap/native/OS overhead. If the runtime uses `-XX:MaxRAMPercentage`, understand how it interacts with container memory detection and other flags.

## 10. Distinguishing Normal Heap Growth From Memory Leaks

### 10.1. Sawtooth Heap Pattern

In a JVM with GC, a typical graph looks like:

```text
Heap used
  ^
  |        /\        /\       /\
  |       /  \      /  \     /  \
  |      /    \    /    \   /    \
  |_____/      \__/      \_/      \____
  +------------------------------------> time
             GC        GC       GC
```

This can be normal behavior: objects are allocated and then reclaimed during GC.

### 10.2. Continuously Rising After-GC Baseline

A more notable sign:

```text
After-GC live set
  ^
  |                              __
  |                        _____/
  |                   ____/
  |              ____/
  |         ____/
  |________/
  +------------------------------------> time
```

If the **live set after comparable GC cycles** increases over hours/days under similar workload and does not stabilize at a new level, there may be excessive retained objects, an unbounded cache, or a leak.

However, the same shape can appear when:

- A cache is warming up to its target size.
- Traffic/concurrency is increasing.
- A batch holds valid data longer.
- A new feature intentionally holds state.
- The GC collector or heap ergonomics changed.

Do not declare a memory leak solely from a rising "heap used" line over 10 minutes.

### 10.3. Information to Collect

- Heap used/committed/max over time.
- Old-generation occupancy or live set when collector-appropriate metrics exist.
- Allocation rate and object types.
- Number of instances, traffic, concurrency.
- Cache size/eviction metrics.
- Thread count and classloader count.
- Full GC or concurrent cycle behavior.
- Heap dump/JFR allocation/retention analysis if needed.

### 10.4. Heap Dumps Contain Sensitive Data

Heap dumps can contain passwords, tokens, request objects, and customer data. When enabling dumps:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
```

ensure sufficient disk space, strict access permissions, a retention policy, encryption, and a deletion procedure. Never automatically upload dumps to a public ticketing system.

## 11. Native Memory and Container OOMKill

### 11.1. Heap Is Not Full Yet the Pod Gets Killed

A scenario:

```text
Heap used                 400 MiB / max 768 MiB
Metaspace                  130 MiB
Direct buffers             250 MiB
Thread stacks/native       220 MiB
Other runtime/native       180 MiB
Container limit           1400 MiB
```

These illustrative numbers do not represent an exact summation rule, as metrics may overlap. However, they show that native/non-heap usage can push total memory past the container limit before heap reaches `-Xmx`.

A container OOMKill typically does not produce a Java `OutOfMemoryError` with a heap dump. The process may disappear and the container orchestrator reports reason `OOMKilled` or the corresponding exit code, depending on the environment.

### 11.2. When to Use Native Memory Tracking?

HotSpot Native Memory Tracking (NMT) can help categorize memory managed by the JVM. A common startup configuration:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Then, on a runtime supporting `jcmd` and attach:

```shell
jcmd <pid> VM.native_memory summary
```

Baseline/diff can be used if the HotSpot version supports it:

```shell
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT has overhead and **does not necessarily track every allocation by third-party native libraries**. It is not a total process RSS measurement tool replacing OS metrics. Enable it under a controlled diagnostic procedure; it must be configured at startup to collect appropriate data.

### 11.3. Thread Count and Stack Memory

Each platform thread requires a stack and native structures. If an application creates too many platform threads, native memory can grow even with ample heap remaining.

Monitor:

- Live platform threads.
- Thread creation rate.
- Thread pool size and queue length.
- Idle/busy worker counts.
- Deadlocks or thread contention.
- JVM thread stack settings if intentionally changed.

With virtual threads, the memory and scheduling model differs from platform threads. Do not infer from total virtual thread count that native stack memory grows at a ratio similar to platform threads.

## 12. Garbage Collection: Concepts to Measure

### 12.1. GC Is Not Just "Cleaning Up Garbage"

GC manages object lifecycles on the heap. Collectors may perform work:

- Concurrently with application threads.
- Stop-the-world (STW) while application threads are paused.
- Young-generation collections.
- Mixed/old-generation collections or corresponding collector phases.
- Compaction, marking, relocation, remembered-set maintenance.

Phase names and behaviors differ across G1, Parallel GC, ZGC, Shenandoah, and specific collectors/versions. Do not apply the "young/full GC" labels of one collector to another without understanding the logs.

### 12.2. Key GC Metrics

| Metric | Meaning | What to avoid |
|---|---|---|
| GC pause duration | Duration of a pause/event affecting progress | Looking only at average, ignoring p99 |
| GC pause count/rate | Frequency of pauses | Treating increased count as an automatic error |
| GC time ratio | Proportion of time the JVM spends on GC activity per metric definition | Confusing with total CPU used by GC |
| Allocation rate | Bytes of objects allocated per second | Looking only at heap used |
| Reclaimed bytes | Data reclaimed per event/collector | Absolute comparison across different loads |
| Old/live set trend | Long-lived data, heap pressure risk | Concluding a leak from a short window |
| Concurrent cycle duration | Phase running alongside the application | Equating with STW pauses |
| Full/degenerate collections | Signal of pressure or special path depending on collector | Crude comparison across collectors |
| Safepoint pause/time-to-safepoint | JVM synchronization outside/around GC | Attributing every safepoint to GC |

### 12.3. Increased GC Frequency Is Not Always Bad

For example, changing collectors may produce many very short pauses instead of a few long ones. In that case `GC count` increases, yet tail latency improves.

Conversely, fewer GC events with each pause lasting longer harms p99. Examine **pause duration distribution, total GC overhead, and application impact**, rather than judging by a single number.

### 12.4. Some Changes When Upgrading the JDK

- GC implementation versions and ergonomics may change.
- Heap sizing and cgroup detection may differ.
- Default flags or option support change.
- Some collectors report metrics/log events differently.
- Virtual threads, allocation patterns, or framework object graphs may change.
- Agents and profilers can alter overhead.

Before comparing GC, record the exact collector and startup flags. If you simultaneously switch collectors from G1 to another collector, that is a **separate performance experiment** that must be analyzed as an independent variable.

## 13. Reading GC Pauses and Correlating With Request Latency

### 13.1. Timestamp Correlation Mindset

Suppose:

```text
12:00:10.100 Request starts
12:00:10.220 GC pause starts
12:00:10.460 GC pause ends
12:00:10.570 Request ends
```

The request took 470 ms and overlapped a 240 ms pause. This is evidence to investigate the GC contribution, but does not prove the entire 470 ms was due to GC: the request may have spent additional time waiting on DB/network.

### 13.2. Clock Synchronization and Measurement Units

GC logs usually have timestamps, uptime, or both depending on configuration. Application traces/logs have timestamps from another system. To correlate:

- Synchronize clocks across instances and log collectors.
- Record consistent timezones, preferring UTC in the pipeline.
- Know whether metrics are in seconds, milliseconds, or nanoseconds.
- Distinguish wall-clock duration from CPU time.
- Record deploy markers and pod restarts to avoid misaligning uptime intervals.

Especially when a container restarts, JVM uptime resets; do not compare two uptime lines from different processes as if on the same timeline.

### 13.3. GC Does Not Explain Every STW Pause

Other safepoints can pause threads. If the application has tail latency spikes while GC pauses are low, inspect safepoint logs, thread contention, CPU throttling, lock wait, and downstream traces.

Only enable tracing/diagnostics detailed enough for the need; logging every class load or every allocation in production can create heavy overhead.

## 14. Enabling GC Logging on Modern JDKs

### 14.1. Unified Logging From JDK 9+

On HotSpot JDK 9+, you can use:

```shell
java \
  -Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
  -jar application.jar
```

The idea behind the example:

- Log GC and safepoint event groups.
- Include timestamp and uptime.
- Write to a file at the configured path.
- Rotate by file count and size per file.

The path must have write permissions, sufficient space, and an appropriate retention policy; logging syntax/tags depend on the JVM version and implementation. For containers, choose stdout or a file volume per logging policy.

### 14.2. JDK 8 Uses Different Syntax

A traditional HotSpot JDK 8 example:

```shell
java \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:gc.log \
  -jar application.jar
```

Do not copy these JDK 8 flags into JDK 21 without checking: Java unified logging changed the mechanism and some old flags are no longer appropriate.

### 14.3. Choosing a Balanced Log Level

Overly detailed GC logging can:

- Increase I/O and disk usage.
- Put pressure on log collectors.
- Make it harder to find critical events.
- Add overhead in sensitive workloads.

Start with a level sufficient to observe collection events, pause durations, and heap transitions; only enable deep trace/debug when testing an investigation hypothesis. Rotation and retention limits are required.

### 14.4. GC Log Parsers Must Understand the Collector and Version

Do not write a parser relying on a fixed English string from JDK 8 and use it for all newer JDKs. Unified logging formats and event names can differ.

Choose a parser supporting the running JDK/collector/version, or use JMX/Micrometer/JFR events with verified semantic conventions.

## 15. JVM Diagnostic Tools

### 15.1. jcmd

If the runtime includes the appropriate tools and serviceability mechanism:

```shell
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
```

Replace `<pid>` with the actual PID. Supported commands may vary by JDK/vendor or custom runtime image. `jcmd` typically requires matching OS permissions and attach capability.

Do not assume a container lacking `jcmd` means the JVM cannot provide diagnostics; JFR startup, agents, or other suitable operational tools can be used.

### 15.2. jstat

In JDKs with `jstat`, a command might be:

```shell
jstat -gcutil <pid> 1000 10
```

This sample captures multiple GC utilization snapshots at an interval. Output and columns depend on the JDK/collector; do not build a production alerting system on a column without verifying semantics on the target JDK.

### 15.3. Java Flight Recorder (JFR)

JFR helps collect relevant JVM and application events:

- GC pauses and allocation.
- CPU/thread samples.
- File/socket I/O.
- Locks/monitor contention.
- Exceptions within configured scope.
- Class loading and runtime state.

A way to enable recording at startup on a suitable HotSpot JDK:

```shell
java \
  -XX:StartFlightRecording=filename=/secure-diagnostics/service.jfr,settings=profile \
  -jar application.jar
```

Or via `jcmd` when the runtime allows:

```shell
jcmd <pid> JFR.start name=migration settings=profile duration=5m filename=/secure-diagnostics/migration.jfr
```

`settings=profile` typically captures more detail than `default` and carries overhead; options must be verified against the specific JDK. JFR files can contain sensitive information about threads, paths, networks, and stack traces; protect them similarly to other diagnostic artifacts.

### 15.4. Java Mission Control (JMC) and Analysis Tools

JFR recordings can be opened with compatible analysis tools such as Java Mission Control to inspect hotspots, thread states, allocation, and GC events.

The goal is using recordings to **test hypotheses**. For example, if p99 increases, check whether lock contention or an allocation spike coincides with that timeframe, rather than simply turning on a profiler and guessing from an overall chart.

### 15.5. Heap Dumps

Heap dumps are useful when suspecting retained objects/leaks, but:

- They can be very large.
- They can pause the application or impact resources depending on method.
- They can contain sensitive data.
- They require permissions, storage location, and a deletion plan.
- They can exhaust container disk space.

Collect only under an approved procedure suited to severity and privacy/security policy.

## 16. Micrometer/OpenTelemetry/JMX Metrics

### 16.1. Distinguishing Metric Names and Meanings

Systems often expose JVM metrics such as:

```text
jvm_memory_used_bytes
jvm_memory_committed_bytes
jvm_memory_max_bytes
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
jvm_threads_live_threads
process_cpu_usage
```

These names are common examples from certain instrumentation systems, **not a mandatory schema for every exporter**. Always inspect actual labels and units before computing.

### 16.2. Heap by Pool

If the `jvm_memory_used_bytes` metric has an `area` label with value `heap`:

```promql
sum by (instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
)
```

When checking committed/max, understand that some memory pools have an undefined `max` or metrics vary by collector. Do not mechanically calculate "% heap" if the denominator is invalid.

### 16.3. GC Pause Time Rate

If the exporter provides total pause time as the counter `jvm_gc_pause_seconds_sum`, an illustrative query:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{
    application="order-service"
  }[5m])
)
```

The unit is **seconds of pause / second of observation time** as calculated by the exporter; it is not necessarily the exact "% of JVM CPU used for GC". With concurrent collectors, distinguish STW pause events from concurrent CPU activity.

### 16.4. GC Pause Count Rate

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{
    application="order-service"
  }[5m])
)
```

Check which types of GC events the exporter counts and labels like action/cause. A higher count can be reasonable if pauses are shorter; inspect alongside duration distribution and workload.

### 16.5. Container Memory

If infrastructure publishes container memory metrics, usage/working set can be compared against limits and restarts/OOMKilled. However, cAdvisor/Kubernetes metric names and working set definitions differ by system.

A trustworthy dashboard must document **the source of each metric**, rather than mixing process RSS, heap committed, and cgroup memory as three ways of writing the same quantity.

## 17. Monitoring GC After Switching Collectors

### 17.1. No Collector Is Best for Every Workload

GC choices carry different trade-offs:

- Throughput.
- Tail latency.
- CPU overhead.
- Memory overhead.
- Heap size and allocation behavior.
- Pause predictability.
- Container constraints.
- Runtime/JDK vendor support.

Do not assume switching to a "low latency" collector always reduces total resource usage. A collector may reduce STW pauses while increasing concurrent CPU or memory overhead.

### 17.2. Variable-Isolation Testing

If a migration changes both the JDK and the GC collector, establish a matrix where feasible:

```text
A: old JDK + old collector
B: new JDK + old collector (if supported)
C: new JDK + new collector
```

Comparing B with A shows JVM/JDK changes; comparing C with B shows collector impact. Even so, GC implementation versions still differ across JDK releases, so results only support inference under controlled test conditions.

### 17.3. Data to Compare

- p95/p99 GC pause by workload.
- Request p95/p99 and timeouts.
- CPU usage and throttling.
- Memory footprint.
- Allocation rate/live set.
- GC time ratio and throughput.
- Reclaim behavior.
- Startup/warm-up.
- Full/degenerate/fallback collection incidents if the collector defines those concepts.

Do not compare raw counts of "Full GC" across different collectors and conclude one collector is better than another.

### 17.4. GC Flags Must Be Recorded and Verified

For example, HotSpot has collector selection flags across releases, though support can change:

```text
-XX:+UseG1GC
-XX:+UseParallelGC
-XX:+UseZGC
```

These are only familiar example flag names. When selecting a collector, check whether the specific version/runtime supports it and verify the exact syntax; do not copy an old string of flags verbatim to JDK 25 or another vendor.

## 18. GC, Allocation Rate, and Application Design

### 18.1. Allocation Rate Affects GC Pressure

A serializer or data-transformation change can create many temporary objects:

```text
Request -> parse JSON -> DTOs -> transformations
                               -> temporary strings/lists
                               -> response serialization
```

If allocation rate spikes, GC may have to do much more work even though live set does not change. For example, an API using new object mapping may consume extra CPU/GC while unit tests still pass.

### 18.2. Do Not Blindly "Optimize" by Retaining Objects Longer

One way to reduce allocations is caching results. However, an unbounded cache can inflate the live set and cause memory pressure. Measure:

- Cache hit ratio.
- Cache size/weight.
- TTL/eviction policy.
- How much allocation is reduced.
- How much after-GC heap occupancy increases.
- Changes in p95/p99 and memory headroom.

### 18.3. Thread Locals and Classloader Leaks

Some leaks occur when:

- Thread-local values are not properly cleaned up.
- Executors hold references to long-lived objects.
- Plugin/redeploy creates a new classloader while the old classloader remains referenced.
- Static caches hold data per deployment.

Growing metaspace or old-gen can be a signal. Inspect object retention/root paths via heap analysis rather than just increasing `-Xmx` to delay the symptom.

### 18.4. Virtual Threads and GC

If a migration adopts virtual threads, it may create more concurrent tasks and change the allocation profile. Check:

- Number of concurrent tasks.
- Scheduling/backpressure.
- Stack/continuation-related memory by JVM version.
- Thread-local usage.
- Network/database pool limits.
- Allocation and GC pause behavior.

Do not infer that "virtual threads are lightweight" means memory always decreases in every application. The number of tasks and payload per task still matter.

## 19. Canary Releases and Old – New Comparison

### 19.1. Why Are Canaries Useful?

A canary routes a portion of traffic to the new version while the remainder stays on the previous version:

```text
                 Production requests
                        |
               +--------+--------+
               |                 |
               v                 v
        Stable JDK 17       Canary JDK 21
         Release A           Release B
               |                 |
               +--------+--------+
                        |
                Compare metrics
                        |
             Promote / hold / rollback
```

Simultaneous comparison reduces the impact of time-of-day variance. However, traffic routing may send a different mix to the canary than to stable, so verify how requests are split.

### 19.2. Traffic Ramp Stages

An illustrative progression:

```text
0% -> 5% -> 20% -> 50% -> 100%
```

These percentages are not mandatory standards. For low-traffic services, 5% may not provide enough samples to detect rare errors. For critical transactions, the team may require staging/load tests and longer observation before raising the percentage.

Each gate must be based on:

- SLO/error budget.
- Error count and sample size.
- p95/p99 by critical route.
- Heap/native/container headroom.
- GC pauses and allocation.
- Restart/OOMKilled/crash count.
- Downstream dependency behavior.
- Features actually exercised by the canary.

### 19.3. Do Not Compare a 2-Minute Canary With a 2-Week Stable Instance

The JVM has warm-up, JIT compilation, cache fill, connection pool establishment, and differing traffic routing. Comparisons must consider uptime and equivalent workloads.

Track all of:

- Cold-start behavior.
- Warmed steady-state behavior.
- Peak-load behavior.
- Long-running memory behavior.

A build that ramps cleanly after 2 minutes is not enough to conclude there is no leak after 24 hours. A build with poor p99 during cold start is not necessarily bad at steady-state, though if the product requires fast startup then cold start remains an important SLI.

### 19.4. Canaries Need Proper Version Labels

Series or traces must distinguish:

```text
service.name
deployment.environment
service.version
jdk.version
container.image.digest
instance/pod identifier
```

Do not use labels with uncontrolled cardinality. For tracing, release/JDK can be placed in resource attributes instead of repeating them in every log message in a high-cost manner.

## 20. Alert Thresholds and Rollout Halt Conditions

### 20.1. Alert on Impact, Not Every Minor Fluctuation

A good alert needs to answer:

- Are users impacted?
- How severe is the impact?
- Is the condition sustained or just a spike?
- Are there enough samples to conclude?
- Does the on-call engineer have a clear action?

Metrics like GC count or heap used should serve as diagnostic signals or guardrails; they should not necessarily trigger a pager alert simply for crossing an unverified number.

### 20.2. Two Alerting Tiers

**Tier 1 — User-facing SLI:** error rate, latency SLO violations, availability, job lag.

**Tier 2 — JVM/resource early warning:** heap/container pressure, pause spikes, CPU throttling, abnormal restarts, threads/queue saturation.

Tier 2 helps explain and prevent issues, but does not replace Tier 1.

### 20.3. Hypothetical Guardrail Examples

| Metric | Policy example | Action |
|---|---|---|
| Error rate | Exceeds baseline significantly and sustains across windows | Hold/pause rollout |
| Critical route p99 | Exceeds SLO or approved regression threshold | Investigate traces/GC/downstream |
| Container memory | Persistently low headroom or OOMKilled occurs | Stop increasing traffic |
| GC pauses | Increased tail pauses paired with latency impact | Cross-check GC logs/JFR |
| Crash loops | Appears across multiple canary instances | Rollback per runbook |
| Message lag | No longer keeping up with producer | Reduce traffic or rollback |
| Sample count | Too low | Do not promote due to insufficient evidence |

Do not take these examples as concrete thresholds. Some services need alerts within seconds; batch services may be evaluated by the hour or per entire job.

### 20.4. Error-Budget Burn Rate

When an SLO exists, error budget consumption rate can be tracked over short and long windows. Fast burn alerts on severe incidents; slow burn catches small, sustained regressions.

However, burn-rate alerts are only reliable when the SLI/denominator is properly defined. If a system has almost zero traffic, a bare percentage can be very noisy.

## 21. Rollback Decisions: Require Sufficient Evidence Without Excessive Delay

### 21.1. Causes That May Require Fast Rollback

- Crash loop due to dependency/bytecode/classloading.
- Elevated error rate causing loss of service availability.
- Severe p99/timeout SLO violations.
- Repeated OOMKilled or zero memory headroom.
- Long GC pauses impacting business operations.
- Data corruption or protocol incompatibility.
- Significant security regression.
- Loss of ability to safely observe/diagnose production.

Decisions need clear owners and coordination authority. Once severe impact is confirmed, do not wait to pinpoint the exact GC or library root cause before restoring a stable build, if rollback is the safe option.

### 21.2. Roll Back Both the App and Runtime/Dependencies

```text
Release A:
  application.jar A
  JDK 17 runtime
  dependency graph A
  agent version A

Release B:
  application.jar B
  JDK 21 runtime
  dependency graph B
  agent version B
```

Rolling back only the application JAR while keeping B's runtime/dependency graph may fail to restore the tested state. For OCI images, use the image digest of a known-good release; for bundles, use the artifact checksum and accompanying runtime.

### 21.3. Data Schema Is an Independent Rollback Condition

Rolling back an executable does not reverse database schemas or events already written by the new producer. Verify data backward compatibility, expand/contract migrations, and consumer status before rolling back.

### 21.4. Avoid Data Loss During Canary

If a canary writes to the same database or publishes messages, code rollback must check:

- Idempotency/retries.
- Schema compatibility.
- Queue backlog.
- Incomplete data.
- Request side effects.
- Job checkpoint/progress.

A canary may be small in traffic yet still produce critical side effects.

## 22. Case Analysis: p99 Increases After JDK Upgrade

### 22.1. Initial Signals

Suppose the dashboard shows:

```text
Old release:
  p99 = 250 ms
  error rate = 0.1%
  GC pause p99 = 35 ms

New canary:
  p99 = 570 ms
  error rate = 0.2%
  GC pause p99 = 40 ms
```

Hypothetical data. Although GC pause p99 rose slightly, there is no basis to claim GC alone explains the 320 ms request p99 difference.

### 22.2. Investigation Procedure

1. Verify whether the canary receives an equivalent request mix and load as stable.
2. Identify which routes experienced the p99 increase.
3. Open traces of slow requests.
4. Inspect DB, downstream HTTP, queue, and lock contention times.
5. Check CPU throttling and thread pool saturation.
6. Correlate timestamps with GC/safepoint events.
7. Check allocation rate if code/framework changed.
8. Attempt reproduction in staging/load tests.
9. Isolate JDK impact from framework/agent changes if possible.
10. Hold/rollback according to SLO and risk level.

### 22.3. Possible Conclusions

- DB connection pool exhaustion: not a GC root cause.
- Slow JIT warm-up: measure cold vs steady-state.
- New serializer creates many objects: higher allocation, GC pressure is a consequence.
- Lower CPU limit on new container: throttling drives up p99.
- New agent instruments more methods: higher tracing overhead.
- New GC collector has different tail behavior: needs benchmarking and GC diagnostics.

These are **hypotheses to prove**, not conclusions drawn from a single table of numbers.

## 23. Case Analysis: Stable Heap Yet Pod OOMKilled

### 23.1. Situation

```text
Heap used          350 MiB
Heap max           700 MiB
Process RSS       1200 MiB
Container limit   1280 MiB
Pod restart        OOMKilled
```

Looking at heap used, it seems the JVM still has plenty of memory. Yet RSS is close to the container limit.

### 23.2. Steps

1. Confirm exit reason and timestamp of the OOMKill.
2. Check heap used, committed/max, and container working set.
3. Inspect direct buffer metrics, thread counts, metaspace, classloaders.
4. Check native/JNI allocations if present.
5. Check JVM flags related to memory sizing.
6. Enable NMT in an appropriate environment if needed.
7. Check whether traffic, threads, or buffers increased after release.
8. Re-examine container limits/base image.
9. Choose to fix leaks/reduce allocations/adjust memory limits based on evidence.
10. Test peak load and preserve headroom.

Do not simply increase `-Xmx`: that can cause the container to OOMKill **even sooner** if total memory is constrained.

## 24. Case Analysis: GC Count Increases Yet Latency Improves

Suppose:

| Metric | Version A | Version B |
|---|---:|---:|
| GC pauses/minute | 4 | 20 |
| GC pause p99 | 180 ms | 16 ms |
| HTTP p99 | 400 ms | 260 ms |
| CPU | 60% | 68% |
| Container RSS | 800 MiB | 850 MiB |

Hypothetical data. Higher pause count **is not automatically a regression** because p99 GC pause and request latency dropped. However, CPU/RSS rose, requiring a trade-off evaluation against resource budget and capacity.

If Version B delivers good latency at excessive compute cost, the decision depends on the SLO and financial/operational needs. Do not rank GC collectors by a single metric.

## 25. Monitoring Startup, Shutdown, and Restarts

### 25.1. Startup Time

After upgrading the JDK/framework, measure:

- Time from process start to readiness.
- Class loading and dependency initialization.
- JIT/warm-up needed for initial requests.
- Database connection initialization.
- TLS/credential initialization.
- Time to build cache/restore state.

Longer startup can impact autoscaling and rolling deploys, even when steady-state p99 is good.

### 25.2. Readiness Differs From Liveness

If readiness is marked true too early, the load balancer may send requests to a JVM that is still warming up or not yet connected to backends. This drives up canary errors/latency without necessarily being caused by GC.

The liveness probe should detect a stuck/dead process, whereas readiness must reflect capability to receive traffic by design. Set appropriate thresholds and avoid restart loops caused by slow startup.

### 25.3. Graceful Shutdown

JDK/framework/executor changes can affect:

- Time to finish in-flight requests.
- Message acknowledgement/rebalancing.
- Thread pool shutdown.
- JFR/telemetry flush.
- Connection teardown.
- Queue draining.

A release with nice p99 that drops messages when a pod is replaced still fails acceptance.

### 25.4. Restart Counters Must Have Causes

Categorize:

- Rolling deployment due to release.
- Liveness probe kill.
- Process crash.
- Container OOMKilled.
- Node eviction.
- Manual restart.
- Native JVM crash.
- External kill signal.

Do not treat an increase in total restart count during a rollout as an incident if it merely reflects planned replacements. Separate abnormal restarts.

## 26. Data Conditions for Reliable Decisions

### 26.1. Sample Size and Statistical Noise

With a 1% traffic canary, a rare route may only receive a few requests. Percentiles or error ratios from small samples fluctuate easily.

Example:

```text
Canary has 5 requests, 1 failed request -> 20% error rate
Canary has 100,000 requests, 100 errors -> 0.1% error rate
```

These two rates do not carry the same certainty. Do not promote simply because the canary has few errors **when it has barely been called**.

### 26.2. Traffic May Not Be Randomly Distributed

Some gateways route by user/session/region. A canary may receive:

- More users in one country.
- Larger payloads.
- A specific tenant.
- A different database cluster.
- Traffic from a particular mobile app version.
- Requests with a low cache hit ratio.

To compare old/new, account for workload distribution and optionally stratify results by appropriately anonymized route/region/tenant segments.

### 26.3. Seasonality and Long-Running Issues

A canary passing 30 minutes of testing does not catch every leak or batch issue. Long-running soak tests/staging or longer canaries may be needed if risks involve memory growth, timezone schedules, or periodic jobs.

### 26.4. Do Not Aggregate p99 Across Windows by Averaging

A p99 computed for 5 minutes cannot be averaged with p99 values of other intervals and treated as the daily p99. To aggregate accurately, use appropriate distribution/histogram data or recompute from raw samples when feasible.

## 27. Phased Post-Release Monitoring Mechanism

### Phase 1: Pre-Release

- Define baseline and acceptance criteria.
- Check application/JVM instrumentation.
- Prepare dashboards with release/JDK labels.
- Verify trace/log correlation.
- Save resolved dependencies and runtime flags.
- Check GC logging/JFR/NMT policy if needed.
- Prepare rollback and owners.
- Check staging load/soak tests.
- Identify business operations that the canary must exercise.

### Phase 2: Small Canary

- Confirm actual version and runtime.
- Verify no startup/linkage errors.
- Check error rate and response codes.
- Compare p95/p99 by route.
- Check heap, process RSS, container headroom.
- Check GC pause/CPU/throttling.
- Verify trace/telemetry exporters.
- Hold if samples are insufficient or blockers appear.

### Phase 3: Controlled Traffic Ramp

- Compare old/new at equivalent load.
- Check downstream dependency saturation.
- Monitor allocation and long-lived memory.
- Watch for retry storms and queue lag.
- Evaluate SLO burn rate.
- Check scaling/restarts.
- Record each promote or hold decision.

### Phase 4: Full Rollout

- Verify all instances run the desired release.
- Monitor traffic segments that never passed through the canary.
- Observe peak/off-peak and scheduled jobs.
- Do not delete baseline/old dashboards immediately.
- Retain rollback artifacts.
- Update runbooks and incident notes.

### Phase 5: Post-Stabilization

- Evaluate memory/GC trends over long cycles.
- Compare CPU/RAM cost and performance.
- Review any incidents/alerts that occurred.
- Finalize the migration report and remaining issues.
- Reduce temporary diagnostic logging if safe.
- Maintain continuous SLO-based monitoring.

## 28. Runbook When Detecting Errors or Regressions

### 28.1. Initial Triage

```text
Alert arrives
    |
    v
Confirm customer impact / SLO
    |
    +-- Severe --> containment/rollback per runbook
    |
    v
Compare stable and canary
    |
    v
Classify: error / latency / memory / GC / infra
    |
    v
Find release change + instance + trace
    |
    v
Collect bounded evidence
    |
    v
Fix, retest, decide rollout
```

### 28.2. When Error Rate Increases

- Check exception/status distribution.
- Check which endpoints the errors occur on.
- Look for `NoSuchMethodError`/`IllegalAccessError`/TLS/JDBC.
- Compare dependency graph, JDK version, app config.
- Check rollout version and classloader/image digest.
- Pause rollout or roll back when users are clearly impacted.

### 28.3. When Latency Increases

- Compare percentiles by operation under equivalent load.
- Analyze traces.
- Check dependency latency and queues.
- Check CPU saturation/throttling.
- Correlate GC/safepoint events.
- Use JFR/thread dumps if still unclear.

### 28.4. When Memory Increases

- Distinguish heap used, live set, committed, native, RSS.
- Check traffic/concurrency/cache/threads.
- Verify whether GC reclaims normally.
- Distinguish OOMKilled vs Java OOME.
- Collect heap dump/JFR/NMT in a controlled way if needed.
- Adjust app/limits based on root cause, not just raising heap.

### 28.5. When GC Pauses Increase

- Confirm collector/JDK flags and workload.
- Analyze pause distribution, GC time rate.
- Inspect allocation, old-gen occupancy.
- Check CPU/container throttling.
- Compare against app latency impact.
- Distinguish warm-up, heap sizing, and collector behavior.
- Test configuration in staging before changing production flags.

## 29. Privacy and Observability Cost

### 29.1. Tracing/Logging Can Generate Sensitive Data

Traces, exception logs, heap dumps, and JFR recordings may contain:

- URLs/paths and query parameters.
- Request headers.
- Tokens/credentials.
- Stack traces with business content.
- Internal file paths.
- User/tenant information.
- Object contents in the heap.

Apply appropriate redaction, sampling, access control, retention, and encryption. Do not create high-cardinality metrics based on personal identifiers.

### 29.2. Overhead of Diagnostic Tools

Tools carry different levels of overhead:

| Tool | Purpose | Notes |
|---|---|---|
| JVM metrics/JMX | Continuous monitoring | Overhead usually low when properly configured |
| Basic GC logging | GC event history | I/O and retention |
| Detailed GC/safepoint logging | Detailed debugging | Large log volume |
| JFR default/profile | JVM events and sampling | Overhead depends on settings/volume |
| Deep allocation profiling | Object churn analysis | Can be significant |
| Heap dump | Retained object analysis | High disk size and data sensitivity |
| NMT | Native JVM memory categories | Must be enabled at startup, has overhead |
| Full classloading logs | Finding JAR/class origin | Very high log volume |

Do not leave all debug modes enabled in production indefinitely. Start with essential monitoring, and only increase detail when there is a specific question to answer.

### 29.3. Telemetry Cost

High-cardinality metrics, overly high trace sampling, or unbounded GC logs can drive up cost and create I/O burden. During a migration, control:

- Retention by data type.
- Sampling policy.
- Number of metric labels and time series.
- Storage quota.
- Log rotation.
- Diagnostic artifact lifecycle.

An observability system must not become a source of regression itself.

## 30. Mistakes to Avoid

**Looking only at CPU and heap and concluding the application is healthy.** Users may still be experiencing severe errors/timeouts despite spare resources.

**Looking only at average latency.** Tail p99 can degrade severely while the average barely moves.

**Treating every GC count increase as an error.** Pause duration and impact are the factors that matter.

**Treating rising heap used as a memory leak.** Look at the after-GC live set, workload, caches, allocation, and a longer timeframe.

**Equating process RSS with heap used.** Native memory, direct buffers, thread stacks, and container page cache make them different.

**Setting `-Xmx` equal to the entire container limit.** Can trigger OOMKill due to non-heap/native overhead.

**Changing JVM flags before knowing the cause.** An unverified GC change can worsen latency or resource costs.

**Comparing two versions under different traffic.** There is no basis to attribute differences to the JDK.

**Calculating service-wide p99 by averaging each pod's p99.** Such percentile aggregation is invalid.

**Using HTTP 200 success to mask application-level errors.** SLIs must reflect the business contract.

**Promoting a canary when traffic is near zero.** Insufficient evidence, especially for rare routes.

**Not tagging release/JDK labels on metrics.** Cannot reliably compare stable/canary.

**Testing only startup.** Runtime errors can surface when a feature is invoked for the first time.

**Using JDK 8 GC logs as the standard format for JDK 21.** Tools and flags must match the release.

**Failing to protect JFR/heap dumps.** Diagnostic artifacts can contain sensitive data.

**Rolling back only application.jar while keeping the new runtime/dependencies.** May fail to restore the tested environment.

**Not managing JVM security updates.** A performance-stable release still needs updates when JDK patches arrive.

## 31. Hands-on Exercises

### Exercise 1: Reading Canary Results

Given the hypothetical table:

| Metric | Stable | Canary |
|---|---:|---:|
| Request rate | 200/s | 10/s |
| Error rate | 0.1% | 0.0% |
| p99 latency | 220 ms | 120 ms |
| Heap used | 500 MiB | 300 MiB |
| Uptime | 20 days | 3 minutes |

Explain why we cannot yet conclude the canary is better: sample size, cache warm-up, uptime, workload mix, and request distribution.

### Exercise 2: GC Count Increases

Version A has 4 pauses/minute with 180 ms p99 pause; Version B has 20 pauses/minute with 15 ms p99 pause. HTTP p99 is lower in B, but CPU increased.

Propose an evaluation based on SLO, throughput, CPU cost, live set, and pauses instead of merely counting collections.

### Exercise 3: Heap Not Full Yet OOMKilled

A container has a 1 GiB limit, 600 MiB heap max, and 350 MiB heap used; process RSS is high near 1 GiB.

Create a plan to collect direct buffers, metaspace, thread stacks, JNI/native, cgroup metrics, NMT, and OOMKilled events. Explain why increasing `-Xmx` can be dangerous.

### Exercise 4: Correlating p99 and GC

A request took 700 ms; the GC log shows a 120 ms pause within that interval. Propose using tracing to separate server processing, DB/HTTP, queue wait, lock contention, and GC contribution. Can we conclude all 700 ms came from GC?

### Exercise 5: Writing Guardrails

A service has a 99.9% success ratio SLO, request latency p99 under a business threshold, and requires zero OOMKills.

Design alerts with short/long windows, minimum traffic conditions, along with how to tie in error budget and canary promotion gates.

### Exercise 6: Designing a Dashboard

Design panels for a JVM-backed HTTP API, including release/JDK metadata, error rate, route p95/p99, throughput, heap/non-heap, RSS/container memory, GC pause, CPU/throttling, threads, connection pools, and restarts.

Specify which metrics must be split by release version and which labels should not be used due to personal data or excessive cardinality.

### Exercise 7: Rollback Runbook

A Java 21 canary begins throwing `NoSuchMethodError` on the payment endpoint, while the Java 17 stable version continues running normally.

Define the rollout halt conditions, how to obtain class/JAR origin, when rollback is needed, and which data rollback risks must be checked.

## 32. Post-Release Monitoring Checklist

### Before Release

- [ ] Exact JDK vendor/version and before/after runtime flags are available.
- [ ] Artifact/image digest and dependency graph are recorded for traceability.
- [ ] Baseline error, latency, throughput, heap, RSS, and GC are saved.
- [ ] SLOs and regression guardrails are defined beforehand.
- [ ] Monitoring/tracing/logging have been verified in staging.
- [ ] Dashboards distinguish stable/canary by version.
- [ ] Peak/cold-start and critical functionality tests exist.
- [ ] Owners, incident channels, and rollback runbooks are in place.

### During Canary

- [ ] Sample count and traffic mix are sufficiently representative.
- [ ] Error rate and application-level failures are measured.
- [ ] p50/p95/p99 are tracked by route, not just average.
- [ ] CPU, throttling, queues, and downstream latency are reviewed.
- [ ] Heap, non-heap, process RSS, and container headroom are reviewed.
- [ ] GC pause distribution and allocation/live set are monitored.
- [ ] Restarts/crashes/OOMKills are classified by cause.
- [ ] The canary has actually exercised critical code paths.
- [ ] Each promote/hold step has a decision and evidence.

### After Full Rollout

- [ ] All instances are confirmed to run the intended version.
- [ ] Peak/off-peak periods and periodic jobs are monitored.
- [ ] Memory growth is observed over a sufficiently long timeframe.
- [ ] No abnormal warnings/linkage errors remain.
- [ ] Agents/JFR/serviceability continue operating per runbook.
- [ ] Log/JFR/heap-dump policies meet security requirements.
- [ ] Previous artifacts remain rollback-ready per policy.
- [ ] Data/schema rollback compatibility has been evaluated.
- [ ] Dashboards and alerts are updated for long-term operations.
- [ ] Migration report clearly documents results and remaining risks.

## Conclusion

**Monitoring errors, latency, memory, and GC behavior after release** is how a Java migration is verified under real user and system conditions, not merely through a successful build. A new JDK release is considered stable when it preserves SLOs, introduces no business regressions, uses resources within allowed headroom, and exhibits GC behavior suited to the workload.

Build a baseline before release, tag application/JDK information clearly in telemetry, use a canary to compare versions under comparable load, measure both tail latency and memory layers beyond the heap, and correlate GC/JFR/traces instead of guessing causes from a single isolated metric. When risks exceed thresholds, have rollback prepared; when all signals meet criteria over an appropriate observation window, traffic can be ramped and the migration completed with concrete evidence. This is the operational discipline that turns a JDK change into a measurable, explainable, and controlled decision.
