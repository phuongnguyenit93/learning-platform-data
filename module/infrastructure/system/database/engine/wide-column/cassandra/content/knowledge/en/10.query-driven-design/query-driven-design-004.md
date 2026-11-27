# Choosing Clustering Columns to Support Sorting or Range Filtering

## Lesson Objectives

In Apache Cassandra, once you determine the **partition key** from the primary access path, you must decide how rows are arranged **inside each partition**. That is the role of **clustering columns**: together with clustering order, they determine whether queries can read data in sorted order and across value ranges without scanning, filtering, or sorting arbitrarily in the application.

This lesson belongs to the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It focuses on choosing and ordering clustering columns from real read requirements, writing CQL tailored to the distributed wide-column model, paginating safely, and consuming results from a Java application. Concepts such as replication, consistency, compaction, and repair are noted where they affect performance or operational evaluation.

After completing this lesson, you will be able to:

- Distinguish **partition key**, **clustering column**, and **regular column** inside `PRIMARY KEY`.
- Choose clustering order suited to queries fetching **newest/oldest records**, filtering by a **time range**, or matching an **equality prefix**.
- Explain `ORDER BY` restrictions, `WHERE` constraints on clustering columns, and why certain query shapes require separate tables.
- Write `CREATE TABLE`, `SELECT`, `ORDER BY`, and `[from, to)` range queries for a real read path.
- Recognize issues around bucket boundaries, duplicate timestamps, `LIMIT`, paging, tombstones, and key updates.

## 1. Where Do Clustering Columns Fit in the Cassandra Model?

Consider a system receiving events from IoT devices. A common API is "view events for **one device on one day**, newest first." A candidate schema is:

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    severity text,
    event_type text,
    reading_value double,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

| Structural Part | Column(s) | Role |
| --- | --- | --- |
| **Composite partition key** | `(tenant_id, device_id, day_bucket)` | Identifies the logical partition, token, and replica set |
| **First clustering column** | `event_time` | Defines chronological order and supports range queries |
| **Second clustering column** | `event_id` | Distinguishes events that share the same `event_time` |
| **Regular columns** | `severity`, `event_type`, `reading_value` | Display values; do not automatically provide optimal filter/sort paths |

The nested parentheses in `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)` matter: the first three values **together form one partition key**, while the last two form the **clustering key**. These are not five independent indexes.

A partition can be visualized as follows:

```text
Partition key = (tenant-A, device-42, 2026-11-21 UTC)
    (10:04:10.000, event-08) -> severity=INFO, reading=21.7
    (10:04:10.000, event-03) -> severity=WARN, reading=31.5
    (10:02:40.000, event-07) -> severity=INFO, reading=20.8
    (09:59:12.000, event-06) -> severity=ERROR, reading=0.0

Partition key = (tenant-A, device-42, 2026-11-22 UTC)
    (00:01:05.000, event-09) -> severity=INFO, reading=21.1
```

The IDs in this diagram are illustrative labels; actual ordering when `event_time` matches relies on Cassandra's **`uuid` key value**, not the literal strings `event-08` or `event-03`. The same device on a different day produces a **different partition**; the same partition key with a different `(event_time, event_id)` pair produces a **different row**.

**Principle:** the partition key decides **where to read**, while clustering columns decide **which rows to read and in what order inside that partition**. When an API must read data across multiple partitions, clustering columns do not automatically create a global order across them.

## 2. Starting from the Query Contract

Never choose clustering columns just because a column "looks important." Record the exact query shapes:

| ID | Requirement | Mandatory Conditions | Additional Filters/Sort | Limit |
| --- | --- | --- | --- | --- |
| Q01 | View newest events of the day | Tenant, device, UTC day | `event_time DESC`, tie-broken by `event_id DESC` | 30 rows |
| Q02 | View events from 09:00 to before 10:00 | Tenant, device, UTC day | `event_time >= from` and `event_time < to`, newest first | 100 rows |
| Q03 | View oldest events of the day | Tenant, device, UTC day | `event_time ASC`, `event_id ASC` | 30 rows |
| Q04 | View `ERROR` events of the day | Tenant, device, UTC day, severity | `ERROR` only, newest first | 30 rows |
| Q05 | View events with highest reading values | Tenant, device, UTC day | `reading_value DESC` | 30 rows |
| Q06 | View 7-day history | Tenant, device, 7 UTC days | Newest first across the whole range | 50 rows |

