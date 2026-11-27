# Working Sets, Caches, and the Impact of Disk Reads in MongoDB

## 1. The Problem: Why Is the Same Query Sometimes Fast and Sometimes Slow?

Suppose an order application has 40 million documents in the `orders` collection. A query looking up a customer's latest orders sometimes takes 8 ms, yet during peak hours takes 250 ms or more—even though the query text and returned data are nearly identical.

One of the following may be happening:

- The required data or index pages are already resident in memory.
- The query must load pages from disk because they were not recently accessed.
- A background report scanned vast numbers of documents and evicted hot data from cache.
- Required data sits across scattered pages, triggering many random I/O operations.
- Storage throughput/IOPS or the I/O queue is saturated.
- The query lacks a suitable index and reads far more data than necessary.
- Cache is contended among multiple queries, writes, checkpoints, and background tasks.

To understand and resolve these issues, master three concepts:

1. **Working set**: the data and index pages your workload actively needs over a given time window.
2. **Cache**: memory holding recently read or modified pages to avoid reading repeatedly from slower storage.
3. **Disk read**: fetching data absent from cache tiers; latency can climb dramatically when frequent or when storage saturates.

> **Key takeaway:** For MongoDB to stay fast, **the entire database** does not need to fit in RAM. What matters is whether the **most frequently accessed data and index pages** fit inside the cache hierarchy and whether queries read only the amount of data they truly need.

---

## 2. Working Set Is Not Database Size

A database on disk might contain:

```text
orders:      600 GiB
customers:    80 GiB
products:     30 GiB
indexes:     120 GiB
--------------------
Total:       830 GiB
```

Yet actual traffic focuses mostly on:

- Orders from the last 7 days.
- 100,000 active customers.
- Currently active products.
- Index pages used by common filters and sorts.

In that case, the **working set** can be far smaller than 830 GiB. Conversely, an automated dashboard scanning all historical orders every few minutes can blow up the working set.

### 2.1. An Operational Definition

The working set is the collection of **data pages, index pages, and related structures that must stay hot** to serve a workload over a defined time window.

There is no single working-set size valid at all times:

```text
Morning:
  App reads today's orders.
  Working set ~ recent orders + indexes.

Night:
  Reports scan 2 years of history.
  Working set ~ many historical pages.

Sale day:
  Many users browse the same product group.
  Working set shifts with traffic and concurrency.
```

**A collection size stat alone never tells you the working set.** You must combine access patterns, cache counters, I/O, and latency.

### 2.2. The Working Set Includes Indexes

If your application has an index:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

then customer-by-time queries read **index B-tree pages**, plus document pages whenever projected fields are not covered by the index.

Indexes are part of the working set and **compete for memory** with document pages. Creating too many indexes increases cache pressure even if each individual index helps a few queries.

---

## 3. Three Layers to Distinguish: WiredTiger Cache, OS Page Cache, Disk

MongoDB uses **WiredTiger** as its default storage engine in modern versions. A simplified mental model:

```text
                  Query / aggregation / update
                              |
                              v
                  WiredTiger internal cache
                  (in-memory pages/structures)
                              |
                        cache miss / eviction
                              |
                              v
                    Filesystem / OS page cache
                     (file blocks held by OS)
                              |
                         cache miss
                              |
                              v
                       SSD / NVMe / EBS
                    (persistent storage)
```

This diagram is an explanatory model, not a claim that every query executes a strict single pass through every tier.

### 3.1. WiredTiger Internal Cache

- Holds data and index pages to serve queries.
- Manages memory for reads/writes, dirty pages, and eviction.
- Exposes counters for cached bytes, pages read, pages written, and evictions.
- Data in the internal cache is stored in WiredTiger's in-memory representation, which differs from compressed bytes in on-disk files.

### 3.2. OS Filesystem Page Cache

- The operating system caches file blocks read from storage.
- MongoDB benefits when needed blocks remain in the OS page cache even after leaving the WiredTiger internal cache.
- The OS automatically uses most free RAM for file caching.
- Linux reporting high `buff/cache` does not mean "RAM is wasted"; most of it is reclaimable whenever processes need memory.

### 3.3. Persistent Storage

- SSD/NVMe drives or cloud block storage.
- Much higher latency than memory, especially under random I/O and queue saturation.
- Tuned via storage type, IOPS/throughput provisioning, access patterns, and concurrency handling.

**Do not add WiredTiger cache + OS page cache as two independent non-interacting memory pools** without accounting for OS and process overhead. Both share the same host RAM; sizing must account for the whole system.

---

## 4. The Read Path of a Single Document

Suppose:

```javascript
db.orders.findOne({
  _id: "ORD-1001"
});
```

The default `_id_` index exists. The server looks up the key in the index and then retrieves the document.

### 4.1. Hot Data Case

```text
Query
  |
  v
Index page already in WiredTiger cache
  |
  v
Document page already in WiredTiger cache
  |
  v
Return data (no disk read needed for these pages)
```

### 4.2. Hot Index, Cold Document Case

```text
Query
  |
  v
Index page in cache
  |
  v
Document page not in internal cache
  |
  +--> OS page cache still has block: read from OS memory
  |
  +--> OS page cache miss: requires storage I/O
  |
  v
Materialize document and return result
```

### 4.3. Both Index and Document Cold Case

The query may need multiple pages from storage, including upper B-tree levels of the index and the document page. If storage is busy or pages are scattered, latency climbs.

**Do not interpret every `FETCH` in `explain` as a disk read.** `FETCH` simply indicates the query retrieves documents after an index lookup—the documents may already sit in memory.

---

## 5. How Much RAM Is Allocated to WiredTiger Cache by Default?

By default, MongoDB sizes the WiredTiger internal cache using the formula documented as:

```text
max(50% × (RAM - 1 GiB), 256 MiB)
```

For example, on a 16 GiB RAM machine:

```text
RAM:                  16 GiB
RAM - 1 GiB:          15 GiB
50% of remainder:     7.5 GiB

Default WiredTiger cache is approximately 7.5 GiB.
```

This is an **example of the formula**, not a guarantee that every container or platform will report exactly 7.5 GiB; check the effective runtime configuration, allocated cgroup limits, and MongoDB version.

### 5.1. Why Not Allocate All RAM to WiredTiger?

WiredTiger is not the only consumer of RAM:

- OS page cache.
- MongoDB binary code and structures outside the WiredTiger cache.
- Connections and network buffers.
- Intermediate query/aggregation memory.
- Index build memory.
- Journaling and background operations.
- Operating system and monitoring agents.
- Other processes on the same host.

Setting internal cache too large starves the OS page cache and triggers memory pressure.

### 5.2. Configuring `cacheSizeGB`

On self-managed MongoDB:

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 8
```

Or the corresponding startup option:

```bash
mongod --wiredTigerCacheSizeGB 8
```

**Note:** These examples merely illustrate the option; never start a new `mongod` against a production `dbPath` without understanding topology, service configuration, and policies. Changing cache sizing typically requires an instance restart and version verification.

### 5.3. When Should You Not Tune It Manually?

- When the real working set is unknown.
- When eviction/cache metrics have not been measured.
- When I/O is not the bottleneck.
- When other processes on the host compete for RAM.
- When running on a managed tier with its own sizing rules.
- Merely because the cache shows "90% full."

Caches are designed to **be used**; high cache occupancy alone is not a fault.

---

## 6. Do Not Confuse a "Full" Cache with an "Overloaded" Cache

A cache at 90–95% utilization can be completely healthy if:

- Hot pages stay resident steadily.
- Eviction frees cold pages without stalling queries.
- Disk read I/O stays low.
- p95/p99 query latencies are healthy.
- No prolonged eviction queue builds up.

Conversely, a cache at only 70% can still suffer terrible query latency due to:

- Queries scanning unread pages.
- Missing or poorly ordered indexes.
- Heavy random disk I/O.
- A continuously shifting dataset larger than cache.
- Aggregations spilling to disk.
- Volume IOPS hitting provisioned limits.

**Diagnose from multiple correlated signals**, never from a single cache-usage threshold.

---

## 7. Data Pages, Index Pages, and Compression

WiredTiger stores data on disk in pages/blocks and supports data compression.

Distinguish clearly:

- **Logical document size**: uncompressed BSON byte length of a document.
- **Storage size**: physical size of allocated files/blocks, shaped by compression and overhead.
- **In-memory cache footprint**: memory used by pages and structures WiredTiger manages in RAM.
- **Index size**: total index footprint, not guaranteed resident pages in cache.

### 7.1. Do Not Treat `storageSize` as the Working Set

Example:

```text
Collection logical documents: 100 GiB
On-disk compressed storage:   40 GiB
Indexes on disk:             15 GiB

Do not automatically conclude:
  Working set = 55 GiB
