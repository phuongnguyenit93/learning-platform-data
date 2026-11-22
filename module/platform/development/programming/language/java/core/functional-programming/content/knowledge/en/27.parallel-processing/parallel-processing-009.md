# Cost of Splitting, Combining, Boxing, and Blocking I/O in Java Parallel Streams

`parallelStream()` and `stream().parallel()` allow Java Stream to **split data-processing work** so multiple tasks can execute concurrently. However, **parallel processing is not automatically faster than sequential processing**. For a small pipeline, a very light transformation, a hard-to-split source, an expensive combine step, heavy boxing/unboxing, or blocking I/O operations, the time and resource overhead of a parallel stream can exceed the work saved.

This lesson focuses on four cost categories:

1. **Splitting**: partitioning the source via `Spliterator`, creating sufficiently large and relatively balanced work chunks.
2. **Combining**: merging local results of `reduce`, `collect`, or stateful operations; the harder it is to merge, the easier it is to lose parallel gains.
3. **Boxing/unboxing**: converting back and forth between `int/long/double` and `Integer/Long/Double`, causing extra objects, memory accesses, and GC pressure in some pipelines.
4. **Blocking I/O (*blocking input/output*)**: waiting on files, network, databases, or external resources, causing tasks to spend time waiting rather than using CPU; can starve workers for other tasks when using the common pool.

**Principle:** Parallelism generally fits large amounts of **easily splittable** data, **CPU-bound**, independent processing, and efficient result combining. Examine the entire pipeline, source, terminal operation, and runtime environment before choosing `parallel()`.

Examples are designed for **Java 17 or later**. They illustrate behavior and correctness; do not infer speedup factors from examples with small data.

## 1. What does a parallel pipeline actually do?

A `Stream<T>` can be in sequential or parallel mode:

~~~java
// Illustrative snippet inside a method; data is List<Integer>.
long a = data.stream()
        .mapToLong(Integer::longValue)
        .sum();

long b = data.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

long c = data.stream()
        .parallel()
        .mapToLong(Integer::longValue)
        .sum();
~~~

All three expressions share the goal of computing a `long` sum; the difference is the pipeline's **execution mode**. `Collection.parallelStream()` creates a parallel stream from a collection; `stream().parallel()` marks the current pipeline as parallel. `sequential()` can switch the mode back to sequential.

Parallel stream is **not** "one thread per element" and does not guarantee thread count equals CPU core count. The JDK typically executes tasks using a fork/join mechanism, often using **`ForkJoinPool.commonPool()`** along with the calling thread depending on the situation. Task counts, re-splitting, and scheduling are runtime details, not a contract for business code to rely on.

Conceptual model:

~~~text
                          data source
                              │
                      Spliterator splits
                       ┌──────┴──────┐
                    part A         part B
                      │               │
                filter/map...   filter/map...
                      │               │
                   result A        result B
                       └──────┬──────┘
                           combiner
                              │
                        final result
~~~

Not every pipeline uses a single combine step. Operations like `forEach` can perform independent actions; `reduce` and `collect` can have multiple partial results to merge; `sorted` may need to store and organize significant amounts of data. **Cost belongs to the entire pipeline**, not just the `parallel()` call.

## 2. Cost model: when is parallelism worth it?

An approximate model for thinking, **not a runtime formula guaranteed by the JDK**:

~~~text
T_sequential ≈ T_work

T_parallel ≈ T_split + T_schedule
             + T_work_parallel
             + T_combine + T_sync
             + T_memory/boxing + T_other
~~~

Where:

- `T_split`: creating and splitting work into chunks small enough for parallel processing.
- `T_schedule`: creating/managing tasks, coordinating, and load balancing.
- `T_work_parallel`: useful processing work, shortened if distributed well across multiple cores.
- `T_combine`: merging local results.
- `T_sync`: waiting for coordination, maintaining order, locks, or contention if any.
- `T_memory/boxing`: object allocation, memory bandwidth, boxing, and garbage collection.
- `T_other`: I/O, cache misses, system load, and external costs.

If each element only adds a small integer, `T_work_parallel` is too small compared to the overhead; parallel may be **slower**. If each element performs heavy, independent computation and the source splits efficiently, useful work can be large enough to offset overhead.

