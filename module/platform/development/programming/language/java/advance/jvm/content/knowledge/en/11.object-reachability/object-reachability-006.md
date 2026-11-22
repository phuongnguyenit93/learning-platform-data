# Java Memory Leaks When Objects Are Still Held by Cache, Listener, or ThreadLocal

Java has a Garbage Collector (GC), but **having a GC does not mean an application cannot have memory leaks**. The GC reclaims objects that are **no longer reachable according to reachability rules**; it cannot conclude on its own that an object, although still having a strong reference path, has **lost its business value**. If an unbounded cache, an unregistered listener, or a `ThreadLocal` retains data across thousands of requests, the object can still be reachable and continuously consume heap.

This lesson is placed in the **reachability** topic on the JVM, using **Java 17** for code and APIs. It is necessary to clearly distinguish **logical memory leaks** (objects no longer needed but still kept alive), **high allocation that has been reclaimed**, **caches intentionally holding data**, and **native memory leaks**. The examples focus on three common sources of reference retention: **cache, listener, ThreadLocal**; then present how to find the **path to GC roots**, read heap dumps, and design resource release lifecycles.

**Key message:** when investigating a Java memory leak, do not only ask “which object is growing?”; also ask **“who is holding a reference to that object and why has that retention path not been cut?”**

## 1. Reachability Is the Mechanism That Decides What Can Be Collected

In the JVM heap model, objects and arrays can reference each other. The GC identifies objects to keep based on a set of **GC roots** and valid reference paths going from roots into the object graph.

```text
GC root: static field APP_CACHE
    |
    v
ConcurrentHashMap
    |
    v
Map entry -> CachedResult -> List -> very large byte[]
                 ^
                 |
            business logic no longer needs it, but cache has not removed entry

The GC still sees a strong reference path from root to byte[].
Therefore byte[] and the objects on the retention path cannot yet be
reclaimed just because the application "no longer uses" them.
```

A **strong reference** is an ordinary reference, for example an `Object value` field, an element in a `List`, or a value in a `Map`. Common retention sources include:

- Static fields of live classes, such as `static final Map`, singletons, registries.
- Local variables/operand-stack references of **active thread frames**, within the range where the VM still considers them live.
- Instance fields and array elements accessed through other reachable objects.
- VM/JNI handle structures according to their corresponding semantics.
- Objects attached to long-lived threads, including entries in the thread-local map.

**An object graph containing a cycle does not by itself create a memory leak.** If `A.next = B` and `B.next = A` but there is no retention path from GC roots to A/B, a tracing GC can still collect the entire cycle. Java GC does not depend on you actively breaking every reference cycle like a simple reference counting system.

### “Reachable” Is Different From “Still Useful”

| Situation | Reachability | Expected Result |
| --- | --- | --- |
| Object currently serving a request | Reachable and still needed | Keep |
| Cached result within size/TTL policy | Reachable and allowed to be kept | Can be kept; this is not by itself a leak |
| Listener of a closed screen still held by event bus | Reachable, past usage lifecycle | **Logical memory leak** |
| Value from an old request in a thread pool worker `ThreadLocal` | Reachable through a live thread, no longer needed | **Logical memory leak**, can also cause data corruption |
| Object with no strong reachability path | May become collectible according to reference processing rules | GC may reclaim when appropriate, **no guaranteed timing** |

Do not use `System.gc()` returning to prove that an object has been reclaimed; `System.gc()` is only a request to perform GC and the VM does not guarantee reclaiming any object immediately.

## 2. Four Important Terms: Allocation, Retention, Reachability, Leak

1. **Allocation:** the JVM creates objects/arrays for computation. An application handling many requests may allocate very quickly, but the GC can also reclaim quickly.
2. **Retention:** references keep a set of objects alive over time. A small object can keep an entire large data tree underneath it alive.
3. **Reachability:** the existence or non-existence of a path from GC roots through reference edges according to the reachability model.
4. **Logical memory leak:** retaining objects that are **no longer needed** longer than their designed lifecycle, often causing the amount of memory needing to be kept to continuously grow or fail to return to the expected level.

There is no formula “large used heap = leak”. In a JVM using GC, you can observe a **sawtooth** heap usage pattern: used increases due to allocations and then drops after collections. If the **post-GC live set** level after comparable workloads keeps rising and does not stabilize, that is a sign to investigate retention.

**Conversely, the absence of `OutOfMemoryError` does not prove there is no leak**: a small leak can accumulate over many days, or still remain below the heap limit at the time of observation.

## 3. GC Roots, Paths, and Retained Size

Consider the diagram:

```text
Root 1: Application.CACHE
   |
   +--> CacheEntry("account-1")
            |
            +--> Report
                  |
                  +--> List<Attachment>
                           |
                           +--> Attachment[1] --> byte[5 MiB]
                           +--> Attachment[2] --> byte[8 MiB]

Root 2: Worker Thread
   |
   +--> ThreadLocalMap
             |
             +--> RequestContext --> Report
```

