# Recording Metrics for Listeners in Spring Framework Application Events

When using **Spring Framework Application Events**, a single `ApplicationEventPublisher.publishEvent(...)` call can trigger one or more `@EventListener` methods. If a listener is slow, fails repeatedly, or builds up a work backlog, looking only at publisher logs makes it hard to pinpoint where the issue lies. **Recording metrics for listeners** lets you measure **processing counts, success/failure rates, execution duration, in-flight work, queue depth, and retries** in a way that can be aggregated, alerted on, and tested.

One point to remember before implementing:

> **Spring Framework does not automatically create Micrometer Observations for every `@EventListener` call.** To have dedicated metrics per listener, the application must add instrumentation (such as `MeterRegistry`/`Timer`/`Counter` or `ObservationRegistry`) at the right spots. Enabling Actuator does not automatically turn all Spring Application Events into listener metrics.

This practice uses **Spring Framework 6.2**, **Micrometer**, Java 17+, and a runnable program to record metrics for a synchronous listener. It then expands to Spring Boot Actuator/Prometheus, `@Async`, `@TransactionalEventListener`, testing approaches, and dashboard design criteria.

## 1. Identify What to Measure Before Writing Code

An event flow within a request has distinct milestones:

```text
HTTP request / use case
      |
      +-- publishEvent(OrderPlaced) -----> publish duration
               |
               +-- Listener A starts --> listener processing duration
               |                              success / failure
               |
               +-- Listener B starts --> listener processing duration
               |                              success / failure
               |
               +-- async listener submitted --> queue waiting time
                                                    |
                                                    +-- worker start
                                                    +-- worker complete
      |
      +-- transaction commit / rollback
```

**Signals do not mean the same thing:**

| Milestone / signal | What has it proven? | What has it not proven? |
| --- | --- | --- |
| `publishEvent` called | Publisher asked Spring to emit the event | Listener processed successfully |
| `publishEvent` returned | Publisher call path finished under current config | All async listeners have finished |
| Listener `started` | One listener execution began | Event finished processing |
| Listener `completed` successfully | One attempt finished without throwing | Business transaction committed or external side effect delivered |
| Transaction `AFTER_COMMIT` triggered | Source transaction committed | Post-commit callback sent notification successfully |
| Message sent to broker | Broker/producer acknowledged per contract | Downstream consumer completed business work |

In the **default synchronous** multicaster, `publishEvent(...)` duration includes the duration of synchronous listeners, not just Spring's dispatch overhead. If a listener has `@Async` or a custom multicaster uses an executor, publish duration usually reflects only the submit/dispatch step, not total worker processing time.

Therefore, a good dashboard must measure **where work actually executes**, not only the event-publishing API.

## 2. Appropriate Metrics for Listeners

### 2.1. Counter: Counting Executions and Errors

A `Counter` is a **monotonically increasing** count in the registry while the program runs. Design example:

```text
app.event.listener.completed{event.type="OrderPlaced",
                             listener="InvoiceProjection",
                             outcome="success"} = 120

app.event.listener.completed{event.type="OrderPlaced",
                             listener="InvoiceProjection",
                             outcome="error"} = 5
```

These numbers are purely **illustrative**. If the application restarts, local counters reset; time-series backends normally compute **rate/increase** over time and handle counter resets with dedicated semantics.

A counter should increment **when an attempt completes**, not unconditionally at the start of the method and labeled "processed successfully". If you want to measure started events, use a separate `started` metric, or measure in-flight work and completions properly.

Never call `counter.increment()` in both `catch` and `finally` for the same failure: that double-counts.

### 2.2. Timer: Duration of a Single Execution

A `Timer` measures the **duration** of completed operations while also providing statistics like `count` and `totalTime`. In Micrometer, `Timer.Sample.start(registry)` records the start time using the registry's clock, and `sample.stop(timer)` records the duration into the chosen timer.

```java
Timer.Sample sample = Timer.start(meterRegistry);
try {
    doWork();
} finally {
    sample.stop(timer);
}
```

This is **illustrative code**, requiring a `meterRegistry` bean, a `timer` meter, and a `doWork` method. `finally` ensures the metric is still recorded when `doWork` throws an exception. To separate success and error durations, select the timer by outcome **at stop time**, such as `outcome="success"` or `outcome="error"`.

**Do not use `Counter` to measure duration** and do not use `DistributionSummary` when the measurement represents duration: `Timer` models time units appropriately. Never record an absolute timestamp as a duration metric.

### 2.3. Gauge: In-Flight Work or Backlog

A `Gauge` represents a **current value**: number of currently executing listeners, queue size, pending outbox rows, or unprocessed jobs. It is usually backed by a stateful object/source:

```java
// Skeleton example: AtomicInteger inFlight is retained long-term by a Spring bean.
Gauge.builder("app.event.listener.inflight", inFlight, AtomicInteger::get)
        .tag("listener", "InvoiceProjection")
        .register(meterRegistry);
```

This is **illustrative code**, requiring `Gauge`, `AtomicInteger`, and `meterRegistry`. Micrometer gauges normally hold a **weak reference** to the state object, so `inFlight` must be strongly referenced by the bean; if the object is garbage-collected, the metric can disappear or report NaN.

