# Measuring Elapsed Time with `System.nanoTime()` in Java 17

**Topic:** Java 17  
**Chapter:** Time Sources  
**Lesson:** Measuring Elapsed Time with System.nanoTime

When you need to know how long an operation takes, you must choose the right time source. Java has several time-related APIs, but they serve different purposes:

- `System.currentTimeMillis()` returns the current time according to the system clock, in milliseconds since the Unix epoch.
- `Instant.now()` represents a point on the global timeline, suitable for recording timestamps.
- **`System.nanoTime()`** provides a monotonic time source (*monotonic time source*) in nanoseconds, suitable for measuring **elapsed time**.

For measuring the execution duration of a piece of code, the standard pattern is to take two `nanoTime()` readings and subtract them:

```java
long start = System.nanoTime();

// Block of work to monitor
doWork();

long elapsed = System.nanoTime() - start;
```

The result `elapsed` is the elapsed time in nanoseconds. Do not interpret a value read directly from `nanoTime()` as a calendar date-time or timestamp. The origin of this clock is arbitrary, and only differences between readings within the same JVM are meaningful.

## 1. Why Do We Need a Monotonic Clock?

A clock used to display dates and times must reflect calendar time. The system clock can be adjusted by users, time-synchronization services, the operating system, or virtualization environments.

For example, a program reads the system time before and after an operation:

```java
long start = System.currentTimeMillis();

doWork();

long elapsedMillis = System.currentTimeMillis() - start;
```

If the system clock is adjusted backward or forward while the operation is running, the difference may not accurately reflect actual elapsed time. The result can even be negative if the clock jumps far enough backward.

`System.nanoTime()` is designed for measuring duration. Within the same JVM, the difference between two readings is the appropriate mechanism because this source is not affected by calendar clock adjustments like `currentTimeMillis()` is.

### 1.1. Two Kinds of Time, Two Purposes

| API | Meaning | Used for |
|---|---|---|
| `System.currentTimeMillis()` | System time in milliseconds from the epoch | Simple timestamps, logging points in time |
| `Instant.now()` | Current point on the timeline | Date-time, timestamps, data exchange |
| `System.nanoTime()` | Monotonic time counter, arbitrary origin | Measuring elapsed time, timeouts, deadlines |
| `LocalDateTime.now()` | Local date and time without offset/zone | Local calendar display, calendar business logic |
| `Duration` | Time interval in seconds and nanoseconds | Representing a duration after measuring or calculating |

For example, if you need to record "the user sent a request at 10:15:30," use `Instant.now()` or an appropriate date-time API. If you need to measure "handling the request took 18 ms," use `System.nanoTime()`.

### 1.2. Monotonic Does Not Mean Calendar Time

A monotonic clock provides a forward-moving measurement source suitable for taking differences. It does not tell you:

- What date it is right now.
- Which Unix epoch time a reading corresponds to.
- Whether the absolute value can be converted into an `Instant`.
- Whether two different machines are at the same point in time.

You can visualize this as:

```text
Calendar clock (Instant/currentTimeMillis)
  2026-11-15 10:00:00
          |
          +-- can be adjusted by the system

Monotonic clock (nanoTime)
  arbitrary origin ->  ... ->  ... ->  ...
       |                            |
      start                        end
       +--------- end - start ------+
                   elapsed
```

Use a calendar clock to know **when**; use a monotonic clock to know **how long**.

## 2. Basic Usage: Taking the Difference of Two Readings

`System.nanoTime()` returns a `long` value in nanoseconds.

One nanosecond is:

\[
1\text{ ns} = 10^{-9}\text{ seconds}
\]

Example:

```java
public class ElapsedTimeExample {
    public static void main(String[] args) {
        long start = System.nanoTime();

        calculate();

        long end = System.nanoTime();
        long elapsedNanos = end - start;

        System.out.println("Elapsed: " + elapsedNanos + " ns");
    }

    private static void calculate() {
        long sum = 0;

        for (int i = 0; i < 1_000_000; i++) {
            sum += i;
        }

        // Keep the result used to illustrate actual work.
        System.out.println("sum = " + sum);
    }
}
```

