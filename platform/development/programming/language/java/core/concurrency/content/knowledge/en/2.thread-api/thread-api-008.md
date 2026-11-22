# ThreadFactory for Standardizing Thread Creation in Java

A multi-threaded Java application needs a consistent way to create threads: readable names in thread dumps, appropriate daemon mode, sensible priority, exception handling, and rules for attaching threads to an executor. If different parts of a program call `new Thread(...)` directly with varying configurations, operations and incident troubleshooting become very difficult to manage.

`java.util.concurrent.ThreadFactory` is a **functional interface** that provides a central point for creating `Thread` instances. It separates **thread creation policy** from **the work the thread will run**. An `ExecutorService` can invoke the factory whenever it needs a new worker; code calling the executor does not need to know how that worker is named or configured.

This lesson covers only **general Java Concurrency and the Thread API**, without implementing Spring-specific task management mechanisms.

## 1. Objectives and Mental Model

After this lesson, you should be able to distinguish the following responsibilities:

| Component | Responsibility | Not Responsible For |
| --- | --- | --- |
| `Runnable` / `Callable` | Describes the work to be performed; `Callable` can return a result or throw a checked exception. | Deciding naming, daemon mode, or worker count. |
| `ThreadFactory` | Creates a `Thread` object to run the passed `Runnable` and applies thread policies. | Task scheduling, queue bounds, auto-starting threads, collecting results. |
| `Thread` | Execution unit per the Thread API; `start()` causes the JVM to begin executing `run()`. | Managing a queue of multiple tasks according to pool policies. |
| `Executor` / `ExecutorService` | Accepts tasks and schedules/dispatches them; `ExecutorService` adds `submit`, shutdown, and `Future` management. | Always creating a new thread for every task; behavior depends on the implementation. |
| `ThreadPoolExecutor` | Defines worker count, queue, timeout, rejection, and worker lifecycle for a thread pool. | Using `ThreadFactory` to replace all pool configurations. |

The typical flow of responsibilities is:

```text
Application submits Runnable/Callable
             |
             v
     ExecutorService
         |  needs a new worker
         v
      ThreadFactory.newThread(Runnable worker)
         |
         v
       Thread (NEW, configured)
         |
         v
     Executor calls start()
         |
         v
   Worker processes task/queue
```

The factory **creates** the thread; the executor typically **decides when to create, when to run, and when to reuse**. If you call the factory directly, the caller itself must `start()`, `join()`/wait in a controlled manner, and manage the lifecycle.

## 2. The ThreadFactory Contract

Declaration in Java:

```java
@FunctionalInterface
public interface ThreadFactory {
    Thread newThread(Runnable r);
}
```

Key points to understand accurately:

1. `newThread(r)` receives **the exact Runnable provided by the caller**. The factory must attach this runnable to the thread; ignoring the runnable prevents the executor from running the worker as designed.
2. The returned thread is normally in the **`NEW`** state (`start()` has not been called). The factory must not call `start()` itself; if it auto-starts the thread, the executor may encounter `IllegalThreadStateException` when trying to start it again or hit unpredictable race conditions.
3. Each time a new worker is needed, the factory must return a **new, usable** thread, never re-returning a thread that has already run. A `Thread` can only be `start()`ed once.
4. By contract, the interface may return `null` when a thread cannot be created. However, doing so may prevent the executor from initializing a worker or making expected progress; in normal applications, you should create a valid thread or let the thread-creation error surface and be handled at the appropriate layer.
5. Not every `submit()` call leads to a `newThread()` call: a thread pool **reuses** workers.
6. The factory may be called concurrently; state used to generate sequence numbers/names should be thread-safe. `AtomicInteger` is a simple choice. There is no need to lock around the entire thread creation just to increment a counter.
7. The factory **does not guarantee** that the `Runnable` will complete, nor does it guarantee execution order, fairness, timeouts, or the number of active threads.

Thread names are operational metadata, not unique keys for identifying tasks. A name can collide across two factory instances; thread IDs should likewise not be treated as long-lived business IDs.

## 3. Java 17+ Example: A Runnable Custom Factory

