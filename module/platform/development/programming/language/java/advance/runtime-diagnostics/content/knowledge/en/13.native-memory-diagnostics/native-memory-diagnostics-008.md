# 13.8. Diagnosing Growing Metaspace, Class Counts, or Class Loaders and Unloading Behavior

When a Java process's memory grows even though the heap remains relatively stable, one possibility to investigate is **metaspace**: the native memory region HotSpot uses to manage metadata for loaded classes. In applications with plugins, hot reload, dynamically generated proxies, script engines, or repeated module redeployments, metaspace growth may accompany **rising loaded class counts**, **rising live class loader counts**, or both. However, the three metrics are not synonymous and are insufficient to conclude a leak when viewed in isolation.

The diagnostic goal is to answer in order: **which memory is growing?** → **are new classes or new class loaders appearing?** → **is class unloading happening after suitable GC cycles?** → **which loaders remain reachable and what references retain them?**. This lesson focuses on HotSpot/OpenJDK 17+, with standalone runnable Java 17 examples. Metric names and GC details may vary across JDKs, collectors, and observation tools.

## 1. What Is Metaspace and How Does It Relate to Class Loaders?

When the JVM loads a class, besides the `java.lang.Class` object representing the class on the Java heap, the JVM also needs internal metadata: descriptors for the class, methods, fields, runtime constant pool, inheritance hierarchy, execution-support structures, and related components. HotSpot allocates this metadata via the **metaspace** manager in native memory; it is **not** a region consuming capacity inside `-Xmx` in the Java heap sense.

In HotSpot, metadata is typically managed along the **lifetime of the defining class loader**. Each loader that defines classes owns structures managing the associated metadata allocation regions. When GC determines a loader is reclaimable and performs class unloading, metadata of classes defined by that loader can be freed or reused, and part of the committed memory may be uncommitted.

Conceptual model:

```text
GC roots ──> application / registry / thread / Class<?> / instance
                    │
                    └──> Reachable ClassLoader
                                │ defines
                                ├──> PluginA (metadata in metaspace)
                                ├──> PluginB (metadata in metaspace)
                                └──> Proxy$123 (metadata in metaspace)

If the class loader remains reachable, the classes it defined
cannot be unloaded simply because the application stopped calling methods.
```

**Distinguishing the class–loader relationship:**

- A **defining class loader** is the loader that actually defines the class. An **initiating loader** may request loading while the parent defines the class; do not count every `loadClass()` call as a new class.
- Classes with the same binary name defined by two different defining loaders are **two distinct classes** to the JVM. Hence, reloading the same JAR with multiple loaders can grow class count and metaspace.
- Applications normally use long-lived loaders (bootstrap/platform/application) to load most classes. Those classes staying until JVM exit is normal.
- Class unloading is an optimization performed by the JVM/GC; application code must not rely on a specific unload timing.

### Metaspace Differs from Heap, RSS, and Compressed Class Space

| Metric / Memory Region | What Does It Hold or Represent? | Common Mistake |
| --- | --- | --- |
| `heap used` | Live or not-yet-collected objects/arrays on the Java heap. | Using it as a metaspace metric. |
| `Metaspace used` | Metadata currently reported as used by HotSpot. | Treating any increase as a leak. |
| `Metaspace committed` | Committed metaspace memory, which can exceed used. | Treating committed not dropping immediately as failed unloading. |
| `Metaspace reserved` | Reserved virtual address space; most of it may be uncommitted. | Adding it straight to RSS as physical RAM in use. |
| `Compressed Class Space` | Separate region for part of class metadata when compressed class pointers are enabled. | Confusing the default 1 GiB reserved with 1 GiB of real RAM consumed. |
| `RSS` / container memory | Resident memory of the whole process/container per the OS. | Blaming all RSS growth on metaspace while ignoring stacks, direct buffers, JIT/code cache, and native allocations. |

When HotSpot uses compressed class pointers, it manages metadata across distinct logical areas for `class space` and `non-class metaspace`. Tools may show "Metaspace" and "class space" on separate lines, or a combined metaspace metric. **Read each metric's exact definition before adding/subtracting** to avoid double-counting. High `reserved` capacity does not by itself prove physical memory consumption; `committed` and `used` are more helpful for evaluating growth, though still requiring cross-checks with RSS.

