# Testing That Caches Do Not Retain End-of-Lifecycle Plugins

## 1. The Problem: Plugin Stopped, Yet ClassLoader Still Alive

In Java applications that dynamically load plugins (plugin managers, application servers, test tools, hot-reload systems), each plugin can be loaded with its own `ClassLoader`, such as `URLClassLoader`. When a plugin is unloaded, the application usually expects no objects, classes, or metadata of that plugin to remain retained by longer-lived code.

A common bug is **a reflection cache in the core application accidentally retaining the plugin's class loader**:

```text
GC roots of the core application
  └─ static metadataCache
      └─ Map entry
          ├─ key: plugin's Class<?> ──> defining ClassLoader
          └─ value: Method/Field/Constructor ──> declaring Class ──> ClassLoader
```

A `Class<?>` defined by a plugin loader remains tied to that loader during its lifetime; `Method`, `Field`, `Constructor`, or `MethodHandle` objects can retain references related to the plugin's classes. When a global cache retains these objects, **`plugin.stop()` or `URLClassLoader.close()` is not enough** to make the plugin unreachable.

Consequences can include:

- The number of class loaders and loaded classes grows across reload cycles;
- Metadata/class memory and heap fail to return to a steady baseline;
- Old plugins keep holding registries, listeners, or data; new plugin versions may hit conflicts;
- Repeated hot reloads lead to rising memory usage, GC overhead, and resource exhaustion.

The goal of this lesson is to **design tests verifying that caches do not retain plugins after their lifecycle ends**, while avoiding the misconception that a single `System.gc()` failing to collect a class loader is definitive proof of a memory leak.

## 2. Understanding "End of Lifecycle" and "Collected" Accurately

A plugin typically goes through these steps:

1. **Load**: create an isolated loader, load classes, discover metadata, instantiate objects, and register services.
2. **Use**: invoke the plugin, potentially caching `Method`/`Field`/`MethodHandle`/descriptors to avoid repeated scanning.
3. **Deactivate**: stop accepting new requests, wait for in-flight tasks to finish, and stop creating new callbacks.
4. **Cleanup**: unregister listeners/services, cancel tasks, close resources, evict cache entries, and clear references from the host.
5. **Close loader**: close `URLClassLoader` when appropriate; this releases resources and prevents loading from the loader's URLs per the API contract, but **does not force class unloading**.
6. **Observe eligibility**: no strong-reference path remains from GC roots to the class loader/classes/plugin.
7. **Eventually collect**: the GC *may* collect the class loader and its associated classes once unreachable; **timing is not guaranteed**.

Distinguish two testing goals:

| Goal | Reliable method |
| --- | --- |
| Did the host remove cache entries/registrations per contract? | Deterministic API checks: `cache.size() == 0`, ID absent from registry, tasks canceled, `close()` called |
| Did the loader become eligible for collection? | Use `WeakReference<ClassLoader>`/`ReferenceQueue`, isolate strong-reference scopes, inspect across cycles |
| Was the loader actually collected by GC? | Observe `WeakReference.get() == null` or queue event; usually needs multiple attempts, result may be inconclusive |
| No remaining leak in real environments? | Run multi-cycle reloads + classloader/class count/heap metrics + profiler/JFR, not a single measurement |

**"Did not observe GC happen" is different from "evidence of a leak."** `System.gc()` is only a hint/request; GC may be restricted by flags, deferred, or behave differently across JDK collectors. Use reasonable timeouts, report *inconclusive* results when appropriate, and diagnose reachability when needed.

## 3. Which Reflection Caches Can Retain a Plugin?

### 3.1. Strong-Reference Caches Holding Plugin Keys or Values

Example of a framework owning a long-lived class loader:

