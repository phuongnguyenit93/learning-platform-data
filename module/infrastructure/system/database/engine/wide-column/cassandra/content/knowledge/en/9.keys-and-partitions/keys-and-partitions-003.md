# Clustering Keys and Row Storage Ordering Within a Partition

In Apache Cassandra, the **partition key** determines which partition data resides in, while **clustering columns** determine how rows within the **same partition** are distinguished and ordered. This combination enables reading data by entity, by time series, or by an ordered range without sorting the entire table as in many relational SQL queries.

This topic belongs to the **Keys and Partitions** section of Cassandra's *wide-column* model. Understanding clustering keys helps you design query-driven tables and lays the foundation for explaining read performance, replica distribution, and the effects of storage, compaction, or repair.

After this lesson, you will be able to:

- Correctly identify clustering columns in a `PRIMARY KEY` declaration.
- Explain *lexicographic order* when multiple clustering columns are present.
- Use `CLUSTERING ORDER BY` to choose the default ordering of data within each partition.
- Write CQL queries that read by clustering key prefix, by time range, and in valid reversed order.
- Design keys with a tie-breaking column for events sharing the same timestamp, and recognize queries that do not match the key.

## 1. Where do clustering columns sit in the primary key?

A logical row is identified by the **entire primary key**:

```text
PRIMARY KEY = partition key + clustering columns (optional)

Partition key          -> Selects partition, participates in token calculation.
Clustering column 1    -> Order and identity within the partition.
Clustering column 2    -> Distinguishes/orders when column 1 is equal.
...
```

Example:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
);
```

| Column role | Column(s) | Function |
| --- | --- | --- |
| Composite partition key | `(tenant_id, customer_id)` | Identifies a customer partition within a tenant. |
| First clustering column | `created_at` | Groups and orders rows by creation timestamp. |
| Second clustering column | `order_id` | Distinguishes orders with the same timestamp and provides secondary ordering. |
| Regular column | `amount` | Row payload; does not determine token or clustering order. |

With this declaration, `(tenant_id, customer_id, created_at, order_id)` is the **full primary key**. Two rows with the same `tenant_id` and `customer_id` but different `order_id` values can coexist in the partition. If all primary key components are identical, writing more data operates on the **same logical row** rather than creating a new row.

Do not confuse:

```sql
-- Only tenant_id is the partition key; the subsequent columns are clustering columns:
PRIMARY KEY (tenant_id, customer_id, created_at, order_id)

-- tenant_id and customer_id together form the partition key; only two clustering columns remain:
PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
```

The inner parentheses are decisive: choosing wrongly can put all customers of a tenant into a single oversized partition.

## 2. Clustering order exists only within a partition

Suppose a temperature measurement table has a three-component partition key: tenant, device, and day. Within each partition, row data is organized by clustering columns:

```text
Partition key = ('acme', 'device-01', 2026-11-21)
    |
    +-- clustering (09:20, event-B) -> temperature 38.2
    +-- clustering (09:20, event-C) -> temperature 38.3
    +-- clustering (09:10, event-A) -> temperature 37.9
    +-- clustering (08:55, event-D) -> temperature 37.7

Partition key = ('acme', 'device-02', 2026-11-21)
    |
    +-- clustering (09:15, event-E) -> temperature 36.6
    +-- clustering (08:45, event-F) -> temperature 36.4
