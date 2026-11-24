# 22.6 Comparing Process Memory, Heap, NMT, and Direct Buffers During Memory Growth

## Objective

A Java service may report heap used steady at 350 MiB while the "process memory" graph climbs from 760 to 1,180 MiB and the container hits its limit. This scenario **does not by itself prove a Java heap leak**, nor does it prove a native memory leak. An investigator needs to know **which memory layer** each data source measures, in **what unit**, at **what point in time**, and whether it **includes or overlaps** with other sources.

In this integrated practice topic, we compare four primary views:

1. **Process memory:** Linux RSS/PSS, virtual size, anonymous/file-backed mappings, native allocations.
2. **Java heap:** used, committed, max, GC behavior, live set, and the meaning of post-GC numbers.
3. **HotSpot Native Memory Tracking (NMT):** reserved/committed per JVM category, baseline/diff, what NMT covers, and where its gaps are.
4. **Direct buffers:** `ByteBuffer.allocateDirect`, `BufferPoolMXBean`, bytes/capacity/count, off-heap lifecycle, and its *possible* relationship with NMT.

After this lesson, you will be able to build time-aligned snapshot tables, avoid double counting, formulate sound hypotheses when RSS rises out of step with heap/NMT/direct, collect data with `jcmd`/JMX/`proc`/cgroup, and design a verification test without worsening memory pressure.

**Scope:** Java 17+ on HotSpot/OpenJDK; `jcmd` command examples per JDK 21; Linux and cgroup v2 when running in containers. NMT category names and coverage can differ across JDKs/vendors. Do not treat the balance equations below as "byte-exact accounting": measurements differ in **definition and timing**.

## 1. The Four Views Do Not Live in Four Disjoint Buckets

Conceptual model:

~~~text
Host / kernel / container memory accounting
|
+-- Java process
|   |
|   +-- Java heap: objects, arrays, heap regions
|   +-- JVM runtime native areas:
|   |     metaspace, class metadata, code cache,
|   |     thread structures/stacks, GC data, JIT compiler...
|   +-- Off-heap / direct / native:
|   |     direct ByteBuffer storage, native libraries,
|   |     malloc arenas, JNI allocations, mappings...
|   +-- File-backed / shared mappings:
|         libraries, mapped files, shared pages...
|
+-- Other processes in the same memory cgroup
+-- File/page cache and some kernel charges
~~~

Mapping each meter onto the model:

- **Java heap used:** the portion of heap the JVM reports as used under memory pool/MXBean definitions; not the entire process memory.
- **Heap committed:** virtual memory the JVM has committed for the heap per API/runtime; not automatically the physical pages currently resident.
- **NMT:** tracks many **internal HotSpot** allocations and regions; it includes the Java Heap category alongside VM-tracked native areas. Hence NMT total **is not "native outside heap"**.
- **Direct `BufferPoolMXBean`:** estimates usage of JVM-reported buffer pools; part of this off-heap storage may already be accounted for inside an NMT category on your runtime implementation. It is not an amount you can always blindly add on top.
- **Process RSS:** physical memory pages currently resident and mapped into the process, including anonymous and file-backed/shared pages; it can cover pages belonging to the heap, some native areas, and mappings. RSS does not reflect all virtual reserved space.
- **Cgroup `memory.current`:** memory charged to the cgroup, which can include file cache, kernel memory, and other processes; **it is not identical to a single PID's RSS**.

Therefore the following calculation is **model-broken**:

~~~text
total_memory = process_RSS + heap_used + NMT_committed + direct_used
~~~

These quantities overlap or use different accounting methods. If RSS already includes resident heap pages, adding heap to RSS double-counts. If NMT total already includes committed Java Heap, adding heap committed to NMT total double-counts. If direct allocations appear under an NMT category, adding direct pool to NMT total can double-count again.

## 2. Standard Definitions Before Comparing

| Quantity | Typical Source | Unit | Question Answered | What **Not** to Infer |
| --- | --- | --- | --- | --- |
| Heap used | MemoryMXBean / JMX / GC telemetry | Bytes | Heap currently in use per runtime | Total process RSS or retained live objects |
| Heap committed | MemoryMXBean / JMX | Bytes | How much heap capacity the JVM committed | All committed pages are physically resident |
| Heap max | MemoryMXBean / `-Xmx` | Bytes or undefined | Heap limit advertised by the runtime | Container memory limit |
| NMT reserved | `jcmd VM.native_memory` | KB/MB/GB | Address space/virtual reservations tracked by NMT | Physical RAM in use |
| NMT committed | `jcmd VM.native_memory` | KB/MB/GB | Memory HotSpot subsystems report as committed | Equals RSS or covers every `malloc` in the process |
| Direct pool `memoryUsed` | `BufferPoolMXBean` | Bytes, may be `-1` | Estimated memory used by buffer pool | All off-heap/JNI/native memory |
| Direct pool `totalCapacity` | `BufferPoolMXBean` | Bytes | Total logical capacities in the pool | Physical RSS or exact native allocations |
| `VmRSS`/RSS | `/proc/PID/status`, `smaps_rollup`, `ps` | kB/KiB depending on tool | Resident pages mapped to the process | Exclusively private memory of the process |
| PSS | `/proc/PID/smaps_rollup` | kB | Shared pages apportioned proportionally to the process | JVM heap used |
| `VmSize`/VSZ | `/proc/PID/status`, `ps` | kB | Total virtual address space mappings/reservations | Physically allocated RAM |
| `memory.current` | cgroup v2 | Bytes | Memory charged to the entire cgroup | RSS of the Java PID alone |
| `memory.stat` anon/file | cgroup v2 | Bytes | Selected charge buckets in the cgroup | One-to-one match with NMT categories |

**Units:** NMT with `scale=MB` and Linux utilities may define MB/KiB differently from dashboard labels. Consistent convention in this lesson's examples: **1 MiB = 1,048,576 bytes**; if command output uses kB/KiB, record the conversion before subtracting. Decimal MB vs. binary MiB mismatches will not explain huge gaps, but they can make tables inaccurate.

## 3. Java Heap: Used, Committed, Max, and Live Set

### 3.1. Heap Used Is Not Always Live Memory

Heap used is the capacity currently occupied as reported by the JVM; it can include objects that are already unreachable **but not yet collected by GC**. You cannot simply take heap used at two timestamps and claim the retained live set changed by that exact difference.

To evaluate **heap leaks / retention**, prioritize:

- Time series of **heap usage after comparable GC cycles**, especially steady-state old-generation live set.
- Allocation rate, GC frequency, object counts/types, classloaders, and cache occupancy.
- Heap dumps/dominator trees when needed and permitted with enough storage/RAM; distinguish reachable objects from native areas.
- Matching workload, traffic, payloads, warm-up, GC collector, and `-Xmx`.

A sawtooth heap graph rising and falling back to baseline may reflect normal allocation pressure, not a leak. Conversely, a post-GC baseline climbing steadily under equivalent work warrants investigating object retention.

### 3.2. Heap Committed Does Not Equal Heap Used or RSS

The JVM can commit a large heap region to optimize allocation/GC while used bytes stay low. Moving from `used=350 MiB` to `used=355 MiB` does not mean process RSS grew by only 5 MiB; native allocations and other resident pages can still change.

