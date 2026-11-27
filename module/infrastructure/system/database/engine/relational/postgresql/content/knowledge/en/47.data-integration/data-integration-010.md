# Single-Node PostgreSQL Limits and Criteria for Considering Data Distribution

## 1. How Far Can Single-Node PostgreSQL Go, and Where Do Limits Appear?

PostgreSQL is typically deployed with a single primary database server handling reads and writes. A server equipped with multi-core CPUs, large RAM, fast NVMe storage, and solid backups can sustain substantial workloads. Many systems never need sharding over the entire product lifecycle if schemas, indexes, queries, connection management, and capacity are designed well.

Still, a single node has physical and architectural limits. CPU, RAM, I/O, network bandwidth, storage capacity, recovery speed, and maintenance speed are all finite. Once a workload crosses one of these ceilings, throwing bigger hardware at it can grow increasingly expensive or fail to fix the actual bottleneck. Some workloads are also constrained by contention on the same rows, write serialization, locks, or a single transaction coordinator.

**Data distribution** spreads data and/or query processing across multiple database nodes to increase capacity, locality, or availability. This can enable horizontal scaling, but introduces costs around routing, consistency, distributed transactions, failure handling, observability, backups, and operations.

The decision to distribute should never rest solely on row counts or a gut feeling that "the database is getting big." Identify the real bottleneck, forecast growth, exhaust lower-complexity optimizations first, and evaluate whether the workload actually partitions cleanly into independent units.

```text
Workload
   |
   v
Measure the bottleneck
   |
   +-- Query / schema / index issue? ----> Optimize SQL and data model
   |
   +-- Connection pressure? -------------> Pooling and concurrency control
   |
   +-- Read capacity? -------------------> Cache / read replicas
   |
   +-- Storage or memory capacity? ------> Tune / partition / scale up
   |
   +-- One node is the hard ceiling?
             |
             v
       Evaluate distribution
             |
       +-----+-------------------+
       |                         |
       v                         v
 Independent partitions      Tight cross-data
 and routing possible?       transactions/joins?
       |                         |
       v                         v
 Shard/distribute candidate   Keep centralized or
                              redesign boundaries
```

### Learning Objectives

After completing this lesson, you will be able to:

1. Explain the single-primary PostgreSQL model and the limits of a single node.
2. Distinguish scaling up, read scaling, partitioning, replication, and sharding.
3. Identify bottlenecks in CPU, memory, storage, network, locks, WAL, and vacuum.
4. Measure capacity using metrics and workload forecasts.
5. Determine when query and schema optimization remain effective.
6. Understand why read replicas do not automatically scale write throughput.
7. Distinguish high availability/failover from horizontal scaling.
8. Evaluate shard keys, tenant locality, skew, and cross-shard queries.
9. Understand consistency, distributed transactions, and failure modes.
10. Compare application-level sharding, Citus, FDWs, and distributed SQL systems.
11. Build a decision framework backed by measurable thresholds.
12. Plan migrations, rebalancing, backups, and disaster recovery.
13. Design observability across multiple database nodes.
14. Recognize signs of distributing too early or too late.
15. Chart a controlled scaling roadmap from a single node to a distributed architecture.

---

## 2. The Single-Node PostgreSQL Model

In the standard model, a PostgreSQL cluster runs on a single host or managed database instance. One primary accepts writes and commonly serves reads. PostgreSQL backend processes handle client sessions, shared memory coordinates state, and storage holds data files and WAL.

A single node may include:
- Many CPU cores.
- Large RAM.
- Local SSD/NVMe or network-attached storage.
- Multiple data tablespaces or volumes.
- A connection pooler.
- Background workers, autovacuum, and the WAL writer.
- Backup and archiving agents.
- Monitoring and failover integration.

### 2.1. One Node Does Not Mean One CPU Core

PostgreSQL utilizes many cores through concurrent backends, parallel query workers, and background processes. A single query will not always saturate all cores; parallelism depends on the query plan, configuration settings, and operation type.

### 2.2. One Primary Is Typically the Central Write Point

In core PostgreSQL, one primary handles writes for a cluster. Many clients can write concurrently, yet locks, WAL ordering, shared catalogs, and transaction coordination remain centralized inside that cluster.

### 2.3. Multiple Databases in One Cluster Still Share Resources

Creating multiple logical databases does not multiply CPU, RAM, IOPS, or WAL capacity. Databases within the same cluster compete for host resources and share the same instance limits.

### 2.4. Multiple Tablespaces Are Not Sharding

Tablespaces place objects onto different storage paths, yet PostgreSQL still manages them inside one cluster. They do not create independent query engines or distribute transaction execution.

## 3. Hardware Limits

Primary resources:

| Resource | Typical Bottleneck | Initial Remediation |
|---|---|---|
| CPU | High CPU utilization, runnable queues, rising query latency | Query tuning, indexes, concurrency limits, scale up |
| RAM | Cache misses, memory pressure, swap/OOM | Tune memory, reduce concurrency, inspect plans |
| Storage capacity | Disk nearing full, rapid growth | Retention, compression, partition lifecycle, larger storage |
| IOPS/throughput | I/O wait, high latency | Faster storage, query/index tuning, caching |
| Network | Throughput/latency between app and DB | App placement, batching, protocol/pool tuning |
| WAL/archive | High WAL generation or archive backlog | Tune write patterns, storage/archive throughput |
| Recovery | Restore/rebuild takes too long | Backup strategy, standbys, faster storage, smaller recovery scope |

### 3.1. CPU Ceiling

When query execution, index maintenance, vacuum, and concurrent sessions continuously saturate CPU, latency can spike non-linearly. Adding cores helps, though serial queries, lock contention, or skew may not scale proportionally.

### 3.2. Memory Ceiling

RAM serves shared buffers, OS page cache, backend memory, sort/hash operations, and background processes. A setting like work_mem can be allocated multiple times per query across many concurrent sessions; never multiply naively by connection count while ignoring operators and concurrency.

### 3.3. Storage Capacity

Database growth can exceed single-volume capacity, backup windows, or restore windows long before the server runs out of CPU. Account for table/index bloat, WAL, temp files, snapshots, and backup copies.

### 3.4. Storage Latency and Throughput

A workload may be gated by random I/O, sequential throughput, or fsync latency. Adding CPU will not fix a storage bottleneck.

### 3.5. Network Ceiling

Applications far from the database or issuing excessive round trips can become network-latency bound. Distributing the database can worsen latency if each request must hit multiple nodes.

## 4. Architectural and Concurrency Limits

Even when more CPU or RAM can be added, certain workloads hit walls imposed by how data and transactions are structured.

### 4.1. Write Serialization

Heavy writes targeting the same rows, hot counters, hot index pages, or narrow key ranges create contention. Adding nodes will not split load if every transaction still updates the exact same logical record.

### 4.2. Lock Contention

A long transaction can block many requests. DDL, row locks, advisory locks, and table-level locks create queues. Sharding only helps if contention cleanly partitions along shard boundaries.

### 4.3. Hot Rows and Hot Keys

Consider a row storing a global inventory counter or a massive single tenant. Even across 100 shards, every request piles onto the same shard/key if the partition key does not distribute the hot workload.

### 4.4. The WAL Pipeline

Writes are logged to WAL for durability, recovery, and replication. A single primary has limits on WAL generation rate, fsync throughput, checkpoints, and downstream replay speed.

### 4.5. Vacuum and Transaction Horizons

