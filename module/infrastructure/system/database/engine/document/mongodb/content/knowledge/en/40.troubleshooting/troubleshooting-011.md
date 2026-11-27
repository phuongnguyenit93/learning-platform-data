# Hot Shards, Data Skew, and Scatter-Gather Queries in MongoDB

## 1. Context: Sharded Yet One Shard Remains Overloaded

A MongoDB system has three shards. The dashboard shows:

```text
                       Shard A   Shard B   Shard C
Data volume               34%       33%       33%
Inserts/updates per sec   87%        8%        5%
Primary CPU               94%       28%       23%
```

Meanwhile, a read endpoint reports:

```text
GET /events?status=FAILED
p95 latency: 120 ms -> 1.8 s after adding the third shard.
```

Two issues can occur simultaneously:

- **Write hotspot:** most write operations target shard-key ranges residing on a single shard even though bytes are evenly distributed.
- **Scatter-gather:** queries missing the shard key force `mongos` to send requests to many or all shards, then wait and merge results.

**Data skew** can also exist independently of those two issues: for example, shard A owns 75% of the data, B 20%, and C 5%. The distribution of documents/bytes/chunks and the distribution of CPU/operations do not necessarily match.

This lesson guides you through **identifying, quantifying, diagnosing, and remedying in a controlled manner** three categories of incidents in a MongoDB sharded cluster:

1. Write-concentrated shard (hot shard/write hotspot).
2. Skewed data or ranges/chunks across shards.
3. Scatter-gather queries and their consequences for latency, network, and fan-out.

### Learning Objectives

After this lesson, you will be able to:

- Read the structure of `mongos`, config server replica set, shards, shard keys, and data ranges.
- Distinguish **data skew**, **write/read workload skew**, and **query fan-out** using dedicated metrics.
- Understand why shard keys with low cardinality, overly frequent values, or monotonic growth create hotspots.
- Inspect actual data distribution via `sh.status(true)`, `sh.getShardedDataDistribution()`, and `$shardedDataDistribution`.
- Inspect balancer state, migrations, jumbo/indivisible ranges, and zones.
- Use `explain("executionStats")` from `mongos` to identify targeted vs. broadcast/scatter-gather queries.
- Use Shard Key Analyzer (`configureQueryAnalyzer`, `analyzeShardKey`) to measure candidate keys using sampled workloads.
- Distinguish range-based vs. hashed shard keys and their routing trade-offs.
- Propose mitigations ranging from **query rewrite/traffic throttling** to **refine/reshard**, without blindly modifying production.
- Connect sharding issues to the Java Driver/Spring Data MongoDB and API latency.
- Write runbooks, checklists, and practice on a sharded test cluster.

**Note:** Numbers in this lesson are illustrative examples. Commands that alter the balancer, shard keys, or indexes must be evaluated in a test environment and executed under an approved production runbook.

---

## 2. Sharded Cluster Architecture Recap

```text
                        Applications
                   Java / Spring Data
                              |
                              v
                 +--------------------------+
                 |         mongos           |
                 | Query router / metadata  |
                 +--------------------------+
                    /         |         \
                   v          v          v
               Shard A     Shard B     Shard C
              Replica Set Replica Set Replica Set
              P  S  S     P  S  S     P  S  S

                 Config Server Replica Set
                 Metadata: chunks/ranges,
                 shard key, zones, placement
```

- **`mongos`:** routes operations using the shard key and metadata; does not own collection data like `mongod`.
- **Shard:** typically a replica set; its primary member handles writes for that shard.
- **Config server replica set (CSRS):** stores partitioning/placement metadata; the balancer coordinates activity according to architecture/version.
- **Shard key:** a field or compound fields used to partition a sharded collection.
- **Chunk/range:** an interval of shard-key values; each range is owned by one shard at any given time.
- **Balancer:** manages range migrations to improve data distribution based on thresholds and zones.
- **Unsharded collection:** typically lives on the database's primary shard; it does not distribute automatically simply because the database lives in a sharded cluster.

### 2.1. Ranges and Bounds

A range spans from **lower inclusive** to **upper exclusive**:

```text
[MinKey, 100) -> Shard A
[100, 200)    -> Shard B
[200, MaxKey) -> Shard C
```

This example only illustrates a single shard key `customerId`; real ranges can be based on hashed values or compound keys.

A **single shard-key value** cannot be split across multiple ranges holding that same value to spread freely. Therefore, a shard key with one extremely frequent value is a warning sign requiring investigation.

### 2.2. Write Path and Read Path

**Insert:** `mongos` evaluates the document's shard key and routes the write to the shard owning that range.

**Read:** if the filter lets `mongos` narrow down shard-key ranges, the query can be **targeted**; otherwise, the router must send the request to many or all shards.

**Update/delete:** routing and rules around shard keys, `_id`, upserts, and multi-updates differ by MongoDB version and operation form. Do not write absolute rules across all versions; for critical workloads, **include the full shard key where appropriate** for reliable targeting and check docs for your exact version.

### 2.3. Do Not Connect Applications Directly to Shard Nodes

Normal applications connect through **`mongos`** (or the endpoint provided by Atlas). Starting in MongoDB 8.0, certain database commands run directly against a shard are blocked with an improper connection error requiring the router, except under maintenance-specific roles/conditions.

Never bypass `mongos` to "reduce scatter-gather" in production: you will lose routing/metadata semantics and risk returning incomplete data.

---

## 3. Three Distinct Symptoms and How to Prove Each

| Issue | Definition | Symptoms | Evidence needed |
| --- | --- | --- | --- |
| **Write hotspot** | Writes concentrate on one shard/range | One shard has high CPU/write IOPS, rising latency | Ops/s per shard, key frequency, key monotonicity |
| **Data skew** | Uneven storage volume/owned docs | One shard holds many bytes/docs, low free disk | `$shardedDataDistribution`, ranges, zones |
| **Scatter-gather** | Query sent to many or all shards | High query p95, `mongos` merge/fan-out, multiple shards busy together | `explain`, query shapes, shard key predicates |
| **Read hotspot** | Many reads hit one shard | High CPU/network on one shard while writes are balanced | Read ops per shard, targeted query distribution |
| **Balancer lag** | Migrations haven't achieved desired distribution | Persistent data skew, running/failed migrations | `balancerStatus`, logs, jumbo/zone metadata |

These symptoms **can coexist**, yet each requires distinct evidence. For example, a 33/33/34% storage split does not disprove that 90% of writes hit shard A.

### 3.1. A Few Simple Metrics

Write share of shard i:

\[
p_i = \frac{\mathrm{writes}_i}{\sum_j \mathrm{writes}_j}
\]

With 870/80/50 writes/s across three shards:

- A: 87%.
- B: 8%.
- C: 5%.

Storage skew ratio:

\[
\mathrm{max/min\ bytes}
=
\frac{\max_i(\mathrm{ownedBytes}_i)}
{\min_i(\mathrm{ownedBytes}_i)}
\]

If a shard has 0 bytes, do not divide by zero; present a table of bytes and shard counts, noting the collection may still be in initial distribution.

**Do not set a universal "above 60% is a bug" threshold.** It depends on tenant sizes, zones, traffic, time of day, and resource capacity.

---

## 4. First-Minute Incident Checklist

If API p99 spikes or one shard hits 95% CPU:

1. Record UTC timestamp, environment, database/collection, cluster/tier/server version.
2. Identify whether a shard is **hot** and capture CPU, writes/s, cache/disk/network.
3. Check **deployment events**, imports/backfills, TTL batches, migrations, and autoscaling.
4. Use `mongos` to inspect the current shard key and distribution.
5. Separate **CPU hotspot** from **data skew** using per-shard metrics.
6. Identify top query shapes and inspect `explain` for targeted vs. scatter.
7. Check balancer status, zones, range migrations, and jumbo ranges.
8. Inspect write key distribution, heavy tenants/single-key values, and monotonic keys.
9. Propose **safe load shedding first**, then schema/shard key changes once backed by evidence.
10. Measure post-remediation outcomes and keep a rollback plan.

**Never immediately** move chunks manually, disable the balancer, drop shard key indexes, or run `reshardCollection` in production.

---

## 5. Connecting Properly to `mongos` and Verifying Topology

From `mongosh`, connect to the `mongos` endpoint of a **test cluster** or an Atlas sharded cluster URI:

```javascript
db.adminCommand({ hello: 1 });
```

On `mongos`, the `hello` output includes:

```javascript
{
  msg: "isdbgrid",
  ok: 1
  // ... more fields
}
```

If `msg: "isdbgrid"` is missing, verify whether you accidentally connected directly to `mongod`.

Diagnostic commands (permissions depend on deployment):

```javascript
sh.status();
sh.status(true);
sh.getBalancerState();

db.adminCommand({ balancerStatus: 1 });
db.adminCommand({ listShards: 1 });
```

### 5.1. What Is `sh.status(true)` Used For?

Typically it displays:

- Shards in the cluster.
- Databases and each database's primary shard.
- Shard key/index strategy for sharded collections.
- Number of ranges/chunks per shard.
- Balancing and zone metadata.
- Potentially sharded data distribution.

For collections with many chunks, `sh.status(true)` enables verbose output, which can be huge. In production, prefer filtering by namespace or using the Atlas UI when checking specific indicators.

### 5.2. Do Not Confuse Primary Shard with Replica Set Primary

