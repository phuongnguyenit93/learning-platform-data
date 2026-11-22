# CPU-bound and I/O-bound: Choosing an Execution Strategy in Java

When handling concurrency in Java, the first question to answer is: **does the task spend most of its time computing on the CPU, or mostly waiting for an external resource?** This characteristic determines the number of workers, the API model, load-limiting mechanisms, and the metrics to measure. This article focuses on Java in general (threads, executors, I/O, virtual threads); Spring-specific mechanisms are covered in the corresponding chapter.

## 1. Distinguishing CPU-bound, I/O-bound, and Mixed Workloads

**CPU-bound**: most of the task's useful time is spent on CPU computation, such as data compression, hashing, image processing, numerical algorithms, or parsing large data already in RAM. If the CPU is already maximally busy, increasing the number of threads does not increase the number of CPU operations executed simultaneously; too many runnable threads also increase context-switching and cache overhead.

**I/O-bound**: the task spends a lot of time waiting for external operations to complete, such as disk reads/writes, database queries, waiting for HTTP responses, or waiting on sockets. With blocking I/O and traditional platform threads, a thread may be held while waiting even though it is not using the CPU to compute that request. Allowing many tasks to wait concurrently usually increases throughput, but connection, quota, heap, and downstream limits cannot be ignored.

**Mixed workload**: phases have different characteristics. For example, receiving an image (waiting on network) → decoding/resizing (CPU) → uploading to storage (waiting on network). You should not label the entire application as CPU-bound or I/O-bound once and for all; classify **each phase** and identify the bottleneck.

| Symptom | Possibility | Needs verification with |
| --- | --- | --- |
| CPU near limit, many runnable threads, increasing pool size does not improve throughput | CPU-bound | CPU profiler, CPU quota, task granularity, contention |
| CPU still idle, requests wait long on socket/DB/disk | I/O-bound | tracing latency, I/O metrics, connection pool |
| Low CPU but slow system | Waiting on I/O, locks, queues, or rate limits | thread dump, lock contention, queue depth |
| High CPU and many slow requests | Mixed workload or overload across multiple resources | measuring CPU time, wait time, and each phase |

Be careful with `Thread.State`: `WAITING`/`TIMED_WAITING` does not always mean I/O; a thread may be waiting on a lock, `Future.get()`, or `Thread.sleep()`. `BLOCKED` means waiting for a monitor lock, which is not automatically synonymous with blocking network I/O. Do not draw conclusions from a single thread dump alone.

## 2. Time, Throughput, and Concurrency Model

Let `C` be the useful CPU time of a task, `W` be the wait time, and `T ≈ C + W` before accounting for queue time. A large `C/T` indicates computation dominates; a large `W/T` indicates waiting dominates. This is a mental model, not an automatic formula for choosing the number of threads.

- **Parallelism:** the number of tasks actually processed simultaneously by the CPU, limited by physical/virtual CPU capacity and the allocated CPU quota.
- **Concurrency:** the number of tasks making progress interleaved or simultaneously, including tasks waiting on I/O. Concurrency can be many times larger than parallelism.
- **Latency:** the time from when a task is received until it finishes, including queue wait time. **Throughput:** the number of tasks completed per second.
- **Tail latency:** p95/p99 shows the slow requests; higher throughput does not mean latency remains good.

**Little’s Law** applies when the system is stable: `L = λ × R`, where `L` is the average number of tasks in the system, `λ` is throughput (tasks/second), and `R` is average time (seconds). If the target is 100 requests/second and each request takes an average of 0.2 seconds, on average about 20 concurrent requests are needed in the system. This is an estimate of the number of in-flight requests, **not a mandate to set thread pool = 20**; connection limits, latency variance, rate limits, and queues still determine the safe level.

For CPU-bound work, Amdahl's law explains that the non-parallelizable portion of an algorithm limits the maximum speedup. Creating many threads does not increase the number of cores, nor does it eliminate locks, cache contention, or task distribution overhead. For I/O-bound work, concurrency helps hide wait time, but too many requests can slow down downstream services and create an overload feedback loop.

