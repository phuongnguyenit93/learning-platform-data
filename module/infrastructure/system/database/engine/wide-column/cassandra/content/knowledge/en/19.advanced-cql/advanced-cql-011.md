# Evaluating Application-Side or Analytical Warehouse Computation Instead of Wide Scans

## Learning Objectives

Apache Cassandra is designed to distribute data across many nodes, serving queries with an **explicit partition key** at low latency with horizontal scalability. However, when a requirement calls for summing, counting, grouping, or aggregating across millions of records scattered over many partitions, seemingly simple CQL can trigger **wide scans**, heavy cluster load, and unpredictable latency.

Within the **Advanced CQL** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson poses a practical question: **Should you compute inside Cassandra, in the Java application, in a pre-aggregated summary table, or offload to an analytics warehouse?** The choice must stem from the wide-column model, partition keys, required query shapes, accuracy, replication, consistency levels, and operational behavior such as compaction and repair.

After this lesson, you will be able to:

- Identify Cassandra queries at risk of scanning many partitions, especially `COUNT(*)`, unsuitable `GROUP BY`, and `ALLOW FILTERING`.
- Distinguish **application-side computation over a bounded dataset** from **full-dataset analytics** in an analytical store.
- Design query-driven tables that bound read volume using partition keys and time ranges.
- Choose between direct application computation, pre-aggregated summary tables (*pre-aggregation*), and OLAP/data warehouse systems.
- Implement CQL and Java examples with row caps, paging, and error handling.
- Evaluate latency, data freshness, operational cost, reconcilability, and result consistency.

## 1. Why Are Wide Scans Unsuitable for Cassandra?

A Cassandra row is located via its **partition key**. The partition key's token determines how data is distributed across replicas per topology and replication factor. **Clustering** columns define row order *within a partition*, making range reads efficient once the partition key is known.

Imagine a system recording payments from 100,000 devices, each generating many events per day:

| Product Requirement | Read Scope |
| --- | --- |
| Show the 20 latest events for **one device** on a day | One partition or a known, bounded set of partitions |
| Sum payments for **one device** over 15 minutes | One device/day partition, known clustering range |
| Sum payments across **all devices** of a tenant for a month | Very many partitions across devices and days |
| Rank the top 100 tenants by quarterly revenue | Many tenants, many partitions, full-dataset aggregation and sorting |

Cassandra excels at the first two queries when tables are designed around those keys. The latter two belong to **large-scale analytics**; attempting to pull every row from Cassandra into a Java service to sum forces the app to coordinate massive request fan-out and ship large volumes over the network.

~~~mermaid
flowchart TD
    Q["New computation requirement"] --> K{"Is partition key known and\nread scope small enough?"}
    K -->|Yes| A["Bounded CQL read\nCompute in app if needed"]
    K -->|No| F{"Is the result queried\nfrequently and needs low latency?"}
    F -->|Yes| P["Pre-aggregate by query key\nRead summary table"]
    F -->|No or exploratory query| W["Analytics warehouse / OLAP\nETL, CDC, or batch export"]
    A --> V["Measure latency, row count, errors, cost"]
    P --> V
    W --> V
~~~

A **wide scan** does not only mean one partition having many rows. It can also be one query—or many concurrent app queries—touching thousands of distinct partitions simultaneously. Coordinators, replicas, CPU, I/O, network, heap, tombstones, and compaction can all suffer.

## 2. Misleading CQL Patterns

### 2.1. COUNT(*) Is Not an Instant Metadata Counter

~~~sql
-- Valid syntax, but dangerous on a large table:
SELECT COUNT(*) FROM events_by_device_day;
~~~

Cassandra does not maintain a cluster-wide exact row count to answer this in constant time. A count query must traverse actual data, risking heavy reads and timeouts as tables grow. Even counting within **one very large partition** must process many rows; specifying a partition key does not turn `COUNT(*)` into an O(1) read.

~~~sql
-- Counting within a single partition can be acceptable if the partition is small:
SELECT COUNT(*)
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21';
~~~

