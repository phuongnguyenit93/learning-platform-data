# Stream.parallel() and parallelStream() in Java

## 1. Lesson Objectives

**Parallel Stream** allows the Java Stream API to execute parts of a pipeline across multiple processing threads, primarily to leverage multiple CPU cores when the dataset is large enough and the work per element is independent. Two common ways to create one are **`stream().parallel()`** and **`parallelStream()`**. Both aim for a pipeline with *parallel mode*, but they differ in API location, supported source types, and when the mode is switched.

After this lesson, you will understand how to use both APIs properly; know what is guaranteed regarding results, ordering, and execution threads; avoid race conditions when using shared state; choose safe `reduce`/`collect` operations; and determine when parallelism actually helps. The scope is Java SE and JDK concurrency, **with no Spring dependency**. Program examples use Java 17+.

## 2. Direct Answer: Where Do They Differ?

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

var first = numbers.stream().parallel();
var second = numbers.parallelStream();
~~~

This is an illustrative snippet inside a method, assuming `java.util.List` is imported. With standard JDK lists, both expressions produce a pipeline marked as **parallel**. Key differences:

| Criterion | `numbers.stream().parallel()` | `numbers.parallelStream()` |
| --- | --- | --- |
| Origin | `Collection.stream()` creates a sequential stream, then `BaseStream.parallel()` selects parallel mode | `Collection.parallelStream()` directly requests a stream that can run in parallel |
| API location | `parallel()` is a method on `BaseStream`, usable on `Stream`, `IntStream`, `LongStream`, `DoubleStream` | `parallelStream()` is a method on `Collection` |
| Applicable targets | Any existing compatible stream, including streams from arrays, `IntStream.range()`, `Stream.of()`, files, generators | Only collections that have `parallelStream()` |
| Runs tasks immediately when called? | **No** | **No** |
| Return value | A stream in parallel mode, which may be the current instance per contract | A stream from the collection; some implementations are permitted to return a sequential stream |
| Operation result | Determined by the same pipeline/source/terminal operation; parallel mode does not alter the logical result of valid operations | Same |

**Specification subtlety:** the `Collection.parallelStream()` documentation explicitly states *returns a possibly parallel Stream* and allows an implementation to return a sequential stream. Therefore, with a **custom collection**, you must not strictly assume that every call to `parallelStream()` makes `isParallel()` `true`. With `ArrayList`, `List.of(...)`, and typical standard collections, it is implemented to support parallel execution.

Meanwhile, `parallel()` is used to **request an execution mode change** on an existing stream. You can confirm the requested mode with `stream.isParallel()`, but that is **not a measurement of how many threads actually participated**, nor does it guarantee that the task will run faster.

## 3. Stream Pipelines Are Lazy: parallel Does Not Trigger Immediate Processing

A stream pipeline has three components:

1. **Source**: collection, array, `IntStream.range`, `Stream.of`, etc.
2. **Intermediate operations**: `filter`, `map`, `sorted`, `distinct`, `parallel`, `sequential`...
3. **Terminal operation**: `sum`, `count`, `reduce`, `collect`, `toList`, `forEach`, etc.

Intermediate operations are typically **lazy**: they are described up front and executed when the terminal operation begins. Calling `parallel()` does not immediately spawn a batch of threads, does not run `map`, and does not copy the entire collection.

~~~java
// Snippet inside a method.
var pipeline = List.of(1, 2, 3, 4)
        .stream()
        .parallel()
        .map(n -> n * n); // map does not run yet because there is no terminal operation.

List<Integer> squares = pipeline.toList(); // Execution starts.
System.out.println(squares);                // [1, 4, 9, 16]
~~~

For a stream with an **encounter order** like the list above, `toList()` preserves the original encounter order in the result; that does not mean every `map` call runs sequentially in that order.

Once a terminal operation consumes a stream, **do not reuse the same stream** for another terminal operation. Create a new stream from the source when you need to run the next computation.

## 4. Standalone Java 17+ Program

