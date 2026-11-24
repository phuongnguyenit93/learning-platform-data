# Error and Processing Duration Metrics in Spring Framework Application Events

## 1. Why measure Spring Application Events?

In **Observability**, having a log saying "event published" is not enough to conclude that listeners processed it successfully. An application can publish `OrderPlaced`, `PaymentReceived`, or `InventoryReserved` and have multiple listeners react. Common issues include:

- A slow listener adds latency to requests during synchronous dispatch.
- A listener fails, yet its error is logged and suppressed by an `ErrorHandler`, making the publisher think everything succeeded.
- Listeners run on a thread pool while `publishEvent()` returns before the task finishes.
- Error counts spike after a deployment, yet scattered logs make it hard to tell which event type/handler is failing.
- Part of the business logic runs after database commit; commit status and side-effect status are not the same state.

**Error and processing duration metrics** answer these questions in an aggregatable, alertable way:

1. How many times is each listener invoked?
2. How many executions succeed vs. throw an exception?
3. What is the actual latency of each listener and its p95/p99 trend?
4. Is there congestion in the executor queue?
5. How do publish, listener processing, and external work completion differ?
6. When an error occurs, can you trace by correlation ID/event ID in logs or traces to investigate?

Metrics need stable names, units, tag sets, clear measurement scopes, and consistent error observation policies. **Measurements without clear boundaries easily lead to wrong operational decisions.**

## 2. Three time boundaries to distinguish

### 2.1. `publishEvent()` call duration

With `ApplicationEventPublisher.publishEvent(event)`, you can measure the duration of the publish call itself:

```java
long start = System.nanoTime();
try {
    applicationEventPublisher.publishEvent(event);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    publisherTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
```

This is an **integration snippet**, assuming publisher, event, and Micrometer `Timer` are declared.

`System.nanoTime()` is suited for measuring **elapsed time** because it is a monotonic clock, not a calendar timestamp. Use `Instant.now()` or `System.currentTimeMillis()` for timestamps in logs/traces; do not subtract two wall-clock values and treat the result as reliable latency.

The meaning of publish duration changes by configuration:

- **Default synchronous multicaster:** `publishEvent()` covers dispatching and running synchronous listeners invoked on the publisher thread. If a listener is slow, publish is slow.
- **Multicaster with executor:** the call may cover only resolving listeners, submitting tasks, and running listeners that still execute on the publisher thread. It **does not** measure processing time of async tasks after they are enqueued.
- **Transaction-bound listener:** synchronization registration can happen at publish time, while phase execution such as `AFTER_COMMIT` happens when the transaction finishes, not necessarily inside the publish call.

Therefore, a `publishEvent latency` chart **does not replace** a handler processing duration chart.

### 2.2. Listener execution duration

This is usually the most important metric for this lesson's goal: place the measurement directly **around each handler's logic**:

```text
Listener starts
       |
       +--> capture start time / Timer.Sample
       |
       +--> validate, compute, call services, I/O if any
       |
       +--> success or exception
       |
       +--> record Timer with corresponding outcome
       +--> increment error Counter if exception is within measurement scope
       |
Listener finishes
```

Measuring at the handler reflects the time actually spent executing listener code, **excluding** queue wait time before the handler started. If a handler only enqueues a job externally and returns, a small handler duration **does not mean the job has finished**.

### 2.3. End-to-end event latency

Latency from when a business fact happens until all required side effects complete can span:

```text
Domain fact -> publish -> queue -> listener -> retry/backoff
                -> remote service / message broker -> consumer -> outcome
```

To measure **end-to-end**, you must define start/end milestones, store `eventId` and appropriate timestamps, observe both queue and remote work, and have a true completion signal. A `Timer` inside a Spring listener does not measure all those stages automatically.

Within a single process, monotonic elapsed time can be used if the same clock and measurement lifecycle apply. Across distributed systems, timestamps from different machines can drift; tracing, clock discipline, and clear measurement interpretation rules are required. Never send `System.nanoTime()` over a broker and subtract it in another process: `nanoTime` has no shared origin across JVMs/machines.

