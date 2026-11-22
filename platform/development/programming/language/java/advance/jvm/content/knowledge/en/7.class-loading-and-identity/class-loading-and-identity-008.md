# When a class can be unloaded and its relation to the class loader lifecycle

## 1. What is class unloading?

The JVM **loads** a class or interface when a runtime type representation is needed. It retains information about the type, methods, fields, constant pool, and internal structures for linking, verification, and execution. **Class unloading** is the process by which the JVM can reclaim a runtime type definition that is no longer needed along with its associated metadata resources according to memory management policies.

Class unloading is **not synonymous** with:

- **Object garbage collection:** collecting instances of a class. There may be no instances left, yet the class remains alive because its class loader is still alive.
- **Closing a class loader:** `URLClassLoader.close()` closes the resources managed by the loader; it does not force the JVM to unload the classes it has defined.
- **Deleting a JAR or `.class` file on disk:** does not immediately remove the loaded runtime class.
- **Setting a reference to `null`:** only changes one reference; it does not guarantee that all reference paths to the loader are gone.
- **Re-running the static initializer:** an unloaded class and a newly defined class in a new loader are two different runtime classes, not the old class's `<clinit>` being "reset".

According to **JVMS §5.3**, for **normal named classes/interfaces**, a class/interface may be unloaded **if and only if its defining class loader may be reclaimed by the garbage collector**. This is an eligibility condition, **not a guarantee of execution timing**. The JVM, garbage collector, and configuration determine when collection/unloading occurs, or whether it occurs at all while the program is running.

> **Key point:** releasing plugin objects is only part of the work. To give named classes defined by a plugin loader a chance to unload, the **defining class loader** and all objects retaining that loader must have no strong reference paths from GC roots.

There is an exception to understand when studying advanced JVM internals: **hidden classes** defined through special APIs may use different reachability mechanisms; do not apply the named-class/plugin-loader rule verbatim to every dynamically generated JVM class.

## 2. Class identity is tied to the defining loader

For a named class/interface, having the same **binary name** is not enough to conclude it is the same JVM type; the **defining class loader** also contributes to determining runtime identity.

~~~text
URLClassLoader A
    └── define demo.plugin.Greeter ──> Class A

URLClassLoader B
    └── define demo.plugin.Greeter ──> Class B

Same name, different defining loaders:
Class A != Class B.
~~~

This has practical consequences:

- The two classes have separate `Class<?>` objects, separate class metadata, and separate **static fields**.
- Each class has its own **initialization** lifecycle: the static initializer can run once for A and once for B.
- A `Greeter` object from A is not automatically an instance of B's `Greeter`. Cross-casting can throw `ClassCastException`, even if the printed class names look identical.
- For a class defined by a parent loader where a child loader merely delegates (delegation), the child loader does not create a new class identity.

It is necessary to distinguish the **initiating loader** (the loader that requests/initiates loading) from the **defining loader** (the loader that actually defines the class). Parent-first delegation usually checks the parent first. If the parent has already defined the class, a call to `child.loadClass(name)` may receive the parent's class. **Do not infer identity from the initial loader that the code calls**; observe the defining loader using `type.getClassLoader()`.

Runtime packages and access rules are also affected by the loader. Two classes with the same package name string but different defining loaders do not automatically belong to the same runtime package for package-private access.

## 3. Plugin loader lifecycle: separating active steps and GC

A typical plugin/hot-reload system has two lifecycle parts:

~~~text
Part the application can control:

[Create version v1 plugin loader]
      |
[Load / link / initialize classes as needed]
      |
[Run plugin: requests, jobs, listeners]
      |
[Stop accepting new work / draining]
      |
[Unregister, stop threads, close I/O]
      |
[Close URLClassLoader, drop host references]
      v

Part decided by JVM/GC:

[Loader is no longer reachable from GC roots]
      |
[Eligible for collection and class unloading]
      |
[GC executes when appropriate]
      |
[Class metadata may be reclaimed]
~~~

**There is no standard Java API `Class.unload()`** for normal named classes. The application manages resources and ownership; unloading happens afterward **if** runtime conditions and policies allow.

You should not design a `stopPlugin()` API that returns with a promise that "all classes belonging to the plugin version have been unloaded by the JVM". A more reasonable promise is: the plugin has stopped processing work, cleaned up registrations/resources owned by the system, and removed strong references that the host can control.

