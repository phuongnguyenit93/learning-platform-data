# Protecting Shared State Without Holding Locks Across the Class-Loading Path

**Java Instrumentation** is often installed at a sensitive location: when the JVM is about to define, redefine, or retransform a class, it invokes `ClassFileTransformer.transform(...)`. That callback can run directly on the **class loading** path, where the class loader, the VM, and multiple other threads are coordinating to define, link, and initialize classes. An agent that wants to count transformations, store filtering configurations, collect telemetry, or cache results needs **thread-safe shared state**; however, if it protects state with a coarse-grained lock and holds that lock while writing logs, accessing the network, or loading helper classes, the agent itself can slow down or deadlock the class-loading path.

The topic of this article is **“Protecting Shared State Without Holding Locks Across the Class-Loading Path”**, in the *Concurrency and Performance* category. The goal is not to claim that every operation is “lock-free”, but to design so that **the callback does not hold agent-created locks for a long time**, while still maintaining correctness for memory visibility, atomic publication, and statistics when multiple classes are loaded concurrently.

Practical approach:

- **Read-mostly, infrequently updated configuration:** publish an *immutable snapshot* via `AtomicReference`.
- **Counters updated by many callbacks:** use `LongAdder` or primitive atomics matching the exact property being measured; do not use `count++` on a shared variable.
- **Lookups by class name:** pre-initialize small, fixed data before registering the transformer; if using `ConcurrentHashMap`, perform only short operations.
- **Complex telemetry:** move it out of the callback with a bounded queue and a backpressure/drop policy; do not perform synchronous I/O under a class-loading lock.
- **Class loader safety:** do not call back into the loader to load the very class being transformed; avoid circular dependencies and do not retain strong `Class<?>`/`ClassLoader` references indefinitely.
- **Verification:** run multiple threads loading classes concurrently, compare counter results after the threads finish, and test updating the policy while callbacks may be running.

A Java agent **compiled with `javac --release 17`** in the hands-on section demonstrates this design pattern using `AtomicReference<Set<String>>`, `ConcurrentHashMap<String,LongAdder>`, and two threads loading target classes concurrently.

## 1. Why is the instrumentation callback a sensitive execution path?

For a Java agent with `premain`:

~~~text
JVM starts up
    |
    v
Agent is loaded, premain(...) is called
    |
    +--> initialize configuration, helpers, counters
    |
    +--> instrumentation.addTransformer(...)
    |
Application / framework / plugin requests class X
    |
    v
Class loader locates class bytes / defineClass
    |
    v
JVM calls transformer.transform(..., className, classfileBuffer)
    |      Related class-loading locks/operations may be active.
    |      The same transformer instance may process multiple classes.
    |
    v
JVM verifies and defines class from final bytes
    |
    v
Application code continues
~~~

The `ClassFileTransformer` specification states that the callback is invoked when a class is **loaded, redefined, or retransformed**, before the final class bytes are verified/applied. The API does not guarantee that the callback will only run on a single fixed thread or that other callbacks will not occur concurrently. Therefore, **you must not assume a transformer instance has exclusive access to its fields**.

Note the scope of the statement about locks: **not every `transform` call on every JVM holds the exact same monitor**. With the default `ClassLoader.loadClass(...)`, the loader synchronizes on the lock from `getClassLoadingLock(name)` during loading; parallel-capable class loaders may use a per-class-name lock, whereas non-parallel-capable loaders typically lock on the loader itself. JVMTI and the redefine/retransform paths have different synchronization mechanisms. The design point is that **the callback can sit on the critical path of class loading**, so any waiting inside it risks cascading impact.

### A small flaw in the callback can amplify

If a callback takes 5 ms because it calls a synchronous logger, classes defined sequentially by a loader can suffer additional latency. If the callback holds a global monitor for 5 ms and multiple threads contend for that monitor, total latency can be even higher. **Not all overhead is linear**: lock contention, JIT warmup, scheduling, and helper class loading make the cost difficult to predict.

Therefore, measuring an agent's performance should examine **p50/p95/p99 callback latency** and **application startup/class-load time**, not just the total number of events collected.

## 2. Three distinct risks: data race, contention, and deadlock

### 2.1. Data races corrupt state

An incorrect example:

~~~java
private static long callbacks;

@Override
public byte[] transform(Module module, ClassLoader loader, String name,
        Class<?> old, java.security.ProtectionDomain domain, byte[] bytes) {
    callbacks++;  // WRONG: non-atomic read-modify-write.
    return null;
}
~~~

This is only an **illustrative code snippet inside a ClassFileTransformer**, not a standalone program. If two threads concurrently execute `callbacks++`, an update can be lost. Marking `callbacks` as `volatile` **only solves visibility of individual reads/writes**, and does not make `++` atomic.

### 2.2. Using one coarse monitor may keep counts accurate but bottlenecks class loading

The following approach can avoid lost updates, but introduces timing risks:

~~~java
private final Object globalLock = new Object();
private final java.util.Map<String, Long> counts = new java.util.HashMap<>();

void recordDangerously(String className) {
    synchronized (globalLock) {
        counts.merge(className, 1L, Long::sum);
        writeToRemoteMonitoringService(className); // WRONG: I/O under lock.
    }
}
~~~

This is a **counterexample snippet**; `writeToRemoteMonitoringService(...)` represents an operation that may be slow or throw errors. Every callback wanting to record statistics may have to wait on the same `globalLock`, even when they are processing different classes.

The `synchronized` keyword itself is not wrong. **Short, narrow-scoped locks** are sometimes the right solution for a structure that needs an atomic operation. The problem is holding a monitor on the **class-loading path while waiting on disk/network, a logger, a future, a user callback, or another class loader**.

### 2.3. Lock inversion: from slowness to deadlock

Consider two locks:

- `L`: a lock related to the loader's class loading (or a JVM operation defining a class).
- `M`: a lock of the telemetry system created by the agent.

