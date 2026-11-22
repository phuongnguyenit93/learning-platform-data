# Static Fields, Reflection Caches, and References from the Host Application

> **Java Core → ClassLoader → Class Unloading and Memory.** In a plugin architecture, simply calling `URLClassLoader.close()` does not make the Java classes, static state, and Metaspace of an old version disappear. What determines this is whether a **strong reference path from GC roots to the loader/classes/plugin objects** still exists. This article distinguishes static fields in a plugin from static caches in the host application, and analyzes reflection metadata, `WeakHashMap`, `ClassValue`, TCCL, ThreadLocal, and lifecycle-based cleanup.

## 1. Why can static fields/caches prevent class unloading?

A runtime Java class is identified by its **binary name + defining class loader**. Plugins V1 and V2 may both declare `plugin.impl.Handler`, yet they are **two runtime types** if defined by two separate plugin loaders. Each type has its own `Class<?>` mirror, static fields, and state.

JLS `12.7` states that a JVM **may** unload a class if and only if **its defining class loader can be reclaimed by the garbage collector**. This is a necessary condition for class unloading, **not a guarantee that GC will occur immediately**.

There are two very different graphs:

~~~text
A. CYCLE INSIDE THE PLUGIN, WITH NO EXTERNAL ROOT

  PluginLoader -> Class<Plugin> -> static INSTANCE
        ^                                |
        +-------- instance/class --------+

  If the entire cluster is unreachable from GC roots:
  tracing GC can reclaim the whole cluster; static does not create a root by itself.

B. REFERENCE FROM A LONG-LIVED HOST

  GC root -> Host Class -> static Map<String, Method>
                                  |
                                  +-> Method
                                        |
                                        +-> declaring Class<Plugin>
                                                |
                                                +-> defining PluginLoader

  The host root still holds Method => loader V1 remains reachable.
~~~

**Principle:** "Having a static field" is not a sufficient conclusion to call something a memory leak. You need to know **which loader defined the class owning the static field**, which objects its value retains, and **whether a GC root outside the stopped generation points into this cluster**.

### 1.1. Terminology to distinguish

| Concept | Meaning |
| --- | --- |
| GC root | Starting point of the JVM/collector reachability analysis, such as live thread frames, runtime roots, and reachable static state |
| Strong reference | A reference that keeps its referent reachable across tracing GC |
| Weak reference | Does not keep its referent alive on its own; cleared when GC processes weakly reachable objects |
| Defining loader | The loader that actually defines the runtime Class; affects type identity and unload eligibility |
| Class mirror | The `Class<?>` object representing a runtime type |
| Metaspace | Native memory used for much of the class metadata in HotSpot, distinct from the Java heap |
| Class unloading | The VM removes metadata of runtime classes when the loader is eligible and the collector performs it |
| Resource closing | Closing JARs/streams/threads/connections according to the API lifecycle, **distinct from** class unloading |

A live loader is not a leak if the plugin is ACTIVE and serving work. A leak is a loader that **should have been retired** yet is still retained by a root that is no longer valid according to the lifecycle.

## 2. Static fields in a plugin do not automatically cause a leak

Plugin example:

~~~java
package plugin.impl;

public final class InternalCache {
    public static final InternalCache INSTANCE =
            new InternalCache();

    private final byte[] data = new byte[4096];

    private InternalCache() {}

    public int bytes() {
        return data.length;
    }
}
~~~

There is a class/static singleton/instance cycle. If no root outside the plugin retains the loader, class, or objects of that generation, tracing GC can reclaim the entire cycle. **There is no need to set every static field to null just to break a cycle**.

However, even when the plugin is active, a large static map can still cause **heap pressure**. Resources such as streams, threads, native handles, and DB connections should be closed explicitly before terminating the plugin; do not rely on GC to close them automatically.

### 2.1. When do static fields in a plugin become a problem?

