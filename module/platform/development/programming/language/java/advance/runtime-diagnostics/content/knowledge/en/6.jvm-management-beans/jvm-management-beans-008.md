# 6.8 BufferPoolMXBean and ClassLoadingMXBean for off-heap buffers or loaded classes

In JVM diagnostics, looking at **heap used** alone is rarely enough. A service may have a relatively stable Java heap while **process or container resident memory keeps climbing**; another service may show its total loaded classes growing steadily while currently loaded classes stay nearly constant. Two Java SE 21 management metric groups that help ask the right questions are **BufferPoolMXBean** and **ClassLoadingMXBean**.

- **BufferPoolMXBean** describes the NIO buffer pools exposed by the JVM, such as **direct** and **mapped**. It provides estimates of buffer count, total logical capacity, and memory currently used by the pool.
- **ClassLoadingMXBean** describes the JVM's class-loading subsystem: currently loaded classes, total classes loaded since process startup, total classes unloaded, and verbose class-loading state.

These are **supporting evidence**, not a measurement of all native memory, RSS, or Metaspace, nor an automatic leak-finding tool. This lesson focuses on the **standard Java SE 21 API** in the **java.management** module, using Java 21/HotSpot for illustration where needed; exact outputs can differ across JVMs, GCs, workloads, and operating systems.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Use **ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)** to enumerate the buffer pools actually present on the current JVM.
2. Read **getName()**, **getCount()**, **getTotalCapacity()**, and **getMemoryUsed()** accurately, including byte units, approximation semantics, and missing-data cases.
3. Use **ManagementFactory.getClassLoadingMXBean()** to read **getLoadedClassCount()**, **getTotalLoadedClassCount()**, and **getUnloadedClassCount()**.
4. Distinguish **snapshots**, **cumulative counters**, **deltas/rates**, and **gauges**, avoiding concluding a leak from a single capture.
5. Distinguish **direct buffers**, **mapped buffers**, Java heap, Metaspace, memory mappings, native allocations, and RSS/container memory.
6. Read MXBeans via the Java API or **platform JMX MBeanServer**, using the right ObjectNames and attributes.
7. Design low-impact sampling and correlate with GC, classloaders, NMT, file mappings, and load changes.
8. Know when these metrics are meaningful and when additional evidence is needed to conclude **direct-memory retention** or **classloader retention**.

## 2. What is an MXBean and why do we need these two?

An **MXBean** is a JMX management bean using data types representable as JMX open types so management tools can access them easily. Platform MXBeans are registered in the JVM's own **platform MBeanServer** and can be read **directly in code**, or through an **MBeanServerConnection** when an appropriate JMX connection exists.

For this topic, both standard APIs live in the **java.lang.management** package:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
~~~

This is solely an **illustrative import snippet**, not a standalone Java program. Two ways to retrieve the beans:

~~~java
var pools = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
var loading = ManagementFactory.getClassLoadingMXBean();
~~~

This is likewise an **illustrative API snippet**, placed into a complete runnable program in the practice section. In Java SE 21:

- A JVM may have **one or more BufferPoolMXBeans**, depending on the implementation and exposed pools; do not assume there must be exactly two pools.
- A JVM has **one ClassLoadingMXBean** for process-level class-loading info.
- Both beans **read the state of the JVM executing the code**; they do not by default read any other Java process on the host.
- Remote JMX requires an authenticated/authorized connection and proper security policy. Never expose an unprotected JMX port on a public network just to view metrics.

### 2.1. Why does container memory keep growing when heap is stable?

**-Xmx** and **MemoryMXBean.getHeapMemoryUsage()** primarily describe the Java heap. Outside the heap there can also be:

- Memory of **direct ByteBuffers** used by NIO for I/O.
- **Memory-mapped regions** backed by files via **FileChannel.map**.
- **Metaspace/class metadata** for classes and classloaders.
- **Thread stacks**, GC/JIT/runtime native memory, code cache, and internal structures.
- Memory allocated via **JNI**, native libraries, third-party allocators, shared memory regions, page cache, and OS/container accounting factors.

**BufferPoolMXBean observes only a subset of these.** If the direct pool does not grow, you cannot conclude there is no native-memory leak. If loaded class count climbs, you likewise cannot assume Metaspace grows byte-for-byte in lockstep or that a classloader is leaking.

## 3. BufferPoolMXBean: metric definitions

The **java.lang.management.BufferPoolMXBean** API has these key methods:

| Method | Return type | Meaning per Java SE 21 |
| --- | --- | --- |
| **getName()** | String | Name of the buffer pool, e.g. **direct** or **mapped** on common HotSpot builds. |
| **getCount()** | long | **Estimate** of the number of buffers in the pool, not cumulative allocations since JVM startup. |
| **getTotalCapacity()** | long | **Estimate** of the total capacity of buffers in the pool, in **bytes**. |
| **getMemoryUsed()** | long | **Estimate** of memory the JVM uses for the pool, in **bytes**, or **-1L** if no estimate is available. |
| **getObjectName()** | ObjectName | MBean identity for access via JMX. |

**What the API guarantees:** values pertain to the **pool** exposed by the JVM; specifically **getMemoryUsed()** can be **-1**. **Do not assume getCount or getTotalCapacity is exact to every nanosecond**: the documentation explicitly calls them **estimates**.

**getMemoryUsed() can differ from getTotalCapacity().** The JVM or allocator may require extra overhead for address alignment, bookkeeping, and allocation strategy. Do not turn **memoryUsed == totalCapacity** into a production assertion. On dashboards, display **count**, **capacity bytes**, and **memoryUsed bytes** separately.

