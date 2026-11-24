# Synchronizing JMX Values into a Monitoring System in Spring Framework

## 1. The Real-World Problem

Spring Framework allows exporting application state as JMX attributes and operations. For example, an MBean managing a queue has the attributes `PendingJobs`, `FailedJobs`, `Enabled`, and `LastSuccessTimestamp`. Operators can view them with JConsole, but manually opening JConsole does not scale to monitoring dozens or hundreds of JVMs.

We need to **synchronize JMX values into monitoring data**: periodic sampling, transforming identifiers and data types, storing time series, building dashboards, triggering alerts, and verifying collected data quality.

```text
Spring application
    |
    +--> MBeanExporter
    |         |
    |         v
    |      MBeanServer
    |         |
    |         +--> JMX collector / javaagent
    |                    |
    |                    v
    |              metrics endpoint
    |                    |
    |                    v
    |               monitoring system
    |                    |
    |             dashboard / alerts
    |
    +--> Micrometer metrics (alternative path)
                     |
                     v
                metrics registry
```

Both the JMX and Micrometer paths can coexist. You must know which metric is the primary data source to avoid duplication and mismatches in naming, cardinality, and semantics.

After this lesson, you will be able to:

1. Design a pipeline to feed JMX attributes into a monitoring system.
2. Distinguish between polling, scraping, notifications, and push.
3. Select appropriate MBeans/attributes for metrics.
4. Map `ObjectName` and attributes to metric names, labels, and values.
5. Distinguish gauge, counter, timestamp, enum/status, and histogram.
6. Understand the roles of JMX Exporter, Prometheus, Micrometer, and Spring Boot Actuator.
7. Control latency, missing data, connection failures, and security.
8. Write tests to verify the JMX contract and collection pipeline.
9. Design dashboards and alerts based on real operational signals.

## 2. What Does “Synchronizing” Mean Here?

Synchronizing JMX values does not necessarily mean instant replication. In monitoring systems, the most common mechanism is periodic **sampling** at fixed intervals.

Example:

```text
T=00s: PendingJobs = 12
T=15s: PendingJobs = 18
T=30s: PendingJobs = 7
T=45s: PendingJobs = 0
```

The monitoring system stores these measurement points as a time series. If the queue spikes to 100 and drops back to 18 between two scrapes, 15-second polling may **never observe the peak of 100**.

You must distinguish:

- **Current state:** the attribute value at the moment of reading.
- **Sample:** the value observed during a single collection.
- **Time series:** samples sharing the same metric name and labels.
- **Notification:** an event/state-transition signal, not durably stored by default.
- **Event/audit record:** an event history when full accuracy is required.

Do not describe metric scraping as a guaranteed-delivery mechanism for every state change.

## 3. Common Collection Architectures

### 3.1. JMX Exporter Java Agent and Prometheus

A common architecture runs JMX Exporter as a Java agent inside the application JVM, allowing it to read JMX MBeans and expose metrics on an HTTP endpoint for Prometheus to scrape.

```text
Spring JVM
   |
   +-- MBeans in platform MBeanServer
   |
   +-- JMX Exporter javaagent
          |
          v
   HTTP /metrics endpoint
          |
          v
      Prometheus
          |
          v
     Dashboard + alerts
```

This is an **in-process** collection model, unlike Prometheus connecting directly to JMX/RMI. The javaagent reads MBeans inside the process and does not necessarily require opening a remote JMX connector.

### 3.2. Standalone Collector via Remote JMX

A separate collector can connect via `JMXConnector` to a JMX/RMI endpoint.

```text
Application JVM
   |
   v
JMX/RMI connector
   |
   v
Standalone collector
   |
   v
Metrics backend
```

This approach decouples the collector from the application, but requires handling networking, authentication, TLS, RMI ports, reconnects, and authorization. If the collector is outside the JVM, verify that the connector is actually bound to the `MBeanServer` containing the target MBeans.

### 3.3. Spring Boot Actuator and Micrometer

Spring Boot Actuator integrates with Micrometer to provide metrics via an appropriate registry and endpoint. This instrumentation path can avoid reading JMX for metrics recorded directly by the application.

```text
Spring component
    |
    v
Micrometer MeterRegistry
    |
    +--> /actuator/prometheus (if registry/endpoint is enabled)
    +--> other supported registries
```