- A host registry retains `InternalCache.INSTANCE` in a `Map<String,Object>`.
- A worker thread created by the plugin keeps running and retains a plugin `Runnable`/frame/TCCL.
- The plugin registers a listener on a **host singleton EventBus**, and the host holds the plugin callback.
- A host serializer/DI framework caches `InternalCache.class` or reflection metadata.
- A global `ThreadLocal`/TCCL of a pool worker retains a plugin object/classloader.
- The plugin holds native resources that the `stop` lifecycle does not close.

You should not replace all static fields with instance fields as a blanket "fix". If the instance is still retained by the host, the classloader remains pinned.

## 3. Static fields in the host: the most obvious source of loader pinning

Consider a host registry:

~~~java
public final class HostRegistry {
    public static final java.util.Map<String, Object> SERVICES =
            new java.util.concurrent.ConcurrentHashMap<>();

    private HostRegistry() {}
}
~~~

The host class lives across multiple V1→V2 reloads. If the host calls:

~~~java
HostRegistry.SERVICES.put("plugin-old", pluginInstance);
~~~

then there is a chain `host static map → plugin instance → runtime class → defining plugin loader`. Calling `URLClassLoader.close()` **does not remove** this entry.

The proper way to handle this is for the host to define ownership: which generation each entry belongs to, when it is removed, who ensures old callbacks/requests have finished, and whether an entry can be re-added.

**Risk with `static final`:** `final` only prevents the `Map` reference from being reassigned normally; **the contents of the Map remain mutable**. By default, Java does not automatically expire entries based on plugin lifecycle.

### 3.1. A host cache that does not hold plugin instances can still leak

For example, a host that only stores Java reflection:

~~~java
static final java.util.Map<String, java.lang.reflect.Method> METHODS =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

A `Method` value represents a member belonging to a specific **declaring Class**. You can trace from:

~~~java
java.lang.reflect.Method method = METHODS.get("plugin.label");
Class<?> declaring = method.getDeclaringClass();
ClassLoader loader = declaring.getClassLoader();
~~~

This is a snippet that depends on the cache already containing the key, not a standalone Java main program. `Method`, `Field`, and `Constructor<?>` expose the `getDeclaringClass()` API. Therefore, a host holding a plugin's reflection metadata can retain the **Class<?>** and its defining loader even after the host has dropped the main plugin instance.

Similarly, important caches:

| Value retained by host | Potential link to plugin generation |
| --- | --- |
| `Class<?>` | Identifies the runtime type/defining loader |
| `Method` | Declaring class and method signature |
| `Field` | Declaring class and field type |
| `Constructor<?>` | Declaring class and parameter/exception types |
| `MethodHandle` | Target, method type, or runtime linkage to the plugin |
| `VarHandle` | Field/access semantics of the runtime type |
| `MethodType` | The `Class<?>` objects of parameter/return types |
| `MethodHandles.Lookup` | Lookup class/context |
| `Proxy`/generated accessor | Generated classes, interfaces, handler instance |
| `ServiceLoader`/`Provider<?>` | Discovered provider types/instances/cache |
| Captured lambda / `Runnable` | Captured plugin service/handler or plugin code |

You must analyze the **actual** graph on the JVM when a leak is suspected; do not claim that every MethodHandle or every framework cache retains a loader permanently.

### 3.2. Is a cache using String keys safe?

~~~java
Map<String, Class<?>> types;
Map<String, Method> methods;
Map<String, Object> instances;
~~~

**Not automatically safe.** A `String` key is a value independent of plugin classes, yet a **strong value** can still point to the plugin. Changing the cache key from `Class<?>` to a `String` class name does not solve the problem if the value still holds a reflection object.

If the host only needs to display the plugin name and version, store a lightweight descriptor:

~~~java
record PluginDescriptor(String id, String version,
                        String implementationName) {}
~~~

