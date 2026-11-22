# Using Native Memory Inspection Tools and Understanding the Limits of Native Memory Tracking

A Java application can consume significantly more memory than the **Java heap** visible in a heap dump or through GC metrics. For programs using JNI, JNA, the Foreign Function & Memory API (FFM), C/C++ libraries, drivers, codecs, or embedded databases, off-heap memory can also grow due to native allocations by the JVM itself and by external libraries. To diagnose this accurately, you must combine HotSpot's **Native Memory Tracking (NMT)**, operating system metrics, and, when needed, native allocation tracking tools.

A key point to remember from the start: **NMT is not a total memory meter for the Java process**. NMT tracks internal allocations of the HotSpot JVM; it does not automatically track `malloc`/`free` calls made by JNI libraries or third-party native libraries outside the JVM's allocation mechanisms. Therefore, seeing RSS increase while NMT remains relatively stable is not enough to conclude that the tool is faulty or that memory is not leaking.

## 1. Identify the Type of Memory Under Investigation

A Java process typically has multiple components:

| Component | Typical Usage Source | Appropriate Diagnostic Tool |
| --- | --- | --- |
| **Java heap** | Java objects, arrays, Java caches | GC metrics, heap histogram, heap dump, heap profiler |
| **Metaspace / class metadata** | Class and class loader information | NMT Class, class count, class unloading |
| **Thread stacks** | Platform thread stacks; native threads | NMT Thread, thread dump, OS tools |
| **Code cache / JIT / GC structures** | Compiled code, GC structures, compiler | NMT Code, GC, Compiler, depending on JDK version |
| **Native memory managed by HotSpot** | Arenas, malloc/mmap of HotSpot subsystems | NMT summary/detail |
| **JDK direct / off-heap memory** | DirectByteBuffer or off-heap allocation mechanisms used by the JDK | Direct buffer metrics/JMX, NMT if the allocation path is tracked, OS metrics |
| **External library native heap** | malloc/calloc/realloc, new/delete from JNI/JNA/FFM or C/C++ libraries | Native allocator profiler, Valgrind, AddressSanitizer/LeakSanitizer, OS tools |
| **Memory mappings / shared libraries** | File mappings, shared libraries, anonymous mappings | /proc, pmap, smaps, VMMap, vmmap |
| **Memory allocated to process/container** | Resident pages, page cache, cgroup accounting | RSS/PSS, cgroup memory.current and memory.stat |

This classification table is only a guide, not a one-to-one mapping between a metric and an allocation site. For example, a DirectByteBuffer holds its **wrapper object** on the Java heap while keeping its data off-heap; a native library can allocate and write to memory regions unknown to HotSpot. Mechanisms like FFM/JNA/JNI are ways of calling native code, and **do not by themselves guarantee visibility into all native memory**.

### Figures That Are Often Conflated

- **Reserved:** a range of **virtual address space** set aside for a region. A very large reserved region does not mean a corresponding amount of physical RAM is currently in use.
- **Committed:** the amount of memory committed by the system/JVM as usable under platform semantics; not strictly synonymous with the number of physical pages currently resident.
- **RSS (Resident Set Size):** the number of process pages currently in physical memory according to OS accounting; may include shared and file-backed pages. RSS does not equal the sum of all reserved or committed regions.
- **PSS (Proportional Set Size, Linux):** divides shared pages proportionally by the number of processes sharing them; useful when multiple processes share libraries or mappings.
- **VIRT/VSZ:** total virtual address space, typically very large for a 64-bit JVM; an increase in VIRT alone is not enough to confirm a leak.
- **Container memory:** memory accounted by cgroup, which may include page cache and multiple processes; do not directly take a single RSS value as representing total container usage.

**Do not use the calculation `RSS − NMT committed` to deduce the exact amount of leaked JNI memory.** These quantities differ in collection scope and accounting methodology. The most useful comparison is **trends at the same point in time** and their relationship with workload, GC, thread count, handle count, and library `malloc` calls.

## 2. What Does Native Memory Tracking (NMT) Actually Measure?

NMT is a diagnostic feature of the **HotSpot VM**. When enabled at JVM startup, NMT records allocations instrumented by HotSpot under categories such as Java Heap, Class, Thread, Code, GC, Compiler, Internal, Other, Symbol, and Native Memory Tracking. Names, categorization, and statistical details may vary across JDK releases.

