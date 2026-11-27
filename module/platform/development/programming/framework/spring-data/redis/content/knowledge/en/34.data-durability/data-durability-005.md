# Snapshot Costs, AOF Rewrites, and Memory Pressure in Spring Data Redis

Redis is widely known as a low-latency in-memory store. However, when Redis holds data that must survive process or host failures, operators must consider **data durability**. The two familiar persistence mechanisms are **RDB snapshots** and **AOF (Append Only File)**. They write Redis state to disk, while introducing costs in **CPU, memory, disk I/O, latency, restart duration, and storage space**.

In Redis, background RDB snapshotting typically uses `BGSAVE`; background AOF compaction typically uses `BGREWRITEAOF`. Both jobs can rely on **`fork()` and copy-on-write (COW)** on supported operating systems. Redis keeps serving commands in the parent process while the child writes durable data. That avoids freezing the entire server as synchronous snapshots do, yet **does not mean background persistence uses zero extra RAM or leaves latency untouched**.

With Spring Data Redis, developers may never call `BGSAVE` or `BGREWRITEAOF` directly, yet still feel these costs through:

- Elevated latency or timeouts on `GET`, `SET`, `INCR`, and `HSET`.
- Redis containers getting OOM-killed as memory climbs during snapshots or rewrites.
- Write commands rejected when persistence fails or disk fills up, depending on config.
- Longer recovery times after restarts than expected.
- Writes reported to the application as successful before being durably persisted to disk.
- Cache misses and database load spikes when Redis restarts with an incomplete dataset.

This lesson explains the cost mechanics of RDB/AOF, how to read metrics related to fork/COW/RSS, how to choose configurations, how to measure from Spring Data Redis, and how to test memory pressure before deployment.

## 1. Context: Redis is in-memory yet has persistence

A basic Redis command:

```redis
SET order:1001:status PAID
```

mutates data state in Redis memory. **An `OK` reply does not automatically mean the data has been `fsync`ed to storage.** Post-failure durability depends on persistence policies and underlying storage/infrastructure.

Overall model:

```text
Spring Data Redis
    |
    | SET / INCR / HSET / XADD
    v
Redis main process (in-memory dataset)
    |
    +---------------------+
    |                     |
    v                     v
RDB snapshot           AOF logging
    |                     |
    | BGSAVE              | write commands to AOF
    |                     | fsync per policy
    v                     v
RDB file              AOF files
    |                     |
    +----------+----------+
               |
               v
        Restart / recovery
```

RDB and AOF serve different goals:

| Criterion | RDB snapshot | AOF |
|---|---|---|
| Data written to disk | Dataset snapshot at a point in time | Log of state-mutating commands in the corresponding format/method |
| Durability point | Per successful snapshot | Per append and fsync policy |
| Crash data loss | Can lose changes since latest snapshot | Depends on `appendfsync` and failure scenario |
| Major background job | `BGSAVE` | `BGREWRITEAOF` |
| Notable resources | Fork/COW, serialize/compress CPU, disk I/O | Append/fsync, fork/COW on rewrite, disk I/O and file management |
| File size | Typically compact for dataset snapshots | Grows with command count; rewrites compact it |
| Restart | Reads dataset snapshot | Reloads state from AOF components per version/config |
| Impact under heavy writes | COW grows while child runs | Continuous appends + long rewrites and COW |

No approach guarantees absolute **zero data loss** across all hardware, crash, failover, or configuration failures. If your application requires strict durable transactions, define clear RPO/RTO requirements and evaluate an appropriate primary store.

## 2. Distinguishing four categories of "cost"

When you hear "Redis snapshots consume memory", do not look at a single RAM metric. There are at least four cost categories:

1. **Fork-time latency:** the parent process may pause briefly to spawn the child process and set up memory-management structures.
2. **COW memory:** memory pages modified while the child still references the old snapshot require separate physical copies.
3. **Background CPU and disk I/O:** the child traverses, serializes, compresses, or writes large files, competing for resources with Redis and co-located apps.
4. **Continuous AOF overhead:** appending, writeback, and `fsync` at various points can raise disk latency even outside rewrites.

Additional factors include:

- Redis allocator overhead, client buffers, and replication buffers.
- OS page cache for files being written or read.
- Time required to load persistence files on Redis startup.
- Extra disk space needed to hold old and new files side by side during rewrites/snapshots.
- Queued requests and connections when Redis's event loop slows down.

Capacity planning or migration measurements that record only `used_memory` before/after `BGSAVE` are **insufficient** to prove memory safety.

## 3. How does `BGSAVE` create an RDB snapshot?

`BGSAVE` instructs Redis to create a snapshot in the background. On platforms where Redis uses `fork()`, the flow is typically:

```text
Redis parent
    |
    | BGSAVE requested
    v
fork()
    |
    +--> Parent keeps serving GET/SET/INCR
    |
    +--> Child sees memory state at fork moment
             |
             | serialize dataset to RDB
             | optionally compress and write to disk
             v
        Temporary RDB file
             |
             | finish, replace snapshot file per Redis mechanics
             v
        New RDB snapshot
```

The data seen by the child reflects the state at snapshot start time. Subsequent writes handled by the parent modify parent memory; they **are not automatically added to the active RDB snapshot**.

### 3.1. Why not use `SAVE` in normal operations?

Redis provides:

```redis
SAVE
```

to create a snapshot synchronously. While it runs, the server can be blocked from processing normal commands until the save completes.

The command:

```redis
BGSAVE
```

lets Redis continue serving most traffic while the child writes the snapshot. Still, `BGSAVE` **is not completely free**: fork, COW, and I/O contention remain.

In low-latency applications, prefer appropriate background persistence and trigger rules rather than issuing `SAVE` per request. Never put `SAVE` into a Spring Boot endpoint just to "guarantee data is saved".

### 3.2. What a snapshot excludes

Suppose:

```text
12:00:00  BGSAVE fork succeeds
12:00:02  SET order:1002:status PAID
12:00:08  Child finishes writing RDB snapshot
12:00:10  Redis crashes
```

The RDB snapshot started at `12:00:00` does not automatically include the `12:00:02` mutation. Without other persistence protecting that change, a command that returned success can vanish on restart.

**Snapshot completion time is not when the snapshot's data was "captured".** The snapshot represents state at start time.

## 4. `fork()` and copy-on-write: the main source of RAM pressure

When Redis forks a child for RDB or AOF rewrite, OS copy-on-write allows parent and child **to initially share the same physical memory pages**.

```text
Immediately after fork:

Parent page table ----+
                      +-- physical page P (old value)
Child page table -----+
```

If the parent mutates data residing in a page the child still reads for the older snapshot, the OS allocates a new physical page for the parent:

```text
After parent writes:

Child page table ----------> physical page P (old value)
Parent page table ---------> physical page P' (new value)
```

Physical memory increases because both **the old copy** and **the new copy** coexist until the child no longer needs the old page.

### 4.1. COW operates per memory page, not per payload byte

Suppose the OS uses 4 KiB pages for a memory region. A `SET` modifying just a few bytes inside a data structure can trigger **one or more pages** to be copied, because surrounding metadata and allocator structures also change.

Purely illustrative example:

```text
Child holds old 4096-byte page
Parent alters 10 bytes on that page
COW may require an additional 4096-byte page
```

That does not mean every `SET` always costs exactly 4 KiB of COW. Subsequent writes may touch already-copied pages, many Redis objects can share a page, allocators add overhead, and allocations/frees can touch multiple pages.

