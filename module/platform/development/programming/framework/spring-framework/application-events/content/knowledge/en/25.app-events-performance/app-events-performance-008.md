# Measuring Throughput and Latency When Processing Spring Framework Application Events

## 1. Purpose of measuring event performance

Spring Framework provides `ApplicationEventPublisher`, `ApplicationEventMulticaster`, `@EventListener`, and `@TransactionalEventListener` for in-application event dispatching. As event volume grows, the important questions are:

- How many events per second do application services **publish**?
- How many events per second do listeners **finish processing**?
- How long does a single `publishEvent(...)` call take?
- How long does a listener take to handle one event?
- How long does it take from event creation until processing finishes, including queue wait time?
- Under higher load, do events back up, get rejected, fail, or get processed multiple times?
- How do CPU, threads, GC, database connections, and memory change?

You cannot answer accurately with a single “event throughput” number. **Throughput** is the number of completed work units per unit of time, whereas **latency** is the time required to complete one unit of work. A publisher might push 20,000 events/second into a queue while consumers finish only 2,000 events/second; looking solely at publish speed makes the system appear very fast even as backlog grows.

Measuring event performance must begin by defining **work boundaries**: publisher call, dispatch, handler, commit, enqueue, or end-to-end delivery. Each boundary has different goals and metrics.

## 2. Throughput: distinguishing offered, published, processed, and committed

A general pipeline:

```text
Commands / event producers
   |
   | offered rate (requested events/s)
   v
ApplicationEventPublisher.publishEvent(...)
   |
   | publish / dispatch rate (handed-off events/s)
   v
ApplicationEventMulticaster
   |
   +-- [optional executor / queue]
   |       | queue depth, wait time, reject count
   |       v
   +-- @EventListener / ApplicationListener
           |
           | handler start rate
           v
       handle business logic
           |
           +-- success: completed events/s
           +-- error: failed events/s
           +-- retry: attempted events/s increases
```

We can define:

| Metric | Definition | Question |
| --- | --- | --- |
| **Offered rate** | Events/commands submitted into the system per second | How high is the requested load? |
| **Publish rate** | Publisher calls handed off per second | How fast is the producer emitting? |
| **Completion throughput** | Successfully completed listener executions per second | How much work is the system genuinely digesting? |
| **Attempt rate** | Processing attempts, including retries, per second | Are we wasting resources on retries? |
| **Failure rate** | Failed executions per second or failure ratio | Is successful throughput dropping due to errors? |
| **Committed-event rate** | Events tied to committed changes per contract | How much durable business work is achieved? |

Distinguish denominators: one event received by three listeners can produce three **handler invocations** from **one** publisher invocation. If you count every listener, do not call that total the number of unique domain events published.

A basic formula:

```text
throughput = completed_operations / elapsed_seconds

Example (hypothetical figures to illustrate the formula):
completed = 12_000 event handling operations
elapsed = 10 seconds
throughput = 1_200 completed operations/second
```

If 12,000 `publishEvent` calls occur in 10 seconds yet only 8,000 handler executions complete, **publish rate = 1,200/s** while **completion throughput = 800/s**. While the queue keeps accepting load without drops, backlog tends to grow. That is not a throughput improvement just because the publisher returned quickly.

For events with fan-out, also track how many listeners must complete per event. For example, if `OrderPaid` has three mandatory listeners: “3 handler completions” is not “3 domain events processed”.

## 3. Latency: at least three intervals must be measured

### 3.1. Publish-call latency

Time from immediately before to immediately after `publisher.publishEvent(event)`:

```text
t0: call publishEvent
t1: publishEvent returns
publish latency = t1 - t0
```

With the default `SimpleApplicationEventMulticaster`, matching listeners typically run **synchronously on the publisher thread**. Publish-call latency then includes dispatching cost and execution time of synchronous listeners (plus any producer overhead within the measured span).

With an asynchronous executor, publish-call latency mainly measures dispatch and task submission, **not completed processing time**. A tiny publish latency number can coexist with a very long queue.

### 3.2. Handler execution latency

Measured right inside the listener:

```text
h0: handler starts
h1: handler finishes (success or failure)
handler latency = h1 - h0
```

