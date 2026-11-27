# Evaluating when sharding is needed and its associated management costs in MongoDB

## 1. Lesson objectives

A MongoDB replica set can serve a system well for a long time. As data volume, user count, and write rates grow, engineering teams start considering **sharding**: splitting a sharded collection's data physically across multiple shards. However, sharding is not a switch where "flipping it makes every query faster." It helps distribute **storage capacity and parts of the workload** provided a suitable shard key is chosen, while introducing many additional components to operate.

This lesson in the **Sharding** chapter focuses on two questions:

1. **When is sharding truly needed?** You must verify single replica set limits, analyze growth, and evaluate simpler alternatives.
2. **What are the accompanying operational and management costs?** Not only server hardware, but also routers, config servers, indexes, the balancer, networking, backups, upgrades, distributed transactions, monitoring, and operational expertise.

After this lesson, you will be able to:

- Read capacity signals across CPU, RAM, IOPS, disk, network, throughput, and query latency.
- Distinguish **scale-up, replication, sharding, and business partitioning**.
- Use metrics and evidence to decide between **do not shard yet / prepare to shard / shard now**.
- Produce a rough shard count estimate based on growth, headroom, and data skew.
- Evaluate shard-key cardinality, frequency, monotonicity, and query targeting.
- Analyze how sharding impacts unique indexes, aggregations, transactions, and consistency.
- Plan benchmarks, migrations, failure observability, and cluster maintenance.
- Present an architectural decision backed by a grounded cost–benefit table.

**Core principle:** Shard only when there is a **measured bottleneck**, the workload **can be distributed effectively**, and the benefits outweigh the added operational cost.

## 2. Comparing scaling strategies

| Approach | Nature | Key benefits | Limitations |
| --- | --- | --- | --- |
| **Query/index tuning** | Reduce data scanned/processed | Lowers p95/p99 and unnecessary I/O | Does not increase physical machine capacity |
| **Scale-up** | Add CPU, RAM, disk/IOPS to a node | Boosts single-node capacity, minimal app changes | Hardware and cost ceilings |
| **Replication** | Multiple copies of the same dataset in a replica set | HA, failover, optional secondary reads | Normal writes still go to one primary |
| **Sharding** | Distribute documents across shards by shard key | Scales out storage and eligible workloads | Adds routers, metadata, balancing, fan-out |
| **Business partitioning** | Split by tenant, year, region, or business unit | Easier lifecycle, isolation, and retention | May only be logical rather than hardware-split |

A replica set with a primary and secondaries is **not** equivalent to three shards:

~~~text
Replica set
  Primary A       Secondary B       Secondary C
  same dataset    same dataset      same dataset
       |                ^                 ^
       +----------------+-----------------+
                 Data replication

Sharded cluster
  Application
       |
     mongos
    /  |   \
   v   v    v
Shard 1  Shard 2  Shard 3
subset A subset B subset C
   |       |         |
replica  replica   replica
set      set       set
~~~

In a standard sharded cluster, each shard is normally a **replica set** to tolerate member failures; `mongos` routes queries, and the **config server replica set (CSRS)** holds metadata. MongoDB 8.0 introduced a config shard option in supported deployments; real architectures must align with your specific version.

**Sharding distributes data**, whereas **replication duplicates each shard's data**. The two mechanisms complement each other.

## 3. Identify the bottleneck before picking a solution

Saying "the database is slow" does not prove sharding is needed. Common root causes include:

- A query performs a `COLLSCAN` due to a missing index.
- `$sort` or `$group` processes far too many documents.
- The hot data + index working set exceeds RAM/cache.
- High disk latency because SSDs lack sufficient IOPS.
- The primary is saturated by write CPU or lock contention.
- A single tenant's reporting query monopolizes resources.
- Too many indexes increase write amplification.
- The application triggers N+1 queries or deep `skip` pagination.
- Slow network links or exhausted connection pools.
- Replication lag or failovers cause intermittent request timeouts.

Moving an unindexed query from one replica set onto five shards can turn it into **five collection scans** plus a merge phase. The result is not necessarily faster.

### 3.1. Minimum metrics to collect

| Category | Metrics to observe | Questions to answer |
| --- | --- | --- |
| Queries | p50/p95/p99 by operation, timeout/error rate | Which API is slow, and when? |
| Query plans | `IXSCAN`/`COLLSCAN`, `totalDocsExamined`, `totalKeysExamined` | Are we scanning excessive documents? |
| CPU | Primary/secondary CPU, system/user CPU | Is CPU spent on writes or queries? |
| Cache/RAM | Cache occupancy, eviction, page faults, working set | Do hot data/indexes fit in RAM? |
| Disk | Data + index size, free space, growth rate | When will we hit safe capacity limits? |
| I/O | IOPS, latency, queue depth, throughput | Are storage devices saturated? |
| Writes | Ops/s, write latency, concurrency | Does the primary still have headroom? |
| Replication | Lag, oplog window, elections | Are there HA or secondary-overload issues? |
| Network | RTT, bandwidth, retransmits | Is the bottleneck outside MongoDB? |
| Skew | QPS/bytes per tenant or candidate key | Does one key drive most of the workload? |

There is no universal threshold like **"collections over 500 GB must be sharded"** or **"shard at 80% CPU"**. With different hardware, SSDs, indexes, and workloads, the exact same number carries different implications.

### 3.2. Capture both normal traffic and peak hours

A CPU snapshot at 2:00 AM does not represent 9:00 AM traffic. Cover daily/weekly cycles, promotional spikes, month-end reports, batch jobs, and major maintenance windows.

Tag metrics with:

- Tenant or business unit where applicable.
- API operation name.
- Filter and sort shapes.
- Response payload sizes.
- Read/write type.
- Read/write concern and retry rates.

Sensitive query values and tenant identifiers must follow security policies; never dump raw payloads containing personal data into logs.

## 4. Define SLOs and acceptable limits first

For example, an ordering system defines **hypothetical SLOs**:

- p95 order-detail read under 80 ms at peak.
- p99 order creation under 250 ms.
- Write failures within the agreed error budget.
- At least 18 months of storage capacity headroom.
- Survive a single member failure without prolonged service outage.
- Reports must not degrade checkout APIs past SLOs.

These numbers are **examples only**, not default MongoDB targets.

The decision to shard should stem from an already-tuned replica set **being unable to meet future SLOs or capacity** economically and reliably—not from wanting to adopt new infrastructure for its own sake.

## 5. Signals that it is time to evaluate sharding

### 5.1. Storage and working set approach single-node limits

As data + indexes continue growing, a single node may run out of:

- Disk capacity with headroom for compaction, backups, and index builds.
- RAM/cache to hold the active working set.
- I/O bandwidth for reads, writes, and replication.
- Recovery time compatible with RTO.

However, a large dataset does not automatically mean a large working set. If 90% is untouched historical data, **archival, retention policies, time-based partitioning, or storage tiering** may relieve pressure before sharding is needed.

### 5.2. Write throughput saturates the primary

A standard replica set has only **one primary accepting writes**. Adding secondaries improves fault tolerance, not multi-primary write scaling.

Sharding helps when writes **spread across many shard key values and multiple shards**. If most writes hit a single shard key value, gains may be minimal.

### 5.3. Read workloads can target few shards

Favorable case:

~~~javascript
// Example assuming shard key {tenantId: 1, orderId: 1}
db.orders.findOne({
  tenantId: "T1",
  orderId: "ORD-1001"
});
~~~

If the router can pinpoint the shard key range, the query targets narrowly.

Harder case:

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Missing the shard key in the filter can trigger **scatter-gather**, sending the query to many or all shards.

### 5.4. Vertical scale-up limits have been proven

After tuning queries, schema, indexes, connection pooling, caching, batching, archival, and machine specs, the team still observes:

- Peak traffic exceeds a single primary's sustainable throughput.
- Bigger machines yield diminishing returns relative to cost.
- Working set and recovery times no longer fit a single replica set.
- A candidate shard key distributes well on the representative workload.

This provides a solid basis to move from discussion to a sharding POC.

## 6. Cases where you should not shard yet

| Issue | Why sharding may not help | Better first step |
| --- | --- | --- |
| `COLLSCAN` on hot queries | Spreading across shards only creates distributed scans | Index / query rewrite |
| `skip` over hundreds of thousands of docs | Offset pagination stays expensive | Keyset pagination |
| Aggregation building huge arrays | Memory and BSON limits still apply | Optimize pipeline/output |
| Cold historical data dominates disk | Active dataset may actually be small | Archival / retention |
| High primary CPU from too many indexes | Sharding does not fix write amplification | Prune redundant indexes |
| Only seeking high availability | Sharded clusters still rely on replica sets per shard | Replica set + backups |
| One tenant drives 90% writes on `tenantId`-only key | A single key value easily becomes a hotspot | Compound key or tenant isolation |
| No SLOs or baseline metrics | Impossible to measure improvement | Instrumentation |
| No cluster-wide runbooks or backups | High risk during outages and migrations | Build operational readiness first |
| Queries are mostly global reports | Fan-out and merge costs can be steep | Consider pre-aggregation / caching |

Choosing **not to shard yet** after measurement and optimization is often the best engineering decision.

## 7. Storage and shard count estimation model

Suppose these **illustrative numbers**:

- Current dataset data + indexes: **1.20 TB**.
- Projected growth: **0.08 TB/month**.
- Planning horizon: **18 months**.
- Target data + index utilization per shard: **0.80 TB/shard** within safe capacity thresholds.
- Safety reservation factor for uneven distribution and hot ranges: **25%**.

### 7.1. Projected storage

~~~text
18-month storage
  = 1.20 TB + (0.08 TB × 18)
  = 2.64 TB
~~~

### 7.2. Baseline shard count

~~~text
N = ceil(2.64 / 0.80)
  = ceil(3.30)
  = 4 shards
~~~

### 7.3. Adding the skew/safety factor

~~~text
N with headroom = ceil(2.64 × 1.25 / 0.80)
                = ceil(4.125)
                = 5 shards
~~~

This is strictly a **preliminary storage sizing model**, not an order to buy five shards. You must still check throughput, IOPS, RAM, query targeting, tenant counts, migration headroom, and budget separately.

### 7.4. Replication cost across shards

If each shard has **3 data-bearing members**:

~~~text
5 shards × 3 members = 15 data-bearing mongod members

Data + index copies, theoretically:
2.64 TB × 3 = 7.92 TB

Excluding oplog, journal, filesystem overhead,
temporary files, compression differences,
config servers, backups, and spare capacity.
~~~

**The 25% safety factor is not literally 25% extra stored bytes.** It is capacity reservation to avoid bumping into utilization ceilings, not additional physical bytes written.

Even though sharding splits 2.64 TB logically, replication still creates multiple full copies of each shard.

## 8. Throughput model: even data does not mean even load

Suppose benchmarks show a single primary meets SLOs at **8,000 writes/sec**, whereas at **12,000 writes/sec** p99 latency and I/O spike unacceptably. Forecasted demand is **18,000 writes/sec**.

An ideal split:

~~~text
Shard A: 6,000 writes/s
Shard B: 6,000 writes/s
Shard C: 6,000 writes/s
~~~

can work if each shard handles that rate and query/replication overhead stays acceptable.

However, a skewed distribution:

~~~text
Shard A: 15,000 writes/s
Shard B:  2,000 writes/s
Shard C:  1,000 writes/s
~~~

still overloads Shard A even when nominal total cluster capacity looks high.

**Never assume throughput scales linearly with shard count.** Measure:

- Write QPS per tenant / candidate key.
- Traffic share of the top 1% and top 10% keys.
- Distinct key count.
- Document sizes and per-shard indexes.
- Query patterns and transaction frequency.
- Network and replication overhead.
- Balancer migrations under load.

## 9. The shard key is the single most consequential decision

Sharding relies on the **shard key** to map documents to chunks/ranges. The shard key governs:

1. Data distribution.
2. Write distribution.
3. How many shards each query must touch.
4. Eligibility for ranges and zones.
5. Unique constraints.
6. Future migrations and resharding.

### 9.1. Cardinality

**Cardinality** is the number of distinct shard key values.

- Very low cardinality makes it hard to split data into many granular ranges.
- High cardinality generally offers finer splitting choices.
- Yet high cardinality **does not guarantee** uniform distribution if a few keys are intensely hot.

### 9.2. Frequency

**Frequency** is how many documents or operations share the same key value.

For example:

~~~text
Tenant A: 90% write QPS
Tenant B:  5% write QPS
Tenant C:  3% write QPS
Others:    2%
~~~

A `{tenantId: "hashed"}` shard key will not distribute Tenant A's traffic across multiple shards, because every document with `tenantId` A hashes to the exact same value.

### 9.3. Monotonicity

Monotonically increasing keys, such as timestamps or sequential order numbers, can direct all new inserts onto the trailing range of a single shard.

Ranged keys can benefit range queries, yet require mitigating monotonic write hotspots. Hashed keys can spread certain sequential workloads, while sacrificing locality over the original ordering.

### 9.4. Ranged vs. hashed sharding

| Property | Ranged shard key | Hashed shard key |
| --- | --- | --- |
| Distribution | By ordered value ranges | By ranges of hashed values |
| Range queries on original key | Usually more favorable | Less favorable |
| Monotonically increasing key | Risk of trailing hotspot | Can scatter writes better |
| Single dominant hot key | Still hot | Still hot (identical hash value) |
| Unique hashed index | Not applicable | Hashed indexes do not support `unique: true` |
| Zone policies | Uses key ranges | Must account for hashed ranges |

### 9.5. Compound shard keys

Example:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Using two fields provides multiple key values within each tenant. Still:

- Queries filtering only by `tenantId` may hit multiple ranges/shards.
- Queries specifying both `tenantId` and `orderId` usually target more narrowly.
- Queries filtering only by `status` may scatter-gather.
- Unique indexes must respect the shard-key prefix and version rules.

Never choose a compound key on intuition ("more fields must split better"); measure on real workloads.

## 10. Query targeting and scatter-gather costs

Suppose a collection uses shard key `{tenantId:1,orderId:1}`.

**Point query with full shard key:**

~~~javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "A-001"
});
~~~

**Prefix-only query:**

~~~javascript
db.orders.find({
  tenantId: "A"
});
~~~

**Query without shard key:**

~~~javascript
db.orders.find({
  status: "PAID"
});
~~~

Typical routing behavior:

| Query | Typical routing |
| --- | --- |
| Full shard key equality | Usually narrowest targeting |
| Compound key prefix filter | May touch one or multiple shards |
| Range on shard key | Can target relevant ranges |
| Filter completely outside shard key | Usually queries many or all shards |

Scatter-gather adds:

- More internal sub-requests.
- Read/index scan work on every shard.
- Network transfers.
- Cross-shard merge, sort, and aggregation work.
- Tail latency tied to the slowest responding shard.

**Sharding and indexing solve different problems:** the shard key decides **which shards to ask**, while indexes help each shard **scan fewer documents**. A targeted query without an index can still be slow; an indexed query sent to every shard still pays fan-out overhead.

## 11. Unique constraints and transactions can shift costs dramatically

### 11.1. Unique indexes on sharded collections

On sharded collections, enforcing uniqueness comes with shard-key rules. Under ranged sharding, a unique index generally must have the **entire shard key as its prefix** per MongoDB rules.

Suppose the shard key is `{tenantId:1}`. The index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

enforces uniqueness per `(tenantId, emailKey)` pair, **not** global uniqueness of email across the whole system.

If global email uniqueness is required, redesign the shard key or maintain an appropriate registry/coordination structure. Never just drop `tenantId` from the unique index expecting the cluster to enforce it across all shards.

When `_id` is not the shard key on a sharded collection, `_id` uniqueness is generally enforced per shard rather than globally; applications must generate globally unique IDs.

### 11.2. Multi-shard transactions

A funds transfer:

~~~text
Debit account on Shard A
Credit account on Shard B
~~~

does not automatically become atomic simply by running through `mongos`. MongoDB supports distributed transactions on compatible topologies and versions, adding:

- Coordination and commit protocol overhead.
- Network hops across participants.
- Transaction state, locks, and cache retention.
- Retries on write conflicts or transient failures.
- Potential p99 latency impact.
- Requirement for proper application-side transaction error handling.

There is no fixed overhead multiplier across all transactions; benchmark it. Still, **percentage of transactions touching multiple shards** is a vital metric to estimate pre-rollout.

### 11.3. Read consistency does not automatically improve with more shards

