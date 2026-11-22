# Heap, Metaspace, and Memory Management Behavior After Upgrading

When upgrading the JDK, an application may function properly yet consume memory differently than before: heap drops while process RSS grows, GC timings shift, metaspace reclaims memory differently after loading and unloading classes, or containers get killed even before `-Xmx` hits its limit. These phenomena do not necessarily mean the new Java "has a memory leak". They can come from the **JVM's memory layout and management**, the selected garbage collector, cgroup/container limits, newer libraries, thread counts, direct buffers, code cache, or class loader lifecycles.

In **Java Advance Compatibility Migration**, keep three questions distinct:

1. **Did actual memory usage change?** Measure heap used/committed, metaspace, native/off-heap, and RSS properly.
2. **Why did it change?** Due to workload, JDK/GC version, sizing ergonomics, application retention, class loading, or native allocations?
3. **How does it affect operational goals?** Does it raise p99 latency, pause durations, OOM frequency, restarts, CPU/throughput, or infrastructure cost?

This lesson explains heap, metaspace, and related memory regions; key changes across JDK generations; how to read logs/metrics, configure JVM options, and build a reproducible before–after comparison workflow. The goal is not always making "used memory" graphs look low, but **keeping the application stable, within memory budgets, and meeting latency/throughput targets under realistic load**.

## 1. Memory Map of a Java Process

A HotSpot application uses more memory regions than the Java heap alone.

~~~text
Container / host memory budget
|
+-- Java process (JVM)
|   |
|   +-- Java heap
|   |   +-- Objects / arrays
|   |   +-- Young/old regions or generations (depending on GC)
|   |
|   +-- Metaspace
|   |   +-- Class metadata
|   |   +-- Class-loader-related allocations
|   |
|   +-- Compressed class space (when applicable)
|   +-- JIT code cache
|   +-- Thread stacks + JVM/internal threads
|   +-- Direct buffers / off-heap memory
|   +-- JNI / FFM / third-party native allocations
|   +-- GC bookkeeping, symbols, arenas, compiler data
|   +-- Mapped files and shared/native libraries
|
+-- Other processes and container overhead
~~~

Some regions can be capped directly with JVM options; others cannot. Total memory recorded by the operating system or cgroup **is not simply `-Xmx`**, nor does it always equal the sum of dashboard numbers because reserved, committed, and resident are distinct concepts.

### 1.1. Quick Comparison Table

| Region | Contents | Signals/Tools | Relevant Options |
|---|---|---|---|
| Java heap | Java objects/arrays, including many buffer wrappers | `MemoryMXBean`, GC logs, `GC.heap_info`, heap dumps | `-Xms`, `-Xmx`, `MaxRAMPercentage` |
| Metaspace | Metadata of Java classes | Metaspace memory pools, `VM.metaspace`, NMT | `MaxMetaspaceSize`, `MetaspaceSize` |
| Compressed class space | Portion of class metadata when compressed class pointers are enabled | `VM.metaspace`, NMT | `CompressedClassSpaceSize` |
| Thread stacks | Call frames/stacks of Java/native threads | Thread count, NMT, OS metrics | `-Xss` |
| Code cache | Machine code compiled by the JIT | Code cache pools, NMT, code cache logs | `ReservedCodeCacheSize` |
| Direct buffers | Off-heap payload of direct `ByteBuffer` instances | `BufferPoolMXBean`, NMT/OS | `MaxDirectMemorySize` where applicable |
| JNI/FFM/native | Allocations managed by native code/libraries | Partial NMT, profilers/native tooling, OS | Depends on library/allocator |
| File mappings | Memory-mapped I/O, shared libraries | OS/proc metrics, partial NMT | Depends on mapping and workload |

**Note:** `MaxDirectMemorySize` does not cap every kind of native allocation. JNI libraries calling `malloc` or FFM off-heap arenas may not fall under the same cap as JVM-managed direct buffers.

## 2. Reserved, Committed, Used, and RSS Are Not the Same

This distinction is foundational when comparing JDKs.

- **Reserved virtual memory:** address space reserved ahead of time; it does not mean corresponding bytes sit in physical RAM.
- **Committed:** memory pages guaranteed or backed by the JVM/OS under its management model; not every page is necessarily resident immediately.
- **Used:** data currently in use as defined by each memory pool.
- **Resident Set Size (RSS):** process pages currently backed by physical memory, including resident heap, stacks, native allocations, and shared/mapped segments.
- **Container memory usage:** figures measured by cgroup/runtime; may include page cache or different accounting depending on OS/cgroup and dashboard.

Illustrative example:

~~~text
-Xmx                         = 2 GiB
Heap reserved                ≈ 2 GiB
Heap committed               = 1.4 GiB
Heap used                    = 0.8 GiB
Metaspace committed          = 0.2 GiB
Native + stack + code + misc = variable
Process RSS                  = 1.7 GiB
Container limit              = 2.5 GiB
~~~

These numbers explain concepts only; they are not an exact summation formula. In particular, compressed class space can **reserve a very large virtual address range** while keeping commit and RSS low. Seeing reserved memory grow on a new JDK without committed/resident growth is not enough to call it a memory regression.

### 2.1. Why Does the Heap Chart Show a Sawtooth Pattern?

Java heap typically rises between GC cycles because the application continuously allocates objects. After GC, unreachable objects are reclaimed and used memory drops. That behavior is normal.

