# Metaspace in HotSpot and the Limits of the Method Area Model

When learning Java ClassLoader, **method area** and **Metaspace** are often used as two names for the same thing. That phrasing is only true as a simplified explanation and easily causes serious misunderstandings when diagnosing **`OutOfMemoryError: Metaspace`**, class-loader leaks, native memory, or the ability to unload classes.

**Foundational distinctions:**

- **Method area** is an **abstract runtime data area required by the Java Virtual Machine Specification (JVMS)**. At the model level, it holds per-class structures such as the runtime constant pool, field/method information, and the code for methods/constructors. The specification **does not require** a JVM to implement this area at a specific address, with a specific allocator, or in a specific heap.
- **Metaspace** is **the mechanism HotSpot uses to manage a major portion of class metadata** in modern JDKs (JDK 8+). HotSpot typically allocates this metadata using **native memory**, unlike the Java object heap governed by the `-Xmx` limit.
- **PermGen** is a **historical implementation detail of HotSpot** prior to JDK 8. Metaspace replaced PermGen's legacy class-metadata storage model in HotSpot; **it does not mean the entire JVMS method area "turned into a single Metaspace byte array"**.
- **Class unloading** depends on the runtime class and its defining loader according to JVM/GC rules; calling `URLClassLoader.close()` does not directly delete class metadata. Metaspace can reuse or return a portion of memory to the operating system after the JVM reclaims eligible class-loader generations.
- **Memory metrics represent different perspectives**: `used`, `committed`, `reserved`, heap usage, the NMT `Class` category, OS RSS, and compressed class space **must not be arbitrarily added or subtracted, or treated as the same metric**.

This lesson is based on **Java 17+**, clearly distinguishing between requirements **of the JVM specification** and behaviors **specific to HotSpot/OpenJDK**. The example at the end of the lesson uses `java.lang.management`, a JAR, and two `URLClassLoader` instances to observe the practical limits.

## 1. Distinguish "Specification" from "Implementation" Before Talking About Memory

Java is a language and platform with multiple JVM implementations. When reading **JVMS `2.5.4`**, we are reading the logical model that a compliant JVM must exhibit. When reading about **HotSpot Metaspace**, we are reading how one specific JVM implements a part of that model.

### Method Area According to the JVMS

JVMS Java SE 17, `2.5.4` specifies a **method area shared among all JVM threads**, used to store per-class structures, including:

- The runtime constant pool.
- Field and method data.
- The code for methods and constructors, including the special methods used in initialization.
- Structures that an implementation needs to manage runtime types.

**The specification states that the method area is "logically part of the heap"**. This phrase does not mean HotSpot must place all metadata inside the **Java heap bounded by `-Xmx`**. The JVMS also explicitly states that the specification **does not mandate the location of memory**, does not require a specific garbage collection/compaction policy for the method area, and does not require every implementation to store compiled code in the same way.

Therefore, the following two statements **do not contradict each other**:

1. **At the JVMS level:** the method area is considered a **logical** part of the heap in the virtual machine model.
2. **At the HotSpot level:** Metaspace class metadata largely uses **native/non-heap memory** and is reported by memory managers/tools outside the Java object heap.

Do not use the word "heap" across two different layers of abstraction and conclude that Java documentation contradicts itself.

### What Is Metaspace?

Metaspace is the subsystem that manages native allocations holding various metadata-related structures for **loaded classes** in HotSpot. When a class is defined, HotSpot needs metadata to understand the structure of the runtime type, its methods, fields, constant-pool information, and other implementation components.

`Metaspace` is not a Java collection where `Class<?>` objects directly "sit inside" in the conventional sense. On HotSpot, **`java.lang.Class` mirrors are Java objects on the Java heap**, linked to their corresponding internal metadata. An instance such as `new Widget()` also resides on the Java heap; metadata for the runtime class `Widget` has a different lifecycle and allocation.

## 2. Easy-to-Remember Diagram: Where Is What Stored?

```text
                   A JVM PROCESS (HotSpot)
  +------------------------------------------------------+
  |                                                      |
  |  Java Object Heap (-Xmx, GC-managed)                |
  |  +-----------------------------------------------+   |
  |  | new Widget() instances                        |   |
  |  | String / Array / Map / Class<?> mirrors        |   |
  |  | objects referenced by static fields           |   |
  |  +-----------------------------------------------+   |
  |                                                      |
  |  Native / VM-managed memory                         |
  |  +-----------------------------------------------+   |
  |  | Metaspace: many class metadata structures     |   |
  |  |  + Non-class metadata allocations             |   |
  |  |  + (when applicable) compressed class space   |   |
  |  +-----------------------------------------------+   |
  |  | Code Cache: machine code/JIT-compiled code    |   |
  |  | Thread stacks, GC data, symbols, VM internals  |   |
  |  +-----------------------------------------------+   |
  |                                                      |
  |  Filesystem / mapped artifacts                      |
  |  +-----------------------------------------------+   |
  |  | class files, JARs, JDK image, CDS archive      |   |
  |  +-----------------------------------------------+   |
  +------------------------------------------------------+
```

This is a **conceptual diagram**, not an exact memory map, nor does it depict all structures across every JDK. Some regions are virtual memory, some bytes reside in mapped files, some are shared across processes, and NMT categorization depends on the HotSpot/JDK release.

### Quick Comparison Table