This is a Java 17 record defined by the host. The descriptor contains plain strings and does not need to retain the plugin's `Class<?>`. When execution is actually needed, resolve the right instance of the **active generation**; do not inadvertently call `Class.forName` on the system loader.

## 4. Java 17+ experiment: static host cache retains `Method` after close

The standalone lab below uses a plugin JAR and a host program. The code demonstrates what can be predicted deterministically **without needing `System.gc()`**: the host cache still holds the reflection Method, the Method leads back to the plugin loader, the already-loaded method can still be invoked after `URLClassLoader.close()`, and the entry is cleared when the host removes it.

### 4.1. Plugin source

Directory tree:

~~~text
reflection-cache-lab/
├── plugin-src/demo/plugin/Feature.java
├── host-src/HostCacheDemo.java
└── build/                 (created by the commands below)
    ├── plugin/
    ├── host/
    └── plugin.jar
~~~

File **`plugin-src/demo/plugin/Feature.java`**:

~~~java
package demo.plugin;

public final class Feature {
    public static final byte[] LOCAL_BUFFER = new byte[1024];

    private Feature() {}

    public static String label() {
        return "hello-from-plugin";
    }
}
~~~

The static `LOCAL_BUFFER` illustrates the state of the plugin's runtime class. It does not by itself turn the loader into a GC root belonging to the host.

### 4.2. Host application source

File **`host-src/HostCacheDemo.java`**:

~~~java
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class HostCacheDemo {
    private static final Map<String, Method> HOST_METHODS =
            new ConcurrentHashMap<>();

    private static WeakReference<ClassLoader> loadAndClose()
            throws Exception {
        URL pluginJar = Path.of("build", "plugin.jar")
                .toAbsolutePath().toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[] {pluginJar},
                ClassLoader.getPlatformClassLoader());

        Class<?> type = Class.forName(
                "demo.plugin.Feature", true, loader);
        Method method = type.getMethod("label");

        HOST_METHODS.put("feature.label", method);

        WeakReference<ClassLoader> observer =
                new WeakReference<>(loader);

        // Closes the loader's JAR handles; does not remove the loaded Class.
        loader.close();
        return observer;
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> observer = loadAndClose();

        Method cached = HOST_METHODS.get("feature.label");
        ClassLoader owner =
                cached.getDeclaringClass().getClassLoader();

        System.out.println("cache size=" + HOST_METHODS.size());
        System.out.println("method owner matches="
                + (owner == observer.get()));
        System.out.println("invoke after close="
                + cached.invoke(null));

        HOST_METHODS.remove("feature.label");
        System.out.println("cache empty=" + HOST_METHODS.isEmpty());

        // The variables 'cached' and 'owner' are still in scope.
        // Cannot assert that the loader has been GC'd just because the map was cleared.
    }
}
~~~

### 4.3. Compile and run

From the `reflection-cache-lab` root, in a POSIX shell (Linux/macOS, Git Bash), with JDK 17 or later:

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Feature.java
jar --create --file build/plugin.jar -C build/plugin .

javac --release 17 -d build/host \
    host-src/HostCacheDemo.java

# Intentionally do not place plugin.jar on the host classpath.
java -cp build/host HostCacheDemo
~~~

**Stdout for the lab configuration**:

~~~text
cache size=1
method owner matches=true
invoke after close=hello-from-plugin
cache empty=true
~~~

Explanation:

1. `URLClassLoader` has the platform loader as its parent, so the plugin implementation in the JAR is defined by the **plugin loader**, rather than being picked up by the application loader from sharing the same classpath.
2. `HOST_METHODS` is a static map belonging to the host class. The `getDeclaringClass()` of the cached `Method` is `demo.plugin.Feature` from the plugin loader.
3. `observer` is a **weak reference** and does not retain the loader on its own. However, `Method` remains in the map and in a local variable, so the loader is still reachable.
4. `Method.invoke(null)` invokes an already-loaded static method; `URLClassLoader.close()` does not remove existing classes.
5. `remove` clears **one root in the host map**, but `cached`, `owner`, and the local stack still hold references. This does not claim that unloading has occurred.
6. If the static method requires loading another class or resource from the JAR for the first time after the loader closes, the call may fail. This example intentionally avoids depending on unloaded classes.

