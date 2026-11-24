# Using Timer.Sample to Measure Operations with Multiple Exit Branches

## 1. The Problem: One Start, Many Ways to End

A lookup operation can finish along several paths: rejecting invalid input, returning data already in cache, loading fresh data, or throwing an exception. Placing a timing call right before each `return` makes it easy to miss a branch. Adding timing calls in both `catch` and `finally` can count a single operation twice.

What must be designed first is **the boundary of a single measurement**:

- Where does it start: before input validation, after acquiring a resource, or before dispatching work?
- Where does it end: when the method returns, after resources are cleaned up, or when an asynchronous result completes?
- How is each final outcome classified: success, cached, rejected, error, or cancelled?

Micrometer's `Timer.Sample` retains the start timestamp so you can select the target timer once the outcome is known. It fits when branches share the same timing meaning, while the outcome tag can only be determined at the end of the operation. [Micrometer 1.13 Timer.Sample guide](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_storing_start_state_in_timer_sample).

The examples below use Java 17 or later and Micrometer 1.13, matching a Spring Boot 3.3 context. We use a test clock to produce fixed intervals; those numbers demonstrate recording behavior, not machine benchmarks.

## 2. Timer, Sample, and Clock Have Distinct Roles

| Component | Role | Typical lifecycle |
| --- | --- | --- |
| `Timer` | Accumulates recording count and time for a group of operations sharing name and tags | Registered once and reused across calls |
| `Timer.Sample` | Holds the start timestamp for one specific measurement | Created fresh for each operation |
| `MeterRegistry` | Manages meters and clock configuration | Shared across the application per configuration |
| `Clock` | Supplies timestamps to compute elapsed intervals | Tied to the registry or explicitly chosen |

Conceptually, the mechanism works as follows:

```text
start(registry): captures t0 from the registry's clock
        ↓
Execute operation; determine final outcome
        ↓
stop(timer): captures t1, computes t1 − t0, records interval into timer
```

`Timer.start(registry)` obtains the clock from the registry. `stop(timer)` records the duration and returns the measured nanoseconds. The `Sample` implementation in Micrometer 1.13 uses `clock.monotonicTime()`; interval computation does not depend on wall-clock date/time displayed on the system clock. [Timer.Sample implementation](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java).

Therefore, do not use `LocalDateTime.now()` or capture two calendar timestamps yourself to replace this mechanism. Timer duration is elapsed wall time between two points, which can include I/O waiting and scheduling delay; it is not automatically CPU execution time.

One easy pitfall: no-arg `Timer.start()` uses the system clock. When the application already has a registry, prefer `Timer.start(registry)`, especially when verifying with a controlled clock. `Timer.Sample` is also not `AutoCloseable`; do not put it in `try-with-resources` expecting automatic recording on close.

### Choosing the Timer at the End Does Not Mean Creating a New Name per Call

You can register the same name `app.lookup.duration`, with tag `outcome` taking finite values `rejected`, `cached`, `success`, `error`. Those are distinct metric series belonging to the same measurement.