Create `NamedThreadFactoryDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public final class NamedThreadFactoryDemo {

    public static void main(String[] args) throws InterruptedException {
        ThreadFactory factory = new NamedThreadFactory("demo-worker");

        Thread first = factory.newThread(() ->
                System.out.println("Task 1: "
                        + Thread.currentThread().getName()));
        first.start();
        first.join();

        Thread second = factory.newThread(() -> {
            System.out.println("Task 2: "
                    + Thread.currentThread().getName());
            throw new IllegalStateException("demo failure");
        });
        second.start();
        second.join();

        System.out.println("Main completed");
    }

    private static final class NamedThreadFactory implements ThreadFactory {
        private final String prefix;
        private final AtomicInteger sequence = new AtomicInteger();

        private NamedThreadFactory(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public Thread newThread(Runnable task) {
            Objects.requireNonNull(task, "task");

            String name = prefix + "-" + sequence.incrementAndGet();
            Thread thread = new Thread(task, name);

            // Configure before the executor or caller calls start().
            thread.setDaemon(false);
            thread.setPriority(Thread.NORM_PRIORITY);
            thread.setUncaughtExceptionHandler((failedThread, error) ->
                    System.out.println("Uncaught in "
                            + failedThread.getName() + ": "
                            + error.getClass().getSimpleName()));

            return thread;
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac NamedThreadFactoryDemo.java
java NamedThreadFactoryDemo
```