```java
static final java.util.Map<Class<?>, java.lang.reflect.Method> METHOD_CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

If the key is `pluginClass`, the map strongly retains that class. If the value is a `Method` declared by a plugin class, the value can also retain its declaring class. A `Map<String, Method>` cache is not safe merely because the key is `String`: the value still retains the plugin's method.

Similarly, other metadata types must be evaluated:

- `Class<?>`, `Method`, `Field`, `Constructor<?>`, `RecordComponent`;
- `MethodHandle`, `VarHandle`, `MethodHandles.Lookup`, bound handles created via `bindTo(pluginInstance)`;
- `MethodType`, or schemas/descriptors containing `Class<?>`, annotation instances, or accessor lambdas;
- `java.beans.BeanInfo`/`PropertyDescriptor` and framework metadata caches;
- `ServiceLoader`, factories, callbacks/`Runnable`, instances, or class loaders stored in registries.

Not every metadata value is guaranteed to retain a class loader; **analyze the actual object graph**. However, treat any entry holding a reference to a plugin's `Class<?>` or instance as risky until lifecycle safety is proven.

### 3.2. `WeakHashMap` Does Not Automatically Break Every Reference Cycle

Flawed design example:

```java
Map<Class<?>, Method> cache = new WeakHashMap<>();
cache.put(pluginClass, pluginClass.getMethod("run"));
```

This fragment requires importing `Map`, `WeakHashMap`, `Method`, and having `pluginClass`. Even though the key is weak, **the `Method` value can hold a strong reference back to its declaring class**. Because `WeakHashMap` still holds values strongly, the path `map -> value -> class (weak key)` can keep the class alive indefinitely; the key is never reclaimed as expected.

Weak keys only help if the value structure does not point back to the key or loader through any strong-reference path. In practice, use `ClassValue<T>` or explicit eviction tied to plugin lifecycle instead of assuming a weak-key map is sufficient.

### 3.3. `ClassValue<T>` for Metadata Tied to Class Lifecycle

`ClassValue` provides a mechanism to store a value computed from a `Class<?>` and managed by the JVM alongside the class's lifecycle. Example:

```java
private static final ClassValue<Method> REFLECTIVE_ADD = new ClassValue<>() {
    @Override
    protected Method computeValue(Class<?> type) {
        try {
            return type.getMethod("add", int.class);
        } catch (NoSuchMethodException e) {
            throw new IllegalStateException(e);
        }
    }
};
```

This is a **fragment** requiring `import java.lang.reflect.Method` and placement inside a class. Caching per class with `ClassValue` fits many dynamic class-loading systems better than a static strong map keyed by `Class<?>`.

However, `ClassValue` **does not guarantee a plugin can unload** if that same `Method` or plugin instance is retained elsewhere (such as a static registry, listener, or queue). In addition, `computeValue` can run multiple times under races; values should be computed idempotently without relying on single-execution side effects. When metadata policies change, use an appropriate invalidation/`remove(type)` strategy.

### 3.4. Caching by Plugin ID and Explicit Eviction

If the host actively manages lifecycle, a clear policy is caching by plugin ID/generation and **removing all descriptors belonging to that generation at unload**. Example:

```java
// Illustrative architectural pseudocode, not an existing Java API.
onPluginUnload(pluginId) {
    stopNewCalls(pluginId);
    waitForInFlightCalls(pluginId);
    unregisterCallbacks(pluginId);
    reflectionCache.evictAll(pluginId);
    closePluginResources(pluginId);
    closeClassLoader(pluginId);
}
```

Advantage: eviction can be tested **deterministically**, without waiting for GC. The critical requirement is preventing an old async task or callback from writing back a cache entry right after cleanup. Use generation tokens, a `CLOSED` state, or proper synchronization to prevent *resurrection* of stale cache entries.

## 4. Designing a Proper Test

A quality test includes both a **negative control** (the flawed cache pattern actually retains the loader) and a **positive case** (cleanup clears all controllable strong references).

### 4.1. Creating a Plugin with an Isolated Loader

Use `URLClassLoader` with a URL pointing to a directory containing plugin bytecode and a suitable parent. The plugin class must be **actually defined by the isolated loader**. Loading `java.lang.String` from the bootstrap/platform loader and attaching a `WeakReference` to an empty loader proves nothing about plugin metadata.

You can generate a small Java source file, compile it into a temporary directory using `javax.tools.JavaCompiler`, and load the class via `Class.forName(name, true, pluginLoader)`. Assert `pluginClass.getClassLoader() == pluginLoader` before proceeding.

### 4.2. Isolating Strong Scope from the Observation Step

Inside a setup/plugin-use method, local variables such as `Class<?> pluginClass`, `Method method`, `Object pluginInstance`, or `URLClassLoader loader` can all act as strong references. The JIT is permitted to keep locals reachable longer than you expect.

Therefore, place **all load/use/close steps in a helper method that avoids leaking references** and return only a `WeakReference<ClassLoader>`; do not return `Class<?>` or `Method`. Separating the helper reduces the risk of the test itself retaining the loader. Never store plugin objects in static test fields or lambda callbacks, and never embed live instances into assertion failure messages.

### 4.3. Using `WeakReference` and `ReferenceQueue` Properly

`WeakReference.get() == null` proves the GC cleared the weak reference to the referent. When registering a reference with a `ReferenceQueue`, you can check enqueue events using `queue.poll()` or `queue.remove(timeout)`. That is a **signal of GC collection**, not a synchronous signal from `ClassLoader.close()`.

Retry multiple times with pauses; if collection is not observed, report *inconclusive* or trigger heap analysis. Do not use `Thread.sleep(100)` as proof that a loader must disappear within 100 ms. Do not set tiny timeouts that make CI flaky; nor allocate unbounded memory to "force GC" until `OutOfMemoryError`.

### 4.4. Cleanup Must Be Measurable Independently of GC

Assert deterministic events:

- `cache.size()` / plugin-specific entry count drops to 0 after unload;
- plugin registries, listeners, command handlers, scheduled jobs, executors/tasks, and callbacks are released;
- no plugin threads or TCCL (`Thread.contextClassLoader`) still point to the old loader;
- loaders/resources are `close`d per contract; streams/JAR handles are closed;
- if framework global caches exist, know their eviction hooks/APIs (e.g., JavaBeans `Introspector.flushFromCaches(pluginClass)` in appropriate contexts);
- no in-flight requests continue invoking or re-registering listeners/caches of the unloaded plugin.

If these assertions are not met, you do not need GC to conclude cleanup is broken.

## 5. Complete Java 17+ Example: Seeing a Flawed Cache Retain a Loader and Clearing It

The example below compiles a small Java plugin **directly inside a temporary directory**, loads it via `URLClassLoader`, invokes a method via reflection, intentionally stores `Class<?> -> Method` in a **flawed** static cache to demonstrate the strong-reference path, and then clears the cache. Afterward, the program merely *attempts to observe* GC.

> Run with a **JDK**, not a stripped JRE, because `ToolProvider.getSystemJavaCompiler()` is required. The program creates and deletes a temporary directory during execution; it does not download plugins from the network.

Save as **`PluginCacheLifecycleDemo.java`**:

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class PluginCacheLifecycleDemo {
    // INTENTIONALLY FLAWED: host cache strongly retains both plugin Class and Method.
    static final Map<Class<?>, Method> BAD_CACHE = new ConcurrentHashMap<>();
    static final ReferenceQueue<ClassLoader> QUEUE = new ReferenceQueue<>();

    // Returns ONLY a weak ref. All temporary strong refs remain inside this scope.
    static WeakReference<ClassLoader> loadUseAndClose() throws Exception {
        Path root = Files.createTempDirectory("plugin-classloader-test-");
        Path javaFile = root.resolve("demo/Plugin.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile,
            "package demo; public class Plugin {"
            + " public Plugin() {}"
            + " public String hello() { return \"hello\"; }"
            + " }");

        try {
            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Please run on a full JDK");
            }

            int exit = compiler.run(null, null, null,
                "--release", "17", "-d", root.toString(), javaFile.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compile error: " + exit);
            }

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {root.toUri().toURL()},
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> plugin = Class.forName("demo.Plugin", true, loader);
                if (plugin.getClassLoader() != loader) {
                    throw new AssertionError("Plugin must use its own loader");
                }
                Method method = plugin.getMethod("hello");

                // Creates strong-reference path: BAD_CACHE -> Class/Method -> loader.
                BAD_CACHE.put(plugin, method);

                Object instance = plugin.getConstructor().newInstance();
                System.out.println("plugin call: " + method.invoke(instance));
                return new WeakReference<>(loader, QUEUE);
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path :
                        paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    static boolean observeCollection(WeakReference<ClassLoader> ref)
            throws InterruptedException {
        for (int i = 0; i < 15; i++) {
            System.gc(); // Hint; does NOT guarantee immediate GC.
            if (ref.get() == null || QUEUE.poll() == ref) {
                return true;
            }
            Thread.sleep(80);
        }
        return ref.get() == null;
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> reference = loadUseAndClose();

        System.out.println("bad cache size: " + BAD_CACHE.size());
        System.out.println("loader reachable via bad cache: "
                + (reference.get() != null));

        // Mandatory cleanup: plugin entries must be evicted.
        BAD_CACHE.clear();
        System.out.println("bad cache empty after cleanup: "
                + BAD_CACHE.isEmpty());

        boolean collected = observeCollection(reference);
        System.out.println("GC: " + (collected
                ? "collected (observed)"
                : "not observed (inconclusive)"));
    }
}
```