Heap committed also **does not necessarily equal the physical pages faulted into RAM**. On Linux, reserve/commit/`mmap`/huge pages/transparent huge pages and page touching affect RSS. The JVM may keep heap committed from shrinking immediately when used drops after GC; behavior depends on the collector and uncommit policy.

### 3.3. `-Xmx` Is Not the Container Maximum Memory

`-Xmx` generally caps maximum Java heap, **not** metaspace, code cache, direct buffers, thread stacks, JNI/native `malloc`, JIT/GC bookkeeping, file mappings, or page cache charged to the cgroup. A container with `memory.max=1.5 GiB` and `-Xmx=1 GiB` can still be `OOMKilled` when native/cgroup charges exceed headroom.

Under memory pressure, inspect both heap **and** process/cgroup metrics; never blindly raise `-Xmx` when RSS or `memory.current` is already near the limit.

## 4. Process Memory on Linux: RSS, VSS, and PSS

### 4.1. What Is RSS?

Resident Set Size (RSS) approximates pages currently in RAM mapped into the process. It typically includes:
- anonymous resident pages: heap, some native allocations/stacks;
- file-backed resident pages: shared libraries, mapped files;
- shared-memory pages;
- other regions per kernel accounting.

In `/proc/PID/status`, `VmRSS` typically corresponds to **`RssAnon + RssFile + RssShmem`** per kernel interface. RSS from `proc/status` may not be a microsecond-exact snapshot at every instant due to kernel accounting mechanics; `smaps_rollup` offers deeper breakdown though reading it has overhead.

**RSS is not just native heap.** It includes resident heap pages, code, stacks, mappings, and some shared pages. If two JVMs map the same library, both processes' RSS can include those shared pages; summing RSS across multiple processes can double-count physical pages.

### 4.2. Huge VSS/`VmSize` Is Often Normal

Virtual address space includes reserved areas, mapped-but-not-resident regions, class space reservations, guard pages, thread stack reservations, and more. A JVM with `VmSize` 8 GiB and RSS 700 MiB **does not** mean it uses 8 GiB of RAM. That is the core difference between **reserved virtual** and **resident physical**.

Similarly, never use NMT "Total reserved = several GiB" to conclude a container is about to hit its RAM limit. Look at committed, RSS, cgroup usage, and memory pressure.

### 4.3. PSS/USS When Many Shared Mappings Exist

- **PSS (Proportional Set Size):** resident shared pages divided proportionally among processes sharing them; useful for attributing cost across multiple processes.
- **USS/private RSS** (tool-dependent, often derived from `Private_Clean + Private_Dirty` in `smaps`): resident pages not shared under the tool's accounting.
- **RSS:** counts resident mappings of the process, including shared pages.

PSS helps when multiple JVMs share libraries/file maps, yet it is **not** equivalent to NMT committed, and you should not ignore tolerances/timestamps when comparing against cgroups.

### 4.4. Read-Only Commands for the Exact PID

On a host or namespace with permission, substitute the Java process PID:

~~~bash
PID=12345
grep -E '^(Name|Pid|PPid|VmSize|VmPeak|VmRSS|VmHWM|RssAnon|RssFile|RssShmem|Threads):' \
  "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
ps -p "$PID" -o pid,etime,rss,vsz,cmd
~~~

- `/proc/PID/status` gives a coarse snapshot, including `VmHWM` (RSS high-water mark), though HWM does not tell you **when** the peak occurred.
- `smaps_rollup` reports `Rss`, `Pss`, shared/private dirty/clean, and related counters when supported by the kernel. Polling it very frequently adds overhead.
- `ps` has its own units for `rss`/`vsz` (typically KiB); verify with the OS/tool man page.
- Some container environments forbid reading `/proc/PID` of other processes; never escalate privileges or run policy-violating tools to bypass restrictions.

If the Java process **died** and its PID was reused, reading `/proc/PID` now inspects a different process; always verify start time and process identity.

## 5. Memory Cgroups: Why `memory.current` Can Differ from RSS

In cgroup v2, `memory.current` reflects memory charges of the cgroup and its descendants per kernel semantics, which can include:

- anonymous memory of processes in the cgroup;
- file/page cache charged to the cgroup;
- kernel memory such as slab/sock/pagetables/kstack per kernel/controller;
- other processes/sidecars inside the same cgroup scope.

It is neither "Java-heap-only RAM" nor necessarily equal to summed RSS. In container orchestration, charts labeled "container memory usage", "working set", "RSS", or "usage_bytes" use differing definitions and cache exclusions depending on the collector. **Record the raw metric name**, not just a dashboard label.

Typical read-only files once **the exact cgroup v2 is verified**:

~~~bash
cat /proc/self/cgroup
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

On a host, the shell's `/sys/fs/cgroup` may belong to a **different** cgroup than the Java PID. Inside a container, cgroup namespaces can display paths differently from the host. Check `/proc/PID/cgroup`, mount info, and Kubernetes/container ID mappings; never use cgroup figures from a **different scope** to explain the Java process.

Specifically:
- **`memory.current`:** usage at read time, not process RSS.
- **`memory.max`:** configured hard limit (`max` if unlimited) of the cgroup; not `-Xmx`.
- **`memory.peak`:** peak per kernel/FD semantics; carries no timestamp telling when the peak happened.
- **`memory.stat` anon, file, slab...:** breaks down selected cgroup charge buckets; counters vary by kernel.
- **`memory.events` oom/oom_kill/max:** pressure/kill event counters; check deltas and verify cgroup/timeframe rather than treating a cumulative counter as proof of a brand-new OOM.

If `memory.current` climbs while Java RSS stays flat, the cause may be page cache, sidecars, kernel charges, or another process. Conversely, Java RSS rising while cgroup usage barely shifts can also happen due to reclaim/cache and other mechanisms; check the exact metrics and timestamps.

## 6. What Does Native Memory Tracking (NMT) Measure and Miss?

### 6.1. Nature of NMT

**NMT is a HotSpot feature that tracks memory regions/allocations managed internally by the JVM**, not a scanner of the process's entire virtual address space. It reports categories such as:

- Java Heap;
- Class / Metadata / Compressed Class Space;
- Thread;
- Code;
- GC, Compiler, Internal;
- Symbol, Native Memory Tracking, Arena Chunk;
- Other and additional categories depending on JDK/collector.

The category list and classification can change across JDK versions. NMT may not accurately track all allocations from third-party JNI/native libraries or runtime components outside HotSpot tracking hooks. Oracle explicitly documents limitations around third-party native code and certain JDK class-library allocations. **If NMT stays flat while RSS climbs, that does not rule out a native memory leak.**

### 6.2. NMT Is Off by Default and Must Be Enabled at Startup

Startup example **for environments where overhead can be evaluated**:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx768m -jar app.jar
~~~

Or choose `detail` when call-site evidence is needed and conditions allow:

~~~bash
java -XX:NativeMemoryTracking=detail -Xmx768m -jar app.jar
~~~

- **`summary`:** aggregates by category; usually the best starting point.
- **`detail`:** tracks finer granularity for tracing VM allocation sites, with higher overhead; evaluate against workload.
- **`off`:** default on many HotSpot builds; leaves no historical NMT data to reconstruct after an incident.

