# Thread.ofVirtual().unstarted(), ThreadFactory, and Startup Lifecycle

## 1. Objectives and Context

A virtual thread is a `java.lang.Thread` whose scheduling is managed by the JVM, well suited for workloads with many I/O-bound waiting tasks. Virtual threads were introduced into Java as a standard feature in **Java 21** (JEP 444). Therefore, the standalone examples in this lesson use **JDK 21 or later** and do not require `--enable-preview`. This is pure Java concurrency knowledge; all operations use the JDK directly, without depending on Spring or a framework's async mechanism.

The central question: **when is a new virtual thread merely created, when is it actually started, and what role does `ThreadFactory` play?**

After this lesson, you will be able to:

- Use `Thread.ofVirtual().unstarted(task)` to create a `Thread` object in the `NEW` state, then explicitly call `start()`.
- Distinguish between `unstarted(task)`, `start(task)`, `Thread.startVirtualThread(task)`, and `ThreadFactory.newThread(task)`.
- Create a reusable `ThreadFactory` from `Thread.ofVirtual().factory()`, customizing names to observe individual tasks.
- Track `NEW`, `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`, and `TERMINATED` without confusing Java thread states with CPU execution state.
- Manage the lifecycle with `join()`, `interrupt()`, `Future`, and executors; avoid forgetting `start()`, calling `run()` directly, or letting the application exit before tasks complete.

## 2. How Do Virtual Threads Differ from Platform Threads?

`Thread.ofPlatform()` creates a builder for **platform threads**, which are typically bound to operating system threads. `Thread.ofVirtual()` creates a builder for **virtual threads**: the Java runtime can multiplex many virtual threads onto a smaller number of platform threads acting as *carriers*. When a virtual thread waits on blocking operations that support this mechanism, the JVM can typically unmount it from its carrier so the carrier can serve other tasks.

The key point: a virtual thread is still a `Thread` with `Runnable`, `start()`, `join()`, `interrupt()`, `getState()`, `isAlive()`, `ThreadLocal`, and stack traces. It makes sequential-style programming easy to read for I/O-waiting tasks, but **does not automatically make CPU-bound code run faster**, does not make blocking operations disappear, and does not guarantee execution order.

```java
Runnable task = () ->
        System.out.println(Thread.currentThread().isVirtual());

Thread virtual = Thread.ofVirtual().unstarted(task);
Thread platform = Thread.ofPlatform().unstarted(task);
```

The snippet above only illustrates the API and does not start either thread. Neither has executed `task`. `Thread.currentThread().isVirtual()` must be checked **inside the running task** if you want to observe the executing thread type, because the thread that creates the task and the thread that runs the task may differ.

A virtual thread in JDK 21 is a **daemon thread**; it cannot be changed to non-daemon to keep the JVM alive. Therefore, a console program needs `join()` or an explicit completion-waiting mechanism. Do not rely on the JVM automatically waiting for unfinished virtual threads.

## 3. `Thread.ofVirtual().unstarted(task)`: Create First, Run Later

```java
Runnable task = () -> System.out.println("work");
Thread worker = Thread.ofVirtual()
        .name("read-catalog")
        .unstarted(task);               // creates Thread, does not run Runnable yet
```

Immediately after `unstarted`:

- `worker.isVirtual()` is `true`.
- `worker.getState()` is `Thread.State.NEW`.
- `worker.isAlive()` is `false`.
- `task.run()` has not been called from this thread, and no work has been scheduled merely because the `Thread` object exists.
- `worker.getName()` is `read-catalog`, a name set for observation or diagnostics.

To schedule the task for execution:

```java
worker.start(); // can only be called once
worker.join();  // current thread waits for worker to finish
```

`start()` asks the JVM to begin executing the `Runnable` on **a separate thread**; the `start()` method does not wait for the task to finish before returning. `join()` waits for the thread to terminate (or throws if the waiting thread is interrupted, depending on the overload), making it appropriate at boundaries where results are needed.

