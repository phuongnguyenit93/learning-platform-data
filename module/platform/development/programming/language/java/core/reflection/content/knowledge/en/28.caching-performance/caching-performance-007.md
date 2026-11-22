# Thread Safety When Publishing and Using Cached Reflection Metadata

## 1. The Problem: A Valid Cache Published Improperly Still Fails

Reflection lets a program look up metadata at runtime, such as `Class<?>`, `Method`, `Constructor<?>`, `Field`, annotations, and generic signatures. Repeatedly looking up metadata on a hot path can be unnecessary; frameworks commonly **cache lookup results** and reuse them across multiple threads.

However, a cache has two independent responsibilities:

1. **Safe publication:** other threads must see the cached object **fully initialized**, never a half-constructed structure or stale missing values.
2. **Safe concurrent use:** after retrieving metadata from the cache, every thread must respect access permissions, receiver/argument types, and the synchronization rules of the **target object**. Shared metadata alone does not protect business state.

For example, a `Map<Class<?>, Method>` cache may return the right method to all threads. If threads call `Method.invoke(...)` on the same object holding an unsynchronized counter field, update results can still be wrong because of a data race on the **target object**.

The core idea is separating the layers:

```text
            [Thread A]              [Thread B]
                |                       |
                +----- read cache ------+
                          |
               safely published cache
                          |
                   Method / Field /
            MethodHandle / InvocationPlan
                          |
             permission + type checks
                          |
                   call on receiver
                          |
                  receiver's state
      (needs separate protection if shared)
```

**Do not** infer that “metadata is nearly immutable” means you can place it in any shared `HashMap` and read/write freely. Risks can lie in the cache structure, how values are built, the publication step, operations that mutate accessibility metadata, or the object on which the metadata is invoked.

## 2. Safe Publication in the Java Memory Model

Under the Java Memory Model (JMM), if one thread builds data and another thread reads it without a proper **happens-before** relationship, merely assigning a reference does not guarantee the reading thread sees all writes performed during construction.

An **unsafe** example, shown purely to point out the bug:

```java
// Bug illustration: DO NOT use as a multi-threaded cache.
static Map<Class<?>, Method> cache = new HashMap<>();

static void register(Class<?> type, Method method) {
    cache.put(type, method); // unsynchronized concurrent write
}

static Method lookup(Class<?> type) {
    return cache.get(type); // unsynchronized concurrent read
}
```

`HashMap` is not safe when multiple threads read and write concurrently without coordination. Even if one thread populates the cache before another thread starts reading, you still need a publication mechanism that guarantees visibility, such as class initialization, lock synchronization, or an appropriate concurrent primitive. Do not use `volatile HashMap` as a “fix” for updates: `volatile` on the **reference** does not make the map's `put/get` operations thread-safe.

Useful publication mechanisms:

| Mechanism | Associated Guarantee | When It Makes Sense |
| --- | --- | --- |
| Initializing a `static final` field during class initialization | The JVM guarantees threads see the properly initialized class state | Caches or immutable objects built during initialization |
| `synchronized` or `Lock` with a consistent protocol | Unlock happens-before a subsequent lock on the same monitor/lock | Caches with transactions or multiple coordinated updates |
| Writing/reading a `volatile` reference | A volatile write happens-before a subsequent volatile read of that field | Publishing an **immutable snapshot** by swapping the entire reference |
| `ConcurrentHashMap` | Concurrent API and visibility guarantees for values properly bound to keys | Dynamically growing caches accessed by key |
| `ClassValue<T>` | Binds lazily computed values per `Class<?>`, with multi-thread-safe access | Per-class metadata caches, especially with dynamic class loading/unloading |
| Immutable objects with `final` fields | Supports final-field semantics when constructed properly without `this` escaping the constructor | Cache values that do not need mutation after construction |

**`final` does not replace synchronization for mutable structures.** For example, `final List<Method> methods` only fixes the reference; if the underlying list is an `ArrayList` mutated concurrently, a race still exists. Prefer constructing all data in a local variable, converting it via `List.copyOf(...)`/`Map.copyOf(...)`, assigning it to a `final` field, and publishing through a safe primitive. Never let `this` or internal collections escape before the constructor finishes.

## 3. Choosing Cache Keys That Uniquely Identify Metadata

An underspecified cache key can return **wrong** metadata even when the map is completely thread-safe.

