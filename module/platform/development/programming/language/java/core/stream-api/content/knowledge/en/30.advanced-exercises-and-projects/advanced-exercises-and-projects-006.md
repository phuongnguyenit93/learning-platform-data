# Measuring and Explaining the Performance of Three Approaches to the Same Problem

A **Java Stream API** solution can be concise, readable, and semantically accurate, yet that **does not automatically prove it is faster** than a traditional loop. Likewise, adding `parallel()` does not guarantee a speedup: splitting the source via `Spliterator`, task scheduling, result merging, memory pressure, and workload size all influence runtime.

This advanced hands-on lesson guides you through designing **a reproducible experiment** comparing **three ways to solve the same problem**: a `for` loop, a sequential stream, and a parallel stream. The goal is not to declare one approach the universal winner, but to **measure properly, verify identical outputs, and explain why speed changes** across data sizes and computational intensity.

This is part of the **Advanced Exercises and Projects** chapter of the `JAVA_STREAM_API` module, connecting lazy pipelines, `filter`, `mapToLong`, `sum`/`reduce`, primitive streams, Spliterators, and the performance limits of parallel streams.

## 1. Project Prompt and Completion Criteria

Given an `int[] data` array, consider only **even** elements. For each selected element, apply a deterministic integer transformation `score(value, rounds)`, then **sum all scores** into a `long`.

Implement and compare three approaches:

1. **Imperative loop:** a `for` loop iterating over the array, checking parity, computing scores, and summing results.
2. **Sequential stream:** `Arrays.stream(data).filter(...).mapToLong(...).sum()`.
3. **Parallel stream:** the same pipeline with `parallel()` enabled so the array can be split across workers.

All three versions must use **the same data, the same `score` function, the same filter predicate, and the same summation type**. Never give one version less work and conclude it is faster.

### Deliverables

| Deliverable | Objective |
| --- | --- |
| Three Java methods | Same problem, readable, no shared mutable state. |
| Correctness verification | All three return the exact same sum across multiple sizes and edge cases. |
| JMH benchmark | Includes warm-up, measurement, forks, and result consumption. |
| Results table | Explicitly records `n`, computation rounds, time units, and runtime environment. |
| Analysis | Explains overhead, source splitting, JIT, CPU, GC, and scalability. |
| Scoped conclusion | Identifies the suitable choice for the measured workload without overgeneralizing. |

## 2. Defining a Computation So All Three Solutions Are Truly Equivalent

Choose a **pure** computation function: it depends solely on `value` and `rounds`, without reading clocks, performing I/O, or mutating global state. In this example, each loop mixes the bits of a `long` value and masks the low 16 bits so the score falls within `[0, 65_535]`.

```java
static long score(int value, int rounds) {
    long x = Integer.toUnsignedLong(value)
        + 0x9E3779B97F4A7C15L;

    for (int i = 0; i < rounds; i++) {
        x ^= x >>> 30;
        x *= 0xBF58476D1CE4E5B9L;
        x ^= x >>> 27;
        x *= 0x94D049BB133111EBL;
        x ^= x >>> 31;
    }
    return x & 0xFFFFL;
}
```

The `long` multiplications can wrap under Java's 64-bit integer rules; here that is **intentional for bit mixing**, not an arithmetic precision requirement on a monetary total. Each `score` result is non-negative and at most 65,535. For an array of up to one million elements, the maximum possible sum is `65_535_000_000L`, safely within `long` bounds.

The `rounds` parameter controls **work per element**:

- `rounds = 4`: relatively light transformation; pipeline setup and splitting overhead can represent a significant fraction.
- `rounds = 64`: more operations per element; parallelization overhead has a chance to pay off.

This function **simulates CPU load for measurement**, not a cryptographic algorithm or statistically vetted hash function. Do not use it to generate security tokens.

## 3. Implementing All Three Approaches in One Class

The complete example below uses Java 8+. Every method receives **the exact same array** and does not mutate the source data.