NMT **cannot be switched from `off` to `summary`/`detail` on an already running process via `jcmd` alone**. Supported mechanisms can shut NMT down at runtime, but you cannot assume tracking can be turned back on inside the same process once off. NMT adds CPU/memory overhead; Oracle documentation cites roughly **5–10% performance overhead** under certain conditions, not a fixed SLA.

### 6.3. Reserved and Committed Are Not Equal

An illustrative NMT summary example:

~~~text
Total: reserved=4500MB, committed=740MB
- Java Heap (reserved=2048MB, committed=512MB)
- Class     (reserved=1050MB, committed=45MB)
- Thread    (reserved=420MB,  committed=40MB)
- Code      (reserved=260MB,  committed=35MB)
- ...
~~~

These are **hypothetical aggregate numbers for illustration**, not complete output from a specific JDK; the abbreviated categories **do not sum to Total** because not all categories are listed. `reserved=4,500 MB` does not mean the process uses 4,500 MB of RAM; `committed=740 MB` also does not equal `RSS=740 MB`. NMT committed follows VM commit accounting, whereas RSS depends on currently resident pages and other allocations/mappings.

Inspect:
- Absolute values per category;
- Committed delta relative to a **baseline on the same PID**;
- Reserved delta solely to understand address-space growth;
- Breakdown across categories (Java Heap, Thread, Class, Code, GC, Other);
- Context of JVM flags, collector, JDK version, threads/classes, and workload.

**Never take NMT total and add heap committed**: Java Heap is already included in NMT total when the report contains that category.

### 6.4. Baseline/Diff: Comparing Trends Instead of Disconnected Snapshots

When NMT was enabled from startup:

~~~bash
PID=12345
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
# Reproduce workload or observe a clearly recorded window.
jcmd "$PID" VM.native_memory summary.diff scale=MB
~~~

If `detail` was enabled from startup and deeper investigation is justified:

~~~bash
jcmd "$PID" VM.native_memory detail.diff scale=MB
~~~

- Baseline marks a reference **at the moment it is taken**, without retroactively capturing state before NMT was enabled.
- `summary.diff` shows net deltas per category since the baseline; allocations and frees can cancel out, so snapshots do not replace event history.
- Never diff across two different JVMs/PIDs and call it a leak in the same process.
- NMT numbers can shift from GC/heap expansion, JIT warm-up, classloading, or native allocators; separate expected warm-up shifts from continuous growth.
- Ensure comparable workload/configuration; take the baseline after warm-up if investigating steady-state retention.

## 7. Direct `ByteBuffer` and `BufferPoolMXBean`

### 7.1. Are Direct Buffers in Heap or Native Memory?

`ByteBuffer.allocateDirect(capacity)` returns a **Java object on the heap** describing the buffer, while its primary data backing storage typically lives **outside the Java heap**, in memory managed by the JVM/native allocator depending on implementation. Hence heap used may grow only slightly when an application creates many direct buffers with large total capacity, while process RSS or cgroup memory still rises.

This is a key mechanism in NIO, network frameworks, file I/O, and zero-copy-oriented paths. However:
- Not every native allocation is a direct buffer.
- Not every `ByteBuffer` lives off-heap: `ByteBuffer.allocate(...)` creates a heap buffer.
- `MappedByteBuffer`/file mappings are a different kind of mapping, not identical to the direct pool.
- Direct buffer wrapper objects may stay reachable due to caches/pools/references; reclaiming native storage depends on object lifecycle and runtime cleanup mechanisms, **and does not necessarily happen instantly** when the application drops a reference.

### 7.2. `BufferPoolMXBean` Exposes Three Distinct Metrics

Java exposes `BufferPoolMXBean` via:

~~~java
ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
~~~

Common pools on HotSpot are **direct** and **mapped** (and possibly others). For each pool:

- **`getCount()`:** estimated number of buffers in the pool;
- **`getTotalCapacity()`:** estimated total logical capacity in bytes;
- **`getMemoryUsed()`:** estimated memory the JVM is using for the pool in bytes; may **return `-1`** if an estimate is unavailable.

`MemoryUsed` and `TotalCapacity` **need not be equal** due to alignment, allocator overhead, and implementation details. Do not treat capacity as exact "direct memory RSS"; do not treat count as live allocation count across every library because pooling/slicing and implementation details vary.

### 7.3. Direct Pool Does Not Equal All Off-Heap

Many native allocations go through JNI, library `malloc`, JIT/GC/JVM internals, compression, crypto/TLS, memory-mapped files, or other SDKs. `BufferPoolMXBean` makes no promise to measure all of those. Conversely, some direct `ByteBuffer` allocations can show up inside NMT under a category such as `Other` on a given HotSpot build, yet **never assume NMT `Other` always equals the direct pool**; verify JDK/implementation behavior, measurement timing, and NMT diffs.

Most importantly: if a direct buffer is already reflected in NMT committed or process RSS, adding the direct pool figure on top of NMT/RSS **double-counts**. Use the direct pool as **evidence for a specific allocation class**, not an independent "new line item" to sum into totals.

### 7.4. `MaxDirectMemorySize` Is Not a Ceiling for All Native Memory

Depending on HotSpot and JDK, `-XX:MaxDirectMemorySize` can cap certain allocations made through the corresponding direct-buffer mechanism, but **does not cap all off-heap/JNI/`mmap`/allocator usage**. Do not treat `-Xmx + MaxDirectMemorySize` as total process maximum. When adjusting this limit, check which allocations your libraries actually use and their real behavior; running out of direct memory can throw `OutOfMemoryError` in Java even while heap has free space.

## 8. Measurement Model and the Double-Counting Trap

Suppose four sources simultaneously report:

~~~text
Process RSS             = 1,180 MiB
Java heap used          =   355 MiB
NMT total committed     =   860 MiB
Direct pool memoryUsed  =   218 MiB
~~~

**Do not** compute `1,180 + 355 + 860 + 218 = 2,613 MiB`. That number is meaningless because major portions overlap.

Replace it with four **separate** statements:
1. The OS records 1,180 MiB of resident mappings for the process.
2. The JVM reports 355 MiB used inside the heap at that snapshot.
3. NMT reports 860 MiB committed across HotSpot-tracked categories, including committed heap.
4. `BufferPoolMXBean` reports an estimated 218 MiB for the direct buffer pool (if supported by the implementation).

Each number answers its own question:
- **Is the application approaching process/container memory limits?** → RSS, cgroup usage, `memory.max`, and pre-OOM trend.
- **Are Java objects being retained?** → post-GC heap, old generation, heap dumps/retained sets.
- **Which HotSpot subsystem grew?** → NMT `summary.diff`, categories Thread/Class/GC/Code/Java Heap/Other.
- **Are direct buffers contributing?** → `BufferPoolMXBean` direct metrics, connection/pool counts, reference retention, and NMT category correlation if present.

Avoid the formula "`unexplained native = RSS − heap used − NMT committed − direct`". Because the metrics use different accounting rules, that subtraction can turn negative or positive depending on page residency, shared mappings, kernel caches, and NMT coverage; **the remainder is not automatically a native leak**.

## 9. Practice Scenario: Process Grows 420 MiB While Heap Used Barely Moves

A service handles many NIO connections and maintains buffer pools for network traffic. Two snapshots are collected on **the same PID**, post warm-up, same JDK, same cgroup, under matching load points. All numbers below are **hypothetical** and normalized to MiB to practice reasoning.

