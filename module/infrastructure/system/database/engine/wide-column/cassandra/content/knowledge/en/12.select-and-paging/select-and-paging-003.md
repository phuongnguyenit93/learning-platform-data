# Querying by Full Key or Range Within a Partition

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between querying by **full primary key**, by **full partition key**, and by a **clustering key range within a partition**.
2. Write CQL to fetch an exact single row, rows sharing a timestamp, or a time range with clear start and end boundaries.
3. Choose between `=`, `>`, `>=`, `<`, `<=`, and tuple comparisons across multiple clustering columns.
4. Combine clustering order, `ORDER BY`, and `LIMIT` to power an event history page without confusing result limits with read-scope limits.
5. Use the last key of a page as a cursor to continue, and distinguish this approach from the Cassandra Java driver's paging state.
6. Recognize queries that scan multiple partitions, are rejected due to missing key components, or carry risks from overly large partitions.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Apache Cassandra distributes data by **partition key**, stores rows inside each partition by **clustering columns**, and serves queries most efficiently when the table model is designed around read patterns. These fundamentals form the basis before integrating CQL into Java applications, choosing read/write consistency levels, and evaluating latency on multi-replica clusters.

## 1. Three Levels of Data Targeting

Start with a table whose key is:

```sql
PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
```

| Key part | Meaning | Role during queries |
| --- | --- | --- |
| `account_id`, `event_day` | **Composite partition key** | Together identify the partition and responsible replicas. |
| `occurred_at` | First clustering column | Orders and bounds rows chronologically within the partition. |
| `event_id` | Second clustering column | Disambiguates events at the same timestamp; establishes a deterministic position in clustering order. |

Three query patterns:

| Query type | Required columns | Possible rows returned |
| --- | --- | --- |
| **Full key** | `account_id`, `event_day`, `occurred_at`, `event_id` | At most **one row**. |
| **Full partition** | `account_id`, `event_day` | Potentially **many rows** within the same partition. |
| **Range within partition** | Full partition key + constraints on clustering key | A **slice** of rows matching the range or key tuple. |

Diagram for one partition:

```text
                  account_id=A, event_day=2026-11-20
                              (partition)
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
   08:00 / id-1              09:30 / id-2              09:30 / id-3
        |                         |                         |
    event row                  event row                 event row
                                  |
                             11:00 / id-4
                                  |
                              event row

Full key               ->  09:30 / id-2
Full partition         ->  all 4 rows
Range [09:00, 11:00)   ->  09:30 / id-2 and 09:30 / id-3
```

**Note:** Read scope is primarily determined by the conditions in `WHERE`. `SELECT` only specifies which columns to return. A `SELECT event_type` statement cannot find an event by itself without the required key conditions.

## 2. Setting Up the Table and Sample Data in cqlsh

Suppose an account activity management application needs two operations: retrieving details for **a single event** when its key is known, and displaying a **daily activity log over a time range**.

```sql
-- Only use SimpleStrategy with one replica for a single-node lab.
CREATE KEYSPACE IF NOT EXISTS cassandra_range_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_range_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

Choosing `ASC` on both clustering columns highlights the ordering behavior clearly: older events come first, and events at the same timestamp are sorted by `event_id`.

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed order'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Clicked details'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'LOGOUT', 'Logged out'
);

-- Events from another day reside in a different partition.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:30:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Logged in next day'
);
```

The sample dataset has four rows in partition `(1111..., 2026-11-20)` and one row in partition `(1111..., 2026-11-21)`. Fixed key values are used so re-running the examples produces the same state: a CQL `INSERT` on the same primary key is an upsert.

**Time convention:** Timestamp strings explicitly specify the `+0000` offset, meaning UTC. The `timestamp` type stores an instant in time, not the original time zone separately. In Java, use `Instant` for this value and derive `event_day` using your business-date rules; do not silently assume UTC date always equals the user's local date.

## 3. Querying by Full Primary Key: Fetching a Single Row

To fetch details of the `VIEW` event at its known position, supply the entire partition key and every clustering column:

```sql
SELECT account_id, event_day, occurred_at, event_id, event_type, payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

**Expected result:** exactly one row with `event_type = 'VIEW'` and `payload = 'Viewed order'`.

Conceptual read flow:

1. The coordinator computes the token for the **pair** `(account_id, event_day)` and identifies the responsible replicas.
2. Inside the partition, the clustering key `(occurred_at, event_id)` pinpoints a single row.
3. The columns listed in `SELECT` determine which data is returned.

Knowing only `event_id` is not enough to locate an event:

```sql
-- No direct query path with the current schema:
SELECT event_type, payload
FROM events_by_account_day
WHERE event_id = 00000000-0000-4000-8000-000000000002;
```

In this table, `event_id` is the **second** clustering column, not the partition key and not a cluster-wide lookup index. If the product must open details using only an `event_id`, either embed the full key in links or design an additional lookup table by ID.

### When Only a Prefix of the Clustering Key Is Known

Because the sample data has two events at `09:30`, the following condition returns **two rows**:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000';
```

Equality on `occurred_at` selects a **group of rows sharing the clustering key prefix**; it only becomes a single-row point lookup if `event_id` is also specified. This is why an extra disambiguating column is needed when multiple events share the same timestamp.

## 4. Querying an Entire Partition: Fetching a Set of Rows

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

A query with only the full partition key returns **four rows**, in the defined clustering order `(occurred_at ASC, event_id ASC)`. No clustering condition is needed when the goal is the entire log for the day.

| `occurred_at` (UTC) | `event_id` (suffix) | `event_type` |
| --- | --- | --- |
| 08:00 | `...0001` | `LOGIN` |
| 09:30 | `...0002` | `VIEW` |
| 09:30 | `...0003` | `CLICK` |
| 11:00 | `...0004` | `LOGOUT` |

From a performance standpoint, providing the full partition key avoids scanning across all partitions. However, **a single partition can still contain many rows or many tombstones**. Querying a huge partition in full can still consume substantial RAM, I/O, and read latency. Therefore, choose `event_day` or another bucket granularity sized to your actual traffic.

If you write only `WHERE account_id = ...` without `event_day`, CQL cannot pinpoint a single partition under the composite partition key; normal queries are rejected or require scanning/filtering unsuitable for real-time APIs.

## 5. Querying a Clustering Column Range Within One Partition

This is a common read pattern for timelines, activity logs, or time-series data.

### 5.1. Half-Open Interval `[start, end)`

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 11:00:00+0000';
```

This returns exactly the **two events `VIEW` and `CLICK` at 09:30**. The `LOGOUT` row at 11:00 is excluded because the upper bound uses `<`.

Interval notation:

```text
08:00             09:00          09:30                   11:00
  |                  [          VIEW, CLICK                 )
  |                  |             |                        |
 LOGIN           included   two rows at same time    excludes LOGOUT
```

This is a useful convention when splitting a day into non-overlapping windows:

- Window one: `[09:00, 11:00)`.
- Window two: `[11:00, 13:00)`.

An event at exactly `11:00` belongs only to window two. Using `<=` in window one as well could count the boundary row twice.

### 5.2. Boundary Types

| CQL on `occurred_at` | Meaning | At exact boundary |
| --- | --- | --- |
| `>= T` | From T onward | Includes T. |
| `> T` | Strictly after T | Excludes T. |
| `<= T` | Up to and including T | Includes T. |
| `< T` | Strictly before T | Excludes T. |
| `>= T1 AND < T2` | Half-open interval `[T1, T2)` | Includes T1, excludes T2. |

These `>`, `>=`, `<`, `<=` comparisons apply to **clustering column `occurred_at`** after providing the full partition key. They do not imply the ability to run direct range queries on `event_day`, which is a component of the partition key.

### 5.3. Single-Sided Bounds Are Also Valid

```sql
-- All events starting from 09:30 (both rows at the same timestamp).
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:30:00+0000';

-- All events before 09:30, excluding the two 09:30 rows.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at < '2026-11-20 09:30:00+0000';
```

One-sided bounds are useful for "view recent events" or "view before a cutoff," but if a partition holds large amounts of data, add an appropriate `LIMIT` or organize buckets to bound the scope.

## 6. Multiple Clustering Columns: Prefixes, Tuples, and Exact Boundaries

In this table, the clustering order is:

```text
occurred_at ASC -> event_id ASC
```

Conditions on clustering columns must respect **prefixes in their declared order**. Example:

```sql
-- Valid: fixes occurred_at, then constrains event_id.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

