# 13.9. Distinguishing Native Thread Creation Failures, Direct Allocation Failures, and Java Heap Exhaustion

## Objectives

Three Java errors can all contain `OutOfMemoryError` yet point to **three distinct resources and allocation steps**:

1. The JVM cannot create a new **native thread**.
2. The JVM or a library cannot allocate a **direct/off-heap buffer**.
3. The JVM cannot allocate an **object in the Java heap**.

Therefore, seeing `java.lang.OutOfMemoryError` is not enough to conclude "heap is too small, increase `-Xmx`". You must read **the full detail message, stack trace, JVM logs, counters, and OS/container limits**. This lesson focuses on **HotSpot JDK 17+**. Exact messages, resource groups, and failure mechanics may vary by vendor/JDK, OS, collector, and library.

## 1. Distinct Resource Regions Within the Same JVM

```text
A Java process (within OS/container limits)
│
├── Java heap                    → Java objects/arrays, GC-managed, -Xmx
│   └── DirectByteBuffer wrapper → object on heap, while payload resides off-heap
│
├── Native / off-heap memory
│   ├── Native thread stacks     → stacks and metadata serving OS threads
│   ├── Direct buffer payload    → typically allocated outside the Java heap
│   ├── Metaspace / Code Cache / JVM internals / GC structures
│   └── JNI / native libraries / memory-mapped regions / other
│
└── Independent limits
    ├── Java heap maximum (-Xmx)
    ├── Direct-buffer reservation limit (-XX:MaxDirectMemorySize)
    ├── OS task/thread quotas and per-thread stack (-Xss affects stack)
    └── Address space, RAM/swap, container memory, and cgroup PID quotas
```

Key concepts to distinguish:

- **Java heap used:** the portion of the heap holding objects per JVM stats; **heap committed** is the memory the JVM has committed for the heap, while **heap max** is the reported heap ceiling. These three numbers are not the same.
- **Native memory:** memory outside the Java heap used by the JVM, OS, native libraries, or off-heap allocators; **not synonymous with direct buffers alone**.
- **Thread stack:** JVM platform threads require OS resources and stack regions; increasing thread count can raise native memory or hit task/PID limits even when the heap is not full.
- **Direct buffer:** a `java.nio.DirectByteBuffer` has its wrapper on the Java heap, while its data payload typically resides in native/off-heap memory. Seeing a small wrapper in a heap dump does not reflect the full payload cost.
- **Reserved, committed, and RSS are not identical:** reserved is a set-aside address range, committed is the JVM/OS-committed amount per reporting rules, and RSS is actually resident pages observed by the OS at measurement time. Do not mechanically sum reserved values to claim RSS.

The same application can encounter all three error types at different times. Identify **which allocation operation failed first** before deciding on a fix.

## 2. Quick Identification Table

| Prominent Signal | Native Thread Creation Failure | Direct Buffer Failure | Java Heap Exhaustion |
| --- | --- | --- | --- |
| Common detail message | `unable to create native thread`; may include `possibly out of memory or process/resource limits reached` | `Cannot reserve ... bytes of direct buffer memory (allocated: ..., limit: ...)` or `Direct buffer memory` | `Java heap space` |
| Typical stack location | `Thread.start0`, `Thread.start`, executor creating a worker | `java.nio.Bits.reserveMemory`, `DirectByteBuffer`, `ByteBuffer.allocateDirect`, or NIO/Netty libraries | `new`, array creation, collections, object deserialization; many sites |
| Resource directly rejected | Native thread / OS task and auxiliary resources | Direct buffer reservation or native allocation | Object / array on the Java heap |
| Counters to check | OS thread count, Java live threads, `pids.max`/`pids.current`, NMT Thread, memory/address space | BufferPoolMXBean `direct`, direct allocated/capacity, `MaxDirectMemorySize`, RSS, NMT/OS | Heap used/max, GC logs, post-GC heap, histogram/dump |
| Typical fix after evidence | Fix thread growth/pools, bound concurrency reasonably; inspect quotas/stacks | Release buffers/pools per lifecycle; tune direct budget within headroom | Shrink live set/allocations, fix retention; review `-Xmx` |
| What **cannot** be inferred | "Raising `-Xmx` will allow more threads" | "Low Java heap means direct cannot fill up" | "Any Java heap space error means a memory leak" |

**Important detail:** `OutOfMemoryError` is an `Error` thrown by the JVM/library, not a normal business case to catch and ignore indefinitely. Once a process has exhausted resources, error-handling paths and even diagnostic commands can fail too.

