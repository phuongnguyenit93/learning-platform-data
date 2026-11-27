# JVM Dashboard for Spring Boot

A JVM dashboard gives operations teams visibility into the runtime health of a Spring Boot application across heap/non-heap memory, garbage collection, threads, CPU, class loading, and buffer pools. These metrics complement HTTP metrics, logs, and distributed traces: when latency increases, the JVM dashboard helps determine whether the application is experiencing memory pressure, GC pauses, thread saturation, or CPU throttling. A good dashboard must answer concrete operational questions, use consistent units and labels, and avoid turning every JVM metric into a contextless chart.

In the **SPRING_BOOT_OBSERVABILITY** module, the JVM dashboard uses Micrometer and Spring Boot Actuator data to present runtime status over time. This lesson belongs to the **Dashboard and Alert** chapter and focuses on JVM dashboard design: metric sources, memory pools, GC, threads, CPU, class loading, buffer pools, PromQL, labels/cardinality, panel layout, alert signals, validation, and investigation workflows.

## Learning Objectives

1. Identify JVM metrics exposed by Spring Boot/Micrometer.
2. Distinguish heap, non-heap, memory pools, and buffer pools.
3. Read GC count, pause duration, and allocation pressure.
4. Monitor live/daemon/peak threads and thread states.
5. Combine process/system CPU with container CPU limits.
6. Design panels for class loading and direct buffers.
7. Write PromQL with appropriate aggregations and labels.
8. Avoid high cardinality and misleading dashboards.
9. Build symptom-based alerts and investigate using correlated signals.

## 1. Sources of JVM Metrics in Spring Boot

When Actuator and a Micrometer registry are configured, Spring Boot can auto-register JVM binders. Commonly encountered meters include:
- jvm.memory.used, jvm.memory.committed, jvm.memory.max;
- jvm.gc.pause;
- jvm.threads.live, jvm.threads.daemon, jvm.threads.peak, jvm.threads.states;
- jvm.classes.loaded, jvm.classes.unloaded;
- process.cpu.usage, system.cpu.usage;
- process.uptime, process.start.time;
- jvm.buffer.memory.used, jvm.buffer.count.

Exact meter names and tags depend on Micrometer, JVM, and registry versions. Inspect `/actuator/metrics` and `/actuator/prometheus` in a live runtime before authoring dashboards. A single meter may be exported as multiple Prometheus series with `_sum`, `_count`, `_max` suffixes or histogram buckets.

### 1.1. Enable Actuator and the Prometheus Registry

Example dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Example exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    prometheus:
      access: read-only
~~~

Endpoint access configuration varies across Spring Boot versions. Only expose the Prometheus endpoint on networks accessible to the monitoring server and protect management endpoints according to organizational policy.

### 1.2. Verify Meters Before Building Panels

Call:

~~~http
GET /actuator/metrics/jvm.memory.used
GET /actuator/metrics/jvm.gc.pause
GET /actuator/prometheus
~~~

Verify the meter has data, tag keys, and units. If a metric does not appear, check registry dependencies, binder configuration, endpoint exposure, and runtime support before editing dashboards.

## 2. Dashboard Layout Design

The dashboard should be ordered from overview to root cause:

~~~text
JVM overview
  ├─ Runtime identity: service, instance, version, uptime
  ├─ Memory: heap used/max, non-heap, pools, direct buffers
  ├─ GC: pause rate, pause duration, collection activity
  ├─ Threads: live/daemon/peak, state distribution
  ├─ CPU: process CPU, system CPU, container throttling
  └─ Class loading: loaded/unloaded classes

Related context
  ├─ HTTP request rate, errors, latency
  ├─ Executor queue and active threads
  ├─ Hikari connection pool
  └─ Logs and traces for the same time window
~~~

An overview dashboard does not need to display every meter. Choose panels that can surface symptoms and lead into specialized dashboards or trace investigations.

### 2.1. Variables and Dashboard Filters

Useful variables:
- service: stable service name;
- environment: deployment environment;
- instance or pod: instance to drill down into;
- namespace/cluster: infrastructure scope;
- version: application version.

Use service/environment as default filters. Allow selecting an instance to locate an outlier pod. Do not create variables from user IDs, request IDs, or high-cardinality values.

## 3. Heap Memory

