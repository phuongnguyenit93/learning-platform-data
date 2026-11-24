# 17.8 ClassLoadingMXBean, VM.classloader_stats, and Class Load or Unload Logs

## Learning Objectives

In Java, **class loading** happens when the JVM needs to define a class. For long-running applications, the number of loaded classes, the number of class loaders, and the ability to perform **class unloading** can directly affect startup speed, plugin/hot-reload mechanisms, dynamic proxy/lambda generation, and **Metaspace** usage. However, "class count rising" **does not automatically mean a memory leak**.

This lesson provides a unified diagnostic workflow using three types of evidence:

1. **`ClassLoadingMXBean`**: JVM-level counters — how many classes are currently loaded, total loaded since startup, and total unloaded since startup.
2. **`jcmd <pid> VM.classloader_stats`**: a detailed snapshot per class loader and ClassLoaderData, including class counts and metaspace chunk/block information.
3. **Unified logging `class+load` / `class+unload`**: an event timeline — which classes were loaded or unloaded, when, and sometimes from which source.

Upon completing this lesson, you will be able to read the metrics accurately, enable logging at an appropriate level, run a Java 17+ experiment with multiple `URLClassLoader`s, detect class-loader retention trends, and distinguish legitimate class-loading churn from a potential leak.

**Scope:** The `ClassLoadingMXBean` API belongs to Java SE (module `java.management`). The `VM.classloader_stats`, `VM.log`, and `-Xlog` commands are illustrated on **HotSpot/OpenJDK 17+**; results, column names, and command availability depend on JDK and environment. Examples were compiled with `javac --release 17` and run on HotSpot JDK 24. Do not assume every JVM provides the exact same HotSpot commands.

## 1. Nature of Class Loading and Class Unloading

### 1.1 A Class Name Alone Cannot Identify a Runtime Class

In the JVM, a class's identity is fundamentally tied to its **binary name** and **its defining class loader**. Two different class loaders can define two classes with the exact same name `lab.PluginThing`, yet they are **two distinct runtime classes** with separate metadata and cannot be cast to one another merely because their names match.

An application may use:

- **Bootstrap class loader** to load core classes of the Java runtime.
- **Platform class loader** for appropriate platform modules.
- **Application class loader** for the standard class path or module path.
- **Custom class loaders** such as `URLClassLoader`, application-server loaders, plugin systems, framework code generation, or hot-reload environments.

Loaders typically follow parent delegation; some use custom strategies. When analyzing, distinguish **loader type** (`URLClassLoader`, `AppClassLoader`, …), **individual loader instances**, and the classes defined by each loader. "Loading the same name again" can be normal if a different loader defines it, yet worth investigating if loaders keep getting created without being freed.

### 1.2 Distinct Steps — Do Not Call All of Them "Load"

A high-level view:

~~~text
JVM asks a class loader to define a class
                   |
                 Loading
                   |
           Linking (verify,
         prepare, resolve if needed)
                   |
          Initialization when
           conditions require
                   |
           Used at runtime
                   |
    Loader and its classes are no longer
     kept alive per GC reachability rules
                   |
       Class unloading may occur when
       JVM/GC supports and chooses to
~~~

- **Loading**: locating/reading the class representation and creating its definition in the JVM.
- **Linking**: includes verification, preparation, and resolution (resolution timing can vary).
- **Initialization**: runs static initialization logic if needed; class loading **does not** immediately run static initializers in every context.
- **Unloading**: reclaims class metadata when reachability conditions and JVM/GC policies permit; does not happen the instant a variable pointing to the loader goes out of scope.

`Class.forName("pkg.Name", true, loader)` can trigger class initialization. Ordinary `ClassLoader.loadClass(...)` does not necessarily trigger initialization eagerly. Do not conclude from a `class,load` log line alone that the static initializer ran or that the class will live forever.

### 1.3 Relation to Metaspace and Heap

HotSpot class metadata lives in native structures, notably Metaspace (and compressed class space depending on configuration). Meanwhile, `ClassLoader` objects, `java.lang.Class` mirrors, and many application references live as Java/heap objects. A retained loader can indirectly retain metadata for a large number of classes.

**However:** `ClassLoadingMXBean.getLoadedClassCount()` does not report Metaspace size in bytes, and `VM.classloader_stats` does not directly measure retained heap across all objects belonging to a loader. Proving a leak requires combining class-loader, memory, and retaining-reference evidence.

## 2. Choose the Tool by Diagnostic Question