### Loading, linking, initialization, and unloading are not a single state

| Phase | What the JVM does | What must not be inferred |
| --- | --- | --- |
| Loading | Find binary representation, create runtime class/interface | Static initializer has already run |
| Linking | Verification, preparation, resolution per JVM rules | Every symbolic reference is always resolved all at once |
| Initialization | Execute `<clinit>` logic when required | An instance has been created |
| Usage | Create objects, run methods, reflection, tasks... | The class is automatically unloaded when a method finishes |
| Eligible for unloading | Defining loader no longer needs to be kept alive (normal named classes) | The JVM has unloaded it immediately |
| Actual unloading | JVM reclaims corresponding class metadata | JAR files or application resources have closed themselves |

For example, a utility class with only static methods can be initialized and used many times without ever having an instance. Conversely, collecting all instances does not force the class to unload.

## 4. Why does a loader stay alive? GC roots and reachability

GC does not work by "counting how many references are in a cycle". It finds objects that are still reachable via **strong references** from roots such as thread stacks, certain static references, native/JNI handles, and relevant runtime structures.

Ask about plugin v1:

1. Does the host still hold the `ClassLoader` in a `Map`, registry, or field?
2. Are there **plugin instances** in a host cache, listener, message queue, scheduler, or callback?
3. Are there `Class<?>`, `Method`, `Field`, `Constructor`, `MethodHandle`, proxy, lambda, or framework caches holding plugin classes?
4. Is there a thread running plugin code or an executor that has not been shut down, or are there queued `Runnable`/`Callable` tasks created from plugin classes?
5. Is there a long-lived host thread whose **thread context class loader (TCCL)** still points to the plugin loader?
6. Are there `ThreadLocal` values on a thread pool or request context that were not cleared?
7. Are there MBeans, drivers, logging handlers, event bus listeners, shutdown hooks, resource managers, or native global refs that were not unregistered?
8. Is there a framework/module layer or custom parent loader holding a reference to the child loader?

These are **places to measure retaining paths**, not an assertion that every API just listed will definitely leak in every situation.

### Example of a retaining path

~~~text
GC ROOT: host worker thread
       |
       +── contextClassLoader
                   |
                   v
             PluginLoader v1
                   |
                   +── define PluginClass / Helpers / ...
~~~

Even if the UI already reports "plugin stopped", a host thread may still hold v1 via `contextClassLoader`. Removing that path along with other strong paths allows the loader to become unreachable.

### A pure cycle is not a leak

~~~text
PluginLoader -> PluginClass -> PluginSingleton
     ^                             |
     +-----------------------------+
~~~

If the object cluster above **has no path from a GC root**, tracing GC can reclaim that cycle. Therefore, do not conclude that because a class static field points to the loader, the loader can never be unloaded; **the actual root path** is what matters.

Conversely, a **host static cache** in a class defined by the long-lived application loader can be a root path:

~~~text
HostRegistry.staticMap
        |
        v
   PluginObject
        |
        v
  Runtime Class
        |
        v
  Defining Loader v1
~~~

Setting a local variable `plugin = null` while forgetting `HostRegistry.staticMap.remove(key)` does not resolve this retaining path.

## 5. "Eligible for unloading" and "unloaded" are not synonymous

| Observation | Valid conclusion |
| --- | --- |
| No direct Plugin instances remain | **Not enough**; the loader/class may still be reachable |
| `plugin = null` | Only removes one reference; many other references may remain |
| `loader = null` | Unknown what other root paths are holding the loader |
| `URLClassLoader.close()` returns | Resources handled per `close` contract; **does not confirm unloading** |
| `System.gc()` is called | JVM receives a GC request/hint; **no deadline or guarantee of unloading** |
| `WeakReference<ClassLoader>.get() == null` | The loader tracked by the weak reference has been cleared by GC; this is a clear signal of reachability at the time of observation |
| HotSpot log `class+unload` records event for class X | There is evidence the JVM unloaded X in that run |
| `Metaspace committed` has not decreased | **Not enough** to say classes were not unloaded; the JVM may keep capacity for reuse |
| `Metaspace used` increases | Does not by itself prove a leak; more new classes may have been loaded or workload increased |