What matters is the **post-GC trough** (approximating the live set), allocation rate, pause duration, and trends across repeated identical load cycles. Periodic rises and drops in heap used do not prove a memory leak.

## 3. Java Heap: Role and JVM Management

The heap stores most Java objects and arrays. The garbage collector decides when to reclaim unreachable objects, how to compact/relocate them, and how to partition regions for throughput or latency.

Key concepts:

- **Allocation rate:** volume of new object memory allocated per unit of time.
- **Live set:** objects still reachable after an appropriate collection cycle.
- **Object retention:** objects kept alive by references, caches, listeners, thread-locals, or static fields.
- **Young/old generations or regions:** how a collector groups objects by age or placement; details depend on the GC.
- **GC pause:** duration the application pauses during stop-the-world phases.
- **Concurrent GC:** much collection work runs concurrently with application threads, yet does not eliminate every pause phase.

Different collectors follow different designs. Never assume an Eden/Survivor/Old physical layout applies identically to every modern GC, especially ZGC.

### 3.1. `-Xms` and `-Xmx`

Example:

~~~bash
java -Xms512m -Xmx2g -jar application.jar
~~~

- `-Xms` is the initial heap size per JVM configuration.
- `-Xmx` is the maximum heap limit.
- The heap can grow or, with supporting GCs and policies, shrink committed memory at runtime.
- Setting `-Xmx` too low can trigger overly frequent GCs or `OutOfMemoryError: Java heap space`.
- Setting `-Xmx` near the container limit leaves insufficient budget for metaspace, thread stacks, direct buffers, JIT, and native allocations.

Avoid blindly setting `-Xms = -Xmx` for every system. That can stabilize heap sizing on some workloads yet prevents the JVM from returning unused committed heap; effects depend on GC, memory pressure, and latency requirements.

### 3.2. Percentage-Based Heap Sizing Relative to RAM

HotSpot JDKs support options such as:

~~~text
-XX:InitialRAMPercentage=...
-XX:MaxRAMPercentage=...
-XX:MinRAMPercentage=...
~~~

Illustrative example:

~~~bash
java -XX:MaxRAMPercentage=60.0 -jar application.jar
~~~

When no absolute heap cap is specified, the JVM can pick max heap as a percentage of memory detected by the runtime. In container-aware JDKs, that memory limit typically reflects container cgroup limits, though exact runtime and version behavior must be checked.

**Never treat `MaxRAMPercentage` as a total process limit.** It primarily controls heap sizing and does not govern metaspace or native allocations. When `-Xmx` is also supplied, check option precedence on the exact target JDK.

## 4. What Is Metaspace?

Metaspace manages most class metadata in HotSpot outside the Java heap. A loaded class has metadata describing methods, fields, constant pools, and runtime structures; these differ from class instances allocated on the heap.

Since **Java 8**, HotSpot replaced permanent generation (PermGen) with Metaspace. Hence, old flags such as `-XX:PermSize` and `-XX:MaxPermSize` are no longer suitable ways to control metadata on modern JDKs.

### 4.1. Metaspace Depends on Class Loader Lifecycles

When the application loads a class via a class loader, associated metadata is allocated. Class unloading can release metadata once reachability conditions for the class loader, classes, and related structures allow.

Common reasons metaspace grows:

- Applications with many dependencies and classes loaded at startup.
- ORM/DI/AOP frameworks generating proxy classes.
- Bytecode instrumentation or dynamic class generation.
- JSP/script engines compiling new classes.
- Dynamically loaded plugins/modules.
- Multiple application class loaders never getting released.
- Framework caches holding references to classes or class loaders after undeploy.

Metaspace growth during warm-up can be normal. However, if live class loaders and loaded classes grow without bound across plugin create/destroy cycles, that can indicate a **classloader leak**.

### 4.2. Compressed Class Space

When HotSpot uses compressed class pointers, part of class metadata sits in compressed class space. This area has its own reservation and accounting; when inspecting stats, distinguish `Metaspace` from `Compressed Class Space` depending on the tool.

A large reserved region does not mean all of it is committed. Never add reserved sizes directly into an RSS budget.

### 4.3. `MetaspaceSize` Differs from `MaxMetaspaceSize`

| Option | General Meaning | Caveat |
|---|---|---|
| `-XX:MetaspaceSize` | Threshold/initial mark influencing metadata-driven GC policy, not "allocating all metaspace upfront" | Setting it very high can delay metadata-driven collections |
| `-XX:MaxMetaspaceSize` | Sets upper limit on HotSpot metaspace | Setting too low can trigger OOM while loading classes |
| `-XX:CompressedClassSpaceSize` | Limits space reserved for compressed class metadata when enabled | Not equivalent to total metaspace or RSS |

Example:

~~~bash
java -XX:MaxMetaspaceSize=384m -jar application.jar
~~~

This is a **hypothetical limit** to illustrate syntax, not a universal recommendation for every application. Measure valid class metadata size under load and account for overhead/fragmentation before setting caps.

When hitting `OutOfMemoryError: Metaspace`, raising the limit only delays failure if the root cause is a classloader leak or unbounded dynamic class generation.

## 5. JDK 16 and Elastic Metaspace

**JEP 387 — Elastic Metaspace** arrived in JDK 16. Its goal is improving the ability to return unused metaspace back to the OS, reducing footprint in workloads that frequently load and unload class loaders.

This leads to an important comparison shift:

- On older JDKs, committed metaspace could remain high after unloading many classes.
- On JDKs with Elastic Metaspace, the JVM can uncommit freed metadata regions at finer granularity.
- Metaspace **used**, **committed**, and **reserved** curves can diverge over time even when active class counts stay roughly constant.
- Actual gains depend on the collector, class unloading, footprint, and specific workload.

Do not claim "JDK 16+ always uses X% less metaspace" without benchmarks. Elastic Metaspace is a mechanism improvement, not a guarantee that every application shrinks RSS.

### 5.1. Metaspace Shifts Do Not Automatically Prove a Classloader Leak

Seeing lower committed metaspace after a plugin-load cycle when moving from JDK 11 to 17 may reflect Elastic Metaspace. Conversely, if metaspace grows, inspect class counts/class loader lifetimes, frameworks, and workloads; never blame a leak on the new JDK from one chart alone.

### 5.2. Classloader Lifecycle Example

~~~text
Startup:
  10 000 classes loaded
  Metaspace grows

Plugin loaded:
  +2 000 classes
  Metaspace grows

Plugin unloaded, no references remain:
  classes may be unloaded in later GC cycles
  metaspace used falls
  committed pages may be uncommitted, depending on JVM/GC
~~~

If a static registry or thread keeps holding a reference to a plugin classloader, merely calling "unload plugin" in application logic is not enough for the JVM to reclaim class metadata.

## 6. Default Garbage Collector Can Change When Upgrading the JDK

One major source of difference is the **selected GC**. Never assume the new JDK picks the old collector unless launcher flags specify it explicitly.

Key milestones:

| JDK Milestone | Notable Change | Consequence to Verify |
|---|---|---|
| JDK 8 | Many HotSpot deployments default to Parallel GC in server-class configurations | Pauses, throughput, and heap layout form a distinct baseline |
| JDK 9 — JEP 248 | G1 becomes HotSpot default GC in common configurations | GC behavior and memory footprint can change even without code edits |
| JDK 14 — JEP 363 | CMS GC removed | Legacy `-XX:+UseConcMarkSweepGC` flag is rejected |
| JDK 15 — JEP 377 | ZGC becomes a production feature | Adds a low-pause GC option |
| JDK 21 — JEP 439 | Generational ZGC introduced | Verify mode/flags for the exact release |
| JDK 23 — JEP 474 | Generational ZGC becomes default mode when selecting ZGC | Do not treat old and new ZGC modes as identical config |
| JDK 24 — JEP 490 | Non-generational ZGC removed | Drop obsolete mode configuration |

These are HotSpot/OpenJDK milestones for orientation. Collector availability, defaults, and flags can vary by JDK distribution, platform, architecture, update/build, and startup options. **Always confirm the actual active GC via startup logs or `jcmd`.**

### 6.1. G1 Is Not "Zero-Pause"

G1 balances throughput and pauses using regions, collection sets, and concurrent phases. Still, it has stop-the-world pauses, and targets like `-XX:MaxGCPauseMillis` are **soft goals**, not hard SLAs.

If the new JDK yields better p99 latency at higher GC CPU cost, evaluate that trade-off carefully. If the heap holds many humongous objects, G1 exhibits specific behavior that requires inspecting GC logs.

### 6.2. ZGC Is Not the Default Answer for Every Workload

ZGC focuses on minimizing pause times and doing most collection work concurrently with the application. That can suit latency-sensitive services, yet does not guarantee better throughput, CPU, or RSS under all workloads.

Specifically, high allocation rates, tight heap headroom, or CPU contention with concurrent GC threads can degrade outcomes. Selecting G1, Parallel GC, ZGC, or another collector must follow **benchmarks and operational goals**, not collector reputation alone.

### 6.3. Shenandoah and Distribution-Specific Collectors

Shenandoah is available across many OpenJDK builds, yet never assume every build/distribution/platform shares identical GC option sets. Verify tool outputs and release docs for the target runtime.

## 7. Identifying Which JVM and GC Are Actually Running

Common inspection commands for HotSpot:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
java -Xlog:gc -version
~~~

`PrintFlagsFinal` prints many lines, so filter key flags for reporting. Non-HotSpot JVMs or older JDKs may support different options.

Against a running process:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`<pid>` is the process ID; substitute the actual PID. Never paste literal `<pid>` into a shell without substitution. Supported diagnostic commands can differ across JDKs/collectors; run `jcmd <pid> help` to see available commands.

**A dashboard label saying "G1" is not reliable if another environment runs a different collector.** At baseline, record JVM version, GC name, heap sizes, and startup arguments for each deployment.

## 8. GC Logging from Java 8 to Java 9+

Java 9 introduced Unified JVM Logging (JEP 158). Therefore, Java 8-style GC logging flags must be reviewed when switching releases.

Common JDK 8 example:

~~~bash
java -XX:+PrintGCDetails \
     -XX:+PrintGCDateStamps \
     -Xloggc:gc.log \
     -jar application.jar
~~~

On JDK 9+, you can use:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
     -jar application.jar
~~~

When log rotation is needed per JVM-supported options:

~~~bash
java "-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
     -jar application.jar
~~~

Quoting depends on the shell; on Windows/PowerShell adjust invocation syntax appropriately. Never assume all JDK 8 GC log flags are accepted verbatim by newer runtimes.

### 8.1. Signals to Extract from GC Logs

