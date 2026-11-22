# Lifecycle and Reclaimability of Custom Layers in the Java Module System

## 1. Objectives

After this lesson, you can:

- Explain when a custom `ModuleLayer` is created, used, and becomes eligible for garbage collection.
- Distinguish the lifecycles of `ModuleLayer`, `ClassLoader`, plugin objects, and class metadata in the JVM.
- Design a plugin shutdown operation so that modules from an old layer are not accidentally retained.
- Recognize sources of strong references and how to observe class unloading.
- Understand why there is no immediate `close()` or `unload()` command for `ModuleLayer`.

Examples use Java 17+ and JPMS (Java Platform Module System). The core mechanisms apply to modern JDKs that support `ModuleLayer`.

## 2. How Does a Custom ModuleLayer Live and End?

`ModuleLayer` is a set of modules bound to a `Configuration`, having parent relationships with one or more layers and a mapping from modules to class loaders. The boot layer (`ModuleLayer.boot()`) contains the modules of the initial runtime environment. An application can define additional layers to load a set of modules at runtime, such as plugin modules or isolated component versions.

A typical application lifecycle:

1. **Module discovery:** use `ModuleFinder` to find modules in JARs or a module directory.
2. **Resolve:** create a `Configuration` from the parent layer's configuration and root modules.
3. **Define layer:** define the modules and corresponding class loaders using `ModuleLayer` APIs.
4. **Initialize and use:** load providers via `ServiceLoader`, instantiate objects, and invoke business logic.
5. **Stop using:** stop tasks, threads, and schedulers, close resources, and unregister callbacks.
6. **Drop strong references:** clear caches, registries, provider lists, and external references that still hold the layer or class loader.
7. **GC and class unloading (if eligible):** the JVM can reclaim Java objects, and then reclaim class metadata of class loaders that are no longer live during an appropriate GC cycle.

**Key point:** A layer does not own an active teardown mechanism. The `ModuleLayer` API does not provide `close()`, `dispose()`, or `unload()`. An application no longer using a layer merely opens the possibility of garbage collection; it does not guarantee memory is freed immediately at that moment.

### Three Lifecycles to Distinguish

| Component | Liveness condition | Meaning when ended |
| --- | --- | --- |
| `ModuleLayer` object | Still reachable from GC roots via strong references | The layer object itself can be GC'd when no longer reachable |
| Class loader defining modules in the layer | Still reachable directly or indirectly via threads, classes, objects, caches, other layers, etc. | When the class loader is no longer live and the JVM performs class unloading, classes defined by that loader can be unloaded |
| Plugin instances and resources | Consumers still hold references; threads, streams, sockets, executors, etc. are still active | Must be stopped/closed according to the business contract; GC does not replace resource cleanup |

Collecting a `ModuleLayer` **does not mean** every class or resource of the plugin has been freed. Conversely, if classes, loaders, and instances remain retained by external sources, the old layer may stay alive through reference chains or most of its memory may remain unreclaimable.

## 3. Reference Relationships Determine Reclaimability

View a custom layer as an object graph, not an isolated process with a power-off button:

~~~text
GC roots (running threads, statics of long-lived modules, registries, ...)
    |
    +-- PluginRegistry --> PluginSession --> ModuleLayer
    |                                        |--> Configuration
    |                                        +--> Module / ClassLoader
    |
    +-- Thread.contextClassLoader ------------> Plugin ClassLoader
    |
    +-- Cache<Class<?>, Object> --------------> Plugin Class<?>
    |
    +-- Listener / callback ------------------> Plugin instance
                                                 |
                                                 +--> Class<?> --> defining ClassLoader
~~~

The arrows above illustrate **possible reference-retention paths**, not a mandatory internal structure of every JDK version. GC determines live objects from GC roots. A reference cycle confined to a group of objects no longer reachable from any root can still be GC'd; two objects pointing to each other do not by themselves create a memory leak.

Sources of class loader retention worth checking:

- **Host registries:** `Map<String, ModuleLayer>`, `List<Plugin>`, `ServiceLoader`, or `Provider` holding objects from a previous load.
- **Threads:** threads spawned by a plugin that have not stopped; long-lived thread pools; `Thread.contextClassLoader` still pointing to the plugin's loader.
- **Callbacks and listeners:** event buses, schedulers, JMX, logging handlers, shutdown hooks, or framework registries still holding listeners, lambdas, or method references created by the plugin.
- **Caches and reflection:** `Class<?>`, `Method`, `Constructor`, `MethodHandle`, dynamic proxies, serializers, or caches keyed or valued by plugin classes.
- **Unclosed resources:** sockets, files, timers, executors, watchers, etc. cause operational side effects and can also retain references to the plugin.
- **Child layers:** a layer defined from a parent layer has relationships to its parents; if a child layer is still retained, the necessary parents can also remain alive.

