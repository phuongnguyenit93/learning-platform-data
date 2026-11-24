# 17.9. Relating Dynamically Generated Classes and Long-Lived Class Loaders to Metaspace

## Objectives

After this lesson, you will be able to:

1. Explain how **Metaspace** stores class metadata in HotSpot/JVM and why it differs from the **Java heap**, which holds `ClassLoader` objects, instances, and application data structures.
2. Distinguish **one class with many instances**, **one class name defined by multiple class loaders**, and **many classes generated dynamically at runtime**.
3. Trace the reference path from **GC root → object retaining `ClassLoader` → classes defined by that loader → metadata in Metaspace** to understand why holding a loader too long can drive Metaspace growth.
4. Measure **loaded/unloaded classes**, Metaspace memory, and loader counts using `ClassLoadingMXBean`, `MemoryPoolMXBean`, `jcmd VM.classloader_stats`, `VM.metaspace`, NMT, and class-unloading logs.
5. Reproduce in **Java 17+** two contrasting cases when generating dynamic proxies: holding strong references to loaders (`hold`) vs. releasing them (`release`); know what can and cannot be concluded from the numbers.
6. Recognize signs of class-loader leaks in plugins, hot-reload, and proxy/bytecode generators, and fix them through lifecycle, cache, and thread context class loader management.

> **Core message:** A dynamically generated class is **not automatically a leak**. Problems arise when *class definitions* keep getting created over time **and** those loaders/classes remain reachable after their associated feature has ended. Failing to release a loader can keep metadata of all classes it defined in Metaspace; yet a single Metaspace increase alone is not enough to declare a leak.

## 1. Where Does Metaspace Live in JVM Memory?

In HotSpot since Java 8, **Metaspace** is a native memory area managed by the JVM for metadata of loaded/defined classes. It is not directly part of the Java object heap. The Java heap continues to store ordinary objects, such as:

- Business class instances: `Order`, `User`, `ArrayList`, byte arrays.
- `java.lang.Class` objects representing classes at the Java level.
- `ClassLoader` objects, cache maps, threads, proxy instances, and application references.

Metaspace in native memory stores the internal class representations and corresponding metadata structures needed by the VM at runtime. **An ordinary Java object does not equal a class definition**: creating 1 million `new Order()` instances shares the metadata of `Order` defined by one loader. Conversely, a system creating thousands of **distinct class definitions** at runtime can create Metaspace pressure even with very few live instances on the heap.

```text
                 Java Heap                            Native memory
  +--------------------------------+           +----------------------------+
  | GC roots                       |           | Metaspace                  |
  |   -> registry / thread / cache |           |  metadata of class A       |
  |       -> ClassLoader L         |---------->|  metadata of class B       |
  |       -> Class<?> / instance   |  lifetime |  ...                       |
  |                                |   binding +----------------------------+
  +--------------------------------+
```

The arrow to Metaspace in the diagram represents **management and lifecycle binding**, not a claim that a single Java reference pointer addresses a specific native block directly.

### Heap, Metaspace, Compressed Class Space, Code Cache: Do Not Mix Them Up

| Component | Conceptually Contains | Primary Observation |
| --- | --- | --- |
| **Java heap** | Object instances, `ClassLoader` objects, `java.lang.Class` mirrors, collections/caches. | Heap metrics, `GC.class_histogram`, heap dump/GC roots. |
| **Metaspace** | Class metadata managed by the JVM outside the heap. | `Metaspace` memory pool, `jcmd VM.metaspace`, NMT. |
| **Compressed Class Space** (when used) | Dedicated region for klass metadata supporting compressed class pointers. | `Compressed Class Space` pool, `VM.metaspace`, NMT. |
| **Code Cache** | JIT-compiled machine code and related code structures. | `jcmd Compiler.codecache`, JFR/JIT metrics. |
| **Thread stack** | Thread stack frames in native memory. | Thread metrics, native memory tools. |

**Important:** `java.lang.OutOfMemoryError: Metaspace` is not the same as `java.lang.OutOfMemoryError: Java heap space`. Raising `-Xmx` only raises the heap limit; it **does not directly expand the Metaspace limit**. In a container with fixed total memory, changing heap size can affect remaining native memory, yet that is a total memory-budget constraint, not the two regions being identical.

### `used`, `committed`, and `reserved` Are Three Different Quantities

- **Used:** metadata actually in use as reported by the JVM/pool.
- **Committed:** memory capacity the JVM has committed for use; may exceed `used`.
- **Reserved:** virtual address space reserved for memory structures, **not necessarily committed or occupying physical RAM**.

**Hypothetical** example:

```text
Metaspace:    used = 120 MiB, committed = 144 MiB
Class space:  reserved = 1024 MiB, committed = 20 MiB
```

