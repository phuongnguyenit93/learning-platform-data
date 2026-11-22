# 19.5 Using ClassValue and Identifying References That Keep Classes or Class Loaders Alive

## 1. The problem: caching per Class without keeping plugins/class loaders forever

When writing a reflection framework, serializer, dependency injector, ORM, dynamic dispatcher, or runtime class-compiling runtime, a program often has to compute metadata once and then reuse it for each **`Class<?>`**:

- Parsed field/method lists, serialization/deserialization plans.
- Looked-up `MethodHandle` and `VarHandle` instances.
- Dispatch tables, accessors, converters, or schemas.
- Configuration specific to a Java type.

The intuitive approach is to use a static cache:

```java
// Anti-pattern illustration: global variable outlives plugin class loader.
static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();
```

If this map resides in a class of the **application loader** that lives for the entire process lifetime, each `Class<?>` acting as a **strong key** can keep the defining class loader alive. In a plugin-reloading system, after each redeployment we have a new loader, even with the same class name. The old global cache retains the old-version `Class<?>` objects; the number of loaders/classes and metaspace can keep growing.

Java provides **`java.lang.ClassValue<T>`** to lazily associate a computed value with each `Class<?>` object, without needing to maintain a global map containing strong keys to every class. This is an especially useful tool when **classes can be unloaded**.

**Core of the lesson:** you must understand both **the ClassValue mechanism** and **the reference paths that keep a class/class loader alive**. Simply switching from `Map<Class<?>,T>` to `ClassValue<T>` does not cure every memory leak; a thread, static singleton, listener, or value holding a reference elsewhere can still prevent unloading.

### Objectives

After this lesson you will be able to:

1. Use `ClassValue.computeValue`, `get`, `remove`; distinguish lazy initialization, per-class identity, invalidation, and thread-safety.
2. Understand why `computeValue` **can run multiple times concurrently** even though only one result is installed for the same class, and why non-repeatable side effects should not be placed in it.
3. Compare strong `Map<Class<?>, ...>`, `WeakHashMap<Class<?>, ...>`, and `ClassValue<T>` regarding loader retention.
4. Identify the chain **GC root → strong object → Class/instance/MethodHandle/ClassLoader → defining loader → class metadata**.
5. Diagnose common traps: thread context class loader, `ThreadLocal`, executor thread, callback/listener, static registry, class-keyed cache, method handles, and cross-loader values.
6. Read indicators using `jcmd VM.classloader_stats`, `VM.metaspace`, `GC.class_histogram`, heap dump, JFR/class unloading logs; do not claim unloading just because of `System.gc()`.
7. Design an explicit lifecycle when unloading/redeploying plugins or generating many dynamic classes.

This lesson uses Java **17+** and three standalone examples tested with `javac --release 17`.

## 2. Class identity, class loaders, and why related leaks happen

### 2.1. One binary name can represent multiple Class objects

For a **named class**, the JVM distinguishes runtime types by **binary name and defining class loader**. For example, two child loaders `L1` and `L2` both define bytes with the binary name `plugin.Widget`:

```text
Class<?> A = Class.forName("plugin.Widget", false, L1);
Class<?> B = Class.forName("plugin.Widget", false, L2);

A.getName().equals(B.getName())  -> true
A == B                           -> false
A.getClassLoader() == L1         -> true
B.getClassLoader() == L2         -> true
```

This is an **illustrative diagram**, not a standalone Java file. These two classes can carry the same name but have different class identities; they have metadata, static state, methods, and access permissions tied to their own loader context.

A cache keyed by **class name string** can mix two different versions and return wrong metadata. A cache keyed by `Class<?>` solves type correctness, but if that cache belongs to a very long-lived root and holds **strong keys**, it can prevent the old loader from being reclaimed.

### 2.2. GC root and class retention path

A root such as a static field in an application class, a live thread, a JNI reference, or a stack variable of a running thread can indirectly keep a class loader alive:

```text
GC root: static field of application loader
        |
        v
ConcurrentHashMap<Class<?>, Metadata>
        |
        +--- strong key ---> Class<plugin.Widget> (loader L1)
                              |
                              v
                         defining loader L1
                              |
                              v
                       plugin's classes/metadata
```

**This is a real retention path**, not just a phenomenon of "Java cache consuming memory". Class objects are linked to their defining class loader; when a class loader is still reachable under JVM rules, the classes it defines generally cannot be unloaded independently as expected for a normal loader.

Note: drawing only the direction `Class → ClassLoader` is not enough to analyze every implementation; metadata/objects/class-loader data have internal JVM mechanisms. However, to **find roots in a heap dump**, the chain from a static map or thread to a class/plugin loader is very useful evidence.

### 2.3. Unloading differs from instance GC

- **Heap object GC:** an object instance that is no longer reachable can be reclaimed.
- **Class unloading:** the JVM is permitted to reclaim a class's metadata when reachability and loading context conditions are satisfied.
- **Class-loader unloading:** the loader and its associated classes/metadata can be reclaimed when there are no strong references keeping them alive, subject to appropriate internal conditions.

A plugin may have no business instances left yet still **cannot be unloaded** if there is still a `Class<?>` in a cache, a live thread created by the plugin, `Thread.contextClassLoader`, a method handle, a callback, or a thread-local value referencing the plugin. Therefore, seeing the heap instance count drop is **not sufficient** to confirm class loader/metaspace release.

**There is no contract that calling `System.gc()` will unload classes immediately**; the runtime may ignore the GC request or choose another time. Metaspace metrics not dropping after a single GC also **do not by themselves prove** a leak, because the JVM may retain committed regions for reuse.

## 3. What is ClassValue<T>?

`ClassValue<T>` is an abstract class available since Java 7 that supports **associating a value T with each Class object** lazily. You define how to compute it via:

