# Avoiding Retaining Application Objects in Telemetry Data Longer Than Necessary

In Java Instrumentation, a probe can be added to thousands of methods to record duration, call frequency, errors, traces, or performance metrics. A critical bug does not lie in the injected bytecode itself, but in **the data retained after the call has finished**: a helper puts `request`, `response`, `Throwable`, or `Object[] args` into a queue/static map/`ThreadLocal`, and accidentally extends the lifetime of an entire application object graph.

Remember: **an object that is no longer useful for business logic is not necessarily eligible for GC reclamation**. If there is still a **strong reference** path from a GC root to that object, it is still considered reachable. A telemetry event that is very small in terms of its own data fields can retain **megabytes of indirect data** if it holds a reference to a request with a payload, session, cache, or class loader.

This lesson belongs to the **Concurrency and Performance** group of Java Instrumentation. The goal is to design probes that do not alter the lifecycle of application data: store only a small snapshot, do not retain original objects, bound buffers and retention duration, clean up thread/async contexts, avoid pinning class loaders, distinguish weak references from guaranteed solutions, and verify using experiments as well as heap tools.

## 1. Distinguishing Execution Time from Reference Retention Time

An HTTP request finishing after 20 ms does not mean every object of the request is collected at millisecond 21. The JVM can only collect based on reachability conditions and GC policy; the timing of GC is **non-deterministic**. An object still being used to process a request can be completely valid while reachable. The problem occurs when a part that **is no longer needed** continues to hold a reference longer than its intended lifecycle.

Diagram:

```text
Request starts
      |
      v
Request object + payload + user context
      |
      +-- method running: valid reference
      |
      +-- ProbeHelper.capture(request)
               |
               v
          static queue / ThreadLocal / callback / cache
               |
      Request completes, stack frame is popped
               |
               v
    Probe still holds a strong reference to request
               |
               v
    Payload and related graph remain reachable
    (even though no longer valuable for measurement)
```

The problem here is not necessarily a permanent "memory leak". An event held for an extra 30 seconds in a queue before an exporter processes it can still be **excessive retention**, increasing peak heap, GC pauses, old generation pressure, and latency. During peak traffic, thousands of objects held for a few extra seconds together can cause severe degradation.

### 1.1. States That Must Not Be Equated

| State | Meaning | Does it prove the object is no longer retained? |
|---|---|---|
| Original method has `return`ed | Call stack frame has ended | **No** if a queue/callback/ThreadLocal still holds a reference |
| Trace/span has "ended" | Logical data has finished | **No** if the exporter or baggage still retains the object |
| Queue has `poll()`ed an event | Removed one reference from the queue | **No** if the consumer/in-flight batch still holds a reference |
| `WeakReference.get()==null` | Referent has been cleared from the weak ref | Does not prove the whole system has no other objects retained |
| `WeakReference.get()!=null` | Referent has not been cleared at check time | **Does not** by itself prove a leak; GC may not have run yet |
| `System.gc()` is called | A GC request/hint was made | **Does not** guarantee immediate collection |
| Class loader is no longer used | Application has undeployed/reloaded a plugin | **No** if an agent metadata cache/queue still holds the class/loader |
| Heap dump shows a GC root path | There is a reference path retaining the object | Strong evidence of a retention path **at the time of capture** |

### 1.2. Definition of GC Root and Strong Reachability

GC roots can include references from the stacks of live threads, static fields of live classes, JNI references, and certain other VM-managed object-holding areas. If there is a chain of **strong references** from a root to an object, that object remains strongly reachable.

```text
GC root
  └─ live agent class
      └─ static Queue<ProbeEvent>
          └─ ProbeEvent.argument: Request
              ├─ Request.payload: byte[]
              ├─ Request.session: Session
              └─ Request.owner: ApplicationService
                  └─ Class<?> / ClassLoader / resource graph...
```

An event that appears to have only `methodId` and `argument` keeps **the entire graph reachable** from the request alive via the `argument` field. Therefore, the direct size of the event object **does not reflect the retained heap size**.

**Do not infer from a heap chart that object A "exclusively owns" its entire graph if other objects also reference the same graph.** Tools can display shallow size, retained size, and dominator trees with different meanings; read the right metric when diagnosing.

## 2. Where Instrumentation Commonly Retains Objects Too Long

| Reference-holding point | Anti-pattern example | Why does it live long? | Remediation direction |
|---|---|---|---|
| `static List<Object[]>` | `EVENTS.add(args)` | Agent class/statics live very long | Event contains only primitives/approved snapshot |
| Exporter queue | `queue.offer(request)` | Backpressure or slow network | Bound queue, drop; do not enqueue original object |
| `ThreadLocal<Request>` | `CURRENT.set(request)` without `remove` | Thread pool threads are reused for a long time | `try/finally` + `remove`; store small context |
| `InheritableThreadLocal` | Copies context containing object to child thread | Child thread may live long/be unrelated | Do not pass entire request; manage explicit scope |
| Lambda/callback | `() -> report(request)` | Closure captures `request`; timer holds callback | Capture small ID/timing upfront; cancel callback on expiry |
| `CompletableFuture`/retry task | `thenApply(x -> use(request))` | Future stage has not completed | Do not capture app graph; controlled timeout/cancel/cleanup |
| Listener registration | `registry.addListener(listenerWithRequest)` | Registry outlives request | Unregister in `finally`/lifecycle closure |
| Metric labels | `label = request.toString()` | High series/cache cardinality and retains string | Finite enum/group labels, do not stringify args |
| Metadata cache | Agent's `Map<Class<?>,Metadata>` | Class key drags along defining class loader | Scoped cache lifecycle, weak keys when safe, clear at right time |
| Broken weak cache | `WeakHashMap<Key,Value>` where value references key | Value strongly retains key | Eliminate reference cycle, verify via heap path |
| Throwable retention | `event.error = throwable` | Cause/suppressed/fields and type/classloader can be retained | Short/approved error code; do not retain raw Throwable |
| Async logger | Log parameter `{request}` held for later formatting | Formatting is deferred while reference persists | Log scalar/trusted text snapshot, do not push raw args |
| Native callback handle | Global JNI reference or tag map holds object | Native side retains outside Java queue | Release global ref/tag with clear lifecycle |

