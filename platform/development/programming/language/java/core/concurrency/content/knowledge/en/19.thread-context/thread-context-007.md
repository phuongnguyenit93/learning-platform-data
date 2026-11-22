# ThreadLocal When Running Thousands of Virtual Threads in Java 21+

`ThreadLocal<T>` allows each thread to store and read **that thread's own value** without having to pass the value through every method parameter. Virtual threads since Java 21 still support `ThreadLocal` just like platform threads. However, when the number of virtual threads grows from a few dozen to thousands or millions, assumptions about caching, lifetime, and thread reuse can cause the application to consume unnecessary memory.

The scope of this article is **pure Java concurrency**, without depending on Spring. We will observe the per-virtual-thread context, learn how to propagate context across thread boundaries, release bindings, recognize the memory cost of `withInitial(...)`, and choose alternatives.

## 1. Principles of ThreadLocal

| API | Behavior |
|---|---|
| `get()` | Reads the **current thread's** copy of the value; if not yet present, initializes it using `initialValue()` (`null` by default). |
| `set(value)` | Sets the **current thread's** value; does not set the value for other threads. |
| `remove()` | Removes the current thread's binding; subsequent `get()` calls may invoke the initializer again. |
| `ThreadLocal.withInitial(supplier)` | Creates a `ThreadLocal` with a **lazy** initialization supplier, invoked per thread on its first `get()`. |

A `static final ThreadLocal<String> TRACE` variable is a **shared key** for lookup, but the value `TRACE.get()` resides in each thread's state. If thread A calls `TRACE.set("A")`, thread B does not automatically see `"A"`.

A virtual thread is still a `java.lang.Thread` object. `ThreadLocal` data is attached to the **virtual thread running the code**, not to the carrier thread — the platform thread temporarily executing the virtual thread.

~~~text
                 static final ThreadLocal<String> TRACE
                                  |
             same key, separate binding per thread
                                  |
         +------------------------+--------------------+
         |                        |                    |
  Virtual Thread V1        Virtual Thread V2      Main Thread
  TRACE = "req-1"          TRACE = "req-2"        TRACE = "caller"
         |
      carrier A
         |
     waits on compatible I/O -> virtual thread unmounts
         |
      carrier B
      TRACE is still V1's "req-1"
~~~

When a virtual thread unmounts from one carrier and resumes on another carrier, **its binding is not lost and does not become the carrier's binding**. Conversely, handing work off to **another virtual thread** can lose context if it is not passed explicitly.

## 2. Runnable Example: Three Virtual Threads, Three Request IDs

