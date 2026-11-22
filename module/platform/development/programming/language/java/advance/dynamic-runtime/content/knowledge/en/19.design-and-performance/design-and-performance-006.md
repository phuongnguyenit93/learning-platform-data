# 19.6 Safe Cache Publication and Controlling Target Updates Under Concurrency

## 1. Goals and Real-World Problems

In Java **dynamic-runtime** systems, a lookup or dynamic linking step can carry significant cost: finding a `Method`/`MethodHandle`, checking signatures, creating adapters, parsing schemas, linking call sites, building dispatch trees, or creating a new implementation. To reduce cost, applications often **cache** the result and share it across multiple threads.

Two distinct requirements must be satisfied simultaneously:

1. **Safe cache publication:** after one thread finishes creating an object, other threads must observe its **fully initialized** state, with the right key/version, and must not read data from a cache structure accessed concurrently in violation of its rules.
2. **Controlling target updates:** when logic needs to be replaced at runtime, in-flight invocations and threads reading the target must have clear **update visibility rules**. Calling `setTarget` does not have the same memory semantics across all `CallSite` types.

If you only focus on optimizing the call path without designing for the Java Memory Model (JMM), you can encounter cache races, visibility bugs, lost updates, inconsistent coordination across multiple fields, or dispatching to an old target version. Such bugs are often **hard to reproduce**: single-threaded runs always succeed, and stress tests may sometimes pass, yet that does not mean the program has a valid happens-before relationship.

In this lesson, we focus on:

- `happens-before`, `volatile`, `final`, `synchronized`, and atomic references;
- `ConcurrentHashMap.computeIfAbsent` for caching `MethodHandle`/adapters;
- immutable snapshots and versioned cache keys;
- the differences among **`ConstantCallSite`, `MutableCallSite`, and `VolatileCallSite`**;
- `MutableCallSite.syncAll`, `SwitchPoint.invalidateAll`, `AtomicReference<MethodHandle>`, and visibility scope;
- swapping targets during concurrent invocations, limitations regarding already-started invocations, and controlling multiple writers;
- a **complete Java 17+ example**, compiled and run, along with a testing and debugging checklist.

> **Core Principle:** A proper cache requires **safe publication** of both *the reference and the state that the reference points to*. A dynamic target requires its **own publication mechanism**, suited to the update frequency and visibility requirements. Do not treat `ConcurrentHashMap`, `volatile`, or `MutableCallSite.setTarget` as magic that turns an entire multi-step workflow into an atomic transaction.

## 2. Two Layers of Responsibility: Cache Reference and Target Binding

Suppose a dynamic framework receives a `calculate(5)` request and needs to invoke a `MethodHandle`. One design might look like this:

```text
request thread(s)
        |
        v
  read config/policy snapshot
        |
        v
 ConcurrentHashMap<Key, MethodHandle>
        | hit                    | miss
        |                        v
        |                build MethodHandle
        |                        |
        +-----------<------------+
        |
        v
 MethodHandle.invokeExact(...)
        |
        v
 business result
```

In another model, the cache holds **a stable dynamic invoker**, while the underlying target can change:

```text
request thread(s)
        |
        v
 stable MethodHandle = callSite.dynamicInvoker()
        |
        v
  CallSite target (changes at runtime)
        |
        +--> version A target
        |
        +--> version B target after valid publication
```

Those are two separate concerns:

- **Cache publication:** retrieving or publishing a `MethodHandle` / a fully constructed state object. `ConcurrentHashMap` or `AtomicReference` can handle this publication.
- **Call-site target visibility:** updating the **target field** inside the `CallSite`. `MutableCallSite` and `VolatileCallSite` have different memory contracts. A `ConcurrentHashMap` holding a reference to a call site **does not automatically make the target inside volatile**.

**Example of flawed reasoning:** “I put the `MutableCallSite` into a `ConcurrentHashMap`, so `site.setTarget(newTarget)` is definitely visible immediately to every thread.” Incorrect. The map publishes the **reference to the site**, while subsequent changes to `MutableCallSite.target` still follow the site's own memory semantics.

## 3. Java Memory Model: Visibility, Atomicity, Ordering

### 3.1. `happens-before` Is the Required Contract

The JMM defines a **happens-before** relationship to explain when effects from a writing thread are guaranteed to be visible to a reading thread under appropriate synchronization rules.

Commonly used mechanisms:

| Mechanism | Notable Relationship | When to Use |
| --- | --- | --- |
| Writing/reading the same `volatile` variable | A volatile write has a synchronization relationship with subsequent volatile reads under the JMM | Publishing a snapshot reference or status flag |
| `synchronized` on the same monitor | An unlock synchronizes-with a subsequent lock on that monitor | Protecting a multi-step sequence of operations |
| `AtomicReference.get/set/CAS` | Has defined volatile/atomic memory effects | Swapping a snapshot or target reference |
| `ConcurrentHashMap` | Per the API, updating a key happens-before a non-null retrieval reporting that mapping | Publishing cached objects by key |
| `Thread.start()`, `Thread.join()`, `CountDownLatch`, `Future.get()` | Establishes specific ordering/happens-before | Coordinating test/worker execution |
| Properly initialized `final` fields | Has initialization-safety guarantee for final values under the JMM | Designing immutable objects, though it does not replace map/cache synchronization |

**Visibility** does not mean **atomicity of an entire transaction**. A single read of a `volatile` reference is atomic, but two separate `volatile` fields **do not** turn a pair of values into an atomic snapshot.

### 3.2. Risk Example: Publishing an Incomplete Object

This is a **counterexample**, not to be run to demonstrate correctness:

```java
// COUNTEREXAMPLE: no safe happens-before for publication.
class BadRegistry {
    static java.util.Map<String, Entry> cache = new java.util.HashMap<>();

    static Entry get(String key) {
        Entry value = cache.get(key);
        if (value == null) {
            value = new Entry();
            cache.put(key, value); // There may be other concurrent writers/readers.
        }
        return value;
    }

    static class Entry {
        int factor = 3;
        int offset = 2;
    }
}
```

The issue is not just two threads creating `Entry` at the same time. `HashMap` **does not allow unsynchronized concurrent mutation**; at the same time, publication of the state fields is not designed with happens-before. Duplicate construction, inconsistent map structure reads, and behaviors unsupported by the contract can occur.

You should not use a stress test that “passed 1000 times” to justify a data race.

### 3.3. A `volatile` Reference Does Not Lock Internal State

Example:

```java
// STILL RISKY if multiple threads modify the map after publication.
volatile java.util.Map<String, String> cache = new java.util.HashMap<>();

void update(String key, String value) {
    cache.put(key, value); // Mutation in HashMap is still not thread-safe.
}
```

`volatile` guarantees read/write rules **for the reference variable**, not turning every method of the referenced object into a thread-safe one. If you want a copy-on-write snapshot, you must **create a new map**, populate it completely, and then publish the reference to a map that is no longer mutated.

