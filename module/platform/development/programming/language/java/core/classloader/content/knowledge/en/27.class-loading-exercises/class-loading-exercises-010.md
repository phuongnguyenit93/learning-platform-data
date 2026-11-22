# Investigating a Class Loader Leak Scenario in Java

## 1. Real-World Scenario: Reloading Plugins Repeatedly, Metaspace Keeps Growing

Suppose a long-running Java application has a mechanism to load plugins from separate JARs using `URLClassLoader`. Each time a new version is deployed, the host creates a new loader, loads the new implementation, switches requests to the new version, and then closes the old loader.

After hundreds of reloads, monitoring observes:

- The number of loaded class loaders or classes increases, while the number of unloaded classes is low.
- Metaspace tends to grow with the number of reloads and does not return to a stable level.
- Heap dumps show that many old `URLClassLoader` instances are still reachable.
- A long-running machine may encounter `OutOfMemoryError: Metaspace` or increased GC latency; however, not every metaspace increase leads to an error.
- Old JAR files may still be held open on Windows if resource handles are not closed — **this is a different resource bug** from a ClassLoader remaining alive in the heap.

The question of this exercise is not “how to call `System.gc()` to force unloading?”, but rather:

> **Which strong reference from a GC root is holding the loader of the retired plugin version, and who must clear that reference during the plugin lifecycle?**

In this example, we will create two reliably observable paths that retain the loader:

1. A `static` host registry holding a `Class<?>` belonging to the plugin loader.
2. A long-lived host worker thread holding the loader via the **thread context class loader (TCCL)**.

We will close the URLClassLoader, prove that **closing does not automatically sever the two references**, and then clean up the registry/TCCL, but **do not claim that GC/class unloading has occurred immediately**.

## 2. A Live Loader Is Only a Leak When Its Expected Lifecycle Has Ended

Each plugin generation typically has its own defining loader, and a `Class<?>` also carries the runtime identity of that loader. If a generation has stopped but a `Class<?>`, plugin object, or TCCL is still retained by the host, the JVM may not reclaim the loader and its corresponding metadata.

Three events are **not synonymous**:

| Event | Guarantees | Does Not Guarantee |
| --- | --- | --- |
| `URLClassLoader.close()` | Begins releasing URL/JAR resources opened by the loader; does not look up new own sources per contract | Does not clear classes, stop threads, or force GC |
| Host drops strong references | Severs the retention paths controlled by the host | Other GC roots may still exist; does not guarantee immediate unloading |
| GC/class unloading | The JVM reclaims metadata when conditions are suitable | No deadline set by `System.gc()` |

**Metaspace growing / committed not decreasing after one GC is not enough to conclude a leak.** Stronger evidence is a *retired* loader with no remaining valid requests that is still reachable from GC roots via a host cache, worker TCCL, or listener. This lab creates and cleans up the first two paths specifically, while when GC occurs is a separate observation concern.

## 3. GC Roots and Loader Retention Paths

To conclude a leak, you need to find a **strong reference path from a GC root** to the loader or to a class/object defined by the loader.

Example 1 — Host registry:

~~~text
GC Root
   |
   v
java.lang.Class<host.LeakLab>
   |
   v
static CACHE: Map<String, Class<?>>
   |
   v
Class<plugin.Greeter> (defined by loader L1)
   |
   v
Defining ClassLoader L1
~~~

The path above illustrates retention through class metadata. In a heap dump, the actual link from a Class to its loader may be displayed differently by tools depending on the JVM; rely on **path to GC roots** and class-loader grouping, without assuming fixed internal field names.

Example 2 — Thread context loader:

~~~text
GC Root
   |
   v
Worker Thread in long-lived pool
   |
   v
Thread.contextClassLoader
   |
   v
URLClassLoader L1
   |
   v
Defined plugin classes/resources
~~~

If the host changes a thread's TCCL to the plugin loader and **forgets to restore it**, the thread pool can retain that loader for the lifetime of the application.

Example 3 — Callback/listener:

~~~text
Host singleton EventBus
   |
   v