```java
ClassValue<Metadata> metadata = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return analyze(type);
    }
};
```

This snippet is **illustrative**, assuming `Metadata` and `analyze(Class<?>)` are already defined. Whenever metadata for a class is needed:

```java
Metadata info = metadata.get(SomeClass.class);
```

Conceptually, we want:

```text
ClassValue<Metadata> METADATA
    get(Class A) ---> Metadata for A itself
    get(Class B) ---> Metadata for B itself
    get(Class A) ---> reuse Metadata already associated with A
```

Importantly, we do **not** put all Class keys into a global `ConcurrentHashMap` ourselves. The API manages the association per `Class<?>`, which fits systems with changing classloader lifecycles.

### 3.1. Three essential methods

| Method | Meaning | Behavior to note |
| --- | --- | --- |
| `protected T computeValue(Class<?> type)` | How to compute metadata when no matching association exists. | May run multiple times due to a race or after `remove`; an exception does not record a new value. |
| `T get(Class<?> type)` | Reads the value corresponding to the class; computes lazily if needed. | Installs the value **atomically**; multiple threads may compute, but one value wins and is returned. |
| `void remove(Class<?> type)` | Removes this ClassValue's association with **one class**. | Subsequent `get` may recompute; need to consider races with other `get` calls. |

`get(null)` and `remove(null)` throw `NullPointerException`. `type` can be an **interface, array, primitive type** (e.g., `int.class`), or `void.class`, not only ordinary application classes.

Each **`ClassValue` object** creates a separate association space. Two different `ClassValue` instances can compute two kinds of metadata on the same `Class<?>` without data colliding.

### 3.2. ClassValue is not a general-purpose Map

There are no public `put(class, value)`, `size()`, `entrySet()`, or `clearAll()` APIs. `ClassValue` produces values via `computeValue` and invalidates per class via `remove`. It is optimized for a specific case: **memoization/caching per Class**.

Therefore, do not choose `ClassValue` when business logic needs to list **all classes ever seen**, count global keys, or perform atomic operations across the whole map. For those goals, a dedicated registry with an explicit lifecycle and retention policy is needed — but avoid long-lived strong Class keys if the classes come from short-lived loaders.

## 4. Lazy initialization, value identity, and invalidation

On the first `ClassValue.get(A.class)`, `computeValue(A.class)` is called to compute the value. If it succeeds, the API **atomically installs** the association. Subsequent `get(A.class)` calls normally return **the exact T object that was installed** until `remove(A.class)` occurs. If `T` is immutable, this pattern is especially easy to use.

`remove(A.class)` does not modify the contents of a value object returned earlier. It only removes the current association in the `ClassValue`; code holding an old reference can still use the old value. The next `get(A.class)` will compute a different value (if `computeValue` creates a new one).

Do **not** use `remove` as a method to close resources or revoke `MethodHandles` already held by others: it does not call `close()` on the value, does not delete metadata copies in other maps, and does not automatically prevent threads that obtained the value earlier from continuing to use it.

### 4.1. Java 17 Example 1 — per-class cache and remove

Create file **`ClassValueBasicsDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueBasicsDemo {
    static final class Alpha { }
    static final class Beta { }

    record Metadata(String name, int generation) { }

    static final AtomicInteger BUILDS = new AtomicInteger();

    static final ClassValue<Metadata> INFO = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            return new Metadata(
                    type.getSimpleName(),
                    BUILDS.incrementAndGet());
        }
    };

    public static void main(String[] args) {
        Metadata first = INFO.get(Alpha.class);
        Metadata again = INFO.get(Alpha.class);

        System.out.println("first name: " + first.name());
        System.out.println("same value: " + (first == again));
        System.out.println("builds after repeated get: "
                + BUILDS.get());

        Metadata beta = INFO.get(Beta.class);
        System.out.println("beta name: " + beta.name());
        System.out.println("builds for two classes: "
                + BUILDS.get());

        INFO.remove(Alpha.class);
        Metadata refreshed = INFO.get(Alpha.class);
        System.out.println("after remove new instance: "
                + (refreshed != first));
        System.out.println("refreshed generation: "
                + refreshed.generation());
        System.out.println("beta unchanged: "
                + (INFO.get(Beta.class) == beta));

        try {
            INFO.get(null);
        } catch (NullPointerException expected) {
            System.out.println("null class: rejected");
        }

        System.out.println("primitive name: "
                + INFO.get(int.class).name());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ClassValueBasicsDemo.java
java ClassValueBasicsDemo
```

Verified stdout:

```text
first name: Alpha
same value: true
builds after repeated get: 1
beta name: Beta
builds for two classes: 2
after remove new instance: true
refreshed generation: 3
beta unchanged: true
null class: rejected
primitive name: int
```

**Analysis:**

1. On the first get for `Alpha`, `computeValue` creates `Metadata("Alpha",1)`. Getting again does not recompute, so `first == again` returns true.
2. `Beta` has its own `Class` object, leading to a separate association and a second computation.
3. `INFO.remove(Alpha.class)` invalidates only the association for `Alpha`. The next get creates a new `Metadata` (generation 3); `Beta` still returns the exact old object.
4. `get(null)` throws `NullPointerException`; `int.class` is also a valid key and has simple name `int`.
5. The output has specific sequence numbers because **this example runs sequentially on a single thread**. Do not generalize this into "computeValue is always called exactly once per Class" when concurrency is involved.

### 4.2. Using multiple ClassValues for one Class

You can have an independent `ClassValue<SerializationPlan>` and `ClassValue<DispatchTable>` for the same `Order.class`. That is better than bundling all metadata fields into a single global Map and having to manage multiple value types in the same entry.