**JMX Exporter and Micrometer are not the same component.** If data is already recorded directly via Micrometer, consider making Micrometer the primary metric source and using JMX only for legacy data or JVM/library MBeans that have no other path.

## 4. Spring JMX Components in the Pipeline

Spring Framework can export a bean:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicLong;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Checkout")
public class CheckoutQueueMonitor {

    private final AtomicLong enqueued = new AtomicLong();
    private final AtomicLong completed = new AtomicLong();

    @ManagedAttribute(
        description = "Current checkout jobs waiting")
    public long getPendingJobs() {
        return Math.max(0L, enqueued.get() - completed.get());
    }

    @ManagedAttribute(
        description = "Total enqueued jobs since process start")
    public long getEnqueuedTotal() {
        return enqueued.get();
    }

    @ManagedAttribute(
        description = "Total completed jobs since process start")
    public long getCompletedTotal() {
        return completed.get();
    }

    public void enqueued() {
        enqueued.incrementAndGet();
    }

    public void completed() {
        completed.incrementAndGet();
    }
}
```

This is an illustrative model; if jobs can be enqueued and completed concurrently, the gauge formula must reflect the system's exact state. If a task fails or is canceled, the completed counter alone is insufficient to infer pending count; production code must define clear semantics and avoid negative or inconsistent values.

For annotations to work, an appropriate exporter must be configured, such as Spring's `@EnableMBeanExport` or an `AnnotationMBeanExporter` in the right ApplicationContext. Annotating a class alone does not guarantee the MBean is registered.

A collector then reads:

```text
ObjectName:
  com.example.orders:type=Queue,name=Checkout

Attributes:
  PendingJobs
  EnqueuedTotal
  CompletedTotal
```

and converts them into appropriate metrics.

## 5. Classifying Metric Types

| JMX attribute | Value type | Suggested metric | Notes |
|---|---|---|---|
| `PendingJobs` | `long` | Gauge | Can increase/decrease |
| `EnqueuedTotal` | `long` | Counter-like | Increases monotonically over process lifetime |
| `CompletedTotal` | `long` | Counter-like | Can reset when the JVM restarts |
| `Enabled` | `boolean` | Gauge 0/1 | Needs a clearly defined state |
| `LastSuccessTimestamp` | Epoch seconds | Gauge timestamp | Clear unit and timezone |
| `State` | String/enum | Enum mapping or info metric | Do not turn arbitrary strings into labels |
| `ProcessDuration` | `long` | Gauge if only last duration | Do not infer a histogram from a single value |
| `ErrorRate` | `double` | Gauge | Must know window and denominator |

You cannot turn an attribute that only holds the latest value into a latency distribution histogram. If you want P95/P99, instrument an actual histogram/timer or collect buckets/counts/sums with proper semantics.

### 5.1. Counters Can Reset

JMX counters are typically accumulated from JVM startup. When a process restarts, the value returns to 0. Prometheus provides functions such as `rate()`/`increase()` to handle counter resets in certain cases, but the metric must retain counter semantics and stable labels.

Do not subtract two samples and treat a negative difference as a business error if a restart occurred. Combine process start time, reset semantics, and collector status.

### 5.2. A Gauge Is Not a Counter

`PendingJobs` can decrease as workers finish jobs. Using a counter for it produces misleading interpretations because counters are expected to only increase except on resets. Choosing the right metric type makes charts and alerts meaningful.

## 6. Mapping ObjectName and Attributes to Metrics

A JMX identifier:

```text
com.example.orders:type=Queue,name=Checkout
```

can be converted into:

```text
app_queue_pending_jobs{queue="Checkout"} 12
app_queue_enqueued_total{queue="Checkout"} 1870
app_queue_completed_total{queue="Checkout"} 1858
```

A mapping must decide:

1. Metric namespace/prefix.
2. Metric name including unit.
3. Which labels come from ObjectName properties.
4. Which attributes are selected/excluded.
5. Metric type (gauge/counter).
6. Name normalization rules.
7. Handling of missing/null/non-numeric values.

**Do not automatically turn every key property into a label.** An ObjectName can contain an instance ID, UUID, session ID, or high-cardinality values.

### 6.1. Cardinality

If `queue` has 5 values, metrics produce few series. If `requestId` has one million values, attaching it as a label can overload the backend.

Rules:

- Use labels for low-variation dimensions: `module`, `queue`, `region`, `role`.
- Avoid `userId`, `requestId`, UUIDs, or random instance identities.
- Do not put tokens, emails, or raw messages into labels.
- Review mappings when adding new MBeans or key properties.
- Configure appropriate sample/series limits at the collector/backend.

## 7. Example JMX Exporter Mapping Configuration

A YAML example **illustrating the rule structure** for reading attributes from MBeans with matching domain and properties:

```yaml
rules:
  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>PendingJobs'
    name: app_queue_pending_jobs
    type: GAUGE
    labels:
      queue: '$1'

  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>EnqueuedTotal'
    name: app_queue_enqueued_total
    type: COUNTER
    labels:
      queue: '$1'

  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>CompletedTotal'
    name: app_queue_completed_total
    type: COUNTER
    labels:
      queue: '$1'
