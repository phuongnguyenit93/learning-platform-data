# Optimizing Cloud SQL, AlloyDB, and Spanner for Real-World Workloads

An e-commerce application running on Google Cloud may serve a few hundred requests per second on regular days, then jump many times higher during promotional campaigns. The engineering team sees API response times spike from 120 ms to several seconds, database connections surge, CPU climb, and transactions time out. The most common knee-jerk reaction is adding vCPUs or upgrading to a pricier database tier. That can mask symptoms briefly, yet it never fixes an unindexed SQL query, a transaction holding locks too long, or a data key taking concentrated writes.

**Optimizing a database for real-world workloads** is the process of measuring, pinpointing bottlenecks, choosing the smallest effective change, and validating with representative load. On Google Cloud, the three common relational services work differently: **Cloud SQL** provides managed MySQL, PostgreSQL, and SQL Server; **AlloyDB for PostgreSQL** focuses on high-performance PostgreSQL with read pools and specialized acceleration; **Spanner** is a distributed SQL database with key-range partitioning and instance-scale compute.

In the **CLOUD_PROVIDERS_GCP** module, this lesson connects deployment knowledge across Compute Engine, GKE, Cloud Run, IAM, and networking with reliability, performance, and cost analysis. The goal is not merely faster benchmark numbers: the application must meet SLOs under forecasted load at reasonable cost with a rollback-ready change process.

After this lesson, you will be able to:

- Classify workloads across OLTP, read-heavy, write-heavy, reporting, and traffic distribution patterns.
- Build baselines using p50/p95/p99 latency, throughput, CPU, memory, I/O, connections, locks, and cost.
- Use Query Insights and execution plans to distinguish slow queries from insufficient hardware resources.
- Tune connection pooling, timeouts, indexes, transactions, and read routing for Cloud SQL.
- Apply AlloyDB read pools, Index Advisor, and the columnar engine to the right workload types.
- Identify Spanner hotspots, design well-distributed keys, and tune compute/autoscaling.
- Run controlled load tests, calculate cost per successful transaction, and establish production runbooks.

## 1. Comparing the Three Services Before Optimizing

There is no rule that "AlloyDB is always faster than Cloud SQL" or "Spanner is always cheaper at high request volume." Fit depends on schema, read/write ratio, transaction semantics, access regions, and scaling needs.

| Criterion | Cloud SQL | AlloyDB for PostgreSQL | Spanner |
|---|---|---|---|
| Engine model | Managed MySQL, PostgreSQL, SQL Server | PostgreSQL-compatible with AlloyDB-specific optimizations | Distributed SQL; GoogleSQL or PostgreSQL dialect |
| Scaling write capacity | Primarily scaling up primary and SQL tuning | Scaling up primary, PostgreSQL tuning | Distributed data/compute; scale instance and eliminate hotspots |
| Scaling read capacity | Read replicas, depends on engine/edition | Read pool with multiple nodes and endpoint | Distributed reads across Spanner splits/replicas |
| HA and DR | HA, backup/PITR, replicas per tier capability | AlloyDB-architected HA, backup/DR | Regional/multi-region configurations, replication |
| Optimization levers | Machine size, indexes, cache, connections, I/O | Read pools, columnar engine, query/index insights | Key distribution, query plans, CPU, transaction contention |
| Best suited for | Traditional SQL apps with minimal code changes | PostgreSQL needing high throughput/query speed | Relational SQL requiring distributed scale and strong consistency |
| Pitfall to avoid | HA standby is not a read replica for load offloading | Read pools do not make primary multi-writer | Adding nodes does not fix a single hot key |

Choosing a database is a long-term architectural and cost decision. Before migrating engines, tune SQL, schemas, connection management, and current configurations to find the true limits.

## 2. Defining Workload Characteristics and Success Criteria

Optimization only makes sense once you know what **real-world load** consists of. Record at least:

- **QPS/TPS:** queries or transactions per second, separated into reads and writes.
- **Read/write ratio:** e.g., 85% SELECT, 10% UPDATE, 5% INSERT.
- **Query shapes:** key lookups, multi-table joins, aggregations, scans, batches, time-range queries.
- **Concurrency:** simultaneous requests, open connections, pool size per application instance.
- **Data distribution:** row/table counts, tenant skew, index sizes, working set, growth rate.
- **Location:** whether app and database share a region or cross WANs; multi-region clients.
- **Special loads:** hourly peaks, bulk imports, migrations, backups, maintenance, month-end reports.
- **Consistency requirements:** which requests strictly require read-after-write vs. tolerate lag.

### Sample SLOs

Suppose a checkout service targets:

| SLI | Illustrative SLO |
|---|---|
| Order completion rate | At least 99.9% of valid requests over a 28-day window |
| p95 API latency | Under 300 ms during normal load |
| p99 database query latency | Under 120 ms for the critical checkout path |
| Transaction aborts/deadlocks | Below the threshold approved by the product team |
| Database connection checkout | p95 under 20 ms |
| Peak headroom | 3× baseline load without exhausting error budget |

These are **example** targets, not Google Cloud universal database thresholds. If the API also calls a payment gateway or shipping service, the database latency budget must be carved out of the end-to-end request deadline rather than giving the database the full 300 ms.

### Distinguishing Latency and Throughput