Key formula:

\[
\text{elapsed} = \text{end} - \text{start}
\]

You do not need to know what the absolute values of `start` or `end` are. You only need two readings from the same monotonic source in the same JVM and to subtract them in the right order.

### 2.1. Why Capture the Start Time Right Before the Work?

```java
long start = System.nanoTime();
doWork();
long elapsed = System.nanoTime() - start;
```

Measurement begins immediately before `doWork()` and ends immediately after `doWork()` returns. Operations outside those two points are not counted.

If you place input preparation, connection opening, or logging inside the measured region, that time is included as well. Therefore, decide clearly **which part you want to measure** before placing the two sampling points.

### 2.2. Use Variable Names That Indicate Units

Avoid generic names like `time` or `result` when the value is a numeric time measurement. Prefer:

```java
long startNanos = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - startNanos;
```

The name `elapsedNanos` tells readers that the value is a duration and the unit in use is nanoseconds.

## 3. Converting Nanoseconds to Readable Units

`nanoTime()` returns results in nanoseconds, though you do not always need to display them in that unit.

Conversions:

| Unit | Nanoseconds |
|---|---:|
| 1 microsecond (µs) | 1,000 ns |
| 1 millisecond (ms) | 1,000,000 ns |
| 1 second (s) | 1,000,000,000 ns |
| 1 minute | 60,000,000,000 ns |

You can divide directly:

```java
long elapsedNanos = 25_000_000L;

double elapsedMillis = elapsedNanos / 1_000_000.0;
double elapsedSeconds = elapsedNanos / 1_000_000_000.0;

System.out.println(elapsedMillis + " ms"); // 25.0 ms
System.out.println(elapsedSeconds + " s"); // 0.025 s
```

Use a floating-point divisor if you want to keep fractional digits. Writing `elapsedNanos / 1_000_000` with two integer operands causes Java to perform integer division and drop the remainder.

### 3.1. Using `TimeUnit`

`java.util.concurrent.TimeUnit` helps convert units:

```java
import java.util.concurrent.TimeUnit;

long elapsedNanos = 25_123_456L;

long millis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
long micros = TimeUnit.NANOSECONDS.toMicros(elapsedNanos);

System.out.println(millis + " ms"); // 25 ms
System.out.println(micros + " µs"); // 25123 µs
```

Methods converting to larger units **truncate fractions** using integer division. Hence `25_123_456 ns` becomes `25 ms`, not `25.123456 ms`.

If you need fractional precision, convert to `double` with the appropriate factor or use `Duration` to retain seconds and nanoseconds.

### 3.2. Using `Duration` to Represent Elapsed Time

`java.time.Duration` represents a time interval with nanosecond resolution:

```java
import java.time.Duration;

long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;

Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println(elapsed);
System.out.println(elapsed.toMillis() + " ms");
System.out.println(elapsed.toNanos() + " ns");
```

`Duration` is useful when passing durations between application layers or formatting results. It does not replace choosing the right clock: still measure with `nanoTime()`, then convert the difference into a `Duration`.

### 3.3. Watch Out for Precision Loss During Conversions

`Duration.toMillis()` returns whole milliseconds; any portion smaller than one millisecond is omitted from that result.

Example:

```java
Duration duration = Duration.ofNanos(1_500_000);

System.out.println(duration.toNanos()); // 1500000
System.out.println(duration.toMillis()); // 1
System.out.println(duration);            // PT0.0015S
```

If diagnostic requirements need exact measured nanoseconds preserved, store `elapsedNanos` or keep `Duration` instead of keeping only `toMillis()`.

## 4. Accuracy and Resolution Are Not the Same

The name `nanoTime` contains "nano," but that **does not guarantee** every read is separated by 1 nanosecond or that the system can accurately measure individual nanoseconds.

Distinguish between:

- **Unit:** The returned value is expressed in nanoseconds.
- **Resolution:** The smallest observable increment of the clock source on the current system.
- **Accuracy:** How closely the measurement reflects actual physical time.
- **Clock read overhead:** The time and cost of making an API call.

The `System.nanoTime()` Javadoc states that the returned value has nanosecond units and provides precision at least as good as `currentTimeMillis()`; actual resolution depends on the system. Thus, a very short operation can yield a difference of 0 or a value rounded to hardware/OS resolution.

Example:

```java
long start = System.nanoTime();
int result = 1 + 1;
long elapsed = System.nanoTime() - start;

System.out.println(elapsed);
```

Do not conclude that addition takes literally 0 ns if the printed output is 0. It only indicates that the measured interval was smaller than the observable granularity during that measurement, or was affected by resolution and measurement overhead.

### 4.1. Measuring Very Short Operations by Repeating Many Times

For very fast operations, you can measure the total time of many iterations and compute a rough average:

```java
int iterations = 1_000_000;

long start = System.nanoTime();

for (int i = 0; i < iterations; i++) {
    performOperation();
}

long elapsed = System.nanoTime() - start;

double averageNanos = (double) elapsed / iterations;

System.out.println("Average: " + averageNanos + " ns/op");
```

This reduces the effect of measuring a single ultra-short operation, yet it is still **not a reliable benchmark** without warmup, JIT control, dead-code elimination prevention, GC control, and environmental control. Proper benchmarking is covered in section 10.

## 5. Properties and Limits of the Return Value

`System.nanoTime()` returns a `long`. This value:

- Can be negative.
- Has an arbitrary origin.
- Is not nanoseconds since the epoch.
- Is only meaningful when taking differences between readings in the same JVM.
- Can overflow when the counter crosses `long` bounds, so subtraction must follow the proper pattern.

### 5.1. Do Not Directly Compare Two Absolute Values

Do not write:

```java
long start = System.nanoTime();

// ...

long end = System.nanoTime();

if (end > start) {
    // Not the recommended way to check elapsed time.
}
```

Compute the difference instead:

```java
long elapsed = end - start;

if (elapsed >= 0) {
    // Measurement interval in normal order.
}
```

However, in real code you do not need to check `elapsed >= 0` just to validate the clock. Use the difference formula and compare against the required duration threshold.

### 5.2. Why Does Subtraction Still Work When the Counter Overflows?

`long` has a finite range. If the monotonic counter wraps from the largest positive value to the smallest negative value, two's-complement subtraction `end - start` still produces the correct difference as long as the measured interval is less than half the cycle of `long`.

In nanoseconds, this limit is approximately 292 years. For timeouts and durations in typical applications, the measured span is always well below that limit.

Thus, the recommended pattern is:

```java
long start = System.nanoTime();

// ...

long elapsed = System.nanoTime() - start;
```

You do not need to handle wrap-around manually using absolute comparisons or checking for negative values.

### 5.3. Do Not Store nanoTime Values as Long-Term Timestamps

Do not store `System.nanoTime()` in a database and treat it as when an event occurred. The absolute value has no guaranteed epoch and no meaning across different processes or machines.

If you need to store a timestamp, use `Instant`:

```java
import java.time.Instant;

Instant occurredAt = Instant.now();
```

If you need to store a duration, store `Duration` or a number of nanoseconds/milliseconds per the agreed data contract:

```java
long elapsedNanos = 12_345_678L;
Duration elapsed = Duration.ofNanos(elapsedNanos);
```

## 6. Measuring Time with try/finally

If the measured code can throw an exception, use `finally` to ensure duration is recorded whether execution succeeds or fails.

```java
long start = System.nanoTime();

try {
    processRequest();
} finally {
    long elapsed = System.nanoTime() - start;
    System.out.println("processRequest took " + elapsed + " ns");
}
```

`finally` runs when the `try` block completes normally or via exception, except when the JVM/process terminates abnormally. This is useful when logging execution time for diagnostics.

In real applications, extract measurement logic into a utility to avoid repetition:

```java
import java.util.concurrent.TimeUnit;

static long measureNanos(Runnable task) {
    long start = System.nanoTime();

    try {
        task.run();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println(
                "Elapsed: " + TimeUnit.NANOSECONDS.toMicros(elapsed) + " µs"
        );
    }

    return System.nanoTime() - start;
}
```

The snippet above only illustrates the idea; because it reads the clock once in `finally` and again at `return`, the returned value can be longer than the printed duration. In code needing a single consistent result, store the difference once:

```java
static long measureNanos(Runnable task) {
    long start = System.nanoTime();
    long elapsed;

    try {
        task.run();
    } finally {
        elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }

    return elapsed;
}
```

If `task.run()` throws an exception, the method still executes `finally` and propagates the exception; the return value is unused in that case. If you need to return both success/failure status and duration, design a dedicated result type instead of swallowing exceptions.

## 7. Using nanoTime to Implement Timeouts

An application often needs to time-bound an operation: waiting for a resource, retrying a request, or waiting up to a maximum duration for a task to finish.

You can compare elapsed time against the timeout:

```java
long timeoutNanos = TimeUnit.SECONDS.toNanos(2);
long start = System.nanoTime();

while (!isReady()) {
    if (System.nanoTime() - start >= timeoutNanos) {
        throw new IllegalStateException("Timed out");
    }
}
```

This uses a monotonic difference and does not depend on calendar clock adjustments.

### 7.1. Writing a Timeout Check Helper

```java
static boolean hasTimedOut(long startNanos, long timeoutNanos) {
    return System.nanoTime() - startNanos >= timeoutNanos;
}
```

Usage:

```java
long start = System.nanoTime();
long timeout = TimeUnit.MILLISECONDS.toNanos(500);

while (!isReady()) {
    if (hasTimedOut(start, timeout)) {
        break;
    }

    Thread.onSpinWait();
}
```

`Thread.onSpinWait()` is a hint to the JVM/CPU that the loop is busy-waiting (*spin-wait*); it does not turn a loop into an efficient waiting mechanism in every case. Whenever possible, use `wait`, `Condition.await`, `BlockingQueue.poll(timeout, unit)`, or waiting APIs with built-in timeouts to avoid continuous CPU consumption.

### 7.2. Why Compare Differences Instead of Adding a Deadline?

An intuitive way people write is:

```java
long deadline = System.nanoTime() + timeoutNanos;

if (System.nanoTime() >= deadline) {
    // timeout
}
```

This approach can run into issues when addition overflows `long` and when comparing absolute values across the wrap-around point. The difference pattern:

```java
if (System.nanoTime() - startNanos >= timeoutNanos) {
    // timeout
}
```

is the idiomatic pattern matching `nanoTime()` rules, provided the measured duration is less than half the counter's cycle (around 292 years).

### 7.3. Converting Timeouts from Duration

```java
import java.time.Duration;

Duration timeout = Duration.ofSeconds(2);
long timeoutNanos = timeout.toNanos();
long start = System.nanoTime();

while (!isReady()) {
    if (System.nanoTime() - start >= timeoutNanos) {
        throw new IllegalStateException("Timed out");
    }
}
```

`Duration.toNanos()` can throw `ArithmeticException` if the duration is too large to fit in a `long` number of nanoseconds. For practical application timeouts, this limit is usually not hit; if accepting user-configured durations, validate the range.

### 7.4. Avoid Busy Loops When Proper Waiting Mechanisms Exist

The loop snippets above only illustrate timeout calculation. When waiting for a condition changed by another thread, using a synchronization primitive or timeout-aware API is much better:

```java
boolean completed = latch.await(2, TimeUnit.SECONDS);

if (!completed) {
    throw new IllegalStateException("Timed out");
}
```

`CountDownLatch.await(timeout, unit)` already accepts a wait duration and manages waiting internally. There is no need to spin calling `nanoTime()` yourself if a synchronization API already supports timeouts for your use case.

## 8. Measuring Execution Time of Multiple Tasks

