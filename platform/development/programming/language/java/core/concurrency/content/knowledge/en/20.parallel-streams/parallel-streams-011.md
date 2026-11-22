# Avoiding Uncontrolled Nested Parallel Streams

**Nested parallel streams** occur when a stream pipeline running in parallel creates and executes one or more other parallel pipelines inside its tasks. For example, an outer loop processes a list of groups with `parallelStream()`, and then each group calls `parallelStream()` in an inner loop. Java allows writing this, but **more `parallel()` layers do not automatically mean faster execution**. Without accounting for the CPU budget, task size, and shared resources, an application can spend significant overhead on splitting work, scheduling, waiting for completion, contention, and memory without improving throughput.

The goal of this lesson is to recognize nested parallelism, understand why it can degrade performance, choose the right level of parallelism, and measure it using standard Java. The content applies to Java 17+; the complete examples below can be run with **JDK 21**.

## 1. Recognizing nested parallel streams

A common example:

```java
long total = groups.parallelStream()
        .mapToLong(group -> group.parallelStream()
                .mapToLong(value -> expensiveCpuWork(value))
                .sum())
        .sum();
```

This is an **illustrative snippet**; `groups` and `expensiveCpuWork` are not declared. We can see two levels:

1. **Outer level:** `groups.parallelStream()` requests parallel processing of the groups.
2. **Inner level:** for each group being processed, `group.parallelStream()` again requests parallel processing of the elements within the group.
3. **Wait point:** the inner group's `sum()` must return a result for the outer element's lambda to complete. The outer `sum()` then combines the group results.

Imagine 8 groups of 1,000 elements each:

```text
groups (8 parts)
   |
   +-- group A (outer task) -- inner parallel stream -- sum() --+
   +-- group B (outer task) -- inner parallel stream -- sum() --+
   +-- group C (outer task) -- inner parallel stream -- sum() --+--> total
   +-- ...                                                      |
   +-- group H (outer task) -- inner parallel stream -- sum() --+
```

A readable expression can create **multiple pipelines with their own scheduling overhead**, while the actual number of CPU cores remains unchanged. To understand this accurately, do not assume that "8 groups times 1,000 elements will create 8,000 threads": a parallel stream makes no guarantee of creating one thread per element.

### Why does using `parallel()` in the inner loop matter?

`parallel()` marks a pipeline as eligible for parallel processing, but the actual degree of parallelism also depends on the source's `Spliterator`, workload size, splitting strategy, terminal operation, and scheduler. If there are few elements or the work is too lightweight, extra splitting can cost more than the computation itself.

`group.stream()` creates a **sequential** pipeline. Therefore:

```java
groups.parallelStream()
      .map(group -> group.stream().map(this::transform).toList())
      .toList();
```

Here, **only the outer pipeline** requests parallelism; inside each group, processing is sequential. The snippet above illustrates an architectural option, not a standalone compilable program, since `groups` and `transform` are not declared.

## 2. How do parallel streams use actual resources?

In common OpenJDK/JDK implementations, parallel streams typically leverage the **Fork/Join framework**, specifically `ForkJoinPool.commonPool()`. Pool workers use *work stealing*: when a worker runs out of its own work, it can take ready work from another worker. At any given moment, the useful parallelism of CPU-bound work is still bounded by the available CPU cores/CPU quota.

**Three points to be precise about:**

- **There is no "separate pool per `parallelStream()`."** When running on ForkJoinPool workers, nested stream levels can share the same scheduling resources; the inner layer does not create new CPU cores or spawn unbounded OS threads by default.
- **You cannot multiply outer parallelism × inner parallelism to measure the thread count.** That is not an API contract. The number of split tasks, the number of actively running workers, and the amount of queued work are different concepts.
- **You cannot claim that every nested parallel stream will deadlock.** Fork/Join is designed to execute recursive tasks and has mechanisms to coordinate and join work. What you need to watch out for is overhead, waiting, contention, load imbalance, and unmanaged blocking; deadlock only occurs when there is an actual dependency/lock cycle causing a stall.

