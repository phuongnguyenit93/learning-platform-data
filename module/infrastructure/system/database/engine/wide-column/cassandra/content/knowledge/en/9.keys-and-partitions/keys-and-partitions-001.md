# Relationship Between Primary Key, Partition Key, and Clustering Column

In Apache Cassandra, `PRIMARY KEY` simultaneously identifies a row of data, determines **where data is distributed**, and defines **how rows within the same partition are ordered**. This is an important difference from how a primary key is typically understood in relational databases.

After this lesson, you will be able to:

- Distinguish `primary key`, `partition key`, and `clustering column` through CQL syntax.
- Explain why rows with the same partition key reside in the same logical partition and are stored on the same set of replicas.
- Design tables based on queries, especially queries targeting a single entity and a time range.
- Recognize designs that cause oversized partitions, uneven load distribution, or fail to support the intended queries.

## 1. How are the three concepts related?

A Cassandra table has one `PRIMARY KEY`, consisting of a **mandatory partition key** and **zero or more clustering columns**:

```text
PRIMARY KEY = partition key + [clustering column 1, clustering column 2, ...]
               |                         |
               |                         +-- Identifies and orders rows
               +-- Identifies partition and distribution placement
```

| Component | Function | Scope of impact |
| --- | --- | --- |
| **Primary key** | Uniquely identifies a logical row; consists of the full partition key and clustering columns (if any). | Table-wide. |
| **Partition key** | Forms the partition key value; Cassandra computes a token to determine the replicas responsible for storing the partition. | Data distribution across nodes/replicas. |
| **Clustering column** | Distinguishes rows within the same partition and determines their sort order. | Within a single partition. |

**Rules for identifying from CQL:**

```sql
-- Single column as partition key, no clustering column.
PRIMARY KEY (user_id)

-- user_id is the partition key; created_at is the clustering column.
PRIMARY KEY (user_id, created_at)

-- Composite partition key consisting of tenant_id and user_id;
-- created_at is the clustering column.
PRIMARY KEY ((tenant_id, user_id), created_at)

-- Composite partition key consisting of two columns;
-- created_at and event_id are two clustering columns in order.
PRIMARY KEY ((tenant_id, user_id), created_at, event_id)
```

Parentheses have **semantic meaning**, not just formatting purpose:

- `PRIMARY KEY (tenant_id, user_id, created_at)` has **`tenant_id`** as the partition key; `user_id` and `created_at` are clustering columns.
- `PRIMARY KEY ((tenant_id, user_id), created_at)` has the composite partition key **`(tenant_id, user_id)`**; only `created_at` is a clustering column.

These two declarations enable very different query patterns and produce very different data distributions.

> **Remember:** `primary key` is the full coordinate of a row; `partition key` selects the partition; `clustering columns` select the row's position *inside* that partition.

## 2. From partition key to partitions and replicas

Cassandra is a distributed wide-column database. Each **complete partition key value** corresponds to one logical partition. With a composite partition key, the *combination* of all components must be considered, not just individual components.

For example, suppose the partition key is `(tenant_id, device_id, event_day)`:

```text
(acme, device-01, 2026-11-21) ── token ──> replica set responsible for partition A
     ├─ (08:30, event-01) : temperature = 38.2
     ├─ (08:20, event-02) : temperature = 37.9
     └─ (08:10, event-03) : temperature = 37.7

(acme, device-01, 2026-11-22) ── token ──> replica set responsible for partition B
     └─ (09:00, event-04) : temperature = 38.0

(acme, device-02, 2026-11-21) ── token ──> replica set responsible for partition C
     └─ (08:30, event-05) : temperature = 36.5
```

Names A/B/C here represent **logical partitions**, without implying they are necessarily placed on different servers. Cassandra uses a partitioner (commonly `Murmur3Partitioner`) to map the partition key to a token; the replication strategy along with the ring topology determines which nodes hold replicas. The number of replicas depends on the keyspace's `replication factor`.

Direct consequences:

1. Two rows with the same values for *all* partition key components belong to the same logical partition and the same responsible replica set.
2. Changing one partition key component can change the token, so the row may reside on a different replica set.
3. Clustering columns **do not participate in determining the token**; they organize rows after the partition has been determined.
4. A logical partition does not equal a single contiguous block of data on disk: the LSM/SSTable storage engine can spread a partition's data across multiple files prior to compaction.

## 3. Reading a table definition from left to right

Consider the requirement: an IoT system needs to fetch the **20 latest events of a device in a day**, or fetch that device's events within a time range. Each customer (`tenant`) owns many devices; multi-day data must have bounded partition sizes.