**Design question:** how immediately exact does the service need that count to be? If a dashboard displays daily transaction counts multiple times per second, consider pre-aggregated counts instead of re-running `COUNT(*)` over raw events.

### 2.2. GROUP BY in CQL Is Not OLAP GROUP BY

`GROUP BY` in Cassandra is constrained by **primary key** and clustering key ordering. It does not offer an arbitrary analytical engine with joins, sorts, shuffles, and group-by over any column like OLAP SQL engines. Asking for `GROUP BY tenant_id` on data partitioned by `device_id` does not magically become efficient.

Do not translate a report like:

~~~sql
-- ILLUSTRATIVE ANALYTICAL SQL, NOT a CQL query pattern to run on a
-- transaction table distributed by device_id:
SELECT tenant_id, DATE(event_time), SUM(amount_minor)
FROM all_events
GROUP BY tenant_id, DATE(event_time);
~~~

into a Cassandra scan merely because the aggregate function names look similar. Evaluate **actual data distribution** and CQL syntax constraints before choosing your tool.

### 2.3. ALLOW FILTERING Does Not Make Wide Scans Cheap

Suppose the partition key is `(tenant_id, device_id, day)`, yet the caller only knows `tenant_id` and the month. The statement:

~~~sql
-- Example mismatch with partition key; do not use this
-- as a query design for monthly reporting:
SELECT event_time, amount_minor
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
ALLOW FILTERING;
~~~

may be rejected by Cassandra or, when forced in a permitted scenario, read and discard huge numbers of rows. `ALLOW FILTERING` merely acknowledges a potentially risky filter plan; it **does not supply a partition key**, create a suitable index, or bound how many partitions get inspected.

`LIMIT 100` does not fix the problem either. It caps rows **returned**, not how many rows the server inspects on disk or how many partitions it contacts. `LIMIT` helps properly modeled queries, not as a substitute for bounding read scope.

### 2.4. Indexes, Materialized Views, and Batches Are Not an Analytics Warehouse

- **Secondary indexes/SAI** can assist queries matching indexed predicates. Yet having an index does not make `SUM`/`GROUP BY` over large datasets cheap; measure selectivity, fan-out, and read cost.
- **Materialized views** in Cassandra offer alternative key lookups; **they do not precompute SUM/AVG/COUNT** like OLAP aggregate tables.
- **BATCH** groups write mutations; batches are neither a distributed aggregation mechanism nor a way to accelerate full-dataset reads.
- `CONSISTENCY QUORUM` raises replica acknowledgment requirements in certain topologies, **without altering the complexity** of wide analytical queries.

## 3. Designing Partition-Bounded Read Paths

Suppose the online requirement is: "Within a specific hour on a day, how many payment transactions and what total amount did device X of tenant Y produce?" Design the event table around that exact query key:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id uuid,
    day date,
    event_time timestamp,
    event_id timeuuid,
    event_type text,
    amount_minor bigint,
    PRIMARY KEY ((tenant_id, device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

**Schema analysis:**

- `(tenant_id, device_id, day)` is the **composite partition key**. The system routes directly to that device's partition for the day.
- `event_time` and `event_id` are clustering columns; `event_id` disambiguates events sharing a timestamp. The application must preserve a stable event ID if idempotent retries are needed.
- `amount_minor` stores money in minor units (cents/dong depending on currency), avoiding `float` rounding bugs during summation.
- `day` must be derived consistently from event time (e.g., in UTC) so time queries neither drop nor double-count across day boundaries.
- Never let a daily partition grow unboundedly if a device produces extreme traffic; switch to hourly buckets or sharding when load metrics justify it.

Insert a few test rows:

~~~sql
INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:10:00Z',
    now(), 'PAYMENT', 12000
);

INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:15:00Z',
    now(), 'PAYMENT', 8500
);

INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:20:00Z',
    now(), 'HEARTBEAT', 0
);
~~~

Read a time window within **the exact partition**:

~~~sql
SELECT event_time, event_id, event_type, amount_minor
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z';
~~~

The application can iterate over the returned rows and sum only those where `event_type = 'PAYMENT'`. With the sample data above, the expected result is **2 transactions**, totaling `20500` minor units. There is no need for a separate summary table if the window holds few rows and query frequency is low.

**Important limitation:** "Has a partition key" does not mean "automatically lightweight." A partition containing millions of rows, or an application concurrently reading thousands of partitions, can still be prohibitively expensive. Measure partition size, rows within the clustering range, requests/second, and response times.

## 4. When Should You Compute in the Java Application?

Application-side computation fits when:

1. There is a **known, relatively small number of partitions**—for instance, a single device/day, or a few bounded partitions.
2. The number of rows to read has an **expected upper bound** backed by real data; you can enforce a hard cap and handle breaches cleanly.
3. The formula is concise—summing, counting by type, computing ratios over a small row set, or applying business logic awkward to express in CQL.
4. Reading raw data is acceptable; latency, bandwidth, and replica load have been measured under realistic conditions.

A Java Driver 4.x pattern using a prepared statement, paging, and a row scan limit:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DevicePaymentCalculator {
    private static final long MAX_SCANNED_ROWS = 10_000L;

    private final CqlSession session;
    private final PreparedStatement readWindow;

    public record Totals(long visitedRows, long paymentCount, long amountMinor) {}

    public DevicePaymentCalculator(CqlSession session) {
        this.session = session;
        this.readWindow = session.prepare(
            "SELECT event_type, amount_minor FROM events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ?");
    }

    public Totals calculate(
            String tenantId,
            UUID deviceId,
            LocalDate day,
            Instant fromInclusive,
            Instant toExclusive) {
        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || day == null
                || fromInclusive == null || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid read window parameters");
        }
        // Callers must also ensure from/to fall inside the target "day" bucket.
        BoundStatement bound = readWindow.bind(
                tenantId, deviceId, day, fromInclusive, toExclusive)
            .setPageSize(200)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        long visited = 0;
        long paymentCount = 0;
        long totalMinor = 0;
        for (Row row : session.execute(bound)) {
            if (++visited > MAX_SCANNED_ROWS) {
                throw new IllegalStateException(
                    "Data window exceeded limit; use a summary table");
            }
            if ("PAYMENT".equals(row.getString("event_type"))) {
                paymentCount = Math.addExact(paymentCount, 1);
                if (!row.isNull("amount_minor")) {
                    totalMinor = Math.addExact(totalMinor, row.getLong("amount_minor"));
                }
            }
        }
        return new Totals(visited, paymentCount, totalMinor);
    }
}
~~~

In this example:

- The read is scoped to **one partition** and a clustering range directly in CQL—no full-table `SELECT *`.
- `setPageSize(200)` limits rows fetched per network page instead of loading everything into a `List`; it **does not cap total rows read**, hence `MAX_SCANNED_ROWS` is still required.
- If the cap is exceeded or the query times out, the method fails explicitly rather than returning a **silently incomplete** total. The caller must switch to a summary report or inform the user that the range is too large.
- `Math.addExact` catches `long` overflow. Monetary values use minor integer units to prevent floating-point inaccuracies.
- `LOCAL_QUORUM` is illustrative; align CL with replication factor/datacenter topology and freshness needs. It does not create an atomic snapshot across multiple rows modified concurrently during the read.

If the time range spans multiple days, the application must resolve the corresponding day buckets and enforce a cap on the **total** partitions/rows, not just per-day limits. Paging, rate limiting, and timeouts are secondary safeguards—not substitutes for bounding data scope in the schema.

## 5. When Should You Build a Pre-Aggregated Summary Table?

Suppose a tenant dashboard frequently asks: "For this month, what are the daily transaction counts and total amounts?" Reading raw events across tens of thousands of devices on every load scales latency and cluster load with raw volume.

You can store **one summary row per tenant/day**, bucketed by month to prevent a single tenant partition from growing forever:

~~~sql
CREATE TABLE tenant_daily_payment_totals (
    tenant_id text,
    year_month text,
    day date,
    payment_count bigint,
    total_minor bigint,
    as_of timestamp,
    PRIMARY KEY ((tenant_id, year_month), day)
) WITH CLUSTERING ORDER BY (day DESC);
~~~

Example of a batch job or stream processor writing a computed snapshot:

~~~sql
INSERT INTO tenant_daily_payment_totals (
    tenant_id, year_month, day,
    payment_count, total_minor, as_of
) VALUES (
    'tenant-a', '2026-11', '2026-11-21',
    842, 9876543, '2026-11-21T10:00:00Z'
);
~~~

The application reads every day of a month from **one known partition**:

~~~sql
SELECT day, payment_count, total_minor, as_of
FROM tenant_daily_payment_totals
WHERE tenant_id = 'tenant-a'
  AND year_month = '2026-11'
  AND day >= '2026-11-01'
  AND day < '2026-12-01';
~~~

Each tenant/month holds at most ~31 daily rows instead of millions of raw events. `year_month` is normalized by the application as `YYYY-MM`; time bucketing, timezone, and bucket naming must match identically between writers and readers.

In return, pre-aggregation introduces its own challenges:

| Challenge | Design Approach |
| --- | --- |
| **Freshness** | Store `as_of` and display when the figures were last updated. |
| **Duplicate events** | Use stable `event_id` values and deduplication/reconciliation. Never assume repeating `counter + 1` is idempotent. |
| **Late-arriving events** | Support updating prior days' totals or running windowed backfill jobs. |
| **Raw vs. summary drift** | Schedule periodic reconciliation against source events and repair summaries. |
| **Failures between two writes** | Never assume writing an event and updating a summary in two partitions/tables is atomic. |
| **Load distribution** | If one tenant/month gets too hot, consider sharding or splitting summaries by query dimension. |

**Prefer writing idempotent recomputed summary snapshots** when your pipeline supports reprocessing, because overwriting the same `payment_count` and `total_minor` for a period is much easier to make idempotent than per-event counter increments. Still, if multiple writers compute snapshots concurrently, add version/checkpoint coordination so stale snapshots never overwrite newer ones.

For **approximate** counts, counters can help. However, Cassandra counters do not guarantee a retried `+1` applies only once; never rely solely on counters for monetary sums or strictly audited totals.

## 6. When Should You Offload to an Analytics Warehouse / OLAP?

Consider a data warehouse, data lakehouse, OLAP engine, or distributed compute system when one or more of the following apply:

- **Many unknown partitions upfront**: aggregating all devices per quarter, slicing by region, tenant, or product.
- **Arbitrary grouping and aggregation**: `GROUP BY` on non-key attributes, dozens of metrics, or high group cardinality.
- **Joins** combining multiple sources such as users, revenue, product catalogs, or campaigns.
- **Long historical analysis**: multi-month/year comparisons, exploratory ad-hoc queries, or continuously evolving BI dashboards.
- **Heavy scan workloads** that must not degrade latency for transactional OLTP traffic on Cassandra.

Reference data flow:

~~~mermaid
flowchart LR
    A["App / business events"] --> B["Cassandra: OLTP queries"]
    A --> S["Event stream with IDs"]
    B -. "CDC or batch export" .-> E["ETL / stream pipeline"]
    S --> E
    E --> D["Analytics warehouse / OLAP"]
    D --> R["Dashboards, rollups, reports"]
    E --> P["Cassandra summary table\nfor low-latency screens"]
~~~

Common synchronization paths include **batch exports**, **CDC** (on supported versions), or publishing business events into a stream feeding both stores. The right choice depends on latency targets, operational maturity, tooling, and recovery needs. CDC still has to handle replays, late arrivals, update ordering, and sync outages; *exactly-once* end-to-end is not automatic.

In an analytics engine, a report like this makes architectural sense (**illustrative** SQL; date syntax varies by engine):

