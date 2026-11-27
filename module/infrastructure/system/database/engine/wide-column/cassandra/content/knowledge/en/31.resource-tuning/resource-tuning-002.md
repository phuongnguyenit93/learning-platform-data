# Heap, Off-Heap, and Memory Needed by the Operating System

> **Chapter:** Resource Tuning  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed database storing data in a wide-column model. A node's performance depends simultaneously on partition design, CQL queries, replication, compaction, repair, error handling, and request volume from Java applications.

## 1. Objectives and Problem to Solve

A Cassandra node typically runs **one JVM process**, yet it does not consume only Java heap memory. It also requires native/off-heap memory, memory-mapped file regions, and **RAM for the operating system to manage I/O, especially the Linux page cache**. Looking at a heap chart alone and concluding that the node has plenty of RAM left is a dangerous mistake.

After this lesson, you should be able to explain:

1. How **heap**, **off-heap/native memory**, and **OS-managed memory** differ.
2. Why setting **-Xmx** too large can make SSTable reads slower or trigger an OOM kill even without any Java heap error.
3. Which data types Cassandra can keep on the heap, off-heap, or in the page cache, and how read/write paths affect them.
4. How to budget RAM for a node, container, or resource-constrained VM.
5. How to measure, diagnose root causes, and validate configuration changes safely when facing GC pauses, direct memory exhaustion, page cache starvation, or Linux OOM kills.

The guiding principle throughout is: **physical RAM must serve both the JVM and the OS simultaneously**. Increasing the heap only helps when the heap is genuinely the bottleneck; if it steals RAM from the page cache or native regions, overall performance can degrade.

## 2. Memory Map of a Cassandra Node

### 2.1. Memory Layers

| Layer | What Does It Store? | Who Manages / Reclaims It? | Signals to Monitor |
|---|---|---|---|
| **Java heap** | Java objects, part of request state, buffers, and JVM structures; some Cassandra components depending on version/config | JVM, garbage collector (GC) | Heap used/committed/max, allocation rate, GC pauses, post-GC live set |
| **Off-heap / native** | Direct ByteBuffers, native allocations, certain memtable structures or SSTable metadata depending on version/config, network buffers | JVM/native allocator and owning components; not automatically reclaimed by Java heap GC like regular objects | Direct/native usage, memory limits, RSS, native OOM |
| **JVM non-heap** | Metaspace, code cache, thread stacks, various runtime/JIT areas | JVM and OS; each area has different limits and reclamation mechanisms | Metaspace, thread count, native memory tracking |
| **File-backed memory and page cache** | SSTable/index/commitlog data pages cached by the OS; pages mapped via **mmap** if configured | Kernel; clean pages can be reclaimed under memory pressure | MemAvailable, cache activity, major page faults, disk read latency |
| **Kernel, auxiliary services** | Kernel slab, network/socket buffers, filesystem journaling, and monitoring agents, log forwarders, container runtime | Kernel and respective processes | Available RAM, kernel memory, usage of other services |

**Heap is not all of the JVM's RAM.** Likewise, **off-heap does not mean spare RAM for Cassandra**: it already occupies memory outside the heap and can compete with the page cache.

One way to visualize this:

~~~mermaid
flowchart TB
    R["Physical RAM / container memory limit"] --> J["Cassandra Process (JVM)"]
    R --> O["Operating system and other processes"]
    R --> P["Linux page cache and file-backed pages"]
    J --> H["Java heap (bounded by -Xmx)"]
    J --> N["Native/off-heap allocations"]
    J --> M["Metaspace, code cache, thread stacks"]
    J -. "Can memory-map files" .-> P
    O --> K["Kernel, sockets, agents..."]
~~~

The diagram illustrates **memory usage responsibilities**, not strictly disjoint physical regions. File-backed pages mapped into the process can appear in the process's **RSS** **and** in OS cache statistics. Therefore, **never simply add RSS + Cached** to estimate RAM used; doing so can double-count.

### 2.2. Commonly Confused Measurements