| Metric | T0 | T1 after 30 min | Delta |
| --- | ---: | ---: | ---: |
| Process RSS | 760 | 1,180 | +420 |
| Heap used | 350 | 355 | +5 |
| Heap committed | 512 | 512 | 0 |
| Heap max (`-Xmx`) | 768 | 768 | 0 |
| NMT total committed | 680 | 860 | +180 |
| NMT category Other committed | 80 | 250 | +170 |
| Direct pool `memoryUsed` | 48 | 218 | +170 |
| Direct pool `totalCapacity` | 48 | 218 | +170 |
| Direct pool `count` | 120 | 540 | +420 |
| Cgroup `memory.current` | 980 | 1,420 | +440 |
| Cgroup `memory.max` | 1,536 | 1,536 | 0 |
| Average RPS | 800 | 800 | 0 |

Because the snapshots are 30 minutes apart, deltas do not show when each MiB was allocated. Process RSS rose 420 MiB while NMT committed rose only 180 MiB; the metrics do not "contradict each other" because NMT committed and RSS **have different scopes and semantics**.

### 9.1. Reading the Table in the Right Order

**Observation 1 — RSS climbs toward the limit.** Process RSS rose +420 MiB, container `memory.current` rose +440 MiB, leaving only 116 MiB below `memory.max` at T1 (`1,536 − 1,420`). This is a real operational risk, though `memory.current` is not RSS and can include page cache/kernel/other-process charges.

**Observation 2 — Heap used barely changed.** Heap +5 MiB, heap committed unchanged. This does not support "all +420 MiB came from Java objects filling heap used", though you still cannot declare heap retention completely problem-free if snapshots were not aligned by GC phase/live set.

**Observation 3 — NMT sees part of the growth.** Total committed +180 MiB, with Other +170 MiB. That is a signal to drill down: seeing Other grow does not by itself prove direct buffers.

**Observation 4 — Direct pool grew in step.** Direct `memoryUsed` +170 MiB, capacity +170 MiB, count climbed. This aligns with a hypothesis of **direct-buffer pool/retention growth** and could explain **part** of the NMT Other shift on this implementation. Never add +170 (direct) and +170 (Other) into +340 MiB without proving they are disjoint.

**Observation 5 — An accounting gap remains.** RSS +420, NMT committed +180. You cannot immediately label the remaining +240 MiB an "untracked native leak". It could be allocator arenas, already-committed pages faulting into residency, file-backed mappings, JNI/native allocations, or timing skew across snapshot collection. You need `smaps_rollup`, `/proc/PID/status`, `memory.stat`, and proper native evidence.

### 9.2. Properly Scoped Preliminary Conclusion

> Over 30 minutes on the same JVM PID, RSS grew +420 MiB while heap used stayed nearly flat, NMT committed rose +180 MiB (mostly Other +170 MiB), and direct buffer pool `memoryUsed` rose +170 MiB. There is solid basis to investigate **direct-buffer growth** as a contributing factor; data is not yet sufficient to declare a leak or blame the entire RSS jump on direct buffers. Container `memory.current` is close to `memory.max`; inspect buffer ownership/lifecycle and other memory mappings before raising heap or shrinking memory limits.

This conclusion cites sources and limits; it is far better than "NMT missed 240 MiB so JNI is leaking" or "direct buffers used 218 MiB, adding to RSS makes 1,398 MiB".

### 9.3. Why Correlation Is Not Yet a Leak

Pools can grow up to a concurrency high-water mark and then plateau; a bounded buffer cache may intentionally retain memory to avoid allocations. Buffers may be held by active connections; buffer count can rise when traffic mix/payloads change even at identical RPS. Ask further:

- Did open connections/HTTP2 streams, request sizes, or in-flight messages increase?
- Does the direct pool **plateau** under steady workload, or keep growing unboundedly?
- Once connections/batches close and load drops, are buffers returned to the pool or cleaned up per lifecycle?
- Is there reference retention in a cache/pool/map/listener? Is there a leak in Netty/driver/native transport?
- Is there allocator chunk fragmentation or memory not immediately returned to the OS even after buffers are released?
- Did SDK/JDK/GC, pool configuration, or library versions change?

Do not force `System.gc()` to try proving direct buffers "must drop immediately"; GC/cleaners, pooling, and native allocator release are asynchronous, and forcing GC distorts measurements.

## 10. Additional Data to Arbitrate the RSS Increase

### 10.1. Inspecting `/proc/PID/status` and `smaps_rollup` Before/After

From T0 → T1:
- `RssAnon` spikes: think heap pages, direct/native `malloc`, thread stacks, anonymous mappings, and similar areas; **do not** jump straight to a direct leak.
- `RssFile` spikes: think mapped files, shared libraries, process-attached page cache; inspect `smaps` by path and mapping.
- `RssShmem` spikes: examine the corresponding shared memory/`mmap` mechanism.
- `PSS` and `Private_Dirty` rise: clarify true per-process resident footprint and shared vs. private memory.
- `VmSize` rises while RSS stays flat: likely only virtual reservations growing, not immediate physical RAM pressure.

Use NMT diff concurrently to see which HotSpot categories changed. If NMT is flat while `RssAnon` rises, prioritize checking third-party JNI/native `malloc`, allocator arenas, and resident transitions unreflected by NMT. **Never replace all hypotheses with one subtraction.**

### 10.2. What Does Cgroup `memory.stat` Add?

If `memory.current` grew +440 MiB, inspect kernel-specific keys:
- `anon` rises → likely user anonymous memory from processes;
- `file` rises → file/page cache/mapped file charges;
- `slab`, `sock`, `kernel_stack`, `pagetables`, or other kernel components rise → kernel charges;
- sibling processes/sidecars in the cgroup may also consume memory.

A pod whose Java RSS is relatively steady while `memory.current` climbs due to file cache/sidecars is entirely plausible. NMT does not measure cgroup-wide page cache.

### 10.3. Memory Pressure and OOMKill

At T1 `memory.current=1,420 MiB`, `memory.max=1,536 MiB`, leaving about 116 MiB of headroom at that snapshot. However, headroom is no guarantee against OOM: memory can spike suddenly, and kernel charging/reclaim behavior and concurrent workloads change. If an `OOMKilled` occurred:
- read the container's last termination reason for the exact container ID;
- read cgroup `memory.events` `oom_kill` delta and kernel logs if still available;
- confirm memory usage/peak prior to crash;
- never use the new PID or post-restart cgroup as a substitute snapshot for the dead process.

Heap dumps or NMT attaches cannot run against a process already killed by `SIGKILL`; preparing telemetry **before an incident** is part of the practice.

## 11. Repeatable Measurement Workflow: T0, T1, T2

### Step 1 — Identify the Exact Target and Limits

Record service, build, JDK vendor/version, PID + start time, container ID/pod UID, node, `Xms`/`Xmx`, `MaxDirectMemorySize` if set, NMT level, GC, thread count, direct-buffer/pool config, `memory.max`, and cgroup path.

**Never** pair NMT from a new PID with RSS from an old PID after a restart. If multiple JVMs share one pod, container `memory.current` cannot automatically be blamed solely on one JVM.

### Step 2 — Pick Comparable Measurement Conditions

