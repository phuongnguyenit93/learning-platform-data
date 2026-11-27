# Native Memory Tracking for Monitoring Native Memory

## 1. What Problem Does Native Memory Tracking Solve?

A Java process uses more memory than just the Java heap. Beyond objects and arrays created by the application, the JVM also uses native memory for class metadata, thread stacks, JIT-compiled code, the garbage collector, internal structures, and other runtime activities. JNI libraries or third-party native libraries can also allocate memory outside the heap.

As a result, you may encounter situations such as:

- Heap used remains low while process RSS climbs continuously.
- A container approaches its memory limit without an `OutOfMemoryError: Java heap space`.
- Increasing thread counts raise memory usage even while the heap stays nearly constant.
- Class loaders or dynamic proxies drive up metaspace usage.
- After increasing the heap size, the container gets OOM-killed sooner because native memory no longer has enough headroom.

**Native Memory Tracking (NMT)** is a HotSpot JVM diagnostic feature that tracks certain native memory categories managed by the JVM itself. NMT reports aggregated figures by category and, in detailed mode, by call site or virtual memory region. It helps reveal where the JVM reserves and commits memory and how usage changes over time.

NMT is neither a heap profiler nor a tool that measures total RSS. Combine NMT with heap metrics, GC logs, heap dumps, OS metrics, and container metrics for a complete picture.

## 2. Distinguishing Java Heap, Native Memory, and RSS

### 2.1. Core Concepts

| Concept | Meaning | Appropriate Observation Source |
|---|---|---|
| Java heap | Region storing application objects and arrays | Heap MXBeans, GC logs, heap dumps, JFR |
| Native memory | Off-heap memory used by the JVM, JDK, or native libraries | NMT combined with OS tools |
| Reserved memory | Virtual address space reserved by the JVM for a purpose | NMT, VM diagnostics |
| Committed memory | Memory regions committed by the JVM for use via VM/OS mechanisms | NMT, VM diagnostics |
| RSS | Process memory pages currently resident in physical RAM | OS process metrics |
| Container memory usage | Memory consumption according to cgroup/container runtime | Container metrics, cgroup files |

These metrics are not interchangeable. For example, a large virtual address range may be reserved without being committed; committed memory is also not necessarily entirely resident in RAM at the time of measurement.

### 2.2. Process-Level Memory Diagram