Long-running transactions, replication slots, or idle-in-transaction sessions hold back xmin, blocking dead-tuple cleanup and driving table/index bloat. Distribution does not automatically eliminate transaction-lifecycle hygiene issues.

## 5. Why "Big Database" Alone Never Proves Sharding Is Needed

A multi-terabyte database can run smoothly on a properly sized instance if the workload consists mostly of indexed lookups and bounded scans. Conversely, a tiny database can buckle under thousands of concurrent writes to the same rows or pathological query plans.

Measure:
- Request rate and transaction mix.
- Read/write ratio.
- Query p50/p95/p99 latency.
- CPU utilization and run queue depth.
- Storage latency, IOPS, and throughput.
- Cache hit ratios and read patterns.
- Lock waits and deadlocks.
- Connections and pool wait times.
- WAL generation rate and replication lag.
- Table/index growth and bloat.
- Vacuum progress and oldest transaction age.
- Backup and restore durations.

### 5.1. Row Count Is Not a Capacity Metric

One billion rows reveals little about CPU demand on its own. Row width, indexes, access patterns, selectivity, cache locality, and concurrency determine true cost.

### 5.2. Database Size Does Not Equal Active Working Set

A 5 TB cluster whose hot working set is 50 GB may fit comfortably in memory and moderate storage. A 500 GB cluster whose working set exceeds RAM under heavy random access can become severely I/O-bound.

### 5.3. Peak Matters More Than Daily Average

Capacity must handle peak traffic, batch jobs, maintenance, and burst traffic. A 30% daily average CPU does not prevent an outage during peak bursts.

### 5.4. Forecast Horizon

Project capacity over a 6–18 month horizon or aligned product cycle. Prepare sharding early enough to leave migration runway, yet avoid triggering it on an unsubstantiated forecast.

## 6. Scale Up: Vertical Scaling

Scaling up adds resources to a single node:
- More CPU cores.
- More RAM.
- Faster/larger storage.
- Higher network bandwidth.
- Larger instance class.

### 6.1. Advantages

Applications continue connecting to a single database endpoint. No shard routing, distributed joins, or cross-shard transactions are needed. Transactions and SQL semantics remain centralized within one cluster.

### 6.2. Limitations

Costs for top-tier instances rise steeply. Instance classes, storage throughput, and maintenance windows have hard limits. One large node also remains a single failure domain without HA.

### 6.3. Scale Up May Be the Best Move

If the bottleneck is CPU/RAM/I/O and the workload does not require regional locality, scaling up is substantially simpler than distributing.

### 6.4. Benchmark Before Changing Instance Classes

Use a representative workload and track query plans, cache warmth, I/O latency, memory headroom, and failover behavior. Never compare core counts alone.

## 7. Scale Out: Horizontal Scaling

Scaling out adds nodes and distributes reads, writes, or data across them.

Common patterns:
- Read replicas for reads.
- Sharding/partitioning across nodes for data distribution.
- Distributed SQL/database layers.
- Application-level routing.
- Managed distributed PostgreSQL-compatible services.

### 7.1. Scaling Out Reads

Multiple replicas serve read queries independently. Applications must handle replication lag and stale reads.

### 7.2. Scaling Out Writes

Writes must be routed across shards/keys or handled by a distributed transaction layer. Standard read replicas do not accept independent writes.

### 7.3. Data Placement

Every row or table needs an authoritative home. Routing must locate the owning node and handle queries lacking a shard key.

### 7.4. Cross-Node Work

Joins, aggregates, transactions, and ordering spanning multiple shards require network round trips, coordinator execution, or application-level orchestration.

## 8. Distinguishing HA from Horizontal Scaling

High availability (HA) minimizes downtime when a node fails. Horizontal scaling increases capacity or locality. An architecture may achieve one, both, or neither well.

| Mechanism | Primary Goal | Increases Write Capacity? | Increases Read Capacity? |
|---|---|---:|---:|
| Primary + standby | Failover/availability | Not significantly | No when standby is idle/warm |
| Read replicas | Read offload | No for primary writes | Yes |
| Single-cluster partitioning | Manageability/pruning | Does not add write nodes | Can reduce per-query work |
| Sharding | Split data/write load | Yes if workload partitions cleanly | Yes |
| Multi-primary | Multiple write endpoints | Possibly, depending on conflict/consistency model | Yes |
| Distributed SQL | Distribute data/transactions | Yes by design | Yes |

### 8.1. Streaming Replication

Physical streaming replication ships WAL from primary to standby. The standby stays in recovery/read-only mode and cannot accept independent writes like a second primary.

### 8.2. Failover

When the primary fails, a standby is promoted per HA procedures. This transfers roles rather than splitting steady-state writes across two nodes.

### 8.3. Read Replicas

Replicas receive changes from the primary and serve reads. They do not give the primary extra CPU for write execution.

### 8.4. Multi-Primary Is Not Core PostgreSQL Default

Multi-writer setups require external extensions/tools or distributed SQL engines. Evaluate conflict resolution, global ordering, sequences, DDL, and transaction guarantees carefully.

## 9. Read Replicas: A Solution for Read-Heavy Workloads

When workloads are predominantly reads, replicas relieve pressure on the primary.

### 9.1. Classifying Queries

- Strongly consistent reads: must read immediately after a write on the primary.
- Eventual/stale-tolerant reads: tolerate replication lag.
- Analytics/reporting: can run on a replica or warehouse.
- Session-consistent reads: must observe prior writes made by the same session.

### 9.2. Replica Lag

Asynchronous replication means a replica may trail behind WAL replay. A query run right after a write might not yet see the new row on a replica.

### 9.3. Read-After-Write Routing

Applications can route post-write reads to the primary for a window, or use consistency tokens/LSN-aware routing when supported.

### 9.4. Do Not Spread Every Read Blindly

Health checks, metadata lookups, transactions, and strict-consistency reads often belong on the primary. Routing policies should match query class and consistency SLAs.

## 10. Partitioning Within a Single PostgreSQL Cluster

Declarative partitioning divides one logical table into multiple physical partitions inside the same PostgreSQL cluster.

Monthly partitioning example:

```sql
CREATE TABLE public.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE public.events_2026_11
PARTITION OF public.events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE public.events_2026_12
PARTITION OF public.events
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
```

### 10.1. Partitioning Is Not Sharding

Partitions remain inside one cluster, sharing the same primary, CPU, RAM, WAL, and failure domain. Partitioning alone does not spread data across servers.

### 10.2. Partition Pruning

The planner skips irrelevant partitions using the partition key, reducing scanned data.

### 10.3. Lifecycle Management

Detaching/dropping old partitions is vastly faster than deleting millions of rows, simplifying retention and archival.

### 10.4. The Partition Key Determines Effectiveness

Queries must filter on the partition key for pruning to trigger. Partitioning on a column absent from query predicates rarely helps performance.

## 11. When Does Partitioning Help and When Doesn't It?

Partitioning helps when:
- Tables are very large and queries consistently filter by the partition key.
- Data follows a clear time-based lifecycle.
- Old ranges must be dropped or archived rapidly.
- Oversized indexes need to be broken into smaller per-partition indexes.
- Maintenance must run per partition.

Partitioning helps little when:
- Queries routinely scan all partitions.
- Tables are small.
- Workloads do not filter on the partition key.
- Excessive partition counts add planning and metadata overhead.
- The bottleneck is hot rows, CPU-heavy query logic, or networking.

### 11.1. Unique Constraints