```

Pattern syntax and how JMX Exporter represents ObjectNames/attributes depend on its version, especially for ObjectNames with additional key properties, quoting, and sanitization. In real deployments, you must run the exact exporter version in use and inspect the `/metrics` output; this example does not replace verifying that rules match. In environments with complex metadata, use specific rules and restrict attributes to prevent unintended exposure.

### 7.1. Javaagent Startup

Formal example:

```bash
java -javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent.jar=9404:/etc/jmx-exporter/config.yaml \
  -jar app.jar
```

File names and flag syntax must be checked against the JMX Exporter version in use. In container deployments, port 9404 may be published unintentionally; restrict network exposure. Do not use this example to blindly expose a public endpoint.

### 7.2. Sample Output

```text
# HELP app_queue_pending_jobs Current pending jobs
# TYPE app_queue_pending_jobs gauge
app_queue_pending_jobs{queue="Checkout"} 12
# TYPE app_queue_enqueued_total counter
app_queue_enqueued_total{queue="Checkout"} 1870
```

Verify metric naming, labels, values, HELP/TYPE, and actual series count. If a metric is missing, check JMX registration, rule matching, and collector logs before editing the dashboard.

## 8. Direct Polling with MBeanServerConnection

Not every system uses Prometheus. You can write a collector that reads JMX periodically.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxSampler {
    private final MBeanServerConnection connection;
    private final ObjectName name;

    public JmxSampler(MBeanServerConnection connection,
                      ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public long pendingJobs() throws Exception {
        Object value = connection.getAttribute(
            name, "PendingJobs");

        if (!(value instanceof Number number)) {
            throw new IllegalStateException(
                "PendingJobs is not numeric: " +
                (value == null ? "null" : value.getClass()));
        }
        return number.longValue();
    }
}
```

A caller can use `ScheduledExecutorService` to run periodically:

```java
ScheduledExecutorService scheduler =
    Executors.newSingleThreadScheduledExecutor();

scheduler.scheduleWithFixedDelay(() -> {
    try {
        long pending = sampler.pendingJobs();
        metricsRecorder.recordPending(pending);
    } catch (Exception ex) {
        metricsRecorder.recordCollectionFailure(ex);
    }
}, 0, 15, TimeUnit.SECONDS);
```

`sampler` and `metricsRecorder` must be injected/defined. `scheduleWithFixedDelay` runs the next cycle after the previous one finishes and the delay has elapsed; it reduces the risk of overlapping runs on a single scheduler thread. Shut down the scheduler properly according to lifecycle and avoid logging sensitive payloads.

### 8.1. Local and Remote MBeanServerConnection

`MBeanServer` implements `MBeanServerConnection`, so a local collector can use:

```java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
```

With a remote connector, obtain the connection via `JMXConnector` and configure security. Remote `getAttribute` calls can fail due to TLS, RMI ports, authentication, network partitions, or server restarts. Do not expose remote JMX on the Internet just for a collector to read a gauge.

## 9. Choosing the Scrape Interval

Collection frequency must balance temporal accuracy against cost.

| Sampling interval | Advantages | Trade-offs |
|---|---|---|
| 1–5 seconds | Sensitive to short fluctuations | High read/JMX/metrics load, many samples |
| 15 seconds | Common for practical monitoring | May miss brief spikes |
| 30–60 seconds | Lower load | Slower alerting and analysis |
| 5 minutes | Suitable for slow-changing metrics | Unsuitable for incidents needing early detection |

