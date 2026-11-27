# Garbage Collection Metrics

Within the **Application metrics** chapter of the **SPRING_BOOT_OBSERVABILITY** module, **garbage collection (GC) metrics** report how the Java Virtual Machine (JVM) is reclaiming memory and how that activity may affect application latency. When a Spring Boot API suddenly experiences a P95 spike or timeouts, GC metrics help answer: *are there more GC cycles than before, is each pause longer, or is the heap under increasing pressure?*

This module uses **Micrometer Observation, metrics, logs, and distributed tracing** to investigate errors, latency, and real-world application behavior. GC metrics belong to **application/runtime metrics**: they describe JVM health at an aggregate level. To determine why a specific request was slow, place GC metrics alongside HTTP latency, logs, traces, and other resource metrics. An unusual GC chart is evidence worth investigating, not standalone proof of the cause of every slow request.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain what GC is and distinguish **allocation**, **promotion**, **heap usage**, and **GC pause**.
2. Enable, read, and verify the JVM/GC metrics that Spring Boot Actuator commonly provides through Micrometer.
3. Recognize meters such as `jvm.gc.pause`, `jvm.memory.used`, and allocated/promoted metrics when supported by the JVM and binder.
4. Write PromQL queries to inspect **GC pauses per second**, **cumulative GC pause time**, **average pause**, and **P95 pause when histograms are enabled**.
5. Evaluate GC **per instance** rather than aggregating across multiple JVMs and misinterpreting the data.
6. Combine GC metrics with logs, tracing, CPU, heap, and connection pools to diagnose latency or errors.
7. Recognize limitations stemming from GC collectors, JVM versions, sampling, tags/cardinality, and exporters.

## 2. How does GC work in a Spring Boot application?

Java objects are allocated in memory managed by the JVM. When objects are no longer reachable, the garbage collector can reclaim their memory. Depending on the GC algorithm, some work runs concurrently with application threads, while certain phases require **stop-the-world (STW)**: application threads are paused for a period of time.

In a Spring Boot service handling HTTP traffic, a sufficiently long pause can inflate response times, especially if requests are executing on the paused JVM. However, high latency also has many other causes: database waits, connection pool exhaustion, retries, network delays, lock contention, or CPU saturation.

Concepts to distinguish:

| Concept | Meaning | Example question |
| --- | --- | --- |
| **Heap used** | Amount of JVM heap currently in use at measurement time. | Does heap keep rising after GC cycles? |
| **Heap committed/max** | Amount of heap the JVM has committed / can use per config. | Is the heap approaching its practical limit? |
| **Allocation** | Rate at which new objects are allocated. | Did allocation rate jump after deployment? |
| **Promotion** | Live data moved into the old generation in collectors with this concept. | Are too many objects surviving across GC cycles? |
| **GC count** | Number of times a type of GC event was observed. | How much did GC frequency increase? |
| **GC pause duration** | Duration of GC pause events recorded by the runtime/binder. | Is each pause long enough to impact SLOs? |
| **Live data size** | Estimated live data size after certain collections, if supported by the collector. | Is the surviving dataset growing abnormally? |

**Do not equate allocated bytes with heap used.** An application can allocate vast numbers of short-lived objects while heap used oscillates in a steady band because GC reclaims them. Conversely, rising post-GC heap may indicate a larger working set or increasing retained objects; deeper analysis is required before concluding a memory leak.

## 3. Where does Spring Boot get GC metrics?

A Spring Boot application with Actuator and Micrometer metrics is typically wired with JVM meter binders. JVM binders can use JVM management data (such as MXBeans and GC notifications) to publish appropriate measurements. Which metrics are actually present depends on **Java version, garbage collector, Micrometer version, binder enablement, and runtime**.

A typical collection flow:

~~~mermaid
flowchart LR
    JVM["JVM and garbage collector"] --> Binder["Micrometer JVM / GC meter binders"]
    Binder --> Registry["MeterRegistry"]
    Registry --> Actuator["Actuator /metrics"]
    Registry --> Exporter["Prometheus registry /prometheus"]
    Exporter --> Prom["Prometheus scrape"]
    Prom --> Dashboard["Dashboard, alerts, PromQL queries"]
    JVM --> GCLogs["GC logs / JFR if enabled separately"]
    App["Spring Boot requests"] --> Tracing["Micrometer Observation / tracing"]
    App --> Logs["Application logs"]
    Dashboard --> Correlation["Correlate GC with HTTP latency"]
    GCLogs --> Correlation
    Tracing --> Correlation
    Logs --> Correlation
