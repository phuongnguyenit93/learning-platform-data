# Thread Pools, Virtual Threads, and the Limits of Changing the Execution Model

When upgrading a Java application to a modern JDK, development teams often want to replace legacy `ExecutorService` instances, worker pools, or request-per-thread models with **virtual threads**. This is a significant step forward in Java concurrency: an application can maintain a very large number of tasks waiting on I/O without creating a corresponding number of expensive **platform threads** managed by the operating system.

However, **virtual threads are not an automatic speedup solution**. Replacing `Executors.newFixedThreadPool(100)` with `Executors.newVirtualThreadPerTaskExecutor()` does not give the CPU more cores, make the database connection pool expand infinitely, or allow downstream APIs to handle more requests. Nor does it automatically fix race conditions, deadlocks, overly long transactions, missing timeouts, overload, or how `ThreadLocal` is managed.

This article belongs to the **Java Advance Compatibility Migration** topic, **JVM and Performance** group, focusing on how traditional thread pools operate, the nature of virtual threads, cases that benefit, limits that must be respected, and a migration path that can be measured and rolled back.

## 1. Three Concepts That Are Often Conflated

Before replacing an executor, it is necessary to distinguish:

- **Concurrency:** the number of tasks currently able to make progress, including waiting on I/O.
- **Parallelism:** the number of tasks actually running on the CPU at the same point in time, depending on cores and processing resources.
- **Throughput:** the number of requests/tasks completed in a unit of time.

For example, an HTTP server has 200 requests in progress, but 180 of them are waiting on the database and only 20 are actually using CPU. Concurrency may be 200, but CPU parallelism is not 200.

Virtual threads primarily help an application **maintain high concurrency with lower thread overhead**, especially in workloads with a large amount of waiting time. They do not equate to increasing CPU processing capacity or expanding downstream resources that are already saturated.

### 1.1. Platform Thread

A platform thread is a `java.lang.Thread` tied to an operating system thread under the traditional model. Creating a very large number of platform threads incurs significant stack memory, scheduling, and resource management costs.

Example:

```java
Thread worker = new Thread(() -> {
    performBlockingOperation();
});
worker.start();
```

With thousands or tens of thousands of I/O tasks, allocating a dedicated platform thread for each request can become costly and difficult to control.

### 1.2. Thread Pool

A thread pool reuses a set of threads to run multiple tasks. For example, `newFixedThreadPool(32)` creates up to approximately 32 worker platform threads operating according to the pool configuration.

Tasks exceeding the pool's capacity must wait in a queue or hit a rejection policy, depending on the executor. A finite thread count both limits resource consumption and can become a bottleneck when threads spend most of their time waiting on the network/database.

### 1.3. Virtual Thread

A virtual thread is an implementation of `Thread` managed by the JDK with significantly lower overhead for many blocking I/O waiting cases. Many virtual threads can be executed across a smaller set of **carrier platform threads**.

A virtual thread is still a `Thread`: it has a stack trace, interruption, a name, the ability to use `ThreadLocal`, and many familiar APIs. However, its scheduling mechanism, memory footprint, and behavior when blocking differ from a platform thread.

**A virtual thread should be understood as a per-task unit of execution**, not a cheap worker platform thread to be kept alive and reused in a pool.

## 2. Virtual Thread Support Timeline Across JDKs

| JDK | Status | Migration Implications |
|---|---|---|
| Java 8–17 | No virtual threads in standard Java SE | Use platform threads, executor pools, async/reactive, or concurrency libraries |
| JDK 19 | Virtual threads in preview (JEP 425) | Mainly for experimentation, requiring appropriate preview flags |
| JDK 20 | Continued in preview (JEP 436) | Should not treat preview APIs/behavior as a stable contract |
| JDK 21 | Virtual threads become a final feature (JEP 444) | Can use `Thread.ofVirtual()` and `Executors.newVirtualThreadPerTaskExecutor()` in supported production code |
| JDK 24 | JEP 491 changes pinning behavior caused by `synchronized` | Must distinguish pinning diagnostics before and after JDK 24 |
| Newer JDKs | Depends on release, updates, and tooling | Check documentation/observability of the actual JDK; do not copy workarounds verbatim from Java 21 |

For example, documentation uses Java 21 as a reasonable stable baseline for virtual threads. This does not mean every framework, driver, or monitoring agent running on JDK 21 already handles virtual threads optimally.

### 2.1. Virtual Threads Are Not Equivalent to Preview Structured Concurrency

Some documentation simultaneously mentions **structured concurrency** or **scoped values**. These are topics related to managing lifetime and context, but their stability level/APIs depend on each JDK release.

It should not be implicitly assumed that installing JDK 21 enables using all of the latest structured concurrency examples without enabling preview or updating APIs. This article prioritizes the final virtual threads APIs in JDK 21.

## 3. How It Works: Virtual Threads and Carrier Threads

Conceptual model:

```text
Request A ---> Virtual Thread A ----\
Request B ---> Virtual Thread B -----\
Request C ---> Virtual Thread C ------> Scheduler ---> Carrier platform threads
Request D ---> Virtual Thread D -----/                   (finite count)
Request E ---> Virtual Thread E ----/
```

When a virtual thread is executing Java code, it is **mounted** onto a carrier thread. When it performs a blocking operation for which the JDK supports unmounting, the virtual thread can detach from the carrier; the carrier continues running another virtual thread.

