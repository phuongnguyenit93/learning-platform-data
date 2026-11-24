# Conditions for Class Reclamation and Limits of GC Guarantees

## 1. Why replacing a plugin does not mean unloading classes

In a Java application supporting plugins, each load of a plugin version can create additional class loaders, classes, and corresponding metadata in the JVM. When updating a plugin, the host typically routes new requests to the new version and closes the old version. However, calling \`close()\`, deleting the JAR, or removing an entry from a registry **does not mean the old classes are immediately reclaimed by the JVM**.

Three actions must be distinguished:

1. **Stopping logical usage**: issuing no new requests to the old plugin; completing or cancelling in-flight tasks.
2. **Releasing application resources**: closing sockets, executors, files, listeners, timers, connection pools, and anything owned by the plugin.
3. **Class unloading**: the JVM can discard metadata of classes that are no longer needed once they and their associated class loader become eligible for reclamation.

The third step depends on reachability across the entire object graph and the garbage collector's decisions, not solely on code calling \`close()\`.

In a long-running plugin system, if old loaders stay retained via threads, callbacks, caches, or registries, repeated hot reloads can steadily grow class metadata memory and eventually lead to Metaspace pressure.

## 2. Class identity and class loaders in plugin replacement

In the JVM, a type is identified by the pair **(binary name, defining class loader)**. Thus two plugin versions that both declare \`com.example.plugin.ReportPlugin\`, yet are defined by two different loaders, are still two distinct classes.

\`\`\`text
Host/API Loader
      |
      +-- PluginLoader V1 --> ReportPlugin V1
      |
      +-- PluginLoader V2 --> ReportPlugin V2
\`\`\`

When V2 is published, V1 does not vanish automatically. If a V1 object remains retained by some part of the host, defining loader V1 can remain reachable and the classes defined by that loader are not yet eligible for unloading.

Conversely, a plugin using **a shared application class loader** cannot independently unload plugin classes as if “delete the JAR and the classes disappear.” Classes defined by a shared loader typically live for the lifetime of that loader. This is one reason class loader boundaries must be designed **before** implementing hot reload.

A dedicated class loader helps organize code and can create the opportunity to unload by loader lifetime, yet it is **not a security sandbox** for untrusted code.

## 3. Conditions for a class to be unloadable

Pragmatically: for classes defined by a reclaimable class loader, the JVM can unload them only when no live state requires keeping those classes and that loader alive.

Retaining sources can include:

- Instances of plugin classes still reachable from a JVM root.
- Retained \`Class<?>\`, \`Method\`, \`Field\`, \`Constructor\`, method handle, or proxy objects associated with the plugin/class.
- Static fields and relationships among classes, instances, and loaders in the object graph.
- Threads executing plugin code; stack frames and variables still using plugin objects/classes.
- Live threads whose **thread context class loader (TCCL)** points to the plugin loader.
- \`ThreadLocal\` values on worker threads holding plugin instances, callbacks, or class loaders.
- Listeners, subscribers, scheduled tasks, executors, timers, caches, DI containers, or host singletons retaining plugin objects.
- Another class loader holding references to the plugin loader, its classes, instances, or resources.
- JNI/native code or framework mechanisms holding global references and related state.

Actual reclamation conditions are more complex than a simple reference-counting rule. The JVM may retain metadata, JIT optimizations, and internal class-loader data structures according to its implementation; unload timing is affected by the garbage collector and safepoints/GC cycles. There is no standard command guaranteeing “unload exact class X right now.”

A useful architectural invariant:

> Once the old plugin stops serving and completes cleanup, **the host holds no strong references** to that plugin version's loader, classes, or private instances.

This invariant does not guarantee when the JVM performs unloading, but it is the core design precondition for unloading to have a chance of occurring.

## 4. Reachability: why one small reference can keep an entire loader alive

Consider an example:

\`\`\`text
GC Root
   |
   v
Host singleton
   |
   v
List<Runnable> callbacks
   |
   v
Plugin callback instance
   |
   v
Plugin implementation class
   |
   v
Plugin defining ClassLoader
\`\`\`

Even after \`activePlugins.remove("old")\`, the reference path from the singleton through the callback still exists. Loader V1 stays alive.

Another example:

\`\`\`text
Worker Thread (reused by host)
   |
   +--> Thread.contextClassLoader --> PluginLoader V1
   |
   +--> ThreadLocalMap --> PluginRequestContext V1
\`\`\`

If the host ever set TCCL or a \`ThreadLocal\` for V1 and failed to restore it in \`finally\`, the loader can remain alive as long as the worker thread exists.

**Do not look only for direct references to \`ClassLoader\`.** An ordinary plugin object held by the host inside an event bus can be enough to prevent unloading.

## 5. Properly ordered plugin replacement workflow

A hot-reload lifecycle can be structured as:

\`\`\`text
Plugin V1 is ACTIVE
         |
         v
Prepare / validate / start V2
         |
         v
Publish V2 registry snapshot
         |
         v
Stop issuing new leases to V1
         |
         v
Wait for running V1 requests / callbacks to finish
         |
         v
Cancel subscriptions, tasks, timers; close V1 resources
         |
         v
Remove references to V1 from host registries and caches
         |
         v
Close class loader if close is supported
         |
         v
Is V1 eligible for GC? (only if no retaining paths remain)
         |
         v
The JVM may reclaim the loader and class metadata later
\`\`\`

When using \`URLClassLoader\`, \`close()\` releases opened JAR/URL resources per its contract and blocks loading new resources/classes under the corresponding rules; **it does not force unloading already-defined classes**.

Clarify who owns resources: a plugin instance shared across multiple snapshots cannot be arbitrarily closed when only one snapshot stops using it. A lease/ref-count or a properly synchronized draining protocol can prevent “closing while a reader is still calling.”

When unloading is uncertain, the application must still maintain correctness: the new registry must not route requests to the old plugin; if the old plugin has not yet been reclaimed, that is a resource issue to monitor and address separately.

## 6. Java 17+ example: observing a class loader reclaimed by GC

To test the **no remaining strong references** principle, a \`WeakReference\` can track a class loader. The program below intentionally **does not depend on a guaranteed GC event**, because GC is allowed not to run or not to reclaim immediately.

Create file **\`LoaderGcDemo.java\`**:

\`\`\`java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;

public class LoaderGcDemo {
    private static WeakReference<ClassLoader> makeLoader() throws Exception {
        // No JAR needed: the goal is to observe loader lifetime.
        URLClassLoader loader = new URLClassLoader(
                new URL[0],
                LoaderGcDemo.class.getClassLoader()
        );
        WeakReference<ClassLoader> weak = new WeakReference<>(loader);

        loader.close();  // Close loader resources; does not force GC/unload.
        return weak;     // After returning, do not hold a strong ref.
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> weak = makeLoader();
        System.out.println("weak reference created: true");

        for (int i = 0; i < 5 && weak.get() != null; i++) {
            System.gc(); // Merely a hint; the JVM has no obligation to comply.
            Thread.sleep(100);
        }

        System.out.println("loader collected: " + (weak.get() == null));
    }
}
\`\`\`

Run:

\`\`\`bash
javac LoaderGcDemo.java
java LoaderGcDemo
\`\`\`

The first line is always:

\`\`\`text
weak reference created: true
\`\`\`

The last line may be **\`loader collected: true\` or \`loader collected: false\`** depending on the JVM, GC, timing, and launch options. Do not write unit tests requiring the result to be \`true\` within a fixed deadline.

This example demonstrates tracking *loader reachability* via a weak reference, **without directly proving a specific class was unloaded**, because the sample loader defines no plugin classes. To observe real class unloading, create a loader that loads a class from a plugin JAR, drop all strong references, and combine with JVM class-unload logging or profiling.

## 7. WeakReference, ReferenceQueue, and verification limits

\`WeakReference<ClassLoader>\` is often useful in tests/diagnostics:

\`\`\`java
WeakReference<ClassLoader> oldLoader =
        new WeakReference<>(pluginLoader);
\`\`\`

After dropping all strong references, \`oldLoader.get()\` **may** become \`null\` when GC processes the object. If the object remains strongly reachable, the weak reference will not be cleared by a normal GC evaluating that reachability.

\`ReferenceQueue\` can signal when a weak reference is enqueued, yet still has no standard notification deadline. \`PhantomReference\` can also help track a reference lifecycle phase; neither means the JVM provides a deterministic “class unload complete” callback.

Limitations to keep in mind:

- A weak reference tracks only the object it points to, not directly confirming all associated class metadata has been freed.
- \`System.gc()\` is a hint to the JVM, not an enforceable command. The JVM may disable explicit GC or decline to run a full collection.
- JIT and local-variable lifetime optimizations can cause experimental results to vary even with identical source code.
- GC logs and heap/metaspace metrics are influenced by runtime, workload, and reallocation policies.
- **Whether Metaspace usage drops immediately or not** is not sole proof of class unloading; the JVM can retain committed memory regions for reuse.

Therefore combine multiple tools rather than relying on a single GC test.

## 8. Using JVM logs and diagnostic tools

On modern HotSpot/JDK builds, Unified Logging can observe loading/unloading:

\`\`\`bash
java -Xlog:class+load=info,class+unload=info -jar host.jar
\`\`\`

Logs will be verbose; in production limit log levels and destinations appropriately to avoid I/O pressure or exposing paths. Unload events appear only when the JVM actually unloads classes; absence of events over a short window does not by itself prove a leak.

Useful tools:

- **JFR (Java Flight Recorder)**: tracks class loading, allocations, GC, and runtime activity depending on enabled events.
- **\`jcmd <pid> VM.classloader_stats\`** on supporting HotSpot versions: summarizes class loaders and metadata, helpful for seeing whether multiple old-version loaders persist.
- **\`jcmd <pid> GC.class_histogram\`**, heap dumps, and memory analyzers: find objects still retaining plugin instances/class loaders. Some commands trigger stop-the-world pauses or overhead; choose timing carefully.
- **Metaspace metrics** (via JMX/\`MemoryPoolMXBean\`, JFR, or monitoring): observe trends across repeated hot reloads.

To investigate leaks, capture a heap dump and follow **paths to GC roots** from the plugin loader or instance. Verify the path consists of real strong references; soft/weak/phantom references have different semantics.

## 9. Common leak sources in a plugin host

### 9.1 Unstopped threads

A plugin spawns threads/executors and forgets to shut them down. Running threads hold stacks/contexts or plugin runnables, keeping the class loader alive.

Solution: threads/executors must have a clear owner; \`shutdown()\`/\`shutdownNow()\` per policy, await termination with a timeout, and alert if they fail to stop.

### 9.2 Thread context class loader not restored

\`\`\`java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    invokePlugin();
} finally {
    t.setContextClassLoader(previous);
}
\`\`\`

This is an integration snippet; restore TCCL even when invocation throws. Never leave a plugin loader permanently attached to a thread pool.

### 9.3 ThreadLocal and MDC

Host worker threads outlive plugins; a \`ThreadLocal\` holding a plugin instance can retain the old object graph. Clear or restore it in \`finally\` on the exact thread where it was set. Calling \`remove()\` from another thread does not clear the worker thread's value.

### 9.4 Listeners/subscriptions and callbacks

Event buses, schedulers, metrics registries, JMX MBeans, shutdown hooks, or DI scopes can retain callbacks/plugin classes. Use registration handles and \`unsubscribe()\`/\`close()\` during \`stop()\`.

### 9.5 Static caches or host singletons

Caches holding \`Class<?>\`, reflective \`Method\`s, method handles, lambdas, dynamic proxies, or serialized metadata pointing to plugin classes. Evict caches by \`pluginId\` and version; never use \`ClassLoader\` as a key in an unbounded global map without eviction.

### 9.6 Native/JNI and external libraries

JNI global references, native threads, logging bridges, or framework caches can retain classes/plugin loaders. Some libraries do not support clean unloading inside the same JVM. When reliable reclamation is required, consider isolating plugins in separate processes.

## 10. Situations where unloading is not guaranteed

Some limitations are architectural or runtime-inherent:

- **No unloading by class name:** Java provides no \`unloadClass("...")\` API.
- **Classes inside a still-living loader:** you cannot expect the JVM to independently reclaim an arbitrary class while its loader remains in use merely because the host stopped calling that class.
- **Shared class loader:** you cannot unload an individual plugin like a module class loader if everything was loaded together into the application loader.
- **No deterministic GC deadline:** even once objects become unreachable, GC/unload timing remains up to the JVM.
- **Close does not force unloading:** \`URLClassLoader.close()\`, \`JShell.close()\`, \`ModuleLayer\`, or removing from a registry are not immediate unload commands.
- **Class/static/stack/native references:** runtime links can continue keeping definitions needed.
- **JPMS layers have no unload command:** the layer, loaders, and all their references must become unreachable; creating a new layer does not automatically reclaim the old layer.

Different collectors/JVMs may use different unloading strategies; verify on the exact target JDK, GC, and production configuration rather than promising results based on a developer machine.

## 11. What can be guaranteed at the application level?

Instead of promising “V1 classes will unload within 500 ms,” define **guarantees the host itself controls**:

1. After V2's publish point, new requests never select V1.
2. Never call V1's \`stop/close\` while V1 leases/in-flight requests remain.
3. When V1 stops, all subscriptions/tasks/resources it owns are cleaned up or clearly flagged on failure.
4. Host registries and caches retain no strong references to V1.
5. Host retains no V1 TCCL/\`ThreadLocal\`/plugin objects beyond scope.
6. Cap the number of coexisting plugin/loader versions and define a policy when cleanup fails.
7. Emit metrics, logs, and alerts if loader/metaspace counts fail to stabilize across reload cycles.

These practices **increase the likelihood** that loaders/classes become eligible for reclamation, without dictating GC timing or how much memory is returned to the OS.

If business requirements demand guaranteed resource reclamation after a hard deadline, **isolating plugins in separate OS processes** usually provides a far stronger resource-termination boundary than relying on class unloading inside a shared JVM. Process termination must still follow graceful shutdown policies and time bounds.

## 12. Testing hot reload and class unloading

An integration test should:

1. Load V1 through a dedicated loader and record a weak reference to that loader.
2. Register V1 and run several real invocations.
3. Prepare V2 and switch new requests to V2 via an atomic snapshot.
4. Drain V1, cancel callbacks, close executors/resources, and drop every strong reference held by the test/host.
5. Hint GC or wait within reasonable test bounds, **never making guaranteed GC within a short deadline a correctness assertion**.
6. Assert V1 is absent from the active registry and zero in-flight leases remain.
7. Use JFR/logs/heap dumps to diagnose if repeated reload cycles show a trend of retaining old loaders.

Rigorous testing should also cover failure cases: unremoved callbacks, hung threads, \`close()\` throwing errors, long-running requests, V2 → V1 rollback, and plugins with native libraries. Observing loader counts per version across hundreds of reload cycles is more informative than running once and calling \`System.gc()\`.

## 13. Common mistakes

- Assuming \`URLClassLoader.close()\` immediately unloads loaded classes.
- Deleting a JAR on disk and concluding plugin code vanished from the JVM.
- Removing a plugin from one map while forgetting event listeners and executors.
- Using static caches storing plugin \`Class\` or method handles indefinitely.
- Forgetting to restore TCCL/\`ThreadLocal\` after callbacks.
- Closing the old plugin before old requests finish.
- Keeping \`ModuleLayer\`, \`ServiceLoader\`, or \`CompiledScript\` of older versions in caches without eviction.
- Expecting \`System.gc()\` to make a class-unloading unit test deterministic.
- Treating instantaneous Metaspace usage as sole proof of a leak.
- Failing to distinguish class loader leaks from resource leaks or heap leaks.
- Over-trusting class loader isolation as a sandbox for untrusted code.

## 14. Checklist before deploying plugin replacement

- Does each plugin version have its own loader/layer if lifecycle-based unloading is a goal?
- Is the shared API defined in a stable parent loader to avoid class identity conflicts?
- Is plugin V2 initialized/validated before shifting requests?
- Does the registry snapshot ensure new requests never select V1?
- Are draining and lease management in place before closing V1?
- Have executors, threads, callbacks, timers, listeners, caches, JNI references, and TCCL/\`ThreadLocal\` been cleaned up?
- Are all strong references from the host to V1 dropped on retirement?
- Is \`close()\` called on appropriate resources without confusing it with GC?
- Are coexisting version limits and Metaspace/loader growth alerts configured?
- Do testing and operations have tools to observe class unloading on the target JVM?

**Remember:** for old classes/plugins to become reclaimable, first **sever all strong reference paths and execution keeping the old class loader alive**, then let the JVM decide when garbage collection and class unloading occur. **Eligibility for reclamation does not mean immediate reclamation or a guaranteed deadline.**