## 3. Which metric to choose: Timer, Counter, Gauge, Observation?

| Metric | Meaning | When to use |
| --- | --- | --- |
| `Timer` | Invocation count, total time, max, and histograms/percentiles if enabled | Measure duration of each listener invocation |
| `Counter` | Cumulative count, monotonically increasing | Count exceptions, retries, rejections, timeouts, or failed tasks |
| `Gauge` | Instantaneous value | Queue depth, active tasks, backlog |
| `DistributionSummary` | Distribution of non-time quantities | Payload size or batch size |
| `Observation` | API tracking an operation that can produce metrics/traces depending on handlers | When combining duration measurement with tracing/low-cardinality context |

**A Micrometer `Timer` already provides count and total time**, so you do not necessarily need an extra `Counter` for **every** success. You can use two timer series tagged `outcome=success/error` to compute success/error ratios over the same denominator. A separate error counter remains useful to:
- Categorize failure causes in a controlled way.
- Alert directly on error throughput.
- Measure errors **not tied to** a handler, such as executor rejections or conversion/publish errors.

Clearly define the unit being counted: **one listener invocation**, **one publish call**, or **one logical event finally processed**. With retries, these three are not identical.

### Naming and units

Example Micrometer-style metric name set:

| Name | Type | Meaning |
| --- | --- | --- |
| `application.events.listener.duration` | Timer | Duration of a single listener execution |
| `application.events.listener.errors` | Counter | Application exceptions recorded by listeners |
| `application.events.publish.duration` | Timer | Length of the `publishEvent` call |
| `application.events.executor.queued` | Gauge | Tasks waiting in the pool |
| `application.events.executor.rejected` | Counter | Task submissions rejected by the executor |
| `application.events.delivery.retries` | Counter | Retry attempts when sending/consuming under a dedicated mechanism |

Micrometer translates names and units according to the monitoring backend. With Prometheus, timers typically export series ending in `_seconds_count`, `_seconds_sum` (and `_seconds_bucket` when appropriate histograms are enabled); counters typically end in `_total`. Do not manually convert nanoseconds to milliseconds across multiple places when already using `Timer.record(duration, unit)` or `Timer.Sample` correctly.

## 4. Tag design: useful grouping without cardinality explosion

A practical tagging strategy:

- `event=OrderPlaced`: event **type**, bounded value set.
- `listener=OrderPlacedListener`: stable handler/consumer name.
- `outcome=success|error`: status of **one attempt**.
- `exception=IllegalArgumentException` or bounded error group when an error counter needs it.
- `phase=immediate|after_commit|after_rollback` if genuinely needed to distinguish and bounded.
- `delivery=sync|async` if meaningfully distinct and standardized by the project.

**Never place into metric tags**:
- `orderId`, `userId`, `eventId`, `correlationId`, `traceId`, or dynamic request URIs containing IDs.
- Full `exception.getMessage()`, raw SQL queries, or message payloads.
- Usernames, emails, access tokens, PII, or sensitive data.

For example: 10 event types × 8 listeners × 2 outcomes × 4 exception categories already create up to 640 metric groups before adding more dimensions. Using a million distinct `eventId` values as tags causes time series to grow with every event, inflating costs, slowing dashboards, and losing data due to backend limits.

Put high-cardinality identifiers in **structured logs or tracing spans**, never in metric labels. The same metric name should have a **consistent set of tag keys** across series, especially with Prometheus registries; if the `exception` tag exists only on error timers, it is better to keep `exception` out of the timer and reserve it for a dedicated error counter.

## 5. Runnable Java 17+ example: Micrometer Timer and Counter for `@EventListener`