On Windows, the directory-creation commands can be replaced with PowerShell equivalents; there is no need to change the classpath separator because the run command has only **a single entry `build/host`**.

### 4.4. Why not include the `WeakReference.get()` result after `System.gc()` in stdout?

A `WeakReference<ClassLoader>` only proves that this reference **does not prevent reclamation on its own**. If another strong root remains, the referent can stay alive. If you have cleared all roots but GC has not run or chooses not to unload, `get()` may still be non-null. Conversely, an experiment where the compiler/JIT optimizes local variable lifetimes may produce a different result than expected.

Therefore, there is no fixed GC-unload stdout across all JVMs. When testing, log the observer/`ReferenceQueue` within an observation window, inspect heap roots, and note that class unloading depends on the collector/runtime.

## 5. `WeakHashMap`: weak key, yet strong value

A familiar cache fix:

~~~java
static final java.util.WeakHashMap<Class<?>,
                                  java.lang.reflect.Method> CACHE =
        new java.util.WeakHashMap<>();
~~~

This may still retain the loader because `WeakHashMap` holds the **value via a strong reference**:

~~~text
Host -> WeakHashMap
        (key) --weak--> PluginClass
        (value) --strong--> Method -> declaring PluginClass
                                     |
                                     +-> PluginLoader
~~~

The value references back to the key, so the key still has a strong reachability path through the value. This is the pitfall warned about in the `WeakHashMap` Javadoc: values **should not retain keys directly or indirectly** if you expect entries to be reclaimed automatically.

A value containing only strings/primitives independent of plugin classes can work with weak keys, though you must still handle entries being removed by GC **at no fixed time**. `WeakHashMap` is not thread-safe by default.

### 5.1. Weak keys are not a lifecycle mechanism

Do not replace the stop/unregister procedure with the belief that GC will clean things up. While requests are actively using a provider, entries being removed unpredictably can affect the cache hit rate; when a plugin retires, the host needs a **deterministic release** of the references it owns.

If you want to use `WeakReference<Method>` as the value, you must handle `ref.get()==null` on access, recompute the metadata, and manage concurrency. A weak cache is a **memory optimization**, not a replacement for the entire cleanup protocol.

## 6. `ClassValue`: per-class metadata cache

Java's `ClassValue<T>` was created for cases where you need to store metadata **per `Class<?>`** without building your own global strong-key map.

Java 17 helper example:

~~~java
import java.lang.reflect.Method;

public final class AccessorCache {
    private AccessorCache() {}

    private static final ClassValue<Method> LABEL =
            new ClassValue<>() {
                @Override
                protected Method computeValue(Class<?> type) {
                    try {
                        return type.getMethod("label");
                    } catch (NoSuchMethodException problem) {
                        throw new IllegalArgumentException(problem);
                    }
                }
            };

    public static Method lookup(Class<?> type) {
        return LABEL.get(type);
    }

    public static void evict(Class<?> type) {
        LABEL.remove(type);
    }
}
~~~

The file **`AccessorCache.java`** can be compiled with `javac --release 17`; it is a **library class**, with no `main`. The goal is to associate computed metadata with a specific class and use `remove(type)` to clear the association when needed.

The `ClassValue` Javadoc notes that `computeValue` may run **multiple times** under concurrent contention, though the mechanism will select a single value to associate with the `Class` per its contract. Do not write `computeValue` with non-idempotent resource side effects without proper control.

**Important limitation:** `ClassValue` does not clear other roots (host registry, TCCL, event listeners) and is not `unloadClass`. If the value holds an `AutoCloseable`, calling `remove` does not automatically invoke `close()` on the value either. A separate owner/lifecycle is required.

