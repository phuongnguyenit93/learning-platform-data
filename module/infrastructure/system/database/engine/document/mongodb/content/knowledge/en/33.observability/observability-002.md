# CPU, RAM, Disk, WiredTiger Cache, and Memory Pressure in MongoDB

## 1. Why Observe Multiple Layers Simultaneously?

Suppose an application runs a MongoDB replica set. During peak hours, API response times rise from around 40 ms to 800 ms. The dashboard shows:

- Primary host CPU around 55%.
- Host RAM "used" at 93%.
- WiredTiger cache near its configured maximum.
- Disk write latency spiking frequently.
- Requests/second up only 20% compared to normal.

If you only look at 93% RAM used, a hasty decision would be to **increase cache size or restart `mongod`**. Yet a nearly full WiredTiger cache can indicate healthy cache utilization; the true cause might be **slow I/O, eviction falling behind, a missing index on a query, or a long-running transaction pinning multiple data versions**.

A performance incident typically involves multiple links in a chain:

```text
            Application request
                    |
                    v
              MongoDB query
                    |
           +--------+--------+
           |                 |
           v                 v
     CPU execution       Memory access
   parse / plan /       WT internal cache
  filter / sort /         and OS cache
 compression                |
           |                 |
           +--------+--------+
                    |
                Cache miss
                    |
                    v
             Storage read I/O
                    |
               Write workload
                    |
           +--------+--------+
           |                 |
           v                 v
       Dirty pages        Journal
           |                 |
           +--------+--------+
                    |
              Storage write I/O
                    |
                  Disk
```

The goal of this lesson in the **Observability** chapter of the **MongoDB Document Database Engine** module is to read signals from **CPU, RAM, disk, and WiredTiger cache** accurately, then identify the root causes of **memory pressure** without causing unnecessary disruption to the system.

After this lesson, you will be able to:

1. Distinguish CPU busy executing queries from CPU waiting on I/O or being cgroup-throttled.
2. Distinguish host physical RAM, process RSS/virtual memory, OS page cache, and WiredTiger internal cache.
3. Read key metrics from `serverStatus()` and `hostInfo()`.
4. Understand cache occupancy, dirty bytes, eviction, cache misses, and when eviction is normal versus a bottleneck.
5. Read disk space, IOPS, throughput, latency, queue depth, and checkpoint/journal signals.
6. Explain the differences among `dataSize`, `storageSize`, `indexSize`, and actual filesystem usage.
7. Combine MongoDB, OS/container, and application latency signals to classify bottlenecks.
8. Design dashboards, alerts, capacity planning, and runbooks for CPU/disk/RAM pressure.
9. Practice **read-only** commands in `mongosh` and the OS, along with a small lab with safe cleanup.

## 2. A Four-Layer Observability Model

No single metric tells the whole story about MongoDB's health. Break it down into:

| Layer | Target | Key Question |
| --- | --- | --- |
| Application | API p50/p95/p99, QPS, errors, timeouts, pool wait | Are users being impacted? |
| MongoDB | operations, active clients, WiredTiger, locks, transactions, replication | What is MongoDB processing or waiting on? |
| OS / container | CPU, RSS, available memory, swap, iowait, page faults, cgroup memory/CPU limits | Which resource limits is the process hitting? |
| Storage and infrastructure | IOPS, throughput, read/write latency, queue, free disk, network, cloud volume limits | Are devices and bandwidth keeping up? |

An example triage flow:

```text
API p95 increases
    |
    v
MongoDB read latency increases?
    |
    +-- Yes --> Cache misses increase?
    |              |
    |              +-- Yes --> Disk read latency increases?
    |                              |
    |                              +-- Yes --> I/O bottleneck
    |                              +-- No  --> Working set/cache pressure
    |
    +-- No  --> App connection pool / network / downstream
```

This diagram is a **triage guide**, not an absolute decision tree. Signals can rise together and must be correlated by timestamp.

### 2.1. Prioritize Time-Series Data

95% CPU at a single instant does not mean sustained CPU saturation. 90% RAM used can be completely normal on Linux due to the filesystem cache. `wiredTiger.cache["bytes currently in the cache"]` at 90% of its maximum does not prove the application is thrashing.

Measure:

- **Absolute levels:** how much RAM/cache/disk is currently in use.
- **Rate of change:** how fast counters increase per second.
- **Ratios:** dirty bytes / max cache, free disk / capacity, errors / requests.
- **Latency:** API and disk p95/p99.
- **Trends:** whether metrics climb steadily over 15–60 minutes or only spike briefly.
- **Concurrent events:** deployments, index builds, backups, bulk imports, failovers.

## 3. CPU: Compute Capacity and Query Bottlenecks

### 3.1. Read CPU Utilization Relative to Core Count

A host has 8 logical CPU cores. A process consuming 100% of **one core** may appear as only ~12.5% host CPU on a dashboard normalized across total cores.

Example:

```text
Host: 8 logical cores
One MongoDB thread: 100% of one core
Overall host CPU: ~12.5% (if other cores are idle)
```

Some tools like `top` can display 100% for one core and **800% for a process saturating all 8 cores**, depending on mode. Before comparing CPU across dashboards, standardize the denominator and representation.

### 3.2. CPU Time Has Multiple Categories

On Linux, operators commonly inspect:

| Component | Approximate meaning | When high, investigate |
| --- | --- | --- |
| `user` | CPU running user-space code | Query execution, BSON parsing, compression, aggregation, TLS |
| `system` | CPU executing kernel code | Syscalls, storage/network I/O, filesystem |
| `iowait` | CPU idle while waiting on pending I/O; OS-specific definition | Disk latency/queue; do not treat as MongoDB CPU "computing" |
| `steal` | VM wants to run but hypervisor allocates CPU elsewhere | Host overcommit/cloud infrastructure |
| `idle` | Unused CPU | Does not rule out single-core or I/O bottlenecks |
| `throttled` | Container exceeded CPU quota and was throttled | Kubernetes/Docker cgroup CPU limits |

**High CPU utilization is not always caused by queries**, and **low CPU utilization does not mean the system has no bottleneck**.

### 3.3. Common Causes of High CPU in MongoDB

1. **COLLSCAN** due to missing indexes or non-selective query predicates.
2. **In-memory SORT** or aggregations processing large numbers of documents.
3. **Complex regex** or heavy expressions/transformations.
4. **Large aggregations** such as `$group`, `$lookup`, `$unwind` over large datasets.
5. **Compression/decompression** depending on codec and workload.
6. **Index builds** or maintenance operations.
7. **Continuous updates** on frequently modified documents/indexes.
8. **High connection concurrency**, creating excessive competing CPU work.
9. **Encryption/TLS** or client/server serialization as workload grows.
10. **Search/Vector Search services** may have **separate** processes/resources; not all search CPU lives inside `mongod`.

If a single query is bound to one core due to internal execution, having idle cores on the host will not necessarily make that query faster. Evaluate **query plans and parallel workloads**, not just adding CPU.

### 3.4. Signs of a CPU Bottleneck

You can suspect CPU is the constraint when:

- Process CPU remains near its quota/capacity;
- API latency rises alongside QPS;
- MongoDB operation execution time increases;
- Disk latency and cache misses show no matching rise;
- cgroup CPU throttling rises or the run queue lengthens;
- `explain` shows high examined documents/keys relative to returned documents;
- Reducing a heavy query group improves both CPU and p95.

Never declare CPU the root cause from a single `top` snapshot.

### 3.5. Cause-Specific Actions

| Observation | Evidence-based action |
| --- | --- |
| `COLLSCAN` on hot path | Inspect query shape and appropriate indexes |
| Large in-memory sort | Review compound index/filter/sort order; bound result size |
| Pipeline cardinality explosion | Trim `$unwind`/joins/groups, filter early where valid |
| Bulk operations consuming CPU | Throttle/batch, move outside peak hours |
| Low CPU quota, rising throttling | Adjust quota/requests/limits when capacity permits |
| One core hot, total CPU low | Inspect single operations/locks before scaling cores |
| Index build running during peak | Schedule DDL and monitor build progress |
| Queries optimized but real load grew | Evaluate vertical/horizontal scaling with benchmarks |

Do not kill operations or restart the primary solely because CPU is high without confirming impact, authorization, and runbook procedures.

## 4. RAM: Distinguishing What Consumes Memory

### 4.1. Four Easily Confused Concepts