**COW volume depends on which pages are actually dirtied while the child lives**, not linearly on the byte length of modified Redis values.

### 4.2. Write patterns that inflate COW

COW is especially concerning when:

- The dataset is already large.
- The child takes a long time to write the file.
- The parent sustains a high write rate.
- The workload modifies **many scattered memory regions**, rather than a few fixed hot keys.
- There are heavy Hash/Set/List/ZSet updates, allocations, or frees.
- Memory is fragmented or allocator structures cause wide page touches.
- The host or container runs close to its RAM limit.

A fast snapshot releases the child quickly; a prolonged snapshot under continuous writes gives many pages a chance to be dirtied, driving up memory pressure.

### 4.3. There is no rule saying "BGSAVE always needs double RAM"

In worst-case scenarios, added memory can rival the dataset size when most pages are modified, yet claiming "BGSAVE always doubles total RAM" is inaccurate.

Example with a multi-GiB dataset:

| Workload while child runs | COW trend |
|---|---|
| Mostly `GET`, minimal writes | Often far smaller than the dataset |
| Repeated writes to a few small keys | Growth concentrated on touched pages and related overhead |
| Updates across many scattered keys | Can rise significantly |
| Heavy writes/deletes/allocations while disk is slow | Can become very high |
| Child finishes quickly | Short window for COW accumulation |
| Child stalls due to I/O bottleneck | Extended window for COW accumulation |

Capacity planning should rely on **measured memory peaks under production-like load** with safety headroom, rather than applying a single multiplier to every deployment.

## 5. Distinguishing `used_memory`, RSS, COW, and container limits

Redis and the OS report distinct memory figures:

```text
Redis logical allocations / allocator
    |
    v
used_memory
    |
    +-- allocator fragmentation / retained pages
    +-- process memory not represented by dataset alone
    |
    v
used_memory_rss (Redis process RSS)
    |
    +-- during fork:
        memory pages may be shared or COW
    |
    v
OS / container memory accounting
    |
    +-- Redis parent + child + OS page cache + buffers + other runtime overhead
```

Avoid simplistic conclusions such as:

```text
used_memory < maxmemory
=> container definitely cannot OOM
```

That conclusion is **false** because `maxmemory` and container memory limits neither measure nor govern the exact same resource boundary.

### 5.1. Key Redis metrics to watch

```redis
INFO memory
INFO persistence
INFO stats
```

Common fields in `INFO memory`:

| Field | Operational meaning |
|---|---|
| `used_memory` | Memory accounted by Redis's allocator |
| `used_memory_human` | Human-readable form of `used_memory` |
| `used_memory_rss` | Redis process RSS as seen by the OS |
| `used_memory_peak` | Peak allocation recorded by Redis |
| `maxmemory` | Eviction/write-limit threshold per Redis policy |
| `mem_fragmentation_ratio` | Indicator of divergence between RAM/RSS figures; read in context |
| `allocator_allocated` | Memory allocator reports as allocated to Redis |
| `allocator_active` | Memory in active allocator pages |
| `allocator_resident` | Resident allocator memory, depending on allocator/version |
| `mem_not_counted_for_evict` | Overhead memory excluded from eviction checks |

Field names and availability vary across Redis versions and allocators. Not every deployment reports every field.

### 5.2. RSS is not total container memory usage

`used_memory_rss` typically reflects the RSS of the **Redis parent process**. While a forked child runs, the OS tracks shared pages and COW pages. Container/cgroup accounting can also include other memory categories, such as file page cache.

Therefore:

- Never mechanically add parent RSS + child RSS as if every shared page were duplicated in physical RAM.
- Never inspect only parent RSS and assume the container faces no OOM risk.
- Monitor **cgroup/container working set or `memory.current`**, OOM events, page cache, and all processes inside the container.
- If Redis shares a host with other processes, monitor host-wide memory pressure.

In Kubernetes, pod/container memory limits and OOM killer behavior can terminate the process even when Redis remains below `maxmemory`.

## 6. Illustrating memory peaks during a snapshot

Suppose a system has:

```text
Initial Redis used_memory:      6.0 GiB
Initial Redis parent RSS:       7.0 GiB
Container memory limit:         9.0 GiB
```

Snapshotting starts and the child runs for many seconds. Meanwhile, the workload mutates substantial data, generating COW and I/O page cache. Container memory can spike past 9 GiB even though:

```text
Redis used_memory ≈ 6.0 GiB
Redis maxmemory   = 7.0 GiB
```

As a result, the container risks being OOM-killed.

**All numbers are illustrative**, not a formula for how many GiB a 6 GiB dataset needs. Always measure actual RSS/cgroup peaks and COW under your real workload.

### 6.1. Mental budget for capacity planning

Do not rely on a rigid formula like `maxmemory + 10% = enough`. Instead, budget by components:

```text
Host/container memory budget
    >= Redis parent resident memory
     + new memory created by COW
     + realistic OS buffers / file cache
     + client/replication/persistence buffers
     + other processes and operational headroom
```

Components can overlap in OS accounting. This is an **inventory checklist**, not a literal sum of potentially shared RSS values.

Effective practice:

1. Measure steady-state memory at target data volume.
2. Trigger `BGSAVE` or a rewrite while generating write traffic.
3. Observe **cgroup/host** peak memory, not just `used_memory`.
4. Repeat near projected capacity limits and under busy disk conditions.
5. Set Redis `maxmemory` and container limits with adequate headroom.
6. Confirm zero OOM events and latencies within SLO.

## 7. Fork-time cost and Redis latency

`fork()` must create the child process context, including address-space/page-table management per OS mechanics. The larger the dataset/address space, the more noticeable the fork pause can become.

Before the child even writes many bytes to disk, Redis can experience **fork latency**.

Useful metric:

```redis
INFO stats
```

Look for a field such as:

```text
latest_fork_usec:...
```

This reports the duration of the most recent fork in **microseconds**, when supported by the Redis version.

If `latest_fork_usec = 120000`, that is roughly 120 ms. The number illustrates unit conversion, not a measurement from any specific system.

### 7.1. Why does fork latency affect Java APIs?

Suppose an endpoint reads Redis:

```java
String value = redis.opsForValue().get("cache:product:42");
```

If Redis pauses during a fork right when the request arrives, the command waits, driving up application latency. A trivial Redis command becomes slow due to **system scheduling/fork pause**.

To diagnose root causes, correlate:

- API/WebFlux p95/p99 latency.
- Client-side Redis command latency.
- `latest_fork_usec`.
- Timestamps of `rdb_bgsave_in_progress` or `aof_rewrite_in_progress`.
- CPU saturation and host memory pressure.

Never conclude from a single sample request; inspect timelines and repeated runs.

### 7.2. Transparent Huge Pages and OS behavior

On Linux, Transparent Huge Pages (THP) can alter COW and fork behavior compared to small pages. Redis traditionally recommends reviewing/disabling THP for low-latency workloads to avoid unexpected COW amplification and memory spikes in certain environments.

However, THP management depends on kernel, Redis version, allocator, distro, and system policy. It is a **host-level configuration change** requiring testing and approval, not something a Java app modifies.

Inspect host configuration in authorized environments, rather than blindly applying sysctl/THP commands to production from generic snippets.

## 8. CPU and disk I/O costs when creating RDB

After fork, the child must:

1. Traverse data structures included in the snapshot.
2. Serialize them into RDB format.
3. Apply compression if configured.
4. Compute/write metadata and checksums per config and version.
5. Write a temporary file and atomically swap the snapshot file.