The Java Stream API lets you choose whether a stream is sequential or parallel, and **does not provide a public contract to bind a specific stream pipeline to a custom ForkJoinPool**. Submitting a parallel stream to a custom `ForkJoinPool` via `pool.submit(() -> stream.parallel()...)` may behave as expected on the JDK version you are using, but you should not assume it is a stable pool-control mechanism across all implementations. If you need independent resource and lifecycle control, use `ExecutorService` or design `ForkJoinTask` directly.

**Blocking I/O is even more dangerous than CPU-bound work:** if a lambda in a parallel stream waits on a socket/lock or another task, workers meant for CPU-bound work can be tied up, slowing down other tasks sharing the pool. `ForkJoinPool` has the `ManagedBlocker` mechanism for certain notified blocking scenarios, but arbitrary blocking calls do not automatically guarantee worker compensation. For I/O, you should choose a separate concurrency model and resource limit.

## 3. Main causes of poor nested parallel performance

| Cause | What happens | Common symptoms |
|---|---|---|
| **Task splitting overhead** | Each inner stream builds pipeline structures, splits work, and combines results | Small work units, yet CPU spends a lot of time on scheduling |
| **Many synchronization/join points** | Outer task waits for the inner pipeline's terminal operation | Wait time exceeds computation time |
| **Shared resource contention** | Multiple groups share cores, cache, memory bandwidth, or the pool | Throughput does not increase even when parallelism increases |
| **Group size imbalance** | One very large group, many very small groups | Workers sit idle while the heavy group runs for a long time |
| **Memory/GC pressure** | Multiple pipelines, intermediate objects, or per-group results stay live together | Increased allocation, GC activity, or heap usage |
| **Blocking inside workers** | I/O or locks hold workers meant for CPU parallelism | Other tasks slow down; low CPU utilization but high wait time |
| **Unsafe side effects** | Lambdas mutate shared `ArrayList`, `HashMap`, or counters | Corrupted data, inconsistent results |
| **Ordering constraints** | `sorted`, `limit`, `findFirst` on ordered sources, or `forEachOrdered` | Loses much of the benefit of parallel processing |

Crucially, **each risk depends on the workload**. If each group is huge, independent, and splits efficiently, an inner parallel level can be useful; however, when the outer loop is also parallel, you must measure the incremental benefit before keeping both.

A source with a few dozen elements and simple addition is usually not worth parallelizing. With a large source, heavy computation, evenly splittable data, and no shared mutable state, a parallel stream can deliver gains. There is no fixed element threshold that applies to every application.

## 4. Runnable example: three ways to handle the same problem

Suppose we have three groups of integers. We need to compute the sum of the **squares** of all elements. With data from 1 to 9, the result must be `1² + 2² + ... + 9² = 285`.

Create the file **`NestedParallelComparison.java`**:

```java
import java.util.List;

public class NestedParallelComparison {
    public static void main(String[] args) {
        List<List<Integer>> groups = List.of(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7, 8, 9));

        // Two parallel levels: valid, but not automatically the fastest.
        long nested = groups.parallelStream()
                .mapToLong(group -> group.parallelStream()
                        .mapToLong(x -> (long) x * x)
                        .sum())
                .sum();

        // Parallel by group only; each group is processed sequentially.
        long outerOnly = groups.parallelStream()
                .mapToLong(group -> group.stream()
                        .mapToLong(x -> (long) x * x)
                        .sum())
                .sum();

        // Flatten the groups and parallelize only a single pipeline.
        long flatOnce = groups.stream()
                .flatMap(List::stream)
                .parallel()
                .mapToLong(x -> (long) x * x)
                .sum();

        System.out.println("nested=" + nested);
        System.out.println("outerOnly=" + outerOnly);
        System.out.println("flatOnce=" + flatOnce);
    }
}
```

```bash
javac NestedParallelComparison.java
java NestedParallelComparison
```

Deterministic output:

```text
nested=285
outerOnly=285
flatOnce=285
```