- Collector and heap configuration.
- Allocation/evacuation rates and young/mixed/full collections where meaningful for the GC.
- Pause counts, p50/p95/p99, and maximum pause duration.
- Percentage of JVM time/CPU spent on GC.
- Heap used before/after collection, committed/capacity.
- To-space exhaustion, evacuation failure, concurrent mode failure, or equivalent warnings.
- Class unloading and metaspace statistics if logging is enabled.
- Heap shrinking/uncommit if supported by the collector.

Do not compare raw "young GC" counts across two collectors as directly equivalent quantities. Region policies and naming differ; compare latency, throughput, GC overhead, and live set against common objectives.

## 9. Memory Ergonomics and Container Awareness

Many Java applications run inside Docker, Kubernetes, or cgroup-based runtimes. When moving from an older JDK 8 to a modern JDK, the JVM may **detect container RAM/CPU limits differently**. That affects default heap sizes, GC thread counts, JIT compiler threads, and sizing heuristics.

Modern HotSpot JDKs support container awareness; some JDK 8 updates also include backports. Do not form rules based solely on "Java 8" while ignoring exact update/build numbers.

### 9.1. Typical Issue: JVM Sees Host RAM Instead of Container RAM

Suppose the host has 64 GiB while the container is capped at 2 GiB. On an older runtime or misconfigured cgroup setup, the JVM may infer a memory budget unsuitable for the container.

Consequences:

- Default max heap exceeds what the container can hold.
- Too many GC/worker threads.
- Process gets cgroup OOM-killed even when Java never throws `OutOfMemoryError`.
- A JDK upgrade "accidentally" shifts default sizing, altering memory and CPU profiles.

Therefore, when comparing JDKs, **never hold container limits fixed and assume JVM memory layout stays identical**.

### 9.2. Inspecting Container Settings Perceived by the JVM

In HotSpot JDKs supporting relevant logging:

~~~bash
java -XshowSettings:system -version
java -XshowSettings:vm -version
~~~

You can inspect container logging when the JDK supports the tag:

~~~bash
java -Xlog:os+container=debug -version
~~~

`-XshowSettings`/logging output details can vary across JDKs. To be certain, record actual cgroup info from the container runtime/Kubernetes alongside `VM.flags` instead of trusting a single command.

### 9.3. Cgroup v1/v2 and CPU Limits

JDK updates differ in support for cgroup v1 and cgroup v2. If CI runs on cgroup v1 hosts while production uses cgroup v2, the JVM may interpret CPU/memory quotas differently.

This impacts:

- GC thread counts.
- Thread pool sizes chosen by frameworks via `availableProcessors()`.
- Concurrent GC scheduling.
- Default heap sizing.
- Latency stability when CPU gets throttled.

Do not test only with the same Docker image while ignoring cgroup/host kernel differences in the deployment environment.

## 10. Container Memory Budgeting: Do Not Let Heap Occupy the Entire Limit

A helpful **conceptual** formula:

~~~text
Container memory limit
    >= heap resident budget
     + metaspace / class metadata
     + code cache
     + thread stacks
     + direct / off-heap buffers
     + JNI / FFM / native libraries
     + JVM / GC internal memory
     + OS and container accounting headroom
~~~

This is not an exact arithmetic sum of raw metrics because shared mappings, page accounting, and reserved/committed/resident semantics differ. However, it reminds us that **`-Xmx` must never be treated as total process memory**.

Illustrative budget example for a 2 GiB container:

| Item | Illustrative Expected Value |
|---|---:|
| Max heap | 1.1 GiB |
| Metaspace + compressed class metadata | 180 MiB |
| Direct/off-heap buffers | 150 MiB |
| Thread stacks/code/JIT/GC/native | 300 MiB |
| Headroom for spikes/accounting | Remainder |

The figures above are **not a concrete configuration recommendation**. A Netty service, database driver with native buffers, or high-thread application may require a completely different budget. Measure realistically before setting limits.

### 10.1. CPU/Memory Limits Apply to the Workload, Not Just the JVM

A limit adequate for startup may run short during peak traffic. Tests require warm-up, concurrency, and representative datasets, including memory spikes during batches/compaction/reconfiguration.

If a pod restarts with status OOMKilled, correlate orchestration events, cgroup metrics, and JVM logs. Exit code 137 is a common symptom when a process receives SIGKILL, yet **by itself does not prove a kernel OOM kill** in every scenario.

## 11. Direct Buffers and Off-Heap Memory

Java NIO offers `ByteBuffer.allocateDirect()` to allocate direct buffers whose payload resides outside the standard Java heap. Wrapper objects and references to those buffers still live on the Java heap.

~~~java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
buffer.putInt(42);
buffer.flip();
System.out.println(buffer.getInt());
~~~

Direct buffers can speed up I/O or native interop, yet their footprint is not fully visible in heap dumps. When process RSS rises while heap used stays steady, inspect buffer pools, native allocations, and thread stacks.

### 11.1. MaxDirectMemorySize Does Not Cap All Native Memory

Depending on JDK/implementation:

~~~bash
java -XX:MaxDirectMemorySize=256m -jar application.jar
~~~

This option bounds JVM-managed direct memory of that type; it does not cap allocations from JNI, FFM, C libraries, memory-mapped files, or third-party native allocators.

A system can encounter `OutOfMemoryError: Cannot reserve ... direct buffer memory` or similar messages even with ample heap free. Increasing `-Xmx` will not fix the root cause and can sometimes increase container memory pressure.

### 11.2. Reading BufferPoolMXBeans

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d memoryUsed=%d totalCapacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity());
}
~~~