- `Class<?>` distinguishes the **actual runtime type**, including classloader identity. Two classloaders can define classes with the same binary name, yet they are two distinct `Class<?>` objects. Using only the string `type.getName()` as a global key can mix metadata from incompatible classes.
- When caching **multiple methods within one class**, the key must include the name, declared parameter types, static/instance distinction where applicable, and policies for overloads, bridges, and visibility. `getMethod("convert", String.class)` differs from `getMethod("convert", Object.class)`.
- A superclass field and a same-named subclass field can coexist; storing only `"id"` without the declaring class or lookup policy easily causes confusion.
- For constructors, the key includes the declaring class and parameter types. Constructors are not inherited.
- For `MethodHandle`, account for `MethodType` and the `Lookup` permissions at creation time; do not expose high-privilege handles as part of an uncontrolled public API.

Cache scope should match **lifecycle and access rights**: public read-only metadata caches can be shared broadly; private handles created with privileged `Lookup` require restricted sharing scope. Putting a handle into a cache does not erase JPMS rules, nor does it grant invocation permission to every end user of the application.

## 4. Prefer `ClassValue<T>` When Caching Per Class

`java.lang.ClassValue<T>` provides a way to attach lazily computed data to a `Class<?>` without manually maintaining a long-lived static `Map<Class<?>, T>`. This API is especially suited for serializers, frameworks, proxies, plugins, or Reflection tools with multiple classloaders.

Conceptual pattern:

```java
private static final ClassValue<Plan> PLANS = new ClassValue<>() {
    @Override
    protected Plan computeValue(Class<?> type) {
        return createPlan(type); // fully construct before publishing
    }
};

Plan plan = PLANS.get(SomeType.class);
```

This is an **illustrative pattern** without `Plan`/`createPlan` declarations; a complete example follows in the next section.

Key points:

- `get(type)` provides the value bound to the requested class. You do not need to lock a `HashMap` yourself on the read path.
- Under concurrent access, **`computeValue(type)` may be invoked multiple times**, even though a single value is ultimately installed for the mapping. Therefore, the cache builder must be safe to run repeatedly and must not trigger business side effects like “register one event per class” based merely on invocation count.
- Do not create and share an incomplete `Plan` early, and do not publish a reference to a map still being populated.
- `ClassValue.remove(type)` can drop a value when policy allows recomputation, but do not treat concurrent remove/get operations as an atomic update across all threads or as revoking `Plan` references threads already retrieved earlier.
- Compared to a static `ConcurrentHashMap<Class<?>, ...>`, `ClassValue` usually fits class/classloader lifecycles better. A static map holding `Class<?>` keys can **prevent a classloader from being unloaded** if there is no cleanup policy.

## 5. Complete Java 17+ Program: One Immutable Plan Shared by Many Threads

The program builds an immutable `InvocationPlan` holding a type's public `greet(String)` `Method`, cached per class using `ClassValue`. Multiple tasks run concurrently to retrieve the plan, each using its own receiver; `main` prints results in the order `Future`s were created so stdout is deterministic.

Create the file **`SafeReflectionCacheDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SafeReflectionCacheDemo {
    public static final class Greeter {
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    private static final class InvocationPlan {
        private final Method method;

        private InvocationPlan(Method method) {
            this.method = method;
        }

        String call(Object receiver, String argument)
                throws ReflectiveOperationException {
            return (String) method.invoke(receiver, argument);
        }
    }

    private static final ClassValue<InvocationPlan> PLANS =
            new ClassValue<>() {
                @Override
                protected InvocationPlan computeValue(Class<?> type) {
                    try {
                        Method method =
                                type.getMethod("greet", String.class);
                        return new InvocationPlan(method);
                    } catch (NoSuchMethodException e) {
                        throw new IllegalArgumentException(
                                "Requires public greet(String): "
                                        + type.getName(), e);
                    }
                }
            };

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 6; i++) {
                final int number = i;
                futures.add(pool.submit(() -> {
                    InvocationPlan plan = PLANS.get(Greeter.class);
                    Greeter receiver = new Greeter();
                    return plan.call(receiver, "friend " + number);
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac SafeReflectionCacheDemo.java
java SafeReflectionCacheDemo
```

Stdout:

```text
Hello, friend 1
Hello, friend 2
Hello, friend 3
Hello, friend 4
Hello, friend 5
Hello, friend 6
```

Why is this example safe?

1. The `PLANS` field is created during **class initialization**. Every thread uses the same `ClassValue` mechanism to obtain the plan for `Greeter.class`.
2. `computeValue` only looks up the public `Method` and constructs a complete `InvocationPlan`; it registers no side effects and remains valid if computed multiple times under contention.
3. `InvocationPlan` has a `final Method` field; there are no setters or collections mutated after publication. The program does not change `setAccessible` on the shared `Method`.
4. `ClassValue` coordinates the association; threads do not access an unsynchronized shared `HashMap`.
5. Each task creates its own `new Greeter()`. If `Greeter.greet` modified shared state, a safe cache alone would still **not** make the business call thread-safe.
6. Tasks may finish out of order, yet `futures` is iterated in **submission order**, so stdout lines appear ordered from 1 to 6.
7. `Future.get()` provides waiting/visibility guarantees: `main` processes each result only after the task completes; there is no need to sleep to “wait for data to appear.”