With large datasets, the child consumes CPU and writes substantial data to disk. **Although the parent continues serving Redis commands, both processes compete for CPU, memory bandwidth, and disk resources.**

Qualitative view:

```text
Without BGSAVE:
  Redis parent CPU  -> command execution
  Disk              -> background load

During BGSAVE:
  Redis parent CPU  -> command execution
  Redis child CPU   -> RDB serialization/compression
  Disk              -> large snapshot write
  Parent memory     -> potential COW growth
```

If Redis shares a disk with databases, logs, or other backup jobs, I/O contention can impact **systems beyond Redis**.

### 8.1. Compression and file size

RDB configs often include compression and checksum options:

```conf
rdbcompression yes
rdbchecksum yes
```

Compression shrinks file size at the expense of CPU. For already compressed or random data, space savings may be minimal. Never disable compression or integrity checks merely to boost a benchmark if it alters safety or diverges from production.

### 8.2. On-disk file and completion timing

Snapshots are normally written to a temporary file and moved into place per Redis rules. When disk is slow, full, or unwritable, snapshotting fails.

Distinguish:

- `BGSAVE` was accepted.
- Child is running.
- Child finished writing the file.
- Redis reports `rdb_last_bgsave_status:ok`.

Receiving an OK from `BGSAVE` alone does not prove the snapshot completed cleanly.

## 9. Configuring when Redis creates an RDB snapshot

Redis supports trigger conditions based on **time intervals and mutation counts**.

Illustrative config:

```conf
save 900 1
save 300 10
save 60 10000
```

Concept:

- Within 900 seconds, if at least one change occurs per Redis tracking, a snapshot may trigger.
- Within 300 seconds, if at least 10 changes occur, a snapshot may trigger.
- Within 60 seconds, if enough changes match the rule, a snapshot may trigger.

These are **trigger conditions**, not a guarantee that "every write is durable within 60 seconds". Snapshots take time to run and can fail or be delayed.

### 9.1. Disabling automatic snapshots when relying on AOF

For example:

```conf
save ""
```

typically disables automatic RDB snapshot rules where appropriate. However:

- This does not mean Redis never generates RDB-formatted data: certain rewrite or replication flows may use RDB representations depending on version and config.
- It does not disable all background forks.
- If AOF is off and no other persistence exists, data cannot be recovered after a crash/restart.

Disabling RDB must pair with AOF, backup, replication, and restore-testing strategies.

### 9.2. `stop-writes-on-bgsave-error`

A common setting:

```conf
stop-writes-on-bgsave-error yes
```

When RDB persistence is configured and snapshotting fails under Redis's rules, the server can **reject data-mutating commands** rather than continuing to accept writes without meeting persistence expectations.

This alerts operators instead of letting the server run silently for hours with broken snapshots, though applications will see write failures.

Never "fix" this by blindly turning the option off. First determine why snapshots failed: full disk, permissions, OOM, fork failure, or unresponsive storage.

## 10. AOF: write commands and the `appendfsync` policy

AOF logs state-mutating operations so Redis can rebuild data on startup. The **`appendfsync`** setting determines how Redis asks the OS to flush writes to storage.

Example:

```conf
appendonly yes
appendfsync everysec
```

Three common modes:

| Mode | Meaning | Trade-off |
|---|---|---|
| `appendfsync always` | Requests fsync per write/batch per Redis mechanics | Stronger durability effort, higher I/O and latency cost |
| `appendfsync everysec` | Typically requests fsync about once per second | Balances performance with risk of losing recent writes |
| `appendfsync no` | Leaves flush timing to the OS | Potentially higher throughput, less predictable un-persisted window |

Never treat `everysec` as an **absolute promise to lose at most 1,000 ms**. Disk stalls, schedulers, OS behavior, or system crashes can alter how much data is at risk.

### 10.1. Appending to a file vs. fsync

A file write can succeed at the OS page-cache level while data is not yet safe across power loss. `fsync` instructs the OS/storage stack to synchronize data per supported protocols, though real guarantees still depend on filesystems, drivers, storage caches, and hardware.

Model:

```text
Redis command accepted
        |
        v
Redis in-memory dataset updated
        |
        v
AOF data appended / queued for write
        |
        v
OS page cache
        |
        | fsync per configuration
        v
Persistent storage
```

These steps **do not necessarily finish simultaneously** with the client response.

### 10.2. Cost of `appendfsync always`

Under workloads with many small writes, frequent fsyncs can:

- Increase disk I/O operations.
- Raise write latency and tail latency.
- Cap write throughput if storage cannot keep up.
- Contend with RDB snapshots, AOF rewrites, and other jobs.

Do not pick `always` solely because the name sounds safer. Prove the application and storage meet SLOs, and recognize it still does not replace replication, backups, or globally durable transactional databases.

### 10.3. Cost of `appendfsync everysec`

`everysec` is a common balanced choice. Yet when disk is overloaded:

- Fsync can lag behind.
- Redis may log AOF fsync warnings.
- Latency spikes and I/O backlogs can appear.
- A crash can lose writes that had not yet been durably flushed.

Therefore, monitor `aof_delayed_fsync` and AOF health rather than blindly trusting `appendfsync everysec`.

## 11. Why does AOF need rewriting?

If every update is appended endlessly to AOF, the file grows with operation count rather than current dataset size.

Example:

```redis
SET counter 1
SET counter 2
SET counter 3
SET counter 4
...
SET counter 100000
```

The final state of `counter` is just `100000`, yet the log retains the full update history. AOF rewrite creates a more compact representation to restore the **current state** without preserving superseded mutations.

```text
AOF before rewrite:
  SET counter 1
  SET counter 2
  ...
  SET counter 100000

New AOF after rewrite (conceptual):
  SET counter 100000
```

Depending on data types and Redis version, the actual representation may use multiple commands or an RDB-encoded base preamble. Never expect rewritten AOF files to be plain `SET` text lines.

### 11.1. `BGREWRITEAOF` is not "in-place file compression"

Redis uses a background process to build a fresh representation from dataset state while the parent continues serving commands. Redis must also preserve new writes arriving during the rewrite.

Rewriting therefore costs:

- Fork and copy-on-write similar to RDB background saves.
- CPU to construct the new representation.
- Disk I/O to write the new files.
- Temporary disk space while old and new files coexist.
- Managing incremental changes arriving during the rewrite.
- Finalization / switching active AOF files.

It is far more than running `gzip` over an existing AOF file.

## 12. AOF rewrite in Redis 7+: multi-part AOF

Redis 7 and later use **multi-part AOF** with separate components and a manifest, instead of relying solely on a single monolithic AOF file as in older versions.

Conceptual layout:

```text
AOF directory
   |
   +-- base AOF (baseline state representation)
   +-- incremental AOF (changes after baseline)
   +-- manifest (describes files belonging to valid AOF set)
```

During a rewrite:

```text
Parent keeps processing commands
    |
    +--> appends new mutations to incremental AOF
    |
    +--> Forks child to build new base AOF
              |
              v
       New base AOF file
              |
              v
       Update manifest / switch valid file set
              |
              v
       Clean up old files per Redis mechanics
```

Actual filenames and manifest rules depend on Redis version and configuration. Never write operational scripts assuming a fixed filename like `appendonly.aof` without checking the actual multi-part AOF layout.

### 12.1. Differences from older versions

