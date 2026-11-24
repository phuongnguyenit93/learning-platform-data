# 13.4 Using VM.native_memory to Read Reports by Memory Usage Category

## Learning Objectives

In a Java process, `-Xmx` limits only the **Java heap**, while the JVM also uses memory for metaspace, thread stacks, JIT-compiled code, GC structures, and other native regions. This lesson shows how to use `jcmd`'s **`VM.native_memory`** diagnostic command to read **Native Memory Tracking (NMT)** reports on the **HotSpot JVM**.

After completing this lesson, you will be able to:

- Enable NMT at `summary` or `detail` level from JVM startup, identify the PID, and collect reports safely.
- Accurately explain `reserved`, `committed`, `malloc`, `mmap`, and how to read totals versus individual memory categories.
- Recognize `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, and other categories reported by the live JVM.
- Use `baseline` and `summary.diff` / `detail.diff` to track changes under identical load conditions.
- Identify NMT's limitations and combine it with heap, thread, metaspace, and OS RSS metrics before concluding a memory leak.

**Scope:** command examples target HotSpot Java 17 and later. Category names, memory amounts, wording in output, attach availability, and classification details may vary across JDKs, operating systems, collectors, and configurations. NMT is a HotSpot diagnostic feature and does not automatically apply verbatim to other JVMs.

## 1. Why the Java Heap Is Not All of Process Memory

Consider a service running with `-Xmx512m`. That 512 MiB figure is normally the **Java heap size limit**, not an absolute cap on the entire process. Beyond the heap, HotSpot needs other memory regions:

| Typical Category | Common Purpose |
| --- | --- |
| Java Heap | Storage for most Java objects, managed by the garbage collector |
| Class / Metaspace | Class and method metadata and class-loading support structures |
| Thread | Native stacks and internal thread-related data |
| Code | JIT-compiled machine code memory and code cache infrastructure |
| GC | Structures serving the collector, depending on collector |
| Compiler | Internal data of the JIT compiler |
| Internal, Symbol, Module, Other… | Other HotSpot categories, depending on version |

In addition to JVM-tracked regions, the process has loaded native libraries, memory from JNI or third-party libraries, file mappings, and allocations outside NMT's scope. Therefore:

~~~text
Java heap usage ≠ NMT committed ≠ process RSS ≠ RAM/container limit
~~~

- **Heap used** is the size of heap objects/regions counted as in use by heap tools, affected by GC timing.
- **NMT committed** reflects memory committed/allocated by HotSpot within tracked NMT categories; it does not tell you exactly which pages actually reside in RAM.
- **RSS / working set** is an OS-level resident page concept; it is also affected by shared pages, mapped files, native libraries, and things NMT does not cover.

A rising NMT report may simply show that the JVM committed more space to operate; it is not enough by itself to conclude a leak or that physical RAM rose by the exact reported amount.

## 2. What NMT Is, Where to Enable It, and What It Costs

**Native Memory Tracking** records how HotSpot manages its internal memory allocations, grouping them by subsystem/category. It is very useful when a process has footprint issues or native out-of-memory errors that the Java heap alone cannot explain.

NMT is **disabled by default**. It must be enabled **at JVM startup**:

~~~sh
# Less detail, suitable when you primarily need category-level trends:
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m -jar app.jar

# Records more detail on native allocation sites inside the VM:
java -XX:NativeMemoryTracking=detail -Xms128m -Xmx512m -jar app.jar
~~~

`app.jar` is just an illustrative JAR name; substitute your application. With Spring Boot, VM options must appear **before** `-jar`. When running in Docker/Kubernetes, set the JVM option in the actual config used to launch the Java process, then verify on the right PID inside the container.

Levels:

| Level | Available Information | When to Choose |
| --- | --- | --- |
| `off` | No NMT data; this is the default | When NMT observation is not needed |
| `summary` | Totals and breakdown by memory category | First step when investigating footprint growth |
| `detail` | Categories as in summary plus native call-site / virtual memory map info | When summary identifies a category needing deeper tracing |

**You cannot start NMT from `off` using `jcmd` on an already running JVM.** Nor can you turn `summary` tracking level into `detail` merely by requesting a report. `VM.native_memory shutdown` disables tracking for the process; per documented HotSpot behavior, it cannot be restarted via `jcmd` afterward. To change levels, restart the JVM with the appropriate flag.

NMT incurs CPU and memory overhead: Oracle documentation notes it can reduce performance by around 5–10% in some cases. This is **not a fixed figure**; benchmark against your actual workload and collection window. Tracking at `detail` can add more overhead and produce large output. Avoid enabling it unconditionally everywhere.

## 3. Finding the Right Process and Calling `VM.native_memory`

Use a `jcmd` belonging to a JDK compatible with the target JVM. You need process access permissions and a working attach mechanism. Inside containers, the PID visible in the container may differ from the PID seen by the host OS.

~~~sh
# List JVMs attachable from the current environment.
jcmd -l

# Replace <pid> with the actual PID found.
jcmd <pid> VM.native_memory summary

# Read numbers in KiB so small categories are not lost to rounding:
jcmd <pid> VM.native_memory summary scale=KB

# Use MB for a compact overview:
jcmd <pid> VM.native_memory summary scale=MB
~~~

If `jcmd -l` does not show the application, check the JDK/JRE path, permissions, process owner user, container namespace, attach restrictions (`-XX:+DisableAttachMechanism`), and whether the application is still running. Do not accidentally pull numbers from another process's PID.

### 3.1 Example of a Partial Real Report

Measured on a small Java program with HotSpot **JDK 24**, `-Xms32m -Xmx128m`, and `NativeMemoryTracking=summary`, `summary scale=MB` produced output such as:

~~~text
Native Memory Tracking:

(Omitting categories weighting less than 1MB)

Total: reserved=1575MB, committed=132MB

-                 Java Heap (reserved=128MB, committed=34MB)
-                     Class (reserved=1024MB, committed=0MB)
-                    Thread (reserved=23MB, committed=1MB)
-                      Code (reserved=242MB, committed=7MB)
-                        GC (reserved=75MB, committed=73MB)
~~~

This is an **illustrative excerpt**, not including all categories and not a standard footprint for JDK 17/21 or every application. `Class committed=0MB` here is due to **MB unit rounding**, not that the JVM uses zero bytes for class metadata. In the full report, small categories appear when using `scale=KB`. Do not sum the lines in this excerpt expecting them to match `Total`, because smaller categories were omitted.

One common point of confusion: total `reserved=1575MB` far exceeds `-Xmx128m`, yet `committed` is only `132MB`. A pre-reserved virtual address region, such as compressed class space, can be large even when committed memory is still very small.

### 3.2 Reading `reserved` and `committed`

**Reserved** is virtual address space set aside by the JVM for future use. **Committed** represents the memory the JVM has committed/allocated for use under the corresponding mechanism. For mapped regions, a large area may be reserved up front and committed gradually; committed does not equal RSS or bytes holding useful data.

For example, the line:

~~~text
Java Heap (reserved=128MB, committed=34MB)
~~~

is read as: HotSpot has reserved roughly 128 MiB of virtual address space for the Java heap, of which roughly 34 MiB is committed at the time of measurement. **Do not** infer "34 MiB of live Java objects" or "34 MiB of RAM pages definitely resident". To inspect object/heap-used status, use a dedicated heap tool, such as:

~~~sh
jcmd <pid> GC.heap_info
~~~

Similarly, `Class` can reserve a large virtual address region for compressed class space; a much smaller `committed` value is normal. Analyze `committed` trends under comparable load conditions rather than sounding an alarm over a large `reserved` figure alone.

### 3.3 Reading `malloc`, `mmap`, `arena`, and the `#` Symbol

