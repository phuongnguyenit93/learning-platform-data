# 13.6 NMT Limitations: HotSpot Scope and Untracked Native Allocations

## 1. When RSS Climbs While NMT Stays Nearly Flat

Suppose a Java service's RSS grows from 700 MiB to 1,100 MiB over several hours. Yet `jcmd <PID> VM.native_memory summary.diff` shows NMT `Total committed` rose by only 15 MiB. Is the remaining 385 MiB guaranteed to be a "native leak"?

**Not yet.** Native Memory Tracking (**NMT**) is a **HotSpot VM** tool that tracks memory allocation paths managed by HotSpot. It is not a tracker for every `malloc` or `mmap` call or allocations made by C/C++ libraries loaded into the same process. Moreover, NMT `committed` and RSS are two differently defined quantities; you must not subtract them to get an exact leaked byte count.

You should be able to answer: what memory NMT sees; what falls outside its scope; how to interpret `reserved/committed`; how to reconcile with RSS/PSS and memory mappings; when native tools beyond `jcmd` are required; and how to prove a leak rather than guessing.

## 2. What Can and Cannot NMT Track?

NMT is a HotSpot-specific diagnostic feature, disabled by default and enabled at **JVM startup**. Two levels:

- `-XX:NativeMemoryTracking=summary`: reports figures by VM subsystem category, with `reserved` and `committed`.
- `-XX:NativeMemoryTracking=detail`: adds call sites and virtual memory regions for **allocations instrumented by NMT**. It does not capture every native allocation across the entire process.

