# JVM Memory Metrics: Measuring, Reading, and Investigating Memory in Spring Boot

> **Chapter:** Application metrics  
> **Lesson:** JVM memory metrics  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. Why monitor JVM memory?

A Spring Boot service sometimes runs stably for hours and then suddenly slows down, triggers frequent garbage collection (GC) cycles, or gets terminated by the OS/container due to out-of-memory errors. If we only track API response times, we know there is an incident, but we do not know whether the cause is heap pressure, Metaspace, direct buffers, or the container's memory limit.

**JVM memory metrics** are quantitative measurements that observe the memory usage state and trends of a Java process. When using **Spring Boot Actuator and Micrometer**, an application can expose meters such as `jvm.memory.used`, `jvm.memory.committed`, and `jvm.memory.max` without manually instrumenting every allocation.

Key questions to answer include:

- How many bytes is the heap using? Is it close to the configured heap budget?
- Does memory usage drop after GC, or does it steadily climb across cycles?
- Which pool is under pressure: Eden, Old Generation, Metaspace, or Code Cache?
- Do allocation rate and GC pressure correlate with p95 latency, 5xx errors, or timeouts?
- If the heap looks normal while the container is still OOMKilled, where else is memory residing?

In an observability system:

| Signal | Role when investigating memory |
| --- | --- |
| **Metrics** | Detect trends, heap usage ratios, pool distribution, allocation rate, and GC pause duration |
| **Logs** | Find `OutOfMemoryError`, GC logs, exceptions, and deployment events |
| **Traces** | Identify endpoints, batch jobs, or downstream paths coinciding with latency spikes |
| **Runtime/container telemetry** | Cross-check RAM limits, resident memory, OOMKills, and native allocator behavior |

The goal of this lesson is to **read semantics and units accurately**, build useful dashboards/alerts, and combine signals to investigate. A single high heap chart is not enough to conclude there is a memory leak.

## 2. JVM memory map: heap, non-heap, and native

The JVM manages multiple memory regions; what is measurable depends on the JVM, garbage collector, operating system, and attached libraries.

~~~mermaid
flowchart TD
    A["Java process memory"] --> B["JVM-managed Heap"]
    A --> C["JVM-managed Non-heap"]
    A --> D["Native / off-heap memory"]
    B --> E["Young generation: Eden, Survivor (GC-dependent)"]
    B --> F["Old generation / tenured region (GC-dependent)"]
    C --> G["Metaspace, class metadata"]
    C --> H["Code Cache, other pools"]
    D --> I["Direct buffers / mmap"]
    D --> J["Thread stacks, native libraries, GC/JIT structures"]
~~~

### 2.1. Heap

The **Heap** holds most Java objects created at runtime. It is managed by the garbage collector. For example, when an API loads a list of records, many temporary objects may be allocated and quickly reclaimed; heap used rises and falls with GC cycles.

With generational collectors, there are typically pools such as Eden, Survivor, and Old. However, **specific pool names are not standardized across all JVMs/GCs**. With G1 you may see IDs like `G1 Eden Space`, `G1 Survivor Space`, and `G1 Old Gen`; other collectors use different names and layouts.

### 2.2. Non-heap

**Non-heap** comprises several JVM-managed regions outside the Java heap, such as Metaspace and Code Cache. Loading too many classes, generating classes dynamically, or leaking classloaders can cause Metaspace to grow. Code Cache relates to JIT-compiled native code. These regions have different limits and allocation mechanics than the heap.

### 2.3. Native and container memory

A Java process also consumes memory outside JVM memory pools: direct byte buffers, thread stacks, native memory used by the JVM/GC, JNI libraries, memory mappings, and other OS components. **Total `jvm.memory.used` does not equal resident set size (RSS), nor does it equal container memory usage.**

For instance, `-Xmx1g` only caps the **maximum Java heap** at roughly 1 GiB; the process can still consume well over 1 GiB due to non-heap and native memory. Setting a container memory limit too close to `-Xmx` can therefore get the container OOMKilled even when the heap chart is below 100%.

## 3. Distinguishing used, committed, and max