```text
Java process
|
+-- Java heap
|     +-- Objects and arrays
|
+-- JVM native memory
|     +-- Metaspace / class metadata
|     +-- Thread stacks
|     +-- JIT code cache
|     +-- GC structures
|     +-- Compiler / runtime / internal
|     +-- NMT bookkeeping
|
+-- Native memory outside full NMT scope
|     +-- JNI / native libraries
|     +-- Certain JDK class library allocations
|     +-- Application-managed native allocators
|
+-- OS-managed mappings and resources
      +-- Shared libraries / mapped files
      +-- Resident pages and page cache as accounted by the OS
~~~

NMT focuses on allocations managed by the HotSpot VM. This scope is valuable but does not cover all memory used by the process. If total RSS is much larger than the NMT categories, that signals a need to inspect allocations outside NMT's scope or how the OS accounts for memory.

### 2.3. Reserved and Committed Are Not RSS

For example, if a category shows:

```text
reserved=512MB, committed=128MB
```

That indicates the JVM reserved 512 MB of virtual address space and committed 128 MB under runtime mechanisms. Do not conclude the process occupies 512 MB of physical RAM. Nor should you conclude RSS equals 128 MB.

RSS depends on pages faulted into RAM, shared mappings, heap pages, native allocations, and OS accounting. Comparing NMT alongside RSS/cgroup usage over time is far more informative than comparing two isolated numbers.

## 3. Enabling Native Memory Tracking in Java 17

### 3.1. NMT Is Off by Default

On HotSpot, NMT is disabled by default. Enable it at JVM launch with a flag:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Or enable detailed mode:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Levels:

| Value | Tracking | When to Use |
|---|---|---|
| `off` | Disables NMT | Production runtimes not needing NMT metrics |
| `summary` | Aggregated statistics by category | Monitoring native memory trends with lower overhead than detail |
| `detail` | Granular statistics with call sites and virtual memory regions | Deep investigation when summary is insufficient |

If unspecified, the default value is `off`.

### 3.2. Choosing summary or detail

`summary` is usually a sensible starting point:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

This mode shows which categories consume the most native memory and how reserve/commit figures change.

`detail` provides additional information about specific call sites or mappings:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Detail is helpful when you need to pinpoint allocations within a category. Output can be much longer and harder to read, and it incurs extra overhead.

### 3.3. NMT Must Be Enabled at JVM Startup

NMT cannot be enabled for the first time via `jcmd` after a JVM is already running without tracking. The tracking level must be chosen at process startup:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

If you need to switch from `summary` to `detail`, plan a JVM restart with the new flag. The `jcmd VM.native_memory shutdown` command can turn off active NMT; do not treat it as a way to switch to detail or re-enable tracking. To change the tracking level, restart the JVM with the desired configuration.

Account for this in deployment planning: enabling NMT before an investigation is needed avoids waiting for an emergency restart.

### 3.4. Verifying NMT Is Enabled

Inspect final JVM flags:

```shell
jcmd <pid> VM.flags
```

Or check default/ergonomic flags:

```shell
java -XX:+PrintFlagsFinal -version
```

Look for `NativeMemoryTracking` in the output. You can also query directly with `jcmd`:

```shell
jcmd <pid> VM.native_memory summary
```

If NMT was not enabled at startup, the command will report that Native Memory Tracking is not enabled. In that case, restart the JVM with `-XX:NativeMemoryTracking=summary` or `detail`.

## 4. Key jcmd Commands

### 4.1. Printing Summary Statistics

```shell
jcmd <pid> VM.native_memory summary
```

You can specify the display scale:

```shell
jcmd <pid> VM.native_memory summary scale=MB
```

Commonly supported scales are `KB`, `MB`, and `GB`. Do not compare raw numeric values across samples without checking units if two captures used different scales.

### 4.2. Printing Detailed Statistics

```shell
jcmd <pid> VM.native_memory detail
```

This command requires the JVM to have been started with `NativeMemoryTracking=detail`. Output can include call sites and virtual address regions. Use it once you already know which category to investigate; avoid starting by reading a huge `detail` output without a specific question.

### 4.3. Creating a Baseline

NMT supports capturing a baseline for comparison:

```shell
jcmd <pid> VM.native_memory baseline
```

The baseline records a reference state for subsequent diff queries. Typically, create the baseline after application startup and warm-up complete if your goal is to monitor growth during steady state.

### 4.4. Comparing Against the Baseline

Summarize changes since the baseline:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

With NMT detail:

```shell
jcmd <pid> VM.native_memory detail.diff scale=MB
```

`summary.diff` and `detail.diff` highlight categories or call sites that increased or decreased since the baseline. Capturing multiple snapshots on a consistent interval helps identify trends.

### 4.5. List of Common Operations

| Purpose | Command |
|---|---|
| View summary | `jcmd <pid> VM.native_memory summary` |
| View summary in MB | `jcmd <pid> VM.native_memory summary scale=MB` |
| View detail | `jcmd <pid> VM.native_memory detail` |
| Record baseline | `jcmd <pid> VM.native_memory baseline` |
| View summary delta | `jcmd <pid> VM.native_memory summary.diff scale=MB` |
| View detail delta | `jcmd <pid> VM.native_memory detail.diff scale=MB` |
| Shut down active NMT | `jcmd <pid> VM.native_memory shutdown` |

NMT does not provide a runtime operation to switch from `off` to `summary`/`detail`. Shutdown is not a re-enable mechanism either; restart to change tracking levels.

## 5. Reading NMT Output

### 5.1. Example Summary Output

Actual output depends on JDK build, collector, flags, and workload. An illustrative snippet:

```text
Native Memory Tracking:

Total: reserved=2450000KB, committed=820000KB

-                 Java Heap (reserved=1048576KB, committed=524288KB)
                            (mmap: reserved=1048576KB, committed=524288KB)