List<Listener>
   |
   v
plugin.ListenerImpl
   |
   v
Class<plugin.ListenerImpl>
   |
   v
Plugin ClassLoader
~~~

Even without directly holding a `ClassLoader`, a plugin instance or `Class<?>` can still keep the loader reachable. This is why an investigation must look for the **entire reference chain**, rather than just grepping code for `ClassLoader` variables.

## 4. Setting Up the Java 17+ Exercise

The exercise uses exactly **two source files**, with no external libraries outside the JDK:

- `plugin.Greeter`: a plugin class with a static method to prove the code is loaded.
- `LeakLab`: the host that creates a child `URLClassLoader`, stores the `Class<?>` in a static registry, sets the loader as the TCCL on a worker thread in a pool, closes the loader, and then cleans up.

The code runs on Java 17+.

### Directory Structure

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── plugin/
│   │       └── Greeter.java
│   └── host/
│       └── LeakLab.java
└── out/
    ├── plugin/                 (created after compilation)
    │   └── plugin/Greeter.class
    └── host/                   (created after compilation)
        └── LeakLab.class
~~~

**Very important condition:** the application classpath at runtime must **contain only `out/host`**. Do not put `out/plugin` on the host classpath, otherwise the parent loader could load `plugin.Greeter` first and break the experiment condition.

### File src/plugin/plugin/Greeter.java

~~~java
package plugin;

public final class Greeter {
    public static String greet() {
        return "hello-plugin";
    }
}
~~~

The class is declared public and has a public static method for the host to invoke via reflection; the plugin does not need to directly use any host-specific API.

### File src/host/LeakLab.java

~~~java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LeakLab {
    private static final Map<String, Class<?>> CACHE = new HashMap<>();

    private static WeakReference<ClassLoader> loadAndRetain(
            Path root, ExecutorService pool) throws Exception {
        URL source = root.toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{source}, LeakLab.class.getClassLoader())) {

            Class<?> type = loader.loadClass("plugin.Greeter");

            // Loader retention path #1: long-lived host registry.
            CACHE.put("old-plugin", type);

            // Loader retention path #2: pool thread holds TCCL.
            pool.submit(() ->
                    Thread.currentThread()
                            .setContextClassLoader(loader)).get();

            System.out.println("plugin defined by child: "
                    + (type.getClassLoader() == loader));
            System.out.println("plugin says: "
                    + type.getMethod("greet").invoke(null));

            return new WeakReference<ClassLoader>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "plugin classes root needed");
        }

        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Thread worker =
                    pool.submit(Thread::currentThread).get();
            ClassLoader original =
                    worker.getContextClassLoader();

            WeakReference<ClassLoader> weak =
                    loadAndRetain(Path.of(args[0]), pool);

            System.out.println("registry holds Class: "
                    + CACHE.containsKey("old-plugin"));

            System.out.println("worker TCCL points to loader: "
                    + (worker.getContextClassLoader() == weak.get()));

            System.out.println("closed loader still reachable: "
                    + (weak.get() != null));

            // Retire plugin: clear the identified references.
            CACHE.clear();

            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(original)).get();

            System.out.println("registry cleaned: "
                    + CACHE.isEmpty());
            System.out.println("worker TCCL restored: "
                    + (worker.getContextClassLoader() == original));

            // Do not test GC timeliness or guarantees.
            System.out.println("class unloading guaranteed: false");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Why Is the Example Designed This Way?

