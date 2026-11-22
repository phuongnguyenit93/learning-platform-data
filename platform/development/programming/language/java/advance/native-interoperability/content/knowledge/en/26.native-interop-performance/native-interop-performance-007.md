# Monitoring Native Memory, Handle Counts, and Latency in Long-Running Execution

**Context:** Java Advance → native-interoperability → Interop Performance.

A Java application calling a C/C++ library via JNI may run fine for a few minutes yet gradually increase process memory, run out of file descriptors/handles, or suffer worsening p99 latency after many hours. A non-growing Java heap **does not prove** that native memory is stable; a fast JNI call in an isolated test **does not prove** good latency under sustained load.

This article guides you through building time-series evidence across three axes: **native memory**, **handle-type resources**, and **latency**. The focus is on choosing the right measurements, placing counters at ownership boundaries, distinguishing footprint from leaks, running soak tests with baseline/cooldown phases, and tracing anomalous signals back to their root cause. A compilable Java 17 + C11 JNI example on Linux demonstrates observing a native resource allocated, retained, and released according to its proper lifecycle.

## 1. Three Questions That Must Be Answered Simultaneously

1. **Native memory:** How many *live* bytes is each stage using, how much physical memory is the process holding, and which numbers increase after returning to the same load? You need to know the source of allocations, not just a single total.
2. **Handle count:** How many native objects/file descriptors/sockets/OS handles remain open, what are the totals created/closed, and how many create/close operations failed? A handle may not consume much RAM yet still hit operating system limits.
3. **Latency:** From the caller's perspective, do p50/p95/p99 and the error/timeout rate increase while active memory/handles grow? Slow requests can be caused by GC, safepoints, native locks, I/O, page faults, or the allocator, so timeline correlation is required.

Do not pick only RSS, heap-used, or average latency to draw conclusions. For example, a library retaining a 512 MiB pool after its first load can keep RSS stably high; conversely, just a few thousand leaked FDs will cause new requests to fail even though RSS barely moves.

### Memory Map to Observe

| Layer | Examples | Observation Source | Measurement Limitations |
| --- | --- | --- | --- |
| Java Heap | Objects, byte[], native handle wrappers | MemoryMXBean, GC/JFR, heap dump | Does not contain all bytes allocated by malloc/native mmap. |
| HotSpot/JVM Memory | Thread stacks, GC internals, code cache, metadata | Native Memory Tracking (NMT), jcmd | NMT does not cover every malloc from third-party JNI libraries; reserved and committed must be inspected separately. |
| JVM-Managed Direct/Mapped Buffers | ByteBuffer.allocateDirect, mapped buffers | BufferPoolMXBean direct/mapped | *Estimated* values, not the total of all off-heap regions created by C/C++. |
| Application/Library-Owned Native Allocations | malloc/new, library memory arenas, mmap | Counters/histograms at allocate/free APIs, native profilers, OS maps | Must instrument at the exact owner; depending on the allocator, freed bytes may not be returned to the OS immediately. |
| Process Physical Memory | Anonymous pages, mapped libraries, stacks, shared pages | OS RSS/PSS/USS, container memory | RSS includes shared pages; does not equal total live bytes; container limits also include other components. |

**Reserved ≠ committed ≠ RSS ≠ live bytes.** Reserved is reserved address space; committed in JVM reports is the allocation commitment as tracked by HotSpot; RSS is pages currently resident in RAM; live bytes are resources the application has not yet released. Do not sum NMT committed + direct buffer + RSS as “total native memory”: the measurements may overlap or measure different things.

## 2. Designing an Observability Contract Where Resources Are Created

There must be a clear **owner** for each resource type: a JNI library, Java wrapper, C/C++ driver, or native subsystem. The resource-creating side should publish at minimum:

| Recommended Metric | Meaning | Usage |
| --- | --- | --- |
| native_allocations_total | Number of successful allocations since startup | Monotonic counter; compare against native_frees_total per resource type. |
| native_frees_total | Number of successful releases | Each resource must have one actual release; do not reset the counter during sampling. |
| native_live_blocks / native_live_bytes | Number of allocations and bytes currently still owned by the owner | Gauge; inspect the slope under steady load and after cooldown. |
| native_peak_live_bytes | Highest live bytes watermark | Used to check budget/peak; do **not** infer a leak from peak alone. |
| native_handles_open | Number of live logical handles per type | Distinguish library handles from OS FDs/sockets. |
| native_handle_open_errors_total / close_errors_total | Resource creation/closing errors | Alerts on resource exhaustion and lifecycle bugs. |
| native_operation_duration_seconds | Latency distribution per operation, labeled by operation/result | Histogram to compute percentiles over time windows. |
| native_inflight_operations | Number of native calls currently in progress | Used to identify concurrency/queue saturation. |