~~~

GC metrics **do not necessarily originate from custom `Observation`s**. They are typically meters registered by a JVM binder. Therefore, even without explicitly calling `Observation.createNotStarted(...)`, the application can still emit `jvm.gc.pause` if the metrics infrastructure is configured and the JVM supplies the data.

**Key takeaway:** `MeterRegistry` collects measurements. `ObservationRegistry` manages the lifecycle of observed operations. Tracing bridges/exporters handle spans; the logging framework handles logs. Having GC metrics does not automatically mean tracing or detailed GC logs are configured.

## 4. Important metric names

In Actuator, Micrometer meter names typically use dot notation. In Prometheus, names are converted to underscore format and may carry unit/meter-type suffixes.

| Meter name in Micrometer/Actuator | What it measures | Notes |
| --- | --- | --- |
| `jvm.gc.pause` | Duration and count of detected GC pauses. | This is a `Timer`; usually the starting point when investigating pauses. |
| `jvm.memory.used` | Memory used by JVM region and pool. | Distinguish `area=heap` and `area=nonheap`. |
| `jvm.memory.committed` | Memory committed by region/pool. | Not synonymous with memory currently used. |
| `jvm.memory.max` | Memory limit published by the JVM for a region/pool. | Some regions may report an undefined limit. |
| `jvm.gc.memory.allocated` | Estimated bytes allocated, if supported by binder/collector. | A counter whose meaning depends on JVM memory region layout. |
| `jvm.gc.memory.promoted` | Bytes promoted, if supported by runtime. | Not every GC shares the same promotion concept. |
| `jvm.gc.live.data.size` | Estimated live data size after GC. | Availability and update timing depend on collector. |
| `jvm.gc.max.data.size` | Maximum data capacity info per binder/JVM. | Does not replace all heap max metrics. |

Allocated/promoted/live data metrics might not appear on a given JVM. Their absence is **not enough** to conclude Spring Boot is broken. Always start with the actual meter list at `/actuator/metrics`.

### What tags does GC pause have?

`jvm.gc.pause` usually has tags describing the event such as `action` and `cause`, depending on runtime and instrumentation version. For instance, an action may describe the completion of a GC phase and a cause may describe what triggered it.

Do not hardcode a specific `action` or `cause` value in dashboards before inspecting real data: names and value sets differ across G1, ZGC, Shenandoah, and different JVMs. When comparing over time, remember that switching GC algorithms can change tags and observed event types.

## 5. Actuator and Prometheus configuration

Example **Spring Boot 3.x, Java 17+** application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
~~~

The Spring Boot BOM should manage Micrometer versions compatible with your Spring Boot version. In most cases, there is no need to manually register a second GC binder when auto-configuration already provides JVM metrics.

Example `application.yml` for a test environment:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

This configuration exposes metrics via Actuator and the Prometheus registry when appropriate auto-configuration conditions are met. **It does not automatically install or start a Prometheus server.** You must configure Prometheus to scrape the endpoint and ensure the application is reachable at the right port and path.

Verifying while the application is running:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.gc.pause
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/prometheus
~~~

Verify in sequence:

1. Does `/actuator/metrics` list `jvm.gc.pause`?
2. What measurements and available tags appear in `/actuator/metrics/jvm.gc.pause`?
3. What `jvm_gc_...` series appear in `/actuator/prometheus`?
4. Is the Prometheus scrape target healthy and applying the right instance-identifying labels?
5. When the application generates load, do GC pause count and sum change as expected?

Never put heavy heap pressure on production just to "force" GC to appear. In a dedicated test environment, use traffic or a bounded object-allocation routine to observe controlled changes.

### Securing endpoints

`/actuator/metrics` and `/actuator/prometheus` expose operational details of the application. Expose them only to monitoring systems and authorized users via security/network policies or a dedicated management port. Management endpoints should never be left arbitrarily open to the Internet.

## 6. Reading basic GC pause charts

For a `Timer` like `jvm.gc.pause`, the Prometheus registry typically exports count and sum in seconds, for example:

~~~text
jvm_gc_pause_seconds_count{application="order-api",action="...",cause="..."} 75
jvm_gc_pause_seconds_sum{application="order-api",action="...",cause="..."} 2.84
~~~

These are **illustrative figures**, not measurements from a live application. `count=75` means 75 pause events were recorded by the meter since the series started; `sum=2.84` corresponds to 2.84 total seconds. Do not infer that 75 GCs occurred in the past minute without calculating the increase over a time window.