Do not conclude the JVM is consuming 1 GiB of RAM just because **reserved = 1024 MiB**. Nor assume that when `used` drops after unloading, process RSS must drop immediately: chunks/pages may be retained by the JVM for reuse, and the allocator and OS decide when memory is returned. Different HotSpot versions/collectors may reclaim differently.

## 2. What Exactly Are "Dynamically Generated Classes"?

In this lesson, **dynamically generated classes** refers to *class definitions created or loaded while the JVM is running*, rather than a fixed set of classes loaded once at startup.

Common sources:

- **JDK dynamic proxies:** `Proxy.newProxyInstance(...)` creates an instance of a JVM-generated proxy class for the given interfaces/loader.
- **Bytecode-generating frameworks:** AOP, interception, ORM, lazy proxies, serializers, mocking, and bytecode generation (Byte Buddy/CGLIB/ASM, depending on framework).
- **Plugins and hot deployment:** reloading JARs/modules with a new loader to swap plugin versions without restarting the JVM.
- **Scripting, expression/rule engines, template compilers:** can generate a class per script/expression if no reuse mechanism exists.
- **`ClassLoader.defineClass` or `MethodHandles.Lookup.defineClass`:** defines classes from bytecode where APIs and permissions allow.

Not every "dynamic" operation creates **a new class**:

| Action | Creates a New Class Definition Every Time? |
| --- | --- |
| `new Customer()` 100,000 times | **No.** Instances share metadata of the class defined by the loader. |
| Repeated `Class.forName("com.acme.Customer")` via the same loader | Usually finds/returns **the same class definition** within that loader's scope; does not generate 100,000 new classes. |
| Repeated `Proxy.newProxyInstance(loader, same interface list)` with **the same loader** | The JDK reuses the generated proxy class for that loader/interface combination; mainly creates new **instances**. |
| `Proxy.newProxyInstance(newLoader, same interface)` with 100 different loaders | Can create **100 distinct proxy class definitions**, each tied to its loader's metadata/lifecycle. |
| Reloading the same name `com.acme.Plugin` with another loader | Two identically named classes can be **two distinct types** in the JVM. |

**Class identity:** by definition, identity requires **binary name + defining class loader**. One class name appearing in two different loaders does not produce the same type; casting between them can throw `ClassCastException` even though printed names match.

Semantic illustration:

```text
com.acme.Plugin @ Loader-v1  !=  com.acme.Plugin @ Loader-v2
```

Class loaders typically use **parent delegation**: a child loader references a parent loader to delegate class lookup. **The default relationship is child → parent**, not the parent automatically pinning every child loader. To conclude a child loader is retained, you must find an actual reference path from a GC root to it, not just point at the app class loader being its parent.

## 3. Why Does ClassLoader Lifecycle Govern Metadata Reclamation?

Suppose each hot deploy creates a new loader and loads plugin classes:

```text
Deploy 1: PluginLoader-A -> 1,000 classes
Deploy 2: PluginLoader-B -> 1,000 classes
Deploy 3: PluginLoader-C -> 1,000 classes
...
```

When A is replaced by B, **A only has a chance to be reclaimed** if strong references keeping loader A or A's classes/instances alive are gone. The JVM can unload classes when their defining loader becomes eligible for collection and class unloading runs. **GC does not guarantee immediate unloading at a deterministic instant**, even after a loader becomes unreachable; JVM implementation and GC configuration also matter.

### Two Contrasting Situations

**A. Clean lifecycle (eligible to unload):**

```text
registry(active) -> Loader-B -> class metadata B
              ...
Loader-A is no longer strongly held by registry, threads, or caches
    -> Loader-A can be GC'd
    -> Loader-A's classes can unload
    -> Loader-A's metadata/chunks can be reused/reclaimed
```

**B. Unexpectedly retained loader (leak risk):**

```text
GC root
  -> static Map in long-lived application
      -> old PluginDescriptor
          -> Loader-A
              -> classes defined by A
                  -> Metaspace retains related metadata
```

In B, even with no requests using plugin A, loader A remains reachable from a root. Normal class unloading cannot reclaim classes defined by A while loader A is still needed. If every deploy creates a new loader and all old loaders stay retained, class metadata can grow linearly with deployments.

**Important distinction:** a reference cycle *purely among objects inside the same plugin* that is **unreachable from any external GC root** does not by itself cause a leak. GC collects unreachable cycles. Conversely, even **one** strong reference from a long-lived registry or thread suffices to keep the entire cluster of objects/loader alive.

### Common GC Roots / Loader-Retention Paths

