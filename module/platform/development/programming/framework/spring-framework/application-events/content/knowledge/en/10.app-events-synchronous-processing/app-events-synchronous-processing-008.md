# Measuring Synchronous Event Processing Time in Spring Framework

## 1. Why Measure?

With Spring Framework Application Events, a single `publishEvent(...)` call can trigger multiple listeners. Under the default synchronous configuration, listeners run on the publisher's thread and can slow down the event-publishing method. If an HTTP request is waiting for that call to complete, every slow listener can contribute to response latency.

For example, after creating an order, the application publishes `OrderPlacedEvent`. A stock-checking listener takes around 30 ms, and a receipt-writing listener takes around 15 ms; publishing time can grow by about 45 ms plus dispatch overhead and related work. Actual measurements must be observed, because runtime environment, JIT, I/O, listener count, and errors all have an impact.

**Lesson goal:** measure how long the publisher waits on an event, measure each individual listener's duration, verify whether they actually run synchronously, and interpret measurements accurately to locate performance bottlenecks.

## 2. Three Time Intervals Must Be Distinguished

| Measurement interval | Where to place the clock? | Meaning |
| --- | --- | --- |
| **`publishEvent` duration** | Immediately before and after `publisher.publishEvent(event)` | Time the caller is occupied by publishing the event, including dispatch and any listeners actually running synchronously inside the call |
| **Single listener duration** | Right at the start and end of the listener method body, or in an instrumentation layer wrapping the call | Processing latency of a specific consumer, potentially including DB/HTTP if the listener waits on them |
| **End-to-end business duration** | From business start to actual completion of all related tasks | Can include transaction commit, queues, deferred tasks, retries; not automatically equal to `publishEvent` duration |

In normal **synchronous, sequential** mode, you can picture it as:

```text
Publisher:
  t0
  | check event type, locate listeners |
  | Listener A: 30 ms                  |
  | Listener B: 15 ms                  |
  | dispatch/overhead                  |
  t1  -> publishEvent returns

elapsed(publishEvent) = t1 - t0
```

`publishEvent` duration is usually close to the sum of synchronous handlers plus overhead. **Do not assume it equals the exact sum of listener durations**: there is also lookup, adapters, AOP interceptors, nested events, logging, and measurements taken at slightly different boundaries.

If a listener calls `publishEvent` again and waits for child-event listeners, the parent listener's duration **already includes** the child event's duration. Adding parent and child listener times together would double-count. When an error is thrown partway through, some listeners may not have run, so you cannot assume the full fan-out completed.

## 3. Conditions for Measurements to Reflect Synchronous Processing

Spring uses `SimpleApplicationEventMulticaster` by default, which typically invokes listeners on the event-publishing thread. `publishEvent` then waits for synchronous listeners to finish. However, the `ApplicationEventPublisher` interface only promises to hand the event off to the publishing mechanism; it does not mandate every configuration to run synchronously.

You must confirm the actual configuration:

1. Check whether an `applicationEventMulticaster` bean is configured with an asynchronous `TaskExecutor`. If so, `publishEvent` may measure only task submission time, not task execution time.
2. Check whether listeners have `@Async` combined with `@EnableAsync`. The listener method may run on another executor and continue after the publisher returns.
3. Check for `@TransactionalEventListener`. With `AFTER_COMMIT`, the listener triggers at a transaction milestone, usually after the `publishEvent` call inside the transaction; a timer around `publishEvent` does not represent post-commit listener work.
4. Check for nested dispatches, AOP proxies, or listeners performing blocking I/O; these change the scope of what needs measuring.

**Note:** Spring may invoke different listeners in a specific order, but timing measurements must not rely on guessed ordering. To identify the most expensive listener, instrument the listeners themselves or use proper instrumentation tools.

## 4. Using the Right Clock

To measure **duration**, use `System.nanoTime()`:

```java
long started = System.nanoTime();
try {
    performWork();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    double elapsedMillis = elapsedNanos / 1_000_000.0;
    // Send elapsedMillis/nanos to an appropriate metric or log.
}
```

The snippet above illustrates timing inside a method where `performWork()` is defined by the application; it is not a standalone Java program.

- `System.nanoTime()` is designed for computing relative elapsed intervals, not representing wall-clock date/time. It is better suited than `System.currentTimeMillis()` for latency because wall clocks can be adjusted.
- Use the **difference between two calls** to `nanoTime()`; never interpret a single return value as a Unix timestamp.
- Use `try/finally` to record duration even when logic throws an exception. If you need to distinguish success from failure, also store the outcome; recording full duration does not mean the operation succeeded.
- Convert nanoseconds to milliseconds by dividing by `1_000_000.0` to keep fractional precision. Integer division `/ 1_000_000` loses sub-millisecond precision.
- Use consistent metric/log names; avoid calling `nanoTime()` in scattered places and combining readings with mismatched start/end boundaries.

