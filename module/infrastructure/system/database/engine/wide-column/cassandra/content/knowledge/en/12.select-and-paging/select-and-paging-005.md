# ORDER BY and Conditions Compatible with Clustering Keys

## Learning Objectives

After this lesson, you will be able to:

1. Explain why `ORDER BY` in Apache Cassandra relies on **clustering columns**, unlike arbitrary sorting in relational SQL.
2. Inspect `PRIMARY KEY` and `CLUSTERING ORDER BY` to predict the **default order** of rows within a partition.
3. Write valid `ORDER BY` clauses in the declared direction or its exact reverse, and identify unsupported column combinations and sort directions.
4. Combine `WHERE` conditions on the **partition key** and **clustering key prefixes** with `=`, time ranges, tuples, and `LIMIT`.
5. Use a full key boundary for stable pagination when multiple rows share the same timestamp.
6. Analyze how multi-partition `IN`, partition size, consistency levels, and the Java driver affect response latency.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Cassandra is a distributed wide-column database optimized for **query-driven table design**, using partition keys to determine where data lives and clustering columns to determine row order **within a partition**. Understanding `ORDER BY` properly lets you write CQL with predictable read costs while avoiding pitfalls when building Java APIs with replication, consistency, paging, and error handling.

## 1. What Does ORDER BY Actually Sort in Cassandra?

In many relational SQL databases, developers often write:

```sql
-- Illustrates a relational SQL mindset, NOT a query
-- guaranteed to be valid on the Cassandra schema below.
SELECT *
FROM events
WHERE event_type = 'LOGIN'
ORDER BY created_at DESC;
```

A relational engine can build a scan/index/sort plan to return the requested row set. By contrast, Cassandra prioritizes queries whose access path is already encoded in the **primary key**:

```text
                         PRIMARY KEY
                              |
             +----------------+----------------+
             |                                 |
        partition key                    clustering columns
             |                                 |
 select partition/replicas           select, order, and scan rows
             |                                 |
             +----------------+----------------+
                              |
                            SELECT
```

Therefore:

- `WHERE` with the **full partition key** precisely locates the target partition to read.
- **Clustering columns** define the built-in row ordering inside the partition.
- `ORDER BY` in CQL only serves orderings compatible with those clustering columns; it does not ask Cassandra to sort arbitrarily on any column.
- `ORDER BY` does not create a secondary index, turn regular columns into clustering keys, or rescue a query missing its partition key.

> Quick rule of thumb: in Cassandra, important query ordering must be **designed when creating the table**. `ORDER BY` mainly selects how to traverse the ordering already supported by the clustering key.

## 2. Building a Practice Table and Inspecting Clustering Order

Suppose an application needs an activity history screen for **one account on one day**. A common requirement is fetching events **newest first**, while also supporting switching to **oldest first**.

### 2.1. CQL Schema

```sql
-- Configuration intended for single-node lab only.
CREATE KEYSPACE IF NOT EXISTS cassandra_order_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_order_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((account_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id DESC);
```

Components:

| Component | Key type | Role |
| --- | --- | --- |
| `(account_id, event_day)` | Composite partition key | Both values together identify a single partition. |
| `created_at` | First clustering column | Orders by timestamp, newest first by default. |
| `event_id` | Second clustering column | Provides deterministic tie-breaking when two events share the same timestamp. |
| `event_type`, `detail` | Regular columns | Hold payload attributes; cannot be used for arbitrary `ORDER BY`. |

Here both `created_at` and `event_id` are declared `DESC`. Hence, the default read order inside a partition is:

```text
created_at from largest to smallest
     |
     +-- when created_at ties:
           event_id from largest to smallest
```

### 2.2. Inserting Sample Data with Duplicate Timestamps

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed order'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened order details'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Paid'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGOUT', 'Logged out'
);

-- Another partition for the same account.
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:30:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Next day'
);