When I/O becomes ready, the virtual thread is scheduled to resume.

Key points:

1. A virtual thread does not necessarily use the same carrier for its entire lifetime.
2. A virtual thread can wait for a long time without holding a carrier for the entire duration of the wait, if the blocking operation supports unmounting.
3. When executing on CPU, a virtual thread still needs a carrier/platform thread to execute instructions.
4. The scheduler does not create additional CPU cores; the number of tasks actually running in parallel remains finite.
5. Not every type of blocking, native call, or framework interaction exhibits the same unmounting behavior.

### 3.1. When Many Tasks Wait on I/O

Suppose 5,000 requests each call an API that takes 200 ms, while the CPU only needs a few milliseconds to process before and after the response.

With a finite thread pool, 200 workers may have to wait on I/O and the remaining requests wait in a queue. Virtual threads can reduce the situation where platform threads are occupied during waiting time.

However, 5,000 requests **can still overload the downstream API**. The execution model does not automatically create rate limits, backpressure, or a connection pool.

### 3.2. When Tasks Are CPU-Intensive

If 5,000 requests simultaneously hash large amounts of data, process images, or perform CPU-bound calculations, virtual threads do not make all of them run in parallel. The scheduler is still bounded by CPU and context-switching overhead.

In CPU-bound workloads, a fixed pool sized according to core count and appropriate operational limits is usually easier to control.

## 4. Traditional Thread Pools: Benefits and Limitations

Familiar Java code:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class FixedPoolExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newFixedThreadPool(16)) {

            Future<String> result = executor.submit(() -> {
                Thread.sleep(200);
                return "done";
            });

            System.out.println(result.get());
        }
    }
}
```

The example assumes running on a JDK that supports `ExecutorService.close()`, such as JDK 21. On Java 8/11, `try/finally` and `shutdown()` can be used instead of try-with-resources.

A fixed pool serves two practical purposes:

- **Reusing platform threads**, avoiding continuous creation/destruction.
- **Limiting the number of concurrently running tasks** by worker count.

However, thread pools also have their own problems.

### 4.1. Queues Can Accumulate Too Many Tasks

`Executors.newFixedThreadPool` uses a work queue capable of growing very large under typical conditions. Limiting to 16 workers does not mean the application only holds 16 requests in memory.

If the request arrival rate exceeds the processing rate for an extended period, the queue grows, latency increases, and ultimately heap pressure can result.

When explicit backpressure is needed, `ThreadPoolExecutor` with a bounded queue, a rejection policy, or admission control at the HTTP/message consumer layer can be used.

### 4.2. A Thread Waiting on the Database Still Occupies a Worker

If all 16 workers are waiting on the network or database, new tasks cannot execute immediately even though the CPU may be idle. This is why virtual threads are attractive for traditional blocking I/O applications.

### 4.3. Pools Do Not Guarantee Data Synchronization

Running tasks in a pool does not prevent race conditions. If multiple tasks share a `HashMap`, a mutable field, or a non-thread-safe transaction object, race and visibility issues still exist.

Replacing a pool with virtual threads can make rare concurrency bugs occur much more frequently because the number of concurrent tasks increases.

## 5. How to Create Virtual Threads in Java 21

### 5.1. Creating Directly with `Thread.ofVirtual()`

```java
public final class VirtualThreadExample {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = Thread.ofVirtual()
                .name("inventory-query")
                .start(() -> {
                    System.out.println(Thread.currentThread());
                    System.out.println(
                            "isVirtual = " + Thread.currentThread().isVirtual());
                });

        thread.join();
    }
}
```

With JDK 21, `Thread.ofVirtual()` is a final API. `join()` waits for the virtual thread to finish; if you omit waiting and only create virtual threads in a short `main` program, the process may exit before the task completes.

### 5.2. `newVirtualThreadPerTaskExecutor()`

A more common approach in application code:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class VirtualExecutorExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 0; i < 100; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(100);
                    return "task-" + id;
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
```

Each task accepted by the executor runs on a new virtual thread. This executor is **not a fixed virtual-thread pool** and does not impose a 100/1,000 thread limit the way a fixed pool does.

`ExecutorService.close()` waits for associated tasks to finish according to the API semantics, so timeouts, cancellation, and shutdown must be managed if work could wait indefinitely.

### 5.3. Why Should You Not Create a Virtual-Thread Pool?

Virtual threads are designed to be created per task. Constraining them with a small pool just to “save threads” can cause the application to lose its concurrency advantage when I/O blocks.

For example, creating a fixed-thread executor with a virtual-thread factory (if configured in a supported way) is generally not the recommended solution for request-per-task workloads. If you need to limit **the number of database calls**, limit the database calls themselves using a connection pool, semaphore, rate limiter, or admission control.

**Distinguish resource limits from virtual thread count limits.**

## 6. Comparing the Three Execution Models

