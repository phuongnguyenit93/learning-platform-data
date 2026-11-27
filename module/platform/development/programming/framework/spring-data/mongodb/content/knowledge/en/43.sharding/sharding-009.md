# Identifying Concentrated Shard Load (Hot Shards) and Verifying with Metrics

## 1. Context and objectives

In systems built with **Spring Data MongoDB**, applications typically access MongoDB via `MongoTemplate` or repositories. As data grows, a collection can be **sharded** to distribute data and request processing across multiple shards. However, having more shards does not guarantee load is distributed evenly.

A **hot shard** is a shard receiving or processing an unusually high share of work compared to other shards in the same measurement window, causing resource saturation or latency spikes. A **hot chunk/range** is a shard key range attracting concentrated access; it can be the root cause making the shard holding it run hot. This phenomenon can happen even when storage size and document counts are fairly balanced.

This lesson focuses on four skills:

1. Distinguishing **data** imbalance from **traffic and processing cost** imbalance.
2. Gathering reliable measurements to confirm which shard is hot, during which window, and from which operations.
3. Using query routing, shard key analysis, and Spring Data MongoDB application metrics to trace the cause.
4. Validating remediation measures with before/after measurements under comparable workloads.

> Scope: examples use a three-shard sharded cluster, each shard a replica set, with a Java/Spring Data MongoDB application connecting through `mongos`. Shard names, databases, and numbers below are illustrative only.

## 2. What does a hot shard look like?

Consider `shop.orders` receiving many new orders. If using a ranged shard key `{ createdAt: 1 }`, orders with continuously increasing timestamps typically land in the upper end of the key range. One chunk can absorb most new writes at any moment; the shard holding that chunk easily becomes a hot shard. If screens also mostly read recent orders, read load can concentrate on that same shard.

Types of imbalance to distinguish:

| Phenomenon | Signal | Meaning |
|---|---|---|
| **Data skew** | One shard holds substantially more documents/bytes | Uneven storage distribution; not yet proof of high load |
| **Workload skew / hot shard** | One shard has higher ops/s, CPU, I/O, queues, or latency than the rest | Concentrated execution load; identify the query shapes and shard keys causing it |
| **Hot chunk / hot range** | One shard key range receives most requests in a time window | Potential cause of a hot shard; moving chunks may only relocate the hotspot |
| **Scatter-gather** | Single query hits many or all shards | Can exhaust cluster-wide resources; does not imply only one shard is hot |
| **Hardware bottleneck or shard-specific issue** | One shard is slow despite roughly equal request volume | Could be disk, memory, cache, replica set health, indexes, or background tasks |

A shard holding 40% of data in a three-shard cluster is not necessarily a hot shard. Conversely, a shard with 33% of data yet processing 80% of writes with CPU pinned above 90% shows much stronger evidence of concentrated load. Final conclusions must examine **access intensity, resource utilization, and latency impact simultaneously**.

### Common root causes

- **Monotonically increasing shard key** (timestamp, sequence, auto-increment ID) with range sharding, concentrating new writes.
- **Low-cardinality or skewed key distribution**, such as order status or one oversized tenant; many operations hit a single key domain.
- **Access biased toward recent data**: historical data is evenly distributed, yet most requests read only a narrow recent window.
- **Uniform query or update shapes** hitting one shard even when the rest of the workload is evenly spread.
- **Oversized/indivisible chunks, data migrations, balancer activity, or background jobs** temporarily skewing observations.
- **Differences in shard capacity** (CPU, disk, replica set resources, indexes, cache) causing different latencies at identical ops/s.

Note: a hashed shard key does not automatically solve all hot shards. If most traffic belongs to **one tenant** and you hash solely by `tenantId`, operations for that tenant can still concentrate on one key spot.

## 3. Designing measurements: right scope, right time window

Start with a fixed observation window—such as **15 minutes**—sampling every 30–60 seconds and comparing against the same hour on a normal day. Include both peak and off-peak windows. Record shard count, hardware specs, topology, MongoDB version, read preference, collection scope, and time range.