There are two common levels:

| NMT Level | Information Obtained | When to Use |
| --- | --- | --- |
| **summary** | Total reserved/committed and metrics by subsystem category | Initial investigation and comparison over time with lower overhead than detail |
| **detail** | Summary information plus native regions/call sites tracked by HotSpot | Isolating a HotSpot category growing abnormally; needed for deep investigation |

NMT is **disabled by default** on many HotSpot builds; it must be enabled via a JVM flag at startup:

~~~bash
# Summary level:
java -XX:NativeMemoryTracking=summary -jar app.jar

# Or detail level:
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

If a process was started with NMT disabled, **`jcmd` cannot enable or restart NMT for that process**. You need to plan a restart with the appropriate flag, or switch to OS metrics/native profilers in the meantime.

NMT has execution and memory overhead; Oracle documentation describes overhead of approximately **5–10%** in some configurations. NMT also uses memory to track itself and has a statistical category dedicated to itself. Do not enable `detail` by default on every production JVM without evaluating the impact.

### Important Observation Boundaries

1. **NMT does not cover native allocations outside HotSpot**, such as direct `malloc`/`new` in C/C++ libraries called via JNI. A native profiler or OS tools are required.
2. **NMT does not tell you which Java object holds references causing a Java heap leak.** The Java Heap line in NMT reflects reserved/committed; to find the object graph, use a heap dump/histogram.
3. **NMT detail is not a Java call stack profiler**, nor does it automatically know which Java method called C code from an external library. NMT call sites are primarily allocation sites inside HotSpot.
4. Certain native/JDK regions, special mappings, and Class Data Sharing have incomplete statistical coverage; do not treat NMT as an absolute accounting total for the process.
5. **Live `malloc` allocations** differ from **freed `malloc` allocations where the allocator still retains arenas/pages**. RSS not dropping immediately after `free` does not by itself prove a leak.
6. NMT does not automatically detect use-after-free, buffer overflow, or double free; AddressSanitizer/Valgrind and ownership checks are more suitable for those bugs.

These limitations are especially important when the same process contains both HotSpot and multiple native libraries maintained by different vendors.

## 3. NMT Commands and How to Read Them Properly

Use the **jcmd** tool from a compatible JDK with permission to attach to the target JVM. In practice, it usually must run on the same host and as the same effective user as the Java process. In containers, PID namespaces, system permissions, or missing JDK tools in the image can prevent `jcmd` from attaching.

### Identifying the JVM and Taking a Snapshot

~~~bash
# List JVMs visible in the current namespace:
jcmd -l

# If unsure which commands the JVM supports:
jcmd <PID> help VM.native_memory

# View summary NMT metrics:
jcmd <PID> VM.native_memory summary scale=MB

# For a process started with NMT detail:
jcmd <PID> VM.native_memory detail scale=KB
~~~

Here **`<PID>` must be replaced with the actual PID**. The lines above are example commands; do not run them verbatim with angle brackets.

### Comparing Against a Baseline

To measure the impact of a workload, start up, wait for warm-up/JIT/class loading to largely stabilize, and then set a baseline:

~~~bash
jcmd <PID> VM.native_memory baseline
~~~

After running a defined amount of work:

~~~bash
jcmd <PID> VM.native_memory summary.diff scale=KB
~~~

If the process was started with `detail`:

~~~bash
jcmd <PID> VM.native_memory detail.diff scale=KB
~~~

**summary.diff** and **detail.diff** show changes **relative to the most recent baseline**, not an instantaneous allocation rate. After each phase you want to compare independently, set a new baseline and record the timestamp. If the workload has just started, cache and JIT growth is normal; you must observe over multiple cycles before concluding there is an unbounded upward trend.

### Reading Each Category in the Report

Several categories typically warrant attention:

- **Java Heap:** reserved/committed heap region; does not indicate the number of live objects. GC may retain committed capacity even after reclaiming objects.
- **Class:** class metadata, metaspace, class space; growth alongside class/classloader count may be legitimate or related to classloader retention.
- **Thread:** thread structures and stack parameters tracked by HotSpot; uncontrolled growth in platform threads can increase memory and OS resources.
- **Code:** code cache and JIT-compiled code; typically grows during warm-up.
- **GC:** native structures serving GC; depends on collector, heap layout, and workload.
- **Internal / Other:** aggregate categories; **do not treat Other as equal to all external JNI library memory**.
- **Native Memory Tracking:** overhead from the tracking system itself.