Micrometer reads memory pool information from JVM management APIs and exposes them as meters. The three core quantities:

| Micrometer metric | Meaning | Interpretation |
| --- | --- | --- |
| `jvm.memory.used` | Bytes currently used in a memory pool at read time | Memory currently holding data as defined by the JVM |
| `jvm.memory.committed` | Bytes the JVM has committed for the pool | Memory the JVM has guaranteed is available to the pool |
| `jvm.memory.max` | Maximum size published by the JVM for the pool, if defined | Pool budget/limit, not current usage |

Under normal circumstances: `used ≤ committed` and `committed ≤ max` **when max is a finite limit and data is consistent**. However, some memory pools report an **undefined max** (e.g., `-1`), and some collectors manage pools dynamically, so you should not blindly use every pool's max as a valid denominator.

~~~text
Example of a heap pool at time T:
  used       = 600 MiB
  committed  = 768 MiB
  max        = 1024 MiB

  Used/committed = 78.125%
  Used/max       = 58.594%
~~~

The two ratios answer different questions:

- **Used/committed:** what portion of committed resources the pool is currently occupying.
- **Used/max:** what portion of the **published limit** the pool is occupying.

Even a high `used/max` ratio does not prove a memory leak: GC might not have run yet, the heap might intentionally hold a cache, or the collector might be optimizing to reduce collection frequency. Compare **post-GC trends**, allocation rate, GC pauses, load levels, and application behavior.

### 3.1. Byte units and conversion

Memory metrics usually use **bytes**. When displaying:

~~~text
MiB = bytes / 1024 / 1024
GiB = bytes / 1024 / 1024 / 1024
~~~

Do not confuse `MB` (decimal, 10^6 bytes) with `MiB` (binary, 2^20 bytes). In dashboards, choose and clearly label the unit so it can be accurately compared against `-Xmx` and container limits.

## 4. Common JVM memory metrics

The table below distinguishes core metrics, related metrics, and availability. The names listed before Prometheus export are **Micrometer names**, and depending on the version they may not appear in every application.

| Meter | Data | Things to note |
| --- | --- | --- |
| `jvm.memory.used` | Gauge of bytes currently used by `area` and `id` | Heap/nonheap, multiple pools |
| `jvm.memory.committed` | Gauge of committed bytes by pool | Not synonymous with physical container usage |
| `jvm.memory.max` | Gauge of pool limit when reported by JVM | May be undefined or unhelpful on some pools |
| `jvm.buffer.memory.used` | Buffer pool memory, e.g., direct/mapped | Complements visibility outside the Java heap |
| `jvm.buffer.count` | Number of buffers by type | Not the count of Java objects in the heap |
| `jvm.buffer.total.capacity` | Total buffer capacity | Not synonymous with resident memory |
| `jvm.gc.memory.allocated` | Bytes allocated, often exposed as a FunctionCounter | Use rate of increase to gauge allocation pressure when available |
| `jvm.gc.memory.promoted` | Bytes promoted to old generation when supported | GC/JVM dependent |
| `jvm.gc.pause` | Timer for GC pauses | Use count/sum or histogram depending on registry |
| `jvm.gc.live.data.size` | Estimated live data size after GC when supported | Not available on every GC/version |

Common labels:

- `area=heap` or `area=nonheap` distinguishes memory region types.
- `id` is typically the **JVM-provided memory pool name**, such as `G1 Old Gen` or `Metaspace`.
- For buffer metrics, labels may use `id=direct` or `id=mapped`.
- `application` can be a common tag configured by the application, whereas `instance` is typically attached by the Prometheus scrape target rather than by the application itself.

**Do not write alert rules based on series names you have not verified on the actual exporter.** Once you know your Spring Boot/Micrometer versions, inspect `/actuator/metrics` and `/actuator/prometheus` to confirm meter names, labels, and units.

## 5. How Spring Boot collects JVM memory metrics

Spring Boot Actuator integrates Micrometer `MeterRegistry`. When the relevant auto-configurations are active, Micrometer provides `JvmMemoryMetrics` and related binders to register JVM gauges into the registry.