| Retention Site | Strong-Reference Example | Action to Check |
| --- | --- | --- |
| **Main app static/singleton registry** | `Map<id, PluginContext>` still holds old context/plugin. | Remove entry on unload; check where instances are still referenced. |
| **Thread context class loader (TCCL)** | Pool worker's `getContextClassLoader()` still points to plugin loader after task ends. | Restore TCCL in `finally`; check threads spawned by the plugin. |
| **Executor, scheduler, timer, thread** | Live task/closure/listener retains plugin Class/instance/loader. | Cancel tasks, shut down executors, unregister listeners, join/terminate threads properly. |
| **Reflection/method caches** | Cache holds plugin `Class<?>`, `Method`, `Constructor`, `MethodHandle`/factory. | Scope caches, clear on unload, key caches by lifecycle. |
| **ThreadLocal** | Platform thread-pool thread-local value points to plugin class/object. | Call `remove()` in the right lifecycle scope; avoid storing long-lived plugin contexts. |
| **EventBus, JDBC/driver, service registry** | Listener/driver/provider registered by plugin was never unregistered. | Perform cleanup via the corresponding registration API. |
| **Misdesigned weak-key cache** | Value holds a strong back-reference to the `ClassLoader` key. | Inspect value → key graph; weak keys alone do not guarantee reclamation. |

Example of **Thread Context ClassLoader** (illustrative snippet for a reusable thread):

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

Here `pluginLoader` and `runPluginTask()` belong to a real application; **this snippet is not a standalone Java program**. The key point is preventing a thread pool from holding an old plugin's TCCL after the task finishes.

### The `WeakHashMap` Trap

The snippet below **does not guarantee** the loader can be GC'd:

```java
Map<ClassLoader, Class<?>> cache = new WeakHashMap<>();
cache.put(pluginLoader, generatedClass);
```

If `generatedClass` was defined by `pluginLoader`, the `Class<?>` value keeps the loader alive. The chain map → **strong value** → class/loader → key pins the key, defeating weak keys. This is an **illustrative snippet**, not a recommended caching pattern. Use lifecycle-scoped caches or weak structures covering **both keys and values/graphs**.

Another misconception: `URLClassLoader.close()` mainly closes resources like files/JARs opened by the loader; **closing does not mean the JVM immediately unloads all classes of that loader**. You still must drop references and wait for unloading conditions.

## 4. Reading Three Metric Groups Correctly: Class Count, Metaspace, and Loader Count

To diagnose effectively, **do not look at a single Metaspace-used chart**. Track simultaneously:

1. **Class loading:** currently loaded classes, total ever loaded, and total unloaded.
2. **Metaspace:** `used`, `committed`, and (when available) `reserved`; also watch Compressed Class Space.
3. **Class loaders:** loader count and distribution of classes/metadata per loader or loader type.

### 4.1. `ClassLoadingMXBean` (Standard Java)

`java.lang.management.ClassLoadingMXBean` exposes three key counters:

| API | Meaning |
| --- | --- |
| `getLoadedClassCount()` | Number of classes **currently loaded**. |
| `getTotalLoadedClassCount()` | Total classes **loaded since JVM start** (cumulative counter). |
| `getUnloadedClassCount()` | Total classes **unloaded since JVM start** (cumulative counter). |

Because of cumulativeness:

```text
deltaCurrentlyLoaded
    ≈ deltaTotalLoaded - deltaUnloaded
```

The `≈` reminds you that reading individual counters is not a single atomic snapshot if the app is actively loading/unloading classes. **Steadily rising total loaded alone does not prove a leak**: that counter only increases even when classes unload normally. Compare *currently loaded* and *unloaded* alongside warm-up/deploy context.

### 4.2. `MemoryPoolMXBean` for Metaspace

Use `ManagementFactory.getMemoryPoolMXBeans()` to inspect pools named `Metaspace` and `Compressed Class Space` (on supporting HotSpot). `MemoryUsage.getUsed()` and `getCommitted()` report **bytes**, not KB; convert units when printing.

`getMax()` may return `-1` if the JVM/pool has no fixed maximum configured. Never interpret `-1` as "infinite real RAM." Container memory, OS limits, virtual address space, and other JVM bounds can still cause allocation failure.

### 4.3. Which Patterns Are Suspect?

| Observation Over Time | Reasonable Interpretation |
| --- | --- |
| Startup: loaded classes and Metaspace rise, then flatten after warm-up | Usually normal class loading/JIT/framework initialization. |
| On every plugin reload: loader count and loaded classes rise; unloaded stays flat; Metaspace used keeps growing | **Suspect retained old loaders**; locate GC roots and compare against active plugins. |
| Total loaded rises, unloaded rises too, currently loaded stays flat | Lifecycle class creation and unloading; no leak proven yet. |
| Metaspace committed stays flat after used drops | Memory regions/chunks may be kept for reuse, not necessarily a leak. |
| Metaspace used rises while class count stays relatively steady | Metadata changes on classes, GC/reclamation lag, caches, or accounting; investigate further before blaming loader count. |
| NMT `Class` shows huge `reserved` yet small `committed` | Cannot conclude physical RAM usage equals `reserved`. |
| `OutOfMemoryError: Compressed class space` | Check compressed class space settings and class churn; do not conflate with heap OOME. |

