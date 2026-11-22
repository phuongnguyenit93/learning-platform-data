# Fairly Comparing Loops, Sequential Streams, and Parallel Streams

## Objectives

In the Java Stream API, three ways of processing the same dataset are often placed side by side: a `for` loop, a **sequential Stream**, and a **parallel Stream** (`parallelStream()` or `parallel()`). The question “which one is faster?” only makes sense when they perform **the exact same work**, run under equivalent measurement conditions, and are evaluated with appropriate metrics. This lesson in the **Performance and Memory** chapter guides you through designing a verifiable comparison, reading results, and deciding when to use each approach.

After this lesson, you will be able to:

- Distinguish traversal cost, pipeline cost, and task splitting/merging cost across the three approaches.
- Build a fair benchmark using **JMH (Java Microbenchmark Harness)** and avoid false conclusions from a single `System.nanoTime()` run.
- Evaluate runtime, throughput, memory allocation, and the impact of data size, per-element work, and CPU core count.
- Recognize cases where outputs differ due to semantics, such as ordering, non-associative operations, or side effects.

## 1. Where do the three approaches actually differ?

| Approach | Mechanism | Notable overhead | Usually suited for |
| --- | --- | --- | --- |
| `for` loop | Traverses data and executes conditions/calculations directly | Low loop overhead; can be optimized very well by the JIT | Short hot paths, small datasets, performance-sensitive sections |
| Sequential Stream | Builds a `filter` → `map` → terminal operation pipeline; runs only on a terminal operation | Pipeline setup, stage invocation/composition; optimization level depends on JVM and workload | Readable data transformations, clear composition of operations |
| Parallel Stream | Uses `Spliterator` to split input, processes chunks via Fork/Join, then merges results | Splitting work, scheduling, synchronization/merging, CPU contention, potential extra allocations | Large enough data, easily splittable, independent CPU-heavy work, efficient merging |

`parallel()` **is not guaranteed to be faster** than `sequential()`. For a few hundred elements, task coordination time can exceed computation time. For millions of elements with CPU-heavy work, multiple cores can bring benefits. Still, outcomes depend on hardware, source splitting, per-element complexity, memory locality, GC state, and system load.

Distinguish **latency** (how long one execution takes) from **throughput** (how many operations or elements complete per second). A parallel Stream might lower latency for one large request while occupying more cores, reducing whole-application throughput when many requests run concurrently.

## 2. Conditions for a fair comparison

Before measuring, state the problem and record these conditions:

1. **Same input.** Use the same array, element count, value distribution, and data state; do not make one variant read a file or generate data while another computes on a ready array.
2. **Same result and semantics.** All three must filter, transform, and aggregate the same elements. If order is required, compare order-preserving variants; do not compare `findFirst()` in one against `findAny()` in another and draw performance conclusions.
3. **Same data types.** Compare a loop on `int[]` against `IntStream`, avoiding accidental comparison against boxed `Stream<Integer>`. If you want to measure boxing cost, design a separate experiment.
4. **Same timed scope.** Measure only the work under study. Array creation, random number generation, logging, `println`, result validation, and app startup belong outside the measured section unless part of the problem.
5. **JIT warmup and multiple samples.** The JVM needs warmup to compile, inline, and optimize code; first-run timing does not represent steady state. Use multiple iterations and multiple JVM forks.
6. **Controlled environment.** Use the same JDK, JVM flags, heap size, machine, CPU/cgroup limits, and background load. Record logical cores visible to the JVM and avoid running competing CPU benchmarks concurrently.
7. **Measure multiple sizes and computation weights.** For example 1,000, 100,000, and 1,000,000 elements; test light and heavy work in separate experiments. The crossover point where parallel Streams pay off is not fixed.
8. **Measure resources too.** Beyond `ms/op`, monitor `B/op`, GC, CPU usage, and run-to-run variance. Shorter runtime using far more memory or cores may not fit production systems.

**Note on “same work”:** If the goal is summing transformed even values, all three versions must compute the exact same formula. If the goal is taking the first 10 elements, the loop must short-circuit just like `limit(10)`; forcing one variant to scan the entire source skews results.

## 3. Runnable JMH benchmark example

The experiment below uses the same `int[]`. Each variant filters even numbers, calls a pure function `work(int)` on selected elements, and sums the `long` results. `work` performs several arithmetic steps to create a clear CPU workload with **no shared state or side effects**. All three benchmarks return the result so JMH keeps the computation live.

```java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
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
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
@Threads(1)
public class LoopStreamBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = i;
        }

        // Verify outside the JMH timed region.
        long expected = loop();
        if (sequentialStream() != expected || parallelStream() != expected) {
            throw new IllegalStateException("Results of the three approaches differ");
        }
    }

    // Pure function: identical input always yields identical output.
    private static long work(int value) {
        long x = value;
        for (int i = 0; i < 32; i++) {
            x = (x * 1_103_515_245L + 12_345L) & 0x7fff_ffffL;
        }
        return x;
    }

    @Benchmark
    public long loop() {
        long sum = 0L;
        for (int value : values) {
            if ((value & 1) == 0) {
                sum += work(value);
            }
        }
        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return Arrays.stream(values)
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopStreamBenchmark::work)
                .sum();
    }

    @Benchmark
    public long parallelStream() {
        return Arrays.stream(values)
                .parallel()
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopStreamBenchmark::work)
                .sum();
    }
}
```

Intentional design points in the example:

- `@Param` exercises different dataset sizes without recreating arrays on every benchmark call.
- `@Setup` builds data and cross-checks all three results **outside measurement**, catching semantic bugs before comparing speed.
- `@Threads(1)` means only one JMH thread invokes the benchmark at a time. `parallelStream()` itself may still use workers from `ForkJoinPool.commonPool()`, so actual processing threads for the parallel variant can exceed one.
- `@Fork(2)` launches separate JVM processes to reduce dependence on a single process's JIT state. Five warmup iterations and five measurement iterations per fork gather far more samples than manual timing.
- All three versions use a primitive array, the same `filter`, the same `work`, and the same `sum`. This experiment measures **latency of processing an entire array**, not the isolated cost of constructing an empty Stream.

JMH is a standalone benchmark library: the project must declare `jmh-core` and the annotation processor `jmh-generator-annprocess` at matching versions, then configure the build to package a benchmark JAR. With a typical Maven JMH setup producing `target/benchmarks.jar`, run:

```bash
java -jar target/benchmarks.jar '.*LoopStreamBenchmark.*' -prof gc -rf json -rff results.json
```

In different shells, quoting syntax for the benchmark filter pattern may vary; the JAR path also depends on Maven/Gradle configuration. `-prof gc` observes allocations/GC; `-rf json -rff results.json` saves results for cross-run comparison. Record JDK version, JVM flags, CPU, container limits, and background load alongside the results file. This lesson provides the benchmark for learners to run in their own environment; **no pre-assumed real measurement numbers are fabricated here**.

### Reading results accurately

In the example, `@BenchmarkMode(Mode.AverageTime)` and `@OutputTimeUnit(MILLISECONDS)` mean:

- **`ms/op`**: average time to process **the whole array once**; lower is faster for a given `size`.
- **Error margins and spread**: inspect confidence intervals or variance across forks/iterations; two very close numbers may lack enough evidence for a conclusion.
- **`gc.alloc.rate.norm` (B/op)** if supported by the profiler: allocated bytes normalized per **one array pass**, not per element. Zero or tiny values can appear due to JVM optimizations; do not assume Stream always allocates an object per element.
- **Element throughput** when comparing at the same `size`: roughly `size * 1000 / (ms/op)` input elements/second. Do not use this conversion to merge results across different sizes without explanation.

As an example of interpretation (not measured data): if `loop` clearly wins at `size=1000`, yet `parallelStream` has lower `ms/op` at `size=1000000`, treat that as a sign of a **split/merge break-even threshold** for that workload and machine. Re-measure with lighter computations, different CPU loads, and the real application before generalizing.

## 4. Why do results change with workload?

### Data size and fixed overhead

Loops have minimal coordination layers. Sequential Streams add pipeline infrastructure; the JIT can inline/fuse many stages but is not guaranteed to erase all overhead. Parallel Streams must split the source, submit tasks to Fork/Join, process across workers, and merge results. On small sets, fixed overhead easily dominates; on large sets, that overhead amortizes against useful computation.

### Per-element computation weight

If each element only adds `1` or checks one bit, distributing tasks rarely helps. If each element performs independent, time-consuming CPU work, concurrent execution can reduce latency. **Keep logic identical across all three variants** when moving from light to heavy workloads; never inflate work in just one variant.

### Source characteristics and merging

Arrays and `ArrayList` have `Spliterator`s that split fairly evenly. Sources that split poorly or must advance sequentially may not scale well. Aggregations like `sum()` merge cheaply; conversely, collectors that must preserve order, acquire locks, or merge huge structures can become bottlenecks. Stateful stages like `sorted()`, `distinct()`, or certain `limit()` uses on ordered Streams may require extra buffering or synchronization when parallel.

### Resource contention and memory pressure

Parallelism does not create infinite memory bandwidth. When cores read a large memory region simultaneously, cache misses or RAM bandwidth can bottleneck speed. Many concurrent tasks can also increase intermediate objects, GC activity, or contention with other requests. To understand real-world benefit, measure both CPU usage and runtime under realistic concurrent request load.

## 5. Comparisons that easily lead to wrong conclusions

| Skewed measurement | Why it is wrong | How to fix |
| --- | --- | --- |
| Running `System.nanoTime()` once per approach | Affected by unwarmed JIT, GC, scheduling, and system noise | Use JMH with warmup, measurement, forks, and read error margins |
| Creating a `List`/array inside only one variant | Measures extra data allocation and initialization | Prepare identical data in setup |
| Comparing `for (int x : int[])` with `Stream<Integer>` | Boxing/unboxing and source types differ | Use `IntStream`; study boxing in a separate experiment if needed |
| Comparing `findFirst()` with `findAny()` | Ordering guarantees and short-circuiting differ | Match ordering requirements and stopping conditions |
| Adding `.peek(System.out::println)` to one pipeline | Console I/O and synchronization distort workload | Remove logging from measured paths |
| Running parallel benchmarks while other benchmarks run | Competing for `commonPool` and CPU skews readings | Run benchmarks sequentially on a quiet machine; record configuration |
| Looking only at `ms/op` while ignoring cores and `B/op` | May win latency at excessive resource cost | Inspect latency, system throughput, CPU, and memory |
| Concluding “Streams are always slow” or “parallel is always fast” from one size | Crossover depends on source, workload, JDK, and hardware | Measure multiple sizes and re-run in the target environment |

**Note on correctness:** `forEach()` on a parallel Stream does not guarantee execution order; if order is required, use the proper API and algorithm such as `forEachOrdered()`, and then measure. Updating a shared counter inside a lambda is a data race, not a valid merge technique. Prefer proper reductions or collectors.

For floating-point numbers, addition is not strictly associative due to rounding: `(a + b) + c` can differ from `a + (b + c)`. Parallel Streams may regroup partial sums differently. When comparing `double` sums, define an acceptable tolerance and measure performance only when results meet domain accuracy requirements; do not compare solely with `==`. The JMH example above intentionally uses integer `long` results to avoid that noise.

## 6. Evaluation workflow in a real project

1. **Set a concrete goal:** e.g., “Reduce p95 processing time for 1,000,000 records without exceeding allocation limits or degrading throughput at 8 concurrent requests.”
2. **Build a verified baseline:** write three equivalent implementations, verify outputs, and use datasets and sizes representative of production.
3. **Run microbenchmarks:** use JMH on the same machine/JDK, multiple forks and sizes; record `ms/op`, errors, and allocation metrics.
4. **Test in application context:** measure throughput, p95/p99, CPU, and GC under concurrent requests, since a single JMH benchmark does not reflect the whole system.
5. **Make a qualified decision:** pick the approach meeting performance, correctness, and maintainability goals. Document the conditions under which the conclusion holds so future JDK upgrades or hardware changes can be re-measured.

### Self-check

- Why is a single `nanoTime()` measurement insufficient to conclude a loop is faster than a Stream?
- Why can a `parallelStream()` benchmark with `@Threads(1)` still use multiple CPU cores?
- If `parallelStream()` lowers `ms/op` yet server throughput drops under concurrent requests, what should you evaluate next?
- For pipelines with `sorted()` or `findFirst()`, what semantics must be matched before comparing performance?

**Point to remember:** A fair comparison starts with equivalent results and semantics, continues with warmed-up and controlled measurements, and ends with choosing an implementation. Loops, sequential Streams, and parallel Streams each have valid domains; benchmarks provide evidence for a **specific problem**, not a universal ranking for every Java program.
# Fairly Comparing Loops, Sequential Streams, and Parallel Streams

## 1. Lesson objectives

In the **`JAVA_STREAM_API`** module, the Java Stream API expresses data processing declaratively with lazy steps like `filter` and `map`, ending with `reduce`, `sum`, or `collect`. Pipelines can also run sequentially or in parallel. Yet a frequent question during optimization is:

> Is a `for` loop, a sequential Stream, or a parallel Stream faster, lighter on memory, and better suited for the same task?

There is no single answer valid for every program. Results depend on **data, per-element cost, source characteristics, JIT behavior, memory, CPU load, and measurement methodology**. Fair comparison is not writing three similar-looking snippets and starting a stopwatch; you must define a **correctness contract** and control independent variables.

This lesson belongs to **Performance and Memory**, connecting lazy pipelines, primitive types, `Spliterator`, reduce/collectors, parallel processing, and Java Stream API resource limits.

After this lesson, you will be able to:

1. Design three implementations **equivalent in inputs, outputs, and work performed**.
2. Explain why a single `System.nanoTime()` timing cannot prove which variant is faster.
3. Use JMH with warmup, measurement, forks, and stable input state.
4. Distinguish **average time**, **throughput**, **allocation rate**, **GC**, and **latency**.
5. Identify costs of boxing, pipeline creation, source splitting, worker coordination, and result merging.
6. Recognize when parallelism is limited by the source, ordering, shared state, or memory bandwidth.
7. Build a checklist and test suite so benchmark results can be verified and reproduced.

## 2. “Fair” means comparing the same contract

A valid comparison must guarantee all three variants compute **the exact same function** over **the exact same dataset**.

Business example: given an array of `long` integers, select only even numbers, square each number, and sum them:

\[
S=\sum_{\substack{x\in A\\x\bmod 2=0}} x^2
\]

To prevent `long` overflow in the experiment, restrict input values to **1 through 10,000** and element count to at most **1,000,000**. Then the sum of squares cannot exceed `100,000,000,000,000`, safely below `Long.MAX_VALUE`.

We will compare:

- **Loop:** iterate the array with `for`, test evenness, accumulate squares.
- **Sequential Stream:** `Arrays.stream(data).filter(...).map(...).sum()`.
- **Parallel Stream:** same pipeline with `.parallel()`.

All three use the **exact same `long[]` array**. That keeps results free from differences between `ArrayList` and `LinkedList`, or between primitive `long` and boxed `Long`.

### 2.1. Conditions that must align

| Factor | Comparison rule |
| --- | --- |
| Input data | Same array/source, identical values and distribution. |
| Data type | Same `long[]` and `LongStream`; never slip `Stream<Long>` into one branch. |
| Work | Same even filter, same squaring, same summation. |
| Output type | Same `long`, avoiding floating-point rounding discrepancies. |
| Timed scope | Measure the processing function itself, not data generation in just one branch. |
| Output usage | Consume the result to avoid dead-code elimination of unobserved work. |
| Environment | Same machine, JDK, JVM flags, background load, and measurement policy. |
| Sample count | Warmup, multiple measurement iterations, and multiple forks for microbenchmarks. |
| Parallelism | Record core counts, CPU load, and shared pool effects. |
| Conclusion | Draw conclusions only for the measured workload and conditions, without groundless generalization. |

**The three approaches do not need identical line counts.** The goal is comparing **practical implementation choices** for the same requirement, not forcing a loop to allocate dummy objects to resemble a Stream.

### 2.2. Unfair comparisons

Methodologically flawed example:

```java
// Branch A uses primitive long[].
for (long value : data) {
    // ...
}

// Branch B uses Stream<Long> and boxing.
listOfLong.stream()
    .filter(...)
    .map(...)
    .reduce(...);

// Branch C uses a different source and different computation.
java.util.stream.LongStream.range(0, data.length)
    .parallel()
    .sum();
```

Those three branches differ in **source representation, boxing, and computation**. If you measure a gap, you cannot attribute it purely to “loop vs. Stream”.

It is equally unfair if one branch merely counts elements while another squares them, or one prints every element to the console. `System.out.println` I/O can completely dominate runtime.

## 3. Three equivalent implementations on `long[]`

The program below uses **Java 8+** and only standard libraries. Create `FairStreamComparison.java`:

```java
import java.util.Arrays;
import java.util.SplittableRandom;

public class FairStreamComparison {
    static long withLoop(long[] data) {
        long sum = 0L;
        for (long value : data) {
            if ((value & 1L) == 0L) {
                sum += value * value;
            }
        }
        return sum;
    }

    static long withSequentialStream(long[] data) {
        return Arrays.stream(data)
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    static long withParallelStream(long[] data) {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    static long[] createData(int size) {
        if (size < 0) {
            throw new IllegalArgumentException(
                "size must be >= 0");
        }

        long[] data = new long[size];
        SplittableRandom random =
            new SplittableRandom(20261118L);

        for (int i = 0; i < data.length; i++) {
            // Values 1..10000, sum of squares will not overflow.
            data[i] = random.nextInt(1, 10_001);
        }

        return data;
    }

    static void verify(long[] data) {
        long a = withLoop(data);
        long b = withSequentialStream(data);
        long c = withParallelStream(data);

        if (a != b || a != c) {
            throw new AssertionError(
                "Result mismatch: "
                + a + ", " + b + ", " + c);
        }
    }

    public static void main(String[] args) {
        verify(new long[0]);
        verify(new long[] {1});
        verify(new long[] {2});
        verify(new long[] {1, 2, 3, 4, 5, 6});
        verify(new long[] {-4, -3, -2, -1, 0, 1, 2, 3, 4});
        verify(new long[] {9_999, 10_000});

        for (int size : new int[] {
                1, 10, 128, 10_000, 1_000_000}) {
            verify(createData(size));
        }

        System.out.println("PASS: all three approaches produced the same result");
    }
}
```

When run properly:

```text
PASS: all three approaches produced the same result
```

This is a **correctness verification suite**, not a benchmark yet. The program deliberately **does not print nanoseconds**, because calling three functions sequentially once is skewed by JIT warmup and call order.

### 3.1. Why `Arrays.stream(data)`?

For a `long[]` array, `Arrays.stream(data)` creates a `LongStream`, avoiding boxing `long` into `Long` per element.

Compare the pipelines:

```java
// LongStream: primitive processing.
long sum1 = Arrays.stream(data)
    .filter(x -> x % 2L == 0L)
    .map(x -> x * x)
    .sum();

// Stream<Long>: involves boxing, evaluate separately.
long sum2 = Arrays.stream(data)
    .boxed()
    .filter(x -> x % 2L == 0L)
    .mapToLong(x -> x * x)
    .sum();
```

Both produce the same value, yet **do not share the same representation cost**. When the question is “loop vs. primitive Stream”, use the `LongStream` branch as the baseline. When the question is “how much does boxing add in an object pipeline?”, build **a second clearly labeled experiment**.

### 3.2. Why return `long`?

If a benchmark method computes a value and discards it, the JIT may optimize away unobserved computations in some situations. Returning `long` to a benchmark harness like JMH ensures the result is **consumed**, reducing the risk of timing an eliminated computation.

Avoid benchmark methods like:

```java
static void notUseful(long[] data) {
    long total = Arrays.stream(data)
        .filter(x -> x % 2 == 0)
        .map(x -> x * x)
        .sum();

    // total is unused.
}
```

That does not mean every such call is guaranteed to be deleted by the JIT; it is a **risk to control**, not a prediction of a specific optimization across all JVMs.

## 4. Correct results first, performance measurement second

Verify independent properties:

1. **Empty source:** sum must be 0.
2. **One odd element:** sum is 0.
3. **One even element:** square of that element.
4. **Mixed negative/positive numbers:** parity check behaves accurately.
5. **Duplicate values:** each element is counted as many times as it appears.
6. **Large source:** all three return the exact same value without overflow in the bounded domain.
7. **Input immutability:** calling the functions does not mutate the array.
8. **Deterministic results:** same data, no stateful variables captured outside lambdas.

### 4.1. Independent check against a hand-calculated value

```java
long[] sample = {1, 2, 3, 4, 5, 6};

// 2² + 4² + 6² = 4 + 16 + 36 = 56
if (FairStreamComparison.withLoop(sample) != 56L) {
    throw new AssertionError("Loop wrong");
}
if (FairStreamComparison.withSequentialStream(sample) != 56L) {
    throw new AssertionError("Sequential wrong");
}
if (FairStreamComparison.withParallelStream(sample) != 56L) {
    throw new AssertionError("Parallel wrong");
}
```

An independent check prevents the trap where all three share the same buggy formula and produce **the same wrong answer**.

### 4.2. Do not carelessly compare `double` with `==`

If the problem switches to `double`, floating-point addition is not strictly associative at the bit level:

```text
(a + b) + c  may differ from  a + (b + c)
```