PostgreSQL partitioned tables enforce constraints/unique index rules tied to the partition key and version. Design primary/unique keys to include the partition key.

### 11.2. Foreign Keys and Partitioning

Foreign-key support on partitioned tables has expanded across major releases, though exact capabilities and operational implications must be verified for your version.

### 11.3. Partition Count

Too many partitions inflate planning time, catalog size, and maintenance overhead. Choose granularity based on data volume and query patterns.

### 11.4. Partitioning Does Not Scale Single-Primary Writers

It can reduce per-query work and streamline data lifecycles, but every write still lands on the same cluster.

## 12. What Is Sharding?

Sharding splits a logical dataset across multiple independent database shards. Each shard holds a subset of data and usually runs its own primary and replicas.

Tenant-based sharding example:

```text
Application
    |
    v
Shard router
    |
    +-- tenant_id 1..1000  ----> Shard A
    |
    +-- tenant_id 1001..2000 -> Shard B
    |
    +-- tenant_id 2001..3000 -> Shard C
    |
    +-- tenant_id 3001..4000 -> Shard D
```

### 12.1. Data Ownership

Each key, range, or tenant maps to one shard. The router must know the authoritative owner for each dataset.

### 12.2. Independent Capacity

Each shard has dedicated CPU, RAM, storage, and WAL. Adding shards increases aggregate capacity when load distributes evenly.

### 12.3. Local Transactions

Transactions touching only one shard preserve standard PostgreSQL ACID semantics on that shard.

### 12.4. Cross-Shard Operations

Queries or transactions spanning multiple shards require orchestration, distributed transaction protocols, or application-level aggregation. This is where complexity spikes sharply.

## 13. The Shard Key Is a Pivotal Architectural Decision

The shard key governs data placement and request routing.

Common choices:
- tenant_id/customer_id.
- user_id/account_id.
- Geographic region.
- Hash of an entity ID.
- Time range or composite key.

### 13.1. High Cardinality

The key needs enough distinct values to distribute data. A key with only a handful of values yields poor shard distribution.

### 13.2. Query Locality

Records commonly read and written together should live on the same shard. If transactions typically touch orders, order_items, and payments for one tenant, tenant_id is often a strong candidate.

### 13.3. Even Distribution

The shard key must balance both storage and request rate, not merely row counts. A shard with few rows yet massive traffic is still a hot shard.

### 13.4. Immutability

An immutable shard key avoids migrating records across shards. Frequently mutating shard keys complicate routing and transactions.

### 13.5. Avoid Hot Keys

One oversized tenant, a hot region, or a global counter can overload a single shard. Plan for skew and shard splitting.

## 14. Tenant-Based Shard Keys

Tenant-based sharding fits SaaS platforms where data and transactions stay mostly scoped within a single tenant.

Advantages:
- Tenant requests route to a single shard.
- Intra-tenant joins stay local.
- Backups, restores, or exports for a tenant can be isolated.
- Tenant/regional data residency is straightforward.

Risks:
- One tenant grows far larger than others.
- Migrating tenants between shards.
- Global analytics require fan-out.
- Cross-tenant unique constraints require special design.
- Queries lacking a shard key trigger scatter-gather.

### 14.1. Tenant Directory

A metadata service or table maps tenant_id to its shard. Implement caching, versioning, and consistency rules during shard moves.

### 14.2. Large Tenant Isolation

Massive tenants can receive dedicated shards while smaller tenants share multi-tenant shards.

### 14.3. Tenant Affinity

All tables belonging to a tenant should share the same placement key to minimize cross-shard joins and transactions.

### 14.4. Global Identities

Globally unique IDs can use UUIDs, composite keys, or centralized/range ID allocation. Local sequences on each shard do not guarantee global uniqueness.

## 15. Hash Sharding vs. Range Sharding

| Strategy | Advantages | Drawbacks |
|---|---|---|
| Hash | More uniform distribution when keys are uniform | Range scans and fan-out are harder |
| Range | Strong range queries and locality | Hot ranges and uneven growth |
| Tenant mapping | Clear transaction locality | Skew from tenant size/traffic |
| Geographic | Data locality and residency | Regional imbalance and cross-region operations |
| Composite | Balances multiple goals | More complex routing and maintenance |

### 15.1. Hash

Hash the key and map to a shard. Great for point lookups and uniform spread, though range queries may require fan-out.

### 15.2. Range

Partition by key or time intervals. Range queries hit fewer shards, yet sequential inserts can create a hot tail shard.

### 15.3. Consistent Hashing

Consistent hashing minimizes key movement when node counts change, though it requires managing virtual nodes/ring metadata and hot partitions.

### 15.4. There Is No Perfect Shard Key

Select keys based on transaction boundaries, query patterns, data growth, tenant distribution, compliance, and migration costs.

## 16. Cross-Shard Queries and Scatter-Gather

When a query omits the shard key or needs global results, the router dispatches the query to multiple shards, collects results, and merges them.

### 16.1. Scatter

Send the query to relevant shards or all shards.

### 16.2. Gather

Pull rows or partial aggregates back to the coordinator/application.

### 16.3. Cost

Network transfer, remote execution, tail-shard skew, and coordinator memory can make queries much slower than on a single cluster.

### 16.4. Aggregation Correctness

SUM/COUNT/MIN/MAX combine cleanly with proper rules, while AVG requires combining SUM and COUNT; percentiles, DISTINCT, and ordering are trickier. Never combine partial aggregates with broken semantics.

### 16.5. Pagination

Cross-shard ORDER BY/LIMIT requires a global merge. Large OFFSETs become very expensive; cursor/keyset pagination should be built around global sort keys.

## 17. Distributed Transactions and Consistency

Single-shard transactions are far simpler than multi-shard transactions.

### 17.1. Single-Shard Transactions

When all modified rows live on one shard, a standard PostgreSQL transaction maintains local atomicity.

### 17.2. Cross-Shard Atomicity

Committing across multiple shards as one unit requires a distributed transaction protocol like two-phase commit (2PC) or orchestration/sagas. Not every sharding framework supports identical guarantees.

### 17.3. Two-Phase Commit

2PC adds prepare and commit phases. It adds coordination overhead, can leave prepared transactions lingering if the coordinator fails, and requires operational recovery runbooks.

### 17.4. Sagas

Sagas break a business transaction into local transactions with compensating actions. They support long workflows but are not equivalent to a single atomic PostgreSQL rollback.

### 17.5. Eventual Consistency

Some systems tolerate delayed propagation of updates. Applications must define stale-read tolerance, retries, duplicate handling, and conflict semantics.

## 18. The Network Is Part of the Transaction

On one node, operations leverage shared memory and local disks. In a distributed architecture, remote calls incur network latency and can fail independently.

### 18.1. Partial Failure

One shard may respond while another times out. Fan-out queries need deadlines, cancellation, and a partial-result policy.

### 18.2. Retries

Retrying a remote write can execute the mutation twice if the reply drops after commit. Use idempotency keys or deduplication.

### 18.3. Clock Differences

Never rely on wall-clock timestamps across multiple nodes for global total ordering. Use database commit positions, logical clocks, or domain ordering mechanisms as required.

### 18.4. Network Partitions

During network splits, consistency vs. availability tradeoffs become acute. Applications must know which node is authoritative and when to fail closed.

## 19. Citus and Distributed PostgreSQL

Citus is a PostgreSQL extension/distributed database technology using a coordinator and worker nodes to distribute tables by distribution key and execute distributed queries within supported bounds.