```

In this example, the ordering is illustrated with **descending** timestamps. `event-B` and `event-C` share the same timestamp, so the second column determines their relative order. Two separate partitions do not share a global clustering order.

This leads to three important conclusions:

1. Cassandra efficiently reads a **contiguous slice of rows within a partition** when a query matches the partition key and clustering key.
2. Clustering columns **do not alter the token** and do not determine the replica set storing the partition; that is the partition key's role.
3. Cassandra does not maintain a globally sorted list by clustering columns across all partitions in the cluster.

## 3. Declaring order with `CLUSTERING ORDER BY`

Unless configured otherwise, Cassandra orders clustering columns in **ascending (`ASC`)** order. You can declare the default order at table creation, which is especially useful for events that need to be read newest-first:

```sql
CREATE TABLE sensor_events_by_device_day (
    tenant_id text,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    temperature double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

In this table:

- **Partition key:** `(tenant_id, device_id, event_day)`.
- **Clustering key:** `(occurred_at, event_id)`.
- **Default order:** `occurred_at DESC`; if two events have the same `occurred_at`, compare `event_id ASC`.
- **Regular columns:** `event_type` and `temperature` cannot be used as clustering columns just because they appear in `SELECT`.

Differences between `PRIMARY KEY` and `CLUSTERING ORDER BY`:

| Configuration | What does it determine? |
| --- | --- |
| `PRIMARY KEY ((tenant_id, device_id, event_day), occurred_at, event_id)` | Partition key components, number of clustering columns, and their **comparison precedence**. |
| `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)` | Default **ascending/descending direction** of each clustering column in storage/read order. |
| `ORDER BY` in `SELECT` | Requests reading in a valid clustering order for a specific query; does not redefine the schema. |

Usually you should choose the default order matching the most common read path. For instance, time-series data typically sets `occurred_at DESC` so recent records can be fetched quickly with `LIMIT`. When multiple columns are present, comparison precedence **by position in the primary key** remains unchanged regardless of differing `ASC`/`DESC` directions.

## 4. How are multiple clustering columns ordered?

When a clustering key consists of multiple columns, Cassandra compares **from left to right** according to the table definition:

1. Compare `occurred_at` first, in `DESC` order.
2. Only when `occurred_at` is equal, compare `event_id`, in `ASC` order.
3. Two rows sharing both `occurred_at` and `event_id` within the same partition key represent **one logical row**.

Illustrative example (shortened `event_id` for readability):

| `occurred_at` | `event_id` | Position under `(occurred_at DESC, event_id ASC)` |
| --- | --- | ---: |
| 09:20 | E-002 | 2 |
| 09:10 | E-005 | 3 |
| 09:20 | E-001 | 1 |
| 08:55 | E-004 | 4 |

Exact order within the same partition:

```text
(09:20, E-001)
(09:20, E-002)
(09:10, E-005)
(08:55, E-004)
```

The table above uses `E-001` for illustration. In real CQL, `event_id` is a `uuid`, so secondary ordering follows Cassandra's `uuid` comparator rather than arbitrary display string sorting.

Avoid the misconception that Cassandra "sorts all rows by the second column" after sorting by the first. The second column only breaks ties among rows with the same first-column value. Therefore, **the order of clustering columns in the primary key is crucial**.

## 5. Writing data: clustering keys also help identify rows

To illustrate, write three events for the same device and day. The first two intentionally share a timestamp, but have different `event_id` values:

```sql
INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:20:00+0700',
    00000000-0000-4000-8000-000000000001,
    'temperature', 38.1
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:20:00+0700',
    00000000-0000-4000-8000-000000000002,
    'temperature', 38.3
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, temperature
) VALUES (
    'acme', 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181, '2026-11-21',
    '2026-11-21T09:10:00+0700',
    00000000-0000-4000-8000-000000000003,
    'temperature', 37.9
);
```

When reading the partition in default order, the two 09:20 events come before 09:10; the 09:20 event with the smaller `event_id` precedes the other.

If you write again with the same **partition key + occurred_at + event_id**, Cassandra updates the values of **that exact row** according to Cassandra's write mechanism and conflict resolution rules, without inserting a duplicate row. Thus:

- If you need to retain **multiple events with the same timestamp**, include a stable tie-breaking key like `event_id`.
- If you need **safe retries**, the application should reuse the `event_id` already assigned to that event when resending the write.
- Do not use `temperature` as a clustering column just to sort measurements: readings can collide, fluctuate, and do not represent event identity.

Every primary key component must have a valid, non-`null` value when identifying a row. Changing `occurred_at` or `event_id` means changing the primary key; typically you must write a row under the new key and handle the old row intentionally.

## 6. Querying by clustering order

### 6.1. Fetching the 20 most recent events in a day

```sql
SELECT occurred_at, event_id, event_type, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
LIMIT 20;
```

The `WHERE` clause specifies the **full partition key**. Within the selected partition, data follows the default order `occurred_at DESC, event_id ASC`; hence `LIMIT 20` retrieves the first 20 rows in this order. No `ORDER BY` is required if you want the declared clustering order.

### 6.2. Fetching events within a time range

```sql
SELECT occurred_at, event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00+0700'
  AND occurred_at <  '2026-11-21T10:00:00+0700';
```

This is a **range** query on the first clustering column. Because rows are organized by this key inside each partition, Cassandra can seek the matching range and read in clustering order.

Note: `event_day` in the partition key is the bucket date chosen by the **application**. Standardize the time zone and bucket calculation; data written under a UTC date while the application queries under Vietnam local date can hit the wrong partition if rules are inconsistent.

### 6.3. Filtering by clustering key prefix

Because `occurred_at` precedes `event_id`, you can filter by a specific `occurred_at` value and then apply a condition on `event_id`:

```sql
SELECT event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:20:00+0700'
  AND event_id >= 00000000-0000-4000-8000-000000000001;
```

Here filtering on `event_id` is efficient because the preceding column (`occurred_at`) is bound by equality. Without knowing `occurred_at`, filtering on `event_id` alone cannot use the clustering key as a simple prefix access path.

### 6.4. Reading in reversed order

```sql
SELECT occurred_at, event_id, temperature
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
ORDER BY occurred_at ASC, event_id DESC
LIMIT 20;
```

The `ASC, DESC` order here is the **exact inverse of the entire** default order `DESC, ASC`. Cassandra can traverse clustering order in reverse when the query targets a single partition. Do not assume CQL allows reversing individual columns arbitrarily or sorting by any column like relational SQL.

## 7. Notable constraints on `WHERE` and `ORDER BY`

CQL is optimized for key-matching access patterns, so keep several principles in mind:

| Query | Fits the example table? | Reason |
| --- | --- | --- |
| Full `tenant_id`, `device_id`, `event_day` | **Yes** | Selects the partition. |
| Full partition key + `occurred_at` range | **Yes** | First clustering column supports range predicates. |
| Full partition key + `occurred_at = ...` + `event_id` filter | **Yes** | Follows clustering key prefix order. |
| Only `tenant_id = ...` | **No via normal key path** | Missing two parts of the composite partition key. |
| Full partition key + only `event_id = ...` | **No via normal key path** | Skips the preceding clustering column. |
| Full partition key + `ORDER BY temperature DESC` | **No** | `temperature` is not a clustering column. |
| `ORDER BY occurred_at DESC` cluster-wide, missing partition key | **No** | There is no global clustering order. |

Invalid examples:

```sql
-- event_id is not the first clustering column:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND event_id = 00000000-0000-4000-8000-000000000001;

-- Cannot sort by a regular column:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
ORDER BY temperature DESC;
```

There are cases where Cassandra supports `IN`, secondary indexes, or `ALLOW FILTERING`, but they come with their own constraints and costs. If a primary query always needs to "look up by event ID without knowing the timestamp," design an `event_id` lookup table or a dedicated access path instead of relying on broad filtering.

## 8. Clustering column ordering is a design decision

With the same three columns `event_type`, `occurred_at`, and `event_id`, changing their clustering positions serves different queries.

**Option A — prioritize time series across all event types:**

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at,
    event_id
)
```

This option suits fetching events by time range regardless of `event_type`. If frequent queries by event type are needed, `event_type` is a regular column and does not natively support key-based access.

**Option B — prioritize events by type, then by time:**

```sql
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    event_type,
    occurred_at,
    event_id
)
```

This suits cases where the application **knows the event type in advance**:

```sql
SELECT occurred_at, event_id
FROM sensor_events_by_type_day
WHERE tenant_id = 'acme'
  AND device_id = 3f8d8c10-0bfe-4f27-b7f5-975e1db0d181
  AND event_day = '2026-11-21'
  AND event_type = 'temperature'
  AND occurred_at >= '2026-11-21T08:00:00+0700';