The example below uses Spring Framework 6.1.21 and Micrometer Core. It produces **two events**: one succeeds, and one intentionally throws `IllegalArgumentException`. The listener:
- Uses `Timer.Sample` to time each invocation.
- Records duration in a `Timer` tagged `outcome=success` or `outcome=error`.
- When the handler throws `RuntimeException`, increments the error `Counter` once and **rethrows** to preserve error semantics.
- Does not put payload IDs into metric tags.
- After publishing both events, the program reads results from `SimpleMeterRegistry` and prints deterministic counts.

No Spring Boot, web server, database, or external monitoring backend is needed. `SimpleMeterRegistry` is for in-process demonstration and testing; production should configure a real registry via Micrometer/Actuator/Prometheus or the appropriate backend.

Project structure:

```text
event-metrics-demo/
├── build.gradle
└── src/main/java/demo/EventMetricsDemo.java
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'io.micrometer:micrometer-core:1.13.6'
}

application {
    mainClass = 'demo.EventMetricsDemo'
}
```

File `src/main/java/demo/EventMetricsDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventMetricsDemo {

    public record OrderPlaced(String orderId, boolean fail) {}

    public static final class OrderPlacedListener {
        private final MeterRegistry meters;

        public OrderPlacedListener(MeterRegistry meters) {
            this.meters = meters;
        }

        @EventListener
        public void on(OrderPlaced event) {
            Timer.Sample sample = Timer.start(meters);
            String outcome = "error"; // Fail-closed default for duration.

            try {
                process(event);
                outcome = "success";
            } catch (RuntimeException ex) {
                Counter.builder("application.events.listener.errors")
                    .description("Number of listener runtime failures")
                    .tags(
                        "event", "OrderPlaced",
                        "listener", "OrderPlacedListener",
                        "exception", "IllegalArgumentException"
                    )
                    .register(meters)
                    .increment();
                throw ex; // Do not swallow the error.
            } finally {
                Timer timer = Timer.builder(
                        "application.events.listener.duration")
                    .description("Elapsed time of one listener attempt")
                    .tags(
                        "event", "OrderPlaced",
                        "listener", "OrderPlacedListener",
                        "outcome", outcome
                    )
                    .register(meters);
                sample.stop(timer);
            }
        }

        private void process(OrderPlaced event) {
            if (event.fail()) {
                throw new IllegalArgumentException(
                    "simulated listener failure"
                );
            }
            // A successful business operation in the example.
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        public OrderPlacedListener orderPlacedListener(
                MeterRegistry registry) {
            return new OrderPlacedListener(registry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            MeterRegistry metrics = context.getBean(MeterRegistry.class);

            context.publishEvent(new OrderPlaced("ORD-1", false));

            try {
                context.publishEvent(new OrderPlaced("ORD-2", true));
            } catch (IllegalArgumentException expected) {
                System.out.println(
                    "publisher caught=" + expected.getMessage()
                );
            }

            long successes = metrics.get(
                    "application.events.listener.duration")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "outcome", "success"
                )
                .timer()
                .count();

            long failures = metrics.get(
                    "application.events.listener.duration")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "outcome", "error"
                )
                .timer()
                .count();

            double errors = metrics.get(
                    "application.events.listener.errors")
                .tags(
                    "event", "OrderPlaced",
                    "listener", "OrderPlacedListener",
                    "exception", "IllegalArgumentException"
                )
                .counter()
                .count();

            System.out.println("success_count=" + successes);
            System.out.println("error_count=" + failures);
            System.out.printf(
                java.util.Locale.ROOT,
                "error_counter=%.0f%n", errors
            );
        }
    }
}
```

Run with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

**Expected business stdout lines** (excluding extra Gradle/backend logging messages):

```text
publisher caught=simulated listener failure
success_count=1
error_count=1
error_counter=1
```

