# Avoiding Nested Parallelism and Choosing Where to Parallelize

The **Java Stream API** lets you replace a sequential pipeline with a parallel one via `parallel()` or `parallelStream()`. The usage looks simple, yet performance does not improve merely by adding more `parallel()` calls. A common mistake is **parallelizing both the outer loop and the inner loop** of hierarchical data: data groups, individual files, transaction batches, or matrix rows.

This lesson belongs to the **Parallel Processing Semantics** chapter, focusing on two decisions:

1. **Should you parallelize at all?** Is the work large enough, independent, splittable, and not bottlenecked primarily by I/O or shared state?
2. **If yes, where should the parallel boundary be placed?** Parallelize across outer batches, across inner elements, or reorganize into **a single** sufficiently fine-grained collection of work to split?

Starting principle: **prefer a single deliberate layer of parallelism; use nested parallelism only when measurements show it truly helps and does not alter semantics.**

## 1. What is nested parallelism?

Suppose there are multiple batches of integers; each batch needs to be summed, and then the batch sums are totaled. We have a two-level structure:

```text
Data:
  Batch A -> [1, 2, 3]
  Batch B -> [4, 5]
  Batch C -> [6, 7, 8]

Outer level: processes batches A, B, C
Inner level: processes the elements of each batch
```

There are four ways to organize this:

| Outer level | Inner level | Meaning |
| --- | --- | --- |
| Sequential | Sequential | Simplest baseline. |
| **Parallel** | Sequential | Independent batches are split; each batch is summed sequentially. |
| Sequential | **Parallel** | One batch is processed at a time, while elements within a batch can split. |
| **Parallel** | **Parallel** | Nested parallelism: inner pipelines also request parallel execution. |

The following snippet is an example of **nested parallelism**:

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {1, 2, 3},
    new int[] {4, 5},
    new int[] {6, 7, 8}
);

long total = batches.parallelStream()
    .mapToLong(batch -> Arrays.stream(batch)
        .parallel()
        .asLongStream()
        .sum())
    .sum();

System.out.println(total); // 36
```

This code is **not forbidden by Java** and can produce the right result. The issue is increasing the levels of requested parallelism without proving any additional useful compute capacity exists. With a few tiny arrays as in the example, scheduling and split/merge overhead will likely outweigh the additions.

**Distinction:** A single stream that calls `parallel()` once and passes through multiple `map`, `filter`, and `reduce` steps is **not** nested parallelism. Nested parallelism typically arises when a lambda inside one pipeline creates and runs **another parallel pipeline**.

## 2. `parallel()` is a pipeline mode, not a separate stage

Within the same pipeline, `parallel()` and `sequential()` set the execution mode for the **entire pipeline when the terminal operation runs**. They do not mean that operations before `parallel()` run sequentially while operations after it run in parallel.

```java
import java.util.stream.IntStream;

long value = IntStream.rangeClosed(1, 100)
    .map(n -> n * 2)
    .parallel()
    .filter(n -> n % 3 == 0)
    .asLongStream()
    .sum();
```

In this example, `map` does not become a "separate sequential stage" just because it is declared before `parallel()`. Java Streams apply either sequential or parallel mode to the pipeline at execution time.

```java
import java.util.stream.IntStream;

boolean parallel = IntStream.range(0, 10)
    .parallel()
    .sequential()
    .isParallel();

System.out.println(parallel); // false
```

If a sequential stage truly must **finish completely** before a parallel stage begins, you need an explicit processing boundary, usually materializing intermediate data or designing two separate pipelines. That carries memory and copying costs, so use it only when business or performance requirements justify it.

## 3. Why is nested parallelism usually harmful?

`parallelStream()` does not create a fresh isolated set of CPUs per pipeline. In typical Java applications, parallel Stream execution relies on **fork/join** and `ForkJoinPool.commonPool()`. Two nested pipelines can contend for the same execution resources.

Visualize batches being computed:

```text
Available CPUs:     [Core 1] [Core 2] [Core 3] [Core 4]

Outer level:         Batch A  Batch B  Batch C
                        |        |        |