Save as **`ParallelStreamBasics.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelStreamBasics {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);

        Stream<Integer> sequential = numbers.stream();
        Stream<Integer> switched = numbers.stream().parallel();
        Stream<Integer> direct = numbers.parallelStream();

        System.out.println("stream(): " + sequential.isParallel());
        System.out.println("stream().parallel(): " + switched.isParallel());
        System.out.println("parallelStream(): " + direct.isParallel());

        int sum = numbers.parallelStream()
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("sum: " + sum);

        List<Integer> squares = numbers.stream()
                .parallel()
                .map(n -> n * n)
                .toList();
        System.out.println("squares: " + squares);

        int firstEven = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);
        System.out.println("first even: " + firstEven);

        boolean lastMode = IntStream.rangeClosed(1, 5)
                .parallel()
                .sequential()
                .isParallel();
        System.out.println("after sequential(): " + lastMode);
    }
}
~~~

Compile and run:

~~~bash
javac ParallelStreamBasics.java
java ParallelStreamBasics
~~~

Expected output on Java 17+ with standard `List.of`:

~~~text
stream(): false
stream().parallel(): true
parallelStream(): true
sum: 15
squares: [1, 4, 9, 16, 25]
first even: 2
after sequential(): false
~~~

These are the **deterministic** results of the computation and usage contract; execution thread counts/names are not printed because they depend on the scheduler and runtime. The program creates three streams to check `isParallel()` and then uses **new** streams for the subsequent terminal operations. `Stream.toList()` has been available since Java 16 and returns a list that cannot be modified through mutating methods.

## 5. Switching Execution Mode with parallel() and sequential()

`BaseStream.parallel()` and `BaseStream.sequential()` adjust the **mode of the pipeline**. When a pipeline calls them multiple times to switch modes, understand the effective mode at the terminal operation; the **last mode-selection call** determines whether the pipeline is requested to process sequentially or in parallel. Do not interpret it as each stage being able to run in an independent mode solely based on where `parallel()` appears in the chain.

~~~java
// Independent expressions; do not reuse a consumed stream.
boolean a = List.of(1, 2, 3).stream().parallel().isParallel(); // true
boolean b = List.of(1, 2, 3).parallelStream().sequential().isParallel(); // false
boolean c = List.of(1, 2, 3).stream()
        .parallel()
        .sequential()
        .parallel()
        .isParallel(); // true
~~~

A stream with `isParallel() == true` only indicates the **execution mode**: the JVM may use fewer tasks if the source is small or cannot be split, and some work may even run on the thread that calls the terminal operation. You **must not** treat it as a contract that "each element runs on its own thread" or "always runs across all cores".

`parallelStream()` only exists on collections. When the source is not a collection, use `parallel()`:

~~~java
long sum = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .asLongStream()
        .sum();
~~~

The snippet above is an illustration inside a method. `IntStream.rangeClosed(...)` provides an integer source that splits efficiently; `asLongStream()` before `sum()` avoids `int` overflow when summing one million numbers. The mathematical sum is **500000500000**.

## 6. How Is Parallelism Implemented?

For a parallel-capable pipeline, the Java Stream implementation typically:

- Uses the source's `Spliterator` to **split the data** into smaller chunks.
- Submits independent chunks of work to the fork/join scheduling mechanism.
- Executes those chunks across multiple threads when beneficial and resources are available.
- **Combines** intermediate results using `reduce`/`collect` or the terminal operation's rules.

~~~text
Source: [1, 2, 3, 4, 5, 6, 7, 8]
                 |
             split work
          /       |       \
       [1,2]    [3,4]   [5,6,7,8]
          \       |       /
         process independently
                 |
          combine / collect
                 |
               result
~~~

For example, when computing `sum()`: each branch can compute a partial sum and then combine them. This works well when the combining operation is **associative** and the state of each branch does not interfere with others.

**Note on the thread pool:** in modern OpenJDK, parallel streams typically use workers from **`ForkJoinPool.commonPool()`** and may also use the thread calling the terminal operation. However, the Streams API **provides no contract** regarding worker count, thread names, or a custom executor per pipeline. Do not design correctness around the assumption that "all actions always run on commonPool workers" or a fixed parallelism level. The common pool is a process-wide shared resource; multiple pipelines and fork/join tasks can affect each other.

You can observe this on your machine:

~~~java
// Illustrative snippet; order and set of thread names are NOT deterministic.
IntStream.range(0, 10)
        .parallel()
        .forEach(i ->
                System.out.println(i + " / " + Thread.currentThread().getName()));
~~~

Do not use `forEach` log order to prove a bug: in a parallel pipeline, the execution order of `forEach` is **non-deterministic**.

## 7. Encounter Order and Execution Order

This is the biggest source of confusion. **Encounter order** describes the logical order of elements according to the source/pipeline, not the order in which tasks are executed by the scheduler.

- `List` and `IntStream.range` typically **have an encounter order**.
- Some sources such as `HashSet` do not promise a deterministic encounter order.
- `parallel()` **does not remove** the source's encounter order.
- `unordered()` allows the pipeline to drop the encounter order constraint when business logic does not require it; **it does not mean calling `shuffle()`**.
- `forEach` on a parallel stream **does not guarantee processing order**.
- `forEachOrdered` preserves action order according to encounter order if the source defines one, but it can reduce parallelism in the terminal stage.
- `toList()`, `toArray()`, and `findFirst()` respect ordering semantics when the stream has an appropriate encounter order.
- `findAny()` is allowed to return **any** matching element, which is useful when the first element is not needed.

Example:

~~~java
List<Integer> data = List.of(5, 1, 4, 2, 3);

System.out.println(data.parallelStream().sorted().toList());
// [1, 2, 3, 4, 5]

System.out.println(data.parallelStream().filter(x -> x % 2 == 0)
        .findFirst().orElse(-1));
// 4: the first even number appearing in encounter order [5,1,4,2,3].

data.parallelStream().forEach(System.out::println);
// May print values in various orders.

data.parallelStream().forEachOrdered(System.out::println);
// Prints 5,1,4,2,3 on separate lines in exact encounter order.
~~~

These are snippets placed inside a method with `java.util.List` imported, not a deterministic stdout example for the entire block because the `forEach` lines vary.

**Cost of preserving order:** `limit(n)`, `skip(n)`, `takeWhile`, `dropWhile`, and `distinct` on ordered parallel streams can require significant coordination and buffering. When the problem allows any *n* elements rather than the *first n elements*, you can consider `unordered()` to reduce constraints, but **you must confirm that business logic accepts the change in result**.

## 8. Non-interference and Stateless Functions: Conditions for Safe Parallelism

Functions passed to `map`, `filter`, `reduce`, etc. should satisfy:

1. **Non-interfering:** do not modify the source while the pipeline is running (except for sources designed for concurrent modification under their own contract).
2. **Stateless:** the result for each element does not depend on state that may be modified by another thread during execution.
3. **Thread-safe if shared state exists:** if side effects are unavoidable, ensure synchronization yourself and accept the deterministic cost/limitations.

**Incorrect example** because multiple workers write to the same `ArrayList`:

~~~java
// DO NOT run as a data collection pattern.
List<Integer> shared = new ArrayList<>();
IntStream.range(0, 10_000).parallel().forEach(shared::add);
// Race condition: size/contents may be wrong, runtime errors may occur.
~~~

**Correct approach** using Stream-managed reduction:

~~~java
List<Integer> result = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
// No need to manually synchronize a shared ArrayList.
~~~

`toList()` returns a list that cannot be added to, removed from, or modified via mutating operations. If you need a mutable list after the pipeline finishes:

~~~java
List<Integer> mutable = new ArrayList<>(
        IntStream.range(0, 10_000).parallel().boxed().toList());
~~~

Both correct snippets are method excerpts requiring imports for `java.util.ArrayList`, `java.util.List`, and `java.util.stream.IntStream`.

**Modifying the source being streamed** is dangerous in both sequential and parallel modes:

~~~java
// Do not do this:
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
source.parallelStream().forEach(source::remove);
~~~

This violates the non-interference condition and can cause undefined behavior or an exception. Even when the collection structure is concurrent, you must still understand the exact semantics of its iterator/spliterator and business requirements.

### Side effects in peek/map may not run as you expect

The Stream implementation can elide certain stages if it can prove that the terminal operation result is unchanged. Therefore, **do not rely on `peek` as a mandatory step to write to a database, send a message, or increment a counter**. For example, with a known-size source, `count()` can compute the element count directly without invoking `peek`:

~~~java
long size = List.of(1, 2, 3)
        .parallelStream()
        .peek(x -> System.out.println("seen " + x))
        .count();
// size == 3; "seen" is not guaranteed to appear.
~~~

`forEach` is specified as a terminal side-effect operation, but on a parallel stream the action's execution order and thread are non-deterministic. For data transformation, prefer `map` + `collect`/`toList`.

## 9. Reduce: Combining Results Must Be Algebraically Sound

`reduce(identity, accumulator)` can only split/combine safely when:

- `identity` is the **identity element** of the combining operation.
- `accumulator` is **associative**: `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- The function has no side effects and does not access external mutable state.

