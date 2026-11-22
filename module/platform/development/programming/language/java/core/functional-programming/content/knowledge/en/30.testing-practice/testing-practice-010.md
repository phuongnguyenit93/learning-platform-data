# Measuring Performance Properly and Synthesizing API Selection Criteria in Java Functional Programming

**The Java Stream API is not faster than a loop by default, and a loop is not the best choice for every problem by default either.** To decide between `for`/`while`, lambdas, `Stream`, primitive streams, collectors, `reduce`, or parallel streams, you must first verify **correctness**, then measure **the right kind of performance under reproducible conditions**, and weigh readability, memory, state, scalability, and business constraints.

An experiment that calls `System.nanoTime()` once and concludes “API A is twice as fast as API B” is very easy to get wrong. The JVM has **JIT compilation**, warmup, garbage collection, escape analysis, dead-code elimination, data-dependent optimizations, and runtime environment effects. Moreover, two pieces of code may return the same result on small data yet differ in semantics for ordering, duplicates, nulls, exceptions, or side effects.

This lesson belongs to **Testing and Practice** of the **Java core – functional-programming** module. The focus is on:

- Designing comparisons for **the same problem and the same result**.
- Understanding time metrics, throughput, latency, allocation, GC, and memory.
- Knowing the limits of `System.nanoTime()` and when to use **JMH**.
- Avoiding flawed benchmarks caused by JIT, constant folding, dead-code elimination, boxing, unrepresentative data, or setup costs.
- Evaluating the impact of `Stream` laziness, pipelines, stateful operations, and parallel overhead.
- Synthesizing API selection criteria by **correctness → clarity → measurable performance**.
- Providing a **standalone compilable/runnable Java 17+ program** for correctness and an illustrative timing probe, plus a JMH template with its library dependency requirements clearly noted.

## 1. Choosing an API Is a Multi-Criteria Problem

For example, computing the sum of squares of even numbers in an array:

~~~java
static long byLoop(int[] data) {
    long sum = 0L;
    for (int n : data) {
        if ((n & 1) == 0) {
            sum += (long) n * n;
        }
    }
    return sum;
}
~~~

A primitive stream version:

~~~java
static long byIntStream(int[] data) {
    return Arrays.stream(data)
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

Both pieces of code have the same goal: traverse input data, select even numbers, square them, and sum into `long`. However, identical semantics are guaranteed only if arithmetic, exception handling, and input ranges are compatible.

A boxed Stream version:

~~~java
static long byBoxedStream(int[] data) {
    return Arrays.stream(data).boxed()
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

A parallel version:

~~~java
static long byParallelStream(int[] data) {
    return Arrays.stream(data).parallel()
        .filter(n -> (n & 1) == 0)
        .mapToLong(n -> (long) n * n)
        .sum();
}
~~~

All four **can be correct**. However, overhead, boxing, task splitting, CPU load, caching, and JIT optimization opportunities differ. A benchmark is meaningful only when variants **perform the same required work**, rather than one skipping validation or producing less output data.

### 1.1. Reasonable decision order

1. **Correctness**: results, nulls, overflow, ordering, duplicates, lifecycle, and errors must be right.
2. **Maintainability**: method names, data contracts, pipeline clarity, and testability.
3. **Resource usage**: allocations, peak memory, I/O, GC, and contention.
4. **Performance**: average time, throughput, tail latency, scalability under real load.
5. **Operational safety**: production behavior, observability, cancellation, retries, and concurrency.

Do not pick an API merely because of a lower nanosecond reading in one run. An approach that is a few percent faster in a microbenchmark can make code harder to understand or introduce serious race risks.

## 2. First Prove Two Approaches Are Equivalent

Before comparing times, write tests to prove:

- Same **input dataset** and filter conditions.
- Same result type and same overflow/rounding rules.
- Same **ordering and duplicate** rules if the problem is order-dependent.
- Same handling of **nulls, empty inputs, and invalid inputs**.
- Neither version secretly mutates the source or relies on external mutable state.
- For single-use Stream sources, a **fresh stream is created** for each measurement.

Example:

~~~java
int[] data = IntStream.rangeClosed(1, 200_000).toArray();

long a = byLoop(data);
long b = byIntStream(data);
long c = byBoxedStream(data);
long d = byParallelStream(data);

if (!(a == b && a == c && a == d)) {
    throw new AssertionError("Algorithms differ");
}
~~~

The snippet above assumes the methods are already defined. This problem uses `long` for squares and sum to avoid `int` overflow from `n*n` when `n` is large; casting **`(long) n * n`** before multiplication is essential.

### 2.1. Do not compare two APIs performing different logic

The following pairs are **not equivalent**, unless the problem explicitly defines them so:

~~~java
stream.sorted(comparator).findFirst();
stream.min(comparator);
~~~

Both can pick an equal extremum when comparator/tie semantics match, but `sorted` has different cost and ordering semantics. Do not use `sorted` just to get `min` when `min` directly satisfies the requirement.

~~~java
stream.filter(predicate).count();
stream.map(sideEffectingMapper).count();
~~~

If the requirement is to count elements matching a predicate, the two approaches are not the same problem. Adding a side effect to `map` is not a reliable way to measure “how many elements actually ran” because Stream may optimize away callbacks that do not affect the terminal result.

### 2.2. Run unit tests before benchmarking

Tests should cover data such as:

- Empty and single-element inputs.
- Many duplicate elements.
- Negative numbers, 0, integer boundaries, and large sums.
- Null values when allowed by the API contract.
- Mutable input state shared across multiple callers.
- Both ordered and unordered cases, if that is a dimension of the problem.
- Parallel output when aggregation has appropriate identity, associativity, and compatibility.

If results differ, **stop measuring** and fix correctness first. Never try to use benchmarks to explain away logic bugs.

## 3. What to Measure? Latency, Throughput, Allocation, and Tail

“Running fast” has multiple meanings.

| Metric | Meaning | When valuable |
| --- | --- | --- |
| Time per operation | Time for one operation | Microbenchmarking an algorithm |
| Throughput | Operations completed per unit time | Processing many requests/batches |
| p50/p95/p99 latency | Response time percentiles | Systems needing consistent latency |
| Allocation rate | Bytes allocated per op/second | Finding boxing/object overhead |
| GC activity | GC counts/pauses/time | Allocation-heavy workloads |
| Peak memory | Peak memory during processing | Large data, `sorted`/`grouping` |
| CPU utilization | CPU usage across cores | Analyzing parallel speedup |
| Scalability | Change as data or workers grow | Batch/parallel processing |

**High throughput does not mean low p99 latency.** A parallel stream may improve batch throughput while consuming many CPUs, increasing latency for other requests on the same JVM. A very fast computation that allocates many objects can create GC pressure when run millions of times.

### 3.1. Wall-clock time vs. CPU time

`System.nanoTime()` measures **elapsed time between two points** in the same JVM, suitable for measuring relative short elapsed times. It **does not** directly report CPU time consumed by a single thread, nor exclude scheduling, GC, page faults, or hardware noise.

For parallel workloads, elapsed time may drop even while **total CPU work** increases because multiple threads run simultaneously. When optimizing server throughput/cost, observe both elapsed time and resource usage.

### 3.2. Units and how to report

Results of 5 ms/op and 200 ops/s may describe the same workload, but conditions must be stated. When reporting, always state:

- Unit: ns/op, us/op, ms/op, or ops/s.
- Data: element count and value distribution.
- Mode: sequential or parallel, worker/CPU count.
- Environment: JDK version, heap settings, OS, CPU.
- Execution: warmup, measurement iterations, forks.
- Results: distribution and variance; do not pick only a minimum number and claim it is faster.

## 4. Why Calling `System.nanoTime()` Once Is Not Enough

A short manual measurement:

~~~java
long start = System.nanoTime();
long result = byIntStream(data);
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

This measures **elapsed time of a single call**, not a reliable benchmark for comparing APIs.

Major sources of distortion:

1. **Class loading / initialization** can happen on the first call.
2. **JIT compilation** needs time and execution profiles to optimize code.
3. **Tiered compilation** can change code quality across runs.
4. **GC** can pause or run during the measurement window.
5. **OS scheduler** can preempt threads or change CPU placement.
6. **CPU frequency/temperature** can vary due to turbo boost or thermal throttling.
7. **Code/data caches** differ between warm and cold inputs.
8. **Dead-code elimination** can remove work if the result is unused.
9. **Constant folding** can replace computations with precomputed values.
10. **Benchmark overhead** can dominate measurements that are too small.
11. **Allocation / escape analysis** can make measured code behave differently from production code.
12. **Background load** from other processes adds timing noise.

Therefore, running a few iterations in `main` cannot replace a dedicated benchmark harness.

### 4.1. What is warmup?

The JVM can run code in interpreter/lower compilation tiers before reaching an optimized state for an execution pattern. **Warmup** runs the workload before the measurement phase so JIT has a chance to optimize and classes are loaded.

However, warmup **is not magic**: it must be sufficient and match the workload, and it does not guarantee CPU temperature/GC or caches match production. If a real application must respond quickly on cold start, then **startup/cold latency** is a separate metric, and you cannot skip warmup entirely and call the result standard for every goal.

### 4.2. Forks and JVM state

Running benchmarks in multiple **separate JVM processes** reduces dependence on the JIT/heap state of a single run. JMH calls these runs forks.

Numbers from a single process after one warmup can be skewed. Observe results across **multiple forks, multiple measurement iterations**, and variance. The goal is evidence-based conclusions, not picking the prettiest run.

## 5. JMH: The Right Tool for Java Microbenchmarks

**JMH (Java Microbenchmark Harness)** is designed for benchmarking small JVM code snippets. It provides a model for benchmark methods, warmup, measurement, forks, measurement modes, and mechanisms to mitigate common optimization pitfalls.

JMH does not automatically turn a flawed benchmark into a valid one: if two benchmarks process different data, use unrepresentative inputs, or share mutable state unsafely, results remain meaningless.

### 5.1. Illustrative JMH template

The following snippet **is not part of the standard JDK**. It requires a project with JMH dependencies and annotation processing/build configuration. It is a template to understand measurement structure, not code you can run directly with `javac` without dependencies.

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class SumBenchmarks {
    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = IntStream.rangeClosed(1, size).toArray();
    }

    @Benchmark
    public long loop() {
        long sum = 0;
        for (int value : values) {
            if ((value & 1) == 0) {
                sum += (long) value * value;
            }
        }
        return sum;
    }

    @Benchmark
    public long primitiveStream() {
        return Arrays.stream(values)
            .filter(v -> (v & 1) == 0)
            .mapToLong(v -> (long) v * v)
            .sum();
    }

    @Benchmark
    public long boxedStream() {
        return Arrays.stream(values).boxed()
            .filter(v -> (v & 1) == 0)
            .mapToLong(v -> (long) v * v)
            .sum();
    }
}
~~~

How to read it:

- **@State(Scope.Thread)**: each benchmark thread gets its own state, avoiding sharing a mutable array across benchmark threads.
- **@Param**: runs multiple data sizes, because a conclusion at n=1,000 may not hold at n=1,000,000.
- **@Setup(Level.Trial)**: creates data before measurement, avoiding mixing array creation cost into every call when the goal is **the cost of processing an existing array**.
- **@Benchmark**: each method represents one variant of the same computation.
- **@Warmup / @Measurement**: separates warmup iterations from data-collection iterations.
- **@Fork(3)**: runs in multiple independent JVM processes.
- **AverageTime**: measures average time per operation per JMH configuration.
- **Return long**: lets JMH observe the benchmark's result, helping prevent the entire computation from being eliminated as unused.

Verify that variants **return equal results using unit tests** outside the benchmark; JMH does not compare two computations for business correctness.

### 5.2. Choosing the right setup scope

If production receives an already-existing array and only sums it, keeping **array creation** outside the timed region is reasonable.

If production must **read a file, parse, filter, map, and write results**, benchmarking only mapping an in-memory array is too narrow to evaluate the entire pipeline. In that case, an **end-to-end benchmark** is needed covering I/O, parsing, allocation, and downstream side effects at appropriate boundaries.

State the question clearly:

- “What is the cost of **processing** an already-created array?” → setup outside measurement.
- “What is the cost of **creating and processing** a new batch?” → measure allocation/setup in a dedicated workload.
- “What is real request latency under load?” → use load testing / application profiling, not just JMH microbenchmarks.

### 5.3. Blackhole and dead-code elimination

A computation whose result is unused can be eliminated or simplified by the JIT. JMH provides **Blackhole** to consume observed results when not returned directly:

~~~java
@Benchmark
public void benchmark(Blackhole blackhole) {
    long result = compute();
    blackhole.consume(result);
}
~~~

This is an illustrative fragment inside a JMH class with appropriate imports, not a pure JDK program. `compute()` is application-defined.

Do not put `System.out.println` inside a benchmark method: console I/O has high cost and noise, making results no longer reflect the algorithm.

### 5.4. When is returning the result enough?

With `@Benchmark` returning `long`, JMH consumes the result to prevent optimizing away the whole work. If there are multiple results, use `Blackhole` or a meaningful combined result. However, **do not try to trick the JIT with a mutable global variable**, as that makes the measurement differ from the code you want optimized.

### 5.5. Limitations of JMH

JMH is great for microbenchmarks, but **does not automatically predict** production latency. Production also involves:

- Concurrent users, network, DB, and storage.
- GC pressure from many other components.
- CPU quotas/container limits.
- Task scheduling and thread contention.
- Real data, exceptions, and cache misses.
- Connection pools, transaction boundaries, and retries.

Use JMH to understand a specific piece of code, then confirm with profiling/load testing on a near-production system.

## 6. Very Common Benchmarking Mistakes

### 6.1. Measuring two approaches that do different work

You cannot compare a collector that builds a full List against `count` returning a single number and claim `count` is faster “in all cases”. The two APIs return **different results**, so the question must match.

### 6.2. Ignoring results so work gets optimized away

~~~java
long start = System.nanoTime();
computeSomething();
long end = System.nanoTime();
~~~

If `computeSomething` is pure and its result is discarded, the compiler/JIT can eliminate or simplify the work. Use JMH and an observed result.

### 6.3. Doing setup in one variant but not the other

One side calls `new Random()`, builds a List, boxes, and copies; the other uses a prebuilt array. If you want to measure an algorithm on prepared data, **do not mix these costs asymmetrically**.

### 6.4. Using overly simple constant inputs

A single number pattern can let the JIT specialize unusually or keep caches artificially hot. Use multiple meaningful sizes, distributions, and patterns; consider pre-generated random data with a recorded seed for reproducibility.

### 6.5. Ignoring allocations

Two variants may have similar timings, yet one allocates many boxed objects, temporary Lists, or new Strings; under heavy load, GC can slow that variant down noticeably. Use JMH GC profiler, JFR, or an appropriate allocation profiler to observe.

### 6.6. Picking only the best number

The lowest value across a series of runs may reflect unusually favorable conditions, not typical system behavior. Report the distribution across multiple iterations/forks and interpret confidence.

### 6.7. Same JVM running workloads in a fixed order

Always benchmarking A then B can give B different JIT, cache, or CPU thermal state than A. A harness coordinates better; still, multiple independent measurements and order effects must be considered.

### 6.8. Using parallel streams with shared mutable state

If one variant increments a shared `AtomicInteger` or mutates an `ArrayList` from multiple threads, it both differs in semantics and suffers contention. Do not treat that as a fair comparison against a pure reduction.

### 6.9. Skipping warmup or mis-measuring cold start

Microbenchmarks targeting steady-state differ from startup benchmarks. Design two separate measurements when the system needs both.

### 6.10. Disabling GC or tuning heap arbitrarily for nicer numbers

JVM flags affect results. If you tune heap/GC, document it and explain why it reflects deployment. Do not use results from one configuration to claim behavior across all environments.

## 7. Stream vs. `for` Loop: How to Choose in Applications

**Stream** usually expresses a pipeline of transformations, filters, and collection well. A **for loop** is usually suited for imperative algorithms, small sequential state, complex short-circuiting, or ultra-hot paths where profiling shows significant pipeline overhead.

| Need | Usually clearer choice | Notes |
| --- | --- | --- |
| Filter then transform objects | `filter().map().toList()` | Callbacks should be stateless/non-interfering |
| Sum `int`/`long` numbers | `IntStream`/`LongStream.sum()` | Avoid boxing and check overflow |
| Count valid elements | `filter(...).count()` | Do not use `AtomicInteger` as a holder just to count |
| Find first matching element | `filter(...).findFirst()` | Can short-circuit |
| Find any matching element | `findAny()` | Can differ from `findFirst` in parallel |
| Group by key | `collect(groupingBy(...))` | Watch memory/Map type |
| Build Map from records | `toMap` or `groupingBy` | Handle duplicate keys explicitly |
| Multiple imperative branches | `for`/`while` | Clear state variables, `break`/`continue` |
| Ultra-hot path, simple loop | `for` or primitive stream | Benchmark on real workload |
| Heavy independent CPU work | `parallel` stream or executor | Measure overhead, thread safety |
| Blocking I/O | Appropriate async/executor API | Parallel stream is not suitable by default |

**Maintainability is a real criterion.** A pipeline with five nested lambdas, three nested collectors, and side effects can be harder to read than a 15-line loop. Conversely, a loop with four temporary collections can be clearer when written as `filter`/`map`/`collect`.

### 7.1. Do not use Stream just to make code shorter

~~~java
List<String> normalized = names.stream()
    .filter(s -> !s.isBlank())
    .map(String::trim)
    .map(String::toLowerCase)
    .toList();
~~~

The snippet above illustrates pipeline expression. However, in locale-sensitive cases, default `String.toLowerCase()` depends on the environment locale: if results must be deterministic, choose an explicit `Locale` per business rules.

If the requirement is to check for empty strings **after trimming**, the step order must change. **Pipeline correctness matters more than compact-looking syntax.**

## 8. Primitive Streams and Boxing: Prefer When Data Is Numeric

Primitive streams **`IntStream`, `LongStream`, `DoubleStream`** process numbers without boxing every element into wrapper objects in many cases.

~~~java
long sum = Arrays.stream(data)
    .filter(n -> n > 0)
    .mapToLong(n -> (long) n * n)
    .sum();
~~~

Compared to:

~~~java
long sum = Arrays.stream(data).boxed()
    .filter(n -> n > 0)
    .mapToLong(n -> (long) n * n)
    .sum();
~~~

The boxed version can add overhead from `Integer` wrappers and conversions. However, the JVM may optimize part of this, so **do not claim a fixed speedup ratio**. Measure on real data, JDK, and pipelines.

### 8.1. `mapToInt`, `mapToLong`, and type limits

If squaring an `int` can overflow, write:

~~~java
.mapToLong(n -> (long) n * n)
~~~

rather than:

~~~java
.mapToLong(n -> n * n)
~~~

In the second version, **`int` multiplication happens first** before widening to `long`. A benchmark can run very fast yet produce wrong results if this rule is forgotten.

### 8.2. When boxed objects are required

Many generic APIs, `Optional<T>`, or collectors require objects. Boxing when needed is fine. Only avoid **unnecessary** boxing in hot loops, especially when a primitive stream already provides the corresponding terminal operation.

## 9. Choosing Between `collect`, `reduce`, and Loops

### 9.1. `reduce` for valid combining operations

~~~java
long total = numbers.stream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

If you have a custom aggregation, `reduce` is appropriate when there is an **identity**, an **associative** operator, and for three-argument `reduce`, a **compatible** accumulator/combiner.

Do not use a mutable `ArrayList` or `StringBuilder` as an identity and mutate it across parallel `reduce`. For building mutable containers, **`collect`** is usually more appropriate.

### 9.2. `collect` for structured results

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

This is a fragment with a hypothetical `Employee` record. If you only need the element count, `count()` is clearer. If you need **a map of counts by group**, `groupingBy`/`counting` is the right tool. Comparing these two APIs only makes sense when output goals are equivalent.

### 9.3. Do not optimize just to eliminate a `for` loop

A plain loop over an array can be very fast and readable. Yet in an object-transformation pipeline, Stream can clarify business steps. Decisions should consider:

- Is this path on a hot path?
- Is the data large enough for overhead differences to matter?
- Are there many allocations from boxing/collectors?
- Do ordering, duplicate, null, and exception semantics need to be preserved?
- Are measurements reproducible under near-production conditions?
- Does changing the API hurt maintainability?

## 10. Parallel Stream: Worth Using Only When Conditions Are Met

A parallel stream can split a pipeline into tasks running across multiple cores. However, it **does not automatically guarantee faster execution**.

Favorable conditions:

1. Source is large enough and **splits easily**, like arrays or index ranges.
2. Per-element work is **heavy enough** to offset scheduling/merging overhead.
3. Lambdas are **stateless**, not mutating the source or external mutable state.
4. Aggregation has proper **identity/associativity/compatibility**.
5. Real CPU resources are available, not heavily throttled by container quotas.
6. Not running inside a system whose threads/CPUs are already saturated.
7. Benchmarks show gains **on real workloads**, not just a developer laptop.

Cases to avoid or treat with great caution:

- Only a few hundred elements with cheap operations.
- Blocking I/O without a dedicated concurrency design.
- Ordered stateful pipelines like `sorted`/`limit` or `forEachOrdered` with coordination cost.
- A shared `AtomicInteger` counter inside callbacks causing contention.
- Shared mutable structures or `Spliterator` sources that split poorly.
- Request-serving servers sharing CPU and thread pool resources.

### 10.1. Parallel does not reduce total CPU work

Suppose a computation needs 100 ms of total CPU time. Running in parallel can reduce elapsed time when idle cores exist, but splitting/merging overhead and cache coherence can make total CPU time **higher**. If a server is handling many concurrent requests, adding parallelism can reduce overall system throughput.

### 10.2. Verify parallel correctness first

Summing can be correct if the reduction is valid. However:

~~~java
List<Integer> output = new ArrayList<>();

numbers.parallelStream()
    .forEach(output::add);
~~~

This is **buggy illustrative code**: `ArrayList` is not designed for unsynchronized concurrent `add` calls from multiple threads. It can cause races or corrupted data.

Replace with:

~~~java
List<Integer> output = numbers.parallelStream()
    .toList();
~~~

`Stream.toList` on Java 17 returns an **unmodifiable** List while following the Stream contract for results/encounter order. If a mutable `ArrayList` is needed, use a collector or copy appropriately after collecting.

### 10.3. Test multiple sizes

A benchmark should run multiple sizes `n`. For small `n`, sequential can win due to overhead. For large `n` and heavy enough work, parallel can win. **There is no single size threshold for every API or machine.**

## 11. Statefulness, Short-Circuiting, and Memory Cost

Some intermediate operations like `filter`/`map` can fuse to process element by element, avoiding intermediate Lists.

Conversely:

- **`sorted()`** may require buffering and sorting cost.
- **`distinct()`** may require state to remember seen elements.
- **`collect(groupingBy)`** must build a Map and child containers.
- **`toList()`** must store the finite collected results.
- **`limit`/`findFirst`/`anyMatch`** can stop early depending on contract and situation.
- **`count()`** can sometimes optimize away callbacks if the source size is known.

### 11.1. Benchmarks must respect lazy evaluation semantics

A wrong example trying to “measure map” by only building a pipeline:

~~~java
long start = System.nanoTime();
Stream<Integer> pipeline = Stream.of(1, 2, 3)
    .map(x -> x * x);
long elapsed = System.nanoTime() - start;
~~~

There is no terminal operation here; the benchmark mainly measures **pipeline construction cost**, not squaring each element.

To measure processing:

~~~java
List<Integer> result = Stream.of(1, 2, 3)
    .map(x -> x * x)
    .toList();
~~~

However, you must decide whether source creation and result List creation belong inside the benchmark scope, and keep that criterion consistent across variants.

### 11.2. Do not count callbacks as a business result

~~~java
AtomicInteger sideCount = new AtomicInteger();

long result = List.of(1, 2, 3).stream()
    .map(n -> {
        sideCount.incrementAndGet();
        return n * 2;
    })
    .count();
~~~

The JVM can know the source size and skip the mapper because it does not affect `count`. Thus **`sideCount` is not a valid tool for counting processed elements**. If you need a count, use terminal `count`; if you need to benchmark `map`, measure a result that actually uses the mapped values.

## 12. Benchmark Data Must Be Representative

Input size is only one dimension. Also consider:

- **Data distribution:** do most elements pass the filter or only a small fraction?
- **Duplicate rate:** affects `distinct`, `groupingBy`, and Map hashing.
- **Key cardinality:** many groups or few? Is distribution skewed?
- **Input ordering:** already sorted or random?
- **String/object size:** affects parsing, mapping, and allocation.
- **Cache locality:** contiguous arrays differ from scattered List objects.
- **Nulls / exceptions:** use realistic inputs, without accidentally making exceptions part of only one variant's work.
- **Sufficient memory:** large batches can trigger paging or OOM.
- **I/O source:** is data in RAM, page cache, or disk/network?
- **Environment concurrency:** are there concurrent requests, background GC, or shared pools?

A benchmark on a 10-element List does not reliably predict `groupingBy` performance on one million records with tens of thousands of keys.

### 12.1. Use a fixed seed for reproducibility

If generating pseudo-random input, fix the seed and generate data **outside the measured region** when data generation cost is not part of the goal. If you want to measure data generation too, create a separate benchmark.

Do not call `new Random().nextInt()` inside one variant while its competitor processes pre-generated data — that compares two different workloads.

## 13. Self-Runnable Java 17+ Program: Correctness First, Timing Reference Only

The following program intentionally separates:

- **Deterministic stdout**: verifies identical results, even-element count, sum, grouping, unmodifiable List, and an observable sink.
- **Non-deterministic stderr**: a few `nanoTime` results from trial runs. They only teach how to read elapsed time, **not a standard benchmark to rank APIs**.

Create the file **`ApiChoiceBenchmarkDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.LongSupplier;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ApiChoiceBenchmarkDemo {
    private static volatile long observed;

    record Sale(String region, int amount) {}

    static long byLoop(int[] data) {
        long sum = 0;
        for (int n : data) {
            if ((n & 1) == 0) {
                sum += (long) n * n;
            }
        }
        return sum;
    }

    static long byIntStream(int[] data) {
        return Arrays.stream(data)
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static long byBoxedStream(int[] data) {
        return Arrays.stream(data).boxed()
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static long byParallelStream(int[] data) {
        return Arrays.stream(data).parallel()
            .filter(n -> (n & 1) == 0)
            .mapToLong(n -> (long) n * n)
            .sum();
    }

    static void roughProbe(String label, LongSupplier task) {
        for (int i = 0; i < 30; i++) {
            observed = task.getAsLong();
        }
        long best = Long.MAX_VALUE;
        for (int i = 0; i < 8; i++) {
            long start = System.nanoTime();
            long result = task.getAsLong();
            long elapsed = System.nanoTime() - start;
            observed = result;
            best = Math.min(best, elapsed);
        }
        System.err.println(label + ": demo_best_ns=" + best);
    }

    public static void main(String[] args) {
        int[] data = IntStream.rangeClosed(1, 200_000).toArray();

        long loop = byLoop(data);
        long primitive = byIntStream(data);
        long boxed = byBoxedStream(data);
        long parallel = byParallelStream(data);

        System.out.println("sameResult=" +
            (loop == primitive && loop == boxed && loop == parallel));
        System.out.println("evenCount=" + Arrays.stream(data)
            .filter(n -> (n & 1) == 0).count());
        System.out.println("sum=" + loop);

        List<Sale> sales = List.of(
            new Sale("North", 10),
            new Sale("South", 25),
            new Sale("North", 15)
        );
        Map<String, Long> counts = sales.stream().collect(
            Collectors.groupingBy(Sale::region, TreeMap::new,
                Collectors.counting()));
        System.out.println("counts=" + counts);

        List<String> labels = sales.stream()
            .map(Sale::region).distinct().sorted().toList();
        System.out.println("labels=" + labels);
        try {
            labels.add("East");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        roughProbe("loop", () -> byLoop(data));
        roughProbe("primitive", () -> byIntStream(data));
        roughProbe("boxed", () -> byBoxedStream(data));
        roughProbe("parallel", () -> byParallelStream(data));

        System.out.println("observedMatches=" + (observed == loop));
    }
}
~~~

Compile and run on **JDK 17 or higher**:

~~~bash
javac ApiChoiceBenchmarkDemo.java
java ApiChoiceBenchmarkDemo
~~~

**Verified deterministic stdout:**

~~~text
sameResult=true
evenCount=100000
sum=1333353333400000
counts={North=2, South=1}
labels=[North, South]
unmodifiable=true
observedMatches=true
~~~

**Stderr has timings that vary by machine and run**, shaped like:

~~~text
loop: demo_best_ns=<measured value>
primitive: demo_best_ns=<measured value>
boxed: demo_best_ns=<measured value>
parallel: demo_best_ns=<measured value>
~~~

Those four lines are **format illustrations**, not fixed stdout/stderr to match verbatim. **Do not use `roughProbe` timing values to claim which API is better.** This function only does minimal warmup and picks the minimum time, without forks, distribution statistics, GC profiling, or reliable JMH configuration.

### 13.1. Analyzing stdout

**sameResult=true:** all four variants produce equal sums for 1..200,000.

**evenCount=100000:** among 200,000 consecutive positive integers there are exactly 100,000 even numbers.

**sum=1333353333400000:** sum of squares of even numbers from 2 to 200,000. All squaring is widened to `long` before multiplication, avoiding `int` overflow.

**counts:** three `Sale` records grouped by region; North has two, South has one. `TreeMap::new` makes key print order predictable.

**labels:** `distinct` combined with `sorted` produces a list of two region names in natural order.

**unmodifiable=true:** `Stream.toList` on Java 17 returns an unmodifiable List, so `add` throws `UnsupportedOperationException`.

**observedMatches=true:** results of calls through `roughProbe` were stored/observed, helping avoid some dead-code cases, yet **not turning manual timing into a standard microbenchmark**.

### 13.2. Why not report an exact timing number?

`System.nanoTime()` depends on the machine's execution time, JDK/JIT, CPU, GC, scheduling, and environment conditions. Writing stdout like “primitive is always 120,000 ns faster” would **fabricate a non-existent property**. This lesson only reports deterministic output and describes the timing format transparently.

### 13.3. Is `volatile observed` necessary?

The `volatile` variable acts as an illustrative sink for return values in `roughProbe`. It introduces overhead and affects optimization, which is another reason **not to interpret `roughProbe` values as production benchmarks**. With JMH, return the result or use `Blackhole` per harness design instead of building a global sink.

## 14. Summary of API Selection Criteria

| Situation | API to consider first | What to check |
| --- | --- | --- |
| Pipeline filtering and mapping | `Stream.filter`/`map`/`toList` | Statelessness, order, nulls, allocation |
| Summing primitive numbers | `IntStream`/`LongStream.sum` | Overflow, avoid boxing |
| Counting elements | `Stream.count` | Do not use side-effect counters |
| Finding an element by condition | `findFirst`/`findAny` | Encounter order, `Optional`, short-circuiting |
| Finding min/max | `min`/`max` with `Comparator` | Tie-breaking, nulls, avoid unnecessary `sorted` |
| Checking existence | `anyMatch`/`allMatch`/`noneMatch` | Short-circuiting, pure functions |
| Converting List to Map | `Collectors.toMap` | Duplicate keys, merge, nulls |
| Grouping data | `groupingBy`/`partitioningBy` | Memory, value type, key distribution |
| Aggregating values | `reduce` or primitive `sum` | Identity, associativity, compatibility |
| Building a mutable container | `collect` or built-in collector | Supplier, combiner, mutable state |
| Joining strings from parts | `Collectors.joining` | Separator, prefix/suffix, allocation |
| Computing multiple statistics | `summarizingInt`/`teeing` | Result type, overflow |
| Stateful loop with `break`/`continue` | `for`/`while` | Clearer than multi-branch pipelines |
| Heavy, independent CPU work | `parallel` stream | Splitting, CPU cores, overhead, correctness |
| I/O or async processing | Appropriate I/O, executor, async API | Closing, blocking, cancellation |
| Short hot path | `for` or primitive stream | JMH before optimizing |
| Systems with critical p99 latency | Measure end-to-end | Do not look only at microbenchmarks |

This table is a **starting point**, not a command to use a single API exclusively. Choose based on semantics, maintainability, data, and real measurements.

## 15. How to Write a Credible Benchmark Report

A minimal report should include:

**Question:** “On the same JVM/JDK, given an already-created `int` array, which approach computes the sum of squares of even numbers most efficiently in time/op and allocation?”

**Workload:** Sizes 1,000, 100,000, and 1,000,000; data distribution description; same `long` return type; same filter.

**Correctness:** Variants produce equal sums; empty, negative/boundary inputs, and overflow policy tested.

**Environment:** JDK version/build, CPU, cores/threads, OS, heap, GC, container quotas if any.

**Method:** JMH mode, warmup iterations, measurement iterations, forks, and thread count; disclose any non-default JVM flags.

**Results:** Time/op or throughput per size, variance, allocation/GC if relevant; do not copy just one run's number.

**Interpretation:** Is the difference significant and consistent? Does it depend on size? Can production code be changed without altering semantics? Is overall performance confirmed on a near-real workload?

**Decision:** Choose the API for specific reasons, stating trade-offs and conditions requiring re-measurement.

### 15.1. Do not hide unexpected results

If a loop is faster than a stream at one size, do not conclude the Stream API is inferior in all situations. If parallel is faster on a one-million-element batch, do not conclude it fits a server handling many concurrent requests.

Look at **the conditions producing the result**, not just table rankings.

### 15.2. Re-measure when the environment changes

A decision may need revisiting when updating:

- JDK version or GC.
- CPU/core count or container limits.
- Data size or distribution.
- Service thread concurrency.
- Pipeline changes adding `sorted`/`distinct`/`collect`.
- Heap, target latency, or memory requirements.
- How the code is called in the application.

Compilers/JITs and runtimes improve over time, so do not “freeze” benchmark conclusions from an old JDK for all future versions.

## 16. Common API Selection Mistakes

**Mistake 1 — Optimizing before measuring.** Writing complex code just assuming an API is faster. Start with correct, clear code, and measure after identifying bottlenecks.

**Mistake 2 — Benchmarks that do not return a result.** JIT can eliminate the work; use JMH return values or `Blackhole`.

**Mistake 3 — Measuring pipeline construction and claiming element processing was measured.** Intermediate Stream operations are lazy; use a terminal operation matching the goal.

**Mistake 4 — Comparing two approaches that return different data.** Do not pit `count` against `toList` when one side needs a full List.

**Mistake 5 — Forgetting boxing.** `Stream<Integer>` can have different overhead from `IntStream`; measure two semantically equivalent versions.

**Mistake 6 — Letting `int` multiplication overflow before casting.** A benchmark may run very fast yet return wrong results; cast before multiplying.

**Mistake 7 — Measuring without warmup.** First runs are affected by class loading/JIT and do not represent steady-state.

**Mistake 8 — Measuring in only one JVM.** Forks and multiple iterations are needed when making microbenchmark decisions.

**Mistake 9 — Looking only at nanoseconds and forgetting allocation/GC.** Object creation cost can degrade performance as load increases.

**Mistake 10 — Using only a single small array.** Multiple input sizes and distributions must be tested.

**Mistake 11 — Using parallel regardless of workload.** For very cheap computations and small inputs, overhead can outweigh benefits.

**Mistake 12 — Shared mutable state in parallel streams.** Causes races or contention; use appropriate collectors/reductions.

**Mistake 13 — Thinking an atomic counter accurately measures callback count.** Streams can optimize/short-circuit; side effects must not be business metrics.

**Mistake 14 — Relying on `HashMap` iteration order in tests.** Choose an ordered Map or compare Map contents, not unguaranteed output order.

**Mistake 15 — Ignoring output collection characteristics.** `Stream.toList` is unmodifiable; if downstream needs a mutable List, design accordingly.

**Mistake 16 — Looking only at averages, not p99.** Server latency can suffer from GC/scheduling even when microbenchmark averages look good.

**Mistake 17 — Putting I/O on one side but not the other.** Measure the same end-to-end scope or separate costs cleanly.

**Mistake 18 — Confusing JMH with load testing.** Microbenchmarking one method is not enough to conclude a multi-user system is faster.

**Mistake 19 — Inferring speed from API names.** “Parallel” does not mean fast; “functional” does not mean slow; “imperative” does not mean optimal.

**Mistake 20 — Optimizing in ways that alter the business contract.** Changing `forEachOrdered` to `forEach` can break side-effect order; changing `findFirst` to `findAny` can change results; changing `Map` to `Set` can lose duplicates.

## 17. Code Review Checklist

- Is there a clearly defined **benchmark question**?
- Do variants have **the same semantics** and identical exception handling?
- Were results verified before measuring?
- Does the data represent real workloads rather than a few convenient values?
- Is setup separated from the measured region?
- Are there enough warmups, forks, and measurement iterations?
- Are results consumed to prevent dead-code elimination?
- Are JDK/JVM flags and machine specs recorded?
- Are allocation/GC observed when needed?
- Are throughput and p99 considered instead of only average?
- Does the pipeline have heavy boxing, `sorted`, `distinct`, or `collect`?
- Is there shared mutable state or atomic counter contention?
- Does parallel have enough work and enough CPU cores?
- Is the chosen API easier to test and read?
- Does it need re-measurement in a production-like workload?

## 18. Self-Check Questions

1. Why is a single `System.nanoTime` call insufficient to conclude Stream is faster than a `for` loop?
2. How do warmup and JIT compilation affect measurements?
3. What is the benefit of forks in JMH?
4. How can dead-code elimination and constant folding invalidate a benchmark?
5. Why should a benchmark method return its result or use `Blackhole`?
6. When should setup be included in the measurement?
7. What kinds of overhead distinguish primitive `IntStream` from boxed `Stream<Integer>`?
8. Why must a squaring operation cast to `long` before multiplying?
9. What does it mean to compare two APIs with the same semantics?
10. Why are `count` and `toList` not directly comparable options in every problem?
11. How can a parallel stream reduce elapsed time while increasing total CPU work?
12. When is a `for` loop clearer than a Stream pipeline?
13. Why is a shared `ArrayList` in parallel `forEach` dangerous?
14. Distinguish average latency, throughput, and p99 latency.
15. When data has many duplicate keys, how can `groupingBy` performance differ?
16. Why should side effects in `map`/`peek` not be used to check processing counts?
17. What statistical guarantees distinguish `System.nanoTime` from JMH?
18. Can a very fast benchmark that produces wrong result ordering be accepted?
19. When upgrading the JDK or changing data distribution, should you re-measure?
20. What information must be included in a performance report so others can reproduce it?

**Conclusion:** Choose Java Functional Programming APIs based on **correctness, clarity, resource cost, and reproducible measurements**, not intuition about `Stream` or `parallel` keywords. For microbenchmarks, use **JMH with multiple sizes, warmups, forks, and actually consumed results**, while checking allocation/GC when needed. For real systems, confirm further with profiling and load tests. Streams, primitive streams, `reduce`, `collect`, and `for` loops are all valid tools; the right API is the one that solves the problem correctly with **the lowest complexity and proven sufficient performance**.
