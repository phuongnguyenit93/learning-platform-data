# Choosing Sequential vs. Parallel Processing Based on Measurement in Java 17

The Java Stream API allows processing a data source in two modes: **sequential streams** and **parallel streams**. Calling `parallel()` allows a pipeline to execute across multiple worker threads, but that does not mean the program is always faster. Splitting work, scheduling, coordination, synchronization, and merging results all carry costs. For small datasets or very fast per-element operations, the overhead can outweigh the benefit of using multiple CPU cores.

Making the right choice depends on **workload characteristics and measurements in an environment close to production**. A pipeline should run in parallel when the work can be split effectively, each piece is large enough to offset orchestration costs, operations are independent, and merging results does not create a bottleneck. Before measuring, sequential is a simple and predictable starting point.

Java 17 includes stable Stream API and parallel stream support. This lesson focuses on how to analyze, benchmark, and make decisions; no preview features are used.

## 1. How Do Sequential and Parallel Streams Differ?

A sequential stream executes the pipeline sequentially. Elements are processed in a single pipeline execution flow, following encounter order when the source and operations define an order.

~~~java
long total = values.stream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

A parallel stream splits the work into chunks and executes those chunks across multiple worker threads, typically via `ForkJoinPool.commonPool()` for standard parallel streams.

~~~java
long total = values.parallelStream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

The two snippets express the same computation if the pipeline obeys Stream API requirements. The integer sum within the non-overflow range is identical; runtime can vary depending on data size, per-element processing cost, hardware, and environment.

### Parallel Does Not Mean One Thread Per Element

A parallel stream does not spawn a new thread for each element. The data source is partitioned into chunks, those chunks are submitted to the parallel execution framework, and workers can process multiple chunks as scheduled by the pool. The thread count does not necessarily equal the element count or chunk count.

A parallel pipeline can:

1. Split the data source into smaller chunks.
2. Schedule those chunks onto workers.
3. Execute intermediate operations on each chunk.
4. Compute partial results locally.
5. Merge partial results into the final result.

Splitting and merging also consume CPU, allocate objects, or synchronize. For small tasks, this overhead can exceed the useful computation time.

## 2. Cost Model: When Does Parallel Have a Chance to Be Faster?

You can think of parallel runtime as:

~~~text
Parallel time
  = startup/orchestration overhead
  + chunk processing time
  + synchronization and contention cost
  + result merging cost
  + memory, GC, and system effects
~~~

Meanwhile, sequential runtime consists mainly of:

~~~text
Sequential time
  = source traversal time
  + operation execution time
  + related allocation and memory cost
~~~

Parallel only pays off when the splittable work is large enough to save more time than total overhead costs. A simple multiplication over a few hundred elements rarely has enough work to offset task-splitting overhead. A CPU-heavy computation over millions of independent elements can utilize multiple cores far better.

### Amdahl's Law and the Non-Parallelizable Portion

If the parallelizable fraction of work is $P$, the non-parallelizable fraction is $1 - P$, and there are $N$ ideal workers, the maximum speedup is approximated by:

\[
S(N) = \frac{1}{(1-P)+\frac{P}{N}}
\]

For example, if 90% of runtime is parallelizable and 10% is sequential, then even with a very large number of workers, speedup remains capped by that 10% portion. In practice, overhead, contention, and memory limits make actual speedup lower than the ideal model.

Do not look solely at CPU core count to predict gains. A pipeline can be bottlenecked by RAM bandwidth, cache misses, allocation/GC, I/O, or a shared lock rather than CPU compute capacity.

## 3. Workloads That Often Benefit from Parallel Streams

Parallel streams are worth testing when there are many elements, per-element operations are relatively CPU-intensive, and elements can be processed independently.

Examples:

- Numeric computations or pure data transformations over large datasets.
- In-memory data analysis and aggregation.
- Transforming images or numeric arrays across independent blocks, if algorithms and libraries used are thread-safe.
- Computing per-record features without accessing contended shared resources.
- Simulations or batch processing that split cleanly into independent parts and merge efficiently.