Compile and run:

```bash
javac --release 17 PluginCacheLifecycleDemo.java
java PluginCacheLifecycleDemo
```

The first three lines and the cleanup line have deterministic output when plugin compilation/loading succeeds:

```text
plugin call: hello
bad cache size: 1
loader reachable via bad cache: true
bad cache empty after cleanup: true
```

The final line depends on GC timing. Two outcomes are possible:

```text
GC: collected (observed)
```

or:

```text
GC: not observed (inconclusive)
```

**Do not treat the second branch as a definite test failure.** The output proves a key point: while `BAD_CACHE` holds an entry, the loader remains reachable through the cache; after `BAD_CACHE.clear()`, that specific reference path is removed. In a real application, inspect other reference paths if the loader persists across multiple GC cycles.

Why does the demo use `ClassLoader.getPlatformClassLoader()` as parent? `demo.Plugin` does not depend on host classes, and the platform parent has no definition of `demo.Plugin`; thus the plugin class is guaranteed to be defined in the isolated loader. Real systems may pick another parent to share plugin APIs, but must ensure they do not accidentally load plugin implementations from the parent loader.

Limitation of the demo: `BAD_CACHE.clear()` wipes the **entire** simulated cache for one plugin. In a multi-plugin system, evict only entries belonging to the exact plugin generation; do not wipe metadata of other plugins. And `QUEUE` illustrates the weak-reference event queue; it is not required to verify that cache entries were evicted.