### 3.4. Immutable Snapshots for Multiple Related Fields

Two independent fields:

```java
// COUNTEREXAMPLE if multiplier and offset must always go as a pair.
volatile int multiplier;
volatile int offset;
```

A reader can observe the multiplier of the new config and the offset of the old config if the writer updates them separately. A safer approach:

```java
record Config(int version, int multiplier, int offset) {}

private static final java.util.concurrent.atomic.AtomicReference<Config>
        CURRENT = new java.util.concurrent.atomic.AtomicReference<>(
                new Config(1, 2, 1));

// Writer creates the complete object BEFORE publishing.
CURRENT.set(new Config(2, 3, 2));

// Reader holds a consistent snapshot.
Config snapshot = CURRENT.get();
int m = snapshot.multiplier();
int b = snapshot.offset();
```

This is a **snippet** for illustration, not a standalone program. `Config` is an immutable record; `AtomicReference.set` publishes a complete reference. The reader reads **once** and extracts all fields from that same object.

Note: `CURRENT.set` does not resolve all conflicts between **multiple writers** if each writer needs to update based on the old state. For read-modify-write, you need `compareAndSet` or `updateAndGet` with a function **free of side effects**.

## 4. Safe Cache Publication with `ConcurrentHashMap`

### 4.1. `computeIfAbsent` for Per-Key Caching

A familiar pattern when caching `MethodHandle`:

```java
// Snippet, assuming Key and buildHandle are already defined.
private final java.util.concurrent.ConcurrentHashMap<Key, MethodHandle>
        cache = new java.util.concurrent.ConcurrentHashMap<>();

MethodHandle getHandle(Key key) {
    return cache.computeIfAbsent(key, this::buildHandle);
}
```

Properties to understand:

1. `ConcurrentHashMap` supports concurrent reads/updates and **publishes mappings with memory-consistency semantics**.
2. With `computeIfAbsent`, creating the mapping for an absent key is performed atomically per the API contract; related competing updates may be blocked during computation.
3. If the mapping function returns **`null`**, the map **does not** record a mapping. If the function throws an exception, no mapping is established by that attempt; a subsequent access may **recompute**.
4. If a key already has a valid value, readers get a cache hit; the mapping function is not run just to return an existing mapping.
5. The mapping function should not **recursively update the same map**, or perform long I/O, or depend on cross-locks that force other threads to wait.

**Do not claim “the mapping function runs exactly once forever.”** A key can be removed/replaced; computation can return null or throw an error; lifecycle and cache eviction allow recomputation in the future. In the experiment below, we do not remove keys and the function succeeds, so eight threads with the same key receive the same handle and the build counter equals one.

### 4.2. Build Completely Before Publishing

Keep the mapping function following a clear sequence:

```text
Immutable key
   |
   v
Resolve MethodType + lookup access
   |
   v
Finish creating/adapting MethodHandle
   |
   v
Check type (if needed)
   |
   v
return MethodHandle
   |
   v
ConcurrentHashMap publishes mapping
```

Do not put an incomplete object into the map and then continue mutating fields that readers will use. With `MethodHandle`, many adapter operations return **a new MethodHandle**, which helps build a complete chain before publishing. Any delegate objects referenced via `bindTo` must also be properly initialized and managed for concurrency.

### 4.3. Cache Keys Must Represent Sufficient Semantics

Consider a framework routing methods by class, signature, and policy version. A key consisting only of `method.getName()` is **not enough**: overloads with different signatures, different class loaders, or different policy versions could be wrongly conflated.

Suggested key components when applicable:

| Component | Reason |
| --- | --- |
| Owner / receiver type | Distinguishes classes/interfaces and runtime class identity |
| Method name + parameter types + return type | Distinguishes overloads and `MethodType` |
| Lookup/access context if relevant | Avoids reusing a cache entry resolved under different privileges with wrong semantics |
| Policy/config version or hash | Prevents using an old target by mistake after an update |
| Defining class loader / deployment identity | Distinguishes versions with the same binary name |
| Adapter flags/calling convention | Distinguishes `asType`, collector/spreader, and other conversions |

Do not stuff everything into the key mechanically; the key must describe **every piece of data that changes the meaning of the cached result**. At the same time, a cache holding `Class<?>`, `MethodHandle`, or class loaders via strong references can prevent class loaders from unloading. Proper lifecycle, eviction, or `ClassValue`/weak-keys design is needed.

### 4.4. `ConcurrentHashMap` Does Not Allow Nulls

`ConcurrentHashMap` does not accept null keys or values. If a valid lookup can return “does not exist”, consider `Optional`, a type-safe sentinel object, a negative cache with TTL, or a separate cache. Having the mapping function return null just to represent “not found” **does not record a negative result**, which can lead to repeated lookups.

Negative caching requires care: a method might appear after a plugin/version change; recording “missing” permanently without a version key will make invalidation difficult to handle.

## 5. Cache Versioning, Invalidation, and Consistent Snapshots

### 5.1. Making Configuration Data Immutable

Pattern in the main example:

```java
record Config(int version, int multiplier, int offset) {
    public int apply(int x) {
        return x * multiplier + offset;
    }
}
record CacheKey(int version, int multiplier, int offset) {}
```

A new config is published via `AtomicReference<Config>`; readers use **one snapshot** to create `CacheKey`. The `MethodHandle` is built from that exact key data. When a new version arrives, the new key automatically separates the new cache entry from the old entry.

This supports **in-flight requests**: a request already holding the old config can continue processing under the old version without the old config object changing underneath it. New requests fetch the new config and use the new cache key.

### 5.2. Multi-Part Updates: Replace the Snapshot Instead of In-Place Edits

**Avoid:**

```java
// COUNTEREXAMPLE: state may be observed during a partial update.
registry.get("rule").setMultiplier(3);
registry.get("rule").setOffset(2);
registry.get("rule").setVersion(2);
```

If three setters run between concurrent requests, a request can observe an unintended mixture. Replace with a complete immutable object and **publish a single reference**, or lock the entire transaction if truly necessary.

### 5.3. Version Keys Do Not Mean Automatic Garbage Collection

Each new version can leave behind old keys/handles. With continuous plugin reloads, the cache can grow unboundedly without a bounded size/expiration/retirement policy. A `MethodHandle` bound to an object can keep the class loader and the entire dependency graph alive.

You must design:

- Threshold of versions to retain;
- when a version no longer has in-flight requests;
- conditions to remove cache entries and release references;
- telemetry for cache hit/miss, build latency, and entry count;
- coordination with class loader lifecycle.

**Do not delete an old entry mid-request** and assume readers have stopped using the old `MethodHandle`. Removing from a map does not invalidate a reference already held by another thread; it only affects subsequent lookups.

### 5.4. Caching a MethodHandle Differs from Caching a CallSite Target