- **Database primary shard:** where a database's unsharded collections normally reside.
- **Replica set primary:** the primary member inside each shard's replica set, serving writes.

A database having primary shard A **does not mean** all sharded collections write only to A. However, an enormous/hot unsharded collection on A can still create an imbalance regardless of other collections' shard keys.

---

## 6. Measuring Data Skew with `$shardedDataDistribution`

On MongoDB versions supporting this stage, connect to `mongos` and target the `admin` database:

```javascript
db.getSiblingDB("admin").aggregate([
  { $shardedDataDistribution: {} },
  { $match: { ns: "commerce.orders" } }
]).toArray();
```

The `$shardedDataDistribution` stage was introduced in MongoDB 6.0.3; it requires the `shardedDataDistribution` privilege and **runs only on `mongos`**.

An equivalent `mongosh` helper:

```javascript
sh.getShardedDataDistribution()
  .filter(x => x.ns === "commerce.orders");
```

**This is a read example;** replace `commerce.orders` with the namespace under investigation.

### 6.1. Reading the Output

```javascript
[
  {
    ns: "commerce.orders",
    shards: [
      {
        shardName: "shardA",
        numOwnedDocuments: 7000000,
        ownedSizeBytes: 7300000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardB",
        numOwnedDocuments: 2000000,
        ownedSizeBytes: 2100000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardC",
        numOwnedDocuments: 1000000,
        ownedSizeBytes: 1050000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      }
    ]
  }
]
```

**These numbers are purely illustrative.**

| Field | Meaning |
| --- | --- |
| `ns` | Database.collection |
| `shardName` | Shard name |
| `numOwnedDocuments` | Documents currently owned by the shard |
| `ownedSizeBytes` | Estimated **uncompressed** size of owned documents |
| `numOrphanedDocs` | Documents left behind after migrations awaiting cleanup |
| `orphanedSizeBytes` | Estimated size of orphaned documents |

Note that `ownedSizeBytes` is **not identical to disk consumed**, due to compression, indexes, fragmentation, oplog, and other storage factors. Host/disk metrics are still required to assess disk capacity.

### 6.2. Orphans Do Not Default to Data Corruption

After a range migration finishes, data on the donor shard may be deleted asynchronously. Thus, orphaned docs can appear during cleanup. Never run `deleteMany()` directly to "clean up orphans", as doing so corrupts the cluster.

If orphaned docs grow without decreasing, check long-running reads, migration cleanup, balancer logs, and server version, following approved support guidance.

### 6.3. Metrics Can Be Estimates

After an unclean shutdown, count/size statistics can drift from true data until refreshed. Do not treat a 1–2% discrepancy as proof of data loss without verifying source/refresh semantics.

---

## 7. Chunk Count Differs from Document and Byte Counts

Suppose:

```text
Shard A: 100 chunks, 12 GB
Shard B: 110 chunks, 11 GB
Shard C:  95 chunks, 11 GB
```

This may represent an acceptable data distribution.

However:

```text
Shard A: 60 chunks, 30 GB
Shard B: 60 chunks,  4 GB
Shard C: 60 chunks,  2 GB
```

Equal chunk counts **do not mean balanced bytes**. Ranges can differ in document density, BSON size, and shard-key frequency.

A chunk can also receive intense concurrent writes right now despite small byte size. Therefore, observe separately:

- Chunks/ranges per shard.
- Owned docs/bytes per shard.
- Writes/reads per shard.
- CPU/IOPS/memory/network.
- Hot shard-key values.
- Balancer activity/errors.

### 7.1. Range Size and Migrations

Current MongoDB documentation cites a default configured range size of about **128 MB**. Balancer migration decisions rely on **data volume** and thresholds, not simply comparing chunk counts.

With the 128 MB default, documentation notes a collection can be considered balanced when the data difference between the largest and smallest shards is below roughly **3 × range size** (e.g., 384 MB). **Do not arbitrarily tune range size** just to make chunk counts look equal across shards.

### 7.2. Per-Collection vs. Total Bytes

If shard A holds many unsharded collections while shard B does not, high total storage on A does not necessarily mean a specific sharded collection is imbalanced. Measure **per namespace** and separate database primary shard/unsharded workloads.

---

## 8. Write Hotspot from a Monotonically Increasing Shard Key

A common anti-pattern:

```javascript
sh.shardCollection(
  "commerce.events",
  { createdAt: 1 }
);
```

Every new event has an ever-increasing `createdAt`.

### 8.1. Why Do Writes Pile Into One Range?

Ranged sharding orders data sequentially by shard key:

```text
...older...                         ...newest...
[MinKey, T1)   -> Shard A
[T1, T2)       -> Shard B
[T2, MaxKey)   -> Shard C  <-- all new writes
```

One range holds the upper bound `MaxKey`. If all new key values increase monotonically, they land in the tail range and at any moment **concentrate on whichever shard owns that range**.

The balancer can split and move ranges by data volume, but it cannot guarantee spreading **simultaneous newest writes** when the key continuously increases.

### 8.2. Signals

- Write ops/s on one shard dominate the rest.
- CPU/IOPS on that shard's primary scale directly with ingest traffic.
- Other shards retain spare capacity.
- Data bytes may still look fairly balanced.
- The hot range shifts over time, yet at any point only one or a few shards take most writes.

### 8.3. Hashed Keys Can Mitigate Monotonic Hotspots

Replacing `{createdAt:1}` with a well-distributed field such as:

```javascript
{ eventId: "hashed" }
```

can spread inserts evenly if `eventId` is sufficiently diverse and each event has a distinct ID.

**Trade-off:** **time-range** queries can no longer target shards using `createdAt` alone if the shard key is `eventId`. They may scatter-gather; measure the ratio of writes vs. time-range reads.

**Never** assume hashing a timestamp is automatically good: hashing distributes equality values, but severely weakens time-range pruning and shifts query patterns.

---

## 9. Write Hotspot from Low Cardinality

A shard key with very few distinct values:

```javascript
{ status: 1 }
// NEW, PAID, FAILED, CANCELLED
```

If most inserts start with `status="NEW"`, all writes for that value map to the same shard-key range, creating a hotspot.

### 9.1. What Is Cardinality?

Cardinality = the number of distinct shard-key values in the dataset.

| Candidate key | Hypothetical cardinality | Risk |
| --- | ---: | --- |
| `status` | 4 | Very low |
| `region` | 5 | Low; regions can be imbalanced |
| `tenantId` | 1,000 | Might work, unless one large tenant dominates |
| `eventId` | 100 million | High |
| `createdAt` | Very high | Likely monotonically increasing |

High cardinality is desirable but **insufficient**. `createdAt` has high cardinality yet still creates a hotspot via monotonicity.

### 9.2. A Single Value Cannot Be Split

A chunk/range covering a single shard-key value with very high frequency can become an **indivisible/jumbo range**. The balancer cannot split one identical key value into separate ranges to migrate partially under the same shard key.

To fix this, you usually must:

- **Refine** the shard key by adding a suffix, enabling splits within previously indivisible values.
- Or **reshard** to a different key.
- Or adjust the data/application model to yield a genuinely distributed key.

Never "force move" a jumbo range in production without evaluating downtime and write blocking.

---

## 10. Write Hotspot from High Key Frequency

Suppose 1,000 tenants exist, yet one tenant drives 80% of traffic:

```text
Tenant A: 80% inserts
Other 999 tenants: 20% inserts
```

The shard key:

```javascript
{ tenantId: 1 }
```

has cardinality 1,000, yet the single value `tenantId="A"` has massive **frequency**. All writes for tenant A concentrate on the shard owning that tenant.

### 10.1. Hashing `tenantId` Alone Does Not Solve It

```javascript
{ tenantId: "hashed" }
```

Hashing spreads **different tenants** across shards. However, **one single tenant A** still hashes to **one deterministic value**, routing to a single shard. It does not split a heavy tenant's workload.

This is a widespread misconception: "Using a hashed key eliminates hot tenants." That is false when the hotspot comes from a single extremely frequent value.

### 10.2. Compound Candidate Key

You might evaluate:

```javascript
{ tenantId: 1, eventId: "hashed" }
```

Distinct `eventId` values under tenant A produce distinct hash values, allowing ranges to spread **within the same tenant**, provided the cluster is sharded/distributed accordingly.

Trade-offs:

- Queries filtering only by `tenantId` may have to hit **multiple shards**.
- Queries with full equality on `tenantId` and `eventId` can be targeted.
- Filtering by time range without `eventId` increases fan-out.
- Compound hashed shard keys carry version-specific constraints and unique/index implications to verify.

Never adopt this candidate on gut feel; evaluate it with Shard Key Analyzer and query workload benchmarks.

---

## 11. Cardinality, Frequency, and Monotonicity: The Triad to Measure

| Property | Typically desirable | Risk |
| --- | --- | --- |
| **Cardinality** | Many distinct values | Too few ranges to split |
| **Frequency** | Document/write counts not heavily skewed | Hot values create hotspots/jumbo ranges |
| **Monotonicity** | Keys do not continuously increase/decrease | "Right-most"/"left-most" insertion hotspot |
| **Query locality** | Common filters include shard key/prefix | Frequent scatter-gather |
| **Update behavior** | Immutable/stable shard key | Cross-shard document movement/complexity |
| **Business constraints** | Supports tenancy/uniqueness | Unfavorable index and transaction constraints |