```text
Physical RAM / Container memory limit
  |
  +-- mongod process memory
  |       |
  |       +-- WiredTiger internal cache
  |       +-- query execution/aggregation memory
  |       +-- connections, stacks, allocators
  |       +-- journals/metadata/other allocations
  |
  +-- OS filesystem/page cache
  |       +-- cached compressed database file blocks
  |
  +-- OS/kernel memory and other processes
  |
  +-- Free/available memory
```

- **Physical RAM:** total memory installed on the machine.
- **Process RSS/resident:** `mongod` memory pages currently resident in RAM (subject to shared-page accounting nuances).
- **Virtual memory/VIRT:** not equivalent to actual physical memory used; includes mapped/reserved address space.
- **WiredTiger internal cache:** an internal buffer with **its own size limit** holding WiredTiger pages and metadata.
- **Filesystem/page cache:** RAM managed by the OS to cache file blocks, including database files on disk.
- **Memory available:** OS estimate of memory available to new applications without heavy swapping; distinct from raw "free".

### 4.2. `mem.resident` Differs from `wiredTiger.cache`

MongoDB `serverStatus.mem.resident` is reported in **MiB**, approximating process resident RAM. WiredTiger cache metrics are measured in **bytes**.

Hypothetical example:

```text
Host RAM                         16 GiB
WiredTiger cache maximum         7.5 GiB
WiredTiger bytes currently       7.1 GiB
mongod resident                  10.2 GiB
OS filesystem cache              3.2 GiB
```

These numbers **cannot simply be added or subtracted** to compute a "true total" because each metric has different boundaries and accounting. Key takeaway: **RSS being larger than WiredTiger cache is normal**, because `mongod` also allocates memory outside the cache.

### 4.3. Is Very Large `mem.virtual` Necessarily an Error?

No. A process's virtual address space can be large due to memory mapping, reservations, and allocator behavior. Virtual size is **not** physical RAM consumed.

Use RSS, private/anonymous memory, OS `MemAvailable`, cgroup metrics, and OOM/swap signals to evaluate real pressure instead of alerting solely on VIRT.

### 4.4. "95% RAM Used" Can Be Normal

Linux uses unused RAM for the page cache. When a process needs memory, clean page cache pages can be reclaimed.

Example:

```text
Total RAM:      16 GiB
Used:           15 GiB
Free:          0.5 GiB
Available:      4 GiB
Swap in/out:  near 0
```

This is not yet proof of severe RAM starvation. Inspect **MemAvailable**, swap activity, memory pressure stalls, major faults, OOM events, and latency.

Conversely, a host showing "70% used" but running multiple **containers with 4 GiB cgroup limits** can still OOM if a single container hits its own limit.

## 5. WiredTiger Internal Cache and Filesystem Cache

### 5.1. Why Are There Two Caches?

MongoDB with WiredTiger uses **both its internal cache and the OS filesystem cache**:

```text
                mongod Query
                     |
                lookup B-tree
                     |
              WiredTiger cache
              (pages / metadata)
                     |
              cache miss / read
                     |
              OS filesystem cache
                     |
              cache miss / storage
                     |
                  Disk / SSD
```

- **WiredTiger internal cache** manages pages the storage engine needs for reads/writes, holds dirty/clean pages, and handles eviction.
- **Filesystem cache** is managed by the OS and can hold MongoDB's **compressed file blocks**, reducing physical disk I/O.
- Each cache has different measurement and eviction/reclaim mechanisms.

Therefore, **increasing WiredTiger cache does not always reduce disk reads**. You can starve the OS filesystem cache and actually worsen I/O.

### 5.2. Default Cache Size

According to current MongoDB documentation, the default WiredTiger internal cache size is the **larger of**:

\[
0.5 \times (\text{RAM} - 1 \ \text{GB})
\]

and:

\[
0.256 \ \text{GB}
\]

For example, on a 4 GB RAM instance:

\[
0.5 \times (4 - 1)=1.5 \ \text{GB}
\]

With 16 GB RAM:

\[
0.5 \times (16 - 1)=7.5 \ \text{GB}
\]

This is the **default rule**, not a guarantee that the process consumes only that many bytes at all times or that half the host RAM always stays "free." Beyond the cache, memory is used by queries, connections, the allocator, and the OS filesystem cache.

When using containers, check `hostInfo.system.memLimitMB` and actual cgroup limits; in some configurations WiredTiger may not detect all container memory limits. Do not size the cache from host RAM when `mongod` is only allocated a fraction of RAM via a container.

### 5.3. Configuration Options That Change Cache Size

MongoDB supports options such as:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 2
```

Or depending on the version:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizePct: 50
```

These illustrate **two separate options**; do not set both `cacheSizeGB` and `cacheSizePct` simultaneously.

MongoDB documentation advises **avoiding raising the cache above the default** without empirical justification. Percentage settings have version- and RAM-dependent bounds; increasing the value can starve the filesystem cache, non-cache process memory, and the OS.

**Do not modify cache configuration directly on production during a lab exercise.** Configuration changes may require restarts or operational procedures, affecting availability and failover; they must be controlled by the infrastructure owner.

### 5.4. What Does High Cache Occupancy Signal?

A cache is designed to use memory to improve performance. Therefore:

```text
max cache:         8.0 GiB
current cache:     7.6 GiB
occupancy:        95%
```

**Is not enough to conclude there is a problem.** If:

- eviction progresses smoothly;
- page reads from disk are low/stable;
- dirty bytes are not climbing abnormally;
- application threads rarely have to perform eviction themselves;
- p95 query latency is stable;
- the OS is not swapping or hitting OOM;

then a nearly full cache may be completely healthy.

Cache pressure becomes concerning when **sustained high occupancy is accompanied by eviction struggles, rising page-ins, rising waits, or degraded application latency**.

## 6. Dirty Pages, Checkpoints, and Eviction

### 6.1. Clean and Dirty Pages

A page is:

- **Clean:** contains no uncommitted/unflushed modifications requiring persistence; generally easier to evict.
- **Dirty:** contains modifications not yet written/synced to data file structures per WiredTiger's mechanism.

```text
Update document
       |
       v
WiredTiger cache
  dirty page
       |
       +----> eviction/reconciliation/write path
       |
       +----> periodic checkpoint runs
       |
       v
Data files / storage
```

Do not equate a dirty page with "unprotected" data. MongoDB also relies on the **journal** and write concern to uphold durability policies. Data page flushes/checkpoints can happen after a write is acknowledged under the relevant contract.

### 6.2. Checkpoints and the Journal Have Different Purposes

- **Journal:** records information required to support crash recovery in the storage engine.
- **Checkpoint:** persists a consistent state of data to storage during WiredTiger management cycles.
- **Eviction:** frees or prepares pages to be freed from the internal cache to make room for new work.

These three mechanisms are related but not identical. **A flushed journal does not mean dirty pages in the internal cache drop to zero**.

### 6.3. Eviction Is Normal

When the working set exceeds the cache, WiredTiger must select pages to evict from cache and read back later if needed. Two situations exist:

**Healthy eviction:**

```text
Cache near target
     |
Eviction workers make progress
     |
Cache has room for new pages
     |
Latency stays relatively stable
```

**Eviction pressure:**

```text
Cache near target
     |
Eviction falls behind / pages are pinned
     |
Application threads must assist eviction or wait
     |
Latency, write stalls, and disk I/O increase
```

There is no "high eviction count = error" across all workloads. Watch **rate, eviction type, application waits, and latency**.

### 6.4. Page Pinning and Long-Running Transactions

A long-running transaction or snapshot reader holding an old state can prevent certain pages or update versions from being reclaimed easily. Consequences:

- Cache must retain extensive history/update versions.
- Eviction is impeded.
- Dirty/cache pressure rises.
- Other operations wait, time out, or roll back depending on conditions.
- Storage history/tracking overhead may grow.

Do not simply increase cache size when a transaction stays open for tens of minutes. Locate the long-lived transaction, cursor, or snapshot and inspect the application code.

### 6.5. Dirty Cache Percentage

A commonly referenced metric:

\[
\text{Dirty cache fraction}
=
\frac{\text{tracked dirty bytes in cache}}
{\text{maximum bytes configured}}
\]

If dirty bytes = 1 GiB and max cache = 8 GiB, the dirty fraction is roughly 12.5%.

Do not rely on an arbitrary static threshold like "above 20% means broken." Consider the **version's eviction/checkpoint trigger points**, write patterns, disk latency, duration of the climb, and application state. **A steadily climbing dirty fraction paired with slow storage writes** is far more significant than a brief high reading.

## 7. Key WiredTiger Cache Metrics

In `mongosh`, on a `mongod` using WiredTiger:

```javascript
const status = db.serverStatus();
const cache = status.wiredTiger?.cache;

printjson({
  maxBytes: cache?.["maximum bytes configured"],
  currentBytes: cache?.["bytes currently in the cache"],
  dirtyBytes: cache?.["tracked dirty bytes in the cache"],
  pagesReadIntoCache: cache?.["pages read into cache"],
  pagesWrittenFromCache: cache?.["pages written from cache"],
  pagesEvictedByAppThreads:
    cache?.["pages evicted by application threads"],
  unmodifiedPagesEvicted:
    cache?.["unmodified pages evicted"],
  modifiedPagesEvicted:
    cache?.["modified pages evicted"]
});
```

Field names with spaces are the **actual statistics keys** in WiredTiger; hence bracket notation is used. Some metrics may be renamed or absent across versions. Use optional chaining and check for existence before feeding them into monitoring.

### 7.1. `maximum bytes configured`

The configured limit of the internal cache, **not the total RSS limit of the process**. Used as the reference denominator for occupancy and dirty fraction.

### 7.2. `bytes currently in the cache`

Bytes currently residing in the WiredTiger cache. It can stay near the maximum during normal operation.

\[
\text{Cache occupancy} =
\frac{\text{Current bytes}}{\text{Max bytes}}
\times 100\%
\]

This is **occupancy**, not directly hit ratio or memory pressure.

### 7.3. `tracked dirty bytes in the cache`

Volume of dirty bytes tracked by WiredTiger in the cache. Rapidly rising dirty bytes can indicate a write burst or flushing/eviction falling behind. Read alongside disk write latency, checkpoint duration, and page eviction/wait counters.

### 7.4. `pages read into cache`

This is a **cumulative counter** of pages read into cache. To evaluate cache miss/page-in activity, compute the **delta between two samples on the same `mongod` process**, divided by elapsed time.

```text
Sample at T1: 1,000,000 pages read
Sample at T2: 1,006,000 pages read
T2 - T1 = 60 seconds

Page read rate ≈ 6,000 / 60 = 100 pages/s
```

A rate higher than baseline may suggest a larger working set, full collection/index scans, eviction churn, or a cold cache after restart. However, a page read served from the OS filesystem cache **does not necessarily trigger physical disk I/O**; verify against OS disk read metrics.

### 7.5. `pages written from cache` and Eviction

Write and eviction counters are cumulative. They increment whenever the engine works; **rising counters alone are not errors**.

Watch:

- `modified pages evicted` and `unmodified pages evicted`.
- `pages evicted by application threads`.
- `application threads page read from disk to cache time (usecs)`.
- `application threads page write from cache to disk time (usecs)`.
- `operations timed out waiting for space in cache` if provided.
- `eviction server unable to reach eviction goal` and wait/eviction-blocked counters if available in your version.

Some internal metrics change names across releases; verify against actual `serverStatus()` output before building dashboards.

### 7.6. Why Must You Compute Rates/Deltas?

`pages read into cache` might be 10 million after 40 days of uptime. Comparing that raw total against a node restarted 2 hours ago is **meaningless**.

Use:

\[
\text{Rate} =
\frac{\text{counter}_{T2}-\text{counter}_{T1}}
{T2-T1}
\]

Notes:

- Counters can reset when `mongod` restarts.
- Some values are large BSON `Long` integers; converting to JS `Number` has precision limits.
- Do not compare raw totals across two different primaries while ignoring uptime.
- Choose a stable sample interval and use reliable clocks.
- Watch sampling overhead and metric cardinality.

## 8. Reading `serverStatus()` for RAM and Load

### 8.1. A Compact, Read-Only Snapshot

```javascript
const s = db.serverStatus();

printjson({
  host: s.host,
  process: s.process,
  uptimeSeconds: s.uptime,
  mem: s.mem,
  connections: {
    current: s.connections?.current,
    available: s.connections?.available,
    active: s.connections?.active
  },
  activeClients: s.globalLock?.activeClients,
  opcounters: s.opcounters
});
```

Meaning:

| Metric | Interpretation |
| --- | --- |
| `mem.resident` | Process resident RAM in MiB; can grow as cache warms up |
| `mem.virtual` | Virtual address space in MiB, not RSS |
| `connections.current` | Currently open connections |
| `connections.active` | Connections currently executing operations, if present |
| `globalLock.activeClients.readers/writers` | Active client readers/writers per server semantics |
| `opcounters` | Read/write operation counters; compute rates via deltas |
| `uptime` | Used to detect counter resets after restarts |

Do not continuously dump full `serverStatus()` into logs: the output is large, some fields are sensitive, and you should collect only the specific metrics needed.

### 8.2. Connections Do Not Equal CPU

10,000 connections **do not mean** 10,000 operations are running. Many connections may sit idle in pools. Conversely, 100 connections issuing parallel operations can easily saturate a node.

If `connections.current` is high:

- Check driver connection pool settings.
- Inspect `active`, `activeClients`, and waiting clients.
- Check per-connection memory usage and file descriptor limits.
- Check for pool leaks, retry storms, and connection churn.
- Do not raise `maxIncomingConnections` arbitrarily without sufficient RAM/CPU.

### 8.3. WiredTiger Concurrent Transactions/Tickets

Depending on the version, `serverStatus.wiredTiger.concurrentTransactions` may expose read/write ticket counts:

```javascript
const wt = db.serverStatus().wiredTiger;

printjson(wt?.concurrentTransactions);
```

When available tickets stay persistently low, check workloads holding tickets too long, I/O waits, locks, cache pressure, and admission policies. Some MongoDB versions feature **dynamic ticket management**, so total/available values can vary; do not assume ticket counts are static constants.

Do not manually tune concurrency ticket counts to "add capacity" without first finding why operations are holding tickets for so long.

### 8.4. Locks, Flow Control, and Replication

Write latency can increase due to:

- Lock contention.
- Admission/ticket waits.
- Flow control protecting the replica set when secondaries fall behind.
- Replication lag and write concern.
- Disk journaling/checkpointing.

Read these signals alongside CPU, RAM, and disk. If storage is healthy while write latency rises alongside flow control, increasing WiredTiger cache is not the first step to take.

## 9. Sampling Two WiredTiger Snapshots Instead of One

A **read-only** `mongosh` example taking two `serverStatus` samples 5 seconds apart in the same session:

```javascript
function captureCache() {
  const s = db.serverStatus();
  const c = s.wiredTiger?.cache || {};

  return {
    timeMs: Date.now(),
    uptime: s.uptime,
    max: c["maximum bytes configured"],
    used: c["bytes currently in the cache"],
    dirty: c["tracked dirty bytes in the cache"],
    pagesRead: c["pages read into cache"],
    pagesWritten: c["pages written from cache"],
    appEvictions: c["pages evicted by application threads"]
  };
}

const first = captureCache();
sleep(5000);
const second = captureCache();

function finiteNumber(value) {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function rate(a, b, seconds) {
  const x = finiteNumber(a);
  const y = finiteNumber(b);
  if (x == null || y == null || seconds <= 0 || y < x) {
    return null;
  }
  return (y - x) / seconds;
}

const durationSec =
  (second.timeMs - first.timeMs) / 1000;

const max = finiteNumber(second.max);
const used = finiteNumber(second.used);
const dirty = finiteNumber(second.dirty);

printjson({
  seconds: durationSec,
  sameProcessLikely: second.uptime > first.uptime,
  cacheUsedPct: max > 0 ? 100 * used / max : null,
  dirtyPctOfMax: max > 0 ? 100 * dirty / max : null,
  pageReadsPerSecond:
    rate(first.pagesRead, second.pagesRead, durationSec),
  pageWritesPerSecond:
    rate(first.pagesWritten, second.pagesWritten, durationSec),
  appEvictionsPerSecond:
    rate(first.appEvictions, second.appEvictions, durationSec)
});
```

Notes:

1. `sleep(5000)` pauses **the observing shell**, not MongoDB.
2. This is a demo measurement, not a substitute for a time-series metrics system.
3. If `mongod` restarts between the two samples, counters reset; discard the sample.
4. `sameProcessLikely` is only a preliminary uptime heuristic, **not proof** that both samples belong to the same process; production tools should use process start time or instance identity.
5. For counters exceeding JS safe integer limits, do not trust `Number()` conversion without checking precision; use appropriate telemetry libraries or `BigInt`.
6. If a metric is missing or renamed, report `null` rather than treating it as `0`.
7. Rate values only reflect the measurement instant; maintain baselines for normal and peak hours.

## 10. Disk Space: Logical Size Differs from Physical Size

### 10.1. Three Storage Layers

