# ClassValue: Storing Computed Data Per Class in Java

## 1. The Problem: Caching Metadata Attached to a Runtime Class

In Java Reflection, operations such as `getDeclaredMethods()`, `getDeclaredFields()`, reading annotations, or analyzing class structure may be repeated many times. If every request rebuilds the metadata list and the lookup table from method names to `Method` objects, the program wastes computation and memory allocations.

A common option is creating a `Map<Class<?>, Metadata>`:

```java
// Illustrative example, not a complete solution:
// private static final Map<Class<?>, Metadata> CACHE = ...
Metadata metadata = CACHE.get(type);
```

However, with a map using **strong keys** that lives for the lifetime of the application, the `Class<?>` key can retain references to classes and classloaders of plugins/modules that the program has stopped using. Synchronizing computation, avoiding duplicate builds, and handling class unloading also become the cache author's responsibility.

**`java.lang.ClassValue<T>`** is designed for associating **one value of type `T` with each `Class<?>` object**. You define how to compute the value via `computeValue(Class<?> type)` and retrieve it via `get(type)`. The JVM/JDK manages the association from each `Class` to its corresponding value for each `ClassValue`.

Example use cases:

- Caching the list of methods or fields per class for serialization/binding/dispatch.
- Storing parsed annotation metadata per type.
- Storing codecs, descriptors, or configuration derived **solely from the class**, not from a specific object.
- Reducing repeated Reflection analysis in libraries/frameworks that encounter many classes and classloaders.

`ClassValue` does not create an actual field in class bytecode, does not modify `Class<?>`, does not invoke business methods on its own, and is not a mechanism for storing state **per object instance**.

## 2. Core API and Key Scope

Outline of the key members of `ClassValue<T>`:

```java
public abstract class ClassValue<T> {
    protected ClassValue();
    protected abstract T computeValue(Class<?> type);
    public T get(Class<?> type);
    public void remove(Class<?> type);
}
```

This is an **illustrative signature**, not a user-defined class; use the JDK implementation via `java.lang.ClassValue`.

| API | Role | Notes |
|---|---|---|
| `new ClassValue<T>() { ... }` | Creates a cache instance with a specific computation function | Must override `computeValue` |
| `computeValue(Class<?> type)` | Computes data for a class when needed | May be called more than once for the same class under contention |
| `get(Class<?> type)` | Returns the value currently bound to `(ClassValue instance, Class<?>)`; triggers computation if absent | Avoids manually managing a `Map<Class<?>,T>` |
| `remove(Class<?> type)` | Removes the value bound to a specific class so subsequent reads can recompute | Affects only **one class in one ClassValue**; there is no whole-cache clear operation like `Map.clear()` |

Example call:

```java
ClassValue<String> simpleNames = new ClassValue<>() {
    @Override
    protected String computeValue(Class<?> type) {
        return type.getSimpleName();
    }
};

System.out.println(simpleNames.get(String.class)); // String
System.out.println(simpleNames.get(Integer.class)); // Integer
```

This snippet is runnable inside a Java method body; there is no need to instantiate `String` or `Integer` because the key is the **runtime class**, not an object.

### The Effective Key Pair Consists of Two Identities

Picture a logical lookup table:

```text
(ClassValue A, Alpha.class) --> value A/Alpha
(ClassValue A, Beta.class)  --> value A/Beta
(ClassValue B, Alpha.class) --> value B/Alpha
```

Each `ClassValue` instance has an independent value space. Calling `get(Alpha.class)` on `ClassValue A` does not share a result with calling the same on `ClassValue B`. At the same time, two instances of the same class `Alpha` share the **class key** when fetching metadata through the same `ClassValue`.

## 3. Lifecycle: Lazy Computation, Reuse, Removal, and Recomputation

On a single thread, the basic flow is:

1. Create a `ClassValue<T>` instance with a `computeValue` implementation.
2. The first `get(Alpha.class)` has no cached value: calls `computeValue(Alpha.class)` to produce a candidate value and binds the selected value.
3. Subsequent `get(Alpha.class)` calls, while the entry remains valid, return the cached value without repeating Reflection analysis.
4. `get(Beta.class)` uses a different class key: computes a separate value for `Beta`.
5. `remove(Alpha.class)` removes the existing association for `Alpha` in **that** `ClassValue` instance.
6. `get(Alpha.class)` after removal can run `computeValue` again and install a new value; `Beta`'s value is unaffected.

```text
                        ClassValue<List<String>>
                                 |
                 +---------------+---------------+
                 |                               |
             Alpha.class                     Beta.class
                 |                               |
        computeValue(Alpha)              computeValue(Beta)
                 |                               |
          [hello, reset]                        [size]
                 |                               |
       get(Alpha) reuse                  get(Beta) reuse
                 |
          remove(Alpha)
                 |
         get(Alpha) recompute
```