If the same `Report` is reachable via **two paths**, deleting one cache entry **is not enough** to reclaim Report because `ThreadLocalMap` still holds the remaining path. This is why heap dump tools allow viewing **Path to GC Roots**, **incoming references**, **dominator tree**, and **retained size**.

Distinguishing sizes:

- **Shallow size:** the direct size of that object itself, excluding the objects it references.
- **Retained size:** the total memory that would potentially be freed in terms of reachability if this object and the objects it **exclusively keeps alive** became no longer reachable, according to the heap snapshot's dominator model.
- A `HashMap` entry only takes a few shallow bytes but can keep an entire graph of tens of MiB alive through `value`.
- If an object has another path from GC roots, it is **not necessarily** in the exclusive retained set of the cache entry under consideration.

**Relationship to remember:** when finding a leak, rapidly growing objects are important, but **which object/root is holding them** points to the place that needs fixing. A large `byte[]` does not mean `byte[]` is the buggy component.

### Caution About Snapshot Timing

A heap dump is a **snapshot at a specific point in time**, and does not by itself prove an object has lost business value. A properly designed cache can also have a large retained size. You need to put the data in the context of lifecycle, request volume, cache hit rate, cardinality, and the time elapsed since the object was created.

## 4. First Leak Source: Cache Without Bounds or Expiration Mechanism

A cache is a mechanism that **intentionally** holds objects for reuse. It becomes a leak when the retention policy exceeds application needs, for example:

- `static Map<String, Payload> CACHE` with no size limit.
- Every request creates a new key so the cache entry **is never accessed again**, yet is never removed either.
- There is a TTL on paper but no actual expire/cleanup action, or eviction only runs when a new operation occurs.
- The cache key holds the entire request/session/context instead of just a small identifier, creating unexpected retention paths.
- The cache value holds a large object graph: images, buffers, documents, response bodies, class loaders.
- A cache partitioned by tenant/user does not remove entries when the tenant/user/session ends its lifecycle.
- A cache used for “optimization” is treated as permanent storage without a memory budget.

### Code Pattern That Should Not Go to Production If Cardinality Grows Unboundedly

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

class UnboundedCache {
    private static final Map<String, byte[]> CACHE =
            new ConcurrentHashMap<>();

    static void remember(String requestId, byte[] payload) {
        CACHE.put(requestId, payload);
    }
}
```

This is an **illustrative class**, without `main`. If `requestId` is always new, the map keeps every `byte[]` because the static field `CACHE` is a long-lived root/owner path. `ConcurrentHashMap` solves **thread safety of the map**, **it does not solve memory bounds**.

A single call to `CACHE.clear()` can cut the retention path through the cache, but it does not guarantee that immediately after the call, heap used or RSS will drop accordingly: other references may still exist, and GC/heap commitment have their own mechanisms.

### A Proper Cache Needs a Lifecycle Management Policy

You can combine:

- **Maximum entry count**: the number of entries does not exceed a limit.
- **Maximum weight**: a budget based on estimated bytes/cost of the value, more suitable when entry sizes vary widely.
- **Time-based expiry**: expire after write/access if appropriate for business logic; do not mechanically use TTL as a substitute for a capacity bound.
- **Eviction policy**: LRU/LFU/segmented, based on hit/miss and workload.
- **Invalidation** when data changes or a session/tenant ends.
- **Explicit cleanup** for values owning resources such as file handles/native buffers, because removing a reference is not a `close()` call.
- **Metrics**: cache entry count, estimated size/weight, eviction count, hit ratio, estimated retained bytes, and owner partitioning.

A bounded cache can use significant memory because that is **expected behavior**. Correctness means staying within budget and not continuing to accumulate indefinitely.

## 5. Runnable Java 17 Example: Bounded LRU Cache Using LinkedHashMap

Create file **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {

    static final class LruCache<K, V> extends LinkedHashMap<K, V> {
        private final int capacity;

        LruCache(int capacity) {
            super(16, 0.75f, true); // access-order
            if (capacity < 1) {
                throw new IllegalArgumentException("capacity");
            }
            this.capacity = capacity;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            return size() > capacity;
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> cache = new LruCache<>(3);

        cache.put(1, "one");
        cache.put(2, "two");
        cache.put(3, "three");

        cache.get(1);           // 1 is the most recently used entry
        cache.put(4, "four");   // evicts entry 2 (eldest)

        System.out.println("size=" + cache.size());
        System.out.println("keys=" + cache.keySet());
        System.out.println("contains2=" + cache.containsKey(2));
    }
}
```

Compile/run:

```bash
javac --release 17 BoundedCacheDemo.java
java BoundedCacheDemo
```

**Exact stdout:**

```text
size=3
keys=[3, 1, 4]
contains2=false
```

Because `LinkedHashMap` has **access-order** enabled, calling `get(1)` moves key 1 to most recently used. Adding key 4 causes the map to evict key 2; the remaining order is `3, 1, 4`.

