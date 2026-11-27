# Caching, Compression Chunks, and the Hot Working Set

> **Chapter:** Resource Tuning  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, a distributed wide-column database; focusing on partition keys, query-driven tables, read/write consistency, and CQL operations, replication, compaction, repair, error handling, and Java connectivity.

When Cassandra queries slow down, increasing cache size or lowering `chunk_length_in_kb` are often the first changes people consider. Yet **which cache is missing**, **what data is being read**, and **how many bytes must be decompressed per read** are the deciding questions. A workload repeatedly reading a few small partitions differs greatly from one randomly reading millions of partitions; changing the compression chunk size can cut read amplification for the first workload while raising metadata or compaction costs for another.

This lesson explains the relationship among **caching layers**, **SSTable compression chunks**, and the **hot working set**—the subset of data actually accessed frequently. The goal is choosing settings based on read/write metrics, rather than assuming "high cache hit rate" or "smaller files" always lead to lower p99.

## 1. Learning Outcomes

After this lesson, you can:

1. Distinguish `memtable`, `key cache`, `row cache`, `counter cache`, `chunk cache`, the **OS page cache**, and Java application caches.
2. Explain the `chunk_length_in_kb` unit in SSTable compression and why reading one small cell may require reading/decompressing an entire chunk.
3. Describe how chunk size affects **compression ratio**, **CPU**, **I/O**, **off-heap metadata**, and **query latency**.
4. Estimate the hot working set size and identify hot partitions and cache thrashing using metrics.
5. Design controlled experiments comparing 4/16/64 KiB chunks and cache configurations, measuring p50/p95/p99, I/O, and write cost.
6. Operate safely across Cassandra 3.11/4.x/5.x without copying renamed parameters or applying unsupported options.

## 2. Which Layers Does a Query Traverse?

For a `SELECT` with a **complete partition key**, the coordinator selects replicas based on token, RF, and consistency level; each replica serves the read from current memtables, SSTables, and supporting structures. Each node maintains its **own** caches; there is no cluster-wide cache automatically sharing all query results.

~~~mermaid
flowchart TD
    A["Java application / driver"] --> B["Coordinator and CL"]
    B --> C["Replica serves read"]
    C --> D{"New data in memtable?"}
    D -->|Has readable data| E["Read and merge versions"]
    D -->|Needs SSTables| F["Bloom filter + partition index"]
    F --> G["KeyCache / index summary / index"]
    G --> H["SSTable locations and compression chunks"]
    H --> I{"Uncompressed chunk in ChunkCache?"}
    I -->|Hit| J["Use decompressed buffer"]
    I -->|Miss| K["OS page cache or disk I/O"]
    K --> L["Read compressed chunk and decompress"]
    L --> J
    J --> E
    E --> M["Merge rows/tombstones, page results"]
    M --> B
    B --> A
~~~

This diagram is a **conceptual model**: exact steps and short-circuits can vary by version/SSTable format, query type, data still in memtables, and enabled caches. `RowCache`, when applicable, may serve part of the data earlier than the SSTable read path; do not assume every request always traverses every single node in the figure.

### 2.1. Comparing Memory Layers

| Layer | What Does It Store? | Primary Benefit | Key Caveats |
|---|---|---|---|
| **Memtable** | Recent in-memory mutations prior to flush | Fast writes; can serve reads for data not yet in SSTables | Write-path buffer; not an LRU cache to enlarge arbitrarily for hot data |
| **Key cache** | Partition location info in certain SSTable formats | Skips some index lookups/seeks when reading the same partition | Does **not** store row payloads; effectiveness depends on SSTable format |
| **Row cache** | Partition rows per table caching policy | Cuts underlying reads when a row set is queried repeatedly | Consumes substantial RAM/off-heap; updates erode benefits; usually disabled by default |
| **Counter cache** | Local metadata supporting counter updates | Reduces contention and part of read-before-write cost for counters | Applies only to counter tables; does not replace key/row cache |
| **Chunk cache** | **Decompressed** SSTable buffers inside the Cassandra process | Avoids re-reading/re-decompressing hot SSTable regions | Consumes off-heap; requires checking `file_cache_enabled` and pooling |
| **OS page cache** | Recently read file pages in kernel memory | Avoids physical I/O while data in pages stays hot | May hold **compressed** SSTable bytes; a hit still needs decompression if ChunkCache misses |
| **Application cache** | Business DTOs/results/values in Java or Redis | Avoids calling Cassandra for data suited to TTL/invalidation | You must handle consistency and expiration yourself; does not show in KeyCache hit rate |