Correct example:

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum); // 5050
~~~

`0` is the identity for addition; integer addition (with Java `int` semantics) is associative. `reduce` using subtraction is **semantically unsafe** because subtraction is not associative:

~~~java
// Do not use as a valid parallel reduction.
int unexpected = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, (left, right) -> left - right);
~~~

Depending on how it is split/combined, the result can differ from the expected sequential calculation. For `double`/`float`, addition performed under floating-point precision is **not strictly associative**, so a parallel sum can differ by a few bits due to rounding order; if stable or high-precision numerical results are required, design an appropriate method.

The `reduce(identity, accumulator, combiner)` form additionally requires compatibility between the accumulator and combiner. **Do not** pass a mutable object like `ArrayList` into `reduce` and mutate it across branches; use `collect`.

## 10. Collect: Safe Aggregation Without Sharing Mutable State

`collect` supports mutable reduction, creating intermediate containers for branches and merging them according to the collector's contract.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = List.of("java", "stream", "cpu", "parallel", "jdk");

Map<Integer, List<String>> grouped = words.parallelStream()
        .collect(Collectors.groupingBy(String::length));
// Map of word groups by length; do not rely on HashMap iteration order.
~~~

This snippet is an example placed inside a method, not a complete class. Standard `Collectors.groupingBy` is **not a concurrent collector**; the JDK can still collect in parallel safely by aggregating intermediate results and then merging them. Do not infer that every collector must be thread-safe to be used with a parallel stream.