`System.gc()` can also be disabled or implemented differently depending on VM flags/collector. Do not write tests like "call GC three times and then all v1 classes must unload".

**Classes defined by the bootstrap, platform, or long-lived application loader** usually have lifecycles matching the JVM or application. They are not a mechanism for arbitrarily unloading individual features. If a normal loader stays alive, there is no API to "unload a specific named class it defined" like removing an entry from a map.

## 6. Standalone Java 17 example: same name, two class loaders

The following example illustrates **two separate runtime classes** and the `close()` behavior of loaders without **claiming that class unloading will happen** immediately. Create two source files in two different directory trees.

### 6.1. Plugin file: `plugin-src/demo/plugin/Greeter.java`

~~~java
package demo.plugin;

public class Greeter {
    static {
        System.out.println("PLUGIN_INIT");
    }

    public String hello() {
        return "HELLO";
    }
}
~~~

### 6.2. Host file: `app-src/LoaderCycleDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderCycleDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderCycleDemo plugin-out");
        }

        URL root = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] { root },
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[] { root },
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> typeA = Class.forName(
                    "demo.plugin.Greeter", true, first);
            Class<?> typeB = Class.forName(
                    "demo.plugin.Greeter", true, second);

            System.out.println("SAME_NAME=" +
                    typeA.getName().equals(typeB.getName()));
            System.out.println("SAME_CLASS=" + (typeA == typeB));
            System.out.println("SAME_LOADER=" +
                    (typeA.getClassLoader() == typeB.getClassLoader()));

            Object objectA = typeA.getConstructor().newInstance();
            System.out.println("HELLO=" +
                    typeA.getMethod("hello").invoke(objectA));

            try {
                typeB.cast(objectA);
                System.out.println("CROSS_CAST=OK");
            } catch (ClassCastException expected) {
                System.out.println("CROSS_CAST=FAIL");
            }
        }

        System.out.println("LOADERS_CLOSED");
    }
}
~~~

Here **the host does not import `demo.plugin.Greeter`**: the host only uses reflection and the binary name. The parent is set to the **platform class loader**, so the two `URLClassLoader` instances load the plugin class from the same directory and each loader defines `Greeter` itself. Do not add `plugin-out` to the host's `java -cp`.

### 6.3. Compile and run

From the directory containing `plugin-src` and `app-src`:

~~~bash
javac --release 17 -d plugin-out plugin-src/demo/plugin/Greeter.java
javac --release 17 -d app-out app-src/LoaderCycleDemo.java
java -cp app-out LoaderCycleDemo plugin-out
~~~

**Deterministic stdout from the program:**

~~~text
PLUGIN_INIT
PLUGIN_INIT
SAME_NAME=true
SAME_CLASS=false
SAME_LOADER=false
HELLO=HELLO
CROSS_CAST=FAIL
LOADERS_CLOSED
~~~

Explanation:

1. `Class.forName("demo.plugin.Greeter", true, first)` loads and **initializes** the class defined by loader `first`, printing `PLUGIN_INIT` the first time.
2. The call with `second` creates another runtime class with the same binary name, printing `PLUGIN_INIT` the second time.
3. `typeA.getName().equals(typeB.getName())` is true, but `typeA == typeB` is false because the defining loaders differ. The loader objects are also different.
4. Reflection invokes `hello()` on the instance of typeA successfully.
5. `typeB.cast(objectA)` fails: the object of typeA is not an instance of typeB.
6. `try-with-resources` calls `close()` on both URLClassLoaders and prints `LOADERS_CLOSED` afterward. **This line does not claim that the classes or loaders have been GC'd/unloaded.**

The example is deterministic regarding identity and dispatch under standard Java 17+ conditions. It does **not** depend on GC cycles, heap size, or JIT timing for its output. With a custom JVM agent/instrumentation, the environment may have additional effects outside this exercise.

## 7. Closing a loader is not closing a plugin and is not unloading

`URLClassLoader.close()` releases open resources managed by the loader, such as `JarFile` instances per the API contract. Importantly:

- **Already defined** classes do not disappear just because of `close()`.
- Running methods from plugin classes are not automatically interrupted by the JVM.
- Already created objects can still exist and use the loaded classes.
- A closed loader object can still be kept alive by a host map, thread, or reflection cache.
- After closing, the loader is no longer expected to load new classes/resources in the old way; the application should not continue using it as an active loader.
- GC and class unloading may happen later or not happen before the process exits.

