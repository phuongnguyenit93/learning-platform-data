# Common ForkJoinPool, Blocking Tasks, and Executor Control Limits

> **Chapter:** Parallel Processing Semantics  
> **Module:** `JAVA_STREAM_API` — learning declarative data processing with the Java Stream API via lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing limits on state, resources, and performance.

When adding `.parallel()` or calling `parallelStream()`, a program can use multiple threads to process a data source. However, **"running in parallel" does not mean "having a dedicated thread pool for this job,"** nor does it guarantee faster execution. In particular, if each element makes HTTP calls, database queries, waits on locks, or performs blocking I/O, using a shared pool can slow down other tasks in the application.

This lesson helps you understand the role of `ForkJoinPool.commonPool()`, how blocking tasks affect progress, the limits of controlling executors through the Stream API, and how to choose a different execution model when concurrency limits, timeouts, or resource isolation are needed.

After studying this lesson, you will be able to:

1. Distinguish the **Java Stream API contract** from **common implementation details** of parallel streams.
2. Recognize why `ForkJoinPool` fits splittable CPU-bound computation, yet is not a good default for blocking I/O.
3. Understand what `ManagedBlocker` solves for waiting, while not replacing load control.
4. Use `CompletableFuture` with an **explicitly** passed `ExecutorService` when controlling the number of concurrent I/O tasks; distinguish this from `ForkJoinTask` using a dedicated pool for CPU tasks.

## 1. What does `parallelStream()` do and not do?

In Java, both of the following request a pipeline in **parallel mode**:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

Stream<Integer> a = numbers.parallelStream();
Stream<Integer> b = numbers.stream().parallel();

System.out.println(a.isParallel()); // true
System.out.println(b.isParallel()); // true
```

`parallel()` is an **intermediate operation** configuring the pipeline's execution mode, without immediately running work. Traversal happens when calling a **terminal operation** such as `sum`, `reduce`, `collect`, or `forEach`. Parts of the pipeline may be split across multiple tasks; actual splitting depends on the source, `Spliterator`, operations, and environment.

Parallel does not mean:

- Each element is assigned to a dedicated thread.
- Thread count always equals CPU core count, or can be specified directly via `.parallel(4)` — **there is no such overload**.
- Every element is processed in source appearance order.
- A source with few elements will be split evenly.
- Blocking operations automatically have concurrency limits or timeouts.
- The pipeline has an executor isolated from other tasks.

**Important:** The Java Stream API only specifies computation semantics and constraints such as *non-interference* and *statelessness* for many lambdas. It **has no standard method to pass an `Executor` or `ForkJoinPool` per parallel pipeline**.

## 2. `ForkJoinPool.commonPool()` and work-stealing

`ForkJoinPool` is an `ExecutorService` designed for tasks that can **split into smaller subtasks** and then **combine results**. Workers can pull tasks from each other's queues (*work-stealing*) to balance load.

```text
               Problem to compute
                       │
                  split source
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Task A     Task B     Task C
             │         │         │
             └────── combine ────┘
                       │
                    result
```

In **common OpenJDK implementations**, a parallel stream invoked from a normal context typically uses `ForkJoinPool.commonPool()` — a JVM-wide shared pool. The thread calling the terminal operation may also participate in processing. These are **descriptions of implementation behavior**, not a contract allowing a program to attach a custom executor to the Stream API.

You can observe the configuration and thread names in a run:

```java
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

System.out.println("Common pool parallelism: "
        + ForkJoinPool.getCommonPoolParallelism());

List<String> seenThreads = IntStream.range(0, 20)
        .parallel()
        .mapToObj(i -> Thread.currentThread().getName())
        .distinct()
        .sorted()
        .toList();

System.out.println(seenThreads);
```

Output regarding thread names is **not fixed**: you may see `main`, threads named like `ForkJoinPool.commonPool-worker-...`, or fewer threads than the configured parallelism. One run does not reveal permanent bounds on thread count or throughput. `getCommonPoolParallelism()` reflects the configured target parallelism for the common pool, **not** a promise of how many threads actually run in a given pipeline.

### Why is it called "common"?

A single common pool can be used by **many components in the same JVM**, such as other parallel streams, Fork/Join tasks submitted by the application or libraries to the common pool, and `CompletableFuture.supplyAsync(...)` calls without an explicit executor in typical configurations.

```text
    Module A: parallelStream() ───┐
                                  ├──► commonPool() ──► shared workers
    Module B: parallelStream() ───┤
                                  │
    Default async work ───────────┘