Explanation:
1. `AnnotationConfigApplicationContext` registers `SimpleMeterRegistry` and an `OrderPlacedListener` with `@EventListener`.
2. Without a configured executor, the default multicaster dispatches listeners synchronously. `publishEvent(ORD-1)` succeeds and records one Timer sample with `outcome=success`.
3. `publishEvent(ORD-2)` invokes the handler, `process` throws `IllegalArgumentException`, the error counter increments, and the `finally` block still records duration with `outcome=error`.
4. The outer `catch` receives the exception because the synchronous Spring multicaster **has no custom ErrorHandler**. This does not prove DB rollback, since the demo uses no transactions.
5. `Timer.count()` is the number of recorded samples, **not total duration**. Total duration can be read via `timer.totalTime(TimeUnit.MILLISECONDS)` or `timer.mean(TimeUnit.MILLISECONDS)`, though actual values vary by machine so the example does not print fixed millisecond numbers.
6. The code catches `RuntimeException` as the scope of the application error counter. If a serious `Error` occurs, `finally` still runs when runtime permits and the sample gets `outcome=error`, while the example counter is not incremented because there is no `catch (Error)`. `OutOfMemoryError` should not be treated as a business error to handle the same way.
7. The `exception` tag in the demo is fixed to `IllegalArgumentException` because the demo method intentionally throws that exact type. Real applications should map exceptions to **a bounded set of classes/categories**; never attach messages or dynamic IDs.

**Important regarding ordering and semantics:** the test does not use `@Async` or `setTaskExecutor(...)`, so all metrics can be read right after `publishEvent` returns (or throws). If the listener is moved to an executor, do not expect counts to be finished when publish returns; tests must wait for the handler using a latch/future or corresponding test signal.

## 6. Why are `Timer.Sample` and `finally` a good fit?

`Timer.Sample.start(registry)` captures the start time using the monotonic clock managed by Micrometer. `sample.stop(timer)` records the elapsed duration into the selected timer. Because the outcome is known only after business logic runs, you can choose the `outcome=success/error` timer tag **at the end**.

General pattern:

```java
Timer.Sample sample = Timer.start(registry);
String outcome = "error";

try {
    businessAction();
    outcome = "success";
} catch (RuntimeException ex) {
    failureCounter.increment();
    throw ex;
} finally {
    Timer.builder("application.events.listener.duration")
        .tags("event", "OrderPlaced", "outcome", outcome)
        .register(registry);
    // Complete example needs to hold the Timer reference and call sample.stop(timer).
}
```

This snippet is a **pseudo-integration snippet** to clarify control flow, not a complete program like section 5. Production code should cache/register meters with an appropriate strategy to minimize hot-path lookup cost. `Timer.Sample` is useful when outcome is determined at the end while still needing an accurate start timestamp.

**Never omit `finally`**: if the handler throws an exception before recording the timer, the slowest and failed invocations will be missing from latency charts, skewing the data. Likewise, **never swallow exceptions** just to keep dashboards pretty; choosing an `ErrorHandler`, retries, and propagating errors to callers must follow an explicit contract.

Also consider errors inside the instrumentation code itself: a measurement bug inside `finally` could mask the original exception. In practice, keep metric-recording logic simple, register stable meters early, and test instrumentation-failure paths if your system has strict reliability requirements.

## 7. Separating publish, listener, and queue wait metrics

A well-designed observability setup typically has three data sources:

| Stage | Start / end boundaries | Metric | Notes |
| --- | --- | --- | --- |
| Publish call | Before/after `publishEvent()` | `application.events.publish.duration` | With async, reflects handoff/dispatch only, not handler completion |
| Queue wait | Task submission until worker starts | `application.events.executor.queue.wait` | Must be measured on the same executor; not automatically in listener Timer |
| Handler execution | Method entry until method exit | `application.events.listener.duration` | Reflects one handler execution; excludes jobs forked later |
| End-to-end | Valid domain fact until real outcome completes | `application.events.delivery.duration` or tracing | Requires outcome/event lifecycle and separate durability mechanisms |

### Async configuration changes what publish metrics mean

`SimpleApplicationEventMulticaster` invokes listeners on the calling thread by default. When `setTaskExecutor(executor)` is configured, listeners supporting async execution can be submitted to the pool; listeners **that do not support async execution** may still be invoked on the publisher thread, such as transactional listeners registering synchronizations. Thus, publish time is not simply "queue enqueue time" for every listener.

