# Virtual Threads vs. Platform Threads in Java: Differences and How to Choose

> Scope: Java threading mechanisms in general, focusing on Java 21 and later. Virtual Threads have been an official feature since **Java 21** (JEP 444). The examples below use standard JDK APIs, without framework dependencies.

## 1. Nature: Two Kinds of `Thread`, Two Ways of Using Resources

In Java, a `Thread` represents a thread of execution: it has its own stack, state, interruption capability, and identity. Since Java 21, there are two kinds:

- **Platform thread**: a `java.lang.Thread` that the JVM binds to an operating system thread (OS thread) for its entire lifetime. The OS schedules the execution of that thread. Creating many platform threads consumes native stack memory and kernel resources; the practical count is limited relatively early.
- **Virtual thread**: still a `java.lang.Thread`, but the JVM manages its execution and saves/restores its state when the thread waits. A virtual thread only **temporarily runs on** a platform thread called a **carrier thread**. Many virtual threads can take turns using a small number of carriers, making them well-suited for a large volume of I/O-waiting tasks.

Both still use the familiar sequential coding model: method calls, `try/catch/finally`, `ThreadLocal`, `interrupt()`, `join()`, locks, and `java.util.concurrent` APIs. A virtual thread does not have its own CPU, nor does it make a purely CPU-bound computation run faster on its own.

### Visualizing Scheduling

```text
Platform threads (typically 1:1):
Task A -> Java platform thread A -> OS thread A
Task B -> Java platform thread B -> OS thread B
Task C -> Java platform thread C -> OS thread C

Virtual threads (many tasks share carriers):
Task A -> virtual thread A --mount--> carrier 1 -> OS thread 1
          when waiting for I/O --unmount--> carrier 1 is free
Task B -> virtual thread B --mount--> carrier 1 -> OS thread 1
Task C -> virtual thread C --mount--> carrier 2 -> OS thread 2
```

**Mount**: the JVM lets a virtual thread resume running on a carrier. **Unmount**: the virtual thread pauses, saves its continuation state, and yields the carrier so another task can run; this typically happens on waiting operations supported by the JDK, such as many blocking I/O operations and `Thread.sleep`. When I/O is ready, the virtual thread is scheduled to run again, possibly on a different carrier.

Therefore, a virtual thread **does not have a fixed 1:1 relationship** with an OS thread. A carrier is still a real platform thread, and tasks actively executing Java code still compete for CPU as usual.

## 2. Comparison Table of Key Points

| Criterion | Platform thread | Virtual thread |
|---|---|---|
| Who schedules it? | The OS schedules the corresponding OS thread | The JVM schedules the virtual thread onto a carrier; the OS still schedules the carrier |
| Binding to OS thread | Typically holds an OS thread for its entire lifetime | Attached to a carrier only while executing; can unmount while waiting |
| Creation and maintenance cost | Relatively high: native stack, OS resources | Much lower for mostly waiting tasks; stack/continuation managed by the JVM |
| Practical scale | Typically tens/hundreds or a few thousand depending on the environment | Can be tens of thousands or more when resources and workload allow |
| `Thread.sleep`, blocking I/O | The OS thread is usually occupied while waiting as well | For operations that support unmounting, the carrier can serve other work |
| CPU-bound work | Suitable if the number of threads running in parallel is reasonably bounded | Does not increase CPU core count or raw computation throughput |
| Lifecycle management | Typically uses `newFixedThreadPool` / `newCachedThreadPool` for reuse | Create one virtual thread per task; **do not pool virtual threads** |
| Compatibility | `Thread` and `java.util.concurrent` | Also a `Thread` and supports most existing APIs; check library/native call limitations |
| `ThreadLocal` | Yes; easy to reuse in pooled threads | Yes; but many tasks = many state copies, easy to inflate memory if caches are large |
| Daemon | Can be daemon or non-daemon | Always daemon; does not keep the JVM alive on its own |
| Blocking due to locks/native | Can block the OS thread | Can experience **pinning** or block the carrier depending on the operation and JDK version |
| Target use case | Moderate thread counts, CPU tasks, long-lived background processing | Many independent tasks that spend most of their time waiting on I/O |