JDK 16+ introduced **Elastic Metaspace** (JEP 387), enabling HotSpot to return unused metadata regions to the OS more effectively after unloading. Still, the allocator retains chunks for reuse, and committed and RSS may react with a delay; **do not infer unloading solely from a dip in committed, or conclude no unloading occurred just because committed has not dropped yet**.

## 2. When Can a Class Actually Be Unloaded?

The Java Language Specification sets the foundational condition: a class may be unloaded only when **its defining loader can be reclaimed by GC**. For classes loaded by the bootstrap loader, class unloading does not happen in this manner. HotSpot needs a GC cycle supporting unloading to discover and free eligible metadata.

For a loader to become a reclamation candidate, there must be no strong reference path from GC roots holding the loader, classes it defined, instances of those classes, or related live structures. Cases to check:

- A `Class<?>` or instance of a class defined by the loader remains in a long-lived cache/registry.
- A thread is running plugin code, or keeps `Thread.contextClassLoader` pointing to an old loader.
- `ThreadLocal`, listeners, callbacks, executors, or tasks held by long-lived threads or services.
- A plugin/module framework retains references in management maps, schedulers, MBean/driver registries, or static fields of **classes belonging to a long-lived loader**.
- Agents/native/JNI/JVMTI or instrumentation frameworks hold references preventing the object graph from becoming eligible for reclamation.

**Do not over-interpret `static`:** a static field referencing an object inside the very class/loader about to be collected can sit inside an unreachable island of objects; merely having a static field does not automatically cause a leak. What matters is a **path from a long-lived root outside the loader** (e.g., an application-loader registry) reaching back into the loader/plugin.

`URLClassLoader.close()` closes I/O resources (such as opened JARs) associated with the loader; **it does not force the JVM to unload classes immediately**. Likewise, setting a variable to `null` removes only one specific reference edge; it does not guarantee all paths from GC roots are gone. `System.gc()` is a GC hint that may be ignored and does not guarantee immediate class unloading.

## 3. Four Metric Groups to Place Side by Side

### 3.1. Class Counts: Current Loaded, Total Loaded, Unloaded

`ClassLoadingMXBean` provides three counters:

- `getLoadedClassCount()`: number of classes currently reported as loaded by the JVM.
- `getTotalLoadedClassCount()`: total classes loaded since JVM startup, **cumulative**, never decreases.
- `getUnloadedClassCount()`: total classes unloaded, **cumulative**, never decreases.

Suppose two samples 10 minutes apart:

```text
t0: current=10_000, total=20_000, unloaded=10_000
t1: current=10_050, total=30_000, unloaded=19_950
```

Here there was heavy class load/unload activity, yet **current loaded classes rose by only 50**. Looking only at `totalLoaded` rising by 10,000 could mislead you into concluding "10,000 classes leaked". Sampling tools do not necessarily capture all three counters atomically at one instant, so do not rely on `total − unloaded = current` as an exact invariant in every log record.

Conversely, if `current loaded` climbs steadily across multiple comparable GC cycles, that signals searching for sources of new live classes/loaders. There is no universal "above N classes is a leak" threshold for all programs.

### 3.2. Class Loaders: Count, Types, and Lifecycle

Live loader counts must be measured with a tool capable of listing loaders or `ClassLoaderData`, such as `jcmd <pid> VM.classloader_stats`. **Do not use `totalLoadedClassCount` as the class loader count**. One loader can define thousands of classes; many loaders may define just one class each.

When reading statistics, distinguish validly active loaders (e.g., plugins still in use) from loaders **from old versions/deployments** that should have been freed. After each redeploy/reload, look for old-generation loader counts rising without dropping across suitable GC cycles.

### 3.3. Metaspace: Used, Committed, Reserved, Class Space

Capture time series of metaspace `used` and `committed`, along with `Compressed Class Space` metrics if enabled and reported by the tool. Keep consistent KiB/MiB units and scope (pool, instance, JVM). A dashboard showing only total reserved is insufficient to diagnose metadata retention.

For the same number of classes, committed may be higher due to **chunk allocation, free space inside chunks, management structures, or reclamation policies**. While a class loader remains alive, allocated metadata cannot always be freed piecemeal arbitrarily.

### 3.4. GC Activity and Class Unloading