**Accounting invariant:** If a resource has one open and one close, on success paths it must hold that **live = successful_open − successful_close** (after properly accounting for pre-existing handles). Count open/close based on **actual events**, including during exceptions, timeouts, or cancellations. Do not treat a Java wrapper being garbage collected as proof that the resource was released, unless the ownership contract confirms that the release actually executed.

Some handles **are not file descriptors**: library pointers, GPU sessions, crypto contexts, device connections, JNI GlobalRefs, etc. Linux FD counts do not see all of them. For each type, measure the active count directly at the create/close API; use the OS FD count as an independent signal. On Windows, you can read the process handle count using OS/Win32 tools, but that also does not represent every logical resource inside a library.

Do not attach pointers/addresses/handle IDs to time-series labels: each ID creates a separate series, causing cardinality explosion. Use resource type, operation name, result, and library version; when you need to trace a specific handle, record the ID in sampled logs/tracing with bounded retention.

### Must Have Finite Lifecycle States

A sound wrapper transitions through states **OPEN → CLOSING → CLOSED**, ensuring the same pointer is never freed twice. If callbacks/native threads still use it, close must coordinate via reference counting, in-flight guards, or an owner thread; zeroing the address on the Java side alone **is not enough** when native code holds aliases. Use try-with-resources/AutoCloseable and release in finally; Cleaner (if used) is only a fallback, because GC timing is non-deterministic.

A native allocator may delay returning pages to the OS, so after release you must compare **native_live_bytes** and OS footprint separately. **live returning to baseline while RSS stays high** may indicate allocator caching/fragmentation or another region; **live rising steadily after cooldown** is a much stronger signal to investigate a missing release.

## 3. Latency Must Be Measured by Distribution and Call Boundaries

The steps of a Java → native call may include: Java caller → argument preparation/copy → JNI transition → native queue/lock → native computation/I/O → result copy → Java caller. Measure **end-to-end** using a monotonic clock from right before the call to right after receiving the result; if you need to break down root causes, add timers *inside* native code at meaningful stages.

- Use **System.nanoTime()** to measure elapsed intervals in Java; in C/C++, use the platform-appropriate monotonic clock (e.g., clock_gettime(CLOCK_MONOTONIC) on Linux). Do not use current wall-clock time to compute elapsed duration, because the system clock can be adjusted.
- Collect latency for **successes, errors, and timeouts alike**, grouped by operation and outcome. If you drop timed-out calls, percentiles only reflect the successful group and can look “fast” even as the system degrades.
- Track **p50** (median), **p95**, **p99**, and when enough samples exist, **p99.9**; always include sample count, throughput, and concurrency. For example, at 1,000 requests/minute, 1% equals about 10 requests/minute; averages hide the distribution tail.
- Histograms/percentiles must have explicit **time windows** (e.g., 1 minute, 5 minutes) and buckets aligned with SLOs. Do not average window p99 values to infer overall p99; merge histograms/raw samples that share the same measurement policy.
- If the workload is closed-loop (threads wait for a request to finish before sending the next), when the system bottlenecks, the actual send rate drops and easily causes **coordinated omission**. When SLOs require it, run controlled open-loop/arrival-rate load tests and record both queueing and timeouts.

JFR is useful for correlating the timing of GC, safepoints, thread scheduling, CPU, Java-side allocations, and blocking events. Standard JFR **is not a tracker for every malloc in a C library**; if the slowdown is deep inside native code, use native traces/metrics/profilers and align timestamps accordingly.

## 4. Collecting the Three Metric Layers on JDK 17 and Linux

### 4.1. NMT: How Much Native Memory Is HotSpot Using?

Start the **target JVM process** with NMT enabled from the beginning:

~~~bash
java -XX:NativeMemoryTracking=summary -jar your-service.jar
~~~

In another terminal, get the PID of that same JVM and take a baseline **after warm-up**:

~~~bash
jcmd -l
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
# Wait and run for a period under a controlled workload.
jcmd <PID> VM.native_memory summary.diff
~~~

In actual commands, replace **<PID>** with the numeric PID; angle brackets are only placeholder notation, do not type them literally into the shell. When you need to trace HotSpot allocation sites, restart with **-XX:NativeMemoryTracking=detail** and use **VM.native_memory detail** and **detail.diff**. You cannot enable NMT via a jcmd command after the JVM is already running if it was disabled at startup. NMT has overhead that should be considered when comparing latency numbers; compare against a consistent measurement configuration.

**Reading the results correctly:** inspect committed/reserved separately, categories such as Thread, Class, Code, GC, and changes since the baseline. According to Oracle JDK 17 NMT documentation, NMT primarily tracks HotSpot internal memory regions and **does not fully track allocations by JNI/third-party native libraries or all JDK class libraries**. Therefore, a flat NMT report does not rule out a malloc leak in a library you wrote.

### 4.2. OS: Footprint and File Descriptors

On Linux, inspect a running process (replace with the actual PID):

~~~bash
pid=12345
awk '/^(VmRSS|VmHWM|VmSize|Threads):/ {print}' \
  "/proc/$pid/status"
awk '/^(Rss|Pss|Private_Clean|Private_Dirty):/ {print}' \
  "/proc/$pid/smaps_rollup"
find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 -type l 2>/dev/null | wc -l
grep 'Max open files' "/proc/$pid/limits"
~~~

**VmRSS** is the current resident set, **VmHWM** is the process peak RSS; **Pss** divides shared pages across the processes sharing them; summing Private_Clean/Private_Dirty helps estimate the private portion. Accessing **/proc** files requires appropriate permissions, depending on kernel/container version. **/proc/PID/fd** lists the FDs currently held by the process; the count can change while the tool is scanning. You can use **lsof -p PID** to identify which FD types/paths/sockets are growing, though lsof output requires interpreting columns properly rather than assuming every row is a separate FD.

In containers, also record cgroup v2 **memory.current** and **memory.stat** when permitted. Cgroup limits may include page cache and other processes; do not equate them with the RSS of a single JVM.

### 4.3. BufferPoolMXBean, FD MXBean, and JFR

In Java, **java.lang.management.BufferPoolMXBean** provides **getCount()**, **getMemoryUsed()**, and **getTotalCapacity()** for pools (typically direct/mapped). These are **estimates**; getMemoryUsed may return **-1** when no estimate is available. On supported Unix JDKs/OSes, **com.sun.management.UnixOperatingSystemMXBean.getOpenFileDescriptorCount()** reports the number of open FDs in the process, not all native handles. On other environments, use an appropriate OS adapter.

Example JFR commands for a running service JVM:

~~~bash
jcmd <PID> JFR.start name=NativeObserve settings=default disk=true \
  maxage=30m maxsize=128m
# When you need to investigate a time period:
jcmd <PID> JFR.dump name=NativeObserve filename=native-observe.jfr
# When you no longer need to keep the recording:
jcmd <PID> JFR.stop name=NativeObserve
~~~

Use the **default** recording for long-running observation, and profile for short investigations needing extra detail. Choose size/maxage, storage location, and observation overhead appropriate for production. Collect custom metrics with UTC timestamps and monotonic elapsed durations to correlate with JFR/OS; do not compare clocks across processes by directly subtracting two System.nanoTime values from different JVMs.

## 5. Java 17 + C11 JNI Example: Measuring Native Live Bytes, Logical Handles, and p95/p99

The goal of this small example is to demonstrate **instrumentation right at the allocation/release API**. Java calls C to malloc/free a native block; C maintains two atomic gauges **liveBlocks/liveBytes**. Java intentionally retains 1 out of every 100 blocks to show the trajectory of active resources, then closes them all. At the same time, Java records open/close durations (microseconds), estimated direct-buffer bytes, and FD count if supported by the JVM/OS.

**Model note:** The returned long value is only an opaque handle; Java does not dereference the address itself. The example has **a single owner thread** per Block and forbids aliasing. If a native library has threads sharing the same pointer, you must manage in-flight/reference counts before freeing. Two independent atomic gauges are only suitable for approximate observation under concurrency, not a multi-variable atomic snapshot.

**File NativeSoak.java**