NMT can show a structure roughly like:

~~~text
Native Memory Tracking:
Total: reserved=...KB, committed=...KB
- Java Heap (reserved=...KB, committed=...KB)
- Class     (reserved=...KB, committed=...KB)
- Thread    (reserved=...KB, committed=...KB)
- Code      (reserved=...KB, committed=...KB)
- GC        (reserved=...KB, committed=...KB)
- Other     (reserved=...KB, committed=...KB)
~~~

This is an **illustrative shape**, not actual output or an exhaustive list; many JDK versions also include additional categories and subcomponents such as `malloc`, `mmap`, and `arena`. Values vary by JDK, flags, GC, OS, and capture time. In diff mode, change values may carry a plus or minus sign.

**Reserved grows sharply while committed remains nearly unchanged**: address space may simply be reserved, which is not yet evidence of corresponding RAM consumption.

**Committed grows in Thread/Class/GC**: there is grounds to investigate the corresponding subsystem, but you must cross-check thread/class counts, lifecycle, and workload. Do not label it a “memory leak” based on a single snapshot.

**RSS grows while NMT stays nearly flat**: pivot to examining OS mapping regions, external library memory, direct/mapped buffers, page residency, allocator fragmentation, or parts outside NMT's scope.

## 4. Measuring Process Memory with OS Tools

NMT answers: **Which regions has HotSpot recorded?** OS tools answer: **Which address/mapping/resident regions does the process currently have?** You must capture both sets of metrics around the same time, under the same workload.

### Linux

~~~bash
# Process RSS/VSZ memory (RSS and VSZ units are typically KiB):
ps -p <PID> -o pid,rss,vsz,etime,args

# Process memory status and metrics:
cat /proc/<PID>/status

# Mapping summary; only available when kernel/permissions allow:
cat /proc/<PID>/smaps_rollup

# Detailed mapping regions:
cat /proc/<PID>/smaps

# Mapping table overview (if the pmap utility is available):
pmap -x <PID>
~~~

In `/proc/<PID>/status`, pay attention to `VmRSS`, `VmSize`, `VmHWM`, and `Threads`. In `smaps_rollup` or `smaps`, pay attention to `Rss`, `Pss`, `Private_Clean`/`Private_Dirty`, `Anonymous`, and file-backed regions. To distinguish anonymous native heap, stacks, shared libraries, and file mappings, use the mapping table together with `smaps` data; mapped paths and region permissions alone are not enough to know exactly “which function called `malloc`”.

**Container/cgroup v2:** add metrics from the cgroup **matching the target process**:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

These paths are the common case when the process resides directly in the mounted cgroup; actual paths may differ if mount configurations or cgroup namespaces differ. Container `memory.current` can include page cache and usage from other processes in the cgroup, so do not compare it 1:1 with a single JVM's RSS. If a process is OOMKilled without a Java `OutOfMemoryError`, check `memory.events`, container status, and native/RSS alongside heap metrics.

### Windows

Use **Process Explorer** to inspect private bytes, working set, image mappings, and thread count; use **VMMap** to analyze committed/reserved regions, private data, images, and mapped files. Supplement with Process counters in Performance Monitor if a time series is needed. Working Set is not synonymous with Private Bytes and must not be added directly to NMT committed.

### macOS

Use **Activity Monitor** to spot initial trends, **vmmap <PID>** to inspect memory regions and mappings, and **Instruments/Allocations or Leaks** when you need to trace native allocations. Some tools require appropriate permissions/entitlements. Do not treat OS-reported resident memory as the same quantity as NMT reserved.

### General Collection Rules

Record alongside the metrics: JDK/vendor version, JVM flags, native library build, PID, timestamp, request/operation count, heap used/committed, RSS/PSS, thread count, NMT categories, and cgroup limits. Compare samples at the same load and warm-up phase; repeat across multiple cycles to avoid drawing conclusions from a single measurement point affected by GC or OS reclaim fluctuations.

## 5. When to Use a Native Allocation Profiler?

If memory growth lies **outside NMT's scope**, you need a tool that records allocations and deallocations at the native level.

