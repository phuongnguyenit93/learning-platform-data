# Distinguishing Used, Committed, Reserved, and Process Memory in the JVM

When monitoring a Java application, you may see **heap used = 400 MiB**, **heap committed = 768 MiB**, **heap max = 2 GiB**, while the operating system reports **RSS = 1.1 GiB** and **virtual memory = several GiB**. These numbers **do not contradict each other**: they are measuring different aspects and sometimes belong to different scopes.

To properly analyze JVM memory usage, you need to distinguish at least five questions:

1. **Used**: how much memory is **currently recorded as used** by the JVM within a specific managed area?
2. **Committed**: how much capacity has the JVM **committed to making available for use** for that area?
3. **Reserved**: how much **virtual address space** has the JVM **reserved in advance**, which may be larger than the committed portion?
4. **Process memory**: what memory areas does the Java process actually have outside the Java heap, and how does the operating system record resident/virtual memory?
5. **Limit/maximum**: which **part** does a limit set by the Java heap, native allocations, the operating system, or a container apply to, rather than being a single shared number?

This article uses **Java SE 17 and common HotSpot/OpenJDK** as its context. Java API definitions and JVM memory areas are part of the specification; **Native Memory Tracking (NMT)** terms, RSS/VSZ, `-Xms`/`-Xmx` flags, and container behavior depend on the implementation/operating system. Always check the exact source and version before comparing.

## 1. Overview: a Java process is not just the Java heap

In a running JVM, the following can exist simultaneously:

- **Java heap**: the area serving object/array allocations according to JVM semantics, managed by the GC. This is the part usually bounded by `-Xmx`.
- **Metaspace/class metadata**: class data and metadata that HotSpot manages using native memory (from Java 8 onward), not simply residing within the `-Xmx` heap limit.
- **Thread stacks**: areas related to thread stacks, along with native resources allocated for each thread.
- **Code cache/JIT**: compiled machine code and structures supporting the compiler/runtime.
- **Direct buffers and native allocations**: for example `ByteBuffer.allocateDirect`, JNI, C/C++ libraries, compression/encryption libraries, and native allocators.
- **Memory-mapped files, shared libraries, file-backed mappings**: how the operating system maps file contents into the process's address space.
- **JVM structures and other components**: GC, symbol/string structures, class loaders, agents, profilers, allocator fragmentation, runtime libraries.

Some of the above components are managed by the JVM, while others are managed by native libraries or the operating system. **Not all of them appear in `MemoryMXBean.getHeapMemoryUsage()`**, and not every byte of process RSS belongs to the heap.

```text
                        Java Process
+---------------------------------------------------------------+
| Process virtual address space (VSZ / virtual size)            |
|                                                               |
|    Java heap reserved                                         |
|      +--------------------------------------+                 |
|      | Heap committed                       |                 |
|      | +-----------------------+            |                 |
|      | | Heap used             |            |                 |
|      | +-----------------------+            |                 |
|      +--------------------------------------+                 |
|                                                               |
|    Metaspace / class metadata                                 |
|    Thread stacks / code cache / GC native / direct buffers    |
|    Shared libraries / mapped files / JVM runtime / native libs|
+---------------------------------------------------------------+
   ^
   | OS resident pages (RSS) is a DIFFERENT measurement:
   | the pages currently resident in RAM for the process at measurement time,
   | not the area of the rectangle above.
```

This diagram is a **conceptual model**, not an exact layout of VM address ranges, allocation order, or physical page commitment for every JVM.

## 2. What is “Used”?

In the Java Management API, `java.lang.management.MemoryUsage` describes the state of **a memory area** using `init`, `used`, `committed`, and `max`. The **`used`** field is the amount of memory **recorded as used in that area** at the time the snapshot is taken.

For example:

- **Heap used**: the heap capacity currently holding allocations/objects and structures recorded as used by the heap-managed area according to how the GC/JVM measures it.
- **Non-heap used**: the capacity of non-heap areas recorded by the management API; it is **not** the total of all native allocations of the process.
- **Memory pool used**: the usage of a specific pool such as a heap generation or metaspace, with semantics and update timing depending on the pool.

### Used is not strictly synonymous with live objects

**Used can differ from the memory size of live objects after a full GC.**

- Before GC, the heap may contain objects that are **no longer reachable** but have not yet been reclaimed. They can still affect `used` until GC processes them.
- After GC, `used` may decrease; you should not expect the decrease to equal the exact byte size of unreferenced objects.
- GC may have regions, allocation buffers, overhead, and its own accounting boundaries. You should not calculate exact retained heap from a single `used` number.
- To know which objects are holding memory, use a **heap histogram, heap dump, or appropriate profiler**; to know whether the heap is growing or shrinking, track `used` over **time and across GC cycles**.

For example, an application whose heap used grows from 350 to 600 MiB and then drops back to 380 MiB after GC does not necessarily have a memory leak. You need to look at the **post-GC trend line**, allocation rate, GC overhead, and retained objects.