When a concurrent map result is needed and semantics allow it, consider `Collectors.groupingByConcurrent` or `toConcurrentMap`. They have trade-offs regarding ordering and contention levels, and are not automatically faster than `groupingBy` on every workload.

A common case:

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(x -> x * x)
        .boxed()
        .toList();
// [1, 4, 9, 16, 25]; encounter order is preserved.
~~~

**Avoid confusion:** `Stream.toList()` returns an unmodifiable list; `Collectors.toList()` **makes no guarantees** about the list type, mutability, or thread-safety of the result. If you need a specific container type, use `Collectors.toCollection(ArrayList::new)` or copy explicitly after the pipeline.

## 11. When Is Parallelism Faster? Hidden Costs

A parallel stream pays off when conditions are favorable together:

- The dataset is **large enough** to offset the cost of splitting work and merging.
- Per-element processing is **CPU-bound, independent, and relatively heavy**.
- The source has a `Spliterator` that **splits evenly and easily**, such as an array, `ArrayList`, or `IntStream.range`.
- Low contention on shared locks, counters, caches, or memory allocators.
- Core count and resources allow parallel execution without competing workloads saturating the CPU.
- The terminal operation does not impose heavy ordering barriers.

Costs to account for include **task scheduling, splitting, merging, allocation, cache locality, memory bandwidth, synchronization, and contention**. With a list of a few dozen elements and `x * 2`, `parallelStream()` is usually slower than a loop or sequential stream because the overhead outweighs the benefit.