```

**Note:** `sensor_events_by_type_day` is **another illustrative table**, not created by the statements above. If implementing Option B, create that table with the corresponding partition key and clustering order before running the query.

If only the `occurred_at` range is known without `event_type`, Option B no longer allows scanning a single contiguous time range across the partition via a clustering key prefix. Thus, the question "which column to order by first?" is really "which condition does the application filter on first?"

In Cassandra, you can store **multiple tables representing the same entity** organized around different queries. This is *query-driven table design*, rather than expecting one table to answer every query type efficiently.

## 9. "Storage order" does not mean the whole partition sits in one place on disk

At the data model level, rows within a partition are ordered by the clustering key. At the physical storage level, Cassandra uses an **LSM-tree**-style architecture:

1. Writes are accepted by Cassandra's write path and accumulated in a *memtable*.
2. On flush, data is written out as immutable **SSTables**, organized in key order.
3. A single logical partition can have versions or slices of data spread across **multiple SSTables**; Cassandra merges results on read.
4. **Compaction** merges/rewrites SSTables according to the configured strategy, managing versions and obsolete data. **Repair** synchronizes data across replicas; neither changes the table's partition/clustering key definition.

Therefore, the statement "clustering keys sort data physically" should be understood as **the ordering rule within a partition used by the storage and query engine**, not that the entire partition permanently resides contiguously in a single file.

Clustering keys also **do not solve oversized partitions**. If the partition key only includes `device_id` and the device writes continuously, that partition still grows indefinitely even if the data is perfectly time-ordered. To bound size, you must bucket by day/hour/month in the **partition key**, such as `(tenant_id, device_id, event_day)`.

### What do pagination and ordering mean?

For a partition with millions of events, use sensible limits and the driver's pagination feature when traversing many rows. Pagination controls the amount of data fetched per page without changing the nature of clustering order. For continuously written data, a sequence of multiple queries at different moments does not automatically form a consistent snapshot of the entire history; read logic must be designed around business requirements.

## 10. Using clustering keys from a Java application

The example below uses the Java Driver 4.x API, assuming an existing `CqlSession` and the `sensor_events_by_device_day` table. The prepared statement provides equality predicates for the partition key, then reads results in clustering order:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class SensorEventReader {
    private final CqlSession session;
    private final PreparedStatement latestInDay;

    public SensorEventReader(CqlSession session) {
        this.session = session;
        this.latestInDay = session.prepare(
            "SELECT occurred_at, temperature " +
            "FROM sensor_events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "LIMIT 20"
        );
    }

    public List<Instant> recentTimes(
            String tenantId, UUID deviceId, LocalDate day) {

        ResultSet rows = session.execute(
            latestInDay.bind(tenantId, deviceId, day)
        );

        List<Instant> result = new ArrayList<>();
        for (Row row : rows) {
            result.add(row.getInstant("occurred_at"));
        }
        return result;
    }
}
```