```

The working set may be far smaller if only 5% of data is read, or larger than naive estimates if query patterns, update churn, in-memory representations, and concurrency demand more RAM.

### 7.2. Compression Has Both Benefits and Costs

- Reduces bytes read from disk and storage consumption.
- Adds CPU overhead for compression/decompression.
- Does not guarantee internal cache pages shrink at the same ratio as on-disk files.
- Helps I/O-bound workloads by cutting physical bytes transferred.
- Can become a measurable factor to benchmark on CPU-bound workloads.

Do not disable compression to "make cache faster" without measuring throughput, CPU, disk latency, and volume capacity.

---

## 8. Hot Set, Warm Set, and Cold Set

A practical classification:

| Tier | Characteristics | Handling Strategy |
| --- | --- | --- |
| **Hot** | Repeatedly accessed at high frequency | Prioritize optimal indexes/queries and cache residence |
| **Warm** | Accessed periodically rather than constantly | Rely on OS page cache and schedule background jobs |
| **Cold** | Historical data rarely queried | Archive/tiered storage or isolated queries |

Application example:

```text
Hot:
  orders last 24 hours
  active customers
  current product catalog

Warm:
  last month's invoices
  support case history

Cold:
  orders older than 5 years
  deactivated users' historical metadata
```

Cold data does not mean deletable data. Archiving and retention policies must preserve business integrity and legal compliance.

### 8.1. A Hot Query Can Drag Cold Pages into Cache

A seemingly common query without an index:

```javascript
db.orders.find({
  status: "PENDING"
});
```

Even if only 1% of orders are `PENDING`, without a suitable index the query scans nearly the entire collection, pulling cold pages into cache.

Therefore **working-set tuning must start with access paths**, not merely classifying records by age.

---

## 9. Measuring the Hot Dataset by Read Behavior, Not Just Size

A practical workflow:

1. Collect top queries by request count and latency.
2. Identify filter, sort, and projection fields.
3. Inspect indexes and query plans for those query patterns.
4. Determine the data ranges frequently accessed (time windows, tenants, categories).
5. Observe WiredTiger pages read/evicted over time.
6. Observe disk read IOPS, throughput, and latency.
7. Compare p50/p95/p99 latency between normal hours and peak hours.
8. Run simulated load on staging with production-like data distributions.
9. Evaluate the percentage of requests served while hot pages stay resident.

MongoDB has no universal command that prints "exact total working set bytes across all queries for 7 days." Sizing is typically **estimated and inferred from multiple correlated metrics**.

### 9.1. Observing Hourly Shifts

```text
09:00–11:00  Heavy web traffic, focused working set.
12:00–12:30  Batch product import.
13:00–16:00  Web traffic resumes.
01:00–04:00  Analytics scans full history.
```

If analytics spikes cache evictions and web traffic remains slow afterward even once the batch finishes, that is a strong signal of **cache pollution** worth investigating.

---

## 10. What Do Cache Hit and Cache Miss Really Mean?

**Cache hit**: required data is already present in the cache tier being examined.

**Cache miss**: required data is absent from that cache tier and must be fetched from a lower tier.

### 10.1. A Miss in WiredTiger Does Not Automatically Mean a Disk Read

```text
WiredTiger cache miss
       |
       +--> OS page cache hit
       |      still reads from memory, not physical disk I/O
       |
       +--> OS page cache miss
              -> persistent storage read
```

A counter of "pages read into WiredTiger cache" **is not proof** that every page triggered disk I/O—many blocks may be served directly from the OS page cache.

### 10.2. Interpret OS Page Faults Properly

- **Minor page faults** generally do not require physical disk I/O.
- **Major page faults** typically correspond to reading from storage.
- Page fault counters do not map 1:1 to total MongoDB logical reads.
- Containers, cgroups, and filesystems may expose different metrics or semantics.

Do not see rising page faults and immediately declare "MongoDB is thrashing disk" without checking disk read IOPS and latency.

### 10.3. Cache Hit Rate Is Not the Only Metric

You can have a 99% hit rate yet the 1% misses fall on a critical user endpoint and ruin p99 latency. Conversely, a 90% hit rate during sequential batch scans may be completely acceptable.

What matters is **the real latency cost of misses and business SLOs**.

---

## 11. Eviction: When WiredTiger Needs Room for Other Pages

**Eviction** is the process of removing less-needed pages from the internal cache to make room for other pages.

```text
WT cache:
  hot A | hot B | cold C | cold D

New query needs E:
  evict cold C
  load E

WT cache:
  hot A | hot B | new E  | cold D
```

This is normal operation.

### 11.1. When Eviction Becomes a Problem

- Cache lacks enough space for the actively reused page set.
- Queries scan vast data volumes, evicting freshly loaded pages right away.
- Too many dirty pages must be reconciled/written before eviction can proceed.
- Application threads are forced to perform eviction themselves, hurting latency.
- Disk writes/checkpoints cannot keep up.
- Cache churn rises in lockstep with p95/p99 latency.

### 11.2. Dirty Pages

A page modified in memory whose changes have not yet been flushed to the corresponding data files on disk is a **dirty page**.

Do not confuse dirty pages with "writes lacking durability":

- MongoDB/WiredTiger handles journaling, write concern, replication, and checkpoints via dedicated mechanisms.
- Write durability is not solely determined by whether a data page has been checkpointed to collection files yet.
- Majority write concern and journal policies must still be evaluated separately.

### 11.3. Dirty Cache Pressure and Background Writes

When dirty pages accumulate, checkpoints and eviction can trigger disk write bursts. On storage volumes sharing read and write IOPS, write bursts can raise read latency even while read query volume is unchanged.

---

## 12. Checkpoints, Journal, and Disk I/O

WiredTiger generates I/O from multiple sources:

| Source | Why It Occurs |
| --- | --- |
| Read cache miss | Data/index page is not resident |
| Eviction / writeback | Flushing modified pages to storage |
| Checkpoint | Persisting a consistent point-in-time state on disk |
| Journal | Recording write-ahead logs for crash recovery/durability |
| Index build | Reading data and writing new index structures |
| Aggregation spill | Writing/reading temporary spill files |
| Backup / restore | Reading/writing large data volumes |
| Compaction | Rewriting/defragmenting storage on command |
| Initial sync | Copying full data and indexes to a member |

### 12.1. Rising Reads Can Come from Non-User Activity

Examples:

- A backup agent scanning data files.
- An index build scanning a collection.
- An analytics/reporting batch reading cold documents.
- Integrity verification scans.
- Restore or initial sync reading from a source member.

When Disk Read IOPS rises, always inspect the **timeline of background operations**, not just web traffic.

### 12.2. Never Disable the Journal or Lower Write Concern to "Save Cache"

Doing so weakens durability and consistency guarantees and risks data loss on failure. They do not fix queries scanning too many pages.

---

## 13. Random Disk Reads vs. Sequential Reads

Two queries both reading 1 GiB can have very different durations.

### 13.1. Sequential Scans

Queries reading contiguous blocks relatively sequentially:

```text
Block 1 -> Block 2 -> Block 3 -> ... -> Block N
```

Storage and the OS can leverage throughput and read-ahead optimizations in many cases.

### 13.2. Random Reads

Queries fetching many scattered documents:

```text
Block 1023 -> Block 7 -> Block 90051 -> Block 231 -> ...
```

Random reads are constrained primarily by IOPS and per-op latency rather than MB/s throughput.

### 13.3. Impact of Indexes

A selective index cuts the number of document pages read, yet a query retrieving hundreds of thousands of scattered documents via an index can trigger more random fetches than a sequential scan. The query planner may choose `COLLSCAN` when beneficial.

Hence **`IXSCAN` does not automatically mean faster than `COLLSCAN`**. Check selectivity and test empirically.

---

## 14. Disk IOPS, Throughput, Latency, and Queue Depth

Four metrics often mentioned together with distinct meanings:

| Metric | Unit | Meaning |
| --- | --- | --- |
| **IOPS** | Operations/s | Number of I/O operations completed per second |
| **Throughput** | MiB/s | Bytes read/written per second |
| **Latency** | ms/op | Time for each I/O operation to complete |
| **Queue depth** | Pending ops | Number of queued or in-flight I/O requests |

### 14.1. Illustrative Calculation

If a volume processes 10,000 reads/s averaging 4 KiB per read:

```text
Throughput ≈ 10000 × 4 KiB/s
           ≈ 39.1 MiB/s
```

If each I/O averages 256 KiB:

```text
Throughput ≈ 10000 × 256 KiB/s
           ≈ 2500 MiB/s
```

These are theoretical illustrations. Real volumes enforce distinct IOPS, throughput, and I/O-size ceilings.

### 14.2. Why Does Latency Climb Non-Linearly Near Saturation?

As I/O demand approaches or exceeds capacity, queues grow. A read taking ~1 ms under light load can take many milliseconds waiting in queue.

Application latency reflects all layers:

```text
Request latency
  ≈ query planning/execution CPU
  + cache misses / storage wait
  + lock/resource contention
  + server-to-client transfer
  + application/network overhead
