# 11.1. Distinguishing heap, non-heap, process memory, and the `-Xmx` limit

A Java application can run with `-Xmx512m` and yet the operating system still reports the process using 800 MiB, 1 GiB, or more. That is **not automatically a memory leak**: `-Xmx` only limits one specific memory region within the JVM, while a Java process has many other regions. When investigating an incident, you must first determine **which region is being measured, with which tool, and by which metric**.

After this lesson, you should be able to distinguish the Java heap, non-heap according to JVM management APIs, native/off-heap memory, and total process memory; understand `used`, `committed`, `reserved`, `max`, and RSS; and choose the right measurement when the JVM throws `OutOfMemoryError` or the process is terminated by the OS/container.

## 1. Four commonly conflated concepts

| Concept | What it contains / represents | Directly limited by `-Xmx`? |
| --- | --- | --- |
| **Java heap** | Allocation region primarily for Java instances and arrays; GC manages object lifecycles | **Yes**: sets the maximum heap size per JVM configuration |
| **Non-heap per `MemoryMXBean`** | Memory pools reported by the JVM outside the heap, such as Metaspace and Code Cache on HotSpot | **No** |
| **Native/off-heap** | Thread stacks, internal JVM structures, memory allocated via native/JNI, backing storage of direct buffers, certain mappings… | **No**; each part has its own mechanism/limit |
| **Process memory at the OS/container level** | The view observed by the operating system: resident pages (RSS), virtual address space, memory charged to cgroups… | **No** |

Two points on terminology:

1. In informal usage, "non-heap" is sometimes used to mean *all memory not on the heap*. However, `MemoryMXBean.getNonHeapMemoryUsage()` is **not the sum of every native allocation in the process**. In HotSpot, thread stacks, direct buffers, and many native structures are not included in this MXBean's non-heap total.
2. Native/off-heap and "MXBean non-heap" overlap in meaning outside the heap, but **they are not two independent groups that can simply be added together**. Always state the exact metric and measurement source.

Conceptual diagram (not drawn to actual scale):

```text
java process (PID)
├── Java heap                             ← limited by -Xmx
│   └── Objects and arrays managed by JVM/GC
├── JVM non-heap memory pools             ← MemoryMXBean / MemoryPoolMXBean
│   ├── Metaspace, Compressed Class Space (JVM-dependent)
│   └── Code Cache (JIT machine code, JVM-dependent)
├── Other native regions
│   ├── Thread stacks, GC/JIT/JVM structures
│   ├── Direct buffers, native libraries, JNI
│   └── Memory mappings and other allocations
└── Pages/code/libraries mapped, shared, or charged to the process by the OS
    ↑ OS reports RSS/VSZ; containers also have their own memory accounting
```

## 2. Heap: object allocation region managed by GC

In the JVM model, the heap is the runtime storage region for objects and arrays. For example, when executing `new byte[1024]`, the array data is normally allocated on the heap; a local reference variable may reside in a stack frame or be optimized away by the JIT, but **that does not mean the object itself is considered to live on the stack**. The JIT compiler can eliminate certain allocations via escape analysis; therefore, you should not infer a one-to-one mapping from each `new` statement to physical bytes used.

The heap may consist of multiple generations/regions depending on the garbage collector. GC reclaims objects that are no longer needed according to reachability rules. The **heap used** figure may include objects that have already become garbage but have not yet been collected by GC. Therefore, a single high `used` snapshot is not enough to conclude a memory leak: you need to look at changes over time, after GC cycles, and in relation to load.

Common flags:

- `-Xms256m`: configures the initial heap size (on HotSpot, also the configured minimum heap size).
- `-Xmx1g`: configures the maximum heap size to about 1 GiB. This is **not** the memory ceiling of the process.
- `-XX:MaxRAMPercentage=...`: on supported HotSpot versions, lets the JVM calculate the maximum heap size as a percentage of the memory it detects; an explicitly specified `-Xmx` determines the maximum heap size instead of this default calculation.

For example, with `-Xms256m -Xmx1g`: the JVM may reserve virtual address space for the heap close to 1 GiB, commit only part of it initially, and use less than the committed amount. Specific behavior depends on the GC, JDK version, and platform. **Heap max ≠ heap committed ≠ heap used ≠ RSS.**