“Virtual threads are lightweight” is a relative statement, **not synonymous with free**: each virtual thread still holds objects, stack frames/state, `ThreadLocal`s, and resources used by the task. You cannot deduce a fixed thread-count threshold for every machine.

## 3. Runnable Example: Checking Both Thread Types

Create the file **`VirtualVsPlatform.java`**:

```java
public class VirtualVsPlatform {
    public static void main(String[] args) throws InterruptedException {
        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .unstarted(() -> { });

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .unstarted(() -> { });

        platform.start();
        virtual.start();

        platform.join();
        virtual.join();

        System.out.println("platform.isVirtual() = " + platform.isVirtual());
        System.out.println("virtual.isVirtual() = " + virtual.isVirtual());
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac VirtualVsPlatform.java
java VirtualVsPlatform
```

Exact output:

```text
platform.isVirtual() = false
virtual.isVirtual() = true
```

`Thread.ofPlatform()` / `Thread.ofVirtual()` create builders; `unstarted(...)` creates an unstarted thread; `start()` begins execution. Calling `join()` ensures the threads finish before printing the results. `isVirtual()` checks the thread type, independent of the thread name. Another concise option is `Thread.startVirtualThread(runnable)`, which both creates and starts a virtual thread.

**Do not confuse:** a virtual thread is not a `CompletableFuture`, nor is it an executor object. An executor is a mechanism that accepts and manages tasks; a task submitted to an executor can be executed on the corresponding type of thread.

## 4. Waiting on I/O: Why Virtual Threads Can Increase Throughput

Suppose each request requires about 20 ms of CPU work and 180 ms waiting on a network service. A platform thread handling requests sequentially will be occupied for the full 200 ms. If you use 100 platform threads, most of the time many OS threads are sitting idle waiting. With virtual threads, when waiting on compatible I/O, the carrier can pick up another task, enabling many concurrent requests to be served without needing one OS thread per request.

This is a **benefit in serving many concurrent tasks (scalability/throughput)**; it does not guarantee lower latency for a single request. Total capacity is still bounded by CPU, database connections, sockets/file descriptors, rate limits, remote services, and memory.

