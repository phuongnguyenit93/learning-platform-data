# 13.7 Cross-Checking NMT with BufferPoolMXBean, Thread Counts, and OS Metrics

## Objectives

When a Java process's RSS climbs, exceeds a container memory limit, or is terminated by the OS even though **Java heap used** is not high, you need to combine multiple measurement sources. This lesson teaches you how to:

1. Read **Native Memory Tracking (NMT)**: reserved, committed, and the Java Heap, Thread, Class, Code, GC, Internal/Other categories; understand NMT's scope limits.
2. Collect metrics from **BufferPoolMXBean** for direct/mapped buffers and distinguish count, totalCapacity, and memoryUsed.
3. Cross-check **JVM platform thread count**, process native threads, and the memory NMT attributes to Thread.
4. Read **RSS, VSZ/VmSize, PSS, anonymous/file-backed memory**, Linux thread counts, and cgroup/container limits.
5. Design measurements with **aligned timestamps, workloads, and units** to narrow down the cause, without summing incompatible numbers or labeling something a "native leak" from a single snapshot.

**Overarching principle:** NMT, BufferPoolMXBean, ThreadMXBean, and OS metrics are **views with different scopes and semantics**. They help cross-verify hypotheses; they generally cannot be added or subtracted into an exact byte-for-byte reconciliation.

## 1. Four Observation Layers of the Same Process

Suppose a service runs with **-Xmx512m**, yet a dashboard reports RSS at 1.2 GiB. This does not automatically prove a leak: a Java process also uses code cache, metadata, native stacks, GC metadata, direct buffers, JNI/native libraries, memory mappings, and many other regions. Even for the Java heap alone, **used**, **committed**, **reserved**, and **resident** all differ.

| Source | Primary Observation | Question to Ask | What Cannot Be Concluded Directly |
| --- | --- | --- | --- |
| **JMX MemoryMXBean** | Heap/non-heap usage reported by the JVM | How much heap is used/committed? | Total resident memory of the process |
| **NMT — jcmd VM.native_memory** | Memory tracked by HotSpot, broken down by subsystem and reserved/committed | Which JVM-managed area is growing? | Total allocations of all JNI/library/native code |
| **BufferPoolMXBean** | Count, total capacity, and estimated memory used for JVM-exposed buffer pools | Are direct/mapped buffers growing? | Total off-heap memory or all process mmaps |
| **ThreadMXBean + OS threads** | JVM platform threads and process native threads | Is abnormal thread growth pulling up stacks? | Virtual thread count; exact resident stack bytes |
| **OS/process/container metrics** | Resident pages, virtual mappings, shared/private, cgroup charges | Is the process/container under real RAM pressure? | Exactly which object/class/call site retains memory |

One situation can happen simultaneously: NMT **Java Heap committed** = 512 MiB, **heap used** = 240 MiB, BufferPoolMXBean **direct memoryUsed** = 128 MiB, RSS = 820 MiB. All four numbers can be valid. There is no rule requiring RSS to equal the sum of those figures.

**The right question to ask:** "During the interval when RSS grew by 300 MiB, which NMT category grew, which buffer pool grew, which thread count grew, and does the OS show the new pages in anonymous or file-backed mappings?"

## 2. Native Memory Tracking (NMT): What Does It Track?

**NMT** is a feature of the **HotSpot JVM**, enabled at startup:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx512m -jar app.jar
~~~

Or select **-XX:NativeMemoryTracking=detail** if deep allocation-site analysis is needed. NMT is off by default. Once a process has started without NMT, you cannot enable NMT mid-flight using jcmd alone; you must restart with the appropriate option. You can run **jcmd VM.native_memory shutdown** to stop tracking, but you cannot use it to restart NMT.

### 2.1. Summary and Detail