The example uses `getMethod` for a known public API. For private methods, other modules, complex overloads, or special access permissions, add appropriate handling policies; do not assume caching automatically solves access issues.

## 6. Using `ConcurrentHashMap` When Caching by Multiple Dynamic Keys

`ConcurrentHashMap` is often appropriate when keys are not just `Class<?>`, such as a `(class, method name, parameter type list)` tuple or per-operation config. It supports concurrent access and `computeIfAbsent` to bind values to keys:

```java
private static final ConcurrentMap<Class<?>, Method> METHODS =
        new ConcurrentHashMap<>();

static Method resolve(Class<?> type) {
    return METHODS.computeIfAbsent(type, key -> {
        try {
            return key.getMethod("greet", String.class);
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Requires greet(String): " + key.getName(), e);
        }
    });
}
```

This is an **illustrative snippet** requiring imports for `java.lang.reflect.Method`, `java.util.concurrent.ConcurrentMap`, and `java.util.concurrent.ConcurrentHashMap`; place it inside a class with access to those members.

`computeIfAbsent` computes the mapping for an absent key per the concurrent map contract; once a successful mapping exists, other threads can reuse it. However, **never design a mapping function assuming it “runs exactly once over the application's lifetime”**: if an entry is removed, computation throws an exception, returns `null`, or the cache is recreated, computation can run again.

A mapping function should:

- Be **short, self-contained, and free of business side effects**, returning a fully initialized object.
- Never recursively or overlappingly update the same map during computation; `ConcurrentHashMap` can reject recursive updates and throw `IllegalStateException`.
- Avoid I/O or long blocking operations because other threads may be blocked while the mapping updates.
- Return an immutable value or one with internal synchronization. **A concurrent map only protects the map structure and publication**, it does not make an `ArrayList` inside the value thread-safe.

**Do not cache failures by sneaking in `null`.** `ConcurrentHashMap` does not accept `null` keys or values; if the mapping function returns `null`, no mapping is recorded. If you want negative caching for missing lookups, define an explicit result type representing “not found” (such as an immutable status value) with explicit expiration and invalidation policies.

With static maps keyed by `Class<?>`, watch out for classloader leaks. If you primarily attach data per class, `ClassValue` is usually simpler and better aligned with class lifecycles.

## 7. The Trap of “Thread-Safe Map, Non-Thread-Safe Value”

Incorrect example:

```java
// Bug illustration: map is concurrent, but the ArrayList value is still mutable.
ConcurrentMap<Class<?>, List<Method>> cache =
        new ConcurrentHashMap<>();

List<Method> list = cache.computeIfAbsent(
        SomeType.class, type -> new ArrayList<>());
list.add(someMethod); // multiple threads adding to the same List -> race
```

The snippet above only illustrates an anti-pattern; `SomeType`, `someMethod`, and imports are omitted. `ConcurrentHashMap` protects putting/getting the list in the map, **it does not synchronize `ArrayList.add` calls** on the returned list.

A better approach for read-only metadata is **build completely, then publish**:

```java
List<Method> collected = new ArrayList<>();
// ... collect Methods into collected solely in the initializing thread ...
List<Method> immutableSnapshot = List.copyOf(collected);
// Publish immutableSnapshot via ClassValue, ConcurrentHashMap,
// volatile, or an appropriate synchronization primitive.
```

This is also a snippet, not a standalone program. `List.copyOf` creates a structurally unmodifiable list and does not expose `collected` as a mutable backing list. Note that it only freezes **the list of references**: if collection elements have mutable state mutated after publication, evaluate that separately.

When multiple related metadata groups exist, build **one snapshot object** containing all the maps/lists and publish them together via **a single reference**. Publishing each map individually easily lets a reader see “new-version method map, old-version field map” within the same operation.

## 8. Swapping Snapshots with `volatile` on Configuration Updates

A program can build a new metadata catalog and **swap the entire snapshot**. In a many-reader, few-writer model, reading a `volatile` field is a simple option:

```java
private volatile List<Method> methods = List.of();

void reload(Class<?> type) {
    List<Method> fresh = List.copyOf(
            java.util.Arrays.asList(type.getMethods()));
    methods = fresh; // publish the entire snapshot with a single volatile write
}

List<Method> currentMethods() {
    return methods; // a single volatile read
}
```