```text
MongoDB logical documents
          |
          | compression & storage layout
          v
WiredTiger allocated storage
          |
          | data files + indexes + journal + oplog
          v
Filesystem and disk volume
          |
          | snapshots / OS / other files
          v
Physical / provisioned capacity
```

These metrics are not interchangeable.

### 10.2. `dbStats`

Reading statistics on a test database:

```javascript
const lab = db.getSiblingDB("mongo_observe_row352_lab");
const stats = lab.runCommand({ dbStats: 1 });

printjson({
  db: stats.db,
  objects: stats.objects,
  dataSize: stats.dataSize,
  storageSize: stats.storageSize,
  indexSize: stats.indexSize,
  totalSize: stats.totalSize,
  fsUsedSize: stats.fsUsedSize,
  fsTotalSize: stats.fsTotalSize
});
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `dataSize` | Total logical **uncompressed** data size per stats |
| `storageSize` | Storage allocated to collections, **excluding indexes** |
| `indexSize` | Storage allocated to indexes |
| `totalSize` | Database `storageSize + indexSize` |
| `fsUsedSize` | Used filesystem space depending on command/version |
| `fsTotalSize` | Total filesystem space depending on command/version |

`dataSize` can be **larger than `storageSize`** when data compresses well. `storageSize` generally does not shrink immediately when documents are deleted because WiredTiger **reuses allocated space**.

### 10.3. Free Space Within Allocated Storage

Supported in some versions:

```javascript
const st = lab.runCommand({
  dbStats: 1,
  freeStorage: 1
});

printjson({
  storageSize: st.storageSize,
  freeStorageSize: st.freeStorageSize,
  indexSize: st.indexSize,
  indexFreeStorageSize: st.indexFreeStorageSize
});
```

Computing `freeStorageSize` can be expensive on databases with many collections/indexes. **Do not include `freeStorage: 1` unconditionally in high-frequency monitoring**.

### 10.4. Why Deleting 100 GiB May Not Shrink the Filesystem by 100 GiB

`deleteMany`, TTL expiration, or cleanup reduces document count and logical data, yet WiredTiger typically retains allocated file space for reuse.

Thus:

```text
Before delete:
  collection storageSize = 120 GiB

After deleting 80 GiB logical documents:
  dataSize decreases
  storageSize may remain near 120 GiB
  reusable free space increases
```

Do not run `compact`/`repairDatabase` or drop/recreate collections during production hours simply because disk bytes have not decreased. Those operations carry preconditions, I/O cost, and replication/availability impact requiring dedicated DBA procedures.

### 10.5. Do Not Forget Oplog, Journal, Logs, and Backups

A proper capacity calculation must account for:

- Collection data files.
- Index files.
- Journal and checkpoint activity.
- Replication oplog.
- Diagnostic logs and FTDC.
- Temporary files, aggregation spills, and index builds.
- Filesystem overhead.
- Local backups/snapshots if sharing the same volume.
- Headroom for restores, compaction/migrations, or bursts.

Never treat `db.stats().totalSize` as the sole disk space MongoDB needs to run reliably.

## 11. Disk IOPS, Throughput, Latency, and Queue Depth

### 11.1. Four Core Metrics

| Metric | Common unit | Question |
| --- | --- | --- |
| IOPS | operations/s | How many read/write operations is the device handling? |
| Throughput | MiB/s | How much data is read/written per second? |
| Read/write latency | ms/op, p95/p99 if available | How long does each I/O wait? |
| Queue depth | requests waiting/in-flight | Does the device have a backlog? |

A 4 KiB random-read workload can generate high IOPS with low throughput. A sequential backup can produce high throughput with moderate IOPS.

Example:

```text
Workload A:
  20,000 reads/s x 4 KiB ~= 78 MiB/s

Workload B:
  200 reads/s x 1 MiB = 200 MiB/s
```

Both can hit **different types of storage limits**.

### 11.2. Reading `iostat` in Context

On Linux, when `sysstat` is installed:

```bash
iostat -xz 1 5
```

Commonly useful columns (version-dependent):

- `r/s`, `w/s`: operations per second.
- `rkB/s`, `wkB/s`: throughput.
- `r_await`, `w_await`: average I/O latency (ms), including queue wait time.
- `aqu-sz` or `avgqu-sz`: average queue length.
- `%util`: percentage of time I/O is active under the tool/device semantics.

**Do not use `%util=100%` as universal proof that an NVMe or cloud volume has reached maximum capacity**: parallel devices can serve multiple I/Os concurrently; check IOPS, throughput, latency, queue depth, and cloud provider provisioned limits.

### 11.3. Signs of a Disk Bottleneck

Suspect disk saturation when:

- `read/write await` climbs clearly above baseline;
- queue depth remains elevated;
- IOPS/throughput approaches provisioned limits;
- MongoDB page-in/checkpoint/journal times increase;
- API latency rises accordingly;
- CPU stays low or `iowait` increases;
- cloud volumes show declining burst credits or throttling;
- replication lag rises because secondaries cannot apply writes fast enough.

Do not blame every disk wait on insufficient WiredTiger cache; it can stem from backups, snapshots, log rotation, index builds, noisy neighbors, or the storage backend.

### 11.4. p95/p99 Matters More Than Average

An average disk write latency of 3 ms can mask several 200 ms writes. For p99-sensitive APIs, journal, checkpoint, or storage spikes cause tail latency.

Prioritize:

- latency histograms if your storage/observability stack supports them;
- MongoDB read/write p95/p99;
- timeout counts;
- timing of checkpoints and journal pressure;
- correlation with cloud volume metrics.

Do not equate query p99 latency with disk p99 latency; a query may trigger many I/Os or none at all.

## 12. Relationship Between Cache Pressure and Disk Pressure

### 12.1. Working Set Larger Than Cache

The **working set** is the subset of data and indexes frequently accessed over a period.

If the working set is 30 GiB while WiredTiger cache is 8 GiB, the engine continuously replaces pages according to access patterns. Still, the OS filesystem cache may retain compressed data in RAM, so the impact on **physical disk** depends on the workload.

```text
Working set > cache
         |
         v
More cache replacement
         |
         +-- OS page cache hit -> may avoid physical disk read
         |
         +-- OS cache miss -> physical disk read
         |
         v
Query latency changes
```

Do not take `dataSize + indexSize` as the exact working set. A 1 TiB database can run smoothly if only 10 GiB is hot; a 50 GiB database can thrash if random accesses span all data under limited RAM.

### 12.2. When Both Eviction and Disk Are Saturated

Scenario:

```text
Write burst
    |
    v
Dirty pages increase
    |
Disk write latency increases
    |
Eviction cannot keep up
    |
Application threads help eviction / wait
    |
Writes and reads slow down
```

An unverified reaction is **raising WiredTiger cache max**. That might offer a slightly larger short-term buffer, but it:

- steals RAM from the filesystem cache;
- raises RSS and container OOM risk;
- does not increase IOPS or storage bandwidth;
- does not fix long-transaction pinning.

Proper solutions may involve **throttling write bursts, optimizing indexes/queries, upgrading storage, adding RAM properly, or fixing long transactions**, depending on the root cause.

### 12.3. High Cache Occupancy with Healthy Disk

```text
WiredTiger occupancy 94%
Dirty fraction stable
OS available RAM plentiful
Disk read/write latency low
Eviction making good progress
API p95 normal
```

No incident is warranted solely for 94% occupancy. Dashboards should alert on **signal combinations**, not a single static percentage.

## 13. Memory Pressure from the OS and Containers

### 13.1. Important OS Signals

On Linux:

```bash
free -h
vmstat 1 5
cat /proc/meminfo
```

Pay attention to:

- `MemAvailable`.
- `SwapUsed`, swap-in/swap-out activity.
- Major page faults.
- Reclaim/page scanning pressure if exported.
- Memory PSI (`/proc/pressure/memory`) on supported kernels.
- OOM killer logs/restarts.

**Allocated swap space** does not prove active swapping; `si/so` (swap-in/out) activity, memory stalls, and rising latency indicate pressure is actively hurting performance. Databases are highly sensitive to swap thrashing.

### 13.2. Cgroup Memory Limits

In containers/Kubernetes:

```text
Host physical RAM:       64 GiB
Container memory limit:   8 GiB
WiredTiger cache max:     7.0 GiB  (unsuitable config for this container)
Other process memory:     2.0 GiB
Total:                    9.0 GiB  -> OOM risk
```

WiredTiger cache is **not the total RAM limit of `mongod`**, and container memory also counts other allocations/caches under cgroup semantics.

Inspection sources depending on cgroup version:

```bash
# cgroup v2 (if mounted at standard path):
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events