```

`CompletableFuture` has its own implementation rules: async methods without an executor usually use the common pool if it supports parallelism greater than one; in environments with low parallelism, it may use an alternative execution strategy. Do not assume **every** async operation or **every** parallel stream necessarily uses these exact threads across all JDKs and configurations.

The practical consequence is resource contention: one module feeding slow work into the shared pool can degrade capacity for other modules. This is a form of **noisy neighbor** interference within the same process.

## 3. What kind of work fits `ForkJoinPool`?

It usually fits **CPU-bound**, non-blocking work whose cost is large enough to offset splitting and merging overhead:

```java
import java.util.stream.LongStream;

long sum = LongStream.rangeClosed(1, 1_000_000)
        .parallel()
        .sum();

System.out.println(sum); // 500000500000
```

This example demonstrates correctness of summing over a finite source within `long` range; it **does not** prove the parallel version is faster than the sequential version. For simple addition, parallel overhead can even dominate runtime.

An easily splittable source such as numeric ranges, arrays, or structures with a good `Spliterator` has a much better chance of distributing work effectively than a hard-to-split sequential I/O source. `SIZED`, `SUBSIZED`, and `Spliterator`'s `trySplit()` help the implementation plan execution, yet do not guarantee speedup.

| Task | Characteristics | Initial recommendation |
| --- | --- | --- |
| Arithmetic over large arrays | CPU-bound, non-blocking, easy to split | Can try parallel stream and measure performance. |
| Independent per-element transforms with substantial CPU cost | Stateless, little I/O | Worth considering parallelism. |
| HTTP/JDBC calls per element | Network or DB waits, variable latency | Use an explicitly bounded executor with timeout/backpressure. |
| Logging/file writes/synchronized locks per element | Side effects, potential blocking or contention | Rethink design; do not default to parallel. |
| Very small source | Split/merge cost may exceed computation | Usually prefer sequential `stream()`. |

## 4. Why is blocking I/O a problem for the common pool?

Consider a pipeline like:

```java
// Illustrative example; DO NOT implement this way by default:
List<String> results = ids.parallelStream()
        .map(id -> blockingHttpLookup(id))
        .toList();
```

`ids` is the input set of identifiers, and `blockingHttpLookup` represents an application-supplied **synchronous** network call. For each `id`, a worker may block waiting on connection, server, database, or timeout. While waiting, the worker cannot perform useful CPU work for the task it holds.

This introduces several risks:

1. **Tying up workers for too long:** many concurrently blocking elements can occupy most of the pool's capacity.
2. **Impacting unrelated tasks:** the common pool is a shared resource; work from other modules may be forced to wait.
3. **No active rate limiting against target services:** pool size is not a rate limit policy or maximum connection budget agreed with the API/DB.
4. **Unpredictable latency:** waiting steps do not obey any deadline set automatically by parallel stream.
5. **Wait-cycle risk:** if a blocking task waits on another task that needs the very pool currently occupied, the design can stall or suffer severe wait inflation.

`ForkJoinPool` has mechanisms supporting certain Fork/Join coordinated waits and provides `ManagedBlocker` to signal blocking operations. However, **you cannot assume it automatically compensates enough workers for arbitrary JDBC, HTTP, or `Thread.sleep` calls**. Execution policy, resource limits, and how blocking APIs are used govern actual behavior.

### `parallelStream()` does not replace timeouts

```java
// limit(10) only limits element count, NOT elapsed time.
List<String> firstTen = ids.parallelStream()
        .limit(10)
        .map(id -> blockingHttpLookup(id))
        .toList();
```

`limit(10)` does not guarantee completion within a given number of milliseconds. If the target service hangs, the pipeline can still wait indefinitely. Timeouts must be configured on the **I/O call**, on the task, or at the orchestration layer with explicit cancellation behavior.

## 5. `ForkJoinPool.ManagedBlocker`: a specialized tool, not a universal cure

`ForkJoinPool.managedBlock(ManagedBlocker)` lets a task inform `ForkJoinPool` that it **may block**, giving the pool an opportunity to adjust worker threads according to its policy and implementation limits.

The two methods of `ManagedBlocker`:

- `isReleasable()`: checks whether execution can proceed without blocking.
- `block()`: performs the potentially blocking operation and returns completion status.

**Syntax-illustration** example, not a recommended solution for HTTP:

```java
import java.util.concurrent.ForkJoinPool;