Suppose Prometheus has `job="order-api"` and `instance` identifying a JVM/process. Adjust labels in the examples below to match your real data.

### 6.1 GC pause frequency per second

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{job="order-api"}[5m])
)
~~~

This gives **recorded pause events per second**, averaged over a five-minute window. Multiply by 60 to estimate events per minute. One pause event does not necessarily equal a full GC cycle, especially for multi-phase collectors. Do not call this metric "full GC count" unless the tags actually prove it.

### 6.2 Cumulative GC pause time per second

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
~~~

Since the numerator is in pause seconds and `rate` divides by wall-clock seconds, the unit is **pause seconds per wall-clock second**. If the value is roughly `0.02`, it can be read as approximately 2% of measured time spent in recorded GC pauses during that window.

To express as a percentage:

~~~promql
100 *
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
~~~

This is an estimate based on pause events recorded by the binder. **Do not assume this is the percentage of CPU consumed by all GC activity**, nor claim it captures all concurrent phases of G1/ZGC/Shenandoah.

### 6.3 Average pause duration

~~~promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{job="order-api"}[5m])
)
/
sum by (instance) (
  rate(jvm_gc_pause_seconds_count{job="order-api"}[5m])
)
~~~

The result is in **seconds per pause event**. For example, `0.035` corresponds to a 35 ms average. If no GC pause occurred in the window, the denominator may be zero, yielding empty or undefined results. Dashboards and alerts must handle this case.

**Average does not replace P95/P99.** A handful of very long pauses can still cause timeouts even when the mean pause remains low. Measuring GC pause tail latency requires histograms or detailed event telemetry.

## 7. P95 GC pause and histograms

Histograms can be configured for the `jvm.gc.pause` timer in an environment verified to support Micrometer/registry distribution configuration:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        jvm.gc.pause: true
~~~

When the registry exports histogram buckets, Prometheus may expose `jvm_gc_pause_seconds_bucket`. Example P95 query:

~~~promql
histogram_quantile(
  0.95,
  sum by (instance, le) (
    rate(jvm_gc_pause_seconds_bucket{job="order-api"}[5m])
  )
)
~~~

The result is the **estimated P95 duration of recorded pauses**, not P95 HTTP request latency. Nor does it mean 95% of **application uptime** was unaffected by GC: the statistical sample here is **GC events**, not HTTP requests.

If `_bucket` is missing, the P95 query above returns nothing. Verify that histogram configuration took effect, events occurred in the runtime, and the Prometheus endpoint actually emits bucket series.

**Cost:** adding buckets multiplies time series across tag combinations; do not enable histograms on every meter just in case you want P95. Weigh SLOs and actual investigation needs before increasing granularity.

## 8. Heap, allocation, promotion, and live data

GC pauses are only half the story. To understand **why** GC behavior changed, examine memory and allocation rates.

### 8.1 Heap usage

Common series from the Prometheus registry:

~~~text
jvm_memory_used_bytes{area="heap",id="..."} ...
jvm_memory_committed_bytes{area="heap",id="..."} ...
jvm_memory_max_bytes{area="heap",id="..."} ...
~~~

`id` typically represents the memory pool name, which varies across collectors. Observe actual names and labels; do not assume every JVM has `Eden Space`, `Old Gen`, or the same number of pools.

To view total heap usage per JVM when pool data is complete and consistent:

~~~promql
sum by (instance) (
  jvm_memory_used_bytes{job="order-api",area="heap"}
)
~~~

To calculate heap used ratio relative to limits, only use regions with valid, consistent max values; some pools report undefined limits. You can use a global heap max metric provided by your observability stack or inspect pools before dividing. **Never blindly sum `max=-1` values** and treat that as real heap capacity.

Heap used typically forms a sawtooth curve: allocations raise memory, GC reclaims it. After a GC cycle, heap used does not necessarily return to the exact same floor because working sets, caches, and collector behavior evolve.

### 8.2 Allocation rate

If the binder/collector supports `jvm.gc.memory.allocated` and the exporter emits a byte counter, a series similar to this may exist:

~~~text
jvm_gc_memory_allocated_bytes_total{job="order-api"} ...
~~~

PromQL example **applicable only when the actual series name exists**:

~~~promql
sum by (instance) (
  rate(jvm_gc_memory_allocated_bytes_total{job="order-api"}[5m])
)
~~~