Cassandra also uses **Bloom filters** and **index summaries** to skip SSTables that do not contain a partition or locate index regions faster. They also consume memory, yet are not row-data copies like the row cache. KeyCache usability differs between traditional SSTable formats (e.g., BIG) and newer formats; verify the format/version before interpreting metrics.

### 2.2. High Key Cache Hits Can Still Read Heavily from Disk

Suppose an endpoint frequently reads `device_id = X, event_day = D`. KeyCache knows where the partition sits in an SSTable and can skip the position lookup, yet **the payload and relevant SSTables still have to be read and merged**. When a request encounters many SSTables, tombstones, or data absent from OS/ChunkCache, disk I/O and latency remain high.

Therefore, `KeyCache.HitRate = 95%` (a hypothetical example) does **not** mean "95% of queries avoid disk". To find why p99 stays high, compare SSTables per read, OS disk metrics, ChunkCache misses, partition size, and tombstones scanned.

### 2.3. Row Cache Only Helps the Right Query Pattern

In CQL, **table-level** configuration allows:

~~~sql
WITH caching = {
    'keys': 'ALL',
    'rows_per_partition': 32
}
~~~

Per CQL documentation, `keys` accepts `ALL` or `NONE`; `rows_per_partition` can be `NONE`, `ALL`, or a row count. It defines the scope of data cached when reading a partition, **not** a guarantee that every query is always served completely from cache.

Changing the table property alone is rarely enough: **row cache also needs a node-level budget**, such as `row_cache_size` in Cassandra 5.0 configuration, which defaults to **0 (disabled)**. Tables with frequent writes/updates, varied range queries, or large partitions can cause row cache to burn memory with low hit rates. Consider row cache when you have **small, relatively static hot partitions/rows read repeatedly**, then measure before and after.

## 3. What Is a Compression Chunk?

### 3.1. Compression Blocks Live in SSTables, Not CQL Result Pages

Immutable SSTables are split into **uncompressed data chunks** of target size `chunk_length_in_kb` and compressed into blocks written to disk. Each chunk has metadata for locating it; on read, Cassandra identifies the chunks containing the needed bytes, reads **the entire relevant compressed chunk**, and decompresses it to extract the data.

Suppose a 300-byte payload cell sits inside a 16 KiB uncompressed chunk. Without a cache hit, Cassandra may need to read and decompress **the chunk containing that cell**, meaning more bytes pass through the codec than the user payload returned. Actual bytes **on disk** depend on the compression ratio; 16 KiB is the pre-compression size, not a guarantee of exactly 16 KiB of physical I/O. One query can touch multiple chunks, multiple SSTables, or blocks already cached.

~~~text
Pre-compression SSTable model:
|------ chunk A 16 KiB ------|------ chunk B 16 KiB ------|
| ... record X (300 B) ...   | ... other records ...     |

Reading record X when all relevant caches miss:
  locate chunk A -> read compressed bytes of A -> decompress A -> extract record X

If chunk A is already in the in-process ChunkCache:
  decompressed buffer can be reused -> saves corresponding I/O and codec work
~~~

Do not confuse three distinct sizes:

- **`chunk_length_in_kb`:** **uncompressed** data size per SSTable chunk.
- **Driver `page size`:** suggested row count fetched per result page; does not control compression chunks.
- **Filesystem page / OS readahead:** how the kernel/device prefetches data; can make actual reads larger than Cassandra's requested range.

### 3.2. Trade-Offs Between Small and Large Chunks

| Chunk Size | Potential Strengths | Costs/Risks to Measure | Workloads Worth Testing |
|---|---|---|---|
| **4 KiB** | Fewer extra bytes decompressed when reading small, selective rows | More chunks, higher metadata/index and codec overhead; potentially lower compression ratio | Very small, scattered point reads |
| **16 KiB** | Balanced starting point on Cassandra 4.x/5.x | Not guaranteed optimal for tiny rows or wide scans | Mixed point/range reads |
| **64 KiB** | More compression context; often better compression ratio on repetitive data | May read/decompress many extra bytes for point reads; higher cache pressure | Contiguous range reads, fetching many adjacent rows |

