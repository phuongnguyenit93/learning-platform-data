# Monitoring Class Loading, Unloading, and Loader Counts with JVM Diagnostic Tools

## 1. Why Monitor Class Loading in a Plugin System?

Every time a Java system finds, links, and defines a class, it can incur CPU, I/O, and metadata memory costs. In a plugin architecture, each plugin typically owns its own `ClassLoader` to isolate dependencies; during a hot reload, the old loader must have no remaining references so that the JVM can reclaim the classes that loader defined. If the old loader is still retained by a thread, listener, or cache, metaspace can grow steadily across repeated reloads.

Three metrics are frequently confused:

- **Loaded class count (live)**: the number of class metadata entries currently remaining or reported by the JVM at the time of observation.
- **Cumulative loaded/unloaded class counts**: counters that increase over time, useful for observing churn but not representing the live count.
- **Class loader count**: the number of loader objects or loader data structures currently alive in the JVM; not synonymous with the number of plugins or the number of classes.

For accurate diagnosis, you need to combine JVM unified logging, `jcmd`, and Java Flight Recorder (JFR). No single number alone is sufficient to prove a class loader leak.

## 2. Class Loading and Unloading Mechanics

A class in the JVM is identified by **binary name + defining class loader**. Therefore, two loaders can define two classes with the same name, yet the JVM still treats them as two distinct types. This allows plugin V1 and V2 to coexist simultaneously, while also risking a `ClassCastException` if an API contract is loaded redundantly.

Class unloading depends on reachability and garbage collector activity. In principle, the JVM can only reclaim class/loader metadata when the runtime's reachability and unloading conditions are satisfied. `URLClassLoader.close()` releases resources such as JAR handles; it **does not force the JVM to unload classes immediately**. `System.gc()` does not guarantee a full GC or unloading, especially if the runtime disables explicit GC or uses a different collector configuration.

Common reference sources that easily retain an old loader:

1. Running threads, `Thread.contextClassLoader`, or `ThreadLocal` values holding plugin classes/objects.
2. Host static collections and service registries storing `Class<?>`, provider instances, or callbacks.
3. Uncanceled executors, schedulers, timers, listeners, or shutdown hooks.
4. Proxies, `MethodHandle`, reflection caches, serialization frameworks, and logging adapters.
5. Unclosed native libraries, JNI references, event buses, and resource pools.

During analysis, you must prove that **the loader is still reachable from GC roots** and then locate the retaining reference; do not conclude a leak solely because metaspace has not dropped immediately after a single `close()` call.

## 3. Unified Logging: Seeing Class Load/Unload in HotSpot

Since Java 9, HotSpot supports unified JVM logging via `-Xlog`. On OpenJDK/HotSpot 17, start with:

```bash
java -Xlog:class+load=info,class+unload=info -cp app.jar com.example.Main
```

The command above is a **configuration example**; it will not run standalone without `app.jar` and `com.example.Main`. Load logs typically include the class name and source (JAR or module); unload logs appear when the JVM actually unloads a class.

To write logs to a file with timestamps, uptime, and tags:

```bash
java -Xlog:class+load=info,class+unload=info:file=class-events.log:time,uptime,level,tags \
     -cp app.jar com.example.Main
```

In production, you must limit log size and rotation to avoid filling the disk. Unified logging file rotation can use the `filecount` and `filesize` options; check the exact syntax and support with `java -Xlog:help`. Do not keep verbose class load logging enabled continuously without evaluating overhead and data volume.

### 3.1. Reading Logs Correctly

Illustrative log format example:

```text
[0.060s][info][class,load] java.lang.Object source: shared objects file
[0.185s][info][class,load] demo.plugins.Greeter source: file:/.../plugin-v1.jar
[5.290s][info][class,unload] unloading class demo.plugins.Greeter 0x...
```

Actual paths, addresses, formats, and timestamps depend on the JDK and collector. A class appearing twice in the load log may be due to two different defining loaders, rather than Java reading the same file twice by mistake.

If no unload events appear, it may be because the JVM has not run a GC cycle with unloading, the loader is still reachable, the collector/configuration has not performed unloading, or logging was enabled after the period of interest. Therefore, inspect the GC timeline and loader statistics before attributing the cause.

## 4. jcmd: Inspecting Class Loader Hierarchy and Statistics

`jcmd`, included in the JDK, supports diagnosing JVMs running on the same machine (subject to OS permissions and attach capabilities). First, find the PID:

```bash
jcmd -l
```

Then view the available commands for that specific runtime:

```bash
jcmd <PID> help
```

`<PID>` is the actual process ID, not a literal string to type verbatim. Some useful commands on HotSpot/JDK 17:

```bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.classloaders
jcmd <PID> GC.class_histogram
jcmd <PID> VM.metaspace
```

Not every JDK build or attach environment provides the exact same commands; if a command is absent, use `jcmd <PID> help` to verify and choose an alternative data source.