```

Never map Disk I/O latency 1:1 onto total query latency blindly.

---

## 15. Why Do SSD/NVMe Drives Matter So Much for MongoDB?

MongoDB document and index workloads often generate substantial random I/O.

Compared to mechanical HDDs, SSD/NVMe typically offers:

- Much lower random read latency.
- Better concurrent I/O handling.
- Far higher IOPS.
- No mechanical seek penalties.

In cloud environments, SSD-backed volumes can still be capped by:

- Provisioned IOPS.
- Provisioned throughput.
- Burst credits.
- Network-attached storage bandwidth.
- Instance-level I/O limits.
- Shared infrastructure contention.

### 15.1. Upgrading Disk Does Not Fix Bad Queries

If a query scans 10 million documents due to a missing index, moving from HDD to NVMe speeds up each I/O yet still reads way too much data.

Typical priority order:

1. Fix the access pattern / query.
2. Add an appropriate index.
3. Reduce unnecessary data read.
4. Measure working set and cache behavior.
5. Upgrade storage/memory once the true bottleneck is proven.

---

## 16. Example: An Unindexed Query Pulling Cold Data into Cache

Suppose:

```javascript
db.orders.insertMany([
  {
    _id: "O1",
    tenantId: "T1",
    status: "PAID",
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    totalMinor: 120000
  },
  {
    _id: "O2",
    tenantId: "T1",
    status: "PAID",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    totalMinor: 80000
  },
  {
    _id: "O3",
    tenantId: "T1",
    status: "PENDING",
    createdAt: ISODate("2026-11-13T11:00:00Z"),
    totalMinor: 60000
  }
]);
```

This is sample data creation in a **test database**—never run duplicate-ID inserts against production.

Business query:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20);
```

On a real collection with millions of orders and no suitable index, the query can:

- Scan many documents for wrong tenants or statuses.
- Read many cold data pages.
- Burn CPU evaluating filters.
- Sort large candidate sets.
- Evict pages serving live online traffic from cache.

### 16.1. Testing a Compound Index

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Now the planner can jump directly to matching `(tenantId, status)` entries and read the time range in index order.

**This index is tailored to this specific query shape, not universally optimal for all workloads.** Inspect data distribution and `explain`.

### 16.2. Impact on the Working Set

Before the index: requests repeatedly touched massive numbers of data pages.

After the index: a compact slice of hot index pages and far fewer document pages suffice.

A well-chosen index **reduces the total volume of data cycled through cache**, not just CPU filter comparisons.

---

## 17. Explain: Reading Exactly What It Tells You

Run in a suitable environment:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20)
  .explain("executionStats");
```

Inspect:

| Field/Signal | Suggested Meaning |
| --- | --- |
| `nReturned` | Number of documents returned during execution |
| `totalKeysExamined` | Number of index keys scanned |
| `totalDocsExamined` | Number of documents inspected |
| `IXSCAN` | Index access occurred |
| `COLLSCAN` | Full collection scan occurred |
| `FETCH` | Documents had to be fetched from collection data |
| `SORT` | Explicit in-memory sort stage in the plan |
| `executionTimeMillis` | Server-side timing inside explain, not full app latency |

### 17.1. Ratio of `docsExamined` / `nReturned`

If:

```text
nReturned:          20
totalDocsExamined:  500000
```

the query likely reads far too many documents relative to its output. Still, check actual query intent, post-query aggregation, filter selectivity, and index plan.

If:

```text
nReturned:          20
totalDocsExamined:  20
```

the query is highly selective. Yet **this does not prove zero disk reads occurred**, because those 20 document pages might be cold.

### 17.2. Explain Does Not Show "20 Disk Reads" for 20 `FETCH`es

`FETCH` means retrieving data documents; those documents might already reside in WiredTiger cache or OS page cache. Correlate with disk I/O metrics before claiming physical read costs.

### 17.3. Execution Stats Can Alter Cache State

Running `explain("executionStats")` actually reads data and warms cache. Do not run it thousands of times on production just for sampling without weighing its overhead.

---

## 18. Covered Queries: Skipping Document Fetches When Possible

A **covered query** can be satisfied purely from index keys without reading document data pages, provided filters, projections, and index rules align.

Suppose:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  totalMinor: 1
});
```

Query:

```javascript
db.orders.find(
  {
    tenantId: "T1",
    status: "PAID"
  },
  {
    _id: 0,
    createdAt: 1,
    totalMinor: 1,
    tenantId: 1,
    status: 1
  }
).sort({
  createdAt: -1
}).limit(20);
```

Under matching conditions, this index serves filter, sort, and projection without fetching full documents.

### 18.1. Why Is `_id: 0` Required?

MongoDB returns `_id` by default. If `_id` is not included in the compound index, keeping `_id` in the default projection prevents coverage and forces a `FETCH`. Explicitly excluding `_id` when unneeded enables coverage.

### 18.2. Do Not Try to Cover Every Query

Adding extra fields bloats indexes:

- Increases disk/index storage.
- Increases cache footprint.
- Increases insert/update/delete overhead.
- Can reduce write throughput.

Reserve covered indexes for truly critical queries with stable projections.

### 18.3. Limitations

Multikey indexes, null/missing semantics, collations, array projections, and query engine/version behavior can all prevent coverage. Verify with `explain`, never assume from the index definition alone.

---

## 19. Does Projection Reduce Disk I/O?

Compare two queries:

```javascript
// A: return full document
db.orders.find({
  tenantId: "T1"
});

// B: return fewer fields
db.orders.find(
  { tenantId: "T1" },
  { _id: 1, status: 1 }
);
```

Projection B reduces:

- Network response payload size.
- BSON serialization overhead.
- Application memory usage.
- Some field-processing CPU.

However, if the server still has to `FETCH` the document page, projection **does not guarantee physical disk reads drop proportionally to response bytes saved**.

Projection significantly cuts storage reads when paired with an **index-covered query** or suitable columnar/engine features depending on version and configuration.

### 19.1. Large Documents / BinData

If documents embed large binary fields while list endpoints only need title and status, redesigning the schema to separate metadata from binary blobs (or using GridFS/object storage where appropriate) avoids loading and transferring unneeded payloads.

Do not rely on "projecting a few fields" as a universal fix for bloated documents.

---

## 20. Large Indexes: Query Benefits vs. Memory Cost

A good index eliminates collection scans. Yet you can end up with:

```text
Collection storage:   40 GiB
Index A:               8 GiB
Index B:              10 GiB
Index C:              12 GiB
Index D:              15 GiB
-----------------------------
Total indexes:        45 GiB
```

If only a subset of those indexes are actively used, the rest waste storage and add write overhead.

### 20.1. Do Not Drop an Index Just Because It Looks Big

Verify:

- Which queries depend on the index?
- Does it support sorting or uniqueness?
- Does it serve periodic batch or maintenance queries?
- Are there overlapping index prefixes?
- Are multiple indexes needed for distinct query shapes?
- Has hiding it via hidden indexes been tested in staging or an approved workflow?

### 20.2. Index Selectivity Affects Cache

An index on a low-cardinality field, like `status` with only 3 values, may lack selectivity.

```javascript
db.orders.createIndex({
  status: 1
});
```

If 95% of orders have `status: "PAID"`, querying `PAID` still reads huge numbers of documents and triggers extensive data page fetches.

Compound indexes pairing tenant, time, and real query patterns are usually worth evaluating.

---

## 21. Time-Based Reads and Locality

The working set depends not just on "how many documents" exist, but also on **locality**.

### 21.1. Time-Range Queries

An app commonly reads:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
});
```

When traffic clusters on recent dates, a suitable index keeps accesses focused on recent index/data pages instead of scanning all history.

### 21.2. Tenant Locality

A SaaS application querying:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "OPEN"
});
```

Putting `tenantId` first in a compound index can improve locality for equality filters, though you must validate against sort, range, and cardinality.

### 21.3. Hot Keys

One document receiving thousands of requests per second:

```javascript
db.config.findOne({
  _id: "global-feature-flags"
});
```

Reads may stay cached comfortably, whereas concurrent writes to that same document cause lock/write contention at another layer. Do not blame disk I/O for every hot-key latency issue.

---

## 22. Aggregations Can Pollute the Cache

Example reporting batch:

```javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2024-01-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      total: { $sum: "$totalMinor" }
    }
  }
]);
```

With massive historical data, this aggregation pulls huge numbers of cold pages outside the web application's hot working set.

### 22.1. Three Cost Categories

1. **Source reads**: loading collection document and index pages.
2. **Intermediate memory**: RAM used by `$group`, `$sort`, or other blocking stages.
3. **Disk spill**: writing/reading temporary files if stages spill beyond memory limits.

All three differ mechanically, yet all pressure disk and memory.