If the cache holds a **MethodHandle bound to an immutable Config**, that entry **does not change its target** when the global config updates. If you want to dispatch the same call site to a new target, you must design a separate **call-site target publication layer**. This is why the following sections cover `MutableCallSite` and `VolatileCallSite`.

## 6. `CallSite` and the Nature of Mutable Targets

`java.lang.invoke.CallSite` associates a call site with a target `MethodHandle` and a fixed `MethodType`. Three common types:

| Type | Updatable Target? | Visibility Across Multiple Threads | When to Use |
| --- | --- | --- | --- |
| `ConstantCallSite` | No | Target fixed after creation | Logic does not change; good JIT optimization opportunities |
| `MutableCallSite` | Yes | Like a **plain field**, does not automatically force other threads to see updates immediately | Infrequent relinking; control publication with `syncAll` |
| `VolatileCallSite` | Yes | Like a **volatile field**, readers have volatile semantics | Frequent updates or strict visibility required |

A `CallSite` has a permanent `type()` for that site. `setTarget` **must** receive a target whose `MethodType` **exactly equals** the old type (do not assume all `asType` conversions are applied automatically). Passing `null` throws `NullPointerException`; passing a target with a different type throws `WrongMethodTypeException` per the contract.

Example of `MethodHandle`s with the same type:

```java
// Two Java methods:
static int plusOne(int x) { return x + 1; }
static int timesTen(int x) { return x * 10; }

// Two handles with the same MethodType (int)int:
MethodType signature = MethodType.methodType(int.class, int.class);
MethodHandle plus = MethodHandles.lookup()
        .findStatic(MyClass.class, "plusOne", signature);
MethodHandle times = MethodHandles.lookup()
        .findStatic(MyClass.class, "timesTen", signature);
```

This is a **snippet**; `MyClass` is an illustrative name, and imports and method definitions must be placed inside a class. The complete example below has the actual `SafeCacheTargetDemo.class` and full imports.

**Do not** replace `(int)int` with `(String)String` and expect the JVM to convert automatically during `setTarget`. If adaptation is truly needed, build `newHandle.asType(site.type())` beforehand and handle `WrongMethodTypeException` if the conversion is invalid.

### 6.1. `dynamicInvoker()` Differs from `getTarget()`

`site.getTarget()` returns the **target MethodHandle at the moment of retrieval**. If you store that reference in a variable and do not re-fetch it, calls through that variable may continue using the old target after the site changes.

`site.dynamicInvoker()` returns a MethodHandle **delegating through the call site**, capable of using the target currently provided by the site, with the memory semantics of that `CallSite` type. This is the appropriate choice when callers want to keep a stable invoker while the underlying target needs to change.

```java
// Snippet in an environment with VolatileCallSite site.
MethodHandle stableInvoker = site.dynamicInvoker();
int a = (int) stableInvoker.invokeExact(3);
site.setTarget(newHandle);
int b = (int) stableInvoker.invokeExact(3);
```

`invokeExact` is signature-polymorphic, so casting `(int)` at the Java call site is **necessary for the JVM signature to match** when the handle returns `int`. See the complete code and the `WrongMethodTypeException` test below.

### 6.2. A CallSite Does Not Have to Come From `invokedynamic`

In this lesson's example, `new MutableCallSite(...)` or `new VolatileCallSite(...)` is created **directly** from Java, and then used via `dynamicInvoker()`. This reproduces the dispatch/visibility contract **without needing** to emit an `invokedynamic` opcode yourself. In a language runtime, a bootstrap method can return those CallSites so an `invokedynamic` instruction can use them.

Keep the distinction clear: using `dynamicInvoker()` from Java **tests the CallSite contract**, and does not claim that this program emitted an `invokedynamic` instruction in `main`.

## 7. `MutableCallSite`: `setTarget` Alone Is Not Enough for Cross-Thread Visibility

### 7.1. A Mutable Site's Target Behaves Like a Plain Field

According to the Java SE 17 API, `MutableCallSite` has a target that interacts with memory **like a non-volatile field**. Therefore:

```java
MutableCallSite site = new MutableCallSite(plus);
MethodHandle invoker = site.dynamicInvoker();
site.setTarget(times);
```

In the **same thread** under normal ordering, you will usually observe the update. But in **other threads** without proper synchronization, readers may continue using the old target, potentially for longer than expected. Do not use a single-threaded test to prove multi-threaded visibility.

### 7.2. Publishing with `MutableCallSite.syncAll`

A coordinated writer can do:

```java
// Snippet: site and times already have the same MethodType.
synchronized (updateLock) {
    site.setTarget(times);
    MutableCallSite.syncAll(new MutableCallSite[]{site});
}
```

`syncAll` forces other threads to discard relevant cached target values. For an update that has completed synchronization and with **no other interfering writers**, future target readers are required to adopt the latest target per the API semantics. Call `syncAll` **after** setting the new target.

**Three important nuances:**

1. A reader may see the **new target early**, right after `setTarget` and **before** `syncAll` returns.
2. A reader may still use the **old target** until synchronization completes. `syncAll` **does not roll back** an invocation that has already started on the old target.
3. If there are **multiple writers**, external mutual exclusion is needed for the `setTarget + syncAll` sequence to avoid one writer overwriting, another syncing, and the application reporting the wrong version. `syncAll` does not provide transaction logic on its own.

### 7.3. Batching Multiple Sites to Reduce Cost

You can group sites that need to be published:

```java
// Snippet assuming sites are all valid and the caller holds the writer lock.
synchronized (updateLock) {
    siteA.setTarget(targetA);
    siteB.setTarget(targetB);
    MutableCallSite.syncAll(
            new MutableCallSite[]{siteA, siteB});
}
```

Batching can save synchronization overhead. However, **do not treat this as an atomic transaction across two sites for running readers**: between `setTarget` calls, a reader may observe new `siteA` and old `siteB`. Even with a single `syncAll`, in-flight calls are not rolled back.

If the system requires a pair of targets to change together **as an atomic snapshot**, consider an **immutable routing table structure** and atomic publication of **a single root reference**, instead of two independent mutable sites.

### 7.4. `syncAll` Can Be Expensive

The API notes that `syncAll` can be costly and should be used sparingly; consider batching. Thus `MutableCallSite` is usually suited for **infrequent relinks**, not policies needing updates every microsecond. Do not guess speed from class names: benchmark the actual workload, read/write ratio, and JVM warm-up.

## 8. `VolatileCallSite`: Visibility Like a Volatile Variable

`VolatileCallSite` has a target with volatile memory semantics.

```java
// Snippet.
VolatileCallSite site = new VolatileCallSite(plus);
MethodHandle invoker = site.dynamicInvoker();
int before = (int) invoker.invokeExact(3);
site.setTarget(times);
int after = (int) invoker.invokeExact(3);
```

`getTarget` has **volatile read** semantics, and `setTarget` has **volatile write** semantics. Invocations dispatched through `dynamicInvoker` observe the target according to the site's rules, without requiring the application to call `syncAll` manually.

