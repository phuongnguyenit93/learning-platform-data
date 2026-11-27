# CLUSTERING ORDER BY and Range Queries

In Apache Cassandra, data is distributed across nodes by the **partition key**, while rows **inside each partition** are organized by **clustering columns**. The CQL `CLUSTERING ORDER BY` property specifies the default sort direction of clustering columns. Combined with range conditions on the clustering key, we can quickly read recent records, event history by hour, or a time slice without sorting the entire dataset in the application.

This is part of the **query-driven table design** mindset in a distributed wide-column model. Distinguish clearly: the partition key locates the right partition; the clustering key and its order locate and traverse rows within that partition. `CLUSTERING ORDER BY` does not change Cassandra's replication factor, tokens, or read/write consistency levels.

After this lesson, you will be able to:

- Define `CLUSTERING ORDER BY` in `CREATE TABLE`, understanding the meaning of `ASC` and `DESC`.
- Predict row order within a partition when one or more clustering columns exist.
- Write CQL queries using `=`, `>=`, `>`, `<=`, `<` on clustering columns.
- Distinguish schema storage order from `ORDER BY` in a `SELECT` statement.
- Recognize queries violating the clustering key prefix rule, partition key scope, and cases requiring a different data model.
- Apply range queries using prepared statements from Java.

## 1. Partitions and ordering within a partition

Consider the requirement of a sensor data collection system: **read the 20 latest measurements of a device in a day** and **read measurements from 08:00 to before 09:00**. A device may emit multiple records at the same timestamp, so an event identifier is also needed.

We design the table:

```sql
CREATE TABLE measurements_by_device_day (
    tenant_id       text,
    device_id       uuid,
    event_day       date,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    battery_percent int,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

Three column groups have distinct roles:

| Group | Column(s) | Responsibility |
| --- | --- | --- |
| Composite partition key | `(tenant_id, device_id, event_day)` | Selects **one logical partition** for one device of one tenant on one day. |
| First clustering column | `measured_at` | Groups rows by timestamp, sorted **newest to oldest** due to `DESC`. |
| Second clustering column | `measurement_id` | Distinguishes measurements at the same timestamp; sorted **ascending** when `measured_at` is equal. |
| Regular columns | `temperature`, `battery_percent` | Hold measurement values; do not participate in row placement or clustering order. |

For a fixed partition key, data is sorted by the clustering key **from left to right**. If `measured_at` is identical, Cassandra uses `measurement_id` to distinguish rows and determine secondary ordering.

```text
Partition ('acme', device-01, 2026-11-21)

  measured_at           measurement_id    temperature
  2026-11-21 08:45:00   ...0002           37.9
  2026-11-21 08:45:00   ...0008           38.0
  2026-11-21 08:30:00   ...0001           37.7
  2026-11-21 08:00:00   ...0005           37.5

              measured_at DESC
                 |
                 +-- at the same timestamp: measurement_id ASC