```java
package example;

import java.util.Arrays;

public final class ThreeWays {
    private ThreeWays() {}

    public static long score(int value, int rounds) {
        long x = Integer.toUnsignedLong(value)
            + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < rounds; i++) {
            x ^= x >>> 30;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 27;
            x *= 0x94D049BB133111EBL;
            x ^= x >>> 31;
        }
        return x & 0xFFFFL;
    }

    // Approach A: direct, sequential loop.
    public static long loop(int[] data, int rounds) {
        long total = 0L;
        for (int value : data) {
            if ((value & 1) == 0) {
                total += score(value, rounds);
            }
        }
        return total;
    }

    // Approach B: sequential Stream pipeline.
    public static long sequentialStream(int[] data, int rounds) {
        return Arrays.stream(data)
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> score(value, rounds))
            .sum();
    }

    // Approach C: identical pipeline allowing parallel execution.
    public static long parallelStream(int[] data, int rounds) {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> score(value, rounds))
            .sum();
    }

    public static int[] makeInput(int size) {
        if (size < 0 || size > 1_000_000) {
            throw new IllegalArgumentException("size out of test range");
        }
        int[] result = new int[size];
        for (int i = 0; i < size; i++) {
            result[i] = i * 37 + 11; // Deterministic data, no RNG needed.
        }
        return result;
    }

    public static void main(String[] args) {
        int[] data = makeInput(10_000);
        int rounds = 64;

        long a = loop(data, rounds);
        long b = sequentialStream(data, rounds);
        long c = parallelStream(data, rounds);

        System.out.println("loop     = " + a);
        System.out.println("sequence = " + b);
        System.out.println("parallel = " + c);

        if (a != b || a != c) {
            throw new AssertionError("Three results do not match");
        }
    }
}
```

**Why is this comparison fairer than many ad-hoc benchmarks?**

- **Single `score` algorithm:** all three invoke the same function; no branch swaps in a lighter calculation.
- **Single filter predicate:** `(value & 1) == 0` identifies even numbers across all `int` values.
- **Primitive streams:** `Arrays.stream(int[])` yields an `IntStream` and `mapToLong` yields a `LongStream`, avoiding unnecessary boxing to `Integer`/`Long`.
- **Identical sum type:** every version accumulates into `long`. Within the data bounds above, the sum never overflows `long`.
- **No side effects:** element processing is independent; `parallel()` shares no external `ArrayList` or mutable counter.
- **Fixed input:** `makeInput` does not depend on wall-clock time or an unrecorded seed.

Do not treat `main` printing three equal sums as full proof of correctness. You must also test empty arrays, all-odd arrays, all-even arrays, negative values, single-element arrays, and larger sizes.

## 4. Understanding What Each Approach Actually Does

### A. The `for` Loop

The loop executes filtering and summation directly over the array. It typically has low startup overhead, requires no Stream pipeline objects, and spawns no fork/join tasks.

**Never assume** a loop is always faster than a stream: the JVM can inline lambdas, optimize primitive streams, and apply JDK-specific optimizations. Speed differences can only be concluded by measuring a specific workload.

### B. Sequential Stream

```java
Arrays.stream(data)
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> score(value, rounds))
    .sum();
```

`filter` and `mapToLong` are **lazy intermediate operations**. `sum()` is the terminal operation triggering traversal; pipelines are typically fused so each element flows through stages without materializing intermediate lists.

When `n` is small, pipeline setup and abstraction calls can be noticeable compared to a loop. When `score` dominates runtime, that relative overhead usually shrinks.

### C. Parallel Stream

```java
Arrays.stream(data)
    .parallel()
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> score(value, rounds))
    .sum();
```

`parallel()` does not spawn a separate thread for **each element**. The framework uses the array's Spliterator to split work; worker tasks process slices and combine partial sums. Integer addition within `long` bounds fits parallel reduction cleanly.

Additional costs can include **source splitting, scheduling, result synchronization, memory traffic, and CPU contention**. With few elements and a light `score`, these costs easily outweigh any benefit. With sufficiently large data and spare CPU cores, parallel execution can win.

## 5. Before Timing: Verify Equivalence

A benchmark is meaningful only when comparing solutions that produce **the exact same business result**. For this project, verify:

| Case | What to Verify |
| --- | --- |
| Empty array | All three return `0L`. |
| Single even element | All three return `score(value, rounds)`. |
| Single odd element | All three return `0L`. |
| Negative values or `Integer.MIN_VALUE` | Consistent parity check; no casting bugs. |
| Multi-element datasets | Identical sum, no dropped or double-counted elements. |
| Varying `rounds` | All three match under each configuration. |
| Repeated runs on same data | Sum is independent of worker scheduling. |

Simple Java 8+ check without needing a test framework:

```java
package example;

import java.util.Arrays;

public class ThreeWaysCheck {
    static void check(int[] data, int rounds) {
        long expected = ThreeWays.loop(data, rounds);
        long actualSequential =
            ThreeWays.sequentialStream(data, rounds);
        long actualParallel =
            ThreeWays.parallelStream(data, rounds);

        if (expected != actualSequential || expected != actualParallel) {
            throw new AssertionError(
                "Mismatch for input " + Arrays.toString(data)
            );
        }
    }

    public static void main(String[] args) {
        for (int rounds : new int[] {4, 64}) {
            check(new int[] {}, rounds);
            check(new int[] {2}, rounds);
            check(new int[] {3}, rounds);
            check(new int[] {-4, -3, 0, Integer.MIN_VALUE}, rounds);
            check(ThreeWays.makeInput(1_000), rounds);
        }
        System.out.println("All test cases matched");
    }
}
```

This is a **correctness check**, not a performance benchmark—nor is it an exhaustive test suite. Keep correctness assertions separate from timed code so you do not accidentally measure assertion, array creation, or logging overhead.

## 6. Why Not Draw Conclusions from a Single `System.nanoTime()` Call?

A one-off measurement:

```java
long start = System.nanoTime();
long result = ThreeWays.parallelStream(data, 64);
long duration = System.nanoTime() - start;
```

can give a rough sanity check, yet is **insufficient** to conclude which approach is optimal. Timings fluctuate due to:

- **JIT compilation:** the JVM needs warm-up invocations before optimizing hot code; the first run does not represent steady-state execution.
- **Dead-code elimination:** if a program ignores the computed result, the compiler may optimize away part of the work.
- **Garbage collection:** sporadic allocations and GC pauses can skew a single measurement.
- **Scheduling:** the OS or background processes preempting CPU cores alter latency.
- **Dynamic frequency / thermal throttling:** CPU clock speed is not always constant, especially under sustained load.
- **JVM and environment:** JDK version, core count, heap size, and container limits all affect results.

Additionally, timing `makeInput` alongside processing mixes **data-preparation cost** into the three algorithms' costs. Measuring end-to-end cost can also be valuable when requested, provided it is labeled clearly and applied **consistently** across all approaches.

## 7. Benchmarking with JMH

**JMH (Java Microbenchmark Harness)** is a toolkit designed for measuring Java operations while accounting for warm-up, repeated measurements, JVM forks, and JIT optimizations. JMH is not built into the JDK; it requires a **JMH project configured with compatible libraries and annotation processing**.

Typically, a Maven JMH project uses `org.openjdk.jmh:jmh-core` alongside `org.openjdk.jmh:jmh-generator-annprocess` of the **same version**. You can generate the project structure via the JMH Maven archetype or equivalent setup. Never manually call `System.nanoTime()` inside a `@Benchmark` method.

Place the following class in your JMH-configured project in package `example` alongside `ThreeWays`:

```java
package example;

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
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
@Threads(1)
public class ThreeWaysBenchmark {

    @Param({"1000", "1000000"})
    public int size;

    @Param({"4", "64"})
    public int rounds;

    private int[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = ThreeWays.makeInput(size);
    }

    @Benchmark
    public long imperativeLoop() {
        return ThreeWays.loop(data, rounds);
    }

    @Benchmark
    public long sequentialStream() {
        return ThreeWays.sequentialStream(data, rounds);
    }

    @Benchmark
    public long parallelStream() {
        return ThreeWays.parallelStream(data, rounds);
    }
}
```

### Why Structure the Benchmark This Way?

| Setting | Purpose |
| --- | --- |
| `@State(Scope.Benchmark)` | Holds shared input data for the benchmark run; the array is read-only so there is no write contention. |
| `@Setup(Level.Trial)` | Builds input **outside the timed section**. |
| `@Param({"1000", "1000000"})` | Tests small and large sources, avoiding conclusions from one `n`. |
| `@Param({"4", "64"})` | Tests light and heavy computation on the same algorithm. |
| `@Warmup` | Gives the JVM a chance to JIT-compile hot paths before measurement iterations. |
| `@Measurement` | Collects multiple independent measurements as configured. |
| `@Fork(2)` | Runs across multiple JVM processes to reduce single-startup bias. |
| `@Threads(1)` | Only one thread **calls the benchmark method** at a time; internally `parallelStream()` can still use multiple workers. |
| Returning `long` from `@Benchmark` | JMH consumes the return value, preventing dead-code elimination. |

Each parameter combination creates a separate benchmark case. Here, **stream creation and the terminal operation are both included in the timed scope**: that reflects the cost of invoking a pipeline in a real application. Array allocation is excluded because the goal is comparing three ways of **processing an existing input**.

JMH neither proves a computation is correct nor guarantees the fastest behavior in production. It simply yields far more reliable numbers than a one-off measurement when properly configured and run.

