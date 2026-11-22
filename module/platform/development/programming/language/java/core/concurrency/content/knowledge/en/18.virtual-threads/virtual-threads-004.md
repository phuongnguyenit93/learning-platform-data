# `Executors.newVirtualThreadPerTaskExecutor()` — one virtual thread per task

`Executors.newVirtualThreadPerTaskExecutor()` is an API introduced in **Java 21** to create an `ExecutorService` that runs **each submitted task on a new virtual thread**. This is a useful choice for Java programs with many independent tasks that wait on I/O such as HTTP, sockets, or databases. We can continue writing readable blocking code, while the JVM can manage many virtual threads without dedicating a separate OS thread for the entire wait duration of each task.

> **Scope:** General Java concurrency, independent of Spring. The source code uses Java 21+ and the JDK standard library; no preview features need to be enabled.

## 1. What does the API actually do?

Signature:

~~~java
public static ExecutorService newVirtualThreadPerTaskExecutor()
~~~

This method belongs to the `java.util.concurrent.Executors` class. When calling `executor.execute(runnable)` or `executor.submit(callable)`, the executor creates and starts a dedicated virtual thread for that task. There is no fixed limit on the number of virtual threads the executor creates. Once a virtual thread finishes its task, it terminates and **is not returned to a pool for reuse**.

Distinguish between:

- **Task:** a `Runnable` job (returns no value) or `Callable<T>` (returns `T` and may throw checked exceptions).
- **Virtual thread:** a lightweight `Thread` scheduled by the JVM; each task has its own virtual thread.
- **Carrier thread:** a platform/OS thread that temporarily runs a virtual thread. When a virtual thread waits on compatible I/O, the JVM can detach it from the carrier so the carrier can serve another task. Not every blocking operation releases the carrier.
- **ExecutorService:** the API for submitting tasks, receiving a `Future`, requesting cancellation, and closing the executor lifecycle; it does not mean a thread pool with a fixed number of workers.

~~~text
submit(A) ---> virtual thread A --\
submit(B) ---> virtual thread B ---> JVM scheduler ---> platform carrier threads
submit(C) ---> virtual thread C --/
                      |
             waiting on compatible I/O:
             virtual thread can unmount to release carrier
~~~

Task submission order **does not guarantee** execution or completion order. Each virtual thread also **does not occupy a dedicated OS thread** for its entire lifetime. This is the major difference compared to the thread-per-request platform thread model.

## 2. Full example: three independent tasks

Save the following code to `VirtualThreadPerTaskDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadPerTaskDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                final int taskId = id;
                futures.add(executor.submit(() -> {
                    Thread.sleep(100); // Simulate I/O wait time.
                    return "task " + taskId + ": virtual="
                            + Thread.currentThread().isVirtual();
                }));
            }

            // All tasks are submitted before retrieving results.
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac VirtualThreadPerTaskDemo.java
java VirtualThreadPerTaskDemo
~~~

Stdout:

~~~text
task 1: virtual=true
task 2: virtual=true
task 3: virtual=true
~~~

Why is this output deterministic?

1. `submit(Callable<String>)` returns a `Future<String>`. Each lambda runs in a new virtual thread.
2. `Thread.currentThread().isVirtual()` is called **inside** the lambda, so it returns `true`.
3. We submit all three tasks before calling `get()`. The tasks can execute concurrently; the `for` loop below only **prints results in future order**. The actual execution and completion order of tasks may still differ.
4. `Thread.sleep(100)` simulates waiting, not a benchmark. The program makes no guarantee that it finishes in exactly 100 ms.
5. `try-with-resources` calls `ExecutorService.close()` when leaving the block, ensuring it waits for submitted tasks to finish.

**Pitfall:** writing `executor.submit(task).get()` directly inside a loop can serialize task submission, because the caller waits for the previous task to complete before submitting the next one. Submit the group of tasks first, then process results when business logic allows.

## 3. Ways to submit tasks and retrieve results

| API | Input accepted | Result for caller | Error handling |
|---|---|---|---|
| `execute(Runnable)` | `Runnable` returning no data | `void` | Unhandled exceptions follow the thread's uncaught exception mechanism |
| `submit(Runnable)` | `Runnable` | `Future<?>`; successful `get()` returns `null` | `get()` throws `ExecutionException` |
| `submit(Callable<T>)` | `Callable<T>` | `Future<T>`, `get()` returns `T` | `get()` throws `ExecutionException` |
| `invokeAll(tasks)` | Collection of `Callable` | List of `Future` in input order | Check each future |
| `invokeAny(tasks)` | Collection of `Callable` | One successful result | May throw `ExecutionException` if no task succeeds |

`Future.get()` blocks **the thread calling `get`** until the task returns a result, is cancelled, fails, or the waiting thread is interrupted. Exceptions from `Callable` are wrapped in `ExecutionException` and can be retrieved via `getCause()`. Ignoring all futures means you may miss task errors.

The following snippet assumes `future` is an already-submitted `Future<String>`:

~~~java
try {
    String result = future.get();
    System.out.println(result);
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Task failed: " + e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Caller decides to stop or cancel the remaining work.
}
~~~

Waiting for each future's result in order does not mean the tasks ran in that exact order.

## 4. `ExecutorService` lifecycle and `close()`

Common flow: create executor → submit work → collect `Future` → close executor.

- **`close()`:** `ExecutorService` supports `AutoCloseable` since Java 19; `close()` initiates an orderly shutdown and **waits for all submitted tasks to finish**. If the thread calling `close()` is interrupted while waiting, the default implementation attempts to interrupt running tasks via `shutdownNow()`, continues waiting, and restores the interrupt before returning.
- **`shutdown()`:** rejects new tasks while allowing already-submitted tasks to continue; the call itself does not wait for completion.
- **`shutdownNow()`:** attempts to interrupt running tasks and returns a list of unstarted tasks; **does not guarantee** tasks stop immediately.
- **`awaitTermination(timeout, unit)`:** waits for completion when managing the lifecycle manually.
- **`RejectedExecutionException`:** may occur if work continues to be submitted after shutdown.

Use `try (ExecutorService executor = ...)` for task groups with a clear lifecycle. For an executor that lives as long as the Java application lifecycle, clearly define its owner and when `shutdown`/`awaitTermination` is called. `close()` can wait indefinitely if a task never terminates; closing the executor **does not automatically close** sockets, file handles, or connections left open by tasks.

## 5. Timeouts, cancellation, and interrupts

Distinguish between **`Future.get` timeout**, **in-task I/O timeout**, and **overall timeout for a group of tasks**. `Future.get(500, MILLISECONDS)` only limits how long the caller waits; the task usually keeps running after `TimeoutException` is thrown. `cancel(true)` requests an interrupt on the virtual thread running the task if the task has already started, but interruption is cooperative, not a forced thread kill.

Snippet, assuming `future` is of type `Future<String>`:

~~~java
try {
    String value = future.get(
            500, java.util.concurrent.TimeUnit.MILLISECONDS);
    System.out.println(value);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true);
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Cause: " + e.getCause());
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
}
~~~

Inside the task, cancellation handling code should handle interrupts properly:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // Example inside a Runnable body.
}
~~~

This snippet illustrates a `Runnable`; if using `Callable<T>`, you must return the appropriate type or rethrow the exception. Some I/O operations do not stop immediately on interrupt, so always configure timeouts directly on the HTTP client, JDBC query, socket, or corresponding API, and close resources with `try-with-resources`/`finally`.

## 6. When do virtual threads help performance?

**I/O-bound:** If a program has thousands of independent requests that mostly wait on network or DB, virtual threads let you represent each request with a thread without dedicating a separate OS thread for the entire wait duration. On JVM-supported blocking operations, a virtual thread can unmount from its carrier; the carrier can then run other work. The main benefit is **concurrency of waiting tasks**, not making an HTTP service or database respond faster.

**CPU-bound:** For encryption, computation, or heavy loops, virtual threads do not add CPU cores. An executor with a bounded number of workers, such as `Executors.newFixedThreadPool(n)`, is usually a better fit to control parallelism. Always measure throughput, latency, CPU, memory, and downstream cost on real workloads.

| Property | `newFixedThreadPool(n)` | `newVirtualThreadPerTaskExecutor()` |
|---|---|---|
| Threads for tasks | Up to around `n` platform workers running concurrently | A new virtual thread per task |
| Thread reuse | Yes | No |
| When submitting a large number of tasks | Excess tasks usually wait in the pool's queue | No fixed limit on the number of virtual threads |
| Best suited for | Controlling worker count, CPU-bound work | Many independent blocking I/O tasks |
| DB/downstream limits | Still needed | **Still needed** |

Do not use virtual threads as a connection pool, do not assume every virtual thread releases its carrier on every blocking operation, and do not expect CPU-bound work to automatically get faster.

## 7. Limiting real resources with `Semaphore`

`newVirtualThreadPerTaskExecutor()` does not limit the number of tasks: if 50,000 tasks simultaneously call a DB that only allows 20 connections, virtual threads do not give the DB 49,980 extra connections. Limit the portion of work that uses external resources with a separate mechanism such as `Semaphore`.

Full example limiting at most **two tasks** concurrently in the simulated I/O section. Create `BoundedVirtualTasks.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;

public class BoundedVirtualTasks {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int id = 1; id <= 5; id++) {
                final int taskId = id;

                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        Thread.sleep(100);
                        return "done-" + taskId;
                    } finally {
                        permits.release();
                    }
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Run:

~~~bash
javac BoundedVirtualTasks.java
java BoundedVirtualTasks
~~~

Stdout:

~~~text
done-1
done-2
done-3
done-4
done-5
~~~

`Semaphore(2)` allows only two tasks to hold a permit simultaneously. `acquire()` is placed **before** `try/finally` so that only tasks that successfully acquire a permit will `release()` it. If `Thread.sleep()` is interrupted, `finally` still returns the permit. The print loop reads futures in submission order, so stdout is deterministic even if actual task execution order differs.