1. `URLClassLoader` takes **the host's loader as its parent** and the URL of the directory containing the plugin class. The host does not have `plugin.Greeter`, so the child is truly the **defining loader**.
2. `loadAndRetain` stores the plugin's `Class<?>` in `CACHE`, a static Map on a class belonging to the long-lived application loader.
3. A task in the single-thread executor intentionally sets the worker thread's TCCL to the child loader; the task finishes, yet **the thread in the pool remains alive**.
4. `try-with-resources` closes the URLClassLoader upon exiting the method; however, the cache and TCCL **still** retain the loader.
5. `WeakReference<ClassLoader>` allows the experiment to query the reference while it is held without adding a **strong reference from the WeakReference itself**. However, calling `weak.get()` at a given point does not by itself prove that GC has run; we rely only on the strong references visible in the code.
6. `CACHE.clear()` removes one retention path; reassigning the old TCCL on **the exact same worker thread** removes the second path.
7. `pool.shutdown()` initiates shutting down the thread pool in the finally block. In a real application, timeout/awaitTermination should also be added according to the lifecycle if asynchronous tasks are still running.
8. The program **does not claim** that class unloading has occurred right after cleanup. There is no `System.gc()` loop waiting until the weak reference becomes null.

### Compiling and Running on Linux/macOS

From inside the `example` directory:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
    src/plugin/plugin/Greeter.java

javac --release 17 -d out/host \
    src/host/LeakLab.java

java -cp out/host LeakLab out/plugin
~~~

### Compiling and Running on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host |
    Out-Null

javac --release 17 -d out\plugin src\plugin\plugin\Greeter.java
javac --release 17 -d out\host src\host\LeakLab.java

java -cp out\host LeakLab out\plugin
~~~

Note that `src/plugin/plugin/Greeter.java` has two directories named plugin due to how the source root and package are organized; the output binary name is still just `plugin.Greeter`.

### Verified Exact Stdout

~~~text
plugin defined by child: true
plugin says: hello-plugin
registry holds Class: true
worker TCCL points to loader: true
closed loader still reachable: true
registry cleaned: true
worker TCCL restored: true
class unloading guaranteed: false
~~~

The full source code was compiled with `javac --release 17`, executed on the JDK, and matched all eight lines of stdout exactly.

**Interpretation:**

- **plugin defined by child: true**: the experiment condition is valid; the class is defined by the separate URLClassLoader.
- **plugin says: hello-plugin**: the plugin class works and is invoked via reflection.
- **registry holds Class: true**: the host's static registry is holding the plugin's Class.
- **worker TCCL points to loader: true**: a long-lived thread is still directly retaining the plugin loader.
- **closed loader still reachable: true**: even though `try-with-resources` called `close()`, references to the loader still remain.
- **registry cleaned: true**: the host has removed the Class from the registry.
- **worker TCCL restored: true**: the TCCL on the exact worker thread has been restored to its previous value.
- **class unloading guaranteed: false**: after cleanup, the program does not claim that the JVM has GC'd/unloaded the class.

This experiment only demonstrates **the retention sources and the action of actively severing the two retention paths**. It should not be used as a metaspace benchmark, an automated memory leak test, or a real-time class unloading guarantee.

## 5. Why Does a Leak Still Persist After close()?

`URLClassLoader.close()` has a clear scope: it terminates the ability to load new classes/resources **defined by the loader itself**, attempts to close file handles it opened, and does not destroy already loaded classes/objects. The parent loader can still provide parent classes according to the delegation mechanism.

The following calls are **not synonymous**:

~~~java
loader.close();       // Close the URLClassLoader's resources.
loader = null;        // Clear one specific strong reference variable.
System.gc();          // Suggest GC, with no timing guarantee.
~~~

This is an **illustrative** snippet: the `loader` variable must not be `final` and it may throw `IOException`. Even after the local variable becomes null, paths such as `CACHE → Class<?> → loader` or `Thread → contextClassLoader → loader` still exist.

If you see an error where a JAR cannot be deleted on Windows, it may be a handle leak rather than heap/class metadata. The `JarURLConnection` cache, an independently opened `JarFile`/`ZipFile`, a custom loader/framework, or another process can also hold the file open. You must investigate **who owns the handle**, rather than inferring from metaspace.

### How Are Loader Leaks and Heap Object Leaks Related?

A still-reachable loader can keep its corresponding class metadata alive. However, not every instance whose type belongs to the loader will be retained merely because the loader exists; regular objects are still GC'd according to their own reachability. Conversely, a single **instance** still held by the host is enough to create a retention path for the runtime class/loader.