| Question | Primary Tool | Key Data | Does Not Answer Directly |
| --- | --- | --- | --- |
| Is total currently loaded class count rising over time? | `ClassLoadingMXBean` | `loadedClassCount` | Which loader holds them, total bytes |
| Is the class creation / unload rate high? | Periodic `ClassLoadingMXBean` reads | Deltas of `totalLoaded` and `unloaded` over time | Individual class names or call sites |
| Which loader holds many classes, and is loader count growing? | `VM.classloader_stats` | Loader, parent, CLD, classes, chunk/block stats | Full GC roots of the loader |
| Which class was loaded, from where, and when? | `-Xlog:class+load=info` | Class-load timeline | Why the app requested the class |
| Which classes were actually unloaded? | `-Xlog:class+unload=info` | Timeline of actual class unloads | Why GC did or did not run |
| How much Metaspace is reserved/committed/used? | `jcmd <pid> VM.metaspace` and memory metrics | Metaspace metrics | All referents keeping a loader alive |
| Why is the loader still reachable? | Heap dump, reference paths, thread/context loaders, framework metrics | Strong reference chains | Cannot be inferred from class-loading counters alone |

**Approach:** measure **overall trend** with the MXBean, find **loader distribution** with `VM.classloader_stats`, and inspect **specific events** via logs. Move to heap dumps/reference analysis only once you have a clear retention hypothesis.

## 3. `ClassLoadingMXBean`: Three Core Counters

### 3.1 Accessing the Standard API

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
int current = bean.getLoadedClassCount();
long total = bean.getTotalLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

This is a **snippet** for use inside a Java method, not a standalone program; the runnable example is in Section 7. A JVM has **one** MXBean managing class loading, accessible in-process via `ManagementFactory` or via the JMX platform MBeanServer using ObjectName:

~~~text
java.lang:type=ClassLoading
~~~

The three metrics have exact meanings:

| Method | Type | Interpretation | Typical Trend |
| --- | --- | --- | --- |
| `getLoadedClassCount()` | `int` | Classes currently loaded at measurement time | Rises, drops, or stays steady |
| `getTotalLoadedClassCount()` | `long` | Total classes ever loaded **since JVM startup** | Non-decreasing |
| `getUnloadedClassCount()` | `long` | Total classes unloaded **since JVM startup** | Non-decreasing |

**Do not** read `getTotalLoadedClassCount()` as "number of classes currently consuming memory." It is a cumulative counter. If an app creates and unloads 10,000 classes during the day, total can climb by 10,000 while live loaded classes at end of day remain nearly unchanged.

Values can change while reading each getter. Three sequential calls are **not an atomic snapshot** at a single instant; do not demand that an arithmetic identity across the three numbers hold down to the exact class during concurrent loading/unloading.

### 3.2 Example Reading Deltas Over Time

Suppose two samples on **the same JVM** are spaced exactly 60 seconds apart:

| Metric | At `t0` | At `t1` | Delta |
| --- | ---: | ---: | ---: |
| `getLoadedClassCount()` | 8,200 | 8,280 | +80 |
| `getTotalLoadedClassCount()` | 12,000 | 12,500 | +500 |
| `getUnloadedClassCount()` | 3,800 | 4,220 | +420 |

In this window, the JVM loaded about **500 additional classes**, unloaded **420 classes**, and currently loaded classes rose by **80**. Average load rate is roughly **8.33 classes/s**; average unload rate is **7 classes/s**. These are **hypothetical figures for practicing interpretation**, not a standard baseline.

An approximation:

~~~text
load_rate ≈ (totalLoaded(t1) - totalLoaded(t0)) / (t1 - t0)
unload_rate ≈ (unloaded(t1) - unloaded(t0)) / (t1 - t0)
net_loaded_change = loadedNow(t1) - loadedNow(t0)
~~~

You need the same process and the real elapsed interval, ideally from a monotonic clock. Never subtract across two JVMs with different PIDs/restarts and call it a rate. After a restart, cumulative counters reset.

**Initial classification:**

- **Total rises, unloaded rises correspondingly, current stays relatively flat:** **class loading churn**. May be legitimate work (plugins/tests/jobs) or overly frequent dynamic class generation causing CPU/GC overhead; does not yet prove a leak.
- **Total rises, current rises persistently, unloaded barely moves:** suspect retained class loaders/definitions or not yet reaching an appropriate GC cycle. Check loader counts, runtime duration, and Metaspace; do not jump to "leak."
- **Current climbs sharply at startup then flattens:** likely lazy loading, JIT/framework warmup, loading long-lived classes/structures; can be completely normal.
- **Unloaded jumps in bursts after GC:** class unloading tied to GC cycles; do not expect continuous per-second unloading.

### 3.3 `isVerbose()` and `setVerbose(boolean)`

`ClassLoadingMXBean` also provides:

~~~java
boolean enabled = bean.isVerbose();
bean.setVerbose(true);
~~~

This is only a **snippet**. Per the Java API, verbose output and destination stream are implementation-dependent; `setVerbose` toggles **globally** in the JVM and can be called by multiple threads. Therefore **do not call `setVerbose(true)` unconditionally in production**, especially when a service loads many classes.

