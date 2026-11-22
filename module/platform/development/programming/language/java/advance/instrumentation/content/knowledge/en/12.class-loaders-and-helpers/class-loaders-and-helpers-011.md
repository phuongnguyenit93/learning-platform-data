# Managing References to Class, ClassLoader, and Caches to Avoid Retaining Expired Class Loaders

> **Key takeaway:** In Java instrumentation, storing `Class<?>`, `ClassLoader`, `Method`, `MethodHandle`, or application objects in a **cache/registry that outlives the instrumented application** can prevent the old application version's class loader from ever being eligible for garbage collection. Removing an application/plugin from the system is not enough if the Java agent, transformer, thread, cache, or callback still holds a strong reference path to classes defined by that loader. To avoid a *class loader leak*, design the lifecycle of the **stored objects**, the **storage location**, and the **unregistration/release mechanism** to align with the lifecycle of the defining class loader.

This lesson belongs to the **Class loaders and helpers** group of Java Advance – instrumentation. We will explain the reference graphs that cause leaks, choosing an appropriate cache, the `WeakHashMap` trap, how to use `ClassValue` and `WeakReference`/`ReferenceQueue`, along with a Java 17+ experiment featuring a real Java agent. **Important:** The experiment demonstrates reference structure and cache behavior with deterministic output; it **does not claim that GC has definitely unloaded classes** after calling `clear()`.

## 1. Class loader lifecycle and why agents easily retain them by mistake

A Java class is identified at runtime by its **binary name and defining class loader**, not merely by a name like `com.example.PaymentService`. Two plugins can both contain `com.example.PaymentService` but defined by two separate class loaders, so they are **two different `Class<?>` instances**.

When a plugin is redeployed:

~~~text
JVM / process stays alive
    |
    +-- Long-lived agent, helpers, metrics exporter, static registry
    |
    +-- Plugin version 1: PluginClassLoader@A --> Class<?> instances of version 1
    |       |
    |       +-- after undeploy: should be eligible for reclamation
    |
    +-- Plugin version 2: PluginClassLoader@B --> Class<?> instances of version 2
            |
            +-- running normally
~~~

If the agent puts a `Class<?>` from version 1 into a `static Map` and forgets to remove it, the long-lived registry becomes a **GC root chain** reaching the classes of loader A. Loader A's classes and the loader itself have mutual retention relationships in the JVM model, causing loader A and much of its associated data to stay alive even after plugin A has been undeployed.

Points to remember:

- **A class not yet unloaded does not by itself prove a leak.** GC/class unloading has reachability conditions and does not necessarily happen immediately upon undeploy.
- **A reference cycle is not by itself a leak.** For example, loader → class metadata → loader can be collected when there is no longer a strong reference path from live roots.
- **An actual leak occurs when a long-lived root** (agent, static cache, thread, global listener, native reference, etc.) continues to reach classes/loaders belonging to an obsolete version that is no longer needed.
- **Class unloading does not equate to immediate object cleanup.** You must manage the plugin's resources, threads, listeners, and caches; do not just rely on GC.

For instrumentation tools, the risk increases because the agent is usually loaded early by the JVM and **lives for the entire lifetime of the process**, whereas the application or plugin has a shorter lifecycle. Treat the agent as a party **that can inadvertently own long-term references** to the class loaders it is meant to observe.

## 2. Reference paths that prevent a loader from being collected

### 2.1. A `Class<?>` as a key in a static cache

Anti-pattern example:

~~~java
// Illustrative snippet inside an agent, not a standalone program.
private static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();

static void remember(Class<?> type, Metadata metadata) {
    CACHE.put(type, metadata);
}
~~~

If the class `type` is defined by a plugin loader, the map held by the agent has JVM lifetime. Even if the plugin removes all of its own references, **the map still strongly holds the `Class<?>` key**. As long as the entry remains there, the JVM cannot treat that `Class<?>` as unreachable in the normal way.

The same issue appears with other keys: `Map<ClassLoader, ...>`, `Set<ClassLoader>`, lists of transformed classes, or caches of `Method` and `Constructor`. Reflection methods are tied to their declaring class; `MethodHandle`/lookup and structures containing methods must also be checked because they can retain classes and loaders.

~~~text
GC root (long-lived agent class)
    |
    v
static ConcurrentHashMap
    |
    +-- key Class<PluginClass>  <-- holds strong reference
            |
            v
       defining PluginClassLoader
            |
            v
       related plugin classes/metadata
~~~

**Fix according to lifecycle:** do not hold entries strongly forever; use a per-class cache whose behavior is compatible with unloading, or remove entries on the undeploy event, or bound the cache with an explicit policy. `CACHE.clear()` only releases the reference path of **that cache**; if another thread, registry, or cache still holds the class, the loader is still not eligible for unloading.

### 2.2. A `ClassLoader` as a key or value

~~~java
// Also an anti-pattern if the map outlives the plugin:
private static final Map<ClassLoader, LoaderInfo> LOADERS = new HashMap<>();
~~~