## 6. Writing Reliable Regression Tests, Avoiding Flaky GC Tests

Divide tests into two tiers.

### Tier A — Deterministic Cleanup Tests (Mandatory)

Create a fake plugin with an explicit ID or generation. Perform in sequence:

1. Register services, populate cache entries via reflection, and create known listeners/tasks.
2. Verify while `ACTIVE`, expected entries exist.
3. Invoke `stop/unload`; wait for in-flight tasks to complete per contract.
4. Assert the cache has zero entries for that **exact plugin generation**.
5. Assert registries/listeners/threads/tasks are unregistered/canceled; loader is closed where applicable.
6. Assert the API rejects further calls/cache writes after transitioning to `CLOSED`.
7. Load a new generation of the plugin with the same class name and same plugin ID; ensure old-generation metadata is not reused.

This test requires no forced GC; it should run reliably in CI across every supported JDK.

### Tier B — Loader Collection Observation Tests (Diagnostic/Integration)

- Create an isolated class loader and real plugin class, using `WeakReference<ClassLoader>`; optionally add weak refs to `Class<?>` or plugin instances, while **never strongly retaining** those referents in the test.
- Run multiple load/unload cycles, with a separate helper per cycle.
- After cleanup, request GC over **bounded** cycles and read results from weak refs/`ReferenceQueue`.
- If a weak ref is cleared, that is observed evidence of collection for that referent.
- If not cleared, classify as **inconclusive**, collect a heap dump/dominator graph to locate pinning roots; do not automatically assume "leak."
- Use repeated workloads and classloader metrics to spot long-term retention trends, rather than inferring from a single data point.

A JUnit test can use `assertTimeout` or a deadline mechanism for the wait phase **to keep test duration bounded**, but must never mandate that GC occur before a deadline in an environment where the JVM makes no such promise. If a product has quantitative resource-release requirements, verify resources with explicit release contracts (closing file descriptors, unregistering listeners, cache entry counts) first; verify class unloading via separate integration metrics.