### 11.1. Do Not Choose a Key Based Only on Historical Data

A dataset might look balanced by tenant today while a newly launched campaign sends 90% of traffic to one new tenant. Analyze **incoming writes** and expected growth, not solely existing documents.

### 11.2. Shard Key Choice Shapes the Entire Workload

A key great for writes can hurt reads, and vice versa:

- `{createdAt:1}` favors time-range reads but risks write hotspots.
- `{eventId:"hashed"}` favors insert spread and `eventId` point lookups, but time-range reads scatter.
- `{tenantId:1,createdAt:1}` supports per-tenant time queries, yet one hot tenant plus increasing timestamps still yields a hot tail.
- `{tenantId:1,eventId:"hashed"}` spreads writes inside a tenant, yet per-tenant reports may fan out.

---

## 12. What Is Scatter-Gather?

A query sent through `mongos` takes one of two primary routing shapes:

### 12.1. Targeted Query

```text
Client:
  find({tenantId:"A", eventId:"evt-42"})
          |
          v
        mongos
          |
          +------> Shard B (exact range)
```

The router uses shard-key metadata to narrow execution to the shard or subset of shards containing the matching data.

### 12.2. Scatter-Gather Query

```text
Client:
  find({status:"FAILED"})
          |
          v
        mongos
        /  |  \
       v   v   v
      A    B   C
       \   |  /
        v  v  v
       merge results
           |
           v
         Client
```

If the filter omits the shard key (or its predicates prevent range pruning), `mongos` broadcasts to all relevant shards, waits for responses, and merges results.

### 12.3. Consequences When Adding Shards

Suppose a query scatters across 8 shards, each doing partial work. 2,000 HTTP requests/s can trigger **many thousands of shard-level query executions per second**. This is a conceptual fan-out relationship rather than guaranteeing every request emits exactly N server commands: optimizer, aggregation pipeline, caching, and implementation details can vary.

Tail latency of a scatter query can be dominated by the **slowest shard** plus network and merge overhead. When one shard is hot, scatter-gather forces otherwise unrelated requests to wait on the busy shard.

### 12.4. Scatter Is Not Always Wrong

Analytical aggregations scanning cluster-wide data may intentionally parallelize across all shards. The problem is **frequent OLTP queries lacking targeting**, not every broadcast aggregation.

---

## 13. Which Queries Are Usually Targeted?

Suppose the current shard key is:

```javascript
{ tenantId: 1, orderId: 1 }
```

Queries:

```javascript
// Full equality on shard key:
{ tenantId: "A", orderId: "O-101" }

// Prefix only:
{ tenantId: "A" }

// Missing prefix:
{ orderId: "O-101" }

// Completely unrelated to shard key:
{ status: "PAID" }
```

Analysis:

| Filter | Can `mongos` prune shards? | Notes |
| --- | --- | --- |
| Full equality `tenantId` + `orderId` | Yes, usually single shard | When key/ranges/metadata align |
| Only `tenantId` (prefix) | Possibly a subset of shards | Not guaranteed one shard if tenant spans multiple ranges |
| Only `orderId` | Usually broadcast | Missing leading `tenantId` prefix |
| Only `status` | Usually broadcast | A `status` index on each shard does not alter routing |
| `tenantId` + `status` | Can prune by `tenantId` | May still hit multiple shards |
| `$or` where one branch lacks `tenantId` | Can broadcast | Inspect full query logic |

**Never treat "shard key appears in filter" as a guarantee of single-shard execution**; prefixes, ranges, compound structure, hashing, zones, and full query shape govern how many shards are targeted.

### 13.1. Hashed Keys

With `{eventId:"hashed"}`:

```javascript
// Equality: mongos can hash the value and target.
{ eventId: "evt-42" }

// Range: hash order does not preserve natural order of eventId.
{ eventId: { $gte: "evt-100", $lt: "evt-200" } }
```

Range queries on original values can scatter-gather. Hashed distribution trades away range locality.

### 13.2. `_id` Is Not Automatically the Shard Key

If a collection is sharded by `{tenantId:1,eventId:"hashed"}`, a query:

```javascript
{ _id: ObjectId("...") }
```

does not automatically supply the full shard key. The `_id` index exists on each shard, yet **does not allow the router to target a single shard**. API endpoints looking up by ID should carry shard-key context when feasible.

### 13.3. Indexing and Routing Are Two Separate Steps

1. `mongos` decides which shard(s) receive the query.
2. **Each receiving shard** chooses a local index/query plan.

Creating `{status:1}` on every shard reduces documents scanned **within each shard**, but **never converts** `find({status:"FAILED"})` into a targeted query when the shard key is `eventId`.

---

## 14. Explain from `mongos`: Verifying Query Fan-Out

Connect `mongosh` to `mongos` and run against an actually sharded collection:

```javascript
const dbLab = db.getSiblingDB("hotspot_lab");

const targetedPlan = dbLab.events_hashed
  .find({ eventId: "event-42" })
  .explain("executionStats");

printjson(targetedPlan);
```

Then:

```javascript
const scatterPlan = dbLab.events_hashed
  .find({ status: "FAILED" })
  .limit(20)
  .explain("executionStats");

printjson(scatterPlan);
```

### 14.1. What to Look For

- Shard IDs/names participating in execution.
- Execution plan inside each shard.
- `nReturned`, `totalDocsExamined`, `totalKeysExamined` per shard when available.
- Stages involving `SHARD_MERGE`, `SHARDING_FILTER`, `SORT`, `IXSCAN`, `COLLSCAN` depending on engine/version.
- Merge logic and sort/limit placement.
- Actual query execution time per shard.

**Explain JSON structure varies by server version and query engine**; it does not always use an identical `queryPlanner.winningPlan.shards` path. Inspect the full output rather than grepping a single keyword.

### 14.2. Aggregations Can Split Pipelines

Example:

```javascript
dbLab.events_hashed.explain("executionStats").aggregate([
  { $match: { status: "FAILED" } },
  { $group: { _id: "$tenantId", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);
```

Explain may display `splitPipeline`, `shards`, `mergeType`, or other structures depending on version; `mongos` and shards divide merge responsibilities differently depending on pipeline stages.

### 14.3. Test in the Right Environment

Never run Explain on a **standalone** instance expecting to inspect multi-shard routing. Only a sharded cluster with at least two shards yields real routing evidence.

---

## 15. Atlas Sharding Insights and Per-Shard Metrics

On eligible MongoDB Atlas deployments, **Sharding Insights** brings together:

- Shards view: resource utilization, workload, data distribution.
- Collections view: distribution by namespace/ranges.
- Mongos Instances view: query router behavior.
- Balancer activity and metadata per current features.

Per referenced Atlas documentation, Sharding Insights requires an **M10+ sharded cluster, MongoDB 8.0+**, commercial Atlas Core, and specific feature restrictions. It is unavailable on standalone replica sets, certain cluster types, or lower tiers.

### 15.1. Read Along Two Axes

**Axis A — Data:** `ownedBytes`, `ownedDocs`, ranges/chunks.

**Axis B — Workload:** writes/s, reads/s, CPU, disk IOPS, network, operation latency.

A shard holding large data volume may not be hot; a shard holding small data volume can still be extremely hot.

### 15.2. Pick the Right Time Window

A batch import running from 14:00–14:10 UTC can be smoothed away on a 30-day graph. Narrow the window, view the finest supported granularity, and correlate deployment markers and batch job logs.

### 15.3. If Insights Is Unavailable

Use `sh.status`, `$shardedDataDistribution`, Atlas per-node metrics, command/profiler logs, or monitoring suitable for self-managed deployments. Never infer balanced data simply because a UI tab is absent.

---

## 16. Shard Key Analyzer: Measure Instead of Guessing

MongoDB 7.0+ supports **`analyzeShardKey`** to evaluate candidate/current shard keys using key characteristics and sampled workloads.

### 16.1. Start with Workload Hypotheses

Candidate keys might include:

```javascript
{ createdAt: 1 }
{ eventId: "hashed" }
{ tenantId: 1, createdAt: 1 }
{ tenantId: 1, eventId: "hashed" }
```

Do not pick a key on high cardinality alone; inspect both read/query distribution and writes.

### 16.2. Enable Controlled Query Sampling

In a test environment or approved production window:

```javascript
const events = db.getSiblingDB("hotspot_lab").events_hashed;

events.configureQueryAnalyzer({
  mode: "full",
  samplesPerSecond: 1
});
```

`configureQueryAnalyzer` requires appropriate privileges. `samplesPerSecond` is a **sampling rate**, not a guarantee of capturing one sample per second if operation volume is lower.

**Never leave sampling enabled for hours in production without an owner, retention rule, and policy.**

### 16.3. Analyze a Candidate Key

```javascript
const report = events.analyzeShardKey({
  eventId: "hashed"
});

printjson(report);
```

Additional options depending on method/version support:

```javascript
events.analyzeShardKey(
  { eventId: "hashed" },
  {
    keyCharacteristics: true,
    readWriteDistribution: true,
    sampleSize: 10000
  }
);
```

`sampleSize` and `sampleRate` cannot be used simultaneously. Distribution metrics depend on **actual sampled queries**, so too few samples can yield missing or unrepresentative metrics.

### 16.4. Disable Sampling After Investigation

```javascript
events.configureQueryAnalyzer({
  mode: "off"
});
```