On modern HotSpot, **Unified Logging with `-Xlog`** is usually more suitable because you can choose tags, levels, output targets, decorators, and file rotation. Use the MXBean primarily to **read metrics** rather than mutating global logging state. If the system already has a logging policy, do not arbitrarily flip `setVerbose(false)` to "reset" it: that can conflict with diagnostics from another component.

### 3.4 Reading via JMX Without Embedding Code

Like other standard MXBeans, this bean can be observed through an appropriate JMX channel, such as JConsole/JMC or a metrics bridge. The ObjectName is `java.lang:type=ClassLoading` and attributes correspond to getters. Ensure proper JMX configuration and access control; **never expose remote JMX to a public network just to read class counts**.

When exporting metrics to dashboards, include PID/JVM start time in labels or metadata to distinguish restarts, and take rates from cumulative counters instead of graphing `totalLoaded` as "currently loaded."

## 4. `jcmd VM.classloader_stats`: From Total Class Count to Specific Loaders

`VM.classloader_stats` is a HotSpot diagnostic command that prints statistics for existing class loaders. It is especially useful when `current` grows abnormally and you suspect a framework creates a new class loader per deploy/plugin/job.

### 4.1 Identify the PID and Run the Command

~~~sh
# Run on the same host/namespace and with permissions to attach to the JVM:
jcmd -l

# Replace <pid> with the actual Java process PID:
jcmd <pid> VM.classloader_stats

# Check syntax/impact directly on the target JVM:
jcmd <pid> help VM.classloader_stats
~~~

`jcmd` normally ships with the JDK. If attach fails, verify the process owner user, namespace/container, JDK path, whether `-XX:+DisableAttachMechanism` is enabled, and whether the PID still exists. Never use another service's PID just because its name looks similar.

Oracle documentation lists `VM.classloader_stats` as low impact, yet in systems with very many loaders/classes under latency-sensitive load, collect it judiciously. It is a **snapshot**, not an event stream, and shows no history for already-unloaded loaders.

### 4.2 Reading Real Output Examples

On HotSpot JDK 24, when a Java demo holds three live `URLClassLoader`s, part of the report looks like:

~~~text
ClassLoader         Parent              CLD*               Classes   ChunkSz   BlockSz  Type
0x...               0x...               0x...                    1      2048      1288  java.net.URLClassLoader
0x...               0x...               0x...                    1      6144      1288  java.net.URLClassLoader
0x...               0x...               0x...                    1      5120      1288  java.net.URLClassLoader
0x...               0x...               0x...                  852    ...       ...     <boot class loader>
...
Total = 6                                                   ...     ...       ...
ChunkSz: Total size of all allocated metaspace chunks
BlockSz: Total size of all allocated metaspace blocks (each chunk has several blocks)
~~~

This is an **illustrative excerpt from one run**, with addresses, some rows, and numbers abbreviated; it is not a fixed result to compare across all JDKs. `Total = 6` in the original example counts reported class loader/data entries, not total Java classes; total classes are in another column. A report may also have separate entries for hidden classes, bootstrap, or loaders with `Classes=0`.

Reading the columns:

| Column | Meaning | Avoid |
| --- | --- | --- |
| `ClassLoader` | Internal HotSpot address/identifier for the loader | Do not use as a business ID or compare directly across restarts |
| `Parent` | Internal parent loader information | Do not assert application relationships from a hex number alone |
| `CLD*` | Native ClassLoaderData identifier linking loader ↔ metadata | Do not confuse with the heap address of the `ClassLoader` object |
| `Classes` | Number of classes counted in that loader entry | Not the count of Java object instances |
| `ChunkSz` | Total size of **metaspace chunks** allocated for that entry | Not live Java heap bytes |
| `BlockSz` | Total size of **metaspace blocks** inside chunks for that entry | Not "object count"; a chunk can contain multiple blocks |
| `Type` | Loader type, e.g., `java.net.URLClassLoader` | Multiple instances can share the same Type name |

Units and formatting of sizes can vary across JDKs; read the legend at the bottom of the report and **do not assume KB or MB**. The `Classes` column can include categories shown separately by the JVM such as hidden classes. The sum across loaders should not be mechanically equated to `ClassLoadingMXBean.getLoadedClassCount()` because snapshot timing, hidden/array-class accounting, and concurrent class loading can differ.

### 4.3 Spotting Signals Worth Investigating

At **two checkpoints under equal load after warmup**, you see `java.net.URLClassLoader` or custom loaders jump from 20 to 200 even though the app has only 20 fixed plugins. This is a strong cue to ask:

- Does each reload/deploy create a new loader while retaining the old one?
- Does any thread or thread pool still hold a `contextClassLoader` pointing to an old loader?
- Does a static cache, singleton, listener, service registry, timer, MBean, JDBC driver, thread local, or reflective method reference hold a class or loader?
- Does the loader still own classes it defined, and does metaspace for them grow accordingly?
- After churn stops and GC/class unloading runs, does loader count drop?

