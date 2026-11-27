# Data Compression, Index Compression, and CPU vs. Storage Trade-offs in MongoDB

MongoDB stores data as BSON and typically uses the **WiredTiger** storage engine. In WiredTiger, compression reduces the number of bytes stored and exchanged with the storage device, though compressing and decompressing requires CPU. Indexes, on the other hand, commonly use **prefix compression** to exploit repeated leading key segments. Therefore, choosing compression settings is not merely about making database files smaller: it affects disk read frequency, CPU utilization, working set size, write speed, query latency, and infrastructure costs.

This lesson explains the mechanisms from an architectural perspective, guides measurement using MongoDB commands, and provides a workflow for choosing workload-appropriate configurations. Examples target MongoDB with WiredTiger; parameter names, default behaviors, and specific metrics should be cross-checked against your **deployed MongoDB version** before applying to production.

## 1. Distinguishing Different Kinds of "Compression"

The term *compression* in MongoDB can refer to mechanisms at completely different layers. Failing to distinguish them leads to wrong decisions: enabling wire compression does not automatically make collections smaller on disk, and shrinking collection size does not mean indexes shrink proportionally.

| Layer | Target | Typical Mechanism | Goal | Key Trade-off |
|---|---|---|---|---|
| Document/BSON | Document fields and values | Schema design, appropriate data types; optional app-level compression | Reduce logical data size before storage | Hard to query fields if entire payload is compressed in the app |
| Collection on disk | WiredTiger data blocks/pages written to storage | Block compression: `snappy`, `zlib`, `zstd`, or `none` | Reduce storage footprint and I/O | Compression/decompression CPU, latency variance |
| Index | Ordered keys inside index structures | Prefix compression for keys sharing common prefixes | Reduce index footprint | Key/page processing overhead; benefit depends on key distribution |
| Journal | Write data for crash recovery | Engine-configured journal compression | Reduce journal write volume/footprint | CPU on the write path and durability requirements |
| Network | Packets between client and server | Wire protocol compression when negotiated by both sides | Reduce bytes transferred over network | CPU on both ends; effectiveness depends on payload |
| Backup | Exported/snapshot/backup data | Compression by backup tool or service | Reduce backup storage and transfer size | Backup/restore CPU and restoration duration |

**Focus of this lesson:** block compression for collections and prefix compression for indexes. The remaining layers must be recognized to avoid measuring the wrong thing.

### What Is Not Data Compression?

- **Projection** returns only needed fields from a query: reduces returned data and often processing cost; does not directly compress storage files.
- **Indexes** avoid reading unnecessary documents; creating indexes generally **increases** total database footprint even though queries run faster.
- **TTL** deletes data after an expiration period: helps manage retention and live data volume, not a compression algorithm.
- **Sharding** splits data across multiple shards; does not reduce total logical data size on its own.
- **Replication** creates data copies for high availability; it typically multiplies total cluster storage by the number of replicas.

## 2. How Does WiredTiger Handle Data in Memory and on Disk?

Let's follow the simplified lifecycle of a document:

~~~mermaid
flowchart LR
    App["Application / MongoDB driver"] --> BSON["BSON Document"]
    BSON --> Cache["WiredTiger cache: data pages processed in memory"]
    Cache -->|"reconcile / write page"| Compressor["Block compressor"]
    Compressor --> Disk["Compressed blocks on storage"]
    Disk -->|"read block"| Decompress["Decompress"]
    Decompress --> Cache
    Cache --> Result["Query execution / result"]
~~~

The diagram omits many details of the write path, checkpoints, eviction, and the journal, but highlights the core point:

1. The application sends/receives BSON documents; the engine manages pages and storage structures.
2. WiredTiger maintains active pages and data in cache for fast access.
3. When writing pages out to the storage device, the block compressor can reduce bytes on disk.
4. When reading a page not yet in cache, the engine reads the stored block and decompresses it for use.
5. A cache-hit read avoids reading and decompressing blocks from disk.

Key point to remember: **compressed size on disk does not equal the RAM required for the working set**. Pages, documents, and management structures in cache still carry memory overhead; cache eviction, in-flight data, and OS cache layers make the picture more complex than dividing by a compression ratio.

### Pages, Blocks, and Locality