Errors commonly related to the heap include `java.lang.OutOfMemoryError: Java heap space` or GC working excessively because the live set is near the upper bound. Increasing `-Xmx` can relieve capacity pressure if the host has enough memory, but it will not fix an application holding unintended references.

## 3. What is non-heap according to JVM management APIs?

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` reports the aggregate of the non-heap memory pools exposed by the JVM via its management API. On HotSpot, you typically encounter:

| Region | Role | Things to keep in mind |
| --- | --- | --- |
| **Metaspace** | Metadata for loaded classes, methods, and related structures | Uses native memory; `-XX:MaxMetaspaceSize` can limit this portion |
| **Compressed Class Space** | Region for compressed class pointers when the corresponding feature is enabled | **Reserved** capacity can be much larger than **committed** capacity |
| **Code Cache** | Machine code compiled by JIT and some JVM-generated code | Has dedicated flags such as `-XX:ReservedCodeCacheSize` |

Pool names, pool counts, and how pools are partitioned are implementation details of the running JVM/GC/JDK; you should not hard-code a list and treat it as universal across all runtimes.

Further distinguish components that are **not fully covered by the MXBean non-heap total**:

- **Thread stack**: each platform thread needs its own stack region; `-Xss` relates to the stack size per thread, **not** a limit on total memory across all threads. Virtual threads have a different stack model; do not multiply the number of virtual threads directly by `-Xss`.
- **Direct `ByteBuffer`**: its backing data is typically allocated off-heap, even though the `ByteBuffer` object itself is a Java object. HotSpot provides the `-XX:MaxDirectMemorySize` option; other native overhead can still occur.
- **GC/JIT/JVM structures and native/JNI libraries**: have their own regions; some are tracked by Native Memory Tracking, while others are not.

Therefore, **heap used + non-heap used from MXBean is not total process memory**, nor can you accurately derive native memory simply by subtracting `RSS - heap used`.

## 4. Memory measurement numbers have different meanings

| Metric | Meaning | Where it is easily misunderstood |
| --- | --- | --- |
| `used` | Portion the JVM reports as currently in use in the measured region/pool | Not synonymous with live objects remaining after GC; not RSS |
| `committed` | Amount of memory committed for the region; for `MemoryUsage`, the JVM guarantees this portion can be used | Does not mean every byte is currently resident in physical RAM |
| `max` | Maximum limit for the pool/heap when determinable; `-1` means undefined | Not every pool has a max; non-heap max does not equal `-Xmx` |
| `reserved` | Virtual address space set aside, commonly seen in Native Memory Tracking (NMT) | A large reserved value does not mean that much RAM has been consumed |
| **RSS** (Resident Set Size) | Process pages currently resident in RAM as measured by the OS | Can include shared pages and differ from the JVM's `committed` figure |
| **VSZ/VIRT** | Virtual address space of the process | A large value alone does not prove a RAM shortage |
| **Container/cgroup memory** | Memory accounted by the kernel to the process group/container | Can include file cache and multiple processes; not the JVM's RSS alone |

In `java.lang.management.MemoryUsage`, when values are defined, we generally have `used <= committed <= max`. The `init` field represents the requested initial capacity. With NMT, the `reserved/committed` pair in each category are **JVM memory management metrics**, not a snapshot of OS RSS. You should also not arbitrarily sum nested categories or metrics coming from different sources.

A **hypothetical** illustrative example, not measurements from a real program:

| Region | Illustrative value |
| --- | ---: |
| Heap max per `-Xmx` | 1,024 MiB |
| Heap committed | 512 MiB |
| Heap used | 350 MiB |
| Non-heap MXBean used | 90 MiB |
| RSS reported by OS | 760 MiB |

These values do not contradict each other. You cannot compute `760 - 350 - 90 = 320 MiB` and claim that exactly 320 MiB is "direct buffers" or a "leak": there are also committed-but-unused heap, stacks, GC, native allocations, mappings, shared pages, and differences between measurement tools.

## 5. A Java 17+ program that measures heap and non-heap itself

Save the following snippet to a file named **`MemoryLayersDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public class MemoryLayersDemo {
    public static void main(String[] args) {
        MemoryMXBean bean = ManagementFactory.getMemoryMXBean();

        printUsage("Heap", bean.getHeapMemoryUsage());
        printUsage("Non-heap (MXBean)", bean.getNonHeapMemoryUsage());

        System.out.println("Runtime max heap: "
                + asMiB(Runtime.getRuntime().maxMemory()));

        System.out.println("Non-heap memory pools:");
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                System.out.printf(Locale.ROOT, "  %s: used=%s%n",
                        pool.getName(), asMiB(usage.getUsed()));
            }
        }
    }

    private static void printUsage(String label, MemoryUsage usage) {
        System.out.printf(Locale.ROOT,
                "%s: used=%s, committed=%s, max=%s%n",
                label,
                asMiB(usage.getUsed()),
                asMiB(usage.getCommitted()),
                asMiB(usage.getMax()));
    }

    private static String asMiB(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.1f MiB",
                bytes / 1048576.0);
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac MemoryLayersDemo.java
java -Xms128m -Xmx256m MemoryLayersDemo
```

The program prints lines `Heap: used=..., committed=..., max=...`, `Non-heap (MXBean): ...`, `Runtime max heap: ...`, and the list of non-heap pools. **The MiB values and pool names depend on the JDK, GC, OS, and measurement time**, so there is no fixed numeric stdout reliable to copy for every machine. In the illustrative configuration, `Runtime.maxMemory()` reflects the effective heap limit close to `-Xmx256m` (it may differ due to how the JVM lays out and rounds the heap).

The key takeaway from the example: `Runtime.getRuntime().maxMemory()` and `MemoryMXBean.getHeapMemoryUsage()` describe the **heap**; `getNonHeapMemoryUsage()` describes only the non-heap pools published by the JVM. No single line directly represents RSS or total container memory.

## 6. Observing a running JVM and cross-checking with the OS

While a Java program/service is still running, you can use the following JDK commands (replace `<PID>` with the actual process ID):

```bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
```

- `jcmd -l`: lists Java processes visible to the tool (not guaranteed to see every process across all containers/namespaces).
- `VM.flags`: views effective JVM flags; combine with startup arguments to verify `-Xmx`, `-Xms`, GC options, and inferred values. Do not guess configuration solely from deployment manifests.
- `GC.heap_info`: a snapshot of heap information whose output format depends on the collector and JDK. Combine with JMX/metrics/GC logs to observe trends.

For **HotSpot Native Memory Tracking (NMT)**, it must be enabled at JVM startup, for example:

```bash
java -Xms256m -Xmx512m -XX:NativeMemoryTracking=summary -jar my-service.jar
```

Once the service is running, take a summary or track changes:

```bash
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Run `summary.diff` after an observation period or workload interval. NMT displays categories such as `Java Heap`, `Class`, `Thread`, `Code`, and `GC` along with total `reserved` and `committed` tracked by HotSpot. It **does not cover all** allocations by external/JNI libraries and does not replace OS tools; NMT also carries overhead, so weigh the trade-off before enabling it in production. You cannot turn NMT on from an off state using `jcmd` in an already-running JVM.