For metadata that depends on **configuration changing over time**, `ClassValue` only associates a value with `Class<?>`; it **does not automatically know** that external configuration has changed. When a config change event occurs, you must invalidate the corresponding association via `remove(type)` (or design your own versioning), and decide how callers still holding old metadata will handle it.

## 5. Concurrency: computeValue can run multiple times

According to the Java 17 Javadoc, when multiple threads concurrently call `get(C)` while no value is present yet:

- **Multiple threads may call `computeValue(C)` at the same time**.
- **Installing the association** is performed atomically.
- One computed value is chosen and returned to the competing readers; the remaining values **may be discarded**.
- Without `remove`, subsequent readers read the installed association.
- If `computeValue` throws an exception during a corresponding `get`, no value is recorded for that failed computation; other `get` calls can still recompute.

Therefore **do not place side effects requiring exactly-once execution** inside `computeValue`:

```java
// Anti-pattern illustration in computeValue:
// chargeCustomerCard(); // must not assume it runs only once!
// registerGlobalListener(); // may register repeatedly during a race
// startThread(); // may create "extra" threads holding the class loader
```

Actions such as calling a billing API, registering a callback, opening a native resource, or starting a thread need their own lifecycle/transaction. `computeValue` should be a **repeatable, immutable metadata** construction that does not affect external state or has a mechanism to discard redundant results if truly necessary.

Do not equate **atomic installation** with **single execution** of the computation.

### 5.1. Java 17 Example 2 — multiple readers receive the same value

Create file **`ClassValueConcurrentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassValueConcurrentDemo {
    static final class Target { }

    static final class Metadata {
        final int sequence;
        Metadata(int sequence) {
            this.sequence = sequence;
        }
    }

    static final AtomicInteger COMPUTATIONS = new AtomicInteger();

    static final ClassValue<Metadata> CACHE = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            int id = COMPUTATIONS.incrementAndGet();
            try {
                Thread.sleep(30);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            return new Metadata(id);
        }
    };

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Metadata>> futures = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    return CACHE.get(Target.class);
                }));
            }

            start.countDown();
            Metadata installed = futures.get(0).get();
            boolean allSame = true;

            for (Future<Metadata> future : futures) {
                allSame &= (future.get() == installed);
            }

            System.out.println("readers same published object: "
                    + allSame);
            System.out.println("subsequent get agrees: "
                    + (CACHE.get(Target.class) == installed));
            System.out.println("compute called at least once: "
                    + (COMPUTATIONS.get() >= 1));
            System.out.println("no remove occurred: true");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ClassValueConcurrentDemo.java
java ClassValueConcurrentDemo
```

Verified stdout:

```text
readers same published object: true
subsequent get agrees: true
compute called at least once: true
no remove occurred: true
```

**Points to note:**

- `CountDownLatch` helps the threads start close together, and `Thread.sleep(30)` is an illustrative operation to increase the chance of overlapping computations; it is **not** a required synchronization of `ClassValue` and does not guarantee any particular computation count.
- The program **does not print the actual number of computeValue calls**, because the scheduler/JVM determines that. With Java 17 `ClassValue`, multiple computations racing to install a value is an allowed case.
- There is no concurrent `remove`, so the `get(Target.class)` calls receive the same **installed object** per the contract.
- `ExecutorService` is shut down in `finally` so the demo does not leave a thread pool alive unintentionally. In plugin frameworks, a thread pool created by a plugin that is not shut down is a very common source of loader retention.

### 5.2. remove racing with get

Suppose `T1` starts `computeValue(C)` but pauses. `T2` computes and installs value `V1`, and then a thread calls `remove(C)`. Afterwards `T1` finishes computing an old value `V0`. `ClassValue` must prevent `V0` from being installed as a valid result of the association after the latest `remove`.

The Java 17 Javadoc describes state/versioning and a **discard + retry** mechanism when the state has changed, to prevent a value computed in an old state from overwriting a newer state. This does not mean reading metadata and external business state becomes a transaction; `computeValue` must still observe/configure dependent data with appropriate synchronization.

**Do not call `remove` inside `computeValue` and assume recursive ordering will always be handled as desired.** If a computation performs a recursive `get` on the same `ClassValue/Class` without a stopping condition, it can cause infinite recursion/stack overflow. Design the metadata computation graph to avoid circular dependencies or have an explicit initialization strategy.

## 6. Why ClassValue is usually a better fit than a strong static Map<Class<?>,T>?

### 6.1. Pattern that easily retains loaders

For example, a host singleton in the application loader:

```java
static final ConcurrentMap<Class<?>, Metadata> GLOBAL =
        new ConcurrentHashMap<>();

Metadata metaFor(Class<?> type) {
    return GLOBAL.computeIfAbsent(type, this::analyze);
}
```

This snippet is **illustrative code**, assuming type `Metadata` and method `analyze` exist. If the key is a class from plugin loader `L1`, the host's map holds a strong reference to that `Class<?>`, even if the plugin manager has stopped using `L1`. A reload creates loader `L2` + a class with the same name, and the map gets a new entry because the `Class<?>` has a different identity.

Using a `String` key avoids holding `Class<?>` by key, but it can **mix metadata between two versions with the same name**; and a value such as `MethodHandle`/`Method` can still retain the class/plugin loader. Changing only the key type does not by itself guarantee memory safety or type correctness.

### 6.2. ClassValue pattern

```java
static final ClassValue<Metadata> PER_CLASS = new ClassValue<>() {
    @Override protected Metadata computeValue(Class<?> type) {
        return analyze(type);
    }
};

Metadata metaFor(Class<?> type) {
    return PER_CLASS.get(type);
}
```

