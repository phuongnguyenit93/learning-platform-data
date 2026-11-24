# Finding References Retaining Class Loaders from Caches, ThreadLocals, Threads, and Callbacks During Plugin Replacement

## 1. The problem: the plugin stopped, yet the old loader remains

A Java host may load plugin version A with its own `URLClassLoader`, then replace it with version B using a new loader. Even after calling `close()` on loader A, deleting the old JAR file, and seeing no trace of A's features in the UI, heap/metaspace keeps growing with every deployment. Usually the issue is **not that the JVM forgot to free classes**: one or more references from live objects still retain loader A or classes/instances it defined.

Example of a *retaining path*:

```text
GC Root
  -> host static field
  -> ConcurrentHashMap
  -> plugin callback instance
  -> callback Class
  -> defining ClassLoader of plugin A
  -> related classes / metadata
```

Another retaining source:

```text
GC Root
  -> live Java Thread in executor pool
  -> contextClassLoader (TCCL)
  -> plugin ClassLoader A
```

Or:

```text
GC Root
  -> Java Thread in pool
  -> ThreadLocalMap entry.value
  -> object defined by plugin A
  -> Class / defining loader A
```

The paths above are **conceptual diagrams**; actual field names and node shapes displayed in a heap analyzer depend on the JVM and version. This lesson focuses on **finding, explaining, and eliminating real reference paths** from caches, `ThreadLocal`, threads, and callbacks, rather than calling `System.gc()` or `URLClassLoader.close()` as a magic “force unload.”

**Expected outcomes:** you will distinguish resource leaks from class-loader retention, identify reference ownership, build a Java 17 experiment reproducing all four retaining sources, investigate using heap dumps/GC roots, and establish a plugin replacement workflow that leaves no references from old versions.

## 2. Conditions for class unloading: closing the loader is not enough

In the JVM, a class's runtime identity depends on **its binary name and its defining class loader**. A `com.example.Plugin` class belonging to loader A is not the same class as an identically named class defined by loader B. When upgrading a plugin, the new loader can create new class definitions while the old loader stays alive.

Points to distinguish:

- **`URLClassLoader.close()`:** releases resources such as JAR/file handles opened by the loader and prevents using the closed loader to load new classes/resources per the API contract. It does **not** destroy instances, static state, threads, or already-defined classes.
- **Stopping plugin logic:** halting incoming requests, stopping callbacks, completing/cancelling work, and unregistering from the host. This is the application's responsibility; `ClassLoader` does not do it automatically.
- **Class unloading:** the JVM/GC can reclaim class metadata once no references keep the loader/classes/instances alive. There is no safe Java 17 API like `unloadClass("demo.plugin.X")` to force-unload individual classes.
- **The JAR file may be closed while the loader stays alive.** A `ClassLoader` object held in a `static Map` or TCCL remains a reachable Java object even with zero OS handles left.
- **Not seeing immediate unloading does not by itself prove a leak.** GC, class unloading, and collection timing can lag; distinguish *not yet GC'd*, *intentional retention*, *unintentional retention*, and *a leak growing across generations*.

To diagnose accurately, ask: **“From which GC root can an object of the old loader still be reached?”** rather than merely asking “Why didn't `close()` shrink heap right away?”.

## 3. Classifying the four common retaining sources

| Retaining source | Typical reference chain | Symptom in application | How to release |
|---|---|---|---|
| Host cache/registry | `static Map → plugin instance / Class / Method / ClassLoader` | Reload completes yet entries or old generations keep growing | Invalidate entries by plugin ID + generation; clear references via proper owner |
| `ThreadLocal` on long-lived thread | `Thread → threadLocals → entry.value → plugin object` | Pool has handled many requests yet still holds old classes | `remove()` on the **exact thread** that called `set()`, ideally in `finally` |
| Thread/TCCL | `Thread → contextClassLoader → plugin loader`; or `Thread → Runnable → plugin` | Worker keeps running/waiting; TCCL shows old loader | Restore TCCL; stop/join plugin-owned workers; drain pools/queues |
| Callbacks/listeners/subscriptions | `host event bus → listener list → plugin listener` | Obsolete events still fire or registry retains subscriptions | `unsubscribe`/remove exact instance; cancel scheduled jobs; await in-flight callbacks |

One loader can be retained through **multiple** paths simultaneously. Clearing a cache entry is not enough if a thread pool still holds TCCL, and stopping threads is not enough if an event bus still retains a listener. Heap analyzers often show only a few shortest paths; once you fix one path, another may surface.

Distinguish **direct references to the loader** from **references to objects defined by the loader**: retaining `Class<?>`, `Method`, `Constructor<?>`, lambdas, proxies, or plugin instances can equally prevent the defining loader from being reclaimed. Do not search only for fields declared as `ClassLoader`.

