# JFR, heap dumps, and class loader retention paths

In Java applications with plugins, application servers, hot redeploys, script engines, or a custom `URLClassLoader`, **creating a new loader does not mean the old loader will be immediately reclaimed by the garbage collector (GC)**. A class loader may still be retained by an object in a static cache, a worker thread holding a thread context class loader (TCCL), a `ThreadLocal`, a `ServiceLoader` provider, a listener, an MBean, a callback, a JNI reference, or an unexpected reference path.

If stopped deployments still leave loader/class metadata in **Metaspace**, the JVM can consume extra memory, accumulate multiple generations of classes with the same name, and over time cause GC pressure or `OutOfMemoryError: Metaspace`. However, **observing that a loader exists is not sufficient to conclude a leak**: the loader may still be serving a valid task, GC may not yet meet the conditions to run, or the metrics may reflect cached metadata according to the expected lifecycle.

A systematic investigation approach combines:

1. **JDK Flight Recorder (JFR)** to observe behavior over **time**: class loading/unloading, class loader statistics, allocation/old-object samples, and GC.
2. **`jcmd`/class loader statistics** to inspect a snapshot of loader status, class counts, and trends.
3. **An HPROF heap dump** to see the object graph at **a single point in time**.
4. **Path to GC Roots / Dominator Tree** in Eclipse Memory Analyzer (MAT) to identify **which strong reference is retaining the loader or plugin object**.
5. **Fixing the root cause and re-measuring under the same scenario**, rather than merely increasing `-XX:MaxMetaspaceSize` or forcing `System.gc()`.

This article focuses on Java 17+ and HotSpot when introducing diagnostic commands. Command names, JFR events, attach permissions, or GC outcomes may vary across JVM vendors and OSes; verify using `jcmd <PID> help` and the actual configuration. Logs, PIDs, object addresses, and GC states are dynamic data, and **fixed stdout should not be published if the runtime does not guarantee it**.

## 1. Things to distinguish before looking for a leak

| Concept | Meaning | Conclusion not to jump to |
| --- | --- | --- |
| **Class loader is still reachable** | There is a reference path holding the loader object. | Does not by itself prove a leak; the loader may still be in use. |
| **Class is still loaded** | The JVM still defines usable Class/type metadata. | Does not mean the loader has leaked permanently. |
| **Class unloading** | The JVM reclaims class/loader metadata when reachability and GC conditions are appropriate. | Not required to happen immediately after `close()` or `System.gc()`. |
| **Heap used** | Java heap memory of instances, maps, arrays, Class objects, and other objects. | Not identical to total Metaspace/native memory. |
| **Metaspace** | Native memory region where the JVM manages various types of class metadata (HotSpot). | Increasing Metaspace does not by itself prove a plugin loader is being retained. |
| **Shallow heap** | Size of an object itself in the heap. | Does not represent all memory it indirectly retains. |
| **Retained heap** | Amount of heap that could be freed if an object/dominator were removed according to the graph. | Does not equate to all native memory/Metaspace occupied by the loader. |

**Invariant to remember:** a class is identified by its **binary name and defining class loader**. Two versions of `com.acme.plugin.Worker` with the same name but different loaders are two distinct JVM types. When each redeploy creates a new loader, classes/data from the old deployment can continue to exist if the old loader remains reachable.

### When can a loader be reclaimed?

For a loader and the classes it defines to become eligible for collection/unloading, there can no longer be any **strong references keeping them alive** according to the GC/runtime: object instances of plugin classes, `Class<?>`, reflection/method handles, the loader object, threads executing code of that class, JNI global references, or other components that can keep the class/loader alive. Once eligible, the JVM still decides **when** and **whether** to perform GC/class unloading depending on the active collector and configuration.

**`URLClassLoader.close()` only closes loader resources**, such as JAR handles managed per the API; **it does not automatically delete Class objects and does not force class unloading**. Similarly, dropping a local variable or calling `System.gc()` creates no contract that the loader must disappear immediately.

## 2. The retention path is the focus of diagnosis

A class loader is retained when there is a **live retention path** from a **GC root** (or a JVM root condition) to the loader, or to an object/class whose liveness keeps the loader alive.

For example:

~~~text
GC Root: host class that lives for the lifetime of the JVM
    |
    v
HostRegistry.CACHE (static Map)
    |
    v
HashMap entry -> plugin instance
    |
    v