**Ownership boundary:** If data originates from the application, the agent should treat it as **borrowed** only during probe execution. Retaining it beyond that scope requires an independent data contract (type, permissions, size limits, and lifetime), not an assumption just because the callback can see it.

## 3. Common Anti-Pattern: "Just Pass Object[] to the Exporter to Process Later"

A transformer might inject a call to a helper like:

```java
// Illustrative API example; not a standalone program.
ProbeHelper.enter(int methodId, Object[] arguments);
```

If the helper does:

```java
// ANTI-PATTERN: retains raw argument references.
static final java.util.Queue<Object[]> EVENTS =
        new java.util.concurrent.ConcurrentLinkedQueue<>();

static void enter(int methodId, Object[] arguments) {
    EVENTS.offer(arguments);
}
```

then `arguments` still holds references to every argument and the objects they reference. `ConcurrentLinkedQueue` has no default element-count bound. A slow or dead exporter causes the queue to grow unboundedly; each reference can retain a huge graph.

**Note:** Replacing this with `arguments.clone()` or `Arrays.copyOf(arguments,...)` does not solve retention: that is only a **shallow copy**; the objects inside the array are still strongly referenced.

```java
Object[] snapshot = arguments.clone(); // Does not copy the object graph.
EVENTS.offer(snapshot);                // Still retains the arguments.
```

Similarly, wrapping them in `record ProbeEvent(Object[] args)` or `Map<String,Object>` still retains the objects. Naming it "snapshot" does not turn a bundle of references into independent data.

### 3.1. Async Logging and Delayed Serialization Still Hold References

Some loggers/encoders do not format values immediately, instead passing an event containing the object to a background processing thread. That can reduce producer latency, but **extends the lifetime of application objects**. If an async log event holds `request`, the value might only have `toString` called seconds later; this causes both retention and the risk of running user code late.

Replace:

```java
logger.debug("request={}", request); // May be formatted late.
```

with:

```java
logger.debug("methodId={} outcome={}", methodId, outcomeCode);
```

where `methodId` and `outcomeCode` are trusted metadata with a finite set of values. **Do not** build `request.toString()` first and then truncate to 100 characters: stringification has already run and can be expensive, leak secrets, or invoke application code. When an event does not need the payload, do not read the payload.

### 3.2. Throwables and Return Objects Also Have Lifecycles

A `Throwable` is a real object, with a stack trace, cause, and suppressed exceptions, and in the case of a custom subclass it may hold additional state. If the agent retains a raw `Throwable` in a batch for later upload, it can retain the class and associated data longer than necessary.

Similarly, `returnValue` can be a domain model/cached proxy/lazy object. Do not treat a `null`-check followed by `new ProbeEvent(returnValue)` as safe just because `toString` has not been called yet: retention begins the moment the event holds the reference.

An error event usually only needs:

```json
{
  "methodId": 241,
  "durationNanos": 72000,
  "outcomeCode": 2,
  "sampled": true
}
```

This is an illustrative schema. There is no raw `Throwable`, `request`, `response`, `Object[]`, or secret value. If an error name is needed, use a classification with an approved value set; do not put the entire message or stack trace into a high-cardinality metric label by default.

## 4. The Minimal Snapshot Principle

A **proper snapshot** is self-contained telemetry data, taken intentionally, that holds no references back to the application object graph and does not need to call methods on the original object after the request has ended.

### 4.1. Example of a Preferred Model

```java
// A simple schema suitable for Java 17+.
public record Measurement(
        int methodId,
        long durationNanos,
        int outcomeCode,
        boolean sampled) {
}
```

This is a record with only primitive fields. It contains no `Object`, `Throwable`, `Class<?>`, or `Map<String,Object>`. Holding events in a bounded queue **cannot itself retain a request instance** through the fields of this record.

**However**, you still need to bound the number of records: small records accumulating unboundedly still consume heap. And `durationNanos` is an interval measured by the monotonic clock `System.nanoTime()`, **not** an epoch timestamp; if a separate wall-clock timestamp is needed, an appropriate synchronization design is required.

### 4.2. Data Policy by Level

| Observability goal | Minimal data | Is the original object needed? |
|---|---|---|
| Method call count | `methodId` and counter | No |
| Latency | `methodId` + `durationNanos` | No |
| Success/error rate | `methodId` + `outcomeCode` | No |
| Basic tracing | Approved short string ID, span ID, timing | No domain object needed |
| Request size | Primitive size provided by application layer per contract | No need to retain `Request` |
| Error classification | Enum/int code chosen by probe per policy | Do not retain raw `Throwable` |
| Evaluating a business field | Approved, capped value from a dedicated API | Do not store entire object graph |
| Investigating rare bugs needing payload | Special opt-in, privacy review, TTL/budget, safe source | Only if approved and no less intrusive option exists |

**Note:** A `String` is immutable, yet it can still contain sensitive or long data; retaining an application `String` is not always harmless. An allowed trace ID needs a cap, cardinality policy, retention policy, and validation before copying/emitting. Unkeyed hashing of low-entropy IDs also does not guarantee anonymity.

### 4.3. Do Not Use Generic Serialization to "Snapshot"

The following approaches can create additional problems:

- JSON serialization from an arbitrary object can invoke getters, custom serializers, proxy interceptors, or lazy loading, depending on library/configuration.
- Java `ObjectOutputStream` can traverse the object graph and trigger serialization hooks such as `writeObject`/`writeReplace`.
- Deep-copying a large graph still costs heap and CPU, can expose data, and occupies the queue for a long time, even if it does not hold the original reference.
- Truncating string size **after** serialization only bounds what is emitted, not the cost incurred beforehand.
- Storing raw payload bytes as telemetry is also sensitive data and can be very large.

The solution is a **pre-declared telemetry schema**, not generic serialize-everything. If the business needs a specific field, the application should provide a safe adapter with an explicit data contract, version, and access permissions.

## 5. When to Capture the Snapshot and When to Release References

A good pipeline defines the lifetime of each piece of data:

```text
Application method entry
  |
  +-- determine methodId / sampling / privacy policy
  |
  +-- create small timing state, if needed
  |
  v
Application method body
  |
  v
Method exit (success/exception)
  |
  +-- duration = now - start
  +-- outcome = finite code
  +-- create Measurement containing only scalars
  +-- offer to bounded buffer; if full, drop + counter
  +-- clear ThreadLocal/context in finally
  |
  v
Request ends
  |
  v
Exporter takes Measurement, serializes, and sends
  (no request/args/return object left to retain)
```

Three places to set boundaries:

1. **Before capture:** sampling, allowlist, privacy, and budget must be decided **before** reading/copying/serializing expensive data.
2. **Before enqueue:** convert into small data **independent of domain objects**; do not push a supplier/lambda that captures objects to "snapshot later".
3. **After completion:** clear references/ThreadLocal/listeners, and do not hold events indefinitely in a retry backlog.

It is also necessary to distinguish **event lifetime** from **request lifetime**: a telemetry event may outlive the request so the exporter can send it, but it must not extend the lifetime of **application objects**.

### 5.1. A Bounded Queue Is Necessary but Not Sufficient

`ArrayBlockingQueue<Measurement>(1024)` bounds the **element count**. But if the event type is `Object` and each element references a large request, 1024 elements can still retain a very large amount of heap. **The unit of bounding must consider the retained graph**, not just the event count.

You should combine:

- Max event count/byte budget.
- Max in-flight batches and export wait time.
- Bounded timeout/backoff.
- Drop policy when the exporter is slow.
- Not retaining the raw request after it is enqueued.
- Shutdown/drain handling with a deadline and release of event references.
- Metrics for accepted/dropped/queue depth/export lag/bytes.
- Policy to delete data after TTL, with sensitive-data controls.

`offer` on a bounded queue is more useful than `put` on a hot path if you do not want to block requests, though performance/semantics must be measured on real workloads. A successful `offer` **does not** mean the information has been exported to an external sink; `ENQUEUED` must be reported separately from `EXPORTED`.

## 6. Runnable Java 17+ Example: Queue Retaining Request vs. Scalar-Only Event

The example intentionally writes an **unsafe** branch to clearly show the strong reference, and a **better** branch using a record with no objects. The program does not call `System.gc()`, does not guess when GC runs, and produces **deterministic** stdout.

### 6.1. File `RetentionDemo.java`

