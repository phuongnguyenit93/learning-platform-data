# Practice: Array Sum with Fork/Join and Benchmarking in Java

## 1. Objectives and Problem Statement

Given an `int[]` array with `N` elements, compute its sum in two ways: a **sequential loop** and **parallel Fork/Join**. Verify that both results are identical, then measure execution time across multiple array sizes, task-splitting thresholds, and worker counts to determine **when Fork/Join is worth using**.

This exercise uses plain Java/JDK (Java 17+), without depending on Spring or any other framework. After completing it, you should be able to explain `RecursiveTask<Long>`, `fork()`, `compute()`, `join()`, work-stealing, `threshold`, scheduling overhead, correctness on empty arrays, and the risk of `int` overflow. Most importantly: know how to compare benchmarks without assuming "parallel is always faster."

**Expected deliverables:** accurate sum results, standalone compilable code, a table of timing measurements on a real machine, and an explanation backed by data. Any timing numbers shown in this lesson are only examples of how to interpret data, not actual benchmarks.

## 2. Algorithm Design and Invariants

Each task's range is a **half-open interval** `[from, to)`: inclusive of `from` and exclusive of `to`. Therefore, the number of elements in a task is `to - from`. When splitting at `mid`, the two sub-ranges must be `[from, mid)` and `[mid, to)`: no elements skipped, no elements double-counted.

- **Sequential version:** initialize `long sum = 0L`, add all elements one by one, and return `sum`.
- **Leaf task:** if the number of elements is `<= threshold`, use a loop to directly sum the range and return a `long`.
- **Branching task:** compute `mid = from + (to-from)/2`, create two tasks. `fork` one branch, compute the other branch on the current worker, `join` the forked branch, and add the two results together.
- **Base case condition:** require `threshold > 0`. An empty range `[0,0)` has a sum of `0L`.

~~~text
N = 16, threshold = 4

[0,16)
   ├─ [0,8)
   │    ├─ [0,4)    -> leaf computation
   │    └─ [4,8)    -> leaf computation
   └─ [8,16)
        ├─ [8,12)   -> leaf computation
        └─ [12,16)  -> leaf computation

S(0,16) = S(0,4) + S(4,8) + S(8,12) + S(12,16)
~~~

**Brief proof:** each leaf adds each of its elements exactly once. When splitting, the two sub-intervals are disjoint and their union equals the parent interval, so the sum of the two branches equals the sum of the parent interval. The recursion terminates because every sufficiently large interval is split into two shorter intervals and `threshold` is positive. The array sum equals the result of the root task `[0, N)`.

### Why Use `long`?

`int` overflows when the sum falls outside the range `-2_147_483_648` to `2_147_483_647`. For example, `Integer.MAX_VALUE + Integer.MAX_VALUE` is mathematically **4,294,967,294**, which is outside the `int` range. Use `long sum` **directly inside the leaf task**, and return `RecursiveTask<Long>` to maintain an accurate sum. `long` also has a limit; if the problem can exceed the `long` range, use `Math.addExact` to detect overflow or `BigInteger` depending on business requirements.

Tasks may only assume that the array is read-only/stable. If another thread modifies `data[i]` during computation, the result is no longer a consistent snapshot. Finish populating the data before starting and do not write to the array until all tasks have completed.

## 3. Complete Java 17 Code: `ArraySumForkJoinDemo.java`

The following example constructs a deterministic dataset, cross-checks the sequential and Fork/Join sums, tests empty-array/`int`-overflow edge cases, and runs an **illustrative timing measurement**. No extra dependencies are required.