**Limitation of this example:** a semaphore inside the lambda only throttles the section holding the permit. A very large number of virtual threads can still **accumulate while waiting for a permit**, consuming memory. For continuous task sources, add backpressure **before submitting**: a bounded input queue, a cap on pending futures, batching, or producer-consumer coordination. Also manage connection pools, rate limits, timeouts, and retry policies.

## 8. Shared state, `ThreadLocal`, and pinning

A virtual thread is still a `Thread` and follows the **Java Memory Model**. It does not automatically fix race conditions, deadlocks, visibility bugs, or unsafe updates to shared mutable state. Use immutable data, `AtomicInteger`, locks, or concurrent collections where appropriate. `Future.get()` lets you wait for and retrieve a result; it does not make the entire program thread-safe.

`ThreadLocal` works with virtual threads, but if each virtual thread holds a cache or large object, creating many threads can consume significant memory. Do not rely on the assumption that another task will run on the **same virtual thread** or carrier thread. It is usually better to pass context via parameters and keep per-task state small.

**Pinning varies by JDK version:**

- On **JDK 21–23**, a virtual thread can become *pinned* to its carrier when performing a blocking operation inside `synchronized` or in certain native/foreign calls. If it blocks for a long time and frequently, the carrier is held, reducing concurrency. Short `synchronized` blocks protecting in-memory operations are usually not a concern.
- With Java 21, Java Flight Recorder (JFR) provides the `jdk.VirtualThreadPinned` event for observation. Only replace synchronization around I/O with `ReentrantLock` (with `try/finally`) when an actual bottleneck is identified; do not replace every `synchronized` unconditionally.
- **JDK 24+** improves monitor/`synchronized`-related pinning via JEP 491. Native/foreign calls and certain other blocking operations still need consideration. Therefore, always specify the JDK version when evaluating pinning.

Finally, verify your actual I/O libraries, JDBC drivers, connection pools, sockets, DNS, transactions, downstream wait times, and profiling. A large number of virtual threads does not prove a system scales well if the bottleneck lies in external resources.

## 9. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming the executor is a pool bounded by CPU cores | Too many concurrent tasks hitting downstream | Resource limits and backpressure |
| Calling `submit().get()` directly inside a loop | Work may be serialized | Submit first, collect futures afterward |
| Not reading futures when tasks can fail | Missed exceptions | Inspect `ExecutionException.getCause()` |
| Thinking `get(timeout)` stops the task | Task keeps running after timeout | `cancel(true)` and I/O timeouts |
| Swallowing `InterruptedException` | Ineffective cancellation | Stop work or propagate the interrupt |
| Forgetting `close()/shutdown()` | Poor lifecycle management, lingering tasks | `try-with-resources` or explicit lifecycle |
| Not synchronizing shared data | Race conditions | Immutability, atomics, locks, concurrent collections |
| Using virtual threads to speed up CPU-bound work | No increase in CPU capacity | Benchmark workload, use a bounded pool when appropriate |
| Storing large data in each `ThreadLocal` | High memory consumption | Keep state small, avoid large per-thread caches |
| Long blocking under `synchronized` on JDK 21 | Can pin the carrier | Measure with JFR and optimize where needed |

## 10. Self-check questions and practice

**Scenario 1:** There are 500 tasks, and the DB allows 20 connections. Does the executor automatically limit tasks hitting the DB to 20? **No.** You must apply appropriate connection/permit/backpressure limits.

**Scenario 2:** Task 3 finishes before task 1. Will a `for` loop reading `Future.get()` in the list order 1, 2, 3 print task 3 first? **No.** Print order follows the order in which futures are read; execution order is not guaranteed.

**Scenario 3:** `future.get(10, MILLISECONDS)` throws `TimeoutException`. Has the task stopped? **Not necessarily; it usually keeps running.** The timeout only ends the caller's wait. Cancellation requires `cancel(true)` and interrupt/I/O timeout handling.

**Exercise:** Modify `VirtualThreadPerTaskDemo` so that task 2 throws `IllegalStateException`, try catching `ExecutionException`, and print `getCause()`. In `BoundedVirtualTasks`, change `Semaphore(2)` to `Semaphore(1)`, and use `AtomicInteger` to measure the maximum number of tasks holding a permit simultaneously. Explain why the printed output order stays the same while total runtime changes.

## 11. Key takeaways

1. `newVirtualThreadPerTaskExecutor()` (Java 21+) returns an `ExecutorService` that creates **a new virtual thread for each task**, does not reuse virtual threads, and has no fixed concurrency cap.
2. A virtual thread can yield its carrier when waiting on compatible blocking operations. The main benefit is for I/O-bound workloads with many waiting tasks.
3. `Future` provides values/errors and cancellation; `get(timeout)` only limits how long the caller waits.
4. `close()` waits for submitted tasks to finish; each task is still responsible for managing its own connections, streams, and resources.
5. You must explicitly configure downstream limits, backpressure, timeouts, interrupt handling, thread safety, and pinning monitoring according to your JDK version.

### Official documentation

- Java SE 21 `Executors` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- Java SE 21 `ExecutorService` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java 21 Virtual Threads Guide: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