demo.plugin.Payload instance
    |
    v
Class metadata of demo.plugin.Payload
    |
    v
defining URLClassLoader
    |
    v
metadata/classes belonging to the old deployment
~~~

In heap analysis, the path from **instance → class → class loader** may be represented in MAT via class/loader relationships modeled by the tool; it is not necessarily an ordinary Java field that you can invoke via reflection.

Common roots or holders:

| Holder/retention path | Lifecycle mistake example | Remediation approach |
| --- | --- | --- |
| **Host static cache** | A map/singleton in a long-lived loader holds a plugin object, `Class<?>`, or method handle. | Remove entries on undeploy; avoid global strong caches without a policy. |
| **Thread.contextClassLoader** | A host worker pool still has TCCL pointing to `OldPluginLoader`. | Save and restore TCCL with `finally`; stop dedicated workers. |
| **ThreadLocalMap** | A long-lived thread retains a plugin-owned `ThreadLocal` value. | Call `remove()` on the right thread; scope the context; clean up executors. |
| **Scheduler/executor queue** | A `Runnable`/`Callable`/`CompletableFuture` callback captures a plugin instance. | Stop accepting tasks, cancel/drain the queue, and shut down properly with the lifecycle. |
| **Listeners/registries** | Event bus, JDBC driver manager, JMX MBean, or logging manager holds a plugin handler. | Unregister/deregister in the lifecycle hook. |
| **ServiceLoader cache** | The host stores `ServiceLoader` or provider instances across multiple deployments. | Drop references to the old loader/providers; create a loader per deployment. |
| **Reflection/caches** | Caches of `Class<?>`, `Constructor<?>`, `Method`, `MethodHandle`, or proxy metadata. | Scope the cache per deployment, using well-designed weak keys where appropriate. |
| **JNI/global/native hooks** | A native component holds a global reference to a plugin object. | Release JNI refs/native registrations according to the API. |

**ThreadLocal keys are weak, but values are strong:** `ThreadLocalMap` uses a weak reference for the key, yet the value can remain strongly held by an entry in a living worker thread, even when the key loses its references. Do not conclude “ThreadLocal is weak, so it is automatically safe.”

**A class loader is not a leak merely because a path exists:** A GC root path describes **why it is still alive**. You must verify whether the path is still **needed for business logic** after the plugin/deployment finishes. A loader currently processing a request may validly exist, whereas an old-version loader across ten redeploys with no remaining work is a much clearer sign of suspicion.

## 3. JFR: observing changes over time

**JDK Flight Recorder (JFR)** records JVM and application events over time, rather than only capturing a single heap snapshot. For class loader leaks, JFR is useful for answering:

- How many classes/loaders are created when loading or redeploying a plugin?
- After undeploy and GC, is there any sign of **class unloading**?
- How do loader statistics and Metaspace/GC change?
- Are long-lived objects caught by sampling?
- Which allocation stacks correlate with the spike in instances?

### 3.1. Capturing a short recording with jcmd

Suppose a Java 17 HotSpot JVM is running with an identified PID:

~~~bash
jcmd <PID> JFR.start name=loaderdiag settings=profile
~~~

This is a **shell command with a `<PID>` placeholder**: replace it with the actual PID number, and do not type `<`/`>` as literal characters in the shell. To see which recordings are currently running:

~~~bash
jcmd <PID> JFR.check
~~~

Once load/undeploy or the suspected reproduction has been performed, dump to a file:

~~~bash
jcmd <PID> JFR.dump name=loaderdiag filename=loaderdiag.jfr
~~~

If you need to investigate a suspected memory leak and have an allowable pause budget, Java 17's `jcmd` provides an option (note the **command-specific option name**):

~~~bash
jcmd <PID> JFR.dump name=loaderdiag filename=loader-roots.jfr path-to-gc-root=true
~~~

**Spelling note:** The `JFR.dump` option in JDK 17 documentation is `path-to-gc-root` (singular). In recording startup approaches such as `-XX:StartFlightRecording`/JFR configuration, you may instead see `path-to-gc-roots` (plural). Always run `jcmd <PID> help JFR.dump` on the exact target JVM to know the supported options; do not guess from a guide for another version.

Collecting paths to GC roots can cause **significant pause/overhead**, so only enable it once a leak is suspected and production impact has been weighed. A regular JFR recording may **not contain sufficient retention paths**; do not treat a default `JFR.dump` as a comprehensive replacement for HPROF.