## 4. Caches and static registries: the easiest place to overlook

Hosts often cache plugins for fast lookup:

```java
// Anti-pattern example (not a standalone program).
static final Map<String, Object> PLUGIN_CACHE = new HashMap<>();
PLUGIN_CACHE.put("reporter", pluginInstance);
```

If `PLUGIN_CACHE` belongs to a class defined by the application/parent loader and lives for the process lifetime, `pluginInstance` can retain the old plugin's loader. Updating the entry to a new version is safe only when **every** reference to the old object truly disappears; do not infer that from a single map update.

Cache types to inspect:

1. **Instance caches:** `Map<PluginId, Plugin>` or `Map<String,Object>` holding objects directly.
2. **Class/reflection caches:** `Class<?>`, `Method`, `Field`, `Constructor<?>`, `MethodHandle`, JSON/DI metadata, or annotation scanners pointing to classes defined by the plugin loader.
3. **Factory/provider registries:** factories or `ServiceLoader.Provider<?>` holding provider classes or objects.
4. **Cache keys can retain too:** a `Map<Class<?>,Metadata>` holds the class in the key even if the value is a host structure; `Class<?>` links back to its defining loader.
5. **Values retaining keys in reverse:** switching a cache to `WeakHashMap` is not a silver bullet. If the value strongly references the key or class/loader, the reachability chain can still persist.
6. **Library caches:** serializers, dependency injection, logging, ORMs, reflection helpers, bean introspection, template engines, or framework event buses maintain internal caches. Check each library's official invalidation API instead of arbitrarily mutating internals via reflection.

A reliable strategy is scoping caches to **the plugin generation's lifetime** with a `close()/clear()` method invoked by the host when retiring the plugin. For process-wide caches, tag entries with plugin name + generation and delete them precisely on teardown. Avoid blindly calling `clear()` on a shared cache while other plugins are active.

### Identifying in a heap dump

A path like:

```text
HostRegistry.class (GC root / static field)
  -> registry.cache
  -> ConcurrentHashMap$Node.value
  -> demo.plugin.VersionAHandler
  -> java.lang.Class
  -> URLClassLoader(version A)
```

clearly points to **the host registry** as owner, not the garbage collector or Java class loader. Trace **who registered it**, whether a subscription/handle object exists, and which lifecycle step should have removed that entry.

## 5. ThreadLocal: must be cleaned on the exact thread owning the value

`ThreadLocal<T>` provides a separate value per thread. `ThreadLocal.remove()` clears the value **of the calling thread**, not values previously assigned on other threads. This is critical in systems using executor pools.

Anti-pattern:

```java
// Illustrative inside a Runnable executing on a pooled worker.
PLUGIN_CONTEXT.set(pluginRequest);
handleRequest();                   // may throw an exception
// Missing PLUGIN_CONTEXT.remove(): worker lives on, value stays retained.
```

Correct pattern:

```java
PLUGIN_CONTEXT.set(pluginRequest);
try {
    handleRequest();
} finally {
    PLUGIN_CONTEXT.remove();       // runs on the same pooled worker
}
```

Both snippets are **illustrative**, assuming `PLUGIN_CONTEXT` and `handleRequest` are declared in the host. When a thread pool reuses workers across requests, failing to call `remove()` can retain plugin objects far longer than the request lifecycle.

**Common trap:** After unloading a plugin, the management thread calls `PLUGIN_CONTEXT.remove()`. If a pooled worker had previously called `set(pluginObject)`, calling `remove()` on the management thread **does not remove the pooled worker's value**. Cleanup must execute on that exact worker, or the worker must terminate after completing work; for shared pools, use a per-task decorator/cleanup wrapper.

In common OpenJDK implementations, the internal `ThreadLocalMap` uses weak keys, yet values can remain held until stale entries are expunged. Do not assume garbage-collecting a `ThreadLocal` key guarantees immediate value release. That is an implementation detail, not an API guarantee to build upon; always call `remove()` proactively.

### InheritableThreadLocal is also worth checking

`InheritableThreadLocal` can propagate values from a parent thread to a newly spawned thread at thread-creation time (per child-value policy). If the value is a plugin instance or an object referencing the loader, a host thread created later may unexpectedly start with a reference to plugin A. Even after the parent thread cleans up, the child thread keeps its own value requiring cleanup. With thread pools, inheritance depends on when workers are created rather than per task submission; never rely on it as a safe default request context.

## 6. Threads, TCCL, and running tasks

Every `Thread` has a **thread context class loader (TCCL)**: read via `Thread.currentThread().getContextClassLoader()` and changed via `setContextClassLoader(...)`. Many frameworks and `ServiceLoader.load(service)` use TCCL to locate providers/resources. A plugin or host may temporarily attach the plugin's loader to a thread while running plugin-scoped code.