A wait cycle can emerge:

~~~text
Thread A: holds L while loading class X
           |
           +-- transform(X) tries to acquire M
                                  ^
                                  |
Thread B: holds M while processing logs
           |
           +-- calls code that needs to load X or another class via L
                                  |
                     both threads wait for each other
~~~

This is a **risk model**, not a guarantee that all JVMs will deadlock with those exact lock names. A logger might load a class for the first time, a serializer might load a provider, or a configuration manager might use a plugin class loader. If the agent is holding monitor M and calls into these components, circular dependencies can become hard to diagnose.

**Safer principle:** avoid adding global locks and blocking calls into the callback; if time-consuming work is needed, move it to the preparation phase or an asynchronous consumer with clear bounds.

## 3. Choosing the right concurrency structure for the purpose

| Requirement | Suitable tool | What to remember |
| --- | --- | --- |
| A toggle flag, read-only in callback | `volatile boolean` or `AtomicBoolean` | `volatile` suffices for a single value; does not automatically protect multiple related fields |
| Update an **entire rule set** and publish consistently | `AtomicReference<ImmutablePolicy>` | Build the complete policy first, swap one reference |
| Total counter, updated by many threads | `LongAdder` | Good throughput under contention; `sum()` is not an atomic snapshot while updates occur |
| Counter used to enforce exact limits | `AtomicLong` with `compareAndSet` or a suitable coordination structure | `LongAdder` is not suitable for issuing sequence numbers/strict limits |
| Metadata/counter lookup by class name | `ConcurrentHashMap<K,V>` | Avoid remapping functions that do I/O, locking, or class loading |
| Telemetry queue | Bounded queue with `offer`/drop policy | Do not use `put` waiting indefinitely in the callback |
| Per-class-loader cache with dynamic lifecycle | Appropriate key/reference design, with cleanup | Strong references can prevent class unloading |
| A multi-step operation that truly needs atomicity | Very short lock or an immutable state object | Do not hold locks across JDK/class-loader/user-code callbacks |

**There is no one-size-fits-all choice.** For example, `LongAdder` is great for metrics but should not be used to generate “unique callback IDs” in global order. `AtomicReference` is great for publishing a new rule set, but does not make everything inside the object immutable if the author still mutates mutable collections after publication.

## 4. AtomicReference: publishing policy as an immutable snapshot

A transformer may need to update an allowlist/denylist at runtime. If the policy is split into multiple separately modified variables:

~~~java
volatile String packagePrefix = "demo/app/";
volatile boolean allowAlpha = true;
volatile boolean allowBeta = true;
~~~

then a callback can observe an **intermediate combination** while an admin thread updates the variables. Each variable may have proper visibility, but **the overall policy is not a transaction**.

Better pattern:

~~~java
record Policy(java.util.Set<String> allowedClassNames, boolean enabled) {
    Policy {
        allowedClassNames = java.util.Set.copyOf(allowedClassNames);
    }
}

private static final java.util.concurrent.atomic.AtomicReference<Policy> POLICY =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Policy(java.util.Set.of("demo/app/Alpha", "demo/app/Beta"), true));

static void replacePolicy(java.util.Set<String> allow, boolean enabled) {
    Policy next = new Policy(allow, enabled); // Prepare completely outside callback.
    POLICY.set(next);                         // Publish once.
}
~~~

This is an **illustrative snippet that needs to be placed in an appropriate class**, not a complete program. Java `record` has been available since Java 16, so the syntax fits Java 17. The defensive constructor uses `Set.copyOf` to prevent the caller from modifying the set contents after publication.

Inside the transformer:

~~~java
Policy p = POLICY.get();  // One consistent snapshot for this callback.
if (!p.enabled() || !p.allowedClassNames().contains(className)) {
    return null;
}
// Continue processing if needed.
~~~

Benefits:

1. Each callback reads **one consistent reference** and uses that policy for the entire invocation.
2. Admin can build a new policy **without locking all callbacks**.
3. `AtomicReference.set/get` provides the necessary memory visibility guarantees to publish the prepared structure.
4. When admin replaces the policy while a callback is running, the callback is allowed to finish on the **old snapshot**. If business logic requires “from time T onward, no callback still uses the old policy”, a more complex quiescence/versioning protocol is needed; `AtomicReference` alone does not create a barrier waiting for old callbacks to finish.

### When using AtomicReference.updateAndGet

A new state can be built from the old state:

~~~java
POLICY.updateAndGet(old -> new Policy(
        java.util.Set.of("demo/app/Alpha"), old.enabled()));
~~~

**Note:** the update function in a CAS loop **may be called multiple times** under contention. It must be **pure, short, and side-effect free**, without sending telemetry events or loading classes itself. For complex configurations, pre-build the snapshot and use `set` or controlled `compareAndSet` outside the callback.

## 5. LongAdder: counting many callbacks without long locks

`LongAdder` is designed for scenarios where many threads increment a counter; as contention increases, it can spread updates across multiple internal cells. This often yields better throughput than a single `AtomicLong` under high contention, at the cost of extra memory and reading the total requiring summing the cells.

Example:

~~~java
private static final java.util.concurrent.atomic.LongAdder CALLBACKS =
        new java.util.concurrent.atomic.LongAdder();

void callbackArrived() {
    CALLBACKS.increment();
}

long snapshotCount() {
    return CALLBACKS.sum();
}
~~~

This is a **self-contained snippet for counter operations**, though it must be placed in a class to run. It does not require an application-created `synchronized(globalLock)`.

### Easily overlooked point: sum() is not transactional

The `LongAdder.sum()` Javadoc explicitly states that the result is **not an atomic snapshot** if other threads are updating concurrently. While updates are in flight, the sum read may omit some concurrent updates. After you **wait for producers to finish** using `Thread.join()` or an appropriate synchronization mechanism, you can accurately read the updates completed in that phase.

