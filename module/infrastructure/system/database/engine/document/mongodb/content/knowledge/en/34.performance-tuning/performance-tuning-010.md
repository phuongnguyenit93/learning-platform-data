# Capacity Planning, Resource Scaling, and Avoiding Tuning on Overly Small Test Data in MongoDB

## 1. Why Can a System That Runs Fast with 10,000 Documents Still Be Slow in Production?

A retail application uses MongoDB to store orders. In the development environment, the engineering team creates 10,000 orders, runs a few **find()** queries, creates an index, and sees response times of only a few milliseconds. The team concludes that a machine with 4 vCPUs, 8 GiB RAM, and a 100 GiB disk will be enough for three years.

Six months later, production has 50 million orders, 2 million customers, several very large tenants, hundreds of concurrent users, and many batch jobs. At that point:

- Queries that used to be fast now scan many documents.
- Indexes are larger than the cache, generating many disk reads.
- CPU rises due to aggregations, compression/decompression, and index maintenance.
- Queries are slow at **p95/p99** even though the average still looks good.
- Secondaries lag during write spikes.
- Index builds, restores, and migrations take a long time.
- Adding RAM does not solve a CPU, disk, or shard key bottleneck.
- Disk is nearly full, lacking headroom for index builds, oplog, or migrations.

The problem is not simply choosing a **strong or weak machine**. You need to understand the data, growth rate, workload, concurrency, distribution across tenants, and operational requirements.

**Capacity planning** is forecasting and verifying whether MongoDB can meet the data size, read/write rate, latency, and recoverability requirements over a defined period.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **logical data size**, **physical storage**, **index size**, **working set**, and capacity including replication.
2. Forecast daily/monthly growth, retention, TTL, and changes in document and index sizes.
3. Budget for **CPU, RAM, WiredTiger cache, disk IOPS/throughput, network, connections**, and headroom.
4. Choose between **vertical scaling**, **replica set read scaling**, **sharding**, and query/index optimization.
5. Define KPIs/SLOs, alerts, and upgrade decision thresholds.
6. Design benchmarks with **a sufficiently large dataset, realistic distributions, concurrency, and cache states**.
7. Avoid false conclusions caused by small test data, indexes always fitting in RAM, and load without hot keys.
8. Use **explain()**, **$collStats**, **$indexStats**, **serverStatus**, the profiler, and metrics.
9. Build a capacity forecast across base, high-growth, and stress cases.
10. Design benchmarks and scaling rollouts with success/rollback criteria.

### 1.1. Three Core Questions

~~~text
1. Which resources is the system currently consuming?
        |
        v
2. With projected growth/workload, which resource runs out first?
        |
        v
3. Which scaling measure solves the right bottleneck?
~~~

Do not pick a solution for the third question before having evidence for the first two.

## 2. Capacity Dimensions That Must Be Calculated Separately

A MongoDB cluster does not have a single metric called “size”.

| Dimension | Meaning | Risk When Misjudged |
|---|---|---|
| **Document count** | Scale of logical records. | Missing growth/hot partitions. |
| **Logical BSON bytes** | Logical BSON data size reported by metrics. | Confusing with physical bytes. |
| **Collection storage** | Storage engine data stored/allocated for the collection. | Underestimating compression, fragmentation. |
| **Index storage** | B-tree indexes and other structures. | Insufficient disk and working set sizing. |
| **Working set** | Data/index pages accessed frequently. | Inappropriate RAM sizing. |
| **CPU** | Queries, aggregations, compression, index maintenance. | Adding RAM when CPU is the bottleneck. |
| **Disk IOPS/latency** | Ability to serve random reads/writes. | Cache misses degrade p95. |
| **Disk throughput** | Bytes/s for scans, backups, index builds. | Batches/restores become too slow. |
| **Network** | App↔router, replication, backup/migration. | Network saturation and lag. |
| **Connections** | Concurrent requests/driver pools/queues. | Pool starvation even while the server is healthy. |
| **Replication overhead** | Copies of data on each member. | Insufficient storage budget. |
| **Backup/recovery** | Snapshots/archives and restore duration. | Missing RPO/RTO targets. |
| **Sharding distribution** | Owned bytes and QPS per shard. | Total capacity looks sufficient, but one shard is hot. |

### 2.1. Logical Data Size Differs from Physical Disk

Suppose logical data is 400 GiB. After WiredTiger compression, collection storage may be smaller than 400 GiB; however, indexes, oplog, fragmentation, and other collections make total disk usage larger.

~~~text
Logical BSON data:          400 GiB
Compressed collection:     250 GiB
Indexes:                   110 GiB
Other/allocated overhead:   40 GiB
---------------------------------
Illustrative used storage: 400 GiB
~~~

**These are illustrative numbers only**, not default compression ratios. Repetitive text compresses differently from JPEG images, already-compressed blobs, or random data.

### 2.2. Working Set Is Not Equal to the Entire Database

The working set consists of the data/index pages accessed during a representative time window:

~~~text
Total historical orders:   2 TiB
Frequently read last 30d: 120 GiB
Hot indexes/pages:         45 GiB
Other cache needs:         variable
~~~

You do not necessarily need to load the entire 2 TiB into RAM to serve recent queries. However, historical scans, reports, and batch jobs can cause the working set to spike. Do not use a fixed RAM/data ratio as a substitute for measuring **evictions, cache misses, disk I/O, and latency**.

### 2.3. A Replica Set Multiplies Physical Copies

A three data-bearing member replica set stores three logical copies, plus each member's individual overhead:

~~~text
Primary:       400 GiB live storage
Secondary A:   400 GiB live storage
Secondary B:   400 GiB live storage
---------------------------------
Approx. total: 1.2 TiB, before backups
~~~

Actual numbers may differ due to oplog, compression, fragmentation, and index builds. Do not confuse **three replica members** with **three logical shards**.

### 2.4. Sharding Does Not Reduce Total Data Volume

Three shards partition a logical dataset into parts rather than making data disappear. Each shard is typically a replica set with multiple physical copies. Sharding increases the ability to distribute data/workload, but adds routing, metadata, migration, and operational overhead.

### 2.5. Headroom Is Part of the Plan

~~~text
Required capacity
  = expected live storage
    + index/oplog/storage overhead
    + temporary operational space
    + growth/uncertainty headroom
~~~

You must account for index builds/rebuilds, backup/restore, migrations, bursts, and fragmentation. There is no single headroom percentage guaranteed safe for every deployment; it must be decided based on topology, growth, and SLOs.

## 3. Modeling Data Growth Over Time

### 3.1. Start from Measurable Units

Suppose the application stores orders:

~~~text
orders per day                = 300,000
average BSON document size    = 2.0 KiB
retention period              = 3 years
index storage                 = measured separately
daily update amplification    = measured
~~~

Before production exists, these numbers are **owned assumptions** rather than confirmed data. Record the measurement date, measurement method, source, and margin of error.

### 3.2. Logical Data Growth Rate

With 300,000 documents per day, each averaging 2 KiB:

~~~text
newLogicalBytesPerDay
  = documentsPerDay * avgBsonBytes
  = 300,000 * 2,048
  = 614,400,000 bytes/day
  ≈ 586 MiB/day
~~~

After 365 days, without deletions:

~~~text
586 MiB/day * 365 ≈ 209 GiB
~~~

These are **logical inserted bytes**, not yet accounting for size growth from updates, indexes, physical compression, oplog, or temporary files.

### 3.3. Retention/TTL

If data is retained for only 90 days and the rate is steady:

~~~text
steadyStateDocumentCount
  ≈ 300,000 * 90
  = 27,000,000

steadyStateLogicalSize
  ≈ 27,000,000 * 2,048 bytes
  ≈ 51.5 GiB
~~~

With a TTL index, deletions run in the background and there is **no SLA to delete documents exactly one second after expiration**. When there is a backlog, retained data can be higher than the ideal model; the storage engine also does not necessarily return physical disk blocks to the OS immediately when documents are deleted.

If data is archived before deletion, you must also budget for **archive storage, transfer, and rehydration costs**.

### 3.4. Non-Uniform Document Sizes

A production corpus might look like:

| Order Type | Share | Average BSON Size |
|---|---:|---:|
| Few items | 70% | 1.2 KiB |
| Medium | 25% | 3.5 KiB |
| Many items | 5% | 18 KiB |

Weighted average:

~~~text
0.70*1.2 + 0.25*3.5 + 0.05*18
= 0.84 + 0.875 + 0.9
= 2.615 KiB
~~~

If tests only generate small orders (1.2 KiB), a forecast based on the test can **underestimate by more than 2×** compared to this average.

Besides the average, measure **p50, p95, p99, max BSON size**, and array length distribution. MongoDB has a **16 MiB limit per BSON document**; unbounded growing arrays also cause many other issues long before hitting that limit.

### 3.5. Growth Is Not Necessarily Linear

If orders/day grows 5% per month:

~~~text
docsPerDay(month m)
  = baselineDocsPerDay * (1.05)^m
~~~

A good forecast has at least three scenarios:

| Scenario | Meaning |
|---|---|
| **Base** | Based on observed growth rate and product roadmap. |
| **High growth** | Rapid increase from market expansion/large customers. |
| **Stress** | Flash sales, data imports, batch backfills, failure replays. |

Do not assume traffic always grows steadily or exponentially forever; account for seasonality, retention, and business rule changes.

### 3.6. Updates and Deletes Also Consume Resources

~~~javascript
{
  _id: "O-100",
  customerId: "C-1",
  statusHistory: [
    { state: "CREATED", at: ISODate("2026-01-01T00:00:00Z") },
    { state: "PAID", at: ISODate("2026-01-01T00:05:00Z") }
  ]
}
~~~

If **statusHistory** grows on every update, the document grows larger over time. You need to calculate:

- How many updates per document over its lifecycle?
- What is the net BSON size change?
- Are indexed fields modified, creating additional index maintenance?
- What is the impact on write amplification, oplog, change streams, and backups?
- Should history be bounded or separated into an events collection?

Do not simply multiply inserts × average size and treat updates as free.

### 3.7. Index Growth

Suppose data compresses well, but there are five large compound indexes. You cannot forecast index bytes using a single universal factor for all workloads:

~~~text
indexBytes = f(numberOfEntries, key sizes, multikey fan-out,
               compression, index structure, updates, versions)
~~~

For example, an array field indexed with a **multikey** index can generate multiple index keys per document; key cardinality and arrays make indexes grow at a different rate from data.

Establish a baseline `indexSize` on a representative corpus, then forecast based on record counts, document shapes, and array distributions. Adding indexes can significantly increase disk/cache/write costs.

### 3.8. Oplog Retention and Workload

The replication oplog is the log of changes stored in replica sets. Its capacity and history retention window affect:

- How long a secondary can lag and still catch up after downtime.
- How far back change stream consumers can resume.
- Backup/oplog-based recovery workflows.

Do not size the oplog from live document counts: **updates and deletes also create entries**. A write-heavy cluster with little live data may still require a substantial oplog depending on retention targets and throughput.

### 3.9. A Monthly Forecast Template

| Month | New Docs | Expired Retention Docs | Retained Docs | Logical Bytes | Index Bytes | Physical Storage | Headroom |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | Baseline | 0 | Baseline | Measured | Measured | Measured | Per policy |
| M1 | Forecast | Forecast | Calculated | Calculated | Estimated | Estimated | Calculated |
| M2 | Forecast | Forecast | Calculated | Calculated | Estimated | Estimated | Calculated |
| M3 | Forecast | Forecast | Calculated | Calculated | Estimated | Estimated | Calculated |

Distinguish **measured** values from **estimated** ones; update the model with actual metrics after each period.

## 4. Capacity Is Not Just Gigabytes

### 4.1. Throughput and Latency Are Two Different SLOs

A system can handle 10,000 ops/s while having unacceptable p99 latency. Conversely, a system responding in 5 ms with a single client may not sustain 1,000 concurrent clients.

Example SLO:

~~~text
GET /orders/{id}:
  p95 < 80 ms under target load
  p99 < 250 ms under stress condition

POST /orders:
  p95 < 150 ms
  error rate < 0.1%
~~~