- **summary**: aggregates memory by VM categories such as Java Heap, Class, Thread, Code, GC, Compiler, Internal, Other, Symbol, and Native Memory Tracking. Category names and contents may vary across JDK/HotSpot releases.
- **detail**: adds call sites and virtual memory maps for NMT-tracked allocations. This is neither a per-object Java allocation profile nor an application call stack for every native library malloc.
- NMT adds CPU and memory overhead; Oracle documentation describes performance cost at around **5–10%** depending on workload/config. Enable purposefully and measure actual impact.

### 2.2. Reserved and Committed: Do Not Read as RSS

In NMT output (**illustrative numbers, not mandatory JVM output**):

~~~text
Native Memory Tracking:
Total: reserved=6144MB, committed=850MB

- Java Heap (reserved=512MB, committed=512MB)
- Class     (reserved=1050MB, committed=75MB)
- Thread    (reserved=420MB, committed=35MB)
- Code      (reserved=250MB, committed=45MB)
...
~~~

- **reserved**: **virtual address space** range set aside for a purpose. It can be huge without needing a matching amount of physical RAM—for instance, compressed class space or heap reservations.
- **committed**: memory committed or malloc'd by HotSpot within NMT's scope. Committed does not mean all those bytes are **resident** pages at the exact moment the OS measures; paging, lazy allocation, and OS mechanisms affect how many pages sit in RAM.
- **Java Heap reserved** may correspond to maximum heap config; **Java Heap committed** is what the JVM has committed; **Java heap used** is object/heap usage reported by MemoryMXBean/GC. Do not substitute one number for another.
- **NMT Total** already includes **Java Heap** and other NMT-tracked categories. Do not add NMT Java Heap on top of NMT Total again.

NMT is designed to track **HotSpot/JVM-tracked memory**, not as a total audit tool for every byte in a process. Oracle documentation notes NMT does not fully cover allocations in third-party native code and JDK class libraries; parts of CDS and allocations outside tracked subsystems also have limits. Thus, **RSS rising while NMT stays nearly flat** can happen—that is a signal to investigate further, not conclusive proof of a JNI leak.

### 2.3. NMT Baseline and Diff: Watching Change Instead of One Snapshot

~~~bash
# After the JVM has warmed up and load is fairly steady:
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline

# After a representative load interval:
jcmd <PID> VM.native_memory summary.diff scale=MB

# Only applies when the JVM started with NMT detail:
jcmd <PID> VM.native_memory detail.diff scale=MB
~~~

In a diff report, **+NMB/-NMB** describes changes relative to the baseline of that **NMT run**, not changes in RSS or total leaked object bytes. For example:

~~~text
- Thread (reserved=... +80MB, committed=... +4MB)
- Class  (reserved=... +0MB,  committed=... +32MB)
~~~

These are illustrative numbers. Thread reserved jumping sharply while committed rises slightly suggests additional stack reservations; Class committed rising may come from loading more classes or class metadata. Check class-load/thread counts, workload, and trends before calling it a leak.

**Important:** an NMT baseline is an internal checkpoint; servers, GC, compilers, caches, and class loading may still be warming up after the baseline. Compare checkpoints at roughly comparable load and prioritize **sustained growth** over a one-time startup increase.

## 3. What Does BufferPoolMXBean Measure?

The **java.lang.management.BufferPoolMXBean** API exposes buffer pools published by the JVM via JMX. On HotSpot, you typically see **direct**, **mapped**, and potentially a separate pool for non-volatile mapped buffers depending on JDK/config. Do not hard-code an assumption that every JVM always has exactly two or three pools.

Three core metrics:

| Method | Unit / Meaning | Interpretation Notes |
| --- | --- | --- |
| **getCount()** | Estimated number of buffers in the pool | Not bytes; can vary with cleaners/lifecycles and buffer structure |
| **getTotalCapacity()** | Estimated total capacity of buffers, **bytes** | Logical capacity, not necessarily actual memory allocated |
| **getMemoryUsed()** | Estimated bytes of memory the JVM is using for the pool | May differ from totalCapacity due to alignment/allocator; **-1** if the JVM has no estimate |

Illustrative example:

~~~text
name=direct count=200 totalCapacity=134217728 memoryUsed=134217728
name=mapped count=12  totalCapacity=268435456 memoryUsed=268435456
~~~

Numbers are not prescriptive. If direct **memoryUsed** climbs alongside direct buffer count, investigate creation sites, ownership, and lifetimes of direct buffers. If the mapped pool grows, inspect file mappings and mapping lifecycles; file-backed pages may or may not be resident in RAM at the same moment.

**BufferPoolMXBean does not measure "all off-heap".** Allocations self-managed by native libraries, JNI mallocs, native arenas, thread stacks, compiler buffers, and many other regions fall outside these pools. A direct buffer may also wrap memory allocated by another library or shared in ways not inferable from count; interpret JVM-reported pool numbers according to the implementation.

### 3.1. Why BufferPoolMXBean and NMT Cannot Be Added Together

Part of direct buffers' backing memory may appear simultaneously in **the appropriate NMT VM category** and in **BufferPoolMXBean**. Two figures can **count the same memory** from two perspectives. Conversely, a buffer type or library may fall outside one of the two sources' scope.

Do not use:

~~~text
RSS = NMT Total committed + BufferPoolMXBean direct memoryUsed
RSS = Java heap used + direct capacity + sum of thread stackSize
native leak = RSS - NMT Total committed
~~~

These are not valid accounting identities. They can both **double-count** and omit components, while mixing committed, resident, and capacity concepts.

### 3.2. Special Cases to Watch For

- **DirectByteBuffer:** ByteBuffer.allocateDirect typically uses off-heap backing memory; the Java wrapper remains a Java object. When the wrapper becomes unreachable, backing memory may be freed via Cleaner/GC mechanisms, **with no guarantee of immediate release upon dropping the reference**.
- **MappedByteBuffer:** pool metrics measure mapped buffers per the JVM; they do not equal resident file pages. Large mapped capacity can coexist with low RSS if most pages have never been accessed.
- **Slice/duplicate views:** views do not necessarily allocate new backing memory. Do not multiply the number of ByteBuffer objects on the heap by capacity to estimate physical memory.
- **getMemoryUsed() = -1:** display as "unknown/unavailable"; do not force it to 0 or convert it into a positive number.
- **-XX:MaxDirectMemorySize:** can cap a set of HotSpot/JDK direct buffer allocations, but **does not cap all native memory in the process**. Do not use it in place of a container memory limit.

## 4. Thread Counts: How Java, JVM Native, and OS Count Differently

### 4.1. ThreadMXBean Counts Platform Threads

In **Java 21**, **ThreadMXBean.getThreadCount()** reports the number of **live platform threads**, including daemon and non-daemon. **It does not count virtual threads.** getPeakThreadCount() and getTotalStartedThreadCount() also refer to platform threads.

A **platform thread** typically maps to an OS thread, whereas **virtual threads** are scheduled by the JVM onto carrier/platform threads without needing one dedicated OS thread per virtual thread. Hence, a large virtual thread count does not imply a matching native OS thread count. Virtual threads still have stack/state memory, but their cost/mapping differs from platform threads.

### 4.2. NMT Thread Is Not Thread Count Times -Xss

The NMT **Thread** category tracks JVM-observed thread components, including thread structures, stack reservations/commits, and related structures. On HotSpot, **-Xss** relates to Java platform thread stack size configuration, yet:

- **Reserved** thread stack does not mean all of it is **committed**.
- **Committed** stack does not mean all of it is resident in RAM.
- The JVM has many native/internal threads, and thread stacks include guard pages, alignment adjustments, and platform-specific defaults.
- Native threads created by libraries outside the JVM may be counted by the OS without appearing fully in ThreadMXBean/NMT.
- A program with many virtual threads must not have its cost estimated as **virtual-thread-count × -Xss**.

The formula **threads × -Xss** helps hypothesize the *scale of stack address reservations* for platform threads, not measure real RAM.

### 4.3. Cross-Checking Three Counting Sources