**Pool names are not a fixed list guaranteed by the standard.** The names **direct** and **mapped** are common on HotSpot, yet code should **enumerate the actual list** instead of hard-coding that only those two exist. Some implementations may expose additional specialized mapped groups.

### 3.1. Direct buffers: why are they outside the heap?

**ByteBuffer.allocateDirect(capacity)** creates a **direct byte buffer**. The Java **ByteBuffer** object and its metadata remain managed objects on the heap, while the buffer's backing storage typically resides in a memory region suited for native I/O, which may lie outside the Java heap. Java SE notes that direct buffers can carry higher allocation/deallocation costs and are used when I/O gains are measurable.

Conceptual example:

~~~java
java.nio.ByteBuffer buffer =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
~~~

This is an illustrative snippet, not a standalone program. **Capacity** here is **1,048,576 bytes**. The **direct** pool on HotSpot may reflect that allocation, yet you cannot assert **getMemoryUsed** will rise by exactly 1,048,576 bytes: there are also JVM internal buffers, alignment, and update/reclamation timing.

**Common mistake:** seeing **heap used = 400 MiB**, **direct memory = 800 MiB**, and concluding process RSS = 1,200 MiB. The process also has Metaspace, stacks, code cache, shared mappings, OS resources, etc.; the metrics reflect different layers, so adding them is **not an RSS formula**.

### 3.2. Mapped buffers: mapping capacity does not equal resident RAM

**FileChannel.map(...)** returns a **MappedByteBuffer** representing a file-mapped region. The logical capacity of the mapping can appear in the **mapped** pool.

A **1 GiB** mapping does not automatically make the process consume **1 GiB of resident RAM** immediately:

- A mapping describes an **address range** and access to file contents.
- Pages can be faulted in on demand and evicted/managed in the OS page cache.
- RSS, committed memory, file-backed pages, and mapping size are not the same metric.
- **getTotalCapacity** of the mapped pool is an estimated total logical capacity, **not pages guaranteed resident**.
- Closing the **FileChannel** does not automatically invalidate the mapping; mapping lifetime is tied to the mapped buffer and JVM/OS reclamation mechanisms.

Therefore, use BufferPoolMXBean to identify **buffer/mapping count and scale**, then cross-check OS metrics when you need actual physical RAM usage.

### 3.3. What is not covered by these pools?

Do not assume coverage of **Unsafe/native malloc**, JNI allocations, C/C++ library mallocs, custom native allocators, thread stacks, native-created memory-mapped files, or kernel/container memory. A library may use direct ByteBuffers or may allocate native memory in ways **that bypass the pools tracked by this MXBean**.

Even if the **direct pool** rises steadily and plateaus, process RSS can still climb from other sources. **BufferPoolMXBean is one signal to correlate**, not a universal native memory profiler.

## 4. ClassLoadingMXBean: three counters for loaded classes

**ClassLoadingMXBean** provides:

| Method | Type | Metric kind | Meaning |
| --- | --- | --- | --- |
| **getLoadedClassCount()** | int | **Gauge** | Number of classes **currently** loaded by the JVM. Can increase or decrease. |
| **getTotalLoadedClassCount()** | long | **Cumulative counter** | Total classes **loaded since the JVM started running**. |
| **getUnloadedClassCount()** | long | **Cumulative counter** | Total classes **unloaded since the JVM started running**. |
| **isVerbose()** | boolean | State | Checks whether verbose class-loading output is enabled. |
| **setVerbose(boolean)** | void | Control | Enables/disables verbose class-loading output **JVM-wide**; can add overhead/log volume. |
| **getObjectName()** | ObjectName | JMX identity | MBean for process class loading. |

Usage:

~~~java
var bean = ManagementFactory.getClassLoadingMXBean();
long total = bean.getTotalLoadedClassCount();
int currentlyLoaded = bean.getLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

The snippet above only shows how to invoke them. **Cumulative counters** such as total/unloaded are typically analyzed via **the difference between two timestamps within the same JVM run**; never take totals from two different processes to compute a rate.

### 4.1. Currently loaded differs from total loaded

Suppose inside a JVM at time t1:

~~~text
loaded-now = 8,000
total-loaded-since-start = 10,000
unloaded-since-start = 2,000
~~~

After some interval, at t2:

~~~text
loaded-now = 8,300
total-loaded-since-start = 10,500
unloaded-since-start = 2,200
~~~

With these hypothetical numbers:

- **Δtotal-loaded = +500**: 500 additional class loads recorded.
- **Δunloaded = +200**: 200 additional unloads recorded.
- **Δloaded-now = +300**: currently loaded classes rose by 300.

If the window is **10 seconds**, the average class-loading rate from the counter is **500 / 10 = 50 classes/second**; unload rate is **20 classes/second**.

**Do not require all three numbers to satisfy an exact identity at every instant across separate method calls**, because the APIs are read sequentially while other JVM threads may still load/unload classes; this is **not a transactionally consistent snapshot**. In rounded data or JMX sampling, discrepancies can also come from timestamps, restart resets, or missed samples.

### 4.2. Class loading is neither classloader count nor Metaspace bytes

**The same binary class name can be loaded by multiple classloaders** and appear as distinct runtime classes. Counting classes **does not list which classloaders created them**, does not show which Java objects retain a classloader, and **does not give exact Metaspace bytes**.

Class unloading is tied to loader lifecycles and reachability/GC/VM conditions. You cannot infer that **dropping a reference to a `Class<?>`** guarantees immediate unloading. If **getUnloadedClassCount()** does not rise for a minute, it may simply be that unloading conditions aren't met, the workload is loading fresh classes, or the collector has not run an unloading cycle yet.