These numbers are **experimental variants**, not a fixed ranking. Cassandra 5.0 documentation lists the default chunk as **16 KiB**, whereas older 3.x branches used **64 KiB**. Always inspect the actual schema via `DESCRIBE TABLE`; never infer chunk size from a version or default when a table was created long ago.

Illustrative scenario: a request fetches 1 random 400-byte row. 4 KiB can cut the amount decompressed compared to 64 KiB. Conversely, reading 100 consecutive rows in the same partition can benefit from 64 KiB chunks due to fewer lookups and codec calls; **cache hits, row sizes, compression ratio, and SSTable count** determine the final outcome.

### 3.3. Choosing the Codec Alongside Chunk Size

Common codecs in Cassandra:

| Codec | General Characteristics | When to Consider |
|---|---|---|
| `LZ4Compressor` | Fast compression/decompression, balanced CPU and ratio | Good baseline for many latency-sensitive workloads |
| `ZstdCompressor` | Can compress tighter; CPU depends on level/config | When storage/disk bandwidth savings matter significantly; benchmark first |
| `SnappyCompressor` | Older codec still supported | Compatibility or baseline comparison with existing clusters |
| `DeflateCompressor`/LZ4HC | Can improve compression ratio, typically costs more compression CPU | Only when CPU headroom and write/compaction overhead are measured |

**Do not decouple chunk choice from codec choice.** A "64 KiB saves disk" result may come with higher p99 due to decompressing extra bytes and higher compaction CPU. If data is already compressed or random, enlarging chunks usually yields little compression benefit.

### 3.4. Metadata and Off-Heap RAM Cost

Every compressed SSTable requires metadata mapping chunks to offsets, sizes, and checksums. Smaller chunks mean **more chunks** for the same data volume, which can increase metadata and buffer management overhead. Cassandra 5.x operational docs note that compression metadata uses **off-heap RAM** and grows with disk footprint.

Switching from 64 KiB to 4 KiB can theoretically increase chunk count **16x** for the same uncompressed data; that does not mean metadata RAM or I/O jumps by exactly 16x. Compression ratios, SSTable layout, and companion structures make real costs differ.

Therefore, alongside heap/GC, monitor **RSS, direct/off-heap memory, OS page cache, free RAM, and swap**. Avoid giving all RAM to Cassandra caches and starving the kernel's file cache.

## 4. Hot Working Set: Which Data Exactly Needs to Stay Cached?

### 4.1. Clarifying "Frequently Accessed Data"

The **working set** is the set of keys/partitions/chunks a workload needs during a specific measurement window. The **hot working set** is the subset receiving the highest share of accesses. It changes over time, by query type, and by routed node:

- A dashboard polling 500 active devices every minute may hit the same partitions/chunks repeatedly.
- A reporting job scanning a full year of data may read **huge amounts of cold data**; a small cache will not turn a cold scan into hot hits.
- An IoT system writing continuously to a few devices can create a **hot partition**. Even if its chunks fit in cache, the owning replicas still overload on CPU, network, or compaction.
- With RF=3, each replica has its own caches. A hot partition served across multiple replicas can **duplicate** working sets across nodes depending on CL and replica selection.

Statements like "the top 1% of keys drive 60% of reads" are **hypotheses to measure**, not conclusions drawn from an aggregate keycache histogram. Gather application sampling/telemetry on tenant/device skew, row/byte volume, and timing while avoiding logging raw sensitive keys.

### 4.2. Tight Enough Estimation for Decision-Making

Suppose on **one replica**, within a 15-minute window, 120,000 partitions are read repeatedly. On average, each partition has about 8 KiB of **uncompressed data actually needed** by hot queries. A rough estimate:

~~~text
Hot logical working set ≈ 120,000 × 8 KiB
                        ≈ 937.5 MiB
~~~

This result does **not** mean a 1 GiB row cache will achieve a 100% hit rate:

1. Row cache has overhead, per-partition row limits, eviction, and invalidation on writes.
2. A partition may span multiple SSTables; chunks also contain neighboring bytes, metadata, and tombstones.
3. ChunkCache caches buffers per **chunk**, not per "8 KiB of useful partition data"; scattered reads can yield a much larger actual footprint.
4. OS page cache competes with heap/off-heap for RAM; the hot set shifts hourly and depends on key distribution across nodes.

A practical goal is determining whether **the fraction of requests/bytes accessed repeatedly within Δt** fits inside the cache budget. For example, a 1 GiB cache provides little benefit if requests cycle through 4 GiB of distinct data without repeating within a short window.