All three approaches produce **the exact same mathematical result**. This example intentionally does not print timings because the dataset is too small; JIT warm-up, scheduling, and measurement overhead make `System.nanoTime()` microbenchmarks prone to misleading conclusions.

**Which approach should you use?**

- **`outerOnly`:** each group has clear semantics, there are enough independent groups, per-group computation is moderate, or group aggregation needs to preserve group boundaries.
- **`flatOnce`:** elements can be processed independently regardless of group; you want only a single parallel pipeline; keep in mind `flatMap` overhead, splittability, and processing order on real sources.
- **`nested`:** keep only when benchmark results prove both levels are needed on the actual workload, and there is no contention or blocking affecting the rest of the system.

Placing `parallel()` after `flatMap` makes **the outer pipeline parallel**; the streams returned by `List::stream` are inner sources used for flattening. This does not mean each group creates a new executor/pool. If group sizes are heavily skewed, `flatMap` does not always give the best load balance either; stream splitting depends on the source and implementation.

## 5. Practical rule: pick one primary level of parallelism

For CPU-bound nested loops, start with **one clear level of parallelism**:

### A. Parallel outer, sequential inner

Suitable when there are many relatively balanced groups and each group has enough work:

```java
long result = groups.parallelStream()
        .mapToLong(group -> group.stream()
                .mapToLong(this::calculate)
                .sum())
        .sum();
```

The snippet above is illustrative only because `groups` and `calculate` are hypothetical. Signs to reconsider: the number of groups is much smaller than the number of cores, or one group is significantly heavier than the others, in which case outer-only parallelism may be imbalanced.

### B. Sequential outer, parallel inner

Suitable when there are very few groups, each group is huge, and you want to process one group at a time:

```java
long result = groups.stream()
        .mapToLong(group -> group.parallelStream()
                .mapToLong(this::calculate)
                .sum())
        .sum();
```

The outer `stream()` is sequential; each group can use all appropriate parallelism before moving to the next group. This does **not** guarantee better speed than flattening; sometimes repeating parallel pipeline overhead for each group is costly. This is also illustrative code with undeclared components.

### C. Flatten and parallelize once

When individual elements are independent and you do not need to keep per-group results:

```java
long result = groups.stream()
        .flatMap(List::stream)
        .parallel()
        .mapToLong(this::calculate)
        .sum();
```

When per-group results are still needed, flattening can lose group information unless you carry a group id along; choose the form that matches your data semantics. You should also check whether `flatMap` produces a pipeline that splits easily enough; no single approach fits every source.

### D. Keep everything sequential

If the work is very small, order-dependent, hard to split evenly, or running inside an already busy CPU environment, a sequential `stream()` can be faster and more predictable. This is an important baseline, not a failure of concurrency.

**Rule:** based on the real workload, choose a task granularity large enough that computation cost significantly outweighs split/join overhead, and **let only one layer be primarily responsible for parallelism** unless solid benchmarks justify otherwise.

## 6. When you need an explicit worker limit: use ExecutorService

If you want to control the number of concurrent tasks separately from stream internals, you can schedule **one task per group** onto a bounded executor. Inside each task, use a sequential stream. This is the standard Java approach when you need explicit pool ownership, shutdown, `Future` retrieval, error handling, and lifecycle tracking.

Standalone Java 21 example, **`BoundedGroupExecutor.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedGroupExecutor {
    public static void main(String[] args) throws Exception {
        List<List<Integer>> groups = List.of(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7, 8, 9));

        List<Future<Long>> futures = new ArrayList<>();

        // Exactly two workers for three groups; no nested parallel streams.
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            for (List<Integer> group : groups) {
                futures.add(executor.submit(() ->
                        group.stream().mapToLong(x -> (long) x * x).sum()));
            }

            long result = 0;
            for (Future<Long> future : futures) {
                result += future.get();
            }
            System.out.println("bounded=" + result);
        }
    }
}
```

```bash
javac BoundedGroupExecutor.java
java BoundedGroupExecutor
```