## 3. Type A: Unable to Create Native Thread

### 3.1 Message, Origin, and Example

On HotSpot/Linux, a failure may look like:

```text
java.lang.OutOfMemoryError: unable to create native thread:
possibly out of memory or process/resource limits reached
    at java.base/java.lang.Thread.start0(Native Method)
    at java.base/java.lang.Thread.start(Thread.java:...)
```

Or JVM/OS logs may show `pthread_create` failing, e.g., with `EAGAIN`. This is an **illustrative error format**; exact line numbers, wording, and errno depend on platform/JDK.

`Thread.start()` must create a platform/native thread. The OS can reject it due to:

- **Excessive thread count:** spawning a new thread per request; unbounded workers; threads that never exit; `ExecutorService` instances created repeatedly without `shutdown()`; oversized thread pools.
- **PID/task limits:** `RLIMIT_NPROC`, systemd `TasksMax`, cgroup `pids.max`, or other system limits. On Linux, the cgroup PID controller counts **tasks**, so many threads can hit the limit even with few processes.
- **Insufficient native memory/address space for stacks or metadata:** hundreds or thousands of threads can reserve separate stack regions while other native components also compete for resources.
- **Memory pressure or container limits:** the process still has Java heap headroom, yet the OS cannot grant more native resources. Conversely, simply seeing a large `-Xss` is insufficient to prove physical RAM exhaustion because stack reserved and resident differ.

**Diagnostic clue:** if heap usage is low while `Thread.start()` fails, check thread/PID quotas and native memory first. Also distinguish Java application threads from JVM GC/JIT/native threads: counts in `ThreadMXBean` do not necessarily match total OS `Threads`.

### 3.2 Collecting Data

For an example process with PID `12345`:

```bash
jcmd 12345 Thread.print -l
jcmd 12345 VM.native_memory summary
```

- `Thread.print -l` records a thread dump and lock info, helping spot huge numbers of threads with identical names/stacks (e.g., an unbounded worker pool). With thousands of threads, output and cost can be large.
- `VM.native_memory summary` has data only if **Native Memory Tracking (NMT) was enabled at JVM startup**. In the `Thread` category, inspect `reserved`, `committed`, and JVM-accounted thread count; do not automatically equate these numbers with RAM/RSS.
- Do not rush to capture a full heap dump just to investigate native thread creation.

On **Linux**, combine OS and cgroup info (the following paths match **common cgroup v2**, and may differ in containers/v1):

```bash
cat /proc/12345/status
cat /proc/12345/limits
cat /proc/12345/cgroup
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
```

- `/proc/12345/status` shows `Threads` and `VmRSS`; `limits` shows relevant process/task limits.
- If `pids.current` is close to `pids.max`, verify quotas first. A value of `max` usually means no limit is set at that cgroup level, though parent-level limits may still exist.
- The `/sys/fs/cgroup/...` files above describe whichever cgroup that path points to. On hosts/containers, identify **the exact cgroup of the target process** from `/proc/12345/cgroup`; do not draw conclusions from another cgroup's metrics.
- If the system lacks `/proc` or cgroup v2, use equivalent OS/Windows tools (e.g., Process Explorer/PerfMon) instead of applying Linux commands verbatim.

**Remediation direction:** bound thread creation, use purposefully sized thread pools and queues, shut down executors properly, and track down thread leaks. Adjust quotas only after confirming the app legitimately needs that concurrency. `-Xss` affects per-Java-thread stack size; lowering it can reduce reservations but increases `StackOverflowError` risk for deep call stacks. `-Xmx` is not a direct knob for this error.

## 4. Type B: Direct Buffer Allocation Failure

### 4.1 Nature and Messages

With `java.nio.ByteBuffer.allocateDirect(n)`, the management wrapper lives on the Java heap while the payload is typically allocated off-heap. HotSpot tracks a direct-buffer budget; when it cannot reserve additional capacity, `java.nio.Bits.reserveMemory` may throw:

```text
java.lang.OutOfMemoryError:
Cannot reserve 1048576 bytes of direct buffer memory
(allocated: 67108864, limit: 67108864)
    at java.base/java.nio.Bits.reserveMemory(Bits.java:...)
    at java.base/java.nio.DirectByteBuffer.<init>(DirectByteBuffer.java:...)
    at java.base/java.nio.ByteBuffer.allocateDirect(ByteBuffer.java:...)
```

