# Why not pool virtual threads?

**Answer:** With Java 21 and later, create **one virtual thread per concurrent task** instead of maintaining a pool of virtual threads for reuse. Traditional thread pools solve the scarcity and creation cost of **platform threads** (threads bound to OS threads). Virtual threads are much lighter and are managed by the JVM so they can be created, run, wait, and terminate along the lifecycle of each task. Pooling them usually imposes an artificial limit, increases queuing, and defeats the *thread-per-task* model.

This **does not mean allowing unbounded access to every resource**: you still need to limit connections, queries, requests, memory, and queued work using purpose-built mechanisms such as `Semaphore`, connection pools, and backpressure. The scope of this article is **Java concurrency in general**, without covering Spring configuration or mechanisms.

## 1. What were platform thread pools created for?

With `java.lang.Thread` as a **platform thread**, a Java thread is typically bound to an OS thread for its entire lifetime. Having too many such threads consumes system resources: stacks, associated memory, creation/destruction overhead, and scheduling. Therefore, instead of creating a new platform thread for every task, we commonly use `Executors.newFixedThreadPool(n)`:

1. The system keeps a finite number of platform threads, for example 16.
2. Incoming tasks are placed in a queue.
3. Each worker picks up a task, finishes it, and then reuses the same platform thread to run another task.

This is a reasonable choice when you need to manage the number of **platform threads** or the number of running CPU tasks. However, if all 16 platform threads make blocking I/O calls for 500 ms, other tasks must wait in the queue even though the CPU may be idle. Continuously increasing the pool size to hide I/O latency ends up consuming more OS threads.

## 2. What do virtual threads change?

A virtual thread is a real `Thread` object in the Java API, but it **does not hold onto a dedicated OS thread for its entire lifetime**. Virtual threads are executed on **carrier threads** (platform threads used by the JVM scheduler). When a virtual thread encounters a JDK-supported blocking operation such as `Thread.sleep` or many socket I/O operations, the JVM can *unmount* (detach) the virtual thread from its carrier, allowing the carrier to run another task; when the operation is ready, the virtual thread can resume on an available carrier.

Illustration:

```text
Platform-thread pool:
Task A ─── blocking I/O ─── complete ──> worker #1
Task B ─── blocking I/O ─── complete ──> worker #2
Task C ─── waiting for free worker ─────> worker #1

Virtual threads:
Task A / virtual thread A ── waiting on I/O ──> complete
Task B / virtual thread B ── waiting on I/O ──> complete
Task C / virtual thread C ── waiting on I/O ──> complete
       Carrier threads are shared by the JVM during execution.
```

Therefore, virtual threads are well suited for large volumes of *independent, I/O-waiting* work. They preserve the easy-to-understand sequential coding style (`read`, `sleep`, `get`, service calls...), while reducing the number of platform threads sitting idle.

**Key takeaway:** A virtual thread typically represents **one task**, rather than a long-lived worker that pulls one task after another. The virtual thread terminates when the task finishes. The JVM itself already manages reusing **carrier threads** at a lower layer; the application does not need to build another pool of virtual threads on top.

## 3. Why is pooling virtual threads not beneficial?

| Aspect | Keeping a pool of virtual threads | One virtual thread per task |
| --- | --- | --- |
| Lifecycle | Virtual threads live long to accept multiple tasks | A virtual thread is created for one task and terminates |
| Limit | Fixed worker count forces tasks into a queue | Number of live virtual threads scales with workload demand |
| Avoided cost | Mainly tries to save creating/destroying virtual threads, which are already lightweight | No need to reuse virtual threads |
| Resource throttling | Conflates worker count with actual resource limits | Enforces clear limits right where the resource is used |
| Observability/debugging | One worker may handle multiple consecutive tasks | Stack traces and lifecycle map directly to each task |

Suppose you need to make 5,000 I/O calls, each taking considerable time waiting for a response. A pool of only 20 virtual threads will allow only 20 tasks into the processing section at a time and queue the rest, even though having many virtual threads *waiting* usually does not require that many carrier threads. You have inadvertently recreated a bottleneck similar to a small pool.

Conversely, if the target system only allows **20 concurrent requests**, opening 5,000 requests at once is wrong. The right limit is **the number of requests to the target system**, not the total number of virtual threads across the application: work that does not use the target system can still proceed independently.

A design mistake is:

```java
// DO NOT DO THIS: keep a fixed pool of 20 virtual threads to reuse as workers.
ExecutorService executor =
        Executors.newFixedThreadPool(20, Thread.ofVirtual().factory());
```

The snippet above creates a **pool of virtual-thread workers** and caps the executor at 20 running tasks. This API is usable, but it is not the recommended model for leveraging virtual threads on independent I/O tasks. In contrast, `Executors.newVirtualThreadPerTaskExecutor()` **is not a virtual thread pool**: each submitted task gets its own virtual thread.

## 4. The standard approach: virtual thread per task

Java 21 directly supports `Executors.newVirtualThreadPerTaskExecutor()` and `Thread.ofVirtual()`. The following example runs standalone on Java 21+ with no external libraries:

**File `WhyNotPoolVirtualThreads.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class WhyNotPoolVirtualThreads {
    private static final int TASK_COUNT = 8;
    private static final Semaphore SERVICE_SLOTS = new Semaphore(2);

    public static void main(String[] args) throws Exception {
        List<Future<String>> results = new ArrayList<>();

        // Each submit() creates one virtual thread for one task.
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 1; i <= TASK_COUNT; i++) {
                final int taskId = i;
                results.add(executor.submit(() -> {
                    // Limit operations on the resource, not the number of virtual threads.
                    SERVICE_SLOTS.acquire();
                    try {
                        Thread.sleep(50); // Simulate I/O wait; not a real network call.
                        return "Task " + taskId
                                + ": virtual=" + Thread.currentThread().isVirtual();
                    } finally {
                        SERVICE_SLOTS.release();
                    }
                }));
            }

            // Retrieve Futures in submission order so stdout always has a deterministic order.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } // close() waits for all tasks to complete; the executor does not retain a VT pool.
    }
}
```

Compile and run:

```bash
javac WhyNotPoolVirtualThreads.java
java WhyNotPoolVirtualThreads
```

Output:

```text
Task 1: virtual=true
Task 2: virtual=true
Task 3: virtual=true
Task 4: virtual=true
Task 5: virtual=true
Task 6: virtual=true
Task 7: virtual=true
Task 8: virtual=true
```

**Exact explanation:**

- There are **8 tasks and 8 virtual threads** created by the executor, but at any given time **at most 2 tasks** can enter the simulated service call section because of `Semaphore(2)`.
- `acquire()` can cause a virtual thread to wait; placing `release()` in `finally` ensures the permit is returned even if the task fails or is interrupted after acquiring successfully. If interrupted while still in `acquire()`, the program has not acquired the permit yet, so the corresponding `finally` block will not run.
- `Thread.sleep(50)` simulates a wait interval, not real I/O performance. The `virtual=true` output is deterministic; the **execution** order of tasks and specific carriers is not guaranteed, only the **printing** order is fixed via the `Future` list.
- `Future.get()` retrieves the result and propagates task failures via `ExecutionException`; `try-with-resources` closes the executor when done.

If you only need a single standalone virtual thread, you can also call `Thread.ofVirtual().start(runnable)`; you must manage waiting for completion and proper error handling. For multiple tasks and `Future`s, a per-task executor is usually easier to organize.

## 5. Limit the right thing

### 5.1. External resources: `Semaphore` or connection pool

For example, suppose a service can only handle 10 concurrent requests. Use `Semaphore(10)` **around the service call**: the 11th request waits for a permit, while other tasks that do not touch that service can still run. When every query must obtain a connection from a bounded connection pool, the **connection pool** itself already handles waiting/limiting the number of connections; there is usually no need for a redundant semaphore unless another protection requirement exists.

Do not mistakenly assume that because virtual threads are cheap, databases, sockets, file descriptors, bandwidth, API quotas, memory, or transactions also become infinite.

### 5.2. Inbound pressure: backpressure and limiting accepted work

A `Semaphore` placed **inside** a virtual thread protects the bounded section, but creating millions of virtual threads all waiting for a permit still consumes memory, task contexts, and management overhead. When input is unbounded, you also need **a limit on accepted/in-flight requests**, bounded queues, controlled rejection, or slowing down the producer. This is **admission control/backpressure**, a separate decision from the number of carrier threads.

