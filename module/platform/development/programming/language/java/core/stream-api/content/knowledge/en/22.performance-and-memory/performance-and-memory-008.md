# Benchmarking Performance with JMH: Warmup, Forks, and Preventing Code Elimination

When comparing a `for` loop against the Java Stream API, a one-off `System.nanoTime()` timing snippet very easily leads to wrong conclusions. The first time a method runs, the JVM may be loading classes, verifying bytecode, allocating memory, and performing Just-in-Time (JIT) compilation. After a few thousand invocations, the optimizer can inline calls, eliminate allocations, remove unused computations, or recompile based on runtime profiles. A first-run timing **does not represent** steady-state execution.

**JMH (Java Microbenchmark Harness)** is the dedicated toolkit in the OpenJDK ecosystem for designing and running Java *microbenchmarks*. It orchestrates **warmup**, **measurement**, **forks** (separate JVM processes), run durations, threads, result consumption, report formats, and profilers. JMH **does not guarantee** every benchmark is valid: the author must still choose a representative workload and prevent optimizations from making the measurement meaningless.

This lesson belongs to the **Performance and Memory** chapter of the **JAVA_STREAM_API** module. We will learn how to measure lazy pipelines, `filter`, `map`, `reduce`, and `collect`; distinguish boxing, allocation, `Spliterator`, and parallel overhead; design fair benchmarks, read scores with error margins, use `Blackhole` or return values to prevent **dead-code elimination**, and recognize when to move from microbenchmarks to system-level benchmarking. Core examples use Java 17 or later; Java 24 Stream Gatherers are not required to learn JMH.

## 1. Why is a single `System.nanoTime()` measurement insufficient?

The short snippet below is **not a reliable benchmark**:

```java
import java.util.stream.IntStream;

public class NaiveTiming {
    public static void main(String[] args) {
        long start = System.nanoTime();

        long sum = IntStream.range(0, 1_000_000)
            .filter(n -> n % 2 == 0)
            .mapToLong(n -> n)
            .sum();

        long elapsed = System.nanoTime() - start;

        System.out.println("sum = " + sum);
        System.out.println("elapsed ns = " + elapsed);
    }
}
```

This code prints a real duration for **that specific run**, yet that interval can include factors unrelated to the comparison goal:

- Stream/JDK class loading and one-time initialization.
- Missing or ongoing JIT compilation.
- Different JVM optimization tiers across runs.
- GC, allocations, CPU caches, CPU frequency scaling, and OS scheduling.
- Data size and branch patterns too trivial compared to real workloads.
- Measurement timer resolution and overhead, especially for very short operations.

Even wrapping measurements manually in a `for` loop still suffers from **measuring loop overhead**, **not isolating JVM processes**, and **letting the compiler optimize away the work**. JMH does not replace experimental thinking, yet it standardizes most of this measurement machinery.

### 1.1. Know precisely what you are measuring

Before writing a benchmark, complete this sentence:

> “I want to compare **the time or throughput of summing squares of even numbers** on the same `int[]` array, between a `for` loop, a sequential `IntStream`, and a parallel `IntStream`.”

That is a concrete objective. It is very different from vague questions like “Are Streams slower than loops?” or “Are parallel Streams fast?”.

A measurement result is meaningful only within the scope of:

- The chosen input data.
- The Java version, JVM, and runtime flags.
- The exact operation definition.
- The benchmark mode and reporting unit.
- The measurement conditions (CPU, GC, contention, forks, warmup).

## 2. What JMH is—and what it is not

JMH executes methods annotated with `@Benchmark` via a dedicated harness. The harness can run warmup before recording metrics, execute multiple iterations, launch multiple JVM forks, and aggregate scores.

| What JMH helps with | What JMH does not solve automatically |
| --- | --- |
| Statistical benchmark execution harness | Whether the workload truly represents production |
| Configurable warmup and measurement | Whether the algorithm logic is correct |
| Forking isolated JVMs | Whether other processes compete for CPU on the machine |
| Multiple benchmark modes and units | Whether the chosen metric fits business goals |
| Consuming return values, `Blackhole` | Whether constant folding or synthetic math makes sense |
| `@State`, `@Param`, and `@Setup` | Whether shared state is designed incorrectly |
| `-prof gc` and profiler integration | Automatic conclusions about heap retention or memory leaks |

A **microbenchmark** typically measures a small operation or pipeline in a controlled setting. It is **not equivalent** to measuring end-to-end HTTP latency, database-backed system throughput, or large-file processing on real disks.

JMH is maintained under OpenJDK; official references are listed at the end. For new Java projects, use a JMH version compatible with your JDK and **pin the dependency version** so measurements remain reproducible.

## 3. Three key layers: warmup, measurement, fork

```text
JMH Runner
    |
    +-- Fork #1: Fresh JVM
    |      |
    |      +-- @Setup(Level.Trial)
    |      +-- Warmup iteration 1
    |      +-- Warmup iteration 2
    |      +-- Warmup iteration 3
    |      +-- Measurement iteration 1
    |      +-- Measurement iteration 2
    |      +-- Measurement iteration 3 ...
    |
    +-- Fork #2: Fresh JVM
           |
           +-- @Setup(Level.Trial)
           +-- Warmup iterations
           +-- Measurement iterations

        => JMH aggregates measurements and error margins
```

Three concepts that do not substitute for each other:

- **Warmup**: runs the workload before recording scores so the JVM can optimize and program state stabilizes.
- **Measurement**: the timed intervals JMH uses to compute the benchmark score.
- **Fork**: a **fresh JVM process** with independent heap/JIT/runtime state, reducing dependence on a single startup and one optimization profile.

**One fork is not one thread.** Inside each fork there can be one or more JMH worker threads. A `parallel()` pipeline also has its own internal task-splitting strategy; distinguish **JMH worker threads** from **parallel tasks inside the Stream**.

## 4. Warmup: the JVM needs time to optimize, yet there is no “magic number”

The HotSpot JVM typically runs bytecode through a mix of interpreter and tiered JIT compilers while profiling method “hotness” and data shapes. During execution, the JVM can:

- Inline method calls, including many lambdas expressed via `invokedynamic`.
- Specialize execution paths from runtime profiles.
- Eliminate or scalar-replace allocations via escape analysis when conditions permit.
- Perform constant folding and dead-code elimination.
- Recompile or deoptimize when optimization assumptions stop holding.

JMH configures warmup using annotations:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Warmup;

@Warmup(
    iterations = 3,
    time = 1,
    timeUnit = TimeUnit.SECONDS
)
```

This specifies **three warmup iterations**, each lasting roughly one second. Warmup data is **excluded from the main measurement statistics** in standard reporting.

### 4.1. How much warmup is enough?

There is no single warmup setting right for every problem. A nanosecond-scale addition differs from an object-allocating pipeline, a cached algorithm, or a service with long startup initialization.

How to choose:

1. Start with a clear baseline, such as `3–5` warmup iterations.
2. Inspect stability across iterations and JVM forks.
3. Increase warmup if measurements still drift strongly over time.
4. If the goal is **cold start**, design a separate experiment; never call a long warmup a cold-start measurement.
5. Record the configuration so runs can be reproduced later.

**Warning:** Warmup cannot fix a benchmark broken by dead-code elimination, bad data, or corrupted state. If the computation was optimized away, warming up longer does not make the result valid.

### 4.2. Warmup and stateful data

If a benchmark mutates a collection or exhausts an iterator across invocations, warmup can alter the input data itself. Measurement then no longer benchmarks the same problem as earlier iterations.

For example, do not create a single `Iterator` once and drain it in the benchmark without proper lifecycle resets. With immutable data or read-only arrays, this risk is much lower.

## 5. Fork: isolating JVM processes to reduce dependence on prior state

Example:

```java
import org.openjdk.jmh.annotations.Fork;

@Fork(2)
```

JMH runs the benchmark across **two JVM forks** per configuration. Each fork gets its own startup, warmup, JIT compilation, and measurement.

Why are multiple forks needed?

- JIT compilation and profiling decisions can vary between processes.
- Runtime state, memory layout, and background noise are never identical.
- A single fork might happen to hit an outlier profile.
- Multi-fork results show repeatability rather than extrapolating from one process.

### 5.1. Is zero forks (`@Fork(0)`) okay?

JMH offers a no-fork mode for certain development/debugging situations, yet **it should not be used as the default for trustworthy performance comparisons**. Without forking, the benchmark can be affected by the JVM hosting the harness and other benchmarks.

For decision-grade results, use at least one proper fork, and usually more than one fork when time and resources allow.

### 5.2. Forks and JVM arguments

When comparing across two JVM configurations, fix or record flags such as:

```text
-Xms
-Xmx
-XX:+UseG1GC
-XX:ActiveProcessorCount=...
```

These are example flags that can affect the environment, **not a recommendation to enable them all**. Change only the flags relevant to your experimental question, and keep JVM options identical when comparing two algorithms.

Never take one measurement on a dev machine and another on a busy CI machine and blame all differences on `Stream`.

## 6. Measurement: iterations, duration, and benchmark modes

JMH supports multiple scoring modes:

| Mode | Typical metric | Question answered |
| --- | --- | --- |
| `Mode.Throughput` | operations/second | How many benchmark calls complete per unit of time? |
| `Mode.AverageTime` | ns/op, µs/op, ms/op | What is the average time per invocation? |
| `Mode.SampleTime` | Sampled latency distribution | What does the call latency distribution look like? |
| `Mode.SingleShotTime` | Time per single invocation | Very long workloads or special single-shot measurements |
| `Mode.All` | Multiple modes | Comprehensive view, though longer total run time |

For a pipeline computing over a fixed array, `Mode.AverageTime` is usually straightforward to interpret:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Measurement(
    iterations = 5,
    time = 1,
    timeUnit = TimeUnit.SECONDS
)
```

When the report prints `us/op`, “op” means **one invocation of the `@Benchmark` method**, not automatically one element in the Stream.

### 6.1. Distinguishing `ns/op` from `ns/element`

Consider a **hypothetical illustrative example**, not real measured output:

```text
Benchmark: summing an array of 10,000 elements
AverageTime: 80,000 ns/op
```

One invocation processes **the entire array**. We can compute a derived figure:

\[
\text{ns/element} = \frac{80,000\ \text{ns/op}}{10,000\ \text{elements/op}}
= 8\ \text{ns/element}.
\]

Yet that division is only an **accounting conversion**: it does not prove each element took 8 ns independently, nor does it separate fixed overhead, cache effects, or scheduling.

If comparing a benchmark processing `N` elements against one processing `1` element where both report `ns/op`, normalize units and goals before drawing conclusions.

## 7. Dead-code elimination: computations can vanish

