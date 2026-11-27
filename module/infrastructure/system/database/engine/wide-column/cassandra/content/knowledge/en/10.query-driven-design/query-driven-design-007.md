# Embracing Data Duplication to Reduce Cross-Partition Queries

## Lesson Objectives

Apache Cassandra is a distributed **wide-column** database in which the partition key determines where data is placed and how queries are routed, while clustering columns determine row order within a partition. Consequently, a table that reads very efficiently by `customer_id` may not read well by `status` or `order_id`: those input predicates identify different partitions.

Within the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, the key solution is to **intentionally duplicate the required columns across multiple tables with different access keys**. This practice is commonly called *denormalization* or *query projections*. You trade some write and storage cost for the ability to hit the right partition, avoid cross-partition scans, eliminate application-side filtering, and achieve predictable latency.

After this lesson, you will be able to:

- Explain why a customer-keyed table can force status-based queries to probe a huge number of partitions.
- Translate critical read paths into projection tables with matching partition keys and clustering keys.
- Analyze the difference between **business data duplication** and Cassandra **replication** across replicas.
- Estimate the fan-out savings alongside additional costs in writes, storage, compaction, tombstones, and synchronization lag.
- Design write operations for status transitions, retries, out-of-order records, and partial projection update failures.
- Write CQL and Java Driver examples while defining `LIMIT`, paging, and consistency level boundaries.

## 1. A Table That Serves One Read Path Well May Fail Another

Suppose a multi-tenant order service has a buyer-facing screen:

> View the 50 most recent orders for a customer in the current month, newest first.

A suitable table for this read pattern can use:

```sql
PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)
```

With partition key `(tenant_id, customer_id, month_bucket)`, Cassandra reads one known partition and returns rows in `created_at DESC, order_id DESC` clustering order. However, operations staff also need:

> View the 50 `PENDING` orders created today across **all customers in the tenant**.

The caller only has `tenant_id`, `status`, and the UTC day. It **does not know `customer_id`**, so it cannot locate a partition in the per-customer table. `status` is merely a regular column in that table—it does not automatically become a status-lookup index.

An inefficient workaround is fetching all customer IDs, reading each customer's monthly partition, filtering for `PENDING`, and merging results:

```text
tenant=T, status=PENDING, day=2026-11-21
        |
        +--> partition customer A / month 11
        +--> partition customer B / month 11
        +--> partition customer C / month 11
        |           ...
        +--> partition customer N / month 11
        |
        +--> filter status + day, merge/sort
        +--> return 50 most recent orders
```

If a tenant has 100,000 customers, the application risks probing an enormous number of partitions just to discover which customers have matching orders. Adding `LIMIT 50` to each query **neither** bounds the number of partitions probed nor produces a tenant-wide global order.

The query-driven design solution is creating a **status/day projection** whose partition key contains what the Q03 caller actually knows. The query can then target a single logical partition, provided that partition is neither oversized nor overly hot.

## 2. What Data Duplication Is—and What It Is Not

In Cassandra, the same order can appear in:

| Table | Primary Lookup Key | Use Case |
| --- | --- | --- |
| `orders_by_id` | `tenant_id + order_id` | View or verify the state of one order |
| `orders_by_customer_month` | `tenant_id + customer_id + month_bucket` | Customer's chronological order list |
| `orders_by_status_day` | `tenant_id + status + day_bucket` | Tenant status-based work queue |

All three tables share columns such as `order_id`, `created_at`, `status`, or `total_amount`. Storing them under three different partition keys is **intentional duplication to answer three distinct query shapes**.

This differs from **replication**: Cassandra stores multiple **replicas of the same partition** per replication factor and placement strategy for fault tolerance. Increasing replication factor does not change the partition key; a query missing `customer_id` still cannot locate a partition in the customer table. Conversely, projection tables do not replace the availability guarantees provided by replication.

### 2.1. Duplicate Only the Columns Needed by Each Query

A list-view table may need only ID, timestamp, status, total amount, and a short display label. You do not necessarily have to copy full shipping addresses, line-item details, or large JSON payloads into every projection.