**Limitations of the example:** `LinkedHashMap` here is **not thread-safe**; it only illustrates eviction in a single thread. Concurrent applications should choose an appropriate cache implementation/concurrency policy (or full synchronization). `removeEldestEntry` uses **entry count**, not byte count, and does not have built-in TTL/async cleanup or eviction callbacks. Do not infer that every cache should hand-roll a `LinkedHashMap` in production; you can use a dedicated cache library with clear policies/metrics.

### Why Is LRU Not the Only Solution?

- One `byte[200 MiB]` entry and one `byte[2 KiB]` entry both count as one entry; a count limit may not be enough.
- If key cardinality is huge, continuous eviction causes churn/GC pressure even without a leak.
- Business data has expiration deadlines, security/PII retention, and its own invalidation; LRU only controls **recency of access**, and does not by itself satisfy retention policies.
- A cache residing in a singleton/static and existing for the lifetime of the process usually **does not release automatically** when a screen/session closes, unless keys and eviction/lifecycle are designed accordingly.

## 6. Do Weak/Soft References Help a Cache Release Automatically?

`java.lang.ref.WeakReference` and `SoftReference` have specific semantics, but they **do not** automatically turn every cache into a proper bounded cache.

- **WeakReference:** when the referent is only weakly reachable according to reference processing rules, the GC can clear the weak reference; GC timing is indeterminate. Use when you want to avoid keeping an object alive solely because of a weak reference.
- **SoftReference:** the referent may be kept longer under certain memory conditions, but the clearing policy depends on implementation/pressure. Do not treat SoftReference as an SLA, TTL, capacity bound, or general solution to avoid OOME.
- **PhantomReference:** primarily supports tracking cleanup after the appropriate reachability state; `get()` does not return an object to use as a cache value.

### The WeakHashMap Pitfall

`WeakHashMap` holds **weak keys**, but **normal values are still strong references** from the map. If the value holds a strong reference back to the key itself (directly or indirectly), the key can remain reachable via `map → value → key`, so the entry **does not disappear automatically as expected**.

```text
WeakHashMap
   | strong
   v
 value
   | strong
   v
 key <--- weak edge --- map's weak-key entry

The path map -> value -> key is strong, so key remains reachable.
```

Do not rely on a test like `System.gc(); assert(map.isEmpty())`: GC has no guaranteed execution time, and WeakHashMap may expunge stale entries during internal operations. If the goal is “a cache using at most 64 MiB”, a clearer approach is **maximum weight + eviction**.

## 7. Second Leak Source: Unregistered Listener/Observer

In the Observer/EventBus pattern, a long-lived publisher holds a list of callbacks/listeners. If the listener is an instance method reference or lambda that **captures** a view/controller/request object, the publisher can inadvertently keep that entire object graph alive.

```text
GC root
    |
    v
Application singleton EventBus
    |
    v
List<Listener>
    |
    v
listener (e.g., controller::onEvent)
    |
    v
Closed Controller
    |
    +--> ViewModel --> large List --> images/buffers
    +--> UserSession
    +--> other closures and objects
```

The user has closed the screen, but the EventBus has not removed the listener. **The Controller is still reachable**, so the GC cannot know the controller is no longer in use.

Things to remember:

- **Lambda capture is reference retention**: `event -> controller.handle(event)` keeps `controller` alive as long as the lambda object is alive. The method reference `controller::handle` can also keep the receiver alive.
- If the listener is an anonymous inner class, it can hold a reference to the enclosing instance depending on the case.
- If the event bus stores listeners in a static field or application-scope singleton, the owner usually outlives the UI component or request.
- It can leak **not only memory**: the old listener still receives events, performs repeated side effects, and writes data to a closed view.

### Lifecycle Principle

**Subscription must come with an explicit unsubscribe/close method.** When a component registers a listener, it should hold a token/subscription handle to unregister in `close()`, `dispose()`, `onStop`, or the corresponding lifecycle hook.

Simply “clearing the local listener variable” is not enough: while the publisher holds a strong reference, the listener stays alive. You must cut **the retention path from the publisher**.

## 8. Java 17 Example: Closeable Listener Subscription

Create file **`ListenerLifecycleDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

public class ListenerLifecycleDemo {

    static final class EventBus {
        private final List<Consumer<String>> listeners =
                new CopyOnWriteArrayList<>();

        Subscription subscribe(Consumer<String> listener) {
            listeners.add(listener);
            return new Subscription(this, listener);
        }

        void publish(String event) {
            for (Consumer<String> listener : listeners) {
                listener.accept(event);
            }
        }

        int listenerCount() {
            return listeners.size();
        }

        private void unsubscribe(Consumer<String> listener) {
            listeners.remove(listener);
        }
    }

    static final class Subscription implements AutoCloseable {
        private final EventBus bus;
        private final Consumer<String> listener;
        private boolean closed;

        Subscription(EventBus bus, Consumer<String> listener) {
            this.bus = bus;
            this.listener = listener;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.unsubscribe(listener);
            }
        }
    }

    static final class Screen {
        private final String name;

        Screen(String name) {
            this.name = name;
        }

        void onEvent(String event) {
            System.out.println(name + ":" + event);
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();
        Screen screen = new Screen("screen-A");

        try (Subscription subscription =
                     bus.subscribe(screen::onEvent)) {
            bus.publish("open");
            System.out.println("during=" + bus.listenerCount());
        }

        bus.publish("after-close");
        System.out.println("after=" + bus.listenerCount());
    }
}
```