## 3. What is “Committed”?

`MemoryUsage.getCommitted()` describes the amount of memory the JVM **has committed and made ready for use** for the reported area. For the Java heap, this is the heap capacity currently managed by the JVM/GC and brought into the usable range, usually lying between `used` and `max` if `max` is defined.

Fundamental invariant in `MemoryUsage`:

```text
0 <= used <= committed

If max >= 0:
    committed <= max
```

Do not blindly apply that invariant across **two different metric sources**: heap used in an MXBean and NMT reserved for the entire process are not four fields of the same `MemoryUsage` object.

### Committed is not RSS

**Committed does not mean every byte already has a physical page resident in RAM at the time of measurement.**

Reasons:

- The operating system manages virtual memory and allocates/touches physical pages according to its own mechanisms. A memory range may be committed but not yet touched or may have been paged out.
- The runtime and OS may use techniques such as demand paging, transparent huge pages, swap, or lazy physical backing.
- Conversely, RSS may include **mmap file pages, native allocations, code cache, thread stacks**, and other components outside the Java heap.
- Therefore, heap committed = 800 MiB **does not imply** that process RSS must be exactly 800 MiB, greater than 800 MiB, or less than 800 MiB in all environments.

**JVM committed** should also not be mechanically equated with the term **commit charge** in Windows tools: the operating system has its own accounting system, does not cover the same set of regions, and does not necessarily measure the same conditions.

### What does committed minus used tell you?

Within the same `MemoryUsage` snapshot:

```text
committed - used = the portion of committed capacity not yet recorded as in use
```

That number does **not** tell you:

- How much physical RAM the operating system has left.
- That the JVM is guaranteed to allocate that exact number of additional object bytes without a GC.
- How many bytes of live objects will remain after GC.
- How much memory must be returned to the operating system if object creation stops.

This is an accounting difference **within the JVM area**; actual allocation still depends on layout, GC, contiguous allocation/region constraints, and overhead.

## 4. What is “Reserved”?

At the virtual memory level, **reserved** is usually the **virtual address** space that the runtime sets aside for a purpose such as the Java heap, thread stacks, or code cache; **committed** is the portion within the reservation that is committed for use.

On HotSpot, the **Native Memory Tracking (NMT)** tool can display categories with:

```text
reserved = ... KB
committed = ... KB
```

Important points:

1. **Reserved is not actually allocated RAM**; reserving virtual addresses does not mean physical pages are backing the entire range.
2. **Reserved can be larger than committed**; for example, the heap may reserve address space near the heap maximum to have room to grow later while only committing a portion.
3. **Committed can be larger than used** if the area has a corresponding `used` metric; however, NMT does not always report a `used` field with the same meaning as the heap MXBean.
4. **Reserved does not mean every virtual address range of the process**; NMT only covers memory recorded by that tracking mechanism, not every mapping that may exist.
5. Large reservations can make **VSZ/VmSize** look high, but a large VSZ value alone does not prove the application is consuming a lot of physical RAM.

### *Hypothetical* numerical example to understand the concept

Suppose at a given moment, an application has the following **illustrative** numbers:

| Metric | Hypothetical value | Meaning |
| --- | ---: | --- |
| Heap max | 2,048 MiB | Maximum usable heap limit from the runtime configuration |
| Heap reserved (NMT) | 2,048 MiB | Virtual address space reserved in advance for the heap in the example |
| Heap committed | 768 MiB | Portion of the heap committed for use |
| Heap used | 400 MiB | Portion of the heap currently recorded as used by the JVM |
| Process RSS | 1,100 MiB | Total resident pages accounted to the process by the operating system |
| Process virtual size | 6,000 MiB | Total virtual address space mapped in the process |

This is a **hypothetical set of numbers for explanation**, not an actual measurement on a JVM. You can verify `400 <= 768 <= 2048` within the heap metric, but **you cannot take `1100 - 768 = 332` and claim that is the exact total native memory**. RSS and heap committed do not measure the same thing, and shared/file-backed mappings, unused committed pages, and OS effects make that subtraction invalid as a standard accounting formula.

## 5. How does “Max” differ from reserved and committed?

In `MemoryUsage`, **`max`** is the maximum capacity that the area can use according to the metric's contract; **`-1`** means the maximum value is **undefined**.

For the Java heap on HotSpot:

- `-Xmx` typically limits the **heap maximum**, not the entire resident memory or virtual memory of the process.
- `-Xms` typically sets the **initial heap size** or the initial heap level managed by the JVM.
- The runtime may **increase/decrease committed heap** between current usage and the configured limit, depending on the collector, flags, and OS conditions.
- Heap **reserved** may relate to the address range reserved for the heap maximum, but **there is no guarantee that NMT reserved always equals `-Xmx` exactly** across all builds/GCs.
- The `max` of a non-heap memory pool may return `-1`, or have its own limit unrelated to `-Xmx`.

Therefore, this interpretation:

```text
-Xmx2g
  does not mean:
    process RSS <= 2 GiB
    process VSZ <= 2 GiB
    total native + heap memory <= 2 GiB
```

If an application uses 1.4 GiB of heap, 500 MiB of direct buffers, metaspace, code cache, threads, and native libraries, **process memory can exceed `-Xmx`** even while the heap remains below its limit.

### Avoid confusing `-Xms` with “used at startup”

`-Xms512m` does **not** mean 512 MiB of objects have been created right when the JVM starts. Initial heap **committed** may be close to the configured size, whereas heap **used** reflects the amount actually used. The JVM may also pre-touch memory if relevant flags are enabled (for example `-XX:+AlwaysPreTouch` in supported environments), affecting the resident footprint; do not infer runtime RSS from `-Xms` alone.

## 6. Process memory: RSS, VSZ/VmSize, and PSS

Operating system tools do not use the same set of metrics as the JVM.

| OS Metric | Concept | What CANNOT be concluded from this single number |
| --- | --- | --- |
| **RSS** (Resident Set Size) | Number of physical resident pages currently assigned to the process according to the OS counting method | Not heap used, not heap committed, not purely private memory |
| **VSZ/VIRT/VmSize** | Total size of the process's virtual memory mappings | Not actual physical RAM used |
| **PSS** (Proportional Set Size; Linux) | Resident memory scaled proportionally for shared pages | Not heap used; also not a type of NMT reserved |
| **Private dirty / anonymous RSS** | OS views into resident private/anonymous pages | Cannot automatically separate heap from all types of native allocations |
| **Peak RSS / VmHWM** | Recorded resident high-water mark | Not the current RSS value |
| **Swap** | Pages/charges currently in swap according to OS tools | Does not by itself tell you which Java object types were paged out |

### Why can RSS be higher than heap committed?

Because RSS includes resident pages from **many areas outside the heap**, such as native buffers, machine code/JIT, metaspace, thread stacks, memory-mapped files, and shared libraries. There is no constraint that “RSS must be smaller than `-Xmx`”.

### Why can RSS be lower than heap committed?

A committed heap region may not have been fully touched yet, or some pages may not currently be resident. OS memory policies and collector behavior cause committed/virtual and resident areas not to coincide.

### Why can VSZ be very large?

Every reserved virtual range contributes virtual address space. Heap, thread stacks, code cache, mmap, and other reservations can make VSZ much larger than physical RAM. A high VSZ value **by itself is not proof of a memory leak**. You must also analyze growth rate, RSS/PSS, native allocations, container limits, and application state.

### Shared memory makes summing RSS across multiple processes misleading

If two processes map the same shared library page, each process's RSS may **count the entire page**. Summing the RSS of two processes can **double-count shared pages**. PSS is a complementary view on Linux when you want to prorate shared portions; it still does not become a JVM `used` metric.

## 7. Java 17’s MemoryMXBean and MemoryUsage

The Java Management API provides metrics by **heap** and **non-heap**:

- `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()`
- `ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()`
- `ManagementFactory.getMemoryPoolMXBeans()`, with `MemoryPoolMXBean.getUsage()` for each pool.

`MemoryUsage` objects have four fields:

| Method | Meaning |
| --- | --- |
| `getInit()` | Initial capacity requested by the JVM, or `-1` if undefined |
| `getUsed()` | Capacity recorded as currently in use |
| `getCommitted()` | Capacity committed by the JVM and ready for use |
| `getMax()` | Limit of the area if known, may be `-1` |

**These are per-JVM-area metrics**, not all native allocations of the process; reading them does not require parsing OS `/proc`.

### Fully deterministic Java 17 example: the four fields of MemoryUsage

Create **`MemoryUsageExample.java`**:

```java
import java.lang.management.MemoryUsage;

public class MemoryUsageExample {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        // Hypothetical numbers: does not measure the current JVM.
        MemoryUsage sample = new MemoryUsage(
                0L, 40L * MIB, 96L * MIB, 512L * MIB);

        System.out.println("used=" + sample.getUsed() / MIB + "MiB");
        System.out.println("committed=" + sample.getCommitted() / MIB + "MiB");
        System.out.println("max=" + sample.getMax() / MIB + "MiB");
        System.out.println("committedMinusUsed="
                + (sample.getCommitted() - sample.getUsed()) / MIB
                + "MiB");
        System.out.println("invariant="
                + (sample.getUsed() <= sample.getCommitted()
                && sample.getCommitted() <= sample.getMax()));
    }
}
```

```bash
javac --release 17 MemoryUsageExample.java
java MemoryUsageExample
```

**Exact stdout:**

```text
used=40MiB
committed=96MiB
max=512MiB
committedMinusUsed=56MiB
invariant=true
```

Note: the `MemoryUsage` constructor in this example creates **a hypothetical snapshot with fixed numbers**; it does not actually allocate 512 MiB or change `-Xmx`. Do not use these numbers to draw conclusions about the running machine.

### Java 17 example reading real JVM metrics