Expected output (the two `join()` calls make the example's order deterministic):

```text
Task 1: demo-worker-1
Task 2: demo-worker-2
Uncaught in demo-worker-2: IllegalStateException
Main completed
```

**Explanation:**

- `AtomicInteger.incrementAndGet()` assigns sequence numbers without lost updates when multiple callers request thread creation concurrently. Within *the same factory instance*, names are numbered incrementally.
- `new Thread(task, name)` associates the `Runnable` with the new thread and sets its name at creation time. No task runs inside `newThread()`.
- `setDaemon(false)` and `setPriority(Thread.NORM_PRIORITY)` establish an explicit policy for **platform threads**. Daemon mode must be set before `start()`. Priority is only a hint to the scheduler, not an SLA.
- `setUncaughtExceptionHandler` receives errors that escape `run()` uncaught. The example intentionally throws `IllegalStateException` to test the handler; in real programs, log/record metrics with appropriate context.
- `join()` waits for the thread to finish before moving to the next step; this example runs sequentially for deterministic stdout, whereas in real applications two threads can typically run concurrently.

**Do not** modify the sample class by adding `thread.start()` inside `newThread()`: the factory must return an unstarted thread. If you only need to run a few independent operations, the factory can be used directly as above, but for long-running task streams, an executor manages lifecycle and resources more cleanly.

## 4. Using ThreadFactory with ExecutorService

The most common use case is passing a factory into an executor constructor. Many `Executors` APIs accept a factory, for example:

```java
Executors.newSingleThreadExecutor(threadFactory);
Executors.newFixedThreadPool(poolSize, threadFactory);
Executors.newCachedThreadPool(threadFactory);
Executors.newScheduledThreadPool(corePoolSize, threadFactory);
```

They differ in thread creation/reuse policies, queuing, and ability to scale worker count. The factory only affects **new threads that the executor requests to create**.

### 4.1 Standalone Java 17+ Program

Create `ExecutorThreadFactoryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ExecutorThreadFactoryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger nextId = new AtomicInteger();

        ThreadFactory factory = task ->
                new Thread(task, "report-worker-" + nextId.incrementAndGet());

        ExecutorService executor = Executors.newSingleThreadExecutor(factory);
        try {
            Future<String> result =
                    executor.submit(() -> Thread.currentThread().getName());
            System.out.println(result.get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
javac ExecutorThreadFactoryDemo.java
java ExecutorThreadFactoryDemo
```

Stdout:

```text
report-worker-1
```

Here `executor.submit(...)` accepts a **task**, while the factory receives an internal `Runnable` created by the executor to serve as a worker. One worker can execute many tasks sequentially. Therefore, do not treat the counter value in the factory as a "task ID": it is the **number of threads created**, not the number of submissions.

`Future.get()` waits for the task result; in this case, the task returns the thread name. If the task throws an exception, `Future.get()` throws an `ExecutionException` wrapping the cause; it does not convert that exception into a string result. `shutdown()` stops accepting new tasks and gives already-accepted tasks a chance to complete. `awaitTermination` with a timeout only bounds **the wait duration**; it does not by itself prove all tasks have stopped. `shutdownNow()` attempts to stop via interruption and returns unstarted tasks; task code must cooperate with interruption if it needs to stop promptly.

### 4.2 ThreadFactory Does Not Replace Pool Configuration

Consider `newFixedThreadPool(4, factory)`: this is a fixed pool policy with at most four workers running tasks concurrently. When four workers already exist and are active, new submissions are normally queued, **not** causing the factory to create a fifth thread. Conversely, `newCachedThreadPool(factory)` can grow to a large number of workers when many short tasks arrive and no worker is idle, which is unsuitable if thread count must be hard-capped without load control.

For workloads requiring a **bounded queue** and an overload policy, you can use an explicitly configured `ThreadPoolExecutor`:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                                  // corePoolSize
        4,                                  // maximumPoolSize
        30, TimeUnit.SECONDS,               // keep-alive time for excess workers
        new ArrayBlockingQueue<>(100),      // bounded queue
        factory,                            // thread policy
        new ThreadPoolExecutor.AbortPolicy() // reject on overload
);
```

This is an **illustrative snippet**, assuming `ThreadPoolExecutor`, `TimeUnit`, `ArrayBlockingQueue` are imported and a valid `factory` variable exists. The pool must be shut down as part of the application lifecycle. When core workers are busy, `ThreadPoolExecutor` normally **prefers queuing tasks** before increasing workers beyond core; only when the queue cannot accept more does it consider scaling workers up to maximum. `AbortPolicy` throws `RejectedExecutionException` when a task cannot be accepted. Those behaviors belong to the executor, not the factory.

## 5. Designing a Consistent Factory Policy

A good factory provides operationally meaningful configuration and keeps its responsibilities small. Common policies:

| Policy | Implementation | Notes |
| --- | --- | --- |
| **Meaningful names** | Purpose-based prefix plus sequence number: `event-dispatch-1`, `file-reader-2` | Avoid names containing user data/secrets; keep prefixes short and stable. |
| **Daemon/platform thread** | `thread.setDaemon(boolean)` before start | Daemon threads do not keep the JVM alive; they may be terminated when the JVM exits. |
| **Priority** | `thread.setPriority(Thread.NORM_PRIORITY)` or values 1–10 for platform threads | Does not guarantee CPU share, fairness, deadlines, or speed. |
| **Uncaught exception handler** | `setUncaughtExceptionHandler` | Only receives throwables escaping the thread; does not automatically cover errors captured by `Future`. |
| **ThreadGroup** | `Thread(ThreadGroup, Runnable, String)` constructor when genuinely needed | Groups are not a modern resource-isolation or pool-management mechanism. |
| **ContextClassLoader** | `thread.setContextClassLoader(loader)` if explicitly required | Can affect class loading and keep a classloader alive; its lifecycle must be managed. |
| **Reusable configuration** | Inject `ThreadFactory` via the consumer component's constructor | Easy to test and avoids duplicating naming/handler rules across multiple places. |

Prefer a minimal, well-justified policy. Do not arbitrarily raise the priority of all workers, as that can starve other threads of CPU. Do not set `daemon` to `true` for every pool just to let the program exit without handling shutdown; in-flight work may be cut off when only daemon threads remain.

If a factory attaches an `UncaughtExceptionHandler`, error handling inside the handler must also be safe. The handler should not perform unbounded blocking operations, call back into a broken resource holding a lock, or throw a new exception: an exception thrown by the handler is ignored by the JVM at the error-dispatch layer, making failures harder to observe.

## 6. defaultThreadFactory and Built-in Options

Java provides:

```java
ThreadFactory factory = Executors.defaultThreadFactory();
```

`Executors`'s default factory creates **platform threads** (JDK 17), names them `pool-N-thread-M`, sets them non-daemon, uses `NORM_PRIORITY` (where appropriate), and uses an appropriate `ThreadGroup` per the JDK implementation. Usually this is a good enough starting point when custom rules are not yet needed.

**Comparison of options:**

- `new Thread(runnable)`: direct creation; the developer must configure and start it manually.
- `Executors.defaultThreadFactory()`: reusable when configuring an executor and wanting consistent default policies.
- `Executors.privilegedThreadFactory()`: legacy API tied to historical security contexts; not the preferred approach for new Java code and may be deprecated/removed in future JDK versions. Do not use it as a general security tool.
- **Custom `ThreadFactory`**: needed for clear naming, custom handlers, daemon policy, or injectability/testability. Only create and configure the thread; do not embed business logic.
- **Java 21+ `Thread.Builder`**: creates factories for platform/virtual threads using the newer syntax, explained in section 9.

A factory should normally be **a single shared instance** scoped to an executor, so the naming counter does not reset on every submission. Creating `new NamedThreadFactory("worker")` per call can leave many threads all named `worker-1`, making thread dumps confusing.

## 7. Exceptions: Differences Between Direct Thread, execute, and submit

Configuring an `UncaughtExceptionHandler` is often misunderstood as a central mechanism for catching **all** task exceptions.

### 7.1 Direct Thread

When `new Thread(runnable).start()` runs and `runnable.run()` throws an uncaught exception, the exception escapes the thread and the corresponding handler is invoked. The first demo illustrated this exact case.

### 7.2 Executor.execute(Runnable)

For executors using platform threads, an unchecked exception escaping `run()` of a task submitted via `execute` can propagate to the worker and trigger the uncaught handler; `ThreadPoolExecutor` may have to replace the dead worker. However, letting a task destroy a worker should not be used as a normal error-handling policy. Handle/retry tasks at the business layer with appropriate bounds.

### 7.3 ExecutorService.submit(...)

`submit()` typically wraps the task in a `FutureTask`. Exceptions from the task are **recorded in the Future**, so they **do not escape the worker's `run()`** for the thread's handler to catch. Example:

```java
Future<?> job = executor.submit(() -> {
    throw new IllegalArgumentException("invalid input");
});

