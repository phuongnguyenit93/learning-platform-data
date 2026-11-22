# Benchmarking with Realistic Error Scenarios and Frequencies

When optimizing exception handling in Java, a result like "throwing an exception takes X ns" may hold true in a very narrow test, yet **fail to reflect real application performance**. Real systems have successful requests, rare errors, bursts of failures when a dependency goes down, different handling paths, and logging/cleanup costs. If a benchmark throws an exception on 100% of loop iterations, you are measuring a workload that does not resemble production; if a benchmark has no errors at all, you also have no idea how the application will handle an error burst under load.

A good benchmark must first answer: **which part of error handling is being measured, under what scenario distribution and frequency, on which JVM/system, and using what metric?** Only after defining the workload and ensuring code correctness does it make sense to compare speed.

This lesson belongs to the **Performance** section of Java core – exceptions. The focus is on designing measurements that include both success and failure branches, avoiding confusing error rate with CPU utilization, using the Java Microbenchmark Harness (JMH) when microbenchmarking is needed, and validating with profiling/load testing in realistic contexts. Code examples are compatible with Java 17 and later.

## 1. What should an exception benchmark model?

A single call may go through:

```text
Receive request / record
         |
         v
Check condition
     /         \
 Success      Failure
     |           |
  Compute    Create exception
     |           |
Return res.  throw/unwind
                 |
                 v
           catch or boundary
                 |
                 v
         log / metric / cleanup
                 |
                 v
          return error result
```

Not all failure paths have the same cost. An `IllegalArgumentException` thrown and caught immediately inside a method differs from an `IOException` raised after a network call, propagating across multiple layers and logged with a stack trace. Therefore, you must clearly choose the **unit of work** instead of lumping all of it together as "exception overhead."

Factors to specify in a benchmark definition:

| Factor | Question to answer | Why it matters |
| --- | --- | --- |
| Goal | Measuring allocation, throughput, latency, or p99? | Each metric answers a different question. |
| Success path | What happens when there is no error? | Most traffic may take this branch. |
| Failure path | Which exception, where is it created, where is it caught? | Constructor/backtrace, throw, and cleanup differ. |
| Frequency | 0%, 0.1%, 1%, 10%, 50%, 100%, or another distribution? | Average cost changes dramatically with the error rate. |
| Time distribution | Are errors scattered evenly or clustered in bursts? | Bursts create pressure on logging, GC, and queues. |
| Logging | Off, on, synchronous, asynchronous, or sampled? | I/O and formatting can dwarf throw/catch. |
| Call stack depth | Thrown locally or across multiple methods? | Stack capture/unwinding and `finally` blocks change. |
| Environment | JDK, GC, CPU, memory, log destination? | Numbers cannot be transferred blindly across machines. |
| Data | Simple request or large payload, warm/cold cache? | You might accidentally measure parsing/I/O instead of exceptions. |

**There is no single standard error rate for all services.** A user-facing API might see 0.1% errors during normal hours; a batch parser might see 20% invalid data; an infrastructure-dependent service might see 70% errors for a few minutes. All rates below are **hypothetical scenarios for designing tests**, not statistics from a specific application.

## 2. Distinguishing per-phase cost from full error-path cost

A realistic measurement of `throw new IllegalStateException(...)` usually already includes **constructor, allocation, backtrace, throw/unwind, and catch**. If the handler also logs, the result includes formatting/appending costs as well. To optimize the right place, split benchmarks into groups:

1. **Successful path** – runs the normal path, possibly with a `try/catch` block that does not throw.
2. **Create-only** – instantiates a `Throwable` without `throw`; meant to isolate constructor/stack-capture cost where possible.
3. **Throw pre-created** – throws an already-created exception; helps roughly separate throw/catch, though it no longer captures a stack trace at the new failure site and does not model common production paths.
4. **Throw new and catch** – measures the typical failure path comprising creation, throwing, and catching.
5. **Throw across frames** – throws at a lower layer, unwinding through one or more frames and `finally`/`try-with-resources`.
6. **Catch and handle** – classification logic, error translation, returning a fallback, updating counters.
7. **Catch and log** – adds stack rendering, formatting, appender, queue, and flush according to configuration.
8. **End-to-end request** – validation, core processing, persistence/network, error mapping, logging, and response.

When reporting results, state clearly which group the measurement belongs to. Never take a "throw new + catch + log" benchmark and conclude that the `throw` opcode **alone** is as slow as that entire duration.

### How to think about average cost

If there are only two paths (success/failure) and system interactions are ignored, average latency can be **estimated** as:

\[
E[T] \approx (1-p)\,E[T\mid success] + p\,E[T\mid failure]
\]

Here `p` is the actual error rate, not an arbitrary number used in a benchmark loop. For example, **to illustrate with hypothetical numbers**: success takes 1 unit, failure takes 101 units; at `p = 0.01`, the modeled average cost is `0.99·1 + 0.01·101 = 2` units. This does not mean actual CPU, p99, or throughput doubles, because concurrency, scheduling, I/O, GC, logging, and system load also come into play.

