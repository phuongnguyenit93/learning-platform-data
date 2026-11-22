# ForkJoin common pool behind parallel streams in Java

## 1. Where do parallel streams execute?

`Stream.parallel()` and `Collection.parallelStream()` allow a pipeline to process elements in parallel. With current JDK Stream implementations, when a pipeline is invoked from a normal application thread, the parallel work is typically split into fork/join-style tasks and executed via **`ForkJoinPool.commonPool()`**. This is a shared pool within the Java process, not a new pool created separately for each stream.

Key distinctions to keep in mind:

- **The Stream API** specifies the operations, ordering rules, associativity, side effects, and results. The API **does not promise** to use a specific pool or a fixed number of threads.
- **ForkJoinPool** is an execution mechanism for workloads composed of many small tasks. `commonPool()` provides a shared pool for Java components to use when appropriate.
- Parallel task execution can also use the **thread calling the terminal operation** alongside pool workers. `parallel()` must not be understood as "all work is necessarily offloaded to other worker threads".
- `parallel()` is an execution mode hint on the stream; it **does not guarantee faster execution** than sequential, and it does not automatically make data or side effects thread-safe.

This lesson focuses on standard Java concurrency, independent of any framework.

### Expected outcomes

After this lesson, you will be able to explain how data is split into tasks, the role of work-stealing in the common pool, the difference between parallelism and actual thread count, the impact of the `Spliterator` source, how to write safe pipelines, how to diagnose resource contention, and when not to use parallel streams.

## 2. Lifecycle from pipeline to fork/join tasks

An expression such as:

~~~java
long result = java.util.stream.LongStream.rangeClosed(1, 1_000_000)
    .parallel()
    .filter(n -> (n & 1L) == 0L)
    .map(n -> n * 2)
    .sum();
~~~

has the following logical steps:

1. `rangeClosed` creates a source capable of splitting the numeric range into segments.
2. `parallel()` marks the parallel execution mode; at this point most operations are still **lazy**, and the full pipeline has not executed yet.
3. `filter` and `map` describe the intermediate operations.
4. `sum()` is the terminal operation, triggering traversal, work splitting, and combining of partial results.
5. Independent chunks of work can be processed across multiple threads; addition combines the final result.

This can be visualized as:

~~~text
A Stream source
       |
       v
Spliterator: splits the source into parts
       |
       +---------+---------+---------+
       |         |         |         |
    task A     task B     task C    task D
       |         |         |         |
    worker X  worker Y  caller/   worker Z
                       worker
       +---------+---------+---------+
                 |
                 v
          combine results
                 |
                 v
           terminal result
~~~

The diagram illustrates the concept and does not dictate a fixed number of tasks or workers. A pipeline may split into more tasks than there are workers; chunk sizes and combining behavior depend on the implementation, data source, operations, and parallelism level.

If a stream is already in parallel mode, calling `sequential()` can switch the pipeline to sequential execution; similarly, `parallel()` on a sequential stream switches it to parallel mode. A stream can only be consumed once; changing modes does not turn the same stream into two independent pipelines that can be re-run.

## 3. ForkJoinPool.commonPool() and work-stealing

`ForkJoinPool` is designed for workloads that can be divided into smaller pieces and combined. Workers typically have their own task queues. When a worker runs out of work, it can **steal** tasks from another worker's queue to balance load. This mechanism is useful when work is split into many independent, relatively short, CPU-bound pieces.

Key concepts:

| Concept | Meaning |
| --- | --- |
| `ForkJoinPool.commonPool()` | Singleton pool shared within a JVM for components that use it |
| `ForkJoinPool.getCommonPoolParallelism()` | Configured/reported parallelism level for the common pool; not the exact number of threads currently processing a stream |
| `ForkJoinPool.commonPool().getPoolSize()` | Number of workers currently existing at the time of sampling, not counting every thread calling a stream |
| `ForkJoinPool.commonPool().getActiveThreadCount()` | Estimate of workers actively executing at a given moment |
| Work-stealing | An idle worker takes runnable work from another worker |
| Fork/join task | Unit of work that can be split and whose results can be combined |
| Caller participation | The thread calling the terminal operation may itself process part of the work |