Do not use lookup keys, order IDs, exception messages, or user IDs as unbounded tag values. Final outcomes should be mapped to a stable value set. [Naming rules and tag value bounds](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

## 3. Synchronous Design: Pick the Outcome in try, Record Once in finally

For synchronous operations, a practical rule is:

1. Create one sample right before the work within the measurement scope.
2. Initialize the outcome variable with the fallback error value.
3. In each normal exit branch, assign the appropriate outcome before `return`.
4. If a branch calls a method that can throw an exception, assign success only after that call returns.
5. Place only one `sample.stop(...)` call, in the outermost `finally` of the measurement scope.

`finally` runs when Java control flow exits the `try` block via normal return or by throwing an exception. Thus you do not need to catch an exception just to record a timer and rethrow it. The exception still propagates outward per the method's original contract.

Assignment placement matters: if you assign success before executing the data-loading step, an error during loading can be tagged as success. Finish the work that determines the outcome before assigning that label.

Also never `return` or throw another exception inside `finally` just for instrumentation. Doing so can override the return value or mask the business exception. Selecting from pre-registered timers keeps `finally` short and avoids building arbitrary tags on the exit path.

## 4. Complete Example: Four Branches, Each Call Recorded Exactly Once

### 4.1. Prepare Libraries and Run Commands

Create a separate experiment directory. Save the following `pom.xml` so Maven downloads Micrometer and transitive libraries into `lib/`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>timer-sample-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The version is pinned to make the standalone experiment reproducible. In a Spring Boot application, let Boot's BOM manage the Micrometer version matching the application.

In PowerShell, with Maven and JDK 17 or later available:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies "-DoutputDirectory=lib"
javac --release 17 -cp "lib/*" TimerSampleBranchesDemo.java
java -cp ".;lib/*" TimerSampleBranchesDemo
```

The `;` in the classpath above is Windows syntax; on Linux/macOS use `:`. The first download requires access to the dependency repository. No Spring context, HTTP server, or external services are required for this experiment.

### 4.2. Source Code TimerSampleBranchesDemo.java

```java
import java.time.Duration;
import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TimerSampleBranchesDemo {
    enum Outcome {
        REJECTED, CACHED, SUCCESS, ERROR
    }

    static final class LookupService {
        private final MeterRegistry registry;
        private final MockClock clock;
        private final Map<Outcome, Timer> timers = new EnumMap<>(Outcome.class);

        LookupService(MeterRegistry registry, MockClock clock) {
            this.registry = registry;
            this.clock = clock;
            for (Outcome outcome : Outcome.values()) {
                timers.put(outcome, Timer.builder("app.lookup.duration")
                        .description("Duration of a completed lookup")
                        .tag("outcome", outcome.name().toLowerCase(Locale.ROOT))
                        .register(registry));
            }
        }

        String lookup(String key) {
            Timer.Sample sample = Timer.start(registry);
            Outcome outcome = Outcome.ERROR;
            try {
                if (key == null || key.isBlank()) {
                    clock.add(Duration.ofMillis(1));
                    outcome = Outcome.REJECTED;
                    return "REJECTED";
                }
                if ("cached".equals(key)) {
                    clock.add(Duration.ofMillis(2));
                    outcome = Outcome.CACHED;
                    return "CACHED";
                }
                if ("boom".equals(key)) {
                    clock.add(Duration.ofMillis(4));
                    throw new IllegalStateException("backend unavailable");
                }
                clock.add(Duration.ofMillis(7));
                String result = "LOADED:" + key;
                outcome = Outcome.SUCCESS;
                return result;
            } finally {
                sample.stop(timers.get(outcome));
            }
        }
    }

    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            LookupService service = new LookupService(registry, clock);
            System.out.println("result=" + service.lookup(""));
            System.out.println("result=" + service.lookup("cached"));
            System.out.println("result=" + service.lookup("item-42"));
            try {
                service.lookup("boom");
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            long count = 0;
            double totalMillis = 0;
            for (Outcome outcome : Outcome.values()) {
                String tag = outcome.name().toLowerCase(Locale.ROOT);
                Timer timer = registry.get("app.lookup.duration").tag("outcome", tag).timer();
                double millis = timer.totalTime(TimeUnit.MILLISECONDS);
                System.out.printf(Locale.ROOT, "%s count=%d totalMs=%.1f%n",
                        tag, timer.count(), millis);
                count += timer.count();
                totalMillis += millis;
            }
            System.out.printf(Locale.ROOT, "all count=%d totalMs=%.1f meanMs=%.1f%n",
                    count, totalMillis, totalMillis / count);
        } finally {
            registry.close();
        }
    }
}
```

`MockClock` is used so each branch has deterministic timing. The `clock.add(...)` calls simulate processing time without sleeping and do not describe real `String` or cache timings. In real business code, replace the simulation with real work; never manually advance the clock or inject a desired duration into the timer.

Four timers are registered when creating the service. Each `lookup` call creates its own sample and selects only one timer in `finally`. The error branch does not overwrite `outcome`, so it keeps `ERROR`; the exception is still thrown outward.

### 4.3. Expected Stdout

```text
result=REJECTED
result=CACHED
result=LOADED:item-42
caught=backend unavailable
rejected count=1 totalMs=1.0
cached count=1 totalMs=2.0
success count=1 totalMs=7.0
error count=1 totalMs=4.0
all count=4 totalMs=14.0 meanMs=3.5
```

Values do not depend on machine speed because the clock is advanced only by the steps set in the experiment. `Locale.ROOT` ensures decimal numbers are printed consistently with a dot.

| Call | How it ended | Selected tag | Recorded duration |
| --- | --- | --- | --- |
| `lookup("")` | Returned early due to invalid input | `rejected` | 1 ms |
| `lookup("cached")` | Returned early from cache branch | `cached` | 2 ms |
| `lookup("item-42")` | Completed simulated data loading step | `success` | 7 ms |
| `lookup("boom")` | Threw `IllegalStateException` | `error` | 4 ms |

Total timer records equal 4, matching the number of measured calls including the failing call. Total time is `1 + 2 + 7 + 4 = 14 ms`; combined mean is `14 / 4 = 3.5 ms`. A `Timer` already includes the count of recordings; do not add a redundant counter just to know how many completions occurred.

## 5. Read Count and Total Time in the Right Scope

A sample does not record a list of intermediate steps or the names of branches traversed. It simply records one duration into the selected timer. In the example:

- Selecting `outcome=error` answers only for executions classified as errors.
- Summing counts across all four outcomes gives the number of completions within the measurement scope.
- Summing total times across all four outcomes gives the total time of those executions.
- To compute the combined mean, divide combined total time by combined count; do not take an unweighted average of branch means when branch counts differ.

Different branches can be slower or faster because they perform different work. Do not conclude the cache branch is faster from these simulated timings; to evaluate performance, measure real processing under appropriate traffic and environment conditions.

An unstopped sample does not increment count. If the application has a hanging operation, timers containing only completed operations may not yet reflect that operation. When you need to observe active task count and elapsed time of unfinished tasks, consider a dedicated `LongTaskTimer` with the exact boundary; it does not replace statistics of completed operations. [Micrometer Long Task Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

## 6. stop Is Not an Idempotent “Once-Only” Close Operation

`Timer.Sample` has no internal flag guaranteeing it records only once. In Micrometer 1.13, each `stop(timer)` computes the elapsed interval from the original start point and calls `record` on the timer. Thus calling it twice does not mean the second call is ignored or measures only the time since the first stop. This behavior must be controlled by your operation's lifecycle. [Reference Sample.stop method](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Timer.java).

The separate experiment below intentionally calls stop twice in error so you can see the consequence. Save as `DoubleStopDemo.java` using the same `lib/` directory:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class DoubleStopDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = registry.timer("demo.double.stop");
            Timer.Sample sample = Timer.start(registry);
            clock.add(Duration.ofMillis(10));
            System.out.println("firstNanos=" + sample.stop(timer));
            clock.add(Duration.ofMillis(5));
            System.out.println("secondNanos=" + sample.stop(timer));
            System.out.printf(Locale.ROOT, "count=%d totalMs=%.1f%n",
                    timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }
}
```