**Latency** is how long one request takes; **throughput** is completed requests per unit of time. A system can increase throughput while p99 latency worsens due to queueing. An average CPU of 40% does not guarantee zero bottlenecks if a single thread, lock, or Spanner split is hot.

A helpful decomposition:

\[
T_{request} = T_{queue} + T_{connection} + T_{network} + T_{execution} + T_{serialization}
\]

Not all components appear in a single metric; use application tracing alongside database metrics to estimate them. If `T_queue` dominates, adding an index may not help; if `T_execution` is high due to a full scan, inspect the query plan.

## 3. Diagnostic Workflow: Measure Before Changing

A seven-step investigation loop:

1. **Pinpoint the timeframe:** establish when the incident happened alongside deploy, migration, and traffic peak timestamps.
2. **Classify errors:** latency, 5xx, deadlocks, pool timeouts, replication lag, or I/O saturation.
3. **Compare baselines:** contrast with the same workload during steady state rather than looking at one point in isolation.
4. **Find top contributors:** which queries drive the largest share of database load or tail latency.
5. **Inspect execution plans:** index scans, sequential scans, sorts, joins, temp spills, remote work.
6. **Check resources:** CPU, memory, storage IOPS, cache hit ratio, lock waits, connections, and network.
7. **Test one change:** A/B benchmark, observe impact, roll back if SLOs worsen.

### Symptom and Hypothesis Matrix

| Symptom | First Hypothesis to Check | Verification Data |
|---|---|---|
| Rising p99, low CPU | Lock waits, pool exhaustion, network, I/O waits | Query Insights wait events, `pg_stat_activity`, Hikari metrics |
| Sustained high CPU | Table scans, poor joins, insufficient compute | Top SQL, execution plans, CPU trend |
| High latency at peak | Pool/connection storm, queueing, quotas | Active connections, checkout wait, QPS, concurrency |
| Only one tenant slow | Data skew, hot key/split, index skew | Query tags, tenant dimensions, Key Visualizer |
| Growing replica lag | Fast primary writes, under-sized replica, long replica queries | Replica lag, replica CPU, WAL/replication metrics |
| Write throughput stalls despite added compute | Lock contention, hot key, serialized transactions | Transaction aborts, lock waits, split hotspots |
| High memory usage and OOM | Hash/sort queries, cache pressure, excessive connections | Working set, temp files, active sessions |
| Rising cost with flat TPS | Overprovisioning, idle replicas, table/index bloat | Billing export, utilization, and unit cost |

Never diagnose root cause from CPU alone: request volume, contention, and query mix can shift simultaneously.

## 4. Observing with Cloud Monitoring and Query Insights

Google Cloud provides Cloud Monitoring, Cloud Logging, and specialized query tools. Monitor **both database metrics and application-side metrics**; looking at only one side misses pool wait times or requests canceled before queries start.

### Minimal Dashboard

| Group | Metrics |
|---|---|
| User experience | Success rate, p95/p99 latency, timeout count |
| Workload | Read/write QPS, TPS, request concurrency, rows examined |
| Compute | High-priority/total CPU where available, memory pressure |
| Storage | IOPS/throughput, latency, disk used, temp spills, cache hit |
| Connections | Active/idle connections, pool wait, max connections |
| Transactions | Lock waits, deadlocks, aborts/retries, transaction duration |
| Replication | Replica lag, network lag, apply lag where applicable |
| Query | Top SQL by total load/latency, plans, index usage |
| Costs | Instance compute, storage, replicas/read pools, backups, data transfer |

### Cloud SQL Query Insights

Query Insights helps view database load, top queries, tags, and drill-downs. Advanced capabilities such as wait event analysis, query plan capture, or index advisor depend on **database engine, edition, and configuration**. For example, Cloud SQL MySQL Enterprise Plus includes index advisor when Query Insights Enterprise Plus is enabled; do not assume every feature exists on Enterprise or across all engines.

### AlloyDB Query Insights and Index Advisor

AlloyDB provides Query Insights for both primary and read pools. Index Advisor can recommend indexes based on SQL workloads; enable it and review suggestions carefully. An index recommendation is only a signal: before creating it, assess write overhead, storage size, maintenance cost, and how many queries actually benefit.

### Spanner Query Insights, Execution Plans, and Key Visualizer

Spanner provides Query Insights for queries and DML, execution plans, CPU/latency breakdowns, and hotspot detection tools. When one server/split bottlenecks while average instance CPU stays modest, check key distribution/Key Visualizer instead of merely adding processing units.

Apply query tags/labels safely to link Java/Spring endpoints to database queries. Never log raw SQL containing customer PII or secrets into telemetry; Query Insights may retain query text and IP addresses depending on configuration choices.

## 5. Optimizing SQL and Schemas Before Adding Hardware

A well-chosen index can slash rows scanned, reduce disk I/O, and drop p95 latency without adding vCPUs. Conversely, too many indexes make INSERT/UPDATE/DELETE operations more expensive.

### PostgreSQL Query Example