| Component | Which Model / Implementation? | Where Does It Typically Reside in Modern HotSpot? |
|---|---|---|
| **Method area** | **JVMS logical region** | No single physical guarantee; its components are realized by HotSpot across multiple structures |
| **Metaspace** | **HotSpot implementation** | Native memory for class metadata |
| **Java heap** | JVM runtime area, HotSpot-managed | Java objects and arrays managed by the garbage collector |
| **`Class<?>` object** | Java reflection API mirror | Java heap, referencing the runtime class metadata |
| **`new Foo()` instance** | Java object | Java heap |
| **Runtime constant pool** | JVMS per-class logical structure | Corresponding metadata/VM structures; does not mean all `String` objects live in Metaspace |
| **Interned `String` objects** | Java objects | On modern HotSpot, `String` instances reside on the Java heap |
| **JIT-compiled machine code** | JIT implementation | HotSpot Code Cache and corresponding VM regions; do not say "all of it is in Metaspace" |
| **.class bytecode in JAR** | Application artifact | File/JAR/CDS image; does not mean every file must be kept as a verbatim copy in Metaspace |
| **Native thread stack** | OS/JVM execution resource | Outside the Java heap; not Metaspace |

A method can have **bytecode metadata** associated with the class and **JIT-compiled machine code** in the code cache. Do not conflate bytecode, compiled code, and method metadata into a single "method area size" number that a Java API is required to report.

## 3. From PermGen to Metaspace

### Historical HotSpot PermGen

In HotSpot versions prior to JDK 8, class metadata and several related components were managed through the **Permanent Generation (PermGen)** mechanism. Operators frequently encountered:

```text
java.lang.OutOfMemoryError: PermGen space
```

and the historical option `-XX:MaxPermSize`.

### JDK 8 Onward

HotSpot moved class metadata to **Metaspace**, using native memory and different allocation algorithms. Consequently, running out of metadata space typically manifests as:

```text
java.lang.OutOfMemoryError: Metaspace
```

**However, one should not say "PermGen and Metaspace are two JVM memory areas specified by the JVMS".** Both are HotSpot implementation details from different eras; the JVMS still describes the abstract **method area**.

The `-XX:MaxPermSize` option is not the way to cap Metaspace on JDK 17. To set a threshold for HotSpot class metadata, use **`-XX:MaxMetaspaceSize`**, which has its own semantics and limits.

### JDK 16+: Elastic Metaspace

**JEP 387 (Elastic Metaspace)** was introduced in **JDK 16** to reduce metadata footprint and enable HotSpot to **return unused memory to the operating system** more promptly after class unloading. It uses a management mechanism based on virtual-memory chunks/commit granules and reclamation policies.

Key takeaways:

- "Metaspace is able to shrink" **does not mean** the JVM will always immediately reduce RSS after closing a plugin loader.
- Returning memory to the OS depends on class unloading, allocator state, sizes/granularity, reclamation policies, and the measurement environment.
- Memory that is **freed/reused within the allocator** differs from **uncommitting** native pages; and uncommitting differs from OS RSS immediately dropping by an exact amount.
- Any remaining live metadata still requires memory to be retained, even after many class-loader generations have been cleaned up.

## 4. How Does ClassLoader Relate to Metaspace?

Each **runtime class** is identified by:

```text
(binary class name, defining class loader)
```

For example, two loaders both defining `example.Widget`:

```text
URLClassLoader A
   └── ("example.Widget", A) -> A's class metadata

URLClassLoader B
   └── ("example.Widget", B) -> B's class metadata
```

These are two distinct runtime classes, so the JVM may need **separate metadata** for each class. There is no rule that "same name + same bytecode means the JVM only spends one copy of class metadata" in all cases.

### Why Can Plugin Reloads Easily Cause Metaspace to Grow?

A plugin manager may create a new loader on every update:

```text
V1: Loader-1 -> plugin classes v1 -> metadata generation 1
V2: Loader-2 -> plugin classes v2 -> metadata generation 2
V3: Loader-3 -> plugin classes v3 -> metadata generation 3
...
```

If older loader generations **remain reachable** through registrations, threads, or caches, the JVM cannot yet reclaim them under class-unloading rules; the amount of class metadata may continue to grow.

Common **sources of loader retention**:

- A plugin instance retained by the host in a `Map`, registry, or listener list.
- Retained `Class<?>`, `Method`, `Constructor`, `MethodHandle`, generated proxy classes, and reflection caches.
- A thread still executing plugin code or a **thread context class loader (TCCL)** pointing to the plugin loader.
- A `ThreadLocal` value on an executor thread holding plugin objects.
- Unregistered ServiceLoader/provider caches, JDBC drivers, MBeans, logging handlers, or scheduled tasks.
- A loader graph with strong references from the host or another custom loader.
- Active call frames, native/JNI global references, or uncleaned resource lifecycles.

**Not all Metaspace growth is a leak.** A warming-up JVM may load many required classes and reach a normal plateau. You need to observe **loaded class counts, loader generations, used/committed metadata, and retaining paths over time**.

## 5. Class Unloading Is Tied to the Defining Loader

**JLS 12.7** allows the JVM to unload a class/interface when its **defining class loader becomes eligible for GC reclamation**; the exact timing of unloading is determined by the JVM. If the host still retains an instance, a `Class<?>`, a reflection cache, or a TCCL belonging to the plugin, the old generation may remain reachable and Metaspace will not be freed for that generation.