### 19.1. Coordinator

The coordinator receives SQL, resolves shard placements, and orchestrates execution.

### 19.2. Worker Nodes

Workers store shards and execute distributed query fragments.

### 19.3. Distributed Tables

Tables are sharded by distribution key; co-located tables keep rows sharing the same key on the same worker to localize joins and transactions.

### 19.4. Reference Tables

Small lookup tables can be replicated to all workers to simplify joins with distributed tables. Understand replication/update semantics and storage overhead.

### 19.5. Compatibility and Limitations

Never assume every PostgreSQL feature, extension, DDL command, or query pattern behaves identically to a single-node cluster. Check version-specific support matrices, managed offerings, and migration requirements.

## 20. Application-Level Sharding

Application-level sharding puts shard placement and connection routing directly into application or service code.

### 20.1. Advantages

- Explicit control over routing.
- Can use standard standalone PostgreSQL instances.
- Tunable per domain or tenant.
- Minimal coupling to specialized distributed extensions.

### 20.2. Drawbacks

- Every service must understand routing rules.
- Cross-shard joins and transactions are difficult.
- Schema migrations must run across all shards.
- Rebalancing and tenant moves require custom tooling.
- A routing bug can read from or write to the wrong shard.

### 20.3. Shard Map

Store mappings from shard keys/ranges/tenants to connection endpoints. Version and cache mappings, and handle cache invalidation during shard moves.

### 20.4. Connection Management

Each shard maintains its own connection pools or pooled routing. Total connections multiply with shard count and application instances.

## 21. Foreign Data Wrappers Do Not Turn PostgreSQL into a Sharded Database

PostgreSQL FDWs such as postgres_fdw enable querying remote tables via foreign tables.

### 21.1. Federation

You can query multiple remote databases from one local server in certain workflows.

### 21.2. Pushdown

Certain predicates, projections, and joins can be pushed to the remote server. Pushdown capability depends on the query, FDW, and PostgreSQL version.

### 21.3. Distributed Transaction Semantics

Do not assume cross-server FDW operations automatically carry the same atomicity and consistency as a local transaction. Inspect remote transaction behavior and failure handling.

### 21.4. Routing and Rebalancing

FDWs do not provide a complete shard map, automated rebalancing, global uniqueness, or a full distributed query optimizer for arbitrary workloads.

## 22. Distributed SQL and PostgreSQL-Compatible Systems

Some distributed SQL databases offer a SQL interface or PostgreSQL wire-protocol compatibility while differing internally from single-node PostgreSQL.

Evaluate:
- SQL compatibility and unsupported features.
- Transaction isolation and consistency guarantees.
- DDL and schema-change behavior.
- Index types and extensions.
- Query planner and execution behavior.
- Sequences and identity behavior.
- Replication and failure semantics.
- Operational tooling and backups.
- Vendor lock-in and portability.
- Cross-region latency.

### 22.1. Wire Compatibility Is Not Full Semantic Compatibility

A client may connect over the PostgreSQL wire protocol even when the server lacks full PostgreSQL SQL behavior or extension support.

### 22.2. Distributed Transactions Carry Overhead

Strong consistency across nodes typically requires consensus/coordination, replication, and network round trips.

### 22.3. Benchmark Against Your Real Application

Run migrations, ORM test suites, transactional workloads, and failure drills. Never choose a platform based solely on a synthetic microbenchmark.

### 22.4. Exit Strategy

Define how to export data/schemas and return to standard PostgreSQL if the platform ceases to fit.

## 23. Replication Is Not Sharding

Replication keeps multiple copies of the same data. Sharding splits data into distinct subsets.

| Characteristic | Replication | Sharding |
|---|---|---|
| Data | Identical or near-identical copies | Each shard holds a subset |
| Goal | HA / read availability | Capacity / locality |
| Write path | Usually one primary for physical replication | Writes route to the owning shard |
| Read routing | Any eligible replica | Shard(s) holding the target data |
| Failure | Promote replica or rebuild | Shard loss impacts a subset; requires replica/restore |
| Cross-node queries | Replicas hold the full dataset | Requires fan-out/aggregation |

### 23.1. Replicas Do Not Partition Storage

Each replica stores a full copy of the cluster. Total disk footprint grows, while each node still carries the entire replicated dataset.

### 23.2. Each Shard Needs Its Own Replication for HA

Each shard can have a primary and standby. Sharding and replication are usually paired: shards partition data, while replicas protect each shard.

### 23.3. Logical Replication Serves Different Use Cases

Logical replication selectively copies tables/changes for migrations or integrations. It does not automatically provide transparent horizontal sharding.

### 23.4. Partitioned Tables Are Not Distributed Tables

Partitioning inside a single cluster differs fundamentally from placing distributed partitions across worker nodes.

## 24. When Should You Stay on Single-Node PostgreSQL?

A single node is generally appropriate when:
- Bottlenecks have not been measured or queries/schemas still have clear optimization headroom.
- Workloads fit comfortably within available instance capacity.
- Transactions frequently span multiple tables requiring strict atomicity.
- Joins and reports routinely scan across the full dataset.
- No natural shard key exists.
- Data growth and recovery objectives remain achievable.
- The team lacks operational maturity to run multi-node databases.
- Distributed architecture costs outweigh expected gains.

### 24.1. Optimize First

Inspect slow queries, indexes, statistics, vacuum health, connection pooling, N+1 queries, caching, and data retention.

### 24.2. Isolate Workloads

Offloading analytics/ETL to a warehouse or reporting replica relieves the primary without sharding OLTP.

### 24.3. Scale Instance and Storage

Scaling up buys runway with minimal operational complexity.

### 24.4. Define Capacity Triggers

Establish thresholds for CPU, I/O, storage, latency, replication lag, and restore time to kick off scale-out work well before hitting a hard ceiling.

## 25. Signals to Consider Distribution

Consider distributed data when evidence shows:
- A single node hits CPU/RAM/IOPS ceilings even after query and schema tuning.
- Required write throughput exceeds the largest purchasable primary class.
- Dataset or working set outgrows storage or recovery time limits.
- Workloads partition naturally by tenant/region/entity with minimal cross-shard transactions.
- Data residency laws require storing data across multiple regions.
- Read replicas and caching fail to address the primary bottleneck.
- Growth forecasts exceed instance headroom within your planning horizon.
- Operational requirements demand independent scaling by domain or tenant.

### 25.1. Hard Limits vs. Brief Spikes

A few minutes of traffic spikes can often be absorbed by application queueing or autoscaling. Distributed databases are long-term commitments requiring sustained, measured bottlenecks.

### 25.2. Marginal Cost

If a larger instance still meets SLAs at reasonable cost, sharding may be uneconomical.

### 25.3. Independent Scaling

When one tenant or domain grows disproportionately, isolating placement allows independent scaling—after checking shared dependencies.

### 25.4. Geographic Locality

When users and data span continents, local reads/writes cut latency, at the price of harder multi-region consistency and failover.

## 26. Signs of Distributing Too Early

Avoid sharding solely because:
- A table holds hundreds of millions of rows while queries are still fast.
- You want to "future-proof" without concrete forecasts.
- A dashboard spikes CPU due to an unfixed query regression.
- Connection counts are high simply because a pooler isn't configured.
- One heavy report could simply move to a replica or warehouse.
- Retention tables just need time-based partitioning and dropping.
- The team lacks automated backups, monitoring, and recovery for even a single cluster.
- No clear shard key exists and most transactions cross shards.