Pools such as `direct` and `mapped` appear depending on runtime. These figures help yet **do not capture every native allocation made by third-party libraries**.

## 12. Thread Stacks, Code Cache, and Native Overhead

### 12.1. Large Thread Counts Can Consume Substantial Memory

Each platform thread usually owns a stack. The JVM option `-Xss` adjusts Java thread stack size within HotSpot-supported bounds.

~~~bash
java -Xss1m -jar application.jar
~~~

This shows syntax only, not a universal optimum. With thousands of platform threads, stack reservation/commit and per-thread overhead can be significant. Actual resident bytes are not simply `thread count × -Xss`, yet thread count remains a key metric to watch.

Shrinking stack size too aggressively can cause `StackOverflowError` in deep call chains. With virtual threads on supporting JDKs, stack/scheduling mechanics differ from platform threads; never explain footprint changes via naive multiplication.

### 12.2. JIT Code Cache

The JIT compiler emits machine code to accelerate hot code, storing it in code cache outside the Java heap. When switching JDKs, optimizers, compilation policies, and code cache usage can differ.

Possible symptoms:

- Code cache full warnings.
- Performance degradation because the compiler stops optimizing.
- RSS grows without heap growth.
- Warm-up behavior shifts across JDKs or workloads.

Options such as `-XX:ReservedCodeCacheSize` should be evaluated alongside profilers and JDK docs; never blindly raise the cap just to suppress warnings without analysis.

## 13. Native Memory Tracking (NMT)

HotSpot Native Memory Tracking is an important tool for distinguishing heap from native memory. It must be enabled **at JVM startup**:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Or with deeper detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Detailed mode can add overhead and data volume; enable deliberately, especially in production environments.

### 13.1. Inspecting NMT with jcmd

After locating the target PID:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
~~~

NMT categorizes memory into groups such as Java Heap, Class, Thread, Code, GC, Compiler, Internal, and others; exact categories and accounting can vary by release.

To measure deltas across an activity window:

~~~bash
jcmd <pid> VM.native_memory baseline
# Run a workload or a plugin load/unload cycle.
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

In detail mode, corresponding detailed stats and diffs are available if supported by the JVM. Always run `jcmd <pid> help VM.native_memory` on the target release.

### 13.2. Limitations of NMT

- NMT carries overhead, so permanent detail mode is not always advisable.
- NMT does not necessarily cover third-party allocations using `malloc`, native libraries, or external allocators completely.
- NMT categories cannot always be summed directly to match RSS or cgroup usage.
- Some reserved regions can be very large while remaining non-resident.
- Rising NMT summary numbers do not prove a memory leak while workloads are warming up or filling bounded caches.

When NMT cannot explain RSS, OS tools, allocator profiling, native/heap profilers, or vendor diagnostics may be needed.

## 14. MemoryMXBean, MemoryPoolMXBean, and Class Loading Metrics

A service can export metrics using the Java Management API:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public final class JvmMemorySnapshot {
    public static void main(String[] args) {
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        System.out.println("Heap used: " + heap.getUsed());
        System.out.println("Heap committed: " + heap.getCommitted());
        System.out.println("Heap max: " + heap.getMax());
        System.out.println("Non-heap used: " + nonHeap.getUsed());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                System.out.printf("%s used=%d committed=%d%n",
                        pool.getName(),
                        usage.getUsed(),
                        usage.getCommitted());
            }
        }

        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("Loaded classes: "
                + classes.getLoadedClassCount());
        System.out.println("Total loaded classes: "
                + classes.getTotalLoadedClassCount());
        System.out.println("Unloaded classes: "
                + classes.getUnloadedClassCount());
    }
}
~~~

These values come from standard APIs, yet how the JVM partitions memory pools and names them can differ across collectors and JDKs. `getMax()` may return a negative value when maximum is undefined.

### 14.1. Reading Metrics Accurately

- Heap used approaching `-Xmx` briefly does not mean OOM is imminent.
- Non-heap used does not equate to total native RSS.
- Loaded class counts rising during startup/warm-up is normal.
- Total loaded counts accumulate historically rather than reflecting live classes.
- Rising unloaded counts show some classes unloaded, yet do not prove plugins no longer hold other references.

To check for leaks, measure across equivalent workload sequences after sufficient warm-up and collection cycles.

## 15. jcmd, JFR, and Heap Dumps for Controlled Investigation

Common HotSpot commands:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.metaspace
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
jcmd <pid> VM.flags
~~~

Not every JVM/version supports identical diagnostic command names or options. Confirm with `jcmd <pid> help`. Operations such as class histograms, heap dumps, or forcing GC can trigger safepoints, consume CPU/RAM, and degrade performance; never run casually during peak production traffic.

### 15.1. Heap Dumps

Configure automatic dumps on Java heap OOME on supporting JDKs:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/secure/dumps \
     -jar application.jar
~~~

Or capture an intentional dump:

~~~bash
jcmd <pid> GC.heap_dump /secure/dumps/heap.hprof
~~~

Heap dumps can contain passwords, tokens, customer records, payloads, and sensitive objects. Control access rights, disk space, retention duration, and data-handling workflows.

Heap dumps excel at diagnosing **object retention**, yet do not show full native/off-heap memory.

### 15.2. Java Flight Recorder

JFR captures data on GC, allocations, class loading, threads, safepoints, and many runtime events. Example:

~~~bash
jcmd <pid> JFR.start \
    name=memory-investigation \
    settings=profile \
    duration=5m \
    filename=/secure/recordings/memory.jfr
~~~

Exact syntax depends on the JDK and configuration. Verify with `jcmd <pid> help JFR.start`. JFR correlates memory pressure with allocation hotspots and GC pauses, though capture duration and overhead still require sizing.

### 15.3. Never Use System.gc() as Sole Evidence

Calling `System.gc()` does not guarantee the JVM performs a specific full collection. Behavior depends on collector, flags, and release. Even if one call lowers heap usage, that does not prove no leak exists.

To assess the live set, rely on GC logs, heap dumps, steady workloads, and multiple observation cycles rather than forcing GC once and comparing two numbers.

## 16. Distinguishing Types of OutOfMemoryError and OS Kills

| Symptom | Likely Cause Region/Layer | Priority Checks |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Insufficient heap or high object retention | Heap dump, GC logs, allocation/live set |
| `OutOfMemoryError: GC overhead limit exceeded` | Collector spends excessive time reclaiming very little, where policy applies | GC logs, allocations, live set, heap sizing |
| `OutOfMemoryError: Metaspace` | Metaspace cap or classloader retention | `VM.metaspace`, class/loader counts, JFR |
| `OutOfMemoryError: Compressed class space` | Class metadata portion in compressed class space | Metaspace diagnostics, class loading |
| Direct buffer memory OOME | Direct memory limit or exhaustion | Buffer pool metrics, direct memory config |
| Unable to create native thread | OS resource/memory or thread/process limit exhausted | Thread counts, stack settings, ulimit/container |
| Container OOMKilled | Total cgroup memory exceeded limit or OS killed process | Kubernetes events, cgroup/OS metrics, JVM logs |
| Process RSS rises while heap is steady | Metaspace, direct/native, thread stacks, code cache, mmap | NMT, OS metrics, buffer pools, class metrics |

Exact messages vary by runtime. Not every killed process logs a Java OOME; the kernel can terminate the process before the JVM ever writes a heap dump.

## 17. Case Study A: Heap Drops Yet Container Still OOMKilled

**Hypothetical scenario:**

- Application upgrades from an older JDK to a newer JDK.
- Dashboard shows lower post-GC heap used.
- Container memory limit stays unchanged.
- During peak hours, pods get OOMKilled.

### 17.1. Hypotheses to Test

1. New `-Xmx` inferred from cgroups differs from baseline.
2. Thread counts increased due to frameworks or CPU ergonomics.
3. Direct buffers or native SDK allocations grew.
4. Metaspace/class loading increased due to new framework/proxies.
5. JIT/code cache or internal GC overhead changed.
6. RSS includes committed heap pages while the dashboard showed only heap used.
7. Changes in native libraries, allocators, or memory mappings.
8. Peak-hour load and concurrency differed from baseline.

### 17.2. Investigation Plan

~~~text
Collect:
  - JDK version/vendor/build and GC
  - Effective -Xmx and cgroup memory limit
  - Heap used/committed/max
  - Metaspace and class counts
  - Thread count and stack config
  - Direct buffer pool metrics
  - NMT summary where enabled
  - Process RSS and container memory accounting
  - Peak traffic/time correlation
~~~

If heap used is low while direct memory or native allocations grew, raising `-Xmx` is usually the wrong fix. Buffer lifecycles, concurrency caps, or native library updates may be needed.

## 18. Case Study B: Metaspace OOME After Repeated Plugin Redeploys

**Hypothetical scenario:** a plugin system creates a new class loader per plugin version. After each reload, heap still drops yet metaspace and loaded class counts climb until OOME.

Causes to inspect:

- Static singletons holding references to classes from old plugins.
- Background threads never stopped, with context class loaders still pointing to plugins.
- Registries/listeners/callbacks left unregistered.
- ThreadLocals retaining values or class loaders.
- Framework caches storing `Class`, proxies, or generated classes.
- A dependency continuously creating class loaders without closing their lifecycle.

### 18.1. Remediation

1. Count live class loaders and classes across each reload cycle.
2. Trace GC roots/references retaining class loaders via heap dumps and profilers.
3. Stop threads, unregister listeners, clear caches, and close resources properly per lifecycle.
4. Confirm class unloading actually occurs.
5. Re-check metaspace used/committed and RSS across multiple cycles.
6. Only then tune `MaxMetaspaceSize` if additional headroom is genuinely needed.

**Raising the metaspace cap is no substitute for fixing a classloader leak.** Elastic Metaspace can only reclaim freed metadata; as long as a class loader stays reachable, its metadata must remain.

## 19. Case Study C: Default GC Change Shifting p99 Latency

**Hypothetical scenario:** a service moves from JDK 8 to JDK 17 without specifying a GC. Previously the older JVM typically used Parallel GC, whereas the newer JDK uses G1 under common HotSpot defaults.

Comparisons may show:

- Different stop-the-world pause patterns.
- Different GC CPU overhead.
- Different young/old region sizes.
- Shifted throughput and p99 latency.
- Different committed heap and post-GC memory.

### 19.1. How to Evaluate Properly

Two experiment modes are needed:

- **Default comparison:** hold workloads, containers, and basic JVM knobs equivalent to see real default upgrade behavior.
- **Controlled comparison:** evaluate alternative collectors or heap headroom within support policies to identify the optimal choice.

Never conclude "G1 is slower than Parallel GC" from one workload or one sample. Pick the collector by p99 latency, throughput, GC CPU, RSS, and stability across load levels.