T0 after warm-up; T1 while memory is climbing; T2 after the load/batch finishes or during a stabilization phase. Record:
- exact UTC timestamp;
- RPS, request mix, connection count, in-flight count, payload sizes, batches;
- GC phase near snapshot (heap used before vs. after GC);
- deploys, traffic spikes, autoscaling, and native library state.

Even at the same RPS, if open connections tripled, the samples are not strictly equivalent.

### Step 3 — Capture All Four Groups Together

1. JMX heap used/committed/max and GC metrics;
2. NMT summary/diff (if enabled);
3. direct/mapped `BufferPoolMXBean` count/capacity/memoryUsed;
4. Process `/proc/PID/{status,smaps_rollup}`, cgroup `memory.current`/`memory.stat`/`memory.events`.

Running a sequence of commands takes time; log each snapshot timestamp instead of claiming "simultaneous to the millisecond" when collected sequentially.

### Step 4 — Compute Deltas **Within Each Column**

`RSS_T1 − RSS_T0`, `HeapUsed_T1 − HeapUsed_T0`, `NMTCommitted_T1 − NMTCommitted_T0`, `DirectUsed_T1 − DirectUsed_T0`, `CgroupCurrent_T1 − CgroupCurrent_T0`.

Only then inspect **temporal correlation** and mechanistic consistency, rather than summing deltas into a "total delta".

### Step 5 — State Hypotheses and Falsifiers

For example:
- Direct retention: direct pool grows and connections/buffers are not freed after load; falsified if the pool plateaus/drops while RSS keeps rising.
- Heap retention: post-GC old-gen trend rises; falsified if live set stays stable across comparable cycles.
- Native leak outside NMT: RSS/`RssAnon` rises while NMT/direct/heap stay flat; verify via native allocator profiling, JNI ownership, or `smaps`.
- Page cache/cgroup growth: `memory.stat` file/slab rises without matching process RSS growth; confirm via OS/controller evidence.
- Thread explosion: thread count and NMT Thread committed/virtual stack rise; check thread dumps and pool bounds.

### Step 6 — Run Small Experiments and Measure the Whole System

If suspecting direct buffers: measure before/after bounding connection pools, fixing buffer caches, reducing retained references, or closing lifecycles properly; verify throughput, latency, and CPU/GC do not regress. If suspecting third-party native code: use allocator profiling suited to the exact libc/library in staging before production.

### Step 7 — Report with Confidence Levels

Separate:
- **Observed:** which metric rose by how much, from which source, in which window;
- **Hypothesis:** which region or allocator likely caused the increase;
- **Falsifier:** what measurement would disprove the hypothesis;
- **Decision:** observe, reproduce, canary rollout, rollback;
- **Limitations:** NMT disabled, missing T0, skewed timestamps, mismatched cgroup scope...

## 12. Practical Commands: `jcmd` and JMX

### 12.1. Running JVM with NMT Enabled at Startup

~~~bash
java -version
jcmd -l
PID=12345

jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
# After a clearly recorded workload window:
jcmd "$PID" VM.native_memory summary.diff scale=MB
~~~

Notes:
- `jcmd` attach usually requires matching user/permissions, JVM support, and target PID visibility in the namespace.
- `GC.heap_info` prints JVM heap info, though formatting varies by collector/version.
- NMT summary/diff works only if NMT was enabled; when disabled, lost historical data cannot be recovered.
- Set the baseline in a **steady state**, avoiding comparing startup JIT/classloading against steady state and calling it a leak.
- Do not call `GC.heap_dump`, `GC.class_histogram`, or `GC.run` carelessly in production. Heap dumps can pause the app, consume I/O/disk, and expose sensitive data; some diagnostic operations alter GC/state and skew comparisons.

### 12.2. NMT Not Enabled?

If the process is running with NMT off, you cannot simply use `jcmd` to turn on `summary` "from now on" without restarting the JVM in a supported way. You still have:
- JMX heap, direct `BufferPoolMXBean`, and thread/class metrics;
- `/proc/PID/status`, `smaps_rollup`, and cgroup;
- application pool counters, GC logs/JFR if already active;
- OS/native allocator diagnostics within authorized bounds.

Plan to enable NMT on a canary/staging redeploy to capture controlled T0/T1 data; never mass-restart production just to add one metric.

### 12.3. `BufferPoolMXBean` via JMX

Buffer pool `ObjectName` values on the JVM typically look like:

~~~text
java.nio:type=BufferPool,name=direct
java.nio:type=BufferPool,name=mapped
~~~

Attributes like `Count`, `TotalCapacity`, and `MemoryUsed` can be scraped via an approved JMX agent/metrics exporter. Verify actual names/attributes rather than assuming every JVM exposes `direct` or `mapped` with identical semantics. Specifically, `MemoryUsed` can return `-1` and must be handled as "unknown", not coerced to `0`.

## 13. Runnable Java 17+: Reading Heap and Direct Pool in a Real JVM

Example **`MemoryViewProbe.java`** uses standard `java.management` and `java.nio` APIs. It uses no internal `sun.*` APIs and requires no external libraries. The program allocates an **8 MiB direct buffer** in a single lab run to illustrate the difference between a heap array and direct-buffer storage, without causing an OOME or trying to force GC to clean memory.

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Locale;

public final class MemoryViewProbe {
    private static final int MIB = 1024 * 1024;

    private static long directUsed() {
        List<BufferPoolMXBean> pools =
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);

        for (BufferPoolMXBean pool : pools) {
            if ("direct".equals(pool.getName())) {
                return pool.getMemoryUsed();
            }
        }
        return -1L;
    }

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.1f", bytes / (double) MIB);
    }

    private static void snapshot(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        long direct = directUsed();

        System.out.printf(
                Locale.ROOT,
                "%s heap-used=%s MiB, heap-committed=%s MiB, "
                        + "direct-pool-used=%s MiB%n",
                label,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(direct));
    }

    public static void main(String[] args) {
        snapshot("before");

        byte[] heapArray = new byte[2 * MIB];
        ByteBuffer direct = ByteBuffer.allocateDirect(8 * MIB);
        heapArray[0] = 7;
        direct.put(0, (byte) 9);

        snapshot("after");
        System.out.println("heap-first=" + heapArray[0]);
        System.out.println("direct-first=" + direct.get(0));

        // Keep both objects reachable up to this point.
        java.lang.ref.Reference.reachabilityFence(heapArray);
        java.lang.ref.Reference.reachabilityFence(direct);
    }
}
~~~

Compile/run:

~~~bash
javac MemoryViewProbe.java
java MemoryViewProbe
~~~

**The two data-check lines** always output the exact same values on a successful run:

~~~text
heap-first=7
direct-first=9
~~~

The program also prints two before/after snapshot lines whose exact numbers **depend on JDK, heap/GC, allocation alignment, background activity, and `BufferPoolMXBean` implementation**, so do not invent fixed stdout numbers for those lines. In a typical HotSpot run, `direct-pool-used` may rise by roughly 8 MiB; however that is not strictly guaranteed because the metric is an **estimate** and other allocations can occur concurrently.

Lessons from the code:
- `byte[]` is an object/data on the heap; the `ByteBuffer` wrapper lives on the heap while its backing direct storage lives off-heap.
- Heap used may not change by exactly 2 MiB due to GC/allocator behavior; never treat a one-shot snapshot as a live-set measurement.
- Direct pool uses a standard API, yet **does not report RSS** and does not capture all JNI allocations.
- `reachabilityFence` prevents the compiler from treating the two references as dead before the end of the demonstration; it **does not** force memory release.