This is an illustrative snippet placed inside a class; import `Method` as needed. The `methods` field must be declared on the instance deliberately shared by threads.

Key points:

- `volatile` on the **snapshot reference** ensures reading threads see the snapshot published after the volatile write; there is no need to mutate the published list directly.
- Both old and new snapshots remain valid for threads that already grabbed a reference before the swap; swapping the reference does not “revoke” data already in a reader's hands.
- If multiple related fields must update together, bundle them into one immutable snapshot and swap **one** reference to avoid mixed data versions.
- If multiple writers concurrently compute snapshots by reading prior state and adding to it, `volatile` **does not** protect read-modify-write from **lost updates**. Use locks, `AtomicReference.compareAndSet`, or an appropriate version/generation mechanism.
- A thread that holds onto a snapshot for a long time can continue seeing older data. If stronger consistency is required (e.g., all calls after reload must use the new policy), define synchronization boundaries, versioning, and how in-flight operations are handled.

Do not hand-roll “double-checked locking” on non-`volatile` mutable references. For lazy per-class caches, `ClassValue` and `ConcurrentHashMap.computeIfAbsent` are generally clearer and less error-prone.

## 9. Using Shared Metadata: When Is It Safe?

### 9.1. `Method`, `Constructor`, and `Field`

Discovered metadata can be retained for reuse. Having multiple threads invoke `Method.invoke` through the same stably configured `Method` is normal. Even so:

- **Do not concurrently toggle `setAccessible(true/false)`** on a shared `AccessibleObject` while other threads are using it. Changing accessibility is a mutation affecting permissions/access checks; resolve permissions before publication or use a valid `MethodHandles.Lookup` with an explicit permission scope.
- `Field.get/set` accesses **actual field state**. If multiple threads read/write the same field on the same object, consider `volatile`, locks, or `VarHandle` access modes; caching `Field` does not protect the read/written values.
- `Constructor.newInstance` creates an instance; the constructor itself may perform side effects or use shared resources. Thread-safety of the `Constructor` cache does not make the target constructor thread-safe.
- Metadata for classes loaded from plugins can depend on classloader/module context. Access permissions may differ for different callers; do not expose privileged handles/metadata outside access boundaries.

### 9.2. `MethodHandle` and `VarHandle`

`MethodHandle` represents a bound, typed operation; `VarHandle` represents a variable and its access modes. They are suitable to share for their intended purposes, yet:

- The receiver, array, or object a handle operates on **can still be mutable and shared**.
- Plain `VarHandle.get`/`set` does not equal `getVolatile`/`setVolatile` or `compareAndSet`. Choose access modes matching the memory contract and field kind.
- Never use a private-privileged handle as a “backdoor” around business authorization checks. Handle creation privileges, module permissions, and end-user authorization are distinct layers.
- Binding a receiver to a handle (`bindTo`) can cause the cache to strongly retain the receiver object and classloader, affecting lifecycle, and can make multiple threads accidentally mutate the same instance. Whenever possible, cache unbound handles and pass the receiver at the call site.

### 9.3. Annotations and Preprocessed Metadata Sets

When reading annotations and building mapping schemas, store an **immutable descriptor** holding names, `MethodType`/field types, parameter lists, flags, and validation results. If it holds `Map`/`List`, use immutable copies; never return internal mutable collections directly to callers.

Runtime `Annotation` results should not be treated as immutable business configuration over time if the application also reads external config files or dynamic policies. Distinguish class metadata from **reloadable configuration state**.

## 10. Cache Lifecycle, Refreshing, and Classloaders

A cache can be thread-safe yet still wrong because it retains metadata **too long** or uses underspecified keys.

- Key by `Class<?>` (or `ClassValue`) instead of class name alone; the same binary name in two classloaders can be two distinct types.
- A static `ConcurrentHashMap<Class<?>, ...>` cache holds strong references to keys/values. A plugin classloader may fail to unload if entries are not removed and values retain the class.
- When you only need values tied to each class, `ClassValue` reduces lifecycle management burden.
- If metadata depends on **configuration version**, annotation scan policies, feature flags, or tenant permissions, keys or snapshots must include that version/policy. `ClassValue` keyed only by class does not separate policy versions automatically.
- When refreshing, clearly define when the new snapshot takes effect, how threads holding the old snapshot behave, and when resources tied to the old snapshot can be released.
- Do not assume calling `ClassValue.remove(type)` forces every thread to stop using the old value; `remove` only affects the mapping managed by `ClassValue`.

