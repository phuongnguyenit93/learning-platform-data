# Binders in Spring Boot Metrics: From `MeterRegistry` to Operational Signals

When a Spring Boot application runs in production, operations teams need to know how much memory the JVM uses, whether CPU is overloaded, whether queues are backing up, and whether connection pools still have available connections. Many of these numbers are not tied directly to a single HTTP request. They describe **the state or activity of a component** and must be registered with the metrics system before they can be collected.

In Micrometer, **`MeterBinder`** is the mechanism that encapsulates registering one or more `Meter`s into a `MeterRegistry`. Spring Boot can auto-configure many binders for the JVM and runtime environment, while allowing applications to define custom binders for business state. Consequently, the same metrics contract can be applied cleanly to whichever registry the application uses.

This lesson belongs to the **Spring Boot metrics** chapter of the **SPRING_BOOT_OBSERVABILITY** module, aiming to establish observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. We will explore binders from fundamentals to code, tags/cardinality, exporters, and how to combine them with tracing, sampling, and context propagation to investigate errors or latency in real environments.

## Learning objectives

After this lesson, you will be able to:

1. Explain what `MeterBinder` is, when it is called, and how it differs from `Meter` or `MeterRegistry`.
2. Identify the metric groups that Spring Boot/Micrometer default binders can provide and the conditions for them to appear.
3. Create a custom `MeterBinder` registering a gauge that measures business queue depth.
4. Register a binder as a Spring bean or call `bindTo` when managing a registry directly.
5. Verify meters via `/actuator/metrics`, `/actuator/prometheus`, and `SimpleMeterRegistry` in tests.
6. Control labels, cardinality, observed object lifecycles, and collection overhead.
7. Distinguish metrics from binders from metrics from Observation, as well as correlating metrics, logs, and traces.

## 1. Three foundational concepts: `Meter`, `MeterRegistry`, and `MeterBinder`

**`Meter`** is the unit of measurement in Micrometer. For example, a `Counter` counts monotonically increasing events, a `Timer` records call counts and completion durations, and a `Gauge` reads the current value of an object or quantity. Common meter types include:

| Meter | Meaning | Example |
| --- | --- | --- |
| `Counter` | Monotonically increasing total event count | Number of jobs processed |
| `Gauge` | Current value at read time | Number of tasks waiting in a queue |
| `Timer` | Count and duration distribution of completed operations | Time to call `inventory-service` |
| `DistributionSummary` | Distribution of a non-time numeric quantity | Payload size, number of items per order |
| `LongTaskTimer` | Tracks long-running active tasks | Count of long batch jobs and their elapsed running time |

**`MeterRegistry`** is where meters are registered and managed. The specific registry implementation determines how data is represented and exported. For instance:

- `SimpleMeterRegistry`: stores meters in memory, useful for testing.
- `PrometheusMeterRegistry`: exposes data in Prometheus format for scrape-based collection.
- Other registries/exporters: push or expose data to their respective monitoring systems depending on libraries and configuration.

**`MeterBinder`** is an interface with a single core method:

~~~java
package io.micrometer.core.instrument.binder;

import io.micrometer.core.instrument.MeterRegistry;

@FunctionalInterface
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
~~~

The snippet above illustrates the API signature—**you do not copy the library interface into your project**. Calling `bindTo(registry)` causes the binder to register the corresponding meters. Afterward, meters are updated or sampled per their mechanics: a gauge reads current state when the registry is scraped; timers/counters require events recorded while the application runs.

### 1.1. What does a binder do and not do?

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Binder["MeterBinder: register meters"]
    Binder --> Registry["MeterRegistry"]
    Runtime["JVM / CPU / pool / queue"] --> Meters["Counter, Gauge, Timer..."]
    Registry --> Meters
    Meters --> Export["Prometheus scrape or metrics exporter"]
    Export --> Backend["Metrics backend / Grafana"]
    App --> Observation["Micrometer Observation"]
    Observation --> Handler["MeterObservationHandler"]
    Handler --> Registry
    Observation --> Tracing["Tracing handler / spans"]
~~~

A binder **defines how meters are registered**; it does not automatically send HTTP requests to a backend, create distributed traces, emit logs, or propagate trace context to another thread. A `MeterBinder` can register the exact same meter types as code using `MeterRegistry` directly; the benefit lies in encapsulating and reusing setup logic.