### 26.1. Complexity Tax

Every shard multiplies migrations, monitoring, credentials, backups, restores, failovers, connection pools, and incident paths.

### 26.2. Debugging Tax

A single request can span multiple nodes, trace/correlation IDs, and partial failures.

### 26.3. Development Tax

Local and test environments must simulate shard maps and cross-shard edge cases. CI may need multiple database instances.

### 26.4. Hiring and Operations Tax

The team needs operational expertise in multi-cluster management, rebalancing, distributed transactions, and incident response.

## 27. Bottleneck-Based Decision Framework

| Primary Bottleneck | Try First | Consider Next |
|---|---|---|
| Slow queries | EXPLAIN, indexes, query rewrites, ANALYZE | Read replica/warehouse if workload is distinct |
| CPU saturated | Query tuning, concurrency limits, scale up | Shard if writes/CPU partition cleanly |
| Read-heavy | Caching, replicas, reporting offload | Distributed read architecture |
| Write-heavy | Batching, hot-row redesign, index/tx tuning | Sharding or distributed SQL |
| Storage growth | Retention, compression, partitioning, larger volumes | Shard by tenant/time if operationally sound |
| I/O bound | Storage tier, caching, query/index tuning | Split independent workloads/datasets |
| Lock contention | Shorter transactions, lock ordering, DDL discipline | Shard only if contention partitions cleanly |
| Slow recovery | Backup/PITR/restore tuning, standbys | Smaller failure domains / shard-level recovery |
| Geographic latency | App placement, regional read replicas/caches | Regional data placement/distribution |

### 27.1. One Bottleneck Can Have Many Causes

CPU saturation can stem from bad query plans, too many connections, vacuum, encryption, heavy JSON processing, or burst traffic. Diagnose root causes before changing architecture.

### 27.2. Distribute Only Distributable Bottlenecks

If all writes update a single global row, sharding unrelated tables will not fix that hot row.

### 27.3. Scaling Out Is Not Free

Aggregate capacity may grow, while individual requests may incur extra network hops or coordinator aggregation.

### 27.4. Compare Cost per Transaction

Include database instances, networking, storage, backups, observability, engineering effort, and on-call burden.

## 28. Evaluating Shard Key Viability

Assess any candidate shard key with these questions:
1. How many distinct keys exist?
2. How are rows distributed across keys?
3. How are requests and writes distributed across keys?
4. What percentage of transactions touch a single key?
5. What percentage of queries omit the key?
6. Is the key immutable?
7. Are there global uniqueness requirements?
8. Are there data residency constraints?
9. Are there oversized tenants or hot keys?
10. Can keys or shards be migrated safely?

### 28.1. Data Skew

One shard holding 40% of total data while peers hold 10% causes capacity imbalance.

### 28.2. Traffic Skew

Even row counts with uneven traffic still produce hot shards. Measure requests/sec and write rates per key.

### 28.3. Co-Location

Tables frequently joined or updated together should co-locate on the same distribution key if supported by the framework.

### 28.4. Global Lookups

If many requests arrive with only an email or external ID, maintain a global lookup table/index or secondary mapping. Ensure that mapping stays consistent without becoming a new bottleneck.

## 29. Cross-Shard Constraints and Identity

A single PostgreSQL cluster enforces unique constraints and foreign keys cluster-wide. With sharding, global enforcement becomes hard.

### 29.1. Unique Keys

If a unique constraint omits the shard key, no single shard sees all values across the fleet. Use globally unique IDs or a dedicated uniqueness service/pattern.

### 29.2. Foreign Keys

Cross-shard foreign keys may be unsupported by the framework or require application-level checks. Draw data boundaries so foreign keys stay local.

### 29.3. Sequences

Independent per-shard sequences can generate colliding IDs. Use UUIDs, composite keys, range allocation, or globally coordinated ID generators.

### 29.4. Referential Integrity

When the application enforces references across shards, handle race conditions, retries, and orphan cleanup. Never treat a naive SELECT-then-INSERT as an atomic global constraint.

## 30. Rebalancing and Shard Lifecycle

When adding shards or cooling down an overloaded shard, data must move.

### 30.1. Rebalancing

Move shards, key ranges, or tenants between nodes to balance storage and traffic.

### 30.2. Online Movement

Some systems copy baseline data and stream live changes while the source remains active, then cut over routing. Verify consistency and write fencing.

### 30.3. Routing Metadata

Shard maps need versions or generations. Clients and routers must know when to refresh and avoid writing to the stale owner.

### 30.4. Failures Mid-Migration

Design resumable checkpoints, idempotent copies, conflict handling, and clear source/destination ownership. Never delete source data before verifying the destination.

### 30.5. Splitting a Hot Shard

A hot tenant or key range can be split onto a dedicated shard. Account for cross-tenant/shared rows and key remapping.

## 31. Backup, Restore, and Disaster Recovery for Shards

Sharding complicates recovery scope.

### 31.1. Per-Shard Backups

Every shard requires base backups/PITR or equivalent managed backups. Track coverage and retention across all shards.

### 31.2. Consistent Cross-Shard Snapshots

If cross-shard operations require a consistent restore point, use coordinated or consistent snapshot strategies. Restoring different shards to different timestamps creates inconsistent global state.

### 31.3. RPO and RTO

Set RPO and RTO per shard and system-wide. One shard outage may impact a subset of tenants or the whole application depending on routing.

### 31.4. Rebuilding Replicas

Each shard may maintain its own HA replicas. Rehearse failovers and replica rebuilds per shard identity.

### 31.5. Global Metadata

Back up shard directories, routing metadata, tenant mappings, schema versions, and credentials/configs alongside shard data. Without metadata, intact data cannot be routed.

## 32. Schema Migrations Across Multiple Shards

A migration must deploy across many clusters or nodes.

### 32.1. Fan-Out Deployment

Runners can apply migrations sequentially or with bounded concurrency. Applying across all shards at once can trigger an I/O and CPU burst.

### 32.2. Version Consistency

Track migration versions on every shard. One shard failing mid-rollout leaves the fleet in a mixed-schema state.

### 32.3. Backward-Compatible Migrations

Applications must stay compatible with both old and new schemas during rolling rollouts. Expand-and-contract patterns are essential.

### 32.4. Per-Shard Locks

Manage migration locks per shard and ensure orchestration knows which shards succeeded or failed.

### 32.5. Resumability

Deployments must resume from failed shards without re-running destructive steps on already-migrated shards.

## 33. Observability for Distributed PostgreSQL

Multi-shard systems need metrics at two levels: per-node and system-wide.

Node-level:
- CPU, RAM, IOPS, storage, WAL.
- Connections, locks, deadlocks.
- Query latency, slow queries.
- Vacuum, bloat, replication lag.
- Backup/restore status.

System-level:
- Requests/s by shard and tenant.
- Fan-out width and remote call latency.
- Hot shards and hot keys.
- Cross-shard transaction counts and durations.
- Router cache misses and stale mappings.
- Rebalance progress.
- Partial failures, timeouts, and retries.
- Schema version divergence.
- End-to-end p95/p99 latency.

### 33.1. Correlation IDs

Attach request/trace IDs to logs and remote shard calls to trace one business request across nodes.

### 33.2. Per-Shard Dashboards

System-wide averages hide an overloaded shard. Display distributions and the worst-performing shard.

### 33.3. Cardinality Control