To detect pool congestion, measure:
- `executor.active`: currently active tasks.
- `executor.queued`: queued waiting tasks.
- `executor.rejected`: rejected task submissions.
- `executor.completed` or task throughput (depending on what the executor/registry exposes).

`ThreadPoolTaskExecutor` can expose relevant figures (`getActiveCount()`, `getPoolSize()`, queue size via the underlying executor); binding/registering gauges must follow bean naming and lifecycle. Do not assume Spring Framework core exports all of these metrics to Prometheus without a binder/Actuator/custom registration.

**Queue wait and timeout are different:** queue wait measures time before the task starts; timeout measures a business or I/O limit. If a task is rejected at submission time, there is no listener invocation to record `listener.duration`; a separate rejection counter is needed for full visibility into unprocessed events.

## 8. Listener errors with `SimpleApplicationEventMulticaster`

### 8.1. Synchronous without `ErrorHandler`

In the default configuration, a listener exception can **halt the current multicast** and propagate to the publisher. With multiple listeners, do not assume all subsequent listeners were invoked when an earlier listener threw an error.

Example:

```text
publish(OrderPlaced)
   |
   +--> listener A succeeds
   |
   +--> listener B throws IllegalStateException
           |
           +--> exception propagates to publisher
           +--> listener C may not be invoked
```

Recording only a `publish error` from the caller loses information about **which listener failed**, while counting both publisher and handler errors without distinguishing intent can make two charts reflect the same incident in different units. Tag metrics to separate publish-boundary errors from handler errors.

### 8.2. Using `setErrorHandler(...)`

`SimpleApplicationEventMulticaster.setErrorHandler(...)` accepts a strategy to handle listener errors. An error-suppressing strategy can let remaining listeners proceed, yet **`publishEvent()` succeeding does not mean all listeners succeeded**. If the strategy propagates errors, the publisher can still receive exceptions.

When using an error handler, increment metrics at **one place with a clear contract**:
- Directly inside the handler/handler wrapper for the actual error of each attempt.
- Or inside a shared error handler to count exceptions caught by the multicaster, when no other instrumentation layer double-counts them.

Avoid incrementing the same counter in both the listener and `ErrorHandler` if both record the same failure, unless the metrics are defined differently with clear names/tags.

### 8.3. Async and `@Async`

With an executor, a listener can fail **after** the publisher has returned. Errors typically go to the executor/async error-handling mechanism rather than propagating back to the request publisher. `@Async @EventListener` uses an async proxy path and error handling that can differ from the multicaster executor depending on configuration.

Therefore, **measuring directly inside the listener or execution wrapper** is more reliable than inferring listener errors from `publishEvent()` exceptions. Critical async work must have retries, dead-letter handling, and alerts on delivery outcomes; an error metric is an alert, not automatic task recovery.

## 9. Transactional event listeners and post-commit duration