Secondaries inside a shard's replica set can still experience replication lag. Read concern, write concern, and causal consistency still require explicit design.

For example, inventory updates need an atomic conditional update:

~~~javascript
db.inventory.updateOne(
  { tenantId: "A", sku: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);
~~~

Never read stale stock from a secondary and subtract unconditionally assuming sharding prevents race conditions.

## 12. Infrastructure cost: from three members to many components

### 12.1. Single replica set

A three-member data-bearing replica set:

~~~text
App -> (P, S, S)
       3 mongod
~~~

Operations manages elections, replication lag, oplog, backups, indexes, and upgrades.

### 12.2. Three-shard sharded cluster

Illustrative topology with dedicated config servers:

~~~text
                          App
                           |
                        2 mongos
                           |
        +------------------+------------------+
        |                  |                  |
      Shard A            Shard B            Shard C
      P/S/S              P/S/S              P/S/S
        |                  |                  |
        +------------------+------------------+
                           |
                    CSRS (3 members)
~~~

Process count in this layout:

- 3 shard replica sets × 3 data-bearing members = **9 `mongod`**.
- 1 config server replica set × 3 members = **3 `mongod`**.
- 2 routers for high availability = **2 `mongos`**.
- Total **14 processes** before counting monitoring agents, backups, load balancers, and other infrastructure.

This is **not the only mandatory layout** across every version/deployment: managed services and config shards have variations. It simply illustrates why scaling to three shards is not "just adding two extra servers."

### 12.3. TCO formula

~~~text
TCO =
  Compute for all shard members
+ Storage / indexes / oplog / headroom
+ Config servers and routers
+ Network across members, shards, and regions
+ Backups and restores
+ Monitoring, logging, and alerting
+ Upgrades and migrations
+ On-call, runbooks, and incident response
+ Application development and testing cost
~~~

You cannot multiply a single database node's price by shard count and call it total cost. Even on managed services where some items are bundled in the bill, responsibility for shard key design, query routing, and data correctness stays with your team.

## 13. Lifecycle management overhead

| Area | Single replica set | Sharded cluster |
| --- | --- | --- |
| Topology | Primary + secondaries | Shard replica sets, CSRS, routers |
| Queries | Dataset indexes and plans | Adds shard targeting, merging, and fan-out |
| Data placement | No chunk migrations | Chunks/ranges and the balancer |
| Monitoring | CPU, storage, lag | All of those **per shard** + metadata/routing |
| Hotspots | Query, node, collection | Hot shard, hot range, hot shard-key value |
| Index management | Collection indexes | Shard-key and unique constraints |
| Capacity | Scale replica set vertically | Scale shards up/down and add shards |
| Backups | Replica-set-consistent backup | Cluster-wide consistent backup |
| Restores | Restore dataset | Coordinate shards + metadata |
| Upgrades | Rolling upgrade / election | Sequence shards, config servers, routers, FCV |
| Failovers | Single replica set election | Elections per shard + shard outages |
| Transactions | Within one replica set | May trigger distributed commits |
| Data reorganization | Custom migrations | Balancing, zones, resharding |

### 13.1. The balancer does not balance everything

MongoDB manages shard key intervals as ranges/chunks. The balancer can move ranges according to configuration and zone rules.

Migration costs include network traffic, I/O, metadata coordination, and temporary disk usage. The balancer primarily addresses **placement**, not guaranteeing equal CPU, byte counts, query counts, or write QPS.

One hot tenant can generate 80% of writes on a single shard while disk usage across shards appears nicely balanced.

### 13.2. Backups, restores, and RPO/RTO

In a sharded cluster, taking independent snapshots of each shard at arbitrary times does not yield **a cluster-wide consistent state**.

Choose a backup method supporting your topology and version, and verify:

- Data across all shards.
- Config metadata and routing state.
- Snapshot or point-in-time consistency.
- Single-collection/tenant vs. full-cluster restores.
- Recovery duration relative to RTO.
- Acceptable data loss relative to RPO.
- Ability to rebuild indexes, users, and schemas.
- Regularly rehearsed restore drills.

Replication **is not a backup**: an accepted accidental delete replicates swiftly to all members.

### 13.3. Upgrades and FCV

A sharded cluster spans multiple components with strict version and **Feature Compatibility Version (FCV)** rules. Upgrade sequencing, preconditions, balancer state, and rollback steps must follow official documentation for your release.

Never upgrade shards and routers in arbitrary order simply because they run on separate servers.

### 13.4. Per-shard observability

A dashboard displaying only **cluster-average CPU** can hide a burning hot shard. Monitor:

- CPU, RAM, IOPS, and storage on **every shard member**.
- Read/write throughput per shard.
- Replication lag per replica set.
- Chunk/range distribution and migration activity.
- Targeted vs. scatter-gather query ratio.
- Slow operations, server-selection errors, and router metrics.
- Connection pools, network metrics, and election events.
- Query p99 by API and tenant.
- Capacity headroom and projected exhaustion dates.

## 14. Failure domains: adding shards adds failure modes

### 14.1. Losing a single member

If Shard A's replica set retains a voting majority and an eligible member, losing one member is handled via election/failover. That comes from replication.

### 14.2. Losing an entire shard

If **all of Shard B** becomes unavailable, healthy Shards A and C **do not hold copies of Shard B's data subset**. Queries requiring Shard B's data fail, even though other shards can still serve partial workloads.

### 14.3. Router and config metadata

`mongos` routers must be deployed redundantly. The config server replica set holds metadata needed to coordinate the cluster. Network partitions or metadata issues can disrupt operations and maintenance.

### 14.4. Hot shard

If one shard hits 100% CPU while others sit at 20%, cluster-wide averages look fine—yet latency for requests hitting the hot shard degrades sharply.

**Rule:** When sharding, monitor **max per-shard resource utilization**, not just averages.

## 15. Business partitioning as an alternative or complement

### 15.1. TenantId inside the same collection

~~~javascript
{
  tenantId: "tenant-A",
  orderId: "A-001",
  status: "PAID"
}
~~~

Using `tenantId` with compound indexes is **logical partitioning**; if the collection is unsharded, data still lives on one replica set.

### 15.2. Yearly collections

~~~text
orders_2024
orders_2025
orders_2026
~~~

This simplifies archival/retention and bounds queries within a period, though keeping all collections on one replica set does not increase write capacity.

### 15.3. Database per tenant

Giving each tenant its own database can ease certain governance policies. In exchange, namespace counts, migrations, backups, and index footprints multiply. When hosted on the same cluster/primary, tenants still compete for resources.

### 15.4. Dedicated cluster for large tenants

A massive tenant driving most QPS or needing strict SLAs/residency can be isolated onto an independent cluster. Trade-offs: tenant-to-cluster routing tables, migrations, cross-tenant reporting, and managing multiple deployments.

Do not confuse application-routed multi-cluster tenancy with a single logical sharded collection managed by `mongos`.

### 15.5. Archive before sharding

If 80% of storage is cold historical data, consider:

- Formal retention rules.
- TTL indexes where deletion is allowed.
- Period-partitioned collections.
- Cold storage offloading.
- Pre-aggregated summary reports.
- Time-series collections where suitable for measurement workloads.

Distinguish **storing less hot data** from **needing to scale out the remaining hot workload**.

## 16. Three-tier decision framework

| Status | Evidence | Action |
| --- | --- | --- |
| **Do not shard yet** | SLOs met, adequate headroom, unoptimized queries | Tune queries/indexes and keep measuring |
| **Prepare to shard** | Growth approaching limits, clear candidate key, time for POC | Design key, benchmark, stage, build runbooks |
| **Shard now** | Confirmed bottleneck, scale-up exhausted, distributable workload, ops ready | Execute controlled rollout and monitor |

### 16.1. Go/no-go gates

Before deciding, answer:

- **G1 — Bottleneck:** which exact resource is out of headroom?
- **G2 — Alternatives:** have indexes, schema, caching, archival, and scale-up been evaluated?
- **G3 — Key distribution:** what do cardinality, frequency, and skew look like on real data?
- **G4 — Query mix:** what share of queries target narrowly vs. run globally?
- **G5 — Correctness:** are unique indexes, transactions, and consistency compatible?
- **G6 — TCO & operations:** are budget, backups, monitoring, on-call, and recovery plans ready?

Even one unresolved **mandatory gate** is reason enough to pause rollout and gather more evidence.

### 16.2. Scoring matrix to guide discussion

You can score criteria from 0 to 3, though never treat raw sum totals as an automated decision:

| Factor | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Storage | Ample headroom | Some pressure | Near threshold | Exceeds safe threshold |
| 18-month growth | Slow | Moderate | Fast | Outpaces projected capacity |
| Write saturation | None | Unclear | Evidenced | Confirmed and hard to scale up |
| Key distribution | Severely skewed | Unmeasured | Fair | Strong on real workload |
| Query targeting | Mostly global | Many global | Mostly targeted | Predominantly narrow-targeted |
| Readiness | None | Partial | Staging & runbook | Rehearsed with DR |

A high capacity score cannot compensate for a broken shard key. Individual criteria act as **hard gates**, not merely weighted points.

## 17. `mongosh` lab: measuring distribution before sharding

This exercise **does not require a sharded cluster** and only touches a practice database.

~~~javascript
const lab = db.getSiblingDB("sharding_decision_lab");

// Drops only the lab collection; never run on production.
lab.orders.drop();

lab.orders.insertMany([
  { _id: 101, tenantId: "A", orderId: "A-001",
    status: "PAID", total: 100, createdAt: ISODate("2026-01-01T08:00:00Z") },
  { _id: 102, tenantId: "A", orderId: "A-002",
    status: "PAID", total: 150, createdAt: ISODate("2026-01-02T08:00:00Z") },
  { _id: 103, tenantId: "A", orderId: "A-003",
    status: "PENDING", total: 230, createdAt: ISODate("2026-01-03T08:00:00Z") },
  { _id: 104, tenantId: "A", orderId: "A-004",
    status: "PAID", total: 400, createdAt: ISODate("2026-01-04T08:00:00Z") },
  { _id: 105, tenantId: "A", orderId: "A-005",
    status: "PAID", total: 80, createdAt: ISODate("2026-01-05T08:00:00Z") },
  { _id: 106, tenantId: "A", orderId: "A-006",
    status: "CANCELLED", total: 20, createdAt: ISODate("2026-01-06T08:00:00Z") },
  { _id: 107, tenantId: "A", orderId: "A-007",
    status: "PAID", total: 260, createdAt: ISODate("2026-01-07T08:00:00Z") },
  { _id: 108, tenantId: "A", orderId: "A-008",
    status: "PAID", total: 110, createdAt: ISODate("2026-01-08T08:00:00Z") },

  { _id: 201, tenantId: "B", orderId: "B-001",
    status: "PAID", total: 75, createdAt: ISODate("2026-01-01T09:00:00Z") },
  { _id: 202, tenantId: "B", orderId: "B-002",
    status: "PAID", total: 125, createdAt: ISODate("2026-01-02T09:00:00Z") },
  { _id: 203, tenantId: "B", orderId: "B-003",
    status: "PENDING", total: 50, createdAt: ISODate("2026-01-03T09:00:00Z") },
  { _id: 204, tenantId: "B", orderId: "B-004",
    status: "PAID", total: 200, createdAt: ISODate("2026-01-04T09:00:00Z") },

  { _id: 301, tenantId: "C", orderId: "C-001",
    status: "PAID", total: 40, createdAt: ISODate("2026-01-01T10:00:00Z") },
  { _id: 302, tenantId: "C", orderId: "C-002",
    status: "CANCELLED", total: 60, createdAt: ISODate("2026-01-02T10:00:00Z") },
  { _id: 303, tenantId: "C", orderId: "C-003",
    status: "PAID", total: 90, createdAt: ISODate("2026-01-03T10:00:00Z") },

  { _id: 401, tenantId: "D", orderId: "D-001",
    status: "PAID", total: 700, createdAt: ISODate("2026-01-01T11:00:00Z") }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_date" }
);

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "uq_tenant_order" }
);
~~~