### 22.2. `allowDiskUse` Does Not Make Queries Faster

```javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: "$tenantId",
        count: { $sum: 1 }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
```

`allowDiskUse` lets supported stages spill temporary data to disk when needed per MongoDB version/server settings. It prevents memory-limit failures in supported cases, yet **can increase I/O and latency**.

Spill indicators in explain/profiler include `usedDisk`, `spills`, or equivalent fields depending on version and stage.

### 22.3. Mitigation Strategies

- Filter early with indexed `$match`.
- Narrow reporting time ranges.
- Reduce projected fields/data processed.
- Use pre-aggregated or materialized views where appropriate.
- Shift heavy batch scans to off-peak hours or dedicated secondaries/analytics deployments, accounting for replication impact.
- Cap concurrency of large jobs.

---

## 23. Periodic Scans and Cache Pollution

A job calling:

```javascript
db.events.find({}).batchSize(1000);
```

on a 500-million-event collection reads massive numbers of cold pages. Run repeatedly, it can evict hot pages used by live requests.

### 23.1. How Cache Pollution Manifests

Hypothetical timeline:

```text
08:50  Web query p95 = 20 ms
09:00  Analytics scan starts
09:05  Disk read IOPS spikes
09:07  WT pages read/evicted rises
09:10  Web query p95 = 250 ms
09:20  Analytics scan ends
09:25  Web queries gradually recover
```

This is an investigative pattern, not causal proof without correlated metrics.

### 23.2. How to Reduce Interference

- Isolate analytical read workloads if architecture allows.
- Route select heavy queries to dedicated secondaries, while guarding against oplog lag.
- Use precomputed summaries.
- Add time-range filters and indexes.
- Throttle batch scan frequency and concurrency.
- Archive cold history appropriately.

**Do not** dump all analytics onto a secondary and forget that secondaries also need disk, memory, and replication headroom.

---

## 24. Impact of Disk Reads on p50, p95, and p99 Latency

Suppose 1,000 requests execute:

```text
950 requests: hot pages, 5 ms
 40 requests: a few page misses, 30 ms
 10 requests: many disk reads, 250 ms
```

Outcome:

- p50 stays near 5 ms.
- p95 lands around the cache-miss tier.
- p99 and tail latency are heavily skewed by I/O-bound requests.

A change that increases cache misses can **severely degrade p99** while p50 barely moves.

### 24.1. Why Does p99 Matter?

Users hit the slowest requests when:

- Opening the first page after an idle period.
- Querying a less-active tenant.
- Fetching older uncached records.
- Concurrency spikes.
- A batch job just polluted the cache.

If SLAs target p99, benchmark both **warm states** and **semi-cold states**, not just 100 repeated lookups of the exact same `_id`.

---

## 25. Cache Reads Still Consume CPU

A cache hit does not mean a free query:

- B-tree traversal uses CPU.
- BSON decoding/materialization requires processing.
- Predicate evaluation still runs.
- Aggregation expressions still compute.
- Sorting/hashing consumes memory and CPU.
- Network serialization takes time.
- Locks, tickets, and worker scheduling can introduce waits.

A query taking 100 ms with near-zero Disk Read IOPS is likely CPU-bound or resource-contended, not "needing more RAM."

### 25.1. Four Diagnostic Buckets

```text
High CPU + low disk reads?
  -> query CPU, aggregation, document size, concurrency

High read IOPS + read latency?
  -> cache misses, indexes, storage saturation

High disk writes + read latency?
  -> checkpoints/dirty eviction, write contention

Low CPU/disk but high app latency?
  -> network, connection pool, locks, remote services
```

These are triage hints, not substitutes for full traces and profiling.

---

## 26. Reading WiredTiger Metrics from `serverStatus`

With appropriate permissions:

```javascript
const status = db.serverStatus();

printjson({
  wiredTigerCache: status.wiredTiger
    ? status.wiredTiger.cache
    : null
});
```

Common counters/fields under `wiredTiger.cache`:

- `maximum bytes configured`.
- `bytes currently in the cache`.
- `tracked dirty bytes in the cache`.
- `pages read into cache`.
- `pages written from cache`.
- `pages evicted by application threads`.
- Counters related to eviction queues, eviction progress, and application waits.

**Field names vary across server versions, storage engines, and platforms.** Inspect actual keys in `db.serverStatus().wiredTiger.cache` on your running environment rather than assuming every version exposes identical counters.

### 26.1. Extracting Common Metrics

```javascript
const cache = db.serverStatus().wiredTiger.cache;

printjson({
  maximumBytes: cache["maximum bytes configured"],
  currentBytes: cache["bytes currently in the cache"],
  dirtyBytes: cache["tracked dirty bytes in the cache"],
  pagesRead: cache["pages read into cache"],
  pagesWritten: cache["pages written from cache"]
});
```

Do not treat `undefined` values as proof the server has no cache; key names may differ, be omitted, or be restricted by permissions/platform.

### 26.2. Cumulative Counters Require Deltas

If:

```text
pages read into cache at 10:00 = 1,000,000
pages read into cache at 10:01 = 1,006,000

Delta = 6,000 pages in 60 seconds
Rate  = 100 pages/second
```

Never look at `1,006,000` and say "MongoDB is slow"—it may simply be cumulative since server startup.

### 26.3. Counter Resets

Cumulative counters reset when the process restarts. When calculating deltas, if the later sample is smaller than the earlier one, check for restarts or reconfiguration instead of reporting negative I/O.

---

## 27. `mongosh` Script to Snapshot Cache Metrics

A **read-only** example:

```javascript
function getCacheSnapshot() {
  const s = db.serverStatus();
  const c = s.wiredTiger && s.wiredTiger.cache
    ? s.wiredTiger.cache
    : {};

  return {
    at: new Date(),
    host: s.host,
    uptimeSeconds: s.uptime,
    maximumBytes: c["maximum bytes configured"],
    currentBytes: c["bytes currently in the cache"],
    dirtyBytes: c["tracked dirty bytes in the cache"],
    pagesRead: c["pages read into cache"],
    pagesWritten: c["pages written from cache"],
    pagesEvictedByApp:
      c["pages evicted by application threads"]
  };
}

printjson(getCacheSnapshot());
```

If polled periodically, store snapshots in an external metrics store; do not write high-frequency monitoring logs back into the same production MongoDB without accounting for write overhead.

### 27.1. Do Not Compute Cache Hit Rate from a Single Mismatched Counter

A formula like:

```text
hitRate = 1 - pagesRead / totalQueries
```

**is invalid** because `pagesRead` counts pages while `totalQueries` counts queries. One query can touch 0, 1, or hundreds of pages; the units do not match.

Use platform-provided cache hit metrics if officially defined, or analyze page read/eviction rates alongside workload and disk I/O.

---

## 28. Monitoring OS and Disk on Self-Managed Linux

Common diagnostic commands:

```bash
# RAM status, OS page cache, and available memory
free -h

# Paging, run queue, CPU wait
vmstat 1

# Disk latency/IOPS/queue (requires sysstat/iostat)
iostat -xz 1

# Process-level CPU/memory
pidstat -r -u -p ALL 1
```

These commands are read-only. In containers or cloud-managed deployments, they may require host privileges or miss the full underlying storage path.

### 28.1. Low `free` Memory Does Not Mean Out of RAM

Linux puts idle memory into file cache. When `free -h` shows:

```text
free:        low
buff/cache:  high
available:   still healthy
```

that is completely normal. Watch `available`, swap activity, OOM events, memory pressure, and latency rather than `free`.

### 28.2. Check the Right Volume in `iostat`

If data files live on `/dev/nvme1n1` while you inspect `/dev/nvme0n1`, your disk conclusions will be wrong. In cloud deployments, also check cloud provider volume metrics for IOPS, throughput, and burst credits.

### 28.3. CPU `iowait` Does Not Prove "MongoDB Is Waiting on I/O"

`iowait` is an OS-level CPU accounting statistic across all processes sharing disks; correlate it with process workloads, disk metrics, WiredTiger counters, and query latency.

---

## 29. Metrics and Tools in MongoDB Atlas

In Atlas, metrics and charts are exposed via the UI/API depending on edition and tier. Key areas to monitor:

- WiredTiger cache usage and dirty pages.
- Disk Read IOPS.
- Disk Write IOPS.
- Disk I/O latency where exposed.
- Disk queue depth and throughput.
- System memory/cache.
- CPU utilization.
- Connections and operation queues.
- Query targeting, scanned/returned ratios, and slow queries.
- Replication lag and background activity.
- Backup, initial sync, and index build activity.
- Search workloads if using MongoDB Search.

### 29.1. Never Blame One Chart in Isolation

Seeing Disk Read IOPS climb alongside p99 latency does not prove cache size is the sole cause. An index build, backup, or batch scan may have run at the same moment.