~~~mermaid
flowchart LR
    A["JVM MemoryMXBean / MemoryPoolMXBean"] --> B["Micrometer JVM binders"]
    B --> C["Spring Boot MeterRegistry"]
    C --> D["Actuator /actuator/metrics"]
    C --> E["PrometheusMeterRegistry"]
    E --> F["/actuator/prometheus"]
    F --> G["Periodic Prometheus scrape"]
    G --> H["Grafana dashboard / alert"]
    H --> I["Correlate with logs, traces, and container metrics"]
~~~

Characteristics of this data pipeline:

1. A **Gauge** reads memory state at collection time; it does not count every `new` object allocation.
2. Micrometer uses **binders** to feed runtime info into `MeterRegistry`. Normally you do not need to write custom code to measure the heap manually.
3. `/actuator/metrics` lets you look up meters and tags at the Micrometer level; it is not the Prometheus scrape endpoint.
4. `/actuator/prometheus` exports metrics in Prometheus format if a Prometheus registry is present and the endpoint is exposed.
5. Prometheus samples at a **scrape interval**. A heap spike shorter than the scrape interval can be missed; GC occurring between two scrapes can also make charts look flatter than reality.

**Note on Observation:** `ObservationRegistry` coordinates observations for business operations, HTTP servers, or clients; `MeterRegistry` stores meters. JVM memory gauges are normally registered through binders rather than creating an `Observation` for each reading. Do not create an Observation on every heap read just to emit JVM metrics.

## 6. Configuring a Spring Boot project

The examples below use typical **Spring Boot 3.x** configuration. Projects on other versions must verify property namespaces, dependencies, and actual exporter output.

### 6.1. Maven dependencies

When the project uses the Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Actuator provides the instrumentation/management foundation. The Prometheus registry is required when scraping in Prometheus format; having Actuator alone does not mean `/actuator/prometheus` exists.

### 6.2. `application.yml` configuration

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
~~~

With this configuration:

- `/actuator/metrics` helps inspect meters like `jvm.memory.used`.
- `/actuator/prometheus` serves scrapes when `micrometer-registry-prometheus` is present.
- The common tag `application=order-service` differentiates services in the backend.

In production, restrict network access and authorization on management endpoints. You do not need to expose all Actuator endpoints publicly for Prometheus to work.

### 6.3. Verification walkthrough

1. Start the application, generate light traffic, and let the JVM load the required classes.
2. Query `/actuator/metrics` to verify `jvm.memory.used` is listed.
3. Query the detailed metric to inspect `measurements` and `availableTags`.
4. Inspect the Prometheus output and verify series names carrying the `_bytes` suffix.
5. Only after verifying the data should you build dashboards/alerts from the actual names and labels.

You do not need to deliberately trigger an `OutOfMemoryError` to learn the basic measurements. An endpoint or job allocating objects in a controlled manner in a test environment is sufficient to observe trends.

## 7. Reading data in Actuator

Assuming the application runs on `localhost:8080`:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:nonheap"
curl http://localhost:8080/actuator/prometheus
~~~

An `/actuator/metrics/jvm.memory.used` response may contain information similar to:

~~~json
{
  "name": "jvm.memory.used",
  "measurements": [
    { "statistic": "VALUE", "value": 315621376.0 }
  ],
  "availableTags": [
    { "tag": "area", "values": ["heap", "nonheap"] },
    { "tag": "id", "values": ["G1 Eden Space", "G1 Old Gen", "Metaspace"] }
  ]
}
~~~

This is **illustrative JSON**, not a fixed output. Which pools appear depends on the JVM and GC; `measurements` across multiple series may be aggregated by Actuator according to the filters provided. Therefore:

- When you want **heap used**, filter with `tag=area:heap`.
- When you want a specific pool, add `tag=id:<pool-name>` with a properly URL-encoded query string.
- For heap utilization ratios, read **used** and **max** with the exact same scope/labels. Never divide `used` of one pool by `max` of another pool.