Do not treat `static` fields of every plugin class as independent GC roots. Static fields in classes managed solely by an otherwise reclaimable class loader do not usually prevent an unreachable loader from being unloaded on their own. The major risk arises when **a long-lived external object** (for example a class in the boot/application layer or a global registry) retains a plugin instance, `Class`, or loader.

## 4. Choosing an Appropriate Layer Definition Strategy

Common approaches:

- `parentLayer.defineModulesWithOneLoader(configuration, parentLoader)`: creates a new class loader for the modules in the new configuration; those modules share this loader.
- `parentLayer.defineModulesWithManyLoaders(configuration, parentLoader)`: creates a separate new loader for each module in the configuration.
- `ModuleLayer.defineModules(configuration, parentLayers, mapper)`: uses an application-supplied function mapping modules to class loaders; pay close attention to the lifecycle of the loaders returned by the mapper.
- The static methods returning `ModuleLayer.Controller` allow adjusting reads, exports, and opens relationships of the corresponding layer's modules; the controller is also an object whose references should be dropped when no longer needed.

**Note:** The `parentLoader` argument of the first two convenience methods is the parent loader for the new loaders; it does not mean the new modules are defined directly into `parentLoader`. If you map modules into a shared loader that lives for the entire application lifetime, you will generally not achieve independent reclaimability per plugin load.

A layer is not an absolute security boundary or resource boundary: plugin code still runs in the same JVM and can spawn threads, interact with modules it is allowed to access, hold native resources, or create references from the host.

### Reloading a Plugin

To replace a running module version, the common approach is:

1. Stop all work of the old version.
2. Unregister everything and close resources of the old version.
3. Clear strong references to old instances, classes, loaders, and the old layer.
4. Create a **new configuration and layer** from the new version's artifact.
5. Load providers and put the new version into service.

You cannot mutate a module already defined in an existing layer into new-version bytecode by calling `ModuleLayer` again. Adjustments to reads/exports/opens via a controller are not a mechanism for swapping bytecode or undoing all state created by an old module.

## 5. Example: Managing a Plugin Session with AutoCloseable

Suppose the host has module `com.example.host`, the shared API `com.example.spi` resides in the boot layer, and the plugin JAR contains module `com.example.plugin`. Placing the SPI interface in a long-lived module allows the host to invoke the service through a stable type without directly retaining the plugin's implementation class.

**In the SPI module:**

~~~java
// module-info.java of com.example.spi
module com.example.spi {
    exports com.example.spi;
}
~~~

~~~java
// com/example/spi/TaskPlugin.java
package com.example.spi;

public interface TaskPlugin {
    void execute();
    void shutdown();
}
~~~

**In the plugin module:**

~~~java
// module-info.java of com.example.plugin
module com.example.plugin {
    requires com.example.spi;
    provides com.example.spi.TaskPlugin
        with com.example.plugin.ExampleTaskPlugin;
}
~~~

~~~java
// com/example/plugin/ExampleTaskPlugin.java
package com.example.plugin;

import com.example.spi.TaskPlugin;

public final class ExampleTaskPlugin implements TaskPlugin {
    @Override
    public void execute() {
        System.out.println("Executing from custom layer");
    }

    @Override
    public void shutdown() {
        // Unregister callbacks, close resources owned by the plugin.
    }
}
~~~

**In the host module:**

~~~java
// module-info.java of com.example.host
module com.example.host {
    requires com.example.spi;
    uses com.example.spi.TaskPlugin;
}
~~~

~~~java
package com.example.host;

import com.example.spi.TaskPlugin;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.Set;

public final class PluginSession implements AutoCloseable {
    private ModuleLayer layer;
    private List<TaskPlugin> providers;

    private PluginSession(ModuleLayer layer, List<TaskPlugin> providers) {
        this.layer = layer;
        this.providers = providers;
    }

    public static PluginSession open(Path pluginJar) {
        Objects.requireNonNull(pluginJar);

        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(pluginJar);
        Configuration configuration = parent.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("com.example.plugin")
        );

        // Create a new loader for the custom layer's module.
        ModuleLayer child = parent.defineModulesWithOneLoader(
            configuration,
            TaskPlugin.class.getClassLoader()
        );