| Observation layer | Metrics / signals | Common sources | Pitfalls to avoid |
|---|---|---|---|
| Storage distribution | Docs, bytes, chunks/ranges per shard | `getShardDistribution()`, `sh.getShardedDataDistribution()` | Reflects storage, **not** directly QPS |
| Operation rate | Reads/s, writes/s, insert/update/delete, command, getMore | Shard monitoring, `serverStatus`, logs/profiler | `mongod` counters are **instance-wide**, not automatically scoped to one collection |
| Resource utilization | CPU, disk IOPS/latency, network, WiredTiger cache, connection pressure | Atlas/Prometheus/host metrics | High CPU can also come from migrations or index builds |
| Latency | p50/p95/p99 by query shape, errors/timeouts, `docsExamined` | Tracing/Micrometer, slow query logs, profiler, `explain` | System-wide p95 does not identify which shard caused slowness |
| Routing | Targeted shard count, scatter-gather, distribution across shard-key ranges | `explain("executionStats")`, `analyzeShardKey`, `mongos` metrics | "Targets one shard" is good, yet **the same single shard** taking nearly all traffic can still run hot |
| Background tasks | Migrations, elections, balancer, compaction, backups, index builds | Telemetry and ops logs | Annotate timestamps so you do not misattribute causes |

For fair comparisons:

- Measure the same time window across **primaries** when comparing write load. If reading from secondaries, measure the serving secondaries and separate reads from writes.
- Normalize metrics into **ops/second** from counter deltas; verify whether counters reset due to restarts or failovers.
- If shards differ in hardware specs, compare both raw load **and** capacity utilization; high raw QPS does not automatically mean overload.
- Break down by **collection and query shape** whenever possible. Shard-wide host metrics are for screening; profiler/tracing/query sampling pinpoint `orders`.
- Analyze latency per endpoint/query shape and comparable result size; never average p95 values across shards to compute a cluster-wide p95.

## 4. Reading sample metrics and calculating skew

Suppose these numbers are aggregated specifically for **`shop.orders`** during peak hours. Operation rates come from log/profiler sampling and timed deltas; CPU is taken from each shard's primary.

| Metric | shard-a | shard-b | shard-c |
|---|---:|---:|---:|
| Document count (millions) | 3.4 | 3.2 | 3.3 |
| Writes/sec | **950** | 120 | 130 |
| Reads/sec | **730** | 180 | 190 |
| Average primary CPU | **91%** | 32% | 36% |
| p95 of queries routed to shard (ms) | **240** | 29 | 35 |

Total writes are `950 + 120 + 130 = 1,200` ops/second. With `N = 3` shards, even load would put roughly `1/3 = 33.3%` of writes on each shard. In this example:

```text
writeShare(shard-a) = 950 / 1200 × 100% = 79.2%
hotFactor          = 79.2% / 33.3% ≈ 2.38x equal-distribution share
max/min write rate = 950 / 120 ≈ 7.92
```

You can apply the general formulas:

\[
\operatorname{share}_i=\frac{\operatorname{ops}_i}{\sum_{j=1}^{N}\operatorname{ops}_j},\qquad
\operatorname{hotFactor}=N\cdot\max_i(\operatorname{share}_i)
\]

**Assessment:** storage is nearly even (roughly 32–34% per shard), yet shard-a handles nearly 80% of writes and suffers spiked CPU and p95. This is **solid evidence to investigate a hot shard**, especially if sustained across multiple windows and rising alongside new traffic. You must still prove which operations drive the load and rule out shard-local resource faults.

There is no universal threshold like "above 60% is broken." Alert thresholds depend on baselines, expected skew, latency SLOs, and shard capacity. For example, trigger an investigation alert when one shard exceeds **2x its equal share of writes for three consecutive windows** while CPU or p95 breaches internal thresholds. That is an operational example, not a MongoDB rule.

## 5. Investigation workflow on a real cluster

### Step 1 — Confirm topology and data distribution

Use `mongosh` connected to **`mongos`**, select the right database/collection, and run:

```javascript
// Run on mongos of the sharded cluster.
sh.status();

const orders = db.getSiblingDB("shop").orders;
orders.getShardDistribution();

// MongoDB >= 6.0.3, run from mongos to view full distribution.
// Subject to permissions and deployment version:
sh.getShardedDataDistribution();
```

Inspect the current shard key, participating shards, docs/bytes/chunks, and size skew. `getShardDistribution()` is a `mongosh` shell helper, **not** a Spring Data API. Some small clusters or managed tiers impose restrictions on these commands.

Even data distribution alongside uneven performance signals a shift from checking **storage** distribution to checking **workload** distribution. If storage is heavily skewed, note it, but do not conclude root cause from storage numbers alone.