This is a **direct strong reference** to the loader via the key. Changing the key to the loader name as a `String` may remove the direct reference path, but **does not solve all problems**: names may not be unique, data still grows unboundedly, and the value may continue to retain classes/loaders.

A `LoaderInfo` value can indirectly retain the loader through a `Class<?>`, `Method`, `ClassLoader`, a plugin object, a lambda capturing a plugin service, a proxy class, or a listener instantiated from the plugin.

### 2.3. Transformers and callbacks registered for the JVM lifetime

~~~java
// Illustrates a design at risk of retaining the loader:
final ClassLoader pluginLoader = discoverPluginLoader();
ClassFileTransformer transformer = new MyTransformer(pluginLoader);
instrumentation.addTransformer(transformer);
~~~

If `MyTransformer` strongly holds `pluginLoader` in a field and the JVM's registration still holds the transformer, then removing references inside the plugin **cannot detach the reference path through the registration**.

When a transformer is no longer needed, remove it using the **exact registered instance**:

~~~java
boolean removed = instrumentation.removeTransformer(transformer);
~~~

Notes:

- `removeTransformer` cancels a corresponding registration; it **does not automatically revert the bytecode of already-instrumented classes**.
- If the same instance was added multiple times, a single remove only removes the most recent matching registration. Avoid duplicate registrations.
- According to the Javadoc, callbacks may still occur after the remove call because class loading happens concurrently. The transformer must tolerate late callbacks.
- If the agent still holds a reference to the transformer or `pluginLoader` in a static field/list, **calling remove alone is not enough**; you must also clear that field/list when safe.

### 2.4. Threads, context class loader, and thread-locals

Direct caches are not the only things that pin a loader:

- A long-lived thread may still have `Thread.getContextClassLoader()` set to the old plugin's loader. For example, a worker thread created by a framework and reused after undeploy.
- A `ThreadLocal` on an executor thread still holds an object belonging to the plugin after the request finishes.
- Scheduled tasks, `ExecutorService`, listeners, shutdown hooks, exporters, metric callbacks, JMX MBeans, or service registries still retain plugin instances/classes.
- A strong callback registered in a JVM-scope singleton can retain the entire closure and the plugin's class loader.

**Context loader restoration pattern** for a bounded task:

~~~java
// Illustrative snippet placed in code where appLoader and Runnable task are known:
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(appLoader);
    task.run();
} finally {
    current.setContextClassLoader(previous);
}
~~~

If you create a dedicated executor/thread for a plugin, manage both its lifecycle and shutdown, not just switching the TCCL. With `ThreadLocal<T>`, call `remove()` in `finally` after the scope of use. When holding a reference to a plugin object, inspect the entire **indirect chain of values**, not just the declared field type.

## 3. Inside a transformer callback, what should and should not be kept?

Java 17+ allows overriding the callback in the form:

~~~java
byte[] transform(Module module,
                 ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain domain,
                 byte[] classfileBuffer);
~~~

This is an **illustrative signature**, not a standalone Java file. Every parameter has its own meaning:

| Parameter | What can it be used for inside the callback? | Risk if cached long-term |
| --- | --- | --- |
| `module` | Restrict the module to instrument | Holding the module object may pull in a graph to the loader/runtime; must be verified |
| `loader` | Distinguish classes defined by the bootstrap loader (`null`) from other defining loaders | Strong reference to the plugin loader |
| `className` | Filter class names in internal name form: `org/sample/Worker` | The string itself does not retain a loader, but is **not sufficient** to uniquely identify a class |
| `classBeingRedefined` | Distinguish a class being defined for the first time (`null`) from an existing class (non-null) | Strong reference to the `Class<?>` of the old loader |
| `domain` | Access protection domain context when genuinely needed | May retain part of the associated object graph; do not store unboundedly by default |
| `classfileBuffer` | Analyze/generate class bytes | Copying bytes does not directly retain `Class<?>`, but can consume large heap and expose contents if cached unboundedly |

**Filter early, process briefly, do not hoard long-lived objects**:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
    if (className == null || !className.startsWith("org/sample/")) {
        return null;
    }
    // Use the information during the callback, do not put Class/loader into a global map.
    // If not generating new bytecode, return null.
    return null;
}
~~~

This callback snippet must be placed in a class implementing `ClassFileTransformer` with appropriate imports; it is not a standalone program. If you only need transform counts by group, you can increment a counter keyed by a **normalized operation/namespace name**, instead of creating a `Map<ClassLoader,Class<?>>` for counting.

**Common misconceptions:**

- For a first definition, `classBeingRedefined == null` is normal; therefore do not rely on it to obtain `Class<?>`.
- `className` uses slashes; `Class.getName()` uses dots. Two different loaders can receive the same `className`, so do not use the string as a unique class identity when true class identity is needed.
- `loader == null` usually means the defining loader is the bootstrap loader, not always missing information or an error.
- Do not call `Class.forName` indiscriminately inside the callback to "get the Class" for the name just seen: it can trigger class loading, recursion, and a class loader leak if the result is cached.
- Callbacks can run concurrently, so caches/counters must be thread-safe and have a capacity policy. Even when using weak references, concurrency and cleanup must be managed.