| Characteristic | Platform thread-per-request | Fixed platform thread pool | Virtual thread-per-task |
|---|---|---|---|
| Cost when many tasks are waiting | High | Workers are occupied, queue grows | Often significantly lower |
| Ability to manage I/O concurrency | Limited by OS threads | Limited by pool size | Can be very high |
| CPU parallelism | By core count | By core/pool count | Still by core/carrier count |
| Thread reuse | Possibly not | Yes | No need to pool virtual threads |
| Bounded task admission | Must be designed | Possible via queue/rejection | Must be designed separately |
| Ability to use blocking style | Yes | Yes | Yes, with supported I/O |
| Protecting database/remote APIs | Not automatic | Worker count sometimes limits indirectly | Not automatic |
| ThreadLocal risk | Yes | State leak when reusing workers | Creates many per-task states |
| Stack trace observability | Yes | Yes | Yes, though virtual thread count can be very large |
| Suitability for CPU-bound work | Limited | Usually easier to control | Does not inherently create a CPU advantage |

This table should not be treated as a quantitative performance prediction. Actual results depend on I/O wait ratio, latency, connection pool, request size, GC, scheduler, framework, and downstream services.

## 7. Which Workloads Are Suitable for Virtual Threads?

### 7.1. Many Independent Blocking I/O Tasks

Potential scenarios:

- HTTP/gRPC clients using blocking I/O on a supported stack.
- Calling a database via a blocking JDBC API.
- Querying multiple partner APIs.
- Handling request-per-thread in a web server that supports virtual threads.
- Batch tasks that must wait on file/network without needing to hold a platform worker.
- Some message processing systems waiting on long I/O.

The key characteristic is that **waiting time accounts for a high proportion** compared to CPU time.

### 7.2. Readable and Traceable Synchronous Code

A flow:

```java
Order order = repository.load(orderId);
Price price = pricingClient.getPrice(order);
repository.save(order.withPrice(price));
```

can maintain a readable sequential style when executed on a virtual thread, rather than forcing every step to be expressed as a chain of callbacks.

However, synchronous code does not automatically control concurrency, timeouts, and transaction lifetime. These issues still require design.

### 7.3. Virtual Threads Are Not Automatically Better Than Reactive

Reactive and event-loop frameworks can also handle high I/O concurrency efficiently, typically using asynchronous APIs and backpressure built into the programming model.

Migrating a well-functioning reactive system to virtual threads does not guarantee higher performance; it may require rewriting flows, context propagation, and cancellation semantics.

Decisions should weigh **code complexity, the libraries in use, and benchmark results**, rather than being based on “virtual threads are always newer”.

## 8. Cases Where Virtual Threads Do Not Bring Major Benefits

### 8.1. CPU-Bound Tasks

For example, bulk hash computation or data compression:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CpuWorkExample {
    public static void main(String[] args) {
        int cpuCount = Runtime.getRuntime().availableProcessors();

        try (ExecutorService executor =
                Executors.newFixedThreadPool(cpuCount)) {
            for (int i = 0; i < 100; i++) {
                executor.submit(() -> computeHeavyResult());
            }
        }
    }

    private static void computeHeavyResult() {
        // Illustrates a CPU-bound task.
        long total = 0;
        for (long i = 0; i < 10_000_000L; i++) {
            total += i;
        }
        if (total == Long.MIN_VALUE) {
            System.out.println(total);
        }
    }
}
```

This is an illustrative pattern, not a proper microbenchmark. CPU-bound workloads need to be bounded by cores, priority, latency, and memory. Using unbounded virtual threads may merely increase the number of runnable tasks, causing CPU contention and making tail latency hard to control.

### 8.2. Native/JNI Blocking or Unsupported Libraries

Not every blocking operation can unmount a virtual thread from its carrier in the same way. A library calling a native API, holding a native/foreign frame, or using specialized synchronization mechanisms may hold a carrier for a long time or cause other limitations.

The corresponding JDK version and native library/framework must be checked; do not assume all I/O is always “free” when using virtual threads.

### 8.3. Work Bounded by External Services

If a database only allows 50 connections, using 50,000 virtual threads does not turn it into a database supporting 50,000 concurrent queries. The excess virtual threads will wait for connections or wait on a semaphore, consuming memory and lengthening latency.

### 8.4. Tiny Tasks Created Millions of Times

Virtual threads are cheaper than platform threads, but they are not free. Creating a virtual thread for each tiny addition operation can incur scheduling overhead greater than the benefit.

For very fine-grained CPU data processing, using loops, batching, vectorization, or an appropriate parallelism model is usually more effective.

## 9. Backpressure: The Most Important Issue During Migration

A fixed thread pool has a worker limit, so it inadvertently acts as a concurrency limit for certain downstream dependencies. When switching to a virtual-thread-per-task executor, that limit can disappear.

Example before migration:

```text
Fixed pool 32 workers
      |
      v
Database pool 20 connections
```

After migration:

```text
20.000 virtual tasks
      |
      v
Database pool 20 connections
```

20 connections remains the real limit. The number of tasks waiting to borrow a connection can surge sharply when the system receives burst traffic.

### 9.1. Limiting Resources with `Semaphore`

Java 21 example:

```java
import java.util.concurrent.Semaphore;

public final class LimitedRepository {
    private final Semaphore permits = new Semaphore(20);
    private final OrderRepository delegate;

    public LimitedRepository(OrderRepository delegate) {
        this.delegate = delegate;
    }

