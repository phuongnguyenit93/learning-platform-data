# Benchmarking Before Choosing Parallel Streams for a Specific Problem

## 1. Why can you not assume `parallel()` is faster?

In the Java Stream API, you can switch a sequential pipeline to parallel processing quite easily:

~~~java
long sequential = numbers.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallel = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Or on the same kind of source:

~~~java
long total = Arrays.stream(values)
        .parallel()
        .mapToLong(x -> x * 2L)
        .sum();
~~~

**Easy to write does not mean always more efficient.** Parallel processing has overhead for splitting work, scheduling, creating/coordinating tasks, and merging results. With small data or overly simple transformations, total overhead can exceed the time saved. On multi-core machines, speed is also bounded by memory bandwidth, actual available CPUs, system load, and data source characteristics.

Therefore, before choosing `parallel()` in real production code, answer using **measurements on a representative workload**, not intuition or a single run:

1. Does the parallel pipeline produce **the same correct result** as sequential per business requirements?
2. How large is the real data, and what is the distribution and selectivity of `filter`?
3. Is the per-element computation cost large enough to offset overhead?
4. Are you measuring **latency**, **throughput**, or both? Under concurrent load, do the results change?
5. How much CPU, heap, and memory bandwidth is required to achieve the improvement?
6. Are results reproducible across warm-up, multiple measurement iterations, and real deployment environments?

This lesson uses Java 17+, providing a benchmarking workflow, a runnable example, and pitfalls that skew measurements.

## 2. Understand both execution modes before measuring

### 2.1. Sequential Stream

~~~java
int sum = Arrays.stream(new int[]{1, 2, 3})
        .map(x -> x * x)
        .sum();
~~~

Normally, a sequential pipeline executes work on the single thread that calls the terminal operation. `map`/`filter` steps are lazy intermediate operations: a terminal operation like `sum`, `toList`, or `collect` is what triggers source traversal.

### 2.2. Parallel Stream

~~~java
int sum = Arrays.stream(new int[]{1, 2, 3})
        .parallel()
        .map(x -> x * x)
        .sum();
~~~

`parallel()` sets the pipeline's execution mode to parallel; it does **not** start computation when called. When the terminal runs, the implementation may split the source via `Spliterator`, distribute tasks on a fork/join mechanism, and combine results.

In common cases, parallel streams use the JVM's **common ForkJoinPool**. However, do not build assumptions that every context or every callback always runs on exactly N threads in the pool or that each operation has its own pool. Pool policy, calling context, JVM environment, and other tasks can affect execution.

### 2.3. Two source variants

~~~java
// With Collection:
List<Integer> list = List.of(1, 2, 3);
long a = list.stream().parallel()
        .mapToLong(Integer::longValue)
        .sum();
long b = list.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

// With primitive array:
int[] array = {1, 2, 3};
long c = Arrays.stream(array).parallel()
        .mapToLong(Integer::longValue)
        .sum();
~~~

On `Collection`, `parallelStream()` creates a stream in parallel mode right from the source. `stream().parallel()` switches the pipeline's mode. When choosing a strategy, the important thing is to measure equivalent pipelines and **not accidentally compare a primitive array stream against a boxed object stream**.

## 3. Timing model: overhead and ideal speed

A simple model to visualize:

\[
T_{\mathrm{sequential}}\approx T_{\mathrm{work}},
\]

\[
T_{\mathrm{parallel}}\approx
T_{\mathrm{split}}+
T_{\mathrm{schedule}}+
T_{\mathrm{work\ on\ workers}}+
T_{\mathrm{combine}}+
T_{\mathrm{contention}}.
\]

This is an explanatory model, **not an exact predictive formula** for a specific application. If the work portion is small, `T_split` + `T_schedule` + `T_combine` can dominate. If each element is CPU-heavy and the source splits evenly, worker computation time can drop significantly.

**Speedup** is defined as:

\[
S = \frac{T_{\mathrm{sequential}}}{T_{\mathrm{parallel}}}.
\]

- `S > 1`: parallel is faster under the measurement being considered.
- `S = 1`: equivalent time.
- `S < 1`: parallel is slower.

Hypothetical example: sequential 120 ms, parallel 50 ms gives a speedup of `120/50 = 2.4x`. These numbers only illustrate the calculation, **not an actual benchmark from the learner's machine**.