## 3. Choosing an Execution Model in Java

| Scenario | Usually Reasonable Choice | Things to Watch Out For |
| --- | --- | --- |
| Heavy computation across many independent datasets | Fixed-size `ExecutorService` close to available CPUs | Benchmark task granularity, contention, memory bandwidth |
| Divide-and-conquer algorithms, uneven subtasks | `ForkJoinPool` if genuinely suitable | Work-stealing has overhead; avoid unmanaged long blocking |
| Blocking I/O on Java 17 | Finite platform thread pool, bounded queue/admission control | One thread is held while waiting; limit threads, memory, connections |
| Many independent blocking I/O calls on Java 21+ | `Executors.newVirtualThreadPerTaskExecutor()` + I/O limits | Cheaper than platform threads when waiting; does not make CPU faster |
| APIs that already provide non-blocking/asynchronous I/O | `HttpClient.sendAsync`, appropriate NIO/async APIs | Callbacks/completion, error handling, timeouts, executor for CPU phases |
| A few very small tasks | Run sequentially | Avoid scheduling and synchronization overhead |
| I/O → CPU → I/O pipeline | Regulate each phase separately | Avoid blocking on completion/event-loop threads; do not saturate the CPU pool |

Traditional **platform threads** map to OS threads and consume more resources when there are many waiting requests. **Virtual threads (stable since Java 21)** are scheduled by the JVM onto carrier platform threads; when entering a compatible blocking operation, the carrier can be used for another task. Java code can still be written sequentially, but virtual threads do not create extra CPU cores and do not increase database/API quotas.

**Asynchronous I/O** means the API returns a future result or callback so the calling thread can do other work while waiting for I/O. `CompletableFuture` by itself does not turn a blocking call into a non-blocking one: wrapping blocking code in `supplyAsync` still needs a thread to run. Async tasks without an explicit executor usually use `ForkJoinPool.commonPool()`; piling long blocking I/O onto the common pool can affect other work.

## 4. CPU-bound Example on Java 17: Fixed Pool

The following standalone example splits the problem of counting prime numbers from 2 to 100 into four segments. The small dataset is only to illustrate the structure; **do not use the runtime results to prove that multi-threading is faster**.

Create `CpuBoundExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CpuBoundExample {
    private static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int d = 2; (long) d * d <= n; d++) {
            if (n % d == 0) return false;
        }
        return true;
    }

    private static int countPrimes(int from, int to) {
        int count = 0;
        for (int n = from; n <= to; n++) {
            if (isPrime(n)) count++;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        int workers = Math.min(4, Runtime.getRuntime().availableProcessors());
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int start = 2; start <= 100; start += 25) {
                final int from = start;
                final int to = Math.min(start + 24, 100);
                futures.add(pool.submit(() -> countPrimes(from, to)));
            }

            int total = 0;
            for (Future<Integer> f : futures) total += f.get();
            System.out.println("So nguyen to tu 2 den 100: " + total);
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac CpuBoundExample.java
java CpuBoundExample
```

Exact stdout:

```text
So nguyen to tu 2 den 100: 25
```

`submit` submits a `Callable` to the executor and returns a `Future`; `get()` waits and returns the result or throws `ExecutionException` if the task fails. Summing results in list order ensures the result does not depend on worker execution order. `shutdown()` stops accepting new tasks; in the example, all `get()` calls have completed before shutdown. The worker count from `availableProcessors()` is only a starting point: in containers/shared environments, you must verify the actual allocated CPU and measure throughput/latency. For small problems or few tasks, sequential execution can be faster due to overhead.

**Production note:** `Executors.newFixedThreadPool` has an unbounded queue in the standard implementation. A fixed pool does **not** automatically limit the number of tasks waiting in the queue. For continuous request sources, use a bounded queue, backpressure, or admission control.

## 5. I/O-bound Example on Java 17: Bounded Platform Thread Pool