To diagnose a classloader leak, combine **class counts**, **Metaspace memory**, **classloader count/lifecycles**, **GC behavior**, and **heap dumps/classloader graphs** or appropriate HotSpot tools. MXBean metrics only help form hypotheses.

### 4.3. Should you call setVerbose(true)?

**isVerbose()** only reads state. **setVerbose(true)** enables class-loading logging at the **JVM-global** level, which can generate huge log volume. Java SE documentation notes that format and destination of verbose output **depend on the implementation**; concurrent calls from multiple threads mutate **the same global state**.

In JDK 21 HotSpot, when detailed diagnostics are needed, operators typically prefer Unified Logging such as **-Xlog:class+load=info** or **jcmd PID VM.log** when supported; do not treat that as a 1:1 synonym for standard **setVerbose** across every JVM. Before increasing logging, know the target file/stdout, permissions, duration, overhead, and rollback steps.

**Never put setVerbose(true) inside a dashboard polling loop.** It is a **system-mutating action**, not a getter. When accessing JMX remotely, grant write/mutate privileges only to responsible operators and restrict access.

## 5. Comparing metric types: avoid conflating names

| Metric | Scope | What must not be inferred |
| --- | --- | --- |
| **MemoryMXBean.heapMemoryUsage.used** | Java heap per JVM | Not process RSS or container usage. |
| **MemoryMXBean.nonHeapMemoryUsage.used** | Non-heap regions reported by MemoryMXBean | Not all native memory, nor automatically equal to direct+mapped. |
| **BufferPoolMXBean direct.memoryUsed** | JVM-reported estimate of direct pool memory | Does not cover all JNI/library/VM native allocations. |
| **BufferPoolMXBean mapped.totalCapacity** | Estimated total logical mapped capacity | Does not equal resident RAM or necessarily file bytes on disk. |
| **MemoryPoolMXBean (Metaspace)** | One JVM memory pool, commonly seen on HotSpot | Does not identify which exact classloader retains memory. |
| **ClassLoadingMXBean.loadedClassCount** | Currently loaded classes | Not classloader count, metadata bytes, or heap object count. |
| **ClassLoadingMXBean.totalLoadedClassCount** | Total classes loaded since startup | Rising alone does not prove a leak: it is a cumulative counter. |
| **ClassLoadingMXBean.unloadedClassCount** | Total classes unloaded since startup | Being 0 does not prove unloading is broken. |
| **Process RSS / container memory** | OS/cgroup view of process/group resources | Do not blame a single Java pool without cross-checking. |

Regarding units:

- Buffer count is a count, not bytes.
- Capacity/memoryUsed are reported in **bytes**.
- **1 MiB = 1,048,576 bytes**; divide by **1024 × 1024** when displaying MiB and label the unit clearly.
- Class count is **number of classes**, not memory size.
- When **memoryUsed = -1**, represent **unknown/unavailable**; **never plot it as -1 byte or 0 bytes**.

## 6. Runnable Java 21: reading snapshots of both MXBeans

The following program is **read-only** against the beans present in its own running JVM. It takes two snapshots separated by a time interval, prints discovered pools, and computes deltas for class-loading counters.