A parallel Stream may combine partial sums in a different order. Floating-point outputs can differ in the last few bits even when every variant obeys the API contract. Tests need an appropriate tolerance (plus policies for NaN, infinity, and ±0), or an arithmetic specification with exact rules.

The main experiment uses `long` in a non-overflowing range to **reduce confounding noise** when evaluating speed, not because Streams are only for integers.

## 5. Distinguishing microbenchmarks from real application measurement

A **microbenchmark** measures a small operation in a controlled environment; an **application benchmark** measures an entire business flow (source read, parsing, processing, serialization, response sending...). Both are useful, yet answer different questions.

| Measurement type | Question answered | What it cannot prove |
| --- | --- | --- |
| Three-function microbenchmark | How long does one computation take on an in-memory array? | Will the whole real API speed up proportionally? |
| End-to-end benchmark | How long does a full data-processing request take? | Exactly which part is slow without profiling. |
| Allocation/GC measurement | How many bytes/objects are allocated, and what is GC impact? | Is CPU faster just because allocations are lower? |
| Multi-request throughput | How many tasks/sec does the system sustain? | Are p95/p99 latencies definitely better too? |
| Profiling | Where are CPU hotspots, waits, and memory allocations? | Does one profile run always match production? |

This lesson's goal is building a **fair and trustworthy** microbenchmark, then explaining how to validate findings at the application level.

### 5.1. Measurement conditions

- Same JDK version, JVM flags, and GC collector.
- Reasonably quiet machine without heavy concurrent background tasks.
- Record physical/virtual CPUs, effective core count, container limits, and memory limits.
- Identical dataset created before timing.
- No `println` or file/network I/O inside benchmark methods.
- Do not change source size mid-run for a given configuration.
- Run multiple iterations, report variance, avoid cherry-picking only the “fastest run”.
- Rotate benchmark state or fork processes to limit call-order and JIT-profile bias.
- Treat cache-resident data vs. larger-than-cache data as **two distinct workloads**.

### 5.2. Why is one `System.nanoTime()` call misleading?

Example:

```java
long start = System.nanoTime();
long result = FairStreamComparison.withSequentialStream(data);
long elapsed = System.nanoTime() - start;

System.out.println(result);
System.out.println(elapsed);
```

This records the duration of **a single execution in one specific JVM state**. It can be skewed by:

- Class loading and first-time initialization.
- JIT compilation, deoptimization, and tiered compilation.
- CPU frequency scaling, thermals, OS scheduler, and background activity.
- GC, memory paging, and cache state.
- Interference from previous code runs.
- Timer call overhead dominating when the function is very short.

The nanosecond reading is not meaningless; it is simply **insufficient for fair comparison** or general conclusions. Use a benchmark harness like **JMH** to mitigate these common pitfalls.


## 6. Using JMH for controlled measurement

**JMH (Java Microbenchmark Harness)** is the benchmark toolkit for the JVM. It manages warmup, measurement duration, forks, threads, and result consumption. It is not part of `java.base`: running JMH samples requires **adding JMH dependencies and annotation processors** according to the JMH version your project uses.

JMH fixes many technical measurement mistakes, yet **cannot make an unequal workload fair automatically**. The benchmark author must still preserve identical inputs, identical semantics, and clarity on what is inside the timed region.

### 6.1. Java 8+ benchmark example using the same source

Create `LoopVsStreamBenchmark.java` inside a **dedicated benchmark module or project configured with JMH**:

```java
import java.util.Arrays;
import java.util.SplittableRandom;
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

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1,
        timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1,
        timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class LoopVsStreamBenchmark {

    // Test three different scales.
    @Param({"128", "10000", "1000000"})
    public int size;

    private long[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = new long[size];

        SplittableRandom random =
            new SplittableRandom(20261118L);

        for (int i = 0; i < data.length; i++) {
            data[i] = random.nextInt(1, 10_001);
        }
    }

    @Benchmark
    public long loop() {
        long sum = 0L;

        for (long value : data) {
            if ((value & 1L) == 0L) {
                sum += value * value;
            }
        }

        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return Arrays.stream(data)
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }

    @Benchmark
    public long parallelStream() {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1L) == 0L)
            .map(value -> value * value)
            .sum();
    }
}
```

**Fairness design points:**

- `@Param` varies **array size**, and all three approaches always receive the exact same array and values within each trial.
- `@Setup(Level.Trial)` builds data **outside `@Benchmark` timing**.
- `SplittableRandom` with a fixed seed makes data **reproducible**; no RNG runs inside benchmark calls.
- `@Benchmark` returns `long` so the harness observes the result.
- `@Warmup` gives the JVM time to optimize hot code paths.
- `@Measurement` measures multiple rounds instead of taking a single first-run number.
- `@Fork(2)` requests **two separate JVM forks** per configuration, reducing dependence on one JVM's state.
- `@BenchmarkMode(Mode.AverageTime)` measures **average time per benchmark operation**.
- `@OutputTimeUnit(TimeUnit.MICROSECONDS)` selects the display unit; it **does not determine absolute precision** of the measurement.

With `@State(Scope.Benchmark)`, the data array is shared across benchmark threads within a trial. Here the methods **only read the array**, so there is no race on source data. The template targets one independent task at a time; measuring multi-request load requires separate thread and concurrency setup.

### 6.2. Configuring the JMH project

To compile code using `org.openjdk.jmh.annotations`, you need:

1. The JMH core library matching your JDK and build tool.
2. The JMH annotation processor code generator.
3. Packaging/running steps guided by your build tool.

You cannot simply run `javac LoopVsStreamBenchmark.java` **without JMH configured** and expect it to compile, because the annotation classes are not in the JDK.

A standard Maven/Gradle JMH setup builds a runner or benchmark artifact. After packaging per that setup, you can run tests by benchmark name and attach allocation profilers such as `-prof gc`. Specific JAR paths and versions depend on the project, so never hardcode a nonexistent filename.

**Note:** This lesson provides study examples; it does not claim JMH has already been compiled or executed on the learner's machine.

### 6.3. Reading a JMH result row

JMH output typically shows benchmark name, parameters, mode, sample count/units, score, and error estimate.

Example **result table template to fill in** (cells left empty because no measurement has been run yet):

| size | Approach | Average time / operation | Spread | Allocation / operation |
| ---: | --- | ---: | ---: | ---: |
| 128 | Loop | To measure | To measure | To measure |
| 128 | Sequential Stream | To measure | To measure | To measure |
| 128 | Parallel Stream | To measure | To measure | To measure |
| 10,000 | Loop | To measure | To measure | To measure |
| 10,000 | Sequential Stream | To measure | To measure | To measure |
| 10,000 | Parallel Stream | To measure | To measure | To measure |
| 1,000,000 | Loop | To measure | To measure | To measure |
| 1,000,000 | Sequential Stream | To measure | To measure | To measure |
| 1,000,000 | Parallel Stream | To measure | To measure | To measure |

**Do not fill in guessed numbers** and present them as proof that “Stream is x times slower” or “parallel is y times faster”. Numbers must come from actual JMH runs with documented environment and flags.

### 6.4. Average time vs. throughput

For average-time benchmarks:

- A **smaller** score means faster per operation.
- For `Mode.Throughput`, a **larger** score is generally better since it represents operations completed per unit of time.
- The two modes use different units and interpretations; never compare “microseconds/op” directly with “ops/s”.