~~~java
long count = values.parallelStream()
        .filter(value -> expensivePredicate(value))
        .count();
~~~

If `expensivePredicate` is a pure, time-consuming CPU calculation with no side effects, the pipeline has an opportunity to leverage multiple cores.

However, calling something "heavy" is not enough to conclude. If the computation calls an internally synchronized library or reads from a contended locked region, workers may just wait on each other. You must measure the actual workload.

## 4. Workloads That Should Usually Stay Sequential

Sequential is usually more suitable when:

- The data source is small.
- Each element only performs a very cheap operation.
- The pipeline allocates many intermediate objects or causes heavy boxing/unboxing.
- Elements depend on results from previous elements.
- Logic requires strict execution order.
- There is extensive shared mutable state or locking.
- The work primarily waits on I/O or external service calls.
- Splitting the source and merging results is more complex than the computation itself.

Example:

~~~java
int total = smallList.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

For a small list, parallel can add overhead without noticeably reducing runtime.

### I/O-Bound Work Is Not Automatically Suited for Parallel Streams

If every element makes an HTTP call, reads a file, or queries a database, most of the time is spent waiting on I/O. Using a parallel stream can tie up common pool workers while waiting, hurting other tasks sharing that pool. Furthermore, concurrent requests may exceed connection pool limits or service rate limits.

For I/O, consider asynchronous APIs, dedicated bounded executors, backpressure mechanisms, or appropriate batching designs. Java 17 does not have official virtual threads yet; do not put Java 21 virtual thread features into Java 17 code. Parallel streams target splitting data-processing work, not general-purpose I/O concurrency management.

## 5. Data Sources and Splittability

Parallel streams rely on the source's ability to split. The Stream API uses `Spliterator` to traverse and partition data sources into chunks.

A source that splits evenly and cheaply is generally more favorable than one hard to partition. For example:

| Source | Typical splittability | Notes |
| --- | --- | --- |
| Arrays | Good | Known size and indices; fast range splitting |
| ArrayList | Good | Can split by index ranges |
| IntStream.range | Good | Numeric range partitions easily |
| HashSet/HashMap | Depends on data and structure | Splittable, though bucket size/distribution affects balance |
| LinkedList | Worse than arrays/ArrayList | Positional access and chunk splitting can be costlier |
| Custom Iterator | Depends on Spliterator | Without efficient `trySplit`, parallelism yields little benefit |
| I/O stream or sequential source | Often difficult | Must weigh reading cost and partitionability |

`Spliterator` has important characteristics:

- `SIZED`: exact remaining element count is known.
- `SUBSIZED`: child spliterators also know their exact sizes.
- `ORDERED`: has an encounter order.
- `DISTINCT`: elements are unique per `equals`.
- `SORTED`: has a sorted order.
- `IMMUTABLE`: source cannot change during traversal.
- `CONCURRENT`: source supports concurrent updates per contract.

These characteristics help the Stream API choose execution strategies and optimizations. Not every source has all characteristics. If writing a custom `Spliterator`, implement `trySplit()` efficiently and declare `characteristics()` accurately for its behavior.

### Inspecting a Source's Splittability

You can inspect a `Spliterator`:

~~~java
Spliterator<Integer> spliterator = values.spliterator();

System.out.println(spliterator.estimateSize());
System.out.println(spliterator.characteristics());

Spliterator<Integer> child = spliterator.trySplit();
System.out.println(child == null ? "Cannot split" : child.estimateSize());
~~~

This is a diagnostic tool to understand the data source, not a complete benchmark. Having `trySplit()` return a non-null child does not prove a parallel pipeline will be faster; operation and merge costs still need to be measured.

## 6. Cost of Intermediate Operations

Two pipelines with the same number of elements do not necessarily have the same cost. Consider the following factors.

### Boxing and Unboxing

