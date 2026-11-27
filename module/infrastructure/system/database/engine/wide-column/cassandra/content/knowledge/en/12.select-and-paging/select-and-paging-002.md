# Conditions on Partition Keys and Clustering Columns in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **partition keys**, **clustering columns**, and **primary keys** in an Apache Cassandra wide-column table.
2. Write `WHERE` conditions to target a single partition or a well-defined set of partitions, avoiding unnecessary data scans.
3. Use equality, `IN`, and range conditions (`>`, `>=`, `<`, `<=`) on clustering columns in the proper order.
4. Understand the limitations of conditions on composite partition keys, multiple clustering columns, tuples, and `token()`.
5. Explain why a query is rejected or exhibits unstable latency, and choose a table design that fits Java application requirements.

This lesson is part of the **SELECT and Paging** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module: covering distributed architecture, the wide-column model, partition keys, query-driven table design, read/write consistency, CQL, and Java connectivity. The focus here is the **row-selection rules in `WHERE`**, not merely memorizing a few statement templates.

## 1. Two Key Layers That Govern Reads

A Cassandra table's `PRIMARY KEY` consists of:

- **Partition key**: one or more columns that together identify a partition. Cassandra hashes the **entire partition key** into a token to locate the replicas storing that partition.
- **Clustering columns**: the columns following the partition key; they determine the sort order and uniqueness of rows **within the same partition**.

Three example declarations:

| Definition | Partition key | Clustering columns |
| --- | --- | --- |
| `PRIMARY KEY (account_id)` | `account_id` | None |
| `PRIMARY KEY (account_id, event_time)` | `account_id` | `event_time` |
| `PRIMARY KEY ((account_id, event_day), event_time, event_id)` | `(account_id, event_day)` | `event_time`, then `event_id` |

In the third row, the nested parentheses are critical. Cassandra **hashes the entire `(account_id, event_day)` pair** to locate the partition. Values with the same `account_id` but different `event_day` belong to different partitions and may be served by different replica sets. This is not an ordered index by `account_id` and then `event_day` as commonly pictured for a SQL B-tree.

Model diagram:

```text
PRIMARY KEY ((account_id, event_day), event_time, event_id)
              \__________________/  \________/  \______/
                partition key        clustering columns

(account A, day 20)  ──> partition P1 ──> rows ordered by event_time, event_id
(account A, day 21)  ──> partition P2 ──> rows ordered by event_time, event_id
(account B, day 20)  ──> partition P3 ──> rows ordered by event_time, event_id
```

**Direct implication:** a query that constrains the full partition key typically has a predictable read scope. Omitting one component of a composite partition key does not allow Cassandra to "traverse a branch" using the remaining component.

## 2. Building a Query-Driven Practice Table

Suppose an application needs an activity history screen for **one account on one day**, showing the newest events first and supporting time-range filtering.

Run the following statements in `cqlsh` in a test environment:

```sql
-- Single-replica configuration is for single-node Cassandra lab use only.
CREATE KEYSPACE IF NOT EXISTS cql_where_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cql_where_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    details text,
    PRIMARY KEY ((account_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 09:15:00+0000',
     00000000-0000-4000-8000-000000000001,
     'LOGIN', 'Logged in on web');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 11:45:00+0000',
     00000000-0000-4000-8000-000000000002,
     'VIEW', 'Opened order page');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 11:45:00+0000',
     00000000-0000-4000-8000-000000000003,
     'CLICK', 'Selected order details');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21', '2026-11-21 08:00:00+0000',
     00000000-0000-4000-8000-000000000004,
     'LOGIN', 'Logged in on new day');
```

**Design explanation:**

- `account_id` and `event_day` together form the partition key: all events for **one account on one day** reside in one partition.
- `event_time` is the first clustering column, enabling range queries by time and newest-first reads via `DESC`.
- `event_id` is the second clustering column, ensuring two events with the same `event_time` can still exist as two distinct rows.
- `event_type` and `details` are regular data columns; they **do not automatically provide an efficient access path** in `WHERE`.
- Each complete tuple `(account_id, event_day, event_time, event_id)` identifies one row. Writing with the same primary key is an upsert, not a duplicate row.

In a multi-node system, configure replication per datacenter (typically `NetworkTopologyStrategy`) and choose consistency according to requirements. Those choices affect durability and freshness of read data, but **do not change CQL's `WHERE` rules**.

## 3. Conditions on the Partition Key

### 3.1. Equality (=): Identifying Exactly One Partition

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

This is the intended read path for the table:

1. The coordinator receives `account_id` and `event_day`.
2. Cassandra computes the token from the **entire partition key pair**, identifying the responsible replicas.
3. The read scope is confined to the target partition; rows are scanned in clustering order.