~~~sql
SELECT
    tenant_id,
    DATE_TRUNC('month', event_time) AS month_bucket,
    COUNT(*) AS payment_count,
    SUM(amount_minor) AS total_minor
FROM analytics_events
WHERE event_type = 'PAYMENT'
  AND event_time >= TIMESTAMP '2026-11-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-12-01 00:00:00'
GROUP BY tenant_id, DATE_TRUNC('month', event_time);
~~~

This query fits engines built for columnar reads, analytical partitioning, aggregations, and large-scale shuffle/merge. Never paste this into `cqlsh` expecting Cassandra to execute it the same way.

Clearly define the **source of truth**. If Cassandra holds authoritative operational data and the warehouse is a replica, build missing/duplicate detection, track sync lag, and support rebuilding from logs or exports. If a durable event log is the source of truth, a pipeline can populate both Cassandra and the warehouse, provided retries and deduplication are explicitly engineered.

## 7. Decision Matrix

| Criterion | Java App Compute After Bounded CQL | Summary Table in Cassandra | Analytics Warehouse / OLAP |
| --- | --- | --- | --- |
| Read scale | Few partitions and few rows, strict cap | Few summary rows per query key | Massive rows/partitions and deep history |
| Latency | Typically low when scope is small | Low, predictable for fixed queries | Engine/load-dependent; suited for reporting and batch |
| Freshness | Close to OLTP data, subject to chosen CL | Lags per aggregation pipeline | Lags per ETL/CDC schedule |
| New query shapes | Requires Java logic changes; still scope-bounded | May require adding new summary tables | Flexible for ad-hoc SQL/BI |
| Cost | Network, app CPU, replica reads | Extra storage and summary maintenance | Dedicated analytical infra/pipeline |
| Correctness | Depends on scope and read stability | Depends on dedupe, late events, reconciliation | Depends on ingest, dedupe, and watermarks |
| Typical use case | Single device total over 15 minutes | Daily tenant totals on dashboard | Top tenants by revenue, quarterly/annual analytics |

No universal row threshold fits every system. A partition with 2,000 tiny rows can be cheaper than 200 rows holding huge payloads or heavy tombstones. Benchmark with realistic **row sizes, RF, node count, replicas touched, concurrency, and target latency**.

### Decision Process

1. **Define outputs:** which metrics, grouped by what fields, exact vs. approximate, and maximum tolerable staleness.
2. **Trace the query key:** can request parameters derive an explicit partition key? How many partitions does one request touch?
3. **Estimate volume:** rows per partition, partition count, payload size, requests/second, and query time window.
4. **Test the simplest viable option:** if bounded, benchmark CQL + Java; for repeated dashboard lookups, prototype a summary table; for wide reports, use an analytics store.
5. **Define acceptable divergence:** can data lag 30 seconds or 1 hour? When must reconciliation run? Can timeouts return partial reports?
6. **Check OLTP impact:** monitor latency, read timeouts, hot partitions, and Cassandra resources under realistic query load.

## 8. Consistency, Compaction, Repair, and Failures

A report can be inaccurate due to **missing data or flawed processing** even when CQL syntax is valid. Analyze these sources of error:

**Consistency level.** With an appropriate replication factor, `LOCAL_QUORUM` provides different guarantees than `LOCAL_ONE`, yet multiple independent reads still do not form an **atomic snapshot across the whole dataset**. If new events keep arriving while Java pages across partitions, the sum may blend different points in time. For financial figures, define cut-off points and recomputation/reconciliation workflows.

**Tombstones and TTL.** Deleted or TTL-expired data leaves tombstones; large range scans traversing many tombstones suffer latency spikes and potential errors/warnings. Never treat `LIMIT 100` as a guarantee that only 100 live rows are touched on disk.

**Compaction.** SSTables and compaction activity affect file counts per read, I/O, and performance. Compaction strategies should match write/read patterns, TTLs, and time buckets; changing compaction cannot turn a partition-less query into an efficient distributed aggregation.