```bash
javac --release 17 ListenerLifecycleDemo.java
java ListenerLifecycleDemo
```

**Exact stdout:**

```text
screen-A:open
during=1
after=0
```

After `try-with-resources`, `Subscription.close()` removes the listener from EventBus; `publish("after-close")` no longer invokes Screen. This is how to **cut the retention path from the publisher**.

**Scope limitations of the pattern:** it only illustrates a basic lifecycle in a single thread. In a real concurrent application, `Subscription.close()` needs to be designed to be thread-safe/idempotent, and removing a callback does not necessarily cancel a callback currently executing in a `CopyOnWriteArrayList` snapshot. Therefore lifecycle/race semantics must be clearly defined. A `Subscription` still held by the component itself can also contain the listener reference, but when both the component and subscription are no longer reachable through a long-lived owner, they can be handled by the GC.

### Some Similar Listener Scenarios

- Swing/JavaFX listeners, event emitters, or message buses that outlive the view.
- Application event handlers registered on every start but not deregistered on shutdown/reload.
- Reactive streams where `subscribe()` returns a subscription/disposable but the owner does not cancel it.
- Callbacks into a web socket/session that the connection manager retains after disconnect.
- Watchers/observers/callbacks carrying closures that capture a heavy context.

The solution is not always to use `WeakReference` for listeners. A weak listener can be collected **too early** if the subscriber side has no clear strong owner; it can also make the lifecycle unobservable. Prefer **explicit subscribe/unsubscribe** when the contract allows.

## 9. Third Leak Source: ThreadLocal in a Thread Pool

`ThreadLocal<T>` provides a value **per thread**. A common point of confusion: the `ThreadLocal` object is not a place holding a shared value for all threads; each `Thread` has its own corresponding thread-local entries structure.

In a thread pool, a worker thread can live **longer than thousands of requests**. If a request puts data into `ThreadLocal` and does not call `remove()`, the worker continues to hold the value after the request has finished.

```text
ExecutorService
    |
    v
Worker Thread (still alive)
    |
    v
threadLocals / ThreadLocalMap
    |
    v
Entry.value (strong reference)
    |
    v
RequestContext
    |
    +--> User / token / session metadata
    +--> buffers / parsed request / classloader-related references
```

Two consequences:

1. **Memory retention:** objects belonging to the old request cannot be collected if still strongly held by a ThreadLocal entry.
2. **Context contamination:** a new task running on **the same worker** can read the old request's value, if the code does not initialize or clear the context properly. This is also dangerous for data safety between requests.

### Technical Points to Understand

- `ThreadLocal.set(value)` writes the value for **the current thread**.
- `ThreadLocal.get()` reads the value attached to the current thread, and may return `null` if not set and there is no other `initialValue`.
- `ThreadLocal.remove()` deletes the value attached to **the current thread** for that key.
- `ThreadLocalMap` on HotSpot typically uses a **weak reference for the `ThreadLocal` key** and a **strong reference for the value**. The key being cleared by GC does not mean the value disappears immediately: a stale entry can remain there until map cleanup runs.
- When `ThreadLocal` is held in `static final`, the key can still live long; without `remove()`, the value remains held by the worker until replaced/removed or the worker terminates.
- `ThreadLocal` **is not a safe mechanism for passing context between threads**. Asynchronous continuations may run on another thread or a reused old thread.

### Practical Rule

Always place `remove()` in `finally` at **the ownership boundary of the data lifecycle**, especially when the data belongs to a request/transaction/task:

```java
CONTEXT.set(context);
try {
    processRequest();
} finally {
    CONTEXT.remove();
}
```

This is an **illustrative fragment**; `CONTEXT`, `context`, `processRequest()` belong to application code, not a standalone Java file. If an existing context needs to be restored because of a nested operation, an appropriate restore policy must be designed instead of always removing blindly. With multiple values, remove all ThreadLocals within the task's scope and close resources before returning the worker to the pool.

## 10. Deterministic Java 17 Example: Same Worker Without Context Leak