This is the execution time of **one listener invocation**. For listeners calling SQL, HTTP, or external services, I/O wait time is included here. If multiple listeners exist, measure separately by a bounded `handler.type` tag rather than blending vastly different work into one confusing average.

A measurement wrapping only enqueueing to a worker cannot be called handler *completion* time. If a handler merely submits a `CompletableFuture` and returns, measure until the future completes or measure inside the worker itself.

### 3.3. End-to-end event latency

Time from event creation until processing reaches its final outcome:

```text
created t0 ---> publish/enqueue t1 ---> handler starts t2 ---> handled t3

queue wait / scheduling delay = t2 - t1
handler execution latency     = t3 - t2
end-to-end processing latency = t3 - t0
```

Within a single JVM, `System.nanoTime()` can serve as a monotonic clock for measuring **elapsed intervals**, even across threads in the same process. Do not send `nanoTime()` values over a broker or to another machine for direct subtraction; `nanoTime`'s origin is process/JVM-specific. For cross-process flows, use appropriate timestamps, clock synchronization, trace/correlation, or measurement methods aware of clock skew.

The end boundary must also be defined: handler return, transaction commit, outbox write, broker ack, or external side-effect success. Without agreement, two “end-to-end latency” charts may measure completely different things.

## 4. Mean is not enough: p50, p95, p99, and distributions

Latency often has a long tail: 99% of events are fast while a few hit slow I/O or GC pauses. Looking only at the **average** can hide cases users genuinely experience as slow.

| Statistic | Meaning | Usefulness |
| --- | --- | --- |
| Mean (average) | Total duration / sample count | Summarizes average time, sensitive to outliers |
| p50 (median) | Roughly 50% of samples are at or below this | Typical case |
| p95 | Roughly 95% of samples are at or below this | Common tail latency |
| p99 | Roughly 99% of samples are at or below this | Captures unusual slowdowns, strict SLOs |
| Max | Largest value in the window | Shows worst outlier, depends on window length |
| Error/timeout count | Count of work failing to finish in time | Ensures latency does not measure successes alone |

Hypothetical example: 99 events take 2 ms, one event takes 5,000 ms. Mean is ~51.98 ms even though the vast majority are just 2 ms; p99 depends on percentile calculation method and window data, yet can reflect a very different tail. Therefore **do not compare percentiles from overly small samples** or from differing calculation methods and conclude there is a regression.

With Micrometer `Timer`, basic measurements include count, total time, and max. **Histograms/percentiles are not always enabled by default in every MeterRegistry/backend**; you must configure appropriate distribution statistics and understand how the exporter computes percentiles. P95/P99 should usually be computed from backend histograms when aggregating across multiple processes.

Never average per-node p95 values to compute cluster-wide p95; percentiles do not aggregate linearly like counts or sums. Use histograms with proper buckets or a metrics system supporting distribution merging.

## 5. Runnable Java 17 + Spring Framework + Micrometer example

The example below measures **in-process events, handled synchronously**:

- Runs warmup first so the JVM/JIT stabilizes somewhat, **without** recording warmup samples.
- Publishes 5,000 `WorkEvent`s marked as measured.
- Counts publisher calls and handler completions using `Counter`.
- Uses `Timer` to measure `publishEvent`, listener body, and end-to-end latency.
- Computes throughput by dividing completions by the total measurement window duration.
- Prints deterministic counts for verification; latency/rate are **actual measurements that vary by machine**, without inventing benchmark numbers.

This is a deliberate instrumentation demo, **not a scientific benchmark**. Because the listener runs a simple CPU loop, it does not measure SQL, brokers, queues, transactions, or real side effects. Production load figures require a separate test.

### 5.1. Directory structure

```text
spring-event-metrics/
├── pom.xml
└── src/main/java/demo/EventMetricsDemo.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-metrics</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.14.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.EventMetricsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/java/demo/EventMetricsDemo.java

```java
package demo;