Run:

```powershell
javac --release 17 -cp "lib/*" DoubleStopDemo.java
java -cp ".;lib/*" DoubleStopDemo
```

Stdout:

```text
firstNanos=10000000
secondNanos=15000000
count=2 totalMs=25.0
```

The first call records 10 ms. The second call records 15 ms measured from the same start timestamp, yielding a total of 25 ms across 2 records. It is neither a single 15 ms record nor two disjoint intervals 10 ms + 5 ms.

From this, three usage patterns must be avoided:

- Calling `stop` before `return`, and then calling it again in `finally`.
- Calling it in `catch`, and then calling it again in `finally`.
- Storing a sample as a service field to reuse across different requests.

You can reuse registered timers because they accumulate multiple measurements. A Sample is the state of **one** measurement. If you want to measure two phases or two independent boundaries, define two separate measurements instead of treating `stop` as a stopwatch reset.

If multiple callbacks can race to finish the same operation, there must be one place deciding the single final outcome. You can funnel them into a single result future, or use a duplicate-recording guard such as `AtomicBoolean.compareAndSet(false, true)` at the exact owner of the operation. A deduplication flag only prevents duplicate metric records; it does not by itself resolve timeouts, cancellation, or precedence among business outcomes.

## 7. Asynchronous Operations: Returning from the Method Is Not Work Completion