    public Order load(long id) throws InterruptedException {
        permits.acquire();
        try {
            return delegate.load(id);
        } finally {
            permits.release();
        }
    }
}
```

`OrderRepository` and `Order` are illustrative domain types, not Java SE classes. This pattern shows a semaphore protecting the database call region and always releasing the permit in `finally`.

Advantage: many virtual threads can wait on a permit without needing a corresponding number of platform threads. However, **a semaphore does not automatically limit the number of requests already admitted into the system**. If 1 million requests are accepted at once, there can still be a very large number of tasks waiting on the semaphore.

### 9.2. Limits Are Needed at the Work Admission Point

For production, the following are also needed:

- HTTP server admission control and concurrent request limits.
- Bounded queues on message consumers/job dispatchers.
- Rate limiting for partner APIs.
- Circuit breakers and bulkheads per downstream dependency.
- Connection pool sizing and connection acquisition wait timeouts.
- Request deadlines and cancellation.
- Mechanisms to return `429`/`503` or `Retry-After` on overload.

Virtual threads do not replace these mechanisms. **Backpressure should live at the request ingress boundary and around each scarce resource**, rather than solely limiting the number of carrier threads.

### 9.3. Timeouts at Every Wait Point

A semaphore or connection pool can wait for a very long time. Example of bounding permit acquisition time:

```java
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class TimedAdmission {
    private final Semaphore permits = new Semaphore(20);

    public void execute(Runnable action) throws InterruptedException {
        boolean acquired = permits.tryAcquire(
                Duration.ofSeconds(2).toMillis(),
                TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new IllegalStateException("Hệ thống đang quá tải");
        }

        try {
            action.run();
        } finally {
            permits.release();
        }
    }
}
```

This pattern illustrates bounding the wait time for a permit; it does not automatically apply a timeout to `action.run()` itself. Timeouts are still needed at the database, HTTP client, and overall request deadline.

## 10. Little's Law and Real Capacity

For a system in a steady state, Little's Law describes the relationship:

\[
L = \lambda \times W
\]

Where:

- \(L\): the average number of items currently inside the system.
- \(\lambda\): the steady-state completion/arrival rate of items.
- \(W\): the average time each item spends in the system.

Illustrative example: if a system completes an average of 500 requests/second and each request stays in the system for 0.2 seconds, the average number of concurrent requests is approximately 100.

If a downstream slows from 200 ms to 2 seconds while the arrival rate does not decrease, the number of waiting requests can increase roughly tenfold under the corresponding steady-state conditions. Virtual threads can reduce platform thread overhead while waiting, but **they do not shorten downstream latency**.

If the arrival rate exceeds the sustainable service rate, queues can grow without bound whether using platform or virtual threads. In that case, load shedding, rate limiting, downstream scaling, or architectural adjustments are required.

## 11. Pinning: You Must Distinguish JDK 21 from Newer JDKs

**Pinning** is a situation where a virtual thread is blocking but cannot detach from its carrier through the normal mechanism. This can reduce benefits when the number of waiting virtual threads is high.

However, the causes of pinning **change across JDK generations**.

### 11.1. JDK 21–23: `synchronized` Can Cause Pinning

In JDK 21 and early releases of virtual threads, a virtual thread executing inside a `synchronized` block/method and blocking on certain operations could hold onto its carrier thread.

Example:

```java
public final class LegacyClient {
    private final Object lock = new Object();

    public String loadData() throws InterruptedException {
        synchronized (lock) {
            // Simulate blocking I/O inside a monitor:
            Thread.sleep(300);
            return "data";
        }
    }
}
```

On JDKs subject to this limitation, blocking inside a monitor can cause pinning. The problem becomes more severe if thousands of requests do the same concurrently.

Approaches when still on JDK 21–23:

1. Identify `synchronized` sections that actually contain long blocking operations.
2. Shorten critical sections while preserving thread safety.
3. Avoid holding a monitor while performing I/O calls if possible.
4. When appropriate, consider a lock with a more suitable mechanism such as `ReentrantLock`.
5. Test for race conditions, fairness, and performance before replacing locks.

**Do not mechanically replace every `synchronized` with `ReentrantLock`.** A monitor protecting a very short critical section does not necessarily cause problems, whereas changing locks can alter semantics and introduce bugs.

### 11.2. JDK 24: Major Change in JEP 491

JEP 491 improves virtual thread behavior with `synchronized` monitors, eliminating synchronization-induced pinning in the corresponding mechanism. Therefore, the advice “every blocking call inside `synchronized` pins the carrier” **is no longer generally true from JDK 24 onward**.

This does not mean every source of pinning or hard-to-manage blocking disappears. Native/foreign interactions and certain specific runtime situations still need to be verified against the actual JDK and libraries.

During migration, state explicitly:

```text
Runtime JDK:
  - 21/22/23: evaluate monitor pinning under the legacy mechanism
  - 24+: review JEP 491 changes and remaining limitations
```

Do not copy Java 21 diagnostics verbatim to every newer JDK.

### 11.3. `synchronized` Can Still Cause Contention

Even when a monitor no longer pins the carrier, `synchronized` still guards a region so that only one thread enters at a time. If an application locks an entire database operation under the same monitor, throughput is still serialized due to lock contention.

**Reducing pinning does not mean removing the logical constraint of a critical section.**

## 12. Observing Pinning and Virtual Threads

### 12.1. JFR (Java Flight Recorder)

JFR supports observing JVM behavior with overhead designed for profiling/production diagnostics depending on configuration level. On JDKs that have the corresponding events, events related to virtual threads, pinning, scheduling, and allocation can be used.

Example of starting a short profile recording:

```bash
java \
  -XX:StartFlightRecording=filename=recording.jfr,duration=60s,settings=profile \
  -jar app.jar