For long-running servers, monitor cache size, classloader counts, hits/misses, metadata initialization time, and invalidation correctness. Do not add a global cache just because reflective lookup “looks slow”; measure on the actual path.

## 11. Common Multi-Threading Bugs and Fixes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Static `HashMap` with `put/get` from multiple threads | Structural map races and visibility bugs | `ConcurrentHashMap`, `ClassValue`, or consistent synchronization |
| Partially constructing an object before inserting into cache | Readers observe incomplete state | Build locally in full, publish immutable value |
| `final Map` while still calling `put` concurrently | `final` only fixes the reference, not internal state | Immutable map or concurrent map |
| `volatile Map` while mutating a `HashMap` | `volatile` does not protect map internals | Swap immutable snapshots or use a concurrent map |
| `computeIfAbsent` computing and updating the same map | Recursive updates, blocking, and nondeterministic side effects | Keep compute pure, fast, and avoid touching the map from the mapping function |
| Assuming `ClassValue.computeValue` runs once | Can compute concurrently multiple times | Keep computation idempotent and side-effect-free |
| Caching by class name string | Two classloaders defining the same name get mixed | Key by `Class<?>` or `ClassValue` |
| Caching `Method` and toggling `setAccessible` during use | Permissions/access checks mutate at runtime | Configure before publication; avoid toggling shared metadata |
| Thread-safe metadata ⇒ thread-safe target method | Receiver state and side effects still race | Synchronize business objects or design them immutable |
| Caching handles bound with `bindTo(receiver)` long-term | Retains receiver and possibly classloader; multiple threads mutate shared state | Cache unbound handle and pass receiver on call |
| Publishing multiple maps at separate times | Readers can see half new version, half old version | Bundle into one immutable snapshot for atomic swap |
| Not clearing cache on plugin unload | Strong references retain `Class<?>`/loader | `ClassValue` or lifecycle/eviction policy |

Do not overuse a global lock spanning entire business operations just to guard a cache. Separate **synchronization for metadata lookup/population** from **synchronization for operations on the target object**. That keeps contracts clear and avoids coarse lock contention.

## 12. Design and Verification Process

For a metadata cache shared across multiple threads:

1. **Define what is cached**: only `Class/Method/Field/Constructor`, or also handles, accessors, parsers, maps, and policies.
2. **Define the identifying unit**: `Class<?>`, member signature, classloader, configuration version, and lookup permissions.
3. **Construct complete values**: validate members, normalize descriptors, and copy collections into immutable snapshots before publishing.
4. **Choose a publication mechanism**: `ClassValue` for per-class; `ConcurrentHashMap` for dynamic multi-key lookups; `static final`/class initialization for fixed values; `volatile` for atomic whole-snapshot swaps.
5. **Separate cache safety from receiver safety**: identify which threads may touch the same target object, mutable fields, and external side effects.
6. **Specify mutation policy**: never toggle shared `AccessibleObject`s arbitrarily; if reloadable, define versions and transition rules.
7. **Test under contention**: cold-starting many threads on the same class, multiple classloaders, cache misses/exceptions, swapping snapshots during reads, checking stale values, and ensuring code never relies on `computeValue` running once.
8. **Measure performance and lifecycle**: duplicate lookup counts, contention, allocations, memory retention, and classloader unloading. Do not guess performance solely from API choice.

### Self-Check Questions

1. Why is `static final HashMap` still unsafe if threads write to the map after initialization?
2. Does `volatile` on a reference to a `HashMap` make concurrent `HashMap.put`/`get` safe?
3. Why should `ClassValue.computeValue` avoid side effects even though caching is per `Class<?>`?
4. In `SafeReflectionCacheDemo`, why is stdout deterministic even though tasks run on four worker threads?
5. If a shared `Method` is retained while multiple threads invoke it on the same unsynchronized counter, does the cache protect the counter?
6. How does `Class<?>` differ from the `getName()` string when two plugin classloaders define classes with the same name?
7. Why can `ConcurrentHashMap<Class<?>, ArrayList<Method>>` still fail if multiple threads modify the same list?
8. When hot-reloading a policy, does replacing three separate `volatile Map` fields guarantee a reader always sees the same version?
9. If you cache `MethodHandle.bindTo(receiver)`, what happens to the receiver's lifetime and the safety of accessing its state?

**Takeaway:** A sound Reflection cache requires **fully constructed values, publication with proper happens-before guarantees, accurate keys and lifecycles**, and safe usage policies for receivers and business state. `ClassValue` and `ConcurrentHashMap` handle metadata access coordination well; they do not replace synchronization on the target objects being invoked.