**File MxBeanSurvey.java**

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class MxBeanSurvey {
    record Classes(int now, long total, long unloaded) {}

    record Pool(String name, long count, long capacity, long used) {}

    record Snapshot(long tick, Classes classes, List<Pool> pools) {}

    private static Snapshot sample() {
        ClassLoadingMXBean loading =
                ManagementFactory.getClassLoadingMXBean();

        Classes c = new Classes(
                loading.getLoadedClassCount(),
                loading.getTotalLoadedClassCount(),
                loading.getUnloadedClassCount());

        List<Pool> pools = new ArrayList<>();
        for (BufferPoolMXBean bean
                : ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            pools.add(new Pool(
                    bean.getName(),
                    bean.getCount(),
                    bean.getTotalCapacity(),
                    bean.getMemoryUsed()));
        }
        pools.sort(Comparator.comparing(Pool::name));
        return new Snapshot(System.nanoTime(), c, pools);
    }

    private static String showBytes(long bytes) {
        return bytes < 0 ? "unavailable" : Long.toString(bytes);
    }

    private static void print(String label, Snapshot s) {
        System.out.printf(Locale.ROOT,
                "%s classes-now=%d classes-total=%d classes-unloaded=%d%n",
                label, s.classes.now,
                s.classes.total, s.classes.unloaded);
        for (Pool p : s.pools) {
            System.out.printf(Locale.ROOT,
                    "%s pool=%s count=%d capacityBytes=%d usedBytes=%s%n",
                    label, p.name, p.count, p.capacity,
                    showBytes(p.used));
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int seconds = args.length == 0
                ? 2 : Integer.parseInt(args[0]);
        if (seconds < 1 || seconds > 60) {
            throw new IllegalArgumentException(
                    "interval must be 1..60 seconds");
        }

        Snapshot first = sample();
        Thread.sleep(seconds * 1000L);
        Snapshot second = sample();

        System.out.println("pid=" + ProcessHandle.current().pid());
        print("first", first);
        print("second", second);

        double elapsed =
                (second.tick - first.tick) / 1_000_000_000.0;
        System.out.printf(Locale.ROOT,
                "delta total=%d unloaded=%d current=%d elapsed=%.3fs%n",
                second.classes.total - first.classes.total,
                second.classes.unloaded - first.classes.unloaded,
                second.classes.now - first.classes.now,
                elapsed);
    }
}
~~~

Compile and run with **JDK 21**:

~~~bash
javac --release 21 MxBeanSurvey.java
java MxBeanSurvey 2
~~~

**The output has no fixed numbers**. The program always prints a **pid=...** line, followed by class counts at both snapshots and one line for **each pool exposed by the JVM** per snapshot, ending with **delta total=... unloaded=... current=... elapsed=...s** on normal completion. Pool names, pool ordering (sorted by name), byte counts, PID, and deltas depend on VM/load.

**Reading the code properly:**

1. Uses **getPlatformMXBeans(...)** instead of assuming direct/mapped pool names always exist.
2. For **getMemoryUsed()**, negative values print as **unavailable** and are not used for MiB/rate calculations.
3. Getters are read sequentially; there is no 100% simultaneous snapshot guarantee across all counters.
4. **System.nanoTime()** is suitable for elapsed time within the process; exact read times of individual getters differ slightly from the final snapshot tick.
5. This is a **diagnostic demo program**, not a production collector. Production needs a proper metrics exporter, polling interval, storage, and error handling.
6. Launching a new process resets the **cumulative counters** of ClassLoadingMXBean; never merge deltas across processes or replicas.

**Note on jlink:** the **java.management** module must be present in the runtime image to use these APIs. An overly minimal image may lack the module/tools even if other Java apps run fine.

## 7. Runnable Java 21: observing direct and mapped buffers

The example below intentionally allocates **one 1 MiB direct ByteBuffer** and **one 4 KiB file mapping**, then prints the pools. It only illustrates where to find the metrics, **not a benchmark or leak-proving tool**.

**File DirectMappedDemo.java**

~~~java
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.Reference;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.List;

public final class DirectMappedDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile(
                "mxbean-mapping-", ".bin");
        file.toFile().deleteOnExit();

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            ByteBuffer seed = ByteBuffer.allocate(4096);
            while (seed.hasRemaining()) {
                channel.write(seed);
            }

            ByteBuffer direct =
                    ByteBuffer.allocateDirect(1024 * 1024);
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4096);
            direct.put(0, (byte) 42);
            mapped.put(0, (byte) 7);

            System.out.println(
                    "direct capacity=" + direct.capacity());
            System.out.println(
                    "mapped capacity=" + mapped.capacity());

            List<BufferPoolMXBean> pools =
                    ManagementFactory.getPlatformMXBeans(
                            BufferPoolMXBean.class);
            pools.stream()
                    .sorted(Comparator.comparing(
                            BufferPoolMXBean::getName))
                    .forEach(pool -> System.out.printf(
                            "pool=%s count=%d capacity=%d used=%d%n",
                            pool.getName(),
                            pool.getCount(),
                            pool.getTotalCapacity(),
                            pool.getMemoryUsed()));

            Reference.reachabilityFence(direct);
            Reference.reachabilityFence(mapped);
        }
    }
}
~~~

~~~bash
javac --release 21 DirectMappedDemo.java
java DirectMappedDemo
~~~

The first two lines on success have **exact** values:

~~~text
direct capacity=1048576
mapped capacity=4096
~~~

Lines starting with **pool=** have runtime-dependent values, including **used=-1** if the JVM has no estimate; there is no fixed stdout for pool counts. HotSpot typically has **direct** and **mapped** pools, though the API does not promise the list contains only those two names.

**Why does the code use Reference.reachabilityFence?** To keep the **direct/mapped buffers reachable** until after the observation block; without a later use, JIT and GC could alter when resources are reclaimed. This **does not turn the metrics into an atomic snapshot**; it merely avoids a common source of noise.

**Why not delete the file immediately after FileChannel.close?** The mapping can outlive channel closure; deleting a mapped file behaves differently across OSes, especially on Windows. The example uses **deleteOnExit()** for the process's temp file; if OS cleanup restricts deletion, clean up according to your test environment's temp-file policy.

**Do not allocate GiB-scale buffers just to observe in production.** 1 MiB / 4 KiB suffices to understand the API. Creating direct buffers consumes real native memory and can trigger OutOfMemoryError when exceeding JVM/OS limits.

## 8. Analyzing deltas, rates, and trends

A **single snapshot** only shows state at one point in time. To assess trends, you need **multiple samples** and the right metric type.

### 8.1. With ClassLoadingMXBean

Notation:

- **L(t)** = currently loaded classes (gauge).
- **T(t)** = total loaded classes since startup (counter).
- **U(t)** = total unloaded classes since startup (counter).

Within the same JVM run, over time window **Δt**:

~~~text
newly loaded    = T(t2) - T(t1)
newly unloaded  = U(t2) - U(t1)
net loaded      = L(t2) - L(t1)

load rate       = newly loaded / Δt
unload rate     = newly unloaded / Δt
~~~

Because getters are not captured atomically, small discrepancies across calculations from the same pass are not automatically bugs. When a process restarts, counters reset and a **new series** must start; if a delta is negative or instance/PID changes, never display it as an ordinary negative rate.

**Deterministic math example** with a 10-second window:

~~~text
T(t1) = 10000      T(t2) = 10400
U(t1) =  2000      U(t2) =  2080
L(t1) =  8000      L(t2) =  8320

newly loaded   = 400
newly unloaded = 80
net loaded     = 320
load rate      = 40 classes/s
unload rate    = 8 classes/s
~~~

A Java 21 exercise with **exact stdout** to verify the math, without reading a live system:

**File CounterMath.java**

