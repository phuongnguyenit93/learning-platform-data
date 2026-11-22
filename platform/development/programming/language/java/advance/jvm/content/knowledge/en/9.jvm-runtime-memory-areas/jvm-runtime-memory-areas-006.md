# HotSpot Metaspace, Compressed Class Space, and Differences from Historical PermGen

## 1. Objectives and Scope of the Lesson

In a Java application running on the **HotSpot JVM**, memory does not consist solely of the **Java heap** for holding application objects. The JVM also uses other memory areas for thread stacks, the JIT code cache, native structures, and especially the **metadata of loaded classes/interfaces**.

Starting from **JDK 8**, HotSpot removed the **Permanent Generation (PermGen)**, which was the old implementation of the region storing class metadata, and replaced it with **Metaspace**, which uses native memory instead of PermGen managed by GC in the historical way. On 64-bit HotSpot configurations with **compressed class pointers**, a portion of the metadata related to class structure is placed in the **compressed class space**, logically separated from the remaining metadata area.

Three concepts must be distinguished:

1. **PermGen:** the legacy generation belonging to HotSpot implementations prior to JDK 8; it is not a mandatory component in the Java Virtual Machine Specification (JVMS).
2. **Metaspace:** the memory allocation and management mechanism for class metadata in HotSpot from JDK 8 onward, using **native memory**.
3. **Compressed class space:** the address region reserved for the portion of class metadata accessible via **compressed class pointers**, which is only meaningful in HotSpot configurations that support and enable this feature.

After completing this lesson, you should be able to answer:

- What does Metaspace store, and how does it differ from the Java heap and the conceptual method area?
- Why does `-Xmx` not directly limit Metaspace?
- How do compressed class pointers relate to `CompressedClassSpaceSize`?
- How do **reserved** and **committed** numbers differ?
- When is class metadata freed, and why can a class loader leak cause `OutOfMemoryError: Metaspace`?
- How can you inspect it using `jcmd`, Native Memory Tracking, logs, and HotSpot flags?
- Should you tune flags or fix the class loader lifecycle when Metaspace usage grows continuously?

**Scope:** this is a lesson about the **HotSpot implementation** and its implementation history, not a claim that every JVM from every vendor must have a region named Metaspace or compressed class space.

## 2. Method Area Is a JVM Concept; Metaspace Is a HotSpot Implementation

### 2.1. What does the JVMS say about the method area?

The **method area** is a runtime data area **shared among JVM threads** that stores per-class structures such as class information, the runtime constant pool, method and field code, as well as data serving the JVM according to the specification model. The JVMS describes the *responsibilities/semantics* of the method area, but **does not require a single physical memory management scheme**.

The implementation can vary by JVM distribution, version, architecture, GC, and optimizations. Therefore:

> **Do not write "method area = Metaspace" as an identity that applies to every JVM.**

A more accurate phrasing is: **HotSpot uses the Metaspace mechanism to allocate many native class metadata structures that serve the functions of the method area in the JVM**.

### 2.2. Conceptual Map

```text
                      HotSpot JVM Process
┌─────────────────────────────────────────────────────┐
│ Java heap (managed by Java GC)                      │
│  - Java instances, array objects                    │
│  - java.lang.Class mirror (Java object)             │
│  - Strings, collections, and application objects    │
├─────────────────────────────────────────────────────┤
│ VM Native / non-heap memory                         │
│  - Metaspace: class metadata, non-class metadata    │
│  - Compressed class space (when enabled)            │
│  - Code cache, thread/native stacks                 │
│  - Other VM/native structures                       │
└─────────────────────────────────────────────────────┘
```

The diagram **does not depict the exact layout of memory addresses**. It only distinguishes the responsibilities of the memory types.

Common points of confusion:

- `java.lang.Class` is a **Java object mirror**, not the entire native data describing the class itself.
- **Instances** created with `new MyClass()` belong to the **Java heap**; they do not move into Metaspace just because they are instances of a loaded class.
- HotSpot's **metadata structures**, such as structures representing class information, can reside in Metaspace.
- You cannot conclude that **all static field values** reside in Metaspace. In particular, the object that a static reference points to is still a Java object in the heap; the exact placement details of static fields and mirrors belong to the runtime implementation.

### 2.3. "Non-heap" in MXBean Does Not Mean a Single Memory Region

The Java Management API has `MemoryType.NON_HEAP` and `MemoryPoolMXBean`. Tools may report pools such as **Metaspace**, **Compressed Class Space**, and **CodeHeap/code cache**, depending on HotSpot/JDK/configuration.

However, **the total native memory of the process** is not equal to just "Metaspace + code cache" or only `MemoryMXBean.getNonHeapMemoryUsage()`. Thread stacks, GC native structures, symbol tables, allocator overhead, native libraries, and other regions can all increase the process's resident memory.

Therefore, when the OS reports increasing RSS, **do not immediately attribute the entire increase to Metaspace**.

## 3. What Was PermGen Before JDK 8?

### 3.1. Permanent Generation Was a Legacy HotSpot Structure

In HotSpot versions prior to JDK 8, class metadata was managed in a region named **Permanent Generation**, commonly called **PermGen**. It was a memory generation/region in the GC and VM organization of that era, separate from the generations holding ordinary Java application objects.

Some historical flags:

```text
-XX:PermSize=...
-XX:MaxPermSize=...
```

These flags were used to tune PermGen in older compatible HotSpot releases. When the limit was exceeded in a situation where enough could not be freed, you could see the error:

```text
java.lang.OutOfMemoryError: PermGen space
```

**Do not use `PermSize`/`MaxPermSize` to configure HotSpot JDK 17+.** PermGen has not been HotSpot's class metadata storage mechanism since JDK 8.