- **Heap used:** size of objects currently live/used in the heap, not total resident memory of the process.
- **Heap committed:** amount of heap memory the JVM has committed; may differ from heap used and heap max.
- **-Xmx:** upper bound for the Java heap, **not** the total process or container memory limit.
- **RSS (Resident Set Size):** resident pages charged to the process, including many native and file-backed regions; not a direct measure of a heap leak.
- **VSZ/VIRT:** virtual address space; mapped/reserved regions can be much larger than resident RAM.
- **MemAvailable:** estimate of memory available to allocate to new applications without excessive swapping; more useful than looking solely at the **free** column.
- **memory.current** in cgroup v2: memory usage charged to the cgroup, typically including both anonymous memory and file cache; compare against **memory.max**.

Linux uses idle RAM as cache and reclaims clean pages when needed. **High Cached is not inherently a bug.** Conversely, if cache pages are constantly reclaimed, queries must re-read from disk, hurting latency even though the Java process itself appears healthy.

## 3. Where Is Memory Used on the Read and Write Paths?

### 3.1. Writing Data

A typical write operation:

~~~mermaid
flowchart LR
    A["CQL write from Java application"] --> C["Coordinator"]
    C --> R["Replica"]
    R --> L["Append commitlog (disk / kernel I/O)"]
    R --> T["Update memtable (heap/off-heap per config)"]
    T --> F["Flush"]
    F --> S["SSTable on disk"]
    S --> PC["Subsequent reads may benefit from page cache"]
~~~

A **memtable** is an in-memory write structure; memory allocated to memtables is bounded by Cassandra configuration mechanisms, while whether it uses heap or off-heap depends on the **version and memtable type**. The **commitlog** is a filesystem log; you should not count total commitlog disk space as a heap block. File writes and flushes still place pressure on kernel I/O, buffers, and the page cache.

When a memtable reaches its threshold or needs to flush, Cassandra creates an SSTable. If flushing falls behind the write rate, the number of pending memtables, heap/native pressure, I/O, and write latency can increase. **Increasing the heap does not fix an overloaded disk.**

### 3.2. Reading Data

When reading by partition key, the coordinator selects replicas based on replication, topology, and consistency level. On a replica, Cassandra may consult memtables and relevant SSTables, using index structures, Bloom filters, internal caches, and OS-cached memory.

~~~mermaid
flowchart TD
    Q["SELECT by partition key"] --> R["Replica handles read"]
    R --> M["Check data in memtable"]
    R --> I["Consult metadata, index, Bloom filter..."]
    I --> P{"Are SSTable data pages in page cache?"}
    P -->|Yes| C["Read from RAM / file-backed page"]
    P -->|No| D["Read from storage device"]
    D --> C
    M --> A["Merge data and apply query semantics"]
    C --> A
    A --> Z["Return result to coordinator"]
~~~

This is a conceptual diagram: the actual read path also depends on the version, SSTable format, cache types, and data layout. Certain structures such as **Bloom filters, index summaries, and caches** may use off-heap or different layouts depending on version/configuration. The key point is that **both Cassandra-managed memory and the page cache affect read performance**.

If the heap consumes nearly all RAM, the kernel has little room to keep hot SSTable pages; device reads increase. If off-heap structures and memtables grow unchecked, they can also evict the page cache from memory.

### 3.3. Impact of Query Design

Memory is not tuned by JVM flags alone:

- **Oversized partitions:** increase data volume and read/compaction time; read requests may hold processing state longer.
- **Queries that cannot locate a partition key:** hit many replicas/partitions, raising I/O and processing resource usage.
- **Client loading entire results into a List:** inflates the heap **of the Java application**; meanwhile, many concurrent queries increase memory load on Cassandra.
- **Excessively large page size and concurrency:** increase the number of rows/buffers processed at once. Paging chunks returned data; it does **not** turn an expensive query into a cheap one.
- **Compaction and repair:** place background load on CPU, I/O, and memory buffers; sizing must account for maintenance windows, not just steady-state workloads.

Because Cassandra is distributed, a poorly optimized query can also multiply load across multiple replicas. Inspect the **wide-column data model, partition key, query-driven table design, and consistency level** before concluding that adding RAM is the solution.