        List<TaskPlugin> instances = ServiceLoader
            .load(child, TaskPlugin.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .toList();

        return new PluginSession(child, instances);
    }

    public synchronized void runAll() {
        if (layer == null) {
            throw new IllegalStateException("PluginSession already closed");
        }
        for (TaskPlugin plugin : providers) {
            plugin.execute();
        }
    }

    @Override
    public synchronized void close() {
        if (layer == null) {
            return;
        }

        RuntimeException failure = null;
        try {
            for (TaskPlugin plugin : providers) {
                try {
                    plugin.shutdown();
                } catch (RuntimeException ex) {
                    if (failure == null) {
                        failure = ex;
                    } else {
                        failure.addSuppressed(ex);
                    }
                }
            }
        } finally {
            // Break references directly owned by the session.
            providers = List.of();
            layer = null;
        }

        if (failure != null) {
            throw failure;
        }
    }
}
~~~

How to call it:

~~~java
try (PluginSession session =
         PluginSession.open(Path.of("plugins", "example-plugin.jar"))) {
    session.runAll();
}
// close() has called shutdown() and dropped references managed by the session.
~~~

Conditions for the example to work:

- The JAR is a **valid modular JAR** with the exact module name `com.example.plugin`; `com.example.spi` can be resolved from the parent layer.
- The host module must be able to read the SPI and declare `uses` accordingly; the plugin declares `provides`.
- The host does not keep `TaskPlugin` instances, `ServiceLoader`, providers, or the old session's class loader elsewhere.
- `shutdown()` genuinely stops threads/tasks and cleans up resources and listeners created by the plugin.
- The session-opening path can throw errors during provider discovery or initialization. In a real system, add cleanup when **partial initialization fails**, not only when `close()` of a succeeded session is called.

The `AutoCloseable` pattern defines an **application-controlled resource-shutdown contract**. It does not force the JVM to unload classes immediately, nor can it automatically discover every reference placed into external registries by frameworks or plugin code.

## 6. Why Can a Supposedly Closed Custom Layer Still Persist?

### 6.1. Thread Context Class Loader

A library might temporarily swap the context class loader to discover resources or providers:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Perform operation that requires the plugin's context loader.
} finally {
    current.setContextClassLoader(previous);
}
~~~

If `finally` is omitted, a long-lived request-handling thread can retain the loader after the plugin session ends. If new threads are created, you must manage their lifecycle, stop them with an appropriate protocol, and `join` or await executor termination when needed; merely resetting the current thread's context loader is not enough.

### 6.2. Registries and Caches Outliving the Layer

Dangerous example:

~~~java
// Host registry that exists for the entire run.
static final java.util.Map<String, TaskPlugin> ACTIVE =
    new java.util.concurrent.ConcurrentHashMap<>();
~~~

If the host places an instance from a custom layer into `ACTIVE` and only sets `layer = null`, the instance remains reachable. When stopping a plugin, you must `remove` the corresponding entry; the same applies to `Class<?>` caches, listeners, schedulers, and every registry populated during loading.

Caches keyed by `Class<?>` are particularly easy to get wrong. If the cache itself is static in the host, strong keys can retain old classes and class loaders. Using weak keys can help, but you must also examine the values and reference chains from values; `WeakHashMap` does not automatically break a cycle that has a strong path from value back to key.

### 6.3. Closing Resources While Still Holding Instances

`shutdown()` or `close()` may release files/sockets/threads, yet if the host still keeps service instances, GC cannot reclaim all related objects and the loader. Two separate actions are needed: **proactive resource cleanup** and **eliminating strong references**.

### 6.4. Using a Process-Wide Class Loader

When updating a plugin multiple times while still defining classes into a loader kept long-term by the system, dropping the layer wrapper does not enable independent class unloading. For plugins that need to be replaced repeatedly, design loader boundaries per load session and avoid retaining that loader after the session ends.

### 6.5. Parent Layers and Child Layers

A custom layer can have multiple parents; `parents()` reflects layer relationships. A still-living child layer itself can keep its required parents alive. Unloading a branch must account for all active layers/connections, not only the session marked as stopped.

## 7. Observing Reclaimability and Class Unloading

### 7.1. WeakReference Is Only a Signal of Reachability

You can track a layer or loader using a `WeakReference` without keeping it alive with a strong reference:

~~~java
import java.lang.ref.WeakReference;