A **strong signal** is a repeatable trend across multiple deploy/workload cycles backed by verified reachability, **not a single snapshot**.

## 5. Diagnostic Tools on a Live JVM: `jcmd`, NMT, and Logs

Suppose the application JVM has PID `12345` (**illustrative only; replace with real PID**). Use a compatible JDK, proper attach permissions, and the same host/PID namespace if containerized.

### 5.1. Listing Loaders, Class Counts, and Metaspace

```bash
jcmd -l
jcmd 12345 help VM.classloader_stats
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.classloaders
jcmd 12345 VM.metaspace basic
```

- `VM.classloader_stats`: class loader statistics, class counts, and metadata-region metrics. Output may include `ClassLoader`, `CLD*`, `Classes`, `ChunkSz`, `BlockSz`, or other layouts depending on JDK.
- `VM.classloaders`: prints loader hierarchy. `show-classes` lists classes, though output is very long and potentially costly; check `help` first.
- `VM.metaspace basic`: basic Metaspace stats; less detailed and per HotSpot docs avoids requiring a safepoint for `basic` mode.
- `VM.metaspace`: richer detail; `show-loaders`/`show-classes` can be used for deep dives when impact is acceptable.

Example:

```bash
jcmd 12345 help VM.metaspace
jcmd 12345 VM.metaspace show-loaders
```

**Operational note:** `VM.metaspace` is classified by JDK docs as **Impact: Medium**, depending on class count; avoid running verbose options back-to-back on overloaded production hosts. In Docker/Kubernetes, host PIDs may differ and `jcmd` may be absent from minimal runtime images. Verify `jcmd` sees the JVM with matching effective user/permissions.

### 5.2. Native Memory Tracking (NMT)

NMT is helpful for tracking HotSpot-managed native categories, including **Class/metadata**. It **does not cover all native allocations from external libraries**.

**Enable at JVM startup** (you cannot use `jcmd` to enable NMT for the first time on a running JVM that started without NMT):

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

In an authorized admin terminal once warmed up:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
```

After a period of class loading/reloading:

```bash
jcmd 12345 VM.native_memory summary.diff
```

`summary.diff` reports changes from the baseline across native memory categories such as `Class`. Distinguish `reserved`, `committed`, and internal metadata metrics. Do not interpret the `Class` category as *bytes of `ClassLoader` objects on the Java heap*. NMT adds overhead; deliberately choose `summary` vs. `detail` as needed.

If NMT is not enabled, `VM.native_memory summary` may report tracking is not active. **Never treat that as "0 native bytes."**

### 5.3. Class Load/Unload and GC Logs

On HotSpot with unified logging (Java 9+), you can use:

```bash
java -Xlog:class+unload=info -jar app.jar
```

In a lab, `class+unload` logs help verify which classes **actually unloaded** after a loader became unreachable. Seeing no unload logs in the first few seconds does not prove a leak: no suitable GC ran, collection conditions were not met, the event has not happened, or logging was off.

Collect GC logs/heap metrics via standard operational configs. Raising class-loading log verbosity in production can create huge output; enable selectively.

### 5.4. How JFR and Heap Dumps Complement Each Other

- **JFR** (when relevant events are enabled): observes class-load/unload activity and Metaspace changes over time; e.g., `jdk.ClassLoad`, `jdk.ClassUnload`, `jdk.ClassLoadingStatistics`, `jdk.MetaspaceSummary` in supporting versions/configs. Check `jfr summary file.jfr` and metadata rather than assuming every event is present.
- **HPROF Heap Dump + Eclipse MAT**: finds **reference paths keeping `ClassLoader`/`Class<?>`/plugin instances alive**, such as registries, `ThreadLocal`s, thread context class loaders, or event listeners. Use *Path to GC Roots* / *Dominator Tree* to investigate why a loader stays reachable. Heap dumps **do not directly measure total metadata bytes residing in native Metaspace**.
- **`GC.class_histogram`**: shows counts of `ClassLoader`, `Class<?>`, and instances on the heap, yet `#bytes` is **shallow bytes of Java heap objects**; it **does not replace** `VM.metaspace` or NMT.

Heap dumps can be very large, cause pauses, and contain sensitive data. Capture only with authorization and sufficient resources, following appropriate security procedures.