When dealing with multiple tasks, clarify whether you want to measure:

- The duration of each individual task.
- Total time from start until all tasks complete (*wall-clock elapsed time*).
- Total CPU time consumed by the threads.

`System.nanoTime()` measures elapsed time on a monotonic clock, not CPU time. If multiple threads run in parallel, total elapsed time is typically less than the sum of individual execution times across all threads.

### 8.1. Measuring an Entire Batch

```java
long start = System.nanoTime();

runAllTasksAndWaitForCompletion();

long elapsed = System.nanoTime() - start;

System.out.println("Batch elapsed: " + elapsed + " ns");
```

Place the end marker **after** all tasks have completed. If you stop measuring right after submitting tasks to an executor, the result is submission time, not completion time.

### 8.2. Measuring Individual Tasks

```java
Runnable timedTask = () -> {
    long start = System.nanoTime();

    try {
        doWork();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println(
                Thread.currentThread().getName()
                        + " took " + elapsed + " ns"
        );
    }
};
```

Each execution of `timedTask` takes its own start mark, allowing per-worker elapsed times to be recorded. In systems with many tasks, use metrics or structured logging instead of printing heavily to the console concurrently.

### 8.3. Wall-Clock Elapsed Differs from Total CPU Time

For example, two threads each running for about 1 second concurrently:

```text
Batch elapsed time (wall-clock): ~1 second
Sum of both task durations:      ~2 seconds
```

`nanoTime()` around the entire batch measures the batch's elapsed time. It does not sum each thread's CPU time. If you need CPU time, use thread management APIs such as `ThreadMXBean` where supported and permitted by the environment.

## 9. Distinguishing nanoTime from sleep and Scheduling

`Thread.sleep()` requests that the thread pause for a minimum duration per the API contract; the thread may wake up later due to the scheduler, system load, or timer resolution.

```java
long start = System.nanoTime();

Thread.sleep(100);

long elapsed = System.nanoTime() - start;

System.out.println(elapsed / 1_000_000.0 + " ms");
```

The result is usually greater than or roughly 100 ms; do not expect it to always be 100,000,000 ns. `nanoTime()` measures actual elapsed time, while `sleep` only guarantees pausing for at least the requested duration.

Similarly, a task scheduled via `ScheduledExecutorService` may run slightly later than its target time. Use `nanoTime()` to observe actual latency, and do not assume the scheduler executes to exact nanosecond precision.

## 10. Benchmarking: nanoTime Is Useful but Does Not Replace JMH

A simple measurement snippet:

```java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    calculate();
}

long elapsed = System.nanoTime() - start;

System.out.println(elapsed + " ns");
```

is useful for preliminary diagnostics, but is not a reliable microbenchmark. The JVM optimizes code at runtime, for example:

- **JIT compilation:** methods may be compiled and optimized after running a number of times.
- **Warmup:** early runs can incur class-loading, compilation, and initialization costs.
- **Dead-code elimination:** unused results may cause the compiler to eliminate part of the work.
- **Constant folding:** expressions made solely of constants may be precomputed.
- **Garbage collection:** GC can affect the timing of a given run.
- **CPU frequency scaling and scheduler:** system load and CPU frequency alter results.
- **Forking and JVM state:** measurements in the same JVM can influence one another.

### 10.1. Using JMH for Java Benchmarks

JMH (Java Microbenchmark Harness) is a dedicated tool for Java benchmarking. It manages warmup, measurement iterations, forking, result consumption, and statistical reporting.

Minimal benchmark example with JMH:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Scope;

@State(Scope.Thread)
public class CalculationBenchmark {