An average calculation does not describe **tail latency** or situations where many errors happen simultaneously. Measurements must add latency distributions and burst workloads when those matter.

## 3. Determining error rates from production

Before running a benchmark, determine error frequencies for each workload type:

- **Per request:** failed requests / total requests in the same window.
- **Per record:** failed records / total records processed; may differ from the request rate because one request can contain multiple records.
- **Per dependency operation:** failed query/HTTP attempts / total attempts; if a request retries multiple times, the attempt failure rate may differ from the final request failure rate.
- **By error type:** validation, data not found, timeout, connection reset, resource exhaustion, internal bug, etc. Do not lump everything into a single exception.
- **By time window:** a 1-minute rate and a 1-hour rate can differ vastly; a daily average can hide a severe incident.

If you do not have real data yet, **state your assumptions clearly** and test an instructive matrix, for example:

| Hypothetical scenario | Error rate | Used to check |
| --- | ---: | --- |
| Healthy | 0% | Baseline for the success path. |
| Mostly healthy | 0.1% | Rare errors; exception cost is diluted. |
| Normal mixed | 1% | Low-error mix to observe overhead when deviating from 0%. |
| Degraded | 10% | Shifts in latency distribution and logging frequency. |
| High rejection/bad batch | 50% | Workload where errors are a very frequent state. |
| Incident | 100% in a short window | Burst resilience, GC/logging/circuit breaker behavior. |

These rates are **exploratory benchmarks**, not SLA targets, and do not mean "50% errors" is normal. Once you collect metrics, replace the hypothetical matrix with your real service's distribution.

Distinguish between **the rate at which exceptions are thrown** and **the rate at which requests fail**. A request can throw and catch multiple exceptions internally and still complete successfully. During retries, a request might create 3 I/O exceptions before the fourth attempt succeeds. Per-request measurements and per-exception-event measurements answer two different questions.

## 4. Realistic data: error distribution and correlation

A random benchmark with 1% evenly scattered errors is not equivalent to a workload with 1% errors all concentrated into a single minute. Both have the same overall rate but very different system characteristics:

**Evenly scattered errors:**

```text
S S S S E S S S S S S S S E S S S S S ...
```

**Bursty errors:**

```text
S S S S S S S S E E E E E E E E S S ...
```

Here `S` is success and `E` is error. A burst can cause many requests to log stack traces at the same time, filling log queues, raising allocation rates, triggering GC, and stretching p99. Many threads may also retry against a broken dependency simultaneously, increasing load and prolonging the incident.

Useful workload dimensions:

- **Time distribution:** scattered, bursty, periodic, errors correlated by host or shard.
- **Input size:** small/large records, payload type, parsing depth.
- **Error type:** cheap validation vs. I/O/network timeout or cleanup exception.
- **Stack depth:** caught near the throw site vs. at the top-level boundary.
- **Logging rate:** 0%, all, sampled; sync vs. async.
- **Worker count:** 1 thread, CPU-matched thread count, pool under queue contention.
- **Infrastructure state:** cache hit/miss, dependency healthy/unavailable, disk/network throughput.

If you want a benchmark to measure the effect of **frequency**, vary one independent variable per experiment and hold other factors steady. If you change the error rate, logger, and thread count all at once and observe different throughput, you cannot attribute the cause to exceptions.

## 5. Java 17 example: generating a workload with an exact error rate

First, we need a **standalone** program that proves the input data actually has the intended error rate. The following program builds 10,000 inputs and injects negative values into an exact fraction using an arithmetic permutation to create scattered errors. It also compares this with a case where all errors sit at the start of the batch (*burst*). The output only counts successes and failures, **without pretending to be a performance measurement**.

Create `ErrorRateScenarioDemo.java`:

```java
public class ErrorRateScenarioDemo {

    private static final int TOTAL = 10_000;

    private static final class InvalidValueException
            extends RuntimeException {
        InvalidValueException() {
            super("negative input");
        }
    }

    private record Stats(int success, int failures, long checksum) {}

    private static int process(int input) {
        if (input < 0) {
            throw new InvalidValueException();
        }
        return input + 1;
    }

    private static Stats run(int badCount, boolean burst) {
        int success = 0;
        int failures = 0;
        long checksum = 0;

        for (int i = 0; i < TOTAL; i++) {
            // 37 is coprime to 10000:
            // (i * 37) % TOTAL visits each value 0..9999 once.
            int position = burst ? i : (i * 37) % TOTAL;
            int input = position < badCount ? -1 : i;

            try {
                checksum += process(input);
                success++;
            } catch (InvalidValueException ex) {
                failures++;
            }
        }

        return new Stats(success, failures, checksum);
    }

    public static void main(String[] args) {
        int[] badCounts = {0, 10, 100, 1000, 5000, 10000};

        for (int count : badCounts) {
            Stats stats = run(count, false);
            System.out.println(
                "scattered " + count + "/10000"
                    + " success=" + stats.success()
                    + " failure=" + stats.failures()
            );
        }

        Stats burst = run(1000, true);
        System.out.println(
            "burst 1000/10000 success=" + burst.success()
                + " failure=" + burst.failures()
        );
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ErrorRateScenarioDemo.java
java ErrorRateScenarioDemo
```