Therefore, you should design three separate lifecycle layers:

~~~text
Business lifecycle:
   stop job -> unregister -> complete requests -> close resources

Class loader lifecycle:
   create loader -> define classes -> serve -> close loader ->
   drop host-owned references

JVM memory lifecycle:
   GC analyzes reachability -> eligible -> may unload ->
   metadata may be reclaimed / reused
~~~

Do not wait for unloading to close a `Socket`, transaction, logging handler, thread pool, or file: Java does not provide a reliable class destructor to do this automatically.

## 8. Use WeakReference to observe, not to force unloading

`WeakReference<ClassLoader>` can help observe whether a loader has been processed by GC. However, using a weak reference itself does not cause classes to unload on schedule.

~~~java
import java.lang.ref.WeakReference;

// Illustrative snippet: makeLoaderAndReleaseStrongRefs()
// must be written so it does not return a strong reference
// and must stop/close all plugin resources.
WeakReference<ClassLoader> probe = makeLoaderAndReleaseStrongRefs();

System.gc(); // only a suggestion, may not GC/unload
ClassLoader result = probe.get();

System.out.println(result == null
        ? "LOADER_CLEARED"
        : "NOT_CLEARED_YET");
~~~

**The snippet above is not a standalone Java program**: the illustrative method `makeLoaderAndReleaseStrongRefs()` is not defined. It explains how to read the measurement:

- `LOADER_CLEARED` means the weak reference can no longer retrieve the loader object; this is a signal that the loader has been processed by GC.
- `NOT_CLEARED_YET` **does not prove a class-loader leak**: a strong reference may still exist, or the collector may not have run in the required way.
- When the `result` variable is non-null, it is itself a **new strong reference** in the running scope; test code can inadvertently keep alive the very object it is waiting to be collected.

**Avoid `finalize()`:** overriding `finalize()` on a loader or plugin object is not a class unloading hook. Finalization is an old, deprecated/unreliable mechanism and can be disabled. Use explicit close, the Reference API with proper semantics, or JVM tools to measure, rather than treating logs from a finalizer as proof that a class has unloaded.

## 9. Observing class loading/unloading with HotSpot

With HotSpot/JDK 17+ JVMs supporting **Unified Logging**, use:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp app-out LoaderCycleDemo plugin-out
~~~

This command logs both class load events and **class unload events if any occur**. The log output depends on the JVM/GC/environment, so no "fixed stdout" is shown when logging is enabled.

You can write JVM logs to a file (Bash/Linux/macOS):

~~~bash
java '-Xlog:class+load=info,class+unload=info:file=classes.log:uptime,level,tags' -cp app-out LoaderCycleDemo plugin-out
~~~

In PowerShell, pass options containing special characters as a quoted string:

~~~powershell
java '-Xlog:class+load=info,class+unload=info' -cp app-out LoaderCycleDemo plugin-out
~~~

**Note:** the example in section 6 runs quickly and does not force the collector, so it is completely normal to see load logs for both `Greeter` classes **without any unload logs** before the process exits. That is not a bug; the purpose of the example is to demonstrate **class identity**, not to generate workload for GC measurement.

Additional observation methods on compatible JVMs:

- `-Xlog:gc*` shows GC activity, but does not by itself explain why a loader is kept alive.
- `jcmd <pid> VM.classloader_stats` can provide statistics on class loaders/class metadata on HotSpot builds that support this command; use `jcmd <pid> help` to check the actual capabilities of the target JVM.
- Heap dumps/Java Flight Recorder or a profiler can help find **retaining paths** from GC roots to `ClassLoader`, threads, `Class<?>`, listeners, or caches.
- When comparing reloads, record the plugin version, loader ID, stop/close timestamp, and count of remaining live loaders.

A heap dump can contain passwords, tokens, and user data in memory. Only collect it when authorized, store it in an access-controlled location, and do not upload it publicly.

### Metaspace is not synonymous with class count

HotSpot typically uses **Metaspace** to manage many forms of class metadata. However:

- `used`, `committed`, and `reserved` are different quantities.
- The JVM may keep committed capacity for **reuse** even after metadata has been reclaimed.
- Concurrent workloads may load new classes while old classes unload, keeping total `used` from decreasing.
- Memory for object instances, class metadata, code cache, native buffers, and file-mapped pages are different consumers.

Therefore, "RSS did not decrease" or "Metaspace committed did not decrease immediately" is **not enough** to conclude that class unloading failed. Combine unload events, loader stats, and heap retaining paths.

## 10. Common causes of class loader leaks

### 10.1. Threads created by the plugin have not been stopped

A plugin creates background threads, executors, schedulers, or job queues. After the host removes the plugin from the UI, workers still run plugin code or hold callbacks/plugin instances. A worker can retain the plugin's runtime classes/loader or TCCL.

Prevention:

1. Design `start()`, `stop()`/`close()` lifecycles with clear ownership.
2. Stop accepting new tasks.
3. Call shutdown/cancel according to protocol, using interruption properly.
4. Wait for a bounded timeout and log incomplete tasks.
5. Do not use `Thread.stop()` to force termination.

Do not write a plugin worker as an endless busy loop and hope GC will clean it up.

### 10.2. Thread context class loader is not restored

A long-lived host thread may change its context loader to run plugin services:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Invoke appropriate plugin/service discovery
} finally {
    current.setContextClassLoader(previous);
}
~~~

This is an **illustrative snippet**: `pluginLoader` is created elsewhere. If not restored in `finally`, the host thread can retain the old version's loader for a very long time.

However, restoring TCCL is **not enough** if the host still holds `Class<?>`, plugin instances, proxies, or registry entries. This is only one item in the checklist.

### 10.3. ThreadLocal in host thread pools

Thread pools typically reuse workers for a long time. If a `ThreadLocal` on a host worker holds an object belonging to a plugin class and the plugin does not call `remove()`, the loader can remain reachable from the thread pool.

Even when the implementation uses **weak keys** for `ThreadLocalMap`, the value can still be retained until the map cleans up stale entries. Do not rely on "ThreadLocal weak keys" as a promise that GC will immediately free plugin objects.

Best practice: set context within a scope using `try/finally`, call `remove()` when the context is no longer needed, and do not let queued tasks or MDC/logging contexts hold plugin objects across requests.

### 10.4. Caches, service registries, listeners, MBeans, drivers

Common root sources:

- A `static Map<String,Object>` in a host class holding plugin objects or class metadata.
- An event bus holding listeners created from plugin classes.
- A service locator/DI container holding plugin singletons after disable.
- An executor queue holding plugin `Runnable`s or capturing lambdas.
- Logging handlers or callbacks still registered.
- `MBeanServer` holding MBeans registered by the plugin.
- JDBC/service registries or native libraries holding drivers/handles via their own mechanisms.
- A reflection cache holding `Class<?>`, `Method`, `Field`, `Constructor` from an old plugin generation.
- JNI global references or framework runtimes holding references to classes/plugin objects.

Do not blindly clear all caches: identify the **owner and registration API**, then unregister each resource at stop time. The same class loader can be retained by multiple independent branches; **all significant retaining paths** must be addressed.

### 10.5. Static fields and reference cycles

A static field in a class **defined by the plugin loader** can point to a plugin object or the loader, forming a cycle. If the entire cycle is no longer reachable from roots, tracing GC can still reclaim it.

Conversely, `HostRegistry.staticMap -> PluginObject -> PluginClass -> PluginLoader` originating from a long-lived host class is real retention. On reload, you must clean up **the old version's registration**, not just set a local variable to null.

## 11. Designing hot-reload per loader version

For plugins that can be upgraded while the application is running, a common structure is:

~~~text
App loader / shared API loader
  ├── Plugin (interface)
  ├── PluginContext
  └── PluginManager

PluginLoader v1
  ├── PluginImplementation v1
  └── v1's own dependencies

PluginLoader v2
  ├── PluginImplementation v2
  └── v2's own dependencies
~~~

**Why must the API be in the shared loader?** If both the host and the plugin define the `Plugin` interface using two different defining loaders, they are two different runtime classes despite having the same name; `instanceof Plugin` or casting can fail.

### Safe version replacement workflow