### Running and Exporting Results

With a Maven JMH project configured to build `target/benchmarks.jar`, run:

```text
java -jar target/benchmarks.jar ThreeWaysBenchmark -rf csv -rff results.csv
```

To also observe memory allocation and GC activity, JMH offers a built-in profiler:

```text
java -jar target/benchmarks.jar ThreeWaysBenchmark -prof gc
```

These commands are **instructions for your JMH project**, not results from a benchmark already executed in this lesson. Depending on build configuration, JAR naming and annotation processor setup may vary; use your project's actual runner. Measure on a relatively quiet machine, minimize background load, and record JDK version, CPU, RAM, OS, and system load.

## 8. Reading the Results Table and Calculating Speedup

In `Mode.AverageTime`, JMH reports average time per invocation (*time/op*); **smaller is faster**. In `Mode.Throughput`, units are operations per unit time; **larger is faster**. Never divide metrics from different modes without converting units.

Table template to fill in **after running the benchmark yourself**:

| `size` | `rounds` | Loop (µs/op) | Sequential (µs/op) | Parallel (µs/op) | Fastest Approach |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1,000 | 4 | Fill measured value | Fill measured value | Fill measured value | Determine after run |
| 1,000 | 64 | Fill measured value | Fill measured value | Fill measured value | Determine after run |
| 1,000,000 | 4 | Fill measured value | Fill measured value | Fill measured value | Determine after run |
| 1,000,000 | 64 | Fill measured value | Fill measured value | Fill measured value | Determine after run |

**No fabricated measurements are pre-filled here.** Every timing entry must come from an actual benchmark run; never fill in numbers based on an expectation that parallel will be faster.

To express speedup between two approaches, use:

\[
\text{Speedup} = \frac{\text{Baseline method time}}{\text{New method time}}
\]

As a **hypothetical illustration of the formula**, not a project measurement: if one method takes 24 ms and another takes 8 ms on the same input, speedup is `24 / 8 = 3`, or roughly **3x**. That speedup does not imply exactly three cores were utilized, nor does it prove memory cost stayed flat.

When evaluating measurements, inspect variance (confidence intervals or spread across forks/iterations), not just the fastest single sample. Differences smaller than measurement noise are not enough evidence to declare one approach faster.

## 9. Explaining Results Across Three Scenarios

### Scenario A: Small Input, Light `score`

With `size = 1_000`, `rounds = 4`, useful computation is tiny. Relative overhead that may dominate includes:

- Creating pipeline objects and traversal machinery for streams.
- Creating and coordinating parallel tasks.
- Merging partial results for `sum`.

The imperative loop will often win here. If actual measurements show otherwise, inspect noise, JIT optimizations, benchmark accuracy, and hardware characteristics **before dismissing the numbers**.

### Scenario B: Large Input, Heavy `score`

With `size = 1_000_000`, `rounds = 64`, most runtime is spent in the CPU-bound transformation. `int[]` has a Spliterator that splits cleanly by index, each element is independent, and summation is associative. Thus the parallel stream has a **real chance** to beat both sequential approaches on a machine with spare CPU cores.

Still, speedup does **not scale linearly forever with core count**. Splitting/merging overhead, memory bandwidth contention, OS load, turbo/thermal limits, and non-parallelizable work all cap gains.

### Scenario C: Large Input, Cheap Transformation

With `size = 1_000_000`, `rounds = 4`, per-element computation may not be heavy enough to offset splitting overhead. Measurements may show the loop or sequential stream competing closely with parallel execution.

The key insight is **never look only at element count; also consider work per element**. That is why the benchmark varies both `size` and `rounds` instead of testing a single configuration.

## 10. Spliterator and Task Granularity Explain Part of Performance

Parallel streams are coordinated via `Spliterator`: `trySplit` hands out sub-ranges, while `estimateSize` and `characteristics` guide splitting and optimizations. `Arrays.stream(int[])` has favorable properties for index-range splitting; not every source does.

| Source | Traits Affecting Benchmarks |
| --- | --- |
| `int[]`, `IntStream.range` | Exact size known, usually splits evenly. |
| `ArrayList` | Indexed access, relatively favorable for splitting. |
| `LinkedList` | Traversal and splitting have very different cost characteristics from arrays. |
| `Stream.iterate` | Recurrence sequence with state dependency, unlike independent indexed work. |
| `Files.lines` | Involves I/O, requires resource closing, and splitting depends on the backing reader. |
| Custom source with `trySplit() == null` | Poor parallel utilization because work cannot be split. |