You can use the approximation `L = λ × W` (Little's Law) to visualize this: if a steady workload arrives at 1,000 requests/second and each request stays in the system for 0.2 seconds, on average about 200 requests will be in flight/waiting. This is a capacity/concurrency calculation, **not a prediction** that simply creating 200 virtual threads will achieve 1,000 req/s.

Well-suited tasks: HTTP/database calls, socket communication, pipelines reading results from multiple sources, or “one sequential flow per request” processing where most of the time is spent waiting for results.

Tasks that do not automatically benefit: compression/encryption/large number crunching, matrix computations, or pure CPU-bound loops. If you have 8 CPU cores, 100,000 virtual threads computing simultaneously will not turn 8 cores into 100,000 cores; CPU contention and scheduler overhead still apply.

## 5. Runnable Example: One Virtual Thread per Task

Create the file **`VirtualTaskExecutor.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualTaskExecutor {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Simulate waiting time
                    return "task-" + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Read in submission order, regardless of completion order.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
```

Run:

```bash
javac VirtualTaskExecutor.java
java VirtualTaskExecutor
```

Exact output:

```text
task-1: virtual=true
task-2: virtual=true
task-3: virtual=true
```

Each `submit` runs the task on a **new virtual thread**, without keeping a pool of virtual threads for reuse. `Future.get()` waits for the result or throws an exception if the task fails; reading in list order makes the output deterministic even though scheduler order is non-deterministic. `try-with-resources` calls `ExecutorService.close()`, waiting for submitted tasks to finish per the API contract.

`Thread.sleep(100)` only simulates “waiting” to illustrate the model clearly; actual runtime depends on the machine and scheduling. In real programs, most of the benefit comes from **compatible blocking I/O** such as network I/O, not because adding sleep to code makes an application faster.

### The Same Kind of Work Using a Platform Thread Pool

```java
// Illustrative snippet: imports and main are in the example above.
try (ExecutorService executor = Executors.newFixedThreadPool(3)) {
    // 3 platform worker threads are reused across tasks.
    // Tasks exceeding the worker count are placed in a queue.
}
```

Platform thread pools are useful when you want to limit the number of resource-heavy workers or the number of CPU tasks executing in parallel. With `newVirtualThreadPerTaskExecutor()`, the number of virtual threads follows the number of submitted tasks, **without applying a 3-worker limit like the pool above**. Therefore, downstream resources must be limited separately.

## 6. Do Not Pool Virtual Threads; Limit Resources in the Right Place

A common mistake is treating a platform pool's size limit as a business/system limit, then switching to virtual threads and letting every task open external connections at once. Virtual threads do not make a database, HTTP server, or disk any faster. If a system only allows 10 connections or at most 10 concurrent requests, you must keep that limit.

Use `Semaphore` to limit access to a specific resource. The following example is an **illustrative snippet inside a method**; `callRemoteService()` represents a real I/O call:

```java
Semaphore permits = new Semaphore(10); // Initialize and share across tasks

void limitedCall() throws InterruptedException {
    permits.acquire();                 // Wait until a permit is available
    try {
        callRemoteService();           // At most 10 calls can enter here concurrently
    } finally {
        permits.release();             // Do not leak a permit on exception
    }
}
```

In real code, you need `import java.util.concurrent.Semaphore;` and a definition of `callRemoteService()`; the snippet above is **not a standalone compilable class**. If `acquire()` is interrupted, no permit has been acquired, so it sits **outside** the `try/finally` release block. Do not use virtual thread counts to replace existing connection pool limits or rate limits. For CPU-bound work, use an executor bounded to a level of parallelism appropriate for the CPU rather than unbounded concurrent tasks.

## 7. How Does Virtual Thread Blocking Differ from Pinning?

**Normal blocking:** the virtual thread waits on an operation that the JVM/JDK can unmount; the carrier is returned to the scheduler. Examples include `Thread.sleep(...)` or many JDK-supported network I/O wait operations.

**Pinning:** the virtual thread remains attached to its carrier while unable to unmount; if a long waiting operation occurs at the same time, the carrier OS thread is also occupied. When pinning happens frequently, many carriers are held and scalability gains can drop. Pinning does not by itself cause incorrect computation results.

You must **distinguish by JDK version**:

- **JDK 21–23:** blocking inside a `synchronized` block/method can pin the carrier; native/foreign calls can also pin. You should only replace `synchronized` with `ReentrantLock` in sections with **long or frequent blocking** once a bottleneck has been observed; there is no need to replace every `synchronized` protecting very short memory updates.
- **JDK 24+ (JEP 491):** the JVM changed its monitor implementation so virtual threads can wait/pass through `synchronized` without being pinned solely because of the monitor. Thus the statement “every `synchronized` pins a virtual thread” is **no longer true** on newer JDKs. Some cases involving native/foreign calls or special runtime operations still need real-world verification.

Measure on the **actual target JDK version**, using JDK Flight Recorder (JFR) and the `jdk.VirtualThreadPinned` event where appropriate, while monitoring throughput, latency, CPU, carriers, and connection limits. Do not conclude pinning solely from seeing a lock or waiting time. When upgrading the JDK, re-evaluate old workarounds based on measurements.

## 8. `Thread` Characteristics You Still Have to Manage

**Interruption and cancellation:** virtual threads support `interrupt()` just like platform threads. Blocking APIs such as `Thread.sleep` can throw `InterruptedException`. If a method cannot handle it immediately, it usually needs to propagate the exception or restore the flag with `Thread.currentThread().interrupt()`; do not swallow the cancellation signal and continue indefinitely. `Future.cancel(true)` requests interrupting the task when appropriate, without guaranteeing that an arbitrary I/O call can stop instantaneously.

**Task errors:** exceptions in a `Runnable` can be reported via `UncaughtExceptionHandler`; with `ExecutorService.submit`, task errors are captured in the `Future` and `get()` can throw `ExecutionException`. Always have a timeout/cancellation strategy and business-appropriate failure handling; virtual threads do not automatically provide retries or timeouts.

**ThreadLocal:** each virtual thread has its own `ThreadLocal` storage; this API still works. However, the “one new virtual thread per task” model means expensive cached data in `ThreadLocal` is often recreated for every task; a large task count can increase memory/GC pressure. Pass parameters explicitly when convenient; audit libraries that rely on `ThreadLocal` and avoid retaining unnecessarily large objects.

**Daemon and JVM lifecycle:** virtual threads are always daemon threads. A JVM with only virtual threads running can exit once all non-daemon threads have finished. In self-written examples, use `join()`, `Future.get()`, or executor lifecycle management to wait for important tasks; do not assume a virtual thread will keep the process alive on its own.

**Shared data:** virtual threads do not eliminate race conditions, deadlocks, data races, or visibility issues. The rules of `volatile`, `synchronized`, locks, atomics, thread-safe collections, and happens-before still apply. Fewer OS threads do not mean shared mutable state is safer.

**Very long-running tasks or library limitations:** virtual threads generally fit work with a clear lifetime, handling a request/task and then finishing. Not all native calls, drivers, third-party libraries, or blocking calls unmount the same way. You need to test your actual workload and target JDK.

## 9. Which Model to Choose in Practice?

| Scenario | Recommendation | Reason |
|---|---|---|
| Very many independent requests, mostly waiting on network/database | Virtual thread per request/task | Easy-to-read sequential code; carriers can be reused during wait time |
| Continuous CPU-bound work | Platform pool bounded by CPU resources, or a controlled parallelism strategy | CPU capacity is finite; virtual threads do not create extra cores |
| Application needs at most N concurrent calls to an API/database | Virtual threads combined with `Semaphore`/connection pool/rate limiter | Business resource limits are independent of thread type |
| Long-lived background tasks needing explicit worker-count management | Evaluate platform threads and an appropriate executor | Threads do not necessarily need to be numerous and must live long |
| Many blocking calls inside monitors on JDK 21–23 | Measure pinning, improve hotspots, consider JDK 24+ | Avoid holding carriers for too long on frequent execution paths |
| Using libraries with JNI/native blocking | Benchmark and profile in practice before migrating | Some operations can hold carriers or block progress |

### Controlled Migration Checklist

1. Identify the workload: ratio of **CPU** time vs. **I/O wait**, concurrent request count, and real resource constraints.
2. Use JDK 21+; replace large platform pools for I/O with `Executors.newVirtualThreadPerTaskExecutor()` where appropriate.
3. Keep timeouts, cancellation, rate limits, connection pools, and shutdown mechanisms explicit. If you need to limit resource access, choose `Semaphore` or the resource pool's built-in limits.
4. Audit `ThreadLocal`, blocking native calls, and frequent lock points; on JDK 21–23, pay special attention to blocking inside `synchronized`.
5. Load test the same workload on both configurations, measuring **throughput, p95/p99 latency, CPU, memory, connection counts, errors/timeouts**; only conclude once metrics and bottleneck limits are identified.

## 10. Check Your Understanding with a Few Self-Test Questions

- **“One million virtual threads means one million tasks running on the CPU simultaneously?”** No. At any moment, actively running tasks still need carriers and real CPUs; many virtual threads may be in a waiting state.
- **“Are virtual threads always faster than platform threads?”** No. Virtual threads mainly help scale the number of blocking tasks, not improve the CPU speed of an individual task.
- **“Should we still pool virtual threads to avoid waste?”** No. Virtual threads are designed to be created per task; constrain downstream access using appropriate resource limits.
- **“Does `synchronized` always pin a virtual thread?”** No. This risk is especially relevant in JDK 21–23 during long waits inside a monitor; JDK 24+ addressed most of this via JEP 491.
- **“Do virtual threads eliminate the need for synchronization, timeouts, and backpressure?”** No. Those requirements remain, and are sometimes even more important because concurrent task counts can grow sharply.

## Official Documentation for Deeper Reading

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) — goals, APIs, and official model for Java 21.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — scheduling, pinning, and practical guidance for Java 21.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — monitor and pinning changes starting in JDK 24.
- [Oracle Java 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html) — newer JDK documentation perspective; distinguish from JDK 21 behavior.

**Key takeaway:** A platform thread is a JVM thread tightly bound to an OS thread; a virtual thread is a lightweight Java thread scheduled by the JVM onto carriers as needed. Choose virtual threads when you have many independent sequential tasks waiting on I/O, and measure your system's real limits rather than guessing from thread counts.