# CPU resources:
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

Do not assume these exact paths exist in every environment; cgroup v1 or managed orchestrators differ. On Kubernetes, check pod memory limits, working set, `OOMKilled`/`restartCount`, and container memory metrics.

### 13.3. `hostInfo()` to Check Limits Seen by MongoDB

```javascript
const info = db.adminCommand({ hostInfo: 1 });

printjson({
  physicalMemMB: info.system?.memSizeMB,
  memoryLimitMB: info.system?.memLimitMB,
  totalCores: info.system?.numCores,
  coresAvailableToProcess:
    info.system?.numCoresAvailableToProcess
});
```

Per MongoDB documentation, `memLimitMB` reflects the memory limit visible to MongoDB, which is especially helpful in containers. Fields may be restricted by deployment type, OS, and privileges; some Atlas tiers do not support `hostInfo`.

**Never draw conclusions solely from host `memSizeMB` when a container enforces a lower memory limit.**

### 13.4. Do Not "Fix" OOM and Restarts by Increasing Cache

If the process was `OOMKilled`:

1. Inspect peak cgroup usage, `memory.events`, and restart history.
2. Compare WiredTiger cache configuration against the container limit.
3. Count connections and co-located processes in the pod.
4. Inspect aggregation spills, in-memory operations, and index builds.
5. Check for memory leaks or allocator growth outside WiredTiger.
6. Review workload changes prior to the incident.
7. Adjust limits/cache/queries per your capacity plan.
8. Review liveness/readiness probes and rollout behavior.

Restarting temporarily lowers RSS/cache, **does not fix the root cause**, cools the cache, spikes disk reads, and disrupts failover and latency.

## 14. Process-Level and Node-Level Measurements

### 14.1. Read-Only OS Commands

Linux:

```bash
# Node CPU/memory overview:
top

# Node memory:
free -h

# CPU + paging summary:
vmstat 1 5

# Storage and queue:
iostat -xz 1 5

# Filesystem capacity:
df -h
df -i
```

If authorized and tools are available:

```bash
# Inspect process memory via ps:
ps -eo pid,comm,%cpu,rss,vsz --sort=-rss

# Per-process stats (sysstat):
pidstat -rud 1 5
```

`pidstat` can produce verbose output; filter for the `mongod` PID in real environments. Never run destructive commands to benchmark "real performance," such as generating tens of GiB of dummy files, dropping collections, or flushing OS caches in production.

### 14.2. Limitations of OS Numbers

- `RSS` can differ from cgroup working set metrics.
- Page cache counts toward "used" memory, yet is reclaimable.
- `iowait` is a Linux scheduler metric, not the exact time individual MongoDB operations waited on disk.
- `df -h` reports filesystem capacity; cloud block volumes may enforce separate burst/IOPS quotas.
- Hypervisor/container isolation complicates direct comparisons.
- On Windows/macOS, use native tools instead of copying Linux commands.

### 14.3. Atlas / Managed Services

When using MongoDB Atlas, prioritize the authorized service dashboards and metrics:

- CPU utilization / normalized CPU.
- Resident memory, system memory.
- WiredTiger cache, dirty/eviction indicators.
- Disk IOPS, throughput, utilization, read/write latency.
- Connection count, queued operations.
- Query execution metrics / slow query view.
- Replication lag and oplog window.
- Storage growth, index builds, maintenance events.

Metric names and calculation scope vary by tier, deployment, and MongoDB version. **Do not assume every field is available on free/shared tiers or across all managed services.**

### 14.4. FTDC and Logs

MongoDB provides **Full-Time Diagnostic Data Capture (FTDC)**, periodically collecting statistics like `serverStatus` for troubleshooting. On self-managed deployments, FTDC is typically enabled by default.

FTDC can contain sensitive system/deployment details, so you should:

- restrict read access to artifacts;
- manage retention and transfer;
- never share them in public repositories;
- preserve timezone, timestamps, and incident context;
- avoid disabling it lightly given its diagnostic value.

Diagnostic logs and slow query logs also help correlate latency, though they may expose namespaces or query shapes. Apply data sensitivity and access-control policies.

## 15. Connecting Metrics to Query Execution

### 15.1. Why Watching CPU/Cache Without Queries Is Incomplete

An unindexed query:

```javascript
db.orders.find({
  customerEmail: "person@example.test"
});
```

Without an appropriate index on `customerEmail`, MongoDB may scan many documents, burning CPU/cache and triggering heavy page reads.

An appropriate index:

```javascript
db.orders.createIndex({
  customerEmail: 1
});
```

can reduce keys/docs examined, CPU, and I/O **if query shape and selectivity fit**. However, adding indexes also increases storage usage and write amplification, so benchmark rather than indexing indiscriminately.

### 15.2. `explain("executionStats")`

On an authorized test collection:

```javascript
db.orders.find({
  customerEmail: "person@example.test"
}).explain("executionStats");
```

Inspect:

| Field / Indicator | Meaning |
| --- | --- |
| `totalDocsExamined` | Number of documents examined |
| `totalKeysExamined` | Number of index keys examined |
| `nReturned` | Number of documents returned |
| `COLLSCAN`/`IXSCAN` or equivalent stages | Whether an index was used |
| `executionTimeMillis` | Duration during `explain` per server semantics |
| Blocking sort/spill indicators | Whether the query adds memory/I/O pressure |

Stage names and output depend on MongoDB version and execution engine. A single `explain` run cannot replace production observability; query plans, data, and cache state differ from live workloads.

### 15.3. Examined/Returned Ratio

Example:

```text
totalDocsExamined = 1,000,000
nReturned = 10
examined/returned = 100,000
```

A high ratio suggests the query scanned extensively to return few documents. However, for aggregations using `$group` or `$count`, `nReturned` reflects pipeline output, so the ratio alone does not prove an index is wrong.

Understand **query semantics** and workload before concluding.

### 15.4. Aggregation Spills

Certain aggregation stages like sort and group consume memory. When limits are exceeded, they may spill to disk depending on version, `allowDiskUse`, and `allowDiskUseByDefault`.

If you observe:

- rising temp disk writes;
- rising query p95;
- rising CPU/memory;
- profiler/diagnostics reporting `usedDisk`/spills;

review the pipeline, sort/filter/indexes, and data bounds. **Allowing spills** lets jobs finish at the cost of disk pressure; **forbidding spills** can cause queries to fail. Neither choice is universally better.

### 15.5. The Profiler Is Not Free

The MongoDB Database Profiler writes detailed operation records to `system.profile`, consuming CPU/disk and adding load. Documentation warns that profiler level 2 (all operations) or overly low slow thresholds introduce significant overhead.

In production:

- prefer existing telemetry, Atlas Query Profiler/Performance Advisor, or `$queryStats` where appropriate;
- if the database profiler is necessary, define scope/time limits and a rollback plan;
- do not blindly turn on level 2 cluster-wide during a CPU/disk incident;
- mind permissions and potential exposure of sensitive metadata.

This lab **does not enable the profiler**.

## 16. Correlating CPU, Cache, Disk, and Workload

### 16.1. Scenario 1 — Rising Cache Misses and Disk Reads

```text
p95 reads: 30 -> 250 ms
WiredTiger page reads/s: 4x increase
Disk reads IOPS: 3x increase
Disk read latency: rising
CPU: 45%
```

Reasonable hypothesis: reduced working set/cache efficiency, large scans, or storage falling behind.

Check:

1. Query/index changes, collection growth, workload access patterns.
2. Repeated collection scans or cold cache after a restart.
3. OS page cache and disk bandwidth.
4. Read preferences or a specific hot secondary.
5. Whether to add RAM, improve indexes, or reduce query fan-out.

Do not raise cache size before verifying disk/working set and actual RAM limits.

### 16.2. Scenario 2 — Dirty Pages and Write Latency Rising Together

```text
Write p95: 20 -> 400 ms
Dirty cache fraction: steadily rising
WT modified page evictions: rising
Disk write await: rising
Write throughput: surging
```

Hypothesis: storage writes, checkpoints, or eviction cannot keep pace with modifications.

Actions:

- Check for bulk imports, index builds, or backups.
- Inspect provisioned IOPS, throughput, and burst credits.
- Throttle non-urgent writes.
- Check for long transactions or locks.
- Consider upgrading storage performance or capacity.

Never disable journaling or downgrade write concern just to make latency charts look cleaner; those are severe durability changes.

### 16.3. Scenario 3 — High CPU, Normal Disk