A `Gauge` does not replace a `Counter` because it does not retain total historical executions. For backlogs in brokers/outboxes, **read real state from the queue** rather than incrementing/decrementing a local variable and assuming it stays accurate across crashes.

### 2.4. LongTaskTimer: Long-Running In-Progress Work

`LongTaskTimer` is useful when you want to know **how many long-running tasks are currently active and their cumulative elapsed time**, such as consumers processing large files, batch projections, or long workflows. A `Timer` normally records when a task **finishes**; hence a stuck task does not yet appear in the duration histogram.

You do not need `LongTaskTimer` for every few-millisecond listener. Instrument it selectively where tasks are long-lived and observation overhead is acceptable.

### 2.5. Which Metric Should Be Used?

| Operational question | Appropriate metric | Notes |
| --- | --- | --- |
| How many times did the listener complete? | `Counter` by outcome | Do not confuse attempts with logical events |
| What is the 5-minute error rate? | Rate/increase of error counter divided by total | Define denominator and window clearly |
| How long does listener processing take? | `Timer` duration histogram/p95/p99 | Requires histogram/percentile config if percentiles are needed |
| How many listeners are running right now? | `Gauge`/`LongTaskTimer` | Do not infer from counter sums |
| Is the executor filling up? | Queue depth, active threads, task rejections | Not provided automatically by `@EventListener` alone |
| Are events stuck after commit? | Outbox pending age, retry backlog, delivery latency | Measure at worker/broker, not just producer |
| How many times was one logical event retried? | Separate attempt counter and terminal success counter | Use stable event ID for correlation in logs/traces |

## 3. Tag Design: Low Cardinality First

Metrics are useful when filterable by event type, listener, and outcome, yet every tag combination can create a separate time series. Strictly bound **cardinality**.

**Recommended low-cardinality tags:**

- `event.type`: a **bounded set** of names like `OrderPlaced`, `InvoiceIssued`.
- `listener`: a stable logical name like `InvoiceProjection` or `EmailNotification`.
- `outcome`: `success`, `error`, optionally `cancelled` when genuinely needed.
- `error.category`: `validation`, `timeout`, `database`, `external`; derived from a classifier with bounded values.
- `phase`: `sync`, `after_commit`, or `async_worker` when operationally meaningful.

**Do not use as metric tags:**

- `eventId`, `orderId`, `customerId`, or `traceId`.
- Email, username, unbounded IP addresses, tokens/credentials.
- Full URLs containing IDs, free-form exception messages, or serialized payloads.
- Dynamically generated listener names per unbounded instance/user/tenant.

Example: 6 event types × 8 listeners × 3 outcomes = **144 tag combinations** before even adding error categories, environments, or histogram buckets. Adding `orderId` with millions of values can cause **time-series explosion** in the metrics backend, spiking RAM and storage costs.

**Event IDs still matter for tracing**, so place them in **structured logs/traces (high-cardinality metadata)** rather than low-cardinality metric tags. In Spring Observations, `highCardinalityKeyValue(...)` has a distinct purpose from `lowCardinalityKeyValue(...)`; never arbitrarily turn high-cardinality data into meter labels.

## 4. Complete Java 17+ Example: `Timer` and `Counter` Inside `@EventListener`

This example uses Spring Framework **6.2.9** and Micrometer Core **1.14.9**. No Spring Boot, HTTP server, or Prometheus is needed; `SimpleMeterRegistry` stores measurements in memory for learning and testing.

We publish two `InvoiceIssued` events:

- `id=101`: the listener processes successfully.
- `id=102`: the listener throws `IllegalStateException` to simulate a failing projection; it still records **failure** and **timer** metrics in `finally`, then propagates the cause to the publisher.

Because the default multicaster is synchronous, output ordering is deterministic. The program prints only **counts**, avoiding unstable nanosecond durations.

### 4.1. Directory Structure