If code forgets to restore TCCL, a pooled worker surviving past plugin unload can keep retaining loader A:

```text
Host executor (lives across multiple plugin versions)
  -> worker Thread
  -> contextClassLoader = URLClassLoader(A)
  -> class loader A cannot be considered free of references
```

Correct TCCL swap pattern (illustrative code; `pluginLoader` and `runPluginTask` provided by caller):

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    current.setContextClassLoader(previous);
}
```

Use `try/finally` to guarantee restoration even if the plugin throws an exception. If the host itself started a task with an old plugin's TCCL left un-restored by an earlier run, capturing `previous` then and “restoring” it only reattaches the old loader. Enforce a **host baseline TCCL for workers** at worker creation or in executor management.

A thread can retain a plugin **without TCCL**:

- A plugin-defined `Thread.target`/`Runnable` retained by the thread during its execution lifecycle.
- Lambdas/closures or method references capturing plugin instances/classes.
- A thread actively executing a plugin method, whose stack frames and local variables reference plugin objects/classes.
- An `ExecutorService` queue holding `Runnable`, `FutureTask`, `ScheduledFuture`, or `CompletableFuture` instances with closures capturing the plugin.
- Plugin-spawned threads or `Timer`s, background pollers, file watchers, or schedulers not stopped on unload.
- Threads blocked indefinitely on I/O/locks or loops so shutdown flags fail to exit them.

Usually you must stop **accepting new work**, cancel/drain relevant tasks, signal shutdown, wait/join up to a timeout, and have a quarantine strategy if the plugin is uncooperative. Never use `Thread.stop()` (deprecated, unsafe) to force cleanup. Always clear task-owned `ThreadLocal`/TCCL on the exact worker and separate plugin-owned thread lifetimes from host-owned executors.

## 7. Callbacks, event buses, and subscriptions: listeners are strong references

A plugin may register callbacks with the host:

```java
// Illustrative anti-pattern, variables supplied by application:
eventBus.subscribe("ready", pluginCallback);
// When replacing the plugin, that exact callback/registration is forgotten.
```

If the event bus lives in the host and stores listeners in a strong collection, `pluginCallback` stays alive as long as the event bus. A plugin-created lambda or method reference like `instance::onEvent` also captures the plugin instance and retains the loader. Even if the callback is invoked rarely, **simply staying registered** creates a retaining reference.

Registration contracts should return a **registration handle**:

```java
// Ideal API pattern, not a standalone program:
AutoCloseable registration = eventBus.subscribe("ready", pluginCallback);
try {
    // Plugin is active.
} finally {
    registration.close(); // remove that exact old registration/instance
}
```

In real applications, ensure the handle's `close()` means unregistering without accidentally removing plugin B's subscribers. Maintain **a list of all registration handles per plugin generation** so teardown completes thoroughly even if the plugin loses track of original registration sites.

Retaining sources in the same callback family: `PropertyChangeListener`, UI listeners, `Flow.Subscription`, observers, MBean callbacks, JDBC driver registrations, event hooks, scheduled timer tasks, shutdown hooks, queue consumers, reactive stream subscriptions, HTTP/filter/interceptor registries, and cron-like schedulers. Each framework has its own unregister/cancel API.

**Teardown race:** Removing a listener does not necessarily abort an **already-executing** callback. Stop ingress, block new registrations, and wait for in-flight callbacks to finish before closing the loader/resources. An exception in one callback must also not prevent the host from cleaning up remaining registrations.

## 8. Standalone Java 17 program: observing all four retaining paths

The example consists of **two source files**. The plugin contains a `Runnable`; the host loads it with a dedicated `URLClassLoader`, then intentionally retains the callback in a cache, a listener list, and a host worker's `ThreadLocal`/TCCL. Afterwards, the host clears each reference and re-checks.

**What to understand upfront:** the program does **not** prove GC collected the loader. Inside `main`, local variables `pluginLoader`, `cls`, and `callback` remain in scope; thus right after cleanup other strong references may still exist. The demo intentionally **checks only the four created retaining sources**. Actual GC analysis is covered in Sections 10–11.

### 8.1. Directory layout

```text
loader-roots-demo/
  src/
    plugin/demo/plugin/GreetingCallback.java
    host/demo/app/LeakRootsDemo.java
  build/
    plugin/       (created by javac)
    host/         (created by javac)
```

**File `src/plugin/demo/plugin/GreetingCallback.java`:**

```java
package demo.plugin;

public final class GreetingCallback implements Runnable {
    @Override
    public void run() {
        System.out.println("plugin-callback=ready");
    }
}
```

The plugin uses the built-in `java.lang.Runnable` interface from the Java platform. The host needs no custom SPI here, keeping the example focused on reference retention.

**File `src/host/demo/app/LeakRootsDemo.java`:**

```java
package demo.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentHashMap;