Create file **`ThreadLocalCleanupDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> first = pool.submit(() -> {
                REQUEST_ID.set("request-A");
                try {
                    System.out.println("first=" + REQUEST_ID.get());
                } finally {
                    REQUEST_ID.remove();
                }
            });
            first.get();

            Future<?> second = pool.submit(() -> {
                System.out.println("second=" + REQUEST_ID.get());
            });
            second.get();
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

**Exact stdout on the successful path:**

```text
first=request-A
second=null
```

`newSingleThreadExecutor()` ensures submitted tasks are processed sequentially on **one worker** (on the normal path, if the worker does not need to be replaced due to failure). `first.get()` completes before `second`, and `remove()` deletes the value from the worker in `finally`. Therefore the second request does not see `request-A`.

If `REQUEST_ID.remove()` is omitted, the same worker can print `second=request-A`, illustrating context leakage. **Do not use the `null` output to prove the object has been reclaimed by GC**; the demo only proves that a reference path has been removed from ThreadLocal.

### Things `remove()` Does Not Solve

- A `RequestContext` still held by a static cache or listener remains reachable.
- A resource inside the value such as a database connection must be **closed/returned to the pool** separately; `remove()` alone does not close the resource.
- `InheritableThreadLocal` has semantics for passing data to child threads at the appropriate time; it is **not** a suitable mechanism for propagating request state to a thread pool created long before the request.
- If using `CompletableFuture`, schedulers, or reactive programming, callbacks can run on different threads; design explicit context propagation instead of assuming the same thread.

## 11. Why Can ThreadLocalMap's Weak Key Still Leak the Value?

A misconception is “`ThreadLocalMap` uses weak keys so the value will be reclaimed automatically if the key is lost”. In reality, if the `ThreadLocal` key no longer has a strong reference from the application, the entry can look like this:

```text
Worker Thread (long-lived)
    |
    v
ThreadLocalMap
    |
    v
Entry
    key   = null  (weak key has been cleared)
    value = RequestContext (strong reference)
                |
                v
             large graph
```

HotSpot has a mechanism to **expunge stale entries** on appropriate map accesses/modifications, but **you must not assume that clearing the weak key will immediately delete the value**. A worker that is idle for a long time or operates under certain patterns can retain stale values longer than expected.

Merely creating `new ThreadLocal<>()` per request without keeping the key and without calling `remove()` makes the situation even harder to diagnose. Therefore:

- For a task-scoped ThreadLocal, keep a reference to the key within scope sufficient to call `remove()`.
- Use `try/finally` even when code throws an exception.
- Avoid values containing an entire large object graph when only a small ID is needed.
- Choose the cleanup boundary at the request/task filter/interceptor, not scattered across many places.
- Check whether the framework's thread pool/task wrapper already cleans up context; do not guess.

**Note on Java 17:** the example uses platform threads and traditional `ThreadLocal`. Virtual threads had foundational changes in later JDKs; do not apply assumptions from a newer version verbatim to explain the Java 17 runtime.

## 12. Static Fields, Singletons, and Class Loaders Can Also Keep Data Alive

A static field can be a legitimate owner of a cache/event bus. In the JVM, retention is not as simple as “every static field of every class exists forever”, because class loader lifecycle and unloading capability also matter.

Example web application/plugin reload scenario:

```text
GC root in host (thread/pool/singleton)
    |
    v
Listener or ThreadLocal value
    |
    v
Object from plugin class
    |
    v
Plugin's defining ClassLoader
    |
    v
