# Virtual Threads in Java 21 and Design Goals

A **virtual thread** is a type of `java.lang.Thread` managed by the Java runtime so that many tasks waiting on I/O can exist concurrently with fewer operating system threads. Java 21 made virtual threads a standard feature via **JEP 444 (Project Loom)**; no preview flags are required. This is a *pure Java concurrency* foundation, independent of frameworks.

After this lesson, the reader will be able to explain why virtual threads were introduced, distinguish them from platform threads, describe the mount/unmount mechanism and pinning in JDK 21, use the standard APIs, bound resources, and accurately evaluate their effectiveness.

## 1. The problem: many waiting tasks, limited OS threads

In the **thread-per-request** model, each request is assigned to a platform thread. A request typically uses the CPU only for a short time and spends most of its remaining time waiting on database queries, sockets, or external services. Because a platform thread is tied to an OS thread for its entire lifetime, it holds onto resources throughout the waiting period. Creating thousands of OS threads increases stack, scheduling, and context-switching overhead; using a fixed thread pool forces requests exceeding the pool size to queue, even when workers are merely waiting on I/O.

This can be addressed with callbacks or `CompletableFuture`, but control flow, exception propagation, and debugging can sometimes be harder to follow than sequential code. Virtual threads allow writing blocking operations with simple syntax while enabling the JVM to release the carrier during compatible waits.

```text
Task A: run Java → wait for I/O ──────────→ resume → complete
Task B:      run Java → wait for I/O ─→ resume → complete
Task C:           run Java → wait for I/O ────→ resume
               ^ carrier can serve another ready task
```

The design goals of virtual threads include:

1. **Increase scalability of I/O-bound concurrency:** many independent waiting tasks do not force the number of OS threads to scale proportionally.
2. **Maintain a readable model:** each task has a `Thread`, using sequential code, `try/catch`, standard call stacks, and standard debugging tools.
3. **Reduce the need to pool expensive threads:** a virtual thread is lightweight enough to represent *a single task* rather than being a reusable worker.
4. **Leverage familiar Java APIs:** `Runnable`, `Callable`, `Thread`, `ExecutorService`, `Future`, and JDK observability tools remain useful.

**No magic for CPU speed:** virtual threads primarily enable higher *throughput* when many tasks are waiting. They do not inherently make a single request have lower latency, do not make a CPU computation faster, and do not create extra CPU cores.

## 2. Distinguishing platform threads and virtual threads

| Criterion | Platform thread | Virtual thread on JDK 21 |
|---|---|---|
| Type in Java | `java.lang.Thread` | Still `java.lang.Thread` |
| Relationship to OS thread | Typically bound to one OS thread for its entire lifetime | Mounted onto a carrier OS thread when it needs to run |
| Scheduling | OS schedules the platform thread | JVM schedules the virtual thread, OS schedules the carrier |
| When waiting on compatible I/O | OS thread usually remains occupied | JVM can unmount the virtual thread and reuse the carrier |
| Cost with many waiting tasks | Higher | Usually significantly lower |
| Usage pattern | Finite OS threads or thread pool | A new virtual thread per task |
| Typical fit | CPU work, bounded number of threads, or specialized APIs | Many independent blocking I/O tasks |
| Limits | OS threads, memory, CPU | Still subject to heap, sockets, connections, CPU, pinning |

Three easily confused terms:

- **Concurrency:** multiple tasks whose processing lifetimes overlap; they can take turns on a single CPU.
- **Parallelism:** multiple tasks actually executing at the exact same time on different CPU cores.
- **Throughput vs. latency:** the number of tasks completed per unit of time vs. the time it takes for a single task to complete. Virtual threads target throughput for I/O-waiting workloads; increasing concurrency does not mean the latency of each individual I/O operation decreases.

A system with 10,000 virtual threads waiting on the network does not necessarily need 10,000 OS threads. However, it may still need the corresponding number of sockets, buffers, and memory; database connection counts or API quotas are not "virtualized" at all.

## 3. Carrier, mount, unmount, and rescheduling mechanism

A virtual thread still needs real CPU time, meaning it must still run on a **carrier**, which is a platform thread. The JVM manages attaching (*mounting*) and detaching (*unmounting*) virtual threads from carriers:

```text
 Virtual thread A ──┐
 Virtual thread B ──┤    JVM virtual-thread scheduler
 Virtual thread C ──┼──────────────┐
 ...                │              v
 Virtual thread N ──┘       Carrier OS threads
                                │
                                v
                          OS scheduler → CPU
```

1. **Mount:** a virtual thread ready to run is attached to a carrier; its code runs just like regular Java code.
2. **Compatible blocking:** when the task waits on a socket, `Thread.sleep`, or certain synchronization mechanisms that support parking, the JVM can save the task's state, unmount it, and return the carrier to another virtual thread.
3. **Ready/resume:** when the wait condition completes, the task is placed back into the queue to continue running; the JVM may mount it onto a different carrier.

Inside a task, `Thread.currentThread()` returns **the task's virtual thread**, not the carrier. You should not design logic that depends on which carrier ran the task or the order in which the scheduler picks virtual threads.

In JDK 21, the HotSpot implementation typically uses a dedicated `ForkJoinPool` to schedule carriers; by default, its parallelism level is related to the number of available processors, with the implementation property `jdk.virtualThreadScheduler.parallelism`. This is the target number of active carriers, **not** a limit on the total number of virtual threads. Do not tune this property arbitrarily based on the number of requests.

**Important limitation:** not every "blocking" operation releases the carrier. Some file I/O on JDK 21, native calls, and blocking while pinned can hold onto the OS thread. Actual effectiveness depends on the type of I/O, JDK version, and libraries.

## 4. The `Thread` API in Java 21

Main APIs:

- `Thread.ofVirtual().start(Runnable)`: creates and starts a virtual thread.
- `Thread.ofVirtual().name("...").start(Runnable)`: sets a name for observability.
- `Thread.startVirtualThread(Runnable)`: concise static factory method.
- `Thread.currentThread().isVirtual()`: checks whether the current thread is virtual.
- `Thread.join()`: waits for the task to finish.

A **standalone example runnable on JDK 21**; save as `VirtualThreadHello.java`:

```java
public class VirtualThreadHello {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println("virtual=" + current.isVirtual());
                    System.out.println("name=" + current.getName());
                });
        worker.join();
    }
}
```

Compile and run:

```bash
javac VirtualThreadHello.java
java VirtualThreadHello
```

Deterministic output:

```text
virtual=true
name=vt-demo
```

`join()` keeps `main` alive until the virtual thread finishes. This is important because **virtual threads are daemon threads** and do not keep the JVM alive on their own once all non-daemon threads have terminated. By default, a virtual thread has no name; naming it intentionally helps with tracing.

An equivalent syntax:

```java
Thread worker = Thread.startVirtualThread(() -> doWork());
worker.join();
```

This is only an API illustration; `doWork()` is a hypothetical method, so this snippet is not a standalone program.

## 5. One virtual thread per task with `ExecutorService`

`Executors.newVirtualThreadPerTaskExecutor()` creates an executor where **each submitted task gets a new virtual thread**, rather than reusing a fixed pool of virtual threads. The returned `Future` helps handle results/errors and wait for tasks.

Example saved as `VirtualThreadTasks.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadTasks {
    public static void main(String[] args) throws Exception {
        List<Future<String>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Simulate waiting, not network I/O.
                    return "task " + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Read Future in submission order, even though completion order may differ.
            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        }
    }
}
```

```bash
javac VirtualThreadTasks.java
java VirtualThreadTasks
```

Output:

```text
task 1: virtual=true
task 2: virtual=true
task 3: virtual=true
```

`Thread.sleep(100)` helps observe the waiting behavior; this example does not prove speed or driver I/O capabilities. `Future.get()` waits for and retrieves the result, throwing `ExecutionException` if the task code fails. `try-with-resources` uses `ExecutorService.close()` to wait for completion per the API contract; there is no need to combine manual shutdown logic in a simple example. On Java 21, this code does not require the `--enable-preview` flag.

### Why not pool virtual threads?