Record when the collector runs phases capable of unloading classes, unload event counts, and subsequent changes in `current loaded` and `metaspace used`. In G1, different cycles/phases have different capabilities; **a single young GC is insufficient proof that the JVM had an opportunity to process all metadata of unused loaders**. With concurrent collectors, unloading can happen on its own cycle schedule, and traces will not necessarily align with a single drop in heap used.

## 4. Common Patterns and How to Interpret Them

| Concurrent Observations | Reasonable Hypothesis | What to Verify |
| --- | --- | --- |
| `totalLoaded` rises, `unloaded` also rises; `current` and metaspace used stay stable | Normal lifecycle class loading/unloading. | Check old-version loader count, GC unloading, and load. |
| `current` rises, metaspace used rises, loader count stays nearly flat | One or a few long-lived loaders continuously defining more classes, e.g., dynamic bytecode/proxies. | Filter class groups and class-generation call sites; check cache/unique keys. |
| Loader count rises alongside `current` and metaspace used, many old-version loaders | Old plugin loaders likely retained after reload/deploy. | Find references to old loaders via heap dump/Path to GC Roots. |
| Loader count rises at deploy then drops after suitable GC, metaspace used drops/stabilizes | Lifecycle churn, potentially normal. | Compare across several cycles; check if peaks exceed memory budget. |
| Metaspace committed rises while used is stable, class/loader counts flat | Chunks/capacity/reuse or native allocator variance; not enough to call a leak. | Check `VM.metaspace`, NMT, GC phases, and long-term trends. |
| RSS rises while metaspace used/committed stay stable | Suspect other native memory, heap committed, direct buffers, stacks, code cache, etc. | Check NMT, OS/container memory, and corresponding pools. |
| Metaspace used rises after startup then stabilizes | Warm-up: lazy class loading, framework/proxy initialization. | Compare warm-up timing and align workload; evaluate plateau. |
| `OutOfMemoryError: Metaspace` or `Compressed class space` | Metadata budget or related limit exhausted; does not automatically prove a leak. | Check VM flags, class/loader growth, native budget, logs, and dumps. |

## 5. Time-Series Diagnostic Workflow

1. **Lock down context:** record JDK/vendor/version, collector, `-Xmx`, `-XX:MaxMetaspaceSize` if set, `CompressedClassSpaceSize`, workload, deploy/reload timestamps, PID/instance, and container memory limit.
2. **Take a post-warm-up baseline:** capture `Metaspace used/committed`, `Compressed Class Space`, `current/total/unloaded` classes, loader count, and RSS. With only one snapshot, do not conclude a trend.
3. **Observe repeatedly:** sample after deploys/reloads or at fixed time windows; capture timestamps and request rates together. Use the same tools/units so checkpoints are comparable.
4. **Verify actual unloading:** cross-check `-Xlog:class+unload`, GC logs, and the `unloaded` counter after GC cycles that support unloading. If no suitable cycle occurred yet, do not use an unchanged counter to declare a leak.
5. **Identify growing loaders/classes:** analyze `VM.classloader_stats`, `VM.metaspace` (when supported by the JVM), class histograms/JFR, or heap dumps; note loaders with large metadata and old-version loaders that fail to disappear.
6. **Find retention paths:** open a heap dump in Eclipse MAT/VisualVM and trace `ClassLoader` / `Class<?>` / instances → `Path to GC Roots`. Look for registries, thread context loaders, `ThreadLocal`, listeners, MBeans, and static caches in long-lived loaders.
7. **Verify with a controlled fix:** remove the reference-retention point or curb duplicate class generation; repeat the same workload/reloads; confirm class unloading resumes and metaspace used stops growing unexpectedly.

Record metrics before and after under **comparable conditions**. After each deploy, the JVM may need to JIT-compile, load framework classes, and generate more proxies; baselining too early before warm-up exaggerates natural growth.

## 6. HotSpot/OpenJDK Tools to Know

### 6.1. `jcmd`: Loader and Metaspace Snapshots

Run as a user authorized to attach to the target JVM; `<pid>` is a placeholder for the actual PID—**do not type it literally into the shell**.