Unlike `Map.computeIfAbsent`, `ClassValue` attaches data alongside the `Class` object and is designed around class/classloader lifecycles. It does not expose map operations such as `entrySet()`, `keySet()`, `put()`, or `clear()`.

## 4. Standalone Runnable Java 17+ Example, Deterministic Output

Create the file **`ClassValueDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueDemo {
    static class Alpha {
        public void hello() {}
        private void reset() {}
    }

    static class Beta {
        public int size() { return 42; }
    }

    private static final AtomicInteger COMPUTES = new AtomicInteger();

    private static final ClassValue<List<String>> METHOD_NAMES = new ClassValue<>() {
        @Override
        protected List<String> computeValue(Class<?> type) {
            COMPUTES.incrementAndGet();
            return Arrays.stream(type.getDeclaredMethods())
                    .map(Method::getName)
                    .sorted()
                    .toList();
        }
    };

    public static void main(String[] args) {
        List<String> first = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha: " + first);

        List<String> again = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha reused: " + (first == again));

        System.out.println("Beta: " + METHOD_NAMES.get(Beta.class));
        System.out.println("computeValue calls: " + COMPUTES.get());

        METHOD_NAMES.remove(Alpha.class);
        List<String> refreshed = METHOD_NAMES.get(Alpha.class);
        System.out.println("Alpha refreshed: " + refreshed);
        System.out.println("same list after remove: " + (first == refreshed));
        System.out.println("computeValue calls after remove: " + COMPUTES.get());

        ClassValue<String> CLASS_NAMES = new ClassValue<>() {
            @Override
            protected String computeValue(Class<?> type) {
                return type.getSimpleName();
            }
        };
        System.out.println("another ClassValue: " + CLASS_NAMES.get(Alpha.class));
    }
}
```

Compile with Java 17 or newer (the `--release 17` flag confirms the code only needs APIs available in Java 17):

```bash
javac --release 17 ClassValueDemo.java
java ClassValueDemo
```

Verified stdout:

```text
Alpha: [hello, reset]
Alpha reused: true
Beta: [size]
computeValue calls: 2
Alpha refreshed: [hello, reset]
same list after remove: false
computeValue calls after remove: 3
another ClassValue: Alpha
```

**Line-by-line analysis:**

- `computeValue` receives the requested `Class<?>` and calls `getDeclaredMethods()` to get directly declared methods (including private ones). Results are sorted by name with `sorted()` before printing, avoiding reliance on Reflection order, which is not guaranteed.
- Two consecutive `METHOD_NAMES.get(Alpha.class)` calls return **the same `List` reference** in this single-threaded example, so `first == again` is `true`.
- `Beta.class` is a different key from `Alpha.class`, so it is computed separately. Total `computeValue` calls reach `2`.
- After `remove(Alpha.class)`, `get(Alpha.class)` computes a new list. Even though the contents match, they are **two distinct list instances**, so `first == refreshed` is `false`.
- Recomputation increments the counter from `2` to `3`; `Beta` retains its value.
- `CLASS_NAMES` is a different `ClassValue` instance managing class name strings; it shares nothing with `METHOD_NAMES` even for the same `Alpha.class` key.

This example intentionally runs single-threaded. **Do not treat the `computeValue` call count in this example as a guarantee that in a multi-threaded program each class is always computed only once.** The next section explains the difference.

## 5. Concurrency: Do Not Assume `computeValue` Runs Exactly Once

When multiple threads call `get(type)` concurrently before a value is cached, **multiple concurrent invocations of `computeValue(type)` can occur**. The JDK installs/retains only one winning value for the class in steady state; competing computations may be discarded. Thus, `ClassValue` eliminates manual locking around cache lookup, but **does not turn `computeValue` into an “exactly-once initializer”**.

This leads to several principles:

- Make `computeValue` **self-contained and deterministic** for `type`, ideally side-effect-free. Scanning metadata and building a new descriptor fits better than opening connections, writing files, or charging money.
- If `computeValue` has side effects or external resources, do not rely on `ClassValue` to ensure single execution. Use dedicated resource-management/idempotency mechanisms.
- If the cache returns a **mutable** object, thread safety of that object itself remains the application's responsibility. `ClassValue` does not automatically make a cached `HashMap` thread-safe.
- For immutable metadata, prefer `List.copyOf(...)`, `Map.copyOf(...)`, or immutable records/value objects. For instance, `Stream.toList()` since Java 16 produces a list that cannot be modified with `add/remove/set`.
- If computation is extremely heavy and many threads contend on one class, measure and design synchronization in a dedicated computation layer; do not infer from `get` that computation only runs once.