Do not make a simplistic one-way assumption that “the loader keeps all objects ever created” or “if GC collects the objects, the loader is definitely unloaded”. These are two sets of reachability conditions that need to be analyzed using GC roots.

## 6. Step-by-Step Practical Investigation Process

A production investigation requires before/after evidence and verifiable conclusions, not just a gut feeling that “metaspace is growing”.

### Step 1 — Identify Symptoms and Baseline

Record at least:

- JDK version/build, GC, JVM flags, and max metaspace if any.
- Number of plugin reloads and the number of plugin versions that **should** still be active.
- The number of live loader classes by type/identity, not only the number of `URLClassLoader` instances created from the beginning.
- Loaded/unloaded class counts (if available), metaspace used/committed, heap memory, and GC activity.
- Any stopped plugin versions that still have known references in the host registry/task scheduler.

Example observation table:

| Point in Time | Serving Loader Version | Retired Loaders Still Visible | Sign Requiring Investigation |
| --- | --- | --- | --- |
| Before reload | v1 | 0 | Baseline |
| After switching to v2 | v2 | v1 temporarily | May be normal while v1 requests have not finished |
| After v1 has stopped/retired | v2 | v1 still reachable | Need to find GC root paths |
| After multiple reloads | v10 | v1…v9 still retained | Stronger evidence of abnormal retention |

The table is only a **hypothetical scenario**, not measurements from an existing system. Do not treat the appearance of loader v1 right after cutover as a leak if valid requests are still running.

### Step 2 — Confirm the Class Loader Identity

From the plugin class:

~~~java
Class<?> type = pluginInstance.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

This is illustrative code inside a method that has `pluginInstance`. `getClassLoader()` is often more important than the class name string. Two classes with the same binary name but different defining loaders can be two different versions. If the actual loader is the application loader (because the plugin JAR is on the host classpath), the ability to retire individual versions separately will not behave as the architecture expects.

### Step 3 — Collect Information with Appropriate JVM Tools

On HotSpot JDK 21, you can use `jcmd`. First find the PID or invoke help to verify the JVM-specific commands:

~~~bash
jcmd -l
jcmd <pid> help
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.metaspace basic
~~~

The lines above are **shell templates where `<pid>` must be replaced with the actual PID**, not a program to run verbatim. `jcmd` usually needs to be run on the same machine and with appropriate user/group permissions for the target process.

Main functions:

- `VM.classloader_stats`: summarizes loader/class metadata statistics to inspect the scale of existing class loaders.
- `VM.classloaders`: displays the class loader hierarchy; some options support listing specific classes.
- `VM.metaspace`: inspects metaspace usage, with additional options depending on the JVM.
- `GC.heap_dump`: creates a heap dump to analyze refs; can significantly impact operations, disk space, and pauses.
- `GC.class_histogram`: summarizes objects on the heap, but does not replace path-to-root analysis.

**Operational warning:** heap dumps often contain sensitive application data such as tokens, user information, or payloads. Store them in an access-protected location, do not upload dumps to public places, and apply an appropriate retention/deletion policy. Do not run heavy commands in production during peak load hours without assessing the impact.

### Step 4 — Capture a Heap Dump Properly

After identifying the PID and an appropriate output path:

~~~bash
jcmd <pid> GC.heap_dump /secure/path/after-reload.hprof
~~~

This is a command template; check the JVM's help output and ensure sufficient disk space and write permissions. A heap dump can be very large, cause pauses/impact, and how the JVM handles GC before dumping depends on the options.

If you need to compare retention, you can capture dumps before and after multiple reloads under a controlled, repeatable procedure. Do not compare two dumps with different workloads and conclude a definitive leak solely from an increase in bytes.

### Step 5 — Analyze “Path to GC Roots”

Open the dump in Eclipse Memory Analyzer Tool (MAT) or a compatible heap analysis tool. Look for:

1. Instances of `java.net.URLClassLoader` or a custom subclass of the plugin loader.
2. Loaders carrying the name/identifier of a **retired version**.
3. Classes defined by that loader, for example `plugin.Greeter`.
4. **Paths to GC Roots**, prioritizing strong references (you can select *exclude weak/soft/phantom references* when analyzing strong retention causes).
5. Retained set/dominator tree to evaluate the retained object graph.
6. Nodes that are a host static field, Thread.contextClassLoader, ThreadLocal, listener, logger, scheduler, or cache.

For the sample exercise, the two suspects are:

~~~text
GC Root -> Host class -> static CACHE
                      -> Class<plugin.Greeter>
                      -> URLClassLoader old

GC Root -> executor worker Thread
                      -> contextClassLoader
                      -> URLClassLoader old
~~~

A snapshot may not show the exact chain as in the simplified diagram above due to how the JVM/MAT represents the Class mirror and native metadata; the decisive factor is the **path retaining the loader from roots**, not fixed internal field names.

### Step 6 — Find the Owner of the Reference

Do not just see a “Thread” root and clear it arbitrarily:

- Was this thread created by the **host** or by the plugin?
- If it is a host thread pool, which task changed the TCCL? Can it be restored by an action running on that exact worker?
- By what key is the registry cached by the host to look up classes/providers? Is the entry deleted by version upon retirement?
- Which listener was registered without being unregistered?
- On which thread was the ThreadLocal set, and has it been removed on that same thread?
- Is there an app/framework static field holding a plugin `Method`, `Constructor`, proxy, `Class<?>`, service instance, or lambda?

You need to identify the **owning object**, the behavior that created the reference, the point at which it must be cleaned up, and the verification check after cleanup.

### Step 7 — Fix and Verify Across Multiple Cycles

Once the root has been identified:

1. Add cleanup to the plugin lifecycle: `start → running → quiesce → stop → close → retire`.
2. Stop accepting new requests for the old plugin, and wait for in-flight requests to finish.
3. Unregister callbacks, cancel tasks, shut down executors, and close streams/JarFiles.
4. Remove host registry/cache entries by version, without breaking the new version.
5. Restore the TCCL in `finally` for any threads that the app modified.
6. Close the URLClassLoader (concurrent class loading must be avoided).
7. Drop strong references to the old `Class<?>`/plugin object/loader.
8. Run a repeated reload sequence with representative load, and compare loader counts/metaspace and paths-to-roots.
9. Do not set a pass condition that “GC must unload immediately within 100 ms”; instead, verify **the correctness of cleanup and data trends**.

When the old version needs to remain in parallel to finish in-flight requests, intentionally keeping the old loader during the drain phase is correct; only label it retired after the lifecycle contract ends.

## 7. Using WeakReference for the Right Purpose

`WeakReference<ClassLoader>` is often used in tests to observe whether a loader can be collected by the JVM after strong reference paths have disappeared.

~~~java
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);
~~~

This is an illustrative snippet. **WeakReference does not hold a strong reference to the referent**, but if the `pluginLoader` variable, a `Class<?>`, or a thread still holds the loader, then `weak.get() != null` is normal.

Caveats:

- `weak.get() != null` before cleanup **does not require calling GC** to prove that the loader is still reachable, if clear strong references still exist.
- `weak.get() == null` after a GC can help observe that the referent has been collected, but it is not a measurement that total memory has returned to baseline.
- `weak.get() != null` right after cleanup **does not prove a leak**. GC may not have run yet, or a temporary strong reference from the stack/debugger/test may still exist.
- Do not write an infinite `while (weak.get() != null) System.gc();` loop.
- If an integration test is needed, set a generous/controlled timeout, drop strong refs inside a helper scope, and combine with heap analysis on failure instead of absolute assertions based on GC timing.
- Use a `ReferenceQueue` if you want to observe notifications when the JVM processes weak references, though you still do not get a promise of any specific processing time.

In the sample program, we intentionally **do not** invoke GC so that learners focus on the two root paths created by the host and deterministic cleanup.

## 8. Leak Sources More Common Than Just a Static Map