**Dead-code elimination (DCE)** is a legal compiler/JIT optimization: if a computation has no observable effect and its result is unused, the compiler may remove it.

An easily broken benchmark:

```java
import org.openjdk.jmh.annotations.Benchmark;
import java.util.Arrays;

@Benchmark
public void wrongIgnoredResult() {
    long total = Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();

    // total is never returned, passed out, or used.
    // The JIT may eliminate part or all of the work.
}
```

Assume `data` is an array prepared in state. The method is valid Java syntax, yet **not a reliable measurement design** for summing.

Another error specific to the Stream API:

```java
@Benchmark
public void wrongNoTerminalOperation() {
    Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .map(v -> v * v);

    // No terminal operation: the pipeline never executes
    // filtering and mapping across the data.
}
```

Here **laziness** of Streams also intervenes: building a pipeline does not traverse data. The benchmark may measure only pipeline construction (and even that may be optimized away), **not** the filtering and squaring the author imagined.

### 7.1. Unobserved results can turn a benchmark into a “great-looking” number

If a benchmark discards its result, one variant may look “dramatically faster” simply because the JIT eliminated more of its work. Never compare numbers without verifying *both variants actually executed the same work*.

**Rule:** A measurement must produce an output or observable effect matching the goal, and the harness must keep that output alive so the JIT cannot treat the work as dead code.

## 8. Preventing DCE #1: return the result from `@Benchmark`

This is usually the simplest and preferred approach:

```java
import org.openjdk.jmh.annotations.Benchmark;

@Benchmark
public long streamFilteredSum() {
    return Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();
}
```

JMH consumes the benchmark's return value so the final result is not treated as unused.

Why return `long`?

- The final aggregate is an **observable value**.
- It matches the goal “compute the sum of squares of even numbers”.
- It does not pollute timing with printing logs or file writes.
- It avoids manually updating a shared mutable field.

Returning the result does not force every internal branch to execute literally as written in source; the JIT is still allowed to optimize **while preserving semantic output**. That is desirable: we want to measure JVM-optimized code just as in production, as long as the work and output are genuine.

### 8.1. Do not call `System.out.println` inside invocations

Unsuitable example:

```java
@Benchmark
public void printResult() {
    System.out.println(Arrays.stream(data).sum());
}
```

Measured time is dominated by printing, synchronization, buffering, and output devices. This method does not answer questions about Stream summation performance.

Never use “printing the right number” to defeat DCE in benchmarks; use `return` or `Blackhole`.

## 9. Preventing DCE #2: using `Blackhole`

JMH provides `org.openjdk.jmh.infra.Blackhole`, a value sink designed for benchmarks. The harness can inject it as a parameter to `@Benchmark`:

```java
import java.util.Arrays;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.infra.Blackhole;

@Benchmark
public void consumeWithBlackhole(Blackhole blackhole) {
    long total = Arrays.stream(data)
        .filter(v -> (v & 1) == 0)
        .mapToLong(v -> (long) v * v)
        .sum();

    blackhole.consume(total);
}
```

Use `Blackhole` when a benchmark produces one or more values to consume without naturally returning a single result object. When you only have `long total`, **returning `long` is simpler**.

### 9.1. Do not accidentally measure per-element consumption overhead

Suppose you compare:

```java
@Benchmark
public void perElementConsume(Blackhole blackhole) {
    for (int value : data) {
        blackhole.consume(value);
    }
}
```

This measures **one `consume` per element**, not summing squares of even numbers. If the second variant only calls `consume` once on the final total, the two variants do different measured work.

For a fair comparison:

- Keep **the same business result** for each variant.
- Consume final results in an equivalent way.
- Avoid adding extra `Blackhole.consume` calls in one branch over another unless that cost is what you intend to measure.

### 9.2. `Blackhole` does not replace input/result verification

A meaningless computation fed into `Blackhole` is still a **non-representative** benchmark. `Blackhole` only keeps values observable; it does not prove inputs, behavior, counts, or algorithm correctness.

## 10. Constant folding and synthetic work

DCE is not the only optimization pitfall. **Constant folding** can collapse an invariant expression into a constant:

```java
@Benchmark
public double suspiciousConstant() {
    return Math.sqrt(144.0);
}
```

If the goal is measuring square roots on runtime data, this is unsuitable: the compiler may immediately fold the result to `12.0` or apply constant-specific optimizations.

A version using JMH-supplied data:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class SquareRootBench {
    @Param({"144.0", "275.5", "10000.0"})
    public double input;

    @Benchmark
    public double squareRoot() {
        return Math.sqrt(input);
    }
}
```

`@Param` lets JMH generate input cases and inject values from outside the benchmark method. This prevents naive source-level constant folding and makes multi-case testing convenient.

**However, `@Param` does not randomize data or guarantee eliminating every optimization.** If production processes diverse distributions, select datasets and distributions reflecting real conditions.

## 11. `@State`: managing input data along the benchmark lifecycle

`@State` defines objects holding data or state used by benchmark methods.

```java
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StreamPipelineBenchmark {
    // Each benchmark worker gets its own state instance.
}
```

Common scopes:

| Scope | Meaning | When appropriate |
| --- | --- | --- |
| `Scope.Thread` | Each JMH worker thread gets its own state instance | Measuring algorithms on independent data without unintended contention |
| `Scope.Benchmark` | State is shared across workers in that benchmark | Measuring contention, synchronization, or genuinely shared state |
| `Scope.Group` | State shared within a JMH benchmark group per contract | Modeling multi-role/multi-thread group scenarios |

When comparing summation algorithms on a read-only array, `Scope.Thread` is a sensible default. Switching to `Scope.Benchmark` with a mutable `ArrayList` written by multiple workers could measure a race condition rather than Stream performance.

### 11.1. `@Param` helps test multiple sizes

```java
@Param({"1000", "100000", "1000000"})
public int size;
```

JMH runs every combination of benchmark and `size`. Because source size strongly affects the ratio of **pipeline setup cost / traversal cost**, this is an essential parameter when comparing Streams and loops.

Instead of a blanket claim like “loops are faster than Streams”, you can state a qualified finding:

> “For dataset size N and the measured JDK configuration, approach A achieved lower average time than B under the same workload.”

## 12. `@Setup`: preparing data outside the measured work

When comparing **pure processing cost on an existing array**, allocate and fill the array during setup, not inside every benchmark invocation.

```java
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Setup;