Suppose an `orders` table has 20 million rows:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE customer_id = 'cust-001'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Inspect the plan in staging or when safe:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, status, created_at
FROM orders
WHERE customer_id = 'cust-001'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` **executes the SQL statement**; never run it carelessly on `UPDATE`/`DELETE` in production. When reading the plan, inspect estimated vs. actual rows, sequential scans, sorts, excessive loops, shared buffers, disk reads, and step timings.

An index suited to this query:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
  ON orders (customer_id, created_at DESC);
~~~

In PostgreSQL, `CREATE INDEX CONCURRENTLY` reduces write locking compared to standard index creation, though it still consumes I/O, CPU, and time, and can fail leaving an invalid index. Never run it inside a transaction block. Re-measure plans and latency after rollout; whether the optimizer picks the index depends on selectivity, statistics, and table size.

### Conditional Queries and Pagination

Common improvements:

- `SELECT` only needed columns; avoid returning large JSON/blob columns when UI only shows summaries.
- Push selective filters into SQL instead of fetching full sets and filtering in Java.
- Eliminate ORM N+1 query loops; use controlled batch loading or joins.
- Use keyset pagination instead of huge `OFFSET` values across deep pages.
- Bound scan time windows; consider time-based partitioning when data and query shapes fit.
- Shorten transactions, especially those holding row locks while calling external HTTP services.
- Check data skew and keep engine statistics up to date.

### Do Not Optimize One Query at the Expense of the Whole System

Adding an index on a frequently updated column can speed up a report while hurting write throughput. Evaluate every change across the **entire workload**, not just one SQL statement in isolation.

## 6. Cloud SQL: Optimizing Compute, Storage, and Connections

Cloud SQL fits many traditional SQL applications. Optimize across three layers: SQL/schema, instance configuration, and application flow.

### Compute and Memory

- If CPU remains high with already-sound query plans, consider adding vCPUs or choosing a better-suited machine type.
- If workloads need a large working set, increasing memory can cut disk reads; compare cache hit ratios before and after.
- If disk I/O is the bottleneck, inspect storage type, capacity/throughput, query scans, and temp files before upgrading machines.
- Monitor storage and backup growth; automatic storage increase prevents out-of-space outages but increases long-term cost.

Modifying instance configurations can cause restarts or downtime depending on the operation/edition. Check impact beforehand and prepare a maintenance window, rollback plan, and SLO monitoring.

### Cloud SQL Enterprise Plus and Data Cache

Certain editions, engines, and machine types support **data cache** to accelerate reads when the working set exceeds buffer pool capacity. This feature does not cure lock contention or unindexed queries. Use Cloud SQL recommendations/Query Insights to verify whether your workload actually benefits and weigh Enterprise Plus pricing.

Never assume all Cloud SQL instances share identical data cache or index advisor features. Consult documentation specific to your engine and edition (MySQL, PostgreSQL, or SQL Server).

### Cloud SQL HA Differs from a Read Replica

An **HA standby** serves failover/availability, not scalable read offloading like a read replica. A **read replica** handles read queries to offload the primary; replicas are typically **asynchronous**, meaning applications may observe stale state.

For "create order then immediately read it back" flows, route reads to primary or enforce read-your-writes semantics; never route every SELECT to replicas blindly. Monitor `replica_lag`, `network_lag`, and replica CPU. On PostgreSQL, long-running reads on a replica or an undersized replica can drive lag higher.

### Connection Pooling

When Cloud Run/GKE autoscales from 10 to 100 instances and each opens up to 20 connections, thousands of connections hit a database that did not scale proportionally. Approximate max connection budget:

\[
C_{max} = \sum_{service} replicas_{peak} \times poolSize_{perReplica}
\]

Reserve budget for administration, backups, monitoring, and failover. With Cloud SQL PostgreSQL Enterprise Plus, **Managed Connection Pooling** has specific version/network/edition requirements and uses port 6432 for direct pooled endpoints; transaction pooling differs from session pooling regarding session state and prepared statements. `Cloud SQL Auth Proxy` **is not a connection pooler**, even though it secures connections.

### Handling Connection Storms

1. Measure **actual** connection counts, including background apps and batch jobs.
2. Inspect pool checkout latency and pending requests waiting on the pool.
3. Shrink pool sizes if workloads create idle unnecessary connections.
4. Set concurrency limits on Cloud Run/GKE and batch workers.
5. Use retry/backoff with jitter on connection errors; avoid infinite retries.
6. Increase database `max_connections` or machine size only after verifying per-connection memory overhead.

## 7. Cloud SQL: Read Scaling and Consistency

E-commerce application example:

~~~mermaid
flowchart LR
    API[Java/Spring API] --> R[Read/write routing]
    R -->|Write, read-after-write| P[Cloud SQL primary]
    R -->|Lag-tolerant read| RR[Cloud SQL read replica]
    P -. async replication .-> RR
    Q[Query Insights and Monitoring] -. observe .-> P
    Q -. observe .-> RR
~~~

### When to Add a Read Replica

Consider one when:

- Most traffic consists of reads tolerant of replication lag.
- Primary CPU/I/O is heavily consumed by SELECTs even after query tuning.
- Reporting/batch workloads can be isolated from core transactions.
- The team can operate routing, lag monitoring, and failover.

Never add a replica to solve heavy primary writes or single-row lock deadlocks. Replicas also add compute/storage/network fees and operational management overhead.

### Routing by Data Sensitivity

| Business Flow | Preferred Endpoint | Rationale |
|---|---|---|
| Payment/order writes | Primary | Accepts writes and transactional consistency |
| Read immediately after order confirmation | Primary | Avoids reading records not yet replicated |
| Rarely changing product catalog | Replica if allowed | Increases read capacity |
| Historical summary reports | Replica or separate analytics store | Protects the OLTP path |
| Dashboards requiring strict real-time freshness | Primary or dedicated streaming pipeline | Requires explicit freshness definition |

A read replica does not automatically provide a client load balancer; applications, proxies, or routing layers must target the right endpoint and handle unavailability or lag.

## 8. AlloyDB: Heavy Reads, Read Pools, and Load Scaling

AlloyDB for PostgreSQL offers a managed PostgreSQL architecture with specialized query acceleration. It fits PostgreSQL workloads hitting throughput limits, needing read scaling, or running analytical queries on the same data platform.

### Primary and Read Pools

- **Primary instance** handles write traffic; increasing vCPU/RAM scales vertically.
- **Read pool instance** can contain multiple nodes; reads are distributed across the read pool endpoint.
- Read pool **node count** can scale manually or via read pool autoscaling under supported conditions.
- Changing node counts does not instantly rebalance all existing client connections; verify connection behavior and reconnections when nodes are removed.

Example:

~~~mermaid
flowchart LR
    APP[Application] -->|Transactions / writes| PRIMARY[AlloyDB primary]
    APP -->|Read-only queries| POOL[AlloyDB read pool endpoint]
    PRIMARY -. storage / replication .-> POOL
    POOL --> NODE1[Read node 1]
    POOL --> NODE2[Read node 2]
    POOL --> NODE3[Read node 3]
~~~

All diagrams are logical illustrations only. With AlloyDB, never assume read pools accept writes, read transactions on a pool immediately see every commit just finished on primary, or queries route automatically without client configuration.

### Signs to Scale Out a Read Pool

Add read nodes when Query Insights/metrics clearly show:

- Rising read throughput with sustained CPU or memory pressure on existing nodes.
- Read p95 latency breaching SLO after verifying indexes and query plans.
- Read pool endpoints and client routing are functioning properly.
- Required read freshness can still be met.
- Incremental cost of read nodes is lower than the throughput/latency value gained.

If a single full-scan SQL query consumes most resources, fixing that query usually beats adding two more read nodes.

### Index Advisor

AlloyDB Index Advisor analyzes frequent queries to recommend `CREATE INDEX` statements and estimate impact. It does not guarantee every suggested index is net-positive. Test in staging and measure read latency, write throughput, storage growth, index maintenance, and build time.

### AlloyDB Query Insights

Inspect primary and read pool metrics separately; a query that is fast on primary yet slow on the read pool may reflect query mix, resources, caching, or recent writes. Use query tags to map application endpoints to top SQL and avoid comparing workloads measured at different times.

## 9. AlloyDB Columnar Engine for Mixed OLTP/Analytics

The **columnar engine** accelerates large scans, joins, and aggregations by storing selected columns in an in-memory column-oriented format. It can run on the primary or read pools depending on supported configurations.

### When It Helps

- Queries aggregating a few columns across large row sets.
- Reports requiring `SUM`, `COUNT`, `AVG`, filters, or joins supported by the planner.
- Read-heavy dashboards that do not need to share the exact OLTP transaction path.
- Reducing analytical query time before needing a separate data warehouse.

### When It Hurts or Requires Caution

- Primary-key lookups that are already fast.
- High-update tables causing frequent column-store invalidations.
- Column store memory shrinking buffers needed for OLTP.
- Query shapes or data types unsupported by the columnar planner.
- Speedups failing to justify added RAM/compute and operational cost.

To use it, enable the `google_columnar_engine.enabled` flag per AlloyDB instructions; toggling this flag is a config change that **requires a restart**. You can let the system pick columns automatically (auto-columnarization) or configure them manually. Use `EXPLAIN` and column store metadata to verify queries actually use the columnar engine; **enabling the feature does not guarantee every query runs columnar**.

### A Verified Pilot Scenario

1. Baseline `SELECT category, COUNT(*), SUM(amount) ... GROUP BY category`.
2. Confirm it ranks among top load-driving queries.
3. Enable columnar on staging with representative data.
4. Check query plans and performance while continuous INSERT/UPDATE traffic runs.
5. Compare p95/p99, RAM pressure, CPU, OLTP throughput, and cost.
6. If OLTP degrades, consider shifting analytical workloads to a read pool or BigQuery.

Do not use AlloyDB columnar as an excuse to skip a proper analytics architecture for cross-source queries and massive batch jobs.

## 10. Spanner: Distributed Scaling Requires Proper Key Design

Spanner partitions data into key ranges (splits) and distributes work across compute resources. This unlocks horizontal scalability while introducing a key requirement: **key and traffic distribution must let the system spread load**.

### Hotspots from Monotonically Increasing Primary Keys

A poor design for a high-write table:

~~~sql
-- GoogleSQL Spanner example: not recommended for high INSERT load.
CREATE TABLE Events (
  EventTime TIMESTAMP NOT NULL,
  EventId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (EventTime, EventId);
~~~

When `EventTime` increases monotonically, new inserts pile onto one end of the key range. A single split becomes a bottleneck even when total Spanner instance CPU is low.

An alternative:

~~~sql
-- GoogleSQL example: EventId distributes randomly when generated with UUIDv4.
CREATE TABLE Events (
  EventId STRING(36) NOT NULL,
  EventTime TIMESTAMP NOT NULL,
  TenantId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (EventId);
~~~

For workloads querying by time or tenant, design secondary indexes carefully considering key distribution. UUIDv4, bit-reversed sequences, or hash-prefixed keys are supported/recommended techniques in appropriate situations; never change keys blindly without accounting for joins and locality.

### Hotspots Do Not Come Only from Primary Keys

A well-distributed table can still hotspot if:

- Every request updates a single counter row.
- A secondary index leads with a monotonic key like commit timestamp.
- One tenant receives 80% of traffic and `TenantId` is a low-cardinality leading prefix.
- Many transactions concurrently update a small hot subset of rows.

Fixes include sharded counters, key salting/distribution, controlled batching, separating write paths, or revising transaction logic. Never rely on adding nodes as the sole cure.

### Key Visualizer and Split Hotspots

When p99 rises despite low average instance CPU, inspect Key Visualizer and lock/transaction stats to locate hot key ranges or indexes. Changing primary key schemas is harder than adding indexes; prepare migration/backfill plans, dual reads/writes, or appropriate migration tooling.

## 11. Spanner: CPU, Processing Units, and Autoscaling

Spanner uses **processing units (PU)** or **nodes** to express compute capacity; typically **1 node = 1,000 PU**. Valid PU increments and scaling ranges depend on instance/edition limits; check quotas and regional support before applying.

### CPU Recommendations Are Not 100% Utilization Targets

Google Cloud publishes reference thresholds to preserve availability during zone/region loss:

| Metric | Regional Instance | Dual-Region or Multi-Region (Per Region) |
|---|---:|---:|
| High-priority total CPU utilization | Recommended max 65% | Recommended max 45% |
| 24-hour smoothed aggregate CPU | Recommended max 90% | Recommended max 90% |

These are **recommended headroom thresholds**, not guarantees of p99 latency for every application. For latency-sensitive workloads, benchmark to set lower targets if necessary.

### Managed Autoscaler

Spanner offers a managed autoscaler to scale compute up/down against CPU and storage targets. You can configure **high-priority CPU**, **total CPU**, and/or storage targets within supported bounds. Starting guidelines:

- Regional: high-priority CPU target ~65%, total CPU target ~70%.
- Multi-region: high-priority CPU target ~45%, total CPU target ~50%.

These numbers are documentation starting points, not rigid defaults. Adding resources carries lag and cost, and will not cure a hot split. If the autoscaler oscillates continuously, examine load periodicity, min/max bounds, and targets before tuning.

### Manual Scaling

Illustrative example increasing an existing instance's capacity:

~~~bash
gcloud spanner instances update spanner-orders-prod \
  --project=orders-prod \
  --processing-units=2000
~~~

This command alters production capacity and spend; never execute without approval. Scaling up takes time to rebalance resources; scaling down requires sufficient headroom for data size, split count, and expected traffic. Always check storage capacity requirements and specific limits before downsizing.

## 12. Spanner: Query Optimizer, Indexes, and Transactions

Spanner includes Query Insights, a cost-based optimizer, and query plans. A poorly written query can trigger remote scans, full-table scans, or expensive distributed joins even with a well-designed primary key.

### Querying by Customer and Time

Suppose the table is:

~~~sql
-- GoogleSQL dialect
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  Status STRING(20) NOT NULL
) PRIMARY KEY (OrderId);
~~~

To list a customer's 50 latest orders:

~~~sql
SELECT OrderId, CreatedAt, Status
FROM Orders
WHERE CustomerId = @customer_id
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

An index supporting this query:

~~~sql
CREATE INDEX OrdersByCustomerTime
ON Orders(CustomerId, CreatedAt DESC)
STORING (Status);
~~~

This index filters by `CustomerId` and orders by `CreatedAt`, storing `Status` alongside it. Note that every secondary index consumes storage, adds write amplification, and can introduce hotspots if key distribution is skewed. `@customer_id` is a query parameter, not variable-assignment syntax when run directly in the SQL console.

### Reading Query Plans and Statistics

Spanner query plans show scans, distributed work, rows returned, and CPU/elapsed time per operator. The optimizer uses statistics packages and versions; a plan shift can stem from statistics changes rather than an application release. When regressions occur, compare plans, query parameters, data volumes, and optimizer statistics/versions.

### Transaction Contention

- Keep read-write transactions short.
- Never make external network calls inside a transaction.
- Batch writes within supported limits and payload sizes; avoid touching many hot rows in one transaction.
- Handle `ABORTED` via Spanner client retry semantics paired with business-layer idempotency.
- For reads that do not strictly require the latest state, consider bounded staleness or exact staleness **in the client API** per contract.

Do not switch all queries to stale reads just to save CPU if the application requires strong consistency, especially for payments or inventory checks.

## 13. Comparing Optimization Levers by Bottleneck

| Bottleneck | Cloud SQL | AlloyDB | Spanner |
|---|---|---|---|
| One query scanning too much | `EXPLAIN`/indexes/statistics | Query Insights, Index Advisor, columnar if appropriate | Query plan, secondary index, predicates/selectivity |
| Heavy SELECTs saturating CPU | Read replica, caching | Read pool and node autoscaling | Distribute reads, add PU/nodes if no hotspot |
| Too many connections | Hikari/PgBouncer/managed pooling per edition | App pool, read pool endpoint, connection limits | Appropriate client/session pooling, session exhaustion metrics |
| Writes hitting a hot row | Optimize locks/transactions, shard counters if needed | Tune PostgreSQL transactions and data model | Redesign hot key/split, sharded counters |
| Large working set | Instance memory/data cache per edition | Memory sizing, read pools, and column store | Compute/data placement, indexes, and scans |
| Region far from users | Choose suitable region/read architecture | Read topology and data locality | Regional/multi-region config, routing/consistency |
| Short traffic spikes | Scaling plan / concurrency limits | Scale primary/read nodes per policy | Managed autoscaler and headroom |
| Excessive cost | Rightsize and remove unneeded replicas | Optimize read pools/columnar | PU autoscale, avoid overprovisioning and hotspots |

Never migrate from Cloud SQL to Spanner just because one table lacks an index; conversely, if distributed write patterns and multi-region latency exceed single-primary limits, simply sizing up Cloud SQL will not hold long term.

## 14. Java and Spring: Fix Connections Before Optimizing SQL

In Spring Boot, HikariCP typically manages the connection pool. Configuration must align with Cloud Run/GKE autoscaling and database limits.

Example `application-prod.yml` for PostgreSQL over a private endpoint or organization-configured connector/proxy:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    # Password retrieved from Secret Manager or platform secret mechanism.
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
      validation-timeout: 2000
      pool-name: orders-pool
~~~

Never hardcode passwords in Git. If the app scales up to 80 replicas, up to 10 connections per replica can request 800 connections for this service alone. That is a **theoretical peak**, not guaranteed active connections. Add other services, admin users, and failover margins.

### Three Timeouts to Distinguish

- **Pool checkout timeout:** waiting to borrow a connection from Hikari; not the same as a SQL timeout.
- **Connection/network timeout:** driver limits for establishing connections and socket reads/writes.
- **Query/transaction timeout:** execution budget for a SQL statement or transaction.

Never fix pool timeouts by raising `maximum-pool-size` indefinitely; that can crash the database faster. Shorten connection hold times, avoid wrapping HTTP calls in open transactions, and enforce sensible concurrency caps.

### Monitoring Pool Metrics

Spring Boot with Micrometer exposes active, idle, pending, and total Hikari connections. When checkout wait grows while DB CPU stays low, inspect thread starvation, connection leaks, slow transactions, and networking. When DB CPU is high and queues grow, lowering client concurrency helps recovery far better than adding retries.

### Read/Write Routing Requires Clear Contracts

If a Java service uses both primary and read replica/read pool endpoints, separate `DataSource` instances or routing components explicitly by intent. Methods reading right after writes or running inside read-write transactions must preserve consistency contracts. Never let a Spring `readOnly` annotation automatically route every SELECT to an asynchronous replica.

## 15. Caching, Batching, and Application-Layer Optimizations

Not every improvement belongs in the database. For slowly changing data, application caching or Memorystore reduces load. For heavy aggregations, precomputing or offloading analytics to BigQuery often beats scaling database instances.

### High-Leverage Techniques

- **TTL caches with invalidation:** catalogs, configuration, reference data.
- **Batched reads/writes:** reduce network round-trips where APIs allow.
- **Debouncing or coalescing:** prevent many concurrent requests from fetching the same cold key simultaneously.
- **Async events:** offload non-immediate work via Pub/Sub or queues.
- **Data archiving:** separate cold historical rows to shrink the working set.
- **Dedicated read models:** precompute dashboards instead of running heavy joins on every page load.

### Risks

Caches can serve stale data; large batches can hold transactions/locks too long; event-driven pipelines introduce eventual consistency. Every change must define freshness bounds, ordering, idempotency, and business completion criteria.

A checkout flow should never cache available inventory counts without strict stock-reservation controls. Nor should account-balance reads move to a replica merely to shave CPU.

## 16. Benchmarking Realistic Load, Not a Single SQL Query

### Building a Representative Workload

A meaningful load test needs:

1. A dataset large enough to mirror production statistics in size, cardinality, and skew.
2. A traffic mix derived from telemetry: reads/writes/transactions/reports/batches.
3. Realistic concurrency and ramp-up matching production apps.
4. Controlled warm/cold cache ratios.
5. Network topology and region alignment close to production.
6. Long enough duration to expose memory pressure, compaction/vacuuming, and background I/O.
7. Recorded error probabilities, retries, and timeouts — not just requests/second.

Never use production PII in benchmark environments without authorization; synthetic data must preserve realistic distributions.

### Experiment Matrix

| Variant | Single Change | Measure |
|---|---|---|
| Baseline A | Current configuration | p50/p95/p99, TPS, CPU, I/O, cost |
| B | Add composite index | Query plan, write overhead, index size |
| C | Pool 20 → 10 connections/replica | Pool wait, DB CPU, throughput, timeouts |
| D | Add read replica/read pool | Read p95, write p95, lag, cost |
| E | Increase CPU or processing units | Throughput, headroom, cost |
| F | Enable columnar / change key schema in staging | Query speedup, memory, hotspots, write costs |

Never alter indexes, node counts, concurrency, and SQL in one test and credit a single factor. When combined changes are unavoidable, document the method and re-verify individual levers.

### Efficiency Formula

\[
CostPer1000SuccessfulTxn =
\frac{TotalDatabaseCost}{SuccessfulTransactions} \times 1000
\]

For example, a database costing 2,000 USD/month for 4 million successful transactions equals 0.50 USD/1,000 transactions. After optimization, cost rises to 2,200 USD while handling 6 million transactions within the p99 SLO: roughly 0.37 USD/1,000 transactions. Total spend rose, yet unit economics improved.

Never optimize averages while tail p99 or failure rates worsen. Set joint goals: cost per successful transaction decreases **and** error budgets remain intact.

## 17. FinOps: Comparing Costs Fairly

Database cost is more than vCPUs:

- Compute for primary, replicas/read pools, or Spanner processing units.
- Data storage, indexes, backups, PITR/transaction logs, and retention.
- Cross-region/VPC/cloud egress and app-to-database connectivity.
- Query Insights, logging, and monitoring under current pricing models.
- HA/DR, maintenance, migration, and operational labor.

### Normalizing the Unit of Comparison

Cloud SQL, AlloyDB, and Spanner have distinct pricing models and architectural boundaries. When comparing them, hold constant:

1. Workload set, data volume, and tenant skew.
2. SLA/SLO, RPO/RTO, region, and HA requirements.
3. Query correctness, business success rate, and latency.
4. Read/write ratio, peak concurrency, and projected growth.
5. Full Total Cost of Ownership (TCO) and migration cost.

A multi-region Spanner instance costing more than a single-region database is not a bad choice if the business requires regional fault tolerance and cross-region consistency; conversely, avoid multi-region for a small internal app without those needs.

### Decide Whether to Scale or Optimize

| Observation | Try Optimizing First | When Scaling Is Justified |
|---|---|---|
| High CPU from query scans | Indexes, query rewrites | After queries are sound yet throughput still falls short |
| High lock waits | Shorten transactions, reduce contention | Scaling helps little on a single hot row |
| High pool wait | Cut connection hold time, fix leaks | Scale DB when true concurrency demands it and DB has headroom |
| Rising read demand | Caching, read pool/replica routing | Scale read capacity after measuring lag/consistency |
| Spanner hot split | Redesign keys/secondary indexes | Scale compute once load distributes evenly |
| Working set > cache | Cut scans, cache, tune storage design | Increase RAM/data cache when benefits are measured |

Optimization must tie to business outcomes: cutting latency to lift conversion, lowering errors to protect SLAs, or reducing cost per unit without sacrificing availability.

## 18. Production Slow-Database Incident Runbook

### Phase 0: Do No Harm to Data

Never run massive DDL, full reindexes, transaction isolation changes, or primary key alterations mid-incident without impact assessment. Establish the incident commander, severity level, and change authority.

### Minutes 0 to 10

1. Identify failing services and request paths; check SLO/error budgets.
2. Compare peak traffic, app replica counts, and database CPU/I/O/connections.
3. Check Cloud Monitoring, Query Insights, and recent deploys/maintenance events.
4. If a connection storm is underway, cap concurrency/rate and disable unsafe retries.
5. If a new query caused the load spike, consider rolling back the app release instead of altering the database immediately.

### Minutes 10 to 30

6. Inspect top SQL, wait events, lock contention, and query plans.
7. Check replica lag or Spanner hotspots where relevant.
8. Pick low-risk mitigations: throttle batch concurrency, shift reports to read pools, disable heavy non-critical features.
9. If scaling is needed, verify quotas, cost, execution time, and rollback conditions.
10. Track p95/p99, error rates, and transaction success after every change.

### Post-Incident

11. Preserve timelines, metrics, query plans, and before/after configurations.
12. Build a reproduction test with representative load.
13. Fix root cause: indexes, connection strategy, hot keys, or capacity policy.
14. Add alerts, runbooks, rollback steps, and a cost review.

Never use "restart the database" as the first response; restarting drops caches, severs connections, and triggers a reconnect storm across all services.

## 19. Exercises: Optimizing Three Different Systems

### Scenario A: Cloud SQL PostgreSQL

A Spring app on Cloud Run scales from 20 to 120 instances during peak hours; each instance sets a Hikari pool max of 20 connections. Cloud SQL CPU sits around 55%, yet many requests fail with connection checkout timeouts.

**Question:** What is the most likely cause and what should you measure before adding vCPUs? Hint: compute the peak connection budget (120 × 20 = 2,400), compare against DB limits, monitor pool pending counts, connection hold times, and transaction duration. Test shrinking pool size, capping concurrency, and removing transactions wrapped around HTTP calls.

### Scenario B: AlloyDB Read Pool

A reporting job runs every minute; a two-node read pool shows 3-second p95 latency and high CPU. The top query aggregates across 30 million rows, while primary writes remain healthy.

**Question:** Should you add nodes immediately or optimize the query? Hint: inspect the plan, indexes/Query Insights, benchmark the columnar engine on the read pool, and measure CPU and memory. Scale node count only once you verify extra read capacity resolves the actual load.

### Scenario C: Spanner

A logging system writes 20,000 events/second. Average instance CPU is 35%, yet p99 write latency rises sharply. The primary key leads with a monotonically increasing timestamp.

**Question:** Will adding nodes fix this? Hint: check Key Visualizer, split hotspots, and secondary index structure; try a distributed `EventId` using UUIDv4 or hash prefixes while preserving time-based queries via an appropriate index.

## 20. Quick Troubleshooting

| Symptom | Common Cause | Verified Action |
|---|---|---|
| p99 rises despite low CPU | Lock/pool/network waits | Query Insights waits, active connections, tracing |
| Added read replica yet lag stays high | Undersized replica or long read queries | Replica lag metrics, replica sizing, query tuning |
| Cloud SQL has too many connections | App autoscaling × pool size | Hikari metrics, connection budget, pooling strategy |
| AlloyDB read pool stays slow | One huge scan query or wrong routing endpoint | Top SQL, query plan, index/columnar validation |
| Enabling columnar gave no speedup | Query skips column store or high invalidations | `EXPLAIN`, column store usage, update rate |
| Spanner still times out after adding PU | Hot key/split or transaction contention | Key Visualizer, split/lock analysis, key redesign |
| Spanner CPU climbs after new query | Plan regression or missing index | Query Insights, optimizer plan, statistics |
| Database bill rises with flat throughput | Overprovisioning, idle read nodes, storage growth | FinOps cost/unit, utilization, and resource inventory |
| Batch jobs break checkout | Reports hold locks/I/O or saturate primary | Schedule/budget batches, read pools, or analytics platform |
| Writes slow down after query optimization | New index increases write amplification | Benchmark read/write TPS and index maintenance |
| Load test passed but production lags | Different dataset/skew/peak or mismatched cache | Recreate realistic traffic, p99, tenant skew |

## 21. Pre-Production Change Checklist

- [ ] Baseline exists for SLOs, traffic mix, p95/p99, error rate, and unit cost.
- [ ] CPU saturation is distinguished from I/O, network, connection, and lock waits.
- [ ] Top SQL and execution plans inspected, not just instance CPU.
- [ ] New indexes tested for both read gain and write overhead.
- [ ] Connection pools sized against peak application replica count.
- [ ] Cloud SQL HA standby is not mistaken for a read replica.
- [ ] Read replicas/read pools have freshness contracts and replication lag monitoring.
- [ ] AlloyDB columnar used only when query shapes fit and memory suffices.
- [ ] Spanner primary/secondary keys reviewed for hotspot risks.
- [ ] Spanner CPU headroom and autoscaler configured per topology and SLOs.
- [ ] Load tests executed with representative data and traffic mix.
- [ ] Changes tested one factor at a time with rollback plan and owner approval.
- [ ] HA/DR, security, networking, and cost impacts evaluated.
- [ ] Alerts configured for pool pending, query latency, replica lag, and transaction aborts.
- [ ] Cost unit, successful transaction count, and measurement window agreed upon.
- [ ] No credentials or sensitive-data SQL logged into telemetry.

## 22. Conclusion

Optimizing Cloud SQL, AlloyDB, and Spanner must start from **real-world workload characteristics**, not machine sizes. The exact same symptom—rising p99 latency—can stem from very different causes: a connection storm on Cloud SQL, a read pool running huge scans on AlloyDB, or a hot key on Spanner. The right remedy is dictated by telemetry, execution plans, concurrency models, and the application's consistency contract.

A sustainable workflow is **baseline → pinpoint top bottleneck → optimize queries/schema/connections → consider scaling → benchmark → reconcile SLOs and cost per unit → monitored rollout**. Once every change can be proven to improve business outcomes at reasonable cost, database optimization becomes part of SRE and FinOps rather than firefighting whenever the system slows down.

## References

- [Cloud SQL for PostgreSQL: Best practices](https://docs.cloud.google.com/sql/docs/postgres/best-practices)
- [Cloud SQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL: Query Insights](https://docs.cloud.google.com/sql/docs/postgres/using-query-insights)
- [Cloud SQL: Replication lag](https://docs.cloud.google.com/sql/docs/postgres/replication/replication-lag)
- [Cloud SQL: High availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [AlloyDB: Query Insights](https://docs.cloud.google.com/alloydb/docs/using-query-insights)
- [AlloyDB: Index Advisor](https://docs.cloud.google.com/alloydb/docs/use-index-advisor)
- [AlloyDB: Scale an instance and read pool](https://docs.cloud.google.com/alloydb/docs/instance-read-pool-scale)
- [AlloyDB: About the columnar engine](https://docs.cloud.google.com/alloydb/docs/columnar-engine/about)
- [Spanner: CPU utilization](https://docs.cloud.google.com/spanner/docs/cpu-utilization)
- [Spanner: Managed autoscaler](https://docs.cloud.google.com/spanner/docs/managed-autoscaler)
- [Spanner: Compute capacity and processing units](https://docs.cloud.google.com/spanner/docs/compute-capacity)
- [Spanner: Primary key design](https://docs.cloud.google.com/spanner/docs/schema-design)
- [Spanner: Query Insights](https://docs.cloud.google.com/spanner/docs/using-query-insights)
- [Spanner: Query execution plans](https://docs.cloud.google.com/spanner/docs/query-execution-plans)
- [Cloud Monitoring overview](https://docs.cloud.google.com/monitoring/docs)