To run offline and keep output deterministic, the code uses `Thread.sleep(50)` to **simulate wait time**, not a real I/O operation and not for network/disk benchmarking. In a real application, this spot could be a DB query or a blocking HTTP call with configured timeouts.

Create `BlockingWaitExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingWaitExample {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 8; i++) {
                final int id = i;
                futures.add(pool.submit(() -> {
                    Thread.sleep(50); // Simulate I/O wait time only
                    return "ok-" + id;
                }));
            }

            for (Future<String> f : futures) f.get();
            System.out.println("Da hoan thanh " + futures.size() + " tac vu");
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac BlockingWaitExample.java
java BlockingWaitExample
```

Stdout:

```text
Da hoan thanh 8 tac vu
```

Four platform threads process eight tasks; while a thread is waiting on `sleep`, it does not process other tasks in the pool. Increasing the number of threads can improve throughput if the workload is mostly waiting on I/O, but it is constrained by stack memory, OS threads, connection pools, rate limits, and downstream services. `Future.get()` in the example has no timeout to keep the flow simple; production code must set timeouts on the I/O client and can use `get(timeout, unit)` for caller-side deadlines. A `get` timeout does **not automatically cancel** the running operation.

## 6. Java 21+: Virtual Threads for Blocking I/O

Virtual threads help handle many blocking calls without dedicating a separate platform thread to each waiting request. The following example runs on Java 21+ without enabling preview features.

Create `VirtualThreadWaitExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadWaitExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 20; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(50); // Simulate blocking I/O only
                    return "ok-" + id;
                }));
            }

            for (Future<String> f : futures) f.get();
            System.out.println("Da hoan thanh " + futures.size() + " tac vu");
        }
    }
}
```

```bash
javac VirtualThreadWaitExample.java
java VirtualThreadWaitExample
```

Stdout:

```text
Da hoan thanh 20 tac vu
```

`newVirtualThreadPerTaskExecutor()` creates a virtual thread per task. `try` manages the executor lifecycle, closing and waiting for completion when exiting the scope. This is still a wait simulation; it is not real I/O benchmark evidence. If you replace `sleep` with heavy CPU computation, virtual threads do **not** allow 20 tasks to compute simultaneously on 20 cores when the machine only has a few cores.

**You do not need a small virtual thread pool to “save threads”.** Instead, you must limit the number of requests to a specific resource: connection pools, semaphores, rate limiting, and the number of pending tasks. Virtual threads still consume heap for stack/data per task; having tens of thousands of waiting requests can still cause OOM or overload downstream services. On some older JDKs (especially Java 21–23), blocking while holding a `synchronized` monitor can pin the carrier platform thread; newer JDKs have improved this behavior. Use JFR and profiling on the runtime/libraries being deployed to verify, especially when libraries perform blocking I/O inside critical sections.

## 7. When Asynchronous I/O Is Already Available

`java.net.http.HttpClient` has been available since Java 11. `sendAsync` returns `CompletableFuture<HttpResponse<T>>` so the caller does not have to wait synchronously until the HTTP response arrives. The following is a **snippet**, assuming the `endpoint` variable has type `java.net.URI` and points to a valid URI; this is not a standalone program and has no fixed stdout:

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(endpoint)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> response =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Integer> length =
        response.thenApply(r -> r.body().length());