For a method returning `CompletableFuture`, the method's `finally` block typically runs as soon as the future is returned. Stopping the sample there measures only launching/submitting the work, not waiting for the final result.

```text
Start sample
        ↓
Launch and obtain source future
        ↓
Method returns future to caller
        ↓
Work may still be running
        ↓
Source future completes normally / with error / cancelled
        ↓
Completion callback selects timer and stops sample
```

You must also handle separately the case where the launcher throws an exception **before returning a future**. Attaching `whenComplete` while ignoring this synchronous failure path drops an exit branch.

### 7.1. Complete Example with a Controllable Future

Save as `AsyncTimerSampleDemo.java`. We control future completion in `main` to verify without depending on thread scheduling or `Thread.sleep`.

```java
import java.time.Duration;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class AsyncTimerSampleDemo {
    private final MeterRegistry registry;
    private final Timer success;
    private final Timer error;
    private final Timer cancelled;

    AsyncTimerSampleDemo(MeterRegistry registry) {
        this.registry = registry;
        success = registry.timer("app.async.lookup.duration", "outcome", "success");
        error = registry.timer("app.async.lookup.duration", "outcome", "error");
        cancelled = registry.timer("app.async.lookup.duration", "outcome", "cancelled");
    }

    CompletableFuture<String> observe(Supplier<CompletableFuture<String>> launch) {
        Timer.Sample sample = Timer.start(registry);
        final CompletableFuture<String> source;
        try {
            source = Objects.requireNonNull(launch.get(), "source future");
        } catch (RuntimeException | Error ex) {
            sample.stop(error);
            throw ex;
        }
        return source.whenComplete((value, failure) -> {
            Throwable cause = failure;
            while (cause instanceof CompletionException && cause.getCause() != null) {
                cause = cause.getCause();
            }
            Timer target = cause == null ? success
                    : cause instanceof CancellationException ? cancelled : error;
            sample.stop(target);
        });
    }

    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            AsyncTimerSampleDemo demo = new AsyncTimerSampleDemo(registry);
            CompletableFuture<String> source = new CompletableFuture<>();
            CompletableFuture<String> observed = demo.observe(() -> source);
            System.out.println("pendingCount=" + demo.success.count());
            clock.add(Duration.ofMillis(20));
            source.complete("done");
            System.out.println("success=" + observed.join());

            CompletableFuture<String> failed = new CompletableFuture<>();
            CompletableFuture<String> observedFailure = demo.observe(() -> failed);
            clock.add(Duration.ofMillis(10));
            failed.completeExceptionally(new IllegalArgumentException("bad response"));
            printFailure("failure", observedFailure);

            CompletableFuture<String> cancelledSource = new CompletableFuture<>();
            CompletableFuture<String> observedCancellation = demo.observe(() -> cancelledSource);
            clock.add(Duration.ofMillis(30));
            cancelledSource.cancel(false);
            printFailure("cancelled", observedCancellation);

            try {
                demo.observe(() -> {
                    clock.add(Duration.ofMillis(5));
                    throw new IllegalStateException("launch failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println("launchFailure=" + ex.getClass().getSimpleName());
            }

            for (String outcome : new String[] { "success", "error", "cancelled" }) {
                Timer timer = registry.get("app.async.lookup.duration")
                        .tag("outcome", outcome).timer();
                System.out.printf(Locale.ROOT, "%s count=%d totalMs=%.1f%n",
                        outcome, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
            }
        } finally {
            registry.close();
        }
    }

    private static void printFailure(String label, CompletableFuture<String> future) {
        try {
            future.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException | CancellationException ex) {
            Throwable cause = ex instanceof CompletionException ? ex.getCause() : ex;
            System.out.println(label + "=" + cause.getClass().getSimpleName());
        }
    }
}
```

