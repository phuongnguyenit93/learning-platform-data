# Avoiding JVM-Wide Reflection Caches Without a Lifecycle Policy in Java

## 1. Key Questions Before Creating a Cache

A Reflection cache is complete only when it has **the right data, the right owner, and the right expiration**. `ConcurrentHashMap` handles multiple threads, yet it does not set a maximum size, expiration time, or teardown point on its own. Therefore, for any metadata cache, you must specify: *who creates it, who can use it, how long metadata remains valid, who removes it, and what to observe after removal*.

Different situations call for different decisions: metadata for a short-lived request can stay in a local variable; a class schema used millions of times can live in `ClassValue`; a plugin registry across versions must drop caches when the plugin stops; policy- or tenant-dependent results must be versioned or stay scoped to the request.

Regarding classloaders, an entry holding a `Class<?>`, `Method`, `Field`, or handle inside a long-lived component **can** retain an old plugin's loader. Still, not every `static` field is a leak: you must inspect ownership and actual reference paths. Deeper coverage of GC roots and `WeakHashMap` is in the lesson “Caches Holding Class Can Retain the Entire ClassLoader”; this lesson focuses on building **testable lifecycle policies**.

## 2. Classifying Data to Determine Validity Lifetime

| Cached Data | Primary Identity/Scope | When Recomputation or Removal Is Needed |
| --- | --- | --- |
| `Field`, `Method`, `Constructor` of a specific class | `Class<?>`, member signature, and lookup rules | Owner/plugin unloads or metadata needs rebuild |
| Immutable descriptor derived from a class | Per `Class<?>`; `ClassValue` when suitable | Class/schema policy actually changes |
| Schema filtered by naming policy/config | Class **plus policy generation/version** | Policy or schema version changes |
| Decision on which fields are exposed to a user/tenant | Request/user/policy; avoid class-only caching | Permissions, tenant, or request context change |
| Value of `Field.get(instance)` | **Instance** state, not class metadata | State changes; normally does not belong in a metadata cache |
| Data/handlers of an old plugin generation | Plugin instance/generation | Plugin closes, unregisters, and finishes in-flight work |

**A correct key alone is not enough.** `Class<?>` distinguishes runtime classes by loader; however, the same class can have different schemas when policies or configurations change. A `ClassValue` distinguishes only by class, so version-dependent data needs an additional version/invalidation layer. Conversely, caching by `getName()` strings can conflate classes from two loaders.

**Values must also be checked.** If a shared value contains private-access capabilities or per-tenant state, merely adding fields to the key does not automatically enforce proper permission boundaries. Keep shared metadata in a verified scope and apply per-request authorization checks at the point of use.

## 3. Three Practical Options and Cleanup Responsibilities

### 3.1. Caches Owned by a Request, Session, or Plugin

Use this when data is repeated only briefly or is tied to one plugin generation. An `InspectionSession` can hold a `Map<Class<?>, Metadata>`, implement `AutoCloseable`, and clear entries in `close()`; a runnable example is in section 4.

Plugin unloading requires a clear order: stop accepting new work → complete/cancel in-flight work → unregister listeners/callbacks/tasks → clear caches and references owned by the plugin → close appropriate resources. `clear()` only drops the map's own references and does not prove the JVM unloaded classes. For multi-threaded sessions, `close()` must also coordinate with in-flight operations rather than letting lookups and shutdown race.

### 3.2. `ClassValue<T>` for Metadata Truly Belonging to Each `Class`

If a descriptor is purely a function of `Class<?>` and reused frequently, `ClassValue` avoids a global map directly holding strong keys. `computeValue(type)` may run multiple times under contention, so construct complete metadata, ideally side-effect-free. `remove(type)` invalidates only one class in one `ClassValue`, and provides no TTL, `clearAll`, or closing of external resources. Readers already holding an old value may keep using it; if policy requires uniform switching, add synchronization/generation control at the owning layer.

### 3.3. Bounded/TTL or Generation-Aware Caches

Choose this when the system must cache across dynamic keys like `(Class, policyVersion)`, needs memory bounds, and needs eviction control. Explicitly configure **maximum size/weight, idle/TTL, invalidation triggers, and owner**; `ConcurrentHashMap` provides none of these automatically.

