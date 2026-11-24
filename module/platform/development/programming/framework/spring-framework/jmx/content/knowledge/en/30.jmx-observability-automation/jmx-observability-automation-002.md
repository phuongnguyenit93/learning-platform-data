# Combining JMX with a Metrics Registry in Spring Framework

## 1. Objective: Bridging JMX Management Capabilities with a Metrics System

Java Management Extensions (JMX) is the JVM's management and observability mechanism. A Java application can register **MBeans** into an `MBeanServer`, exposing attributes and operations so that JConsole or JMX clients can read state, change runtime configuration, or receive notifications.

Meanwhile, a **metrics registry** such as Micrometer's `MeterRegistry` is where an application records standardized measurements: counters, gauges, timers, distribution summaries, and classification tags. The data is exported to systems like Prometheus, Datadog, or another monitoring backend depending on the chosen registry/exporter.

The two mechanisms have partially overlapping purposes but are **not identical**:

- JMX is suited for **runtime management and diagnostics**, including read-only attributes and operations.
- A metrics registry is suited for **time-series monitoring**, aggregation, dashboards, alerts, and trend analysis.
- Many JVM/platform MXBeans already provide data about heap, threads, GC, and class loading.
- Spring Boot Actuator and Micrometer can push many JVM metrics into the registry **without writing custom MBeans for every measurement**.
- A JMX exporter/collector can also read MBean attributes and turn them into metrics when compatibility with an existing JMX setup is needed.

This lesson walks through choosing an integration path, building Spring examples, understanding trade-offs, and avoiding double counting or putting inappropriate metrics/cardinality onto dashboards.

## 2. Four Common Integration Patterns

```text
                     Java / Spring Application
                               |
             +-----------------+------------------+
             |                                    |
     MBeanServer (JMX)                      MeterRegistry
             |                                    |
     JConsole / JMX client                 Micrometer meters
             |                                    |
      JMX collector                        Registry exporter
             |                                    |
             +---------------+--------------------+
                             |
                      Metrics backend
                             |
                    Dashboard / Alerts
```

There are four paths to choose from:

| Pattern | How does data flow? | Suitable when |
|---|---|---|
| **A. JMX → collector → metrics** | MBean attributes are scraped and converted into time series | Legacy apps already have MBeans and instrumentation is hard to modify |
| **B. Application → Micrometer → backend** | Code records counters/gauges/timers into `MeterRegistry` | New Spring apps need dashboards/alerts |
| **C. JVM/Micrometer binders** | Runtime/JVM metrics go directly into the registry | Heap, GC, CPU, and thread metrics are needed in the registry's standard format |
| **D. Combining JMX + registry** | JMX keeps management operations, registry holds telemetry | You want both runtime control and time-series monitoring |

Do not implement both A and B for the **same measurement** without an ownership convention. For example, a counter recorded directly in Micrometer and simultaneously scraped by a JMX collector may appear as two series; dashboards aggregate incorrectly if both are summed.

## 3. Distinguishing an MBean Attribute from a Metric

JMX example:

```java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
```

A JMX client can call `getAttribute(ObjectName, "CompletedJobs")` to retrieve the current value.

Micrometer example:

```java
Counter completed = registry.counter(
    "worker.jobs.completed",
    "queue", "orders"
);
completed.increment();
```

Both may reflect the number of completed jobs, but systems interpret the data with different semantics:

| Aspect | JMX attribute | Metrics meter |
|---|---|---|
| Identity | ObjectName + attribute | Metric name + tags |
| Reading data | JMX API | Backend/exporter/registry |
| History | Not stored by default | Backend typically stores time series |
| Type | Primitive, String, OpenData, or JMX-supported types | Counter/gauge/timer/summary/distribution |
| Aggregation | Client must design its own | Backend supports querying and aggregation |
| Operation | MBean can expose callable operations | Meters are generally not a control API |
| Unit | Usually described by the MBean contract | Has metadata/base unit depending on the registry |
| Cardinality | ObjectName has multiple properties | Tags must be tightly controlled |

A number read from JMX is **not automatically a counter**: you must know whether it increases monotonically, when it resets, and whether it can decrease. A `QueueDepth` attribute is a gauge, whereas `CompletedJobsTotal` can be a counter if the actual semantics match.

## 4. Choosing the Metric Type Before Instrumenting