Typical categories are `Java Heap`, `Class`/metaspace, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Symbol`, `Other`, and `Native Memory Tracking`. Category names, counts, and granularity depend on the JDK version. The presence of a category does not mean every Java- or standard-library-related allocation lands in it.

| Memory Source | NMT Observation Level | What Not to Infer |
| --- | --- | --- |
| Java heap reserved/committed by HotSpot | NMT shows the VM heap's `reserved` and `committed` regions | Not `heap used`, live objects, or a heap dump |
| HotSpot class metadata/metaspace, code cache, GC structures, part of threads/stacks, and VM runtime | Corresponding NMT categories appear when allocated through instrumented VM paths | Does not automatically include every byte allocated by Java libraries/OS |
| `malloc`/`mmap` via HotSpot internal allocators with NMT instrumentation | `summary` records totals; `detail` includes call-site/region info | Not equivalent to a process-wide libc `malloc` profiler |
| JNI/JNA/native plugins calling libc `malloc`, `calloc`, `realloc`, `mmap`, or custom allocators directly | **Outside HotSpot NMT's guaranteed tracking scope** | Cannot assume it will show up under `Other` |
| Native allocations in JDK class libraries, CDS archives, and very early startup | Oracle documentation notes **areas not fully covered** | Do not claim all JDK APIs are always counted or always missed |
| RSS/PSS/Working Set/cgroup memory | Must be obtained from OS/container | Cannot be read directly from NMT `Total committed` |

**Important:** `Other` is for *HotSpot-recognized allocations that do not fit a specialized VM category*, not a catch-all for JNI/third-party library memory. Nor can `detail` trace the stack of an allocation NMT never observed.

For `ByteBuffer.allocateDirect`, `Unsafe`, JDK native libraries, or the Foreign Function & Memory API, **do not decide "tracked/untracked" from the API name alone**: allocation paths can change across implementations/JDK builds. Some allocations go through the VM and are recorded by NMT, while others go straight into native libraries. The right approach is to verify on **the exact JVM and code path you run**.

### Operational Limitations

1. NMT is **off by default**. When a JVM starts with NMT off, `jcmd` cannot enable/restart NMT; you must restart the JVM with the appropriate flag.
2. `summary` cannot be upgraded to capture `detail` call sites via `jcmd` at runtime; `detail` must be chosen at startup.
3. NMT has a cost: Oracle documentation cites roughly **5–10%** performance overhead in some scenarios plus extra memory metadata; plan ahead when measuring production systems.
4. Coverage is incomplete for CDS archives, certain early-startup allocations, and native code outside HotSpot; category groupings can change across JDKs.
5. **NMT growth does not equal a leak.** The JVM can grow heap committed, code cache, metaspace, GC structures, or thread stacks with load and keep them for reuse.
6. **Flat NMT does not prove the process has no leak.** It only says the HotSpot-tracked portion NMT observes has not shown a corresponding increase.

## 3. Distinguishing Reserved, Committed, RSS, PSS, and Heap Used

| Quantity | What Does It Measure? | Inference Trap |
| --- | --- | --- |
| NMT `reserved` | **Virtual address space** range set aside for JVM-managed regions | Reserving 2 GiB does not mean using 2 GiB of RAM |
| NMT `committed` | Regions recorded by HotSpot/OS as committed/backed; includes NMT-tracked VM `malloc` | Does not equal actually resident pages, and certainly does not represent all native code |
| Linux RSS (`VmRSS`) | Actual resident memory pages attributed to the process, including shared mappings | Shared pages can appear in the RSS of multiple processes |
| PSS in `/proc/<PID>/smaps_rollup` | Resident memory divided proportionally among processes sharing the same pages | Differs from RSS and cannot replace ownership/allocation-stack tracing |
| `heap used` or live set | Volume of Java objects in use/retained after GC | Does not equal NMT `Java Heap committed` |
| cgroup v2 `memory.current` | Memory charged to the cgroup, which may include page cache, kernel memory, and multiple processes | Not the RSS of the Java PID alone |

For example, a JVM with `-Xms256m -Xmx2g` may **reserve** nearly 2 GiB of heap while initially **committing** only a fraction. NMT `Java Heap` represents the JVM-managed region, not individual Java objects. After GC, `heap used` can drop while `committed` stays high; that alone is not a leak.

A hypothetical table:

| Checkpoint | NMT `Total committed` | RSS |
| --- | ---: | ---: |
| `t0`, after warm-up | 520 MiB | 690 MiB |
| `t1`, after 20 minutes of comparable load | 530 MiB | 940 MiB |
| Delta | +10 MiB | +250 MiB |

Supported conclusion: "The RSS growth **is not explained by the NMT committed trend**; we need to inspect resident pages and memory accounted by native libraries/OS." Unsupported conclusion: "Confirmed a 240 MiB leak in JNI." `250 - 10` is not an exact untracked byte count, because reservation/commit, page residency, shared/file mappings, allocator caches, and load shifts affect the comparison.

## 4. Collecting NMT Data Methodically

### 4.1 Enabling at Startup

~~~bash
# Choose ONE level at startup:
java -XX:NativeMemoryTracking=summary -jar app.jar
# Or:
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

These two lines are **two mutually exclusive choices**, not run together on the same process. `detail` is finer-grained but can incur higher overhead. Record JDK vendor/build, PID, container quota, workload, and timestamps. Use a `jcmd` compatible with the JVM and an account with attach permissions.

### 4.2 Baseline After Warm-Up, Then Compare Deltas

~~~bash
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
# After reproducing the RSS growth phase:
jcmd <PID> VM.native_memory summary.diff scale=MB
~~~

If **started with detail**, you can also run:

~~~bash
jcmd <PID> VM.native_memory detail scale=MB
jcmd <PID> VM.native_memory detail.diff scale=MB
~~~

Replace `<PID>` with the actual PID. The baseline should be set **after JVM/app warm-up**, right before the interval under investigation. Compare across the same PID, workload, and JDK, capturing multiple checkpoints rather than one snapshot. `summary.diff`/`detail.diff` show changes **within the tracked HotSpot scope**, not every `malloc` in external libraries.

Read categories accurately:

- `Java Heap` committed grows: the JVM expanded the heap. To know what Java objects retain memory, check GC/live set, heap histograms, or heap dumps.
- `Class`/`Code` grows: check class loading, metaspace, or JIT code cache before calling it a leak.
- `Thread` grows: may come from **platform threads** and related native stacks; do not equate one virtual thread with one native stack.
- `GC`/`Internal`/`Native Memory Tracking` grows: inspect VM mechanisms or tool overhead.
- `malloc`/`mmap`/`arena` in detail: only paths HotSpot instrumented; arenas may be managed in blocks.

`jcmd <PID> VM.native_memory shutdown` stops tracking, and **NMT cannot be re-enabled via `jcmd`**. Do not run shutdown while you still need snapshots in the same session.

## 5. Cross-Checking the OS Where NMT Has Gaps

On Linux, use the **same PID and same timestamp** as the NMT report:

~~~bash
# Replace 12345 with the real Java PID; run on the host/namespace where the PID is visible.
PID=12345
ps -o pid,rss,vsz,comm -p "$PID"
grep -E '^VmRSS:|^VmSize:|^RssAnon:|^RssFile:' "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
pmap -x "$PID"
~~~

`ps rss` and `VmRSS` are typically in KiB. `smaps_rollup` shows total RSS/PSS; `/proc/<PID>/smaps` traces specific mappings: anonymous/private, file-backed, shared libraries, thread stacks, and allocator mappings. `VmSize/VSZ` is virtual address space, not resident RAM. Reading `/proc` may require appropriate permissions or namespaces.

For cgroup **v2**:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

A cgroup can include multiple processes, page cache, and other memory charges; do not equate cgroup memory with one PID's RSS. In Kubernetes, check pod/container namespaces, OOMKilled status, sidecars, and quotas. On Windows, compare Private Bytes/Working Set and memory mappings using Process Explorer/VMMap; on macOS, use `vmmap` and Instruments. Do not assume Linux commands work on every OS.

### Time-Series Inference Matrix

| Observation | Reasonable Hypothesis | Additional Data Needed |
| --- | --- | --- |
| NMT `Class`/`Code`/`GC` committed grows alongside RSS | VM expanding internal regions; may be normal under load | Detail call sites, class counts, compiler/GC behavior, growth timing |
| NMT `Java Heap committed` grows; RSS also grows | Heap committing additional space | Heap used/live set, GC logs, histogram; do not assert a Java leak yet |
| RSS climbs steadily while NMT committed stays near flat | Native allocations outside NMT coverage **or** residency/mapping/allocator shifts | `smaps`, per-library allocation stats, malloc/free call stacks |
| NMT `reserved` jumps sharply, RSS stable | Virtual address reservation grew | `committed` and OS mappings; do not call it a RAM leak |
| After `free`/GC, RSS does not drop immediately | Allocator cache/arena fragmentation or VM keeping committed memory | Live allocations, allocator stats, multiple allocate/release cycles |

A **memory leak** is proven when allocations that **should have ended their lifecycle** stay live and accumulate across operational cycles. High-water marks, legitimate caches, arenas kept for reuse, or file-mapped pages can keep RSS high without being a leak.

### Choosing Tools by Scope

- **HotSpot growth:** NMT `detail.diff`, class loading/GC/code-cache metrics.
- **Java object retention:** heap histogram, heap dump, JFR Java allocations when appropriate.
- **JNI/JNA/C/C++ `malloc/free` outside HotSpot:** allocation/free instrumentation, native allocator statistics, heaptrack, Valgrind Massif, LeakSanitizer/AddressSanitizer in test environments, or eBPF/uprobes/perf depending on system constraints.
- **`mmap`/file mappings:** `smaps`/`pmap`, mapping info and owner/lifecycle.
- **Libraries with custom caches/arenas:** library-specific debug counters and profiling (e.g., jemalloc/tcmalloc if actually used).

Do not replace the question "which library is holding allocations?" with a single `Total committed` figure. The OS tells you *where pages live*; profilers tell you *who allocated and who failed to free*; NMT tells you *what HotSpot managed*.

## 6. Java 17+ and JNI Lab: Native Allocations Untracked by HotSpot NMT

This standalone lab targets **64-bit Linux, JDK 17+, and GCC**, demonstrating a C library calling libc `malloc`, touching pages to raise RSS, holding a 64 MiB region during measurement, and then calling `free`. NMT itself still runs to monitor HotSpot; it is not designed to record every `malloc` from this C library.

### File `NmtBlindSpotLab.java`

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public final class NmtBlindSpotLab {
    private static final long BYTES = 64L * 1024 * 1024;

    private static native long mallocAndTouch(long bytes);
    private static native void nativeFree(long address);

    private static void pause(BufferedReader input, String prompt)
            throws IOException {
        System.out.println(prompt);
        if (input.readLine() == null) {
            throw new IOException("Run interactively from a terminal");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--help".equals(args[0])) {
            System.out.println("Usage: java NmtBlindSpotLab");
            return;
        }

        System.loadLibrary("nmtblindspot");
        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in));
        System.out.println("PID=" + ProcessHandle.current().pid());
        pause(input, "BEFORE: collect NMT and RSS, then press Enter");

        long address = mallocAndTouch(BYTES);
        try {
            pause(input, "ALLOCATED 64 MiB: collect NMT and RSS, then press Enter");
        } finally {
            nativeFree(address);
        }
        pause(input, "FREED: collect NMT and RSS, then press Enter to exit");
    }
}
~~~

### File `nmtblindspot.c`

~~~c
#include <jni.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

static void throw_java(JNIEnv *env, const char *name, const char *message) {
    jclass type = (*env)->FindClass(env, name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
    }
}

JNIEXPORT jlong JNICALL
Java_NmtBlindSpotLab_mallocAndTouch(
        JNIEnv *env, jclass owner, jlong requested) {
    (void)owner;
    if (requested <= 0 || (uint64_t)requested > SIZE_MAX) {
        throw_java(env, "java/lang/IllegalArgumentException", "Invalid size");
        return 0;
    }

    size_t size = (size_t)requested;
    volatile unsigned char *memory =
            (volatile unsigned char *)malloc(size);
    if (memory == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError", "malloc failed");
        return 0;
    }
    for (size_t offset = 0; offset < size; offset += 4096) {
        memory[offset] = 0x5A;
    }
    memory[size - 1] = 0x5A;
    return (jlong)(intptr_t)memory;
}

JNIEXPORT void JNICALL
Java_NmtBlindSpotLab_nativeFree(
        JNIEnv *env, jclass owner, jlong address) {
    (void)env;
    (void)owner;
    free((void *)(intptr_t)address);
}
~~~

**Explanation:** Java holds a native address as a `long`; the 64 MiB data lives outside the Java `byte[]` heap. C calls libc `malloc` directly and writes at least one byte per 4 KiB page to trigger OS allocation of resident pages rather than mere address reservation. Using `finally` ensures `free` is called exactly once at the end of the measurement phase. In production systems, design safe owners/handles instead of passing raw pointers around. The experiment assumes Linux x86_64/common page sizes; OS numbers still carry rounding/accounting variance.

Compile in the directory containing both files; `JAVA_HOME` must point to a JDK with `include/jni.h`:

~~~bash
javac -h . NmtBlindSpotLab.java
gcc -std=c11 -O0 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnmtblindspot.so nmtblindspot.c
java -XX:NativeMemoryTracking=detail \
  -Djava.library.path=. NmtBlindSpotLab
~~~

The program prints `PID=...` and waits at `BEFORE`. Open a **second terminal** and replace the example PID with the printed number:

~~~bash
PID=12345
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
grep -E '^VmRSS:|^VmSize:' "/proc/$PID/status"
~~~

In the Java terminal, press Enter **once** so C allocates/touches 64 MiB. When `ALLOCATED` appears, take a fresh snapshot:

~~~bash
jcmd "$PID" VM.native_memory summary.diff scale=MB
grep -E '^VmRSS:|^VmSize:' "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
~~~

**Prediction to verify:** RSS typically rises by roughly the 64 MiB allocation, depending on allocator, OS pages, and environment; NMT `summary.diff` will not show an extra 64 MiB in a HotSpot category corresponding to that libc `malloc`. A few NMT categories may still fluctuate slightly due to unrelated JVM activity. Press Enter again to `free` and capture another snapshot; the allocator may retain memory for reuse, so RSS does not necessarily drop immediately. This is a **lab illustrating tracking boundaries**; do not treat hypothetical numbers as evidence from a real incident.

If your machine lacks GCC/Linux, you can still practice the **NMT + OS metrics** portion using equivalent OS tools; the Java program requires the JNI shared library to run the `malloc` portion fully. Running `java NmtBlindSpotLab --help` checks the Java interface without loading the C library.

## 7. Investigation Scenario: Native Image-Processing Library

A Java service loads a C/C++ library for image processing. After every batch of 500 requests, RSS grows by another 100 MiB even after throughput returns to baseline; NMT `Class`, `GC`, and `Java Heap committed` barely change.

Evidence-based investigation steps:

1. **Synchronize metrics** for the same PID/time window/JDK, container configuration, load, and input images; collect RSS/PSS, NMT deltas, heap used/live set, errors, and native handle counts.
2. **Check semantic gaps:** NMT is not equivalent to RSS; check whether `smaps` shows growing private anonymous mappings or mapped files, and whether multiple processes share the cgroup.
3. **Isolate the library:** identify JNI/JNA call paths, contexts/pools, `malloc`/`mmap` timing, `free/close` methods, which requests increase allocations, and any exception paths.
4. **Profile native memory:** in staging, collect allocation/free call stacks or allocator stats; inspect live allocations across multiple cycles after requests complete.
5. **Change one variable:** cap concurrency or force-close native handles on one execution path; re-measure under comparable load. If live native bytes stop rising and RSS stabilizes, you have stronger causal evidence.
6. **Fix at the resource owner:** ensure cleanup in `finally`/`close`, clean up error/cancellation paths, fix library bugs if present, and bound intentional caches; verify across multiple workload cycles.

Do not call it a "100 MiB leak per 500 requests" solely because RSS grew: the memory may be a valid cache/arena. Verify whether live allocations are losing their owners. If cgroup memory grows while the Java PID's RSS stays flat, investigate sidecars/page cache/kernel charges before blaming JNI.

## 8. Common Misconceptions

1. **"NMT `Total committed` is total JVM RAM."** False; it is only HotSpot-tracked committed memory and does not share RSS's meaning.
2. **"`detail` sees every JNI `malloc`."** False; detail only goes deeper within the scope tracked by NMT.
3. **"`Other` is all native allocations outside the JVM."** False; it is a HotSpot category recorded by NMT.
4. **"Heap `reserved` 2 GiB means 2 GiB of RAM used."** False; reserved is virtual address space, not resident RAM.
5. **"High RSS after GC proves a leak."** False; heap committed, allocator high-water marks, caches/arenas, and mappings can keep RSS high.
6. **"Flat NMT proves there is no leak."** False; JNI/native libraries can grow outside NMT's scope.
7. **"RSS growth minus NMT growth equals leaked memory."** False because the metrics have different semantics and involve shared pages/page residency.
8. **"One `summary.diff` is enough to find the leaking library."** False; you need OS mappings and native allocation stacks/ownership over a time series.
9. **"NMT can be enabled mid-flight with `jcmd`."** False if the JVM started with it off.
10. **"If RSS doesn't drop right after `free`, `free` failed."** False; the allocator/OS may retain space for reuse, so observe live blocks and reuse.

## 9. Scope-Accurate Conclusion Checklist

- [ ] Accurately record HotSpot/JDK build, PID, CPU/memory quota, NMT level, and measurement timestamps.
- [ ] NMT enabled at startup, baseline set after warm-up, and multiple snapshots captured under the same workload.
- [ ] Interpret `reserved`/`committed` separately from `heap used`, RSS/PSS, and cgroup charges.
- [ ] Analyze HotSpot categories if NMT grows; do not assume all growth is a leak.
- [ ] If RSS grows while NMT stays flat, check OS mappings, JNI/JNA/C libraries, `malloc/mmap`, allocator caches, and native handles.
- [ ] If a leak is suspected, gather evidence of live native allocations by call site and resource lifecycle, not just a byte gap between two tools.
- [ ] Re-measure after fixes under identical load, tracking p95/p99, errors, RSS/PSS, NMT diff, and native allocation stats where available.
- [ ] Clearly distinguish **observations**, **hypotheses**, and **confirmatory experiments** in the report.

### Official Documentation

- Oracle Java 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle Java 21 — Diagnostic Tools/NMT categories: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java troubleshooting — native memory leaks and JNI: https://ops.java/troubleshooting/articles/memory-leaks/

**Guiding principle:** NMT answers "Which regions known to HotSpot is it reserving/committing?". To answer "How much RAM is the entire process currently keeping resident, and which native allocations are still live?", cross-check OS/container metrics and an allocator-appropriate profiler.