Exact stdout:

```text
scattered 0/10000 success=10000 failure=0
scattered 10/10000 success=9990 failure=10
scattered 100/10000 success=9900 failure=100
scattered 1000/10000 success=9000 failure=1000
scattered 5000/10000 success=5000 failure=5000
scattered 10000/10000 success=0 failure=10000
burst 1000/10000 success=9000 failure=1000
```

Explanation:

1. `TOTAL = 10_000` is fixed. Because `gcd(37, 10000) = 1`, `(i * 37) % 10000` permutes all positions 0 through 9999, so comparing against `badCount` produces **the exact** number of errors required.
2. With `badCount = 10`, the error rate is 0.1%; `100` is 1%; `1000` is 10%; `5000` is 50%.
3. The `burst = true` branch picks `position=i`, so the first 1,000 errors occur consecutively, while the total error count matches the scattered case.
4. `Stats.checksum` keeps the processed data alive in code; the example does not print the checksum because the goal here is verifying rates.
5. The program **does not measure nanoseconds, throughput, or p99**. It is merely an exact-count scenario generator that can be adapted into a real test/benchmark.
6. In a real benchmark, data preparation should be separated from the measured region if the goal is input-processing cost rather than dataset-construction cost.

The simple permutation here **does not represent production time distribution**, and when executed sequentially it only changes the order of errors across elements. To evaluate bursts causing queue contention, log backpressure, and concurrency effects, you need a multi-threaded workload or load test with controlled request arrival times.

## 6. Why not use a single System.nanoTime loop as a conclusion?

A commonly seen example:

```java
long begin = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    try {
        throw new IllegalArgumentException("bad");
    } catch (IllegalArgumentException ignored) {
    }
}

System.out.println(System.nanoTime() - begin);
```

This **illustrates an unreliable test**, not a valid benchmark. Its problems include:

- It only tests **100% errors**, failing to represent real requests with 0.1% or 1% errors.
- It lumps constructor/stack capture, `throw`, and `catch` together.
- There is no control test for the success path with the same data/work.
- A single run may not warm up the JIT; results mix in startup, class loading, and GC.
- The JIT may optimize code differently than expected, especially when results are not meaningfully consumed.
- Measuring total loop time reveals nothing about request latency distribution or p99.
- No logging, no cleanup, no concurrency, no network, and no bursty errors.
- OS thread scheduling and background machine load can dominate variance.

`System.nanoTime()` is a monotonic clock API for measuring relative elapsed time and is useful when applied properly, but **the API itself does not turn a loop into a scientific benchmark**. You should not cite a single number from the snippet above as the performance cost of Java exceptions.

## 7. Using JMH for microbenchmarks

**JMH (Java Microbenchmark Harness)** is an OpenJDK ecosystem tool for designing microbenchmarks with warm-up, measurement iterations, JVM forks, result consumption to prevent dead-code elimination, and proper statistics. JMH is **not part of the JDK standard library**, so it requires an appropriate project and JMH dependencies.

Common building blocks:

| Annotation/configuration | Purpose |
| --- | --- |
| `@Benchmark` | Marks a benchmark method. |
| `@State(Scope.Thread)` | Gives each worker thread its own benchmark data, reducing unintended sharing. |
| `@Param(...)` | Runs each configuration of error rate, stack depth, or logging. |
| `@Setup(Level.Trial)` | Builds inputs before measurement, avoiding mixing dataset-creation cost. |
| `@BenchmarkMode(Mode.Throughput)` | Measures invocations per unit time. |
| `@BenchmarkMode(Mode.AverageTime)` | Measures average time per invocation/operation. |
| `@Warmup` / `@Measurement` | Configures warm-up and measurement iterations. |
| `@Fork` | Runs the benchmark in independent JVM forks. |
| `@Threads` | Controls worker thread count; requires understanding shared state/contention. |
| `Blackhole` | Consumes data so results cannot be easily eliminated. |
| `@OperationsPerInvocation` | Scales a single invocation into multiple operations when appropriate for the goal. |

You do not need to attach every annotation at once. Choose the parameters that express your goal, then **record the full configuration in your report** so others can reproduce it.

### JMH template: varying error frequency in a controlled way

The code below is a **real JMH class**, not a Java program you compile with plain `javac`: it requires a project with JMH and its annotation processor configured. The example tests `badPerTenThousand` at 0%, 0.1%, 1%, 10%, 50%, and 100%. Each invocation processes a batch of 10,000 records, avoiding random input decisions inside the measured region.