| Tool | Strengths | Caveats |
| --- | --- | --- |
| **Valgrind Memcheck** (Linux and supported environments) | Detects many out-of-bounds read/write bugs and leaks, provides native stack traces | Runs very slowly; an entire large JVM produces a lot of noise; best reduced to a native repro |
| **AddressSanitizer / LeakSanitizer** (ASan/LSan) | Detects buffer overflow, use-after-free, and corresponding leaks when built/instrumented appropriately | Requires building native code with instrumentation; injecting sanitizers into a JVM process may require extra configuration |
| **heaptrack** (Linux) | Tracks native allocations by call stack and memory usage over time | Collection overhead; may need symbols/debug info for useful call stacks |
| **jemalloc/tcmalloc profiling** | Analyzes allocations passing through the corresponding allocator | Only observes allocations actually routed through that allocator |
| **eBPF/perf/native tracing** (Linux) | Observes allocators/syscalls and per-process trends in supported environments | Requires kernel permissions, symbols, and accurate interpretation of allocation stacks |
| **VMMap, Instruments** | Inspects detailed memory region maps or native allocations on the respective OS | Detail level/data sources vary by tool |

No single profiler covers every mechanism. A library may use `malloc`, `mmap`, a custom allocator, or GPU/device memory; you must choose instrumentation based on the **actual allocation mechanism**. For example, hooking only `malloc` does not automatically observe all `mmap` calls. For native code you own, compiling with debug symbols and running sanitizers in an isolated test build usually gives a clearer signal than running Valgrind on an entire production JVM.

When analyzing leaks, distinguish between:

- **Definitely lost:** the program no longer has a path to the allocated region (if the tool can determine it).
- **Still reachable / retained cache:** memory still held by an allocator or cache; may be intentional.
- **Fragmentation:** the allocator struggles to return pages or reuse suitable blocks.
- **High-water mark:** the OS displays peak usage, not currently live memory.
- **Mmap/file cache:** can alter RSS/cgroup without appearing as live `malloc` allocations.
- **Unreleased handle/resource:** beyond byte regions, there are file descriptors, threads, sockets, and GPU allocations.

Ask “which allocations have not been freed after the business lifecycle?” rather than only asking “did RSS drop immediately after `free`?”.

## 6. Java 17 + JNI Hands-On: Seeing NMT's Blind Spot

This exercise creates two bursts of off-heap memory consumption in the same JVM:

1. **32 MiB DirectByteBuffer** via the JDK API, holding a reference so the region stays alive throughout the measurement phase.
2. **32 MiB `malloc`** directly from a C library called via JNI, then `free`.

We compare **NMT** and **RSS/PSS** at three points in time. The goal is to understand measurement scope; exact deltas depend on the JDK, libc, OS, how the system allocates pages, and concurrent JVM tasks.

### 6.1. Java File: NativeMemoryProbe.java

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public final class NativeMemoryProbe {
    private static final int MIB = 1024 * 1024;
    private static final BufferedReader IN = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));

    // Keep the reference alive across measurement points.
    private static volatile ByteBuffer direct;

    static {
        System.loadLibrary("nmtprobe");
    }

    private static native void nativeAllocate(int mebibytes);
    private static native void nativeFree();

    private static void pause(String stage) throws IOException {
        System.out.println(stage + " | PID=" + ProcessHandle.current().pid());
        System.out.println("Capture NMT/RSS in another terminal and press Enter.");
        if (IN.readLine() == null) {
            throw new IllegalStateException("Must be run in an interactive terminal");
        }
    }

    public static void main(String[] args) throws IOException {
        pause("P0: Buffer/native malloc not yet created");

        direct = ByteBuffer.allocateDirect(32 * MIB);
        // Touch each page to make the difference between allocation and resident pages clear.
        for (int i = 0; i < direct.capacity(); i += 4096) {
            direct.put(i, (byte) 1);
        }
        pause("P1: Created 32 MiB DirectByteBuffer");

        nativeAllocate(32);
        try {
            pause("P2: Allocated 32 MiB via malloc from JNI");
        } finally {
            nativeFree();
        }

        pause("P3: Freed JNI malloc; DirectByteBuffer is still alive");
        direct = null; // Does not guarantee that direct memory is reclaimed immediately.
    }
}
~~~

The class uses Java 17, `ProcessHandle`, and `ByteBuffer` built into the JDK. The program intentionally waits for input so you can capture NMT/OS metrics between phases. We **do not output a fixed PID to stdout**, because the PID changes with each run.