These are **illustrative SLOs**, not default MongoDB guarantees. SLOs should be measured at the application boundary (including network, driver pool, and downstream logic), alongside DB-specific metrics for diagnostics.

### 4.2. Concurrent Operations and Little's Law

An approximate relationship in a stable system:

~~~text
L ≈ λ * W

L = average number of requests/operations in the system
λ = average completed throughput per second
W = average time spent in the system (seconds)
~~~

If throughput is 2,000 requests/s and each request takes 50 ms:

~~~text
L ≈ 2,000 * 0.050 = 100 concurrent requests
~~~

This calculation applies to the defined workload/system boundary; **it does not mean MongoDB needs exactly 100 connections**: one request may issue multiple operations, connection pools have queues, and operations may not occupy a socket for the entire duration of the request.

### 4.3. CPU Capacity

CPU is consumed by:

- Query execution and filtering/aggregation.
- Sorting, grouping, and projections.
- WiredTiger compression/decompression.
- Index maintenance and BSON processing.
- Encryption/TLS and mongos routing.
- Background tasks, replication, and index builds.

If CPU hits its limit during a load test, analyze **CPU usage vs useful operations/s**, query plans, and service time. Adding CPU helps little if the real bottleneck is disk latency or lock/contention.

### 4.4. WiredTiger Cache and Memory

MongoDB WiredTiger uses a cache to hold internal data/index pages. The default cache size depends on server version, configuration, and environment; outside the WiredTiger cache, memory is still needed for the OS, connections, aggregations, and other components.

Monitor:

- Cache bytes in use, dirty bytes, and eviction pressure.
- Page reads from disk and disk latency.
- Page faults and operating system memory pressure.
- Aggregation sort/group spilling depending on version.
- Number of concurrent operations and memory peaks.

**More RAM does not automatically fix a bad query plan**: a COLLSCAN scanning too many documents still consumes CPU and I/O even when well cached.

### 4.5. Disk IOPS and Storage Latency

A workload with many point reads missing the cache can require high random IOPS. A batch scan reading many bytes sequentially is more sensitive to throughput.

~~~text
Point lookups with cache misses -> random reads / IOPS
Large scans / index builds      -> throughput and CPU
Heavy writes / updates         -> write IOPS, durability, replication
~~~

Do not pick a disk solely by “1 TiB capacity”; check the platform's **sustained IOPS, throughput, p95/p99 disk latency, burst credits, and throttling**.

### 4.6. Network and Replication

The application and cluster must transfer:

- Read results/write payloads.
- Replication oplog streams.
- Balancer range migration copies.
- Backups/restores/CDC.

Network bottlenecks or packet loss can cause replication lag and elevated p95 latency. A replica set with three members does not mean each write transfers data only once.

### 4.7. Driver Connection Pools

Connection pool configuration affects queueing and concurrent execution capacity:

~~~text
Incoming application requests
          |
          v
Driver connection pool
          |
     +----+-----+
     |          |
  Available   Waiting
 connections requests
     |          |
     v          v
MongoDB       Pool wait latency
~~~

Too few connections cause pool waits; too many connections and threads can make `mongod` contend for resources and increase context switching. Tune the pool based on **active operations, checkout latency, server metrics, and load tests**, rather than setting a huge `maxPoolSize` without measuring.

### 4.8. Batch Jobs and Peak Workloads

A system running smoothly at 500 writes/s during the day may ingest 20 million documents on month-end night. Capacity planning must simulate:

- Peak ingest throughput.
- Concurrent application traffic.
- Backfills/migrations.
- Index builds/maintenance.
- Replication lag.
- Backup windows.

Do not use the 24-hour average QPS as the sole provisioning target.

## 5. Choosing the Right Resource Scaling Option

Before scaling, identify the **bottleneck** using evidence:

~~~text
Query plan inefficient?
  -> index/schema/query optimization

Cache misses + high disk reads?
  -> working-set and memory/storage analysis

CPU saturated on one mongod?
  -> efficient queries, vertical scaling, possible sharding

Read-heavy traffic?
  -> query tuning, cache, read distribution / replicas

Write throughput concentrated on one shard?
  -> shard-key/write distribution and possible resharding

Disk near capacity?
  -> retention/archive/index cleanup, scale disk or shards
~~~

Do not assume **adding shards** is the default answer for every slow query.

### 5.1. Vertical Scaling: Increasing Resources per Node

**Scale up** means increasing vCPU, RAM, disk, IOPS/throughput, or node class.

Advantages:

- Minimal changes to application architecture and shard keys.
- Sensible when the bottleneck is on a single node and solvable with hardware.
- Can help the working set fit closer to cache or give CPU additional headroom.

Limitations:

- There is a maximum machine size, and cost may scale non-linearly.
- Failover/maintenance still requires checking replica set and member compatibility.
- Increasing vCPU alone does not help if disk I/O is saturated.
- A bad query plan does not fix itself on a bigger machine.

If WiredTiger cache pressure is high and random disk reads are frequent, adding RAM may help. However, compare **cache misses, latency, and IOPS before/after** to prove it.

### 5.2. Read Scaling with a Replica Set

A replica set has secondaries for availability and, in certain workloads, can distribute read operations using **read preference**.

Notes:

- Writes are primarily processed on the primary and replicated to secondaries.
- Reads on secondaries can be stale due to replication lag.
- Adding secondaries does not automatically distribute every query evenly.
- Data/indexes are stored on every data-bearing member.
- Read workloads on a secondary can contend for I/O with replication.

Example Java configuration for read preference in a workload that accepts eventual consistency:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .readPreference(ReadPreference.secondaryPreferred())
    .build();
~~~

This is a configuration illustration; in production you need complete imports/client initialization and a defined consistency contract. Do not route all financial transactional queries to secondary reads merely to reduce primary CPU.

### 5.3. Sharding to Distribute Data and Workload

**Sharding** partitions sharded collections across multiple shards and helps scale capacity when:

- The dataset/working set exceeds the economic or technical limits of a single replica set.
- Write throughput needs to be distributed.
- Query patterns can target shards by shard key.
- The operations team can monitor `mongos`, CSRS, the balancer, and migrations.

Unsuitable when:

- Primary queries lack the shard key and frequently scatter-gather.
- One hot key accounts for most writes.
- The dataset is too small to justify the added complexity.
- The root problem is a missing index or an inefficient aggregation.

### 5.4. Choosing a Shard Key Based on Workload

~~~javascript
{ createdAt: 1 }
~~~

With monotonically increasing timestamp inserts, the range at the edge of the keyspace can become a write hot spot.

~~~javascript
{ deviceId: "hashed" }
~~~

This can spread out multiple devices, yet a single device generating 70% of events still creates hot-spot risk. Evaluate **cardinality, frequency, monotonicity, query targeting, zone constraints, and future growth** before sharding.

### 5.5. A New Shard Does Not Receive Data Instantly

The balancer takes time to move eligible ranges according to policies and resource limits. Do not plan under the assumption:

~~~text
Add shard at 10:00
All data balanced by 10:01
~~~

During migrations, extra network bandwidth, recipient disk headroom, and replication capacity are needed. Zones or oversized ranges can restrict migration.

### 5.6. Retention/Archive Instead of Only Scaling

If 95% of queries read the last 90 days while the collection retains 10 years of logs:

~~~text
Hot collection: last 90 days
Cold archive: older data according to retention
~~~

This can reduce the working set and index size. However, you must design archive queries, compliance, TTL cleanup, restores, and data that needs rehydration.

### 5.7. Application Caching

Catalog data read repeatedly can be cached at the application/Redis/CDN layer if semantics allow. Caching reduces read load but adds complexity around expiration, invalidation, stale reads, and authorization.

Do not use a cache to mask a bad query plan without measuring its impact; cache keys must respect user/tenant permissions when data has access control.

### 5.8. Decision Table

| Symptom | What to Check | Options to Consider |
|---|---|---|
| Large COLLSCAN | `explain`, predicates | Query/index optimization. |
| RAM pressure, high disk reads | WiredTiger cache, working set | RAM/storage or reducing hot data. |
| High CPU from aggregations | Profiler, pipeline | Optimize pipeline, add vCPU if needed. |
| High disk latency | Cache misses, IOPS | Storage tier, query changes. |
| High primary read load | Consistency, pool, traffic | Secondary reads/cache/query tuning. |
| Hot writes on one key | Shard key frequency | Redesign partitioning/reshard. |
| Dataset exceeds node capacity | Retention, growth, disk | Scale node/disk or shards. |
| One shard's disk is full | Balancer, zones, indexes, orphans | Fix placement/capacity based on evidence. |
| Backups take too long | Throughput, snapshots, RPO/RTO | Backup architecture and bandwidth. |

## 6. Why Does Overly Small Test Data Lead to Wrong Conclusions?

One of the classic MongoDB tuning traps is a **test corpus that does not resemble production** in scale, document shape, value distribution, and concurrency.

### 6.1. Data and Indexes Always Fit in RAM

Locally:

~~~text
Data:     10 MiB
Indexes:   4 MiB
RAM:       8 GiB
~~~

Point reads are served almost entirely from cache.

In production:

~~~text
Data:      2 TiB
Indexes: 400 GiB
RAM:      64 GiB
~~~

Cache misses and random I/O become critical. Results from 10 MiB cannot reliably predict latency at 2 TiB.

### 6.2. The Query Planner Chooses a Different Plan

With 20 documents, a **COLLSCAN** may be very fast or reasonable. With 50 million documents, the same query may require an index.

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

A candidate compound index:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
~~~

This index is not a recommendation to apply blindly: you must inspect all query patterns, cardinality, index size, and write cost. Always compare **explain.executionStats** on a representative corpus.

### 6.3. Selectivity Changes

In tests:

~~~text
status="PAID": 10% of documents
~~~

In production:

~~~text
status="PAID": 95% of documents
~~~

A single-field index on `status` may be far less useful than expected. You must preserve realistic **value frequency distributions, correlations between fields, and record counts per tenant**.

### 6.4. No Hot Keys or Tenant Skew

Test:

~~~text
100 tenants, 1,000 documents each
~~~

Production:

~~~text
Tenant A: 65% data, 80% QPS
Tenant B: 10% data
Other tenants: remaining 25%
~~~

Uniform random tests fail to reproduce hot shards, cache pressure, and hot document contention.

### 6.5. Overly Simple Document Shapes

Test:

~~~javascript
{ _id: 1, userId: 42, value: 100 }
~~~

Production:

~~~javascript
{
  _id: ObjectId("65a000000000000000000001"),
  tenantId: "t-001",
  userId: "u-0042",
  status: "PAID",
  amountCents: NumberLong(99900),
  items: [
    { sku: "SKU-100", quantity: 2, priceCents: 34900 },
    { sku: "SKU-200", quantity: 1, priceCents: 30100 }
  ],
  shipping: { city: "Hanoi", country: "VN" },
  statusHistory: [
    { state: "CREATED", at: ISODate("2026-01-01T00:00:00Z") },
    { state: "PAID", at: ISODate("2026-01-01T00:02:00Z") }
  ],
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
~~~

Arrays, subdocuments, field lengths, and multikey index fan-out affect storage, cache, and update throughput.

### 6.6. No Concurrency

Single-client test:

~~~text
find -> wait -> find -> wait
~~~

Production:

~~~text
200 concurrent clients
80% point reads
10% filtered list queries
8% writes/updates
2% large aggregations
~~~

Concurrency exposes pool waits, CPU contention, cache evictions, disk queueing, and replication lag.

### 6.7. No Long-Tail Documents

The average order has two items, yet 1% of orders have 200 items; 5% of customers generate a huge share of events. The tail distribution can dominate p99 latency, index fan-out, and aggregation memory peaks.

### 6.8. A Single Run Is Not Enough

A fast query run may result from a warm cache, no background writes, no backups/index builds, warmed JIT, local networking, or storage using burst credits.

Measure **repeat runs, warm-up, steady state, cache regimes, p95/p99**, and resource usage at the same time.

### 6.9. Small Data Hides the Cost of $lookup

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $limit: 20 }
]);
~~~