WiredTiger organizes data as B-trees and manages pages; compressed blocks on disk are storage-mechanism units, not necessarily one-to-one with a single document. One page can contain multiple documents or keys; data repetition **within the compressed blocks** affects efficiency.

For example, many documents sharing `tenantId: "tenant-a"`, `status: "ACTIVE"`, and repetitive text fields offer strong compression opportunities. Conversely, already-compressed payloads, encrypted data, or random strings leave few useful repeating patterns.

**Do not infer that "a long document will always compress well."** Repetitive content within the block, page size, write order, data distribution, and algorithm choice all have an impact.

## 3. Collection Block Compression

WiredTiger supports common compressors:

| Configuration | Practical Characteristics | When to Consider |
|---|---|---|
| `snappy` | Prioritizes compression/decompression speed, typically moderate ratios | Latency-sensitive workloads wanting reduced I/O at relatively low CPU cost |
| `zstd` | Typically provides strong compression ratios at competitive speeds; CPU depends on data and deployment level | Large datasets, expensive storage/I/O, spare CPU; measure on real workloads |
| `zlib` | Traditional compression algorithm; can achieve strong ratios but usually consumes more CPU | Workloads prioritizing storage savings and accepting processing overhead |
| `none` | No block compression at the collection layer | Comparative testing or workloads with incompressible data / CPU constraints |

Many WiredTiger deployments use `snappy` as the collection default. However, **do not assume which compressor a running cluster uses** merely from knowing the storage engine name: deployments may be configured differently, and collections created at different times may carry different settings.

### 3.1. Why Can Fewer Bytes on Disk Improve Performance?

Suppose a query must read 100 MiB of logical data from blocks not yet in cache:

- Uncompressed: may need to transfer a larger volume of bytes from storage into memory.
- Compressed: may transfer only a fraction of those bytes and spend CPU to decompress.

When disk or storage networking is the bottleneck, reducing physical bytes can significantly lower I/O wait time. For workloads repeatedly accessing hot data already in cache, benefits from smaller on-disk size may be much smaller. If CPU is already near saturation, decompression cost can become the new bottleneck.

A simple mental model:

~~~text
Data processing time on cache miss
    is influenced by:
    wait and read time for block from storage
    + decompression / page reconstruction cost
    + query processing cost

Overall system throughput
    is capped by whichever resource saturates first:
    CPU, I/O, RAM/cache, network, lock/contention,
    or workload concurrency limits.
~~~

Execution steps can overlap or run in parallel, so this is a qualitative model, **not an absolute additive formula to predict latency**.

### 3.2. Illustrative Numerical Example

Suppose a scan must read logical data equivalent to 100 GiB, effective disk read throughput stays constant at 200 MiB/s, and all other overhead is ignored:

| Hypothetical Option | Data Read from Disk | Minimum Pure I/O Time in Model |
|---|---:|---:|
| Uncompressed | 100 GiB | 512 seconds |
| Compressed to 62% | 62 GiB | ~317 seconds |
| Compressed to 45% | 45 GiB | ~230 seconds |

**These ratios are hypothetical to illustrate the math, not benchmark results for Snappy/Zstd/Zlib.** Real duration can be much lower or much higher due to caching, random reads, decompression CPU, page size, parallelism, queries, and storage device behavior. If the 45%-ratio option saturates CPU, it can still deliver worse throughput or p99 latency than the 62%-ratio option.

## 4. Index Compression with Prefix Compression

WiredTiger indexes are typically B-tree structures holding entries ordered by key. In a compound index, keys combine multiple fields. Among entries close together in sort order, many leading key bytes may be identical.

**Prefix compression** exploits repeated leading bytes across adjacent keys to avoid storing duplicate prefixes repeatedly. Distinguish it from block compression:

- Block compression looks for compressible patterns inside collection block contents.
- Prefix compression exploits **ordering and shared prefixes of index keys**, especially useful when many entries share values in the leading components of a compound key.
- Index prefix compression does not mean MongoDB stores only one copy of each key or removes entry uniqueness; the engine must still distinguish every individual key and document reference.

### 4.1. Multi-Key Compound Index Illustration

Suppose the `orders` collection contains documents:

~~~javascript
{
  _id: "order-1001",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:00:00Z")
}
{
  _id: "order-1002",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:05:00Z")
}
{
  _id: "order-1003",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:10:00Z")
}
~~~

Index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
})
~~~