```

Actual event contents depend on the JDK version and recording configuration. Do not conclude “no `jdk.VirtualThreadPinned` event definitely means there are no concurrency issues”: the event may be disabled, have a threshold, or have changed semantics across JDKs.

### 12.2. `jdk.tracePinnedThreads` on Early JDKs

Some early JDKs can use:

```bash
java -Djdk.tracePinnedThreads=full -jar app.jar
```

to help locate pinning situations caused by monitor/native frames. This is a version-specific diagnostic tool: on newer JDKs after pinning changes, the property may no longer have the same meaning as before.

Rely on diagnostic tools and JFR appropriate for the **running JDK**, rather than simply enabling a property and treating the absence of output as proof of safety.

### 12.3. Thread Dumps and `jcmd`

Modern JDKs support ways to capture thread dumps suitable for virtual threads, for example using `jcmd`:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Replace `<pid>` with the actual PID of the Java process; this is an example command, and syntax/support depends on the JDK. The dump file can become very large when the system has many virtual threads.

For production environments requiring tracing, limit dump capture frequency, protect sensitive information, and choose tools/formats suitable for the number of virtual threads.

### 12.4. Metrics to Measure

- Request throughput and p50/p95/p99 latency.
- CPU utilization, CPU throttling, and available processors.
- Heap, GC pauses, allocation rate, and memory footprint.
- Virtual thread count or active state according to supported tooling.
- Carrier utilization and signs of scheduling contention where observable.
- Database connection pool active/idle/waiters/timeouts.
- HTTP client pool, outbound request concurrency, and retry rate.
- Queue depth, rejected requests, timeouts, and cancellation.
- Pinning or monitor contention if the JDK provides corresponding events.
- Downstream error rate, rate limits, and circuit breaker state.

A figure such as “having 100,000 virtual threads” does not by itself prove whether a system is healthy or unhealthy. It must be read alongside latency, resource saturation, and workload.

## 13. ThreadLocal: Not Removed, but More Expensive When Overused

Virtual threads support `ThreadLocal`; however, the **one virtual thread per task** model can create a very large number of threads concurrently. If each thread holds a large object in `ThreadLocal`, total memory increases significantly.

Risky example:

```java
private static final ThreadLocal<byte[]> BUFFER =
        ThreadLocal.withInitial(() -> new byte[1024 * 1024]);
```

If thousands of virtual threads each allocate a 1 MiB buffer, memory usage can become enormous. This differs from a fixed platform pool that only has a few dozen workers holding buffers.

### 13.1. Use Short-Lived Contexts, Do Not Hold Large Objects

Avoid storing:

- Large per-thread caches.
- Database connections in `ThreadLocal`.
- Long-lived mutable session objects.
- Pooled resources requiring closure whose lifecycle is tied to a thread.
- Unbounded large buffers.

Request context can be passed via parameters or an appropriate framework context propagation mechanism.

### 13.2. MDC/Logging Context

A logging framework may use `ThreadLocal` to hold a trace ID, user context, or request metadata. Virtual threads are created fresh for each task, so **do not assume context from a platform worker will automatically propagate to child tasks**.

Example of context logic that needs explicit scoping:

```java
try {
    putTraceId(traceId);
    performRequest();
} finally {
    clearTraceId();
}
```

`putTraceId` and `clearTraceId` are placeholders for actual logging APIs. Check how the framework supports propagation when spawning new tasks, especially when using asynchronous completions or thread hops.

### 13.3. Do Not Assume Stable Thread Identity Across a Worker Pool

Some legacy libraries use `Thread.currentThread()` or `ThreadLocal` as a key to store resources for a worker reused across many requests. That model is no longer appropriate when each request gets a new virtual thread.

Thread-per-task architectures should favor **request-scoped data** or framework-managed dependency injection scopes rather than relying on worker reuse.

## 14. JDBC, Connection Pools, and Transaction Lifetimes

Virtual threads can fit synchronous JDBC programming well because they allow code to wait on the database without having to dedicate a platform thread for the entire wait time, provided the driver and runtime interact appropriately.

However, the database is still bounded by:

- Maximum connections.
- Query execution slots, locks, and I/O capacity.
- Transaction isolation and contention.
- Statement timeouts and network timeouts.
- Connection pool wait queue.
- Database-side CPU, buffer cache, and disk throughput.

### 14.1. Do Not Remove the Connection Pool

A common misconception is that virtual threads make connection pools unnecessary. In reality, a connection pool protects the **database connection** resource, which is different from a pool protecting platform threads.

Example:

```text
Virtual threads = 10.000
HikariCP maximumPoolSize = 30
```

The system does not have 10,000 database connections. Many requests will wait to acquire a connection; latency and timeouts can still increase.

Choose connection pool size based on benchmarks, avoiding increasing it to thousands simply because the virtual thread count is high.

### 14.2. Transactions Must Not Be Held Open Indefinitely

A virtual thread can wait on I/O for a long time without occupying a carrier, yet its transaction can still hold a connection or row locks. Those are real resources and can cause deadlocks or saturate the database.

Do not keep transactions open across slow external API calls if business correctness does not require it and the design allows splitting them.

### 14.3. Drivers and Pools Must Be Compatible

Some JDBC drivers or pool libraries use `synchronized` sections, `ThreadLocal`, or native calls. During migration, check versions supporting newer JDKs, JDK 21 pinning behavior if relevant, timeouts, and cancellation semantics.

Do not merely test `SELECT 1` and conclude every transaction flow is compatible.

## 15. HTTP Clients and I/O Wait Times

A synchronous HTTP call can be very readable on a virtual thread:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpClientExample {
    public static void main(String[] args) throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com"))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response =
                    client.send(request, HttpResponse.BodyHandlers.ofString());

            System.out.println(response.statusCode());
        }
    }
}
```