-- Another account, another partition.
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGIN', 'Second account'
);
```

The sample dataset has **three populated partitions**: account A day 20 (5 rows), account A day 21 (1 row), and account B day 20 (1 row). The main examples below read only **account A's partition on 2026-11-20**. Since fixed keys are used, re-running `INSERT` on the same primary key is an upsert and does not create duplicate rows.

**Convention:** `created_at` uses timestamps with offset `+0000` (UTC). In Java, map CQL `timestamp` to `Instant`; `event_day` should follow your defined business time zone.

## 3. Default Order When ORDER BY Is Omitted

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Because the table was declared with `CLUSTERING ORDER BY (created_at DESC, event_id DESC)`, rows in this partition appear in this order:

| Position | `created_at` (UTC) | `event_id` (suffix) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 12:00 | `...0005` | `LOGOUT` |
| 2 | 11:00 | `...0004` | `PAY` |
| 3 | 09:30 | `...0003` | `CLICK` |
| 4 | 09:30 | `...0002` | `VIEW` |
| 5 | 08:00 | `...0001` | `LOGIN` |

The two rows at `09:30` are not ordered arbitrarily: `event_id` determines the secondary order. When building a real-time API, **full ordering by the complete clustering key** is essential for a pagination cursor that never drops rows.

Changing `SELECT created_at, event_id` to `SELECT event_type` only changes the **returned columns**, not the clustering order. If you want to browse "`PAY` events first," you must design a new key/query model—you cannot achieve it just by changing `SELECT`.

## 4. Valid ORDER BY: Declared Direction or Exact Reverse

### 4.1. Explicitly Writing the Default Order

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC;
```

For this partition, the result matches the query without `ORDER BY`. Writing it explicitly documents the newest-first intent in code and APIs, but it **does not perform a new arbitrary sort**.

### 4.2. Reversing the Entire Clustering Order

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at ASC, event_id ASC;
```

Rows are returned in this order:

| Position | `created_at` (UTC) | `event_id` (suffix) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 08:00 | `...0001` | `LOGIN` |
| 2 | 09:30 | `...0002` | `VIEW` |
| 3 | 09:30 | `...0003` | `CLICK` |
| 4 | 11:00 | `...0004` | `PAY` |
| 5 | 12:00 | `...0005` | `LOGOUT` |

This is the **uniformly reversed direction** of the schema's `DESC, DESC` order. Cassandra can traverse clustering order in reverse; actual performance—especially on large partitions—should be measured rather than assuming forward and reverse scans always cost the same.

### 4.3. Invalid Cases

For a table declared with two `DESC` columns:

```sql
-- Invalid: event_type is a regular column, not a clustering column.
SELECT created_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_type ASC;

-- Invalid: reverses event_id alone while created_at
-- remains in declared order; matches neither the original
-- (DESC, DESC) order nor its inverse (ASC, ASC).
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id ASC;

-- Invalid: skips the leading created_at column to
-- request direct ordering by event_id across the whole partition.
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_id DESC;
```

In principle, columns in `ORDER BY` must follow the **defined clustering key order**; skipping a leading clustering column does not allow sorting the entire partition by a trailing column. Even if a CQL version allows certain shorthand forms when preceding columns are fixed by equality, stick to explicit patterns and verify syntax on your running cluster version.

### 4.4. What If the Schema Mixes ASC and DESC?

Cassandra allows mixed clustering orders. For example, another table could be created as:

```sql
CREATE TABLE IF NOT EXISTS events_mixed_order (
    account_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id ASC);