For applications that perform repeated reloads, inspect retaining paths and class-loader generations **before increasing `MaxMetaspaceSize`**; adjusting memory configuration only relieves pressure temporarily if the root cause is retention.

## 6. Metaspace and the Java Heap Have Distinct OOMEs

| Error / Symptom | Commonly Related Causes | How to Investigate |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap objects/arrays, retention, allocation pressure | Heap usage, allocation profiler, heap dump, `-Xmx` |
| `OutOfMemoryError: Metaspace` | HotSpot cannot allocate additional metadata due to limits or native memory pressure | Loader/class counts, metaspace pools, `MaxMetaspaceSize`, NMT |
| `OutOfMemoryError: Compressed class space` | The region reserved for compressed class pointers/class metadata reaches its applicable limit | `CompressedClassSpaceSize`, NMT `Class` category, class counts/types |
| `OutOfMemoryError: unable to create native thread` | Native memory, thread/process limits, OS resources | Thread count/stacks, OS/container limits |
| JVM/process killed by the OS (OOM killer) | Total resident/native + heap + stacks + JIT/CDS/... exceeds the quota | OS/container RSS, `memory.events`, NMT, and GC logs |
| High Metaspace committed but low used | Allocator overhead/free chunks, fragmentation/reclaim policy, sampling | Track used vs. committed/reserved and class unloading over time |

**Do not equate `OutOfMemoryError: Metaspace` with a full Java heap.** Raising `-Xmx` does not inherently fix a Metaspace error; making the heap too large inside a memory-limited container can even reduce native headroom.

Conversely, setting a higher `-XX:MaxMetaspaceSize` **does not fix a classloader leak**; it may only delay the symptoms while old loader generations remain reachable.

## 7. Three Key Terms: used, committed, and reserved

When observing Metaspace/NMT, separate three levels:

### Used

`used`: memory that the allocator/pool reports as consumed for metadata or the used portion as accounted by the tool. It is neither the number of objects on the heap nor automatically equivalent to OS resident bytes.

### Committed

`committed`: the amount of virtual-memory backing that the JVM has **committed** for the relevant region and can use under that management mechanism. It can be larger than `used` because allocations are organized into chunks/granules, contain slack/fragmentation, or hold memory ready for subsequent allocations.

### Reserved

`reserved`: the **virtual address space** the JVM reserves ahead of time so it can commit when needed. A large `reserved` value **does not mean** the operating system has allocated physical RAM for all of those bytes.

```text
Virtual address space reserved (can be very large)
+------------------------------------------------------+
| Committed virtual memory backing                     |
| +----------------------------------+                  |
| | Used metadata | free/slack/      |                  |
| |               | allocator space  |                  |
| +----------------------------------+                  |
|                  uncommitted region                  |
+------------------------------------------------------+
```

These metrics change dynamically. An NMT `Class reserved=... committed=...` report is not a measurement of "free RAM" or "used Java heap". In particular, **Compressed Class Space can reserve a large virtual address range** while its initial committed size is substantially smaller.

### Does OS RSS Equal Metaspace Committed?

Not necessarily. **Resident Set Size (RSS)** is the OS view of resident pages for the entire process; it includes many subsystems beyond Metaspace. Shared/mapped pages, demand paging, accounting, and memory reclamation mean that reconciling RSS against committed memory is not simple arithmetic.

When tuning for container RAM, consider **heap, GC native allocations, metaspace, code cache, thread stacks, direct buffers, libraries/mapped regions, and OS reports** together. NMT provides visibility into HotSpot internals, but it does not account for all native allocations made by third-party libraries.

## 8. Configuration Limits in HotSpot Java 17+

### `-XX:MaxMetaspaceSize`

Sets the maximum threshold for native memory that HotSpot allocates for class metadata according to JVM semantics, for example:

```bash
java -XX:MaxMetaspaceSize=256m -jar app.jar
```

This is an **illustrative command** that requires an appropriate `app.jar` artifact. If the required metadata allocations exceed the limit, the JVM may attempt GC/class unloading and eventually throw `OutOfMemoryError: Metaspace`.

Do not arbitrarily choose `256m` as a production value. You must measure the workload with appropriate class counts, plugin generations, class metadata, compressed class space, and safety headroom.

### `-XX:MetaspaceSize`

This is primarily a **threshold related to metadata allocation and triggering certain GC activities**, not "Metaspace starts pre-allocated with exactly X MB", nor is it a maximum limit like `MaxMetaspaceSize`.

An illustrative configuration:

```bash
java -XX:MetaspaceSize=64m -XX:MaxMetaspaceSize=256m -jar app.jar
```

Do not assume the JVM immediately consumes 64 MB of physical RAM merely because of `MetaspaceSize=64m`.

### `-XX:CompressedClassSpaceSize`

When HotSpot uses **compressed class pointers**, metadata can be split into non-class metadata and class metadata inside **compressed class space**. The option:

```bash
java -XX:CompressedClassSpaceSize=256m -jar app.jar
```

can adjust the corresponding reservation size/limit in supported configurations. Do not use this option unless you have verified the JVM/flags and confirmed the issue actually lies in compressed class space.

A large reserved region in NMT `Class` **is not evidence of a physical RAM leak**, because most of the virtual space may be uncommitted.