**The common pool is a shared resource.** Different parallel streams or other Java components using the common pool can compete for workers and CPU. For example, `CompletableFuture.supplyAsync(...)` and `runAsync(...)` overloads without an explicit executor typically use the common pool under normal configuration; there are implementation exceptions when common-pool parallelism does not meet certain conditions. Therefore, contention with them must also be considered within the same application.

`ForkJoinPool.commonPool().shutdown()` is not the way to manage the pool lifecycle of a parallel stream: the common pool is a shared runtime resource; ordinary shutdown calls do not stop the common pool like a user-created executor. You do not need to, and should not, shut down the common pool after each stream.

A parallel stream may wait inside the terminal operation until a result is available; calling `parallel()` **does not** turn a terminal operation into an API that returns a `Future` or `CompletionStage`. If a thread calls `sum()`, `collect()`, or `forEach()`, that call only returns when the terminal operation completes normally or throws an error.

## 4. Parallelism and common pool size configuration

In many common JDK configurations, the default parallelism of the common pool is derived from the number of processors visible to the JVM, typically close to `availableProcessors() - 1`, subject to a minimum level and specific rules/configurations. The JVM may see a CPU count constrained by a container or runtime policy. **Do not write logic that depends on a fixed default number of workers.**

Inspecting information at runtime:

~~~java
import java.util.concurrent.ForkJoinPool;

int cpuCount = Runtime.getRuntime().availableProcessors();
int commonParallelism = ForkJoinPool.getCommonPoolParallelism();

System.out.println("CPU JVM nhìn thấy: " + cpuCount);
System.out.println("Common parallelism: " + commonParallelism);
~~~

This snippet is an illustration placed inside a method or class with appropriate imports; the two printed numbers vary by machine/JVM. To adjust the common pool configuration, you can use a system property at JVM startup:

~~~bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 ParallelCommonPoolDemo
~~~

The syntax above passes the configuration to a **new JVM**; the example program in section 5 does not assume that this setting produces exactly four active workers at all times. You should set the property before the common pool is initialized (passed via `-D` at launch), rather than calling `System.setProperty(...)` late and expecting the pool to resize. The appropriate value depends on load, CPU, and other tasks sharing the pool.

In particular:

- **Parallelism does not equal throughput.** For example, parallelism = 4 does not guarantee four operations always run simultaneously, due to scheduling, caller participation, tasks being too small, or having too few branches to split.
- **It does not equal the total JVM thread count.** There are application threads, GC threads, I/O threads, other executors, and caller threads.
- **Metric values are point-in-time snapshots.** `getPoolSize()`, `getActiveThreadCount()`, and `getStealCount()` only aid observation; they do not prove which worker executed a specific task.

Do not set `common.parallelism` arbitrarily high to "speed things up": CPU-heavy tasks can contend on the same cores; blocking I/O can leave workers waiting idly; multiple concurrent parallel streams can put pressure on the pool together.

## 5. Runnable Java 17 example and deterministic output