| Source | Example Metric | Interpretation |
| --- | --- | --- |
| Java **ThreadMXBean** | getThreadCount() | Live **platform threads** managed by the JVM in Java 21 |
| NMT **Thread** category | threads #...; reserved/committed | Thread resources tracked by HotSpot |
| Linux **/proc/PID/status** | Threads | Number of kernel tasks/native threads belonging to the process at read time |

OS Threads can exceed ThreadMXBean due to GC/compiler/service/internal/native-library threads. Counts captured at slightly different times can also differ due to short-lived threads. **Do not infer a leak simply because the three numbers differ.** Look for an upward **trend** in threads and match it against NMT Thread, OS native thread counts, thread names/stacks, and executor types.

## 5. OS Metrics: RSS, VSZ, PSS, and Containers

To know whether a process is consuming excessive physical memory or hitting runtime limits, inspect OS metrics. The examples below target **Linux**, using the real JVM PID.

### 5.1. /proc/PID/status

~~~bash
PID=12345
grep -E '^(Name|VmSize|VmRSS|RssAnon|RssFile|RssShmem|VmSwap|Threads):' /proc/"$PID"/status
ps -o pid,rss,vsz,nlwp,cmd -p "$PID"
~~~

- **VmSize / VSZ:** total virtual address space of the process; can be large from heap reserve, class space reserve, thread stack reserve, and mappings. Large VSZ **does not mean large RAM usage**.
- **VmRSS / RSS:** process pages currently resident as counted by the OS. RSS includes anonymous, file-backed, and shared mappings; some pages may be shared with other processes.
- **RssAnon:** anonymous resident portion; often useful for seeing touched heap/native malloc/stacks, though **it does not separate Java heap from all native allocations**.
- **RssFile:** resident file-backed mappings, including shared libraries and file mappings; can rise when reading files without a heap leak.
- **RssShmem:** resident shared-memory mappings.
- **VmSwap:** eligible pages swapped out per Linux's definition; not an independent "swapped heap portion".
- **Threads / nlwp:** native OS thread count at measurement time.

**Measurement quality note:** Linux documentation notes that VmRSS in **/proc/PID/status** may not be completely exact due to accounting optimizations. When deep analysis or proving small differences is needed, use **smaps/smaps_rollup** and consider read overhead.

### 5.2. /proc/PID/smaps_rollup and PSS

~~~bash
grep -E '^(Rss|Pss|Pss_Anon|Pss_File|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Swap):' \
  /proc/"$PID"/smaps_rollup
~~~

Available fields depend on the kernel. **RSS** here is total resident mappings; **PSS (Proportional Set Size)** divides shared pages by the number of sharing processes, useful for estimating one process's contribution when shared libraries/mapped files are shared. **Private_Dirty/Private_Clean** isolate process-exclusive pages; **Shared_*** reflects shared pages.

PSS is **not JVM native memory**, and smaps_rollup **does not label individual OS pages with Java objects/BufferPoolMXBean**. To locate specific mappings, read **/proc/PID/smaps** or **/proc/PID/maps** and use native profiling tools. Read permissions on some /proc files may be restricted in containers or production systems.

### 5.3. Container/cgroup: Another Accounting Layer

Commonly seen with **cgroup v2**:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
~~~

Paths depend on cgroup mounts and namespaces; do not assume this is the right cgroup for a PID when running from a different host. **memory.current** records charges for the **entire cgroup**, which can include multiple processes in the cgroup and file cache per accounting rules; it is **not the JVM's RSS alone**. **memory.max** is the cgroup limit if configured, and may be the string **max** when unlimited in that field.

A service with a small heap can still hit **container OOM** from total heap, native memory, page cache, memory charged to other processes, and limits. Inspect OOM events, container metrics, and relevant cgroup rules before simply raising **-Xmx** or shrinking **-Xss**.

### 5.4. Comparing on Windows and macOS