In Redis versions prior to multi-part AOF, rewrites could use an **in-memory rewrite buffer** to capture writes occurring while the child built the new AOF. That buffer could grow with write load and become a major source of memory pressure.

With multi-part AOF, ongoing changes are appended into incremental AOF files under the new mechanism, changing buffer usage and finalization. Still, **fork/COW, disk I/O, and file growth remain**. Never assume upgrading to Redis 7 eliminates memory pressure from rewrites.

When reading docs, metrics, or runbooks mentioning `aof_rewrite_buffer_length`, verify which Redis version they describe; do not blindly apply Redis 6 behavior to Redis 7+.

### 12.2. `aof-use-rdb-preamble`

A setting you may encounter:

```conf
aof-use-rdb-preamble yes
```

When supported and enabled, the **base AOF** can use an RDB representation for faster reloading, while incremental AOF continues appending mutations.

This explains why AOF files **are not necessarily plain-text Redis command logs**. Never open the file and manually delete "a couple of bad lines" based on single-file text habits; file repair requires proper tooling, version alignment, and backups.

## 13. Automatic triggers and AOF rewrite thresholds

Redis supports automatic rewrites based on AOF size growth over the previous base/rewrite.

Example:

```conf
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

Concept: once AOF exceeds the minimum size and grows by the configured percentage over its baseline, Redis may trigger a background rewrite when conditions allow.

These values are **common examples**, not fixed recommendations for all datasets. High-write workloads on a stable set of keys grow AOF very differently from workloads constantly inserting new keys.

If rewrites trigger too frequently:

- Forks and COW occur more often.
- Disk repeatedly rewrites base files.
- Repeated latency and memory spikes can occur.

If rewrites trigger too rarely:

- AOF grows very large.
- More disk space is consumed.
- Restart/load times grow depending on files and structure.
- An eventual rewrite can become very heavy.

### 13.1. Checking AOF size and status

```redis
INFO persistence
```

Fields commonly inspected:

```text
aof_enabled
aof_rewrite_in_progress
aof_rewrite_scheduled
aof_last_rewrite_time_sec
aof_last_bgrewrite_status
aof_current_size
aof_base_size
aof_last_cow_size
aof_delayed_fsync
```

Field presence and exact meanings depend on Redis version. When plotting dashboards, note the version and use each field's true units.

For example, `aof_current_size` growing rapidly while `aof_base_size` stays flat shows the log expanding above baseline. Yet **do not conclude rewrites are failing** without checking triggers, `in_progress`/`scheduled` flags, and current config.

## 14. COW during AOF rewrite can contend with RDB snapshots

Both `BGSAVE` and `BGREWRITEAOF` are resource-intensive background persistence jobs. Redis coordinates scheduling to avoid unsafe overlap between certain background fork jobs, yet that **does not prevent persistence load from exerting continuous pressure**.

An operational sequence might look like:

```text
t0: BGSAVE starts
t1: heavy write workload -> COW rises
t2: BGSAVE finishes
t3: AOF rewrite starts or resumes per schedule
t4: heavy write workload -> COW and disk I/O climb again
t5: rewrite finishes
```

When both RDB and AOF are enabled, inspect **background job windows across the entire cycle**, not just one isolated snapshot.

### 14.1. Replication full resyncs also trigger background work

A reconnecting or newly added replica may require full resynchronization. Depending on Redis configuration and version, Redis may generate an RDB for replication, incurring fork/COW/CPU/I/O or corresponding transfer overhead.

Therefore, seeing a background save does not always mean an automatic `save` rule fired. When investigating, capture both:

```redis
INFO replication
INFO persistence
```

to distinguish replication syncs from persistence snapshots.

### 14.2. Impact of slow disks

If the child writes slowly due to low disk throughput:

1. The child stays alive longer.
2. The parent keeps modifying more memory pages during that period.
3. COW rises further.
4. File I/O and page cache continue building pressure.
5. Peak memory grows even though business write rates stay constant.

This is an **indirect link between disk throughput and peak RAM**. Investing in faster storage shortens background jobs and shrinks the COW window.

## 15. `no-appendfsync-on-rewrite`: trading durability risk for latency

Redis provides:

```conf
no-appendfsync-on-rewrite no
```

When enabled in supported versions/environments, Redis can skip certain AOF fsync calls while background RDB/AOF rewrites run, reducing I/O contention.

**Trade-off:** new AOF writes may miss normal fsync intervals, **widening the window of potential write loss if the server fails**. Never turn this on solely for prettier p99 benchmarks without assessing RPO.

Base the choice on:

- Whether storage has enough IOPS/fsync throughput.
- Actual rewrite durations.
- Application tolerance for data loss.
- p95/p99 latency targets.
- Backup, replication, and restore capabilities.

Changing a single persistence flag alters data guarantees, not just speed.

## 16. Typical Redis persistence profiles

The snippets below are **comparison examples**, not complete production configs. Production still needs ACL/TLS, logging, directory settings, file permissions, replication, memory policies, and backups.

### 16.1. RDB-focused

```conf
appendonly no

save 900 1
save 300 10
save 60 10000

rdbcompression yes
rdbchecksum yes
stop-writes-on-bgsave-error yes
```

Pros:

- Snapshots are usually compact and convenient for backups.
- Can restart quickly with an appropriate snapshot.
- No continuous AOF append/fsync overhead.

Trade-offs:

- Can lose changes since the latest snapshot on crash.
- `BGSAVE` still uses fork/COW and disk I/O.
- If snapshots fail, writes may be rejected per policy.
- Unsuitable if the application needs very small RPO without additional safeguards.

### 16.2. AOF-focused

```conf
appendonly yes
appendfsync everysec

save ""

auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-use-rdb-preamble yes
```

Pros:

- Append-log model typically yields tighter RPO than standard RDB-only setups.
- Data is reconstructed from valid AOF components.
- Rewrites curb unbounded log growth compared to keeping full history forever.

Trade-offs:

- Ongoing append/fsync overhead.
- Rewrites still incur fork/COW and disk cost.
- Must manage version-specific AOF components and manifests.
- `everysec` does not guarantee at most one second lost across all failures.

### 16.3. Combined RDB and AOF

```conf
appendonly yes
appendfsync everysec