```text
event-listener-metrics-demo/
├── pom.xml
└── src/main/java/example/EventListenerMetricsDemo.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-listener-metrics-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.14.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.EventListenerMetricsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. src/main/java/example/EventListenerMetricsDemo.java

```java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventListenerMetricsDemo {

    public record InvoiceIssued(long id) {}

    public static final class InvoiceProjectionListener {
        private final MeterRegistry registry;

        // Register meters with a bounded tag set at bean creation time.
        private final Counter successCounter;
        private final Counter errorCounter;
        private final Timer successTimer;
        private final Timer errorTimer;

        public InvoiceProjectionListener(MeterRegistry registry) {
            this.registry = registry;
            this.successCounter = newCounter(registry, "success");
            this.errorCounter = newCounter(registry, "error");
            this.successTimer = newTimer(registry, "success");
            this.errorTimer = newTimer(registry, "error");
        }

        private static Counter newCounter(
                MeterRegistry registry, String outcome) {
            return Counter.builder("demo.event.listener.calls")
                    .description("Completed listener attempts")
                    .tags(
                            "event.type", "InvoiceIssued",
                            "listener", "InvoiceProjection",
                            "outcome", outcome)
                    .register(registry);
        }

        private static Timer newTimer(
                MeterRegistry registry, String outcome) {
            return Timer.builder("demo.event.listener.duration")
                    .description("Execution duration of listener attempts")
                    .tags(
                            "event.type", "InvoiceIssued",
                            "listener", "InvoiceProjection",
                            "outcome", outcome)
                    .register(registry);
        }

        @EventListener
        public void onInvoiceIssued(InvoiceIssued event) {
            Timer.Sample sample = Timer.start(registry);
            boolean success = false;

            try {
                if (event.id() == 102L) {
                    System.out.println(
                            "listener: failed invoice=" + event.id());
                    throw new IllegalStateException(
                            "projection unavailable");
                }

                System.out.println(
                        "listener: processed invoice=" + event.id());
                success = true;
            } finally {
                // finally runs even when the listener throws an exception.
                sample.stop(success ? successTimer : errorTimer);
                if (success) {
                    successCounter.increment();
                } else {
                    errorCounter.increment();
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        InvoiceProjectionListener listener(SimpleMeterRegistry meterRegistry) {
            return new InvoiceProjectionListener(meterRegistry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            context.publishEvent(new InvoiceIssued(101L));

            try {
                context.publishEvent(new InvoiceIssued(102L));
            } catch (IllegalStateException ex) {
                System.out.println(
                        "publisher: caught " + ex.getMessage());
            }

            MeterRegistry registry =
                    context.getBean(SimpleMeterRegistry.class);

            long successCalls = Math.round(registry
                    .get("demo.event.listener.calls")
                    .tag("outcome", "success")
                    .counter().count());

            long errorCalls = Math.round(registry
                    .get("demo.event.listener.calls")
                    .tag("outcome", "error")
                    .counter().count());

            long successDurations = registry
                    .get("demo.event.listener.duration")
                    .tag("outcome", "success")
                    .timer().count();

            long errorDurations = registry
                    .get("demo.event.listener.duration")
                    .tag("outcome", "error")
                    .timer().count();

            System.out.println(
                    "metrics: success=" + successCalls
                    + " error=" + errorCalls
                    + " timer.success=" + successDurations
                    + " timer.error=" + errorDurations);
        }
    }
}
```

Run in the project directory with **JDK 17+** and Maven:

```bash
mvn -q compile exec:java
```

Lines printed by **the program**, in order (excluding Spring/Maven logs):

```text
listener: processed invoice=101
listener: failed invoice=102
publisher: caught projection unavailable
metrics: success=1 error=1 timer.success=1 timer.error=1
```

### 4.4. Mechanism and Result Explanation

1. `DemoConfig` declares a `SimpleMeterRegistry` and an `InvoiceProjectionListener` Spring bean. Spring detects `@EventListener` when `ApplicationContext` initializes.
2. `context.publishEvent(new InvoiceIssued(101L))` uses the default synchronous multicaster; the listener prints the success line, `success` becomes `true`, and the `finally` block records exactly **one timer sample** and **one counter increment** with `outcome=success`.
3. For `id=102`, the listener prints the failure line and throws `IllegalStateException`. The `finally` block still executes, recording `errorTimer` and `errorCounter`; the exception is **not swallowed**.
4. The publisher catches `projection unavailable` because the listener runs synchronously and no `ErrorHandler` suppresses exceptions.
5. `SimpleMeterRegistry` returns both counters/timers tagged with `outcome=success/error`. Counts for each branch equal 1; timer `count` is the number of **completed samples**, not milliseconds.
6. Actual durations can vary across runs. We **do not print them** so stdout does not depend on machine speed.
7. Meters are **registered once in the constructor**, avoiding building and looking up meters on every incoming event. That is a good optimization for high-frequency listeners when the tag set is finite.

### 4.5. Why Doesn't the Example Need an Exporter?

`SimpleMeterRegistry` is an **in-memory** registry used for demos and tests. Its measurements **are not sent to Prometheus automatically**. In a Spring Boot deployment, inject the Boot-managed `MeterRegistry` instead of creating a `SimpleMeterRegistry` in production; backend exporters and Actuator are configured separately.

The example also **opens no database transaction**, uses no `@Async`, and implements no retries. Thus it demonstrates measuring **execution outcomes** on a synchronous listener, not commits/rollbacks or delivery to external systems.

### 4.6. Extended Practice

Modify the error condition:

```java
if (event.id() == 102L) {
    throw new IllegalStateException("projection unavailable");
}
```

Then replace event `102` with `103`. You will see one more success sample instead of a failure, assuming the publisher makes one more call. Never adjust outcome metrics manually before logic runs; metrics must reflect **the real execution path**.

Try removing the `finally` block to observe how metrics can be lost on exception paths. Then restore `finally` and confirm both error timer and counter are recorded. This exercise clarifies why both success and failure paths must be instrumented.

## 5. From Direct Meters to Micrometer Observation

Micrometer offers two suitable approaches:

**Approach A — Instrument metrics directly:** use `MeterRegistry`, `Timer`, and `Counter` as in the example. Advantages include fewer layers and explicit meter/tag names; suitable when only metrics are needed.

**Approach B — Instrument an `Observation`:** use `ObservationRegistry`/`Observation` for a unified operation concept. Depending on configured handlers, an observation can emit **both metrics and traces** without writing separate code per backend.

Example of a listener in a **Spring Boot application with `ObservationRegistry`**:

```java
@Component
public class CustomerProjectionListener {
    private final ObservationRegistry observationRegistry;
    private final CustomerProjectionService projection;

    public CustomerProjectionListener(
            ObservationRegistry observationRegistry,
            CustomerProjectionService projection) {
        this.observationRegistry = observationRegistry;
        this.projection = projection;
    }

    @EventListener
    public void onCustomerChanged(CustomerChanged event) {
        Observation.createNotStarted(
                        "application.event.listener",
                        observationRegistry)
                .lowCardinalityKeyValue("event.type", "CustomerChanged")
                .lowCardinalityKeyValue("listener", "CustomerProjection")
                .highCardinalityKeyValue("event.id", event.eventId())
                .observe(() -> projection.update(event));
    }
}
```

This is **illustrative integration code**, not a file runnable alongside `EventListenerMetricsDemo`; types `CustomerChanged`, `CustomerProjectionService`, and imports for `@Component`, `Observation`, and `ObservationRegistry` must be supplied by the application.

`observe(...)` manages the observation lifecycle around the handler code, records errors, and closes the scope properly. However, to emit meters, `ObservationRegistry` must have an **ObservationHandler** that creates metrics, such as `DefaultMeterObservationHandler`. Spring Boot Actuator can auto-configure required handlers based on dependencies; plain Spring Framework applications must configure one manually when choosing Observation over `MeterRegistry` directly.

**Do not use both A and B to measure the same operation with the same name/tags without an explicit design.** If Observation already emits a Timer, adding a manual Timer alongside it can cause dashboards to double-count and report skewed latencies.

### 5.1. Manually Configuring Metrics for Observation in Plain Spring

**Standalone illustrative snippet** (requires `micrometer-observation` and `micrometer-core` dependencies and proper imports):

```java
SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

observations.observationConfig().observationHandler(
        new DefaultMeterObservationHandler(meters));

Observation.createNotStarted("application.event.listener", observations)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "OrderListener")
        .observe(() -> handleOrder());
```

With this handler registered, a completed observation contributes a **timer** to `MeterRegistry`. This snippet is not a full app; `handleOrder()` is just a placeholder for application work and must be implemented in a real project.

### 5.2. `@Observed` and AOP

Micrometer provides `@Observed`. Depending on your Spring Boot/AOP version and configuration, you can instrument methods via `ObservedAspect` or annotation-observation support. Never assume simply adding `@Observed` to `@EventListener` automatically produces metrics.

**Illustrative integration example**:

```java
@Observed(
        name = "application.event.listener",
        lowCardinalityKeyValues = {
            "event.type", "OrderPlaced",
            "listener", "Projection"
        })
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    projectionService.apply(event);
}
```

To make it take effect, verify:

- Are Spring AOP/AspectJ and `ObservedAspect` registered in configuration?
- Through which **proxy** does Spring actually invoke the method; is there self-invocation bypassing advice?
- If manual custom observations are also used, is there **double instrumentation**?
- Do annotation tags have **bounded cardinality**?
- Do tests observe the exact expected meters and sample counts?

With Spring Boot, `management.observations.annotations.enabled=true` is supported in applicable versions depending on dependency/proxy infrastructure; follow the docs for your exact application version.

## 6. Integrating with Spring Boot Actuator and Prometheus

In a Spring Boot application, typically add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
```

This is a **dependency fragment** for a Spring Boot project that already has dependency management; it is not a standalone `pom.xml`. Boot manages the Micrometer version via its BOM.

Suggested configuration in `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.application.event.listener=true
management.metrics.distribution.slo.application.event.listener=100ms,500ms,1s
```

The `application.event.listener` names here assume the application uses an **Observation/Timer with that exact name**; `EventListenerMetricsDemo` above uses its own meter `demo.event.listener.duration`, so **do not copy these SLO properties expecting them to affect a different name**. When using a Timer directly, replace the property suffix with **the actual meter name**.

You can inspect:

- `/actuator/metrics`: list of recorded meters. Endpoints must be explicitly exposed and should not be public by default.
- `/actuator/metrics/application.event.listener` or `/actuator/metrics/demo.event.listener.duration` depending on the meter in your app.
- `/actuator/prometheus`: Prometheus-formatted output when `micrometer-registry-prometheus` is present and the endpoint is exposed.
- Grafana/Prometheus dashboards: request rates, error ratios, and histogram quantiles per listener.

**Securing endpoints:** Actuator can expose system names, tags, and runtime details. Never expose sensitive endpoints to the public internet for debugging. Enforce authentication/authorization, network restrictions, and proper scraping config.

### 6.1. Consistent Metric Naming

Example convention for **application-defined metrics**, not metrics auto-generated by Spring:

| Meter name | Type | Meaning |
| --- | --- | --- |
| `app.event.listener.duration` | Timer | Duration of each listener attempt |
| `app.event.listener.completed` | Counter | Completed attempts by outcome |
| `app.event.listener.inflight` | Gauge | Currently executing listeners |
| `app.event.listener.queue.depth` | Gauge | Backlog in the observed executor |
| `app.event.listener.rejected` | Counter | Tasks rejected by executor |
| `app.event.delivery.end_to_end` | Timer | Time from event emission/commit to final processing |
| `app.event.retry.attempts` | Counter | Retry attempts at worker/broker |
| `app.event.outbox.pending` | Gauge | Pending outbox events |

When using a Micrometer Observation named `application.event.listener`, meter names may derive from that name; some registries/exporters **transform names** (e.g., dots to underscores, unit suffixes). Query `/actuator/metrics` using **the Micrometer name**, and verify the exported name in Prometheus rather than guessing.

### 6.2. Percentiles, Histograms, and SLOs

To examine p95/p99 durations, understand:

- `Timer.count`/`totalTime` does not automatically yield p95/p99 in every registry.
- Client-side percentiles can help for a single instance, yet usually **cannot be accurately aggregated** across instances.
- Histogram buckets allow backends like Prometheus to compute **aggregated quantile estimates** via `histogram_quantile`, depending on bucket layout and retention.
- SLO buckets at 100 ms / 500 ms / 1 s reveal the fraction of attempts exceeding specific thresholds.
- Histograms multiply time series; enable them only for critical listeners/metrics.
- With too few samples, p99 is noisy. Never conclude "listener is healthy" simply because zero errors occurred over a couple of minutes.

Do not directly compare p95 of **listener processing duration** with p95 of **end-to-end event latency** when async/queues exist. They measure two different quantities.

### 6.3. Illustrative PromQL

Assuming the exporter produces `app_event_listener_completed_total` with the configured labels:

```promql
sum by (listener) (
  rate(app_event_listener_completed_total{outcome="error"}[5m])
)
/
clamp_min(
  sum by (listener) (
    rate(app_event_listener_completed_total[5m])
  ),
  1e-9
)
```

This is **illustrative PromQL**; metric names depend on naming conventions and exporters. When the denominator is 0, the expression relies on `clamp_min` and can report 0 during zero traffic; dashboards should also display throughput and handle "no data" intervals. Never use this ratio alone to infer availability at low sample volumes.

If histogram buckets exist for duration, p95 can be computed:

```promql
histogram_quantile(
  0.95,
  sum by (le, listener) (
    rate(app_event_listener_duration_seconds_bucket[5m])
  )
)
```

Prerequisite: histogram metrics are actually exported under that name with `le` and `listener` labels. This query will not run against the demo's `SimpleMeterRegistry` (which has no Prometheus exporter).

## 7. Synchronous Event Listeners: Where Metrics Measure and Transaction Impact

With the default `SimpleApplicationEventMulticaster`, listeners run **synchronously on the publisher thread**. Example:

```text
HTTP Request Span
  |
  +-- @Transactional OrderService
        |
        +-- publishEvent(OrderPlaced)
              |
              +-- AuditListener  [Timer A]
              +-- EmailListener  [Timer B]
              +-- Projection    [Timer C]
        |
        +-- COMMIT / ROLLBACK
```

In this setup:

- Each listener's duration usually **adds directly to the request's waiting time**.
- If a listener performs slow I/O inside the transaction, it holds DB connections/locks longer and drives up p95/p99 for other requests.
- If a listener throws `RuntimeException` and it is not suppressed, the error can propagate to the publisher and trigger a transaction rollback per policy.
- A `Timer` with `outcome="success"` at the end of a listener **does not prove the transaction committed**; the transaction can roll back after the listener returns.
- If an earlier listener throws and stops multicasting early, later listeners may record **zero samples** because they were never invoked. Never interpret missing samples as "0ms success".

Certain business-critical steps belong in explicit service calls rather than hiding synchronous dependencies in event listeners. Metrics reveal the cost, but do not by themselves fix transaction coupling.

## 8. Async and Executors: Metrics Must Be Measured on the Worker

A listener:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event);
}
```

is **illustrative integration code**, requiring `@EnableAsync`, an executor, and application types. When `@Async` is active, handler code runs on another thread. Placing a `Timer` **only around `publishEvent(...)`** may measure only **scheduling/submission**, missing `notificationService.send` duration.

Instrument **inside the listener body** on the worker:

```text
event published (T0)
      |
      +-- submit task (T1)
              |
              +-- task waits in executor queue
                         |
                         +-- worker start (T2)
                                 |
                                 +-- listener handling
                                 |
                                 +-- worker finish (T3)