From the sample data, the result contains **three events from November 20**, ordered by default by `event_time DESC`, then `event_id DESC`. You do not need to include the partition key in the `SELECT` column list in order to filter on it in `WHERE`.

If only `account_id` is known without `event_day`:

```sql
-- Does not satisfy the full partition key of the example table.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Do not expect Cassandra to discover every `event_day` for an account automatically. On the current table, this query lacks a complete partition locator and is normally rejected unless filtering is allowed. If the application frequently needs "an account's entire history," it needs a dedicated read pattern: for instance, the service querying known date buckets sequentially or using another table tailored to the required time window.

### 3.2. IN: Listing a Set of Known Partitions

`IN` specifies a discrete set of values and is treated as a form of equality condition for key selection. With a **composite partition key**, `IN` can be applied to the last component after fixing the preceding components:

```sql
SELECT event_day, event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

This query may access **two distinct partitions**. On the sample data it returns three events from day 20 and one event from day 21; do not assume that events across multiple partitions are **globally** ordered by time.

Comparison:

| Condition pattern | Expected read scope |
| --- | --- |
| `account_id = A AND event_day = D` | One partition identified by `(A, D)`. |
| `account_id = A AND event_day IN (D1, D2)` | Two specific partitions. |
| `account_id = A` | Incomplete composite partition key. |
| `event_day = D` | Omits the leading component of the composite partition key. |
| `account_id = A AND event_day >= D` | Direct inequality on partition key is not supported this way. |

**Cost of `IN`:** a large list of values can trigger many reads across different partitions, increasing latency or making it unpredictable. Keep the element count small, observe real query behavior, and consider splitting into bounded requests rather than treating `IN` as a substitute for table design.

### 3.3. Why Can't Range Operators Be Used Directly on the Partition Key?

```sql
-- Wrong access pattern: event_day is part of the partition key.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20'
  AND event_day < '2026-11-23';
```

Even though `date` has chronological ordering, Cassandra partitions by the **hashed token of the full partition key**, so partitions with the same `account_id` are not stored adjacent to each other by `event_day`. Consequently, `>=`/`<` comparisons directly on a partition key component cannot form a contiguous lookup slice as they do on a clustering column.

To query a few known days, enumerate partitions via `IN` or issue separate queries. If the primary requirement is querying long, continuously varying date ranges, consider an additional read table with a partition bucket and time-based clustering sized to your traffic and partition limits.

## 4. Conditions on Clustering Columns

Once the partition is located, Cassandra reads rows in the order declared in `PRIMARY KEY`. In the example table, the clustering order is:

```text
Partition (account_id, event_day)
        |
        +-- event_time DESC
                 |
                 +-- event_id DESC
```

Conditions on clustering columns must select a contiguous slice in this order, or point sets supported by CQL. A common mental rule is: **preceding columns use equality conditions, followed by a column with a range condition**.

### 4.1. Equality on the First Clustering Column

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000';
```

The query returns **two rows** because `event_time` is identical while `event_id` differs. This shows that equality on **one clustering column** does not necessarily identify a single row; only the **full primary key** guarantees uniqueness.

### 4.2. Locating a Single Row by the Full Primary Key

```sql
SELECT event_type, details
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

This query matches only the single row with `event_type = 'VIEW'`. Fetching one row by its full primary key is a very specific, predictable query pattern.

### 4.3. Ranges on a Clustering Column

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 09:00:00+0000'
  AND event_time < '2026-11-20 12:00:00+0000';
```

Using **`>=` on the lower bound and `<` on the upper bound** creates the half-open interval `[09:00, 12:00)`, avoiding double-counting events right on the boundary into the next window. In the sample data, all three events from day 20 fall within this range.

Standard comparison operators on clustering columns are `=`, `>`, `>=`, `<`, and `<=`. CQL does not require SQL's `BETWEEN` syntax here; write two range conditions to express both bounds clearly.

Because `event_time` is declared `DESC`, newer rows appear first when `ORDER BY` is omitted. The comparison `event_time >= ...` still compares **timestamp values**, rather than flipping the inequality sign because of descending storage order.

### 4.4. The Second Clustering Column Can Only Be Constrained When Preceding Ones Are Fixed

Once both the partition key and `event_time` are fixed with equality, you can filter on `event_id`:

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

With the sample data, this query finds the row whose `event_id` ends in `...0003`. The filter structure is valid because **all clustering columns preceding `event_id`** are fixed.

Two common invalid patterns:

```sql
-- Wrong: skips event_time and filters directly on event_id.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id = 00000000-0000-4000-8000-000000000002;

-- Wrong: places a range on event_time and then adds a separate condition
-- on a subsequent clustering column, which does not guarantee a contiguous
-- slice along the clustering key.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

In the second query, `event_id` comes after `event_time`. Once `event_time` is constrained by a range, a fixed `event_id` does not form a single contiguous segment across the entire `event_time` range. Conditions like this are normally rejected by CQL in standard queries; even if `ALLOW FILTERING` permits execution, it does not create a new index.