## 14. Runnable Java 17+: Computing Deltas Without Double Counting

The second example processes **the hypothetical table from section 9**, producing **completely deterministic** output. It needs no `jcmd` or `/proc` access, making it handy for checking reporting format and avoiding bogus "sum the layers" reasoning.

Create **`MemoryDeltaCase.java`**:

~~~java
public final class MemoryDeltaCase {
    record Snapshot(
            long rssMiB,
            long heapUsedMiB,
            long heapCommittedMiB,
            long nmtCommittedMiB,
            long directUsedMiB,
            long cgroupCurrentMiB) {
    }

    public static void main(String[] args) {
        Snapshot t0 = new Snapshot(760, 350, 512, 680, 48, 980);
        Snapshot t1 = new Snapshot(1180, 355, 512, 860, 218, 1420);

        System.out.println("RSS delta MiB="
                + (t1.rssMiB() - t0.rssMiB()));
        System.out.println("Heap used delta MiB="
                + (t1.heapUsedMiB() - t0.heapUsedMiB()));
        System.out.println("Heap committed delta MiB="
                + (t1.heapCommittedMiB() - t0.heapCommittedMiB()));
        System.out.println("NMT committed delta MiB="
                + (t1.nmtCommittedMiB() - t0.nmtCommittedMiB()));
        System.out.println("Direct pool delta MiB="
                + (t1.directUsedMiB() - t0.directUsedMiB()));
        System.out.println("Cgroup current delta MiB="
                + (t1.cgroupCurrentMiB() - t0.cgroupCurrentMiB()));
        System.out.println("Do not sum overlapping memory views.");
    }
}
~~~

Run on JDK 17+:

~~~bash
javac MemoryDeltaCase.java
java MemoryDeltaCase
~~~

**Exact** stdout:

~~~text
RSS delta MiB=420
Heap used delta MiB=5
Heap committed delta MiB=0
NMT committed delta MiB=180
Direct pool delta MiB=170
Cgroup current delta MiB=440
Do not sum overlapping memory views.
~~~

**Important:** The deltas are not disjoint components to sum. For example, NMT +180 MiB may already include the direct +170 MiB growth on a specific implementation; seeing direct and NMT rise closely together is a signal **to verify with evidence**, not proof of strict equality.

## 15. Using NMT Properly When the Direct Pool Grows

Suppose NMT `summary.diff` shows:

~~~text
Total: committed=860MB +180MB
- Java Heap (committed=512MB)
- Other     (committed=250MB +170MB)
- ...
~~~

This is an **abbreviated mock output** illustrating delta figures; remaining categories are omitted and exact wording varies across JDKs.

Workflow:
1. Verify NMT was enabled at T0; output is **`summary.diff` against the same baseline**, not two different processes.
2. Capture direct pool `memoryUsed`/`count`/`totalCapacity` in **the same window**.
3. If `Other` grew +170 and `Direct` grew +170, record the hypothesis "likely direct backing memory classified under `Other`".
4. Run a controlled test: keep workload steady, shrink/close buffer holders per lifecycle, and watch how **all three** — direct pool, `Other`, and RSS — change.
5. If direct pool drops while NMT `Other` stays flat, check allocator retention, category mapping, sampling timing, and other allocations.
6. If NMT `Other` drops while RSS stays high, physical pages may not be returned to the OS yet, file mappings may have grown, or a non-NMT source exists.
7. If both stay flat while RSS grows, investigate `/proc/smaps` and third-party native code.

**Never assert NMT `Other` = `ByteBuffer.allocateDirect`** or NMT total = heap + direct. NMT categories and what gets tracked vary by JDK, libraries, allocators, and allocation paths.

## 16. Minimum Evidence Bundle for an Incident

| Source | When to Collect | Used For | Key Warning |
| --- | --- | --- | --- |
| PID/start time/build | T0, T1, T2 | Ensure same JVM | Restarts invalidate cross-run comparisons |
| JMX heap used/committed/max | T0, T1, T2 with GC context | Heap usage/commit trends | Used is not automatically live retained set |
| GC logs/after-GC occupancy | Continuous | Retention vs. allocation pressure | GC/collector phases differ |
| NMT summary/diff | T0 baseline, T1/T2 | JVM internal categories | Cannot recover if off at startup |
| `BufferPoolMXBean` direct/mapped | T0, T1, T2 | Buffer count, capacity, usage | Estimate, may be `-1`, not all off-heap |
| `/proc/PID/status` | T0, T1, T2 | RSS, `RssAnon`/`RssFile`/`RssShmem`, threads | Point-in-time, process identity, accuracy limits |
| `/proc/PID/smaps_rollup` | Triggered | PSS, private/shared/mappings | Overhead/permissions; avoid polling continuously |
| cgroup `memory.current`/`stat`/`events` | T0, T1, T2 | Container charges/limits/cache/pressure | Scope may include sidecars/other processes |
| Workload metrics | Continuous | RPS, bytes, connections, queues/batches | Do not claim leak without matched load |
| JVM flags, pool configs | Every deploy | `-Xmx`, NMT, direct sizing/pooling | Config changes invalidate baselines |

**Store data with UTC timestamps** plus environment, service, pod/container ID, host node, and PID labels. Never collect snapshots "over 5 minutes" and claim they represent the same instant; timing gaps matter when GC and buffer recycling happen quickly.

## 17. Classifying Common Growth Patterns

### 17.1. RSS Rises, Heap Used Rises, After-GC Baseline Rises

Primary hypothesis: Java object retention or growing live data set. Check old-gen occupancy, dominator tree, static maps/caches, request/context leaks, classloader retention, and workload. Still do not ignore native areas: the JVM can expand heap **and** direct buffers concurrently.

**Falsifier:** post-GC heap stays flat under identical workload across multiple cycles while RSS grows mainly in `RssAnon` outside heap mappings in `smaps`; pivot the investigation.

### 17.2. RSS Rises, Heap Steady, Direct Pool and NMT `Other` Rise Together

Primary hypothesis: direct-buffer growth or related allocator behavior. Check Netty/NIO/JDBC/network caches, byte buffer lifetimes, connection counts, in-flight requests, and pooled chunk retention. Do not call it a leak if it grows up to a cap, plateaus appropriately, and shrinks when load drops.

**Falsifier:** closing connections/releasing pools in the lab clearly drops direct `memoryUsed`, yet RSS continues rising under another native library; gather native allocator evidence.

### 17.3. RSS Rises, NMT `Thread` Rises, Thread Count Rises

Hypothesis: unbounded thread creation or misconfigured thread pools. Each thread typically has native stack reservations/commits and runtime structures, though `Thread` **reserved** does not equal resident stack RAM. Check `/proc/PID/task` count, Java thread dumps, pool bounds, virtual threads vs. platform threads, NMT `Thread` committed, `RssAnon`, and container limits.

**Do not** count `Thread` reserved for 1,000 threads as physical RAM used. Virtual threads manage stacks differently from platform threads; never assume 1 MB of OS stack per thread across the board.

### 17.4. RSS Rises, NMT `Class`/Metaspace Rises, and Loaded Classes Rise

