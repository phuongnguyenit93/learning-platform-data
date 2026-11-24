# Specifying Instance Cardinality, Shared State, and Synchronization Mechanisms in the Java Plugin Lifecycle

## 1. Why Must the Plugin Lifecycle Explicitly Define Instance Cardinality?

A Java host can discover and load a **plugin implementation** via `ServiceLoader`, a dedicated class loader, a `ModuleLayer`, or a plugin-provided factory. Yet finding a class and instantiating an object **does not answer** three critical operational questions:

1. **How many instances does a plugin have?** One instance for the whole host, one instance per plugin generation, per tenant, per session, per request, or a bounded pool?
2. **What state is shared?** Do counters, caches, connections, configuration, user state, transaction context, and per-call data belong to the instance or the host?
3. **How are concurrent calls handled?** Is the plugin safe when two threads call it at once? Must the host lock, issue a separate instance, cap concurrency, or reject requests while stopping?

Failing to clarify these questions leads to unpredictable results: lost updates, cross-tenant data corruption, use-after-`close()`, class loader leaks, callback deadlocks, or excessive object and resource creation.

For example, suppose a host uses a singleton `Plugin` containing a mutable `int requestCount` field and two threads execute `requestCount++` concurrently. That increment is read–add–write; without synchronization guarantees, updates can be lost. Conversely, if the host creates an instance per request, races on instance fields may disappear, but the cost of initializing a database client, model, or interpreter spikes sharply.

**Principle:** instance cardinality, state ownership rules, and concurrency are **part of the host–plugin contract**, and must be declared, verified, and enforced across `create → initialize → start → invoke → quiesce → stop/close → unload`. Do not leave each plugin to guess.

### 1.1. Distinguishing Three Easily Confused Quantities

- **Live instances**: how many plugin objects are currently held by the host and potentially usable.
- **Total instances created**: cumulative count since the start of the generation. With `PER_CALL`, this number grows with requests even though older instances have closed and been GC'd.
- **In-flight calls**: how many calls have not yet returned. One shared instance can handle multiple in-flight calls if thread-safe; a pool of 4 instances allows at most 4 concurrent uses if each instance is leased to only one borrower at a time.

These numbers are not equal. Therefore `maxInstances=4` does not automatically mean `maxConcurrentCalls=4`, and `singleton` does not automatically mean `single-threaded`.

## 2. Common Instance Cardinality Policies

| Policy | Typical Instance Count | Shared State | Use When | Watch Out For |
| --- | --- | --- | --- | --- |
| **Singleton within a host/generation** | 1 | All calls hit the same object | Plugin is cheap, thread-safe, or needs a shared registry | Races, tenant state leakage, close affecting all requests |
| **One instance per call (per-call)** | 1 fresh instance per invoke | Little per-instance sharing | Plugin has mutable state, short processing | Creation/close overhead; large cumulative instance count |
| **Per-session** | 1 per active session | State within the session | Multi-step workflows needing context | TTL, eviction, concurrent requests within a session |
| **Per-tenant** | 1 or a set per tenant | Scoped to a single tenant | Per-tenant config/caches | Data isolation, per-tenant quotas |
| **Per-thread (thread-confined)** | Usually 1 per involved thread | On that thread | Libraries with true thread affinity | Thread pools reusing threads, `ThreadLocal` leaks |
| **Object pool** | At most N objects in the pool | Controlled reuse | Expensive initialization, not thread-safe | Borrow/return, state reset, broken instances, backpressure |
| **Per-request scope + shared host service** | N plugin instances, few host services | Only services explicitly shared by the host | Want state isolation while keeping shared caches/connections | Service permissions, transactions, and thread safety |

**A singleton in the host is not a JVM-wide or cluster-wide singleton.** When a plugin is reloaded by another class loader, a singleton class or static field in the new loader can be a separate copy. If **cluster-wide** uniqueness is required, you must use an external mechanism such as a database lock, coordinator, or a service designed for distribution; you cannot rely on `static` or `synchronized` inside one process.

### 2.1. Choose by Plugin Characteristics, Not Framework Habit

Evaluate along these axes:

- **Initialization cost**: large parser/cache, connections, native resources, dedicated threads?
- **Reusability**: can the same instance process another request without carrying over stale data?
- **Thread safety**: can `process` be invoked concurrently on the same instance?
- **State scope**: host-wide, per-tenant, per-user, per-transaction, or per-invocation?
- **Blocking potential**: can I/O block for long periods, or can locks stall unrelated requests?
- **Resource limits**: memory, connections, file descriptors, threads, request backlog?
- **Version replacement**: must the old plugin instance/loader keep serving in-flight requests while a new generation starts?

