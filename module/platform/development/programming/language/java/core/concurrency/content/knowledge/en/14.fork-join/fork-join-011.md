# Benchmarking Fork/Join vs. Sequential Execution in Java

## 1. Questions to Verify

Fork/Join helps split a task into smaller parts so multiple workers can process them concurrently and then combine the results. However, **being splittable** does not mean **running faster**. When the work is short, the number of small tasks is too large, memory bandwidth is saturated, or the machine does not have enough CPU cores, the overhead of task creation, scheduling, work stealing, and result combining can outweigh the time saved.

A useful benchmark must answer specific questions:

1. Given the same input and the same computation, do the **sequential** and **Fork/Join** versions produce the same result?
2. For the data size and machine configuration under test, which version finishes faster?
3. How do the results change when increasing the data size, number of workers, or task-splitting threshold?
4. Are the measurements reliable enough to make a decision, or are they just noise from JIT, GC, pool initialization, and system load?
5. When deployed in a real application, do throughput, latency, CPU, and memory behave as predicted by the microbenchmark?

This article covers **general Java Concurrency**, using standard JDK APIs without depending on Spring.

## 2. Two Ways to Execute the Same Computation

Suppose we need to compute the sum of results of a transformation function applied to each element of an array:

\[
S = \sum_{i=0}^{N-1} f(a_i)
\]

**Sequential:** a single thread iterates over the entire array, calls the same function \(f\), and accumulates the results.

**Fork/Join:** each task manages a half-open index range \([lo, hi)\). When the range is less than or equal to `threshold`, it computes sequentially within that range. When larger, it splits the range in two, calls `fork()` on the left branch, computes the right branch on the current worker, then calls `join()` on the left branch and adds the two sums.

Diagram:

```text
sum[0, N)
    |
    +-- sum[0, N/2)  -- fork
    |      |
    |      +-- smaller ranges computed sequentially
    |
    +-- sum[N/2, N)  -- compute on the current worker
           |
           +-- smaller ranges computed sequentially
    |
    +-- join and add the two results
```

Both approaches must execute **the exact same workload**. If the sequential branch uses a different algorithm, the Fork/Join branch skips part of the data, or one branch benefits from a warmer cache, the comparison is no longer fair.

For `long` integer sums, Java performs addition modulo \(2^{64}\) on overflow; addition at the bit-pattern level remains associative. Therefore, changing the order of addition across branches does not change the bit pattern of the result. For `double` or `float`, the order of addition **can change the result** due to floating-point rounding rules. Floating-point benchmarks should compare using an appropriate tolerance rather than assuming bit-exact matches.

## 3. Why ForkJoinPool Can Be Faster — and When It Isn't

`ForkJoinPool` uses multiple workers to concurrently process splittable pieces of work. The **work stealing** algorithm allows an idle worker to take tasks from another worker's queue, helping distribute uneven workloads. `RecursiveTask<V>` represents a task that returns a result, and `RecursiveAction` represents a task that does not return a value.

```java
// Fragment illustrating the core operation of RecursiveTask<Long>:
if (hi - lo <= threshold) {
    return computeDirectly(lo, hi);
}
int mid = lo + (hi - lo) / 2;
SumTask left = new SumTask(data, lo, mid, threshold);
SumTask right = new SumTask(data, mid, hi, threshold);
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
```

This is a fragment: the `SumTask` class and `computeDirectly` are fully defined in the runnable program in the next section.

Cost factors to account for:

| Cost Source | Sequential Execution | Fork/Join |
| --- | --- | --- |
| Actual computation | Yes | Yes |
| Task object allocation | Not needed for a plain loop | Yes, proportional to split nodes |
| Scheduling/work stealing | Virtually none in a plain loop | Yes |
| Result synchronization | Immediate accumulation | `join()` and combining results |
| Cache, memory bandwidth | Yes | Yes; multiple workers may contend for bandwidth |
| JIT, GC, and warmup | Yes | Yes, sometimes affected differently |
| Available physical cores | One compute thread | Can utilize multiple cores if there is enough work |

If each leaf performs only a few additions, overhead can dominate the total time. If each leaf contains many independent computations, parallelization can amortize the overhead. If each task needs to access a sequential resource or a shared lock, more workers may not help.