Hypothesis: classloader leak, dynamic proxy/generation, repeated in-process redeploys, script/bytecode generation, or legitimate class growth. Check loaded/unloaded class counters, classloader references, metaspace committed/used, and JDK class metadata.

**Do not** treat large `Class` reserved as a leak if committed stays flat; compressed class space typically reserves a large virtual address range.

### 17.5. RSS Rises While NMT/Direct/Heap Stay Relatively Flat

Investigate:
- `malloc`/JNI/agent/native codec/crypto/compression allocations outside NMT;
- native allocator fragmentation/arenas, memory not returned to OS;
- anonymous/file mappings or page residency;
- other processes in the cgroup, kernel/page cache when looking at cgroup usage;
- metric mismatches or non-comparable snapshots.

**Flat NMT does not disprove a native leak**, especially in third-party libraries. Use an appropriate native memory profiler in the same time window rather than inventing subtraction formulas.

### 17.6. Cgroup `current` Rises While Java RSS Stays Steady

Prioritize `memory.stat`: file/page cache, slab/sock, other processes/sidecars, OOM group scope, filesystem activity. Check pod-level/container-level labels and working-set metric definitions. **Do not** raise heap or shrink direct allocations if data shows the growth lies outside the Java PID.

### 17.7. `VmSize`/NMT Reserved Jumps Sharply While RSS/Committed Does Not

This can be virtual address reservation, stack reserve, class space, or mappings. Unless address-space exhaustion or commit failures occur, large virtual reservations alone are not evidence of physical memory pressure. On 32-bit or under strict VA limits reservations can pose other issues; this lesson focuses on common 64-bit Java 17+ environments.

## 18. When Is Direct Memory Freed?

Practical subtlety: a Java direct buffer has a **wrapper object** on the heap while its backing storage has a native lifecycle. Once the wrapper becomes unreachable, runtime cleanup/GC mechanisms can reclaim it per implementation; however:
- timing is not necessarily immediate;
- pools/caches may intentionally retain references;
- views/slices/duplicates may still point to the backing storage;
- native libraries may manage their own ownership/release semantics;
- allocators may keep arenas/chunks for reuse even after `free`.

Do not judge a leak from one snapshot "right after the method returns". Place **measurement point T2 after workload/connection lifecycles finish**, allow stabilization time, and inspect buffer metrics alongside OS/RSS trajectories. Never use `System.gc()` as a standard ritual to "force direct memory to 0"; it does not guarantee the native allocator returns pages to the OS and distorts benchmarks.

With frameworks using reference-counted buffers (such as certain networking libraries), follow actual `release`/`retain` APIs and enable the framework's leak detector per policy. Standard `ByteBuffer.allocateDirect` does not share the exact release protocol of every framework.

## 19. Why Does NMT Committed Grow Less Than RSS?

Do not treat the gap as a mystery bucket. Sources of divergence include:

1. **Coverage:** NMT does not fully track native allocations from libraries outside HotSpot.
2. **Resident vs. committed:** physical pages can start getting touched inside already-committed regions while NMT committed delta stays zero.
3. **Shared/file-backed mappings:** RSS includes file-backed pages not represented the same way in NMT.
4. **Allocator accounting:** `malloc` arenas/retained pages and differences between `alloc`/`free` vs. RSS returned to the OS.
5. **Time skew:** NMT, JMX, `/proc`, and cgroup read at slightly different instants.
6. **Different scope:** cgroup `current` spans multiple processes/kernel/cache; NMT covers only the target JVM.
7. **Units/rounding:** KB/MB, MiB, and dashboard aggregation.
8. **Collector/JDK behavior:** heap uncommit, THP, page touching, GC resizing.
9. **Incomplete snapshots:** partial files, permissions, process restarts, metric scrape gaps.

To decide, examine **time-aligned trends and mechanistic fit**, not a sum-subtraction equation.

## 20. Preventing `OOMKilled`: Memory Budgeting for a Java Container

A practical budget covers:
- heap max per `-Xmx` or ergonomic sizing;
- metaspace/class metadata and code cache;
- JIT/GC structures;
- platform thread stacks;
- direct buffers and native allocators;
- JNI/agents/third-party libraries;
- mappings/page cache/kernel charges;
- peak workload/payloads, spikes, and safety headroom.

There is no single rule like "`-Xmx` equals 80% of memory limit" that works for every service. An app with heavy NIO/direct pools needs different headroom than a compute-bound app using no native libraries. Measure under **peak representative load**, not just idle startup.

Example: `memory.max=1,536 MiB`, `Xmx=768 MiB`. Heap max does not guarantee 768 MiB remains available for native use. If direct pools + thread stacks + filesystem cache + kernel charges grow quickly, the cgroup can still hit `memory.max`. Preventing OOM may require bounding pools, reducing retained buffers, tuning connection concurrency, limiting workloads/caches, or raising resource limits after capacity evaluation — **never blindly raising `-Xmx`**.

Control actions:
- alert on cgroup `current / memory.max`, RSS, direct pool, post-GC heap, and NMT diffs;
- verify cgroup scope and restart metadata;
- bound concurrency/queues/buffer ownership;
- use canary rollouts, measure p99/throughput/GC/CPU, and keep rollback ready.

## 21. When Do You Need a Heap Dump vs. Native Tooling?

| Question | Appropriate Tool | Risks/Limitations |
| --- | --- | --- |
| Which Java objects are still reachable? | Heap dump + dominator tree, JFR object allocation/old object (if enabled) | Pause/disk/PII; heap dumps do not measure native `malloc` |
| Which HotSpot subsystem grew? | NMT `summary.diff`/`detail.diff` | Must be enabled at startup; excludes full third-party native coverage |
| How much is the direct pool holding? | `BufferPoolMXBean` metrics + framework pool instrumentation | Estimates; excludes non-pool off-heap |
| Which JNI/native allocations outside NMT grew? | Native allocator profiler, `malloc`/eBPF/traces in authorized environments | Overhead/permissions/scope complexity; sensitive data |
| Which mappings own process resident pages? | `/proc/PID/smaps_rollup`, `smaps`, `pmap` | Point-in-time, kernel accounting, shared pages |
| Where do container charges come from? | cgroup `memory.current`/`stat`/`events`, runtime metrics | Scope spans multiple processes/kernel |
| Did an OOM kill happen? | Kernel logs + cgroup `oom_kill` delta + container termination reason | Post-restart metrics may lose evidence |
| Which code path allocates direct buffers? | Application allocation tracing, JFR/native instrumentation per library/API | Sampling bias, request context correlation |

**Never take a heap dump to directly explain all of RSS.** It helps when suspecting Java object retention or wrapper references pinning backing memory, but does not capture all native allocations. For off-heap libraries invisible in the heap, collect native/OS evidence.

## 22. Wrong Decisions and How to Fix Them

### Mistake 1 — "Heap used 350 MiB, RSS 1,180 MiB, so 830 MiB native leak"

Subtraction is invalid: RSS includes resident/committed heap pages, mappings, and shared pages; heap used is not resident heap size; native areas may be steady baseline. Concluding a leak requires **growth over time** proven disproportionate to workload or lacking valid release.

### Mistake 2 — "NMT reserved 4 GiB, container only 1.5 GiB, so OOM is guaranteed"