## 6. Java 17+ Hands-On: One New Loader Generates One Proxy Class — Hold or Release?

Goal: use **pure JDK APIs** to generate many **dynamic proxy classes**. No Byte Buddy, CGLIB, Spring, or external libraries required. We create **100 distinct `ClassLoader` instances** and generate **one proxy class per loader** using `Proxy.newProxyInstance`. Repeating the same `loader + interface` on **the same loader** normally reuses the generated class; hence the demo intentionally creates a new loader each time.

Create **`LoaderMetaspaceDemo.java`**:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.lang.ref.WeakReference;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class LoaderMetaspaceDemo {
    public interface Greeting {
        String say();
    }

    private static final List<ClassLoader> RETAINED = new ArrayList<>();
    private static final List<WeakReference<ClassLoader>> WATCH = new ArrayList<>();

    private static void makeProxies(int count, boolean retain) {
        for (int i = 0; i < count; i++) {
            ClassLoader loader = new ClassLoader(Greeting.class.getClassLoader()) {};
            Object proxy = Proxy.newProxyInstance(
                    loader, new Class<?>[]{Greeting.class},
                    (object, method, args) -> "hello");
            if (!Proxy.isProxyClass(proxy.getClass())) {
                throw new AssertionError("Expected generated proxy");
            }
            WATCH.add(new WeakReference<>(loader));
            if (retain) {
                RETAINED.add(loader);
            }
        }
    }

    private static void show(String stage) {
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();
        long reachableLoaders = WATCH.stream().filter(ref -> ref.get() != null).count();
        System.out.printf("%s: loaded=%d totalLoaded=%d unloaded=%d weakAlive=%d retained=%d%n",
                stage, classes.getLoadedClassCount(),
                classes.getTotalLoadedClassCount(), classes.getUnloadedClassCount(),
                reachableLoaders, RETAINED.size());

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getName().equals("Metaspace")
                    || pool.getName().equals("Compressed Class Space")) {
                MemoryUsage usage = pool.getUsage();
                if (usage != null) {
                    System.out.printf("  %s usedKiB=%d committedKiB=%d%n",
                            pool.getName(), usage.getUsed() / 1024,
                            usage.getCommitted() / 1024);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!args[0].equals("hold") && !args[0].equals("release"))) {
            System.out.println("Usage: java LoaderMetaspaceDemo hold|release");
            return;
        }

        boolean retain = args[0].equals("hold");
        System.out.println("mode=" + args[0]);
        makeProxies(100, retain);
        show("after-create");

        System.gc(); // Hint only; does not guarantee immediate unloading.
        Thread.sleep(800);
        show("after-gc-hint");

        System.out.println("Press Enter to exit...");
        System.in.read();
    }
}
```

Compile with **Java 17** (even if your installed JDK is newer):

```bash
javac --release 17 LoaderMetaspaceDemo.java
```

### 6.1. `hold` Mode: Intentionally Retaining Loaders

Terminal A:

```bash
java -Xms64m -Xmx192m LoaderMetaspaceDemo hold
```

Lines with **fixed structure**, while metrics vary by system:

```text
mode=hold
after-create: loaded=... totalLoaded=... unloaded=... weakAlive=... retained=100
  Metaspace usedKiB=... committedKiB=...
  Compressed Class Space usedKiB=... committedKiB=...
after-gc-hint: loaded=... totalLoaded=... unloaded=... weakAlive=... retained=100
  Metaspace usedKiB=... committedKiB=...
  Compressed Class Space usedKiB=... committedKiB=...