### `-XX:MetaspaceReclaimPolicy`

HotSpot after **JEP 387** supports choices such as:

```text
balanced
aggressive
none
```

With the option:

```bash
java -XX:MetaspaceReclaimPolicy=balanced -jar app.jar
```

`balanced` is the default policy commonly used in HotSpot versions that implement Elastic Metaspace; `aggressive` can increase the aggressiveness of uncommitting/reclaiming at the cost of some bookkeeping overhead; `none` reduces memory-return actions under that policy.

**Do not treat `aggressive` as "always lowest RAM and fastest".** Workloads with frequent class loading/unloading need to measure throughput, pause behavior, and footprint, rather than optimizing a single number at one point in time.

### `-Xmx` Is a Separate Matter

`-Xmx` limits the Java heap. Setting:

```bash
java -Xmx512m -XX:MaxMetaspaceSize=128m -jar app.jar
```

does not mean the JVM process is limited to 640 MB. There are still thread stacks, code cache, GC native metadata, direct buffers, JIT, mapped libraries, CDS, JVM internals, and OS-level overhead. When running in a container, you must budget for real headroom instead of adding two flags together as the memory limit.

## 9. Java 17+ Demo: Observing Metaspace and Two Loaders with the Same Class Name

The demo below is a **real runnable program** that uses `java.lang.management.MemoryPoolMXBean` to observe the **HotSpot pool named `Metaspace`**, then creates **two `URLClassLoader` instances** to load a JAR containing the class `example.Widget`.

**No fixed used/committed numbers are stated:** memory snapshots vary by JDK, GC, CDS, flags, and observation timing. Instead, the example verifies stable, tested invariants and semantics.

### 9.1. Directory Structure

```text
metaspace-demo/
├── src/
│   ├── plugin/
│   │   └── example/
│   │       └── Widget.java
│   └── host/
│       └── host/
│           └── MetaspaceDemo.java
├── out/
│   ├── plugin/
│   └── host/
└── plugin.jar
```

### 9.2. Plugin Class

File **`src/plugin/example/Widget.java`**:

```java
package example;

public final class Widget {
    private static int calls;

    public String hello() {
        calls++;
        return "hello " + calls;
    }
}
```

`calls` is static state per **runtime class**, not a JVM-wide variable keyed by the class name string.

### 9.3. Host Program

File **`src/host/host/MetaspaceDemo.java`**:

```java
package host;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class MetaspaceDemo {
    public static void main(String[] args) throws Exception {
        MemoryPoolMXBean metaspace = ManagementFactory
                .getMemoryPoolMXBeans().stream()
                .filter(p -> p.getName().equals("Metaspace"))
                .findFirst().orElseThrow();

        System.out.println("Pool name: " + metaspace.getName());
        System.out.println("Pool is non-heap: "
                + (metaspace.getType() == MemoryType.NON_HEAP));

        MemoryUsage sample = metaspace.getUsage();
        System.out.println("Metadata snapshot valid: "
                + (sample != null && sample.getUsed() >= 0
                   && sample.getCommitted() >= sample.getUsed()));

        URL code = Path.of(args[0]).toUri().toURL();
        ClassLoader parent = MetaspaceDemo.class.getClassLoader();

        try (URLClassLoader a =
                     new URLClassLoader(new URL[] {code}, parent);
             URLClassLoader b =
                     new URLClassLoader(new URL[] {code}, parent)) {

            Class<?> ca = a.loadClass("example.Widget");
            Class<?> cb = b.loadClass("example.Widget");

            System.out.println("Same binary name: "
                    + ca.getName().equals(cb.getName()));
            System.out.println("Different runtime classes: "
                    + (ca != cb));
            System.out.println("Each child defines its class: "
                    + (ca.getClassLoader() == a
                       && cb.getClassLoader() == b));

            Object objectA =
                    ca.getDeclaredConstructor().newInstance();
            System.out.println("Instance created: "
                    + (objectA != null));

            System.out.println("Method: "
                    + ca.getMethod("hello").invoke(objectA));

            a.close();

            System.out.println("Method after close: "
                    + ca.getMethod("hello").invoke(objectA));

            MemoryUsage after = metaspace.getUsage();
            System.out.println("After snapshot valid: "
                    + (after != null && after.getUsed() >= 0));
        }
    }
}
```

### 9.4. Compile and Run — Bash

From the `metaspace-demo` directory on Linux/macOS/Git Bash:

```bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin \
  src/plugin/example/Widget.java

javac --release 17 -d out/host \
  src/host/host/MetaspaceDemo.java

jar --create --file plugin.jar -C out/plugin .

# Only host classes are on the system classpath.
java -cp out/host host.MetaspaceDemo plugin.jar

# Try capping Metaspace and enabling NMT for practice.
java -XX:MaxMetaspaceSize=64m \
  -XX:NativeMemoryTracking=summary \
  -cp out/host host.MetaspaceDemo plugin.jar
```

**Note:** The `plugin.jar` path is passed as a **program argument**, not in `-cp`. If you put the plugin JAR on the parent classpath, two parent-first `URLClassLoader` instances may return the same class from the parent instead of defining it themselves.

### 9.5. Equivalent PowerShell Commands