If an application request consists of many steps, benchmarking one function may **not scale proportionally** to total request latency. Follow up with end-to-end benchmarks once viable implementation candidates are selected.

## 7. Warmup, JIT, and JVM state

The JVM does not necessarily execute all Java code identically from the first run to the last. The JIT can recompile “hot” methods, inline lambdas, optimize expressions, or change strategies after observing runtime data types.

### 7.1. Why is timing three approaches one after another error-prone?

Methodologically flawed:

```java
long a = time(loop);
long b = time(sequential);
long c = time(parallel);
```

Here `time` simply denotes an illustrative timing helper; running three measurements back to back in the same JVM lets the first branch pay class-loading/JIT costs that later branches avoid. Reversing call order can flip the winner.

Warmup and forks do not eliminate all noise, yet they prevent confusing **JIT warmup effects** with **true algorithmic cost**.

### 7.2. Warmup is not a magic number

Five iterations is an illustrative JMH setting, **not a universally optimal default**:

- Very short workloads may need more rounds to reach steady state.
- Workloads with multiple code paths or complex branching must ensure critical branches execute.
- Excessive warmup on heavy benchmarks can heat up hardware, trigger CPU throttling, or create GC pressure.
- Check consistency across forks and variance rather than blindly raising iteration counts until a desired number appears.

A responsible measurement report records warmup, measurement, fork, parameter, and load settings.

### 7.3. Random inputs must be generated outside the timed region

Wrong:

```java
@Benchmark
public long bad() {
    SplittableRandom random = new SplittableRandom();
    long[] values = new long[1_000_000];

    for (int i = 0; i < values.length; i++) {
        values[i] = random.nextLong();
    }

    return Arrays.stream(values).sum();
}
```

If the goal is measuring **processing an existing array**, the snippet above also measures allocation and RNG generation. That is valid only if the real problem requires **creating + processing the array**, and unfair if the loop variant receives a pre-built array.

Depending on the question, create two separate benchmarks:

- **Processing-only:** all three use the same array built in `@Setup`.
- **End-to-end:** all three measure the full build/read/transform chain with equivalent source creation.

Do not mix both measurements into one table without stating scope.

## 8. Computation elimination and over-optimization mistakes

In tiny benchmarks, the compiler can fold constant-only expressions or remove computations without observable output. Therefore:

```java
@Benchmark
public void ineffective() {
    long result = 1L + 2L + 3L;
    // result is unused.
}
```

does not measure addition as expected. Conversely:

```java
@Benchmark
public long observable() {
    return 1L + 2L + 3L;
}
```

has an observable return value, yet the compiler can still **constant-fold** it to `6`. That tests constant optimization, not a data-processing workload.

The lesson's benchmark avoids this by:

- Reading an array initialized beforehand in JMH state.
- Making the output depend on array contents.
- Returning `long` to the harness.
- Varying array sizes via `@Param` across multiple work thresholds.

Even so, nothing guarantees the compiler **won't apply a valid optimization**. A good benchmark does not try to “forbid JIT optimizations”, it measures realistic post-optimization code on representative data and conditions.

If a method produces multiple results or outputs, JMH provides `Blackhole` to consume values instead of printing to console. Use `Blackhole` only when needed; never introduce unequal consumption cost across branches.

## 9. Never create an unfair advantage by changing the algorithm

All three core implementations filter and square the same elements. Yet one could cheat algorithmically:

```java
// A different approach if the source is 1..N
// could use a closed-form arithmetic formula.
// That is no longer the same arbitrary-array processing implementation.
```

A different algorithm can be orders of magnitude faster. That is **algorithm comparison**, not purely **loop vs. Stream comparison**.

Similarly, if one branch calls `sum()` while another calls `collect(toList())` and sums in a second loop, you are also measuring intermediate list allocation. That is meaningful if the task **genuinely needs that list**, yet unfair when only the sum is required.

### 9.1. Avoid differing materialization

For a sum-only problem:

```java
// Unnecessary extra cost:
List<Long> squared = Arrays.stream(data)
    .filter(x -> (x & 1L) == 0L)
    .map(x -> x * x)
    .boxed()
    .collect(Collectors.toList());

long result = squared.stream()
    .mapToLong(Long::longValue)
    .sum();
```

This pipeline builds an intermediate collection and boxes values. Do not use it to represent `LongStream` performance when comparing terminal `sum`.

### 9.2. Watch out for `count()` and laziness

`LongStream.count()` can inspect source size metadata and skip steps that do not change element count. For instance, a `map` with side effects is not guaranteed to run merely because terminal `count` is invoked.

Hence if a benchmark intends to time `map` work yet ends with `count()`, it may measure **a pipeline that skips the intended work**.

```java
// DO NOT use to measure computation cost inside map:
long count = Arrays.stream(data)
    .map(x -> expensiveCalculation(x))
    .count();
```

In this snippet, `expensiveCalculation` is just an illustrative name. Since `map` does not change element count, `count` can omit evaluating the mapper. Choose a terminal operation that genuinely requires **the mapper's output values**, such as `sum` in the main benchmark.

### 9.3. Do not mix array copying cost into just one variant

Unfair comparison:

```java
// Branch A: existing array.
long a = FairStreamComparison.withLoop(data);

// Branch B: copy before running.
long b = FairStreamComparison.withSequentialStream(
    Arrays.copyOf(data, data.length));
```

Branch B measures an extra `O(n)` copy step. If production genuinely needs a defensive snapshot for parallel safety, report **snapshot cost** separately rather than blaming it on every Stream.

## 10. A fair measurement can still yield unexpected results

Results can shift dramatically with scale:

- **Very small data:** pipeline setup and parallel coordination can outweigh a simple loop.
- **Medium data:** the JIT can optimize sequential Streams heavily; differences from loops are not always significant.
- **Large, independent, CPU-bound data:** parallel Streams can leverage multiple cores effectively, while still paying split/combine costs.
- **Data far exceeding CPU caches:** memory bandwidth can become the bottleneck, so adding threads stops scaling linearly.
- **Complex filtering or skewed cost:** varying per-element work can cause load imbalance.

These are **possibilities to verify**, not a fixed ranking. If a benchmark shows a sequential Stream matching or beating a loop on a workload, never massage numbers to match preconceptions. Verify correctness, noise, and environment, then report what was observed.

### 10.1. Do not extrapolate a microbenchmark to “the whole application”

If an application spends 90% of its time waiting on a database, optimizing the 10% CPU processing portion **cannot speed up the whole application by the same factor**.

Amdahl's Law gives an intuitive estimate:

\[
Speedup_{\text{total}}
=\frac{1}{(1-p)+p/s}
\]

where `p` is the improvable fraction of time and `s` is its speedup factor. With `p = 0.10` and `s = 4`:

\[
Speedup_{\text{total}}=\frac{1}{0.9+0.1/4}
\approx 1.081
\]

Even though that computation became four times faster, the whole application improves theoretically by only about **8%** if the model's assumptions hold.

The formula is a **bounding model**; real load shifts, tasks contend for resources, or throughput drops. Never substitute it for end-to-end measurement.


## 11. Measure memory and GC cost, not just elapsed time

Returning the same result does not mean all three approaches have the same **allocation** or garbage-collector pressure.