For example, a plugin performing pure transformations with immutable configuration usually fits a singleton. A non-thread-safe parser that is cheap to construct can be per-call; one that is non-thread-safe and expensive to initialize can use a pool with state reset. A per-tenant cache should not sit inside a global singleton without partition keys and access controls.

### 2.2. “Factory Singleton” and “Plugin Singleton” Are Different Concepts

A `PluginFactory` may be held as a single object in the registry, yet each `factory.create()` call still returns a **new plugin instance**. Conversely, a factory may return the same object on every call. The host must **specify scope by contract**, not infer it from the number of factories.

The contract may include metadata:

```java
enum Scope { SINGLETON, PER_CALL, PER_TENANT, POOLED }
enum ConcurrencyMode { THREAD_SAFE, SERIALIZED, CONFINED }

record PluginPolicy(
        Scope scope,
        ConcurrencyMode concurrency,
        int maxActiveCalls,
        int maxInstances,
        boolean reusableAfterFailure) {

    PluginPolicy {
        if (maxActiveCalls < 1 || maxInstances < 1) {
            throw new IllegalArgumentException("limits must be positive");
        }
    }
}
```

This is a **standalone illustrative API model**, not a `PluginPolicy` built into the JDK and not the code of the runnable demo in Section 6. The registry must verify that the declared policy matches the real implementation, version, and resources; “the plugin claims `THREAD_SAFE`” cannot substitute for testing.

A good design keeps the final decision with the host: a plugin that only supports `SERIALIZED` must not be forced by the host to serve parallel calls on the same instance. If the host needs higher throughput, it can create multiple independent instances or use a pool if permitted by the plugin.

## 3. Classifying State: What Is Allowed to Be Shared?

Rather than treating every field on a plugin as identical state, separate them by ownership and lifetime.

| State Category | Examples | Ideal Owner | Rules |
| --- | --- | --- | --- |
| Immutable configuration | Endpoints, feature flags, API version | Host/generation | Initialize once, publish safely |
| Per-invocation state | Request ID, input, response builder | Invocation | Do not store in singleton fields |
| Per-session state | Workflow step, session token | Session | TTL, authorization, reset/cleanup |
| Per-tenant state | Tenant cache, quotas, mappings | Tenant/partition | Keyed by tenant, no cross-tenant sharing |
| Intentional shared state | Metric counters, immutable lookup tables | Host or shared plugin | Use atomics/locks/concurrent collections |
| External state | DB transactions, message offsets, distributed leases | Service/DB | Transactions/idempotency and distribution |
| Lifecycle-managed resources | Connections, executors, file handles | Host/factory/instance per contract | Close exactly once; never close while in use |
| Class-level static state | Static maps/caches inside plugin JAR | Defining class loader | Do not assume sharing across loaders/generations |

### 3.1. Immutable Configuration Is a Good Starting Point

Configuration should be built as immutable objects (`record`s or `final` fields) and completed before publishing the plugin instance to request threads. Publishing the object must establish a proper **happens-before** relationship: complete construction, `final`-field semantics, and registry/thread-safe publication mechanisms; merely marking a field `final` does not fix data races if it references a mutable collection that keeps changing.

When reloading config, you can swap the entire immutable snapshot via a `volatile` reference or `AtomicReference<Config>`, while deciding whether a request reads **one snapshot** throughout or may observe multiple versions mid-flight.

### 3.2. Do Not Store Request Data in Singleton Fields

Classic mistake:

```java
class UnsafePlugin {
    private String currentUser; // mutated across requests

    String handle(String user) {
        currentUser = user;
        return "hello " + currentUser;
    }
}
```

This is **warning code**, not production code. If thread A writes `"alice"` and then thread B writes `"bob"` before A reads it back, A can return B's name. Adding `volatile` only improves visibility; **it does not turn a global field into per-request state**.

The simplest fix is to put the data in local variables or a passed-in context object:

```java
record Request(String user) {}

String handle(Request request) {
    return "hello " + request.user();
}
```

This is an **integration snippet**; the method must live inside a valid class and `Request` must share the same runtime type between host and plugin if crossing a boundary. In plugin APIs, put request/response DTOs in the shared contract and do not let multiple tenants share mutable request objects.

### 3.3. “Shared” Does Not Mean “Unsynchronized”

If multiple threads update the same counter, `AtomicInteger.incrementAndGet()` or `LongAdder.increment()` fits depending on requirements (for example, `LongAdder` is often better for high-contention metrics, though `sum()` is not an atomic snapshot of all concurrent updates).