Press Enter to exit...
```

The `...` placeholders above **only indicate varying numbers, not literal output**. If the JVM does not use a Compressed Class Space pool, those lines may be absent. `RETAINED` is a **static strong-reference list** in a class loaded by the app loader; it retains 100 child loaders, thereby pinning 100 generated proxy classes and their metadata.

**When `Press Enter` appears**, keep the process running, open Terminal B to inspect metrics, and press Enter afterward to exit.

### 6.2. `release` Mode: Not Strongly Retaining Loaders

After exiting the `hold` process, launch a fresh process:

```bash
java -Xms64m -Xmx192m LoaderMetaspaceDemo release
```

In this mode, `RETAINED` stays empty; `WATCH` holds only **`WeakReference<ClassLoader>`**. Once `makeProxies` returns, the demo deliberately holds no strong references to the newly created loaders. After GC you may observe:

- `weakAlive` drops, possibly to 0.
- `unloaded` rises as generated proxy classes get a chance to unload.
- Metaspace `usedKiB` and Compressed Class Space `usedKiB` may drop.
- `committedKiB` may drop **or stay flat** due to VM memory management.

**No numbers are guaranteed**: JIT, JVM version, GC, class loading from management APIs, and timing alter results. `System.gc()` is only a *hint*; the JVM may ignore it or skip unloading (`-XX:+DisableExplicitGC`, collector behavior, etc.). **Never use `System.gc()` as a leak fix in production.**

### 6.3. Collecting External Metrics While Waiting

In Terminal B, find the actual PID from `jcmd -l` or process listings. Replace `12345` with the actual PID:

```bash
jcmd -l
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.metaspace basic
jcmd 12345 VM.metaspace show-loaders
```

You can capture both during `hold` and during `release` before exiting. Compare:

- `ClassLoader`/class counts at measurement time.
- `loaded`, `unloaded` from the demo program.
- Metaspace `used`/`committed`.
- The difference between **strong retention** and **no intentional strong retention**.

To verify unloading via logs, re-run either mode with:

```bash
java -Xlog:class+unload=info -Xms64m -Xmx192m LoaderMetaspaceDemo release
```

### 6.4. Why Is This a Meaningful Experiment?

1. `Greeting` is a **public interface** defined by the app loader so child loaders see it via delegation.
2. `new ClassLoader(Greeting.class.getClassLoader()) {}` creates a **new child loader object** on every iteration.
3. `Proxy.newProxyInstance(...)` generates or looks up the proxy class for that loader and interface; because loaders differ, the proxy classes have **distinct type identities**.
4. `WATCH` holds weak references: lets us observe whether loaders were GC'd without pinning them alive.
5. `RETAINED` holds **strong references** in `hold`, simulating a registry/loader leak; in `release` it holds none, testing unloading **if the JVM performs it**.
6. `ClassLoadingMXBean` measures **class counts**, whereas `MemoryPoolMXBean` measures **Metaspace used/committed**. The two metrics have different units and meanings.
7. Querying via `jcmd` from a second terminal mirrors real live-JVM diagnostic workflows.

**Experiment limits:** the demo illustrates loader/proxy lifecycles, not full framework caching. Do not compare raw numbers across two processes as a performance or memory-size benchmark across all JVMs; compare **trends and loader creation/retention conditions**.

## 7. Production Case Study: Metaspace Grows on Every Hot-Reload

Suppose a service supports reloading rule sets or plugins without restarting the JVM. Each deploy of a new plugin version creates a new loader.

Simulated report across several business load/unload cycles (**numbers below are illustrative, not real JVM output**):

| Phase | Active Plugins | Reachable Class Loaders | Currently Loaded Classes | Metaspace Used |
| --- | ---: | ---: | ---: | ---: |
| After warm-up | 1 | 1 plugin-related | 8,000 | 90 MiB |
| After 5 reloads | 1 | 6 plugin-related | 13,500 | 145 MiB |
| After 10 reloads | 1 | 11 plugin-related | 19,000 | 205 MiB |
| After cleanup + proper GC | 1 | 1 plugin-related | 8,500 | 98 MiB |

**Proper analysis steps:**

1. Record reload timestamps, permitted active plugin counts, JDK/GC, and request rate.
2. Capture `VM.classloader_stats` every few reloads; see whether **old** loaders remain with similar class counts.
3. Track `ClassLoadingMXBean`: `getTotalLoadedClassCount()` should rise if new classes are created; the problem is `getLoadedClassCount()` failing to drop and `getUnloadedClassCount()` failing to rise as lifecycles end.
4. Track Metaspace used/committed, NMT `Class`, and GC/class-unload logs to corroborate the same trend.
5. Capture a heap dump if authorized and resourced. Use MAT **Path to GC Roots** to find the chain holding old loaders, e.g., `PluginRegistry -> historicalContexts -> ClassLoader` or a pool thread's `contextClassLoader`.
6. Audit cleanup code on unload: deregister listeners/drivers, cancel tasks, clean up `ThreadLocal`/TCCL, and clear reflection/proxy caches no longer needed.
7. Replay equivalent workload and measure before/after. **Dropping loaded classes/Metaspace across multiple cycles** is far better evidence than one `System.gc()` showing no change.

If loader count rises only with **truly active** plugins, there is not necessarily a leak. If Metaspace used rises and plateaus as caches warm, there is not necessarily a leak. **You need a lifecycle expected to end whose references were not dropped.**

## 8. Diagnosing Root Cause: Who Is Holding Which Class Loader?

When suspecting a leak, find the **retaining path** instead of merely bumping Metaspace limits.

### Reference-Path Checklist

```text
GC root
  ├─ singleton/static registry -> PluginContext -> PluginClassLoader
  ├─ pool Thread -> contextClassLoader -> PluginClassLoader
  ├─ pool Thread -> ThreadLocal value -> plugin instance -> PluginClassLoader
  ├─ scheduler/Executor -> pending task -> closure -> plugin class/instance
  ├─ event bus -> listener -> plugin instance
  └─ reflection/proxy cache -> Class<?>/Method -> PluginClassLoader
