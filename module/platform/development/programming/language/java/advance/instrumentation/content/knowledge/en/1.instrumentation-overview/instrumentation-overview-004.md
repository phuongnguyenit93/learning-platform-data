# Instrumentation Applications in Java: Call Counting, Timing, Error Tracking, and Coverage

Instrumentation is the practice of attaching **observation points (probes/hooks)** to program execution to know which code ran, how many times, how long it took, and how it ended. In Java, measurement points can live in the source code itself, in a wrapper/proxy layer, or be inserted into bytecode by a Java agent. A useful measurement must have a clear **measurement boundary, unit, outcome classification, and observation overhead**.

This lesson covers four applications: **call counting**, **timing**, **error tracking**, and **code coverage**. The first three typically serve runtime observability; coverage primarily serves testing. They share probe-placement techniques but do not measure the same quantity.

## 1. Choosing the Right Question and Measurement Boundary

| Goal | Probe placement | Data | Questions that can be answered |
| --- | --- | --- | --- |
| Call counting | Entry of method/API/operation | Invocation/attempt count, completion status | Is the operation called often? Are retries increasing? |
| Timing | Before and after the operation, including error branches | Duration of each call; total/distribution | How are average latency and p95/p99 changing? |
| Error tracking | Throw site or result-return boundary | Failure count, error type, contextual trace/log | Which error is increasing? What is the failure rate? |
| Coverage | Bytecode probes during test runs | Executed instruction/line/branch/method | Which code segments or branches are still untested? |

**One HTTP request can invoke multiple service methods; one service can perform multiple queries due to retries.** Therefore, request count, method invocation count, and database attempt count must not be added together or compared directly as the same unit. Name metrics after what is being measured; agree on where a "call" begins and when it is considered finished.

A typical synchronous flow:

~~~text
caller
  -> [entry: attempted++, start = nanoTime()]
  -> [execute logic]
     -> success: return result
     -> error: failed++, rethrow original error
  -> [finally: record duration, completed++]
  -> caller receives result or error
~~~

At a given moment, **attempted > completed** can occur because a call is still in flight. In a multithreaded system, reading counters non-simultaneously can also produce an inconsistent transient snapshot.

## 2. Standalone Runnable Example on Java 17+

We build an item lookup service. The `MonitoredCatalog` decorator records all calls **that pass through itself**: start count, completion count, failure count, and total nanoseconds.

**File: InstrumentationDemo.java**

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class InstrumentationDemo {
    interface Catalog {
        String lookup(int id);
    }

    static final class CatalogImpl implements Catalog {
        @Override
        public String lookup(int id) {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be > 0");
            }
            return "item-" + id;
        }
    }

    static final class Metrics {
        final LongAdder attempted = new LongAdder();
        final LongAdder completed = new LongAdder();
        final LongAdder failed = new LongAdder();
        final LongAdder totalNanos = new LongAdder();
    }

    static final class MonitoredCatalog implements Catalog {
        private final Catalog delegate;
        private final Metrics metrics;

        MonitoredCatalog(Catalog delegate, Metrics metrics) {
            this.delegate = delegate;
            this.metrics = metrics;
        }

        @Override
        public String lookup(int id) {
            metrics.attempted.increment();
            long started = System.nanoTime();
            try {
                return delegate.lookup(id);
            } catch (RuntimeException | Error failure) {
                metrics.failed.increment();
                throw failure;
            } finally {
                metrics.totalNanos.add(System.nanoTime() - started);
                metrics.completed.increment();
            }
        }
    }

    public static void main(String[] args) {
        Metrics metrics = new Metrics();
        Catalog catalog = new MonitoredCatalog(new CatalogImpl(), metrics);

        System.out.println(catalog.lookup(3));
        try {
            catalog.lookup(0);
        } catch (IllegalArgumentException failure) {
            System.out.println("error: " + failure.getMessage());
        }

        System.out.println("attempted=" + metrics.attempted.sum());
        System.out.println("completed=" + metrics.completed.sum());
        System.out.println("failed=" + metrics.failed.sum());
    }
}
~~~

Compile/run in the directory containing the file:

~~~bash
javac --release 17 InstrumentationDemo.java
java InstrumentationDemo
~~~

**Deterministic stdout:**

~~~text
item-3
error: id must be > 0
attempted=2
completed=2
failed=1
~~~

The `lookup(3)` call returns successfully. The `lookup(0)` call throws `IllegalArgumentException`; the decorator increments `failed` and then **rethrows the same exception**, while the `finally` block still records duration and completed. Specific timing is not printed because it varies by environment. This is a **pure JDK** example, requiring no Spring, AOP, or Java agent.

**Limitation of the example:** the code only measures when the caller uses `MonitoredCatalog`. A caller holding a reference to `CatalogImpl` and calling it directly will bypass the probe. `LongAdder.sum()` is suitable for metric reporting but does not provide an atomic snapshot while multiple threads are updating.