With the example table from Section 1:

- **Q01–Q03** share one partition and `event_time`-based read shapes, so they can be served by **one table**.
- **Q04** has a mandatory condition on `severity`; in the current table that is a regular column, so there is no designed primary read path.
- **Q05** wants to sort by `reading_value`, which is not in the clustering key, so you cannot request `ORDER BY reading_value DESC` as in arbitrary SQL.
- **Q06** spans multiple days, requiring multiple partitions and application-level merge rules, or a different table if it is a primary read path.

When choosing clustering, clarify whether "newest" means **event occurrence time** (`event_time`), **ingestion time** (`ingested_at`), or **update time** (`updated_at`). These three diverge when events arrive late or are modified.

## 3. Choosing Clustering Columns for Read Order

### 3.1. Default Order Declared at Table Creation

`WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)` sets the default clustering order inside **each partition**. For query Q01:

```sql
SELECT event_time, event_id, severity, event_type, reading_value
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 30;
```

The `?` placeholders are bind markers suited to an application **prepared statement**. When running directly in `cqlsh`, pass valid CQL literals instead of `?`.

Q01 provides **the full partition key** and the table already organizes rows in descending time order; thus no extra `ORDER BY` is needed. Cassandra can read along the defined clustering order and cap the returned rows.

If newest-first is always the default, choosing `DESC` in the schema directly expresses that read path. However, Cassandra also supports reading in the reverse of an eligible clustering order; default direction should be grounded in workload and benchmarks rather than assuming one direction is universally faster across all versions or configurations.

### 3.2. When Multiple Rows Share the Same Timestamp

If you use only `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time)`, each partition **has only one row per `event_time` value**. Two events arriving in the same millisecond with the same partition key will share the **same row key**, so the later write can update/overwrite the corresponding columns of the same logical row.

Adding `event_id` to the clustering key allows two events with different IDs at the same timestamp to coexist:

```sql
PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)
```

This guarantees uniqueness only if `event_id` is genuinely **unique within the corresponding key scope**. Using a UUID as a tie-breaker provides deterministic ordering by key value, but random UUID ordering **does not represent causal order** between events with equal timestamps.

If the system requires strict business ordering, gather requirements around **sequence numbers**, timestamp precision, or ID generation, and design appropriate columns and ordering. Never blindly treat a random `UUID` as a sequence.

### 3.3. Reading in Reverse Order to Fetch Oldest Records

Q03 can reuse the table by reversing the **entire** clustering direction:

```sql
SELECT event_time, event_id, severity, event_type
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
ORDER BY event_time ASC, event_id ASC
LIMIT 30;
```

For a table with default order `(event_time DESC, event_id DESC)`, this statement represents the full reversal. In CQL, `ORDER BY` has strict rules: it applies to clustering columns in schema-permitted order with an appropriately constrained partition key; you cannot arbitrarily reverse or sort individual columns, nor can you sort by an arbitrary regular column.

**Operational note:** if Q03 frequently reads large partitions, verify latency and reverse-read impact using representative data. CQL validity is not a performance guarantee.

## 4. Choosing Clustering Columns for Range Conditions

### 4.1. Putting Time as the First Clustering Column

Q02 wants events within a time window of **one device/day partition**:

```sql
SELECT event_time, event_id, severity, event_type, reading_value
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

Here:

1. `tenant_id`, `device_id`, and `day_bucket` locate one partition.
2. `event_time` is the **first** clustering column, so the range condition isolates an **ordered slice** within the partition.
3. `event_id` distinguishes rows sharing the same `event_time`.

The `[fromInclusive, toExclusive)` convention prevents double-counting when stitching contiguous windows: an event at exactly 10:00:00 belongs to `[10:00, 11:00)` and not to `[09:00, 10:00)`.

This range must follow the same timezone and bucketing rule as the write path, such as UTC dates. If `from` is 23:30 on day 21 and `to` is 00:30 on day 22, a query with `day_bucket = 2026-11-21` **cannot** return events from day 22. The application must split it into two reads:

```text
(day_bucket = 2026-11-21, event_time ∈ [21 23:30, 22 00:00))
(day_bucket = 2026-11-22, event_time ∈ [22 00:00, 22 00:30))
```

Times here are UTC; numbers are illustrative. Never assume Cassandra automatically infers and scans adjacent days from an `event_time` predicate.

### 4.2. Prefix Rules and Clustering Order

Consider a generalized design:

```sql
PRIMARY KEY ((tenant_id, device_id, day_bucket), severity, event_time, event_id)
```

In this structure, clustering order is `severity`, then `event_time`, then `event_id`. To read a **time range for a known severity**, a query typically applies an **equality** predicate on the preceding clustering column:

```sql
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND severity = ?
  AND event_time >= ?
  AND event_time < ?
```

The range on `event_time` now falls within rows sharing the same `severity` value.

Conversely, "all severities from 09:00 to 10:00 ordered by time" does **not** have the same seamless read path in a table where `severity` comes first. Skipping the first clustering column and filtering on a subsequent column generally does not yield a valid/efficient direct range query. Similarly, once a range condition is placed on one clustering column, do not assume subsequent clustering columns can still be filtered arbitrarily with equivalent efficiency.

A safe working rule for query-driven design:

- **Prefix** clustering columns are typically bound by equality (`=`) in exact key order.
- The next column can use a **range condition** (`>`, `>=`, `<`, `<=`) when CQL permits.
- Any case wishing to skip part of a prefix, combine multiple ranges, or sort differently must be evaluated with **concrete queries against the target schema and Cassandra version**.

This is a pragmatic guideline for predictable read-cost modeling; CQL supports additional condition forms and operators depending on version, so do not overgeneralize one rule to every syntax variant.

### 4.3. Range Filtering on Non-Time Clustering Columns

Clustering columns can be **sequence numbers**, **versions**, **dates**, **measurements**, or other ordered types if the primary read path genuinely relies on that range.

For example, a versioning system fetching document versions on a branch:

```sql
CREATE TABLE document_versions_by_branch (
    tenant_id text,
    document_id uuid,
    branch text,
    version_no bigint,
    change_id uuid,
    author_id uuid,
    summary text,
    PRIMARY KEY ((tenant_id, document_id, branch), version_no, change_id)
) WITH CLUSTERING ORDER BY (version_no DESC, change_id DESC);

SELECT version_no, change_id, author_id, summary
FROM document_versions_by_branch
WHERE tenant_id = ?
  AND document_id = ?
  AND branch = ?
  AND version_no >= ?
  AND version_no < ?;
```

Here, choosing `version_no` as the first clustering column comes from the requirement to fetch the newest versions and filter a range of version numbers. Another table for searching by author would have a different access path; never add `WHERE author_id = ?` to this table and expect comparable performance.

## 5. Consequences of Choosing the Wrong Clustering Order

### 5.1. Placing Severity Before Time

A product has a screen to "view the newest `ERROR` events for a device on a day." When **severity is a mandatory, frequent filter**, you can design another table:

```sql
CREATE TABLE device_events_by_severity_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    severity text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    reading_value double,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), severity, event_time, event_id)
) WITH CLUSTERING ORDER BY (severity ASC, event_time DESC, event_id DESC);