Create **`LiveJvmMemory.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public class LiveJvmMemory {
    private static final long MIB = 1024L * 1024L;

    private static String amount(long bytes) {
        return bytes < 0 ? "undefined"
                : String.format("%.1f MiB", bytes / (double) MIB);
    }

    private static void show(String name, MemoryUsage usage) {
        System.out.println(name
                + ": used=" + amount(usage.getUsed())
                + ", committed=" + amount(usage.getCommitted())
                + ", max=" + amount(usage.getMax())
                + ", init=" + amount(usage.getInit()));
    }

    public static void main(String[] args) {
        show("heap", ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage());
        show("non-heap", ManagementFactory.getMemoryMXBean()
                .getNonHeapMemoryUsage());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                show("pool " + pool.getName(), usage);
            }
        }
    }
}
```

```bash
javac --release 17 LiveJvmMemory.java
java -Xms128m -Xmx512m LiveJvmMemory
```

**Stdout depends on the JVM, GC, timing, and OS** — there is no single exact set of byte counts across all machines. The template **only illustrates the format**, not a measured result:

```text
heap: used=<number> MiB, committed=<number> MiB, max=<number> MiB, init=<number> MiB
non-heap: used=<number> MiB, committed=<number> MiB, max=undefined, init=<number> MiB
pool <pool name>: used=<number> MiB, committed=<number> MiB, max=<number or undefined>, init=<number> MiB
```

**Do not use the template above as a regex requiring exact output**: for example, `<...>` here is an explanatory placeholder, the non-heap `max` value is not always `undefined`, and the list of pools depends on the collector.

### Why doesn't summing all memory pools always match a single heap snapshot?

- Values may be captured **non-simultaneously**, with GC or allocations occurring between calls.
- GC divides the heap into pools/regions according to the collector's policy; a pool's maximum value may be undefined or fluctuate.
- Metrics are updated at different times and according to pool structure; do not use a manual sum as a strict byte-for-byte match against the heap aggregate across all releases/collectors.
- Non-heap MXBean is not a complete measurement of RSS or all native allocations.

## 8. Runtime.totalMemory/freeMemory/maxMemory: same direction, different snapshot

A familiar API:

```java
Runtime runtime = Runtime.getRuntime();
long total = runtime.totalMemory();
long free = runtime.freeMemory();
long max = runtime.maxMemory();
long approximateUsed = total - free;
```

This is an **illustrative fragment** placed inside a method.

- `totalMemory()`: the heap capacity currently available for the JVM to use according to the runtime contract, often compared with **heap committed**.
- `freeMemory()`: the free portion of the heap **within the current `total`**, not free physical RAM.
- `maxMemory()`: the maximum limit the JVM will attempt to use for the heap, not the process RSS limit.
- `total - free` is an estimate of **heap currently used** at the time of the call, but each method is a separate observation; allocations/GC may occur between calls, so do not require it to match a subsequent `MemoryMXBean` reading exactly.

Do not use `Runtime.freeMemory()` as “how many GB of RAM the machine has left” and do not assume `Runtime.maxMemory()` also limits direct buffers, metaspace, and thread stacks.

## 9. Native Memory Tracking (NMT): viewing reserved/committed on the HotSpot side

**Native Memory Tracking** is a diagnostic capability of HotSpot/OpenJDK for tracking allocations/mappings within the JVM's supported scope. NMT can categorize memory into categories such as **Java Heap**, **Class**, **Thread**, **Code**, **GC**, **Compiler**, **Internal**, etc., with total **reserved** and **committed**.

NMT is an *implementation-specific* tool, not a standard `MemoryMXBean` that every JVM is required to implement identically. Category names and statistics may vary by JDK build/collector.

### Enabling NMT at startup

For example:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m LiveJvmMemory
```

The `LiveJvmMemory` program in the previous example exits very quickly, so there may no longer be a process to attach to. In a real application, enable NMT on a **long-running JVM process** (a server or a program with a suitable wait time) and then use its process ID.

While the process is running:

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

This is an **illustrative command with placeholder `<PID>`**; replace it with the actual PID and run it while the VM is still running. If NMT was not enabled at **startup**, you cannot simply request `summary` and expect data; it must be configured appropriately when starting the JVM.

### Illustrative NMT output format

```text
Native Memory Tracking:
Total: reserved=...MB, committed=...MB