```

Rows from another day or another device reside in other logical partitions; `CLUSTERING ORDER BY` **does not create a global order across partitions**.

## 2. How is `CLUSTERING ORDER BY` declared and how does it work?

Syntax used in `CREATE TABLE`:

```sql
CREATE TABLE sample_events (
    account_id uuid,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (account_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

In this example, `account_id` is a **simple** partition key. The two clustering columns `occurred_at` and `event_id` are sorted in opposite directions.

If `CLUSTERING ORDER BY` is **omitted**, Cassandra defaults to ordering clustering columns **`ASC`**:

```sql
-- Defaults to occurred_at ASC, event_id ASC:
CREATE TABLE sample_events_asc (
    account_id uuid,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (account_id, occurred_at, event_id)
);
```

Meaning:

- `ASC`: smaller values precede larger values according to the column **data type's** comparator.
- `DESC`: larger values precede smaller values according to that comparator.
- For timestamps, `DESC` is commonly suitable when the UI needs newest data first.
- With multiple clustering columns, a later column's criterion only matters when preceding columns are equal.

**Note on "storage order":** Cassandra uses an LSM architecture with memtables and multiple SSTables; a partition can appear across multiple SSTables. Thus, "ordered by clustering key" is a logical ordering rule Cassandra uses when retrieving and merging data, **not** a guarantee that the entire partition always lies contiguously in a single file.

`CLUSTERING ORDER BY` is a schema property tied to key organization. To change clustering key design/storage order after a table already exists, you typically need to create a new appropriate table, migrate data, and switch read/write traffic; do not treat it as an option that can be altered arbitrarily per query.

## 3. Reading in default order: no `ORDER BY` needed

With `measurements_by_device_day`, the following query already returns measurements in the partition's declared clustering order:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Results start with the rows having the largest `measured_at`. If two rows have the same timestamp, `measurement_id ASC` determines their order.

Here:

1. Three equality predicates select the **full partition key**.
2. `CLUSTERING ORDER BY (measured_at DESC, measurement_id ASC)` defines the default order.
3. `LIMIT 20` caps the number of returned rows, making it suitable for a recent measurements list of **one partition**.

There is no need to add `ORDER BY measured_at DESC` just to match the schema order. In large query scenarios, actual efficiency also depends on tombstone counts, partition size, cache, SSTables, and read behavior, yet choosing the right partition key remains the foundational step.

### Using `ORDER BY` in `SELECT` when reversing direction is needed

CQL has `ORDER BY` in `SELECT`, but it is constrained by the **clustering columns**. For a table declared with `measured_at DESC, measurement_id ASC`, you can request traversing in the **completely reversed order**:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
ORDER BY measured_at ASC, measurement_id DESC
LIMIT 20;
```

At this point, the day's oldest measurements appear first; when timestamps tie, `measurement_id` is traversed in the opposite direction.

For a table with multiple clustering columns, the sort direction requested by `SELECT ORDER BY` must align with the schema's clustering order, or **reverse all directions together**. You cannot freely pick directions per column or sort by a regular column such as `temperature`.

| Statement / Desired behavior | Fits the example table? | Explanation |
| --- | --- | --- |
| Omit `ORDER BY` | Yes | Uses default `measured_at DESC, measurement_id ASC`. |
| `ORDER BY measured_at ASC, measurement_id DESC` | Yes | Reverses the entire clustering order. |
| `ORDER BY measured_at DESC, measurement_id DESC` | No | Reverses only one column; matches neither schema order nor full reverse order. |
| `ORDER BY temperature DESC` | No | `temperature` is a regular column, not a clustering column. |
| Sort all devices in the system by `measured_at` | Not directly | Clustering order is scoped strictly within each partition. |

Querying in the reverse direction of storage can carry different costs depending on Cassandra version and data state. If both directions are needed at large scale simultaneously, benchmark under realistic load before deciding.

## 4. Range queries on clustering columns

A **range query** is a query with one or more inequality conditions such as `>`, `>=`, `<`, `<=`, used to retrieve a slice of values within an identified partition.

### A half-open time interval

To fetch measurements from **08:00:00 (inclusive)** to **09:00:00 (exclusive)** on 2026-11-21, in UTC:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z';
```

This is the interval **`[08:00, 09:00)`**. Using half-open intervals prevents two consecutive windows `[08:00, 09:00)` and `[09:00, 10:00)` from both including a measurement taken at exactly 09:00:00.

Cassandra can narrow down the matching slice of clustering keys within **one partition**, and then return rows in the table's clustering order. The condition `measured_at >= ...` does not automatically switch results to ascending order: the default order here remains `DESC`.

### Range on the second column: prefix must be fixed

With two clustering columns `(measured_at, measurement_id)`, Cassandra orders by **`measured_at` first**, and only then by `measurement_id`.

You can select measurements at a specific timestamp and constrain `measurement_id`:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at = '2026-11-21T08:45:00Z'
  AND measurement_id >= 00000000-0000-0000-0000-000000000010;
```

Here `measured_at` is fixed with `=`, so Cassandra can scan the range of `measurement_id` values within that clustering key slice. The illustrative UUID value only demonstrates type-aware comparison operators; in practice, choose `measurement_id` and query goals so the comparison has business meaning.

You cannot omit `measured_at` and range-filter `measurement_id` as if the second column were independently indexed:

```sql
-- Missing the clustering column preceding measurement_id:
SELECT *
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measurement_id >= 00000000-0000-0000-0000-000000000010;
```

The primary key access path does not support that query as a contiguous clustering slice. When designing multiple clustering columns, place the column commonly range-filtered **earlier**, and use trailing clustering columns to distinguish rows or serve other query patterns.

### Clustering column prefix rule

For a clustering key `(c1, c2, c3)`, the standard usage in CQL is:

- Bind **`c1 = ...`** before filtering `c2`.
- Bind **`c1 = ... AND c2 = ...`** before filtering `c3`.
- A range condition can be used on the **next clustering column** after a sequence of equality conditions.
- Once a range is used on one column, subsequent columns no longer act as independent ranges along the same simple access path.

Cassandra also supports certain tuple clustering query syntax/cases; those must be checked per specific version and syntax, and do not negate the declared prefix-based data organization rule.

## 5. A complete example with a time window

Suppose a monitoring application needs to return the first page of a temperature chart:

- Tenant: `acme`.
- Device: `327a71e9-f562-4b54-94b9-2138a9e30b12`.
- Day bucket: `2026-11-21` (computed in UTC).
- UTC range: `[08:00, 09:00)`.
- Limit: 100 measurements.

Corresponding CQL:

```sql
SELECT measured_at, measurement_id, temperature, battery_percent
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

Conceptual execution sequence:

```text
1. Read tenant_id + device_id + event_day
                    |
                    v
2. Compute token -> identify replica set holding the partition
                    |
                    v
3. Inside partition, seek measured_at slice in [08:00, 09:00)
                    |
                    v
4. Traverse in clustering order: measured_at DESC, measurement_id ASC
                    |
                    v
5. Return at most 100 matching rows
```

This diagram only illustrates the logical access path, not the full steps of reading from memtable/SSTables, inter-replica communication, or consistency levels.

### Fetching data across multiple days

Because `event_day` is in the **partition key**, a query "from 23:30 on the 21st to 00:30 on the 22nd" must cover at least **two different partition keys**.

The application can:

1. Query the day-21 partition with range `[2026-11-21T23:30Z, 2026-11-22T00:00Z)`.
2. Query the day-22 partition with range `[2026-11-22T00:00Z, 2026-11-22T00:30Z)`.
3. Merge and sort by `measured_at` in the application if a **single combined result stream** is needed.

`ORDER BY` on each individual query **does not automatically merge ordering across multiple partitions**. If cross-bucket queries are a primary business requirement, consider adding a table designed for that access path while keeping partition sizes controlled.

## 6. Distinguishing `CLUSTERING ORDER BY` and `SELECT ORDER BY`

| Criterion | `CLUSTERING ORDER BY` | `SELECT`'s `ORDER BY` |
| --- | --- | --- |
| Where declared? | In `CREATE TABLE ... WITH` | In the `SELECT` statement |
| Purpose | Defines default sort direction of clustering keys within a partition | Requests result traversal direction compatible with clustering order |
| Scope | Every partition of the table | Query results read along a supported clustering access path |
| Uses regular columns? | No | Not via standard clustering access paths |
| Varies per query? | No; it is a schema setting | Yes, provided it matches a supported order |
| Sorts across all partitions? | No | Does not provide relational SQL-style global `ORDER BY` |

In relational DBMSs, `ORDER BY created_at DESC` is often an operation that sorts the result set after querying. In Cassandra, you should **plan data order from table design time** to avoid expecting an arbitrary `ORDER BY` clause to solve every case.

An invalid example in this design:

```sql
-- temperature is not a clustering column:
SELECT *
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
ORDER BY temperature DESC;
```

If the business requirement needs "the top 100 highest temperature measurements," consider a dedicated table ordered by temperature key, an aggregation pipeline, or sorting at the application layer over a bounded dataset, depending on consistency and scale requirements.

## 7. Common mistakes and how to handle them

| Symptom | Cause | Approach |
| --- | --- | --- |
| `SELECT` without `ORDER BY` returns results "backwards" from expectation | Schema defaults to `ASC` or declared a different clustering direction than desired. | Choose `CLUSTERING ORDER BY` for the primary query right at design time. |
| Wanting to sort by `temperature` or a non-clustering column | CQL `ORDER BY` is not a free-form sort over arbitrary columns. | Design a different table/access path or sort a bounded set in the application. |
| Filtering `measurement_id` without fixing `measured_at` | Skipping a prefix column of the clustering key. | Fix the appropriate prefix or reorder clustering columns in a new table. |
| Searching by `measured_at` without providing `device_id` and `event_day` | Incomplete partition key cannot locate a partition. | Supply full key, read the right buckets, or create another query-specific table. |
| Time-range query crossing midnight only reads the first day's bucket | `event_day` splits data into daily partitions. | Compute all covered buckets and merge results. |
| Missing/duplicate boundary timestamps | Using closed intervals on both ends or inconsistent time zone handling. | Use half-open intervals `[start, end)` and standardize UTC/bucketing. |
| Range query returns many rows with high latency | Oversized partition, overly wide slice, many tombstones, or poor paging. | Shorten the range, use proper bucketing, paginate, monitor metrics and compaction. |

### Note on `LIMIT` and pagination

`LIMIT 100` caps the **number of returned rows**, not necessarily meaning Cassandra only reads 100 cells from disk in every case. A range with tombstones or multiple SSTables may still require extra processing. When executing subsequent reads, use the **paging state** from the Cassandra driver instead of manually slicing pages by guessing the last timestamp: multiple rows can share the same `measured_at`.

If you must build a custom key-based *cursor*, include **enough clustering columns** so rows sharing a timestamp are neither skipped nor duplicated; tuple condition rules and sort directions must be verified against your CQL version.

## 8. Calling a range query from Java

In a Java application using Cassandra Java Driver 4.x, bind the key values and time bounds into a `PreparedStatement`. The example uses `Instant` for a CQL `timestamp` column and `LocalDate` for a `date` column:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MeasurementRepository {
    private final CqlSession session;
    private final PreparedStatement findInRange;

    public MeasurementRepository(CqlSession session) {
        this.session = session;
        this.findInRange = session.prepare(
            "SELECT measured_at, measurement_id, temperature " +
            "FROM measurements_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet findInRange(
            String tenantId, UUID deviceId, LocalDate eventDay,
            Instant startInclusive, Instant endExclusive) {
        return session.execute(findInRange.bind(
            tenantId, deviceId, eventDay, startInclusive, endExclusive));
    }
}
```

When calling this, the application must ensure `eventDay` is computed using the **same bucketing rule** used when writing data. For ranges spanning two days, invoke the method for two different partition keys and combine the results. `Instant` represents an absolute point in time; only derive a `LocalDate` bucket after establishing a time zone (such as UTC) to prevent off-by-one day shifts.

In production deployments, reuse prepared statements, configure an appropriate page size, and pass deadlines/timeouts suited to system load. Querying with the proper partition key lets the driver compute the routing key to send the request to an appropriate coordinator when full cluster metadata is available.

## 9. Self-check exercises

Given an orders table:

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    ordered_at timestamp,
    order_id uuid,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
```

Answer before checking the solutions:

1. Does the table return the newest or oldest order first if `ORDER BY` is omitted?
2. If two orders have the same `ordered_at`, which column determines the tie-break order?
3. To fetch orders in `[2026-11-10T00:00Z, 2026-11-11T00:00Z)` for one customer in November, what minimum conditions are needed in `WHERE`?
4. Is `ORDER BY ordered_at ASC, order_id DESC` valid? What about `ORDER BY ordered_at ASC, order_id ASC`?
5. Can you use this exact table to query "all orders of all customers in tenant T, month M, sorted by `ordered_at DESC`" and receive results in one global order?
6. If an order has the same timestamp as another order but a different `order_id`, will it overwrite the other order?

**Suggested answers:**

1. **Newest first** because of `ordered_at DESC`.
2. `order_id ASC` determines the order when `ordered_at` ties.
3. Requires `tenant_id = ...`, `customer_id = ...`, `month_bucket = ...`, and the range predicate on `ordered_at`.
4. `ASC, DESC` reverses the entire schema order, so it is valid; `ASC, ASC` only reverses the first column, which is not a supported order in this model.
5. **Not directly**: the partition key also includes `customer_id` and clustering order only applies within each partition.
6. **No**, because `order_id` is part of the full primary key; two distinct key combinations represent two logical rows.

## 10. Takeaways for Cassandra table design

- `CLUSTERING ORDER BY` is defined in the schema and applies **within each partition**, following the order of clustering columns.
- If omitted, clustering columns default to **`ASC`**; `DESC` is useful when primary queries need the newest records first.
- For efficient range queries, supply the **full partition key** and a range on the clustering column respecting the prefix rule.
- CQL `SELECT ORDER BY` is bounded by clustering order; do not use it to sort arbitrarily by regular columns or across the entire cluster.
- **Half-open** time intervals and consistent bucketing/time zone conventions prevent missing or duplicate boundary records.
- Combine clustering order with **time buckets**, query-driven table design, and pagination to control latency in a distributed Cassandra system.

Mastering clustering order and range queries helps you design log, order, sensor, and timeline tables aligned with how Cassandra actually stores and reads data. This is also the foundation for evaluating read/write performance, consistency levels, compaction, and querying from Java applications.