Save anonymized reports, time ranges, traffic mix, and total sample counts in incident notes.

### 16.5. Report Sections

| Group | Meaning |
| --- | --- |
| `keyCharacteristics` | Cardinality, frequency, monotonicity |
| `numDocsSampled` | Sample size |
| `mostCommonValues` | Most frequent values and frequencies |
| `readWriteDistribution` | Targeting/read/write workload distribution from sampled queries |
| Routing-related metrics | Targeted/multi-shard/scatter ratios per version structure |

Do not treat an off-peak sample as representative of campaign or batch peaks. Compare multiple time windows and account for seasonal workloads.

---

## 17. Verify Key Data Properties Before Considering a Reshard

The aggregation queries below can be expensive on large collections; **run them in lab/staging or under approved query sampling**.

### 17.1. Heavy Tenants

```javascript
db.getSiblingDB("hotspot_lab").events_range.aggregate([
  { $group: { _id: "$tenantId", docs: { $sum: 1 } } },
  { $sort: { docs: -1 } },
  { $limit: 10 }
]).toArray();
```

Document counts **do not equal write throughput over time**; a tenant with many historical documents may not be the tenant generating 80% of live writes today.

### 17.2. Key Frequency

```javascript
db.getSiblingDB("hotspot_lab").events_range.aggregate([
  { $group: { _id: "$status", docs: { $sum: 1 } } },
  { $sort: { docs: -1 } }
]).toArray();
```

If 90% of events have `status="NEW"`, a `status` shard key is a dangerous candidate in terms of frequency.

### 17.3. Monotonicity

Inspect keys over time:

- At time T, do newly inserted `createdAt` values always increase?
- Do `ObjectId` or auto-incrementing sequences grow monotonically over time?
- Do historical batch imports invert trends?
- Are there distinct partitions/regions creating multiple active tails or just one?

`analyzeShardKey` is helpful, but combine it with application write traces and expected future patterns.

---

## 18. What Is the Balancer Responsible For and What Can It Not Do?

The balancer monitors data volume per sharded collection and can migrate ranges across shards when distribution skew crosses thresholds, while **respecting zone constraints**.

### 18.1. Migrations Have a Cost

Moving data generates:

- Network copy between donor and recipient.
- Index synchronization.
- Increased disk/CPU load.
- Replication overhead.
- Metadata updates and routing refreshes.
- Asynchronous cleanup on the donor.

Do not treat the balancer as a live scheduler that will automatically spread **CPU/writes per second** across shards.

### 18.2. Status and Diagnostics

On `mongos`:

```javascript
sh.getBalancerState();

db.adminCommand({ balancerStatus: 1 });

sh.status(true);
```

You can also inspect balancing status per collection (method and options depend on release):

```javascript
sh.balancerCollectionStatus("hotspot_lab.events_range");
```

If the balancer is enabled yet data skew persists, inspect migrations, zones, range sizes, jumbo/indivisible ranges, and migration failures.

### 18.3. When Should You Leave the Balancer Alone?

Minor data skew **below migration thresholds** is normal. The balancer balances based on data volume rather than triggering solely because chunk counts differ.

Disabling the balancer long-term can worsen imbalance over time; turning it back on will not resolve a **hot key value** or concentrated writes.

### 18.4. Never Reset Metadata Manually

Never manually edit `config.chunks`, `config.collections`, `config.tags`, chunk ownership, or balancer state inside the `config` database using unsupported commands. Corrupted metadata can severely break the cluster.

---

## 19. Jumbo/Indivisible Chunks and Stuck Migrations

When a range grows so large it cannot be split along the shard key, it can become a **jumbo/indivisible range**. This commonly happens when a shard key has highly repeated values or insufficient cardinality.

### 19.1. Signals

- `sh.status(true)` or balancer logs report `jumbo` or oversized range warnings.
- `balancerStatus` shows failed/retried migrations.
- One shard holds disproportionately high bytes for the collection.
- The balancer is enabled, yet data distribution fails to improve.
- Logs report range migration conflicts, replication lag, or disk pressure.

### 19.2. Do Not Run `forceJumbo` Lightly in Production

Commands/options like `moveRange`, `moveChunk`, `forceJumbo`, and clearing jumbo flags may exist depending on MongoDB version. MongoDB documentation warns that **forcing migration of a jumbo range can block writes for a long time**.

Therefore, follow a safe process:

1. Confirm it is genuinely an oversized/indivisible range.
2. Inspect migration logs, disk, replication health, ranges, and zones.
3. Analyze shard-key cardinality/frequency.
4. Evaluate **refine** or **reshard** to resolve the root cause.
5. If manual migration is necessary, follow an approved runbook with backups/change approval and engage MongoDB Support where appropriate.
6. Never delete data or manually edit config metadata.

### 19.3. One Hot Key Value Cannot Be Split by Moving

If 50 million documents share `tenantId="A"`, moving that range to shard B only **relocates the hotspot from A to B**; it does not split concurrent writes across A and B. You need a key capable of splitting across distinct values.

---

## 20. Zone Sharding: Data Skew Can Be Intentional

MongoDB allows defining **zones/tags** to pin shard-key ranges to designated shards.

Example:

```text
EU region -> EU shards
APAC region -> APAC shards
```

If APAC traffic is 4× larger than EU, APAC shards will carry more data and CPU load. That reflects **geographic/compliance policy**, not a balancer bug.

Before resharding or moving data:

- Check zone ranges and shard assignments.
- Check data residency/compliance requirements.
- Verify which shards ranges are allowed to migrate onto.
- Never move data out of its zone merely to make dashboard bars look even.

**The goal is not 33.3% across every shard**, but meeting SLOs, capacity headroom, and data-placement policy.

---

## 21. Refine Shard Key vs. Reshard

### 21.1. Refine: Append a Suffix to the Existing Shard Key

Suppose the current shard key is:

```javascript
{ tenantId: 1 }
```

You propose a new candidate:

```javascript
{ tenantId: 1, eventId: 1 }
```

`refineCollectionShardKey` appends field(s) **after** the existing shard key while preserving the existing prefix; this increases cardinality and enables splitting hot values.

Example **for API learning only; do not run outside lab/approved changes**:

```javascript
db.adminCommand({
  refineCollectionShardKey: "commerce.events",
  key: { tenantId: 1, eventId: 1 }
});
```

Practical requirements:

- A supporting index for the refined shard key must exist per requirements.
- All documents must satisfy field semantics (or handle missing values within version rules).
- Unique constraints/shard key rules must be valid.
- The existing prefix **is not changed**.
- Refining **does not immediately** redistribute existing data/writes across shards.
- Allow the balancer/subsequent range splits to redistribute in context.

### 21.2. Reshard: Choose a New Shard Key

MongoDB 5.0+ supports `reshardCollection` to change a sharded collection's shard key.

Example **DO NOT run in production without change approval**:

```javascript
db.adminCommand({
  reshardCollection: "commerce.events",
  key: { eventId: "hashed" }
});
```

Resharding redistributes data under a new key and changes routing semantics, yet it consumes **substantial resources** and imposes requirements/limitations around version, capacity, concurrent changes, and transactions.

### 21.3. MongoDB 8.0: Redistribute with the Same Shard Key

Some MongoDB 8.0 releases support **same-key resharding** using `forceRedistribution` where eligible:

```javascript
db.adminCommand({
  reshardCollection: "commerce.events",
  key: { eventId: "hashed" },
  forceRedistribution: true
});
```

This is **not** a fix for a single shard-key value absorbing all writes. It mainly helps redistribute data across shards **without changing the key**—for instance, after adding a shard—and still requires resource capacity and a runbook.

MongoDB 8.0 also offers `sh.shardAndDistributeCollection()` for applicable deployments. Never copy a command from a lesson into production without checking your current key, cluster version, and prerequisites.

### 21.4. Comparison

| Solution | What it solves | What it does NOT automatically solve |
| --- | --- | --- |
| Re-enable balancer if turned off | Halted data migrations | Single hot shard-key value |
| Add local index | Scan cost inside each shard | Scatter routing |
| Refine key with suffix | Increases cardinality/splittability | Existing hot tail immediately |
| Reshard to a new key | Changes routing, redistributes data and writes | Query patterns missing the new shard key |
| Same-key redistribution | Moves data onto added shards where eligible | Poor key cardinality/frequency |
| Add a shard | Increases total cluster resources | Single hot key pinned to one shard |
| Throttle/limit batch jobs | Short-term load relief | Root-cause key design |

---

## 22. Short-Term Mitigation for Write Hotspots

Before undertaking costly shard-key changes, apply impact-reducing measures (subject to business requirements):

1. **Throttle batch imports/backfills** driving 80% of writes into one range.
2. Cap per-tenant/per-producer write concurrency.
3. Reschedule heavy jobs if the business permits.
4. Reduce write amplification from redundant indexes.
5. Optimize update predicates, batch sizes, and network round trips.
6. Apply admission control/load shedding for non-critical traffic.
7. Pause high-impact background jobs temporarily.
8. Add compute/IOPS capacity deliberately to ease CPU/IO pressure while remediating.
9. Check whether active migrations are forcing the hot shard to process writes and copy chunks simultaneously.
10. Document rollback steps and watch p95/p99 and error rates.

### 22.1. Do Not Lower Write Concern Arbitrarily