-                     Class (reserved=1100000KB, committed=45000KB)
                            (classes #...)
                            (  metadata: reserved=..., committed=...)

-                    Thread (reserved=120000KB, committed=120000KB)
                            (thread #...)
                            (stack: reserved=..., committed=...)

-                      Code (reserved=..., committed=...)
-                        GC (reserved=..., committed=...)
-                  Compiler (reserved=..., committed=...)
-                  Internal (reserved=..., committed=...)
-                    Symbol (reserved=..., committed=...)
-        Native Memory Tracking (reserved=..., committed=...)
```

This is a structural example for learning how to read output, not predictive numbers for every application. Categories and subfields may vary across HotSpot releases.

### 5.2. Total

`Total` shows overall reservations and commitments tracked by NMT within its scope. Do not equate `Total committed` with process RSS or container memory usage.

If `Total committed` grows, check which category contributes to the growth. If RSS grows while NMT Total stays nearly flat, investigate allocations outside NMT's scope or OS mappings/memory.

### 5.3. Java Heap

NMT displays the Java heap reservation/commitment as a category. That does not mean NMT analyzes individual objects inside the heap or identifies which objects hold references.

To analyze objects, dominator trees, retained sizes, or reference paths:

- Use a heap dump.
- Use Java Flight Recorder for appropriate allocation/GC events.
- Use a profiler or heap analysis tool.

### 5.4. Class and Metaspace

The class/metaspace category can grow when an application loads many classes, generates proxies, or retains multiple class loaders. Inspect:

- Number of loaded classes.
- Metaspace committed/used via `MemoryPoolMXBean`.
- Whether class loaders are being reclaimed.
- Whether hot reload, dynamic class generation, or repeated redeployments occur.

Do not conclude a memory leak simply because class count rises during startup; frameworks routinely load classes during warm-up. Observe trends after the workload stabilizes.

### 5.5. Thread

The Thread category reflects thread-related memory, including stack reservation/commitment as reported by HotSpot. If thread count rises continuously, native memory can grow even when the heap stays unchanged.

Cross-check:

- Live thread count.
- Stack size configured via `-Xss`.
- Thread dumps.
- Thread pool sizing.
- Thread leaks or threads spawned per request without terminating.

Do not merely shrink `-Xss` to solve thread explosion. Inspect thread counts and lifecycles first.

### 5.6. Code, GC, Compiler, and Internal

These categories can reflect:

- Code cache and JIT-generated code.
- Garbage collector internal structures.
- Compiler/JIT memory.
- Other internal runtime structures.

Category names and breakdowns can change between HotSpot releases. Inspect output from the exact JDK 17 runtime in use and its accompanying documentation rather than relying on a fixed list from another runtime.

### 5.7. NMT Category

NMT itself allocates memory to store tracking metadata. Hence the output includes a Native Memory Tracking category. The tracking tool incurs its own memory and CPU cost; measurements are not completely free.

## 6. Reserved, Committed, and malloc in Detail Mode

### 6.1. Virtual Address Regions

The JVM may reserve a large virtual address region upfront and commit pages gradually on demand. Reservation does not mean the entire region is in use or occupying physical RAM.

Example:

```text
reserved=1024MB
committed=256MB
```

This happens for regions that need room to expand later. When reading NMT, pay attention to both columns.

### 6.2. malloc and mmap

In detail mode, output may describe allocations via mechanisms such as `malloc` or `mmap`, along with associated call sites.

- `malloc`: native heap allocations through the allocator.
- `mmap`: memory regions mapped into the process address space.

Not every `mmap` region corresponds to an amount of RSS equal to its reservation. Pages may remain untouched, be shared, or be managed separately by the OS.

### 6.3. Call Sites Help Narrow Down Causes

Detail mode can reveal which group of call sites drives a category's growth. For example, if thread stacks grow alongside thread count, investigate thread creation. If class/metaspace grows alongside class loader count, inspect class loading.

Call sites in NMT are HotSpot-internal allocation traces, not full Java stack traces for every object or native allocations inside third-party libraries.

## 7. Baselining and Diffing to Detect Growth

### 7.1. Choosing When to Take a Baseline

A practical workflow:

1. Start the JVM with NMT `summary` or `detail`.
2. Wait for application startup to complete.
3. Run warm-up so JIT, frameworks, and connection pools stabilize.
4. Record the baseline.
5. Run a representative workload.
6. Capture `summary.diff` periodically.
7. If needed, restart in `detail` mode to investigate specific categories/call sites.

If you take the baseline immediately at JVM startup, the diff will include startup, class loading, and JIT warm-up. That fits startup measurement goals, but not detecting abnormal post-warm-up growth.

### 7.2. Example Investigation Session

```shell
# 1. Start with summary tracking
java -XX:NativeMemoryTracking=summary -jar app.jar

# 2. In another terminal, find PID and view summary
jcmd -l
jcmd <pid> VM.native_memory summary scale=MB

# 3. After warm-up, create baseline
jcmd <pid> VM.native_memory baseline

# 4. Run workload for a period of time

# 5. Capture delta
jcmd <pid> VM.native_memory summary.diff scale=MB
```

To measure another phase, record a fresh baseline before that phase and capture a diff afterward. Log timestamps, workloads, replicas, container limits, and JVM flags so cross-run comparisons stay meaningful.

### 7.3. Reading Diffs Correctly

Suppose a diff output shows:

```text
Thread   +40MB committed
Class    +12MB committed
Code      +5MB committed
Java Heap +80MB committed
```

This is purely illustrative. Ask:

- Did thread count increase proportionally?
- Were additional classes loaded due to workload or proxies?
- Is JIT warm-up still continuing?
- Is heap commitment growth expected under normal workload?
- Does growth continue after the workload stops?

A single increase does not prove a leak. Memory naturally grows during startup or warm-up and then plateaus. Warning signs are continued growth across repeated cycles of the same workload, failure to drop after work finishes, or correlation with an unreleased resource.

### 7.4. Combining summary and detail

Use a two-step approach:

- **Summary:** identify which category has significant growth.
- **Detail:** investigate the narrowed-down category deeply.

You do not need `detail` enabled on every production workload upfront if its overhead or output size is unsuitable. You can use a canary instance under representative load for deeper investigation.

## 8. NMT Does Not Track All Native Memory

### 8.1. Tracking Scope

NMT is designed to track internal HotSpot allocations. It is not a comprehensive monitor of every byte used by the process.

Allocations that may not be fully tracked by NMT include:

- Native memory allocated directly by third-party libraries.
- Allocations managed directly by the application's JNI code.
- Certain allocations made by JDK class libraries outside tracked HotSpot paths.
- Shared mappings and OS-managed overhead accounted separately.

Exact coverage depends on the allocation path and runtime version. When native libraries are present, do not assume NMT Total explains the entire RSS gap.

### 8.2. Direct ByteBuffers

Direct buffers warrant special attention:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(16 * 1024 * 1024);
```

The direct memory region resides off-heap. The `ByteBuffer` wrapper object lives on the heap, while the underlying buffer is managed through native/JDK mechanisms. Do not assume NMT categorizes all direct buffer allocations under a dedicated category across every release.

To inspect direct/mapped buffer pools exposed by the JVM, use `BufferPoolMXBean`:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d, used=%d, capacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity()
    );
}
```

These metrics supplement direct/mapped buffers; compare them against NMT and RSS.

### 8.3. JNI and Native Libraries

A JNI library can call `malloc`, allocate native objects, open handles, or map memory directly. If the library does not go through NMT-tracked paths, NMT will not fully display those allocations.

When suspecting JNI/native libraries:

- Check the library's documentation and lifecycle APIs.
- Verify whether native allocations and frees are balanced.
- Use platform-appropriate native profilers or tools.
- Compare RSS/cgroup usage against NMT Total.
- Run repeated load tests to see if memory grows per invocation or stabilizes.

Do not conclude “there is no native leak” just because NMT summary shows no growing category.

## 9. Combining NMT with Other Tools

### 9.1. Heap Metrics and Heap Dumps

If post-GC Java heap usage rises, NMT does not show which objects retain memory. Use:

- `MemoryMXBean` and memory pool metrics.
- GC logs.
- Heap dumps with `-XX:+HeapDumpOnOutOfMemoryError`.
- Heap analysis tools to inspect dominators and retained sizes.

NMT adds the JVM native perspective; it does not replace heap analysis.

### 9.2. JFR

Java Flight Recorder captures allocations, GC, threads, locks, and relevant runtime events. JFR helps correlate application behavior with memory changes and latency.

JFR is not a direct replacement for NMT on native allocations. Select events and tools matching your diagnostic question.

### 9.3. Operating System Tools on Linux

Common commands:

```shell
ps -o pid,rss,vsz,comm -p <pid>
cat /proc/<pid>/status
cat /proc/<pid>/smaps_rollup
pmap -x <pid>
```

General meanings:

- `RSS`: resident set size.
- `VSZ`: virtual address space size.
- `/proc/<pid>/status`: process memory and thread details.
- `smaps_rollup`: aggregated memory mapping summary.
- `pmap`: process memory map.

Field names and availability depend on the kernel and Linux distribution. These commands read OS metrics; they do not automatically attribute allocations to Java objects or JVM categories.

### 9.4. Container/Cgroup Metrics

With Linux cgroup v2, two common files are:

```text
/sys/fs/cgroup/memory.current
/sys/fs/cgroup/memory.max
```

With cgroup v1, common filenames are:

```text
memory.usage_in_bytes
memory.limit_in_bytes
```

Actual paths depend on mount namespaces and the container runtime. Use Kubernetes/container platform metrics if available; avoid hardcoding cgroup v1 paths across environments.

Cross-reference:

| Source | Question Answered |
|---|---|
| NMT | Which categories is HotSpot reserving/committing native memory in? |
| Heap metrics | How much heap is used/committed? |
| Heap dump | Which objects retain heap? |
| JFR | When did allocation/GC/thread behavior occur? |
| OS RSS/smaps | How much memory is resident/mapped for the process? |
| cgroup metrics | How much is the container consuming relative to its limit? |
| BufferPoolMXBean | How much are direct/mapped buffer pools using? |

## 10. Overhead and Production Usage

### 10.1. NMT Has Overhead

NMT stores tracking metadata and updates statistics when the JVM allocates or frees memory regions. This can increase CPU and memory overhead.

Actual cost depends on:

- `summary` vs. `detail` tracking level.
- Allocation frequency and patterns.
- JDK build and platform.
- Workload and number of threads/categories.

`detail` generally carries higher overhead than `summary`. Do not assume a fixed overhead percentage for every application; benchmark on a representative workload and measure both latency and memory.

### 10.2. Choosing an Activation Strategy

Operational options:

| Environment | Strategy |
|---|---|
| Local development | Enable summary or detail while learning or investigating |
| CI integration tests | Enable summary if tests verify native memory trends |
| Staging | Enable summary during load tests or when establishing baselines |
| Production | Consider summary when observability benefits outweigh measured overhead |
| Deep investigation | Launch a canary instance with detail for a limited time |

Do not enable `detail` across all replicas by default without assessing overhead and output size. Select a canary instance handling representative load for deep dives.

### 10.3. Protecting Diagnostic Information

NMT output can expose runtime structure, call sites, libraries, and how the application operates. Be sure to:

- Restrict access to `jcmd` and process diagnostics.
- Store outputs in access-controlled locations.
- Avoid posting detailed diagnostic logs in public channels.
- Record timestamp, PID, container/replica, and JVM flags.
- Disable `detail` mode once investigation ends if no longer needed and redeploy with standard configuration.

## 11. Example Workflow: Investigating Native Memory Growth

Suppose a service runs in a 1 GiB container. Max heap is 512 MiB, post-GC heap used stays steady around 180 MiB, yet container memory usage climbs steadily toward 900 MiB.

### 11.1. Initial Observation

Collect simultaneously:

- Heap used/committed/max.
- Process RSS.
- cgroup `memory.current`.
- Thread count.
- Direct buffer pools.
- NMT summary.

If heap used is stable while RSS climbs, you cannot immediately conclude a native leak; locate the growing category or allocations outside NMT.

### 11.2. Enable Summary and Take a Baseline

Launch the investigation instance:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

After warm-up:

```shell
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.native_memory baseline
```

Run a workload at representative concurrency and capture diffs periodically:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

### 11.3. Interpreting Results

Suppose the Thread category grows alongside thread count. Then:

1. Capture a thread dump.
2. Identify which thread pool creates threads.
3. Check whether threads terminate after requests/tasks complete.
4. Check pool configuration and concurrency limits.
5. Compare stack reservations/commitments against RSS.

If Class/Metaspace grows:

1. Track loaded class count and metaspace pools.
2. Check whether class loaders are released.
3. Check for dynamic proxies, script engines, hot reload, or redeployments.
4. Use class histograms/heap dumps if you need to find references retaining class loaders.

If NMT does not explain RSS growth:

1. Inspect direct/mapped buffer pools.
2. Check JNI/native libraries.
3. Inspect `smaps_rollup` or `pmap`.
4. Use native profilers or platform-specific tools.

### 11.4. Switching to detail When Needed

If `summary` shows a specific category growing without revealing the call site, deploy an investigation instance with:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

After warm-up, take a baseline and inspect:

```shell
jcmd <pid> VM.native_memory detail
jcmd <pid> VM.native_memory detail.diff scale=MB
```

Detail mode can pinpoint relevant HotSpot call sites. If the allocation originates in JNI or libraries outside NMT's scope, other tools are required.

## 12. Common Mistakes When Using NMT

| Mistake | Why It Is Wrong | How to Handle It |
|---|---|---|
| Running `jcmd VM.native_memory` when NMT is disabled | The JVM has no tracking data | Restart with `-XX:NativeMemoryTracking=summary` or `detail` |
| Thinking NMT can be enabled after startup | Tracking must be initialized from launch | Choose the tracking level when starting the JVM |
| Reading reserved as RAM currently in use | Reserved is virtual address space | Inspect committed, RSS, and cgroup metrics separately |
| Equating committed with RSS | The two metrics have different definitions | Cross-check NMT with OS process metrics |
| Assuming NMT tracks every JNI allocation | NMT focuses on HotSpot VM; external native code may not be recorded | Use native profilers/OS metrics for native libraries |
| Using NMT instead of a heap dump | NMT does not analyze object graphs or retained sizes | Use heap dumps and JFR for the heap |
| Concluding a leak from a single diff | Startup, warm-up, and workload cause normal growth | Take multiple baselines/diffs across comparable cycles |
| Enabling detail on all replicas | Unnecessary overhead and large outputs | Use summary first, detail on a canary when needed |
| Not recording baseline timing | Diffs are hard to correlate with workload | Record timestamp, workload, PID, and configuration |
| Comparing outputs with different scales | Units do not match | Use consistent `scale=` when comparing |
| Using NMT Total to explain all container usage | OS, JNI, class libraries, and other native allocations exist | Combine RSS/cgroup, buffer metrics, and native tools |
| Shutting down NMT and expecting to re-enable via jcmd | Shutdown is not a re-enable mechanism | Restart the JVM with tracking enabled |

## 13. Java 17 Example: Reading Heap, Non-Heap, Thread, and Buffer Metrics

NMT is queried with `jcmd`; applications can also expose JVM metrics for cross-checking. Save **JvmMemoryMetrics.java**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class JvmMemoryMetrics {

    private static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        System.out.printf("Heap used: %.1f MiB%n", mib(heap.getUsed()));
        System.out.printf(
                "Heap committed: %.1f MiB%n",
                mib(heap.getCommitted())
        );
        System.out.printf("Heap max: %.1f MiB%n", mib(heap.getMax()));
        System.out.printf(
                "Non-heap used: %.1f MiB%n",
                mib(nonHeap.getUsed())
        );

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        System.out.println("Live threads: " + threads.getThreadCount());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class
                )) {
            System.out.printf(
                    "%s: count=%d, used=%.1f MiB, capacity=%.1f MiB%n",
                    pool.getName(),
                    pool.getCount(),
                    mib(pool.getMemoryUsed()),
                    mib(pool.getTotalCapacity())
            );
        }
    }
}
```