**Do not infer a leak from one large `ChunkSz` column.** Chunks are Metaspace management units; size can be large due to legitimate loader allocations, fragmentation, or internal structures. You need trends, lifetimes, and retaining reference paths.

### 4.4 Pairing with Other Commands When Needed

~~~sh
# Metaspace summary on supporting HotSpot:
jcmd <pid> VM.metaspace basic

# Detailed Metaspace report and/or per-loader breakdown:
jcmd <pid> VM.metaspace show-loaders

# Inspect loader hierarchy on supporting HotSpot builds:
jcmd <pid> VM.classloaders
~~~

`VM.metaspace` shows reserved/committed/used bytes and native structural details; `VM.classloaders` focuses on loader trees/relationships. These commands **supplement** `VM.classloader_stats`; they do not by themselves find a loader's GC roots. On different JDKs, run `jcmd <pid> help VM.metaspace` or `help VM.classloaders` before using options.

To compare VM footprint within Native Memory Tracking, you can use `VM.native_memory summary` **only if NMT was enabled at JVM startup**. Never mix `ClassLoadingMXBean` class counts with native bytes without a dedicated metric.

## 5. Unified Logging: Observing Class Load and Unload Over Time

Since JDK 9, HotSpot supports **Unified Logging `-Xlog`**. This is a convenient way to record timestamped load/unload events. With JDK 17+:

~~~sh
# Capture class load and class unload into a file:
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' -jar app.jar
~~~

`app.jar` is illustrative; replace with your real JAR. In shells supporting quoting, the entire `-Xlog:...` is **one JVM argument** and must appear **before `-jar`**. In Windows PowerShell, use single quotes as shown; in Windows CMD, adjust quoting accordingly. In Docker, the file is written in the JVM process's filesystem (often inside the container).

Two key tags:

- **`class+load=info`:** logs when HotSpot loads a class, typically including class name, source/module, and timestamps per decorators.
- **`class+unload=info`:** logs when a class is actually unloaded. Absence of events means no unload was observed in **the captured log window**; it does not mean GC or unloading is "broken."

You can bound log files with rotation where supported by the JDK:

~~~sh
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags:filecount=3,filesize=5M' -jar app.jar
~~~

The command above uses **colon-separated sections** after `-Xlog`: selection → output → decorators → output options (including filecount/filesize). This syntax was verified on HotSpot JDK 24. Rolling files can drop older class-load events; when investigating rare incidents, align retention strategy with reproduction time.

### 5.1 Example Load Log

In the Section 7 experiment, after running three distinct loaders, the file contains three lines like:

~~~text
[0.072s][info][class,load] lab.PluginThing source: file:/.../plugin/
[0.075s][info][class,load] lab.PluginThing source: file:/.../plugin/
[0.076s][info][class,load] lab.PluginThing source: file:/.../plugin/
~~~

Timestamps, paths, and addresses depend on the **machine/run**; the key point is **three loads of the same name `lab.PluginThing`** defined by three separate loaders. Seeing the same name three times does not prove a leak: the experiment program **intentionally** creates three loaders.

Note: `class+load` events do not necessarily print loader identity in a way that distinguishes each instance at `info` level. Pair with `VM.classloader_stats` and capture timestamps, or use more detailed logging when needed and overhead is acceptable. `source: file:/...` is the class code source, **not a GC root** or proof the loader will stay alive forever.

### 5.2 Why Might Unload Logs Be Absent?

Unloading is not a file-close call; it involves **class loader reachability** and GC mechanics. Possible reasons:

1. The loader is still held by a static map/list, a thread's TCCL, JMX/listeners, scheduled tasks, callbacks, or objects/classes from the loader itself.
2. Workload is still using the class or loader, with live stack/object references.
3. No suitable GC/class-unloading cycle has occurred yet; GC may be deferred.
4. JVM/collector flags or VM mode currently disable class unloading.
5. Logging was enabled after unloading already happened, logs rotated/truncated, or event filters are wrong.

**`URLClassLoader.close()` only closes resources opened by the loader; it does not force the JVM to unload classes.** Likewise, setting a variable to `null` removes only one reference edge and does not prove the object is unreachable. `System.gc()` or `jcmd <pid> GC.run` are experimental requests that can cause pauses and **do not guarantee** all eligible classes unload immediately.

### 5.3 Enabling Logging on an Already-Running JVM

On HotSpot supporting the `VM.log` diagnostic command, inspect the current setup:

~~~sh
jcmd <pid> VM.log list
jcmd <pid> help VM.log
~~~

An example enabling logs to the target JVM's console output:

~~~sh
jcmd <pid> VM.log what=class+load=info,class+unload=info output=stdout decorators=uptime,level,tags
~~~