### 4.1. VM.classloader_stats

Usually reports each class loader data entry, the number of associated classes, and metadata/byte costs. This is the starting point for detecting old loaders persisting after multiple plugin reload cycles. When recording, compare snapshots from the same JVM, same version, and same workload rather than comparing raw bytes across different JDKs.

Illustrative self-constructed interpretation table, not standard stdout:

| Timestamp | Plugins Reloaded | Old Loaders Still Visible in Stats | Metaspace |
|---|---:|---:|---:|
| T0 | 0 | 0 | 80 MiB |
| T1 | 10 | 1 | 86 MiB |
| T2 | 50 | 28 | 132 MiB |

Under similar workload/heap/GC conditions, a steady increase in living old loaders across GC cycles is more significant than a single metaspace increase. The hypothetical data only illustrates how to read the trend.

### 4.2. VM.classloaders

Displays topology/class loader hierarchy information on supported runtimes. Useful for finding plugin loaders under the application loader, which loader owns a module/class, and inspecting the parent delegation structure. For graphs with custom layers or child-first loaders, combine this with application code printing loader identities; display names and hierarchy alone are not sufficient proof of all class ownership relationships.

### 4.3. VM.metaspace

Reports metaspace metrics—committed, reserved, and used—as well as certain allocation or class space details depending on options. Do not confuse committed/reserved bytes with live class metadata; the JVM may retain committed memory for reuse even after classes have been unloaded.

### 4.4. GC.class_histogram and Heap Dump

`GC.class_histogram` helps inspect object counts by class. To find retained class loader objects, you can filter for `URLClassLoader`, custom plugin loaders, `Thread`, registry objects, and provider instances. A histogram is only a snapshot of object types; it does not directly show retention paths.

If the issue persists, take a heap dump and use a heap analysis tool to trace GC roots and retained sizes. Heap dumps may contain passwords, tokens, personal data, and request payloads; you must enforce access permissions, encryption, retention periods, and deletion policies according to organizational policy.

## 5. Java Flight Recorder (JFR)

JFR collects JVM events over time with relatively low overhead when configured appropriately. It can provide class loading/unloading events, class loader statistics, allocations, and GC data depending on the JDK, profile, and event settings.

Start a recording using `jcmd`:

```bash
jcmd <PID> JFR.start name=plugin-diagnostics settings=profile duration=120s filename=plugin.jfr
```

Inspect the summary and event types using JDK tools:

```bash
jfr summary plugin.jfr
jfr metadata plugin.jfr
```

To observe class load/unload, ensure the corresponding events are enabled in the recording settings. Names such as `jdk.ClassLoad`, `jdk.ClassUnload`, and `jdk.ClassLoaderStatistics` depend on event availability and configuration; a default `profile` recording is not guaranteed to include all detailed events.

You can use Java Mission Control (JMC) to analyze the timeline, class loading, and GC, correlating spikes with exact plugin deploy/reload timestamps. Do not enable all events at high detail in production without evaluating storage and CPU overhead.

## 6. Java MXBean Tools: Observing Counters from Inside the Application

The JDK provides `ClassLoadingMXBean` to retrieve the current class count and cumulative counters. Use it to build simple host metrics without parsing JVM logs.

**Standalone** Java 17+ example, file `ClassLoadingMetrics.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class ClassLoadingMetrics {
    public static void main(String[] args) {
        ClassLoadingMXBean bean = ManagementFactory.getClassLoadingMXBean();
        int live = bean.getLoadedClassCount();
        long total = bean.getTotalLoadedClassCount();
        long unloaded = bean.getUnloadedClassCount();

        System.out.println("live classes >= 0: " + (live >= 0));
        System.out.println("total >= live: " + (total >= live));
        System.out.println("unloaded >= 0: " + (unloaded >= 0));
    }
}
```

Compile and run on JDK 17+:

```bash
javac ClassLoadingMetrics.java
java ClassLoadingMetrics
```

Expected stdout:

```text
live classes >= 0: true
total >= live: true
unloaded >= 0: true
```

On a normal HotSpot JVM, these conditions are reasonable; actual class counts always vary by JVM, JDK, libraries, and sampling time. `getLoadedClassCount()` is the current count; `getTotalLoadedClassCount()` and `getUnloadedClassCount()` are counters since JVM startup. Do not take a cumulative counter and interpret it as the number of live loaders.

### 6.1. Computing Deltas Over Time

Example of an exporter observing each sampling interval:

```java
long loadedBefore = bean.getTotalLoadedClassCount();
long unloadedBefore = bean.getUnloadedClassCount();
// ... plugin reload workload happens here ...
long loadedDelta = bean.getTotalLoadedClassCount() - loadedBefore;
long unloadedDelta = bean.getUnloadedClassCount() - unloadedBefore;
```

