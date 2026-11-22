# Lifecycle of Thread-Bound Resources in Java

When a `Thread` executes work, it uses several kinds of resources: the stack and scheduling metadata managed by the JVM, thread-private data (`ThreadLocal`), thread-bound context, and resources opened by application code such as files, streams, sockets, or connections. **These resources do not necessarily live and end at the same time.** In particular, a thread in a pool can serve thousands of tasks: a task ending does not mean the thread ends, and a thread ending does not automatically close every application resource that was opened.

This lesson focuses on **general Java concurrency (Java 17+)** under the `Thread` lifecycle topic; it does not cover Spring-specific thread management or context mechanisms.

After this lesson, you should be able to answer:
- Which resources truly belong to the JVM/`Thread`, and which belong to a **task** or a **processing scope**?
- How long does data in `ThreadLocal` persist, why does thread reuse lead to retaining stale data, and how do you clean it up properly?
- When an exception, cancellation, timeout, or interrupt occurs, who is responsible for closing resources?
- How does manual thread lifecycle management differ from `ExecutorService`?
- How to identify and prevent memory retention, handle leaks, wrong context, and non-terminating threads.

## 1. Distinguishing Thread, Task, and Resource Lifecycles

A **thread** is an execution thread. A **task** is a unit of work assigned to a thread to execute. A **resource** is an object or access capability that must be reclaimed, closed, or restored at the appropriate ownership boundary.

~~~text
Thread pool worker lifecycle:
  Thread created ───────────────────────────────────────────> Thread terminates
                 | Task A |  | Task B |  | Task C | ...
                 open/close  open/close  open/close
                  resource    resource    resource

Worker's ThreadLocal:
                   set(A) -> remove()
                                set(B) -> remove()
                                            set(C) -> remove()
~~~

For a manually created `new Thread(task)`, a thread typically executes `run()` only once and then terminates. However, with `ExecutorService`, **a worker thread outlives each task** so that it can be reused. Therefore, cleanup must not be tied to "when the thread dies" if the resource is only used within a single task.

| Kind | Java Example | When it should end/be restored | Who is responsible |
| --- | --- | --- | --- |
| JVM internals for the thread | Execution stack, thread state/metadata | When the thread terminates and the JVM reclaims the corresponding parts | JVM/OS, according to implementation |
| Value bound to a thread | `ThreadLocal<T>` | At the end of the logical usage scope (usually the end of the task), especially in a pool | The code that sets the value must `remove()` or restore the previous value |
| Context modified on the thread | Context class loader, thread name within a scope | Upon exiting the scope, including on error | The code that modifies it must restore it |
| Task resource | `InputStream`, `Reader`, `Socket`, JDBC `Connection` | At the end of the ownership scope; independent of whether the worker is still running | The owning code, usually via `try-with-resources` |
| Lock that must be released | `ReentrantLock` | At the end of the critical section | `unlock()` in `finally` after acquiring the lock successfully |
| Executor | `ExecutorService` | When the owner stops accepting new work and wants to complete/cancel remaining tasks | The component that created and owns the executor |

A Java variable becoming **unreachable** does not mean off-heap resources are closed immediately. The garbage collector manages object reachability; it is **not** a mechanism that determines when to close connections, files, or sockets. Closing at the right time helps avoid resource exhaustion and unpredictable behavior.

## 2. Thread Lifecycle Does Not Equal Resource Lifecycle

### 2.1. Key States

`Thread.State` consists of `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`.

- `NEW`: the thread object has been created, but `start()` has not been called yet.
- `RUNNABLE`: running or ready to run as represented by the JVM; not necessarily consuming CPU at the exact moment of observation.
- `BLOCKED`: waiting to acquire a `synchronized` monitor.
- `WAITING` / `TIMED_WAITING`: waiting indefinitely or with a time limit for another condition, such as `join()`/`sleep()`/certain synchronization mechanisms.
- `TERMINATED`: `run()` has finished, either normally or due to an uncaught exception.

A `Thread` can only be `start()`ed **once**. After `run()` finishes, the thread cannot be restarted. `join()` is how another thread waits for a thread to finish; `join()` does not return a task's result by itself and is not a method that "closes all resources the thread ever used."

### 2.2. What Happens When a Thread Terminates?