### Step 2 — Compare operations on each shard

Connect to the **primary of each shard** (rather than only `mongos`) to read `serverStatus`. Quick sampling script for **one primary**, then repeat on the remaining primaries over comparable windows:

```javascript
// In mongosh connected to a shard's primary.
// Use for short observations; does not isolate a single collection.
const t0 = Date.now();
const before = db.getSiblingDB("admin").serverStatus().opcounters;

sleep(60_000);

const t1 = Date.now();
const after = db.getSiblingDB("admin").serverStatus().opcounters;
const seconds = (t1 - t0) / 1000;

function perSecond(name) {
  return (Number(after[name]) - Number(before[name])) / seconds;
}

printjson({
  insertPerSecond: perSecond("insert"),
  updatePerSecond: perSecond("update"),
  deletePerSecond: perSecond("delete"),
  queryPerSecond: perSecond("query")
});
```

`opcounters` accumulate since `mongod` startup; field names can vary across versions. Discard samples if values go negative, a failover/restart occurred, or the interval is invalid. The `query` counter does not capture all read traffic; `getMore` and aggregations must also be checked per version and workload. This is an **instance-level load screen**: do not claim "`orders` receives X writes/s" solely from `opcounters` if the shard also hosts other collections.

In real operations, prefer time-series monitoring dashboards per shard correlated with slow query logs/profiler, tracing, or query samples for `shop.orders`. Inspect network, disk IOPS/latency, CPU, cache, replication lag, and migration/election events in the same window.

### Step 3 — Inspect how actual queries are routed

On `mongos`, analyze the **exact query shapes** sent by the application:

```javascript
use shop

db.orders.find({
  tenantId: "tenant-A",
  createdAt: {
    $gte: ISODate("2026-11-20T00:00:00Z"),
    $lt: ISODate("2026-11-21T00:00:00Z")
  }
}).explain("executionStats");
```

Check which shards were targeted and stats such as `totalKeysExamined`, `totalDocsExamined`, `nReturned`, execution time, and per-shard plans (`explain` structures vary across versions and query types). Answer:

1. Does the query run on a single shard or hit multiple shards?
2. Do hot queries repeatedly hit the **same shard**, or rotate across shard key values?
3. Does the query use an appropriate index, and is the `docsExamined / nReturned` ratio reasonable?
4. Are `sort`, `aggregate`, `getMore`, or multi-document updates forcing one shard to do extra work?

`explain("executionStats")` actually executes the query to gather stats; use bounded filters in appropriate environments and avoid running heavy explains carelessly in production.

### Step 4 — Analyze the shard key using query sampling (MongoDB 7.0+)

MongoDB 7.0 and later support query sampling and `analyzeShardKey`. In a test environment with proper permissions, enable low-rate sampling over a representative window:

```javascript
// Run on mongos; adjust namespace and sample rate for your workload.
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "full",
  samplesPerSecond: 5
});

// After the system collects a representative sample window:
db.getSiblingDB("shop").orders.analyzeShardKey(
  { createdAt: 1 },
  {
    keyCharacteristics: true,
    readWriteDistribution: true
  }
);

// End the measurement session in a lab environment:
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "off"
});
```

In production, check `oldConfiguration` before modifying settings and **restore the existing sampling configuration** afterward; never turn off sampling that operations already relies on. Sampling creates extra data and requires appropriate privileges. Analyzing key characteristics requires a supporting index; read/write distribution metrics are meaningful only when sampled queries are numerous enough and reflect peak hours.

Watch `readDistribution`, `writeDistribution`, `percentageOfSingleShardReads/Writes`, `percentageOfScatterGatherReads/Writes`, and `numReadsByRange` / `numWritesByRange`. Those `...ByRange` arrays reflect **how hot shard key ranges are in the sample**, not direct live ops/s per running shard. Combine them with topology and per-shard telemetry before concluding.

If 95% of operations **each** target a single shard (across different shards), routing is effective; but if nearly all sampled operations hit the **exact same key range** and the primary holding that range is overloaded, that is clear evidence of a hotspot.

### Step 5 — Correlate back to Spring Data MongoDB operations

The application may send queries using `MongoTemplate`:

```java
// mongoTemplate, from, and to are initialized in the service.
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-A")
        .and("createdAt").gte(from).lt(to)
);

List<Order> orders = mongoTemplate.find(query, Order.class);
```

