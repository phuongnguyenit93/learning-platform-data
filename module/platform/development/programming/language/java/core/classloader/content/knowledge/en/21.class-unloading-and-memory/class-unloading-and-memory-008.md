# Listeners, registries, ServiceLoader cache, and causes of retaining plugins in memory

## 1. The problem: the plugin has stopped, but the ClassLoader is still alive

A Java plugin system typically creates a **dedicated ClassLoader** to load implementations and dependencies. When a plugin is removed (unload/undeploy/redeploy), the host may stop serving requests and call `URLClassLoader.close()`, yet the memory allocated for the plugin **is not necessarily freed**.

The cause is usually not that the JVM “forgot to unload classes,” but that **one or more references still keep an object/plugin class/ClassLoader reachable**:

- The plugin's listener is still registered in a long-lived host registry.
- A plugin instance remains in a singleton list/map, event bus, or callback table.
- A `ServiceLoader` stored in a host cache still holds the loader/provider metadata and iterated instances.
- A thread pool worker holds a `Thread Context ClassLoader (TCCL)` pointing to the plugin loader.
- An executor, timer, thread, shutdown hook, or `ThreadLocal` still holds an object/class belonging to the plugin.
- A cache contains `Class<?>`, reflection `Method`, `Constructor`, `MethodHandle`, a lambda/proxy, or an object defined by the plugin loader.
- Another resource (JDBC driver, MBean, logger/handler, scheduled job, etc.) is still registered with a long-lived component.

**Lesson focus:** understand **strong reference paths** from GC roots to the plugin, distinguish **stop**, **close**, **dereference**, and **class unloading**, and design a verifiable cleanup process.

This article targets Java 17+, with a runnable example of **listener registry + ServiceLoader cache**, an example of the limitations of `reload()`, guidance on identifying leaks using JVM tooling, and a safe redeploy checklist.

## 2. Four distinct lifecycle concepts

**Stopping a plugin** halts processing and unregisters business logic; **`URLClassLoader.close()`** closes the class/resource sources and JAR handles managed by the loader; **GC eligibility** depends on whether the loader generation is still reachable from roots; **class unloading** is the JVM's decision when conditions are met.

For `ServiceLoader`, calling `reload()` clears the provider cache of that `ServiceLoader` itself, but does not remove provider instances held in other host registries. This article focuses on the ownership of listener/registry/provider caches.

## 3. How ClassLoader, Class, and objects retain one another

A plugin instance, `Class<?>`, listener object, or ServiceLoader provider can still lead back to the plugin's runtime type and **defining loader**. For example: `host event bus → listener instance → runtime class → plugin loader`.

Because the JVM identifies a normal class by `(binary name, defining loader)`, two plugin versions can hold two distinct runtime classes with the same name. Only when the registrations and references still held by the host are removed does the old defining loader have a chance to be reclaimed.

## 4. Listener and callback registries are classic sources of plugin retention

An event bus typically has an API:

```java
public interface Listener {
    void onEvent(String message);
}
```

This is a sample interface that can be placed in `Listener.java`. The host may hold:

```java
// Snippet: event bus belongs to a class defined by the host loader.
private static final java.util.List<Listener> LISTENERS =
        new java.util.concurrent.CopyOnWriteArrayList<>();

public static void register(Listener l) {
    LISTENERS.add(l);
}

public static void unregister(Listener l) {
    LISTENERS.remove(l);
}
```

If a plugin calls `register(new PluginListener())` and never calls `unregister`, `LISTENERS` retains the plugin object. When the host `ClassLoader` lives for the lifetime of the JVM, the registry usually remains reachable through a host class/field.

**The leak mechanism does not depend on whether the listener is actively receiving events.** Simply having the reference remain in the collection is enough.

### Lambdas and method references are also callbacks

For example:

```java
// Snippet: eventBus is a long-lived host object, plugin is a plugin instance.
eventBus.subscribe(event -> plugin.handle(event));
```

A lambda can capture `plugin` inside the callback object. The host only sees a generic `Consumer<Event>`/interface, but the callback retains the plugin object behind it. The lambda's runtime class name may not look like `PluginListener`, making a heap dump harder to read.

Similarly, `plugin::handle` is a method reference that can retain the `plugin` receiver. A single callback remaining in a host registry **can still keep the entire plugin loader alive**.

**Good API design:** `subscribe` returns an `AutoCloseable`/`Subscription` object so the plugin manager can unregister cleanly:

```java
// API design snippet:
interface Subscription extends AutoCloseable {
    @Override
    void close();
}

Subscription subscription = eventBus.subscribe(listener);
try {
    // plugin active
} finally {
    subscription.close();
}
```

This is a **snippet** because `eventBus`, `listener`, and the `subscribe` overload are defined by the application. In an asynchronous system, `unsubscribe` only removes the callback from future dispatches; events already dispatched or in-flight tasks still need to complete before closing the loader.

## 5. Registries and singleton caches in the parent loader

A host often has:

```java
// Snippet in a host class:
private static final java.util.Map<String, Object> PLUGINS =
        new java.util.concurrent.ConcurrentHashMap<>();
```

If `PLUGINS.put("alpha", pluginInstance)` is called, and after `plugin.stop()` `remove("alpha")` is not called, the plugin loader can remain alive.

Variants that are easy to overlook:

- `Map<String, Class<?>>` storing provider classes to instantiate objects later via reflection.
- `Map<String, Method>` storing reflective methods on plugin classes.
- `List<Runnable>` storing callbacks that capture the plugin.
- Framework caches storing metadata about annotations, generated proxies, method handles, serializers, mappers, or DI providers.
- A `ThreadLocal` on a host thread pool storing an object of a plugin class.
- A cache holding a `ServiceLoader<?>` pointing to an explicit plugin ClassLoader.
- A JDBC driver registry or MBean server in a long-lived runtime component holding implementations defined by the plugin.

### Watch out for indirect references

Do not only check whether a collection directly contains a **ClassLoader**. An entry typed as `Object`, `Runnable`, `Listener`, or `Supplier<?>` can also hold **an object defined by the plugin loader**, which in turn retains the runtime class/loader.

A `static Map` located **in a host/common loader class** can retain plugins across multiple deployments. A `static Map` located only inside a plugin class does not necessarily outlive the loader if there is no external reference path.

When analyzing a heap dump, trace from **GC roots** to the suspected loader and inspect the **retaining/dominator path**, rather than just searching for “which class has a static field.”

## 6. How does the ServiceLoader cache retain providers?

`java.util.ServiceLoader<S>` discovers implementations of a service interface or abstract class from:
- `META-INF/services/<service-binary-name>` in the classpath/unnamed modules;
- `provides ... with ...` in module descriptors;
- a selected module layer when using `ServiceLoader.load(layer, service)`.

**ServiceLoader uses lazy discovery/instantiation and caches per ServiceLoader instance.** With `iterator()` or `findFirst()`, instantiated providers can be retained and returned on subsequent iterations. A live `ServiceLoader` object can hold:
1. the configured discovery loader/context;
2. cached provider descriptors/types and objects after iteration;
3. auxiliary objects used for provider discovery.

If the host keeps `ServiceLoader<HostService>` in a static field across multiple plugin generations, it can retain **the plugin loader and provider instances of the old generation** even if the host no longer calls them.

```text
Host static field
     │
     ▼
ServiceLoader<HostService>
     ├── discovery ClassLoader = PluginLoader-v1
     └── provider instance cache
              │
              ▼
         PluginProvider-v1
              │
              ▼
         PluginLoader-v1

Even after deploying v2, v1 can still be reachable.
```

**There is no `ServiceLoader.close()` to automatically close provider objects or class loaders.** The host must manage the lifecycle of the providers themselves, the service loader holder, callback resources, and plugin loaders.

### What does reload() solve and what does it not solve?

`serviceLoader.reload()` clears the provider cache of **that ServiceLoader instance itself**, so the next iteration attempts rediscovery. It does **not**:
- remove providers that have references in other listener registries;
- automatically drop the reference to the **discovery ClassLoader** attached to the ServiceLoader itself;
- unload classes already defined by the JVM;
- reset static initializers of already initialized classes;
- stop threads/connections created by a provider;
- close a `URLClassLoader`;
- replace a hot-deploy architecture using a new loader.

Therefore, if the host intends to unload the entire plugin loader, **simply calling `reload()` is usually not enough**: the host must also drop references to the old ServiceLoader, old providers, and other owners.

## 7. Runnable Java 17+ example: Listener registry + ServiceLoader cache retaining a plugin after close()

This is a complete example with deterministic stdout and **no need to guess GC timing**. We create:
- Host API `api.Hook`;
- implementation `impl.PluginHook` in a separate plugin directory;
- file `META-INF/services/api.Hook` so `ServiceLoader` discovers the implementation;
- a host static registry storing the provider instance and caching `ServiceLoader`;
- `URLClassLoader` is `close()`d, yet the host can still invoke the loaded provider;
- finally, the host clears the registry and cache.

### 7.1. Source structure

```text
plugin-leak-demo/
├── src/
│   ├── api/
│   │   └── Hook.java
│   ├── impl/
│   │   └── PluginHook.java
│   └── host/
│       └── RegistryLeakDemo.java
├── host-out/
└── plugin-out/
    └── META-INF/
        └── services/
            └── api.Hook
```

### 7.2. File src/api/Hook.java

```java
package api;

public interface Hook {
    String message();
}
```

`Hook` is the **shared API** of the host. The plugin implementation will implement this exact `api.Hook` defined by the application/host loader.

### 7.3. File src/impl/PluginHook.java

```java
package impl;

import api.Hook;

public final class PluginHook implements Hook {
    public PluginHook() {
        System.out.println("PluginHook constructed");
    }

    @Override
    public String message() {
        return "plugin active";
    }
}
```

### 7.4. Service provider configuration

Create the file:

```text
plugin-out/META-INF/services/api.Hook
```

Single-line content:

```text
impl.PluginHook
```

The metadata filename is the binary name of the **service**, not the provider. The provider class has a public no-argument constructor, satisfying the classpath SPI mechanism in the example.

### 7.5. File src/host/RegistryLeakDemo.java