### 3.2. The Transition Was Not "Moving All of PermGen As-Is Into Metaspace"

Interpreting this as "JDK 8 simply renamed PermGen to Metaspace" is wrong.

In substance:

- HotSpot **removed the Permanent Generation**.
- Class metadata was moved to a **metadata management area in native memory**.
- The allocator mechanism, threshold tuning, accounting, and memory reclamation changed.
- Components that used to be grouped together in legacy descriptions **did not all end up verbatim in Metaspace**.

An important example: **interned strings** were already moved out of PermGen into the Java heap in some HotSpot releases before JDK 8, notably from JDK 7. It is incorrect to say "JDK 8 moved the entire string pool from PermGen to Metaspace". Java `String` objects belong to the heap; the String table and lookup structures have their own native details.

### 3.3. Historical Milestones

| Period | Metadata Management Mechanism in HotSpot | Notes |
| --- | --- | --- |
| JDK 6/7 and pre-JDK 8 | **PermGen**, with limits/flags appropriate to the JVM version | Class metadata associated with Permanent Generation |
| **JDK 8** | **PermGen removed; native Metaspace used** | Main content of OpenJDK **JEP 122** |
| JDK 9–15 | Metaspace continued to evolve | Detailed behavior depends on version and platform |
| **JDK 16 and later** | **Elastic Metaspace** from **JEP 387** | Improved reuse and returning committed memory to OS upon unloading |
| JDK 17/21/25+ | Metaspace/Compressed class space in modern HotSpot | Flags, ergonomics, and accounting may differ across JDKs |

**"Elastic Metaspace" does not mean Metaspace can never OOME**; it improves management/reclamation capabilities but does not eliminate metadata limits or class loader retention bugs.

## 4. What Does Metaspace Store and How Is It Allocated?

### 4.1. What Kinds of Information Does Class Metadata Include?

HotSpot needs native data to understand and execute loaded classes, such as:

- Information describing a class/interface, class hierarchy, and method/field descriptors.
- Metadata serving runtime method/constant-pool access, linking, and dispatch.
- Structures related to methods and classes that HotSpot maintains outside the Java object heap.
- Information related to class-loader data and allocators dedicated to metadata.

You should not naively describe it as "Metaspace holds all bytecode, all `Class` objects, static objects, and JIT compiled code". **JIT compiled machine code** is primarily managed in the **code cache**, not Metaspace; Java object mirrors exist on the heap.

### 4.2. Tied to Class Loaders and Chunks

Conceptually, HotSpot allocates metadata in structures tied to **class loaders/class-loader data**, using **chunks/arenas** managed by the metaspace allocator:

```text
ClassLoader A
   |
   +--> metadata allocations / arena A
             ├── class metadata A1
             ├── method metadata A1
             └── class metadata A2

ClassLoader B
   |
   +--> metadata allocations / arena B
             ├── class metadata B1
             └── ...
```

This diagram is a **management model**, not an exact heap dump. Its purpose is to emphasize that class metadata has a lifecycle tied to **class loader/data**. When a class loader and its classes can be unloaded, HotSpot has the opportunity to reuse or return chunks/memory portions.

### 4.3. A Class Name Does Not Uniquely Determine Metadata

In the JVM, a nonarray runtime class is identified by its **binary name and defining class loader**. Two different loaders can define two classes bearing the same name, resulting in two runtime classes and **two separate sets of metadata**.

If an application continuously creates custom loaders and defines the same class in each loader while keeping all loaders alive, Metaspace can continue to grow even though the `.class` file on disk does not change.

This is a common source of **class-loader retention** and Metaspace pressure in plugin systems, application servers, test runners, or bytecode generation.

### 4.4. Metadata Is Not Freed Immediately Just Because a Variable Is Set to Null

```java
Object instance = new SomeType();
instance = null;
```

This is an **illustrative snippet**, assuming `SomeType` exists. Clearing a reference to an instance **does not mean unloading class SomeType**. The class may still be in use by many objects, threads, static references, loaders, reflection caches, running methods, and VM structures.

For class metadata to be reclaimed, the conditions for **class unloading** must be met; this process is tied to GC and actual reachability. There is no standard Java API to "free this class metadata immediately".

## 5. Compressed Class Pointers and Compressed Class Space

### 5.1. What Are "Compressed Class Pointers"?

On some **64-bit HotSpot** configurations, the VM can use a pointer representation referencing **class metadata** in a compressed encoding form. The common flag is:

```text
-XX:+UseCompressedClassPointers
```

This is **different** from **compressed ordinary object pointers (compressed oops)**, typically controlled by:

```text
-XX:+UseCompressedOops
```

The two pointer types must be distinguished:

| Mechanism | Purpose | Reference Example |
| --- | --- | --- |
| **Compressed oops** | Compresses the representation of a reference from one Java object to another Java object | A field holding a reference to a `String` |
| **Compressed class pointers** | Compresses how the object header/runtime structures reference class metadata | Class metadata pointer corresponding to the object's runtime type |

Although related in HotSpot configuration, these are **not the same kind of data**. You should not say "enabling compressed oops automatically shrinks every metadata structure by a fixed ratio".

### 5.2. Where Does Compressed Class Space Reside?

When HotSpot enables compressed class pointers, the VM uses a separate region, called the **compressed class space**, to hold the class metadata structures that need to reside within a range representable by the compressed class pointers mechanism.

```text
Native memory for class metadata (model)
┌───────────────────────────────────────────┐
│ Non-class metadata / Metaspace allocator  │
│  - much metadata outside class-space      │
├───────────────────────────────────────────┤
│ Compressed class space (when enabled)     │
│  - metadata needing compressed class ptrs │
│  - reserved address range                 │
│  - committed gradually on demand          │
└───────────────────────────────────────────┘
```