import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventMetricsDemo {

    private static final int WARMUP_EVENTS = 2_000;
    private static final int MEASURED_EVENTS = 5_000;

    // createdNanos is used to measure elapsed intervals within the same JVM.
    public record WorkEvent(
            int sequence, long createdNanos, boolean measured) {}

    public static final class EventMeters {
        final Counter published;
        final Counter handled;
        final Timer publishTimer;
        final Timer handleTimer;
        final Timer endToEndTimer;

        EventMeters(SimpleMeterRegistry registry) {
            published = Counter.builder("demo.event.published")
                    .tag("type", "work")
                    .register(registry);
            handled = Counter.builder("demo.event.handled")
                    .tag("type", "work")
                    .register(registry);
            publishTimer = Timer.builder("demo.event.publish")
                    .tag("type", "work")
                    .register(registry);
            handleTimer = Timer.builder("demo.event.handle")
                    .tag("type", "work")
                    .register(registry);
            endToEndTimer = Timer.builder("demo.event.end.to.end")
                    .tag("type", "work")
                    .register(registry);
        }
    }

    public static final class WorkHandler {
        private final EventMeters meters;
        private volatile long resultSink;

        WorkHandler(EventMeters meters) {
            this.meters = meters;
        }

        @EventListener
        public void onWork(WorkEvent event) {
            long started = System.nanoTime();

            // Simulate CPU work without using sleep or I/O.
            long result = 0;
            for (int i = 0; i < 1_000; i++) {
                result += event.sequence() * 31L + i;
            }
            resultSink = result; // keep result observable to the JVM

            long finished = System.nanoTime();
            if (event.measured()) {
                meters.handled.increment();
                meters.handleTimer.record(
                        finished - started, TimeUnit.NANOSECONDS);
                meters.endToEndTimer.record(
                        finished - event.createdNanos(),
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        EventMeters eventMeters(SimpleMeterRegistry registry) {
            return new EventMeters(registry);
        }

        @Bean
        WorkHandler workHandler(EventMeters meters) {
            return new WorkHandler(meters);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            EventMeters meters = context.getBean(EventMeters.class);

            // Warm-up: dispatches and runs listener without recording.
            for (int i = 0; i < WARMUP_EVENTS; i++) {
                context.publishEvent(
                        new WorkEvent(i, System.nanoTime(), false));
            }

            long windowStart = System.nanoTime();
            for (int i = 0; i < MEASURED_EVENTS; i++) {
                long created = System.nanoTime();
                long publishStart = System.nanoTime();

                context.publishEvent(
                        new WorkEvent(i, created, true));

                long publishFinished = System.nanoTime();
                meters.publishTimer.record(
                        publishFinished - publishStart,
                        TimeUnit.NANOSECONDS);
                meters.published.increment();
            }
            long windowFinished = System.nanoTime();

            double elapsedSeconds =
                    (windowFinished - windowStart) / 1_000_000_000.0;
            double rate = meters.handled.count() / elapsedSeconds;

            System.out.printf(Locale.ROOT,
                    "counts published=%d handled=%d publishSamples=%d"
                            + " handleSamples=%d endToEndSamples=%d%n",
                    (long) meters.published.count(),
                    (long) meters.handled.count(),
                    meters.publishTimer.count(),
                    meters.handleTimer.count(),
                    meters.endToEndTimer.count());

            System.out.printf(Locale.ROOT,
                    "throughput=%.1f events/s"
                            + " meanPublish=%.3f ms"
                            + " meanHandle=%.3f ms"
                            + " meanEndToEnd=%.3f ms%n",
                    rate,
                    meters.publishTimer.mean(TimeUnit.MILLISECONDS),
                    meters.handleTimer.mean(TimeUnit.MILLISECONDS),
                    meters.endToEndTimer.mean(TimeUnit.MILLISECONDS));
        }
    }
}
```

Run with JDK 17+ and Maven in the `spring-event-metrics` directory:

```bash
mvn -q clean compile exec:java
```

**Verifiable count line** in this example:

```text
counts published=5000 handled=5000 publishSamples=5000 handleSamples=5000 endToEndSamples=5000
```

The next line prints `throughput=... events/s` and the three mean latencies. **There are no fixed throughput/latency figures**: results depend on CPU, JVM, JIT, load, OS, instrumentation, and environment conditions. Do not copy measurements from one machine into another document as a baseline.

### 5.4. Why are the counts equal?

- Each measured `WorkEvent` published corresponds to one `publishEvent(...)` call.
- There is a single synchronous `WorkHandler.onWork(...)` that throws no errors.
- The handler finishes before `publishEvent(...)` returns, so across 5,000 measured events, completions = publisher calls.
- `Timer` records **one sample per measured invocation**. Warmup still emits events, yet `measured=false` keeps Counters/Timers unchanged; the publish timer also records only inside the measurement loop.
- Throughput is computed as **handled count / duration wrapping the entire measured publish loop**; since execution is synchronous, that is completed operations per second for the test thread.

In the demo, `meanEndToEnd` includes dispatch cost and the handler body, so it is typically greater than `meanHandle`; meanwhile `meanPublish` can include listeners and other measurement overhead. Close or slightly different values **do not by themselves prove** performance gains or regressions; multiple runs and statistical analysis are required.

### 5.5. Do not treat sample code as a production benchmark

The CPU loop can be optimized by the JIT and does not reflect real work; 2,000 warmup events may not be sufficient either. Serious benchmarks require production-like load, steady GC state, and failure/queue/DB scenarios.

The takeaway from the example is **instrumenting the right boundaries and distinguishing counts from latency**, not proving exactly how many events per second Spring handles on an arbitrary machine.

## 6. Collecting metrics with Micrometer in real applications

### Counter

Use `Counter` for total accepted events, publish attempts, handler completions, failures, or retries. Rates must be computed over **a time window**, e.g., counter derivative/rate in the monitoring backend; never treat cumulative counter values since process start as “events/s”.

An example meter naming structure:

```text
app.event.publish.attempts
app.event.handle.completed
app.event.handle.failed
app.event.handle.retried
app.event.queue.rejected
```

The metric names above are a **proposed schema**, not names built into Spring. In some cases a timer already carries count, so avoid redundant counters if the backend can derive counts from timers and no extra categorization is needed.

### Timer

`Timer` stores count and total duration, and can support histograms/percentiles when configured. Use it when timing is needed:

```java
// Excerpt; requires an already-defined registry and event.
Timer timer = Timer.builder("app.event.handle")
        .tag("event.type", "order-placed")
        .register(registry);

long start = System.nanoTime();
try {
    handleBusiness(event);
} finally {
    timer.record(System.nanoTime() - start, TimeUnit.NANOSECONDS);
}
```

Do not treat this excerpt as a standalone runnable class. `finally` ensures samples are recorded even when logic throws. If splitting into success/failure timers, you must know the outcome and align naming/tags; record errors with a separate metric or use `Timer.Sample` to select tags after the outcome is known.

Avoid high-cardinality tags such as order ID, email, user ID, or event ID. Use bounded-value tags like event type, handler type, and outcome. Every tag combination increases the number of metric time series stored.

### LongTaskTimer, Gauge, and queue metrics

- `LongTaskTimer` fits when measuring how many tasks are **currently running** and how long unfinished long tasks have been running. It does not replace `Timer` for completed task distributions.
- `Gauge` fits queue depth, active threads, and in-flight tasks. A Gauge reports the current level at read time, not cumulative events processed.
- Counters for rejected/failed/retries help distinguish whether a queue is truly draining data or the producer is pushing load unchecked.

Do not represent queue depth with a Counter that never decrements; it requires a value that goes up and down or a reliable state source.

### Observations do not appear automatically on @EventListener

Spring Framework **does not automatically contribute a Micrometer Observation** for `@EventListener` methods. Synchronous listeners usually run on the publisher thread within the current context/trace, yet gain no dedicated span/timer from the annotation alone. To measure handler latency, use a manual `Timer` as in the demo, `ObservationRegistry` with `Observation.createNotStarted(...).observe(...)`, or properly configured AOP `@Observed`.

Simply having Actuator/Micrometer dependencies or an `ObservationRegistry` bean does not automatically generate timers for every listener. If using `@Observed`, ensure the aspect/proxy intercepts the actual invocation. Do not rely on self-invocation within the same bean to capture all cases.

## 7. Async systems: measuring queue wait, processing throughput, and backlog

When configuring a custom `ApplicationEventMulticaster` with an executor, or using `@Async`, the publisher can finish before the handler completes. Two measurement groups are then needed:

**Producer side:** publish/enqueue rate, publish latency, task rejections, and queue size at observation points.

**Consumer side:** handler start rate, handler completion rate, handler duration, queue waiting time, in-flight count, and failed/retry counts.

```text
Producer --submit--> bounded queue --dequeue--> Worker listeners
          t0       t1              t2         t3

enqueue latency       = t1 - t0
queue wait            = t2 - t1
handler service time  = t3 - t2
end-to-end latency    = t3 - t0
```

If a listener merely receives an event and forwards it to another queue, the handler method returning is not the real business completion milestone. Instrument the worker executing the final work, or explicitly label this as handoff latency only.

### Bounded executors and backpressure

A `ThreadPoolTaskExecutor` configuration can set core/max threads and queue capacity. With an unbounded queue, the publisher can sustain high speed until memory runs out and wait latency climbs steeply. With a bounded queue, saturation must trigger rejection/caller-runs/backpressure or block the producer per contract.

Conceptual configuration snippet (requires appropriate BeanFactory and imports, not a standalone program):

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(1000);
executor.setThreadNamePrefix("event-worker-");
executor.initialize();

SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(executor);
```

Register the multicaster bean under `applicationEventMulticaster` to replace the `ApplicationContext` default. Shut down the executor properly in the lifecycle. In Spring 6.x, certain transaction-synchronized listeners disallow async execution, so **do not assume every callback leaves the publisher thread**. Tests must reflect the actual listener types used.

**Throughput reports cannot count only successful producer submissions**: tests should await queue drain / handler completion and measure lost events, rejected events, exceptions, and remaining items. Otherwise, you are only benchmarking backlog growth rate.

### Queue evaluation formulas

In a relatively steady window, if the arrival rate is \(\lambda\) and completion rate is \(\mu\):

- If \(\lambda \gt \mu\) over an extended period and events are not dropped, queues/backlogs grow.
- If \(\lambda \lt \mu\), the system has headroom to clear backlogs, though latency still depends on bursts, scheduling, and dependencies.
- Under Little's Law in appropriate steady-state conditions: \(L = \lambda W\), where \(L\) is average work in the system, \(\lambda\) is average completion throughput, and \(W\) is average time spent in the system.

Do not force Little's Law onto a short burst sample when the system is not in steady state, has drops, or lacks a proper measurement window. Note that “in-flight” may include both queued and running tasks; each system defines its scope differently.

## 8. Designing repeatable load tests

A worthwhile performance test clearly states its assumptions and conditions:

1. **Representative workload**: event sizes, listener counts, listener types, SQL/HTTP, hot/cold data, fan-out, error rates, and payload distributions.
2. **Environment**: JDK version, JVM heap/GC, CPU count, thread count, pool sizes, container limits, DB/broker locality, and sampling/tracing settings.
3. **Warmup**: initialize context, warm up JIT and connection pools; avoid mixing bean creation time into steady-state throughput.
4. **Measurement window**: measure multiple sufficiently long windows, stating start/end and separating warmup, ramp-up, and cooldown.
5. **Load model**: closed-loop (each client waits for completion before sending next) or open-loop (arrival rate independent of response). The two yield different tail latencies.
6. **Correctness checks**: count publishes, successes, failures, retries, queue rejections, and missing/duplicate events.
7. **Resource telemetry**: CPU utilization, GC allocations/pauses, heap, thread pools, connections, queue depth, and network/IO.
8. **Analysis**: report p50/p95/p99, success rates, errors, backlog, saturation, and confidence/variance across multiple runs.
9. **Tools**: use JMH for code-path microbenchmarks where appropriate; use Gatling/k6/JMeter or dedicated workload generators for end-to-end scenarios. Microbenchmarks do not replace integration/load tests.
10. **Repeat under identical conditions**: run each variant multiple times, alternating A/B order when possible, and avoid measuring while unrelated heavy tasks run on the machine.

### Coordinated omission and real load

A closed-loop test that sends the next request **only after the previous request finishes** slows down its send rate whenever the system stalls. Requests that would have arrived during a server pause are never issued, making the latency distribution look artificially better than reality.

For workloads whose expected arrival rate is independent of processing time, use open-loop tests or coordinated-omission correction mechanisms; also report rejection/drop rates and backlogs. Never just crank up thread counts until a “pretty” throughput number appears.

### Avoiding measurement bias from tooling

- `System.out.println` inside every listener can become an I/O bottleneck; print summaries only after measurement ends.
- DEBUG logging/stack traces for every event can dominate latency; define production and baseline configurations clearly.
- In overly simple processing loops, Timer/Counter overhead can become a large fraction: measure both instrumented and uninstrumented variants when assessing overhead.
- Use `System.nanoTime()` for internal durations rather than `currentTimeMillis()` when sub-millisecond precision is needed and to avoid wall-clock shifts.
- Random data generation, JSON parsing, serialization, and event object creation also have cost; clarify whether those steps are inside the publish window.
- In ultra-short CPU benchmarks, the JIT may optimize away unobservable work; use JMH with proper state/`Blackhole` to avoid benchmarking dead code.
- GC, CPU throttling, and lock contention can spike tail latency; track them alongside latency charts.

## 9. Reading results and locating bottlenecks

An investigation workflow:

```text
Keep load scenario constant
  |
  +-- high publish rate yet low completion?
  |      -> check queue depth, rejections, active threads, retries
  |
  +-- high publish latency in sync mode?
  |      -> check handler duration, fan-out, and I/O inside listeners
  |
  +-- low publish latency yet high E2E?
  |      -> check queue wait, worker saturation, broker lag
  |
  +-- high p99 while p50 looks fine?
  |      -> check GC pauses, DB pool waits, network tail, lock contention
  |
  +-- throughput rises yet errors/drops rise?
  |      -> measure success throughput, not just attempted throughput
  |
  +-- slow post-commit callbacks?
         -> measure AFTER_COMMIT phase separately, monitor I/O outside transaction
```

Do not try to optimize `publishEvent` if the true bottleneck is the database pool or HTTP client called inside a listener. Most application event performance depends on listener work and sync/async policy, not Spring dispatch cost alone.

## 10. Transactional events and measurement accuracy

`@TransactionalEventListener` supports phases such as `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. These phases require defining “event completion time” very explicitly:

- **Publish time**: when the service calls `publishEvent` inside the transaction. The event is not necessarily committed yet.
- **Before-commit callback**: still before commit; errors can prevent commit.
- **After-commit handling**: callback runs once the transaction commits. Latency measured from creation to callback start includes waiting for the transaction to finish.
- **Rollback**: a published event may never get an `AFTER_COMMIT` completion; if measuring successes only, classify events discarded after rollback under the right outcome.

Instrumentation should include metrics distinguishing at least `phase` and `outcome` with low-cardinality values. A committed transaction does not guarantee an after-commit listener's I/O succeeded; a post-commit handler failure cannot roll back that transaction.

With cross-service events, `Transactional Outbox` adds boundaries: outbox row commit, relay publish, broker ack, and consumer completion. “End-to-end” must specify up to which milestone and how retries/duplicates are handled. Use event IDs and correlation IDs properly rather than treating two broker deliveries as two distinct domain facts.

## 11. Defining SLOs and capacity planning

An **illustrative target example**, not default Spring figures:

- At target load of 2,000 events/second, completion throughput stays close to the offered rate over long windows.
- End-to-end p95 under 200 ms and p99 under 500 ms for time-sensitive event types.
- Error/drop/rejection rates stay below agreed thresholds.
- Sudden backlog spikes recover to steady state within the required window.
- Reserve sufficient CPU/thread/connection headroom for bursts and single-node loss.

The levels above are **examples of how to frame SLOs** and must be tailored per event type. A metrics-recording event may tolerate delayed processing; a payment-confirmation or inventory-coordination event may demand very different reliability and latency.

In capacity sizing, raising pool size from 4 to 32 will not necessarily yield 8x throughput: it may hit limits on DB connections, CPU, locks, network, fan-out, or downstream pools. Plot throughput and p95/p99 against offered load to find the saturation knee rather than guessing thread counts intuitively.

## 12. Testing and QA criteria for measurements

Include tests and validation criteria such as:

1. **Accurate counts:** one measured event produces exactly one publish sample and one completion sample with one matching synchronous listener.
2. **Failures:** failing handlers are not counted in success throughput; failure counters increment via proper `catch/finally`.
3. **Two listeners:** one publisher call can produce two handler samples; dashboards must not mistakenly sum them as two events.
4. **Async:** tests await all handlers to finish before computing completion throughput rather than counting submitted tasks alone.
5. **Retries:** attempts increment per retry; unique event counts / idempotent completions are categorized separately.
6. **Transactions:** measure `AFTER_COMMIT` handling inside a real transaction; rollbacks are not counted as committed successes.
7. **Queue saturation:** enforce queue limits, measure rejections/backpressure, and avoid dropping metrics under overload.
8. **Timer units:** always specify ms/s and `TimeUnit`; never add nanoseconds to milliseconds.
9. **Percentiles:** verify histograms/percentiles are enabled with proper buckets and sufficient sample counts.
10. **Tag privacy/cardinality:** never put order IDs, emails, user IDs, IPs, or secrets into metric labels.
11. **Reproducibility:** record JVM, heap, GC, CPU, workload, warmup, measurement window, run count, and environment.
12. **Measurement overhead:** never conclude from a single run; analyze variance and use JMH for ultra-short code paths.

Do not cite a “max events/s” number while ignoring errors and backlogs. The true performance goal is **completed business work meeting latency, correctness, and reliability requirements**.

## 13. Common mistakes

**Mistake 1 — Treating `publishEvent` return as “finished processing” in async.** When listeners run on an executor, the publisher can return while events sit in the queue. Measure handler completion separately.

**Mistake 2 — Counting every listener call as a domain event.** Fan-out makes total invocations larger than logical events; keep publish and handle metrics separate.

**Mistake 3 — Looking only at mean latency.** p95/p99 latencies and errors/timeouts can be terrible even when the mean looks fine.

**Mistake 4 — Skipping warmup.** Mixing context creation and JIT/connection setup into steady-state throughput skews comparisons.

**Mistake 5 — Benchmarking with `println` per event.** Console I/O overwhelms dispatch/handler costs.

**Mistake 6 — Creating labels from event IDs.** Micrometer/Prometheus must track a time series per tag value, causing high cardinality and potential data exposure.

**Mistake 7 — Believing `@EventListener` automatically has an Observation.** Spring Framework does not automatically create Observations for callbacks; instrument explicitly when needed.

**Mistake 8 — Ignoring rejected/failed events.** A system with high publish speed achieved by rejecting work does not have good success throughput.

**Mistake 9 — Comparing two benchmarks with different workloads.** Differences in payload sizes, listener counts, logging, or JVM/GC/DB prevent attributing changes to Spring code.

**Mistake 10 — Measuring only one JVM when production uses a broker.** Separate outbox, relay, broker lag, and consumer latency; do not use `System.nanoTime` across hosts.

**Mistake 11 — Optimizing throughput with an unbounded queue.** Short-term submit speed can trade off for OOM and ever-growing end-to-end latency.

**Mistake 12 — Computing cluster p95 by averaging per-node p95s.** Percentiles cannot be averaged directly; use aggregated histograms instead.

## 14. Self-check questions

1. **How does throughput differ from latency?** — Throughput is completed work units per second; latency is the time one unit of work takes.
2. **Can publish rate exceed completion throughput?** — Yes, especially when queues and slow listeners exist.
3. **What does `publishEvent` measure under default synchronous mode?** — Dispatch time plus synchronous listener execution time.
4. **Why is publish latency insufficient in async mode?** — It usually measures only enqueue/dispatch, missing queue wait and handler execution.
5. **Which clock should be used for durations within a single JVM?** — `System.nanoTime()` or an appropriate Timer API.
6. **Can `nanoTime` be sent to another JVM to compute E2E latency?** — No, there is no meaningful shared time origin.
7. **Do p95/p99 appear automatically when creating a `Timer`?** — Not on every backend/configuration; distribution statistics/histograms must be enabled.
8. **Why avoid using event ID as a metric tag?** — High cardinality and risk of exposing sensitive data.
9. **Can a slow `AFTER_COMMIT` listener roll back an already-committed DB transaction?** — No.
10. **One event has three synchronous listeners; how many publisher calls occurred?** — Potentially just one; handler invocations are a separate metric.
11. **Does increasing thread count always scale throughput linearly?** — No; shared resources can bottleneck.
12. **What must a benchmark claiming 10,000 events/s disclose?** — Workload, environment, window, success count, latency percentiles, errors/backlog, and measurement methodology.

## References

- [Spring Framework — Application Events & @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2.8 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Distribution Summaries and Histograms](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