If not running Linux, use the OS's corresponding tools to read **working set/resident**, **private bytes/commit**, and **thread count**, such as Process Explorer/Performance Monitor on Windows or Activity Monitor/vmmap on macOS. Names and semantics do not match Linux RSS/PSS identically; when comparing across OSes, state the exact metric type and source rather than labeling different quantities generically as "RAM".

## 6. Runnable Java 17+ Example: Reading Three Metric Groups Inside the Process

The program below reads the Java heap from MemoryMXBean, BufferPoolMXBeans, and platform-thread count. It retains **four 1 MiB direct ByteBuffers**, allowing you to collect NMT and OS metrics before and after allocation in **the same process**.

Create **NativeMemoryCompare.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class NativeMemoryCompare {
    private static final List<ByteBuffer> HELD = new ArrayList<>();
    private static final long MIB = 1024L * 1024L;

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT, "%.2f MiB", bytes / (double) MIB);
    }

    private static void snapshot(String phase) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("SNAPSHOT: " + phase);
        System.out.println("  heap used=" + mib(heap.getUsed())
                + ", committed=" + mib(heap.getCommitted()));
        System.out.println("  platform threads=" + threads.getThreadCount());

        List<BufferPoolMXBean> pools = new ArrayList<>(
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class));
        pools.sort(Comparator.comparing(BufferPoolMXBean::getName));

        for (BufferPoolMXBean pool : pools) {
            System.out.println("  pool=" + pool.getName()
                    + ", count=" + pool.getCount()
                    + ", capacity=" + mib(pool.getTotalCapacity())
                    + ", memoryUsed=" + mib(pool.getMemoryUsed()));
        }
    }

    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in));

        System.out.println("PID: " + ProcessHandle.current().pid());
        snapshot("before allocation");

        System.out.println("PHASE 1 READY - collect NMT baseline, then press Enter");
        input.readLine();

        for (int i = 0; i < 4; i++) {
            HELD.add(ByteBuffer.allocateDirect(1024 * 1024));
        }
        System.out.println("PHASE 2 READY - allocated four 1 MiB direct buffers");
        snapshot("after allocation");

        System.out.println("Collect NMT diff and OS metrics, then press Enter");
        input.readLine();

        HELD.clear();
        System.out.println("PHASE 3 READY - cleared retained references");
        snapshot("after clear");

        System.out.println("Press Enter to exit");
        input.readLine();
    }
}
~~~

Compile and run in an interactive terminal with **HotSpot/OpenJDK 17+**:

~~~bash
javac NativeMemoryCompare.java
java -Xmx128m -XX:NativeMemoryTracking=summary NativeMemoryCompare
~~~

The landmark lines **guaranteed to be printed by the program in exact order** (interleaved with PID, snapshots, and dynamic pool lines):

~~~text
PHASE 1 READY - collect NMT baseline, then press Enter
PHASE 2 READY - allocated four 1 MiB direct buffers
PHASE 3 READY - cleared retained references
Press Enter to exit
~~~

**There is no fixed byte/thread output**: PID, available pools, class loading, allocator, GC, and JVM activity vary by runtime. You should see the direct pool increase after the allocation step on typical HotSpot builds; **do not force the result to equal exactly 4 buffers / 4 MiB** if the JVM already has other buffers or implementation differences.

**HELD.clear() does not synchronously free native backing memory.** It only drops strong references from the List. Reclamation depends on whether wrappers remain reachable elsewhere, GC/Cleaner, and implementation rules. Do not use the moment of clear() to claim RSS/memoryUsed must drop immediately.

### 6.1. Synchronized Sampling for Each Phase

In a second terminal, substitute the actual PID just printed by the program:

~~~bash
PID=12345

# When PHASE 1 READY appears, record current figures and set the NMT baseline:
date -Is
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|Threads):' /proc/"$PID"/status
~~~

Press Enter in the Java terminal to perform allocation. When **PHASE 2 READY** appears, sample right away:

~~~bash
date -Is
jcmd "$PID" VM.native_memory summary.diff scale=MB
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|Threads):' /proc/"$PID"/status
grep -E '^(Rss|Pss|Private_Dirty|Private_Clean):' /proc/"$PID"/smaps_rollup
~~~