```bash
# List JVM PIDs (on the appropriate host/PID namespace)
jcmd -l

# View available commands and exact help for the running JVM
jcmd <pid> help
jcmd <pid> help VM.classloader_stats
jcmd <pid> help VM.metaspace

# Class/byte counts and statistics per class loader
jcmd <pid> VM.classloader_stats

# Metaspace stats if this command is present in this JVM version
jcmd <pid> VM.metaspace

# When supported: break down usage by loader
jcmd <pid> VM.metaspace show-loaders
```

`VM.classloader_stats` gives loader info and related statistics; exact formatting varies by JDK. `VM.metaspace` and `show-loaders` may only exist in certain versions/distributions; **always check `jcmd <pid> help`**. `VM.metaspace` output typically includes concepts such as used, committed, reserved, capacity, or free chunks; if you see thousands of MiB reserved while committed is far lower, do not infer the JVM is using that much physical RAM.

`jcmd` commands may trigger safepoints or incur overhead depending on the command and loader/class count; avoid polling at high frequency on very large systems. If the app runs in a container, enter the right PID namespace and user; host commands may not see container-internal PIDs the same way.

### 6.2. `jstat`: Fast Time Series

```bash
# Sample every 1,000 ms for 10 samples total
jstat -class <pid> 1000 10

# Track metadata space capacity (if reported by JVM)
jstat -gcmetacapacity <pid> 1000 10

# Track utilization percentages of GC / metaspace regions
jstat -gcutil <pid> 1000 10
```

`jstat -class` includes columns for `Loaded`, `Unloaded`, and load/unload time; those do not mean all are **currently live classes**. Check `Bytes` column units in your JDK's help. `-gcutil` typically shows `M` for percentage of metaspace used relative to reported capacity and `CCS` for compressed class space (if present), **not absolute MiB**. `-gcmetacapacity` focuses on relevant capacity/committed metrics; column names can vary by JDK/collector. Run `jstat -options` to see available options.

### 6.3. JVM Unified Logging: Class Load/Unload and Metaspace GC

From JVM startup, you can enable a log configuration with clear tags/timestamps:

```bash
java -Xms256m -Xmx1024m \
  -Xlog:gc*=info,class+unload=info,gc+metaspace=debug:file=class-gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

This is an example for HotSpot 17+. GC logs help correlate metadata fluctuations with GC phases; `class+unload` records detected unload events. If you need to see **which classes are continuously being newly defined**, you can temporarily add `class+load=info`, though that log can grow huge on dynamic applications. **Do not leave detailed logging running continuously in production without measuring overhead and preparing rotation/storage.**

Seeing no `class+unload` over a short observation window may simply mean the JVM **has not yet had a reason or suitable GC cycle to unload**, logging was off, or all loaders remain reachable. To tell them apart, correlate GC events with class/loader snapshots.

### 6.4. Native Memory Tracking: Measuring Growth by Subsystem

HotSpot Native Memory Tracking (NMT) must be enabled **at JVM startup**; `summary` mode is usually enough to start, while `detail` has higher cost.

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar

# After the app warms up, take a baseline
jcmd <pid> VM.native_memory baseline

# View current summary
jcmd <pid> VM.native_memory summary scale=MB

# After a growth interval, compare against baseline
jcmd <pid> VM.native_memory summary.diff scale=MB
```

In NMT, the `Class` category and `Metaspace` lines/details can show reserved, committed, metadata regions, and loader overhead depending on JVM config. **Reserved is not committed, and committed is not used**. If `Class` stays nearly flat while RSS rises, check other subsystems: `Thread`, `Code`, `GC`, `Internal`, native allocations outside HotSpot NMT tracking, and third-party library memory. NMT neither covers every `malloc` in external native libraries nor provides the full reference-retention graph.

### 6.5. JFR, Heap Dumps, and Linking Root Cause

Java Flight Recorder (JFR) can record class loading/unloading events and GC traces when the corresponding events are enabled; inspect with Java Mission Control. Use a short recording under reproducible conditions:

```bash
jcmd <pid> JFR.start name=metaspace-check settings=profile duration=120s filename=metaspace-check.jfr

# When retention analysis is needed and disk/permissions permit:
jcmd <pid> GC.heap_dump /tmp/loader-investigation.hprof
```