Do not emit metric labels for every customer ID at high scale. Use top-N views, histograms, and sampled diagnostics.

### 33.4. Alert on Skew

Alert when any shard's storage, CPU, latency, or queue depth diverges beyond thresholds relative to peers.

## 34. Security and Data Residency

Distributing data lets you place records closer to users or within specific jurisdictions, while expanding the operational security surface.

### 34.1. Network Boundaries

Each shard and replica needs explicit network access rules, TLS, credentials, and firewall policies.

### 34.2. Secret Rotation

Routers and services may hold credentials for many shards. Design rotation so it does not drop connections across all nodes simultaneously.

### 34.3. Tenant Isolation

Shard placement does not replace authorization. Applications must still enforce tenant access controls; never trust a client-supplied shard key without validation.

### 34.4. Data Residency

Specify which data must remain in which regions—including backups, WAL archives, replicas, logs, and analytics copies.

## 35. Multi-Region and Latency

Multi-region architectures can lower latency for local users or satisfy residency rules, though network distance impacts transactions.

### 35.1. Regional Primaries

Assigning write ownership by region or tenant keeps local writes fast, while cross-region queries and transactions incur remote latency.

### 35.2. Synchronous Cross-Region Replication

Can add substantial commit latency because every commit awaits remote network acknowledgment. Balance RPO/consistency against latency.

### 35.3. Asynchronous Replication

Reduces commit latency, but risks losing the most recent writes when failing over to a replica that has not yet received or replayed all WAL, depending on the failure scenario.

### 35.4. Global Transactions

Transactions updating multiple regions require heavy coordination and failure policies. Design workflows to localize transactions whenever possible.

## 36. Measuring Workloads Before Distributing

Capture a baseline including at least:
- Peak TPS / queries per second.
- Read/write ratio.
- p50/p95/p99 latency.
- Concurrent active sessions.
- CPU utilization and run queue.
- Memory and cache behavior.
- Storage latency, throughput, and IOPS.
- WAL bytes per second.
- Replica lag.
- Lock wait times.
- Top queries by total time and call count.
- Largest/hottest tables and tenants.
- Weekly/monthly growth rates.
- Backup and restore durations.

### 36.1. pg_stat_statements

Use pg_stat_statements to identify query families driving high total execution time, call volume, or temp I/O.

### 36.2. pg_stat_activity

Use it to inspect active sessions, wait events, and transaction ages during incidents.

### 36.3. OS and Cloud Metrics

Database views do not replace host, storage, or network metrics. Combine provider telemetry with OS-level metrics.

### 36.4. Representative Load Tests

Replay or generate workloads with realistic data skew and concurrency. Uniform synthetic keys often miss hot-tenant bottlenecks.

## 37. Capacity Model and Growth Forecasts

Capacity forecasts should account for:
- Data growth.
- Index growth.
- WAL and archive growth.
- Backup storage.
- Active working set.
- Peak concurrency.
- Read/write mix.
- Per-tenant growth and skew.
- Maintenance overhead.
- Recovery and rebuild headroom.

### 37.1. Headroom

Never operate continuously at 95–100% resource utilization. Leave headroom for traffic bursts, vacuum, index builds, failovers, and organic growth.

### 37.2. Growth Rates

Use real historical trends, seasonality, and product roadmaps. Never extrapolate one anomalous week into an annual growth rate.

### 37.3. Restore Capacity

A single node might run production fine, yet restoring 10 TB within your required RTO may be impossible. Recovery time is a real capacity dimension.

### 37.4. Scale Triggers

Examples include p99 latency persistently breaching SLO, storage headroom dropping below threshold, sustained replica lag growth, or projected capacity crossing instance ceilings within the planning horizon. Base triggers on measured baselines.

## 38. Try Simpler Solutions Before Sharding

A practical sequence of investigation:

1. Eliminate N+1 queries and excessive round trips.
2. Run EXPLAIN (ANALYZE, BUFFERS) on top queries.
3. Add or tune indexes.
4. Run ANALYZE and fix stale statistics.
5. Shorten transactions and standardize lock ordering.
6. Deploy connection pooling and cap concurrency.
7. Add caching for appropriate read paths.
8. Offload reports/analytics to replicas or a warehouse.
9. Partition tables by access and lifecycle patterns.
10. Scale up instance CPU, RAM, and storage.
11. Split workloads/databases by domain where coupling is low.
12. Only then evaluate sharding/distributed SQL if remaining bottlenecks suit distribution.

### 38.1. Optimize SQL First

Full-table scans or bad joins overload even small databases. Sharding complicates every query without fixing broken query logic.

### 38.2. Connection Pooling

One backend process per connection carries memory and scheduling overhead. PgBouncer or platform pooling reduces connection churn and memory pressure.

### 38.3. Caching

Caching cuts database reads, though it introduces invalidation, TTL, consistency, and stampede-protection requirements.

### 38.4. Workload Isolation

Separating analytics, ETL, and reporting often delivers larger gains than sharding OLTP.

## 39. Example: Multi-Tenant SaaS

A SaaS platform serves 20,000 tenants. Each tenant owns users, orders, invoices, and audit events.

### 39.1. Starting on One Node

Include tenant_id in keys, indexes, and foreign keys. While workload fits within capacity, keep a single cluster.

### 39.2. Read Replicas

Route stale-tolerant dashboards/reporting to replicas; keep critical transactional reads on the primary.

### 39.3. Partitioning

Partition audit/events tables by time for retention and query pruning.

### 39.4. Sharding by Tenant

Once the primary hits write or storage ceilings, tenant_id is a strong shard key because most transactions stay scoped to one tenant.

### 39.5. Tenant Skew

A handful of enterprise tenants may generate the bulk of traffic. Place them on dedicated shards or prepare a split strategy.

### 39.6. Cross-Tenant Reporting

Send system-wide analytics to a warehouse/CDC pipeline rather than fanning OLTP queries across all shards.

## 40. Example: Events and Time-Series Systems

An application ingests billions of time-ordered events.

### 40.1. Time-Based Partitioning

If queries mostly target time windows and retention, single-node time partitioning can sustain long-term growth.

### 40.2. Retention

Detach, archive, or drop aged partitions per policy. Avoid retaining full event history on the OLTP primary unless required by the business.

### 40.3. Sharding by Tenant/Device/Time

If ingest throughput surpasses one primary, shard by tenant/device hash or region. Preserve event ordering and query locality.

### 40.4. Analytics

Event data typically suits CDC/ETL into an analytical store. Avoid running full scans on the OLTP primary.

## 41. Example: Global Applications

An application serves users across multiple regions with strict low-latency goals.

### 41.1. Local Read Caches and Replicas

Start with regional caches or read replicas if stale reads are acceptable.

### 41.2. Data Residency

If records must reside in specific regions, tenant/region placement becomes the shard key or database boundary.

### 41.3. Local Writes

If each tenant has a home region, route writes to that regional primary/shard owner.

### 41.4. Cross-Region Workflows

Payments, inventory, and global accounts may need complex coordination and consistency. Design sagas or centralized ownership rather than assuming local transaction semantics.

## 42. Migrating from Single-Node to Sharded Architecture

A migration plan should follow these steps:

1. Identify the workload bottleneck and business objective.
2. Select data ownership boundaries and shard key.
3. Inventory tables, foreign keys, transactions, and queries.
4. Establish global IDs and uniqueness rules.
5. Design the shard map and routing layer.
6. Choose a framework or platform.
7. Rehearse schema migrations across multiple shards.
8. Perform initial data copy.
9. Stream changes continuously during the migration window.
10. Validate row counts, checksums, and business invariants.
11. Cut over reads/writes by tenant or key range.
12. Monitor hot shards, errors, and latency.
13. Maintain a rollback/reconciliation plan.
14. Rebalance and scale based on live metrics.

### 42.1. Dual-Write Risks

Writing simultaneously to old and new databases risks partial success. When dual-writing is necessary, use outbox/CDC, idempotency, and reconciliation rather than uncoordinated independent writes.

### 42.2. Backfill

Copy by key range or batch with checkpoints. Avoid overloading the old primary while it serves live traffic and exports data.

### 42.3. Cutover

Briefly freeze writes or use CDC catch-up to establish a clean consistency point. Update routing metadata atomically and with versioning.

### 42.4. Rollback

Once new shards accept live writes, rolling back to the old node requires reverse sync and reconciliation. Simply flipping endpoints back risks losing newly written data.

## 43. Failure Scenarios in Distributed Architectures

Test these scenarios:
- One shard unreachable.
- Excessive replica lag.
- Coordinator/router restart.
- Network timeout after write commit.
- One shard runs out of disk.
- Migration succeeds on only a subset of shards.
- Rebalancing interrupted mid-flight.
- Stale global metadata.
- Hot shard exceeding capacity.
- Backup/restore of a single shard.
- Cross-shard transaction prepared before coordinator dies.

### 43.1. Partial Availability

Decide whether to keep serving tenants on healthy shards or fail the entire service. The business contract must be explicit.

### 43.2. Idempotent Retries

A timeout never tells you whether a write committed. Use operation IDs and unique constraints scoped within the shard.

### 43.3. Circuit Breakers

Prevent routers from flooding a failing shard and building unbounded queues.

### 43.4. Recovery Ownership

Define who is authorized to promote replicas, repair shard maps, replay changes, or resume rebalancing.

## 44. Distributed Anti-Patterns

- Sharding before measuring bottlenecks.
- Picking a shard key simply because it is convenient in code.
- Picking a key with even row distribution yet severe traffic skew.
- Letting most queries become scatter-gather.
- Running frequent cross-shard transactions.
- Turning global counters or uniqueness checks into a central bottleneck.
- Using asynchronous replication while assuming strong consistency.
- Routing read-after-write traffic to replicas without consistency policies.
- Lacking shard map versioning.
- Lacking rebalancing tooling.
- Running migrations on only one shard.
- Backing up individual shards without a consistent recovery plan.
- Ignoring per-shard metrics.
- Performing non-idempotent dual writes.
- Lacking a tenant/data migration path.
- Treating FDWs as if they automatically guarantee distributed ACID transactions.
- Confusing single-cluster partitioning with sharding.
- Confusing HA replicas with write scaling.
- Failing to test partial failures and retry behavior.
- Ignoring engineering and on-call operational costs.

## 45. Decision Checklist

Before committing to sharding or distributed data, answer:

| Question | Required Evidence |
|---|---|
| What is the bottleneck? | Metrics and query analysis |
| Have queries/schemas been optimized? | EXPLAIN plans, index review, load tests |
| Is scaling up still viable? | Instance/storage options and costs |
| Are read replicas/caches sufficient? | Read/write split and consistency analysis |
| Would partitioning solve it? | Partition pruning/lifecycle evaluation |
| Does the workload have a natural shard key? | Query and transaction access patterns |
| How frequent are cross-shard transactions? | Transaction tracing |
| What do data/traffic skew look like? | Per-tenant/key distributions |
| What global uniqueness is needed? | ID and constraint design |
| Does recovery meet RTO/RPO? | Restore and failover rehearsals |
| Can the team operate it? | Runbooks, staffing, automation |
| Is total cost justified? | TCO per request/transaction |
| Can the migration roll back safely? | CDC/reconciliation/failback plan |
| Is multi-region truly required? | Latency and residency requirements |

## 46. Practice Exercises with Answers

### Exercise 1. What is single-node PostgreSQL?

**Answer:** A PostgreSQL cluster running on a single host or instance, typically with one primary handling writes and optional separate standbys/replicas.

### Exercise 2. Do multiple databases in the same cluster get independent CPU partitions?

**Answer:** No. They share host and cluster resources.

### Exercise 3. What is scaling up?

**Answer:** Increasing CPU, RAM, storage, or network capacity on a single node.

### Exercise 4. What is scaling out?

**Answer:** Adding nodes and distributing reads, writes, or data across multiple nodes.

### Exercise 5. Must a large database always be sharded?

**Answer:** No. Evaluate workload, working set, query patterns, hardware headroom, and recovery requirements.

### Exercise 6. Why does peak load matter more than daily average?

**Answer:** Capacity must withstand bursts, batch jobs, and peak concurrency; averages mask overload.

### Exercise 7. Do read replicas increase write throughput on the primary?

**Answer:** No. They offload reads; writes still execute on the primary.

### Exercise 8. How do HA and horizontal scaling differ?

**Answer:** HA minimizes downtime on failure; horizontal scaling adds capacity or locality across multiple nodes.

### Exercise 9. Does a physical standby normally accept direct writes like a primary?

**Answer:** No. It replays WAL and stays read-only until promoted.

### Exercise 10. Is partitioning inside a single PostgreSQL cluster the same as sharding?

**Answer:** No. Partitions still share the same cluster and node resources.

### Exercise 11. What is partition pruning?

**Answer:** The planner skips partitions irrelevant to query predicates, reducing scanned data.

### Exercise 12. When is time-based partitioning useful?

**Answer:** When data lifecycles and queries center on time ranges and require fast retention/archiving/dropping.

### Exercise 13. What is sharding?

**Answer:** Splitting a logical dataset into subsets stored across independent database shards.

### Exercise 14. What does the shard key determine?

**Answer:** Data placement, request routing, and how well transactions/queries stay local.

### Exercise 15. Why is tenant_id often a good SaaS shard key?

**Answer:** Most transactions and queries stay within one tenant, co-locating data and minimizing cross-shard work.

### Exercise 16. What is a hot shard?

**Answer:** A shard receiving far more traffic or writes than peers and becoming a bottleneck.

### Exercise 17. How does data skew differ from traffic skew?

**Answer:** Data skew is uneven storage/row distribution; traffic skew is uneven request/write load.

### Exercise 18. What is the benefit of hash sharding?

**Answer:** Fairly uniform key distribution when keys and hashing behave uniformly.

### Exercise 19. What is the benefit of range sharding?

**Answer:** Range queries can hit fewer shards while preserving locality across key ranges.

### Exercise 20. Which range shard can sequential inserts overheat?

**Answer:** The tail range continuously receiving newly generated keys.

### Exercise 21. What is scatter-gather?

**Answer:** Dispatching a query to multiple shards and collecting/merging the results.

### Exercise 22. Why is global ORDER BY/LIMIT harder across shards?

**Answer:** Each shard returns locally sorted rows; the coordinator must merge streams for global top-N.

### Exercise 23. Can AVG be combined by averaging each shard's averages?

**Answer:** No if shard row counts differ. Combine SUM and COUNT across shards and divide afterward.

### Exercise 24. What is a cross-shard transaction?

**Answer:** A transaction modifying data distributed across multiple shards.

### Exercise 25. What are the tradeoffs of 2PC?