This code illustrates HTTP client structure on a JDK supporting `HttpClient.close()`, such as JDK 21; network calls may fail depending on the environment. In real applications, manage client lifecycle, connection reuse, auth, and TLS according to production requirements.

### 15.1. Virtual Threads Do Not Replace Request Timeouts

If requests lack timeouts, many virtual threads can remain waiting for a long time. Even if carriers are released during supported waits, the system still holds request context, memory, deadlines, and potentially downstream slots.

Configure:

- Connection timeout.
- Request/read timeout.
- Overall business deadline.
- Retry policy with exponential backoff and jitter when appropriate.
- Idempotency when performing retries.
- Rate limiting and circuit breakers.
- Cancellation/interruption propagation.

### 15.2. Do Not Fire Hundreds of Thousands of Concurrent Outbound Requests

A virtual-thread-per-task executor can accept a huge number of tasks, but partner APIs typically have rate limits. For example, a partner allows 200 requests/second; 50,000 virtual threads do not make that limit disappear.

Limit outbound request concurrency/rate at an appropriate place before submission or at the downstream client layer.

## 16. Interruption, Cancellation, and Shutdown

Virtual threads use `Thread`'s interruption mechanism, but application code must still **cooperate with cancellation**.

### 16.1. Do Not Swallow `InterruptedException`

Incorrect:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Ignored completely, task keeps running.
}
```

Better approach when the method cannot throw:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Or have the method declare `throws InterruptedException` and let the orchestration layer decide.

### 16.2. `Future.cancel(true)` Requests Cancellation; It Does Not Guarantee Every Task Terminates Immediately

Example:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CancellationExample {
    public static void main(String[] args) {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Future<?> future = executor.submit(() -> {
                try {
                    while (!Thread.currentThread().isInterrupted()) {
                        Thread.sleep(100);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            future.cancel(true);
        }
    }
}
```

A task executing native code, an operation that does not support cancellation, or handling interrupts incorrectly may not stop immediately. Design deadlines, close resources, and verify actual shutdown flows.

### 16.3. Task Lifetimes Must Have an Owner

An application should not simply spawn virtual threads and forget about them:

```java
Thread.ofVirtual().start(() -> callPartnerApi());
```

If a request is canceled or the application shuts down, who is responsible for awaiting, canceling, or collecting errors from the task? In a backend service, there must be an owner in the request/service lifecycle or a specific orchestration component.

Virtual threads simplify blocking code, but **they do not replace lifetime management**.

## 17. Framework and Servlet Container Compatibility

### 17.1. A Server Supporting Virtual Threads Does Not Mean the Entire Stack Is Optimal

Several web servers and frameworks offer configuration options to handle requests with virtual threads. However, final effectiveness depends on:

- Servlet/request dispatcher implementation.
- Filter/interceptor chain.
- JDBC pool and driver.
- HTTP client library.
- Logging/tracing instrumentation.
- Transaction manager.
- ThreadLocal/context propagation.
- Security framework.
- Application code and critical sections.

If a legacy filter holds a monitor while calling an external API on JDK 21, performance may fall short of expectations even though the server supports virtual-thread-per-request.

### 17.2. Spring Boot and Modern Frameworks

Several versions of Spring Boot/frameworks provide options to enable virtual threads, but **syntax, support conditions, and lifecycle consequences differ by version**. Do not copy a property from a newer version to an older version and assume it is enabled.

When enabling them in a framework:

1. Check the official JDK/framework support matrix.
2. Confirm that the request executor or task executor actually switches to virtual threads.
3. Verify schedulers, background jobs, and application liveness.
4. Verify async/messaging/transaction semantics.
5. Run tests against the final runtime and container versions.

Some scheduler configurations may continue using platform threads; enabling virtual threads for HTTP requests does not automatically switch every task in the application.

### 17.3. Virtual Threads and Daemon Semantics

Virtual threads are daemon threads. If an application has only virtual threads remaining and no non-daemon threads keeping the JVM alive, the process may terminate when `main` or the primary lifecycle ends.

In backend applications, let the framework/container manage the lifecycle properly. Do not rely on background virtual threads to keep the process alive.

## 18. Locks, Race Conditions, and Thread Safety

Some systems were built assuming the worker pool only had 20 threads. When switching to virtual threads, many requests can concurrently perform operations that rarely contended before.

Example of non-thread-safe code:

```java
public final class Counter {
    private long value;

    public void increment() {
        value++;
    }

    public long get() {
        return value;
    }
}
```

`value++` is not atomic. With many virtual threads, updates can be lost; however, this bug also exists with platform threads.