For example, when serialization config advances from generation `v12` to `v13`, build a new metadata snapshot, publish the new generation, and discard `v12` entries once older processing passes complete. TTL is a fallback time limit, not a substitute for invalidation events when schemas or security policies change. Monitor hits/misses, current entries, evictions, and retained old loaders to detect ineffective policies.

### Design Checklist

Before implementing, define **owner**, **key/value dependencies**, **validity lifetime**, **invalidation points**, **concurrent close/reload behavior**, and **verification strategy**. A cache missing any of those items may be fast in steady state yet return stale schemas or retain plugins unexpectedly long.

## 4. Complete Java 17+ Example: Global Map, `ClassValue`, and Session

The example below uses simple metadata consisting of field names of the `Invoice` class. The program illustrates **comparing cache behaviors**, not full class unloading. Because it runs sequentially on a normal class, scan counts are deterministic. Do not copy `GLOBAL` as a production solution without a release policy.

Save the contents to `ReflectionCacheLifetimeDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ReflectionCacheLifetimeDemo {
    static final class Invoice {
        private final String id = "INV-7";
        private final int amount = 500;
        private transient String debug = "temporary";
    }

    private static final AtomicInteger SCANS = new AtomicInteger();

    // Anti-pattern demo: never cleared, strongly retains Class keys.
    private static final ConcurrentMap<Class<?>, List<String>> GLOBAL =
            new ConcurrentHashMap<>();

    private static final ClassValue<List<String>> PER_CLASS = new ClassValue<>() {
        @Override
        protected List<String> computeValue(Class<?> type) {
            return scan(type);
        }
    };

    private static List<String> scan(Class<?> type) {
        SCANS.incrementAndGet();
        return Arrays.stream(type.getDeclaredFields())
                .filter(f -> !f.isSynthetic())
                .filter(f -> !Modifier.isStatic(f.getModifiers()))
                .filter(f -> !Modifier.isTransient(f.getModifiers()))
                .map(Field::getName)
                .sorted()
                .toList();
    }

    static final class InspectionSession implements AutoCloseable {
        private final Map<Class<?>, List<String>> cache = new HashMap<>();
        private boolean closed;

        List<String> fieldNames(Class<?> type) {
            if (closed) throw new IllegalStateException("session closed");
            return cache.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan);
        }

        int entries() {
            return cache.size();
        }

        @Override
        public void close() {
            if (!closed) {
                cache.clear();
                closed = true;
            }
        }
    }

    public static void main(String[] args) {
        Class<?> type = Invoice.class;
        System.out.println("global first: " +
                GLOBAL.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan) +
                ", scans=" + SCANS.get());
        System.out.println("global again: " +
                GLOBAL.computeIfAbsent(type, ReflectionCacheLifetimeDemo::scan) +
                ", scans=" + SCANS.get());

        System.out.println("ClassValue first: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());
        System.out.println("ClassValue again: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());
        PER_CLASS.remove(type);
        System.out.println("ClassValue after remove: " + PER_CLASS.get(type) +
                ", scans=" + SCANS.get());

        try (InspectionSession session = new InspectionSession()) {
            System.out.println("session first: " + session.fieldNames(type) +
                    ", scans=" + SCANS.get());
            System.out.println("session again: " + session.fieldNames(type) +
                    ", entries=" + session.entries() +
                    ", scans=" + SCANS.get());
        }
        System.out.println("session closed: references cleared");
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 ReflectionCacheLifetimeDemo.java
java ReflectionCacheLifetimeDemo
~~~

Exact output (single-threaded program):

~~~text
global first: [amount, id], scans=1
global again: [amount, id], scans=1
ClassValue first: [amount, id], scans=2
ClassValue again: [amount, id], scans=2
ClassValue after remove: [amount, id], scans=3
session first: [amount, id], scans=4
session again: [amount, id], entries=1, scans=4
session closed: references cleared
~~~

**Interpretation:**

1. `GLOBAL` scans only once, but the `Class<?>` entry stays in the `static` map until removed or the cache itself is GC'd. This map has no `remove/clear`.
2. `PER_CLASS` also reuses metadata; calling `remove(Invoice.class)` causes the next `get` to scan again. With multiple threads, the `computeValue` count need not match the demo.
3. `InspectionSession` reuses results within the session; `close()` clears the map. The `"references cleared"` line only confirms application-level cleanup, **it does not prove the ClassLoader was unloaded**.
4. `scan` only extracts metadata, without reading `Invoice` instance state. Skipping `transient` fields is **this demo's specific policy**, not a mandatory rule when using Reflection.
5. `getDeclaredFields()` does not guarantee order; the example uses `sorted()` for deterministic output.
6. `InspectionSession` demonstrates **sequential usage**. `HashMap`/`closed` are not thread-safe; a shared multi-threaded session needs synchronization and rules to stop tasks before `close()`.

## 5. Why Can the Right Key Still Return the Wrong Value?

`Class<?>` is a valid key for **class structural metadata**, yet many derived metadata values also depend on policy. The same class can have different projections when:

- Internal audits need technical fields, while public APIs exclude sensitive fields.
- Tenant A and Tenant B are allowed to see different fields.
- Serialization config, naming strategy, locale, or schema version changes.
- Module layer/access context differs, or a plugin is hot-reloaded.
- The mapping between fields and business properties changes even though `Class<?>` stays the same.

Never cache an `allowed=true` decision for User A in a JVM-wide `Map<Class<?>, Boolean>` and reuse it for User B. Cache the **shareable metadata** and compute authorization/redaction per request; or include policy identity/version in the key and place the cache inside an owner with a concrete lifecycle.

Do not cache `Field.get(obj)` as if it were metadata: that is **an instance's runtime value**, which changes over time, carries security implications, and does not automatically form a consistent snapshot across multiple fields.

## 6. Eviction, Unloading, and Concurrency Are Three Separate Topics

### 6.1. Eviction Does Not Mean Immediate Class Unloading

When an entry is removed, the map drops **its own** reference. Live objects, stack frames, thread-locals, executors, listeners, callbacks, monitoring tools, or other caches can still hold the ClassLoader. Even when no strong reference paths remain, the JVM may defer GC/class unloading.

Do not test for leaks by calling `System.gc()` once and declaring certainty. Analyze heap dumps, GC roots, and retained heap across multiple appropriate run/redeploy cycles.

### 6.2. Compute Does Not Guarantee Exactly-Once Execution

The `ClassValue.get` Javadoc allows multiple threads to compute `computeValue` concurrently and install one result; therefore compute must be safely repeatable, ideally a pure function over metadata and immutable policy. `remove(type)` racing with `get(type)` follows its own state rules.

`ConcurrentHashMap.computeIfAbsent` coordinates atomic map insertion; do not extrapolate the map's single-entry atomicity semantics onto `ClassValue`. When analyzing multi-threaded benchmarks, do not assert exactly one compute call if the API permits contention.

### 6.3. Close Must Coordinate with In-Flight Work

`close()` on a scoped cache does not automatically wait for requests currently holding references to finish. If multiple workers are using a plugin, the owner should stop accepting new work, wait for or cancel in-flight work per policy, and then release the cache and ClassLoader. Avoid tearing down a loader while an operation is still accessing plugin metadata.

## 7. A Testable Reflection Cache Design Process

1. **Measure the need:** measure repeated scan rate, Reflection time, total latency, class volume, and heap/metaspace before caching.
2. **Classify the data:** cache only validly reusable metadata; separate derived schemas, per-user data, and object values.
3. **Choose the owner:** request/session, plugin, application component, or JVM. Avoid an owner that outlives the data without a reason and cleanup.
4. **Choose the key:** `Class<?>` for class identity, adding policy/config generation when needed; never use class name alone across loaders.
5. **Choose the implementation:** scoped cache, `ClassValue`, bounded/TTL; check whether values point back to classes/loaders.
6. **Define expiration/invalidation:** clear in `close`, remove on policy change, plugin unload, or bounded eviction; specify behavior during concurrent loading.
7. **Measure/test:** hits/misses, entry count (if available), retained classloaders, memory usage, reload time, and post-shutdown behavior. Run multiple plugin unload/reload cycles, not just one.

Warning signs to investigate include: old-generation classloaders failing to disappear from GC roots after a plugin stops, entry counts growing on every reload, retained heap/metaspace climbing continuously, or caches holding fields/Methods of a loader no longer serving any requests.

## 8. Scenario-Based Selection Examples

| Scenario | Suitable Approach | Notes |
| --- | --- | --- |
| Scanning a few DTO types during one request | Cache within the request/session | Clean up right after the request or on close. |
| Immutable per-`Class` metadata used across many requests | `ClassValue` | Do not mix per-user auth/config; `computeValue` may run multiple times. |
| Hot-deployed plugins requiring runtime reload | Plugin-owned cache or per-class association | Remove registries, listeners, workers, and all other references to the old loader. |
| Schema depending on configuration version | Bounded cache key including version, or generation-scoped cache | Invalidate when version changes. |
| Shared cache at risk of encountering hundreds of thousands of types | Bounded cache with memory budget/TTL, or skip caching | Plain `ConcurrentHashMap` has no max size. |
| Per-tenant sensitive data | Do not store in a JVM-wide metadata cache | Apply redaction/permissions per request. |

## 9. Lifecycle Bugs to Catch in Code Review

| Symptom | Analysis | Action |
| --- | --- | --- |
| Global cache grows entries on every plugin reload | Likely retaining old-generation metadata | Scope owner per plugin/generation; evict on unload |
| Policy updated but metadata stays stale | Key lacks policy version or invalidation is missing | Versioned keys/snapshots and explicit switchover workflow |
| `close()` runs while requests still use metadata | Stale references remain in in-flight work | Block new work, wait/cancel old work, then clean up owner |
| Bounded cache expires, yet security data is still wrong | TTL does not guarantee immediate invalidation when permissions change | Enforce permissions per request or invalidate immediately |
| Chose `ClassValue` but need `clearAll()`/TTL | API does not provide those operations | Choose another owner/cache policy or manage instance/generation |
| `ConcurrentHashMap` assumed to be capacity-bounded | Thread-safe does not mean bounded | Add separate eviction/memory budget |
| Ran GC once to conclude there is no leak | GC/class unloading has no guaranteed timing | Track GC roots and retained loaders over multiple cycles |

Do not validate cache safety solely by hit rate. Also test schema/tenant policy changes, plugin reloads, exceptions inside compute, concurrent close, and live references remaining after cleanup.

## 10. Self-Check Exercises

1. Add a `Receipt` class to the program and call `GLOBAL.computeIfAbsent(Receipt.class, ...)`. How does the global map's size change? Does it automatically remove entries when the class is no longer used?
2. Remove the `PER_CLASS.remove(type)` line and predict `SCANS`. When adding multiple threads, what can cause the compute count to differ?
3. Call `InspectionSession.fieldNames` after `close()`: why does the program proactively reject it?
4. Design a case where two loaders A/B load a class with the same binary name. Why is a `getName()` key wrong, whereas `Class<?>` suffices to distinguish them?
5. Draw the reference graph of `WeakHashMap<Class<?>, List<Field>>` and explain why the key might still not be collected.
6. A schema-export tool has per-tenant policies and supports automatic plugin reloads: pick which cache type to use for raw metadata, which for per-user views, and the exact invalidation points.
7. Propose a stress test loading/unloading a plugin for 100 cycles. Monitor old loaders via heap/GC roots and cache entries; if retained loaders increase, which owners besides the cache should you inspect?

**Self-assessment:** Whenever a cache uses `Class<?>`/`Method`/`Field` as key or value, can you identify **its owning unit, lifetime limit, invalidation point, which loaders its keys may point to, and whether data becomes wrong when policies change**? If not, an unbounded JVM-wide cache is an incomplete design.

## 11. Official References

- [Java SE 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html) — `get`, `computeValue`, `remove`, and contention.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getDeclaredFields`, `getClassLoader`, and class identity.
- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html) — declaring class, metadata.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) — atomic map operations, `computeIfAbsent`.
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) — weak keys, strong values, and reference cycles.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — defining classes through loaders.