## 4. `WeakHashMap`: a weak key cannot save a value that points back to the key

A common suggestion is to replace `HashMap<ClassLoader, V>` with `WeakHashMap<ClassLoader, V>`. This approach is **only correct** if the **values do not strongly retain the loader key** (directly or indirectly).

**Wrong** example:

~~~java
// Wrong when the map outlives the plugin:
Map<ClassLoader, Class<?>> cache = new WeakHashMap<>();
cache.put(pluginLoader, pluginClass);
~~~

Why does it still retain the loader? `WeakHashMap` only holds the key via a weak reference, **but holds the value via a strong reference**. Because `pluginClass.getClassLoader() == pluginLoader`, the path becomes:

~~~text
GC root: Map held by the agent
       |
       v
WeakHashMap.Entry
       |
       +-- weak key -----> pluginLoader   (does not count as a strong path)
       |
       +-- strong value -> Class<PluginClass>
                              |
                              v
                          pluginLoader   (strong path!)
~~~

Therefore, value → `Class<?>` → loader can cause the weak key to **never become weakly reachable** while the map still holds the value. The same trap occurs if the value is a `Method`, `ClassLoader`, `Supplier` closing over a plugin object, or a `LoaderInfo` containing a class/loader.

The Oracle JDK `WeakHashMap` Javadoc explicitly states that values are strongly held and warns against values referring back to keys. When you want to use a weak map:

- The key can be the loader, but the value should be independent metrics/metadata, such as a `LongAdder` or an immutable value containing no loader/class.
- If the value must hold a plugin class or object, consider a **weak value** and a mechanism that tolerates cache entries disappearing; inspect the actual object graph.
- `WeakHashMap` is not synchronized. You can use `Collections.synchronizedMap`, and you must synchronize when iterating; for high throughput, consider another structure with a clear policy.
- Key disappearance depends on **GC**, so `map.size()` can change between two reads. Do not use the timing of entry removal as a deterministic callback or shutdown milestone.

**Still not a complete solution:** if another registry retains the plugin loader, a weak map cannot actively cause the loader to be GC'd. Weak references **do not remove** external strong reference paths.

## 5. `ClassValue<T>`: metadata attached to the class itself, not a global strong map

If you need to cache **information scoped per `Class<?>`**, Java 17 provides `ClassValue<T>`. This is an API to associate a lazily-computed value with a specific class, instead of creating your own `static Map<Class<?>, T>` that strongly holds keys.

Example:

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class PerClassCounters {
    private PerClassCounters() {}

    private static final ClassValue<LongAdder> COUNTS = new ClassValue<>() {
        @Override
        protected LongAdder computeValue(Class<?> type) {
            return new LongAdder();
        }
    };

    public static void count(Class<?> type) {
        COUNTS.get(type).increment();
    }

    public static long read(Class<?> type) {
        return COUNTS.get(type).sum();
    }

    public static void reset(Class<?> type) {
        COUNTS.remove(type);
    }
}
~~~

**This is a compilable Java class**, though running it requires a caller passing a target `Class<?>`. `ClassValue.get(type)` creates the per-class value when absent; `remove(type)` removes the association for that class, and a subsequent `get` may recompute it.

Design benefits:

- There is no self-created global `Map<Class<?>,...>` strongly retaining every observed class.
- Two classes with the same binary name defined by two different loaders receive **two independent values**.
- No need to pick a string ID assumed to be unique for the class loader when using internal metadata.
- Well suited for per-class metadata that does not need to enumerate the entire cache via a global registry.

**Do not turn `ClassValue` into a promise of automatic unloading:** you must still ensure no other strong roots retain the class/loader; the `LongAdder` value in the example does not retain the loader, but if you simultaneously put `Class<?>` into a static list, a leak can still exist. `ClassValue` also does not replace a policy for closing plugin-owned resources.

Concurrency note: if threads concurrently call `get`/`remove`, `computeValue` may be recomputed; keep side effects in `computeValue` minimal and compliant with its contract. `ClassValue` is great for per-class **caches**, but it is not an API to enumerate all live plugins.

## 6. `WeakReference` and `ReferenceQueue` for lifecycle observation

When you need to **track whether a loader can be GC'd yet** without pinning the loader yourself, use a weak reference:

~~~java
import java.lang.ref.WeakReference;

WeakReference<ClassLoader> watched = new WeakReference<>(pluginLoader);
// ... after all strong references are dropped:
ClassLoader maybeAlive = watched.get(); // may be null after an appropriate GC
~~~

This is an **illustrative snippet**, not a standalone file. `watched.get() != null` may simply be because **GC has not collected yet**, not necessarily a leak. `watched.get() == null` indicates the weak referent has been cleared; however, that does not mean every file handle, exporter, or external resource of the plugin has been cleaned up.