Next:

~~~bash
jfr summary loaderdiag.jfr
jfr print --events jdk.ClassLoaderStatistics,jdk.ClassLoad,jdk.ClassUnload loaderdiag.jfr
~~~

`jfr summary` lists the event types actually present in the file. `jfr print --events ...` filters events that were already recorded; **it does not cause previously disabled events to reappear**.

### 3.2. Important pitfall: profile does not necessarily enable ClassLoad/ClassUnload

In the JFR configuration of many OpenJDK/HotSpot 17 builds, `settings=profile` enables statistics such as `jdk.ClassLoaderStatistics` but may **not individually enable** the high-detail events `jdk.ClassLoad` and `jdk.ClassUnload`. Therefore:

**Not seeing `jdk.ClassUnload` in a JFR file has at least two very different possibilities:** no events were recorded, **or** that event type was disabled. You cannot rely solely on a recording whose configuration has not been checked to declare that the JVM is not unloading classes.

What to do properly:

1. Use `jfr summary` to check the event types/counts and metadata settings.
2. Inspect the `$JAVA_HOME/lib/jfr/default.jfc` or `profile.jfc` configuration file of the **exact JDK** that is running.
3. If you need to track individual loads/unloads, create a **custom `.jfc`** enabling the `jdk.ClassLoad`/`jdk.ClassUnload` events, or configure JVM-supported event settings.
4. Capture the recording **before reproducing**. If JFR is started after classes have already been loaded, previously occurred loading events will not appear simply by waiting.
5. You can supplement with HotSpot unified logging when individual events are needed:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp . LoaderRetentionDemo
~~~

Class loading logging produces many lines depending on the JDK, classpath, and timing; **there is no fixed stdout** for this command. Look at the unloading of **specific loaders/classes**, not just the total log line count.

### 3.3. OldObjectSample and path to GC roots

JFR includes events such as `jdk.OldObjectSample` to provide signals about **long-lived objects** (based on sampling and configuration). When the recording is properly configured, JDK Mission Control (JMC) can show you the allocation stack and sometimes the retention path to GC roots.

- Sampling **does not enumerate every object** or guarantee capturing the exact leaking plugin loader.
- If the event has no relevant samples, that **does not prove there is no leak**.
- `path-to-gc-root=true` in a JFR dump must be explicitly enabled when you want to capture roots (subject to JVM capability); this collection carries overhead.
- Tracing the **complete reference path for a specific object** is usually more convenient with HPROF and MAT, whereas JFR excels at **timelines and correlation**.
- When analyzing JFR, compare snapshots/events across `deploy → use → undeploy → GC` cycles, rather than looking at only a single point in time.

### 3.4. How JFR, GC logs, and classloader stats complement one another

| Tool | What it observes well | Limitations |
| --- | --- | --- |
| **JFR** | Timeline: allocation/GC/class loader stats and enabled events. | Sampling-based; events may be disabled, and it is not a full object graph. |
| **`-Xlog:class+unload=info`** | Reports class unloads on HotSpot when they occur. | Only indicates whether unloading occurred; does not directly show every reference path. |
| **`jcmd VM.classloader_stats`** | Loader/class/metaspace snapshot. | Does not by itself identify the GC root retaining a loader. |
| **`GC.heap_dump` + MAT** | Object graph and paths to GC roots at a point in time. | Incurs pause/disk overhead; the dump does not contain full allocation history. |
| **JMC** | UI for JFR analysis, event correlation, and leak suspects/old samples depending on configuration. | Can only analyze evidence that was recorded. |

## 4. Heap dumps: capturing the object graph at a point in time

An HPROF heap dump generally lets you see **objects on the Java heap, fields, class/loader references, and GC roots** at dump time, depending on the JVM and export tool. Using HotSpot Java 17:

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump loader-before.hprof
~~~

**Meaning:**

- `VM.classloader_stats`: prints class loader and class metadata statistics. Used to identify whether the count of loaders of the same type grows across redeploy cycles; loader names or numbers are not standalone proof of a leak.
- `GC.class_histogram`: instance count/size by class on the heap; helps spot suspicious groups of objects. It does not directly answer “who is retaining the loader”.
- `GC.heap_dump`: creates an HPROF file for analysis with MAT. Under JDK 17 HotSpot, this command has **high impact** and typically requires a **full GC** unless `-all` is enabled.