```java
package host;

import api.Hook;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class RegistryLeakDemo {
    // Fields reside in the host class, not the plugin class.
    private static final List<Hook> LISTENERS = new ArrayList<>();
    private static ServiceLoader<Hook> cachedServices;
    private static ClassLoader pluginLoaderForComparison;

    private static void deploy() throws Exception {
        URL url = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {url},
                RegistryLeakDemo.class.getClassLoader()
        )) {
            ServiceLoader<Hook> services =
                    ServiceLoader.load(Hook.class, loader);
            Hook provider = services.findFirst().orElseThrow();

            LISTENERS.add(provider);
            cachedServices = services;
            pluginLoaderForComparison = loader;

            System.out.println("provider uses plugin loader: "
                    + (provider.getClass().getClassLoader() == loader));
        }
        // Here the loader has been close()d, but the host still holds references.
    }

    public static void main(String[] args) throws Exception {
        deploy();

        System.out.println("after close listeners: "
                + LISTENERS.size());
        System.out.println("provider still callable: "
                + LISTENERS.get(0).message());
        System.out.println("cache keeps same provider: "
                + (cachedServices.iterator().next()
                   == LISTENERS.get(0)));
        System.out.println("registry points to loader: "
                + (LISTENERS.get(0).getClass().getClassLoader()
                   == pluginLoaderForComparison));

        LISTENERS.clear();
        cachedServices = null;
        pluginLoaderForComparison = null;

        System.out.println("after cleanup listeners: "
                + LISTENERS.size());
        System.out.println("after cleanup cached: "
                + (cachedServices != null));
    }
}
```

The `pluginLoaderForComparison` field is only a **verification marker in the demo**, not a mechanism to use in a real host. This field itself also holds a strong reference to the loader; in a real system, it should not be stored in a static field longer than the plugin's lifecycle. The `LISTENERS` and `cachedServices` lines are sufficient to illustrate the two main types of reference paths.

### 7.6. Compile and run

Open a terminal in `plugin-leak-demo`. For Bash:

```bash
mkdir -p host-out plugin-out/META-INF/services
```

For Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force host-out,plugin-out/META-INF/services | Out-Null
```

Create the metadata file as in section 7.4, then compile with **JDK 17+**:

```bash
javac --release 17 -d host-out src/api/Hook.java src/host/RegistryLeakDemo.java
javac --release 17 -cp host-out -d plugin-out src/impl/PluginHook.java
java -cp host-out host.RegistryLeakDemo
```

**Note:** the `java` command only puts `host-out` on the application classpath. Do not add `plugin-out` to the host's `-cp`: if the parent loader sees the implementation first, the class will no longer be defined by the dedicated plugin loader and the demo loses its isolation meaning.

### 7.7. Exact stdout

```text
PluginHook constructed
provider uses plugin loader: true
after close listeners: 1
provider still callable: plugin active
cache keeps same provider: true
registry points to loader: true
after cleanup listeners: 0
after cleanup cached: false
```

The output has been tested with `javac --release 17` and a newer Java runtime following the Java 17 API.

### 7.8. Step-by-step analysis of each retention relationship

**Step 1:** The host creates a new `URLClassLoader` with the host loader as its parent. The plugin loader can read `plugin-out` and find `impl.PluginHook`, while the `api.Hook` API is provided by the parent. The provider is assignable to the host service interface because they share the same runtime type.

**Step 2:** `ServiceLoader.load(Hook.class, loader)` creates a discovery object; `findFirst()` iterates lazily, instantiates `PluginHook`, and the constructor prints `PluginHook constructed`.

**Step 3:** The host stores the provider in `LISTENERS` and keeps the ServiceLoader in `cachedServices`. These are strong references in a long-lived host class.

**Step 4:** Exiting `try (URLClassLoader loader = ...)`, `close()` runs. However, already defined provider classes/objects remain present. Because `message()` does not require finding new classes/resources, the subsequent call still succeeds. **Do not conclude that a plugin after close always works completely**: another method needing an unloaded dependency may fail.

**Step 5:** `cachedServices.iterator().next()` returns the cached instance from the `findFirst()` pass. This proves that the ServiceLoader cache can be a **provider instance retention path**.

**Step 6:** `LISTENERS.get(0).getClass().getClassLoader()` equals the created loader. The host still references an implementation belonging to that loader.

**Step 7:** `LISTENERS.clear()`, `cachedServices=null`, and `pluginLoaderForComparison=null` remove the demo's three host references. This is **structural cleanup that can be verified immediately**; it **does not prove the loader has already been garbage collected at the moment the last line is printed**.

### What happens if only one of the two caches is cleared?

- Only `LISTENERS.clear()`: `cachedServices` can still retain provider instances and the discovery loader.
- Only `cachedServices=null`: `LISTENERS` still retains the provider instance.
- Only `cachedServices.reload()`: the provider cache is cleared, but ServiceLoader is still a live object with its attached loader/context; moreover, the listener registry still retains the instance.
- Only `loader.close()`: does not automatically drop any reference in the host.
- Only `System.gc()`: is not cleanup and does not resolve strong references.

That is why verifying via registry/ownership structure is more important than a single GC call in tests.

## 8. Removing individual listeners accurately: tokens or removal by identity?

In a simple registry, a `remove(listener)` API may suffice. However, in practice issues arise:
- a listener is registered **multiple times**;
- a callback is wrapped/decorated so the object passed to remove is not the same object stored in the registry;
- the listener's `equals()` has custom logic causing the wrong object to be removed;
- asynchronous dispatch already copied the callback into a queue before unregistering;
- the event bus needs to stop accepting new callbacks during cleanup.

Therefore, registration tokens are usually clearer:

```java
// Design snippet:
AutoCloseable registration = eventBus.register(pluginListener);