| Reference Retention Point | A Common Root Path | Cleanup Measure |
| --- | --- | --- |
| Host static cache of `Class<?>`/`Method`/`Constructor` | Static field → reflective metadata → class/loader | Clear cache per plugin version; avoid global unbounded maps. |
| Thread context class loader | Thread pool worker → TCCL → loader | Save and restore TCCL in finally on the same thread. |
| ThreadLocal | Worker thread → ThreadLocalMap → plugin object | Remove/clear on the same thread; do not merely null out a variable in another request. |
| Listener/event bus | Host singleton → plugin's listener implementation | Unregister via registration token in the stop hook. |
| Executor/scheduled task | Queue/task/runnable → plugin class/object | Cancel futures, shut down executor, drain tasks. |
| Thread created by the plugin itself | Live Thread → Runnable/context loader | Stop using a controlled protocol and join/await termination. |
| JDBC driver registration | Global DriverManager registry → driver from plugin | Deregister the driver by the proper owner upon retirement, if appropriate. |
| MBean/JMX | MBeanServer → plugin MBean instance | Unregister the name when the plugin stops. |
| Logger/appender/callback | Logger context/listener → plugin object | Detach the plugin appender/handler/callback via the official API. |
| SPI provider caching | Long-lived ServiceLoader/list → provider Class or instance | Drop the registry/loader or create a new ServiceLoader per version. |
| Java shutdown hooks | Runtime hooks → plugin Thread/lambda | Remove the hook while still permitted and within a valid lifecycle. |
| Heap/native resources | Resource stream or JarFile/ZipFile | Close by the proper owner; memory leaks and file-handle leaks need separate analysis. |

In particular, **plugin static fields** are often misunderstood: an object graph residing entirely inside the plugin loader, with no root from the host or an external thread, can become unreachable together and be collected. Conversely, just a single reference from a host static field to a plugin object/class can keep the entire loader generation alive.

## 9. Distinguishing Normal Metaspace Growth from a True Leak

Careful evaluation:

| Observation | Reasonable Conclusion |
| --- | --- |
| Metaspace used increases after initial requests | Could be normal class loading. |
| Metaspace committed has not decreased after GC | Does not by itself prove the loader is still reachable; the JVM manages committed regions separately. |
| URLClassLoader.close() was called | Proves resource cleanup was requested, **not** class unloading. |
| Heap dump shows many retired loaders with strong GC root paths | Strong evidence of abnormal retention if those versions have genuinely stopped. |
| Live loader count increases nearly linearly across multiple drained reloads | A more reliable indicator for investigating a leak than a single snapshot. |
| GC/class unloading logs show old loaders were collected | Supports the conclusion that unloading occurred in that run; does not guarantee the next reload behaves identically. |
| JAR file cannot be deleted on Windows | Must investigate file handles; do not immediately conclude a metaspace leak. |

In production evaluations, measure **used vs committed metaspace**, number of classes/loader instances, heap-retained objects, GC behavior, and plugin lifecycle. Do not use an arbitrary metaspace number as a universal threshold for all workloads.

## 10. Code Fixing Process in Host/Plugin

### Do Not Leak TCCL: Always Use finally

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call code/framework whose contract requires the plugin's TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an illustrative snippet assuming an already created `pluginLoader`. It is valid when the task is processed on a single worker thread: **restore on the exact thread that was modified** before returning the thread to the pool.

Do not try to clear ThreadLocal values on another thread from an administrative thread by modifying private JVM fields; instead, build proper lifecycle/task cleanup on the owning thread.

### Do Not Leak the Registry: Remove by Version Key

~~~java
Map<PluginId, PluginHandle> handles = ...;

// When retiring the exact plugin version:
PluginHandle old = handles.remove(retiredPluginId);
if (old != null) {
    old.stopAndClose();
}
~~~

This is an illustrative snippet in a host with application-defined `PluginId` and `PluginHandle` types. If both v1 and v2 are running, you must remove **the exact version**, rather than calling clear on everything and accidentally deleting the currently serving plugin.

### Managed Lifecycle

A typical `PluginHandle` should own its loader, instance/provider, subscriptions, tasks, and dedicated resources. Create an API:

~~~text
start()
  -> acceptRequests()

quiesce()
  -> stopAcceptingNewRequests()
  -> awaitInFlightRequests()

stop()
  -> unregisterListeners()
  -> cancelJobs()
  -> clearCaches()
  -> restoreThreadContexts()
  -> closeStreamsAndJars()
  -> closeClassLoader()

retire()
  -> removeHostStrongReferences()
~~~

This is a **logical** diagram, not executable Java code. The goal is clear ownership and idempotent actions when exceptions occur during stop/cleanup.

If the plugin has lazy dependencies, do **not** close the loader before in-flight requests complete. With URLClassLoader, one thread calling `close()` while another thread is loading a class has unspecified behavior according to the API documentation.

### A Separate Classloader Is Not a Security Sandbox

Do not confuse isolating class namespaces with isolating permissions. A separate `URLClassLoader` does **not** strip plugin code of the JVM's filesystem/network/process permissions by default. If untrusted code must be executed, consider process/container isolation and controls outside the class-loading mechanism.

## 11. How to Build a More Reliable Regression Test

A leak-prevention test should have at least two verification layers:

**Functional, deterministic layer:**

- The plugin is defined by the child loader as expected.
- The plugin operation runs correctly.
- When the version is marked retired, registry/callback entries are removed.
- The TCCL of every affected host worker is restored.
- Threads/executors created by the plugin are stopped/shut down.
- Resource owners call close according to the contract; exceptions are logged/propagated.

**Unloadability, JVM observation layer:**

- Run multiple reloads in an isolated test process.
- Do not hold `Class<?>` or the loader in test variables or static caches beyond the version's lifetime.
- Observe WeakReference/ClassLoadingMXBean/logs/heap snapshots **within practical limits and conditions**.
- If the loader has not been collected, capture a heap dump and path-to-roots instead of drawing blind conclusions.
- Do not write assertions like “the loader must be GC'd within X ms” as a universal JVM rule.

A test data structure:

~~~text
Iteration 1: load v1 -> use -> quiesce -> close -> cleanup
Iteration 2: load v2 -> use -> quiesce -> close -> cleanup
Iteration 3: load v3 -> use -> quiesce -> close -> cleanup
...
Compare number of intentionally active plugin versions and reachable retired loaders
~~~

If the number of reachable retired loaders continues to grow after cleanup, only then dig into the root paths. If the count drops but committed metaspace has not decreased, distinguish allocation policy and fragmentation from retention.

### Why Not Use a Test That Only Calls System.gc()?

`System.gc()` is an advisory hint; a runtime may ignore it or handle it according to a different policy. References on the stack, JIT scopes, the debugger, and temporary variables in the test can still keep the loader alive. Do not use a single “weak.get is still non-null” result to conclude that the application has a leak.

## 12. Case Study: Root Cause Conclusion and Actions

### Symptoms

After each plugin reload, the previous generation's class loader still appears in the heap dump; the count of retired loaders increases even though the plugin manager called `close()`.

### Evidence in the Lab

- A cache in the host holds `Class<plugin.Greeter>`.
- An executor thread holds the child loader as its TCCL.
- The loader had `close()` called on it, yet the two retention paths were not automatically cleared.
- Cleanup code proactively calls `CACHE.clear()` and restores the TCCL on the worker thread.

### Root Cause

**The reference lifecycle outlived the plugin lifecycle**. The host forgot to clean up registrations/contexts after the old version retired. It is neither a bug that the JVM reloaded the same class name, nor because GC was “broken”.

### Fix

- Per-version registry/cache, cleared when the version retires.
- Temporarily swap the TCCL within a `try/finally` scope without leaving it set in the thread pool.
- Ensure the plugin lifecycle quiesces, stops tasks, unregisters, closes resources, and only then retires the loader.
- Add regression tests for the retention paths, rather than only testing that `close()` was called.

### Verification After Fix

The strong-reference paths controlled by the host are severed; the application can continue measuring across multiple reloads to see whether old class loaders remain reachable from any other GC roots. **Do not claim that GC has unloaded them**, because the JVM does not guarantee timing.