Output:

```text
bounded=285
```

**Explanation:** The pool has at most two workers processing the submitted tasks in the example. Each task processes one group sequentially, and `Future.get()` collects the results; summing in futures order keeps the output deterministic. `try-with-resources` with `ExecutorService` has been supported since Java 19 and works on Java 21; `close()` waits for tasks to finish per the API contract.

**Warning about submission volume:** `newFixedThreadPool` uses an unbounded queue by default in the standard factory. Submitting a million tasks at once can still cause memory pressure even with only two workers. If data can arrive unboundedly, use a limit on pending tasks/batching, a bounded `ThreadPoolExecutor`, or backpressure. Limiting workers **does not automatically limit queued tasks**.

This pattern makes sense when each group is sufficiently large. If each group only does a few additions, the overhead of creating `Future` objects, queueing, and scheduling can be more expensive than a sequential stream.

### Do not "lock in" a parallel stream by relying on a custom ForkJoinPool

You may come across code like `customPool.submit(() -> data.parallelStream()...)`. Do not treat a specific stream's pool-selection behavior as a general guarantee provided by the Stream API. In particular, if the pipeline calls `parallelStream()` again at an inner level, you have not solved nested splitting—you have only changed the scheduling context based on implementation details. When you need an explicit scheduling configuration, `ExecutorService` or a custom `ForkJoinTask` provides a more appropriate contract and lifecycle.

## 7. If the inner computation is blocking I/O, change the model

Parallel streams work best for transformations/reductions that are **independent, have minimal side effects, and are typically CPU-bound**. An inner lambda making blocking HTTP, JDBC, or file calls in a Fork/Join pool can hold workers waiting on I/O, slowing down other computations sharing the common pool.

Example to reconsider (illustrative only):

```java
var result = orders.parallelStream()
        .map(order -> order.lines().parallelStream()
                .map(line -> remotePriceService.fetch(line)) // Blocking I/O.
                .toList())
        .toList();
```

Here `orders`, `lines()`, and `remotePriceService` are hypothetical; the snippet is not standalone runnable code. If the external service limits concurrency to 20 simultaneous requests, you still should not send unbounded requests even if you have 100 cores.

Better options include: **a managed executor** with a limit on concurrent I/O, an appropriate async API, or in Java 21, one virtual thread per blocking I/O task paired with a `Semaphore`/connection pool matching the quota. Virtual threads reduce thread overhead in many I/O-waiting scenarios, but they do not increase the capacity of the downstream database or API. Never use nested parallel streams as an ad-hoc mechanism to control request concurrency.

No single option is right by default for every I/O driver; timeouts, cancellation, bounded queues, resource quotas, and the actual workload still need to be measured and handled.

## 8. Correctness before speed: side effects and reduction

When adding a parallel layer, lambdas can execute concurrently and in an unpredictable order. Prefer **stateless operations** and safe reductions.

### A common bug

```java
List<Integer> results = new ArrayList<>();
groups.parallelStream().forEach(group ->
        group.parallelStream().forEach(results::add));
```

This is an illustrative snippet only (`groups` is not defined). `ArrayList` is not safe for concurrent `add` calls from multiple threads; data can be lost, corrupted, or throw errors. Do not "fix" this by switching to `Collections.synchronizedList` and assuming nested parallel will be fast: locking still causes contention, and the result order is not guaranteed to be what you expect.

A cleaner way to express the result as a pipeline:

```java
List<Integer> results = groups.stream()
        .flatMap(List::stream)
        .parallel()
        .map(x -> x * 2)
        .toList();
```

This snippet assumes `groups` is `List<List<Integer>>`. `Stream.toList()` collects results in encounter order if the source is ordered, returning an unmodifiable list. It does not require a shared `ArrayList` mutated by multiple workers. If you want per-group results, use `map` to return a separate list for each group and collect in the outer pipeline.

### Reduction correctness