### 4.1. Counter

A Counter represents a cumulative total of events, typically increasing over time:

```java
Counter successCounter = registry.counter(
    "orders.processed",
    "outcome", "success"
);

successCounter.increment();
```

Do not use a Counter to represent queue depth, active threads, or open connections, because those values can both increase **and decrease**.

### 4.2. Gauge

A Gauge represents a value that can go up and down:

```java
AtomicInteger queueDepth = new AtomicInteger();

Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
    .description("Current number of waiting orders")
    .baseUnit("tasks")
    .register(registry);
```

A Gauge typically reads an object's state at scrape time. Maintain a strong reference to the observed object; depending on the registry implementation, an unreferenced object may be garbage-collected and the gauge will lose its expected value.

### 4.3. Timer

A Timer measures duration and occurrence count:

```java
Timer timer = registry.timer(
    "orders.processing.duration",
    "result", "success"
);

timer.record(() -> processOrder());
```

A Timer may export multiple time series depending on the registry/backend, such as count, total time, and histograms/percentiles when configured. Do not sum all of them together as the same quantity.

### 4.4. DistributionSummary

Used when measuring size/distribution that is not necessarily a duration, such as bytes per message or batch size:

```java
DistributionSummary batchSizes = DistributionSummary.builder(
    "orders.batch.size"
).baseUnit("items").register(registry);

batchSizes.record(25);
```

**Metric type is a semantic decision**, not just a display choice. An MBean getter can supply a raw value, whereas the registry needs a meter type defined so the backend can compute rates, quantiles, or histograms accurately.

## 5. Spring Boot Actuator and Micrometer

In Spring Boot, a common approach is using Actuator + Micrometer to export metrics.

Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Versions should be managed by the Spring Boot project's compatible dependency management/BOM. This example assumes the application uses a Boot version that supports the corresponding Prometheus registry.

Illustrative configuration:

```properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.show-details=never
```

Once the registry and endpoint are appropriately auto-configured, data can be inspected via:

```bash
curl http://localhost:8080/actuator/prometheus
```

The actual path may change if a custom management base path/port is configured. The endpoint must be enabled and exposed over the web; having the dependency is only part of the requirement. Security policies and access restrictions must also be applied rather than exposing management endpoints indiscriminately.

**Note:** `/actuator/metrics` is an API for looking up metrics by name, whereas `/actuator/prometheus` provides the Prometheus scrape format when the corresponding registry is present. They are not the same endpoint.

## 6. Spring Example: Single State Observed via JMX and Micrometer

Suppose `QueueState` is the single source of truth:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class QueueState {
    private final AtomicInteger depth = new AtomicInteger();
    private final AtomicLong processed = new AtomicLong();

    public void enqueued() {
        depth.incrementAndGet();
    }

    public void completed() {
        depth.updateAndGet(current -> Math.max(0, current - 1));
        processed.incrementAndGet();
    }

    public int depth() {
        return depth.get();
    }

    public long processedTotal() {
        return processed.get();
    }
}
```

This state holder prevents two independent measurements from contradicting each other. Register it in Spring:

```java
@Configuration
public class QueueConfiguration {
    @Bean
    public QueueState queueState() {
        return new QueueState();
    }
}
```

Next, create an MBean facade:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "company.queue:type=QueueMonitor,name=orders"
)
public class QueueJmxMonitor {
    private final QueueState state;

    public QueueJmxMonitor(QueueState state) {
        this.state = state;
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return state.depth();
    }

    @ManagedAttribute
    public long getProcessedTotal() {
        return state.processedTotal();
    }
}
```

A configuration bean registers the facade and enables annotation export:

```java
@Configuration
@EnableMBeanExport
public class QueueJmxConfiguration {

    @Bean
    public QueueJmxMonitor queueJmxMonitor(QueueState state) {
        return new QueueJmxMonitor(state);
    }
}
```

This snippet illustrates Spring Framework JMX; you need to import annotations from `org.springframework.context.annotation` and configure an appropriate `MBeanServer` in the application. With Spring Boot auto-configuration already active, adding `@EnableMBeanExport` manually is not necessarily required; avoid creating two exporters registering the same ObjectName.

## 7. Registering a Gauge from the Same QueueState