publish duration      = T1 - T0 (approx)
queue waiting time    = T2 - T1
listener duration     = T3 - T2
event completion lag  = T3 - T0
```

This is a conceptual timing model. Within one JVM, `System.nanoTime()` can measure **durations** from a single clock source; `Instant`/UTC timestamps suit events crossing processes, though subject to system clock drift. Across brokers or multiple hosts, event completion lag requires understanding clock skew and establishing an explicit start-timestamp contract.

### 8.1. Metrics on `ThreadPoolTaskExecutor`

In applications using `ThreadPoolTaskExecutor`, monitor:

- Active thread count, pool size, and queue depth.
- Rejected task count.
- Queue wait time when end-to-end latency matters.
- Consumer/worker successes, failures, and timeouts.
- Shutdown backlog during application termination.

Executor metrics do not automatically equal `listener completed`: a task can be rejected before the method starts. If **zero event loss** is required, an in-memory executor is insufficient; consider a durable queue or Transactional Outbox.

### 8.2. `ThreadLocal`, MDC, and Tracing Context

Another thread may lack the publisher's context/trace ID. In Spring, you can use `ContextPropagatingTaskDecorator` with the Micrometer Context Propagation library:

```java
@Bean("eventExecutor")
ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
```

This is an **illustrative integration configuration**, not part of the Section 4 Maven demo. It requires proper imports and dependencies; context accessors/tracing handlers must be configured. `TaskDecorator` propagates supported contexts, yet **does not transfer the publisher's database transaction to workers** and does not provide durable delivery.

**Listener metrics do not strictly require trace context**, since meter tags are registered explicitly on the listener. However, to trace from an error-rate spike back to **the failing event ID**, structured logging/tracing with correlation IDs is valuable.

### 8.3. Recording Error Metrics for Async

For `@Async` returning `void`, exceptions can route through `AsyncUncaughtExceptionHandler` rather than propagating to the publisher. Therefore:

- Place `try/finally`/Observation around work **inside the async listener**.
- Record `outcome=error` before passing the error to async exception handling.
- Never increment "success" merely when a task is submitted.
- If the caller holds a `CompletableFuture`/`Future`, track terminal completion appropriately via the API rather than equating scheduler acceptance with business success.
- If the queue rejects a task, record a **rejected** metric at the submit/exception handler rather than conflating it with a listener processing failure.

## 9. Transaction-Bound Events: Before Commit Differs from After Commit

`@TransactionalEventListener` has these phases:

| Phase | When callback runs | Correct metric interpretation |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit | Listener success does not guarantee final commit |
| `AFTER_COMMIT` | After successful commit | Measures post-commit side effect; failure does not roll back committed transaction |
| `AFTER_ROLLBACK` | After rollback | Records rollback handling, not business success |
| `AFTER_COMPLETION` | After commit or rollback | Must include transaction outcome if distinguishing commit vs. rollback |

Example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted(
                    "application.event.after_commit",
                    observationRegistry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "Notification")
            .observe(() -> notificationService.send(event));
}
```