~~~java
public final class CounterMath {
    public static void main(String[] args) {
        long totalBefore = 10000, totalAfter = 10400;
        long unloadedBefore = 2000, unloadedAfter = 2080;
        int liveBefore = 8000, liveAfter = 8320;
        long elapsedSeconds = 10;

        long loadedDelta = totalAfter - totalBefore;
        long unloadedDelta =
                unloadedAfter - unloadedBefore;
        int liveDelta = liveAfter - liveBefore;

        System.out.println("loadedDelta=" + loadedDelta);
        System.out.println("unloadedDelta=" + unloadedDelta);
        System.out.println("liveDelta=" + liveDelta);
        System.out.println(
                "loadRate=" + loadedDelta / elapsedSeconds + "/s");
        System.out.println(
                "unloadRate=" + unloadedDelta / elapsedSeconds + "/s");
    }
}
~~~

~~~bash
javac --release 21 CounterMath.java
java CounterMath
~~~

**Exact stdout:**

~~~text
loadedDelta=400
unloadedDelta=80
liveDelta=320
loadRate=40/s
unloadRate=8/s
~~~

**Do not misunderstand:** total loaded increasing steadily over time is normal behavior for a cumulative counter; what warrants investigation is an **abnormal load rate, persistently climbing loaded-now/Metaspace**, or failing to unload when a lifecycle clearly ended, combined with other evidence.

### 8.2. With BufferPoolMXBean

**count**, **capacity**, and **memoryUsed** are **point-in-time state estimates**, not counters of allocations since startup. Therefore:

~~~text
delta direct used (bytes) = direct.used(t2) - direct.used(t1)
delta direct count        = direct.count(t2) - direct.count(t1)
delta mapped capacity     = mapped.capacity(t2) - mapped.capacity(t1)
~~~

**Do not interpret delta count=+10 as meaning exactly 10 allocations occurred**: within that window thousands of buffers may have been allocated and nearly all freed; the pool only reflects buffers still in the statistics at sample time. **Do not compute deltas/rates when memoryUsed=-1**.

For direct NIO, track at least **direct.count**, **direct.totalCapacity**, and **direct.memoryUsed**. For mapped, track count/capacity/memoryUsed alongside OS mappings/RSS when needed. Use the **pool name** label as series identity; never collapse all pools into one and call it "JVM off-heap memory".

### 8.3. Sampling and natural variance

- Each sample is not strictly simultaneous across both beans; under bursty workloads, slight "mismatches" are expected.
- Sampling too sparsely can miss allocation/release bursts, classloading spikes, or unloads happening between polls.
- Sampling too frequently increases exporter/JMX/serialization overhead across many instances; tune interval to sensitivity and cost.
- Rate charts must use **actual elapsed seconds between samples**, not assuming exactly 5 seconds every time since schedulers can drift.
- Tag series with **JVM process identity**: container/Pod ID, namespaced PID, process start time, app version, JDK vendor, and GC.
- Separate **startup/warmup** from **steady-state**: high classloading in the first minute may be normal, whereas continuous loading on every request signals something to investigate.

## 9. Accessing via JMX: ObjectNames and attributes

Per Java SE 21, these MXBeans are registered on the **platform MBeanServer**.

| MXBean | ObjectName |
| --- | --- |
| **ClassLoadingMXBean** | **java.lang:type=ClassLoading** |
| **BufferPoolMXBean** | **java.nio:type=BufferPool,name=<pool name>** |

For ClassLoadingMXBean, JMX typically exposes attributes:

~~~text
LoadedClassCount
TotalLoadedClassCount
UnloadedClassCount
Verbose
~~~

For each buffer pool, attributes such as:

~~~text
Name
Count
TotalCapacity
MemoryUsed
~~~

**Do not hard-code an MBeanName by guessing.** To get the exact name registered by the JVM, call **bean.getObjectName()** in Java or query the **java.nio** domain of the platform MBeanServer. If a pool name contains special characters, ObjectName quoting/escaping may need proper JMX handling.

Example reading via MBeanServer **in-process**; this is an illustrative snippet (not a standalone Java file):

~~~java
var server = ManagementFactory.getPlatformMBeanServer();
var cls = ManagementFactory.getClassLoadingMXBean();
Object loadedNow = server.getAttribute(
        cls.getObjectName(), "LoadedClassCount");
~~~

This snippet uses **ManagementFactory** with imports as shown earlier, and **getAttribute** requires handling checked exceptions in real code. A management application can use **MBeanServerConnection** and proxies instead of the local server, with appropriate network/JMX permissions.

**JConsole/JMX** lets you inspect MBeans without writing a custom collector. When connecting remotely, **never open a public JMX port lacking authentication/TLS**. These interfaces expose infrastructure and JVM state; write access to attributes like **Verbose** can also alter system behavior.

## 10. Connecting to Metaspace, direct-memory limits, and OS metrics

### 10.1. Direct memory does not mean all non-heap memory

**-XX:MaxDirectMemorySize** is a HotSpot implementation flag limiting one class of direct buffer allocations. It is **not a universal cap on all native memory allocations** and does not prove all mapped pages, JNI native mallocs, or thread stacks appear in BufferPoolMXBean's direct metrics.

Suppose you see:

~~~text
heap used          = 600 MiB
direct pool used   = 400 MiB
mapped capacity    = 2,000 MiB
container memory   = 1,800 MiB
~~~

These four values **cannot be summed or compared with a single formula**: mapped capacity is a logical size; container memory uses cgroup accounting and may include page cache; heap used differs from reserved/committed heap; direct used may include overhead beyond capacity. Before declaring a memory limit violation, check what **memory.current/usage**, RSS, mapped pages, shared pages, and byte units are actually measuring.