Run with the same library directory:

```powershell
javac --release 17 -cp "lib/*" AsyncTimerSampleDemo.java
java -cp ".;lib/*" AsyncTimerSampleDemo
```

Stdout:

```text
pendingCount=0
success=done
failure=IllegalArgumentException
cancelled=CancellationException
launchFailure=IllegalStateException
success count=1 totalMs=20.0
error count=2 totalMs=15.0
cancelled count=1 totalMs=30.0
```

Four operations were measured:

| Case | Recording point | Metric result |
| --- | --- | --- |
| Source future completes normally | `whenComplete` callback | `success`: 1 count, 20 ms |
| Source future completes exceptionally | `whenComplete` callback | Contributes 1 count, 10 ms to `error` |
| Source future is cancelled | `whenComplete` callback | `cancelled`: 1 count, 30 ms |
| Launcher throws before returning future | `catch` block around `launch.get()` | Contributes 1 count, 5 ms to `error` |

Thus the `error` branch has 2 records totaling 15 ms. Across all three timers there are 4 records, 65 ms. While the first future is still pending, `pendingCount=0` confirms the sample has not recorded a completion yet.

The two `stop` calls in `observe` serve **two mutually exclusive paths**: launching failed before obtaining a future, or a future was obtained and a completion callback attached. There is no shared `finally` calling stop a second time.

`Objects.requireNonNull` enforces the contract that the launcher must return a future. Returning `null` is a launch failure in this example. Unwrapping `CompletionException` helps identify cancellation before selecting one of the three finite timers.

### 7.2. Scope and Limits of the Future Example