### 6.2. C File: nativeprobe.c

~~~c
#include <jni.h>
#include <stdlib.h>
#include <string.h>

static unsigned char *native_block = NULL;

static void throw_java(JNIEnv *env, const char *type, const char *message) {
    jclass error = (*env)->FindClass(env, type);
    if (error != NULL) {
        (*env)->ThrowNew(env, error, message);
    }
}

JNIEXPORT void JNICALL
Java_NativeMemoryProbe_nativeAllocate(JNIEnv *env, jclass unused, jint mib) {
    (void) unused;

    if (mib <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException", "mib must be positive");
        return;
    }
    if (native_block != NULL) {
        throw_java(env, "java/lang/IllegalStateException", "already allocated");
        return;
    }

    size_t bytes = (size_t) mib * 1024u * 1024u;
    native_block = (unsigned char *) malloc(bytes);
    if (native_block == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError", "malloc failed");
        return;
    }

    // Actually write to each page via memset so the allocated region has resident pages.
    memset(native_block, 0x5a, bytes);
}

JNIEXPORT void JNICALL
Java_NativeMemoryProbe_nativeFree(JNIEnv *env, jclass unused) {
    (void) env;
    (void) unused;

    free(native_block);
    native_block = NULL;
}
~~~

In this demo, all native operations run sequentially from the main thread; the static variable `native_block` is **not a thread-safe design** for applications with multiple callers. For real systems, you must follow concurrency policies and the library's handle lifecycle, and avoid static global state without a clear owner.

### 6.3. Compiling on Linux with JDK and GCC

~~~bash
# JAVA_HOME points to the JDK 17+ directory.
javac -h . NativeMemoryProbe.java

gcc -O0 -g -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativeprobe.c -o libnmtprobe.so

# Run in an interactive terminal, keeping it open to press Enter between phases.
java -XX:NativeMemoryTracking=detail \
  -Djava.library.path=. NativeMemoryProbe
~~~

**`javac -h`** generates the JNI header from the exact method names; the C signatures above correspond to a class without a `package` declaration. On Windows/macOS, library names, linker flags, and OS-specific include directories differ; this example build command is intentionally specific to Linux. To apply it in another environment, compile the shared library using that platform's toolchain and JNI headers.

In a **second terminal**, substitute the PID printed by the program:

~~~bash
# At P0, capture OS metrics then set the NMT baseline:
ps -p <PID> -o pid,rss,vsz
jcmd <PID> VM.native_memory baseline

# At P1 and P2:
jcmd <PID> VM.native_memory summary.diff scale=KB
ps -p <PID> -o pid,rss,vsz
cat /proc/<PID>/smaps_rollup

# When you need to view HotSpot call sites (since the JVM was started with detail):
jcmd <PID> VM.native_memory detail.diff scale=KB
~~~

After P1, you can record a snapshot and **set a new baseline right at P1** to isolate the P1 → P2 change; clearly record timestamps in your logs to avoid mixing up checkpoints. At P3, capture again once `malloc` has been freed.

### 6.4. Predicting and Explaining the Results

| Phase | Action | What to Check |
| --- | --- | --- |
| **P0** | No buffer created yet in demo | Used as baseline; the JVM still consumes startup memory |
| **P1** | `ByteBuffer.allocateDirect` 32 MiB, touch pages | RSS may increase; allocations going through JDK/HotSpot paths may appear in NMT, depending on implementation/version |
| **P2** | `malloc`/`memset` 32 MiB in the JNI library | RSS/anonymous resident typically increases; NMT **does not directly record the external library's `malloc` itself** |
| **P3** | `free` the JNI `malloc` | Live allocations decrease; RSS may drop or stay high because the allocator retains pages; DirectByteBuffer is still alive |

Seeing P2 cause a clear RSS increase without a corresponding increase in NMT is a classic illustration of **NMT's limitation**. However, concurrent HotSpot activities can still cause NMT to shift slightly. Do not force numbers to equal exactly 32 MiB, do not assume the NMT label is necessarily `Other` on every JVM, and do not conclude a “leak” from a `malloc` that **is properly freed** as in this demo.

If you want to investigate an actual leak, replace it with a native module that has a clear lifecycle, run multiple business cycles in a loop, and compare **live allocated bytes** with snapshots/call stacks from a profiler. When writing a repro, avoid harming production systems by intentionally accumulating unbounded `malloc` allocations.