try {
    plugin.run();
} finally {
    registration.close(); // unregister a specific registration
}
```

This is **design pseudocode**, where `eventBus` and `plugin` are provided by the application. When the user closes `registration`, the event bus should remove that exact registration (usually idempotently) and have a clear policy for currently running callbacks.

If a listener is in an application registry **where the plugin does not own an unsubscribe API**, the manager must still have a cleanup mechanism upon undeploy. A registry that only has `add` without an appropriate `remove`/`close`/`reset` is a leak risk sign.

### Scoped registration

A safer architecture places all subscriptions in a lifecycle object:

```java
// Snippet: registrations is List<AutoCloseable>.
void stopSubscriptions(List<AutoCloseable> registrations)
        throws Exception {
    Exception first = null;
    for (int i = registrations.size() - 1; i >= 0; i--) {
        try {
            registrations.get(i).close();
        } catch (Exception ex) {
            if (first == null) {
                first = ex;
            } else {
                first.addSuppressed(ex);
            }
        }
    }
    registrations.clear();
    if (first != null) {
        throw first;
    }
}
```

This is an **illustrative method** that can be placed in a class; it requires no imports beyond `java.util.List`. It attempts to close **all** registrations in reverse order and records suppressed errors instead of stopping after the first failure. In production, thread-safety and preventing overwrites to registrations during cleanup are also needed.

## 9. Thread Context ClassLoader retaining plugins on a thread pool

`Thread.currentThread().getContextClassLoader()` can retain a plugin loader when a framework/`ServiceLoader` uses TCCL to discover providers. If a host worker thread lives across multiple reloads and does not reset its context loader, it can pin the old generation.

Restore TCCL in `finally`, and clean up provider caches/registrations per owner. The Thread/ThreadLocal/TCCL article explains the pooled thread scenario in full.

## 10. ThreadLocal, CompletableFuture, and asynchronous tasks

`ThreadLocal` values, scheduled callbacks, `CompletableFuture` chains, executor queues, and running tasks can retain plugin objects even if `ServiceLoader` or the event bus has been cleared.

To retire them, cancel/drain futures/tasks appropriately, `remove()` ThreadLocals on the exact thread that set them, and avoid letting new callbacks be registered during shutdown. The dedicated threads article examines this bug in detail.

## 11. JNI, JDBC, JMX, logging, and framework-managed registries

Besides listeners you write yourself, many JDK/framework components are also **registries**:

- **JDBC DriverManager**: a plugin registers a `java.sql.Driver` defined by the plugin loader. Depending on how the driver was initialized/registered and the runtime, it is necessary to **deregister** plugin-owned drivers on unload using the appropriate API. Do not deregister another application's driver.
- **JMX MBeanServer**: MBeans registered with a long-lived server can retain plugin objects/classes/loaders; unregister the exact `ObjectName`.
- **Logging handlers/appenders**: a plugin logger/handler can be retained by the host logger tree, async queue, or logging context; detach/stop/close according to the framework API.
- **Shutdown hooks**: `Runtime.addShutdownHook(Thread)` retains the registered hook thread until it runs or is removed; the plugin must remove hooks it owns while still permitted.
- **Timer/Executor/Scheduler**: task objects can capture the plugin and outlive the plugin.
- **Shared framework class/serializer/reflection caches**: can retain plugin `Class<?>`/`Method`/codegen proxies.
- **JNDI, service registries, DI containers**: similar in nature when they retain provider objects or class metadata.

These are **categories to investigate**, not a claim that every library/JVM implementation leaks. Many frameworks already use weak references or cleanup hooks. Measure and identify the reference path on the version in use.

### Do not accidentally clean up shared resources

If the host owns a thread pool shared by multiple plugins, plugin A must not `shutdown()` the entire pool when A undeploys. A should only cancel its own tasks/callbacks and return control to the host.

Similarly, drivers/MBeans/listeners/resources should only be unregistered by their owner or lifecycle manager by their registration token/ID. Indiscriminate cleanup can break plugin B.

## 12. Relationship between ServiceLoader, ClassLoader, and module layers

In modular applications (JPMS), ServiceLoader can discover providers via module descriptors:

```java
module app.api {
    exports app.api;
}
```

```java
module plugin.impl {
    requires app.api;
    provides app.api.Plugin with plugin.impl.DefaultPlugin;
}
```

These are **two illustrative descriptors**, assuming the types actually exist. `ServiceLoader.load(layer, Plugin.class)` locates providers in the appropriate `ModuleLayer` per the Java API.

A host creating a **child ModuleLayer** for a plugin may retain:
- the `ModuleLayer` object;
- `Module` objects;
- the `ClassLoader` used by the layer;
- `ServiceLoader`/provider descriptors;
- providers/instances and callbacks.

Even without using `URLClassLoader` directly, the reference path from the host to the child layer/plugin loaders/classes still needs management. Do not treat `ModuleLayer` as a “shell” that automatically unloads when some method is called; `ModuleLayer` itself has no `close()`.

**Do not equate JPMS export/open with memory isolation.** Module `requires`/`exports`/`opens` control readability/access; they do not automatically manage GC or stop plugin threads.

## 13. Why WeakReference/WeakHashMap is not an automatic solution

Java provides:
- `WeakReference<T>`: a weak reference that does not keep the referent alive solely through that reference.
- `WeakHashMap<K,V>`: weak keys; an entry can be removed when the key is no longer strongly reachable.
- `ReferenceQueue<T>`: allows observing weak/phantom references enqueued as GC progresses.
- `Cleaner` and phantom references: reachability-based cleanup mechanisms with no guaranteed execution timing.

They are useful in certain caches, but **do not replace explicit lifecycle cleanup**.

### Example of the WeakHashMap trap

```java
// Snippet:
Map<ClassLoader, Holder> cache = new WeakHashMap<>();
cache.put(pluginLoader, new Holder(pluginLoader));
```

Here `Holder` is assumed to hold a strong reference to the loader. Even though the `WeakHashMap` key is weak, **the Holder value can strongly retain the key loader**, creating the path:

```text
WeakHashMap (host)
     └── strongly-held value Holder
              └── strongly-held pluginLoader
                       └── key not yet collectible