### 4.5. IN on the Last Column of the Primary Key

For the example table, `event_id` is the **final column of the primary key**. After fixing the preceding columns, you can select multiple `event_id` values:

```sql
SELECT event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id IN (
      00000000-0000-4000-8000-000000000002,
      00000000-0000-4000-8000-000000000003
  );
```

`IN` is not a time-range operator, nor can it be placed arbitrarily on any clustering column. Under standard CQL rules, `IN` is allowed on the **last component of the partition key** or the **last column of the entire primary key** (taking preceding equality conditions into account).

### 4.6. Tuple Conditions Across Multiple Clustering Columns

CQL supports grouping consecutive clustering columns into a tuple:

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (event_time, event_id) > (
      '2026-11-20 11:45:00+0000',
      00000000-0000-4000-8000-000000000002
  );
```

The condition `(event_time, event_id) > (...)` is a **lexicographical tuple comparison in key order**, quite different from `event_time > ... AND event_id > ...`. This relational form is useful when you need a boundary spanning multiple clustering columns, provided the tuple follows exact column order and you verify comparator/clustering-order semantics when using it as an application cursor.

Another CQL-supported variant is `(event_time, event_id) IN ((t1, id1), (t2, id2))` when selecting specific clustering key tuples within the same partition.

## 5. ORDER BY and Clustering Order

Because the table was created with:

```sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
```

You can request the default order or its supported exact reverse:

```sql
-- Newest events first: matches the default ordering.
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;

-- Reversed order: oldest first.
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_time ASC, event_id ASC
LIMIT 20;
```

`ORDER BY` in Cassandra is **not an arbitrary sort**. It relies on clustering columns, their declared order, and valid reversal directions. You cannot replace it with `ORDER BY event_type` because `event_type` is not in the clustering key. If a primary query needs "events by type and then time," that is a different access pattern, typically requiring a read table organized under different keys.

**Note on `IN` over partition keys:** when a query reads multiple partitions, do not assume a global chronological order as when reading a single partition. If the application must merge events from multiple days, design bounded merging/sorting in the application tier or a dedicated data model.

## 6. Conditions on Regular Columns and ALLOW FILTERING

`event_type` is a regular column, so this query has no key-based access path on the created table:

```sql
-- Invalid with the current schema for normal queries.
SELECT event_time, event_type
FROM events_by_account_day
WHERE event_type = 'LOGIN';
```

Even when the partition is already specified:

```sql
-- May force Cassandra to filter rows within the partition.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'LOGIN'
ALLOW FILTERING;
```

`ALLOW FILTERING` enables execution of certain queries that must scan and filter many rows; **it does not create an index and does not guarantee fast execution**. In the second query, even though the partition is known, Cassandra may still have to inspect many events in the partition to find a `LOGIN`. Without the partition key, the risk escalates to scanning across a vast number of partitions. Cost depends on row count, tombstones, data distribution, topology, and consistency.

When querying by `event_type` is a core requirement, consider:

- **Designing an additional query-specific table**, such as one whose partition key includes `account_id`, `event_day`, and `event_type`, clustered by `event_time`.
- **An appropriate index** for your Cassandra version and data distribution, such as Storage-Attached Index (SAI) where supported. Indexes do not eliminate the need to evaluate cardinality, fan-out, and query stability.
- **Filtering after reading a small bounded set**, if the partition is genuinely small and controlled; measure cost on realistic data.

## 7. Special Exception: Token Ranges Are Not Business Key Ranges

For partition keys, direct inequality operators do not define a contiguous range of business partitions. Cassandra supports one specialized form:

```sql
-- Example token range expression, typically used by data-scanning tools.
-- The two bind markers are tokens supplied by the application/tool.
SELECT account_id, event_day, event_time
FROM events_by_account_day
WHERE token(account_id, event_day) > ?
  AND token(account_id, event_day) <= ?;