Amdahl's law also shows that the non-parallelizable portion of work limits speedup. If the sequential fraction is `s` and the rest runs ideally on `p` workers, the approximate bound is:

~~~text
speedup ≤ 1 / (s + (1 - s) / p)
~~~

The formula assumes negligible overhead and balanced load; in practice it is often lower due to splitting/combining, memory, and synchronization. **Do not choose `parallel()` just because data has many elements**; you need both sufficient work *per element* and suitable splitting/combining characteristics.

## 3. Splitting cost: the role of `Spliterator`

`Spliterator<T>` is a Java interface for traversing and **splitting a source** into parts that can be processed separately. Key methods:

- `trySplit()`: attempts to split off a portion of data from the current part. Returns `null` if it cannot split suitably.
- `estimateSize()`: estimates the number of remaining elements in the current part.
- `characteristics()` and `hasCharacteristics(...)`: describes traits such as `SIZED`, `SUBSIZED`, `ORDERED`, `DISTINCT`, `SORTED`.

Sources like **arrays or `ArrayList`** typically can split into segments of known size, aiding load balancing. A source from an `Iterator` with unknown size or a linear I/O source can be harder to split, though that does not mean every such source cannot be parallelized.

Create file `SpliteratorSplitDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSplitDemo {
    public static void main(String[] args) {
        ArrayList<Integer> numbers = new ArrayList<>(
                List.of(1, 2, 3, 4, 5, 6, 7, 8));

        Spliterator<Integer> right = numbers.spliterator();
        boolean sized = right.hasCharacteristics(Spliterator.SIZED);
        boolean subsized = right.hasCharacteristics(Spliterator.SUBSIZED);
        Spliterator<Integer> left = right.trySplit();

        long totalEstimated = right.estimateSize()
                + (left == null ? 0 : left.estimateSize());

        System.out.println("sized=" + sized);
        System.out.println("subsized=" + subsized);
        System.out.println("split=" + (left != null));
        System.out.println("totalEstimated=" + totalEstimated);
    }
}
~~~

~~~bash
javac --release 17 SpliteratorSplitDemo.java
java SpliteratorSplitDemo
~~~

Result with `ArrayList` in Java 17:

~~~text
sized=true
subsized=true
split=true
totalEstimated=8
~~~

This result does **not** mean you should always split as small as possible. Parts that are too small create many tasks and coordination overhead; parts that are too large can leave workers idle while one worker still has heavy work. The scheduler and Spliterator try to balance both sides.

If data has skewed cost distribution (one element takes 1 ms, another takes 1 second), equal element counts per branch **do not necessarily** mean equal computation. Consider cost skew, locality, and work-stealing capabilities.

## 4. Not every source splits and replays well

Quick comparison:

| Source | Common traits when parallel | Risks to watch |
| --- | --- | --- |
| `int[]`, `long[]`, object arrays | Known size, easy to split by range | Overly fine-grained task allocation; memory bandwidth. |
| `ArrayList` | Indexed access, easy to split | Mutable objects modified during traversal. |
| `HashSet` | Splittable but unordered | No defined encounter order; locality and distribution. |
| `LinkedList` | No random access like arrays | Higher splitting/traversal and memory access costs. |
| One-shot `Iterator` | May lack size information | Hard to split efficiently; not automatically replayable. |
| `BufferedReader.lines()`, socket sources | I/O and stateful source | Often involves blocking waits; resource closing and concurrency limits. |

Do not infer performance solely from the data structure's name: you need to know the specific `Spliterator` implementation, size, and operation properties. `SIZED` and `SUBSIZED` help work-splitting algorithms, **but are not speed guarantees**.

With infinite streams or sources without a clear end, terminal operations needing the full result (such as `sorted().toList()`) may never terminate or may exhaust resources; `parallel()` does not change that nature.

## 5. Combining cost: `reduce()` and `collect()` are not free

Parallel work partitions typically produce **local results**. If the goal is just summing, merging two local sums is cheap; but if you must merge large lists, build a `Map`, sort, or maintain order, combining costs can be substantial.

Example:

~~~java
// Illustration: a new Stream<Integer> for each expression.
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

List<Integer> sorted = numbers.parallelStream()
        .sorted()
        .toList();
~~~

In the first expression, summing as `long` is associative with a relatively small merge state. In the second expression, `sorted()` must establish a global order; it is a *stateful* operation and may require extra memory and data movement/merging.

A custom collector typically has **supplier → accumulator → combiner → finisher**:

~~~text
supplier()            creates a new, neutral accumulation container A
accumulator(A,T)      folds each T into container A
combiner(A,A)         combines two A containers
finisher(A)           converts A into final result R
~~~

In parallel reduction, the combiner may be called to merge many containers. If it must repeatedly copy a large structure, the benefit of splitting work shrinks. Do not put shared mutable state in the supplier just to "save merging": that usually breaks correctness when running in parallel.

## 6. Runnable example: independent accumulators and cheap combining

Create file `ParallelSummaryDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class ParallelSummaryDemo {
    record Event(int score) {}
    record Report(long count, long total) {}

    static final class Acc {
        long count;
        long total;

        void add(Event event) {
            count++;
            total += event.score();
        }

        Acc merge(Acc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Report finish() {
            return new Report(count, total);
        }
    }

    static Collector<Event, Acc, Report> reportCollector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish);
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(2), new Event(3),
                new Event(5), new Event(7));

        Report serial = events.stream()
                .collect(reportCollector());
        Report parallel = events.parallelStream()
                .collect(reportCollector());

        System.out.println("serial=" + serial);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 ParallelSummaryDemo.java