```

This is a **separate** table solely to illustrate the rule, with no sample data loaded. When a schema uses `(DESC, ASC)`, the two valid directions are:

| Traversal direction | Clustering column order |
| --- | --- |
| Same as declared | `ORDER BY created_at DESC, event_id ASC` |
| Fully inverted declared order | `ORDER BY created_at ASC, event_id DESC` |
| Flipping only one column | Incompatible with forward or reverse traversal of the full clustering key. |

Do not flip a single column's direction and expect Cassandra to sort freely like an SQL engine sorting a temporary table. If an API frequently needs two non-dual sort orders, consider an **additional read table** with the matching clustering order.

## 5. WHERE Compatible with ORDER BY: The Partition Key Must Be Explicit

With `events_by_account_day`, the standard valid read pattern is:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

This is a **single-partition** query using the full composite partition key and scanning in clustering order. CQL `ORDER BY` cannot fix queries that lack a partition-locating path.

### 5.1. Valid vs. Invalid Examples

| Condition and ordering | Assessment | Reason |
| --- | --- | --- |
| `account_id = A AND event_day = D ORDER BY created_at DESC` | Valid | Full partition key; sorts by leading clustering column. |
| `account_id = A AND event_day = D ORDER BY created_at ASC, event_id ASC` | Valid | Exact reverse of `DESC, DESC`. |
| `account_id = A AND event_day = D AND created_at >= T ORDER BY created_at DESC` | Valid | Range on the leading clustering column within one partition. |
| `account_id = A AND event_day = D AND created_at = T AND event_id > I` | Valid | After fixing the first clustering column, the next can be constrained. |
| `account_id = A ORDER BY created_at DESC` | Missing partition key | Does not specify `event_day` of the composite partition key. |
| `event_day = D ORDER BY created_at DESC` | Missing partition key | Omits `account_id` from the partition key. |
| `account_id = A AND event_day >= D ORDER BY created_at DESC` | Not a valid range scan on partition key | `event_day` is part of the partition key, not a clustering column. |
| `account_id = A AND event_day = D ORDER BY event_type DESC` | Incompatible | `event_type` is a regular column. |

**Important detail:** the order in which conditions are listed in `WHERE` does not have to match column order in `PRIMARY KEY`; **the columns and predicate types** determine query validity. For clustering range scans, schema column order dictates which prefixes must be constrained.

## 6. WHERE on Clustering Columns: From Prefixes to Ranges

Inside a known partition, Cassandra stores rows ordered by `(created_at, event_id)`. Effective predicates typically use **equality on leading columns**, followed by a **range on the next column**.

### 6.1. Half-Open Time Interval

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at < '2026-11-20 12:00:00+0000'
ORDER BY created_at DESC, event_id DESC;
```

This is the interval **`[09:00, 12:00)`** over *timestamp values*. Results in order are `PAY 11:00`, `CLICK 09:30`, `VIEW 09:30`. `LOGOUT 12:00` is excluded because the upper bound uses `<`.

**`DESC` in the schema does not invert operator semantics:** `created_at >= 09:00` still means timestamps from 09:00 onward, even when rows are traversed newest-first. Keep **row-selection predicates** separate from **presentation order**.

### 6.2. Filtering by Equality on Timestamp First, Then by ID

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at = '2026-11-20 09:30:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002
ORDER BY created_at DESC, event_id DESC;
```

The result is the `CLICK` event whose ID ends in `...0003`. This condition is valid because `created_at`, the clustering column **preceding** `event_id`, is fixed.

Conversely, the following query does not form a standard clustering-order slice:

```sql
-- Missing condition on the first clustering column created_at.
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

Even when the partition is known, `event_id` values are grouped under each `created_at`; there is no single contiguous range by `event_id` alone across the entire partition. If you need this query pattern frequently, create a table with a matching clustering key or another lookup path.

### 6.3. Why Not Write Two Separate Inequalities?

```sql
-- Not the right way to express "after the key tuple (T, I)".
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at < '2026-11-20 09:30:00+0000'
  AND event_id < 00000000-0000-4000-8000-000000000003;
```

This does not define a unified cursor boundary: it requires **both timestamp and ID to be smaller**. Moreover, CQL generally rejects it as a standard slice once a range already exists on the preceding clustering column. To express a boundary spanning multiple clustering columns, use a **tuple comparison** when supported by your CQL version and clustering order.

For an example with two `DESC` columns, see the pagination section below.

## 7. ORDER BY When Using IN on the Partition Key

Single-partition queries are the most predictable. To retrieve specific days for the same account, you can use `IN` on the last component of the composite partition key:

```sql
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

This targets **two partitions**: `(account A, day 20)` and `(account A, day 21)`. Unlike single-partition queries, clustering order inside each partition **does not guarantee a global timeline** when combining days.

In CQL versions that permit combining partition-key `IN` with `ORDER BY`, merging/sorting across multiple partitions can increase overhead, including in-memory sorting on the coordinator. Therefore, even if a query like the one below is accepted by the cluster, verify version constraints and measure latency:

```sql
-- Carefully consider cost when IN touches multiple partitions.
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