```sql
CREATE TABLE sensor_events_by_device_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    timeuuid,
    event_type  text,
    reading     double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

In this example:

| Component | Columns | Meaning |
| --- | --- | --- |
| Partition key | `(tenant_id, device_id, event_day)` | Each device of each tenant has one partition per day. |
| Clustering column 1 | `event_time` | Orders events by timestamp, newest first. |
| Clustering column 2 | `event_id` | Distinguishes events that share the same `event_time`; provides secondary ordering. |
| Full primary key | `(tenant_id, device_id, event_day, event_time, event_id)` | Identifies an event row. |
| Regular columns | `event_type`, `reading` | Event payload data; does not participate in row identification or partition placement. |

`CLUSTERING ORDER BY` specifies the logical physical order when reading rows by the clustering key. If omitted, the default clustering order is ascending (`ASC`). It does not provide arbitrary sorting on regular columns.

Let's write two events for the same device, same day, and same measurement timestamp:

```sql
INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, event_type, reading
) VALUES (
    'acme', a14d4f48-5ca8-4c4e-9b13-3c9680cdb993, '2026-11-21',
    '2026-11-21T08:30:00+0700', now(), 'temperature', 38.2
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, event_type, reading
) VALUES (
    'acme', a14d4f48-5ca8-4c4e-9b13-3c9680cdb993, '2026-11-21',
    '2026-11-21T08:30:00+0700', now(), 'temperature', 38.3
);
```

CQL's `now()` function generates a new `timeuuid` value for `event_id`, so the two statements can create two distinct rows even with identical `event_time`. In a real system, if idempotency against duplicate writes from retries is needed, use a stable `event_id` supplied by the application instead of generating a new ID on every retry.

If you write **the exact same primary key combination** again, Cassandra updates/overwrites the column values of the **same logical row** according to timestamp-based conflict resolution rules; it does not create a new row. Therefore, adding a clustering column purely for uniqueness should originate from a true event identifier.

## 4. The primary key determines which queries are efficient

The starting point is selecting the exact partition using the **full partition key**, then using clustering columns to limit or order results within the partition.

### Fetching the latest events of a device in a day

```sql
SELECT event_time, event_id, event_type, reading
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = a14d4f48-5ca8-4c4e-9b13-3c9680cdb993
  AND event_day = '2026-11-21'
LIMIT 20;
```

Because the schema declares `event_time DESC, event_id DESC`, results in the partition are read in that order. Cassandra does not need to scan all devices or sort the entire table to find the first 20 events of this partition.

### Fetching events within a time range

```sql
SELECT event_time, event_id, event_type, reading
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = a14d4f48-5ca8-4c4e-9b13-3c9680cdb993
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00+0700'
  AND event_time <  '2026-11-21T09:00:00+0700';
```

The query uses equality predicates on the entire partition key and range predicates on the first clustering column. If querying **across multiple days** is needed, the application can read each relevant day bucket and merge the results, or create an additional table suited for cross-day query patterns.

### Queries that do not match the key

With the table just created, the following patterns are **not standard partition access paths**:

```sql
-- Missing two components of the composite partition key:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme';