If `jvm.memory.used` does not appear, check Actuator dependencies, endpoint exposure, whether JVM binders are enabled, and whether any configuration disables the meter. Do not build a manual gauge before identifying why auto-configuration is missing.

## 8. Reading Prometheus series and units

With the Prometheus registry, Micrometer meters are typically renamed to `snake_case` with the byte unit appended to the name:

~~~text
# Illustrative example; pool names and values are examples only
jvm_memory_used_bytes{area="heap",id="G1 Eden Space",application="order-service"} 1.6777216E8
jvm_memory_used_bytes{area="heap",id="G1 Old Gen",application="order-service"} 2.097152E8
jvm_memory_committed_bytes{area="heap",id="G1 Old Gen",application="order-service"} 4.194304E8
jvm_memory_max_bytes{area="heap",id="G1 Old Gen",application="order-service"} 1.073741824E9
~~~

These quantities are **gauges**, not counters. Values can rise or fall between scrapes. In particular, heap used usually drops after GC.

Notes when reading a series:

- `area="heap"`: pool belongs to the Java heap region.
- `id="G1 Old Gen"`: a G1 collector pool on a matching JVM. Take pool names from real output rather than hardcoding if you run across multiple collectors.
- `application="order-service"`: example Spring Boot common tag.
- `instance`: typically added when Prometheus attaches metadata to the scraped target.
- `_bytes`: value in bytes; divide by 1,048,576 to display MiB.

**A practical nuance:** the JVM may not report `max` for every pool. Undefined values may be represented by the exporter as negative numbers or missing useful series. Always filter or exclude invalid denominators when computing ratios.

## 9. PromQL: from usage to heap ratio

The queries below assume the series above have been verified at `/actuator/prometheus` and Prometheus has the appropriate `application`/`instance` labels.

### 9.1. Total heap used per instance, in MiB

~~~promql
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
) / 1024 / 1024
~~~

Heap memory pools are summed for the same target. This is total **heap used** measured across pools, not the process's resident memory.

### 9.2. Total non-heap used per instance, in MiB

~~~promql
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="nonheap"
  }
) / 1024 / 1024
~~~

Non-heap used helps observe Metaspace/Code Cache, though it also **does not include all native memory**.

### 9.3. Heap committed and heap max

~~~promql
sum by (application, instance) (
  jvm_memory_committed_bytes{
    application="order-service",
    area="heap"
  }
)
~~~

Across many collectors, summing `jvm_memory_max_bytes` across all pools **does not always yield the true heap limit**: a pool may report `max=-1` or pools may reflect limits in different ways. Before computing %heap, inspect the pools and identify a reliable denominator from your running JVM.

If your application's actual JVM/G1 setup confirms that **`G1 Old Gen` reports a valid max representing the heap limit**, an illustrative collector-specific query is:

~~~promql
100 *
sum by (application, instance) (
  jvm_memory_used_bytes{
    application="order-service",
    area="heap"
  }
)
/
max by (application, instance) (
  jvm_memory_max_bytes{
    application="order-service",
    area="heap",
    id="G1 Old Gen"
  } > 0
)
~~~

**This is not a universal cross-collector query.** For ZGC, Shenandoah, Parallel GC, or other deployments, inspect which pool reports a valid max or use a separately configured total heap max metric verified against `MemoryMXBean`/`-Xmx`. If the denominator is missing, the query may return no data; do not substitute 0% and assume the heap is safe.

### 9.4. Seeing which pool is growing

~~~promql
topk(
  5,
  jvm_memory_used_bytes{
    application="order-service"
  }
)
~~~

This returns the top 5 series by bytes used, potentially spanning multiple instances and both heap/nonheap. To compare **pools of a single instance**, add an `instance="..."` filter matching the actual label; for heap only, add `area="heap"`.

Do not apply `rate(jvm_memory_used_bytes[5m])` as if it were an allocation counter: `used` can drop after GC, so the difference between two readings does not equal the allocation rate.

## 10. GC metrics: understanding heap movement

Heap memory metrics only show **state**. To understand why the heap grows or why latency is high, you also need garbage collection data:

| Measurement group | Question | Interpretation hint |
| --- | --- | --- |
| Allocation | How fast is the JVM allocating objects? | Unusual increases may indicate heavy data processing or excessive object creation |
| Promotion | How many bytes survive long enough to move to old generation? | High promotion puts pressure on old gen |
| GC pause | What are the total duration and frequency of GC pauses? | Long or more frequent pauses can correlate with latency |
| Live data after GC | Is live data after major/appropriate GCs growing? | Worth investigating when sustained growth occurs, though not standalone proof of a leak |

When `jvm.gc.memory.allocated` is exposed as a counter in Prometheus, the series may be named `jvm_gc_memory_allocated_bytes_total`. Querying allocation rate:

~~~promql
sum by (application, instance) (
  rate(jvm_gc_memory_allocated_bytes_total{
    application="order-service"
  }[5m])
)
~~~

The result is typically **bytes/second**. However, Micrometer's allocation meter may be derived from GC/memory-pool data; it is not an exact counter of every single allocation on every collector. Verify series presence and behavior in your real environment.

For the GC pause timer, an illustrative query for **total pause seconds per observed second**:

~~~promql
sum by (application, instance) (
  rate(jvm_gc_pause_seconds_sum{
    application="order-service"
  }[5m])
)
~~~

If the result is `0.05`, it can be roughly interpreted as recorded pause time equaling 0.05 seconds per second (approximately 5% of time), **as defined by how the collector/metric records GC pauses**. Do not treat this as an exact measure of CPU usage or per-request overhead.

When you need pause count per second, use `jvm_gc_pause_seconds_count` with `rate()`. For p95 pause from a histogram, confirm the exporter provides the appropriate buckets; you cannot derive p95 from `_count` and `_sum`.

## 11. High heap: normal, memory pressure, or memory leak?

A "sawtooth" heap chart is usually a sign of the JVM allocating objects and GC reclaiming them:

~~~text
heap used
  ^
  |      /|       /|       /|
  |     / |      / |      / |
  |____/  |_____/  |_____/  |____> time
         GC       GC       GC
~~~

What matters is **whether the post-GC floor rises steadily across cycles**, not just the peaks. A heap reaching 85% before GC and dropping back to 35% after GC can be completely normal. Conversely, if live data after every full GC keeps rising under similar workloads, investigate retention or leaks.

| Symptom | Possible hypothesis | Cross-check data |
| --- | --- | --- |
| Heap used swings sharply but recovers well | Normal allocation/GC, possibly high allocation pressure | Allocation rate, GC pauses, throughput |
| Post-GC old generation climbs steadily | Bloated cache, retained references, memory leak, or workload holding more data | GC logs, live-data, heap dump when appropriate |
| Heap used near max with continuous GC | Memory pressure, risk of `OutOfMemoryError` | GC pauses, error logs, container/heap limits |
| Metaspace grows across reloads/deploys | Many classes/classloaders, possible classloader leak | Class loading metrics, heap/classloader analysis |
| Heap stable but container is OOMKilled | Native/direct memory, thread stacks, memory overhead, or limit too low | Container memory, RSS, buffer metrics, NMT if enabled |

A **memory leak** means the application retains data that is no longer needed, preventing GC from reclaiming it. Heap growing over time is a **symptom with multiple possible causes**. Confirming a leak requires deeper evidence: heap dumps, dominator trees, allocation profiling, or retention data gathered under safe operational procedures.

## 12. Distinguishing JVM memory from container memory

An application running in Kubernetes may be configured with:

~~~yaml
resources:
  requests:
    memory: "768Mi"
  limits:
    memory: "1536Mi"
~~~

The snippet above is an illustrative **container configuration**, not an Actuator configuration. If the JVM runs with `-Xmx1024m`, the heap limit is roughly 1 GiB, yet the process still needs RAM for Metaspace, thread stacks, direct buffers, native allocations, and overhead. Total container memory can approach 1.5 GiB even while `jvm.memory.used{area="heap"}` has not reached max.

Cross-check sources:

- **JVM heap/non-heap:** `jvm.memory.*` from Micrometer.
- **Buffer pools:** `jvm.buffer.*` if provided by binder and JVM.
- **Process RSS or resident memory:** OS/collector process metric, if available; not synonymous with heap.
- **Container/cgroup memory:** container/Kubernetes monitoring metrics; limits and accounting depend on the environment.
- **OOMKill events:** container/orchestrator status and related logs.

When a container is OOMKilled, do not rush to raise `-Xmx`: increasing max heap within the same memory limit can **leave even less room for native memory** and worsen the failure. Budget memory for the entire process and evaluate the root cause.

## 13. Foundational dashboard for JVM memory

A useful dashboard should focus on operational questions rather than dumping every meter onto one screen.

| Suggested panel | Data | Purpose |
| --- | --- | --- |
| Heap used / committed / limit | `jvm.memory.used/committed/max` | Track budget and trends |
| Heap pools | Heap `area`, `id` per instance | Identify which pool is under pressure |
| Non-heap pools | Metaspace, Code Cache... | Detect off-heap JVM pressure |
| Allocation rate | `jvm.gc.memory.allocated` if available | Track object creation rate |
| GC pauses | `jvm.gc.pause` count/sum (and buckets if present) | Recognize GC pressure |
| Process/container memory | RSS/cgroup metrics from appropriate source | Detect total budget exceedance |
| Request latency and errors | `http.server.requests` Timer and 5xx | Correlate JVM symptoms with user experience |

Note when placing panels side by side: metrics have **different units, scrape cadences, and aggregation methods**. Heap used is a point-in-time gauge; GC pause sum/counter requires `rate()` over a range; HTTP p95 requires histogram buckets or an appropriate distribution source.

### 13.1. Which labels should be kept?

Bounded labels like `application`, `instance`, `area`, `id`, and `region` are usually enough to slice JVM metrics by service, instance, and memory pool. Never attach `userId`, `orderId`, `requestId`, or real URLs as labels. JVM memory is shared across the process and has no one-to-one relationship with individual users or requests.

Even if a custom tag has low cardinality, adding it to every JVM meter multiplies series across all combinations. Only add common tags that are genuinely needed for dashboards and monitoring backend routing.

## 14. Alerting: avoid treating a single heap threshold as gospel

A "heap used > 90%" alert can be useful, yet it also produces many **false positives**: GC hasn't run yet, a pool has an unstable max, or the collector intentionally uses a wide heap to optimize throughput. Combine it with GC pressure, post-GC usage, latency, and container limits.

Example rule for a system where it is **verified** that the `G1 Old Gen` pool reports a max matching the heap limit:

~~~yaml
groups:
  - name: spring-boot-jvm-memory
    rules:
      - alert: HighJvmHeapUsage
        expr: |
          (
            sum by (application, instance) (
              jvm_memory_used_bytes{
                application="order-service",area="heap"
              }
            )
            /
            max by (application, instance) (
              jvm_memory_max_bytes{
                application="order-service",
                area="heap",
                id="G1 Old Gen"
              } > 0
            )
          ) > 0.90
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Sustained high JVM heap usage"
~~~

**Scope of this rule:** illustrative only for a verified pool/collector; do not copy verbatim for every JVM. Without valid max samples, the rule may fail to evaluate. Systems with strict SLOs may need alerts on GC pauses, OOMKills, memory headroom, or error-budget burn rate instead of occupancy alone.

Before applying:

1. Verify the metrics and labels exist in Prometheus.
2. Verify denominator accuracy for your exact collector/version/JVM flags.
3. Tune the `for` duration based on scrape interval and GC cycle; avoid paging on brief spikes.
4. Cross-check against allocation rate, GC pauses, post-GC old gen, and container memory.
5. Attach a runbook to the alert explaining triage steps and escalation thresholds.

## 15. Real-world incident investigation: rising p95 and climbing heap

**Context.** `order-service` runs 4 instances. After a release, p95 latency rises from 180 ms to 900 ms, and the 5xx rate climbs from 0.2% to 3%. Heap used charts on several instances climb rapidly, and GC pauses also increase.

### Step 1 — Triage symptoms