This is also an **illustrative snippet**. `ClassValue` attaches the association to each `Class` object, rather than requiring the host to keep a global strong Map from `Class` to metadata. If the remaining references to the loader/class are gone, a `ClassValue` held by the host does not by itself create the same **strong-key registry path** as the Map example.

**Do not conclude absolutely that "using ClassValue means there will never be a memory leak"**:

- If a global object still holds a plugin `Class<?>`/`MethodHandle`/instance, the loader can still stay alive.
- If the `ClassValue` object itself or its subclass stored by the host in a static field has a captured field pointing directly to the plugin loader, you still create another retention path.
- The value may hold a file handle, thread, timer, listener, connection, or `MethodHandle`; `ClassValue` does not automatically call `close()`, `removeListener()`, or shut down an executor.
- If code takes metadata from `ClassValue` and stores it in another global list/map, that global structure can become a root retaining the plugin class.
- While the class is currently still reachable, the value attached by `ClassValue` to the class can also stay alive; this is **intentional caching**, not by default a leak.

Thus, the main benefit is **type correctness by Class identity and avoiding a strong-key global cache**. It is not a resource collector or a lifecycle manager for plugins.

## 7. WeakHashMap is not an automatic solution

An often-proposed option:

```java
static final Map<Class<?>, Metadata> CACHE =
        new WeakHashMap<>();
```

`WeakHashMap` uses **weak keys**, but **values are strongly held**. If the value or an object that the value points to **references back to the `Class<?>` key**, the chain from the `WeakHashMap` root through the strong value back to the Class key still exists:

```text
GC root --> WeakHashMap
              |
              +-- strong VALUE --> Metadata
                                     |
                                     v
                                Class<plugin.Widget>  <-- weak KEY
                                     |
                                     v
                                 loader L1
```

Because the key is still reachable via the **value**, the weak-key entry is not cleared merely because the key in the map is weak. This situation is easy to encounter if `Metadata` contains:

- `Class<?> targetClass`;
- `java.lang.reflect.Method` / `Field` / `Constructor` declared in the plugin class;
- `MethodHandle`/`MethodType` having parameter/return/declaring classes from the plugin;
- A `ClassLoader`, object instance, or callback from the plugin.

**Consequence:** `WeakHashMap<Class<?>, MethodHandle>` **can still leak**, because the `MethodHandle` value is capable of retaining the Class/loader via its target and type. You must inspect **the entire object graph** of the value, not just the map type.

In addition, `WeakHashMap` is not thread-safe by default. Wrapping it with synchronization alone does not fix a `value → key` reference cycle. Some architectures use weak references on both key/value or reference queues, but that requires a more complex design and still must handle the lifecycle of external resources.

## 8. Java 17 Example 3 — two loaders, ClassValue, and the strong/weak-key trap

This example actually creates **two Class objects with the same binary name** from the same bytes, in two different defining loaders. It then demonstrates the retention path of a global map and a weak-key value trap.

Separating the plugin's compilation output from the host classpath is **mandatory** in the demo: if the parent application class loader can already see `plugin.Widget`, parent-first delegation may return the class from the parent instead of a new class defined by the child loader.

### 8.1. File `plugin/Widget.java`

```java
package plugin;

public class Widget {
    public String message() {
        return "ready";
    }
}
```

### 8.2. File `RetentionGraphDemo.java`

```java
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class RetentionGraphDemo {
    private static final String NAME = "plugin.Widget";

    record Meta(String typeName, int methods) { }
    record Holder(Class<?> clazz) { }

    static final Map<Class<?>, Meta> GLOBAL = new HashMap<>();
    static final Map<Class<?>, Holder> WEAK_KEYS = new WeakHashMap<>();

    static final ClassValue<Meta> PER_CLASS = new ClassValue<>() {
        @Override
        protected Meta computeValue(Class<?> type) {
            return new Meta(type.getName(),
                    type.getDeclaredMethods().length);
        }
    };

    static final class BytesLoader extends ClassLoader {
        private final byte[] bytes;

        BytesLoader(ClassLoader parent, byte[] bytes) {
            super(parent);
            this.bytes = bytes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));

        Class<?> first = Class.forName(
                NAME, false,
                new BytesLoader(
                        RetentionGraphDemo.class.getClassLoader(), bytes));

        Class<?> second = Class.forName(
                NAME, false,
                new BytesLoader(
                        RetentionGraphDemo.class.getClassLoader(), bytes));

        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("different Class objects: "
                + (first != second));
        System.out.println("different defining loaders: "
                + (first.getClassLoader() != second.getClassLoader()));

        System.out.println("ClassValue stable per Class: "
                + (PER_CLASS.get(first) == PER_CLASS.get(first)));
        System.out.println("ClassValue independent per loader: "
                + (PER_CLASS.get(first) != PER_CLASS.get(second)));

        WeakReference<ClassLoader> probe =
                new WeakReference<>(first.getClassLoader());

        GLOBAL.put(first, PER_CLASS.get(first));
        System.out.println("global cache holds loader: "
                + (GLOBAL.keySet().iterator().next()
                        .getClassLoader() == probe.get()));

        WEAK_KEYS.put(first, new Holder(first));
        System.out.println("WeakHashMap value points to key: "
                + (WEAK_KEYS.get(first).clazz() == first));

        GLOBAL.clear();
        WEAK_KEYS.clear();
        System.out.println("explicit registries cleared: "
                + (GLOBAL.isEmpty() && WEAK_KEYS.isEmpty()));
        System.out.println("GC outcome tested: false");
    }
}
```

### 8.3. Compiling and running with the right classpath

From the root directory containing both files above:

```bash
javac -encoding UTF-8 --release 17 -d plugin-out plugin/Widget.java
javac -encoding UTF-8 --release 17 -d host-out RetentionGraphDemo.java
java -cp host-out RetentionGraphDemo plugin-out/plugin/Widget.class
```