### 10.2. Metaspace often moves with classloading, but not in a fixed ratio

On HotSpot, **Metaspace** stores class metadata in native memory. Retained classloaders can cause both currently loaded classes and Metaspace to grow together, yet metadata size varies per class, alongside code cache, loader data, layout, and other native allocations.

To understand the phenomenon, correlate:

- **ClassLoadingMXBean loaded-now**, load/unload rates.
- **MemoryPoolMXBean** for **Metaspace** and, when present, **Compressed Class Space**, reading pools by actual name.
- **JVM GC/unloading events** at corresponding timestamps.
- **HotSpot jcmd VM.classloader_stats** if supported by the JVM and authorized; it provides helpful classloader visibility, though it does not automatically pinpoint what holds references.
- **Heap dump or classloader graph** when object-retention analysis is truly needed; assess impact/size before dumping.

**Do not run GC.class_histogram or heap dumps repeatedly in production just to update a dashboard.** Such operations can be expensive or cause pauses and never substitute for lighter MXBean getters.

### 10.3. Native Memory Tracking helps, but has its own scope

On **HotSpot JDK 21**, **Native Memory Tracking (NMT)** helps observe internal VM memory. To use it in a process, you generally must enable **-XX:NativeMemoryTracking=summary** or **detail** at startup; documentation notes NMT has overhead and **cannot be enabled via jcmd if previously off**.

Example when NMT is enabled and PID/tools are verified:

~~~bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
~~~

**12345 is an illustrative PID**; commands depend on attach permissions on the target JVM. Nor is NMT a profiler for every native `malloc`: official documentation limits it to internal JVM/HotSpot memory, not fully covering third-party native library allocations or every JDK library.

Hence, when **RSS rises while BufferPoolMXBean stays flat**, NMT, library allocator metrics, mappings, and OS/container metrics are **complementary evidence**, never a reason to "ignore" the alert.

## 11. Case A: direct buffers growing in a long-running JVM

**Hypothetical symptom:** an application handles network I/O; heap stays steady near 500 MiB, while container memory grows. The dashboard shows:

| Timestamp | Direct count | Direct total capacity | Direct memory used | Heap used |
| --- | ---: | ---: | ---: | ---: |
| 10:00 | 800 | 150 MiB | 158 MiB | 500 MiB |
| 10:10 | 2,100 | 420 MiB | 435 MiB | 505 MiB |
| 10:20 | 4,500 | 860 MiB | 890 MiB | 498 MiB |

Data is **hypothetical**, strictly for analysis practice. The pattern suggests **direct buffers are growing in count, capacity, and memory used**, while heap stays flat. This supports a hypothesis of **direct buffer retention or rising live buffers from workload**, yet **does not by itself prove a leak**.

Workflow:

1. Check whether **request concurrency, load, connection pools, queue depth, or message sizes** grew proportionally. If load tripled, more direct buffers may be normal pooling behavior.
2. Separate **warmup** from steady-state, checking intervals when traffic returns to baseline. If count/capacity keep climbing across multiple steady cycles, investigate deeper.
3. Inspect **collector/reclamation behavior** and lifetimes of ByteBuffer wrappers; never invoke **System.gc()** as a default leak fix.
4. Check **Netty/JNI/native allocator metrics** if libraries manage their own buffers; do not assume all of them are tracked by BufferPoolMXBean.
5. Correlate **RSS/cgroup memory**, file mappings, NMT (if enabled), Java version, **MaxDirectMemorySize** limit, and OOM traces.
6. Only with evidence choose a fix: close resources on the right lifecycle, bound pooling, adjust ownership/release logic, tune concurrency, or fix code.

**Distinguish two states:** pool count may stay high because **a buffer pool is designed to retain buffers for reuse** while memory plateaus; that is not necessarily a leak. Conversely, the **MaxDirectMemorySize** limit can cause allocation failures before the process hits the container limit. Inspect the exact error type.

## 12. Case B: loaded classes climb after every redeploy inside the same JVM

**Hypothetical symptom:** an app server or plugin framework unloads/reloads modules without **restarting the JVM**. Every 10 minutes:

| Checkpoint | loaded-now | total-loaded | unloaded | Metaspace used |
| --- | ---: | ---: | ---: | ---: |
| A | 9,000 | 12,000 | 3,000 | 180 MiB |
| B | 10,500 | 14,000 | 3,500 | 225 MiB |
| C | 12,200 | 16,200 | 4,000 | 275 MiB |

Numbers are **hypothetical**. Even though **unloaded** keeps rising, **loaded-now** and **Metaspace** keep climbing. This **suggests** live classes/classloaders are accumulating across cycles, though it could also reflect new modules or intentionally designed caches.

Checks needed:

- How many **ClassLoader instances** and classes does each reload create, and are loaders closed properly?
- Are **thread context class loaders**, plugin threads, static registries, shutdown hooks, ThreadLocals, scheduled tasks, logger handlers, or external registries retaining references to old loaders?
- Has **GC/unloading** run, does the collector support unloading classes under those conditions, and should loaded-now realistically drop right after reload?
- What do **VM.classloader_stats**, Metaspace metrics, and heap dump/classloader graph/JFR (when authorized and impact-safe) show holding the loader?

**Do not conclude from rising total-loaded.** That counter **must increase** whenever the JVM loads new classes; even a completely healthy JVM can see total-loaded grow unboundedly over time if it continuously creates and unloads classes. A stronger signal is **retained current count and Metaspace across comparable cycles**, controlling for workload and GC.