```

Here `token(account_id, event_day)` takes the **exact list of partition key components in exact order**. A token range describes a slice of the data distribution ring, not "days from date A to date B." Results can span many accounts, many days, and multiple nodes. This is primarily a tool for controlled scanning, migration, or verification jobs—not a way to build a single-customer history screen.

When you need to read a multi-day span for the same account, prefer an appropriate data model and bucketing scheme rather than trying to use `token()` to mimic date comparisons.

## 8. Quick Check of Common WHERE Clauses

Assume all queries below run on `events_by_account_day` with no additional indexes:

| `WHERE` condition | Assessment | Reason |
| --- | --- | --- |
| `account_id = A AND event_day = D` | Valid, single partition | Provides full composite partition key. |
| `account_id = A AND event_day IN (D1, D2)` | Valid, two partitions | `IN` on the last component of the partition key. |
| `account_id = A` | Missing direct read path | Missing `event_day`; partition cannot be located. |
| `event_day = D` | Missing direct read path | Missing preceding `account_id`. |
| `account_id = A AND event_day > D` | Invalid under standard key rules | Cannot range-compare partition keys like clustering keys. |
| `account_id = A AND event_day = D AND event_time >= T1 AND event_time < T2` | Valid | Range on the first clustering column. |
| `account_id = A AND event_day = D AND event_time = T AND event_id = I` | Valid | Specifies the complete primary key. |
| `account_id = A AND event_day = D AND event_id = I` | Invalid under standard read path | Skips the preceding clustering column `event_time`. |
| `account_id = A AND event_day = D AND event_time = T AND event_id IN (I1, I2)` | Valid | `IN` on the last clustering column after equality conditions. |
| `event_type = 'LOGIN'` | No key-based read path | Unindexed regular column. |

"Invalid" in this table means **not accepted by CQL along the standard key-lookup path of this schema**; some cases may have alternative syntax with `ALLOW FILTERING` or secondary indexes, which does not automatically make them suitable for production use.

## 9. Java Application: Binding Partition Keys and Clustering Ranges

In Java driver 4.x, use prepared statements to pass key values, preserving query logic and avoiding string concatenation with user input:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// session is already connected to keyspace cql_where_lab.
PreparedStatement prepared = session.prepare("""
    SELECT event_time, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND event_time >= ?
      AND event_time < ?
    """);

BoundStatement statement = prepared.bind(
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    LocalDate.parse("2026-11-20"),
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z")
).setPageSize(50);

for (Row row : session.execute(statement)) {
    Instant eventTime = row.getInstant("event_time");
    UUID eventId = row.getUuid("event_id");
    String eventType = row.getString("event_type");
    System.out.printf("%s %s %s%n", eventTime, eventId, eventType);
}
```

The example uses Java **text blocks** (Java 15+). In projects on older Java versions, replace the text block with a regular string. `setPageSize(50)` sets the driver fetch page size, **not a limit on total returned events**; to cap total rows, add `LIMIT` in CQL. For queries in distributed environments, set an appropriate consistency level on the statement or session per application policy.

When implementing cursor pagination, preserve the input values identifying the query (`account_id`, `event_day`, time range) alongside the driver's paging state. Reading multiple days with `IN` requires handling cross-partition ordering and multi-partition read cost separately.

## 10. Practice Exercises and Answers

**Exercise 1.** Retrieve all events for the sample account on November 20, 2026, from 10:00 up to (not including) 12:00 UTC.

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 10:00:00+0000'
  AND event_time < '2026-11-20 12:00:00+0000';
```

*Expected:* two rows at 11:45 with different `event_id` values.

**Exercise 2.** Retrieve the exact `CLICK` event from the sample data using the full key.

```sql
SELECT event_type, details
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

*Expected:* exactly one `CLICK` row.

**Exercise 3.** Explain why the query below cannot be used directly even though `event_day` has type `date`:

```sql
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20';
```

*Suggested answer:* `event_day` is part of the **partition key**, so it does not provide chronological ordering across partitions. If you genuinely need two specific days, list them with `IN`; if long-range queries are a primary read path, design an additional tailored table.

**Exercise 4.** Why can't you add `LIMIT 20` to "fix" `WHERE event_type = 'LOGIN'`? Because `LIMIT` caps the number of returned rows; it does not create a partition key, clustering key, or index for `event_type`. Cassandra still lacks an efficient access path.

## 11. Checklist When Designing SELECT Queries

Before putting a `SELECT` statement into your application's main code path:

1. Do you have the **full partition key** or only part of it? Can you describe exactly which partitions will be read?
2. If using `IN`, is the resulting number of partitions small and bounded?
3. If using clustering conditions, are columns specified in **exact primary key order**? Are columns before the range column fixed?
4. If sorting is required, does `ORDER BY` match the clustering order (or its supported reverse)?
5. Does the query require filtering on regular columns, scanning, or `ALLOW FILTERING`? If so, should you redesign the read table, narrow the scope, or add an index?
6. Is partition size controlled with reasonable bucketing? In distributed operations, do consistency levels and retry policies affect API latency or data freshness?
7. When using the Java driver, are key types bound properly, fetch size/`LIMIT` set appropriately, and pagination handled consistently with the query?

Core takeaway: **the partition key determines where Cassandra looks for data; clustering columns determine how Cassandra selects and orders rows within that partition**. A good `WHERE` clause must align with both key layers. If query requirements change, it is usually better to adapt or add a query-specific table model rather than forcing a single table to serve every access pattern.

## References

- [Apache Cassandra Documentation — Data Manipulation: SELECT and WHERE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Definition: Primary Key and Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — RDBMS Design and Query-driven Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/data-modeling_rdbms.html)