There are **16 orders** and **4 tenants**. The dataset is intentionally tiny for manual verification, not for benchmarking sharding.

### 17.1. Document distribution

~~~javascript
lab.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      n: { $sum: 1 }
    }
  },
  { $sort: { n: -1, _id: 1 } }
]).toArray();
~~~

| Tenant | Orders | Share |
| --- | ---: | ---: |
| A | 8 | 50% |
| B | 4 | 25% |
| C | 3 | 18.75% |
| D | 1 | 6.25% |
| **Total** | **16** | **100%** |

This **does not prove Tenant A generates 50% of QPS**: historical document counts and operations per second are two different quantities.

### 17.2. PAID orders aggregation

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

| Tenant | PAID orders | PAID amount |
| --- | ---: | ---: |
| A | 6 | 1,100 |
| B | 3 | 400 |
| C | 2 | 130 |
| D | 1 | 700 |
| **Total** | **12** | **2,330** |

These are synthetic lab values, not real revenue figures. Monetary values in production should use suitable numeric types and rounding rules, such as `Decimal128`.

### 17.3. Inspect query plans

~~~javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Examine query plan, documents examined, keys examined, and latency. Index `ix_tenant_status_date` is defined for this pattern, though MongoDB might pick another plan on a tiny lab collection.