public final class LeakRootsDemo {
    private static final Map<String, Object> CACHE =
            new ConcurrentHashMap<>();
    private static final List<Runnable> LISTENERS =
            new CopyOnWriteArrayList<>();
    private static final ThreadLocal<Object> REQUEST_CONTEXT =
            new ThreadLocal<>();

    private static String workerHolders(ExecutorService worker,
                                        ClassLoader pluginLoader)
            throws Exception {
        return worker.submit(() ->
                "tl=" + (REQUEST_CONTEXT.get() != null)
                + ",tccl=" + (Thread.currentThread()
                        .getContextClassLoader() == pluginLoader)).get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor(r ->
                new Thread(r, "host-worker"));
        try {
            ClassLoader previousTccl = worker.submit(() ->
                    Thread.currentThread().getContextClassLoader()).get();
            Path pluginDir = Path.of("build/plugin").toAbsolutePath();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] { pluginDir.toUri().toURL() },
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> cls = Class.forName(
                        "demo.plugin.GreetingCallback", true, pluginLoader);
                Runnable callback = cls.asSubclass(Runnable.class)
                        .getDeclaredConstructor().newInstance();
                CACHE.put("plugin", callback);
                LISTENERS.add(callback);
                worker.submit(() -> {
                    REQUEST_CONTEXT.set(callback);
                    Thread.currentThread()
                            .setContextClassLoader(pluginLoader);
                }).get();
                System.out.println("plugin-owned=" +
                        (cls.getClassLoader() == pluginLoader));
                System.out.println("cache-before=" + CACHE.size());
                System.out.println("listeners-before=" + LISTENERS.size());
                System.out.println("worker-before=" +
                        workerHolders(worker, pluginLoader));
                LISTENERS.forEach(Runnable::run);

                CACHE.remove("plugin");
                LISTENERS.remove(callback);
                worker.submit(() -> {
                    REQUEST_CONTEXT.remove();
                    Thread.currentThread().setContextClassLoader(previousTccl);
                }).get();
                System.out.println("cache-after=" + CACHE.size());
                System.out.println("listeners-after=" + LISTENERS.size());
                System.out.println("worker-after=" +
                        workerHolders(worker, pluginLoader));
            }
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
```

**Note:** the program is designed to illustrate the success path and print deterministic states. Removing cache/listeners and resetting TCCL/`ThreadLocal` here is not wrapped in separate `finally` blocks in case an earlier step fails; production teardown code must guarantee cleanup in `finally` even when callbacks/tasks throw exceptions (see Section 12). `worker.shutdownNow()` only sends interrupts to attempt stopping remaining tasks, with no guarantee that uncooperative plugin code exits immediately.

### 8.2. Compiling/running on Windows PowerShell

From `loader-roots-demo/`, with JDK 17 or newer:

```powershell
New-Item -ItemType Directory -Force -Path build/plugin,build/host | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/GreetingCallback.java
javac --release 17 -d build/host src/host/demo/app/LeakRootsDemo.java
java -cp build/host demo.app.LeakRootsDemo
```

### 8.3. Compiling/running on Linux/macOS

```bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin src/plugin/demo/plugin/GreetingCallback.java
javac --release 17 -d build/host src/host/demo/app/LeakRootsDemo.java
java -cp build/host demo.app.LeakRootsDemo
```

**Important:** do not add `build/plugin` to `java -cp`. If the host application loader finds `demo.plugin.GreetingCallback` on the classpath, `URLClassLoader` may delegate to an eligible parent and invalidate the defining-loader test. Here the parent is explicitly the platform class loader, while the plugin class is loaded from the child's URL; `Runnable` is a shared API provided by the JDK.

### 8.4. Exact stdout

```text
plugin-owned=true
cache-before=1
listeners-before=1
worker-before=tl=true,tccl=true
plugin-callback=ready
cache-after=0
listeners-after=0
worker-after=tl=false,tccl=false
```

The code was actually compiled with `javac --release 17` and run in a compatible JDK environment; stdout matches the lines above. It does not rely on GC timing or random scheduling order: every required worker operation is awaited via `Future.get()`.

## 9. Explaining the example: where are the references?

**Before cleanup:**

1. `plugin-owned=true`: `cls.getClassLoader() == pluginLoader`, proving the plugin implementation was defined by the child loader.
2. `CACHE.put("plugin", callback)` creates the path `host static Map → plugin instance → Class → pluginLoader`. Although the static Map is host-owned, the value is a plugin object.
3. `LISTENERS.add(callback)` creates an independent retaining path from the listener list. `LISTENERS.forEach(Runnable::run)` proves the callback is still invoked.
4. `REQUEST_CONTEXT.set(callback)` runs **on the host worker**. The thread pool does not terminate after the task, so the value can stay in the worker's `ThreadLocalMap`.
5. `setContextClassLoader(pluginLoader)` creates a **direct path** from the worker `Thread` to the loader. `workerHolders` runs subsequently on the same single-thread executor to inspect these two retaining sources.

**During cleanup:**

1. `CACHE.remove("plugin")` deletes the reference held by the cache.
2. `LISTENERS.remove(callback)` removes the exact registered listener.
3. Submits a task calling `REQUEST_CONTEXT.remove()` on **the exact worker that set the value**.
4. Restores the worker's TCCL to `previousTccl` recorded **before** attaching the plugin loader.
5. Waits on `Future.get()` before measuring `worker-after=tl=false,tccl=false`.
6. Exits `try-with-resources` to call `pluginLoader.close()`; shuts down the executor in the outermost `finally`.

**What cannot be concluded from stdout:** that the class loader was collected by GC, that all classes of the loader were unloaded, that metaspace shrank, or that the heap is clean in the real JVM. In the demo, local variables and closures alive for a period can still retain objects. Furthermore, the VM can defer class unloading even after all references are dropped; never write `weakRef.get() == null` assertions immediately after cleanup.

## 10. Finding loader-retaining paths via heap dumps and GC roots

In a long-running application, the most effective approach is analyzing **paths from GC roots to objects of the old plugin generation**. Prefer approved staging/incident environments since heap dumps can be large, cause pauses, and contain sensitive data.

### 10.1. Preparing a controlled reproduction test

1. Pick a plugin with a clear generation, e.g., `reporting/v41`. Record install/uninstall timestamps and loader identity, not just class names.
2. Start the host with a stable workload; create plugin A and invoke APIs so caches/callbacks/threadlocals are actually populated.
3. Replace with plugin B, invoke A's teardown, and ensure no valid requests are still using A.
4. Track old loader counts, class counts, metaspace, and registry sizes across multiple reloads; do not use a single snapshot as proof of a leak.
5. Capture heap dumps at controlled milestones and analyze references to **A**, avoiding confusion with currently active loader B.

### 10.2. Observation commands with JDK/HotSpot

Example terminal commands (substitute PID and paths appropriately):

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /path/to/plugin-retention.hprof
```

- `VM.classloader_stats` helps inspect class loaders and the number of classes attached to their loader data in some HotSpot JVMs. Command names, output details, and attach capability depend on vendor/JDK/policy.
- `GC.class_histogram` helps observe object counts by class; it does not replace retained-path analysis.
- Heap dumps require sufficient disk space and read permissions; they can pause the application and may trigger GC. Avoid collecting in sensitive environments without data-protection procedures.
- For Java 17 HotSpot with Unified Logging, tests can be launched with:

```bash
java -Xlog:class+load=info,class+unload=info -cp build/host demo.app.LeakRootsDemo
```

The logging command is a supplementary example for the demo; it generates JVM-determined log volume with **no fixed stdout**. Appearance of class unloading events is a positive signal; absence of events over a short interval does not prove a loader is leaked.

### 10.3. Eclipse MAT or equivalent heap analyzer

Recommended investigation steps:

1. Open the heap dump; find objects of type `java.net.URLClassLoader` or custom `PluginClassLoader` and identify the instance belonging to generation A. When multiple loaders share the same class, combine URLs/paths, identifiers, and references to identify the exact instance.
2. Select **Path to GC Roots** / **Shortest Path to GC Roots** and exclude paths going solely through weak/soft/phantom references if the tool offers that option.
3. Read the path from the root down to the loader or classes/instances defined by it. Do not stop at a `HashMap$Node` name; trace up to a modifiable field/registry/owner.
4. If the root is a **static field**, investigate the cache owner and specific key/value.
5. If the root is a **Thread**, inspect TCCL, `threadLocals`/`inheritableThreadLocals`, stack locals, `Runnable`/target, and task queues.
6. If the root is an **event bus** or subscriber registry, trace registration handles, listener lists, active callbacks, and unsubscribe mechanisms.
7. After fixing one path, capture another snapshot under similar conditions; the loader may have a second retaining path hidden during the first pass.

**Do not treat every visible “GC root” as an application-caused leak.** Paths from the host to the loader of **the active version** are normal. The problem is a **retired** loader generation still being retained after finishing its lifecycle and grace period.

## 11. WeakReference for observation, not absolute proof

One way to monitor whether the JVM *can* collect a loader after dropping strong references is keeping a weak reference:

```java
// Illustrative snippet, not a standalone program:
WeakReference<ClassLoader> monitor = new WeakReference<>(pluginLoader);
// Clear all strong references still held by host/plugin.
// After one or more GC cycles at an appropriate time:
boolean wasCollected = (monitor.get() == null);
```

`import java.lang.ref.WeakReference;` is required in programs using this snippet. **Do not** place `pluginLoader` in another static field or an overly long-lived local variable and wait for the weak reference to become null on its own. Even within the scope using `pluginLoader`, the JIT may treat the variable as live depending on circumstances; do not deduce GC behavior from a single trial.

Notes when writing tests:

- `monitor.get() != null` immediately after cleanup **does not prove a leak**: GC may not have run yet or the loader may not yet be eligible for unloading at that instant.
- `System.gc()` is a hint to the JVM, **not a guarantee** that GC runs, clears all references, or unloads classes immediately. Do not base strict pass/fail assertions on a single call.
- Test **specific retaining sources** by checking registries, TCCL, and `ThreadLocal` on the exact workers; then use heap dumps to find retained paths in retired generations.
- For time-based observation, `ReferenceQueue` can receive notifications when weak referents are cleared/enqueued under applicable semantics; it still does not replace verifying all owners tore down.
- A test measuring old class loader counts after 100 redeploy cycles is more useful than `sleep(100); assertNull(weak.get())`, yet it must also control GC/warmup/workload and avoid expecting collection by a hard deadline.

**Key distinction:** using a weak reference as a *probe* does not eliminate strong references in caches/threads/callbacks. If the graph still contains one strong retaining path, a weak reference will not force the JVM to ignore that path.

## 12. Exception-safe teardown pattern in production

Once retaining sources are identified, the runtime needs a teardown sequence that **executes even when one step fails**. A failure in callback A must not cause the host to skip cleaning up A's timers, `ThreadLocal`, or caches.

Recommended sequence:

1. Mark plugin generation A as **DRAINING**; block new requests/registrations to A, routing new requests to B.
2. Cancel/dispose A's subscriptions and scheduled tasks; prevent new callbacks from queuing.
3. Wait for in-flight callbacks/tasks to finish or terminate per timeout and quarantine policy; do not rush to close the JAR loader while code still needs to lazy-load classes/resources.
4. On workers that executed A's code, guarantee `ThreadLocal.remove()` and baseline TCCL restoration. With shared host executors, cleanup must run on each exact worker holding state; submitting a single task **does not guarantee** it reaches every worker in a multi-thread pool.
5. Delete the exact cache/registry entries, listener handles, DI scopes, reflection metadata, and references that **the host** holds to A.
6. Stop and join threads **created and owned by A**. For uncooperative threads, apply an isolation policy; do not assume `shutdownNow()` reliably kills them.
7. Close A's file watchers/streams/timers/`URLClassLoader`, then drop strong references held by the plugin manager/monitoring.
8. Re-measure paths from GC roots and monitor class unloading and memory across multiple replacement cycles.

For an individual task, here is an exception-resilient restoration pattern (illustrative snippet; variables depend on context):

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    PLUGIN_CONTEXT.set(pluginRequest);
    pluginCallback.run();
} finally {
    try {
        PLUGIN_CONTEXT.remove();
    } finally {
        Thread.currentThread().setContextClassLoader(previous);
    }
}
```

Nested `finally` blocks ensure TCCL restoration is still attempted even if `ThreadLocal` cleanup throws an unexpected exception. The code above only clears the thread-local value and TCCL **on the calling thread**; it does **not** automatically unregister `pluginCallback` from registries. Registry registrations require their own lifecycle, typically via `AutoCloseable` or an unsubscribe method.

For the plugin as a whole, the teardown manager should aggregate results across cleanup steps, report per-source errors, and still attempt remaining independent cleanup steps. Never catch an error and declare unloading successful if callbacks/threads actually remain alive.

## 13. Do not overlook indirect retaining sources

The four primary retaining sources often have variants:

### Reflection, proxies, and metadata

- Caches containing `Class<?>`, `Method`, `MethodHandle`, dynamic proxy classes, annotation proxies, or plugin record components.
- Class keys in metadata maps defined by a parent loader.
- Lambda implementations, method references, or `invokedynamic` call sites with closures/call targets tied to plugin instances.
- Logging/serializer/DI libraries retaining metadata or process-wide factories.

**Investigation:** filter classes defined by loader A and inspect reverse references. If the root is a library, use the library's official clear/close/unregister API rather than poking into internals with unsupported reflection.

### ServiceLoader and service registrations

`ServiceLoader` can cache provider instances/types. If the host keeps a `ServiceLoader` or provider longer than plugin A's lifecycle, it can continue holding provider classes/instances and the loader. Calling `ServiceLoader.reload()` clears internal caches to rediscover providers, yet does not drop references in other registries/variables; it is not a “full plugin unload” API. When replacing plugins, manage provider lifecycles and ownership explicitly.

### Drivers, shutdown hooks, JMX, native code

Some libraries/plugins register JDBC drivers, shutdown hooks, MBeans, JNI/global native references, or event callbacks in process-lifetime registries. Those registrations can retain instances or classes of loader A; teardown depends on the respective APIs. Do not wipe all system-wide entries if other drivers/plugins are still using them.

### Thread stacks and unfinished activity

A thread dump may show a worker still inside A's code; that is evidence of a running/waiting task, distinct from a stale `ThreadLocal` value left behind after a task ended. Stop legitimate tasks first; if class files/resources lazy-load during execution, closing the loader early can trigger spurious errors.

### Plugin-owned caches

A static field inside a class **defined solely by plugin loader A** does not automatically create a path from an independent GC root to A if the entire A graph is isolated and unreachable. Look for **links from host/JVM roots** into that graph. Conversely, a host static field holding a plugin object is a direct retaining path. Distinguish these two cases when reading a heap analyzer so you do not try to “fix a leak” merely by clearing static fields of already-unreachable classes.

## 14. Analyzing retained paths by root type

When a heap analyzer returns a path, cross-reference this table:

| Observed root/path | Grounded inference | Where to fix |
|---|---|---|
| `HostRegistry.staticCache → Map.Node.value → PluginHandler` | Host registry retains instance | Invalidate API keyed by plugin generation |
| `HostCache.classCache → Class<PluginType>` | Host retains class metadata | Cache eviction/clear scope |
| `Thread → contextClassLoader → PluginLoader` | Worker retains plugin TCCL | Restore baseline on the exact thread |
| `Thread → threadLocals → entry.value → PluginContext` | Pooled worker retains context | `remove()` on worker, typically in task `finally` |
| `Thread → target / stack / Runnable` | Plugin code/task still alive or queued | Stop/drain/cancel/join; inspect queues and futures |
| `EventBus → listeners → PluginListener` | Listener not unregistered | Keep subscription handle, remove specifically |
| `ScheduledThreadPoolExecutor → queue → plugin task` | Timer/task still pending | Cancel scheduled task, purge where appropriate |
| `ServiceLoader → provider instance/type` | Provider cache still held | Clean up owner of loader/provider; don't just call reload |
| `Host static → WeakHashMap value → PluginClass/loader` | Weak key failed to break strong chain | Redesign cache/value or lifecycle |
| `Class<?> / Method / MethodHandle of A` | Reflective metadata retains A's class | Clear reflection caches and retained callables |

**One shortest path does not mean it is the only path.** If removing `HostRegistry.staticCache` leaves the loader alive, re-run path-to-roots and check threads/callbacks/metadata; cleaning up the entire graph may require multiple component owners.

## 15. Recommended logging, instrumentation, and metrics

From the moment a plugin loads, the host should assign a distinct identity to **each generation**, not just the JAR filename:

```text
plugin-id=reporting
generation=9f7a-...           (deployment ID)
loader-type=PluginClassLoader
loader-identity=<identity hash + ID generation>
artifact=plugins/reporting-v41.jar
state=ACTIVE | DRAINING | RETIRED
```

The above is an **example log format**, not a Java API. `System.identityHashCode(loader)` helps distinguish instances at a point in time, yet is neither a durable process-wide ID nor a guaranteed-unique UUID; attach a host-generated generation ID as well.

Useful metrics:

- Count of generations in `ACTIVE`/`DRAINING`/`RETIRED` and time since retirement.
- Count of callbacks/listeners/timers/subscriptions still registered per generation.
- Count of cache entries holding references to generation A, and unfinished futures/tasks.
- Names and count of workers with TCCL pointing to loader A; count of workers/contexts holding `ThreadLocal` values belonging to A (measured via host-controlled instrumentation, not by probing JDK private fields).
- Metaspace usage, loaded class loader/class counts, and class unloading events via GC/JFR/Unified Logging when enabled.
- Heap dump retained sizes/traces when leaks occur, tagged with timestamp, workload, and generation ID.

Beware when computing “loader count”: not every class loader in the JVM is a plugin loader; the runtime, app servers, frameworks, or tool agents legitimately create loaders. Filter accurately by plugin class/identity and track trends across **multiple** identical replacement cycles.

## 16. Valuable regression tests

A test suite should separate **deterministic ownership assertions** from **GC observations**:

| Scenario | Predictable assertion | Observation-only part |
|---|---|---|
| Cache retains plugin A | Cache holds A's instance/class before cleanup | Loader A may still not be GC'd |
| Cache eviction | Entry A disappears from the proper owner's map | Do not force metaspace to shrink immediately |
| Pooled `ThreadLocal` | Task on that exact worker reads A's value before, null after `remove` | Do not assert weak ref cleared instantly |
| TCCL | Worker TCCL equals A before, baseline afterwards | GC still depends on other references |
| Listener registration | Registry contains A before, lacks A after unsubscribe | In-flight callbacks may still be running |
| Plugin-owned thread | Thread A stops/joins within a reasonable deadline | Class unload has no deterministic deadline |
| Plugin A → B → C | Retired A/B have zero registrations/caches | Loader count and metaspace trends across multiple GCs |
| Fault injection | Callback or cleanup throws yet independent steps still execute | Heap analysis used to locate leftover paths |
| Parallel reload | New requests hit B; no new tasks enter A; old tasks drain | Races depend on workload |
| Weak reference probe | No assertion requiring null at a fixed timestamp | Observed after appropriate GC cycles |

In particular, build a test where “plugin A intentionally creates all four roots → tear down A → each root is removed → plugin B continues operating.” Then inspect **retaining paths** in staging if old loader counts grow linearly across cycles. This test catches plugin replacement bugs far more directly than a vague assertion based on GC wait times.

## 17. Common mistakes

1. **“`URLClassLoader.close()` ran, so the classes are definitely unloaded.”** False: `close` only manages loader resources; GC roots govern reachability.
2. **“Removing the plugin from the main map is enough.”** Not necessarily: callback registries, threadlocals, queues, and TCCL are independent retaining paths.
3. **“Calling `ThreadLocal.remove()` on main cleans the pool.”** False: `remove` affects only the calling thread.
4. **“Once the `ThreadLocal` key becomes weak, the value vanishes immediately.”** Not guaranteed; stale entries in the implementation can hold values for a long time.
5. **“Daemon threads do not retain loaders.”** Daemon threads still have context loaders, stacks, targets, and `ThreadLocal`s; the daemon flag does not automatically drop references.
6. **“Stopping scheduling is enough.”** An already-running or queued callback/task can still retain the plugin.
7. **“Right after calling unsubscribe, nobody is invoking the listener anymore.”** In-flight callbacks and event bus consistency must be handled.
8. **“Making the cache a `WeakHashMap` guarantees zero leaks.”** Values can strongly reference keys or plugin classes.
9. **“Calling `System.gc()` once and counting loaders is enough.”** GC timing is not guaranteed, and a count snapshot does not identify the retaining path owner.
10. **“Caches inside plugin classes are definitely the culprit.”** You must check whether a path exists from a GC root into the plugin's graph.
11. **“Reassigning the host's `loader` variable from A to B is enough.”** Other threads/registrations/caches may still hold A.
12. **“Close the loader as soon as draining starts.”** Old tasks may need to lazy-load dependencies; wait for the proper lifecycle stage.
13. **“Clear every callback on the event bus to be safe.”** Dangerous for other plugins; remove strictly by registration/generation.
14. **“Logging only class names identifies the loader.”** Two generations can have classes with identical binary names yet different defining loaders.
15. **“`WeakReference.get() != null` proves a memory leak.”** GC may simply not have occurred yet; inspect retaining paths and lifecycle.
16. **“Monitoring Metaspace alone is enough.”** Heap callbacks/threadlocal values, file handles, and native resources also need monitoring.

## 18. Concise runbook for handling a real incident

When memory becomes unstable after multiple plugin upgrades:

1. **Isolate** the exact `RETIRED` plugin generation and collect the old class loader's identity.
2. **Check obvious owners:** host caches, listener registries, schedulers/futures, worker `ThreadLocal`/TCCL, and plugin-owned threads. Assert by generation.
3. **Capture controlled snapshots:** `jcmd VM.classloader_stats`, GC/class-unload logs, and heap dumps when needed.
4. **Read Path to GC Roots:** find strong references from roots to the loader or plugin classes/instances; record the root owner and registration site.
5. **Fix at the lifecycle owner:** evict the right cache, unsubscribe the right callback, `remove()` on the right worker, restore TCCL, stop/join threads/tasks.
6. **Re-verify:** specific roots disappear; zero requests enter old generations; monitor retaining paths and classloader/metaspace trends across A→B→C cycles.
7. **Codify teardown in the plugin contract:** registration handles, managed worker scopes, generation-scoped caches, and exception-safe cleanup so the incident does not recur.

**Remember:** an old class loader is not released merely because a `pluginLoader` variable was reassigned to a new version or `URLClassLoader.close()` ran. You must sever **all strong reference paths still reachable from GC roots** — especially host caches, `ThreadLocal` on long-lived workers, TCCL/threads, and callback registrations — and then let the JVM decide when class unloading occurs. Diagnose via **retaining paths**, fix by **ownership/lifecycle**, and verify using both deterministic assertions and controlled GC observations.

**Standard Java 17 documentation:** [ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html), [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html), [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html), [Java 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/), and [Java Command / Unified Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).