Save the file **`ThreadLocalVirtualDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalVirtualDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private static String nestedCall() {
        return REQUEST_ID.get();
    }

    public static void main(String[] args) throws Exception {
        REQUEST_ID.set("caller");
        try {
            System.out.println("caller=" + REQUEST_ID.get());

            try (ExecutorService executor =
                         Executors.newVirtualThreadPerTaskExecutor()) {

                List<Future<String>> futures = new ArrayList<>();

                for (int id = 1; id <= 3; id++) {
                    final int taskId = id;
                    futures.add(executor.submit(() -> {
                        String before = REQUEST_ID.get();
                        REQUEST_ID.set("req-" + taskId);
                        try {
                            return "task-" + taskId
                                    + " before=" + before
                                    + " nested=" + nestedCall()
                                    + " virtual="
                                    + Thread.currentThread().isVirtual();
                        } finally {
                            REQUEST_ID.remove();
                        }
                    }));
                }

                for (Future<String> future : futures) {
                    System.out.println(future.get());
                }
            }

            System.out.println("caller-after=" + REQUEST_ID.get());
        } finally {
            REQUEST_ID.remove();
        }
    }
}
~~~

Compile/run with JDK 21+:

~~~bash
javac ThreadLocalVirtualDemo.java
java ThreadLocalVirtualDemo
~~~

Stdout:

~~~text
caller=caller
task-1 before=null nested=req-1 virtual=true
task-2 before=null nested=req-2 virtual=true
task-3 before=null nested=req-3 virtual=true
caller-after=caller
~~~

Observations:

1. `main` assigns `"caller"` to the main thread's `ThreadLocal`.
2. Each `executor.submit(...)` creates a **new virtual thread**. A regular `ThreadLocal` **does not automatically inherit** values from the submitting thread, so `before=null`.
3. Within each task, `set("req-N")` creates its own binding. `nestedCall()` reads that exact value even without taking parameters, because it still runs **on the same virtual thread**.
4. `finally { REQUEST_ID.remove(); }` removes the virtual thread's binding, without removing `"caller"` on the main thread.
5. Tasks run/complete in a non-deterministic schedule; stdout has a deterministic order because the `for` loop calls `Future.get()` in list order.

**Takeaway:** carrying context along the call stack **within a single thread** is what `ThreadLocal` is capable of. To cross **to a new thread**, context must be passed explicitly.

## 3. Why Does the Number of Virtual Threads Change Memory Cost?

In `Executors.newFixedThreadPool(16)`, many tasks reuse 16 platform worker threads. A `ThreadLocal` that initializes a per-worker cache may create around 16 objects if every worker accesses it. However, `Executors.newVirtualThreadPerTaskExecutor()` creates **a new virtual thread per task**; virtual threads are not pooled to run multiple different tasks. Therefore, per-thread caches are allocated **repeatedly for every task**.

Example of an anti-pattern (snippet, not a standalone program):

~~~java
static final ThreadLocal<byte[]> PER_THREAD_BUFFER =
        ThreadLocal.withInitial(() -> new byte[64 * 1024]);

void process() {
    byte[] buffer = PER_THREAD_BUFFER.get();
    // Use buffer here ...
}
~~~

If **10,000 virtual threads are alive concurrently** and each thread has called `get()` on a 64 KiB buffer, the array data alone has a nominal size of **625 MiB** (`10_000 × 64 KiB`), excluding object headers, thread stacks, maps, or other objects. This is only an illustrative calculation, **not a measurement of JVM peak heap**. For short-lived tasks, GC can reclaim many buffers; for tasks waiting on long I/O, many buffers can remain alive simultaneously.

Distinguish two metrics:

- **Total allocations over the runtime**: grows with the number of virtual threads that call `get()` on the `ThreadLocal`.
- **Retained memory at a point in time**: depends on how many live virtual threads still reference the buffer, and the size of the reachable objects.

`ThreadLocal.withInitial(...)` is **lazy**: merely declaring the key does not create 10,000 objects immediately. However, each thread calling `get()` for the first time creates a new value, even if other threads already have values.

In particular, avoid using `ThreadLocal` to cache `SimpleDateFormat`, large buffers, or connections with the expectation of reuse across multiple tasks on **one virtual thread**; that does not happen with the thread-per-task model. Prefer a shared immutable `DateTimeFormatter`, scoped resource management, or a real pool for expensive resources (such as a DB connection pool). Do not use `ThreadLocal` as a mechanism to limit the number of requests to downstream services.

## 4. Runnable Example: 1,000 Tasks Creating 1,000 Buffers

Create the file **`ThreadLocalAllocationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadLocalAllocationDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ThreadLocal<byte[]> BUFFER =
            ThreadLocal.withInitial(() -> {
                CREATED.incrementAndGet();
                return new byte[1024];
            });

    public static void main(String[] args) throws Exception {
        int tasks = 1_000;

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < tasks; i++) {
                futures.add(executor.submit(() -> {
                    try {
                        BUFFER.get()[0] = 1;
                    } finally {
                        BUFFER.remove();
                    }
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("tasks=" + tasks);
        System.out.println("buffer-initializations=" + CREATED.get());
    }
}
~~~

Run:

~~~bash
javac ThreadLocalAllocationDemo.java
java ThreadLocalAllocationDemo
~~~

Stdout:

~~~text
tasks=1000
buffer-initializations=1000
~~~

`CREATED` uses `AtomicInteger` to count accurately across concurrent tasks. Each task runs on a new virtual thread and calls `BUFFER.get()` once, so the supplier runs exactly **1,000 times**. `remove()` cleans up each thread's binding, but **does not create a mechanism to reuse** the buffer for other threads.

If `BUFFER.get()` is omitted, the supplier will not run; if `remove()` is called and then `get()` is called again **on the same thread**, the supplier is invoked again. Do not use the runtime of a small example to draw conclusions about real-world application performance.

## 5. Value Lifetime and Proper Cleanup

A small `ThreadLocal<String>` holding a trace ID or correlation ID can be reasonable when many deeply nested functions within the same task need the context, and you do not want to pass parameters through an entire legacy library.

Pattern where a task owns the binding from start to finish:

~~~java
// Illustrative snippet inside a Runnable; TRACE is already declared.
TRACE.set(traceId);
try {
    handleTask();
} finally {
    TRACE.remove();
}
~~~

For nested contexts, when code is called on a thread that **already has** a value, avoid accidentally clearing the caller's binding:

~~~java
// Snippet: save and restore if the contract defines null as "absent".
String previous = TRACE.get();
TRACE.set(traceId);
try {
    handleTask();
} finally {
    if (previous == null) {
        TRACE.remove();
    } else {
        TRACE.set(previous);
    }
}
~~~

This is only a snippet; `handleTask()` and `TRACE` are provided by the calling code. If using `ThreadLocal.withInitial(...)`, calling `get()` to capture `previous` may initialize a value itself; choose a binding model that matches your application's default/absent semantics.

Use `try/finally` to clean up across normal return, exception, retry, timeout, or cancellation paths. Benefits:

- Releases references to data (including large object graphs) as soon as the task no longer needs it.
- Ensures a subsequent operation on **the same thread** does not mistakenly read stale context.
- Safer compatibility if the library is also used on a **platform thread pool**: reused workers can easily leak the previous task's binding into the next task if `remove()` is forgotten.
- Keeps request/task lifecycle boundaries clear.

**Do not claim that every ThreadLocal on a virtual thread leaks permanently:** when a virtual thread terminates and the values have no other references, they can be reclaimed by GC. The main risk is **too many concurrently live threads retaining objects**, or objects being kept alive by external references. `remove()` helps clean up early, but does not replace backpressure, timeouts, and bounding outstanding tasks.

`set(null)` is not the same as `remove()`: `set(null)` sets a binding whose value is `null`; `remove()` deletes the binding so a subsequent `get()` can invoke the initializer again.

## 6. Propagating Context Across Thread Boundaries

`ThreadLocal` normally **does not propagate** the submitting thread's value to a virtual thread. Here is an example snippet:

~~~java
TRACE.set("trace-A");
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() -> TRACE.get());
    // future.get() will be null if the new thread has not set TRACE.
}
~~~