In Spring, you can use `StopWatch` for local diagnostics or Micrometer `Timer` to collect metrics over time. Whichever tool you pick, first decide the exact **boundaries of the measurement interval**.

## 5. Complete Java 17+ Example with Spring Context

The runnable example below has two synchronous `@EventListener` handlers. Each listener measures its own duration inside `finally`; the caller measures total `publishEvent` duration. `Thread.sleep(...)` merely simulates an observable slow task and is **not a recommendation to put sleep in production code**.

Directory structure:

```text
sync-event-timing/
├── build.gradle
└── src/main/java/demo/SyncEventTimingDemo.java
```

Contents of `build.gradle`:

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
}

application {
    mainClass = 'demo.SyncEventTimingDemo'
}
```

Contents of `src/main/java/demo/SyncEventTimingDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SyncEventTimingDemo {

    public record OrderPlacedEvent(String orderId) {}

    public record Sample(String listener, long elapsedNanos, boolean success) {}

    public static final class TimingStore {
        private final List<Sample> samples = new ArrayList<>();

        public synchronized void record(
                String listener, long elapsedNanos, boolean success) {
            samples.add(new Sample(listener, elapsedNanos, success));
        }

        public synchronized List<Sample> snapshot() {
            return List.copyOf(samples);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public TimingStore timingStore() {
            return new TimingStore();
        }

        @Bean
        public InventoryListener inventoryListener(TimingStore store) {
            return new InventoryListener(store);
        }

        @Bean
        public ReceiptListener receiptListener(TimingStore store) {
            return new ReceiptListener(store);
        }
    }

    public static final class InventoryListener {
        private final TimingStore store;

        public InventoryListener(TimingStore store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlacedEvent event) {
            long started = System.nanoTime();
            boolean success = false;
            try {
                simulateWork(30);
                success = true;
            } finally {
                store.record(
                    "inventory",
                    System.nanoTime() - started,
                    success
                );
            }
        }
    }

    public static final class ReceiptListener {
        private final TimingStore store;

        public ReceiptListener(TimingStore store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlacedEvent event) {
            long started = System.nanoTime();
            boolean success = false;
            try {
                simulateWork(15);
                success = true;
            } finally {
                store.record(
                    "receipt",
                    System.nanoTime() - started,
                    success
                );
            }
        }
    }

    private static void simulateWork(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Work interrupted", ex);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            TimingStore store = context.getBean(TimingStore.class);
            OrderPlacedEvent event = new OrderPlacedEvent("ORD-101");

            long publishedAt = System.nanoTime();
            context.publishEvent(event);
            long publishNanos = System.nanoTime() - publishedAt;

            System.out.printf(
                Locale.ROOT,
                "publishEvent: %.3f ms%n",
                publishNanos / 1_000_000.0
            );

            for (Sample sample : store.snapshot()) {
                System.out.printf(
                    Locale.ROOT,
                    "%s listener: %.3f ms, success=%s%n",
                    sample.listener(),
                    sample.elapsedNanos() / 1_000_000.0,
                    sample.success()
                );
            }
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

**An illustrative output** might look like this; millisecond numbers will **differ on every run**, and the order of the two listener lines is not an application contract:

```text
publishEvent: 51.304 ms
inventory listener: 31.085 ms, success=true
receipt listener: 15.101 ms, success=true
```

What can be predicted from the code when no errors occur:
- There are exactly **two records** in `TimingStore`, one for `inventory` and one for `receipt`.
- Both have `success=true`.
- Total `publishEvent` duration contains the runtime of both synchronous listeners plus overhead. It tends to exceed each individual duration, but you should not assert a fixed millisecond number.
- It will not necessarily print `51.304`, `31.085`, or `15.101`; scheduler, JIT, GC, Spring overhead, and host machine all affect timings. `Thread.sleep(30)` only requests waiting at least that duration, not producing an exact 30 ms measurement.

In the example, `TimingStore` stores samples in RAM for easy inspection. In production applications, never keep unbounded measurement samples in a `List`: use a metrics system with memory-bounded aggregates. Because timing happens **inside** each listener body, it excludes Spring's cost for listener selection, argument conversion, proxies, and interceptors running before the body begins.

## 6. Handling When a Listener Throws an Exception

There are two separate questions: "how long did the listener run before failing?" and "was the entire event fully processed?"

With the default synchronous `SimpleApplicationEventMulticaster` and no `ErrorHandler`, a listener throwing a runtime exception can cause `publishEvent` to throw and **halt the dispatch pass**, leaving later listeners uninvoked. Therefore, if you only log after the `publishEvent` line as in the main example, an error will prevent the total log from printing.

In applications that also need failure timings, place the publisher timer in a `finally` block:

```java
long started = System.nanoTime();
boolean success = false;
try {
    publisher.publishEvent(event);
    success = true;
} finally {
    long elapsed = System.nanoTime() - started;
    reportPublishDuration(elapsed, success);
}
```

This is an **illustrative snippet**, assuming `publisher`, `event`, and `reportPublishDuration(...)` are already declared. `finally` records duration even on exception; the original exception still propagates because it is not swallowed. Likewise, listener bodies should record duration and outcome in `finally` as in the complete Java example.

If you choose to configure `SimpleApplicationEventMulticaster.setErrorHandler(...)` to catch errors and keep calling other listeners, do not confuse "`publishEvent` returned normally" with "all business tasks succeeded." Measurement needs to record errors per consumer; a swallowing handler can hide failures from the caller.

## 7. Using Micrometer Timer in Real Applications

For long-running services, logging individual requests makes it hard to spot p95/p99 or trends under rising load. Micrometer `Timer` is well suited for recording durations and execution counts, exporting to monitoring systems as configured by the application.

Below is an **integration pattern** inside a listener that already has `MeterRegistry` and a business service. This snippet requires Micrometer dependencies, registry configuration, and application types; it is **not a standalone runnable Java file** like the section 5 example:

```java
@EventListener
public void onOrderPlaced(OrderPlacedEvent event) {
    Timer.Sample sample = Timer.start(meterRegistry);
    String outcome = "success";
    try {
        inventoryService.reserve(event.orderId());
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(
            Timer.builder("business.event.listener.duration")
                .description("Time spent processing a synchronous listener")
                .tag("event", "OrderPlaced")
                .tag("listener", "inventory")
                .tag("outcome", outcome)
                .register(meterRegistry)
        );
    }
}
```

The code above uses `io.micrometer.core.instrument.Timer` and `MeterRegistry`, assuming fields and types are injected properly. If you want to count specific errors or classify failures, add low-cardinality counters. With `Timer`, check which statistics are supported by your registry/monitoring backend: **count**, total duration, throughput rate, max, and percentiles/histograms when enabled. Avoid assuming every backend automatically publishes p95/p99 without enabling distribution statistics.

Naming and tag recommendations:

| Component | Recommendation | Why |
| --- | --- | --- |
| Metric | `business.event.listener.duration` | Distinguishes listener time from publisher time |
| `event` tag | `OrderPlaced` | Groups by event type |
| `listener` tag | `inventory`, `receipt` | Identifies which consumer is slow |
| `outcome` tag | `success`, `error` | Separates success latency from failure latency |
| Tags to avoid | `orderId`, `userId`, `eventId` | Nearly unbounded values, causing time-series explosion |

To measure publisher time too, create a separate metric such as `business.event.publish.duration` around `publishEvent`. Never reuse the same metric name for two different measurement boundaries, or readers will misinterpret it. To investigate a specific event, log `eventId` in **logs or sampled traces** rather than turning it into a metric tag. Always consider protecting sensitive data.

Do not assume Spring Framework automatically produces an observation with your desired semantics for every `@EventListener` method. Verify actual instrumentation or add intentional measurements at the listener/service level.

## 8. Analyzing Metrics to Find Bottlenecks

When a request is slow, inspect concurrently:
1. **`publishEvent` duration:** does it account for a significant share of the request?
2. **Per-listener duration:** which consumer drives up p95/p99, max, or failure rates?
3. **Number of listeners actually executed:** was a new listener registered that increased total time?
4. **Underlying resources:** are DB query time, connection pool waits, external HTTP calls, locks, or I/O happening inside a listener?
5. **Measurement conditions:** do cold start/JIT, concurrent load, GC, warmup, host/VM/container, or resource contention skew numbers?

For example, if `publishEvent` rises from ~20 ms to 180 ms while one listener has a p95 around 160 ms due to database queries, examine that listener's queries and connection pool first. If every individual listener remains fast yet the publisher is slow, check other overhead between the two measurement points (AOP, nested events, adapters, listener lookup, logging, caller-side blocking) and ensure the metrics cover matching scopes.

**Do not add percentiles together:** p95 of A + p95 of B does not generally equal p95 of the sum, because the 95th percentile can occur on different event invocations. To understand end-to-end latency, measure the end-to-end path directly and analyze correlated traces/samples.

Also monitor under load: a 30 ms listener on a request thread may be fine at low frequency yet become a bottleneck when many concurrent requests hold threads. Choosing async can reduce publisher blocking time, while introducing its own queue, throughput, retry, and durability requirements.

## 9. Common Measurement Mistakes

### 9.1. Asynchronous Listeners

With `@Async` or a multicaster using an executor, a timer around `publishEvent` can finish as soon as the task is scheduled. A 2 ms publisher duration **does not mean** the listener finished in 2 ms. Measure inside the task separately, and for end-to-end tracking record publish time, execution start time, and completion time to separate **queue wait** from **processing time**. Note that `nanoTime()` values are only comparable within the same clock domain; across machines/processes, use timestamps, traces, and proper clock-skew handling.

### 9.2. Transaction-Bound Listeners

A synchronous `@EventListener` can typically run inside the publisher's transaction before commit. By contrast, `@TransactionalEventListener(phase = AFTER_COMMIT)` has a different lifecycle: if the publisher emits inside a transaction, timing immediately around `publishEvent` excludes post-commit work. To measure post-commit work, place a timer inside the post-commit listener or service. Do not merge the two latencies without annotation.

### 9.3. Measuring Only the Happy Path

Do not record the end timestamp only after the work without `finally`, because errors will drop failed samples from the data. With multiple listeners, if one synchronous listener throws an error and halts dispatch, missing samples are an important signal; do not backfill zero duration for listeners that never ran.

### 9.4. Measuring Logging, I/O, or Startup and Blaming the Listener

`System.out.println`, string formatting, `ApplicationContext` initialization, class loading, connection creation, or file writes can add large delays. Place markers at the exact boundary you want to measure; in the main example, context setup happens **before** the `publishEvent` timer. Do not treat a single cold-start run as a production benchmark.

### 9.5. Logging Every Event Under Heavy Load

Printing every measurement with decimals can add overhead, logger lock contention, and heavy I/O, distorting the very latency under study. In production, use `Timer` or sampled logs/traces. Instrumentation must provide enough detail to explain behavior without materially slowing the system.

### 9.6. Treating Synchronous Completion as Proof of Durable Completion

When `publishEvent` returns in the default synchronous setup, synchronous listeners were invoked successfully along the current execution path. That **does not automatically guarantee** the transaction committed, a message/email was durably stored, or an external side effect succeeded reliably. Distinguish method return from business completion.

## 10. Testing and Performance Evaluation

**Behavior tests:** In a configuration with synchronous listeners only, create two observable handlers, publish one event, and verify both complete before `publishEvent` returns. Duration tests should check recorded values, counts, and outcomes, **not assert exact millisecond numbers**, because CI speed varies unpredictably.

**Error tests:** Have one handler throw an error, check that duration is recorded in `finally`, and verify how the error propagates per the multicaster setup. If a custom `ErrorHandler` exists, test the exact error-logging/dispatch-continuation policy.

**Benchmarks:** Warm up to reduce JIT noise, run enough iterations, increase load in steady steps, and examine p50/p95/p99 distributions. To compare pure Java algorithms at a microbenchmark level, consider JMH; to measure real event paths, use integration/load tests with the real application and resources. Separate business service time from instrumentation overhead if you suspect timers or logs are skewing results.

**Alerting:** Set SLOs based on request/transaction budgets. For instance, if the budget allocated to synchronous events is 50 ms, monitor p95 or the percentage of events exceeding 50 ms over an appropriate window; this threshold is purely illustrative and must be set from your actual system requirements.

## 11. Implementation Checklist

- Have you verified the listeners being measured actually run synchronously on the publisher thread?
- Does the `publishEvent` timer wrap only the call, without accidentally sweeping in startup, HTTP, or serialization overhead?
- Does each listener have its own timer using `System.nanoTime()` and recording outcome in `finally`?
- Do you distinguish queue wait, handler execution, transaction commit, nested events, and end-to-end latency?
- Are durations collected across enough samples, inspecting p95/p99, max, throughput, and errors instead of relying on a single log line?
- Are metric tags low-cardinality, and are metrics free from significant distortion by logging overhead?
- If a listener fails partway through, do measurements reveal which listeners ran and which did not?
- If configuration changes to async or `AFTER_COMMIT`, will dashboards and metric names still be interpreted accurately?

**Practical conclusion:** measure `publishEvent` to know how long the caller is blocked; measure inside each `@EventListener` to attribute processing time; and measure end-to-end paths when transactions, post-commit tasks, or async execution are involved. Three metrics answer three different questions.

## References

- [Spring Framework — Additional Capabilities of the ApplicationContext (Events)](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