The code above demonstrates binding the full partition key and reading the built-in order. In a production system, you must decide on `event_day` calculation rules, page size, timeouts, consistency levels, and error handling when a replica fails to respond; none of those settings alter the clustering key structure.

## 11. Common mistakes and fixes

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Two events with the same timestamp "lose one row" | Primary key only has `occurred_at`, with no secondary identifier. | Add a stable `event_id` to the clustering key. |
| Fetching latest records still processes a huge dataset each time | Oversized partition or unbounded query. | Use buckets in the partition key, `LIMIT`, and appropriate pagination. |
| Wanting `ORDER BY temperature` but Cassandra rejects it | `temperature` is a regular column. | Design a dedicated access path/table if this is a primary requirement. |
| Need to filter `event_id` without `occurred_at` | Skipping the first clustering column. | Use an event-ID lookup table or a different key model. |
| All records for a day land in one partition | Partition key only contains low-cardinality `event_day`. | Combine with tenant/device or an entity with suitable cardinality. |
| Hard to fetch time-series ranges despite having a timestamp column | `event_type` precedes `occurred_at` while the query does not bind the type. | Reorder clustering columns in a new table or add a time-based query table. |
| Data "is not sorted cluster-wide" | Confusing intra-partition clustering order with global order. | Read each partition/bucket and merge order in the application if needed. |

