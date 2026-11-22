# Why Can Blocking I/O Cause a Parallel Stream Bottleneck?

**Answer:** `parallelStream()` helps split work into parts that can execute concurrently, which is especially useful when each part **performs CPU computation**. In the common JDK implementation, parallel stream tasks are organized using `ForkJoinPool` and typically use `ForkJoinPool.commonPool()`. When `map()`, `filter()`, `forEach()`, or another processing step invokes **blocking I/O** (waiting on HTTP, sockets, files, databases, etc.), a worker may have to **wait idly** instead of processing the next piece of data. If many workers wait simultaneously, parallel splitting no longer processes work efficiently: unprocessed elements must queue up, completion time increases, and other tasks sharing the pool may also be affected.

This article focuses solely on **Java concurrency and the Java Stream API**, and does not cover Spring-specific configuration mechanisms.

## 1. Background: How Does a Parallel Stream Run?

A sequential stream typically applies a pipeline along a single thread of execution:

```java
List<String> result = ids.stream()
        .map(this::calculate)
        .toList();
```

When using `parallelStream()` (or `stream().parallel()`), the Stream API can split the data source into parts and execute tasks via the fork/join mechanism:

```text
Input list: [1, 2, 3, 4, 5, 6, 7, 8]
                    |
                  split
            /                 \
       [1,2,3,4]           [5,6,7,8]
         /   \               /    \
      [1,2] [3,4]         [5,6] [7,8]
         \   /               \    /
            combine results
                    |
          [result-1, ..., result-8]
```

`ForkJoinPool` uses workers (platform threads) and a *work stealing* mechanism to reduce worker idle time when suitable work remains to be processed. For short, CPU-bound tasks that can be split and combined, this is usually a reasonable choice.

**Important distinctions:**

- `parallelStream()` is a **pipeline execution mode** of the Stream API, not an interface for creating an asynchronous request group.
- A pipeline can run on `ForkJoinPool.commonPool()` workers **and may also use the calling thread**. You must not assume that every element necessarily runs on a common-pool worker.
- The typical parallelism level of the common pool is tied to the number of processors recognized by the JVM and runtime configuration; it is not "one thread per element."
- A stream does not inherently create a separate thread for each I/O operation or automatically scale the pool based on the number of waiting requests.
- Speed also depends on how the source is split (`Spliterator`), per-element cost, result ordering, synchronization, and other tasks sharing the pool.

## 2. Why Does Blocking I/O Cause a Bottleneck?

Blocking I/O occurs when a call **cannot return a result yet** and the executing thread must wait—for example:

- Waiting for a socket to receive data or a response from an HTTP service.
- Waiting for a database query to complete or waiting to acquire a connection from a pool.
- Waiting to read/write a file, or waiting for a shared lock/resource.
- `Thread.sleep()` is used to simulate wait time in examples; by itself, it **is not real I/O**.

Example:

```java
List<Response> responses = urls.parallelStream()
        .map(url -> blockingHttpCall(url))
        .toList();
```

This is **illustrative code**; `Response` and `blockingHttpCall` must be defined in the program. The `map` step is no longer a pure CPU transformation: each call can tie up a worker until a response arrives.

Suppose there are 4 execution units processing concurrently, 12 requests, and each request takes about 1 second **waiting on the network**:

```text
Time            Worker-1      Worker-2      Worker-3      Worker-4
0–1 s           request 1     request 2     request 3     request 4
                [waiting I/O] [waiting I/O] [waiting I/O] [waiting I/O]
1–2 s           request 5     request 6     request 7     request 8
                [waiting I/O] [waiting I/O] [waiting I/O] [waiting I/O]
2–3 s           request 9     request 10    request 11    request 12
                [waiting I/O] [waiting I/O] [waiting I/O] [waiting I/O]
```

This is a **hypothetical visual model** with 4 usable workers and no worker compensation mechanism; **it is not a schedule guaranteed by Java**. When all four workers are waiting, the CPU may be idle while the remaining work still waits its turn. To achieve higher throughput when most of the time is spent waiting on I/O, you need a mechanism that allows more requests to wait concurrently while still controlling actual resource limits.

The bottleneck is the **number of workers available to continue processing tasks**, not a lack of CPU computation. Additionally, when a stream occupies common pool workers with long-running blocking operations, other work using the common pool also risks *thread starvation*.

### An Estimation to Understand the Phenomenon

In a simple case with `P` concurrent I/O calls, each taking an average of `L` seconds, and no other limits on external resources, maximum throughput is approximately `P / L` calls/second when load is sufficiently high. This is only a qualitative model: in reality, there is variable latency, CPU time, scheduling, network behavior, connection limits, and pool execution policies. Do not use this formula to derive the exact requests/second of a specific parallel stream.