A `ConcurrentHashMap` supports thread-safe map operations, but does not automatically make a multi-step “check → compute → put” sequence transactional. When updating based on an existing value, use appropriate atomic operations such as `compute`/`merge`; be careful that callbacks inside `compute` do not block for long, mutate nested maps improperly, or carry complex side effects.

For invariants spanning **multiple fields**, an atomic counter per field may not suffice. You need a lock protecting the whole group or to swap an immutable snapshot via `AtomicReference`/CAS. Prioritize correctness before optimizing throughput.

### 3.4. ThreadLocal Is Not Per-Request by Default

`ThreadLocal` binds values to a **thread**. On servers using thread pools, a thread serving request A today can serve request B tomorrow. Forgetting `remove()` can retain request data, tenant data, classes, or an old plugin's class loader.

If a plugin must use `ThreadLocal`, create/read/clear it inside `try/finally`, and never rely on thread identity as tenant identity. For asynchronous work or virtual threads, design context propagation deliberately; do not assume thread-local state automatically propagates across executors.

## 4. Synchronization Mechanisms Suited to Each Data Kind

| Java Tool | Good For | Does Not Replace |
| --- | --- | --- |
| `final` + immutable objects | Unchanging config/state | Coordination of mutable resources |
| `volatile` | A single reference/flag needing visibility | Atomicity of `counter++`, multi-field invariants |
| `AtomicInteger` / `AtomicLong` | Counters, single-value CAS | Multi-state transactions |
| `LongAdder` | High-contention metric counters | Exact linearizable snapshots during writes |
| `ConcurrentHashMap` | Multi-reader/writer maps | Non-atomic multi-step workflows |
| `synchronized` / `ReentrantLock` | Preventing concurrent entry into critical sections | Automatic tenant data isolation |
| `ReentrantReadWriteLock` | Multiple readers, one writer; lifecycle gate | Ensuring a plugin is thread-safe when multiple readers enter the same object |
| `Semaphore` | Limiting concurrent calls/borrowers | Total created instance count or intrinsic thread safety |
| `BlockingQueue` | Bounded queue for pools | Resetting/validating instances before reuse |
| `CountDownLatch` / `Phaser` | Waiting on conditions/coordinating task groups | Full cancellation/quiescence policies |
| `ExecutorService` | Running and managing tasks | Automatically rejecting requests when a plugin has stopped |

### 4.1. Avoiding Over-Synchronization and Under-Synchronization

If a singleton plugin is **thread-safe** and each request only reads immutable config, the host can allow concurrent calls. If it is not thread-safe, there are three options: the host **serializes** calls; instantiates per request; or uses an instance pool guaranteeing at most one borrower at a time.

Serializing all calls behind a single coarse lock can sharply reduce throughput when the plugin does I/O. Moreover, a lock protecting internal plugin state is not the same as managing the **stop/unload lifecycle**: the host must still reject new requests and wait for in-flight calls before calling `close()`.

### 4.2. Lock Ordering Must Be Defined

In multi-layered systems (registry → plugin host → plugin instance → callback), if thread A holds `registryLock` and waits for `pluginLock`, while thread B holds `pluginLock` and calls back into the registry, deadlock can occur. Establish a consistent lock acquisition order, avoid invoking arbitrary plugin code while holding a broad registry lock, and never naively upgrade a read lock to a write lock.

`ReentrantReadWriteLock` **does not support upgrading a read lock → write lock** in a standard safe way: a thread holding the read lock that invokes a stop method requiring the write lock will deadlock itself. Lifecycle APIs should prevent `process()` callbacks from closing the same host while holding the read lock, or design a separate stop protocol that does not require upgrading.

### 4.3. Concurrency Limits and Backpressure

If each instance serves at most one call, a pool of size N bounds **concurrent borrowers** at N. `Semaphore(N)` can also cap in-flight requests at N even when the plugin is thread-safe. However, if the host uses only a semaphore while calling `new Plugin()` on every request, the cumulative number of created instances can still grow unboundedly over time.

In production, distinguish:

- `maxLiveInstances`: cap on live objects.
- `maxConcurrentCalls`: cap on in-flight calls.
- `maxQueuedCalls`: cap on waiting requests.
- `acquireTimeout` and **rejection/backpressure policy** under overload.
- Task-level timeouts, cancellation, and cleanup when clients disconnect.

Limits must have telemetry and load tests. Do not leave queues unbounded merely because a pool limits threads.

## 5. Safe Shutdown Protocol with In-Flight Requests