**Repair.** Repair keeps replicas synchronized per Cassandra's anti-entropy mechanics. Repair does not fix double-counted summary tables, replace event deduplication, or recover business events dropped by an upstream pipeline.

**Node/network failures.** A Java job scanning thousands of partitions risks partial timeouts. Never silently ignore failed partitions and return the partial sum as complete. Track completed scopes, checkpoints, bounded retries, and surface explicit `"complete/incomplete"` status.

**Concurrent write load.** A summary built while data streams in can drift due to watermarks and late-arriving events. Distinguish `as_of` (processed data watermark), display time, and closed reporting periods.

## 9. Profiling and Observability Before Deciding

Metrics to collect for each option:

| Area | Metrics to Observe | What It Reveals |
| --- | --- | --- |
| Cassandra queries | p50/p95/p99, read timeouts, partitions per request | Clarifies latency and fan-out |
| Cassandra data | Partition sizes, rows read, tombstones, TTLs | Spots wide scans hidden behind small outputs |
| Infrastructure | CPU, disk I/O, network, heap, compaction pressure | Prevents reporting from hurting OLTP paths |
| Java application | Rows visited, bytes transferred, page count, concurrency | Prevents unbounded memory/request growth |
| Summary tables | `as_of`, reconciliation drift, late-event counts | Evaluates freshness and accuracy |
| Analytics warehouse | Ingest lag, missing/duplicate counts, job runtime, scan cost | Ensures analytical pipeline reliability |

When comparing implementations, use **the exact same event set and cut-off timestamp** across Java, summary tables, and the warehouse. If totals disagree, check time windows, timezones, duplicate events, late arrivals, ongoing writes, paging bugs, or pipeline sync lag.

Never use one successful run on a tiny sample dataset as proof that `COUNT(*)` or a full-table scan is production-safe. Test concurrent load, large partitions, and node failures at realistic scale; record design/benchmark results here while keeping operational rollouts under a separate deployment plan.

## 10. Hands-On Practice and Applied Questions

**Exercise 1 — Bounded by partition.** Create `events_by_device_day` and insert the three sample rows. Query from 09:00 to 10:00 UTC and compute the sum in the application. Add a `HEARTBEAT` event to verify summation checks `event_type`. Assess the impact if daily volume scales to 100,000 rows.

**Exercise 2 — Spotting wide scans.** A new requirement asks to "count all transactions across 10,000 devices for the month" from `events_by_device_day`. Explain why `WHERE tenant_id = ? ALLOW FILTERING` or table-wide `COUNT(*)` is not scalable. Propose adding a query-driven summary table or OLAP report.

**Exercise 3 — Summary table.** Create `tenant_daily_payment_totals`, write totals for three days, and read the whole month via `(tenant_id, year_month)`. Describe how a late-arriving event alters the previous day's total, how to update the snapshot, and how to surface `as_of`.

**Exercise 4 — Mid-pipeline failure.** An event writes successfully to Cassandra while the summary job pauses. Describe how to detect the gap, run controlled replay, and reconcile. Explain why blindly replaying `counter + 1` fails strict accuracy requirements.

**Exercise 5 — Choosing where to compute.** Pick Java, summary table, or OLAP and justify for each: (a) total amount for one device over 5 minutes; (b) tenant dashboard refreshing every minute showing 30 days; (c) exploratory revenue query across all tenants by product, region, and quarter.

**Thought question:** If a warehouse lags 10 minutes yet reconciles accurately by watermark, whereas Java scans the whole table in near-real time yet occasionally times out or drops partitions, which is better for financial settlement reports? The choice depends on the report's **data contract**, not speed alone.

## Remember

**Cassandra is optimized for queries with known partition keys and bounded data scopes; it is not a wide-scan engine for arbitrary aggregations.** Compute in the Java application when partition and row counts are strictly capped, use summary tables for frequently read low-latency metrics, and offload to an analytics warehouse/OLAP engine for arbitrary grouping, joins, rankings, or deep historical analysis. Evaluate every option against latency, real row/partition counts, consistency, freshness, reconcilability, and failure recovery.