// Capture while the session is active:
WeakReference<ClassLoader> weakLoader =
    new WeakReference<>(layer.findLoader("com.example.plugin"));

// After stopping the session, clear all strong references held in the host.
// When the JVM runs GC, weakLoader.get() may become null.
~~~

The snippet above only illustrates the technique of taking a weak reference; in a real program, the `layer` variable and local variables holding the loader must go out of scope. `weakLoader.get() == null` indicates that the weakly referenced object is no longer strongly held at the time of inspection; it **does not replace evidence from class unloading logs**. Conversely, a non-null value right after closing a session does not yet prove a memory leak.

`System.gc()` is only a request/hint to perform GC, and the JVM may not respond as expected. Do not write functional tests that rely on a fixed number of milliseconds to force a weak reference to become null.

### 7.2. Diagnostic Tools

With a HotSpot JVM supporting unified logging:

~~~text
java -Xlog:class+unload=info -m com.example.host/com.example.host.Main
~~~

Class unloading logs help confirm that classes are actually unloaded in practice. You can combine GC logs or JFR/JDK Mission Control to observe trends in class loaders and metaspace. On supported environments, `jcmd <pid> VM.classloader_stats` reports loader statistics; exact syntax and detail level depend on the JDK/JVM.

To investigate repeated-load scenarios:

1. Create a plugin session, run some tasks, and close the session; repeat in a controlled test environment.
2. Monitor the number of class loaders, loaded classes, and metaspace after actual GC cycles; prioritize **trends over multiple cycles**.
3. If the loader/class count grows continuously, use a heap dump and path-to-GC-root analysis tools to find the specific holder.
4. Inspect thread dumps, thread context class loaders, listeners, registries, caches, schedulers, and static fields in the host module.
5. After removing the true retention path, repeat the measurements and look for unloading events when the JVM runs an appropriate GC.

Do not conclude there is a memory leak solely because metaspace has not shrunk immediately after closing a layer once: the JVM has its own GC and memory allocation/retention policies.

## 8. Lifecycle Design Principles for Plugin Systems

- Clearly define **who owns** the layer, loader, providers, tasks, listeners, and external resources.
- Provide a shutdown contract such as `AutoCloseable`, `shutdown`, or `stop`; invoke it once according to the managed lifecycle.
- Separate long-lived API/SPI from implementations loaded inside custom layers.
- Avoid letting plugins spawn unmanaged background threads; use host-provided executors or explicit lifecycle interfaces.
- Every `register` operation must have an `unregister` path, and every plugin cache needs an entry-eviction policy.
- Keep `ServiceLoader`, `Provider`, `Class<?>`, `MethodHandle`, and class loaders scoped to the session rather than in global variables.
- If swapping the thread context class loader, always restore it in `finally`.
- When reloading, create a new layer/loader for the new version's code and dispose of the old session's resources before dropping references.
- Diagnose reclaimability by observing reachability, class unloading, and GC roots; avoid assuming specific GC timing.

## 9. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Setting `layer = null` unloads the plugin.” | It only drops one reference; you must also account for all references to the loader, classes, providers, and related resources. |
| “`ModuleLayer` has a close API like `URLClassLoader`.” | `ModuleLayer` has no close/unload API. The business lifecycle must be designed by the host. |
| “Closing files/sockets is enough to unload classes.” | Resource cleanup and making the loader unreachable are two different conditions. |
| “When GC runs, all classes will unload.” | Unloading depends on loader reachability and JVM policies/cycles. |
| “Creating a new layer automatically replaces old modules.” | Two versions can coexist with different loaders; the host must switch dispatch and release the old session. |
| “A child layer does not affect its parent.” | Parent relationships and references from a live layer can extend the lifetime of related components. |

## 10. Self-Check Questions

1. Why can a `TaskPlugin` instance sitting in a host static registry prevent the plugin class loader from being reclaimed?
2. Distinguish the effect of `PluginSession.close()` from the JVM class unloading process.
3. When you see `WeakReference<ClassLoader>.get()` still non-null right after ending a plugin, what should you check before declaring a memory leak?
4. For a system that reloads plugins hundreds of times, why should you avoid reusing a defining class loader that lives for the entire process?
5. What reference-retention paths can arise from context class loaders, schedulers, listeners, and `ServiceLoader`?

**Conclusion:** Reclaimability of a custom layer is the result of lifecycle design, resource management, and the reference graph. The host must proactively stop activity and drop references of the plugin session; only then does the JVM have the opportunity to collect the layer, class loader, and class metadata at an appropriate time.