This command was tested on HotSpot JDK 24 and returned `Command executed successfully`. **Caution:** it modifies the logging configuration of **the target JVM**, rather than printing logs into the terminal running `jcmd`. In containers/servers, JVM `stdout` may flow into another log pipeline, and changing outputs can interact with existing log configs. Record `VM.log list` state beforehand and plan exact restoration without inadvertently disabling other system logs. For controlled reproductions, enabling `-Xlog` at startup is usually easier to track and manage.

### 5.4 Levels and Operational Cost

`info` is usually sufficient to see class names and load/unload timestamps. `debug`/`trace` on some tags can produce huge logs, increase I/O, and add noise. Do not turn on `-Xlog:class*=trace` broadly in production when you only need to confirm a few extra loaders. Use file rotation, bounded capture windows, disk-space checks, and protect paths if module/class/source names are sensitive.

## 6. Distinguishing Churn, Retention, and Leaks with Evidence

### 6.1 Class Loading Churn (Frequent Creation/Unloading)

Suppose a service continuously compiles rule expressions or generates dynamic proxies. `totalLoaded` climbs quickly; after GC cycles, `unloaded` also climbs; `current` fluctuates around a band. Frequent load/unload logs for the same class names across different loaders may accompany it.

Impacts can include CPU for verification/linking/initialization, metadata allocation, GC class unloading, and JIT caches invalidated when loaders vanish. This can be a **performance problem** even without a memory leak. Ask: can loaders/generated classes/caches be reused safely? Is class generation cost significant in CPU profiles or startup logs?

### 6.2 Class Loader Retention

If an app redeploys 10 times and retains 10 old loaders, each loader can hold many class definitions, static data, and attached objects. `current` climbs or plateaus high; `VM.classloader_stats` shows loaders from old deployments still alive; Metaspace may grow without sufficient reclamation.

Common loader-retention paths:

~~~text
GC roots (static fields, live threads, native references...)
                       |
             App singleton / cache
                       |
             plugin Class<?> / instance
                       |
                ClassLoader
                       |
             Loaded classes / metadata
~~~

Or:

~~~text
Live worker thread
        |
thread context class loader (TCCL)
        |
Old webapp/plugin class loader
        |
Metadata + classes belonging to old deployment
~~~

These are **illustrative models**; actual reference paths must be verified with heap dumps/GC roots. Never assume every `ThreadLocal` or singleton retains a loader if those objects are no longer relevant. Nor call it a leak merely because an active plugin's loader is still needed for legitimate work.

### 6.3 Normal Class Unloading

If an app shuts down a plugin, drops all references to its loader/classes/instances, and undergoes a GC supporting unloading, `class,unload` logs may appear, `unloaded` rises, and `current` may drop. Still:

- Not every GC cycle unloads classes.
- JVM committed Metaspace may not shrink immediately even after classes unload, due to chunk management or retention.
- Some classes shared/loaded by platform loaders have lifetimes matching the JVM and are not expected to unload before exit.

Not seeing `class,unload` over a short window is **insufficient** to claim a leak.

## 7. Java 17+ Hands-On: Three Class Loaders Defining the Same Class

This experiment uses two Java files, compiles a plugin class into a separate folder, and loads `lab.PluginThing` using **three `URLClassLoader` instances** whose parent is the platform loader. The program holds the three loaders in a list so you can inspect `VM.classloader_stats`, then releases references. Every component uses Java SE 17+ with zero external libraries.

### 7.1 Create the Plugin Class

Save **`PluginThing.java`**:

~~~java
package lab;

public final class PluginThing {
    public static String ping() {
        return "OK";
    }
}
~~~

Compile into the `plugin` directory (creating package subdirectories if needed):

~~~sh
javac --release 17 -d plugin PluginThing.java
~~~

After this command, the class file sits at `plugin/lab/PluginThing.class`. Do not add `plugin` to the main app's default classpath; in this example, **each `URLClassLoader`** loads the class from that directory's URL.

### 7.2 Program Using the MXBean and Custom Loaders