An easily confused name is **`MeterObservationHandler`**. That handler reacts to the lifecycle of an `Observation` to record metrics, whereas `MeterBinder` registers meters for a target object/system. Both mechanisms can coexist and write into the same `MeterRegistry`, but they are not the same API.

## 2. `bindTo` lifecycle and how data is updated

Consider a binder measuring queue depth:

1. The application initializes the queue object and `MeterRegistry`.
2. The binder is created, then `bindTo(registry)` registers a `Gauge` bound to the queue object.
3. As waiting tasks change, **the queue object** holds the new value.
4. When the metrics system reads the gauge, the callback returns the current value.
5. The registry/exporter makes the data queryable in the backend.

~~~mermaid
sequenceDiagram
    participant Boot as Spring Boot
    participant Binder as QueueMeterBinder
    participant Registry as MeterRegistry
    participant Queue as Business queue
    participant Prom as Prometheus
    Boot->>Binder: Create bean
    Boot->>Registry: Apply binder to registry
    Registry->>Binder: bindTo(registry)
    Binder->>Registry: Gauge.builder(...).register(...)
    Queue->>Queue: Depth changes with workload
    Prom->>Registry: Scrape at /actuator/prometheus
    Registry->>Queue: Read queue.size()
    Queue-->>Registry: Current task count
    Registry-->>Prom: Metric and tags
~~~

Crucial point: **a Gauge is an instantaneous state measurement**. If a queue spikes to 1,000 and drains back to 0 between two scrapes, the backend may miss that peak completely. If you need *how many tasks were processed over an interval*, use an event-incremented Counter; if you need processing time, use a Timer. Never try to turn a Gauge into an accumulative counter.

### 2.1. Should `bindTo` be called multiple times?

Normally, a binder only needs to be applied **once per registry**. Spring Boot automatically applies matching `MeterBinder` beans to the registries it manages. If a binder is already declared as a bean, do not also manually invoke `binder.bindTo(registry)` on the same registry without a clear reason; duplicate registration can cause redundant config, warnings, or confusing values.

When multiple independent registries are used, a binder can be applied to each registry. Ensure meter names/tags and collection costs are controlled at every destination.

## 3. Built-in binders and metrics in Spring Boot

When `spring-boot-starter-actuator` is added, Spring Boot can auto-configure many metric groups if library, bean, and runtime conditions are satisfied. Some rely on **built-in Micrometer binders**; others come from instrumentation or specialized integrations.

| Signal group | Commonly seen meter examples | Condition or measurement source |
| --- | --- | --- |
| **JVM memory** | `jvm.memory.used`, `jvm.memory.committed`, `jvm.memory.max` | JVM memory binder |
| **GC** | `jvm.gc.pause` and related GC metrics | JVM GC binder, depending on collector/JDK |
| **Threads** | `jvm.threads.live`, `jvm.threads.daemon` | JVM thread binder |
| **Classes** | `jvm.classes.loaded` | Class loader binder |
| **Process / CPU** | `process.cpu.usage`, `process.uptime`, `system.cpu.usage` | Process/system binder, platform-dependent |
| **Disk space** | `disk.free`, `disk.total` | Disk space binder, depends on monitored path |
| **Connection pool** | E.g., `hikaricp.connections.active` | DataSource/HikariCP present with matching metrics integration |
| **Cache** | E.g., `cache.gets`, `cache.puts` | Supported cache manager/provider, sometimes requires enabling stats |
| **HTTP server** | `http.server.requests` | Usually via HTTP instrumentation / Micrometer Observation, distinct from JVM binders |

The list above consists of **examples**, not a guarantee that all appear in every application. Meter names and data types also depend on Spring Boot, Micrometer, JDK, runtime, providers, and registry naming conventions. When a meter is missing, verify whether that component exists and is instrumented.

### 3.1. Trying Micrometer binders directly

The snippet below illustrates using built-in binders outside Spring Boot auto-configuration:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

try (MeterRegistry registry = new SimpleMeterRegistry()) {
    new JvmMemoryMetrics().bindTo(registry);
    new JvmThreadMetrics().bindTo(registry);
    new ProcessorMetrics().bindTo(registry);

    // The registry now contains the corresponding JVM/process-related meters.
    registry.getMeters().forEach(meter ->
            System.out.println(meter.getId().getName()));
}
~~~