## 20. JFR and GC Logs: Reading Allocation Pressure vs Memory Leaks

Two systems can both use 1 GiB of heap yet show very different profiles:

| Chart Pattern | Initial Interpretation | Next Check |
|---|---|---|
| Heap grows between GCs then drops to steady trough | Normal allocation under steady load | GC overhead and latency |
| Post-GC trough climbs across equivalent cycles | Likely growing retained objects | Heap dump diff, allocation sites, GC roots |
| RSS grows while heap used and committed stay steady | Native/off-heap/threads/metaspace/mapped | NMT, OS metrics, buffer pools |
| Metaspace used climbs with plugin/class-loader counts | Class loading or retention | Class unloading and loader lifetimes |
| Frequent GCs, short pauses, poor throughput | Small heap or high allocation rate | Allocation profiling, heap sizing, GC options |
| Rare GCs but very long pauses under memory pressure | Mismatched collector/workload/headroom | GC log phases, safepoints, load |
| RSS grows post-startup then plateaus | Warm-up, class loading, JIT, caches | Observe long enough before calling a leak |

Calling something a **memory leak** requires evidence of resources failing to release as expected, not merely memory rising during a few minutes of warm-up.

## 21. Designing a Before–After JDK Upgrade Comparison

A good benchmark controls variables and answers a specific question.

### 21.1. Holding Baseline Factors Constant When Possible

- Same source commit and artifact, if binaries run on both JDKs.
- Same dependency graph and schema.
- Same request mix, input datasets, and concurrency.
- Same container memory/CPU limits.
- Same OS/architecture and cgroup mode if possible.
- Same warm-up and measurement duration.
- Same logging/monitoring policies.
- Same background load profile from databases/external services.

If the framework must upgrade alongside the JDK for compatibility, the report must explicitly note that **two stacks are being compared**, rather than blaming every difference on the JVM.

### 21.2. Minimum Metric Set

| Group | Metrics to Save |
|---|---|
| Service | Throughput, error rate, p50/p95/p99 latency |
| GC | Collector, pause count/duration, GC CPU/time, full GCs |
| Heap | Used/committed/max, live-set trend, allocation rate |
| Metaspace | Used/committed, classes loaded/unloaded, class loader count when available |
| Native | RSS, NMT summary, direct buffers, thread count, code cache |
| Container | Memory working set/usage, cgroup limit, OOM events, CPU throttling |
| Runtime | JDK feature/update/vendor, flags, OS/arch, container image |
| Stability | Restarts, OOMEs, native crashes, long safepoints |

Capture data across multiple runs to avoid concluding from random variance. Ensure metrics share identical definitions and units when comparing, especially when changing GCs.

### 21.3. Defining Go/No-Go Criteria Before Running

Illustrative example:

~~~text
Baseline:
  Java 17, G1, 4 GiB container
Candidate:
  Java 21, G1, same workload and limits

Criteria:
  - p99 latency does not exceed SLO threshold
  - Zero OOMKilled/OOME under representative load test
  - Peak RSS stays within memory budget and headroom
  - GC pauses/CPU remain within budget
  - Metaspace and classloader count stabilize after warm-up
  - No functional/data regressions
~~~

These are example criteria, not test results from a real application. Numerical thresholds must come from the project's SLOs and resource budgets.

## 22. Configuring the JVM for the Environment Instead of Copying Old Flags

A JDK 8-style startup command may carry legacy GC, PermGen, and logging flags:

~~~text
-XX:+UseConcMarkSweepGC
-XX:MaxPermSize=256m
-XX:+PrintGCDetails
-Xloggc:/logs/gc.log
~~~

When moving to JDK 17/21/25, some flags are removed, obsolete, or replaced by newer logging mechanisms. **Never copy the entire old flag set verbatim and ignore warnings.**

Process:

1. Document all current JVM options and the purpose of each.
2. Group them into heap sizing, metaspace, GC selection, logging, diagnostics, native access, and security.
3. Check option support against the target JDK.
4. Drop obsolete flags and migrate logging to Unified Logging if needed.
5. Start with less manual tuning where test coverage permits.
6. Measure baseline under sensible defaults.
7. Add tuning flags only to address measured issues with a clear hypothesis.
8. Record every flag edit and test outcome.

Tuning that worked well on JDK 8 does not automatically fit JDK 21's collectors and ergonomics. Subtle JVM flag edits also obscure regression analysis when bundled with dependency and schema upgrades.

## 23. Example Configuration for a Service in a Container

An illustrative modern-JDK configuration:

~~~bash
java \
  -Xms512m \
  -Xmx1536m \
  -XX:+UseG1GC \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/secure/dumps \
  "-Xlog:gc*:file=/secure/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar application.jar
~~~

**Do not treat the values above as a ready-to-apply recommendation.** Reserve enough budget for metaspace, direct/native buffers, thread stacks, and GC internals. With a 2 GiB container limit and a 1.5 GiB heap, headroom can still run short for high-thread or native-memory-heavy applications.

Where possible, verify actual active flags via `jcmd <pid> VM.flags` and startup logs. Container entrypoints or deployment platforms may append or override JVM arguments.

## 24. Commonly Misinterpreted Failures

**"Heap used is low, so the process cannot OOM."** False. Total RSS/cgroup usage also includes metaspace, stacks, direct memory, native allocations, and JVM overhead.