The name **"class space"** does not mean that the region holds Java `Class` objects on the heap. It holds native metadata managed by HotSpot.

**Do not equate compressed class space with the entirety of Metaspace.** It is a **logically separate metadata space** in configurations that have class pointer compression.

### 5.3. `-XX:CompressedClassSpaceSize`

The flag:

```text
-XX:CompressedClassSpaceSize=128m
```

adjusts the **size of the class space address space** reserved for the compressed class pointers representation, subject to VM limits and adjustments. On many traditional 64-bit HotSpot setups, the default is close to **1 GiB**, but **it is not an immutable value for every JVM, architecture, or JDK**. The VM may adjust the actual size when other flags impose limits or the configuration does not support it.

Important:

- **Reserved 1 GiB does not mean the process has already consumed 1 GiB of physical RAM** for class metadata.
- Class space **commits** the pages needed for use on demand.
- When class space is committed up to its available limit and cannot be freed/satisfied further, `OutOfMemoryError: Compressed class space` may appear.
- This flag does not directly limit the number of Java instances created on the heap.

### 5.4. Relationship with `-XX:MaxMetaspaceSize`

In HotSpot configurations with class space, `MaxMetaspaceSize` applies to the **total amount of committed metadata** to be managed, including non-class metadata and the committed portion of class space, according to the runtime's actual mechanism/limits.

Do not deduce a simple addition:

```text
MaxMetaspaceSize = ReservedCompressedClassSpaceSize + MaxNonClassMetaspace
```

This is a **wrong formula if used as a mandatory equality**. `CompressedClassSpaceSize` pertains to a **reserved address range/capacity** of class-space, whereas `MaxMetaspaceSize` is the **committed metadata ceiling** according to HotSpot, and the VM may adjust internal limits to ensure consistency.

For example, you might see:

```text
class space reserved:  ~1 GiB
class space committed: 20 MiB
non-class committed:   80 MiB
```

These are only **illustrative numbers**. The total committed metadata is about 100 MiB, not about 1.1 GiB. To draw conclusions about actual memory, you must look at **committed and used**, not just reserved.

## 6. How Do Reserved, Committed, Used, and Capacity Differ?

Metaspace data is very easy to misread, especially when monitoring container memory.

| Concept | General Meaning | What Should Not Be Inferred |
| --- | --- | --- |
| **Reserved** | Virtual address space set aside for the data region | Does not mean the corresponding amount of physical RAM is used |
| **Committed** | Memory portion that the VM/OS has committed for use under the underlying mechanism | Not necessarily the number of metadata bytes actually used |
| **Used** | Metadata memory currently in use to hold data per the VM's accounting | Does not mean the total native memory of the process |
| **Capacity** | Current allocation capacity in chunks/arenas per the corresponding statistics | Not a uniform configuration threshold across all JVM versions |

Fictional example:

```text
Metaspace:
  used       80 MiB
  capacity   90 MiB
  committed  96 MiB
  reserved   1200 MiB
```

In that model:

- 80 MiB of metadata is actually being used.
- The VM has committed 96 MiB for the corresponding metadata areas.
- The 1200 MiB reserved portion is a virtual address reservation and **should not be added wholesale to actual RAM in use**.
- Differences between used/capacity/committed may relate to allocator chunks, internal fragmentation, and allocation headroom.

**Specific fields/definitions depend on the HotSpot version's output.** When debugging, read the legend of the tool and version; do not blindly apply an old reporting definition to new output.

### 6.1. Why Can a Large "Metaspace Reserved" Still Be Normal?

A compressed class space can **reserve** a relatively large virtual address range to support compressed pointers while only **committing** a small portion. OS memory map tools may show a large reservation, while actual resident memory is much smaller.

If you see "1 GiB reserved class space" and conclude "the JVM is eating 1 GiB of heap", you have confused **virtual addresses**, **native metadata**, and the **Java heap**.

### 6.2. Committed Increases Without Used Increasing Proportionally?

This may relate to the metadata allocator retaining chunks for reuse, fragmentation, or reclamation strategy. On modern HotSpot after JEP 387, the VM improved its ability to return committed memory to the OS when classes unload, but there is no guarantee that any difference must drop to 0 immediately.

Measure over time, and read **used/committed/reserved** figures alongside class-loading statistics, GC, and other native memory metrics.

## 7. Common HotSpot Configuration Flags

| Flag | Role | Common Misconception |
| --- | --- | --- |
| `-Xmx512m` | Maximum **Java heap** limit | Not a cap on total process memory or Metaspace |
| `-XX:MetaspaceSize=128m` | Initial threshold related to metadata occupancy to trigger GC/class unloading; can change | **Not** "initialize Metaspace to exactly 128 MiB" or a hard limit |
| `-XX:MaxMetaspaceSize=256m` | Upper limit on metadata memory in HotSpot | Not a total resident process cap |
| `-XX:CompressedClassSpaceSize=128m` | Adjusts class-space reservation/usability when compressed class pointers are enabled | Not the amount committed immediately at startup |
| `-XX:+UseCompressedClassPointers` | Enables compressed class pointers when supported by the environment | Not general compression of Java object references |
| `-XX:-UseCompressedClassPointers` | Disables class-pointer compression when supported by the VM | Does not mean all class metadata disappears |
| `-XX:+UseCompressedOops` | Uses compressed ordinary object references when supported by the environment | Do not equate compressed oops with class-space |
| `-XX:MetaspaceReclaimPolicy=balanced` | Reclamation policy on HotSpot from JEP 387 | Does not solve a class-loader leak that is still reachable |
| `-XX:NativeMemoryTracking=summary` | Collects native memory metrics for `jcmd VM.native_memory` | Adds tracking overhead; must be enabled at JVM startup |