This code uses a standalone registry to demonstrate binders. **In a real Spring Boot application**, if the corresponding binders are already auto-configured, there is no need to register them again manually. Some meters may have no value or be unavailable on a given JVM/OS/container.

### 3.2. Distinguishing infrastructure metrics from user-impacting signals

When `jvm.memory.used` increases, the application is not necessarily failing; when `process.cpu.usage` is high, users are not necessarily seeing slowdowns. These metrics explain resource conditions and **aid root-cause investigation**, but usually should not be the sole SLI.

An order-creation service should combine:

- **User-facing signals**: HTTP 5xx, order completion rate, request duration p95/p99.
- **Dependency signals**: call duration to `inventory-service`, timeouts, retries.
- **Resource signals**: JVM memory, GC pauses, CPU, connection pools, queues.

That way, when requests slow down, operations can see whether resource utilization rises alongside latency.

## 4. Creating a custom `MeterBinder` to measure a business queue

Suppose an application accepts order creation requests and enqueues background work onto a queue. We want to track **the number of orders currently waiting to be processed**.

Define the contract:

| Element | Value |
| --- | --- |
| Meter name | `orders.queue.pending` |
| Meter type | `Gauge` |
| Base unit | `tasks` |
| Bounded-value tag | `queue=orders` |
| Measured data | Number of waiting tasks in an application-managed queue |

### 4.1. Defining the observed object

In `PendingOrderQueue.java`:

~~~java
package com.example.orders.metrics;

public interface PendingOrderQueue {
    int size();
}
~~~

This interface is an illustrative API. The application must provide a real implementation bean, such as an adapter reading the size of an in-memory queue. If the queue resides in an external system, querying its size over the network on every scrape can be slow or fail; design a data source that is readily available, cheap to read, and has clear freshness guarantees.

### 4.2. Writing the binder

In `PendingOrderQueueMeterBinder.java`:

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Objects;

public final class PendingOrderQueueMeterBinder implements MeterBinder {
    private final PendingOrderQueue queue;

    public PendingOrderQueueMeterBinder(PendingOrderQueue queue) {
        this.queue = Objects.requireNonNull(queue);
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("orders.queue.pending", queue, PendingOrderQueue::size)
                .description("Number of orders currently waiting in the queue")
                .baseUnit("tasks")
                .tag("queue", "orders")
                .register(registry);
    }
}
~~~

`Gauge.builder(name, object, function)` uses a callback to read the value from `queue` whenever the registry needs it. `baseUnit("tasks")` expresses the measured quantity without turning it into a counter. In a Prometheus backend, the exported name may receive a unit suffix (such as `_tasks`), so inspect live export output before writing PromQL.

**Lifecycle concern:** Micrometer typically holds only a **weak reference** to the object observed by a Gauge. If the application stops holding a strong reference to `queue`, the Gauge can lose its source or report invalid values. Here, `PendingOrderQueueMeterBinder` holds a reference to the queue, and the application's queue bean must also have an appropriate lifecycle. Never allocate a temporary object inline inside `Gauge.builder` and let it be garbage collected.

### 4.3. Registering the binder as a Spring bean

In `MetricsConfiguration.java`:

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterBinder pendingOrderQueueMeterBinder(PendingOrderQueue queue) {
        return new PendingOrderQueueMeterBinder(queue);
    }
}
~~~

In **Spring Boot 3.x with metrics auto-configuration**, `MeterBinder` beans are applied to the application's managed `MeterRegistry`. `PendingOrderQueue` must be an actual Spring bean for injection. When not using Spring Boot auto-configuration or when managing a custom registry directly, you can bind manually:

~~~java
MeterRegistry registry = /* application-provided registry */;
PendingOrderQueue queue = /* live application component */;

new PendingOrderQueueMeterBinder(queue).bindTo(registry);
~~~

This snippet demonstrates manual invocation, not an instruction to instantiate a new `MeterRegistry` inside a service. In a Spring Boot application, prefer injecting the centrally configured registry so exporters, common tags, and filters work consistently.

### 4.4. Why not call `size()` to set a Gauge value manually?