```text
CPU: 95% sustained
Disk await: stable
WT page read rate: no major change
Query examined/returned ratio: surged
```

Hypothesis: compute-heavy or inefficient query-plan workload.

Inspect query shapes, `explain`, regexes, aggregations, index selection, connection concurrency, and duplicate client requests.

### 16.4. Scenario 4 — High RAM Used Without Pressure

```text
Host RAM used: 94%
MemAvailable: sufficient
Swap in/out: near 0
OOM events: 0
WT cache: near max, stable
API latency: stable
```

No evidence requiring intervention. The OS is likely using RAM effectively for caching.

### 16.5. Scenario 5 — Container OOM Despite Free Host RAM

```text
Host memory available: 60 GiB
Pod limit: 8 GiB
Container memory: hits 8 GiB
Pod OOMKilled: rising
WT configured max: 7 GiB
```

The primary issue is **cgroup memory quota versus total footprint**, not a lack of host RAM. Review cache sizing, resource limits, query memory, and co-located processes in the pod.

### 16.6. Scenario 6 — Secondary Lag, Slow Write Concern

```text
Primary CPU: 40%
Primary disk: normal
Secondary disk: high write latency
Replication lag: rising
Majority write latency: rising
```

Hypothesis: secondary storage/apply cannot keep up, or flow control/replication is throttling writes. Increasing primary CPU/cache will not solve a bottleneck on the secondary.

## 17. Operator-Focused Dashboards

### 17.1. Minimum Dashboard

```text
+-----------------------------+------------------------------+
| API p95 / p99 + error rate  | MongoDB read/write latency   |
+-----------------------------+------------------------------+
| Host/process CPU            | Container CPU throttling     |
+-----------------------------+------------------------------+
| MemAvailable + RSS          | cgroup usage / OOM / swap    |
+-----------------------------+------------------------------+
| WT cache used/max           | WT dirty bytes / max         |
+-----------------------------+------------------------------+
| WT page-in & eviction rates | WT eviction/wait anomalies   |
+-----------------------------+------------------------------+
| Disk IOPS / throughput      | Read/write latency + queue   |
+-----------------------------+------------------------------+
| Disk free space / growth    | Replication lag + tickets    |
+-----------------------------+------------------------------+
| Slow query shapes           | Index build / deployment     |
+-----------------------------+------------------------------+
```

### 17.2. Custom Application Metric Names

Example custom metrics:

```text
mongo_app_request_duration_seconds
mongo_wt_cache_occupancy_ratio
mongo_wt_dirty_fraction
mongo_wt_pages_read_per_second
mongo_wt_app_evictions_per_second
mongo_process_rss_bytes
mongo_container_memory_limit_bytes
mongo_disk_read_latency_seconds
mongo_disk_write_latency_seconds
mongo_disk_queue_depth
mongo_replication_lag_seconds
mongo_oom_events_total
```

These are **suggested names**, not mandatory standard names exported automatically by MongoDB/Prometheus. When using an exporter, check actual metric names and units and ensure counters are properly converted into rates.

### 17.3. Impact-Based Multi-Signal Alerts

**Illustrative examples**, not MongoDB defaults:

| Alert | Conditions to combine | Goal |
| --- | --- | --- |
| CPU saturation | Sustained high CPU/process or throttling **and** rising latency | Catch CPU issues impacting users |
| Memory pressure | Low `MemAvailable` + swap/PSI/OOM or cgroup near limit | Prevent OOM/thrashing |
| WT eviction pressure | Rising eviction waits + cache/dirty pressure + rising p95 | Distinguish healthy full cache from stalls |
| Storage bottleneck | High disk await/queue + throughput near limit + rising DB latency | Detect I/O saturation |
| Disk capacity risk | Low free space + growth rate + projected headroom | Prevent full disks |
| Replication pressure | Rising lag + write concern latency/flow control | Protect availability and durability |
| Monitoring failure | Stale metrics / FTDC / collector failures | Avoid "false green dashboards" |

Avoid alerting solely because WiredTiger cache is 95% full or host RAM is 90% used, as this generates constant false positives.

### 17.4. Headroom Requires Forecasting

Example:

```text
Disk volume:          1,000 GiB
Used:                   800 GiB
Recent growth:           10 GiB/day
Theoretical free:       200 GiB
Time to full:         ~20 days (assuming steady rate)
```

Do not wait until 99% full to react: reserve headroom for oplog, journal, temporary files, index builds, traffic bursts, restores, and failures.

This division is illustrative; real growth may be non-linear. Forecast over multiple horizons and scenarios such as data imports or traffic campaigns.

## 18. Safe Lab: Observing Metrics Without Stressing the Cluster

### 18.1. Prerequisites

- Use an authorized **MongoDB test deployment**.
- Ensure read privileges for `serverStatus`/`hostInfo` if inspecting system-wide stats; some managed tiers restrict them.
- Do not intentionally induce disk pressure, memory leaks, or CPU spikes.
- Do not modify WiredTiger cache, profiler, journal, OS cache, or process resource limits in this lesson.
- Create only a few hundred small documents in a dedicated lab database.
- Never run against `admin`, `local`, `config`, or any production namespace.

### 18.2. Step A — Read-Only Overview via Query

```javascript
const s = db.serverStatus();

printjson({
  uptimeSeconds: s.uptime,
  processMemoryMiB: {
    resident: s.mem?.resident,
    virtual: s.mem?.virtual
  },
  wtCache: {
    used: s.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
    max: s.wiredTiger?.cache?.[
      "maximum bytes configured"
    ],
    dirty: s.wiredTiger?.cache?.[
      "tracked dirty bytes in the cache"
    ]
  },
  totalConnections: s.connections?.current
});
```

If the command returns `Unauthorized`, that reflects environment RBAC restrictions. Do not request full cluster admin rights just to run a lab; use DBA-provided dashboards or an approved `clusterMonitor` account.

### 18.3. Step B — Generate Demo Data Scoped by `runId`

```javascript
const lab = db.getSiblingDB("mongo_observe_row352_lab");
const coll = lab.getCollection("sample_records");
const runId = "row352-" + new ObjectId().toHexString();

const docs = Array.from({ length: 200 }, (_, i) => ({
  _id: new ObjectId(),
  runId,
  seq: i,
  groupKey: "group-" + (i % 10),
  status: i % 2 ? "ACTIVE" : "INACTIVE",
  metric: i * 10,
  payload: "sample-" + i
}));

const inserted = coll.insertMany(docs);

printjson({
  runId,
  insertedCount: Object.keys(inserted.insertedIds).length,
  labCount: coll.countDocuments({ runId })
});
```

This is only 200 small documents, **not a stress test**; CPU, cache, and disk numbers may barely move.

### 18.4. Step C — Create an Index Only on the Lab Collection

```javascript
coll.createIndex(
  { runId: 1, groupKey: 1, seq: 1 },
  { name: "row352_run_group_seq" }
);
```

This index serves a specific query:

```javascript
printjson(
  coll.find({
    runId,
    groupKey: "group-3"
  }).sort({ seq: 1 }).limit(10).toArray()
);
```

Creating an index on a shared collection can add load and alter plans for other workloads. In this lab, the index is isolated to the test collection; if the collection holds data from other runs, confirm ownership/permissions first.

### 18.5. Step D — Inspect `explain`

```javascript
const explanation = coll.find({
  runId,
  groupKey: "group-3"
}).sort({ seq: 1 }).limit(10)
  .explain("executionStats");

printjson({
  nReturned: explanation.executionStats?.nReturned,
  docsExamined:
    explanation.executionStats?.totalDocsExamined,
  keysExamined:
    explanation.executionStats?.totalKeysExamined,
  executionMs:
    explanation.executionStats?.executionTimeMillis
});
```

Note: `explain` output depends on the execution engine and version. Measuring a few hundred documents only demonstrates syntax and metric reading—it cannot predict how much an index will improve production.

### 18.6. Step E — Tiny Before/After Measurement

A measurement snippet:

```javascript
const before = db.serverStatus();

coll.updateMany(
  {
    runId,
    status: "ACTIVE"
  },
  {
    $inc: { metric: 1 }
  }
);

const after = db.serverStatus();

printjson({
  beforeUptime: before.uptime,
  afterUptime: after.uptime,
  beforeCacheBytes:
    before.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
  afterCacheBytes:
    after.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ]
});
```

Modify only documents matching **your run's `runId`**. The `updateMany` demonstrates before/after collection, **not causal attribution** on a system with concurrent workloads; server-wide cache metrics can shift due to other activity.

