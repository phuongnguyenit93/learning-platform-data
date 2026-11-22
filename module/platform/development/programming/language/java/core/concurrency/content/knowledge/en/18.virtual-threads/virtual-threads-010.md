# ThreadLocal and Per-Virtual-Thread Data Overhead

## 1. Problem Statement

Since Java 21, **virtual threads** (JEP 444) allow Java to run a very large number of concurrent tasks, especially when tasks are waiting on I/O. Every virtual thread is still a `java.lang.Thread`; the JVM can park it, return the platform thread running it (commonly called a *carrier*) to the scheduler, and later resume the virtual thread on another carrier.

`ThreadLocal<T>` remains fully supported: **each virtual thread has its own value for each ThreadLocal key**. When a virtual thread switches carriers, the value is not lost, is not transferred to another virtual thread, and does not belong to the carrier. The issue lies in **data scale**: the number of concurrently live virtual threads can be far greater than the traditional number of platform threads. Caches or state attached to each thread can become a major source of heap consumption and allocations.

For example, a legacy application has 32 platform threads in a pool, with each thread holding a 64 KiB buffer via `ThreadLocal`. The total payload is estimated at 2 MiB when all 32 threads are initialized. Moving the same logic to 10,000 live virtual threads, where each thread creates its own 64 KiB buffer, results in a payload alone of roughly **625 MiB**, excluding metadata, object headers, stacks, references, and other objects. This is a capacity estimate, **not a benchmark**.

Goal: understand `ThreadLocal` on virtual threads, distinguish memory cost from scheduling capability, organize data lifecycles properly, and choose alternative APIs when needed.

## 2. What Does ThreadLocal Store and Where?

A `ThreadLocal<T>` instance is a **key** that lets the current thread access its own value; a shared key does not mean a shared value. The methods are:

| API | Behavior |
| --- | --- |
| `new ThreadLocal<>()` | The initial value for a thread that has not set one is `null`. |
| `ThreadLocal.withInitial(supplier)` | Creates a value when the thread first calls `get()`; after `remove()`, a subsequent `get()` call can reinitialize it. |
| `get()` | Returns the value of the **currently executing** thread. |
| `set(value)` | Associates the value with the current thread without updating other threads. |
| `remove()` | Removes the current thread's association with the key. |

In the JDK, these associations are managed by a map-like structure attached to the `Thread` object. On a virtual thread, that map belongs to the **virtual thread**, not the carrier. The data cost applies only to the ThreadLocals **actually used**—creating a virtual thread does not immediately allocate buffers for every `ThreadLocal.withInitial` declared in the program.

Illustrative sequence:

1. Virtual thread V1 calls `TRACE_ID.set("A")`.
2. V1 waits for I/O and is parked; the carrier can switch to running V2.
3. V2 calls `TRACE_ID.get()`: it reads V2's own value and does not automatically see `"A"`.
4. V1 resumes on another carrier: `TRACE_ID.get()` still returns `"A"`, until V1 modifies or removes the value.

**Limitation:** `ThreadLocal` preserves the isolation of per-thread mappings; it does not make a mutable object shared by other means thread-safe. If two ThreadLocal values point to the same object, code modifying that object still needs synchronization when required.

## 3. Java 21+ Example: Isolated Data Persisting Across Method Calls

Save as `VirtualThreadLocalDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadLocalDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static String handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            return "virtual=" + Thread.currentThread().isVirtual()
                    + ", id=" + readFromNestedMethod();
        } finally {
            REQUEST_ID.remove();
        }
    }

    static String readFromNestedMethod() {
        return REQUEST_ID.get();
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first = executor.submit(() -> handle("REQ-101"));
            Future<String> second = executor.submit(() -> handle("REQ-202"));

            System.out.println(first.get());
            System.out.println(second.get());
        }
        System.out.println("Caller=" + REQUEST_ID.get());
    }
}
```

Compile and run with JDK 21 or later, no preview flags needed:

```bash
javac -encoding UTF-8 VirtualThreadLocalDemo.java
java VirtualThreadLocalDemo
```