**There is no single "best" leaf-size threshold for all programs.** The threshold depends on the computation, data size, cache, CPU speed, number of workers, and resource contention.

## 4. Standalone Java 17 Benchmark Program

This example includes both versions of the same computation. The `transform` function performs several rounds of integer transformations on each element so the work is not too trivial. Results are verified **before and during measurement**. The program uses a dedicated pool, warmup, and multiple trials, reporting the **median** rather than relying on a single run.

Save as **`ForkJoinVsSequentialBenchmark.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class ForkJoinVsSequentialBenchmark {
    private static final int SIZE = 1_000_000;
    private static final int THRESHOLD = 32_768;
    private static final int WARMUPS = 3;
    private static final int TRIALS = 7;

    // Prevent the result from existing only within the measurement without being used.
    private static volatile long resultSink;

    private static long transform(long value) {
        long x = value;
        for (int i = 0; i < 16; i++) {
            x ^= x >>> 27;
            x *= 0x3C79AC492BA7B653L;
            x ^= x >>> 33;
        }
        return x;
    }

    private static long sequential(long[] data, int lo, int hi) {
        long sum = 0L;
        for (int i = lo; i < hi; i++) {
            sum += transform(data[i]);
        }
        return sum;
    }

    private static final class SumTask extends RecursiveTask<Long> {
        private final long[] data;
        private final int lo;
        private final int hi;
        private final int threshold;

        SumTask(long[] data, int lo, int hi, int threshold) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= threshold) {
                return sequential(data, lo, hi);
            }
            int mid = lo + (hi - lo) / 2;
            SumTask left = new SumTask(data, lo, mid, threshold);
            SumTask right = new SumTask(data, mid, hi, threshold);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();
            return leftResult + rightResult;
        }
    }

    private static long parallel(
            ForkJoinPool pool, long[] data, int threshold) {
        return pool.invoke(new SumTask(data, 0, data.length, threshold));
    }

    private static long timedSequential(long[] data, long expected) {
        long start = System.nanoTime();
        long value = sequential(data, 0, data.length);
        long elapsed = System.nanoTime() - start;

        if (value != expected) {
            throw new AssertionError("Sequential checksum mismatch");
        }
        resultSink = value;
        return elapsed;
    }

    private static long timedParallel(
            ForkJoinPool pool, long[] data, int threshold, long expected) {
        long start = System.nanoTime();
        long value = parallel(pool, data, threshold);
        long elapsed = System.nanoTime() - start;

        if (value != expected) {
            throw new AssertionError("Fork/Join checksum mismatch");
        }
        resultSink = value;
        return elapsed;
    }

    private static long median(long[] measurements) {
        long[] ordered = measurements.clone();
        Arrays.sort(ordered);
        return ordered[ordered.length / 2]; // TRIALS is odd.
    }

    public static void main(String[] args) throws InterruptedException {
        long[] data = new long[SIZE];
        for (int i = 0; i < data.length; i++) {
            data[i] = 13L * i + 7L;
        }

        int processors = Runtime.getRuntime().availableProcessors();
        int parallelism = Math.max(1, Math.min(processors, 4));
        ForkJoinPool pool = new ForkJoinPool(parallelism);

        try {
            long expected = sequential(data, 0, data.length);

            // Warm up both execution paths, excluded from the trials.
            for (int i = 0; i < WARMUPS; i++) {
                if (sequential(data, 0, data.length) != expected
                        || parallel(pool, data, THRESHOLD) != expected) {
                    throw new AssertionError("Different results");
                }
            }

            long[] sequentialNanos = new long[TRIALS];
            long[] parallelNanos = new long[TRIALS];

            // Alternate measurement order across trials to reduce bias.
            for (int i = 0; i < TRIALS; i++) {
                if (i % 2 == 0) {
                    sequentialNanos[i] = timedSequential(data, expected);
                    parallelNanos[i] =
                            timedParallel(pool, data, THRESHOLD, expected);
                } else {
                    parallelNanos[i] =
                            timedParallel(pool, data, THRESHOLD, expected);
                    sequentialNanos[i] = timedSequential(data, expected);
                }
            }

            double seqMs = median(sequentialNanos) / 1_000_000.0;
            double parMs = median(parallelNanos) / 1_000_000.0;
            double speedup = seqMs / parMs;

            System.out.println("Checksums equal: true");
            System.out.println("Trials per variant: " + TRIALS);
            System.out.println("Parallelism: " + parallelism);
            System.out.printf(Locale.ROOT,
                    "Sequential median: %.3f ms%n", seqMs);
            System.out.printf(Locale.ROOT,
                    "Fork/Join median: %.3f ms%n", parMs);
            System.out.printf(Locale.ROOT,
                    "Speedup: %.2fx%n", speedup);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac ForkJoinVsSequentialBenchmark.java
java ForkJoinVsSequentialBenchmark
```