### 11.1. Where allocations can arise

- **Loop over `long[]`:** may need only a few local primitive variables; the loop itself forces no per-element objects or lists.
- **Sequential `LongStream`:** builds pipeline description structures and some internal objects; JIT optimization/allocation varies by JVM and code path.
- **`LongStream.parallel()`:** beyond the pipeline, involves task splitting, task scheduling, and result merging depending on source and implementation.
- **`Stream<Long>`:** can add boxing/unboxing and memory pressure relative to `LongStream`; JIT optimizations alter actual cost.
- **`collect(toList())`:** retains output elements in a collection, unlike `sum()` which returns one total.
- **`sorted`, `distinct`, `groupingBy`:** examples that can require significant intermediate structures; never introduce them asymmetrically into one branch.

Do not assert “Streams always allocate N objects” or “loops always allocate 0 bytes” across every JVM. Report **numbers measured on a specific configuration**, including whether the JIT eliminated allocations.

### 11.2. Using the JMH GC profiler

Once JMH and your benchmark runner are configured per project workflow, enable the GC profiler with:

```text
-prof gc
```

Common metrics JMH displays include:

| Metric | Meaning | Interpretation limit |
| --- | --- | --- |
| `gc.alloc.rate.norm` | Allocated bytes normalized per operation | Not bytes remaining live after GC. |
| `gc.alloc.rate` | Allocation rate over time | Depends on throughput and benchmark mode. |
| `gc.count` | Number of GC cycles during measurement | Can be 0 in short runs. |
| `gc.time` | Recorded GC duration | Does not capture all memory or latency costs alone. |

Available metrics depend on JMH version, JDK, and profiler support. If the profiler does not report a metric, report **no data**, never fill in 0.

### 11.3. Allocation differs from live heap and RSS

Three frequently confused concepts:

1. **Allocated bytes:** total bytes allocated over a period; objects may die almost immediately.
2. **Live heap:** heap memory held by objects that remain reachable.
3. **RSS/process memory:** physical memory used by the process, including thread stacks, native buffers, metadata, and off-heap regions.

A pipeline can allocate many short-lived objects while keeping live heap low. Conversely, a `collect` retaining a big list can produce high **live heap** even with modest instantaneous allocation rates.

To understand production impact, supplement with **JFR (Java Flight Recorder)**, heap profiling, or environment-appropriate allocation tools. Never treat a single Task Manager screenshot as sufficient memory proof.

## 12. Boxing and choosing the data baseline

`LongStream` and `Stream<Long>` do not share the same memory profile:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

long[] data = {2L, 3L, 4L, 5L};

// Primitive pipeline.
long primitiveSum = Arrays.stream(data)
    .filter(x -> x % 2L == 0L)
    .map(x -> x * x)
    .sum();

// Object pipeline with boxed Long.
long boxedSum = Arrays.stream(data)
    .boxed()
    .filter(x -> x % 2L == 0L)
    .mapToLong(x -> x * x)
    .sum();

System.out.println(primitiveSum); // 20
System.out.println(boxedSum);     // 20
```

Both produce the same value. Yet `boxed()` can allocate `Long` objects and `mapToLong` must unwrap wrapper values. On large data, overhead can be significant, though you should measure rather than assuming a fixed slowdown factor.

If the domain already stores `List<Long>`, copying everything into `long[]` also costs time and memory. In that case, run **two experiment groups**:

- **Same `long[]` source:** compare loop vs. sequential/parallel `LongStream`.
- **Same `List<Long>` source:** compare iterating the list vs. `list.stream().mapToLong(...)` and `list.parallelStream().mapToLong(...)`.

Never compare a loop on an array against a Stream on a list and blame the gap solely on “Streams are slow”. Both **data layout** and **memory access** changed.

### 12.1. Do not create an intermediate list just to benchmark a sum

`Collectors.toList()` retains the full output; `sum()` needs only an aggregate number. Those are two **different result contracts**. If the real app needs the list for display, the benchmark should return the list or include list construction in **all three** variants. If only the sum is needed, all three should return just the sum.

## 13. Why does `parallel()` add overhead?

A parallel stream conceptually passes through these phases:

```text
                source long[]
                     |
                Spliterator
                     |
             split work chunks
              /      |      \
         chunk A  chunk B  chunk C
              |      |      |
          filter + map + local sum
              \      |      /
                merge sums
                     |
                single long value
```

In common JDK implementations, parallel Streams use fork/join mechanics and typically `ForkJoinPool.commonPool()`. Still, the Stream API **does not guarantee** a fixed thread count, fixed split scheme, or that each element stays on a dedicated thread.

Overhead can include:

- `Spliterator.trySplit()` and organizing data chunks.
- Creating, scheduling, stealing, and joining tasks.
- Synchronization, coordination, or waiting for sibling subtasks to finish.
- CPU cache interactions and memory bandwidth contention.
- Stateful operations and encounter-order constraints.

Therefore, `parallel()` on a 128-element array doing simple multiplication **can be slower** than sequential execution. With one million elements and substantial independent per-element work, it **has a chance** to be faster. Even so, there is no universal “always parallelize above N” threshold across all machines and workloads.

### 13.1. `Spliterator` determines splittability

| Source | Typical characteristics | Implication for parallel benchmarks |
| --- | --- | --- |
| `long[]`, `IntStream.range` | Splits quickly into known-size segments | More favorable for independent CPU-bound work. |
| `ArrayList` | Supports index-based range splitting | Generally a good source for testing parallelism. |
| `LinkedList` | Lacks fast random index access | Batch splitting adds different overhead; must measure. |
| `Stream.iterate` | Elements can depend on predecessors, hard to split evenly in some forms | Do not assume good parallel scaling. |
| `Files.lines` or I/O iterators | Often sequential reading tied to resources | Parallelism does not speed up reading disks or networks automatically. |

Do not compare a random-access loop against a Stream backed by a poorly splittable `Spliterator` and blame all differences on `parallel()`.

### 13.2. Uneven per-element cost

If the first half of an array is trivial and the second half is expensive, splitting into equal element counts **does not guarantee load balance**. The runtime may split further, yet has no guarantee of eliminating skew.

Beyond element count, check **per-element execution time distribution**, resource contention, and actual available core counts.

## 14. Impact of ordering and stateful operations

In the main benchmark, even filtering and squaring are stateless; `sum()` does not depend on element order. That workload is favorable for **splitting and merging**.

A real business pipeline, however, may include:

| Operation | Common constraint/cost |
| --- | --- |
| Pure `map`, `filter` | Elements can be processed independently. |
| `sorted` | Requires sorting coordination, may allocate large intermediate buffers. |
| `distinct` on ordered stream | Keeping the first occurrence can require extra coordination. |
| `limit(n)`, `skip(n)` on ordered parallel stream | Tracking exact positions can require coordination overhead. |
| `findFirst` | Respects encounter order's first element, limiting parallel freedom. |
| `findAny` | Can return any matching element, relaxing constraints. |
| `groupingBy` | May build local maps and merge them. |
| `groupingByConcurrent` | Can accumulate concurrently under right conditions, yet has contention and order implications. |

Benchmarking `filter/map/sum` **does not predict** the performance of `sorted/distinct/groupingBy`. If a system runs diverse pipelines, select several **representative workloads** rather than one unrepresentative “catch-all” benchmark.

### 14.1. Never drop `ORDERED` just to win a benchmark

`unordered()` can unlock certain optimizations. Yet if business logic needs the **first element**, **top-K in a specific order**, or an **ordered report**, dropping encounter order alters the contract.

Invalid:

```java
// Sequential branch keeps exact initial elements.
// Parallel branch drops ORDERED to run faster.
//
// This is no longer a semantically equivalent comparison.
```

If business rules genuinely **do not care about order**, state that upfront; you can then benchmark `unordered` as a valid candidate with the same contract across all branches.

## 15. Shared state corrupts both correctness and benchmarks

Wrong example:

```java
import java.util.ArrayList;
import java.util.List;