```

Thus “using WeakHashMap” does not automatically guarantee the entry disappears. The same applies to caches containing `Class<?>` or provider instances linked to the loader.

### Are weak listeners enough?

An event bus using only weak references to listeners can avoid unintended long-term retention, but introduces another problem: a listener can be GC'd **while it still needs to receive events** if the owner does not keep a reference. In many systems, **strong registration + explicit unsubscribe** is more reliable, with clear lifetime and ownership.

**Only use weak references when cache semantics fit**, not to mask the lack of an unregister/stop API.

## 14. Using WeakReference to observe collectibility

You can record:

```java
// Snippet:
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);

// After stopping the plugin, drop strong references in the proper owner:
// pluginLoader = null;  // only if the variable can be reassigned
//
// Later, at a point when GC runs:
ClassLoader stillThere = weak.get();
```

This is a **snippet**, requiring `import java.lang.ref.WeakReference` and an appropriate `pluginLoader` variable. **`weak.get() != null` immediately after cleanup does not prove a leak**: GC may not have run yet or transient stack references may still exist. **`weak.get() == null`** indicates the referent was reclaimed by GC at that observation point, but does not replace verifying resource cleanup.

Some test harnesses try looping `System.gc()`, waiting on a `ReferenceQueue` with a timeout. These tests are prone to flakiness across different CI/JVM/GC configurations, because `System.gc()` is a request, not a guarantee. Instead:
- Use **structural assertions** to prove registries are empty, subscriptions closed, TCCL restored, and executors stopped.
- Use **integration soak/redeploy tests** to monitor loader count/metaspace trends.
- Use weak references/queues as **supporting signals**, without turning “GC must happen within 100 ms” into a correctness condition of application logic.

## 15. How to observe class unloading with HotSpot

On HotSpot JDKs supporting unified logging, you can enable:

```bash
java -Xlog:class+load=info,class+unload=info -cp host-out host.RegistryLeakDemo
```

This command uses the demo in section 7. **Actual log lines depend on the JVM/JDK** and can be very verbose. It does not mean the JVM is required to unload plugin classes during this short run.

For a running process, you can use:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> Thread.print -l
```

`<pid>` is a placeholder for the actual process ID. Available commands and information depend on the JVM/JDK. In HotSpot:
- `VM.classloader_stats` helps inspect ClassLoader statistics (if the command is available in that JVM).
- Thread dumps help find threads still running plugin code or holding a related TCCL.
- `GC.class_histogram`/heap dumps can help analyze instances and retention paths, though production overhead must be considered.
- Heap analysis tools like Eclipse Memory Analyzer can help inspect **path to GC roots**, dominator trees, and retained heap.

### Do not look at metaspace only once

Metaspace can grow due to legitimate class loading, JVM caching, or GC activity; usage not dropping immediately is not enough to conclude a leak. A stronger signal is **multiple old plugin loader generations remaining reachable and growing with each redeploy**, along with concrete reference paths from long-lived GC roots.

Distinguish between:
- **Open/locked JAR bytes**: I/O/file handle issue; `URLClassLoader.close()` helps release them.
- **Plugin object still in listener registry**: strong reference issue; requires unregistering.
- **ServiceLoader/provider caches not dropped**: discovery object/cache lifecycle issue.
- **Worker TCCL still holding plugin loader**: thread context/lifecycle issue.
- **Class metadata not unloading immediately**: could be GC timing; measure over time/roots.

## 16. Heap dump: reading “path to GC roots” properly

Suppose you discover `PluginClassLoader-v1` is still alive when it should have been unloaded. A retaining path might be:

```text
GC Root: System ClassLoader's class / host static field
    └── host.EventBus.REGISTRATIONS
          └── ArrayList.elementData[5]
                └── impl.PluginHook instance
                      └── runtime Class / loader
                            └── PluginClassLoader-v1
```

Or:

```text
GC Root: live executor Thread
    └── contextClassLoader
          └── PluginClassLoader-v1
```

Or:

```text
GC Root: host static service registry
    └── cached ServiceLoader<Hook>
          ├── explicit discovery ClassLoader
          └── provider instance cache
                 └── PluginHook instance
```

These diagrams **describe typical causes**, not guaranteed identical internal field names across every JVM.