save 900 1
save 300 10
save 60 10000
```

This combines snapshots with AOF. Measure:

- Disk contention levels.
- Frequency of both background job types.
- Periodic fork/COW memory peaks.
- Actual recovery behavior from persistence files.
- Backup/restore workflows.

When both exist, Redis's startup source selection depends on config and version; AOF is typically prioritized when enabled because it may hold more recent changes than RDB. Test this explicitly rather than guessing from filenames.

### 16.4. Pure rebuildable cache

A Redis holding exclusively cache that can be rebuilt completely from a database may intentionally disable persistence in some architectures:

```conf
appendonly no
save ""
```

However, **this is not the default choice** for required sessions, queues, sensitive tokens, or business state lacking another source.

Account for:

- Post-restart cold caches triggering cache stampedes and DB load surges.
- Redis failover changing cached state.
- Whether every key in Redis is genuinely rebuildable.
- Whether TTLs, invalidation, and eviction policies fit.

Never turn off durability merely because Redis is called a "cache" if the system relies on it as a data store.

## 17. Relationship between `maxmemory`, eviction, and persistence

Redis may be configured with:

```conf
maxmemory 6gb
maxmemory-policy allkeys-lru
```

`maxmemory` caps Redis logical memory usage alongside an eviction policy when needed. Yet persistence also involves:

- Parent/child COW pages.
- Client output buffers.
- Replication buffers.
- AOF overhead and page cache.
- Memory fragmentation.
- Container/cgroup memory accounting.

Therefore:

```text
maxmemory = 6 GiB
container memory limit = 6 GiB
```

**is not safe** just because the two numbers match. Redis needs RAM above `maxmemory` for persistence and auxiliary tasks.

### 17.1. `noeviction` and business data

If the policy is:

```conf
maxmemory-policy noeviction
```

Redis can reject memory-growing commands once full rather than evicting keys. For business state, this prevents silent data eviction while turning memory exhaustion into **write errors**.

Choose `maxmemory-policy` per data semantics:

- Rebuildable cache: can tolerate eviction.
- Streams/queues or business state: must not be arbitrarily evicted under memory pressure.
- Mixed workloads: co-locating caches and critical state complicates policy choice; consider separate instances.

### 17.2. Eviction does not cure every COW spike

Even when Redis evicts keys to keep `used_memory` below `maxmemory`, deleting or updating structures modifies pages and **can generate additional COW** while a child holds an old snapshot.

Thus, eviction during memory pressure does not immediately shrink OS RSS. If the allocator retains pages or a child still references old pages, the container remains exposed to OOM.

This is another reason to measure host/container memory rather than trusting Redis's `maxmemory` cap alone.

## 18. Impact on Spring Data Redis: latency and timeouts

Spring Boot apps commonly use:

```java
StringRedisTemplate redis;
```

with configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

When Redis background persistence stresses CPU, disk, or fork latency, Java operations can see latency spikes or exceptions such as:

```text
RedisConnectionFailureException
RedisCommandTimeoutException
RedisSystemException
```

Exception types are translated by Spring Data Redis from the underlying driver per version and cause; do not assume every timeout comes from `BGSAVE`/AOF rewrite.

### 18.1. Why command timeouts do not alter durability

Suppose:

```java
redis.opsForValue().increment("metrics:orders");
```

Redis may have executed `INCR`, while the reply missed the client deadline due to network or system stalls. If Spring Data Redis throws a timeout:

- The application **cannot assume `INCR` did not run**.
- Non-idempotent retries can increment twice.
- Persistence follows Redis server policy, not Java's client timeout.
- Switching to `ReactiveRedisTemplate` does not turn commands into durable transactions.

Distinguish **client request outcome**, **Redis in-memory update**, **AOF/RDB durability**, and **replica receipt**.

### 18.2. Do not invoke `BGSAVE` or rewrites from HTTP requests

An anti-pattern:

```java
@PostMapping("/orders")
public ResponseEntity<?> saveOrder(...) {
    storeOrder(...);
    redis.execute(connection -> {
        // call BGSAVE after every request?
        return null;
    });
    return ResponseEntity.ok().build();
}
```

Calling persistence commands per request is not a way to commit individual operations durably. It causes nonstop background jobs, contention, and scheduling errors.

RDB/AOF belongs to Redis server configuration. Business apps should invoke normal commands and design holistic durability strategies rather than turning endpoints into snapshot triggers.

## 19. Measuring real latency from Spring Data Redis

You can use Micrometer to measure **operation duration from the application's perspective**. Illustrative service:

```java
package com.example.orders;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusCache {

    private final StringRedisTemplate redis;
    private final Timer writeTimer;
    private final Timer readTimer;

    public OrderStatusCache(
            StringRedisTemplate redis,
            MeterRegistry meterRegistry
    ) {
        this.redis = redis;

        this.writeTimer = Timer.builder("redis.order_status.write")
                .description("Redis SET duration from application")
                .register(meterRegistry);

        this.readTimer = Timer.builder("redis.order_status.read")
                .description("Redis GET duration from application")
                .register(meterRegistry);
    }

    public void put(String orderId, String status) {
        String key = "cache:order:status:" + orderId;

        writeTimer.record(() ->
            redis.opsForValue().set(
                key,
                status,
                Duration.ofMinutes(5)
            )
        );
    }

    public String get(String orderId) {
        String key = "cache:order:status:" + orderId;

        return readTimer.record(
            () -> redis.opsForValue().get(key)
        );
    }
}
```

This example uses standard Micrometer and Spring Data Redis APIs; real applications need Micrometer/Actuator dependencies and a configured metrics registry.

`Timer` here measures **end-to-end duration** from the app, spanning:

```text
Client / connection management
+ serialization
+ network
+ Redis server wait + execution
+ response
+ deserialization
```

Not just Redis server CPU time for the command.

### 19.1. Measure p95/p99 instead of averages alone

During `BGSAVE` or rewrites, most commands may remain fast while a subset hitting fork/fsync contention slows dramatically.

Measure:

- p50/p95/p99 latency split by GET/SET operations.
- Throughput and error/timeout counts.
- Redis `latest_fork_usec`.
- COW peak and background job duration.
- Disk IOPS, fsync latency, utilization/queue depth.
- Host/container CPU.
- Cgroup memory peak and OOM events.

A few average benchmark numbers cannot confirm SLO compliance under production load.

### 19.2. Avoid high-cardinality metrics

Never use individual `orderId` or Redis keys as metric tags, as each unique key generates a new time series.

Good tags:

```text
operation = get|set
result = success|timeout|error
workload = cache|counter|stream
```

Bad tags:

```text
key = cache:order:status:100000001
key = cache:order:status:100000002
...
```

When tracing a specific request, use a correlation ID in controlled logs, not metric labels.

## 20. Using `INFO persistence` to monitor background saves/rewrites

First command to inspect:

```redis
INFO persistence
```

Useful fields:

| Field | How to understand it |
|---|---|
| `rdb_bgsave_in_progress` | Whether `BGSAVE` is currently running |
| `rdb_last_save_time` | Timestamp of last successful snapshot as recorded by Redis |
| `rdb_last_bgsave_status` | Result of latest background save |
| `rdb_last_bgsave_time_sec` | Duration of latest `BGSAVE` job |
| `rdb_current_bgsave_time_sec` | Elapsed duration of active `BGSAVE` |
| `rdb_changes_since_last_save` | Mutations counted by Redis since last save |
| `rdb_last_cow_size` | COW statistic for the latest RDB background job, usually in bytes |
| `aof_enabled` | Whether AOF is enabled |
| `aof_rewrite_in_progress` | Whether AOF rewrite is currently running |
| `aof_rewrite_scheduled` | Whether a rewrite is scheduled/queued per Redis |
| `aof_last_bgrewrite_status` | Status of the latest AOF rewrite |
| `aof_last_rewrite_time_sec` | Duration of latest rewrite |
| `aof_current_size` | Current AOF size reported by Redis |
| `aof_base_size` | Baseline size used for growth checks |
| `aof_last_cow_size` | COW statistic associated with AOF rewrite |
| `aof_delayed_fsync` | Counter of delayed AOF fsync events per Redis semantics |

Exact field names vary by Redis version; if a metric is missing, check version and config rather than assuming `0`.

### 20.1. Do not conclude from a single sample

For instance, running:

```redis
INFO persistence
```

returning:

```text
rdb_bgsave_in_progress:0
rdb_last_bgsave_status:ok
```

only says **at that instant** no `BGSAVE` is running and the previous one returned OK. It reveals nothing about the previous job's memory peak, p99 latency during the job, or whether AOF is healthy.

To evaluate persistence overhead, sample over time at an appropriate interval alongside OS metrics.

### 20.2. `rdb_last_cow_size` and `aof_last_cow_size`

These COW metrics indicate how many pages a write workload caused to be copied during a job.

However:

- They are per-**job** metrics, not total live memory usage at all times.
- Do not add them directly to `used_memory_rss` to estimate cgroup usage.
- Do not use them alone to predict peak memory if workloads shift.
- Compare trends under identical Redis version, allocator, OS, and load conditions.

## 21. Observing fork latency and Redis latency events

Also inspect:

```redis
INFO stats
LATENCY LATEST
LATENCY DOCTOR
SLOWLOG GET 20
```

Redis's latency monitor requires configuring an appropriate threshold before recording events:

```redis
CONFIG GET latency-monitor-threshold
```

In an authorized **lab**, you can use an illustrative threshold:

```redis
CONFIG SET latency-monitor-threshold 10
```

The unit for `latency-monitor-threshold` is **milliseconds**. Never alter production settings arbitrarily for benchmarking without evaluating metric overhead and change controls.

### 21.1. `SLOWLOG` and fork latency are not identical

`SLOWLOG` typically tracks server-side command execution time, excluding networking. Fork pauses or commands queued behind a stalled server may appear differently in `SLOWLOG` than per-command execution times.

Thus:

```text
Application p99 rises
SLOWLOG shows no slow GETs
```

does not clear Redis as the latency source. Check fork latency, disk, CPU, network, and client connection pools.

### 21.2. OS and container metrics

Alongside Redis `INFO`, collect:

- `memory.current` / cgroup memory metrics and OOM events.
- Parent and child Redis RSS, accounting for shared memory.
- Disk write throughput, latency, and queue depth.
- Free disk space and free inodes.
- User/system CPU and container CPU throttling.
- Page faults and swap in/out if swap is enabled.
- Storage fsync latency.
- Container restart reasons and `OOMKilled` statuses.

Focusing strictly on `redis-cli` while ignoring cgroups easily misses fork/COW failures.

## 22. RDB snapshot benchmark scenario

A meaningful test must use **production-like data and write workloads**, not merely running `BGSAVE` on an idle Redis.

Recommended lab workflow:

### Step 1 — Prepare dataset

Populate enough keys to resemble production:

```text
small strings:      many small keys
hash entities:      Hashes with realistic field counts
lists/zsets:        collections at expected sizes
TTL distribution:   varied expiration times
```

Do not generate data by hammering the same single key repeatedly if production mutates millions of scattered keys; that creates completely different COW patterns.

### Step 2 — Capture baseline

Run a steady read/write workload over a measurement window:

```text
GET/SET/INCR
Target write rate
Concurrent client count
p50/p95/p99 latency
RSS/cgroup memory
CPU and disk throughput
```

Record steady-state duration and starting memory usage.

### Step 3 — Start BGSAVE

In an **authorized test environment**:

```redis
BGSAVE
```

Keep the workload running. Capture:

```redis
INFO persistence
INFO stats
INFO memory
```

alongside system monitoring metrics.

### Step 4 — Measure while child runs

Observe:

- Fork-time pause.
- Total `BGSAVE` duration.
- Cgroup memory and RSS climb.
- COW bytes.
- Disk write throughput/latency.
- GET/SET p95/p99.
- Timeouts, errors, and OOM events.

### Step 5 — Measure after child finishes

Confirm `rdb_last_bgsave_status:ok` and continue observing several latency/memory intervals. Memory peaks may subside after the child exits, though allocator RSS does not necessarily drop back immediately.

### Step 6 — Repeat across load profiles

Compare at least:

- Read-heavy.
- Low write rate.
- Medium write rate.
- High write rate touching scattered keys.
- Disk under competing I/O load.

Outputs should chart **peak RAM and latency curves across workloads**, not just "BGSAVE took 5 seconds".

## 23. AOF and rewrite benchmark scenario

Separate **normal AOF append cost** from **`BGREWRITEAOF` cost**.

### 23.1. Comparing fsync policies

In independent runs with comparable datasets and loads, test:

```conf
appendfsync no
```

```conf
appendfsync everysec
```

```conf
appendfsync always
```

Record:

- Write throughput.
- p95/p99 latency.
- Disk IOPS / write throughput / fsyncs.
- Fsync delay counts and errors.
- Storage utilization.
- Data recovery rate after controlled crash tests.

Never change `appendfsync` on a Redis holding production data for ad-hoc benchmarking. Some managed Redis services also forbid altering this setting.

### 23.2. Testing BGREWRITEAOF

On a lab Redis with AOF enabled:

```redis
BGREWRITEAOF
```

Then monitor:

```redis
INFO persistence
```

and OS metrics. Record:

- Rewrite start/finish status.
- Rewrite duration.
- COW bytes.
- AOF size before and after rewrite.
- Peak disk space while old and new files coexist.
- In-flight command latency and timeouts.
- Cgroup memory peak and OOMs.
- Whether `aof_delayed_fsync` rises.

A rewrite that finishes cleanly yet pushes API p99 past SLA still represents an operational risk.

### 23.3. Why test rewrites once AOF is large?

If AOF is only a few MB, rewrites finish too fast to expose fork/COW, disk, and file-management costs. Production AOFs can span multiple GiB under heavy writes.

Do not run tiny synthetic datasets and assume rewrites are always harmless. Scale data and storage realistically.

## 24. Illustrative results and how to read them properly

Suppose a staging test yields this table:

| State | p99 SET (ms) | Container memory peak | Disk write | Notes |
|---|---:|---:|---:|---|
| Baseline without background jobs | 4 | 7.2 GiB | 20 MB/s | Steady |
| BGSAVE under read load | 8 | 7.4 GiB | 160 MB/s | Relatively low COW |
| BGSAVE under heavy write load | 55 | 8.8 GiB | 180 MB/s | Elevated COW |
| BGREWRITEAOF under heavy write load | 80 | 9.0 GiB | 210 MB/s | Disk/fsync contention |
| Rewrite with congested disk | 200 | 9.5 GiB | 90 MB/s | Prolonged job and high RAM |

**All numbers strictly illustrate presentation format**, not measured benchmarks or standard Redis thresholds.

How to interpret:

1. A clean baseline does not guarantee healthy persistence jobs.
2. `BGSAVE` on the same dataset size produces different COW under different write loads.
3. Slow disks prolong rewrites, widening the COW window.
4. Container memory peaking near its limit is dangerous even if `used_memory` stays under `maxmemory`.
5. Bad p99 must be judged against API SLAs and exact load, not a single `INFO` snapshot.

Never size production `maxmemory` from an estimated table; measure in a production-representative environment.

## 25. Verifying durable data: do not merely read back in the same process

A `SET` followed by `GET`:

```redis
SET durability:test 1
GET durability:test
```

proves Redis's in-memory state holds the value. It **does not prove RDB/AOF wrote durably**.

To test durability:

1. Generate writes with unique IDs.
2. Record acknowledged writes **outside Redis**.
3. Trigger an approved failure scenario in lab/staging.
4. Restart/restore Redis from persistence artifacts.
5. Read back acknowledged IDs.
6. Count missing, mismatched, and uncertain-outcome operations.

### 25.1. External write-log model

```text
Test harness
    |
    +-- write key=durability:run-1:seq:101
    |        |
    |        +-- Redis returns OK
    |        |
    |        +-- record seq=101 in external durable ACK log
    |
    +-- write key=durability:run-1:seq:102
             |
             +-- Redis times out
             |
             +-- record UNKNOWN status, do not treat as confirmed ACK