### 18.7. Step F — Clean Up Data According to Ownership

Before deleting, display IDs and counts:

```javascript
print("database=" + lab.getName());
print("collection=" + coll.getName());
print("runId=" + runId);

const ownedIds = coll.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  count: ownedIds.length,
  ids: ownedIds.map((doc) => doc._id)
});
```

Only after confirming the exact 200 documents belonging to your run:

```javascript
for (const item of ownedIds) {
  coll.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + coll.countDocuments({ runId }));
```

Do not run `deleteMany({})` or `dropDatabase()` on a database that may be shared. The lab index may remain on the collection; remove it only according to test-environment governance and permissions.

## 19. Triage Procedure When Performance Degrades

### 19.1. Step 1 — Confirm User Symptoms

Record:

- Timestamp and time window.
- p95/p99 and error rates.
- Affected request/query types.
- Whether primary or secondary nodes are affected.
- Any deployments, backups, batch imports, index builds, or failovers.
- Whether latency rose across all endpoints or a specific subset.

Do not alter configuration before establishing an adequate baseline for comparison.

### 19.2. Step 2 — Check Resources External to MongoDB

- Process/host CPU and cgroup throttling.
- `MemAvailable`, RSS, swap, OOM events.
- Free disk, read/write await, queue depth, and cloud IOPS/throughput.
- Network saturation or packet errors if applicable.
- Container/VM quotas and limits.

If `mongod` runs in a container, inspect the exact container/pod and individual node, not just host-wide totals.

### 19.3. Step 3 — Inspect `serverStatus` and WiredTiger

- Cache used/max and dirty bytes.
- Pages read into cache/s and application eviction rate.
- Eviction wait/timeout counters.
- Connections and active operations.
- Read/write ticket availability if exposed by your version.
- Checkpoint and journal timings.
- Replication lag and flow control.
- Uptime and restarts.

### 19.4. Step 4 — Identify Queries and Workloads

- Slow query shapes from authorized logs/profiler.
- `explain("executionStats")` on representative queries.
- `totalDocsExamined`/`totalKeysExamined`.
- Blocking sorts, spills, large aggregations.
- Long-running transactions or cursors.
- Bulk writes or index maintenance.
- Connection pool saturation and retry storms.

### 19.5. Step 5 — Fix at the Constraining Layer

```text
CPU/query bound
   -> index / query plan / aggregation / concurrency

Cache/workload bound
   -> working set / indexes / RAM / long transactions

Disk bound
   -> query I/O / storage provision / batch throttling

OS/container memory bound
   -> limits / cache config / outside-cache allocations

Replication bound
   -> secondary / oplog / flow control / network

App pool bound
   -> pool settings / leak / request queue / retry behavior
```

### 19.6. Step 6 — Verify Impact

After every approved change:

- Log the exact change timestamp and version/configuration.
- Compare before/after metrics under comparable traffic or normalized workload.
- Verify p95/p99, error rate, and throughput.
- Monitor across multiple peak cycles if needed.
- Have a rollback ready if metrics worsen.
- Never declare "fixed" based on a single snapshot showing lower CPU.

## 20. Advanced Diagnostic Scenarios

### 20.1. Long-Running Transaction Pinning Cache

```text
Node CPU: 35%
Disk writes: rising
WT dirty bytes: rising
Eviction blocked: rising
Oldest active transaction age: very large
```

This may be a **version retention/pinning** issue rather than merely low RAM. Identify the client holding the long transaction, enforce timeouts/lifecycle controls, and inspect application code.

Do not arbitrarily run `killOp` or abort real customer transactions without verifying impact; doing so can roll back active business workflows.

### 20.2. Full Scans Caused by Collection Growth

```text
Dataset size: 20 -> 200 GiB
Traffic QPS: nearly unchanged
CPU/query latency: rising
Docs examined per query: rising
Disk reads/s: rising
```

Suspect poor query selectivity or missing/suboptimal indexes as the dataset grew. Optimizing queries/indexes is often far more effective than doubling cache size.

### 20.3. "Cold Cache" After Restart

After `mongod` restarts, the internal cache is cold; many queries must load pages from storage. Disk read IOPS spike temporarily, and p95 may climb.

Do not mistake this warm-up phase for a memory leak. Watch uptime, page read rate, and the downward trend as the cache warms. If the cache never stabilizes, examine working set and disk capacity.

### 20.4. Disk and Replication Lag Spike After Import

A bulk import writes data while updating multiple indexes, increasing dirty pages and putting pressure on the journal, checkpoints, and secondaries.

Reduce batch size or throughput, schedule outside peak hours, and monitor replication lag and disk capacity. Do not reflexively raise or lower `w` or disable journaling; business durability and availability contracts must be respected.

### 20.5. Free Disk Drops Rapidly Due to Oplog or Logs

If `dbStats.totalSize` grows slowly while the filesystem fills quickly, inspect **files outside logical database collections**, including oplog, journal, logs, temp files, and backups. Do not delete application collections when the growth lives elsewhere.

Never manually delete `local.oplog.rs`, journal files, or the FTDC directory to reclaim space; doing so can break replication and recoverability.

## 21. Capacity Planning for RAM, CPU, and Storage

### 21.1. Working Set and RAM

Example:

```text
Hot index pages:            5 GiB
Hot document pages:         7 GiB
Estimated hot working set: 12 GiB
Available WT cache:         8 GiB
```

This is an **estimate**. If the workload is random access, you may need more RAM or index/query optimization; if the OS cache holds compressed blocks, performance may still be adequate. Do not assume MongoDB must hold the entire database inside the WiredTiger cache.

Practical approach:

1. Identify query access patterns.
2. Measure cache page-ins/s, eviction, and disk reads.
3. Test on staging with a representative workload.
4. Compare p95/p99 across data sizes, cache sizes, and traffic levels.
5. Account for headroom and failover scenarios.

### 21.2. Capacity During Failover

In a replica set, a newly elected primary must handle all writes during failover. A secondary's cache is not guaranteed to be as warm as the former primary's, and post-election traffic patterns may shift.

Capacity plans must include:

- Write throughput and replication apply overhead.
- Disk/CPU headroom for elections and catch-up.
- Cache warm-up.
- Backup operations.
- Index builds and migrations.
- Traffic bursts from client retries.

### 21.3. Disk Forecast

```text
Current data+index allocated:    500 GiB
Oplog/journal/logs reserve:       80 GiB
Expected growth:                  15 GiB/day
Planned horizon:                  30 days
Growth estimate:                 450 GiB
Extra safety/maintenance reserve: 150 GiB
----------------------------------------
Projected requirement:         ~1180 GiB
```

Numbers are **illustrative**. Compression, TTL expirations, index growth, backup staging, and compaction can change actuals. Forecast from storage trends and growth scenarios rather than a single day's snapshot.

### 21.4. Remember Separate IOPS/Throughput Quotas on Storage

A large 2 TiB volume does not automatically provide enough IOPS for 100,000 random reads/s; cloud storage often separates provisioned IOPS, throughput, and burst limits.

When scaling storage, evaluate:

- capacity;
- random IOPS;
- throughput;
- latency;
- sustained vs. burst performance;
- replication/backup overhead;
- cost.

## 22. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "95% cache used means out of RAM" | Caches are meant to fill; check eviction, I/O, and latency |
| "MongoDB RSS = WiredTiger cache" | RSS includes many allocations outside the cache |
| "VIRT 200 GiB = MongoDB uses 200 GiB RAM" | Virtual address space differs from resident memory |
| "Low Linux free RAM means imminent OOM" | Check `MemAvailable`, cgroups, swap/PSI/OOM |
| "A cache miss is a physical disk read" | OS filesystem cache can satisfy the read |
| "Setting cacheSize to max RAM is fastest" | Can starve OS cache and trigger OOM |
| "Shrinking cache always improves performance" | Can cause excessive page-ins; measure first |
| "Low host CPU means queries aren't CPU-bound" | A single core may be saturated or cgroup-throttled |
| "High `iowait` means CPU is busy computing" | It is OS idle time waiting on I/O |
| "Disk `%util` 100% on NVMe means max IOPS hit" | Check throughput, latency, queue depth, provisioned limits |
| "High IOPS means slow storage" | IOPS can be high while latency remains low |
| "`dataSize` is bytes occupied on disk" | `dataSize` is uncompressed; `storageSize` is allocated storage |
| "Deleting documents immediately frees disk space" | WiredTiger typically reuses allocated space |
| "Dirty pages mean data is not durable" | Journal, write concern, and checkpoints have distinct semantics |
| "Rising eviction counter is an error" | Eviction is normal; watch waits and latency |
| "Rising page reads counter means heavy disk reads" | Counter is cumulative and hits may hit OS cache |
| "Higher counter than another node means worse node" | Convert to rates and account for uptime/restarts |
| "Turn on profiler level 2 to find any root cause" | Carries overhead and data-exposure risks |
| "Raising connection limit lowers latency" | Can raise RAM/contention if pools are uncontrolled |
| "Increasing cache fixes replication lag" | Bottleneck may be on secondary, network, or flow control |
| "Restart reduced RAM so the bug is fixed" | May only mask leaks temporarily while cooling cache |
| "Lower write concern to ease disk pressure" | Can break durability guarantees |
| "Increasing disk size increases IOPS" | Capacity and IOPS/throughput may have separate quotas |
| "One snapshot proves root cause" | Need trends, correlation, and baselines |
| "Containers can use all host RAM" | Cgroup memory limits may be much lower |
| "FTDC/profiler artifacts can be shared publicly" | Contain system/query details; enforce RBAC and retention |