**Do not use `-all` when trying to prove objects survive GC**: this option can include **unreachable** objects in the snapshot and may not perform a full GC beforehand. Therefore, an object's appearance in an HPROF `-all` dump **does not by itself prove it is strongly retained**.

If there are two phases:

~~~text
before: after plugin creation/while still held by host cache
after:  after undeploy, cache cleared, tasks stopped, and GC had a chance to run
~~~

you can collect:

~~~bash
jcmd <PID> GC.heap_dump loader-before.hprof
jcmd <PID> VM.classloader_stats
~~~

After cleanup, collect at another point in time:

~~~bash
jcmd <PID> GC.heap_dump loader-after.hprof
jcmd <PID> VM.classloader_stats
~~~

**There is no fixed loader/class count** between the two files. A loader may remain uncollected even with no remaining strong references due to GC timing, class unloading policy, active stacks, or references outside the scenario. Conclusions must be based on the retention path and whether lifecycle conditions have truly terminated.

### Operational and privacy warnings

- Heap dumps can be **very large**, causing significant pauses and increasing disk/memory pressure during capture.
- Dumps can contain **passwords, tokens, customer data, sessions, secret keys, and request payloads** still on the heap. Treat HPROF files as sensitive data: restrict file permissions, encrypt, enforce limited retention, securely delete per policy, and never send to public systems.
- `jcmd` typically requires appropriate attach permissions to the target JVM and compatible JDK/OS tools; containers and security policies may block attach.
- Do not create heap dumps in bulk in production without planning for disk capacity and latency impact.

## 5. MAT: tracing Path to GC Roots properly

**Eclipse Memory Analyzer (MAT)** is a popular tool for opening `.hprof` files and finding objects retaining memory. How to investigate:

1. Open `loader-before.hprof` in MAT.
2. Go to **Histogram** or **Class Loader Explorer** to find `java.net.URLClassLoader`, a custom `PluginClassLoader`, or a plugin class such as `demo.plugin.Payload`.
3. Filter instances of the suspect plugin class or loader, and inspect their fields and retained/shallow sizes.
4. On the loader or instance, select **Path To GC Roots**, preferring the **exclude weak/soft/phantom references** option when looking for a **strong retention path**.
5. Read the **ownership chain** back to the GC root. For example, `system-loaded HostRegistry.static CACHE → HashMap entry → plugin instance → class/loader`.
6. Use the **Dominator Tree** to see which object is the accumulation point. A dominator is not necessarily the object at the start of a shortest GC-root path; retained heap must be interpreted according to its exact definition.
7. Compare with `loader-after.hprof` and the actual post-cleanup state to see whether the holder still exists or has been removed.
8. Tie the finding back to registration/initialization code and the **cleanup hook**, rather than merely reporting “URLClassLoader is still alive”.

### Path to GC Roots is not a “call path”

`Path to GC Roots` is a **reference graph to the object**, not a stack trace telling you which file/line created the loader. A heap dump **does not by itself provide a complete allocation history**. To know “who created the object,” you need a JFR allocation stack/profiler or logging/instrumentation from creation time.

A simplified reference path in MAT might look like:

~~~text
GC Root: class of LoaderRetentionDemo (system loader)
    |
    v
static HOST_CACHE
    |
    v
java.util.HashMap
    |
    v
HashMap$Node.value
    |
    v
demo.plugin.Payload instance
    |
    v
class demo.plugin.Payload
    |
    v
java.net.URLClassLoader
~~~

**This is an explanatory diagram**; the MAT UI may arrange nodes or represent Class/loader edges differently depending on the version. The key point is that **the host static cache retains the plugin instance**, and the plugin instance prevents the defining loader from being collected.

### Questions to answer after each root path

- **Who owns the root?** A system class/static field, a live thread, a native/JNI reference, or a framework object?
- **Is the relationship strong or weak/soft?** A weak reference is not proof that it keeps the referent alive indefinitely.
- **Is the path valid according to the lifecycle?** If the plugin is still active, the cache's existence may be legitimate. If the plugin has been undeployed, you must explain why the holder was not cleaned up.
- **Are there multiple other paths?** Clearing one cache while leaving a TCCL/thread pool or listener intact will not release the loader.
- **Are there any classes/instances/references from an older version?** Comparing only the binary name is not enough; compare the **defining loader identity** and deployment marker.
- **Are there any JNI/global references or active frames?** Paths outside ordinary Java fields can also retain a classloader.