A configuration using `MeterRegistry`:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueMetricsConfiguration {

    @Bean
    public QueueMetricsBinder queueMetricsBinder(
            QueueState state,
            MeterRegistry registry) {

        return new QueueMetricsBinder(state, registry);
    }

    static final class QueueMetricsBinder {
        QueueMetricsBinder(QueueState state, MeterRegistry registry) {
            Gauge.builder("orders.queue.depth", state, QueueState::depth)
                .description("Current queue depth")
                .baseUnit("tasks")
                .tag("queue", "orders")
                .register(registry);
        }
    }
}
```

This code is illustrative: in a larger project, a dedicated `MeterBinder` is usually more appropriate because it centralizes meter registration logic and makes testing easier.

Lifecycle note: `QueueMetricsBinder` holds `QueueState` via a field or other reference to ensure the measured object stays alive. In the example above, ensure `QueueState` is a Spring singleton and lives throughout the registry lifecycle.

Both the MBean `QueueDepth` and the Micrometer gauge `orders.queue.depth` read the same state. When using both, designate **registry metrics** as the source for time-series dashboards and the JMX getter as a local administrative inspection path. If this JMX attribute is also scraped as a second metric, plan carefully to avoid double counting.

## 8. Counters Should Increment at the Event, Not Read an Arbitrary Cumulative Number

If `QueueState.processedTotal()` increments when a job completes, it is an internal counter. You have two approaches:

### Approach 1: Record a Micrometer Counter right where the event occurs

```java
@Service
public class QueueWorker {
    private final QueueState state;
    private final Counter processedCounter;

    public QueueWorker(QueueState state, MeterRegistry registry) {
        this.state = state;
        this.processedCounter = registry.counter(
            "orders.processed",
            "queue", "orders"
        );
    }

    public void completedOneJob() {
        state.completed();
        processedCounter.increment();
    }
}
```

This approach works well when all events pass through the instrumented code path and counter semantics are clear.

### Approach 2: Expose cumulative state as a FunctionCounter

In some cases where an existing state counter is available, you can use `FunctionCounter` with an object holding a monotonically increasing count:

```java
FunctionCounter.builder(
    "orders.processed",
    state,
    QueueState::processedTotal
).tag("queue", "orders")
 .register(registry);
```

FunctionCounter is appropriate when the source value is monotonic over its lifecycle. If `processedTotal` can reset due to an operation or object re-creation, the backend and export logic must handle counter resets properly.

Do not use a `Gauge` for a cumulative count and expect the system to automatically infer a counter rate correctly in all cases. Choose the meter according to the data semantics.

## 9. Integrating Existing MBeans via a JMX Collector

If a legacy Java application already has MBeans but lacks Micrometer, metrics can be collected from JMX via a collector/exporter.

```text
Legacy Java Application
   |
   +-- MBeanServer
          |
          +-- java.lang:type=Memory
          +-- company.queue:type=QueueMonitor,name=orders
          |
       JMX exporter / collector
          |
       Prometheus-compatible metrics
          |
       Metrics backend
```

A collector can use the JMX API to read:

```java
ObjectName name = new ObjectName(
    "company.queue:type=QueueMonitor,name=orders"
);