Compile and run on JDK 17:

```shell
javac --release 17 JvmMemoryMetrics.java
java -XX:NativeMemoryTracking=summary JvmMemoryMetrics
```

Then grab the JVM PID and run:

```shell
jcmd <pid> VM.native_memory summary scale=MB
```

The metrics in the example come from MXBeans; they do not cover all native memory. Use them together with NMT and OS/container metrics for correlation.

## 14. End-to-End Practical Workflow

1. **Define the question.** Is heap growing, native memory growing, RSS growing, or the container hitting its limit? Choose the right metrics to inspect.
2. **Enable NMT before running.** Use `summary` for initial exploration; `detail` for deep investigation.
3. **Confirm tracking level.** Check `VM.flags` and test `VM.native_memory summary`.
4. **Wait for startup/warm-up.** If hunting a steady-state leak, do not baseline while frameworks/JIT are still loading initial resources.
5. **Record the baseline.** Run `jcmd <pid> VM.native_memory baseline`.
6. **Run a repeatable workload.** Log concurrency, request rate, duration, and input data.
7. **Capture diffs.** Use `summary.diff` with a consistent scale.
8. **Narrow down categories.** Compare with thread count, class count, heap, buffer pools, and RSS.
9. **Switch to detail if needed.** Use an instance with `detail` to inspect call sites.
10. **Check outside NMT's scope.** If RSS remains unexplained, use OS/native tools.
11. **Repeat to confirm.** A trend is trustworthy only when reproducible across multiple measurements under equivalent conditions.
12. **Document findings and remove unnecessary diagnostic settings.** If changing NMT level, roll a restart with appropriate flags.