java ParallelSummaryDemo
~~~

Result:

~~~text
serial=Report[count=4, total=17]
parallel=Report[count=4, total=17]
~~~

Here `Acc::new` creates a container with `count=0` and `total=0`; `Acc::add` updates locally; `Acc::merge` adds two containers. `long` sum and count are associative operations suited to the example data range. Record `Report` is the final result, without exposing the mutable accumulator.

The example **does not use `CONCURRENT`**. That does not prevent it from running in parallel: the framework can use independent containers and merge them afterward. If you mark it `CONCURRENT` yet let multiple tasks modify plain `long count` and `long total` simultaneously, data risks race conditions. Conversely, unconditionally using `AtomicLong` is not free either: contention can degrade performance.

**Do not treat the code above as a benchmark.** Four elements are far too few to conclude whether parallel is faster or slower; the goal is to demonstrate proper combiner design.

## 7. Which `Collector`s increase combining cost?

Look at the result structure to spot overhead sources:

- `summingInt`, `counting`, `summarizingInt`: small accumulation state and relatively simple combiner; usually fit reductions well.
- `toList()`, `toSet()`: may need to combine data from many containers; increases copy/memory cost and allocation pressure.
- `groupingBy()`: may create many intermediate Maps, then merge keys and downstream collections; merging large Maps can be expensive.
- `toMap()`: when keys collide, a merge function must be applied; expensive or side-effecting merge logic causes issues.
- `sorted()`, `distinct()`: are *stateful* intermediate operations that may require coordinated state across the entire pipeline.

`Collectors.groupingByConcurrent()` and `toConcurrentMap()` can help in suitable cases, but **are not faster by default**: concurrent maps, contention, key distribution, and ordering requirements have their own costs. On data with a few very "hot" keys, multiple tasks competing for the same buckets can wipe out parallel gains.

**Semantic note:** `reduce` and `collect` running in parallel require contract-compliant combining functions (especially associative, stateless, non-interfering). Do not use subtraction or logic depending on callback order as reduction operators because task grouping can change the result.

## 8. Boxing/unboxing: primitive to wrapper can be very expensive

An object stream like `Stream<Integer>` holds **references to `Integer`**; primitive streams like `IntStream`, `LongStream`, and `DoubleStream` process primitive values directly. For large numeric pipelines, boxing and unboxing add extra work:

~~~text
int                --boxing-->   Integer
Integer            --unboxing--> int

IntStream           .boxed()           → Stream<Integer>
Stream<Integer>     .mapToInt(...)      → IntStream
IntStream           .asLongStream()     → LongStream
Stream<T>           .mapToLong(...)     → LongStream
~~~

Distinguish **data type results** from **performance**: the JVM may optimize away some allocations/boxing in specific situations, so do not claim every element always causes exactly one allocation. However, generic `Stream<Integer>` requires data as objects and can add memory/GC pressure compared to a well-designed `IntStream` pipeline.