`GC.heap_dump` can pause the JVM and create a very large file; by default on HotSpot, dumping may request a full GC before capturing (see `jcmd <pid> help GC.heap_dump`). A heap dump is a snapshot of the **object graph on the heap**, not a direct measure of all native metadata bytes. It helps trace why a `ClassLoader` remains reachable, e.g., held by a thread or registry. Use MAT's `Path to GC Roots` to verify.

HPROF files can contain tokens, user info, and internal data; store, transfer, and delete them only under appropriate security policies.

## 7. Java 17+ — Self-Sampling Class and Metaspace MXBeans

The following program is standalone and needs no libraries outside the JDK. It reads `ClassLoadingMXBean` and the `Metaspace` `MemoryPoolMXBean`, printing 5 lines roughly 1 second apart. Save as `ClassMetaspaceMonitor.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.time.Instant;

public final class ClassMetaspaceMonitor {
    private static final long KIB = 1024L;

    public static void main(String[] args) throws InterruptedException {
        ClassLoadingMXBean classBean =
                ManagementFactory.getClassLoadingMXBean();

        MemoryPoolMXBean metaspace = ManagementFactory.getMemoryPoolMXBeans()
                .stream()
                .filter(pool -> "Metaspace".equals(pool.getName()))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("HotSpot Metaspace pool not found"));

        for (int i = 0; i < 5; i++) {
            MemoryUsage usage = metaspace.getUsage();

            System.out.printf(
                    "%s current=%d total=%d unloaded=%d metaUsed=%dKiB metaCommitted=%dKiB%n",
                    Instant.now(),
                    classBean.getLoadedClassCount(),
                    classBean.getTotalLoadedClassCount(),
                    classBean.getUnloadedClassCount(),
                    usage.getUsed() / KIB,
                    usage.getCommitted() / KIB);

            if (i < 4) {
                Thread.sleep(1000);
            }
        }
    }
}
```

Compile and run:

```bash
javac ClassMetaspaceMonitor.java
java ClassMetaspaceMonitor
```

**Output:** exactly **5 lines** matching the `printf` format. Timestamps, class counts, and metaspace sizes depend on JDK/machine/run; there is no reliably fixed numeric stdout. For example, a **hypothetical illustrative line**, not a standard benchmark result:

```text
2026-10-29T10:00:00Z current=1020 total=1060 unloaded=40 metaUsed=5120KiB metaCommitted=5376KiB
```

All three class numbers come from three consecutive MXBean calls, not a single atomic snapshot. The example measures **only the monitor process itself**, not another application. To diagnose a real service, expose metrics via JMX/monitoring or run `jcmd`/`jstat` against the target PID. The pool name `Metaspace` is specific to HotSpot; other JVMs may use different pools.

## 8. Java 17+ — Reproducing Multi-ClassLoader Lifecycles

The experiment below loads **the same class using many distinct URLClassLoaders**, demonstrating why loader count, class count, and metaspace can grow even when the class source does not change. There are two modes: **`release`** does not intentionally retain loaders; **`retain`** holds loaders in a long-lived static list. This is a test model, not meant to run as a production workload.

Create `PluginTask.java`:

```java
public final class PluginTask {
    public static String run() {
        return "ready";
    }
}
```

Create `LoaderCycleDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LoaderCycleDemo {
    private static final List<ClassLoader> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        boolean retain = args.length > 0 && "retain".equals(args[0]);
        URL pluginDir = Path.of("plugin-bin").toAbsolutePath().toUri().toURL();

        for (int i = 0; i < 100; i++) {
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{pluginDir},
                    ClassLoader.getPlatformClassLoader())) {

                Class<?> plugin = Class.forName("PluginTask", true, loader);
                Object value = plugin.getMethod("run").invoke(null);
                if (!"ready".equals(value)) {
                    throw new IllegalStateException("Unexpected plugin output");
                }

                if (retain) {
                    RETAINED.add(loader);
                }
            }
        }

        System.out.printf("created=100 retained=%d%n", RETAINED.size());
        Thread.sleep(30_000L);
    }
}
```

Run from the directory containing both source files on Bash/Linux/macOS (with JDK 17+, `javac`, and `java` on PATH):

```bash
mkdir -p plugin-bin
javac -d plugin-bin PluginTask.java
javac LoaderCycleDemo.java

# Run A: do not actively retain references to loaders
java -Xmx128m -Xlog:class+unload=info -cp . LoaderCycleDemo release

# Run B: retain 100 loaders in a static list
java -Xmx128m -Xlog:class+unload=info -cp . LoaderCycleDemo retain
```