~~~java
import com.sun.management.UnixOperatingSystemMXBean;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Locale;

public final class NativeSoak {
    static {
        System.loadLibrary("nativesoak");
    }

    private static native long allocate(int bytes);
    private static native void release(long address);
    private static native long liveBlocks();
    private static native long liveBytes();

    private static final class Block implements AutoCloseable {
        private long address;

        Block(int size) {
            address = allocate(size);
            if (address == 0) {
                throw new IllegalStateException("No native address");
            }
        }

        @Override
        public synchronized void close() {
            long old = address;
            if (old != 0) {
                address = 0;
                release(old);
            }
        }
    }

    private static long directMemoryUsed() {
        for (BufferPoolMXBean pool
                : ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                return pool.getMemoryUsed();
            }
        }
        return -1; // No pool/estimate available.
    }

    private static long openFileDescriptors() {
        var os = ManagementFactory.getOperatingSystemMXBean();
        if (os instanceof UnixOperatingSystemMXBean unix) {
            return unix.getOpenFileDescriptorCount();
        }
        return -1; // Not supported on the current platform.
    }

    private static double percentileUs(
            long[] nanos, int from, int to, double q) {
        long[] sorted = Arrays.copyOfRange(nanos, from, to);
        Arrays.sort(sorted);
        int position = (int) Math.ceil(q * sorted.length) - 1;
        return sorted[position] / 1_000.0;
    }

    private static void report(
            String label, long[] samples, int from, int to) {
        System.out.printf(Locale.ROOT,
            "%s ops=%d active=%d bytes=%d directBytes=%d "
                + "fds=%d p95_us=%.2f p99_us=%.2f%n",
            label, to - from, liveBlocks(), liveBytes(),
            directMemoryUsed(), openFileDescriptors(),
            percentileUs(samples, from, to, 0.95),
            percentileUs(samples, from, to, 0.99));
    }

    public static void main(String[] args) {
        final int blockSize = 8192;
        final int total = 10_000;
        final int window = 2500;
        Deque<Block> retained = new ArrayDeque<>();

        // Warm-up is not recorded in the sample set, to let the library/JIT start up.
        for (int i = 0; i < 2000; i++) {
            try (Block ignored = new Block(blockSize)) {
                // Only measure the native allocation lifecycle.
            }
        }

        long[] nanos = new long[total];
        try {
            for (int i = 0; i < total; i++) {
                long start = System.nanoTime();
                Block block = new Block(blockSize);

                if (i % 100 == 0) {
                    retained.addLast(block);
                } else {
                    block.close();
                }

                nanos[i] = System.nanoTime() - start;

                if ((i + 1) % window == 0) {
                    report("window", nanos, i + 1 - window, i + 1);
                }
            }

            System.out.printf(
                "before_cleanup active=%d bytes=%d%n",
                liveBlocks(), liveBytes());
        } finally {
            while (!retained.isEmpty()) {
                retained.removeFirst().close();
            }
        }

        System.out.printf(
            "after_cleanup active=%d bytes=%d%n",
            liveBlocks(), liveBytes());
    }
}
~~~

**File nativesoak.c**

~~~c
#include <jni.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdlib.h>

typedef struct {
    size_t size;
    unsigned char payload[];
} NativeBlock;

static _Atomic long active_blocks = 0;
static _Atomic long active_bytes = 0;

static void throw_java(JNIEnv *env, const char *type,
                       const char *message) {
    jclass exceptionClass = (*env)->FindClass(env, type);
    if (exceptionClass != NULL) {
        (*env)->ThrowNew(env, exceptionClass, message);
        (*env)->DeleteLocalRef(env, exceptionClass);
    }
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_allocate(JNIEnv *env, jclass cls, jint bytes) {
    (void)cls;
    if (bytes <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "bytes must be positive");
        return 0;
    }

    size_t n = (size_t)bytes;
    if (n > SIZE_MAX - sizeof(NativeBlock)) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native size overflow");
        return 0;
    }

    NativeBlock *block = malloc(sizeof(NativeBlock) + n);
    if (block == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native malloc failed");
        return 0;
    }

    block->size = n;
    block->payload[0] = (unsigned char)(n & 0xffu);

    // Only count resources of this API, not the entire process.
    atomic_fetch_add_explicit(
        &active_blocks, 1, memory_order_relaxed);
    atomic_fetch_add_explicit(
        &active_bytes, (long)n, memory_order_relaxed);
    return (jlong)(intptr_t)block;
}