final class WaitOnce implements ForkJoinPool.ManagedBlocker {
    private volatile boolean done;

    @Override
    public boolean isReleasable() {
        return done;
    }

    @Override
    public boolean block() throws InterruptedException {
        if (!done) {
            Thread.sleep(50); // Simulating a wait only
            done = true;
        }
        return true;
    }
}

// Inside a method declaring throws InterruptedException:
ForkJoinPool.managedBlock(new WaitOnce());
```

This illustrates the interface and should not be copied into a benchmark snippet. **`ManagedBlocker` does not set API rate limits, does not provide a pipeline-wide timeout, does not guarantee zero resource exhaustion, and does not turn the common pool into an isolated pool.** It only fits when the developer controls the waiting mechanism and understands the Fork/Join contract.

In most applications calling external services, a clearer approach is offloading I/O tasks to a **dedicated executor**, capping load, and setting timeouts at the call site.

## 6. Complete Java 17+ example: blocking I/O with an explicit `ExecutorService`

Instead of relying implicitly on the common pool, we can create a dedicated executor for blocking I/O tasks. The example below uses `Thread.sleep` **solely to simulate latency**, so it runs without needing a server or network connection. Save as `ControlledIoTasksDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ControlledIoTasksDemo {
    static String simulateRemoteLookup(int id) {
        try {
            Thread.sleep(80); // Simulate I/O wait time
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Tra cứu bị ngắt", e);
        }
        return "item-" + id;
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(1, 2, 3, 4, 5, 6);

        // Limit to at most 3 workers executing lookups concurrently
        // within this dedicated ExecutorService.
        ExecutorService ioPool = Executors.newFixedThreadPool(3);

        try {
            List<CompletableFuture<String>> futures = ids.stream()
                    .map(id -> CompletableFuture.supplyAsync(
                            () -> simulateRemoteLookup(id),
                            ioPool
                    ))
                    .toList();

            // Read results in exact list order of futures.
            List<String> results = futures.stream()
                    .map(CompletableFuture::join)
                    .toList();

            System.out.println(results);
        } finally {
            ioPool.shutdown();
        }
    }
}
```

Output:

```text
[item-1, item-2, item-3, item-4, item-5, item-6]
```

Key design points:

- `ids.stream()` here is a **sequential Stream** used to **submit tasks**. Concurrency comes from `CompletableFuture.supplyAsync(..., ioPool)`, not from `.parallel()`.
- `ioPool` is passed explicitly, avoiding the common pool for these lookups.
- `newFixedThreadPool(3)` caps active worker execution in the pool at three, even though the list has six jobs. The order in which tasks finish is still unspecified.
- `futures.stream().map(CompletableFuture::join)` collects results **in the order of futures in the list**, not by task completion time. `join()` may block waiting.
- `shutdown()` initiates executor shutdown; in this example, all `join` calls completed normally before `shutdown`. Production applications still need explicit error, cancellation, and cleanup paths.

**Essential caveat:** `Executors.newFixedThreadPool(3)` uses an unbounded task queue in typical configurations. It limits the **number of concurrently running tasks**, **not** the number of queued waiting tasks. Submitting millions of requests can still grow queue memory sharply.

## 7. Queue bounds, backpressure, and timeouts

If an application needs to bound queued tasks as well, you can use `ThreadPoolExecutor` with a fixed-capacity queue:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor ioPool = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.CallerRunsPolicy()
);
```

This snippet illustrates **configuration** only. After use, manage its lifecycle and call `shutdown()` or an appropriate termination policy.

When all four workers are busy and 16 jobs are queued, `CallerRunsPolicy` may execute a new task **on the thread calling `execute`**, creating *backpressure* by making the submitter participate in work. However:

- This mechanism can **block the submitting thread**; do not apply it carelessly on an event loop or low-latency request path.
- `CallerRunsPolicy` behaves differently if the executor has already been shut down; it does not replace admission control and cancellation policies.
- No queue configuration automatically enforces DB connection limits, service rate limits, or excessive retry bounds. Those limits must be configured separately.

### `CompletableFuture` timeouts

On Java 9+, `orTimeout` completes a future exceptionally if a deadline expires:

```java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(
                () -> simulateRemoteLookup(1), ioPool
        ).orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` limits **how long callers wait for the future's result** under `CompletableFuture` completion semantics. It **does not automatically interrupt** an underlying blocking network/JDBC call. Nor should `CompletableFuture.cancel(true)` be assumed to reliably interrupt a running task. In real systems, configure **connect timeouts and read/request timeouts** on the HTTP/JDBC client and define cleanup for timed-out work.

Do not add a future timeout and assume the worker, socket, or resource has been released. **Result timeout** and **underlying execution cancellation** are two separate concerns.

## 8. Want pool control for CPU-bound work: use an API with an explicit executor

A commonly passed-around trick is wrapping a parallel stream inside a custom `ForkJoinPool`:

```java
// NOT a standard API to bind a pool per parallel Stream:
// customPool.submit(() -> data.parallelStream().map(...).toList()).join();
```

In some implementations, a parallel stream launched from a worker of a custom `ForkJoinPool` may execute on that pool. Yet this is **not a standard contract** for selecting an executor per pipeline; nor does it solve timeouts, blocking I/O control, or isolation in all environments. Do not make this trick a correctness requirement of your application.

If you need to **explicitly choose a `ForkJoinPool`** for divide-and-conquer computation, use `ForkJoinTask`/`RecursiveTask` directly. The following Java 17+ example sums the range `[1, 1_000_001)` using a pool with target parallelism two. Save as `DedicatedForkJoinDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class DedicatedForkJoinDemo {
    static final class RangeSumTask extends RecursiveTask<Long> {
        private static final long THRESHOLD = 20_000;

        private final long fromInclusive;
        private final long toExclusive;

        RangeSumTask(long fromInclusive, long toExclusive) {
            this.fromInclusive = fromInclusive;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            long length = toExclusive - fromInclusive;

            if (length <= THRESHOLD) {
                long sum = 0;
                for (long i = fromInclusive; i < toExclusive; i++) {
                    sum += i;
                }
                return sum;
            }

            long middle = fromInclusive + length / 2;
            RangeSumTask left = new RangeSumTask(fromInclusive, middle);
            RangeSumTask right = new RangeSumTask(middle, toExclusive);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool dedicatedPool = new ForkJoinPool(2);
        try {
            long sum = dedicatedPool.invoke(
                    new RangeSumTask(1, 1_000_001)
            );
            System.out.println(sum); // 500000500000
        } finally {
            dedicatedPool.shutdown();
        }
    }
}
```

Here:

1. `dedicatedPool.invoke(task)` submits the **Fork/Join task** to an **explicitly** chosen pool.
2. `compute()` splits the range when element count exceeds the threshold; the left branch calls `fork()`, the right branch computes on the current thread, and then `join()` waits for the left result.
3. The two branches cover **disjoint**, exhaustive ranges, and addition on this input does not overflow `long`.
4. `new ForkJoinPool(2)` controls a target parallelism level for a **dedicated pool**, though it should not be viewed as a hard guarantee that the OS creates strictly two threads across any helper or blocker-compensation mechanisms.

This is an example with **explicit executor control**, using `RecursiveTask`, **not** `Stream.parallel()`. For merely summing a small range, `LongStream.rangeClosed(...).sum()` is still more concise; writing custom Fork/Join tasks is worth considering when divide-and-conquer or pool isolation is a real requirement.

## 9. Comparing task orchestration approaches

| Approach | Choose executor for work? | Suitable scenario | Limits to remember |
| --- | --- | --- | --- |
| `stream().parallel()` | **No** standard API to pass a custom executor | Stateless, splittable, sufficiently large CPU computation | Commonly uses shared pool per implementation; no built-in timeout/backpressure. |
| `CompletableFuture.supplyAsync(task)` | Unspecified | Simple async work when default executor policy is acceptable | May use common pool or another default mechanism; prone to contention. |
| `CompletableFuture.supplyAsync(task, executor)` | **Yes** | I/O or async work needing a dedicated pool | Must bound threads, queues, deadlines, and cleanup. |
| `ForkJoinPool.invoke(RecursiveTask)` | **Yes** | CPU divide-and-conquer needing pool control | Must design splitting, thresholds, merging, and avoid blocking. |
| `ExecutorService.submit(Callable)` | **Yes** | Explicit `Future` management, cancellation, and waiting | Cancel/interrupt behavior depends on task and executor. |