## 7. Investigation Workflow When RSS Keeps Growing Despite a Stable Java Heap

Here is an approach you can apply to Java applications that interface with native code:

**Step 1 — Verify symptoms and scope.** Record when growth starts, load, restarts, OOMKilled events, Java `OutOfMemoryError`, number of processes in the container, and OS limits. Distinguish “Java heap used growing” from “RSS/private bytes growing”; record both peak and current values.

**Step 2 — Collect synchronized measurements.** Capture heap used/committed and thread count, NMT summary or diff, RSS/PSS, and mapping regions; also record actual native handle counts and open/close counts if the adapter exposes metrics.

**Step 3 — Use NMT to isolate the HotSpot portion.** If there is clear growth in Class/Thread/Code/GC, inspect classloader/thread lifecycle/warm-up/GC accordingly. If no matching growth appears, treat **untracked native allocation** as a hypothesis to verify, not the sole conclusion.

**Step 4 — Inspect OS mappings and allocators.** On Linux, compare `smaps` and anonymous/private dirty regions, thread count, and mapped files; check whether the library allocates via `malloc` or `mmap`/a custom allocator. For containers, check cgroup limits and page cache separately.

**Step 5 — Isolate the native component with a controlled experiment.** Run the same workload with and without activating the suspected native feature; vary the number of handles or requests; check memory after the lifecycle completes and after enough time for the allocator to reuse memory. Do not directly compare results from two different traffic levels.

**Step 6 — Use a native profiler/sanitizer.** On a repro with a symbol/debug build, collect call stacks of live allocations; cross-check create/destroy, `malloc`/`free`, `new`/`delete`, and `mmap`/`munmap` code. For memory corruption, prefer ASan/Valgrind on an isolated native component; leaks are only one of many types of memory bugs.

**Step 7 — Fix ownership and prove regression is resolved.** Every native resource must have a creation point, an owner, a last-used point, and both normal and exception cleanup paths. Re-measure across multiple cycles at the same load; confirm live memory stops growing or reaches a steady state, and test concurrency/timeouts/shutdown.

### Interpretation Table for Common Scenarios

| Observation | Hypothesis to Check | Next Step |
| --- | --- | --- |
| NMT Thread increases and OS thread count increases | Creating too many platform/native threads or failing to shut down executors | Thread dump, pool configuration, thread lifecycle |
| NMT Class/Metaspace increases after every deploy/reload | ClassLoader retention or continuous class generation | Classloader/class count, heap roots, unloading |
| NMT Code/Compiler increases during warm-up | Normal JIT activity | Compare after warm-up and under steady load |
| NMT GC increases alongside heap/collector config changes | Legitimate growth in GC structures | Cross-check JVM flags/heap sizing and GC logs |
| RSS increases sharply while NMT is stable | JNI `malloc`, third-party library, `mmap`, or page residency/fragmentation | `smaps`, native profiler, handle allocation logs |
| NMT reserved is very large, committed is low | Address space reserved in advance | Compare committed, RSS/PSS; avoid treating reserved as actual RAM used |
| Native `free` was called but RSS does not drop immediately | Allocator retains arenas/fragmentation or OS has not reclaimed yet | Track outstanding allocations, reuse, and mappings |
| Heap histogram is stable but container is OOMKilled | Off-heap usage, page cache, sidecar/other processes, cgroup limits | `memory.stat`/events, per-process RSS/PSS |

A single snapshot right as the process is about to OOM is usually insufficient. A time series with clear workload and baseline data is worth far more than a disconnected table of numbers.

## 8. Limitations When Investigating Direct Buffers, FFM, and Mappings

**DirectByteBuffer:** a `byte[]` or Java object does not contain the full off-heap data capacity. A Java heap dump may show the wrapper/reference-retaining path, but that does not mean the full native buffer contents are saved in the dump. Monitor the direct buffer pool via `BufferPoolMXBean` or corresponding metrics for additional visibility; total buffer pool is also not “all native memory”.

**JNI:** a C library loaded into the same process can hold `malloc` pointers in global variables or native handles that the Java side no longer sees. If `nativeFree`/`nativeDestroy` is forgotten, the Java heap dump can look completely normal. NMT does not automatically inventory allocations made directly by that library.