JNIEXPORT void JNICALL
Java_NativeSoak_release(JNIEnv *env, jclass cls, jlong address) {
    (void)env;
    (void)cls;
    if (address == 0) {
        return;
    }

    NativeBlock *block = (NativeBlock *)(intptr_t)address;
    long n = (long)block->size;
    free(block);

    atomic_fetch_sub_explicit(
        &active_bytes, n, memory_order_relaxed);
    atomic_fetch_sub_explicit(
        &active_blocks, 1, memory_order_relaxed);
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_liveBlocks(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jlong)atomic_load_explicit(
        &active_blocks, memory_order_relaxed);
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_liveBytes(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jlong)atomic_load_explicit(
        &active_bytes, memory_order_relaxed);
}
~~~

**Compile/run on Linux x86-64 with JDK 17+ and GCC supporting C11** (JAVA_HOME pointing to the JDK):

~~~bash
javac -h . NativeSoak.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativesoak.so nativesoak.c
java -Djava.library.path=. NativeSoak
~~~

**Two verification lines with deterministic output on a successful run:**

~~~text
before_cleanup active=100 bytes=819200
after_cleanup active=0 bytes=0
~~~

Four **window** lines are printed before these two lines; the values of **p95_us/p99_us, fds, and directBytes** depend on the JVM, scheduling, and OS, so there is no reliable fixed stdout for those lines. The program does not create a real leak: it **retains 100 blocks during the load phase and then releases all of them in finally**. The number 100 is 10,000 / 100; each block has 8,192 bytes → 819,200 bytes. The gauges only measure memory managed by these two allocate/release APIs and do not replace RSS, NMT, or native profilers.

This example measures allocation time **plus Java→JNI release operations** and an intentional retention ratio; it is not an end-to-end throughput/latency benchmark of a production service. If the machine does not support UnixOperatingSystemMXBean, **fds=-1** means “no data available” and must never be interpreted as 0 FDs. **NativeSoak.release** assumes a valid handle, owned by the caller, not yet freed; a raw pointer reused across another wrapper will cause a severe native error. Production implementations should use a handle table that checks generation/id and coordinates with in-flight tasks instead of exposing raw pointers.

## 6. Scaling the Example into a Long-Running Test (Soak Test)

A loop of 10,000 operations only verifies the mechanism; detecting slow leaks requires **time** and **representative workload volume**. For a real JNI service, keep JVM/GC configuration, library versions, CPU/memory limits, allocator, traffic mix, and worker count constant so runs remain comparable.

### Recommended Scenario

| Phase | Conditions | What to Collect and Compare |
| --- | --- | --- |
| 1. Startup/warm-up | Load native libraries, JIT, initialize pools, caches | Wait for metrics to stabilize; distinguish startup growth from leaks. |
| 2. Baseline | Low load or steady standard load | RSS/PSS, NMT committed/reserved, direct pool, live bytes, active handles/FD, p95/p99, throughput, error rate. |
| 3. Steady load | Run for many hours at the same arrival rate/concurrency | Trend of live resources, RSS slope, FD count, tail latency; store samples with timestamps. |
| 4. Burst/peak | Increase load within expected limits | Peak handles/memory, allocator behavior, p99, timeouts, and recovery time. |
| 5. Cooldown | Return to **the same load level** as baseline, then drain pending tasks | Compare active resources with baseline; RSS may not shrink even if live drops. |
| 6. Graceful shutdown | Wait for in-flight = 0, then release all owner-managed resources | Count opens/closes and remaining live bytes; check error/close failures. |

A practical cadence could be 1–10 second metrics and NMT/OS snapshots every 1–5 minutes, adjusted for error rate and sampling cost. Tail metrics should be computed from histograms over explicit windows. Record **offered/accepted/completed workload**, pending request count, and outcome breakdown; if incoming request volume changes, absolute memory trends may not be comparable.

To detect a **retained leak**, measure state after all in-flight work finishes under **the same conditions**. For example:
- Baseline: 100 active handles due to a persistent pool; after 6 hours at the same load, it steadily rises to 1,300 and does not return to ~100 → investigate missing close paths.
- Live memory map does not grow, but RSS rises and stays at a plateau after a burst → could be allocator caching, fragmentation, mappings, or JVM heap commitment. More evidence is needed before calling it a leak.
- For each window, compare **live_bytes / active tasks** and **the delta after cooldown**; under the same workload, a sustained upward trend is more suspicious than a single high RSS value.