- Java Heap (reserved=...MB, committed=...MB)
- Class     (reserved=...MB, committed=...MB)
- Thread    (reserved=...MB, committed=...MB)
- Code      (reserved=...MB, committed=...MB)
- GC        (reserved=...MB, committed=...MB)
```

These lines **only describe how to read the output**, do not represent an actual NMT result, and do not attempt to list every category. For some areas tracked by the JVM via `malloc`, NMT may count the allocated portion as both reserved and committed accordingly; memory maps may have `reserved` larger than `committed`. Do not force the same simple reservation model onto every line.

### Tracking *deltas* instead of a single snapshot

A common usage pattern:

```bash
jcmd <PID> VM.native_memory baseline
# Let the workload run through the phase to observe.
jcmd <PID> VM.native_memory summary.diff scale=MB
```

If NMT was started in detail mode, you can also use appropriate detailed reports such as `detail`/`detail.diff` when supported by the tool. Because `summary` has lower overhead than `detail`, balance the cost against your operating environment.

**Reading deltas properly:** a significant increase in NMT native committed in the Thread category may suggest more threads; an increase in Class may suggest class metadata/classloaders; Code may increase with JIT compilation. These are **investigative signals**, not proof by themselves of a leak source or which Java object is retaining memory.

### NMT does not measure all native memory of every library

NMT's scope does not comprehensively cover native allocations performed directly by third-party libraries outside the tracked JVM mechanisms. It is also not direct RSS. Therefore:

- **NMT committed != process RSS** is normal.
- **NMT reserved != process VSZ** is normal.
- Process RSS increasing while NMT committed barely changes may come from mmap/file-backed pages, native/JNI libraries, allocator behavior, or portions not recorded by NMT.
- Use appropriate OS/native profiler tools to investigate further; do not treat “RSS - NMT committed = memory leak bytes” as an exact formula.

## 10. Direct buffers, metaspace, and thread stacks are outside the heap used story

### Direct ByteBuffer

`ByteBuffer.allocateDirect(size)` allocates a buffer with backing memory outside the Java heap according to JVM/runtime mechanisms. **The `ByteBuffer` wrapper/reference object may still live on the heap**, while the backing memory can be managed natively; therefore:

- Small increases in Java heap used do **not** prove direct memory is not growing.
- `-Xmx` is not the sole limit for allocating direct buffers.
- HotSpot has related options such as `-XX:MaxDirectMemorySize`; defaults and enforcement behavior should be checked against the JDK/build.
- When backing memory is released may depend on reference reachability, cleaners, and GC, not necessarily immediately when a local variable goes out of scope.

### Illustrative Java 17 program: direct allocation and heap wrapper

Create **`DirectMemoryDemo.java`**:

```java
import java.nio.ByteBuffer;

public class DirectMemoryDemo {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(1024);
        ByteBuffer direct = ByteBuffer.allocateDirect(1024);

        System.out.println("heapDirect=" + heap.isDirect());
        System.out.println("nativeDirect=" + direct.isDirect());
        System.out.println("heapCapacity=" + heap.capacity());
        System.out.println("nativeCapacity=" + direct.capacity());
    }
}
```

```bash
javac --release 17 DirectMemoryDemo.java
java DirectMemoryDemo
```

**Exact stdout:**

```text
heapDirect=false
nativeDirect=true
heapCapacity=1024
nativeCapacity=1024
```

`isDirect()` indicates whether the buffer is direct according to the API; it does **not** measure exact RSS. This demo does not prove that resident memory will increase by exactly 1024 bytes because wrappers, alignment, the native allocator, and OS policies are also involved.

### Metaspace

From Java 8 onward, HotSpot uses **native memory for class metadata** in metaspace. When loading many classes or keeping many class loaders alive, native committed for class metadata can grow while **heap used does not grow proportionally**. There are still objects on the heap related to `Class`/class loaders; saying “everything about classes is off-heap” is also incorrect.

- `-XX:MaxMetaspaceSize` is an example configuration limiting metaspace on HotSpot; it is not a total native memory limit.
- `OutOfMemoryError: Metaspace` points to a class metadata and limit/resource issue, not an immediate conclusion to “increase `-Xmx`”.
- If you suspect a class loader leak, check the number of classes/loaders, unloading behavior, references retaining the class loader, and NMT/ClassLoader-related diagnostics.

### Thread stacks

Many threads can increase stack/native memory demand even when heap used changes very little:

- Flags like `-Xss` affect thread stack resources (applicability depends on the JVM/thread type and OS).
- NMT may show **Thread reserved larger than committed** because reserved stack space is not necessarily all committed/touched.
- Creating threads also consumes other OS resources, and containers may have PID/thread count limits.
- `java.lang.OutOfMemoryError: unable to create native thread` is not necessarily due to a full heap; it can relate to native memory, OS process/thread limits, or resource controls.

Do not use `Threads × -Xss` as an exact RSS measurement. That may be an estimate of reserved virtual stack space, not actual resident pages.

## 11. Reading operating system metrics on Linux

If Java runs on Linux, you can inspect process information with a valid PID:

```bash
ps -o pid,rss,vsz,comm -p <PID>
grep -E 'VmSize|VmRSS|VmHWM|RssAnon|RssFile|VmSwap|Threads' /proc/<PID>/status
cat /proc/<PID>/smaps_rollup
```

These are **illustrative commands**; replace `<PID>` with the real PID, and `smaps_rollup` may be restricted by permissions or unavailable on older kernels. `ps` typically displays RSS/VSZ in KiB on Linux; check the environment's manual rather than assuming units across all OSes.

Practical meaning:

- `VmSize` relates to **virtual address space**, not consumed RAM.
- `VmRSS` is close to the process RSS view, including various types of resident pages, possibly shared.
- `RssAnon` and `RssFile` help distinguish anonymous/file-backed pages according to OS bookkeeping, **not directly indicating Java heap vs non-heap**.
- `smaps_rollup` can provide aggregated RSS/PSS and private/shared metrics; useful if RSS contains many file-backed/shared mappings.
- Metrics from different sources are captured at **different times**; CPU/GC/allocator activity can change memory between measurements.

### OS memory and JVM metrics must be matched by the same PID and same time

If running multiple JVMs on a machine, identify the PID of the **right application**. `jcmd -l` can list some available Java processes; `ps` helps inspect processes; container PID namespaces can cause the PID observed inside and outside the container to **differ**.

Do not compare the heap used of JVM A with the RSS of JVM B or the total RSS of the cgroup/container and conclude there is a leak in JVM A.

## 12. Container memory: not the Java heap maximum

In containers or Kubernetes, cgroups limit **resources for the entire cgroup/container**, not just the Java heap. On Linux cgroup v2, common files include:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
```