Here `Order` is a `@Document(collection = "orders")` entity. Spring Data MongoDB builds queries via the Java driver; **the target shard is chosen by MongoDB based on shard key, filter, and routing metadata**, not load-balanced by `MongoTemplate`.

When you need the execution plan for an equivalent operation, use the Java driver via `MongoTemplate.execute`:

```java
Document filter = new Document("tenantId", "tenant-A")
    .append("createdAt",
        new Document("$gte", Date.from(from))
            .append("$lt", Date.from(to)));

Document plan = mongoTemplate.execute(
    "orders",
    collection -> collection.find(filter)
        .explain(ExplainVerbosity.EXECUTION_STATS)
);

System.out.println(plan.toJson());
```

Instrument at the Spring layer with Micrometer/Observability per **query shape** or operation name, such as `orders.findRecent`, then correlate timestamps against shard dashboards:

```java
Timer.Sample sample = Timer.start(meterRegistry);
try {
    return mongoTemplate.find(query, Order.class);
} finally {
    sample.stop(
        Timer.builder("mongo.orders.findRecent")
            .tag("shape", "tenantAndTimeRange")
            .register(meterRegistry)
    );
}
```

Never put `tenantId`, `orderId`, or user keys into metric tags—cardinality will explode and sensitive context may leak. To investigate large tenants, use controlled tracing/logs, cohort aggregates, or permissioned query stats. **App metrics do not automatically know which shard executed a query**: always correlate with `explain`, logs, or MongoDB monitoring.

## 6. Separating root causes with evidence

| Observation | Testable hypothesis | Next verification step |
|---|---|---|
| Storage nearly even, new writes pile onto one shard | Monotonic range key or hot range | Inspect shard key, `numWritesByRange`, write filters, key-range history |
| Large storage skew, largest shard is also busy | Skewed key distribution or resource exhaustion | `getShardDistribution()`, cardinality/frequency, CPU and I/O |
| One tenant generates most requests | Hot tenant and key cannot split that tenant's load | Break down workload by tenant/cohort; inspect routing and intra-tenant skew |
| Many shards busy, every query fans out | Scatter-gather, missing shard key component in queries | `explain`, `percentageOfScatterGatherReads`, redesign queries/indexes |
| Similar QPS yet one shard has high p95/CPU | Missing/skewed index, hardware, cache miss, disk, election/migration | Compare specs, `explain` for same query shape, logs/events |
| Spikes only appear while balancer runs | Temporary migration or background task | Mark migration windows; re-measure once steady |
| Reads only hit one slow secondary | Read preference, replica lag, or bottlenecked node | Measure secondary individually, role, lag, and connection routing |

A sound line of reasoning is: **recurring anomaly → specific shard → specific collection/query shape → specific shard key range or execution cost → measurable remediation**. If any link lacks data, record it as a hypothesis with confidence level rather than stating it as confirmed cause.

## 7. Remediation options and their limits

No single balancing command fixes every kind of hot shard. Choose remedies based on measured causes:

1. **Fix queries/indexes before changing the shard key** if `docsExamined` is high, sorts lack indexes, aggregations burn CPU, or queries scatter-gather. Better indexes cut work per request, though they do not necessarily alter how requests split across shards.
2. **Reduce repeated access pressure** via caching, pagination, concurrency limits, write batching, or throttling; apply only when consistency/freshness constraints permit, and measure impact.
3. **Re-evaluate the shard key** around cardinality, frequency, monotonicity, and read/write targeting. For monotonically increasing timestamps, a hashed key can spread writes better while making time-range queries harder to target efficiently. Benchmark the entire primary query set.
4. **For oversized tenants**, hashing `tenantId` alone still pins that tenant together. You may need an extra workload-appropriate distribution component, storage model changes, or per-tenant rate limits; verify impact on tenant queries and transactions.
5. **Moving chunks or waiting for the balancer** can balance bytes/chunks, yet if one hot chunk absorbs all new writes, moving it may simply **relocate the hotspot to another shard**. Never treat "balanced chunks" as proof the hotspot is gone.
6. **Resharding** carries major data, index, resource, and operational impact. Execute only with a validated new key, before/after baselines, rollback strategy, and an appropriate maintenance window.

Design comparison example:

| Candidate shard key | Potential upside | Risk to measure |
|---|---|---|
| `{ createdAt: 1 }` (range) | Supports routing time-range queries | Monotonic new writes easily crowd a hot range |
| `{ orderId: "hashed" }` | Usually distributes writes well when IDs are well distributed | Time-only or tenant-only queries may fan out |
| `{ tenantId: 1, createdAt: 1 }` | Tenant + time-range queries can target well | Large tenants and chronological writes can still run hot |
| `{ tenantId: "hashed", createdAt: 1 }` | Spreads multiple tenants by hash | One large tenant can still run hot; timestamp is not the shard key prefix |

The candidates in this table are **not** default recommendations. For a mixed workload, inspect critical queries, per-tenant distribution, indexes, and deployment version characteristics before deciding.

## 8. Validating changes with before/after measurements

Use the same dashboards, window lengths, and query shape groupings before and after. In staging, replay traffic matching production read/write ratios, tenant counts, key distributions, and document sizes. In production, compare equivalent hours and annotate unusual events.

Illustrative table showing a **likely improvement**:

| KPI | Before change | After change | Evaluation target |
|---|---:|---:|---|
| Max write share on a single shard | 79.2% | 38% | Closer to even split |
| Highest primary CPU | 91% | 58% | Reduced saturation risk |
| `orders.findRecent` p95 | 240 ms | 85 ms | Meets endpoint SLO |
| Error/timeout rate | 1.8% | 0.2% | Clear reduction |
| Read scatter-gather rate | 8% | 9% | No sharp increase as a side effect |
| Total throughput | 1,200 writes/s | 1,230 writes/s | Compared under equivalent load |

**Do not look only at "shard-a cooled down":** verify no new hot shard appeared, total throughput did not drop, p99 latency did not rise, fan-out did not spike, index/write costs stayed reasonable, and application consistency remained intact.

To avoid false conclusions:

- Compare **per-shard load share** alongside absolute ops/s and total throughput; naturally lower traffic drops CPU without fixing the root cause.
- Wait for data movement/catch-up to settle before recording steady state, while keeping transition-window metrics to assess risk.
- Collect enough samples for p95/p99 and isolate key query shapes; inspect reads and writes separately.
- Record MongoDB version, shard specs, read preference, indexes, and data size before/after to explain differences.

## 9. Reusable investigation report template

```text
Measurement window: 2026-11-20 09:00–09:15 UTC
Scope: shop.orders, 3 shards, identical primary specs
Symptom: orders.findRecent p95 rising, timeouts increasing
Data distribution: ~34% / 32% / 33% document count
Write distribution: 79.2% / 10.0% / 10.8% total writes/s
Resources: shard-a CPU ~91%, shard-b/c < 40%
Routing evidence: recent queries concentrate on newest createdAt range
Hypothesis: hot range on monotonically increasing createdAt shard key
Ruled out: no prolonged election/migration during measurement window
Proposed action: benchmark candidate key, measure fan-out, p95, and writeShare
Pass criteria: CPU/p95 below SLO; no new hot shard created
Confidence: high/medium/low, with dashboard and explain links attached
```

This is a **report template**, not an incident that actually happened. In practice, attach raw measurement data or dashboard links and corresponding `explain` outputs. If you only ran `getShardDistribution()` without throughput/latency metrics, the proper conclusion is *"checked data distribution; insufficient evidence to confirm a hot shard."*

## 10. Operational takeaways for Spring Data MongoDB

- The shard key governs query targeting; neither repositories nor `MongoTemplate` know how to "load-balance" across shards themselves.
- **Document distribution ≠ request distribution ≠ processing cost distribution.** You need at least three metric groups: operation rates, resources, and latency.
- Measure the right scope and compute **counter deltas over time**, rather than comparing raw cumulative counters across shards.
- A query targeting a single shard cleanly can still cause a hot shard if most traffic repeatedly hits the same shard/range.
- Validate success with **before/after baselines under identical workloads**, not merely by checking that chunks were redistributed.

### MongoDB references

- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — hot shards, hot chunks, monotonic keys, and scatter-gather queries.
- [db.collection.getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/) — sharded collection data distribution stats.
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — cluster-wide distribution info.
- [analyzeShardKey](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/) — inspect shard key characteristics and read/write distribution via query sampling (MongoDB 7.0+).
- [configureQueryAnalyzer](https://www.mongodb.com/docs/manual/reference/command/configurequeryanalyzer/) — configure query sampling and sampling overhead.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverstatus/) — instance-level metrics and counter limitations.