Less direct detour example:

~~~java
// Illustrating a long sum; not a snippet to use for benchmarking.
long total = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .boxed()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Here `boxed()` converts `IntStream` to `Stream<Integer>`, and then `mapToLong` unboxes back to primitive `long`. If `Integer` objects are not needed, stay primitive:

~~~java
long total = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .asLongStream()
        .sum();
~~~

Both computations yield the same mathematical result in the example, yet the primitive approach avoids boxing at the API design level.

## 9. Runnable example: two pipelines, same result, different types

Create file `BoxingCostDemo.java`:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class BoxingCostDemo {
    public static void main(String[] args) {
        long primitive = IntStream.rangeClosed(1, 100_000)
                .asLongStream()
                .sum();

        long boxed = IntStream.rangeClosed(1, 100_000)
                .boxed()
                .mapToLong(Integer::longValue)
                .sum();

        long parallel = LongStream.rangeClosed(1, 100_000)
                .parallel()
                .sum();

        System.out.println("primitive=" + primitive);
        System.out.println("boxed=" + boxed);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 BoxingCostDemo.java
java BoxingCostDemo
~~~

Result:

~~~text
primitive=5000050000
boxed=5000050000
parallel=5000050000
~~~

The sum `1 + 2 + ... + 100000 = 5000050000` **exceeds the `int` limit** but fits in `long`. Thus the pipelines above use `LongStream` or convert to `long` before summing. If replaced with `IntStream.rangeClosed(...).sum()`, an `int` sum can overflow and produce the wrong result.

Do not look at identical stdout and conclude performance is identical. To compare speed/GC, you need a real benchmark with warm-up, sufficiently large data, a stable environment, and dead-code elimination control; JMH is the right tool.

### When is `boxed()` still necessary?

Not every `boxed()` is a mistake. You may need `List<Integer>`, `Map<Integer,V>`, or a generic API accepting `Integer`:

~~~java
// IntStream -> Stream<Integer> -> List<Integer>.
List<Integer> numbers = java.util.stream.IntStream.range(0, 5)
        .boxed()
        .toList();
~~~

This is a **choice driven by the required output type**. Only avoid pointless `int → Integer → int` round-trips, especially inside heavy computation loops running many times.

## 10. Boxing and data structures affect memory, cache, and GC

When there are many `Integer` elements, beyond the numeric values there are also:

- Object references inside the `Stream<Integer>`/collection structure;
- Object representation overhead when new wrappers must be allocated;
- Indirect pointer chasing to object memory, hurting cache locality;
- Garbage collector activity and memory pressure if many objects are created.

With `int[]` or `IntStream`, primitive data is typically organized more compactly and contiguously, helping the CPU process sequentially efficiently. Actual results also depend on JIT, escape analysis, how collections store data, and data flow.

**Do not say `Integer.valueOf` always creates a new object.** Java caches wrappers for some values; the JVM can also optimize boxing. The accurate conclusion is that **APIs requiring boxing create potential overhead**, so design primitive pipelines where appropriate and **measure** before optimizing.

A `parallel().boxed().map(...)` pipeline can pay both parallel overhead and boxing overhead. If the actual per-element work is too light, the two cost categories stack and adding more cores will not help much.

## 11. Blocking I/O operations: waiting is not like computing

A **CPU-bound** task uses the CPU to compute. An **I/O-bound** task may spend most of its time **waiting** on external systems:

- Synchronous HTTP calls or blocking database queries.
- Slow reads from network/disk.
- Waiting on locks, semaphores, or limited resources.
- Calling external APIs with long timeouts.

Writing:

~~~java
// Pseudocode: fetchBlocking is a synchronous network/database call.
List<Result> results = ids.parallelStream()
        .map(id -> fetchBlocking(id))
        .toList();
~~~

does **not** mean network operations are well-managed just because the pipeline runs in parallel. Parallel streams typically tie to a fork/join mechanism using the common pool; when a worker is blocked on I/O, that worker does no useful CPU work while waiting. Many concurrent blocking calls can also:

- Occupy shared resources needed by other parallel streams or ForkJoin tasks.
- Cause queueing, reducing throughput for CPU tasks.
- Overload connection pools, API rate limits, quotas, or database backends.
- Trigger timeouts, retries, lock contention, and **tail latency** effects.
- Make it hard to control concurrency limits and task cancellation.

Fork/join has certain compensation mechanisms for blocking tasks, such as `ForkJoinPool.ManagedBlocker` when integrated properly, yet **do not assume** arbitrary I/O APIs automatically declare blocking so the pool compensates fully. Do not treat implementation details as a performance promise.

**A usually better approach:** bound concurrent I/O calls, manage timeouts/cancellation, and use an executor or asynchronous API designed for that kind of work.

## 12. Runnable example: bounding concurrency for waiting work

To illustrate coordinating blocking tasks, you can use an `ExecutorService` with a bounded thread pool. The example below uses `Thread.sleep` to **simulate I/O wait time**, not a real network-calling program.

Create file `BoundedBlockingDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedBlockingDemo {
    public static void main(String[] args) throws Exception {
        List<Callable<String>> tasks = List.of(
                () -> { Thread.sleep(20); return "A"; },
                () -> { Thread.sleep(20); return "B"; },
                () -> { Thread.sleep(20); return "C"; }
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<String>> results = pool.invokeAll(tasks);
            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac --release 17 BoundedBlockingDemo.java
java BoundedBlockingDemo
~~~

Result:

~~~text
A
B
C
~~~

With `newFixedThreadPool(2)`, at most **two tasks execute concurrently on that pool**, even though there are three tasks. `invokeAll` waits for tasks to complete; the `Future` list corresponds to **task submission order**, so stdout prints A, B, C regardless of which task finishes first. `shutdown()` requests releasing executor resources after use.

**This is not a complete production pattern.** Real network tasks need timeouts, cancellation/interruption strategies, queue monitoring, request limits, and error handling; `newFixedThreadPool` has an unbounded queue that can grow large if too much work is submitted. In high-load applications, designing bounded queues/backpressure and sizing pools based on upstream/downstream limits is essential.

Java also has asynchronous APIs such as `HttpClient.sendAsync`, `CompletableFuture`, and non-blocking I/O. Choosing a dedicated executor or an async API depends on operation type, libraries, concurrency limits, and error-handling contracts. **Do not use parallel streams as the default for all HTTP/JDBC queries.**

## 13. Ordered streams and order-preserving operations increase cost

When a source has **encounter order** (e.g., `List`, `IntStream.range`), some operations must preserve that order:

- `forEachOrdered` preserves encounter order when issuing actions, which can limit useful parallelism.
- `findFirst` respects first order on ordered streams; `findAny` can pick any element and usually allows more freedom.
- `limit(n)` and `skip(n)` on ordered parallel streams can incur coordination cost to select the exact positions.
- `takeWhile` on an ordered parallel stream must keep **the longest prefix** matching the predicate; it is not as simple as independent per-element filtering.
- `sorted` needs to establish global order; `distinct` may need coordination to deduplicate and preserve stability depending on stream traits.

Example `ParallelOrderDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<Integer> squares = IntStream.rangeClosed(1, 8)
                .parallel()
                .map(n -> n * n)
                .boxed()
                .toList();

        System.out.println(squares);
    }
}
~~~

