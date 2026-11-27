# Prolonged Heap/GC Pauses, Off-Heap Memory, and OS Resources in Apache Cassandra

## 1. Objectives and Diagnostic Scope

Apache Cassandra is a distributed **wide-column** database where every CQL request traverses coordinators, replicas, memtables, SSTables, the commit log, and multiple caching layers. When a Java application reports rising p99 latency, a node gets killed, or an `OutOfMemoryError` appears, the root cause may not be "insufficient Java heap"—it may lie in **off-heap/native memory**, the Linux page cache, cgroup limits, executor queues, disk I/O, or queries scanning oversized partitions.

This lesson belongs to the **Troubleshooting** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, guiding end-to-end investigation from the JVM down to the OS, tied to partition key design, read/write consistency levels, compaction, repair, Java Driver behavior, and live workloads.

After this lesson, you can:

1. Distinguish **Java heap**, **off-heap/native/direct memory**, **RSS**, **virtual memory**, **Linux page cache**, **filesystem cache**, **container memory limits**, and **host RAM**.
2. Read GC pauses, allocation rate, heap occupancy, and young/full GC cycles, distinguishing **GC as root cause** from **GC as downstream symptom** of heavy workloads.
3. Diagnose `java.lang.OutOfMemoryError: Java heap space`, `Direct buffer memory`, native allocation failures, and kernel/cgroup OOM-kills.
4. Understand how memtables, caches, the read path, SSTables, tombstones, compression, and compaction affect heap, off-heap memory, and I/O.
5. Gather safe evidence using `nodetool`, JMX, GC logs, `jcmd`, `jstat`, and Linux/cgroup inspection commands.
6. Correlate CPU throttling, swap, disk await, file descriptors, threads, and page cache with p95/p99 latency, timeouts, and dropped messages.
7. Build **triage, mitigation, rollback, and recovery verification runbooks** across memory failure modes.
8. Design load/fault tests, dashboards, and guardrails to prevent recurrence.

**Version note:** JVM flags, collectors, JMX metrics, off-heap buffers, and Cassandra parameters differ substantially across Cassandra 3.x, 4.x, 5.x, vendor distributions, and JDK versions. Examples here are a **diagnostic framework to verify against your exact release**, not blanket tuning settings.

**Operational scope:** illustrative commands must only run **when operationally authorized**, preferring read-only inspection. Actions like capturing heap dumps, class histograms, switching collectors, restarting nodes, triggering compaction/repair, or tuning kernel/cgroup parameters **require formal change procedures**. This lesson executes no live commands.

## 2. Distinguishing Memory Layers

### 2.1. A Node Consumes More Than Java Heap

~~~mermaid
flowchart TB
    A["Host / VM RAM"] --> B["Container / cgroup memory accounting"]
    B --> C["Cassandra JVM process"]
    B --> D["Page cache / kernel-accounted memory"]
    C --> E["Java heap: objects, allocations"]
    C --> F["Native/off-heap: direct buffers, malloc, mmap residency"]
    C --> G["Metaspace, code cache, thread stacks, GC/JVM native"]
    C --> H["Memory-mapped files / shared libraries"]
    D --> I["SSTables, commit log, filesystem cache"]
~~~

This diagram is a **logical model**: on Linux, `mmap` pages can appear in both process address mappings and page cache accounting; **never blindly sum every box** into physical RAM usage.

### 2.2. Key Terminology

| Term | What is it? | Units / common misconception |
|---|---|---|
| JVM heap | Managed region for Java objects, collected by GC | `-Xmx` caps max heap, not total process RSS |
| Heap used/committed/max | Live/allocated/maximum heap bounds | Lower used heap after GC does not mean RSS drops equally |
| Off-heap / native | Memory outside Java heap used by JVM, libraries, direct buffers, `malloc`, etc. | Not directly reclaimed by standard Java heap GC |
| Direct buffer | `ByteBuffer.allocateDirect` / network I/O buffers | Can hit `Direct buffer memory` even with free heap |
| Metaspace / code cache | Class metadata and JIT-compiled native code | Resides outside Java heap |
| Thread stacks | Per-thread native/Java stack space | Excessive thread counts can exhaust native memory |
| `mmap` | Memory-mapped files or anonymous regions | Huge virtual mapping size does not mean all RAM is allocated |
| RSS | Resident Set Size: RAM-resident pages of a process | Can include shared/file-backed pages; not total host RAM |
| PSS | Proportional Set Size: splits shared pages proportionally | Helpful when comparing processes with shared mappings |
| VSZ/VIRT | Total mapped virtual address space | Usually **does not** reflect actual physical RAM consumed |
| Linux page cache | OS cache of filesystem pages | Useful performance cache, reclaimable under rules |
| Cgroup memory | Memory charged by kernel to a container/cgroup | Can include page cache/kernel memory alongside JVM RSS |
| Swap | Paging memory out to swap space | Causes severe latency spikes; track active I/O, not only size |
| OOM-kill | Kernel/cgroup terminates process under out-of-memory policy | Distinct from Java's `OutOfMemoryError` |

### 2.3. Preliminary Capacity Math

Suppose a container has a **16 GiB** memory limit and JVM `-Xmx = 12 GiB`. That **does not** guarantee 4 GiB remains free for everything else, because:

- Heap may not commit all 12 GiB continuously, or conversely may commit fully under load.
- The JVM also allocates metaspace, JIT code cache, GC metadata, and thread stacks.
- Direct/native buffers and native allocations expand under concurrency.
- Page cache and kernel memory are charged to the cgroup depending on kernel/cgroup accounting rules.
- Memory-mapped file pages consume resident memory in ways not equal to raw file size.
- Cgroup memory pressure and OOM behavior depend on the container's hard and soft boundaries.

The target is a **budget with genuine headroom**, not assuming "`-Xmx` = 90% of RAM is optimal". Always measure **real peak usage**, steady-state load, cache percentages, and surges during compaction, repair, and restarts.

### 2.4. Never Blindly Sum RSS and Page Cache

`/proc/PID/status VmRSS` can include file-backed resident pages; `memory.stat file` reflects filesystem cache pages accounted to the cgroup. Summing `RSS + page cache` often **double-counts**. During analysis:

1. Pick one **accounting boundary** (host, cgroup, or process).
2. Explicitly document where each metric is accounted.
3. For shared mappings, check PSS/`smaps_rollup` where authorized.
4. Inspect container `memory.current`, `memory.stat`, and `memory.events`—not just JMX heap gauges.
5. Compare across **time-series**, never just a snapshot moments before failure.

## 3. Initial Symptoms and Candidate Causes

| Symptom | Priority hypothesis | Distinguishing evidence |
|---|---|---|
| Heap used climbs steadily; Full GC fails to clear | Retained objects, cache/buffers, leak, oversized live dataset | Post-GC old/live occupancy, controlled histogram/dump |
| Frequent Young GC, post-GC heap remains low | Allocation churn, paging/large rows | Allocation rate, total pause time, object profile |
| Prolonged stop-the-world pauses | GC pressure, humongous allocations, CPU throttling, or collector mismatch | GC log + CPU throttling + JVM safepoint stats |
| JVM `Java heap space` | Heap allocation failed | JVM logs/errors, post-GC heap, class histogram |
| JVM `Direct buffer memory` | Direct memory exhaustion/cap | Direct/mapped buffer pools, NMT if enabled |
| Process exit 137 / `OOMKilled` | Kernel/cgroup likely killed process | `memory.events` / container runtime status / kernel logs |
| Cgroup `memory.current` high while heap is low | Page cache, native buffers, `mmap`, kernel accounting | `memory.stat` breakdown, RSS/PSS |
| Host available memory low, swap-in/out climbing | Memory pressure / thrashing | `vmstat si/so`, PSI, request latency |
| High CPU quota throttling + longer GC pauses | GC/JVM starved of CPU slices | `cpu.stat`, per-core usage, GC pause timeline |
| `too many open files` | FD limit, sockets, or SSTable handles | `/proc/PID/fd`, `ulimit`, authorized `lsof` |
| `unable to create native thread` | Native memory or thread/PID limits | Thread counts, cgroup `pids.current`/`pids.max` |
| Read p99 climbs with SSTables/tombstones | Read amplification or wide partitions | `tablestats`, `tablehistograms`, bounded tracing |
| Write p99 climbs with flush/compaction | Disk/commitlog/background I/O stalls | `compactionstats`, disk await/IOPS, commitlog metrics |

**Never blame a single cause from one metric.** Long Full GCs can come from a huge live heap, or simply from container CPU throttling stretching pause durations.

## 4. First 10-Minute Triage Workflow

### 4.1. Preserve Evidence Before Restarting