For a regular platform thread on Java 17, the JVM/OS can reclaim execution resources (such as the stack/corresponding native thread) when the thread terminates. **The `Thread` object itself may still be referenced and remain on the heap** afterward; a thread being in the `TERMINATED` state does not mean every related object has immediately been garbage-collected.

Values in `ThreadLocal` are attached to data stored on the thread, so they can be collected after the thread and its data no longer have relevant references. This is not a guarantee that "the moment `run()` ends, the application's `close()` runs automatically."

For example, if a worker opens a `FileInputStream` or `Socket` and forgets to close it, thread termination **provides no closing contract** for that resource. You must use `try-with-resources`/`finally` according to the corresponding API, even when the task runs on a short-lived thread.

### 2.3. Daemon Threads and Liveness

`setDaemon(true)` must be set before the thread is started. When only daemon threads remain active in the JVM (and there is no other reason for the runtime to keep running), the JVM can exit without waiting for those daemon threads to finish their tasks. Therefore, do not use daemon threads as a way to "auto-clean up"; they can leave write operations incomplete, and `finally` is not guaranteed to run when the JVM terminates abruptly.

Conversely, a stuck non-daemon thread can prevent the application from exiting. A proper lifecycle requires a cooperative shutdown plan, not just toggling `daemon`.

## 3. ThreadLocal: How Long Is Thread-Private Data Kept?

`ThreadLocal<T>` gives each thread an independent value looked up through the same `ThreadLocal` variable. It is suitable for state that **truly belongs to a thread** or context data whose **usage lifetime must be very clearly bounded**. It does not automatically synchronize a shared object and does not transfer data between threads.

Operations:
- `set(value)`: writes the value belonging to the calling thread.
- `get()`: retrieves the value for the **calling thread**, or the initial value if `withInitial(...)` is used.
- `remove()`: deletes the current thread's mapping for this `ThreadLocal`; a subsequent `get()` may reinitialize it if an initializer is configured.

~~~java
ThreadLocal<String> currentTask = new ThreadLocal<>();
currentTask.set("task-A");
try {
    // Code running on the same thread can read currentTask.get().
} finally {
    currentTask.remove();
}
~~~

This is an **illustrative snippet** used within a known scope. `remove()` only removes the association in `ThreadLocal`; **it does not call `close()` on the object stored in it**. If the value is a resource that needs closing, you must close the resource separately and clean up the mapping at the same time.

### 3.1. Classic Bug: Thread Pool Reusing Data from a Previous Task

Because a pool keeps workers alive between tasks, `ThreadLocal` will retain values across task boundaries if you forget to clean it up. That is a logic bug (task B sees task A's context) and can also extend the lifetime of a large object.

The complete Java 17+ example below uses a **single-worker** executor to guarantee that two tasks run sequentially on the same thread. This is an intentional experiment; you should not keep a branch missing cleanup in production code.

~~~java
// ThreadLocalLifecycleDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalLifecycleDemo {
    private static void scenario(String label, boolean cleanup) throws Exception {
        ThreadLocal<String> context = new ThreadLocal<>();
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            pool.submit(() -> {
                context.set("request-A");
                try {
                    System.out.println(label + " first: " + context.get());
                } finally {
                    if (cleanup) {
                        context.remove();
                    }
                }
            }).get();

            pool.submit(() -> {
                try {
                    System.out.println(label + " second: " + context.get());
                } finally {
                    context.remove();
                }
            }).get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        scenario("unsafe", false);
        scenario("safe", true);
    }
}
~~~

Run:

~~~bash
javac ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
~~~

Stdout:

~~~text
unsafe first: request-A
unsafe second: request-A
safe first: request-A
safe second: null
~~~

**Explanation:** The first task sets `"request-A"`. In the `unsafe` scenario, the task finishes but the worker does not terminate, so the second task reads the stale value. In `safe`, `remove()` runs in `finally` before the thread is reused; the next task's `get()` returns `null`. The two scenarios use two separate executors; each executor has exactly one worker, avoiding dependence on worker selection in a multi-threaded pool. The `Future.get()` calls ensure the two tasks run in order and any errors in them are propagated to the caller.

**Rule:** Code that `set()`s data meant for **one request/one task** must have a cleanup boundary at the **end of that request/task**, without waiting for the pool to shut down.

### 3.2. How Values Persist in Memory