Process for reading a heap dump:
1. Select **the loader instance belonging to an old plugin generation**, distinguishing it from the current loader.
2. Inspect objects of plugin classes defined by the old loader.
3. Use **path to GC roots, excluding weak/soft/phantom references** when supported by the tool to prioritize strong retention.
4. Identify the **owner outside the plugin** (host registry, thread, module layer, singleton).
5. Find the corresponding registration/cleanup path and verify it runs on both normal and error shutdown.
6. Re-measure after multiple redeploy cycles and appropriate GC.

Do not “fix” a leak by holding suspected objects in a debugger/test code and expecting GC to unload them: the tool/test itself can keep the referent reachable.

## 17. Designing PluginContext with clear ownership

A resilient plugin architecture has **one responsible owner for each resource**. The host can create a context for the plugin to register all handles needing cleanup:

```text
PluginManager
   └── PluginSession
         ├── Plugin ClassLoader
         ├── ServiceLoader / provider instances
         ├── Event subscriptions
         ├── Scheduled tasks / Executor-owned handles
         ├── MBean / JDBC / logging registrations
         └── Closeable resources
```

When stopping:
- Stop accepting new plugin work.
- Allow already started work to finish or cancel according to policy.
- Invoke the plugin's stop hook while the loader and dependencies are still available.
- Close subscriptions/registrations and cancel scheduled tasks.
- Clean up ThreadLocals/TCCL on the proper thread/scope.
- Close streams/sockets/connections owned by the session.
- Clear host caches pointing to plugin instances/classes/loaders.
- Drop the old ServiceLoader; if reloading providers, create a discovery context for the new generation.
- Close URLClassLoader if the host owns and uses that type of loader.
- Remove the session from PluginManager's registry.

If one cleanup step fails, **still attempt the remaining steps**, collect/suppress exceptions, and report them together. Do not abort midway, leaving other registrations behind just because one listener threw an exception.

### Simple resource stack example

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class CleanupStack implements AutoCloseable {
    private final Deque<AutoCloseable> resources =
            new ArrayDeque<>();

    public void own(AutoCloseable resource) {
        resources.push(resource);
    }

    @Override
    public void close() throws Exception {
        Exception failure = null;

        while (!resources.isEmpty()) {
            AutoCloseable resource = resources.pop();
            try {
                resource.close();
            } catch (Exception ex) {
                if (failure == null) {
                    failure = ex;
                } else {
                    failure.addSuppressed(ex);
                }
            }
        }

        if (failure != null) {
            throw failure;
        }
    }
}
```

This is a **compilable `CleanupStack.java` file** on Java 17. Register resources in ownership order; `push` and `pop` cause cleanup to run in **reverse registration order**.

Usage example (snippet):

```java
try (CleanupStack scope = new CleanupStack()) {
    scope.own(registrationA);
    scope.own(registrationB);
    // Execute plugin while registrations are active.
}
```

`registrationA`/`registrationB` here are placeholders for real `AutoCloseable` instances. Do not use the same `CleanupStack` from multiple threads without adding synchronization; the class illustrates managing a sequential scope. Also, the order of stopping tasks before cleaning up callbacks/loaders must be enforced at the PluginManager layer; do not blindly push all lifecycle responsibility onto the stack.

### Why is this useful?

- Clear resource owner, avoiding forgotten unsubscribes.
- Exiting the scope via `return`/exception still calls `close()`.
- Cleanup errors are preserved as suppressed exceptions.
- Easy to test idempotent `close()` on individual wrappers.
- Avoids turning `ServiceLoader.reload()` into a plugin-stopping mechanism.

This is a helper pattern, not a replacement for full concurrency and lifecycle policies.

## 18. Shutdown order and race conditions

Avoid:

```text
Thread A: close PluginClassLoader
Thread B: loading a new plugin class
Thread C: event bus invoking a plugin listener
```

With `URLClassLoader.close()`, the Java API warns that the result of loading classes concurrently with close is undefined. Functionally, even if the loader is closed, an already dispatched event may continue invoking a callback; if the callback lazily loads a class/resource, it can fail.

A safe order is typically:

```text
ACTIVE
  ↓ 1. set state STOPPING (accept no new work)
STOPPING
  ↓ 2. cancel/drain, await in-flight work
QUIESCENT
  ↓ 3. stop providers, unregister callbacks/listeners
CLEANING
  ↓ 4. close owned resources, drop ServiceLoader/registry refs
  ↓ 5. restore per-thread context, shutdown owned executors
  ↓ 6. close loader and release session refs
CLOSED
  ↓ 7. GC can unload later