```powershell
New-Item -ItemType Directory -Force -Path out/plugin, out/host | Out-Null

javac --release 17 -d out/plugin src/plugin/example/Widget.java
javac --release 17 -d out/host src/host/host/MetaspaceDemo.java

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.MetaspaceDemo plugin.jar

java -XX:MaxMetaspaceSize=64m -XX:NativeMemoryTracking=summary -cp out/host host.MetaspaceDemo plugin.jar
```

### 9.6. Compiled and Tested Output

Compiled with **`javac --release 17`** and run on **OpenJDK 24.0.2**. Both the baseline run and the run with `-XX:MaxMetaspaceSize=64m` and `-XX:NativeMemoryTracking=summary` printed the exact output:

```text
Pool name: Metaspace
Pool is non-heap: true
Metadata snapshot valid: true
Same binary name: true
Different runtime classes: true
Each child defines its class: true
Instance created: true
Method: hello 1
Method after close: hello 2
After snapshot valid: true
```

**Explanation of each group of results:**

1. **Pool name: Metaspace** — the application is running on HotSpot/OpenJDK, which has a `MemoryPoolMXBean` pool named `Metaspace`. You should not assume this pool name exists across every other JVM implementation.
2. **Pool is non-heap: true** — HotSpot's memory management API classifies this pool as **NON_HEAP**. This does not refute the statement "method area logically part of the heap" in the JVMS because the two statements belong to **two different levels of abstraction**.
3. **Metadata snapshot valid: true** — a valid sample can be obtained and `committed >= used`. Absolute byte counts are not tested as fixed values.
4. **Same binary name: true** and **Different runtime classes: true** — the two `Class<?>` objects share the same name but have different defining loaders.
5. **Each child defines its class: true** — `ca.getClassLoader() == a` and `cb.getClassLoader() == b`, confirming isolation.
6. **Method: hello 1** — the plugin object was created and the method works.
7. **Method after close: hello 2** — the loaded class continues to work even though loader A called `close()`; this **is not class unloading**.
8. **After snapshot valid: true** — the bean still provides a metadata snapshot; this does not assert that the size has decreased or that the old loader has become collectible.

**Limitation of the demo:** The application still keeps `ca`, `cb`, and `objectA` in scope, so the JVM must **not** be expected to unload/reclaim those classes immediately here. `URLClassLoader.close()` handles loader resources, not the garbage collector.

## 10. Reading MemoryPoolMXBean Metrics Correctly

From `java.lang.management`:

```java
MemoryPoolMXBean pool = ManagementFactory
        .getMemoryPoolMXBeans().stream()
        .filter(p -> p.getName().equals("Metaspace"))
        .findFirst().orElseThrow();

MemoryUsage usage = pool.getUsage();

if (usage != null) {
    System.out.println("used=" + usage.getUsed());
    System.out.println("committed=" + usage.getCommitted());
    System.out.println("max=" + usage.getMax());
}
```

This is an **illustrative snippet inside a method** with `java.lang.management.*` imports. It prints **dynamic values**, so a fixed stdout number should not be treated as the expected answer.

**Meaning:**

- `getUsed()`: the amount of memory the pool reports as currently in use.
- `getCommitted()`: the amount of backing memory committed for the pool according to the Java Management API.
- `getMax()`: can be **`-1`** if no maximum is defined for the pool according to the implementation/configuration. **Do not** substitute total machine RAM for `-1`.
- A measurement can change between calls; if you need to compute deltas, you must pick clear snapshot boundaries/points in time.

If running on a non-HotSpot JVM, the pool may have a different name or may not provide a similar classification. If application logic depends on memory-pool naming, treat it as a **JVM-vendor-specific monitoring integration**, not a JVM portability contract.

### What Does "Used Bytes Increased After Loading a Class" Prove?

It indicates a change in the snapshot; it does not prove the entire delta came from that single class. At that same moment, the following could be happening:

- The JDK lazily loads management/reflection classes.
- Reflection creates metadata or caches.
- The loader and ZIP/JAR handling perform multiple allocations.
- GC/class unloading occurs in between.
- JIT compilation/caches/thread scheduling affect measurement behavior.

To draw conclusions about the cause, measure multiple times, use JFR/profiler/NMT/classloader stats, and distinguish steady-state cost from warmup. Do not assert "each class = X bytes of Metaspace".

## 11. Native Memory Tracking (NMT): Observing the Entire VM by Categories

**Native Memory Tracking** is a HotSpot feature that helps track categories of native allocations made by the **HotSpot VM**. On Java 17, enable it at **process startup**:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Or when finer-grained analysis is needed:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

**You cannot turn NMT from off to on for an already-running process using `jcmd` alone**; the tool's design requires enabling it at startup if investigation is expected. `detail` can increase overhead and produce a large volume of information.

### 11.1. Using jcmd

Once the application is running with a PID, for example `12345`:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory summary scale=MB
```

To compare snapshots of the same process:

```bash
jcmd 12345 VM.native_memory baseline
# Run workload: initialize plugins, reload a batch.
jcmd 12345 VM.native_memory summary.diff scale=MB
```

The `#` character denotes a Bash comment. In PowerShell, `#` is also used for comments; the `jcmd` syntax is similar.

**Do not hardcode the literal PID `12345` into a runbook as a fixed value.** Find the actual Java process PID using `jcmd -l` or an appropriate OS tool, and substitute it into the command.

### 11.2. What Does NMT Report?