Parallel `reduce` relies on combining partial results. The combiner function should be **associative**, the identity value must be correct, and lambdas must not interfere with the source during traversal. Non-overflowing `long` addition combines predictably; with `double`, changing addition order can produce bit-level differences due to floating-point rounding. Concatenating `String` with `+` in a reduction can cause heavy allocation; consider `Collectors.joining()` where appropriate.

**Processing order:** `forEach` on a parallel stream does not guarantee encounter order; `forEachOrdered` preserves order but can reduce throughput. Ordered pipelines containing `limit`, `skip`, `takeWhile`, `dropWhile`, `sorted`, or `distinct` may require extra coordination depending on the source and semantics. Only use `unordered()` when business logic truly does not care about order—never use it just to "speed things up" if it breaks correctness.

**Short-circuiting:** `findAny()` may return different elements across runs; `findFirst()` has ordering constraints. Nested parallel short-circuiting may perform extra work before cancelling or detecting a result across branches; do not rely on the mapper invocation count as a contract.

## 9. Load imbalance and task granularity

Suppose one group has 100,000 elements, while 100 other groups have 5 elements each. If you only parallelize the outer level, one worker may get stuck with the huge group while the small groups finish quickly. Before enabling inner-loop parallelism, consider:

1. **Splitting large groups into chunks** evenly enough to schedule at a **single level**, keeping `groupId` if per-group aggregation is needed.
2. **Using a flat pipeline** if elements are independent; measure whether the source/`Spliterator` supports good splitting.
3. **Scheduling tasks by group/chunk in an executor** with an appropriate worker count for resource control.
4. **Keeping it sequential** if the element count is small or per-element work is cheap.

For a `rows × cols` matrix problem that performs the same independent computation on each cell, you can represent it as **a single linear index range** (illustrative snippet, not a standalone program):

```java
long total = java.util.stream.LongStream
        .range(0, (long) rows * cols)
        .parallel()
        .map(index -> {
            int row = (int) (index / cols);
            int col = (int) (index % cols);
            return calculate(row, col);
        })
        .sum();
```

Here `rows` and `cols` must be positive, and `calculate` is a hypothetical function returning `long`; make sure the indices fit within `int` and the product `(long) rows * cols` does not overflow. This form creates **a single parallel level** instead of `rows` parallel outside and `cols` parallel inside, and can allow a contiguous index range to split tasks more evenly. However, if the computation maintains per-row state, transforming it this way requires re-evaluating safety conditions and semantics.

## 10. Evaluate performance by measurements, not by counting `parallel()` calls

Compare at least **four equivalent versions producing the same result**:

1. Fully sequential.
2. Outer-level parallel only.
3. Flattened / single sensible parallel level.
4. Nested parallel, solely to verify whether any additional benefit exists.

Measure with a sufficiently large and representative workload; do not use the 9 integers from a textbook example to draw conclusions about throughput. Use **JMH** for Java microbenchmarks because JIT, dead-code elimination, warm-up, and GC can skew results when manually timing a loop with `System.nanoTime()`. For application workloads, also look at CPU utilization, throughput, tail latency, allocation, GC, queued task count, and contention.

Experiment design:

- Run on the same JVM/JDK, same CPU cores/quota, same data, same terminal operation, and same computation logic.
- Warm up first; repeat multiple iterations and examine the distribution rather than just the fastest run.
- Ensure results are consumed so the JIT does not eliminate computation; verify that all versions produce correct output.
- Test small/medium/large group counts, balanced and skewed groups, and lightweight vs. heavy per-element work.
- Also measure when the system has **other load using the common pool**, since isolated benchmarks can miss real-world contention.
- If I/O is involved, measure external quotas and status and set timeouts; do not compare using uncontrolled random data or constantly changing services.

How to interpret results: if the nested version uses more CPU without increasing throughput, it is likely overhead or a contended resource. If CPU is low and wait time is high, investigate blocking/locking and the data source. If flattening is slow, examine `flatMap`, locality, and splitting before concluding that "nested is always better."