**Answer:** Coordinates atomic commits across participants at the cost of extra latency, coordinator dependency, and prepared-transaction recovery.

### Exercise 26. What is a saga?

**Answer:** A workflow of local transactions paired with compensating actions; not equivalent to an atomic global rollback.

### Exercise 27. Why do distributed write retries require idempotency?

**Answer:** Timeouts can happen after a remote commit; blind retries risk executing the operation twice.

### Exercise 28. What query locality does a good shard key need?

**Answer:** Rows frequently read and written together should reside on the same shard.

### Exercise 29. Why are global unique constraints hard in sharding?

**Answer:** No single local index/constraint checks values across every shard automatically.

### Exercise 30. Can per-shard local sequences produce duplicate IDs?

**Answer:** Yes. Use UUIDs, composite IDs, range allocations, or globally coordinated ID strategies.

### Exercise 31. What model does Citus provide?

**Answer:** A coordinator and worker nodes distributing tables/shards by distribution key and executing distributed queries within supported limits.

### Exercise 32. Does postgres_fdw provide a complete sharding framework by itself?

**Answer:** No. It provides foreign-table access and federation, not full automated routing, rebalancing, and global consistency.

### Exercise 33. Does PostgreSQL wire compatibility guarantee full SQL compatibility?

**Answer:** No. Verify semantics, features, extensions, and unsupported operations.

### Exercise 34. Why is multi-primary complex?

**Answer:** It requires conflict resolution, ordering, ID allocation, and transaction consistency across multiple writers.

### Exercise 35. When should you keep a single node?

**Answer:** When workloads fit comfortably within capacity, transactions span many tables, no natural shard key exists, or distributed complexity outweighs benefits.

### Exercise 36. When should you consider sharding?

**Answer:** Once bottlenecks are measured and tuned, a single node cannot meet capacity/SLOs, the workload partitions cleanly by key, and cross-shard work is manageable.

### Exercise 37. Why isn't database size alone enough to decide?

**Answer:** Row width, working set, query mix, concurrency, indexes, and I/O patterns determine actual load.

### Exercise 38. Which bottleneck does connection pooling solve?

**Answer:** Connection churn and backend-process overhead caused by excessive client connections.

### Exercise 39. Where can analytical workloads be offloaded?

**Answer:** Read replicas, data warehouses, or analytical platforms depending on freshness and volume requirements.

### Exercise 40. Why monitor per-shard metrics?

**Answer:** Aggregate averages mask hot shards, storage imbalances, or failing individual nodes.

### Exercise 41. What is rebalancing?

**Answer:** Moving shards, key ranges, or tenants across nodes to equalize capacity and load.

### Exercise 42. Why do shard maps need versioning?

**Answer:** Clients and routers must detect updated mappings and avoid writing to stale shard owners during moves or cutovers.

### Exercise 43. Why don't independent per-shard backups guarantee a consistent global restore?

**Answer:** Shards may be backed up or restored at slightly different instants; cross-shard invariants require coordination.

### Exercise 44. What do multi-shard migrations require?

**Answer:** Orchestrated rollouts, per-shard migration histories/locks, bounded concurrency, resumability, and schema compatibility.

### Exercise 45. How does multi-region synchronous replication affect latency?

**Answer:** Commits wait for distant network acknowledgments, increasing write latency.

### Exercise 46. What risk does asynchronous failover carry?

**Answer:** A standby that has not received or replayed all WAL may be missing the latest writes at failover time.

### Exercise 47. Why are dual writes dangerous?

**Answer:** Two independent writes can leave one succeeding and the other failing; use outbox/CDC, idempotency, and reconciliation.

### Exercise 48. What are signs of premature distribution?

**Answer:** Unmeasured bottlenecks, untapped query/index/pooling/partitioning improvements, and no clear shard key.

### Exercise 49. What should be benchmarked before adopting distributed SQL?

**Answer:** Real workloads, transactions, SQL/extension compatibility, consistency behavior, failure modes, migrations, and recovery.

### Exercise 50. What evidence should back a data distribution decision?

**Answer:** Metrics, growth forecasts, exhausted single-node options, shard-key locality, cross-shard transaction profiles, cost models, team readiness, and tested recovery plans.

## 47. PostgreSQL and Ecosystem References

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/) — architecture, performance, replication, partitioning, and administration.
- [PostgreSQL Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — declarative partitioning within a single cluster.
- [PostgreSQL Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — primary/standby and WAL streaming.
- [PostgreSQL Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publication/subscription and replication scope.
- [PostgreSQL Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — activity, locks, I/O, and replication statistics.
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — query plan analysis.
- [PostgreSQL postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html) — accessing remote PostgreSQL tables.
- [Citus Documentation](https://docs.citusdata.com/) — distributed PostgreSQL, distribution keys, co-located tables, and coordinator/workers.
- [PgBouncer Documentation](https://www.pgbouncer.org/) — connection pooling.
- [PostgreSQL Wiki: Sharding](https://wiki.postgresql.org/wiki/Shard) — sharding approaches in the PostgreSQL ecosystem.

Feature support, transaction guarantees, replication behavior, and deployment options vary by PostgreSQL major version, Citus release, and managed provider. Review compatibility matrices and run failure/recovery drills before deploying a distributed architecture to production.

## 48. Summary: Distribute Only When Bottlenecks and Data Boundaries Are Clear

```text
Measure workload and bottleneck
             |
             v
Optimize SQL / schema / indexes
             |
             v
Pool connections and isolate workloads
             |
             v
Scale up / cache / read replicas
             |
             v
Partition for pruning and lifecycle
             |
             v
Does one node still miss capacity/SLO?
          /             \
        No               Yes
        |                 |
        v                 v
Keep single node     Is there a natural shard key?
and monitor             /          \
                      No            Yes
                      |              |
                      v              v
                Redesign workload  Evaluate sharding /
                or keep centralized distributed SQL
                                      |
                                      v
                           Test transactions, failures,
                           rebalancing, backup and cost
                                      |
                                      v
                                  Cut over
```

Key principles to remember:

1. **Single-node PostgreSQL scales remarkably far.** Measure workloads and optimize before changing architecture.
2. **Database size alone never dictates sharding.** Query mix, working set, concurrency, I/O, and recovery provide the real evidence.
3. **Scale up, replicas, and partitioning solve different problems.** Never confuse HA or read scaling with write sharding.
4. **Read replicas relieve read load, not primary write capacity.**
5. **Single-cluster partitioning does not spread resources across nodes.** It improves pruning and data lifecycle management.
6. **Sharding demands a clear data-ownership key.** Query locality, transaction locality, and traffic distribution dictate success.
7. **Cross-shard joins and transactions multiply complexity.** Design domain boundaries to keep operations local.
8. **Distributed systems must handle partial failures, retries, and consistency.** A network timeout never tells you whether a write committed.
9. **Every shard needs backups, HA, migrations, and observability.** System-wide operations also require global metadata and consistent recovery strategies.
10. **Rebalancing and schema rollouts are ongoing work.** Distribution is never a one-time split.
11. **Factor engineering and on-call effort into TCO.** More nodes mean more failure modes and operational overhead.
12. **Distribute only when a single node can no longer meet requirements and the workload splits cleanly.** Base the move on metrics, forecasts, shard keys, and recovery rehearsals.

**One sentence to remember:** *Scale single-node PostgreSQL to its practical limit; distribute only when bottlenecks are measured, data partitions naturally along a key, and your team is ready to operate consistency, routing, and recovery across multiple shards.*