Verified stdout:

```text
same binary name: true
different Class objects: true
different defining loaders: true
ClassValue stable per Class: true
ClassValue independent per loader: true
global cache holds loader: true
WeakHashMap value points to key: true
explicit registries cleared: true
GC outcome tested: false
```

**What this program proves:**

1. It is possible to define two classes with the same binary name from one bytes file using **two different child loaders**. Their `Class<?>` objects have different identities.
2. `PER_CLASS.get(first)` and `PER_CLASS.get(second)` return two independent `Meta` instances; for the same class, the same cached object is returned.
3. `GLOBAL.put(first, ...)` puts a **strong key** that is the first loader's `Class` into the host's static map. While the entry exists, there is a strong path from the static cache to the `Class` and then to the loader.
4. `WeakReference<ClassLoader> probe` is only a secondary observation. Comparing `GLOBAL.keySet().iterator().next().getClassLoader() == probe.get()` proves **the cache is holding a path to the loader**, without needing to force GC or measure timing.
5. `WEAK_KEYS.put(first, new Holder(first))` creates a value pointing back to the Class key. This is why **a weak key is not enough** if the value retains the key.
6. Both registries are `clear()`ed at the end; the program **does not assert that the loader has been reclaimed** because local variables `first`, `second`, `probe`, and other JVM state may still hold references. Even after local references go out of scope, unloading still depends on GC/JVM.

### 8.4. Difference between cleanup and proving unloading

`GLOBAL.clear()` is a useful cleanup operation: it removes **that registry's strong retention path**. However, removing one path does not mean all retention paths from other GC roots have been eliminated. You must check thread context class loaders, callbacks, executors, `ThreadLocal`, registries, and any `MethodHandles` still held.

Do not add:

```java
// NOT proof of unloading:
System.gc();
// assert weakReference.get() == null;
```

A single `System.gc()` call is not a promised unloading time. If you need to test for loader leaks, design a test with a baseline, explicit lifecycle, reference probes, and probabilistic checks within a bounded time **as a diagnostic**, but do not turn an unstable GC outcome into a deterministic correctness condition.

## 9. Identifying references that actually keep a loader alive

Not every leak is inside `Map<Class<?>,...>`. Below are common retention paths in Java runtimes with hot reload:

| Long-lived strong retention source | Reference path to plugin | How to handle |
| --- | --- | --- |
| Host's static global map | Map key `Class<?>` or value containing plugin's `MethodHandle`/instance. | Prefer `ClassValue` for per-Class metadata; use registry cleanup on unload. |
| `Thread.contextClassLoader` | Live thread → TCCL → plugin loader. | Restore original TCCL in `finally`, avoid using plugin loader on long-lived worker threads. |
| `ThreadLocalMap` of pool thread | Live thread → ThreadLocal value → plugin object/Class. | Call `ThreadLocal.remove()` on the right thread in `finally`; clean up worker tasks. |
| Executor/Timer/Scheduled task | Live thread/queue → plugin's `Runnable`/`Callable`/lambda → class/loader. | Cancel tasks, shut down executor, await termination, clear queues. |
| Listener/event bus | Host singleton → listener registered by plugin → plugin instance/loader. | `unsubscribe`/unregister during lifecycle stop. |
| JDBC DriverManager, logging bridge, MBeans/JMX | Global registry holding plugin's callback/driver/class. | Deregister via proper API, stop services on unload. |
| Third-party library static cache | Reflection/serializer metadata or MethodHandles still have plugin types. | Use the library's cache clear/invalidate API; check the cache's scope. |
| Method/Field/Constructor/MethodType/MethodHandle/CallSite | Metadata/handle object can contain plugin's Class, target, or type. | Drop references or use a lifecycle-bound cache; don't just delete the key while keeping the value elsewhere. |
| `Class<?>`/instance in a public singleton | Host service holds an actual plugin callback object. | Separate lifecycles, release callback/instance when plugin stops. |
| Native/JNI/global reference | Native code continues holding object/Class. | Release using the corresponding native protocol. |

**The most important rule when reading a heap dump:** go from the suspected object or loader to **Path to GC Roots**, inspect the **specific strong reference path**, rather than concluding "ClassValue leak" merely because the system uses `ClassValue`.

### 9.1. Thread context class loader (TCCL)

A host thread that lives across multiple reloads can retain a plugin loader even if all static caches have been cleared:

```java
// Illustration snippet when having pluginLoader and Runnable action.
Thread worker = Thread.currentThread();
ClassLoader previous = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    action.run();
} finally {
    worker.setContextClassLoader(previous);
}
```

The key point is **`finally`**. If restoration is missing, a long-lived pool thread can retain the old plugin version's loader indefinitely. If `action` creates a new thread, the child thread may **inherit the TCCL** and continue retaining the loader; thread creation and its own lifecycle must be managed.

Restoring the TCCL only addresses one retention path. If `action` already stored a plugin instance in a host static map or another `ThreadLocal`, the loader is still retained.

### 9.2. ThreadLocal: weak keys do not solve strong values

Inside `ThreadLocalMap`, the `ThreadLocal<?>` key has a weak-reference mechanism, but the **value** is strongly held until the slot is cleared. With long-lived threads, a value belonging to a plugin can persist for a long time even when the `ThreadLocal` key is no longer reachable.

For example, if a thread pool handles a request with a plugin object, stores it in a `ThreadLocal`, and forgets `remove()`, the pool thread can keep retaining the instance/class loader across many subsequent deployments. The safe structure is:

```java
// Snippet with ThreadLocal<RequestContext> context:
context.set(requestContext);
try {
    processRequest();
} finally {
    context.remove();
}
```

