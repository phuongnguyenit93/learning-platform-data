# Caches Holding `Class` Can Retain the Entire ClassLoader: Reflection Metadata Lifecycle in Java

## 1. The Problem: Caching Improves Speed but Can Keep Plugins in Memory

A framework using Reflection often has to look up the same class repeatedly: lists of fields, methods, constructors, annotations, data mappers, `MethodHandle`s, or serialization configurations. Caching those results reduces the cost of metadata discovery and adapter construction.

However, in applications that **load and unload plugins**, module-redeployment environments, application servers, or programs that dynamically create many classloaders, a **cache that outlives a classloader** can prevent old classes from being reclaimed. For example:

~~~java
// Illustrating the risk: static map living for the entire application.
static final Map<Class<?>, Metadata> CACHE = new ConcurrentHashMap<>();
~~~

If `Class<?>` in the map is a class loaded by a plugin's loader, the entry is held by a **strong reference**. Under normal conditions, this reference chain can keep the `Class` and its defining classloader reachable, thereby blocking collection of the classloader and the classes managed by that loader.

**The root cause is a lifecycle mismatch:** the application's cache component is long-lived, whereas plugins and the classes they load must be releasable after unloading. This does not mean every `Class` cache causes a bug. If all classes share the application's lifetime, a bounded cache can be completely reasonable. The issue arises when a cache **outlives the class-loading namespace** it holds.

After this lesson, you will know how to identify retention paths, choose caches with appropriate scope, use `ClassValue` and weak-key caches properly, verify with diagnostic tools, and avoid ineffective fixes.

## 2. Recall Type Identity and Classloaders

In Java, **a binary name alone is not enough to identify a runtime type**. The defining classloader is part of type identity. Two classes with the same `getName()` defined by two different loaders can be two distinct `Class<?>` objects:

~~~text
Main application: AppClassLoader
    └── com.example.PluginApi       → Class A

Separately loaded plugin: PluginClassLoader
    └── com.example.PluginApi       → Class B

A.getName().equals(B.getName())     → true
A == B                              → false
~~~

This is an illustrative scenario, not two definitions in the same package within a single standalone source file. In a real program, you must check whether a loader **delegates to its parent** or **defines the class itself**. A child loader can return a `Class` already defined by the parent loader; that does not create a new type.

Class unloading is a JVM capability during memory management: according to the Java Language Specification, a class/interface **may** be unloaded when its defining classloader can be reclaimed by GC. Whether a class is actually unloaded and when it happens is decided by the JVM; applications must not rely on class unloading happening immediately.

Two points to distinguish:

- **The `Class<?>` object is the metadata gateway for a specific type.** If code outside the plugin holds a strong reference to this object, the defining classloader can continue to be retained.
- **A live classloader** can retain much more than a single class: metadata of loaded classes, links between them, and related objects. Thus, a single small cache entry can keep a substantial amount of memory from being reclaimed.

## 3. Reference Paths That Retain a ClassLoader

Suppose a cache resides in a class of the main application, which typically lives until the program ends:

~~~text
GC Root: Class/static field of the main application
      ↓
ConcurrentHashMap (long-lived cache)
      ↓
entry: key is plugin's Class<?>       [strong]
      ↓
Class metadata / runtime type
      ↓
defining PluginClassLoader
      ↓
related classes/metadata of the plugin
~~~

This is a **conceptual reachability diagram**, not a strict description of every internal edge in every JVM. When analyzing a heap dump, the reference path may contain different intermediate objects and edges than shown above.

Common retention patterns include:

- `Map<Class<?>, ...>`, `Set<Class<?>>`, or lists of `Class<?>` stored in singletons or static registries.
- `Map<String, Method>` or `Map<String, Field>`. **Using a `String` key does not remove the risk** if the value is a Reflection object referencing the plugin's declaring class.
- Caches holding `Constructor<?>`, `MethodHandle`, `MethodType`, `CallSite`, factories, lambdas, plugin instances, or objects with fields referencing those components.
- Structures that do not directly hold `Class`, yet whose values contain classes, classloaders, plugin objects, or `ThreadLocal` data surviving in a thread pool.
- Running threads whose **thread context class loader (TCCL)** still points to the plugin loader after the plugin is no longer used.

Therefore, diagnostics must ask **what is still holding strong references to what, and for how long**, rather than only searching for variables named `CACHE`.

## 4. Standalone Java 17+ Example: Same Name, Two Loaders, One Strong Cache