### Collecting a Simple OS Time Series on Linux

With a known PID, only use the script below to observe **the same process**, without mistaking it for another JVM. FD sampling is approximate because opens/closes can occur while listing:

~~~bash
pid=12345
while kill -0 "$pid" 2>/dev/null; do
  date -Is
  awk '/^(VmRSS|VmHWM|Threads):/ {print}' \
    "/proc/$pid/status"
  printf 'open_fds='
  find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 -type l \
    2>/dev/null | wc -l
  sleep 60
done
~~~

Send output to your existing metrics/logging system if long-term tracking is needed; include process ID, deploy timestamp, JVM version, and native library version. Track the rate of failed/unauthorized samples; if a metric source is unavailable, represent it as unknown rather than turning the value into 0.

## 7. Interpreting Signals: What Kind of Anomaly Is Happening?

| Observation in the Same Time Window | Priority Hypothesis | Next Checks |
| --- | --- | --- |
| Java heap mostly stable; RSS rising; native_live_bytes counter rising after cooldown | Missing free/handle release in native library | Correlate allocation stacks/call sites, open/close per operation, inspect exception/cancel paths. |
| RSS rising; NMT committed rising noticeably in Thread | Thread count or thread stack growth | Thread count, JFR, stack traces, thread pools and shutdown. |
| RSS rising; NMT mostly flat; direct pool flat | Native allocations outside HotSpot or mapping/fragmentation | Custom counters, /proc/PID/smaps_rollup, native heap profiler, malloc tracing in a controlled environment. |
| FD count rising steadily while native malloc counters are stable | Unclosed sockets/files/pipes/eventfds | lsof, /proc/PID/fd, Java/native resource ownership, close/error paths. |
| Custom native_handles_open rising while OS FD stays unchanged | Opaque library handle not backed by an FD | Create/release API logs/metrics, check callbacks/child owners. |
| p99 rising with active handles/in-flight; CPU not very high | Queueing, contention, locks, or I/O backlog | Per-stage native timers, thread states, queue length, timeouts. |
| p99 spikes coincide with GC/safepoints | JVM-side pauses affecting end-to-end latency | JFR/GC logs, allocation rate, pause durations; do not jump to blaming slow C code. |
| RSS at a high plateau after load while native_live_bytes returns to baseline | Allocator cache/fragmentation or HotSpot memory still committed | Compare PSS, NMT, mmap/allocator stats, check trends across multiple cycles. |
| Active handles drop but double-free/crash errors occur | Broken ownership/aliasing; close racing with active tasks | Generation-safe handle registry, refcount/in-flight guard, appropriate native sanitizers. |

Do not conclude a root cause from a single chart. For example, “RSS rises while NMT is stable” only **suggests** something outside NMT's scope; you must combine live allocations, direct buffers, mmap, native profilers, and active workload. A **heap dump** does not show the full malloced payload, but it can reveal which Java wrappers still hold references to native resources.

## 8. Pitfalls in Long-Running Measurement

**Observer effect:** Every debug log, allocation stack trace, and profiler costs CPU/RAM; NMT detail and JFR profile can alter tail latency. Measure overhead separately and use a sensible sampling policy before comparing debug-environment numbers with production.

**Wrong baselines and wrong samples:** Comparing morning idle RSS with end-of-day peak RSS produces skewed conclusions. A 99th percentile over a few dozen calls has no meaningful resolution. Sampling only successful requests omits timeouts; statistics can look better during an outage.

**GC and Cleaner:** A ByteBuffer/Java wrapper may already be unreachable while native cleanup has not run yet. Do not use System.gc() as a design cleanup mechanism; forcing a GC once in a test can help distinguish retention via Java wrappers, but it distorts normal operating cadence. Use deterministic close and report actual release metrics.

**Allocator reuse:** free may return blocks to a cache/tcache/arena without lowering RSS; native memory fragmentation can increase footprint even when live bytes are stable. Observe OS mappings/allocator stats and sufficiently long load cycles before judging.