On Linux, inspect the resident and virtual memory of the **exact PID**:

```bash
ps -o pid,rss,vsz,comm -p <PID>
cat /proc/<PID>/status
```

`rss` and `vsz` in `ps` are typically reported in KiB; check the tool documentation for your specific environment. For containers, cross-check memory metrics from the cgroup/orchestrator, and `memory.current` and `memory.max` on cgroup v2 systems where applicable. On Windows you can inspect Working Set/Commit in process monitoring tools; do not compare numbers with different definitions directly without standardizing how they are measured.

When suspecting the heap, GC logs can provide a time series of occupancy before/after GC, pauses, and collection cadence (for example, on HotSpot: `-Xlog:gc*`). Some attach tools require matching user permissions, namespace, and runtime support; if attaching is not possible, use available metrics/logging.

## 7. `-Xmx` and container memory limits: two different limit layers

Suppose a container has a memory limit of **1 GiB**, while the JVM is configured with `-Xmx900m`. Even if the heap only reaches 850 MiB, the process may still need additional Metaspace, code cache, stacks, direct buffers, GC structures, and native libraries. When total accounted memory exceeds the container limit, the kernel may kill the process due to OOM. In that case, you may sometimes only see exit code **137** or an `OOMKilled` event, **without necessarily seeing a Java `OutOfMemoryError` or a heap dump**.

Therefore, when planning a memory budget:

1. Obtain the **actual limit** of the host/cgroup and check which limit the JVM detects.
2. Estimate live heap and set `-Xmx` based on realistic workload, rather than allocating the entire limit to the heap.
3. Reserve capacity for Metaspace, Code Cache, GC, platform thread count/`-Xss`, direct buffers, JNI, and native libraries.
4. Leave headroom for traffic spikes and observation error; verify against RSS/cgroup and NMT when possible.
5. In modern HotSpot, container awareness and ratio-based heap sizing can affect defaults; if you set `-Xmx` explicitly, verify the final value via flags/metrics rather than guessing.

There is no single formula "RSS = `-Xmx` + non-heap" that applies to every application. Stack size, thread count, GC, mmap, page cache, direct allocations, and the operating environment make the gap vary significantly.

## 8. Symptom-based diagnosis

| Symptom | Hypotheses to check first | Evidence to collect |
| --- | --- | --- |
| Heap used rises across multiple load cycles, post-GC baseline gets higher and higher | Objects retained by references / unbounded cache growth; could also be load or warmed-up state | Heap trend, GC logs, heap dump/retained references |
| `OutOfMemoryError: Java heap space` | Heap is insufficient for retained objects or there is a leak | Effective `-Xmx`, heap occupancy, timely heap dump |
| Heap used is low while RSS/cgroup memory is high | Thread stacks, direct memory, Metaspace, GC/native/JNI, mappings, or OS accounting | RSS/cgroup trend, NMT, thread count, direct-buffer metrics |
| `OutOfMemoryError: Metaspace` | Metadata pressure or unreleased class loaders | Metaspace pool/NMT `Class`, class/class loader count, Metaspace configuration |
| Direct buffer allocation failure | Direct memory reached its limit or native memory is tight | BufferPoolMXBean `direct`, direct allocations, direct limit config, and OS |
| `unable to create native thread` | Insufficient resources for threads, stacks, or hitting OS/cgroup limits | Thread count, `-Xss`, ulimit/PID limits, OS memory |
| Container `OOMKilled` without the JVM reporting Java OOME | Cgroup hit its memory limit before the JVM threw an error | Orchestrator events, cgroup memory, RSS, and heap/native config |

**Practical workflow:** verify PID/runtime/flags → record heap used/committed/max over time → cross-check non-heap pools and thread/direct-buffer metrics → read NMT (if enabled) → compare with RSS/cgroup at matching timestamps → only then conclude the root cause. A single snapshot is usually insufficient to distinguish normal growth from a leak.

### Three scenarios to test your understanding

**Scenario A.** `-Xmx512m`, heap used 220 MiB, RSS 700 MiB. Is `-Xmx` being violated? **No.** RSS measures regions outside the heap as well. What you need to do is find which component is consuming memory; do not infer a leak from this difference.

**Scenario B.** `-Xmx1g`, NMT `Java Heap reserved` is nearly 1 GiB while `committed` is only 300 MiB. Has 1 GiB of physical RAM been consumed? **You cannot conclude that.** Reserved is pre-allocated virtual address space; compare committed and actual resident memory.

**Scenario C.** A service in a 1 GiB container has `-Xmx900m`; GC logs do not report `Java heap space`, yet the Pod is `OOMKilled`. Should you increase `-Xmx`? **Not as a knee-jerk reaction.** Check cgroup usage and total off-heap overhead; increasing max heap may worsen the container's OOM risk.

## 9. Common misconceptions to avoid

- "`-Xmx` is the maximum total RAM Java is allowed to use" → false; it only limits the **heap**.
- "Heap used equals heap committed" → false; the JVM may commit capacity not yet used by objects.
- "Heap used drops immediately when an object has no more references" → false; reclamation is decided by GC.
- "MXBean non-heap includes all native memory" → false; there are also stacks, direct buffers, JNI, and many other regions.
- "NMT committed must equal RSS" → false; tracking methods and page sets differ, and NMT also has untracked regions.
- "Large VSZ = memory leak" → false; reserved/mapped virtual address space can be larger than resident memory.
- "`OutOfMemoryError` and `OOMKilled` are the same event" → false; one is an error thrown by the JVM, and the other is an event from OS/cgroup memory management.

**Remember:** `-Xmx` is the *Java heap ceiling*; `MemoryMXBean` measures *the heap and a set of non-heap pools*; NMT observes *a subset of HotSpot's native memory management*; RSS/cgroup gives *the operating system's perspective*. Always place numbers alongside **metric name, scope, timestamp, and measurement source**.

## References

- Java SE 21 API — `MemoryMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Java SE 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Java SE 21 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