## 23. Self-Practice Exercises

### Exercise A — Distinguishing Cache Occupancy from Memory Pressure

A node shows:

```text
Host RAM used:           92%
MemAvailable:             6 GiB
WiredTiger cache used:   95% of max
Swap in/out:          near 0
Disk read latency:    stable
API p95:              stable
```

1. Is there enough evidence to conclude RAM starvation?
2. Which metrics provide additional evidence?
3. Why could increasing the cache backfire?

### Exercise B — Computing Cache Occupancy

```text
Cache maximum: 8 GiB
Bytes in cache: 6.8 GiB
Tracked dirty: 0.9 GiB
```

1. Calculate occupancy %.
2. Calculate dirty fraction % of cache maximum.
3. Can you conclude eviction is failing from these two ratios alone?
4. Which metrics should you inspect at the same time?

### Exercise C — Computing Page-In Rate

```text
T1: pages read into cache = 100,000,000
T2: pages read into cache = 100,012,000
Time elapsed: 60 sec
```

1. Calculate page reads/s.
2. What happens if MongoDB restarts between T1 and T2?
3. Why does page reads/s not necessarily equal physical disk IOPS?

### Exercise D — Process CPU vs. Host CPU

A MongoDB process uses 100% of one core on a 16-core machine, while overall host CPU is about 7%.

1. Is there a contradiction?
2. Why might adding more cores fail to speed up a serial query?
3. Propose measurements/query-plan checks to find the cause.

### Exercise E — Disk Saturation

```text
Read IOPS:  near volume limit
Read await: jumps 2ms -> 25ms
Queue:      sustained increase
WT page-ins: sharp rise
API p99:    sharp rise
```

1. What is the likely root cause?
2. Could a query or index change trigger this?
3. Why is increasing WiredTiger cache alone insufficient?
4. Which cloud volume quotas should you verify?

### Exercise F — Container OOM

```text
Host RAM:          64 GiB
Pod memory limit:   8 GiB
WT cache max:       7 GiB
mongod RSS:         8.5 GiB
Pod restarts:       OOMKilled
```

1. Why was the pod killed while the host still had RAM?
2. Which allocations live outside the WT cache?
3. Which settings, cache configs, and metrics should you inspect?
4. Why is restarting not a root-cause fix?

### Exercise G — `dbStats`

A database shows:

```text
dataSize:     200 GiB
storageSize:  120 GiB
indexSize:     40 GiB
```

1. Why can `dataSize` exceed `storageSize`?
2. Roughly what is `totalSize` by definition?
3. After deleting many documents, which metric decreases?
4. Which parts of disk usage are not fully reflected here?

### Exercise H — Dirty Pages and Long Transactions

```text
WT dirty bytes: rising
Eviction waits: rising
Disk latency: no significant increase
Oldest active transaction: 30 minutes
```

1. Why can a long transaction impede eviction?
2. Why shouldn't you simply increase cache size?
3. What application code patterns should you investigate?
4. Should you immediately kill the transaction?

### Exercise I — Choosing Dashboards and Alerts

Design a **Memory Pressure** alert without relying solely on RAM used%. Pick at least four metrics and describe:

- how long the condition must persist;
- whether latency/availability should be correlated;
- how to avoid false alarms when filesystem cache grows;
- the first action to take when the alert fires.

### Exercise J — Capacity Planning

A cluster currently uses 500 GiB for data/indexes and grows by 15 GiB/day. Plan for 30 days, accounting for oplog/journal/logs and a safety reserve.

1. Calculate baseline growth.
2. Why shouldn't you just pick a volume of exact size `500 + 15*30`?
3. How should disk capacity, IOPS, and throughput be selected?
4. How do backups and index builds affect headroom?

### Exercise K — Multi-Node Bottleneck Isolation

Primary has 40% CPU and healthy disk; secondary shows high disk write latency, rising replication lag, and rising majority write p95.

1. Should you immediately raise the primary's cache?
2. Which metrics on the secondary should you inspect?
3. Could flow control or write concern be involved?
4. Which signals should you compare after remediation?

### Exercise L — Query Optimization Plan

A query returns 10 documents per call but scans millions of documents, driving up CPU and page reads.

1. Which fields do you read from `explain("executionStats")`?
2. How do you design an index without over-indexing?
3. Why does effectiveness depend on selectivity and sort order?
4. When is staging/canary testing needed?

## 24. Official Reference Documentation

When implementing, always verify against your exact MongoDB server version, deployment topology, exporter, and OS:

- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — cache architecture, filesystem cache, default cache size formula, and compression.
- [Production Notes for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/production-notes/) — memory, cache, and tuning recommendations.
- [`serverStatus` Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — `mem`, `wiredTiger.cache`, connections, opcounters, and checkpoint metrics.
- [`hostInfo` Command](https://www.mongodb.com/docs/manual/reference/command/hostInfo/) — memory limits, CPU cores, and host/container information.
- [`dbStats` Command](https://www.mongodb.com/docs/manual/reference/command/dbStats/) — `dataSize`, `storageSize`, `indexSize`, and filesystem metrics.
- [`db.stats()`](https://www.mongodb.com/docs/manual/reference/method/db.stats/) — helper, scaling, and `freeStorage`.
- [Explain Slow Queries](https://www.mongodb.com/docs/manual/tutorial/explain-slow-queries/) — using explain/profile to locate query bottlenecks.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — slow operation thresholds, overhead, and limits.
- [Full-Time Diagnostic Data Capture (FTDC)](https://www.mongodb.com/docs/manual/administration/full-time-diagnostic-data-capture/) — diagnostic metrics and protecting artifacts.
- [`mongostat`](https://www.mongodb.com/docs/database-tools/mongostat/) — tool for observing MongoDB throughput, cache, and operations.
- [`mongotop`](https://www.mongodb.com/docs/database-tools/mongotop/) — read/write time by collection within supported scope.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — cluster metrics on the managed service.
- [WiredTiger Cache Configuration](https://www.mongodb.com/docs/manual/reference/configuration-options/#storage-wiredTiger.engineConfig.cacheSizeGB) — cache size options and configuration warnings.

**Version note:** WiredTiger statistic names, ticket metrics, FTDC, profiler behavior, and Atlas access vary across MongoDB releases and tiers. Thresholds, ratios, load examples, and SLOs in this lesson are illustrative only, **not fixed guarantees or limits from MongoDB**.

## 25. Conclusion

Proper MongoDB observability requires understanding **CPU, RAM, storage, and WiredTiger cache** together:

- **High CPU** must be analyzed across process/cores, query plans, throttling, and I/O waits.
- **High RAM used** does not automatically mean memory exhaustion; inspect RSS, `MemAvailable`, swap, OOM events, and container limits.
- **WiredTiger internal cache** is a bounded buffer working alongside the **OS filesystem cache**. A nearly full cache is often normal; worry only when eviction, page-ins, dirty bytes, waits, and latency confirm real pressure.
- **Disk** must be evaluated via IOPS, throughput, read/write latency, queue depth, and remaining capacity; logical data size is not physical disk usage.
- **Cumulative counters** must be converted to rates over time, handle restarts, and be compared against baselines.
- **Remediation** must target the true cause—queries/indexes, working set, long transactions, disk performance, container memory, or replication—rather than guessing with cache changes or restarts.

**Core takeaway:** a healthy MongoDB node is not necessarily one with low CPU, RAM, or cache usage. A healthy node is one that **serves its workload within defined latency, availability, and durability bounds**, maintains adequate headroom, and clearly accounts for resource signals from the application down to storage.