Number depth = (Number) connection.getAttribute(
    name, "QueueDepth"
);
```

Then convert it into a gauge metric sample. ObjectName/attribute must be mapped to metric name, labels, and unit. This mapping depends on the collector type. **There is no universal YAML configuration** that works for every JMX exporter.

For the Prometheus JMX exporter, there are multiple deployment modes such as Java agent or standalone collector, depending on version and architecture; each mode has different connection and security mechanisms. Choose based on the deployment environment rather than opening a public remote JMX port.

### 9.1. When Is a JMX Collector Better Than Modifying the Application?

- Legacy applications with minimal source code changes.
- The JVM/library already exposes comprehensive MBeans.
- The team wants to collect metrics quickly from existing sources.
- There is a requirement to monitor platform MBeans of a third-party service.
- Existing operations need to be linked with a new monitoring backend.

### 9.2. When Is Direct Micrometer Better?

- You have permission to modify the Spring application.
- Rich timers/histograms/tags are needed.
- You want to control metric naming and units directly in code.
- Context such as outcome/status is needed that MBeans do not provide.
- You want to reuse meters across multiple registries/backends.

In new systems, Micrometer is usually the right choice for instrumentation; JMX remains useful for management operations and runtime diagnostics.

## 10. Mapping ObjectName to Metric Name and Labels

JMX identifies via ObjectName:

```text
company.queue:type=QueueMonitor,name=orders
```

A metrics backend might receive:

```text
orders_queue_depth{queue="orders",service="checkout"} 12
```

This is an illustrative example and does not mean every exporter generates this name automatically. You must decide the mapping:

| JMX Component | Metric Component | Example |
|---|---|---|
| Domain | Prefix or namespace | `company.queue` → `orders_` |
| `type` | Meter family / label | `QueueMonitor` |
| `name` | Source label | `queue="orders"` |
| Attribute | Metric semantics | `QueueDepth` → `queue_depth` |
| Unit | Metric unit/base unit | Tasks, seconds, bytes |
| ObjectName instance | Instance label | `instance="worker-1"` if needed |

Metric naming should remain stable across deployments and avoid changing merely because a Java class name is refactored. If an ObjectName changes from `name=orders` to `name=primary`, collector rules or labels may change; dashboards and alerts will need a migration plan.

## 11. Metric Type, Unit, and OpenData

JMX attributes come in many forms:

- `int`, `long`, `double`, `boolean`.
- `String`, enum, or status values.
- `CompositeData` and `TabularData` from MXBeans/OpenTypes.
- Arrays or object data converted by JMX per contract.

Not every value maps directly to a numeric time series.

For example, `java.lang:type=Memory` has `HeapMemoryUsage` of type `CompositeData`, containing fields such as `used`, `committed`, `max`, and `init`.

A collector might select:

```text
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
```

However, each field must be checked: `max` may have a special sentinel value when the limit is undefined; do not treat every value as a valid byte count for calculating percentages.

For booleans, interpretation is a metric convention, for instance `1` for true and `0` for false. For multi-value states such as `RUNNING`, `PAUSED`, `FAILED`, use an encoding/tag with controlled cardinality rather than putting arbitrary free-form messages into labels.

## 12. Cardinality: An Often Overlooked Risk

Cardinality is the number of distinct time series generated by combinations of metric names and label values.

Example:

```text
orders_processed_total{queue="orders",outcome="success"}
orders_processed_total{queue="orders",outcome="failure"}
```

Cardinality here is small and bounded.

However, if you add labels like `userId`, `orderId`, `requestId`, or `sessionToken`, the number of time series can grow unboundedly with the number of users/transactions:

```text
orders_processed_total{orderId="O-000001"}
orders_processed_total{orderId="O-000002"}
...
```

The consequences are increased memory, storage cost, scrape time, and query latency, as well as potential exposure of sensitive data.

JMX ObjectNames sometimes contain key properties generated dynamically per instance/request. When turning ObjectName properties into metric labels, **do not copy all keys unconditionally**. Choose labels with a finite set of values such as `queue`, `outcome`, `region`, or `worker_pool` when needed.

A good label policy:

1. Does not contain user IDs, session IDs, credentials, or transaction data.
2. Has a reasonable and predictable number of values.
3. Avoids free-form values such as exception messages.
4. Does not store per-request object IDs.
5. Is documented and kept stable across upgrades.
6. Enforces series limits and alerts on cardinality when thresholds are exceeded.

## 13. Avoiding Duplicate Collection of JVM Metrics

A JVM can provide memory/GC/thread metrics from:

- Platform MXBeans via a JMX collector.
- Micrometer JVM binders in Spring Boot Actuator.
- Another Java agent or vendor monitoring agent.

If all three paths export equivalent metrics, the backend may store three sets of measurements with different names and labels. This may not cause an immediate error, but dashboards can confuse sources or double-count.

Example:

```text
JMX collector -> jvm_memory_used_bytes
Micrometer    -> jvm_memory_used_bytes
Other agent   -> vendor_jvm_heap_used
```

If they share the same semantics and target, designate a primary owner for dashboards/alerts. When keeping multiple pipelines for comparison, use explicit source labels and do not aggregate them as three separate JVMs.

### 13.1. Comparing Metrics Does Not Mean Summing Them

A safe migration approach:

```text
In staging:
  Micrometer series A
  JMX collector series B
  Compare A vs B by timestamp/scope

In production:
  Choose A as the primary source
  Use B only for diagnostics or disable redundant collection