Build a correlated timeline linking **query shapes**, **cache**, **storage**, and **application latency**.

---

## 30. Measuring Collection and Index Sizes to Form Hypotheses

On a collection with realistic data and proper privileges:

```javascript
db.orders.stats({
  scale: 1024 * 1024
});
```

Key fields:

- `count`.
- `size`.
- `storageSize`.
- `totalIndexSize`.
- `indexSizes`.

Or via aggregation:

```javascript
db.orders.aggregate([
  {
    $collStats: {
      storageStats: {
        scale: 1024 * 1024
      }
    }
  }
]);
```

Field availability and exact interpretation vary by version and topology. Returned sizes show **capacity footprint**, not **access frequency**.

### 30.1. Rough Estimation

Suppose:

```text
Recent 7-day order data:    12 GiB on disk
Relevant hot indexes:        6 GiB on disk
Cold history:              300 GiB on disk
```

Do not conclude hot RAM must be exactly 18 GiB, yet you can use this as an **initial hypothesis** to test against actual cache residency, page-read rates, and traffic latency.

---

## 31. Query Profiler and Slow Query Logs

MongoDB's profiler and logs help pinpoint queries reading excessive data:

- `docsExamined`.
- `keysExamined`.
- `nreturned`.
- `planSummary`.
- `millis`.
- `numYields`.
- Disk spill / temporary storage fields where supported.
- Lock/resource wait metrics depending on version.

### 31.1. Do Not Over-Enable Profiling in Production

Profiling every query adds overhead and can capture sensitive query parameters. Use deployment-appropriate query insights, sampling thresholds, and retention policies.

### 31.2. Distinguish Query Shape from Specific Execution

A single `find` shape can exhibit wildly different latencies depending on:

- Warm vs. cold cache.
- Large vs. small tenants.
- Predicate selectivity.
- Concurrent backup I/O on storage.
- Index plan changes.

Group diagnostics by both query shape **and** key parameters / data distributions.

---

## 32. Experiments: Warm Cache vs. Cold Cache

A sound way to validate hypotheses is benchmarking on **staging with production-like data distributions**.

### 32.1. Experiment A — Warm Repeated Reads

1. Select a representative query shape.
2. Execute it repeatedly once the system stabilizes.
3. Measure p50/p95/p99, CPU, and disk read rates.
4. Ensure no heavy background scans interfere.
5. Record the index plan.

Example:

```javascript
for (let i = 0; i < 20; i++) {
  const started = Date.now();

  db.orders.find({
    tenantId: "T1",
    status: "PAID"
  }).sort({
    createdAt: -1
  }).limit(20).toArray();

  print("elapsedMs=", Date.now() - started);
}
```

This is a simple wall-clock illustration, **not a rigorous benchmark framework**. JavaScript runtime, network, and client parsing all contribute to the timing.

### 32.2. Experiment B — Varying Accessed Data Subsets

1. Cycle across multiple tenants and IDs.
2. Mix hot time ranges with cold historical ranges.
3. Run under workload-realistic concurrency.
4. Observe page reads and disk latency.
5. Contrast against warm repeated reads.

### 32.3. Never Drop OS Page Cache in Production

Commands like `sync; echo 3 > /proc/sys/vm/drop_caches` clear caches system-wide and can cause severe latency spikes. **Never run them on production** just to test cold caches. Even in staging, get approval and understand the impact on co-located processes.

### 32.4. 100 Documents Never Proves Performance at 100 Million Documents

A tiny dataset that stays permanently cached hides real disk reads and cache eviction. Benchmarks must have meaningful scale and skew.

---

## 33. Java Sync Driver: Reducing Data Read

Example query fetching the 20 newest orders for a tenant:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

public final class OrderQueryRepository {

    public static void listRecentPaidOrders(
            MongoCollection<Document> orders,
            String tenantId,
            Date from
    ) {
        Bson filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("status", "PAID"),
            Filters.gte("createdAt", from)
        );

        orders.find(filter)
            .sort(Sorts.descending("createdAt"))
            .projection(
                Projections.fields(
                    Projections.include(
                        "tenantId",
                        "status",
                        "createdAt",
                        "totalMinor"
                    ),
                    Projections.excludeId()
                )
            )
            .limit(20)
            .maxTime(2, java.util.concurrent.TimeUnit.SECONDS)
            .forEach(doc ->
                System.out.println(doc.toJson())
            );
    }
}
```

### 33.1. What This Code Accomplishes

- Constrains scope by tenant, status, and time.
- Returns 20 documents rather than all matches.
- Returns only needed fields.
- Applies a server-side execution timeout via the driver API.

### 33.2. What This Code Does Not Automatically Guarantee

- Does not create missing indexes.
- Does not guarantee a covered query.
- Does not guarantee zero disk reads on every execution.
- Does not eliminate I/O when pages are cold.
- Does not replace client-side timeouts, connection pools, and cancellation policies.

Pair it with an appropriate compound index at the schema/migration layer and verify the execution plan with `explain`.

---

## 34. Java: Running `explain` on a Query

Example running `explain()` on a `FindIterable` in the Java Sync Driver:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.ExplainVerbosity;
import org.bson.Document;

public final class ExplainOrderQuery {

    public static void explain(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        Document result = orders.find(
                Filters.eq("tenantId", tenantId)
            )
            .sort(Sorts.descending("createdAt"))
            .limit(20)
            .explain(ExplainVerbosity.EXECUTION_STATS);

        System.out.println(
            result.toJson()
        );
    }
}
```

`EXECUTION_STATS` reveals server-side execution statistics for the query. Never embed `explain` into live per-HTTP-request code paths: explain carries overhead and numbers vary under load.

---

## 35. Java: Separating Server Latency from End-to-End Latency

A request comprises:

```text
HTTP request
    |
    +-- authentication
    +-- application validation
    +-- connection pool wait
    +-- network to MongoDB
    +-- server query execution
    +-- MongoDB network response
    +-- BSON deserialization
    +-- business transformations
    +-- HTTP serialization
    v
HTTP response
```

If `explain.executionTimeMillis` is low while HTTP p99 is high, the culprit may be the connection pool, network, application CPU, or downstream services.

### 35.1. Application-Level Timing

```java
long started = System.nanoTime();

var results = orders.find(
        Filters.eq("tenantId", tenantId)
    )
    .limit(20)
    .into(new java.util.ArrayList<>());

long elapsedNanos =
    System.nanoTime() - started;

System.out.println(
    "DB call elapsedMs="
        + elapsedNanos / 1_000_000.0
);
```

This captures client-side duration for that call; it does not separate cache misses from disk I/O on its own. Combine with tracing, driver metrics, and `serverStatus`.

### 35.2. Watch Connection Pool Wait

Requests can queue up waiting on the connection pool even when the server cache is completely healthy. Adding RAM to MongoDB will not solve an application-side pool bottleneck.

---

## 36. Sizing RAM for MongoDB: Do Not Just Double `databaseSize`

A sizing plan starts with:

1. Current collection and index sizes.
2. Fraction of data accessed across active time windows.
3. Query patterns driving page reads.
4. Peak concurrency and intermediate working memory.
5. Configured WiredTiger cache size.
6. OS page cache and available memory.
7. Disk I/O performance on cache misses.
8. 6–12 month growth projections.
9. Target p95/p99 latency SLOs.
10. Cost of adding RAM vs. index/schema tuning or archiving.

### 36.1. Architecture Examples

```text
Physical RAM:             64 GiB
WT cache default:       ~31.5 GiB
OS/process headroom:      remainder
Estimated hot pages:     ~22 GiB
Cold data:               500 GiB
```

This workload **can run very well** if hot pages truly stay near 22 GiB and indexes/queries are sound, even though cold data dwarfs RAM.

A different situation:

```text
Physical RAM:             64 GiB
Hot pages:                75 GiB
WT cache default:       ~31.5 GiB
Daily reports:            scans 300 GiB
```

Here cache churn and heavy disk reads are likely; optimize access patterns and separate batch jobs before assuming more RAM alone will suffice.

### 36.2. Memory Sizing in Containers

When running MongoDB in containers, verify:

- Cgroup memory limits visible to the MongoDB process.
- Default/effective WiredTiger cache configuration.
- OS page cache accounting within the cgroup.
- Sidecars/agents sharing the memory budget.
- OOM kill events.
- Kubernetes resource requests/limits and eviction policies.

Never set cache equal to the entire container memory limit; MongoDB requires memory outside the WiredTiger cache.

---

## 37. Data Size Grows, but Must the Working Set Grow?

No.

An order history growing from 100 GiB to 1 TiB over 3 years where users still primarily query the last 30 days may see its working set grow far more slowly.

Conversely, adding a feature that searches all 5 years of orders or an auto-refreshing dashboard can spike the working set abruptly while **database size stays unchanged**.

### 37.1. Changes That Commonly Expand the Working Set

