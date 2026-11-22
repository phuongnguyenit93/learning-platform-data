# Using Benchmarks to Determine the Break-Even Threshold for Parallel Streams

## 1. The Question to Answer

`parallelStream()` or `stream().parallel()` instructs the Stream library to process a pipeline in parallel. That **does not guarantee the program will run faster**. When splitting the data source into chunks, scheduling tasks, executing across multiple workers, and merging results, the JVM pays an overhead cost. With small datasets or trivial per-element operations, that overhead can exceed the computation time saved.

The practical question is not merely “is parallel faster than sequential?” but rather:

> Given this data type, per-element work, element count, CPU count, JVM configuration, and real-world load, at what size does `parallel()` deliver a consistent enough improvement to be worth using?

We call that point the **break-even threshold** or **beneficial threshold**. There is no universal default like “use parallel above 1,000 elements” that applies to every Java program.

For example, 100,000 elements where each element only adds an integer may be too little work to offset splitting/merging overhead; 5,000 elements where each element requires a complex CPU computation may yield a benefit. The outcome also depends on how many CPU cores are actually available to the system and whether other tasks are sharing those cores.

**Learning objective**: design a proper measurement, build a size/workload matrix, read JMH results, choose a threshold based on evidence, and recognize when to keep a stream sequential.

## 2. Mechanism Behind the Break-Even Point

A pipeline such as:

```java
long result = data.parallelStream()
        .mapToLong(Record::expensiveMetric)
        .sum();
```

may involve: splitting the source via a `Spliterator`, creating subtasks, distributing them to workers, running the mapping function, and finally merging the `sum()` result. `ForkJoinPool.commonPool()` typically participates in executing parallel streams on OpenJDK/HotSpot, and the thread invoking the terminal operation can also participate in the work. You should not assume the actual number of workers always equals the CPU core count or that each element is assigned to its own thread.

A model for **thinking**—not a formula for predicting exact JVM timing—is:

```text
T_seq(N) ≈ C_setup_seq + N × C_element

T_par(N, P) ≈ C_setup_par
             + C_split(N)
             + N × C_element / P_effective
             + C_merge(N)
             + C_contention(N)
```

Where:

- `N`: the number of elements actually processed.
- `C_element`: the processing cost per element, including mapping/filtering operations.
- `P_effective`: effective parallelism; usually **less than or equal to** actual available processing capacity, and can drop due to imbalance, memory limits, contention, and system load.
- `C_split` / `C_merge`: the cost of splitting and combining stream segments.
- `C_contention`: synchronization cost, cache/memory bandwidth contention, and shared resource contention.

Parallel only wins when the saved computation time **exceeds the total added overhead**. If per-element cost increases, the threshold N may decrease. If split/merge or contention cost increases, the threshold N may increase or **not exist** within any meaningful data range. The relationship is usually non-linear, so only an actual benchmark can confirm it.

Observable definitions:

```text
speedup(N)          = T_sequential(N) / T_parallel(N)
relativeSaving(N)   = (T_sequential(N) - T_parallel(N)) / T_sequential(N)

speedup(N) > 1: parallel has lower execution time in that measurement
speedup(N) = 1: near the break-even point
speedup(N) < 1: parallel is slower in that measurement
```

Measuring `speedup > 1` once is **not enough** to enable parallel by default. The difference must be consistent across runs, large enough relative to noise, and must not degrade other important metrics.

## 3. Variables That Shift the Threshold