This example creates two `Class` objects for one name, where the second class is **defined directly** by a child loader. It does not depend on whether GC runs; the program checks type identity and the fact that the strong cache holds the entry.

Create the file `ClassCacheLifetimeDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ClassCacheLifetimeDemo {
    record Metadata(String binaryName, int methodCount) {}

    static final Map<Class<?>, Metadata> STRONG_CACHE =
            new ConcurrentHashMap<>();

    static final ClassValue<Metadata> CLASS_METADATA = new ClassValue<>() {
        @Override
        protected Metadata computeValue(Class<?> type) {
            return new Metadata(
                    type.getName(), type.getDeclaredMethods().length);
        }
    };

    // Only for the name PluginPayload, this loader defines the class itself.
    static final class IsolatedLoader extends ClassLoader {
        private final String isolatedName;

        IsolatedLoader(ClassLoader parent, String isolatedName) {
            super(parent);
            this.isolatedName = isolatedName;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(isolatedName)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent()
                            .getResourceAsStream(resource)) {
                        if (in == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = in.readAllBytes();
                        result = defineClass(
                                name, bytes, 0, bytes.length);
                    } catch (IOException ex) {
                        throw new ClassNotFoundException(name, ex);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> hostType = PluginPayload.class;
        ClassLoader pluginLoader = new IsolatedLoader(
                hostType.getClassLoader(), hostType.getName());
        Class<?> pluginType = Class.forName(
                hostType.getName(), false, pluginLoader);

        System.out.println("same name: "
                + hostType.getName().equals(pluginType.getName()));
        System.out.println("same Class: " + (hostType == pluginType));
        System.out.println("defined by child: "
                + (pluginType.getClassLoader() == pluginLoader));

        Metadata data = new Metadata(
                pluginType.getName(),
                pluginType.getDeclaredMethods().length);
        STRONG_CACHE.put(pluginType, data);
        System.out.println("strong entries: " + STRONG_CACHE.size());

        Metadata fromClassValue = CLASS_METADATA.get(pluginType);
        System.out.println("ClassValue result: "
                + fromClassValue.binaryName().equals(pluginType.getName()));

        // Actively remove the reference held by the application in the map.
        STRONG_CACHE.remove(pluginType);
        System.out.println("strong entries after remove: "
                + STRONG_CACHE.size());
    }
}

// Same source file: javac also generates PluginPayload.class.
class PluginPayload {
    public int answer() {
        return 42;
    }
}
~~~

Run commands (from the directory containing the file):

~~~bash
javac ClassCacheLifetimeDemo.java
java ClassCacheLifetimeDemo
~~~

Deterministic output:

~~~text
same name: true
same Class: false
defined by child: true
strong entries: 1
ClassValue result: true
strong entries after remove: 0
~~~

**Explanation:**

1. `PluginPayload.class` is the type seen by the application's normal loader. `IsolatedLoader` reads the bytecode itself and calls `defineClass` for **the exact same name `PluginPayload`**, so `pluginType` differs from `hostType` despite having the same name.
2. The entry `STRONG_CACHE.put(pluginType, data)` strongly holds the `Class` object as a key while the map remains alive. If this code were a long-lived registry, the entry could retain the old loader/plugin.
3. `ClassValue.get(pluginType)` creates metadata bound **to that exact `Class<?>`**, suitable for data computed once per type.
4. `STRONG_CACHE.remove(pluginType)` drops the reference **from the map**. Local variables `pluginType`, `pluginLoader`, metadata, and other JVM references may still exist while the program runs. **You must not infer that the loader has unloaded** solely from `size() == 0`.

This program illustrates cache mechanics and ownership; it **does not use `System.gc()`, `finalize()`, or sleeps** to produce an unreliable GC result. `IsolatedLoader` is a learning tool, not a production plugin loader with full resource, security, and module boundary handling.

## 5. Why Keying by `Class<?>` Differs from Keying by Class Name

Look at two ways to organize a cache:

~~~java
Map<Class<?>, Metadata> byClass = new ConcurrentHashMap<>();
Map<String, Metadata> byName = new ConcurrentHashMap<>();
~~~

*This is a fragment: it requires `Metadata` and importing `Map` and `ConcurrentHashMap` as in the example above.*

### Caching by `Class<?>`

**Pros:** automatically distinguishes types with the same name defined by different loaders; looks up by exact runtime type; convenient for Reflection.

**Risks:** a long-lived map with strong keys can retain classes and loaders no longer used by the application. If the cache lacks a per-plugin eviction policy, entries accumulate across reloads.

### Caching by `String`

**Pros:** the class name `String` itself does not necessarily hold a classloader. It can fit loader-independent content, such as normalized display names.

**Risks:** two plugins can have classes with the same `binaryName` yet different metadata. Using only the name as a key **can return the wrong data**. Moreover, if `Metadata` in the value holds a `Class`, `Method`, `Field`, or plugin instance, a `Map<String, Metadata>` cache can still retain the loader. Switching keys to `String` is not a general fix.

**Choose keys based on domain identity.** If a cache needs a plugin namespace, you can construct a logical key `pluginId + pluginGeneration + className` (including reload version/generation) and **remove entries** when unloading the plugin. When using `Class<?>`, apply an appropriate cache scope or one of the lifecycle solutions below.

## 6. Option 1: Scoped Cache with Active Removal

The simplest approach is to **align the cache with the proper lifecycle**:

~~~text
PluginSession #42
  ├── loader
  ├── services
  └── metadata cache used only for session #42

When unloading the session:
  1. Stop new calls, wait for running work to complete
  2. Unregister handlers, listeners, tasks, timers, ThreadLocals
  3. Clear metadata cache and references to services/loader
  4. Close loader resources supporting close() if appropriate
  5. Let the JVM decide GC and class unloading
~~~

If a static cache holds multiple plugins, organize namespaces by `pluginId` with an `evictPlugin(id)` method. **Concurrency must be controlled:** do not evict entries while old requests are still using them and then declare the plugin unloaded; transition the plugin to stop accepting new work, finish in-flight tasks, and unregister all reference holders.

Use a size-bounded or time-expiring cache API when the goal is overall memory control. However, expiration policies **do not guarantee** a loader is unloaded on time if entries are still accessed, and do not replace lifecycle cleanup for other resources.

**Best suited when:** plugins have an explicit lifecycle, modules are redeployed, or the cache holds multiple components (metadata, instances, handlers) where weak GC cannot handle unregistration/resource cleanup.

## 7. Option 2: `ClassValue<T>` for Per-`Class` Metadata

`java.lang.ClassValue<T>` is Java's standard API for **attaching lazily computed values per `Class<?>`**. It is especially well suited for metadata derived from the class itself: field mappings, serializer info, and framework descriptors.

~~~java
static final ClassValue<Field[]> DECLARED_FIELDS = new ClassValue<>() {
    @Override
    protected Field[] computeValue(Class<?> type) {
        return type.getDeclaredFields();
    }
};

Field[] fields = DECLARED_FIELDS.get(SomeType.class);
~~~

*This fragment requires `import java.lang.reflect.Field;` and an existing `SomeType` class.*

Key characteristics:

- Values are bound to the **exact `Class<?>`**, so two classes with the same name under different loaders can receive separate metadata.
- `get(type)` computes data on demand via `computeValue(type)`; under multi-threaded contention, `computeValue` **may be invoked multiple times**, even though one value is accepted for that binding. Do not perform non-repeatable side effects or unconditional resource registrations inside `computeValue`.
- `remove(type)` removes the `ClassValue` binding for that class; the next `get` can recompute. This is **metadata invalidation**, not a class-unload command, nor does it clear references held by external code.
- Unlike a `static Map<Class<?>, V>` in the application, `ClassValue` is designed to associate values with the lifetime of `Class` without using a global map that strongly retains type keys in the usual way. It helps avoid **one source** of loader retention; it does not guarantee unloading if elsewhere something still holds the class, loader, or value.

If `Field[]` in the example is a cached array, **do not let callers mutate the shared array directly** if that could affect other components; return a copy or immutable metadata when needed. `ClassValue` guarantees the association mechanism, **not that the value object itself is immutable or thread-safe**.

Also distinguish `ClassValue` from `ThreadLocal`: `ClassValue` associates per **class**, not per thread. This is usually an advantage for metadata shared across many threads; internal synchronization of the value remains a design responsibility.

**Best suited when:** data is derived from a class, accessed repeatedly, should live with the class's lifecycle, and you do not need to enumerate all entries for reporting.

## 8. Option 3: `WeakHashMap<Class<?>, V>` — You Must Check the Value Too

`WeakHashMap` stores **keys via weak references**. When a key is no longer strongly referenced elsewhere, GC can reclaim it and the entry will be removed. This is an option to consider for some caches, yet it has a major trap: **values in `WeakHashMap` are still strongly referenced**.

Example that **does not break the retention cycle**:

~~~java
Map<Class<?>, Method> methods = new WeakHashMap<>();

Class<?> type = ...;
Method method = type.getDeclaredMethod("run");
methods.put(type, method);
~~~

*Illustrative fragment assuming `type` has a `run` method and lookup exceptions are handled.*

The reference path can look like:

~~~text
Global WeakHashMap
    │
    ├── key (weak) ─────→ plugin's Class<?>
    │
    └── value (strong) ─→ Method
                             └── declaring Class<?> of the plugin
                                      └── plugin loader
~~~

The `Method` value holds a strong reference path back to **the very class used as the key**. Thus the key may never become eligible for GC, and using weak keys fails to deliver the expected effect.

Similarly, values that are `MethodHandle`s, metadata objects holding `Class<?>`, `Field[]` arrays, or lambdas capturing plugin classes/instances can retain the key directly or indirectly. You can use values containing only immutable data independent of the class, or you need an *ephemeron*-style cache structure handling reference cycles; **do not assume `WeakHashMap` is an ephemeron map**.

Notes:

- `WeakHashMap` is **not thread-safe** by default. For concurrent access, use appropriate synchronization or another option; `Collections.synchronizedMap(...)` only synchronizes operations per the wrapper contract and does not solve values retaining keys.
- Entry counts can change due to GC; `size()` is not a stable metric for business logic or snapshot tests.
- Weak references **do not force GC to run immediately**; do not write tests expecting an entry to vanish after `System.gc()`.
- Weak values (`WeakReference<V>`) also have trade-offs: data can be reclaimed quickly and recomputed frequently; correctness and concurrency still must be guaranteed.

**Best suited when:** you clearly understand the retention paths of both keys and values, metadata does not point back to the key, and GC-driven eviction is acceptable. For typical per-class caches, `ClassValue` is usually the option to try first.

## 9. Caching `Method`, `Field`, `MethodHandle`, and Proxies Can Also Retain Classloaders

The danger does not live solely in the key's generic type.

| Cache Contains | Why Reference Paths Matter | How to Handle |
| --- | --- | --- |
| `Class<?>` | Tied to the class's runtime identity and defining loader | Limit scope, evict actively, or use `ClassValue` |
| `Method` / `Constructor<?>` | Member metadata belonging to declaring class | Do not retain in global registries beyond plugin lifetime |
| `Field` | References declaring class's field | Cache in appropriate class/scope and remove on unload |
| `MethodHandle` / `MethodType` | Can reference classes, members, adapters, and related types | Inspect the value graph, not just the cache key |
| `Proxy` instance / `InvocationHandler` | Instance, handler, and interfaces/proxy class can anchor the plugin | Unregister listeners/handlers, stop running work |
| Lambdas/factories/callbacks | May capture plugin instances or classes/loaders | Unregister per lifecycle, avoid static holders |
| `ThreadLocal` and TCCL | Application thread pools can outlive plugins | `remove()` `ThreadLocal`, restore context loader, finish tasks |
| `ClassValue<V>` | Attaches metadata per class with managed association | Do not leak values into long-lived global holders; consider `remove` when invalidating |

A common example: a **static map in a class loaded by `AppClassLoader`** holds a plugin's `Method`. Even if the map uses `String` keys, the value contains a reflective member whose reference path can retain the plugin loader. When redeploying the plugin, the old `Method` is not a method of the new class merely because the two classes share a name.

## 10. Lifecycle Cleanup: What Is the Plugin System's Responsibility?

A plugin load/unload system should define cleanup steps with clear ownership:

1. **Stop using the old plugin.** Block new requests, finish or cancel running tasks, callbacks, or related timers.
2. **Unregister long-lived objects.** Remove listeners, interceptors, registries, event bus subscriptions, drivers/providers, or services holding plugin instances.
3. **Clear caches per plugin/classloader.** Both keys and values can retain metadata; inspect singletons and static fields of the host application.
4. **Clean up threads and context.** Restore TCCL after each unit of work; clear plugin `ThreadLocal`s from application-managed threads; avoid threads running plugin code indefinitely.
5. **Close closeable resources.** For instance, `URLClassLoader.close()` stops loading new resources/JARs and releases related resources per the API; **calling `close()` does not automatically unload already-loaded classes**.
6. **Only after no required strong references remain** can you expect the loader to *possibly* become eligible for GC. The JVM decides when to collect and unload classes.

Avoid running cleanup in `finalize()` or treating `System.gc()` as a required operational mechanism. Lifecycle cleanup must be active, observable, and error-handled behavior.

### A New `ClassLoader` Created on Each Reload

If a plugin is reloaded multiple times, each loader generation may hold its own version of the same class name. When registering caches or callbacks, attach *generation* metadata to avoid serving stale metadata to the new plugin.

Logical example:

~~~text
plugin: payments
generation: 17 → loader A → com.example.Handler (Class A)
generation: 18 → loader B → com.example.Handler (Class B)

Same class name, Class A != Class B.
Caches/handlers of generation 17 must be released per lifecycle.
~~~

A new class with the same name does not automatically delete entries held by the main application for the old class.

## 11. Practical Diagnostics: Heap, Class Unloading, and Paths to GC Roots

If memory grows after each redeploy cycle, measure and identify the retention source.

### 11.1. Symptoms to Distinguish

- **Heap growth:** may come from live cache values/instances/plugin registries; the heap is not the entirety of JVM memory.
- **Metaspace growth:** may relate to class/loader counts and class unloading behavior, yet also depends on GC policy, workload, and normal class loading.
- **Old classloader count does not drop after plugin removal:** inspect lifecycle, actual GC activity, and whether strong reference paths remain. Do not conclude from a single observation.

A large, bounded, properly functioning cache may be an intentional trade-off. For leaks, prioritize evidence of **objects no longer needed that are still kept alive through GC roots**.

### 11.2. Using HotSpot/JDK Tools When Appropriate

On a HotSpot JVM with built-in diagnostic tools:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

For example, this command can display classloader statistics; availability and command names depend on the JVM/JDK. `<pid>` is the actual process ID—do not enter angle brackets literally in the shell.

When actively enabling logging in a HotSpot test environment:

~~~bash
java -Xlog:class+unload=info YourApplication
~~~

Class unload log lines show actual unload events; **seeing no log lines** during a short window does not by itself prove a leak, because the JVM may not have run class unloading yet.

With Native Memory Tracking (requires proper startup flags if supported by the JVM), you can inspect overall native memory/metaspace with the corresponding tool. Do not use a single NMT figure alone to blame a cache.

### 11.3. Heap Dump: Finding Paths from Retained Objects to GC Roots

In a heap analyzer such as Eclipse Memory Analyzer or VisualVM (depending on environment):

1. Locate **old plugin classloaders**, grouped by type and count.
2. Pick a loader that should no longer be in use, inspect **path to GC roots** and strong references holding the loader, `Class`, or plugin reflective members.
3. Trace back to long-lived components: static maps, singletons, threads, `ThreadLocal`, TCCL, listeners, callbacks, or cache values.
4. Inspect the value graph too: weak keys do not help if values retain keys.
5. Fix the actual retention points and repeat load/unload cycles under the same test conditions.

Heap dumps must be handled carefully because they may contain sensitive application data. Diagnose only in authorized environments and limit data scope as needed.

## 12. Testing Strategies Without Depending on Timely GC

You can reliably test **cache lifecycle**, even when you cannot force the JVM to reclaim a classloader immediately:

- Load a new plugin generation and assert that the new generation's `Class<?>` **differs** from the old generation's class when the loader defines the type itself.
- Verify the cache is scoped or keyed by generation so it never returns stale metadata.
- After calling `unloadPlugin(id)`, assert the application's registry no longer contains entries/callbacks/tasks owned by that plugin; this can be checked via remaining entry counts or registration lists.
- For `ClassValue`, test `get`, `remove`, and recomputation through a `computeValue` function without non-repeatable side effects. Do not assume `computeValue` is invoked only once when running concurrently.
- For weak references, record GC reclaiming a loader only as a supporting signal in **controlled integration tests**. Do not write assertions like “call `System.gc()` and then `weakRef.get() == null` must hold.”

Example self-check for cache ownership logic:

~~~java
Map<Class<?>, Metadata> cache = new HashMap<>();
cache.put(pluginType, metadata);

// After the lifecycle unregister/evict step:
cache.remove(pluginType);
if (cache.containsKey(pluginType)) {
    throw new AssertionError("Plugin cache entry remains");
}
~~~

*This fragment assumes types/variables are already declared; it checks entry removal and does not assert that the JVM unloaded the class.*

Do not confuse **“our code dropped the references it owns”** with **“the JVM reclaimed all plugin data.”** A third-party library or another thread may still hold references.

## 13. Reflection Cache Selection Checklist

| Need | Usually Suitable Choice | What to Verify |
| --- | --- | --- |
| Metadata used only within one request/task | Local variable or per-request cache | Do not store into a singleton |
| Per-class metadata used repeatedly | `ClassValue<V>` | Pure `computeValue`, thread-safe value, no global holder retaining it |
| Plugin with clear lifecycle and many associated resources | Per-plugin cache, `evictPlugin` | Complete unregistration and wait for old tasks to finish |
| Shared cache with size/time bounds | Bounded/expiring cache | How long keys/values retain loaders, whether recomputation occurs too often |
| Weak-key cache when values are key-independent | `WeakHashMap<Class<?>, V>` (with caution) | Values do not point back to class; concurrency and GC |
| Long-lived registry of all system classes | Registry with explicit ownership | Must have a policy to remove plugin classes on unload |
| Only keeping plugin-independent display names | `String` or immutable DTO | Never use name alone as runtime identity across multiple loaders |

There is no single optimal cache for every case. Start from **who owns the metadata**, **when the data expires**, **whether multiple loaders exist**, and **what references the values hold**.

## 14. Common Misconceptions

**“`Class<?>` is just a lightweight name; keeping it won't affect the loader.”** False. It represents a specific runtime type tied to its defining classloader.

**“Just change `Map<Class<?>, V>` to `Map<String, V>`.”** Not necessarily. Values can still hold classes, methods, or instances; and plain name keys can collide across plugin generations.

**“`WeakHashMap<Class<?>, Method>` guarantees no leaks.”** False if `Method` holds a reference path back to its declaring class used as the key. Values are strongly held.

**“`ClassValue` guarantees the JVM unloads classes immediately.”** False. It helps organize metadata per class, but a loader is only eligible for collection when no other strong reference paths remain; the JVM makes no timing guarantee for unloading.

**“Calling `URLClassLoader.close()` unloads all classes.”** False. `close()` closes the resource source/ability to load additional classes/resources per the API, not a command to unload existing `Class` objects.

**“Seeing no unload logs proves a memory leak.”** Insufficient. Check whether a suitable GC/class-unloading cycle has occurred and whether any reference path still retains the loader.

**“Only static fields cause leaks.”** Incorrect. Thread pools, TCCL, callbacks, listeners, timers, container instances, and cache values can all be retention sources.

## 15. Self-Check

1. Why can `static Map<Class<?>, Metadata>` retain a plugin after removal? **The `Class` key is strongly held by a long-lived map and can retain the loader along with related classes.**
2. Are two classes with the same `getName()` but different defining loaders always the same type? **No.**
3. Is `WeakHashMap<Class<?>, Method>` automatically safe for class unloading? **No, because the `Method` value can retain the declaring class/key.**
4. Metadata should be attached per `Class` without needing to enumerate the whole cache: which API should you try? **`ClassValue<T>`.**
5. Does calling `ClassValue.remove(type)` force the JVM to unload the class? **No.** It only removes the corresponding metadata binding.
6. When reloading a plugin, besides caches, what else must be cleaned up? **Callbacks, listeners, tasks, `ThreadLocal`s, TCCL, instances, and resources still owned by the system.**
7. Why shouldn't you call `System.gc()` and assert the loader disappeared? **GC/class unloading has no guaranteed timing; results can be flaky.**
8. If a map uses `String` keys while values are `Method` objects from a plugin, is there still a risk of retaining the loader? **Yes.**

## 16. Conclusion

Caching Reflection metadata is a sensible optimization, yet a single strong reference to a `Class<?>`, `Method`, `Field`, `MethodHandle`, or plugin instance can extend the lifetime of **the entire classloader**. What is essential is designing **caches aligned with data lifecycle**, distinguishing type identity by loader, actively clearing registrations on plugin unload, using `ClassValue` when values belong per class, and avoiding confusing weak keys with values that still retain classes.

When a leak is suspected, verify via paths from GC roots and classloader/metaspace metrics over time. An entry disappearing from a cache only proves one retention source was dropped; whether the JVM unloads classes still depends on the entire reference graph and GC execution.

### References

- [Java SE 21 — `ClassValue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html)
- [Java SE 21 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html)
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 21 — `URLClassLoader.close`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html)
- [JLS `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7)