`CompletableFuture` accepts only a single transition to a completed state among standard racing calls such as `complete`, `completeExceptionally`, and `cancel`. One centralized completion callback gives a single recording point for the source future. A callback without the `Async` suffix may run directly on the thread completing the future, so keep work inside it to brief metric recording. [Java 21 CompletableFuture contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

In the experiment, cancellation is applied to the **source future** `cancelledSource`. The future returned by `whenComplete` is a dependent stage. Cancelling the stage received by the caller does not guarantee cancelling the source future or stopping underlying work. If your API requires caller-side cancellation to propagate down to the task, design that mechanism separately; do not infer it from `Timer.Sample`. Even when the source future enters a cancelled state, that alone does not guarantee the actual task has stopped. The timer in this example measures the result lifecycle of the source future.

Similarly, a caller-side timeout does not necessarily mean the source future completed with a timeout error. You must define whether you are measuring how long the caller waited or how long the underlying task actually existed. If you want to distinguish timeouts from general errors, add a finite tag value and a clear classification rule at the completion point owned by the application.

The example assumes recording into a valid timer does not throw. If the `whenComplete` callback itself throws while recording, the dependent stage may reflect that error; the application needs an explicit policy if observability errors must not affect returned results. Do not put network calls, tag building from payloads, or error-prone tasks into this callback.

When reusing the pattern above, remember also that the sample starts **before** `launch.get()`: the measured duration includes launching, waiting for the result, and the gap until the callback reads the clock. If you want to measure only execution time inside a queued task, you need a separate start point inside that task itself.

## 8. Applying in Spring Boot Actuator

The programs above create their own `SimpleMeterRegistry` for standalone verification. They do not provide HTTP endpoints. In a Boot application with Actuator, receive `MeterRegistry` via the constructor of your service or metrics component, register timers on that registry, and keep samples in local variables for each operation. Boot configures registries according to backends on the classpath. [Metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

When moving from experiment to application:

- Use real business logic instead of `MockClock` and `clock.add` calls.
- Use the Boot-managed registry instead of creating a private registry in each service.
- Do not call `close()` on the injected registry after each request; registry lifecycle belongs to the application.
- Keep shared timers and per-call samples, even when the service is a singleton.
- Check whether another instrumentation layer already measures the same boundary so you do not record twice into the same timer.

If the application already has a web server and permits reading management endpoints, an exposure configuration might be:

```properties
management.endpoints.web.exposure.include=health,metrics
```

After the real execution path has registered and recorded `app.lookup.duration`, you can query:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration"
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration?tag=outcome:error"
curl.exe "http://localhost:8080/actuator/metrics/app.lookup.duration?tag=outcome:cached"
```

An unfiltered endpoint may sum series with the same name; filter by `outcome` to view one branch. Inspect both `measurements` and `availableTags`, and do not infer which branch occurred solely from the timer having been pre-registered.

In a real application, durations will depend on real processing and the units used by the backend/endpoint; do not expect the simulated 1, 2, 7, 4 ms values to reappear. If a module has no HTTP server, you can still inspect the registry directly or use your configured backend; there is no need to create a business API just to practice `Timer.Sample`.

## 9. Prometheus Export and Understanding Measurement Units

`stop` returns nanoseconds, while `Timer` converts durations to the appropriate unit on export. In Java code, explicitly use `totalTime(TimeUnit.MILLISECONDS)` or the desired unit; do not assume a returned number is milliseconds when the API specifies nanoseconds.

In a Boot application using Prometheus, you can add the registry and expose the corresponding endpoint:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

With typical naming conventions, the `app.lookup.duration` timer exports series such as:

```text
app_lookup_duration_seconds_count{outcome="success"}
app_lookup_duration_seconds_sum{outcome="success"}
```

These are **series name and label patterns**, not complete scrape output with values. Inspect actual scrape output to verify names, labels, and the application's common tags. [Micrometer Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

The average duration of completed calls over a window can be calculated across the same label set:

```promql
sum by (job, outcome) (rate(app_lookup_duration_seconds_sum[5m]))
/
sum by (job, outcome) (rate(app_lookup_duration_seconds_count[5m]))
```

The result here is in seconds. Multiply by 1,000 if you want milliseconds. Enough scrape samples are needed to compute a rate; a window with no new recordings can produce a zero denominator, which is not proof that every operation took 0 seconds.

You cannot infer p95 or p99 from count and total time alone. If percentiles are needed, configure appropriate histograms/percentiles on the timer or through the application's metrics configuration. Choosing `Timer.Sample` instead of `record` does not automatically enable histograms. [Histograms and percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 10. Boundary Changes That Alter Measurement Meaning

### Measure the Whole Operation or Each Attempt?

If an operation has retries, a sample wrapping the entire retry loop measures total time to final outcome, including backoff waits between attempts. A fresh sample per attempt measures each attempt. Both can be useful, but they need distinct names and classifications; do not sum them and call that total user requests.

A failed first attempt followed by a successful retry does not necessarily mean the outer operation timer gets `outcome=error`. The outer measurement's outcome should reflect the final-outcome rule you defined. If you return a fallback value after an error, decide explicitly whether it belongs to `success` or a value like `fallback`, instead of leaving the outcome variable at its default due to forgetting to assign it.

### Include Resource Cleanup Time?

If the operation is defined as completing only after closing resources, place the stop point after cleanup and ensure errors during cleanup still reach the recording point. A cleanup call can throw an exception before `sample.stop` inside the same `finally`, preventing the recording call from running. An outer `try/finally` wrapping both the work and resource cleanup helps establish a clearer boundary.

Do not alter cleanup's error contract merely to make charts look clean. What must be agreed is whether “completed successfully” includes successful resource cleanup, and which part the timer surrounds.

### Choose the Tool for the Question

| Need | Suitable approach |
| --- | --- |
| Measure a synchronous block with target timer known upfront | `Timer.record` or `recordCallable` is usually cleaner |
| Outcome/tag known only after processing | `Timer.Sample`, then select timer upon completion |
| Measure until a future completes | Sample tied to the future's lifecycle and completion callback |
| Count/time tasks still in progress | A `LongTaskTimer` or dedicated in-flight task metric |
| Understand individual steps and cross-service relationships | Appropriate tracing/observability; a sample does not create trace spans by itself |

Having multiple `return` statements does not automatically require using a sample. If every branch records to the same timer and no end-of-call tag decision is needed, the block-wrapping API can be easier to read. The primary benefit of a sample is separating start timing from choosing the destination meter once the outcome is clear.

## 11. Diagnosing Unexpected Results

| Symptom | Cause to check |
| --- | --- |
| Count is lower than completed operations | A branch bypassed the stop point, callback was not attached, or synchronous launch error before returning future was missed |
| Count is higher than operations | Two places call stop, another instrumentation layer writes the same meter, or counting per-attempt while comparing to request count |
| Asynchronous duration is very short | Sample stopped when returning the future, before the source future completed |
| Failed branch recorded as success | Assigned success label before a call that can still throw |
| Metric series count keeps growing | Tag taken from arbitrary input/message/error text |
| Flaky timing tests | Using wall-clock time and sleep with absolute assertions; control the clock to verify logic |
| MockClock timings do not match | Sample does not use that registry's clock, or concurrent tasks are mutating the test clock together |
| Hanging tasks missing from count | Standard Timer records only on stop; use an in-flight task metric for unfinished tasks |
| Timer exists but all counts are 0 | Timers pre-registered, but the path has not run or sample was not stopped |
| Caller cancelled yet timer keeps waiting | Only the dependent stage was cancelled, while the source future has not ended under the measured boundary |

`finally` handles normal Java control-flow exits, not guaranteed recording when a process is forcefully killed or the JVM exits abruptly. Nor should a mismatch between started and completed counts be used as proof of an application bug without accounting for tasks still in progress.

## 12. Verification Exercises

1. Call `lookup("cached")` three times on a fresh registry. Predict that the `cached` timer has count = 3 and simulated total time = 6 ms; other timers remain at count = 0 because they were pre-registered.
2. Add a new early-return branch. Define its finite outcome and verify there is only one recorded sample without adding `stop` before `return`.
3. Make the data-loading branch throw an exception before the `SUCCESS` assignment line. Verify the exception still reaches the caller and `error` count increases, while `success` does not increment for that call.
4. Using `DoubleStopDemo`, explain why the second stop records 15 ms instead of 5 ms. Fix the usage by leaving only one stop point, without modifying the library to hide duplicate recordings.
5. In the future example, hold a source future uncompleted after the method returns. Verify no new record appears yet; then complete it and verify count increments once.
6. Create an already-completed future before calling `observe`. The callback may run immediately upon attachment; there must still be exactly one record whose duration reflects the boundary at `observe`, not the time the future ran earlier.
7. Compare cancelling the source future against cancelling the stage returned by `whenComplete`. State clearly which case the instrumentation in the example treats as completion and why cancelling the result does not prove the real task stopped.

A usable measurement requires **one sample per operation, one clearly defined end boundary, one place determining the final outcome, and one recording for that boundary**. Only when those align do per-branch counts and durations carry valid analytical meaning.