Using `Stream<Integer>` can introduce boxing/unboxing costs compared to `IntStream`:

~~~java
int boxedSum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

int primitiveSum = IntStream.of(array).sum();
~~~

When benchmarking sequential vs. parallel, compare the same data representation. If one side uses a primitive stream and the other uses a boxed stream, the measurement no longer isolates the effect of parallelism.

### Stateful Operations

Operations such as `sorted()` or `distinct()` may need to coordinate data across chunks. They can introduce buffering, state, or substantial merge costs.

~~~java
long count = values.parallelStream()
        .distinct()
        .sorted()
        .filter(this::expensivePredicate)
        .count();
~~~

In this pipeline, `sorted()` may be unnecessary if the final output is just `count`. Removing unnecessary operations often has a bigger impact than switching to parallel.

Review the business goal before choosing an execution mode. Do not use parallel to mask a pipeline with redundant steps.

### Preserving Order

Operations such as `forEachOrdered()` preserve encounter order when performing the terminal action, but require coordination and can limit parallel speedups.

~~~java
values.parallelStream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
~~~

If output order is unnecessary, `forEach` can reduce ordering constraints, but only use it when side effects and output contracts allow. Do not replace `forEachOrdered` with `forEach` if order is a requirement.

Operations like `findFirst()` must also respect encounter order; `findAny()` can be more flexible in parallel pipelines when the domain does not require the first element.

## 7. Side Effects, Shared State, and Correctness

Parallel streams require operations not to interfere improperly with the source and to avoid stateful behavioral parameters. Predicates, Functions, Consumers, and lambdas should be as pure as possible: outputs depend on arguments, not on shared mutable state changing over time.

### Wrong Example: Updating a Shared ArrayList

~~~java
List<Integer> results = new ArrayList<>();

values.parallelStream()
        .map(this::transform)
        .forEach(results::add); // Unsafe
~~~

Multiple threads calling `add()` concurrently on an `ArrayList` can cause race conditions or corrupt internal state. Never use a non-thread-safe mutable collection as a shared target in parallel `forEach`.

Use a collector:

~~~java
List<Integer> results = values.parallelStream()
        .map(this::transform)
        .toList();
~~~

`Stream.toList()` has existed since Java 16 and returns an unmodifiable list. If a mutable list is needed:

~~~java
List<Integer> results = values.parallelStream()
        .map(this::transform)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Standard collectors can accumulate into thread-local containers and combine them per the collector contract. This is much safer than manually mutating a shared container.

### Do Not Use Mutable Counters in Parallel Lambdas

~~~java
long[] count = {0};

values.parallelStream().forEach(value -> {
    if (value > 0) {
        count[0]++; // Race condition
    }
});
~~~

Use `count()` or an appropriate reduction:

~~~java
long count = values.parallelStream()
        .filter(value -> value > 0)
        .count();
~~~

If multiple summary values are needed, use a collector or reduction with proper accumulator/combiner rules instead of mutating shared variables.

### Collectors and the CONCURRENT Characteristic

`Collectors.toList()` or `Collectors.toCollection()` do not require a single shared mutable container updated concurrently; the framework can use local containers and merge them.

A Collector with the `CONCURRENT` characteristic allows the accumulator to be invoked concurrently on the same result container when collector and stream ordering conditions permit. Never add this characteristic to a custom collector if the container does not support concurrent accumulation. Likewise, `UNORDERED` should only be declared if results do not depend on encounter order.

### synchronized Can Erase Parallel Gains

~~~java
Object lock = new Object();
List<Integer> results = new ArrayList<>();

values.parallelStream().forEach(value -> {
    int transformed = transform(value);
    synchronized (lock) {
        results.add(transformed);
    }
});
~~~

This snippet may guard list insertions, but all threads still serialize through the lock. If most time is spent in the critical section, adding more workers will not increase throughput. Prefer properly designed collectors.

## 8. Measuring Performance Properly with JMH