```

Detailed steps may vary by dependency. For example, threads must restore TCCL **before completely stopping** if they set TCCL themselves; shutting down an executor does not automatically let the host access another worker's ThreadLocals to remove context properly. Design cleanup hooks to run **inside the task/thread that used the context**, rather than waiting until the end and trying to “clear a thread local from another thread.”

### Use explicit states

`PluginManager` should have states such as `NEW / STARTING / ACTIVE / STOPPING / CLOSED`, reject new callbacks/tasks after `STOPPING`, and make `stop()` **idempotent** where possible. This helps prevent two threads from concurrently undeploying and repeating remove/close out of order.

An idempotent `close()` on a listener registration token makes comprehensive cleanup even easier when application shutdown encounters various failures.

## 19. Why plugin-owned static caches are not always a problem

A self-referencing static cache inside a plugin generation **does not cause a leak by itself** if the entire generation graph is no longer reachable from GC roots. Conversely, a **host static registry** holding a plugin's provider/listener/callback maintains a reference path outside the generation.

Distinguish cache owner and reference direction. The static field/cache reflection article analyzes specific cases where per-generation caches or `ClassValue` should be used.

## 20. Testing cleanup conditions without relying on GC

Deterministic assertions immediately after undeploy:
- `registry.size() == 0` for the old plugin's registrations.
- `pluginSession.isClosed()` or state `CLOSED`.
- The count of plugin-registered subscriptions/handlers/timers returns to baseline.
- Plugin worker tasks are no longer in-flight; owned executors are shut down.
- Worker TCCLs are restored or plugin-owned workers have terminated.
- `ServiceLoader` and provider instances of **the old generation** are no longer held in host registries/caches.
- A new loader can load a new implementation version via the shared API without runtime class identity conflicts.

A test scenario should model:

```text
Deploy v1
  → register listener, create provider/cache
  → assert plugin active and callable

Stop v1
  → unregister listener, clear caches, close loader
  → assert no old callbacks/owners
  → do NOT assert immediate class unloading

Deploy v2 with fresh loader
  → assert new implementation selected
  → assert shared host API still assignable

Repeat N times
  → check loader count/metaspace trend under controlled GC