List<Long> result = new ArrayList<>();

Arrays.stream(data)
    .parallel()
    .filter(x -> (x & 1L) == 0L)
    .forEach(result::add);
```

`ArrayList` is unsafe for concurrent mutation by multiple threads; outputs can drop elements, corrupt state, or throw exceptions. Never benchmark a **semantically broken** implementation and treat it as an optimization candidate.

Replace with a proper collector or terminal operation:

```java
List<Long> result = Arrays.stream(data)
    .parallel()
    .filter(x -> (x & 1L) == 0L)
    .boxed()
    .collect(java.util.stream.Collectors.toList());
```

This example returns a boxed list, so compare it only against a loop that **also builds an equivalent result list**. That is a different benchmark from the sum benchmark in this lesson.

### 15.1. `AtomicLong` is not a substitute for `sum()`

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong total = new AtomicLong();

Arrays.stream(data)
    .parallel()
    .forEach(x -> total.addAndGet(x));
```

This may yield the right integer sum, yet multiple threads contend on **one shared variable**. `AtomicLong` provides write safety, **without making the cost equivalent** to `LongStream.sum()`.

If the requirement is simply summing, use:

```java
long sum = Arrays.stream(data)
    .parallel()
    .sum();
```

`sum` can accumulate locally and merge, avoiding updating one shared hotspot per element. The main benchmark uses `sum` for both Stream modes.

### 15.2. Side effects also ruin reproducibility

Lambdas updating global counters, writing logs, or calling I/O tie timing to contention and external load. If those side effects are actual business requirements, measure **that requirement**; if the goal is pure pipeline overhead, exclude them from all three implementations.

## 16. Parallel streams and concurrent server workloads

A microbenchmark of one isolated `parallelStream` call cannot tell whether a service handling **100 concurrent requests** will be faster.

When many requests launch parallel streams simultaneously:

- Pipelines can share the same underlying worker pool.
- Task count grows while usable CPU cores do not grow with it.
- Cache contention, memory bandwidth pressure, and queueing delays can increase.
- Single-request latency might drop in isolation while overall service throughput falls.
- Inside containers, CPU quotas or cgroup limits may differ from cores reported by the OS/JVM in some setups.

For **blocking** work like HTTP calls, JDBC queries, or file waits, do not use parallel streams as a default replacement for bounded concurrency/backpressure I/O models. Blocking pool workers waiting on I/O can starve unrelated tasks.

### 16.1. Services need two measurement levels

1. **Function level:** JMH comparing loop/sequential/parallel on identical data across one or more sizes.
2. **Service level:** load tests with realistic traffic and concurrency, measuring throughput, p50/p95/p99 latency, CPU, GC, and I/O pressure.

Deploy changes only when both levels show consistent gains and correctness holds. Never decide solely from a microbenchmark on an idle laptop.

## 17. CPU caches, locality, and memory bandwidth

A `long[]` array usually enjoys good **locality** because primitive elements sit contiguously in Java's array layout. Both loops and `LongStream` can exploit that source layout.

Across sizes:

- **128 elements:** tiny dataset, likely cache-resident; pipeline/split setup dominates.
- **10,000 elements:** processing and cache behavior start diverging depending on CPU.
- **1,000,000 elements:** reads much more memory; memory bandwidth may cap speed.

These sizes are only **experimental scales**, not fixed mappings to L1/L2/L3 caches on every CPU.

When measuring parallelism, distinguish:

- **CPU-bound:** most time is spent computing.
- **Memory-bound:** waiting on data from memory or capped by bandwidth.
- **Synchronization-bound:** workers waiting on locks or contending on shared data.
- **I/O-bound:** waiting on external devices/networks.

A pipeline scanning an array with minimal math per element can quickly become memory-bound. Adding threads helps only up to a point. With `List<Long>`, chasing object references can give very different locality from primitive arrays.

## 18. Interpreting benchmark results responsibly

A report should state:

- **Objective:** sum squares of even numbers on `long[]`, values 1..10,000.
- **Independent variable:** loop, sequential Stream, parallel Stream.
- **Parameters:** sizes, warmup/measurement iterations, fork count, JMH mode/units.
- **Environment:** OS, JDK, JVM options, CPU, heap, container limits, and background load.
- **Results:** actual measured numbers, spread/error, and allocation/GC if collected.
- **Correctness:** all variants returned identical results, cross-checked against hand-calculated values.
- **Scope limits:** applies only to the measured workload and methodology; does not generalize blindly to other pipelines.
- **Decision:** which variant was chosen for that workload and why, not merely picking the lowest average.

### 18.1. How should speedup ratios be computed?

If two durations **were measured under identical conditions and units**, you can compute:

```text
speedup = baseline_time / candidate_time
```

**Hypothetical mathematical example**, not real measured data:

```text
baseline = 40 microseconds/op
candidate = 20 microseconds/op
speedup = 40 / 20 = 2.0
```

Here the candidate ran twice as fast **for the measured operation**. If `speedup = 0.5`, the candidate was twice as slow as the baseline. For throughput, ratios must use **operations/second**, without flipping which direction is better.

If the gap is smaller than noise or variance is wide, do not claim one variant is definitely faster. Run further measurements or report **insufficient evidence** of a difference.

### 18.2. Do not pick solely on the smallest mean

Check:

- Are results consistent across forks?
- Were there outliers from GC, throttling, or background load?
- Did allocation rates shift dramatically?
- Does the behavior hold as size grows or shrinks?
- Does it hurt latency or throughput under concurrent requests?
- Is the gain large enough to justify extra code complexity?

Never pick `parallel()` just because it won 1 out of 10 runs. Likewise, never discard a clean sequential Stream just because a tiny benchmark showed a few microseconds' difference in non-hot-path code that is far easier to maintain.

## 19. Practice exercises

### Exercise 1 — Spot the unfair comparison

Someone compares a loop over `long[]` against `Stream<Long>` from a `List<Long>` and concludes all Streams are slower. Name at least three uncontrolled variables.

### Exercise 2 — Verify correctness

Given `data = [1,2,3,4,5,6]`, compute the sum of squares of even numbers. Write both a loop and a `LongStream` and verify matching outputs.

### Exercise 3 — Generate data in the right place

Why should you avoid calling `new SplittableRandom()` and `new long[1_000_000]` inside a `@Benchmark` method when you only want to measure filter/map/sum cost?

### Exercise 4 — JMH warmup and forks

Explain the purpose of `@Warmup`, `@Measurement`, `@Fork`, and `@Param` in the benchmark example. Which risk does each address?

### Exercise 5 — Reading allocation metrics