- Adding an endpoint that scans full history.
- Adding dashboards with no default time filter.
- Growing number of concurrently active tenants.
- Adding indexes touching hot pages.
- Switching queries from narrow projections to full documents.
- Scheduling more reporting/batch jobs.
- Introducing unselective regexes or unindexed sorts.
- Higher record counts inside the active hot time window.
- Shifting from clustered recent accesses to random IDs across all history.

---

## 38. Archiving Cold Data to Shrink the Working Set

One pattern:

```text
orders_hot
  Last 90 days

orders_archive
  Older than 90 days
```

Or keep a single collection with appropriate partitioning, sharding, and query boundaries.

### 38.1. Archiving Is More Than Moving Documents

Ensure:

- Retention policies and historical lookup requirements.
- Referential consistency.
- Indexes on archive data.
- Acceptable retrieval latency for archived queries.
- Backups and restores covering archive data.
- Access controls and data protection.
- Zero data loss during move/delete pipelines.
- Auditability and rollback.

### 38.2. Do Not Misuse TTL Arbitrarily

TTL indexes automatically delete old documents—that is **data deletion**, not archiving. Data with retention requirements must never be dropped via TTL solely to relieve cache pressure.

### 38.3. Archiving Does Not Cut I/O If Queries Still Scan the Archive

If an hourly report reads both `orders_hot` and `orders_archive`, disk reads still occur. To protect hot-path latency, **isolate workloads or change data access strategies**, not merely collection names.

---

## 39. Sharding and the Working Set

Sharding distributes data and traffic across multiple shards:

```text
Application
    |
    v
  mongos
    |
    +--> shard A: local data/index/cache
    +--> shard B: local data/index/cache
    +--> shard C: local data/index/cache
```

When queries target shards cleanly via the shard key, each shard holds a smaller working set backed by its own cache and disk.

### 39.1. Sharding Does Not Automatically Reduce Total I/O

If queries lack the shard key and scatter-gather, multiple shards hit disk simultaneously.

Sharded clusters also introduce:

- Shard key distribution challenges.
- Hot chunks / uneven load.
- Cross-shard joins and aggregations.
- Balancer overhead.
- Replication overhead per shard.
- Higher operational complexity.

Do not shard solely to "shrink each index" when fixing queries/indexes on a single replica set works.

### 39.2. Hot Shards

If the shard key routes most reads/writes to one shard, idle RAM on other shards cannot help the overloaded shard. Choose shard keys for workload distribution and monitor per-shard cache and disk metrics.

---

## 40. Read Preference and Secondaries

A read-heavy system may route select queries to secondaries:

```javascript
db.orders.find({
  tenantId: "T1"
}).readPref("secondaryPreferred");
```

This illustrates `mongosh` syntax; production strategies must respect your driver's read preference and consistency semantics.

### 40.1. Benefits

- Offloads read traffic.
- Leverages secondary WiredTiger caches and OS page caches.
- Protects primary headroom from compatible reporting loads.

### 40.2. Trade-Offs

- Secondaries can experience replication lag.
- Stale reads can occur.
- Heavy reports can saturate secondary disks and increase replication lag.
- Secondaries still require proper indexes.
- Overloading a secondary can jeopardize replica health and failover readiness.

Never route reads requiring immediate read-after-write consistency to secondaries.

---

## 41. Cache Warm-Up After Restarts and Failovers

After MongoDB restarts, the process's internal cache starts empty of hot pages; the OS page cache may survive or be wiped depending on restart type.

### 41.1. Scenarios

| Event | What Happens |
| --- | --- |
| Restart `mongod` on same host | WT cache cleared; OS page cache may survive |
| Full host reboot | Both WT cache and OS page cache must reload |
| Failover to a secondary with traffic | Secondary may have a different hot cache than primary |
| Failover to a rarely read node | Needs warm-up under hot query patterns |
| Restoring a new cluster | Cache starts cold; indexes/data load on demand |
| Initial sync completes | Entire working set is not automatically hot |

### 41.2. Safe Warm-Up

- Verify indexes are ready.
- Ramp traffic gradually if architecture permits.
- Optionally pre-warm selectively with **representative read-only queries**, once benchmarked.
- Avoid scheduling heavy batch scans during failovers.
- Watch disk read IOPS and p95/p99 closely.

### 41.3. Do Not Scan the Entire Database to "Warm Cache"

If the hot working set is 20 GiB inside a 1 TiB database, a full scan floods cache with cold pages and evicts hot ones—counterproductive.

---

## 42. Disk I/O During Index Builds

Creating an index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1
});
```

can:

- Scan the entire collection.
- Read many cold data pages.
- Consume memory and CPU for sorting/building.
- Write index pages.
- Create I/O and latency pressure while building.

### 42.1. Long-Term Effect

Once built, targeted queries read far less data, lowering long-term cache churn.

Yet **during the build**, disk read/write spikes can occur. Schedule and monitor large production index builds carefully.

### 42.2. Do Not Use `reIndex` as a "Cache Reset"

Rebuilding indexes is expensive, I/O-heavy, and does not fix bad query shapes. Run it only for supported maintenance/repair needs, never as a routine speedup trick.

---

## 43. Disk Spills Differ from Collection Reads

A query:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T1" } },
  { $sort: { totalMinor: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true
});
```

can incur:

- Data and index page reads.
- Intermediate sort memory.
- Disk spills if the sort lacks an index and exceeds memory limits per server mechanics.

### 43.1. Why Distinguish Them?

If Disk Write IOPS climbs due to sort spills, enlarging the WiredTiger cache will not fix the root cause. You must:

- Add an index supporting the sort.
- Filter data before sorting.
- Reduce cardinality.
- Consider precomputed rankings or pagination.
- Redesign the aggregation pipeline.

### 43.2. Temporary Files Still Share Storage

Disk spills often reside on MongoDB's storage volume and contend with page reads and checkpoints. Never assume temp disk I/O is isolated from database storage without verifying your deployment layout.

---

## 44. Reading Many Small Records: The N+1 Query Problem

A backend pattern:

```text
1 request fetches 100 orders
  -> query 100 orders
  -> for each order, query customer
  -> for each order, query shipping info

Total ~201 queries / HTTP request
```

Even if every query hits an index, hundreds of round trips and scattered page lookups inflate latency.

### 44.1. Remediation

- Batch fetch using `$in` with reasonable bounds.
- Embed frequently co-read data if update and size semantics allow.
- Use `$lookup` with proper indexes and data distribution.
- Materialize read models where the domain fits.
- Control connection pool sizing and request parallelism.

**Goal:** minimize the total disk, index, and document pages plus network round trips per business operation.

---

## 45. Reading Large Documents When Only One Small Field Is Needed

Suppose a document:

```javascript
{
  _id: "DOC-100",
  title: "Large contract",
  status: "READY",
  body: "very long text...",
  attachments: [ /* large embedded payloads */ ]
}
```

A list API only needs `title` and `status`. When huge bodies/attachments sit inside the same document, reading and materializing pages carries heavy overhead.

### 45.1. Separate Metadata from Payload When Appropriate

```javascript
// documents
{
  _id: "DOC-100",
  title: "Large contract",
  status: "READY",
  contentId: "CONT-100"
}

// documentContents
{
  _id: "CONT-100",
  body: "very long text..."
}
```

Benefits:

- List APIs never touch the `documentContents` collection.
- Hot metadata document pages remain compact.
- Heavy content is read only when users open details.

Trade-offs:

- Extra query or `$lookup` when full content is needed.
- Consistency management across two collections.
- Schema and migration complexity.
- Transactions or workflows for coordinated updates.

Do not split every field into its own collection—that causes N+1 queries and destroys locality.

---

## 46. When Does Adding RAM Actually Help?

Adding RAM is typically worthwhile when:

1. The hot working set exceeds cache capacity and drives repeated evictions.
2. Query and index plans are already optimized.
3. Disk reads and latency correlate tightly with cache pressure.
4. No unrelated memory leaks, swapping, or OS pressure exist.
5. Budget and resize/failover plans are in place.
6. More RAM is projected to meaningfully raise hit rates and cut IOPS/latency.

### 46.1. When Might Adding RAM Not Help?

- Queries are CPU-bound.
- Storage latency stems from checkpoints/write load rather than read misses.
- Network or connection pool bottlenecks dominate.
- Missing indexes force full scans on every request.
- Reports scan historical data larger than any practical RAM tier.
- A hot shard is severely skewed.
- Untargeted queries scatter across all shards.
- Export/serialization payloads are simply huge.

### 46.2. Raising `cacheSizeGB` Differs from Adding Host RAM

Increasing `cacheSizeGB` on the same RAM squeezes the OS page cache and other components. Upgrading host RAM while keeping WiredTiger's default sizing increases both internal cache and OS headroom together.

---

## 47. Investigation Playbook When Latency Spikes