```

After restart:

```text
Current Redis
    |
    +-- reconcile every seq in ACK log
    |
    +-- record missing and mismatched counts
```

Timed-out writes must be classified as **UNKNOWN** because Redis may have executed them without the reply reaching the client.

### 25.2. Distinguishing process crash, OS crash, and power loss

Three failure injections expose different data risks:

| Scenario | Meaning |
|---|---|
| Controlled restart | Redis may flush/save cleanly before exiting |
| Process kill | Process dies abruptly, yet OS stays up and page cache may persist |
| Power loss / OS crash | Clearer exposure for un-persisted storage buffers |

Never equate "no data lost on process kill" with "no data lost on power outage". Understand OS cache, filesystem, and storage boundaries.

Run crash/power tests only in authorized isolated labs; never corrupt production storage to test RPO.

## 26. Measuring recovery time (RTO) and data loss (RPO)

Two standard objectives:

- **RTO (Recovery Time Objective):** target duration to restore service after an outage.
- **RPO (Recovery Point Objective):** maximum tolerable data loss measured in time or work volume.

With Redis persistence, a benchmark run must track:

```text
t0: failure starts / process lost
t1: Redis process restarts
t2: Redis finishes loading persistence
t3: Spring Data Redis stably serves GET/SET again
```

Measures:

```text
Observed server load duration = t2 - t1
Observed app recovery duration = t3 - t0
```

Large RDB/AOF files slow Redis startup loading, meaning **persistence file size affects not only runtime disk usage, but also RTO**.

### 26.1. RPO must be verified against real data

You cannot simply read:

```conf
appendfsync everysec
```

and write "RPO = 1 second" in a report. Measure acknowledged writes actually lost under specific failure modes for your storage and configuration.

Even with AOF intact, replica-based failover remains exposed to **asynchronous replication loss**, a separate data-loss path from local filesystem crashes.

## 27. When Redis runs out of disk or snapshot/AOF fails

Persistence imposes steady and peak disk demands:

```text
Disk usage before rewrite:
  Active AOF files
  RDB snapshot
  Other backups