private int[] data;

@Setup(Level.Trial)
public void setUp() {
    data = new int[size];

    for (int i = 0; i < data.length; i++) {
        data[i] = (i * 31 + 7) & 1023;
    }
}
```

With `Level.Trial`, data is prepared once for a JMH trial according to the state's lifecycle, rather than recreated inside the measurement body.

### 12.1. Three setup/teardown levels

| Level | When it runs | Caution |
| --- | --- | --- |
| `Level.Trial` | Once per trial/state lifecycle | Data could be mutated later by benchmark runs |
| `Level.Iteration` | Before each warmup/measurement iteration | Needed if state must reset between iterations |
| `Level.Invocation` | Before each invocation | Can distort measurement targets and add huge coordination overhead |

**Do not use `Level.Invocation` mechanically** to reset data on very short benchmarks. It can change the execution model and ruin measurement accuracy. If state must be restored between calls, reconsider the experiment design or use immutable workloads to avoid this cost.

### 12.2. What if you want to include initialization?

When production genuinely needs to measure **source creation + collection construction + Stream execution** in one request, write a **separate** benchmark including that allocation cost. Never accidentally include setup in one variant while excluding it from another.

**Key question:** Are you measuring *operations on existing data* or *the whole pipeline including source preparation*? Name them as two separate experiments if they are two different questions.

## 13. Complete JMH benchmark: loop, Stream, and parallel Stream

Problem: from an `int[]` array, **keep only even numbers**, compute **squares as `long`**, and sum them as `long`. All three variants must receive **the exact same data** and return **the exact same value**.

Example file: `StreamPipelineBenchmark.java`

```java
package vn.example.bench;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class StreamPipelineBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] data;

    @Setup(Level.Trial)
    public void setUp() {
        data = new int[size];

        // Identical deterministic data for all three variants.
        for (int i = 0; i < size; i++) {
            data[i] = (i * 31 + 7) & 1023;
        }
    }

    @Benchmark
    public long forLoop() {
        long total = 0L;

        for (int value : data) {
            if ((value & 1) == 0) {
                total += (long) value * value;
            }
        }

        return total;
    }

    @Benchmark
    public long sequentialIntStream() {
        return Arrays.stream(data)
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> (long) value * value)
            .sum();
    }

    @Benchmark
    public long parallelIntStream() {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> (long) value * value)
            .sum();
    }
}
```

### Why are the three variants comparable?

- Same `int[]` array and same value distribution.
- Same even-number filter condition: `(value & 1) == 0`.
- Same squaring formula after widening to `long`, preventing `int` overflow during multiplication.
- Same sum output: `long` returned and consumed by the harness.
- No logging, no array reallocation inside benchmark bodies.
- Covers small, medium, and large array sizes.
- Consistent warmup, measurement, and fork configuration.

This example **does not prove** `parallel()` is faster. On small arrays, task-splitting overhead can exceed any gain; on large arrays, results depend on core count, memory bandwidth, per-element work, and environment. The benchmark's purpose is to **measure instead of guessing**.

### 13.1. A calculation must be verified correct before benchmarking

Before trusting JMH numbers, confirm that all three implementations return identical results on small inputs.

For `[1, 2, 3, 4, 5]`, even elements are `2` and `4`, so:

\[
2^2 + 4^2 = 4+16 = 20.
\]

If one variant sums all values, uses `map(value -> value * value)` causing `int` overflow, or changes operation order in a way that alters business results, **timing comparisons are no longer fair**.

When benchmarking financial calculations using decimals, correctness may require `BigDecimal` and rounding rules; when benchmarking `double` sums, rounding error and parallel addition order should be checked with an appropriate tolerance rather than requiring exact bitwise equality in every case.

## 14. Creating a standalone JMH project and running from the command line

JMH is typically run in a **dedicated benchmark project** with JMH dependencies and annotation processors. A convenient approach is the Maven archetype provided by JMH.

Example project creation command (run in an environment with Maven and an appropriate JDK):

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=vn.example \
  -DartifactId=stream-jmh \
  -Dversion=1.0-SNAPSHOT
```

This is an **example configuration for JMH 1.37**, not a claim that it is always the latest release. For real projects, check the JMH version matching your toolchain and dependency policy first.

After generating the project, place the benchmark class in its package, e.g. `src/main/java/vn/example/bench/StreamPipelineBenchmark.java`. Build it:

```bash
mvn clean verify
```