One variant has lower average time yet significantly higher `gc.alloc.rate.norm`. Can you conclude it is always better in a server application? What else should you measure?

### Exercise 6 — Can `count()` measure `map` work?

Why might `Arrays.stream(data).map(expensive).count()` fail to measure the cost of `expensive`? Name a better terminal operation when you need to force evaluation of `map`'s outputs.

### Exercise 7 — Parallel on a small source

For 64 numbers where each element only performs one addition, why can `parallel()` be slower than a loop? Which overheads dominate?

### Exercise 8 — Parallel and I/O sources

A service calls a database for every record inside `parallelStream()`. How can connection pool limits, latency, and worker starvation degrade results?

### Exercise 9 — Evaluating data types

Design a separate experiment comparing `LongStream` vs. `Stream<Long>` for speed and allocations without confusing it with array-vs-list differences.

### Exercise 10 — Analyzing counter-intuitive results

A JMH run shows sequential Stream beating a loop in some configurations. What checks will you perform before stating the cause?

### Exercise 11 — Ordering and correctness

A `sorted().limit(20)` pipeline needs the 20 smallest values. May you add `unordered()` or move `limit` before `sorted` just for speed? Why or why not?

### Exercise 12 — Microbenchmark vs. application

A CPU-bound microbenchmark shows a 4x speedup, yet the application spends most of its time waiting on network calls. Why cannot you expect the entire application to run 4x faster?

## 20. Reference answers

**Exercise 1.** `long[]` and `List<Long>` differ in memory layout and access; object streams involve boxing/unboxing; source allocation and initialization may differ; terminal operations might differ too. To compare loops vs. Streams, keep the same source and primitive types.

**Exercise 2.** Sum is `2² + 4² + 6² = 56`:

```java
long[] data = {1, 2, 3, 4, 5, 6};

long loopSum = 0L;
for (long x : data) {
    if ((x & 1L) == 0L) {
        loopSum += x * x;
    }
}

long streamSum = Arrays.stream(data)
    .filter(x -> (x & 1L) == 0L)
    .map(x -> x * x)
    .sum();

System.out.println(loopSum == streamSum); // true
```

**Exercise 3.** Doing so measures array allocation and RNG generation too. Use `@Setup(Level.Trial)` to pre-build data so all three benchmark methods operate on the exact same array.

**Exercise 4.** Warmup lets the JIT optimize hot code; measurement collects statistics across iterations; fork runs separate JVMs to isolate single-JVM state effects; `@Param` sweeps multiple dataset sizes with the same test logic.

**Exercise 5.** Not yet. Higher allocations can increase GC pressure, lower throughput, or hurt tail latency under heavy load. Also measure GC metrics, live heap, RSS, throughput, and end-to-end latency under realistic load.

**Exercise 6.** `count` can infer size from the source and skip mappers that do not alter element count. When benchmarking `map`, use a terminal operation like `sum`, `reduce`, or `collect` that consumes mapper results.

**Exercise 7.** Source splitting, scheduling, coordination, result merging, and pipeline setup can cost far more than 64 additions. Small sizes cannot amortize overhead; measure on the target machine.

**Exercise 8.** Blocking calls hold workers idle, causing connection pool contention, queueing, and timeouts. Concurrent requests compete for shared workers; manage concurrency and backpressure explicitly instead of treating parallel streams as a default I/O solution.

**Exercise 9.** Keep `long[]` as the source for both branches. The primitive branch calls `Arrays.stream(data)`, while the boxed branch calls `Arrays.stream(data).boxed()` before identical filter/map/sum. Measure time and allocations; document that the gap reflects **boxing + stream-type change**, not just a single isolated variable.

**Exercise 10.** Verify output correctness, identical inputs, no hidden data-generation differences, stable variance, adequate warmup/forks, matching JDK flags, quiet background load, no contract-breaking compiler elimination, and representative workload. If all checks pass, report observed measurements without forcing conclusions to fit bias.

**Exercise 11.** No, you must not change order if business logic needs the 20 smallest values **across the entire source**. `limit(20).sorted()` only sorts the first 20 source elements, unlike `sorted().limit(20)`. `unordered()` can also drop encounter-order guarantees; check semantics carefully rather than looking only at speed.

**Exercise 12.** The microbenchmark measures only the optimized CPU portion; network wait time remains. Amdahl's Law bounds total speedup by the improvable fraction; run end-to-end benchmarks and real load tests.

## 21. Pre-publication checklist

- [ ] Describe **the same task** and correct output for all approaches.
- [ ] Use the same source and data types, never mixing `long[]` and `List<Long>` unintentionally.
- [ ] Control overflow, floating-point rules, ordering, and invalid-data policies.
- [ ] Generate data outside the timed scope when measuring processing only.
- [ ] Test empty sources, single elements, boundary values, and large datasets.
- [ ] Exclude logging or I/O from benchmark methods unless part of the workload.
- [ ] Avoid required side effects inside `map`, `peek`, or parallel `forEach`.
- [ ] Consume results; never measure computations susceptible to elimination.
- [ ] Configure appropriate warmup, measurement, forks, and size parameters.
- [ ] Record JDK version, JVM flags, core count, hardware specs, and background load.
- [ ] Measure across multiple sizes, not just a single array.
- [ ] Inspect variance and outliers instead of cherry-picking the best run.
- [ ] Measure allocation/GC when memory matters.
- [ ] Distinguish allocated bytes, live heap, and RSS.
- [ ] Evaluate split/merge costs and `Spliterator` suitability.
- [ ] Never drop encounter order or change algorithms just to polish numbers.
- [ ] Never claim `parallel()` is always faster, especially on small sources or blocking I/O.
- [ ] For server applications, test throughput and latency under concurrent load.
- [ ] If differences fall within noise, record **insufficient evidence**.
- [ ] Base deployment decisions on correctness, code clarity, performance, and operability.

## 22. Summary

Comparing loops, sequential Streams, and parallel Streams must start with **a shared contract**, not a stopwatch:

```java
// Same long[] and same calculation:
long a = FairStreamComparison.withLoop(data);
long b = FairStreamComparison.withSequentialStream(data);
long c = FairStreamComparison.withParallelStream(data);

// All three must agree before timing.
if (a != b || a != c) {
    throw new AssertionError("Results are not equivalent");
}
```

Remember:

1. **Fairness:** identical source, types, data, operations, and outputs.
2. **Correctness before speed:** verify edge cases and numeric ranges before benchmarking.
3. **Measure properly:** use JMH and understand warmup, forks, measurement, dead-code elimination, and timed scope.
4. **Memory:** check boxing, allocations, GC, and live heap, not just elapsed time.
5. **Parallelism:** incurs split/combine overhead, pool/worker scheduling, and CPU/bandwidth limits; no automatic speedup.
6. **Semantics matter more than pretty numbers:** never alter order, side effects, or reductions just to win a benchmark.
7. **Decide by workload:** a solid microbenchmark is evidence for the measured task; production impact still requires end-to-end measurement.

Loops often offer predictable low overhead for small, simple work; sequential Streams express pipelines clearly; parallel Streams have a chance to speed up large, splittable, independent CPU-bound tasks. Yet the right choice must come from **reproducible measurements, business correctness, and real resource limits**, never from a slogan claiming one Java style is always faster than another.