```

Counters can reset on process restarts, gauges sample at two different instants, and timer histograms may have different bucket configurations. Therefore, do not expect all values to match identically at all times.

## 14. Metrics Do Not Replace JMX Operations

MeterRegistry is primarily for recording measurements, not a system for invoking management operations with side effects. JMX can provide operations:

```java
@ManagedOperation
public void pauseConsumers() {
    queueController.pause();
}
```

A `Counter` or `Gauge` cannot replace the ability to call `pauseConsumers()`. When both viewing state and performing management actions are needed, you can:

- Use Micrometer for time-series metrics.
- Use restricted JMX MBeans for management operations.
- Protect connectors and operations with authorization.
- Audit log critical commands.
- Avoid exposing sensitive operations under the same privileges as a scraping account if unnecessary.

This is why the **monitoring plane** and **management plane** should be separated architecturally, even though both relate to application observability.

## 15. JMX Notifications and the Metrics Registry

JMX notifications are pushed events, not time-series metrics by default. A listener can translate notifications into counts:

```java
NotificationListener listener = (event, handback) -> {
    if ("company.queue.threshold.exceeded".equals(event.getType())) {
        registry.counter(
            "queue.threshold.events",
            "queue", "orders"
        ).increment();
    }
};
```

This approach is useful when the event is operationally meaningful and there is no direct instrumentation point. However, consider:

- Notifications can be lost before the listener is registered.
- The same event may arrive at multiple registrations and be double-counted.
- Reconnecting does not automatically replay history.
- Event types and payloads can change between versions.
- Listener callbacks must not block or execute heavy backend queries.

If an event represents an important business transaction, instrument directly where the event originates or use durable messaging rather than relying on JMX notifications as the sole counter source.

## 16. Metadata and Inspecting via MBeanServer

To verify source metrics before configuring a collector:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "company.queue:type=QueueMonitor,name=orders"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

Include only appropriate **readable attributes** in the collector. Do not read writable attributes merely because they are writable; writable attributes may still be readable, but they carry control semantics and may contain sensitive data.

Avoid calling JMX operations such as `resetCounters`, `clearCache`, or `restartService` to collect metrics. A collector should read state, not mutate state.

## 17. Testing via MeterRegistry in Unit Tests

With Micrometer, use `SimpleMeterRegistry` to test instrumentation without a real backend.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter(
    "worker.jobs.completed",
    "queue", "orders"
);

counter.increment();
counter.increment();

double value = registry.get("worker.jobs.completed")
    .tag("queue", "orders")
    .counter()
    .count();

assertEquals(2.0, value);
registry.close();
```

`assertEquals` needs to be imported from JUnit. In a test, close the registry using `try-with-resources` if the implementation supports `AutoCloseable`, or use `finally`.

This test proves the meter is registered and increments as expected; it **does not prove that the Prometheus endpoint is exposed** or that a real collector has scraped it.

## 18. Integration Test: JMX and Registry Observing the Same State

A suitable test:

1. Create `QueueState`.
2. Create a Spring context with `QueueJmxMonitor` and the exporter.
3. Use a dedicated test MBeanServer.
4. Register a `Gauge` from the same `QueueState` into `SimpleMeterRegistry`.
5. Mutate state using `enqueued()`/`completed()`.
6. Read `QueueDepth` via JMX.
7. Read the `orders.queue.depth` gauge via the registry.
8. Assert both values reflect the updated state.
9. Close the Spring context, registry, and release the MBeanServer.

Conceptual example:

```java
state.enqueued();
state.enqueued();

int jmxDepth = (Integer) server.getAttribute(
    objectName, "QueueDepth"
);

double micrometerDepth =
    registry.get("orders.queue.depth")
        .tag("queue", "orders")
        .gauge()
        .value();

assertEquals(2, jmxDepth);
assertEquals(2.0, micrometerDepth);
```

Because this is an integration test with a local server/registry, there is no need to enable a remote JMX connector. If using Spring Boot, `@SpringBootTest` may automatically create additional metrics; consider using a smaller context to isolate the exact contract being tested.

## 19. Metrics Pipeline and Dashboards

A complete metrics system has the following stages:

```text
Application instrumentation
       |
MeterRegistry
       |
Registry export / scrape endpoint
       |
Collector (e.g., Prometheus)
       |
Time-series storage
       |
Dashboard + Alert rules
```