Example of choosing sequential for a small computation:

~~~java
List<Integer> tiny = List.of(1, 2, 3, 4);
int sum = tiny.stream().mapToInt(Integer::intValue).sum();
~~~

Parallel streams are **not built for I/O**: in modern JDKs, fork/join workers are typically a shared resource, so many tasks **blocking for long periods on HTTP, JDBC, files, sockets, or locks** can occupy workers and degrade the throughput of other pipelines. When you need to coordinate a large number of independent blocking tasks, look at dedicated concurrency mechanisms: `ExecutorService`, `CompletableFuture`, or since JDK 21 `Executors.newVirtualThreadPerTaskExecutor()`, along with I/O resource limiting policies. That is a different problem from parallel data processing.

**Do not use parallel streams as a default way to "speed up" a server.** Doing so can cause requests to contend more heavily for CPU even if single-request latency improves in an isolated benchmark.

### Amdahl's law

If a portion of the work must remain sequential, the maximum speedup is bounded. With parallelizable fraction `p` and `N` ideal workers:

~~~text
speedup <= 1 / ((1 - p) + p / N)
~~~

For example, with `p = 0.8` and `N = 4`, the ideal maximum speedup is `1 / (0.2 + 0.8/4) = 2.5`, **before subtracting scheduling, memory, and contention overhead**. The formula is a mental model, not an exact predictor of Java application throughput.

## 12. Source and Spliterator Determine Work Splitting

Parallel streams are backed by `Spliterator`. The ability of `trySplit()`, size estimation, and characteristics such as `SIZED`, `SUBSIZED`, `ORDERED`, and `CONCURRENT` affect how the runtime partitions work.

| Source | Tendency |
| --- | --- |
| `ArrayList`, array, `IntStream.range()` | Known size, usually splits well |
| `HashSet` | No guaranteed encounter order; splitting depends on the spliterator |
| `LinkedList` | Splitting capability and locality are usually less favorable than arrays |
| Infinite or unknown-size sources | Can be hard to split evenly; some pipelines require heavy barriers |
| I/O data from `Files.lines()` | Also incurs resource reading/closing costs and I/O limits, not automatically beneficial in parallel |

To be certain, run actual benchmarks with your application's data types, sizes, and runtime. Do not infer solely from `isParallel() == true` that the Spliterator created as many partitions as CPU cores.

If you use a stream wrapping a resource like `Files.lines(path)`, close it properly in both sequential and parallel modes:

~~~java
// Snippet inside a method that may throw IOException.
try (var lines = java.nio.file.Files.lines(path)) {
    long count = lines.parallel().filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
~~~

This is an example of resource management, **not a recommendation to always use parallel when reading files**. Ensure `path` exists and evaluate actual I/O reading costs.

## 13. Concurrency Issues to Understand Before Production Use

**Side effects and shared state.** Do not put counter increments, writes to a shared list, or mutations to a shared object inside `map/forEach` without a synchronization strategy. Even if you use `synchronized` to "fix" the race, lock overhead can wipe out the parallel benefit. Prefer pure pipelines and reductions.

**ThreadLocal and transaction context.** `map/filter/forEach` functions may run on different threads, with no guarantee that the calling thread's `ThreadLocal` will automatically propagate to workers. Do not rely on thread identity to pass request context or hold per-element resources.

**Exceptions.** An exception from an action can cause the terminal operation to fail; you cannot predict exactly which elements finished first or how many side effects occurred before the error propagated. Parallel streams have no rollback mechanism for side effects. If an action has external effects, design explicit idempotency and error handling.

**Cancellation/timeout.** The Stream API does not provide a per-`parallelStream()` deadline or cancellation token like an executor task. `limit`/`findAny` have short-circuit semantics, but they are not an instant cancellation mechanism for all already-running side effects. If you need hard deadlines, monitoring, and task cancellation, consider another orchestration model.

**Nested parallel streams.** When a parallel pipeline spawns multiple nested parallel pipelines, task scheduling/merging can consume heavy resources and become hard to predict; do not assume that nesting parallel levels multiplies performance gains.

**ForkJoin common pool.** You should not change the global parallelism property for the common pool just to optimize a single computation; doing so can affect many other tasks in the JVM. The Stream API has no standard executor parameter for `parallel()`.

## 14. How to Measure to Decide Between Parallel and Sequential

A benchmark must answer the right question: "Given the current source, operation, element count, and CPU load, does the parallel version improve **actual throughput/latency**?"

1. **Design two versions of the same computation**, one using `stream()`, one using `parallelStream()` or `stream().parallel()`, with the same input and semantics.
2. **Warm up the JIT** before measuring; the JVM can optimize code over multiple iterations.
3. **Use JMH** (Java Microbenchmark Harness) for serious microbenchmarks; ad-hoc measurements with `System.nanoTime()` a few times are easily skewed by JIT, GC, thread scheduling, and dead-code elimination.
4. **Verify results** of both versions match before comparing speed; pay special attention to ordering, floating-point numbers, and shared state.
5. **Measure across multiple data sizes and workloads**: lightweight ops, CPU-heavy ops, contention, I/O; find the crossover point where parallel starts paying off.
6. **Measure at the system level** if running in a server: throughput, p95/p99 latency, CPU, allocation/GC, and the impact when multiple requests invoke parallel streams concurrently.

A CPU computation expression typically suitable for benchmarking:

~~~java
// Pure computation function, no side effects, illustrating a CPU workload.
static long compute(long x) {
    long value = x;
    for (int i = 0; i < 200; i++) {
        value = value * 1664525L + 1013904223L;
    }
    return value;
}

static long calculateSequential(int size) {
    return java.util.stream.IntStream.range(0, size)
            .mapToLong(ParallelBenchmarkCandidate::compute)
            .sum();
}

static long calculateParallel(int size) {
    return java.util.stream.IntStream.range(0, size)
            .parallel()
            .mapToLong(ParallelBenchmarkCandidate::compute)
            .sum();
}
~~~

This is a **method excerpt in a class named `ParallelBenchmarkCandidate`**, not a complete JMH benchmark. Both versions compute the same result because `compute` is pure and addition on `long` is suitable for reduction. To evaluate real performance, place it in JMH, pass data from benchmark state, and ensure the result is consumed to avoid dead-code elimination optimizations. Do not attach an "x times faster" number without measuring.

## 15. Common Mistakes and How to Fix Them

| Error-prone practice | Why it is wrong/unsuitable | How to fix |
| --- | --- | --- |
| Assuming `parallelStream()` is always faster than `stream()` | Fork/join, merge, and contention overhead can exceed the benefit | Benchmark with real data |
| Assuming calling `parallel()` runs all elements immediately | Intermediate operations are lazy | Understand that the terminal operation triggers the pipeline |
| Using `forEach` to add data to a shared `ArrayList` | Data race, corrupted results | Use `collect`/`toList` or an appropriate reduction |
| Assuming `forEach` preserves order | Parallel `forEach` does not promise order | Use `forEachOrdered` when semantics require it, accepting the trade-off |
| Using subtraction in `reduce` | Not associative | Design an associative function with the right identity |
| Using `findAny` and expecting the first element | `findAny` does not preserve selection order | Use `findFirst` if you need the first element |
| Treating `unordered()` as random shuffling | It only drops the encounter order requirement | Use only when semantics accept an unordered result |
| Relying on the calling thread's `ThreadLocal` | Workers may be different threads | Pass context data as explicit parameters |
| Doing long blocking I/O in `parallelStream()` | Easily ties up shared workers, hard to control timeouts | Use concurrency APIs designed for I/O |
| Treating a task error as rolling back the whole pipeline | Already-executed side effects may not be undone | Avoid side effects or have an idempotency policy |
| Globally tuning the common pool for one pipeline | Affects other tasks | Consider appropriate orchestration design and measure |

## 16. Quick Selection Scenarios

**Scenario A — Aggregating millions of numbers with CPU-heavy, independent operations:** try `IntStream.range(...).parallel().mapToLong(...).sum()`, then benchmark against the sequential version. This is a good candidate because the source splits well, the transformation has no shared state, and the result uses reduction.

**Scenario B — Taking 30 elements from a list and doubling them:** `list.stream().map(x -> 2 * x).toList()` is usually simpler and has less overhead. Do not enable parallel just because you can write it.

**Scenario C — Calling an API for each element:** do not treat `parallelStream()` as an HTTP client concurrency manager with timeouts/rate limits. Use an asynchronous mechanism or executor and bound concurrency by resources.

**Scenario D — Must preserve result order:** `parallelStream().map(...).toList()` can return the exact encounter order while still computing in parallel. Consider the cost of maintaining order; `forEachOrdered` when side-effect order is needed, though it usually reduces parallel advantage.

**Scenario E — Result is a Map or grouped data:** prefer `collect(Collectors.groupingBy(...))` or an appropriate collector. Collection is handled per the collector's contract without creating a shared `HashMap` for all workers to mutate simultaneously.

## 17. Self-Check Questions

**1. How does `collection.parallelStream()` differ from `collection.stream().parallel()` in API location?**  
`parallelStream()` belongs to `Collection`; `parallel()` belongs to `BaseStream`, so it can enable parallel mode on streams produced from many kinds of sources. A custom collection is allowed to return a sequential stream from `parallelStream()`.

**2. Does `list.stream().map(...).parallel()` mean the `map` part runs sequentially and the rest runs in parallel?**  
No. Execution mode is a pipeline property; the stream implementation can apply the parallel configuration to processing the entire pipeline at the terminal operation.

**3. Why does `parallelStream().map(...).toList()` preserve list order while `parallelStream().forEach(...)` can print out of order?**  
`toList()` preserves the encounter order of an ordered source; `forEach` does not require respecting execution order.

**4. Does `isParallel() == true` guarantee multiple threads will be used?**  
No. It is the requested mode, not the number of workers that executed.

**5. If you need to find the first element matching a condition, use `findAny()` or `findFirst()`?**  
`findFirst()` if the source is ordered and the exact first element is required. `findAny()` if any matching result is acceptable.

**6. Why is `List<Integer> target = new ArrayList<>(); source.parallelStream().forEach(target::add)` dangerous?**  
Multiple threads can write to the shared `ArrayList` without synchronization. Use `collect`/`toList` instead of side effects.

**7. Why not always enable parallel on a multi-request server?**  
Pipelines can contend for CPU, fork/join workers, memory bandwidth, and downstream resources, worsening p95/p99 latency even if a single isolated request appears fast.

## 18. Official Documentation

- [Java SE 21 — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): pipeline, laziness, parallel operations, `forEach`, `forEachOrdered`, `reduce`, `collect`, `toList`.
- [Java SE 21 — BaseStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html): `parallel()`, `sequential()`, `isParallel()`, `unordered()`.
- [Java SE 21 — Collection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html): `stream()`, `parallelStream()`, and the "possibly parallel" note.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless, non-interfering, reductions, ordering, and performance.
- [Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html): data source splitting and characteristics.
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): Java microbenchmarking when performance measurement is needed.

**Key takeaway:** `stream().parallel()` and `parallelStream()` usually lead to the same parallel execution mode on standard collections. Correctness depends on pure pipelines, non-interference with the source, valid reductions, and ordering semantics; performance is only decided by measuring under realistic load.