Press Enter once more for **HELD.clear()**, take a third sample, and note whether the direct pool and OS RSS have changed yet. **Do not force GC just to produce a prettier result**; the goal is to see the difference between reference lifecycle, NMT accounting, and residency. If you run an experiment with GC for comparison, explicitly note **GC was requested**, whether GC actually ran, and the sampling timestamp.

To view deeper NMT allocation sites in another run, switch to **-XX:NativeMemoryTracking=detail** at startup and then use **jcmd PID VM.native_memory detail** or **detail.diff**. You cannot switch summary → detail directly on a running JVM.

## 7. How to Read a Combined Metric Set

Ideally each checkpoint captures:

| Group | Minimum Fields | Meaning |
| --- | --- | --- |
| Time / Conditions | Timestamp, PID, JDK, cgroup, traffic or phase | Ensures data is comparable |
| Heap | Heap used/committed/max, GC activity | Checks whether heap grows persistently |
| NMT | Total committed/reserved, Java Heap, Thread, Class, Code, GC, Other, and diff | Pinpoints which JVM subsystem is changing |
| Buffer pool | Per pool: name, count, capacity, memoryUsed | Checks whether direct/mapped buffers are growing |
| Threads | Java platform thread count; OS native thread count; NMT Thread | Detects thread/stack growth |
| OS | RSS, VSZ, anonymous/file-backed, PSS/private, swap when present | Observes resident and mapped memory |
| Container | memory.current/max, OOM events, cgroup memory | Checks why the workload is hitting limits |

To avoid false positives, observe **at least two checkpoints under comparable load**, and if possible **baseline after warm-up**. Sample often enough to see trends without running jcmd/detail/smaps so frequently that they add significant overhead.

### 7.1. Common Patterns

**Pattern A — RSS and NMT Java Heap grow together; post-GC heap used also grows.** Investigate **heap retention**: long-lived caches/collections/objects, class histograms, heap dumps, and Paths to GC Roots. NMT Java Heap committed alone does not prove a leak; examine live object sets and application lifecycles.

**Pattern B — RSS and BufferPoolMXBean direct grow; heap used stays relatively stable.** Investigate **direct buffers**: allocation hotspots, owners, pools, release/Cleaner lifecycles, and direct buffer limits. Compare against NMT categories only for cross-checking; do not assume NMT Other = direct bytes on every JDK.

**Pattern C — NMT Thread reserved grows, OS Threads and ThreadMXBean grow.** Suspect **platform-thread/pool expansion**. Collect thread dumps and check thread names, thread states, executor queues, and lifecycles. Large reserved growth does not necessarily mean proportional RSS growth.

**Pattern D — RSS jumps sharply while NMT Total committed stays nearly flat, and direct/mapped pools and platform threads are also stable.** Check **/proc/PID/smaps**, anonymous vs. file-backed, JNI/native libraries, malloc arenas, mappings, OS page residency, and cgroup charges. Also consider previously committed pages touched for the first time causing resident growth. **You cannot assert an external-JVM leak** from this discrepancy alone.

**Pattern E — VSZ jumps sharply while RSS/PSS and committed remain stable.** This may simply be additional **address space reservations** (stacks/class space/mappings), not increased physical RAM pressure.

**Pattern F — Container memory.current grows while process RSS does not grow proportionally.** Check **page cache and other processes in the same cgroup**, kernel memory/cgroup stats; do not attribute all of memory.current to a single Java PID.

## 8. Comparative Scenario Table (Hypothetical Figures)

Two checkpoints 30 minutes apart, comparable load and post-warm-up:

| Metric | T0 | T1 | Assessment to Investigate |
| --- | ---: | ---: | --- |
| Java heap used after GC | 180 MiB | 183 MiB | Shows no significant heap retention growth |
| NMT Total committed | 520 MiB | 525 MiB | NMT-tracked VM categories fairly stable |
| BufferPoolMXBean direct memoryUsed | 32 MiB | 33 MiB | Direct buffer pool not growing noticeably |
| ThreadMXBean platform threads | 84 | 85 | No clear Java platform thread expansion |
| Linux Threads | 112 | 113 | Native threads relatively stable |
| Process RSS | 640 MiB | 980 MiB | Process resident memory grew by 340 MiB |
| RssAnon | 480 MiB | 815 MiB | Growth is mainly anonymous |

**Do not conclude "335 MiB native leak".** Anonymous growth may include malloc/JNI allocations uncounted by NMT, previously committed JVM regions touched for the first time, allocators holding pages for reuse, or other native components. Next steps: analyze smaps, native libraries/profilers, load patterns, allocation lifecycles, and time-series data.

Conversely, if during the same interval BufferPoolMXBean direct memoryUsed also grew by ~300 MiB, prioritize investigating direct buffer lifecycles; still verify before claiming one pool accounts for the entire RSS delta.

## 9. Practical Diagnostic Workflow When RSS Climbs or Container OOMs

### Step 1. Lock Down Observation Context

Record PID, actual container/cgroup, JDK version, active GC, `-Xms/-Xmx`, `-Xss` if set, direct memory limit if configured, traffic/request rate, and timestamps. If multiple JVMs exist, never compare RSS of process A with NMT of process B.

### Step 2. Check the Heap First

Observe **post-GC** heap used, committed, GC logs, or JFR if enabled. Steadily rising post-GC heap used points to retention; large heap committed with low used may reflect heap retention policy rather than proving a leak.

### Step 3. Read NMT by Category and Over Time

Use NMT summary/diff to see which **HotSpot subsystems** grow; use detail when call sites are needed and overhead is acceptable. Distinguish normal one-time class loading from continuous Class metadata growth; distinguish NMT Thread **reserved** and **committed**.

### Step 4. Cross-Check BufferPoolMXBean

Collect direct/mapped **count/capacity/memoryUsed** at the same timestamps. If growing, identify who creates and retains buffers. JFR/heap dumps may help locate Java wrappers and reference chains; remember **a heap dump does not show all native backing memory**.

### Step 5. Cross-Check Thread Counts and Stacks

Use ThreadMXBean (platform threads), NMT Thread, and Linux Threads/nlwp. If all rise, check thread dumps, pool sizing, blocked tasks, native library threads, and shutdown lifecycles. On Java 21, many virtual threads do not translate directly to many OS threads.

### Step 6. See Where OS Pages Actually Reside

Inspect RSS/PSS, RssAnon/RssFile/RssShmem, smaps/smaps_rollup, native mappings, and cgroup usage. Only at this step do you have solid grounds to separate anonymous pressure, file-backed mappings, third-party native allocations, or residency changes.

### Step 7. Test a Small Hypothesis and Re-Measure

For example, reduce queue backlog, close/release buffers per lifecycle, bound an unbounded thread pool, or fix JNI allocations. After changes, re-measure under **the same workload and duration**. Conclude only when the chain of evidence aligns: code/lifecycle root cause plus post-fix shifts in NMT/JMX and OS metrics.

## 10. Misconceptions to Avoid