The result is in **bytes/second**. A rising allocation rate after deployment may point to a code path creating more short-lived objects than before. However, how the binder estimates allocation depends on JVM/GC, so it is not an absolute count of every object allocation.

### 8.3 Promotion and live data

Promoted bytes or live data size metrics provide additional signals about long-lived objects. For example, a release that raises both allocation rate and promoted bytes may make GC phases work harder. However:

- **Promotion** is a GC-algorithm-dependent concept; you cannot assume every collector reports identical figures.
- **Live data size** is measured at specific points/phases, not a full snapshot of all live objects at every instant.
- Higher live data can also reflect cache warmup, increased traffic, or legitimate working-set growth.

If you suspect a memory leak, track **post-GC** growth over a sufficiently long window under comparable load, and use heap dumps, allocation profilers, or Java Flight Recorder in appropriate environments. Never conclude a leak from a few minutes of rising heap used alone.

## 9. How the collector shapes data interpretation

No single metrics model reflects every garbage collector identically.

| Collector/situation | What to note | Caution when concluding |
| --- | --- | --- |
| **G1 GC** | Has young/mixed pauses, with substantial phased work. | Longer pause duration does not automatically prove full GC. |
| **ZGC/Shenandoah** | Much of the work runs concurrently with the application. | GC CPU work and latency impact cannot be inferred solely from STW pause sum. |
| **JDK/collector changed after deploy** | Pool names, cause/action tags, and semantics may change. | Old dashboards may misfilter or miss series. |
| **App near heap limit** | GC may run more frequently, reducing throughput. | Check allocation, retained data, container memory, and OOM together. |
| **No GC events in window** | Timer does not increment; query rate is 0. | Does not mean Micrometer is broken. |

JVMs may run with different settings between local and production environments. When dashboards shift abruptly after a Java upgrade or GC change, re-verify meter meanings and tags rather than blindly comparing curves against the previous version.

## 10. Correlating GC metrics with HTTP latency

To test the hypothesis "GC is slowing down the API," align charts on **the same time range and the same instance**:

1. P95/P99 latency of the affected HTTP server route.
2. Error rate and request throughput.
3. GC pause count, pause sum rate, and pause histogram/P95 if available.
4. Heap used/committed/max, allocation rate, and available promoted/live data signals.
5. Process CPU, JVM threads, connection pools, downstream latency, and queue lengths.

Simulated example:

| Time window | HTTP P95 | Mean GC pause | GC pause time/s | Process CPU |
| --- | ---: | ---: | ---: | ---: |
| 10:00–10:05 | 180 ms | 15 ms | 0.006 s/s | 32% |
| 10:05–10:10 | 1,100 ms | 210 ms | 0.12 s/s | 78% |
| 10:10–10:15 | 900 ms | 160 ms | 0.09 s/s | 71% |

**The figures in this table are purely hypothetical.** They show GC pauses and latency rising together, yet do not prove GC is the sole cause. Rising traffic/allocations could drive both GC pressure and downstream load, or CPU saturation could stretch wait times.

When requests span multiple instances, **do not aggregate across all JVMs before checking anomalous instances**. One JVM under memory pressure can inflate tail latency while the cluster-wide average still looks normal.

### Distinguishing time-series metrics from a single trace

If the trace backend shows a 1.2-second HTTP span coinciding with a 300 ms GC pause, that makes the GC-induced latency hypothesis worth examining. However, a tracing span includes thread waiting, scheduling, network, and dependencies; it does not automatically label how much time was GC pause.

To strengthen the hypothesis, cross-check GC logs/JFR with matching timestamps, multiple slow traces at the same time on the exact same instance, and latency/CPU data. **Trace IDs are not embedded inside JVM-wide GC events**: GC is normally a runtime event affecting many threads, not a child span of one request.

## 11. What do GC logs and Java Flight Recorder add?

Metrics are great for dashboards and alerts; to inspect an individual GC cycle in detail, you may need **GC unified logging** or **Java Flight Recorder (JFR)** as provided by the JVM.

Java 17 example enabling GC logging in a test environment:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Ensure the file path has write permissions and sufficient disk space, rotation/retention policies, and assess operational impact. In containers, stdout or an appropriate log collection pipeline may be preferable to uncollected local files.

GC logs reveal pause types, causes, detailed memory stats, and precise timestamps. JFR captures rich JVM events for latency and allocation analysis. Use tools compatible with your Java version and account for storage and overhead costs.