A thread has a structure that stores thread-local values (the JDK implementation uses `ThreadLocalMap`). In the standard implementation, an entry's key holds a weak reference to the `ThreadLocal` object, while the value is strongly referenced. There are two notable situations:

1. If the `ThreadLocal` still exists—for example, a `static final` field—each worker that ever called `set` can retain the value until it is `remove()`d/replaced or the worker is reclaimed.
2. If the `ThreadLocal` object itself is no longer strongly referenced elsewhere, the weak key can be collected, but the entry holding the value is not necessarily cleaned up immediately; the implementation expunges stale entries during appropriate operations, so you must not rely on GC as a timely cleanup strategy.

Consequently, a long-lived pool can retain a large object graph, or even reference chains involving a class loader. Do not label every case of memory retention a "permanent memory leak": more accurately, it is **retaining references longer than the needed scope**, which increases heap usage or extends object lifetimes.

### 3.3. When Is ThreadLocal Not Appropriate?

- Results that need to be passed from a worker to the caller: use `Future`, `Callable`, or an explicit data-passing mechanism.
- Context that must follow a task across **multiple threads**: pass parameters or copy context in a controlled way; a regular `ThreadLocal` only reads the value of the **current thread**.
- When local variables or method parameters can do the job: that approach is usually easier to understand and has a shorter lifetime.
- Data that is a resource needing `close()`: do not treat `ThreadLocal.remove()` as a replacement for `close()`.

## 4. Task-Owned Resources: Closing Within the Ownership Scope

### 4.1. Use try-with-resources, Even When Running via ExecutorService

If a task opens a stream/reader/socket/connection, the task or the designated owning abstraction must close it after completion. `try-with-resources` automatically calls `close()` when exiting the block, even if an exception is thrown. If there are multiple resources, they are closed in reverse order of declaration.

The example below returns a result via `Future`, closes the resource, and removes the `ThreadLocal` according to the task lifecycle. `StringReader` is only used to make the example self-contained without an external file; with real files or sockets, the resource ownership rules remain the same.