Never downgrade from `majority` to `w:1` just for speed if the business needs durability/consistency. Likewise, never disable journaling, TLS, or auth to boost throughput.

### 22.2. Do Not Kill Operations by Duration Alone

An aggregation, transaction, or index build may legitimately run long. Before intervening, verify owner and consequences.

---

## 23. Fixing Scatter-Gather Through Query Patterns

If the shard key is `{tenantId:1,eventId:"hashed"}`, an endpoint running:

```javascript
db.events.find({ status: "FAILED" });
```

can broadcast across the entire cluster.

### 23.1. Include Shard-Key Context in APIs

If business requests naturally belong to tenant A and a specific event ID:

```javascript
db.events.find({
  tenantId: "A",
  eventId: "event-42"
});
```

This carries full equality on the shard key and qualifies for targeted routing.

### 23.2. When Only `tenantId` Is Known

```javascript
db.events.find({
  tenantId: "A",
  status: "FAILED"
});
```

Filtering on the **prefix** lets the router narrow the scope, though if tenant A spans multiple ranges/shards the query may still hit several shards. That is the trade-off between **spreading writes within a tenant** and **querying across an entire tenant**.

### 23.3. Never Inject Fake or Unverified `tenantId`

Never accept an unverified `tenantId` from a raw query parameter purely to make queries targeted. Tenant scope must come from authenticated principal/authorization context; otherwise you are merely optimizing a security vulnerability.

### 23.4. Queries Without a Shard Key Need a Different Strategy

Options:

- Secondary indexes for local query efficiency, even when scatter remains.
- Pre-aggregated/reporting collections keyed for analytics.
- Redesigning APIs to accept partition/tenant/time scopes sensibly.
- Offloading global search to a dedicated search engine when required.
- Considering materialized views/OLAP pipelines isolated from the OLTP cluster.
- Batching/async jobs and properly invalidated caches.
- Resharding with a key aligned to query patterns, if suitable for the full workload.

There is no free option: requiring shard-key fields on every request may be impossible for global admin queries; plan capacity for intentional scatter workloads.

---

## 24. Good Indexes on Shards Are Still Not Enough

Example collection sharded by `{eventId:"hashed"}`:

```javascript
db.events.createIndex({ status: 1, createdAt: -1 });
```

Query:

```javascript
db.events.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
```

`mongos` cannot deduce from a local `status` index which shards hold `status: "FAILED"`. It must ask **every shard**, each shard uses its local index, and results are merged and sorted.

### 24.1. Two Questions You Must Ask

1. **Routing:** How many shards does the query target?
2. **Execution per shard:** How many index keys/documents does each shard scan, and is there an in-memory sort stage?

Tuning local indexes without fixing fan-out reduces per-shard work, but does not reduce shard-level operation counts.

### 24.2. When `limit`/`sort` Scatters

A distributed sort/limit can require shards to produce candidate rows for `mongos` or a merge shard to combine. Do not assume `limit(20)` limits cluster-wide work to 20 documents; check Explain.

### 24.3. Index Skew

If one shard holds many documents for a hot tenant, index size and cache pressure on that shard can be disproportionately higher; do not inspect collection data bytes alone. Compare index sizes, cache eviction, disk IOPS, and memory per shard.

---

## 25. Java Driver: Writing Properly Sharded Queries

Java Sync Driver example:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

import static com.mongodb.client.model.Filters.*;