### Phase A — Ask the Right Questions

1. Which endpoint is slow?
2. Since when?
3. Did p50 rise, or only p99?
4. One tenant or many tenants?
5. After a failover/restart, or during a batch job?
6. Any recent deploys, index changes, or data growth?

### Phase B — Inspect Queries

7. Locate query shapes in profiler / slow query logs.
8. Run `explain("executionStats")`.
9. Check for `COLLSCAN`, `SORT`, and keys/docs examined.
10. Review indexes and projections.
11. Identify hot vs. cold data ranges.

### Phase C — Inspect Cache and Disk

12. WiredTiger max/current cache bytes.
13. Dirty pages and eviction counters/rates.
14. Delta of pages read into cache.
15. OS available memory, swap, and page faults.
16. Disk read IOPS, throughput, and latency.
17. Disk write IOPS, checkpoints, and storage queue depth.
18. Concurrent background jobs, backups, and index builds.

### Phase D — Act on Verified Hypotheses

19. Query reads too broadly → fix filters/indexes.
20. High `FETCH` volume → evaluate covered projections/indexes.
21. Batch scans evicting hot pages → reschedule/throttle batches.
22. Hot working set exceeds cache → scale RAM / archive / isolate workloads.
23. Disk saturated despite clean queries → upgrade IOPS/throughput/SSD.
24. Aggregation spills → index, sort optimization, or precomputation.
25. Cold cache after failover → controlled traffic warm-up.

### Phase E — Verify Results

26. Measure the exact same query/workload before and after.
27. Compare p50/p95/p99, docs examined, disk IOPS, and evictions.
28. Ensure write latency and replication lag did not regress.
29. Document the change and rollback plan.
30. Monitor across at least one full peak traffic cycle.

---

## 48. Scenario A — Missing Index Driving Disk Reads

**Symptoms:**

```text
Query p95:              450 ms
nReturned:                20
docsExamined:        800,000
Disk read IOPS:        15,000
WT pages read rate:     high
```

**Hypothesis:** Query scans unnecessary documents.

**Action:**

- Identify filters and sorts.
- Create a suitable compound index.
- Re-run `explain`.
- Compare latency and disk read rates.

**Expected outcome:** Fewer candidate documents and data pages read, without needing more RAM.

**Caveat:** Actual improvement depends on selectivity, cache state, and chosen plan.

---

## 49. Scenario B — Cache Pollution from Reporting

**Symptoms:**

```text
07:00 Web p95:            18 ms
07:30 Analytics starts
07:35 Disk Read IOPS:      rises
07:40 Eviction rate:       rises
07:45 Web p95:           180 ms
08:15 Analytics ends
08:30 Web p95:            23 ms
```

**Hypothesis:** Historical scan evicts hot pages.

**Action:**

- Schedule batches during off-peak hours.
- Add range filters and indexes.
- Use pre-aggregated reports.
- Consider dedicated secondary or reporting deployments.
- Try incremental processing.

**Avoid:** Infinitely scaling RAM to fit all history when live web traffic only needs hot data.

---

## 50. Scenario C — Slow Disk After Resizing

**Symptoms:**

```text
Query docsExamined: same as before
WiredTiger cache usage: stable
Disk latency: rises from ~1ms to ~20ms
Cloud burst credits: depleted
Request p99: rises sharply
```

**Hypothesis:** Storage hit IOPS/throughput caps or exhausted burst credits.

**Action:**

- Inspect volume metrics and provisioning.
- Verify instance-level throughput caps.
- Adjust IOPS/throughput or storage tier per cloud provider.
- Smooth bursty workloads.
- Compare physical read sizes and queue depth.

**Avoid:** Adding an unrelated index just because queries turned slow.

---

## 51. Scenario D — Replica Set Failover

**Symptoms:**

```text
Primary A warm, p95 = 15 ms
Failover to B
New primary B, p95 = 140 ms for 5 minutes
Read IOPS spikes then subsides
```

**Hypothesis:** B lacks the same hot pages in internal/OS cache; workload is warming it up.

**Action:**

- Measure cache/disk metrics per node.
- Verify B has matching RAM/disk specs as A.
- Ramp traffic appropriately if possible.
- Inspect failover health and replication history.
- Never resize cache based on a single brief post-failover spike.

**Trade-off:** Failover prioritizes availability first, then tail-latency warm-up.

---

## 52. Practice Exercises with Solutions

### Exercise 1 — Total Size vs. Working Set

A database is 2 TiB, yet hot traffic touches only ~20 GiB of recent documents and index pages.

**Question:** Do you strictly need more than 2 TiB of RAM?

**Answer:** No. As long as the working set and cache layers comfortably hold the hot pages, cold data can safely reside on disk.

### Exercise 2 — Full Cache

WiredTiger cache is at 92%, yet p99 is stable and disk read IOPS is low.

**Question:** Should you add RAM immediately?

**Answer:** Not without further evidence. Caches are designed to stay utilized; check evictions, page reads, latency, and memory pressure.

### Exercise 3 — WiredTiger Cache Miss

A page is absent from WT cache yet present in the OS page cache.

**Question:** Does this require an SSD read?

**Answer:** No. The OS page cache can serve it from RAM.

### Exercise 4 — FETCH

Explain shows `FETCH` after `IXSCAN`.

**Question:** Is this proof of a physical disk read?

**Answer:** No. `FETCH` means retrieving the document, which may already be resident in cache.

### Exercise 5 — Disk Reads and Projection

A query projects 5 fields instead of 50 fields while still fetching the same pages.

**Question:** Will disk reads drop by 10x?

**Answer:** No. Projection shrinks response size and serialization, without directly guaranteeing proportional cuts in physical I/O; covered queries are what avoid fetches.

### Exercise 6 — Query Targeting

`nReturned=20`, `docsExamined=1,000,000`.

**Question:** What should be investigated?

**Answer:** Filter selectivity, indexes, sorting, and overly broad query scans.

### Exercise 7 — Cumulative Counter

Pages read into cache rise from 20,000 to 26,000 over 60 seconds.

**Question:** Average rate?

**Answer:** `(26000 - 20000) / 60 = 100 pages/s`.

### Exercise 8 — Page Faults

OS reports 50,000 minor page faults.

**Question:** Can you conclude 50,000 SSD reads occurred?

**Answer:** No. Minor page faults generally do not require physical disk I/O.

### Exercise 9 — Disk Throughput

A volume serves 10,000 IOPS averaging 4 KiB/request.

**Question:** Approximate throughput?

**Answer:** 39.1 MiB/s.

### Exercise 10 — Random I/O

A query fetches 10,000 scattered documents across a collection.

**Question:** Why can SSD matter more than HDD?

**Answer:** Much lower random I/O latency and higher IOPS without mechanical seek delays.

### Exercise 11 — Aggregation Spill

`$sort` writes temporary spill files to disk.

**Question:** Will increasing WiredTiger cache definitely fix it?

**Answer:** No. You need to tune sorts, indexes, aggregation memory limits, and workload design.

### Exercise 12 — Dirty Pages

Dirty bytes in WT cache rise alongside Disk Write IOPS.

**Question:** Does that mean read misses are the only cause?

**Answer:** No. Checkpoints, eviction, and heavy write workloads also drive disk pressure.

### Exercise 13 — Hot Dataset and Indexes

A 500 GiB collection has hot queries touching a 2 GiB index and 5 GiB of hot documents.

**Question:** What should be measured before adding RAM?

**Answer:** Resident pages, evictions, cache page-read rates, disk I/O, and p95/p99 latency.

### Exercise 14 — Linux `free`

`free -h` shows `free` near 0 while `available` is high and cache is large.

**Answer:** This is typically normal; Linux uses idle RAM for the OS page cache.

### Exercise 15 — Covered Query

A query's index holds all filter and projected fields, yet default output still includes `_id`, which is absent from the index.

**Question:** Why might it still `FETCH`?

**Answer:** Default projection includes `_id`; explicitly pass `_id: 0` if not needed.

### Exercise 16 — Tenant Hotness

Tenant T1 drives 90% of traffic, while queries scatter across all shards.

**Question:** What must be inspected?

**Answer:** Shard key targeting, hot shards, query filters, and per-shard cache/disk metrics.

### Exercise 17 — Cache Warm-Up After Reboot

Disk Read IOPS spikes right after a reboot and then subsides.

**Answer:** OS page cache and WT internal cache are repopulating; distinguish transient warm-up spikes from sustained bottlenecks.

### Exercise 18 — Full Scan to Warm Cache

A team runs a 1 TiB full collection scan to warm a 16 GiB cache.

**Answer:** Counterproductive because it evicts hot pages; use representative hot queries instead.

### Exercise 19 — Raising Cache on the Same VM

A team raises `cacheSizeGB` from 8 to 14 GiB on a 16 GiB RAM VM.