This is an **example message**, not guaranteed stdout. `allocated/limit` comes from the direct buffer implementation's reservation counters/rules; **it does not equal total process RSS**. A different JDK version or library may report `Direct buffer memory` or fail native allocation elsewhere.

Two cause groups must be separated:

1. **Hitting the direct budget limit** set by `-XX:MaxDirectMemorySize` or JVM defaults while the Java heap still has free room.
2. **Inability to obtain actual native memory** due to container/OS/address space/allocator limits, or because other native sources consume too much memory. A program can fail native allocation even before reaching its configured reservation cap.

Situations that grow direct buffers include I/O/networking, channel reads/writes, pooled buffers, calling `allocateDirect` too frequently, libraries holding buffers in caches/pools, or reachable wrappers preventing cleaners from freeing payloads.

### 4.2 Direct Memory Cap and Reclamation

```bash
java -Xmx512m -XX:MaxDirectMemorySize=128m -jar app.jar
```

- `-XX:MaxDirectMemorySize=128m` caps direct buffer memory per the HotSpot/JDK implementation, **not all native memory** (thread stacks, JNI allocations, metaspace, etc.).
- Direct buffers may be cleaned when wrappers become unreachable and cleaner/reference processing runs; **there is no guarantee of immediate deallocation upon setting `null`**.
- Many frameworks use custom buffer pooling, reference counting, or release mechanisms; read the framework's lifecycle contract. Keeping a buffer in a pool can be a valid reuse strategy, whereas an unbounded pool or missing releases drives rising usage.
- `System.gc()` is not a reliable way to free direct buffers and rescue an exhausted system; GC can be delayed or configured differently, and it does not fix buffer retention.
- **Raising `-XX:MaxDirectMemorySize`** makes sense only when direct usage is genuinely capped, the app has a legitimate need, and the OS/container has sufficient headroom. Raising the cap without investigating retention can shift the failure from direct budget to an OOM kill/native memory exhaustion.

### 4.3 Direct Measurement with BufferPoolMXBean

The JDK provides `java.lang.management.BufferPoolMXBean`. For the pool named `direct`:

- `getCount()`: estimated number of buffers in the pool.
- `getTotalCapacity()`: estimated total capacity (bytes) of managed buffers in the pool.
- `getMemoryUsed()`: estimated native memory used by the pool; may differ from capacity due to alignment/allocator and **can return `-1`** when unavailable.

These metrics do not cover every JNI allocation, native library, self-managed framework pool, or every kind of off-heap memory. Compare against `MaxDirectMemorySize`, logs, and RSS. If the direct pool climbs continuously while the heap stays flat, prioritize finding retained buffers, unreleased pools, or excessive I/O concurrency.

**A heap dump can show `DirectByteBuffer` wrappers and reference paths**, but because payloads live off-heap, `shallow heap` does not reflect full native size. Capturing a heap dump can also perturb the scene; never treat HPROF file size as total direct memory.

## 5. Type C: Java Heap Exhaustion

### 5.1 Symptoms and Causes

An error pattern:

```text
Exception in thread "worker" java.lang.OutOfMemoryError: Java heap space
    at com.example.Service.buildResult(Service.java:...)
```

This illustrates a stack location, not code/error from a specific app. The JVM lacks enough space in the **Java heap** to allocate the needed object/array (and cannot satisfy it after allowed collection/expansion mechanisms).

Typical causes:

- Heap limit set too low for the **live set** and legitimate load.
- Memory leak where objects remain held by GC roots: `static` caches without eviction, uncleaned `ThreadLocal`s, unregistered listeners, ever-growing collections, non-expiring sessions.
- Oversized allocation bursts: reading whole files/responses into memory, large intermediate structures, high request concurrency.
- Frequent GCs reclaiming very little because most objects remain reachable.

**Not every heap-related `OutOfMemoryError` carries the detail `Java heap space`**. Errors such as `GC overhead limit exceeded`, `Requested array size exceeds VM limit`, `Metaspace`, or `Direct buffer memory` have distinct meanings. For instance, `Requested array size exceeds VM limit` can occur when an array length exceeds JVM limits even if the heap has ample memory.

### 5.2 Measuring Java Heap and Monitoring GC

```bash
jcmd 12345 GC.heap_info
jcmd 12345 VM.flags
```

GC logging can be enabled at JVM startup:

```bash
java -Xms256m -Xmx512m \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

When analyzing, check **post-GC heap used**, GC frequency, pauses, allocation rate, heap occupancy, object retention, and changes across load waves. One moment of high heap used does not prove a leak; **live set rising persistently across multiple GCs under steady load** is strong evidence worth investigating.

When a heap dump is needed to trace roots:

```bash
jcmd 12345 GC.heap_dump /tmp/java-heap.hprof
```

This command has CPU/I/O cost, requires disk space, and on HotSpot JDK 17 **requests a Full GC by default** unless `-all` is chosen. Thus it can alter the scene; use it based on diagnostic goals and avoid running it blindly on an already resource-starved production process. You can inspect Dominator Tree, retained heap, and paths to GC roots in MAT.

When you need a dump automatically when the JVM throws OOME, prepare beforehand:

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/tmp/oom.hprof \
  -jar app.jar
```

**Do not claim one HPROF file explains every kind of OOME**: a heap dump describes the Java heap and object graph, not all native memory or thread/PID quotas. Creating a dump during an incident also needs resources and can fail.

## 6. Getting NMT Metrics and Their Limits

**Native Memory Tracking (NMT)** is a HotSpot tool tracking internal JVM memory by categories like `Java Heap`, `Thread`, `Class`, `Code`, and `GC`. It must be enabled at **process startup**; do not assume you can fully enable it on a running process if it started disabled.

Example:

```bash
java -Xms256m -Xmx512m \
  -XX:MaxDirectMemorySize=128m \
  -XX:NativeMemoryTracking=summary \
  -jar app.jar
```

Then run commands from the same environment with attach permissions:

```bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
```

After a workload interval, capture the delta:

```bash
jcmd 12345 VM.native_memory summary.diff scale=MB
```

- **`Thread` growing** alongside thread count: check stack reservations and native structures; also cross-check OS task counts/quotas.
- **`Java Heap` in NMT** primarily reports reserved/committed heap ranges, **not replacing `MemoryMXBean.getHeapMemoryUsage().getUsed()`** for object usage.
- **Other native categories growing:** identify which category and cross-check profilers, JNI, allocators, OS RSS, and BufferPoolMXBean; do not treat any arbitrary NMT category as direct buffers.
- **Large `reserved` does not mean the same amount of physical RAM is used**. Nor does `committed` equal total process RSS.
- NMT **does not track all third-party native/JNI library allocations** and incurs overhead; combine with OS tools when needed. In production, weigh the cost of enabling NMT.

If the command reports NMT is not enabled, **that is an observation gap**, not proof the process uses no native memory.

## 7. Java 17: Program Capturing Three Metric Groups Without Intentionally Triggering OOME

A safer example than spawning thousands of threads or allocating until crash is **observing signals** before and after a small direct-buffer allocation. Create **`MemoryFailureSignals.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.nio.ByteBuffer;

public class MemoryFailureSignals {
    private static void snapshot() {
        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.printf("heap.used=%d heap.committed=%d heap.max=%d%n",
                heap.getUsed(), heap.getCommitted(), heap.getMax());
        System.out.printf("threads.live=%d threads.peak=%d threads.started=%d%n",
                threads.getThreadCount(),
                threads.getPeakThreadCount(),
                threads.getTotalStartedThreadCount());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                System.out.printf("direct.count=%d direct.capacity=%d direct.used=%d%n",
                        pool.getCount(), pool.getTotalCapacity(), pool.getMemoryUsed());
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("BEFORE");
        snapshot();

        ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
        buffer.putInt(0, 42);

        System.out.println("AFTER");
        snapshot();
        System.out.println("sample.capacity=" + buffer.capacity());
        System.out.println("sample.value=" + buffer.getInt(0));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 MemoryFailureSignals.java
java -Xms64m -Xmx256m \
  -XX:MaxDirectMemorySize=64m \
  -XX:NativeMemoryTracking=summary \
  MemoryFailureSignals
```

Lines **guaranteed by the example's logic when allocation succeeds**:

```text
BEFORE
...
AFTER
...
sample.capacity=1048576
sample.value=42
```

`...` above simply indicates metric lines that **vary by JVM/environment**, not literal output to copy. `heap.used`, `heap.committed`, `heap.max`, `threads.live`, and direct pool values should be read from an actual run; `direct.used` may be `-1` if the JVM does not support an estimate. On some JVM platforms, metric reporting may not match HotSpot identically.

**Interpretation:**