Checkpoints at each layer:

| Layer | What to check |
|---|---|
| Application | Counter increments and gauge updates properly |
| MeterRegistry | Meter name/tags/type exist |
| Export endpoint | Data is emitted in the expected format |
| Scrape | Target is UP and scrape succeeds |
| Backend | Series appears with valid timestamps |
| Dashboard | Queries use the right metric name/labels |
| Alert | Thresholds and missing-data behavior are correct |

With a JMX collector, replace the first layer with `MBeanServer → JMX collector`, while the backend/dashboard layers remain similar.

**An application starting successfully does not prove metrics have reached the backend.** Any layer can fail due to security, configuration, naming, network, or selectors.

## 20. Units, Rates, and Resets

Durations may be recorded in nanoseconds in code but exported in seconds at the backend; memory bytes may be exported with a unit suffix such as `_bytes`; Prometheus counters commonly have a `_total` suffix. Actual names depend on the registry/exporter and naming conventions.

Do not guess units from short names without metadata.

### Counter resets

When the JVM restarts, an in-memory counter typically resets to 0. Time-series backends may provide `rate()` or `increase()` functions that handle resets appropriately. Do not naively subtract `current - previous` while ignoring restarts.

### Gauges and rates

A `queue_depth` gauge can increase and decrease; taking a rate of a gauge does not mean the same thing as event throughput. If throughput is needed, create a `jobs_completed_total` counter and compute its rate.

### Latency

Timers/histograms require understanding base units and bucket configurations. A `p99` computed per instance cannot always simply be averaged across instances to get a system-wide p99. Histogram bucket aggregation or appropriate statistics may be required.

## 21. Cost and Performance Risks

Monitoring is not free:

- JMX getters may execute on the collector/JMX server thread and cause load if they query a database or traverse a large object graph.
- Micrometer gauge functions may be invoked during scraping, so their logic must be fast and safe.
- Timer percentiles/histograms increase series count and memory cost.
- High-cardinality tags increase storage costs.
- Overly frequent collector scraping increases CPU/network usage.
- Multiple exporters reading the same resource can multiply observability load.

Good design practices:

1. Getters/gauges read snapshot values already updated by business flows.
2. Do not hold long locks inside metrics callbacks.
3. Bound tag values.
4. Choose an appropriate scrape interval.
5. Use sampling when needed for tracing/logging instead of placing every request into metric labels.
6. Do not export raw exception messages or user data.
7. Implement timeouts and stale/unavailable states when the source stops returning data.

## 22. Security for JMX and Metrics Endpoints

JMX can expose operations that alter runtime behavior, while metrics endpoints can reveal application structure, service names, or dependency health. Both require access control.

### JMX

- Do not open remote JMX ports publicly.
- Use authentication and TLS/protected channels appropriately.
- Restrict `invoke` and `setAttribute` permissions for monitoring accounts.
- Export only necessary MBeans and avoid secrets.
- Manage credentials, truststores, and network policies.

### Metrics endpoints

- Expose `/actuator/prometheus` only to authorized collectors/network segments.
- Consider a separate management port/path protected by network rules.
- Do not include user IDs, tokens, or request payloads in tags.
- Monitor series count and ingestion cost.
- Do not treat a metrics endpoint as completely “non-sensitive” merely because it is typically read-only.

Separate read-only monitoring from management operations whenever possible. A metrics scraping account should not by default have permission to reset counters, reload configuration, or restart workers over JMX.

## 23. Common Pitfalls

### 23.1. JConsole sees the MBean, but Prometheus has no metric

MBean registration and metrics export are two separate paths. A collector or Micrometer registry must be configured to send data to Prometheus. Enabling Spring JMX alone does not create `/actuator/prometheus`.

### 23.2. /actuator/metrics has numbers, but /actuator/prometheus does not work

The Prometheus registry dependency may be missing, the endpoint may not be exposed, the management port/path may differ, or security may be blocking it. Check the effective configuration and endpoint availability.

### 23.3. Gauge is always 0 or NaN

Check whether the observed object is still alive, whether the callback reads the right state, and whether the data source actually changes. If the state object was recreated while the gauge still holds the old reference, the value will not behave as expected.

### 23.4. Counter drops after restart

In-memory counters reset on process restart. Use appropriate backend rate/increase functions and distinguish metric resets from business errors.