Never decide between sequential and parallel using a single `System.nanoTime()` call around a pipeline. Measurements can be skewed by:

- JIT compilation and tiered compilation.
- Class loading and data initialization.
- Insufficient warmup.
- Garbage collection.
- CPU frequency scaling and OS load.
- Other processes competing for CPU.
- `ForkJoinPool.commonPool()` being used by other tasks.
- Unrepresentative data size or cache state.

JMH (Java Microbenchmark Harness) is the dedicated tool for JVM benchmarking. It supports warmup, measurement iterations, JVM forking, result management, and mechanisms to reduce benchmark bias.

### Example Sequential vs. Parallel Benchmark

The following example uses a fixed `int` array and sums it via a primitive stream. Place the benchmark in a separate project with the appropriate JMH dependencies:

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class StreamModeBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = (i * 31) % 1000;
        }
    }

    @Benchmark
    public long sequentialSum() {
        return Arrays.stream(values)
                .asLongStream()
                .sum();
    }

    @Benchmark
    public long parallelSum() {
        return Arrays.stream(values)
                .parallel()
                .asLongStream()
                .sum();
    }
}
~~~

JMH consumes the benchmark's return value to prevent the JVM from eliminating the computation as dead code. Data is initialized at `Level.Trial` so array setup time is excluded from each pipeline measurement. Both benchmarks use the same array and computation.

To run, configure the JMH annotation processor and benchmark runner per JMH's build-tool instructions. `AverageTime` results are reported as average time per invocation; you can also choose `Throughput` when the question is operations completed per unit of time. Do not compare two numbers with different modes or units.

### Principles When Using JMH

1. Use warmup iterations so the JIT has time to optimize the code.
2. Use multiple measurement iterations and multiple forks to reduce dependence on a single JVM state.
3. Move data/setup out of the benchmark method when setup is not what you intend to measure.
4. Measure across different data sizes, not just a single favorable case.
5. Return the result or use a `Blackhole` so the result is not eliminated.
6. Do not run multiple benchmarks concurrently on the same machine if you want reliable CPU throughput comparisons.
7. Record CPU, available cores, RAM, JDK, JVM flags, OS, container quotas, and library versions.
8. Repeat measurements in a deployment-like environment.

### Why Shouldn't You Benchmark with Short Hand-Rolled Loops?

A hand-written microbenchmark can accidentally measure JIT compilation time, allocations, or first-run latency. The JIT can inline, constant-fold, or eliminate code that produces no observable result. A short measurement can fluctuate more than the difference you are trying to detect.

`System.nanoTime()` remains suitable for measuring a sufficiently long application operation during profiling or end-to-end timing, but it is not a reliable way to compare small JVM pipeline differences. For microbenchmarks, use JMH.

## 9. Measure Real Workloads, Not Just Synthetic Benchmarks

The sample benchmark helps compare basic pipeline costs, but it does not represent every application. Measure with:

- Data whose size and distribution match production.
- The same `filter`/`map`/`sort`/`reduce` steps as the real pipeline.
- The same source type (`ArrayList`, array, map, file, etc.).
- The same allocation rate and object graph.
- The same level of contention or shared state.
- The same CPU, RAM, and container quota limits.
- The same common pool configuration if the application relies on that pool.

For example, a pipeline filtering one million integers might speed up in parallel, whereas a pipeline parsing large JSON payloads might be bottlenecked by allocation and GC. A file-reading pipeline might be bottlenecked by I/O. A benchmark using only primitive addition will not reflect those differences.

### Measure Multiple Sizes to Find the Break-Even Point

There is no universal element-count threshold across all machines and pipelines. Some workloads only start paying off at hundreds of thousands of elements; heavier CPU workloads can pay off earlier; very light operations may never gain meaningful speedups.

Benchmark across increasing sizes, for example:

| Size | Purpose |
| ---: | --- |
| 100 | Observe fixed overhead |
| 1,000 | Small workload |
| 10,000 | Medium workload |
| 100,000 | Large workload |
| 1,000,000 | Very large workload |

These are only illustrative test sizes. Choose a range matching your application's actual data sizes. Plot or tabulate timings by size to find where parallel begins paying off, rather than measuring one size and generalizing to all.

## 10. Interpreting Benchmark Results

Suppose a benchmark yields this illustrative table:

| Elements | Sequential (ms) | Parallel (ms) | Notes |
| ---: | ---: | ---: | --- |
| 1,000 | 0.02 | 0.35 | Parallel is slower due to overhead |
| 100,000 | 0.45 | 0.62 | Does not offset split/merge cost yet |
| 1,000,000 | 5.8 | 2.4 | Parallel pays off for this workload |
| 10,000,000 | 58 | 20 | Parallel continues paying off, though below ideal speedup |

These numbers are purely illustrative examples, **not measurements from a specific machine and not selection thresholds**. In real measurements, report error bounds or variance, not just a single average.

### Speedup

Speedup is calculated as:

\[
\text{Speedup} = \frac{T_{sequential}}{T_{parallel}}
\]

If sequential takes 20 ms and parallel takes 5 ms, the speedup is 4x. That does not mean the machine has four cores or that the algorithm scales linearly; it is simply the time ratio in that measurement.

### Do Not Look Only at Mean Time

In server applications, tail latency (p95/p99), overall throughput, CPU utilization, allocation rate, and GC pauses matter too. A parallel stream might reduce the latency of one isolated request while causing concurrent requests to contend on the common pool, degrading p99 across the entire service.

Benchmarks should reflect the optimization goal: single-batch runtime, system-wide throughput, per-request latency, or CPU consumption.

## 11. ForkJoinPool.commonPool and Server Applications

Parallel streams normally use `ForkJoinPool.commonPool()`. This is a JVM-wide shared pool for many Fork/Join activities, including several other APIs. Consequently, one parallel stream pipeline can compete with other parallel work.

In a server:

- Multiple requests running parallel streams simultaneously can pressure the common pool.
- A pipeline with blocking I/O can tie up workers while waiting.
- Other tasks using the common pool can be slowed down.
- Container CPU limits may be lower than the physical CPU count reported by the host.
- Increasing parallelism does not create additional physical CPU resources.

Do not assume a parallel stream acts like a dedicated per-request executor. Understand the actual pool, concurrent load, and deployment limits.

### Configuring Parallelism

`ForkJoinPool.commonPool()` can be affected by the `java.util.concurrent.ForkJoinPool.common.parallelism` system property, but changing this property alters the JVM's shared common pool and can affect many other components. Do not tweak it arbitrarily just to make one benchmark faster.

If you need explicit executor management, concurrency bounds, workload isolation, or task lifecycle control, consider building the concurrency flow with an appropriate `ExecutorService`/`ForkJoinPool`. Parallel streams do not offer a general API to pass an arbitrary executor into every pipeline.

Some JDK versions exhibit specific implementation behavior when a terminal operation is invoked inside another `ForkJoinPool`, but do not rely on unguaranteed Stream API implementation details to design isolation. When executor selection is part of the application contract, manage tasks directly with concurrency APIs.

## 12. Load Balancing and Chunk Granularity

If one element takes 1 microsecond and another takes 100 milliseconds, the workload is uneven. If chunks are split purely by element count while per-element costs vary wildly, one worker can finish early while another still has heavy work left.

`ForkJoinPool` uses work-stealing so idle workers can steal tasks from other workers. This helps balance load, yet it still incurs overhead and does not solve every blocking or resource-contention pattern.

When writing custom work-splitting algorithms:

- Choose chunks large enough to reduce overhead.
- Avoid a single huge task leaving other workers idle.
- Ensure splitting neither duplicates nor drops elements.
- Avoid sharing mutable state across chunks.
- Measure multiple thresholds/chunk sizes on representative data.