Exact output:

```text
virtual=true, id=REQ-101
virtual=true, id=REQ-202
Caller=null
```

`Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread for each task. `Future.get()` is read sequentially, so the order of the first two lines is deterministic. `readFromNestedMethod()` implicitly receives context via `ThreadLocal` within the same virtual thread; the main thread does not have that value. The `finally` block ensures the value is cleaned up even when handling errors.

Note: `REQUEST_ID.remove()` only removes the value in the **calling thread**. Calling `remove()` on the main thread cannot clean up ThreadLocals of other workers.

## 4. Memory Cost and Lifecycle in Practice

There are three cost categories:

- **The virtual thread itself:** object, execution state, continuation/stack, and other references the JVM must manage.
- **ThreadLocal storage structure:** metadata and entries for the keys used.
- **Values and retained object graphs:** Strings, byte arrays, buffers, contexts, caches, resources, or objects referenced by those values.

You can think of it as:

```text
Total live ThreadLocal data ≈
  sum of values and metadata still retained by live virtual threads
```

Object sharing and garbage collection semantics mean this is not an exact heap measurement formula. If two values point to the same immutable object, you do not double-count that object's size. Conversely, a tiny value can reference a large object graph.

**Two numbers to distinguish:** the *total number of virtual threads created* and the number of threads *concurrently live at the same time*. One million short-lived tasks running in batches can create heavy **allocation/GC** pressure without necessarily holding data for all million threads in the heap at once. On the other hand, tens of thousands of virtual threads waiting on the network or retained by other references can keep ThreadLocal data alive longer than expected.

### Per-Thread Caches Are No Longer Per-Worker Caches

This is the easiest pitfall when migrating from a platform-thread pool to virtual-thread-per-task.

- A pool of 16 platform threads: a `ThreadLocal.withInitial` cache can be reused across many tasks running sequentially on the same worker.
- A virtual thread per task: each task is a different thread; the initialized cache is only reused **within that single task**, and may then be discarded with the thread.
- If one million tasks each create a 64 KiB cache, the **allocation count** and memory bandwidth are huge even if one million caches do not exist simultaneously.

Do not solve this by pooling virtual threads to reuse buffers. The recommended model is one virtual thread per task; if you need to pool expensive resources, create a **separate bounded resource pool**, independent of thread identity.

## 5. Java 21+ Example: Observing Per-Task Initialization Cost

Save as `VirtualThreadLocalCostDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLocalCostDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ThreadLocal<byte[]> BUFFER =
            ThreadLocal.withInitial(() -> {
                CREATED.incrementAndGet();
                return new byte[64 * 1024];
            });

    private static boolean task() {
        try {
            byte[] first = BUFFER.get();
            byte[] second = BUFFER.get();
            return first == second;
        } finally {
            BUFFER.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 4; i++) {
                results.add(executor.submit(
                        VirtualThreadLocalCostDemo::task));
            }
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    throw new IllegalStateException("Not the same buffer");
                }
            }
        }
        System.out.println("Buffers created: " + CREATED.get());
    }
}
```

```bash
javac -encoding UTF-8 VirtualThreadLocalCostDemo.java
java VirtualThreadLocalCostDemo
```

```text
Buffers created: 4
```

Each virtual thread calls `get()` twice and receives the **same buffer within that thread**. However, four tasks correspond to four virtual threads; the supplier runs four times. `AtomicInteger` ensures accurate counting in a multithreaded environment. After `remove()`, if that thread calls `get()` again, the supplier can run again and allocate a new buffer.

This example uses a small number of tasks to demonstrate the mechanism. Do not arbitrarily scale this demo to hundreds of thousands of concurrent tasks with large buffers on a machine with limited heap.

## 6. Proper Cleanup and Reference-Retention Risks

A useful rule for per-task context is **set, use, clean up in `finally`**. The following snippet illustrates a method inside a class, not a standalone program:

```java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static void process(String traceId) {
    TRACE_ID.set(traceId);
    try {
        doWork();
    } finally {
        TRACE_ID.remove();
    }
}
```

If nested contexts need to restore the previous value after processing a child branch, `remove()` alone is not enough; you must design saving and restoring parent state with proper semantics. Avoid letting libraries deep in the call chain arbitrarily mutate values expected to be invariant.

**Does ThreadLocal cause a permanent memory leak?** Missing `remove()` in a virtual thread does not automatically cause a permanent leak. Once a virtual thread terminates and is no longer referenced, the data associated with it can be garbage-collected. However, if the thread stays alive for a long time (including waiting on I/O), the value can still be retained; code running on a platform-thread pool can also retain state across multiple requests. Therefore, intentional cleanup helps control lifecycles and prevent data leakage between tasks when code runs in different environments.

In the JDK's `ThreadLocalMap` implementation, keys are weak references and values are typically strong references. If a key is no longer referenced elsewhere, old entries are not necessarily cleared immediately; relying solely on key GC to release values is unsafe.

**Do not confuse `remove()` with closing resources.** If a value holds a socket, connection, or `AutoCloseable` resource, `remove()` only drops the association; the code owning the resource must still close it (`close()`/`try-with-resources`). Do not stuff entire request bodies or oversized buffers into ThreadLocal just to avoid passing parameters.

## 7. Differences Between ThreadLocal and InheritableThreadLocal

Regular `ThreadLocal` does not automatically pass values from a parent thread to a newly created thread. `InheritableThreadLocal` supports inheriting the **initial value at thread creation**. In Java 21, `Thread.ofVirtual()` inherits `InheritableThreadLocal` by default; to disable it, call `inheritInheritableThreadLocals(false)`.

Save as `VirtualInheritanceDemo.java`:

```java
public class VirtualInheritanceDemo {
    private static final InheritableThreadLocal<String> TRACE =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        TRACE.set("parent");
        try {
            Thread inheriting = Thread.ofVirtual().start(
                    () -> System.out.println("Inherited: " + TRACE.get()));
            inheriting.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() -> System.out.println("Isolated : " + TRACE.get()));
            isolated.join();
        } finally {
            TRACE.remove();
        }
    }
}
```

```bash
javac -encoding UTF-8 VirtualInheritanceDemo.java
java VirtualInheritanceDemo
```

```text
Inherited: parent
Isolated : null
```

Key points to remember:

- Values are inherited when the new thread is created, **not continuously synchronized** whenever the parent thread calls `set()`.
- For mutable objects, by default the child may receive the same reference as the parent; two threads mutating that object can cause data races. This is not a deep copy.
- Copying inheritable mappings into many virtual threads has a cost, especially when the parent has many entries.
- With executors, you must know which thread **actually creates the virtual thread** and when; do not assume every context at the `submit()` call site is automatically propagated across all executors and async mechanisms.

Do not use `InheritableThreadLocal` as a general-purpose context propagation mechanism across all async boundaries. Clearly identify who creates the thread, who owns the value, and whether the value is allowed to be shared.

## 8. Choosing Alternatives for Context Propagation or Resource Reuse

| Purpose | Suitable Approach to Consider | Notes |
| --- | --- | --- |
| Only a few methods need a value | Explicit parameter passing or immutable record | Clear ownership and lifetime, easy to test. |
| Existing Java 21 libraries relying on local context | `ThreadLocal` with `finally/remove` | Compatible and convenient, but value size must be controlled. |
| Read-only context passed across methods | `ScopedValue` from Java 25 | Lexical-scope lifetime, reduces hidden mutable state. |
| Shared and expensive resources | Bounded resource pool, shared service with clear thread safety | Truly shared across tasks; manages allocation and closing. |
| Limiting concurrent tasks using a resource | `Semaphore` or capacity limit | No need to pool virtual threads to throttle DB/network access. |

### ScopedValue: Distinguishing Java Versions

`ScopedValue` is available as a **preview feature in Java 21–24**; preview APIs can change between releases and require enabling preview. It becomes a standard API starting in **Java 25** (JEP 506). Therefore, the runnable examples above use Java 21+ without preview; the snippet below only illustrates part of a class on **JDK 25+**, not a standalone Java 21 file:

```java
private static final ScopedValue<String> TRACE_ID = ScopedValue.newInstance();