| Variable | Impact on benchmark | What to control |
| --- | --- | --- |
| Element count `N` | Small N usually cannot offset parallel overhead | Test an increasing range of sizes, including points near the threshold |
| CPU work per element | Heavier computation can create speedup opportunities | Measure multiple cost levels while keeping the same logic across branches |
| Data source / `Spliterator` | `ArrayList`, arrays, and `IntStream.range` usually partition more easily than hard-to-split sources | Keep the same source across variants; re-measure when changing source types |
| Pipeline and terminal operation | `sorted`, `distinct`, `limit`, `findFirst`, `forEachOrdered`, and collectors have distinct requirements | Benchmark **the entire pipeline**, including merging/ordering operations |
| Boxing and allocation | `Stream<Integer>` can incur different costs than `IntStream` | Compare the exact data types the application uses |
| Available processors | Limits parallel execution capacity | Record `Runtime.availableProcessors()` and CPU quota |
| Cache and memory bandwidth | Can saturate before all cores are utilized | Measure small/medium/large data; monitor CPU/cache/GC when needed |
| Concurrent background load | Contention on the common pool and CPU | Measure in an isolated environment, then verify under realistic load |
| JVM/JDK and warmup | JIT, profiling, and GC alter measurements | Fix JDK/flags, warm up, and use multiple forks |

**Hard-to-split sources** cause one branch to receive too much work while leaving other workers idle. `Spliterator` characteristics such as `SIZED`/`SUBSIZED` help report size and split chunks predictably; however, checking flags alone is not enough to guarantee speedup. With linked lists, the pipeline may spend effort creating chunks; with arrays, index-based partitioning is typically favorable.

**Ordered pipelines** also have an impact. `forEachOrdered` preserves encounter order, which can limit parallel gains; `forEach` allows non-deterministic execution order. If the result does not require ordering, some pipelines may improve when `unordered()` is used semantically correctly. Do not drop ordering constraints just to improve a benchmark if business logic requires them.

**I/O work** such as network/disk/DB calls is a different workload. Using parallel streams for large volumes of blocking I/O can tie up workers and starve other tasks sharing the pool; CPU-bound benchmarks cannot be used to justify I/O-bound decisions. I/O typically requires dedicated concurrency limits and timeout management.

## 4. Designing the Measurement: Three Variants Doing the Same Work

There should be at least three ways to execute a computation:

1. **Sequential for-loop**: baseline to reveal the general overhead of the Stream API.
2. **Sequential stream**: same source and computation, calling `stream()` or `Arrays.stream(...)`.
3. **Parallel stream**: the exact same pipeline, differing only by the `parallel()` flag.

If you only compare `parallelStream()` against a for-loop, readers may confuse **Stream API overhead** with **the cost of enabling parallelism**. If you only measure the two stream variants, you should still know whether a plain loop is faster than both.

A sample experiment matrix:

| Dimension | Initial levels to test | Purpose |
| --- | --- | --- |
| `N` — element count | 1,000, 10,000, 100,000, 1,000,000 | Locate the crossover region by size |
| `work` — CPU loop iterations per element | 8, 128 | Compare light and heavy computations |
| Effective CPU count | Fixed per run; re-measure on target environment | See how the threshold shifts with hardware |
| Pipeline type | First map + sum only; then the real pipeline | Separate baseline cost from specialized operators |

The ranges above are **only a starting point**, not a list of standard Java thresholds. If the crossover occurs near 10,000, add levels like 4,000, 8,000, 12,000, and 16,000 to narrow it down; if no crossover appears, expand to the feasible data range or record the conclusion “no beneficial threshold observed”.

Each variant must:

- Read **the exact same data content**; generate input outside the timed region if data generation is not part of the application operation being optimized.
- Perform **the exact same computation** and produce **the same result** according to an appropriate comparison rule.
- Have its result consumed by the benchmark harness so the JVM cannot easily eliminate the entire workload.
- Run under equivalent JDK, heap, OS, and resource conditions.
- Not print logs, read config files, fetch network data, or generate random data **inside** the timed region unless that is what is being measured.

Do not put `Thread.sleep()` inside the compute function to simulate “CPU work”: sleep simulates waiting rather than CPU cost and easily leads to wrong conclusions.

## 5. Why a Single `System.nanoTime()` Call Is Misleading

`System.nanoTime()` is suitable for simple elapsed-time checks, but a snippet like:

```java
long start = System.nanoTime();
long sum = input.parallelStream().mapToLong(x -> x).sum();
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

is **not sufficient for performance conclusions**:

- The first run may include class loading, JIT compilation, and runtime structure initialization; subsequent runs can be dramatically faster.
- GC, OS scheduling, CPU frequency scaling, and background tasks skew individual samples.
- The JVM optimizes code based on profiles: overly simple benchmarks, unused results, or completely invariant inputs may not represent the application.
- If sequential runs first and parallel runs second, parallel may benefit from cache/warmup that sequential did not get (or vice versa).
- A single timer does not provide distribution, variance, or confidence intervals.
- Tiny datasets make harness/timer overhead account for a significant fraction.

Using `nanoTime()` for **preliminary observation or exploratory checks** can be helpful, but for microbenchmarks that determine thresholds you should use **JMH (Java Microbenchmark Harness)**. JMH supports warmup, measurement iterations, separate JVM forks, result consumption, and statistical reporting. JMH does not automatically turn a poorly designed benchmark into a reliable one: you still need to verify workload, equivalence, and environment.

## 6. Hands-On JMH: Building a Runnable Benchmark

OpenJDK recommends using the official archetype to scaffold a project with the JMH annotation processor and build configuration. **JDK 17+** and Maven are required; JDK 21 can be used to match the learning runtime.

From an empty directory with no existing Maven project, run:

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=parallel-threshold-bench -Dversion=1.0-SNAPSHOT
cd parallel-threshold-bench
```

The archetype generates the appropriate JMH configuration and dependencies; check the build/JDK used by the generated project. Create **`src/main/java/org/sample/ParallelThresholdBenchmark.java`** with the following full content:

```java
package org.sample;

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
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
@Threads(1)
@State(Scope.Thread)
public class ParallelThresholdBenchmark {
    @Param({"1000", "10000", "100000", "1000000"})
    public int size;

    @Param({"8", "128"})
    public int work;

    private int[] input;

    @Setup(Level.Trial)
    public void setup() {
        input = new int[size];
        for (int i = 0; i < size; i++) {
            input[i] = i * 31 + 7;
        }

        // Verify semantics before benchmarking; excluded from score.
        long expected = sequentialKernel();
        long actual = parallelKernel();
        if (expected != actual) {
            throw new AssertionError("Different results");
        }
    }

    private long compute(int value) {
        long x = Integer.toUnsignedLong(value);
        for (int i = 0; i < work; i++) {
            x = (x * 1664525L + 1013904223L + i) & 0xFFFF_FFFFL;
        }
        return x;
    }

    private long sequentialKernel() {
        return Arrays.stream(input)
                .mapToLong(this::compute)
                .sum();
    }

    private long parallelKernel() {
        return Arrays.stream(input)
                .parallel()
                .mapToLong(this::compute)
                .sum();
    }

    @Benchmark
    public long forLoop() {
        long sum = 0L;
        for (int value : input) {
            sum += compute(value);
        }
        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return sequentialKernel();
    }

    @Benchmark
    public long parallelStream() {
        return parallelKernel();
    }
}
```

Intentional design points:

- `@State(Scope.Thread)` gives each JMH harness worker its own state; `@Threads(1)` keeps **one JMH thread invoking the benchmark at a time**. The parallel stream inside is still allowed to use multiple JVM workers, so `@Threads(1)` **does not turn the parallel stream into sequential**.
- `@Param` generates the Cartesian product of `size` and `work`; every combination is measured for all three methods.
- `@Setup(Level.Trial)` builds the array and validates results outside the scored section. The input is deterministic; both streams read the array without modifying it during measurement.
- `compute` uses integer arithmetic and a fixed loop; the computation is **stateless** and independent per element. `long` addition produces consistent results across both execution modes; if desired, the for-loop can also be checked against `expected`.
- Each `@Benchmark` returns a `long` value. JMH consumes the result instead of letting the benchmarked method become an unobservable “no-op” call.
- `@Warmup` gives the JVM time to optimize and stabilize before recording scores; `@Measurement` measures multiple iterations, and `@Fork(2)` runs in fresh JVM processes. The annotation values are sample practical defaults and can be increased when results are noisy.

**Do not conclude from a single benchmark:** this CPU-bound array benchmark does not model allocation cost, filter predicates, collector merging, ordering, per-element skew, or I/O in a real pipeline. To make application decisions, you must benchmark **the actual pipeline** after validating the baseline measurement.