1. Record the **UTC timeline**: when p99 rose, app deploys, schema/data changes, compaction, repair, traffic bursts, or node restarts.
2. Determine **blast radius**: one node, one rack/DC, specific coordinators, Java app tier, or cluster-wide?
3. Categorize failures: timeouts, `OverloadedException` (if release supports it), OOMs, connection refused, dropped messages, `UnavailableException`.
4. Check **GC pause durations + post-GC heap used**, not merely GC counts.
5. Check **process RSS/PSS** and **cgroup `memory.current`/`max`/`events`**, separating `OOMKilled` from Java OOM.
6. Inspect **CPU throttling**, swap, disk await, pending queues, and compaction backlogs.
7. Check driver concurrency, query shapes, rows/page, bytes/row, and hot partitions.
8. Record effective config: Cassandra/JDK versions, GC flags, `-Xms`/`-Xmx`, container limits/requests, memory tunables.
9. Apply **controlled load shedding** if guardrails are breached; never rewrite JVM flags cluster-wide while quorum is fragile.
10. Re-check after shedding load: did p99, errors, queues, GC, and RSS recover? Record what did **not** recover too.

### 4.2. Initial Decision Map

~~~mermaid
flowchart TD
    A["Node p99 spike / restart / OOM"] --> B{"Killed by kernel/cgroup?"}
    B -->|Yes| C["Check memory.events, pod OOMKilled, RSS/native/file cache"]
    B -->|No| D{"JVM logged OutOfMemoryError?"}
    D -->|Yes| E["Classify heap space vs direct vs native threads/metaspace"]
    D -->|No| F{"GC pauses & post-GC heap rising?"}
    F -->|Yes| G["Allocation/live set/heap config + CPU throttling"]
    F -->|No| H["Disk/network/FD/threads/replica queues/compaction"]
    C --> I["Guardrails + targeted remediation"]
    E --> I
    G --> I
    H --> I
    I --> J["Verify recovery, quorum, correctness, SLO"]
~~~

### 4.3. Triaging Is Not "Run Everything at Once"

Collect the **lowest-impact evidence** first:

- Existing metrics/GC logs → read-only and non-intrusive.
- `nodetool info/tpstats/compactionstats` or JMX metrics → cluster-level telemetry.
- `/proc`, `vmstat`, `pidstat`, cgroup files → OS/container telemetry.
- `jcmd Thread.print`, class histogram, heap dump → can pause or consume CPU/disk; **run only with approval**.

Never run `jcmd GC.heap_dump` on a node nearly out of disk space just to "peek at heap"; the resulting dump file can exhaust disk and worsen the outage.

## 5. GC Pauses and Heap Occupancy: What to Look For

### 5.1. Three Distinct GC Patterns

**A. Allocation churn:** heap climbs rapidly between young GCs and drops sharply afterward; total GC time/second spikes, causing latency jitter despite low post-GC residency.

**B. Growing live set:** after full or mixed GCs, post-GC heap remains high and trends upward; caused by retained caches/buffers, thread-locals, page retention, or leaks.

**C. CPU-starved GC:** live heap isn't oversized, yet wall-clock pauses stretch because containers hit CPU quota throttling or host steal time; check CPU throttling alongside pause logs.

### 5.2. Illustrative Time-Series Table

| UTC | Pre-GC heap used | Post-GC heap used | GC pause | CPU throttled % | Read p99 |
|---|---:|---:|---:|---:|---:|
| 10:00 | 8.0 GiB | 4.1 GiB | 60 ms | 0% | 75 ms |
| 10:05 | 9.0 GiB | 5.0 GiB | 95 ms | 3% | 120 ms |
| 10:10 | 10.5 GiB | 7.9 GiB | 420 ms | 28% | 650 ms |
| 10:15 | 11.5 GiB | 10.2 GiB | 2,100 ms | 35% | 3,000 ms |

**Hypothetical data**, illustrating live heap and CPU throttling rising together. Never assume causality from correlation alone; examine GC logs, workload metrics, and cgroup samples around those timestamps.

### 5.3. Pause Percentiles Are Not Request p99

- A 300 ms JVM STW pause impacts active requests, yet you **cannot simply add 300 ms to request p99**.
- Driver p99 spans client→coordinator; Cassandra GC pauses are just one driver of downstream queuing and retries.
- Averaging GC pause histograms with API p99 histograms is mathematically invalid.
- An application reading with RF=3/`LOCAL_QUORUM` experiences different delays depending on whether a coordinator or one replica paused.

### 5.4. GC Pause Time Fraction

Suppose a node records 4.8 seconds of stop-the-world pauses in a 60-second window:

~~~text
GC pause fraction = 4.8 / 60 = 8%.
~~~

This reflects **wall-clock time frozen during STW phases** as instrumented, not total CPU consumed by GC. Concurrent collectors perform background marking on CPU outside STW pauses; track concurrent GC CPU overhead separately from pause duration.

### 5.5. Post-GC Occupancy Beats Instantaneous Snapshots

Seeing 90% heap used right before a young GC can be completely normal when short-lived objects dominate. Conversely, 80–90% used **right after full/mixed reclamation cycles** signals a large live set and thin headroom.

Different collectors manage generations, concurrent cycles, and mixed collections differently. Never apply a blanket rule like "80% after one young GC = leak" across all JDKs.

## 6. JVM Collectors and GC Logging by Release

### 6.1. Verify the Active Collector Instead of Guessing

Production Cassandra/JDK deployments use different collectors such as CMS (legacy), G1, or other release-supported collectors. **Newer JDKs removed older collectors**; each Cassandra version ships specific JVM option templates.

Never copy legacy flags like `-XX:+UseConcMarkSweepGC` from old blog posts onto modern JDKs. Before altering GC settings, verify:

- Cassandra version and **officially supported JDK versions**.
- Active collector via `VM.flags` or startup logs.
- Heap size, host/container CPU/RAM, and rolling restart rules.
- Existing GC logs, baseline workloads, and SLOs.
- Flag compatibility with your specific JDK vendor.

### 6.2. Unified Logging Example on Modern JDKs

~~~text
# Illustrative flag syntax for supporting JVM/JDK versions only.
-Xlog:gc*,safepoint:file=/var/log/cassandra/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

On **older JDKs**, logging uses legacy flags such as `-XX:+PrintGCDetails`. **Never mix incompatible flag styles into production without testing**, and never direct `gc.log` onto tiny volumes without rotation limits.

A typical GC log entry captures:

- Collector phase and cause.
- Pause duration (usually ms).
- Pre-GC and post-GC heap usage plus committed capacity.
- Wall, user, and sys CPU timings where supported.
- Safepoint overhead, concurrent cycle timings, and allocation pressure.

### 6.3. Aligning GC Logs with Request Timelines

~~~text
12:00:01.000  API p99 begins rising
12:00:01.200  Cassandra node B hits 1.4 s GC pause
12:00:01.250  Driver timeouts and retry attempts climb
12:00:02.700  Node B exits pause; pending queue remains elevated
12:00:05.000  API p99 returns to baseline once queue drains
~~~

This timeline is illustrative. Always verify clock sync/UTC alignment, request IDs, and per-node telemetry; clock skew between hosts can make effects look like causes.

## 7. Causes of High Heap Allocation in Cassandra

### 7.1. Partition-Key Queries Can Still Be Expensive

A valid CQL query:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

is generally inexpensive when partitions are bounded and tombstone counts are low. However, another pattern:

~~~cql
-- Cautionary example: reading an entire very wide partition.
SELECT *
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

can pull millions of rows. Even on a single logical partition, paging buffers, row decoding, large collections, and request state create significant allocations on both server and client.

### 7.2. Common Heap/Read-Path Pressure Sources

- Overly wide partitions: massive clustering row counts or huge cell payloads.
- Excessive tombstones or expired TTL data forcing read scans over dead cells.
- Many uncompacted SSTables inflating merge/read amplification.
- Missing `LIMIT` clauses or clients consuming all pages indiscriminately.
- `ALLOW FILTERING` scanning multiple partitions.
- Low-selectivity secondary index queries hitting many replicas.
- Oversized batches or unconstrained concurrency.
- Hot LWT keys accumulating Paxos queues and latency.
- Bulk backfills, repairs, and streaming competing for CPU/I/O.

**Never keep raising `-Xmx` just to mask an access pattern unsuited to Cassandra.** Long-term fixes belong in data modeling, bucketing, page sizes, TTL/tombstone hygiene, and admission control.

### 7.3. Java Clients Can OOM Independently

Inside a Java Driver application:

~~~java
// ANTI-PATTERN: pulling every page into one giant List.
List<Row> allRows = new ArrayList<>();
for (Row row : session.execute(statement)) {
    allRows.add(row);
}
~~~