SELECT event_time, event_id, event_type, reading_value
FROM device_events_by_severity_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND severity = 'ERROR'
LIMIT 30;
```

For a specific severity, rows with that value are read in descending time order. However, this table does **not** maintain a single list of the **30 newest events across all severities** on one `event_time` axis: rows are grouped/ordered by `severity` first. Therefore, if both query patterns matter, consider maintaining **two tables for two read paths** and verify duplicated write costs.

There are two distinct designs for Q04:

| Model | Partition Key | Clustering | Strong At |
| --- | --- | --- | --- |
| Time-grouped | `(tenant_id, device_id, day_bucket)` | `event_time, event_id` | Newest/oldest and time ranges across all severities |
| Severity-grouped in same partition | `(tenant_id, device_id, day_bucket)` | `severity, event_time, event_id` | One known severity, then time filtering/sorting |

A variant puts `severity` into the **partition key**, such as `(tenant_id, device_id, day_bucket, severity)`, placing each severity in its own partition. Choosing `severity` as part of the **partition key** versus a **clustering column** is a data and load distribution trade-off: the clustering approach keeps severities together in one partition, while the partition-key approach fans out by severity—reducing individual partition sizes at the cost of reading more partitions if you ever need all severities.

### 5.2. Placing ID Before Time

```sql
-- Example with a different read path:
PRIMARY KEY ((tenant_id, device_id, day_bucket), event_id, event_time)
```

With this key, events are organized by `event_id` first. It may fit lookups for a specific known `event_id`, but it does **not** directly serve listing the 30 most recent events or querying an `event_time` range across all IDs in the partition. When time is the primary filter/sort axis, put time **before** ID.

### 5.3. Placing Low-Relevance Columns Ahead of the Primary Read Axis

A common mistake is putting `event_type` before `event_time` simply because it appears on many screens. If the primary screen does not pass `event_type` on every call, it breaks the time-based read path. Never put a column into the clustering key just because it is "often displayed"; do so only when filtering/sorting requirements and query frequency justify that ordering.

## 6. Distinguishing `CLUSTERING ORDER BY` and `ORDER BY`

| Statement / Concept | Where Used | Effect |
| --- | --- | --- |
| `WITH CLUSTERING ORDER BY (...)` | Inside `CREATE TABLE` | Declares the **default clustering order** inside each partition |
| `ORDER BY ...` | Inside a valid `SELECT` | Requests a read order compatible with the clustering key, typically default or supported reversal |
| `WHERE` on clustering column | Inside `SELECT` with suitable partition key | Restricts a slice of rows along key order |
| `ORDER BY` on a regular column | Not arbitrarily supported | Do not use `ORDER BY reading_value DESC` on a time-clustered table |
| Sorting results across multiple partitions | In application tier / suitable data pipeline | Cassandra does not automatically enforce a global CQL order across partitions |

A real-world query **must not** rely on "scan the whole table then ORDER BY" as a habit carried over from relational SQL. In Cassandra, partition and clustering structures must be chosen so that target results already sit on a deterministic access path.

### Comparison Table of CQL Query Shapes

Assuming `device_events_by_day` with `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)`:

| Query Pattern | Assessment | Reason |
| --- | --- | --- |
| Full partition key, `LIMIT 30` | Suitable | Reads the head of one partition in clustering order |
| Full partition key, `event_time >= ? AND event_time < ?` | Suitable | Reads a range on the first clustering column |
| Full partition key, reversed `event_time ASC, event_id ASC` | Suitable | Reads reverse clustering order within the partition |
| Only `tenant_id = ?`, missing device/day | No single-partition read path | Missing components of the composite partition key |
| Full partition key, `event_id = ?` without `event_time` | Does not match primary read path | Skips the preceding clustering column |
| Full partition key, `severity = 'ERROR'` | Not optimized by default schema | `severity` is a regular column |
| `ORDER BY reading_value DESC` | Invalid as a standard clustering sort | `reading_value` is not a clustering column |

Some non-matching queries can be rewritten using indexes, alternative filtering mechanisms, or `ALLOW FILTERING` depending on version, but **valid syntax does not mean low data read cost**. When such a pattern is a primary requirement, prioritize evaluating a dedicated table/projection or search architecture and measure real performance.

## 7. Time Ranges, Boundaries, and Data Accuracy

### 7.1. Aligning Write Time and Query Time

Before choosing `event_time` as a clustering key, agree on:

1. **Time source:** device-generated timestamp or server ingestion time?
2. **Precision:** Cassandra `timestamp` stores instants with millisecond precision; do not assume microsecond/nanosecond ordering from this type alone.
3. **Timezone:** store and compute `day_bucket` using one consistent convention, such as UTC.
4. **Late-arriving events:** still belong to the occurrence-time bucket if the key is derived from `event_time`.
5. **Timestamp corrections:** changing values in the primary key is not an ordinary `UPDATE` on the key; it typically requires deleting the row under the old key and writing a new row under the new key, with error-recovery handling.

For example, an event occurs at `2026-11-21T23:59:59Z` but arrives after midnight. If the system defines `day_bucket` from `event_time`, it still belongs to the day-21 partition. If one service writes using `ingested_at` while another reads using `event_time`, records become hard to find or land in unexpected partitions.

### 7.2. Result Limits Do Not Guarantee Low Read Cost

`LIMIT 30` only caps **rows returned** by the query. If a partition contains heavy tombstones from TTLs/deletes, Cassandra may still scan many non-visible cells before returning enough rows. Therefore, clustering choices must be paired with forecasts of:

- Maximum size and row count of **one partition**.
- Write rate into the hottest partition.
- TTLs, deletes, data updates, and tombstone counts.
- Range width and maximum partitions allowed per API call.
- p95/p99 latency targets and actual rows/bytes returned.

Compaction affects SSTable counts and read cost, while repair keeps replica data consistent via Cassandra's repair mechanisms. Neither can turn a query lacking a matching clustering path into a cheap small-slice read.

### 7.3. Multi-Page Pagination

Distinguish three levels of limits:

| Limit | Meaning | Example |
| --- | --- | --- |
| CQL `LIMIT 30` | Maximum total rows in the query result | Preview screen needs only 30 events |
| Java driver `page size = 30` | Target rows per page fetched by the driver | User clicks "load more" |
| API limits | Max days/buckets, total pages, max payload per request | Disallow reading 5 years in a single request |

If you want multiple consecutive 30-row pages, use driver pagination with an appropriate query. A `SELECT ... LIMIT 30` will not keep yielding endless subsequent pages of 30 new rows each.

**Paging state** is opaque data tied to the query and its bound values; never modify it, reuse it across different partitions/filters, or treat pages as an immutable snapshot under concurrent writes/deletes. When an API passes paging state to a client, protect token integrity and re-check tenant, device, and time-range permissions on every call.

## 8. Example of Calling a Range Query from Java

The example below uses **DataStax Java Driver 4.x** and a prepared statement for Q02. Date and timestamp bounds are computed by the application using the same UTC rules as writes.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DeviceEventReader {
    private final CqlSession session;
    private final PreparedStatement rangeQuery;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.rangeQuery = session.prepare(
            "SELECT event_time, event_id, severity, event_type, reading_value " +
            "FROM device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public ResultSet readRange(
        String tenantId,
        UUID deviceId,
        LocalDate utcDay,
        Instant fromInclusive,
        Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        // Assumes the caller has verified both bounds belong to the same utcDay bucket.
        BoundStatement statement = rangeQuery
            .bind(tenantId, deviceId, utcDay, fromInclusive, toExclusive)
            .setPageSize(50);
        return session.execute(statement);
    }
}
```