This is **illustrative integration code**, requiring appropriate beans and imports. If notification fails in `AFTER_COMMIT`, the order transaction **has already committed**. `outcome=error` reflects the **notification attempt**, not a transaction rollback.

By default, `@TransactionalEventListener(fallbackExecution = false)` **does not run when there is no active transaction**. Thus listener metrics may stay empty even though the publisher called `publishEvent(...)`. Never blindly fix that by enabling `fallbackExecution=true` if it alters business semantics.

When using **reactive transactions**, transaction context resides in Reactor Context; do not assume imperative `ThreadLocal` semantics match reactive transactions. Follow the proper `TransactionalEventPublisher`/transaction-context contract when using reactive transaction-bound events.

### Where Should Commit Outcomes Be Measured?

If the question is "how many orders committed?", you cannot simply count successful `@EventListener` runs. Measure outcomes at **the transaction boundary** or from a committed business source (DB/outbox/CDC) with corresponding guarantees.

A `publishEvent(...)` call inside a transaction may succeed even though the transaction rolls back later. Conversely, an `AFTER_COMMIT` listener can fail after the DB already committed. Dashboards should separate two metric groups: **business commits** and **side-effect processing**.

## 10. Retries: Count Attempts and Logical Events Separately

Suppose event `evt-42` is processed three times by a worker:

```text
evt-42 attempt 1 -> timeout
evt-42 attempt 2 -> timeout
evt-42 attempt 3 -> success
```

If each attempt increments listener success/error counters, we observe:

```text
listener_attempts{outcome="error"}   += 2
listener_attempts{outcome="success"} += 1
logical_events_completed            += 1
```

These are **illustrative metric meanings**, not names automatically created by Spring.

Do not report "three events processed" just because three attempts occurred. **One logical event** can retry several times before succeeding or moving to a dead-letter queue. With Kafka/RabbitMQ/outbox:

- Measure attempts at the **consumer worker**, not only the producer.
- Use a stable `eventId` for correlating logs/traces and idempotency; **do not put `eventId` in metric labels**.
- Monitor retry backlog, oldest pending age, dead-letter count, and final success/exhaustion.
- Consumers must be idempotent because a worker can process an event and crash before ack/offset commit.
- During prolonged retries, attempt counts climb while logical successes may remain flat.

**Double counting:** If both `@EventListener` and a service retry wrapper are instrumented, clarify which metric counts *attempts* and which counts *logical completions*. Never merge both under one name and treat it as a business success rate.

## 11. Designing Actionable Alerts and SLOs

A dashboard should answer:

1. **Throughput:** how many listener attempts/sec complete? Did it suddenly drop to 0 while the publisher is still active?
2. **Error rate:** is the `error` ratio rising relative to total attempts? Is traffic sufficient to judge?
3. **Latency:** p95/p99 listener processing duration—is it breaching thresholds?
4. **Backlog:** for async/outbox/brokers, is pending event age exceeding budget?
5. **Rejections/failures:** are executor rejections, broker-publish errors, or retry exhaustion/DLT climbing?
6. **Business impact:** are end-to-end event completion and transaction commit outcomes meeting SLAs?