During rewrite:
  Old active AOF
  New base AOF being built
  Incremental AOF
  Temporary files / metadata
```

If disk space or inodes run out:

- `BGSAVE` can fail.
- `BGREWRITEAOF` can fail and must keep the prior valid AOF set.
- AOF appends/fsyncs can hit I/O errors.
- Redis may reject writes or log errors depending on policy and version.
- Latency may rise before failures surface clearly.

Monitor **free bytes, free inodes, and disk latency**—not merely total AOF file size.

### 27.1. Why never manually delete active AOF files?

In Redis 7+ multi-part AOF, active files and the manifest depend on one another. Deleting a file just because it looks "big" can render the entire persistence set unrecoverable.

Safe workflow:

1. Identify Redis version and configured persistence paths.
2. Check current Redis status.
3. Create an appropriate backup/copy.
4. Use Redis-supported rewrite/retention mechanisms.
5. For corrupted files, run check/repair tools per recovery procedures on a **copy** before swapping real files.

Never edit manifests or truncate AOF files in a text editor on a running system.

## 28. Recovering when persistence files are corrupted

Redis provides file-checking tools, such as:

```bash
redis-check-rdb /path/to/dump.rdb
```

and version-appropriate AOF checks, for example:

```bash
redis-check-aof --check /path/to/appendonly.aof
```

Adjust exact paths and flags for your **actual file layout**: Redis 7+ uses a manifest and multiple AOF components rather than one monolithic file.

Rules to follow:

- Never run repair modes against live production persistence files in use by Redis.
- Always make a copy before attempting any repair.
- Verify Redis version compatibility with the file format.
- Confirm backups actually restore cleanly rather than merely existing on disk.
- Post-restore, reconcile critical records and validate the application.
- Record observed data loss instead of silently claiming complete recovery.

Options such as loading truncated AOF files depend on version/config and can drop the tail of the log. Never enable auto-repair without knowing what data may be discarded.

## 29. Replication, Sentinel, and Cluster do not replace persistence

A Redis primary with a replica:

```text
Primary (P) ---> Replica (R)
```

keeps a copy on another node and supports failover. However, replication is usually asynchronous:

```text
Client SET -> P returns OK
                   |
                   | data has not reached R yet
                   v
              P dies
                   |
                   v
              R is promoted