## 13. Common Diagnostic Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Seeing metaspace increase once and calling it a leak | Class loading/JIT and allocation policies can normally increase it | Compare trends and reachable retired loaders across multiple cycles |
| Assuming `URLClassLoader.close()` unloads classes by itself | Close manages lookup/resource handles, without forcing GC | Sever references and then observe the JVM |
| Using `System.gc()` as a production fix | Does not resolve the GC root holding the loader | Find the owner and clear references |
| Failing to distinguish a Class from a class name | Two loaders can define the same binary name | Print `Class.getClassLoader()`, compare runtime Classes |
| Only reading exceptions or logging the loader name | Logs can be ambiguous | Use heap dump + paths-to-GC-roots |
| Clearing the static cache while forgetting TCCL | The thread pool continues retaining the loader | Restore the context on the exact worker |
| Calling `ThreadLocal.remove()` on the wrong thread | ThreadLocalMap resides inside each individual thread | Clean up from the owning thread or terminate the thread properly |
| Seeing a non-null WeakReference right after cleanup | The JVM may not have run GC yet | Do not draw conclusions from unguaranteed timing |
| Sharing a heap dump publicly to ask about bugs | Dumps can contain secrets/user data | Protect the file, restrict access and retention |
| Closing the loader while requests are still in flight | Concurrent load/close behavior is not guaranteed | Quiesce and wait before closing |
| JAR deletion fails and metaspace is blamed | A file handle leak is a different resource | Track open handles and the actual owner |
| Moving all classes to the system loader to avoid unload issues | Loses the ability to retire classes separately and invites version conflicts | Use a loader per version and a shared API parent |

## 14. Self-Check Questions

**Question 1.** Once `URLClassLoader.close()` has been called, is the loader guaranteed to no longer be in the heap?

**Answer:** No. Already loaded classes/objects may still be retained by the host/thread/registry; `close()` does not remove strong references.

**Question 2.** Why can a host's static `Map<String, Class<?>>` retain the entire plugin loader?

**Answer:** The Map holds the plugin's Class, which is tied to the runtime type defined by its defining loader; the root path from the host static cache can keep the loader reachable.

**Question 3.** Why is the TCCL on a worker thread a suspect point?

**Answer:** A worker thread outlives a single request/plugin version; contextClassLoader is a strong reference to the plugin loader if code sets it without restoring it.

**Question 4.** Do clearing the cache and restoring the TCCL prove that the class has been unloaded immediately?

**Answer:** No. That clears two known root paths; other paths may still exist, and the JVM/GC makes no commitment to unload immediately.

**Question 5.** Does a WeakReference still returning the loader right after cleanup always mean there is a leak?

**Answer:** No. GC may not have run yet, the test/debugger may still hold refs, or other roots may exist. You need to inspect the heap/paths-to-root and lifecycle, not just timing.

**Question 6.** Which tools help inspect class loaders and GC roots?

**Answer:** `jcmd VM.classloader_stats`/`VM.classloaders` support inspecting hierarchy statistics (HotSpot); a heap dump with MAT helps trace GC root paths and dominators.

**Question 7.** Why not close the loader immediately upon receiving a reload command?

**Answer:** In-flight requests may still require lazy class/resource loading; concurrent close and load have behavior not guaranteed by the API. You must quiesce/stop first.

**Question 8.** If a JAR file cannot be replaced on Windows, is it definitely a classloader leak in metaspace?

**Answer:** No. A file handle may be held by URLClassLoader, JarURLConnection, JarFile, or another process. File handles and class loader reachability must be measured separately.

## References

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): close(), accessing loaded classes/resources, and concurrency.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation, and runtime class identity.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): getContextClassLoader()/setContextClassLoader().
- [Java SE 21 — WeakReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html): semantics of weak reachability.
- [Java SE 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM.classloader_stats, VM.classloaders, VM.metaspace, GC.heap_dump.
- [JVMS Java SE 21 §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class loading and defining loader.