1. **"NMT Total is the process's RAM."** False: NMT tracks HotSpot scope and reports reserved/committed; OS RSS/PSS have different scopes and semantics.
2. **"Native memory = NMT Total − Java Heap."** False: outside NMT's scope sit library native allocations and other memory maps; NMT is not a complete off-heap inventory.
3. **"RSS − heap used = off-heap leak."** False: the difference includes committed-but-unused heap, code/class/GC, stacks, native allocations, file-backed/shared pages, and paging.
4. **"NMT committed + direct memoryUsed + stack size = RSS."** False because it **double-counts** and mixes committed, reserved, capacity, and resident.
5. **"Large MappedByteBuffer capacity equals resident RAM."** False: a mapping can be huge while only a subset of pages sit in RSS.
6. **"BufferPoolMXBean memoryUsed of -1 means zero memory used."** False: it means the estimate is unavailable.
7. **"ThreadMXBean counts Java 21 virtual threads too."** False: that API only counts platform threads; native OS thread counts also include JVM/native internal threads.
8. **"200 threads with -Xss1m are definitely consuming 200 MiB of physical RAM."** False: reservation, commitment, and page residency differ.
9. **"RSS rising while NMT is flat definitely means a JNI leak."** False: check newly touched resident pages, file mappings, native allocator caching, and NMT scope.
10. **"Very high VSZ means OOM is imminent."** False: virtual reservations can be large while RSS/committed stay low; inspect address space limits and actual memory charges.
11. **"Container memory.current is the Java PID's RSS."** False: it is cgroup-wide usage/charge, including other resources depending on config.
12. **"One snapshot is enough to conclude."** False: you need trends, comparable conditions, and lifecycle evidence.
13. **"NMT summary and detail are free measurements."** False: both have overhead; detail belongs in controlled investigation windows.
14. **"GC will always return direct buffer native memory right after clear()."** False: release depends on reachability/Cleaner/GC and can lag; use explicit close/release APIs when resource lifecycles are defined.

## 11. Self-Check Questions

**Question 1.** NMT reports Java Heap **reserved=2 GiB**, **committed=500 MiB**; MemoryMXBean reports heap **used=220 MiB**; RSS=700 MiB. Is anything contradictory?  
**Answer:** No. Reserved is address space, committed is memory the JVM committed, used is active heap usage, and RSS is process resident memory including many other regions. You cannot infer a leak from those four numbers.

**Question 2.** BufferPoolMXBean direct memoryUsed rises by 400 MiB; one NMT category also rises by 400 MiB. Should you add them to get 800 MiB of native usage?  
**Answer:** No. Both sources may reflect the same backing allocations. Cross-check trends and origins rather than summing different accounting frameworks.

**Question 3.** There are 30,000 virtual threads on Java 21, yet ThreadMXBean shows only 120 platform threads and Linux Threads=150. Why?  
**Answer:** Virtual threads do not each own a dedicated OS thread; Java 21 ThreadMXBean counts only platform threads; Linux also counts native/JVM internal threads.

**Question 4.** NMT Thread reserved rose by 500 MiB, while committed rose by only 10 MiB and RSS rose by 6 MiB. Has the process consumed 500 MiB of new RAM?  
**Answer:** No. Reserved is primarily virtual address space, not resident memory.

**Question 5.** NMT, BufferPoolMXBean, and thread counts stay nearly flat, yet RSS and RssAnon climb across multiple comparable load checkpoints. What is the next step?  
**Answer:** Inspect smaps/smaps_rollup and native allocations outside NMT; check JNI/native libraries, allocator caching, and residency, then test a hypothesis under representative load. Do not assert a leak until you find unfreed allocation lifecycles.

**Question 6.** memory.current rises by 600 MiB while process RSS rises by only 50 MiB. Can you blame the remaining 550 MiB on a "JVM native leak"?  
**Answer:** No. Check other processes in the same cgroup, file cache, memory.stat, OOM events, and cgroup accounting rules.

## 12. Verification References

- [Oracle JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html) — scope, tracking levels, overhead, baseline/diff, and limitations.
- [Oracle JDK 21 — Diagnostic Tools / NMT Categories](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html) — reserved/committed, memory categories, and diagnostic workflow.
- [Oracle JDK 21 — BufferPoolMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html) — count, totalCapacity, memoryUsed, and the -1 case.
- [Oracle JDK 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html) — platform threads and virtual-thread scope limits.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — carrier thread model and resources.
- [Linux man-pages — /proc/PID/status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html) — VmRSS, VmSize, RssAnon, RssFile, Threads.
- [Linux Kernel — proc filesystem / smaps](https://www.kernel.org/doc/html/latest/filesystems/proc.html) — RSS/PSS/shared/private and smaps_rollup.