The two output lines printed by the program itself (excluding VM log lines) are **deterministic**, respectively:

```text
created=100 retained=0
```

```text
created=100 retained=100
```

In each run, the program sleeps 30 seconds after printing so you have time to inspect from another terminal with `jcmd <pid> VM.classloader_stats`. Because `PluginTask` resides in `plugin-bin` rather than classpath `.`, and the parent is the platform loader, each new `URLClassLoader` can **define its own copy of `PluginTask`**. If you replaced the parent with the application loader that can find the class itself, parent-first delegation would change the outcome.

**Lifecycle implications:**
- In `retain` mode, `RETAINED` is a static field of the **application class loader**, so all 100 loaders stay reachable; closing `URLClassLoader` via try-with-resources only frees associated I/O resources and does not cause them to unload.
- In `release` mode, there is no retention list, yet class unloading still depends on actual reachability and GC. You might see **no** unload events within that exact 30 seconds if the collector does not run a suitable phase.
- Do not compare two runs solely by RSS at the final second or by forcing `System.gc()`. For solid evaluation, run a controlled repeated workload, collect metrics before/after GC cycles with unloading, and check whether loaders remain reachable.

To simulate a more realistic leak, place the retention list inside an application/hot-reload manager registry and iterate across many generations. What needs fixing is **reference-management lifecycle**, not merely increasing `MaxMetaspaceSize`.

## 9. Building a Measurement Table and Reading a Numeric Example

Assume a plugin service is reloaded hourly; the table's checkpoints are taken after warm-up and after GC cycles with class-unloading opportunities under comparable workloads. All figures are **hypothetical data for reading practice**, not standard diagnostic thresholds:

| Checkpoint | Current Loaded Classes | Total Loaded Classes | Total Unloaded Classes | Live Loaders | Metaspace Used | Metaspace Committed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 08:00 | 9,200 | 14,000 | 4,800 | 95 | 80 MiB | 96 MiB |
| 10:00 | 11,900 | 21,000 | 9,100 | 240 | 118 MiB | 132 MiB |
| 12:00 | 14,300 | 29,000 | 14,700 | 400 | 159 MiB | 172 MiB |

From 08:00 to 12:00, `totalLoaded` increased by 15,000 and `totalUnloaded` increased by 9,900: the JVM **is unloading**, yet currently loaded classes still rose by 5,100. Live loaders rose by 305 and metaspace used rose by 79 MiB. This concurrent growth raises the hypothesis: **old-generation loaders/plugins are not being released, or new class creation outpaces unloading**.

To confirm a loader leak, find: which loaders outlive their valid lifecycle, which deploy they belong to, how many classes they define, and which GC roots retain them. A feature legitimately opening many plugins can produce similar rising metrics. The table establishes an **investigation signal**, not self-sufficient proof of root cause.

If instead you saw a second series: `current=9,200 → 9,250 → 9,230`, `metaspace used=80 → 83 → 81 MiB` while `totalLoaded` kept climbing, the app is likely loading/unloading in a controlled manner. A `committed` gap can still persist due to chunk reservation/reuse without necessarily indicating a leak.

## 10. Typical Causes and Remediation

### 10.1. Plugin/Redeploy Retaining Old Loaders

For example, a manager loads each plugin version with a new `URLClassLoader`, but on unload only closes the JAR without removing its entry from an application `Map<String, ClassLoader>` or leaves a scheduler running plugin tasks. Old loaders remain reachable, so classes they defined do not unload.

**Investigate:** compare loader generations, threads, schedulers, and registries; in a heap dump trace paths from roots to old loaders. **Fix:** cancel tasks/executors, unregister listeners/callbacks/MBeans, remove registry entries, close resources, drop strong references, and verify unloading across multiple suitable cycles.

### 10.2. Thread Context Class Loader and `ThreadLocal`

A long-lived thread pool can retain an old plugin's `contextClassLoader`, or a `ThreadLocal` value can reference a class/instance defined by an old loader. After redeploy, clearing one field in the plugin manager is not enough if the thread survives.