~~~java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public class ArraySumForkJoinDemo {
    private static final int N = 1_000_000;
    private static final int THRESHOLD = 16_384;
    private static final int WARMUP = 5;
    private static final int ROUNDS = 11;
    private static volatile long sink;

    private static long sequentialSum(int[] a) {
        long sum = 0L;
        for (int x : a) {
            sum += x;
        }
        return sum;
    }

    private static final class SumTask extends RecursiveTask<Long> {
        private final int[] a;
        private final int from;
        private final int to;
        private final int threshold;

        private SumTask(int[] a, int from, int to, int threshold) {
            this.a = a;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int length = to - from;
            if (length <= threshold) {
                long sum = 0L;
                for (int i = from; i < to; i++) {
                    sum += a[i];
                }
                return sum;
            }

            int mid = from + length / 2;
            SumTask left = new SumTask(a, from, mid, threshold);
            SumTask right = new SumTask(a, mid, to, threshold);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    private static long forkJoinSum(
            ForkJoinPool pool, int[] a, int threshold) {
        if (threshold <= 0) {
            throw new IllegalArgumentException("threshold must be > 0");
        }
        return pool.invoke(new SumTask(a, 0, a.length, threshold));
    }

    private static double medianMillis(
            LongSupplier operation, long expected) {
        for (int i = 0; i < WARMUP; i++) {
            long value = operation.getAsLong();
            if (value != expected) {
                throw new AssertionError("Incorrect warmup result");
            }
            sink = value;
        }

        long[] samples = new long[ROUNDS];
        for (int i = 0; i < ROUNDS; i++) {
            long start = System.nanoTime();
            long value = operation.getAsLong();
            samples[i] = System.nanoTime() - start;
            if (value != expected) {
                throw new AssertionError("Incorrect measured result");
            }
            sink = value;
        }

        Arrays.sort(samples);
        return samples[ROUNDS / 2] / 1_000_000.0;
    }

    public static void main(String[] args) throws InterruptedException {
        int[] data = new int[N];
        for (int i = 0; i < N; i++) {
            data[i] = (i % 1_000) - 500;
        }

        // One group of 1000 numbers has a sum of -500; there are 1000 groups.
        long expected = -500_000L;
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            if (sequentialSum(data) != expected
                    || forkJoinSum(pool, data, THRESHOLD) != expected) {
                throw new AssertionError("Sum mismatch");
            }

            int[] largeValues = {
                    Integer.MAX_VALUE, Integer.MAX_VALUE
            };
            long largeSum = 4_294_967_294L;
            if (sequentialSum(largeValues) != largeSum
                    || forkJoinSum(pool, largeValues, 1) != largeSum) {
                throw new AssertionError("Overflow-case mismatch");
            }

            int[] empty = new int[0];
            if (sequentialSum(empty) != 0L
                    || forkJoinSum(pool, empty, 1) != 0L) {
                throw new AssertionError("Empty-array mismatch");
            }

            System.out.printf(
                    "n=%d, expected=%d, workers=%d, threshold=%d%n",
                    data.length, expected,
                    pool.getParallelism(), THRESHOLD);
            System.out.println("correctness=PASS");

            double seqMs = medianMillis(
                    () -> sequentialSum(data), expected);
            double fjMs = medianMillis(
                    () -> forkJoinSum(pool, data, THRESHOLD), expected);

            System.out.printf("sequential medianMs=%.3f%n", seqMs);
            System.out.printf("forkjoin   medianMs=%.3f%n", fjMs);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Save the file with the exact name `ArraySumForkJoinDemo.java`. Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 ArraySumForkJoinDemo.java
java ArraySumForkJoinDemo
~~~

The first two lines of stdout are **deterministic** (on a successful run):

~~~text
n=1000000, expected=-500000, workers=4, threshold=16384
correctness=PASS
~~~

After that come the two lines `sequential medianMs=...` and `forkjoin   medianMs=...`. Execution times on another machine cannot be predicted in advance, so **do not fabricate numbers for this part**. If you change `N`, the data generation rule, or the worker count, update `expected`/messages accordingly.

### Key Points in the Code Explained

1. **`RecursiveTask<Long>`:** a task that returns a result. `RecursiveAction` is only appropriate when the task does not need to return a value.
2. **`left.fork()`:** schedules a branch onto the pool's queue; it does not create a separate OS thread per task. Idle workers can pick up tasks via work-stealing.
3. **`right.compute()`:** executes the remaining branch on the current worker, reducing the number of tasks unnecessarily pushed onto queues.
4. **`left.join()`:** retrieves the result of the forked task and may wait; in `ForkJoinPool`, waiting cooperates with executing other tasks as permitted by the runtime.
5. **`pool.invoke(root)`:** submits the root task to the pool and awaits the result (or exception). No need to manually spawn threads per branch.
6. **`threshold=16_384`:** merely a starting point for experimentation, **not the optimal value**.
7. **`volatile sink` and the expected-value check:** ensure the program actually uses the computed result, limiting JIT dead-code elimination in this measurement example. Still, this is not yet a full benchmark.
8. **`shutdown()` and `awaitTermination()`:** manage the lifecycle of the private pool; avoid leaving workers alive unnecessarily after `main` finishes.

The code does not update a shared sum variable. Each leaf task produces a local sum, which is then combined after `join`; therefore, neither `synchronized` nor `AtomicLong` is needed for the addition. Replacing this with a shared `AtomicLong` would introduce contention among workers and benchmark a different algorithm altogether.

## 4. Work-Stealing, Complexity, and Sources of Overhead

`ForkJoinPool` manages workers and splittable tasks. When a worker runs out of work, it can take available work from another worker (**work-stealing**). This helps when branches have uneven workloads and enough parallel tasks exist.

| Concept | What to Understand |
| --- | --- |
| `fork()` | Schedules a task for potential parallel execution; does **not** guarantee it runs immediately. |
| `compute()` | Executes on the current thread; typically computes one half inline. |
| `join()` | Obtains a child task's result, waiting or cooperating in task execution via the Fork/Join mechanism. |
| `invoke()` | Submits the root task and retrieves the final result. |
| `getParallelism()` | The pool's configured parallelism level; does not guarantee that the exact number of physical cores is used. |

The total number of additions remains **O(N)**; balanced splitting keeps the recursion tree depth around `O(log(N / threshold))` when `N > threshold`. Total execution time includes the overhead of range splitting, task instantiation, scheduling, `join`, `Long` boxing, and memory access. Hence, in theory, having more workers does not mean linear speedup.

Summing elements of an `int[]` is a very cheap operation. For sufficiently large arrays, execution time is often limited by **memory read bandwidth**, where workers must share cache/bus/memory resources. As a result, 8 workers may not be twice as fast as 4 workers. Conversely, an array that is too small can be noticeably slower because Fork/Join overhead outweighs the addition itself.

**Amdahl's law** provides an upper-bound model: if the sequential fraction is `s` and there are `p` workers, the theoretical speedup is approximately `1 / (s + (1-s)/p)`, even before accounting for overhead. In the array-sum problem, memory bandwidth limits and scheduler overhead can yield results lower than this model.

### Threshold Trade-Offs

- **Threshold too large:** the tree has too few tasks, failing to utilize all workers; nearly sequential while still incurring pool overhead.
- **Threshold too small:** creates too many tasks, wasting time on scheduling, fork/join, and object allocation.
- **Moderate threshold:** each leaf is large enough that task creation cost is small relative to scanning the array, while still providing enough independent branches. The best value depends on `N`, CPU, JVM, and workload.

The number of leaves is approximately `N / threshold` when the tree is balanced (estimate), not the number of workers. Hundreds of tasks can be processed by four workers without creating hundreds of threads.

## 5. Verifying Correctness Before Benchmarking

A benchmark is meaningless if one side computes the wrong answer. Use the sequential baseline on the same input to cross-check before and during measurements.

| Input | Result | What It Tests |
| --- | ---: | --- |
| `[]` | `0L` | Empty range, base case. |
| `[7]` | `7L` | Single element. |
| `[-3, 10, -2]` | `5L` | Does not assume all positive numbers. |
| `[Integer.MAX_VALUE, Integer.MAX_VALUE]` | `4_294_967_294L` | `int` overflow, using `long`. |
| Size equal to threshold | Matches sequential | Leaf task boundary. |
| Size equal to threshold + 1 | Matches sequential | Triggers task splitting. |
| Odd size, not a power of 2 | Matches sequential | No skipped or double-counted tail elements. |
| Large array, multiple workers | Matches sequential | No shared mutable total. |

When writing automated tests, use `Future.get(timeout, unit)` or your test runner's timeout to catch deadlocks/livelocks; do not rely on `Thread.sleep` to guess that a schedule has occurred. For benchmarks, input data must be prepared **outside the measured region**—do not combine array generation with summation and conclude that Fork/Join is slow.

**Do not run benchmarks concurrently with heavy background workloads or other benchmarks.** CPU throttling, JIT, GC, and OS scheduling can all skew results. If running inside a container, explicitly record CPU and memory limits.

## 6. Comparing Timings and Reading Speedup

The `ArraySumForkJoinDemo` program provides a learning-oriented measurement: 5 warmup runs, 11 measured runs, taking the median time in milliseconds. `System.nanoTime()` is used to measure elapsed duration, not wall-clock date/time.

To interpret speed, use:

~~~text
speedup = time_sequential / time_forkjoin
efficiency ≈ speedup / worker count
~~~

An example **solely to illustrate how to interpret results**, not actual measured data:

| Configuration | Hypothetical Time | Conclusion If Measured Reliably |
| --- | ---: | --- |
| Sequential | 2.0 ms | Baseline |
| Fork/Join 4 workers | 1.5 ms | Speedup 2.0/1.5 ≈ 1.33× |
| Fork/Join with threshold too small | 3.0 ms | 2.0/3.0 ≈ 0.67×, meaning slower |

Timings on a real machine may be completely different. `speedup > 1` indicates the parallel version is faster under the measured conditions; `speedup < 1` indicates it is slower. `efficiency` is a model-based efficiency estimate, **not** a measurement of CPU utilization. Never report speedup while ignoring variance.

**Limitations of a custom harness:** JIT may warm up differently, results depend on measurement order, the JVM may optimize certain code paths, worker startup/wakeup times and cache states vary, and a single JVM process cannot capture run-to-run variance. For serious evaluation, use **JMH**.

## 7. Benchmarking with Warmup and Forks Using JMH

JMH (*Java Microbenchmark Harness*) is a Java microbenchmarking tool that supports warmup, measurement, JVM forks, and result consumption. For this exercise, you can create a **separate Maven project** to compare sequential vs. Fork/Join on the exact same input.

Directory structure:

~~~text
forkjoin-bench/
├── pom.xml
└── src/main/java/example/SumBenchmark.java
~~~

Because this project has a JMH dependency, **it cannot be compiled with standalone `javac` using only the JDK** like the first example. Maven is required to download dependencies.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>forkjoin-bench</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/SumBenchmark.java`:**

~~~java
package example;

import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
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
import org.openjdk.jmh.annotations.TearDown;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SumBenchmark {
    @Param({"100000", "1000000", "10000000"})
    public int size;

    @Param({"4096", "65536"})
    public int threshold;

    private int[] a;
    private ForkJoinPool pool;

    private static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int from;
        final int to;
        final int limit;

        Task(int[] a, int from, int to, int limit) {
            this.a = a;
            this.from = from;
            this.to = to;
            this.limit = limit;
        }

        @Override
        protected Long compute() {
            if (to - from <= limit) {
                long sum = 0L;
                for (int i = from; i < to; i++) {
                    sum += a[i];
                }
                return sum;
            }

            int mid = from + (to - from) / 2;
            Task left = new Task(a, from, mid, limit);
            Task right = new Task(a, mid, to, limit);
            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    private long sequential() {
        long sum = 0L;
        for (int value : a) {
            sum += value;
        }
        return sum;
    }

    private long parallel() {
        return pool.invoke(new Task(a, 0, a.length, threshold));
    }

    @Setup
    public void setup() {
        a = new int[size];
        for (int i = 0; i < size; i++) {
            a[i] = (i % 1_000) - 500;
        }
        pool = new ForkJoinPool(4);
        if (sequential() != parallel()) {
            throw new AssertionError("Incorrect parallel result");
        }
    }

    @TearDown
    public void tearDown() throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
        }
    }

    @Benchmark
    public long sequentialBenchmark() {
        return sequential();
    }

    @Benchmark
    public long forkJoinBenchmark() {
        return parallel();
    }
}
~~~

Run inside the `forkjoin-bench` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/forkjoin-bench-1.0.0.jar '.*SumBenchmark.*' -t 1
~~~

JMH outputs an `avgt` report in `ms/op` (**lower is better**). In this example, JMH uses **1 thread to invoke the benchmark** because of `-t 1`, while the private `ForkJoinPool` uses **4 workers** to compute the sum. This design measures **one summation request** per algorithm. To measure multiple concurrent requests, you must design a different benchmark workload and explicitly state the level of contention.

`@Setup` prepares the array and the private pool before the measurement loop, avoiding counting input-creation cost in each summation. Both `@Benchmark` methods return `long` so JMH can consume the result, reducing the risk of the JVM optimizing away the work. `@Fork(2)` runs two forked JVMs, and warmup/measurement use the declared parameters.

**Note when reading results:** `threshold` is a parameter for Fork/Join, yet JMH also runs the sequential baseline repeatedly for each `threshold` value even though the baseline does not use it. When comparing, match **the same `size`** and use only one corresponding sequential baseline; do not duplicate statistical data.

## 8. Recommended Experiment Matrix

| Parameter | Suggested Levels | Purpose |
| --- | --- | --- |
| `N` | 100,000; 1,000,000; 10,000,000 | Find a size large enough to benefit from task splitting. |
| `threshold` | 4,096; 16,384; 65,536 | Trade off task count against parallelism. |
| Pool parallelism | 1; 2; 4; 8 if hardware permits | Find useful parallelism levels on the machine. |
| JVM forks | At least 2 | Identify variance across independent runs. |
| Warmup/measurement | e.g., 3/5 iterations, 1 second each | Reduce cold-start effects and noise. |

The JMH template above already varies `size` and `threshold`. To test multiple worker counts, add `@Param({"1","2","4","8"}) public int workers;` and use `new ForkJoinPool(workers)` in `setup()`; note that this increases the number of benchmark combinations to run. Record the actual CPU configuration and avoid oversubscription when running inside a quota-limited container.

In your report, include **JDK version, CPU, cores/threads, RAM, OS, container/VM limits, JMH version, N, threshold, parallelism, score, and error bars**. Draw speed conclusions from actual results—never use an example timing value or a single random run as evidence.

### When Can Fork/Join Be Fast, and When Can It Be Slow?

Fork/Join has a good chance of winning when the input is sufficiently large, leaves perform substantial computation, branches are independent, and the machine has available processing resources. It tends to be slower when:

- Data is too small: task and pool overhead are large compared to a `for` loop.
- Threshold is too small: too many tasks, increasing fork/join/scheduling overhead.
- Threshold is too large: not enough tasks for workers to process concurrently.
- Memory is already saturated: adding workers does not increase `int[]` read bandwidth.
- CPU has few cores or is constrained by other workloads.
- The benchmark includes array allocation, pool creation, or uneven GC.

Every result must be explained by workload characteristics and machine conditions, not solely by worker count.

## 9. Common Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `int sum` in leaves | Sum overflows with large numbers. | Accumulate into `long` from the start. |
| Splitting into `[from,mid]` and `[mid,to]` | Double-counts the `mid` element. | Use `[from,mid)` and `[mid,to)`. |
| Not checking `threshold > 0` | Can cause infinite recursion on a 1-element range. | Validate input threshold and leaf condition. |
| Creating a task per element | Heavy scheduling overhead. | Group enough elements per leaf and tune threshold. |
| Forking both branches then joining immediately | Unnecessarily queues extra tasks. | Fork one branch, compute the other, then join. |
| Using a shared total with `AtomicLong` or locks | Contention/race, defeating divide-and-conquer. | Have tasks return local sums and combine them. |
| Modifying the array concurrently while reading | Inconsistent results. | Keep a snapshot or read-only data until done. |
| Creating a new pool in every benchmark call | Measures worker creation overhead as well. | Create the pool before measurement and reuse it. |
| Using the common pool with other workloads | Noisy results. | Use a private pool or document the sharing. |
| Not verifying the sum before measuring | "Fast" but potentially wrong. | Compare against baseline; test empty/overflow/odd `N`. |
| Generating data inside the measured loop | Measures setup, not just summation. | Prepare input before the benchmark. |
| Treating a single `nanoTime()` call as conclusive | Large noise from JIT/GC/OS. | Use JMH, multiple iterations/forks, and report error. |

## 10. Extension Exercises

**Exercise A — Odd-sized array:** try `N=1_000_003` and replace `expected` with `sequentialSum(data)` before comparing Fork/Join. Why can't `-500_000L` be kept after changing `N`? Verify that tasks do not drop the last element.

**Exercise B — Splitting threshold:** measure `N=100_000` and `N=10_000_000` with thresholds 1,024, 4,096, 16,384, 65,536, and 262,144. Tabulate JMH scores and variance. Explain why a threshold optimal for one `N` is not necessarily optimal for another `N`.

**Exercise C — Single worker:** run `new ForkJoinPool(1)` and compare with the sequential loop. Analyze task/recursion overhead when there is virtually no parallelism.

**Exercise D — Large-value sum:** test `int[] {Integer.MAX_VALUE, Integer.MAX_VALUE, -1}`. The correct result is `4_294_967_293L`. Temporarily change `long sum` to `int sum` in a test copy to observe the overflow error; restore the correct code afterward.

**Exercise E — Compare with a built-in API:** add `Arrays.stream(data).asLongStream().parallel().sum()`. It typically runs on the common Fork/Join pool, which has different configuration and contention characteristics from a private pool; explicitly note these differences when comparing, and do not assume all "parallel" operations share the same algorithm or worker count.

## 11. Acceptance Checklist

- [ ] Both sequential loop and `RecursiveTask<Long>` Fork/Join implementations exist; their results match.
- [ ] Range `[from,to)` has no overlaps or gaps; threshold is positive; empty arrays, odd-length arrays, and `int` overflow are handled.
- [ ] Tasks only read the array, each leaf computes a local sum, and there is no shared mutable total.
- [ ] `fork()`/`compute()`/`join()` are used properly and the pool is shut down when finished.
- [ ] Data is prepared before benchmarking; results are consumed/verified.
- [ ] Multiple values of `N`, `threshold`, and worker counts are measured; warmup and multiple iterations are used; JMH is preferred for performance conclusions.
- [ ] Machine/JDK specs and error margins are recorded; Fork/Join is not assumed to always be faster.

**Key takeaway:** Fork/Join helps split large problems into tasks that can run in parallel and then combine results, but for array summation, the sequential version is already highly optimized and memory can become the bottleneck. Being able to evaluate this problem properly comes from **proving correctness, measuring under controlled conditions, and explaining when Fork/Join wins or loses**.