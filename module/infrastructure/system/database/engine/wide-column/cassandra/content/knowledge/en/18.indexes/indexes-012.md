# Comparing Adding an Index vs. Designing a New Query-Driven Table

> **Chapter:** Indexes  
> **Topic:** Deciding between creating an index and creating a query-dedicated table in Apache Cassandra.  
> **Context:** Cassandra is a *wide-column* distributed database; design must account for partition keys, data distribution, read/write latency, replication, compaction, repair, and querying from Java applications.

## 1. The architectural question to solve

Suppose an order management application stores core data keyed by `order_id`. Initially, the API only looks up a single order by ID. Later, the product adds a screen:

> "Display a **customer's 20 most recent paid orders**, from newest to oldest."

Two approaches are commonly proposed:

1. Keep the original table and **add indexes** on `customer_id` and `status` (or whichever columns need filtering).
2. Create a **query-driven table** with `customer_id` and `status` in the partition key and `created_at` in the clustering key.

Both approaches allow accessing data by conditions other than the original primary key, yet **they do not offer the same sorting capabilities, read costs, or data synchronization responsibilities**. The right decision starts from the API contract: which fields are filtered, how many rows are returned, how results are ordered, what data freshness is required, and how large the expected load is.

This lesson aims to show when an index solves the problem well enough, when a query-driven table is required, and how to prove the choice with real measurements.

## 2. Why is the partition key the starting point?

In Cassandra:

- The **partition key** determines the token and which replicas store the partition. When the full partition key is known, the coordinator routes queries directly to the relevant replicas.
- The **clustering key** orders rows *within the same partition*. It lets Cassandra read a slice and return rows in the defined order, without providing global ordering across multiple partitions.
- **Replication factor (RF)** determines the number of copies of a partition. Adding an index does not eliminate network communication, synchronization, or distributed read costs.
- **`LIMIT 20`** only caps the number of returned rows. It does not guarantee Cassandra reads or inspects only 20 rows before producing results.

Example base table:

```cql
CREATE TABLE IF NOT EXISTS orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text,
    created_at timestamp,
    total decimal
);
```

The natural read path is:

```cql
SELECT order_id, customer_id, status, created_at, total
FROM orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

In this table, each `order_id` is its own partition key. The question "orders for customer X with status PAID" **lacks a matching partition key**. Cassandra cannot deduce a contiguous partition containing that customer's orders.

Trying to force `ALLOW FILTERING` does not fix the root issue. It permits the server to read large volumes of data and filter afterward, making latency unpredictable as the table grows. Treat `ALLOW FILTERING` as a signal to revisit your access pattern, not a default trick to make queries efficient.

## 3. Option A — Adding indexes to the original table

### 3.1. What does an index actually do?

Cassandra provides different index mechanisms depending on **version and distribution**:

| Type | Overview | Design notes |
| --- | --- | --- |
| Traditional secondary index (often called **2i**) | Maintains lookup structures for non-primary-key columns. | Generally ill-suited for broad queries, common values across many partitions, or large-scale distributed workloads. |
| **Storage-Attached Index (SAI)** | Index attached to replica storage, supporting more efficient filtering and predicate combinations on supporting versions. | SAI does not change partitioning and does not provide arbitrary global sorting. Benchmark with realistic result volumes and load. |
| Query-dedicated table | Stores an additional data representation whose partition/clustering keys match the read pattern. | Pays the price of extra rows, extra writes, and synchronized update/delete logic. |

**Regarding versions:** Apache Cassandra 5.0 supports SAI; older releases, CQL-compatible databases, or managed services may differ. Verify cluster capabilities before using SAI syntax. This lesson uses SAI to illustrate the indexing option on clusters that support it.

### 3.2. CQL example with SAI

On a Cassandra version supporting SAI, after creating `orders_by_id`:

```cql
CREATE CUSTOM INDEX IF NOT EXISTS orders_customer_sai
ON orders_by_id (customer_id)
USING 'StorageAttachedIndex';

