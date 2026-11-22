# Measuring Elapsed Time with a Monotonic Time Source in Java Instrumentation

**Problem:** A Java agent wants to measure how long a method, query, task, or span takes to complete. It needs to choose an **elapsed-time source for measuring the interval between two points** rather than taking two calendar date/time values and subtracting them. In Java, the foundational API is **`System.nanoTime()`**; the correct usage is to take two samples in the same JVM and compute **`end - start`**.

~~~java
long start = System.nanoTime();
try {
    // The work to be measured goes in this block.
} finally {
    long elapsedNanos = System.nanoTime() - start;
    // Record elapsedNanos using a non-throwing recorder.
}
~~~

This is a **fragment** illustrating where to place the clock, not a complete program. This article explains why a monotonic source must be used, how to handle overflow, how to cover `return` and exception paths, where to place timers in instrumentation, accuracy and impact on metrics, along with standalone compilable/runnable Java 17 examples.

## 1. Wall-Clock Time and Elapsed Duration Are Two Different Quantities

A system typically needs to answer two questions:

1. **At what time did the event occur?** For example, `2026-10-31T08:05:00Z`. This is a *wall-clock timestamp*, used for logs, auditing, and correlating events by point in time.
2. **How long did the work take to run?** For example, `42.3 ms`. This is an *elapsed duration*, computed as the difference between two samples taken from **the same time source intended for measuring intervals**.

API comparison in Java:

| API | Returns | Suitable for | Not suitable for |
|---|---|---|---|
| `System.currentTimeMillis()` | Milliseconds since the Unix epoch (wall clock) | Recording approximate date/time timestamps, some logs | Measuring latency because the wall clock can be adjusted and has limited resolution |
| `Instant.now()` | UTC calendar instant from the system clock | Event timestamps, auditing | Not a monotonic source by default for measuring elapsed time |
| `Clock.systemUTC().instant()` | Timestamp based on the system clock | Configurable time points, injectable in applications | Not synonymous with a monotonic clock |
| **`System.nanoTime()`** | `long` nanosecond value relative to an **arbitrary JVM origin** | **Measuring elapsed time**, timeouts, durations within a JVM | Not used as an epoch, not directly displayed as a date/time |
| `ThreadMXBean.getCurrentThreadCpuTime()` | Thread CPU time, when supported and enabled by the JVM | Analyzing **thread CPU usage** | Does not replace transaction duration that includes I/O/waiting |

**Why is the wall clock unsuitable?** System time can be synchronized/adjusted by NTP, an administrator, or OS mechanisms. If you compute:

~~~java
long startMs = System.currentTimeMillis();
doWork();
long elapsedMs = System.currentTimeMillis() - startMs;
~~~

then you may get negative or anomalous durations if the wall clock is adjusted between the two reads. Measuring with `nanoTime()` avoids depending on calendar date/time representation.

Having a nanosecond API in `Instant.now()` does not mean the underlying clock has true one-nanosecond resolution or provides monotonicity. **Data unit, accuracy/precision, and clock source type are three distinct properties.**

## 2. `System.nanoTime()`: Only the Difference Between Two Samples Is Meaningful

The Java SE specification defines `nanoTime()` as returning a `long` value from the JVM's high-resolution time source. **The origin is fixed but arbitrary**, and may even lie in the future relative to the current time; the returned number **can be negative**. Two different JVMs may have different origins.

~~~java
long startNanos = System.nanoTime();
performOperation();
long endNanos = System.nanoTime();

long elapsedNanos = endNanos - startNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

This is an illustrative fragment inside a method that already has `performOperation()`; the arithmetic part is valid Java syntax.

Key points to understand:

- **`startNanos` is not a timestamp**. Do not convert it directly to an `Instant`, and do not log the raw value thinking it is nanoseconds since the Unix epoch.
- **Only take the difference `end - start` from the same JVM**. Do not take `nanoTime()` from service A on JVM A and subtract `nanoTime()` from service B on JVM B.
- **Nanosecond precision does not mean nanosecond resolution**: the return type and unit are nanoseconds, but the clock may not update every nanosecond; two calls close together can return the same value, yielding a duration of 0.
- Actual accuracy depends on the JVM, OS, and hardware. **Do not** conclude that a task actually took exactly 1 ns just because the API uses ns units.
- The standard measurement is elapsed time (*elapsed/wall duration*), **not CPU time alone**. Lock wait time, I/O wait, thread scheduler delays, or GC can be included in the duration depending on where the markers are placed.