Depending on the JDK, the summary output may look like:

```text
Total: reserved=..., committed=...
  Java Heap       (reserved=..., committed=...)
  Class           (reserved=..., committed=...)
  Thread          (reserved=..., committed=...)
  Code            (reserved=..., committed=...)
  GC              (reserved=..., committed=...)
  Internal        (reserved=..., committed=...)
  ...
```

This is a **layout illustration**, not a fixed runtime log; category names and level of breakdown can change across HotSpot releases.

Under `Class`, part of the figures may describe metadata/non-class memory, compressed class space, class counts, or loader data. **Do not conclude that `Class reserved` is total RSS**, and **do not add `reserved` to `committed`** as if they were two separate amounts of RAM.

### 11.3. Important Limitations of NMT

NMT **does not track all allocations from third-party/native libraries** and does not necessarily measure all mapped/CDS memory in the way readers might expect. Enabling NMT per subsystem incurs operational overhead; it is a HotSpot diagnostic tool, not a replacement for OS metrics.

Therefore:

- NMT shows which category of **VM internal native allocations** is growing.
- A heap dump shows **retaining paths of Java objects**.
- JVM classloader stats show **loader/class populations**.
- OS/container metrics show **RSS/cgroup usage** and actual process pressure.
- Combining these sources leads to a sound diagnosis.

## 12. VM.classloader_stats and Class-Unload Logging

HotSpot supports the diagnostic command:

```bash
jcmd 12345 VM.classloader_stats
```

This command helps inspect class loaders and class metadata/class counts as supported by the JVM. A large number of loaders **does not automatically mean** a leak: application servers and plugin frameworks can legitimately require many loaders.

To observe when the JVM performs class unloading:

```bash
java '-Xlog:class+load=info,class+unload=info' -jar app.jar
```

PowerShell:

```powershell
java "-Xlog:class+load=info,class+unload=info" -jar app.jar
```

Seeing `class+unload` logs when the VM unloads some classes **does not prove all plugin resources were cleaned up**; conversely, **the absence of unload logs in a short test** does not prove a leak. GC does not guarantee that unloading will occur immediately after `close()` or `System.gc()`.

`java -Xlog:help` lists the logging tags/levels supported by the runtime. Use the tools appropriate for your JDK/vendor.

## 13. Investigating a Classloader Leak That Grows Metaspace

Suppose a server updates a plugin every minute, creating a new `URLClassLoader` each time. Initially everything looks fine, and after a few hours you observe:

```text
Metaspace used          steadily increasing after each reload
Class count             steadily increasing
Classloader generations steadily increasing
OS/container memory     steadily increasing or fluctuating high
GC cycles               occurring, but with little/no unloading of old loaders
```

This is a **suspicious pattern**, not proof; metrics must be measured directly and the retaining graph must be analyzed.

### 7-Step Process

1. **Establish a baseline:** runtime version, container memory limit, `-Xmx`, `MaxMetaspaceSize`, GC, CDS, flags, and loader count before reload.
2. **Reproduce under control:** repeat plugin load/stop/reload N times in a test environment; log generation IDs.
3. **Track heap and non-heap independently:** capture Metaspace pool used/committed, the NMT `Class` category, and the heap object population.
4. **Count loader/class populations:** `jcmd VM.classloader_stats`, and JFR class loading/unloading events when enabled.
5. **Analyze heap retaining paths:** identify which GC roots still point to the old loader or its objects/classes/methods.
6. **Clean up lifecycle resources:** threads, executors, TCCL, listener registries, JDBC/MBeans, reflection/ServiceLoader caches, buffers, and resource handles.
7. **Re-measure after cleanup:** an immediate drop in numbers is not required, but the trend should stabilize; if it still grows, revisit retaining paths/VM-level profiling.

### Example of a Loader Retention Path

```text
GC root / long-lived host object
    |
    +--> static Map<String, Handler> in host
            |
            +--> PluginHandler instance
                    |
                    +--> Class<plugin.Handler>
                            |
                            +--> defining URLClassLoader V1
                                    |
                                    +--> plugin classes/metadata
```

Even if `pluginManager.currentLoader = loaderV2`, a remaining reference inside a static map can keep loader V1 reachable. Replacing the primary loader reference **does not automatically clear all other references**.

**A static field inside a plugin is not automatically a permanent leak.** Object cycles that only point to each other can be reclaimed by GC when the entire graph is no longer reachable from GC roots. The problem lies in **actual reference roots** and the runtime lifecycle.

## 14. When Is Metaspace Reused or Returned to the OS?

In modern HotSpot, metadata allocations are typically managed via **class-loader-associated arenas/chunks**. From a simplified perspective:

```text
Define classes -> class metadata allocations -> Metaspace chunks
          |
          v
Retire class loader generation
          |
          v
Are strong references to loader/classes/instances cleared?
          |
         Yes
          |
          v
JVM/GC can unload the class loader and its classes
          |
          v
Allocator has free chunks or regions available for reuse
          |
          v
Elastic Metaspace can uncommit some unused pages
          |
          v
OS resident memory may decrease (no guarantee on exact timing/byte count)
```

### Reasons Used Decreases While Committed Has Not Decreased Yet