**Hypothetical SLO example**, not a Spring standard:

```text
ProjectionListener:
  - 99% of attempts succeed over 5 minutes, when >=100 samples exist
  - p95 processing duration < 250 ms
  - oldest pending item in queue < 5 s
  - zero silently dropped mandatory events
```

An alert watching only error rate can miss a listener that stopped running altogether (since zero calls produce zero errors). Add **missing-traffic** or backlog/age alerts whenever an independent event source exists for comparison. For listeners that run rarely by design, avoid context-free "zero events in 1 minute" alerts.

**Label and histogram budgets:** enabling histograms for every event type, every listener, and every deployment can cause massive time-series growth. Start with listeners that have critical SLOs, and pick buckets matching real latency distributions.

## 12. Testing Metrics: Verify Logic, Not Absolute Nanoseconds

An instrumentation bug may not break the service, yet it breaks dashboards. Test both **meter state** and **business behavior**.

### 12.1. Unit Tests with `SimpleMeterRegistry`

Goals:

- A successful event records exactly one success counter increment and one success timer sample.
- A failing event records exactly one error counter increment and one error timer sample; the exception still propagates per contract.
- No metric tag is created per event ID.
- Meters are registered with stable names, types, and tags.
- No double counting occurs on nested calls or retries.

**JUnit 5 snippet** integrating with the Section 4 class:

```java
@Test
void recordsFailureMetricsAndPropagates() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    EventListenerMetricsDemo.InvoiceProjectionListener listener =
            new EventListenerMetricsDemo.InvoiceProjectionListener(registry);

    assertThrows(IllegalStateException.class,
            () -> listener.onInvoiceIssued(
                    new EventListenerMetricsDemo.InvoiceIssued(102L)));

    assertEquals(1.0, registry
            .get("demo.event.listener.calls")
            .tag("outcome", "error").counter().count());

    assertEquals(1L, registry
            .get("demo.event.listener.duration")
            .tag("outcome", "error").timer().count());
}
```

This is a **test snippet**, not inside `EventListenerMetricsDemo.java`. It requires JUnit 5, `@Test`, and static imports `assertThrows`/`assertEquals`. The test demonstrates that **metrics are recorded even when the code throws**, though it does not prove Spring registered `@EventListener`.

### 12.2. Spring Integration Tests

Use `@SpringJUnitConfig` or `@SpringBootTest` to verify:

1. The listener bean actually exists in `ApplicationContext`.
2. Publishing an event of the right type invokes the method.
3. Counter/timer increments by exactly one sample, without duplication from duplicate bean registrations.
4. Synchronous/async exception propagation matches the design.
5. With `@TransactionalEventListener`, test phases under real transaction commits and rollbacks.
6. With `@Async`, wait using `CountDownLatch`/test executor/completion signals; never use `Thread.sleep` to guess the event ran.
7. With Spring Boot metric exporters, the endpoint exposes the exact expected metric name and tags after listener execution.

`spring-test`'s `@RecordApplicationEvents` can verify **event publication**, yet does not replace asserting that the listener completed and recorded meters. If a listener is outside component scanning, the event is still published in the context while zero listener samples are recorded.

### 12.3. Testing Cardinality and Sensitive Data

Publish several events with different `orderId` values and assert that the list of registered meters/tags **does not grow with the number of order IDs**. That catches cardinality bugs early.

Check:

- No passwords, access tokens, customer emails, or sensitive payloads appear in tags.
- Dynamic exception messages do not become tag values.
- `event.type` and `listener` come from controlled sets, never raw user input.
- Each event attempt emits exactly one completion signal; failure recording in `finally` never masks the original exception.

## 13. Common Mistakes When Instrumenting Listener Metrics

**1. Measuring only `publishEvent(...)` and calling it listener latency.**  
When synchronous, it aggregates multiple listeners; when async, it may measure only submission. Measure inside each listener/worker.

**2. Believing Spring automatically emits metrics for every `@EventListener`.**  
It does not by default. Manual `MeterRegistry`/Observation instrumentation or explicit configuration is required.

**3. Incrementing the success counter as soon as the listener starts.**  
A subsequent error will still be reported as success. Choose the outcome once processing finishes.

**4. Forgetting `finally` when timing.**  
On exception paths, the timer is never stopped, leaving duration stats without failure samples.

**5. Swallowing exceptions so `error` metrics never appear.**  
That alters transaction semantics and creates misleading reports. Record the metric and propagate when business rules require it.

**6. Putting event IDs or customer IDs into metric labels.**  
Causes high cardinality and potential data leaks. Use traces/logs instead of tags.

**7. Dynamically naming metrics per class instance or per request.**  
`MeterRegistry` accumulates unbounded meter IDs, making capacity hard to manage. Use stable names and finite tags.

**8. Re-registering the same meter repeatedly on hot paths.**  
While registries cache meters by ID, creating builders and lookups repeatedly still adds overhead. Cache meter references when the tag set is fixed.