Standard JMH archetypes build an executable uber-JAR, usually `target/benchmarks.jar`. From the project directory, run:

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark
```

If the JAR is named differently by your build config, use the exact artifact produced by Maven; do not assume every project uses the exact same path.

### 14.1. Running with JMH CLI arguments

You can explicitly override warmup/measurement iterations, forks, and JMH worker threads:

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -w 1s -r 1s -f 2 -t 1 \
  -bm avgt -tu us
```

Meaning:

| Flag | Purpose |
| --- | --- |
| `-wi 3` | Three warmup iterations |
| `-i 5` | Five measurement iterations |
| `-w 1s` | One second per warmup iteration |
| `-r 1s` | One second per measurement iteration |
| `-f 2` | Two JVM forks |
| `-t 1` | One JMH worker thread executing the benchmark; does not govern internal tasks of a parallel Stream |
| `-bm avgt` | Average Time |
| `-tu us` | Microsecond time unit |

CLI options can override matching annotations. Record the **actual command executed**, not just annotations in source files.

### 14.2. Measuring allocations with the GC profiler

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -f 2 -t 1 -prof gc
```

The profiler can report metrics such as:

- `gc.alloc.rate`: estimated allocation rate.
- `gc.alloc.rate.norm`: allocated bytes normalized per operation.
- `gc.count`: observed GC cycles.
- `gc.time`: observed GC time.

Available metrics and accuracy also depend on the JVM, JMH, and environment. **Allocated memory (allocation)** does not equal **retained heap** or a memory leak. A benchmark can allocate many short-lived objects without increasing post-GC heap over time.

### 14.3. Exporting reports for later comparison

```bash
java -jar target/benchmarks.jar StreamPipelineBenchmark \
  -wi 3 -i 5 -f 2 -rf json -rff stream-results.json
```

Save alongside the results:

- JDK version and JVM vendor.
- JMH version and build dependencies.
- CPU model, core count, OS, and background load.
- JVM flags, GC, and heap sizing.
- `@Param` settings, warmup, iterations, forks, and threads.
- Commit hash/version of benchmark code and dataset used.

Do not save just a screenshot of one result line and lose track later of whether you are comparing the same workload.

## 15. Reading JMH output: Score, Error, Units, Params

JMH output typically includes columns like:

```text
Benchmark                         (size)     Mode  Cnt    Score    Error  Units
StreamPipelineBenchmark.forLoop     100000    avgt   ...    ...      ...   us/op
StreamPipelineBenchmark.sequentialIntStream ...
StreamPipelineBenchmark.parallelIntStream   ...
```

Meaning:

- **Benchmark**: the measured method.
- **Params**: parameter values for that run, e.g. `size`.
- **Mode**: aggregation mode, e.g. `avgt`.
- **Cnt**: number of samples/iterations aggregated into the report row.
- **Score**: central estimate of the measurement.
- **Error**: statistical error margin reported by JMH; not an absolute guarantee of real-world precision.
- **Units**: reporting unit, such as `us/op` or `ops/s`.

### 15.1. Is lower or higher better?

| Mode | Lower Score | Higher Score |
| --- | --- | --- |
| `AverageTime` | Usually faster per invocation | Usually slower |
| `Throughput` | Fewer operations/second | More operations/second |

Never compare `ns/op` directly against `ops/s` just by looking at which number is larger. They measure opposite directions under potentially different setups.

### 15.2. Overlapping errors and fork-to-fork variance

If two Scores are close and Error margins are large, it is hard to say with confidence which is better from the current run. Inspect:

1. Per-fork and per-iteration raw data.
2. Variance and drift over time.
3. Whether the gap repeats in fresh runs.
4. Whether the benchmark was affected by GC, scheduling, CPU throttling, or contention.
5. Whether the difference has **practical significance** for the product.

**Never draw conclusions from a Score differing by a few percent** when the benchmark fluctuates widely. Statistical error margins do not capture systematic bias from an unrepresentative workload.

## 16. Comparing Streams with loops: keeping the comparison fair

A valid comparison must keep identical:

| Aspect | Verification example |
| --- | --- |
| Source | Same `int[]`; do not compare `ArrayList<Integer>` against `int[]` and blame everything on the API |
| Element count | Same size and value distribution |
| Formula | Same even check, same `long` arithmetic for squares/sums |
| Observed output | Both return the same `long` or consume equivalently |
| Ordering | If business rules require order, both enforce the same constraint |
| Data setup | Both use data prepared in `@Setup` |
| State | Do not let one variant hit a warm cache while the other cold-misses unintentionally |
| JVM | Same JDK/vendor/JVM flags, heap, and GC |
| Environment | Same hardware, background load, and CPU governor |
| JMH config | Same warmup, measurement, forks, threads, and mode |

### 16.1. Boxing is an experimental variable, not mandatory for every Stream

Compare:

```java
// Primitive path: IntStream -> LongStream, avoiding boxing in the core loop.
long primitiveSum = Arrays.stream(data)
    .filter(v -> (v & 1) == 0)
    .mapToLong(v -> (long) v * v)
    .sum();
```

with:

```java
// Object path: boxing, creating Stream<Integer>.
long boxedSum = Arrays.stream(data)
    .boxed()
    .filter(v -> (v & 1) == 0)
    .mapToLong(v -> (long) v * v)
    .sum();