- Chunks have free space but are retained for **fast reuse**.
- Commit granules still hold live metadata, so they cannot be completely uncommitted yet.
- The reclaim policy aims to balance footprint and CPU overhead.
- GC/class unloading has not occurred yet or conditions have not been met.
- Tools capture snapshots at different points in time.

### Reasons Committed Decreases While Process RSS Does Not Decrease Proportionally

- OS accounting/mapped pages behave differently than expected.
- Other subsystems simultaneously increase native memory or heap committed/resident memory.
- Pages have been returned/marked, but RSS metrics do not reflect the change immediately.
- Cgroup/process measurements and NMT cover different scopes.

Therefore, KPIs should include **Metaspace used/committed, classloader count, native total, RSS, and time**, not just a single chart bar.

## 15. Compressed Class Space Is Not All of Metaspace

In 64-bit HotSpot with **compressed class pointers**, metadata class pointers can be represented via an appropriately reserved address region called **Compressed Class Space**. A portion of non-class metadata uses a different allocator.

This leads to reports such as:

```text
Class (reserved=..., committed=...)
  Metadata: ...
  Class space: ...
```

Depending on the HotSpot/JDK version, the exact presentation may differ.

**Distinctions:**

- `CompressedClassSpaceSize`: the limit/reservation related to compressed class space in applicable configurations.
- `MaxMetaspaceSize`: the limit on total class-metadata allocations according to the HotSpot option.
- `-Xmx`: limits the Java heap; it **does not** directly limit Metaspace.
- `reserved`: virtual address space, not equal to resident RAM.
- `committed`: backing memory; does not mean all of it consists of actively used objects.
- `used`: a snapshot according to allocator accounting, not the byte equivalent of a class-file JAR.

If `OutOfMemoryError: Compressed class space` appears, increasing `MaxMetaspaceSize` alone does not always resolve this distinct limit; you must inspect the compressed class space configuration, the number of classes/loader generations, and native headroom.

## 16. CDS, Code Cache, and Metadata Sharing

**Class Data Sharing (CDS)** in HotSpot helps share certain pre-prepared class data across Java processes or improve startup/memory footprint when an archive is used.

However:

- CDS does not mean "all custom-loader class metadata is shared".
- A new class loader still has its own runtime class identity and lifecycle.
- CDS does not turn plugin A's objects or mutable static fields into controlled shared state.
- CDS does not eliminate all costs of class initialization, dynamic linking, or JIT.
- Memory-mapped CDS archives have different accounting from Metaspace committed memory and the Java heap.

Similarly, the **JIT code cache** stores native compiled code used to execute methods. It has its own memory lifecycle and flags; **you should not lump code cache into Metaspace merely because a method belongs to a loaded class**.

When profiling native memory, compare the **`Class`, `Code`, `Thread`, `GC`, and `Java Heap`** categories according to your tooling; avoid blaming Metaspace for every native memory growth.

## 17. Difference Between "Metadata Growth" and a "Heap Leak"

| Observed Symptom | Suspected Direction | Next Verification |
|---|---|---|
| Heap objects grow sharply, loader/class counts are stable | Typical heap cache/leak | Heap histograms, heap dump, allocation profile |
| Loader/class counts grow with the number of plugin reloads | Retained loader generations | Retaining paths from GC roots, stop/unregister |
| Metaspace used grows, heap is relatively stable | Many class definitions/loader retention | NMT, classloader stats, JFR |
| Metaspace used plateaus, committed is higher | Allocator slack/reclaim timing | Elastic Metaspace policy, trends |
| RSS grows while Metaspace is stable | Another native subsystem, direct buffers, threads, JNI, GC, JIT | NMT subsystem diff and OS tools |
| `Class reserved` is very large while committed is low | Virtual address reservation for compressed class pointers | Do not directly equate it with a physical memory leak |

In a containerized server, memory leaks can also come from **direct/mapped buffers**, JNI libraries, or native agents that NMT does not fully account for. Do not simply tune `MaxMetaspaceSize` if the OS is killing the process due to RSS growth from another component.

## 18. Misconceptions to Eliminate

### "The Method Area Is Metaspace According to the Java Specification"

**Incorrect.** The method area is a JVMS abstract runtime region; Metaspace is a HotSpot implementation detail for class metadata. Another JVM may use a different allocation mechanism while still conforming to the specification.

### "The Method Area Is Logically Part of the Heap, So `-Xmx` Must Limit Metaspace"

**No.** `-Xmx` limits HotSpot's Java object heap, whereas many HotSpot metadata allocations reside in native/non-heap memory. The phrase "logically part" is not a guarantee of physical placement.

### "All Static Variables Reside Entirely in Metaspace"

**False as an absolute statement.** Class metadata, static field storage, `Class<?>` mirrors, and the object pointed to by a static reference have different representations/placements depending on the HotSpot implementation. In particular, **the object referenced by a static field resides on the Java heap**. Do not depict every static value as bytes that always sit entirely inside Metaspace.

### "If a JAR Has 30 MB of Class Files, Metaspace Must Use 30 MB"

**No.** Compressed JAR size, the number of classes actually loaded, class metadata structures, shared archives, JIT code, resources, and allocator overhead are all different quantities.

### "Each Class Loader Always Has Its Own Separate Metaspace"

**Not in the sense of a separate fixed-size pool.** HotSpot has a shared Metaspace subsystem and allocates chunks/arenas associated with loader data structures. Different loaders have distinct metadata ownership, but each loader does not own an independent OS memory pool with its own `MaxMetaspaceSize`.