Create `ParallelCommonPoolDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

public class ParallelCommonPoolDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 1000)
            .sum();

        int parallelSum = IntStream.rangeClosed(1, 1000)
            .parallel()
            .sum();

        List<Integer> doubled = IntStream.rangeClosed(1, 8)
            .parallel()
            .map(n -> n * 2)
            .boxed()
            .toList();

        long evenCount = IntStream.rangeClosed(1, 1000)
            .parallel()
            .filter(n -> n % 2 == 0)
            .count();

        System.out.println("sequential=" + sequentialSum);
        System.out.println("parallel=" + parallelSum);
        System.out.println("doubled=" + doubled);
        System.out.println("evenCount=" + evenCount);
        System.out.println(
            "sameCommonPool=" +
            (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac -encoding UTF-8 ParallelCommonPoolDemo.java
java ParallelCommonPoolDemo
~~~

Deterministic stdout:

~~~text
sequential=500500
parallel=500500
doubled=[2, 4, 6, 8, 10, 12, 14, 16]
evenCount=500
sameCommonPool=true
~~~

Explanation:

- `rangeClosed(1, 1000)` has sum `1000 × 1001 / 2 = 500500`. `sum()` is an appropriate combining operation for the chunks; there is no `int` overflow here.
- `IntStream.rangeClosed` provides a source with a deterministic encounter order. `map` preserves logical order. `Stream.toList()` on an ordered stream returns a list in encounter order even if element processing happens out of order.
- `evenCount` only counts elements matching the predicate; actual processing order does not affect the result.
- `ForkJoinPool.commonPool()` returns the same shared pool. The last line illustrates pool object identity, **not** a proof that every pipeline is required to use the common pool by the Stream API contract.

This is a demonstration of **result correctness**, not a speed benchmark. For 1,000 integers, the splitting overhead can exceed any parallel speedup.

## 6. Executing threads and scheduling non-determinism

If you add a statement to print thread names:

~~~java
// Illustration, placed inside main() or a Java method.
java.util.stream.IntStream.range(0, 12)
    .parallel()
    .forEach(n ->
        System.out.println(
            n + " -> " + Thread.currentThread().getName()));
~~~

you may see names like `main` and `ForkJoinPool.commonPool-worker-N` on a typical run. However:

- The print order is not fixed.
- There is no guarantee that worker threads will appear on every run, or that exactly N workers will appear.
- `System.out.println` uses internal synchronization, altering contention; this observation does not accurately reflect the performance of a pure CPU pipeline.
- Thread names are diagnostic details, not a business contract.

Avoid asserting on thread order or thread names in parallel stream tests. Tests should assert on **results**, encounter order when the operation preserves order, and pipeline invariants.

One subtlety: invoking a parallel stream **inside an application-created `ForkJoinPool`** can cause execution on workers of the calling pool in current JDKs. This behavior is an implementation detail; the Stream API does not provide a "my executor" parameter. Do not treat `customPool.submit(() -> stream.parallel()...)` as a resource isolation mechanism with a stable contract. If you strictly need control over the executor, scheduling, and resource boundaries, explicitly design `Callable`/`CompletableFuture` tasks with an executor, or specific fork/join tasks.

## 7. Spliterator determines how data is split

Parallelism is useful when the source can be split into sufficiently large chunks at low cost. Streams typically rely on `Spliterator` for traversal and splitting work via `trySplit()`.

Common characteristics:

| Characteristic | Typical effect |
| --- | --- |
| `SIZED` | Accurate estimated size is known for the source/described part |
| `SUBSIZED` | Child spliterators after splitting also have accurate sizes |
| `ORDERED` | Has an encounter order; some terminal operations must preserve this order |
| `DISTINCT` | Elements are already distinct according to source semantics |
| `SORTED` | Data follows a defined order, which can help optimize certain operations |

Sources such as arrays, `ArrayList`, and `IntStream.range(...)` typically split well. Sources backed by an iterator, stateful generators, or inherently sequential data can be hard to split and cause high parallel overhead.

Example:

~~~java
int[] numbers = java.util.stream.IntStream
    .range(0, 1_000_000).toArray();

long total = java.util.Arrays.stream(numbers)
    .parallel()
    .asLongStream()
    .sum();
~~~

The snippet above is an illustration without a separate `main` class. Arrays and numeric ranges have clean partitioning, making them more suitable for testing parallel computation benefits. Still, even an easily splittable source does not guarantee speedup if the per-element work is too trivial.

### Stateful and ordered operations can limit scalability

Operations such as `sorted()`, `distinct()`, `limit()`, or `skip()` on ordered sources sometimes require coordination or buffering, depending on pipeline characteristics. `findFirst()` must respect encounter order; `findAny()` can accept any matching element. `forEachOrdered()` respects encounter order and can reduce parallel benefit compared to `forEach()` if the application does not need ordering.

If business logic allows an unordered result, `unordered()` or order-independent terminal operations can open up optimization opportunities. Only drop ordering constraints when order truly **does not matter**; do not replace `findFirst()` with `findAny()` if the logic requires the first element.

## 8. Stateless, non-interfering, and associative reductions

For parallel streams to produce correct results, functions in the pipeline generally must be **stateless** (not depending on mutable state between elements) and **non-interfering** (not modifying the source being traversed), except where the API explicitly specifies otherwise. A common mistake:

~~~java
// Wrong: ArrayList is not safe for multiple threads adding concurrently.
java.util.List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 10_000)
    .parallel()
    .forEach(output::add);
~~~

This is an anti-pattern example, not code to run in an application. Multiple threads can mutate the same `ArrayList`, causing data races, missing elements, or other errors. Even if replaced with `Collections.synchronizedList(...)`, the code still suffers from contention and relies on side effects.

The proper Stream API approach:

~~~java
java.util.List<Integer> output =
    java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

The stream framework manages collecting partial results and constructing the list. `toList()` returns a list that **cannot be modified via List mutator methods**, and preserves encounter order if the source is ordered.

Similarly, avoid shared accumulator variables:

~~~java
// Wrong: += on a shared array is not atomic.
long[] total = {0};
java.util.stream.LongStream.range(1, 10_001)
    .parallel()
    .forEach(n -> total[0] += n);
~~~

Replace with:

~~~java
long total = java.util.stream.LongStream.range(1, 10_001)
    .parallel()
    .sum();
~~~

In general reductions, the operation needs an appropriate **identity** and must be **associative** so that grouping/recombining does not change the meaning:

~~~java
int sum = java.util.stream.IntStream.rangeClosed(1, 100)
    .parallel()
    .reduce(0, Integer::sum);
~~~

`0` is the identity for addition, and integer addition (under Java arithmetic rules) is associative. Subtraction is not associative: `reduce(0, (a,b) -> a - b)` can yield different results when split and recombined. For floating-point numbers, addition can differ due to rounding order; do not expect bit-for-bit identical results between parallel and sequential unless the algorithm accounts for it.

With `collect(supplier, accumulator, combiner)` or `Collector`, each accumulator container and the combiner must satisfy the contract. Do not supply a single shared mutable container across all partitions and mutate it concurrently. `Collectors.groupingByConcurrent(...)` can support concurrent collection, but that does not mean it is always faster than `groupingBy(...)`; choose based on ordering requirements, contention, and grouping cost.

## 9. Why is the common pool easily saturated by blocking I/O?

Fork/join is generally suited for **CPU-bound, short, splittable, and combinable** work. Consider:

~~~java
// Anti-pattern illustration, assuming urls and fetchBlocking() exist.
urls.parallelStream()
    .map(url -> fetchBlocking(url))
    .toList();
~~~

If `fetchBlocking` waits on network/DB/file, workers can spend most of their time **waiting on I/O** instead of computing. Other parallel streams and work using the common pool may have to compete with blocked workers. ForkJoinPool's ability to compensate with extra threads when tasks block is limited, and you cannot assume all ordinary I/O waits are automatically detected or compensated by the runtime.

If the problem is primarily I/O-bound:

- Use an `ExecutorService` with explicit concurrency limits, or an asynchronous API designed for I/O.
- Separate data fetching from CPU processing; you can use a parallel stream for the **CPU step** once the data is available.
- If the operation must call a blocking library, control concurrent requests, timeouts, and downstream pressure rather than simply increasing common parallelism.

`ForkJoinPool.ManagedBlocker` exists for certain fork/join scenarios where blocking is anticipated; placing an arbitrary I/O call inside `map` does not mean `managedBlock` is being used.

### Cross-impact example

Suppose two components run concurrently:

1. A parallel stream processes millions of elements and consumes nearly all available CPU.
2. Another task calls `CompletableFuture.supplyAsync(...)` without passing an executor, so under normal configuration it needs a worker from the common pool.

Both can increase each other's latency. When a system has clear latency/throughput requirements, you should not evaluate the processing time of a single pipeline in isolation; observe overall load and design appropriate executor ownership.

## 10. Exceptions, cancellation, and waiting for results

When a function in `map` or `filter` throws an exception, the terminal operation can terminate abnormally and the exception is propagated to the calling thread, sometimes wrapped depending on the execution path. Do not assume tasks for other partitions are interrupted immediately at the exact moment one partition fails. Tasks that have already started may still finish their in-progress work.

~~~java
// Illustration: terminal operation may throw an exception.
long total = java.util.stream.LongStream.range(0, 100)
    .parallel()
    .map(n -> {
        if (n == 42) {
            throw new IllegalArgumentException("invalid item");
        }
        return n;
    })
    .sum();
~~~

Use `try/catch` at the terminal operation call boundary and let the higher-level framework/executor manage error policy if the pipeline is part of a larger system.

A parallel stream does not directly provide a `Future`-style `cancel()`. Short-circuiting operations such as `anyMatch`, `findAny`, and `limit` can skip remaining work once the condition is met, but there is no guarantee that every running lambda is stopped immediately. Do not rely on pipeline side effects to determine the exact elements visited when a short-circuiting operation finishes.

If a parallel stream is placed inside a `CompletableFuture`:

~~~java
// Illustration snippet placed inside a method; data source already exists.
java.util.concurrent.CompletableFuture<Long> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> java.util.stream.LongStream.rangeClosed(1, 1_000_000)
            .parallel()
            .sum());
~~~

cancelling `result` does not mean all running fork/join subtasks of the computation are reliably cancelled. Choosing a separate executor for the outer stage also does not turn the Stream API into a pipeline with guaranteed subtask cancellation. For workflows requiring deadlines, backpressure, or fine-grained cancellation control, use an abstraction with explicit ownership and cancellation.

## 11. Measurement: when is a parallel stream actually faster?

Total time can be broken down as:

~~~text
Total parallel time
  = setup/splitting overhead
  + time to process parts
  + scheduling/work-stealing overhead
  + combining/order-preservation overhead
  + contention/waiting time
~~~

Parallelism pays off when per-element computation is heavy enough, the source splits well, the dataset is large enough, reductions are safe, and the machine has available CPU. Conversely, pipelines with trivial operations over a few dozen elements usually incur extra overhead; order-dependent pipelines also struggle to scale.

Verification approach:

1. Measure **sequential and parallel** with the same data and logic; verify result correctness before comparing performance.
2. Use a benchmark harness like **JMH** when reliable numbers are needed: JIT warm-up, multiple measurement iterations, JVM forks, avoiding dead-code elimination, and controlling allocation/GC.
3. Also run under **concurrent system load**, because the common pool is shared; a benchmark in an idle JVM can miss important contention.
4. Monitor CPU usage, allocation, GC, throughput, latency, and `ForkJoinPool` metrics; pool metrics are indicators, not a substitute for profiling.
5. If performance is critical, experiment with dataset sizes, `Spliterator` types, startup-configured parallelism levels, and concurrent process counts.

Do not rely solely on `System.nanoTime()` around a single run and conclude "parallel is x times faster"; first-run JIT, caches, GC, and scheduling cause results to fluctuate.

## 12. Decision table and common pitfalls

| Situation | Recommended action |
| --- | --- |
| CPU-heavy computation over large array/range, stateless operations | Try `parallel()` and benchmark |
| A few elements, very lightweight logic | Prefer simple sequential execution |
| Many blocking network/DB calls | Use bounded I/O/executor mechanisms and measure load |
| Need to preserve exact element order in output | Use order-preserving terminals like `toList()` or `forEachOrdered()` when needed |
| Want to write into a shared `ArrayList` from `forEach` | Replace with `collect`/`toList` or a contract-compliant reduction |
| Want to specify a parallel stream's pool via official API | Stream API has no executor parameter; consider an application-managed task/executor model |
| Seeing `ForkJoinPool.commonPool-worker-*` in thread dumps | Indicates the pool is working; not sufficient to infer every stream uses the same threads |
| Want to shut down the pool after `parallelStream()` | Do not `shutdown()` the common pool; it belongs to the runtime |
| Need to "immediately stop all tasks" when one element fails | Do not assume short-circuiting/exceptions provide full cancellation |
| Stream produces inconsistent wrong results | Check for shared mutation, stateful lambdas, non-associative reduce, and encounter order |

The most common mistakes are treating `parallel()` as a guaranteed speedup button; assuming each stream has its own pool; counting thread names to infer a contract; mutating a shared collection from `forEach`; putting blocking I/O into the common pool; and expecting physical execution order when Java only guarantees result order on operations with the appropriate contract.

## 13. Key takeaways for practice

**Parallel streams** describe how a pipeline can be processed in parallel; the **ForkJoin common pool** is the shared execution mechanism typically used behind the scenes by JDK implementations. Work-stealing helps distribute tasks, but effectiveness also depends on the `Spliterator`, operation independence, combining cost, CPU load, and contention with other work.

Write pure lambdas, use contract-compliant reductions/collectors, avoid shared mutable variables and blocking I/O, and validate with realistic benchmarks. When you need precise control over thread pools, deadlines, cancellation, and latency isolation across workloads, move scheduling into an explicit executor/task API rather than relying on the internal details of parallel streams.