The term "monotonic clock" in probe design emphasizes **using a relative time source that is not adjusted to the calendar**. Do not rely on the absolute value of `nanoTime` numbers to infer chronological ordering across a distributed system.

## 3. Standard Formula and Timestamp Comparison Pitfalls

The safest pattern for measuring duration:

~~~text
t0 = System.nanoTime()
      [work segment]
t1 = System.nanoTime()

elapsedNanos = t1 - t0
elapsedMillis = elapsedNanos / 1_000_000.0
~~~

If you need a timeout limit, compare the **difference** against the timeout:

~~~java
long started = System.nanoTime();
long timeoutNanos = java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(250);

// After performing some work:
boolean timedOut = System.nanoTime() - started >= timeoutNanos;
~~~

Do not use:

~~~java
long deadline = started + timeoutNanos;
boolean timedOut = System.nanoTime() >= deadline;
~~~

When the `long` value crosses the numerical boundary, deadline addition and absolute comparison can produce incorrect results. The Java specification recommends **`System.nanoTime() - start >= timeoutNanos`** instead of `now >= start + timeoutNanos`.

### Overflow: Why Can Subtraction Still Be Correct?

`System.nanoTime()` uses a signed `long`, so the value itself can cross `Long.MAX_VALUE` and become negative. As long as the actual elapsed interval is shorter than about **2^63 ns**, which is approximately **292 years**, two's-complement `long` subtraction still accurately represents the interval within the valid range. If the interval exceeds this limit, the specification **does not guarantee** the difference is computed correctly due to overflow.

**Arithmetic example simulating `long` overflow:**

~~~text
start = Long.MAX_VALUE - 3
end   = Long.MIN_VALUE + 6

end - start = 10 (nanoseconds, via long subtraction)
~~~

This does not claim a real JVM has just run past the 292-year boundary; the example only clarifies **why comparing raw values `end >= start` is wrong**. After this simulated wraparound, `end` is negative, yet the duration of 10 ns remains valid.

Practical rules:

1. Only compute elapsed time from **two samples in the same JVM**.
2. Only compare against a **non-negative timeout**; if accepting a timeout from a user, check the sign and avoid overflow when converting units.
3. Timeouts and actual measured intervals must stay within the appropriate `long` representation range.
4. Do not use `nanoTime()` values as global time keys or cross-JVM event IDs.

## 4. Where Should Markers Be Placed to Measure the Right Target?

In instrumentation, **the start and end points determine the meaning of the metric**. Name metrics based on their actual semantics.

~~~text
Receive request
    |
    v
[ t0: enter handler method ]
    |
    +---- validate
    +---- query database       (includes I/O wait)
    +---- serialize response
    |
[ t1: exit handler method ]
    |
    v
Return response
~~~

`elapsed = t1 - t0` measures **the time from entering to exiting the method**, including waiting and scheduling that occur during that interval. It does not necessarily measure the entire time from when the packet arrives at the socket until the last byte is sent to the client. If you want end-to-end latency, you must instrument at the appropriate protocol/request boundary.

| Timer placement | What the metric reflects |
|---|---|
| Around a synchronous method body | Method call time from entry to return/throw |
| Around a JDBC call | Time the caller is held in the JDBC API, which may include driver/network wait |
| Around an executor task | If started after the task is dequeued: *execution time*; if started before `submit`: includes *queue time* |
| Around a `CompletableFuture` until completion | Time waiting for the asynchronous result, not just future creation time |
| Around a retry loop | Total latency **of all attempts** and backoff intervals if inside the timer |
| Around each individual attempt | Latency of each attempt; distinct from total request latency |

You must decide whether to **count once per request** or **per attempt**, and record separate metrics if you want both. Misplacing the timer is a much larger source of semantic error than a few nanoseconds of clock variance.

## 5. Covering Success, `return`, and Exception Paths with `try/finally`

When instrumenting a synchronous method, a common mistake is placing the clock at the end of the method:

~~~java
long start = System.nanoTime();
Result result = doWork();
long elapsed = System.nanoTime() - start;
record(elapsed);
return result;
~~~

The fragment above **fails to record the duration if `doWork()` throws an exception**. Moreover, methods with multiple `return` branches make it very easy to miss paths. Use `finally` to place the end-time measurement:

~~~java
long start = System.nanoTime();
try {
    return doWork();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    record(elapsedNanos);
}
~~~

This is an illustrative fragment requiring `doWork()` and `record(...)` in a real program. `finally` still executes when control leaves `try` via a normal `return` or an exception. `finally` is not guaranteed to run if the process is forcibly killed, the JVM is halted, or an unrecoverable system condition occurs.

**Caution:** If `record(...)` itself throws an exception from `finally`, it can **mask the original exception** or alter the method's outcome. An agent's recorder should be a very lightweight, fault-tolerant operation that avoids dangerous side effects:

~~~java
long start = System.nanoTime();
try {
    return doWork();
} finally {
    long elapsed = System.nanoTime() - start;
    try {
        metrics.record(elapsed);
    } catch (RuntimeException metricsError) {
        // Do not let a measurement error mask the business result/exception.
    }
}
~~~

This is only a strategy sketch; production code needs to decide how to log metrics errors separately rather than silently ignoring all errors without observability. In systems with high reliability requirements, you can use a recorder designed not to throw from the start and verify its API contract.

## 6. Standalone Java 17 Example: Measuring Success and Failure, Testing with a Fake Ticker

You should not test timing by hard-asserting "code runs in 5 ms": thread scheduling, the VM, and the OS will cause values to fluctuate. Instead, **inject the time source** so unit tests can return predetermined samples. In production, the real source remains `System::nanoTime`.

Save the file **`MonotonicTimingDemo.java`** with the following content:

~~~java
import java.util.function.LongConsumer;
import java.util.function.LongSupplier;

public final class MonotonicTimingDemo {
    @FunctionalInterface
    interface CheckedSupplier<T> {
        T get() throws Exception;
    }

    static <T> T timed(
            CheckedSupplier<T> task,
            LongSupplier ticker,
            LongConsumer recorder) throws Exception {
        long start = ticker.getAsLong();
        try {
            return task.get();
        } finally {
            long elapsedNanos = ticker.getAsLong() - start;
            recorder.accept(elapsedNanos);
        }
    }

    static LongSupplier scripted(long first, long second) {
        return new LongSupplier() {
            private int calls;

            @Override
            public long getAsLong() {
                return switch (calls++) {
                    case 0 -> first;
                    case 1 -> second;
                    default -> throw new IllegalStateException("no more ticks");
                };
            }
        };
    }