Even though the driver pages internally, the `List` retains every row and exhausts application heap. **A client OOM does not mean Cassandra nodes hit heap OOM**. Always inspect memory metrics on the **process throwing the error**.

When APIs stream data asynchronously or reactively, consume page-by-page with bounded concurrency, backpressure, and response byte caps. Never assume reactive `Flux` stays memory-bounded if code calls `collectList()`.

## 8. Cassandra Memtables, Caches, and Off-Heap Memory

### 8.1. Memtables Are Not "Always All Inside Java Heap"

Cassandra writes mutations into memtables according to storage engine configuration before flushing to SSTables. **Memtables may allocate on-heap, off-heap, or hybrid structures depending on version and config**, so you cannot treat `nodetool tablestats` memtable sizes as pure Java heap usage.

When memtable pressure mounts:

- Flushes occur more frequently.
- Disk writes, commit log, and compaction pressure rise.
- Background threads compete for CPU and I/O.
- Reads must merge more SSTables.
- Write/read p99 can spike even when post-GC heap stays modest.

### 8.2. Common Memory & Cache Components

| Component | Role | Diagnostic caveat |
|---|---|---|
| Memtable | Buffers writes prior to flush | On/off-heap pressure; flush backlog |
| Key cache | Locates SSTable index offsets | Consumes memory and alters read I/O |
| Row cache | Caches row data when configured | Increases footprint and invalidation cost |
| Chunk/file cache | Buffers SSTable chunks per release | Drives direct/native memory footprint |
| Bloom filters | Skips SSTables missing partition keys | Off-heap/native footprint; false positives |
| Index/compression metadata | Supports lookups and decompression | Off-heap/mapped depending on release |
| OS page cache | Caches SSTable/commitlog file pages | Reclaimable, though churn causes I/O spikes |
| Driver connection buffers | Native transport networking | Direct/native buffers scaled by concurrency |

**Never add every cache size onto `-Xmx` and call that total RSS.** Different structures live on heap, off-heap, mmap, or OS page cache; verify against your specific release and metrics.

### 8.3. Do Not Disable Caches Blindly

If key cache or chunk cache shows a large footprint, disabling it immediately can surge disk reads and worsen p99 latency. Any cache adjustment requires:

1. Measuring hit/miss ratios, footprint, disk await, and p99 baseline first.
2. Confirming on-heap vs off-heap placement for your Cassandra version.
3. Testing in a lab with realistic datasets and warm-up.
4. Sizing limits within the **total node memory budget**.
5. Rolling out node-by-node while watching retries, CL, and headroom.
6. Keeping a rollback plan if disk I/O or latency climbs.

## 9. Compaction, Tombstones, and Memory

### 9.1. Compaction Is Heavy I/O Rewriting, Not Simply a Heap Problem

Compaction reads multiple SSTables, merges live/deleted cells, and writes new SSTables using CPU, RAM buffers, and disk bandwidth. When compaction falls behind:

- High SSTable counts inflate read amplification.
- Elevated disk await slows replica responses.
- Aggressive file I/O churns the Linux page cache.
- Native and heap allocations shift under queued requests.
- Commit log and memtable flushes stall if disks saturate.

Thus **GC pauses rising alongside compaction backlog** do not automatically mean compaction "leaked Java heap". Compaction may be starving CPU/I/O, stretching GC wall-clock time or growing request queues.

### 9.2. TTL and Tombstones

Expired TTL cells stop appearing as live rows in results, yet their markers persist until compaction and safety windows expire. When a query scans massive tombstone sets to return just a few rows:

~~~text
SELECT returns 20 live rows
Yet the read path examined:
  50,000 expired/deleted cells
  across multiple SSTables

User sees: 20 rows
Actual server cost: far higher than 20 rows
~~~

These figures are illustrative. Tombstone-heavy reads inflate CPU, disk I/O, allocations, and tail latency. Align TTLs, retention windows, partition bucketing, and compaction strategies with your actual data lifecycle.

### 9.3. Never Force Major Compaction on Memory/Disk-Starved Nodes

`nodetool compact` and similar operations temporarily consume massive disk space, CPU, and I/O. On a node suffering `OOMKilled` restarts or low free disk, forcing compaction can escalate the outage.

Prioritize workload measurement, load shedding, capacity checks, and authorized SOPs. Repair and streaming likewise demand heavy I/O and network bandwidth—track them on the same timeline.

## 10. `nodetool` and JMX: Separating Heap Pressure from Storage Load

### 10.1. Baseline Observation Commands

~~~bash
# Command names/syntax depend on Cassandra release.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats telemetry_lab.readings_by_device_day
nodetool tablehistograms telemetry_lab readings_by_device_day
nodetool gcstats
nodetool netstats
~~~

These are **illustrative commands**, not executed automatically. Check `nodetool help` and access permissions before running; syntax and reported metrics differ slightly across versions.

| Tool | Useful signals | Interpretation limits |
|---|---|---|
| `status` | Node UP/DOWN, DC/rack, ownership | `UN` does not prove healthy p99 or GC |
| `info` | Heap usage, uptime, caches, load per release | Heap is not process RSS or cgroup memory |
| `tpstats` | Stage pending/active/completed/dropped | Stage tasks ≠ logical HTTP requests |
| `compactionstats` | Active/pending compactions and progress | Growing backlog does not prove heap leak |
| `tablestats` | SSTables, memtable, read/write metrics | Memtable size isn't strictly on-heap |
| `tablehistograms` | Table latency/cell/partition distributions | Not a substitute for client end-to-end latency |
| `gcstats` | Aggregate GC stats per release | Not a replacement for time-stamped GC logs |
| `netstats` | SSTable streaming activity | Empty does not mean CQL traffic is idle |

### 10.2. Essential JMX Metric Categories

| Category | Metrics | Why needed |
|---|---|---|
| JVM heap pools | Used, committed, max | Live vs available Java heap |
| JVM GC | Collection count/time, pause histograms if exposed | STW pauses and GC overhead |
| `BufferPoolMXBean` | Direct/mapped buffer counts and memory | Partial off-heap visibility (excludes non-Java native malloc) |
| JVM threads | Count, peak, blocked | Thread count and stack footprint |
| Cassandra stages | Active, pending, dropped | Executor queuing on slow nodes |
| Memtables | Occupancy, flushes, pending per release | On/off-heap allocation and flush lag |
| SSTables | Live count, SSTables/read, tombstones | Query amplification and storage health |
| Compaction | Pending tasks, bytes, progress | Competing background CPU/disk load |
| Commit log | Sync latency, segments, waits | Write-path disk/sync pressure |
| Native transport | In-flight requests, connections | Buffer allocations and request load |

Exact JMX MBean names, GC pool names, and exporter labels **vary across Cassandra and JDK releases**. Verify the active collector and exporter mappings rather than assuming fixed names.

### 10.3. Multi-Cause Observation Example

~~~text
Time      ReadStage Pending    GC pause    Disk await
10:00                    20       40 ms        4 ms
10:05                   350      150 ms       10 ms
10:10                 2,100      950 ms       70 ms
~~~

One possibility: slow disks stalled reads → queues backed up → live request objects filled heap → GC slowed down. Another: GC paused first → queues backed up → I/O bursts followed. **Granular timestamps and corroborating metrics** are essential to determine direction of causality.

## 11. Read-Only Linux Commands: Host and Process

### 11.1. Host Memory, CPU, and Disk

~~~bash
free -h
vmstat 1 5
top -b -n 1
ps -eo pid,ppid,rss,vsz,%cpu,%mem,comm
df -h
df -i
~~~

`free -h` typically reflects host RAM, **not a pod's cgroup memory limit**. Inspect multi-second `vmstat` intervals rather than only line 1 (which shows averages since boot). `df -i` catches inode exhaustion even when free byte capacity remains.

### 11.2. Interpreting `vmstat` Fields

| Field | General meaning | What NOT to conclude |
|---|---|---|
| `r` | Runnable threads waiting for CPU | That all runnable threads are GC workers |
| `b` | Uninterruptible blocked tasks | That blocking is strictly heap-related |
| `si`/`so` | Swap-in / swap-out rates | That any `SwapUsed > 0` caused the outage |
| `bi`/`bo` | Block I/O activity | 1:1 count of CQL requests |
| `us`/`sy` | User/kernel CPU time | Absence of container cgroup CPU throttling |
| `wa` | CPU time waiting on I/O | Direct % disk saturation |
| `st` | Hypervisor steal time | Negligible if overall host CPU looks low |

If active `si`/`so` climbs concurrently with p99 and GC pauses, inspect swap policy and memory headroom. Never disable swap or change sysctl flags in production without change control.