The heap is the memory region the JVM uses for object allocation. Rising heap usage can reflect normal workload, allocation bursts, cache growth, or a memory leak. You need to look at used, committed, and max together.

| Metric | Meaning |
| --- | --- |
| jvm.memory.used | Memory currently used in the pool |
| jvm.memory.committed | Memory committed by the JVM |
| jvm.memory.max | Pool limit if provided by the JVM |
| jvm.memory.usage | Usage ratio if exposed by the binder/registry |

Do not mechanically sum all pool maxes if some pools have undefined max or if memory pool lifecycles change. Distinguish heap pools such as Eden, Survivor, and Old Gen depending on collector/JVM.

### 3.1. Heap utilization

A panel can express the ratio:

\[
\text{heap utilization} =
\frac{\sum \text{heap used}}{\sum \text{heap max}} \times 100
\]

Example PromQL if the series has an `area` label:

~~~promql
100 *
sum by (service, instance) (
  jvm_memory_used_bytes{area="heap"}
)
/
sum by (service, instance) (
  jvm_memory_max_bytes{area="heap", id=~".+"}
)
~~~

This is an illustrative query. Label/series names depend on Prometheus naming conventions and Micrometer versions. Some pools have an undefined max; filter/adjust to avoid skewed ratios. Verify actual series before using.

### 3.2. Used vs. committed

High heap used while committed is still below max may cause the JVM to expand committed memory. High heap committed does not mean all of that memory is in use. When investigating, examine both absolute bytes and ratios, along with GC pauses and allocation behavior.

### 3.3. Old generation and leak signals

Old Gen creeping upward across multiple GC cycles without dropping significantly can signal retained objects, unbounded caches, or a leak. A single snapshot is not enough to draw conclusions. Observe post-GC trends under similar load over hours/days; only capture heap dumps following controlled procedures since they can induce pauses and contain sensitive data.

## 4. Non-Heap and Metaspace

Non-heap includes regions such as Metaspace and Code Cache, depending on the JVM. Metaspace holds class metadata; continuous growth may relate to classloader leaks, dynamic proxies, or redeploy behavior. Code Cache stores compiled code.

Panels should display used/committed per pool and alert based on trends/actual runtime limits. `jvm.memory.max` may be undefined for some non-heap pools; do not divide by invalid values.

## 5. Garbage Collection

GC metrics help distinguish allocation pressure from pause behavior. Micrometer typically provides `jvm.gc.pause` with duration and tags describing action/cause depending on the JVM.

### 5.1. GC pause rate

With the Prometheus timer export, you can observe pause frequency:

~~~promql
sum by (service, instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
~~~

### 5.2. GC pause duration

p95 from histogram buckets if histograms are enabled:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, instance) (
    rate(jvm_gc_pause_seconds_bucket[5m])
  )
)
~~~

If histogram buckets are not exported, do not use this query; check `_sum`/`_count` and histogram configuration first. Average pause can be calculated from rate sum / rate count, though it does not replace p95/p99.

~~~promql
sum by (service, instance) (rate(jvm_gc_pause_seconds_sum[5m]))
/
sum by (service, instance) (rate(jvm_gc_pause_seconds_count[5m]))
~~~

### 5.3. Interpreting GC properly

Increasing GC count is not necessarily a problem; examine pause duration, throughput, heap trend, and request latency. A collector with many short pauses may be operating normally. Alerts based solely on GC count are often noisy.

## 6. Threads and Thread States

Threads indicate concurrency levels and potential pool stalls. Common meters:
- live threads;
- daemon threads;
- peak threads;
- thread states: NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED depending on the binder.

### 6.1. Live and peak threads

~~~promql
jvm_threads_live_threads
~~~

The panel displays live threads per instance and peak threads if the series is present. Continuous growth can point to a thread leak, tasks spawning unbounded threads, or an unmanaged executor pool.

### 6.2. Thread state distribution

~~~promql
sum by (service, instance, state) (
  jvm_threads_states_threads
)
~~~

A high proportion of BLOCKED or WAITING threads does not automatically prove a deadlock. Compare against baseline and inspect thread dumps when there are signs of elevated request latency, executor queue backlogs, or lock contention.

### 6.3. Combining with executor metrics

JVM thread count should be read alongside executor active threads, pool size, queue depth, and rejected tasks. Stable thread count with a growing queue may mean workers are blocked or throughput is low. Avoid merely increasing max pool size without checking downstream capacity.