On the other hand, projecting too few columns can force the application to issue an `orders_by_id` read for **every row in the list** (the N+1 lookups anti-pattern). Choose projection columns based on screen content, and fetch full details from the ID table only when the user opens a specific order.

## 3. Gathering Query Shapes Before Creating Projections

Suppose an e-commerce system has the following queries. Limits are **illustrative assumptions**, not universal Cassandra defaults.

| ID | Read Behavior | Mandatory Inputs | Order/Limit |
| --- | --- | --- | --- |
| Q01 | View one order by ID | Tenant, order ID | One order |
| Q02 | View one customer's orders in a UTC month | Tenant, customer ID, month | `created_at DESC`, 50 orders |
| Q03 | View `PENDING` orders created on a UTC day | Tenant, status, creation day | `created_at DESC`, 50 orders |
| Q04 | View `PENDING` orders across seven UTC calendar days | Tenant, status, seven days | Screen-wide order, 50 orders |
| Q05 | Search by keyword and price range, arbitrary sort across tenant | Multiple optional filters | No deterministic read path yet |

Q01–Q03 can have **three separate tables**. Q04 can reuse the Q03 table with **bounded** fan-out across days and application-tier merging. Q05 must be evaluated as a distinct query shape, likely better suited to a search/analytics engine than adding Cassandra tables for every filter combination.

For every query shape, also document average/peak QPS, read-to-write ratio, p95/p99 latency, customer count, order distribution across tenants/statuses, rows/bytes in the largest partition, freshness requirements, and retention policy.

## 4. Designing the Three Projection Tables

### 4.1. Q01: Lookup by ID

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    updated_at timestamp,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, status, total_amount, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

`(tenant_id, order_id)` locates one partition and one summary row. `revision` is an application-assigned business version, **not auto-incremented** by Cassandra. This table is a candidate for application-controlled source state, provided concurrency rules are enforced when using it as the authoritative state source.

### 4.2. Q02: Order List by Customer/Month

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

`month_bucket` is a `YYYY-MM` string computed from **`created_at` in UTC**, e.g., `2026-11`. Clustering by time and ID separates orders with identical creation timestamps. If querying across multiple months, the application must cap how many months are read and merge results; a single Q02 query reads **one monthly partition**.