~~~bash
javac --release 17 ParallelOrderDemo.java
java ParallelOrderDemo
~~~

Result:

~~~text
[1, 4, 9, 16, 25, 36, 49, 64]
~~~

`IntStream.rangeClosed` has encounter order; `Stream.toList()` preserves encounter order when present. **An ordered result does not mean each `map` lambda ran in that order**: evaluation can happen across different workers. Do not rely on mapper side effects to infer execution order.

With `parallel().forEach(System.out::println)`, line order can vary. If action order is mandatory, use `forEachOrdered` or collect results and process them in order, while accepting the coordination cost.

## 14. A pipeline can defeat its own parallel gains

Consider the pattern:

~~~java
// Illustration; data is an existing List<String>.
List<String> result = data.parallelStream()
        .filter(s -> !s.isBlank())
        .map(String::trim)
        .sorted()
        .distinct()
        .limit(100)
        .toList();
~~~

Each part has different costs:

1. `filter` and `map` can normally process each element independently, though here the operations are quite light.
2. `sorted` needs to know the order of the entire valid set.
3. `distinct` must detect duplicates, potentially maintaining global state.
4. `limit(100)` after `sorted` does not turn the preceding sort into only processing the first 100 source elements.
5. Collecting and emitting results in encounter order can add coordination and memory costs.