In driver 4.x, `LocalDate` maps to CQL `date`, and `Instant` maps to `timestamp`. The application layer must **actually enforce** bucket checks, read-range caps, and access authorization; the comment in the example represents an assumption about the caller, not an implemented check. If a range spans multiple days, split by bucket and handle multi-partition ordering/pagination.

A single `CqlSession` should be managed over the service lifecycle and shared across queries; avoid creating a new session per call. Configure timeouts, consistency levels, retries, and `ResultSet` iteration to match API goals. For paginated results, synchronously iterating through an entire `ResultSet` can trigger automatic fetching of subsequent pages, so an endpoint returning a single page must explicitly track rows consumed and the next-page state.

## 9. Impact on Replication, Consistency, and Duplicated Data

The clustering key defines **row order and identity within a partition**, but does not itself determine consistency. Keyspace replication factor and replica placement strategy determine data copies; per-operation read/write consistency levels govern replica responses. Choosing `LOCAL_QUORUM` may suit specific topologies and SLAs, yet it **cannot fix** a query wanting `ORDER BY reading_value DESC` on a table without a matching clustering path.

If you maintain both `device_events_by_day` and `device_events_by_severity_day` for two query shapes, the write path must maintain both. When `severity` changes, in the second table it is **part of the primary key**: you must delete the row under the old severity key and write a row under the new severity key, while also updating the representation in the first table. This can create tombstones, and tables may temporarily diverge if one write fails.