### 4.3. Q03: Order List by Status/Day

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, day_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
LIMIT 50;
```

`day_bucket` is the **UTC date of `created_at`**, so Q03 returns "orders **created on day X** that **currently have status S**." If the product actually wants "orders **transitioned to status S on day X**," bucket by transition time and design a distinct access model; never reuse `day_bucket` for two meanings without distinguishing them.

In the Q03 table, `status` becomes part of the partition key. In the Q02 table, `status` is only a display column. The same attribute can play different roles across query-driven tables.

**Design warning:** a `(tenant_id, status, day_bucket)` partition can grow very large or hot when a tenant has many `PENDING` orders in a day. Never finalize a schema just because CQL syntax is valid; measure size and mutation rate on the largest partition.

### 4.4. Why Knowing Only Order ID Cannot Update Every Projection

`order_id` is part of the partition key in `orders_by_id`, yet it is a clustering column in both list tables. To update the right row in `orders_by_customer_month`, the application must know `customer_id`, `month_bucket`, and `created_at`. To delete the old row in `orders_by_status_day`, it must know the **old status**, creation day, creation timestamp, and ID.

Therefore, "copy locator" metadata should live in the source state or change events: `tenant_id`, `order_id`, `customer_id`, `created_at`, `old_status`, `new_status`, and `revision`.

## 5. Trading Read Fan-Out for Write and Storage Cost

Comparing the Q03 read path:

| Aspect | Customer/Month Table Only | With Status/Day Projection |
| --- | --- | --- |
| API inputs | Tenant, status, day | Same |
| Partition lookup | Unknown which customers hold matching orders | Direct `(tenant, status, day)` key |
| Queries | May probe huge numbers of customer/month partitions | One partition per tenant/status/day in illustrative schema |
| Status filtering | May filter in app or via another path | Status is part of partition key |
| Sorting | Must merge across many partitions | Pre-clustered by `created_at` inside partition |
| Data writes | Fewer copies | Extra mutation per order, plus delete/insert on status change |
| Risk | High fan-out and read latency | Must maintain projection and control hotspots |

Suppose queue Q03 receives 2,000 calls/minute and without a projection must probe an average of 5,000 partitions/call: conceptually that is **10 million logical partition reads/minute**. That is **not** an exact Cassandra RPC count—batching, caching, topology, and data determine actual cost—but it illustrates why changing the access key matters far more than micro-optimizing a single `SELECT`.

In return, each order is stored in multiple tables: increasing write-path mutations, storage footprint, tombstones on status transitions, and reconciliation work. Duplicate only query shapes with sufficient value in frequency or SLA; for rare queries with small, bounded fan-out, reading a few partitions and merging may be preferable.

## 6. What If the Status Projection Partition Gets Too Hot?

Suppose a tenant creates 250,000 orders/day and at a given moment 40% of that day's orders are `PENDING`. The status table may hold roughly **100,000 `PENDING` rows** for one `(tenant, status, day)`. At roughly 400 bytes of raw data per row, that is about **40 MB of raw data**, excluding overhead, indexes, tombstones, compaction, or replication.

No single universal number guarantees that partition is safe. A partition can also become hot from rapid status churn even when its total size is modest. When measurements show load splitting is needed, add shards:

```sql
CREATE TABLE orders_by_status_day_sharded (
    tenant_id text,
    status text,
    day_bucket date,
    shard_id int,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    revision bigint,
    PRIMARY KEY ((tenant_id, status, day_bucket, shard_id),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

With 16 shards and a fixed rule `shard_id = hash(order_id) mod 16`, an order's shard is deterministic. Reading the full status/day requires reading **at most 16 partitions**, then merging results by `(created_at DESC, order_id DESC)`. That is still fan-out, but **bounded and predictable**, instead of probing thousands of customers.

| Organization | Target Partitions for Q03 | Trade-Off |
| --- | --- | --- |
| No projection | Unknown upfront; potentially huge | Fewer extra mutations, expensive reads |
| Status/day projection | 1 | Simple reads, hot/oversized partition risk |
| Status/day/16-shard projection | Up to 16 | Reduces per-partition load, adds merge/paging work |

Never change shard count from 8 to 16 without a way to locate older data or a migration plan. The shard count is part of the contract between writes and reads; the hash rule must be uniform across all producers. If load is still low, do not add sharding just "in case."

## 7. Maintaining Duplicated Data on Writes

Read-path benefits remain sustainable only when projections converge to the correct state. Cassandra **does not automatically know** that three tables represent the same order; the application or data pipeline must update each representation.

### 7.1. Creating a New Order

An "order created" event can translate into three CQL statements:

```sql
INSERT INTO orders_by_id (
    tenant_id, order_id, customer_id, created_at,
    status, total_amount, updated_at, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket, created_at,
    order_id, status, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO orders_by_status_day (
    tenant_id, status, day_bucket, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`created_at` and bucket calculations must stay consistent. Here both `month_bucket` and `day_bucket` derive from **UTC order creation time**, even if a projection is written later. Never derive buckets from retry time, or a replayed order could land in a different month/day.

### 7.2. Status Transitions Require Deleting the Old Key and Writing the New Key

Suppose an order created on Nov 21 is `PENDING`; on Nov 22 it becomes `PAID`. Since `day_bucket` in Q03 means **order creation day**, the new projection entry still belongs to Nov 21. However, `status` is in the partition key, so the row has **moved to a different partition**.

The business steps to design:

1. Validate the new status transition against business rules and version.
2. Update `orders_by_id` with the accepted status/revision.
3. Update the `status` column in `orders_by_customer_month` using its full primary key.
4. **Delete** the row in `orders_by_status_day` under `old_status = PENDING`.
5. **Insert** the row in `orders_by_status_day` under `new_status = PAID`.

The two status-table mutations can be written as:

```sql
DELETE FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
  AND created_at = ?
  AND order_id = ?;

INSERT INTO orders_by_status_day (
    tenant_id, status, day_bucket, created_at,
    order_id, customer_id, total_amount, revision
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
```

`status` in the `DELETE` must be the **old status**; `status` in the `INSERT` must be the new status. You cannot simply run `UPDATE status = ?` on a primary key column. Deletes generate tombstones, so for entities with frequent status churn, measure read/write cost and compaction, and reconsider the model if needed.

### 7.3. Out-of-Order Events, Retries, and Duplicates

Consider two events emitted by the application:

```text
revision 11: PENDING
revision 12: PAID

Consumer receives revision 12 first and updates to PAID.
Later consumer receives revision 11 out of order and writes PENDING.
Without order control, final state regresses backward.
```

Having a `revision` column **does not automatically** make Cassandra reject older versions. Standard updates use write timestamps and Cassandra conflict resolution, not business-level comparison on `revision`.

To keep state accurate, choose and implement explicit rules:

- Maintain a **source of truth** for state with a monotonically increasing `revision`/sequence.
- Control accepted transitions, e.g., via per-`order_id` sequential processing or **LWT/CAS** on a single source row when needed. With LWT like `IF revision = ?`, callers must inspect `[applied]` and handle contention.
- Emit projection mutations **from accepted state changes**; consumers must handle duplicates, ordering, and partial failures.
- Run **reconciliation/rebuilds** for projections when updates are lost or corrupted, rather than trusting ad-hoc retries to fix every edge case.

LWT on a single source row **does not turn** updates across multiple partitions and tables into a fully isolated SQL transaction. If business requirements demand instantaneous cross-table consistency, revisit the architecture and read/write contracts.

### 7.4. Should You Use CQL `BATCH`?

A CQL batch groups multiple mutations; a **logged batch** helps ensure accepted mutations are eventually all applied after failure recovery, but it **does not provide snapshot-style observational isolation like a SQL transaction**. Reads across multiple tables/partitions can still observe partial updates at different moments.

Large batches spanning many partitions also increase coordinator/batchlog overhead and are **not** a default throughput optimization. Batches do not solve whether an older-revision event may overwrite a newer one. Separately design the event source, idempotent retries, processing order, and reconciliation.

### 7.5. Direct Writes vs. Asynchronous Updates

| Model | Mechanism | Advantage | What Must Be Solved |
| --- | --- | --- | --- |
| Write projections inside the request | Service writes tables while handling request | Simple single-request tracing; updates early | Partial failures, latency, concurrent updates/retries |
| Driven by accepted events | Write source, then consumers maintain projections | Independent scaling, reconciliation, and replay | **Eventual consistency**, lag, idempotency, out-of-order events |

With asynchronous updates, measure **projection lag** (delay between accepted source event and projection visibility) and publish acceptable freshness targets to product. If an API requires read-your-writes immediately after a write, consider reading the source table by ID or using explicit confirmation rather than assuming list tables update instantaneously.

## 8. Replication, Consistency, Compaction, and Repair Do Not Fix Business Sync Bugs

Keyspace replication factor/placement keeps multiple **replicas** per partition; consistency level (e.g., `LOCAL_QUORUM` in a matching topology) governs replica responses for reads/writes. These control consistency **within the read/write path of data already sent to Cassandra**.

If `orders_by_id` already updated to `PAID` while the consumer has not yet written `orders_by_status_day`, raising the consistency level on the status query **cannot conjure the missing projection mutation**. That discrepancy is application/business-level, not replica lag within one partition.

- **Repair** synchronizes replicas via Cassandra's anti-entropy mechanisms; it does not know a pipeline forgot to delete a `PENDING` row.
- **Compaction** merges SSTables and clears eligible tombstones; it will not materialize a missing `PAID` row in an unwritten projection.
- **TTLs** can expire projections at different times if retention policies differ; align per-table lifecycles intentionally.

Therefore, projection tables need **entity-level reconciliation**: comparing revision/status between source and projections, detecting missing/duplicate IDs, tracking unapplied mutation backlogs, retrying, and rebuilding tables when necessary.

## 9. Using Projections from Java

Example using **DataStax Java Driver 4.x**. The application queries the exact table matching the keys provided by the API, using prepared statements:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.UUID;

public final class OrderReader {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement byCustomerMonth;
    private final PreparedStatement byStatusDay;

    public OrderReader(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, status, total_amount, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.byCustomerMonth = session.prepare(
            "SELECT order_id, created_at, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
        this.byStatusDay = session.prepare(
            "SELECT order_id, customer_id, created_at, total_amount " +
            "FROM orders_by_status_day " +
            "WHERE tenant_id = ? AND status = ? AND day_bucket = ? " +
            "LIMIT 50"
        );
    }

    public Row findById(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet customerOrders(
        String tenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            byCustomerMonth.bind(tenantId, customerId, utcMonth.toString())
        );
    }

    public ResultSet pendingOrders(
        String tenantId, LocalDate createdUtcDay
    ) {
        return session.execute(
            byStatusDay.bind(tenantId, "PENDING", createdUtcDay)
        );
    }
}
```

`UUID` maps to CQL `uuid`, `LocalDate` maps to `date`, and `YearMonth.toString()` produces the `YYYY-MM` bucket string. `YearMonth` carries no timezone; when deriving it from `Instant createdAt`, always use UTC consistently. The service must authenticate/authorize tenants and set timeouts and query limits; having `tenant_id` in the partition key **does not replace** authorization.

Manage a shared `CqlSession` over the application lifecycle. A dedicated prepared statement per query shape guarantees inputs always supply the required keys; never build arbitrary `WHERE` strings from every possible filter expecting any schema to handle them.

### 9.1. `LIMIT`, Page Size, and Reading Multiple Buckets

`LIMIT 50` in the queries above caps **total query rows**, suitable for previews. If an API needs multiple pages from the same partition, use a query **without a hardcoded `LIMIT 50`**, set driver page size, and handle the opaque paging state tied to the query shape and bound values.

```java
PreparedStatement customerHistory = session.prepare(
    "SELECT order_id, created_at, status, total_amount " +
    "FROM orders_by_customer_month " +
    "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ?"
);

var statement = customerHistory
    .bind(tenantId, customerId, monthBucket)
    .setPageSize(50);
```

Synchronously iterating the entire `ResultSet` can cause the driver to fetch extra pages; an endpoint returning one page must control rows consumed and continuation tokens. When data mutates during pagination, multiple pages do not inherently form an immutable snapshot.

For Q04 across seven days or sharded projections, track read cursors per partition, merge in `(created_at DESC, order_id DESC)` order, and cap total partitions, rows, and bytes. A single query's paging state **does not** capture progress across a multi-partition fan-out.

## 10. When Should You Not Add Another Projection?

Denormalization is a tool for critical read paths, not a goal in itself. Before creating a new table, ask:

1. Does this query have enough frequency or SLA criticality to justify ongoing write, storage, and reconciliation costs?
2. Does the API already have the keys of an existing table, or can it obtain them via one small lookup?
3. If the query only touches two or three known buckets, is a small bounded fan-out sufficient?
4. Does the query combine arbitrary filters and sorts? If so, a search/analytics engine or narrower feature scope may fit better.
5. Does the projection key attribute (such as `status`) change frequently? Are the delete/insert/tombstone costs acceptable?
6. Are TTL policies, access controls, and projection recovery/rebuild procedures in place if data is lost?

Secondary indexes or **Storage-Attached Indexes (SAI)**, when supported by your Cassandra version/deployment, can be evaluated for certain filters. They do not guarantee global `ORDER BY` or efficient execution for arbitrary filter combinations. Benchmark selectivity, scanned data volume, and latency on real workloads before committing.

## 11. Verification and Operations Checklist

| Item | Test Scenario | What to Observe |
| --- | --- | --- |
| Query routing | Q01/Q02/Q03 have full partition keys | Partitions touched and p95/p99 latency |
| Hot partitions | Highest-traffic tenant and status | Rows/bytes, mutation rate, hot replicas |
| State transitions | `PENDING → PAID` | Old row deleted, new row present after projection converges |
| Out-of-order events | Revision 12 processed before 11 | Final state never regresses |
| Retries/timeouts | Mutation applied but client missed ACK | No duplicate rows or lost updates |
| Partial failures | Lookup updated, status projection missed | Backlog visibility, retries, detection, reconciliation |
| TTL, deletes, tombstones | Frequent state transitions or expired data | Queries still meet SLA; no unintended TTL mismatches |
| Multi-day/sharded queries | Q04 and 16-shard table | Fan-out bounds, correct merge, safe paging |
| Node failure, repair | Slow or down replica | Proper replica sync; not confused with projection sync |
| Read-after-write | Update status then open queue | Sync lag within product commitments |

Measure **projection lag**, unapplied mutation counts, revision/status mismatches during reconciliation, read/write p95/p99, tombstones scanned, and partitions touched per request. A CQL query working on a handful of sample rows **does not prove** the read path is optimal or the write path recovers cleanly from failures.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using one customer table for all filters | Must scan many partitions or filter regular columns | Create projections for primary queries |
| Copying entire payloads into every projection | Inflates write, storage, and column-sync costs | Project only the columns needed for return |
| Building status/day projections without sizing the largest tenant | Hot or oversized partitions | Measure load; bucket/shard when needed |
| Running `UPDATE status` when status is in primary key | Keys cannot be changed via standard updates | Delete old key and insert new key |
| Assuming a `revision` column blocks stale updates automatically | Data can regress backward | Use CAS/ordering controls and reconciliation |
| Treating logged batches like isolated SQL transactions | Readers can observe partial updates | Understand batch limits; use retries/reconciliation |
| Raising consistency level to sync projections | Projection lag or missing mutations still occur | Monitor pipeline and recover failures |
| Using `LIMIT 50` across hundreds of partitions | Fan-out and merging remain expensive | Bound buckets/shards and benchmark realistically |
| Relying on repair to fix app bugs | Projections remain missing rows never written by source | Run business-level reconciliation and rebuilds |
| Adding a new table for every rare filter | Schema and write paths become unmaintainable | Prioritize valuable query shapes; explore alternatives |

## 13. Practice Exercise

A Java support-ticket management application has the following columns:

```text
tenant_id, ticket_id, requester_id, created_at,
status, priority, title, updated_at, revision
```

Requirements:

1. **R1:** Staff opens a ticket by `ticket_id`.
2. **R2:** Users view their 20 most recent tickets within a UTC month.
3. **R3:** Team leads view the 50 `OPEN` tickets created on a given day, newest first, across the tenant.
4. **R4:** When a ticket transitions `OPEN → RESOLVED`, the OPEN queue must no longer contain that ticket once projections converge.
5. **R5:** Search tickets by title keyword and sort by `priority` across the entire tenant.

Answer the following:

1. Choose tables and partition keys for R1–R3; why can the three queries not naturally share a single partition key?
2. Write the CQL `CREATE TABLE` and `SELECT` for R3. Should the day bucket derive from creation time or transition time?
3. Describe the operations in R4: ID table, requester/month table, deleting the old status row, and writing the new status row.
4. If a tenant receives 500,000 new tickets/day, what must you measure before using `(tenant, OPEN, day)`? When do you add shards?
5. If revision 8 arrives after revision 9, what rule prevents current state from regressing?
6. Why are R5 requirements not naturally served by the three tables above? Propose an alternative access approach and clarify SLA/consistency questions.

**Reference guidance:** R1 uses `tickets_by_id` with partition key `(tenant_id, ticket_id)`. R2 uses `tickets_by_requester_month` keyed by `(tenant_id, requester_id, month_bucket)` with clustering `created_at DESC, ticket_id DESC`. R3 uses `tickets_by_status_day` keyed by `(tenant_id, status, day_bucket)` with similar clustering, and `day_bucket` must consistently derive from creation date if the requirement says "created on that day." R4 requires deleting the row from the OPEN partition and writing to RESOLVED while updating the ID and requester tables. R5 is a different search/sort problem requiring evaluation of indexes or a dedicated search engine rather than merely adding `ALLOW FILTERING`.

## Conclusion

In Cassandra, **embracing intentional data duplication** lets each critical query hit a matching partition and clustering order, reducing fan-out and application-side filtering/merging. In return, each projection adds mutations, storage overhead, and business synchronization responsibilities. A solid design proves both **bounded read-path cost** and **write-path correctness across key changes, retries, out-of-order events, and failure recovery**. Choose projections based on real needs, test peak workloads, and maintain reconciliation so all views converge to the true state.