**Investigate:** inspect `Thread`/`contextClassLoader` and `ThreadLocalMap` in a heap dump; track threads/tasks surviving across deploys. **Fix:** restore the context class loader after tasks in `try/finally`, call `ThreadLocal.remove()` in the right scope, stop tasks/threads when unloading plugins; avoid letting task/plugin objects leak into long-lived executors.

### 10.3. Unbounded Dynamic Proxy/Bytecode Generation

A framework generates proxies, bytecode, runtime classes, template/script classes, or instrumentation per new input. If every request generates a **distinct class definition** inside a long-lived loader, `current loaded` and metaspace used can grow while **loader count stays nearly flat**. While the same defining loader remains alive, the JVM cannot simply unload individual defined classes just because one proxy instance is no longer used.

**Investigate:** check generated class names, generation stacks, cache keys, per-loader class stats, and relevant JFR/traces. **Fix:** reuse configs/proxies, normalize cache keys, bound generated variants, redesign cache/loader lifecycles; do not automatically assume every class named `$Proxy` or `$$Enhancer` is a leak.

### 10.4. Registries/Global Caches Retaining `Class<?>`

A map in an application-loader class stores `Class<?>`/`Method`/`Constructor` objects from an old plugin, listener, or callback. Because `Class<?>` objects and reflection metadata link back to their defining loader, holding that reference can block class unloading.

**Investigate:** heap dump + retained paths; inspect static registries in loaders **that outlive plugins**. **Fix:** remove entries on unload, use lifecycle-appropriate cache policies, and consider weak references only when doing so preserves business semantics.

### 10.5. Normal Growth During Warm-Up or New Feature Rollouts

A microservice may lazy-load classes the first time a rare request path runs, initializing codecs, JSON serializers, ORM proxies, or libraries. Metaspace rising initially and then **reaching a plateau** is normal behavior. Adding features/dependencies can permanently raise the baseline class and metadata footprint.

**Investigate:** compare the same version/config with warmed-up workloads; avoid using "before deploy" and "after deploy" with different class sets as a leak test. **Fix:** if within budget and stable, no change may be needed.

## 11. JVM Flags to Interpret Properly

| Flag | Effect | Caveat When Using |
| --- | --- | --- |
| `-XX:MetaspaceSize=<size>` | **Initial high-water mark** used in the policy triggering metaspace-related GC. | Not a fixed metaspace size or "maximum limit". |
| `-XX:MaxMetaspaceSize=<size>` | Sets a ceiling on native memory for class metadata; includes committed class space when compressed class pointers are used. | Can cause `OutOfMemoryError: Metaspace` sooner; does not fix loader retention. |
| `-XX:CompressedClassSpaceSize=<size>` | Adjusts virtual address space reserved for compressed class space in supported configurations. | Large reserved size does not mean large RAM used; do not shrink arbitrarily. |
| `-XX:+ClassUnloading` / `-XX:-ClassUnloading` | Enables/disables class unloading in HotSpot when supported by the collector. | Disabling unloading keeps metadata retained; change only with verified reason. |
| `-XX:NativeMemoryTracking=summary` | Tracks HotSpot native memory by subsystem. | Must be enabled at startup and account for overhead. |
| `-XX:MetaspaceReclaimPolicy=...` | Elastic metaspace reclamation policy in newer HotSpot builds. | Does not replace cleaning up references; consider tuning only after diagnosing root cause. |

`-Xmx` limits only the Java heap, **not metaspace inside that heap**. In a container, heap + metaspace + compressed class space committed + thread stacks + direct buffers + code cache + other native parts all share the memory budget. When hitting `OutOfMemoryError: Metaspace`, determine **whether it is due to `MaxMetaspaceSize`, class/loader growth, or actual RAM/native limits** rather than immediately raising the flag.

If `CompressedClassSpaceSize` shows ~1 GiB reserved in logs, do not assume 1 GiB of RSS: check actual **committed** and **used**. When totaling committed, pay attention to combined vs. separate metrics to avoid double-counting.

## 12. Practice Reading Three Different Scenarios

### A. Flat Heap While Metaspace/Loaders Grow

After 10 plugin redeploys, `heap used after GC` shows no clear rise, yet `VM.classloader_stats` shows loaders from all 10 versions still present; `Metaspace used` rises each time. A heap dump reveals an application-level event bus retaining listeners from old versions, and listeners hold objects and their defining loaders. **The fix** is unregistering listeners on unload and verifying old loaders become unloadable. Raising `-Xmx` does not solve native metadata retention.