**The first three lines have a deterministic structure**, though `Parallelism` depends on the number of processors visible to the JVM:

```text
Checksums equal: true
Trials per variant: 7
Parallelism: 4
```

The line `Parallelism: 4` above corresponds to a machine with at least four available processors; if the JVM sees only one or two processors, it prints the corresponding number. The last three lines print the **actual measured median times** (in milliseconds, to three decimal places) and `Speedup` (to two decimal places). There are no fixed timing or speedup values across all machines.

If the program prints `Speedup: 1.60x`, it means the sequential median time is about 1.6 times larger than the Fork/Join median **in this measurement**. If `Speedup: 0.70x`, Fork/Join is slower than sequential. Do not assume the result must be greater than 1.

### Why Is the Result Correct?

- Both execution paths use **the exact same `transform` function**, the same array, and the same index range.
- `SumTask` splits the half-open range into two **non-overlapping** ranges, so no elements are skipped or double-counted.
- The `long` sum may overflow, but Java's `long` addition yields the same bit-pattern result regardless of how additions are grouped.
- `pool.invoke(...)` waits for the root task's result before returning.
- Inside the measurement loop, the `value == expected` check ensures a fast measurement is not achieved by computing the wrong answer; `resultSink` keeps the result observable.

### Is This Benchmark Sufficient for Final Performance Conclusions?

**Not yet.** This is a **learning harness** using `System.nanoTime()`. It demonstrates fair comparison design, warmup, repeated trials, and result validation. The JIT may compile at different times; GC, turbo boost, CPU frequency scaling, temperature, the OS scheduler, background processes, and memory layout can all affect measurements. For publishing or seriously optimizing microbenchmarks, see the JMH section below.

Do not run both variants **concurrently** and compare their timings: they will contend for CPU/cache and measure a different scenario. In this harness, each measurement finishes before the next starts, alternating order to reduce simple biases.

## 5. Speedup Formula and Parallel Efficiency

Let:

- \(T_s\): time of the sequential version.
- \(T_p\): time of the Fork/Join version with \(P\) workers.
- \(S = T_s/T_p\): **speedup**.
- \(E = S/P\): parallel efficiency relative to the configured number of workers.

| Example Measurement | Speedup | Meaning |
| --- | --- | --- |
| \(T_s = 100\) ms, \(T_p = 50\) ms | \(2.0\times\) | Fork/Join takes half the time |
| \(T_s = 100\) ms, \(T_p = 80\) ms | \(1.25\times\) | Improved, but sublinear |
| \(T_s = 100\) ms, \(T_p = 140\) ms | \(0.71\times\) | Fork/Join is slower |
| \(T_s = 100\) ms, \(T_p = 100\) ms | \(1.0\times\) | No improvement observed |

The numbers above only illustrate the calculation, not actual output from the program.

For work that has a non-parallelizable portion, **Amdahl's law** gives an ideal upper bound:

\[
S(P) \leq \frac{1}{(1-f) + f/P}
\]

Where \(f\) is the fraction of execution time that can be parallelized and \(P\) is the number of workers. This ideal formula **does not account for** task-splitting overhead, synchronization, memory bandwidth, or load balancing; therefore, actual numbers are usually lower than the estimate.

For example, when only 80% of the work can be parallelized and 4 workers are used, the ideal maximum speedup is \(1/(0.2+0.8/4)=2.5\times\), even with four workers. Do not expect `4x` simply because `parallelism=4`.