## 7. A generation-scoped cache

If the host needs to look up methods repeatedly for a plugin version, it is usually better to place the cache **inside the generation object**, rather than in a static global:

~~~java
import java.lang.reflect.Method;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class GenerationMethods {
    private final Map<String, Method> methods =
            new ConcurrentHashMap<>();

    void put(String name, Method value) {
        methods.put(name, value);
    }

    Method get(String name) {
        return methods.get(name);
    }

    void clear() {
        methods.clear();
    }
}
~~~

This code compiles, but it only illustrates the cache object and **does not include lifecycle coordination**. For production use, you need `ACTIVE → DRAINING → CLOSED` states and must prevent a V1 request from adding an old Method **after** an admin calls `clear()`.

Incorrect race diagram:

~~~text
Request V1                           Admin
  holds Method V1
                                      CACHE.clear()
  CACHE.put("key", Method V1)         close(loader V1)
  -> V1 gets re-cached after cleanup
~~~

`ConcurrentHashMap` only protects map operations at the thread-safety level; it does not turn "clear old generation" and "prevent V1 writer from re-adding" into a single transaction.

The fix: block new requests on V1, wait for in-flight work to finish (read/write lock or **generation lease/reference counting**), clean up the V1 cache, close objects/resources, close the loader, and then drop the final references.

### 7.1. Using a generation id to avoid mixing V1/V2

If the host is forced to maintain a global registry, the key should include the generation identity **and** the tenant/plugin scope, along with exact eviction:

~~~java
record CacheKey(String pluginId, long generation,
                String operation) {}
~~~

A good key **does not release the value on its own**. When generation 42 stops, remove all entries belonging to generation 42 after draining; do not accidentally remove generation 43 that was just published. In multithreaded applications, ensure iteration/removal and lookup do not execute outside the lifecycle contract.

## 8. `MethodHandle`, `VarHandle`, proxies, and framework caches

Traditional reflection is not the only source:

- `MethodHandle` may retain a target or runtime type associated with the plugin implementation.
- `VarHandle` may be bound to a plugin's field type and declaring class.
- `MethodType` contains `Class<?>` parameter/return types; a host cache of MethodType containing a plugin type can pin the loader.
- `MethodHandles.Lookup` holds the lookup class/context; retaining it longer than the plugin generation can cause retention.
- Generated proxies/bytecode accessors/captured lambdas contain interfaces, handlers, or target objects belonging to the plugin loader.
- Serializer/ORM/DI frameworks cache annotation metadata, property descriptors, builders, or suppliers for plugin types.
- `java.beans.Introspector` and framework-specific introspection caches must be handled via their official APIs when a plugin unloads.

Do not claim that every cache provided by the JVM or a framework leaks; many caches use weak keys or appropriate lifecycle scopes. **Only when a root path retains a retired loader** is it an actual leak. A heap dump/dominator tree is more useful than guessing based on class names.

## 9. TCCL and ThreadLocal: hidden roots in thread pools

A worker thread in the host can retain an old plugin loader via `Thread.contextClassLoader` or a `ThreadLocal` value after a plugin task completes. This is a `live Thread → plugin state/loader` path that clearing the host's static cache alone does not resolve.

Restore TCCL in a `finally` block, call `ThreadLocal.remove()` on the **exact worker thread**, and cancel/drain asynchronous tasks before retiring. The Thread/ThreadLocal/TCCL article covers a dedicated thread pool experiment.

## 10. Closing resources does not mean unloading classes

`URLClassLoader.close()` closes the class/resource sources and file handles it manages; already-loaded classes, `Method` objects, and instances can still continue to be retained by the host. A host cache still holding a reflection `Method` after close is a classic example.

To give the JVM **an opportunity** to unload, sever the retaining references to the class/defining loader; GC timing is the VM's decision.

## 11. Retirement procedure to leave no V1 roots behind