When `computeValue` throws an exception, the `get` call performing that computation propagates it; do not treat an error outcome as a cached valid descriptor. Define clear retry/diagnostic policies instead of masking failures with invalid placeholder values.

**Do not recursively call `sameClassValue.get(type)` for the same key from inside `computeValue(type)`.** That easily causes infinite recursion or cyclic dependencies, because the result for that key has not yet been established.

## 6. Class Identity, Classloaders, and Class Unloading

In the JVM, a class's identity depends on **its binary name and defining classloader**. Two distinct classes can share the same name, such as `example.Plugin`, when defined by two different classloaders:

```text
Loader 1 -> example.Plugin (Class object A)
Loader 2 -> example.Plugin (Class object B)
```

`ClassValue.get(Class object A)` and `ClassValue.get(Class object B)` use **two distinct keys**. This is necessary for Reflection: methods, fields, annotations, and module access on the two classes may differ even though `getName()` is identical.

**Why is this helpful in plugin/redeploy environments?**

A structure such as `static ConcurrentHashMap<Class<?>, Metadata>` uses **strong keys**. When the map is long-lived and entries are not evicted, it can keep old plugin classes and classloaders from being garbage collected. `ClassValue` is designed to associate data with a `Class`'s lifecycle without making every `Class` a strong key in an application-managed global map.

This **does not guarantee class unloading will occur**: if the application or framework still holds strong references to the class, classloader, objects, threads, or metadata, they can still block collection. A `ClassValue` holding class-associated values cannot replace closing resources, stopping threads, or clearing other caches that retain the classloader.

Do not build keys using `type.getName()` in place of `Class<?>`: the same name in different loaders can represent two distinct runtime types. When caching Reflection metadata, preserving true identity is a **correctness** requirement, not just a memory concern.

## 7. Attaching Structured Reflection Data to Each Class

`ClassValue` often stores **parsed metadata**, not just method-name lists. For example, caching a class's directly declared `Method`s:

```java
// Illustrative snippet placed inside a class that uses Reflection.
private static final ClassValue<List<java.lang.reflect.Method>> METHODS =
        new ClassValue<>() {
            @Override
            protected List<java.lang.reflect.Method> computeValue(Class<?> type) {
                return java.util.Arrays.stream(type.getDeclaredMethods())
                        .sorted(java.util.Comparator.comparing(
                                java.lang.reflect.Method::toGenericString))
                        .toList();
            }
        };
```

`METHODS.get(SomeType.class)` returns the `Method` list associated with `SomeType.class`. This snippet only defines the field/cache; running it standalone requires an enclosing class providing `SomeType`. Any overload selection must check **both name and actual parameter types**: never blindly pick the first element with a matching name, because a class may contain multiple overloads, bridge methods, or synthetic methods.

A minimal lookup snippet:

```java
// Assumes variable 'type' is Class<?> and 'methodName' is String.
for (java.lang.reflect.Method method : METHODS.get(type)) {
    if (method.getName().equals(methodName) &&
            java.util.Arrays.equals(
                    method.getParameterTypes(),
                    new Class<?>[]{String.class})) {
        // Found a method accepting exactly one String.
        // Access must be checked before invoking.
        break;
    }
}
```

**Reflection note:** caching a `Method` does not mean that method is callable. `getDeclaredMethods()` can return private methods; `Method.invoke` still enforces visibility and module boundaries. `setAccessible(true)` can also be rejected if the module/package is not suitably opened. Metadata caching **grants no extra access permissions**.

If results depend on parameters other than the class—such as schema version, locale, user permissions, or tenant configuration—design keys/values accordingly. Use `ClassValue` only when the data belongs to the class; do not put short-lived user state into a value shared across requests.

## 8. Refreshing Caches, Configuration Changes, and `remove()`

`ClassValue.remove(Class<?> type)` deletes the cached association for **one class** in a specific `ClassValue` instance. The method returns `void`; it neither returns the previous value nor clears the entire cache.

Example:

```java
// Suppose metadata is computed by CACHED_METADATA:
CACHED_METADATA.remove(type);
// The next get(type) call can recompute:
Metadata refreshed = CACHED_METADATA.get(type);
```

This is an **illustrative snippet**, where `CACHED_METADATA`, `type`, and `Metadata` are application-defined. Calling `remove` makes sense when the cache policy detects that data must be recomputed. With multiple threads, check your application's synchronization guarantees for updates and queries; concurrent `get` calls can race with `remove`. Do not treat `remove` as a transactional barrier ensuring every thread immediately sees a single new data version.

If metadata is a function of **runtime-mutable configuration**, a cached entry built under old configuration can become stale. Consider three design options:

1. Ensure the data depends solely on the class and stays immutable throughout the association's lifetime, in which case `ClassValue` fits directly.
2. Call `remove` for classes needing refresh when an update occurs, while using application-level synchronization to coordinate concurrent reads/writes.
3. If config/version changes independently of the class and multiple versions are needed simultaneously, structure the **inner value** as a map/versioned descriptor or choose a cache with a composite key. A single `ClassValue` only has a one-dimensional `Class<?>` key.

There is no API to iterate over all currently stored `Class<?>` entries and call `remove` in bulk on a `ClassValue`. If you must manage sets of keys, the application needs its own registry, along with considering the risk of unintentionally keeping classloaders alive.

## 9. Comparing Caching Options

| Option | When Appropriate | Points of Caution |
|---|---|---|
| `ClassValue<T>` | One lazily computed value per runtime `Class<?>`, such as Reflection metadata | No key-iteration API; does not guarantee `computeValue` runs only once under concurrency |
| `ConcurrentHashMap<Class<?>, T>` | Need key iteration, custom eviction, specific cache policies; controlled class-set lifecycle | Strong keys can retain classes/classloaders; requires cleanup and compute policy design |
| `WeakHashMap<Class<?>, T>` | Need weak keys with application-managed synchronization | Not thread-safe by default; values referencing back to the class can defeat weak keys |
| Recompute with Reflection every time | Infrequent calls, small metadata, no evidence of bottleneck | Pays lookup/allocation cost on every call |
| Cache attached to object instance | Result depends on per-object state | Not a **per-Class** cache; `ClassValue` shares across the runtime class |

`ClassValue` is often a clean choice for libraries analyzing type metadata in multi-classloader environments. Still, do not assume it outperforms every map on every workload. Measure with benchmarks reflecting your class count, read frequency, contention, `computeValue` cost, and class-unloading requirements.

## 10. Common Design Mistakes

**1. Confusing per-class with per-object.** If two objects `a` and `b` have `a.getClass() == b.getClass()`, the same `ClassValue` returns the same value bound to that class. Do not store per-request/per-instance data here.

**2. Assuming `computeValue` runs exactly once.** Under contention, multiple candidate computations can run. Side effects must be controlled independently.

**3. Storing unsafe mutable data.** A cache returning an `ArrayList` or `HashMap` mutated across requests will cause races/corruption. Build immutable snapshots or deliberately use concurrent structures.

**4. Computing from external state without invalidation.** Values become stale when config, feature flags, schemas, or plugin registrations change. Define an explicit update policy.

**5. Calling `get` recursively for the same key from `computeValue`.** The result is not cached yet; this can lead to infinite loops/`StackOverflowError`.

**6. Assuming `remove` clears “all classes.”** `remove(type)` only removes the entry for `(ClassValue instance, type)` without affecting other classes or other `ClassValue` instances.

**7. Caching metadata to “bypass” accessibility rules.** `ClassValue` does not alter `private`, module openness, or exceptions thrown during invocation.

**8. Using string class names as identity.** Different classloaders can define two types with the same name; caching by `getName()` alone easily returns wrong metadata.

**9. Treating `ClassValue` as a cure-all for leaks from every source.** `ClassValue` does not automatically stop threads or free plugin loaders still held by other caches, thread-locals, or static references.

## 11. Self-Check Questions

1. Will two consecutive `cache.get(String.class)` calls on one thread, without removing the entry, run `computeValue` a second time? — Normally **no**, because the value is already bound and reused.
2. Do two different `ClassValue` instances calling `get(String.class)` share the same value? — **No**; each `ClassValue` manages its own associations.
3. Can you assume `computeValue` runs strictly once per class in a multi-threaded system? — **No**; multiple concurrent computations can occur.
4. Does `remove(Alpha.class)` delete the `Beta.class` entry? — **No**, as long as they are two distinct classes in the same `ClassValue`.
5. Do two plugins defining two `Class` objects with the same binary name under two different defining loaders share a key? — **No**; runtime class identity differs.
6. Does `ClassValue<List<Method>>` allow calling every private method of that class? — **No**; Java access control and module boundaries still apply.

## 12. Key Takeaways

- **`ClassValue<T>`** binds lazily computed data to each `Class<?>` and each `ClassValue` instance; well suited for caching Reflection metadata.
- **`get` reuses values**, `computeValue` produces values on demand, and `remove(type)` drops the binding for that exact class.
- **Thread-safety in the mapping mechanism does not mean compute-once**, nor does it make cached mutable objects thread-safe.
- **The classloader is part of identity**: `ClassValue` properly distinguishes same-named classes defined by different loaders and supports architectures compatible with class unloading.
- **Caching does not replace lifecycle design, invalidation, or access security**: cache only properly scoped data and handle config changes, resources, and access checks at the appropriate layer.