A typical lifecycle can be described as:

```text
DISCOVERED
    |
    v
CREATED -> INITIALIZING -> RUNNING
                         |
                         | stop requested
                         v
                    QUIESCING
                    (reject new calls,
                     finish/cancel in-flight)
                         |
                         v
                    STOPPING -> STOPPED -> eligible for unload
                         |
                         +--> FAILED if cleanup fails
```

These labels are a **suggested host state machine model**, not a built-in JVM enum. What matters is specifying valid transitions, who is authorized to trigger them, observable states, and idempotent handling.

### 5.1. In-Flight Calls and Stop Must Coordinate

Common race:

```text
Thread A: check running == true
Thread B: close(plugin)
Thread A: plugin.process(request)   // use-after-close
```

Adding only `volatile boolean running` is **not sufficient**, because checking and starting work do not form an atomic admission step with `close`. You can use a **lifecycle gate**: a read lock while admitting/executing an invocation, and a write lock when stopping; or an active lease/reference count paired with a condition to wait for active count to reach zero.

In the example in Section 6, the host holds a **read lock** for the duration of `process()`. `close()` requires the **write lock**, so it cannot close the shared instance while any read-locked invocation remains inside. Once the write lock sets `closed=true`, subsequent calls acquiring the read lock check the flag and are rejected.

This model is easy to understand and prove ordered, but it **has a trade-off**: if a plugin hangs indefinitely or calls back into an operation needing the write lock, shutdown can hang. Production systems often need timeouts, cooperative cancellation, and lease/condition protocols to avoid holding locks across untrusted code; never forcibly break locks improperly.

### 5.2. Closing Resources by the Right Owner

A singleton plugin may own private connections/threads and be closed once when the host shuts down that generation. A per-call plugin can be closed in `finally` right after the invocation. A pool must return instances to the pool, check/reset state, and close all instances when the pool shuts down.

If a `DataSource`/`ExecutorService` is **injected and shared by the host**, the plugin should not close that resource on its own unless the contract assigns ownership to the plugin. A plugin accidentally closing a host-managed executor can break every other plugin.

### 5.3. Idempotency and Errors During Close

`close()` should be idempotent, or the host must guarantee it is called only once, including cleanup when initialization succeeded only partially. If cleanup throws an exception, still attempt to close independent resources, record the error, and determine the final state. Do not swallow all errors and report a clean `STOPPED` while threads/resources are still running.

For reloads, create a **new generation** and shift routing before/after quiescing according to an explicit strategy. Do not try to “swap bytecode” of a live class in an existing class loader as if it were an infinitely resettable instance.

## 6. Complete Java 17+ Example: Shared Instance, Per-Call Instance, and Lifecycle Lock

The following example uses only standard Java. The host executes 8 calls via a thread pool in **`SHARED`** mode, then switches to **`PER_CALL`** mode for 2 independent calls.

Key aspects of the demo:

- `CountingPlugin` has an `AtomicInteger` counter and an `AtomicBoolean` flag, so incrementing the counter is safe when multiple threads call the same instance.
- `PluginHost(SHARED)` creates **exactly one** `CountingPlugin` in its constructor.
- `PluginHost(PER_CALL)` creates a plugin only upon invocation, closing it in `finally` after use.
- `ReentrantReadWriteLock(true)` serves as the lifecycle gate: multiple invocations can concurrently hold the read lock; `close()` acquires the write lock to wait for calls inside the gate to finish and block new calls once closed.
- `AtomicInteger created` counts **total instances ever created**, `AtomicInteger inFlight` counts currently running calls, and `AtomicLong completed` counts successful completions. Do not conflate these three metrics.
- After stop, new invocations throw `IllegalStateException` and the host creates no further plugins.