Within a category's detailed breakdown, you may see lines like:

~~~text
-       Sample Category (reserved=4000KB, committed=3000KB)
                       (malloc=1000KB #200)
                       (mmap: reserved=3000KB, committed=2000KB)
~~~

**These are hypothetical numbers for practicing syntax**, and `Sample Category` is not a standard category emitted by the JVM.

- `malloc=1000KB #200`: in this example, the category also has about 1,000 KiB allocated via NMT-tracked malloc paths, with a counter of 200 allocation blocks as accounted by the VM. `#200` is **not 200 Java objects**.
- `mmap: reserved=3000KB, committed=2000KB`: virtual/committed addresses via mapping mechanisms in the JVM report; not synonymous with file mappings or RSS.
- Some categories include `arena`: memory distributed via internal arenas/chunks; do not read each chunk as an individual Java object.
- Each category's total already encompasses its sub-lines; **do not add `malloc` and `mmap` again to the category total or Total**. Breakdowns like `Metadata`, `Class space`, or smaller sub-items under `Class` are also breakdowns, not independent extra categories.

When using `scale=MB`, small amounts can round to 0; use `scale=KB` when investigating small deltas. Do not infer exact byte counts from rounded display numbers.

## 4. Reading Each Memory Category: Signals and Questions to Ask

Category names and counts vary by JDK. The following table summarizes how to interpret common entries in HotSpot reports:

| Category | Typical Contents | When `committed` Rises, Check |
| --- | --- | --- |
| **Java Heap** | Heap capacity JVM reserved/committed for objects | Did heap committed expand due to load/GC? How much is heap **used** or real live set? |
| **Class** | Class metadata, Metaspace, compressed class space depending on config | Are new classes/classloaders being loaded? Is class unloading occurring? Is the app generating dynamic proxies/classes? |
| **Thread** | Thread stacks and internal per-thread structures | Is total thread count rising? Unbounded thread pools, threads held without exiting? |
| **Code** | Code cache, JIT machine code, and related regions | Is JIT warming up, many methods compiled, code cache nearing limit? |
| **GC** | Structures used by the collector | Which collector is running, did heap size/workload grow, did GC policy change? |
| **Compiler** | Working structures of the JIT compiler | Prolonged warm-up/compilation or changes in compilation task count? |
| **Internal** | Internal JVM data not belonging to the categories above | Any config/agent/runtime changes? Need `detail` or additional metrics |
| **Symbol** | JVM symbol tables/strings | How are class loading, metadata, and runtime structures growing? |
| **Native Memory Tracking** | Memory NMT itself uses to track allocations | Overhead of enabling tracking, especially at `detail` |
| **Other** | HotSpot allocations assigned to the remaining bucket | Do not automatically assume direct buffers/JNI or a leak; verify context and other tools |

Some JVMs also display `Arena Chunk`, `Logging`, `Arguments`, `Module`, `GCCardSet`, or feature-specific categories. The absence of a category also does **not** prove the corresponding feature uses zero memory: the amount may be tiny, omitted under `scale=MB`, or classified elsewhere.

### 4.1 `Java Heap`: Reserved/Committed Differs from Object Usage

`-Xms`/`-Xmx`, commit/uncommit policies, and the garbage collector govern the NMT `Java Heap` entry. When Java code allocates another array while the **already-committed heap has enough room**, `committed` may **not change**. NMT is not a profiler for allocation rate, object counts, heap histograms, or retained size.

If your goal is investigating a Java heap leak, cross-check `GC.heap_info`, post-GC heap used trend, heap dumps, or JFR allocation/GC events. Do not treat `Java Heap committed` as live object bytes.

### 4.2 `Class`: Understanding Compressed Class Space and Metaspace

A report may reserve roughly 1 GiB of address space for class space while committing only a few MiB, depending on `-XX:CompressedClassSpaceSize` and whether compressed class pointers are used. `Class` may also show instance class count, array class count, metadata used/free/waste, and class space.

When investigating steadily rising `Class committed`, check loaded class counts, live classloaders, class unloading, and frameworks generating dynamic proxies/code. Use `jcmd <pid> VM.metaspace` when supported by the JVM to inspect metaspace further. Do not declare a leak just because class count rises during normal warm-up.

### 4.3 `Thread`: Thread Count and Stacks

The `Thread` report usually shows `threads #...` along with `stack: reserved=..., committed=...`. More threads can cause total stack **reserved** to jump sharply even while committed stays low; stack sizing depends on the platform and `-Xss`. `Thread` also includes non-stack data.

Cross-check thread count and thread dumps with `jcmd <pid> Thread.print`. If a pool keeps creating threads, inspect backpressure, pool sizing, thread termination, and thread leaks; do not conclude from `Thread reserved` alone.

### 4.4 `Code`, `GC`, and `Compiler`

- **Code** commonly changes during JIT compilation/warm-up; distinguish code cache reaching steady state from unbounded growth.
- **GC** depends on the collector and heap/config; allocating collector structures does not imply a Java heap leak.
- **Compiler** can fluctuate as the JVM compiles methods; temporary spikes around warm-up are not automatically abnormal.

Investigate along the same timeline with application load, CPU, GC pauses, thread count changes, and JVM flags.

## 5. Baseline and Diff Technique: Finding Growing Categories Over Time

A point-in-time snapshot only shows **state at that instant**. To see trends, NMT provides baselines.

### 5.1 Taking a Baseline After Application Warm-Up

~~~sh
# Once request rate, caches, and JIT have passed startup:
jcmd <pid> VM.native_memory baseline

# After a representative load interval, compare against baseline:
jcmd <pid> VM.native_memory summary.diff scale=KB

# Capture a current snapshot when you need absolute values to compare:
jcmd <pid> VM.native_memory summary scale=KB
~~~

`summary.diff` displays current values alongside increases/decreases compared to the baseline. `+` means growth, `-` means shrinkage, and no delta can mean zero or rounding below the display unit. **Hypothetical illustrative** example:

~~~text
Total: reserved=640000KB +16000KB, committed=155000KB +12000KB
- Thread (reserved=52000KB +16000KB, committed=5000KB +1000KB)
- Class  (reserved=110000KB, committed=12000KB +500KB)
~~~

Growth in `Thread` suggests checking thread counts; growth in `Class` suggests checking class loading. These are **investigation hypotheses**, not leak conclusions. Because `reserved` and `committed` can move differently, examine both as well as their progression over time.

Repeat measurements at multiple checkpoints, e.g., after 5, 10, and 30 minutes under comparable workload. Do not take the baseline too early and mistake normal class loading/JIT warm-up for a leak. Before replacing a baseline, save the reports you need to keep for comparison.

### 5.2 When Do You Need `detail.diff`?

If the JVM was started with `-XX:NativeMemoryTracking=detail`, use:

~~~sh
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

`detail` can also provide a virtual memory map and allocation call sites inside **HotSpot native code**. Addresses, symbols, and call stacks depend on the JVM/build/OS; this is **not** a full Java allocation stack trace and cannot trace every `malloc` inside third-party libraries.

If the JVM started at `summary`, running `detail` or `detail.diff` will not "upgrade" the data. On a tested HotSpot JDK 24 build, `VM.native_memory detail` returned:

~~~text
Detail tracking is not enabled
~~~

To get detail, restart with `NativeMemoryTracking=detail`. Start with the lowest level sufficient to answer the question, and raise the level only in a controlled run.

## 6. Java 17+ Hands-On: Generating Reports for a Controllable Process

The following example keeps a JVM running so you can inspect it from a second terminal, then allocates 16 Java arrays each with a 1 MiB payload. The goal is to **observe NMT before/after on the same JVM**, while seeing why allocated object size **does not have to** match the change in `Java Heap committed`.

Save **`NativeMemoryDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class NativeMemoryDemo {
    private static volatile byte[][] retained;

    public static void main(String[] args) throws Exception {
        BufferedReader console = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        System.out.println("READY: press Enter to allocate");
        console.readLine();

        byte[][] chunks = new byte[16][];
        for (int i = 0; i < chunks.length; i++) {
            chunks[i] = new byte[1_048_576];
        }
        retained = chunks;

        System.out.println("RETAINED: 16 arrays, 16 MiB payload");
        System.out.println("Press Enter to exit");
        console.readLine();
    }
}
~~~

**Terminal A:** compile and run (keep the terminal open, do not press Enter yet):

~~~sh
javac --release 17 NativeMemoryDemo.java
java -Xms32m -Xmx128m -XX:NativeMemoryTracking=summary NativeMemoryDemo
~~~

Initial stdout is exactly:

~~~text
READY: press Enter to allocate
~~~

**Terminal B:** find the actual PID of the `NativeMemoryDemo` process and set a baseline:

~~~sh
jcmd -l
jcmd <pid> VM.native_memory summary scale=KB
jcmd <pid> VM.native_memory baseline
~~~

Return to **Terminal A** and press Enter **once** to trigger allocation. The program additionally prints:

~~~text
RETAINED: 16 arrays, 16 MiB payload
Press Enter to exit
~~~

While Terminal A keeps the process alive, run in **Terminal B**:

~~~sh
jcmd <pid> VM.native_memory summary.diff scale=KB
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> GC.heap_info
~~~

Now compare. 16 MiB is the **payload** of the arrays; actual objects also include headers/alignment and overhead from other structures. The static field `retained` keeps the arrays reachable. However, do not expect `summary.diff` to necessarily show `Java Heap committed +16384KB`: the JVM may have already committed enough space beforehand, or commit a different amount depending on the collector. `GC.heap_info` gives a different view of the heap from NMT.

Once finished observing, press Enter again in **Terminal A** to exit cleanly. The example above was compiled with `javac --release 17` and verified on HotSpot; the three lines printed by the program match as described. `jcmd` output varies by JVM and machine.

### 6.1 If You Want to Try Detail

Start a fresh run with the same program but change the JVM flag:

~~~sh
java -Xms32m -Xmx128m -XX:NativeMemoryTracking=detail NativeMemoryDemo
~~~

While the program waits for input in Terminal A:

~~~sh
jcmd -l
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory baseline
~~~

After pressing Enter to allocate in Terminal A:

~~~sh
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

Do not directly compare runtime cost between these two runs without identical workloads: `detail` has different overhead than `summary`, and JIT/GC activity also varies across runs.

## 7. Reading NMT During an Incident: Which Evidence Sources to Combine

| Symptom | How Can NMT Help? | What Else to Check |
| --- | --- | --- |
| RSS/working set grows, post-GC Java heap used stable | See which HotSpot committed category grows, especially Thread/Class/Code/GC | OS/container RSS data, JNI and native libraries, direct buffers, mapped files |
| NMT `Class committed` grows continuously | Narrow down metadata/class space | Classloader/class counts, `VM.metaspace`, class unloading, and proxy-generation lifecycle |
| NMT `Thread reserved` jumps sharply | Check `threads #...`, stack reservation/commit | Thread dump, thread pool metrics, `-Xss`, resource limits |
| NMT `Java Heap committed` high | Check actual heap reservation/commitment | Heap used/live set, GC logs, heap dump, object histogram |
| NMT `GC committed` or `Code committed` grows | Identify the responsible subsystem | Collector/version/config, workload, JIT compilation/code cache |
| NMT stable while RSS keeps growing | NMT does not explain the change; likely out-of-scope allocations or resident page behavior | OS memory maps/working set, native profiler, JNI/direct/mapped memory, cgroup stats |

**There is no valid deduction "RSS − NMT committed = exact leaked native memory".** The two measurement systems use different definitions, some regions may be accounted differently, and physical residency does not match committed bytes. Look for a specific memory-retention mechanism and verify it with the right tool.

### Complementary Tools and Corresponding Questions

- `jcmd <pid> GC.heap_info`: current heap state; GC logs and heap metrics show heap used/committed trends.
- `jcmd <pid> VM.metaspace`: inspect metaspace when supported by the JVM.
- `jcmd <pid> Thread.print` and thread metrics: thread counts, thread states, and suspected non-terminating threads.
- JFR/JMC or Java heap profiler: analyze Java allocations/GC, pause times, and Java allocation stacks; they do not replace NMT's native subsystem breakdown.
- `BufferPoolMXBean` / JMX buffer pools: additional visibility into Java-API-managed direct/mapped buffers; this does not cover all JNI allocations.
- OS memory tools (Windows Process Explorer/Performance Monitor, Linux `/proc/<pid>/smaps_rollup` and `pmap`, container memory metrics): observe RSS, mappings, and shared/private memory outside NMT's scope.

Errors like `OutOfMemoryError: Java heap space`, `OutOfMemoryError: Metaspace`, `unable to create native thread`, or an OS/container OOM kill have different mechanisms. Pair the error message, timestamps, and metrics for the right memory region. Simply raising `-Xmx` does not solve every native memory incident.

## 8. Workflow for Investigating Abnormal Footprint with NMT

1. **Gather context:** record JDK vendor/version, collector, `-Xms/-Xmx`, `-Xss`, container limits, and current thread count. Confirm the JVM is HotSpot supporting NMT.
2. **Enable NMT for a planned startup:** start with `summary` when you need to know which category grows; use `detail` if native allocation call sites are needed and overhead is acceptable.
3. **Warm up and set baseline:** wait until the app reaches representative load; record load rate, latency, thread count, heap used/committed, and RSS with timestamps.
4. **Collect multiple diffs:** capture `summary.diff scale=KB` at suitable intervals; save both current values and deltas from baseline. Do not rely on a single snapshot.
5. **Narrow down the category:** if `Thread` grows, check thread count; if `Class` grows, check classloaders/metaspace; if `Java Heap` grows, cross-check GC/heap; if `Other/Internal` grows, use `detail` or other profilers to verify.
6. **Check regions outside NMT's scope:** if OS memory grows while NMT stays flat, investigate JNI and native libraries, direct/mapped buffers, file mappings, and resident page costs.
7. **Test a fix and re-measure:** run comparable load, cross-check committed, RSS, latency, and throughput. Conclude only when you find the allocation/retention root cause and the metrics shift in line with the hypothesis.

**Operational safety note:** attach may be restricted; `VM.native_memory` has diagnostic impact, and `detail` can produce very long logs. In production, choose measurement windows, tracking levels, and output collection per approved operational procedures; do not restart services or enable NMT broadly just to grab an example.

## 9. Common Misconceptions

1. **"`reserved=2GB` means the process is using 2GB of RAM."** False: reserved is virtual address space; check committed and RSS in context.
2. **"`committed=500MB` is the exact RSS."** False: NMT committed is not the OS resident-pages metric, and NMT does not cover the entire process.
3. **"`Java Heap committed=200MB` means Java objects occupy 200MB."** False: committed space may contain unused space; check used/live set with heap tools.
4. **"`Class reserved=1GB` proves a metaspace leak."** False: compressed class space can reserve large space up front while committing very little.
5. **"`malloc #5000` means 5000 Java objects."** False: that is a native/NMT allocation counter within the context of that report line.
6. **"You can turn on `detail` with `jcmd` while the JVM is already running with NMT off."** False: the desired tracking level must be enabled at JVM startup.
7. **"`summary.diff` showing `+` definitely means a leak."** False: warm-up, higher load, legitimate caches, thread/class loading, and heap state shifts can all raise numbers.
8. **"NMT is guaranteed to see every `malloc` from JNI and external libraries."** False: NMT has scope limits; native/OS tools are needed to observe outside HotSpot.
9. **"A small category showing `0MB` means zero memory used."** False: switch to `scale=KB`; output was rounded or small categories were omitted.
10. **"Just raising `-Xmx` eliminates native OOM."** False: increasing heap even competes with native regions for the container/host memory budget.

## 10. Applied Exercises with Solutions

**Scenario A — reading a single line.** Report reads `Java Heap (reserved=1024MB, committed=256MB)`. Is the JVM using 256 MiB of live objects?

**Solution:** Cannot conclude that. The JVM reserved 1024 MiB of address space and committed roughly 256 MiB for the heap. You need heap used/live-set metrics and GC observations to know how many live objects remain.

**Scenario B — suspected thread issue.** Under steady load, `Thread reserved` rises by 400 MiB in 30 minutes, and `Thread (threads #...)` also rises steadily. What next?

**Solution:** Investigate thread counts and lifecycles, `Thread.print`, thread pools, concurrency limits, and retained resources. You cannot confirm a leak from `reserved` alone; first identify which threads are not terminating and why.

**Scenario C — RSS grows while NMT stays flat.** RSS rises by 600 MiB; `summary.diff` is near 0 across all categories. Can you conclude the JVM is not involved?

**Solution:** Not yet. NMT only tracks what HotSpot supports; JNI/third-party library allocations or resident pages/mappings may lie outside its scope. Use OS metrics, native profilers, and direct/mapped memory data to locate the source of growth.

**Scenario D — choosing tracking level.** On a run with `NativeMemoryTracking=summary`, `jcmd <pid> VM.native_memory detail` reports detail tracking is not enabled. How to handle?

**Solution:** Restart the JVM with `-XX:NativeMemoryTracking=detail` for the next observation run; take the baseline after warm-up, then run `detail.diff`. NMT cannot dynamically enable or upgrade to `detail` via `jcmd`.

**Scenario E — timing differences.** 20 seconds after startup, `Class committed` and `Code committed` rise; after 10 minutes both stabilize. Is this a leak?

**Solution:** No leak evidence from this observation. Class loading and JIT warm-up normally increase committed memory early in a process's life and then plateau. Set the baseline after warm-up, keep monitoring under comparable load, and cross-check actual performance.

## 11. Command Quick Reference

~~~sh
# Enable when creating the process:
java -XX:NativeMemoryTracking=summary -jar app.jar

# Read status:
jcmd -l
jcmd <pid> VM.native_memory summary scale=KB

# Measure growth/shrinkage:
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff scale=KB

# If the JVM was started with NativeMemoryTracking=detail:
jcmd <pid> VM.native_memory detail scale=KB
jcmd <pid> VM.native_memory detail.diff scale=KB
~~~

**How to read properly:** start from **Total reserved/committed**, examine the **top-level categories**, use `malloc/mmap/arena` sub-lines to understand mechanisms, take **baseline/diff** to track trends, then verify with heap/thread/metaspace/OS metrics. Every signal requires a testable hypothesis. NMT is strongest at answering **"Which category is HotSpot reserving/committing memory into, and which category is changing?"**, rather than single-handedly answering "why is RSS rising?" or "which Java object is leaking?".

### References

- Oracle, *Java 21 Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle, *Java 21 Diagnostic Tools – Native Memory Tracking*: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- OpenJDK / Java troubleshooting, *Troubleshooting Memory Leaks*: https://ops.java/troubleshooting/articles/memory-leaks/