### Negative Control: Confirming the Test Can Catch Real Leaks

In an isolated test run:

- Retain a plugin's `Class<?>` or `Method` in the host's static cache;
- After the helper returns only the weak ref, verify the strong cache still holds the entry and `weak.get() != null`;
- Clear that entry, check `cache.isEmpty()`;
- Afterward, you **may** wait/observe GC.

With this negative control, you prove the test suite can detect at least one deterministic retention path. Testing only the "good" version without an intentional leak sample leaves uncertainty about whether the observation/cleanup helpers were built properly.

## 7. Sources Retaining ClassLoaders Outside Reflection Caches

Even when the metadata cache is properly designed, a plugin can still be retained by:

| Reference source | How it arises | Mitigation |
| --- | --- | --- |
| Static registry in host | `Map<String, PluginHandler>` holding plugin instances/callbacks | Unregister by plugin generation |
| Running Executor/Thread | Runnable/lambda capturing `pluginInstance`/`ClassLoader` | Stop and join/await tasks; purge references in queues |
| Thread context classloader (TCCL) | Host thread calls `setContextClassLoader(pluginLoader)` and fails to restore it | Use `try/finally` to restore TCCL; stop plugin threads |
| `ThreadLocal` | Long-lived thread holds a plugin-owned value | Call `remove()` on the right thread or manage thread lifecycle |
| Listener/MBean/observer | Host event bus retains plugin listener class | Unregister using an explicit token |
| Scheduler, timer, callback | Future job captures plugin object | Cancel; remove queue entries and block re-registration |
| JavaBeans metadata | `Introspector` or framework cache retains `BeanInfo`/descriptors | Check flush/invalidation APIs, e.g., `Introspector.flushFromCaches(clazz)` when appropriate |
| Service discovery | `ServiceLoader`/factory retains provider instances or loader | Release loader/providers and related caches |
| Logging / tracing / metrics | Logger appender, instrumentation, or exporter retains callbacks/classes | Remove registrations when plugin stops |
| JNI/native handles/file resources | Native code/JAR handles hold resources | Close resources properly, release registrations per native API |

A static field **inside the plugin class itself** does not create an external GC root outside the plugin once its entire loader/classes are unreachable; the risk is references from **long-lived host/JDK threads/registries** pointing back into the plugin. When investigating, always ask: "Which GC root holds a strong path to the loader?"

### Safe TCCL Restoration Example

```java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Short-lived work requiring the plugin's loader.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
```

The fragment above requires a valid `pluginLoader` variable. This is hygiene for threads reused from a pool. It does not replace stopping threads actually spawned by the plugin. When using thread pools, also manage `Runnable`/`Callable` tasks sitting in queues.

## 8. Designing Caches for Multiple Plugins, ClassLoaders, and Hot Reload

### Keys Must Distinguish Plugin Versions

The same fully qualified class name, e.g., `com.example.Plugin`, can be defined by **two different class loaders**. In Java, class identity ties to *binary name + defining class loader*. Therefore, caching purely by **string class name** can return stale metadata from the wrong class loader after reload.

If caching by name, attach the plugin generation/classloader identity using a key with strictly managed lifecycle, and evict on unload. Avoid storing strong classloader keys permanently in a global cache.

### "Safe" Cache Data Can Still Pin via a Value

A wrapper like `CachedAccessPlan` may look like it only stores text names/types, yet a hidden field such as `Method getter`, `Class<?> type`, `MethodHandle access`, or `Supplier<?> lambda` can retain the plugin. Inspect the object graph of **values**, not only key types.

### Cache Eviction Under Concurrency

A plugin can be unloaded at the exact moment another request is using the cache:

1. Transition the plugin to `STOPPING` to block issuing new call sessions.
2. Await/cancel in-flight requests per contract.
3. Delete metadata/registries/tasks belonging to that generation.
4. Close resources/loaders.
5. Set `CLOSED`; any late lookup for the old generation must be rejected.

Merely calling `cache.remove(key)` while a worker is still running `computeIfAbsent` and recreating the entry leaves the old plugin retained. Concurrency tests should use barriers/latches coordinating an in-flight lookup while stopping the plugin; at the end of the test, verify **no repopulation** occurred.