### 11.3. Process Resident Memory

~~~bash
# PID 12345 is a placeholder; verify the actual Cassandra PID.
ps -p 12345 -o pid,etime,rss,vsz,%cpu,%mem,comm
cat /proc/12345/status
cat /proc/12345/smaps_rollup

# If sysstat is installed:
pidstat -r -u -d -p 12345 1 5
~~~

- `VmRSS`: process resident set, potentially including shared/file-backed pages.
- `VmSize`/`VSZ`: mapped virtual address space, **not allocated physical RAM**.
- `Pss` from `smaps_rollup`: useful when shared mappings are large.
- `Threads`: helps detect native thread growth.
- `VmSwap`: swap pages attributed to this process, not host total.

Polling `smaps_rollup` or `lsof` rapidly on a JVM with thousands of mappings adds overhead. Sample judiciously and redact sensitive paths/hostnames in tickets.

## 12. Cgroups: Why Can a Pod Hit `OOMKilled` Before Heap Fills?

### 12.1. Read-Only Cgroup v2 Files

~~~bash
# Example paths when inside the target cgroup v2 namespace.
# On Kubernetes hosts, paths sit under the pod/container cgroup hierarchy.
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events

cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max

cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

`memory.max` prints `max` when uncapped in cgroup v2. `memory.events` exposes counters like `high`, `max`, `oom`, and `oom_kill` depending on kernel version. Measure **deltas over time** inside the **specific Cassandra cgroup**, never assuming root cgroup stats apply.

Cgroup v1 uses different filenames such as `memory.usage_in_bytes` and `memory.limit_in_bytes`; verify against your host OS.

### 12.2. JVM OOM vs. Kernel OOM-Kill

~~~text
JVM-level:
  java.lang.OutOfMemoryError: Java heap space
  java.lang.OutOfMemoryError: Direct buffer memory
  java.lang.OutOfMemoryError: unable to create native thread

Kernel/container-level:
  Process receives SIGKILL (often exit code 137)
  Pod status reason: OOMKilled (if reported by runtime)
  cgroup memory.events oom_kill increments
~~~

**Exit code 137 alone does not prove a kernel OOM**: `SIGKILL` can come from liveness probes or manual kills. Corroborate with runtime termination reason, cgroup counters, or authorized kernel logs.

### 12.3. An Interpretive Calculation

~~~text
Container memory.max      16 GiB
Container memory.current  15.8 GiB
JVM -Xmx                  10 GiB
JVM heap used              7.5 GiB
Process RSS               12 GiB
memory.stat file           4 GiB
memory.events oom_kill     +1

=> A container can be OOMKilled even with free headroom under -Xmx.
=> Never blindly add RSS + file cache due to potential double-counting.
=> Account for native, file cache, and kernel memory inside memory.current.
~~~

Numbers are illustrative. Cgroup accounting tracks far more than Java heap; while page cache is reclaimable, reclamation isn't free or always fast enough under bursts. Never size `-Xmx` near 100% of `memory.max`.

## 13. CPU Throttling Can Stretch Wall-Clock GC Time

### 13.1. Cgroup CPU Counters

~~~text
usage_usec         110000000
nr_periods             10000
nr_throttled            1200
throttled_usec       4500000
~~~

These are illustrative cumulative cgroup v2 counters. `nr_throttled / nr_periods` tracks the fraction of CFS periods throttled—it does **not equal % GC time**. Aggregation semantics of `throttled_usec` across cores/threads depend on kernel/cgroup versions.

### 13.2. Why Does This Matter?

- The underlying host may have plenty of idle CPU while the container hits low `cpu.max` quotas.
- GC threads and Cassandra stage executors get descheduled mid-work.
- Stop-the-world **wall-clock duration** balloons far beyond what an unthrottled JVM would need for the same heap.
- Driver retry/reconnection storms consume additional CPU quota.
- Hot partitions overload individual nodes well before cluster averages look high.

Diagnosis: overlay `cpu.stat` deltas, GC pause logs, per-core CPU, QPS, and `tpstats` Pending on one UTC timeline. **Adding Java heap will not cure CPU throttling.** Adjusting CPU quotas/requests requires capacity validation and canary rollout.

## 14. Swap, PSI, and Memory Pressure

### 14.1. Swap Activity

- `SwapUsed > 0` alone is not proof of an outage.
- Active `vmstat si/so` paging correlated with disk latency and p99 is a real warning sign.
- Never alter `vm.swappiness` or swap configuration in production without formal SOPs.
- Container runtimes and kernels differ in swap enforcement; verify your live cluster config.

### 14.2. Pressure Stall Information (PSI)

~~~bash
# Only available on kernels with PSI enabled.
cat /proc/pressure/memory
cat /proc/pressure/cpu
cat /proc/pressure/io
~~~

PSI provides `avg10/avg60/avg300` and `total` stall percentages/microseconds waiting on memory, CPU, or I/O. Some cgroup v2 hierarchies also expose per-cgroup `memory.pressure`/`cpu.pressure`/`io.pressure`. Host scope and cgroup scope differ—**never compare them as if measuring the same population**.

## 15. `jcmd`, `jstat`, and JVM Diagnostic Tools

### 15.1. Tools Ranked by Operational Impact

~~~bash
# PID 12345 is an example; verify exact PID and matching JDK.
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jstat -gcutil 12345 1000 5

# Potentially disruptive; run only when authorized:
jcmd 12345 Thread.print
~~~

| Tool | Diagnostic value | Operational risk |
|---|---|---|
| Existing GC logs / JMX metrics | Pauses, heap pools, GC overhead | Minimal / non-intrusive |
| `jcmd VM.flags` | Effective JVM flags & collector | Requires attach permissions |
| `jcmd GC.heap_info` | Heap used vs committed | Minor attach overhead |
| `jstat -gcutil` | Live GC utilization counters | JDK-dependent formatting |
| `jcmd Thread.print` | Thread states and locks | CPU/safepoint pause; sensitive stack metadata |
| `jcmd GC.class_histogram` | Object counts and bytes by class | Can trigger GC / STW safepoint |
| `jcmd GC.heap_dump` | Full object retention graph | Huge disk write, long STW pause, contains secrets |
| `jcmd VM.native_memory` | NMT memory breakdown | Requires startup flag; incomplete native coverage |

### 15.2. Never Take a Heap Dump as Your First Triage Step

~~~text
Never run ad-hoc on a disk-constrained node:
    jcmd 12345 GC.heap_dump /secure/path/heap.hprof

Proceed only when:
    change approval and secure storage exist;
    disk headroom handles the full dump, and STW/CL impact is accepted;
    the artifact is access-controlled (may contain secrets/user data);
    a recovery/rollback plan is ready.
~~~

A class histogram heavy in `byte[]` alone does not prove a leak. Evaluate **post-GC live heap trends** across multiple workload windows, trace object retention paths, and rule out intentional caches or in-flight buffers.

## 16. Native Memory Tracking (NMT) and Direct Buffers

### 16.1. Scope Limits of NMT

If `-XX:NativeMemoryTracking=summary` or `detail` was enabled at JVM startup on supported HotSpot/JDK builds:

~~~bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
~~~

NMT tracks categories internal to HotSpot: reserved/committed heap, class metadata, GC structures, thread stacks, and code cache. **NMT misses third-party JNI/libc/native allocations and Linux page cache**, and adds startup overhead. Never treat NMT totals as equivalent to RSS or cgroup memory.

### 16.2. Reserved vs. Committed vs. Resident

~~~text
JVM reserved virtual space  30 GiB
NMT committed              12 GiB
Process RSS                13 GiB
Cgroup memory.current      15 GiB

Illustrative figures; DO NOT sum them into 70 GiB.
~~~

Reserved virtual memory is not resident RAM; committed doesn't match RSS identically; cgroup accounting includes kernel and file-backed pages.

### 16.3. Direct Buffer OOM

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
java.lang.OutOfMemoryError:
  Cannot reserve ... bytes of direct buffer memory
~~~

Inspect `BufferPoolMXBean` (direct/mapped), native allocations, RSS/PSS, cgroup `memory.events`, driver/server network in-flight counts, and payload sizes. Triggers include excessive buffer counts, large pages/rows, native leaks, misconfigured caps, or retry storms.

**Never increase `-XX:MaxDirectMemorySize` blindly**: without expanding container memory limits and headroom, you risk trading a Java direct-memory OOM for a fatal kernel `OOMKilled`.

## 17. Threads, File Descriptors, and OS Limits

### 17.1. Native Thread Exhaustion

~~~text
java.lang.OutOfMemoryError:
  unable to create native thread
~~~