If you want to change the **primary key structure** or defined clustering order of a deployed table, you generally need to create a new table, migrate/backfill data, and switch read/write traffic; do not treat this as a simple `ALTER TABLE` operation. Test schemas against a realistic query suite before putting them into production.

## 12. Self-check exercises

Given the table:

```sql
CREATE TABLE activities_by_user_week (
    tenant_id text,
    user_id uuid,
    week_start date,
    activity_type text,
    occurred_at timestamp,
    activity_id uuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, user_id, week_start),
        activity_type,
        occurred_at,
        activity_id
    )
) WITH CLUSTERING ORDER BY (
    activity_type ASC,
    occurred_at DESC,
    activity_id ASC
);
```

Answer for yourself:

1. Which columns form the partition key? How many clustering columns are there?
2. Within the same week and same user, by which criterion are activities with different `activity_type` grouped/ordered first?
3. Do two activities with the same `activity_type` and `occurred_at`, but different `activity_id`, create two rows?
4. To fetch the 10 most recent activities of type `login`, which conditions must be placed in `WHERE`?
5. To fetch the 10 most recent activities **regardless of type**, does this table return results in global chronological order for the partition?
6. Moving `activity_type` from the first clustering position to after `occurred_at` will prioritize which query pattern?

**Answers with explanations:**

1. Composite partition key `(tenant_id, user_id, week_start)`; three clustering columns in the order `activity_type`, `occurred_at`, `activity_id`.
2. First by `activity_type ASC`. Only within each `activity_type` value are rows ordered by `occurred_at DESC`, followed by `activity_id ASC`.
3. Yes, because `activity_id` is part of the primary key; the full keys of the two rows differ.
4. Provide full `tenant_id`, `user_id`, `week_start`, and `activity_type = 'login'`, then `LIMIT 10`. Since we want the 10 newest within type `login`, the default clustering order satisfies it.
5. No. Rows are grouped by `activity_type` first, so the first 10 rows may belong only to the alphabetically first types rather than the 10 newest events across all types.
6. Prioritizes querying by **time across activity types**; if filtering by type is also needed, consider adding a specialized table.

## 13. Takeaways for Cassandra table design

- **Partition keys select the partition; clustering keys identify and order rows inside the partition.**
- **The order of clustering columns in `PRIMARY KEY`** determines comparison precedence. `CLUSTERING ORDER BY` determines `ASC`/`DESC` direction.
- To read by a later clustering column, you typically must bind preceding clustering columns; **ranges** are normally placed on the first unfixed clustering column.
- `LIMIT`, `ORDER BY`, and range filtering are effective when queries match the partition key and clustering key; they do not turn intra-partition order into global order.
- Choose clustering columns based on primary queries and include a tie-breaking column whenever sort values can collide. To bound partition size, you must design an appropriate **partition key/bucket**.

Mastering clustering keys helps you read data in the intended order, write CQL with predictable cost, and choose wide-column table structures suited to Java services connecting to Apache Cassandra.