try {
    job.get();
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    // Log or handle the task error according to application policy.
}
```

This snippet assumes an `ExecutorService executor` and imports for `Future` and `ExecutionException`. `get()` can also throw `InterruptedException`; when a task is cancelled, it can throw `CancellationException`. In applications, you must handle both the `Future` lifecycle and task cancellation per the API contract.

**Rule of thumb:** use `UncaughtExceptionHandler` for uncaught thread-level errors, while asynchronous task errors must be handled at the `Future`/result level, retry policy, and task monitoring. A factory does not turn `submit` into safe fire-and-forget.

## 8. ThreadLocal, Context, and Worker Reuse

A task runs on a pool worker, **not necessarily** the thread that called `submit()`. A `ThreadLocal` set on the submitting thread does not automatically become a `ThreadLocal` on another worker. With `InheritableThreadLocal`, values may be inherited **when a thread is created**, but a pool creates workers ahead of time or reuses workers, so the result is not "per-task context" and risks leaking data between tasks.

Example of an error-prone snippet:

```java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

void process(String requestId) {
    REQUEST_ID.set(requestId);
    // ... business logic ...
    REQUEST_ID.remove();
}
```

The snippet above shows **setting and cleaning up on the same thread**, but by itself it does not handle the case where `business logic` throws an exception. In real code, place cleanup in `finally`:

```java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(requestId);
    // Run the task on the worker that needs the context.
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
```

This is an illustrative snippet, assuming `REQUEST_ID` and `requestId` already exist. If you need to propagate context across threads, capture **the appropriate context value** at submit time, attach it, and clean it up **at execution time on the worker**. Avoid reading the submitting thread's `ThreadLocal` inside the factory and applying it by default to all tasks on a worker: a worker is long-lived and runs many requests, so the context from thread-creation time will become stale.

Do not pass secrets, classloaders, or unnecessary context to long-lived threads. The factory should only manage thread attributes; **per-task** context propagation requires a wrapper/decorator at the task execution layer.

## 9. Platform Threads and Virtual Threads from Java 21

JDK 17 uses `ThreadFactory` to create regular platform threads; in Java 21, `Thread.Builder` adds a declarative way to create factories for both platform and virtual threads.

Java 21+ example creating a virtual thread factory:

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("v-worker-", 0)
        .factory();
```

`Thread.ofVirtual()` creates a builder for **virtual threads**; `name(prefix, start)` sets the prefix and starting sequence number; `factory()` creates a factory that applies that configuration to each new virtual thread.

### Standalone Java 21+ Example

Create `VirtualFactoryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.Future;

public final class VirtualFactoryDemo {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("v-worker-", 0)
                .factory();

        try (ExecutorService executor =
                Executors.newThreadPerTaskExecutor(factory)) {
            Future<String> future = executor.submit(() ->
                    Thread.currentThread().getName()
                    + ", virtual=" + Thread.currentThread().isVirtual());
            System.out.println(future.get());
        }
    }
}
```

Run with **JDK 21 or later**:

```bash
javac VirtualFactoryDemo.java
java VirtualFactoryDemo
```