The result is the `CLICK` row whose `event_id` ends with `...0003`. Because `occurred_at` is fixed to a single value, a range on `event_id` produces a valid slice within that timestamp group.

Conversely:

```sql
-- Invalid along the normal key path: skips occurred_at.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id > 00000000-0000-4000-8000-000000000002;

-- Cannot treat these two conditions as a contiguous clustering range.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at > '2026-11-20 09:00:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

When you need to compare a **complete pair of clustering columns** left to right, CQL supports tuples:

```sql
-- Tuple boundary: strictly after the key pair (09:30, ...0002).
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  );
```

With both columns ordered `ASC`, the tuple expression means **rows that follow `(09:30, ...0002)` in lexicographical order**:

- `(09:30, ...0003)` is included because the timestamp matches and the ID is greater.
- `(11:00, ...0004)` is included because the timestamp is greater, regardless of ID.
- `(09:30, ...0002)` is excluded because of the strict `>` operator.

**Crucial difference:** `(occurred_at, event_id) > (T, I)` is not equivalent to `occurred_at > T AND event_id > I`. The tuple form defines a boundary over an **ordered key pair**; two separate inequalities require both components to be greater and are generally not supported by CQL as a single slice.

When clustering order uses `DESC` or mixes `ASC`/`DESC`, verify the cursor semantics and tuple comparison support for your Cassandra version. The examples above intentionally use **two `ASC` columns** to avoid ambiguity.

## 7. Combining ORDER BY and LIMIT

### 7.1. Reading Oldest-to-Newest or Reversed

```sql
-- Default table order: oldest first.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;

-- Reversed order: newest first.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

The first query returns `LOGIN 08:00`, `VIEW 09:30`. The second returns `LOGOUT 11:00`, `CLICK 09:30`. Cassandra only supports `ORDER BY` on clustering columns matching the declared order (or its supported exact reverse); it cannot arbitrarily sort by `event_type` or `payload`.

### 7.2. LIMIT Caps Output, Not Partition Routing

```sql
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
ORDER BY occurred_at ASC
LIMIT 2;
```

In the sample data, this limit suffices to return `VIEW` and `CLICK`. However, `LIMIT 2` does not turn `WHERE event_type = 'VIEW'` into a partition-targeted query, nor does it turn a massive partition into a good data model.

Distinguish:

- `LIMIT n` is the maximum total rows for the **entire result**.
- `PER PARTITION LIMIT n` caps the number of rows **per partition** when a query touches multiple partitions.
- **Page size** in the Java driver is the target number of rows fetched per round trip in the paging protocol, **not** the total rows permitted to be returned.

## 8. Key-Based Paging: Avoiding Skipped Rows on Duplicate Timestamps

Suppose an API fetches **two events per page**, oldest first. After the first page, the next page must start *immediately after the full key of the last row*, not solely based on timestamp.

### First Page

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Returns:

| `occurred_at` | `event_id` | `event_type` |
| --- | --- | --- |
| 08:00 | `...0001` | `LOGIN` |
| 09:30 | `...0002` | `VIEW` |

The last key on page one is `(09:30, ...0002)`.

### Next Page Using Tuple Cursor

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  )
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Returns:

| `occurred_at` | `event_id` | `event_type` |
| --- | --- | --- |
| 09:30 | `...0003` | `CLICK` |
| 11:00 | `...0004` | `LOGOUT` |

If page two used `occurred_at > '2026-11-20 09:30:00+0000'`, the `CLICK` event at 09:30 would be **missed**, because it shares the same timestamp as `VIEW` at the end of page one. A tuple cursor solves this with a **unique and deterministic** ordering key combining timestamp and ID.

### Tuple Cursor and Paging State Serve Different Roles

| Mechanism | How it works | When it fits |
| --- | --- | --- |
| **Keyset/tuple cursor** | Application stores the last clustering key tuple and applies a comparison predicate on the next request. | When you want a data-interpretable cursor, explicit boundary control, and queries scoped to one partition. |
| **Driver paging state** | Cassandra Java driver receives/passes a continuation token for the **exact same query**. | When you want to iterate across pages of a single query without manually constructing clustering conditions. |
| **OFFSET** | Skips N rows and fetches the next N rows. | Cassandra CQL does not provide SQL-style `LIMIT ... OFFSET ...`. |