### 4.3. Skew, Churn, and Cache Thrashing

| Phenomenon | Signal | Tuning Implication |
|---|---|---|
| **Small, repeating hot set** | Cache hits rise after warm-up; disk reads drop, p99 drops | Favor the right cache type, preserve sufficient headroom |
| **Hot set larger than cache** | Hit rate fluctuates, high eviction/occupancy, disk I/O stays high | Expanding cache may be uneconomical; revisit query/model |
| **Churn** (hot keys shift continuously) | Short cache warmth, persistently high misses | Measure across hours/days instead of short snapshots |
| **Single hot partition** | A few partitions/hot replicas stay slow despite good hit rate | Add buckets/shards, adjust read/write path—don't just add RAM |
| **Large scans evicting hot cache** | Business request p99 spikes after batch jobs | Isolate resources/jobs, throttle scans, pick off-peak windows |
| **Overlapping tombstones/SSTables** | High SSTables per read and tombstones scanned | Inspect write patterns, TTL, compaction/repair; cache won't solve it all |

## 5. Configuring Caches in CQL and cassandra.yaml

### 5.1. Table Level: Key/Row Cache and Compression

Here is a CQL example for Cassandra 4.x/5.x:

~~~sql
CREATE TABLE example_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 16};
~~~

Later, policies can be altered individually:

~~~sql
ALTER TABLE example_by_device_day
WITH caching = {'keys': 'ALL', 'rows_per_partition': 32};

ALTER TABLE example_by_device_day
WITH compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 4};
~~~

**The two `ALTER` commands differ in when they take effect:**

- Caching policy affects how subsequent queries are handled, yet caches do not warm instantaneously and have no effect if the node-level cache budget is 0.
- **SSTables are immutable**, so `compression` changes govern only SSTables **written afterward** (flushes/compactions/rewrites). Existing SSTables retain their old compression settings until rewritten. Do not measure "4 KiB vs 16 KiB" immediately after an `ALTER` when all files still use the old chunk size.

Do not disable compression simply over a slight CPU increase: compression can substantially cut disk I/O and network/streaming traffic. Measure trade-offs on **both reads and writes**, including compaction.

### 5.2. Node Level: Cache Budgets and Version Differences

Some **Cassandra 5.x** parameter names found in `cassandra.yaml`:

~~~yaml
# Illustrates key names only, not a recommended production configuration.
# Check your running distribution/release before applying.
key_cache_size: 100MiB
row_cache_size: 0MiB
file_cache_enabled: false
file_cache_size: 512MiB
~~~

**Do not copy this YAML into Cassandra 4.0**: older releases used unit-suffixed names such as `key_cache_size_in_mb` and `row_cache_size_in_mb`. Newer Cassandra guides switched several keys to unit-aware syntax. Always inspect the config file of your running version, restart/apply rules, and off-heap conditions for that release.

Per 5.x documentation, `row_cache_size` defaults to **0** and `file_cache_enabled` defaults to **false**. When enabled, ChunkCache stores **decompressed** SSTable buffers; `file_cache_size` is an off-heap budget for the chunk cache **and buffer pooling**, not 100% dedicated to cached chunks. The illustrative YAML values do not mean caches should be sized identically on every machine.

When budgeting RAM, reserve room for **JVM heap, memtables, Bloom filters/index summaries, compression metadata, networking/buffer pools, and the OS page cache**. Enabling a large off-heap cache can shrink OS page cache capacity and cause swapping or OOMs on another workload.

### 5.3. SSTable Format and Actual Cache Effectiveness

In certain SSTable formats (such as BIG), KeyCache speeds up partition-to-offset lookups. Newer SSTable formats may use different index structures and **do not use the key cache the same way**. Therefore, before enlarging `key_cache_size`:

1. Confirm the version and the table's actual SSTable format.
2. Check whether Cache Metrics show increasing requests/hits; if that cache isn't used at all, adding capacity helps nothing.
3. Correlate with LocalReadLatency, SSTables per read, and disk I/O.

Never deduce "enlarging key cache fixes p99" from a hit-rate metric alone.

## 6. Lab: Three Compression Chunk Sizes on Identical Data

### 6.1. Experimental Conditions