## 7. CPU and Container Limits

Process CPU and system CPU answer two different questions:
- process CPU usage: the fraction of CPU used by the process as defined by the binder;
- system CPU usage: overall CPU usage of the host/runtime environment.

~~~promql
process_cpu_usage
~~~

~~~promql
system_cpu_usage
~~~

Values are usually a 0..1 ratio, though you should verify the meter's unit and semantics in your version/runtime. With containers, cross-check CPU usage against CPU limits, throttling, and node pressure from container/platform metrics. These metrics do not necessarily come from the Micrometer JVM binder.

### 7.1. CPU throttling

Kubernetes CPU limits can throttle a container even when the node still has spare CPU. A JVM dashboard should link panels with container CPU usage/throttling metrics from cAdvisor/kubelet or a platform exporter. These metrics do not necessarily originate from Micrometer.

### 7.2. CPU and latency

If CPU rises alongside request latency, check thread states, GC pauses, and allocation. If CPU is low while latency rises, check dependency spans, connection pools, locks, or thread pools.

## 8. Class Loading and Buffer Pools

### 8.1. Class loading

`jvm.classes.loaded` tracks currently loaded classes; `jvm.classes.unloaded` is a counter of class unload events depending on the binder. Loaded classes increasing during startup is normal. Continuous growth after warm-up may suggest dynamic class generation or a classloader leak.

~~~promql
jvm_classes_loaded_classes
~~~

~~~promql
rate(jvm_classes_unloaded_classes_total[10m])
~~~

Prometheus series names may vary by version; verify scrape output.

### 8.2. Direct and mapped buffers

NIO buffer pools can consume native memory outside the heap. Monitor `jvm.buffer.memory.used` and `jvm.buffer.count` by pool. Stable heap alongside growing direct buffers can cause native memory pressure. Read alongside process RSS/container memory because a heap dashboard does not cover the entire process memory footprint.

## 9. Combining JVM with Application Signals

A JVM dashboard should link to application signals:
- HTTP request rate, error ratio, and p95/p99 latency;
- executor active/queue/rejected;
- Hikari active/idle/pending/acquisition;
- messaging consumer lag;
- database/client span latency;
- deployment/version markers.

For example: rising HTTP latency, low CPU, normal GC, rising Hikari pending, and long JDBC spans usually point toward a database/pool bottleneck rather than JVM CPU. If heap/Old Gen and GC pauses rise simultaneously, investigate allocation/retention.

### 9.1. Correlation via consistent labels

Use stable labels such as service, environment, cluster, namespace, instance, and version. Ensure dashboards share consistent naming conventions. Do not join metrics by request ID or trace ID.

### 9.2. Deployment annotations

Mark deployments, config changes, JVM restarts, and scaling events on the timeline. This helps correlate runtime changes with heap, GC, thread, and latency behavior.

## 10. Alerting from the JVM Dashboard

A dashboard is for viewing and investigating; alerts need to detect meaningful symptoms and trigger specific actions. Do not alert on every metric.

| Signal | Suggested Alert Condition | What to Verify |
| --- | --- | --- |
| Heap usage | Sustained high after GC | Leak/heap sizing/cache |
| GC pause | p95/p99 exceeds latency budget | Collector/alloc pressure |
| Live threads | Abnormal growth vs. baseline | Thread leak/pool growth |
| BLOCKED threads | Rising alongside latency | Lock contention |
| Process CPU | Sustained high | CPU saturation |
| Container throttling | Increasing throttled time | CPU limit/capacity |
| Direct buffers | Continuous growth or near limit | Native memory pressure |
| Class loaded | Continuous growth after warm-up | Dynamic class generation |

### 10.1. Alerts with windows and duration

Use a `for` duration to avoid alerts from brief spikes. Set thresholds based on load tests and the service's baseline. 85% heap utilization might be normal for one workload and dangerous for another; do not apply generic thresholds without verification.

### 10.2. Symptom-based alerts

An alert like "JVM heap pressure sustained" is better than "memory leak confirmed". Metrics only indicate symptoms; leaks require heap analysis and object retention verification. Alert messages should state service/instance, metric, threshold, duration, and links to dashboards/runbooks.

## 11. PromQL Examples for the Dashboard