## 3. Why Doesn't ForkJoinPool Automatically Handle All Blocking?

`ForkJoinPool` is designed to make good use of work that can be split and combined. When a worker waits for **another fork/join task** to complete through mechanisms the pool understands, it can assist with executing other work instead of sitting idle.

However, **unmanaged I/O waiting** is different from fork/join waiting. The `ForkJoinPool` API documentation notes that the pool **does not guarantee adjusting the number of workers to compensate** for blocked I/O or unmanaged synchronization. Certain types of waiting can be supported using `ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)`; however, that does not mean every HTTP/JDBC/socket call or `Thread.sleep()` inside `map()` will automatically cause the pool to create replacement workers.

Therefore, both of the following statements are false if stated as absolutes:

- "The common pool is always fixed at exactly P threads, and no additional threads can exist."
- "The common pool always automatically spawns enough threads to compensate for every blocking operation."

**Practical takeaway:** Worker adjustment depends on the type of blocking, the runtime, and the specific call path. Do not design an I/O pipeline requiring high concurrency based on the assumption that `ForkJoinPool` will definitely compensate with extra workers.

### Compounding Effects

1. **Sharing the common pool:** Stream A performing blocking I/O can delay Stream B or `CompletableFuture.supplyAsync(...)` calls that use the default common pool.
2. **Synchronization in the pipeline:** Shared locks, writing to an unsafe structure, or waiting on a constrained resource can serialize multiple tasks even when the stream is in parallel mode.
3. **Ordering requirements:** `forEachOrdered` must respect encounter order and can cause some steps to require coordination/serialization. `toList()` preserves encounter order for ordered sources but does not force every element to be computed sequentially.
4. **Slow external I/O:** A connection pool of 10 connections or a service that can only handle 20 concurrent requests is its own bottleneck; increasing the thread count cannot bypass this limit and may degrade the system.
5. **Errors and timeouts:** Requests without reasonable timeouts can hold workers for a long time; if a queue is used, the number of waiting tasks continues to grow.

## 4. Standalone Java 17+ Example: Same Data, Two Coordination Approaches

The following program creates eight independent tasks. The `simulatedBlockingCall()` method uses `Thread.sleep(80)` **to simulate** a waiting operation. The first run uses `parallelStream()`; the second uses a **dedicated I/O executor** with four platform threads. The data result is the same, but where it executes and the task-limiting policy differ.

**File: `BlockingIoParallelStreamDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

public class BlockingIoParallelStreamDemo {

    private static String simulatedBlockingCall(int id) {
        try {
            Thread.sleep(80); // Only simulates I/O wait time.
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at id=" + id, e);
        }
        return "item-" + id;
    }

    public static void main(String[] args) throws Exception {
        List<Integer> ids = IntStream.rangeClosed(1, 8).boxed().toList();

        // Approach 1: blocking inside a parallel stream.
        List<String> fromParallelStream = ids.parallelStream()
                .map(BlockingIoParallelStreamDemo::simulatedBlockingCall)
                .toList();
        System.out.println("parallel=" + fromParallelStream);

        // Approach 2: offload blocking work to a dedicated executor.
        ExecutorService ioExecutor = Executors.newFixedThreadPool(4);
        try {
            List<Callable<String>> tasks = ids.stream()
                    .<Callable<String>>map(id ->
                            () -> simulatedBlockingCall(id))
                    .toList();

            List<Future<String>> futures = ioExecutor.invokeAll(tasks);
            List<String> fromExecutor = new ArrayList<>();
            for (Future<String> future : futures) {
                fromExecutor.add(future.get());
            }
            System.out.println("ioExecutor=" + fromExecutor);
        } finally {
            ioExecutor.shutdown();
        }
    }
}
```

**Compile and run with Java 17+:**

```bash
javac BlockingIoParallelStreamDemo.java
java BlockingIoParallelStreamDemo
```

**Deterministic output (without printing thread names or timing):**

```text
parallel=[item-1, item-2, item-3, item-4, item-5, item-6, item-7, item-8]
ioExecutor=[item-1, item-2, item-3, item-4, item-5, item-6, item-7, item-8]
```

Explanation:

- `parallelStream()` requests parallel pipeline execution, but does not mandate a fixed worker count; `sleep(80)` causes the thread processing the element to wait. This is a simple model for *blocking*, not a measure of real socket/JDBC capacity.
- `newFixedThreadPool(4)` separates blocking work from the common pool and allows **at most four tasks of this executor to run concurrently**. The number 4 is purely illustrative, not an optimal configuration.
- `invokeAll()` waits for tasks to complete and returns `Future` instances in the order of the task list. `Future.get()` can throw `ExecutionException` if a task fails; `main throws Exception` is used to keep the example concise.
- `List.toList()` preserves the encounter order of an ordered stream such as the `ids` list; therefore, the **printed output order** does not reflect the order in which threads ran.
- `shutdown()` instructs the executor not to accept new tasks. If timeout/cancellation shutdown is needed, the application must handle it explicitly and may use `awaitTermination` / `shutdownNow` according to contract.
- `Executors.newFixedThreadPool()` uses an **unbounded task queue by default**. It avoids occupying the common pool, but **does not solve backpressure on its own** when submission rates are high: production systems need a bounded queue or separate input rate control.

**Do not conclude from this example that a dedicated executor is always faster.** With only eight tasks, a parallel stream may be equal or faster depending on the machine and worker count; the goal is to illustrate **resource scope and control**. Only benchmarking under real load, network conditions, and limits can answer throughput/latency questions.

## 5. Diagnosing Bottlenecks in Production

A parallel stream affected by blocking I/O may exhibit the following symptoms:

- **Low CPU but low throughput:** many workers are in an I/O wait state, latency increases, and CPU is underutilized relative to load.
- **Growing queues or pending tasks:** work arrives faster than I/O returns.
- **Sharp spikes in p95/p99:** a subset of slow requests can prolong the completion time of an aggregated pipeline, especially when waiting for all results.
- **Other tasks sharing the common pool slow down:** even though they do not use the same external service.
- **Thread dumps show waiting:** stacks may be inside socket reads, awaits, locks, blocking clients, or `Thread.sleep`; distinguish between network waiting and connection pool waiting.

Inspect using **JFR, thread dumps, profilers**, remote service metrics, and connection pool metrics. `ForkJoinPool.commonPool().getActiveThreadCount()`, `getQueuedTaskCount()`, or `getPoolSize()` can aid observation, but they are approximate/instantaneous measurements; they do not fully reflect caller threads, external resources, or application queues.

### Experimenting with the Common Pool Parallelism Limit

You can run the example above with the following JVM argument to **observe the difference in a specific environment**:

```bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=2 BlockingIoParallelStreamDemo
```

This property is set **at JVM startup**, before the common pool is initialized. This value adjusts the target parallelism of the common pool; **it is not a guarantee of the exact number of threads running at all times**, nor does it simply account for calls that may run on the caller thread. Do not treat a single measurement or a `sleep`-based example as a conclusive benchmark.

## 6. Suitable Options for I/O-Bound Workloads

### Option A: Dedicated ExecutorService for Blocking I/O

With Java 17, a dedicated `ExecutorService` can be an easy-to-implement solution when you must use blocking libraries:

1. Identify the scope of I/O work that needs to be bounded, and do not use `parallelStream()` to trigger blocking calls.
2. Submit tasks to an executor with an explicitly managed lifecycle.
3. Configure the worker count based on the capacity of the remote service, connection pool, CPU, memory, and load testing.
4. Add a **bounded queue, appropriate rejection/waiting policy, and timeouts**, rather than merely replacing the common pool with `newFixedThreadPool` and its default unbounded queue.
5. Collect `Future` results, handle errors, and cancel/wait with timeouts to avoid holding tasks past their deadline.

The `Executors.newFixedThreadPool(4)` example above is a short illustration; in production, when **a bounded queue and admission control** are needed, you can use `ThreadPoolExecutor` with a bounded `BlockingQueue` and an appropriate `RejectedExecutionHandler`. Do not increase workers indefinitely to mask a slow downstream service.

### Option B: Virtual Threads for Blocking I/O (Java 21+)

When each task primarily waits on blocking I/O through APIs supported by the JVM, Java 21+ allows creating **one virtual thread per task**:

```java
// Java 21+ illustrative snippet, assuming ids and blockingCall are already defined.
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    var futures = ids.stream()
            .map(id -> executor.submit(() -> blockingCall(id)))
            .toList();

    for (var future : futures) {
        System.out.println(future.get());
    }
}
```

This is an **illustrative snippet**, not a standalone program; it uses Java 21+ APIs and requires `ids`, `blockingCall`, and exception handling to be provided. When a virtual thread waits on JDK-supported I/O, the carrier platform thread can be released to run other work. Compared to occupying a small number of parallel stream workers, this approach is better suited for many predominantly waiting workloads.