Another metric is **throughput** (work units per second). If a benchmark runs a fixed-size batch, the computed rate is \(N/T\). For applications serving concurrent requests, also measure p95/p99 latency, queued task counts, CPU utilization, and GC, because batch speedup does not automatically translate to system-wide improvement.

## 6. Impact of Threshold and Workload Size

`threshold` is the smallest range size processed directly. It governs the number of tasks and the amount of work per leaf.

- **Threshold too small:** creates many `RecursiveTask` instances, incurring allocation, scheduling, and `join()` overhead; leaves are too light.
- **Threshold too large:** does not create enough branches to keep multiple workers busy; some workers sit idle, leading to poor load balancing.
- **Appropriate threshold:** each leaf is large enough that computation cost outweighs overhead, yet small enough to distribute work across the pool.

For an array of \(N\) elements and threshold \(L\), binary splitting typically produces roughly \(N/L\) leaf tasks when \(N\) is larger than \(L\); the number of intermediate nodes also scales with the number of leaves. This is a rule-of-thumb estimate, not an exact task count for all \(N\) and \(L\).

### Useful Experiment Matrix

| Variable to Change | Illustrative Values | What to Observe |
| --- | --- | --- |
| Data size \(N\) | 10,000, 100,000, 1,000,000, 10,000,000 | Crossover point where parallelism becomes beneficial |
| Leaf threshold | 512, 4,096, 32,768, 262,144 | Task overhead vs. worker utilization |
| Parallelism | 1, 2, 4, 8 (if hardware resources allow) | Scalability and CPU saturation |
| Work per element | Simple addition, multi-round transformation | Light vs. heavy workloads |
| Uneven data distribution | Ranges with varying difficulty | Value of work stealing |

These rows are **experimental designs**, not a guarantee that every machine has enough RAM or cores to run all combinations. Keep the other variables fixed when investigating one variable. Run multiple independent forks/trials, record the median or timing distribution, and report the JDK/CPU/heap/OS configuration.

In the example program, try changing `THRESHOLD` to 1,024, 8,192, 32,768, and 131,072 to observe the differences. Do not change the `transform` algorithm between the two variants within the same comparison.

## 7. Work Stealing and Real-World Load Balancing

Fork/Join is most useful when a problem can be divided into independent parts, including cases with **uneven** computational load such as recursion, searching, tree traversal, or branch-based data processing.

A worker can have multiple tasks in its deque. When another worker becomes idle, it can **steal** a task to keep working. This improves CPU utilization when it is not known ahead of time which branch will take longer.

However:
- Work stealing also has coordination overhead.
- If every leaf is extremely light, workers spend much of their time managing tasks.
- If all workers read/write large data simultaneously, memory bandwidth and cache contention can become bottlenecks.
- If tasks contend on locks or write to the same variable, useful parallelism drops sharply.
- Tasks blocking on long-running I/O can tie up workers without consuming useful CPU; Fork/Join is designed for splittable CPU-bound work, not as a default solution for all blocking I/O.

In Java, `ForkJoinPool.managedBlock(...)` is a specialized mechanism allowing the pool to handle certain managed blocking situations. It does not turn I/O into non-blocking I/O and should not be added to a CPU benchmark just to increase the thread count.

## 8. Avoiding Pitfalls When Using System.nanoTime()

`System.nanoTime()` is suitable for measuring **relative elapsed time** within a single JVM process:

```java
long started = System.nanoTime();
long result = doWork();
long elapsedNanos = System.nanoTime() - started;
```

This is a fragment; `doWork()` is defined by the application. Do not use `System.currentTimeMillis()` for short durations due to its resolution and susceptibility to system clock adjustments. `nanoTime()` reports in nanoseconds, but **its actual resolution is not guaranteed to be 1 ns**.

Common mistakes:

1. **No warmup:** measuring the very first run may mostly measure class loading and JIT compilation.
2. **Only a single trial:** conclusions are skewed by scheduling, GC, or thermal throttling.
3. **Discarding the result:** the compiler/JIT may eliminate or alter parts of the work if it proves the result has no observable effect.
4. **Including data preparation in only one variant's timing:** makes the comparison unequal in scope.
5. **Creating `ForkJoinPool` inside the timed loop:** includes pool initialization and shutdown overhead that the sequential version does not pay; if the real use case creates a pool per request, measure that scenario separately rather than mixing it into a steady-state processing benchmark.
6. **Including console printing in the measurement:** `System.out.println()` and output flushing have variable cost that masks computation time.
7. **Running both variants concurrently:** they contend for CPU and cache, turning the measurement into a contention benchmark.
8. **Skipping checksum verification:** a variant that processes fewer elements can appear misleadingly faster.
9. **Assuming setting workers equal to logical cores yields proportional speedup:** hyperthreading, container CPU quotas, and memory-bound workloads can deviate significantly from expectations.
10. **Relying on the median while ignoring dispersion:** inspect min/max, p95, or confidence intervals when making optimization investment decisions.

Warmup and median are better than a single measurement, but they **do not eliminate all** JIT, DCE, GC, and benchmark-structure-dependent optimization biases.

## 9. When to Use JMH

**JMH (Java Microbenchmark Harness)** is the specialized benchmarking tool in the OpenJDK ecosystem, used when higher-confidence Java microbenchmark comparisons are needed. JMH **is not included in the standard JDK library**: you must add its dependency and run it with an appropriate build/harness configuration.

JMH supports:
- Warmup iterations and measurement iterations.
- Multiple independent **JVM forks**, reducing state carryover between runs.
- Measurement units, throughput/average time/sample time.
- `Blackhole` to consume results, preventing certain forms of dead-code elimination.
- Benchmark state (`@State`) and lifecycle (`@Setup`, `@TearDown`).
- Parameters (`@Param`) to automatically test multiple thresholds, data sizes, or worker counts.

An example **fragment requiring the JMH dependency** (not a standalone `javac` program):

```java
@State(Scope.Benchmark)
public class SumBenchmark {
    @Param({"8192", "32768", "131072"})
    public int threshold;

    private long[] data;
    private ForkJoinPool pool;

    @Setup(Level.Trial)
    public void setUp() {
        data = createInput();
        pool = new ForkJoinPool(4);
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        pool.shutdown();
    }

    @Benchmark
    public long sequential() {
        return sumSequential(data);
    }

    @Benchmark
    public long forkJoin() {
        return pool.invoke(new SumTask(data, 0, data.length, threshold));
    }
}
```

The structure above only illustrates JMH annotations and setup scope: it requires imports from `org.openjdk.jmh.annotations`, the JMH dependency, and the `createInput`, `sumSequential`, and `SumTask` helpers from the test application. Benchmark methods return `long` so the harness can consume the result, rather than printing to the console inside a `@Benchmark` method.

Important: use the same dataset, the same computation function, the same worker count, the same JDK/JVM flags, and sufficient warmup time. Even JMH cannot guarantee results represent production workloads if the measured operation differs from real usage.