## 6. Self-contained Java 17 example: host static cache retains a plugin class loader

The following program creates `demo.plugin.Payload` using the JDK's `JavaCompiler`, loads the class with a **new URLClassLoader**, creates a plugin instance, and puts that instance into a **static Map on the host class**. It intentionally retains the loader via the instance so you can observe it with JFR and MAT.

To avoid using `System.gc()` as a test condition, stdout only verifies **things Java guarantees**: the loader defined the class, the cache has one entry, the weak reference still has its referent **while the cache strongly retains it**, and the cache is empty after `clear()`. The program **does not claim that the loader unloaded immediately after clear**, because the actual decision belongs to the GC/JVM.

### Single file: LoaderRetentionDemo.java

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LoaderRetentionDemo {
    private static final Map<String, Object> HOST_CACHE = new HashMap<>();

    private static Path compilePlugin() throws Exception {
        Path root = Files.createTempDirectory("loader-retention-");
        Path src = root.resolve("src/demo/plugin/Payload.java");
        Path classes = root.resolve("classes");

        Files.createDirectories(src.getParent());
        Files.createDirectories(classes);
        Files.writeString(src,
                "package demo.plugin; " +
                "public final class Payload { " +
                "public String id() { return \"plugin\"; } }");

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK");
        }

        int status = compiler.run(null, null, null,
                "--release", "17",
                "-d", classes.toString(), src.toString());

        if (status != 0) {
            throw new IllegalStateException("Plugin compilation failed");
        }
        return classes;
    }

    private static WeakReference<ClassLoader> install(Path classes)
            throws Exception {
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { classes.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> type =
                    pluginLoader.loadClass("demo.plugin.Payload");
            Object instance =
                    type.getDeclaredConstructor().newInstance();

            HOST_CACHE.put("plugin", instance);

            System.out.println("Plugin class: " + type.getName());
            System.out.println("Defined by child: "
                    + (type.getClassLoader() == pluginLoader));

            return new WeakReference<>(pluginLoader);
        }
    }

    public static void main(String[] args) throws Exception {
        Path classes = compilePlugin();
        BufferedReader console = new BufferedReader(
                new InputStreamReader(System.in));

        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Press ENTER to load plugin");
        console.readLine();

        WeakReference<ClassLoader> weak = install(classes);

        System.out.println("Cache entries before cleanup: "
                + HOST_CACHE.size());
        System.out.println("Loader reachable while cached: "
                + (weak.get() != null));

        System.out.println("Press ENTER to clear cache");
        console.readLine();

        HOST_CACHE.clear();
        System.out.println("Cache entries after cleanup: "
                + HOST_CACHE.size());

        System.out.println("Press ENTER to exit");
        console.readLine();
    }
}
~~~

**Compile and run on Java 17 or later:**

~~~bash
javac --release 17 LoaderRetentionDemo.java
java LoaderRetentionDemo
~~~

After each prompt, press **ENTER** once. `ProcessHandle.current().pid()` prints the actual process PID, so the first line **changes on every run**. The stable functional lines are:

~~~text
PID: <actual PID number>
Press ENTER to load plugin
Plugin class: demo.plugin.Payload
Defined by child: true
Cache entries before cleanup: 1
Loader reachable while cached: true
Press ENTER to clear cache
Cache entries after cleanup: 0
Press ENTER to exit
~~~

This is a **sample output with a single dynamic PID line**; the exact same PID number cannot be printed on every machine. The program was checked with `javac --release 17` and run on OpenJDK; `false` does not appear on the `Loader reachable while cached` line because the map holds a **strong reference** to the plugin instance.

### Why is this a retention example rather than merely keeping a local variable?

- `install(...)` creates the loader, loads the class, instantiates it, inserts the instance into **static `HOST_CACHE`**, and returns a **`WeakReference`**. When the method returns, the local variables `pluginLoader` and `type` are no longer in that stack frame.
- The `install` method uses `try-with-resources`, so `URLClassLoader.close()` has been called. However, `close()` does **not** release a defining loader that is still referenced by live classes/objects.
- `HOST_CACHE` resides on the **host/application class loader** and outlives the plugin. The `Payload` object is strongly held by the map, which in turn retains the corresponding class/loader.
- `WeakReference<ClassLoader>` held on `main`'s stack serves only as a **weak observer**. It **does not by itself keep the loader alive**. The value `weak.get() != null` while the cache holds the object is `true` by design.
- After `HOST_CACHE.clear()`, the retention path from the static map is removed. **There is no assertion yet that the loader will immediately disappear**: it still depends on GC and other references.
- Pausing with `BufferedReader.readLine()` gives you enough time to capture JFR/heap dumps in both phases. On PowerShell and Bash, use an interactive terminal to press ENTER; no background process is needed for multi-step input.