Possible drivers: thread leaks, thread stack reservations, `pids.max`, systemd `TasksMax`, `ulimit -u`, or OS memory/commit limits. Inspect `Threads` in `/proc/PID/status`, JVM thread metrics, `pids.current/max`, process limits, and controlled thread dumps.

**Increasing Java heap does not fix native thread limits—and can even starve native stack/thread address space on constrained hosts.**

### 17.2. File Descriptor Exhaustion

~~~bash
# When authorized with verified PID:
cat /proc/12345/limits
ls /proc/12345/fd
~~~

`Too many open files` points to sockets, open SSTables, log handles, or connection churn. Correlate FD count trends against configured limits, SSTable counts, native transport connections, and leaks. Never set `nofile` arbitrarily infinite or run continuous host-wide `lsof` loops on stressed nodes.

### 17.3. I/O Pressure Can Indirectly Grow Heap

Slow disks → slow memtable flushes, commit logs, and compaction → queued requests hold in-flight objects longer → live heap occupancy and GC rise → driver timeouts and retries amplify inbound load further. Therefore, **disk await, free space, IOPS, and pending compactions** must sit alongside heap/GC on every timeline.

## 18. Java Driver Paging, Concurrency, and Client/Server OOMs

### 18.1. One CQL Query Can Stress Two JVMs

~~~text
REST /readings
  -> Java app / driver
    -> SELECT by partition key
      -> Cassandra coordinator/replica
         -> memtables, SSTables, tombstones
    <- multiple pages
  -> client collects rows into List/JSON
~~~

Server-side cost: CPU, disk I/O, heap/off-heap buffers, and tombstone scanning. Client-side cost: retained row references, JSON serialization, `List` allocations, pending futures, and direct network buffers.

| Mechanism | What it bounds | What it does NOT bound |
|---|---|---|
| CQL `LIMIT 20` | Returned live rows | Tombstones/storage cells scanned |
| Driver page size 100 | Target rows per network page | Total rows returned by query |
| In-flight cap 64 | Outstanding requests within one scope | Aggregate traffic across all client pods |
| Reactive `request(n)` | Downstream demand | Data model cost or server I/O |
| `flatMap(...,8)` | Concurrency in one reactive operator | Fleet-wide HTTP service concurrency |

### 18.2. Java Client Anti-Pattern

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.ArrayList;
import java.util.List;

// Anti-pattern: accumulating every row from a large query in memory.
List<Row> rows = new ArrayList<>();
for (Row row : session.execute(statement)) {
    rows.add(row);
}
~~~

Even though the driver fetches incrementally across pages, `List` retains every row. **Application heap OOM does not prove Cassandra node OOM**.

Bounded query example:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 20;
~~~

You must still check tombstone density, since `LIMIT 20` can force the read path to scan thousands of tombstones before finding 20 live rows.

### 18.3. Retry Amplification

~~~text
1,000 logical reads/s
20% retry one additional attempt
=> ~1,200 driver attempts/s

Gateway retries or speculative execution can push this even higher.
~~~

Never allow unbounded retries when GC or executor queues are saturated. Timeouts on writes, LWTs, counters, or TTL mutations never prove the mutation was not applied.

## 19. Layered Observability and Timelines

### 19.1. Measure the Right Process

| Evidence | Scope | Investigation target |
|---|---|---|
| Java app `OutOfMemoryError` | Client/driver JVM | Result lists, JSON buffers, futures |
| Cassandra GC log | Cassandra node JVM | Live heap, GC pause durations |
| Driver request p99 | Client→coordinator | Pools, network RTT, retries |
| `tpstats` Pending | Server executors | Thread pool queues and stalls |
| `memory.events oom_kill` | Specific cgroup | Hard container memory boundary |
| `smaps_rollup` | Process PID | RSS/PSS and file-backed mappings |
| Disk await/IOPS | Node/block device | Compaction, commit log, SSTables |

### 19.2. Correlation Alone Does Not Prove Causation

| UTC | CQL p99 | Max GC pause | Post-GC heap | Cgroup mem | ReadStage pending | Disk await |
|---|---:|---:|---:|---:|---:|---:|
| 10:00 | 90 ms | 50 ms | 4.1 GiB | 9 GiB | 20 | 4 ms |
| 10:05 | 250 ms | 150 ms | 5.0 GiB | 11 GiB | 350 | 14 ms |
| 10:10 | 1,200 ms | 800 ms | 7.9 GiB | 14 GiB | 2,100 | 65 ms |
| 10:15 | 170 ms | 100 ms | 5.4 GiB | 12 GiB | 120 | 10 ms |

All figures are **hypothetical**. Establish offered load, per-node workload, retries, compaction, CPU quota, swap activity, and deployment timelines to determine true root cause.

### 19.3. Keep Metric Labels Bounded in Cardinality

~~~text
component=cassandra-server
dc=dc1
symptom=gc_pause_and_queue_growth
post_gc_heap_band=high
cgroup_oom_kill_delta=0
cpu_throttled_band=high
query_template=latest20_by_device_day
~~~

This is a recommended logging/metric schema, **not default Cassandra metric labels**. Never place raw tenant/device IDs, routing keys, secrets, or bind values inside metric labels.

## 20. Memory Budgets for Capacity and Failover

### 20.1. Partitioning the Budget (Conceptual Model—Never Blindly Sum Snapshots)

~~~text
Java heap
JVM native/metaspace/thread stacks
Direct/network/off-heap structures
Memory-mapped/file-backed resident pages
Kernel/accounted page cache
Safety margin for compaction/repair/failover

Regions may overlap when measured across RSS, NMT, and memory.stat.
~~~

| Hypothetical 32 GiB container | Planned budget |
|---|---:|
| Heap cap `-Xmx` | 16 GiB |
| JVM native/metadata/threads | 2 GiB |
| Direct/off-heap | 3 GiB |
| File cache/mmap/kernel | 6 GiB |
| Margin | 5 GiB |
| **Model total** | **32 GiB** |

Do not apply this table as a universal tuning prescription. Measure real peak consumption under load, inspect cgroup accounting, and preserve headroom for node outages, repairs, and streaming.

### 20.2. Having Quorum Does Not Mean Having Enough Memory

Under RF=3, `LOCAL_QUORUM` typically requires two replicas in the local DC. If one node goes down, the remaining two replicas still satisfy ACK rules, yet load, in-flight queues, and buffers shift onto them—plus hints, repair, and streaming add extra pressure when the third node returns.

## 21. Runbook A — Rising Post-GC Live Heap and Long Pauses

**Scenario:** Cassandra node has `-Xmx=16 GiB`; post-GC heap climbs from 8 to 14 GiB over an hour; pauses grow from 100 ms to several seconds, and `ReadStage Pending` rises.

1. **Scope:** affected node/rack/DC, JDK/collector, Cassandra version, recent changes.
2. **Measure:** GC logs pre/post heap, pauses, allocation rate, p99/errors, `tpstats`.
3. **Classify:** allocation churn vs. retained live heap—is GC able to reclaim objects?
4. **Queries:** wide/hot partitions, `SELECT *`, tombstones, analytic scans, large batches.
5. **Resources:** disk await, compaction, CPU throttling, swap, client retries.
6. **Mitigation:** throttle batches/backfills, cap fan-out, protect core user SLOs.
7. **Deep diagnostics:** class histogram or heap dump only after verifying disk headroom, CL impact, and security approval.
8. **Root cause:** caches/retention, queues, leaks, data modeling, or version bug.
9. **Test fix:** bounded queries, partition bucketing, or cache/heap adjustments in staging.
10. **Canary:** verify post-GC live heap, p99, error rate, and node health post-rolling deploy.

**Do not merely raise `-Xmx`**, especially where container cgroup limits leave no slack.

## 22. Runbook B — `OOMKilled` While Java Heap Has Headroom

**Scenario:** Heap used is 7 GiB (`-Xmx` 10 GiB), container limit is 16 GiB, yet restart reason is `OOMKilled`.

1. Confirm container OOM events rather than relying solely on exit code 137.
2. Inspect `memory.current/max/stat/events` on the exact container cgroup.
3. Compare process RSS/PSS, mapped/file cache, and JVM heap.
4. Check direct/native buffer pools, NMT (if enabled), and thread counts.
5. Correlate with network in-flight load, compaction/repair, and cache warm-up.
6. Reduce concurrency, payload bytes, and background pressure controllably.
7. Avoid running heap dumps when disk/memory quotas are already critical.
8. Rebudget heap, off-heap, and page cache allocations in staging.
9. Test under sustained traffic and degraded-replica failover scenarios.
10. Canary rollout and verify `oom_kill` delta, `memory.current`, p99, and error rates.

**Heap below `-Xmx` does not rule out cgroup memory exhaustion.**