```

This is a **diagram of possibilities**, not an assertion that every JVM app has all of these paths.

Common heap-dump clues:

- Multiple class loader objects of the same type/name tied to old plugin deployments.
- A long-lived registry holding a cache that grows with every reload.
- A plugin-spawned thread that never stopped, or an executor holding stale `ThreadLocal` values.
- `Class<?>`/reflection objects from an old loader still held by an application singleton.

**Do not wipe caches blindly:** class/proxy caches may be vital for correctness and performance. Design around scope/TTL/lifecycle, test in-flight requests, and never tear down a loader while its classes are still needed.

### Design Principles for Hot-Reload Systems

- **Clear lifecycle:** `load -> active -> quiesce -> close/unregister -> drop references -> observe unload`.
- **Scope caches by loader/plugin version:** avoid global caches holding every `Class`, `Method`, factory, or bytecode model forever.
- **Restore TCCL:** use `try/finally` whenever temporarily switching context class loaders.
- **Clean `ThreadLocal`s and background tasks:** `remove()` on the right thread, unregister listeners, shut down plugin-owned executors.
- **Reuse classes/proxies when valid:** avoid generating new class definitions per request when a shared class/cache suffices.
- **Avoid maps whose values point back to loaders:** weak keys alone do not guarantee collection.
- **Maintain long-term monitoring:** class load/unload rates, loader count after each reload, Metaspace used/committed, OOMEs, and container RSS.

## 9. Metaspace OOME: Raise the Limit or Fix a Leak?

Two common errors:

```text
java.lang.OutOfMemoryError: Metaspace
java.lang.OutOfMemoryError: Compressed class space
```

Distinguish the cause:

| Cause Category | Example | Appropriate Response |
| --- | --- | --- |
| **Configured cap too low** | Legitimate app needs many classes, yet `-XX:MaxMetaspaceSize` is set too small. | Measure actual live set/peak and tune within total memory budget. |
| **Class-loader leak** | Old loaders retained by static registry/threads after every deploy. | Fix retaining path; raising cap only postpones OOME. |
| **Excessive class generation despite valid lifecycles** | Compiling expressions or creating new proxies per request/tenant. | Reduce class churn, cache/cap versions, avoid unnecessary class generation. |
| **GC/unloading not triggered as expected** | Lack of suitable collector cycles, or flags disabling class unloading. | Check GC logs/config; never rely on `System.gc()` as a guarantee. |
| **Native/container memory exhausted** | Heap + Metaspace + thread stacks + code cache exceed memory limit. | Inspect total process budget, NMT/OS/container; do not adjust `-Xmx` alone. |

Key HotSpot options to know:

- `-XX:MaxMetaspaceSize=...`: **upper limit** on total Metaspace under HotSpot rules; exceeding it can throw `OutOfMemoryError: Metaspace`.
- `-XX:MetaspaceSize=...`: threshold influencing when the JVM considers GC due to metadata pressure; **not a setting forcing Metaspace to pre-allocate that exact number of bytes**.
- `-XX:CompressedClassSpaceSize=...`: caps compressed class space when compressed class pointers are enabled; distinct from heap `-Xmx`.
- `-XX:NativeMemoryTracking=summary` or `detail`: enables NMT from startup; incurs overhead.
- Class unloading/GC flags vary by JDK and collector; inspect `java -XX:+PrintFlagsFinal` or `jcmd <PID> VM.flags -all` when needed, and **never change production flags just to force an experiment**.

**There is no single "best MaxMetaspaceSize for every service."** A service running plugins, framework proxies, or many tenants/versions needs a different budget. Base decisions on post-warm-up baseline, deploy peaks, headroom, and container memory limits; keep monitoring and OOME alerts active.

## 10. Quick Table of Common Misconceptions

| Hasty Claim | Accurate Understanding |
| --- | --- |
| "Creating 1 million objects grows Metaspace 1 million times." | Objects of the same class share class metadata; instances live on the heap. |
| "Calling reflection or `Class.forName` repeatedly creates new classes." | Same name and defining loader normally yield one class definition; distinguish **loading** from **lookup**. |
| "Two classes with the same name are always the same type." | Runtime type identity also depends on the defining class loader. |
| "One proxy instance = one new proxy class." | JDK proxy classes reuse per loader/interface; creating new loaders is what multiplied classes in the demo. |
| "Just drop proxy instances and Metaspace shrinks automatically." | If the loader is still pinned by a registry/thread/cache, class metadata stays. |
| "Parent loaders always retain all child loaders." | Children reference parents; the reverse requires an **actual reference path**, never assumed. |
| "A static field in a plugin always leaks the loader." | Internal cycles inside a loader do not leak if the whole group is unreachable from external GC roots. |
| "`WeakHashMap<ClassLoader, Class<?>>` always prevents leaks." | The value can pin the key/loader alive, defeating weak keys. |
| "`URLClassLoader.close()` unloads all classes immediately." | `close()` frees some loader resources; unloading requires reachability and JVM GC. |
| "`System.gc()` guarantees unloading." | It is only a hint, which may be ignored or skip class unloading. |
| "Metaspace reserved = RAM in use." | Reserved is virtual address space; check committed/used and actual RSS. |
| "NMT `Class` is bytes of `ClassLoader` objects on the heap." | NMT measures JVM native categories; heap objects live in a separate region. |
| "Total loaded classes rising => leak." | Cumulative counters always grow; check **currently loaded, unloaded**, loader counts, and lifecycle. |
| "A larger `-Xmx` fixes Metaspace OOME." | `-Xmx` caps the heap, not native metadata leaks or caps. |
| "Raising `MaxMetaspaceSize` is a root fix." | Necessary when configured too low, yet **never replaces** fixing retaining paths on a leak. |

## 11. Actionable Diagnostic Workflow

**Before reproducing:**

1. Record PID, JDK version, GC, heap limit, metaspace limit, container memory limit, and startup/warm-up/deploy timestamps.
2. Capture baseline `VM.classloader_stats`, `VM.metaspace basic`, and `ClassLoadingMXBean` metrics.
3. If NMT is enabled, capture `VM.native_memory baseline`; if not, plan enabling it at an approved restart rather than trying via `jcmd` at runtime.

**During controlled load/redeploy:**

4. Repeat the exact same business/reload operation with matching counts and intervals.
5. Capture loaded/unloaded class counts and Metaspace used/committed across multiple checkpoints; count remaining old loaders.
6. Inspect class-unload logs/JFR when available, noting thresholds and observation overhead.
7. If old loaders persist abnormally, find GC roots of **specific loaders** via heap dump.

**When concluding:**

8. Verify whether those loaders/classes **should have been released**, or still belong to active plugins.
9. Document the exact strong retaining path and fix point: static registry, thread context, listener, cache, task.
10. Re-measure after the fix across multiple runs: do old loaders vanish, does `unloaded` rise appropriately, and does Metaspace stabilize under load? Do not demand `committed` or RSS drop immediately to a fixed number.

**Responsible conclusion statement:** "After 10 reloads, reachable old loaders grew from 0 to 10 and Metaspace used kept climbing; heap dump shows a static registry holding the old loaders. After removing registry entries and unregistering listeners, loaders became eligible to unload and Metaspace stabilized." This is far stronger than "Metaspace grew, so Java has a leak."

## 12. Self-Check Questions

1. **Why do many instances of the same class not increase class definitions proportionally?** Because instances share the class metadata defined by one loader.
2. **Are two classes with the same name defined by two loaders the same type?** No. The defining loader is part of runtime type identity.
3. **Which metrics distinguish class churn from a class leak?** Combined currently loaded, total loaded, unloaded, loader count, Metaspace used, and lifecycle; **total loaded alone is insufficient**.
4. **Why can a weak-key-only cache still retain a loader?** The value may reference a class of that loader, linking back to the key/loader and creating a strong reference path.
5. **Does `URLClassLoader.close()` alone guarantee unloading?** No; strong references must be dropped and appropriate GC/class unloading must run.
6. **How do `VM.classloader_stats` and `GC.class_histogram` differ?** The former focuses on loaders/classes/metadata; the latter summarizes instance counts and shallow bytes on the Java heap.
7. **If Metaspace committed does not drop while used drops, is it definitely a leak?** No; committed regions may be retained by the JVM for reuse.
8. **Why is `System.gc()` in the demo not an absolute proof?** Because it is only a hint; GC and unloading are not guaranteed immediately.
9. **Why does a thread pool's TCCL matter?** Threads outliving a plugin can retain an old loader via `contextClassLoader`.
10. **When is increasing `MaxMetaspaceSize` reasonable?** When measurements show legitimate live metadata needs more than currently configured and memory budget allows; never treat it as a fix for a loader leak.

## Official References

- [Java SE 21 — Optimizing Metadata Memory / Metaspace](https://docs.oracle.com/en/java/javase/21/gctuning/other-considerations.html).
- [Java SE 21 — `jcmd`: `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`, `VM.native_memory`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Java SE 21 — Native Memory Tracking: enable, baseline, and diff](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html).
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).
- [Java SE 21 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).
- [Java Language Specification §12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7).
- [Java SE 21 — Dynamic Proxy API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html).