```java
import java.util.ArrayDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class RetentionDemo {
    private static final int MAX_SAFE_EVENTS = 2;

    // ANTI-PATTERN: static queue retains the Request object itself.
    private static final ArrayDeque<Request> RAW_EVENTS =
            new ArrayDeque<>();

    // Event independent of Request, bounded by element count.
    private static final ArrayDeque<Measurement> SAFE_EVENTS =
            new ArrayDeque<>();

    // Used to illustrate the risk of context leaking across tasks in a pool.
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static final class Request {
        final byte[] payload = new byte[1024 * 1024];
    }

    private record Measurement(
            int methodId,
            long durationNanos,
            int outcomeCode) {
    }

    private static boolean recordSafe(
            int methodId, long durationNanos, int outcomeCode) {
        if (SAFE_EVENTS.size() >= MAX_SAFE_EVENTS) {
            return false;
        }
        return SAFE_EVENTS.offerLast(
                new Measurement(methodId, durationNanos, outcomeCode));
    }

    public static void main(String[] args) throws Exception {
        Request request = new Request();

        RAW_EVENTS.addLast(request);
        System.out.println(
                "RAW_HOLDS_REQUEST="
                + (RAW_EVENTS.peekFirst() == request));

        System.out.println(
                "SAFE_ACCEPTED_1=" + recordSafe(101, 2500L, 0));
        System.out.println(
                "SAFE_ACCEPTED_2=" + recordSafe(102, 5000L, 0));

        System.out.println("SAFE_EVENT=" + SAFE_EVENTS.peekFirst());

        boolean thirdAccepted = recordSafe(103, 7500L, 1);
        System.out.println(
                "THIRD_DROPPED=" + !thirdAccepted);

        // Drop the strong reference held by the static queue itself.
        RAW_EVENTS.clear();
        System.out.println(
                "RAW_QUEUE_EMPTY=" + RAW_EVENTS.isEmpty());

        // Do not test GC timing: request could still reside
        // in locals or other non-visible references.
        request = null;

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Task A intentionally omits removing context.
            pool.submit(() -> CONTEXT.set("request-A")).get();

            boolean stale = pool.submit(
                    () -> "request-A".equals(CONTEXT.get())).get();
            System.out.println("STALE_CONTEXT_SEEN=" + stale);

            // Clear context on the right worker thread.
            pool.submit(() -> CONTEXT.remove()).get();

            // Task B: proper cleanup in finally.
            pool.submit(() -> {
                CONTEXT.set("request-B");
                try {
                    // Simulate work; do not retain Request.
                } finally {
                    CONTEXT.remove();
                }
            }).get();

            boolean cleaned = pool.submit(
                    () -> CONTEXT.get() == null).get();
            System.out.println("AFTER_FINALLY_CLEAN=" + cleaned);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

The program intentionally runs on **one main thread and one executor thread**, not a multi-threaded production queue. `ArrayDeque` is not thread-safe; the demo only accesses the queues on main. `Measurement` is a nested record with three primitive fields, so the record itself does not reference `Request`. `ThreadLocal<String>` uses short strings because the goal is to demonstrate **stale context leaking into a new task**; if `Request` were placed in a ThreadLocal in production, the graph-retention risk would be much worse.

### 6.2. Compile and Run

Use JDK 17 or newer in the directory containing the file:

```shell
javac RetentionDemo.java
java RetentionDemo
```

**Stdout from the code logic:**

```text
RAW_HOLDS_REQUEST=true
SAFE_ACCEPTED_1=true
SAFE_ACCEPTED_2=true
SAFE_EVENT=Measurement[methodId=101, durationNanos=2500, outcomeCode=0]
THIRD_DROPPED=true
RAW_QUEUE_EMPTY=true
STALE_CONTEXT_SEEN=true
AFTER_FINALLY_CLEAN=true
```

Explanation:

- `RAW_HOLDS_REQUEST=true` proves the static queue is holding **the exact same Request instance** while it has not been `clear()`ed.
- `SAFE_ACCEPTED_1/2` are true because the queue has not hit the 2-event limit. The printed record contains only scalar metadata.
- `THIRD_DROPPED=true` is the result of the policy rejecting the third event, not an assumption that the network has successfully sent the first two events.
- `RAW_QUEUE_EMPTY=true` proves the **reference has been removed from this queue**; it **does not** prove the object has definitely been reclaimed by GC.
- `STALE_CONTEXT_SEEN=true`: the same executor worker thread runs task B after task A, so it sees the ThreadLocal value that task A forgot to clear.
- `AFTER_FINALLY_CLEAN=true`: the task using `finally` removed the context on that same thread; the next task sees no stale data.

**What this lab does not prove:** it does not measure exact retained bytes, does not prove when GC collects objects, does not stress multi-threaded queue access, and does not have an actual Java agent injecting bytecode. The goal is to demonstrate reference ownership and scope cleanup using standard Java commands.

### 6.3. How to Turn the Demo into a Good Pattern

Do not copy `RAW_EVENTS` into a real helper. In production instrumentation:

- Do not create an `Object[] args` array if the measurement does not need arguments.
- If the helper only needs `methodId` and `durationNanos`, bytecode should pass those exact primitives.
- Use a thread-safe queue with capacity and a drop policy, such as `ArrayBlockingQueue<Measurement>` for an appropriate pipeline.
- When the async exporter dequeues an event, do not reconstruct `Request` via a lookup cache to serialize later.
- Clear context in `finally` on the right thread; for async flows, plan to transfer **small scoped IDs** rather than carrying the entire request.
- Retain for only a reasonable duration for retries/backlog, and design shutdown and cleanup.

## 7. ThreadLocal: A Thread Can Outlive Many Requests

`ThreadLocal<T>` provides a value **per thread**, not an automatic per-request scope. According to the Javadoc, each thread holds a reference to its copy of a thread-local variable under the conditions described by the thread and ThreadLocal lifecycles. If a pool thread lives for many hours, a request object placed in a ThreadLocal can remain retained after the task has finished.

```java
// Illustrative ANTI-PATTERN, not a standalone file:
private static final ThreadLocal<Object> CURRENT_REQUEST =
        new ThreadLocal<>();

void handle(Object request) {
    CURRENT_REQUEST.set(request);
    process(request);              // If it throws, not removed.
}
```

The consequence is not just heap pressure: a task for request B on the same thread can read **request A's context**, causing wrong trace IDs or cross-request data leaks.

**Fixed pattern:**

```java
// Illustrative pattern; process(...) is an application method.
void handle(Object request, String approvedTraceId) {
    try {
        CURRENT_TRACE_ID.set(approvedTraceId);
        process(request);
    } finally {
        CURRENT_TRACE_ID.remove();
    }
}
```

This snippet assumes `CURRENT_TRACE_ID` is an already-declared `ThreadLocal<String>`; `request` is only passed to the application, **not placed into an agent ThreadLocal**. The trace ID must have a schema/budget/privacy policy, and `remove` must run on **the exact thread that called `set`**.

### 7.1. Nested Calls and Scope Restoration

If a helper uses `ThreadLocal` to pass context across nested methods, an unconditional `remove()` in an inner scope can wipe out the outer scope's context. For example:

```text
outer request scope: trace A
  enter nested operation: trace B
  nested operation exits
  outer expects trace A restored