Stdout:

```text
v-worker-0, virtual=true
```

`Executors.newThreadPerTaskExecutor(factory)` creates **a new thread per task**, rather than reusing workers from a fixed pool. With virtual threads, a thread-per-blocking-task model is far more practical than one platform thread per task; however, you still need to bound access to databases, networks, connection pools, and downstream resources using separate mechanisms. The factory **does not** enforce backpressure on its own.

Virtual threads in Java 21 are always daemon threads; you cannot customize priority/daemon mode the way you can for platform threads. Do not copy a factory that calls `thread.setDaemon(false)` or `setPriority` verbatim to virtual threads. If you need to configure virtual threads, use the supported builder methods, e.g., `Thread.ofVirtual().name(...).uncaughtExceptionHandler(...).factory()`.

Virtual threads still work with `ThreadFactory`, `Runnable`, and `ExecutorService`, but the goal of virtual threads is not to build a small "virtual fixed pool" to cap thread count. Throttling load with semaphores, queues, or limits on genuinely scarce resources is usually clearer. If you must support Java 17, **do not** include `Thread.ofVirtual()` in code compiled with JDK 17: that API does not exist there.

For platform threads on JDK 21, you can also write `Thread.ofPlatform().name("platform-", 0).factory()` instead of a simple custom factory. Be clear about your target runtime/JDK before choosing an API.

## 10. Performance, Safety, and Liveness Limits

Do not mistake `ThreadFactory` for a complete concurrency solution:

- **Safety:** a factory does not make shared data thread-safe; you still need `synchronized`, locks, atomic operations, or proper immutable design.
- **Liveness:** a factory does not prevent deadlock, livelock, starvation, or unbounded waiting inside tasks; you need lock ordering, timeouts, cancellation, and dependency management between tasks.
- **Worker count:** a factory only creates threads when asked; resource limits live in the executor/pool. A factory that spawns extra workers unasked violates the executor's policy.
- **Thread reuse:** tasks may run on the same worker repeatedly; `ThreadLocal` and thread names are not unique task IDs.
- **Throughput/latency:** naming and handlers aid observability; they do not make a pool faster. Unbounded queues can accumulate backlog, while unbounded thread creation can cause CPU/memory pressure.
- **Shutdown time:** `daemon` is not a graceful shutdown strategy. Tasks must handle interruption and reasonable deadlines.
- **Priority:** `setPriority` is not a fairness mechanism, and behavior can vary across JVM/OS platforms.

A factory called from multiple threads should be fast, avoid long blocking, and avoid side effects outside thread creation/configuration. Do not invoke business callbacks or I/O inside `newThread()`. If there are specific resource limits, let the executor/admission control decide whether to create another worker or reject the task.

## 11. Testing ThreadFactory

Test **observable** properties without relying on unpredictable scheduling order:

1. `newThread(runnable)` returns a non-`null` thread in the `NEW` state and has not run `Runnable` before `start()` is called.
2. The thread actually runs the passed `Runnable` and completes upon `join()`.
3. The thread name has a valid prefix; within the same factory, names do not collide under contention.
4. For **platform threads**, daemon/priority/handler match the policy; do not run these assertions on virtual threads where the API does not support the same attributes.
5. The handler receives uncaught exceptions when the thread executes `run()` after `start()`; errors escaping a direct `run()` call propagate to the caller like a normal method call, while `submit()` task errors are stored in `Future`.
6. When integrating with an executor, verify that factory-created workers are actually used, tasks complete, shutdown works, and overload scenarios behave per the pool configuration.

A short harness verifying `newThread()` does not start the thread:

```java
ThreadFactory factory = r -> new Thread(r, "test-worker");
Thread thread = factory.newThread(() -> { /* nothing to print */ });

if (thread.getState() != Thread.State.NEW) {
    throw new AssertionError("Factory started the thread");
}
thread.start();
thread.join();
```

This is an **illustrative snippet** placed inside a method that can `throws InterruptedException`, with `ThreadFactory` imported. Once a thread is running, its state can change very quickly; only checking the `NEW` state **before start** is stable. Testing concurrent uniqueness should use a thread-safe collection and a barrier to increase contention, then verify all names after creation completes; do not infer correctness from a single run.

In production environments, consistently prefixed thread names help when reading thread dumps, but investigations also require dedicated task IDs/correlation IDs, queue depth, saturation, and wait times. Never use a worker name to back-trace the root cause of a specific request when that worker serves many requests.