static void dispatch() {
    ScopedValue.where(TRACE_ID, "REQ-7")
            .run(() -> System.out.println(TRACE_ID.get()));
}
```

The bound value exists within the `run` scope and is automatically unbound upon exiting the scope. This is a great fit for read-only context. `ScopedValue` cannot mechanically replace use cases that require arbitrarily mutating local state mid-execution; in those cases, design the API and state according to actual needs.

## 9. Common Misconceptions

**"ThreadLocal values follow the carrier."** False. They are bound to the virtual thread; the scheduler switching carriers does not cause virtual threads to share values.

**"Having one million virtual threads means one million copies of every ThreadLocal."** False. Values are typically initialized on demand; data volume depends on which ThreadLocals are accessed and how many threads are live. However, if every task calls `get()` on a large cache, the cost is genuinely very high.

**"static final ThreadLocal means a static singleton value."** False. The key object is static, while the value mapping remains independent per thread.

**"withInitial runs only once."** False. It runs per thread when initialization is needed and can run again after `remove()`.

**"ThreadLocal makes mutable data inside it safe."** False. If an object is shared through another path or via `InheritableThreadLocal`, data races must be controlled separately.

**"remove closes connections and returns resources to the pool."** False. `remove()` does not `close()` the value and does not manage pool lifecycles.

**"Keep ThreadLocal caches and pool virtual threads for reuse."** Unsuitable for the virtual-thread-per-task model; manage caches or shared resources at a different abstraction layer.

## 10. Measuring and Making Decisions

Before introducing `ThreadLocal` into a workload with many virtual threads:

1. Count the number of **concurrently live** virtual threads, not just total tasks processed.
2. Measure value sizes and objects retained via references; distinguish shared objects from per-task allocated objects.
3. Monitor allocation rate, heap live set, GC pauses, and p95/p99 latency, especially under high load and long I/O waits.
4. Use JFR, a Java heap profiler, or a controlled initialization counter to detect caches being created anew per task.
5. Check whether values are held longer than necessary and whether cleanup runs properly on exceptions.
6. Separate the goal of **context propagation** from **resource reuse**. The latter should generally have an independent pool or capacity limit.
7. If context is read-only and the project is on Java 25+, consider `ScopedValue`. For Java 21 projects, consider explicit parameters or clearly scoped `ThreadLocal`.

Virtual threads improve the scalability of blocking I/O code; they do not make CPU-bound computations faster, nor do they remove downstream database or network limits.

## 11. Self-Check Questions

**Q:** V1 is parked, and V2 runs on the same carrier. Does V2 see V1's `ThreadLocal`?  
**A:** No, because ThreadLocal belongs to each virtual thread.

**Q:** What is the impact of 20,000 virtual threads each holding 128 KiB?  
**A:** The payload alone can reach GiB scale if all are live and holding values simultaneously; you must also account for metadata, other objects, and GC pressure.

**Q:** Does a virtual thread terminating without calling `remove()` guarantee a permanent memory leak?  
**A:** No. Once the thread and data are no longer referenced, they can be collected. The concern is how long the data lives, how many threads remain active, and whether the code might also run on long-lived threads.

**Q:** Does `InheritableThreadLocal` deep-copy a mutable `ArrayList` from parent to child?  
**A:** Not by default; the child may share the reference, so you must design to avoid races.

**Q:** In Java 21, can `ScopedValue` be used directly as a stable API?  
**A:** Not yet. It is in preview in Java 21–24 and becomes a standard API in Java 25+.

**Key takeaway:** `ThreadLocal` still works on virtual threads, but each virtual thread has its own local data. As concurrency scales up, be especially careful with **per-thread caches, large buffers, context inheritance, and cleanup lifecycles**.

### References

- [OpenJDK JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Java 21 API: ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 21 API: Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [OpenJDK JEP 506: Scoped Values](https://openjdk.org/jeps/506)
- [Java 25 API: ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html)