- `heap.used` and `heap.max` indicate Java heap pressure. A 1 MiB direct-buffer payload does not mean `heap.used` must rise by 1 MiB.
- `direct.capacity` and `direct.used` reflect the JVM-reported buffer pool; after allocating a new buffer, they typically rise accordingly while the buffer remains reachable. The `MaxDirectMemorySize` limit applies per JVM semantics, not total native RSS.
- `threads.live` is the **live Java platform thread count** seen by `ThreadMXBean`; do not treat it as the OS's exact task/PID count.
- To determine **OOME root cause**, sample metrics periodically and pair them with the **stack trace/detail message at failure time**. A single snapshot does not prove a memory leak.

The program does not intentionally exhaust memory or spawn threads en masse. If an environment is already severely constrained, even a 1 MiB `allocateDirect` can fail; that is a signal to investigate, not a forced outcome.

## 8. Investigation Workflow: Read Evidence Before Tuning Flags

### Step 1 — Pin Down the Exact Error Type

Preserve **the verbatim first few lines and stack trace**, PID, timestamp, JVM vendor/version, startup flags, workload, and container/OS limits. Branch by detail message:

```text
OutOfMemoryError occurred?
  |
  +-- "unable to create native thread"
  |      -> Thread count / task quota / native stacks / native headroom
  |
  +-- "Cannot reserve ... direct buffer memory" or "Direct buffer memory"
  |      -> Direct pool / MaxDirectMemorySize / buffer lifecycle / native headroom
  |
  +-- "Java heap space"
  |      -> Heap used/limit / GC / live set / allocations / GC roots
  |
  +-- Other message (Metaspace, array size, native allocation ...)
         -> Investigate the exact resource region named by that message
```

The stack trace adds where the allocation failed; **do not infer the whole cause from a method name alone** when the detail message carries clearer semantics.

### Step 2 — Check Underlying Resources and Container

- `-Xmx` and heap usage, `-XX:MaxDirectMemorySize`, thread count, `-Xss`, NMT native memory, RSS.
- On Linux: process limits, `pids.current/pids.max`, and `memory.current/memory.max` of **the exact cgroup**; if capped at a parent level, inspect the cgroup hierarchy.
- **An OS OOM killer event differs from a Java `OutOfMemoryError`**: a process killed with `SIGKILL` may print no Java exception. Containers often report exit code 137 on SIGKILL, yet **137 alone does not prove an OOM kill**; cross-check kernel logs, Kubernetes events, or cgroup `memory.events`/`oom_kill`.

### Step 3 — Cross-Check Signals and Choose Remediation

| Situation | Additional Evidence Needed | Remediation After Verification |
| --- | --- | --- |
| Post-GC heap normal, thread count climbs steadily, `pids.current` near `pids.max` | Time-series thread dumps, stacks/owners, pool config | Fix unbounded thread creation/missing shutdown, lower worker count, or adjust quotas with justification |
| Thread count modest yet `Thread.start` fails, native committed/RSS high | Cgroup RAM, `/proc/PID/limits`, `-Xss`, NMT/OS usage | Identify stack/address-space/native limits; reserve headroom or tune appropriately |
| `direct.capacity` near limit while heap has free space | Time-series buffer pool/JMX, Netty/framework releases, `allocateDirect` stacks | Fix lifecycle/pooling, bound concurrency, consider direct cap if RAM suffices |
| Direct reservation nowhere near cap yet OS out of memory | RSS/cgroup, NMT, native library stats, allocator | Investigate other native usage; raising direct cap will not solve RAM exhaustion |
| `Java heap space`, post-GC heap climbs across steady load windows | GC logs, heap dump, retained heap, GC roots | Fix retention/leak or legitimate usage exceeding config |
| Heap OOME during huge data batches | Allocation profiling, element count, payload size, concurrency | Stream/chunk data, reduce buffering, control batch size; review heap size |
| Process OOMKilled with no Java exception | Cgroup `oom_kill`/OS logs, RSS, process limits | Balance total RSS against container limits rather than blaming heap immediately |

### Step 4 — Budget Memory with Headroom

For example, a container has a **1 GiB memory limit** yet the JVM is configured with `-Xmx768m`, a `256m` direct cap, and runs several hundred platform threads: this configuration **risks lacking headroom** for thread stacks, metaspace, code cache, JIT, GC, native libraries, page cache, and auxiliary work.

However, **do not sum `768 + 256 + N × Xss` and call the result RSS**: `-Xmx` is heap max, direct cap is a ceiling, stacks have distinct reserved/committed behavior, and some allocations are not immediately resident. Measure under peak load and set headroom suitable for the environment.