This is a **code snippet** requiring `bean` to be already declared. This delta describes the number of classes loaded/unloaded during the measurement interval, not which specific loader is leaking. Add metrics for plugin reload count, active plugin instances, class loader references, and metaspace committed/used for a complete picture.

## 7. Experimenting with New Class Loaders and Loader Leaks

A small experiment helps observe class identity and retention:

1. Create a `URLClassLoader` for a versioned plugin JAR.
2. Load a class with `Class.forName` and instantiate it if needed.
3. Record the loader's identity, loaded class count, and metaspace.
4. Stop the plugin, clearing listeners, tasks, registries, and thread-local references.
5. Close the loader, dropping strong references to classes, the loader, and instances.
6. Let GC run according to the runtime; observe logs/JFR/jcmd to see whether class unloading occurs.
7. Repeat multiple times under controlled workload conditions.

**Caution:** `WeakReference<ClassLoader>` can be used to observe whether a loader is still reachable, though `weakRef.get() == null` is only proof that the object was collected by GC at that point. Conversely, a weak ref still holding a value after one GC does not prove a leak. A class can still retain a loader via static caches or an active call stack.

Java snippet illustrating loader identity:

```java
ClassLoader loader = pluginInstance.getClass().getClassLoader();
System.out.println("loader identity: " + System.identityHashCode(loader));
System.out.println("module: " + pluginInstance.getClass().getModule());
```

This snippet is not standalone because it requires `pluginInstance`; `identityHashCode` does not guarantee absolute uniqueness across all objects. In production logging, assign a plugin-loader-instance ID using a counter or UUID and log it alongside the version to correlate logs accurately.

## 8. Systematic Class Loader Leak Diagnosis Workflow

### Step A: Establish a Baseline

Before reloading, record `ClassLoadingMXBean`, `jcmd VM.classloader_stats`, `VM.metaspace`, heap/metaspace metrics, JFR timeline, and the number of active plugins. Try to stabilize the workload/GC and record the JDK flags.

### Step B: Generate Controlled Load

Reload the same plugin a known number of cycles, e.g., 20 times; ensure the plugin code does not intentionally spawn unbounded threads/resources. Record timestamps and loader IDs for each version.

### Step C: Stop and Cleanup

Wait for requests to drain, call `stop/close`, cancel listeners/callbacks/timers/executors, close the loader when appropriate, and clear registry references. Then observe across multiple GC cycles that include class unloading.

### Step D: Compare Snapshots

If the number of living old loaders and the live class count rise continuously across cycles, inspect a heap dump to find GC roots. If the live count stays stable while both loaded and unloaded counters increase, you may simply have legitimate class churn rather than a leak.

### Step E: Verify the Fix

After fixing retained references, repeat the experiment with the same workload, same JDK, and same GC configuration; compare trends in loader count, live classes, metaspace used, heap retained size, and reload duration.

## 9. Common Tooling Mistakes

| Misconception | Why It Is Wrong | How to Fix |
|---|---|---|
| `URLClassLoader.close()` means classes are unloaded | `close()` only handles loader resources; reachability determines GC/unloading | Observe unload events, loader references, and GC |
| Increasing total loaded classes means a memory leak | This is a cumulative counter, not a live count | Combine live count and unloaded count |
| No unload log means a leak | GC/unloading has not occurred yet or logging is insufficient | Enable proper logging, observe longer, and check GC |
| Metaspace committed not shrinking means a leak | The JVM may keep memory for reuse | Compare metaspace used, class loader stats, and heap roots |
| Having two classes with the same name is a duplicate bug | Two loaders defining the same name may be intentional isolation | Check the defining loader and API contract |
| Using `System.gc()` to test reliably | The JVM may ignore it or not unload immediately | Use multiple observation cycles, JFR, and heap analysis |
| Recording all class load logs indefinitely in production | Causes I/O/CPU/disk overhead | Use short durations, log rotation, and sampling |

## 10. Operational Checklist for Plugin Hosts

- [ ] Track metrics for loaded/live/unloaded class counts and metaspace.
- [ ] Attach plugin version and class loader instance ID to lifecycle logs.
- [ ] Ensure `jcmd`/JFR commands are usable in production with proper permissions.
- [ ] Have an observation schedule before/after hot reloads under controlled workload.
- [ ] Clean up ThreadLocal, TCCL, executors, listeners, registries, and native resources before releasing a loader.
- [ ] Avoid retaining old plugin classes/objects/loaders in shared caches.
- [ ] Have a heap dump procedure and protect sensitive data inside dumps.
- [ ] Alert on **trends** of loader count, live classes, and metaspace rather than a single snapshot.

**Conclusion:** Monitoring class loading/unloading requires combining `ClassLoadingMXBean` counters, `-Xlog:class+load/unload` events, `jcmd` statistics, and JFR timelines. An old loader can only be reclaimed when no references retain it; closing the loader or running GC once does not guarantee unloading. Reliable diagnosis must correlate loader identity, plugin lifecycle, GC, and heap retention paths.