## 4. Heap: Sizing by Live Set and GC Behavior

### 4.1. Is a Larger Heap Always Better?

No. A larger heap can delay certain collections, but at the same time it:

1. Takes away RAM that the kernel could use to cache data pages.
2. Increases the memory span GC must manage; pause or CPU consequences depend on the collector, live set, and allocation rate.
3. Masks the fact that the application is allocating too many objects or holding requests too long.
4. Pushes the process closer to the host/container RAM limit if native memory is not accounted for.

Conversely, a heap that is too small can cause frequent GC, difficult promotion/evacuation, higher latency, or **java.lang.OutOfMemoryError: Java heap space**.

**There is no single optimal -Xmx value for every cluster.** Sizing depends on Cassandra/JDK version, collector, core count, disk type, available RAM, hot dataset, partition sizes, and read/write patterns. Historical recommendations for an older JVM version should not be copied verbatim to a new release.

### 4.2. Looking Beyond the Basic Heap Chart

| Metric | Question to Answer |
|---|---|
| Heap used **after** GC | Is the remaining live set steadily climbing or stable? |
| Heap allocation rate | How fast are objects allocated? Are there abnormal requests/batches? |
| GC pause p95/p99/max | Are pauses affecting replica or coordinator latency? |
| GC CPU / frequency | How much resource is GC spending just to maintain the heap? |
| Heap max and committed | Do the limit and current committed size match the running process? |
| Thread count / stack | Are there too many threads, native stacks, or blocked executors? |

For example, **heap used around 45%** is not enough to prove a node is safe. The process might be using large direct buffers, thousands of threads, or experiencing continuous page cache eviction. Conversely, **high heap used right before GC** does not prove a memory leak; check the **post-GC live set** and long-term trend.

## 5. Off-Heap and Native Memory: Reducing GC Pressure While Still Consuming RAM

### 5.1. Why Does Cassandra Use Off-Heap Regions?

Off-heap allocated structures reduce the number of Java objects GC must scan and support efficient I/O operations. Common examples include **direct buffers**, networking components, memtable data, or SSTable read structures, depending on version/configuration.

Trade-offs:

- **Pros:** reduces part of heap and GC pressure; helpful when workloads create many buffers.
- **Costs:** still consumes real RAM; harder to spot when looking only at JVM heap, and can cause native allocation failures, memory fragmentation, or OS-level OOM kills.
- **Lifecycle:** do not assume native regions are reclaimed immediately as soon as a Java reference goes out of scope. Release behavior depends on libraries/allocators and data structure lifecycles.

Regions such as **metaspace, code cache, and thread stacks** also sit outside the Java heap, yet should not be mechanically lumped under "direct memory". They have distinct limits and failure signals.

### 5.2. Do Not Infer All Limits from One Limit

**-XX:MaxDirectMemorySize** bounds JVM direct-buffer allocations, not an absolute cap on **all** native/off-heap allocations, memory mapping, or total RSS. **-Xmx8g** does not mean the process uses only 8 GiB of RAM.

Cassandra's memtable/cache management and the JVM's direct memory management can interact. Before changing any parameter, check **the running version, version-specific configuration docs, and actual effective values**.

A change moving memory from heap to off-heap may improve GC yet still cause **RSS to rise**. If the OS no longer has enough room for the page cache, read latency can degrade. Therefore, measure **GC and I/O together**.

## 6. Memory That Must Be Reserved for the OS and Page Cache

Cassandra frequently accesses large SSTable files; kernel caching of read pages limits physical storage access. When a query misses in memory, SSD/NVMe read speed and compaction state largely dictate that read path's latency.

Stable operation requires RAM for:

- **Page cache / file-backed pages:** holding hot data and indexes; required amount depends on the working set.
- **Kernel and networking:** TCP/socket buffers, filesystem, and kernel data structures.
- **Other processes:** exporters, sidecars, log/monitoring agents, container runtime.
- **Temporary load spikes:** compaction, repair, streaming, bursts in connections and concurrent requests.