```

With true nesting, a **save/restore previous value** policy is needed:

```java
// Illustrative pattern with a CONTEXT variable of type ThreadLocal<String>.
String previous = CONTEXT.get();
try {
    CONTEXT.set(childTraceId);
    runNested();
} finally {
    if (previous == null) {
        CONTEXT.remove();
    } else {
        CONTEXT.set(previous);
    }
}
```

This is only safe if `previous` is **a small context permitted to exist in the outer scope**, not a reference to a huge request object. When the outer scope finishes, the outer scope itself must also clean up. Replacing `remove` with `set(null)` is not always equivalent in lifecycle and initial-value semantics; prefer `remove` at the actual ending boundary.

### 7.2. Async Threads and Virtual Threads

`ThreadLocal` does not automatically become "request scoped" just because a thread comes from an executor. With `CompletableFuture.supplyAsync`, a callback may run on a different thread pool; the context may be **absent** or retained on the worker thread if cleanup is wrong.

With virtual threads (Java 21), each virtual thread also supports ThreadLocal, but there can be vast numbers of them with their own lifecycles. Abusing large data in ThreadLocal still increases memory footprint, and frameworks/jobs may spawn new threads frequently. Do not use ThreadLocal as a storage bin for `Request` across an asynchronous transaction; transfer **minimal metadata** within an explicit scope.

`InheritableThreadLocal` can pass values to child threads under defined conditions, but that can **widen reachability** to many threads. Do not choose it as an agent payload-passing channel just to avoid adding a method parameter.

### 7.3. MDC/Tracing Context Is Also Lifecycle-Bound Data

A logger's Mapped Diagnostic Context (MDC) and a tracing library's "current span" usually rely on thread-local or scope-style context storage. Make sure to close scope tokens and clear context in `finally`, especially in worker pools. When transferring context to another task, copy only **trace/span identifiers** and approved baggage; do not attach a whole request/session/Throwable to baggage.

## 8. Callbacks, Lambdas, Futures, Timers: Hidden References Inside Deferred Work

A lambda can capture variables from its enclosing scope. If the lambda is held in a scheduler or retry queue longer than the request, the captured objects can also live longer.

```java
// ANTI-PATTERN, illustrative snippet:
Request request = ...;
scheduler.schedule(
    () -> exporter.export(request), 60, TimeUnit.SECONDS);
```

In this example, the lambda can retain `request` at least until the scheduler releases the task/callback; in practice it also depends on lifecycle, cancellation, and scheduler structure. A callback registered in a listener registry can persist indefinitely if never unregistered.

**Better approach:** convert to a primitive snapshot before creating the callback:

```java
// Variables/scheduler/exporter are assumed in this illustrative code.
int methodIdSnapshot = methodId;
long elapsedSnapshot = elapsedNanos;
int outcomeSnapshot = outcome;

scheduler.schedule(
    () -> exporter.export(
        methodIdSnapshot, elapsedSnapshot, outcomeSnapshot),
    60, TimeUnit.SECONDS);
```

Even so, the lambda still captures `exporter` and can extend the exporter's lifetime. This may be intentional if the exporter is a global agent component; you must control where tasks are scheduled, handle shutdown/cancel, and avoid creating a new exporter object per request.

### 8.1. A Pending Future Does Not Mean Callbacks Are Released

An incomplete `CompletableFuture`, a queued `FutureTask`, or a retry closure can still hold captured references. Calling `cancel` does not always mean the task is immediately removed from every queue/graph; behavior depends on the executor/implementation. Set timeouts and cleanup, measure pending tasks, and inspect heap paths rather than assuming GC has freed objects after a cancel call.

### 8.2. Listener Registration and Class-Loader Leaks

`static listenerRegistry.add(listener)` where the listener is an anonymous inner class/lambda capturing an object from an application module can retain the listener, the owner object, and the plugin's class loader. On undeploy, the agent/JVM registry remains alive, so the plugin loader cannot be unloaded by GC.

You need to use a registration handle to **unregister** at the corresponding lifecycle point, or a semantically sound weak-listener structure if truly appropriate. A weak listener can be GC'd before work completes; therefore, it is not a default solution if the callback is a mandatory responsibility.

### 8.3. Using `Supplier<?>` Does Not Make Data Automatically Safe

A "lazy event" such as:

```java
queue.offer(() -> request.toString());
```

does not call `toString` immediately, but **the closure still retains the request**. When the consumer processes it later, it both retains the graph longer and invokes application code on another thread. This can be even harder to diagnose than synchronous stringification. If you do not need the object's contents, do not create a capturing supplier in the first place.

## 9. Metadata Caches and Class-Loader Unloading

A Java agent typically lives for the lifetime of the JVM, while a webapp/plugin may be redeployed multiple times with **different class loaders**. An agent cache that holds strong key/value references to application classes can prevent old class loaders from being GC'd:

```java
// Illustrative ANTI-PATTERN:
static final Map<Class<?>, Object> METADATA =
        new ConcurrentHashMap<>();

METADATA.put(applicationClass, metadata);
```

`Class<?>` is tied to the class definition, and metadata may contain `Method`, `Field`, `MethodHandle`, `ClassLoader`, callbacks, or lambdas capturing the application class. A static map held by a long-lived agent class can create a retention chain to the application's loader.

```text
Agent singleton
  └─ static metadata map
      └─ key: Class<?> of webapp V1
          └─ defining ClassLoader V1
              └─ many classes/resources/caches of the webapp
```

Not only the key: the value can also retain the loader, even if the key is a `String` binary name. And the same binary name can be defined by different loaders, so caching by a bare string name also risks **returning wrong metadata** across deployments.

### 9.1. How to Manage Caches

- Cache only when truly needed; prefer small IDs/descriptors, and do not retain `Class<?>` indefinitely.
- Scope caches to the **class-loader/deployment lifecycle**, and clear them when the application unloads if a reliable hook exists.
- If using weak keys, ensure values **do not reference back** to keys/classloaders.
- Check references inside `MethodHandle`/reflection metadata, callbacks, and executor tasks; they can indirectly retain the declaring class.
- Consider cache structures with eviction/LRU/size/TTL, though TTL is not an absolute class-loader cleanup policy if an object is still held by a value outside the cache.
- Do not rely on `ClassLoader.finalize` or "waiting for GC to take care of it"; explicit ownership/lifecycle is needed.

### 9.2. `WeakHashMap` Can Be Misleading

`WeakHashMap<K,V>` holds **keys via weak references** but **values via strong references**. If a value holds the key (directly or through a chain of objects), the key is not weakly reachable and the entry may never disappear.

```java
// Illustrates the hazard (not recommended as a production cache):
Map<Object, Object> cache = new WeakHashMap<>();