```

Some client-acknowledged writes can be absent from the new primary.

Persistence handles single-node recovery; replication/failover handle availability and node replacement. Neither replaces the other:

| Mechanism | What it helps | What it does not guarantee |
|---|---|---|
| RDB | On-storage snapshot | Writes right after snapshot are durable |
| AOF | Mutation log per fsync policy | Zero lost writes across all crashes |
| Replica | Data copy on another node | Every ACKed write replicated |
| Sentinel | Auto-discovers/promotes replacement primary | Zero-data-loss failover |
| Redis Cluster | Data sharding and per-slot/node HA | Cluster-wide atomic commits |
| Off-Redis backups | Recovery from corrupted files/data | RPO = 0 unless backups are continuous |

In a multi-primary Redis Cluster, **each primary holds a different slice of data**; assess persistence and disk/memory headroom **per node**, not from a cluster-wide RAM total.

### 29.1. Snapshots can worsen replication lag

Heavy CPU/disk usage from RDB or AOF rewrites can compete with replication traffic, raising replica lag under some conditions. If a primary fails while a replica lags, failover RPO degrades.

When benchmarking persistence on replicated topologies, collect:

```redis
INFO replication
```

and replication offsets/lag metrics alongside `rdb_last_cow_size`.

## 30. Common mistakes

**"`BGSAVE` runs in the background, so it cannot affect requests."** False. Fork, COW, CPU, and disk I/O can all raise latency.

**"Redis fork copies all 6 GiB of RAM immediately."** False. COW shares unmodified pages initially, copying pages only when mutated while the child lives.

**"A `SET` modifying 100 bytes only adds 100 bytes of COW."** False. COW operates at memory-page granularity and allocator structure level, not logical payload bytes.

**"`used_memory < maxmemory` means OOM is impossible."** False. RSS, COW, buffers, page cache, and cgroup limits can exceed `used_memory`.

**"Setting Redis `maxmemory` equal to the container memory limit is good."** High risk without headroom for fork, fragmentation, and background jobs.

**"`appendfsync everysec` guarantees losing at most 1 second."** No such absolute guarantee holds across storage stalls, OS delays, and crash scenarios.

**"`appendfsync always` turns Redis into a zero-loss transactional database."** No. Hardware, network, replication, and workflow limits remain.

**"AOF rewrite just compresses the existing log file."** False. Redis builds a fresh state representation while managing concurrent mutations during the rewrite.

**"Redis 7 uses multi-part AOF, so COW is gone."** False. Fork/COW remains a significant cost.

**"An RDB snapshot finishing at 12:10 contains all writes before 12:10."** False if the snapshot forked earlier.

**"Enabling `no-appendfsync-on-rewrite` is a free optimization."** False. It widens the un-persisted write window during background rewrites.

**"Redis replicas eliminate the need for backups."** False. Replicas mirror accidental deletes or corrupted writes and can lag.

**"A `GET` right after `SET` proves data is on disk."** No. It usually confirms only in-memory state.

**"A large `aof_current_size` proves rewrites failed."** No. Check rewrite triggers, job status, baseline size, and Redis version.

**"Watching only parent RSS suffices to measure fork RAM."** No. Account for shared pages, COW, and cgroup memory.

**"Increasing Java timeouts fixes fork OOMs."** No. Timeouts only alter client waiting behavior; they add zero RAM to Redis.

**"It is safe to retry `INCR` endlessly if it times out during a rewrite."** False. The initial command may have executed; retrying double-increments.

**"Redis is just a cache, so turning off persistence has zero impact."** Doubtful. Cold caches can overload origin DBs, and some apps store non-rebuildable state in Redis.

## 31. Strategy selection table by business requirement

| Workload | Direction to consider | What to verify |
|---|---|---|
| Rebuildable cache | Can reduce or disable persistence per architecture | Cold start, DB surge, eviction |
| Sessions requiring recovery | Suitable RDB/AOF or separate durable store | RPO, restarts, security |
| Non-critical statistical counters | AOF `everysec` or external batching | Acceptable data-loss level |
| Event Streams requiring replay | Strong persistence/replication and idempotency | RPO, pending/ACKs, trimming |
| Authoritative order/payment state | Consider a DB with fitting transactions/durability | Exactly-once side effects and recovery |
| Very large dataset, high write rate | Measure COW, fork latency, and disk throughput closely | Memory peak and p99 under BGSAVE/rewrite |
| Tight container memory limit | Budget COW/page cache, avoid RAM overcommit | Cgroup memory and OOM events |
| Multi-node Sentinel/Cluster | Test per node and across failover | Replication loss, RTO/RPO |
| Slow or shared disk | Schedule and throttle I/O | Rewrite duration, fsync delays |
| Managed Redis | Follow provider capabilities and limits | Allowed settings, backups, and metrics |

Not every workload needs both RDB and AOF. Decisions should stem from **data semantics**, acceptable loss, and measured operational cost.

## 32. Repeatable pre-production test procedure

A practical test plan includes:

### Phase A — Define targets

Document:

```text
Expected dataset:       <GiB, key count, data-type mix>
Writes/sec:             <steady and peak>
Redis/OS/container:     <versions, RAM, cgroup limit>
Storage:                <type, throughput, IOPS>
Target API p99 latency: <ms>
Maximum RPO:            <seconds / acknowledged writes>
Maximum RTO:            <seconds>
```

### Phase B — Capture baseline

Measure `INFO memory`, `INFO persistence`, CPU, disk, cgroup memory, and Spring Data Redis latency with **no background jobs running**.

### Phase C — Run RDB snapshot

In the lab, trigger `BGSAVE` while sustaining production-like load. Record fork time, completion time, COW, peak memory, p99, and disk metrics.

### Phase D — Run AOF rewrite

Enable AOF in the test environment, grow the log realistically, run `BGREWRITEAOF`, and measure the same metrics plus `aof_delayed_fsync` and peak disk usage.

### Phase E — Apply stress

Test high write bursts, scattered-key updates, competing disk I/O, and realistic cgroup limits. Do not test only the happy path.

### Phase F — Crash and restore test

Using an external ACK log, inject crashes in the lab per defined scenarios, restart/restore, and reconcile acknowledged writes. Never run destructive tests in production.

### Phase G — Test with replicas and failover

Measure replication lag, failover RPO, and client reconnection. Distinguish single-node crash loss from async replication loss.

### Phase H — Report and decide

Summarize:

- Peak memory and headroom.
- p99 increase during `BGSAVE`/rewrites.
- Background job durations.
- Disk/fsync pressure.
- Error/timeout rates.
- Observed RPO/RTO.
- Selected configuration and rationale.
- Experiment limitations and untested scenarios.

Accept a configuration only when production-like test results meet operational requirements.

## 33. Operations and alerting checklist

### 33.1. Memory

- [ ] Monitor `used_memory`, `used_memory_rss`, and `used_memory_peak`.
- [ ] Monitor `maxmemory`, evictions, and `mem_not_counted_for_evict`.
- [ ] Monitor cgroup/host memory, OOM events, and swap.
- [ ] Measure `rdb_last_cow_size` and `aof_last_cow_size` during persistence jobs.
- [ ] Maintain fork/COW headroom validated by realistic load tests.
- [ ] Recognize scattered writes generate different COW from hot-key updates.

### 33.2. Snapshots

- [ ] Know which `save` rules are active.
- [ ] Track the timestamp of the last successful snapshot.
- [ ] Alert when `rdb_last_bgsave_status` fails.
- [ ] Monitor `BGSAVE` duration and fork latency.
- [ ] Ensure disk space, permissions, and off-host backups.
- [ ] Understand behavior when `stop-writes-on-bgsave-error` triggers.

### 33.3. AOF

- [ ] Know active `appendonly` and `appendfsync` policies.
- [ ] Monitor AOF size and rewrite frequency.
- [ ] Alert when `aof_last_bgrewrite_status` fails.
- [ ] Monitor `aof_delayed_fsync` and disk latency.
- [ ] Understand multi-part AOF layout for your Redis version.
- [ ] Test actual restarts/restores from AOF.
- [ ] Never manually delete active AOF files or manifests.

### 33.4. Spring Data Redis application

- [ ] Measure GET/SET/INCR latency and error rates by operation type.
- [ ] Distinguish cache misses, timeouts, and connection failures.
- [ ] Never blindly retry non-idempotent commands.
- [ ] Know whether Redis is a cache or source of truth for each data type.
- [ ] Mitigate cache stampedes on Redis restarts.
- [ ] Maintain fallback/load-shedding behavior when Redis is unavailable.

### 33.5. Recovery

- [ ] Define acceptable RTO/RPO before testing.
- [ ] Store backups independently of the Redis instance.
- [ ] Run periodic restore drills.
- [ ] Maintain an external ACK log or reconciliation source for critical workloads.
- [ ] Test both single-node crashes and replica failovers.
- [ ] Document the limits of asynchronous replication.

## 34. Conclusion

The cost of **RDB snapshots** and **AOF rewrites** extends well beyond persistence file size. Because Redis stores data in RAM, `fork()` and **copy-on-write** can drive sharp physical memory growth while writes continue during background snapshots or AOF base creation. CPU, disk throughput, fsync latency, and file management can degrade Spring Data Redis p95/p99 latency even while Redis keeps serving commands.

Key principles to remember:

1. **`BGSAVE` captures state at fork time**, excluding writes occurring up until file completion.
2. **COW cost scales with memory pages modified while the child runs**, neither matching modified payload bytes nor always equaling the full dataset size.
3. **`used_memory` and `maxmemory` cannot predict OOM alone**; measure RSS/cgroup memory, buffers, fragmentation, and COW peaks.
4. **AOF `appendfsync` trades performance against durability**; `everysec` is not a hard cap of at most one second lost.
5. **`BGREWRITEAOF` compacts state to curb AOF growth**, yet still incurs fork/COW and disk overhead; Redis 7+ multi-part AOF requires proper management.
6. **A successful `SET` or `GET` readback does not prove disk durability.** Measuring RPO requires crash/recovery tests with an external ACK log.
7. **Replication and failover do not replace persistence**, since replicas can lag and acknowledged writes remain exposed.
8. **In Spring Data Redis**, track errors/timeouts, p95/p99 latency, and command-idempotent retry rules; raising timeouts will not fix fork/OOM/disk bottlenecks.
9. **Size via measurement**, never from assumptions that "background means free" or a fixed RAM multiplier.

A durable, performant Redis deployment is one tested across **snapshots, rewrites, memory peaks, storage pressure, and real recovery**, tuned to the value of the data and the risk the application can truly accept.