The queries below are samples. Series names/labels must be verified from `/actuator/prometheus`.

**Heap used bytes:**

~~~promql
sum by (service, instance) (
  jvm_memory_used_bytes{area="heap"}
)
~~~

**Non-heap used bytes:**

~~~promql
sum by (service, instance) (
  jvm_memory_used_bytes{area="nonheap"}
)
~~~

**GC pause rate:**

~~~promql
sum by (service, instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
~~~

**GC average pause:**

~~~promql
sum by (service, instance) (rate(jvm_gc_pause_seconds_sum[5m]))
/
sum by (service, instance) (rate(jvm_gc_pause_seconds_count[5m]))
~~~

**Live threads:**

~~~promql
jvm_threads_live_threads
~~~

**Process CPU:**

~~~promql
process_cpu_usage
~~~

**Class loading:**

~~~promql
jvm_classes_loaded_classes
~~~

If `service` or `instance` labels do not exist, use the actual labels from your scrape/relabel configuration. Do not copy queries into a production dashboard before checking their output.

## 12. Cardinality and Dashboard Performance

Every label dimension multiplies the number of time series. Labels should use bounded, stable values: service, environment, region/cluster, namespace, instance/pod, and version.

Avoid user IDs, request IDs/trace IDs, URL paths containing IDs, exception messages, dynamic per-task thread names, JVM arguments, or dynamic paths.

Instance/pod is a useful dimension for spotting an anomalous replica, though it can cause churn during autoscaling. Use dashboard variables and aggregation to keep panels manageable; do not remove instance if per-pod investigation is needed.

### 12.1. Reducing panel/query cost

- Limit default time ranges.
- Use recording rules for expensive repeated queries.
- Aggregate before rendering when panels do not need per-instance detail.
- Avoid broad label regexes and complex joins.
- Use a step/resolution appropriate for the displayed time range.
- Enable histogram buckets only when quantiles are needed and cardinality cost has been accounted for.

## 13. Testing Dashboards and Metric Contracts

Dashboards should be tested at two layers: metric production and query/panel behavior.

| Test | Objective |
| --- | --- |
| Actuator scrape test | JVM series are exported |
| Meter contract test | Required meter names/tags are stable |
| PromQL validation | Queries parse and return series |
| Dashboard JSON validation | Panels/variables/datasources are valid |
| Load test | Panels remain responsive at real cardinality |
| Alert rule test | Threshold/for/labels/annotations are accurate |
| Upgrade test | Micrometer/JDK/Boot upgrades do not break panels |

### 13.1. Checking metrics from the application

Call `/actuator/prometheus` in integration tests and verify required series are present. Avoid asserting on the entire scrape output since JVM version, process, and runtime metrics can vary.

### 13.2. Checking queries

Use Prometheus rule tests or query validation in CI if your platform supports it. Test absent series, zero denominators, and non-existent labels. Heap utilization queries must handle undefined pool maxes.

### 13.3. Checking dashboards after upgrades

When upgrading the JDK, Spring Boot, or Micrometer, compare scrape output before and after. Some meters/labels/units may change. Dashboards should be version-controlled alongside alert rules and reviewed during releases.

## 14. Investigation Workflow Using the JVM Dashboard

When latency rises or a pod restarts:
1. Select the affected service, environment, and instance.
2. Check request rate, error ratio, and latency at the same timestamp.
3. Inspect heap used/max, Old Gen trend, and non-heap.
4. Check GC pause rate/duration and correlate with latency.
5. Inspect live threads, state distribution, and executor queues.
6. Check process CPU alongside container throttling.
7. Check direct buffers and process/container memory.
8. Cross-check Hikari pool, HTTP client spans, and database metrics.
9. Open logs/traces in the same time window to identify the specific operation.
10. Compare before and after deployment markers.

Do not conclude a memory leak solely from high heap usage, a deadlock solely from WAITING threads, or a CPU bottleneck solely from system CPU. The dashboard helps narrow hypotheses; heap dumps, thread dumps, profilers, and traces provide deeper evidence.

## 15. Troubleshooting the JVM Dashboard

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No JVM metrics | Missing binder/registry or endpoint not exposed | Check Actuator, registry, and scrape |
| Heap utilization exceeds 100% | Invalid pool max or wrong query | Filter pools with valid max and verify labels |
| Empty GC panel | Different histogram/series name or JVM binder not emitting | Inspect scrape output |
| Thread count rises steadily | Thread leak or executor growth | Thread dump and executor metrics |
| CPU panel reads 0 | Unsupported OS bean or wrong unit/query | Check runtime support and meter unit |
| Stable heap but rising RSS | Native/direct memory or thread stacks | Buffer pools, NMT, and container metrics |
| Class count grows indefinitely | Dynamic class generation/classloader leak | Classloader analysis |
| Slow dashboard | High query cardinality/large time range | Recording rules, aggregation, label review |
| Empty panels after upgrade | Meter/label naming changed | Contract tests and query updates |
| Noisy GC alerts | Alerting solely on count | Use pause duration and latency correlation |
| One pod behaves abnormally | Instance-specific workload/config | Drill down to instance and compare replicas |

### 15.1. Short runbook

- Heap pressure: check post-GC Old Gen, allocation, cache limits, and capture a heap dump per procedure.
- GC latency: check pause quantiles, collector logs, CPU throttling, and allocation rate.
- Thread saturation: check thread states, executor queues, thread dumps, and downstream calls.
- CPU saturation: check process CPU, container throttling, hot threads, and request mix.
- Native memory: check direct buffers, RSS, thread count, and Native Memory Tracking.

## 16. Production Checklist

| Criterion | Evidence |
| --- | --- |
| JVM meters exposed | Scrape test includes required series |
| Heap/non-heap separated | Panels grouped by area/pool |
| Pool max handled safely | No division by -1/NaN |
| GC pauses measured accurately | Count/sum/histogram semantics verified |
| Threads have context | Live/peak/states and executor metrics |
| CPU has container context | Process/system CPU alongside throttling |
| Native memory considered | Direct buffers/RSS |
| Stable labels | No dynamic identifiers |
| Dashboard has variables | Service/environment/instance |
| Alerts have runbooks | Threshold, duration, owner, and action |
| Acceptable query performance | Cardinality/time range/recording rules |
| Upgrades tested | Metric contracts and dashboard validation |
| Logs/traces linked | Drill-down within the same time window |

## 17. Hands-on Exercise: Building a JVM Dashboard for order-service

**Context:** `order-service` runs multiple replicas on Kubernetes. After a release, p99 HTTP latency increases and several pods restart due to memory pressure. The operations team needs a dashboard to distinguish heap pressure, GC, CPU throttling, and thread/executor saturation.

**Tasks:**
1. Enable Actuator and the Prometheus registry.
2. Collect scrape output and record actual meter/label names.
3. Create variables for service, environment, namespace, and instance.
4. Create panels for heap used/committed/max and non-heap by pool.
5. Add GC pause rate, average, and p95/p99 when histograms are available.
6. Add live/daemon/peak threads and state distribution.
7. Add process/system CPU alongside container CPU throttling.
8. Add direct buffer memory/count and class loading trend.
9. Link HTTP latency/error, executor queue, and Hikari pool panels.
10. Create alerts for sustained heap pressure, high GC pauses, thread growth, and CPU throttling.
11. Test PromQL when series are absent, max is invalid, and labels change.
12. Write a drill-down runbook from JVM symptoms to logs/traces and profilers.

**Expected outcome:** a JVM dashboard with panels/variables, alert rules, validated queries, and a runbook for investigating latency/memory incidents.

## 18. Key Takeaways

A JVM dashboard should help detect and categorize runtime pressure. Heap/non-heap shows memory pools; GC pauses show collection cost; threads and executor metrics point to concurrency/saturation; process CPU must be read alongside container throttling; direct buffers and RSS complete the native memory view. No single metric alone is enough to prove a memory leak, deadlock, or CPU bottleneck.

Verify meter names, units, and labels from `/actuator/prometheus` before writing PromQL. Use stable labels, variables for drill-downs, and recording rules when queries are expensive. Alerts need duration, baselines, owners, and runbooks; avoid alerting solely on GC count or a generic heap threshold. Combine the JVM dashboard with HTTP metrics, pool metrics, logs, and traces to move from runtime symptoms to specific request root causes.

**References:**
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus Endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Micrometer JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Grafana — Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Java — Monitoring and Management](https://docs.oracle.com/en/java/javase/21/management/)