**What must not be inferred:** “VolatileCallSite guarantees that every running invocation will switch to the new method mid-execution.” No. An invocation that already selected the old target and started running may complete with the old logic. Volatile only governs memory ordering/visibility of reading/writing the target, not canceling or migrating stack frames.

Compared to `MutableCallSite`:

- Need strict visibility and frequent updates → `VolatileCallSite` is a strong candidate.
- Very rare updates, many read paths needing optimization → `MutableCallSite` + `syncAll` may fit.
- Logic never changes → `ConstantCallSite`, avoiding the need for target publication.

There is no “always fastest” performance conclusion. Volatile semantics often carry overhead on the hot path, especially if the target is repeatedly read while threads contend.

### 8.1. `volatile` Does Not Prevent Lost Updates from Multiple Writers

If two threads read policy version 1 and both compute target version 2, calling `setTarget` concurrently in arbitrary order, the final target is determined by write order. If business logic requires **compare-and-update** based on version, use an external lock, CAS on immutable routing state, or a sequence/versioning mechanism.

`VolatileCallSite` guarantees visibility, but `setTarget` itself does not take an `expectedTarget` for CAS. Do not confuse memory visibility with serializing a configuration update workflow.

## 9. `SwitchPoint`: Invalidating an Optimized Guard

`java.lang.invoke.SwitchPoint` is suitable when a hot-path branch is used **until an assumption no longer holds**.

```java
SwitchPoint point = new SwitchPoint();
MethodHandle fastPath = point.guardWithTest(plus, times);

int first = (int) fastPath.invokeExact(3); // 4
SwitchPoint.invalidateAll(new SwitchPoint[]{point});
int second = (int) fastPath.invokeExact(3); // 30
```

This is a snippet; `plus`/`times` are created in the full example. `guardWithTest(target,fallback)` selects `target` while the point is valid; after `invalidateAll`, it selects `fallback` per the global visibility contract of `SwitchPoint`.

**Special property:** invalidation of a `SwitchPoint` is **one-way only**. Once invalidated, there is no API to “reset valid=true”. To start a new optimized epoch, you must create a **new `SwitchPoint`** and publish the new guarded handle through a safe mechanism.

### 9.1. `SwitchPoint` Is Not a Target Setter

It is not simply `setTarget(newHandle)`:

- It is a mechanism to **guard an assumption**.
- After invalidation, all guarded handles attached to that point will choose the fallback.
- A single `SwitchPoint` can guard multiple handles/call sites.
- The same point cannot be made valid again.

`SwitchPoint.invalidateAll` can have overhead; if invalidating multiple points, consider batching. In-flight calls that passed the guard before invalidation may already be running the old branch; invalidation does not “turn back time”.

### 9.2. Practical Use in Inline Caches

A dynamic language runtime may assume an object shape remains stable: the hot path uses a specialized `MethodHandle`. When the shape changes, the runtime invalidates the `SwitchPoint` so subsequent calls switch to the fallback, where an appropriate target can be relinked.

Distinguish `SwitchPoint` (guarding assumptions) from a `ConcurrentHashMap` cache (storing built handles). Both can appear together, but they solve two different layers.

## 10. `AtomicReference<MethodHandle>`: An Option Without CallSite

If the application does not need an actual `invokedynamic` call site, it can hold a reference to a `MethodHandle` and swap it atomically:

```java
AtomicReference<MethodHandle> current =
        new AtomicReference<>(plus);
int a = (int) current.get().invokeExact(3);
current.set(times);
int b = (int) current.get().invokeExact(3);
```

Here:

- `get` has volatile-read semantics; `set` has volatile-write semantics.
- Each invocation reads **one MethodHandle reference** and invokes it. If a writer swaps the reference after the reader has read it, the running call may still use the old handle.
- If conditional swap is needed, use `compareAndSet(expected,newHandle)`.
- There is no `CallSite` metadata or JVM `invokedynamic` bootstrap; this is an **application-level dispatcher**.

An `AtomicReference<MethodHandle>` does not automatically check “whether the new handle has the same MethodType as the old handle” at `set` time. **The application must validate** `newHandle.type().equals(expectedType)` before publication; otherwise, `invokeExact` callers may fail with `WrongMethodTypeException` at invocation time.

Therefore `VolatileCallSite` has a clear advantage: the **fixed MethodType** invariant is enforced by `setTarget`. With `AtomicReference`, we can swap the root reference, but we must protect the contract ourselves.

### 10.1. Snapshotting a Routing Table

When **multiple targets need to be swapped together under one version**:

```java
// Illustrative snippet.
record Routes(int version, Map<String, MethodHandle> handles) {}

AtomicReference<Routes> current =
        new AtomicReference<>(new Routes(1, Map.of(
                "read", oldReadHandle,
                "write", oldWriteHandle)));

// Writer creates a complete immutable map, then publishes ONE reference.
Routes next = new Routes(2, Map.of(
        "read", newReadHandle,
        "write", newWriteHandle));
current.set(next);

// Reader uses ONE snapshot for all related lookups.
Routes snapshot = current.get();
MethodHandle read = snapshot.handles().get("read");
MethodHandle write = snapshot.handles().get("write");
```

This is a **snippet**; the handles are defined in the actual application. `Map.of` holds immutable entries; the reader keeps a single `Routes` instance. This approach handles consistency for **a group of routes**, rather than updating multiple separate sites/fields.

If a writer needs to update based on the current version, use a CAS loop with a version check. `AtomicReference.set` is an atomic publication, but it **does not automatically reject stale writers**.

## 11. Complete Java 17+ Example: Controlled Caching and Target Swapping

The following example is **a standalone runnable program** using only standard JDK APIs. It demonstrates both layers:

1. **Cache publication**: eight threads contend for the same `CacheKey` via `ConcurrentHashMap.computeIfAbsent`, receiving the **same handle reference**; a new immutable config snapshot leads to a new key.
2. **Target publication**: a writer updates a `VolatileCallSite`, while a reader thread uses `dynamicInvoker` before and after the update; `MutableCallSite.syncAll`; `SwitchPoint.invalidateAll`; `AtomicReference<MethodHandle>`.
3. **Type safety**: attempting to set a `MethodHandle ()String` into a site fixed at `(int)int` and catching `WrongMethodTypeException`.

### 11.1. File `SafeCacheTargetDemo.java`