## 23. Runbook C — GC Pauses Climb Alongside CPU Throttling or Swap

**Scenario:** GC wall pauses grow long even though post-GC heap drops cleanly; `cpu.stat nr_throttled` or `vmstat si/so` climbs.

1. Compare GC log **wall time vs. CPU time** alongside safepoint timelines.
2. Measure CPU quotas, per-core usage, and `nr_throttled` deltas.
3. Measure host steal time, memory/CPU/IO PSI, and swap-in/out activity.
4. Check retry storms, compaction load, and CPU-heavy query patterns.
5. Throttle non-essential jobs and enforce admission control.
6. Test adjusted CPU quotas/requests in staging.
7. Never swap GC collectors or inflate heap before gathering evidence.
8. Re-measure pauses, p99, queues, and throughput.
9. Never tune kernel sysctl or swap settings in production without SOPs.
10. Save a regression test reproducing the CPU quota constraints.

**Slow GC does not always mean a heap leak**; scheduler throttling or OS paging may be the culprit.

## 24. Runbook D — Direct Memory OOM and Connection Buffers

**Scenario:** `Direct buffer memory` appears while Java heap stays low and native transport in-flight requests rise.

1. Pinpoint the OOMing PID: Cassandra server or Java client app.
2. Check JDK direct-memory limits and `BufferPoolMXBean` metrics.
3. Compare RSS/PSS, cgroup memory stats, and NMT (if enabled).
4. Identify queries returning huge rows/pages and high bytes/response.
5. Check concurrency, retries, and connection/TLS churn.
6. Reduce request rate, page/response sizes, and in-flight caps.
7. Check known driver/server direct-buffer leaks for your exact release if evidence points there.
8. Raise direct-memory caps only when total container headroom permits.
9. Canary and monitor OOM events, native memory, p99, and errors.
10. Add bytes/s guardrails and native memory pressure alerts.

**Unconditionally raising `MaxDirectMemorySize` can turn a Java error into a fatal kernel `OOMKilled`.**

## 25. Runbook E — Slow Compaction/Flushes Cascading Into GC and Timeouts

**Scenario:** A cluster runs a backfill; `compactionstats` pending grows, disk await climbs, memtable flushes stall, and both live heap occupancy and write p99 rise.

1. **Pinpoint timing:** when did backfill, repair, or compaction start, and did schema or cell sizes change?
2. **Measure storage pressure:** free disk, IOPS, await, SSTable counts, compaction bytes, and pending tasks.
3. **Check read/write mix:** incoming writes, commit log sync, memtable occupancy, replication factor.
4. **Separate server vs. client:** Cassandra heap/GC vs. Java client buffers; both can suffer together.
5. **Shed load controllably:** pause/throttle backfill at safe checkpoints, rate-limit writes or bulk scans.
6. **Do not force extra major compaction or repair** merely because backlog metrics look high; that adds more I/O.
7. **Inspect query shapes:** hot partitions, tombstone density, large batches, heavy TTL expirations.
8. **Verify drain and capacity:** confirm flush and compaction queues drain when offered load drops.
9. **Validate fixes in staging:** partition bucketing, retention, compaction strategy, or faster/larger disks against a clear baseline.
10. **Canary:** verify read/write p99, GC pauses, disk await, and pending tasks stabilize.

**Do not make raising `-Xmx` your first move** when disk throughput is the bottleneck and queued requests hold objects in memory.

## 26. Runbook F — Native Thread Failure or File Descriptor Exhaustion

**Scenario:** A node logs `unable to create native thread` or `Too many open files` while heap usage stays modest.

1. **Classify the exact error:** native thread limit, FD limit, socket exhaustion, or JVM heap OOM.
2. **Measure threads:** JVM `ThreadMXBean`, `/proc/PID/status Threads`, and `pids.current/max`.
3. **Measure FDs:** `/proc/PID/limits` and FD count trend without dumping every raw path into tickets.
4. **Audit config:** pool sizes, thread stack sizes, systemd `TasksMax`, `ulimit -n/-u`, container PID limits.
5. **Inspect workload:** are clients opening a `CqlSession`/connections per request? Is Cassandra churning SSTables/files?
6. **Check for leaks:** do thread or FD counts keep rising even when offered load is flat or reduced?
7. **Mitigate:** curb connection churn, cap concurrency, pause non-essential jobs; avoid killing random processes.
8. **Tune carefully:** raise OS/container caps only after budgeting native stack RAM and valid FD needs.
9. **Verify:** thread/FD counts stabilize, native memory drops, connection errors and p99 recover.
10. **Regression test:** test sustained load, rolling restarts, reconnect storms, and high SSTable counts.

An FD or PID exhaustion outage can trigger timeouts and failed connections **without a single Full GC**. Never switch GC collectors when an OS limit is to blame.

## 27. Safe Testing and Drill Matrix

| ID | Scenario | Key evidence | Acceptance criteria |
|---|---|---|---|
| T01 | Young allocation churn | GC count, allocation/s, post-GC heap | Within pause and error SLOs |
| T02 | Live heap growth over time | Post-GC heap trend, histogram | Bounded without unbounded creep |
| T03 | Lab heap-space OOM | JVM error and GC logs | Correct OOM category identified |
| T04 | Lab direct-buffer OOM | `BufferPoolMXBean`, native/RSS | Not misdiagnosed from heap alone |
| T05 | Container `OOMKilled` | `memory.events`, runtime status | Detected despite heap headroom |
| T06 | Cgroup CPU throttling | `cpu.stat`, GC wall vs. CPU | Not mistaken for heap leak |
| T07 | Lab swap pressure | `vmstat si/so`, PSI, p99 | Guardrails and triage work |
| T08 | Large file-backed page cache | `memory.stat`, RSS/PSS | No double-counting mistake |
| T09 | Native thread exhaustion | `pids.max`, `Threads` | Not "treated" by raising `-Xmx` |
| T10 | File descriptor exhaustion | `/proc/PID/limits`, count | Exact resource identified |
| T11 | Wide partition reads | Rows/partition, read p99 | CQL and response bytes bounded |
| T12 | Tombstone-heavy queries | Tombstones/read, SSTables | Read amplification diagnosed |
| T13 | Large `SELECT *` in Java client | App heap, response bytes | Collect-all OOM prevented |
| T14 | Unbounded async fan-out | In-flight count, buffers, errors | Admission control holds |
| T15 | Large reactive `collectList` | App heap/GC | Replaced with bounded streaming |
| T16 | Retry storm during slow node | Attempts/logical op | Retry budget protects backend |
| T17 | Compaction backlog | Disk await, pending, p99 | No unchecked I/O overload |
| T18 | Backfill competing with reads | QPS, compaction, GC | Paused/throttled at guardrail |
| T19 | RF=3 with one replica lost | Replica headroom, CL, errors | Serves within designed SLO |
| T20 | Node restart and cold cache | Page cache, disk I/O, p99 | Controlled warm-up and recovery |
| T21 | Container limit changes | `memory.max/current/events` | Zero new OOM kills |
| T22 | JDK/GC collector upgrade | GC logs, flags, p99 | Compatible release + canary pass |
| T23 | NMT summary vs. native growth | NMT vs. RSS/cgroup | NMT not assumed to cover all native |
| T24 | Heap dump near full disk (negative) | SOP/guardrail | Unsafe dump blocked |
| T25 | Load test stop conditions | OOM/GC/disk/queue alerts | Test halts controllably |

### 27.1. Environment Tiering for Tests

- **Unit tests:** limits/timeouts, pagination logic, retry budgets, and admission control.
- **Single-node integration:** basic CQL, bounded paging, GC/memory metrics, and payload volumes.
- **Isolated load tests:** wide/hot partitions, compaction backlogs, disk pressure, CPU/memory quotas, OOM fault drills.
- **Multi-node RF/CL lab:** one replica down, rolling upgrades, hints/repair/streaming, and read/write correctness.

**Never execute OOM fault injection, CPU throttling drills, heap dumps, or compaction stress tests in production.** A single-node RF=1 test never validates RF=3 quorum behavior.

### 27.2. Stop Conditions

~~~text
[ ] Error/timeout rate exceeds approved budget.
[ ] Cgroup oom_kill increments or memory.current nears hard limit.
[ ] GC pause/time ratio breaches alert threshold persistently.
[ ] Free disk drops below minimum reserve for compaction/snapshots.
[ ] Pending messages/compactions climb with no drainage.
[ ] The load generator itself hits CPU/GC/OOM saturation.
[ ] An unintended node goes down outside the fault plan.
[ ] Quorum/CL or data correctness is put at risk.
~~~

**Stopping at a guardrail is a valid measurement result**; never hide it or push load higher merely to claim "peak QPS".