**STOP new work → DRAIN current work → UNREGISTER callbacks → CLEAR host caches and generation records → CLEAN TCCL/ThreadLocal → CLOSE owned resources and URLClassLoader → RELEASE strong references**.

For this article, the primary check is that the host cache no longer holds `Class<?>`, `Method`, `MethodHandle`, proxy, or instance entries belonging to V1, including hidden framework caches. With `WeakHashMap`, you must also check whether the value references back to the key; `ClassValue` or a per-generation cache may be more suitable.

## 12. Accurate diagnosis using heap roots and Metaspace

A class unloading event depends on the JVM/GC. JLS `12.7` does not require classes to be unloaded immediately when a loader becomes eligible. Java SE also does not provide a `ClassLoader.unloadClass("name")` method.

When retention is suspected after multiple V1→V2 cycles:

1. Log the **generation id/artifact hash/loader identity** at startup and stop.
2. Measure the number of active plugins, in-flight calls, host cache entries, and the TCCL of long-lived workers.
3. Observe the number of classloaders, class count, Metaspace, and heap across multiple reload cycles; do not treat a single point-in-time memory increase as proof.
4. Capture a heap dump when operationally appropriate and use the dominator tree / path to GC root to find what retains the loader.
5. Prioritize paths such as `Host static Map → Method → Class → Loader`, `Thread → contextClassLoader`, `ThreadLocalMap → value`, `Host EventBus → listener`, and `ServiceLoader cache → provider`.
6. Fix the **ownership/eviction/lifetime protocol**; do not use a GC loop as a workaround.
7. Run multiple cycles again and check whether the total loader count or Metaspace stops growing uncontrollably.

### 12.1. Supporting commands on the corresponding HotSpot/JDK

~~~bash
java -version

# HotSpot unified logging when running the example:
java -Xlog:class+load=info,class+unload=info \
    -cp build/host HostCacheDemo

# For a long-lived process, substitute the actual PID for <pid>:
jcmd <pid> help
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace basic
jcmd <pid> Thread.print
~~~

`jcmd` and its options depend on JVM/tool availability; verify them via `jcmd PID help`. A heap dump/`GC.class_histogram` can incur stop-the-world overhead, heavy I/O, or contain sensitive data; only run them according to appropriate diagnostic policies.

### 12.2. Interpreting signals carefully

| Signal | What is known | What cannot yet be concluded |
| --- | --- | --- |
| Static host map contains a V1 Method | There is a root to V1 metadata | That no other roots remain |
| `URLClassLoader.close()` succeeds | An attempt was made to close loader-owned file handles | That V1 classes have unloaded |
| `WeakReference.get()!=null` after `System.gc()` | The loader had not been cleared at the time of observation | That there is definitely a leak |
| `WeakReference.get()==null` | The referent was cleared by GC per weak semantics | That all plugin resources have been closed |
| Class unload log is present | The JVM unloaded classes per its implementation | That every native/file/socket handle has been released |
| Metaspace increases after several reloads | There is metadata/commit/reservation activity | That the cause is definitely a reflection cache |
| Host Method/Class cache grows continuously across generations | There is suspicious retained metadata | Who the cache owner is without inspecting the heap path |

## 13. Common misconceptions