Examine the same time window:

- Did RPS and error rate rise together? If RPS stayed flat while heap/GC climbed, internal processing behavior may have changed.
- Which instances have rising `jvm_memory_used_bytes`, and which pool grew the most?
- Did `jvm_gc_pause_seconds_sum` and allocation rate increase at the same time?
- Does container memory still have headroom, or did OOMKills/restarts just occur?

### Step 2 — Form hypotheses

Testable hypotheses:

| Observation | Hypothesis | Evidence to look for |
| --- | --- | --- |
| Eden grows fast, frequent GC, recovers afterward | Excessive temporary object creation | Allocation profile, new workload, GC pauses |
| Old gen retains more data after GC | Cache/collection bloat, retained references | Heap dump or live-set analysis |
| Non-heap Metaspace grows | Continuous class/classloader generation | Class loading, classloader analysis |
| Heap stable, RSS/container memory rises | Direct/native memory or thread stacks | Buffer pools, thread count, NMT/container stats |
| CPU/GC normal but p95 rises | Downstream/DB/lock issue | Traces, connection pools, logs |

### Step 3 — Find the code path and root cause

Search logs for `OutOfMemoryError`, memory config changes, batch loads, and GC warnings if appropriate logging is enabled. Use tracing to see whether a slow request spends time in internal code, the database, or a downstream service. If trace sampling missed the relevant requests, reproduce in a test environment with an appropriate sampling policy.

**Do not put trace IDs or request IDs as tags on `jvm.memory.used`.** JVM metrics reflect process-wide state; correlate with requests using timestamps, instances, trace/span attributes, and log correlation.

### Step 4 — Verify after fixing

After fixing the code path that over-allocates objects or retains references, observe several GC cycles and representative traffic:

- Does post-GC heap used stabilize?
- Do allocation rate and GC pauses drop?
- Do p95/p99, 5xx, and throughput return to target levels?
- Are container RSS and restart/OOMKill counts under control?

A single drop after GC is an encouraging sign, not definitive proof the leak is gone. Observe long enough under the workload pattern that originally triggered the issue.

## 16. Common mistakes when reading JVM memory metrics

| Symptom | Possible cause | Appropriate check |
| --- | --- | --- |
| `/actuator/metrics/jvm.memory.used` returns 404 | Endpoint not exposed or JVM binder missing/disabled | Actuator dependency, management endpoints, metrics config |
| Metric exists in Actuator, missing in Prometheus | Missing Prometheus registry, endpoint, or scrape target | `/actuator/prometheus` and target status |
| `jvm_memory_max_bytes` is negative or missing | Pool does not publish a finite max | Check `area`/`id`, collector, `MemoryMXBean`, JVM flags |
| Heap ratio > 100% or negative | Incorrectly summing pool maxes, unit/instance mismatch, invalid max | Inspect individual pools and denominators |
| Heap near 100% yet app runs fine | GC hasn't triggered yet, collector keeps a generous heap | Check GC cadence and post-GC floor |
| Heap normal but OOMKilled | Native/direct memory, RSS, cgroup limit, or memory overhead | Container memory, RSS, `jvm.buffer.*` |
| No heap spike visible despite GC logs | Scrape interval missed short-lived spikes | Adjust resolution when appropriate; inspect GC metrics/logs |
| `rate(jvm_memory_used_bytes)` is negative or confusing | `jvm.memory.used` is a gauge that drops after GC | Read gauge directly; get allocation rate from GC counters |
| Pool names change after deploy | Changed JVM/collector/version | Avoid hardcoding pool names on multi-collector dashboards |
| Memory alerts are constantly noisy | Alerting on transient peaks, confusing max with workload | Add `for`, post-GC checks, and GC pressure |
| Chart summing heap across all instances misleads | Dashboard sums cluster while thresholds apply per JVM | `sum by (instance)` or filter specific targets |

A metric can be technically accurate yet **operationally misinterpreted**. Always tie the question being asked to clear units, denominators, and aggregation scope.

## 17. Hands-on verification with Spring Boot

The exercises below use a Spring Boot application with Actuator and the Prometheus registry.