`@TransactionalEventListener` supports phases `BEFORE_COMMIT`, `AFTER_COMMIT` (default), `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Publishing an event inside a transaction typically **registers a synchronization**; phase processing can occur when the transaction finishes.

Keep these questions separate:
- Did the DB transaction commit successfully?
- Was the `AFTER_COMMIT` listener invoked?
- Did listener execution throw an exception?
- Did the job/broker/API triggered by the listener complete?

If the DB committed yet the `AFTER_COMMIT` handler failed, the original transaction cannot be rolled back. Listener timing measures **handler execution during that phase**, and does not automatically measure total transaction duration or lag since event emission.

Measure transaction duration with appropriate transaction/database instrumentation; measure event handler duration with its own Timer; measure external delivery or outbox lag with another metric. Never add series with different units or start/end boundaries to fabricate an arbitrary "total".

**Delivery guarantees cannot be measured automatically:** Spring Application Events are in-process; `@TransactionalEventListener(AFTER_COMMIT)` still has a post-commit crash window. If critical events must not be lost, persist a **transactional outbox** in the same DB transaction, then measure backlog, age, retries, and successful deliveries from the worker.

### Reactive transactions

In WebFlux/Reactor, transactional events can carry a `TransactionContext` per Spring 6.1 mechanisms (typically via `TransactionalEventPublisher`). With reactive handlers, a method returning `Mono` **does not mean measuring method invocation covers subscription and completion time**. Instrument the reactive Publisher lifecycle, such as via `doOnEach`, `doFinally`, `tap`, or properly integrated Micrometer Observation. In particular, `doFinally` runs on terminal/cancel signals, so distinguishing success/error/cancel requires explicit handling; never treat every `finally` as success.

## 10. Latency and distributions: mean, p95, p99, histograms

A `Timer` provides count, total time, and max/percentiles/histograms depending on configuration. Never rely on **mean** alone:

- A 10 ms mean can still hide a group of requests taking 5 seconds.
- p95/p99 show **tail latency**, which often degrades user experience when listeners are synchronous.
- Max in Micrometer is typically a time-window max that can reset/change as the window rolls; do not treat max from `SimpleMeterRegistry` over one minute as a permanent max.
- Histograms require choosing suitable buckets/service level objectives and carry time-series cost.

A timer can be declared for production as follows (integration snippet):

```java
Timer timer = Timer.builder("application.events.listener.duration")
    .description("Duration of an event listener invocation")
    .tags(
        "event", "OrderPlaced",
        "listener", "OrderPlacedListener",
        "outcome", "success"
    )
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(50),
        Duration.ofMillis(200),
        Duration.ofSeconds(1)
    )
    .register(registry);