Before deciding to shard, make sure **queries are already efficient on a single shard**.

### 17.4. Check collection stats

~~~javascript
lab.runCommand({
  collStats: "orders",
  scale: 1048576
});
~~~

Output depends on version and topology, and reports sizes, storage/index footprint, and counts. `scale` simply changes display units.

## 18. Optional experiment on a prepared sharded cluster

The commands below are **strictly for staging** connected through `mongos`. Never alter production metadata directly.

### 18.1. Observe the cluster

~~~javascript
sh.status();
~~~

In many setups, `db.hello()` run against `mongos` returns `msg: "isdbgrid"`, distinguishing a router from a `mongod` member.

### 18.2. `shardCollection` example

Assuming the workload has been evaluated and shard key `{tenantId:1,orderId:1}` satisfies preconditions:

~~~javascript
// Architectural/metadata change: run ONLY in a test environment.
sh.shardCollection(
  "sharding_decision_lab.orders",
  { tenantId: 1, orderId: 1 }
);
~~~

Eligibility and behavior on populated collections depend on MongoDB version, indexes, uniqueness, and cluster state. Never treat a short command as a full migration plan.

### 18.3. Targeted vs. scatter-gather

~~~javascript
lab.orders.explain("queryPlanner").find({
  tenantId: "A",
  orderId: "A-001"
});

lab.orders.explain("queryPlanner").find({
  status: "PAID"
});
~~~

In the explain output, inspect the number of shards queried and the per-shard plan; exact field structures vary by version and query engine. Never confuse an `IXSCAN` on every shard with targeting a single shard.

You can also inspect `sh.status()` and collection distribution helpers like `getShardDistribution()` where supported. **Balanced chunk counts are not proof of balanced QPS.**

## 19. Benchmarking the sharding candidate

Evaluate the candidate sharded cluster using the **same dataset and query mix** as the replica set baseline, including peak traffic, skews, concurrency, and configured read/write concerns.

| Test case | Metrics | Purpose |
| --- | --- | --- |
| Full shard-key point reads | p95/p99, shards targeted | Verify narrow routing |
| Tenant-only reads | Fan-out, latency | Check whether large tenants span shards |
| Global aggregations | Scatter-gather, merge, CPU | Measure reporting overhead |
| Distributed writes | Ops/s, p99, per-shard CPU | Prove write scale-out |
| Hot-tenant writes | Hot shard, error rate | Detect skewed key saturation |
| Multi-shard transactions | Commit latency, retries | Measure coordination cost |
| Balancing/migrations | Network, p99, resource spikes | Assess background impact |
| Member failover | Errors/recovery time | Verify intra-shard HA |
| Shard outage | App errors, partial availability | Validate failure handling |
| Backup/restore | RPO/RTO, consistency | Prove recovery |

If average throughput increases while p99 or error rates breach SLOs, the candidate design **fails acceptance**.

Compare **total cost per unit of SLO-compliant workload**, not peak raw ops/sec in a short synthetic run.

## 20. Controlled rollout roadmap

### Phase A — Discovery

1. Collect representative metrics and query patterns.
2. Exhaust remaining query, index, and schema optimizations.
3. Forecast data + index growth alongside workload growth.
4. Measure candidate shard-key distributions.
5. Analyze unique indexes, multi-shard transactions, and global queries.
6. Draft preliminary cost–benefit comparisons against scale-up or partitioning.