With the Stream API, the framework decides splitting via `Spliterator` and its execution engine; users do not directly set chunk sizes in ordinary pipelines. If fine-grained control is needed, consider `ForkJoinTask` or a dedicated executor.

## 13. Correctness Must Be Verified Before Performance

A faster parallel version that returns wrong results is not a successful optimization. Before comparing timings:

1. Run both versions with the same inputs.
2. Compare outputs against the exact contract.
3. Check side effects, ordering, and exceptions.
4. Test edge-case inputs and concurrent load.
5. Run benchmarks only after correctness is confirmed.

### Associativity of Reductions

Parallel reductions require an associative combining operation under the accumulator/combiner mathematical contract. Integer addition can wrap around on overflow under Java rules; if the domain forbids overflow, use `Math.addExact` or an appropriate type/algorithm. `double` addition is not associative due to rounding, so results can differ when operations are grouped differently.

Example:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

If a pipeline uses parallel `double` summation, define acceptable tolerance and an appropriate summation algorithm. Never assert that `double` results must be bit-identical to a sequential pipeline when addition order changes.

### Encounter Order and Results

Some operations preserve encounter order; others like `forEach` can execute in a different order in parallel. If the result requires ordering, use operations and collectors that preserve the contract and accept the corresponding overhead.

Do not use side effects to construct a result sequence based on worker execution order. If deterministic ordering is needed, represent order in the output data or use a collector/operation with matching guarantees.

## 14. Example: Comparing Sequential and Parallel with a CPU-Bound Predicate

The following example demonstrates a primality-checking pipeline. It only illustrates how to construct two equivalent execution paths; do not treat this primality algorithm as a representative benchmark for all applications.

~~~java
import java.util.stream.IntStream;

public class PrimeCount {