### 23.5. Metric is double-counted

The same measurement may be exported through both Micrometer and a JMX collector. Establish clear ownership and unified mapping; do not sum two series reflecting the same source.

### 23.6. Dashboard loses data after changing ObjectName

The JMX collector selector may no longer match the new name, or metric labels may have changed. Check `queryNames`, collector rules, metric series, and dashboard queries.

### 23.7. Cardinality explodes

Do not put `orderId`, `userId`, `requestId`, or dynamic ObjectName properties into metric labels. Use finite, rule-controlled labels.

### 23.8. JMX getter causes overload

Getters doing heavy reads or holding long locks allow the collector to impact production. Replace them with lightweight snapshot counters/gauges, caching, and controlled scrape intervals.

### 23.9. Reading MXBean OpenData with incorrect mapping

`CompositeData` and `TabularData` require selecting specific fields with appropriate types and units. Do not force the entire object into a single numeric value.

### 23.10. Assuming Micrometer replaces all of JMX

Micrometer is very strong for metrics, but it does not directly replace every JMX management operation or notification. The two mechanisms solve different problems.

## 24. Hands-On Exercises

**Exercise 1 — One state, two views.** Create `QueueState`, export `QueueDepth` via JMX and the `orders.queue.depth` gauge via SimpleMeterRegistry. Mutate the state and verify both values.

**Exercise 2 — Counter throughput.** Instrument `orders.processed` with a Counter on the event path. Read the counter in a test, then explain how Prometheus can compute a rate after scraping.

**Exercise 3 — JMX collector mapping.** Take `company.queue:type=QueueMonitor,name=orders` and `QueueDepth`. Design the metric name, labels, unit, and type. Explain what happens if the ObjectName changes.

**Exercise 4 — Cardinality.** Compare the label `queue=orders` with `orderId=<id>`; estimate the number of series as orders grow. Design a replacement using an aggregated counter.

**Exercise 5 — Double collection.** Simulate the same count exported through both Micrometer and a JMX exporter. Write a rule selecting a primary source for dashboards to prevent double counting.

**Exercise 6 — Spring Boot Actuator.** Add Actuator + Prometheus registry, expose the appropriate endpoint, and inspect `/actuator/prometheus`. Compare with the MBeans in JConsole.

**Exercise 7 — Event notifications.** Create a threshold JMX notification and a listener that converts the event type into a counter. Discuss lost events and duplicate delivery.

**Exercise 8 — Monitoring security.** Design separate policies for a read-only metrics endpoint and high-privilege JMX operations. Do not use hard-coded credentials.

**Exercise 9 — JVM binders.** Inspect Micrometer's memory/GC/thread metrics alongside platform MXBeans. List semantically duplicate measurement pairs to avoid collecting them twice.

**Exercise 10 — CI test.** Write an integration test using a dedicated test MBeanServer and SimpleMeterRegistry, verifying ObjectName/attribute/metric name/tags as well as lifecycle cleanup.

## 25. Self-Check Questions

1. How do a JMX MBean and a Micrometer MeterRegistry differ in purpose?
2. Why is not every JMX attribute suitable as a counter?
3. Should QueueDepth be a gauge or a counter?
4. When should FunctionCounter be used?
5. Why might a JMX collector be suitable for a legacy application?
6. Why should you not export the same JVM metric through multiple pipelines and sum them?
7. What risks do high-cardinality tags introduce?
8. How should `CompositeData` from an MXBean be handled?
9. How does `/actuator/metrics` differ from `/actuator/prometheus`?
10. When should JMX operations be kept instead of being replaced by metrics?
11. Why does a missing `queue_depth` metric not mean queue depth is 0?
12. How can a test verify that JMX and Micrometer both read the same state accurately?

## 26. Key Takeaways

**JMX and a metrics registry complement each other.** JMX provides the JVM's management surface, while Micrometer/MeterRegistry standardizes and exports metrics as time series for dashboards and alerts. Existing MBeans can be read via a JMX collector, or code can be instrumented directly with Micrometer.

When combining them, choose a primary data source, define accurate metric types and units, control tags/cardinality, prevent double counting, verify the entire pipeline to the backend, and secure both JMX connectors and metrics endpoints. The ultimate goal is accurate observability without introducing unnecessary overhead or risk surface.