The flags above are **HotSpot-specific**, not mandatory options for every JVM. Version, architecture, GC, and ergonomics can change default values, flag interactions, or supportability.

### 7.1. Example of Setting Thresholds, Not Treated as a Standard Production Configuration

```bash
java -Xmx512m -XX:MaxMetaspaceSize=256m -XX:CompressedClassSpaceSize=128m MyApp
```

This is an **illustrative command** assuming `MyApp` has already been successfully built and is on the classpath. It is not a standalone Java exercise; you should not copy it into production without measuring class-loading behavior, container memory limits, and workload.

Effects:

- `-Xmx512m` limits the Java heap around the configured 512 MiB level (JVM details apply).
- `-XX:MaxMetaspaceSize=256m` sets the metadata ceiling.
- `-XX:CompressedClassSpaceSize=128m` adjusts the compressed class space region when available.

**Do not deduce that the maximum total RAM of the process is `512 + 256 + 128 = 896 MiB`**. Because class space is already tied to metadata limits, and thread stacks, code cache, GC native memory, and other regions also consume resources outside the heap. Computing the total by adding flags like that is wrong.

### 7.2. MetaspaceSize Differs from MaxMetaspaceSize

The names easily confuse learners:

- `MetaspaceSize` affects a **GC-related threshold** for metadata, which can be adjusted by the runtime.
- `MaxMetaspaceSize` is the **upper ceiling** for metadata allocation/commit enforced by the VM according to its policy.

Increasing `MetaspaceSize` can reduce early GCs caused by crossing the metadata threshold in some workloads, but **does not fix class loader retention**. Increasing `MaxMetaspaceSize` can extend the time before OOME if metadata can no longer be freed; **it does not solve the root cause**.

### 7.3. Check the Actual JVM Flags Instead of Inferring From a Wiki Command

Use:

```bash
java -XX:+PrintFlagsFinal -version
```

Then look for `MetaspaceSize`, `MaxMetaspaceSize`, `CompressedClassSpaceSize`, `UseCompressedClassPointers`, `UseCompressedOops` when supported by the runtime. The output is very long and varies by JDK; do not use a snapshot from another machine as the default parameters for every container.

For a running JVM, `jcmd <pid> VM.flags` allows viewing a subset of the actual flags.

## 8. Why Is Class Unloading Important for Metaspace?

### 8.1. Loaded Classes Do Not Disappear Automatically When a Method Returns

A loaded class can remain in the JVM for the entire lifetime of the application if its defining loader and class metadata remain reachable according to JVM/GC rules.

Common scenarios:

- Classes of bootstrap/platform/system/application loaders have long lifecycles.
- Plugins loaded via a custom `ClassLoader`.
- Frameworks generating many dynamic classes (proxies, bytecode enhancement).
- Application deployment reloads creating new loaders.
- Threads, `ThreadLocal`, listeners, caches, or static registries accidentally holding references to old loaders.

**Growing Metaspace does not necessarily prove a leak.** An application with warm-up, lazily loaded classes, or newly added modules can increase metadata and then stabilize. You need to observe the growth **over multiple operational/GC/unloading cycles**, rather than judging from a single measurement point.

### 8.2. Metadata Lifecycle and Unloading

```text
Load class / define class
          |
          v
Metadata allocated for class-loader data
          |
          v
Class still used / reachable? ---- yes ----> continue retaining metadata
          |
          no
          v
GC may unload class / loader when appropriate
          |
          v
Metaspace chunks are reused or
committed memory is reclaimed (JVM-dependent)
```

Class unloading is tied to reachability conditions, version, GC, and actual settings. **There is no guarantee that calling `System.gc()` will unload all unused class loaders**; the JVM has the right to handle the GC hint and unloading is not guaranteed to happen immediately.

### 8.3. Example of a Class-Loader Leak

Suppose a plugin application has code like:

```java
// Illustrative snippet, not a standalone application:
static final java.util.List<ClassLoader> KEEP_FOREVER =
        new java.util.ArrayList<>();

void reloadPlugin() {
    ClassLoader loader = createPluginLoader();
    KEEP_FOREVER.add(loader);        // Intentionally retains every created loader.
    // Load the plugin's classes using the loader.
}
```

If every reload adds a loader to `KEEP_FOREVER`, the old loaders can remain reachable. Class metadata is not reclaimed as expected.

Adding memory to `-Xmx` does not directly fix the issue of retained native class metadata. Increasing `MaxMetaspaceSize` also only delays the limit if loader creation does not stop.

### 8.4. Lifecycle Solutions

- Properly unregister plugins from registries/caches.
- Close loaders that manage closeable resources, such as `URLClassLoader.close()`, keeping in mind that **closing a URLClassLoader does not force all classes to unload**.
- Stop plugin threads and clear context class loaders that are no longer needed.
- Remove listeners, scheduled tasks, ThreadLocals, and cross-references from host to plugin.
- Reduce unbounded class/proxy generation and use properly scoped caching.
- Re-measure unload/classloader counts after each reload cycle.

You need to **assign clear object/loader ownership** rather than just setting an extremely large Metaspace capacity.

## 9. Two Easily Confused OutOfMemoryError Messages

### 9.1. `OutOfMemoryError: Metaspace`

Common message:

```text
java.lang.OutOfMemoryError: Metaspace
```

It indicates that **metadata allocation** cannot continue under the actual runtime conditions: possibly due to `MaxMetaspaceSize`, native memory pressure, class-loader retention, or other factors. The message and behavior depend on the HotSpot version.

Analysis:

1. Check whether the `MaxMetaspaceSize` flag is set too low.
2. Inspect used/committed, the number of classes/loaders, and the trend over time.
3. Look for loaders that grow indefinitely or persist after redeploys.
4. Check native memory/container limits; not just the heap.
5. Fix the source of abnormal growth first, and only then tune the ceiling for the real workload.