Put the entire source into **`PluginLifecycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class PluginLifecycleDemo {
    enum Scope { SHARED, PER_CALL }

    interface Plugin extends AutoCloseable {
        int process(int input);
        int calls();
        @Override void close();
    }

    static final class CountingPlugin implements Plugin {
        private final AtomicInteger count = new AtomicInteger();
        private final AtomicBoolean stopped = new AtomicBoolean();

        @Override
        public int process(int input) {
            if (stopped.get()) {
                throw new IllegalStateException("plugin closed");
            }
            count.incrementAndGet();
            return Math.multiplyExact(input, 2);
        }

        @Override public int calls() { return count.get(); }
        @Override public void close() { stopped.set(true); }
    }

    static final class PluginHost implements AutoCloseable {
        private final Scope scope;
        private final ReentrantReadWriteLock lifecycle = new ReentrantReadWriteLock(true);
        private final AtomicInteger created = new AtomicInteger();
        private final AtomicInteger inFlight = new AtomicInteger();
        private final AtomicLong completed = new AtomicLong();
        private final CountingPlugin shared;
        // 'closed' must be accessed only under the lifecycle lock.
        private boolean closed;

        PluginHost(Scope scope) {
            this.scope = scope;
            this.shared = scope == Scope.SHARED ? newPlugin() : null;
        }

        private CountingPlugin newPlugin() {
            created.incrementAndGet();
            return new CountingPlugin();
        }

        int invoke(int input) {
            Lock read = lifecycle.readLock();
            read.lock();
            try {
                if (closed) throw new IllegalStateException("host stopped");
                CountingPlugin plugin =
                        scope == Scope.SHARED ? shared : newPlugin();
                inFlight.incrementAndGet();
                try {
                    int result = plugin.process(input);
                    completed.incrementAndGet();
                    return result;
                } finally {
                    try {
                        if (scope == Scope.PER_CALL) plugin.close();
                    } finally {
                        inFlight.decrementAndGet();
                    }
                }
            } finally {
                read.unlock();
            }
        }

        int instancesCreated() { return created.get(); }
        long completedCalls() { return completed.get(); }
        int activeCalls() { return inFlight.get(); }
        int sharedCalls() { return shared == null ? 0 : shared.calls(); }

        @Override
        public void close() {
            Lock write = lifecycle.writeLock();
            write.lock();
            try {
                if (!closed) {
                    closed = true;
                    if (shared != null) shared.close();
                }
            } finally {
                write.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginHost shared = new PluginHost(Scope.SHARED);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Integer>> tasks = new ArrayList<>();
            for (int i = 1; i <= 8; i++) {
                final int input = i;
                tasks.add(() -> shared.invoke(input));
            }
            int sum = 0;
            for (Future<Integer> future : workers.invokeAll(tasks)) {
                sum += future.get();
            }
            System.out.println("shared sum: " + sum);
            System.out.println("shared instances: " + shared.instancesCreated());
            System.out.println("shared calls: " + shared.sharedCalls());
            System.out.println("shared active: " + shared.activeCalls());
        } finally {
            workers.shutdown();
            shared.close();
        }

        try {
            shared.invoke(10);
            System.out.println("after close: accepted");
        } catch (IllegalStateException expected) {
            System.out.println("after close: rejected");
        }

        try (PluginHost perCall = new PluginHost(Scope.PER_CALL)) {
            System.out.println("per-call values: " +
                    perCall.invoke(3) + "," + perCall.invoke(4));
            System.out.println("per-call instances: " + perCall.instancesCreated());
            System.out.println("per-call completed: " + perCall.completedCalls());
        }
    }
}
```

### 6.1. Compiling and Running

On a machine with JDK 17 or newer:

```bash
javac --release 17 PluginLifecycleDemo.java
java PluginLifecycleDemo
```

**Exact stdout**, verified with `javac --release 17` and `java`:

```text
shared sum: 72
shared instances: 1
shared calls: 8
shared active: 0
after close: rejected
per-call values: 6,8
per-call instances: 2
per-call completed: 2
```

### 6.2. Explaining the Output

1. **`shared sum: 72`**: all eight inputs `1..8` are doubled. The sum is `2 × (1+2+...+8) = 72`. Task execution order can vary, but summing future results yields a deterministic total.
2. **`shared instances: 1`**: the host constructor created one plugin used across all eight calls, without creating a new plugin per thread.
3. **`shared calls: 8`**: one shared instance received eight calls; `AtomicInteger.incrementAndGet()` guarantees no counts are lost to races.
4. **`shared active: 0`**: all `Future`s completed before measuring `inFlight`. The output does not assert `active=0` at earlier points in time.
5. **`after close: rejected`**: after `shared.close()`, the host rejects new requests because the `closed` flag is guarded by the lifecycle lock.
6. **`per-call values: 6,8`**: the two calls produced independent outputs without reusing the same plugin.
7. **`per-call instances: 2`**: two total instances were created across the two calls. They were closed after each call; this number is *cumulative*, not the live instance count at print time.
8. **`per-call completed: 2`**: both invocations succeeded. `completed` does not increment for an execution that throws an exception before updating it.

### 6.3. Correctness Analysis of the Synchronization

`PluginHost.invoke` holds the **read lock** from validating `closed` until the plugin finishes processing, cleans up, and decrements `inFlight`. `PluginHost.close` holds the **write lock** to update `closed` and close the singleton. This preserves the invariant:

> No valid `process()` on the shared plugin begins **after** the host's `close()` has transitioned to the closed state, and the shared plugin is not closed while an invocation remains inside the lifecycle gate.

This is a **host** invariant; it does not automatically prove every `Plugin` subclass is thread-safe. In the demo, `CountingPlugin` uses atomics internally, so multiple read-locked invocations can increment the count concurrently. If `CountingPlugin` used a mutable `HashMap` or an unsynchronized `int counter++`, having only a read lock **would not fix the bug**, because multiple threads are allowed to hold the read lock simultaneously.

Keep in mind:

- Fairness `true` reduces the risk of a writer being continuously starved by new readers, but **does not guarantee** deadlines or strict absolute ordering for every task.
- If `process()` hangs, `close()` can wait indefinitely; the demo does not implement timeouts/cancellation.
- If a callback inside `process()` calls `PluginHost.close()` on the same host and same thread, deadlock is possible due to read → write lock upgrade.
- If `CountingPlugin.close()` throws an exception, the host needs a procedure to record cleanup failure and handle remaining resources. The demo uses an atomic flag, so `close` is lightweight and idempotent.
- The demo keeps API and implementation in one program to focus on scope and synchronization; dynamically loaded plugin systems still need shared API/SPI type identity, class loaders, and unload lifecycles.

## 7. Pairing Instance Models with Synchronization Mechanisms

### 7.1. Singleton: Thread-Safe or Serialized

A singleton should expose an appropriate public contract:

- **Thread-safe**: `process` can run concurrently; mutable state is guarded via atomics/locks/immutable design.
- **Serialized**: the host or plugin holds a mutex for the duration of each invocation; only one invocation runs at a time.
- **Stateless**: ideal for singletons, though if there is an internal shared cache/metric, thread safety and cleanup still apply.

For non-thread-safe plugins, a simple host approach is a **per-plugin mutex** inside the lifecycle gate. However, do not hold a global registry lock while calling into the plugin; the wider the lock scope, the higher the risk of deadlocks and latency. If the plugin performs long I/O, a pool of separate instances may be better than serialization.

### 7.2. Per-Call: Better Isolation, Not Immune to Races

Giving each invocation its own instance avoids races on fields across separate instances, **provided instances do not reference shared mutable state**. A per-call plugin can still access static maps, a shared database, host-provided caches, executors, or singleton services. Thus instance scope does not replace transaction protocols and external resource synchronization.

Do not assume per-call is automatically resource-safe. Close in `finally`, bound **concurrent** instances, and apply rejection/backpressure under overload. At thousands of requests per second, instantiating a heavy client per request can cause severe CPU/memory pressure.

### 7.3. Pool: Exclusive Instance per Borrower

Basic pool rules:

```text
onRequest:
    acquire permit (bounded wait + timeout)
    lease = pool.borrow()
    try:
        validate lease
        result = lease.plugin.process(request)
        return result
    finally:
        if lease healthy:
            reset per-request state
            pool.return(lease)
        else:
            pool.discardAndReplaceWithinLimit(lease)
        release permit
```

This is **pseudocode**, not a built-in Java class. The pool must own resources, reset state before handing an instance to another borrower, guard against double-return and lease leaks, and close instances only when nobody is using them. A **non-thread-safe** instance may be lent to only **one** borrower at a time; do not rely solely on `ConcurrentLinkedQueue` to ensure that if the borrow/return workflow is flawed.

If an instance fails mid-request, do not return it to the pool as a healthy object without checking. When the pool shuts down, stop issuing leases, wait for or cancel active leases per deadline, and then close remaining objects.

### 7.4. Per-Tenant: Guaranteeing Data Partitioning

A per-tenant registry may map `TenantId → PluginSession`, while ensuring:

- Tenant ID is authenticated from the host context, not read from a self-declared script/plugin string.
- Per-tenant and global quotas are enforced; never let any tenant spawn unbounded instances.
- If two requests for the **same tenant** access shared mutable state, synchronization is still required.
- If a plugin instance holds tenant-specific secrets/credentials, reset/destroy them at the end of its lifetime and never pass them to another tenant.
- Tenant eviction, idle TTL, and unloading coordinate with in-flight calls so active sessions are not closed mid-request.

## 8. ClassLoader, Static Fields, and Plugin Upgrades

In Java, class identity is tied to binary name and **defining class loader**. A plugin class with a static singleton:

```java
public final class GlobalState {
    private static final java.util.concurrent.atomic.AtomicInteger COUNTER =
            new java.util.concurrent.atomic.AtomicInteger();

    public static int next() {
        return COUNTER.incrementAndGet();
    }
}
```

This is an **illustrative class snippet**, not a contract provided by the JDK. If `GlobalState` is defined by two different plugin class loaders, each class definition has its **own separate static field**. If the class happens to be defined by the parent loader (due to delegation), multiple plugins may inadvertently share the very same static state.

Therefore, do not use static singletons as “global shared state” without knowing class loader ownership. If you want to share counters/caches across plugin generations, place that service in a **host-owned API/service** with a separate lifecycle; do not pass unsynchronized mutable objects directly across the boundary.

### 8.1. Shared Contract Across the Boundary

The host can define `Plugin`, `PluginFactory`, and `PluginContext` in a parent loader. Plugin implementations in child loaders must use **the same type definitions** so the host can cast and invoke them. DTOs, callbacks, and exceptions crossing the API also require a consistent type-identity policy.

Ideal model:

```text
HostClassLoader
    |- api.Plugin
    |- api.PluginFactory
    |- api.Request, api.Response
    |- api.HostServices
             ^
             | parent delegation
    PluginLoader (generation 42)
    |- impl.MyPlugin
    |- private dependency v2
```

A plugin may have **1 instance in generation 42**, but when deploying generation 43, the new plugin loader and new singleton are two separate entities. The host must keep the boundary clean: do not let objects specific to the old generation enter the new registry outside controlled purposes, and do not accidentally close shared host resources.

### 8.2. ServiceLoader Does Not Automatically Specify Instance Cardinality

`ServiceLoader` locates and instantiates providers under the SPI mechanism. It is **not a built-in plugin lifecycle manager** with per-tenant policies, pooling, concurrency, and safe shutdown. Calls to `iterator()`, `stream()`, or `reload()` must be understood in terms of a specific `ServiceLoader`'s caching/discovery behavior; do not assume every lookup creates a new instance or that instances automatically close at the right time.

If the system needs an explicit `Scope`, the common approach is to treat the provider as a **factory/descriptor** and let the host decide when to instantiate the plugin implementation, when to register it, and when to dispose of it. Do not pass shared host state arbitrarily into provider constructors without an API boundary and ownership model.

## 9. Concurrency and Lifecycle Testing

### 9.1. Scenarios That Need Tests

| Scenario | Desired Invariant |
| --- | --- |
| 100 concurrent calls to a thread-safe singleton | Instance count = 1; all results correct; no lost counter increments |
| Non-thread-safe singleton | Host serializes or rejects config; no silent races |
| Per-call with 100 requests | 100 creations (assuming no retries) and proper cleanup; no leaked instances |
| Per-tenant with multiple tenants | State never mixes; per-tenant quotas enforced |
| Pool size 4, 20 requests | At most 4 concurrent leases; exclusive borrowers |
| Stop while in-flight calls exist | Never closes an instance in use; new requests rejected or routed to new generation |
| Repeated stop calls | Idempotent, no double close/double release |
| Initialization fails midway | Already-created resources cleaned up per ownership |
| Generation upgrade under heavy load | No class identity errors; never serves new calls with stopped instances |
| Plugin callback invokes registry/stop | No deadlock from lock ordering or read→write upgrade |
| Request canceled/timed out | In-flight counter and lease reclaimed in `finally` |
| Static caches/ThreadLocal after reload | Old plugin loader not inadvertently retained |

**Do not test only the final result after all threads finish.** Race tests need repeated runs and synchronized starts via `CountDownLatch`/`CyclicBarrier`, controlled stops mid-execution using latches, recording max concurrent calls, and asserting no calls start **after** cutover. Arbitrary `Thread.sleep(...)` durations usually make concurrency tests flaky.

### 9.2. Minimum Metrics

Record metrics labeled with plugin ID, generation, version, and scope (with cardinality control):

- `plugin_instances_live` and `plugin_instances_created_total`.
- `plugin_invocations_in_flight` and `plugin_invocations_completed_total`.
- `plugin_invocations_failed_total`, distinguishing plugin errors from lifecycle errors.
- `plugin_queue_depth`, `plugin_rejected_total`, `plugin_wait_duration`.
- `plugin_start_duration`, `plugin_stop_duration`, and number of generations still retaining references.
- Pool borrow timeouts, unhealthy/evicted instances, circuit-breaker state.

If plugins carry sensitive tenant data, do not automatically attach every tenant ID/request ID to metric labels, which causes unbounded cardinality or information leaks; use tracing/logging with appropriate access policies instead.