-- Partition key not specified; event_type is only a regular column:
SELECT * FROM sensor_events_by_device_day
WHERE event_type = 'temperature';
```

Without an appropriate indexing mechanism, Cassandra usually rejects these queries because they require broad filtering. `ALLOW FILTERING` can permit some cases, but it easily causes scanning large amounts of data and unpredictable latency; **it should not be treated as a fix for an unsuitable key model**. When querying events by type across a whole tenant is required, design a dedicated query table or evaluate indexes suited to the data and Cassandra version in use.

For `ORDER BY` in CQL, the sorted columns must be clustering columns in a supported key order; this operation is most useful when the exact partition has already been selected. It does not replace arbitrary `ORDER BY` over a set of rows scattered across the cluster as in relational SQL.

## 5. What establishes row uniqueness?

Consider three records for the same device and same day:

| `event_time` | `event_id` | Result |
| --- | --- | --- |
| `08:30:00` | `id-A` | Row 1. |
| `08:30:00` | `id-B` | Row 2, because the clustering key `event_id` differs. |
| `08:30:00` | `id-A` | Same primary key as row 1; writes to row 1, not a row 3. |

We must distinguish **primary key uniqueness** from a business constraint. Cassandra does not automatically enforce that `event_id` values in *different partitions* are globally unique: if `event_id` is not the entire primary key, two rows in two different partitions can have the same value. To enforce uniqueness at another scope, appropriate key design, write workflows, or coordination mechanisms are needed.

Primary key columns cannot have `null` values in the key of a written row. Changing a primary key means changing the row's coordinates: it typically requires writing a new row at the new key and, if needed, deleting the old row. `UPDATE` is only used to modify values of non-primary-key columns of a row already identified by the key.

## 6. Choosing the partition key: balancing query speed and load distribution

A good partition key must simultaneously satisfy two goals:

1. **Match the primary query pattern:** conditions commonly present in `WHERE` must identify the partition key without scanning the entire cluster.
2. **Keep partition size and load reasonable:** avoid letting a single key value accumulate unbounded data or receive the majority of write/read traffic.

Suppose a device generates 1,000 events per day, with an average data size of 1 KiB/event (illustrative assumption only, excluding metadata, tombstones, and compression):

| Partition key design | Estimated logical scale | Remarks |
| --- | --- | --- |
| `(tenant_id, device_id)` | Around 365,000 rows, equivalent to 356 MiB after one year. | Partition grows continuously over time, hard to bound. |
| `(tenant_id, device_id, event_day)` | Around 1,000 rows, equivalent to 0.98 MiB per day. | Bounds data by day; easy to read daily history. |
| `(tenant_id, device_id, event_time)` | Nearly one partition per event. | Easily fragments data and loses the benefit of reading time-series within one partition. |

The numbers only describe hypothetical data volume; actual SSTable size also depends on column types, number of updates/deletes, tombstones, compression, and compaction. Bucketing by hour, day, or month must be chosen based on **actual throughput and read requirements**; there is no single optimal bucket size for every system.

A design that looks reasonable at first glance but easily creates a **hot partition** is:

```sql
PRIMARY KEY (tenant_id, device_id, event_time)
```

Here only `tenant_id` is the partition key. If a tenant is very large, all events of that tenant land in a single partition regardless of the number of devices; `device_id` and `event_time` are merely clustering columns. To partition by device/day, you need to write:

```sql
PRIMARY KEY ((tenant_id, device_id, event_day), event_time, event_id)
```

Increasing `replication factor` does not automatically split an oversized partition into multiple independent partitions; replicas still carry the same logical data volume. To avoid hotspots, you must fix the partition key selection or bucket according to access patterns.

## 7. Common design mistakes

| Symptom | Key-related cause | Remediation |
| --- | --- | --- |
| Slow tenant-wide reads, some nodes overloaded | Using only `tenant_id` as the partition key despite high data volume for that tenant. | Add appropriate partitioning components by entity, time, or bucket. |
| Querying by `device_id` when schema requires `tenant_id` and `event_day` | Missing partition key components in the query. | Ensure the application knows the full key, or design another table for that query. |
| Two events with the same timestamp get merged | Primary key only has `event_time` as the clustering column. | Add a stable event identifier such as `event_id` to the clustering key. |
| Need to search by `event_type` but forced to use `ALLOW FILTERING` | `event_type` is not on the partition/clustering key access path. | Design a query-driven table or evaluate an appropriate index. |
| Unbounded data growth within a partition | No time bucket or bucket is not small enough. | Split by day/hour/month depending on ingestion rate and read requirements. |
| Every event resides in a separate partition despite frequent time-range reads | Putting a high-cardinality timestamp into the partition key. | Keep entity/bucket identifiers in the partition key; place timestamp in a clustering column. |

In Cassandra, **changing the primary key structure typically requires creating a new table, migrating data, and switching read/write traffic**, rather than just running `ALTER TABLE` to change the key. Therefore, you should determine queries and estimate partition sizes before deployment.

## 8. Self-check with another example

Given a table storing orders by customer:

```sql
CREATE TABLE orders_by_customer (
    tenant_id    text,
    customer_id  uuid,
    created_at   timestamp,
    order_id     uuid,
    amount       decimal,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Answer these yourself before looking at the hints:

1. Do two orders with the same `tenant_id`, same `customer_id`, and different `created_at` belong to the same partition?
2. Do two orders with the same `customer_id` but different `tenant_id` necessarily belong to the same partition?
3. Is querying the order history of **one** customer within a `created_at` range suitable for this schema?
4. Can you efficiently use only `WHERE created_at >= ...` to read all latest orders across all tenants with this table?

**Answers:** (1) Yes, because the partition key is identical; `created_at` only affects row ordering/identity. (2) No, because `tenant_id` is part of the partition key. (3) Yes, when providing `tenant_id` and `customer_id` and then range-filtering on `created_at`. (4) No; global time-based queries require designing a different access path.

## 9. Principles to take into practice

- Reading `PRIMARY KEY` syntax: the **innermost pair of parentheses** defines the composite partition key; the following columns are clustering columns.
- Choose the partition key based on query predicates and partition size/load bounds; token distribution happens across the **entire** partition key.
- Choose clustering columns to identify rows within a partition and support ordered/range reads; clustering column order matters.
- The same primary key means the same logical row. To allow multiple events with the same timestamp, add a distinguishing column to the key.
- Cassandra encourages **query-driven table design**. Distinct access patterns may require dedicated query tables rather than forcing one table to serve every `WHERE` and `ORDER BY`.

Understanding these three key types properly forms the foundation for learning next about tokens, replication, read/write consistency levels, oversized partitions, compaction, and operating Cassandra in Java applications.