**9. Using one Timer for both handler and broker delivery and interpreting them as the same latency.**  
Processing duration differs from queue latency and end-to-end completion lag; name and measure them separately.

**10. Using a `Gauge` to count historical events.**  
A gauge is a point-in-time snapshot, not a cumulative counter. Use a `Counter`.

**11. Printing exact durations and asserting fixed milliseconds in stdout.**  
Timings depend on the scheduler, JVM, and GC. Assert only counts, synchronous contract order, or bounded thresholds where appropriate.

**12. Adding `@Observed` in a project without an AOP handler and assuming metrics exist.**  
The annotation may not be intercepted. Verify real meters in integration tests.

**13. Double-measuring with both `@Observed` and a manual Timer.**  
When both instrument the same operation, duplicate samples/measurements occur. Keep metric ownership in one place.

**14. Seeing a success timer and concluding the order committed.**  
A synchronous listener can run before the transaction rolls back. Measure commit outcomes at the proper boundary.

**15. Failing to monitor rejected tasks for async listeners.**  
A rejected task never runs, so listener timers/errors show nothing. Instrument the submission/executor path.

**16. Enabling histograms on every metric and tag set.**  
Can generate excessive buckets/time series and increase costs. Enable them selectively for listeners with clear SLOs.

**17. Looking only at averages.**  
A handful of very slow requests can be hidden by a low average. Combine throughput, error rate, and p95/p99.

**18. Ignoring missing-data alerts.**  
A listener that stops being registered/scanned can produce **zero metrics** rather than rising error counters. Cross-check against expected event volume and source backlogs.

## 14. Practical Workflow for Production Applications

In a Spring Boot project, you can roll this out in order:

1. **Select listeners to instrument:** business-critical, typically slow, retried, or performing external side effects.
2. **Define the metric contract:** stable names, units, types, allowed tags, and meaning of outcomes and attempts.
3. **Place instrumentation at the right boundary:** inside listener execution, not just around `publishEvent`; if async, measure on the worker.
4. **Configure registry/exporter:** Spring Boot Actuator + appropriate backend; do not secretly create a `SimpleMeterRegistry` as a production registry when Boot already manages one.
5. **Preserve error semantics:** `finally`/Observation records failures too; do not swallow exceptions or turn mandatory listeners into best-effort ones.
6. **Bound cardinality:** inspect actual meter IDs before deploying; avoid tags derived from dynamic inputs.
7. **Test with `SimpleMeterRegistry`/`TestObservationRegistry`:** success, failure, rollback/after-commit, and async paths.
8. **Verify in staging:** check meter names on `/actuator/metrics`, sample counts, tags, and exporter transformations.
9. **Build dashboards/alerts:** error ratio, p95 latency, missing-traffic alerts where appropriate, queue lag, rejections, and retries.
10. **Load test:** measure instrumentation overhead, time-series counts, histogram size, and throughput impact.
11. **Verify reliability:** if events must survive process crashes, pair with an outbox/broker and measure terminal delivery; metrics do not replace durability.
12. **Review periodically:** clean up unused meters, update SLOs, and ensure no tags contain PII.

## 15. Self-Check Questions

**1. Does Spring `@EventListener` automatically generate metrics?**  
No. Spring Framework does not create an Observation for each `@EventListener` call by default. The application must add appropriate instrumentation.

**2. Which meter type measures a listener's execution duration?**  
`Timer`; you can use `Timer.Sample.start(...)`, choose the timer at the end by outcome, and call `stop(...)` inside `finally`.

**3. Why isn't `Timer.count()` a number of milliseconds?**  
Because it is the number of recorded samples. Duration comes from `totalTime(...)`, `max(...)`, or configured histograms/percentiles.

**4. Should `eventId` be placed in the `event.type` or `listener` tag?**  
No. Event IDs have virtually unbounded cardinality; they belong in structured logs/traces, not metric tags.

**5. Why doesn't a listener success metric prove the transaction committed?**  
Because a synchronous listener can run inside an uncommitted transaction that later rolls back.

**6. If an `@Async` listener fails while the publisher returns normally, where should the failure be measured?**  
Inside the listener body running on the worker and/or in the completion/error handler, not solely from the publisher response.

**7. Can `SimpleMeterRegistry` be used for demos/tests without Prometheus?**  
Yes. It stores meters in memory for asserting counts/timers, though it does not export metrics to a monitoring system.

**8. How does `Observation` differ from a direct `Timer`?**  
`Observation` is an operation abstraction that can attach both metric and tracing handlers; a direct `Timer` only records durations in `MeterRegistry`.

**9. Why can't you alert only when the error counter increases?**  
Because a mis-scanned/unregistered listener bean or stalled executor can yield **zero samples** while the system is broken. Pair with expected-volume, backlog, and missing-data alerts.

**10. When retries exist, how should success rate be calculated?**  
Clarify whether you are measuring by **attempts** or by **logical events**. Never mix both definitions in a single metric.

## 16. Official Documentation

- [Spring Framework — Observability Support, Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2 — Application Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer — Timers and Timer.Sample](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