Official project reference: [OpenJDK JMH](https://github.com/openjdk/jmh). When numbers are needed for decision-making, record the benchmark configuration, JDK/JMH versions, hardware, and result distribution so others can reproduce them.

## 10. Interpreting Benchmark Results in Context

Suppose an experiment shows:

- Small input: sequential is faster due to task-splitting overhead.
- Medium input: Fork/Join starts to match or slightly beat sequential.
- Large input, CPU-bound: Fork/Join can be faster if multiple cores are available.
- Large input, memory-bound: adding workers may not yield much speedup.
- Workload with shared locks: more workers can be slower due to contention.

These are **likely trends**, not absolute rules. Measure and verify on the corresponding target machine/production environment.

### What Should a Benchmark Report Include?

| Information | Why It Is Needed |
| --- | --- |
| Problem, input size, and data characteristics | Ensures both versions process the same work |
| JDK version and JVM flags | JIT/GC behavior may differ |
| CPU, cores/threads, RAM, container quota | Explains actual parallel capacity |
| Parallelism, threshold, pool lifecycle | Parameters determining task count and overhead |
| Warmup, number of trials/forks, reported metrics | Distinguishes stability from lucky runs |
| Correctness/checksum results | Avoids comparing non-equivalent algorithms |
| Times, speedup, timing distribution | Provides evidence rather than a single number |
| CPU, allocation, and GC if available | Explains costs shifted elsewhere |

If Fork/Join is faster in a microbenchmark but a production API is slower, check queueing delay, contention with other requests, garbage collection, cache, I/O, and resource limits. **Batch latency** differs from **application-wide throughput**.

## 11. Fork/Join Algorithm-Specific Mistakes

### Do Not Call fork Then Immediately join Pointlessly

Bad pattern:

```java
left.fork();
long leftValue = left.join();
long rightValue = right.compute();
```

The worker may block waiting for `left` before starting `right`, reducing parallel utilization. The commonly recommended pattern:

```java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
```

The code above is a fragment inside `compute()`, with both tasks already constructed. It keeps the current worker doing useful work while other workers can pick up the forked task.

### Do Not Split All the Way Down to a Single Element

Every task has overhead. Stop at a threshold chosen based on measurements, then process the leaf with a sequential loop. Branches do not have to be equal if per-element processing cost varies; for predictable, uniform workloads, splitting the index range in half is a good baseline.

### Do Not Share a Contended Sum Variable

Avoid having all workers update a `static long sum` or a single `AtomicLong` on every element if the benchmark goal is efficient parallel summation. This can cause data races or contention. Each leaf should return a local sum, and the root combines results via `join()`.

### Mind Integer Overflow and Floating-Point Arithmetic

For `long` arithmetic, overflow is defined at the language level, and the result modulo \(2^{64}\) is invariant under reassociation of additions. If business logic requires **exact mathematical sums exceeding `long` limits**, use `BigInteger` or an appropriate algorithm in both variants and re-benchmark. For `double`, different addition orders can produce different numbers; use a tolerance and verify numerical accuracy.

### Do Not Default to commonPool for All Measurements

`ForkJoinPool.commonPool()` is shared by many parts of the process; load from elsewhere in the application can affect the benchmark. A dedicated pool defines `parallelism` and lifecycle more clearly, though it **does not isolate the machine from other system processes/threads**.

## 12. Experiment Checklist and Conclusion

1. **Define the exact same workload:** identical input, computation function, element count, and read/write operations.
2. **Verify correctness before measuring:** matching checksums/results; define a tolerance for floating-point values.
3. **Choose a minimal sequential baseline:** do not force the sequential version to pay unnecessary overhead.
4. **Control the pool:** create a pool with a fixed parallelism and manage shutdown outside the timed region when measuring steady state.
5. **Warm up and repeat:** never draw conclusions from the first run or a single trial.
6. **Explore threshold, data size, and parallelism:** find the region where overhead is amortized.
7. **Reduce environmental noise:** close other heavy programs, keep JDK and machine settings consistent.
8. **Measure actual outcomes:** median, dispersion, speedup, CPU, and GC; use JMH when high confidence is needed.
9. **Test correctness/concurrency:** non-overlapping splits, no missed elements, and tasks do not mutate shared state without synchronization.
10. **Validate on production workloads:** a batch benchmark does not replace end-to-end measurement.

## 13. Self-Check Questions

**1. Does increasing `parallelism` always make Fork/Join faster?**  
No. Speedup is bounded by the sequential portion, physical core count, overhead, contention, and memory bandwidth.

**2. Why is a threshold that is too small usually bad?**  
The number of `RecursiveTask` objects, `fork/join` operations, and scheduling overhead become large relative to the computation in each leaf.

**3. Can you compare two algorithms that return different results?**  
You cannot draw speed conclusions for **the same problem** if their results are not semantically equivalent. Correctness and measurement definitions must be verified.

**4. Does `System.nanoTime()` automatically make a benchmark accurate?**  
No. It only measures elapsed time; you still must handle warmup, JIT, GC, dead-code elimination, machine load, and multiple trials.

**5. What does a speedup of \(0.8\times\) mean?**  
Fork/Join was slower than the sequential baseline in that measurement, because \(T_s/T_p = 0.8\).

**6. Why keep `left.fork(); right.compute(); left.join();`?**  
The current worker continues doing useful work while the left branch can be processed by another worker.

**7. What problem does JMH solve?**  
It provides a dedicated harness for warmup, measurement, JVM forks, and result consumption, reducing several pitfalls of manual microbenchmarking.

**8. When is application-level testing also necessary?**  
When you want to know real performance under CPU/GC competition, queueing, request latency, I/O, and production workload demands.

## References

- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