## 12. Common Pitfalls

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Calling `thread.start()` inside the factory | Executor may start it again and throw `IllegalThreadStateException`; uncontrolled races. | Only create/configure and return a `NEW` thread. |
| Ignoring the input `Runnable` | Executor creates a worker that fails to run its intended work. | Pass the exact runnable into the thread constructor/builder. |
| Creating a new factory/counter from 0 on each `newThread()` | Duplicate names and fragmented policies. | Use a factory instance scoped to the executor's lifetime. |
| Using `int counter++` in a concurrently called factory | Lost updates, duplicate names. | Use `AtomicInteger` or appropriate synchronization. |
| Setting `daemon=true` on every pool | JVM may exit before work is complete. | Choose daemon policy based on requirements and shut down properly. |
| Relying on uncaught handler to catch `submit()` errors | Errors are held in `Future` and easily missed. | Collect `Future`s and handle `get()`/completion. |
| Using priority instead of load control | Unpredictable scheduling and no SLA guarantees. | Configure queues, pools, timeouts, and downstream limits. |
| Using caller-created `ThreadLocal` to "auto-propagate context" | Reused workers get missing/wrong context or retain stale data. | Wrap each task, attach context inside the worker, and clean up in `finally`. |
| Assuming "one submit = one thread creation" | Incorrect task counts and wrong assumptions about worker reuse. | Distinguish tasks, worker threads, and executor policies. |
| Calling `Thread.ofVirtual()` on Java 17 | Fails to compile because the Java 21 API does not exist. | Use a Java 17 factory or upgrade the minimum JDK to 21. |

## 13. Workflow for Applying in a Java Project

1. **Identify workload and executor.** CPU-bound tasks, blocking I/O, scheduled jobs, request volume, and arrival rates differ; choose the executor/pool first based on load requirements.
2. **Define thread rules.** Name prefixes per role, daemon or non-daemon, handler, and logging policy; only set attributes that serve a specific purpose.
3. **Create a thread-safe `ThreadFactory`.** Each `newThread(r)` returns a new thread in the `NEW` state, binds `r` properly, configures it, and returns it.
4. **Pass the factory to the executor.** Separate executor setup from `submit` code; bound core/max, queue, rejection, and timeouts at the executor layer.
5. **Observe tasks and errors.** `Future`/results capture business exceptions; the handler handles uncaught exceptions; monitor pool saturation and thread dumps.
6. **Define shutdown.** Stop accepting tasks, wait with a bound, request cancellation if needed, clean up resources; cooperate with interruption inside runnables.
7. **Test correctness and load.** Test the factory contract, thread naming, task failures, concurrent creation, and lifecycle; stress-test under realistic workloads.

### Self-Check

**Q1.** Should `ThreadFactory.newThread(r)` return a thread that has already called `start()`?  
**A:** No. The caller/executor is responsible for starting it; the returned thread must be new and unstarted.

**Q2.** If you submit 100 tasks to a fixed thread pool with 4 workers, will the factory necessarily be called 100 times?  
**A:** No. The factory is only called when the executor needs a new worker; a worker can execute multiple tasks.

**Q3.** Why is `AtomicInteger` suitable for the naming counter in a factory?  
**A:** When the factory is called concurrently, each increment is atomic, preventing threads from receiving the same number due to lost updates.

**Q4.** Why doesn't a worker's handler see exceptions from `executor.submit(() -> { throw ...; })`?  
**A:** `submit` wraps the task and stores the error in the `Future`; it must be observed via `Future.get()` or an appropriate completion mechanism.

**Q5.** If you want at most 8 tasks accessing the database concurrently, should you enforce that limit in `ThreadFactory`?  
**A:** No. Use admission control, a semaphore, pool/connection-pool limits, or an appropriate queue policy; a factory only creates threads.

**Q6.** What is the main difference between `Executors.newFixedThreadPool(4, factory)` and `Executors.newThreadPerTaskExecutor(Thread.ofVirtual().factory())`?  
**A:** The former reuses a bounded number of workers; the latter creates a new (typically virtual) thread per task and is a Java 21+ API. Downstream resources must still be managed.

**Remember:** `ThreadFactory` is where you standardize **how threads are created and configured**, making code consistent and easier to observe. The executor decides **when to create, reuse, queue, and stop workers**; the application decides **task logic, data safety, cancellation, and error handling**.