### Guarding References Across JDK Versions

Different JDK versions can change internals of reflection, GC, and class unloading. Never rely on a magic threshold or guess internal `Method` caches to confirm unloading. Test on target JDKs (at least supported versions) with assertions based on the **public lifecycle contract**, combined with `WeakReference`/JFR/heap analysis observations. Especially across JDK upgrades, caches using internal JDK accessors are brittle designs.

## 9. Diagnostic Tools When Loaders Fail to Disappear

When multi-cycle reload integration shows unstable loader/class counts:

1. Record counts of closed plugin generations, cache entries per generation, and active threads/tasks/registries.
2. Enable Unified Logging for class unloading if needed: `-Xlog:class+unload=info` (supported on HotSpot). It logs class-unload events only when they actually occur, without guaranteeing timing.
3. Use JFR or heap dumps and dominator-path analysis tools to trace **GC root → host cache/registry/thread → plugin classloader**.
4. Inspect static `Class<?> -> Method` maps, `WeakHashMap`s with values referencing keys, externally leaked `ClassValue`s, thread context loaders, `ThreadLocal`s, and scheduled executors.
5. Identify which object is actually retained: loader, `Class<?>`, plugin instance, metadata/handle, thread, or resource. A single heap snapshot must be read carefully; high loaded-class counts can result from workload or GC not having run yet.
6. Remove one strong-reference path and re-run an equivalent test sequence; compare metrics and object graphs. Avoid changing multiple factors at once and losing visibility into the root cause.

When analyzing graphs, remember that **one class loader can hold many classes**; seeing a single loader stay alive can retain large amounts of metadata even if only one listener or one `Method` was miscached.

## 10. Common Mistakes and Self-Check Questions

- **"`URLClassLoader.close()` was called, so classes definitely unloaded":** false; `close()` releases loader resources but does not clear existing strong references.
- **"One `System.gc()` didn't collect, so there's definitely a memory leak":** false; GC makes no timing guarantees.
- **"`WeakHashMap<Class<?>, Method>` is safe because keys are weak":** false if the `Method` value retains the class/key.
- **"`ClassValue` fixes every leak":** false when listeners, registries, threads, or another cache still retain the plugin.
- **"Caching class name is enough to distinguish plugins after reload":** false because the same class name can come from two different loaders.
- **"Removing a cache entry once is enough even while the plugin runs concurrently":** false if a late task can recreate the entry.
- **"Measuring heap usage right after stop is enough":** insufficient; heap memory differs from metaspace and also depends on GC, allocation pressure, classloader count, and JIT warm-up.
- **"Test keeps `Class<?>`/`Method` variables in scope while waiting for GC":** the test itself can pin the plugin and produce a false positive.

Self-check:

1. A host static cache stores a `Method` declared in a plugin; the plugin closes its `URLClassLoader`, yet the method stays in the cache. Is there a risk of retaining the loader? **Yes**: metadata can retain the declaring class and loader.
2. Need a deterministic, non-flaky CI test: what do you use first? **Assert exact eviction/unregistration/stop**, then observe GC at a separate integration layer.
3. Does `weak.get() != null` after 100 ms prove a leak? **No**.
4. Is using `WeakHashMap<Class<?>, Method>` safe enough? **No**, you must inspect reference paths from value back to key.
5. Reload two plugin classes with the same name under different loaders: is their class identity identical? **No**.
6. If the cache was cleared yet the class loader stays alive, what should you investigate? **Other GC roots:** threads/TCCL, `ThreadLocal`, listeners, tasks, service registries, framework caches, and the object graph.
7. An in-flight request might add a cache entry for a `CLOSED` plugin after cleanup. What do you test? **A race test with a generation token/barrier**, ensuring entries cannot be repopulated.

Further reading from standard APIs:

- [`java.lang.ref.WeakReference` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html)
- [`ReferenceQueue` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html)
- [`ClassValue` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html)
- [`URLClassLoader.close` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [`java.util.WeakHashMap` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html)
- [`Introspector.flushFromCaches` — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html#flushFromCaches(java.lang.Class))
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html)