A Gauge measures state, so you **register a callback** to read the value. When the queue moves from 3 to 7 and back down to 2, the callback returns the current value at scrape time. There is no `gauge.increment()` concept for counting total processed orders in this model.

When you need to count total successful/failed tasks, use a `Counter` where events occur; when you need latency, use a `Timer` or an `Observation`. A binder can register those meters, though recording events at the right moments remains the responsibility of instrumentation code.

## 5. Configuring Spring Boot Actuator and metrics exporters

Basic dependencies when using Spring Boot with Micrometer and Prometheus support:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

An illustrative configuration in `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-service
~~~

Once the application is running and endpoints are reachable from an authorized network, check:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/orders.queue.pending
curl -s http://localhost:8080/actuator/prometheus
~~~

Meaning:

- **`/actuator/metrics`** lists meter names visible to Actuator. `/actuator/metrics/orders.queue.pending` returns summary measurements and tags in Actuator format.
- **`/actuator/prometheus`** exposes metrics formatted for Prometheus scraping; it exists only when the Prometheus registry and endpoint exposure are properly configured.
- **`management.metrics.tags.application`** adds a low-cardinality common tag; never use dynamic values like request IDs.

The meter name at the Actuator endpoint (e.g., `orders.queue.pending`) **differs** from the normalized series name in Prometheus (e.g., dots turned to underscores and unit suffix appended). Exact names also depend on registry and version; do not guess series names when building dashboards.

**Security:** metrics/prometheus endpoints can reveal service names, instances, hostnames, resource states, and operational labels. In production, restrict access or use an internal management network; never expose endpoints publicly just to simplify scraping.

### 5.1. Registry and exporter are two separate concerns

A successfully registered meter **does not prove** the backend received the data. For example:

1. `MeterBinder` bound the `Gauge` to `MeterRegistry`.
2. `/actuator/metrics` sees the meter.
3. `/actuator/prometheus` exports the series.
4. The Prometheus server still needs to scrape the right target at the right interval.
5. The backend/dashboard needs matching queries, labels, and retention.

If using another export mechanism (such as pushing via OTLP), you need the corresponding registry/exporter for your Spring Boot and Micrometer version. Do not confuse the **OTLP metrics exporter** with the **OTLP tracing exporter**: they can have different pipelines and destination endpoints.

## 6. Testing a custom `MeterBinder`

You do not need to start Spring Boot or Prometheus to test whether a binder registers a Gauge with the right name/tags and reads accurate values. `SimpleMeterRegistry` is a clean choice for unit tests.

### 6.1. Unit test using `SimpleMeterRegistry`

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class PendingOrderQueueMeterBinderTest {

    @Test
    void gaugeReflectsCurrentQueueDepth() {
        AtomicInteger pending = new AtomicInteger(3);
        PendingOrderQueue queue = pending::get;

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            new PendingOrderQueueMeterBinder(queue).bindTo(registry);

            Gauge gauge = registry.find("orders.queue.pending")
                    .tag("queue", "orders")
                    .gauge();

            assertNotNull(gauge);
            assertEquals(3.0, gauge.value(), 0.001);

            pending.set(7);
            assertEquals(7.0, gauge.value(), 0.001);

            pending.set(2);
            assertEquals(2.0, gauge.value(), 0.001);
        }
    }
}
~~~

This test protects two key requirements: the Gauge is registered with the right name/tags, and the callback reads **the live value** rather than capturing a single snapshot at registration time.

It does not prove Prometheus metric naming normalization, exporter operation, or that Spring Boot applied the `MeterBinder` bean. Therefore, real applications also need integration tests at the proper boundary.

### 6.2. Spring Boot integration tests

A `@SpringBootTest` or minimal integration test should verify:

1. `PendingOrderQueue` is a bean and `MeterBinder` is picked up by auto-configuration.
2. The `MeterRegistry` injected into services/Actuator is the registry the binder bound to.
3. The `orders.queue.pending` meter is present and reflects test queue state changes.
4. Tags form a finite set; no order IDs, user IDs, or trace IDs appear in labels.
5. When the Prometheus registry is configured, scrape output exposes the gauge with expected units and series name.

Do not duplicate every unit-test assertion in integration tests. The purpose of integration testing is verifying the **wiring Spring Boot ↔ binder bean ↔ registry ↔ exporter**, which standalone unit tests cannot cover.

## 7. Reading and using binder metrics in dashboards

With default binders, dashboards provide context for investigating slowdowns or errors:

| Dashboard | Signals to include | Question |
| --- | --- | --- |
| JVM | Heap used, GC pauses, thread counts | Is the app experiencing memory pressure or GC stalls? |
| Process | CPU usage, uptime | Does CPU rise alongside latency? Was there a recent restart? |
| Connection pool | Active, idle, pending connections (if supported by provider) | Are requests waiting for a connection? |
| Queue | Current pending tasks, retry count, age of oldest task | Is the backlog growing faster than it drains? |
| HTTP/Business | Request rate, 5xx errors, p95/p99, success count | How severely are users affected? |

The following PromQL queries are examples; obtain actual series names from `/actuator/prometheus` or your live backend.

### 7.1. Heap memory used by instance

~~~promql
sum by (instance) (
  jvm_memory_used_bytes{area="heap",application="order-service"}
)
~~~

This is normally a **gauge** measured in bytes. Do not apply `rate(...)` to current heap usage as if it were a counter; to observe growth/shrink trends, plot it over time or use gauge-appropriate functions.

### 7.2. Average CPU usage over 5 minutes

~~~promql
avg_over_time(
  process_cpu_usage{application="order-service"}[5m]
)
~~~

`process_cpu_usage` typically represents a ratio (0 to 1 in standard meter behavior), not a cumulative counter. Do not use `rate(process_cpu_usage[5m])` to derive CPU utilization. Exact meter behavior depends on runtime and binder; verify actual values.

### 7.3. Current queue backlog

Assuming the Prometheus-exported series is `orders_queue_pending_tasks`:

~~~promql
orders_queue_pending_tasks{application="order-service",queue="orders"}
~~~

For **per-instance local queues**, `sum by (queue)` gives the total unprocessed tasks across the cluster. However, if every instance measures **the same shared queue**, summing Gauges **multiplies the same backlog by the instance count**. Before writing a sum, confirm whether each series represents an independent quantity or a shared state source.

For queues that can spike sharply between scrapes, consider scrape frequency, `max_over_time(...)`, or complementary metrics tracking tasks enqueued/processed and oldest task age.

### 7.4. Correlating resource state with user-facing latency

When `POST /orders` p95 spikes, an investigation flow might be:

1. Check request rate, error rate, and p95 to confirm user impact.
2. Compare the spike timestamp against CPU, GC pauses, heap, or connection pools.
3. If queue backlog climbs, inspect enqueue/dequeue rates, retries, and wait times.
4. Locate a sampled slow trace and examine spans calling the database or `inventory-service`.
5. Use the trace ID to search logs for timeouts or upstream errors.

`MeterBinder` supplies **resource and system context**. To answer "which specific request was slow and why?", you still need request/operation instrumentation via Observation plus correlated tracing and logging.

## 8. Tags and cardinality when using binders

Even a single Gauge with too many labels can inflate series counts:

| Tag | Example | Assessment |
| --- | --- | --- |
| `application` | `order-service` | Suitable, small value set |
| `environment` | `staging`, `production` | Suitable |
| `queue` | `orders`, `notifications` | Suitable if queue count is bounded |
| `instance` | Instance identifier assigned by monitoring system | Necessary for operations; series scale per instance |
| `order.id` | Different value per order | **Unsuitable** as a metric label |
| `user.email` | Individual user email | **Never collect** in metrics |
| `trace.id` | Varies per request | **Never put into metric labels** |

Suppose a binder registers a metric across 3 deployment regions, 4 environments, and 20 instances. If all combinations occur, a single metric name produces **3 × 4 × 20 = 240** series. Adding 100,000 `order.id` values scales cardinality with traffic and ruins metric aggregability.

**Rules to follow:**

- Keep meter names stable, with clear units and meanings.
- Only include tags with finite value sets serving specific analytical questions.
- Never put personal data, tokens, or request payloads into tags.
- Never register a new meter per request; register stable meters and record values/events against them.
- When adding tags or histograms, account for series multiplication, since histograms also multiply by bucket boundaries.
- In multi-instance setups, verify aggregability: the same shared queue measured from multiple instances must not be summed.

### 8.1. Common tags and `MeterFilter`

Spring Boot can configure common tags via `management.metrics.tags.*` to standardize `application` or `environment`. For more complex needs, `MeterFilter` allows transforming or denying meters per registration policy—for example, managing an unwanted metric name or malformed tag set.

`MeterFilter` differs from **`ObservationFilter`**:

- `MeterFilter` operates at the **`MeterRegistry` and `Meter.Id`** layer.
- `ObservationFilter` operates on **`Observation.Context`** during its lifecycle.
- `ObservationConvention` defines naming and key-values for an Observation family.
- `MeterBinder` registers meters and can work completely without Observation.

Do not use filters to mask broken tag design at the source. Fix the binder/instrumentation and treat filters as an auxiliary policy layer when genuinely needed.

## 9. How do binders, logs, and distributed tracing work together?

A binder observing JVM, CPU, or queue backlog **has no per-request trace ID**. That is expected: it describes application-wide or component-level quantities. Conversely, a custom `Observation` and tracing handler can produce spans belonging to a request's trace.

~~~mermaid
flowchart LR
    Binders["JVM / Process / Queue MeterBinders"] --> Registry["MeterRegistry"]
    Registry --> Metrics["Metrics backend: resource trends"]
    Requests["HTTP + Business Observations"] --> MeterHandler["Metrics handler"]
    MeterHandler --> Registry
    Requests --> TraceHandler["Tracing handler"]
    TraceHandler --> Traces["Trace backend: request path"]
    Requests --> Logs["Logs: events and error codes"]
    Traces -. "trace ID when present" .-> Logs
    Metrics -. "service, instance, timestamp" .-> Traces
~~~

The link between binder metrics and traces is normally **service, instance, environment, deployment version, and time window**. Not every meter has an exemplar or direct trace pointer. Some backends support **exemplars** to jump from a metric to a trace, though this requires explicit support and configuration across registry, tracing, and backend.

### 9.1. Context propagation and sampling do not govern binder metrics

When `order-service` calls `inventory-service`, spans correlate via W3C Trace Context, usually through the `traceparent` header. For asynchronous execution, configure proper propagation to preserve parent-child relationships.

**`MeterBinder` does not propagate context** across HTTP/threads and does not require an active request span to measure CPU or queues. If tracing is sampled at 10%, most traces are not stored, yet JVM/queue metrics are still collected normally. Conversely, Prometheus scrape or exporter failures can drop metric time series even while traces remain intact.

Therefore, separate causes during investigations:

| Symptom | Possibilities to check |
| --- | --- |
| `orders.queue.pending` missing from `/actuator/metrics` | Binder bean not created, registry not bound, meter filtered out, queue does not exist |
| Metric present in Actuator, missing in Prometheus | Prometheus registry, exposure, scrape config, network, or series name |
| Metrics present, traces missing | Sampling, tracing bridge, exporter, Collector, or propagation |
| Traces present, logs lack correlation | Logging/MDC configuration or lost scope |
| CPU spikes without slow requests | CPU driven by background tasks, GC, cron jobs, or off-request workloads |

Do not infer that a binder is working merely because `/actuator/health` returns `UP`. Health endpoints and metrics answer different questions.

## 10. Common mistakes when writing custom `MeterBinder`s

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Building a Gauge on a temporary object | Object gets GC'd; Gauge stops returning reliable values | Hold a strong reference in a bean with a matching lifecycle |
| Attaching request ID as a tag | Cardinality scales with traffic | Use bounded tags; correlate requests via traces/logs |
| Updating a Gauge like a Counter | Total event counts are wrong | Counter for cumulative counts; Gauge for instantaneous state |
| Making heavy network/DB calls inside a Gauge callback | Slow scrapes, extra load, timeout risks | Provide lightweight reads or bounded-freshness caching |
| Registering a binder twice on the same registry | Duplicate registration, warnings, confusing readings | Let Spring Boot manage it or call `bindTo` manually—pick one |
| Instantiating a new registry inside a service | Meters missing from exported registry | Inject the centrally configured registry |
| Measuring a shared queue from all instances and summing | Total backlog multiplied by instance count | Understand data source semantics before aggregating |
| Embedding timestamps in meter names | Metric names churn continuously | Keep names static; timestamps belong to samples |
| Changing metric name or `baseUnit` arbitrarily | Existing dashboards/alerts stop finding data | Govern metrics contracts and migration plans |
| Using only a Gauge and missing short spikes | Scrapes sample periodically | Add Counters/Timers; review scrape interval |
| Checking only Actuator endpoints | Unsure whether Prometheus scrapes successfully | Verify destination backend and pipeline health |
| Confusing binders with tracing instrumentation | No request spans despite complete infra metrics | Instrument requests/business steps with Observation and tracing handlers |

## 11. Checklist before shipping a binder to production

| Criterion | Required evidence |
| --- | --- |
| Meter describes a clear quantity | Defined name, meter type, unit, description, and data source |
| Binder registers exactly once per registry | Clear bean or manual `bindTo` convention |
| Values update accurately | Unit test mutates source and asserts Gauge values |
| Observed object has a sound lifecycle | Gauge does not depend on short-lived objects prone to GC |
| Callback overhead is acceptable | No slow queries or side effects during scrapes |
| Tags have finite cardinality | No request/user/order IDs or sensitive data |
| Cross-instance aggregation is defined | No double-counting a shared queue |
| Actuator sees the meter | `/actuator/metrics` shows expected name and measurements |
| Exporter/backend verified | Scrape or target pipeline shows fresh data and timestamps |
| Dashboard links thresholds to actions | E.g., sustained high backlog triggers consumer inspection |
| Correlatable with other signals | Can compare alongside HTTP errors/latency, traces, and logs |
| Schema change plan exists | Renaming/retagging/unit changes update queries, alerts, and docs |

## 12. Hands-on exercise: detecting a backed-up order queue

**Scenario:** `order-service` accepts `POST /orders` and dispatches background processing tasks to a queue. Operations notices HTTP request p95 stays fairly flat, yet many orders fail to complete on time. Additional metrics are needed to distinguish accepted requests from congested background processing.

**Tasks:**

1. Configure Actuator and the Prometheus registry for your project's Spring Boot version, exposing metrics endpoints in a test environment.
2. Define `PendingOrderQueue` with `size()` and an implementation backed by `AtomicInteger` to simulate pending tasks.
3. Implement `PendingOrderQueueMeterBinder` registering `Gauge` `orders.queue.pending`, unit `tasks`, and tag `queue=orders`.
4. Declare the binder as a Spring bean; verify the queue bean and registry are managed by the application.
5. Write a unit test using `SimpleMeterRegistry` changing queue depth from 3 → 7 → 2. Explain why the Gauge reads the current value rather than accumulating 12.
6. Send simulated requests to build up a backlog, and inspect the meter at `/actuator/metrics` and the live series at `/actuator/prometheus`.
7. Propose adding a `Counter` for succeeded/failed jobs and a `Timer` for processing duration; clearly distinguish the questions each of the three meter types answers.
8. If the queue is an external shared resource, state when Gauges from multiple instances can be summed and when summing would double-count.
9. Simulate a background processing timeout; combine queue depth, failure count, HTTP latency, a sampled trace, and trace-ID logs to investigate.
10. Propose an alert for sustained backlog above a threshold, along with a dashboard showing enqueue/dequeue rates and oldest task age if supported by the source.

**Expected deliverables:** readable Java binder code, unit test proving dynamic Gauge readings, matching Spring Boot configuration, verified live metrics queries, and a brief write-up explaining how to diagnose slow background processing when HTTP requests succeed.

## 13. Key takeaways

**`MeterBinder` is the mechanism for registering meters into a `MeterRegistry`**. Spring Boot and Micrometer ship many binders for JVM, process, system, and resource integrations; applications can also write custom binders for queues or business state. A well-designed binder keeps names/units stable, reads values cleanly, manages observed object lifecycles, and caps tag cardinality.

Binder metrics reveal resource health and operational trends. When you need to pinpoint *where a specific request slowed down or failed*, complement them with **Micrometer Observation, correlated logs, and distributed tracing**. These signals connect via service/instance/time context or trace IDs when tracing is active; investigation effectiveness also depends on context propagation, sampling, exporters, and backends actually ingesting telemetry.

**References:**

- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