If you need to receive GC signals and clean up **metadata that does not point back to the loader**, you can use `ReferenceQueue`:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

// Implementation snippet placed inside a registry class:
private static final ReferenceQueue<ClassLoader> QUEUE = new ReferenceQueue<>();
private static final Map<Reference<? extends ClassLoader>, Integer> TAGS =
        new ConcurrentHashMap<>();

static void observeLoader(ClassLoader loader, int tag) {
    drain();
    TAGS.put(new WeakReference<>(loader, QUEUE), tag);
}

static void drain() {
    Reference<? extends ClassLoader> cleared;
    while ((cleared = QUEUE.poll()) != null) {
        TAGS.remove(cleared);
    }
}
~~~

**This is a code snippet to place inside a class**, not a standalone program. The registry strongly holds the **`WeakReference` object** so it does not vanish before being enqueued; `WeakReference` does not strongly hold the loader referent. `Integer tag` is independent data and **does not reference the loader**. `drain()` must be run according to an appropriate policy (on new events or periodically), because the queue will not automatically clean up `TAGS` if not polled.

**Do not use `ReferenceQueue` as a mandatory business cleanup mechanism:** GC may be delayed or may not run within the observation window. On undeploy, proactively unregister listeners, shut down executors, clear caches, and reclaim resources. A reference queue only assists with observing/cleaning up auxiliary metadata.

Another trap: using `ConcurrentHashMap<WeakReference<ClassLoader>, Value>` with newly created `WeakReference` instances on every lookup **does not provide lookup semantics by referent identity**. Weak references default to the identity of the reference object itself; to get proper weak-key map lookup you need a dedicated weak-key structure, queue cleanup, and race handling, not merely changing the key type.

## 7. Java 17+ experiment with a real agent: two loaders, one class name, two cache styles

Goals of the demo:

1. Two different defining class loaders define a class with the same name `PluginTask`.
2. The agent's transformer observes **two definitions** without **storing `ClassLoader`/`Class<?>`**.
3. `ClassValue` provides separate state for each `Class<?>`.
4. A global strong map and an intentionally misconfigured `WeakHashMap` show **reference paths that risk pinning a loader**.
5. Caches and the transformer are cleaned up via explicit calls.

**Scope of the test:** The program **does not use `System.gc()` as an assertion condition** and does not claim classes were unloaded. In `main`, local variables still hold loader/class objects up to certain points; the goal is to demonstrate **cache graphs and class identity**, not to measure GC timing.

### 7.1. File `PluginTask.java`

~~~java
public final class PluginTask {
    public String run() { return "plugin"; }
}
~~~

This class is **not** loaded by the application by referencing `PluginTask.class`. The program reads the `PluginTask.class` file as bytes, then defines the same binary name into two separate loaders.

### 7.2. File `PluginObserver.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.LongAdder;

public final class PluginObserver implements ClassFileTransformer {
    private final LongAdder observations = new LongAdder();

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
        if (!"PluginTask".equals(className)) return null;
        observations.increment();
        System.out.println("observer=PluginTask");
        return null;
    }

    public long observations() { return observations.sum(); }
}
~~~

The transformer receives `loader` but **does not put it into any field/map**; it only counts events with `LongAdder`. Returning `null` means **do not modify the bytecode**. The name `PluginTask` in the callback is in JVM internal name form (since the class is in the default package, it contains no slashes).

In a production agent, you should not `System.out.println` from every class-load callback because it can easily cause slow I/O or recursion. The demo prints only twice on a specific class for clear observation.

### 7.3. File `ObserverAgent.java`

~~~java
import java.lang.instrument.Instrumentation;

public final class ObserverAgent {
    private static Instrumentation instrumentation;
    private static PluginObserver observer;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        observer = new PluginObserver();
        inst.addTransformer(observer);
        System.out.println("agent=registered");
    }

    public static long count() { return observer.observations(); }

    public static void stop() {
        System.out.println("observer-removed=" +
                instrumentation.removeTransformer(observer));
        observer = null;
    }
}
~~~

A startup agent loaded before the application registers the transformer before the two plugin loaders define `PluginTask`. `stop()` removes the exact instance, then clears the agent's static reference to the transformer. In the demo there is only one registration.

If callbacks could still run concurrently with `stop()`, setting `observer = null` must be carefully managed in a real system (e.g., synchronization/in-flight accounting). Here `main` runs sequentially and no target class definitions occur when `stop()` is called.

### 7.4. File `LoaderCacheDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.WeakHashMap;

public final class LoaderCacheDemo {
    private static final Map<Class<?>, String> BAD_CLASS_CACHE = new HashMap<>();
    private static final Map<ClassLoader, Class<?>> BAD_WEAK_KEY_CACHE = new WeakHashMap<>();

    private static final ClassValue<Stats> PER_CLASS_STATS = new ClassValue<>() {
        @Override
        protected Stats computeValue(Class<?> type) { return new Stats(); }
    };

    private static final class Stats { int observations; }