```

This requires importing `java.time.Duration`, `io.micrometer.core.instrument.Timer`, and `MeterRegistry`, plus a backend supporting histograms. This **is not required code for the demo program**; enable histograms only when you genuinely need percentile computation on a monitoring backend, generally not everywhere indiscriminately.

**Reading p95/p99 properly:** if the backend supports histograms, aggregate percentiles across tags validly (such as Prometheus `histogram_quantile` over buckets); never take a simple average of p95 values from multiple pods and treat that as the system-wide p95.

## 11. Prometheus query examples and meanings

If using a Prometheus registry and timers/counters exported with normalized names, queries can look like:

```promql
sum by (event, listener, outcome) (
  rate(application_events_listener_duration_seconds_count[5m])
)
```

This query estimates **attempts per second** by outcome. It is not latency.

A query computing **mean seconds** per handler:

```promql
sum by (event, listener) (
  rate(application_events_listener_duration_seconds_sum[5m])
)
/
clamp_min(
  sum by (event, listener) (
    rate(application_events_listener_duration_seconds_count[5m])
  ),
  1e-9
)
```

A p95 query **only when histogram buckets exist**:

```promql
histogram_quantile(
  0.95,
  sum by (le, event, listener) (
    rate(application_events_listener_duration_seconds_bucket[5m])
  )
)
```

An error ratio query based on **the same Timer attempts**, reducing denominator mismatch risk between counters and timers:

```promql
sum by (event, listener) (
  rate(application_events_listener_duration_seconds_count{outcome="error"}[5m])
)
/
clamp_min(
  sum by (event, listener) (
    rate(application_events_listener_duration_seconds_count[5m])
  ),
  1e-9
)
```

Actual names depend on naming conventions, Micrometer registry version, and your system's exporter. The queries above are **illustrative patterns** to verify against series actually scraped by Prometheus, not a guarantee that a plain Spring Context app exposes a Prometheus endpoint automatically.

**Rate on counters** is better than viewing cumulative totals when comparing traffic over time. For rare events, 5 minutes may lack samples; you may need longer windows or alerts based on absolute error counts. Watch out for "zero denominator" branches and events never invoked not creating a success series to divide by; dashboards should handle "no data" intentionally.

## 12. Alerts and SLOs

Some operationally meaningful indicators:

| Signal | When to alert? | Check before concluding |
| --- | --- | --- |
| Error rate of critical listener | Exceeds threshold long enough with sufficient attempts | Are there retries? Did event volume change? |
| Absolute error count | Rare but severe failure occurs | Exception category and business criticality |
| p95/p99 duration | Breaches latency objective across multiple windows | Handler blocking, downstream API, or GC |
| Executor backlog/queue wait | Grows continuously while workers are busy | Pool size, task type, rejection policy |
| Rejected tasks | Any non-zero value for mandatory events | Is there a sync fallback? Is there an outbox? |
| Outbox age/backlog | Event committed long ago yet undelivered | Is the worker alive, is the broker failing? |
| Disappearing event volume | Count drops abruptly to 0 while traffic continues | Are events not published or is the metric pipeline broken? |

Hypothetical example: an email-sending listener must process at p95 within 200 ms with an error ratio under 0.5% over at least 15 minutes. This is an **illustrative target**, not a default for every project. If the listener merely enqueues an email into a queue, 200 ms is the SLO of **enqueueing**, not of the email reaching the customer. Set SLOs at the right user-facing/business outcome boundary.

Alerts need minimum traffic floors and suitable evaluation windows to avoid over-alerting on 1 error out of 2 attempts or when deployments change series counts.

## 13. Combining metrics with logs and tracing

Metrics answer **"how often, and how slow?"**. Logs and tracing answer **"which occurrence, where, and why?"**.

An event should have:
- `eventId`: identifies one domain event occurrence; useful for retries/idempotency.
- `correlationId`: links multiple operations within the same workflow.
- `traceId`/`spanId`: links to a distributed trace if tracing is configured.
- `eventType` and `listener`: bounded tags for metrics.

Structured log example when a handler fails:

```text
level=ERROR eventType=OrderPlaced listener=OrderPlacedListener
eventId=EVT-17 correlationId=REQ-42 exception=IllegalArgumentException
message="simulated listener failure"
```

This log is **illustrative**; it is not output from the demo program. Metrics attach only `event=OrderPlaced`, `listener=OrderPlacedListener`, and `outcome=error`. Specific IDs stay in logs/traces, avoiding cardinality explosion.

When listeners run via `@Async` or an executor multicaster, thread-bound MDC (Mapped Diagnostic Context) does not automatically propagate to workers. Use an appropriate `TaskDecorator`/Micrometer context propagation, or rebuild the logging scope from the immutable event payload. Propagating MDC does not automatically propagate transactions, security, or delivery guarantees.

## 14. Testing instrumentation correctness

### 14.1. Unit testing `Timer` and `Counter`

`SimpleMeterRegistry` is well suited for tests:
1. Call the listener with a succeeding event; assert Timer `outcome=success` has count 1, and fail timer is absent or count 0.
2. Call the listener with a failing event; assert the exception is still thrown and Error Counter increments exactly once.
3. Assert Timer `outcome=error` has count 1 **even though the handler threw an exception**.
4. You can assert `totalTime(...) >= 0`, without asserting exact machine duration since scheduling/CPU varies.
5. Ensure metrics have no `eventId`, `orderId`, or `correlationId` tags.

In a test framework, to avoid clock dependencies, you can supply `MockClock` to an appropriate registry or measure with `Timer.Sample` against a controlled clock. Avoid relying primarily on `Thread.sleep` to verify time units.

### 14.2. Integration tests with Spring context

Run with `AnnotationConfigApplicationContext` similar to the demo, ensuring `@EventListener` is actually registered. Call `publishEvent` and read the registry. In sync mode, metrics are available immediately after the listener call completes; with multiple listeners, verify each listener independently rather than assuming all ran if one threw.

### 14.3. Async tests

When the multicaster uses `ThreadPoolTaskExecutor`:
- Use a `CountDownLatch`/future or test signal to wait for listener completion.
- Verify **listener** Timer counts after completion; do not measure publish and treat it as handler time.
- Verify rejected tasks or full queues are observed in separate metrics.
- Trigger a listener failure and verify the error appears in error metrics/logs even though the publisher receives no exception.

### 14.4. Transaction integration tests

In a transaction with `@TransactionalEventListener(AFTER_COMMIT)`:
- Actually commit and verify the listener is invoked/measured.
- Roll back and verify the `AFTER_COMMIT` listener is not invoked.
- If the listener fails after commit, DB state remains committed; error metrics reflect a **post-commit failure**.
- Spring `@Transactional` tests often roll back automatically at the end of a test, so commit explicitly when testing `AFTER_COMMIT`.

### 14.5. Retries and idempotency

If an event is retried 3 times and succeeds on the last try:
- `attempt_count=3`, `attempt_error_count=2` are metrics at the **attempt layer**.
- `logical_events_succeeded=1` holds only if there is a mechanism tracking final outcome by `eventId` (such as an outbox consumer).
- Do not sum three attempts and call them three separate domain events.
- If retries throw the same exception and an error handler also counts errors again, check for double counting.

## 15. Common pitfalls

1. **Using `publishEvent` duration as async listener duration:** those are two different boundaries.
2. **Not recording Timer on exceptions:** latency charts look artificially good by omitting failed executions.
3. **Measuring errors only at the publisher:** misses async listener failures or errors suppressed by an `ErrorHandler`.
4. **Counting errors twice in both the listener and `ErrorHandler`:** inflates reported error rates.
5. **Using `eventId`, `orderId`, or `correlationId` as metric tags:** causes cardinality explosion.
6. **Using average latency only:** hides p95/p99 and tail latency issues.
7. **Assuming Micrometer core auto-exposes endpoints:** an appropriate registry, exporter/binder/Actuator is required.
8. **Enabling histograms everywhere:** increases time series/memory/costs without defined SLOs.
9. **Not separating queue wait from listener execution:** misses pool congestion.
10. **Treating an `AFTER_COMMIT` callback failure as a DB rollback:** the original commit already completed.
11. **Treating a retry as a new business event:** confuses attempt metrics with logical outcomes.
12. **Not classifying cancellations/timeouts:** reactive chains/async tasks have outcomes distinct from `RuntimeException` success/error.
13. **Skipping logs and tracing because metrics exist:** lacks specific IDs to investigate individual events.
14. **Assuming metrics provide reliability:** metrics do not replace outboxes, retries, DLQs, or idempotency.

## 16. Implementation checklist

- [ ] Defined `publishEvent latency`, `listener duration`, and `end-to-end duration` clearly as three distinct metrics.
- [ ] Every critical listener has a Timer, including the exception path, and error metrics have a consistent counting contract.
- [ ] Outcomes success/error/cancel/rejected are classified accurately for the execution model.
- [ ] Dynamic identifiers, exception messages, and PII are never used as metric tags.
- [ ] Async listeners are measured at the execution point rather than inferred from the publisher.
- [ ] Queue wait, executor backlog, and rejections are observed when using a thread pool.
- [ ] Transactional listeners measure the right phase; post-commit failures are not confused with DB rollbacks.
- [ ] Histograms/p95/p99 are enabled on handlers needing SLOs, not everywhere out of habit.
- [ ] Alerts have evaluation windows, traffic floors, and business-meaningful thresholds.
- [ ] Correlation/event IDs live in logs/traces for investigation, not in metric tags.
- [ ] Unit/integration tests verify timer counts, error counts, exact grouping, rollbacks, and retries.
- [ ] For events requiring durable delivery, an outbox/queue exists and true delivery outcomes are tracked.

**Takeaway:** measure **a single listener invocation** with Micrometer `Timer` at the execution boundary and record errors with controlled `Counter`s or outcome tags. `publishEvent()` measures dispatch/handoff per configuration and does not guarantee async listeners have finished. Combine metrics with logs/tracing, avoid high-cardinality tags, and separate DB commits from side-effect outcomes for reliable system observability.

## References

- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer Concepts — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Concepts — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Concepts — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Concepts — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