You can acquire a permit **before submitting a task** so the producer waits when the number of live tasks reaches a threshold; when the task finishes, release the permit, even on failure. You must also handle the case where `submit()` is rejected so permits do not leak. Do not use an arbitrary cap like a "pool of 100 virtual threads" as a substitute for analyzing actual load, latency, and resource requirements.

### 5.3. CPU-bound work: no magic speedup

Virtual threads improve **scalability when many tasks are waiting**, not by giving the CPU more cores. For compute-heavy tasks (encryption, compression, numerical processing), adding virtual threads may only increase CPU contention and context switching. The actual number of CPU tasks running in parallel still depends on allocated cores/CPUs, the scheduler, and JVM configuration. A bounded platform thread pool or a dedicated scheduling mechanism for CPU workloads may be more appropriate. Do not conclude "virtual threads are always faster than platform threads" solely from thread count.

## 6. Common misconceptions

1. **"Virtual threads don't use any pool at all."** Not quite accurate. Applications should not pool **virtual threads**; the JVM still uses **carrier platform threads** and an internal scheduler to execute them. Do not try to control carriers by manually pooling virtual threads.
2. **"Using `newVirtualThreadPerTaskExecutor()` means unbounded concurrency is safe."** False. The executor creates one virtual thread per submitted task; downstream limits, memory, queues, and inbound pressure must still be managed.
3. **"A Semaphore turns virtual threads into a pool."** False. A semaphore limits a *resource access section*, not by reusing a fixed group of virtual threads. The virtual threads still live and die with their tasks.
4. **"Having 10,000 virtual threads means 10,000 OS threads."** False. Many virtual threads can take turns using a much smaller number of carrier threads, especially when most are waiting on supported blocking operations. The actual number of carriers is determined by the JVM and workload.
5. **"Blocking I/O always releases the carrier in every situation."** False. Certain native calls, foreign-function calls, or special runtime situations can hold the carrier (pinning); verify by measuring on your target JDK.
6. **"Each virtual thread can hold a large cache in `ThreadLocal` because threads are reused."** False. `ThreadLocal` still works, but virtual threads are typically short-lived and numerous; heavy per-thread caches easily cause allocations and GC pressure. Only keep truly necessary context data and measure memory footprint.
7. **"You can remove the connection pool when switching to virtual threads."** False. Connection pools exist to manage **real connections**, which are finite and expensive, so they remain valuable.

## 7. JDK version and operational notes

- **Java 21:** Virtual threads are a standard feature (JEP 444). When blocking inside `synchronized`, a virtual thread can become **pinned** to its carrier; if this happens frequently and for long durations, it impacts scalability. Identify I/O sites that may block for extended periods inside a monitor; switch to an appropriate locking mechanism only when needed based on profiling.
- **Java 24+:** JEP 491 allows most `synchronized`-related blocking scenarios to avoid pinning the carrier as before. Therefore, **do not mechanically repeat** the JDK 21 advice that every `synchronized` must be replaced with `ReentrantLock`. Some native/foreign cases can still pin; rely on your JDK version and real observations.
- **Observability:** Measure throughput, p95/p99 latency, requests waiting on permits, connection pool wait times, memory/GC, CPU, and pinning events. JDK Flight Recorder has the `jdk.VirtualThreadPinned` event; you can use virtual-thread-aware thread dumps (`jcmd <pid> Thread.dump_to_file -format=json <file>`) depending on version/tooling. Do not use "thread count" alone as an optimization metric.
- **Cancellation and errors:** Tasks can fail, be interrupted, or time out. Ensure permits are released, resources are closed, errors are retrieved from `Future`, and executor lifecycle is managed. Virtual threads make waiting more efficient; they do not automatically handle timeouts, retries, or cancellation.

## 8. When to apply?

**Choose virtual-thread-per-task** when many independent tasks use blocking Java I/O APIs and you want to preserve a sequential coding style. **Apply separate limits** on each resource with a real quota or cost. **Control admission** when incoming task volume can grow unbounded. **Measure in practice** if the application is CPU-heavy or involves significant native blocking/pinning.

Remember: **Pool platform threads because platform threads are expensive; do not pool virtual threads because virtual threads are created per task. Limit resources with resource-limiting mechanisms.**

## References

- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): the virtual-thread-per-task model, lifecycle, and scalability.
- [Oracle Java Virtual Threads Guide](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): not pooling virtual threads, semaphores, thread-locals, and Java 21 notes.
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): pinning changes starting in Java 24.