```

Both pipelines compute the same value yet differ in allocation and optimization opportunities. If the question is “`IntStream` vs. loop”, use the primitive Stream. If the question is “how much does boxing cost?”, those two are the exact variants to benchmark separately.

The JIT can eliminate some allocations in specific situations; never assume every element definitely allocates a new `Integer` or that all boxing disappears. Use `-prof gc` and proper profilers for evidence.

### 16.2. `collect(toList())` is different work from `sum()`

```java
var list = Arrays.stream(data)
    .filter(v -> (v & 1) == 0)
    .boxed()
    .toList();
```

This pipeline builds **a result collection**. It cannot be compared against `forLoop()` returning just `long total` to conclude “collect is slower than a loop”: the two programs **do not perform the same function**.

If comparing list-building performance, both the loop branch and the Stream branch must return lists with identical elements and matching ordering/mutability contracts.

## 17. Parallel Streams: what else must be measured?

`parallel()` can help when:

- The source is large enough and `Spliterator` splits work efficiently.
- Each element has enough independent computation.
- Multiple CPU cores are genuinely available.
- `reduce`/`collect` combines accurately at reasonable cost.
- There is no heavy synchronized/atomic contention or costly ordering constraint.

Yet `parallel()` can be **slower** because of:

- Creating and scheduling parallel tasks.
- Splitting the source and merging partial results.
- Memory bandwidth/cache contention.
- Encounter order constraints (`forEachOrdered`, certain `limit`/`distinct` calls).
- Stateful operations like `sorted`, windows, or grouping on hot keys.
- Workloads too small relative to overhead.

### 17.1. `-t 1` does not make `parallelStream()` sequential

In JMH CLI flags, `-t 1` sets **one JMH worker thread calling the benchmark** at a time. Inside that method, `parallelStream()` can still use multiple runtime worker tasks.

Thus inspect:

- **Internal parallelism of the Stream**.
- **Concurrent benchmark calls launched by JMH**.
- **Available CPU cores** and background load.
- Whether other workloads compete for resources.

If measuring service throughput across many concurrent requests, design a separate experiment with multiple JMH workers and an accurate concurrency model. Never extrapolate single-worker results to all multi-user load scenarios.

### 17.2. Never use a shared mutable accumulator to “go faster”

Wrong example:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

Arrays.stream(data)
    .parallel()
    .filter(v -> (v & 1) == 0)
    .forEach(shared::add); // Not thread-safe!
```

This can lose elements or corrupt state. A benchmark that runs fast by **violating correctness** is not a credible result.

Use a properly designed terminal operation/collector such as `toArray`, `sum`, or `collect`; if a concurrent structure is needed, specify its contract clearly and measure contention.

## 18. `Spliterator` and source shape affect performance

The Stream API does not guarantee every source splits efficiently. Much of parallel performance rests on `Spliterator`:

- `trySplit()` can divide elements into independent chunks.
- `SIZED` provides an exact size estimate under contract.
- `SUBSIZED` means child Spliterators also honor size contracts.
- `ORDERED` defines encounter order; preserving order can increase coordination.
- `CONCURRENT` carries specific guarantees regarding concurrent source modification.

When benchmarking `List.stream().parallel()` against `StreamSupport.stream(customSpliterator, true)`, you may be comparing **Spliterator characteristics** rather than just lambdas.

### 18.1. Benchmark source and pipeline separately when needed

If the goal is **data transformation performance** on an existing source, prepare the source beforehand and keep stream creation uniform. If the goal is **I/O reading or data generation performance**, that is a different problem requiring source costs inside the benchmark.

Never sort data in one branch and leave it unsorted in the other unless sorting is the variable under test.

## 19. Distinguishing allocation, heap usage, and memory leaks

In Java, three distinct questions are often lumped into “uses lots of memory”:

| Question | Appropriate metric/method |
| --- | --- |
| How many new bytes does each invocation allocate? | JMH `-prof gc`, especially `gc.alloc.rate.norm` |
| After GC, how many objects remain alive? | Heap profiling, heap dump, retained size |
| Over many hours, how does memory evolve? | Application monitoring, GC logs, long-running soak tests |

For example, `windowSliding(k)` creating window lists and `toList` keeping every window can scale live objects with `N` and `k`; a custom Gatherer computing a sliding sum can retain far less data. Yet a JMH microbenchmark runs within a bounded window and **cannot by itself prove or disprove a long-term system memory leak**.

### 19.1. Zero allocation in a measurement does not mean “never uses memory”

If `gc.alloc.rate.norm` is tiny or zero in a run, it may stem from allocation elimination, escape analysis, or a special workload property. Confirm the benchmark still performs the real work and consumes the result.

A `record`, lambda, or Stream object does not necessarily become a long-lived allocation; the JVM may optimize it away when semantics allow. Conversely, large element counts, boxing, and materialization can push allocations up sharply.

## 20. Operation-level benchmarks vs. system-level benchmarks

Do not use JMH to answer every performance question.

| Question | Method |
| --- | --- |
| Is `IntStream` faster than a loop for summing this array? | JMH microbenchmark |
| Is `groupingBy` or `groupingByConcurrent` faster for this key distribution? | JMH with representative workload, verifying output correctness |
| How long does the log-reading tool take to generate a report? | Realistic end-to-end pipeline benchmark measuring I/O and GC |
| Does the API stay stable at 10,000 requests/minute? | Load test / service benchmark |
| Is transaction P99 latency hurt by contention? | Load test, tracing, profilers, metrics |
| Is there a memory leak after two days of uptime? | Soak test, heap analysis, GC monitoring |