1. Create the v2 loader and prepare binaries/dependencies.
2. Verify that v2 can initialize and pass required health checks.
3. Block new requests from going to v1; let v1 **drain** already accepted tasks/requests.
4. When v1 is no longer serving, call lifecycle `stop/close`, cancel schedulers/timers, and close network/database/file resources.
5. Unregister all callbacks/listeners/MBeans/registries/caches holding v1.
6. Clean up TCCL, ThreadLocals, queues, and retained class/method/instance references in the host.
7. Close loader v1 if it is a `URLClassLoader` to close the corresponding JARs/resources.
8. Drop the last host-owned references to v1.
9. Monitor loader versions and class-unload events **afterward**; do not claim `stop()` unloaded classes synchronously.

Business consistency must be preserved: do not close loader v1 while v1 requests still need to load new classes/resources. Closing file handles early does not necessarily interrupt a running method, but it can cause subsequent dependency/resource loading operations to fail.

### Do not redefine the same named class in the same loader

A normal loader is not a "dictionary store" that allows arbitrarily overwriting the definition of an already-defined named class with different bytecode. Redefining the same binary name in the same loader via normal definition paths can lead to `LinkageError`. Java instrumentation/hotswap is a separate mechanism with specific limitations.

To hot-reload plugin generations, use a **new defining loader** and manage old/new version objects concurrently during the draining phase.

## 12. Some advanced JVM exceptions and extensions

### Hidden classes

`MethodHandles.Lookup.defineHiddenClass` allows defining specialized runtime types for frameworks/lambdas/proxies. Hidden classes have special rules for identity, name lookup, and **strong/weak reachability**.

A hidden class with weak reachability semantics may become eligible for unloading based on that class's own reachability, **without necessarily waiting for its defining loader to be collectible like normal named classes**. Therefore, the statement "every class in the JVM is only unloaded when the entire loader dies" is too broad if it includes hidden classes.

### Lambdas and dynamically generated bytecode

Lambdas or framework-generated code do not necessarily correspond to a `.class` file inside a JAR. Some JVMs use hidden classes or other runtime mechanisms. Do not use the number of `.class` files on disk to accurately count loaded/unloaded runtime classes.

### Native handles and reflection

A `Class<?>` or `java.lang.reflect.Method` can retain a class/loader via runtime relationships; `MethodHandle`, proxies, and JNI refs can add retaining paths. Internal JVM structures are not necessarily fully visible as ordinary Java heap objects, so deep diagnostics require combining JVM tools with heap analysis.

## 13. Testing unloading properly

An integration test for hot reload should measure **multiple cycles** and **convergence** rather than a deadline based on a single `System.gc()`.

### Steps

1. Create a **new loader for each version** and record the loader's ID/version.
2. Load, run a small set of requests, and verify output.
3. Shut down the plugin per lifecycle, unregister, close I/O, and stop thread pools.
4. Drop all references held by the test harness or host to the loader, classes, and plugin objects.
5. Monitor `WeakReference<ClassLoader>`/`ReferenceQueue` without inadvertently holding a strong reference in test code.
6. If needed, apply GC pressure in the test environment with a safe limit; do not use a `System.gc()` loop as a deterministic guarantee.
7. Cross-check class-unload logging, class-loader stats, and heap retaining paths.
8. Compare Metaspace/class counts and memory metrics **across multiple cycles**, not from a single snapshot.

**Result classification:**

- **Observed unloading:** runtime logs actually record that old version classes were unloaded.
- **Loader retained:** there is a strong reference path from a root to the loader or an object leading to it after the plugin has stopped.
- **Inconclusive:** `WeakReference.get()` is still non-null or committed memory has not decreased after one GC. This is a temporary observation, not enough to confirm a leak.

Even with evidence of unloading, the test must still verify that **resources are closed** and no unauthorized background work remains. Unloading does not replace the plugin's cleanup responsibility.

## 14. Common diagnostic scenarios

### Scenario A: Reloaded 20 times, Metaspace keeps growing

Possibilities include: there really are many new class generations; old loaders are retained by a host static cache; plugin threads have not stopped; the JVM has not unloaded yet; or committed capacity has not been returned to the OS. Find retaining paths and unload logs before changing the collector/increasing heap.

### Scenario B: No instances remain, yet the loader stays alive

Check `Class<?>`, reflection caches, thread context loaders, global registries, lambdas/callbacks, scheduler queues, and thread-local values. A class does not need instances to stay alive.