File `ErrorRateBenchmark.java` (place in a JMH project package; adjust the package declaration as needed):

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OperationsPerInvocation;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class ErrorRateBenchmark {

    private static final int TOTAL = 10_000;

    @Param({"0", "10", "100", "1000", "5000", "10000"})
    public int badPerTenThousand;

    private int[] values;

    @Setup(Level.Trial)
    public void prepare() {
        values = new int[TOTAL];
        for (int i = 0; i < TOTAL; i++) {
            int position = (i * 37) % TOTAL;
            values[i] = position < badPerTenThousand ? -1 : i;
        }
    }

    private static int withException(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return value + 1;
    }

    @Benchmark
    @OperationsPerInvocation(TOTAL)
    public long throwAndCatch() {
        long sum = 0;
        for (int value : values) {
            try {
                sum += withException(value);
            } catch (IllegalArgumentException ex) {
                // Failure path handled; no logging in this measurement.
            }
        }
        return sum;
    }

    @Benchmark
    @OperationsPerInvocation(TOTAL)
    public long conditionalResult() {
        long sum = 0;
        for (int value : values) {
            if (value >= 0) {
                sum += value + 1;
            }
        }
        return sum;
    }
}
```

How to set up the JMH project:

1. Create a Maven/Gradle project or official JMH template using a version compatible with your JDK.
2. Add JMH core and the `jmh-generator-annprocess` annotation processor per your build tool's configuration; **do not mix different versions** of these two modules.
3. Place the class in a source set processed by the JMH annotation processor; some setups/templates require a named package rather than the default package.
4. Build the project per the template's instructions to generate the benchmark runner, and run the benchmark via the JMH runner.
5. Record the exact command, JMH/JDK versions, warm-up, measurement, forks, threads, CPU, and GC when publishing results.

Example command using a **pre-built JMH runner**, not a plain JDK `java` command:

```bash
java -jar target/benchmarks.jar ErrorRateBenchmark -wi 3 -i 5 -f 2
```

The JAR name and path depend on how your JMH project is configured; the command above only applies when the build outputs `target/benchmarks.jar`. **There is no fixed stdout** for this benchmark: actual ns/op depends on hardware, JVM, and workload. Do not copy fabricated numbers into documentation.

Key points when reading results:

- `@OperationsPerInvocation(TOTAL)` lets JMH interpret a 10,000-element batch as the corresponding number of operations. However, the measurement still includes loop, check, and accumulation overhead; there is no "pure ns of throw."
- `throwAndCatch` pays constructor/backtrace cost on errors, whereas `conditionalResult` creates no exception. This compares **two API/error-path strategies**, not catch overhead in isolation.
- `@Param` produces results per error rate; when analyzing, compare within the same configuration and environment.
- `@State(Scope.Thread)` gives each JMH worker its own dataset. To measure contention, you need a separate test with explicitly defined shared state.
- Returning `long` lets JMH consume the result, reducing the risk of the entire computation being eliminated. Still, inspect assembly/profiles if numbers look anomalous; no benchmark is immune to all optimizations.
- At high error rates, exception logic and branch logic do not share the same memory/JIT characteristics. A performance gap does not prove "exceptions should never be used": it also depends on whether the failure is an expected business state.

If a JMH configuration needs to measure **batch throughput** instead of average time per record, omit `@OperationsPerInvocation` or switch to the appropriate mode/unit. Always state whether an "operation" is **one record** or **one batch**.

## 8. Verifying data and equivalence before measuring

A benchmark is only valid if both approaches produce **equivalent business results** on the same inputs. In the example above:

- Both `throwAndCatch` and `conditionalResult` add `value+1` for every non-negative input.
- For negative inputs, both skip the element.
- Neither logs, retries, or performs I/O.
- The fixed dataset is built from the same `badPerTenThousand`.
- Both computations return `long` to avoid `int` overflow across 10,000 elements.

However, the two APIs are **not equivalent in diagnostic capability**: one creates an `IllegalArgumentException` with a stack trace, while the other treats bad data as a non-throwing conditional branch. This is a design difference that must be noted; you cannot look only at ns/op and declare branching always right.

If you want to compare two implementations that share the same exception contract, keep the exception type, required message, catch path, and semantic side effects identical; avoid letting one implementation skip logging or validation that the other must perform.

### Verifying rates before running the benchmark

You can test `@Param` values beforehand:

```text
badPerTenThousand = 0      → 0 errors / 10,000 records
badPerTenThousand = 10     → 10 errors / 10,000 records
badPerTenThousand = 100    → 100 errors / 10,000 records
badPerTenThousand = 1000   → 1,000 errors / 10,000 records
badPerTenThousand = 5000   → 5,000 errors / 10,000 records
badPerTenThousand = 10000  → 10,000 errors / 10,000 records
```

This is the expected data table from the code, not performance numbers. Run count verification **outside the measured region** so checking overhead is not added to the main sample.

## 9. Separating rare errors from error bursts

A JMH benchmark processing batches sequentially usually shows average time for a workload, but **does not fully model system collapse when errors erupt simultaneously**.

To evaluate bursts:

1. Build two scenarios with the **same total requests and total errors**: evenly scattered vs. concentrated in a time window.
2. Generate load with an external load-testing tool/driver, controlling request rate and concurrency. You can simulate a dependency failing during a specific window.
3. Keep worker counts, queue capacities, log destinations, timeouts, and retry policies identical to production.
4. Observe throughput, p50/p95/p99, request timeouts, GC pauses, CPU, memory, dropped/blocked log time, and queue depth.
5. Record the start and end times of the error burst to distinguish **load-bearing** behavior from **recovery** time.
6. Verify correctness: were any jobs processed twice, was any data lost, were any resources left unclosed, or were any statuses mistakenly marked "success" by a fallback?

For example, an application handles 1,000 requests/s with 1% overall errors. A scenario with a steady 10 errors/s differs from one with 100 errors/s over a short burst followed by no errors. With synchronous logging or bounded queues, the two scenarios can cause vastly different latencies. The numbers here only illustrate distribution shapes, **not experimental measurements**.

### Do not let fault-injection mechanisms unintentionally alter the workload

If fault injection works by calling `Thread.sleep(500)` before throwing, you are also measuring **500 ms of waiting**, not just exception cost. When testing network timeouts, waiting time is a legitimate part of an end-to-end scenario, but not the cost of `throw`. Label scenarios accurately:

- `ValidationException` thrown locally, no I/O.
- `IOException` thrown immediately by a fake adapter, no network.
- Real timeouts from network calls or deliberate fake delays.
- DB/HTTP errors with real transactions, retries, backoff, and cleanup.

These are distinct, useful scenarios; do not blend them into a single "exception benchmark."

## 10. Varying frequency without adding random overhead to the hot path

A common mistake:

```java
for (...) {
    if (random.nextDouble() < errorProbability) {
        throw new RuntimeException();
    }
    doWork();
}
```

This is an illustrative snippet; `random`/`errorProbability`/`doWork` are undefined. If your goal is measuring exception cost, you are also measuring random number generation, branching, and data variation. Randomness itself may be part of a real workload, in which case state that explicitly.

Common solutions:

- **Precompute inputs** or fault-triggering state in `@Setup`.
- Use the exact same dataset for both strategies.
- Use a fixed seed if repeatable random tests are needed.
- Combine different distribution patterns, not just one highly predictable pattern.
- Separate **error rate** from **error ordering**. The same 1% distributed evenly, in bursts, or grouped by key can produce different JIT, cache, and concurrency behavior.
- When comparing, alternate benchmark run order or use independent forks to reduce effects from CPU thermals, JIT state, and cache state.

Randomness does not have to be banned in benchmarks. If production work requires randomness, it can be part of what you measure. What matters is **knowing what you are measuring** and keeping the model aligned with your question.

## 11. Measuring stack trace, construction, throw, and catch separately

If profiling shows significant exception allocation, you can design targeted sub-benchmarks:

**Construct-only:** instantiate `new IllegalStateException("invalid")` without `throw`. You must consume the object so the JIT does not eliminate it as dead code. The default cost may already include stack capture.

**Throw cached:** create the exception during setup and rethrow the same object; measures the difference without construction cost. However, the stack trace on rethrow is not the actual failure site, and sharing the object across threads carries risks. This is **an isolation technique for understanding cost**, not a production trick to apply automatically.

**Throw new local:** create, throw, and catch immediately without logging or cleanup. Compare with construct-only to understand control-flow/unwinding, though the difference between two benchmarks **is not an exact per-opcode subtraction**, because JIT and code shapes differ.

**Throw across depth:** chain multiple methods and vary frame count; separates stack-capture cost from exiting scopes with `finally`.

**Log disabled/enabled:** separately benchmark message construction, stack rendering, and appender cost. A log call with heavy formatting can still burn CPU even when the level is disabled if expressions are evaluated eagerly.

**Cleanup failure:** if `close()` also throws, costs change because Java must attach suppressed exceptions. Include this only if that path is relevant.

State clearly what level of error diagnostics is preserved. An exception without a stack trace via `Throwable(String, Throwable, boolean, boolean)` can be faster, but **trades away diagnostic capability**. Do not compare it against full exceptions and treat them as having the same contract.

### Watch out for HotSpot fast-throw optimization

Some HotSpot versions/configurations optimize certain exceptions **generated frequently by the JVM itself** at the same site, such as implicit `NullPointerException` or bounds checks. Stack traces may be omitted in special circumstances. Do not generalize that behavior to `throw new DomainException(...)` or to all JVMs.

If a benchmark shows suspiciously tiny numbers after warm-up, check the exception type, JVM version/flags, stack depth, and assembly/profile if needed. **Do not rely on HotSpot-specific behavior as a stable API contract.**

## 12. Logging: a variable to measure separately

Logging exceptions can far exceed throw/catch cost when many stack traces are emitted. A production-oriented test should specify:

| Configuration | What is being measured | What is easily missed |
| --- | --- | --- |
| No logging | Constructor + throw/catch + lightweight handler | Does not represent paths with mandatory audit logging. |
| Disabled by log level | Level-check / message-prep overhead | Eager log expressions may still run before the logger discards them. |
| Log message, no stack | Formatting and appender for short messages | Less diagnostic information for debugging failures. |
| Log full stack | Frame/cause/suppressed rendering, I/O | Cost grows with stack depth, cause chains, and log line count. |
| Async logging | Enqueueing and background consumer processing | A full queue may block or drop records depending on policy. |
| Sampling/rate limiting | Filtering most logs during bursts | Total error metrics must still be kept so incidents aren't hidden. |

With `java.util.logging`, you can use a message supplier to defer formatting when the level is not enabled:

```java
logger.log(Level.FINE, () -> expensiveMessage(context));
```

This is an **illustrative snippet**; `logger`/`context`/`expensiveMessage` are assumed to exist, and `java.util.logging.Level` must be imported. A supplier avoids building the message unnecessarily under the right configuration, but it does not eliminate the cost of an exception that was already created.

Never log raw payloads, tokens, credentials, SQL containing sensitive data, or full personal context just to make a benchmark produce more bytes. Simulated heavy logs must use non-sensitive test data.

### Log storms during error bursts

If 10,000 errors log stack traces simultaneously, the logger can:
- Sharply increase allocation and GC;
- Wait synchronously on console/file writes;
- Grow queue size and block worker threads;
- Drop log records or introduce long waits;
- Consume network bandwidth and disk space;
- Slow down non-error requests.

Therefore, when evaluating service throughput/latency, do not just toggle `logger` on/off and measure averages. Observe **log rate, queue occupancy, dropped log count, appender CPU, and drain rate** during bursts over time.

## 13. Metrics to record alongside benchmarks

A minimal report table can include:

| Metric | Unit | Meaning |
| --- | --- | --- |
| Throughput | requests/s or records/s | Work completed per unit time. |
| Mean latency | ms/operation | Average; easily skewed by the success/failure ratio. |
| p50/p95/p99 latency | ms | Latency distribution; especially critical during incidents. |
| Allocation rate | MB/s or B/op | Allocation pressure from objects, stack traces, logging. |
| GC pause/frequency | ms/count | Impact on tail latency and throughput. |
| CPU utilization | % per core/process | Actual processing load, not just wait time. |
| Error/exception rate | errors/s and % requests | Verifies the scenario; avoid inferring from log counts. |
| Log volume/drop/block | records/s, bytes/s, count, ms | Cost and degree of observability loss. |
| Queue depth | jobs/log records | Sign of backpressure or saturation. |
| Retry attempts | attempts/request | Distinguishes original load from retry-amplified load. |
| Resource usage | file descriptors, connections, threads | Cleanup health under consecutive errors. |

For JMH microbenchmarks, `ns/op`, `ops/s`, and confidence/error estimates are useful; they **do not automatically give end-to-end request p99 latency**. To get service p99, use an appropriate load/observability tool with timestamps and controlled workloads. When measuring client-side latency, account for network, TLS, scheduling, and queueing.

### Observing with Java Flight Recorder and profilers

Java Flight Recorder (JFR) and profilers help locate hot spots and analyze allocations, CPU, pauses, and exception activity depending on enabled capabilities/events. When collecting data, record the recording configuration and profiling overhead. **Do not assume all exception events are captured completely under every default JFR configuration**, as event settings and thresholds vary.

A pragmatic workflow:

1. Run healthy and degraded baselines with the same JVM/configuration and controlled data.
2. Collect throughput/latency/allocation/GC/log metrics.
3. Profile to see whether time goes to exception constructors, stack traces, logger, serializers, I/O, or business code.
4. Optimize only components consuming significant resources.
5. Re-run the same scenario and verify no loss in correctness, observability, or diagnosability.

Do not disable stack traces or swallow exceptions before proving they are actually the bottleneck.

## 14. Benchmarks must distinguish "request succeeded after retry" from "failed attempt"

For example, a request calls a dependency three times:

```text
Request #1:
  attempt 1: IOException
  attempt 2: IOException
  attempt 3: success