JMH is usually **one layer of evidence**, helpful for narrowing down causes and algorithm choices. System optimization decisions also need metrics on the end-to-end workload.

### 20.1. Be careful with I/O benchmarks

If a benchmark reads `Files.lines(path)`, results depend on OS page cache, filesystem, disk speed, file contents, and stream closing.

To measure **in-memory string processing cost**, prepare `List<String>` in `@Setup`. To measure **actual file reading and processing**, include `Files.lines` and `try-with-resources` inside the measured scope. Never conflate these two experiments into one.

## 21. Designing a verifiable Stream experiment

A practical workflow:

### Step 1 — State a falsifiable hypothesis

Example: “On one million `int`s, a sequential `IntStream` will have measurably different latency from a loop, while parallel Stream speed depends on core count and splitting overhead.”

That is a question to **measure**, not a foregone conclusion.

### Step 2 — Write a correct algorithm first

Test on small, empty, negative, boundary-value, and varied even/odd distributions. Ensure all variants compute the exact same mathematical function.

### Step 3 — Control data and state

Use `@Param` for `size`, `@Setup(Level.Trial)` to build data, and avoid cross-invocation mutation unless mutation is what you are testing.

### Step 4 — Prevent DCE and constant folding

Return the real result from `@Benchmark`, or use `Blackhole.consume` when needed. Never build a lazy pipeline without a terminal operation.

### Step 5 — Configure warmup, measurement, and forks

Pick run lengths long enough to reduce noise, then inspect variance across forks. Record CLI commands and JVM options.

### Step 6 — Read units and uncertainty accurately

Distinguish `us/op` from `ops/s`, inspect Error, raw iterations, and repeatability across runs. Never report per-element speed for a multi-element invocation without explicit conversion.

### Step 7 — Measure allocations and contention too

Use `-prof gc`, CPU/heap profilers, or system tools. If one variant is faster yet allocates far more or contends heavily, weigh system priorities.

### Step 8 — Validate on the real workload

A 10% speedup on an algorithm microbenchmark may not speed up the service by 10% if most time sits in database or network calls. Use whole-system profiling before over-optimizing.

## 22. Common benchmark mistakes

| Mistake | Why it invalidates numbers | Fix |
| --- | --- | --- |
| Calling `System.nanoTime()` once | Dominated by JIT, GC, and noise | Use JMH with warmup/iterations/forks |
| Calling `stream().map(...)` with no terminal operation | Lazy pipeline never runs processing | Add the intended terminal operation and consume output |
| Computing `sum()` and discarding the result | Risks dead-code elimination | Return `long` or use `Blackhole.consume` |
| Benchmarking `Math.sqrt(144.0)` for general sqrt speed | Constant folding | Use controlled runtime inputs |
| Rebuilding inputs inside every invocation in one branch | Measures allocation absent from the other branch | Use `@Setup` or separate benchmarks |
| Timing a few-ns op with `println` | Measures I/O and synchronization | Never print inside benchmarks |
| Using one fork to draw absolute conclusions | Tied to a single JIT state | Run multiple forks for important measurements |
| Zero warmup called “steady state” | JIT has not stabilized | Warm up properly; measure cold start separately |
| Giving Stream `int[]` and loop `List<Integer>` | Mixes source/boxing/cache differences | Keep identical sources when comparing APIs |
| One branch calls `collect(toList())`, the other sums | Non-equivalent work | Measure two distinct functions separately |
| Increasing `-t` without accounting for `parallelStream` workers | CPU oversubscription/contention | Separate JMH threads from Stream parallelism |
| Using shared `ArrayList` in `parallel().forEach` | Data race, wrong results | Use thread-safe terminals/collectors |
| Accidentally sharing mutable `@State(Scope.Benchmark)` | Measures unintended contention | Choose the right Scope |
| Mutating source across invocations | Workload changes over time | Use immutable inputs or proper resets |
| Skipping correctness tests | May benchmark a faster buggy algorithm | Test before benchmarking |
| Comparing Scores with mismatched units | Incomparable quantities | Standardize mode, unit, and workload |
| Looking only at Score, ignoring Error and forks | Easy to mistake noise for signal | Inspect distributions and re-run |
| Calling low allocation “no memory leak” | Confuses allocation with retained heap | Heap profiling / soak tests |
| Concluding faster JMH equals faster system | Microbenchmarks omit other bottlenecks | Validate with system benchmarks / load tests |

## 23. Practice exercises

### Exercise 1 — Spot the DCE bug

A benchmark has:

```java
@Benchmark
public void ignored() {
    long total = Arrays.stream(data).asLongStream().sum();
}
```

Explain two risks: discarding `total` and the compiler potentially eliminating the computation. Rewrite the method returning `long` and also write a `Blackhole` version.

### Exercise 2 — Distinguish a lazy pipeline from executed work

Compare:

```java
@Benchmark
public void buildOnly() {
    Arrays.stream(data).filter(x -> x > 0).map(x -> x * x);
}
```

with:

```java
@Benchmark
public long withTerminal() {
    return Arrays.stream(data)
        .filter(x -> x > 0)
        .mapToLong(x -> (long) x * x)
        .sum();
}
```

Which actually models summing squares of positive elements? Why cannot these be called two equivalent implementations?

### Exercise 3 — Designing warmup and forks