Traditional thread pools are useful when you need to **limit the number of expensive OS threads**. With virtual threads, you should create one thread per task and let the JVM schedule them. A fixed pool of virtual threads can inadvertently create queuing even when the pool worker threads are only waiting on I/O.

This **does not mean you can submit an unbounded number of tasks**. You must manage resource limits separately: connection pools, API quotas, RAM, sockets, admission rate, and the number of queued tasks. Use `Semaphore`, bounded queues, timeouts, backpressure, or connection limits to protect the right resources.

## 6. Example: limiting a resource with finite capacity

Suppose 12 tasks are waiting to use an external service, but the system only allows a maximum of 3 concurrent accesses. You can still create 12 virtual threads and use a `Semaphore` to limit the **resource-usage region**, rather than limiting by the thread count of a pool.

Save as `VirtualThreadLimit.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLimit {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(3);
        AtomicInteger completed = new AtomicInteger();
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 12; i++) {
                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        Thread.sleep(50); // Simulate I/O using the resource.
                        completed.incrementAndGet();
                    } finally {
                        permits.release();
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac VirtualThreadLimit.java
java VirtualThreadLimit
```

Deterministic output:

```text
completed=12
```

12 tasks are submitted, but at most 3 tasks are between `acquire()` and `release()` at the same time. Other tasks wait for a permit. `finally` ensures the permit is returned after a successful acquire, even if the work inside `try` is interrupted or throws an error. `AtomicInteger` updates safely from multiple threads. In a real system, choose the number of permits based on connections, quotas, or service capacity; configuring it too high can still overload the underlying resource.

## 7. Pinning: a very important limitation on **JDK 21**

**Pinning** means a virtual thread is held onto its carrier and cannot unmount when it has to wait. In JDK 21, the two main cases are:

1. Virtual thread code is executing inside a `synchronized` block/method and encounters a blocking operation.
2. Code is executing a native method or foreign function that prevents the JVM from unmounting it.

The snippet below is *illustrative only*; variables/methods are not defined for standalone compilation:

```java
synchronized (sharedLock) {
    blockingRemoteCall(); // Long blocking here can pin the carrier (JDK 21).
}
```

**Pinning does not directly cause incorrect results or equal a deadlock.** Its impact is on performance: if many virtual threads are pinned for a long time, fewer carriers remain free, reducing the ability to serve new tasks. Very brief `synchronized` blocks guarding an assignment or memory update are usually not a concern. The risk is **long and frequent blocking I/O** inside a synchronized region.

The preferred design is to capture state under the lock, release the lock, perform the I/O outside the lock, and then update state appropriately. If you genuinely need to hold a lock across a blocking call and cannot change the model, `java.util.concurrent.locks.ReentrantLock` can avoid pinning caused by intrinsic monitors on JDK 21:

```java
lock.lock();
try {
    blockingRemoteCall();
} finally {
    lock.unlock();
}
```

This is also non-standalone illustrative code: `lock` and `blockingRemoteCall()` need to be defined. **ReentrantLock does not eliminate lock contention**; tasks using the same lock can still wait on each other. Do not replace every `synchronized` with `ReentrantLock` unless there is evidence that pinning is affecting the system.

**Version distinction:** pinning due to `synchronized` is specific to **JDK 21–23**; **JDK 24** changed this behavior via JEP 491. The lesson and pinning examples here intentionally describe **Java 21**.

## 8. Common limitations and pitfalls

**CPU-bound:** Continuous computation, data compression, or running heavy algorithms are still limited by core count and CPU time. Creating countless virtual threads for pure CPU problems does not speed up computation; it can increase overhead. Measure and use an appropriate level of parallelism.

**Blocking that does not support unmounting:** Do not assume that just because an API is blocking, the JVM will release the carrier. Verify libraries, JDBC drivers, native calls, file I/O, and pinning indicators on the actual JDK version.

**ThreadLocal:** Virtual threads support `ThreadLocal` and `InheritableThreadLocal`; however, an application can create a very large number of threads. If each thread stores a large buffer or cache in `ThreadLocal`, total memory usage will grow sharply. Avoid using thread-locals to hold expensive resources per task, and call `remove()` in `finally` when you must manage values manually.