~~~java
// TaskScopedResourceDemo.java
import java.io.BufferedReader;
import java.io.StringReader;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TaskScopedResourceDemo {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Callable<String> task = () -> {
                CONTEXT.set("request-7");
                try (BufferedReader reader =
                         new BufferedReader(new StringReader("alpha\nbeta"))) {
                    return CONTEXT.get() + ": " + reader.readLine();
                } finally {
                    CONTEXT.remove();
                }
            };

            System.out.println(pool.submit(task).get());
            System.out.println("next sees: " +
                pool.submit(() -> CONTEXT.get()).get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac TaskScopedResourceDemo.java
java TaskScopedResourceDemo
~~~

Stdout:

~~~text
request-7: alpha
next sees: null
~~~

- `BufferedReader.close()` is called at the end of the `try-with-resources` block, **before the task returns its result**; the caller only receives the string through `Future.get()`.
- `finally { CONTEXT.remove(); }` ensures the context is cleared whether the task completes normally or throws an exception.
- The next task is submitted to the same single-worker executor, so it sees `null`. This is the expected result.
- `shutdown()` manages the **executor** lifecycle; it does not replace closing the reader and clearing the context inside each task.

When using connections, pay attention to "who owns it?": a connection opened by the task itself may need to be closed at the end of the scope; a connection lent by another component may have its own return contract. Do not close a resource owned by another component just because you used it.

### 4.2. Cleanup Mechanisms Cannot Substitute for One Another

| Mechanism | What does it do? | What does it NOT do? |
| --- | --- | --- |
| `ThreadLocal.remove()` | Removes the value bound to the current thread | Does not close the resource pointed to by the value |
| `AutoCloseable.close()` | Calls the close method according to the resource contract | Does not automatically remove any `ThreadLocal` mapping |
| `finally` | Guarantees the cleanup block runs on normal exit or exception exit while the JVM continues executing | Not guaranteed to run after `Runtime.halt()`, a JVM crash, or process kill |
| `Thread.join()` | Waits for a specific thread to terminate | Does not close a task's handles/resources |
| `Future.get()` | Waits for and observes the task's result/exception | Does not automatically close resources left open by the task |
| `ExecutorService.shutdown()` | Stops accepting new tasks, lets already-accepted tasks finish | Does not wait for completion, does not automatically clean up every resource opened by tasks |

`java.util.concurrent.locks.ReentrantLock` also requires explicit cleanup, but it is **not `AutoCloseable`**: after acquiring the lock successfully, you must call `unlock()` in `finally`.

~~~java
// Illustrative example: assume lock is an already declared ReentrantLock.
lock.lock();
try {
    // Update shared state that needs protection.
} finally {
    lock.unlock();
}
~~~

The `finally` scope must begin after the lock is actually acquired; do not `unlock` a lock that the thread does not hold.

## 5. Thread-Bound Context: Do Not Leak Stale Values to the Next Task

### 5.1. Thread Name and Context Class Loader

Thread names often help with diagnostics. If you temporarily change `Thread.currentThread().setName(...)` for a task on a worker, restore the old name in `finally` so the next task does not inherit the previous task's label.

The context class loader is also thread-bound state, accessed via `getContextClassLoader()` / `setContextClassLoader(...)`. Some APIs look up providers/services using this loader. Changing it and forgetting to restore it can cause later tasks to use the wrong loader and retain unnecessary references to a class loader.

~~~java
// Illustrative example: customLoader is already defined.
Thread current = Thread.currentThread();
String oldName = current.getName();
ClassLoader oldLoader = current.getContextClassLoader();
try {
    current.setName("worker-for-task-A");
    current.setContextClassLoader(customLoader);
    // Execute work requiring the temporary context.
} finally {
    current.setContextClassLoader(oldLoader);
    current.setName(oldName);
}
~~~

The snippet above is **not a standalone runnable Java file**, because `customLoader` must be provided. The key point is **save → change → use → restore**, even when the operation fails. If contexts can be nested, restoring the previous value is more accurate than simply calling `ThreadLocal.remove()` on a context that already existed before the scope; clearly define who owns the context.

### 5.2. InheritableThreadLocal Does Not Automatically Propagate Context Per Task

`InheritableThreadLocal<T>` allows a child thread to receive an inherited value when the thread is created, according to the API contract. It **does not guarantee** that each task submitted to a thread pool will receive the submitting thread's current context: workers may have been created earlier and reused. With mutable values, inheriting a reference can also cause unintended shared state.

Do not use `InheritableThreadLocal` assuming it provides a "request context" propagation mechanism across all executors. If per-task context is needed, **pass the data explicitly**, and only set/restore it within the task scope on the actual executing thread when truly necessary.

## 6. How Interrupt, Timeout, Cancel, and Exceptions Affect Cleanup

### 6.1. Interrupt Is a Cooperative Signal, Not a Kill Switch

Calling `Thread.interrupt()` asks the thread to pay attention to its interrupted status. Blocking operations that support interruption—such as `Thread.sleep`, `Object.wait`, `Thread.join`, and certain waits in concurrency APIs—can throw `InterruptedException`. When this exception is thrown, the interrupted status is typically cleared per the method's contract; if you catch it and do not propagate it, consider restoring it with `Thread.currentThread().interrupt()`, then exiting the work or signaling the caller.

~~~java
// Illustrative snippet inside a task; resource is AutoCloseable.
try (var resource = openResource()) {
    doInterruptibleWork(resource);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Exit the task or report cancellation per contract.
}
~~~

`openResource()` and `doInterruptibleWork(...)` are **structural placeholders**, not built-in Java APIs; this snippet is not a standalone program. The takeaway is that the resource is closed when exiting `try-with-resources` due to an interrupt. Even so, not every I/O operation or third-party library responds to interrupts immediately.

### 6.2. Future.cancel and ExecutorService.shutdownNow

- `Future.cancel(true)` attempts to cancel the task, allowing the running thread to be interrupted if the task is running and the implementation supports it. This is **not a guarantee** that task code stops immediately.
- `Future.get(timeout, unit)` only limits **the caller's wait time**. `TimeoutException` does not automatically stop the task or close its resources.
- `ExecutorService.shutdown()` stops accepting new work; already-accepted tasks can still run.
- `ExecutorService.shutdownNow()` attempts to stop running tasks via interrupt and returns the list of waiting tasks that have not started; it does not guarantee all workers have actually stopped.
- `awaitTermination(...)` lets the caller wait for the executor to finish within a timeout; if it expires, a follow-up policy is needed.

**Resource consequence:** `finally`/`try-with-resources` inside a task only runs when the task's control flow actually exits the scope. If a task ignores interrupts and keeps running, calling `cancel` or `shutdownNow` cannot magically close resources held inside that task. Design tasks with cooperative exit paths and appropriate deadlines.

### 6.3. Executor Management Pattern on Java 17

~~~java
// ExecutorShutdownDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            pool.execute(() -> System.out.println("task complete"));
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        System.err.println("executor still running");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Stdout on a normal run:

~~~text
task complete
~~~

Explanation: `shutdown()` prevents new tasks from being accepted; `awaitTermination` waits up to the specified time; if not finished, `shutdownNow()` requests cancellation to the extent the implementation allows. In a normal run, a task prints a message and finishes very quickly. In real systems, timeouts and failure reporting policies must match application requirements, and callers need to know when shutdown fails.

**Version note:** On Java 17, `ExecutorService` does not yet have `AutoCloseable.close()` from newer APIs, so manage `shutdown`/`awaitTermination` explicitly as shown. Do not copy `try (ExecutorService executor = ...)` from newer JDK documentation and expect it to compile under Java 17.

### 6.4. Uncaught Exceptions and Cleanup

An uncaught exception can cause `Thread.run()` to terminate; for a manual `Thread`, the JVM has an uncaught-exception handler mechanism to report errors. However, this is **not** a way to automatically clean up resources opened in the wrong scope. `finally` and `try-with-resources` in unwinding stack frames still run under normal Java execution. For tasks submitted via `ExecutorService.submit`, errors are typically captured in the `Future` and observed when calling `get()`. Do not rely solely on log handlers to know whether a task completed successfully.

## 7. Difference Between ThreadLocal and Parameter-Passed Resources

Suppose a worker processes task A and then task B:
- Using a **parameter** `process(order, requestId)`: the value belongs to the call, has clear boundaries, and is not stored on the worker.
- Using **ThreadLocal** for `requestId`: methods deep in the call stack can read it without taking a parameter, but any code on the same thread can read the same mapping and cleanup must be guaranteed. If code hands off a step to another thread, the new thread does not automatically have the value.
- Using a **shared mutable object** across multiple workers: thread safety of the object must be designed independently of lifecycle; `ThreadLocal` does not make that object immutable or prevent races if multiple threads point to the same instance.

Practical rule: **prefer processing-scoped state**, and only store thread-scoped state when there is a clear API, performance, or execution-context reason. A thread is a tool for running work, not necessarily a business "request" unit.

## 8. Diagnosing Resources Held Too Long

### Common Symptoms

| Symptom | Possible Cause to Check |
| --- | --- |
| A later request sees the ID/context of a previous request | `ThreadLocal` or thread metadata was not cleaned up/restored on a reused worker |
| Heap grows over time even though requests have completed | `ThreadLocal` values, caches/task queues, or object graphs remain retained |
| Increasing number of file descriptors/sockets/connections | Off-heap resources were not `close`d at the right time |
| Application refuses to exit after stopping new work | Executor was not `shutdown`, workers did not terminate, or tasks block/ignore interrupts |
| Task was canceled but still holds connections for a long time | Timeout/cancel only stopped the caller from waiting; the task did not exit its scope or the API does not support interruption |
| Task running on another thread loses context | `ThreadLocal` does not travel with the task; reused thread pools do not guarantee `InheritableThreadLocal` |

### How to Find the Root Cause

1. **Identify the owner**: who opened the file/connection, who `set` the `ThreadLocal`, who created the executor? Write down the exact boundary: method call, task, request, worker, or entire application.
2. **Measure actual lifetime**: when the work finishes, is the resource closed? Measure open connections/descriptors, heap or queues holding tasks, and live worker counts.
3. **Trace exit paths**: do exceptions, early returns, cancellations, timeouts, and interrupts pass through `finally`/`try-with-resources`? Is any branch missing cleanup?
4. **Test thread pool reuse**: run multiple consecutive tasks on the same worker to detect stale `ThreadLocal` data; do not test with two fresh threads and conclude there is no bug.
5. **Inspect thread dumps if a worker is suspected stuck**: `jcmd <PID> Thread.print -l` can help view the state/call stacks of active threads, though it **does not tell you whether all streams or ThreadLocals were cleaned up**. Combine with logs, heap dumps, or appropriate resource measurement tools when needed.
6. **Fix according to the ownership contract**: close resources where they are owned; `remove` task-scoped `ThreadLocal` at the end of the task; restore temporary context state; shut down application-owned executors according to their lifecycle.

Do not assume a "memory leak" whenever the heap is large: valid caches, uncollected garbage before GC runs, backed-up task queues, thread-locals holding values, or out-of-scope references can produce similar symptoms. Trace the objects and when they remain referenced.

## 9. Design Checklist and Pitfalls to Avoid

- **Task opens a resource** → use `try-with-resources` if it is `AutoCloseable`; ensure closing even on error.
- **Task sets a ThreadLocal** → `remove()` in `finally`, or save/restore the previous value if handling nested contexts.
- **Task changes thread name/context loader** → save the prior value and restore it in `finally`.
- **Thread uses a lock** → acquire the lock successfully, then `unlock()` in `finally`.
- **Executor owned by the current component** → `shutdown()` and wait for completion with a bound, handling interrupts/cancellations appropriately.
- **Task needs to be stoppable** → respond to interrupts or provide a cooperative cancellation mechanism; do not rely on `Thread.stop()` (unsafe/deprecated).
- **Multiple workers** → do not use `ThreadLocal` to pass return values or assume context is shared across threads.
- **Using daemon threads** → do not treat daemon threads as a mechanism to flush/close resources when the JVM exits.
- **Values cached per thread** → consider memory cost multiplied by worker count and specific cleanup/eviction needs.
- **Exceptions in executor tasks** → observe the `Future` result, because errors may not surface as expected if you only `submit` and discard the future.

### Common Misconceptions

**"The request is done, so ThreadLocal will empty itself."** False if the worker stays alive; the mapping is per **thread**, not per request.

**"Calling ThreadLocal.remove() will close the Connection."** False: `remove` only detaches the binding. `Connection.close()` follows its own ownership contract.

**"When a thread ends, the JVM closes all sockets/files it opened."** There is no such guarantee. Threads and I/O resources have different lifecycles.

**"Future.get(timeout) timing out means the task was canceled."** False: the caller stopped waiting; the task may still be running.

**"Using InheritableThreadLocal automatically carries context across submit()."** False with pools: inheritance happens at thread creation, not on every task submission.

**"shutdownNow() is guaranteed to stop everything immediately."** False: it attempts to interrupt running tasks; tasks must cooperate and may not exit.

**"Waiting on join() replaces close()."** False: `join` waits for execution to finish; the task's resources must be closed by the task itself or their owner within the proper scope.

## 10. Self-Check Questions

1. **An `ExecutorService` has only one worker. Task A sets a `ThreadLocal` and finishes without removing it. What does Task B read?** Without other overwrites or cleanup, B can read A's value because both run on the same thread.
2. **Task A uses a `BufferedReader` in `try-with-resources`, while the worker stays alive. Is the reader closed?** Yes, it is closed upon leaving the scope, without waiting for the worker to die.
3. **What problems can arise from catching `InterruptedException` and continuing as if nothing happened?** It loses the cancellation/stop signal, prolonging the task and keeping resources held longer; consider propagating it or restoring the interrupt and exiting.
4. **If a `ThreadLocal` holds a `Socket`, does calling `remove` close the socket?** No; the owner must close the socket according to its contract.
5. **If you change the context class loader inside a task, do you need to restore it?** Yes, so that the reused worker does not carry the previous task's loader.
6. **If you call `shutdown()` and exit `main`, is the pool guaranteed to have finished?** No; you need to wait or structure the lifecycle appropriately if a deterministic completion point is required.
7. **Does using `InheritableThreadLocal` for a pool created at application startup guarantee that new tasks see the submitting thread's context?** No, because inheritance happens when workers are created, not on each task submission.

**Key takeaway:** Identify **which scope a resource belongs to**, and place **cleanup at the end of that exact scope**. Threads can outlive tasks; therefore, clearing `ThreadLocal`, restoring context, releasing locks, and closing I/O must be performed proactively by the owning code. `Thread.join()`, `Future.get()`, and `ExecutorService.shutdown()` help coordinate execution lifecycles, but they do not replace application resource cleanup.