A pipeline run on 100 orders cannot prove its cost on tens of millions of records. You must evaluate cardinality, foreign indexes, early filtering, join candidates, result sizes, pipeline ordering, and shard topology.

### 6.10. Confusing “Index Present” with “Index Useful”

With 1,000 documents, every index is tiny. In production:

- A compound index with the wrong field order may fail to support a sort.
- An index with many fields can consume substantial disk/cache and slow down writes.
- Queries using unanchored regexes or mismatched data types may make poor use of an index.
- A partial index is only used for queries satisfying its filter predicate.
- Multikey indexes have specific limitations and overhead.

Do not build 15 indexes just because each query in a small dataset gets a matching one. Evaluate the overall workload and **write amplification**.

### 6.11. Testing Queries with the Wrong Data Type

Production:

~~~javascript
{ customerId: ObjectId("65a000000000000000000001") }
~~~

Test:

~~~javascript
{ customerId: "65a000000000000000000001" }
~~~

A String is not equal to an ObjectId. A benchmark returning 0 results very quickly may simply prove you are **querying the wrong type**. Always verify result counts and BSON types; do not treat 0 ms with zero matches as success.

### 6.12. No Cache Churn

A benchmark repeatedly reading the same 100 documents measures cache-friendly behavior. Production has users reading across many tenants, reports, and time ranges, pushing hot pages out of the cache.

Design **access distributions**: hot subset, cold subset, random reads, and scans in proportions close to production.

### 6.13. What Small Tests Fail to Prove

| Observation from a Small Test | Not Enough to Prove |
|---|---|
| 5 ms with 10,000 docs | 5 ms with 50 million docs. |
| 0 disk reads | Production working set fits in RAM. |
| COLLSCAN is fast | No index is needed. |
| One client hits 1,000 ops/s | 200 clients achieve the same per-client rate. |
| Importing 100 docs is fast | Importing 100 million docs will not impact replication. |
| Index build takes 0.2 seconds | Building in production needs no headroom. |
| No hot shard | Shard key withstands tenant skew. |
| Simple documents perform well | Arrays/large docs behave identically. |
| Low mean latency | p99 meets the SLO. |
| Test disk still has free space | Enough capacity for retention/backup/growth. |
| Zero-result query is very fast | Query matches real production data properly. |

## 7. Designing a Representative Benchmark Dataset

A good benchmark does not have to be a full copy of production, but it must reflect the characteristics that alter execution cost.

### 7.1. Five Dimensions to Represent

| Dimension | What to Simulate |
|---|---|
| **Scale** | Document count, total bytes, index size relative to RAM. |
| **Shape** | Fields, types, nested documents, arrays, sizes, p95/p99 lengths. |
| **Distribution** | Tenant sizes, status frequencies, hot keys, date recency, missing/null values. |
| **Access** | Point vs range reads, writes, updates, aggregations, hot/cold mix. |
| **Concurrency** | Clients/threads, arrival rate, batch jobs, long-running operations. |

Do not use 10 million **identical** documents and treat it as a large enough benchmark: repetitive data can compress unrealistically well and produce unrealistic selectivity.

### 7.2. Safely Extracting Distributions from Production

If production metrics exist, collect **anonymized/aggregated** statistics:

- Document size buckets (0–1 KiB, 1–4 KiB, 4–16 KiB, ...).
- Record counts by tenant percentile, avoiding exporting sensitive tenant IDs.
- Status frequencies and correlations with `createdAt`/tenant.
- Element counts in arrays.
- Ratio of new/old records, retention, and update frequency.
- Mix of query types and concurrency.
- Selected hot keys via valid hashing/anonymization.

Do not copy customer data, tokens, or secrets directly to a laptop or less secure test environment. Synthetic data should have **similar shapes and distributions**, without containing real PII.

### 7.3. Sizing the Dataset by Working Set Ratio

A medium-scale test can still be useful if the ratio of **hot data/index pages to cache** approximates production.

Example:

~~~text
Production:
  hot working set 200 GiB / effective cache 50 GiB = 4.0

Representative smaller environment:
  hot working set 20 GiB / effective cache 5 GiB = 4.0
~~~

An identical ratio does not guarantee identical performance: CPU/IOPS/network, concurrency, storage, and cache algorithms still differ. However, it is **far better** than a 10 MiB test sitting completely in RAM when production experiences cache misses.

### 7.4. Scaling Document Counts and Distinct Values

A benchmark must have sufficient cardinality to reproduce query selectivity:

~~~text
documents: 10,000,000
unique customers: 1,000,000
unique tenants: 1,000
status values: 6, skewed frequencies
time range: 2 years
items per order: p50=2, p95=12, p99=40
~~~

These numbers are examples. A benchmark with 10 million documents but only 10 distinct customers does not reflect a million-customer system.

### 7.5. Generating Hot Tenants

Production may have one tenant generating 30% of requests, 10 tenants generating another 40%, and the rest sharing 30%.

If a synthetic dataset spreads across 1,000 tenants evenly, cache contention, hotspots, and shard key distribution will differ.

Generate a **Zipf-like distribution** or a custom weighted distribution based on telemetry, instead of relying on default uniform randomness.

### 7.6. Time and Retention

Queries typically favor the most recent data:

~~~text
70% reads -> last 7 days
20% reads -> last 90 days
10% reads -> older history
~~~

The dataset must span timestamps across those ranges and test corresponding read filters.

If every synthetic document has the same `createdAt`, date indexes, shard key monotonicity, and range queries will not reflect reality.

### 7.7. Data Must Include Nulls, Missing Fields, and Edge Cases

Include realistic proportions of:

- Missing fields.
- Null fields.
- Empty arrays.
- Long text.
- Unicode and Vietnamese text.
- Documents with deep nested objects.
- Duplicate values.
- Large values in the tail.

For example, a partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { partialFilterExpression: { status: "PENDING" } }
);
~~~

Cost and query behavior depend on the ratio of **PENDING** documents, not just total records. Testing with 0% PENDING makes the benchmark meaningless for this endpoint.

### 7.8. Indexes Must Match the Target Environment

A test with data but without the production index set measures the wrong thing. Conversely, creating extra indexes not present in production changes write costs.

Prepare:

1. The same indexes, key order, and partial/sparse/TTL/collation options where applicable.
2. The same critical schema validation rules.
3. The same sharding setup/zone constraints when evaluating a sharded cluster.
4. The same read/write concerns matching business semantics.
5. The same MongoDB/driver versions, or explicitly document differences.

### 7.9. Data Compression Must Be Natural

If every record uses:

~~~javascript
{ payload: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" }
~~~

compression may be artificially high. If purely random bytes are used, compression is nearly zero. Neither may resemble real data.

Use string/array/field variation matching production; **measure actual compressed storage and index sizes**, rather than extrapolating from synthetic character counts.

### 7.10. Separate Benchmark Data from Correctness Fixtures

A small dataset can serve **unit tests, contract tests, and correctness checks**. A large representative dataset serves **performance/capacity evaluation**.

Do not force every CI run to seed 100 million documents. You can structure tiers:

~~~text
Unit / contract:
  Small deterministic fixtures, milliseconds.

Functional integration:
  Moderate dataset, real MongoDB, correctness.

Performance integration:
  Millions of representative documents, indexes.

Capacity / stress:
  Production-like data-to-cache ratio,
  traffic distribution and concurrency.
~~~

Do not replace small tests with large benchmarks: **the two types of tests answer different questions**.

## 8. Designing Comparable Benchmark Workloads

### 8.1. Workload Matrix

A test suite for orders:

| Operation Type | Share | Pattern | What to Measure |
|---|---:|---|---|
| Get order by `_id` | 40% | Point read | p50/p95/p99, cache hits. |
| List recent orders by customer | 25% | Filter + sort + limit | Index scan, pages read, latency. |
| Create order | 15% | Insert + indexes | Write throughput, replication lag. |
| Update status | 10% | Update indexed/unindexed fields | Write amp, locks/queues. |
| Search/report by date/status | 8% | Range/group/sort | CPU, memory, spill, I/O. |
| Batch reconciliation | 2% | Background aggregation | Tail latency impact. |

Proportions should come from real telemetry and can separate a **peak scenario** from steady state.

### 8.2. Arrival Rate vs Fixed Concurrency

Two benchmark models:

- **Closed-loop:** each client sends the next request only after the previous one completes.
- **Open-loop:** the generator sends requests at a scheduled arrival rate, even when the service slows down.

Closed-loop models can throttle throughput as latency rises and partially hide overload (coordinated omission). Open-loop simulates arrival load better for certain goals, though backlog and wait times must be controlled.

**Explicitly state the load model**, rather than just writing “100 users”.

### 8.3. Ramp-Up, Steady-State, and Spike

~~~text
0–5 min:    warm-up
5–15 min:   200 ops/sec
15–25 min:  500 ops/sec
25–35 min:  1,000 ops/sec
35–45 min:  1,500 ops/sec
45–50 min:  spike to 3,000 ops/sec
50–60 min:  recovery/steady-state
~~~

Numbers and durations are an illustrative scenario. The goal is to find:

- Sustainable load that meets SLOs.
- The point where p95/p99 begins climbing sharply.
- Queue/pool wait and disk/CPU saturation.
- Recovery behavior after a spike.

Do not report only the highest throughput achieved while the system is returning many errors.

### 8.4. Warm Cache vs Cold Cache

Two scenarios:

| Scenario | Purpose |
|---|---|
| **Warm cache** | Measure performance after warm-up with the hot working set. |
| **Cold/mixed cache** | Observe sensitivity when insufficient pages are cached or the workload shifts. |

Do not restart production MongoDB or drop system caches to test a “cold cache”. In a lab environment you can generate a controlled cold workload, vary query ranges, or start a dedicated instance; document the exact method so results are repeatable.

### 8.5. Query Correctness Is a Prerequisite

For every operation:

~~~text
expected result count / invariants
actual result count
error category
query/transaction semantic correctness
latency
resource consumption
~~~

A query that runs very fast while returning the wrong tenant or zero results due to a type mismatch **is not a successful benchmark result**.

### 8.6. Measuring Latency Distribution

Collect:

- p50.
- p90/p95.
- p99 (requires sufficient sample count).
- Max or slow outliers.
- Timeouts/errors.
- Queue time vs service time if separable.

A dashboard showing only **average latency** easily hides the tail; 1% of queries taking multiple seconds can heavily impact users.

### 8.7. Do Not Confuse a Load Generator Bottleneck with a Database Bottleneck

If the load generator CPU hits 100% or its network link saturates, measured QPS does not reflect MongoDB's maximum throughput.

Monitor:

~~~text
Load generator CPU and memory
Client connection pool waits
Network on generator and database
MongoDB server CPU/cache/disk
Application latency and error rate
~~~

Use multiple generators or isolate the load injector from the database if needed, and document the topology so bottlenecks are clear.

### 8.8. Comparing Under Identical Conditions

When comparing Index A vs Index B:

- Same corpus/document count.
- Same workload mix and query parameter distribution.
- Same hardware/versions.
- Same warm-up policy.
- Same concurrency/arrival rate.
- No unintended background migrations.
- Multiple runs to control for variance.

Do not conclude “Index B is 50% faster” if run B executed after the OS cache was warm while A was a cold run.

### 8.9. Stress, Soak, and Failure Tests

- **Stress:** increase load until SLOs are breached or limits appear, in an authorized environment.
- **Soak:** run for extended periods to detect memory growth, queue buildup, fragmentation, or oplog/TTL backlogs.
- **Failure/recovery:** simulate node restarts/elections/network degradation in a lab to assess availability and recovery.

Do not trigger failovers or disk exhaustion in production just to gather benchmark numbers.

### 8.10. Benchmark Results Must Have Context

A minimal report:

~~~text
Dataset: 25,000,000 docs; 85 GiB logical; indexes 32 GiB
Node: 8 vCPU, 32 GiB RAM, SSD IOPS tier specified
Topology: replica set 3 members
MongoDB + driver version: recorded
Workload: 50% reads, 30% writes, 20% aggregate
Traffic model: open-loop 1,200 requests/sec
Duration: 30 min steady state after warm-up
P95 application latency: measured
P99 application latency: measured
Error/timeouts: measured
CPU/disk/cache/replication: measured
Conclusion: passes/fails defined SLO and headroom requirement
~~~

Do not put a single throughput number on a slide without data shape, resource baseline, errors, and SLOs.

## 9. Measuring Real MongoDB with mongosh and Monitoring

These examples are intended for environments where observation is authorized. Some commands require **clusterMonitor** or equivalent privileges. Output and metric field names vary by MongoDB version, storage engine, and topology.

### 9.1. Measuring Document Counts and Collection Size

In `mongosh`:

~~~javascript
use commerce

db.orders.estimatedDocumentCount();
~~~

**estimatedDocumentCount()** is appropriate when an approximate count from metadata is needed; it is not always identical to **countDocuments({})** in all situations, especially during active sharded cluster migrations.

You can check collection stats:

~~~javascript
db.orders.stats({ scale: 1024 * 1024 });
~~~

Some tool versions format output differently; in particular, understand fields like **size, storageSize, totalIndexSize, indexSizes, count** and the scaling unit.

### 9.2. $collStats

~~~javascript
db.orders.aggregate([
  {
    $collStats: {
      storageStats: { scale: 1048576 },
      count: {}
    }
  }
]);
~~~

Results may include per-shard stats depending on deployment and version. **storageStats.storageSize is not always synonymous with owned logical bytes**; it can differ from `dataSize` due to compression, allocation, and orphan document effects.

Do not sum metrics with different definitions for disk capacity planning.

### 9.3. Inspecting Indexes

~~~javascript
db.orders.getIndexes();
~~~

Cross-check:

- How many indexes exist?
- Which main queries use them?
- Do compound indexes have an appropriate key order?
- Are there unique, partial, TTL, or multikey indexes?
- Are collation and filter expressions appropriate?

**Do not drop an index in production just because a small benchmark did not use it.** You must examine the entire workload over time, including reports, background jobs, and constraints.

### 9.4. $indexStats for Observing Usage

~~~javascript
db.orders.aggregate([
  { $indexStats: {} },
  {
    $project: {
      name: 1,
      key: 1,
      accesses: 1
    }
  }
]);
~~~

The **accesses.ops** field represents the number of index access operations according to server/source semantics since stats began, not “unique queries” or bytes accessed. Counters can reset upon node restart/reindex, and you must observe long enough to capture infrequent jobs.

### 9.5. explain on Critical Queries

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Inspect components such as:

- Winning plan.
- **IXSCAN** vs **COLLSCAN**.
- **totalKeysExamined**.
- **totalDocsExamined**.
- **nReturned**.
- Execution time and stages.
- Whether the sort uses the index or needs an extra stage.
- Targeted shards if the collection is sharded.

Do not look only at `executionTimeMillis` while ignoring **nReturned**. A query returning 0 records can be fast without actually exercising the real data path.

### 9.6. Comparing Query Efficiency Metrics

~~~text
Plan A:
  nReturned = 20
  totalDocsExamined = 1,000,000
  totalKeysExamined = 0

Plan B:
  nReturned = 20
  totalDocsExamined = 20
  totalKeysExamined = 20
~~~

Plan B generally indicates better index targeting in this example. However, you still need to consider write/index costs and workload mix to choose the overall design.

One useful ratio:

~~~text
documentsExaminedPerResult =
  totalDocsExamined / max(nReturned, 1)
~~~

This helps detect scan amplification, though when a query runs count/group or returns 0 results, interpretation differs. Do not set one hard threshold for all query types.

### 9.7. serverStatus

On an authorized `mongod` member:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  opcounters: s.opcounters,
  connections: s.connections,
  network: s.network,
  opLatencies: s.opLatencies,
  wiredTigerCache: s.wiredTiger ? s.wiredTiger.cache : undefined
});
~~~