Propose a warmup, measurement, and fork configuration for an operation taking around microseconds per invocation. Explain why you must inspect result stability before concluding rather than trusting fixed magic numbers.

### Exercise 4 — Sweeping data sizes

Add `@Param({"100", "1000", "100000", "1000000"})` to a benchmark. Predict how Stream's fixed setup overhead ratio behaves when `N` is small, and test your prediction with actual measurements.

### Exercise 5 — Comparing primitive vs. boxed Streams

Write two benchmarks computing the sum of squares of even numbers: one using `Arrays.stream(data)` directly, one using `boxed()`. Both return the same `long`. Use `-prof gc` to check whether allocations differ.

### Exercise 6 — Is replacing `sum()` with `collect()` fair?

Someone compares `IntStream.sum()` against `Stream<Integer>.collect(toList())` and concludes `collect` is inefficient. Point out the difference in **required output** and design a fairer comparison.

### Exercise 7 — Reading hypothetical JMH results

Two **hypothetical** measurements score:

```text
A: 100 ± 15 us/op
B: 105 ± 16 us/op
```

Can you conclude with certainty that B is slower than A? What additional details (forks, iterations, workload, environment) should you check before proposing a production change?

### Exercise 8 — Measuring `parallel()` on small and large inputs

For `int[]` arrays of 1,000 and 1,000,000 elements, benchmark sequential and parallel runs. Explain why results can invert with size; discuss Spliterator roles, task coordination, and memory bandwidth.

### Exercise 9 — Multi-request throughput goal

If a system serves 32 concurrent requests, does `-t 1` reflect real load conditions? Propose a follow-up benchmark with multiple JMH workers, specifying whether data is shared and considering parallel Stream oversubscription.

### Exercise 10 — Distinguishing allocation from memory leaks

A report shows high `gc.alloc.rate.norm` while post-GC heap remains flat. Is that enough evidence to conclude a memory leak? What additional tests or metrics are needed?

### Exercise 11 — Keeping results verifiable

Write a pure Java 17 function taking `int[]` and returning the sum of squares of even numbers. Write a simple test on `[1,2,3,4,5]` expecting `20L`. Use that same function or rule in JMH to verify Stream and loop variants return identical results.

### Exercise 12 — Designing a benchmark for `groupingBy`

Given one million transactions with skewed region keys, propose a benchmark comparing `groupingBy` and `groupingByConcurrent`, including both in parallel pipelines. What must you verify regarding correctness, hot keys, order, merge cost, and contention?

### Exercise 13 — File-reading benchmarks

A benchmark calls `Files.lines(path)` on a file already cached in the OS. Does this represent a server reading cold files from physical disk? Separate the questions: in-memory string processing, reading from page cache, and reading from actual storage hardware.

## 24. Self-check knowledge questions

- Why is a single `System.nanoTime()` timing unreliable under JIT compilation?
- What is the difference between warmup iterations, measurement iterations, and JVM forks?
- Is increasing forks the same as increasing thread count `-t`?
- Why can warmup not automatically fix a benchmark broken by DCE?
- When should a `@Benchmark` return its result?
- What does `Blackhole.consume` protect against and what are its limits?
- Why does calling `stream().map(...)` without a terminal operation fail to measure full-source transformation?
- How can constant folding distort a measurement's intent?
- What are the roles of `@State`, `@Param`, and `@Setup(Level.Trial)`?
- When do you use `Scope.Thread` vs. `Scope.Benchmark`?
- In JMH, is one `op` one Stream element or one method invocation?
- How do `avgt` and `thrpt` differ? Which direction is better for each?
- Why inspect `Error` and multi-fork results?
- How do you compare `IntStream` with a loop without mixing source/boxing differences?
- How does `-prof gc` reveal allocations, and why is it insufficient to prove a leak?
- Why can `parallelStream()` be slower than sequential execution?
- Does `-t 1` force `parallel()` code to run sequentially?
- When is a small Stream microbenchmark insufficient evidence to optimize an entire service?
- Why verify correctness before measuring performance?

## 25. References

- [OpenJDK — JMH](https://github.com/openjdk/jmh): source code, harness usage guide, Maven archetypes, and runner options.
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): official examples on dead-code elimination, Blackhole, state, forks, warmup, benchmark modes, and measurement.
- [JMH `JMHSample_08_DeadCode`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): demonstrates how unused values can be eliminated by the JIT.
- [JMH `JMHSample_09_Blackholes`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): demonstrates return values and Blackhole consumption.
- [JMH `JMHSample_10_ConstantFold`](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): demonstrates constant folding.
- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): laziness, pipeline characteristics, side effects, and terminal operations.
- [Java SE 17 — `IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): primitive processing and terminal operations `sum`, `average`, `summaryStatistics`.
- [Java SE 17 — `Spliterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): splitting mechanics and characteristics supporting parallel Streams.

**Key takeaway:** A solid JMH benchmark must **measure the right work**, **keep results observable**, **warm up the JVM**, **repeat across multiple iterations and forks**, and **hold comparison conditions constant**. With the Java Stream API, especially remember that **intermediate operations are lazy**, `map`/`filter` do not run without a terminal operation, boxing/`collect` change the workload, and `parallel()` carries overhead. Return results or use `Blackhole` to prevent DCE, read `Score/Error/Units` accurately, inspect allocations/GC when needed, and treat microbenchmarks as just one source of evidence for performance decisions.