When data is small, a sequential pipeline can be faster and simpler. When data is large, measure and consider changing the algorithm (such as a structure maintaining top-k if business-valid), rather than just adding `parallel()`.

Setting `unordered()` can reduce some ordering constraints **when business logic genuinely does not need encounter order**. However, `unordered()` can change the meaning of `limit`, `findAny`, `takeWhile`, or first-element selections, so do not use it as an unconditional optimization trick.

## 15. Principles to avoid race conditions and wrong results

A parallel pipeline **must be semantically correct before discussing performance**:

- `map`, `filter`, and accumulators should be **stateless** and **non-interfering**, not modifying the source being traversed.
- Avoid updating shared `ArrayList`, `HashMap`, `int` variables, or non-thread-safe state directly from parallel `forEach`.
- Use `collect(Collectors.toList())`, `groupingBy`, or a properly designed collector instead of sharing a mutable `ArrayList`.
- Reducers/combiners need **associativity**; subtraction or logic depending on callback invocation counts can change results when splitting/merging changes.
- Even if using `ConcurrentHashMap`, `AtomicLong`, or locks, still evaluate contention; synchronization correctness **does not mean fast**.
- Do not attach `Collector.Characteristics.CONCURRENT` when the container and accumulator are not safe for concurrent updates.
- Do not rely on **how many times** the JDK calls supplier, accumulator, or combiner, or on which worker.

**Wrong** example:

~~~java
// Wrong: ArrayList is not safe for concurrent adds.
List<Integer> shared = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
~~~

The above must not be used to collect results. Lost elements or corrupted data structures can happen, even if a small run appears to work.

**Correct** example:

~~~java
List<Integer> values = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

The collector/terminal operation is responsible for collecting results using the Stream's proper mechanism. When `List<Integer>` is needed, boxing here is justified by **the required result type**; if only a numeric sum is needed, prefer primitive reductions.

## 16. Measuring performance: avoid flawed benchmarks

Do not conclude parallel stream effectiveness by running `System.nanoTime()` once and printing the result:

~~~java
// Simple measurement sketch, NOT a reliable benchmark:
long start = System.nanoTime();
// run task ...
long elapsed = System.nanoTime() - start;
~~~

Factors that skew measurements include:

- JIT compilation, warm-up, inlining, escape analysis.
- Different GC and heap pressure between boxed/object streams and primitive streams.
- CPU turbo/thermal throttling, memory bandwidth, actual core count, and background system tasks.
- Data size too small, hot/cold cache state.
- Results being optimized away if the computation is unused.
- Difference between throughput and single-request latency.
- Contention with `ForkJoinPool.commonPool()` used elsewhere in the application.
- I/O, network jitter, timeouts, and quotas when benchmarking live backends.

Use **JMH** for CPU microbenchmarks: with warm-up, multiple iterations, multiple forks when appropriate, result consumption, identical inputs, and timing distribution statistics. For systems with real I/O, beyond local function benchmarks, also measure end-to-end **p95/p99 latency, throughput, queuing, saturation, CPU, GC, connection counts, and timeouts**.

Benchmarks should compare at least:

~~~text
A. sequential, primitive, few stateful operations
B. parallel,   primitive, same algorithm and input
C. sequential, boxed,     if that is an option under consideration
D. parallel,   boxed,     if the pipeline actually involves boxing
~~~

There is no universal "element count threshold to always parallelize" for all applications. One million elements with a trivial operation and one thousand elements with a very CPU-heavy operation can lead to opposite decisions.

## 17. Decision table: sequential, parallel, or I/O executor?