**These paths are only examples for common cgroup v2 environments**; systems may mount them elsewhere, use cgroup v1, or restrict access permissions.

- `memory.current`: memory currently accounted to the cgroup, which may include **anonymous memory, page cache, kernel memory**, and other components depending on kernel mechanisms.
- `memory.max`: the hard limit of the cgroup, or the string `max` if there is no finite limit in that file.
- `memory.stat`: breakdown of cgroup usage sources according to the kernel.
- `memory.events`: events such as hitting limits or OOM/OOM-kill within the relevant scope.

**Container memory usage does not equal process RSS** if the cgroup contains multiple processes, caches, and accounted kernel regions. A container can also be **OOM killed** by the kernel even though the JVM never threw `OutOfMemoryError: Java heap space`, because total cgroup consumption exceeded the limit.

### Sizing example

Suppose the container limit is **2 GiB** and `-Xmx2g` is set. This configuration **leaves no budget** for metaspace, stacks, code cache, GC native allocations, direct buffers, agents, mapped memory, or OS/page-cache accounting. Therefore, the risk of container memory pressure is very high, even when Java heap used has not reached 2 GiB.

Budget calculation should include:

```text
Container / process budget (estimate, not an RSS equality)
    = heap target
    + direct/native buffers
    + metaspace/classes
    + thread stacks
    + code cache + GC/JVM internals
    + native libraries, agents
    + headroom for runtime and kernel accounting
```

Do **not** add heap used, NMT reserved, and RSS together: they are overlapping views. Prefer measuring real numbers under peak workload with headroom, rather than combining metrics with different units/semantics.

### Do not guess the cause from an exit code alone

An exit status like `137` in some environments is often associated with the `SIGKILL` signal, which may be caused by the container OOM killer or an external kill. **An exit code alone does not prove a kernel OOM**; check Kubernetes events, cgroup `memory.events`, logs, and orchestrator information.

## 13. Comparison table of observation tools

| Tool/API | What it can show | What it does not directly provide |
| --- | --- | --- |
| `MemoryMXBean.getHeapMemoryUsage()` | Heap used/committed/max/init | Process RSS/VSZ and all native allocations |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Non-heap managed usage | All native memory from third-party libraries |
| `MemoryPoolMXBean` | Pool usage by collector/manager | An unbiased OS resident snapshot |
| `Runtime.totalMemory/freeMemory/maxMemory` | API-level heap information | Free RAM on the machine |
| `jcmd <PID> GC.heap_info` | JVM-specific heap/GC information | Full process memory mapping |
| `jstat -gc <PID>` | Collector-specific GC/heap pool counters | Exact total RSS |
| `jcmd <PID> VM.native_memory summary` | NMT reserved/committed tracked by the JVM | All native allocations and physical RSS |
| `ps`, `/proc/<PID>/status` | Linux process VSZ/RSS/thread counters | Reachable heap objects or Java ownership |
| `/proc/<PID>/smaps_rollup` | Aggregated PSS/RSS, private/shared memory | Object histogram or GC reachability |
| cgroup `memory.current`/`memory.max` | Cgroup usage/limit | How much each Java method/object used |
| Heap dump/profiler | Objects/retained heap/allocations depending on mode | By default, does not give a full native RSS breakdown |

**Avoid “a single metric as the single source of truth”**. Start from a specific diagnostic question: heap leak, direct/native leak, too many threads, metaspace growth, or OS/container pressure.

## 14. A repeatable measurement workflow on Java 17

### Step 1: lock down the environment and limits

Record at least: JVM vendor/build, Java version, GC, `-Xms`/`-Xmx`, `-Xss`, NMT flag, container memory limit, and PID. If possible, enable GC logging/NMT from startup for planned observations.

Example running a **real server** (not a program that exits immediately):