`AtomicLong`, locks, or immutable designs can be used as needed:

```java
import java.util.concurrent.atomic.AtomicLong;

public final class SafeCounter {
    private final AtomicLong value = new AtomicLong();

    public long increment() {
        return value.incrementAndGet();
    }

    public long get() {
        return value.get();
    }
}
```

Choosing between atomics and locking must be based on business invariants, not just fixing a simple increment.

### 18.1. Do Not Share Request-Scoped State

Objects such as mutable request DTOs, `EntityManager`, or transaction contexts should not be shared across tasks if the library does not guarantee thread safety.

Many virtual threads may call singleton services simultaneously; singletons must be designed for concurrent access or use non-shared state.

### 18.2. Deadlocks Still Happen

Virtual threads do not resolve circular lock dependencies. If task A holds lock X and waits for Y, and task B holds Y and waits for X, a deadlock still occurs.

Deadlocks can be harder to spot when task counts are very high; thread dumps, lock-ordering policies, and contention testing are required.

## 19. Pooling Resources Beyond Threads

Traditional thread pools are often used as a “control knob” for multiple resources at once. When removing the worker count limit, resource constraints must be explicitly redefined.

| Resource | Real Limit | Control Measure |
|---|---|---|
| CPU | Core count/quota | Bounded CPU executor, reduce parallelism on saturation |
| Database connections | Pool size and server limit | Connection pool, short transactions, timeouts |
| Outbound HTTP | Rate/concurrency limit | Semaphore, rate limiter, connection management |
| File descriptors | OS limit | Proper lifecycle closing, admission control |
| Heap memory | Request state, buffers, queues | Bounded admission, measure allocation and GC |
| External API quota | Provider quota | `Retry-After`, backoff, circuit breaker |
| Message broker | Prefetch/in-flight/ack rate | Consumer concurrency, backpressure |
| Third-party native library | Thread safety and native handles | Dedicated pool/semaphore, version compatibility |
| Logging/monitoring | Queue/buffer/network sink | Async log backpressure, sampling, and tracing policy |

**Do not move from a platform thread limit to “unlimited” if these resources are not yet protected.**

## 20. Benchmarking Properly Before Concluding Performance Improved

A virtual threads benchmark must faithfully simulate the workload.

### 20.1. Parameters to Hold Constant

- JDK vendor/update and JVM flags.
- CPU quota, RAM, and GC configuration.
- Database/HTTP connection pool counts.
- Dataset, transaction isolation, and query complexity.
- Request arrival pattern and payload size.
- Network latency and downstream capacity.
- Framework, application server, and agents.
- Build artifact and dependency graph.

If you simultaneously enable virtual threads and upgrade the ORM, JDK, connection pool, and API gateway, it becomes very hard to attribute improvements to the execution model.

### 20.2. Compare Under the Same SLOs

Example:

```text
Baseline (platform thread pool):
  throughput: X request/s
  p95 latency: Y ms
  CPU: Z%
  DB waiters: A

Candidate (virtual threads):
  throughput: ...
  p95 latency: ...
  CPU: ...
  DB waiters: ...
```

Multiple load levels must be tested, including burst, steady state, and overload. Do not measure only peak throughput while ignoring p99 latency, error rate, and memory.

### 20.3. Warmup and JIT

Java has JIT compilation, profile-guided optimizations, and GC. A microbenchmark running for a few seconds can produce results distorted by warmup.

For concurrency microbenchmarks, use methodologically sound tools like JMH when needed, but **do not take simple `sleep` benchmark results as proof of production performance**. Real workloads require end-to-end load testing.

### 20.4. Choose the Right Success Metrics

Virtual threads may not reduce the latency of a **single** database call, but they help handle **many** I/O-waiting calls within the same thread resources. Therefore, measure throughput at target concurrency, waiting task count, tail latency, and downstream saturation.

If the real bottleneck lies in database CPU, changing threads may yield no significant improvement.

## 21. Recommended Migration Process

### Step 1 — Capture Baseline

Collect request throughput, latency, queue depth, active threads, CPU, heap, DB/HTTP pool saturation, timeouts, and error rate on the current runtime.

Record JDK/framework/driver versions as well for post-migration comparison.

### Step 2 — Classify Workloads

Separate:

- Blocking I/O with high wait times.
- CPU-bound work.
- Native/JNI blocking.
- Long-lived streaming connections.
- Background jobs and scheduled tasks.
- Request handling and batch processing.

Do not convert everything to virtual threads just because one module benefits.

### Step 3 — Verify JDK and Library Support

Choose JDK 21+ with final virtual threads, evaluating updates and pinning differences after JDK 24. Check:

- Framework/server executor support.
- JDBC drivers and connection pools.
- HTTP client behavior.
- Logging/tracing/monitoring agents.
- Synchronized/native calls.
- Test/mocking/instrumentation libraries.

### Step 4 — Choose a Narrow Migration Scope

For example, switch the executor for one endpoint/blocking service with well-understood traffic, rather than replacing the entire concurrency architecture at once.

Retain the ability to toggle via a feature flag or deploy a separate configuration when the framework allows.

### Step 5 — Redesign Concurrency Limits

If a fixed pool previously capped calls to an external API at 50, replace it with an explicit resource limit such as a semaphore, rate limiter, or bulkhead. Configure timeouts and bounded admission.