Prepare an **isolated lab** Cassandra cluster, `cqlsh`, `nodetool`, and a data generator/Java client capable of measuring latency. This example assumes a datacenter named `dc1` with **at least three nodes**; verify via `nodetool status`. If your topology differs, adjust keyspace RF/DC and CL before running.

Record the version with:

~~~sql
SELECT release_version FROM system.local;
~~~

Note that `IF NOT EXISTS` **will not alter an existing schema**. If similarly named tables already exist, inspect their actual definitions or use a fresh lab keyspace to avoid leftover data/chunks from earlier experiments.

### 6.2. Create Three Tables Differing Only in Compression Chunk Size

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_resource
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_resource.events_4k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 4};

CREATE TABLE IF NOT EXISTS lab_resource.events_16k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 16};

CREATE TABLE IF NOT EXISTS lab_resource.events_64k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 64};
~~~

All three tables share the same partition/clustering keys, codec, and caching policy. **The sole actively varied parameter is chunk size.** For a meaningful experiment, load the exact same logical dataset into each table with identical timestamps, key distributions, payload sizes, TTLs, and write pacing; keep RF/CL, compaction strategy, and cluster conditions equivalent.

Insert one test row to verify syntax:

~~~sql
INSERT INTO lab_resource.events_16k (
    device_id, event_day, event_time, event_id, payload
) VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    285f4c95-6fc7-4950-9e3b-1250900aecea,
    'sample-0001'
);
~~~

This is only smoke-test data. When comparing A/B/C, **this exact logical row and all others must exist across all three tables**. A single row cannot yield valid conclusions about compression ratios or latency.

### 6.3. Two Query Classes to Benchmark Separately

**Q1 — Small point/range read, few rows in one partition:**

~~~sql
SELECT event_time, event_id, payload
FROM lab_resource.events_16k
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 10;
~~~

**Q2 — Wider range scan, consuming many rows/pages:**

~~~sql
SELECT event_time, event_id, payload
FROM lab_resource.events_16k
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time <  '2026-11-22T00:00:00Z';
~~~

Repeat both equivalent queries changing **only the table name** `events_4k` / `events_16k` / `events_64k`, targeting partitions with identical data. For Q2, the driver must **consume all pages** if measuring the full scan; do not stop at the first page and report that latency.

### 6.4. Data and Load Dimensions

| Dimension | Levels to Test | Why It Matters |
|---|---|---|
| Average payload | 200 B; 2 KiB; 20 KiB | Reading one row can span multiple chunks |
| Payload type | Repetitive text, JSON, pre-compressed/random data | Compression ratios differ sharply |
| Rows/partition | 10; 1,000; 100,000 | Affects range reads, scans, and hot partitions |
| Key distribution | Uniform; 1% very hot keys | Hot set and cache thrashing |
| Warm-up state | Cold-ish; steady warm | Separates disk vs cache effects |
| Concurrency | 1; 16; 64 clients (scaled to lab hardware) | Tail latency and CPU/IO saturation |
| Read/write ratio | Read-only; 90/10; 50/50 | Codec cost, flushes, and compaction |
| Page size | 50; 500 rows | Network, paging, and round trips |

**Do not call it a "cold cache" test** simply because you switched table names; OS caches and other buffers may still hold similar data. If a true cold test is needed, follow a controlled lab procedure stating warm-up/cool-down steps, and avoid rebooting, dropping caches, or forcing compaction mid-run without documenting the impact.

### 6.5. Measuring and Correlating Per Node

Informational commands:

~~~bash
nodetool status
nodetool info
nodetool tablestats lab_resource.events_4k
nodetool tablestats lab_resource.events_16k
nodetool tablestats lab_resource.events_64k
nodetool tablehistograms lab_resource events_16k
nodetool compactionstats
nodetool tpstats
~~~

In `nodetool tablestats`, inspect **SSTable Compression Ratio**, storage space used, SSTable count, local read/write latency, and partition statistics. Run `tablehistograms` for the other two tables as well. `nodetool info` can provide node-level cache summaries; exact fields depend on the release.

Cross-check JMX/monitoring per [Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html):

