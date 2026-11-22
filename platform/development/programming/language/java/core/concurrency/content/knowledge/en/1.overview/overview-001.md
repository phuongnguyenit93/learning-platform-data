# How do concurrency, parallelism, and asynchronous execution differ in Java?

These three terms often appear together because they all relate to performing multiple tasks, but they answer **three different questions**:

- **Concurrency (concurrent processing in the organizational sense):** How does a system manage the progress of multiple tasks within the same time period?
- **Parallelism (parallel execution):** Are two or more tasks actually running at **the exact same point in time** on different compute resources?
- **Asynchronous execution:** After requesting a task, can the caller **continue** without waiting for the result immediately?

An application can use all three, only one, or two of them. **Asynchronous does not mean non-blocking; concurrency does not mean parallelism; more threads do not automatically guarantee speedup.**

## 1. Concurrency: managing the progress of multiple tasks together

**Concurrency** is the ability to structure a program so that multiple tasks have overlapping progress within a given time period. At any brief moment of observation, each task may be running, waiting for CPU, waiting for I/O, waiting for a lock, or ready to run.

On a system with only one available CPU core, the scheduler can give each thread a turn to run for a short slice and then switch to another thread. Viewed over a longer interval, both tasks make progress; at any single instant of CPU execution, only one task is running.

```text
Time ----------->

One CPU core:
CPU:  [A runs][B runs][A runs][B runs][A runs]
A:    [runs]   [runs]          [runs]
B:             [runs]   [runs]

Tasks A and B have overlapping lifetimes,
but no two "runs" segments on the CPU occur at the same time.
```

The diagram is an illustration of turn-sharing, not a schedule guaranteed by Java. In Java, multiple `Thread`s or tasks submitted to an `ExecutorService` are ways to organize concurrent work. Whether they actually run simultaneously on multiple cores depends on the number of active threads, the number of available cores, and the scheduler's decisions.

The strength of concurrency is not just speed: it helps a program respond to independent requests, handle waiting work, and use resources flexibly. In return, tasks can contend for shared data, locks, and resources; synchronization and lifecycle must be managed carefully.

## 2. Parallelism: actually running at the same time

**Parallelism** occurs when two or more pieces of work **are executing simultaneously in real time**, for example on two CPU cores. This is a property of actual runtime execution, not just how the code is written.

```text
Time ----------->

Two CPU cores:
Core 1: [A runs][A runs][A runs]
Core 2: [B runs][B runs][B runs]

The execution segments of A and B overlap across two cores.
```

For example: splitting a large computation into two independent parts and assigning them to two workers on two CPU cores. If they actually run simultaneously, the problem exhibits parallelism. In Java, this intent can be expressed using an `ExecutorService` with multiple workers, `ForkJoinPool`, parallel streams, or divide-and-conquer algorithms.

However:

- A pool with two workers **allows** two tasks to run simultaneously; it does not guarantee they will always be placed on two cores or always be faster.
- Increasing the number of threads does not increase the number of CPU cores; too many threads can increase context-switching overhead and contention.
- An algorithm that cannot be split into independent parts, or that frequently has to lock the same data, may not benefit from parallelism.
- On a multi-core machine, concurrent tasks can also be parallel. Therefore, parallel execution is a case that exhibits concurrency in terms of progress, but not every concurrent execution is parallel.

## 3. Asynchronous execution: not forcing the caller to wait immediately

**Asynchronous execution** is about the **timing relationship between the caller and the result**. The caller initiates the work and can do other things before receiving the result via a `Future`, `CompletableFuture`, callback, or completion notification mechanism.

Contrasting control flows:

```text
Synchronous:
Caller: [call A........wait for A][process result][other work]

Asynchronous:
Caller: [start A][other work.....................][use result]
Worker:       [execute A.........................]
```

With a normal synchronous call, the method only returns when its work has completed or failed. With an asynchronous API, the method typically returns early with an object representing the work; the result arrives later. The caller can still **choose to wait**, for example by calling `Future.get()` or `CompletableFuture.join()`. At that exact wait point, the calling thread can be blocked.

Asynchronous execution does not have only one execution model:

- **Thread-based async:** A worker thread performs the work on behalf of the caller. If the worker performs blocking I/O, the worker itself is still blocked.
- **Event-driven/non-blocking I/O async:** An event loop can register multiple I/O operations and process them when they are ready, without keeping a dedicated thread waiting for each request. Java NIO `Selector` is a foundational API for this approach.
- **Async completion chain:** Subsequent processing is described using `thenApply`, `thenCompose`, `thenCombine`, etc., to trigger when the appropriate completion condition is met.