If an API needs "the 20 newest events for an account across **all days**" at scale, more predictable options usually are:

1. Bound the list of date buckets to read based on a realistic lookback window.
2. Read a bounded slice from each partition, then merge rows by `(created_at, event_id)` in the application layer using explicit rules, or
3. Create another read table if sorting across all days is a primary query path.

Never assume `LIMIT 20` causes Cassandra to read only 20 rows or contact only one partition. Always distinguish **candidate partitions**, **rows inspected**, and **rows returned**.

## 8. LIMIT, PER PARTITION LIMIT, and Return Order

Read at most the three newest events in one day:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

With the sample data, the result is `LOGOUT 12:00`, `PAY 11:00`, `CLICK 09:30`. `LIMIT 3` caps the **total returned rows**, without altering schema ordering or partition routing.

When reading multiple partitions, `PER PARTITION LIMIT` has a different meaning:

```sql
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 1;
```

Here each partition yields at most **one row** along its traversal order, so across two populated partitions at most two rows are returned. You can combine `PER PARTITION LIMIT 1 LIMIT 1` to enforce both a **per-partition** cap and a **total result** cap. If you need "the single newest event across all days for an account," do not assume `PER PARTITION LIMIT 1` alone solves it.

The Java driver's **page size** is a third concept: it only controls the batch size of each data fetch, not partition selection or the total query limit. `ORDER BY` + `LIMIT` + page size must be designed to match API semantics rather than treated as synonyms.

## 9. Paging by Clustering Key: Handling Duplicate Timestamps

Suppose an API displays **two events per page**, newest first. Because two events share the `09:30` timestamp, using only the timestamp as a cursor would drop or duplicate rows.

### 9.1. First Page

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

For example, fetching **three rows** illustrates the boundary clearly:

| Position | `created_at` | `event_id` | `event_type` |
| ---: | --- | --- | --- |
| 1 | 12:00 | `...0005` | `LOGOUT` |
| 2 | 11:00 | `...0004` | `PAY` |
| 3 | 09:30 | `...0003` | `CLICK` |

The next page must start **after** the last key `(09:30, ...0003)` in descending order, meaning key tuples lexicographically **smaller** than that pair.