### 9.2. `OutOfMemoryError: Compressed class space`

Common message when using compressed class pointers:

```text
java.lang.OutOfMemoryError: Compressed class space
```

It indicates that the region of **class metadata managed in the compressed class space** could not satisfy an allocation, not simply that "the Java heap is full". Investigate `CompressedClassSpaceSize`, pointer compression flags, the number of classes/loaders, and metadata pressure.

You can increase the class-space limit when the VM and resources permit, or review pointer compression configuration according to the specific JVM documentation, **but you must evaluate the memory/performance and compatibility impact**. It is not recommended to arbitrarily disable compressed class pointers to mask a broken loader lifecycle.

### 9.3. Comparison with Heap Errors

| Symptom | Primary Suspect Region | What to Check |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Java heap | Object retention, `-Xmx`, allocation profile |
| `OutOfMemoryError: Metaspace` | Native class metadata | Metadata limits, class loaders/classes, unloading |
| `OutOfMemoryError: Compressed class space` | Compressed class metadata region | Class space limit, compressed pointers, loader churn |
| OS/container kill due to exceeding RAM | **Entire resident process** | Heap + metaspace + stacks + code cache + GC/native allocations |

Real-world errors can be complex; this is an **initial investigation direction**, not proof of a single root cause.

## 10. Observing Metaspace with JDK Tools

The tools below apply to **modern HotSpot/JDK**. Syntax/support depends on the runtime. Before using them in production, consider access permissions, the impact of diagnostic commands, and the volume of printed output.

### 10.1. Step One: Identify the Java Process

```bash
jcmd -l
```

The command can print a list of Java processes and PIDs. If there are multiple JVMs, choose the **exact target PID**; do not send diagnostic commands to the wrong application.

### 10.2. View Supported Diagnostic Commands

```bash
jcmd <pid> help
```

`<pid>` is a placeholder to be replaced with the actual PID. Do not type `<` and `>` as shell command syntax; in documentation they only indicate parameter positions. HotSpot 17+/21 usually supports `VM.metaspace`, but always verify the actual command.

### 10.3. View Metadata Usage

```bash
jcmd <pid> VM.metaspace
jcmd <pid> VM.metaspace basic
```

`VM.metaspace` displays metadata memory statistics. In supported versions, `basic` provides a summary with fewer pause/synchronization requirements; other options give breakdowns by loader, class, chunk, or space.

```bash
jcmd <pid> VM.metaspace show-loaders
```

This command can produce large output, especially when the application loads a large number of classes. Do not treat the output as fixed-format data; pay attention to the differences between **used/committed/reserved**, compressed class space figures, and per-loader details.

### 10.4. View Class Loader Statistics

```bash
jcmd <pid> VM.classloader_stats
```

Use this when suspecting uncollected plugin reloads/framework-generated classes. Monitor:

- Number of loaders.
- Number of classes per loader.
- Metadata chunks/blocks or statistical data printed by the HotSpot version.
- Loader types holding more classes than expected.
- Loaders still persisting after a plugin should have been unloaded.

**Do not use "increasing loaded class count" as the sole proof of a leak.** During warm-up, an increase is normal; what matters is the **growth rate, stabilization level, unloading trend**, and correlation with business operations.

### 10.5. Native Memory Tracking (NMT)

When you want an overall native memory breakdown, start the JVM with:

```bash
java -XX:NativeMemoryTracking=summary -cp . MetaspaceInspectDemo
```

**Note:** this is HotSpot's `-XX:NativeMemoryTracking=summary` flag, not `-XX:+NativeMemoryTracking`. Tracking has overhead and usually must be enabled at JVM startup to collect the necessary metrics.

Then:

```bash
jcmd <pid> VM.native_memory summary
```

NMT can help distinguish groups such as Class, Thread, Code, GC, and other native subsystems. NMT figures do not necessarily include **every allocation from native libraries outside the JVM**, and do not directly equal the process's RSS.

For periodic analysis cases, baseline and summary.diff operations can be used when supported by the HotSpot version:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

Take a baseline right before a specific workload, execute the workload, and then inspect the diff; this is more useful than reading total numbers once.

### 10.6. GC and Class-Loading Logs

You can run HotSpot with:

```bash
java -Xlog:gc+metaspace=info -cp . MetaspaceInspectDemo
```

Depending on the JVM/JDK, logs provide additional data related to metaspace usage during GC or at relevant points. To check actual tags and levels:

```bash
java -Xlog:help
```

To observe class loading, some setups use:

```bash
java -Xlog:class+load=info -cp . MetaspaceInspectDemo
```

Class-load logs are usually very verbose. Do not assume detailed logging is free or that every load line proves a classloader leak.

## 11. Standalone Java 17+ Example Combining MXBean and `jcmd`

Create a single file **`MetaspaceInspectDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class MetaspaceInspectDemo {
    static final class Marker {
        static final String NAME = "Marker";
    }

    public static void main(String[] args) throws Exception {
        Class<?> loaded = Class.forName(Marker.class.getName());
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("same runtime class: "
                + (loaded == Marker.class));
        System.out.println("class loading bean available: "
                + (classes != null));
        System.out.println("loaded class count positive: "
                + (classes.getLoadedClassCount() > 0));

        System.out.println("press Enter to finish");
        new BufferedReader(new InputStreamReader(System.in)).readLine();
        System.out.println("finished");
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac --release 17 MetaspaceInspectDemo.java
java MetaspaceInspectDemo
```

**Exact stdout when running on standard HotSpot/JDK and pressing Enter at the end:**

```text
same runtime class: true
class loading bean available: true
loaded class count positive: true
press Enter to finish
finished
```