Never "optimize" by falsely declaring `SIZED`/`SUBSIZED` on a custom Spliterator. Characteristics are **semantic contracts**, not unconditional speedup hints.

If a real workload consists of unevenly sized groups, consider splitting large groups into **chunks** and parallelizing by chunk. Never blindly nest `parallelStream()` inside both outer and inner loops; that can explode task counts, pool contention, and latency without adding CPU cores.

## 11. Why Not Compare `Stream<Integer>` Against `int[]` in the Main Experiment?

If the loop scans `int[]` while the stream processes `List<Integer>` with `map` and `reduce`, the experiment changes **data layout and boxing/unboxing cost**. Results would reflect `Integer` wrapper overhead more than differences between loops and the Stream API.

In this lesson, all three start from **the exact same `int[]`** and use primitive values. You can run a separate **side experiment**:

```java
long total = boxedValues.stream()
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> ThreeWays.score(value, rounds))
    .sum();
```

When reporting the side experiment, explicitly state the input is `List<Integer>` and note whether `boxedValues` construction time is excluded or included. Never mix measurements from two different data types to claim "Streams are always slower than loops".

## 12. Watch Out for Arithmetic, State, and Aggregation Rules

The three project pipelines produce bounded `score` values, sum into `long`, and leave the source untouched. If you change the problem, correctness conditions can shift:

| Change | Risk | Mitigation |
| --- | --- | --- |
| Using `int` for huge sums | `int` overflow—fast measurement, wrong result. | Use `long` before adding or check for overflow. |
| Using `double` and comparing with `==` | Floating-point rounding; parallel order may shift last bits. | Define tolerance; note merge order sensitivity. |
| Calling `Math.random()` in mapper | Runs are non-reproducible. | Fix dataset and seed; never share generator state carelessly. |
| Writing to external `ArrayList` in `parallel().forEach` | Contention, dropped or duplicate elements. | Use `collect` or a valid reduction. |
| Using a non-associative `reduce` | Result depends on split/merge tree. | Choose a combiner with a lawful identity and associativity. |
| Mutating source array during measurement | Iterations no longer see identical inputs. | Keep input immutable throughout the benchmark session. |
| Calling network or DB APIs in `score` | Benchmark dominated by I/O, timeouts, and connection limits. | Design a dedicated I/O benchmark with explicit concurrency control. |

An operation can be **very fast yet semantically wrong**, especially with side effects or dropped elements. Correctness is always a prerequisite before evaluating speed.

## 13. Analyzing Memory Allocation, GC, and Latency

Time/op is not the only dimension of performance. Also examine:

1. **Allocation rate:** bytes/op or bytes/sec from JMH's GC profiler; does using a pipeline raise allocations significantly?
2. **Garbage collection:** do GC counts and pause times affect forks?
3. **CPU utilization:** does the parallel stream genuinely utilize multiple cores, or is it bottlenecked by an unsplittable source?
4. **Latency variance:** are runs consistent, especially when concurrent requests share the common pool?
5. **Memory bandwidth/cache:** multiple workers scanning arrays simultaneously can contend on memory bandwidth.

In the standard example, we use primitive streams, `filter`, `mapToLong`, and `sum`, so **no intermediate `List<Long>` holding all elements is created**. Even so, streams may allocate pipeline objects or internal fork/join tasks; a benchmark may reveal allocation differences even without per-element boxing.

Separate **single-invocation latency** from **application-wide throughput**. A `parallelStream()` call might finish sooner in isolation, while many concurrent requests competing for CPU/pool resources can degrade throughput or p99 latency. That is a different test from JMH `@Threads(1)` and should be reported separately.

## 14. Experiment Report Structure

A solid report can follow this outline:

### A. Environment and Measurement Setup

```text
JDK:                <actual version>
CPU / logical cores:<machine info>
RAM / heap limit:   <actual info>
OS:                 <operating system>
JMH:                <project version>
Benchmark mode:     AverageTime, microseconds/op
Warm-up:            3 iterations x 1 second
Measurement:        5 iterations x 1 second
Forks:              2
JMH calling threads:1
Inputs:             size = 1000 / 1000000
                    rounds = 4 / 64
```

This is a **reporting template**, not a machine configuration observed in this lesson. Practitioners must fill in real environment details in place of placeholders.

### B. Results and Correctness

Record a time/op table by `size`, `rounds`, and approach name, including variance. Document how you verified all three approaches produce identical sums. If any discrepancy appears, **halt performance conclusions** and investigate semantics first.