Do not swap a paging state across queries with different `WHERE` clauses, bind values, sort orders, or page sizes. Nor should you treat paging state as a business token safe for arbitrary client modification. When an API accepts a token from a client, protect its integrity and bind it to the appropriate query/user scope.

Neither keyset cursors nor paging state **automatically create an immutable snapshot**. New writes, deletes, TTL expirations, and data changes between requests can alter the visible result set. Depending on the use case, consider fixing the upper time window and defining how evolving data should be handled.

## 9. Reading Across Multiple Days: One Partition per Day

Because the table's partition key is `(account_id, event_day)`, a range condition `event_day >= ...` cannot keep the query inside a single partition.

```sql
-- Not a clustering range, because event_day is part of the partition key.
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20'
  AND event_day < '2026-11-22';
```

If you only need two specific days, you can target both partitions:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Note that `IN` on the last partition key component can trigger **multiple distributed reads**. Do not rely on it for a global chronological sort as within a single partition. For long date spans, consider querying bounded buckets sequentially and merging in the application tier, or adding another table if query needs do not match daily bucketing.

**Bucketing trade-offs:**

- Smaller buckets (by day or hour) keep row counts per partition manageable, but long-span queries must read more partitions.
- Larger buckets (by month or unbucketed) reduce the number of partitions needed for a history view, but risk creating large partitions that increase read, compaction, and repair overhead.

Choose bucket granularity based on write throughput, history lookback length, row size, pagination requirements, and observed cluster behavior.

## 10. Java Application: Point Lookup and Range Lookup with Bind Markers

Example with **Apache Cassandra Java Driver 4.x**; assumes an active `CqlSession session` connected to keyspace `cassandra_range_lab`.

### 10.1. Point Lookup by Full Primary Key

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID accountId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId = UUID.fromString("00000000-0000-4000-8000-000000000002");
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement byFullKey = session.prepare("""
    SELECT event_type, payload
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at = ?
      AND event_id = ?
    """);

BoundStatement exact = byFullKey.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T09:30:00Z"),
    eventId
);