Create a file named exactly **`SafeCacheTargetDemo.java`** with the following content:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.SwitchPoint;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class SafeCacheTargetDemo {
    record Config(int version, int multiplier, int offset) {
        public int apply(int x) {
            return x * multiplier + offset;
        }
    }

    record CacheKey(int version, int multiplier, int offset) {}

    private static final AtomicReference<Config> CURRENT =
            new AtomicReference<>(new Config(1, 2, 1));
    private static final ConcurrentHashMap<CacheKey, MethodHandle> CACHE =
            new ConcurrentHashMap<>();
    private static final AtomicInteger BUILDS = new AtomicInteger();

    private static MethodHandle build(CacheKey key) {
        BUILDS.incrementAndGet();
        Config snapshot = new Config(
                key.version(), key.multiplier(), key.offset());
        try {
            return MethodHandles.lookup().findVirtual(
                    Config.class, "apply",
                    MethodType.methodType(int.class, int.class)
            ).bindTo(snapshot);
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static CacheKey key(Config c) {
        return new CacheKey(c.version(), c.multiplier(), c.offset());
    }

    public static int plusOne(int input) {
        return input + 1;
    }

    public static int timesTen(int input) {
        return input * 10;
    }

    public static void main(String[] args) throws Throwable {
        Config snapshot1 = CURRENT.get();
        CacheKey key1 = key(snapshot1);

        ExecutorService workers = Executors.newFixedThreadPool(8);
        try {
            CountDownLatch start = new CountDownLatch(1);
            List<Future<MethodHandle>> tasks = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                tasks.add(workers.submit(() -> {
                    start.await();
                    return CACHE.computeIfAbsent(
                            key1, SafeCacheTargetDemo::build);
                }));
            }
            start.countDown();

            MethodHandle first = tasks.get(0).get();
            boolean identical = true;
            for (Future<MethodHandle> task : tasks) {
                identical &= first == task.get();
            }
            System.out.println("same cached handle=" + identical);
            System.out.println("cache entries=" + CACHE.size());
            System.out.println("builds after contention=" + BUILDS.get());
            System.out.println("old snapshot result=" +
                    (int) first.invokeExact(5));

            CURRENT.set(new Config(2, 3, 2));
            Config snapshot2 = CURRENT.get(); // Read one snapshot.
            MethodHandle second = CACHE.computeIfAbsent(
                    key(snapshot2), SafeCacheTargetDemo::build);
            System.out.println("new snapshot result=" +
                    (int) second.invokeExact(5));
            System.out.println("old handle remains=" +
                    (int) first.invokeExact(5));
            System.out.println("cache entries after version=" + CACHE.size());
            System.out.println("builds after version=" + BUILDS.get());
        } finally {
            workers.shutdown();
            if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                throw new IllegalStateException("workers did not terminate");
            }
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(int.class, int.class);
        MethodHandle plus = lookup.findStatic(
                SafeCacheTargetDemo.class, "plusOne", signature);
        MethodHandle times = lookup.findStatic(
                SafeCacheTargetDemo.class, "timesTen", signature);

        // VolatileCallSite: one reader thread reads before/after writer.
        VolatileCallSite volatileSite = new VolatileCallSite(plus);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        CountDownLatch before = new CountDownLatch(1);
        CountDownLatch afterUpdate = new CountDownLatch(1);
        ExecutorService reader = Executors.newSingleThreadExecutor();
        try {
            Future<int[]> readPair = reader.submit(() -> {
                try {
                    int oldResult = (int) volatileInvoker.invokeExact(3);
                    before.countDown();
                    afterUpdate.await();
                    int newResult = (int) volatileInvoker.invokeExact(3);
                    return new int[]{oldResult, newResult};
                } catch (Throwable ex) {
                    throw new IllegalStateException(ex);
                }
            });
            before.await();
            volatileSite.setTarget(times);
            afterUpdate.countDown();
            int[] pair = readPair.get();
            System.out.println("volatile other thread=" +
                    pair[0] + " -> " + pair[1]);
        } finally {
            afterUpdate.countDown();
            reader.shutdown();
            if (!reader.awaitTermination(10, TimeUnit.SECONDS)) {
                reader.shutdownNow();
                throw new IllegalStateException("reader did not terminate");
            }
        }

        // MutableCallSite: publish update to readers using syncAll.
        MutableCallSite mutable = new MutableCallSite(plus);
        MethodHandle mutableInvoker = mutable.dynamicInvoker();
        System.out.println("mutable before=" +
                (int) mutableInvoker.invokeExact(3));
        synchronized (mutable) {
            mutable.setTarget(times);
            MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        }
        System.out.println("mutable after syncAll=" +
                (int) mutableInvoker.invokeExact(3));

        // SwitchPoint: one-way valid -> invalid.
        SwitchPoint switchPoint = new SwitchPoint();
        MethodHandle guarded = switchPoint.guardWithTest(plus, times);
        System.out.println("switch before=" +
                (int) guarded.invokeExact(3));
        SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
        System.out.println("switch after=" +
                (int) guarded.invokeExact(3));

        // AtomicReference<MethodHandle>: application-level dispatch.
        AtomicReference<MethodHandle> reference =
                new AtomicReference<>(plus);
        System.out.println("atomic ref before=" +
                (int) reference.get().invokeExact(3));
        reference.set(times);
        System.out.println("atomic ref after=" +
                (int) reference.get().invokeExact(3));

        // CallSite rejects target with a different MethodType.
        try {
            volatileSite.setTarget(
                    MethodHandles.constant(String.class, "bad"));
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrong target type=" +
                    ex.getClass().getSimpleName());
        }
    }
}
```

### 11.2. Compiling and Running

In the directory containing the source above, using **JDK 17 or later**:

```bash
javac --release 17 SafeCacheTargetDemo.java
java SafeCacheTargetDemo
```

**Exact stdout verified on the JDK by actual compilation and execution:**

```text
same cached handle=true
cache entries=1
builds after contention=1
old snapshot result=11
new snapshot result=17
old handle remains=11
cache entries after version=2
builds after version=2
volatile other thread=4 -> 30
mutable before=4
mutable after syncAll=30
switch before=4
switch after=30
atomic ref before=4
atomic ref after=30
wrong target type=WrongMethodTypeException
```

Verification completed with `javac` exit code **0** and `java` exit code **0**.

### 11.3. Why Is the Cache Part Output Deterministic?

`CURRENT` initially holds `Config(version=1, multiplier=2, offset=1)`, so `apply(5)` returns `5 * 2 + 1 = 11`. Eight tasks on an `ExecutorService` are released by `CountDownLatch.start` and all call `computeIfAbsent(key1, ...)`.

For that exact key, **the mapping function succeeds**, there is no competing remove/update, and the map starts empty, so `CACHE` contains one mapping. `builds after contention=1`; every future receives the same `MethodHandle` reference, so `same cached handle=true`.

When `CURRENT.set(new Config(2,3,2))` runs, the reader fetches **a new snapshot**; the key differs and the cache builds a new handle. `apply(5)` returns `17`. However, `first` remains bound to the old config, so `old handle remains=11`. This is the designed **versioned cache** behavior, not a stale visibility bug.

`cache entries after version=2` and `builds after version=2` are expected test results because the application **intentionally retains both versions**; production must have an eviction policy.

### 11.4. Why Does the `VolatileCallSite` Update Use Two Latches?

The reader thread performs:

1. Uses the already-created `volatileInvoker` and invokes it with `3`; receives `4` from `plusOne`.
2. Signals the writer that the first read is done via `before.countDown()`.
3. Waits on `afterUpdate.await()`.
4. Invokes the same `volatileInvoker` again, after the writer calls `setTarget(times)`, receiving `30`.

The latches **make the event ordering reproducible** and themselves establish synchronization. Therefore, the experiment verifies behavior and API usage, **and is not an isolated measurement proving only the volatile memory barrier**. Proof of visibility semantics must rely on the Java SE 17 API/JMM, not on a single stress-test output.

If you remove the latches and let the threads race freely, the reader could pick the old or new target depending on timing; you should not assert that every concurrent start sees the new target.

### 11.5. `MutableCallSite`: Result After `syncAll`

`mutable before=4` and `mutable after syncAll=30`. The code uses **a single writer**, so `synchronized (mutable)` illustrates a writer critical section; if there are multiple writers in the same registry, every writer must obey **the exact same lock** so that `setTarget/syncAll` is serialized.

The same-thread result shows the code works, but does not replace the `syncAll` contract for other threads. A call that already entered the old target before publication can still finish with the old value; `syncAll` is not a transaction rollback.

### 11.6. `SwitchPoint` and `AtomicReference`

`switch before=4`, and after invalidation `switch after=30`, corresponding to target/fallback. An invalidated `SwitchPoint` cannot return to the valid state; use a new point for a new optimized epoch.

`atomic ref before=4` and `atomic ref after=30` illustrate application-level volatile reference publication. Here the code actively swaps the `MethodHandle` reference. **`AtomicReference` does not do the same thing as JVM `invokedynamic` linkage**, and does not enforce `MethodType` on `set`.

### 11.7. Controlling the Target Type

`volatileSite` has the fixed type **`(int)int`**. `MethodHandles.constant(String.class,"bad")` has type **`()String`**. `VolatileCallSite.setTarget` rejects it with `WrongMethodTypeException`:

```text
wrong target type=WrongMethodTypeException
```

The JVM does not automatically add an `int` parameter or convert the `String` return type to `int`. If an adapter is needed, you must check and build a `MethodHandle` of the **exact type** before publishing.

## 12. Commonly Overlooked Race Conditions

### 12.1. Double-Checked Locking Missing `volatile`

A classic example:

```java
// COUNTEREXAMPLE: singleton without valid publication.
private static Registry instance;