**Note on timestamps:** Prometheus dashboards use scrape timestamps; logs/JFR use their own clocks. Synchronize clocks, timezones, and uptime conversions as needed to avoid misinterpreting whether two events occurred simultaneously.

### Logs and tracing correlation

Application logs can include `traceId` and `spanId` via Micrometer Tracing/MDC, allowing you to open the trace of an errored request. Standard GC logs lack request IDs because GC is JVM-wide. The investigation path is:

~~~text
HTTP latency alert
   -> GC metrics by instance + time window
   -> GC logs/JFR for the matching JVM and timestamp
   -> application logs containing traceId
   -> distributed trace of the affected request
   -> verify hypothesis across multiple data sources
~~~

This correlates **signals by timestamp and instance**, rather than turning every GC event into a per-request span.

## 12. Sampling, exporters, and tags/cardinality

### Trace sampling does not change how GC metrics work

GC metrics are normally registered into `MeterRegistry` by meter binders. If tracing keeps only 10% of requests via sampling, GC metrics **do not drop to 10%**. An unsampled request can still experience a GC pause; JVM metrics continue accumulating via their own mechanism.

Therefore, when HTTP P95 and GC metrics show data but you cannot find a trace for a failed request, check the tracing sampler, exporter, collector, backend, and context propagation. Do not blame the GC binder merely because a trace is absent.

### Metrics exporters must be working

The Prometheus registry produces data for the Prometheus server to scrape. If scraping fails, dashboards receive no new points even though the application keeps recording metrics in-process. Check `/actuator/prometheus`, target status, network, authentication, port, and `job`/`instance` labels. If the application restarts, counters/timers can reset; PromQL functions like `rate()` are designed to handle counter resets under proper conditions.

### Tags must have bounded cardinality

Useful tags may include collector action/cause, application, environment, or instance. However, never add `requestId`, `userId`, `orderId`, timestamps, or raw URLs to GC metric tags. GC is a **JVM-wide** phenomenon not owned by a specific request ID; attaching per-request IDs to GC metrics is both semantically wrong and explodes cardinality.

Filtering too strictly on `cause` or `action` can drop data after a JVM/collector upgrade. Observe real cardinality before adding new dimensions to dashboards.

## 13. Runbook for investigating GC-related latency

When a latency spike alert fires, follow this procedure:

1. **Locate the incident:** record service, environment, instance/pod, timestamp, JVM version, GC algorithm, and deployed version.
2. **Check HTTP metrics:** which route/method saw rising P95/P99 or 5xx? Did traffic rise? One instance or the whole cluster?
3. **Check GC metrics:** pause count, pause sum rate, average duration, and histogram if available. Inspect per instance.
4. **Check heap and allocation:** is post-GC heap climbing? How did allocation/promotion change? Is usage near container/JVM memory limits?
5. **Check CPU and other resources:** thread counts, CPU, queues, connection pools, dependency latency. Avoid overlooking non-GC bottlenecks.
6. **Cross-check GC logs/JFR:** find GC phases and long events matching the time window. Watch for timestamp alignment and collector-specific tags/causes.
7. **Cross-check application logs/traces:** do slow requests on the same instance show matching wait gaps? Are there retries, timeouts, or slow dependencies?
8. **Test hypotheses in an appropriate environment:** evaluate allocations, object retention, heap sizing, caches, or workload; never tweak GC flags blindly.
9. **Verify after remediation:** compare latency, error rate, GC pressure, and traffic over a sufficiently long window; document changes.
10. **Update dashboards/alerts:** refine thresholds and note collector/version details, keeping metrics meaningful for triage.

An action like raising `-Xmx` can ease heap pressure in some cases, yet it can also delay leak detection or enlarge container memory footprint. Base decisions on evidence rather than treating heap expansion as the default fix.