Do not expect four cores to necessarily be four times faster. Some work cannot be parallelized, and speed is bounded by shared resources. Amdahl's law is a mental framework for the speedup ceiling when only part of the work is parallelizable; the real ceiling is also affected by overhead and many system factors.

## 4. Only measure after ensuring the two pipelines are equivalent

Measurements are only meaningful when comparing the same business requirement.

~~~java
long sequential = Arrays.stream(values)
        .mapToLong(Work::compute)
        .sum();

long parallel = Arrays.stream(values)
        .parallel()
        .mapToLong(Work::compute)
        .sum();

if (sequential != parallel) {
    throw new AssertionError("Different results");
}
~~~

`Work::compute` represents a pure computation function taking `int` and returning `long`; the full example in section 10 defines this function. For `long` addition, overflow under Java arithmetic has deterministic behavior (64-bit modulo), so the sum of values does not depend on grouping under the same `long` addition operator. However, business requirements may not accept overflow; in that case, choose different types and algorithms.

Some aggregations **do not guarantee identical results** if grouping order changes:

~~~java
// Dangerous example if you expect subtraction to preserve semantics:
int result = IntStream.of(20, 3, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Subtraction is not associative, so a reduction like the above does not satisfy the algebraic requirements of `reduce`. With `double`, floating-point addition has rounding errors and can yield different results depending on combination order; check using **an appropriate error tolerance**, rather than assuming strict bitwise equality.

With data having encounter order and requiring an ordered list, do not casually replace `toList()` with side-effecting `forEach` and conclude it is faster. If the two pipelines have different output contracts, it is not a fair comparison.

## 5. Choosing representative test data

### 5.1. Source size (N)

A benchmark with only `N = 100` can reach a completely different conclusion than `N = 1_000_000`. Choose levels close to real data and add a small region to find the crossover point where parallel begins to pay off:

~~~text
N = 100
N = 10_000
N = 100_000
N = 1_000_000
~~~

The sizes above are **sample scenarios**, not universal thresholds for Java. The actual crossover varies by per-element work, source, and machine.

### 5.2. Computation cost per element

Compare two workload types:

~~~java
// Very light work:
.mapToLong(x -> x + 1L)

// More CPU-heavy work:
.mapToLong(x -> expensivePureCalculation(x))
~~~

A simple addition usually lacks enough work to amortize parallel overhead. A multi-loop computation function may have a chance to benefit, but must still be measured. Do not use `Thread.sleep` to simulate CPU load: sleep is waiting, not CPU-bound; parallelizing blocking I/O/sleep on the common pool carries separate risks.

### 5.3. Source splittability

`Arrays.stream(int[])` and `IntStream.range(...)` have relatively favorable splittable sources. A source generated via an iterator or an unevenly splitting `Spliterator` can limit parallel potential. Sources like line-by-line processing, tokenization, or I/O often have sequential parts or synchronization overhead.

Explicitly record **the source** in your benchmark, not just element count and map function. Switching from `ArrayList<Integer>` to `int[]` also changes boxing, locality, and memory footprint, which is a separate variable beyond "sequential vs. parallel".

### 5.4. Selectivity and data distribution

`filter(x -> condition(x))` with 1% of elements passing can behave differently from 99% passing. `findAny`, `anyMatch`, and `findFirst` short-circuit: the position of matching elements changes how much work is done. Test "early match", "late match", and "no match" cases if they occur in production.

## 6. Designing JVM benchmarks: warm-up, multiple runs, statistics

Running once with `System.nanoTime()` and drawing conclusions from the result is insufficient, because the JVM has JIT compilation, class loading, garbage collection, CPU scaling, and an OS running many background tasks.

### 6.1. Warm-up

Run the same workload several times before measuring to reduce the impact of unoptimized JIT and class loading:

~~~java
for (int i = 0; i < 10; i++) {
    result = operation.getAsLong();
}
~~~

**The number 10 is illustrative only.** Whether warm-up is sufficient depends on result stability and the benchmarking tool; there is no single constant suitable for every JVM and problem.

### 6.2. Measuring multiple rounds

Perform multiple measurement rounds and analyze metrics such as median and dispersion, not just a single minimum number. Re-run the whole program or benchmark forks to observe variance across processes.

### 6.3. Alternating measurement order

If you always measure sequential first and parallel second, changes in CPU temperature, warm-up, caches, and background load can bias one method. Alternate the order, or use a benchmark framework that controls multiple iterations/forks.

### 6.4. Avoiding dead-code elimination

If the computation result is never observed, the JIT may eliminate some of the work you think you are measuring. In simple examples, you can store into a **`volatile` sink** or use the result in a correctness check; for serious benchmarks, use JMH's anti-elimination mechanisms (such as `Blackhole`) per framework design.

### 6.5. Do not accidentally include data preparation in the measurement

If the goal is comparing **pipeline cost**, create the data array before measuring. If the goal is **full request** latency, measure data conversion, pipeline creation, and required serialization together. Both can be valid, but they answer different questions.

## 7. Latency, throughput, CPU, and memory: there is more than one metric

| Metric | Question | Notes |
| --- | --- | --- |
| Per-operation latency | How fast does one request complete? | Measure p50/p95/p99 if there are many requests |
| Throughput | How many requests/sec are processed? | Per-request parallelism can contend for CPU with other requests |
| CPU utilization | How much CPU resource is used? | Faster speed while consuming more cores is not always better |
| Allocation/GC | Does it create more objects and trigger more GC? | Distinguish primitive streams from boxed streams |
| Stability | Do results fluctuate with load/hardware? | Run multiple trials, scales, and times |
| Correctness | Are results right in element set, order, and arithmetic? | Mandatory check before evaluating performance |

Example: one request drops from 100 ms to 60 ms by using most of the machine's CPUs, yet a system receiving 20 concurrent requests may lose overall throughput because requests contend for the same common pool/CPU. When choosing parallel in a server service, evaluate **the whole system under expected concurrency**, not just a single isolated request.

If processing is tiny compared to network/database I/O, optimizing `stream().parallel()` may bring no noticeable improvement to overall request latency. Use profiling to identify the real bottleneck.

## 8. Factors that make parallel slower

### 8.1. Splitting and merging overhead

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .filter(x -> x >= 0)
        .count();
~~~

With 100 elements and a simple condition, task creation/coordination overhead can overwhelm any gain. Do not use this example to claim a fixed slowdown ratio; measure on the specific machine and JVM.

### 8.2. Boxing and intermediate objects

~~~java
// Primitive pipeline:
long sum = IntStream.range(0, n)
        .parallel()
        .mapToLong(i -> i * 2L)
        .sum();

// Reference pipeline with boxing:
long sum2 = IntStream.range(0, n)
        .boxed()
        .parallel()
        .mapToLong(i -> i * 2L)
        .sum();
~~~

If only integers are needed, staying on primitive streams can reduce boxing and allocation. When comparing sequential/parallel, do not simultaneously change the data strategy; otherwise you can no longer isolate the cause.

### 8.3. Stateful operations and ordering constraints

Operations like `sorted`, `distinct`, and certain stateful operations can force data coordination/buffering. `limit` and `skip` on ordered sources in a parallel stream can also be expensive when encounter order must be maintained.

~~~java
List<Integer> topTen = numbers.parallelStream()
        .sorted()
        .limit(10)
        .toList();
~~~

This pipeline has a specific goal, but you cannot infer that adding `parallel()` definitely makes it fast. Sorting, preserving order, and slicing elements can dominate parallel mapping.

**Do not use `unordered()` just to speed up if the application needs order.** Removing the encounter-order constraint can change result semantics, especially with `findFirst` or `limit`.

### 8.4. Synchronization and contention overhead

~~~java
// Avoid sharing mutable state between callbacks:
List<Integer> result = new ArrayList<>();

// Unsafe in parallel:
// numbers.parallelStream().forEach(result::add);
~~~

`ArrayList` is not thread-safe for concurrent additions. Using `collect` or `toList` is more appropriate:

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(x -> x > 0)
        .toList();
~~~

Putting a synchronized lock around `result.add` can reduce race risks, yet creates contention that can wipe out parallel gains. If correctness is only achieved via a global lock point, revisit the design.

### 8.5. Actually available CPU

`Runtime.getRuntime().availableProcessors()` only reports the processor count the JVM sees at call time, not a guarantee that the application always has that much free CPU. Container quotas, resource limits, other processes' load, temperature, turbo boost, and memory all affect measurements.

To compare between two environments, record the JDK version, reported CPU count, container limits if any, RAM, OS, JVM flags, and overall load.

## 9. Distinguishing CPU-bound work from blocking I/O

Parallel Stream is generally most suitable to consider when **each element has independent CPU-bound work** and the source can split relatively evenly.

If a callback queries HTTP, calls a database, or waits on the filesystem:

~~~java
// Just an example of what NOT to blindly switch to parallel:
// urls.parallelStream().map(this::fetchRemote).toList();
~~~

That is a **blocking I/O** operation. Waiting calls can occupy common pool workers for long periods, affecting other workloads and failing to provide the concurrency limits, timeouts, and backpressure a dedicated I/O client needs. Explicitly design thread pools, concurrent request limits, timeouts, retries, and appropriate resource management; do not use `parallelStream` as a general-purpose async solution.

**Do not benchmark with `Thread.sleep(10)` and conclude parallel stream optimizes CPU-heavy work.** Sleep increases wait time; the test does not represent actual computation cost.

## 10. Complete Java 17+ program for initial experimentation

The example below intentionally **does not print a specific timing**: timings are empirical data that vary by machine and run. The program checks result equivalence between sequential and parallel, warms up, runs a few comparison rounds, and prints only formatted measurements.

This is a **microbenchmark illustrating how to think**, not yet a reliable benchmark like JMH. Use it to observe skew risks and form hypotheses before setting up rigorous measurements.

Create file **`ParallelMeasurementDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.function.LongSupplier;

public class ParallelMeasurementDemo {
    // Make results observed; does not replace JMH Blackhole.
    private static volatile long sink;

    // Pure, independent computation function per element.
    static long compute(int input) {
        long x = input + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 64; i++) {
            x ^= (x >>> 13);
            x *= 0xBF58476D1CE4E5B9L;
            x ^= (x >>> 17);
        }
        return x;
    }

    static long sequential(int[] input) {
        return Arrays.stream(input)
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    static long parallel(int[] input) {
        return Arrays.stream(input)
                .parallel()
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    static long measureNanos(LongSupplier task, int repeats) {
        long total = 0L;
        for (int i = 0; i < repeats; i++) {
            long start = System.nanoTime();
            long value = task.getAsLong();
            long elapsed = System.nanoTime() - start;
            sink = value;
            total += elapsed;
        }
        return total / repeats;
    }

    public static void main(String[] args) {
        int n = 100_000;
        int[] data = new int[n];
        for (int i = 0; i < n; i++) {
            data[i] = i * 31 + 7;
        }

        // Verify correctness before any speed comparison.
        long expected = sequential(data);
        long parallelValue = parallel(data);
        if (expected != parallelValue) {
            throw new AssertionError("Mismatch");
        }
        System.out.println("resultsEqual=true");
        System.out.println("elements=" + data.length);

        // Warm up both branches before measuring.
        for (int i = 0; i < 12; i++) {
            sink = sequential(data);
            sink = parallel(data);
        }

        // Measure in alternating order; simple example, does not replace JMH.
        long sequentialTotal = 0;
        long parallelTotal = 0;
        int rounds = 6;
        for (int i = 0; i < rounds; i++) {
            if (i % 2 == 0) {
                sequentialTotal += measureNanos(() -> sequential(data), 1);
                parallelTotal += measureNanos(() -> parallel(data), 1);
            } else {
                parallelTotal += measureNanos(() -> parallel(data), 1);
                sequentialTotal += measureNanos(() -> sequential(data), 1);
            }
        }

        double seqMillis = sequentialTotal / (rounds * 1_000_000.0);
        double parMillis = parallelTotal / (rounds * 1_000_000.0);
        System.out.printf(Locale.ROOT,
                "sequentialAvgMs=%.3f%n", seqMillis);
        System.out.printf(Locale.ROOT,
                "parallelAvgMs=%.3f%n", parMillis);
        System.out.println("speedupDependsOnEnvironment=true");
    }
}
~~~

Compile and run:

~~~bash
javac ParallelMeasurementDemo.java
java ParallelMeasurementDemo
~~~

**Result lines verifiable independently of the machine:**

~~~text
resultsEqual=true
elements=100000
sequentialAvgMs=<actual measured value>
parallelAvgMs=<actual measured value>
speedupDependsOnEnvironment=true
~~~

The two `<actual measured value>` lines are descriptive placeholders, **not verbatim stdout**; the program will print actual decimal numbers like `123.456` depending on the runtime environment. There is no single millisecond number valid for every machine. Because the loop simulates a CPU workload, timing and speedup are especially sensitive to JIT, processor, and background load.

### 10.1. What is and is not controlled?

Partially controlled:

- The `int[]` source is pre-created, excluding data initialization time from each measurement.
- The two pipelines differ primarily in `parallel()`.
- The `compute` function performs no I/O and mutates no external state.
- Results are checked as `long` values and written to `volatile sink`.
- Warm-up is included and measurement order alternates across rounds.

Not fully controlled:

- No multiple independent JVM forks.
- Does not use JMH to mitigate compiler effects, sampling, and dead-code elimination.
- Round and warm-up counts are chosen for **illustration**, not proven to have converged.
- Results use **arithmetic mean**, without distribution or confidence intervals.
- The common pool may be shared by other tasks in the same JVM.
- Does not measure CPU time, allocation rate, GC, throughput under load, or tail latency.

This is why a manual program like the above should not be used as the sole proof to enable `parallel()` in production.

## 11. Using JMH for more reliable microbenchmarks

**JMH (Java Microbenchmark Harness)** is OpenJDK's benchmarking tool for Java/JVM, commonly used to measure short code snippets with high risk of JIT skew. JMH is not part of the default JDK: you must add its dependency/plugin or create a separate JMH project.

Skeleton example **for illustration, not a standalone plain-JDK Java file**:

~~~java
@State(Scope.Thread)
public class StreamBenchmark {
    private int[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = new int[100_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i * 31 + 7;
        }
    }

    @Benchmark
    public long sequential() {
        return Arrays.stream(data)
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }

    @Benchmark
    public long parallel() {
        return Arrays.stream(data)
                .parallel()
                .mapToLong(ParallelMeasurementDemo::compute)
                .sum();
    }
}
~~~

The JMH snippet above **assumes**:

- JMH dependencies/imports are configured, such as `org.openjdk.jmh.annotations.*`.
- `ParallelMeasurementDemo.compute` is included in the same project or replaced by a computation function defined in the benchmark; this example is only to clarify structure, not standalone copy-paste code.
- The benchmark is executed using an appropriate JMH runner and configuration.

Concepts to configure:

| JMH concept | Role |
| --- | --- |
| `@Benchmark` | Marks the method to measure |
| `@State` | Manages data and sharing scope |
| `@Setup` | Prepares fixtures before measuring |
| Warmup iterations | Warms up the JVM and measured code |
| Measurement iterations | Collects samples after warm-up |
| Forks | Launches a fresh JVM to reduce prior process state effects |
| Benchmark mode | Chooses AverageTime, Throughput, or an appropriate mode |
| `Blackhole`/return value | Ensures results are consumed, limiting unwanted optimizations |

A special detail when measuring **parallel streams**: each benchmark invocation can trigger multiple workers, so two benchmarks "called by one thread" do not have the same CPU usage. When measuring throughput with multiple benchmark threads, each invocation also using the pool makes contention more complex. Clearly separate single-request benchmarks from concurrent multi-request throughput benchmarks.

**Choose JMH when the goal is microbenchmarking a Java operation; choose end-to-end load testing when the goal is optimizing an entire service.** Both are needed if a change affects tail latency or resource contention across requests.

## 12. Designing a benchmark matrix before concluding

Instead of a single pair of results, build a matrix of meaningful cases:

| Case | Element count | Work/element | Source | What to verify |
| --- | ---: | --- | --- | --- |
| Small, light | 100 | `x + 1` | `int[]` | Parallel overhead may dominate |
| Medium, light | 10,000 | `x + 1` | `int[]` | Whether a break-even point exists |
| Large, CPU-heavy | 100,000 | Multi-loop function | `int[]` | Real parallel benefit exists |
| Very large, CPU-heavy | 1,000,000 | Multi-loop function | `int[]` | Whether memory or CPU becomes the bottleneck |
| Boxed data | 100,000 | Multi-loop function | `List<Integer>` | Boxing and locality impact |
| Stateful pipeline | 100,000 | `sorted` or `distinct` | Representative source | Coordination/ordering cost |
| Multi-request | Per production workload | CPU-heavy | Server environment | Throughput, tail latency, contention |

These sizes and descriptions are **test-design suggestions**, not measured results or decision thresholds. For each case, keep the sequential and parallel pipelines identical in source, predicates, results, and environment.

Only compare code versions that are identical except for execution mode; if you want to test boxing optimizations or switching collectors, isolate that into **a separate experiment**.

### 12.1. Comparing multiple environments

You can test on a local developer machine and a staging/production-like environment, but do not assume local results apply directly to CPU-quota-limited containers. Record:

- JDK vendor/version, JVM flags, heap/GC configuration.
- Physical/logical CPUs and CPU quota/container limits.
- OS, CPU architecture, background load conditions.
- Source size, data types, and distribution.
- Number of warm-up iterations, measurement iterations, and forks.
- Number of benchmark threads/concurrent requests.
- Median/mean, dispersion, allocation, GC, throughput, and tail latency where applicable.

## 13. Analyzing decision scenarios

### 13.1. Scenario A — small data, light mapper

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
~~~

There are three elements and each mapper is short. The need for parallel is unclear and overhead is very likely not worthwhile. **Prefer sequential** until representative measurements prove otherwise.

### 13.2. Scenario B — many independent computations

~~~java
long total = Arrays.stream(largeIntArray)
        .parallel()
        .mapToLong(this::expensivePureCalculation)
        .sum();
~~~

If `expensivePureCalculation` is CPU-bound, stateless, each element is independent, and the source is large, parallel has a chance to speed up. However, the result is only valid if the function uses no mutable shared state and the aggregation satisfies associativity. Benchmark at sufficient scale and real load.

### 13.3. Scenario C — exact element order required

~~~java
List<String> labels = names.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

On a `List` source with encounter order, `toList()` preserves order. However, operations like `forEach` can have different execution orders; if ordered output is needed, you cannot arbitrarily swap terminals. Order-preservation constraints can reduce speedup, especially with stateful operations like `limit`.

### 13.4. Scenario D — busy server system

A REST request that turns on parallel stream to "borrow" multiple CPUs may reduce that request's latency when alone, yet contend for resources when dozens of requests run concurrently. Do not optimize only a single request under zero load. Measure throughput and p95/p99 under representative traffic, noting that the common pool may be shared with other code.

### 13.5. Scenario E — callback accesses a database

Do not assume `parallelStream` is the solution for running multiple queries concurrently. Queries have network cost and database systems have their own connection pools/limits; opening many concurrent requests can slow down the database or overload it. Fixing N+1 queries, batching, caching, and controlling concurrency usually matter far more than switching Stream mode.

## 14. Common benchmarking and interpretation mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Measuring once and concluding | JIT/GC/OS cause high variance | Warm up, measure multiple times and forks |
| Looking only at best time | Picks a lucky sample, unrepresentative | Report median/mean and dispersion |
| Not checking results | Pipeline might change order or break reduction | Test correctness before measuring |
| Ignoring data-prep cost | Measures a different end-to-end question | Define measurement scope clearly |
| Creating boxed `List` in parallel, `int[]` in sequential | Different sources, unisolated results | Fix source and types |
| Using `Thread.sleep` to simulate CPU work | Measures blocking, not CPU computation | Use real workload or realistic CPU-bound work |
| Using side-effecting `map` to count | Callback may be optimized or run out of order | Use terminals/collectors with clear semantics |
| Treating `parallel()` as a multi-core guarantee | Depends on Spliterator, pool, quota, workload | Measure and inspect environment |
| Measuring one request, ignoring multi-request load | CPU/common pool contention under concurrency | Load-test throughput and tail latency |
| Assuming all `reduce` ops are associative | Subtraction and floating point have issues | Choose valid aggregations/tolerances |
| Using `unordered()` to optimize without checking correctness | Can alter element selection and order | Preserve business semantics |
| Interpreting speedup > 1 as always enable | Can consume significantly more resources | Evaluate CPU, GC, latency, and throughput |
| Benchmarking with unrealistic data | Wrong caching and distribution skew conclusions | Use representative datasets/sizes |
| Running JMH without controlling benchmark threads | Parallel per invocation uses multiple workers | Separate single-request and concurrent-load tests |

## 15. Repeatable decision process

1. **Define the goal:** optimizing single-operation latency, service throughput, or CPU efficiency?
2. **Write a semantically correct sequential baseline**, preferring pure functions and primitive streams where appropriate.
3. **Create a parallel version differing only in mode**, without changing logic, source, or result construction.
4. **Verify correctness** on empty, small, large, boundary, and realistic distributions. For floating point, define a reasonable tolerance.
5. **Microbenchmark** with JMH if the operation is small enough and needs detailed comparison; ensure warm-up, measurement, forks, and result observation.
6. **End-to-end benchmark** when the operation sits inside a request/application with I/O and resource contention.
7. **Observe metrics beyond speed** such as throughput, p95/p99, CPU, allocation/GC, and memory.
8. **Weigh cost and complexity:** if the benefit is smaller than measurement noise or hurts throughput under load, keep the sequential version.
9. **Document the decision:** workload, environment, measurement method, numbers, acceptance criteria, and conditions requiring re-benchmarking.
10. **Re-measure when things change**—JDK, hardware, CPU quota, data, or code; do not assume performance stays fixed over time.

Enabling parallel should be the result of a **repeatable experiment**, not a word-of-mouth "10,000-element size rule".

## 16. Self-check exercises

**Question 1.** Why is `IntStream.range(0,100).parallel().sum()` not necessarily faster than `IntStream.range(0,100).sum()`?

**Answer:** The aggregation work is tiny, while parallel adds overhead for splitting, scheduling, and merging results. You must measure; there is no speedup guarantee.

**Question 2.** Given two pipelines identical except for `parallel()`, what must be checked before comparing times?

**Answer:** Both pipelines must produce business-equivalent results, including required ordering and arithmetic rules; no side effects/races breaking correctness.

**Question 3.** Why is the first measurement with `System.nanoTime()` easily skewed?

**Answer:** Class loading, JIT, warm-up, GC, CPU scaling, and background processes can make timing differ from steady-state runs. Use warm-up, multiple iterations, and JMH for serious microbenchmarks.

**Question 4.** Is a single-request parallel benchmark running 30% faster enough to choose it in a REST service?

**Answer:** Not yet. You need to measure throughput and latency under multiple concurrent requests, CPU usage, and impact on the common ForkJoinPool and GC/heap. A single-request gain can make the overall system slower.

**Question 5.** Why should you not compare a sequential pipeline on `int[]` against a parallel one on `List<Integer>`?

**Answer:** Differences in boxing, locality, source, allocation cost, and `Spliterator` make it hard to isolate the gain/loss from parallelization.

**Question 6.** Does parallel `findAny` always return a different element each time and run faster than `findFirst`?

**Answer:** No. `findAny` guarantees neither random results nor faster speed; it is simply free to pick any matching element without having to preserve the "first" requirement in encounter order. Measure real workloads and check whether the selection is acceptable.

**Question 7.** When a pipeline makes HTTP calls for each element, is `parallelStream` the best way to control concurrency?

**Answer:** Should not be used by default. Blocking I/O, the common pool, connection limits, timeouts, and retries need dedicated design. Benchmark end-to-end and use an appropriate I/O/concurrency model.

**Question 8.** If both versions are correct and parallel is 5% faster in a single measurement run, is that enough evidence to enable it?

**Answer:** No. A small difference can fall within measurement noise; repeat runs, report variance, and evaluate impact under load. If gains are unstable or increase resource consumption, keep the simpler version.

## 17. Takeaways

**The decision to use parallel Stream is a data-driven decision, not a syntax-driven one.** Remember:

- `parallel()` does not make every pipeline faster; overhead can exceed time saved.
- **Correctness first, performance second.** Only compare pipelines equivalent in data, ordering, and aggregation.
- Compare on data and computations **representative of production**, including multiple source sizes and concurrent load.
- Warm up the JVM, measure multiple times, and control dead-code elimination; use **JMH** for serious microbenchmarks and load tests for systems.
- Also evaluate throughput, tail latency, CPU, heap, and allocation/GC; single-request speedup does not tell the whole story.
- Consider costs of splitting, boxing, hard-to-split sources, stateful operations, order preservation, contention, and the common pool.
- Do not use parallel Stream as a default solution for blocking I/O or mutable side effects.
- Record measurement conditions and re-check when data/hardware/JVM changes.

Without reliable benchmark results for the specific case, **prefer the simple, correct, maintainable sequential version**, and only enable parallelism when evidence shows the benefit is genuinely worthwhile.