### Phase B — Proof of concept

1. Stand up a staging sharded cluster matching version and topology.
2. Load a representative dataset including hot tenants and monotonic data.
3. Build indexes matching each workload query.
4. Measure throughput, p95/p99, storage, and CPU/IOPS/network per shard.
5. Test balancer activity, failovers, and long-running aggregations.
6. Test full backup and restore execution, not just snapshot creation.

### Phase C — Readiness

1. Prepare connection URIs, `mongos` endpoints, and driver pools.
2. Audit shard-key requirements for `find`/`update`/`upsert`.
3. Verify global unique IDs and constraints.
4. Finalize consistency and transaction semantics.
5. Set up monitoring, alerting, and runbooks.
6. Prepare contingency plans if migration stalls or fails.

### Phase D — Migration

1. Capture a verified backup before making changes.
2. Follow the MongoDB-supported procedure for your version and data state.
3. Guard write behavior during sensitive cutover phases.
4. Reconcile counts and business invariants.
5. Monitor chunk movements and query routing.
6. Shift traffic progressively with explicit abort gates if SLOs breach.
7. Do not assume "dropping the shard key" is an easy rollback; resharding/unsharding carry strict preconditions.

### Phase E — Long-term operations

1. Track hot shards, growth rates, and capacity headroom.
2. Periodically audit scatter-gather queries.
3. Drill restores, shard outages, and upgrades.
4. Revisit shard-key assumptions as workloads shift.
5. Evaluate adding shards or resharding based on empirical evidence.

Sharding is a **long-term operational capability**, not a one-time task.

## 21. Decision scenarios

### Scenario A — Queries are slow due to missing indexes

Dataset is 200 GB, CPU 85%, one endpoint p99 is 500 ms. `explain` reveals heavy scanning from a missing compound index on `status/category/price`.

**Decision:** Tune indexes/queries and re-measure first. If p99 returns within SLO and headroom remains, do not shard yet.

### Scenario B — Capacity and write QPS exceed one node

Dataset grows steadily, projected write QPS exceeds a primary's ceiling, most queries include tenant/order keys, and a candidate shard key distributes writes evenly.

**Decision:** A sharding POC is justified. Still measure hot-tenant share, global queries, unique constraints, and full TCO.

### Scenario C — One large tenant drives most traffic

Tenant A generates 92% of writes. Key `{tenantId:"hashed"}` cannot split documents sharing `tenantId` A.

**Decision:** Evaluate a compound shard key with a field that distributes within the tenant, a dedicated cluster, or a routed partitioning model.

### Scenario D — Most data is cold history

85% of storage is logs untouched for years. Retention and archival can shrink the active dataset dramatically.

**Decision:** Evaluate archival, tiering, or time-based partitions first; never delete data outside policy.

### Scenario E — Regional data residency

EU and APAC data must stay in separate locations. Zone sharding or separate regional clusters may work.

**Decision:** Compare locality guarantees and TCO. Zone placement **does not automatically ensure** all replica members, backups, logs, or exports remain inside legal jurisdictions.

## 22. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Data over 1 TB definitely requires sharding" | There is no universal size threshold |
| "Database is slow so add shards" | Diagnose query, index, and I/O bottlenecks first |
| "Three replica members equal three shards" | Replica members hold the same dataset; shards hold subsets |
| "Adding secondaries increases write capacity" | Writes still go to the replica set primary |
| "More shards always make queries faster" | Scatter-gather and merge overhead can dominate |
| "Hashing tenantId spreads a hot tenant across all shards" | One tenantId produces one hashed value |
| "The balancer automatically balances CPU and QPS perfectly" | The balancer mainly manages range placement |
| "A bad shard key can be changed for free" | Resharding consumes heavy resources and has preconditions |
| "Having `tenantId` means we are sharded" | That may just be logical business partitioning |
| "Unique indexes work identically to standalone replica sets" | Shard-key prefix and uniqueness rules apply |
| "Primary shard means the primary member of a replica set" | They are concepts at two different architectural tiers |
| "With a good `$match`, every aggregation hits one shard" | Requires shard-key filtering and compatible plans |
| "Independent shard snapshots equal a consistent backup" | Coordinated cluster-wide backups are required |
| "Replication eliminates the need for backups" | Accidental deletes and bugs replicate too |
| "TCO is only the price of shard nodes" | Includes CSRS, routers, network, DR, and ops effort |
| "Benchmarking inserts/sec is sufficient" | Must measure p99, global queries, balancing, and failovers |
| "Once sharded, no further monitoring is needed" | Skew and workloads shift over time |

## 23. Practice exercises

### Exercise 1 — Pick the scaling strategy

An application needs: (a) tolerance for a single-server failure; (b) lower query p99 caused by a COLLSCAN; (c) logical storage scaling past a single node; (d) yearly data archival. Prioritize replication, indexing, sharding, or business partitioning for each item and explain why.

### Exercise 2 — 18-month capacity sizing

Data + indexes = 1.20 TB; growth = 80 GB/month; horizon = 18 months; target = 0.80 TB/shard; safety factor = 25%. Compute baseline shard count and post-safety-factor shard count.

**Answer:** 2.64 TB projected; 4 baseline shards; 5 shards with safety headroom.

### Exercise 3 — Storage with replication

With 5 shards and 3 data-bearing members per shard, how many data-bearing members are there? With 2.64 TB logical data + index size, what is the raw three-copy footprint ignoring overhead?

**Answer:** 15 members; 7.92 TB of replicated data + index copies.

### Exercise 4 — Hot shard