**Cancellation and timeouts:** `Future.cancel(true)` requests an interrupt on the running task; effectiveness depends on whether the code/library responds to interruption. `Future.get(timeout, unit)` throws `TimeoutException` when the wait times out, but **does not automatically cancel the task**. Design timeouts at both the I/O layer and the waiting point; handle interruption according to the program's contract.

**Daemon lifecycle:** Virtual threads do not keep the JVM alive. `join()`, management via `ExecutorService`, or an explicit waiting mechanism helps prevent premature exit before work is done.

**A `Thread` cannot be started again:** Each virtual thread is a real `Thread`; do not call `start()` a second time. New tasks use new virtual threads.

**Practical limits:** Many virtual threads still consume stack frames, objects, memory retained by tasks, sockets, and external resources. Shed load at the ingress point if request volume can exceed serving capacity; virtual threads do not replace rate limiting or backpressure.

## 9. Measurement and diagnostics on Java 21

Compare the same workload before and after switching the executor: **throughput**, p95/p99 latency, CPU, heap, queued requests, connection pool usage, and timeout errors. A demo that only calls `sleep` is not a representative production benchmark.

JDK 21 tools:

- **JFR:** the `jdk.VirtualThreadPinned` event detects pinning; the default configuration reports pinning above a threshold of about 20 ms. `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` can be enabled when needed (typically disabled by default), along with `jdk.VirtualThreadSubmitFailed`.
- **Trace pinning:** run the application with `-Djdk.tracePinnedThreads=full` or `short` in JDK 21 to inspect stack traces related to pinning; consider log volume.
- **Thread dump:** `jcmd <PID> Thread.dump_to_file -format=json threads.json` lets you observe both virtual and platform threads; this dump format is not a strictly atomic snapshot.

In the commands below, replace the PID with the actual process ID, and the JFR file must be recorded beforehand:

```bash
jcmd 12345 Thread.dump_to_file -format=json threads.json
jfr print --events jdk.VirtualThreadPinned recording.jfr
```

When throughput is low, check whether the CPU is overloaded, whether the connection pool is exhausted, whether virtual threads are being pinned by `synchronized`/native code, or whether the external service itself is slow. Only tune scheduler parallelism after clear evidence; do not treat it as a "maximum virtual threads" knob.

## 10. Selection and adoption guidelines

**Choose virtual threads** for many independent tasks with a high proportion of waiting on network I/O, JDBC, or external services; especially when you want easy-to-debug sequential code and blocking libraries well-supported by the JVM.

**Do not expect significant benefits** if the bottleneck is CPU, contention on a shared lock, connection limits, memory, a slow database, or an external API with a low quota. Address the actual bottleneck and verify with measurements.

Recommended workflow:

1. Classify tasks: how much CPU time vs. how much blocking I/O time?
2. Use one virtual thread per suitable task; manage results and lifecycle.
3. Properly bound scarce resources (`Semaphore`, connection pools, quotas, timeouts).
4. Verify library compatibility, pinning, and interruption/shutdown behavior.
5. Measure performance and resource usage under realistic conditions.

**Core mindset:** virtual threads make *wait-heavy concurrency* cheaper and easier to write; they do not replace resource-limit design, synchronization correctness, or CPU capacity.

### Self-check questions

1. Why do 10,000 tasks concurrently waiting on sockets not necessarily require 10,000 OS threads?
2. Does `Thread.currentThread()` called inside a virtual thread return the virtual thread or the carrier?
3. What is the difference between increasing throughput and reducing the latency of a single request?
4. Why is `synchronized` wrapping long network I/O a problem on JDK 21?
5. A database only allows 8 connections: should you limit the number of virtual threads or the number of concurrent operations using a connection?
6. Does `Future.get(timeout, unit)` expiring automatically cancel the task?

**Suggested answers:** (1) The JVM unmounts virtual threads waiting on compatible I/O and reuses the carrier; (2) the virtual thread; (3) number of tasks completed per unit of time vs. time for a single task; (4) the carrier is pinned while blocking; (5) concurrent resource/connection usage; (6) no, cancellation must be requested explicitly.

### Official sources

- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 — `Thread` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Java SE 21 — `Executors` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