```

Required imports: `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`, and `java.util.concurrent.CompletableFuture`. `thenApply` transforms the result once the response is available. If the body processing step is CPU-intensive, use `thenApplyAsync(..., cpuExecutor)` to offload it to a CPU executor. Calling `join()`/`get()` directly on the completion thread or event loop can negate the non-blocking benefit. You must handle errors with `handle`/`exceptionally`, timeouts, and chain cancellation.

**Async or virtual threads?** If the API is already non-blocking and the architecture uses `CompletableFuture` pipelines well, async makes sense. If most libraries are blocking and you are running Java 21+, virtual threads keep code sequential with clear `try/catch` and resource management. Choose based on existing APIs and workloads; both must control load.

## 8. Load Limiting: Threads, Queues, Connections, and Deadlines

Two things must be regulated separately: (1) the number of tasks **currently active/waiting on resources**, and (2) the number of tasks **queued waiting to be executed**. Using a fixed pool with an unbounded queue can lead to very long latency, growing memory usage, and eventual overload. With platform threads, `ThreadPoolExecutor` + a bounded `ArrayBlockingQueue` and an intentional rejection policy help limit accepted work. `CallerRunsPolicy` sometimes provides backpressure, but it can block the caller and trigger cascading congestion; you must inspect the request path.

You can refer to a heuristic for blocking I/O on platform threads: `N_threads ≈ N_cpu × U_target × (1 + W/C)`, where `U_target` is the target CPU utilization, `W` is wait time, and `C` is CPU compute time. Use this only as a **starting point for experimentation**, not an absolute safe limit, because context switching, locks, connection pools, queues, and memory can dominate. For CPU-bound work, start with a worker count close to effective CPUs and measure. With virtual threads, replace the question “how many threads in the pool?” with “at most how many I/O calls can use this resource?”.

Example **snippet** limiting to at most 20 concurrent blocking I/O calls when using virtual threads:

```java
Semaphore permits = new Semaphore(20);