**Do not use `worker.run()` instead of `worker.start()`.** For a virtual thread, calling `Thread.run()` directly from another thread **does not start the virtual thread**, and the default implementation of `Thread.run()` on a virtual thread does not run the task the way you might expect. For platform threads as well, calling `run()` directly does not create an independent thread, so the general rule remains calling `start()` to achieve concurrency.

A `Thread` can be `start()`ed **at most once**. Calling it a second time, even after `TERMINATED`, throws `IllegalThreadStateException`. To run the same logic again, create **a new `Thread`** using the same `Runnable` or a new task. A terminated `Thread` instance cannot be reused.

## 4. Quick API Comparison

| API | Created Result | Started When API Returns? | When to Use |
| --- | --- | --- | --- |
| `Thread.ofVirtual().unstarted(task)` | A virtual `Thread` | **No**; state is `NEW` | Need to name/configure and retain explicit control over calling `start()` |
| `Thread.ofVirtual().start(task)` | A virtual `Thread` | **Start requested** | Want to create and start immediately |
| `Thread.startVirtualThread(task)` | A virtual `Thread` | **Start requested** | Concise syntax, no builder customization needed |
| `Thread.ofVirtual().factory()` | A `ThreadFactory` | No worker thread yet | Want to create many threads with the same configuration |
| `factory.newThread(task)` with the factory above | A virtual `Thread` | **No**; `start()` must be called | Creating threads manually one by one or passing to an executor |
| `Executors.newVirtualThreadPerTaskExecutor()` | `ExecutorService` | Tasks submitted to the executor are started by the executor | Organizing many tasks, managing results/cancellation/closing the executor |

`Thread.ofVirtual().start(task)` is equivalent in creation and startup semantics to creating via `unstarted(task)` and then calling `start()`, except you have no window to inspect or configure the unstarted object. Neither approach guarantees that the task has **completed** when the call returns.

`Thread.startVirtualThread(task)` is a static utility in Java 21, equivalent to `Thread.ofVirtual().start(task)`. It does **not** return a `Future`; to wait for the task to finish, you can keep the returned `Thread` and call `join()`.

## 5. `ThreadFactory`: Reusable Thread Creation Policy

`java.util.concurrent.ThreadFactory` is a functional interface with the method `Thread newThread(Runnable runnable)`. By contract, the factory creates an **unstarted thread**, allowing the caller or executor to decide when to run it.

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("io-vt-", 0)
        .factory();

Thread t0 = factory.newThread(() -> downloadChunk());
Thread t1 = factory.newThread(() -> downloadChunk());

// At this point both are still NEW; downloadChunk() is an illustrative method.
t0.start();
t1.start();
```

This is an **illustrative snippet** because `downloadChunk()` is not defined. The prefix with starting index `0` produces names `io-vt-0`, `io-vt-1`, ... for threads allocated by the factory. `factory()` snapshots the builder's current configuration to create threads consistently. The returned factory is designed to be **thread-safe**, suitable for multiple callers; by contrast, `Thread.Builder` itself is not meant to be configured concurrently by multiple threads.

The factory returned by `Thread.ofVirtual().factory()` produces virtual threads; `Executors.defaultThreadFactory()` is a platform thread factory, so it must not be used as a substitute when the explicit goal is virtual threads.

By the general interface contract, `ThreadFactory.newThread()` **may return `null`** if the factory refuses to create a thread; this is a contract possibility for custom factories, not the normal behavior of the JDK factory obtained from `Thread.ofVirtual()`. Handle it appropriately if you receive a factory provided by another library.

### Builder Configuration

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("request-", 100)
        .inheritInheritableThreadLocals(false)
        .uncaughtExceptionHandler((thread, failure) ->
                System.err.println(thread.getName() + ": "
                        + failure.getClass().getSimpleName()))
        .factory();
```

Each setting has a specific purpose:

- `name(prefix, start)` generates counter-based names. `name("fixed")` uses a fixed name for all threads created from that configuration; if you need to distinguish a batch of threads, use a prefix and starting index.
- `inheritInheritableThreadLocals(false)` prevents inheriting initial `InheritableThreadLocal` values from the creating thread; consider this to avoid leaking context across tasks. `ThreadLocal` is still supported by virtual threads, but each task should not rely on the assumption that all threads share the same context.
- `uncaughtExceptionHandler(...)` is used to observe unhandled exceptions in tasks running directly on the thread. `Future`/executor mechanisms may capture exceptions according to their own contracts, so do not rely solely on the handler to collect results.
- Virtual threads are always daemons and have specific priority restrictions; `Thread.Builder.OfVirtual` does not have daemon configuration methods like `Thread.Builder.OfPlatform`.

Do not create a new factory in every loop iteration just to number names: configuring once and reusing it keeps the naming policy and thread type consistent.

## 6. Lifecycle: `NEW` → Scheduled → `TERMINATED`

```text
ofVirtual().unstarted(task) or factory.newThread(task)
                         |
                         v
                     NEW
                         |
                      start()
                         v
           RUNNABLE <----------+
               |               |
       running or ready        |
               |               |
               +--> WAITING ---+
               |      (join/park...)
               +--> TIMED_WAITING -+
               |      (sleep/timed wait)
               +--> BLOCKED --------+
                      (waiting for monitor)
               |
        Runnable finishes
        (normally or throws exception)
               |
               v
           TERMINATED
```

`Thread.State` values are **point-in-time snapshots**, not a mandatory sequence passing through every node. A virtual thread that has just been `start()`ed may still be observed as `RUNNABLE`, or it may have finished very quickly and already become `TERMINATED`. `RUNNABLE` **does not necessarily mean** it is actively occupying a CPU; it is a Java state that covers both ready-to-run and currently running.

- `NEW`: instance created, `start()` not yet called.
- `RUNNABLE`: eligible to execute or currently executing, including while waiting to be scheduled on a carrier.
- `WAITING`: waiting indefinitely for an event, such as an appropriate wait call.
- `TIMED_WAITING`: waiting for a bounded amount of time, such as `Thread.sleep(...)`.
- `BLOCKED`: waiting to acquire a Java monitor when entering a `synchronized` block held by another thread.
- `TERMINATED`: `Runnable.run()` has returned or exited due to an uncaught exception. This state is final for a thread instance.

Do not use `getState()` for exact coordination between threads: right after reading the state, the thread may transition to another state. To confirm completion, use `join()`, `Future.get()`, `CountDownLatch`, or an appropriate synchronization mechanism.

`isAlive()` returns `false` before `start()` and after completion, and `true` during the lifetime after starting and before terminating. Therefore, **`isAlive() == false` alone is not enough to conclude that a task has finished running**: it is also true for a thread that has never been started.

### Memory Ordering Milestones (happens-before)

According to the Java Memory Model:

- Actions in the creating thread before calling `worker.start()` *happen-before* actions in the newly started thread.
- All actions in a terminated thread *happen-before* another thread successfully returns from the corresponding `join()`.

Because of this, `join()` both waits for completion and ensures the calling thread sees valid writes made by the task before it finished. However, **do not use this to skip synchronization** if multiple threads are reading/writing shared state *while they are still running*. When concurrent updates occur, still use `volatile`, atomics, locks, or thread-safe data structures as appropriate.

## 7. Example 1: Manual Startup, Observing State, and Factory Naming

The standalone program below demonstrates that both `unstarted()` and `ThreadFactory.newThread()` create threads in the `NEW` state. It intentionally calls `join()` before printing the next step so the output is deterministic. Save as `VirtualThreadLifecycleDemo.java`:

```java
import java.util.concurrent.ThreadFactory;

public class VirtualThreadLifecycleDemo {
    private static final Runnable TASK = () -> {
        Thread current = Thread.currentThread();
        System.out.println("run=" + current.getName()
                + ", virtual=" + current.isVirtual());
    };

    public static void main(String[] args) throws InterruptedException {
        Thread manual = Thread.ofVirtual()
                .name("manual-vt")
                .unstarted(TASK);
        System.out.println("manual-before=" + manual.getState());
        System.out.println("manual-alive=" + manual.isAlive());
        manual.start();
        manual.join();
        System.out.println("manual-after=" + manual.getState());

        ThreadFactory factory = Thread.ofVirtual()
                .name("factory-vt-", 1)
                .factory();
        Thread first = factory.newThread(TASK);
        Thread second = factory.newThread(TASK);
        System.out.println("factory-before=" + first.getState()
                + "," + second.getState());
        first.start();
        first.join();
        second.start();
        second.join();
        System.out.println("factory-after=" + first.getState()
                + "," + second.getState());
    }
}
```

Compile and run with JDK 21+:

```bash
javac VirtualThreadLifecycleDemo.java
java VirtualThreadLifecycleDemo
```

Output:

```text
manual-before=NEW
manual-alive=false
run=manual-vt, virtual=true
manual-after=TERMINATED
factory-before=NEW,NEW
run=factory-vt-1, virtual=true
run=factory-vt-2, virtual=true
factory-after=TERMINATED,TERMINATED
```

Why is the output deterministic?

1. `manual` was just created with `unstarted()`, so it is in `NEW` and `isAlive()` is `false`.
2. `manual.start()` triggers the task; `manual.join()` waits for the task to print the `run=...` line before `main` reads `TERMINATED`.
3. Calling `factory.newThread(TASK)` twice allocates two unstarted threads, named using the counter starting at `1`.
4. `first.start(); first.join(); second.start(); second.join();` gives the two task output lines a clear order. If replaced with `first.start(); second.start(); first.join(); second.join();`, **the order of the two printed lines is not guaranteed**, even though both tasks run properly.
5. `--enable-preview` is not required because Virtual Threads became standard in Java 21.

## 8. Example 2: Providing a `ThreadFactory` to an Executor

When you have many tasks of the same kind, it is usually better to hand thread lifecycle management over to an `ExecutorService`. The executor calls `ThreadFactory.newThread(task)` and then **calls `start()` itself** on the newly created thread: the client must not manually start threads managed by an executor.

Save to `VirtualThreadExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;

public class VirtualThreadExecutorDemo {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("task-", 0)
                .factory();
        try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
            Future<String> a = executor.submit(() -> Thread.currentThread().getName());
            Future<String> b = executor.submit(() -> Thread.currentThread().getName());
            System.out.println(a.get());
            System.out.println(b.get());
        }
    }
}
```

Run:

```bash
javac VirtualThreadExecutorDemo.java
java VirtualThreadExecutorDemo
```

Output:

```text
task-0
task-1
```

Each `submit()` creates a task and the executor uses the factory to create a new virtual thread. The name is assigned when the thread is created; the two tasks may run or finish in any order, but the **print** order in the example is deterministic because `main` calls `a.get()` then `b.get()`. `Future.get()` returns the result or throws `ExecutionException` if the task failed, and can throw `InterruptedException` if the waiting thread is interrupted.

The `try-with-resources` block calls `ExecutorService.close()` upon exit; in Java 21, this close operation waits for submitted tasks to complete per its contract. If custom naming is not needed, use the convenience method:

```java
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    // executor.submit(task) ...
}
```

This is an **illustrative snippet**: the `task` variable and result-collection logic must be defined according to your problem. This approach fits the *one virtual thread per task* model; it does not create a fixed pool of a few virtual threads for reuse. If a workload has tens of thousands of I/O requests, you must still bound downstream resources such as database connections, concurrent requests, and API quotas.

### When to Manage `Thread` Directly vs. Using an Executor?