**However, virtual threads do not make external services faster.** Use a `Semaphore` or connection pool to limit concurrent operations against the target resource, and add backpressure to bound the total number of accepted tasks. Do not pool virtual threads just to maintain a fixed number of virtual threads; executors like `newVirtualThreadPerTaskExecutor()` create a virtual thread **per task** and do not reuse them like fixed pool workers.

### Option C: Asynchronous / Non-Blocking APIs When Supported by the System

Use true async I/O (for example, Java networking APIs that support asynchronous operations) so that a waiting request **does not occupy a worker platform thread like a blocking call**. When combining with `CompletableFuture`:

- `CompletableFuture.supplyAsync(task)` **without an explicit executor** typically still uses the common pool; if `task` is blocking I/O, it can continue to cause common pool contention.
- `supplyAsync(task, dedicatedExecutor)` moves the **blocking task** to the specified executor, though the blocking call itself still occupies a worker of that executor.
- A **truly asynchronous** I/O API that returns a future upon initiating I/O may behave differently in thread usage; check the specific API contract rather than inferring behavior solely from the `CompletableFuture` return type.

You do not need to rewrite all code to be non-blocking if synchronous APIs + virtual threads meet your latency and throughput goals. Choose based on your operational targets and Java ecosystem.

## 7. Should You Use ForkJoinPool.ManagedBlocker?

`ForkJoinPool.managedBlock(...)` allows code to **declare a potentially blocking operation** to `ForkJoinPool`, so the pool *may* allocate a compensating worker appropriately when blocked. This is an advanced API useful when directly building fork/join tasks and managing waiting.

However:

- `ManagedBlocker` requires implementing both `isReleasable()` and `block()` strictly according to contract; you cannot simply drop an arbitrary I/O call into `map()` and assume compensation happens automatically.
- Compensation **does not make remote services infinite** and does not guarantee that all bottlenecks disappear.
- This style of blocking support may fit a specific library, but is usually harder than **offloading I/O to a dedicated executor** or using virtual threads/async I/O at the application level.
- Writing an ad-hoc `ManagedBlocker` for every HTTP call just to keep forcing blocking I/O into a parallel stream is discouraged.

## 8. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Calling `parallelStream()` makes all I/O run faster." | It can only increase concurrency within the pool's limits; waiting on I/O still consumes a worker platform thread. |
| "`ForkJoinPool` always compensates with enough workers for blocking I/O." | There is no guarantee for blocked I/O or unmanaged synchronization. |
| "All work runs on common-pool workers." | The calling thread can also participate; execution details are not fixed per element. |
| "Using `CompletableFuture.supplyAsync` avoids the common pool by default." | The default overload can still use the common pool; you must consider both the executor and the actual I/O API. |
| "Switching to a 1000-thread pool eliminates bottlenecks." | Usually it just shifts the bottleneck to the database, network, RAM, connections, or queues. |
| "Low CPU proves the application is healthy." | Low CPU combined with many waiting workers can be a sign of an I/O bottleneck or starvation. |
| "Use `parallel()` for every map/filter." | For small, short tasks, tasks with side effects, or ordering requirements, overhead and contention can make it slower than sequential execution. |
| "Virtual threads make each individual request faster." | Virtual threads primarily improve scalability for many concurrently waiting tasks, not the latency of a single network call. |

## 9. How to Choose in Practice

- **CPU-bound, independent, sufficiently large workloads:** `parallelStream()` can be a good fit. Measure on real data; watch out for ordering, shared mutable state, and split/merge overhead.
- **Heavy blocking I/O:** Offload to an I/O-oriented concurrency mechanism with explicit resource limits: a dedicated executor, virtual-thread-per-task (Java 21+), or a truly async API.
- **Mixed CPU and I/O:** Separate into stages. Do not place slow remote calls directly inside a CPU-oriented `map()` intended to run on the common pool.
- **External resources with quotas:** Regardless of approach, you still need real request/connection limits, timeouts, controlled retries, and backpressure.
- **Measure performance:** Observe throughput, percentile latency, I/O wait time, queue depth, pool/connection metrics, CPU, and thread dumps; measure with warm-up and a representative load environment.

**Key takeaway:** Parallel streams are well-suited for **splitting computation**; blocking I/O makes workers **wait instead of compute**. If too many workers wait at once, the pool may no longer have enough resources to execute other work. Choose a separate I/O coordination mechanism and properly bound the target resources.

## Official References

- [Java SE 21 API — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, common pool, worker adjustment limits during unmanaged blocking, `ManagedBlocker`.
- [Java SE 21 API — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): pipelines, parallel execution, ordering, and requirements to avoid interference/side effects.
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default asynchronous execution facility and overloads accepting an executor.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): blocking I/O tasks on virtual threads, resource efficiency, and concurrency limits.