public class ShardingRoutingDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("hotspot_lab");
            MongoCollection<Document> events =
                db.getCollection("events_hashed");

            // Full equality on shard key {eventId: "hashed"}.
            Document targeted = events
                .find(eq("eventId", "event-42"))
                .first();

            System.out.println(
                targeted == null ? "not found" : targeted.toJson()
            );

            // Missing shard key, may scatter-gather.
            events.find(eq("status", "FAILED"))
                .limit(20)
                .forEach(doc ->
                    System.out.println(doc.getString("eventId"))
                );
        }
    }
}
```

**Important:** `events_hashed` must actually be sharded by `{eventId:"hashed"}` in the lab; on an unsharded collection, these two queries will not demonstrate `mongos` fan-out.

### 25.1. Do Not Create a New `MongoClient` Per Request

Reuse a singleton `MongoClient` per service. Each instance maintains connection pools and monitoring threads; recreating clients increases connection churn without fixing hotspots.

### 25.2. Read Preference Does Not Change Shard-Key Routing

Switching from `primary` to `secondaryPreferred` changes which replica member serves a **read** within a shard, yet it never turns a query lacking the shard key into a targeted query or reduces logical shard fan-out. You also accept replication lag and read-consistency trade-offs.

---

## 26. Spring Data MongoDB: Derived Queries Can Scatter Accidentally

Entity:

```java
@Document("events")
public class EventDoc {
    @Id
    private String id;
    private String tenantId;
    private String eventId;
    private String status;
    private Instant createdAt;
    // Constructors/getters/setters...
}
```

Repository:

```java
public interface EventRepository
        extends MongoRepository<EventDoc, String> {

    Optional<EventDoc> findByEventId(String eventId);

    List<EventDoc> findByStatus(String status);

    List<EventDoc> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Assuming the collection is sharded by `{eventId:"hashed"}`:

| Method | Expected routing |
| --- | --- |
| `findByEventId` | Equality on hashed key, usually targeted |
| `findByStatus` | Missing key, usually scatter |
| `findByTenantIdAndStatus` | Missing `eventId`, usually scatter |

Assuming another shard key `{tenantId:1,eventId:"hashed"}`:

| Method | Expected routing |
| --- | --- |
| `findByEventId` | Missing `tenantId` prefix, can scatter |
| `findByTenantIdAndStatus` | Has `tenantId` prefix, can prune subset, not guaranteed one shard |
| Query with both `tenantId` + `eventId` | Usually targeted to one shard |

**Key takeaway:** a Spring Data repository method **does not automatically enforce a business intent that "this query must be targeted"**; it merely builds a MongoDB filter. Verify sharding metadata and Explain for the resulting query.

### 26.1. `@Query` and Field Mappings

```java
@Query("{ 'tenantId': ?0, 'eventId': ?1 }")
Optional<EventDoc> findScopedByEventId(
    String tenantId,
    String eventId
);
```

When tenant scope is validated via auth context, this method can target the compound key `{tenantId:1,eventId:"hashed"}`.

With `@Field("tenant_id")` or BSON field names differing from Java property names, verify Spring Data mapping; `mongos` routes on **BSON shard-key fields**, not Java variable names.

### 26.2. Application N+1 Queries Magnify Fan-Out

If a service iterates 500 events and calls `findByStatus(...)` 500 times, with each call scattering across 8 shards, application fan-out explodes. Batch requests, redesign access patterns, cache, or use materialized read models when appropriate.

### 26.3. `@Aggregation` Needs an Early `$match`

With a pipeline:

```javascript
[
  { $match: { tenantId: "A", eventId: "event-42" } },
  { $project: { _id: 0, status: 1 } }
]
```

Placing the shard-key filter at the beginning gives `mongos` the best chance to target. However, the aggregation optimizer and merge stages involve multiple rules; confirm with Explain rather than relying purely on `$match` placement.

---

## 27. Safe Lab: Preparing a Sharded Test Cluster

**Prerequisite:** you already have a **MongoDB sharded test cluster** with at least two shards and required administrative privileges. This lesson does not walk through building a production sharded topology from scratch.

Never use a production database. In `mongosh`, confirm you are connected via `mongos`:

```javascript
db.adminCommand({ hello: 1 }).msg;
// "isdbgrid"
```

Use the lab database:

```javascript
const lab = db.getSiblingDB("hotspot_lab");

lab.events_range.drop();
lab.events_hashed.drop();
```

**Warning:** both `drop` commands delete data and indexes of those lab collections. Run them only when certain you are on an authorized test cluster/database.

### 27.1. Sharding Empty Collections

```javascript
sh.enableSharding("hotspot_lab");

sh.shardCollection(
  "hotspot_lab.events_range",
  { createdAt: 1 }
);

sh.shardCollection(
  "hotspot_lab.events_hashed",
  { eventId: "hashed" }
);
```

In certain MongoDB versions, `sh.enableSharding` is optional or behaves differently; check responses and sharding state for your version.

- Range collection: shard key `createdAt`, monotonically increasing with time.
- Hashed collection: shard key `eventId`, spreads better when IDs are diverse.

**Important note on initial layout:** an empty range-sharded collection may start with one large range; hashed sharding may apply pre-splits/initial distribution depending on shard count and zone settings. After inserting a few thousand documents, total volume may still be below balancer thresholds. Initial shard distribution in the lab may not look immediately even.

### 27.2. Never Paste Example Scripts Into a Production Shell

Even with the name `hotspot_lab`, always double-check cluster URI and permissions. Creating, sharding, or dropping collections modifies metadata and consumes resources.

---

## 28. Lab: Seeding Data and Observing a Write Hotspot

In `mongosh` connected to `mongos`:

```javascript
const lab = db.getSiblingDB("hotspot_lab");
const startMs = Date.parse("2026-11-14T00:00:00Z");

for (let base = 0; base < 4000; base += 200) {
  const docs = [];

  for (let i = base; i < base + 200; i++) {
    docs.push({
      _id: "id-" + i,
      eventId: "event-" + i,
      tenantId: i % 10 === 0 ? "B" : "A",
      status: i % 20 === 0 ? "FAILED" : "OK",
      createdAt: new Date(startMs + i * 1000),
      value: i % 100
    });
  }

  lab.events_range.insertMany(docs);

  lab.events_hashed.insertMany(
    docs.map(x => ({ ...x }))
  );
}
```

This inserts **4,000 documents per collection**, with increasing `createdAt`, distinct `eventId`, tenant A receiving about 90% of documents, and status `FAILED` accounting for roughly 5%.

### 28.1. Compare Counts

```javascript
lab.events_range.countDocuments({});
lab.events_hashed.countDocuments({});
// Both ~4000 documents if inserts succeeded.
```

### 28.2. Inspect Shard Key Metadata

```javascript
sh.status(true);
```

Confirm `hotspot_lab.events_range` uses `{createdAt:1}` and `events_hashed` uses `{eventId:"hashed"}`.

### 28.3. Inspect Data Distribution

```javascript
sh.getShardedDataDistribution()
  .filter(x =>
    x.ns === "hotspot_lab.events_range" ||
    x.ns === "hotspot_lab.events_hashed"
  );
```

Do not expect exact 33/33/34 or 50/50 splits: lab volume is below balancing thresholds and initial placement varies; this is an **observational lab**, not a full-scale hotspot benchmark.

### 28.4. Why Not Insert Millions of Writes Here?

Generating massive write load on a shared cluster creates resource contention, cost, replication lag, and disruption for other teams. For real load testing, provision a dedicated performance environment with approved load generators, cleanup plans, and cost budgets.

---

## 29. Lab: Targeted and Scatter-Gather Queries on the Hashed Collection

### 29.1. Equality Query with Shard Key

```javascript
const lab = db.getSiblingDB("hotspot_lab");

lab.events_hashed
  .find({ eventId: "event-42" })
  .explain("executionStats");
```

With `{eventId:"hashed"}`, equality on that field normally targets a single shard.

### 29.2. Query Missing the Shard Key

```javascript
lab.events_hashed
  .find({ status: "FAILED" })
  .limit(20)
  .explain("executionStats");
```

Filtering on `status` gives `mongos` no way to compute the `eventId` hash, so it usually broadcasts. Check fan-out even if a `status` index exists.

### 29.3. Range Query on the Original Hashed Field

```javascript
lab.events_hashed
  .find({
    eventId: {
      $gte: "event-100",
      $lt: "event-200"
    }
  })
  .explain("executionStats");
```

A hashed key does not preserve lexicographic/range ordering of original values. Range queries on it typically cannot prune shards effectively.

### 29.4. Time-Range Query on the Range-Sharded Collection

```javascript
lab.events_range
  .find({
    createdAt: {
      $gte: ISODate("2026-11-14T00:10:00Z"),
      $lt: ISODate("2026-11-14T00:20:00Z")
    }
  })
  .explain("executionStats");
```

A range key can prune to a subset of ranges/shards, though with small layouts or ranges spanning shards it may still touch multiple shards.

### 29.5. Experiment Report Table

| Query | Shard key | Prediction | Actual observation |
| --- | --- | --- | --- |
| `eventId = event-42` | Hashed `eventId` | Targeted | Fill in from Explain |
| `status = FAILED` | Hashed `eventId` | Scatter | Fill in from Explain |
| `eventId` range | Hashed `eventId` | Scatter/little pruning | Fill in from Explain |
| `createdAt` range | Ranged `createdAt` | Can prune | Fill in from Explain |
| `tenantId = A` | Ranged `createdAt` | Scatter | Fill in from Explain |

Never rely on one latency reading; compare shards targeted, docs examined, keys examined, sort/merge stages, and network traffic.

---

## 30. Lab: Evaluating Candidate Shard Keys with Analyzer

In a **7.0+ test cluster with appropriate privileges**, enable query sampling on a collection:

```javascript
const events = db.getSiblingDB("hotspot_lab").events_hashed;

events.configureQueryAnalyzer({
  mode: "full",
  samplesPerSecond: 1
});
```

Generate a small lab workload:

```javascript
for (let i = 0; i < 100; i++) {
  events.findOne({ eventId: "event-" + (i % 80) });
  events.find({ tenantId: "A", status: "FAILED" })
    .limit(5).toArray();
}
```

Then inspect the report:

```javascript
printjson(
  events.analyzeShardKey({ eventId: "hashed" })
);
```

With sufficient samples and a supported version, the report contains key characteristics and read/write distributions. If distribution fields are absent, check sampling config, query count, privileges, topology, and sampling limitations.

**Turn off sampling afterward:**

```javascript
events.configureQueryAnalyzer({ mode: "off" });
```

### 30.1. Another Candidate Key

Evaluate an additional candidate on the test collection under compatible settings:

```javascript
events.analyzeShardKey({ tenantId: 1 });
```

Output will highlight that heavy tenant A has very high frequency.

Never base a final production decision on a tiny sample alone: evaluate peak traffic, batch imports, long-running reports, and future growth projections.

---

## 31. Lab: Distinguishing Data Skew from Workload Skew

An illustrative simulation:

```text
Data distribution:
  Shard A: 2.0 GB
  Shard B: 2.1 GB
  Shard C: 1.9 GB

Write throughput:
  Shard A: 800 ops/s
  Shard B: 120 ops/s
  Shard C:  80 ops/s
```

### Questions

1. Are data bytes significantly skewed?
2. Is write distribution skewed?
3. Will the balancer necessarily fix the write skew?
4. Which key characteristics and query shapes must you examine?

**Guided answer:** bytes are nearly balanced, while writes concentrate on A. The balancer moves data ranges according to thresholds; it cannot split a single hot shard-key value just by migrating ranges. Inspect key frequency/monotonicity and candidate keys.

### 31.1. Do Not Blame Sharding Simply Because CPU Is High

High CPU on A can also stem from:

- A standalone heavy aggregation.
- An index build or checkpoint.
- Secondary replication or recovery work.
- TTL cleanup.
- Orphan range deletion.
- A stuck transaction or application retry storm.
- Unsharded collections residing on primary shard A.

Cross-check ops/s, namespace activity, logs, migrations, and query profiler data before declaring the shard key guilty.

---

## 32. Scatter-Gather and the Slowest Shard

Suppose a request scatters across three shards:

```text
Shard A: 15ms
Shard B: 210ms  <-- hot from writes
Shard C: 18ms
Merge/network overhead: ...
```

Client latency is heavily governed by shard B (the slowest leg in the fan-out) plus merge and network costs. You cannot estimate it by averaging `(15+210+18)/3`.

### 32.1. Adding Shards Can Increase Fan-Out

If a query still broadcasts cluster-wide, adding shards increases the participant count even if each shard stores fewer bytes. End latency can get better or worse depending on parallelism, network, merge overhead, indexes, skew, and load. **Never claim more shards always make scatter queries slower**; always measure.

### 32.2. Per-Shard Indexes Matter

When scatter is a valid business need (global analytics), optimize local filters, projections, aggregation pipelines, and merge costs. Measure:
- `docsExamined` per shard.
- `keysExamined` per shard.
- Returned candidates per shard.
- Sort/merge stages.
- CPU/cache/network.
- p95/p99 and error rates.

### 32.3. Never Run Unbounded Counts in Production

A global `countDocuments({})` or unfiltered aggregation can hit every shard and burn heavy resources. For periodic dashboards, use precomputed counters or an analytics pipeline suited to the use case.

---

## 33. Runbook Remediation by Root Cause

| Evidence | Likely cause | Short-term action | Long-term action |
| --- | --- | --- | --- |
| 90% inserts hit newest range | Monotonic ranged key | Throttle imports, smooth bursts | Reshard / compound hashed candidate |
| 80% writes from one `tenantId` | Heavy hitter | Per-tenant rate limit | Partition within-tenant with a new key |
| Equal chunk counts, skewed bytes | Uneven range density | Check migration thresholds/zones | Refine/reshard if necessary |
| Balancer off, skew growing | Balancer disabled | Check maintenance/change owner | Re-enable per policy, monitor |
| Balancer on, jumbo warnings | Indivisible range | Check logs/range sizes | Refine/reshard; Support |
| APAC zone hot | Residency + traffic skew | Scale capacity inside zone | Zone/key/capacity design |
| API query missing shard key | Scatter-gather | Local index optimization, caching | Query rewrite / read model |
| Per-shard `IXSCAN`, still high p99 | Fan-out + slowest shard | Throttle + isolate workloads | Targeting / data modeling |
| Added shard, data hasn't moved | Threshold/placement | Watch balancer progress | Same-key redistribute if 8.0-eligible |
| Unsharded collection hot on primary shard | Unsharded data | Check jobs/resources | Shard collection with an appropriate key |
| Sudden lag during migration | Data copy/replication load | Throttle competing batches | Migration scheduling/capacity |

**Not every action in this table should be executed mid-incident.** Any change impacting metadata, shard keys, or data placement requires change approval, backup/restore planning, canary/benchmarking, and clear ownership.

---

## 34. Choosing a Candidate Shard Key: Scorecard

Suppose an event ingestion application has:

```text
80% operations: insert events
15% operations: find event by eventId
 5% operations: tenant time-range analytics
```

Three candidates:

| Candidate | Write distribution | Point lookup | Tenant time range | Risk |
| --- | --- | --- | --- | --- |
| `{createdAt:1}` | Monotonic hotspot | Usually scatter | Can target by time | Hot tail |
| `{eventId:"hashed"}` | Usually well distributed | Targeted equality | Usually scatter | Analytics fan-out |
| `{tenantId:1,eventId:"hashed"}` | Can split a hot tenant | Targeted on full key | Fan-out within tenant | Key complexity |

Never decide from operation percentages alone; factor in bytes/IO per operation, SLOs, and business consistency requirements.

### 34.1. The Heavy-Tenant Problem

If tenant A generates 80% of traffic, hashing `tenantId` alone still fails to split that single tenant. A compound key with a high-dispersion suffix can help, at the cost of per-tenant queries hitting multiple shards. Measure your real workload.

### 34.2. Constraints to Respect

- Indexes/unique constraints: MongoDB sharded collections enforce strict rules on unique indexes and shard-key prefixes.
- Transactions and shard-key updates carry restrictions and overhead.
- Legacy documents might lack candidate shard-key fields.
- Query patterns and pagination must match suitable sort/filter fields.
- Zone ranges impose business/compliance placement rules.
- Resharding requires adequate storage, compute, network, and healthy oplog/replication.

---

## 35. When to Reshard vs. When Not To

**Consider resharding** when:

- A hot key/range is proven to drive p95/p99 regressions.
- The balancer cannot resolve it due to cardinality/frequency limits.
- Core queries routinely scatter due to a mismatched key.
- A candidate key has been validated through sampling and benchmarks.
- Resources exist to execute, monitor, and roll back the migration.

**Do NOT reshard** merely because:

- Chunk counts look unequal.
- CPU spiked for 30 seconds on one graph.
- A small collection isn't evenly split right after `shardCollection`.
- An analytics scatter query runs a few times daily within SLO.
- Zone compliance intentionally leaves bytes uneven.
- No baseline, sampling, load tests, or migration plan exist yet.

### 35.1. Risk Profile of `reshardCollection`

Resharding alters data placement and the shard key, drives heavy read/write volume, and enters a commit phase. Certain phases cannot be aborted once commit starts, per MongoDB docs.

Your plan must cover:

1. MongoDB version/prerequisites.
2. Current key, candidate key, and indexes.
3. Data size and bandwidth/storage headroom.
4. Business SLOs/maintenance window.
5. Migration observability and progress tracking.
6. Concurrent write handling.
7. Phased rollback/backout strategy.
8. Contingency if commit/migration fails.
9. Before/after benchmarks.
10. Owner, on-call coverage, and approval.

Never portray `reshardCollection` as a harmless "copy-paste one command and you're done" action.

---

## 36. Minimum Dashboard for a Sharded Cluster

### 36.1. Workload Per Shard

| Metric | Why? |
| --- | --- |
| Insert/update/delete ops/s | Spot write hotspots |
| Read ops/s | Spot read hotspots |
| CPU per primary | Compute saturation |
| Disk read/write IOPS, latency | Storage bottlenecks |
| WiredTiger cache used/dirty/evictions | Working set and eviction pressure |
| Network in/out | Scatter results, replication, migrations |
| Connection count | Driver/pool fan-out |
| Replication lag | Write/migration pressure |

### 36.2. Sharding Metadata

| Metric | Why? |
| --- | --- |
| Owned docs/bytes per collection per shard | Data skew |
| Number of ranges/chunks | Placement granularity |
| Orphaned docs | Migration cleanup health |
| Balancer status/migrations | Data movement |
| Jumbo/indivisible ranges | Cannot split/move normally |
| Zone assignments | Data residency/allowed placement |
| Scatter/targeted query proportions | Routing efficiency |
| Shard Key Analyzer read/write distribution | Key design verification |

### 36.3. Application Metrics

| Metric | Why? |
| --- | --- |
| API p50/p95/p99 | User SLO |
| Throughput/RPS | Load level |
| Errors/timeouts/retries | Availability |
| Driver pool checkout waits | Client-side bottlenecks |
| Query shapes/command durations | Identify top costly queries |
| Tenant/region/endpoint breakdown | Hot tenants, regional skew |
| Deployment/batch markers | Correlate changes |

### 36.4. Keep Timestamps Consistent

Record events in UTC, synchronize clocks with NTP, and mind chart granularity/sampling. A 1-minute spike can vanish on hourly-averaged charts.

---

## 37. Security and Stability While Troubleshooting

- Use least-privilege monitoring accounts; keep admin/Analyzer commands in dedicated roles.
- Never log raw query literals containing tenant IDs or PII onto shared dashboards.
- Never share full Atlas URIs with embedded credentials.
- Never connect directly to shards to bypass routing.
- Never manually edit `config` metadata.
- Never leave high-volume profiling or sampling running indefinitely.
- Never force `moveChunk`/`forceJumbo` without a runbook due to write-blocking risk.
- Never delete orphaned documents via application queries.
- Never risk calling `drop()` or `sh.shardCollection()` on a production database via typos.
- Cap duration, sample rate, and query volume when benchmarking.
- Define timeouts, rollback policies, and clear ownership for every change.

**Principle:** start investigations with **read-only metrics**, and apply configuration changes only after gathering evidence and approval.

---

## 38. Common False Conclusions

| False claim | Reality |
| --- | --- |
| "Once sharded, writes balance automatically." | The shard key can still cause hotspots. |
| "Equal data bytes mean no hot shard." | Workload skew differs from data skew. |
| "High CPU on one shard must be the shard key." | Could be index builds, jobs, TTL, or migrations. |
| "Equal chunk counts mean equal data." | Chunk sizes/densities vary. |
| "The balancer evens out writes/s." | The balancer mainly migrates data ranges. |
| "If the balancer is on, data skew can't happen." | Thresholds, zones, jumbo chunks, or failures still apply. |
| "Hashing `tenantId` spreads a hot tenant." | One value hashes to one value on one shard. |
| "High cardinality guarantees a good shard key." | It can still be monotonic. |
| "Refining a key immediately spreads all data." | Does not guarantee immediate redistribution. |
| "Adding a shard fixes any hot key." | A single hot key still hits one shard. |
| "Same-key redistribution fixes high-frequency keys." | Does not change key cardinality. |
| "Having a `status` index targets `status` queries." | `mongos` routes using the shard key. |
| "Good shard indexes eliminate scatter-gather." | Routing and local indexing are separate steps. |
| "`_id` lookups are always targeted." | Not unless `_id` is an eligible shard key/prefix. |
| "Prefix filters always hit one shard." | A prefix can span multiple shards. |
| "Hashed shard keys handle all range queries well." | Hashing sacrifices range locality. |
| "Scatter queries are always wrong." | Analytics can deliberately broadcast. |
| "Scatter latency equals the average across shards." | Slowest shard plus merge overhead dominate. |
| "Adding shards always lowers p99." | Fan-out overhead and skew can raise latency. |
| "One Explain proves production p99." | Real workload metrics are required. |
| "Index hints fix routing issues." | Hints affect local plans, not shard-key targeting. |
| "See jumbo, run `forceJumbo` right away." | Can block writes for a long period. |
| "Zone imbalance is always a bug." | May reflect data-residency compliance policies. |
| "Standalone `mongosh` proves routing." | Requires `mongos` on a sharded cluster. |
| "MongoDB 8.0 allows all commands directly on shards." | Certain direct shard commands are blocked. |
| "Shard key changes don't affect applications." | Query predicates, indexes, and transaction semantics change. |
| "Reshard can always roll back cleanly." | Commit-phase constraints apply. |
| "Orphan documents mean corruption." | May simply be pending post-migration cleanup. |
| "Query sampling is always representative." | Requires enough samples in the right time window. |

---

## 39. Practice Exercises

### Exercise 1 — Classify the Symptom

Data bytes are 34/33/33 while writes are 87/8/5. Is this data skew or workload skew?

**Answer:** Write workload skew; data volume is relatively even.

### Exercise 2 — Connecting to `mongos`

Which command verifies the client is connected to `mongos`? What `msg` value should appear?

**Answer:** `db.adminCommand({hello:1})`, `msg: "isdbgrid"`.

### Exercise 3 — Chunks vs. Data

Why don't 100 chunks per shard guarantee equal bytes?

### Exercise 4 — Owned vs. Orphaned

Distinguish `numOwnedDocuments` from `numOrphanedDocs`. Why shouldn't you delete orphans manually?

### Exercise 5 — Sharded Data Distribution

Write the `$shardedDataDistribution` command on the `admin` DB filtering namespace `commerce.orders`.

### Exercise 6 — Write Hotspot

What risk does a continuously increasing `{createdAt:1}` shard key pose?

**Answer:** Writes hit the hot tail range, usually concentrating on a single shard at any time.

### Exercise 7 — Cardinality

Why is a shard key with only four status values a poor candidate?

### Exercise 8 — Frequency

1,000 tenants exist, yet one tenant generates 80% of writes. Why is cardinality 1,000 not enough?

### Exercise 9 — Hashed Tenant

Does `{tenantId:"hashed"}` split writes from one tenant A across all shards?

**Answer:** No; a single `tenantId` still hashes to one value.

### Exercise 10 — Hashed `eventId`

If `eventId` values are unique and diverse, what are the pros and cons of a hashed key for time-range reports?

### Exercise 11 — Scatter-Gather

With shard key `{eventId:"hashed"}`, how does `{status:"FAILED"}` usually route?

**Answer:** Broadcast/scatter because the shard key is absent.

### Exercise 12 — Indexes Aren't Enough

Does adding `{status:1}` on every shard make `status` queries targeted?

**Answer:** No; it only speeds up execution inside each shard.

### Exercise 13 — Compound Prefix

With `{tenantId:1,orderId:1}`, can a filter on `orderId` alone target a shard?

### Exercise 14 — Full Equality

With `{tenantId:1,orderId:1}`, what does filtering on both fields usually achieve?

### Exercise 15 — Prefix

Does a query filtering only on `tenantId` guarantee reaching just one shard?

**Answer:** No; it may target a subset of shards.

### Exercise 16 — Hashed Range

Why can `{eventId:{$gte:"evt-10",$lt:"evt-50"}}` scatter on a hashed shard key?

### Exercise 17 — Explain

In Explain output from `mongos`, what should you inspect to distinguish targeted vs. broadcast queries?

### Exercise 18 — Aggregation

When is scatter-gather an intentional and reasonable choice?

### Exercise 19 — Slowest Shard

A scatter hits A=12ms, B=220ms, C=15ms. Why isn't client latency equal to the mean?

### Exercise 20 — Balancer

Does the balancer equalize data or CPU/writes per second?

**Answer:** It balances data ranges by policy/threshold, not ops/s directly.

### Exercise 21 — Balancer Threshold

With a default 128 MB range size and roughly a 3× imbalance threshold, explain why a 100 MB difference may not trigger migration yet.

### Exercise 22 — Jumbo

A hot tenant has millions of docs sharing one shard-key value. Why can its chunk become indivisible?

### Exercise 23 — ForceJumbo

What is the main risk of forcing migration of an oversized/jumbo range?

### Exercise 24 — Zones

Why isn't having 70% of data in APAC shards necessarily a balancer bug?

### Exercise 25 — Refine

What differs between `{tenantId:1}` and refined `{tenantId:1,eventId:1}`? What does not happen automatically?

### Exercise 26 — Reshard

When is `reshardCollection` more appropriate than `refineCollectionShardKey`?

### Exercise 27 — Same-Key Redistribution

What case does MongoDB 8.0 `forceRedistribution:true` address, and what does it **not** fix?

### Exercise 28 — Query Analyzer

Write commands to enable sampling at 1 sample/s, analyze a shard key, and disable sampling.

### Exercise 29 — Sampling Bias

Why don't 200 off-peak samples prove a key will hold up during a campaign peak?

### Exercise 30 — Data vs. Workload

One shard has the most bytes yet low CPU, while another has fewer bytes and high CPU. What do you measure next?

### Exercise 31 — MongoDB Java Driver

Write a Java equality query on `eventId` and a `status`-only query; compare routing under a hashed `eventId` shard key.

### Exercise 32 — Spring Data

With key `{tenantId:1,eventId:"hashed"}`, write a repository method providing both fields and contrast it with `findByStatus`.

### Exercise 33 — Security

Why must you never let clients pass arbitrary `tenantId` values solely to achieve targeted queries?

### Exercise 34 — Unsharded Collection

A database belongs to a sharded cluster, yet a collection is unsharded; does it automatically spread across all shards?

### Exercise 35 — Migration Logging

What signs indicate stuck range migrations? Which logs and metrics should you inspect?

### Exercise 36 — Capacity

What does adding a shard help with, and why might it fail to help a single-key hotspot?

### Exercise 37 — P99 Regression

After adding a shard, p99 of a global `status` query rises. Trace fan-out, per-shard indexes, merge work, and the slowest shard.

### Exercise 38 — Short-Term Runbook

A batch import pushes 90% of writes to the hot tail. Pick two load-shedding actions deployable without changing the shard key and list their risks.

### Exercise 39 — Index Trade-Off

How can adding many indexes for scatter queries worsen a write hotspot?

### Exercise 40 — Capstone Exercise

A large `events` collection is sharded by `{createdAt:1}`. The app has:
- 80% writes using current timestamps.
- 15% point lookups by `eventId`.
- 5% tenant time-range reports.
- Nearly balanced data sizes, yet CPU is 90/30/25.
- Several global status reports scatter.

Produce a report covering:
1. Evidence for hotspot, data distribution, and fan-out.
2. Candidate keys and trade-offs.
3. A sampling/benchmark plan.
4. Short-term load-reduction actions.
5. Long-term refine/reshard approach if warranted.
6. Migration/rollback constraints.
7. Post-rollout validation metrics.

---

## 40. Production Checklist

### Diagnostics

- [ ] Verified connection goes through `mongos`, never inferring routing directly from shards.
- [ ] Recorded namespace, shard key, shard count, and server version.
- [ ] Separated data skew from write/read workload skew.
- [ ] Collected per-shard ops/s, CPU, disk, cache, and network.
- [ ] Collected owned bytes/docs per namespace.
- [ ] Checked chunk/range counts, zones, balancer status, and orphan cleanup.
- [ ] Measured monotonicity/cardinality/frequency of the current key.
- [ ] Collected query shapes and Explain shard target counts.
- [ ] Reviewed application read/write mix and tenant distribution.
- [ ] Captured baseline p95/p99, error rates, and retries.

### Solution Selection

- [ ] Do not expect the balancer to spread writes/s automatically.
- [ ] Do not hash `tenantId` unmeasured when one tenant dominates traffic.
- [ ] Evaluated hashed/ranged/compound keys for both reads and writes.
- [ ] Collected Shard Key Analyzer samples over representative time windows.
- [ ] Do not use index hints trying to "fix" queries lacking a shard key.
- [ ] Planned targeted queries or intentional analytics scatter strategies.
- [ ] Accounted for unique indexes, transactions, zones, and data residency.
- [ ] Checked jumbo/indivisible ranges before considering manual migrations.
- [ ] Proceed with refine/reshard only after benchmarking and change approval.

### Rollout and Operations

- [ ] Checked MongoDB/Atlas version compatibility and feature prerequisites.
- [ ] Prepared backups and phased rollback/backout plans.
- [ ] Provisioned resource headroom for migrations/resharding.
- [ ] Set up migration progress, replication lag, and disk-space monitoring.
- [ ] Assigned owner, on-call rotation, incident timeline, and change ticket.
- [ ] Never edit `config` metadata directly.
- [ ] Never run `forceJumbo` or modify zones without an approved runbook.
- [ ] Never leave sampling/profiling enabled indefinitely.
- [ ] Captured before/after per-shard metrics and API p95/p99.
- [ ] Measured impact across writes, reads, query routing, cache, and network.

---

## 41. Summary

When a sharded MongoDB cluster is still slow, never default to "we need more shards." Separate these distinct issues:

1. **Write hotspot:** one shard-key value or range absorbs most writes. Common root causes are low cardinality, high key frequency, or monotonic growth.
2. **Data skew:** owned data/ranges differ sharply across shards; inspect `$shardedDataDistribution`, `sh.status(true)`, and balancer/zones/jumbo state.
3. **Scatter-gather:** filters omit enough of the shard key for `mongos` to target; local indexes speed up per-shard execution without reducing fan-out.
4. **The balancer equalizes data by thresholds**, not live writes/s across shards.
5. **Hashed sharding** relieves monotonic hotspots, yet impairs time-range pruning; hashing `tenantId` **does not split a single heavy tenant**.
6. **Refine/reshard** can fix flawed key designs, but requires sampled workload analysis, index compliance, migration capacity, and rollback planning.
7. **Java/Spring Data** code must pass authorized shard-key predicates where feasible; repository method names alone do not guarantee targeted routing.
8. **Base conclusions on three pillars of proof:** per-shard distribution, Explain/routing behavior, and end-to-end workload metrics.
9. **Diagnose first, shed load safely, change structure last** is the safest sequence for production incidents.

The core question is always:

> **"Does the bottleneck lie in data placement, operation distribution, or the number of shards each query touches—and does the shard key match the real workload?"**

### Official MongoDB Documentation

- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — `mongos`, shards, config servers, ranged/hashed sharding.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, monotonicity, query patterns.
- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — hot keys, jumbo chunks, poor distribution.
- [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — targeted queries, broadcast/scatter-gather, aggregation merges.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — ranges, migrations, indivisible chunks.
- [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — migration thresholds, balancing policies.
- [Manage Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — supported administration options.
- [Troubleshoot Stuck Chunk Migrations](https://www.mongodb.com/docs/manual/troubleshooting/chunk-migrations-stuck/) — balancer and jumbo diagnostics.
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — cluster metadata, chunk placement.
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — owned/orphaned documents and bytes.
- [$shardedDataDistribution](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shardeddatadistribution/) — distribution output from `mongos` admin.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hashed keys and range query trade-offs.
- [analyzeShardKey](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/) — shard key characteristics and read/write distribution.
- [configureQueryAnalyzer](https://www.mongodb.com/docs/manual/reference/command/configurequeryanalyzer/) — query sampling.
- [refineCollectionShardKey](https://www.mongodb.com/docs/manual/reference/command/refineCollectionShardKey/) — extend shard key prefix.
- [reshardCollection](https://www.mongodb.com/docs/manual/reference/command/reshardcollection/) — change/redistribute shard key ranges.
- [Atlas Sharding Insights](https://www.mongodb.com/docs/atlas/sharding-advisor/) — per-shard metrics, distribution, and balancer.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution statistics.
- [Spring Data MongoDB Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived queries, `@Query`.