There is no single right interval for every metric. If an attribute getter reads a database or runs heavy calculations, scraping every second can push load back onto the application.

You must know:

- Is the getter O(1) or does it perform I/O?
- Is there an appropriate snapshot cache?
- Is the scrape duration shorter than the interval?
- How many targets and attributes are there?
- Do dashboards/alerts require high resolution?
- Is distribution history needed rather than just snapshots?

### 9.1. Avoiding Overlap and Thundering Herd

Hundreds of collectors polling at the top of every minute can create spikes. You can tune stagger/jitter, scrape scheduling, and concurrency limits. With Prometheus, scrape scheduling is controlled by the server; with a custom collector, schedule proactively.

## 10. JMX Getters Must Be Safe for Polling

A `@ManagedAttribute` getter may be called repeatedly without warning.

Anti-pattern:

```java
@ManagedAttribute
public int getPendingJobs() {
    return database.countPendingJobs(); // May be slow.
}
```

If the database slows down, monitoring becomes a cause of increased load.

A design that considers caching/snapshots:

```java
private final AtomicInteger pendingSnapshot =
    new AtomicInteger();

@ManagedAttribute
public int getPendingJobs() {
    return pendingSnapshot.get();
}

public void updateSnapshot(int current) {
    pendingSnapshot.set(current);
}
```

Define snapshot freshness and the update mechanism. Stale but stable data should not be presented as strict real-time data.

### 10.1. No Side Effects in Getters

A monitoring getter should not clear caches, trigger refreshes, or start write transactions. If a refresh is needed, separate it into an explicit operation with separate permissions so scraping never triggers business actions accidentally.

## 11. Missing Data, Stale Data, and Collection Errors

Scenarios:

- The MBean is not yet registered.
- The MBean is unregistered during context shutdown.
- The collector cannot find the ObjectName.
- The attribute was renamed or changed type.
- The client lacks permissions.
- The JVM/connector is unreachable.
- The scrape exceeded its timeout.
- The parser/mapping rule does not match.
- The attribute value is non-numeric.

Do not silently replace collection errors with `0`. `0` means “the queue has zero jobs,” whereas “unable to retrieve data” is a completely different state.

### 11.1. Three States to Distinguish

```text
Observed value = 0:
  collector succeeded, queue genuinely has zero jobs

No sample:
  collector failed to retrieve data

Stale sample:
  an old sample is still shown in the UI but is outdated
```

Dashboards should display target/collector health and the latest timestamp. A flat line after a JVM dies may indicate the system is holding onto stale samples instead of ingesting fresh data.

### 11.2. Prometheus `up` Metric

Prometheus uses `up` to indicate whether scraping the target succeeded. However, `up=1` only means the target is reachable and scrapable; it **does not guarantee that every JMX rule matched or every MBean attribute was collected properly**. Add checks for the presence of critical metrics and exporter errors where applicable.

## 12. Designing Meaningful Alerts

A good alert needs a clear signal, a sustained condition, and context:

```text
Queue backlog:
  app_queue_pending_jobs > 100
  sustained for 5 minutes
```

Illustrative PromQL:

```promql
app_queue_pending_jobs{queue="Checkout"} > 100
```

A rule can use `for: 5m` to reduce alerts on brief spikes:

```yaml
groups:
  - name: app-queues
    rules:
      - alert: CheckoutQueueBacklog
        expr: app_queue_pending_jobs{queue="Checkout"} > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Checkout queue backlog remains high"
```

The threshold of 100 and 5 minutes are exercise assumptions that must be tuned to actual load and SLOs. If the metric is missing because the target is down, this rule may not fire as expected; separate alerts are needed for scrape failures and metric absence.

### 12.1. Alerts for Missing Metrics

A critical metric disappearing may indicate an export/mapping failure rather than a business value of zero. Prometheus supports functions like `absent()`, though usage must account for labels and targets. Distinguish target down, exporter error, and unmatched metrics.

### 12.2. Rate-Based Alerts

If `EnqueuedTotal` and `CompletedTotal` are true counters, you can monitor:

```promql
rate(app_queue_enqueued_total[5m])
-
rate(app_queue_completed_total[5m])
```

When multiple queues/instances exist, group by appropriate labels before subtracting. The result is the average throughput delta, not the exact instantaneous `PendingJobs` value. Do not use a rate-only alert as a substitute for a backlog gauge when current queue depth is needed.