Therefore, **async does not prove non-blocking I/O**. For example, `CompletableFuture.supplyAsync(() -> Thread.sleep(...), executor)` returns early to the caller, but the worker is blocked in `sleep`. Conversely, a non-blocking operation does not automatically create CPU parallelism.

## 4. Comparison by criteria

| Criteria | Concurrency | Parallelism | Asynchronous execution |
| --- | --- | --- | --- |
| Main question | How can multiple tasks make progress / be managed together? | Are multiple tasks actually running at the same time? | Does the caller need to wait for the result immediately after calling? |
| Focus of observation | Lifecycle and coordination among tasks | Overlap of **execution** in real time | Calling, completion, and result-retrieval interface |
| Requires multiple CPU cores? | No | Requires simultaneous execution resources for true CPU parallelism | No |
| Requires multiple threads? | Not necessarily (can use an event loop) | CPU parallelism usually requires multiple workers/cores | Not necessarily |
| Common goals | Responsiveness, organizing independent work | Increasing compute throughput when work is split effectively | Avoiding blocking the caller, composing dependent tasks |
| Risks to watch out for | Race condition, deadlock, starvation | Overhead, contention, CPU load | Faulty callbacks/chains, loss of lifecycle control, accidental blocking |

**The three concepts lie on different axes.** For example, a program accepting many connections using an event loop has concurrency and asynchronous I/O operations, yet still processes callbacks on a single thread at any given moment. A program using two workers computing simultaneously has concurrency and parallelism. A program returning a `CompletableFuture` is async from the caller's perspective, but if it only uses one worker, you cannot conclude it has CPU parallelism.

## 5. Java 17+ example: all three aspects appearing in one program

The following program submits **two independent tasks** to a two-worker pool, allowing the `main` thread to continue processing before using the result. `Thread.sleep` only **simulates a blocking wait operation** to make the structure easy to observe; it does not represent non-blocking I/O.

Save as `ExecutionModesDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutionModesDemo {
    private static String load(String id) {
        try {
            Thread.sleep(150); // Simulate a blocking wait operation
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", e);
        }
        return id;
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<String> first =
                    CompletableFuture.supplyAsync(() -> load("A"), pool);
            CompletableFuture<String> second =
                    CompletableFuture.supplyAsync(() -> load("B"), pool);

            System.out.println("Da gui hai tac vu");

            CompletableFuture<String> combined =
                    first.thenCombine(second, (a, b) -> a + " + " + b);

            System.out.println("Main tiep tuc viec khac");
            System.out.println(combined.join());
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExecutionModesDemo.java
java ExecutionModesDemo
```

**Exact stdout** (the workers do not print to the console, so the order of the three lines is deterministic):

```text
Da gui hai tac vu
Main tiep tuc viec khac
A + B
```

Breakdown of each part:

1. **Concurrency:** `first` and `second` represent two independent tasks that can both be in an incomplete state at the same time; `main` also continues running.
2. **Asynchronous execution:** `supplyAsync` schedules the tasks and returns a `CompletableFuture`. The `main` thread prints the next message without waiting for the two tasks to complete at the call site. `thenCombine` represents a processing step when **both** results are ready.
3. **Parallelism may occur:** The pool has two workers, so the two tasks have the opportunity to execute at overlapping times on different cores. The code does not guarantee this across all environments; measured elapsed time is also not absolute proof.
4. **Blocking is still present:** Each worker is blocked in `Thread.sleep(150)`. After printing the second line, `main` calls `combined.join()`; if the result is not finished yet, `main` is also blocked until completion.
5. **No unbounded thread creation:** `Executors.newFixedThreadPool(2)` limits the pool to two workers and queues excess tasks. `shutdown()` instructs the executor to stop accepting new tasks and terminate after previously submitted tasks finish; in this example, `join()` has already waited for both to complete successfully beforehand.

Do not take a single run measuring around 150 ms as conclusive proof of "parallelism": startup time, scheduling, waiting, and the number of available cores all affect the result.

## 6. CompletableFuture: an async API does not mean a new thread for every step

Once you have a `CompletableFuture<T>`, Java provides different ways to compose steps:

| API | Meaning | Things to remember |
| --- | --- | --- |
| `supplyAsync(supplier, executor)` | Schedules computing a value on the specified executor | The supplier can still block |
| `runAsync(runnable, executor)` | Schedules a task that produces no value | Result type is `CompletableFuture<Void>` |
| `thenApply(fn)` | Transforms the result when the previous stage succeeds | Does not guarantee a separate task/thread; the function may run on the thread that completes the stage |
| `thenApplyAsync(fn, executor)` | Schedules the transformation step asynchronously via the executor | Execution timing depends on the executor |
| `thenCompose(fn)` | Chains an async task that depends on the previous result | Avoids nested `CompletableFuture<CompletableFuture<T>>` |
| `thenCombine(other, fn)` | Combines the results of two stages when both complete | Suitable for tasks with independent inputs |
| `allOf(futures...)` | Stage completes when all given stages complete | Does not automatically produce a list of results; must retrieve from each future |
| `exceptionally(fn)`, `handle(fn)` | Handles or transforms errors | Need to define recovery behavior and preserve error context |
| `join()` / `get()` | Waits for and retrieves the final value | Both can block; `join()` wraps errors in `CompletionException`, `get()` uses `ExecutionException` and can throw `InterruptedException` |

A common misconception: a name like `thenApply` **without the `Async` suffix** does not mean it always runs on the caller thread; conversely, `thenApplyAsync` does not mean Java creates a brand-new thread. For `Async` methods without an executor argument, they typically use `ForkJoinPool.commonPool()` according to `CompletableFuture`'s default execution policy; when you need resource control, provide an appropriate executor.

If B needs A's result, the chain `A.thenCompose(a -> startB(a))` expresses **sequential data dependency**, even though the caller can still interact asynchronously with the whole chain. If A and B are independent, create both first and then use `thenCombine` to take advantage of overlapping execution; do not start B only after `A.join()` if there is no dependency relationship.

`Future.get()` simply retrieves the result and may have to wait; `CompletableFuture` additionally provides mechanisms to combine and handle completions without forcing the caller to call `get()` at every step. However, a system still needs a synchronization point at the boundary where the result is consumed, as well as appropriate timeout, error, and cancellation policies.

## 7. Separate example of CPU parallelism intent

For computations that can be split into independent parts, a parallel stream is a Java API that expresses the **intent** to partition computation. To keep the example reproducible, use integer summation:

Save as `ParallelSumDemo.java`:

```java
import java.util.stream.LongStream;

public class ParallelSumDemo {
    public static void main(String[] args) {
        long total = LongStream.rangeClosed(1, 1_000_000)
                .parallel()
                .sum();

        System.out.println(total);
    }
}
```

```bash
javac ParallelSumDemo.java
java ParallelSumDemo
```

Stdout:

```text
500000500000
```

The mathematical result is `1_000_000 × 1_000_001 / 2 = 500_000_500_000`. `parallel()` allows the stream to split work for execution across multiple workers, typically using the common fork/join pool. That does not guarantee it will be faster than `.sequential()`. For simple operations or small datasets, the overhead of splitting and merging work can dominate. This code illustrates how to express parallel computation; to prove performance, you need proper benchmarking on real data and a well-defined environment.

It is also important to distinguish: `sum()` has a safe reduction rule; you should not use `parallelStream().forEach(...)` to mutate a shared `ArrayList` or rely on element order, as that easily causes data races or unstable results.

## 8. Common combinations in Java applications

| Scenario | Concurrency? | Parallelism? | Async to the caller? |
| --- | --- | --- | --- |
| Two `Thread`s alternated by the scheduler on one core | Yes | No at the CPU level being considered | Depends on how the caller starts/waits |
| Two compute tasks running simultaneously on two cores | Yes | Yes | May or may not be, depending on the API |
| Caller uses `supplyAsync`, but the executor has only one worker and tasks block | Can organize multiple tasks coexisting | No two tasks run in parallel in that pool | Yes, until the caller invokes a waiting method |
| A Java NIO event loop handling ready connections | Yes | Not necessarily | Possibly, depending on the API/notification mechanism |
| Caller invokes a synchronous method that internally splits work across multiple CPUs and waits until done before returning | Yes (internally) | Possibly | No at the caller interface |
| A single synchronous HTTP call running in one thread | Not necessarily | No | No |

The parallelism column depends on **actual runtime execution behavior**; it cannot be deduced with certainty just by seeing `parallel()`, the number of threads, or a `Future` object.

## 9. Choosing an approach by workload type

**CPU-bound** (computation, data analysis, bulk data encryption): if the work can be split into sufficiently large and independent parts, consider `ForkJoinPool`, an executor with an appropriate parallelism level, or parallel streams. Measure actual performance. Limit the number of truly runnable tasks to avoid having more workers than the CPU can efficiently handle.