## 15. Practice Exercises

### Exercise 1 — Enabling NMT Summary

Run a Java 17 application with:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Use `jcmd` to pull the summary. Identify Total reserved/committed and the largest categories. Explain why committed cannot be called RSS.

### Exercise 2 — Creating a Baseline and Diff

After warm-up, run:

```shell
jcmd <pid> VM.native_memory baseline
```

Generate load for a period, then run:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Record the fastest-growing category and formulate a testable hypothesis. Repeat with an equivalent workload to separate steady growth from normal fluctuation.

### Exercise 3 — Comparing summary and detail

Start two separate test JVMs: one with `summary`, one with `detail`. Compare outputs and observe overhead under the same workload. Do not try to switch tracking levels mid-flight inside the same JVM.

### Exercise 4 — Tracking Threads

Create a workload with thread pools configured at different sizes. Compare the NMT Thread category, thread count, and RSS. Explain how thread stacks increase native memory.

### Exercise 5 — Tracking Direct Buffers

Allocate several `ByteBuffer.allocateDirect` buffers, and observe `BufferPoolMXBean`, NMT, and RSS. Explain why you should not expect one NMT category to always reflect all direct buffers across every runtime.

### Exercise 6 — Separating Heap and Native Growth

Create one workload that grows heap objects and another that grows native allocations in an appropriate test environment. Observe heap metrics, NMT, and RSS. Identify which tool explains each type.