**Swap** can introduce unpredictable latency spikes if part of process memory is paged out to disk. Many production Cassandra setups restrict or disable swap per deployment guidelines, though the exact choice must align with operational strategy, cgroups, and fault tolerance; disabling swap is not a substitute for proper RAM sizing. When RAM is genuinely exhausted without swap or other safeguards, the kernel/cgroup may kill the process to reclaim memory.

### 6.1. RSS, Page Cache, and Cgroups Cannot Simply Be Added Together

Suppose monitoring displays:

- Cassandra **RSS = 20 GiB**;
- Linux **Cached = 30 GiB**;
- host has **64 GiB RAM**.

You cannot claim Cassandra is using **20 + 30 = 50 GiB** from those two numbers alone. Part of the file-backed pages may be counted in both RSS and Cached. Use **MemAvailable**, **cgroup memory.current**, **memory.stat**, **smaps_rollup**, and native/heap metrics to separate trends.

In containers, the **cgroup limit** often matters more than total host RAM. A node running on a 128 GiB host might be capped at 16 GiB; setting a 12 GiB heap can still OOM the container once native memory, kernel accounting, and cache are included.

## 7. RAM Budgeting: Concrete Numerical Example

Suppose a Cassandra node **is permitted to use 64 GiB RAM**, stores SSTables on SSD, and runs alongside a few monitoring processes. An initial budget might look like:

| Item | Illustrative Budget |
|---|---:|
| Max JVM heap (-Xmx) | 8 GiB |
| Native/off-heap and JVM non-heap (planning estimate) | 10 GiB |
| Kernel, agents, and operational reserve | 6 GiB |
| **Remaining headroom supporting page cache and burst variance** | **40 GiB** |
| **Total budget** | **64 GiB** |

The arithmetic is **64 − 8 − 10 − 6 = 40 GiB**. This is only an **illustrative allocation scenario**, **not a default "8 GiB heap" recommendation for every 64 GiB node**.

Notes when using this table:

1. **Native** and **kernel** values are workload-based estimates; they can fluctuate sharply, especially during repair/streaming/compaction. Measure to calibrate.
2. **40 GiB is not a hard-reserved page cache partition.** The kernel allocates and reclaims cache dynamically, sharing RAM with other software.
3. If measurements show actual off-heap frequently reaches **18 GiB**, you must reduce expected cache/headroom or revise the resource design.
4. For a container with **memory.max = 24 GiB**, **do not** use total host RAM in your calculation. Rebuild the table from 24 GiB or the lower effective limit.
5. The budget must cover **peak load**, not just averages; keep a safety buffer so sudden bursts do not trigger OOMs.

A planning formula, not a measurement formula:

~~~text
Permitted RAM
  ≈ max usable heap
  + expected native/off-heap and non-heap
  + kernel/agent/overhead
  + headroom for page cache and load spikes
~~~

Do not use the formula above to sum overlapping Linux stats like **RSS** and **Cached**. This is a **responsibility-based budget**, not a method for adding runtime counters.

### 7.1. When Should You Consider Increasing the Heap?

Only after evidence shows that:

- The heap live set approaches the limit, or the JVM repeatedly lacks allocation space.
- GC causes significant pauses/CPU overhead and the issue does not stem primarily from bad queries, hot partitions, or compaction backlog.
- The node retains enough RAM for native memory and page cache after increasing the heap.
- You can test on a canary/test node under representative workload, tracking latency, GC, I/O, memory headroom, and rollback.

If increasing heap helps GC yet **disk read latency rises**, evaluate the page cache impact before keeping the new configuration.

## 8. Observation and Inspection Tools

The following commands apply in Linux and compatible Cassandra/JDK environments. **Do not run every command on production simply because RAM looks high**; select commands based on the operational question and access permissions. Metric names or output fields may vary across Cassandra, JDK, and Linux versions.

### 8.1. Observing Cassandra

~~~bash
# Node overview: heap, off-heap (if shown by version), load, uptime...
nodetool info

# Table statistics: memtable, SSTables, Bloom filter, off-heap, latency...
nodetool tablestats app.events_by_tenant_day

# Running / pending compaction tasks
nodetool compactionstats

# Thread pools and pending tasks
nodetool tpstats