## 13. Case C: large mapped capacity without corresponding RSS growth

An application using **FileChannel.map** on large files can have **mapped.totalCapacity = 8 GiB** while RSS stays much lower. Do not immediately raise an incident claiming "8 GiB of RAM is held".

Proper analysis:

1. **Mapped capacity** mainly reflects logical mapping size, not resident pages.
2. Pool memoryUsed is an **estimate** and still provides neither a page map nor exact file bytes resident in RAM.
3. **RSS** counts memory pages present in physical memory per the OS at sample time; **shared/file-backed pages** follow OS- and tool-specific accounting rules.
4. If the application reads continuously, page cache can grow and affect cgroup usage; nor does mapped buffer count equal file descriptor count.
5. When mapped count/capacity does not drop after closing the channel, remember **the mapping lives until the mapped buffer is reclaimed**; check references and GC/lifecycle, not just file handles.

If the goal is to identify specific mapped files, inspect OS process mappings/procfs and appropriate application metadata. **BufferPoolMXBean contains neither file paths nor individual ByteBuffer instances**.

## 14. Production monitoring implementation

### 14.1. Suggested metric names and labels

An exporter reading these MXBeans might expose:

~~~text
jvm_buffer_pool_count{pool="direct"}
jvm_buffer_pool_capacity_bytes{pool="direct"}
jvm_buffer_pool_used_bytes{pool="direct"}

jvm_buffer_pool_count{pool="mapped"}
jvm_buffer_pool_capacity_bytes{pool="mapped"}
jvm_buffer_pool_used_bytes{pool="mapped"}

jvm_classes_loaded_current
jvm_classes_loaded_total
jvm_classes_unloaded_total
~~~

**These are illustrative metric names proposed by this lesson**, not guaranteed to match the exact names of any specific Micrometer/Prometheus/JMX exporter. With a real exporter, check naming conventions, versions, units, and unsupported handling.

- **Buffer pools** need a **pool** label from **getName()** instead of a hard-coded list.
- **Class counters** are process-wide; attach **instance/JVM identity**; in Prometheus, compute per-process rates and handle resets.
- Never put **class name** or **buffer instance** in labels; these MXBeans do not provide them and high cardinality overwhelms monitoring storage.
- When a pool has **getMemoryUsed = -1**, consider **omitting the used series** or exporting an unavailable status per convention. Never plot -1 as a real memory value.
- Use **bytes** consistently; never attach a `_mb` suffix while exporting bytes.

### 14.2. What thresholds should trigger alerts?

No single threshold for **direct count**, **mapped capacity**, or **loaded-now** fits every application. Alerts should combine:

- Sustained growth across multiple comparable windows, not a single spike.
- Actual container/host memory capacity and OS headroom.
- **Load, concurrency, throughput**, GC mode, pool warmup, and framework retention policies.
- Accompanying symptoms: **OutOfMemoryError direct buffer memory**, Metaspace OOM, RSS growth, classloader count growth.
- Scaling/deployment plans and risk tolerance.

If a target JVM runs for only a few minutes before restarting, total-loaded counters can jump rapidly on each startup; metrics must **reset cleanly and stay isolated per process lifecycle**. Never sum loaded-now across all replicas and treat it as memory or unique system classes.

### 14.3. Limits when sampling via remote JMX

Remote JMX carries serialization/network cost and security controls. If one collector polls thousands of JVMs at tiny intervals, polling itself can generate load. Start with a sensible cadence for the incident class (e.g., every **5–30 seconds** depending on load), then evaluate cost vs. missed spikes.

There is no need to enable **verbose class logging** or capture heap dumps on every scrape. MXBean getters serve well as lightweight background monitoring, while tracing/profiling/heap dumps should be triggered only with a hypothesis and impact preparation.

## 15. Common mistakes and how to correct them

1. **"Pool `direct.memoryUsed` is total native memory."** No; it is only the JVM-published estimate for that pool.
2. **"Pool `mapped.capacity` of 8 GiB means 8 GiB of resident RAM."** No; logical mapping differs from resident pages.
3. **"Buffer count is allocations since startup."** No; it is an estimate of **buffers currently in the pool** at the snapshot.
4. **"`used` must always equal `totalCapacity`."** No; alignment/allocators can cause differences.
5. **"`MemoryUsed=-1` means negative memory or unused."** No; it means no estimate is available.
6. **"A JVM always has exactly two pools: direct and mapped."** No; enumerate actual MBeans and check the implementation.
7. **"Stable heap usage means stable process memory."** No; direct, native, metaspace, and OS layers sit outside heap scope.
8. **"Rising `total-loaded` means a classloader leak."** No; it is a counter incremented on every class load.
9. **"Rising `loaded-now` means Metaspace grows in exact proportion."** No; per-class sizes and VM metadata vary.
10. **"`Unloaded` not rising for one minute means GC is broken."** No; unloading has specific conditions and timing.
11. **"`getLoadedClassCount == total-loaded - unloaded` on every sample."** Do not assert non-atomic snapshots, especially during concurrent class loading.
12. **"`setVerbose(true)` is just reading a metric."** Wrong; it mutates JVM-wide logging and adds overhead.
13. **"JMX ObjectName `direct` definitely exists on every JVM."** No; check `getPlatformMXBeans`/`getObjectName`.
14. **"Native Memory Tracking is on by default and tracks all JNI/native mallocs."** No; NMT must be enabled at startup and has its own scope.
15. **"Counters before and after a restart can be compared as one series."** Wrong; counters reset with the process lifecycle.
16. **"Direct buffers are freed immediately upon closing a FileChannel."** No; direct buffers/mappings have their own lifecycles.
17. **"Scraping more frequently always proves leaks better."** No; dense samples from mismatched phases or missing metadata still mislead.
18. **"Take a heap dump immediately whenever the direct pool grows."** Not yet; check load, lifecycle, metrics, and impact first.