The sample above was compiled and run with JDK 21 using `--release 17`; the output matches. **Actual class count** and **Metaspace size** values are not hardcoded in stdout because they depend on the runtime, workload, and class-loading activity.

### 11.1. Why Does the Demo Wait for Enter?

The program keeps the process alive so you can run `jcmd` from **another terminal**:

```bash
jcmd -l
jcmd <pid> VM.metaspace basic
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.flags
```

After capturing statistics, return to the terminal running `MetaspaceInspectDemo` and press Enter so the program prints `finished` and exits.

If running under an IDE/CI that does not provide interactive stdin, the `readLine()` call may receive EOF and the program will terminate immediately. In that situation, run directly from an interactive terminal when inspection is needed.

### 11.2. What Does MXBean Display?

`ClassLoadingMXBean` is the standard API to retrieve overall class loading counts, for example:

```java
// Illustration inside a method:
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();
int current = bean.getLoadedClassCount();
long total = bean.getTotalLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
```

These numbers **can change during execution**, so an "exact stdout" should not be published for them. They are useful for tracking trends alongside time/GC/logs, but are not sufficient to know per-loader details or individual metadata allocations.

### 11.3. MemoryPoolMXBean Can Show Metaspace and Class Space

On HotSpot, you can query:

```java
// Illustrative code snippet inside a method:
for (java.lang.management.MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.println(pool.getName() + ": " + pool.getUsage());
}
```

Pool names and values **are not fixed across all JVMs**. You may see `Metaspace` and `Compressed Class Space` if configured appropriately; when compressed class pointers are not used, the class-space pool may not appear as you expect.

Do not use a one-time output to decide production flag settings. You need to compare over time and across workloads.

## 12. Comparing PermGen, Metaspace, and Compressed Class Space

| Criterion | **PermGen (historical)** | **Metaspace (HotSpot 8+)** | **Compressed class space (when enabled)** |
| --- | --- | --- | --- |
| Exists in modern HotSpot? | **No** since JDK 8 | **Yes** | **Conditionally** on supported configurations |
| Primary role | Allocate class metadata in the legacy model | Metadata allocation mechanism in native memory | Class metadata region for compressed class pointers |
| Relationship to Java heap | Separate region/GC generation in legacy HotSpot; not regular application Java heap | **Outside Java heap**, uses native memory | **Outside Java heap**, separate region related to Metaspace |
| Typical flags | `PermSize`, `MaxPermSize` | `MetaspaceSize`, `MaxMetaspaceSize` | `CompressedClassSpaceSize` |
| Common OOME error | `PermGen space` | `Metaspace` | `Compressed class space` |
| Metadata reclamation | According to legacy GC/class unloading policy | Reuse/reclamation tied to unloading and allocator | Also depends on metadata/class unloading and class-space mechanism |
| Size interpretation | Region limit per legacy generation | Used/committed/reserved must be distinguished | Reservation is usually large but committed on demand |
| Does JVMS mandate this name? | No | No | No |

Point to remember: **Compressed class space is not a separate descendant of PermGen**; it is an implementation detail **within the HotSpot Metaspace design with compressed class pointers**. The names can be confusing, but their purposes and allocation methods differ.

### 12.1. Why Did JDK 8 Not Eliminate Metadata OutOfMemoryErrors?

Removing a fixed-limit region like PermGen does not make class metadata infinite. Native memory still has practical limits, the JVM has ceiling flags, containers have memory limits, and class loader leaks can continue retaining metadata.

An application that only increased `-XX:MaxPermSize` on JDK 7 and then upgraded to JDK 17 without changing its monitoring may find that "PermGen" monitoring disappears, while **Metaspace** is what needs to be observed.

### 12.2. Is "Metaspace Resides on the Native Heap" Strictly Accurate?

Saying **Metaspace uses native memory** is appropriate. However, "every byte of Metaspace is allocated with `malloc` on the C heap" is not accurate for how HotSpot typically manages metadata: it has mechanisms to reserve/commit virtual address regions, often using memory mappings and its own allocators/chunks. Therefore, terms like **native memory**, **reserved address space**, and **committed pages** are generally more accurate than saying "everything is malloc'd immediately".

## 13. JEP 387 — Elastic Metaspace and Practical Significance

**JEP 387: Elastic Metaspace** arrived in JDK 16. Its goal is to improve native memory management for metadata to **reuse it more efficiently** and **return committed memory to the operating system more promptly**, especially for workloads with many small class loaders or continuous loading/unloading.

Previously, unused class metadata could cause the allocator to retain more committed space than desired. Elastic Metaspace redesigned several management and reclamation structures to reduce the footprint.

### 13.1. Reclamation Policies

A flag on modern HotSpot:

```text
-XX:MetaspaceReclaimPolicy=balanced
```

Depending on the JDK version, options may include:

- `balanced`: balanced policy (usually the default).
- `aggressive`: more aggressive reclamation, which may increase management overhead.
- `none`: disables some reclamation mechanisms as described by the corresponding policy.

Options are **HotSpot details**; verify the version and tuning goals.

### 13.2. Elastic Does Not Mean "Guaranteed to Return All RAM"

If loaders and classes are still reachable, metadata still **needs to exist**. Elastic Metaspace does not change reachability rules. If a cache holds hundreds of old loaders, even an aggressive policy cannot turn live classes into unloaded classes.

Even when classes are unloaded, other runtime resources, fragmentation, allocator management, and GC activity may prevent committed memory from returning to the exact startup level.

## 14. A Practical Workflow When Metaspace Grows Continuously

Suppose a server JVM has a stable heap, but RSS and committed Metaspace increase after every plugin reload.

### Step 1 — Record the Environment

Collect:

```bash
java -version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

Identify the JVM vendor/build, architecture, GC, container limits, and configured memory flags.

### Step 2 — Distinguish Memory Regions

Collect:

```bash
jcmd <pid> VM.metaspace
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.heap_info
```

If NMT was enabled from the start:

```bash
jcmd <pid> VM.native_memory summary
```

Do not lump heap, Metaspace, compressed class space, and resident process memory into a single unattributed number.

### Step 3 — Compare Before/After Repeated Workloads

Take a baseline before reloading the plugin multiple times. Record:

- Current number of class loaders and loader types.
- Number of classes per loader.
- Metaspace used/committed (record class-space separately if split).
- Number of unloaded classes over time if available.
- Heap/RSS along with GC activity.

If after each cycle the number of loaders keeps increasing, metadata used increases, and there is no corresponding sign of unloading, investigate **class loader retention**.

### Step 4 — Find References Retaining Loaders

Inspect:

- Static registries, callback listeners, JMX registrations.
- Executor threads and thread context class loaders.
- ThreadLocal values/keys, scheduled tasks.
- Framework caches, reflection/proxy frameworks.
- Resources held by the plugin or class loader.
- Host objects holding instances of classes defined by the plugin loader.

Do not assume "calling `loader.close()`" is enough; you must check what references still keep the loader reachable.

### Step 5 — Tune Flags When Supported by Evidence

If class loading is reasonable and stable, but the metadata limit was set too small, consider increasing `MaxMetaspaceSize` or the class-space cap appropriately. If it is a leak, **fix the leak first**; a larger limit only prolongs the time before OOME.

### Step 6 — Verify After the Fix

Re-run the same workload with the same JDK/config:

- The number of loaders stabilizes or decreases after unloading.
- Metaspace **used** does not grow unboundedly.
- Committed memory can decrease or be reused according to the policy.
- Application heap, native memory, and RSS fit within the container budget.
- No new runtime errors appear due to loader lifecycle changes.

## 15. Mistakes and Statements to Correct

1. **"Metaspace is part of the Java heap."** False for HotSpot 8+: Metaspace class metadata uses native memory outside the Java heap.
2. **"The JVMS requires every JVM to have Metaspace."** False. The JVMS describes the method area; Metaspace is a HotSpot implementation.
3. **"Increasing `-Xmx` increases Metaspace."** False. `-Xmx` applies to the Java heap.
4. **"JDK 8 only renamed PermGen."** False. The allocation/accounting mechanism and metadata location changed significantly.
5. **"The string intern pool moved to Metaspace in JDK 8."** False. Not all legacy PermGen structures were moved verbatim into Metaspace; interned Strings already had changes starting in JDK 7.
6. **"`MaxMetaspaceSize` always equals `CompressedClassSpaceSize` plus the rest."** False. The two flags control different types of limits, depending on ergonomics/committed and reserved.
7. **"1 GiB reserved compressed class space means 1 GiB of RAM is used."** False. Reserved differs from committed/used.
8. **"Compressed oops and compressed class pointers are the same."** False. Their reference types and purposes differ.
9. **"Static object instances are stored in Metaspace."** False. Java objects belong to the heap; class metadata is native data.
10. **"Each `new` instance creates a new copy of class metadata."** False. Ordinary instances of the same runtime class share the metadata of the loaded class.
11. **"A class loader leak always causes a Java heap space OOME first."** False. Native metadata can also run out first, depending on configuration/workload.
12. **"`System.gc()` guarantees unloading all old classes immediately."** False. There is no such guarantee.
13. **"Elastic Metaspace has eliminated all native memory pressure."** False. It optimizes reclamation; it does not create infinite memory.
14. **"`MetaspaceSize` is the maximum heap for metadata."** False. It mainly relates to a GC high-water mark, not a hard cap.
15. **"NMT class memory is all of the JVM's RSS."** False. NMT/VM accounting and RSS serve different measurements with different scopes.
16. **"Missing `Compressed Class Space` in MXBean means the JVM is broken."** No. The feature/pool may not appear in configurations with compressed class pointers disabled or in other JVMs.
17. **"A single snapshot showing increased class count proves a leak."** False. You need to observe trends, unloading, and workload.
18. **"Setting `-XX:-UseCompressedClassPointers` is the cure for every OOME."** False. Disabling compression has trade-offs and does not change the class loader lifecycle.

## 16. Self-Check Exercises with Answers

**Question 1.** Does HotSpot JDK 17 use PermGen to store class metadata?

**Answer:** No. HotSpot removed PermGen in JDK 8; class metadata is allocated via Metaspace/native memory.

**Question 2.** Is the JVMS method area always identical to Metaspace?

**Answer:** No. Method area is a concept in the JVM Specification; Metaspace is how HotSpot implements and allocates many types of class metadata.

**Question 3.** Does `-Xmx1g` set the Metaspace ceiling to 1 GiB?

**Answer:** No. `-Xmx` limits the Java heap, not directly native Metaspace.

**Question 4.** Does `CompressedClassSpaceSize=1g` mean the JVM already uses 1 GiB of RAM for metadata right at startup?

**Answer:** No. The flag relates to virtual address space reservation/capacity; committed/used can be much lower.

**Question 5.** Why are `MaxMetaspaceSize=256m` and a class-space reservation near 1 GiB not a contradiction?

**Answer:** Because MaxMetaspaceSize acts on committed/allocated metadata per runtime limits, whereas class-space reservation is **reserved virtual addresses**, which does not mean it is all committed.

**Question 6.** Two custom class loaders define two versions of `example.Plugin`. Might two sets of metadata be needed?

**Answer:** Yes. Runtime class identity depends on both the binary name and the defining loader, so two independent definitions have separate metadata.

**Question 7.** After `plugin = null`, is the plugin class's metadata guaranteed to be freed?

**Answer:** Not necessarily. The class loader/classes may still be reachable via caches, threads, static registries, listeners, or other references. Class unloading is not instantaneous.

**Question 8.** Which command provides detailed Metaspace statistics for a running HotSpot JVM?

**Answer:** `jcmd <pid> VM.metaspace` when supported by the JVM. For a loader breakdown, `jcmd <pid> VM.classloader_stats` can be used.

**Question 9.** What preparation is needed to use `VM.native_memory summary`?

**Answer:** In HotSpot, NMT usually must be enabled at startup, for example `-XX:NativeMemoryTracking=summary`; the tool has overhead and does not include all memory managed independently by native libraries outside the VM.

**Question 10.** Why can't `MemoryPoolMXBean` always be used to calculate a process's RSS?

**Answer:** Pool metrics reflect the memory pools reported by the JVM, not the entire OS resident memory including all native allocations and thread stacks.

**Question 11.** Why doesn't JEP 387 automatically fix a class-loader leak?

**Answer:** Elastic Metaspace helps reclaim **metadata of unloaded classes**. If a loader is still reachable, the classes have not unloaded, so the metadata still needs to exist.

**Question 12.** How do the investigation directions for `OutOfMemoryError: Java heap space` and `OutOfMemoryError: Metaspace` differ?

**Answer:** Heap errors prioritize inspecting object heap retention and `-Xmx`; Metaspace errors prioritize inspecting metadata limits, class counts/loaders, unloading, and native memory pressure.

**Question 13.** Is the `java.lang.Class` object on the heap or in Metaspace?

**Answer:** The `java.lang.Class` mirror is a Java object in the heap on HotSpot, while the VM has separate native metadata structures linked to it.

**Question 14.** Why shouldn't `MaxPermSize` be used to tune HotSpot JDK 21?

**Answer:** Because PermGen has been removed; you must look at the Metaspace/Compressed Class Space flags supported by the target JVM version.

**Question 15.** A redeploy causes committed Metaspace to increase, and after several GCs committed does not decrease. Can we conclude for certain there is a leak?

**Answer:** Not yet. You need to look at **used, remaining loaders/classes, unloading capability, allocator caching, and reclamation policy**. Committed may stabilize/be retained for reuse; you need trends and reachability evidence.

## 17. Checklist When Deploying HotSpot in a Container

Metaspace is part of the **native memory budget**. When a JVM runs inside a container with a RAM limit, you need to leave room for:

```text
Total container memory limit
    ├── Java heap (-Xmx)
    ├── Metaspace + compressed class space (committed)
    ├── JIT code cache
    ├── Thread stacks
    ├── GC/native VM structures
    ├── Direct buffers and native I/O
    └── Other native allocations