Cassandra does not automatically maintain a `JOIN` or standard SQL transaction across application-managed projections. Establish idempotent retry workflows, reconciliation mechanisms, and handling for late or duplicate events. Raising the consistency level **does not automatically ensure** all denormalized tables update instantaneously as a single transaction.

## 10. Checklist for Choosing Clustering Columns

| Question | Sign It Is Clarified | If Unclear |
| --- | --- | --- |
| Is the partition key finalized? | Caller always supplies tenant, device, bucket | Lock the access path before choosing clustering |
| What is the sort axis? | `event_time DESC`, tie-break `event_id DESC` | Distinguish event time, ingest time, updated time |
| Is there range filtering? | `event_time >= from AND event_time < to` | Identify range column and clustering prefix |
| Are columns before the range column bound by equality? | E.g., `severity = 'ERROR'` when severity precedes time | Consider reordering columns or using a separate table |
| Does the query sort across multiple partitions? | Explicit fan-out/merge rules exist | Do not rely on global `ORDER BY` |
| Is sorting by a regular column requested? | Flagged as a separate query shape | Never promise arbitrary `ORDER BY` |
| Can events share timestamps? | `event_id`/sequence tie-breaker present | Avoid multiple events colliding on primary key |
| Can time ranges cross buckets? | Explicit partition-splitting read path | Fix day/hour splitting rules |
| How are limits/paging handled? | `LIMIT`, page size, API bounds distinguished | Never assume `LIMIT` is unconditionally cheap |
| Benchmarked on representative load and data? | Measured p95/p99, large partitions, tombstones, reverse reads | Do not conclude solely because CQL executes |

## 11. Practice Exercise

A Java application stores price-change history per store. Each change contains:

```text
tenant_id, store_id, product_id, day_bucket,
changed_at, change_id, price, currency, actor_id
```

Queries:

1. **R1:** Fetch the 20 newest price changes for a product in a store/day.
2. **R2:** Fetch price changes in `[09:00, 12:00)` for the same product/day.
3. **R3:** Fetch the 20 oldest price changes for the same product/day.
4. **R4:** Fetch the 20 price changes with the highest `price` for the same product/day.
5. **R5:** Fetch the 50 newest price changes for a product across **all stores** in a tenant.

Tasks:

1. Propose a partition key for R1–R3 based on fields the caller always knows; explain the role of `product_id`.
2. Choose clustering keys supporting R1/R2, handling multiple changes with the same `changed_at`.
3. Write the `CREATE TABLE` and three matching `SELECT` queries for R1/R2/R3.
4. Explain why R4 and R5 do not naturally share the same read path, and how to approach them if both are business-critical.
5. For a range starting at 23:00 on day 21 and ending at 01:00 on day 22 UTC, describe the bucket count and how to split the range.

**Reference guidance:** A candidate schema for R1–R3 is `PRIMARY KEY ((tenant_id, store_id, product_id, day_bucket), changed_at, change_id)` with `CLUSTERING ORDER BY (changed_at DESC, change_id DESC)`. R2 uses `changed_at >= ? AND changed_at < ?`; R3 reverses both clustering columns to `ASC`. R4 needs sorting by `price`, likely requiring another access path; R5 lacks `store_id` and also demands a shared order across stores. A range crossing UTC midnight must read **two daily partitions** for the same store/product and merge as required.

## Conclusion

Choosing clustering columns is about deciding **the read order inside a partition**. When the primary access path needs the newest records or a time range, place the time column in the right clustering position, add a tie-breaker column for equal timestamps, and declare clustering direction from the query contract. When requirements add filters ahead of the time axis, sort by regular columns, or combine data across multiple partitions, re-evaluate clustering order, partition key, or add dedicated serving tables. A good schema is proven by **concrete CQL, representative data, and measurements under real load**.