### Step 6 — Switch Execution Code

For example, replace:

```java
ExecutorService executor = Executors.newFixedThreadPool(64);
```

with:

```java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
```

but only when the logic supports thread-per-task, the executor lifecycle is managed, and downstream resources are already protected. This is a **concurrency model** change, not a syntax swap guaranteed to be compatible.

### Step 7 — Review Context and Thread Safety

Inspect `ThreadLocal`, MDC, security context, transaction boundaries, mutable state, and code binding resources to worker threads. Add context propagation and cleanup where needed.

### Step 8 — Inspect Pinning and Native Calls

On JDK 21–23, locate `synchronized` blocks containing blocking operations. On JDK 24+, re-evaluate under JEP 491 and remaining limitations. Inspect JNI/native libraries and drivers.

### Step 9 — Run Load Tests Across Multiple Levels

Test normal load, burst, and overload. Observe database waiters, connection timeouts, p95/p99 latency, heap/GC, and downstream error rates.

### Step 10 — Pilot and Rollback

Deploy to a small percentage of traffic and compare SLOs against the baseline. Have a mechanism to revert to the previous executor if overload, regressions, or incompatibilities arise.

### Step 11 — Update Operations

Adjust dashboards, alerts, runbooks, thread dump procedures, profiling/JFR, and capacity planning. With virtual threads, counting platform threads no longer fully represents the number of in-flight requests.

## 22. Common Misconceptions

### “A virtual thread is a lightweight operating system thread”

Not quite. Virtual threads are Java threads managed by the JDK and executed by a scheduler on carrier platform threads. They do not map 1:1 to OS threads.

### “Virtual threads make the CPU run faster”

False. CPU-bound work still depends on actual processing capacity and may require bounded parallelism.

### “Switching an executor to virtual threads eliminates the need for queues/backpressure”

False. Admission control and database/HTTP/API limits become even more important when the application can easily spawn many concurrent tasks.

### “Virtual threads always unmount when blocking”

This cannot be asserted for every library/native operation/JDK. You must inspect runtime behavior, pinning, and actual JFR/observability data.

### “Any `synchronized` pins a virtual thread on every JDK”

False. Behavior on JDK 21–23 differs after the JEP 491 improvements in JDK 24; even without pinning, lock contention can still limit throughput.

### “Just using a fixed virtual-thread pool is safe”

Not necessarily. Virtual threads are typically created per task; resource limits should be applied to the resources themselves. A fixed pool can mask missing backpressure or negate I/O waiting benefits.

### “ThreadLocal behaves identically in cost with 100,000 requests”

False. Each virtual thread can have its own `ThreadLocal` state. Storing large objects or transaction resources per thread can cause memory and lifecycle pressure.

### “Seeing no errors at startup means drivers/agents are supported”

False. Failures may emerge under high-load transactions, tracing, timeouts, native calls, cancellation, or pinning.

### “Enabling virtual threads means you are using structured concurrency”

False. Virtual threads are an execution primitive; structured concurrency is a different lifetime/cancellation model whose API may be in preview depending on the release.

## 23. Checklist Before Declaring Migration Successful

- [ ] Identified the JDK runtime supporting virtual threads and matching framework/driver versions.
- [ ] Classified CPU-bound work, blocking I/O, native calls, and background tasks.
- [ ] Collected baselines for throughput, p95/p99, CPU, heap, queues, and downstream capacity.
- [ ] Distinguished virtual thread count from CPU parallelism.
- [ ] Audited which resources were previously inadvertently bounded by legacy fixed pools/queues.
- [ ] Added bounded admission, rate limits, timeouts, and cancellation.
- [ ] Preserved connection pools and business-appropriate transaction boundaries.
- [ ] Audited `ThreadLocal`, MDC, security context, transaction context, and cleanup.
- [ ] Audited shared mutable state, race conditions, and deadlocks.
- [ ] Evaluated pinning using diagnostics appropriate for JDK 21–23 or 24+.
- [ ] Verified JNI/native integrations where present.
- [ ] Ensured executor/task lifecycles and shutdown have an owner.
- [ ] Tested burst/overload conditions, not just low traffic.
- [ ] Monitored downstream saturation and rate-limit errors.
- [ ] Tested against the actual production artifact and JVM.
- [ ] Updated dashboards/JFR/runbooks for virtual threads.
- [ ] Prepared an incremental rollout and rollback strategy.
- [ ] Based conclusions on measured data rather than expectations of “free” speedups.

## 24. Conclusion

Thread pools address reusing and bounding platform workers, while virtual threads let Java keep blocking code in a straightforward style while sustaining high concurrency for many I/O-waiting tasks. Yet **changing the execution model does not eliminate physical and business constraints**: CPU cores, database connections, API rate limits, heap, transaction locks, `ThreadLocal` state, and driver/agent compatibility still dictate real capacity.

In Java Advance Compatibility Migration, choose virtual threads when workloads genuinely benefit, use supported JDKs and frameworks, protect downstream resources with backpressure/admission control, review pinning according to the exact JDK generation, and manage cancellation/lifetime explicitly. Only declare improvements after load testing on the real runtime shows that throughput, latency, stability, and resource efficiency meet targets. **Virtual threads are a tool for scaling concurrency, not a wholesale replacement for resilient system design.**