Save the file as **`LoaderDiagnosticsDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LoaderDiagnosticsDemo {
    private static final List<URLClassLoader> ACTIVE_LOADERS = new ArrayList<>();

    private static void metrics(String stage, ClassLoadingMXBean bean) {
        System.out.printf("%s current=%d total=%d unloaded=%d%n",
                stage, bean.getLoadedClassCount(),
                bean.getTotalLoadedClassCount(), bean.getUnloadedClassCount());
    }

    public static void main(String[] args) throws Exception {
        ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
        BufferedReader stdin = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        metrics("START", bean);
        System.out.println("READY_LOAD");
        stdin.readLine();

        URL classes = Path.of("plugin").toAbsolutePath().toUri().toURL();
        for (int i = 1; i <= 3; i++) {
            URLClassLoader loader = new URLClassLoader(
                    new URL[]{classes}, ClassLoader.getPlatformClassLoader());
            Class<?> type = Class.forName("lab.PluginThing", true, loader);
            String result = (String) type.getMethod("ping").invoke(null);
            ACTIVE_LOADERS.add(loader);
            System.out.println("LOADED_" + i + "=" + result);
        }
        metrics("AFTER_LOAD", bean);
        System.out.println("READY_RELEASE");
        stdin.readLine();

        for (URLClassLoader loader : ACTIVE_LOADERS) {
            loader.close();
        }
        ACTIVE_LOADERS.clear();
        System.out.println("REFERENCES_RELEASED");
        System.out.println("READY_EXIT");
        stdin.readLine();
    }
}
~~~

Explanation of key lines:

- `ManagementFactory.getClassLoadingMXBean()` reads JVM-wide class counts, **not just the classes of the three `URLClassLoader`s**.
- `getPlatformClassLoader()` serves as parent for platform classes; `plugin` is not on the application classpath, so `lab.PluginThing` is defined separately by each of the three custom loaders.
- `Class.forName(..., true, loader)` loads and initializes the class through that loader; `ping()` returns confirmation string `OK`.
- `ACTIVE_LOADERS` holds strong references so you are guaranteed to see three loaders at the measurement point.
- `loader.close()` closes file/URL resources; `ACTIVE_LOADERS.clear()` drops strong references held by this list. **Does not guarantee immediate unloading** because other references/stack liveness or GC timing may apply.

### 7.3 Run with Two Terminals and Measure Across Three Stages

**Terminal A**, in the folder with both source files (with `plugin` already compiled above):

~~~sh
javac --release 17 LoaderDiagnosticsDemo.java
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' LoaderDiagnosticsDemo
~~~

The program prints a line with variable numbers, then pauses at the prompt:

~~~text
START current=<JVM-dependent number> total=<JVM-dependent number> unloaded=<JVM-dependent number>
READY_LOAD
~~~

The line with angle brackets is an **output template, not fixed stdout**; the counters are real numbers from your running JVM. **Do not type the template text above**; just press Enter when ready to advance.

**Terminal B**, while Terminal A is waiting:

~~~sh
jcmd -l
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace basic
~~~

Record the loader count and metrics. Return to **Terminal A** and press **Enter the first time**. Java prints:

~~~text
LOADED_1=OK
LOADED_2=OK
LOADED_3=OK
AFTER_LOAD current=<JVM-dependent number> total=<JVM-dependent number> unloaded=<JVM-dependent number>
READY_RELEASE
~~~

Still in **Terminal B**, take the second snapshot:

~~~sh
jcmd <pid> VM.classloader_stats
~~~

Find the three `java.net.URLClassLoader` entries corresponding to the newly loaded classes. On the tested HotSpot JDK 24, the report showed **three `URLClassLoader` entries, each with `Classes=1`**. Platform loader counts, other class counts, chunks, and addresses vary by JVM. `ClassLoadingMXBean` also rises by more than three in the experiment because using MXBean/URL/reflective APIs lazily loads additional JDK classes.

Return to **Terminal A** and press **Enter the second time**. The program prints:

~~~text
REFERENCES_RELEASED
READY_EXIT
~~~

At this point `ACTIVE_LOADERS` is cleared and the `URLClassLoader`s have closed their resources. You can take another snapshot:

~~~sh
jcmd <pid> VM.classloader_stats
~~~

**Do not assume the `URLClassLoader` rows will disappear immediately.** One strong-reference source was removed, yet class unloading still depends on true reachability and GC. In this lab (not production), if you want to give GC a chance to run, you may invoke `jcmd <pid> GC.run` and re-measure; this command can cause a pause and **does not guarantee** unloading. In production, avoid calling `GC.run` just to make numbers look cleaner.

When finished, press **Enter the third time** in Terminal A to exit.

### 7.4 Read the Class Load Log

In Terminal A's working directory:

~~~sh
# Linux/macOS:
grep 'lab.PluginThing' class-events.log
~~~

Or with PowerShell:

~~~powershell
Select-String -Path class-events.log -Pattern 'lab.PluginThing'
~~~

On the tested HotSpot JDK 24, three `lab.PluginThing` load lines appear with sources pointing to the `plugin` directory. As noted, timestamps vary. If `[class,unload]` lines appear for this class, unloading genuinely occurred during capture; if not, you cannot conclude a loader leak from one short run.

### 7.5 Cross-Checking Verified Output

In a test run feeding three Enter newlines immediately so the program steps through all stages, the **fixed** confirmation lines in order are:

~~~text
READY_LOAD
LOADED_1=OK
LOADED_2=OK
LOADED_3=OK
READY_RELEASE
REFERENCES_RELEASED
READY_EXIT
~~~

Beyond those lines, two counter lines `START ...` and `AFTER_LOAD ...` print **machine/JVM-dependent values**. In one real run, for example, `START current=789 total=789 unloaded=0` and `AFTER_LOAD current=983 total=983 unloaded=0`; these are only **sample numbers from the test environment**, not fixed expectations. The experiment used `javac --release 17` and ran successfully on HotSpot JDK 24; file logging flags were also verified.

## 8. From Metrics to Hypotheses: Three Diagnostic Scenarios

### Scenario A — Sudden Startup Rise Followed by Stability

After startup, a service loads 2,000 more classes via frameworks, serializer caches, HTTP clients, and reflection. `current` climbs during the first few minutes and then plateaus; `VM.classloader_stats` shows the corresponding framework loaders. `class+load` logs many classes during warmup, yet loaders do not keep multiplying.

**Assessment:** likely normal lazy class loading. Set the baseline **after warmup** and keep measuring under steady traffic; do not declare a "leak" just because `totalLoaded` rose initially.

### Scenario B — Class Loading Churn in a Dynamic Rule Engine

Every second a service generates several short-lived proxy classes with dedicated loaders. After GC, `getUnloadedClassCount()` climbs steeply, `current` stays roughly flat, and old `URLClassLoader`s gradually vanish. Both `class+load` and `class+unload` logs are dense.

**Assessment:** likely not a leak, yet there is **CPU/GC/Metaspace churn cost**. Investigate where classes/loaders are generated and see if reasonable caching/reuse can replace continuous class generation; measure optimization impact under realistic workload.

### Scenario C — Class Loader Leak After Redeploy

After each redeploy, another set of old application loaders remains. `current` steps upward, `unloaded` barely moves across multiple appropriate GC cycles, `VM.classloader_stats` persistently shows loaders from old deployments, and `VM.metaspace` shows a growing footprint trend. A heap dump identifies a long-lived thread whose `contextClassLoader` still points to an old loader.

**Assessment:** evidence aligns with **loader retention/leak**. Remediation may include stopping threads on undeploy, restoring TCCL in scope, removing listeners/`ThreadLocal`s, clearing caches, or closing plugin lifecycles. Re-verify after the fix using the exact same metrics, not just a single drop in count.

## 9. Production Investigation Checklist

1. **Identify the exact JVM:** record PID, JVM start time, JDK version/vendor, GC, container state, and observation window. Separate restarts from counter movements.
2. **Capture baseline:** read `ClassLoadingMXBean` or JMX: current, total, unloaded. Record timestamp/load/concurrency and Metaspace used/committed.
3. **Measure over a window:** take readings post-warmup and after repeated workload; compute `load_rate` and `unload_rate` from cumulative counters.
4. **Narrow down loaders:** on the same PID, capture `VM.classloader_stats` several times. Inspect loader types, classes per entry, live loader count, `ChunkSz`/`BlockSz`, and trends.
5. **Enable targeted logs:** if you need class names or load/unload timestamps, use `class+load` and `class+unload` with bounded output/rotation around the symptom window.
6. **Form a concrete hypothesis:** e.g., "each hot deploy retains a `URLClassLoader` via an unstopped thread pool" rather than "Metaspace is leaking."
7. **Inspect roots:** use heap dumps/paths-to-GC-roots, thread dumps/TCCL, listeners, caches, and framework/plugin lifecycles. In latency-sensitive environments, weigh each diagnostic command's impact.
8. **Test fix and re-measure:** compare under equal load, JVM config, and warmup window; verify old loaders disappear once GC/unloading conditions are met, `current` stabilizes, and memory footprint stops climbing.

**Never declare a leak from a single `VM.classloader_stats` screenshot.** An application with 50,000 classes can be completely legitimate by runtime design, whereas one stale loader holding 100 unused classes can still be a lifecycle bug.

## 10. Common Pitfalls to Avoid

1. **Confusing `totalLoaded` with `current`.** A rising `totalLoaded` does not mean live loaded classes are growing.
2. **Interpreting `unloaded=0` over a few seconds as a GC bug.** Unloading only runs when conditions are met at appropriate times.
3. **Confusing `Classes` in `VM.classloader_stats` with object instance counts.** It counts class definitions per loader/CLD, not an object histogram.
4. **Reading `ChunkSz` as Java heap used or exact live Metaspace.** Cross-check `VM.metaspace` and HotSpot chunk/block allocation.
5. **Seeing the same class name load three times and calling it wasteful duplication.** Each may be a distinct class defined by a separate loader.
6. **Assuming `URLClassLoader.close()` or `null` assignment unloads classes.** `close()` frees loader resources; unloading requires reachability and GC.
7. **Calling `setVerbose(true)` and forgetting it is global.** Logs can explode and output depends on implementation.
8. **Using legacy flags like `-XX:+TraceClassLoading` on JDK 17+.** Modern HotSpot uses `-Xlog:class+load=info` and `class+unload=info`.
9. **Forgetting class-source logging was enabled too late.** Startup `-Xlog` records only after launch; dynamic `VM.log` does not retroactively log past loads.
10. **Forgetting log rotation.** Once files rotate, missing old events does not mean they never occurred.
11. **Comparing counters across different PIDs/JVMs.** Restarts reset counters; separate series per process.
12. **Concluding every `current` increase is a leak.** Lazy loading, proxies, generated classes, new plugins, and warmup can all be valid.
13. **Overlooking thread context class loaders.** Long-lived threads can pin old loaders even after requests/plugins finish.
14. **Repeatedly running `GC.run` in production to "force unloading."** It can cause pauses and offers no guarantee; observe natural GC cycles first.
15. **Enabling excessive logs and diagnostic commands that distort latency.** Choose the lowest detail sufficient to answer the question, capping file sizes and duration.

## 11. Exercises with Solutions

**Exercise 1.** `totalLoaded` rose by 4,000 over 1 hour, `unloaded` rose by 3,900, and `current` rose by only 100. Is this a memory leak?

**Solution:** Insufficient evidence. The data fits churn of ~4,000 loads / 3,900 unloads with net loaded classes up ~100. Monitor rate and CPU/GC cost, and inspect loader groups if `current` keeps climbing.

**Exercise 2.** `VM.classloader_stats` lists 40 `URLClassLoader`s, each with 10 classes. Has the tool proven 400 Java objects sit on the heap?

**Solution:** No. `Classes` is the number of class definitions per loader/CLD at snapshot time, not object instance count. To count/locate objects, use a profiler or heap dump/histogram, keeping in mind a loader holds metadata for various classes.

**Exercise 3.** You call `URLClassLoader.close()` and see no `[class,unload]` within 3 seconds. Conclusion?

**Solution:** Only that no unload was observed in those 3 seconds of logs. Strong references may remain, the loader may still be reachable, or an appropriate GC/unloading cycle has not run yet. Do not jump to a leak or JDK bug.

**Exercise 4.** `class,load` logs show `lab.PluginThing` loaded three times, yet the application does not have three different plugin types. What is worth checking?

**Solution:** Check which loader defined each class. Three independent loader instances may be loading the same name, as in the demo; if the app only needs one instance, that could be unnecessary churn. Use `VM.classloader_stats`/loader identity to distinguish, then inspect lifecycle management.

**Exercise 5.** A service has been up for 30 days and you need to know when `com.acme.DynamicRule` was first loaded. Logging is not currently enabled. Can `VM.classloader_stats` give you the exact timestamp history?

**Solution:** No. `VM.classloader_stats` gives only a current snapshot; `ClassLoadingMXBean` gives only total counters. You need logs/JFR/traces captured during that earlier window for historical timestamps. Enabling logging now will not reconstruct past events.

**Exercise 6.** After redeploying, currently loaded classes climb steadily, `VM.classloader_stats` shows multiple loaders from old deployments, and Metaspace grows. Next verification step?

**Solution:** Find **retaining reference paths keeping those class loaders alive** using a heap dump and GC roots—inspect threads/TCCL, static registries, listeners, timers, JDBC drivers, `ThreadLocal`s, or framework resources; confirm those loaders should have been unloaded. After fixing, re-measure under the same load across appropriate GC cycles.

## 12. Quick Command Cheat Sheet

~~~sh
# 1. Read current/total/unloaded with ClassLoadingMXBean
#    (via Java/JMX metrics, see Section 7 code)

# 2. Identify PID and capture loader snapshot:
jcmd -l
jcmd <pid> VM.classloader_stats

# 3. When memory detail is needed:
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.metaspace show-loaders

# 4. Log class load/unload from JVM startup:
java '-Xlog:class+load=info,class+unload=info:file=class-events.log:uptime,level,tags' -jar app.jar

# 5. If changing logging on a running JVM (controlled operation):
jcmd <pid> VM.log list
jcmd <pid> help VM.log
~~~

**Bottom line:** `ClassLoadingMXBean` gives **trends**, `VM.classloader_stats` gives **per-loader distribution**, and `class+load`/`class+unload` give the **event timeline**. Combining them with Metaspace and GC roots answers **why a loader stays alive**. Distinguish "lots loaded," "lots currently loaded," and "unloading hasn't run yet" before labeling anything a leak.

### Official References

- Oracle Java 21 API, `ClassLoadingMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle Java 21, `The jcmd Command` (including `VM.classloader_stats`, `VM.metaspace`, `VM.log`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 17, `The java Command` / Unified Logging / migrating `TraceClassLoading` to `-Xlog`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 22, `Troubleshooting Memory Leaks` (class loader statistics): https://docs.oracle.com/en/java/javase/22/troubleshoot/troubleshooting-memory-leaks.html
- Oracle Java 21 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
