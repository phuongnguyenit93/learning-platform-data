# Evaluating Disk, Journal, Checkpoints, and Compression Configuration in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Performance Tuning  
> **Lesson:** Evaluating Disk, Journal, Checkpoints, and Compression Configuration

## 1. Real-World Scenario: MongoDB Is Slow Despite Spare CPU

An order service runs on a MongoDB replica set. During peak hours, operations observe:

- Order-write API p95 jumps from 35 ms to 350 ms.
- Primary CPU sits around 50–60%, not saturated.
- `iostat` shows `w_await` climbing sharply with a growing write queue.
- WiredTiger accumulates dirty pages and checkpoint durations lengthen.
- On a cloud volume, write IOPS approaches its provisioned cap.
- Actual disk usage grows faster than projected after a data import.

Someone suggests "disabling the journal to write faster," another wants to "switch all collections to `zstd`," and a third claims "just adding RAM will fix it." None of these is guaranteed right without separating the underlying stages:

```text
Application write
       |
       v
mongod: parse / validate / index updates
       |
       v
WiredTiger pages in cache
       |
       +---------------------+
       |                     |
       v                     v
Journal write-ahead log    Checkpoint / data files
       |                     |
       v                     v
Journal flush / fsync      Dirty page write / fsync
       |                     |
       +----------+----------+
                  |
                  v
             Filesystem / OS
                  |
                  v
            SSD / cloud disk
       (IOPS, throughput, latency,
         queue, capacity, burst)
```

**Journal** and **checkpoints** work together to provide durability, yet they are not interchangeable substitutes. **Compression** shrinks bytes stored on and transferred to storage, yet consumes CPU and shifts performance depending on workload. **Disk evaluation** must inspect latency, IOPS, throughput, capacity, and true I/O limits together.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Identify disk bottlenecks using IOPS, MiB/s, latency, queue depth, and volume limits.
2. Distinguish logical data size, allocated bytes, and filesystem usage.
3. Explain WiredTiger journaling, checkpoints, crash recovery, and how they relate to write concern.
4. Read metrics from `serverStatus.wiredTiger.log`, `checkpoint`, `cache`, and OS/cloud tools.
5. Understand three compression tiers: **collection block compression**, **journal compression**, and **index prefix compression**.
6. Compare `snappy`, `zlib`, `zstd`, and `none` across CPU, I/O, storage, and latency.
7. Understand why default config changes generally apply only to **newly created collections and indexes**.
8. Design fair, single-variable benchmarks with clear rollback plans.
9. Practice with `mongosh` and OS diagnostics on simulated data without touching production settings.

## 2. Storage Model: From Document to Bytes on Disk

MongoDB uses WiredTiger as its default storage engine in standard deployments. Several layers sit between a BSON document and physical bytes on disk:

```text
BSON documents and indexes
          |
          v
WiredTiger B-tree pages
          |
       (compression)
          |
          v
Allocated WiredTiger data/index blocks
          |
          +---- Journal files
          +---- History store / oplog
          +---- Checkpoint and temporary I/O
          |
          v
Filesystem / OS page cache
          |
          v
Block device / cloud volume
          |
          v
Snapshots, backups, replicas elsewhere
```

A 2 KiB document does not mean MongoDB performs one exact 2 KiB disk write per operation. A write updates data pages, multiple indexes, journal records, and later checkpointed data blocks. The OS and storage stack also coalesce or split I/O.

### 2.1. Storage Metrics Mean Different Things

| Concept | Example Measurement | Meaning |
| --- | --- | --- |
| Logical BSON data | `dataSize` | Uncompressed logical document bytes per MongoDB stats |
| Storage allocation | `storageSize` | Bytes allocated for collection data |
| Index allocation | `indexSize` | Bytes allocated for indexes |
| Total DB data/index | `totalSize` | Typically `storageSize + indexSize` |
| Journal files | Filesystem, `wiredTiger.log` | Write-ahead logging; fluctuates with activity |
| Oplog / history store | Namespace / filesystem | Needed for replication, rollback, and snapshots |
| Reusable free space | `freeStorageSize` (where supported) | Allocated space freed internally for reuse |
| Filesystem used/free | `df -h` or cloud metrics | All files and metadata on the volume |
| Backups/snapshots | Backup/cloud tooling | Often stored outside MongoDB's filesystem |

Example:

```text
Logical BSON data       300 GiB
Collection allocation   180 GiB  (with compression)
Index allocation         45 GiB
Journal + oplog + other  35 GiB
Filesystem overhead      10 GiB
---------------------------------
Disk used               ~270 GiB
```

These numbers are **illustrative**, not fixed ratios. Pull measurements from the exact same timestamp, node/volume, and metric definitions.

### 2.2. Why Can `dataSize` Exceed `storageSize`?

BSON documents repeat field names and often carry repetitive strings or JSON-like payloads; block compressors exploit that redundancy. Thus 300 GiB of logical BSON can fit inside under 200 GiB of allocated storage.

However:

- Already-compressed data (JPEG, PDF, ZIP, ciphertext) compresses poorly.
- Different document shapes yield different ratios.
- Indexes consume extra bytes separately.
- Fragmentation and internal free space keep `storageSize` from shrinking immediately after deletes.
- `dataSize` excludes journal, oplog, and external files.

Never treat `dataSize / storageSize` as a universal "absolute compression ratio" for the whole system.

## 3. Evaluating Hardware and Cloud Storage

### 3.1. Criteria Before Selecting Storage

| Attribute | Question |
| --- | --- |
| Usable capacity | How much remains after OS, journal, oplog, and headroom? |
| Random read IOPS | Can it serve index lookups and page-ins within SLO? |
| Random write IOPS | Can it keep up with updates, index writes, and journal/checkpoints? |
| Sequential throughput | How fast do backups, restores, large scans, and index builds run? |
| Read/write latency | How long does each I/O wait, especially at p95/p99? |
| Queue depth | Do requests form sustained I/O queues? |
| Burst / credits | Do cloud volumes run fast briefly and then throttle once credits deplete? |
| Durability | Are replication, snapshot policies, and failure domains sound? |
| Filesystem / OS | Are mount options and `fsync` behavior compatible? |
| Workload isolation | Do DB files, journal, and backups/temp contend on one volume? |

**NVMe SSDs**, **network SSDs**, and **cloud block storage** have different capabilities and ceilings. "1 TiB disk" states capacity only—never IOPS or bandwidth.

### 3.2. IOPS Differs from Throughput

A workload reading 4 KiB blocks:

\[
20\,000 \text{ IOPS} \times 4 \text{ KiB}
\approx 78.1 \text{ MiB/s}
\]

A sequential workload reading 1 MiB blocks:

\[
200 \text{ IOPS} \times 1 \text{ MiB}
=200 \text{ MiB/s}
\]

The first workload is **IOPS-hungry**; the second is **throughput-hungry**. The same volume can hit its IOPS limit long before its MiB/s cap, or vice versa.

### 3.3. Latency and Queue Depth

When incoming I/O demand exceeds device service capacity, queues lengthen and latency spikes rapidly.

```text
Arrival:    10,000 I/O requests/s
Capacity:    8,000 I/O requests/s
            ----------------------
Backlog:    +2,000 requests/s if sustained
```

As queues grow, journal `fsync`s and checkpoint writes stall behind queued I/O. Increasing disk GiB capacity fixes nothing if the IOPS quota stays flat.

An approximate relation via Little's Law:

\[
L \approx \lambda W
\]

Where `L` is average requests in the system, `λ` is throughput, and `W` is average time in the system. This models queue/latency correlation—**not a formula to compute exact MongoDB latency from a single `iostat` counter**.

### 3.4. Reading `iostat`

On Linux with `sysstat`:

```bash
iostat -xz 1 5
```

Common columns:

- `r/s`, `w/s`: read/write operations per second.
- `rkB/s`, `wkB/s`: read/write throughput.
- `r_await`, `w_await`: average read/write I/O latency, including queue wait per tool semantics.
- `aqu-sz`: average request queue length.
- `%util`: percentage of elapsed time the device had active I/O as measured by the kernel.

**Do not equate `%util=100%` on NVMe or cloud volumes with "100% maximum IOPS reached."** Parallel storage devices handle many concurrent I/Os; always correlate latency, queue depth, throughput, and provisioned caps.