### "Closing a Loader Immediately Shrinks Metaspace"

**No.** `URLClassLoader.close()` releases loader resources; it does not force GC or class unloading. The loader may still be reachable, and there is also allocator reclaim delay.

### "Metaspace Reserved 1 GB Means the JVM Has Consumed 1 GB of RAM"

**No.** Reserved virtual address space differs from committed physical backing and differs from resident memory. In particular, compressed class space can reserve a large address range.

### "Increasing `MaxMetaspaceSize` Fixes a Metaspace Leak"

**No.** It only changes the limit; it does not remove the references retaining classloader generations. You must find the root cause via profiling and the heap graph.

### "The Method Area Can Never Be Garbage Collected"

The JVMS does not mandate that every implementation apply a specific GC policy to the method area; **it does not prohibit the JVM from performing class unloading**. HotSpot performs class unloading and reclaims metadata under certain conditions. The JLS constrains when a class may be unloaded.

## 19. Metaspace Operations Checklist for Plugin Applications

- [ ] Record the **JVM implementation/vendor/version** currently running.
- [ ] Separate the **JVMS method area** from **HotSpot Metaspace** when explaining concepts.
- [ ] Do not add `-Xmx` and `MaxMetaspaceSize` together and call that the total process RAM limit.
- [ ] Monitor the `Metaspace` pool's `used/committed` values and keep in mind `max` can be `-1`.
- [ ] Distinguish among `reserved`, `committed`, `used`, and **RSS**.
- [ ] Track **loaded-class count** and **classloader generations** over time.
- [ ] If a leak is suspected, capture **heap retaining paths** to the loader/instances/reflection handles.
- [ ] Check TCCL, `ThreadLocal`, executors, listeners, `ServiceLoader`, and global registries.
- [ ] When retiring a plugin, stop its work, clean up resources, and `close` the loader in the proper order.
- [ ] Do not rely on `System.gc()` as a mandatory trigger to verify unloading.
- [ ] If enabling NMT, enable it at startup and account for profiling overhead.
- [ ] When tuning `MetaspaceReclaimPolicy`, benchmark both memory and CPU/latency.
- [ ] Check CDS, compressed class pointers, and allocator differences before interpreting NMT.
- [ ] Verify container/cgroup limits, native headroom, and other memory pools.
- [ ] Do not treat a classloader as a security sandbox merely because it isolates metadata.

## 20. Self-Check Questions

**1. Is the method area a specific name for HotSpot Metaspace?** No. The method area is an abstract structure in the JVMS; Metaspace is how HotSpot manages class metadata.

**2. Why does "method area logically part of heap" not contradict HotSpot's `MemoryType.NON_HEAP`?** Because one statement describes the **logical model**, while the other describes the **implementation/management classification**.

**3. Where do a `Class<?>` mirror and `new Widget()` typically reside in modern HotSpot?** As Java objects on the Java heap; the separate class metadata can reside in Metaspace.

**4. Do two loaders defining the same binary name produce the same runtime class?** No. The defining loader is part of the runtime class identity.

**5. Does calling `URLClassLoader.close()` directly delete the metadata of loaded classes?** No. Class unloading depends on the JVM/GC and the eligibility of the defining loader.

**6. Are `used` and `committed` the same?** No; committed can be higher than used due to allocator chunks, slack, and reclaim state.

**7. Is `reserved` equal to the amount of physical RAM used?** No. It is virtual address space reserved in advance.

**8. Can `-Xmx` be used to precisely limit Metaspace?** No. `-Xmx` limits the Java heap, not HotSpot metadata memory.

**9. Why can JEP 387 help applications that reload plugins?** Elastic Metaspace improves the ability to return unused native memory after class unloading, though it cannot replace lifecycle cleanup.

**10. Does NMT cover every malloc from third-party native code?** No. NMT primarily tracks HotSpot VM internals and has scope limitations.

**11. If Metaspace grows continuously, should you raise the limit or look for references first?** Assess the situation first: whether it is frequent loading or unreclaimed loader generations; trace retaining paths and the lifecycle root cause.

**12. If you do not see a class-unload log immediately after `close`, is it definitely a leak?** No. GC/class unloading has no specific timing guarantee.

## 21. Official Reference Documentation

- **JVMS Java SE 17, `2.5.4` – Method Area**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.4
- **JLS Java SE 17, `12.7` – Unloading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- **Java SE 17 `MemoryPoolMXBean` / `MemoryUsage`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- **Oracle Java SE 17, GC Tuning – Other Considerations, Metaspace**: https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html
- **Oracle Java SE 17, Native Memory Tracking**: https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- **Oracle Java SE 17, `java` launcher options**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JEP 387 – Elastic Metaspace (JDK 16)**: https://openjdk.org/jeps/387
- **Java SE 17 `URLClassLoader`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html

**Key takeaway:** **The method area is a logical specification; Metaspace is a HotSpot detail**. A runtime class has its metadata managed in association with its defining loader; a loader kept alive can cause its metadata to continue occupying memory. To diagnose accurately, combine **the Metaspace pool, NMT, classloader stats, heap retaining paths, and OS/container metrics**, always distinguishing **used, committed, reserved, and RSS**. Calling `close` on a loader or raising memory limits cannot replace proper lifecycle and reference management.