**Races in counters:** If updating native_live_bytes is non-atomic or skips an error path, monitoring itself becomes wrong. Two gauges read separately under concurrency may not match the same point in time; for a consistent snapshot, capture them under the same lock/version protocol rather than just reading two atomics back-to-back.

**Handle limits:** Linux has per-process **RLIMIT_NOFILE** and system-wide limits; do not treat “FD count below limit” as proof that sockets/pools are not leaking. FD count may dip temporarily during retries/connection timeouts and then rise again. Measure age, type, open/close rates, and owner activity.

**JNI/FFM lifetime:** JNI local/global refs, native buffers, and arenas/MemorySegments have their own lifetime rules. If a library keeps a pointer after the Java scope has ended, use-after-free occurs even if RAM counters look fine temporarily. With JDK 22+ FFM, Arena.ofShared only allows multiple threads to access within its valid scope; it does not automatically guarantee thread safety or track arbitrary C-side mallocs.

**Shutdown bugs:** Wait for native threads/callbacks/in-flight work to reach 0 before releasing. Check timeouts, exceptions, cancellations, retries, partial initialization, close called multiple times, and deploy shutdown paths; those are usually where cleanup is missed.

## 9. Investigation Workflow and Completion Criteria

1. **Define scope:** Which JVM/OS, which native library version, which handle/operation types; explicitly document resource owners and close contracts.
2. **Establish baseline after warm-up:** capture heap + direct pool + NMT + OS RSS/PSS + FD/custom handles + latency histogram under the same load conditions.
3. **Collect timestamped time series:** measure by windows with count/throughput/errors/in-flight; keep peak points and cooldown data.
4. **Find divergence:** if native_live rises without GC heap growth, inspect allocate/free APIs; if FDs rise, inspect opens/closes; if p99 rises, compare queue/GC/native timers.
5. **Reproduce under control:** increase iterations, traffic mix, cancellations, timeouts, bursts, and shutdowns. You can intentionally retain resources in a small test like the example to verify alerts.
6. **Fix at the owner and rerun the same workload:** add close/finally, handle callback/thread lifecycles, or reduce contention; do not just add periodic GC/restarts to mask the bug.
7. **Set regression gates:** over the same duration/same load, active resources do not drift continuously, there are no close errors, FD/memory limits retain headroom, and p99/error rate stay within approved SLOs.

A reference criterion must be **quantified per system**: after a sufficiently long soak and cooldown, **outstanding native allocations/handles** return to baseline within an acceptable fluctuation band; there is no sustained upward trend when normalized by workload; p99 and timeout rate remain stable within budget; metrics remain intact when native/JVM errors occur. Specific numeric thresholds depend on the service type; do not apply a single MiB/minute or p99 threshold across every project.

## 10. Self-Check Questions

1. Why might NMT summary.diff remain unchanged while a JNI library repeatedly calls malloc without freeing?
2. When directBuffer getMemoryUsed and RSS differ, why can you not take the larger number as “native live bytes”?
3. If native mallocs are freed but RSS stays the same after cooldown, what data do you need before concluding there is a leak?
4. The OS FD count is not increasing, but active opaque handles from a C library are growing; where should you place metrics?
5. Why can the p99 of **successful** requests decrease at the same time the timeout rate increases?
6. In the NativeSoak example, why must retained Blocks be closed in finally; when is synchronized close still insufficient to prevent use-after-free?
7. How do you prove that a latency issue is caused by native locks/queues rather than GC, OS page faults, or Java thread scheduling?
8. Why must you compare baseline and cooldown under the same load level and the same JVM/native library versions?

**Core principle:** Long-running observability is only trustworthy when you measure *resource lifecycles at the owner* and *actual process footprint* alongside *latency distributions and workload*. RSS/NMT/FD/histograms complement one another; none of them alone proves that a JNI application has no leaks or tail-latency regressions.

## References

- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): HotSpot scope, summary/detail, baseline/diff, overhead.
- [Oracle JDK 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): VM.native_memory, JFR.start/dump/stop.
- [Java 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): count, capacity, and memoryUsed estimates.
- [Java 17 — UnixOperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html): file descriptor count on Unix.
- [Oracle JDK 17 — JNI Function Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): JNI rules, references, and native interface.
- [Linux proc(5) — /proc/PID/status, smaps, and fd](https://man7.org/linux/man-pages/man5/proc.5.html): process and memory data.