### Build and Run

```bash
mvn clean verify

# Run the full benchmark; with many combinations this may take time.
java -jar target/benchmarks.jar ParallelThresholdBenchmark -t 1 -rf csv -rff target/parallel-results.csv
```

For **quick exploration** when final decision-grade numbers are not yet needed:

```bash
java -jar target/benchmarks.jar ParallelThresholdBenchmark -t 1 -p size=1000,10000,100000 -p work=8,128 -wi 2 -i 3 -w 1s -r 1s -f 1
```

Key flags:

| Flag | Purpose |
| --- | --- |
| `-t 1` | Number of threads JMH uses to invoke the benchmark; distinct from the parallel stream’s worker count |
| `-p size=...` and `-p work=...` | Select a subset of `@Param` values to run |
| `-wi 2` and `-i 3` | Number of warmup/measurement iterations; **overrides** annotations for this run |
| `-w 1s`, `-r 1s` | Duration of each warmup/measurement iteration |
| `-f 1` | Single fork for quick exploration; formal decisions usually require multiple forks |
| `-rf csv -rff ...` | Export results to CSV for storage/comparison by parameter |

The JMH result table includes the method, params, `Mode=avgt`, `Cnt`, `Score`, `Error`, and unit (e.g., `ms/op`). For **AverageTime**, a lower score is generally better. `Error` is the statistical uncertainty reported by JMH according to its methodology; it should not be read as a guarantee of results under all real-world loads.

There is no “standard stdout” for timing: numbers vary by CPU, JDK, temperature, OS, container, JVM flags, and background tasks. If a program prints the exact same score on every machine, the measurement itself should be doubted.

## 7. Reading the Crossover Point from the Result Table

After running, group scores by the same `work` and `size`; compare the three methods separately. **Hypothetical illustrative example** (not actual measured results):

| size | work | Sequential stream (ms/op) | Parallel stream (ms/op) | Speedup | Observation |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1,000 | 8 | 0.03 | 0.30 | 0.10× | Parallel clearly loses |
| 10,000 | 8 | 0.20 | 0.34 | 0.59× | Still not beneficial |
| 100,000 | 8 | 1.90 | 1.20 | 1.58× | Signs of benefit |
| 1,000 | 128 | 0.85 | 1.10 | 0.77× | Not yet break-even |
| 10,000 | 128 | 8.20 | 3.90 | 2.10× | Signs of benefit |

These numbers **only illustrate how to read the table**, not a prediction of the program output from section 6.

For example, with `size=100000, work=8`:

```text
speedup = 1.90 / 1.20 ≈ 1.58
relativeSaving = (1.90 - 1.20) / 1.90 ≈ 36.8%
```

If error margins/variance cause the two results to overlap substantially, this cannot be called a reliable threshold. Re-measure near the crossover with more sizes, more forks, and longer iterations. A solid beneficial region should appear **consistently across adjacent sizes**, not just as a single lucky sample.

Do not force the results into a single number. A proper report might state:

- For `work=8`, parallel is not yet consistent for `N < 50000`, and becomes clearly beneficial when `N >= 100000` on the test environment.
- For `work=128`, parallel begins to pay off at a lower level on the same environment.
- On a machine with only one available CPU, no meaningful benefit was found.
- For pipelines with `forEachOrdered` or `groupingBy`, the threshold differs substantially from `mapToLong().sum()` alone.

These are **examples of conclusion formatting**; replace the figures with your project’s own measured numbers.

## 8. A Practical Process for Choosing a Usable Threshold