## 13. When to Use JMX Notifications Instead of Polling?

Notifications can signal when a threshold or state changes:

```text
Queue crosses threshold
        |
        v
JMX Notification
        |
        v
Event listener
        |
        v
Trigger investigation
```

However, remote notifications can be lost on disconnect, listener overload, or process restart. Therefore, a resilient pattern is typically:

1. Notification signals “state changed.”
2. Collector/client re-reads authoritative attributes.
3. Time-series monitoring continues periodic scraping.
4. If an exact event history is required, persist to a separate event log.

Do not push every request as a JMX notification and expect a monitoring backend to use it as a durable streaming system.

## 14. Comparing JMX Exporter and Micrometer

| Criterion | JMX Exporter | Micrometer |
|---|---|---|
| Reads data from | Existing MBeans/JMX metadata | Instrumented meters in the app |
| Best suited for | Legacy MBeans, JVM/third-party JMX | New application metrics |
| Naming | Rule-based ObjectName/attribute mapping | Meter names and tags |
| Metric types | Depends on mapping and JMX values | Counters, gauges, timers, distribution summaries |
| Cardinality | Must restrict ObjectName-derived labels | Must restrict tags |
| Overhead | JMX getter/collector overhead | Meter instrumentation/scrape overhead |
| Integration | Java agent/standalone exporter | Spring Boot Actuator/registries |
| Weaknesses | Complex mapping, can lose semantics | Requires instrumenting code and compatible registry |

If the application already uses a Micrometer `Counter` and JMX also exports `CompletedTotal`, it can create two metrics with the same meaning but different names and update timings. Choose one primary metric source or document the difference clearly to avoid double counting.

## 15. Testing the JMX Contract Before Mapping

An integration test can verify JMX attributes:

```java
import org.junit.jupiter.api.Test;
import javax.management.*;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class QueueJmxContractTest {

    @Test
    void expectedAttributesArePresent() throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("test");

        // Create the Spring context and inject this server into the exporter.
        // After the exporter registers CheckoutQueueMonitor:

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Checkout");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("PendingJobs")
                && a.isReadable()));

        Object value = server.getAttribute(name, "PendingJobs");

        assertTrue(value instanceof Number);
    }
}
```

This is an illustrative skeleton: the test must actually create the Spring context and exporter using the same `server` before running assertions. Creating only an empty server and asserting will not pass.

### 15.1. Testing After Changing Exporter/AOP

Adding `@Transactional` or changing the proxy strategy can alter exported metadata depending on configuration. Tests must confirm that ObjectName, attribute names, and numeric types remain stable. Monitoring mappings depend on this contract.

## 16. Testing Exporter Output

With JMX Exporter running in a lab, tests should check HTTP output:

```bash
curl -fsS http://127.0.0.1:9404/metrics
```

Then confirm:

- `app_queue_pending_jobs` is present.
- The metric has the expected value and labels.
- `gauge`/`counter` types have the right semantics.
- No dynamic labels such as request ID are present.
- No secrets appear in HELP, labels, or values.
- When an MBean unregisters, the exporter does not keep reporting stale metrics as fresh data.
- When an attribute type changes, collector errors are detected.
- Scrape duration and series count stay within limits.

Do not use a public HTTP endpoint for a “quick check” if it contains internal metrics. Test locally or through a protected management network.

## 17. Testing the Pipeline End-to-End

An integration test needs to span multiple layers:

```text
Spring test app
   |
   v
MBean registered
   |
   v
JMX Exporter mapping
   |
   v
HTTP metrics
   |
   v
Prometheus scrape (test stack)
   |
   v
Query result / alert
```

A test fixture can:

1. Start the app with a fixed server and exporter.
2. Drive queue state from 0 to 5 via a test API.
3. Verify the JMX attribute returns 5.
4. Scrape the exporter and verify the gauge equals 5.
5. Scrape through a Prometheus test container and query it.
6. Return state to 0 and verify the metric updates.
7. Restart the app and verify counter reset and labels.
8. Intentionally change ObjectName to confirm the contract test catches the breakage.
9. Verify the management endpoint is not public.
10. Clean up processes, ports, and test data.

Do not treat a `curl` returning HTTP 200 as end-to-end success if metric mappings have not been verified.