### Execution and evidence collection sequence

**Terminal A — run the demo.** The program prints the PID and pauses at `Press ENTER to load plugin`.

**Terminal B — start recording before loading the plugin:**

~~~bash
jcmd <PID> JFR.start name=loaderdiag settings=profile
~~~

Return to Terminal A and press ENTER **for the first time**. At this point, the plugin class is loaded and `HOST_CACHE` has one entry. Do not press ENTER a second time yet; keep the program paused at `Press ENTER to clear cache`.

**Terminal B — snapshot before cleanup:**

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.heap_dump loader-before.hprof
jcmd <PID> JFR.dump name=loaderdiag filename=loader-before.jfr
~~~

In MAT, open `loader-before.hprof` and find `demo.plugin.Payload` or its `java.net.URLClassLoader`. Following Path To GC Roots will show a path indicating that `LoaderRetentionDemo`'s static `HOST_CACHE` holds a `Payload` instance. Even if the tool models loader/class edges differently, you must still locate **the host cache as the strong holder**.

**Terminal A — press ENTER a second time** to clear the map, then keep the program at `Press ENTER to exit`.

**Terminal B — snapshot after cleanup:**

~~~bash
jcmd <PID> GC.heap_dump loader-after.hprof
jcmd <PID> VM.classloader_stats
jcmd <PID> JFR.dump name=loaderdiag filename=loader-after.jfr
~~~

Compare the HPROF, class loader statistics, and JFR recordings against the actual lifecycle. If the loader has become eligible for class unloading, an appropriate GC cycle can collect it; if unloading does not appear immediately, do not use that single result to conclude the fix failed. Re-check other roots, GC policy, and whether there are active stacks/plugin tasks.

Finally, press ENTER a third time to exit the demo. The temporary directory containing the dynamically generated ClassFile can be cleaned up separately; the program does not automatically delete source/class files created in the temp folder.

## 7. Practical MAT walkthrough with the example above

When opening `loader-before.hprof`:

1. **Histogram →** find `demo.plugin.Payload` and its instance.
2. Select that instance, view **Path To GC Roots**, and set **exclude weak/soft/phantom references** (per MAT's option).
3. Confirm a chain roughly like `LoaderRetentionDemo.HOST_CACHE → HashMap entry → Payload instance`. In MAT, there may be additional nodes for the class/static field.
4. Select `Payload`'s defining loader to inspect the classes it defines and their instance counts. There is only one `Payload` because the demo is simple, whereas the JVM may have many other loaders.
5. Inspect the **Dominator Tree** to understand which `HOST_CACHE`/holder dominates the object graph; note that retained heap does not necessarily represent all of Metaspace.
6. Open `loader-after.hprof`. Search again for `Payload` and the loader; if they were collected by GC, they may no longer appear in the live snapshot. If they still exist, request a **new Path To GC Roots** rather than assuming the old map still retains them.
7. Cross-check the results with the source: the direct reference path through `HOST_CACHE` is removed after `clear()`. The pre-cleanup dump proves the initial retention path; the post-cleanup dump helps check whether any other holder or unexpected retention remains.

### What if the loader is still in the heap after clear?

Different explanations:

- **No strong path remains**, but the snapshot includes unreachable objects due to dump options or GC mechanics; check how it was captured.
- **The JVM has not unloaded it yet** due to GC timing/class unloading policy; do not enforce an arbitrary self-imposed deadline.
- **A strong reference still exists** from a thread/TCCL, JNI, listener, class/instance, another cache, or instrumentation.
- **Different dump/loader instance**: there are multiple loaders of the same type/name, so you must cross-check identity, owner/class instances, and deployment id.

The decisive evidence is the **root path** and lifecycle. A standalone “metaspace has not decreased” statistic may be because the allocator is still holding committed memory or other classes are still loaded; do not claim a leak based solely on a single chart.

## 8. JFR + heap dump: how to read across a timeline

Suppose you re-run the plugin 5 times:

~~~text
T0: baseline after startup, loader count stable
T1: deploy #1 → loads 80 classes
T2: undeploy #1 → close resources, stop tasks
T3: deploy #2 → create new loader, load 80 classes
T4: undeploy #2 → ...
T5: after several appropriate GCs → measure live loaders/metaspace
~~~

Two scenarios:

**Expected scenario:** old loaders no longer have a strong path after undeploy; class unloading can occur after GC, and the number of live plugin loaders does not grow indefinitely with the number of deploy cycles.

**Suspected leak scenario:** each deploy creates a new loader; after undeploy, old loaders remain retained via a cache/thread root, the count of live loaders/classes per generation increases across multiple cycles, and there is no corresponding cleanup path.

However, **JFR does not by itself provide the final conclusion**. Increasing class loading metrics may simply be due to normal lazy startup; class unload events may be disabled. Therefore:

- Use **JFR** to pinpoint **when** load/redeploy/GC occurred and which changes look suspicious.
- Use **`VM.classloader_stats`** to see **which loaders** are still visible to the JVM and their class counts.
- Use **heap dump/MAT** to find **who retains** that specific loader.
- Use code/lifecycle logs to determine whether the holder is still valid or is a leak.
- Use **a repeatable scenario with matching comparison conditions** to evaluate the fix.

## 9. Misconceptions that lead to false conclusions

### 9.1. `System.gc()` ran and WeakReference is still non-null → definitely a leak

Incorrect. `System.gc()` does not guarantee that GC/class unloading will run by an expected deadline; in some environments, explicit GC can be disabled. A weak reference that still has its referent is not enough to conclude a leak; nor does a `null` weak reference prove that all resources/plugins have been properly cleaned up.

In the example, what is **certain** before cleanup is that `HOST_CACHE` strongly retains the instance. After cleanup, verify via root paths/live set in dumps and across multiple appropriate cycles, rather than arbitrarily printing an `unloaded=true` line.

### 9.2. `URLClassLoader.close()` succeeded → the loader unloads

False. `close()` releases the associated resource handles; **it does not delete** still-reachable Class/instance/method handles. The demo closes the loader in `install`, yet the static cache still retains the class loader.

### 9.3. A heap dump only contains the heap, so class loaders cannot be investigated

Incorrect. HPROF and MAT can represent `ClassLoader` objects, `Class<?>`, static fields, and the corresponding reference paths; MAT also models class→loader relationships. However, a heap dump **does not measure all Metaspace/native memory as heap bytes**. You need to use JFR/stats/metaspace tools when analyzing the native side.

### 9.4. A loader's retained heap = the loader's entire Metaspace

False. **Retained heap** is a metric over the Java heap object graph; much class metadata lives in native Metaspace. A loader instance with a small shallow size can still be associated with significant class metadata and references.

### 9.5. `JFR.dump` shows no ClassUnload = no unloading occurred

False if the `jdk.ClassUnload` event was not enabled, the recording did not cover the time when unloading occurred, or the JVM had not yet run GC during the observation window. Check the event configuration and timeframe before drawing conclusions.

### 9.6. Post-cleanup heap snapshot still has Payload → cache was not cleared

Not necessarily. The object might still be held by another root, the dump might have used `-all`, an active frame might still exist, or GC might not have collected it yet. Do not skip `Path To GC Roots`.

### 9.7. ThreadLocal has weak keys, so leaks disappear automatically

False. A long-lived worker thread can strongly retain the value even if the weak key is cleaned up later. Cleanup must run in the right thread context and be tied to the task/deployment lifecycle.

### 9.8. Simply increasing Metaspace is a fix

No. Increasing `-XX:MaxMetaspaceSize` may delay the error, but it does not remove root references. If the leak grows with every redeploy, it will still accumulate after enough cycles.

## 10. Controlled production diagnostic workflow

1. **Identify measurable symptoms:** loader instances, class counts, Metaspace committed/used, redeploy rate, GC/unloading logs, or OOME stack/cause.
2. **Confirm timing and scope:** which JVM, which application/deployment, which plugin owns the loader, and whether it is from before or after undeploy.
3. **Capture a JFR recording** early enough, choosing `default`/`profile` or an appropriate custom `.jfc`; know which events are enabled.
4. **Use `VM.classloader_stats`** (and optionally `VM.metaspace` depending on HotSpot/JDK) to get a per-loader overview.
5. **Choose a safe time for a heap dump:** ensure sufficient disk space, pause budget, and privacy controls; account for full GC impact; record the JVM build/flags.
6. **In MAT**, locate loaders/objects from old deployments, and inspect Path To GC Roots excluding weak refs and the Dominator Tree.
7. **Identify the root holder**: static cache, TCCL, ThreadLocal, service registry, listener, JNI global, active frame, or task queue.
8. **Fix at the lifecycle boundary:** unregister, call `ThreadLocal.remove()`, restore TCCL with `finally`, shut down executors, cancel delayed tasks, clear maps/registries, and close loader resources.
9. **Re-measure across multiple deploy/undeploy cycles**, comparing snapshots and JFR stats against a baseline with the same workload. Do not expect “GC must unload immediately after calling `clear`”.
10. **Report with evidence:** GC-root path before the fix, root path after the fix, classloader stats/timeline, test conditions, operational cost, and limitations of the conclusions.

### Pattern for handling TCCL in a worker

This is a **fragment** applicable when a task genuinely needs the plugin loader (the `pluginLoader`/`task` variables are already declared):

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

thread.setContextClassLoader(pluginLoader);
try {
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

TCCL is **state belonging to the running thread**, not automatically propagated by an executor per `submit`. The pattern above prevents a host worker from retaining the plugin TCCL after the task; however, if the task also writes a ThreadLocal or registers a listener, those must still be cleaned up separately.

## 11. Self-check questions

**Question 1.** Does a successful `URLClassLoader.close()` call mean the loader is immediately garbage-collected?

**Answer:** No. It closes the loader's resource handles; the loader/classes/instances may still be reachable from a root.

**Question 2.** A host static map retains a plugin instance. Why can the plugin loader remain alive?

**Answer:** The instance has an associated defining class and loader; the map strongly holds the instance via a host GC root, so the class/loader are not eligible for unloading.

**Question 3.** Does the absence of `jdk.ClassUnload` events in `JFR.dump` prove that no unloading occurred?

**Answer:** No. The event might not have been enabled, or the recording might not have covered the relevant time; check the `.jfc` and `jfr summary`.

**Question 4.** How does a heap dump differ from JFR?

**Answer:** A heap dump is a snapshot of the object graph/GC roots at a point in time; JFR is an event timeline/sampling. Combine both sources to learn both “when” and “what retains it.”

**Question 5.** What question does MAT's `Path To GC Roots` answer?

**Answer:** The chain of objects/references/roots **currently keeping the object alive**, not by default the stack trace where the object was created.

**Question 6.** Why should weak/soft/phantom references be excluded when searching for a leak via a strong path?

**Answer:** Weak/soft/phantom reference paths do not have the same retention semantics as strong references; excluding them helps focus on the strong holders that require cleanup.

**Question 7.** Why is an increase in `Metaspace used` not sufficient to conclude a classloader leak?

**Answer:** It could be due to normal class loading, the JIT/JVM allocator, workload, or GC timing; you need evidence from loader generations and root paths still existing after the lifecycle ends.

**Question 8.** After clearing the cache, a worker still has TCCL=OldPluginLoader. Is the fix complete?

**Answer:** Not yet. TCCL is a strong reference from a live thread; it must be restored/cleaned up at the task boundary, or the worker must be terminated appropriately.

## Key takeaways

**A class loader leak is a reachability and lifecycle problem, not merely a heap byte count or a `close()` call.** JFR gives the load/unload/GC timeline, `VM.classloader_stats` gives a loader/class snapshot, a heap dump gives the object graph, and MAT **Path To GC Roots** points out the strong holder keeping the loader/instance alive. Do not treat the absence of a JFR event, one-time Metaspace growth, or a single `System.gc()` call as decisive evidence. Find the **retention path**, tie it to ended business logic, remove the right references, and re-measure across multiple deploy/undeploy cycles.

**Official documentation and reference tools:**

- Oracle Java SE 17, `jcmd` (JFR.start/JFR.dump/GC.heap_dump/VM.classloader_stats): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java SE 17, `jfr` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle Java SE 17, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Oracle Java SE 17, `URLClassLoader.close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- OpenJDK/Java learning, JFR configuration: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/
- Eclipse Memory Analyzer, *Basic Tutorial* — Dominator Tree and Path to GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse MAT, *Path to GC Roots* and excluding weak references: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html