| Situation | Default to consider | Reason |
| --- | --- | --- |
| A few hundred elements, light `map/filter` | Sequential `stream()` | Split/schedule/merge overhead easily outweighs gains. |
| Large array or `ArrayList`, heavy independent CPU transforms | Benchmark `parallel()` | Source splits easily, useful work is large enough. |
| Large `int/long/double` sums | `IntStream/LongStream/DoubleStream` | Avoids unnecessary boxing; cheap reducer. |
| `groupingBy` with many duplicate/hot keys | Measure collector and contention carefully | Map merging or concurrent updates can be very expensive. |
| `sorted`, `distinct`, `limit` preserving encounter order | Review full pipeline then benchmark | Order coordination and stateful ops have overhead. |
| Synchronous HTTP/JDBC/remote APIs, heavy waiting | Bounded I/O executor or async API | Better control over concurrency, timeouts, backpressure. |
| One-shot source from network/socket | Single-pass or suitable I/O pipeline | Calling parallel does not create splittability/replayability. |
| Strict side-effect ordering required | Sequential design or explicit coordination | `forEachOrdered` restricts execution freedom. |
| CPU and I/O mixed in the same pipeline | Separate stages if worthwhile | Each stage has different coordination and limits. |

A controllable design in real systems is **bounded data reading → parallelizable CPU processing → controlled aggregation and writing**, rather than running parallel while firing blocking network requests inside every `map`.

## 18. Common mistakes

1. **"Adding `parallel()` is always faster."** False: splitting, scheduling, combiners, and GC have overhead.
2. **"Each element gets its own thread."** False: the framework splits into tasks and reuses workers; task/thread counts are implementation details.
3. **"`ArrayList` and `Iterator` split the same way."** No: the `Spliterator` and source characteristics determine splitting efficiency.
4. **"Combiners take no time."** False: merging large Maps/Lists or contended state can be very expensive.
5. **"`Stream<Integer>` has the same cost as `IntStream`."** They have different data representations; object streams can incur boxing/unboxing and memory pressure.
6. **"`boxed()` must always be removed."** No: when output needs `List<Integer>` or generic APIs, boxing has a legitimate reason.
7. **"`IntStream.sum()` never overflows."** False: `int` sums can overflow; convert to `long` first if needed.
8. **"Blocking HTTP/JDBC inside `parallel().map` scales automatically."** Not guaranteed; common pool, connection pools, timeouts, and backends have limits.
9. **"Running parallel on a custom collector without a proper combiner is fine."** Can fail when merging accumulation containers.
10. **"Marking `CONCURRENT` always makes a collector faster."** False when the accumulator is not thread-safe or contention is high.
11. **"Using parallel `forEach` to add into a shared `ArrayList`."** Not thread-safe; use appropriate `collect`.
12. **"Parallel `forEach` preserves source order."** No; if side-effect order is needed, redesign or use `forEachOrdered`.
13. **"`sorted().limit(10)` only processes ten elements."** No; the preceding sort usually has to process a much larger range to find the smallest top items.
14. **"One stopwatch run determines the fastest algorithm."** False due to JIT, GC, environment, and system variance.
15. **"Increasing workers infinitely increases throughput."** No: CPU, memory bandwidth, I/O, connection pools, locks, and backends all have limits.

## 19. Checklist before enabling parallel stream

Check in order:

1. **How large** is the data and how much **actual CPU computation** does each element need?
2. Does the source have an **easily splittable `Spliterator`**? Does it have `SIZED/SUBSIZED` or reasonable splittability?
3. Is the cost distribution across elements **balanced**? Are there very slow tasks causing a long tail?
4. Can you **avoid boxing** with `IntStream/LongStream/DoubleStream` or `mapToInt/mapToLong`?
5. Do `reduce`/`collect` have a **cheap, associative, contract-compliant combiner**?
6. Are there **stateful/ordered** operations limiting concurrent execution?
7. Are there **blocking HTTP/JDBC/file I/O** calls inside mappers? Should they be moved to an I/O executor with a concurrency limit?
8. Do the source and accumulator avoid **shared mutable state**, race conditions, and side effects?
9. Are there risks of **overflow**, `double` precision errors, out-of-memory, or GC pressure?
10. Have you measured **sequential vs. parallel** on real data using an appropriate benchmark, observing both throughput and latency?

**Takeaway:** parallel stream performance is determined by **useful computation minus the costs of splitting, scheduling, combining, boxing, memory, and waiting**. Choose primitive streams for large numeric computations, design efficient combiners, and avoid putting uncontrolled blocking I/O onto the common fork/join pool. Prioritize **correctness and empirical measurement**, rather than assuming `parallel()` is a free optimization.