## 16. MXBean diagnostic checklist

| Question | Required evidence |
| --- | --- |
| Measuring the right **JVM process**? | PID, JVM start time, container/Pod, JDK vendor and version. |
| Reading the right MXBeans? | `BufferPoolMXBean` list and singleton `ClassLoadingMXBean`; never guess ObjectNames. |
| What unit is each metric? | Count / bytes / cumulative count / gauge. |
| Any unsupported values? | Check `memoryUsed = -1`; never interpolate as 0. |
| Enough samples over time? | Timestamps, sampling interval, startup vs. steady-state. |
| Did counters reset on restart? | Process identity, uptime, deploy events. |
| Does direct pool growth match workload? | Request rate, concurrency, buffer pool design, load tests. |
| Is mapped capacity resident memory? | Cross-check OS mappings/RSS/page cache; never add directly. |
| Are currently loaded classes and Metaspace rising together? | `ClassLoadingMXBean`, `MemoryPoolMXBean`, GC/classloader evidence. |
| Justified to run heap dump/NMT/JFR? | Specific hypothesis, authorization, overhead, disk size, and rollback plan. |
| Do conclusions separate observations from hypotheses? | Corroborating evidence, competing explanations, and confidence level. |

## 17. Self-check questions and exercises

**Q1.** The direct pool shows **count=4,000**, **totalCapacity=300 MiB**, **memoryUsed=310 MiB**. Is this a metric bug?

**Answer:** Not necessarily. **memoryUsed** is an estimate of memory the JVM uses for the pool; it can differ from capacity due to alignment, allocator overhead, and implementation details. Record units clearly and track the trend.

**Q2.** Total loaded classes rose from **100,000 to 105,000** over a day, while loaded-now stayed near 15,000 and Metaspace barely changed. Can you conclude a classloader leak?

**Answer:** Not yet. Total loaded is a **cumulative counter** that grows whenever new classes load; stable loaded-now/Metaspace after GC cycles can fit normal operation. Check classloader lifecycles and unload rates if issues appear.

**Q3.** The mapped pool reports **12 GiB** capacity while process RSS is around **2 GiB**. Which number is wrong?

**Answer:** Likely neither. Mapped capacity measures logical mappings, while RSS measures resident physical memory; the two quantities cannot be compared directly.

**Q4.** No MBean is named **direct**, yet another pool is exposed by the VM. Should you throw a fatal error?

**Answer:** No. The API permits a JVM to expose one or more pools with implementation-provided names. Enforce specific pool names only when you know the exact target VM and configuration.

**Q5.** Should **memoryUsed = -1** be exported as **-1** on a bytes dashboard?

**Answer:** Do not treat -1 as real memory; represent it as unavailable/absent per convention. For alerting, separate missing-metric status from memory thresholds.

**Q6.** After load drops, direct count stays high yet flat; is it necessarily a leak?

**Answer:** Not yet. Buffer pools/frameworks may retain buffers for reuse. Compare the plateau, pool policy, workload, and memory headroom before calling it abnormal retention.

**Q7.** `ClassLoadingMXBean.isVerbose()` returns false. To inspect class loading, should a health endpoint call `setVerbose(true)`?

**Answer:** No. That is a **JVM-wide** mutation that can add logging overhead. Use time-bounded logging/diagnostics tools with proper authorization and rollback.

**Q8.** Why can **RSS rise while heap and the direct pool stay flat** still be a native-memory issue?

**Answer:** Because BufferPoolMXBean does not cover all native allocations. Check Metaspace, threads, code cache, OS mappings, startup-enabled NMT, and library/native code allocators.

**Q9.** A JMX collector samples at 10:00 and 10:01 from two different JVMs of the same service; can you subtract total-loaded to compute a rate?

**Answer:** No. Counters are **per process**; never subtract across two different processes/instances. Preserve process identity labels and compute rates within a continuous series.

**Q10.** Would running **jcmd PID GC.class_histogram** every second be better than MXBeans?

**Answer:** Unsuitable as a background collector. Histograms can carry high impact; poll MXBeans periodically and take histograms/dumps only when deep investigation is justified and prepared.

## Official references

- [Java SE 21 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): pool metrics, units, accuracy, and -1 value of memoryUsed.
- [Java SE 21 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): class-loading counters and verbose mode.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MXBeans, MBeanServer, and ObjectNames.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): direct buffers, `allocateDirect`, and native I/O characteristics.
- [Java SE 21 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html): mapping lifecycle, page/file behavior.
- [Java SE 21 — FileChannel.map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long)): mapping and lifetime conditions.
- [JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): scope, limits, and enabling at startup.
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic commands, impact, and attach requirements.
- [JDK 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): runtime options such as `MaxDirectMemorySize`, NMT, and class-loading logs.

**Practical takeaway:** read **BufferPoolMXBean** to track **buffer pools exposed by the JVM**, read **ClassLoadingMXBean** to track **loaded class state and load/unload cadence**, and place both on the same timeline with **heap, Metaspace, RSS/container memory, GC, and workload**. Draw leak conclusions only after ruling out cumulative counter behavior, normal pooling, GC delays, and differing measurement scopes.