**I/O-bound** (reading/writing, network connections, service calls): concurrency is useful because tasks spend time waiting. You can use a pool performing blocking I/O or non-blocking I/O APIs if the libraries and architecture fit. Async helps the caller continue processing and compose results; it does not turn a blocking call into a non-blocking one on the worker.

**Need a responsive interface:** use async so you don't hold the caller at an immediate wait point, but design where results are received, control the number of in-flight tasks, and handle error reporting. If you merely offload a task to a worker and immediately call `join()`, the asynchronous benefit to the caller virtually disappears.

**Need ordered data:** identify dependency relationships. Dependent steps must wait for prior data; independent steps can be submitted concurrently. Blindly parallelizing can cause ordering bugs or data corruption.

## 10. Common conceptual and technical mistakes

1. **"Concurrent means always running at the same time."** False: on a single CPU core, the scheduler can let tasks make progress alternately. Parallelism is what refers to truly overlapping execution intervals.
2. **"Async means non-blocking."** False: the caller may not wait, but the worker still blocks when reading a file, calling `sleep`, or performing synchronous I/O.
3. **"Using `CompletableFuture` guarantees parallelism."** False: a single-worker executor can execute tasks sequentially; dependent stages also do not run simultaneously just because of the API name.
4. **"More threads are always faster."** False: CPU contention, context switching, lock contention, memory bandwidth, and split/merge overhead can make things slower.
5. **"Calling `join()` right after each `supplyAsync` makes good use of concurrency."** Usually false if two tasks are independent: this pattern can serialize when the work starts. Initiate independent tasks first, then combine or wait for their results.
6. **"Async tasks handle errors automatically."** False: errors can complete a future exceptionally; you must observe failures via `join/get` or an error-handling stage. Never ignore important futures.
7. **"`shutdown()` cancels everything immediately."** False: `shutdown()` stops accepting new tasks and lets already-submitted tasks finish; `shutdownNow()` attempts to interrupt/cancel on a best-effort basis, but also does not guarantee tasks stop immediately. Blocking tasks must be designed to respond properly to interruption.
8. **"Thread safety comes automatically with async."** False: `count++` on a shared variable does not become atomic just by running inside a task. You need immutable data, thread confinement, `AtomicInteger`, locks, or appropriate concurrent data structures depending on the situation.
9. **"All continuations always run on the same thread."** False: a continuation without the `Async` suffix may run on the thread that completed the previous stage, or on the calling thread if the stage is already complete; do not rely on thread identity when designing logic.
10. **"Cancellation always interrupts running work."** There is no such general guarantee with `CompletableFuture.cancel(...)`; specifically, this mechanism does not use interrupts to control execution. Design timeouts, cancellation flags, and resource closing according to the specific API.

With Java 21 and later, **virtual threads** make the thread-per-task model more convenient for many blocking I/O tasks, but they **do not create additional CPU cores** and do not make a CPU-bound computation inherently faster. They also do not change the definitions of the three concepts above. The main examples in this article still use APIs available on Java 17.

## 11. Self-check scenarios

**Scenario A:** One thread handles multiple sockets by receiving I/O readiness notifications and processing events one by one. There is concurrency among connections and possibly asynchronous/non-blocking I/O; there is no evidence of parallel callback processing on the CPU.

**Scenario B:** Two independent computations are assigned to two workers and actually run at the same time on two cores. This is concurrency **and** parallelism; whether the calling interface is async depends on whether the caller must wait immediately at the call site.

**Scenario C:** A function returns a `CompletableFuture` immediately, while the worker reads data using a blocking method and the caller continues processing. This is async to the caller; the worker is still blocking. There is not enough information to say whether CPU parallelism is occurring.

**Scenario D:** A caller invokes a synchronous function that computes a large sum using multiple workers; the function waits for all of them to finish before returning the result. The computation itself may be concurrent and parallel, but **the external call is still synchronous**.

When encountering a new API or design, ask in order:

1. **How many tasks are coexisting and making progress?** → examine concurrency.
2. **Are there computation segments actually running at overlapping times on different resources?** → examine parallelism.
3. **Can the caller do other work before needing the result, or is it forced to wait at the call site?** → examine asynchronous execution.

These three questions help you choose the right Java mechanism, analyze bottlenecks more clearly, and avoid drawing wrong conclusions from API names or thread counts.