| Metric Group | Values to Read | Correct Interpretation |
|---|---|---|
| `Cache.KeyCache.*` | `Hits`, `Requests`, `HitRate`, `Size`, `Capacity` | Index-position hits, **not** payload hits |
| `Cache.RowCache.*` | Hit rate, entries, size if enabled | Effectiveness of caching hot rows per policy and budget |
| `Cache.ChunkCache.*` | Hits, misses, miss latency, size if enabled | Ability to avoid re-reading/decompressing chunks |
| `Table.*.SSTablesPerReadHistogram` | SSTables involved in a single read | Read amplification across multiple SSTables |
| `Table.*.ReadLatency` | Per-table replica read latency | Excludes full coordinator/client overhead |
| `ClientRequest.Read.Latency` | Coordinator latency | Can differ from Java end-to-end p99 |
| OS CPU/GC/RSS/free RAM | CPU load, heap/off-heap memory, RAM pressure | Avoids oversized caches triggering swap |
| OS disk read IOPS/bytes/latency | Physical I/O volume and duration | Measures chunk size impact under equal cache conditions |

Metric names can vary by version/exporter; treat the table as **group names and semantics**, verifying exact names against live JMX. **Node-level** cache metrics do not separate tables automatically: test the three tables sequentially or isolate workloads so table A's hits are not confused with table B's.

### 6.6. Result Table for Recording Real Measurements

Never use hypothetical numbers as results; record measurements observed from the cluster:

| Variant | Q1 p50/p95/p99 (ms) | Q2 p50/p95/p99 (ms) | Disk read MiB/s | CPU % | Compression ratio | Hot cache hit | Timeout % |
|---|---|---|---:|---:|---:|---:|---:|
| LZ4 / 4 KiB | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| LZ4 / 16 KiB | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| LZ4 / 64 KiB | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ | _fill in_ |

Add separate tables for **write p95/p99, flush/compaction backlog, disk footprint, off-heap metadata**. Compare under identical client driver/CL/partition size and concurrency, repeating runs with rotated A/B/C order to reduce cache/compaction bias. Conclude only when input data, row counts, and load conditions match.

## 7. Testing Row Cache and ChunkCache: One Variable at a Time

### 7.1. Row Cache Experiment

With a small hot set and repeated reads of the top rows of partitions, test in the **lab**:

~~~sql
ALTER TABLE lab_resource.events_16k
WITH caching = {'keys': 'ALL', 'rows_per_partition': 32};
~~~

Prerequisites: node-level `row_cache_size`/`row_cache_size_in_mb` must allocate a budget > 0 in the corresponding release, following admin procedures and valid restart/apply steps. Compare `NONE` vs `32` after warm-up on the same query; measure **RowCache hits, RSS/off-heap, and p99**, especially while updating some hot rows.

Do not use a read-only benchmark to conclude row cache helps write-heavy workloads. Run an update phase as well and measure cache invalidation, memory pressure, and read/write latency.

### 7.2. ChunkCache Experiment

Cassandra 5.x `cassandra.yaml` docs describe `file_cache_enabled` to enable **SSTable ChunkCache** and `file_cache_size` to cap the off-heap region for chunk caching/buffer pooling. Enable it in a **lab cluster** with an explicit RAM budget and compare against the default/disabled state. Do not expect row cache and ChunkCache to behave identically: one caches rows, while the other caches **decompressed SSTable chunks**.

Your matrix should include at least:

| Scenario | RowCache | ChunkCache | Access Distribution |
|---|---|---|---|
| A — baseline | Off | Off | Many partitions, realistic read/write |
| B — row cache | Bounded on | Off | Few hot partitions, repeated reads |
| C — chunk cache | Off | Bounded on | Repeated point/range reads hitting SSTables |
| D — combined | Bounded on | Bounded on | Test only after understanding B/C and verifying RAM |

**Keep chunk size fixed** when measuring cache effects. Conversely, **keep cache policy fixed** when comparing 4/16/64 KiB. Mixing both changes makes it impossible to tell what caused the win or loss.

### 7.3. When Caches "Hit" Yet P99 Stays Bad

Check in order: is the query missing the partition key, reading too many rows/SSTables/tombstones, hitting an overloaded hot partition, waiting on replicas/CL, suffering GC/CPU/disk pressure, or bottlenecked by driver pool/paging limits? Caching cannot fix:

- Cluster-wide scans caused by tables not modeled for the access pattern.
- Reading payloads larger than network/CPU can process.
- Write amplification/compaction saturating the disk.
- Slow or disconnected replicas forcing quorum waits.
- Inefficient application-side paging or deserialization.

## 8. Java Driver: Measuring Latency Accurately on Real Data Volumes