## 18. Time, Timestamps, and Timezones

Time-series systems usually attach a timestamp at scrape/ingest time. A JMX attribute like `LastSuccessTimestamp` carries its own business timestamp meaning. Distinguish:

```text
Sample timestamp:
  when the collector gathers the value

Business timestamp:
  when the last batch succeeded
```

A metric:

```text
app_worker_last_success_timestamp_seconds 1794376800
```

should use epoch seconds if the metric name ends with `_seconds`. Do not put milliseconds in a `_seconds` metric, as that will break charts and alerts.

Age since last success:

```promql
time() - app_worker_last_success_timestamp_seconds
```

If the timestamp has never been set, establish a clear convention (absent metric or sentinel value). Do not use `0` without explanation because it represents the epoch instant, not “unknown” by default.

## 19. Collecting Across Multiple JVMs and Stable Labels

In multi-instance environments, Prometheus typically adds target labels such as `job` and `instance`. JMX Exporter can add labels from ObjectNames.

Example:

```text
app_queue_pending_jobs{
  job="orders-service",
  instance="10.0.0.12:9404",
  queue="Checkout"
} 12
```

During autoscaling, `instance` can change. Service-level dashboards should aggregate by `job`, `queue`, or other durable labels.

Example:

```promql
sum by (job, queue) (app_queue_pending_jobs)
```

Do not sum across all instances if every instance exports the same duplicated global value, as that will double count. Understand whether a metric describes **per-instance state** or **cluster-wide state**.

### 19.1. Horizontal Scaling

With 10 replicas, if each replica has its own local queue size and metric, summing can reflect overall backlog if the queues do not overlap. However, if each replica queries a central database and reports the same cluster-wide pending count, summing 10 replicas multiplies it by 10. Choose `max`, `avg`, or a single source based on semantics rather than defaulting to sum.

## 20. Securing the Monitoring Pipeline

JMX can contain sensitive information and operations that alter state. A collector that only needs to read metrics should not be granted broad administrative privileges.

Principles:

1. Prefer collecting metrics via an in-process exporter or protected endpoint, avoiding opening remote JMX unnecessarily.
2. If using remote JMX, configure authentication, TLS, and network segmentation.
3. Use a read-only principal where appropriate, disallowing invocation of destructive operations.
4. Restrict metrics endpoint exposure to the monitoring network.
5. Never put secrets in ObjectNames, attribute descriptions, or metric labels.
6. Do not expose all MBeans via overly broad wildcards unnecessarily.
7. Review third-party MBeans as they may contain unexpected data.
8. Limit request rate/scrape concurrency to avoid stressing the JVM.
9. Monitor failed authentication and metric scrape errors.
10. Verify the effective configuration after deployment; container ports can be published unintentionally.

An unauthenticated `/metrics` endpoint bound only to loopback may be suitable for a sidecar in a controlled environment; do not assume that is safe if network namespaces are shared or ports are forwarded.

## 21. Common Issues and How to Diagnose Them

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| MBean appears in JConsole, but metric is missing | Rule does not match or exporter reads a different server | `MBeanInfo`, exporter logs, `/metrics` |
| Metric renamed after update | ObjectName/attribute naming changed | Contract tests |
| Metric has unexpected 0 value | Collector substitutes zero on error | Logs and raw `getAttribute` |
| Metric disappears after restart | Exporter not registered yet or ObjectName changed | Check lifecycle/identity |
| Alert does not fire when app dies | Condition only checks business gauge | Alert on `up`/absence |
| Slow scrape | Getter performs heavy I/O or too many MBeans | Thread dump and scrape duration |
| Backend series grow rapidly | High-cardinality labels | Count series by label |
| Counter drops | JVM restart or reset logic | Process start time and counter semantics |
| Total backlog is inflated | Double counting global metric across replicas | Check scope and aggregation |
| Remote collector connection error | RMI host/port, TLS, auth, network | Connector diagnostics |
| Dashboard shows flat line when app is down | Stale/cached data | Timestamp, `up`, and ingest status |
| Alert flaps repeatedly | Improper threshold/window | SLO, `for`, alert grouping |

### 21.1. An Ordered Diagnostic Workflow