### Exercise A — Explore and read data

1. Start the application, query `/actuator/metrics`, and locate `jvm.memory.used`, `jvm.memory.committed`, and `jvm.memory.max`.
2. Fetch `jvm.memory.used` with `area=heap` and `area=nonheap`. Record the list of `id` values from your running JVM.
3. Read `/actuator/prometheus` and locate `jvm_memory_used_bytes`, `jvm_memory_committed_bytes`, and `jvm_memory_max_bytes`.
4. Convert a byte value to MiB. Explain the difference between `used`, `committed`, and `max`.
5. Identify which pool reports an undefined `max` and explain why it must not be used as a ratio denominator.

### Exercise B — PromQL and dashboard

Design these panels:

- Heap used in MiB per `instance`.
- Non-heap used in MiB per `instance`.
- Heap pool breakdown by `id`.
- Allocation rate and GC pauses if the corresponding meters are available.
- HTTP error rate and latency on the same timeline.

Verify that charts do not sum across instances when the goal is alerting on a single JVM. If calculating %heap, explain where the denominator comes from and why it is valid for your collector.

### Exercise C — Controlled load simulation

In a test environment, run a task that allocates temporary objects in small batches and let GC manage them normally. Observe `jvm.memory.used` before, during, and after generating load. Do not intentionally cause an OOM or use massive payloads that disrupt shared systems.

Record:

1. How does `used` change over time?
2. After one or more GC cycles, does memory drop?
3. Do `committed` or `max` necessarily change at the same pace as `used`?
4. Does the scrape interval miss short peaks?
5. Can you conclude a memory leak from a `used` chart alone?

### Exercise D — Scenario analysis

A container has a 1.5 GiB limit, and the JVM is configured with `-Xmx1g`; heap used is around 600 MiB, yet the container is OOMKilled. List off-heap memory regions that could account for the remainder and the data sources to inspect. Explain why raising `-Xmx` to 1.3 GiB under the same container limit may be a poor decision.

### Self-check questions

1. Why is `jvm.memory.used` a Gauge instead of a Counter?
2. How do `used`, `committed`, and `max` differ?
3. Can total `jvm.memory.used` be treated as the Java process's RSS?
4. Why does heap used dropping right after GC not mean the metric was reset?
5. Which memory pools can vary by collector/version?
6. Why shouldn't you use `rate(jvm_memory_used_bytes)` to measure allocation rate?
7. Why does `jvm_memory_max_bytes` not always provide a valid positive denominator for total heap?
8. How do high pre-GC heap and high post-GC heap differ in meaning?
9. If there are 4 instances, is a cluster-wide sum appropriate for alerting on individual JVM heap usage?
10. What roles do metrics, logs, and traces play when analyzing errors caused by memory pressure?

**Completion criteria:** accurately explain used/committed/max; distinguish heap/non-heap and native/container limits; read Actuator/Prometheus and compute/justify usage ratios for the right collector; distinguish Gauge from Counter; and design a dashboard and investigation workflow combining GC, logs, and traces.

## 18. Key takeaways

- **JVM memory metrics** report the state of memory pools; `jvm.memory.used`, `committed`, and `max` have distinct meanings and limitations.
- **Heap, non-heap, native memory, and container memory are not identical.** `-Xmx` only caps the heap; budget must remain for everything else.
- `jvm.memory.used` is a **Gauge**, not a Counter. Do not use `rate()` on `used` as a substitute for allocation rate.
- **Max may be undefined per pool**; inspect `area/id` and your collector before building heap ratios or alerts.
- Combining JVM memory with allocation, GC pauses, process/container memory, and latency/error rates helps distinguish memory pressure, normal load, and leak indicators.
- Spring Boot Actuator + Micrometer provide JVM meters; Prometheus scrapes them to show trends. You do not need to create manual Observations for every heap read.
- Track bounded tags such as `application/instance/area/id`, avoiding per-request IDs; use logs/traces to connect memory symptoms to specific execution paths.

## References

- [Micrometer Reference — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Java SE — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Java SE — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Prometheus — Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