Both `requestContext` and `processRequest()` are assumed to be defined in the application. Call `remove` on the **exact thread** that called `set`; another thread clearing its own `ThreadLocal` does not clean up the entry sitting on the old worker thread.

### 9.3. MethodHandle and dynamic runtime caches

A cache like `ConcurrentMap<String, MethodHandle>` may look harmless because the key is only a `String`. However, the value is a `MethodHandle` bound to a plugin method or has a `MethodType` containing parameter/return types from the plugin. Thus host singleton → `MethodHandle` → class/plugin loader can still be a strong path.

Similarly, a `MutableCallSite`/`VolatileCallSite` held by the host may point to a new or old target that is a plugin's `MethodHandle`. Even after replacing the target, if an old `getTarget()` snapshot is still stored in a list/diagnostic callback, the old loader is still retained. Do not assume changing the map key is enough: you must verify **the value and the entire reference graph**.

## 10. ClassValue does not manage resource lifecycles for you

`ClassValue.remove(type)` removes the association so that the next `get` can recompute. It does **not** call `close()`, shut down threads, unsubscribe listeners, flush database connections, or remove class references in other registries.

Therefore, separate the two responsibilities:

**Pure metadata cache:**

```java
record AccessPlan(String typeName, int methodCount) { }

static final ClassValue<AccessPlan> ACCESS_PLANS = new ClassValue<>() {
    @Override protected AccessPlan computeValue(Class<?> type) {
        return new AccessPlan(type.getName(),
                type.getDeclaredMethods().length);
    }
};
```

If the value is immutable and owns no external resources, `ClassValue` is a natural choice.

**Lifecycle-owning resource owner:**

```java
// This is an illustrative API diagram, not a standalone class:
plugin.start();             // create subscriptions/threads/connections
try {
    usePlugin(plugin);
} finally {
    plugin.stop();          // must close / unregister at owner
    // if holding a known Class<?> and wanting to invalidate metadata:
    // ACCESS_PLANS.remove(pluginClass);
}
```

For resources with `close`, keep an explicit owner. Do not expect a value to "auto-close" when a class is unloaded or when `ClassValue` is GC'd.

**Why?** `ClassValue` manages metadata associations. GC reclaims memory when no longer reachable, whereas closing network sockets/files/JDBC sessions or canceling subscriptions is an **ordered application procedure** that cannot be inferred from reachability alone.

## 11. When to use ClassValue and when not to?

| Need | Choice and rationale |
| --- | --- |
| Metadata depends only on `Class<?>`, repeated many times | **ClassValue**: per-class lazy value, avoids a strong global Class-key registry. |
| Reflection/MethodHandle lookup per plugin class | **ClassValue** can be suitable; the value can contain handles related to the class itself but must not be copied into another global cache. |
| Need to query total cached classes or scan all entries | `ClassValue` **has no iteration/size API**; use a dedicated registry with a clear retention policy. |
| Metadata depends on both Class and changing config/tenant/version | `ClassValue` can hold a small per-version cache for the class, but invalidation/versioning must be designed manually; avoid retaining unbounded tenants/versions. |
| Need to memoize per object instance, not per class | `ClassValue` is **not** an object-key cache; pick an appropriate API (e.g., `WeakHashMap<Object,...>` if the value graph is safe). |
| `computeValue` logic registers side effects or allocates resources | Must move those side effects to an explicitly managed lifecycle; `computeValue` can run repeatedly during races. |
| Plugin loader is replaced periodically | `ClassValue` helps reduce one retention path; still need to shut down tasks/threads, clear registries, and find GC roots retaining the loader. |
| Guarantee cleanup at an exact point in time | Do not use `System.gc()`/`ClassValue` as a cleanup scheduler. Proactively call `close`/`removeListener`/`shutdown`. |

### 11.1. ClassValue does not change Reflection/Lookup access rights

If a value is computed using `MethodHandles.Lookup.findVirtual`, `findStatic`, `privateLookupIn`, or `unreflect`, it can only create handles according to the privileges of a valid `Lookup`. `ClassValue` **does not grant extra access privileges**, and cached metadata may carry the capability to access methods/fields.

Avoid exposing metadata containing private `MethodHandles` outside the plugin boundary if consumers do not have the right to use them. `ClassValue` protects **how caching per class works**, not security boundaries.

### 11.2. Performance

`ClassValue` is designed for relatively efficient per-class access. However, one should not promise that it is "always faster than ConcurrentHashMap" in every workload. The cost of computing metadata can be high; the hot path should reuse the existing association and avoid frequent `remove` calls that trigger recomputation.

If benchmarking is needed, use JMH with warmup and compare:

- First `get` (cold compute);
- Subsequent `get` calls (warm cached access);
- Concurrent access;
- With/without invalidation;
- Impact on class unloading/memory when creating and discarding many child loaders.

**More important than a few nanoseconds:** correct class identity and not keeping hundreds of old class loaders alive unnecessarily long.

## 12. Diagnosing class loader retention with JDK 17 tools

Measure across **multiple controlled load/reload cycles** instead of a single snapshot. Distinguish the number of loaded classes, unloaded classes, heap object count, metaspace committed/used, and the count of specific plugin loaders.

### 12.1. jcmd: inspecting class loaders, metaspace, and heap histogram

In an environment with appropriate attach permissions, use the actual process ID:

```bash
jcmd -l
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.metaspace
jcmd 12345 GC.class_histogram
```

`12345` is only an **illustrative PID**, which must be replaced with the PID of the JVM to diagnose. The commands above are not fixed demo output. `jcmd` usually requires the same host/user and corresponding attach permissions; some runtime images/containers may not include the full set of tools.