Reserved virtual address space differs from committed/resident physical memory. Inspect `memory.current`/RSS/NMT committed and limits; huge reserved space alone is not enough.

### Mistake 3 — "NMT committed 860 + direct 218 = 1,078 MiB native"

NMT total already includes Java Heap; direct bytes may be tracked inside an NMT category; total and direct are not disjoint. Compare categories and pools, **do not sum**.

### Mistake 4 — "NMT is flat so Java isn't raising RSS"

NMT has coverage limits, notably third-party JNI/native; committed-vs-resident differences also exist. Check OS mappings and native allocator evidence.

### Mistake 5 — "Direct pool count went up so it's definitely a leak"

Pools can grow to a valid high-water mark as concurrency/payloads rise; still check for plateaus, owner references, and behavior after load/connections close. Count/capacity/`memoryUsed` over a timeline beat a single count reading.

### Mistake 6 — "GC just ran, direct memory must drop to 0"

Direct buffers have native/cleaner lifecycles and pooling; GC does not promise immediate off-heap release. Freed allocations may also keep resident pages before returning to the OS.

### Mistake 7 — "Container `memory.current` equals Java RSS"

Cgroups include file cache/kernel charges and may contain sidecars/other processes. Read `memory.stat`, verify cgroup scope, and check metric definitions.

### Mistake 8 — "Raise `-Xmx` to cure `OOMKilled`"

If the kernel killed the container because total cgroup usage exceeded the limit, raising heap max under an unchanged limit can **shrink native headroom**. Identify the source of memory growth first.

### Mistake 9 — "One snapshot is enough"

Snapshots before/after GC or across restarts cannot be compared directly. Record identical PID, time window, workload, units, and GC state; prefer time series.

### Mistake 10 — "Enable detail NMT and heap dumps on all production nodes"

NMT and heap dumps add overhead and disk/latency impact, especially under memory pressure. Use canary/staging or low-intrusion methods with proper permissions, rate limits, retention, and rollback plans.

## 23. Auditable Investigation Sheet Template

~~~text
# Java memory growth comparison

Service / build / JDK vendor+version / collector:
PID + process start time:
Pod UID / container ID / node / cgroup path:
Xms / Xmx / direct memory flags / NMT level:
Incident UTC window:
Workload: RPS, payload, in-flight, connections, batches:
GC phase at measurement (before/after GC):

T0 UTC:
- Process VmRSS / RssAnon / RssFile / RssShmem:
- PSS / smaps private/shared breakdown:
- Heap used / committed / max:
- NMT total reserved / committed:
- NMT category breakdown:
- Direct pool count / capacity / memoryUsed:
- Mapped pool count / capacity / memoryUsed:
- Cgroup current / max / stat anon-file-slab:

T1 UTC (same PID? same workload?):
- All the same measurements
- Each metric delta within its own definition

T2 UTC (post-workload or stabilizing period):
- Same metrics and whether trends plateau/recover

OS/runtime:
- memory.events oom/oom_kill deltas:
- Container termination reason/restart metadata:
- GC logs, after-GC live-set, thread/class counts:

Observed:
Hypothesis A / supporting evidence / falsifier:
Hypothesis B / supporting evidence / falsifier:
Known blind spots (NMT off, -1 pool metric, missing T0...):
Experiment / guardrails / rollback:
Conclusion with confidence level:
~~~

This sheet records evidence **without double counting** and clearly separates direct observations from hypotheses. When collecting snapshots, save raw outputs (not just one copied number) so reviewers can check categories, units, and tool reporting conventions.

## 24. Practice Completion Checklist

- [ ] Verified exact JVM PID/start time, container/cgroup scope, JDK version, GC, and workload.
- [ ] Understood heap used, committed, max, and why heap used is not strictly live set.
- [ ] Understood how RSS differs from virtual memory size, PSS, and cgroup `memory.current`.
- [ ] Did not equate NMT total committed with RSS or "native outside heap".
- [ ] Distinguished NMT reserved (virtual) from committed, never treating reserved as physical usage.
- [ ] Knew NMT must be enabled at startup, with summary/detail levels and baseline/diff on the same JVM.
- [ ] Knew NMT does not cover all JNI/third-party native allocations or all process mappings.
- [ ] Used `BufferPoolMXBean` to read direct/mapped pool count, `totalCapacity`, and `memoryUsed`.
- [ ] Knew `memoryUsed` can be `-1` and capacity is not automatically actual RSS.
- [ ] Did **not sum** heap, NMT total, direct pool, and RSS as independent buckets.
- [ ] Checked T0/T1/T2 under aligned timing/workload and recorded GC state for meaningful comparison.
- [ ] Computed per-metric deltas independently without calling `RSS − NMT` an unexplained leak.
- [ ] Checked `RssAnon`/`RssFile`/`RssShmem` and `smaps_rollup`/PSS when RSS changed.
- [ ] Checked `memory.stat` anon/file/slab and sibling processes when cgroup `current` rose.
- [ ] Inspected thread/class/code/GC/Other categories when NMT committed grew.
- [ ] Checked pool/connection/buffer lifecycles before calling direct growth a leak.
- [ ] Avoided blindly raising `-Xmx` or `MaxDirectMemorySize` when a container nears `memory.max`.
- [ ] Evaluated diagnostic tooling overhead and protected sensitive data in logs/dumps.
- [ ] Defined hypothesis, falsifier, bounded test, and post-change verification metrics.
- [ ] Recorded "insufficient data" when only one snapshot existed or NMT was disabled.

## 25. Conclusion

**Process RSS, Java heap, NMT, and direct buffers are not four same-unit measurements of four disjoint buckets.** Each source observes a different layer with different semantics:

- Heap helps investigate Java objects/GC and Java heap limits.
- NMT helps identify growth across internal HotSpot categories via reserved/committed/baseline/diff.
- `BufferPoolMXBean` exposes direct/mapped buffer pool usage per JVM APIs, though not all off-heap memory.
- Linux `/proc` and cgroups reveal resident pages, memory charges, shared/file mappings, and proximity to real limits.

In the scenario with RSS +420 MiB, heap used +5 MiB, NMT committed +180 MiB, and direct pool +170 MiB, the sound conclusion is **direct buffer growth worth investigating**, not "confirmed 170 MiB leak" and certainly not "NMT missed 240 MiB so there is a native leak". Correlate with PID, timestamps, workload, NMT categories, OS memory mappings, buffer lifetimes, and post-load recovery metrics.

Production-ready workflow:

**Document metric definitions → capture T0/T1/T2 on the same JVM → compute deltas per source → verify category/mapping/cgroup scope → form hypotheses and falsifiers → test small changes → confirm RSS, `memory.current`, GC, direct pool, and SLOs all stabilize.**

### Official References

- Oracle JDK 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle JDK 21 — jcmd (`VM.native_memory`, `GC.heap_info`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `BufferPoolMXBean` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- Oracle JDK 21 — `ManagementFactory` / MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Oracle JDK 21 — Diagnostic Tools and NMT categories: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Linux kernel — `/proc` filesystem, `status`/`smaps`/`smaps_rollup`: https://www.kernel.org/doc/html/latest/filesystems/proc.html
- Linux kernel — Control Group v2 `memory.current`/`stat`/`max`/`events`: https://docs.kernel.org/admin-guide/cgroup-v2.html