Therefore:

- **Right purpose:** `requestsSeen.sum()` for trend statistics or displaying metrics.
- **Wrong purpose:** `if (requestsSeen.sum() < 100) allowRequest()` to guarantee there is never a 101st request under concurrent access.
- **Avoid resetting during active updates:** `sumThenReset()` or `reset()` have semantics/races that must be understood; you can use **epoch-based accumulator swapping** or an appropriate metrics mechanism.

### Per-class-name counters

The Javadoc notes that `ConcurrentHashMap<String, LongAdder>` can be used for a frequency map:

~~~java
counts.computeIfAbsent(className, key -> new LongAdder()).increment();
~~~

This is a valid pattern when counters need to be created for dynamic keys, but on the class-loading path it can still **allocate a new object and run a mapping function**. The `ConcurrentHashMap.computeIfAbsent` Javadoc notes that some map updates may be blocked while computing the value, so the computation function must be **short and simple**, **must not modify the map itself**, and must not call complex code.

If there is only a fixed set of classes, **pre-creating counters before registering the transformer** and only doing `get + increment` in the callback is a more predictable choice:

~~~java
counts.put("demo/app/Alpha", new LongAdder());
counts.put("demo/app/Beta", new LongAdder());
// Register transformer after preparation is complete.

LongAdder counter = counts.get(className);
if (counter != null) counter.increment();
~~~

This is a **snippet**, requiring `counts` to be initialized with the proper type. Not every `ConcurrentHashMap.get`/`LongAdder.increment` is completely wait-free in every implementation, but there is no **agent-created monitor wrapping the entire callback**.

## 6. Pre-initialization: preparing helpers before entering class-loading callbacks

Even if the transformer body only calls `LongAdder.increment()`, the first use of a helper or framework can cause the JVM to load/initialize additional classes during the callback. Ways to reduce this risk:

1. In `premain`, initialize counters, immutable policy, the transformer implementation, and minimal dependencies.
2. If a bytecode library is needed, prepare the required classes/structures before registration, avoiding complex lazy initialization of a logger inside the callback.
3. Only after that, call `Instrumentation.addTransformer(...)`.
4. Have the callback filter class names early, **never load the target class itself**, and never call application code.
5. Move detailed reporting to another phase or a consumer thread.

**There is no guarantee that “warming up” a few helpers will completely eliminate class loading in every runtime branch.** A library may lazy-load a service/provider at another point. A safer design also requires eliminating circular dependencies and keeping callback code minimal.

### Helper packages should be excluded from transformation scope

If you instrument all application classes and the agent's own helpers fall within that scope, the helpers themselves may be instrumented, causing recursion or unexpected class loading. There should be a filter:

~~~java
if (className == null
        || className.startsWith("demo/agent/")
        || !className.startsWith("demo/app/")) {
    return null;
}
~~~

This is an **illustrative snippet inside a transformer**. `className` is the JVM internal name (with `/`), not the binary name with `.`. Early filtering reduces cost before any operations on counters, parsers, or logging.

## 7. Complete JDK 17+ Java agent: two threads loading classes, counters without long locks

The following example implements **an observing Java agent**. It does not modify bytecode; the callback always returns `null`, but it performs three tasks:

- Counts classes whose internal name starts with `demo/app/`.
- For the allowlist in the immutable snapshot, increments the pre-created counter for each allowed class.
- Records classes outside the allowlist using `LongAdder SKIPPED`.

The application creates **two threads**, released together by a `CountDownLatch`, loading `demo.app.Alpha` and `demo.app.Beta`. After both threads `join`, the application updates the policy via `AtomicReference.set` and reads the statistics.

**The design intentionally avoids:** `synchronized` in the callback, logging on every transformation, reloading the target class via the loader inside the callback, creating counters with I/O in a mapping function, and updating a large map while holding a class-loading lock.

### 7.1. Directory layout

~~~text
classloading-concurrency-demo/
├── agent-src/
│   └── demo/agent/LowContentionAgent.java
├── app-src/
│   └── demo/app/
│       ├── Alpha.java
│       ├── Beta.java
│       └── RunDemo.java
└── agent.mf
~~~

The output directories `agent-bin/` and `app-bin/` are created by the compile commands. **Separating agent and application sources** makes it clear that `premain` is the agent entrypoint while `RunDemo.main` is the application entrypoint.

### 7.2. agent-src/demo/agent/LowContentionAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public final class LowContentionAgent {
    private static final String ALPHA = "demo/app/Alpha";
    private static final String BETA = "demo/app/Beta";
    private static final AtomicReference<Set<String>> POLICY =
            new AtomicReference<>(Set.of(ALPHA, BETA));
    private static final ConcurrentHashMap<String, LongAdder> PER_CLASS =
            new ConcurrentHashMap<>();
    private static final LongAdder SEEN_IN_PACKAGE = new LongAdder();
    private static final LongAdder SKIPPED = new LongAdder();

    public static void premain(String options, Instrumentation instrumentation) {
        PER_CLASS.put(ALPHA, new LongAdder());
        PER_CLASS.put(BETA, new LongAdder());
        // Initialize the callback class and its dependencies before registration.
        ClassFileTransformer transformer = new CounterTransformer();
        instrumentation.addTransformer(transformer);
        System.out.println("agentReady=true");
    }

    private static final class CounterTransformer implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer) {
            if (className == null || !className.startsWith("demo/app/")) {
                return null;
            }
            SEEN_IN_PACKAGE.increment();
            Set<String> policyAtEntry = POLICY.get();
            if (!policyAtEntry.contains(className)) {
                SKIPPED.increment();
                return null;
            }
            LongAdder counter = PER_CLASS.get(className);
            if (counter != null) {
                counter.increment();
            }
            return null;
        }
    }

    public static void replacePolicy(Set<String> newPolicy) {
        if (!Set.of(ALPHA, BETA).containsAll(newPolicy)) {
            throw new IllegalArgumentException("Only known classes allowed");
        }
        POLICY.set(Set.copyOf(newPolicy));
    }

    public static void report() {
        System.out.println("seenInPackage=" + SEEN_IN_PACKAGE.sum());
        System.out.println("alphaCallbacks=" + PER_CLASS.get(ALPHA).sum());
        System.out.println("betaCallbacks=" + PER_CLASS.get(BETA).sum());
        System.out.println("skippedCallbacks=" + SKIPPED.sum());
        System.out.println("activeRules=" + POLICY.get().size());
    }
}
~~~