**Answer:** Risks starving OS page cache and memory outside WiredTiger; size for the whole host.

### Exercise 20 — Optimization Trade-Off

A `COLLSCAN` on a 10-document collection takes 1 ms.

**Question:** Must an index be added immediately?

**Answer:** Not necessarily. Scanning tiny collections is often optimal; adding an index adds write and storage costs.

### Exercise 21 — Slow After Import

Right after a 100 GiB import finishes, web queries briefly slow down.

**Answer:** Likely cache churn, checkpoints, or I/O backlog; correlate metrics timelines.

### Exercise 22 — Deleting History

A team wants to add TTL deletion on contract history purely to boost cache hit rates.

**Answer:** Never apply TTL if legal or retention policies require keeping records. Consider archiving and query isolation instead.

### Exercise 23 — Secondary Reads

Reports are moved to a secondary, and secondary replication lag climbs.

**Answer:** Reporting I/O competes with replication; throttle/isolate workloads or increase capacity.

### Exercise 24 — Query Faster After Warm-Up

A query runs in 500 ms on the first run and 20 ms on the second.

**Answer:** Possibly cache warm-up, or CPU/plan differences; inspect I/O and benchmark under controlled conditions.

---

## 53. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "If total DB size exceeds RAM, MongoDB is always slow." | The hot working set is what drives cache locality. |
| "Working set = `storageSize` of the whole collection." | Working set depends on actual access patterns. |
| "Only document pages occupy cache." | Index pages also occupy cache. |
| "WiredTiger cache and OS page cache are the same." | Two separate tiers sharing host RAM. |
| "Every WT page read is an SSD read." | The OS page cache may serve it from memory. |
| "95% cache usage is a memory leak." | Caches are designed to use RAM; inspect eviction and latency. |
| "Low `free` RAM means out of memory." | OS page cache uses reclaimable RAM. |
| "`FETCH` always means a disk read." | `FETCH` retrieves documents, which may already sit in memory. |
| "`IXSCAN` is always faster than `COLLSCAN`." | Depends on selectivity, access pattern, and document count. |
| "Having an index means zero document page reads." | False whenever fetches outside the index are needed. |
| "Projecting fewer fields cuts disk reads proportionally." | Guaranteed to shrink response size; physical I/O savings must be verified. |
| "More indexes always make everything faster." | Indexes add storage, cache, and write overhead. |
| "Setting `cacheSizeGB` to 100% of RAM is better." | Starves OS/queries and risks OOM. |
| "High disk reads always come from web traffic." | Backups, index builds, and reports also drive I/O. |
| "Every page fault means storage I/O." | Minor faults usually do not. |
| "High IOPS means the disk is slow." | Inspect latency, queue depth, and capacity limits. |
| "High MB/s throughput means good random I/O." | IOPS and latency matter separately. |
| "Faster SSDs fix queries scanning too many docs." | Only lowers per-I/O cost without fixing the access path. |
| "`allowDiskUse` makes aggregations faster." | May trigger disk spills and slow queries down. |
| "Restore RTO has nothing to do with cache." | Restored nodes start cold and need warm-up. |
| "Adding RAM always lowers p99." | Not if CPU, network, or query shape is the bottleneck. |
| "Sharding automatically cuts all query latency." | Scatter-gather and hot shards can make it worse. |
| "Secondary reads never impact replication." | Reporting workloads compete for node resources. |
| "Full-scanning all data is a good cache warm-up." | Evicts hot pages with cold ones. |
| "Large cumulative counters mean an active bug." | Compute rates via deltas and account for restarts. |
| "Explain reports physical disk I/O per `FETCH`." | Must correlate with storage metrics. |
| "Repeating one `_id` lookup proves production speed." | Need hot/cold mixes, concurrency, and real skew. |
| "Disabling journal / lowering write concern fixes read latency." | Compromises durability without fixing access patterns. |
| "Archiving means deleting old data." | Archiving preserves retention and retrievability. |
| "TTL is a harmless working-set tuning tool." | TTL permanently deletes data—huge business risk if misused. |

---

## 54. Checklist Before Tuning Read Performance

1. [ ] Identified the query shape/endpoint causing high latency.
2. [ ] Inspected `explain("executionStats")`?
3. [ ] Checked for excessive keys/docs scanned?
4. [ ] Verified indexes support filters and sorts properly?
5. [ ] Checked whether projections can be covered?
6. [ ] Estimated working set via access patterns rather than database size alone?
7. [ ] Accounted for hot index pages?
8. [ ] Verified WiredTiger cache max/current bytes at runtime?
9. [ ] Checked for unusual dirty pages or eviction spikes?
10. [ ] Computed deltas for pages read into cache?
11. [ ] Checked OS page cache and `available` memory?
12. [ ] Checked for swap, OOMs, or memory pressure?
13. [ ] Checked whether Disk Read IOPS and throughput hit limits?
14. [ ] Correlated disk read latency/queue spikes with p99 spikes?
15. [ ] Checked whether write IOPS/checkpoints contend for I/O?
16. [ ] Checked for concurrent batch scans, index builds, or backups?
17. [ ] Checked for aggregation spills?
18. [ ] Checked whether queries pull oversized BSON documents or unnecessary fields?
19. [ ] Checked for N+1 queries or excessive network round trips?
20. [ ] Evaluated isolating analytics/reporting workloads?
21. [ ] Checked whether cold data can be archived within retention rules?
22. [ ] Checked sharded clusters for hot shards or scatter-gather?
23. [ ] Verified whether read preference tolerates stale reads and lag?
24. [ ] Accounted for post-restart/failover cache warm-up?
25. [ ] Verified whether adding RAM actually cuts repeated cold page reads?
26. [ ] Verified whether storage upgrades target a real IOPS/latency bottleneck?
27. [ ] Measured p50/p95/p99 under representative load?
28. [ ] Prepared before/after benchmarks and a rollback plan?
29. [ ] Avoided cache-disrupting operations on live production?
30. [ ] Configured trend monitoring to catch working-set growth over time?

---

## 55. Official Documentation and Learning Resources

- [MongoDB — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/): storage engine architecture, compression, and concurrency.
- [MongoDB — WiredTiger Memory Use](https://www.mongodb.com/docs/manual/core/wiredtiger/#memory-use): cache sizing and interaction with OS cache.
- [MongoDB — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/#mongodb-setting-storage.wiredTiger.engineConfig.cacheSizeGB): configuring WiredTiger cache.
- [MongoDB — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/): cache, memory, and storage engine metrics.
- [MongoDB — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/): query planner and index selection.
- [MongoDB — explain](https://www.mongodb.com/docs/manual/reference/explain-results/): `executionStats`, keys/docs examined, and stage semantics.
- [MongoDB — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-queries): index-only retrieval and projections.
- [MongoDB — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/): choosing indexes for queries.
- [MongoDB — Analyze Query Performance](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/): running and interpreting `explain`.
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/): memory limits and disk spills.
- [MongoDB — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): capturing query execution metrics with overhead awareness.
- [MongoDB Atlas — Review MongoDB Metrics](https://www.mongodb.com/docs/atlas/review-available-metrics/): cache, CPU, disk, and operation charts.
- [MongoDB — Operational Factors and Data Access Patterns](https://www.mongodb.com/docs/manual/administration/production-notes/): filesystem, storage, and production considerations.
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): `find`, projection, sort, and limit.
- [MongoDB Java Sync Driver — Explain](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/explain/): using `explain` to inspect execution plans.

**Version note:** WiredTiger metric names, query planner behavior, aggregation spill defaults, Atlas monitoring charts, and container memory sizing support can vary across MongoDB Server releases, FCV, drivers, and platforms. Verify against your exact version before changing production configurations.

## 56. Conclusion

The **working set** is the subset of data and indexes accessed repeatedly, not the entire database. With MongoDB WiredTiger, pages are cached in the **WiredTiger internal cache** and can also be served from the **OS page cache** before reaching SSD/cloud storage.

**Disk reads** are far slower than memory accesses and can drive up **p95/p99 latency**, especially as random I/O, queue depth, and storage saturation climb. Yet a WiredTiger cache miss does not automatically mean a physical disk read, and `FETCH` in `explain` does not prove disk I/O occurred.

To tune systematically: **inspect query plans and docs/keys examined, identify hot data/index pages, correlate WiredTiger cache/eviction metrics with disk I/O, and fix access paths**. Scaling RAM, IOPS, SSDs, sharding, or archiving should only happen once metrics prove they address the actual bottleneck.

A multi-terabyte MongoDB cluster can still serve queries rapidly if the workload is focused, indexes are sound, and the hot working set fits in cache. Conversely, even a small collection can be slow if queries scan poorly, storage saturates, or workloads contend for resources.

**Do not optimize merely to make a cache chart "look less full" or disk "read slightly less"; optimize so critical queries touch only the right data, avoid needless I/O, and meet real latency SLOs.**