CREATE CUSTOM INDEX IF NOT EXISTS orders_status_sai
ON orders_by_id (status)
USING 'StorageAttachedIndex';
```

Query filtering by the two indexed columns:

```cql
SELECT order_id, created_at, total
FROM orders_by_id
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND status = 'PAID';
```

For predicates supported by SAI, Cassandra can use indexes to find candidate rows rather than scanning the entire table with `ALLOW FILTERING`. However, distinguish three things:

1. **Finding rows matching predicates:** SAI supports this goal.
2. **Reading data and returning across the cluster:** still incurs partition lookups, row reads, predicate validation, and replica communication.
3. **Getting the 20 newest orders by `created_at` across multiple partitions:** two indexes on `customer_id` and `status` **do not guarantee that ordering**.

You cannot rely on the arbitrary return order of an SAI query to imply "most recent." With the base table schema above, `ORDER BY created_at DESC` is not a valid sort across a multi-partition result set. If the API strictly requires *top 20 by timestamp*, fetching from the index and sorting in Java may require collecting a large result set, paging repeatedly, and risking missed recent orders if only one page is fetched.

### 3.3. When is an index worth considering?

An index fits better when all of these hold:

- The query produces **few results**, filters selectively, and does not require specific clustering order across multiple partitions.
- Query volume, acceptable latency, and replica access overhead have been tested on near-production data.
- Search requirements are ad-hoc and changing; creating separate tables for every filter combination would be more complex than the value gained.
- Capacity exists for index storage, write-time index maintenance, compaction, and operations.

**Never use distinct value count (*cardinality*) as the sole criterion.** For instance, `status='PAID'` has low cardinality yet may match millions of orders; adding `customer_id` can shrink the candidate set dramatically. What decides viability is **candidate row/partition count and measured latency**, not simply whether a column has "high or low cardinality."

## 4. Option B — Creating a separate query-driven table

Instead of searching across `order_id` partitions, store an additional **read model** whose partition key matches the filter combination and clustering key matches display order:

```cql
CREATE TABLE IF NOT EXISTS orders_by_customer_status (
    customer_id uuid,
    status text,
    created_at timestamp,
    order_id uuid,
    total decimal,
    PRIMARY KEY ((customer_id, status), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

A sample row:

```cql
INSERT INTO orders_by_customer_status
    (customer_id, status, created_at, order_id, total)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'PAID',
    '2026-11-20 09:30:00+0000',
    11111111-1111-4111-8111-111111111111,
    249.00
);
```

The new query matches the partition key exactly and leverages clustering order:

```cql
SELECT order_id, created_at, total
FROM orders_by_customer_status
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Here Cassandra knows the exact partition from `(customer_id, status)`; inside that partition, rows are already stored in `created_at DESC` order. `order_id` acts as a *tie-breaker* so two orders created at the same instant remain distinct rows. The API can use driver paging to read subsequent pages; never emulate `OFFSET` for deep pagination.

**The new table is an intentional duplicate representation serving a query.** It does not replace `orders_by_id` if the API still needs direct lookups by ID. In Cassandra, duplicating data per access pattern is normal as long as consistency workflows and update costs are controlled.

### The new table must answer the *exact* query

This design satisfies "20 newest **PAID orders for customer X**." It does **not** automatically solve "20 newest orders of **any status** for customer X," because each status lives in a different partition.

If both queries are primary flows, you may need an additional `orders_by_customer` table partitioned solely by `customer_id` and clustered by time, or else adjust the query contract. Adding tables should be driven by real production query patterns—not necessarily one table per minor API variant.

### Avoiding oversized partitions

A customer with millions of orders in the same status can create an oversized partition. When data accumulates unboundedly, consider **monthly/daily bucketing** or size-targeted bucketing—such as adding `bucket_yyyymm` to the partition key. Queries then determine which bucket to read or read recent buckets and merge results. Bucketing must reflect actual order distributions and latency targets.

## 5. Direct comparison

| Criterion | Adding an index (e.g., SAI) | New query-driven table |
| --- | --- | --- |
| **Schema change** | Adds lookup structures to existing table. | Creates a new table with different partition/clustering keys. |
| **Flexible filtering** | Easy to add predicates supported by indexes. | Great for anticipated access patterns; new query shapes may need another table. |
| **Reading few rows in small result sets** | Can perform very well when selective and well supported by cluster. | Excellent when exact partition and clustering bounds are known. |
| **Top N by time** | Does not guarantee global order across multiple partitions. | Naturally supported when time is a clustering key inside one partition. |
| **Very broad result sets** | Can incur heavy distributed reads/lookups. | Can be efficient when scoped to a partition; large partitions must still be managed. |
| **Write cost** | Updates base row and index structures. | Writes to multiple tables; updates may require deleting/inserting in projections. |
| **Storage** | Requires index disk space. | Requires space for duplicated read-model columns. |
| **Application consistency** | Index maintained by Cassandra on base-table writes. | Application/pipeline must keep replicated projections synchronized. |
| **Operations** | Monitor indexes, compaction, read/write resources, and index builds. | Monitor per table: tombstones, repair, growth, and data sync. |
| **Primary risk** | Broad queries or wrong assumptions about ordering/limits. | Drift across read models and excessive table proliferation. |

There is no universal rule like "always build a new table" or "SAI is always faster." They optimize different cost dimensions: **indexes optimize attribute-based candidate lookup**, whereas **query-driven tables optimize physical placement and sort order** for a specific access pattern.

## 6. The price of a new read table

With `orders_by_customer_status`, when an order transitions `PENDING -> PAID`, the application cannot merely update `status` in place in the new table. Because `status` is part of the **partition key** and primary key, the order's logical location changed. The workflow must account for:

1. Updating source state in `orders_by_id`, potentially using LWT/`IF` if business rules require preventing state races.
2. Deleting the old row from the projection's `(customer_id, 'PENDING')` partition.
3. Inserting the new row into `(customer_id, 'PAID')` while preserving `created_at` and `order_id`.
4. Having idempotent retries and **reconciliation** when network errors or mid-flight failures occur so projections converge to the right state.

A CQL `BATCH` can group related writes, yet **does not turn multi-partition operations into an RDBMS transaction with multi-row isolation**. A logged batch provides atomicity for applying its mutations, not isolation from concurrent readers seeing intermediate states across partitions. When strict cross-partition invariants are required, design workflows, versioning, and recovery accordingly.

Also keep `TTL`, deletion policies, retention, and repair aligned across tables. Deleting a row creates a **tombstone**; frequent status transitions can elevate compaction and read costs. Evaluate the full data lifecycle before duplicating tables.

## 7. Scenario matrix for choosing a solution

| Access pattern | Preferred option to test | Reason |
| --- | --- | --- |
| Look up order by `order_id`. | `orders_by_id` table, no extra index. | Already has the exact partition key. |
| Find a few orders by a rare reference code, no sort needed. | SAI on reference code column if supported by cluster. | Expected result set is small; avoid maintaining a whole table for rare queries. |
| Support-tool filter by `customer_id` and `status`, small results, no top-N required. | Test SAI and benchmark before deciding. | Combining two predicates can shrink candidate sets substantially. |
| Customer X's 20 newest PAID orders, high-frequency API. | `orders_by_customer_status` table. | Partition key and clustering order match the API contract. |
| Find *all* PAID orders system-wide with millions of results. | Revisit requirements; use bucketed/sharded tables or a search/analytics system. | Indexing a common value does not shrink broad queries; a `status`-only partition turns hot. |
| Multi-dimensional summary reports scanning most data daily. | Analytics/ETL system or pre-aggregation. | Cassandra serves keyed navigation better than ad-hoc warehouse scans. |

**Practical rule:** If the API requires "returning the **first N rows in a fixed order**," try a partition/clustering table model first. If the API requires "**finding a handful of rows** by auxiliary attributes" without special global ordering, an index can be the cleaner choice.

## 8. A verifiable decision process

### Step 1 — Specify the query contract

Do not stop at "filter by customer." Document completely:

- Which `WHERE` predicates are always present vs. optional?
- Are `ORDER BY`, `LIMIT`, cursors, or next-page navigation required?
- How many **rows and partitions** does each filter value typically match?
- What is the API's average and peak QPS?
- What are p95/p99 latency targets, consistency requirements, acceptable projection lag, and writes/sec?

If numbers are unknown, mark them as assumptions to measure—never treat them as facts.

### Step 2 — Analyze routing capability

Trace the execution path:

```text
Index option
Client -> Coordinator -> SAI/secondary index on replicas
       -> locate candidate partitions/rows -> read data -> return results

Query-driven table option
Client -> Coordinator -> partition (customer_id, status)
       -> read slice by created_at DESC -> return LIMIT N
```

Both paths involve Cassandra replicas and consistency levels; the difference is whether Cassandra discovers candidates through index structures or routes directly to the target partition and clustering range.

### Step 3 — Estimate write cost and growth

For a new table, count how many projections are touched when an order is created or changes state. For indexes, list indexed columns, update rates, and index footprint over time. Measure compaction, tombstones, and disk headroom rather than timing a single `SELECT`.

A query-driven table speeds up reads while complicating the write path; an index ships quickly while risking unpredictable load from broad queries. Weigh both against your system SLOs.

### Step 4 — Test with representative data and load

Build a test environment with realistic partition counts, partition sizes, `status` distributions, large/small customers, and production-like RF. Run the **same access patterns** on both options and record:

| Metric to measure | Purpose |
| --- | --- |
| p50/p95/p99 latency under realistic concurrency | Expose tail latency when replicas or disks are busy. |
| Returned row counts and match rates | Understand actual index selectivity. |
| Read/write throughput, CPU, network, disk I/O | Spot cost shifting from reads to writes or vice versa. |
| Table/index disk growth, compaction backlog | Verify long-term operational sustainability. |
| Partition sizes, hot partitions, tombstones, timeouts | Catch issues that worsen at scale. |
| Projection lag and repair time (for new tables) | Validate application consistency requirements. |

Use CQL tracing in test environments to inspect read paths, but avoid heavy tracing in production since tracing itself adds overhead. `LIMIT` and one quick benchmark cannot substitute for sustained load testing with skewed data.

### Step 5 — Choose an option and define switchover triggers

For example: pick an index for a rarely used admin feature when results are small, sorting is unnecessary, and p95 meets targets. If results later grow, the API shifts to top-N ordering, or p99 breaches SLOs, revisit a query-driven table.

Conversely, pick a dedicated table for a hot order-history screen; maintain only projections actively used by APIs, backed by clear backfill, sync, testing, and monitoring workflows.

## 9. Rolling out changes without losing data

### If adding an index

1. Verify Cassandra version, SAI support, data types, and planned predicate operators.
2. Create the index over existing data following your version's procedures; monitor index building and cluster resources.
3. Run queries at low load first, comparing row counts and timings against existing read paths.
4. Set up alerts for low-selectivity index queries, abnormal read latencies, and compaction pressure.

### If creating a new table

1. Create the projection table with partition/clustering keys matching the access pattern; estimate partition growth over time.
2. Implement dual-writes or a retryable update pipeline handling primary-key changes and deletes.
3. **Backfill** historical data from a reliable source at a controlled rate while concurrently ingesting live updates with an ordering strategy so stale data never overwrites newer writes.
4. Reconcile results using keys/versions/timestamps and measure projection lag.
5. Shift read traffic via feature flags or gradual rollout while monitoring latency and discrepancies; keep a safe fallback read path during transition.

Specifically, never create an empty table and switch the API to read from it immediately: prior orders will not appear in the projection automatically. Cassandra **never automatically synchronizes two independent tables** simply because they store related business entities.

## 10. How should Java applications implement both read paths?

Whether using an index or a query-driven table, use **prepared statements**, bind parameter values safely, leverage driver paging, and monitor latency per query type. Never force a time-ordered top-N endpoint onto SAI if the index query cannot satisfy the sort order.

Java Driver 4.x example using the projection table:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderQueries {
    private final CqlSession session;
    private final PreparedStatement recentPaid;

    public OrderQueries(CqlSession session) {
        this.session = session;
        this.recentPaid = session.prepare(
            "SELECT order_id, created_at, total " +
            "FROM orders_by_customer_status " +
            "WHERE customer_id = ? AND status = ? " +
            "ORDER BY created_at DESC LIMIT ?"
        );
    }

    public ResultSet findRecentPaid(UUID customerId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }

        BoundStatement statement = recentPaid.bind(
                customerId, "PAID", limit)
            .setPageSize(limit)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        return session.execute(statement);
    }

    public void printRecentPaid(UUID customerId) {
        ResultSet result = findRecentPaid(customerId, 20);
        for (Row row : result) {
            System.out.println(
                row.getUuid("order_id") + " " +
                row.getInstant("created_at") + " " +
                row.getBigDecimal("total")
            );
        }
    }
}
```

This example assumes `CqlSession` has selected the proper keyspace and topology/replication config. `LOCAL_QUORUM` is one choice of read consistency, not mandatory for every system. The driver handles paging; when designing multi-page APIs, manage **paging state** safely with respect to queries and application security constraints.

If only flexible SAI filtering is needed, Java can similarly prepare `WHERE customer_id = ? AND status = ?`. However, that query's return order **must not be treated as chronological order**.

## 11. Common pitfalls

**"Create an index for any column appearing in `WHERE`."** An API involves sorting, limits, combined predicates, and pagination. Individual indexes do not automatically satisfy all of them.

**"SAI replaces query-driven table design."** SAI expands search options; it does not replace the advantage of partition/clustering keys when reading an ordered range.

**"Having `LIMIT` makes the query cheap."** `LIMIT` caps returned rows; the work to locate N matches still depends on selectivity, data distribution, and read plans.

**"Duplicating tables is always fast."** A hot or oversized partition still makes queries slow. Extra tables also add write and reconciliation burdens.

**"Logged `BATCH` ensures tables update simultaneously and readers never see intermediate state."** False. BATCH does not provide RDBMS-style multi-partition transaction isolation.

**"A new table has historical data right after `CREATE TABLE`."** False. You must backfill historical records and synchronize concurrent updates during cutover.

## 12. Self-check

1. Why doesn't adding a `status` index to `orders_by_id` automatically solve "customer X's 20 newest PAID orders"?
2. When would you choose SAI even though a dedicated table could answer the query faster? What metrics would you use to justify that choice?
3. Why must transitioning `status` from `PENDING` to `PAID` in `orders_by_customer_status` account for both deleting and inserting rows?
4. If the `(customer_id, status)` partition risks growing too large, how would you add a bucket to the key? How does that affect paging?
5. Is a fast `SELECT` over 1,000 test rows enough to roll out cluster-wide? Explain what else must be measured.

**Practical conclusion:** Start from **the queries to serve and how Cassandra locates partitions**. Use an index when you need selective lookups on auxiliary attributes without global ordering; use a query-driven table when the primary read path needs clear keys and ordering valuable enough to justify syncing duplicated data. Base the final decision on workload metrics, data distributions, and SLOs—not merely how many lines of CQL need changing.