### 3.5. Use Multi-Layer Telemetry

```text
API latency increased
           |
           v
MongoDB write latency increased?
           |
           +-- No  -> check app/network/pool/downstream
           |
           +-- Yes -> journal sync/checkpoint/eviction?
                         |
                         +-- OS disk await/queue up?
                         |         |
                         |         +-- Yes -> I/O pressure
                         |
                         +-- CPU/query/lock/replication?
```

A low CPU snapshot does not prove storage is healthy. Conversely, low disk latency does not rule out CPU, locks, query plans, or flow control.

## 4. What Is the Journal in WiredTiger?

### 4.1. Write-Ahead Log for Crash Recovery

WiredTiger combines a **journal (write-ahead log)** with **checkpoints** to protect data durability.

When a write modifies a document and its indexes, the storage engine generates journal records describing the changes. Records are buffered in memory and written/synced to journal files according to configuration rules.

```text
Client update
      |
      v
Update page(s) / index(es) in cache
      |
      v
WiredTiger journal record(s)
      |
      +--> memory buffer
      |
      v
Journal write / sync
      |
      v
Durable journal on storage
      |
     ...
      |
      v
Later checkpoint persists data pages
```

Do not misread this diagram as "every write finishes journal sync before returning success." **When acknowledgement returns depends on write concern**, especially `j` and `w`.

### 4.2. The Journal Is Not a Diagnostic Log

Easily confused names:

- `mongod.log` / container logs: **diagnostic logs** for operational observability.
- `WiredTigerLog.<sequence>` inside `dbPath/journal`: **write-ahead journal** for durability and crash recovery.

Never tail, rotate, or delete journal files manually like application logs. Deleting or truncating journal files destroys crash recovery capability.

### 4.3. Journaling Is Always Enabled in Modern MongoDB

Starting in **MongoDB 6.1**, journaling is always on per official docs. Legacy options `storage.journal.enabled`, `--journal`, and `--nojournal` have been removed.

Therefore, never suggest "turning off the journal to boost TPS" on MongoDB 6.1+; it is unsupported and compromises durability. Even on older versions, never disable journaling for important data.

### 4.4. One Journal Record Can Cover Index Updates Too

Example:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { status: "PAID", updatedAt: new Date() } }
);
```

If `status` and `updatedAt` are indexed, the write modifies both document and index entries. Per WiredTiger journaling behavior, journal records for a client write can cover related internal modifications.

Do not infer from `modifiedCount=1` that only one disk write or one index entry changed.

## 5. When Is the Journal Synced?

### 5.1. Buffering and Group Commit

MongoDB configures WiredTiger with journal buffering. Instead of issuing a separate physical `fsync` per write, the engine groups concurrent modifications to reduce overhead.

Key sync triggers per documentation:

- A write specifying or implying `j: true` triggers journal sync on the corresponding replica set member.
- Secondaries sync the journal as oplog batches are applied.
- Default journal commit interval is around **100 ms**.
- When creating a new journal file (each file is capped around **100 MB**).

These are **design triggers**, not a guarantee that "every write takes at most 100 ms" on storage. Actual latency still depends on queues, `fsync`, workload, and OS scheduling.

### 5.2. `storage.journal.commitIntervalMs`

On self-managed deployments / supported versions:

```yaml
storage:
  journal:
    commitIntervalMs: 100