### 9.2. Next Page Using a Tuple Boundary

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (created_at, event_id) < (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

In the chosen key order, the next rows are `VIEW 09:30 / ...0002` and `LOGIN 08:00 / ...0001`. The **tuple** comparison preserves the composite boundary:

```text
DESC:
12:00 / id-5
11:00 / id-4
09:30 / id-3   <-- cursor: last row of the first page
----------------
09:30 / id-2   <-- next page still retrieves this row
08:00 / id-1
```

If you simply wrote `created_at < '2026-11-20 09:30:00+0000'`, the `VIEW` row also at `09:30` would be skipped. If you used `<=` without checking `event_id`, `CLICK` could be repeated. Use tuple comparisons only when columns and clustering order are compatible; for mixed `ASC`/`DESC` schemas, verify comparison semantics carefully to construct an accurate cursor.

### 9.3. Keyset Cursor vs. Java Driver Paging State

| Mechanism | How it continues | What to keep in mind |
| --- | --- | --- |
| **Keyset/tuple cursor** | Next request adds a boundary from the last clustering key tuple. | Application manages traversal direction, last key, and range bounds explicitly. |
| **Driver paging state** | Driver resumes each page of the **exact same query** via protocol state. | Must keep matching query and bind values; avoid modifying, mixing, or reusing paging state arbitrarily. |
| **SQL OFFSET** | Skips N rows and fetches the next rows. | Cassandra CQL has no `LIMIT ... OFFSET ...` for arbitrary page jumps. |

Neither mechanism automatically creates an immutable snapshot if data changes between requests. New events, deletes, TTL expirations, and replication lag can alter subsequent pages. For APIs requiring high historical stability, consider pinning the query window and defining cursor rules at the business level.

## 10. Real-World Scenario: Misusing ORDER BY and How to Fix It

Suppose product requirements specify two queries:

- **A.** "For one account and one day, fetch the 50 newest events."
- **B.** "For one account and one day, fetch 50 events sorted alphabetically by `event_type`, then by `created_at`."

The `events_by_account_day` table satisfies **A** directly:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 50;
```

It cannot satisfy **B** simply by adding `ORDER BY event_type ASC, created_at DESC`, because `event_type` is not in the clustering key.

If B is an important query, a query-driven table can be designed as:

```sql
CREATE TABLE IF NOT EXISTS events_by_account_day_type (
    account_id uuid,
    event_day date,
    event_type text,
    created_at timestamp,
    event_id uuid,
    detail text,
    PRIMARY KEY ((account_id, event_day), event_type, created_at, event_id)
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    created_at DESC,
    event_id DESC
);
```

With this schema, `event_type` is the **first** clustering column, so within a known partition you can traverse by type and then by timestamp. If a new requirement asks for "newest events of **one event type**" and per-tenant daily volume is large, you might also consider putting `event_type` into the partition key of a dedicated query table. That is a schema design and write/synchronization cost decision, not an `ORDER BY` capability.

**Trade-off:** multiple read tables serve multiple query patterns efficiently, but the application must maintain denormalized records and handle dual writes, retries, TTL, repairs, backfills, and consistency appropriately. Tables do not automatically stay synchronized like relational joins.

## 11. Java Integration: Prepared and Ordered Queries

The example below uses **Apache Cassandra Java Driver 4.x**, Java 15+ (text blocks), assuming an active `CqlSession session` connected to keyspace `cassandra_order_lab`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate eventDay = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT created_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND created_at >= ?
      AND created_at < ?
    ORDER BY created_at DESC, event_id DESC
    LIMIT ?
    """);

BoundStatement statement = prepared.bind(
    accountId,
    eventDay,
    Instant.parse("2026-11-20T08:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z"),
    50
).setPageSize(20);

for (Row event : session.execute(statement)) {
    System.out.printf("%s %s %s%n",
        event.getInstant("created_at"),
        event.getUuid("event_id"),
        event.getString("event_type"));
}
```

In this example:

- `UUID` binds to `uuid`, `LocalDate` to `date`, and `Instant` to `timestamp`.
- `LIMIT 50` caps the CQL query at **at most 50 rows**; `setPageSize(20)` sets the driver fetch batch size.
- `session.execute(statement)` is a synchronous API; iterating over `ResultSet` can automatically fetch subsequent pages. To expose individual pages to clients, use the driver's paging mechanism and your API token contract.
- `created_at < 12:00` excludes `LOGOUT` at 12:00 from the result regardless of `ORDER BY DESC`.
- Because only one specific partition is queried, reading and ordering are far more predictable than queries spanning multiple days/partitions.

**Consistency:** The Java driver lets you configure read consistency level per session or statement, such as `LOCAL_ONE` or `LOCAL_QUORUM`, depending on replication and business requirements. Consistency affects how many replicas must respond and data freshness, **without changing `ORDER BY` syntax or granting permission to sort by regular columns**. When a query fails with `InvalidQuery` due to key/`ORDER BY` rules, increasing timeouts or retrying will not fix the schema. For timeout/unavailable errors, re-evaluate replica health, load, consistency, and retry policy.

## 12. Common Errors When Using ORDER BY

| Query or expectation | Issue | How to handle it |
| --- | --- | --- |
| `ORDER BY event_type ASC` | `event_type` is a regular column. | Design a read table with `event_type` in the clustering key if this is a primary need. |
| `ORDER BY event_id DESC` without fixing/referencing `created_at` | Skips the leading clustering column; cannot describe full-partition ordering. | Order by a clustering key prefix or design a different table. |
| `ORDER BY created_at DESC, event_id ASC` on a `DESC,DESC` schema | Neither the declared order nor its full inverse. | Use `DESC,DESC` or `ASC,ASC`. |
| `WHERE account_id = A ORDER BY created_at DESC` | Missing `event_day` from the composite partition key. | Supply the day/bucket or change the table design. |
| `WHERE event_day >= D ORDER BY created_at DESC` | Range on a partition key component does not replace single-partition routing. | Enumerate finite buckets or build a table suited to the range. |
| `WHERE created_at >= T AND event_id > I` | Not a valid tuple boundary across two clustering columns. | Use a prefix condition or a valid tuple comparison. |
| `ORDER BY created_at DESC LIMIT 10` guarantees scanning only 10 rows cluster-wide | `LIMIT` only caps results and does not locate partitions. | Bound partitions in `WHERE` and measure read cost. |
| `ORDER BY` automatically provides global sorting when querying multiple partitions via `IN` | Multi-partition reads can incur high merge/sort cost; do not extrapolate from single-partition ordering. | Bound fan-out, benchmark, or merge in the application/another read table. |
| Cursor stores only `created_at` | Events sharing the same timestamp may be duplicated or skipped. | Store both `created_at` and `event_id`, or use driver paging state. |
| `ALLOW FILTERING` permits `ORDER BY` on any column | `ALLOW FILTERING` only permits certain filters; it never turns regular columns into clustering keys. | Design compatible queries and schemas. |

## 13. Exercises and Answers

### Exercise 1. Fetching the Three Newest Events of the Day

**Task:** Using the sample table and data, fetch the three newest events for account A on November 20.

**Answer:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Expected result: `LOGOUT`, `PAY`, `CLICK`.

### Exercise 2. Reversing Order While Keeping Same-Timestamp Events Ordered

**Task:** Fetch all events on November 20 oldest first; at `09:30`, `VIEW` precedes `CLICK`.

**Answer:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at ASC, event_id ASC;
```

Result: `LOGIN` → `VIEW` → `CLICK` → `PAY` → `LOGOUT`.

### Exercise 3. Analyzing an Invalid Query

```sql
SELECT created_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_type ASC, created_at DESC;
```

**Question:** Why is this query invalid even though the full partition key is supplied?

**Answer:** `event_type` is a regular column, not a clustering column. Providing the full partition key selects the right partition, but it does not create an on-disk sort order by `event_type`. To make this query a primary read path, design a table with `event_type` in the clustering key, or sort a small bounded dataset in the application layer if genuinely acceptable.

### Exercise 4. Continuing After a Duplicate-Timestamp Event

**Task:** Page one of the newest-first list ends at key `(09:30, ...0003)`. Write the condition so `VIEW` at 09:30 is not skipped.

**Answer:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (created_at, event_id) < (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Next rows returned are `VIEW`, `LOGIN`. The tuple boundary excludes the last row of the previous page while keeping other rows with the same timestamp and a smaller `event_id`.

### Exercise 5. Identifying a Scope Misconception

**Scenario:** An API asks for "an account's 20 newest events over 90 days" and plans to use `event_day IN (90 days) ORDER BY created_at DESC LIMIT 20`.

**Suggested answer:** The query targets **90 composite partition keys**. Even if the syntax is accepted by the cluster, read volume and multi-partition merge/sort cost must be controlled. Consider splitting into bounded batches, benchmarking with realistic data and consistency, or creating a read table optimized for an account's latest history. `LIMIT 20` does not shrink candidate partitions down to 20.

## 14. Checklist Before Using ORDER BY in a Java API

1. Confirm the **full partition key** or a finite known list of partitions; when using `IN`, count candidate partitions.
2. Verify that columns in `ORDER BY` are **clustering columns** in their declared order.
3. Verify that sort directions match the declared directions or their **compatible exact inverse**; never mix directions arbitrarily.
4. If adding ranges in `WHERE`, verify that preceding clustering columns are properly fixed and `<`/`<=`/`>`/`>=` bounds express the exact desired interval.
5. If paginating, use a key tuple with **deterministic ordering**, including tie-breaker columns when timestamps collide; understand the difference between a business cursor and driver paging state.
6. Control `LIMIT`, `PER PARTITION LIMIT`, page size, partition size, and concurrent requests; monitor p95/p99 latency, tombstones, and compaction/repair impact.
7. Choose replication and consistency per read/write SLAs; handle timeouts and invalid queries separately instead of retrying all errors identically.

**Remember:** Cassandra's `ORDER BY` is not a general-purpose sorter over any column on any row set. It leverages the **clustering order already built into the table**. When `WHERE` targets the right partition and clustering predicates are valid, reading newest/oldest rows and paginating become straightforward. If a different sort order is needed as a primary read path, design a table or query model tailored to that order.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT and ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY and CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