try {
    permits.acquire();
    try {
        // Perform a blocking I/O call with a timeout here.
    } finally {
        permits.release();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Cancel or report appropriate status.
}
```

Requires importing `java.util.concurrent.Semaphore`; the I/O body is supplied by the application. `Semaphore` limits execution **after acquiring a permit**, not the number of virtual threads waiting for a permit. If input arrives continuously without bound, you also need a bounded request queue, a limit on waiting tasks, admission control, or rate limiting at the source.

For example, a DB pool only has 30 connections: even if you can create 10,000 virtual threads, 10,000 queries cannot hold connections simultaneously if the pool is capped at 30. When you see high connection wait times, optimize queries, transactions, workload, and load levels before increasing concurrency.

## 9. Timeouts, Cancellation, Errors, and Lifecycle

- **Timeouts on the I/O client**: configure connect/read/request timeouts or deadlines depending on the API; avoid requests waiting indefinitely. `Future.get(timeout, unit)` only limits how long the caller waits; it does not stop the running task.
- **Cancellation**: `Future.cancel(true)` can interrupt the running thread, but the task must cooperate and I/O APIs have their own cancellation semantics. Do not assume an external operation has rolled back when the Java task is cancelled.
- **Interrupts**: when catching `InterruptedException` without rethrowing, typically restore it with `Thread.currentThread().interrupt()` and then terminate/coordinate cancellation appropriately. Do not swallow interrupts.
- **Errors from tasks**: `Future.get()` wraps errors in `ExecutionException`; `CompletableFuture.join()` can wrap them in `CompletionException`. Log the root cause and correlation id, avoiding logging only the wrapper.
- **Shutting down executors**: stop accepting tasks, wait with a deadline, and use `shutdownNow()` when policy requires. Manage executor lifecycles in the appropriate component; do not create a platform-thread executor per request and leave it unmanaged.
- **Shared data**: use immutable objects, clear ownership, concurrent collections, or proper synchronization to avoid data races. Increasing/decreasing thread counts does not solve deadlocks, race conditions, or lock contention.

## 10. How to Measure and Make Data-Driven Decisions

1. **Define goals**: throughput, p95/p99 latency, CPU cost, memory, tail latency, or errors when downstream is slow? Know container/VM CPU limits, connection limits, and rate limits.
2. **Capture a baseline under representative load**: requests/sec, average and p95/p99 latency, CPU usage, heap/GC, queue depth, active threads, active connections, and timeouts/errors.
3. **Locate the bottleneck**: Java Flight Recorder (JFR), CPU profiler, thread dumps (`jcmd <pid> Thread.print`), application tracing, and I/O metrics. Measure CPU time and wall-clock time for each phase; low CPU can be caused by locks, I/O, or throttling.
4. **Test each strategy**: sequential vs. fixed CPU pool for compute tasks; bounded platform-thread pool/virtual threads/async for I/O. Keep data and downstream conditions equivalent; increase concurrency in a controlled way.
5. **Observe the breaking point**: if adding concurrency does not increase throughput while queues, p99, timeouts, or memory grow, the system has hit a bottleneck. Reduce load or improve the corresponding resource/algorithm.
6. **Verify after deployment**: load spikes, downstream slowdowns, client disconnects/cancellations, graceful shutdown; set alerts on queue wait, saturation, errors, and resource exhaustion.

`Runtime.getRuntime().availableProcessors()` in modern JVMs generally reflects the processor configuration visible to the runtime, which may be affected by cgroups/containers; do not treat it as a performance guarantee by itself. CPU-bound benchmarks must be large enough that task-creation overhead does not dominate, and must also measure memory/cache contention.

## 11. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Creating hundreds of threads for CPU-bound work with only a few cores | Context switching/cache contention, slower execution | Size CPU pool close to CPU capacity, measure and tune |
| Arbitrarily running long blocking I/O in `ForkJoinPool.commonPool()` | Starvation and hard-to-control queues | Use a dedicated I/O executor, virtual threads, or async APIs |
| Believing virtual threads make compute algorithms faster | CPU remains bottlenecked, too many runnable tasks | Limit CPU parallelism, optimize the algorithm |
| Believing virtual threads mean unlimited downstream capacity | Exhausted DB connections, rate limits, sockets/heap | Semaphores, connection caps, queue bounds, timeouts |
| Using `Thread.sleep` as an HTTP/DB benchmark | Simulated measurements, ignoring downstream and tail latency | Benchmark real I/O under operational conditions |
| Looking only at average throughput | Missing p99, queues, and errors | Monitor tail latency, queues, saturation, errors |
| `get()` without a deadline, swallowing interrupts | Hung requests and difficult shutdowns | Proper timeouts, cancellation, and propagation |
| Creating an executor and never closing it | Thread/resource leaks | Clear lifecycle management |

## 12. Four Applied Scenarios

**A. Hashing one million records in RAM.** Mostly CPU-bound: split into independent batches, use a worker count close to useful CPUs, and measure batch size and memory pressure. Virtual threads do not speed up hashing.

**B. Aggregating results from 10 HTTP APIs.** Mostly waiting on I/O: if using a blocking client on Java 21+, virtual threads + per-call timeouts + per-API concurrency limits are a readable option. If the API already supports `sendAsync`, an asynchronous pipeline is also suitable. Do not exceed service quotas.

**C. Download image → resize → upload.** Download/upload are I/O-bound; resize is CPU-bound. Regulate each phase and offload the resize step to a CPU executor; avoid heavy image processing directly on the event-loop/completion thread. Consider streaming so large files are not kept entirely in heap.

**D. Database queries with a 30-connection pool.** Increasing platform/virtual threads does not create more connections. If queries are slow, measure connection wait time, SQL time, transactions, indexes, and DB throughput; increase concurrency only when the DB and pool can actually sustain it.

## 13. Pre-Design Final Checklist

- Is each phase **computation**, **waiting on I/O**, or **waiting on locks/queues**? Do you have profiles and measurements?
- Java 17 or Java 21+? Does the API support true non-blocking I/O or just wrap a blocking call in `CompletableFuture`?
- How much CPU is actually allocated? How many concurrent connections/requests does downstream allow?
- How are active tasks and pending queues bounded? Under overload, will the system wait, reject, or shed load?
- Are timeouts, error propagation, cancellation, interrupt handling, and executor shutdown properly implemented?
- Does realistic load testing improve throughput **and** p95/p99 without increasing errors, queues, memory, or saturation?

**Guiding principle:** CPU-bound → limit parallel computation to CPU capacity; I/O-bound → use concurrency to hide wait time within resource limits; Java 21+ virtual threads make large-scale blocking I/O code clear; existing non-blocking APIs can leverage async. For mixed workloads, split into phases and measure each part.