### 9.3. Logging Transitions by Generation

When races occur, log the `CREATED → RUNNING → QUIESCING → STOPPED` sequence for a **specific generation**, along with in-flight count, live instance count, and stop reason. Logging only the plugin name without generation makes two parallel deployments easy to mistake for a single instance.

Wall-clock timestamps alone cannot reliably establish event ordering across threads; use request/trace IDs, sequence numbers, or proper correlation when reconstructing flows.

## 10. Common Mistakes

### 10.1. “One Instance” Means No Races?

False. A singleton can receive hundreds of concurrent calls. Having an instance count of 1 does not limit how many threads invoke its methods. If the instance is not thread-safe, you must serialize or change scope.

### 10.2. “One Instance per Request” Means No Shared State?

False. Instances can still share static fields, host-injected caches, the same database rows, shared transactions, or native libraries. List **all shared mutable state**, not just fields inside the plugin class.

### 10.3. “Having an AtomicInteger Means It Is Safe”?

Only for operations on that single value itself. If an invariant requires `processed <= admitted` and the two variables are updated separately, readers can see an inconsistent snapshot. Design atomic state transitions or appropriate locking.

### 10.4. “volatile running” Makes Stop Safe?

False if checking `running` and using the plugin are two separate operations not coordinated with `close`. You need an admission gate, lease/quiescence, or a controlled state machine. `volatile` provides visibility, not an atomic “check-and-enter” operation.

### 10.5. “Synchronized on the Plugin” Solves All Deadlocks?

No. Proper internal synchronization on the plugin does not address registry locks, host callbacks, stop/cancel, unbounded blocking I/O, thread pool starvation, or reentrant close. Lock-graph analysis and bounding lock scope are mandatory.

### 10.6. “Closing the ClassLoader Unloads Immediately”

False. With `URLClassLoader`, `close()` releases resources managed by the loader, yet classes/instances can stay alive if static caches, threads, TCCL, listeners, or host registries retain references. The JVM can reclaim classes/loaders only when GC conditions are satisfied.

### 10.7. “A Dedicated ClassLoader Is a Sandbox”

False. Class loader isolation separates namespaces/versions/lifecycles; it does not stop a plugin from reading files, opening network connections, or using granted runtime privileges. If plugins are untrusted, you need boundaries like separate processes, authorization, quotas, and OS restrictions in addition to concurrency policies.

## 11. Design Checklist Before Accepting a Plugin

1. **Cardinality contract:** does the plugin use `SINGLETON`, `PER_CALL`, `PER_SESSION`, `PER_TENANT`, or `POOLED`? Clearly define “one” per host, generation, and tenant.
2. **Resources:** what is the cost of create/start/close? Who owns connections, executors, files, threads, and caches? How are cleanup failures handled?
3. **Thread safety:** does a single instance support concurrent invocations? Does the host enforce serialization if not?
4. **Shared state:** are immutable config, per-request state, tenant, global, static, and external state cleanly categorized?
5. **Concurrency limits:** what are max in-flight, max live instances, max queue, wait timeouts, and overload rejection behavior?
6. **Lifecycle state machine:** valid transitions, safe publication, quiesce, idempotent stop, and preventing invocation after close?
7. **Synchronization:** right choice of atomics, mutexes, read/write gates, or leases/conditions matching invariants; never using `volatile` to paper over races?
8. **Lock ordering:** avoiding holding broad locks during callbacks, read→write upgrades, and unbounded waits?
9. **Failure/cancellation:** every path cleans up in `finally`; metrics and root causes are never lost?
10. **Tenant isolation:** identity verified by host, no state/secret leakage, and sensible quotas?
11. **Class identity:** shared API/SPI/DTOs in the parent loader, private implementations in appropriate loaders/generations?
12. **Reload/unload:** new generation created, traffic routed properly, old version drained, all unused references/threads/TCCL cleared?
13. **Testing and monitoring:** stress tests, stop-under-load tests, live/created/in-flight instance metrics, generation-scoped tracing?
14. **Security boundary:** never treat scope or class loaders as a restriction mechanism for untrusted code.

**Conclusion:** reliable plugin lifecycle management starts with an **instance cardinality contract** (one or many, and in what scope), **state ownership** (who is allowed to share what), and **synchronization mechanisms** (how threads, admission, and stop are coordinated). The host should retain policy enforcement, measure distinct quantities like live/created/in-flight instances, reject new requests before closing plugins, and separate shared API/SPI contracts from generation-specific implementations. When these three axes are designed together, concurrent execution and plugin upgrades become safe and verifiable.