**Explanation of intentional details:**

1. `POLICY` holds `Set.of(ALPHA, BETA)` — a collection that cannot be modified through normal APIs. The callback obtains a **snapshot reference** via `POLICY.get()`; no global lock.
2. `PER_CLASS` already has two entries before `addTransformer`. For allowed classes, the callback only does `get(className)` followed by `LongAdder.increment()`, without running `computeIfAbsent` while defining a class.
3. Both `SEEN_IN_PACKAGE` and `SKIPPED` also use `LongAdder`; there is no shared `long++`.
4. `className == null` is handled before `startsWith`; this also avoids analyzing out-of-scope classes.
5. There is no `System.out.println` inside `transform(...)`. Stdout printing only occurs in `premain` and `report()`, at points decoupled from target class callbacks.
6. `return null` keeps the class bytes unchanged at the transformer step. **The callback count is not the number of classes whose code was modified**.
7. `replacePolicy(...)` accepts a new policy at administrative time, validates allowed names, creates `Set.copyOf`, and publishes it with `POLICY.set(...)`. This **does not force running callbacks to wait on a coarse monitor**.
8. `report()` is only called **after both class-loading threads have `join`ed** in the demo, so the counts are stable. While the app is still loading classes, `LongAdder.sum()` is only suitable for near-real-time statistics, not a transactional snapshot.

Note that using `ConcurrentHashMap<String,LongAdder>` is **reasonable with a controlled number of keys**. If a production agent records counters for every class name regardless of scope, the map can grow unbounded; you must enforce a budget, TTL, or aggregation.

### 7.3. app-src/demo/app/Alpha.java

~~~java
package demo.app;

public final class Alpha {
    public static String message() {
        return "alpha";
    }
}
~~~

### 7.4. app-src/demo/app/Beta.java

~~~java
package demo.app;

public final class Beta {
    public static String message() {
        return "beta";
    }
}
~~~

The two target classes have no direct link to the agent. `RunDemo` requests loading them by **string name**, avoiding having the compiler turn class literal expressions into direct dependencies that could cause classes to be resolved earlier in some situations.

### 7.5. app-src/demo/app/RunDemo.java

~~~java
package demo.app;