Class metadata and related object graph
```

If the host still holds an object defined by the plugin class loader, that class loader may **not be eligible for collection/unloading**, leading to heap and class metadata/metaspace growth across multiple reloads.

This does not mean “any ClassLoader with a remaining object will definitely never have classes unloaded” in every collector/runtime; it only describes **a typical retention path** to inspect in heap dumps and class unloading metrics.

### Unexpected Sources Holding Class Loaders

- A worker thread holds a `ThreadLocal` value belonging to an old web app.
- Thread Context ClassLoader (TCCL) still points to a plugin loader that has been unloaded in business logic.
- A host's static global registry or listener bus holds callbacks from the plugin.
- Scheduler/timer/task queue still has pending tasks capturing class/plugin objects.
- JNI global references or caches outside the JVM hold corresponding handles/lifecycles.
- Logging/metrics adapters create registrations that the plugin does not unregister on shutdown.

The solution must start from **the owner with the longer lifecycle**. It usually requires deregistering/unsubscribing, canceling tasks, shutting down thread pools owned by the plugin, resetting TCCL, removing ThreadLocals, closing resources, and avoiding keeping Class/Method/MethodHandle/plugin instances too long in global caches.

## 13. Distinguishing Memory Leaks From Resource Leaks and Useful Caches

An object not yet reclaimed by GC does not by itself prove a program bug. For example:

| Situation | Is It Truly a Leak? | Additional Evidence Needed |
| --- | --- | --- |
| Cache holds 10,000 entries but is properly bounded at 10,000 with high hit rate | Cannot conclude yet | Budget, hit rate, value provided by cache |
| User/session cache grows over time even after users log out | Very suspicious | Key cardinality, eviction/TTL/invalidation |
| Listener list grows with the number of times a screen is opened and closed | Very suspicious | Registration lifecycle and path to publisher |
| Thread pool uses 50 workers, each holding old context | Suspicious | ThreadLocalMap values, request boundary cleanup |
| Heap used rises before GC then drops back to baseline after GC | May be normal | Post-GC live set and throughput/latency |
| Native direct buffers not released at proper lifetime | May be native resource retention | Native memory/JFR/NMT/OS metrics; heap dump may only show wrapper |
| Objects in cache with proper TTL but committed heap does not decrease | Not enough to conclude leak | Post-GC heap used, GC uncommit policy, RSS |

**File descriptor/socket leaks are not necessarily heap leaks.** Sometimes a Java object holds a native resource and needs `close()` even if the GC can later reclaim the wrapper. Use `try-with-resources`/explicit lifecycle for resources like streams, database connections, response bodies, and sockets; do not rely on finalizers or GC to complete release logic.

## 14. Diagnosis: The True Sign Is the Post-GC Retained Heap Trend

When an application slows down or reports `OutOfMemoryError: Java heap space`, do not immediately blame the cache or GC. The process should combine:

1. **Identify symptoms and scope:** heap OOME, `GC overhead limit exceeded`, metaspace OOME, direct/native memory pressure, or container OOMKilled?
2. **Record version and collector:** `java -version`, `-Xms`, `-Xmx` flags, collector, and workload when the error appeared.
3. **Track heap occupancy over time:** compare points with equivalent workload and post-GC measurements when possible.
4. **Look at object counts per class** via class histogram at appropriate times.
5. **Take a heap dump when permissions and resources allow**, then inspect retained size, dominator tree, and GC roots.
6. **Trace back to the owner:** static cache, event bus, thread, ThreadLocalMap, scheduler, or class loader.
7. **Compare against lifecycle:** should the object have disappeared after logout, response completion, component close, or plugin unload?
8. **Fix the place holding the reference**, add bounds/cleanup, write a regression test, and monitor again under an equivalent workload.

A single snapshot only shows which objects are held at that moment. **A leak is better concluded through variation and business logic**, for example repeating the same “open/close 1,000 screens” test where the number of listeners/retained controllers does not return to baseline.

### Heap Used Is Not Necessarily the Live Set

Between two GCs, the heap can contain objects that are no longer reachable but not yet reclaimed. Therefore:

- High heap used does not by itself prove there are strong references to all allocated bytes.
- Post-GC occupancy can be useful, but how the collector collects and metric timestamps must be properly understood.
- Heap committed and process RSS may not drop immediately even after a leak is fixed, because the JVM keeps memory for reuse or the OS/JVM does not uncommit immediately.
- NMT/RSS/direct memory numbers belong to a different scope; do not use `-Xmx` as the total memory limit of a Java process.

## 15. Using jcmd, Histogram, and Heap Dump on Java 17

Some useful commands on a JDK with the `jcmd` tool:

```bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap-issue.hprof
```

**Note:** `<PID>` and `/path/to/heap-issue.hprof` are **placeholders**, not a verified existing PID or path. Histogram/heap dump commands can **consume CPU, memory, disk, cause pauses, or affect production**; you need to confirm permissions, disk space, data security, and execution timing.

- **`GC.heap_info`:** view heap/GC information depending on the JVM.
- **`GC.class_histogram`:** statistics of count and shallow bytes by class at the time of observation. Does not show who holds the object or retained size.
- **`GC.heap_dump`:** exports a heap snapshot to analyze the object graph. Heap dumps can contain secrets, tokens, PII, and user data; apply appropriate read permissions, storage, encryption, and retention limits.
- Supported flags/variants like `-all` can change whether a full GC is requested before the dump. **Read `jcmd <PID> help GC.heap_dump`** on the exact JVM instead of guessing pause effects or which objects are included in the dump.

A heap dump is not an “automatic answer machine”. You need to trace **reference chains** to know why objects remain alive.

### Using Eclipse MAT / Heap Analyzer

A relatively effective workflow:

1. Open `.hprof` in an analysis tool such as Eclipse Memory Analyzer (MAT).
2. View the histogram, look for unusual classes: `byte[]`, `char[]`, DTOs, `ArrayList`, `HashMap$Node`, listener classes, request contexts.
3. View **Dominator Tree** to find object owners with **large retained size**.
4. For a suspicious group of instances, use **Path To GC Roots** and exclude weak/soft/phantom edges if you want to find the specific strong retention path.
5. Read **incoming/outgoing references** from the owner to the values; look for specific fields like `CACHE`, `listeners`, `threadLocals`.
6. Compare with lifecycle: should the owner still be alive or should it have been released? If it should have closed, check whether `close/remove/invalidate` ran on all error paths.
7. Repeat the same load scenario after the fix; do cache entries/listeners/context values stabilize?

**A path to a GC root can have many branches.** Finding `static CACHE -> object` does not prove it is the **only path**. If an object remains alive after clearing the cache, it may be held by a ThreadLocal, listener, or pending task.

## 16. Reading a ThreadLocal Leak in a Heap Dump

A typical retention path in MAT has the conceptual form:

```text
Thread "http-worker-17"
  └── threadLocals
      └── ThreadLocalMap
          └── table[]
              └── Entry
                  ├── referent: ThreadLocal key or null if cleared
                  └── value: RequestContext
                              └── byte[] / user/session graph