Since Java 21, **virtual threads** offer an option for many blocking I/O tasks that can scale concurrency: `Executors.newVirtualThreadPerTaskExecutor()`. However, that is a separate scheduling mechanism—**it does not mean `parallelStream()` automatically switches to virtual threads**, and virtual threads still require limits on connections, queries, and request rates. The main examples in this lesson target Java 17 and therefore do not invoke Java 21 APIs.

## 10. Ordering, side effects, cancellation, and other limits

### Keep correctness before optimizing

Stream lambdas should generally be **non-interfering with the source, free of shared mutable state, and independent of execution order across elements**:

```java
import java.util.List;

List<Integer> doubled = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8]
```

`map` is an independent transformation, easy to parallelize. With an ordered `List` source and `toList()`, output order is maintained per pipeline semantics; **actual lambda invocation order and processing threads may vary**.

Conversely, the following is unsafe:

```java
// Do not do this: a shared ArrayList is unsafe when multiple threads add.
// List<Integer> shared = new ArrayList<>();
// numbers.parallelStream().forEach(shared::add);
```

If a list result is needed, use `collect(Collectors.toList())` or `toList()` instead of mutating an external `ArrayList`. Using standard collectors lets the framework manage accumulation containers and merge results properly.

### `forEach` and `forEachOrdered`

`forEach` on a parallel stream **does not guarantee processing order**; `forEachOrdered` preserves encounter order when the source is ordered, though it may reduce parallel efficiency:

```java
List.of("A", "B", "C").parallelStream()
        .forEachOrdered(System.out::print); // ABC
```

Do not equate **returned result order** with **callback execution order**. If a program requires ordered external side effects such as sending emails, writing to a DB, or calling APIs in sequence, design explicit orchestration rather than relying on `parallelStream()`.

### When to stop and cancel?

The Stream API provides short-circuiting terminal operations like `findAny`, `anyMatch`, or `limit` in relevant pipelines, yet those are **not general task-cancellation APIs** or deadline mechanisms. Some work may already have started before the short-circuit result is decided.

There is no general `stream.cancel()` to reliably halt all blocking tasks. When deadlines, cancellation, or partial results are needed, pick a task model with orchestration tools and explicitly define interruption, cancellation checks, and resource closure.

### Avoid habitual nested parallelism

A parallel stream inside the lambda of another parallel stream can complicate scheduling, spawn excessive tiny tasks, and obscure performance measurements. Do not enable parallelism at both levels by default; usually pick **one appropriate level** to parallelize and keep the rest sequential, or design Fork/Join tasks with explicit split thresholds.

## 11. Configuring and observing the common pool: knowing intervention limits

The JDK provides system properties affecting the common pool, such as `java.util.concurrent.ForkJoinPool.common.parallelism`. Such configuration is **JVM-wide**, not scoped to a single `parallelStream()`. It is also affected by when the common pool is initialized and runtime configuration.

Therefore:

- Do not use JVM-wide system properties as a way to select a custom executor per pipeline.
- Do not arbitrarily tune common pool parallelism just to speed up one module; it can impact other modules.
- Do not treat `Runtime.getRuntime().availableProcessors()` as an exact thread count in all environments, especially when CPU/cgroup/container limits change.
- Monitor `ForkJoinPool.getCommonPoolParallelism()`, CPU, latency, queues, blocking states, and system metrics, without assuming from a single number that throughput is under control.

When tight control is needed, choose a mechanism with an **explicitly passed executor**, enforcing load limits and timeouts at the service-call layer.

### Measure performance instead of inferring from `.parallel()`

To evaluate whether a parallel stream is worthwhile, measure on representative data and environments:

1. Identify whether the work is CPU-bound or I/O-bound; measure the ratio of actual CPU time to wait time.
2. Measure both **throughput and latency**, not just one warm-memory run.
3. Compare sequential execution, parallel stream, and a dedicated executor if heavy I/O is involved.
4. Test under concurrent load from other modules when sharing the common pool.
5. For Java microbenchmarks, consider **JMH** instead of timing a single `System.nanoTime()` call and jumping to conclusions.

Do not over-provision threads simply because tasks are slow; that can increase contention on CPU, connections, memory, or downstream service limits.

## 12. Common pitfalls