1. "A plugin's static field causes a leak by itself." — **Not necessarily**, if the entire loader graph has no external root.
2. "A static final Map in the host cannot retain additional entries." — **False**, final only fixes the Map reference.
3. "Caching `Method` does not retain a plugin instance, so it is safe." — **False**, Method relates to its declaring class.
4. "Using String as the cache key prevents classloader leaks." — **False** if the value retains a `Class<?>`/Method/plugin object.
5. "`WeakHashMap<Class<?>, Method>` automatically releases every entry." — **False**, the value can retain the key.
6. "Switching to `ClassValue` solves every memory leak." — **False**, host listeners/TCCL/registries can still remain.
7. "`URLClassLoader.close()` immediately unloads classes." — **False**.
8. "V1 static state is reset after close." — **False**, loaded classes remain alive while reachable.
9. "Daemon workers never pin a plugin loader." — **False**, an active thread can hold roots.
10. "`System.gc()` guarantees the loader will disappear." — **False**, there is no deadline/guarantee.
11. "If two classes share the same binary name, the host cache is pointing to the new version." — **False**, you need to compare defining loader identity.
12. "`ConcurrentHashMap.clear()` is atomic with respect to all requests." — **False**, a writer can repopulate it after clear.
13. "ServiceLoader.reload() hot-reloads bytecode." — **False**, it resets the provider cache of the current instance.
14. "When the heap shrinks, Metaspace shrinks immediately." — **Not certain**, the two memory regions/GC policies differ.
15. "If the class count fails to drop once, the JVM violates the spec." — **False**, unloading is a runtime-dependent optimization.

## 14. Self-check questions

1. Static `PluginCache.INSTANCE` only references internals of a retired V1 loader, with no external root. Does it **necessarily** pin V1? **No**.
2. Can a host static `Map<String, Method>` pin a plugin loader? **Yes**, via Method→Class→loader.
3. Is `WeakHashMap<Class<?>, Method>` guaranteed to be safe? **No**, the value can strongly retain the key.
4. Does `URLClassLoader.close()` remove already-loaded `Class<?>` objects? **No**.
5. Why must V1 tasks be stopped before clearing the cache? **To prevent repopulation and avoid using closed resources**.
6. When observing with `WeakReference<ClassLoader>`, does a single GC run failing to clear it prove a leak? **No**.
7. What is `ClassValue` used for? **Caching computed metadata per Class**, not forcing class unloading.
8. How does `ThreadLocal.remove()` help prevent leaks on pool workers? **It removes the plugin value after the scope ends**.
9. Is a cache with `String` keys and `Class<?>` values safe for hot reload? **No, when the value retains V1**.
10. What is the significance of reflection `Method.getDeclaringClass()`? **It identifies the runtime Class where the method is declared**.
11. What does a heap dump/dominator tree look for? **A strong path to a GC root retaining the loader**.
12. When is a living V1 loader not considered a leak? **When there are active V1 requests/services according to the lifecycle**.
13. Does using a new classloader for V2 remove all V1 roots? **No**, host caches/threads may still retain V1.
14. Is `System.gc()` a request or a guarantee? **A hint/request**, with no guarantee of immediate unloading.
15. Which memory region does a static byte array primarily belong to? **The heap**; HotSpot class metadata resides in Metaspace.

## 15. Official references

1. [JLS `12.7` — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): a class may be unloaded only when its defining loader can be reclaimed, and the timing is implementation-dependent.
2. [JVMS `5.3` — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime type identity, defining/initiating loader.
3. [ClassLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): delegation, define/load, findLoadedClass.
4. [URLClassLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): close, already-loaded classes, and JAR/file handles.
5. [Method — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): getDeclaringClass, invoke.
6. [WeakHashMap — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/WeakHashMap.html): weak keys/strong values that may reference back to the key.
7. [ClassValue — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassValue.html): computed per-Class cache, get/remove.
8. [WeakReference — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): weak references and GC semantics.
9. [jcmd — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): VM.classloader_stats, VM.classloaders, VM.metaspace.
10. [Thread — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): TCCL and thread lifetime.
11. [ServiceLoader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider cache/reload.

**Conclusion:** Static fields do not automatically cause leaks, but **strong references from a host/GC root to a plugin Class/Method/instance/loader** can retain a retired generation. Manage caches **by owner/generation**, stop in-flight work, unregister listeners, restore TCCL, remove ThreadLocal values, close resources properly, and observe retained paths. `URLClassLoader.close()` is an I/O cleanup step, **not a class-unloading API**.