```

Depending on JDK/build/dump, internal field names may differ. This is an illustrative diagram, not an API contract for `ThreadLocalMap` structure.

Investigate these questions:

- Is the thread a long-lived worker in a pool? Who owns the pool?
- Does the `ThreadLocal` key still exist or has it been cleared by GC into a stale entry?
- What references does the value contain, and how large is its retained size?
- Is `remove()` used in `finally` for all exit paths, including exceptions/timeouts/cancellation?
- Does the code accidentally create a `ThreadLocal` on every request instead of reusing one key with a clear lifecycle?
- Do tasks run interleaved across multiple tenants/users, and could a leaked value cause a security bug?

If there is only one large value instance, it may be a valid running request. If every worker holds contexts from long-completed requests, or many stale entries accumulate after comparable workloads, suspicion is much higher.

## 17. Reading Cache/Listener Leaks in a Heap Dump

### Cache

```text
Application.class
  └── static CACHE
      └── ConcurrentHashMap
          └── table[]
              └── Node
                  ├── key: request-382773
                  └── val: ResponseSnapshot
                              └── byte[] / nested DTOs
```

Suspicious signs: key cardinality continuously growing, keys not reused, values having no TTL, or memory still retained after the client/session ends. Note that the class histogram of `byte[]` does not tell which map the keys belong to; you must walk from **incoming references** back to the owner.

### Listener

```text
GlobalEventBus
  └── listeners
      └── ArrayList/CopyOnWriteArrayList
          └── Consumer/lambda/method reference
              └── ScreenController
                  └── viewModel / resource graph