### B. Metaspace Committed Rises While Used and Class Count Stay Stable

After a wave of plugin churn, `totalLoaded` jumped and `totalUnloaded` jumped too; `current` and `used` returned near baseline while `committed` remained higher. Likely the allocator retained chunks for reuse or has not uncommitted yet; on JDK 17+ elastic metaspace can often return some memory to the OS after unloading, though timing depends on VM state. **There is no direct proof of a loader leak** solely from committed not dropping yet. Monitor a few more cycles and cross-check NMT and RSS.

### C. Current Classes Rise While Loader Count Barely Changes

A service uses one long-lived loader yet generates new bytecode classes on every random configuration. `current loaded` climbs from 20,000 to 50,000; loader count stays flat and metaspace used rises. Investigation targets the generator and class-caching/key logic, **not merely looking for an unclosed loader**. The solution may be reusing proxy types or reducing generated-class cardinality.

## 13. Common Reasoning Errors

- **"Metaspace rising means a memory leak."** Insufficient; determine plateau, workload, class growth, loader lifetimes, and GC unloading.
- **"`totalLoaded` rising means live classes are rising."** False; the cumulative counter only increases, even for unloaded classes.
- **"If class unloading happens, there cannot be a leak."** False; some classes can unload while other loaders remain persistently retained.
- **"A loader was `close()`d so it is guaranteed to unload."** False; `close` frees URL/JAR resources, not all GC roots.
- **"A class with no remaining instances is guaranteed to unload."** False; its defining loader may still be reachable and the class still usable via reflection/static code.
- **"Stable loader count means metadata cannot leak."** False; one long-lived loader can define new classes endlessly.
- **"High reserved metaspace equals RAM used."** False; separate reserved/committed/used and measure RSS.
- **"`-XX:MetaspaceSize` is a cap."** False; it sets a high-water mark for triggering GC; the cap is controlled by `MaxMetaspaceSize` when configured.
- **"`System.gc()` did not increase unloaded, so there is a leak."** False; calling GC is only a hint, and the collector/JVM may not unload during that pass.
- **"A heap dump shows all native metadata accurately."** False; dumps help trace heap paths retaining loaders, not replace metaspace/NMT reports.
- **"Raising `MaxMetaspaceSize` is a fix."** False; a higher ceiling only adds headroom while reference/bytecode-generation leaks continue.
- **"RSS rising is a metaspace bug."** False; compare NMT, heap committed, thread/native memory, and container metrics.

## 14. Operational Checklist Before Concluding

1. **Metrics:** are you using the right `Metaspace used`, `committed`, `Compressed Class Space`, consistent units, and the exact same JVM?
2. **Baseline:** did you exclude startup/warm-up and compare the same version/workload?
3. **Classes:** is `current loaded` climbing persistently, or is only `totalLoaded` rising over time?
4. **Loaders:** are old-generation plugin/redeploy loaders still alive, or is one loader continuously defining new classes?
5. **GC:** have GC cycles capable of class unloading run, and how did unload logs/`unloaded` counters change?
6. **Native:** do NMT `Class/Metaspace` and RSS agree; are there signs of growth in other subsystems?
7. **Reachability:** did you find a path from GC roots retaining the loader/`Class<?>`/instance in a heap dump?
8. **Resolution:** after cleaning registries, thread contexts, listeners, caches, or curbing class generation, do class/loader/metaspace trends stabilize under the same test scenario?

**Core takeaway:** to diagnose metaspace growth, read **the trio of trends—metaspace, classes, and class loaders—together with GC class-unloading events**. `Total loaded` only tells how many classes were **ever** loaded; `current loaded` shows what exists at sampling time; loader counts and GC roots reveal which object lifecycles retain metadata. Base fixes on what retains loaders or drives excessive class generation, not on a single rising memory line.

### Official Reference Documentation

- [Oracle JDK 17 — Garbage Collection Tuning: Other Considerations (Class Metadata)](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html)
- [Oracle JDK 17 — jcmd diagnostic commands](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java Language Specification, Java SE 17 — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/en/java/specs/jls/se17/html/jls-12.html#jls-12.7)
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387)