### Exercise 7 — Investigating Cgroups

Run the JVM inside a container with a memory limit. Track cgroup usage alongside NMT Total committed and heap usage. Explain what components can cause discrepancies among the three figures.

### Exercise 8 — Writing an Investigation Report

Document:

- JDK vendor/version and JVM flags.
- NMT level.
- Container memory limit.
- Warm-up and baseline timestamps.
- Workload.
- Summary and diff.
- Peak RSS/cgroup usage.
- Hypothesis and confirming evidence.

Do not conclude a leak from a single snapshot.

## 16. Self-Check Questions

1. What is NMT, and at which layer of the Java runtime is it implemented?
2. Why does NMT not replace a heap profiler?
3. Is NMT enabled or disabled by default on HotSpot?
4. What is the difference between `summary` and `detail`?
5. Why must NMT be enabled when the JVM starts?
6. What does `jcmd VM.native_memory baseline` do?
7. What reference point does `summary.diff` compare against?
8. How do reserved and committed differ?
9. Why does committed not equal RSS?
10. Which categories commonly appear in an NMT summary?
11. How does thread count relate to native memory?
12. Does NMT fully track every JNI/native library allocation?
13. Why do direct buffers require `BufferPoolMXBean` as well?
14. When should you switch from `summary` to `detail`?
15. Does NMT have overhead, and how should you evaluate it?
16. If RSS grows while NMT stays nearly flat, what should you inspect?
17. Why is a post-warm-up baseline helpful when looking for steady-state growth?
18. How does `OOMKilled` differ from `OutOfMemoryError`?
19. Can NMT be re-enabled after running the `shutdown` command?
20. Why must NMT be combined with cgroup/container metrics?

## 17. References

- [Java SE 17 Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): using NMT to investigate memory leaks and native memory.
- [Java SE 17 jcmd Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): syntax for sending diagnostic commands to a running JVM.
- [Java SE 17 VM Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:NativeMemoryTracking` and runtime flags.
- [Java SE 17 API — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap and non-heap memory usage.
- [Java SE 17 API — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct and mapped buffer pool details.
- [Java SE 17 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread counts and thread details.
- [OpenJDK HotSpot Virtual Machine Guide](https://docs.oracle.com/en/java/javase/17/vm/): HotSpot runtime mechanisms and memory management.

Native Memory Tracking reveals how HotSpot reserves and commits native memory by category while providing baselines and diffs to spot growth trends. Enable tracking at JVM startup, use `summary` to narrow down categories, and use `detail` when deep investigation is needed. Always distinguish NMT from heap object usage, RSS, and container memory usage; when figures disagree, check direct buffers, JNI, native libraries, and OS-managed memory regions. Combining these data sources enables accurate Java 17 memory diagnostics without mistaking a single NMT category for total process memory.