## 3. Counting Calls Correctly

Call counting needs to distinguish the phases:

- **attempted** increments on entry, including calls that later fail.
- **completed** increments when the operation actually finishes, whether it succeeded or failed.
- **failed** increments when the outcome is defined as a failure.

If synchronous calls have finished and error classification does not miss any cases, the success count equals **completed − failed**. When there are still in-flight calls or concurrent reads of `LongAdder` instances, this subtraction may temporarily fail to reflect a single consistent snapshot.

`LongAdder` is suitable for counters updated frequently by many threads: additions can be striped internally to reduce contention. However, `sum()` does not guarantee a consistent snapshot across increments. If business logic requires an exact transactional snapshot, use synchronization or an appropriate data structure instead of treating metrics as a ledger.

**Decisions that must be named clearly:**

1. An HTTP request with three retries has **one logical request** but **three dependency attempts**.
2. A service calling another method on the same object may not go through an external proxy; if self-invocations also need to be counted, probe placement must change.
3. A request touching a controller, service, and repository may produce three valid counters, but they measure three different boundaries.
4. For asynchronous tasks, increment completed **when the future/stream finishes**, not when the method merely returns the async handle.

Metric labels should be a finite set of values: `operation=lookup`, `outcome=success|failure`, `error_group=timeout|validation`. Do not use request IDs, user IDs, URLs with continuously varying parameters, or exception messages as labels; unbounded cardinality will overload the monitoring system and increase cost. Individual identifiers belong in managed traces/logs.

## 4. Measuring Execution Time

Use two `System.nanoTime()` readings and take the **difference** to measure elapsed time: `elapsedNanos = end − start`. The absolute value of `nanoTime()` is not a wall-clock date/time timestamp and should not be exported to compare across machines. `System.currentTimeMillis()` is suitable for calendar timestamps, but the wall clock can be adjusted; it is not the preferred choice for measuring short durations.

The example in section 2 takes a timestamp before calling the delegate and records total nanoseconds in `finally`, so **calls that throw an exception also get a timing sample**. After completion, the average in milliseconds can be computed as:

~~~text
average_ms = totalNanos / completed / 1_000_000.0
(if completed > 0 and each completed has exactly one timing sample)
~~~

**The average does not tell you p95 or p99.** For example, 99 calls take 10 ms and one call takes 2,000 ms: the average is only about 29.9 ms, yet there is still a slow 2-second experience. To know latency percentiles/tails, you must store the distribution using a **histogram/timer** or an appropriate statistical sampler. A total-duration counter and a call counter are not enough to derive percentiles.

Several concepts need to be separated:

- **Wall-clock latency** of a call may include waiting on I/O, locks, and the scheduler; it does not equal CPU time.
- **Operation time** at a service does not necessarily equal **end-to-end request latency** at the HTTP client.
- With `CompletableFuture` or `CompletionStage`, measuring until the future is returned only reflects task submission time. If you need end-to-end latency, record when the future completes (including exceptional completion/cancellation), while avoiding double recording.
- Under heavy load, instrumentation has overhead; JIT, GC, warm-up, contention, and the measurement environment also affect results. For microbenchmarking, use JMH under controlled conditions and do not draw conclusions from a single `nanoTime` measurement.

On a running system, tracking **request rate, error rate, latency distribution, and saturation** together is more meaningful than a single isolated average.

## 5. Tracking Errors Without Changing Program Behavior

**Errors must be defined by contract.** In the example, an exception escaping `lookup` is counted as failed. However, an API might return HTTP 5xx without throwing an exception; conversely, a `NOT_FOUND` result might be normal business behavior. Measurement conventions must clearly specify which situations count as failures and at which boundary.

Safe handling pattern:

1. Start the timer, increment attempted.
2. Invoke the business logic.
3. If an error matching the failed definition occurs, increment the failure counter and record the normalized error type.
4. Rethrow the original exception or return the result unchanged per contract; **the probe must not swallow errors or alter results**.
5. In `finally` (or a completion callback), record duration and completed.

In the example, `catch (RuntimeException | Error)` is appropriate because the `Catalog.lookup` signature declares no checked exceptions. If an interface declares checked exceptions, the observation logic must handle them according to the contract; do not ignore them just because the example catches unchecked ones. It is not necessary to log every exception: many errors may be caught and handled successfully by the caller. When using reflection with `Method.invoke`, the method's exception may be wrapped in `InvocationTargetException`; inspect `getCause()` to classify it accurately and rethrow the appropriate business error.

**Error rate** is typically `failed / completed` within the same operation set and time window, with a non-zero denominator. If one failing request generates multiple exceptions across multiple layers, counting the sum of those exceptions is not equivalent to "failed request count." Tracing connects the sequence of processing spans, while counters track trends.