Adjacent keys share `tenant-001` and `PAID` at the start, creating an opportunity for prefix compression. Logical visualization (not WiredTiger's actual byte format):

~~~text
Full key 1: [tenant-001 | PAID | 2026-02-01 09:10]
Full key 2: [tenant-001 | PAID | 2026-02-01 09:05]
Full key 3: [tenant-001 | PAID | 2026-02-01 09:00]

Conceptual representation:
  [tenant-001 | PAID | 09:10]
  [same prefix as previous key | 09:05]
  [same prefix as previous key | 09:00]
~~~

In this example, the repeating prefix provides a compression opportunity **on the encoded key bytes**; the real algorithm handles formatting, page boundaries, and metadata in its own way. Do not assume every key saves the exact number of characters omitted in the illustration.

### 4.2. When Index Compression Is Effective vs. Limited

| Key/Data Shape | Prefix Compression Opportunity | Reason |
|---|---|---|
| Many orders with identical `tenantId` and `status` | Generally good | Many adjacent keys share identical leading bytes |
| String keys with meaningful prefixes | Potentially good | Adjacent keys share repeating prefixes |
| Keys starting with random, widely distributed values | Potentially limited | Few shared prefixes between adjacent keys |
| Multi-field index where leading values change constantly | Data-dependent | Adjacent keys do not necessarily share long prefixes |
| Small index fitting entirely in cache | I/O benefit may be small | Query cost may lie in CPU or elsewhere |

Common mistakes to avoid:

1. **Do not reorder fields in a compound index just to improve compression.** Index key order must first serve filters, sorts, ranges, cardinality, and query performance.
2. **Do not confuse index prefix compression with query prefix search.** A query starting with a prefix regex/string is a separate query-planning topic.
3. **Do not infer index compression percentage solely from `totalIndexSize`.** You need controlled comparisons over identical data.
4. **Do not assume a smaller index is always better.** A larger compound index tailored to queries can save far more CPU and I/O than a tiny unhelpful index.

### 4.3. Role of Indexes in RAM

Shrinking index footprint can reduce I/O and help more index structures fit into the working set. However, RAM usage still depends on active pages, in-cache page format, number of indexes, access patterns, and WiredTiger cache configuration. **Do not take compressed on-disk index size as a direct forecast of cache requirements.**

## 5. Configuring Compression in MongoDB

In WiredTiger deployments, common server parameters include:

~~~yaml
# Illustrative configuration example; use only after checking version docs.
storage:
  wiredTiger:
    collectionConfig:
      blockCompressor: zstd
    indexConfig:
      prefixCompression: true
~~~

- `storage.wiredTiger.collectionConfig.blockCompressor`: selects the default compressor for collections created by WiredTiger under applicable configuration.
- `storage.wiredTiger.indexConfig.prefixCompression`: controls index prefix compression within applicable configuration scope.

Depending on version, MongoDB also supports setting storage engine options at collection/index creation time. Exact options and syntax should be checked against documentation for your **specific version**.

**Configuration lifecycle note:** Changing server-level defaults does not guarantee existing blocks/indexes are immediately rewritten with the new algorithm. When testing or planning a compressor migration, verify precisely whether it applies to **newly created objects**, newly written data, rewritten pages, or requires a controlled rebuild/migration procedure. Avoid assuming that editing YAML and restarting instantly converts the entire historical footprint.

### What Not to Do Directly in Production

- Do not change the compressor at the same time as changing schemas, indexes, and topology and then attribute latency differences to compression.
- Do not batch-rebuild collections/indexes without estimating free disk space, I/O, node load, and operation duration.
- Do not run heavy benchmarks on a live primary serving production traffic to evaluate "before/after."
- Do not use file size after deleting many documents as proof that the compressor works poorly; disk reuse, fragmentation, and page structures retain allocated space.
- Do not select `none` merely because CPU is high; measure what operations are actually consuming CPU.

## 6. How to Measure Storage Footprint and Compression Effectiveness

Collect **logical size**, **allocated physical storage size**, **index size**, **host resources**, and **query latency**. A single number cannot fully explain compression benefits.

### 6.1. Common Statistics Fields

~~~javascript
use mongo_learning

const s = db.orders.stats()
printjson({
  count: s.count,
  size: s.size,
  avgObjSize: s.avgObjSize,
  storageSize: s.storageSize,
  totalIndexSize: s.totalIndexSize,
  indexSizes: s.indexSizes,
  totalSize: s.totalSize
})
~~~

Common meanings:

| Field | How to Read It |
|---|---|
| `count` | Number of documents in the collection |
| `size` | Reported logical size of documents, not identical to bytes stored on disk |
| `avgObjSize` | Average logical size per document |
| `storageSize` | Allocated storage footprint for the collection; reflects compression and space management |
| `totalIndexSize` | Total footprint of indexes as reported by engine stats |
| `indexSizes` | Per-index footprint (when present in output) |
| `totalSize` | Combined collection and index footprint as computed by stats |

A ratio for **rough reference**:

~~~text
approximate_collection_ratio = storageSize / size

If size = 2,000 MiB and storageSize = 800 MiB:
  ratio = 0.40  (~60% less than logical size)
~~~

This is **not the pure algorithmic compression ratio**. `storageSize` may include page overhead, unused preallocated space, reusable free space, and observation-timing effects. Also note `size` excludes index and journal overhead. When `size` is very small, the ratio can be meaningless; avoid dividing by zero or drawing conclusions from a handful of documents.

### 6.2. Distinguishing Logical Size from BSON Size

To inspect per-document BSON sizes across a sample:

~~~javascript
db.orders.aggregate([
  { $sample: { size: 50 } },
  {
    $project: {
      _id: 0,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  {
    $group: {
      _id: null,
      avgBsonBytes: { $avg: "$bsonBytes" },
      maxBsonBytes: { $max: "$bsonBytes" }
    }
  }
])
~~~

This example returns data only if the collection exists and contains documents. `$bsonSize` measures BSON at the document layer, **not the bytes of a document after WiredTiger block compression**. Sampling also does not replace population-wide statistics if the dataset contains widely varying document groups.

### 6.3. Observing Indexes and Host Resources

~~~javascript
db.orders.getIndexes()

// Way to observe index usage (access counts), not compression ratio.
db.orders.aggregate([
  { $indexStats: {} }
])

// High-level server/WiredTiger stats; exact fields depend on version.
const status = db.serverStatus()
printjson(status.wiredTiger && status.wiredTiger.cache)
~~~

`$indexStats` reports index usage counts during the system's observation window, not whether an index "compresses well." Cache and block I/O metrics in `serverStatus` must also be checked against version-specific definitions. Some commands require appropriate monitoring privileges.

On the infrastructure side, capture at minimum:

- CPU utilization per **core**, CPU saturation, and request processing time.
- Disk read/write throughput, IOPS, latency, and queue depth.
- WiredTiger cache usage, read/eviction pressure, and cache misses or storage read indicators.
- Query and update p50/p95/p99 latencies; actual throughput.
- Data/index sizes, free disk space, and growth rate.
- Replication status, backups, and background jobs that could skew numbers.

## 7. Experiment: Compressible vs. Incompressible Data

The following experiment uses a **dedicated learning environment**. Create the exact same dataset on two or more independent MongoDB instances with different compressors, keeping version, hardware resources, topology, and queries identical. A small sample suffices to see behavior; trustworthy benchmarks need sufficiently large, representative datasets.

### 7.1. Generating Data with Repetitive Structure

In `mongosh` on a lab instance:

~~~javascript
use mongo_compression_lab

const coll = db.events
const repetitive = "event-source=checkout;tenant=alpha;".repeat(30)

let batch = []
for (let i = 0; i < 10000; i++) {
  batch.push({
    _id: i,
    tenantId: "tenant-" + String(i % 5).padStart(3, "0"),
    status: i % 3 === 0 ? "PAID" : "CREATED",
    kind: "CHECKOUT",
    createdAt: new Date(Date.UTC(2026, 0, 1, 0, 0, i)),
    sequence: i,
    payload: repetitive
  })

  if (batch.length === 500) {
    coll.insertMany(batch)
    batch = []
  }
}

coll.createIndex({ tenantId: 1, status: 1, createdAt: -1 })

const s = coll.stats()
printjson({
  count: s.count,
  logicalBytes: s.size,
  storageBytes: s.storageSize,
  indexBytes: s.totalIndexSize,
  indexSizes: s.indexSizes
})
~~~

**Run only once on an empty collection.** Re-running with the same `_id` values will raise duplicate key errors; that is expected behavior. Never drop databases containing non-lab data.

The repetitive payload above creates favorable conditions for compression. Actual ratios depend on blocks and instance settings, so do not assume exact numbers upfront.

### 7.2. What Does Hard-to-Compress Data Look Like?

A dataset can be harder to compress when it contains:

- Randomly generated token strings with high entropy.
- Pre-compressed bytes (JPEG, ZIP, MP4, GZIP, etc.) using their own algorithms.
- Application-encrypted payloads where ciphertext has high entropy.
- Heterogeneous binary data with few repeating patterns across documents.

You cannot run a valid comparison by simply generating a short incrementing string and calling it "random." Random data must come from an appropriate generator or a representative production workload; a fair benchmark controls both **logical size** and **access patterns**, not just document count.

### 7.3. Measuring Before and After Under the Same Workload

Example query with filter and sort:

~~~javascript
db.events.find({
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") }
}).sort({ createdAt: -1 }).limit(100).explain("executionStats")
~~~

Measure across multiple phases:

1. **Warm-up:** run queries long enough to observe steady cache behavior or explicitly separate cold-cache vs. warm-cache runs.
2. **Read-heavy:** point lookups, range queries, and representative aggregations.
3. **Write-heavy:** inserts/updates at matching rates, batch sizes, indexes, and concurrency levels.
4. **Mixed workload:** read/write ratio close to production, not just sequential scans.
5. **Scale:** grow data beyond the working set to observe cache misses and storage I/O.

When comparing a `snappy` instance against a `zstd` instance, keep all other variables as identical as possible: logical documents, index count, JVM/application, connection pool, hardware, test timing, filesystem, replica set, journal, cache, and read/write strategies.

## 8. Decision Matrix: Balancing CPU, Disk, and Latency

### 8.1. Common Workload Cases

| Workload | Potential Bottleneck | Decision to Validate |
|---|---|---|
| Many range queries, data larger than RAM | Disk throughput, IOPS, cache misses | A higher-ratio compressor may reduce I/O; measure decompression CPU and p95/p99 |
| Read-heavy, indexes fit in memory | Query-processing CPU, network, contention | Changing block compressor may have little impact; prioritize queries/indexes/projections |
| Continuous writes, high CPU | Write CPU, index updates, compression | A faster compressor may reduce CPU; monitor disk writes and durability |
| Very large dataset, expensive storage | Disk capacity, backups, I/O | Test a more space-efficient compressor; calculate total operational cost |
| Already-compressed multimedia data | Low additional compression yield | Test `none` or a fast compressor in lab; consider where blobs are stored |
| Multi-tenant with repeated index prefixes | Index footprint, cache pressure | Keep prefix compression; measure index sizes and real latency |
| Highly p99-sensitive workload | CPU jitter, page faults, I/O | Measure tail latency at peak load; do not pick based on average size |

### 8.2. How to Read Benchmark Results

Suppose two configurations A and B yield **hypothetical** results:

| Metric | A | B |
|---|---:|---:|
| Collection footprint | 300 GiB | 210 GiB |
| Peak CPU | 55% | 88% |
| Disk read throughput | 220 MiB/s | 150 MiB/s |
| p95 query latency | 45 ms | 48 ms |
| p99 query latency | 90 ms | 160 ms |

B saves 90 GiB on the collection and lowers read bytes, yet CPU approaches saturation and p99 rises. For a service requiring p99 under 100 ms, B fails the requirement despite a smaller footprint. If the workload consists mostly of off-hours batch jobs and storage is a major cost driver, B could be worth trying. **You cannot conclude from compression ratio alone**; consider SLOs, scalability, write throughput, backup/restore, and hardware costs.

### 8.3. Total Cost Accounting

An economically sound compression configuration balances at least:

~~~text
Approximate total cost:
  primary data storage
  + index storage
  + replica set copies
  + backups and retention
  + CPU/servers needed to sustain throughput
  + storage I/O or network storage throughput
  + risk of missing SLOs / recovery duration
~~~

For example, saving 25% storage per node in a replica set can be substantial at scale. However, if you have to upgrade CPUs across every node to maintain throughput, total cost might actually go up. The problem is never merely picking the algorithm with the highest **compression ratio**.

## 9. Factors That Make Compression Metrics Misleading

### 9.1. Dataset Too Small

Collections with a handful of documents are dominated by page overhead, metadata, and storage allocation. The `storageSize / size` ratio can exceed 1; that is not necessarily a bug.

### 9.2. Many Documents Deleted

After deletions, WiredTiger can reuse allocated regions inside files instead of immediately returning every byte to the OS. Seeing on-disk files not shrink does not prove the compressor failed. Evaluating post-deletion footprint requires understanding free space, compaction, and version-specific management policies.

### 9.3. Hot Cache Masking I/O Cost

If queries repeatedly hit data already in cache, the storage compressor may barely affect latency. Benchmarks must distinguish cache-hot from cache-cold without running reckless cache-clearing actions in production.

### 9.4. Workloads Differing Between Measurements

New indexes, new queries, shifted read/write ratios, different connection counts, or dataset drift can swing results far more than changing compressors. Avoid causal claims without controlling these factors.

### 9.5. Forgetting Indexes or Replicas in Calculations

Collection `storageSize` does not reflect total database cost. You must add indexes, journal/backup needs, replicas, logs, and capacity headroom. Strong document compression does not mean total system footprint drops by the same percentage.

### 9.6. Pre-Compressing in the Application

An application can compress a binary field itself before storing it in MongoDB. This shrinks the BSON payload, but also prevents querying or indexing that field's contents normally; it requires versioning, integrity checks, and decompression logic. Data compressed once rarely benefits much from subsequent block compression.

### 9.7. Encryption and Random Data

Ciphertext is designed to conceal repeating patterns. Consequently, compressing externally after encryption is typically ineffective; compression/encryption decisions must account for security mechanisms, queryability, and sensitive data without inventing custom pipelines that risk leaking information.

## 10. Prefix Compression, Index Design, and Write Amplification

Reducing index footprint allows storing more index entries/pages in the same storage budget. However, **every index must still be updated whenever a document changes on relevant fields**. Creating too many indexes can:

- Increase write operations, CPU, and I/O due to updating multiple B-tree structures.
- Increase cache requirements and maintenance/rebuild durations.
- Increase backup and replication overhead due to write amplification and auxiliary data size.
- Hurt throughput during bulk imports or mass document updates.

Prefix compression makes some indexes cheaper in space, **not zero-cost to maintain**. Therefore, index sets must be chosen based on access patterns and `explain()` results, never added just because they compress well.

Example of two distinct queries:

~~~javascript
// Query A: order history by tenant and status.
db.orders.find({
  tenantId: "tenant-001",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20)

// Query B: find any order containing productId in the items array.
db.orders.find({ "items.productId": "p-101" }).limit(20)
~~~

The index `{tenantId: 1, status: 1, createdAt: -1}` may fit Query A, yet it does not optimize Query B. Query B needs separate analysis around multikey indexes, selectivity, and business requirements. Never choose key ordering just to lengthen a compressible prefix.

### Does Index Compression Affect Correctness?

Storage/index compression is a physical data representation mechanism. At the logical layer, query predicates, sort orders, unique constraints, and lookup keys must still obey MongoDB semantics. A valid index configuration cannot "mix up" two distinct keys merely because they share a prefix. If query results look wrong, inspect schemas, types, collations, filters, indexes, and application code rather than suspecting prefix compression corrupted data.

## 11. Operating Compression in Replica Sets and Sharded Clusters

Production MongoDB rarely consists of a single process. When changing compression algorithms, evaluate the entire topology:

1. **Replica set:** Each node has its own storage and resources; collection creation history/configs may differ. Replicated logical data does not mean compressed on-disk bytes must match across nodes.
2. **Secondaries:** Receiving and applying writes via replication still generates CPU/I/O load; monitor replication lag after storage changes.
3. **Failover:** When the primary changes, the new primary must handle full read/write traffic; benchmarking only the current primary is insufficient for capacity planning.
4. **Sharding:** Data distribution by shard key can yield shards with varying compressibility; measure per shard and cluster-wide.
5. **Backup/restore:** Logical restores may rewrite data under new compressor settings; restore duration and footprint should be verified. Different backup approaches have different semantics.
6. **Rolling operations:** When rolling out configuration changes across multiple nodes, plan for version compatibility, controlled rollout, and availability monitoring—do not switch everything at once.

Low CPU on one node does not prove the whole cluster has spare CPU. When Shard A carries most traffic or the primary just failed over to a smaller node, compression overhead can behave differently than predicted.

## 12. Practical Process for Choosing a Compressor

### Step 1 — Define the Problem to Solve

State the current **constraint**: disk capacity, IOPS, throughput, CPU utilization, or p99 latency. Without a clear bottleneck, changing compressors can add risk with no benefit.

### Step 2 — Map Your Data

Record the largest collections, field types, share of repetitive payloads, pre-compressed/encrypted binary data, growth rate, index count, and working-set-to-RAM ratio. Separate hot operational data from historical data.

### Step 3 — Define a Representative Workload

Select real query types and request proportions: point lookups, range queries, aggregations, inserts/updates/deletes, background index builds, and backups. Record concurrency, batch sizes, read/write concern, and cache state.

### Step 4 — Build Test Environments

Hold MongoDB version, logical data, topology, index count, host specs, drivers, and query settings constant. Vary only the compressor setting across comparisons. When testing index prefix compression, compare indexes built under identical conditions and data volumes.

### Step 5 — Collect a Full Metric Suite

Capture collection/index footprints, CPU, I/O, cache pressure, throughput, p95/p99, write latency, replication lag, and restore timings if evaluating a production change. Run multiple trials across load levels and record variance ranges.

### Step 6 — Decide by SLOs and Recoverability

If a compressor saves storage yet pushes p99 beyond SLO or raises replication lag past targets, do not adopt it merely for smaller byte counts. Document the accepted trade-offs with data, rollout scope, and a rollback plan.

### Step 7 — Roll Out in Stages and Observe

Use topology-appropriate configuration change procedures; monitor footprint, CPU, I/O, errors, replication, and latency. Before expanding scope at each stage, verify actual outcomes and confirm you can revert to prior configs/layouts if needed.

## 13. Real-World Diagnostic Scenarios

### Scenario A — Smaller Collection on Disk, Yet Slower API

**Symptoms:** After picking a higher-ratio compressor, `storageSize` drops, but p99 increases.

**Investigation path:**

1. Compare CPU usage, saturation, and cache-miss/I/O metrics before and after.
2. Verify request volume, query plans, indexes, and concurrency stayed constant.
3. Separate queries needing disk reads from cache-hot queries.
4. Check whether tail latency spikes correlate with CPU saturation.
5. Compare against the prior configuration under an equivalent workload.

**Lesson:** Compression cuts I/O but can shift the bottleneck to CPU, especially under high load.

### Scenario B — Indexes Exist, Yet Total Database Keeps Growing

**Symptoms:** Logical data grows modestly, while `totalIndexSize` climbs rapidly.

**Investigation path:** Audit existing indexes, `$indexStats` usage, unused indexes, nearly redundant compound indexes, multikey indexes on arrays, and document count trends. Do not drop an index solely because of low hits in a brief window: seasonal reports, admin queries, and infrequent jobs must also be accounted for.

**Lesson:** Index compression does not replace thoughtful index design and lifecycle governance.

### Scenario C — Disk Stays Full After Deleting Old Data

**Symptoms:** `count` and `size` drop, yet storage files do not shrink proportionally.

**Investigation path:** Distinguish logical size, allocated storage, reusable free space, retention policies, and background operation impacts. If reclaiming filesystem space is necessary, research compaction/resync tools and limits for your version and topology, budgeting for extra temporary space and performance impact.

**Lesson:** Space allocation/reuse mechanisms are distinct from compression ratios.

### Scenario D — Great Compression in Lab, Poor in Production

**Symptoms:** Sample dataset achieved very high compression ratios, while production saves very little.

**Investigation path:** Compare entropy/payloads, index counts, document sizes, binary data types, tenant distributions, collection creation timing, and hot/cold ratios. Specifically check whether the sample contained synthetic repeating strings unlike real data.

**Lesson:** Compression ratio is a property of **data + algorithm + storage layout**, not a fixed constant of the compressor.

## 14. Integrated Practice Exercise

**Context:** An event platform stores 500 million events, each with `tenantId`, `deviceId`, `eventType`, `createdAt`, and `payload`. Common queries fetch the 100 latest events for a tenant/device; nightly batch jobs aggregate events per day. Data older than six months is rarely read, but must be retained for two years. Current hosts occasionally hit I/O limits, while daytime CPU fluctuates high.

### Requirements

1. Design 2–3 data/index options tailored to the concrete queries; explain why you should not index every field.
2. Classify which `payload` fields may repeat versus which are pre-compressed/encrypted and how that affects block compression.
3. Propose an experiment comparing `snappy`, `zstd`, and `none` on representative data; hold queries/indexes/topology constant across runs.
4. Collect `size`, `storageSize`, `totalIndexSize`, CPU, throughput, p95/p99, disk IOPS, and replication lag.
5. Compare cache-hot queries against queries over rarely accessed historical data; explain the difference.
6. Write out the decision rationale if an option saves 30% storage yet pushes p99 past SLO.
7. Propose a separate retention/archival and backup strategy; explain why these are not compression algorithms.
8. Outline a rollout plan on a replica set or sharded cluster with rollback capability and capacity monitoring.

### Sample Measurement Table

| Trial | Collection GiB | Index GiB | Peak CPU | Disk Read MiB/s | p95/p99 ms | Ops/s | Notes |
|---|---:|---:|---:|---:|---|---:|---|
| Snappy | … | … | … | … | … / … | … | Data/query/conditions |
| Zstd | … | … | … | … | … / … | … | Data/query/conditions |
| None | … | … | … | … | … / … | … | Data/query/conditions |

Learners must **fill in their own measured numbers**, rather than reusing the hypothetical table from Section 8 as benchmark results.

## 15. Review Questions and Guided Answers

**1. How do collection compression and index compression differ?**

Block compression compresses collection data when written as blocks to disk. Index prefix compression exploits shared leading bytes across adjacent index keys in an ordered structure. They operate at different layers and savings rates do not directly carry over from one to the other.

**2. Why might a 40% reduction in `storageSize` not reduce RAM usage by 40%?**

`storageSize` reflects the collection's storage footprint; cache also holds pages, processing structures, and the working set rather than keeping the entire dataset in memory at its compressed on-disk byte ratio.

**3. Is the compressor with the highest compression ratio always the best choice?**

Not automatically. CPU, disk I/O, cache misses, p99, throughput, replication lag, RPO/RTO, and cost determine the right configuration for your system.

**4. Should you always reorder compound index keys to maximize shared prefixes?**

No. Key ordering must first satisfy filters/sorts/ranges and access patterns. Changing order can prevent queries from using the index effectively.

**5. Does `$bsonSize` measure compressed on-disk bytes?**

No. It measures the logical document's BSON size, without allocating compressed block bytes to individual documents.

**6. Why don't files shrink proportionally right after deleting data?**

WiredTiger can reuse already-allocated storage regions; file footprint and live data volume do not change linearly. Understand free space and compaction/resync mechanisms before taking action.

**7. Do encrypted data or JPEGs compress much further with WiredTiger?**

Usually there is little room left because the content already has high entropy or was compressed by another algorithm. Exact outcomes should still be measured on real workloads.

**8. Can you conclude an index compresses well from a single look at `indexSizes`?**

No. You need controlled comparisons with identical datasets, index definitions, and environments. `indexSizes` shows current footprint, not a standalone compression ratio.

**9. When can stronger compression increase throughput?**

When a workload is I/O-bound and CPU still has headroom for compression/decompression, cutting physical bytes can speed up overall system processing.

**10. Why test both primary and secondaries?**

Because compression imposes CPU/I/O load on every node, and failover can shift write traffic to another node; replication lag and capacity headroom must also meet targets.

## 16. Architectural Conclusion

Three principles to carry into MongoDB performance and operations lessons:

1. **Understand the exact compression layer:** WiredTiger block compression serves collections, prefix compression serves indexes, while network/journal/backup compression are separate mechanisms.
2. **Measure the whole system:** smaller storage is not automatically better; track CPU, cache, I/O, throughput, and real latencies, especially p95/p99 at peak load.
3. **Decide based on workload and data lifecycle:** algorithms, indexes, data models, backup strategies, topology, and rollback capability all shape long-term cost.

Only when experimental results show a configuration reduces storage while preserving SLOs, durability, and recoverability do you have valid evidence for wider rollout. The goal of compression is not the prettiest compression ratio, but **reliable data storage and retrieval at reasonable resource cost**.