```

Per current configuration docs, this is the default maximum interval between journal sync operations, bounded by version limits. Lowering it increases sync frequency and disk overhead; raising it widens the durability window for writes without `j: true`.

**Never tune `commitIntervalMs` on guesswork**, and never alter an application's durability contract merely to mask a latency spike.

### 5.3. `j: true` and `w: "majority"`

Example:

```javascript
db.orders.insertOne(
  {
    _id: new ObjectId(),
    status: "CREATED",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
```

Distinguish clearly:

- `w: 1`: primary acknowledgement per write concern semantics.
- `w: "majority"`: acknowledgement once a majority of voting/eligible members confirm per write concern rules.
- `j: true`: requests on-disk journal durability per deployment semantics.
- `wtimeout`: caps how long to wait for write concern; timing out does **not** mean the write rolled back.

In a replica set, `w: "majority"` **implies `j: true` when `writeConcernMajorityJournalDefault=true`** per documentation. Never state unconditionally that majority always implies journal durability regardless of configuration or version.

`j: true` **does not replace `w: "majority"`** when failover durability across replicas is required. Conversely, stronger write concerns increase latency when secondaries or disks saturate.

### 5.4. Write Concern Timeouts and Unknown Outcomes

If a client receives a timeout:

```text
Client sends update
       |
MongoDB may have applied write
       |
Journal/replica acknowledgment delayed
       |
Client times out
```

Never treat "timeout" as "nothing was written" and blindly insert duplicate records. Reconcile using business keys, idempotency keys, or retryable writes where applicable—this protects correctness and prevents duplicate load during storage slowdowns.

### 5.5. Journal Security and Safety

The journal contains sensitive database writes. Enforce:

- Strict OS permissions on `dbPath`.
- Encryption at rest / volume encryption as required.
- Secure backup/snapshot policies and key management.
- Never copy journal files to world-readable folders for "debugging."
- Never delete `WiredTigerLog.*` manually.
- Maintain disk headroom: running out of space for the journal can crash `mongod`.

## 6. What Is a Checkpoint?

### 6.1. A Consistent Point-in-Time State on Disk

WiredTiger creates **checkpoints** to flush consistent snapshots of data files to persistent storage so recovery can start from a valid baseline.

Diagram:

```text
Memory / cache has latest changes
                |
                v
        WiredTiger checkpoint
                |
        write dirty data pages
                |
                v
     data files at consistent state
                |
                v
        checkpoint metadata
     references new valid checkpoint
```

WiredTiger keeps the **previous checkpoint valid while writing the new checkpoint**. Only after metadata atomically flips to the new checkpoint does it become the recovery baseline.

### 6.2. Typical Checkpoint Interval

Per WiredTiger docs, MongoDB triggers checkpoints roughly every **60 seconds**. Do not interpret this as a promise that every checkpoint finishes within 60 seconds; duration depends on dirty pages, device speed, and concurrent load.

Under heavy writes, checkpoints cause disk write bursts. Still, **disk writes rising around checkpoints is not automatically a bug**—correlate checkpoint duration, queue depth, latency, and application impact.

### 6.3. Journal + Checkpoint on Restart

Suppose:

```text
T0: checkpoint A completes
T1: write X, journal durable
T2: write Y, journal durable
T3: process crashes before checkpoint B
T4: mongod restarts
```

Conceptual recovery flow:

1. Locate the last valid checkpoint metadata.
2. Identify journal records written after that checkpoint.
3. Replay the required changes.
4. Restore consistent durable state per contract.

Thus **checkpoints are not required for each `j: true` write to be durable**; the journal bridges durability between checkpoints.

### 6.4. Checkpoints Are Not Standalone Backups

A checkpoint is an **internal storage-engine mechanism**. Never arbitrarily copy live open `.wt` files and treat them as a valid backup.

Backups require:

- Supported MongoDB/Atlas/snapshot procedures.
- Cross-file consistency across data, indexes, and metadata.
- Oplog/PITR when point-in-time recovery is needed.
- Matching replica state, FCV, and topology.
- Tested restore drills.

**Journal + checkpoint do not replace backups**, and cannot rescue you if a user runs an authorized drop/delete that promptly gets journaled and checkpointed.

### 6.5. History Store and Long Transactions

WiredTiger relies on MVCC and snapshot history. Long-running reads or transactions pin old versions, swelling the history store, cache pressure, and I/O.

Docs describe `minSnapshotHistoryWindowInSeconds` governing snapshot history retention and `WiredTigerHS.wt`. Never expand the history window to "fix slow reads" without evaluating storage impact.

## 7. How Journal, Checkpoints, Eviction, and Cache Interact

```text
             MongoDB writes
                   |
                   v
        WiredTiger dirty pages
                   |
         +---------+---------+
         |                   |
         v                   v
    Journal records     Checkpoint / eviction
         |                   |
  journal flush/fsync     data page writes
         |                   |
         +---------+---------+
                   |
                   v
          Same storage subsystem
                   |
                   v
         IOPS, latency, queue
```

### 7.1. Dirty Cache Pressure

During heavy updates, dirty bytes climb. If storage writes fall behind, checkpoints and evictions take longer, forcing application threads into eviction work or stalls waiting for clean cache space.

Still, high dirty cache ratio **does not mean the journal is non-durable**; journal durability and dirty cache pages operate independently.

### 7.2. When Checkpoints Look Like the Culprit but Are Only a Symptom

Scenario:

```text
13:00 bulk import starts
13:01 dirty bytes rise
13:02 checkpoint duration rises
13:02 disk write latency rises
13:02 API p95 increases
```

The true root cause may be **the bulk import pushing writes past IOPS limits**, while longer checkpoints are merely a downstream consequence. Changing checkpoint intervals will not fix a saturated disk.

### 7.3. Why Adding Cache May Not Help

A larger cache holds more pages, yet:

- Adds zero physical disk IOPS or throughput.
- Steals RAM from the OS filesystem page cache.
- Can trigger OOM kills inside containers.
- Does not stop long transactions from pinning history.
- May merely delay rather than eliminate I/O write bursts.

Prove the bottleneck before adjusting `storage.wiredTiger.engineConfig.cacheSizeGB` or `cacheSizePct`.

## 8. Reading Journal Metrics from `serverStatus()`

On WiredTiger servers:

```javascript
const s = db.serverStatus();
const log = s.wiredTiger?.log || {};

printjson({
  uptime: s.uptime,
  logBytesWritten: log["log bytes written"],
  logPayloadBytes: log["log bytes of payload data"],
  logWriteOperations: log["log write operations"],
  logSyncOperations: log["log sync operations"],
  logSyncDurationUs: log["log sync time duration (usecs)"],
  recordsCompressed: log["log records compressed"],
  recordsNotCompressed: log["log records not compressed"],
  recordsTooSmall:
    log["log records too small to compress"]
});
```

Keys inside `wiredTiger.log` are **storage-engine statistics** that may vary or be omitted across releases. Some managed tiers restrict `serverStatus`.

### 8.1. Interpreting the Counters

| Metric | How to Read It |
| --- | --- |
| `log bytes written` | Total journal bytes written per engine stats |
| `log bytes of payload data` | Payload bytes tracked separately |
| `log write operations` | Journal write operations, typically cumulative |
| `log sync operations` | Tracked journal sync operations |
| `log sync time duration (usecs)` | Cumulative sync time in microseconds |
| `log records compressed` | Count of compressed journal records |
| `log records too small to compress` | Records below the minimum compression size threshold |

**Never** assume `logBytesWritten` equals the current disk size of the journal directory: it is a cumulative counter, whereas journal files are recycled via checkpoints and recovery.

### 8.2. Computing Journal Rates via Deltas

\[
\text{Journal bytes/s}
=
\frac{B_2-B_1}{t_2-t_1}
\]

\[
\text{Journal sync/s}
=
\frac{S_2-S_1}{t_2-t_1}
\]

For total sync duration `T` and sync count `S`:

\[
\text{Mean sync time over interval}
\approx
\frac{T_2-T_1}{S_2-S_1}
\]

These formulas apply only when both samples come from **the same process**, counters have not reset, and the denominator is positive. This yields the interval average—**not p95 fsync latency**.

### 8.3. Two-Sample Script with Reset Guard

```javascript
function journalSample() {
  const s = db.serverStatus();
  const log = s.wiredTiger?.log || {};

  return {
    at: Date.now(),
    uptime: s.uptime,
    bytes: log["log bytes written"],
    syncs: log["log sync operations"],
    syncTimeUs: log["log sync time duration (usecs)"]
  };
}

function safeNumber(value) {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) &&
    Number.isSafeInteger(n) ? n : null;
}

function rate(v1, v2, elapsedSec) {
  const a = safeNumber(v1);
  const b = safeNumber(v2);
  if (a == null || b == null ||
      b < a || elapsedSec <= 0) return null;
  return (b - a) / elapsedSec;
}

const first = journalSample();
sleep(5000);
const second = journalSample();
const seconds = (second.at - first.at) / 1000;

if (second.uptime <= first.uptime) {
  print("Uptime did not increase: discard measurement if a restart occurred.");
} else {
  const bytesPerSec =
    rate(first.bytes, second.bytes, seconds);
  const syncsPerSec =
    rate(first.syncs, second.syncs, seconds);

  printjson({
    elapsedSec: seconds,
    journalBytesPerSec: bytesPerSec,
    journalSyncsPerSec: syncsPerSec,
    averageJournalSyncMs:
      syncsPerSec > 0
        ? (rate(first.syncTimeUs,
                second.syncTimeUs,
                seconds) / syncsPerSec) / 1000
        : null
  });
}
```

This is a **diagnostic sampling example**. Production systems should use time-series telemetry agents handling counter resets, 64-bit integers, and instance identity cleanly. `Number()` is not exact for arbitrary 64-bit counters; the helper returns `null` beyond `MAX_SAFE_INTEGER`.

## 9. Reading Checkpoint Metrics from WiredTiger

`serverStatus` exposes metrics under `wiredTiger.checkpoint` and `wiredTiger.transaction` depending on version.

```javascript
const s = db.serverStatus();

printjson({
  checkpoint: s.wiredTiger?.checkpoint,
  selectedTransactionCheckpoint: {
    checkpoints:
      s.wiredTiger?.transaction?.[
        "transaction checkpoints"
      ],
    recentMs:
      s.wiredTiger?.transaction?.[
        "transaction checkpoint most recent time (msecs)"
      ],
    totalMs:
      s.wiredTiger?.transaction?.[
        "transaction checkpoint total time (msecs)"
      ]
  }
});
```

Never assume all fields exist identically across releases. When `checkpoint` fields appear:

- `most recent time (msecs)`: duration of the latest checkpoint.
- `max time (msecs)`: longest recorded checkpoint.
- `total time (msecs)`: cumulative checkpoint time.
- `total succeed number of checkpoints`: successful checkpoints counter.
- `total failed number of checkpoints`: failed checkpoints counter.
- `bytes written for checkpoint` under `block-manager`/`capacity`: related throughput indicator when present.

### 9.1. How to Evaluate Long Checkpoints

A single 3-second checkpoint is not automatically a bug. If normal recent times are 0.8 seconds and peak hours jump to 35 seconds alongside rising disk write latency, queue depth, and API p99, investigate immediately.

Check:

- Dirty cache bytes.
- Disk write latency, IOPS, and throughput.
- Journal sync durations.
- Index builds or bulk imports.
- Long-running transactions and snapshot history.
- Replication lag and write concern.
- Cloud volume burst quotas.

### 9.2. What Never to Do

- Never delete checkpoint or WiredTiger metadata files.
- Never manually edit `WiredTiger.wt` or `WiredTigerHS.wt`.
- Never restart the primary repeatedly just because checkpoints take longer.
- Never alter checkpoint scheduling without documentation and benchmarking.
- Never assume fast checkpoints guarantee fast journal `fsync`s.

## 10. Compression Configuration: Three Completely Separate Layers

WiredTiger has **three compression layers**, each addressing a different data structure.

| Layer | Configuration | What Is Compressed | Common Default |
| --- | --- | --- | --- |
| Collection block | `storage.wiredTiger.collectionConfig.blockCompressor` | Collection data blocks | `snappy` for most collections; **time-series defaults to `zstd`** |
| Journal | `storage.wiredTiger.engineConfig.journalCompressor` | Journal records | `snappy` |
| Index prefix | `storage.wiredTiger.indexConfig.prefixCompression` | Shared prefixes across index keys | `true` |

**Do not confuse these with MongoDB wire protocol network compression** (`compressors` in driver/server), which applies strictly to data **in transit over the network**.

### 10.1. Collection Block Compression

WiredTiger compresses data blocks on disk. Documented options:

- `none`: no block compression.
- `snappy`: prioritizes speed and relatively light CPU.
- `zlib`: often higher compression ratio at higher CPU cost.
- `zstd`: often strong balance of ratio and speed depending on level and corpus.

**No single compressor is best for every workload.** A CPU-bound service can suffer if switched to a heavy algorithm/level even if disk footprint shrinks.

### 10.2. Journal Compression

Configured independently from collection compression:

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: snappy
```

Choices: `none`, `snappy`, `zlib`, `zstd`. The journal compressor applies to write-ahead log records and **does not alter how collection data blocks are encoded**.

Per documentation, WiredTiger skips compressing journal records **≤ 128 bytes**. Thus journal compression ratios depend heavily on record size and workload, not just the algorithm.

### 10.3. Index Prefix Compression

B-tree indexes often contain keys sharing prefixes:

```text
customer:0000001
customer:0000002
customer:0000003
customer:0000004
```

Instead of storing the full prefix on every key, prefix compression cuts index storage. It is **not** `snappy`/`zlib`/`zstd` on index keys—it is **prefix deduplication**.

MongoDB enables `prefixCompression: true` by default. Savings can be large on compound/prefixed keys, and smaller on random hashes/UUIDs.

Never disable prefix compression to "save CPU" without benchmarking; most workloads benefit from the smaller disk and cache footprint.

## 11. Comparing `snappy`, `zlib`, `zstd`, and `none`

| Algorithm | Typical Strength | Trade-Off | When Worth Testing |
| --- | --- | --- | --- |
| `snappy` | Fast compress/decompress, relatively light CPU | Lower ratio than `zlib`/`zstd` | Latency-sensitive OLTP; solid baseline |
| `zstd` | Strong ratio, often balanced speed; tunable levels | High levels consume significant CPU | Large datasets, storage-constrained, spare CPU headroom |
| `zlib` | High ratio on compressible corpora | Often slower / higher CPU than `snappy` | Archive-heavy or highly compressible data; measure carefully |
| `none` | Eliminates CPU compression cost at that tier | High disk/I/O usage, less effective OS page cache | Pre-compressed data or extreme CPU scarcity; benchmark first |

**This table shows general tendencies, not guaranteed rankings across all environments.** Real outcomes depend on data shape, document sizes, compression levels, cache state, read/write mix, CPU instruction sets, and disk IOPS.

### 11.1. Data That Compresses Well

Documents with repetitive keys, enums, and prose:

```javascript
{
  tenantId: "demo-tenant",
  category: "BOOK",
  status: "ACTIVE",
  description:
    "Simulated document with repetitive structure for compression testing"
}
```

Repetitive structures and long strings compress far better than high-entropy bytes.

### 11.2. Data That Compresses Poorly

- Pre-compressed JPEG/PNG/video media.
- ZIP/gzip archives.
- Properly encrypted ciphertext.
- Random / high-entropy bytes.
- Payloads already compressed by the application.

Do not turn on high-level `zstd` over pre-compressed blobs expecting another 50% savings; you will mostly burn CPU.

### 11.3. Compression Affects RAM and I/O in Two Ways

```text
Compressed blocks on disk
              |
         OS page cache
       (compressed bytes)
              |
        WiredTiger reads
              |
           Decompress
              |
       WiredTiger cache
       (working pages)
```

Compression shrinks on-disk bytes and lets the OS page cache fit more compressed blocks in RAM. However, the WiredTiger internal cache holds uncompressed in-memory page representations, so never assume internal cache memory shrinks at the exact same ratio as disk files.

### 11.4. When Does Stronger Compression Slow Queries Down?

If a workload:

- Fits comfortably in cache;
- Is CPU-bound on query execution;
- Frequently updates/dirtied pages;
- Demands ultra-low p99 latency;

then disk savings may not pay back compression/decompression CPU overhead.

Conversely, on I/O-bound workloads, a stronger compressor can **cut physical reads and writes**, lowering latency even while CPU climbs. Always measure empirically.

## 12. Configuring WiredTiger on Self-Managed MongoDB

### 12.1. Reference YAML Snippet

Example for a **self-managed lab environment**, not an immediate production recommendation:

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: snappy
    collectionConfig:
      blockCompressor: snappy
    indexConfig:
      prefixCompression: true
```

This reflects documented defaults for standard collections, journaling, and indexes. Time-series collections have different compression defaults.

### 12.2. Experimental `zstd` Configuration

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: zstd
      zstdCompressionLevel: 6
    collectionConfig:
      blockCompressor: zstd
    indexConfig:
      prefixCompression: true
```

This is an **experimental test config**, not a universal "best practice." Changing both journal and collection compressors at once makes it **impossible to isolate which change caused what effect**; test **one variable per experiment**.

MongoDB 8.2 expanded `zstdCompressionLevel` to accept values from `-7` to `22`, whereas MongoDB 8.0 accepts `1` to `22`. Never copy negative levels onto unsupported versions. Level `0` also carries special semantics in current docs (using the `zstd` library default rather than MongoDB's default).

### 12.3. Changing Defaults Applies Only to Newly Created Objects

Per MongoDB documentation:

- Changing `storage.wiredTiger.collectionConfig.blockCompressor` on an existing deployment: **new collections** use the new default; **existing collections retain the compressor set at creation**.
- Changing `storage.wiredTiger.indexConfig.prefixCompression`: **new indexes** use the new default; existing indexes do not convert automatically.

Therefore you can never claim "we changed YAML from `snappy` to `zstd`, so all 3 TiB of existing data automatically re-compressed to `zstd`."

To change compression on existing data, plan a migration creating a new collection/index or a MongoDB-supported rebuild workflow, budgeting temporary space and verifying data integrity. Never run `collMod` or `compact` assuming all existing data blocks changed algorithms.

### 12.4. Per-Collection Configuration at Creation Time

On self-managed MongoDB versions supporting storage engine options:

```javascript
const lab = db.getSiblingDB("mongo_perf_row370_lab");

lab.runCommand({
  create: "zstd_example",
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=zstd"
    }
  }
});
```

Depending on managed deployment rules or privileges, this command may be rejected; never use production privileges to bypass service restrictions. Collection-specific options persist in creation metadata rather than retroactively changing existing collections.

**Create `zstd_example` only when certain the namespace does not exist and testing is authorized.** The full lab below uses unique run-scoped names to avoid collisions.

### 12.5. Per-Index `prefixCompression`

WiredTiger supports per-index storage config in supported commands/options. Changing an existing index requires a proper index rebuild rather than tampering with index metadata or system collections.

For critical indexes, benchmark toggling prefix compression only after isolating query-plan or key-pattern changes, guided by evidence.

## 13. Inspect Running Config Rather Than Trusting Old YAML Files

### 13.1. `getCmdLineOpts`

On self-managed `mongod` with appropriate privileges:

```javascript
const result = db.adminCommand({
  getCmdLineOpts: 1
});

printjson({
  parsed: result.parsed?.storage?.wiredTiger,
  journal: result.parsed?.storage?.journal
});
```

This reflects parsed startup options; **missing fields do not mean the feature is disabled**—the server simply uses its built-in defaults. Managed services may restrict this command.

### 13.2. Inspecting Collection Metadata

```javascript
const info = db.getCollectionInfos({
  name: "orders"
});

printjson(
  info.map((x) => ({
    name: x.name,
    options: x.options,
    type: x.type
  }))
);
```

If a collection was created with `storageEngine.wiredTiger.configString`, those options may appear here depending on version. However, not every version exposes the effective compressor cleanly via `getCollectionInfos` alone; cross-check `collStats`, collection metadata, and admin records.

### 13.3. Never Edit Raw Engine Files

Never manually modify:

```text
dbPath/WiredTiger.wt
dbPath/WiredTiger.turtle
dbPath/collection-*.wt
dbPath/index-*.wt
dbPath/journal/WiredTigerLog.*
```

Touching raw engine files corrupts checkpoint recovery and renders databases unbootable. Apply changes strictly through supported admin interfaces with backups and maintenance windows.

## 14. Measuring Storage Usage and Compression Ratios

### 14.1. `dbStats`

```javascript
const s = db.runCommand({
  dbStats: 1
});

printjson({
  db: s.db,
  objects: s.objects,
  dataSize: s.dataSize,
  storageSize: s.storageSize,
  indexSize: s.indexSize,
  totalSize: s.totalSize,
  fsUsedSize: s.fsUsedSize,
  fsTotalSize: s.fsTotalSize
});
```

For an individual collection:

```javascript
const s = db.runCommand({
  collStats: "orders"
});

printjson({
  count: s.count,
  size: s.size,
  storageSize: s.storageSize,
  totalIndexSize: s.totalIndexSize,
  wiredTiger: s.wiredTiger ? "[statistics available]" : null
});
```

Admin tooling can also use `$collStats` or equivalent APIs per version. `collStats` may be restricted in some managed environments; verify permissions and compatibility.

### 14.2. Ratios Are Only Relative Indicators

For a single collection snapshot:

\[
\text{Approx. logical/storage ratio}
=
\frac{\text{size}}{\text{storageSize}}
\]

Example:

```text
Collection logical size: 100 MiB
Collection storageSize:   40 MiB
Ratio:                   2.5
```

However, this is **not a pure compressor benchmark** due to:

- Page fragmentation and internal allocated free space.
- Index bytes excluded from `storageSize`.
- Differences in document counts or field shapes.
- Block compression sensitivity to insert/update ordering.
- Concurrent checkpoint/write activity.
- Metadata and time-series storage semantics.

Use ratios only to **compare trends on standardized datasets**, never as immutable constants or billing guarantees.

### 14.3. Poll `freeStorage` Responsibly

Some versions support:

```javascript
db.runCommand({
  dbStats: 1,
  freeStorage: 1
});
```

Computing `freeStorage` can incur heavy I/O and CPU; never poll it every second on large production databases just for a dashboard. Prefer existing monitoring metrics where available.

## 15. Fair Compression Benchmarking: Design Principles

### 15.1. Ask the Right Question First

Do not ask "Is `zstd` faster than `snappy`?" Ask:

> "For our system's actual documents and query distribution, does switching from `snappy` to `zstd` cut disk cost and improve p95 without breaching CPU SLOs, write latency, or storage budgets?"

Define criteria clearly:

- Dataset: document count, structure, entropy, BSON sizes.
- Read/write mix: 90/10 vs. 10/90.
- Query patterns: point lookups, range scans, aggregations.
- Identical indexes.
- Compression level, index prefix compression, journal settings.
- Hardware: CPU cores, RAM, storage tier, IOPS, throughput.
- Concurrency: clients/threads, connection pooling.
- Duration, warm-up, cold/warm cache states.
- Errors, throttling, replication, failovers.
- Metrics: p50/p95/p99, throughput, CPU, disk, `storageSize`.

### 15.2. Never Change Multiple Variables

Do not compare:

```text
A: snappy, 8 GiB RAM, HDD, no index
B: zstd, 32 GiB RAM, NVMe, with index
```

and declare "`zstd` is 10× faster." Control variables and run repeated trials to avoid warm-cache, compaction, or noisy-neighbor artifacts.

### 15.3. Separate Two Experiments

**Storage compression experiment:**

- Insert the exact same dataset.
- Identical indexes and storage layout.
- Wait for steady post-load/checkpoint state.
- Measure `storageSize`, `indexSize`, and raw dataset size.
- Compare CPU and bytes processed during inserts.

**Application performance experiment:**

- Run representative read/write queries.
- Hold concurrency and dataset identical.
- Compare QPS, p95/p99, and errors.
- Compare disk IOPS, `await`, and queue depth.
- Compare journal/checkpoint metrics and replication lag.

A compressor with a high compression ratio can still hurt application latency if CPU or query execution is the bottleneck.

### 15.4. Measure Checkpoint and Journal Impact Separately

When changing the block compressor, measure **checkpoint/data-file writes** separately from the journal. When changing the journal compressor, measure **journal write/sync bytes and times** and durability latency.

Stronger block compression does not necessarily reduce journal sync calls. Journal compression and collection block compression are distinct; keep the two experiments separate so results stay interpretable.

## 16. Mini `mongosh` Lab: Comparing `snappy` and `zstd`

### 16.1. Prerequisites and Scope

Run this lab only on a **self-managed test MongoDB deployment supporting `storageEngine.wiredTiger.configString`**, with collection creation permissions. If Atlas or a managed tier disallows collection-specific storage options, **skip creating custom-compressed collections** and focus on inspecting `serverStatus` and `dbStats`.

Never:

- Modify production startup YAML.
- Restart `mongod`.
- Disable journaling or delete journal files.
- Generate gigabytes of data trying to induce I/O pressure.
- Touch namespaces outside the lab.
- Run `dropDatabase()` on a shared database.

### 16.2. Generate Unique Collection Names per Run

```javascript
const lab = db.getSiblingDB("mongo_perf_row370_lab");
const runId = "row370-" + new ObjectId().toHexString();

const collSnappyName =
  "sample_snappy_" + runId.replace(/-/g, "_");
const collZstdName =
  "sample_zstd_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(collSnappyName) ||
    lab.getCollectionNames().includes(collZstdName)) {
  throw new Error("Duplicate namespace; will not overwrite.");
}

printjson({
  database: lab.getName(),
  runId,
  collSnappyName,
  collZstdName
});
```

### 16.3. Create Collections with Different Compressors

```javascript
const snappyResult = lab.runCommand({
  create: collSnappyName,
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=snappy"
    }
  }
});

const zstdResult = lab.runCommand({
  create: collZstdName,
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=zstd"
    }
  }
});

printjson({ snappyResult, zstdResult });

if (!snappyResult.ok || !zstdResult.ok) {
  throw new Error(
    "Missing support/permission: stopping lab, do not test on prod."
  );
}

const snappy = lab.getCollection(collSnappyName);
const zstd = lab.getCollection(collZstdName);
```

If `create` fails in your environment, never blindly run `drop()` to "clean up." First verify which namespaces exist and who owns them. Do not proceed with inserts unless both collections exist.

### 16.4. Repetitive Yet Distinct Sample Data

```javascript
const template =
  "Demo document with repetitive content to compare block " +
  "compression on a MongoDB dataset; contains no PII. ";

const docs = Array.from({ length: 1500 }, (_, i) => ({
  _id: new ObjectId(),
  runId,
  code: "ROW370-" + String(i).padStart(5, "0"),
  category: "demo-" + (i % 7),
  status: i % 4 === 0 ? "INACTIVE" : "ACTIVE",
  value: i * 17,
  description: template.repeat(12),
  tags: ["mongodb", "wiredtiger", "compression"],
  createdAt: new Date("2026-11-14T00:00:00Z")
}));

const snappyWrite = snappy.insertMany(docs);
const zstdWrite = zstd.insertMany(docs);

printjson({
  runId,
  snappyInserted: Object.keys(snappyWrite.insertedIds).length,
  zstdInserted: Object.keys(zstdWrite.insertedIds).length
});
```

Both collections receive **identical document IDs and payloads**, yet this is not a production benchmark. The corpus is intentionally compressible; low-repetition JSON/BSON, pre-compressed blobs, or ciphertext behave differently.

### 16.5. Create Identical Indexes on Both Collections

```javascript
for (const coll of [snappy, zstd]) {
  coll.createIndex(
    { runId: 1, category: 1, value: -1 },
    { name: "run_category_value" }
  );
}
```

Matching indexes reduce bias in data storage comparisons. Still, index bytes are tracked separately, and physical block placement, caching, and fragmentation will never be 100% identical.

### 16.6. Inspect Statistics for Both Collections

```javascript
function storageSummary(name) {
  const stats = lab.runCommand({
    collStats: name
  });

  return {
    collection: name,
    count: stats.count,
    logicalBytes: stats.size,
    storageBytes: stats.storageSize,
    indexBytes: stats.totalIndexSize,
    approximateLogicalStorageRatio:
      Number(stats.storageSize) > 0
        ? Number(stats.size) / Number(stats.storageSize)
        : null
  };
}

printjson([
  storageSummary(collSnappyName),
  storageSummary(collZstdName)
]);
```

Notes:

- 1,500 documents is far too small to extrapolate production p99.
- Storage allocation uses block granularity/overhead, making ratios noisy on tiny datasets.
- Never compare raw lab numbers directly against production collections with active updates.
- Run repeated trials on staging with representative data and steady state.

### 16.7. Simple Query Comparison

```javascript
const filter = {
  runId,
  category: "demo-3"
};

for (const coll of [snappy, zstd]) {
  const result = coll.find(filter)
    .sort({ value: -1 })
    .limit(10)
    .explain("executionStats");

  printjson({
    collection: coll.getName(),
    nReturned: result.executionStats?.nReturned,
    docsExamined:
      result.executionStats?.totalDocsExamined,
    keysExamined:
      result.executionStats?.totalKeysExamined,
    executionTimeMillis:
      result.executionStats?.executionTimeMillis
  });
}
```

**Never use a single `explain()` call to claim one compressor is faster.** This 1,500-doc query merely illustrates reading index and execution stats.

### 16.8. Cleaning Up Demo Data by `runId` and `_id`

Before deleting:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
print("collections=" + collSnappyName + ", " + collZstdName);

for (const coll of [snappy, zstd]) {
  printjson({
    collection: coll.getName(),
    ownedCount: coll.countDocuments({ runId })
  });
}
```

Once you have verified both collections and your exact `runId`:

```javascript
for (const coll of [snappy, zstd]) {
  const ownIds = coll.find(
    { runId },
    { _id: 1, runId: 1 }
  ).toArray();

  for (const item of ownIds) {
    coll.deleteOne({
      _id: item._id,
      runId
    });
  }

  printjson({
    collection: coll.getName(),
    remainingOwnedDocs: coll.countDocuments({ runId })
  });
}
```

Empty collections and indexes remain after deleting documents. In a dedicated lab, an admin can drop those specific namespaces **after verifying ownership**—never run `dropDatabase()` or drop collections indiscriminately in a shared database.

**Note:** Deleting documents removes the corpus for further tests. Complete any warm-up or checkpoint measurements before cleaning up.

## 17. Holistic Monitoring for Disk, Journal, and Checkpoints

### 17.1. A Useful Dashboard Layout

```text
+-----------------------------+----------------------------+
| API write p95 / p99         | MongoDB write latency      |
+-----------------------------+----------------------------+
| Host CPU / process CPU      | Read/write IOPS            |
+-----------------------------+----------------------------+
| Disk throughput MiB/s       | Disk r_await / w_await     |
+-----------------------------+----------------------------+
| Disk queue / burst credits  | Disk free + growth         |
+-----------------------------+----------------------------+
| WT dirty bytes / cache max  | WT page in / eviction      |
+-----------------------------+----------------------------+
| WT journal bytes/s          | WT journal sync time       |
+-----------------------------+----------------------------+
| Checkpoint duration         | Checkpoint write bytes/s   |
+-----------------------------+----------------------------+
| Replication lag             | Flow control/commit delay  |
+-----------------------------+----------------------------+
```

On Atlas, metric names and availability differ from self-managed `serverStatus`. Never hardcode a name like `checkpointP99` assuming Atlas exposes it.

### 17.2. Custom Application/Monitoring Metric Names

Example **suggested** metric names (not MongoDB standards):

```text
mongo_disk_read_iops
mongo_disk_write_iops
mongo_disk_read_latency_seconds
mongo_disk_write_latency_seconds
mongo_disk_queue_depth
mongo_disk_free_bytes
mongo_wt_dirty_cache_ratio
mongo_wt_journal_bytes_per_second
mongo_wt_journal_syncs_per_second
mongo_wt_journal_sync_avg_seconds
mongo_wt_checkpoint_duration_seconds
mongo_app_write_latency_seconds
mongo_replication_lag_seconds
mongo_storage_compression_config_info
```

For cumulative counters, export raw counters and compute rates in the time-series backend while handling counter resets cleanly.

### 17.3. Alerts Should Correlate Multiple Signals

| Alert | Correlated Signals |
| --- | --- |
| Storage write pressure | `w_await`/queue climbs, near IOPS quota, API write latency rises |
| Journal fsync pressure | Sync time/count rises, write concern p95 climbs, device latency rises |
| Checkpoint pressure | Recent/max checkpoint time climbs alongside dirty bytes and disk writes |
| Disk full risk | Low free bytes + high growth rate + insufficient journal/oplog headroom |
| Compression CPU pressure | CPU climbs after compressor change + throughput/p99 drops |
| Unexpected storage growth | `storageSize`/`indexSize`/journal/oplog grows past baseline |
| Replication I/O bottleneck | Secondary disk latency rises + replication lag and majority latency climb |

A high dirty cache ratio, checkpoint duration, or journal bytes/sec alone is never conclusive root-cause proof.

## 18. Real-World Investigation Scenarios

### 18.1. Scenario A — Write p99 Spikes, Slow Journal Syncs

```text
API write p99: 50 -> 600 ms
Journal sync avg: 8x higher
Disk w_await: 2 -> 45 ms
Disk queue: growing
CPU: spare capacity
```

Hypothesis: storage write/`fsync` cannot keep up.

Steps:

1. Check provisioned IOPS/throughput and cloud burst credits.
2. Check for backups, snapshots, bulk writes, or index builds.
3. Inspect dirty cache/eviction and checkpoints.
4. Check replication lag and write concern.
5. Throttle non-urgent bursts or increase provisioned I/O capacity as authorized.
6. Verify p99, sync times, and disk queue recover.

**Never flip `j: true` to `false` just to "make latency look good"**—that alters durability guarantees.

### 18.2. Scenario B — Checkpoint Duration Jumps After Bulk Import

```text
Import rate: 5x
WT dirty bytes: rising
Checkpoint recent time: rising
Disk write throughput: near limit
Write p95: rising
```

Root cause is likely increased write load hitting storage ceilings—not a checkpoint bug.

Actions:

- Batch and throttle data imports.
- Eliminate unneeded indexes in the design (never drop prod indexes arbitrarily).
- Check disk capacity and cost.
- Run imports during maintenance windows or provision higher throughput.
- Ensure replicas keep pace.

### 18.3. Scenario C — High Read I/O Despite Compression Enabled

```text
snappy enabled
WT page reads/s: surging
Disk r_await: rising
Queries scanned docs: rising
```

Do not jump to "switching to `zstd` will fix everything." Inspect indexes, query plans, working set, OS cache, and access patterns. Stronger compression only helps when disk bytes and cache efficiency are the bottleneck; `COLLSCAN` remains a far bigger problem.

### 18.4. Scenario D — Compressor Change Saves Space but Spikes CPU

```text
Data storage: -30%
Process CPU: +25%
Write p95: +40%
Disk queue: stable
```

The workload is likely **CPU-bound** and the `zstd` level is too aggressive. Re-test with `snappy` or a lower `zstd` level in staging. Pick based on cost and latency SLOs, not disk size alone.

### 18.5. Scenario E — Disk Full Even Though `dbStats.totalSize` Barely Grew

Hidden growth sources:

- Oplog.
- Journal headroom during stalled checkpoints/recovery.
- WiredTiger history store.
- Temporary files during index builds or aggregation spills.
- Backups or log files sharing the same filesystem.
- Docker/container overlay logs.
- Data/index allocation fragmentation.

Inspect `df`, filesystem directories or managed dashboards, and MongoDB stats. **Never manually delete journal, oplog, or `WiredTigerHS.wt`.** Running out of journal space can crash `mongod`; expand volume headroom, throttle writes, and follow runbooks.

### 18.6. Scenario F — Slow Secondary Disk Drives Majority Write Latency

```text
Primary CPU: 50%
Primary disk: stable
Secondary disk w_await: high
Replication lag: rising
Majority write latency: rising
```

The bottleneck lies in secondary apply/flush or flow control—not solely on the primary. Inspect **every replica member**, alongside read preference and replication config.

## 19. Storage Incident Runbook

### 19.1. Define Scope

Record:

- Cluster/replica set, primary/secondaries, version/FCV.
- Time window and timezone.
- Affected API operations.
- Recent changes: deploys, index builds, backups, maintenance.
- CPU, RAM, disk, journal, checkpoint, and replication metrics.
- Volume type, limits, and cloud provider.
- Current compression configs on affected collections.

### 19.2. Gather Evidence Safely

On MongoDB:

```javascript
const s = db.serverStatus();

printjson({
  uptime: s.uptime,
  wtCache: {
    current: s.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
    max: s.wiredTiger?.cache?.[
      "maximum bytes configured"
    ],
    dirty: s.wiredTiger?.cache?.[
      "tracked dirty bytes in the cache"
    ]
  },
  journal: {
    bytes: s.wiredTiger?.log?.["log bytes written"],
    syncs: s.wiredTiger?.log?.["log sync operations"]
  },
  checkpoint: s.wiredTiger?.checkpoint
});
```

On Linux:

```bash
iostat -xz 1 5
free -h
vmstat 1 5
df -h
```

These commands are primarily **read-only** and lightweight. Avoid heavy `du -sh /path` or recursive `find` scans on production storage during peak hours if telemetry already tracks usage; scanning huge filesystems adds I/O.

### 19.3. Identify the Bottleneck Layer

```text
CPU-bound?
  -> query plan / aggregation / compressor CPU

Memory/cache-bound?
  -> working set / eviction / long transactions

Disk-bound?
  -> IOPS / MiB/s / latency / queue / volume throttle

Journal-bound?
  -> fsync timing / write concern / storage latency

Checkpoint pressure?
  -> dirty bytes / write burst / history / device

Replication-bound?
  -> secondary lag / oplog apply / flow control
```

### 19.4. Risk-Ordered Mitigations

Lowest-risk actions first:

1. Throttle non-urgent batch jobs, exports, and imports.
2. Stop runaway I/O-heavy queries under change control.
3. Scale up cloud volume provisioned IOPS/throughput if supported online.
4. Expand storage capacity/headroom per DBA procedures.
5. Tune queries, indexes, and workloads with monitored rollouts.
6. Evaluate compressor or cluster resizing after benchmarking.

Never do under incident pressure without a vetted plan:

- Disable journaling.
- Delete WiredTiger metadata or journal files.
- Drop oplog or indexes arbitrarily.
- Downgrade write concern cluster-wide.
- Copy live data files outside supported backup protocols.
- Repeatedly restart nodes, wiping warm caches and triggering failovers.
- Run `compact`/`repairDatabase` purely to "shrink disk used."

### 19.5. Verify After Changes

Compare before/after:

- Latency p95/p99 and error rates.
- QPS and completed throughput.
- Journal sync average latency and syncs/s.
- Checkpoint durations and trends.
- Disk read/write `await`, queue depth, IOPS, and MiB/s.
- Dirty cache ratio and eviction rates.
- Replication lag and free disk capacity.

Confirm mitigation worked only when both **user-facing** and **storage** metrics improve sustainably under equivalent load.

## 20. Capacity Planning for Journal, Checkpoints, and Compression

### 20.1. Do Not Buy Storage Sized Solely to `dataSize`

An illustrative capacity calculation:

```text
Allocated collections:        400 GiB
Allocated indexes:            100 GiB
Oplog/history/logs reserve:    80 GiB
Journal/recovery headroom:     40 GiB
Expected 60-day growth:      180 GiB
Operational safety reserve:  160 GiB
------------------------------------
Capacity target:             960 GiB
```

Safety buffers vary by backup location, index rebuilds, traffic bursts, and cloud volume sizes. Never treat 960 GiB as a universal template.

### 20.2. The Journal Is Not Permanently Fixed in Size

WiredTiger manages journal files needed for checkpoint recovery. Documentation notes each journal file is roughly **100 MB** alongside factors like checkpoint size, compression, recovery time, and preallocation.

Never configure quotas assuming "the journal stays under 100 MB total." ~100 MB is the limit per **individual journal file**, **not a 100 MB ceiling for the entire journal directory**.

### 20.3. Forecasting by Growth Rate

\[
\text{Time to full}
\approx
\frac{\text{Free disk bytes}}
{\text{Net growth bytes per unit time}}
\]

Use this only as a rough approximation when net growth is positive and steady. Storage can jump abruptly during index builds, imports, long transactions, or traffic campaigns—always keep headroom and early alerts.

### 20.4. Failover Capacity

Any eligible secondary can become the primary; provision sufficient CPU, disk IOPS, and write bandwidth on every primary-eligible member.

A sluggish secondary also slows majority write concern and increases replication lag. Never size an entire replica set based solely on normal-state primary load.

## 21. Rolling Out Compression Changes Safely

### 21.1. Recommended Workflow

```text
Baseline metrics & SLO
          |
          v
Hypothesis: CPU vs I/O vs capacity
          |
          v
Staging corpus + query replay
          |
          v
A/B compressors, one variable at a time
          |
          v
Measure size, latency, CPU, disk, journal
          |
          v
Decide migration strategy
          |
          v
Canary / isolated new collection
          |
          v
Validate data and business queries
          |
          v
Cutover with rollback path
          |
          v
Monitor several workload cycles
```

### 21.2. Migrating an Existing Collection

Because changing default `blockCompressor` leaves existing collections untouched, a migration must cover:

- Creating a new collection with the desired compressor.
- Copying documents via supported tools/apps while preserving BSON types.
- Creating indexes with exact definitions and ordering.
- Verifying uniqueness, collations, schema validation rules, and TTLs.
- Handling concurrent writes via managed sync/cutover (quiesce or Change Streams).
- Running count/hash/application-level validation.
- Updating namespace references, read/write clients, and batch jobs cleanly.
- Ensuring valid backups and rollback paths.
- Never changing `_id` or document shape purely for better compression ratios.
- Provisioning temporary disk headroom for **two copies of the collection + indexes + oplog/journal**.

Never run `renameCollection` or `drop` in production under the excuse of "just changing compression" without a strict read/write consistency plan.

### 21.3. Rollback

Compression changes are not always reverted by editing one YAML line:

- Existing collections created with `zstd` stay `zstd` even after resetting the default back to `snappy`.
- Migrated data needs a cutback plan or read-only source retention.
- Journal compression operates at the engine/startup level with its own rollout procedure.
- Existing indexes do not revert prefix compression when changing defaults.

A rollback plan must address **data state, configuration, application routing, and backups**, not just a YAML snippet.

## 22. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| "CPU has headroom, so disk cannot be the bottleneck" | Misses I/O stalls | Inspect queue, `await`, IOPS, throughput |
| "A 1 TiB disk is always faster than 500 GiB" | IOPS quota may be identical | Check volume provisioned limits |
| "`%util=100%` always means max NVMe saturation" | Overly simplistic diagnosis | Check latency, queue, parallel I/O |
| "A write equals one disk write" | Ignores indexes/journal/checkpoints | Account for write amplification |
| "The journal is `mongod.log`" | Risk deleting recovery WAL files | Separate diagnostic logs from WAL |
| "Disable journal to boost TPS" | Data loss risk and removed in 6.1+ | Keep journal; fix root bottleneck |
| "Journal syncs strictly every 100 ms" | Wrong with `j: true`, secondaries, rotation | Understand all sync triggers |
| "`w: 1` and `w: majority, j: true` are equivalent" | Breaks durability/failover contract | Match write concern to business rules |
| "Write concern timeout = nothing was written" | Causes duplicate inserts | Use idempotency and verification |
| "Checkpoints always finish in 60s" | Misdiagnoses write spikes | Measure actual checkpoint durations |
| "No new checkpoint means recent writes are lost" | Ignores journal recovery | Understand checkpoint + journal recovery |
| "A checkpoint is a backup" | Cannot restore safely from live files | Use supported backups/snapshots |
| "High dirty cache means the journal isn't durable" | Confuses two mechanisms | Track journal and dirty pages separately |
| "100 MB journal file means max 100 MB total journal" | Runs out of disk headroom | Account for multiple files and preallocation |
| "Stronger compression is always faster" | CPU can become the bottleneck | Benchmark target workload |
| "`zstd` on ZIP files saves massive space" | Pre-compressed data barely shrinks | Inspect data entropy first |
| "Block compression and journal compression are the same" | Misinterprets config impact | Separate collection vs. engine config |
| "Index `prefixCompression` is `snappy` for indexes" | Wrong mental model | Understand prefix deduplication |
| "Changing default to `zstd` re-compresses old collections" | Wrong capacity forecast | Plan explicit migration/rebuild |
| "`dataSize` equals physical disk bytes" | Mis-sizes storage | Check `storageSize`, `indexSize`, filesystem |
| "Deleting docs immediately frees OS disk space" | Misreads storage stability | WiredTiger reuses freed space internally |
| "One `explain()` run proves everything" | Skewed by cache/load | Benchmark with warm-up and repetitions |
| "`log bytes written` is journal directory size" | Confuses cumulative counter with gauge | Compute per-process rate/delta |
| "No need for backup KMS or replication" | Severe recovery risk | Test backups, restores, and replication |
| "Deleting `WiredTigerLog.*` manually is safe" | Breaks crash recovery | Never tamper with engine files |
| "Every Atlas tier allows changing compressors" | Permission/feature errors | Follow deployment tier docs |
| "The profiler alone diagnoses storage" | Misses OS/cloud telemetry | Correlate all 4 telemetry layers |
| "Expanding disk capacity always adds IOPS" | May leave IOPS unchanged | Provision each limit explicitly |

## 23. Self-Practice Exercises

### Exercise A — I/O Diagnostics

A node shows:

```text
CPU used:            45%
Disk write IOPS:     near 100% quota
w_await:             3 -> 55 ms
Disk queue:          rising sharply
Write p99:           80 -> 600 ms
```

1. What evidence supports a disk bottleneck?
2. Why would adding CPU likely fail to help?
3. If backups run on the same volume, what should you inspect?
4. Propose a low-risk mitigation.

### Exercise B — Journal and Checkpoints

Order these events:

```text
Checkpoint A completes
Write X becomes journal-durable
Write Y becomes journal-durable
Process crashes before Checkpoint B
Process restarts
```

Explain how X and Y are recovered from the journal. What can happen if a write was not yet journal-synced per its write concern?

### Exercise C — Write Concern

Compare:

```javascript
{ w: 1 }
{ w: 1, j: true }
{ w: "majority" }
{ w: "majority", j: true, wtimeout: 10000 }
```

Explain durability, failover safety, latency trade-offs, and the role of `writeConcernMajorityJournalDefault`.

### Exercise D — Journal Metrics

Suppose:

```text
T1: log bytes written = 2,000,000,000
T2: log bytes written = 2,600,000,000
Elapsed: 60 seconds

T1: log sync operations = 400,000
T2: log sync operations = 402,400
```

1. Compute journal bytes/sec.
2. Compute syncs/sec.
3. Can you derive p95 `fsync` latency from these?
4. If MongoDB restarted between T1 and T2, how must you handle the calculation?

### Exercise E — Checkpoint Pressure

```text
Checkpoint recent time: 1s -> 35s
Dirty cache bytes: rising
Disk w_await: rising
Bulk import: just started
```

1. What is the likely cause?
2. How do you separate cause from effect?
3. Why should you not blindly tweak the checkpoint interval?
4. Pick metrics to verify improvement after throttling the bulk import.

### Exercise F — Compression Trade-Offs

Two environments run the same corpus:

```text
Snappy storage:  150 GiB
Zstd storage:     95 GiB
Snappy CPU:       55%
Zstd CPU:         80%
Snappy p95 write: 35 ms
Zstd p95 write:   52 ms
```

If the write p95 SLO is 45 ms, should you immediately switch all traffic to `zstd`? What adjustments or cost/SLO trade-offs should be evaluated?

### Exercise G — `dataSize` vs. Disk

```text
dataSize:        300 GiB
storageSize:     180 GiB
indexSize:        50 GiB
Filesystem used: 280 GiB
```

1. Why can `dataSize` exceed `storageSize`?
2. What is the defined `totalSize` of data/indexes?
3. Where can the extra filesystem usage come from?
4. Why should 280 GiB not be treated as the collection's compression ratio?

### Exercise H — Does Changing Compressor Affect Existing Collections?

A DBA changes `blockCompressor` from `snappy` to `zstd` in startup YAML.

1. Do previously created collections switch compressors right away?
2. How are newly created collections affected?
3. What plan is required to re-encode existing data?
4. How much temporary storage headroom is needed when holding two copies during migration?

### Exercise I — Compressing High-Entropy Data

A collection holds mostly:

- JPEG images.
- Base64-encoded ZIP archives.
- Encrypted application blobs.

1. Why does block compression save very little here?
2. Should `none` be benchmarked?
3. How should CPU, `storageSize`, disk I/O, and p99 be measured?
4. When are GridFS or object storage better fits?

### Exercise J — Primary vs. Secondary

Primary disk `await` is normal, while secondary disk write `await` climbs alongside replication lag and majority write latency.

1. Which node likely holds the bottleneck?
2. Which metrics should be collected across members?
3. Will changing journal compression only on the primary guarantee better results?
4. How should failover capacity be planned?

### Exercise K — Journal Disk Full

A node is nearly out of disk while collection `dataSize` barely grew. The journal directory, oplog, and temporary files are active.

1. Which measurements should be gathered first?
2. Why must you never manually delete `WiredTigerLog.*`?
3. Why is journal headroom essential in capacity planning?
4. Outline a safe runbook remediation.

### Exercise L — Designing a Benchmark

Plan an A/B `snappy` vs. `zstd` benchmark for a service with:

- 80% reads, 20% writes.
- Identical 2 million documents with repetitive strings plus some binary fields.
- p99 target under 100 ms.
- ~25% CPU headroom.
- Cloud volume with IOPS caps.

Specify dataset design, control variables, warm/cold cache handling, metrics, repetition count, canary rollout, and rollback.

## 24. Official References

Configuration behavior depends on MongoDB server version, storage engine, managed environment, and deployment topology. Authoritative sources:

- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — checkpoints, journaling, block compression, and prefix compression.
- [Journaling](https://www.mongodb.com/docs/manual/core/journaling/) — write-ahead logging, sync intervals, files, and crash recovery.
- [Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/) — `journalCompressor`, `blockCompressor`, `prefixCompression`, `zstdCompressionLevel`, and `commitIntervalMs`.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, majority durability, and timeouts.
- [`serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — `wiredTiger.log`, `checkpoint`, cache, and transaction counters.
- [`dbStats`](https://www.mongodb.com/docs/manual/reference/command/dbStats/) — logical data, allocated collection/index storage, and filesystem metrics.
- [`collStats`](https://www.mongodb.com/docs/manual/reference/command/collStats/) — per-collection storage allocation, indexes, and WiredTiger stats.
- [`create` command: Storage Engine Options](https://www.mongodb.com/docs/manual/reference/command/create/) — collection-specific WiredTiger `configString`.
- [Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/) — memory, filesystem, and production deployment guidelines.
- [MongoDB Atlas Cluster Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — resource and disk metrics on managed deployments.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — slow queries and profiler overhead.
- [`explain`](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans and execution statistics.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — specialized storage and compression behavior.

**Version note:** Metric names, field layouts, and config parameters evolve across releases; MongoDB 6.1+ enforces always-on journaling, MongoDB 8.2 expands the `zstd` compression level range, and time-series collections default to `zstd` instead of `snappy`. Verify your exact server/FCV, driver, edition, and permissions before making changes.

## 25. Conclusion

Evaluating MongoDB storage performance must trace from **API symptoms** down to **WiredTiger and underlying hardware**:

1. Disk evaluation requires measuring **IOPS, throughput, latency, queue depth, free capacity, and burst quotas**—not capacity alone.
2. The **journal** is the write-ahead log protecting durable writes between checkpoints; it is not a diagnostic log and must never be deleted manually.
3. **Checkpoints** persist consistent states to disk—typically triggered every 60 seconds, with actual duration driven by dirty pages, I/O, and workload.
4. **Write concern** defines when clients receive acknowledgement; `j: true` and `w: "majority"` serve distinct roles.
5. **Collection compression, journal compression, and index prefix compression** are three independent layers with different defaults and scopes.
6. **`snappy`, `zstd`, `zlib`, and `none`** must be chosen via benchmarks on real corpora and queries, balancing storage, CPU, disk I/O, and p95/p99.
7. Changing default compression **never automatically re-compresses existing collections or indexes**. Migrations require backups, temporary space headroom, validation, and rollback plans.
8. During incidents, never disable journaling, tamper with WiredTiger files, or weaken durability reflexively. Collect time-aligned metrics and fix the true bottleneck layer.

**Core principle:** Tuning MongoDB storage is not hunting for one "fastest knob," but proving a configuration **meets application SLOs and durability guarantees at an acceptable resource cost** while keeping data recoverable and operations safe.