When recording diagnostic details, collect only necessary data, mask tokens/passwords/PII, avoid printing sensitive payloads, and bound log volume. Attach correlation/trace IDs to traces/logs instead of creating a new metric label per request. A recorder must not throw a new error that alters the business execution path.

## 6. Code Coverage: Instrumentation for Testing

**Code coverage** measures which code was executed during test runs. Tools like **JaCoCo** attach probes to bytecode, run tests, and aggregate the data. Coverage is not a production traffic counter or timer. Common metrics:

| Metric | What it measures | Limitations |
| --- | --- | --- |
| Instruction | Which bytecode instructions were executed | Finer-grained than source lines; may include compiler-generated code |
| Line | Which lines with executable code ran | A single line with multiple branches may not be fully covered |
| Branch | Decision branches such as true/false of `if`, `switch` | Requires boundary test cases; not every exception path appears as a separate branch |
| Method/Class | Which methods/classes had part of their code executed | Does not evaluate assertion strength |

In `CatalogImpl.lookup`, there is the condition `id <= 0`. If a test only calls `lookup(3)`, the exception-throwing branch has not been executed; adding a `lookup(0)` case with an assertion verifying the exception exercises this path. **High coverage does not prove logic is correct**: tests can execute a line without asserting properly, or miss race conditions, misconfigurations, integration bugs, and boundary data.

### 6.1. Illustrative Test with JUnit Jupiter

In a Java Gradle project, place `InstrumentationDemo.java` in `src/main/java` and the test below in `src/test/java`, in the same package. The snippet uses the default package for brevity; real projects should declare a consistent package.

**File: InstrumentationDemoTest.java**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class InstrumentationDemoTest {
    @Test
    void recordsSuccessAndFailure() {
        var metrics = new InstrumentationDemo.Metrics();
        var catalog = new InstrumentationDemo.MonitoredCatalog(
                new InstrumentationDemo.CatalogImpl(), metrics);

        assertEquals("item-3", catalog.lookup(3));
        assertThrows(IllegalArgumentException.class, () -> catalog.lookup(0));

        assertEquals(2, metrics.attempted.sum());
        assertEquals(2, metrics.completed.sum());
        assertEquals(1, metrics.failed.sum());
    }
}
~~~

The test verifies both the return value/exception and the counter increments. Do not assert a fixed number of nanoseconds: that quantity depends on timing and environment. You can add an assertion `totalNanos.sum() >= 0` after completion if you need to verify the timing recording path.

### 6.2. Configuring JaCoCo with Gradle Groovy DSL

The following is an **example build.gradle** using Java, JaCoCo, and JUnit 5:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        html.required = true
        xml.required = true
    }
}
~~~

Run:

~~~bash
./gradlew test jacocoTestReport
~~~

On Windows PowerShell you can use `.\gradlew.bat test jacocoTestReport`. With the plugin's default report path, open `build/reports/jacoco/test/html/index.html`; the XML report can be used for CI. A report only includes the tests and JVMs/tasks configured for collection. If there are integration tests/separate forked JVMs, dynamically loaded code, or excluded classes, configure them appropriately before interpreting percentages.

**Coverage is evidence of "code having been traversed."** Test quality also relies on assertions, branch/boundary design, concurrency tests, mutation tests, and integration tests when needed. Do not equate 100% coverage with 100% production reliability.

## 7. Ways to Attach Instrumentation in Java

| Mechanism | When appropriate | Key limitations |
| --- | --- | --- |
| Calling recorder directly in a method | Few measurement points, easy to control | Easy to miss a branch or forget `finally` |
| Decorator/wrapper | Want to separate measurement from business logic as in the example | Only captures calls going through the wrapper |
| JDK dynamic proxy | Object has an interface, want to intercept invocations | Does not automatically capture self-invocation or callers invoking the target object directly |
| Spring AOP/AspectJ | Want to centralize cross-cutting logic across many methods | Requires understanding advice scope, proxies, and weaving; does not cover every call by default |
| Java agent/bytecode transformer | Need to attach probes across many classes/libraries without editing each source file | Must handle classloading, JVM compatibility, configuration, and overhead |
| Coverage tool like JaCoCo | Want to measure test execution paths | Provides coverage, not a replacement for operational timers/counters |

Java provides the `java.lang.instrument` API. A Java agent can use the `premain` entry point at startup via `-javaagent`, or `agentmain` for dynamic attach when supported by the environment. The agent registers a `ClassFileTransformer` and can transform bytecode at load time or retransform when permitted. Libraries such as ASM or Byte Buddy assist with bytecode manipulation; JaCoCo uses probes to record coverage.

The following command is only an **integration template when you already have a valid agent.jar and a manifest containing the appropriate entry point**; it cannot be run with just the demo program above:

~~~bash
java -javaagent:/path/to/agent.jar -jar application.jar
~~~

Do not assume every class/method will be intercepted automatically. Already-loaded classes, self-calls, native methods, different classloaders, exclusion rules, or retransform restrictions can all make the measurement scope differ from expectations. An agent must avoid instrumenting the recorder library itself in a way that causes infinite recursion, and must test startup/GC/CPU impact before rollout.

Micrometer or OpenTelemetry are often useful for standardizing metrics/tracing and exporting data, but **choosing the right boundary and defining outcomes** remains a design responsibility. Bytecode instrumentation, proxies, and logging are merely ways of placing probes.

## 8. Process for Applying to a Real System

**Step 1 — Define the question.** For example: "Is the lookup API getting slower?", "Is the dependency retrying excessively?", "How many requests end in error?", "Has the timeout branch been tested?". Do not lump everything under one generic metric.

**Step 2 — Choose measurement points.** At the request boundary to count requests, the service boundary to measure operations, the dependency boundary to count attempts; at bytecode under a coverage tool to see which code tests execute. Avoid adding different layers together and calling them the same unit.

**Step 3 — Capture the full lifecycle.** For sync, record start before processing and end in `finally`; for async, record end when it actually completes/errors/cancels per contract. Record exactly once per completed operation, including error branches.

**Step 4 — Classify.** Choose finite status groups: success, validation/input error, dependency error, timeout/cancellation. Do not turn arbitrary request IDs or exception messages into metric labels.

**Step 5 — Test the recorder.** Run one success, one exception, multiple concurrent calls, retries, and async if applicable. For counters, assert totals after tasks have completed; for timing, assert that samples exist rather than exact nanosecond numbers. For agents/proxies, verify in practice which methods are actually intercepted.

**Step 6 — Measure overhead and observe.** Probes can cost CPU, allocations, and bandwidth. Prefer aggregated counters/timers/histograms, and optionally sample traces purposefully, but clearly record the sampling rate and do not treat sample count as actual traffic. Evaluate impact on a representative workload before enabling broadly.

**Step 7 — Connect to action.** Counters and rates help detect rising traffic/retries; histograms show p95/p99; failure counts and traces pinpoint errors; JaCoCo helps pick branches needing more tests. These data sources complement rather than replace one another.

### Analysis Scenario

Suppose a lookup API has a stable **request rate**, while **p95 latency** rises and the error rate stays low. This suggests investigating tail latency at the service/dependency rather than concluding the API is receiving too many requests. If the error rate rises alongside dependency timeouts, you can inspect error traces and attempt/retry counts. If test coverage has not hit the timeout branch, add tests with assertions for timeouts and retries before changing logic. Base each conclusion on **the right kind of evidence**.

## 9. Common Mistakes

| Mistake | Why it is wrong | Proper approach |
| --- | --- | --- |
| Recording duration only after the method call | Exceptions skip the recording line | Record in `finally` or a completion callback |
| Using `currentTimeMillis` to time short methods | Wall clock can be adjusted | Use `nanoTime()` difference |
| Inferring p99 from total duration/count | Average does not determine distribution | Use a distribution histogram/timer |
| Counting both controller and service into the same request count | Double-counts different units | Clear names/labels per boundary |
| Catching exceptions and returning a dummy value | Alters business behavior | Record metric and rethrow original error |
| Classifying `InvocationTargetException` as a business error | Loses the real exception type | Unwrap `getCause()` appropriately |
| Treating `LongAdder.sum()` as an atomic snapshot | Different counters update at different times | Accept approximate stats or synchronize when needed |
| Using coverage as a substitute for test assertions | "Executed" does not mean "correct" | Test results, edge cases, and error paths |
| Using user/request ID as a metric label | Cardinality explodes | Keep labels finite; put IDs in traces/logs |
| Measuring only when `CompletableFuture` is returned | Misses async execution time | Record on complete/failure/cancel |
| Enabling an agent broadly without measuring overhead | May increase latency or affect classloading | Test compatibility, benchmark workload, scope configuration |

## 10. Self-Check

1. An HTTP request calls a dependency three times due to retries: what do request count and attempt count measure respectively?
2. Why must `finally` record duration even when a method throws an exception?
3. Can p95 be computed accurately from `totalNanos` and `completed`? Why or why not?
4. Does a test that only calls `lookup(3)` cover all branches of `if (id <= 0)`?
5. Does self-invocation bypassing a proxy cause measured call counts to be missed?
6. With `CompletableFuture`, how does the time the future is returned differ from the time the operation completes?

Instrumentation is valuable when **probes are in the right place, units are right, the measurement lifecycle is complete, and data is interpreted correctly**. Preserve business results/exceptions, verify recorders with tests, and understand that coverage is a tool for finding testing gaps, not a certification of correctness.