In Java Driver 4.x, prepared statements and paging let you measure workloads close to production application behavior. The example below assumes an initialized `CqlSession session` connected to the cluster and appropriate local DC, querying a populated `events_16k` table:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM lab_resource.events_16k " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT ?");

BoundStatement statement = prepared.bind(
        UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b"),
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T08:00:00Z"),
        Instant.parse("2026-11-21T09:00:00Z"),
        1000)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

long start = System.nanoTime();
ResultSet results = session.execute(statement);
long payloadChars = 0;
int rows = 0;
for (Row row : results) {
    String payload = row.getString("payload");
    if (payload != null) payloadChars += payload.length();
    rows++;
}
long elapsedNs = System.nanoTime() - start;
double elapsedMs = elapsedNs / 1_000_000.0;
// Record into histogram: elapsedMs, rows, payloadChars, table variant, request key.
~~~

Important notes:

- The duration above is **end-to-end across all iterated results**, including subsequent pages; it does not measure only the first page. If the UI only needs the first page, track a **separate metric**.
- `LIMIT 1000` caps returned rows; `setPageSize(100)` controls fetch page size, **not** compression chunks. One request may span multiple pages and multiple chunks.
- Compute p50/p95/p99 across **many partitions and independent repetitions**. Avoid comparing one warm query run against another cold run.
- When changing the table name in prepared statements, prepare the corresponding statement; keep bind values, CL, page size, concurrent clients, and actual payloads identical.
- If data skew is high, track latencies separately for **hot keys vs. cold keys** instead of relying on a single overall p99.

## 9. Evidence-Based Decision Process

~~~mermaid
flowchart TD
    A["Define query pattern and SLO"] --> B["Measure hot working set, skew, disk, CPU, p99"]
    B --> C{"Primary bottleneck?"}
    C -->|Partition lookup| D["Check KeyCache, SSTables/Read, and format"]
    C -->|Repeated same rows| E["Test bounded row cache"]
    C -->|SSTable decompression and reads| F["Test chunk size/ChunkCache"]
    C -->|Hot partition or wide scan| G["Fix partition key, buckets, query"]
    D --> H["Benchmark under equal conditions"]
    E --> H
    F --> H
    G --> H
    H --> I{"Do p99, throughput, RAM, I/O, writes meet SLO?"}
    I -->|Yes| J["Document config, metrics, and validation criteria"]
    I -->|No| K["Analyze metrics then change one variable"]
    K --> B
~~~

### 9.1. Keeping Configurations That Benefit the Whole System

When selecting a setting, save the following in your report:

1. **Primary queries:** point/range/scan mix, partition key predicates, rows/pages, and payload sizes.
2. **Dataset:** partition count, hot set over time, TTL/tombstones, compressibility.
3. **Environment:** Cassandra release, SSTable format, RF/CL, nodes/CPU/RAM/SSD, JVM heap, OS page cache, compaction strategy.
4. **Changed variable:** 4/16/64 KiB chunk or cache policy—one variable per experiment.
5. **Measure both sides:** read p50/p95/p99, throughput, read/write latency, flush/compaction, disk footprint, CPU, off-heap/RSS, errors.
6. **Rollback readiness:** save original schema/config, rollout scope, and monitoring plan; remember compression changes apply only to new SSTables, so effects are not immediately uniform.

If p99 drops yet RSS climbs near limits, OS page cache shrinks sharply, or writes/compaction slow down, the change may **not be worth deploying**. Prioritize product SLOs and total resource cost over a flattering compression ratio.

### 9.2. Easily Mistaken Claims

| Claim | Why It Is Wrong or Incomplete | How to Verify |
|---|---|---|
| "KeyCache hit is 99%, so disk is no longer read." | KeyCache holds no payloads; multiple SSTables/chunks still need access | Compare disk I/O, ChunkCache, SSTables per read |
| "Increasing row cache helps every query." | Hot set may be huge, volatile, or rows heavy to cache | Compare p99 and evictions/hits under real workload |
| "4 KiB chunks are always fastest." | Large scans, codec/metadata overhead, and compression ratio can degrade | Benchmark identical point and range data |
| "64 KiB chunks always save disk." | Random/pre-compressed data gains little while metadata/codec work remains | Measure compression ratio, disk footprint, CPU |
| "After ALTER compression, the whole table changes right away." | Existing SSTables are immutable and change only when rewritten | Inspect SSTable metadata after legitimate compaction |
| "ChunkCache is the OS page cache." | ChunkCache holds decompressed buffers in Cassandra; OS holds file pages | Read both layer metrics plus RSS/disk |
| "Row cache is enabled because CQL caching was set." | The node may have row cache size = 0 | Check YAML/JMX and cache entry counts |
| "Cluster-wide working set fits RAM, so every node has enough." | Each replica has its own data/caches; hot keys may be skewed | Measure per-node hot sets and traffic |
| "Caching solves hot partitions." | Hot keys still hit per-replica CPU/IO limits | Fix partition/bucket/shard design |
| "p50 improved, so tuning succeeded." | Tail latency, GC, compaction, and errors may have worsened | Compare p95/p99, timeouts, and resource budgets |