```

The items above are only an **inventory of consumption sources**; do not assume every NMT field is a non-overlapping independent group or that reservations can be summed to get actual RSS.

Practical suggestions:

- Monitor RSS, heap used/committed, and metadata used/committed separately.
- Evaluate warm-up class loading and peak loader count.
- Test build/runtime on the exact JDK being deployed.
- Use NMT in test environments or in production while accounting for overhead.
- Do not set `-Xmx` close to the entire container RAM and ignore native memory.
- Do not set the class-space cap too low if the application uses many dynamically generated classes.
- Avoid setting an unjustifiably huge ceiling, as that can mask abnormal metadata growth.
- Verify with monitoring and real workloads, rather than using a single default rule for every service.

## 18. Summary

```text
HotSpot before JDK 8:
    PermGen
      |
      +-- class metadata in the legacy mechanism

HotSpot JDK 8+:
    Native class metadata management
      |
      +-- Metaspace (non-class metadata)
      |
      +-- Compressed class space (if compressed class pointers enabled)
              reserved address space ≠ committed memory ≠ used bytes

Class unloading:
    class/loader no longer needed and eligible for unload
      |
      +-- metadata allocator can reuse/reclaim
      +-- JEP 387 (JDK 16+) improves returning committed pages
```

**Key Takeaways:**

- **PermGen is HotSpot history prior to JDK 8; Metaspace is HotSpot's native metadata mechanism from JDK 8 onward.**
- **Compressed class space is only a specific class metadata region when compressed class pointers are enabled**, not the entirety of Metaspace.
- **Reserved, committed, and used must be read differently.** A large reservation is not an amount of RAM already used.
- **Metaspace is not the Java heap:** `-Xmx` does not directly limit Metaspace, and a Metaspace OOME has a different diagnostic direction than a heap OOME.
- **Class metadata has a lifecycle tied to class loading/unloading and defining class loaders.** If loaders are retained forever, Metaspace can grow forever.
- **JEP 387 improves elasticity but does not cure memory leaks.** Monitor `jcmd VM.metaspace`, `VM.classloader_stats`, NMT, and controlled workloads to make decisions.

### Official Documentation and Verification Sources

- [Oracle JDK 21 GC Tuning Guide — Class Metadata](https://docs.oracle.com/en/java/javase/21/gctuning/other-considerations.html): Metaspace native memory, compressed class pointers, class space, flags, and memory metrics.
- [OpenJDK JEP 122 — Remove the Permanent Generation](https://openjdk.org/jeps/122): removing PermGen when moving to JDK 8.
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): allocator and reclamation improvements from JDK 16.
- [Oracle JDK 21 — java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-XX:MaxMetaspaceSize`, `-XX:MetaspaceSize` options, and JVM flags.
- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.metaspace`, `VM.classloader_stats`, `VM.native_memory`, and using diagnostic commands.
- [Oracle JDK 21 — JVM Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/): diagnosing native memory and class metadata-related errors.
- [JVMS §2.5.4 — Method Area](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.4): conceptual area in the JVM specification, without mandating HotSpot details.
- [ClassLoadingMXBean — JDK 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): counts of loaded/unloaded classes.