    static boolean isPrime(int number) {
        if (number < 2) {
            return false;
        }
        if (number % 2 == 0) {
            return number == 2;
        }
        for (int divisor = 3;
             divisor <= number / divisor;
             divisor += 2) {
            if (number % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    static long sequentialCount(int limit) {
        return IntStream.rangeClosed(2, limit)
                .filter(PrimeCount::isPrime)
                .count();
    }

    static long parallelCount(int limit) {
        return IntStream.rangeClosed(2, limit)
                .parallel()
                .filter(PrimeCount::isPrime)
                .count();
    }

    public static void main(String[] args) {
        int limit = 1_000_000;

        long sequential = sequentialCount(limit);
        long parallel = parallelCount(limit);

        System.out.println("Sequential: " + sequential);
        System.out.println("Parallel: " + parallel);
        System.out.println("Same result: " + (sequential == parallel));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 PrimeCount.java
java PrimeCount
~~~

Both methods check the same numeric range and return the same count. The check is CPU-bound and mutates no shared state, so parallel execution has an opportunity to utilize multiple cores. Even so, exact timings depend on CPU, JDK, machine load, and `limit` size. Measure with JMH if performance conclusions are needed.

## 15. Measurement-Driven Decision Workflow

A practical workflow:

### Step 1: Build a Correct Sequential Version

Write a clear pipeline without unnecessary steps. Use primitive streams when appropriate, minimize boxing, and clarify ordering and exception behavior.

### Step 2: Analyze Parallelizability

Ask:

- Is work independent per element/chunk?
- Does the source split quickly and evenly?
- Does each chunk have enough CPU work?
- Is there shared mutable state, locking, or blocking I/O?
- Does the result require encounter order?
- Does any reduction satisfy the required associativity contract?

### Step 3: Write an Equivalent Parallel Version

Add `parallel()` only when the pipeline can preserve the same contract. Do not change algorithm, data structures, and execution mode simultaneously, or it becomes hard to tell which change caused the difference.

### Step 4: Verify Correctness

Compare sequential and parallel outputs on normal inputs, edge inputs, and representative datasets. Check side effects, ordering, exceptions, and race conditions.

### Step 5: Benchmark with JMH

Measure across multiple sizes with proper warmup, measurement iterations, forks, and environment settings. Run sequential and parallel with the same data and same work. Monitor variance, allocations, and CPU.

### Step 6: Measure in the Deployment Environment

If running in containers or servers, measure with realistic CPU quotas, concurrent load, and common pool contention. A benchmark on an idle laptop is not enough to conclude for production.

### Step 7: Choose Based on Practical Benefit

Keep parallel only if the improvement is consistent and worth the added complexity/resource cost. If gains are small, unstable, or harm other workloads, sequential is usually easier to operate.

## 16. Quick Decision Table

| Workload characteristic | Initial choice | What to measure/verify |
| --- | --- | --- |
| Small list, cheap calculation | Sequential | Fixed overhead |
| Large array, independent CPU math | Try parallel | Speedup across sizes |
| Large data, very light per-element work | Sequential first | Break-even point |
| Pipeline with heavy sort/distinct/grouping | Measure both | Stateful and merge overhead |
| Work mostly calls database/HTTP | Design dedicated I/O concurrency | Connection pool, rate limits, latency |
| Has shared mutable state or locks | Fix design first | Contention and correctness |
| Requires strict output ordering | Sequential or ordered parallel | Cost of `forEachOrdered`/collector |
| Hard-to-split source | Sequential first | `Spliterator`/`trySplit` quality |
| Large CPU-bound task, balanced splits | Parallel is a candidate | Throughput and CPU saturation |
| Server with many concurrent requests | Needs load testing | Common pool, p95/p99, starvation |

## 17. Common Mistakes

| Mistake | Why it causes issues | Resolution |
| --- | --- | --- |
| Assuming parallel is always faster | Ignores split/merge and scheduling overhead | Measure across multiple data sizes |
| One-off benchmark with `nanoTime` | JIT, GC, and OS load skew results | Use JMH for microbenchmarks |
| Using datasets that are too small | Does not represent real workload | Choose sizes matching production |
| Shared `ArrayList` in parallel `forEach` | Race condition | Use an appropriate collector |
| Incrementing a mutable counter inside a lambda | Race condition or atomic contention | Use `count`/reduction |
| Using parallel streams for blocking I/O | Ties up common pool workers | Use async APIs or bounded executors |
| Ignoring `forEach` ordering | Execution order is not guaranteed to match encounter order | Use `forEachOrdered` when truly required |
| Ignoring `sorted`/`distinct` cost | Stateful operations may require coordination | Review pipeline and measure steps |
| Comparing two non-equivalent pipelines | Benchmark results become meaningless | Keep data and logic identical |
| Looking only at single-request time | Ignores system-wide throughput and p99 | Measure under concurrent load |
| Using laptop numbers for server decisions | CPU quotas, pools, and environment differ | Benchmark in a production-like environment |
| Expecting bit-identical `double` results | Reduction can change addition order | Define tolerance/algorithm |
| Tuning JVM-wide common pool for one pipeline | Can affect other components | Manage a dedicated executor if isolation is needed |

## 18. Selection Principles

When choosing sequential vs. parallel in Java 17:

1. Start with a clear and correct sequential pipeline.
2. Only consider parallel when work splits independently and the source splits efficiently.
3. Weigh per-element operation cost against splitting, scheduling, and merging overhead.
4. Avoid shared mutable state, unsafe side effects, and blocking I/O in the common pool.
5. Account for encounter order, stateful operations, and reduction correctness.
6. Compare across data sizes using JMH with proper warmup, measurement, and forks.
7. Measure in the deployment environment, under realistic load, against the target metric.
8. Keep parallel only when measured gains are consistent without harming the wider system.

A parallel stream is an execution choice, not a default badge of better code. For any given pipeline, reliable decisions come from **correctness first, workload modeling second, and measurements last**. Without evidence that parallelism helps, sequential is usually simpler, clearer, and easier to operate.
