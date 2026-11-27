# Designing Lookup Tables and Time-Ordered History Tables

## Lesson Objectives

In Apache Cassandra, a business domain often has at least two very different data-reading needs: **quickly looking up the current state of an entity** by its identifier, and **viewing that entity's progression over time**. For example, a support agent needs to know immediately what status an order is currently in, and then open the history of status transitions for that same order.

These two requirements may concern the same entity, yet they require **two access paths**: a lookup table by ID and a time-ordered history table. Cassandra's query-driven design embraces storing data in multiple intentional representations so each critical query hits an appropriate partition, rather than relying on `JOIN`s, full-table filtering, or global sorting.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Concepts are framed in the context of distributed wide-column systems, CQL, replication, consistency, compaction, repair, error handling, and Java application integration.

After this lesson, you will be able to:

- Distinguish the requirements of a **lookup table** versus a **time-series/history table** and choose matching partition keys and clustering columns.
- Write CQL tables and queries for ID lookup, single-bucket history reads, range filtering, and pagination.
- Decide how to bucket by day/month, handle multi-bucket reads, late-arriving events, and identical timestamps.
- Recognize responsibilities for maintaining multiple tables, keeping current state accurate under out-of-order events, TTLs, tombstones, and temporary divergence across business projections.
- Design clean read contracts for Java applications and build a verification checklist before production rollout.

## 1. Same Order, Two Different Questions

Suppose a Java service manages orders across multiple tenants:

> **Question A:** "What status is order `orderId` currently in?"

> **Question B:** "Which events occurred on this order in November, newest first?"

For Question A, the caller has `tenantId` and `orderId`; it needs a single result and does not care about chronological history. For Question B, the caller also knows `tenantId` and `orderId`, but wants **multiple rows ordered by time**, potentially with range filtering and pagination.

| Criterion | ID Lookup Table | Time-Ordered History Table |
| --- | --- | --- |
| Purpose | Return the latest status/attributes of an order | Return an ordered sequence of events or versions over time |
| Candidate partition key | `(tenant_id, order_id)` | `(tenant_id, order_id, month_bucket)` |
| Clustering key | Not needed if each order is one row | `(event_time, event_id)` |
| Result shape | One current record | An ordered list of events |
| Volatility | Updated whenever status/summary changes | Mostly appends new events; avoid unnecessary history edits |
| Bounding strategy | Read one deterministic partition | `LIMIT`, paging, bucketing, and fan-out caps |
| Data lifecycle | May need to persist for the full order lifetime | May have a separate retention/TTL policy |

Merely because both tables contain `order_id`, `status`, or `updated_at` does not mean they can be collapsed into one table and still serve both read paths efficiently.

### 1.1. A Lookup Table Is More Than Just an Index

A lookup table in Cassandra can store **all the information the UI needs** to return immediately—such as buyer name, total amount, current status, and last-change timestamp. Alternatively, it can be purely a **key-mapping** table (for example, from an external reference to `order_id`) so the next step reads the main table.

Choosing between **returning data directly** and **looking up a key then reading again** is a trade-off: storing extra fields increases write cost and projection-drift risk; an extra read adds a round-trip and latency.

### 1.2. A History Table Is Not Simply "When Was It Updated?"

An `updated_at` column on a lookup row tells you only one recent timestamp; it **cannot** reconstruct every event: who changed the status, old/new status, reason, and exact occurrence time. A history table stores **each change as a separate row**, uniquely identified and ordered chronologically.

If the domain requires an immutable audit trail or legal compliance, separately define data-protection controls, edit/delete restrictions, and event-source trustworthiness. An ordinary Cassandra table with application-level append-only writes **is not automatically a legally immutable log**.

## 2. Gathering Query Contracts Before Choosing Tables

Illustrative query inventory:

| ID | Need | Mandatory Inputs | Scope and Order | Design Direction |
| --- | --- | --- | --- | --- |
| Q01 | View order status and summary info | `tenant_id`, `order_id` | Exactly one order | Table `orders_by_id` |
| Q02 | View 50 newest order events in a UTC month | `tenant_id`, `order_id`, `month_bucket` | Single partition, `event_time DESC` | Table `order_events_by_month` |
| Q03 | View events within an hour range in that month | Same keys as Q02, `from`, `to` | Single partition, range on `event_time` | Reuse Q02 table |
| Q04 | View last 3 months of history | Tenant, order, month range | Multiple partitions, merged by time | Bounded cross-month reads |
| Q05 | Look up order by partner transaction reference | Tenant, `external_ref` | Exactly one reference | Requires lookup path by external code |
| Q06 | View `FAILED` events across all orders of a tenant on a day | Tenant, day, event type | Many orders, tenant-wide ordering needed | Different query shape; design separately |

Numbers like "50 events" and "3 months" are **business assumptions for the example**, not Cassandra defaults.

Before locking the schema, add average/peak QPS, p95/p99 targets, row sizes, maximum events per order/month, likelihood of late events, history retention, and read-after-write requirements. These numbers decide whether smaller buckets are needed.

## 3. Designing the Identifier Lookup Table

### 3.1. Schema Serving Q01

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    current_status text,
    total_amount decimal,
    last_event_time timestamp,
    last_event_id uuid,
    last_event_month text,
    PRIMARY KEY ((tenant_id, order_id))
);
```

`(tenant_id, order_id)` is a **composite partition key**. One tenant/order pair identifies one logical partition; no clustering column is needed because each key pair represents a single summary row.

Do not pick `tenant_id` as a single partition key for all orders of a tenant: in large tenants, one partition can grow unboundedly and become hot. Likewise, do not pick `order_id` alone if access contracts must always identify and scope the tenant; including tenant in the key expresses the lookup path and isolates the keyspace in the data model. **Authorization** must still be enforced in the application layer, not delegated solely to the partition key.

### 3.2. Looking Up Exactly One Order

```sql
SELECT customer_id, created_at, current_status, total_amount,
       last_event_time, last_event_id, last_event_month
FROM orders_by_id
WHERE tenant_id = ?
  AND order_id = ?;
```

The `?` placeholders are for **prepared statements**. When using interactive `cqlsh`, substitute valid CQL literals. The query supplies the full partition key and reads one deterministic partition; typically `LIMIT 1` is unnecessary to mean "one order" because the schema already holds at most one row per key.

On the lookup row:

- `current_status` is the **current summary status**; this is business data that must be synchronized when new events arrive.
- `last_event_time` and `last_event_id` let the UI see which event snapshot is currently summarized.
- `last_event_month` can serve as a **hint** for the most recent history bucket acknowledged by the pipeline, but it neither proves older months are non-empty nor replaces rules for probing all months.

**Important:** `last_event_time` is not automatically updated by Cassandra when a new row enters `order_events_by_month`. The application or pipeline must maintain lookup columns under an explicit rule.

### 3.3. When Lookups Have Multiple Key Types

If support staff only have a payment gateway reference (`external_ref`) without `order_id`, `orders_by_id` does not offer a single-partition lookup by that code. You can create a mapping table if `external_ref` is unique within a tenant:

```sql
CREATE TABLE order_id_by_external_ref (
    tenant_id text,
    external_ref text,
    order_id uuid,
    PRIMARY KEY ((tenant_id, external_ref))
);