| Mistake | Possible impact | How to fix |
| --- | --- | --- |
| Believing `parallelStream()` always uses a dedicated pool | Unrelated jobs can contend on the common pool | Understand API limits; use an explicit executor when isolation is needed. |
| Putting blocking synchronous I/O in a parallel stream `map` | Workers stay tied up waiting; latency rises in other modules | Use a dedicated executor, timeouts, and I/O load limits. |
| Raising `common.parallelism` to "fix" all blocking issues | JVM-wide side effects, higher resource contention | Fix architecture, timeouts, backpressure; configure globally only with intent. |
| Treating `ManagedBlocker` as guaranteed worker compensation | Can still exhaust resources or stall | Use only in specialized cases, not as a substitute for pool isolation. |
| Using `newFixedThreadPool(n)` assuming its queue is also bounded | Queued waiting tasks can grow unbounded | Use a bounded queue, rejection/backpressure policy, or semaphore. |
| Using `orTimeout` alone thinking I/O was interrupted | Future fails yet underlying work may keep running/blocking | Set timeouts on HTTP/JDBC clients and design resource cancellation. |
| Treating custom-FJP wrapping of parallel stream as a portable pool-selection API | Implementation-dependent, hard to control | Use `ForkJoinTask` or executor APIs with explicit contracts. |
| Using `forEach` with shared mutable state | Races and wrong results | Use `collect`, proper associative reduction, or explicit synchronization. |
| Assuming thread count always equals CPU count | Wrong concurrency and performance predictions | Observe runtime and measure real load. |
| Parallelizing tiny or nested tasks | Overhead outweighs gains, poor scheduling | Choose appropriate parallelism level and split thresholds. |

## 13. Self-check questions

**Question 1.** Can you call `numbers.parallelStream().executor(myExecutor)` in the standard Java Stream API?

**Answer:** No. The Stream API provides no standard method to attach an executor per pipeline. When explicit executor selection is needed, use APIs like `CompletableFuture.supplyAsync(task, executor)` or `ForkJoinPool.invoke(task)`.

**Question 2.** Why can `ForkJoinPool.commonPool()` cause cross-module interference?

**Answer:** In common implementations, it is a JVM-wide shared pool. When one module ties up many workers with blocking tasks, other modules sharing that pool can be starved of processing capacity.

**Question 3.** Does `newFixedThreadPool(4)` automatically limit the number of queued waiting requests to four?

**Answer:** No. It limits concurrently executing workers; the default queue has no small built-in capacity cap. Add a bounded queue, rejection policy, or admission control.

**Question 4.** Does `CompletableFuture.orTimeout(...)` guarantee the HTTP socket is closed and the I/O call is interrupted?

**Answer:** No. It governs completion of the future; cancelling the underlying work depends on the call and execution mechanism. Configure timeouts, cancellation, and resource closure on the actual client.

**Question 5.** Why can `parallelStream().map(cpuHeavyPureFunction).collect(...)` fit better than `parallelStream().map(blockingDatabaseQuery).collect(...)`?

**Answer:** Independent CPU work splits and merges efficiently; blocking queries occupy workers during I/O waits, causing contention on the pool and connections. Queries need bounded concurrency and timeouts.

**Question 6.** You need a dedicated `ForkJoinPool(2)` for a divide-and-conquer algorithm. What approach has a clear contract?

**Answer:** Submit `RecursiveTask`/`ForkJoinTask` directly via `dedicatedPool.invoke(task)` or `submit`. This explicitly controls the pool of the submitted tasks; do not rely on wrapping a parallel stream inside a pool as a standard Stream configuration API.

## Takeaway

- `parallelStream()` only requests parallel pipeline execution; **there is no standard API to pass a custom executor per Stream**.
- In common OpenJDK implementations, parallel streams typically use the **shared `ForkJoinPool.commonPool()`**, so blocking work can impact other tasks.
- `ForkJoinPool` works better for splittable, mergeable CPU work; **blocking I/O needs concurrency limits, timeouts, and backpressure** in an appropriate execution model.
- `ManagedBlocker` helps signal certain blocking operations without providing isolation or worker guarantees; `orTimeout` does not automatically interrupt background work.
- When explicit control is required, use `CompletableFuture.supplyAsync(..., executor)` / `ExecutorService`, or submit `ForkJoinTask` to a dedicated pool; keep lambdas safe, manage resources, and **measure performance before optimizing**.