    private static final class PluginLoader extends ClassLoader {
        PluginLoader() { super(null); }
        Class<?> definePlugin(byte[] bytes) {
            return defineClass("PluginTask", bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("PluginTask.class"));
        PluginLoader loaderA = new PluginLoader();
        PluginLoader loaderB = new PluginLoader();
        Class<?> classA = loaderA.definePlugin(bytes);
        Class<?> classB = loaderB.definePlugin(bytes);

        System.out.println("same-binary-name=" + classA.getName().equals(classB.getName()));
        System.out.println("same-class=" + (classA == classB));
        System.out.println("loader-a-matches=" + (classA.getClassLoader() == loaderA));
        System.out.println("agent-observations=" + ObserverAgent.count());

        PER_CLASS_STATS.get(classA).observations++;
        PER_CLASS_STATS.get(classB).observations += 2;
        System.out.println("per-class-counts=" +
                PER_CLASS_STATS.get(classA).observations + "," +
                PER_CLASS_STATS.get(classB).observations);
        BAD_CLASS_CACHE.put(classA, "metadata");
        BAD_WEAK_KEY_CACHE.put(loaderB, classB);
        System.out.println("strong-class-key-present=" +
                BAD_CLASS_CACHE.containsKey(classA));
        System.out.println("weak-value-references-key-loader=" +
                (BAD_WEAK_KEY_CACHE.get(loaderB).getClassLoader() == loaderB));

        BAD_CLASS_CACHE.clear();
        BAD_WEAK_KEY_CACHE.clear();
        System.out.println("cache-cleared=" +
                (BAD_CLASS_CACHE.isEmpty() && BAD_WEAK_KEY_CACHE.isEmpty()));
        ObserverAgent.stop();
    }
}
~~~

**Points to analyze carefully:**

- `PluginLoader() { super(null); }` uses only the bootstrap loader as its parent for the demo; `PluginTask` only depends on core JDK classes, so the class defined from bytes can run. This is **not a recommended class loading pattern for large applications**.
- `definePlugin(byte[])` calls `ClassLoader.defineClass("PluginTask",...)`, creating a `Class<?>` belonging to **that exact loader instance**.
- `classA` and `classB` have the **same binary name but different class identities**.
- `PER_CLASS_STATS` is a `ClassValue`, and the `Stats` value contains no class or loader; the two different classes have independent counts.
- `BAD_CLASS_CACHE` is a bad cache if it lives past undeploy. The `Class<?>` key is strongly held.
- `BAD_WEAK_KEY_CACHE` demonstrates the **weak key → strong value → defining loader trap**. The program prints a check of the reference path, not a GC benchmark.
- The two `clear()` calls are proactive cleanup. The output `cache-cleared=true` only says the two maps are empty; it **does not prove the loaders have been GC'd**, because local variables or other places may still hold references.

### 7.5. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: ObserverAgent
~~~

The lesson does not require `Can-Retransform-Classes` or `Can-Redefine-Classes`, because the transformer only observes the **first definition** of the two classes. Save the manifest with a trailing newline.

### 7.6. Compile and run

Create five files in the same directory:

~~~text
demo/
  PluginTask.java
  PluginObserver.java
  ObserverAgent.java
  LoaderCacheDemo.java
  agent.mf
~~~

The layout above consists of **four Java sources and one manifest**. Compile and package:

~~~bash
javac --release 17 PluginTask.java PluginObserver.java ObserverAgent.java LoaderCacheDemo.java

jar --create --file observer-agent.jar --manifest agent.mf ObserverAgent.class PluginObserver.class

java -javaagent:observer-agent.jar LoaderCacheDemo
~~~

**Stdout verified with `javac --release 17` on OpenJDK 24:**

~~~text
agent=registered
observer=PluginTask
observer=PluginTask
same-binary-name=true
same-class=false
loader-a-matches=true
agent-observations=2
per-class-counts=1,2
strong-class-key-present=true
weak-value-references-key-loader=true
cache-cleared=true
observer-removed=true
~~~

### 7.7. What do the results show — and what do they not show?

| Output | Justified conclusion | What must not be concluded |
| --- | --- | --- |
| `observer=PluginTask` appears twice | Two class definitions were observed by the transformer | How many GCs occurred |
| `same-binary-name=true` | The two classes have the same name `PluginTask` | The two classes can substitute instances/`Class<?>` for each other |
| `same-class=false` | `classA` and `classB` are two different `Class<?>` objects | A loader was unloaded |
| `per-class-counts=1,2` | `ClassValue` separates data by class identity | `ClassValue` alone resolves all references in the application |
| `strong-class-key-present=true` | The global map holds a strong reference to `classA` | The heap has only one root path |
| `weak-value-references-key-loader=true` | The weak map's strong value has a path back to its key loader | `WeakHashMap` protected the loader from leaking |
| `cache-cleared=true` | The two caches were proactively cleared | GC has definitely reclaimed the classes/loaders |
| `observer-removed=true` | The transformer registration was removed | Previously instrumented classes were reverted |

**Why not call `System.gc()` to print "unloaded=true"?** Because `System.gc()` is only a hint requesting GC, not an API guaranteeing class unloading. The JIT holding a local reference, another thread using the loader, the JVM delaying unloading, or GC flags can all produce different results. A proper test must distinguish **"no unwanted strong roots remain after teardown"** from **"GC has completed class unloading"**.

## 8. Designing an appropriate cache for real-world needs

| Need | Better choice | Conditions/limitations |
| --- | --- | --- |
| Metadata specific to a `Class<?>` | `ClassValue<V>` | Do not create your own global strong-key map; values should have minimal side effects and not pin the loader via other roots |
| Counters by **operation name** with a small label set | `ConcurrentHashMap<String, LongAdder>` with a capacity policy | Do not confuse class name with class identity; avoid unbounded cardinality |
| Per-loader metadata whose value does not point back to the loader | `WeakHashMap<ClassLoader, SimpleMetadata>` or a proper weak-key cache | Inspect the value graph, synchronization, and cleanup |
| Tracking loader GC | `WeakReference<ClassLoader>` + `ReferenceQueue` | Nondeterministic signal; not a mandatory cleanup mechanism |
| Caching reflection/method handles for a plugin | Cache owned by the plugin itself or sharing its lifecycle, closed on undeploy | An agent-wide strong cache of `Method`/`MethodHandle` can pin the loader |
| Caching bytecode by class name | Size- and time-bounded cache with sufficiently scoped keys | Bytes consume heap without directly retaining `Class`; avoid mixing up two loaders with the same name |
| Cases requiring a strong cache for operation | Map scoped to **deployment scope** with `close()/clear()` | Needs reliable teardown across all success/failure/redeploy paths |

Do not choose a cache type solely by the "fastest" criterion while ignoring **who owns the cache and who knows when the class loader's lifecycle ends**. A strong cache living inside the plugin's own classes usually expires with the loader if there are no external root paths. That exact same cache, if placed in a JVM-scope singleton/agent, will have a completely different lifecycle.

### Scoped cache, proactively closed

A simple pattern for a per-deployment cache:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class DeploymentCache implements AutoCloseable {
    private final Map<String, String> settings = new HashMap<>();

    public void put(String name, String value) {
        settings.put(name, value);
    }

    public String get(String name) {
        return settings.get(name);
    }

    @Override
    public void close() {
        settings.clear();
    }
}
~~~

This is a compilable Java class, but it only has meaning if **the owner itself** calls `close()` and **releases references to `DeploymentCache` itself** on undeploy. If the cache needs to hold `Class<?>` or plugin objects, place it within the same lifecycle and clear all references outside that scope. `AutoCloseable` does not make GC automatic; it only establishes a cleanup contract.

## 9. Safe teardown procedure for agents and plugins

When a deployment/plugin ends, check each layer of ownership:

1. **Stop new event sources**: stop accepting requests/jobs, stop registering callbacks or service listeners belonging to the plugin; avoid new callbacks starting to use state that is closing.
2. **Remove instrumentation registrations** no longer needed: call `Instrumentation.removeTransformer(transformer)` with the exact instance; manage callbacks that may still be in flight after removal.
3. **Stop threads and schedulers** created by the plugin/agent, waiting for bounded termination; do not leave threads depending on the old loader alive indefinitely.
4. **Clear `ThreadLocal` and restore TCCL** at the right ownership boundary. For shared thread pools, set/restore TCCL per task scope rather than simply killing shared pool threads.
5. **Unregister external registries**: JMX MBeans, listeners, hooks, exporter callbacks, service registrations, and shutdown hooks belonging to the plugin when appropriate.
6. **Close resources**: file handles/JARs, network clients, thread pools, and `URLClassLoader`-type class loaders if owned by the application (call `close()` to close JAR resources, noting that close **does not guarantee unloading**).
7. **Clear deployment-scoped caches**: do not leave values/reflection handles/`Class<?>`/`ClassLoader` from the old deployment in global singletons, and release lambdas/callbacks capturing them.
8. **Drop references to the context and loader** after cleanup, without altering references still needed by in-flight requests. Check roots from the agent, application server, and native code alike.
9. **Observe after one or more GC cycles** if needed using heap dumps, class loader statistics, and `-Xlog:class+unload`; understand that these are implementation observations, not synchronous GC guarantees.

Do not merely execute a "cache.clear" step while plugin threads are still running or static listeners are still receiving callbacks; doing so neither fixes the leak nor avoids races and `NullPointerException`.

### A callback option that does not retain the loader long-term

~~~java
// Illustrative snippet inside ClassFileTransformer:
if (!"com/acme/PluginEndpoint".equals(className)) {
    return null;
}
// Aggregated metric with a fixed label; do not put loader into a field/static map.
PLUGIN_ENDPOINT_DEFINITIONS.increment();
return null;
~~~

If a per-deployment identifier is needed for diagnostics, you can assign a **short-lived deployment ID that is released on undeploy**; do not use `System.identityHashCode(loader)` as a guaranteed globally unique key over time (values can collide and carry no ownership semantics).

## 10. Diagnosing class loader leaks with evidence instead of guessing GC

### 10.1. Observing loader counts and metaspace

With compatible HotSpot/OpenJDK builds, useful commands are:

~~~bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace
~~~

`<pid>` here is a **placeholder in a sample command**, not a shell token to copy verbatim; replace it with the actual Java process PID. The commands depend on the JVM/JDK in use and attach permissions to the process, and the output structure can vary across releases.

When investigating redeploy:

- Record a **baseline** of loader counts before deployment; redeploy multiple times with the same operations.
- Capture `VM.classloader_stats` after each teardown and after eligible GC opportunities; compare loader counts, class counts, and footprint.
- Observe `VM.metaspace` or related metrics, though **rising metaspace does not by itself prove a loader leak**; the JVM may retain committed memory for reuse.
- Do not use the JVM-wide loaded class count as the sole indicator. A system using dynamic proxies, reflection, lambdas, JIT, or hidden classes can normally load new classes.

You can enable HotSpot unified logging to observe class unloading:

~~~bash
java -Xlog:class+unload=info -javaagent:agent.jar -jar application.jar
~~~

This is a **production sample command**, not the command to run the demo in section 7. When you know the JVM supports unified logging, class unload events prove that unloading occurred; **not seeing an event immediately** does not definitively prove a leak.

### 10.2. Heap dumps and GC roots

If many loaders from old versions persist after multiple redeploys, take a heap dump/flight recording following a safe procedure and inspect **retained paths to GC roots**:

~~~text
JVM static root
  -> AgentRegistry
  -> HashMap entry
  -> java.lang.Class<OldPlugin>
  -> OldPluginClassLoader
~~~

Or:

~~~text
Worker Thread (long-lived)
  -> contextClassLoader
  -> OldPluginClassLoader
~~~

Or:

~~~text
System listener registry
  -> plugin callback/lambda
  -> plugin object
  -> OldPluginClassLoader
~~~

Heap dumps can be large, increase pauses/memory/disk I/O, and contain sensitive data; take them only when authorized, with sufficient disk space and data protection policies. Heap analysis tools can help distinguish **retained bytes** from **shallow size** and pinpoint which exact reference must be removed. Do not assume a loader should be deleted just because it appears in a heap dump: verify that it genuinely belongs to a finished deployment.

### 10.3. A more meaningful GC test than a single `System.gc()`

To test unloading behavior in an isolated environment:

- Define the plugin with a separate loader, run its task, then **complete the plugin's lifecycle**.
- Unregister callbacks/transformers, close resources, clear caches, and leave the scope holding strong local variables.
- Keep a **`WeakReference<ClassLoader>`** for observation, without additionally holding `Class<?>`/loader in a static cache or closure.
- Give the JVM opportunities to GC in the test environment, combining logs/statistics/weak-reference observations.
- If the weak reference has not cleared, inspect GC roots to find what retains it. **Do not use a short timeout** to assert absolute program correctness/failure because GC/class unloading has no API-guaranteed deadline.

The ultimate goal is **no unwanted strong reference paths remaining from roots to an expired loader**, not "GC must happen within 100 ms".

## 11. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| "Using `WeakHashMap` guarantees the loader will unload." | Values are strongly held; a value can point back to the key via `Class<?>` | Inspect the full key/value graph; use weak values or metadata without loader refs |
| "Storing `Class<?>` is safer than storing `ClassLoader`." | A plugin's `Class<?>` is still tied to its defining loader | Avoid keeping either in a long-lived global cache |
| "The cache only stores `Method`, so it does not retain the class." | Reflection `Method` references its declaring class | Cache per deployment or use metadata that does not own the method |
| "The agent only holds the transformer, not the loader." | The transformer may close over the loader, helpers, lookups, or plugin objects | Inspect captured state; remove registration and clear strong references |
| "`removeTransformer` is enough to remove the agent." | Only unregisters the callback; bytecode, threads, metrics exports, and other refs remain | Perform full resource teardown; do not confuse with unload/revert |
| "Closing the class loader's JAR file means it is unloaded." | `URLClassLoader.close()` closes class-lookup resources, without guaranteeing class/loader GC | Close then drop refs; observe class unloading |
| "Two classes with the same name are the same class." | The defining loader forms the second part of identity | Check `Class.getClassLoader()`/module; do not cache solely by name |
| "`ClassValue` makes all leaks disappear." | External roots can retain the loader regardless of per-class caches | Evaluate the entire GC root chain |
| "No class unload events means there is definitely a leak." | GC/class unloading is not required on a fixed schedule | Compare across multiple cycles; use heap analysis |
| "If a weak reference remains after calling `System.gc()`, it is a bug." | `System.gc()` is neither synchronous nor a mandatory unloading contract | Do not assert timing; trace strong paths if persistence continues |
| "Caching by class name is never wrong." | Two loaders can load the same binary name; data can get mixed up | Tie ownership to deployment or proper per-class identity |
| "Counting every callback requires storing every `Class<?>`." | Counting events does not require a strong class map | Use low-cardinality labeled counters without storing loader/Class if unused |
| "Closing the plugin will automatically free `ThreadLocal`." | Shared thread pools can outlive the plugin and retain old values | `ThreadLocal.remove()` and TCCL restoration in `finally` |
| "`ClassValue` can enumerate all cached classes." | `ClassValue` is designed for per-type lazy association, not global key listing | Use bounded telemetry and separate ownership for discovery |

## 12. Design checklist for a Java agent used with hot deployment

- [ ] Does it distinguish **binary class name** from **class identity = name + defining loader**?
- [ ] **Where** are `Class<?>`/`ClassLoader`/`Method`/`MethodHandle` held, by which roots, and for how long?
- [ ] Does the cache belong to the long-lived agent or to a short-lived deployment? Who has the authority/lifecycle to clear it?
- [ ] Does the transformer hold a plugin loader in a field, closure, or helper?
- [ ] Is `removeTransformer` called with the **exact instance**, while waiting for/tolerating in-flight callbacks?
- [ ] Does it avoid storing unnecessary objects from `transform(Module, ClassLoader, ..., Class<?>, ...)`?
- [ ] Do `WeakHashMap` values have any strong reference back to the key? Were nested objects/lambdas checked?
- [ ] Can per-class metadata use `ClassValue` instead of a static strong `Map<Class<?>, V>`?
- [ ] Do weak registries using `ReferenceQueue` have a poll/drain policy and avoid relying on GC for business cleanup?
- [ ] Have thread pools, TCCL, `ThreadLocal`, listeners, MBeans, exporters, and scheduled tasks been cleaned up?
- [ ] Are `URLClassLoader`/resources closed when the owner genuinely finishes, without confusing close with unload?
- [ ] Are log/metric labels sufficient to distinguish deployments without holding strong loader references or unbounded cardinality?
- [ ] Have multiple redeploy cycles been tested, comparing classloader counts, heap retained paths, metaspace, and class unload logs?
- [ ] Is it documented that **GC is nondeterministic** and `System.gc()` does not guarantee class unloading?
- [ ] Is there a rollback plan if a missing helper/agent class leads to `NoClassDefFoundError` after undeploy?

### Comprehension check scenarios

**1.** An agent's static `ConcurrentHashMap<Class<?>, Metadata>` contains an entry for an old plugin, even though the application cleared its instance and called `URLClassLoader.close()`. Could there be a class loader leak?

**Answer:** Yes. The `Class` object is still strongly held by the agent's static map; closing resources does not eliminate that GC root path.

**2.** Using `WeakHashMap<ClassLoader, Class<?>>` with a weak key and a value that is a class defined by that key loader. Is this safe?

**Answer:** No. The `Class<?>` value is strongly held by the map and has a reference path to the key loader; the key is unlikely/unable to become weakly reachable while the entry exists.

**3.** Two loaders A/B define classes with the same name, using `ClassValue<Counter>`. Can the counters be independent?

**Answer:** Yes. Two different `Class<?>` objects will have separate associated values. This is why using `ClassValue` for per-class metadata is more suitable than a cache keyed only by binary name.

**4.** The transformer has been removed and the map cleared; however, a plugin thread still has its TCCL set to the old loader. Can it unload yet?

**Answer:** You should not expect it to. A live thread holding the context loader creates another strong reference path; you must manage TCCL and thread lifecycle.

**5.** `WeakReference.get() != null` after one `System.gc()` call. Can you conclude there is definitely a leak?

**Answer:** No. You need to check whether GC had sufficient opportunity to run, whether local refs remain in scope, whether the JIT/VM temporarily holds references, and look for real GC root paths in a heap dump if the symptom persists.

**6.** Do `removeTransformer(t) == true` and `cache.clear()` mean the instrumentation bytecode in already-loaded classes has been removed?

**Answer:** No. Removing the transformer only unregisters the callback; modified class definitions can continue to be used. **Releasing references** and **reverting bytecode** are two independent tasks.

**Conclusion:** In instrumentation, what matters is not only *"what data the agent holds"* but *"how long that data lives, who still holds it, and which class loader it leads to"*. Per-class caches must respect class lifecycles; per-loader caches must not create backward reference paths from values; and teardown must proactively clear long-lived roots. Only when unnecessary strong reference paths are removed **does the JVM get the opportunity** to unload the old class loader in an appropriate GC cycle.

### Official documentation

- [Java SE 17 — `ClassValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): per-class associated values, `get`/`computeValue`/`remove`.
- [Java SE 17 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values, and the trap of values referencing keys back.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html) and [`ReferenceQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): weak reachability and notification queue.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `addTransformer`, `removeTransformer`, and concurrent callback contracts.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks and class loader identity during transformation.
- [JDK 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`.