The clearest approach is to **capture an immutable value and pass it as a parameter**:

~~~java
// Snippet: traceId and process(String) are declared at the call site.
final String capturedTraceId = traceId;
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() -> process(capturedTraceId));
    future.get();
}
~~~

If a legacy API only reads `ThreadLocal`, wrap each task to call `set()` **inside the executing thread**, then clean up with `finally`. If wrappers can be nested, save and restore the previous value according to your application's contract.

Do not confuse a **virtual thread switching carriers** with **work moving to another virtual thread**. The former does not change `ThreadLocal`. The latter requires explicit context propagation. When using `CompletableFuture`, callbacks, worker pools, or other executors, identify exactly which code runs on which thread before relying on implicit context.

## 7. How Does InheritableThreadLocal Inherit?

`InheritableThreadLocal<T>` differs from `ThreadLocal<T>` in that it can copy the parent thread's **initial value** into the child thread **at thread creation time**. With `Thread.Builder`, the default behavior is to inherit; this can be disabled via `inheritInheritableThreadLocals(false)`.

Create the file **`InheritableVirtualDemo.java`**:

~~~java
public class InheritableVirtualDemo {
    private static final InheritableThreadLocal<String> CONTEXT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        CONTEXT.set("from-parent");
        try {
            Thread inherited = Thread.ofVirtual().start(() ->
                    System.out.println("inherited=" + CONTEXT.get()));
            inherited.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() ->
                            System.out.println("isolated=" + CONTEXT.get()));
            isolated.join();
        } finally {
            CONTEXT.remove();
        }
    }
}
~~~

Run:

~~~bash
javac InheritableVirtualDemo.java
java InheritableVirtualDemo
~~~

Stdout:

~~~text
inherited=from-parent
isolated=null
~~~

`inherited.join()` ensures the first line is printed before creating and waiting for the second thread. With `inheritInheritableThreadLocals(false)`, the child does not receive the `"from-parent"` binding. An already-created child **is not automatically synchronized whenever the parent changes its value** afterward.

Important warning: `InheritableThreadLocal.childValue(parentValue)` returns **the same reference** by default. If the value is an `ArrayList` or a mutable object, parent and child can reference the same object even though each thread has its own binding. There is no automatic deep copy. Automatically inheriting many bindings across thousands of threads can also increase overhead and carry unintended data; do not convert all `ThreadLocal`s into `InheritableThreadLocal`s to "fix" every propagation issue.

## 8. Alternatives Suited to Your Needs and JDK Version

| Need | Option | Advantage |
|---|---|---|
| Only a few functions need request/trace ID | Parameters or immutable `record RequestContext(...)` | Clear data flow, easy to test |
| Legacy library reads context deep in the same task | Small `ThreadLocal`, cleaned up with `finally` | Compatible with Java 21 |
| Read-only context with lexical scope | `ScopedValue` depending on JDK version | Bounds binding lifetime and reduces overhead |
| Immutable formatter reused across many tasks | `static final DateTimeFormatter` | Safe sharing, no per-thread cache allocation |
| Finite resources (DB connections) | Connection pool, `Semaphore`, backpressure | Properly limits the resource |

`ScopedValue` is a **preview API since JDK 21**, continued in subsequent previews, and **finalized in JDK 25** (JEP 506). The syntax below is a **snippet for JDK 25+**, not a default runnable Java 21 program:

~~~java
private static final ScopedValue<String> TRACE = ScopedValue.newInstance();

ScopedValue.where(TRACE, "trace-123").run(() -> {
    System.out.println(TRACE.get());
});
// Outside run(), this scope's binding is no longer present.
~~~