# GC statistics if provided by the version
nodetool gcstats
~~~

The name **app.events_by_tenant_day** is illustrative; replace it with the actual keyspace/table. If your version does not support a specific flag or metric field, use the exact syntax of the running version.

To find why reads are slow, correlate metrics **from at least two sides**: application/driver (p95/p99, timeouts, concurrency) and Cassandra node (heap/GC, compaction, disk I/O, memtables, caches). **Latency rising during compaction** does not by itself prove insufficient heap.

### 8.2. JVM and Process

~~~bash
# Replace <pid> with the actual PID of the Cassandra process.
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info

# Useful data only when the JVM was started with Native Memory Tracking enabled.
jcmd <pid> VM.native_memory summary

# Quick view of resident/virtual memory, subject to access permissions.
ps -o pid,rss,vsz,%mem,cmd -p <pid>
grep -E 'VmRSS|VmHWM|VmSize|Threads' /proc/<pid>/status
~~~

**Native Memory Tracking (NMT)** usually must be enabled at JVM startup (for example via **-XX:NativeMemoryTracking=summary**, depending on the JDK). NMT adds overhead and **cannot track every native allocation from libraries outside the JVM**; therefore, do not treat NMT as a complete audit of all off-heap memory. The **jcmd** tool may also require the same OS user and a compatible JDK version.

When deep RSS breakdown is needed, **/proc/<pid>/smaps_rollup** provides resident/PSS stats and certain breakdowns on supported Linux kernels. Use it for targeted investigation; avoid polling it at high frequency.

### 8.3. Operating System / Container

~~~bash
free -h
grep -E 'MemTotal|MemAvailable|Cached|SReclaimable|SwapTotal|SwapFree' /proc/meminfo

# Cgroup v2; paths vary by deployment environment.
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events

# Kernel logs / OOM events depending on permissions and platform.
dmesg
~~~

On cgroup v1, Kubernetes, or environments with nested cgroups, paths and accounting may differ. **memory.max = max** in cgroup v2 means that cgroup level has no finite limit set; you must still check parent levels. **memory.events** helps detect limit hits, OOMs, and OOM kills for that cgroup.

If the Java application reports **connection reset** or sudden disconnects, also check for node/container OOM kills; a killed JVM may not have time to write an **OutOfMemoryError** stack trace.

## 9. Diagnosis by Symptom

| Symptom | What to Distinguish | Evidence-Based Action |
|---|---|---|
| **Frequent GC, long pauses, high post-GC heap** | Large live set, high allocation rate, too many requests, undersized heap, or leak | Measure allocation/live set; inspect requests and partitions; only adjust heap/GC if RAM headroom exists |
| **java.lang.OutOfMemoryError: Java heap space** | Heap genuinely exhausted, data/objects retained too long | Analyze heap and workload; avoid raising heap before understanding the cause |
| **OutOfMemoryError: Direct buffer memory** | Direct buffer limit/allocation; does not mean heap is full | Inspect direct/native usage, JDK flags, networking libraries, concurrency |
| **Process/container OOM-killed while heap looks low** | RSS/native, cache, cgroup limit, or other processes | Read memory.events, kernel logs, memory.current/max, RSS, and NMT; rebalance total budget |
| **GC is fine, yet reads are slow and disk I/O rises** | Page cache starvation, hot set exceeds RAM, many SSTables, compaction/tombstones | Measure MemAvailable, page faults, disk latency, SSTables/compaction; review access patterns |
| **RSS rises alongside off-heap** | Rising native allocations or resident file-backed pages | Analyze NMT, smaps_rollup, and memory.stat over time; do not immediately call it a leak |
| **Writes slow down when flush/compaction piles up** | Disk throughput, memtable flushes, compaction backlog, commitlog I/O | Check compactionstats, tpstats, disk utilization, and hot partitions |
| **Repair/streaming causes node RAM exhaustion** | Concurrent background jobs consuming I/O, buffers, network, and cache | Coordinate concurrency/maintenance windows; monitor peak load and RAM headroom |
| **Java driver holds many results, app OOMs** | **Application** heap is separate from **Cassandra** heap | Use paging, cap concurrent requests, stream/process row-by-row instead of buffering all |