    @Benchmark
    public long sum() {
        long result = 0;

        for (int i = 0; i < 1_000; i++) {
            result += i;
        }

        return result;
    }
}
```

JMH manages measurement loops and consumes benchmark results through its mechanisms to prevent optimizations from eliminating work. Do not write your own `nanoTime()` loop over operations and treat the output as an accurate benchmark.

### 10.2. When Should You Use nanoTime Directly?

| Situation | Appropriate approach |
|---|---|
| Logging request processing time | `System.nanoTime()` difference |
| Timing a block of code while debugging | `System.nanoTime()` |
| Timeouts in loops or synchronous APIs | `nanoTime()` or timeout-accepting APIs |
| Benchmarking two implementations | JMH |
| Recording when an event occurred | `Instant.now()` |
| Measuring thread CPU time | `ThreadMXBean` when appropriate |

## 11. Building a Reusable Timing Utility

If you need to time an action that returns a value, you can write a helper using `Supplier<T>` that returns both the value and the elapsed duration. The snippet below reads the clock only twice: once before and once after the action.

```java
import java.time.Duration;
import java.util.function.Supplier;

public final class Timer {

    private Timer() {
    }

    public record Measurement<T>(T value, Duration elapsed) {}

    public static <T> Measurement<T> measure(Supplier<T> action) {
        long start = System.nanoTime();

        T value = action.get();

        long elapsed = System.nanoTime() - start;
        return new Measurement<>(value, Duration.ofNanos(elapsed));
    }
}
```

If `action.get()` throws an exception, the exception propagates and no `Measurement` is produced. This is usually the right behavior if the caller handles errors along the normal flow.

If you need to record duration even when the action fails, you can measure inside `finally` without returning the duration from the helper:

```java
static <T> T measureAndLog(Supplier<T> action) {
    long start = System.nanoTime();

    try {
        return action.get();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }
}
```

Here `finally` only logs the duration; if the action throws an exception, the exception still propagates. Do not catch and swallow exceptions just to obtain a measurement.

For actions that return no result, use `Runnable`:

```java
static Duration measure(Runnable action) {
    long start = System.nanoTime();

    action.run();

    return Duration.ofNanos(System.nanoTime() - start);
}
```

These helpers fit small utilities or diagnostics. In larger applications, consider existing metrics/tracing libraries to avoid building a redundant measurement layer.

Usage:

```java
Timer.Measurement<String> measurement =
        Timer.measure(() -> loadData());