- `VM.classloader_stats`: number of classes and metadata per class loader; useful to see multiple loaders from different plugin versions coexisting.
- `VM.metaspace`: class metadata area statistics; look at trends and the distinction between **reserved/committed/used**, not just a single number.
- `GC.class_histogram`: instance counts/heap bytes by type; helps find growing metadata, thread objects, and registries. A histogram **does not by itself show the GC root path**.
- `jcmd 12345 help VM.classloader_stats`: view specific help if JVM builds differ.

A heap dump can be used to find strong retention paths:

```bash
jcmd 12345 GC.heap_dump filename=heap.hprof
```

**Warning:** heap dumps can be large, sensitive (containing secrets, personal data), and affect process latency/GC. Only take them in authorized environments with sufficient disk space and a security policy for dump files.

### 12.2. Class-loading / unloading logs

When starting a JVM supporting Unified Logging (HotSpot Java 17), you can observe class loading and unloading events:

```bash
java -Xlog:class+load=info,class+unload=info MyApp
```

This is a **sample command** for an application named `MyApp`, not demo output; configure classpath/module path appropriately. Class load log volume can be large. Not seeing unload events in a short window does not prove a leak; classes/loaders may still be validly reachable, GC may not have collected yet, or the JVM may not have chosen to perform unloading yet.

### 12.3. Java Flight Recorder and JDK Mission Control

On a JVM supporting JFR, you can start a recording with profile settings:

```bash
jcmd 12345 JFR.start name=LoaderAudit settings=profile duration=60s filename=loader.jfr
jcmd 12345 JFR.check
```

The program needs to run long enough to capture events during the recording window; recorded event names and JFR configuration depend on the profile/JVM. JFR/JDK Mission Control lets you view loaded/unloaded class counts, allocations, and thread activity over time when the corresponding events are enabled. Use JFR to **observe trends** and combine it with heap retention graphs, rather than claiming a recording automatically identifies the leak's root cause.

### 12.4. Native Memory Tracking (NMT)

On HotSpot, when you need to distinguish heap and native memory (especially metaspace), you can enable NMT **at startup**:

```bash
java -XX:NativeMemoryTracking=summary MyApp
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

NMT has overhead and may require JVM/build support. It shows native memory categories such as Class/Metaspace, but does not replace a heap dump for the goal **"who is keeping a particular ClassLoader reachable?"**. NMT growth is a signal to investigate, not by itself proof of an object-graph leak.

### 12.5. Heap dump: from loader to GC roots

In Eclipse Memory Analyzer (MAT) or a similar tool:

1. Find the plugin's class loader instances: `URLClassLoader` or a custom subclass like `PluginClassLoader`.
2. Group by class loader/class histogram; inspect class counts/retained size of each loader.
3. Select the loader of a stopped plugin version and use **Path to GC Roots** / shortest strong paths.
4. Identify the live root: host static map, live thread, `ThreadLocal`, TCCL, listener registry, `MethodHandle`, JNI global, service registry...
5. Cross-check against the actual stop/unregister lifecycle.
6. Fix the **root retention path** and re-verify in a multi-redeploy workload.

Do not simply search for the class name `PluginClassLoader` and conclude it leaks upon seeing an instance. If the plugin is **running**, its loader being alive is valid. Conversely, if multiple loaders of stopped versions remain reachable from roots for a long time, that is much stronger evidence.

## 13. Practical investigation workflow: loader stays alive after plugin stopped

Suppose an application reloads a plugin 20 times, creating a new loader each time, yet metaspace and the number of plugin loaders keep increasing.

**Step 1 — confirm there are actually multiple loaders:** use `VM.classloader_stats`, loaded/unloaded class counts, and loader names/versions. Distinguish one loader loading more classes from **multiple loaders** carrying classes with the same name.

**Step 2 — inspect metadata caches:** look for static `Map<Class<?>,...>`, or string-keyed maps whose values hold `MethodHandle`, `MethodType`, `Field`/`Method`, or plugin instances. If the metadata is purely per-class derived data, consider `ClassValue` and remove the strong-key map.

**Step 3 — inspect threads:** identify thread pools, scheduled tasks, TCCL, and thread locals. A plugin's scheduled callback can stay alive even after metadata registries are cleared.

**Step 4 — inspect registries:** unsubscribe listeners, deregister drivers, MBeans, logging hooks, and service callbacks provided by the old plugin.

**Step 5 — inspect value graphs:** even with `WeakHashMap<Class<?>, Metadata>`, the value can retain the Class key. If metadata is placed in `ClassValue` **and** another global list, that list is still a root retaining the loader.

**Step 6 — fix and re-measure:** define a stop protocol where the plugin stops accepting requests, finishes async work, cancels registrations, restores TCCL, clears registries, and drops final strong refs. Re-run multiple reload cycles and compare class/loader/metaspace trends against the baseline.

**Step 7 — do not assume immediate GC:** correctness of cleanup means **no unnecessary root retention paths remain**; unloading occurs when the JVM and GC allow it. If strong proof is needed, use heap dump/reachability analysis together with logs and a sufficient duration.

### 13.1. Distinguish a "leak" from an intentionally kept cache

A class-loader manager may intentionally keep created loaders to serve hot rollbacks/versioned requests. In that case, metaspace growth is **intentional retention**, though there must still be capacity/version limits and an eviction policy. Investigation starts with the question "is this loader still required?" before calling it a leak.

A `ClassValue` cache can hold a very large `Metadata` object while the `Class` is still in use. That may be **memory bloat** needing value optimization, even though it is not a class-loader leak. Separate **classes unable to unload due to a root**, **oversized values**, and **excessive class load rates**.

## 14. Checklist for designing long-lived systems

- [ ] Cache per-`Class<?>` metadata using `ClassValue<T>` when appropriate; do not put strong `Class` keys into a static `Map` without a lifecycle.
- [ ] `computeValue` has safe repeatable computation semantics and performs no side effects that must be exactly-once.
- [ ] Metadata values are ideally immutable; if they contain `MethodHandle`/other `Class` objects, check class-loader provenance.
- [ ] When configuration changes, define how to invalidate/version and who is allowed to continue using old values.
- [ ] Plugin stop closes thread pools, tasks, sockets, class-specific resources, and unregisters callbacks/listeners.
- [ ] Worker threads restore `Thread.contextClassLoader` and clean up `ThreadLocal` on the right thread.
- [ ] Do not keep plugin instances/classes in global singletons or diagnostic buffers forever.
- [ ] Do not treat `WeakHashMap` as a memory-safety guarantee if the value can reference the key.
- [ ] Old-version class loaders are not retained by `MethodHandle`, `CallSite`, `MethodType`, proxies, or cached reflection members on the host.
- [ ] Have metrics for class-loading/unloading, metaspace, and plugin loader count; investigate using heap root paths when growth is observed.
- [ ] GC/unloading is not tested by forcing `System.gc()` and asserting a weak reference is null.
- [ ] Do not use `ClassValue`/weak references to replace explicit cleanup and safe access control.

## 15. Self-check questions

**1. Why can a `static Map<Class<?>,Metadata>` in an application singleton keep an old plugin's loader alive?**

Because the `Class<?>` key is strongly held by the map. A `Class` object belonging to the plugin retains a link to its defining loader, creating a retention path from the singleton's GC root to the loader, even if the plugin manager has stopped that version.

**2. How does `ClassValue` differ from `ConcurrentHashMap<Class<?>,Metadata>`?**

It attaches associations on a per-Class basis via a lazy `computeValue/get/remove` API without forcing the application to maintain a global map with strong `Class` keys. It lacks `iteration/size/put` like a regular map and does not automatically clean up external resources.

**3. Does `computeValue` run exactly once per Class?**

You must not assume so. Multiple threads may compute concurrently and only one value is published; `remove` can also cause computation to run again. Side effects inside the computation must tolerate repetition.

**4. Does `remove(Class)` release all metadata currently used by others and close files/sockets?**

No. It invalidates one `ClassValue`'s association with that `Class`. Already-returned references still exist, and external resource lifecycles must be managed independently.

**5. Why does using `WeakHashMap<Class<?>,Metadata>` still carry a leak risk?**

The key is weak, but the value is strongly held. If `Metadata` contains the `Class<?>` key or a `MethodHandle` pointing to that class, the strong path `map → value → key → loader` still keeps the class/loader alive.

**6. If two child loaders create the same `plugin.Widget`, will `ClassValue` confuse their metadata?**

No. The two `Class<?>` objects are distinct, even though their binary name strings are identical; `ClassValue` associates by Class identity. In the demo, each loader's metadata is a separate object.

**7. If `ThreadLocal` has a weak key, why does it still retain a plugin loader?**

Because `ThreadLocalMap` can strongly hold the value on a live pool thread; the value is a plugin object or contains a Class/loader. You need `remove()` on the right thread and lifecycle cleanup.

**8. Does calling `System.gc()` once and seeing `WeakReference<ClassLoader>.get()!=null` prove a leak?**

No. GC/unloading is not a synchronous contract. You need to identify root paths/lifecycles, monitor trends across multiple load cycles, and investigate using heap dump/JFR/jcmd.

**9. Which tools help find loader retention?**

`jcmd VM.classloader_stats` to see loaders/classes, `VM.metaspace` for metadata memory, `GC.class_histogram` for heap objects, JFR/logs for load/unload trends; **a heap dump with Path to GC Roots** is the direct way to find strong retention paths.

**10. Is `ClassValue` the right solution when all metadata depends on both `Class<?>` and a changing tenant?**

It only keys by `Class`. You must model tenant/config/version yourself in the value and invalidation, or choose another cache with an explicit lifecycle. If you use `ClassValue` and keep all tenants forever inside the value, it can still cause memory bloat.

## 16. Summary

- **`ClassValue<T>`** is suitable for metadata caches that are **lazy by Class identity** and avoid strong global `Class<?>` keys.
- **`get`** computes/installs the association when needed; **`computeValue` can run multiple times** under races, but the installed value is observed consistently per the contract; **`remove`** invalidates the association so the next `get` recomputes.
- **Class loader leaks are a reachability story:** trace the chain from **GC roots** to plugin `Class<?>`, loader, instance, or `MethodHandle`, rather than looking only at class names or a single metaspace number.
- **`WeakHashMap` does not guarantee leak-free behavior** if strong values reference keys back; `ThreadLocal` and TCCL are two major loader retention sources.
- **`ClassValue` does not auto-close resources**, does not remove listeners, does not stop thread pools, and does not block other retention paths.
- **Testing/class unloading is not deterministic around a single `System.gc()`**; observe with `jcmd`, JFR, class unloading logs, heap dumps, and **Path to GC Roots** when signs of retention appear.
- **Good design requires both the right cache and the right lifecycle:** per-Class metadata, explicit cleanup, bounded registries, controlled thread contexts, and monitoring.

### Official References — Java SE 17

- [ClassValue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): `computeValue`, `get`, `remove` contracts, atomic installation, contention, and invalidation.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): identity, `getClassLoader`, class metadata.
- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, class loading/definition.
- [WeakHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values, and the risk of values indirectly retaining keys.
- [ThreadLocal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `set/get/remove`, lifecycle of thread-local values.
- [Java SE 17 Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): `jcmd`, class loading stats, metaspace/NMT, JFR, heap dumps.
- [Java SE 17 Troubleshooting Guide — Diagnosing Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-guide.pdf): class-loader statistics and retention investigation.