Row row = session.execute(exact).one();
if (row != null) {
    System.out.println(row.getString("event_type"));
}
```

With prepared statements, bound Java types must match CQL types: `uuid` ↔ `UUID`, `date` ↔ `LocalDate`, `timestamp` ↔ `Instant`. `Row == null` indicates no matching row at the current read consistency level; do not treat it as stronger proof across all replicas.

### 10.2. Range Lookup Within a Partition

```java
PreparedStatement byTimeRange = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at >= ?
      AND occurred_at < ?
    ORDER BY occurred_at ASC, event_id ASC
    LIMIT ?
    """);

BoundStatement range = byTimeRange.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T11:00:00Z"),
    100
).setPageSize(50);

for (Row event : session.execute(range)) {
    System.out.printf("%s %s %s%n",
        event.getInstant("occurred_at"),
        event.getUuid("event_id"),
        event.getString("event_type")
    );
}
```

In this example, `LIMIT 100` caps the **entire CQL result**, while `setPageSize(50)` configures driver page fetching. Calling `CqlSession.execute(...)` and iterating through `ResultSet` can trigger automatic fetches for subsequent pages; if you need a cursor-paginated API, explicitly control the returned page and paging state instead of iterating across the entire result set.

This snippet uses Java text blocks (Java 15+). In older Java projects, replace text blocks with standard Java strings.

### 10.3. Consistency Does Not Change Key Semantics

In a distributed cluster, request consistency level (e.g., `LOCAL_ONE`, `LOCAL_QUORUM`) is configured on the driver or statement to match replication and freshness requirements. Whether doing a full-key lookup or a range scan, **the same primary key routes to the same partition**. Consistency level determines how many replicas must confirm a read and shapes the latency/availability/freshness trade-off; it never adds query paths for columns absent from the key.

When an application encounters timeouts or `Unavailable` exceptions, distinguish replica/cluster issues from `InvalidQuery` errors caused by key conditions. Increasing timeouts will not fix a `WHERE` clause missing the partition key.

## 11. Common Errors and Misconceptions

| Misconception or query | Why it is problematic | How to fix it |
| --- | --- | --- |
| `WHERE event_id = I` | `event_id` is not a partition key; no direct lookup path exists in the schema. | Store the full primary key when fetching details, or add a lookup table. |
| `WHERE account_id = A` | Missing `event_day` from the composite partition key. | Query known days or create a table serving account-wide reads. |
| `WHERE account_id = A AND event_day >= D` | `event_day` is part of the partition key, not a clustering key. | Use discrete day buckets; redesign if long date ranges are needed. |
| `WHERE occurred_at BETWEEN T1 AND T2` | Relational SQL habit; use supported CQL operators to express bounds. | Use `occurred_at >= T1 AND occurred_at < T2` within a known partition. |
| `WHERE account_id = A AND event_day = D AND event_id = I` | Skips the leading clustering column `occurred_at`. | Supply `occurred_at`, adjust the query, or design a new table. |
| `WHERE ... AND occurred_at > T AND event_id > I` | Two separate inequalities do not express a tuple boundary and are typically not supported as a single slice. | Use `(occurred_at, event_id) > (T, I)` with compatible key/clustering order. |
| `occurred_at > lastTime` for next page | Skips rows sharing the same timestamp as the last row of the previous page. | Store a cursor with both `occurred_at` and `event_id`, or use driver paging state. |
| `SELECT *` or `LIMIT 10` makes a query cheap by itself | Does not change read scope or partition routing. | Choose proper keys and buckets, bound ranges, and project only needed columns. |
| `ALLOW FILTERING` solves any filter condition | Can scan and filter many rows with unpredictable latency. | Redesign tables for the query or evaluate an index suited to the use case. |

## 12. Practice Exercises and Self-Check

### Exercise 1. Point Lookup

Retrieve the `payload` of the `CLICK` row at `09:30` on November 20, 2026 for the sample account, given `event_id` ending in `...0003`.

**Answer:**

```sql
SELECT payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

Expected result: `Clicked details`.

### Exercise 2. Range Lookup

Retrieve events on November 20 from `08:30` up to (**before**) `11:00` UTC.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 08:30:00+0000'
  AND occurred_at <  '2026-11-20 11:00:00+0000';
```

Returns the two rows `VIEW` and `CLICK` at `09:30`, excluding `LOGIN` at 08:00 and `LOGOUT` at 11:00.

### Exercise 3. Continuing Pagination Across Duplicate Timestamps

Page one ends with `(09:30, ...0002)`. Write the page-two condition so it neither repeats `VIEW` nor drops `CLICK`.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  )
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Returns `CLICK` and `LOGOUT`.

### Exercise 4. Identifying Invalid Conditions

Why is the following statement not an in-partition range query?

```sql
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day > '2026-11-20';
```

**Hint:** `event_day` participates in the **partition key**, so different date values select different partitions; it is not a clustering column that can be range-scanned after `account_id`. To read multiple days, you need the explicit partition list or a table tailored to that query pattern.

## 13. Practical Application Checklist

Before releasing a Cassandra data-reading endpoint:

1. **Single-row lookup:** do you have the full partition key and clustering key? If only a business ID is available, is it sufficient to locate the row or do you need a lookup table?
2. **Range lookup:** is the full partition key fixed and the range applied to an appropriate clustering column? Are inclusive/exclusive bounds unambiguous?
3. **Ordering:** is the desired order compatible with clustering order? If paginating via cursor, does the cursor include enough unique key columns so duplicate timestamps are never skipped?
4. **Multi-day data:** have you accounted for the number of partitions queried and the merge strategy?
5. **Production load:** how might partition size, row counts, tombstones, compaction, and repair impact latency? Do `LIMIT` and page size satisfy requirements while avoiding huge scans?
6. **Java driver:** are types bound properly (`UUID`, `LocalDate`, `Instant`), consistency/page size configured sensibly, and timeouts/retries/paging state handled per application policy?

The central rule is: **querying by full primary key locates one row; querying by full partition key locates one partition; clustering conditions narrow that partition to a slice**. Designing keys and buckets properly keeps query costs predictable when Cassandra runs distributed and replicated across multiple nodes.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation (SELECT, WHERE, ORDER BY, LIMIT)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition (PRIMARY KEY, CLUSTERING ORDER)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling Overview](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