In a valid declaration context, the snippet above prints `trace-123`. `ScopedValue` is well-suited for **read-only context within a call scope**, and provides controlled inheritance with structured concurrency. Do not assume by default that bindings automatically propagate to **any** `executor.submit(...)`. On JDK 21 without preview features, prefer parameter passing or a `ThreadLocal` with an explicit lifecycle.

## 9. Inspecting and Optimizing Systems with Thousands of Virtual Threads

Before migrating a library to virtual threads or optimizing `ThreadLocal`, measure what actually affects load:

1. How many **bytes** does each `ThreadLocal` value hold, and is it referencing large buffers/caches/connections/object graphs?
2. How many **virtual threads are alive concurrently**, not just the total number of tasks processed since application startup?
3. How many times is the `withInitial(...)` supplier invoked; is it creating expensive objects **per task**?
4. Do success, exception, timeout, cancel, and retry paths all properly clean up or restore context?
5. Is any context lost when crossing `CompletableFuture`, new thread, or other executor boundaries?
6. Do DB/network/connection pools have clear timeouts and limits; does the producer apply backpressure before submitting in bulk?

Use JFR, an allocation profiler, heap dumps, heap usage/GC metrics, outstanding task counts, and p95/p99 latency under realistic load. If you see many byte arrays or cache objects kept alive through virtual-thread contexts, identify **who creates and who retains** those values before making changes. Third-party libraries can also create thread-local caches implicitly.

### Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming bindings follow the carrier | Wrong context when the JVM remounts | Bindings are attached to the virtual thread |
| Using `withInitial` to cache large buffers per thread | Thousands of allocations and potentially large heap retention | Use immutable shared objects, allocate per scope |
| Not cleaning up context | Retains data longer, or leaks previous task on a worker pool | `try/finally` and `remove()`/restore |
| Thinking `ThreadLocal` auto-propagates to new threads | Child task reads `null` | Capture and pass parameters / wrap task |
| Inheriting mutable objects via `InheritableThreadLocal` | Parent/child may unsafely share the same object | Pass immutable values, control inheritance |
| Using `set(null)` instead of `remove()` | Does not re-initialize as expected | Delete binding with `remove()` |
| Submitting unbounded tasks waiting on DB | Many virtual threads hold memory and queue up | Backpressure, limits, timeouts |
| Using JDK 25 `ScopedValue` API on default JDK 21 | Fails to compile | Distinguish preview in 21 vs. finalized in 25 |

## 10. Self-Check

**Question 1:** A virtual thread moves from carrier A to B. Does `ThreadLocal` change to B's value? **No.** The data belongs to the virtual thread.

**Question 2:** `ThreadLocal.withInitial(() -> new byte[65536])` has `get()` called on 10,000 virtual threads. Is there one shared buffer? **No.** Up to 10,000 separate buffers may be created; peak heap also depends on how many virtual threads/buffers are alive at the same time.

**Question 3:** A virtual thread finishes without calling `remove()`. Does it always leak permanently? **No.** Values can be reclaimed by GC when no references remain. Early cleanup is still recommended.

**Question 4:** The main thread calls `TRACE.set("A")` and then `executor.submit(() -> TRACE.get())`. Does the new task see `"A"`? **No**, if `TRACE` is a regular `ThreadLocal` and the task has not set it itself.

**Question 5:** Should every context be converted to `InheritableThreadLocal`? **No.** Inheritance only happens at thread creation time, and mutable values can end up with shared references.

**Practice:** Try changing the allocation example to 100, 1,000, and 10,000 tasks; observe `CREATED`. Replace the array cache with a shared `DateTimeFormatter` and analyze the difference in initialization counts. Add an exception path to the request ID example to verify that `finally` always cleans up.

## 11. Key Takeaways

- `ThreadLocal` works on Java 21+ virtual threads, and values are attached to the **virtual thread**, not the carrier.
- Very large numbers of virtual threads can lead to **very large numbers of bindings and object copies**. Do not use `ThreadLocal` as a cache reused across multiple tasks that each have their own virtual thread.
- `withInitial` initializes lazily per thread; `remove()` deletes the current thread's binding. Manage scope with `try/finally`.
- Regular `ThreadLocal` does not propagate to other threads. `InheritableThreadLocal` only inherits when creating a child thread; be careful with mutable values.
- Prefer immutable parameters/records when possible; `ScopedValue` is finalized in JDK 25, while in JDK 21 it is preview.
- Measure allocations, heap/GC, concurrent virtual thread counts, and downstream resources before optimizing.

### Official Documentation

- Java SE 21 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 21 `Thread` and inheritance: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- Oracle Java 21 Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- JEP 506 — Scoped Values (JDK 25): https://openjdk.org/jeps/506