Result: request succeeded, but 2 exceptions occurred.
```

If a system reports 0% failed requests while every request retries twice, the exception rate can still be very high. A per-`request` benchmark must model retry policies and backoff if that is production behavior; a per-`attempt` benchmark should be labeled separately.

Do not compare a "no-retry" version against a "with-retry" version and conclude the latter is slower because of exceptions. It is doing more work.

When retrying on timeout errors, you need to know whether the old attempt is still running, whether it has side effects, and whether it is idempotent. Never design a benchmark that triggers real transactions outside a test environment just to get "realistic errors."

## 15. Concurrency, pooling, and how errors affect threads

A single-threaded in-memory loop does not reflect:

- Executor queues building up a backlog;
- Worker threads blocking on synchronous loggers;
- Thousands of requests retrying against the same failing dependency;
- Circuit breakers changing state;
- Semaphores or connection pools exhausting due to improper cleanup;
- GC pauses affecting many concurrent requests at once;
- Tail latency spiking when a small fraction of requests holds resources too long.

In load tests, measure worker counts and concurrent requests; avoid uncontrolled high thread counts where the benchmark measures thread-scheduling overhead instead of exceptions. For HTTP server workloads, track open-loop request arrival rates (issuing requests at a fixed schedule) or intentional closed-loop concurrency, and state the load model clearly.

One trap is **coordinated omission**: if the load generator only sends the next request after the previous one responds, it automatically backs off when the server slows down and fails to record requests that should have arrived. When SLOs or tail latencies matter, choose a load model and measurement method that does not mask overload periods.

## 16. Ensuring fairness between two implementations

Two approaches being compared must be evaluated under **the same workload and the same contract**:

- Same input dataset, error rate, and input ordering per scenario.
- Same success results and same error-handling behavior.
- Same logging/metrics level when measuring end-to-end.
- Same retry frequency, deadline limits, and cleanup.
- Same JVM flags, heap/GC, hardware, and container limits.
- Equivalent JMH warm-up/forks and steady environment.
- Never let one version skip validation or I/O and declare it "faster."

If a result-type approach provides no stack trace while an exception approach provides a full trace, they have **different semantics**. You can still compare them to inform a design decision, but the conclusion must state the trade-off clearly rather than calling it a "free" optimization.

### Guarding against unrealistic benchmark optimizations

Common pitfalls:

- Results are ignored, so the JIT eliminates the computation;
- Input values are constants that the JIT can fold away;
- Data is generated randomly inside the measured region even though production already has the data;
- The benchmark only throws a singleton exception, skipping construction/stack capture;
- The benchmark relies on an implicit `NullPointerException` that receives special JVM optimization;
- Comparing runs executed under different CPU thermal throttling conditions;
- Too few forks, picking only a single "fastest" number;
- Using error-free benchmark runs to predict error-burst performance.

JMH mitigates several of these risks, but **it cannot fix a flawed workload**. Reviewing the scenario matters more than piling on annotations.

## 17. How should a benchmark report be structured?

A report can use this template:

```text
Goal: measure cost of error-handling choices for a batch parser.
JDK: <actual version and vendor>
JMH: <actual version>
Hardware/OS: <actual CPU, memory, container limits>
GC/JVM flags: <actual values>
Work unit: one record / one 10,000-record batch
Scenario: 0%, 0.1%, 1%, 10%, 50%, 100% errors
Exception: newly created IllegalArgumentException; caught locally
Logging: OFF in JMH; separate scenario with logging ON
Warm-up/measurement/forks: <actual values>
Output: throughput, average time, B/op, GC metrics
Load test: requests/s, p50/p95/p99, queue/log backpressure
Correctness: outputs and error counts match between both approaches
Conclusion: <which change helps which workload, and at what trade-off>
```

This is a **report template**, not measured data, and items inside `<...>` are placeholders to be filled from actual runs. Never invent numbers to make it look like a benchmark was run.

Every conclusion should be scoped to its data:

> In environment X, with input Y and error rate Z, approach A has lower B/op and higher throughput than approach B; results do not demonstrate the impact on p99 when logging is enabled.

Avoid concluding:

> Java exceptions are always 1000x slower and should never be used.

That is an unconditional claim; no single benchmark fits every workload and every JVM.

## 18. Applied scenarios: validation, parsing, and system errors

### 18.1. Rare validation errors

A public API receives mostly valid requests, with only ~0.1% violating constraints. If the system already has clear exception types and clean contracts, average latency impact may be negligible. Benchmark the success path with `try/catch` and the rare-error path; do not rush to rewrite the API just because a 100%-throw benchmark looks slow.

### 18.2. Batch parser frequently encountering bad data

If 20–40% bad records is an **expected state**, throwing an exception for every record can incur substantial allocation/GC cost. A result type like `ValidationResult` may fit better. However, keep error statistics and record positions; optimization must not strip required audit information.

### 18.3. Widespread network failures

A network timeout can spend hundreds of milliseconds waiting; creating an `IOException` may be tiny compared to the wait time. Yet when tens of thousands of concurrent requests receive exceptions and log full stack traces, logging and GC can become a major load. Measure end-to-end behavior, retries, and log throughput rather than only local throw/catch.

### 18.4. Interrupted workers and resource cleanup

When a task is canceled, `InterruptedException` may trigger `finally`/`try-with-resources` to close sockets, return connections, or release locks. Benchmarking cancellation paths must include real cleanup time if the question is **shutdown duration**; do not omit cleanup to get prettier numbers.

### 18.5. CompletableFuture and task failure

`CompletableFuture` can store exceptional completions; `join`/`get` may also create or throw `CompletionException`/`ExecutionException` wrappers depending on the API. For async workloads, measure the whole pipeline/callback chain, queueing, executor behavior, and how fallbacks affect results. A single-threaded exception microbenchmark does not represent completion latency of an async pipeline.

## 19. Common mistakes when evaluating performance

**Always throwing exceptions in a benchmark and applying the numbers to production with 0.1% errors.** This uses the wrong frequency model. Measure a mixed workload at realistic rates.

**Using log count as the exception count.** An exception may be logged multiple times or not logged at all; place counters at appropriate boundaries.

**Assuming all errors are alike.** Validation, timeouts, OOM, I/O, and cancellation have different costs and policies.

**Using `System.nanoTime` once and picking the lowest result.** Fails to account for warm-up, JIT, GC, variance, and environmental noise.

**Measuring without a control group.** To state how much overhead throw/catch adds, establish a baseline with the same success/validation logic.

**Failing to verify dataset correctness.** Thinking you ran at 1% errors when the data actually produced 0% or 100%, leading to false conclusions.

**Generating random numbers, formatting messages, and logging inside a throw benchmark without noting it.** Costs are mixed; separate the tests or explicitly label it as an end-to-end workload.

**Using a cached exception and generalizing to `throw new`.** Reusing an object skips constructor/backtrace cost and changes stack trace semantics.

**Disabling stack traces just to lower ns/op.** Can destroy production debugging information; prove both the benefit and the trade-off.

**Measuring the mean while ignoring p99.** Exception bursts can make some requests severely slow even when the mean rises only slightly.

**Ignoring queue/log backpressure.** Async logging does not eliminate cost; it shifts it to the consumer and queue.

**Comparing across different JDKs/hardware/configurations.** Results depend on JVM, JIT, GC, and flags like fast-throw; record the environment.

**Not re-running after optimizing.** A valid conclusion requires repeated measurements under the same scenario and proper regression checks.

## 20. Practical checklist

Before trusting an exception benchmark, confirm:

- [ ] **The measurement question** is defined: constructor, throw/catch, logging, or end-to-end?
- [ ] A baseline exists for the success path and equivalent error handling.
- [ ] **The unit** is defined: invocation, record, request, task, or retry attempt.
- [ ] Error rates are backed by data or **explicitly marked as assumptions**.
- [ ] At least one rare-error scenario and one high-error/burst scenario are included as appropriate.
- [ ] Inputs share the same distribution/size across implementations; error counts have been tested.
- [ ] All return values are consumed; no benchmark code is inadvertently eliminated by the JIT.
- [ ] JMH warm-up, measurement, forks, threads, and state are clearly configured.
- [ ] Logging enabled/disabled state, message formatting, and output destination are recorded.
- [ ] GC/allocation metrics are reviewed alongside CPU/throughput.
- [ ] Where SLOs matter, p95/p99 are measured via load tests with realistic load and concurrency.
- [ ] Cleanup, cause/stack trace, or validation is not stripped out just to get faster numbers.
- [ ] The report includes environment, versions, commands, and error margins; no fabricated results.
- [ ] Re-tested on realistic workloads and verified correctness after optimization.

## 21. Self-check exercises

**Q1.** An API serves 1 million requests, with 1,000 failing. Does a benchmark that throws an exception on all 1 million iterations represent the production rate?

**Answer:** No. The request failure rate is `1000/1_000_000 = 0.1%`. A 100%-throw test can serve as a stress scenario, but you must also test 0.1% to model normal operation.

**Q2.** Two benchmarks both have 10% errors. Benchmark A scatters them evenly; Benchmark B concentrates all errors at the beginning. Can end-to-end results differ?

**Answer:** Yes. A burst can fill log queues and cause sudden spikes in contention, retries, and GC. Equal overall error rates do not guarantee equal p99.

**Q3.** A benchmark shows a large gap between `throw new IllegalArgumentException` and `throw cachedException`. Should you use cached exceptions in production?

**Answer:** Do not jump to that conclusion. A cached exception skips per-error construction/stack capture and its stack trace may no longer reflect where the failure occurred; evaluate contracts, diagnostics, and correctness before making that trade-off.

**Q4.** Does a `try/catch` block where no error occurs pay the full cost of a stack trace?

**Answer:** No. If no `Throwable` is created and nothing is thrown, no exception stack trace is generated merely from having a `catch` structure.

**Q5.** On an I/O error path, most time is spent in a 2-second timeout. Will optimizing the exception constructor significantly reduce p99?

**Answer:** Not necessarily. If I/O wait time dominates, the constructor may not be the bottleneck. Profile and separate wait time, cleanup, retries, and logging.

**Q6.** JMH shows one approach is 20% faster under 100% failure, but production only sees 0.1% errors. Can you announce that the whole service is 20% faster?

**Answer:** No. You must measure the realistic mix and end-to-end behavior. A 100%-failure result does not automatically extrapolate to the improvement of the entire workload.

## 22. Conclusion

**Measuring exceptions properly means measuring the right workload.** Every measurement must account for error rate, time distribution, unit of work, error type, catch/cleanup/logging paths, and target metrics. Use JMH to explore micro-level costs under controlled settings; use load tests, JFR/profilers, and metrics to confirm real-system impact. Compare success, rare errors, frequent errors, and error bursts; do not extrapolate from a single 100%-throw test into an absolute rule for all applications.

A trustworthy optimization is one that is **measured, reproducible, and preserves both contracts and diagnosability**. Reducing exceptions on a hot path when failures are an expected state can help; never sacrifice validation, necessary stack traces, causes, cleanup, or responsible logging just for a smaller ns/op number.