### Scenario C: `ClassCastException: Foo cannot be cast to Foo`

There may be **two different runtime Foo classes** from two defining loaders. Inspect `obj.getClass()` and `obj.getClass().getClassLoader()`, check the shared API loader, and do not compare by class name alone.

### Scenario D: Loader is `close()`d yet plugin methods are still running

Correct: close is neither interrupt nor unload. The host must stop tasks via its own lifecycle before closing the loader and dropping references.

### Scenario E: `System.gc()` produces no class-unload events

Inconclusive: the loader may still have a root path or the JVM has not performed class unloading. Check logs and heap. Do not use `finalize()` to try to observe class unloading.

### Scenario F: An application only called a static method, yet the class is already initialized

A static method can trigger class initialization without creating an instance. Conversely, a class can be loaded without being initialized. **Loading, initialization, object GC, and class unloading** are four separate concepts.

## 15. Unload-safe plugin operations checklist

- **Ownership:** each plugin version has its own loader/context and a list of resources/callbacks it owns.
- **Start:** record version, binary path, class-loader identity, and dependency boundary.
- **Stop:** block new work, drain old tasks with a bound, and close network/file/DB/executors.
- **Unregister:** remove the plugin from host registries, services, MBeans, listeners, caches, and scheduling.
- **Context:** restore TCCL, remove ThreadLocals, and clear queued callbacks.
- **Loader:** close `URLClassLoader`/managed resources per API at the right time.
- **References:** ensure the host does not retain old version Plugin objects, Classes, Methods, or loaders.
- **Verification:** monitor class load/unload logs and retained loader references; evaluate memory across multiple cycles.
- **Failure handling:** if a loader stays alive, inspect heap retaining paths from roots; do not just add `System.gc()`.

This workflow helps the application manage **resources and business safety** well even when the JVM decides to defer class unloading.

## 16. Self-check questions

1. Does having no remaining `Plugin` instances guarantee immediate class unloading? **No**, the defining loader may still be reachable.
2. For normal named classes, what is the central condition for a class to be eligible for unloading? **Its defining class loader can be reclaimed by GC**.
3. Is `URLClassLoader.close()` a command to unload all classes it defined? **False**.
4. Are two classes with the same binary name defined by two loaders the same JVM type? **False**.
5. Can an app static cache holding an old plugin object keep the old loader alive? **Yes**.
6. Is `System.gc()` a deadline guaranteeing class unloading? **No**.
7. How is a class-loader leak typically proven? **A strong retaining path from a GC root**.
8. Why must TCCL be restored on host threads? **To avoid unintentionally retaining the old version's loader**.
9. Is a reference cycle inside a plugin guaranteed to be a leak? **No**, if it is not reachable from a root.
10. Does `WeakReference<ClassLoader>.get() != null` after GC prove a leak? **No**.
11. Why is Metaspace committed not decreasing insufficient to conclude classes did not unload? **The JVM may keep capacity for reuse**.
12. Do classes defined by the bootstrap loader have the same lifecycle as a plugin child loader? **No**.
13. Should multiple versions of the same named class be hot-reloaded in the same loader? **Not the standard strategy; use a loader per version**.
14. Should GC be left to clean up a plugin's sockets, executors, and DB connections? **No**, close them proactively.
15. Can hidden classes have special unloading rules? **Yes**, not all named-class rules apply.
16. If `Foo cannot be cast to Foo`, what should be checked? **Defining loaders and runtime class identity**.

## 17. Official references

- **JVMS Java SE 17, §5.3 Creation and Loading**, class identity and unloading: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS §5.4 Linking**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS §5.5 Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17, Chapter 12 Execution**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **`ClassLoader` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **`URLClassLoader` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **`WeakReference` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **`MethodHandles.Lookup.defineHiddenClass` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html

**Technical conclusion:** class unloading is not a direct call but a **possible consequence of GC and JVM policy**. For normal named classes, the defining loader must be eligible for GC reclamation. In a plugin/hot-reload system, the most important thing is **deliberate lifecycle management: stop work → unregister → close resources → drop strong references → let the JVM decide GC/unloading**. Observe with class-unload logs and retaining paths; do not treat `System.gc()` or `URLClassLoader.close()` as a commitment to immediate unloading.