**FFM:** `MemorySegment`/`Arena` instances have ownership and lifecycle rules. A memory region returned by an external library via a downcall must be managed according to the library's contract; observing NMT alone does not verify that `free` was called properly. FFM became a standard API starting in **JDK 22**; on JDK 17, do not use JDK 22 standard FFM syntax. If an example runs on Java 17, JNI as in the hands-on section is an available option.

**Memory-mapped files:** large mappings increase virtual address space; the number of resident pages depends on which pages have been touched and OS caching/reclaim. NMT is not a complete tool for distinguishing file-backed RSS, anonymous RSS, and cache. Use `smaps`/VMMap and inspect `unmap`/`close` logic along with file lifecycles.

**C/C++ allocators:** `malloc` can retain arenas after `free`. Some libraries use custom allocators and retain buffer pools for reuse. Concluding a leak requires evidence of **outstanding allocations or sustained growth across equivalent work cycles**, not merely the fact that RSS does not drop immediately.

## 9. Common Diagnostic Mistakes

1. **Reading `-Xmx` as the RAM limit for the entire process.** `-Xmx` primarily limits Java heap capacity; beyond the heap there are stacks, code cache, native heap, `mmap`, and other overhead.
2. **Seeing NMT not increase and dismissing the possibility of a JNI leak.** `malloc` in an external library is outside HotSpot's tracking scope.
3. **Treating reserved as physical memory.** Reserved can be virtual addresses without corresponding resident pages; read committed/RSS/PSS and trends.
4. **Taking an NMT diff before setting a baseline.** There is no valid comparison point; you must set a baseline after warm-up or the phase you want to investigate.
5. **Running `detail` on a process started only with `summary`.** The `detail` level must be enabled at JVM startup; `jcmd` cannot upgrade a tracking level that was not enabled.
6. **Assuming timeouts/restarts/finalizers will automatically free all native allocations.** Native libraries have their own allocation/deallocation contracts; they need owners, proper cleanup, and protection against use-after-free.
7. **Using a heap dump to trace native pointers not managed by Java.** A heap dump may show wrappers, but is insufficient to identify native allocation stacks.
8. **Forgetting to synchronize measurement timestamps.** RSS after GC and NMT before GC represent two different states; snapshots skewed relative to workload easily mislead.
9. **Running heavy tools on a production process without evaluating impact.** Sanitizers and Valgrind should generally run on a repro/test build; NMT also has overhead.
10. **Fixing by blindly shrinking the heap.** Reducing `-Xmx` may create headroom for native memory in a container, but it does not fix the underlying `malloc` leak/handle leak and can cause Java heap OOM.

## 10. Practical Checklist for Handling Native Memory Incidents

- [ ] Confirm HotSpot/JDK vendor and version, JVM flags, native library version, and OS platform.
- [ ] Distinguish **heap used**, **heap committed**, **NMT committed**, **RSS/PSS**, and **container memory**.
- [ ] Confirm NMT was enabled from startup and know whether it is `summary` or `detail`.
- [ ] Record a baseline and capture diffs after workload phases with clear timestamps.
- [ ] If NMT reports category growth, cross-check subsystems, thread/class counts, and GC/JIT warm-up.
- [ ] If RSS grows outside NMT, inspect mappings, the library's allocator, and native call stacks.
- [ ] Run an A/B test toggling the exact native feature or holding load constant to isolate the cause.
- [ ] Prove that native handles/buffers/mappings are freed on every execution path, including exceptions and shutdown.
- [ ] Re-test across multiple cycles and save evidence to compare against the fix.
- [ ] Do not claim “the leak is fixed” just because RSS dropped once; check outstanding allocations and steady-state trends.

### Official Technical Sources for Cross-Reference by JDK

- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): NMT scope, limitations regarding external native code, how to enable, and basic commands.
- [Oracle JDK 21 — Diagnostic Tools, Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): NMT report examples, baseline/diff, and category interpretation.
- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): exact syntax of `VM.native_memory` and diagnostic commands.

**Conclusion:** NMT is very useful for analyzing **memory managed by HotSpot**, especially when inspecting changes by subsystem and call site. However, diagnosing native interoperability must go one layer further: OS metrics to know which pages the process is occupying, and a native profiler/sanitizer to know **which blocks the C/C++ library allocated, retained, or freed**. Only by combining these sources of evidence with resource lifecycles and workloads can you determine the true cause of memory growth.