Inner level:         split A   split B  split C
                        \        |       /
                many tasks needing split/merge & coordination
```

Notable costs:

1. **Work fragmentation:** each small batch spawns further subtasks. Task count and coordination steps can exceed useful computations.
2. **Resource contention:** nested pipelines compete for the same worker pool, CPU caches, memory bandwidth, and synchronization resources.
3. **Load imbalance:** one huge batch and many tiny batches can leave batch-level splitting uneven; adding inner parallelism does not necessarily fix it.
4. **Wait times and latency:** outer tasks must wait for inner terminal operations to finish; batches may block behind one another under uncontrolled scheduling.
5. **Memory and GC pressure:** creating numerous intermediate objects, buffers, or tasks increases allocations and garbage collection work.
6. **Harder behavioral analysis:** when side effects, logs, I/O access, or non-compliant aggregations exist, outputs become harder to reproduce.

These are **risks**, not a guarantee that every nested pipeline is slower. Depending on data and environment, execution can behave differently; speed conclusions must rest on measurement.

Likewise, do not claim that two `parallel()` calls always create twice as many threads, or that nested parallelism always causes deadlock on its own. Worker counts and execution depend on the runtime, pool, source, workload, and inner code.

## 4. Three clear versions for two-level data

Below is a standalone program (Java 8+) comparing the **semantics** of the choices. It uses `long` when summing `int` values to reduce 32-bit overflow risk:

```java
import java.util.Arrays;
import java.util.List;

public class ChooseParallelLevel {
    static long sequential(List<int[]> batches) {
        return batches.stream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .sum())
            .sum();
    }

    static long outerParallel(List<int[]> batches) {
        return batches.parallelStream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .sum()) // Each batch is processed sequentially.
            .sum();
    }

    static long innerParallel(List<int[]> batches) {
        return batches.stream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .parallel()
                .sum())
            .sum(); // Batches are processed one after another.
    }

    public static void main(String[] args) {
        List<int[]> batches = Arrays.asList(
            new int[] {1, 2, 3},
            new int[] {4, 5},
            new int[] {6, 7, 8}
        );

        System.out.println(sequential(batches));    // 36
        System.out.println(outerParallel(batches)); // 36
        System.out.println(innerParallel(batches)); // 36
    }
}
```

All three options return the same value when data is unmutated and sums do not overflow. Yet **they are not equivalent in cost**:

- `sequential` fits as a baseline and for small batches.
- `outerParallel` fits when there are **many independent batches**, with enough work per batch to offset scheduling cost and relatively balanced batch sizes.
- `innerParallel` can fit when there are **very few batches**, yet a batch holds very many elements and the inner source splits efficiently.

Do not choose based solely on line count. Look at task count, magnitude, and skew across batches.

## 5. Choosing the parallelization point by work granularity

**Granularity** is the amount of work an independent task performs. If tasks are too small, distribution overhead exceeds gains; if too large or unevenly distributed, some workers sit idle while another stays busy.

| Workload shape | Starting choice | Reason |
| --- | --- | --- |
| A few dozen elements, very cheap math | **Sequential** | Parallel overhead is rarely worthwhile. |
| Thousands of independent batches, each large enough | **Outer parallel** | Splits by batch; per-batch logic stays clear without pool nesting. |
| One massive primitive array | **Inner parallel**, i.e., the array's stream itself | Only one large source needs partitioning. |
| A few huge batches and many tiny ones | **Redesign into evenly sized chunks** | Avoids a trailing huge task stretching overall runtime. |
| Many elements bottlenecked by files, network, or DB | **Consider a dedicated controlled I/O model** | CPU parallel streams are not inherently suited to blocking I/O. |
| Must preserve observable action order | **Prefer sequential**, or parallel with ordered merging | Order-preservation cost can erase gains. |
| Shared mutable state exists | **Redesign to be element-independent first** | `parallel()` does not make racy code safe. |

A practical workflow:

1. Start from a **correct, tested** sequential version.
2. Identify CPU-heavy sections via profiling or real metrics.
3. Evaluate whether the source's Spliterator splits well (arrays, index ranges, and `ArrayList` are usually better than hard-to-split sources).
4. Pick **one** level with plenty of independent work.
5. Re-measure and verify **correctness** before considering further optimization.

If one parallel level already saturates CPU resources, adding another level usually creates no extra compute capacity; it mainly changes how work is split and adds coordination cost.

## 6. Reorganizing the source instead of nesting parallelism

If batches consist of independent elements, you can try creating **a single stream of all elements** and parallelizing at one point:

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {1, 2, 3},
    new int[] {4, 5},
    new int[] {6, 7, 8}
);

long total = batches.stream()
    .flatMapToInt(Arrays::stream)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(total); // 36
```