1. **Define winning criteria before measuring.** For example, require parallel to reduce processing time by at least 10% on the target environment with a difference exceeding observable noise; the 10% figure here is a **team-chosen** business/engineering criterion, not a Java rule.
2. **Fix test conditions.** Record JDK version, vendor, CPU, processors visible to the JVM, RAM, heap, GC, flags, OS, input type, load state, and JMH command.
3. **Measure a coarse size grid.** Use log-scale N to locate the crossover interval. Do not pick an “element-count threshold” when per-element cost varies widely without grouping by workload.
4. **Measure densely around the crossover.** Increase forks/iterations, compute `speedup`, inspect uncertainty intervals, and re-run at different times.
5. **Measure on a realistic workload.** Use production-like data distributions, filter ratios, collectors, skew levels, heap sizes, and concurrency.
6. **Evaluate system-wide impact.** Check overall throughput, CPU, GC, tail latency, fairness, and impact on other tasks sharing CPU/common pool.
7. **Codify the decision and guardrails.** Only enable parallel for regions measured as beneficial; monitor and re-evaluate when changing JDK, hardware, or pipeline.

An example decision **after measurement**, using a configurable threshold:

```java
static long sumMetrics(int[] values, int threshold) {
    var stream = Arrays.stream(values);
    if (values.length >= threshold) {
        stream = stream.parallel();
    }
    return stream.mapToLong(MyClass::metric).sum();
}
```

The snippet above **illustrates code inside `MyClass`** with a `static long metric(int)` method and `import java.util.Arrays`; it is not a standalone runnable file. `threshold` is a **tuning result** defined for a specific environment/workload and should not be filled with an arbitrary number in a lesson. If `values.length` does not reflect computation volume (e.g., 99% is filtered out), an array-size criterion can lead to wrong decisions; consider a cheaper metric that reflects actual work.

Length `N` is not always sufficient either. A dataset with a few very expensive elements and many cheap elements can cause **load imbalance**; benchmark the actual distribution and check whether partitioning can be improved.

## 9. Specific Micro-Pitfalls with Parallel Streams

### 9.1. Do Not Mutate External State in `map`/`filter`

Incorrect example where multiple elements write to the same mutable collection:

```java
List<Integer> output = new ArrayList<>();
input.parallelStream().forEach(output::add); // unsafe
```

This can cause race conditions or corrupted data. Use standard reduction/collectors:

```java
List<Integer> output = input.parallelStream().toList();
```

Both snippets above are illustrated in a scope where `input` is `List<Integer>` and `ArrayList`/`List` are imported; `Stream.toList()` has been available since Java 16. The result of `toList()` is a list that does not allow modification via standard mutators, so do not use it as a direct drop-in replacement when a mutable collection is required.

A benchmark with non-thread-safe side effects is meaningless: a “faster” computation that returns wrong results is never a good choice.

### 9.2. Beware Non-Associative Reductions

Parallel reductions require a genuinely **associative** operation so splitting/merging does not alter the result. `long` addition is associative under Java integer semantics (including modulo 2^64 overflow); subtraction and division are generally **not associative**.

With `double`, different addition orders can produce rounding differences:

```java
double a = DoubleStream.of(1e16, 1.0, -1e16).sum();
double b = DoubleStream.of(1e16, 1.0, -1e16).parallel().sum();
```

These two lines illustrate the floating-point precision issue and **do not claim** they will always print two different values on every JDK. If business logic requires tight error bounds or bit-for-bit reproducibility, design comparisons with a tolerance and/or an appropriate numerical strategy before drawing performance conclusions.

### 9.3. Remember Allocation and Collector Costs

Using `Stream<Integer>` with boxing, `Collectors.groupingBy`, `sorted`, or merging maps/lists can have vastly different allocation/merge behavior compared to `IntStream`/`LongStream` pipelines. Concurrent collectors can sometimes help when encounter order is not needed, but may trade off data ordering and contention. Measure the **complete terminal operation**—do not omit `collect()` from the benchmarked region just to get prettier numbers.

### 9.4. Benchmarks That Eliminate Work or Alter the Workload

- Do not benchmark a pipeline **without a terminal operation** and draw conclusions, because intermediate stream operations are lazy.
- Do not discard results intentionally; return a value from `@Benchmark` or use JMH `Blackhole` properly when the result is an object.
- Do not put `System.out.println` or I/O inside a mapper when measuring compute performance.
- Do not mutate the input while both streams read it; besides data races, it introduces measurement variance.
- Do not use an overly “neat” fixed workload as representative of real input; even random data needs controlled seeds and setup.