**Do not tune** `-Djava.util.concurrent.ForkJoinPool.common.parallelism` JVM-wide just to optimize one piece of code if other components share the common pool. That property alters a shared resource and is not a fix for over-splitting, broken pipeline semantics, or blocking. If you need workload isolation with a clear contract, design a dedicated executor.

## 11. Common design mistakes and how to fix them

| Mistake | How to fix it |
|---|---|
| Enabling `parallelStream()` at every level because "we have many cores" | Pick one parallel level and prove the benefit with benchmarks |
| Assuming nested streams create their own pool and unlimited threads | Understand the scheduler/common pool; count tasks/threads via real profiling |
| Assuming nested parallel always deadlocks | Only diagnose deadlock when there is a specific dependency/lock cycle |
| Calling blocking I/O inside Fork/Join workers | Use an I/O concurrency model with explicit timeouts and quotas |
| Inner stream has only a few elements yet is still parallel | Use sequential `stream()` to avoid overhead |
| `forEach` writing to a shared mutable collection | Use stream reduction/`collect` with proper semantics or partitioned data |
| Skewed data with group-level parallelism only | Flatten/chunk appropriately and re-measure balance |
| Bounding a fixed thread pool while still submitting unbounded tasks | Use a bounded backlog, batching, or backpressure |
| Using a custom FJP assuming Stream API guarantees a specific executor | Treat it as implementation-dependent; choose task APIs with explicit contracts |
| Comparing performance with a single `nanoTime` run | Use JMH benchmarks or load tests with warm-up and multiple iterations |
| Relying on `forEach` order in a parallel stream | Use reduction/collection or `forEachOrdered` when semantics require it |
| Estimating CPU concurrency via `availableProcessors()` multiplied by nested levels | Use actual CPU/quota as your budget; avoid multiplying parallelism levels |

### Checklist before merging a nested stream

- Does the pipeline **truly need two parallel levels**? Why is one level not enough?
- Are the elements and groups large/independent enough to split?
- Is there any I/O, lock, `synchronized`, `Future.get()`, or `join()` inside the mapper?
- Is there any shared mutable state, `ThreadLocal`, or side effect that needs protection?
- Are there encounter-order constraints, short-circuiting, or non-associative reductions?
- Is anything else sharing the common pool?
- Do you have a sequential baseline, a single-level parallel baseline, and reproducible benchmark results?
- Are there scarce resources or task backlogs that require explicit bounds?

## 12. Self-check exercises

**Q1.** 20 groups, 10 elements each, and the operation is just integer addition. Why is parallelizing both levels unlikely to help?

**Q2.** 2 groups, 5 million independent elements each, CPU-heavy computation. Compare outer-only parallel, inner-only parallel, and single-level flatten strategies, and explain why benchmarking is needed.

**Q3.** Why can `groups.parallelStream().forEach(group -> group.parallelStream().forEach(sharedList::add))` produce wrong results even ignoring speed?

**Q4.** A mapper calls an HTTP API taking 200 ms, and the API limits concurrent requests to 10. Should you raise the common pool's parallelism to 500?

**Q5.** You observe that nested parallel slows down a program. Can you conclude for certain that it is a deadlock, or that 1,000 groups will create 1,000 OS threads?

**Suggested answers:** (1) splitting and combining overhead is high compared to the work; (2) outer-only has too few groups to split, inner-only utilizes the large groups but processes one group at a time, and flatten splits elements at one level—measure overhead, locality, and balance; (3) the shared mutable list is not thread-safe; (4) no, you need an I/O model and a real concurrency limit of 10; (5) no, the scheduler and task count differ from thread count, and a specific stalling condition must be proven.

### Official documentation

- [Java SE 21 — Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): `parallel()`, `flatMap()`, semantics of `forEach`, `reduce`, and other operations.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavioral parameters, side effects, parallelism, and reduction.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work stealing, blocking, and `ManagedBlocker`.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle management, `Future`, and bounded worker concurrency.
- [OpenJDK JMH project](https://openjdk.org/projects/code-tools/jmh/): dedicated Java benchmarking tool.