    public static void main(String[] args) throws Exception {
        long[] recorded = new long[2];
        String value = timed(
                () -> "OK",
                scripted(1_000L, 1_250L),
                nanos -> recorded[0] = nanos);
        System.out.println("value=" + value);
        System.out.println("successNanos=" + recorded[0]);

        try {
            timed(() -> {
                throw new IllegalStateException("boom");
            }, scripted(500L, 950L), nanos -> recorded[1] = nanos);
        } catch (IllegalStateException e) {
            System.out.println("caught=" + e.getMessage());
        }
        System.out.println("failureNanos=" + recorded[1]);

        long[] liveNanos = new long[1];
        int answer = timed(
                () -> 40 + 2,
                System::nanoTime,
                nanos -> liveNanos[0] = nanos);
        System.out.println("answer=" + answer);
        if (liveNanos[0] < 0) {
            throw new AssertionError("Unexpected negative real duration");
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 MonotonicTimingDemo.java
java MonotonicTimingDemo
~~~

**Verified stdout when compiling and running the example:**

~~~text
value=OK
successNanos=250
caught=boom
failureNanos=450
answer=42
~~~

Why this output is **deterministic**:

- The fake ticker returns `1_000` and `1_250`, so the subtraction is exactly `250 ns`; the task returns `"OK"`.
- On the throwing path, the fake ticker returns `500` and `950`, so `finally` **still records** `450 ns`, and then the `"boom"` exception is caught in `main`.
- The final branch uses the real `System::nanoTime` but **does not print the fluctuating duration**. It only prints `answer=42` and ensures the normal real duration is non-negative.
- `long[]` in the demo is a simple holder because it runs on a single thread. For multi-threaded collectors, use a thread-safe metric recording mechanism and avoid sharing raw unsynchronized arrays.

The `LongSupplier` object allows **deterministic testing of timing behavior** without replacing `System.nanoTime()` with a wall clock. `LongConsumer` allows testing metric recording on both execution paths.

The example uses `switch` expressions (available prior to Java 17), `@FunctionalInterface`, generics, and built-in Java 17 APIs, requiring no Maven or external libraries.

## 7. Java 17 Example: Checking Timeouts When `long` Crosses the Boundary

File **`TimeoutDemo.java`**:

~~~java
public final class TimeoutDemo {
    static boolean expired(
            long startNanos, long timeoutNanos, long nowNanos) {
        if (timeoutNanos < 0) {
            throw new IllegalArgumentException("timeout < 0");
        }
        return nowNanos - startNanos >= timeoutNanos;
    }

    public static void main(String[] args) {
        long start = Long.MAX_VALUE - 3;
        long end = Long.MIN_VALUE + 6;

        System.out.println("elapsed=" + (end - start));
        System.out.println("expired8=" + expired(start, 8, end));
        System.out.println("expired15=" + expired(start, 15, end));
    }
}
~~~

Commands:

~~~bash
javac --release 17 TimeoutDemo.java
java TimeoutDemo
~~~

**Verified stdout:**

~~~text
elapsed=10
expired8=true
expired15=false
~~~

This test uses **simulated timestamps on the `long` type**, does not use `System.nanoTime`, and is not evidence of a real clock rolling over. It confirms that comparing **difference first, timeout second** works correctly in a boundary-overflow example. Note that real-world cases with elapsed time exceeding ~292 years are **not** within the API's guaranteed range.

## 8. Converting Units Properly

Every subtraction of `System.nanoTime` yields **nanoseconds**. Never record this number under a `ms` or `seconds` label without converting it.

~~~java
long elapsedNanos = 2_345_678L;

double elapsedMillis = elapsedNanos / 1_000_000.0;
long wholeMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

System.out.println(elapsedMillis);
System.out.println(wholeMillis);
~~~

If placed inside `main`, stdout:

~~~text
2.345678
2
~~~

Distinctions:

- Dividing by `1_000_000.0` gives **floating-point milliseconds**.
- `TimeUnit.NANOSECONDS.toMillis` returns a `long`, **truncating the fractional part** during unit conversion. A measurement of `999_999 ns` becomes `0 ms`, which does not mean the task took 0 ns.
- `Duration.ofNanos(elapsedNanos)` represents a time length as a `Duration` object, suitable for application APIs; `Duration` is not a clock-reading source.
- When recording into a histogram, keep **`long` nanoseconds** until the conversion layer or the exact unit required by the metric SDK, avoiding back-and-forth conversions that lose resolution.
- If a user supplies a very large `Duration`, `Duration.toNanos()` **can throw `ArithmeticException`** if it does not fit in a `long`. Check the range before turning it into a timeout.

For example, annotations or fields should be named explicitly: `elapsed_nanos`, `duration_ms`, `timeout_nanos`. A numeric value without a **unit** is a metric easily misread.

## 9. Bytecode Instrumentation: How to Inject Probes into Methods

Java agents typically transform class files via `ClassFileTransformer`, ASM, Byte Buddy, or the Java Class-File API (standardized in JDK 24). Regardless of the tool, the generated logic must be equivalent to:

~~~text
Method entry:
    startNanos = System.nanoTime()

Original method body:
    ... original JVM instructions ...

Normal return:
    elapsed = System.nanoTime() - startNanos
    record(elapsed)
    return originalResult

Exceptional exit:
    elapsed = System.nanoTime() - startNanos
    record(elapsed)
    rethrow originalThrowable
~~~

This is **control-flow pseudocode**, not verbatim runnable ASM/JVM bytecode syntax. When performing actual bytecode transformation, you must:

1. **Insert at a valid method point** and allocate a `long` local slot (occupying two JVM slots) to store the start time.
2. **Ensure every return and exception exit path has an end point**. Placing a callback only before the first `RETURN` opcode will miss `IRETURN`, `ARETURN`, other returns, and exceptions.
3. Preserve the **original return value**: when inserting code before a return, preserve the operand stack and do not alter the return type.
4. Construct the **exception handler/finally** carefully so measuring the throw path does not alter the original exception; handle nested handlers and existing code.
5. Update **stack map frames, max stack/max locals, labels, and the exception table** so the new class file passes the verifier.
6. Avoid mis-instrumenting constructors: certain operations before calling `super(...)`/`this(...)` have restrictions regarding `uninitializedThis`. Do not apply the exact same constructor insertion logic as regular methods without accounting for verifier rules.
7. Only instrument methods **that have code**; `abstract` and `native` methods have no `Code` attribute for inserting standard Java opcodes.
8. If using a transformer invoked during retransformation, ensure the transformation does not inject timers **repeatedly in multiple layers** across invocations, which would cause double-counting.

An example transformation that looks right but is wrong:

~~~text
onMethodEnter: start = nanoTime()
onMethodExit(RETURN): record(nanoTime() - start)
~~~

The combination above **does not cover the path where the method throws an exception** if the hook only runs for normal returns. Some libraries allow hooks to receive **exit opcodes**; even when intercepting `ATHROW`, an exception can propagate out of another call without an `ATHROW` opcode in the instrumented method itself. To cover all exceptional exits, an appropriate handler/finally must be designed rather than relying solely on finding `ATHROW` opcodes.

## 10. Synchronous vs. Asynchronous: Do Not Stop the Timer Too Early

If a method **returns a `CompletableFuture` immediately**, the method's execution time usually measures only the time to **create/schedule** the future, not the time for the asynchronous work to complete.

**Wrong target if trying to measure end-to-end latency:**

~~~java
long start = System.nanoTime();
try {
    return service.callAsync();
} finally {
    record(System.nanoTime() - start);
}
~~~

This is a fragment: `finally` runs as soon as the future is returned, even though the future has not completed yet. If the goal is **the time for `callAsync()` to return the future**, this approach is right. If the goal is **from invocation until the future completes**, stop the timer in the completion callback.

**Semantically correct sketch for measuring asynchronous duration:**

~~~java
long start = System.nanoTime();
try {
    CompletableFuture<Result> future = service.callAsync();
    return future.whenComplete((value, error) -> {
        long elapsed = System.nanoTime() - start;
        record(elapsed);
    });
} catch (RuntimeException immediateFailure) {
    record(System.nanoTime() - start);
    throw immediateFailure;
}
~~~

This is a **fragment** inside a method that already has the corresponding `service`, `Result`, and `record`, with `java.util.concurrent.CompletableFuture` imported. `whenComplete` fires when the source future completes; the clock is read inside the callback. The callback may run with a small delay depending on the scheduler/executor, so the measurement reflects when the callback is actually invoked. If `record` throws an error, the dependent future could receive a different failure result: **the recorder must be safe**.

In a pipeline with multiple `CompletionStage`s, determine precisely **which stage represents business completion**. If an already-completed future is returned, the callback may execute immediately, which is normal behavior. If you want to include queue time, capture start **before enqueueing**; if measuring execution time only, capture start **inside the worker when the task begins executing**.

The `System.nanoTime()` source shares the same origin within **a single JVM**, so sampling on two different threads in that JVM can still be meaningful if control flow is properly synchronized/has a happens-before relationship. **Do not pass a raw start tick from JVM A over a message for JVM B to take an end tick and subtract**.

## 11. Logging, Metrics, and Tracing Should Use Two Different Kinds of Time

A real span or event may need both a **point-in-time timestamp** and a **duration**:

~~~text
timestamp_utc = Instant.now()          // calendar timestamp for attaching to logs
start_tick    = System.nanoTime()      // relative tick
... operation ...
duration_ns   = System.nanoTime() - start_tick
~~~

Note that the first two samples are not read in a single atomic operation; the timestamp used for log correlation can differ slightly from the duration by the call overhead. Do not attempt to compute a completion timestamp by directly converting `start_tick` into an epoch.

In production, record a **histogram/timer** for processing time rather than logging every single request:

| Information | Good representation |
|---|---|
| Time per operation | Numeric duration with unit |
| Latency distribution | Histogram with consistent buckets; observe p50/p95/p99 from appropriate data |
| Execution count | Counter |
| Success/failure | Low-cardinality status/tag |
| When an event occurred | Separate wall-clock timestamp |
| Correlating processing steps | Trace/span ID and context, not raw `nanoTime` |

**Avoid high cardinality**: do not use user IDs, URLs with UUIDs, transaction IDs, or unique durations as histogram labels. Doing so can cause the number of time series to explode.

**Avoid invalid averaging**: the p99 latency of a flow cannot be obtained by simply averaging the p99 values of each instance. Histograms require proper aggregation methods.

**Do not use a latency measurement as a CPU benchmark**: duration can include I/O, lock contention, GC, and time when the thread is not running on the CPU. If you want to measure CPU specifically, consider `ThreadMXBean`, a profiler, or JFR where supported.

## 12. Understanding Clock Limitations and Instrumentation Overhead

`System.nanoTime()` is the standard choice for elapsed time, but it is not a perfect microscopic measuring tool.

- **Clock call overhead**: two `nanoTime()` calls and one metric recording have a cost; for extremely short methods, the overhead can account for a significant proportion.
- **Instrumentation changes the very thing being measured** (*observer effect*). It can affect JIT inlining, register pressure, class loading, and the performance profile.
- **Resolution differs from precision**: if two reads return the same value, a duration of 0 is a valid result given the observed resolution, and does not mean the work took "zero time".
- **Warm-up/JIT/GC**: first-call results and post-warm-up results can differ drastically; comparisons must define identical conditions.
- **Scheduling/virtual threads**: elapsed sources continue to reflect time passing while a task is blocked/waiting; this is appropriate for service latency but does not isolate CPU.
- **Clock jitter and virtualized environments** can affect measurements; avoid claiming a fixed resolution across all OSes/JVMs.
- **Recording and export**: if the exporter blocks threads, most of the overhead may lie in the recorder rather than in reading the clock; measure/optimize the recorder separately.

For **microbenchmarks** comparing short code snippets, use **JMH** because manual benchmarks are easily skewed by optimizations, dead-code elimination, JIT effects, and improper iteration control. For **real application probes**, `nanoTime()` + accurate measurement scope + lightweight metrics are usually a sound foundation.

**Do not** take millions of `nanoTime` samples yourself and deduce "clock accuracy" from a single number; that figure is also affected by scheduling and timing API overhead.

## 13. Timeouts, Deadlines, and Waiting

A deadline can be represented by `Instant` when a system-wide calendar schedule is needed, but **the timeout of a running operation** should be compared against a relative interval:

~~~java
long started = System.nanoTime();
long budgetNanos = java.util.concurrent.TimeUnit.SECONDS.toNanos(2);

while (!finished()) {
    if (System.nanoTime() - started >= budgetNanos) {
        throw new java.util.concurrent.TimeoutException("budget expired");
    }
    doOneStep();
}
~~~

This is a fragment assuming application-provided `finished()`/`doOneStep()` methods; it illustrates timeout checking, not an optimal polling loop. In real systems, use timeout-aware blocking primitives such as `Lock.tryLock`, `Condition.awaitNanos`, `Future.get(timeout, unit)`, or `ScheduledExecutorService`, rather than busy-spinning continuously just to read the clock.

Things to remember:

1. **Do not use `Thread.sleep(2000)` as proof of exactly 2,000 ms elapsed**. Sleep typically has scheduling delays and does not guarantee nanosecond-exact wakeup.
2. When computing `remaining = budgetNanos - (now - start)`, you may need to handle `remaining <= 0` before passing it to an API that requires a positive duration.
3. If the budget is already exhausted before starting new I/O, the timeout should be **propagated** or checked before that I/O step to avoid starting an operation that could block indefinitely.
4. When a request traverses multiple services/processes, propagate the **deadline or remaining budget via an appropriate protocol**; do not send raw `System.nanoTime` from one process to another.
5. A timeout measuring elapsed time does not mean cancellation has succeeded; after expiration, cancellation/cleanup mechanisms are still needed depending on the API.

## 14. Common Mistakes When Designing Probes

| Symptom | Possible cause | Fix |
|---|---|---|
| Anomalous negative duration when using `currentTimeMillis` | Wall clock was adjusted | Use `System.nanoTime()` for elapsed time |
| Negative duration when taking `nanoTime()` across two JVMs | Origins are not shared | Only subtract samples from the same JVM; use a tracing protocol across services |
| Missing measurements when a method throws | Duration recording inserted only on the return path | Use `finally`/exception handlers for all exits |
| Method returns `CompletableFuture` with tiny duration | Timer stopped when returning the future | If end-to-end is desired, stop in the completion callback |
| Metric labeled `ms` but value comes from `nanoTime` | Forgot to convert from ns | Convert units properly or record `elapsed_nanos` |
| Too many metric series | Dynamic IDs/URLs used as labels | Design low-cardinality labels |
| Adding a timer degrades performance | Blocking log/metric writes, allocations, or instrumenting too many methods | Filter targets, sample appropriately, use a lightweight recorder |
| Wrong timeout behavior near `long` overflow | Comparing `now >= started + timeout` | Compare `now - started >= timeout` |
| Seeing `0 ns` for a small operation | Clock source lacks 1 ns resolution | Do not assume the task is free; use a distribution of many samples |
| Re-running transformer nests timers multiple times | Instrumentation does not check idempotence | Maintain a transform pipeline that does not duplicate probes |
| Low CPU time but high latency | Task is waiting on I/O/locks/scheduling | Distinguish elapsed duration from CPU time |
| Metrics error masks original exception | Recorder throws inside `finally` | Build a non-throwing recorder or handle errors separately |

**Implementation checklist:** define business boundaries → use one nanoTime source for the start/end pair → record deltas rather than absolute ticks → cover success/error → standardize units → check async boundaries → ensure low-overhead and thread-safety → test with a fake ticker → observe latency distributions in a real environment.

## 15. Self-Check

1. **Is `nanoTime()` the number of nanoseconds since the Unix epoch?** No; the origin is fixed but arbitrary for a single JVM.
2. **Can you subtract `nanoTime()` of JVM B from `nanoTime()` of JVM A?** No; the two origins can differ.
3. **Why measure duration with `System.nanoTime()` instead of `currentTimeMillis()`?** Because it does not depend on a calendar clock that can be adjusted, and is suited for elapsed time.
4. **Can two `nanoTime()` calls return the same number?** Yes; nanosecond precision does not guarantee nanosecond resolution.
5. **When checking a timeout, should you use `now >= start + budget` or `now - start >= budget`?** Use subtraction first, within the `long` elapsed limit.
6. **Is a timer around a method that only measures normal return paths enough?** No; exception paths must be covered.
7. **What instrumentation bug can `finally` cause?** A recorder in `finally` can mask the original error if it throws an exception.
8. **A method returns a `CompletableFuture` immediately; what does a timer in `finally` measure?** The time for the method to return the future, not necessarily when the future completes.
9. **What is `TimeUnit.NANOSECONDS.toMillis(999_999)`?** `0` because `long` conversion truncates the fractional part.
10. **A metric asks for "CPU runtime"; is `nanoTime` enough?** No; it measures elapsed time, including wait time.
11. **Why should unit tests inject `LongSupplier`?** To produce deterministic time samples and test success/error branches and subtraction without depending on scheduling.
12. **When instrumenting bytecode, is inserting only before `RETURN` instructions enough?** No; multiple return opcodes and exceptional exits must be handled, while keeping stack map frames valid.

### References

- [Oracle Java SE 21 — `System.nanoTime()` and `currentTimeMillis()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): arbitrary origin, paired measurements, timeouts, and overflow limits.
- [Oracle Java SE 21 — `TimeUnit`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html): converting time duration units.
- [Oracle Java SE 21 — `Duration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html): representing durations and handling overflow when converting to nanoseconds.
- [Oracle Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `whenComplete` callback for asynchronous completion boundaries.
- [Oracle Java SE 21 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread CPU time, distinct from latency.
- [OpenJDK JMH](https://github.com/openjdk/jmh): Java microbenchmarking tool for fine-grained code comparisons.

**Takeaway:** when you need a *duration*, read `System.nanoTime()` **twice in the same JVM** and use **`end - start`**. Choose the right business boundaries, measure both success and error paths completely, and clearly distinguish **elapsed duration**, **wall-clock timestamp**, and **CPU time**.