import demo.agent.LowContentionAgent;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public final class RunDemo {
    private static final class LoaderTask implements Runnable {
        private final String name;
        private final CountDownLatch start;
        private final AtomicReference<String> answer;
        private final AtomicReference<Throwable> failure;

        LoaderTask(String name, CountDownLatch start,
                AtomicReference<String> answer,
                AtomicReference<Throwable> failure) {
            this.name = name;
            this.start = start;
            this.answer = answer;
            this.failure = failure;
        }

        @Override
        public void run() {
            try {
                start.await();
                Class<?> loaded = Class.forName(
                        name, true, RunDemo.class.getClassLoader());
                answer.set((String) loaded.getMethod("message").invoke(null));
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<String> a = new AtomicReference<>();
        AtomicReference<String> b = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread first = new Thread(new LoaderTask(
                "demo.app.Alpha", start, a, failure), "loader-alpha");
        Thread second = new Thread(new LoaderTask(
                "demo.app.Beta", start, b, failure), "loader-beta");
        first.start();
        second.start();
        start.countDown();
        first.join();
        second.join();
        if (failure.get() != null) {
            throw new AssertionError("Concurrent loading failed", failure.get());
        }

        System.out.println("alpha=" + a.get());
        System.out.println("beta=" + b.get());
        LowContentionAgent.replacePolicy(Set.of("demo/app/Alpha"));
        LowContentionAgent.report();
    }
}
~~~

This is a **test driver**, so calling `Class.forName(name, true, ...)` in an **application thread** is a controlled original class-loading request. It is **not** `ClassFileTransformer` calling the loader to reload the very target being transformed. The two `Thread`s share a latch to start roughly concurrently, though it **does not guarantee callbacks actually overlap on every JVM**; it creates concurrent class-loading pressure and checks thread-safe behavior in a test environment.

`AtomicReference<Throwable> failure` allows each task to report errors back to the main thread instead of merely printing an uncaught exception in a child thread and letting the main program still exit with code 0. `join` provides the appropriate happens-before relationship for main to read task results and counters updated by the corresponding callbacks before they finish.

Naming the nested class `LoaderTask` (instead of a lambda in the demo) makes the list of application classes easier to follow: the `demo.app` package will have callbacks for `RunDemo`, `RunDemo$LoaderTask`, `Alpha`, and `Beta`.

### 7.6. agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LowContentionAgent
~~~

Ensure **a trailing blank line in the manifest**. The demo only observes classes at load time and uses `addTransformer(transformer)`; no retransform/redefine manifest capability is needed. If `retransformClasses(...)` is used in another article, that is a separate capability.

### 7.7. Compiling and running with JDK 17+

From the root directory `classloading-concurrency-demo/`, run in **Bash**:

~~~bash
mkdir -p agent-bin app-bin
javac --release 17 -d agent-bin agent-src/demo/agent/LowContentionAgent.java
javac --release 17 -cp agent-bin -d app-bin \
  app-src/demo/app/Alpha.java \
  app-src/demo/app/Beta.java \
  app-src/demo/app/RunDemo.java
jar --create --file agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:agent.jar -cp app-bin demo.app.RunDemo
~~~

In **Windows PowerShell**, use commands that do not rely on Bash-style line continuation:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/LowContentionAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/demo/app/Alpha.java app-src/demo/app/Beta.java app-src/demo/app/RunDemo.java
jar --create --file agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:agent.jar -cp app-bin demo.app.RunDemo
~~~

`jar -C agent-bin .` also packages the nested class `LowContentionAgent$CounterTransformer.class`; if you only package `LowContentionAgent.class` and forget the nested class, the agent will lack the transformer implementation.

### 7.8. Exact verified stdout

The code was **compiled with `javac --release 17` and run on Zulu OpenJDK 24**. Result:

~~~text
agentReady=true
alpha=alpha
beta=beta
seenInPackage=4
alphaCallbacks=1
betaCallbacks=1
skippedCallbacks=2
activeRules=1
~~~

Causal explanation rather than just looking at the numbers:

| Line | What was verified |
| --- | --- |
| `agentReady=true` | Transformer was prepared/registered before the driver ran |
| `alpha=alpha` and `beta=beta` | Both application classes were loaded, initialized, and had their methods invoked successfully from two threads |
| `seenInPackage=4` | Four classes with internal names starting with `demo/app/` received callbacks in the scenario: driver, nested task, Alpha, Beta |
| `alphaCallbacks=1` | Callback for `demo/app/Alpha` was allowed and incremented the counter accurately |
| `betaCallbacks=1` | Callback for `demo/app/Beta` was allowed and incremented the counter accurately |
| `skippedCallbacks=2` | `RunDemo` and `RunDemo$LoaderTask` were outside the allowlist yet still within the counted package |
| `activeRules=1` | After loading both classes, the policy was replaced with a new snapshot allowing only Alpha |

**Do not generalize `seenInPackage=4` into a rule across all JVMs/apps.** That is the result of the demo configuration on the verified environment. If classes are loaded by multiple loaders, retransformation occurs, another Java agent is active, or the driver is changed, the callback count may differ. More reliable invariants are that **counting does not lose updates due to data races in the metrics structure itself** and that the policy rule is applied correctly on each invocation.

**Do not claim this program is a bytecode-modifying transformer:** it always returns `null`. This is a program demonstrating concurrency safety of callbacks and counters, not an agent injecting tracing instructions.

## 8. Why not print logs directly inside transform?

A seemingly harmless statement:

~~~java
System.out.println("Transforming " + className);
~~~

can force the callback to format strings, acquire the stream's lock, perform slow console writes, and trigger helper initialization. In small examples, logging is sometimes handy; in production with many class-loading threads, it can create a bottleneck on the console lock.

Recommended data pipeline:

~~~text
transform callback:
    very fast filter
    + counter.increment()
    + if needed, offer(event) into bounded queue
    + return null/byte[] immediately
                  |
                  v
telemetry worker:
    poll/consume queue
    format log / JSON
    write to stdout, disk, metrics, or network
~~~

A snippet illustrating a bounded queue:

~~~java
private static final java.util.concurrent.ArrayBlockingQueue<String> EVENTS =
        new java.util.concurrent.ArrayBlockingQueue<>(1024);
private static final java.util.concurrent.atomic.LongAdder DROPPED =
        new java.util.concurrent.atomic.LongAdder();

static void emitWithoutWaitingForCapacity(String event) {
    if (!EVENTS.offer(event)) {
        DROPPED.increment();
    }
}
~~~

This is a **snippet**, requiring placement in a class and a consumer reading the queue on another thread. `offer` returns immediately when the queue is full **instead of waiting for space** like `put`, though `ArrayBlockingQueue` still uses a **short internal lock** and can experience lock contention. It is **not a wait-free queue**. Building the `event` string also allocates; if latency is very sensitive, consider a lower-allocation structure.

If telemetry cannot lose events, you must choose a different trade-off (persist/buffer/backpressure) and accept that **you cannot simultaneously guarantee zero event loss and completely non-blocking behavior** when the consumer is persistently slow and memory is bounded. For observability during class loading, a **counted drop + alert** policy is usually less risky than blocking the class-loading path to keep every log.

## 9. Do not use computeIfAbsent for heavy work

`ConcurrentHashMap.computeIfAbsent` provides atomic mapping updates for a key. However, the Javadoc emphasizes that the mapping function must be **short and simple** because some other update operations may wait while the mapping is computed.

Example of **what not to do**:

~~~java
counters.computeIfAbsent(className, key -> {
    loadFullConfigurationOverNetwork(); // WRONG: I/O, may block.
    buildLargeBytecodeCache();          // WRONG: heavy work inside map operation.
    return new LongAdder();
});
~~~

This is a **counterexample snippet**; `loadFullConfigurationOverNetwork` and `buildLargeBytecodeCache` represent slow operations, not built-in Java APIs.

If keys are known in advance, initialize them in `premain` as in the demo. If keys are dynamic and volume is bounded, the pattern `computeIfAbsent(key, k -> new LongAdder())` can be acceptable; you still need to account for allocation cost, bound the number of keys, and ensure the lambda does not invoke a class loader or modify the map itself.

### An often-forgotten race: using two separate maps

Suppose one thread updates `allowedClasses` and another thread updates `counters` in two steps without a joint publication. A callback may see the **new allowlist without the corresponding counter yet**. In the demo, the valid key set is fixed and counters are pre-created, so `PER_CLASS.get(className)` always finds a counter for any name in a valid allowlist.

For dynamic policies with unbounded names, one option is to bundle the **policy and counters map** in a single immutable holder/reference published together, or allocate counters first before publishing the policy and manage counter eviction so active callbacks do not lose data. Do not assume `AtomicReference<Set<String>>` alone solves all coordination problems across multiple structures.

## 10. Very short locks are sometimes better than a complex lock-free model

The requirement is not “ban all synchronized”, but **do not hold locks across the class-loading path**.

Example of updating a complex configuration snapshot from an administrative thread:

~~~java
synchronized (configUpdateLock) {
    // Only assign a new state reference and swap it.
    currentConfig = preparedImmutableConfig;
}
~~~

This is an **illustrative snippet**, requiring properly typed variables and ensuring visibility of `currentConfig` if callbacks read it outside the lock (for example `volatile` or `AtomicReference`). Preparing `preparedImmutableConfig` should be done **outside synchronized**. More importantly, the callback **must not have to acquire that same lock** just to read the policy on every class load.

If a lock must be used in the callback to protect a cache that cannot be replaced with a concurrent structure:

1. Keep the locked region strictly around a **small O(1) operation**, with no I/O.
2. Do not call custom/plugin code under the lock.
3. Do not load or initialize classes under an agent-created lock.
4. Establish lock ordering across all paths to avoid lock inversion with class loaders.
5. Measure callback latency and wait time, and set up alerts.
6. Have a fallback to skip optional metrics if the lock cannot be acquired within budget; do not make telemetry a survival dependency of class loading.

## 11. ThreadLocal reentrancy guard: useful but insufficient

A transformer can accidentally trigger nested callbacks when its own helpers or parser library need a new class. A per-thread guard sometimes helps detect/limit reentrancy:

~~~java
private static final ThreadLocal<Boolean> ACTIVE =
        ThreadLocal.withInitial(() -> false);

static byte[] guardedTransform(String name, byte[] input) {
    if (Boolean.TRUE.equals(ACTIVE.get())) {
        return null;  // Skip nested event on the same thread.
    }
    ACTIVE.set(true);
    try {
        return transformBytes(name, input);
    } finally {
        ACTIVE.remove();
    }
}
~~~

This is an **illustrative snippet**, requiring `transformBytes(...)` to be defined and placed in an appropriate class. When a nested transform invocation occurs on the same thread, it returns `null`. You must explicitly decide that skipping nested classes is acceptable for your instrumentation policy.

However, the guard **does not solve**:

- Deadlocks between two threads and two class loaders.
- Shared-state races caused by callbacks on different threads.
- Nested callbacks occurring on another thread.
- Helpers already loaded/initialized improperly due to side effects before the guard ran.
- Leaks if `ThreadLocal` holds long-lived references and `remove()` is not called.

**Do not treat the guard as an excuse to call `loader.loadClass(target)` inside the transformer.** Eliminating circular dependencies by design is a higher priority.

## 12. Per-ClassLoader caches: contention and memory leaks

When multiple plugin loaders each define `com.example.Service`, a key consisting only of the string name is **not enough** to distinguish class identity. A key combining loader identity and class name/module may be needed. However, if the agent holds:

~~~java
Map<ClassLoader, Map<String, Metadata>> perLoaderCache = new HashMap<>();
~~~

in a singleton that lives for the lifetime of the JVM, **strong references** to loaders can prevent them from being garbage-collected and prevent class unloading after a plugin is uninstalled.

Solutions depending on requirements:

- Cache only **value-like metadata** that does not hold references to loaded `Class`/loader objects when unnecessary.
- Bound key count, size, and lifetime; perform cleanup.
- When weak keys are needed, consider a properly synchronized `WeakHashMap` or a caching library with weak-key semantics, and ensure **values do not hold a strong back-reference to the key**.
- For dynamic keys, consider using a stable ID in a registry with an explicit lifecycle; **`identityHashCode`** should only be diagnostic information, not a guaranteed unique global ID.
- Do not scan the entire cache or perform heavy cleanup inside the callback; run it on an admin/consumer thread.

`ConcurrentHashMap<ClassLoader,...>` guarantees thread-safe operations, but **does not automatically turn keys into weak references**. Reducing contention while causing a memory leak still results in an operationally unsafe agent.

## 13. Coordinating with Retransformation/Redefinition

The demo measures **load-time** callbacks, but the same shared-state principles apply when calling `retransformClasses(...)` or `redefineClasses(...)`.

Some differences:

| Operation | Impact on callbacks/counters |
| --- | --- |
| Initial load | Previously registered transformers are called; `classBeingRedefined` is typically `null` |
| Redefine | Transformers are called per group rules; `classBeingRedefined` is the existing class |
| Retransform | Only transformers with `canRetransform=true` are called again; results from non-capable groups are reapplied |
| Multiple classes in a batch | Callbacks for multiple classes may traverse multiple threads/internal paths; do not rely on global logs to infer strict order between classes |
| A class redefined multiple times | Callback counter may be >1 for the same internal name; that is not necessarily a data race |

**Do not use “counted exactly once per class” as a JVM-wide invariant.** The demo counts once for Alpha/Beta because each class is defined once in the scenario; an application with multiple loaders, agents, and retransforms can produce multiple callbacks for the same name.

If you want to measure “how many unique loaded classes”, you must properly define identity (`Class<?>` once loaded, loader + binary name as appropriate for context) and lifecycle/retention. If you want to measure “how many times the transformer was invoked”, increment the counter on **each invocation** and allow >1 for a class.

## 14. Protecting business results and preventing telemetry errors from breaking class loading

The `ClassFileTransformer` contract allows a callback to return `null` if no changes are made; an exception thrown by a transformer does not mean the JVM automatically stops all remaining transformers. However, **you should not use throwing exceptions as a normal way to skip instrumentation**: it still incurs overhead, loses observability, and masks programming bugs.

Fail-open design for **optional telemetry**:

- Counters/queues may drop event recording when overloaded.
- Do not let serializer/network errors break the callback.
- Do not mutate the `classfileBuffer` array passed in by the JVM.
- Do not alter class bytes merely because telemetry failed.
- If bytecode transformation is mandatory functionality, distinguish errors that make bytes unsafe from errors in recording metrics. Do not continue emitting malformed bytes to “salvage” a transformation.
- For extreme errors like `OutOfMemoryError`, JVM crashes, or exhausted system resources, do not promise every hook can recover; the best strategy remains **minimizing allocations and dependencies** before reaching that state.

Separate:

~~~text
mandatory bytecode correctness     optional telemetry
           |                            |
           v                            v
parse -> transform -> verify       metric.increment() / queue.offer()
           |                            |
           v                            +-- error/drop: record within safe bounds
      return byte[]/null                |
                                        v
                             do not alter business result
~~~

A slow callback, deadlock, or class-loading error caused by the agent can prevent the application from starting even when the class bytes are valid. Therefore, **bytecode correctness** and **callback operational safety** must be tested separately.

## 15. What should benchmarks and stress tests measure?

When comparing “before agent” and “after agent”, separate the measurements:

| Metric | Question |
| --- | --- |
| Callback count by class group | Is the agent accidentally entering too many classes? |
| Callback latency p50/p95/p99 | Does the callback have many outliers when multiple threads load? |
| Class-loading latency | Does class definition time increase significantly? |
| Startup latency | Does the application start more slowly with the agent enabled? |
| Lock contention/wait | Is any callback waiting on an agent or logger monitor? |
| Deadlocked threads | Is there a wait cycle between agent locks and class-loader locks? |
| Allocation per callback | Are large events/stack traces/strings allocated on the hot path? |
| Queue depth/dropped events | Is the consumer keeping up with the event rate? |
| Loader/cache retention | Can plugin loaders unload after a plugin is removed? |
| Correctness count | Does the total after `join` match the number of triggered callbacks? |
| Policy updates | Do callbacks see valid snapshots rather than a half-edited set? |

### Systematic concurrency test

1. Start the JVM with the agent and a small set of classes with clear expected outcomes.
2. Create multiple threads using a latch/barrier to start roughly concurrently.
3. Have each thread load or request definition of **distinct classes** (not just repeatedly calling `loadClass` on an already-loaded class).
4. Compare counters **after the threads finish**.
5. Replace the policy multiple times via immutable snapshots and verify each callback uses **a valid policy**.
6. Intentionally make the telemetry consumer slow or fill the queue; confirm the callback does not wait indefinitely.
7. Use custom non-parallel-capable/parallel-capable loaders in dedicated tests when dealing with complex loader models.
8. Inspect thread dumps and JFR events if stalls/lock contention appear.
9. Test repeated load/unload lifecycles of plugin loaders; check memory retention.
10. Verify class bytes/method behavior if the agent performs real transformations, not just counting callbacks.

**A fast run on one machine does not prove deadlock is impossible.** Deadlocks often depend on rare interleavings, lazy initialization, or library versions. Stress testing should combine static review of lock order with runtime measurement.

## 16. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `count++` on a plain global variable | Lost updates under concurrency | `LongAdder` for metrics; `AtomicLong` for exact counters |
| Only adding `volatile` to `count++` | Still non-atomic | Use atomic updates |
| `synchronized(globalLock)` wrapping network/logging | Long callback waits, lock inversion risk | Move I/O out of locks/callbacks |
| Lazy loading helpers/parsers/loggers in callback | Nested class loading, reentrancy | Prepare helpers before registration, filter early |
| Calling `loader.loadClass(className)` for the target itself | Circular dependency or wrong runtime identity | Use `className` and `classfileBuffer` |
| Unsynchronized shared mutable `HashMap` | Races, inconsistent state reads | `ConcurrentHashMap` or immutable snapshot |
| Updating two policy variables independently | Callback can see half-old/half-new config | One immutable Policy via `AtomicReference` |
| Mutating a Set after publishing it | Callback sees mutable/racy data | `Set.copyOf` and appropriate deep immutability |
| Doing I/O inside `computeIfAbsent` | Some map updates may be blocked | Keep lambda tiny, preseed keys when possible |
| Using `LongAdder.sum()` to enforce hard quotas | No atomic snapshot | CAS/AtomicLong or an atomic allocator |
| Using an unbounded queue | Unbounded memory growth when consumer is slow | Bounded queue, explicit drop/sampling/backpressure |
| Using `BlockingQueue.put` in callback | May wait indefinitely if queue is full | `offer` and handle drops, understand internal locks |
| Adding a ThreadLocal guard while still loading target | Guard does not cure multi-thread deadlocks | Remove class-loading dependency; guard is an extra layer |
| Caching `ClassLoader` with strong keys forever | Class unloading is blocked | Weak keys/lifecycle + cleanup |
| Logging every class to stdout inside callback | Console lock, I/O, and startup lag | Counters/queue, emit logs outside callback |
| Treating callback count as unique class count | Wrong under redefine/retransform/multi-loader | Define metrics and identity clearly |
| Believing `return null` means “do nothing JVM-wide” | Other transformers may still modify bytes | Understand the transformer chain and capabilities |
| Not testing helper visibility | `NoClassDefFoundError` when new code calls helper | Place helpers/modules properly for the environment |
| Locking the entire bytecode build/verify process | Greater contention than necessary | Separate immutable inputs and caches, narrow lock scope |

## 17. Code review checklist for multi-threaded transformers

- [ ] Callback filters `className`/scope early and is null-safe.
- [ ] No agent-created monitor is held while calling loggers, I/O, class loaders, plugin code, or custom callbacks.
- [ ] `Class.forName(target)`/`loader.loadClass(target)` is not called while target is being defined.
- [ ] Shared counters do not use unsynchronized `++`.
- [ ] Policy updates use safely published immutable snapshots; callback reads one snapshot.
- [ ] Fixed keys/counters/helpers are prepared before registering the transformer when appropriate.
- [ ] Map mutations/remapping functions contain no I/O or heavy work.
- [ ] Strong `Class<?>`/loader references are not held longer than necessary.
- [ ] Optional telemetry is bounded; has a strategy when full/failing, and does not block class loading indefinitely.
- [ ] `classfileBuffer` is not mutated in place.
- [ ] Metrics distinguish callbacks, class identity, and modified class bytes.
- [ ] Concurrency, reentrancy, loader isolation, startup time, and failure modes are tested.

## 18. Self-check exercises

**Question 1.** Two threads concurrently execute `callbacks++` on a static `long`. Does adding `volatile` guarantee no lost updates?

**Question 2.** Why is `LongAdder` often suitable for counting callbacks under contention, yet unsuitable as an exact quota allocator for “only 100 requests may be accepted”?

**Question 3.** An agent updates `allowedPackages` and `excludedPackages` in two separate mutable collections without synchronization. What state might a callback observe?

**Question 4.** `AtomicReference<Policy>` receives a `Policy` object containing a `HashSet`. An admin thread continues adding elements to that same `HashSet` after publication. Is this still safe?

**Question 5.** Is `computeIfAbsent(name, key -> slowRemoteCall())` inside `ClassFileTransformer.transform` dangerous, even though the map is a `ConcurrentHashMap`?

**Question 6.** Does `ArrayBlockingQueue.offer(event)` block indefinitely when the queue is full like `put(event)`? Can it be claimed to be completely lock-free?

**Question 7.** A transformer uses `ThreadLocal<Boolean>` to skip nested callbacks on the same thread. Does that eliminate deadlocks between two threads holding different loader locks?

**Question 8.** A program reads `LongAdder.sum()` while callbacks are still incrementing the counter. Can that be treated as an exact atomic snapshot at a point in time?

**Question 9.** Two classes have the same binary name but are defined by two different class loaders. What problems can a cache keyed solely by name cause?

**Question 10.** After unloading a plugin loader, the agent still keeps it in `ConcurrentHashMap<ClassLoader,...>`. What consequence can occur?

**Question 11.** In the demo, `seenInPackage=4` and `skippedCallbacks=2`. Which two classes were skipped? Why do Alpha and Beta each have a count of 1?

**Question 12.** Does calling `Class.forName("demo.app.Alpha", ...)` in `RunDemo.LoaderTask` violate the rule against loading the target inside the transform callback?

**Question 13.** If a transformer only returns `null`, does invoking it prove the class file was modified?

**Question 14.** If the app updates the policy via `AtomicReference.set(newPolicy)` while a callback has already read the old snapshot, must that callback switch to the new snapshot mid-invocation?

**Question 15.** Why is it necessary to measure startup latency, lock wait, and class-loader leaks in addition to checking that counters are accurate?

### Answers

1. **No.** `volatile` guarantees visibility under the Java Memory Model, but `++` is not an atomic operation.
2. `LongAdder` optimizes distributed updates and summary statistics, while `sum()` is not an atomic snapshot under concurrent updates; hard quotas need a dedicated atomic mechanism.
3. A **half-old/half-new** combination, causing inconsistent filtering scope within a single observation.
4. **No.** Safely publishing a reference does not make a mutable `HashSet` immutable; defensive measures like `Set.copyOf` are needed and published objects must not be mutated.
5. **Yes.** The mapping function can cause some map updates to wait, adding I/O/class loading onto the active class-loading path.
6. `offer` does not wait for space like `put`, but `ArrayBlockingQueue` uses an internal lock; it cannot be called wait-free.
7. **No.** A per-thread guard cannot resolve lock cycles across threads or class loaders.
8. **No.** The Javadoc states `sum()` is not an atomic snapshot when updates are occurring.
9. Mixing up metadata/counters or instrumenting the wrong runtime identity; loader identity/module context is needed.
10. Strong references can prevent class unloading, causing a memory leak when plugins are loaded and unloaded repeatedly.
11. `RunDemo` and `RunDemo$LoaderTask` were skipped because they are not in the allowlist; Alpha/Beta were each defined once in the scenario.
12. **No.** That is a load request from an application thread, not the transformer itself reloading the class being defined.
13. **No.** `return null` means that transformer did not supply replacement bytes.
14. **No.** The callback is entitled to complete based on the valid snapshot read upon entry; the new update applies to subsequent reads.
15. Because a callback can be data-accurate while still **slowing down or deadlocking class loading** or holding references that prevent loaders from unloading.

## 19. Conclusion

**Do not choose between “thread-safe” and “fast” by sacrificing one for the other.** Choose the right state model:

- **Immutable policies** published via `AtomicReference` let callbacks read configuration without acquiring administrative locks.
- **Counters** use `LongAdder` or atomic primitives instead of unsafe shared counter variables.
- **Keyed class metadata/counters** use concurrent structures with short operations, preseeded when appropriate.
- **I/O, logging, and expensive operations** stay outside locked regions and class-loading callbacks; telemetry has an explicit budget.
- **Class loaders/helpers** must not create circular dependencies or be retained indefinitely.
- **Stress testing** and observing latency/lock contention are necessary to prove a design is truly production-ready.

A correct transformer must **preserve both class bytes and class-loading progress**, not merely “avoid data races”. When state is protected with minimal synchronization scope and heavy work is moved off the critical path, the agent is much safer when the JVM loads many classes concurrently.

## 20. Official technical documentation

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): load/redefine/retransform callbacks, `classfileBuffer` input, returning `null`, and the rule against mutating the original array.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration, capabilities, and redefine/retransform coordination.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getClassLoadingLock`, parallel-capable loaders, and deadlock warnings for non-tree delegation.
- [Java SE 21 — LongAdder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): distributed counters, `sum()` not being an atomic snapshot, and frequency map example.
- [Java SE 21 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent map and the `computeIfAbsent` contract requiring short, simple computation functions.
- [Java SE 21 — AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): snapshot publication, `get`, `set`, compare-and-set, and update functions.
- [Java SE 21 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue and the distinction between `offer` and `put`.
- [Java Language Specification 21 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): happens-before, synchronization, memory visibility, and data races.