**"Setting `-Xmx` equal to the container limit uses all RAM efficiently."** This easily triggers OOMKilled due to missing off-heap headroom.

**"Reserved memory equals used RAM."** False. Reserved can be virtual address space; check committed and resident memory.

**"Rising heap means a leak."** Not necessarily; it may reflect warm-up, bounded caches, or normal allocation churn.

**"On Metaspace OOME, just raise MaxMetaspaceSize."** That can mask a classloader leak or uncontrolled class generation.

**"PermGen flags still govern metaspace on modern Java."** No. PermGen was replaced by Metaspace in Java 8.

**"Elastic Metaspace always cuts RAM across every app."** No. Gains depend on workloads and whether metadata actually gets released.

**"Newer JDKs use the same old GC when no flag is set."** Cannot be assumed; HotSpot changed the default GC starting in JDK 9 in common configurations.

**"MaxGCPauseMillis is a hard pause cap."** No. It is a soft goal for supporting collectors.

**"ZGC is always faster than G1."** Depends on workload, CPU availability, heap headroom, throughput, and SLOs.

**"MaxDirectMemorySize limits all native allocations."** No. JNI/FFM and third-party `malloc` calls may bypass that cap.

**"A GC heap dump suffices to investigate rising RSS."** No. Heap dumps do not cover native/off-heap allocations thoroughly.

**"NMT shows every native allocation."** Not completely; allocations outside JVM allocators may require native profilers.

**"Pod exit 137 definitely means Java OOME."** No. OS/container events and logs are required to identify the cause.

**"Passing CI tests means production memory is safe."** Traffic load, cgroups, container limits, and warm-up can differ.

## 25. JVM Memory Migration Checklist

- [ ] Recorded source/target JDK feature/update/build, vendor, and OS/architecture.
- [ ] Verified actual active GC and JVM flags in each environment.
- [ ] Distinguished heap used/committed/reserved from RSS/container memory.
- [ ] Recorded `-Xms`, `-Xmx`, and RAM percentages if used.
- [ ] Reserved headroom for metaspace, thread stacks, direct/native memory, and code cache.
- [ ] Checked container cgroup limits, CPU quotas, and JVM container awareness.
- [ ] Checked obsolete or removed JDK/GC options; dropped old CMS flags.
- [ ] Selected GC based on latency/throughput/RSS rather than legacy habit.
- [ ] Configured GC logs using syntax supported by the target JDK.
- [ ] Monitored metaspace, class counts, and classloader lifecycles.
- [ ] Evaluated Elastic Metaspace impact for workloads that unload classes.
- [ ] Checked direct buffer pools and native allocations when RSS diverges from heap.
- [ ] Checked thread counts, `-Xss`, code cache, and native libraries.
- [ ] Enabled NMT where needed and understood its overhead/tool limits.
- [ ] Prepared plans for JFR, heap dumps, and access controls for sensitive data.
- [ ] Distinguished Java OOME from kernel/container OOMKilled.
- [ ] Ran benchmarks with warm-up, representative load, and repeated trials.
- [ ] Recorded p95/p99 latency, throughput, GC pauses, peak RSS, and cgroup events.
- [ ] Documented effects of non-JDK dependency/framework changes.
- [ ] Defined go/no-go criteria, rollout, and rollback/roll-forward plans for regressions.
- [ ] Marked untested environments clearly rather than assuming PASS.

## 26. Official References by JDK Milestone

Reference sources on HotSpot and GC changes:

- **JEP 122 — Remove the Permanent Generation (Java 8):** https://openjdk.org/jeps/122
- **JEP 158 — Unified JVM Logging (Java 9):** https://openjdk.org/jeps/158
- **JEP 248 — Make G1 the Default Garbage Collector (Java 9):** https://openjdk.org/jeps/248
- **JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector (Java 14):** https://openjdk.org/jeps/363
- **JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Java 15):** https://openjdk.org/jeps/377
- **JEP 387 — Elastic Metaspace (Java 16):** https://openjdk.org/jeps/387
- **JEP 439 — Generational ZGC (Java 21):** https://openjdk.org/jeps/439
- **JEP 474 — ZGC: Generational Mode by Default (Java 23):** https://openjdk.org/jeps/474
- **JEP 490 — ZGC: Remove the Non-Generational Mode (Java 24):** https://openjdk.org/jeps/490
- **Java SE `java`/`jcmd` tool documentation:** consult the documentation matching the target JDK at https://docs.oracle.com/en/java/javase/

These links pinpoint milestone changes; for real deployments, still consult documentation for the selected JDK's distribution, GC flags, and updates. Never treat benchmark results from a JEP as measurements for your own system.

## Conclusion

**Heap, metaspace, and native memory are separate regions, and their management behavior can change substantially after upgrading the JDK.** From the G1 default switch, CMS removal, and Elastic Metaspace improvements to ZGC and container ergonomics, a newer JVM can change GC pauses, heap commitment, returning metadata to the OS, or memory budget calculations — even without changing business code.

To evaluate performance compatibility, measure **heap used/committed/max, metaspace, direct/native memory, thread stacks, RSS, GC, and container limits** under identical workloads. When hitting OOM, identify the exact category: Java heap, metaspace, direct buffers, native threads, or cgroup OOMKilled; each demands different diagnostics and fixes. Final conclusions must rest on SLOs, peak RSS, GC behavior, stability under load, and reproducible per-JDK evidence — not a single heap chart or JVM flags copied from older versions.