Tune the exact limiting knob:

- **Thread problem:** address thread growth drivers and task quotas first; do not raise heap just because the message says `OutOfMemoryError`.
- **Direct problem:** manage direct buffers and reservations; avoid raising direct cap past physical RAM.
- **Heap problem:** shrink the live set or size appropriately; do not blindly cut `-Xmx` to "leave room for native memory" when the heap is genuinely too small.

After fixing, rerun **the same workload** and compare post-GC heap, thread growth, direct pool, RSS, cgroup pressure, and errors/pauses.

## 9. Common Mistakes

1. **"Every `OutOfMemoryError` is caused by a full Java heap."** False: native threads, direct buffers, metaspace, and native allocators can fail independently.
2. **"Heap used is only 40%, so the process still has 60% RAM free."** False: heap used excludes direct buffers, native thread stacks, and other regions.
3. **"Increasing `-Xmx` fixes `unable to create native thread`."** No guarantee; inside a constrained container, enlarging the heap can shrink native headroom.
4. **"Lowering `-Xss` is always safe and solves all thread errors."** False: you can still hit task quotas, and smaller stacks risk `StackOverflowError`.
5. **"`DirectByteBuffer` is on the heap, so raising `-Xmx` is enough."** The wrapper is on the heap, while the payload is off-heap; check direct cap and native memory.
6. **"`-XX:MaxDirectMemorySize` caps all process native memory."** False: it only governs a scope of direct-buffer reservations, not all JNI/native allocations.
7. **"Just call `System.gc()` to cure direct buffer OOME."** Unreliable; it does not fix still-reachable buffers or mismanaged pools.
8. **"Many objects in a heap dump means a leak."** Insufficient: inspect retained heap/paths to GC roots and trends.
9. **"NMT summary is exact RSS or covers JNI."** False: each source has its own scope and semantics.
10. **"Exit code 137 is always Java heap OOME."** False: SIGKILL and OOM killer differ from Java exceptions; check OS/cgroup events.
11. **"Seeing `Threads` in Java MXBean tells you the exact OS task quota."** False: native JVM threads and other tasks share the cgroup.
12. **"Just raise `-Xmx`, direct cap, and thread pool together to be safe."** Within one memory limit, those budgets compete; measure first and tune purposefully.

## 10. Self-Check Questions

**Question 1:** `heap.used` is low, `Thread.start()` throws `unable to create native thread`, and `pids.current` is near `pids.max`. What should you do first?  
**Answer:** Investigate thread/task counts and quotas, check for thread pools/thread leaks, and identify the process's actual cgroup; raising `-Xmx` is not the direct answer.

**Question 2:** `ByteBuffer.allocateDirect` throws `Cannot reserve ... allocated: 134217728, limit: 134217728`. What does this tell you?  
**Answer:** Per the message's semantics, direct-buffer reservations hit a 128 MiB limit; inspect buffer lifecycles, pools/concurrency, and `MaxDirectMemorySize` before raising the cap.

**Question 3:** `OutOfMemoryError: Java heap space` occurs while RSS is still below the container's memory limit. Is this contradictory?  
**Answer:** No. `-Xmx` is a heap-specific limit, so the heap can run out before the process hits the container memory limit.

**Question 4:** NMT reports `Thread reserved=1 GiB`. Does that mean 1 GiB of physical RAM is immediately resident?  
**Answer:** No. Reserved virtual addresses do not equal RSS; check committed, OS RSS, and cgroup usage.

**Question 5:** Direct buffer cap is only 256 MiB, yet the OS reports high process RSS. Can you conclude direct buffers are the culprit?  
**Answer:** No. Check the JMX direct pool, NMT/OS metrics, and other native allocations; a cap is not current usage.

**Question 6:** A container was `OOMKilled` with no `java.lang.OutOfMemoryError` logged. Why?  
**Answer:** The kernel/container can kill the process externally on resource exhaustion before Java can throw or log an exception. Check `memory.events`/system logs and limit configs.

## Reference Documentation

- [Oracle JDK 17 — The `jcmd` Command (Thread.print, VM.native_memory, GC.heap_info)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — The `java` Command (`-Xmx`, `-XX:MaxDirectMemorySize`, `-XX:NativeMemoryTracking`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Memory Leaks and Java OutOfMemoryError](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle JDK 17 — Diagnostic Tools and Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