## 14. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `/actuator/metrics/jvm.gc.pause` has no data | No GC events recorded yet; binder/config/runtime differs from expectation. | Check meter list, JVM, collector, and generate controlled test traffic. |
| Metrics exist in Actuator, missing in Prometheus | Registry/export endpoint or scrape target misconfigured. | Inspect `/actuator/prometheus`, target health, permissions, and labels. |
| GC count rises, HTTP latency does not | Pauses are short or off the critical request path. | Compare pause duration and HTTP latency by instance/time window. |
| HTTP latency rises, GC pause stays flat | Bottleneck in dependency, lock, queue, network, or concurrent GC work not captured in pause metric. | Cross-check traces, connection pools, CPU, and runtime logs. |
| Pause P95 is empty | Missing histogram buckets or wrong label in query. | Check `jvm_gc_pause_seconds_bucket` and distribution configuration. |
| Query wrongly merges two JVMs | Missing group by `instance` or wrong job/namespace. | Add filters and verify process-identifying labels. |
| Allocation/promoted/live data metrics missing | Collector or JDK/Micrometer binder does not expose them. | Check real meter names; use heap/GC logs/JFR instead when needed. |
| Heap used climbs continuously | Traffic growth, cache warmup, retained objects, or leak. | Compare post-GC floor, allocation, working set, and heap dump/JFR. |
| Charts shift after Java upgrade | Collector, pool IDs, tag values, or binder semantics changed. | Verify new metrics/labels before comparing across versions. |
| GC metrics exist, trace missing for slow request | Sampling, exporter, context propagation, or instrumentation. | Debug tracing pipeline independently of JVM metrics. |

## 15. Self-check exercises

### Exercise 1: What do count and sum mean?

Over five minutes, `jvm_gc_pause_seconds_count` increased by 20 and `jvm_gc_pause_seconds_sum` increased by 1 second. What is the average pause duration?

**Answer:** Roughly `1 / 20 = 0.05` seconds, or **50 ms per pause**. This is an average; a few much longer pauses could still exist. Histograms, logs, or JFR are needed to evaluate percentiles and outlier pauses.

### Exercise 2: Is it a memory leak?

Heap used rose from 40% to 70% in ten minutes after deploy, while traffic also tripled. Can you conclude there is a memory leak?

**Answer:** No. You must examine working set, post-GC live memory, allocation, caches, and trends over a sufficiently long window. Steadily rising post-GC heap under comparable load is a much stronger signal to investigate, though still not standalone proof.

### Exercise 3: Is GC P95 comparable to HTTP P95?

A dashboard shows GC pause P95 is 80 ms and HTTP request P95 is 800 ms. Can you deduce the remaining 720 ms is database time?

**Answer:** No. Those two percentiles measure **two different sets of events**. You cannot subtract them to infer dependency time. You need traces, logs, client metrics, and downstream telemetry.

### Exercise 4: Why are there metrics without traces?

An application records hundreds of GC pauses in metrics, yet only a few HTTP traces are stored. Does that mean tracing lost GC spans?

**Answer:** No. The GC binder normally emits JVM-wide metrics, not a separate span for each GC event inside request traces. Few traces can also be due to sampling. To investigate GC in detail, use GC logs/JFR and correlate by time with request traces.

### Exercise 5: Percentiles across multiple instances

A dashboard averages P95 GC pauses from three JVMs. Is that the cluster-wide P95 pause?

**Answer:** No. Percentiles cannot be aggregated by simple averaging. When you need P95 across the entire pause set and have compatible histogram buckets, sum the bucket counts/rates properly before applying `histogram_quantile`. During incident diagnosis, keep **per-instance** charts to spot an individual unhealthy JVM.

## 16. GC metrics operational checklist

- [ ] Actuator and the appropriate registry implementation are added to the Spring Boot application.
- [ ] Real meter names and labels are verified at `/actuator/metrics` and `/actuator/prometheus`.
- [ ] An active Prometheus scrape target is configured and management endpoints are secured.
- [ ] Dashboards include GC pause count, total pause time, and key heap memory metrics.
- [ ] GC pause histograms are enabled selectively when P95/P99 is needed; bucket series presence is verified.
- [ ] Monitoring is broken down per JVM/instance; collector, Java version, and pool name changes are accounted for.
- [ ] Allocation, promotion, and live data are used only when genuinely supported by the runtime.
- [ ] Request IDs, user IDs, or sensitive data are never attached as GC metric labels.
- [ ] GC metrics can be correlated with HTTP latency, CPU, connection pools, logs, and traces.
- [ ] Team understands trace sampling does not alter JVM-wide GC measurements.
- [ ] A mechanism to enable and collect GC logs/JFR is ready for deeper diagnosis.
- [ ] After changes, metrics are compared under equivalent workload or normalized for traffic.

**Remember:** **Garbage collection metrics** reveal memory management health and JVM-recorded pauses, but they are only one piece of the Spring Boot latency picture. Start with `jvm.gc.pause` and `jvm.memory.used`, expand to allocation/promotion when available, correlate by the same instance and time window with HTTP metrics, logs, and traces, and then use GC logs or JFR to verify the root cause before tuning JVM flags.