### C. Evidence-Based Explanation from Measurements

For each configuration, ask:

- Are there few or many elements? Is `score` cheap or expensive?
- Do pipeline setup, source splitting, and merging account for a large share?
- Does JMH show high variance across iterations or forks?
- Are CPU, GC, or memory showing bottlenecks?
- Why did one approach win in one configuration yet lose in another?

### D. Conclusions and Limitations

Never write "`parallelStream` is N times faster" unless N was actually measured. State a scoped conclusion: **on the tested JDK, hardware, data, and load**, approach X performed better or approaches showed no meaningful difference. Note conditions that could flip the conclusion.

## 15. Extending the Project Beyond the Basic Comparison

### Extension 1 — Data Size and Break-Even Threshold

Add intermediate `size` values such as `10_000`, `100_000`, and `500_000`. Observe where parallel streams begin competing with sequential execution. The **break-even threshold** varies across machines and `rounds` values.

### Extension 2 — Object Sources and Boxing

Keep the same problem but switch the array to `List<Integer>`. Compare `Stream<Integer>` with `IntStream`. Record boxed-data setup separately and watch GC effects.

### Extension 3 — Simulating Concurrent Requests

Benchmark multiple concurrent invocations running at the same time. Observe throughput and p95/p99 rather than single-call latency alone. Never infer multi-request production behavior solely from `@Threads(1)`.

### Extension 4 — Skewed Group Data

Replace a flat array with batches of uneven sizes. Compare a parallel pipeline per batch, a flattened pipeline, and chunked splitting. Avoid assuming nested two-level parallelism is optimal.

### Extension 5 — Multi-Metric Statistics Instead of a Single Sum

Replace `sum` with `summaryStatistics` or `Collectors.summarizingLong` to compute count/sum/min/max/average. When multiple metrics are needed, compare **one combined aggregation** against multiple independent pipelines, ensuring identical total work and proper empty-data handling.

## 16. Self-Assessment Exercises

1. **Correctness before speed:** Why verify outputs across all three approaches before benchmarking? Give an example where a parallel stream runs fast yet returns wrong results due to shared mutable state.
2. **Small data:** Why can `size=1000` and `rounds=4` make a parallel stream slower than a loop?
3. **Splittable sources:** What roles do `Spliterator.trySplit`, `SIZED`, and array source traits play in parallel processing?
4. **Measurement methodology:** Explain `@Warmup`, `@Fork`, `@Param`, `@Threads(1)`, and why `@Benchmark` methods return `long`.
5. **Two metric types:** Distinguish latency/time-op from throughput. Why might a method that is faster in single-call tests fail to improve throughput under high load?
6. **Scoped analysis:** Suppose measurements show parallel clearly winning at `size=1_000_000, rounds=64` while losing at `size=1000, rounds=4`. Write a conclusion without overgeneralizing.
7. **Range check:** Can the `long` sum in this example overflow on the largest array created by `makeInput`? Use the upper bounds of `score` and `size` to explain.
8. **Workload redesign:** If data lives across many files and most time is spent waiting on I/O, why is this lesson's CPU-bound benchmark insufficient justification for applying `parallelStream()` to file reading?

## 17. Project Completion Checklist

- [ ] All three approaches use identical inputs and `score`, differing only in traversal style and parallelism.
- [ ] The source array is never modified during benchmarking.
- [ ] Empty, small, negative, and large test cases are verified for correctness.
- [ ] JMH runs with appropriate warm-up, measurement iterations, and forks.
- [ ] Values returned from each `@Benchmark` are consumed by JMH.
- [ ] Data-generation time is excluded or accounted for consistently with the measurement goal.
- [ ] Results tables clearly specify size, rounds, units, and variance.
- [ ] Explanations cover overhead, JIT, Spliterator, CPU/GC, and limits of parallelism.
- [ ] No **hypothetical** numbers are presented as actual benchmark measurements.
- [ ] Conclusions explicitly state the target environment and experimental limits.

**Key takeaway:** Good performance measurement does not begin by adding `parallel()`, but by **defining the problem precisely, building equivalent solutions, and verifying outputs**. Use JMH to observe all three approaches across multiple sizes and CPU intensities, then explain results in terms of pipeline overhead, Spliterator splitting, reduction mechanics, hardware resources, and JVM variance. Pick an approach only **within the scope of measured evidence**, rather than treating one benchmark pattern as a universal rule for the entire Java Stream API.