**serverStatus** contains many counters and gauges. Do not treat raw cumulative counters as QPS:

~~~text
ops(t0) = 1,000,000
ops(t1) = 1,060,000
Δtime = 60 s

rate = (1,060,000 - 1,000,000)/60
     = 1,000 ops/s
~~~

Watch for counter resets on `mongod` restarts; `mongos` and `mongod` members return different metrics.

### 9.8. DB Stats

~~~javascript
db.stats(1024 * 1024);
~~~

This command returns database statistics depending on version/engine and does not replace per-collection, per-shard, or per-replica-member metrics.

### 9.9. Query Profiler and Slow Operations

The database profiler can help find slow queries, but **enabling the profiler or raising the profiling level introduces overhead**. Only adjust it in production with proper authorization and an approved change procedure.

If profiling is already enabled per policy:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    ns: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

Profiler statistics depend on version/configuration, may contain sensitive query contents, and may not capture every workload. Use appropriate sampling and data retention so PII is not exposed.

### 9.10. Current Operations

Some tools can use **$currentOp** or the `currentOp` command depending on version to investigate running operations, lock waits, and long-running jobs. Output is point-in-time and can be very large; avoid running unrestricted full dumps on large clusters.

Prefer:

- Slow query dashboards.
- Aggregated query latency metrics.
- Profiler/log sampling.
- Controlled query `explain`.
- Driver command monitoring with sensitive-data protection.

### 9.11. mongostat, mongotop, and Atlas Metrics

**mongostat** helps observe counters/rates over time; **mongotop** helps inspect per-collection activity on `mongod` under appropriate conditions.

MongoDB Atlas/Ops Manager or your monitoring stack can provide charts for:

- CPU, memory, and disk capacity/IOPS/latency.
- Opcounters and network traffic.
- WiredTiger cache/evictions.
- Connections and queues.
- Replication lag and oplog.
- Storage/index growth.
- Query latency and alerts.

Do not mistake metrics available in a managed product for default fields in vanilla `serverStatus`; names and resolution depend on the deployment.

### 9.12. When Using Sharding

Capacity planning across shards requires measuring:

~~~text
ownedDataBytes by shard
diskFreeBytes by member
read/write QPS by shard
balancer migrations and failures
zone constraints
hot shard-key values
application p95/p99
~~~

A sharded cluster with plenty of total disk still risks breaching SLOs if a single shard runs out of resources.

## 10. Preparing a Lab Dataset Larger Than a Toy Dataset

An example **mongosh seed generator** strictly for a **lab database**. It generates orders with distributions across tenants, statuses, `createdAt`, and items rather than 100 identical records.

**Do not run this script in production.** Create a separate test database/cluster, cap the document count, and check disk/CPU before scaling up.

### 10.1. Dataset Generator in mongosh

~~~javascript
// Run only on an isolated benchmark MongoDB deployment.
const benchDb = db.getSiblingDB("perf_capacity_lab");
const orders = benchDb.getCollection("orders_benchmark");

// Change this deliberately for larger experiments.
const TOTAL_DOCUMENTS = 20000;
const BATCH_SIZE = 500;
const BASE_TIME = Date.UTC(2026, 0, 1);
const SPAN_DAYS = 365;
const ONE_DAY_MS = 86400000;

// The script refuses to append data to an existing test collection.
if (orders.estimatedDocumentCount() !== 0) {
  throw new Error(
    "orders_benchmark is not empty; use a fresh lab collection"
  );
}

let state = 20261114;
function nextRandom() {
  // Deterministic, non-cryptographic pseudorandom numbers.
  state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
  return state / 4294967296;
}

function pickTenant() {
  const x = nextRandom();
  if (x < 0.30) return "tenant-hot";
  if (x < 0.50) return "tenant-large-2";
  return "tenant-" + Math.floor(nextRandom() * 400);
}

function pickStatus() {
  const x = nextRandom();
  if (x < 0.55) return "PAID";
  if (x < 0.80) return "SHIPPED";
  if (x < 0.92) return "PENDING";
  if (x < 0.98) return "CANCELLED";
  return "REFUNDED";
}

function pickItemCount() {
  const x = nextRandom();
  if (x < 0.70) return 1 + Math.floor(nextRandom() * 3);
  if (x < 0.95) return 4 + Math.floor(nextRandom() * 9);
  return 13 + Math.floor(nextRandom() * 28);
}

function buildOrder(i) {
  const itemCount = pickItemCount();
  const items = [];
  let totalCents = 0;

  for (let j = 0; j < itemCount; j++) {
    const skuNumber = Math.floor(nextRandom() * 100000);
    const price = 1000 + Math.floor(nextRandom() * 50000);
    const quantity = 1 + Math.floor(nextRandom() * 3);

    items.push({
      sku: "SKU-" + skuNumber,
      quantity: quantity,
      priceCents: price,
      label: "product-" + skuNumber + "-variant-" + (j % 7)
    });
    totalCents += price * quantity;
  }

  const dayOffset = Math.floor(nextRandom() * SPAN_DAYS);
  const at = new Date(BASE_TIME + dayOffset * ONE_DAY_MS);
  const tenant = pickTenant();

  return {
    _id: "BENCH-" + String(i).padStart(10, "0"),
    tenantId: tenant,
    customerId: "C-" + Math.floor(nextRandom() * 300000),
    status: pickStatus(),
    createdAt: at,
    amountCents: totalCents,
    items: items,
    shipping: {
      country: "VN",
      city: ["Hanoi", "Danang", "HCMC"][
        Math.floor(nextRandom() * 3)
      ]
    }
  };
}

for (let offset = 0; offset < TOTAL_DOCUMENTS; offset += BATCH_SIZE) {
  const batch = [];
  const end = Math.min(offset + BATCH_SIZE, TOTAL_DOCUMENTS);

  for (let i = offset; i < end; i++) {
    batch.push(buildOrder(i));
  }

  orders.insertMany(batch, { ordered: true });
}

print("Inserted " + TOTAL_DOCUMENTS + " synthetic documents");
~~~

These numbers are chosen to **illustrate distributions**, not copied from a real system. The script defaults to only 20,000 records so it is easy to start with; scale to millions only when environment capacity and quotas allow.

### 10.2. Why Is This Generator Better Than Inserting the Same Document Repeatedly?

It provides:

- Hot/large tenants alongside smaller tenants.
- Non-uniform status values.
- Varying item counts, including a long tail.
- `createdAt` spread across a time range.
- Many customer IDs and SKU values.
- Nested fields and arrays.
- Deterministic randomness for repeatability with the same seed.

Even so, it is **not yet production-like** if real document shapes, value correlations, update patterns, sizes, and workloads differ substantially. Treat it as a starting point to tune against telemetry.

### 10.3. Creating Indexes for the Example

~~~javascript
orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});

orders.createIndex({
  customerId: 1,
  createdAt: -1
});
~~~

Measure **index size, build time, and insert throughput** after building indexes, and compare against creating indexes before ingestion. Do not conclude one approach is always best for every production write path.

### 10.4. Inspecting the Lab Dataset

~~~javascript
print("Count: " + orders.countDocuments({}));

orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);

orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } },
  { $limit: 10 }
]);
~~~

After verifying the distribution, run workloads with matching selectivity. **This is a test-design step**, not automatic proof that synthetic data already matches production.

## 11. Comparing Query Plans on a Larger Corpus

### 11.1. Query with a Candidate Index

With the index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

run:

~~~javascript
orders.find({
  tenantId: "tenant-hot",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

Evaluate:

- Does an IXSCAN match the index key order?
- How many keys/docs are examined?
- Is an additional SORT stage needed?
- Do returned documents match the tenant/status?
- How does latency compare for the hot tenant vs a rare tenant?

**Do not** take one cached execution plan from a small test and assume the production planner or working set behaves the same way.

### 11.2. Query Missing the Index Prefix

~~~javascript
orders.find({
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

An index starting with `tenantId` is not necessarily efficient for queries containing only `status`/`createdAt`; inspect the MongoDB planner and query shape.

Instead of adding a new index immediately, ask:

- Should this API always require `tenantId`, and did a client omit it?
- Is a cross-tenant query valid from a security/business standpoint?
- Does a second index provide enough read benefit to justify write/storage overhead?
- How frequent is this query compared to other queries?

### 11.3. Small Data Alters Index Decisions

In a 100-order test:

~~~text
COLLSCAN 100 docs -> 1 ms
IXSCAN 10 keys -> 1 ms
~~~

You cannot extrapolate that both plans are equivalent across 50 million orders. At scale, documents examined and I/O diverge sharply, especially once the working set exceeds cache.

### 11.4. Queries with Skewed Result Sets

Test the same query shape across:

~~~text
tenant-hot:       millions of records
tenant-large-2:   hundreds of thousands
tenant-123:       small number of records
~~~

Note:

- The hot tenant has many more pages to read.
- Ranges and sort/limit behavior differ.
- `nReturned` may be 50 in both cases, while the work before retrieving the top 50 differs.
- Query plan caching and parameter distributions can cause variance.

Measure **per-query-shape distributions**, not just a single favorable query parameter.

### 11.5. $group and Spilling

~~~javascript
orders.aggregate([
  {
    $match: {
      tenantId: "tenant-hot",
      createdAt: {
        $gte: ISODate("2026-06-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      total: { $sum: "$amountCents" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } }
], { allowDiskUse: true });
~~~

**allowDiskUse** permits certain pipeline stages to spill to temporary disk when server/version conditions apply; it does not make queries free or bypass every memory limit. Measure spills, temp I/O, and p95 while normal application traffic is running.

### 11.6. $lookup and Cardinality

When `customers` has an index on `_id`, a point-lookup join behaves differently from joining on an unindexed `foreignField`. With large datasets and separate shards, join cost can exceed estimates drawn from a few hundred documents.

Compare:

~~~text
Number of outer documents
Foreign index availability
Average and p99 matches per join key
Result document size
Memory/disk spilling
Network cost in sharded cluster
~~~

Do not benchmark only a query returning 20 orders at the end of a pipeline if earlier stages processed millions of records.

### 11.7. Indexes Affect More Than Reads

Every additional index adds cost to:

- Disk and memory.
- Insert write amplification.
- Updates whenever indexed fields change.
- Index build/rebuild time.
- Backup/restore time.
- Operational complexity.

Evaluate indexes in a **mixed workload**, not for a single read query in isolation.

### 11.8. TTL and Cleanup

When using TTL for logs/sessions:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

With high volumes of expiring documents, TTL deletes generate write load and oplog entries. Budget for purge backlogs and I/O matching expiration rates; **TTL cleanup does not execute with exact wall-clock precision**.

Do not use a test containing only non-expired documents to conclude TTL deletion has no throughput impact.

## 12. Worked Example: Forecasting Capacity for a Collection

Suppose a system has:

~~~text
Current retained documents:       30,000,000
Average BSON size:                2.5 KiB
Net new documents/day:            250,000
Forecast horizon:                 365 days
Index size observed at baseline:  45 GiB
Storage compression ratio:        measured, not assumed
Replica set:                      3 data-bearing members
~~~

### 12.1. Forecasting Document Count

With no deletes/retention and steady growth:

~~~text
documentsAfterOneYear
  = 30,000,000 + 250,000 * 365
  = 121,250,000
~~~

### 12.2. Forecasting Logical Bytes

~~~text
logicalBytes
  = 121,250,000 * 2,560 bytes
  = 310,400,000,000 bytes
  ≈ 289.1 GiB
~~~

This figure excludes indexes, oplog, overhead, and updates that enlarge existing documents.

### 12.3. Do Not Blindly Fix the Index Ratio

Given the baseline:

~~~text
current logical data ≈ 71.5 GiB
current index size  = 45 GiB
~~~

The current index/logical ratio is roughly 0.63. However, future index growth also depends on:

- Increasing cardinality.
- Growing or shrinking key sizes.
- Changes in multikey arrays.
- Added/removed index definitions.
- Compression and storage engine behavior.

You can use the measured ratio as an **initial forecast assumption** with error bounds, then recalibrate as the corpus grows; do not treat 0.63 as a permanent constant.

### 12.4. Physical Storage Under a Scenario Model

Suppose for this worked example:

~~~text
Projected logical BSON: 289 GiB
Scenario compression factor: 0.65
Estimated collection storage: 188 GiB
Estimated index storage: 180 GiB
Other allocated/oplog overhead: 50 GiB
------------------------------------
Estimated per-member storage: 418 GiB
~~~

These components are **estimates**, not measurements from a specific deployment. Adjust them using real metrics.

If the example policy requires **30% operational free headroom**:

~~~text
Required usable volume capacity
  ≈ 418 GiB / (1 - 0.30)
  ≈ 597 GiB per data-bearing member
~~~

Across three data-bearing members:

~~~text
Approximate provisioned volumes:
  597 GiB * 3 = 1,791 GiB
~~~

In practice, round to provider storage tiers, plan appropriately for oplog/index builds/migrations, and budget backups separately.

**30% is only an illustrative assumption**; adjust the percentage based on reliable benchmarks, retention, and SLOs. Do not adopt it verbatim as a universal rule.

### 12.5. Backup Capacity Differs from Live Storage

A three-copy replica set does not replace backups:

~~~text
Replication:
  protects service availability and copies current state.

Backup:
  supports recovery from deletion, corruption,
  operational mistakes and historical restore.
~~~

If a bug deletes 100,000 orders, the deletion also replicates to secondaries. You must budget snapshot retention, PIT oplog/backup chains, encryption, and restore bandwidth independently.

### 12.6. Limitations of the Linear Model

The model above holds only under its assumptions:

- Constant net new documents per day.
- Constant average document size.
- No significant retention cutoff.
- Compression and index growth match estimates.

If growth accelerates or archiving is enabled, rebuild the forecast from **net retained bytes**, not simply newly inserted documents.

## 13. Worked Example: When to Add RAM Instead of Adding Shards?

Suppose a replica set has:

~~~text
Total live data:          800 GiB
Frequently read dataset:  70 GiB
Hot indexes:              25 GiB
Current memory:           64 GiB
Disk read IOPS:           high at peak
CPU:                      40% average at peak
p95 read latency:         misses SLO
~~~

A reasonable hypothesis is that the working set regularly exceeds available cache, causing disk reads. However, this is **not yet a conclusion**: inspect WiredTiger eviction metrics, I/O latency, query plans, memory allocation, and query selectivity.

### 13.1. Two Options

**Option A — Upgrade RAM/node size:**

- Allows more hot data/index pages to stay cached.
- Minimal topology changes.
- Requires checking upgrade/failover procedure and cost.

**Option B — Add shards:**

- Distributes data/workload if the shard key is well chosen.
- Requires `mongos`/CSRS/balancer and migrations.
- Increases operational cost and complexity.
- Cross-shard/scatter-gather queries can still be expensive.

If the primary bottleneck is cache size and the workload still fits comfortably on a stronger replica set, **Option A can be simpler**. If write throughput or storage growth is approaching single-node limits, sharding may be worth considering.

### 13.2. Decision Factors

| Condition | Tends to Favor |
|---|---|
| CPU/disk have headroom, high cache misses | Consider more RAM or shrinking the working set. |
| Dataset growth exceeds economical node sizes | Consider sharding/retention. |
| Writes distribute well under a strong shard key | Sharding is better justified. |
| One hot key drives most writes | Fix shard-key/workload design first. |
| Heavy cross-shard analytics | Re-evaluate query design/analytics architecture. |
| Priority on operational simplicity | Scaling up has an advantage while sufficient. |

### 13.3. Decisions Must Be Backed by Experiment

Run the **same workload and corpus** on 64 GiB vs larger RAM; measure cache/IOPS/p95 and cost. Likewise, simulate sharding in an isolated environment if it is a realistic contender.

Do not choose by gut feel such as “sharding is always faster” or “more RAM is always better”.

## 14. Java Sync Driver: Multi-Threaded Read Benchmark

The example below executes **bounded read-only queries** against the seeded lab collection using a shared `MongoClient` and measures client-side latency.

**Do not run in production.** This tool only illustrates sample collection and does not replace a load generator with open-loop arrival rates, soak runs, error categorization, and resource instrumentation.

### 14.1. A Bounded Java Workload

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;

public final class MongoReadBenchmark {
    private static final int THREADS = 8;
    private static final int OPS_PER_THREAD = 200;

    private static double percentileMillis(
            List<Long> sortedNanos,
            double quantile) {
        if (sortedNanos.isEmpty()) {
            return Double.NaN;
        }
        int index = Math.max(0,
                (int) Math.ceil(sortedNanos.size() * quantile) - 1);
        return sortedNanos.get(index) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_BENCHMARK_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_BENCHMARK_URI is required for lab");
        }

        List<Long> latencies =
                Collections.synchronizedList(new ArrayList<>());
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger returnedDocs = new AtomicInteger();

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                    client.getDatabase("perf_capacity_lab")
                            .getCollection("orders_benchmark");

            ExecutorService executor =
                    Executors.newFixedThreadPool(THREADS);
            List<Future<?>> futures = new ArrayList<>();
            long started = System.nanoTime();

            for (int thread = 0; thread < THREADS; thread++) {
                Callable<Void> task = () -> {
                    for (int i = 0; i < OPS_PER_THREAD; i++) {
                        boolean hot = ThreadLocalRandom.current()
                                .nextDouble() < 0.7;
                        String tenant = hot
                                ? "tenant-hot"
                                : "tenant-" + ThreadLocalRandom.current()
                                        .nextInt(400);

                        long operationStart = System.nanoTime();
                        try {
                            List<Document> result = orders.find(
                                    Filters.and(
                                            Filters.eq("tenantId", tenant),
                                            Filters.eq("status", "PAID")
                                    )
                            ).sort(Sorts.descending("createdAt"))
                             .limit(20)
                             .into(new ArrayList<>());

                            returnedDocs.addAndGet(result.size());
                            latencies.add(
                                    System.nanoTime() - operationStart);
                        } catch (RuntimeException ex) {
                            errors.incrementAndGet();
                        }
                    }
                    return null;
                };
                futures.add(executor.submit(task));
            }

            try {
                for (Future<?> future : futures) {
                    future.get();
                }
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            }

            double seconds = (System.nanoTime() - started)
                    / 1_000_000_000.0;
            Collections.sort(latencies);

            int attempted = THREADS * OPS_PER_THREAD;
            System.out.printf(
                    "attempted=%d errors=%d resultDocs=%d%n",
                    attempted, errors.get(), returnedDocs.get());
            System.out.printf("attemptedOpsPerSec=%.1f%n",
                    attempted / seconds);
            System.out.printf("p50=%.2fms p95=%.2fms%n",
                    percentileMillis(latencies, 0.50),
                    percentileMillis(latencies, 0.95));
        }
    }
}
~~~

### 14.2. Limitations of This Code

1. Measures client-side operation elapsed time, not the full HTTP request.
2. Uses a **closed-loop workload**: each thread waits for the previous query before sending the next.
3. Lacks a separate warm-up, fixed arrival rate, soak duration, or failure testing.
4. 1,600 operations is too few samples for reliable p99 estimates.
5. Exceptions are counted but not classified into timeouts, network errors, or pool errors.
6. `attemptedOpsPerSec` **includes failures**, not just successful throughput.
7. Lacks concurrent writes and server resource metrics.
8. Choosing 70% hot-tenant access is an illustrative assumption.

To evaluate capacity, broaden the workload mix, increase sample counts, and collect **CPU, disk, cache, network, and replica lag** simultaneously.

### 14.3. Do Not Create a New MongoClient per Operation

**MongoClient is designed to be shared and manages connection pooling**. Instantiating a client per query adds connection, authentication, and setup overhead, making the benchmark diverge from a real application.

### 14.4. Timeouts and Cancellation

Under concurrent workloads, always measure:

~~~text
successful operations
timeouts
pool checkout failures
server errors
client cancellations
~~~

Do not inflate throughput numbers by ignoring errors. If 40% of requests time out, a high attempted request count does not mean the benchmark meets its SLO.

## 15. Spring Boot/Spring Data: Measuring at the Application Boundary

Repository and `MongoTemplate` calls carry mapping overhead, connection pool waits, service logic, and network latency.

### 15.1. Database Latency Differs from HTTP Latency

~~~text
HTTP latency
  = gateway/proxy
    + authentication/authorization
    + application processing
    + driver pool wait / network
    + MongoDB execution
    + response serialization
~~~

A 10 ms MongoDB query does not guarantee the API responds in 10 ms. Measure both **DB operation latency** to find query/index bottlenecks and **end-to-end latency** to verify user-facing SLOs.

### 15.2. Micrometer Timer

Spring Boot can collect HTTP/JVM/pool metrics depending on configuration and version. Example creating a `Timer` for an operation:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedOrderQuery {
    private final MongoTemplate mongoTemplate;
    private final Timer timer;

    public InstrumentedOrderQuery(
            MongoTemplate mongoTemplate,
            MeterRegistry registry) {
        this.mongoTemplate = mongoTemplate;
        this.timer = Timer.builder("app.orders.query.duration")
                .description("Duration of a MongoDB order query")
                .tag("operation", "countByTenant")
                .register(registry);
    }

    public long countByTenant(String tenantId) {
        return timer.record(() ->
                mongoTemplate.getCollection("orders")
                        .countDocuments(
                                new Document("tenantId", tenantId)
                        )
        );
    }
}
~~~

This is an instrumentation example—it is **not** a recommendation to run `countDocuments` on a large collection for every HTTP request. Always measure operation frequency and cost.

### 15.3. Low-Cardinality Metric Labels

Prefer:

~~~text
operation="listRecentOrders"
collection="orders"
environment="benchmark"
~~~

Avoid:

~~~text
customerId="C-182763847"
orderId="O-890127341"
rawQuery="..."
~~~

Labels with millions of unique values cause **metrics cardinality explosion** and risk exposing data. Use controlled query shapes/templates instead.

### 15.4. Command Monitoring and Tracing

The MongoDB Java Driver supports command monitoring and tracing integrations depending on version. When instrumenting:

- Do not log raw BSON documents containing PII or secrets.
- Separate client pool wait time from DB execution time where possible.
- Sample data appropriately for traffic volume.
- Attach correlation ID, service name, and operation shape.
- Verify instrumentation overhead during benchmarks.

### 15.5. Pagination Is a Capacity Variable

~~~javascript
db.orders.find({ tenantId: "tenant-hot" })
  .sort({ createdAt: -1 })
  .skip(100000)
  .limit(20);
~~~

Deep pagination with large `skip` values can cost far more than page one even with a good index. Consider **keyset/cursor pagination** using sort fields with a stable unique tie-breaker and properly scoped filters.

Do not benchmark only the first page.

## 16. Tying Capacity Planning to SLOs and Growth Triggers

A useful capacity plan explicitly states **when to act**, not just how many GiB are projected.

### 16.1. Targets and Early Warnings

| Metric | Current | Target / SLO | Early-Warning Trigger |
|---|---|---|---|
| Read p95 | Measured | Per product requirements | Upward trend, approaching SLO breach. |
| Write p95 | Measured | Per product requirements | p95 rising alongside queues/IOPS. |
| Error rate | Measured | Within error budget | Sustained failures. |
| Disk free | Measured | Sufficient operational headroom | Runway drops below lead time. |
| CPU saturation | Measured | Retains burst headroom | Sustained saturation with rising latency. |
| Cache eviction/disk reads | Measured | Stable baseline | Rising together with tail latency. |
| Replication lag | Measured | Per consistency target | Exceeds threshold per member. |
| Backup age/restore test | Measured | Meets RPO/RTO | Stale backup or failed restore drill. |

Targets are **specific to your system**, not a universal set of thresholds enforced by MongoDB.

### 16.2. Forecasting Runway and Lead Time

Suppose:

~~~text
Usable free space: 480 GiB
Net storage growth: 20 GiB/day
Expected runway: 480 / 20 = 24 days
~~~

If it takes 14 days to approve, provision, test, and roll out an upgrade, a 24-day runway leaves little buffer for growth spikes.

~~~text
Trigger resource expansion when:
  estimatedRunwayDays
  <= provisioningLeadTimeDays + safetyBufferDays
~~~

Runway is an estimate: retention changes, migrations, batch imports, and hardware scaling can alter growth rates. Use rolling trends and adjust during unusual events.

### 16.3. Each Resource Has Its Own Runway

~~~text
Disk runway:         30 days
CPU runway:          90 days
IOPS runway:          7 days
Network runway:     150 days
~~~

The nearest bottleneck is **IOPS**, not disk capacity. Expanding storage bytes while keeping the same IOPS tier may fail to protect SLOs.

### 16.4. Seasonal Forecasts

~~~text
Normal:      1,000 writes/sec
Campaign:    5,000 writes/sec
Flash peak: 15,000 writes/sec
~~~

You need to know:

- Does the peak last 30 seconds or 6 hours?
- What are the write concern, retries, and indexing overhead?
- Is there queueing/buffering or is real-time processing mandatory?
- How do replication lag and consumer backlogs grow?
- Can load be smoothed via backpressure or batching?

If the peak is short and buffered by queues, the solution differs from a workload that must process every write immediately.

### 16.5. Do Not Look Only at Averages

~~~text
Average CPU: 40%
Peak CPU: 98% for 20 minutes
Read p95 misses SLO during peak
~~~

A 40% average CPU does not prove the system has adequate capacity. Evaluate rolling peaks, durations, p95/p99, and error budgets.

### 16.6. Per-Collection and Per-Tenant Growth

~~~text
Cluster total growth: 3% per month
Hot tenant growth:  25% per month
~~~

On a sharded cluster, a single tenant or range can hit limits before the whole cluster runs out of capacity. Forecast by **tenant cohorts, shard-key ranges, and eligible zones** when skew is significant.

### 16.7. Recovery Time Is Also a Constraint

RTO is affected by backup download bandwidth, restore/index rebuild throughput, shard/node count, replication catch-up, and data validation.

A 10 TiB database with low restore network bandwidth has vastly different recoverability than a 1 TiB database with high bandwidth, even if both back up daily.

### 16.8. Capacity Planning Must Include a Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Growth forecast too low | Disk fills early | High-growth scenario, rolling reforecast. |
| Single tenant spikes | Hot shard/cache | Workload skew monitoring, shard-key review. |
| Index build expands disk | Capacity incident | Reserve headroom, scheduled change window. |
| Backup/restore misses RTO | Slow recovery | Restore drills, throughput sizing. |
| Secondary lag on write surge | Stale reads/resume risk | Oplog planning, I/O headroom. |
| Cloud IOPS throttling | Tail latency spikes | Sustained load testing, storage tier sizing. |

## 17. Planning Safe Upgrades

### 17.1. Before the Change

1. Confirm the bottleneck using metrics/traces/`explain`.
2. Record cluster topology, MongoDB/driver versions, workload, and SLOs.
3. Capture baseline p95/p99, QPS, errors, and resource usage.
4. Forecast data/index/oplog/operational headroom.
5. Compare alternatives: query/index tuning, retention, RAM, storage, replicas, shards.
6. Verify backups, failover readiness, and maintenance policies.
7. Define success criteria, rollback conditions, and approvers.

### 17.2. When Scaling Up

Depending on the deployment:

- Rolling maintenance or failover may be required.
- Check node types, members, and supported upgrade procedures.
- Verify whether storage expansion also increases IOPS/throughput proportionally.
- Monitor replication lag and primary elections.
- Do not upgrade all members using procedures unsupported by the vendor.

### 17.3. When Adding a Shard

Monitor:

- The new shard is recognized by `mongos`.
- Zone placement and balancer window.
- Owned bytes/chunks per collection.
- Migration commits/failures.
- Donor/recipient disk, network, and replication headroom.
- Application p95/p99 during rebalancing.

Do not expect a new shard to receive exactly `1/N` of the data within minutes; workload skew, document sizes, and zones can produce different placement.

### 17.4. When Creating or Changing Indexes

Budget build time at real scale, disk/CPU/memory overhead, write impacts, and version-specific replica set/sharded index build behavior. An index build on 100 records does not prove building an index on 100 million records is safe during peak hours.

### 17.5. When Enabling TTL/Archiving

If 500 million documents are already past retention, do not assume enabling TTL deletes them instantly with zero load:

- TTL deletes run as background work.
- Deletes generate oplog and write activity.
- Index fragmentation and physical storage usage may shift.
- Phased batch cleanup throttled to protect SLOs may be necessary.
- Archive correctness and backup retention must be accounted for.

### 17.6. Rollback Conditions

~~~text
Abort or roll back via supported procedure if:
  application p95 stays above approved threshold
  error rate threatens error budget
  replication lag exceeds safe window
  free disk falls below operational headroom
  index build / migration repeatedly fails
~~~

Rollback feasibility depends on the change type: **resharding or large migrations are not always instantly reversible**. Understand commit points and official recovery paths beforehand.

### 17.7. After the Change

Compare the same workload before and after:

~~~text
p50, p95, p99
successful throughput
errors/timeouts
CPU/cache/disk/network
replication lag
storage/runway
cost per useful operation
~~~

If doubling node size raises successful throughput by only 3% with no latency improvement, revisit your bottleneck hypothesis.

## 18. Optimizing for Total Cost, Not Just One Query's Latency

### 18.1. Total Cost of Ownership

A MongoDB deployment incurs costs across:

- Compute: vCPU and RAM for `mongod`/`mongos`/CSRS.
- Storage: data, indexes, oplog, snapshots/retention.
- Provisioned IOPS and throughput tiers.
- Network egress and replication/migration traffic.
- Observability/log storage and support.
- Engineering effort for cluster operations, backup/restore, and incident response.
- Cost of schema, index, and shard key changes.

An extra index might shave 100 ms off a rare query while increasing write cost by 15% across all inserts. Good decisions weigh **query frequency, SLOs, and total workload**, not a single microbenchmark.

### 18.2. Cost per Useful Operation

An economic metric:

~~~text
costPerMillionSuccessfulOps
  = totalInfrastructureCostForPeriod
    / successfulOperationsInPeriod
    * 1,000,000
~~~

SLOs and availability still apply. Cutting cost in a way that multiplies p99 latency by ten can worsen business outcomes.

### 18.3. Scale-Up Cost Does Not Always Scale Linearly

Example:

| Node Size | Relative Cost | Throughput Meeting SLO (Illustrative) |
|---|---:|---:|
| 4 vCPU / 16 GiB | 1.0× | 800 ops/s |
| 8 vCPU / 32 GiB | 1.9× | 1,500 ops/s |
| 16 vCPU / 64 GiB | 3.8× | 1,900 ops/s |

If adding resources beyond 8 vCPU yields minimal throughput gains, you may have hit an IOPS, locking, network, or inefficient query limit. **These numbers are illustrative only** and do not represent any specific MongoDB product tier.

### 18.4. Query Optimization Can Be Cheaper Than Scaling

Compare:

~~~text
Query A:
  docsExamined = 2,000,000
  nReturned    = 20

After appropriate index:
  docsExamined = 25
  nReturned    = 20
~~~

Query/index optimization can cut CPU and IOPS far more cheaply than buying larger nodes. Because the new index still adds storage and write overhead, benchmark the mixed workload.

### 18.5. Do Not Skip the Cost of Running Proper Benchmarks

A production-like benchmark may require:

- Generating hundreds of GiB or TiB of data.
- Running a test cluster for multiple days.
- Storing logs, trace samples, and metrics.
- Isolating environments and backups.
- Provisioning sufficiently powerful traffic generators.

This is the cost of avoiding mis-sized capacity purchases or production outages. You can optimize benchmark cost using **representative sampling, staged experiments, and data-to-cache ratios**, rather than testing an overly tiny dataset.

## 19. Common Operational Scenarios

### 19.1. Case A — Production Grows from 5 Million to 50 Million Documents

~~~text
Before:
  5M docs, indexes fit in cache, p95 20 ms

After:
  50M docs, cache evictions high, p95 250 ms
~~~

Investigate:

1. Did the query shape or index plan change?
2. Did keys/docs examined grow faster than `nReturned`?
3. How much did the working set and index bytes grow?
4. Did cache evictions and disk IOPS/latency rise alongside p95?
5. Did read/write QPS or long-tail queries shift?
6. Are retention/archiving or index reductions feasible?

Do not conclude “MongoDB is slow because there are many documents” before pinpointing the cause.

### 19.2. Case B — Disk Usage Exceeds Forecast

~~~text
Forecast: 300 GiB used after 1 year
Actual:   600 GiB after 8 months
~~~

Check:

- Did average BSON document size grow?
- What are index count, multikey fan-out, and key sizes?
- Are TTL/archiving jobs running, and is there a backlog?
- Is there duplicated data, failed cleanup, or long-running migrations?
- Where are oplog and backup snapshots stored?
- Did compression and storage engine allocation differ from assumptions?
- Were data copies across replica members double-counted or mixed up?

Fix **metric definitions** before revising the forecast; avoid mixing logical bytes with total physical copies.

### 19.3. Case C — High CPU, Low Disk

~~~text
CPU: 95%
Disk IOPS: 20% capacity
Cache eviction: stable
P95 query latency: high
~~~

Prioritize inspecting aggregations/sorts, execution plans, CPU-intensive expressions, BSON processing, and concurrency. Increasing disk throughput will likely not help.

### 19.4. Case D — Low CPU, High Disk Latency

~~~text
CPU: 25%
Random disk reads: high
IOPS throttling: observed
P99 latency: high
~~~

Analyze cache misses, working set, storage tier, access patterns, and index selectivity. Adding vCPUs will likely not reduce p99.

### 19.5. Case E — One Very Hot Tenant

~~~text
Tenant A: 70% write load
All other tenants: 30%
Overall cluster disk: balanced
One shard primary CPU: 98%
~~~

This is likely **workload skew**. Inspect the shard key, hot-key frequency, and query targeting. The balancer mainly distributes data ranges; you may need to redesign partitioning rather than waiting for owned bytes to balance further.

### 19.6. Case F — Secondary Read Scaling Causes Stale Data

After switching read preference to `secondaryPreferred`, primary load drops, but users who just updated an order do not always see the new state right away.

This is a **consistency contract** issue. Decide which endpoints tolerate stale reads and which require reading from the primary or causal consistency. Do not trade correctness for throughput without explicit business design.

### 19.7. Case G — Index Build Nearly Fills the Disk

A large new index consumes additional storage and can create temporary overhead and heavy I/O. If free disk space is near the threshold, the build risks failing or impacting availability.

Before building:

1. Estimate index size on a representative corpus.
2. Measure free space and ongoing growth during the build window.
3. Check version-specific index build behavior.
4. Prepare a maintenance, rollout, and rollback plan.
5. Monitor replication, CPU, disk latency, and application errors.

### 19.8. Case H — Benchmark Performs Well Only Because Page Cache Is Warm

Run 1:

~~~text
p95 180 ms
disk reads high
~~~

Run 2:

~~~text
p95 20 ms
disk reads low
~~~

Do not rush to declare the system optimized. Inspect cache state, run order, warm-up, query key distributions, and the OS cache. Report both **warm and mixed/cold workloads**.

### 19.9. Case I — Query Runs Fast Because It Returns Zero Results

The test query passes `customerId` as a String while production stores an ObjectId. The benchmark returns `nReturned=0` in 1 ms. That is a **correctness failure**, not a performance win.

Always verify matched data by BSON type and expected result counts.

### 19.10. Case J — p95 Looks Fine While p99 and Timeouts Climb

~~~text
p50: 12 ms
p95: 80 ms
p99: 4 seconds
timeouts: 1%
~~~

Investigate long-tail queries, batch jobs, pool queues, primary elections, disk stalls, and large documents. Capacity expansion must target **tail latency and error rates**, not just the mean.

### 19.11. Case K — Adding Shards Increases Cost While Latency Stays Flat

If the workload consists mostly of scatter-gather queries lacking shard-key predicates, adding shards increases fan-out and cost without improving p95.

Check query targeting with `explain` through `mongos` and fix queries, indexes, or schema before scaling out further.

### 19.12. Case L — Backup Restore Misses RTO

The live cluster handles 2,000 ops/s, yet restoring 4 TiB takes more hours than the RTO permits. Examine backup topology, snapshot/PIT strategy, bandwidth, index rebuilds, replica catch-up, and restore drills.

**Capacity includes recoverability**, not just live query throughput.

## 20. Table of Optimization Measures and Verification Metrics

| Measure | Hypothesis | Metrics That Must Improve | Side Effects to Monitor |
|---|---|---|---|
| Compound index | Reduce scanned docs/sort | Docs/keys examined, p95 | Index bytes, write latency. |
| Add RAM | Reduce cache misses | Disk reads/evictions, p95 | Cost, other memory pressure. |
| Higher IOPS tier | Reduce disk queue | Disk latency, p99 | Storage cost. |
| Add vCPU | Reduce CPU contention | CPU headroom, throughput | I/O may become the new bottleneck. |
| Secondary reads | Reduce primary read CPU | Primary QPS, latency | Staleness, secondary lag. |
| Add shard | Distribute storage/work | Owned bytes/QPS by shard | Migrations, zones, scatter-gather. |
| Reshard collection | Improve entropy/targeting | Hot shard ratio, p95, QPS | Operational impact, index design. |
| TTL/retention | Shrink retained data | Data/index growth, working set | TTL backlog, delete I/O, compliance. |
| Archive cold data | Shrink hot storage | Cache/disk/latency | Rehydration, query complexity. |
| Application cache | Reduce repeat reads | DB read QPS, latency | Invalidation, stale data. |
| Pagination change | Reduce deep skip cost | Keys/docs examined, p95 at page N | Cursor semantics. |
| Batch writes | Lower per-record overhead | Successful throughput | Batch size, failures/retries. |

Do not optimize a metric in this table without watching the side effects on the same row.

## 21. Capacity Planning and Benchmark Checklist

### 21.1. Inventory and Baseline

- [ ] MongoDB deployment type/version, driver version, and topology documented.
- [ ] Document counts and BSON sizes recorded per collection.
- [ ] `indexSizes`, compression/storage estimates, and disk allocations recorded.
- [ ] Logical bytes separated from physical storage and replica copies.
- [ ] Working set/cache metrics and disk IOPS/latency collected.
- [ ] CPU, memory, network, and connection pool metrics collected.
- [ ] Peak-hour throughput and read/write mix recorded.
- [ ] p50/p95/p99 latencies and error/timeout rates recorded.
- [ ] Replication lag, oplog window, and backup health checked.
- [ ] If sharded: owned bytes/QPS per shard and shard-key statistics recorded.

### 21.2. Growth Model

- [ ] Daily/monthly new record rates estimated.
- [ ] Net retained documents calculated after TTL/archiving/deletes.
- [ ] Average and tail BSON document sizes tracked.
- [ ] Document growth or indexed-field changes from updates factored in.
- [ ] Index count, multikey fan-out, and key size growth accounted for.
- [ ] Compression ratio grounded in a representative corpus.
- [ ] Oplog retention, snapshots, backup archives, and restore capacity budgeted.
- [ ] Base, high-growth, and stress forecasts prepared.
- [ ] Operational headroom reserved for index builds, migrations, and bursts.
- [ ] Expansion triggers tied to runway and lead time.

### 21.3. Test Corpus

- [ ] Enough documents/bytes that the dataset does not fit purely in cache.
- [ ] BSON field types match production.
- [ ] Arrays, nested objects, null/missing values, and long-tail sizes included.
- [ ] Realistic tenant/customer/status/cardinality distributions.
- [ ] Hot keys and skew modeled.
- [ ] Timestamps span retention windows and query recency.
- [ ] Index definitions match target configuration.
- [ ] Query results validated for business correctness.
- [ ] No unauthorized production PII or secrets included.
- [ ] Seeding process is repeatable and cannot wipe non-lab data.

### 21.4. Benchmark Workload

- [ ] Multiple query shapes weighted according to telemetry.
- [ ] Includes reads, writes, updates, aggregations, and batch jobs.
- [ ] Realistic concurrency with documented arrival model.
- [ ] Includes warm-up, steady state, spike, and soak phases as appropriate.
- [ ] Tests both warm and mixed/cold cache scenarios.
- [ ] Measures successful throughput and error rates.
- [ ] Reports p50/p95/p99 instead of averages alone.
- [ ] Monitors load generator CPU, memory, and network.
- [ ] Captures server CPU, cache, disk, and replication concurrently.
- [ ] Compares multiple runs against the same configuration/baseline.

### 21.5. Scaling Decision

- [ ] Bottleneck confirmed with measurements.
- [ ] Alternatives compared (indexes, RAM/IOPS scaling, replicas, sharding).
- [ ] Consistency and read preferences reviewed when read-scaling.
- [ ] Shard key and zone constraints evaluated if sharding.
- [ ] Capacity cost and operational complexity estimated.
- [ ] Downtime, failover, and upgrade compatibility assessed.
- [ ] Backups and restores still meet RPO/RTO after the change.
- [ ] Migration and rollback plans follow supported procedures.
- [ ] SLO owner and change approver identified.
- [ ] Post-change benchmark and monitoring scheduled.

## 22. Practice Exercises

These exercises use a dedicated lab dataset and do not require running load directly against production.

### Exercise 1 — Distinguishing Size Metrics

Explain the differences between **logical BSON bytes, physical collection storage, totalIndexSize, working set, and diskUsedBytes**. Why should they not be collapsed into one field named "databaseSize"?

### Exercise 2 — Logical Growth Rate

An application writes 250,000 documents/day at an average of 3 KiB each. Calculate logical inserted GiB/day and GiB/year assuming no deletions.

### Exercise 3 — 90-Day Retention

A service writes 500,000 sessions/day averaging 1 KiB with a 90-day retention. Estimate steady-state document count and logical data size. Why can TTL lag and physical storage differ from the forecast?

### Exercise 4 — Weighted Average Document Size

70% of docs are 1 KiB, 25% are 4 KiB, and 5% are 20 KiB. Calculate the weighted average BSON size. Why is testing only 1 KiB docs misleading?

### Exercise 5 — 5% Monthly Growth

Build a docs/day forecast for months 0, 1, 3, 6, and 12 given a baseline of 300,000 and 5% monthly growth. Contrast compounding growth with linear growth.

### Exercise 6 — Index Ratio

Current logical data is 120 GiB and indexes are 50 GiB. Compute the index/logical ratio, then explain why you cannot apply that same ratio indefinitely if a multikey index is added.

### Exercise 7 — Replica Storage

One data-bearing member uses 400 GiB in a three-member replica set. Estimate total live physical storage and list uncounted overhead.

### Exercise 8 — Sharding and Replication

A 900 GiB collection is split evenly across three shards, each a three-member replica set. Distinguish approximate data per shard from total replicated physical data before indexes/overhead.

### Exercise 9 — Headroom

Projected live storage is 420 GiB/member. If policy requires 25% free headroom, compute minimum provisioned volume capacity using `data / (1 - 0.25)`.

### Exercise 10 — Disk Runway

A shard has 500 GiB usable free space and grows by 25 GiB/day net. Calculate runway. With a 15-day change lead time and 10-day safety buffer, has the expansion threshold been reached?

### Exercise 11 — CPU vs IOPS

Case A: CPU=95%, low disk latency. Case B: CPU=25%, disk latency 40 ms with IOPS throttling. For each case, what would you measure and which hypothesis would you prioritize?

### Exercise 12 — Working Set

A 2 TiB database serves 90% of reads from the most recent 100 GiB. Why does RAM not necessarily need to equal 2 TiB? Under what conditions would sizing for just the 100 GiB hot set still fall short?

### Exercise 13 — Cache Misses

When dataset size grows 10× with unchanged RAM, disk reads and p99 jump sharply. Name at least five metrics/queries to inspect before purchasing more RAM.

### Exercise 14 — Little's Law

A steady workload achieves 3,000 requests/s with a 40 ms average response time. Compute approximate average concurrency. Why does that number not equal the required `maxPoolSize`?

### Exercise 15 — Query with Index

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Propose a candidate compound index and list the metrics in `explain.executionStats` to measure for verification.

### Exercise 16 — Query Returning Zero Results

Production stores `customerId` as an ObjectId, whereas the benchmark uses a string. Why is tiny latency untrustworthy? Explain how to verify BSON types and correctness.

### Exercise 17 — Selectivity

`status = "PAID"` accounts for 10% of docs in test but 95% in production. How does the usefulness of a single-field index on `status` change?

### Exercise 18 — Tenant Skew

10 large tenants generate 75% of queries, while the remaining 990 tenants generate 25%. Design a workload generator that reproduces this skew rather than uniform randomness.

### Exercise 19 — Long-Tail Document Sizes

1% of orders have over 100 items, while the rest have 1–5. Why is testing only at an average of 3 items unsuitable for evaluating p99 and index fan-out?

### Exercise 20 — Query Planner

A 1,000-doc collection runs fast with a COLLSCAN. What data must you gather before concluding no index is needed at 100 million docs?

### Exercise 21 — Mixed Workload

Design a workload with 50% point reads, 20% list/filter queries, 20% writes, and 10% aggregations. What must you measure so that an index speeding up list queries does not silently degrade writes?

### Exercise 22 — Open-Loop vs Closed-Loop

Explain both load-generation models. Why can closed-loop testing hide overload (coordinated omission) when service latency rises?

### Exercise 23 — Warm vs Cold Cache

The second run of a test is 5× faster than the first. List hypotheses and how to design fair repeat runs without harming production.

### Exercise 24 — Benchmark with Errors

A load test reports 4,000 attempted ops/s, but 20% of requests time out. Estimate successful ops/s assuming only 80% succeed, and explain why the benchmark likely fails SLOs.

### Exercise 25 — p50/p95/p99

An API has average=25 ms, p95=80 ms, p99=3 s. Why does scaling based on average latency miss the issue? Propose additional metrics.

### Exercise 26 — Data-to-Cache Ratio

Production has a 180 GiB working set and 45 GiB effective cache; test has an 18 GiB working set and 4.5 GiB effective cache. Compute the ratio for both, then explain which variables still differ.

### Exercise 27 — $collStats

Write an aggregation pipeline retrieving `storageStats` and `count` for a collection scaled to MiB. Explain why `storageSize` is not necessarily equal to logical BSON `dataSize`.

### Exercise 28 — $indexStats

Write an aggregation to inspect index accesses. Why is `accesses.ops` neither index bytes nor unique query count? What happens when a node restarts?

### Exercise 29 — Profiler

Describe how to use the profiler/slow query logs safely: permissions, privacy, sampling, and overhead. Why should high-level profiling not stay enabled at all times in production?

### Exercise 30 — Java Benchmark

Design a Java Sync Driver workload using a shared `MongoClient`, 8 threads, tenant-skewed queries, and p95 measurement. State the limitations of closed-loop execution and small sample sizes.

### Exercise 31 — Spring Boot Metrics

Explain the difference between MongoDB operation latency and HTTP latency. List three safe operation-shape metric labels while avoiding user IDs.

### Exercise 32 — Deep Pagination

With `skip(100000).limit(20)`, why can deep pages be slow? Propose keyset pagination and explain the tie-breaker requirement.

### Exercise 33 — Scale-Up or Sharding?

Cache misses are high, CPU is 40%, disk is 50%, and the dataset still fits on a larger node. Propose a benchmark to decide between adding RAM and adding shards.

### Exercise 34 — Read Scaling and Consistency

After switching to `readPreference` `secondaryPreferred`, primary CPU drops, but users see stale state. Why? Design which endpoints allow secondary reads and which require stronger consistency.

### Exercise 35 — Hot Key on a Shard

One tenant generates 60% of write QPS while owned data is balanced. Why might the balancer still be doing its job correctly? Propose how to analyze shard-key frequency and architectural options.

### Exercise 36 — Index Build Planning

An index build on 50,000 test records takes 1 second. What must you measure and budget when building on 500 million records?

### Exercise 37 — TTL Backlog

Migrating 100 million expired sessions to TTL cleanup. Outline write/oplog/disk risks and an appropriate phased cleanup approach.

### Exercise 38 — Cost per Successful Operation

Infrastructure costs 2,000 USD/month and serves 100 million successful operations/month. Calculate USD per million successful operations. Why must this metric still be paired with SLOs?

### Exercise 39 — RTO and Storage

Restoring 5 TiB at a sustained effective bandwidth of 200 MiB/s (ignoring rebuild/validation), estimate the lower bound on byte-transfer time. Which stages make actual RTO longer?

### Exercise 40 — Growth Plan

Draft a capacity proposal for the `orders` service covering:

~~~text
Current data and indexes
Growth forecast (base/high/stress)
Hot working set
SLO latency/throughput/error
CPU/RAM/IOPS/network utilization
Replica set/sharding topology
Recovery RPO/RTO
Options: query tuning, RAM, disk, shards
Cost and risks
Triggers, rollout, rollback
Benchmark evidence
~~~

Do not select an option based solely on results from 10,000 toy documents.

## 23. Review Questions

1. How does MongoDB capacity planning differ from simply checking how many GB remain on disk?
2. How do logical `dataSize` and physical `storageSize` differ?
3. How does index size affect RAM, disk, and write throughput?
4. What is the working set? Does it necessarily equal the entire database?
5. Why is total physical storage of a replica set with multiple data-bearing members larger than the logical dataset?
6. Does sharding automatically reduce total data volume?
7. What operations require operational headroom?
8. How does net growth differ from gross inserted bytes?
9. How do TTL and retention change a growth model?
10. Why do TTL deletes not immediately shrink physical disk usage?
11. Why is average document size insufficient for forecasting tail behavior?
12. How does multikey index fan-out affect storage and index maintenance?
13. Why does oplog storage depend on write activity rather than only live data size?
14. How do CPU, IOPS, and network bottlenecks manifest differently?
15. How should WiredTiger cache pressure be interpreted alongside evictions, I/O, and latency?
16. How does Little's Law relate throughput, latency, and concurrency?
17. Why cannot `maxPoolSize` be computed directly from concurrent HTTP requests alone?
18. Why can `secondaryPreferred` read preference produce stale reads?
19. What are the limits of vertical scaling?
20. When is sharding more appropriate than scaling up?
21. Why can a timestamp-ordered shard key create a hot shard?
22. Why can a single hot tenant still leave a hashed shard key unevenly loaded?
23. How does zone sharding affect capacity planning?
24. Why does adding a shard not guarantee instant data distribution?
25. Why does a fast COLLSCAN on 100 documents fail to prove no index is needed?
26. How can test selectivity differing from production alter plans and costs?
27. Why should synthetic data approximate real document shapes, array lengths, and tail sizes?
28. Why can a uniform tenant distribution hide a hot key?
29. What factors make a warm-cache benchmark faster than cold/mixed cache?
30. How can a closed-loop benchmark mask overload?
31. How does open-loop traffic model arrival rates differently from closed-loop?
32. Why must benchmarks measure errors and timeouts alongside throughput?
33. Why can p99 matter more than mean latency?
34. What data do `$collStats` and `$indexStats` provide?
35. Why must `indexStats.accesses.ops` not be treated as total index bytes?
36. How does `explain.executionStats` help assess scan amplification?
37. Why must `nReturned` and BSON types be verified during benchmarks?
38. How can a new index lower read latency while increasing write latency?
39. What is wrong with a Java benchmark creating a new `MongoClient` per query?
40. Why is Spring Boot HTTP latency typically higher than MongoDB execution time?
41. Why should metrics avoid high-cardinality labels like `orderId` or `tenantId`?
42. How must disk runway and provisioning lead time be combined?
43. Why can IOPS runway be shorter than disk-capacity runway?
44. How do you build base/high/stress forecasts that account for seasonality?
45. Why are backup/restore drills required when evaluating capacity?
46. When is archiving cold data preferable to expanding hot storage?
47. Why can a cluster with spare total capacity still suffer a hot shard?
48. When scaling, which metrics must be compared before and after to prove improvement?
49. How does rolling back an index differ from rolling back a resharding change?
50. What details about dataset, workload, hardware, and SLOs must a complete benchmark report include?

## 24. Summary

When tuning MongoDB performance, three questions must be connected together:

~~~text
                 Production-like workload
                         |
                         v
                Data shape and growth
                         |
                         v
         Current CPU / RAM / disk / network
                         |
                         v
                   Bottleneck?
                         |
              +----------+-----------+
              |                      |
              v                      v
        Query/index issue      Capacity distribution?
              |                      |
              v              +-------+----------+
       Optimize workload      |                  |
                             v                  v
                      Scale up / storage     Replica/sharding
                             |                  |
                             +--------+---------+
                                      |
                                      v
                            Repeat realistic benchmark
                                      |
                                      v
                       Validate p95/p99, errors and cost
                                      |
                                      v
                         Monitor growth / trigger next step
~~~

### 24.1. Key Principles

1. **Data size is not total capacity**: account for indexes, working set, oplog, replicas, physical storage, backups, and operational headroom.
2. **Optimize for the constrained resource**: adding RAM does not fix a CPU bottleneck; adding vCPUs does not fix query scans or storage latency.
3. **Forecast across multiple scenarios**: base, high growth, stress, net retention, document growth, and seasonal spikes.
4. **Do not plan capacity from 10,000 documents when production holds tens of millions**; scale, selectivity, array shape, and cache behavior can change completely.
5. **Test data must represent real distributions**, including hot tenants, document size tails, timestamps, missing values, and query parameter frequencies.
6. **Benchmarks need concurrency and tail latency**, not single sequential queries or mean latency alone.
7. **Verify query results**: a query returning zero matches due to a BSON type mismatch does not demonstrate good performance.
8. **Indexes are a two-way trade-off**: they reduce scanned docs for reads, but consume extra disk/cache and make inserts/updates costlier.
9. **Replica reads trade off consistency**, while sharding trades operational/routing complexity to distribute data and workload.
10. **The shard key governs scalability**; a hot shard-key value can remain hot even across many shards.
11. **Headroom and recoverability are mandatory**: index builds, migrations, backup restores, and replication catch-up require capacity beyond live traffic.
12. **Set triggers before running out of resources**: runway must exceed lead time plus a safety buffer.
13. **Judge benchmarks by SLOs and successful throughput**, combined with CPU/cache/disk/network/replication, not peak raw ops.
14. **Total system cost matters more than microbenchmarks**: choices require evidence across cost, latency, availability, and operations.
15. **Re-measure after scaling**, because a new bottleneck can surface in a different resource.

### 24.2. A Minimum Capacity Report Table

| Question | Evidence to Present |
|---|---|
| How much data exists and how fast is it growing? | Doc counts, BSON sizes, retained bytes, indexes, monthly forecasts. |
| How is the data accessed? | Hot/cold access, read/write mix, top query shapes, tenant skew. |
| What is the current bottleneck? | CPU, WiredTiger cache, disk IOPS/latency, network, `explain`. |
| What maximum load meets SLOs? | Representative benchmark, p95/p99, success QPS, error rate. |
| When is an upgrade needed? | Runway, lead time, safety buffer, growth scenarios. |
| What should be upgraded? | Options analysis: indexes, RAM, IOPS, replicas, shards, archiving. |
| Can it recover? | Backup/restore drill, RPO/RTO, free space, and replication. |
| How is success measured? | Baseline vs after, regression guard, operational cost. |

### Official References

- [MongoDB Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/) — performance observation and analysis.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — index design and trade-offs.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans and execution metrics.
- [db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — inspecting explain output for queries.
- [$collStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/collStats/) — collection storage statistics.
- [$indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/) — index usage metrics.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — `mongod` metrics.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — storage, compression, and cache.
- [Replica Set Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — read routing and consistency implications.
- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — data/workload partitioning.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, and query targeting.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — retention/cleanup.
- [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/) — backup/recovery planning.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — aggregation, command monitoring, and client API.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — `MongoTemplate`, query integration, and application patterns.

Metrics and API options may vary across MongoDB, `mongosh`, Java Driver, Spring Data, and deployment types (Atlas/self-managed). Before modifying production topology or capacity, verify against the documentation for your exact version and validate in a matching environment.

**Conclusion:** Do not tune MongoDB based on how fast a query runs on a few hundred records or a dataset small enough to fit in RAM. Model real data, account for growth and headroom, benchmark realistic scale and concurrency, pinpoint the constrained resource accurately, and choose a scaling solution proven by **SLOs, successful throughput, recovery capability, and total operating cost**.