```text
1. Did the Spring bean/exporter register the MBean?
2. Right ObjectName/MBeanServer?
3. Does MBeanInfo contain the attribute?
4. Does getAttribute return the right type and value?
5. Does the collector/JMX Exporter rule match?
6. Does /metrics contain the expected metric and labels?
7. Did the Prometheus scrape succeed?
8. Did the query/dashboard aggregate correctly?
9. Do alerts handle missing/stale data?
10. Are security and resource cost acceptable?
```

Do not start by editing the dashboard before the JMX source has been verified.

## 22. Production Design Checklist

- [ ] Inventory MBeans/attributes being collected.
- [ ] Every metric has a clear name, unit, type, and description.
- [ ] ObjectName and attribute names have a stable contract.
- [ ] Getters are lightweight, read-only, and side-effect-free.
- [ ] Export only necessary metrics; do not scrape everything.
- [ ] Labels contain neither high-cardinality values nor sensitive data.
- [ ] Counter resets/restarts are understood properly.
- [ ] Scrape health metrics and missing-data alerts exist.
- [ ] Interval/timeout match getter cost.
- [ ] No duplicate metrics between Micrometer/JMX.
- [ ] Integration tests cover JMX → exporter → monitoring.
- [ ] Remote connectors and metrics endpoints are secured.
- [ ] Dashboards and alerts are built on accurate semantics.
- [ ] A metric renaming and dashboard migration process exists.
- [ ] A rollback plan exists when changing exporter rules.

## 23. Hands-On Exercises

### Exercise A — Create a JMX Gauge

Create a `@ManagedResource` Spring bean with `@ManagedAttribute getPendingJobs()`. Register it via the Spring JMX exporter and verify the value using `MBeanServerConnection.getAttribute`.

### Exercise B — Exporter Mapping

Create a JMX Exporter rule mapping `PendingJobs` to `app_queue_pending_jobs` with a `queue` label. Scrape the local endpoint and compare with the raw JMX value. Check behavior when changing the ObjectName.

### Exercise C — Counter Reset

Create an incrementing `CompletedTotal`. Restart the lab app to simulate a reset, inspect the `rate` chart/query, and explain why a reset is not treated as negative business throughput.

### Exercise D — Cardinality

Add `requestId` to the ObjectName of test MBeans. Observe the series count grow when the collector uses `requestId` as a label. Fix the mapping to keep only `module` and `queue`.

### Exercise E — Missing-Data Alert

Create an alert for backlog exceeding a threshold and an alert for scrape failure. Stop the app and verify: the backlog condition alone may not trigger, but the target health alert must detect the outage.

### Exercise F — JMX and Micrometer

Instrument the same business counter with Micrometer and a JMX getter. Compare names, reset semantics, and update timing. Choose one primary source for the dashboard and justify why.

### Exercise G — Multiple Replicas

Have three instances export the same queue gauge. Practice `sum by(queue)`, `max by(queue)`, and `avg by(queue)` on a lab dataset. Explain which aggregation accurately reflects the business backlog.

## 24. Self-Check Questions

1. What is the difference between JMX polling and JMX notifications?
2. Does a JMX Exporter javaagent always require a remote JMX port?
3. Why should `PendingJobs` be a gauge?
4. When can `CompletedTotal` reset?
5. Why should a request ID not be placed in a metric label?
6. Does `up=1` guarantee that every JMX metric was collected?
7. What risks does an overly short scrape interval introduce?
8. Why should a JMX getter not perform heavy database calls?
9. What is the difference between sample timestamp and business timestamp?
10. When does summing metrics across multiple replicas cause double counting?
11. How do Micrometer and JMX Exporter differ?
12. Why are alerts for missing/stale data necessary?

## 25. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Prometheus JMX Exporter: https://prometheus.github.io/jmx_exporter/
- JMX Exporter Configuration: https://prometheus.github.io/jmx_exporter/1.4.0/http-mode/rules/
- Prometheus Metrics Concepts: https://prometheus.io/docs/concepts/metric_types/
- Prometheus Querying Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/
- Spring Boot Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer Documentation: https://docs.micrometer.io/micrometer/reference/
- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Key takeaway:** synchronizing JMX to a monitoring system means turning **JMX state into samples with clear semantics**, not replicating every event in real time. For a reliable pipeline, standardize metric types and labels, keep JMX getters lightweight, monitor missing/stale data, secure endpoints, and test from MBean to dashboard.