### Three Diagnostic Traps

**Trap 1 — Seeing large Cached and concluding a RAM leak.** Cache usage can be normal kernel behavior. Check **MemAvailable**, paging/reclaim, I/O latency, and actual memory exhaustion signals.

**Trap 2 — Seeing low heap and concluding the JVM cannot cause an OOM.** Native memory, thread stacks, and mmap/file cache counted toward the cgroup—plus other processes—can still push the node over its limit.

**Trap 3 — Seeing slow reads and increasing the heap.** SSTable reads rely on the page cache and disk; raising the heap can shrink that cache. Inspect queries, partition sizes, SSTables/tombstones, compaction, and OS metrics first.

## 10. Safe Configuration, Changes, and Verification

### 10.1. Finding the Currently **Effective** Configuration

Cassandra and JDK versions can differ in config file locations, default heap sizing formulas, collectors, and option names. Before making changes, record:

- Running **Cassandra** and **JDK** versions.
- Effective **-Xms**, **-Xmx**, GC collector, and direct/native-related flags (verified via **jcmd VM.flags** when appropriate).
- Host/VM and **cgroup** RAM limits, plus other processes sharing the machine.
- Memtable, cache, and related limits **matching the exact Cassandra version**.
- Baseline values: p50/p95/p99 latency, timeouts, GC pauses, RSS, MemAvailable, disk I/O, compaction, and repair state.

The following example JVM flags only illustrate configuration **meaning**, not a fixed recommended setup:

~~~text
-Xms8g    # initial heap size
-Xmx8g    # maximum heap size
~~~

In some Cassandra distributions/versions, heap is set via **cassandra-env.sh**, environment variables, or JVM options files; verify the actual mechanism on the node. Never add duplicate options in multiple places and assume the last one wins.

Parameters such as **memtable_heap_space**, **memtable_offheap_space**, or **memtable_allocation_type** (if supported by your running version) have specific semantics; memtable limits are not total RAM limits, and actual off-heap usage still depends on configuration. Verify effective settings before tuning.

### 10.2. Metric-Driven Tuning Process

1. **Isolate the symptom:** heap OOM, direct/native OOM, cgroup OOM, GC pauses, or page cache starvation? Confirm with multiple metric sources.
2. **Capture a baseline:** on the same workload and time window, save latency, throughput, GC, RSS, MemAvailable, disk I/O, timeouts, and compaction.
3. **Build a RAM budget:** based on real limits and peak load; leave room for kernel, native allocations, and page cache.
4. **Change one related parameter group:** for example heap sizing **or** concurrency/memtable limits; avoid changing multiple factors that prevent attributing the outcome.
5. **Verify on a canary or rolling rollout:** observe reads/writes, retries, GC, I/O, available replicas, consistency, and load during compaction/repair.
6. **Compare against baseline and keep a rollback plan:** accept the change only when it improves the target without degrading other resource metrics or cluster stability.

Never restart all replicas simultaneously just to apply a memory change. Stagger maintenance according to cluster procedures and active consistency levels, verifying replica availability at each step.

## 11. Relationship with the Java Driver, Replication, and Cassandra Operations

A Java **SELECT** query can be paged:

~~~java
// Assume session, prepared, tenantId, and eventDay are already initialized.
var statement = prepared.bind(tenantId, eventDay)
        .setPageSize(100);
var result = session.execute(statement);

for (var row : result) {
    // Process each row; avoid collecting all results into a large List.
    processRow(row);
}
~~~

**Page size = 100** is the page size requested between the driver and server, not a guarantee that the query reads only 100 rows total or uses a fixed maximum amount of memory. Iterating through the full result can still fetch many pages; running too many such queries concurrently pressures both Cassandra nodes and the Java application. In a real app, **processRow** is application-defined, and using **var** requires a supporting Java version.

Additional factors to consider together when tuning RAM:

- **Replication:** each replica consumes resources serving the data it stores; higher replication factors increase storage footprint and cluster-wide maintenance work. Consistency level determines how many responses are required and can affect latency/load, but does not replace RAM sizing.
- **Compaction:** reads/writes many SSTables, consuming CPU, I/O, and memory buffers; plan for peak compaction volume.
- **Repair / streaming:** transfers data between nodes, creating I/O/network pressure and auxiliary memory usage. Maintenance schedules must avoid unnecessarily stacking heavy tasks.
- **Query-driven table design:** well-chosen partition keys/buckets reduce hotspots, read amplification, and per-request data volume.
- **Error handling:** unbounded retries when nodes are resource-starved amplify the outage. Throttle concurrency, bound timeouts, and keep idempotency aligned with each write type.

In summary, **memory tuning only makes sense alongside the data model, query rate, and cluster-wide background work**.

## 12. Practical Exercises and Self-Check Questions

### Exercise A — Finding Risk in a 24 GiB Container

A Cassandra container has **memory.max = 24 GiB** and **-Xmx = 18 GiB**. Measurements show native/non-heap and sidecar processes can reach **5 GiB** before counting page cache and remaining overhead.

- How much theoretical budget remains?
- When compaction/repair pushes native usage higher than expected, what failure can occur?
- Why is **Java heap used at only 50%** still not enough to conclude it is safe?

**Hint:** 24 − 18 − 5 = **1 GiB** before page cache and uncounted overhead; the margin is tiny and can trigger cache pressure or an OOM kill. **-Xmx** is the heap cap, not total process usage. Base decisions on resident/current usage and actual peak loads.

### Exercise B — Slow Reads After Increasing the Heap

A node's heap is increased from **8 GiB** to **16 GiB**. Afterward, GC pauses drop, yet disk read latency and SELECT p99 rise.

Explain a plausible hypothesis and propose how to verify it.

**Hint:** RAM may have been shifted from the page cache to the heap, increasing disk reads. Compare **MemAvailable**, page faults, cache reclaim, I/O latency, and SSTable counts before and after under the same workload, while ruling out compaction, hot-set shifts, and hardware faults. You may need to roll back or re-size rather than looking only at GC.

### Exercise C — Distinguishing Errors

Given three signals:

1. **java.lang.OutOfMemoryError: Java heap space**;
2. **java.lang.OutOfMemoryError: Direct buffer memory**;
3. Kernel/cgroup reports **oom_kill**, and Cassandra disappears without a Java stack trace.

Match each signal with its priority measurements.

**Hint:** (1) heap/live set and GC; (2) direct/native allocations, relevant limits, and concurrency; (3) memory.current/max/events, kernel logs, RSS, and memory accounting. Do not lump all cases into "increase -Xmx".

### Check Questions

1. **Why can RSS include pages that are also counted in the Linux page cache?**  
   Because the process can map and keep resident file-backed pages that the kernel is caching; these counters can overlap.
2. **Why shouldn't Cassandra be tuned by giving nearly all RAM to the heap?**  
   Native/off-heap memory, the OS, the page cache, and background load spikes still need RAM.
3. **Can you conclude a native memory leak from seeing high RSS once?**  
   Not yet; break down memory and observe trends over time, separating file-backed pages, allocators, workload, and GC.
4. **Does page size in the Java driver fundamentally solve queries spanning too many partitions?**  
   No; you must redesign the access pattern and partition key.
5. **How do compaction or repair relate to RAM budgeting?**  
   They alter I/O, network, buffer load, and sometimes peak memory consumption, so they must be accounted for in verification and capacity planning.

## 13. Conclusion

For Apache Cassandra, the **Java heap**, **native/off-heap**, and **OS/page cache memory** share a finite RAM budget. Adequate heap lowers allocation and GC pressure; appropriate off-heap reduces objects GC must traverse; and the page cache cuts physical SSTable reads from storage. No region can be tuned in isolation while ignoring the other two.

To find a sound configuration, establish real RAM limits, measure live set/GC, RSS/native memory, MemAvailable/cache, and disk I/O under the same workload, then adjust step by step. **Partition keys, query-driven table design, replication, consistency levels, compaction, repair, and Java application behavior** all shape memory demand; addressing the true cause at each layer is what keeps Cassandra's latency stable and prevents OOM incidents.