System.out.println(measurement.value());
System.out.println(measurement.elapsed().toMillis() + " ms");
```

## 12. Common Mistakes

### Mistake 1. Using `currentTimeMillis()` to measure elapsed time

The system clock can be adjusted. Use `System.nanoTime()` for durations.

### Mistake 2. Treating nanoTime values as timestamps

The origin is arbitrary. Never convert values directly into `Instant` or store them as calendar points in time.

### Mistake 3. Comparing absolute values instead of differences

Use `end - start`. Do not rely on `end > start` to check elapsed time.

### Mistake 4. Assuming nanoTime guarantees 1 ns resolution

The unit is nanoseconds, but actual resolution depends on the system. A very short measurement can return 0.

### Mistake 5. Integer division losing fractional parts

`elapsedNanos / 1_000_000` performs integer division if both operands are integer types. Use `1_000_000.0` if you need decimal fractions.

### Mistake 6. Measuring task submission time instead of task completion time

Place the end marker after tasks finish or after `Future.get()`/`awaitTermination()` completes, depending on program structure.

### Mistake 7. Running a custom single-shot benchmark and drawing conclusions

JIT, warmup, GC, and the scheduler can make results fluctuate. Use JMH for serious benchmarking.

### Mistake 8. Creating a deadline by addition and comparing absolutely

Use the difference pattern `System.nanoTime() - start >= timeout` to avoid comparison issues across wrap-around.

### Mistake 9. Using nanoTime to measure CPU time

`nanoTime` measures elapsed time. When multiple threads run concurrently, elapsed time is not the sum of their CPU times.

### Mistake 10. Converting units and accidentally truncating the remainder

`TimeUnit.NANOSECONDS.toMillis` returns whole milliseconds. If fractional precision is needed, keep nanoseconds or use `Duration`.

## 13. Complete Example: Measuring Processing Time and Formatting Duration

Save the following program as `NanoTimeDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class NanoTimeDemo {

    private static long doWork() {
        long result = 0;

        for (int i = 0; i < 5_000_000; i++) {
            result += i;
        }

        return result;
    }

    public static void main(String[] args) {
        long startNanos = System.nanoTime();

        long result = doWork();

        long elapsedNanos = System.nanoTime() - startNanos;

        Duration elapsed = Duration.ofNanos(elapsedNanos);

        System.out.println("result = " + result);
        System.out.println("elapsed ns = " + elapsedNanos);
        System.out.println(
                "elapsed ms = "
                        + TimeUnit.NANOSECONDS.toMillis(elapsedNanos)
        );
        System.out.println("duration = " + elapsed);
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 NanoTimeDemo.java
java NanoTimeDemo
```

Exact duration depends on the machine, JDK, system load, and JIT state; there is no fixed output number. What matters is:

- `startNanos` is captured immediately before the work.
- `elapsedNanos` is the difference between the two readings.
- `Duration.ofNanos` converts the duration into a meaningful representation.
- `TimeUnit` converts to whole milliseconds for display.
- The `result` value is used, avoiding examples where work produces a dead value.

## 14. Practice Exercises

### Exercise 1. Computing elapsed time

Given:

```java
long start = System.nanoTime();

// work

long elapsed = System.nanoTime() - start;
```

**Question:** What unit is `elapsed` in?

**Answer:** Nanoseconds, because `System.nanoTime()` returns values in nanoseconds.

### Exercise 2. Choosing the right API

A system needs to record when a user logged in and how long processing the login took.

**Answer:** Use `Instant.now()` to record the point in time; use a `System.nanoTime()` difference to measure the duration.

### Exercise 3. Why avoid adding a deadline?

A developer writes `long deadline = System.nanoTime() + timeout;` and checks `System.nanoTime() >= deadline`.

**Answer:** This can fail when the value overflows and crosses the wrap-around point. Use the difference `System.nanoTime() - start >= timeout`.

### Exercise 4. Unit conversion

If `elapsedNanos = 1_500_000`, what does `TimeUnit.NANOSECONDS.toMillis(elapsedNanos)` return?

**Answer:** `1` millisecond, because the conversion returns an integer value and truncates the 0.5 ms remainder.

### Exercise 5. Resolution

A very short snippet produces `elapsed == 0`. Can you conclude the code took zero time?

**Answer:** No. The clock source has finite resolution; the measured span can be smaller than the smallest observable increment.

### Exercise 6. Measuring parallel batches

A program launches 10 tasks and immediately takes a measurement right after submitting them. What does the result reflect?

**Answer:** Primarily the task submission time, not completion time. Wait for the tasks to finish before taking the end reading.

### Exercise 7. Benchmarking

A loop calls a method once and reads nanoTime to conclude that method A is faster than method B. Is that conclusion reliable?

**Answer:** No. Multiple iterations, warmup, and control over JVM factors are needed; use JMH for microbenchmarks.

### Exercise 8. Distinguishing elapsed and CPU time

Two threads run concurrently, each taking around 2 seconds. Will measuring around the entire batch with nanoTime necessarily return 4 seconds?

**Answer:** No. If run concurrently, elapsed time can be close to 2 seconds. Total CPU time or the sum of individual task durations is a different concept.

## 15. Official References

- [JDK 17 API — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): API contract, arbitrary origin, nanosecond units, and taking differences to measure elapsed time.
- [JDK 17 API — System.currentTimeMillis()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#currentTimeMillis()): calendar time in milliseconds since the epoch.
- [JDK 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): representing durations and converting units.
- [JDK 17 API — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): converting between time units.
- [JDK 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): representing a point on the timeline.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmarking tool for Java and the JVM.

**Key takeaway:** To measure elapsed time, take `start = System.nanoTime()` before the work and compute `System.nanoTime() - start` after the work. Only use differences within the same JVM, and never treat absolute values as timestamps. Convert via `TimeUnit` or `Duration` when displaying, use the difference pattern for timeouts, and choose JMH if the goal is serious benchmarking.