## 28. Common Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| "JVM `-Xmx 12 GiB` means the process uses only 12 GiB." | Metaspace, native/direct buffers, threads, and mmap sit outside heap |
| "If heap isn't full, the pod can't be `OOMKilled`." | Cgroups charge non-heap memory, native buffers, and file cache |
| "RSS equals Java heap used." | RSS combines heap, native, shared, and file-backed resident pages |
| "VSZ 100 GiB means 100 GiB of RAM consumed." | Virtual address reservations do not equal resident physical RAM |
| "Simply add RSS + file cache for total memory." | Shared and mapped pages may get double-counted |
| "NMT tracks all native allocations." | Coverage is partial; OS page cache is outside NMT |
| "Fix direct buffer OOM by raising `-Xmx`." | Check native limits, buffer usage, and in-flight requests |
| "`OOMKilled` always means Java `OutOfMemoryError`." | Kernel/cgroup kills happen at a separate OS layer |
| "Exit 137 always means memory OOM." | `SIGKILL` can come from other orchestration/operator actions |
| "Frequent Full GCs always mean a memory leak." | High churn, large live sets, CPU throttling, or small capacity can cause it |
| "Long GC pauses? Just increase heap." | CPU throttling, disk stalls, swap, or queues may be responsible |
| "90% heap before GC guarantees an error." | Inspect post-GC occupancy and collector behavior |
| "Host CPU is idle, so pods aren't throttled." | Per-pod cgroup quotas (`cpu.max`) still throttle containers |
| "`SwapUsed > 0` always explains p99." | Inspect active swap paging (`si/so`), PSI, and time-series correlation |
| "Cassandra memtable size = Java heap." | On/off-heap split depends on version and configuration |
| "Large caches should always be turned off." | Disabling caches can surge disk I/O and hurt p99 |
| "Huge pending compaction? Run major compaction." | Can worsen disk contention and exhaust free space |
| "`LIMIT 20` only scans 20 storage cells." | Tombstones and SSTable merges may scan far more cells |
| "Page size 100 limits the `SELECT` to 100 total rows." | It only bounds rows per network page |
| "Async/Flux guarantees bounded memory." | In-flight requests, buffers, or `collectList()` can still OOM |
| "Node `UN` means incident over." | Must verify heap, GC, p99, CL, and replica convergence |
| "Empty `netstats` means zero CQL traffic." | `netstats` tracks SSTable streaming, not normal CQL queries |
| "`jcmd heap_dump` is read-only and harmless." | Causes long pauses, huge disk writes, and exposes secrets |
| "Polling `/proc` files continuously is free." | `smaps_rollup`, `lsof`, and class histograms carry real cost |
| "Collector tuning works across every release." | Always verify Cassandra/JDK compatibility matrices |
| "Raising OS `ulimit` to unlimited fixes FD leaks." | It only delays failure until the next kernel/process limit hits |
| "GC p99 = API p99." | Different scopes and distributions |
| "Quorum is intact, so memory headroom is safe." | Node failover concentrates load onto surviving replicas |

## 29. Practice Exercises and Answers

### Q1 — Heap vs. RSS

A node runs with `-Xmx=12 GiB` and shows 15 GiB RSS. Does that prove a memory leak?

**Answer:** No. RSS covers heap, native allocations, mapped/file-backed pages, and shared memory. Inspect trends, post-GC heap, buffer pools, NMT/cgroups, and workload.

### Q2 — `OOMKilled`

Heap used is 7 GiB (`-Xmx` 10 GiB), pod limit is 16 GiB, yet `memory.events oom_kill` increments. Is this possible?

**Answer:** Yes. Cgroup accounting charges native allocations, file cache, and kernel memory—not solely Java heap.

### Q3 — Exit 137

A container exits with code 137. Is that sufficient proof of an OOM-kill?

**Answer:** No. `SIGKILL` can come from other sources; inspect runtime termination reason, cgroup `memory.events`, and authorized kernel logs.

### Q4 — VSZ

`ps` reports VSZ 100 GiB and RSS 12 GiB. Has the server actually consumed 100 GiB of RAM?

**Answer:** No. VSZ is virtual address mapping; RSS/PSS and cgroup metrics reflect actual physical residency and memory pressure.

### Q5 — Double-Counting Page Cache

Should you add 12 GiB RSS and 4 GiB `memory.stat file` to claim the process uses exactly 16 GiB?

**Answer:** No. File-backed pages can be counted in both metrics; work within a single cgroup boundary, PSS, and proper accounting breakdowns.

### Q6 — GC Churn

Pre-GC heap looks very high, yet after GC it drops to 40% with short pauses. Is there definitely a live-set leak?

**Answer:** No. High churn of short-lived objects behaves like this. Monitor multi-window trends and total GC overhead.

### Q7 — Rising Live Heap

Post-GC heap grows over several hours under steady load, with full/mixed GCs reclaiming little. Next step?

**Answer:** Inspect retained references, caches, in-flight requests, query payloads, known version bugs, and an approved class histogram or dump—never rely on one data point.

### Q8 — CPU Throttling

GC wall pauses are long while GC CPU time is low and cgroup `nr_throttled` rises. Hypothesis?

**Answer:** The JVM is starved of CPU slices by cgroup quota limits or host scheduling contention; correlate CPU quotas, per-core metrics, and load.

### Q9 — Direct Buffer OOM

Java logs `Direct buffer memory` while heap has plenty of space. Should you simply increase `-Xmx`?

**Answer:** No. Inspect direct/native buffers, direct caps, RSS/cgroup limits, in-flight traffic, and total container headroom.

### Q10 — NMT

NMT summary reports 8 GiB while RSS is 12 GiB. Does that mean 4 GiB definitely leaked?

**Answer:** No. NMT excludes several native/JNI/file-backed allocations and uses different accounting rules than RSS.

### Q11 — Memtable Memory

`nodetool tablestats` reports high memtable live data. Does that exact amount sit inside Java heap?

**Answer:** Not necessarily. Memtables may allocate on-heap or off-heap depending on release/config; verify against JVM/native metrics and version docs.

### Q12 — Tombstones

A `SELECT` specifies `LIMIT 20` yet scans thousands of tombstones. Why does p99 stay high?

**Answer:** `LIMIT` restricts returned live rows, not the tombstone and SSTable merge scanning done underneath.

### Q13 — Paging

Driver page size is 100, and a query matches 100,000 rows. Does that guarantee only 100 rows total are loaded?

**Answer:** No. Page size controls rows per network round-trip; use CQL `LIMIT` or stop iterating pages intentionally.

### Q14 — Application Heap OOM

A Spring service hits OOM calling `collectList()`, while Cassandra node heap stays healthy. Where do you fix first?

**Answer:** In the client pipeline: enforce bounded streaming, paging, row/byte limits, and concurrency—do not inflate Cassandra heap.

### Q15 — Disk Pressure

GC pauses climb alongside `compactionstats` pending and disk await. Does that prove a misconfigured GC collector?

**Answer:** No. Disk stalls lengthen request queues, keeping objects live in heap longer and amplifying GC pressure; isolate the disk bottleneck first.

### Q16 — Heap Dump

A node has 3 GiB free disk left and a 12 GiB heap. Should you trigger a heap dump on that volume immediately?

**Answer:** No. The dump will likely fill the disk, trigger a long pause, and expose sensitive data. Require approval, safe external storage, and quorum planning.

### Q17 — Native Thread Creation

The JVM throws `unable to create native thread` while heap is only 50% full. What do you inspect?

**Answer:** Native thread counts/stack sizes, `pids.max`, `TasksMax`, `ulimit -u`, native memory headroom, and thread leaks.

### Q18 — FD Counts

`Too many open files` rises after connection churn. Will changing the GC collector fix it directly?

**Answer:** No. Inspect FD limits, socket/file lifecycles, and resource leaks; GC configuration does not raise OS open-file limits.

### Q19 — RF/CL

RF=3, `LOCAL_QUORUM`, one node down. Logical availability holds on the two surviving replicas; can p99 and GC still worsen?

**Answer:** Yes. Traffic shifts onto the remaining replicas, and retries, hints, and catch-up increase resource demand.

### Q20 — `netstats`

`nodetool netstats` is empty. Does that mean no native CQL network traffic exists?

**Answer:** No. `netstats` primarily tracks SSTable streaming; inspect native transport and OS network telemetry instead.

### Q21 — Retry Amplification

1,000 logical reads/s where 20% retry once. Minimum request attempt rate?

**Answer:** Approximately 1,200 attempts/s under those simplified assumptions; gateway retries or speculative execution push it higher.

### Q22 — Cgroup CPU