Object key = new Object();
Object value = new Object() {
    final Object owner = key;
};
cache.put(key, value);

// Value -> key: since the map holds value strongly, key remains reachable.
```

This is an illustrative concept, not a GC test. In real Java source, a local variable `key` captured in an anonymous class must be **final or effectively final**; the snippet above does not reassign `key`, so it satisfies that. In real metadata cache cases, however, cycles can be indirect through class/method/loader.

**Do not claim "using WeakHashMap eliminates class-loader leaks"**. You must analyze the strong-reference graph of both keys and values and ensure structures/callbacks do not pin the loader elsewhere.

### 9.3. `WeakReference` Does Not Replace a Data Policy

`WeakReference<Request>` does not itself keep the referent strongly reachable, so it can be useful for best-effort observation tables. However:

- `weak.get()` can return `null` at any time convenient to GC, with no guarantee the data will still be there for the exporter to read.
- Another object may still hold the request via a strong reference, so changing only **one field** to weak does not prove retention is gone.
- If every event requires the payload to guarantee accurate export, using weak references can cause uncontrolled data loss.
- You should not call `System.gc()` on a hot path and wait for collection to verify logic.

For telemetry, it is better for events **not to need the referent**, containing only an approved snapshot.

## 10. Sensitive Data, Size, and Cardinality

A reference leak often comes with privacy risk: a `Request` object can hold request bodies, headers, tokens, sessions, account identifiers, credentials, or user data. When a queue stores the reference, that data can linger in the heap and appear in heap dumps, even if the pipeline was only meant to export latency.

### 10.1. Data Policy to Establish Before Instrumenting

- **By default, do not capture arguments, return objects, or Throwables**.
- Record only `methodId`, duration, outcome, and controlled trace/span IDs.
- If a field must be captured, there must be an allowlist, privacy review, cap, TTL, ownership, and dedicated tests.
- Do not use raw user ID/order ID/exception message as a metric label: high cardinality and easy data exposure.
- Do not convert a raw payload to Base64/JSON and call it a "small snapshot" — the copy is still the data and still consumes memory.
- Restrict log/heap dump access; heap dumps can contain secrets currently in memory.
- Enforce permissions and audit capture configuration changes; have a way to disable the feature when a retention bug is found.

### 10.2. Budgets Must Be Applied Before Copying

A sample policy:

```text
captureMode                = NO_RAW_ARGUMENTS
maxEventCountInQueue        = 1024
maxEventPayloadBytes        = 256
maxExporterBatchEvents      = 256
maxPendingRetries           = 2
maxEventAgeMillis           = 5000
overflowPolicy              = DROP_WITH_COUNTER
captureSensitiveData        = false
```

The numbers are **configuration examples**, not safe defaults for every system. `maxEventPayloadBytes` is only useful when events are already designed to contain bounded data, **without raw object references**. A single reference can pin a huge graph far beyond any "256 bytes" estimate.

**Retention time budget:**
`t_lifetime = t_last_reference_release - t_capture`, not just `t_export - t_capture`. An exporter may report success while still holding the event in a last-batch list or retry closure; references must be cleared upon completion.

## 11. Measuring Overhead and Detecting Retention with Tools

### 11.1. Do Not Conclude a Leak from a `System.gc()` Test

`System.gc()` is a request/hint; the JVM may react differently depending on collector configuration. Local variables in active frames or JIT optimizations also affect reachability. Therefore, a test like:

```java
WeakReference<Request> ref = new WeakReference<>(request);
request = null;
System.gc();
assert ref.get() == null; // WRONG if treated as a deterministic test.
```

is unreliable for asserting "GC must collect the object immediately". The snippet is an **illustrative anti-pattern**, not a unit test to copy. Instead, use evidence such as queue element counts, in-flight event counts, class-loader counts, heap dumps/retained-size paths, and controlled load tests.

### 11.2. Metrics to Monitor

```text
probe_events_accepted_total
probe_events_dropped_total{reason}
probe_queue_depth
probe_inflight_batches
probe_oldest_event_age_seconds
probe_capture_bytes_estimated_total
probe_export_retries_total
probe_export_latency_seconds
probe_context_cleanup_errors_total
probe_active_registrations
probe_metadata_cache_entries
probe_classloaders_observed
```

These metric names are **suggestions**, not a standard API. Do not add labels for request IDs, unbounded raw class loader identity strings, arguments, or emails. Monitor from the moment the agent is enabled against a baseline with it disabled, and watch peak heap, allocation rate, p95/p99 latency, GC pause time, and memory after a traffic + idle cycle.

### 11.3. Diagnosing with `jcmd` (HotSpot JDK 17+)

For a Java process with a real PID, after obtaining operational authorization:

```shell
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /secure/path/heap.hprof
```

**The two commands above are templates**: replace `<pid>` with the actual numeric PID and the path with a permitted writable location. According to `jcmd` documentation, histogram/heap dump commands can **heavily impact the process** (especially on large heaps), and heap dumps can contain credentials/PII. Run them only after assessing impact, in an environment with appropriate access controls, and do not capture production heap dumps routinely.

In a heap analysis tool such as Eclipse MAT or an equivalent profiler, look for:

1. Instances of `Request`/`Payload` still alive after traffic stops.
2. **Path to GC Roots**: what is retaining `Request` (static `EVENTS`, `ThreadLocalMap`, task queue, listener registry, metadata cache)?
3. **Dominator tree/retained size**: which object is responsible for retaining a significant graph?
4. Class loader count after multiple redeploys/agent attaches.
5. Queue state and in-flight/retry events at the time of capture.
6. Is there a difference between "validly in-flight" and "past its lifecycle yet still retained"?

A class histogram only tells you counts and sizes by class; it **does not by itself show which object is holding the reference**; a heap graph/path is needed to conclude a retention chain. During analysis, avoid placing heap dumps in unprotected storage.

### 11.4. Two-Phase Controlled Testing

**Phase A – agent disabled:** generate a representative volume of requests, complete all requests, and measure steady-state heap/GC and class loader lifecycle.

**Phase B – agent enabled:** same traffic, same observation window, with the exporter throttled in a controlled manner; compare queue depth, retained heap, latency, pending tasks, and counts. After traffic returns to 0, verify that queues/callbacks/contexts are all cleaned up; if any objects remain alive, trace the path to GC roots.

Run multiple iterations because GC, JIT warm-up, and allocation behavior have variance. **Do not set a rigid threshold of "0 live request objects"** while threads/tasks are still processing or the heap dump includes validly reachable objects.

## 12. Designing Probes Compatible with Callback/Bytecode Instrumentation

A production helper should not accept every argument as an object just to compute latency:

```java
// Preferred API design:
void onEnter(int methodId);
void onExit(int methodId, long elapsedNanos, int outcomeCode);
```

This is a **descriptive interface**, not a standalone runnable source file. When injecting bytecode, you can pass a primitive method ID and elapsed time, not `this`, `args`, return value, or exception object. This reduces live references in the helper and reduces data-exposure risk.

### 12.1. Do Not Retain `this` Just to Correlate Enter/Exit

A common design does:

```text
onEnter(this, args) -> create event with object identity
onExit(this, result) -> look up event to complete
```

If an event map is keyed by `this`, each instance can be retained until exit or longer if the method throws or the task is cancelled. Use a safely generated scalar token/ID, or store the start time in a local variable of **the instrumented call** when the bytecode design allows. On method exit, emit the small event and release the invocation state.

### 12.2. Guards and Helper Lifecycle

A reentrancy guard such as `ThreadLocal<Boolean>` can prevent a helper from re-entering probes on the same thread, but the guard must also be `remove()`d in `finally`. Do not put a raw `Request` in the guard. A boolean/enum has a low footprint, but if guard logic stores a Throwable or full argument context, it creates a new source of retention.

### 12.3. When Instrumenting Async APIs

A probe around `CompletableFuture`/executors often wants to measure the time "from submit to complete". Retaining the request object just to wait for the callback is the wrong design. Create a very small **span/token**, correlate via an ID or context record containing no domain objects, and remove the registration on complete/timeout/cancel.

If a map of pending operations is needed, it must have **bounded entries, timeouts, cleanup, and race protection** between complete/timeout/cancel. A static `ConcurrentHashMap<UUID,Request>` is not safe just because it uses a concurrent data structure.

### 12.4. Interaction with Class Loading

A Java agent outlives many webapp class loaders. Do not retain `Class<?>`/`ClassLoader` from `ClassFileTransformer.transform(...)` callbacks in a permanent static metadata map unless there is a solid lifecycle policy. Such caches can prevent class unloading across multiple deployments.

If metadata is needed, use lightweight descriptors/identifiers and loader-scoped caches with a release mechanism, checking for weak-key cycles. Also do not store raw `ProtectionDomain` or `Module` alongside class loaders indefinitely just to diagnose each method invocation.

## 13. Safe Implementation Checklist

### Before Recording Telemetry Data

- [ ] Does the probe actually need arguments/return value/exception object? If not, **do not pass them**.
- [ ] Does the event schema use only primitives/finite metadata or an approved snapshot?
- [ ] Are sampling/policy decisions made before any expensive copy/serialization?
- [ ] Are size/TTL/cardinality all bounded with clear behavior when budgets are exceeded?
- [ ] Is there no default `Object.toString()`/JSON serialization/Java Serialization on arbitrary objects?
- [ ] Do queues/async loggers avoid holding `Object[] args` or `Supplier`s capturing requests?
- [ ] Are Throwables/stacks/contexts and sensitive strings handled according to the data policy?

### During Request Processing

- [ ] Are ThreadLocal, MDC, and tracing scopes restored/removed in `finally`?
- [ ] For nested calls, is the outer context properly restored?
- [ ] If a task hops to another thread, does the forwarded data contain only minimal metadata?
- [ ] Are no callbacks/lambdas created that retain the request longer than the task?
- [ ] Are no locks held or application threads blocked just to wait for the exporter?
- [ ] Does instrumentation preserve the application's return values and exception semantics?

### After Completion and on Application Undeploy

- [ ] Does the producer hold no remaining references to original objects in queued events?
- [ ] Does the consumer release batches/callbacks after exporting or dropping?
- [ ] Are cancellation/timeout/unregister executed at the right lifecycle points?
- [ ] Do metadata caches avoid pinning `Class<?>`/classloaders that are no longer in use?
- [ ] Do heap paths show no static agent roots retaining requests/sessions beyond request scope?
- [ ] Is queue-full/backpressure still bounded by retained memory, not just entry count?
- [ ] Are heap dumps/traces containing sensitive data kept out of unauthorized locations?

## 14. Misconceptions to Avoid

1. **"The request has returned, so all request objects can be GC'd immediately."** False if a queue/callback/ThreadLocal still holds a strong reference.
2. **"Holding just one Object reference is cheap."** A single reference can retain a very large object graph.
3. **"Cloning `Object[]` before enqueueing is an independent snapshot."** False; array cloning is shallow; the elements are still the same objects.
4. **"A queue bounded to 1000 events is definitely bounded to 1000 × a few dozen bytes."** False if each event retains a raw request.
5. **"Async logging doesn't slow down the request, so it doesn't retain objects either."** False; async events can hold references and format late.
6. **"When a ThreadLocal key is gone, the value is definitely freed immediately."** Do not assume that; manage lifecycle/`remove` explicitly.
7. **"ThreadLocal clears itself after each HTTP request."** False; it is bound to the thread, not by default to the request.
8. **"Once the executor task finishes, callbacks are released everywhere."** Not necessarily; registries/Futures/listeners/retries can still hold them.
9. **"`WeakHashMap` guarantees no classloader leaks."** False if the value retains the key or loader via another path.
10. **"`WeakReference` always keeps the object long enough for the exporter."** False; GC may clear it before it is used.
11. **"Calling `System.gc()` and seeing a non-null weakRef proves a leak."** False; GC is not guaranteed to run or be ready to collect.
12. **"`Class<?>` is just small metadata; retaining it indefinitely is fine."** It is tied to the class definition and defining loader.
13. **"Hashing user IDs definitely anonymizes them."** False; low-entropy IDs can be reversed and still cause cardinality issues.
14. **"A snapshot means serializing all fields and then truncating to 256 bytes."** False; before truncation it has already traversed the graph, spent memory/CPU, and possibly run user code.
15. **"The exporter finished sending, meaning all references are cleared."** You must check batches, retry buffers, callbacks, and caches.
16. **"Every long-lived object is a leak."** No: you must compare against valid lifetime and root paths.
17. **"`GC.class_histogram` points to the code retaining the request."** No; you need the heap graph/path to GC roots.
18. **"If instrumentation doesn't modify class fields, it can't cause a memory leak."** False; the helper's own static fields can retain app objects.
19. **"You need to keep the exception object to know an error occurred."** Usually an outcome code or approved classification is enough.
20. **"Just adding a timeout solves everything."** Timeouts help, but objects can still be retained in queues/callbacks that cleanup fails to clear.

## 15. Self-Check Questions

1. **What is the key condition that prevents GC from reclaiming a request object?** There is still a strong reference path from a GC root to the object.
2. **Why is `static Queue<Object[]>` dangerous?** It directly holds references to all arguments and their related graphs; the queue can outlive the request.
3. **Does `arguments.clone()` solve object retention?** No, array cloning is a shallow copy.
4. **Why is an event with only `methodId,durationNanos,outcomeCode` more suitable?** It requires no references to domain objects and has a small, stable schema.
5. **Is dropping an event when the queue is full a silent telemetry bug?** Not if it is designed as a policy with explicit counters/status; drops must be distinguished from export success.
6. **Does ThreadLocal store values per request or per thread?** Per thread; it must be cleaned up at task/request boundaries.
7. **Why is `remove()` placed in `finally`?** To clear the context even when business code throws an exception.
8. **Why do nested scopes sometimes need to restore the previous value?** An inner scope ending must not accidentally wipe out the valid context of an outer scope.
9. **How can `CompletableFuture` retain a request?** Callbacks/lambdas or pipeline stages capture the request in their closure.
10. **Why can an event containing a `Throwable` retain a lot of data?** The Throwable object, cause/suppressed/custom fields, and classloader can be in the reachable graph.
11. **What can storing `Class<?>` in an agent static map cause?** It retains the app's class/defining loader, blocking class unloading.
12. **Does `WeakHashMap` completely solve the problem?** No, if the value retains the key directly or indirectly.
13. **Does `WeakReference.get()==null` guarantee the exporter will always get the payload?** No, on the contrary, the referent may already be lost.
14. **Why shouldn't you rely on `System.gc()` to assert object collection?** GC timing is non-deterministic.
15. **Is a bounded queue containing large Requests truly bounded in retained bytes?** Not to a tight limit if graph sizes vary unboundedly.
16. **What in the demo caused `STALE_CONTEXT_SEEN=true`?** A task forgot to remove ThreadLocal, and the next task ran on the same worker thread.
17. **What caused `AFTER_FINALLY_CLEAN=true`?** The task removed the context in `finally` on the right thread.
18. **Why can an event retained by the exporter longer than the request still be acceptable?** If the event contains only an approved, bounded snapshot and does not pin application objects.
19. **What is the first step when suspecting an agent-induced leak?** Identify the reference graph/GC roots and compare actual lifetimes, not just observe heap growth.
20. **When the business needs detailed payloads but privacy/retention forbids it, what should be done?** Drop the feature or design an approved dedicated capture API; do not retain the entire graph.

## 16. Official References

- [Java SE 21 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread value copies and `remove()`, thread-scoped lifecycle.
- [Java SE 21 — `java.lang.ref`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/package-summary.html): strongly/softly/weakly/phantom reachable and reference queues.
- [Java SE 21 — `WeakReference`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html): weak references and clearing behavior.
- [Java SE 21 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html): weak keys but strong values, warning about values retaining keys.
- [Java SE 21 — `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded-capacity queue and `offer`/`put`.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): task execution, shutdown, and lifecycle.
- [Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): asynchronous stages and callbacks.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent lifecycle and instrumentation entrypoints.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer callbacks, class loaders, and transformation scope.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `GC.class_histogram`, `GC.heap_dump`, and operational impact.
- [Java SE 21 — `Object`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): `toString` and object method contracts.
- [Oracle Java SE Core Libraries Developer Guide](https://docs.oracle.com/en/java/javase/21/core/java-core-libraries-developer-guide.pdf): describes risks of ThreadLocal outliving its scope and cleanup in thread pools.

**Conclusion:** to measure performance without altering the application lifecycle, **do not let agent events/queues/ThreadLocals/callbacks/caches retain `Request`, `Object[] args`, `Throwable`, `Class<?>`, or application graphs longer than needed**. Feed the pipeline a **minimal, approved, budgeted snapshot with no references back to original objects**, clean up at the right lifecycle points, monitor retained heap, and inspect paths to GC roots. Good measurement not only produces accurate metrics, but also **returns data-collection rights to the application as soon as the data is no longer needed**.