Three shards receive 15,000 / 2,000 / 1,000 writes/sec respectively. Why can p99 still degrade even though nominal total throughput looks adequate?

**Answer:** One hot shard becomes the bottleneck; inspect shard-key skew, workload distribution, and per-shard capacity.

### Exercise 5 — Query targeting

Shard key `{tenantId:1,orderId:1}`. Compare routing for:

~~~javascript
db.orders.findOne({ tenantId: "A", orderId: "A-001" });
db.orders.find({ tenantId: "A" });
db.orders.find({ status: "PAID" });
~~~

**Answer:** Full key usually targets most narrowly; tenant-only may touch multiple shards; status-only usually triggers scatter-gather.

### Exercise 6 — Verifying indexes before sharding

Run `explain` on `lab.orders` with `tenantId="A"`, `status="PAID"`, sorted by `createdAt`. Which index was created for this query? Why verify query plans before sharding?

### Exercise 7 — Tenant distribution

The fixture contains A=8, B=4, C=3, D=1 documents. Calculate percentage shares and explain why this ratio cannot serve as write QPS distribution.

**Answer:** 50%, 25%, 18.75%, 6.25%; existing document count does not measure live write rate.

### Exercise 8 — PAID report

Compute PAID order count and total amount per tenant. Cross-check:

~~~text
A: 6 orders, 1,100
B: 3 orders,   400
C: 2 orders,   130
D: 1 order,    700
Total: 12 orders, 2,330
~~~

If this aggregation runs cluster-wide, what merge operations are needed across shards?

### Exercise 9 — Process count overhead

Compare a 3-member replica set against three 3-member shards + a 3-member CSRS + two routers.

**Answer:** 3 `mongod` vs. 9 + 3 = 12 `mongod` plus 2 `mongos`, totaling 14 processes in the illustrative topology.

### Exercise 10 — Global unique email

A collection is sharded on `tenantId`, yet email must be unique application-wide. Why doesn't a unique index on `{tenantId:1,emailKey:1}` satisfy this? Propose a registry collection or an alternative shard key design.

### Exercise 11 — Backup and restore

Why do snapshots of four shards taken at four separate timestamps fail to produce a cluster-wide consistent backup? List RPO/RTO and metadata requirements.

### Exercise 12 — Cross-shard transaction

A funds transfer updates two accounts on different shards. When is a distributed transaction needed? List at least three extra costs compared to two independent writes.

### Exercise 13 — Zones and compliance

EU data must stay in the EU. Is configuring one zone range sufficient? List replica placement, backup, log, and export checks required.

### Exercise 14 — Hot-tenant decision

One tenant produces 92% of writes and needs an isolated SLA. Compare a compound shard key in a shared cluster against a dedicated cluster. What are the trade-offs in isolation, cost, and routing?

### Exercise 15 — Benchmark plan

Design a benchmark comparing a tuned replica set against a candidate sharded cluster. Include targeted reads, global aggregations, hot-tenant writes, balancing, failover, and p99/error rates.

### Exercise 16 — GO/NO-GO decision

Fill out G1–G6 for a hypothetical system: bottleneck, alternatives, shard key distribution, query mix, unique/transaction constraints, TCO, runbooks, and DR. Conclude **do not shard yet**, **prepare to shard**, or **shard now** backed by quantitative evidence.

## 24. Summary

Sharding is valuable when you need to **scale out storage and workloads** beyond the technical or economic limits of a single shard. It pays off only when the shard key distributes data and load well, queries can target shards effectively, and the organization can sustain cluster operations.

Ten principles:

1. Measure bottlenecks and SLOs before sharding.
2. Tune indexes, schemas, cache, and vertical scaling before adding distributed complexity.
3. Forecast growth and capacity with explicit headroom.
4. Evaluate shard-key cardinality, frequency, monotonicity, and skew.
5. Measure both targeted queries and scatter-gather/global aggregations.
6. Never assume throughput scales linearly with shard count.
7. Maintain replication and backups: sharding replaces neither HA nor disaster recovery.
8. Account for full TCO: shard members, CSRS, routers, balancing, network, monitoring, and on-call.
9. Audit unique constraints, consistency, transactions, and migration plans.
10. Decide using benchmarks with realistic workloads, p95/p99 latency, and failure scenarios.

**Choosing not to shard when it isn't needed is also a sound decision.** Once scale-out evidence and operational readiness are proven, sharding unlocks MongoDB growth—with management costs that must be consciously accepted and sustained over time.

### Official MongoDB documentation

- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — concepts, cluster components, and data distribution.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shard replica sets, `mongos`, config servers.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — criteria for evaluating shard keys.
- [Shard Key Cardinality](https://www.mongodb.com/docs/manual/core/shard-key-cardinality/) — distinct shard key values.
- [Shard Key Frequency](https://www.mongodb.com/docs/manual/core/shard-key-frequency/) — key frequency and hotspots.
- [Shard Key Monotonicity](https://www.mongodb.com/docs/manual/core/shard-key-monotonic/) — monotonic growth and write distribution.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — range queries and placement.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hash distribution and trade-offs.
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/) — chunk/range distribution.
- [Balancer Administration](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — balancing and migrations.
- [Resharding](https://www.mongodb.com/docs/manual/core/resharding/) — changing the shard key under supported conditions.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — key-range zone placement.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — unique indexes and shard keys.
- [Replication](https://www.mongodb.com/docs/manual/replication/) — replica sets and failover.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document and distributed transactions.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — analyzing query plans.
- [collStats Command](https://www.mongodb.com/docs/manual/reference/command/collStats/) — storage and index statistics.