### 9.5. CPU Contention and Memory Bandwidth

In a multi-task JVM process, the common pool may already be executing other parallel streams or tasks using `ForkJoinPool.commonPool()`. A standalone microbenchmark showing a large speedup does not prove that enabling parallel for thousands of concurrent requests will improve **overall throughput**. Under high real-world load, finite cores and contention overhead can make sequential faster per request or deliver better tail latency.

Do not call `System.setProperty("java.util.concurrent.ForkJoinPool.common.parallelism", "...")` inside a benchmark body to change pool configuration between runs; this property is tied to when the common pool is initialized and affects other components. To study worker-count impact, run separate JVMs with explicit configuration flags, record the environment, and understand that capping the pool does not change physical core count.

## 10. When Should You Choose Sequential Even If Parallel Is Faster at Some Point?

- The speedup is only a few percent, smaller than measurement noise, and lacks reproducible evidence.
- Typical application inputs are smaller than the beneficial region; occasional large requests do not justify added complexity.
- The pipeline has strong ordering constraints, side effects requiring synchronization, or numerical results sensitive to merge order.
- The application is already CPU- or common-pool-saturated, and the goal is optimizing system-wide throughput/tail latency.
- Data depends on I/O, databases, or external resources; CPU measurements are not representative.
- A simple loop is already faster than both sequential and parallel streams, and the codebase does not require the Stream API.
- Simpler debugging and deterministic ordering are needed; parallel gains do not outweigh operational risk.

Do not “optimize with parallel” before measuring the bottleneck. If the heaviest part is network, locks, or allocation, switching `stream()` to `parallelStream()` may not address the root cause.

## 11. Result Checklist and Self-Assessment Exercises

When presenting benchmark findings to teammates, report at least:

| Item | Required information |
| --- | --- |
| Problem | Actual pipeline, input, expected result, side effects/ordering |
| Environment | JDK/version/vendor, OS, cores/CPU quota, heap, GC, background load |
| Benchmark design | JMH version, @Param, warmup, measurement, forks, threads, unit |
| Correctness | Sequential/parallel/for-loop produce equivalent results under defined criteria |
| Results | Score and Error by size/work; speedup; raw data/CSV |
| Decision | Beneficial region, minimum improvement, limits, and re-measurement conditions |

**Exercise 1:** Run the JMH benchmark from section 6 with `size=1000,10000,100000`, `work=8,128` on your machine. Build a `speedup` table. Is there a single shared threshold for both `work` values? Explain in terms of per-element compute cost.

**Exercise 2:** Add a variant using boxed `Stream<Integer>` and compare it with `IntStream` on the same input. Record differences in `Score` and allocation using appropriate profiling tools. Why can this result not be extrapolated to all object stream pipelines?

**Exercise 3:** Switch a source from an array to `LinkedList<Integer>` and re-measure while keeping equivalent processing logic. Observe source/splitting costs as well as any boxing/allocation overhead; do not attribute every difference solely to `Spliterator`.

**Exercise 4:** Suppose JMH measures `T_seq=2.0 ms/op` and `T_par=1.8 ms/op` at one point, but per-iteration variance is around 0.3 ms. Is there sufficient basis to set the threshold at this point? **Not yet**: more samples/forks and statistical evaluation are needed, because the difference is smaller than the observed fluctuation.

**Exercise 5:** Re-measure in an environment handling many concurrent requests. Explain why the beneficial threshold from a standalone microbenchmark may no longer hold.

## 12. Official References

- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): archetype, configuration, running JMH, examples, and benchmarking pitfalls.
- [OpenJDK JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): reference for `@State`, `@Param`, warmup, forks, and measurement techniques.
- [Java SE 21 — java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavior, parallelism, ordering, reduction, side effects.
- [Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html): `trySplit` and characteristics supporting partitioning.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing mechanism, common pool.
- [Oracle — Parallelism in Streams](https://docs.oracle.com/javase/tutorial/collections/streams/parallelism.html): choosing parallel, ordering, and requirements on side effects.