static Registry get() {
    if (instance == null) {
        synchronized (Registry.class) {
            if (instance == null) {
                instance = new Registry();
            }
        }
    }
    return instance;
}
```

This is a **discouraged snippet**. Readers outside synchronization do not read a `volatile` reference, so double-checked locking lacks the proper publication guarantee.

Fix with `private static volatile Registry instance;` and fully initialize the object before publishing, or use the JVM's holder idiom / initialization-on-demand when only an immutable singleton is needed.

Do not hand-roll complex double-checked caches if `ConcurrentHashMap.computeIfAbsent` or class initialization already solves the problem more cleanly.

### 12.2. Non-Atomic Check-Then-Act

```java
// COUNTEREXAMPLE with a regular map (or even with a concurrent map
// if only a single build/update is required).
if (!cache.containsKey(key)) {
    cache.put(key, build(key));
}
```

Even if `cache` is a `ConcurrentHashMap`, splitting `containsKey` and `put` into two operations still allows two writers to interleave. If the mapping function is expensive or you must ensure a single valid mapping is chosen, use `computeIfAbsent` properly, with its null/throw semantics understood.

### 12.3. “Assuming `volatile` Makes Counter Increments Atomic”

`volatile int count` with `count++` is **not atomic**. It is read → add → write; threads can lose updates. Use `AtomicInteger.incrementAndGet`, `LongAdder` (for high-frequency statistics, not for generating unique transaction ordering), or a lock.

In the exercise, `BUILDS` is an `AtomicInteger`; if you used a plain `int++` and relied on the count in a stress test, several builds could occur while the counter misleads you due to lost updates.

### 12.4. Writers Winning in an Unintended Order

Two concurrent writers can publish:

```text
W1 build target(version=11) --------------- publish
W2 build target(version=12) ---- publish
```

If W1 finishes building slower than W2 and calls `setTarget` last, the target can **revert to version 11**. `VolatileCallSite` still completely satisfies its memory semantics; the **business invariant “version only increases”** is broken due to lack of coordination.

You need:

- a lock / serialized update queue;
- CAS on a `(version, target)` record;
- or rejection if the proposed version is not newer than current.

`CallSite.setTarget` has no built-in version check. Do not rely on the completion order of network/config loaders to determine the latest config.

### 12.5. Multi-Site Updates Are Not an Atomic Release

When a request needs both `routeA` and `routeB` at the same version, if code sets two sites separately, a reader can observe “A version 2, B version 1” between updates. A final `syncAll` improves visibility but **does not turn two sites into a global transaction**.

For invariants requiring consistency, use an immutable routing snapshot in an `AtomicReference` and read **once per request**. Alternatively, a shared lock or a suitable generation/seqlock protocol can be used, provided correctness is proven.

### 12.6. In-Flight Requests and Rollback

Even when the writer has published the new target, an invocation that already read the old target **before publication** may still be executing. No `CallSite` API “stops all old frames” just because `setTarget` or `invalidateAll` was called.

If target switching has security or business-critical implications, you must also determine:

- Should new requests be blocked during the transition?
- Are old requests allowed to finish?
- Is quiescence/barrier/epoch reclamation needed?
- When can resources/old class loader versions be cleaned up?
- Should validation occur at **action commit time** rather than only at dispatch time?

Target visibility only solves **choosing the call path at observation time**, and does not replace a version-transition governance protocol.

## 13. Choosing a Model by Update Frequency and Contract

| Requirement | Suitable Model | Trade-off |
| --- | --- | --- |
| Cache lookup/adapter by key, rarely changes | `ConcurrentHashMap.computeIfAbsent` | Accurate key, fast mapping function, and bounded cache |
| Publish a consistent immutable config group | `AtomicReference<Config>` or `volatile Config` | Each request must read one snapshot and hold it |
| A target linked only once | `ConstantCallSite` | No target updates |
| Rare relinks, want optimized read path | `MutableCallSite.setTarget` + `syncAll` | Sync operations can be costly; writers must coordinate |
| Target changes frequently, readers need volatile visibility | `VolatileCallSite` | May add volatile overhead on the hot path |
| One-way invalidation of a hot-path assumption | `SwitchPoint` | No reset; create a new point for a new epoch |
| No `invokedynamic`, only swapping a Java dispatch reference | `AtomicReference<MethodHandle>` | Must validate `MethodType` and version yourself |
| Swap multiple routes as one snapshot | `AtomicReference<ImmutableRoutes>` | Build complete new table and publish one root |
| Multiple writers needing conditional updates | CAS/version check or external lock | Must handle retries/conflicts explicitly |
| Runtime reloading many class loaders | Per-loader/weak/ClassValue cache + lifecycle | Avoids strong-reference/metaspace retention |

### 13.1. The “Read-Mostly, Write-Rarely” Rule

If the read path is extremely hot and updates are rare, `MutableCallSite` with batched `syncAll` can be attractive. However, if updates are frequent, measure whether the cost of `syncAll` and coordination exceeds the cost of volatile reads.

If the target changes per request, by design you probably **should not** keep a mutable call site: using an `AtomicReference` to an appropriate policy or target function is usually clearer.

### 13.2. Both Cache and Target Must Preserve the Exact `MethodType`

For `MethodHandle` adapters, verify:

```java
if (!newHandle.type().equals(expectedType)) {
    throw new IllegalArgumentException(
            "Target type mismatch: " + newHandle.type());
}
```

This is a **snippet** with existing variables. Especially if the cache key does not include the full signature, a handle with a different type could be mistakenly returned to a call site and cause `WrongMethodTypeException`.

Do not arbitrarily call `asType` as a “force everything through” workaround: the conversion must be valid and may add boxing/unboxing/casts/overhead. If an adapter does not match business semantics, passing the type check still does not guarantee correct logic.

## 14. Testing Concurrency Reliably

### 14.1. Why Passing a Multi-Threaded Test Is Not Enough

A visibility bug may not surface with a small thread count, in interpreter mode, or on a specific CPU/cache topology. The compiler/JIT is allowed to optimize according to the JMM; code with a data race has no guarantees and just “working today” should not be used in production.

Distinguish QA categories:

- **API correctness test:** build a `MethodHandle` with the right signature, `invokeExact` returns the right result.
- **Publication test:** map/cache creates and publishes a completed object.
- **Concurrency scenario test:** readers/writers operate under contention, no deadlocks, no unintended lost updates.
- **Memory-model reasoning:** based on happens-before/volatile/atomic contracts, not on iteration counts.
- **Performance benchmark:** use JMH or an appropriate tool, with warm-up and multiple JVM forks, not measured from a simple `System.nanoTime` loop.

### 14.2. Barriers in the Example Code

The code uses `CountDownLatch` and `Future.get()` for coordination, because deterministic stdout is desired. They are also **synchronization actions**, so:

- The test verified the pipeline and behavior.
- It **does not prove in isolation** that a continuously racing reader can observe the new target solely due to those specific operations.
- To investigate reorderings/happens-before under contention, use specialized tools such as **JCStress**, while reading the JLS/Javadoc.

**Do not** write an unsynchronized test loop and wait until a failure appears: not seeing a failure is not proof.

### 14.3. Minimum Test Matrix

| Scenario | What to Verify |
| --- | --- |
| 8 threads `computeIfAbsent` same key, function succeeds | One mapping with consistent value; no partially constructed object observed |
| Mapping function returns null or throws | Result is not treated as a cached successful value |
| Two consecutive config versions | Cache keys are distinct; old handle stays bound to old version |
| Config update while a request is running | Request uses one immutable snapshot, without mixing fields |
| Writer `VolatileCallSite.setTarget` | Subsequent readers follow volatile contract, understanding in-flight limits |
| Writer `MutableCallSite.setTarget` before sync | Do not assume other readers have already seen the update |
| `MutableCallSite.syncAll` completes | Future readers adopt the published target properly when no competing writes occur |
| Two writers updating target concurrently | Serialized ordering/CAS version, no silent downgrade |
| `SwitchPoint.invalidateAll` | Guard switches to fallback and point cannot be reset |
| Target with different `MethodType` | `WrongMethodTypeException` or validation failure |
| Cache eviction/class loader reload | No unbounded strong references; in-flight requests remain safe |
| Updating multiple routes in the same epoch | Reader holds one consistent routing snapshot |
| Thread interruption/exceptions during build | Cache is not left in a half-built state |

## 15. Exercises and Solutions

**Q1.** A `HashMap<String,MethodHandle>` is accessed with `get` and `put` by multiple threads without locking. Is it safe because `MethodHandle` is generally immutable?  
**Solution:** No. Value immutability does not make `HashMap` thread-safe or create publication/happens-before for map updates. Use `ConcurrentHashMap` or an immutable map snapshot with proper publication.

**Q2.** A cache map is declared `volatile Map<...>`, yet the writer still calls `map.put` on a shared `HashMap`. Is that enough?  
**Solution:** No. A `volatile` reference does not turn a `HashMap`'s contents into a concurrent collection. Create a new immutable map and `volatile`-publish it, or use a concurrent map.

**Q3.** Two variables `volatile int factor` and `volatile int offset` are updated separately. Is a reader guaranteed to see both from the same version?  
**Solution:** No. Each field has its own memory semantics and does not form an atomic multi-field snapshot. Use an immutable config object and a single reference publication.

**Q4.** `ConcurrentHashMap.computeIfAbsent` can return null from the mapping function; is null cached?  
**Solution:** No. `ConcurrentHashMap` does not store null values; another access may recompute.

**Q5.** The mapping function throws an exception. Can you conclude that all subsequent lookups will see the same cached exception?  
**Solution:** No. The cache does not establish a mapping from a failed computation; subsequent attempts may retry. This **differs** from JVM failed-resolution mechanisms for certain symbolic references.

**Q6.** A cache key only contains the name `"process"` even though `process(String)` and `process(int)` exist. What is the risk?  
**Solution:** The two overloaded methods are conflated to the wrong `MethodHandle`. The key must include class/owner and full signature, plus any context that alters meaning.

**Q7.** `MutableCallSite.setTarget` is called by a writer. Must another reader thread see the new target immediately?  
**Solution:** No. A mutable target behaves like a plain field; proper synchronization is needed, typically `MutableCallSite.syncAll` to force visibility per the contract.

**Q8.** Does `MutableCallSite.syncAll` cancel an invocation that has already started running the old target?  
**Solution:** No. It does not roll back in-flight invocations. An application-level protocol is needed if quiescence or stronger revocation is required.

**Q9.** A thread calls `VolatileCallSite.setTarget`. Is `MutableCallSite.syncAll` also needed?  
**Solution:** No. `VolatileCallSite` already has volatile memory semantics; `syncAll` is a static API for `MutableCallSite[]`.

**Q10.** Does placing a `MutableCallSite` in a `ConcurrentHashMap` give `site.setTarget` volatile visibility automatically?  
**Solution:** No. The map publishes the reference to the site; the target field inside `MutableCallSite` still has mutable site semantics.

**Q11.** You want to swap two routes as a consistent snapshot. Can you call `VolatileCallSite.setTarget` twice and consider it atomic?  
**Solution:** No. A reader can observe a mix before both updates finish. Use an immutable routing snapshot with a single root `AtomicReference` or a synchronization protocol.

**Q12.** After `SwitchPoint.invalidateAll`, can you reset the same point to reuse the old fast target?  
**Solution:** No. Invalidation is one-way. Build a new point and a new guarded chain if a new epoch is needed.

**Q13.** Can an `AtomicReference<MethodHandle>` swap the target to a handle with the wrong type?  
**Solution:** `AtomicReference.set` itself does not check `MethodType`. The application must validate; an error may appear at `invokeExact`. `CallSite.setTarget` enforces the fixed type invariant.

**Q14.** Two writers concurrently swap the target to version 7/8. Does `VolatileCallSite` guarantee it will never be downgraded to version 7?  
**Solution:** No. Volatile only provides memory semantics; version ordering requires CAS/an external lock/a separate policy.

**Q15.** In the example, eight threads receive the same handle and `BUILDS==1`. Can you conclude that the mapping function runs exactly once in all programs and at all times?  
**Solution:** No. That result holds for a successful mapping that is not removed, does not return null/throw, and under the experiment's conditions. The key could be evicted/recomputed later.

**Q16.** Does a `MethodHandle` bound to `Config(version=1)` automatically switch to Config version 2 after `CURRENT.set`?  
**Solution:** No. A bound handle keeps the bound object. A versioned cache creates a new entry; existing in-flight calls may use the old config.

**Q17.** Both `volatile` write/read and `synchronized` involve happens-before, so do they make any block of code atomic?  
**Solution:** No. They have specific memory/synchronization guarantees; multi-step transactions require a clear protocol/lock/CAS and invariants.

**Q18.** After `syncAll`, a caller receives the old result from an invocation that started earlier. Is it necessarily a visibility bug?  
**Solution:** No. An in-flight invocation may have already selected the old target. Relying solely on the return value is not enough to infer when the target was read.

**Q19.** Why should `newHandle.type().equals(expected)` be checked when swapping targets?  
**Solution:** Because `CallSite` keeps a fixed `MethodType`; a new target with a mismatched signature is rejected. `AtomicReference` does not check automatically, making validation even more important.

**Q20.** When an old plugin loader has been replaced, does `cache.remove(key)` alone guarantee the loader is unloaded immediately?  
**Solution:** No. Other threads, bound objects, `MethodHandle`s, static registries, or external callbacks may still hold strong references. Unloading requires lifecycle cleanup and appropriate GC conditions.

## 16. Production Deployment and Diagnostics Checklist

To bring a cache/target publication design into a real application:

1. **Identify invariants:** need consistent values per request, no version downgrades, how many active versions, whether in-flight calls may use old logic?
2. **Choose the publication root:** `ConcurrentHashMap` for per-key mappings, immutable snapshot + `AtomicReference`/`volatile` for a group of fields.
3. **Structure keys properly:** full signature, class identity/loader, version, lookup context when relevant.
4. **Finish initialization before publishing:** do not put a half-built adapter/registry into a shared cache.
5. **Choose the CallSite type:** `ConstantCallSite` if immutable; `MutableCallSite+syncAll` if relinks are rare; `VolatileCallSite` if updates are frequent and volatile visibility is needed.
6. **Preserve the MethodType invariant:** do not update a site with a wrong-type target; `asType` adapters must be valid.
7. **Serialize writers:** lock, CAS, or update coordinator, especially when `setTarget + syncAll` and config versions can race.
8. **Distinguish when updates are seen:** readers may see the new target early; old in-flight calls are not revoked. Do not describe `syncAll` as a global atomic transaction.
9. **Choose invalidation:** versioned key, atomic routing snapshot, or `SwitchPoint` (one-way), without mixing semantics.
10. **Maintain safe lifecycle:** bounded cache, classloader/version retirement, cleanup of bound references and handles.
11. **Record telemetry:** hit/miss/build counts, cache size, build duration, relink count, `syncAll` duration, target version, error types.
12. **Test under contention:** multiple readers/writers, absent keys, failed computations, exceptions, version changes; use barriers for reproducible behavior.
13. **Reason via JMM:** benchmarks/tests do not replace happens-before proofs; read the Java API/JLS.
14. **Benchmark before optimizing:** separate build cost, dispatch cost, relink/sync cost, and memory; use JMH with warm-up/forks.
15. **Design rollback:** if a business policy rollback is needed, perform a **new target/snapshot publication** with an appropriate version; do not expect already-running calls to be reversed.

A system can simultaneously use a **versioned ConcurrentHashMap cache** for expensive lookups and a **VolatileCallSite** for a dispatch point that needs swapping. What matters is identifying **which concurrency primitive is responsible for which variable/state**, rather than piling on as many primitives as possible.

## 17. Summary and Official Documentation

### 17.1. Quick-Reference Summary Table

| Question | Answer |
| --- | --- |
| How to cache `MethodHandle` across multiple threads? | `ConcurrentHashMap.computeIfAbsent` or an immutable snapshot with clear publication |
| Can a multi-field `Config` be kept consistent per version? | Yes, by using an immutable config and reading one published reference |
| Does `MutableCallSite.setTarget` automatically guarantee immediate cross-thread visibility? | No; the target is like a plain field, use proper synchronization/`syncAll` |
| How does `VolatileCallSite.setTarget` differ? | Volatile memory semantics for the target |
| Want one-way invalidation for an optimized path? | `SwitchPoint.invalidateAll` |
| Want to swap a dispatch reference outside CallSite? | `AtomicReference<MethodHandle>`, validate signature yourself |
| Does `syncAll` provide a transaction across sites or roll back in-flight calls? | No |
| Can changing the target change the MethodType? | No, the site keeps a fixed MethodType |
| Does a cache map automatically change state inside a mutable callsite? | No |
| Does passing a multi-threaded test prove memory-model correctness? | No; JMM reasoning plus proper tests/benchmarks are needed |

**Conclusion:** Separate **cache reference publication**, **immutable configuration snapshot publication**, and **CallSite target publication**. Each layer has its own tools and memory visibility contract. Choose techniques based on invariants and relink frequency, not on code “appearing to work” under a few stress-test runs.

### 17.2. Official Java SE 17 References

- [`java.lang.invoke.MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): target semantics as a plain field; `syncAll`, batch cost, racing updates, in-flight calls.
- [`java.lang.invoke.VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target as a volatile variable, `dynamicInvoker` and `setTarget`.
- [`java.lang.invoke.CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): fixed `MethodType` and CallSite types.
- [`java.lang.invoke.SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): `guardWithTest` and one-way invalidation.
- [`java.util.concurrent.ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `computeIfAbsent`, per-key happens-before, constraints on mapping functions, null values.
- [`java.util.concurrent.atomic.AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): volatile/CAS memory semantics and conditional updates.
- [`java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): acquire/release/volatile/atomic access modes.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization order, happens-before, final-field semantics.
- [`java.util.concurrent.CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) and [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): synchronization guarantees used in test code.