SELECT order_id
FROM order_id_by_external_ref
WHERE tenant_id = ? AND external_ref = ?;
```

The service then uses `(tenant_id, order_id)` to read `orders_by_id`. Two reads can be appropriate when external-code lookups are infrequent and only need a mapping; if the API requires a single round-trip, consider duplicating the required result columns and accepting the maintenance responsibility.

If `external_ref` can be **non-unique**, the single-row mapping table above will overwrite entries sharing the key. In that case, change the business contract or schema so one code can map to multiple orders, and define result ordering/selection.

## 4. Designing the Time-Ordered History Table

### 4.1. Why Are Buckets Needed?

If an order's entire history sits inside `(tenant_id, order_id)`, row counts can grow indefinitely over time. For orders with heavy event activity, large partitions complicate load control, SSTables, latency, and tombstone handling.

For requirements Q02–Q03, we choose **UTC monthly buckets**:

```sql
CREATE TABLE order_events_by_month (
    tenant_id text,
    order_id uuid,
    month_bucket text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    status_before text,
    status_after text,
    actor_id uuid,
    note text,
    recorded_at timestamp,
    PRIMARY KEY ((tenant_id, order_id, month_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

In this example, `month_bucket` is a standardized **`YYYY-MM` UTC string** such as `2026-11`. Enforce a single canonical format on both writes and reads; you may use another type or format if the application controls it uniformly, but never let `2026-11` and `2026-011` become two spellings for the same month.

The schema provides:

1. **Partition key** `(tenant_id, order_id, month_bucket)` locates an order's history within one month.
2. **Clustering column** `event_time` orders events chronologically.
3. **Clustering column** `event_id` distinguishes events sharing the same `event_time`, preventing primary key collisions.
4. Columns `event_type`, `status_before`, `status_after`, `actor_id`, and `note` hold event payload; they do not automatically support arbitrary filtering.

```text
Partition (tenant-A, order-42, 2026-11)
    (2026-11-21T10:40:00Z, event-c)  -> DELIVERED
    (2026-11-21T09:15:00Z, event-b)  -> OUT_FOR_DELIVERY
    (2026-11-20T15:00:00Z, event-a)  -> PACKED

Partition (tenant-A, order-42, 2026-10)
    (2026-10-30T08:00:00Z, event-x)  -> CREATED
```

Two months are **two distinct partitions**; `DESC` ordering is guaranteed only within each respective partition. IDs in the diagram are illustrative labels and do not represent actual `uuid` key ordering when timestamps match.

### 4.2. Q02: Fetching the Newest Events in a Month

```sql
SELECT event_time, event_id, event_type,
       status_before, status_after, actor_id, note, recorded_at
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?
LIMIT 50;
```

With the full partition key and descending `CLUSTERING ORDER BY`, the query reads the newest events first within the month. `LIMIT 50` is the **total row limit** for this query, suited for a 50-row preview.

If the API defines "50 most recent events **regardless of month**," Q02 alone is not enough. You must specify how to pick the starting month, rules for probing earlier months, and stopping conditions. Never rely on `last_event_month` as a complete solution when months may be empty or events arrive late.

### 4.3. Q03: Filtering a Time Range Within a Month

```sql
SELECT event_time, event_id, event_type, status_after, note
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

`event_time` is the **first clustering column**, allowing range narrowing. Use a half-open interval `[fromInclusive, toExclusive)` to avoid double-counting at boundaries. For example, an event occurring at exactly 11:00 belongs to `[11:00, 12:00)` and not to `[10:00, 11:00)`.

Ensure both bounds belong to the queried `month_bucket`. For a range crossing a month boundary, split it into per-month sub-ranges:

```text
Request: [2026-10-31T23:30:00Z, 2026-11-01T00:30:00Z)

Read partition 2026-10:
    [2026-10-31T23:30:00Z, 2026-11-01T00:00:00Z)
Read partition 2026-11:
    [2026-11-01T00:00:00Z, 2026-11-01T00:30:00Z)
```

The `month_bucket = ?` predicate cannot automatically expand into the next month when the time range crosses the boundary.

### 4.4. Q04: History Across Multiple Months

If a user wants all events for an order from September through November, the application can derive buckets `2026-09`, `2026-10`, and `2026-11`, then:

1. Read the corresponding partitions within the agreed maximum month cap.
2. Fetch each partition's rows ordered by clustering `(event_time DESC, event_id DESC)`.
3. Merge the result streams in that same order for display.
4. Track read position / paging state per partition, along with total row and payload caps.

A **sliding window** of exactly 90 × 24 hours can touch **four calendar months**, depending on the start time; it is not identical to "three calendar months." The API contract must define which meaning applies before estimating partition counts.

Do not assume using `IN` across multiple partition keys combined with `ORDER BY` will automatically yield global ordering at low cost. If full-lifetime history queries have high traffic or strict SLAs, consider different bucketing, a specialized projection table, or a controlled dedicated read flow.

## 5. Coordinating Lookup and History Tables on the Write Path

A new event creates two distinct needs:

- **History:** write a row representing the event.
- **Lookup:** update current status or summary metadata *if* that event is legitimately the latest valid state under business rules.

### 5.1. Write Operation Example

Assume the application has validated and normalized input values:

```sql
INSERT INTO order_events_by_month (
    tenant_id, order_id, month_bucket, event_time, event_id,
    event_type, status_before, status_after, actor_id, note, recorded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

After processing the event against valid state-transition rules, a lookup table update might look like:

```sql
UPDATE orders_by_id
SET current_status = ?,
    last_event_time = ?,
    last_event_id = ?,
    last_event_month = ?
WHERE tenant_id = ?
  AND order_id = ?;
```

These two CQL statements are **insufficient** to guarantee business correctness if executed independently and concurrently in all scenarios. Cassandra resolves cell-level conflicts using write timestamps; **the event that arrives later at the server is not necessarily the event that occurred later**.

For example:

```text
09:00  Order moves to PACKED (event E1)
10:00  Order moves to SHIPPED (event E2)

Application receives E2 first and updates lookup = SHIPPED.
Then E1 arrives late and overwrites lookup = PACKED if updated unconditionally.

History may contain both E1 and E2 in the right event_time order;
meanwhile lookup reflects the older event.
```

Therefore, define current state using a **reliable version/sequence**, per-order sequential processing, or a **conditional update/LWT** that checks version before writing. The application must compare valid versions and handle retries/failures; you cannot automatically rely on `MAX(event_time)` from the history table to keep the lookup row accurate.

### 5.2. Example of Conditional Version Control

One approach when the domain has a monotonically increasing **revision** is adding a `revision bigint` column to the lookup row at **schema design time**, and using a conditional update after reading the current value:

```sql
-- Illustrated with a lookup schema containing an added revision bigint column.
-- Apply only after the application validates that nextRevision is valid.
UPDATE orders_by_id
SET current_status = ?,
    last_event_time = ?,
    last_event_id = ?,
    last_event_month = ?,
    revision = ?
WHERE tenant_id = ?
  AND order_id = ?
IF revision = ?;
```

The `IF revision = ?` clause uses a **lightweight transaction (LWT)**; the caller must inspect `[applied]` and, when not applied, re-read and resolve contention per business rules. The statement itself does not prove that `nextRevision` is greater than the old value; that is the responsibility of the revision generator/algorithm. LWTs incur higher cost and latency than regular writes, so adopt them only after confirming consistency requirements.

Serialized event consumption partitioned by `(tenant_id, order_id)` is another option if the architecture guarantees source and processing order. Either way, plan for duplicate events, late arrivals, retries, transient failures, and reconciliation between lookup and history.

### 5.3. Should You Use CQL `BATCH`?

A logged batch helps mutations across multiple partitions be **recorded so they are eventually all applied** after partial failures, but it **does not provide relational-database transaction isolation**: readers can still observe part of the changes before the rest complete. Never use multi-partition batches as a throughput trick or as a substitute for business-level consistency management.

For systems requiring durable event emission and persistence, use a pipeline with a durable log/outbox, idempotent retries, and reconciliation. Design for real failure modes: connection drop after a write succeeds, duplicate delivery, lookup updated while history is missing, or vice versa.

### 5.4. Identifiers and Event Replay

Events may be redelivered after timeouts. If you preserve the **exact same** `(tenant_id, order_id, month_bucket, event_time, event_id)` and identical payload, re-writing to history is a form of **key-idempotent upsert**. Keep in mind:

- The same `event_id` with a **different `event_time`** creates a different row; this schema does not enforce uniqueness of `event_id` across months or timestamps.
- If the payload or write timestamp differs, rewriting can alter cell values.
- If TTLs are used, rewriting can alter expiration times of the written cells; never assume replay is harmless under every retention policy.

If global uniqueness of `event_id` within a tenant is required, design ID generation/deduplication or a dedicated mapping table; do not infer uniqueness simply because `event_id` is in the clustering key.

## 6. History Pagination and Read-Scope Limits

In Cassandra, `LIMIT`, page size, and API limits serve three distinct purposes:

| Concept | Meaning | Use When |
| --- | --- | --- |
| `LIMIT 50` in CQL | Caps total rows returned by **the query** | Previewing 50 events |
| Driver page size | Target number of rows per page fetch | API loads multiple pages of the same query shape |
| API limits | Caps months, partition count, total rows/bytes, and processing time | Preventing fan-out and overly broad queries |

To load multiple pages from a single bucket, use a query **without a hardcoded `LIMIT 50`**:

```sql
SELECT event_time, event_id, event_type, status_before, status_after, note
FROM order_events_by_month
WHERE tenant_id = ?
  AND order_id = ?
  AND month_bucket = ?;
```

Then configure **page size** on the driver and return a continuation token to the caller while more data exists. Driver **paging state** is opaque data bound to the query and bound values; never edit it, reuse it with different keys or ranges, or treat multiple pages as an immutable snapshot if concurrent writes/deletes occur.

When paginating **across multiple months**, a single token from a single-month query cannot describe overall progress. The service must design how to track per-month cursors, merge order, logical snapshot cutoffs if product requires them, and stopping conditions. Protect integrity of API-issued tokens and always re-verify tenant/access permissions on continuation calls.

Returning few rows does not guarantee low resource usage: accumulated **tombstones** or probing many partitions to gather 50 rows can still make a query slow.

## 7. Connecting from a Java Application

The example below uses the **DataStax Java Driver 4.x** API for both read paths. `CqlSession` is created and managed with the service lifecycle, not created per request.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.YearMonth;
import java.util.UUID;

public final class OrderReader {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement historyByMonth;

    public OrderReader(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, current_status, total_amount, " +
            "last_event_time, last_event_id, last_event_month " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.historyByMonth = session.prepare(
            "SELECT event_time, event_id, event_type, status_before, " +
            "status_after, actor_id, note, recorded_at " +
            "FROM order_events_by_month " +
            "WHERE tenant_id = ? AND order_id = ? AND month_bucket = ?"
        );
    }

    public Row getOrder(String tenantId, UUID orderId) {
        return session.execute(byId.bind(tenantId, orderId)).one();
    }

    public ResultSet history(
        String tenantId, UUID orderId, YearMonth utcMonth
    ) {
        String monthBucket = utcMonth.toString(); // YYYY-MM
        BoundStatement statement = historyByMonth
            .bind(tenantId, orderId, monthBucket)
            .setPageSize(50);
        return session.execute(statement);
    }
}
```

The example illustrates only **how to invoke the two read paths**. A production application must:

1. Authenticate and authorize `tenantId/orderId` before executing queries.
2. Ensure `utcMonth` is computed in **UTC** if derived from `event_time`; `YearMonth` itself carries no timezone.
3. Design APIs to return one explicit page: synchronously iterating an entire `ResultSet` can cause the driver to automatically fetch additional pages. Explicitly control rows consumed and paging state using your driver version's API.
4. Configure timeouts, consistency levels, fan-out caps, error reporting, and retries appropriate for the service.

On the write path, the monthly bucket can be computed in Java as:

```java
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneOffset;

public static String monthBucket(Instant eventTime) {
    return YearMonth.from(eventTime.atZone(ZoneOffset.UTC)).toString();
}
```

This rule must be consistent across all producers and consumers. Using `recorded_at` for bucketing on writes while using `event_time` to select the month on reads can place late-arriving events into a different month so they do not appear in the expected query.

## 8. TTL, Compaction, Repair, and Consistency

### 8.1. Choosing Different Lifecycles for Lookup and History

Lookup rows may need to live until an order completes and business retention expires. History might be kept for 90 days, 12 months, or longer depending on product requirements. If applying TTL on the history table, CQL can use:

```sql
-- Example of 90 days in seconds; use only if retention policy permits.
INSERT INTO order_events_by_month (
    tenant_id, order_id, month_bucket, event_time, event_id,
    event_type, status_before, status_after, actor_id, note, recorded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL 7776000;
```

In Cassandra, TTL applies at the cell level; expiration generates deletion markers (tombstones) cleaned up by storage/compaction when eligible. A 90-day TTL **is not equivalent to** "retain exactly three calendar months"; confirm retention goals, tombstone volume, and deletion policy before using it.

Never blindly apply the same TTL to both lookup and history: if the lookup row expires earlier than history, Q01 loses current status while the timeline still exists. Conversely, if history expires while lookup still points to `last_event_month`, the UI must handle finding no events in the indicated bucket.

### 8.2. Compaction Aligned with Write Patterns and TTL

History tables are predominantly append-only and may carry time-based TTLs, making **TimeWindowCompactionStrategy (TWCS)** worth evaluating for suitable time-series workloads. However:

- TWCS does not automatically guarantee low cost if there are many **out-of-window** writes/updates or inappropriate mixing of long-lived and short-lived data.
- Late-arriving events, heterogeneous TTLs, and mutations after a window closes must be evaluated when choosing strategy and window size.
- A lookup table updated repeatedly in place has a very different write pattern from history; do not blindly apply the same compaction strategy to both.

Compaction does not replace proper partition keys and clustering keys. Key metrics include SSTables per read, tombstones scanned, partition size, p95/p99 latency, and disk load.

### 8.3. Replication and Consistency Do Not Synchronize Business State Across Two Tables

Keyspace replication factor and placement define replicas; per-operation read/write consistency levels (such as `LOCAL_QUORUM` in an appropriate topology) determine replica acknowledgment. Choosing the right consistency level satisfies fault-tolerance and read-after-write requirements within design bounds, but it **does not turn** lookup and history writes into a SQL transaction capable of reading both tables at an identical logical instant.

**Repair** resolves replica divergence within Cassandra's storage mechanisms; it **does not** detect that an application pipeline missed a history record or failed to update a lookup row. That requires business-layer reconciliation. Write pauses, network faults, and retries must be included in operational testing.

## 9. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using one table with only `PRIMARY KEY (tenant_id, order_id)` for the timeline too | Only one row per order; cannot store multiple historical events | Separate lookup table and time-clustered history table |
| Using `PRIMARY KEY ((tenant_id, order_id), event_time)` for unbounded history | Partitions can grow very large over time | Evaluate daily/monthly buckets and maximum size |
| Keeping only `updated_at` as an audit trail | Loses intermediate events, actors, and before/after states | Store each event as a row with its own ID and timestamp |
| Using `event_time` alone as the clustering key | Events with equal timestamps share the same primary key | Add `event_id` or a tie-breaking sequence |
| Always overwriting lookup with late-arriving events | Current status can regress backward | Apply version/ordering rules, CAS, or serialized processing |
| Enabling `ALLOW FILTERING` to search by external code | Unpredictable scans and read cost | Create a proper `external_ref → order_id` mapping table |
| Assuming `LIMIT 50` makes every history query cheap | Tombstones and multi-month fan-out still cost work | Bound buckets, page size, bytes, and benchmark realistically |
| Reusing the same TTL for lookup and history out of habit | Current status disappears or timeline mismatches expectations | Define each table's lifecycle independently |
| Expecting repair to restore projections missed due to app bugs | Lookup and history remain logically inconsistent | Use durable queues, retries, reconciliation, and rebuild mechanisms |

## 10. Verification Checklist Before Finalizing the Schema

| Check | Passing Signal |
| --- | --- |
| Does lookup have complete inputs? | Every Q01 request has `tenant_id` and `order_id` |
| Is an external reference unique? | Clear uniqueness rule confirmed before creating mapping |
| Does history have a suitable partition key? | Caller knows the order and target range/bucket |
| Does clustering match read order? | `event_time DESC, event_id DESC` serves list and range reads |
| Can events share timestamps? | Deterministic tie-breaker key with sufficient uniqueness |
| Can events arrive late or out of order? | Lookup updates obey version rules with retry/reconciliation |
| Are multi-bucket reads needed? | Max months defined with merge and paging logic |
| How large is the largest partition? | Projected rows/bytes/peak writes per order and bucket documented |
| Are TTL and compaction appropriate? | Per-table retention, tombstones, and late events accounted for |
| Are SLAs and consistency verified? | Tested large datasets, failures/retries, read-after-write, and p95/p99 |

Verify CQL via `cqlsh`, prepared statements via the Java driver, multi-month datasets, same-timestamp events, UTC boundary ranges, histories with tombstones, post-write network failures, and late-arriving events. A `SELECT` succeeding on a few sample rows **does not prove** the table handles production traffic.

## 11. Practice Exercise

A delivery platform needs two screens:

1. Enter `parcelId` to view the **current status** of a parcel and its latest change timestamp.
2. View the parcel's **scan history** for a UTC day, newest first, loading 20 records per page.

Each scan has `tenant_id`, `parcel_id`, `scan_time`, `scan_id`, `location_id`, `status_after`, and `received_at`. Events can arrive late; a parcel can be scanned multiple times within the same millisecond.

Solve the following:

1. Choose the partition key and columns for the lookup table to answer the current-status requirement.
2. Choose the partition key, clustering columns, and ordering for the daily scan history table; write `CREATE TABLE`.
3. Write CQL queries for the status screen and for history within `[09:00, 12:00)` on the same day.
4. Distinguish `LIMIT 20` from driver page size 20 if the UI must load hundreds of records across multiple pages.
5. Describe the bug that occurs if a 09:00 scan arrives at the server **after** a 10:00 scan, while both unconditionally update the lookup table.
6. If product adds "find all parcels scanned at a given location on a day," explain why the first two tables are insufficient and propose a query-driven approach.

**Reference guidance:** The lookup table can use `PRIMARY KEY ((tenant_id, parcel_id))`. The history table can use `PRIMARY KEY ((tenant_id, parcel_id, day_bucket), scan_time, scan_id)` with `DESC` order, since `scan_id` distinguishes records sharing `scan_time`. For the location/day query, you may need another table keyed by `tenant_id`, `location_id`, and an appropriate bucket, then clustered by time—after estimating load and size for the busiest location. Lookup updates must follow event-order/version rules rather than "whichever arrives last wins."

## Conclusion

In Cassandra, an **ID lookup table** optimizes quickly locating one entity or a key mapping, while a **time-ordered history table** uses an entity/bucket partition key and time-based clustering key to read events in order. These two tables complement each other while placing responsibilities on the write path: preventing incorrect replays, handling late-arriving events, synchronizing current state, and reconciling business projections. A complete design explicitly specifies bucket/paging caps, TTLs, peak loads, consistency, and real failure testing before declaring queries supported.