```

If the Controller has been closed in business logic but there is still a path from the singleton event bus, that is a strong sign of a leak. The fix is to **remove the exact listener instance/reference**, not just `screen = null` on an unrelated local variable.

### A Leak Can Have Multiple “Owner Traps”

If a Controller registers a listener itself, and the listener captures the Controller, then the Controller holding `Subscription` forms a cycle. That cycle **by itself does not cause a leak** if the whole graph has no roots. The problem is that the global bus continues to hold one end of the cycle; therefore you must **unsubscribe from the bus**.

## 18. Avoid Fixing Leaks With Symptom-Hiding Workarounds

Coping methods that do not solve the root cause:

- **Increasing `-Xmx`:** may delay OOME, but caches/listeners/ThreadLocals still retain objects by the same rules.
- **Calling `System.gc()` repeatedly:** cannot reclaim objects that are still strongly reachable; can also reduce throughput and increase pauses.
- **Only clearing local variables:** if the object is still held by a static cache or listener list, the reference at the owner still exists.
- **Changing every reference to WeakReference:** can lose data during GC, and does not solve memory budget or cleanup logic.
- **Shutting down the worker thread pool indiscriminately:** may cut ThreadLocal values but breaks the service, and does not fix the root owner of the task lifecycle.
- **Only tweaking the heap dump analyzer:** the root cause lies in ownership/lifecycle code, not in the observation tool.
- **Relying on finalizers:** finalization has no timing guarantees and is an obsolete mechanism; use explicit `close()`, `Cleaner` when truly appropriate as a backup for native cleanup, and `try-with-resources`.

**The best fix** is usually one of three types: set a **budget/eviction for the cache**, **unsubscribe the listener at the proper lifecycle**, or **remove/restore ThreadLocal at the proper task boundary**. A combination may be needed if the object is being held through multiple roots.

## 19. Design Checklist to Prevent Leaks From Reappearing

| Component | Review Question | Measure |
| --- | --- | --- |
| Cache | Is entry count/estimated weight bounded? | Maximum size/weight, eviction, expiration, invalidation |
| Cache key | Does the key retain request/session/object graph? | Small, immutable, stable key with lifecycle |
| Cache value | Does the value retain a large graph or native resource? | Reduce retained graph, close on evict if needed |
| Listener | Who holds the subscription and when is it canceled? | `AutoCloseable`/dispose/unsubscribe |
| Listener | Which objects does the lambda/method reference capture? | Avoid capturing overly broad context; proper cleanup |
| ThreadLocal | Does the value belong to the thread or the request/task? | `try/finally remove()` at task boundary |
| ThreadLocal | Does the thread pool reuse workers across users? | Context isolation and cleanup |
| ThreadLocal | Are there stale entries from cleared keys? | Keep key lifecycle clear, call remove, inspect heap dump |
| ClassLoader | Is the plugin fully shut down on unload? | Cancel tasks, close registries, unregister, reset TCCL |
| Resources | Are there files/sockets/direct memory needing release? | Explicit close and owner lifecycle |
| Diagnostics | Are there baselines and metrics before/after workload? | Heap occupancy, counts, heap dumps, JFR when appropriate |
| Testing | Are create/destroy operations repeated and retention measured? | Lifecycle regression and boundedness tests |

A good policy also states **who owns the data** and **when the retention period ends**: request, session, window, tenant, plugin, or entire application. The same object may be validly cached during a session lifecycle but become a leak if kept after logout.

## 20. Self-Check Questions

**Question 1:** A `HashMap` contains objects A and B pointing to each other in a cycle. After removing all external roots to the map, will A and B get “stuck” because of the cycle?

**No.** A tracing GC can collect the entire graph that is unreachable from GC roots. Cycles do not by themselves create leaks.

**Question 2:** Does a `static final Map` always cause a leak?

**No.** A static map can be a properly designed cache/registry. A leak occurs when retention exceeds the actual lifecycle/budget; the `final` modifier only prevents reassigning the field reference, not changing the map's contents.

**Question 3:** Does `ConcurrentHashMap` perform eviction automatically?

**No.** It provides concurrent map semantics; there must be a separate size/time/invalidation policy.

**Question 4:** A view has closed, yet `GlobalEventBus.listeners` still contains `view::onEvent`. Why is the view not yet collectible?

Because the bus holds the method-reference callback, and the callback holds the view receiver; there is a **strong path from a root** to the view.

**Question 5:** `ThreadLocalMap` has weak keys, so does the value definitely disappear as soon as the key is cleared?

**No.** The value can remain a strong reference in a stale entry until cleanup, so lifecycle-appropriate `remove()` is needed.

**Question 6:** A worker uses `REQUEST_ID.set(...)` for request A and then processes request B. If cleanup is missing, what can happen?

Memory retention through context A, and the risk of B reading A's **stale data** if the code calls `get()` without setting it again.

**Question 7:** With a `WeakHashMap` whose value has a strong reference back to the key, is the entry guaranteed to disappear when there is no longer an external key variable?

**No.** The `map → value → key` path can still keep the key strongly reachable.

**Question 8:** Heap used rises right before GC but returns near baseline after GC. Is this definitely a leak?

**No.** It may be normal allocation churn. You need to observe the retained live set and object lifecycle.

**Question 9:** A heap dump histogram shows very many `byte[]`. Can we conclude the bug is where byte arrays are allocated?

**No.** You must trace the retained owner/path to GC roots. A cache entry or ThreadLocal value might be holding the arrays.

**Question 10:** Does deleting a cache entry force RSS to drop immediately by an amount matching the retained size?

**No.** Other roots may still exist; GC may not have reclaimed yet; the JVM may keep committed heap, and OS RSS depends on native memory/pages.

## 21. Practical Workflow to Investigate and Verify a Fix

A repeatable test scenario:

1. **Measure baseline** after reasonable warm-up, recording memory pools, listener counts, cache entry counts, thread count, and heap usage.
2. **Generate a sequence of operations** with a clear lifecycle: 1,000 requests / 100 view open-close cycles / 10 plugin start-stop cycles, with comparable inputs.
3. **Wait for the system to become quiescent** if appropriate, re-measure counts and post-GC metrics at instrumented/recorded points, without forcing an exact number.
4. **If object counts grow continuously**, capture a heap dump and find top owners using the dominator tree.
5. **Find the path to GC roots**: static cache, event bus, threadLocalMap, or another owner.
6. **Identify where the object's lifecycle ends**: response complete, screen close, tenant delete, task finally, plugin shutdown.
7. **Fix the code at the owner** using eviction/invalidate, unsubscribe/dispose, or ThreadLocal remove.
8. **Add tests**: after lifecycle close, listenerCount equals 0; cache size does not exceed max; the next task does not see the old request context.
9. **Re-test under concurrent workload**: cleanup in `finally` even on errors, cancellation, or timeouts; avoid races between subscribe and unsubscribe.
10. **Monitor production**: number of listeners/cache entries, hit rate, ThreadLocal context hygiene, heap live set, OOME/GC pressure. The fix must remain stable over time.

**Do not wait for `OutOfMemoryError` to investigate:** low-level leaks often show up earlier through steadily growing cache sizes, accumulating listeners, and long-lived thread contexts.

## Authoritative References

- [JVMS Java SE 17 §2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): objects, arrays, and heap management.
- [Java SE 17 `java.lang.ref` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): reachability levels and reference objects.
- [Java SE 17 `Reference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html), [`WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [`SoftReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): reachability, clearing, `reachabilityFence`, and reference lifecycle.
- [Java SE 17 `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, notes on values pointing back to keys.
- [Java SE 17 `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove`, and per-thread values.
- [Java SE 17 `LinkedHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): access order and `removeEldestEntry` for bounded LRU demo.
- [Java SE 17 `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): managing unsubscribe/cleanup lifecycle with try-with-resources.
- [Java SE 17 `ManagementFactory`, `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage and metrics.
- [Java SE 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `GC.class_histogram`, `GC.heap_dump`, and diagnostic conditions.
- [Java SE 17 `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory utilization statistics.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/): heap dump, retained size, dominator tree, path to GC roots.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): basis for runtime observation via JFR, when additional evidence over time is needed.

**Remember:** the GC reclaims objects that are **no longer reachable**, rather than guessing which data has lost its business value. **Caches need budget/eviction**, **listeners need lifecycle-appropriate unsubscribe**, and **ThreadLocal needs `remove()` or restore in `finally`**. When you see the heap growing, trace **strong reference paths from GC roots to the retained graph**, fix **the owner keeping it alive**, and then verify with a repeated workload and before–after metrics.