This is **a single parallel pipeline**, with no parallel stream created inside a lambda. It is a clear formulation when every element shares the same processing and we only need one final aggregation.

However, `flatMap` does not guarantee turning any hierarchical source into balanced chunks. When one batch is huge and others are tiny, pipeline splittability can still be constrained by the source structure. **Do not treat flattening as an always-faster trick**; measure and inspect Spliterator characteristics.

If the data already lives in **one large primitive array**, use the array source directly for splitting:

```java
import java.util.Arrays;

int[] values = {1, 2, 3, 4, 5, 6, 7, 8};

long sum = Arrays.stream(values)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(sum); // 36
```

For problems with many heavily skewed batches, another option is **pre-building a list of balanced chunks/work units** before calling stream, so each chunk has substantial, roughly comparable work. Preparing chunks costs memory and time; it is only worthwhile if measurements prove a benefit.

## 7. A batch example: processing objects without nested parallelism

Suppose the data is `List<List<Integer>>` and we must report each batch's sum in the exact original batch order. We can parallelize across batches and sum each batch sequentially:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<List<Integer>> groups = Arrays.asList(
    Arrays.asList(1, 2, 3),
    Arrays.asList(4, 5),
    Arrays.asList(6, 7, 8)
);

List<Long> sums = groups.parallelStream()
    .map(group -> group.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .collect(Collectors.toList());

System.out.println(sums); // [6, 9, 21]
```

`groups` is a `List` with encounter order, and `Collectors.toList()` preserves encounter order in the output. **Batch computation order may vary**, yet results are placed in exact batch order.

In another case, if each batch must call an external service and update shared state, this is no longer pure CPU processing. You need connection limits, retries, timeouts, idempotency, and commit ordering. Do not add `parallelStream()` automatically just because batches look independent.

## 8. Behavioral contracts and reduction matter more than thread count

In a parallel pipeline, `map`, `filter`, and other lambdas should be **non-interfering** and **stateless** (not relying on shared mutable state). A common mistake is keeping an external counter or `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> output = new ArrayList<>();

// WRONG EXAMPLE: multiple workers mutate a non-thread-safe ArrayList.
IntStream.range(0, 1000).parallel()
    .forEach(output::add);
```

This can lose data, alter order, or cause structural corruption. Instead of pushing results into an external mutable variable, use a collector:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> output = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toList());

System.out.println(output.size()); // 1000
```

`collect` manages accumulation containers and combiners. No shared list across workers is needed.

### Combiners must satisfy the contract

For `reduce`, the combining operation must have a valid **identity** and **associativity**. For example, integer addition (assuming no overflow) qualifies; subtraction is not associative:

```java
import java.util.stream.IntStream;

int sum = IntStream.rangeClosed(1, 4)
    .parallel()
    .reduce(0, Integer::sum);

System.out.println(sum); // 10

// DO NOT USE subtraction as a parallel reduction:
// .reduce(0, (left, right) -> left - right)
```

A matching sequential result on a small case does not prove a reduction is valid when data is split and merged in parallel. Similarly, passing `new ArrayList<>()` as the identity to `reduce` and mutating it is not a valid replacement for `collect`.

### `AtomicInteger` does not fix an algorithmic flaw

Swapping an `int[]` counter for `AtomicInteger` can make incrementing thread-safe, yet still creates a **contention point**. If a predicate depends on `getAndIncrement()` order, which elements are selected will still depend on worker scheduling. Use element data to make decisions and let `count`, `sum`, `reduce`, or `collect` aggregate results.

## 9. Ordering, short-circuiting, and stateful operations

Parallelization can increase overhead when a pipeline must preserve encounter order or coordinate across source partitions:

| Operation | Consideration when parallel |
| --- | --- |
| `forEach` | Does not guarantee action invocation order on ordered sources. |
| `forEachOrdered` | Preserves encounter order but may increase coordination, limiting parallel gains. |
| `findFirst` | On ordered sources must return the first element, even if later elements finish earlier. |
| `findAny` | May return any matching element; suitable when "first" is genuinely unnecessary. |
| `limit`, `skip` | On ordered parallel streams, maintaining exact prefix/skip boundaries can add cost. |
| `distinct` | Deduplication requires tracking seen elements; ordered distinct can need coordination/buffering. |
| `sorted` | Stateful operation, typically must process the entire finite source before emitting sorted output. |

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> firstTen = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .limit(10)
    .collect(Collectors.toList());

System.out.println(firstTen); // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
```

`limit(10)` must keep **the first ten elements in the source's encounter order**. The pipeline may run and cancel tasks across different source chunks; do not deduce that the lambda runs exactly ten times or that exactly ten elements are read in every implementation.

`unordered()` can relax some ordering constraints in the pipeline if business rules permit, yet it changes the **result contract**: for instance, `findFirst()` after `unordered()` no longer means the first element of the original source. Do not use it merely as a performance trick when order is an actual requirement.

## 10. Determinism of results and floating-point addition

Parallel semantics do not necessarily make results **wrong**; results can satisfy the contract while differing in observed order or slightly due to arithmetic:

```java
import java.util.stream.DoubleStream;

double sequential = DoubleStream.of(1e16, 1.0, -1e16)
    .sum();

double parallel = DoubleStream.of(1e16, 1.0, -1e16)
    .parallel()
    .sum();
```

Do not write tests requiring two `double` results to match bit-for-bit across all datasets and splits. `double` addition is not strictly associative due to binary rounding; even when an API uses compensated summation, result merging can still introduce slight differences.

With integer sums, results are exact and consistent provided values stay within type bounds and the reduction follows contract. When currency or high decimal accuracy is required, choose an appropriate numeric representation such as smallest integer units, `BigInteger`, or `BigDecimal`, with explicit rounding rules and overflow checks.

**Nested parallelism** is not the sole cause of non-reproducible results. Shared state, `forEach` order, shared random generators, I/O, and non-associative reductions can cause issues **even in a single parallel pipeline**.

## 11. Different sources have different splittability

Parallel Streams rely on splitting a source into independent chunks. That capability depends heavily on the source's **`Spliterator`**:

- **Arrays, `ArrayList`, `IntStream.range`** typically have known sizes and split favorably.
- **`LinkedList`** or linear-traversal sources can incur different splitting costs depending on implementation and size.
- **`Stream.iterate`** has stateful dependencies between elements; not naturally independent like index ranges.
- **`Stream.generate`** is unbounded unless sliced; using a supplier with shared state can cause contention.
- **`Files.lines`**, network, and database sources add I/O overhead, resource management, and data consistency concerns.

Thus the same `map(...).reduce(...)` can benefit from parallelism on a large array yet fail to benefit on a hard-to-split source or small dataset. When writing a custom Spliterator, `trySplit()`, `estimateSize()`, and `characteristics()` must obey contracts; do not attach `SIZED`/`SUBSIZED` arbitrarily hoping for speed.

With extremely skewed inputs, you can prepare **reasonably balanced chunks** and use an `IntStream.range` over chunk indices. That is one way to organize work, not a universal optimum for every workload.

## 12. Do not use parallel streams as a bounded I/O scheduler

CPU-bound and I/O-bound workloads have different orchestration requirements:

| CPU-bound | Blocking I/O |
| --- | --- |
| Most time spent computing. | Most time spent waiting on network, disk, or DB. |
| Can benefit from multiple cores when data is independent and large enough. | Needs connection limits, timeouts, retries, backpressure, or task cancellation. |
| Parallel streams can be a suitable tool. | Usually needs async APIs, `ExecutorService`, or controlled I/O orchestration. |

For example, a pipeline using `parallelStream()` to call an external API per record can **tie up workers while waiting on I/O**, impacting other CPU tasks sharing the resource. When slow or blocking calls nest, wait times can become unpredictable.

Do not claim every case of blocking I/O in a parallel stream causes deadlock. The more accurate problem is **lack of concurrency control and resource contention**, especially when logic depends on other tasks needing the same workers. For applications needing explicit I/O bounds, choose an execution mechanism that lets you configure concurrency, timeouts, and cancellation.

## 13. Common pool and resource control limits

In common practice, parallel streams use `ForkJoinPool.commonPool()`. Key points to remember:

1. **The pool is a shared resource across application execution**, not a new pool per `parallel()`.
2. Useful worker count cannot grow indefinitely with nested streams; core count, blocking work, and runtime settings impose limits.
3. Serving many concurrent requests where each opens a parallel pipeline can cause contention even when **there is no nesting in source code**.
4. `Stream.parallel()` has no standard parameter to select a custom executor or cap workers per request.

Some projects try invoking a parallel stream inside a custom `ForkJoinPool` task to steer pool selection. Avoid treating this as a universal API contract across all JDKs and usages; if strict execution-policy control is needed, designing directly with `ExecutorService`, `ForkJoinTask`, or an appropriate library is clearer.

Especially, do not alter global common pool settings as a quick fix for nested parallelism. Such changes affect other parts of the application, not just the pipeline being tuned.

## 14. Measuring performance properly

Decisions about which level to parallelize must be verified on **real workloads or realistic benchmarks**. Factors to include in measurements:

- Batch count, average batch size, batch-size distribution, and skew between small and large batches.
- Per-element compute cost: simple addition differs vastly from heavy CPU algorithms.
- Source size and Spliterator splittability.
- External concurrency (number of requests, threads, other tasks).
- *Throughput*, mean latency, p95/p99 tail latency, memory allocation, and GC.
- Hardware configuration, core count, JDK version, and JIT warm-up state.

Do not rely on a single `System.nanoTime()` around a stream block for final conclusions. The JVM has warm-up, JIT optimization, system noise, and dead-code elimination. For Java microbenchmarks, **JMH** is the right tool, offering warm-up, multiple iterations/forks, and blackholes to prevent compiler elimination.

Design variants to compare:

```text
A. outer sequential + inner sequential
B. outer parallel   + inner sequential
C. outer sequential + inner parallel
D. outer parallel   + inner parallel   // control variant
E. single flat parallel stream or chunked split
```

Across all variants, **verify result equivalence** before comparing timings. For `double`, use an appropriate tolerance; for ordered data, compare according to the truly required ordering contract.

### How to interpret measurements

If B beats A while D is slower than B, that indicates **outer-level parallelism is sufficient** in that test configuration. If C beats B when there is only one massive batch, consider **parallelizing the large inner source**. If E outperforms D on heavily skewed multi-batch data, chunking may beat nesting. These conclusions must remain tied to the specific workload and JDK, not treated as universal laws.

## 15. Examples of choosing design by business goal

### Case A: processing many independent dossiers

Each dossier has dozens of fields; there are very many dossiers. Choose to parallelize **across dossiers**, while processing fields within one dossier sequentially:

```java
import java.util.Arrays;
import java.util.List;

List<List<Integer>> records = Arrays.asList(
    Arrays.asList(1, 2, 3),
    Arrays.asList(4, 5, 6),
    Arrays.asList(7, 8, 9)
);

long total = records.parallelStream()
    .mapToLong(record -> record.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .sum();

System.out.println(total); // 45
```

In this example, dossiers share no accumulation state. `record.stream()` is created separately per dossier and runs sequentially.

### Case B: one very large numeric set

There is only **one large data source**, such as an `int[]` array. Choose to parallelize **directly on the array**:

```java
import java.util.Arrays;

int[] values = {10, 20, 30, 40, 50};
long total = Arrays.stream(values)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(total); // 150
```

The array here only illustrates syntax; with five elements, sequential is almost always the sensible baseline. The design is only worth testing in parallel when computation volume is sufficiently large.

### Case C: many skewed batches

One batch has millions of elements while others have only a few. Outer parallelism may fail to balance load; parallelizing at both levels may spawn extra tasks yet remain inefficient. Consider **splitting large batches into independent chunks** and running one parallel pipeline over the chunk list.

The deciding factor is not "how many `parallel()` calls there are," but the **total number of useful work units** and how evenly they distribute across available resources.

## 16. Common pitfalls

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Adding `parallel()` to both outer and inner makes it slower | Split/merge overhead and resource contention | Keep one parallel level; measure the alternative. |
| Many-core machine yet stream is barely faster | Small data, cheap mapper, hard-to-split source, memory bandwidth, or heavy coordination | Increase useful granularity, pick a splittable source, profile. |
| Concurrent requests cause latency spikes | Requests contend on the common pool or CPU | Consider capping concurrency at the application layer. |
| Results vary across runs | Side effects, shared state, bad combiner, or floating-point order | Use stateless functions, contract-compliant collect/reduce, define tolerances. |
| Result list drops elements | `parallel().forEach(sharedArrayList::add)` | Use `collect` or proper concurrent coordination. |
| Logs print out of order | `forEach` does not guarantee encounter order | Use `forEachOrdered` only when order is mandatory; accept the cost. |
| `sorted`/`distinct`/`limit` cause slowdowns | Stateful/ordered operations require extra coordination | Optimize pipeline without changing semantics; re-measure. |
| Blocking I/O slows down other CPU tasks | Workers held while waiting on external I/O | Use an I/O model with explicit concurrency limits. |
| `parallel()` mid-pipeline did not create "two stages" as hoped | Execution mode applies to the whole pipeline | Use an actual processing boundary if separate phases are needed. |
| Nested parallelism only seems fast on a dev machine | Hardware, JDK, and load differ | Benchmark across sizes and production-like load. |

## 17. Practice exercises

**Exercise 1 — Identifying nested parallelism.** Given:

```java
long result = batches.parallelStream()
    .mapToLong(batch -> Arrays.stream(batch)
        .parallel()
        .asLongStream()
        .sum())
    .sum();
```

Point out the two syntactically distinct parallel pipelines and rewrite so only the **outer level** is parallelized. Explain why small batches rarely warrant their own inner parallelism.

**Exercise 2 — Choosing where to parallelize.** With 10,000 batches of 100 elements each and a relatively heavy CPU calculation, compare expected behavior of `outerParallel` vs. `innerParallel`. If there were only **one** batch of 10 million elements, how would your decision change?

**Exercise 3 — Flattening.** Write a pipeline using `flatMapToInt(Arrays::stream).asLongStream().parallel().sum()` for `List<int[]>`, and verify its result matches the sequential version. Explain why flattening does not guarantee balanced splits when batch sizes are heavily skewed.

**Exercise 4 — Shared state.** Fix the `parallel().forEach(output::add)` example into a valid collector. What does switching `ArrayList` to `Collections.synchronizedList` solve, and why should you still prefer a collector that avoids external side effects?

**Exercise 5 — Ordering and floating-point.** Create `IntStream.range(0, 1000).parallel().boxed().limit(10).collect(toList())`. Verify the resulting list matches encounter order. Then try `forEach` to observe print order, without writing a test asserting fixed `forEach` output.

**Exercise 6 — Benchmarking.** Build a timing and throughput comparison table for the five variants A–E in section 14 across balanced batches, skewed batches, and small datasets. Run warm-up and repeated measurements; base conclusions on data rather than the number of `parallel()` calls.

**Takeaway:** `parallel()` helps utilize compute resources when work is **independent, large enough, and splittable**. Parallelizing both an outer stream and an inner stream typically increases orchestration overhead and contention without adding CPU cores. Pick **one parallelization level with appropriate granularity**, use lambdas free of shared mutable state, ensure reductions obey their contracts, and measure on real workloads. When one batch is huge or data is imbalanced, consider redesigning work units rather than automatically adding another `parallel()` layer.