| Need | Appropriate Tool | Reason |
| --- | --- | --- |
| A simple task, want to see `NEW` then `start()` explicitly | `Thread.ofVirtual().unstarted()` | Explicit lifecycle control and state observation |
| A task that runs immediately, no need to control start timing | `Thread.ofVirtual().start()` | Concise |
| Many threads sharing configuration/naming | `ThreadFactory` | Centralized configuration, caller controls startup |
| Many tasks returning values or needing cancellation/error collection | `ExecutorService` with factory or virtual-thread-per-task | Integrates `Future`, shutdown, and task management |
| Primarily CPU-bound work | Design parallelism limits based on CPU and resources | Virtual threads do not increase CPU capacity on their own |

## 9. `join()`, Interrupts, Timeouts, and Task Failures

### `join()` Waits for Completion but Does Not Propagate Task Exceptions

`Thread.join()` waits for the thread to terminate; it **does not rethrow** exceptions thrown by the `Runnable` in the child thread. If you need to receive data or errors as the outcome of a computation, use `Callable` and `Future`, or pass results through a thread-safe channel. For directly managed threads, `UncaughtExceptionHandler` helps record uncaught errors.

If the thread waiting in `join()` is itself interrupted, `join()` throws `InterruptedException`. An appropriate pattern when the method cannot propagate the exception is:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Exit or hand control back to the caller to decide.
}
```

This is a snippet in a context where `worker` exists, not a standalone program. Restoring the interrupt flag avoids "swallowing" the cancellation signal. Do not assume the worker has completed if `join()` was interrupted before it finished.

### `interrupt()` Is a Cooperative Request

```java
Thread worker = Thread.ofVirtual().start(() -> {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
});
worker.interrupt();
```

The snippet above asks the sleeping thread to accept the interrupt and exit; `interrupt()` does not force a task to stop in every situation. A computation loop that never checks the interrupt flag or a custom stop signal may keep running. When using an executor, `Future.cancel(true)` attempts to interrupt the running task, but does not guarantee the task will stop immediately.

`join(Duration)` is only available in newer Java releases; to ensure examples remain compatible with Java 21, use `join(long millis)` or `join(long millis, int nanos)` when a bounded wait is needed. After calling `join(timeout)`, check `isAlive()` if you need to know whether the task actually finished or merely timed out.

### Task Failures: Thread State Still Terminates

If a `Runnable` throws an unhandled exception, the thread transitions to `TERMINATED`; the exception is delivered to the appropriate uncaught-exception handler. `Thread.join()` still only waits and does not imply a successful result. To ensure the caller receives failure information, prefer `Future.get()` for executor tasks, or design an explicit error-reporting channel for manually managed threads.

## 10. Notable Concurrency Characteristics

**Virtual threads do not automatically create structured concurrency.** Spawning many threads and ignoring their results leads to unhandled task failures or the application exiting prematurely. For small scopes, keep a list of threads and `join()`; for tasks needing values, choose `ExecutorService` and close resources properly. Avoid spawning thousands of tasks just to prove the API can create them: having many virtual threads does not mean the backend can accept the same number of connections.

**Do not use a fixed virtual thread pool in the old style as an I/O throttling mechanism.** Virtual threads are cheap to create and are typically used one per task. If limiting to 20 concurrent requests is a business requirement, limit the 20 *requests or resources*, such as with a `Semaphore` or an appropriate connection pool. Using a small number of worker threads as a proxy for resource limits easily causes waiting tasks to occupy all workers.

**Synchronized, native calls, and pinning vary by JDK version.** In JDK 21, certain `synchronized` blocks or native calls can cause a virtual thread to be *pinned* to its carrier when blocking; this can hurt throughput when many tasks wait concurrently. Newer JDK releases improve monitor handling; conclusions about pinning from one version should not be assumed for all JDKs. Measure on your target runtime, keep locks short, and avoid holding locks during long I/O when possible. Pinning does not change the `NEW/start/join/TERMINATED` rules covered in this lesson.

**Thread names are for diagnostics, not business identity.** A task may have its own trace/correlation ID; thread names can collide, change, or be assigned by a factory. Do not use thread names for synchronization or checking request uniqueness.

**Creation time and execution time are different.** For example, `inheritInheritableThreadLocals(...)` affects values inherited at **thread creation time**, not every time the scheduler mounts a virtual thread onto a carrier. A carrier's `ThreadLocal` does not automatically become the context of every virtual thread. Do not store per-request state in shared static variables without concurrency protection.

## 11. Common Pitfalls

| Code / Assumption | Problem | Recommended Practice |
| --- | --- | --- |
| `Thread.ofVirtual().unstarted(task)` and forgetting `start()` | Task never runs | Call `start()` once; use `start(task)` if you want it to run immediately |
| `factory.newThread(task)` and assuming the task already started | Factory only creates an unstarted thread | Explicitly call `start()` or pass the factory to an executor |
| Calling `run()` instead of `start()` | Does not create a separate virtual execution thread | Call `start()` |
| Calling `start()` twice | `IllegalThreadStateException` | Create a new thread instance for the next run |
| Checking `getState() == RUNNABLE` to be sure a task is done | State is only a snapshot, subject to races | Use `join()` or `Future.get()` |
| Checking only `isAlive() == false` | Does not distinguish `NEW` from `TERMINATED` | Track whether it was started and use a clear completion mechanism |
| `main` creates a virtual thread and exits | Virtual threads are daemons and may not finish | Call `join()` or close the executor properly |
| Assuming `join()` returning means the task succeeded | `join()` does not propagate task exceptions | Use an exception handler or `Future` |
| Assuming every virtual thread runs simultaneously on its own CPU | The JVM shares carriers/scheduler | Understand this is concurrency, not multiplying CPU cores |
| Sharing a `ThreadFactory` while concurrently mutating `Thread.Builder` | Builder is not thread-safe | Configure the builder first, then use the created factory |
| Blocking on I/O while holding a monitor too long | Increases contention/pinning on affected JDKs | Shorten lock scopes, measure, and optimize hotspots |

## 12. Self-Check Scenarios

**Scenario A.** After `Thread t = Thread.ofVirtual().unstarted(job);`, can you conclude that `job` has already run? **No.** `t` remains `NEW` until `start()` is successfully called.

**Scenario B.** With `ThreadFactory f = Thread.ofVirtual().factory(); Thread t = f.newThread(job);`, who calls `start()`? **The caller** if managing threads directly; if the factory is passed to an `ExecutorService`, the **executor** starts the thread for the task.

**Scenario C.** After `t.join()` returns normally, can `t` be `start()`ed again? **No.** A thread instance that has been started cannot be started a second time.

**Scenario D.** Two tasks from `factory.newThread(job)` are `start()`ed back-to-back; their names are `job-1` and `job-2`. Will the smaller name necessarily print its result first? **No.** The name reflects thread allocation order, not scheduling order.

**Scenario E.** Does `Executors.newThreadPerTaskExecutor(factory)` using a virtual thread factory necessarily run only one thread at a time? **No.** This executor creates a new thread for each task; how many tasks run or wait concurrently depends on the workload and resources.

**Scenario F.** Does `Thread.State.TERMINATED` mean the task completed successfully? **No.** An uncaught exception can also cause the task to terminate.

## 13. Authoritative References

- [Java SE 21 – Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): `unstarted`, `start`, `factory`, and builder properties.
- [Java SE 21 – Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html): naming, thread-local inheritance, and handlers.
- [Java SE 21 – ThreadFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html): `newThread` contract returning an unstarted thread.
- [Java SE 21 – Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): lifecycle, `start`, `join`, `interrupt`, `isVirtual`.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): goals and design of virtual threads.

A useful self-check is to create a thread with `unstarted()`, observe `NEW`, call `start()`, and then `join()` to observe `TERMINATED`. When scaling to many tasks, keep the separation of responsibilities clear: **the builder configures, the factory creates threads, the caller or executor starts them, and a completion mechanism confirms termination**.