## 10. Practical Exercises

**Scenario A — Point reads and chunk size.** A table stores small 300-byte rows, and queries usually fetch 1–2 random rows. Compare `LZ4 4 KiB` vs `LZ4 64 KiB`; name two metrics beyond p99 that must be measured.

**Hint:** disk bytes/read and CPU/decompression; also track compression ratio, ChunkCache hits, SSTables per read, and metadata/RSS. Smaller chunks **may** reduce read amplification, yet you lack proof without measurements.

**Scenario B — High cache hit rate yet slow queries.** `KeyCache.HitRate` is 98%, while `SSTablesPerReadHistogram` and disk read latency are both high. What could be happening?

**Hint:** KeyCache only helps locate partitions; payloads may span many SSTables/chunks, hit tombstones, or miss OS/ChunkCache. Investigate disk and compaction rather than simply enlarging key cache.

**Scenario C — Changed compression yet saw no difference.** You just ran `ALTER TABLE ... chunk_length_in_kb: 4`, yet disk usage and latency stayed virtually identical. Why?

**Hint:** Existing SSTables keep their old compression; you must wait for files to be rewritten via flushes/compaction or a version-appropriate rewrite procedure. Never force major compaction in production just to get benchmark numbers.

**Scenario D — 2 GiB hot set, 1 GiB row cache.** There are 250,000 hot partitions; cache hit rate fluctuates and GC/OS cache pressure rises. Should you raise row cache to 3 GiB?

**Hint:** you cannot decide from simple arithmetic. Measure overhead, per-node distribution, write/invalidation rate, memory headroom, and p99. You may need to shrink payloads, change partitioning/bucketing, or cache only the genuinely useful read model.

**Scenario E — Different versions.** A Cassandra 4.0 runbook uses `key_cache_size_in_mb`; a 5.0 environment uses `key_cache_size`. Describe the checks before migrating the config.

**Hint:** confirm `release_version`, inspect `cassandra.yaml` and matching docs, verify units/defaults, SSTable format, heap/off-heap budgets, apply/restart rules, and rollback; test in a lab with metrics.

### Lab Submission Checklist

- [ ] Explained the distinct roles of KeyCache, RowCache, ChunkCache, and the OS page cache.
- [ ] Explained why reading a small value can require decompressing an entire SSTable chunk.
- [ ] Verified release/version, DC name, RF/CL, and schema/caching/compression of all three tables.
- [ ] Used equivalent logical data and benchmark conditions for 4/16/64 KiB.
- [ ] Recorded p50/p95/p99, compression ratio, CPU, disk bytes, RSS/off-heap, write latency, and errors.
- [ ] Tested hot/cold working sets and key distributions rather than a single hot key.
- [ ] Understood row cache requires both CQL table policy and node-level budget.
- [ ] Did not infer compression results right after `ALTER TABLE` before old SSTables were rewritten.
- [ ] Chose configuration based on empirical SLOs with a monitoring and rollback plan.

## 11. References

1. Apache Cassandra Documentation — [Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html): read path, SSTables, memtables, Bloom filters, and index components.
2. Apache Cassandra Documentation — [Compression](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compression.html): codecs, chunk size, read amplification, metadata costs, and when `ALTER TABLE` takes effect.
3. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): table `caching` and `compression` properties.
4. Apache Cassandra Documentation — [cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): node-level cache budgets, `file_cache_enabled`, and off-heap settings.
5. Apache Cassandra Documentation — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): Cache Metrics, Table Metrics, and ClientRequest Latency.
6. Apache Cassandra Documentation — [Configuration naming changes](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/configuration.html) and [Cassandra 4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html): version-specific parameter differences.
7. Apache Cassandra Documentation — [Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html): I/O readahead and compression chunk sizing.