```

In the soak step, use heap dumps/reference paths if the trend rises abnormally. Do not turn the test suite into an infinite `System.gc()` loop, because the JVM may not collect classes immediately and GC timing is not a synchronous API.

## 21. Special case: ServiceLoader in a host using TCCL

Suppose a framework in the host loader calls:

```java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);
```

By contract, this overload picks the calling thread's TCCL. If a thread pool is reused across plugins:
- TCCL still holds `PluginLoader-v1` → service discovery may find the v1 provider.
- Changing TCCL to `PluginLoader-v2` later does not mean the old `providers` automatically switches its discovery loader; it was created in the old context.
- A host static `providers` cache still retains the ServiceLoader object and references related to the old loader.

Solution:
1. Scope TCCL per task and restore it in `finally`.
2. If the host knows the right loader, prefer `ServiceLoader.load(service, pluginLoader)` for clarity.
3. Do not cache `ServiceLoader` solely by service type if the provider set actually **depends on each plugin generation/ClassLoader/ModuleLayer**.
4. When unloading, drop the old generation's cache entry, stop provider tasks, and clean up callback registrations.
5. Create a new ServiceLoader for the new generation's loader/layer.

This scenario often causes confusion between **class loading**, **service discovery**, **thread context**, and **memory retention**.

## 22. Key signs in logs, heap dumps, and monitoring

| Sign | Possible cause | Next check |
|---|---|---|
| Listener continues receiving events after plugin stop | Subscription not removed, in-flight queue | Registry snapshot, owner registration token |
| Multiple old plugin class loader instances after redeploy | Registry/cache/threads holding reference | Path to GC roots |
| `ServiceLoader` returns old provider after update | Cache + old loader, no new context created | ServiceLoader object, loader/layer, `reload`/replace |
| Metaspace grows with redeploy count | Classloader generations not collected | Class loader stats, GC roots, trend |
| JAR cannot be deleted on Windows | Open file handles | URLClassLoader.close, JarFile, other streams |
| NoClassDefFoundError after close | Plugin/code still active, needs new dependency | Shutdown order, lazy loading, in-flight tasks |
| Request B uses plugin A's provider | Worker TCCL retained from previous request | TCCL set/restore in task |
| Thread pool does not stop when plugin stops | Executor/scheduled job still alive | Threads, queue, owner shutdown |
| `WeakReference.get()` still non-null after stop | GC has not run or strong refs remain | Do not conclude yet; check registry/roots |
| Leak only occurs on error during start | Cleanup did not run on failure path | try/finally, cleanup stack, partial registration |

Where possible, logging should associate **plugin generation ID** with loader object identity (not just class name), and record the number of registrations/providers/tasks still owned by that generation.

## 23. Common anti-patterns

### 23.1. “Close is enough”

```java
// Architectural anti-pattern, snippet:
pluginLoader.close();
// hostRegistry still holds plugin instances
```

**Wrong** because close does not remove registry entries. Unsubscribe/drop references before or during the shutdown protocol.

### 23.2. “Reloading ServiceLoader removes old providers everywhere”

```java
// Snippet:
services.reload();
```

**Wrong** if a listener registry still contains the provider, or ServiceLoader still holds an explicit plugin loader. `reload` does not call `close()` on providers.

### 23.3. “Using WeakHashMap eliminates leaks”

Wrong when the map value or another reference still retains the loader/key, and when data requires strong lifecycle ownership.

### 23.4. “Using System.gc() to unload plugins”

```java
System.gc();
```

The API only requests GC; there is no guarantee of collecting a reachable loader. In particular, if a host static field still holds a callback/provider, GC is not allowed to reclaim that object.

### 23.5. “Using a new loader while the host cache still holds the old version”

The new loader can define the same binary name as a new runtime class, but `Class<?>`/provider objects from the old loader in the host registry remain alive. Casting implementations across two generations can throw `ClassCastException`.

### 23.6. “Clearing all static caches in the plugin via reflection”

Unnecessary if no strong refs remain from the host/GC roots; it can also cause access issues in JPMS. It is better to clean up **cross-loader-boundary references** and owned resources with explicit lifecycles.

## 24. Code review checklist for plugin systems

### Before deployment

- Shared service APIs/interfaces reside in the **host/common loader** or a stable shared module.
- Private plugin implementations/dependencies reside in a dedicated loader per architecture.
- An ownership model exists for loaders, ServiceLoaders, listeners, async tasks, ThreadLocals, and external resources.
- Registration APIs return tokens or support unregistering by the proper owner.
- Clear rules specify whether TCCL or an explicit loader/module layer is used during discovery.

### During ACTIVE lifecycle

- Track lists of subscriptions/providers/tasks belonging to each plugin generation.
- TCCL is set/restored per scope, especially in executors.
- Do not use a global static cache keyed solely by class name for plugins with multiple generations.
- Do not let providers spawn unbounded background threads without a stop hook.
- Do not close the loader prematurely if the plugin may lazy-load classes/resources.

### During STOPPING

- Reject new work and wait for in-flight tasks.
- Invoke stop hooks while plugin dependencies are still active.
- Unregister listeners, MBeans, drivers, and shutdown hooks owned by the plugin.
- Cancel timers/tasks and shut down plugin-owned executors.
- Remove ThreadLocals and restore TCCL on the proper thread.
- Close streams/sockets/connections, handling errors while still cleaning up the rest.
- Clear host registry/cache refs to provider instances, `Class<?>`, reflection objects, ServiceLoader, layer, and loader.
- Call `URLClassLoader.close()` where applicable and drop session references.

### After cleanup

- Assert registry counts/owners return to expected levels.
- Do not require synchronous GC/unloading.
- Run reload integration tests with a fresh-generation loader.
- Monitor metaspace/loader generations across multiple deploy cycles; if rising, analyze GC roots.
- Do not touch another plugin's resources during teardown.

## 25. Self-check questions

1. **Does `URLClassLoader.close()` automatically unload all classes?** No, it closes lookup sources and resources; already loaded classes can remain alive.
2. **Can a listener in a host static registry retain the plugin loader?** Yes, via the implementation object/class/loader.
3. **If the event bus stops emitting events, does the listener stop leaking?** No; the reference must be removed.
4. **Can `ServiceLoader.findFirst()` cause the cache to retain a provider instance?** Yes, the ServiceLoader instance can cache instantiated providers.
5. **Does `ServiceLoader.reload()` clear listeners registered by the host?** No.
6. **Does an old ServiceLoader still retain the discovery loader after `reload()`?** Potentially yes, because it remains a discovery object with its configured loader/context.
7. **Why is a host static `Map<String, Class<?>>` dangerous?** It can retain the plugin runtime Class and its defining loader.
8. **Do self-referencing static fields inside a plugin always cause a leak?** No; if the entire group is no longer reachable from GC roots, GC can collect it.
9. **What happens if a thread pool's TCCL still points to an old plugin?** It holds a strong reference and may select the wrong provider.
10. **Is `setContextClassLoader(null)` always right during cleanup?** No; restore the exact previous value.
11. **Does removing a ThreadLocal automatically stop a background thread?** No; a separate task/executor lifecycle is needed.
12. **Does using `WeakHashMap` with a value strongly holding the key make the entry disappear automatically?** No.
13. **Does `WeakReference.get() != null` right after stop prove a leak?** No; GC may not have run yet.
14. **How should cleanup be tested reliably?** Assert unregistration, empty registries, dropped caches, completed tasks, and restored TCCL; GC observation is supplementary.
15. **What should you investigate if classloader count grows across redeploys?** Live loader generations and paths to GC roots.
16. **Can you swap in a new-generation provider without cleaning up the old provider?** Technically possible, but prone to leaks, wrong provider selection, and type identity conflicts.
17. **What is the purpose of a subscription token?** To ensure the host has a handle to cancel the exact registration belonging to the plugin.
18. **Does `ModuleLayer` have automatic close()/unload?** No.
19. **Is ServiceLoader thread-safe?** No; coordinate when iterating/reloading from multiple threads.
20. **What is the practical goal of undeploying?** Stop the plugin, clean up resources and references; GC can unload classes afterward.

## Official references

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): discovery, caching, `reload()`, threading, and provider lifecycle.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): close behavior and loaded classes/resources.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation, and runtime class identity.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): TCCL and thread lifecycle.
- [Java SE 17 — WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): reachability and weak references.
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys and warning that values can retain keys.
- [JVMS 17 — `5.3` Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loaders, runtime identity, class lifecycle.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-local data and `remove()`.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layer runtime and ClassLoader mapping.

**Conclusion:** When a plugin has stopped but memory does not decrease, check **who is still retaining the plugin**: listener registries, host singletons/caches, `ServiceLoader` and cached provider instances, TCCL/ThreadLocals, background tasks, or framework registries. `close()` and `reload()` only handle **part of the lifecycle**; they do not remove strong references from the system. Proper cleanup is **stop work → unregister/close owned resources → drop caches and references → close loader → let GC decide unloading**, using structural tests and GC root analysis rather than relying on `System.gc()`.