```bash
java -Xms256m -Xmx1024m -XX:NativeMemoryTracking=summary -jar app.jar
```

`app.jar` is only an illustrative name for a properly built application. Do not add `-jar` to commands for `.class` Java examples if you do not have a JAR.

### Step 2: observe simultaneously for the same PID

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> VM.native_memory summary scale=MB
ps -o pid,rss,vsz,comm -p <PID>
```

If running in cgroup v2, also record `memory.current` and `memory.max` in the **actual cgroup containing the process**. Read units carefully: bytes, KiB, MiB, and rounded numbers easily create discrepancies that look like bugs.

### Step 3: set a baseline to observe deltas

```bash
jcmd <PID> VM.native_memory baseline
# Run a representative workload with steady load and peak.
jcmd <PID> VM.native_memory summary.diff scale=MB
```

At the same time, record **heap used after GC** or heap pool trends, RSS/PSS, thread count, and cgroup memory. The NMT delta shows which category grew from the baseline; it does not by itself tell you which objects remain reachable.

### Step 4: classify the symptom

| Symptom | Priority hypothesis to check |
| --- | --- |
| Heap used after GC rises steadily, near heap max | Java heap retention, unbounded cache, object leak |
| Heap committed is large, heap used is low | Heap has not shrunk or JVM is keeping committed headroom; does not prove a leak by itself |
| NMT Thread reserved/committed increases and thread count increases | Many threads, stacks/native thread resources |
| NMT Class/Metaspace increases along with rising class loader count | Dynamic class loading, class loader retention |
| NMT Code increases then stabilizes | JIT code cache warming; growth does not equal a leak |
| RSS increases, heap used is stable, NMT native increases | Investigate native categories, direct buffers, agents |
| RSS increases while NMT barely changes | Check mmap, third-party native, allocator fragmentation, OS pages |
| Container memory.current rises rapidly while process RSS does not match | Cgroup has other processes/cache/kernel accounting; check memory.stat |
| OOMKilled while heap usage is not high | Container/native budget pressure, not just Java heap |

### Step 5: confirm with the right tool

- Suspected **Java object leak**: allocation profiler, heap dump, dominator/retained-size analysis, and GC logs.
- Suspected **native memory leak**: NMT trend combined with native profiler/OS mappings, especially C/JNI libraries not covered by NMT.
- Suspected **too many threads**: thread dump, thread count over time, stack reservation, thread pool configuration.
- Suspected **container limit**: cgroup events, kubelet/orchestrator events, memory pressure, and total budget.
- Suspected **GC/commit behavior**: GC logs, heap occupancy before/after collection, actual GC shrink/uncommit behavior.

Do not proactively call `System.gc()` in production just to “make metrics look nicer”. GC is not guaranteed to complete or reduce footprint immediately; forcing GC can hurt latency.

## 15. Using measurements to avoid false inferences

### Scenario A: heap committed is high but used is low

For example (hypothetical): heap used 250 MiB, committed 1,000 MiB, max 2,000 MiB. The JVM may keep the heap committed to avoid expanding again, or the collector has not shrunk / does not shrink after GC. **Not enough data to conclude a leak**. Check heap occupancy across GCs, memory pressure, and collector flags.

### Scenario B: NMT reserved is high but RSS is low

For example: NMT heap reserved 4 GiB, heap committed 512 MiB, RSS 900 MiB. There is no contradiction: the reserved portion is **address space**, not 4 GiB of physical RAM. Check virtual address space limits (especially in older 32-bit environments) only when relevant; do not upgrade RAM based solely on `reserved`.

### Scenario C: RSS increases while heap used stays nearly constant

Possible culprits: direct buffers, JNI/native library allocations, more threads, JIT code cache, metaspace, touched file-backed memory, or native allocator fragmentation. Use NMT + OS + profiler; **do not automatically conclude “memory leak in the Java heap”**.

### Scenario D: process RSS is larger than `-Xmx`

Entirely possible: `-Xmx` only limits the heap. The process has other memory, and RSS is a resident metric of the entire process. Fix this by understanding the native budget; blindly increasing `-Xmx` can make container OOM **more likely**.

### Scenario E: a container has memory.current higher than Java process RSS

The cgroup may also include page cache, kernel memory, or other processes. Check `memory.stat` and the process list; do not force the two metrics to match byte-for-byte.

### Scenario F: VSZ is unusually high but RSS/PSS is stable

There may be many reserved address ranges, thread stacks, or mmap mappings. Monitor trends and actual failures. On 64-bit platforms, virtual address space is huge; a high VSZ number alone does not mean physical memory is about to run out.

## 16. Common misconceptions and how to correct them

| Misconception | Correct understanding |
| --- | --- |
| “Heap used = RSS of the Java process” | Heap used is only one area; RSS includes many mapped/resident pages |
| “Heap committed = RAM occupied” | Committed is a JVM-area metric; physical residency is measured by RSS/PSS at the OS level |
| “Heap reserved = RAM consumed” | Reserved is usually virtual addresses; not necessarily backed by physical pages |
| “`-Xmx` = limit on all process memory” | `-Xmx` limits the heap, not native/direct/stacks/metaspace |
| “`-Xms` = heap objects initially in use” | `-Xms` relates to the initial heap, not creating that many objects |
| “`Runtime.freeMemory()` is the machine's free RAM” | It is the free heap space within the current `total` |
| “NMT committed equals RSS” | NMT tracking and OS residency differ in scope and semantics |
| “NMT sees all memory of JNI/C libraries” | NMT does not guarantee tracking all allocations outside JVM mechanisms |
| “Summing RSS of multiple processes equals physical RAM used” | Shared pages can be double-counted; PSS provides a different view |
| “High VSZ proves a leak” | It may just be virtual address reservations |
| “Low heap used means OOM is impossible” | Native/container/thread/metaspace allocations can still cause OOM |
| “Rising heap used definitely means a leak” | Need to compare post-GC and correlate with objects/retention |
| “Every `MemoryPoolMXBean.getMax()` is a finite positive number” | Max can be `-1` (undefined) |
| “Different measurement tools must match byte-for-byte” | Scope, snapshot timing, and units differ |
| “Increasing `-Xmx` fixes container OOM” | It can starve the native budget even more; must analyze total footprint |
| “A single measurement sample proves the root cause” | Need trends, GC/allocation/OS evidence, and workload reproduction |

## 17. Self-check questions

**Question 1:** Heap used = 300 MiB, committed = 600 MiB, max = 2 GiB. Does that mean the process is using exactly 300 MiB of RAM?

**No.** 300 MiB is heap used according to the metric, not counting all resident native/file-backed pages.

**Question 2:** Heap reserved = 8 GiB, but the machine only has 4 GiB of physical RAM; is this data definitely wrong?

**No.** Reserved can be a virtual address range, not requiring 8 GiB of physical RAM immediately.

**Question 3:** Java process RSS = 1.5 GiB, `-Xmx1g`. Is the JVM necessarily violating the limit?

**No.** `-Xmx` only sets the Java heap limit; non-heap/native memory still consumes process memory.

**Question 4:** What does `getCommitted() - getUsed()` in the same `MemoryUsage` tell you?

**The portion of capacity committed but not yet recorded as used by the metric**. It is not free OS RAM.

**Question 5:** A memory pool has `getMax() == -1`. Has that area run out of memory?

**No.** `-1` indicates an **undefined** maximum according to the API.

**Question 6:** NMT summary is not increasing, but RSS is increasing. Can you conclude there is no native leak?

**No.** NMT does not cover every library/mapping; you still need native profiler/OS evidence.

**Question 7:** In a container, heap used is not high, yet the kernel OOM-kills the process. What could be the cause?

**Total cgroup memory** including heap, native memory, stacks, file cache/kernel allocations, and other processes exceeded the limit. Check cgroup events/metrics.

**Question 8:** Should you take a single pre-GC heap used measurement to conclude an object leak?

**No.** Prefer post-GC occupancy trends and retained object analysis, with the corresponding workload.

**Question 9:** Can the RSS of two processes sharing a shared library page double-count it?

**Yes.** RSS counts resident pages per process; PSS is a way to prorate shared pages on Linux.

**Question 10:** You run `jcmd <PID> VM.native_memory` and the tool reports NMT disabled. Can you fix it by adding `summary` to the command?

**No.** NMT must be configured appropriately from JVM startup; running `jcmd` does not enable tracking retroactively.

## References and further reading

- [Java SE 17 `MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): definition of `init`, `used`, `committed`, `max`, and snapshot validity.
- [Java SE 17 `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap vs non-heap memory usage.
- [Java SE 17 `MemoryPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): per-pool usage and thresholds.
- [Java SE 17 `Runtime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `totalMemory`, `freeMemory`, `maxMemory`.
- [JVMS Java SE 17, Chapter 2 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): heap, method area, JVM stack, native stacks.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct and heap buffers.
- [Java SE 17 `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info` and `VM.native_memory`.
- [Java SE 17 `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory utilization statistics.
- [Oracle Java Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): tracking mechanism and NMT limitations.
- [Linux proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): `VmSize`, `VmRSS`, `RssAnon`, `RssFile`, `VmHWM`.
- [Linux proc_pid_smaps(5)](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): RSS/PSS and private/shared mappings.
- [Linux cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory): `memory.current`, `memory.max`, `memory.stat`, `memory.events`.

**Takeaway:** **Used** is the amount recorded as used by the JVM in **one area**; **committed** is the amount that area has committed as usable; **reserved** usually refers to **pre-reserved virtual addresses**, not resident RAM. **RSS/VSZ/PSS** are **process/OS** views, while **cgroup memory** is a **resource-group** view. Only compare them once **scope, units, timing, and JVM/OS implementation** are aligned; do not use `-Xmx` or a single heap metric to represent total process memory.