Host CPU utilization looks low, yet the Cassandra pod experiences frequent throttling. Is this contradictory?

**Answer:** No. The host can have idle cores while the container hits its own `cpu.max`/quota ceiling.

### Q23 — Recovery

After restarting, a node reports `UN` and low heap usage. Is recovery confirmed?

**Answer:** No. Verify API p99/errors, memtable/compaction queues, hints/streaming, cgroup memory, GC stability, and RF/CL health.

### Q24 — Capacity

A 16 GiB container runs with `-Xmx 15 GiB` under heavy cache and direct-buffer traffic. Is it safe just because heap currently has 1 GiB free?

**Answer:** No. Native/off-heap structures, page cache, kernel memory, thread stacks, peaks, and failovers easily exceed 1 GiB outside heap.

### Q25 — Measurement

Does a 1-second GC pause on Node B automatically equal 1-second API p99?

**Answer:** No. Scopes and distributions differ; queries may hit other coordinators/replicas, while network, queuing, and retries also shape API latency.

## 30. Operational Checklist: Before, During, and After Incidents

### 30.1. Before an Incident

~~~text
[ ] Inventory Cassandra, JDK, and Java Driver versions plus GC collectors.
[ ] Measure actual JVM -Xms/-Xmx and container cgroup memory/CPU limits.
[ ] Configure GC logging with UTC timestamps, rotation, disk quota, and retention.
[ ] Track heap used/committed, post-GC live set, and GC pause durations.
[ ] Track process RSS/PSS, direct/native buffers, and cgroup memory.current/events.
[ ] Track cpu.stat throttling plus memory/CPU/IO PSI where supported.
[ ] Track disk free/IOPS/await, swap activity, and FD/thread counts.
[ ] Collect nodetool/JMX telemetry: tpstats, compactionstats, tablestats.
[ ] Document query templates, partition distributions, and TTL/tombstone behavior.
[ ] Enforce admission control, bounded paging/concurrency, and retry budgets.
[ ] Set guardrails and capacity headroom for repairs, backfills, and streaming.
[ ] Maintain runbooks for rolling restarts, RF/CL availability, and recovery.
[ ] Secure permissions and isolated storage for approved heap/thread artifacts.
[ ] Never rely solely on a single p99 or heap % threshold.
~~~

### 30.2. During Triage

~~~text
[ ] Confirm exact node, PID, container, DC/rack, and UTC timestamps.
[ ] Separate Java app OOM, Cassandra server JVM OOM, and kernel OOMKilled.
[ ] Capture GC log snapshots, post-GC heap levels, and allocation/pause trends.
[ ] Capture memory.current/max/stat/events and container runtime OOM status.
[ ] Correlate cgroup CPU throttling with host swap/PSI at matching timestamps.
[ ] Inspect disk await/free, memtable flushes, and compaction/repair queues.
[ ] Inspect query shapes: partition keys, LIMIT, page sizes, and tombstones.
[ ] Check driver outstanding requests, retries, connection churn, and payload sizes.
[ ] Check thread/PID caps and FD counts/limits when errors point there.
[ ] Avoid running unapproved or repeated heap dumps and class histograms.
[ ] Never mass-restart nodes and break quorum.
[ ] Never trigger major compaction or heavy repair when disks are tight.
[ ] Never increase heap or direct memory without checking cgroup headroom.
[ ] Log all collected evidence, hypotheses, and applied mitigations.
~~~

### 30.3. After Remediation / Recovery

~~~text
[ ] Post-GC heap remains stable across representative workload windows.
[ ] GC pauses/overhead and CQL/API p95/p99 meet SLOs.
[ ] memory.events oom_kill stays flat; native/RSS shows no upward drift.
[ ] Cgroup CPU throttling, swap-in/out, and PSI remain within acceptable bounds.
[ ] Disk IOPS/await/free and compaction backlogs do not grow unchecked.
[ ] Stage pending/dropped counts and driver timeouts/retries return to baseline.
[ ] Node status, internode links, hints, and repair posture are healthy.
[ ] RF/CL contracts, read/write correctness, and business invariants pass.
[ ] Tested against wide partitions, heavy TTL/tombstones, and failover headroom.
[ ] Observed over a sustained stability window rather than seconds post-restart.
[ ] Postmortem records root cause, ruled-out paths, and rollback steps.
[ ] Alerts, memory budgets, and query guardrails updated.
[ ] All changes recorded in operational runbooks with clear owners.
[ ] STEP 6 Content QA remains a separate downstream phase not run here.
~~~

## 31. Reporting Rules and Ownership Boundaries

A useful incident report should never stop at "Cassandra hit OOM". Structure it like this:

~~~yaml
# Example report structure, not observations from a real incident.
incident_id: cassandra-mem-001
environment: isolated-staging
timestamp_utc: "2026-11-21T10:00:00Z"
scope:
  datacenter: dc1
  affected_nodes: 1
  affected_apps: ["telemetry-api"]
symptom:
  category: "cgroup_oom_kill"
  customer_impact: "CQL timeouts and API 5xx"
observations:
  jvm_heap_after_gc: "stable"
  process_rss: "high"
  cgroup_memory_events: "oom_kill increased"
  disk_compaction: "normal"
hypothesis:
  category: "native-plus-file-cache-headroom"
mitigation:
  action: "bounded client concurrency / rollback oversized workload"
validation:
  success_rate: "within agreed SLO"
  p99: "within agreed SLO"
  memory_events: "no new oom_kill over observation window"
limitations:
  - "No heap dump taken; native allocation attribution incomplete"
~~~

This is strictly a **report template**, not claimed telemetry from a live cluster. Always include owners, applied changes, authorization scope, start/end timestamps, links to preserved graphs, and explicit evidentiary gaps.

### 31.1. Conclusions That Must Carry Qualifications

- "`OOMKilled`" → requires runtime/cgroup/kernel evidence, not exit code 137 alone.
- "Heap leak" → requires multi-window retention trends, not a single `heap used=90%` sample.
- "GC caused timeouts" → requires timeline proof after checking disk, CPU, network, and queues.
- "Raising `-Xmx` fixed it" → must verify cgroup/native headroom and failover survival.
- "Cluster recovered" → requires API SLOs, retries, RF/CL health, and compaction/repair posture—not merely `UN`.
- "Caches are wasting RAM" → must evaluate hit rates and read-I/O trade-offs.

## 32. Summary

To resolve **prolonged heap/GC pauses, off-heap memory issues, and OS resource contention** in Cassandra systematically:

1. **Separate JVM heap, off-heap/native, RSS/PSS, mmap, page cache, and cgroup accounting.** Each reflects a different boundary—never sum them blindly.
2. **Read GC pauses alongside post-GC live heap, allocation rate, and CPU throttling.** Long pauses do not automatically prove a memory leak or wrong collector.
3. **Java OOM and kernel `OOMKilled` are separate failure modes.** Distinguish them via JVM logs, runtime statuses, and `memory.events`.
4. **Memtables, caches, compression metadata, and native transport allocate across heap and off-heap** depending on release; `-Xmx` is never the entire memory budget.
5. **CQL data modeling directly drives resource demand:** wide partitions, tombstones, uncompacted SSTables, `ALLOW FILTERING`, huge batches, and retry storms amplify pressure.
6. **Page size does not replace `LIMIT`**, async/reactive pipelines do not guarantee bounded memory by default, and Java client OOMs do not equal Cassandra heap failures.
7. **Examine disk I/O, compaction, repair, streaming, and commit log alongside GC** because I/O stalls swell request queues and retained objects.
8. **Native memory, thread stacks, file descriptors, PID caps, and swap** are independent OS boundaries that must be tracked explicitly.
9. **`nodetool`, JMX, GC logs, `/proc`, cgroups, and JVM tools carry vastly different risk**; heap dumps and class histograms are not default first steps in production.
10. **Size headroom for failovers, compaction, and bursts** instead of packing heap/direct limits tightly up against pod limits at idle.
11. **Confirm recovery across layers:** stable GC/heap/native usage, zero new cgroup OOM kills, draining disk/executor queues, intact RF/CL, and healthy API p99/error rates.
12. **Enforce safety guardrails in runbooks and drills:** never inject OOM/fault stress in production, never restart multiple replicas simultaneously, and never capture heap dumps containing sensitive data without approval.

The essential diagnostic question is never just **"Why is Cassandra heap/GC climbing?"**, but rather: **"Which exact process or cgroup is under pressure, which memory pool or OS resource is exhausting, which queries or background jobs are holding or consuming it, and which bounded change restores p99 and RF/CL correctness without triggering a secondary outage?"** Diagnosing along these boundaries prevents blind heap inflation, missed container OOM kills, and mistaking disk or CPU bottlenecks for memory leaks.
