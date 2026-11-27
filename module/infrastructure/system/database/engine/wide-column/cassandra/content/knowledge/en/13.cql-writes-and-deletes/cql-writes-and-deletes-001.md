# INSERT, UPDATE, and Primary-Key Write Semantics in Apache Cassandra

In Apache Cassandra, both `INSERT` and `UPDATE` are **upsert** operations: a write statement can create new data or replace the values of the specified columns. Cassandra does not use the relational database concept where "`INSERT` must fail with a duplicate key error if the record already exists." What determines where data is written is the table's **primary key**, specifically the **partition key** and **clustering columns**.

This lesson belongs to the **CQL Writes and Deletes** chapter. After completing it, you should be able to:

- Identify which partition and row a write statement affects based on the primary key.
- Write `INSERT` and `UPDATE` statements properly, understanding both creation and overwrite cases.
- Distinguish between omitted columns, assigned column values, and columns assigned `NULL`.
- Explain the outcome when multiple competing writes target the same data cell, when TTL is used, and when `IF` conditions are applied.
- Choose a write approach aligned with query-driven table modeling, replication, and consistency levels.

## 1. The primary key determines where a write goes

Suppose a retail application needs to look up orders by customer and month. A query-driven table can be created as follows (assuming the `shop` keyspace already exists):

```sql
CREATE TABLE shop.orders_by_customer (
    customer_id   uuid,
    order_month   text,
    order_id      uuid,
    ordered_at    timestamp,
    status        text,
    total         decimal,
    delivery_note text,
    PRIMARY KEY ((customer_id, order_month), order_id)
);
```

Reading the key definition from the inside out:

| Component | In the example | Role |
| --- | --- | --- |
| Partition key | `(customer_id, order_month)` | Identifies the logical partition; Cassandra uses the partition key's token to distribute data to replicas. |
| Clustering column | `order_id` | Distinguishes rows within the same partition and determines the sort order of rows inside the partition. |
| Full primary key | `(customer_id, order_month, order_id)` | Uniquely identifies **a single row** in the table. |
| Regular column | `ordered_at`, `status`, `total`, `delivery_note` | Stores data that can be written or updated without changing row identity. |

For example, two orders from the same customer in `2026-11` will reside in the same partition if their `order_id` values differ. Two writes with **all three key values identical** will target the exact same row.

```text
Partition key: (customer A, "2026-11")
  |
  +-- Clustering key: order_id X --> status, total, ordered_at, ...
  |
  +-- Clustering key: order_id Y --> status, total, ordered_at, ...

Partition key: (customer A, "2026-12")
  |
  +-- Clustering key: order_id Z --> status, total, ordered_at, ...
```

This is the link between CQL and distributed wide-column architecture: the primary key is not merely for uniqueness enforcement; it also controls how data is placed and accessed. Because `order_month` is part of the partition key, it helps partition data by time. Choosing keys must start from the queries the application needs to serve; Cassandra does not automatically generate a hidden row ID to replace the defined primary key.

## 2. INSERT: writing a row by full primary key

Common syntax:

```sql
INSERT INTO keyspace_name.table_name (pk_column, ..., regular_column, ...)
VALUES (pk_value, ..., column_value, ...);
```

With the example table:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id,
    ordered_at, status, total, delivery_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    '2026-11-21 09:30:00+0700',
    'CREATED',
    1200000.00,
    'Deliver during business hours'
);
```

This statement writes the row with the full key:

```text
(customer_id = 11111111-1111-4111-8111-111111111111,
 order_month = '2026-11',
 order_id = 22222222-2222-4222-8222-222222222222)
```

To `INSERT` a regular row, all primary key components must be provided. Primary key values cannot be `NULL`. Regular data columns can be omitted.

### Re-INSERTing the same key does not cause a duplicate key error

Suppose after the first statement, the system executes:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'PAID'
);
```

Because the **full primary key is identical**, Cassandra writes to the existing row. If the second write has a newer timestamp, `status` becomes `PAID`. The `total`, `ordered_at`, and `delivery_note` columns are not mentioned in the second write, so they retain their existing values. No second row is created, and no "duplicate primary key" error is raised automatically.

Conversely, if you replace `order_id` with a different UUID while keeping the same partition key, Cassandra writes a **different row within the same partition**.

> **Core rule:** In Cassandra, `INSERT` means "write these values at this key," not by default "only insert if the key does not exist." When you genuinely need to create only if absent, use `IF NOT EXISTS` (section 6).

## 3. UPDATE: changing column values without changing the primary key

Syntax:

```sql
UPDATE keyspace_name.table_name
SET column_name = value, ...
WHERE partition_key_component = value
  AND clustering_key_component = value;
```

Example updating the status and delivery note of a single specific order:

```sql
UPDATE shop.orders_by_customer
SET status = 'SHIPPING',
    delivery_note = 'Call before delivery'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

In this table without `static` columns, updating regular columns requires specifying all primary key components in `WHERE`. This is not like an arbitrary `UPDATE ... WHERE status = 'CREATED'` in relational SQL: `status` is a regular column and cannot be used to locate rows for a write. When updates by other criteria are needed, the application must already know the keys of the target rows or design a table tailored to that query.

The `UPDATE` above **does not modify** `total` or `ordered_at`. If the row does not exist yet, a regular `UPDATE` can still **create a new row** at the specified primary key. For example:

```sql
UPDATE shop.orders_by_customer
SET status = 'CREATED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;
```

After this statement, the row whose `order_id` ends in `3333...` can appear with `status = 'CREATED'`, while regular columns that have never been written will read back as `null`.

### You cannot UPDATE a primary key component

The following operations are semantically invalid:

```sql
-- INVALID: primary key columns cannot appear in SET.
UPDATE shop.orders_by_customer
SET order_id = 44444444-4444-4444-8444-444444444444
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;

-- INVALID: missing clustering key when updating a regular column.
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Changing `order_id` or moving an order to a different `order_month` actually changes the row's identity: you must write the row under the new key and handle deleting the data under the old key according to your business workflow. Cassandra does not provide an "in-place primary key rename" statement. For tables with a `static column`, the `WHERE` rule for updating only the `static` column has an exception; the examples in this lesson consider only regular columns.

## 4. Why are both INSERT and UPDATE upserts?

Cassandra's storage model treats column values as cells attached to a key. A normal write sends a mutation to the replicas responsible for the partition, rather than forcing a prior read to decide whether to perform an `INSERT` or an `UPDATE`.

Suppose a row currently holds the following values:

| Key (abbreviated) | `status` | `total` | `delivery_note` |
| --- | --- | --- | --- |
| `customer A / 2026-11 / order X` | `CREATED` | `1200000.00` | `Deliver during business hours` |

After executing `UPDATE ... SET status = 'PAID' WHERE <exact full primary key>`, we have:

| Key (abbreviated) | `status` | `total` | `delivery_note` |
| --- | --- | --- | --- |
| `customer A / 2026-11 / order X` | `PAID` | `1200000.00` | `Deliver during business hours` |

The same happens with an `INSERT` that only supplies the key and `status`. Values not included in the mutation are not overwritten with `null` simply because they are absent from the statement.

Distinguish three cases:

| Action | Meaning for a regular column |
| --- | --- |
| Omit column in `INSERT` or `UPDATE` | Does not rewrite that column; its previous value is unchanged by this statement. |
| Assign `status = 'PAID'` | Writes the new value to the `status` cell for the corresponding key. |
| Assign `status = NULL` | Creates a deletion marker (*tombstone*) for that column's data; this does not mean "skip updating." |

Example:

```sql
UPDATE shop.orders_by_customer
SET delivery_note = NULL
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Once the deletion takes effect and is visible at the active read consistency level, `delivery_note` reads back as `null`. Cassandra must retain the tombstone for a period of time so that replicas that missed the delete do not resurrect old data; tombstone management, compaction, and repair are covered in detail in dedicated lessons.

When using the Java Driver with prepared statements, **not binding** a parameter or using the **UNSET** state leaves the column untouched, whereas binding **NULL** deletes the column. Applications should clearly distinguish between "not sending a new value" and "intending to delete the current value."

## 5. Concurrent writes: timestamps and last-write-wins

Because Cassandra is a distributed database, multiple replicas or clients can process competing writes. For regular cells, Cassandra reconciles versions by **cell timestamp** (*timestamp-based last-write-wins*), rather than simply by the order in which a user perceives statements arriving at the server.

For example, two clients concurrently write `status` for the same row:

```text
Client A: status = 'PAID'      @timestamp = 1000000
Client B: status = 'CANCELLED' @timestamp = 2000000

When versions are reconciled:
status = 'CANCELLED' (higher timestamp)
```

The timestamps above merely illustrate comparison order. Cassandra write timestamps have **microsecond** resolution since the Unix epoch; the higher timestamp wins for the same cell. If timestamps are equal, Cassandra applies deterministic tie-breaking rules, so you should never rely on identical timestamps to decide business values.

Key implications to keep in mind:

- Different columns can have different timestamps. Updating `status` does not necessarily overwrite `total` in the same row.
- A request that arrives later in wall-clock order but carries a higher timestamp can still win; conversely, a newly arrived write with an older timestamp may not change the value read back.
- Clock skew between clients/nodes, especially when supplying custom timestamps, can produce unexpected results. Only use custom timestamps when you thoroughly understand clock synchronization and conflict resolution.
- Default upserts do not verify "the previous state must be X." If multiple actors update the same order concurrently, business-level lost updates can occur. Use `IF` conditions when controlled state transitions are required.

CQL supports `USING TIMESTAMP <microseconds_since_epoch>` on regular write statements, though in typical applications it is best to let the configured system/driver timestamp generator handle it. Do not apply manual timestamps across every operation type—for example, conditional writes or counters have specific restrictions.

## 6. Conditional writes with IF: when upsert is not enough

To require "create only if this key does not exist," use `IF NOT EXISTS`:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'CREATED',
    1200000.00
)
IF NOT EXISTS;
```

To require "update only if the row currently exists," use `IF EXISTS`:

```sql
UPDATE shop.orders_by_customer
SET delivery_note = 'Deliver after 6 PM'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF EXISTS;
```

Conditions can also inspect existing column values—for example, allowing a transition only from `CREATED` to `PAID`:

```sql
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF status = 'CREATED';
```

`IF` statements belong to **lightweight transactions (LWT)** and use a consensus protocol to enforce conditions under concurrent client contention. The CQL result returns `applied = true` if the condition is met, or `applied = false` if not; when the condition fails, the current values may also be returned so the application can decide the next step.

LWT incurs higher coordination overhead and latency than regular upserts. Use it when you need to guarantee creation uniqueness or conditional state transitions; do not turn every write into an LWT merely to mimic relational SQL.

## 7. TTL: written values can expire automatically

Regular `INSERT` and `UPDATE` statements support a time to live (*TTL*) specified in seconds:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    55555555-5555-4555-8555-555555555555,
    'TEMPORARY'
)
USING TTL 3600;

UPDATE shop.orders_by_customer USING TTL 1800
SET delivery_note = 'Temporary note'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

In this example, `status` is written with a one-hour TTL on a temporary row; `delivery_note` is written with a 30-minute TTL on an existing row. TTL applies primarily to **the written column values**; primary key parts do not independently carry a TTL like regular columns. Rewriting a column with a new TTL can update when that value expires. Once the TTL expires, the value is no longer returned on reads, and Cassandra handles expiration via the tombstone mechanism.

You can inspect the write timestamp and remaining TTL:

```sql
SELECT status, WRITETIME(status), TTL(status)
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 55555555-5555-4555-8555-555555555555;
```

`WRITETIME(status)` returns the cell's write timestamp; `TTL(status)` reports the remaining seconds if the cell has a TTL, and typically returns `null` when no TTL is set. Do not think of TTL as an instant physical deletion of rows from all storage files.

## 8. Consistency level does not change primary key semantics

Replication enables Cassandra to keep copies of data across multiple nodes; the **write consistency level** defines how many replicas must acknowledge a write for it to be considered successful from the client's perspective. For instance, with a replication factor of 3, `QUORUM` typically requires successful acknowledgments from 2 replicas within the scope of that consistency level.

In `cqlsh`, you can set the consistency level before running write statements:

```sql
CONSISTENCY QUORUM;
```

However, changing from `ONE` to `QUORUM` does not alter the full primary key, does not cause `INSERT` to throw a duplicate-key error, and does not turn `UPDATE` into an atomic conditional check-and-set operation. Consistency level governs replica acknowledgment and read/write visibility; value conflicts still depend on timestamps, and race-prone conditions require LWT.

In production systems, when a client experiences a timeout, you cannot conclude with certainty from the timeout alone whether the mutation was persisted. Retrying an idempotent upsert with the same key and values is generally safer than retrying an additive operation, though timestamps, TTL, LWT, and business requirements still need to be evaluated for safe retry design.

## 9. Hands-on verification for each scenario

After creating the table and running the first `INSERT` from section 2, execute the following steps in order:

**Step 1 — Read the row by exact primary key**

```sql
SELECT customer_id, order_month, order_id,
       status, total, delivery_note
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Expected: one row with `status = 'CREATED'`, `total = 1200000.00`, and the initial delivery note.

**Step 2 — Upsert a single column with INSERT**

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'PAID'
);
```

Re-run the `SELECT` from step 1: assuming no competing writes and no unusual timestamps, `status` is `PAID` while `total` and `delivery_note` remain unchanged.

**Step 3 — UPDATE a non-existent key**

```sql
UPDATE shop.orders_by_customer
SET status = 'CREATED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;

SELECT order_id, status, total
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;
```

Expected: a new row exists with `status = 'CREATED'` and `total = null`.

**Step 4 — Check a conditional state transition**

```sql
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF status = 'CREATED';
```

Because step 2 already changed this row's `status` to `PAID`, the condition `status = 'CREATED'` is false, so the result will be `applied = false`. Instead of silently updating, the application receives a signal that the state is no longer as expected.

### Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| Duplicate-key `INSERT` must fail as in relational SQL. | By default `INSERT` is an upsert; use `IF NOT EXISTS` to check for existence. |
| `UPDATE` on a missing row does nothing. | A regular `UPDATE` can create a new row at the full primary key. |
| Not passing a column sets it to `NULL`. | Omitting a column skips writing it; passing `NULL` can create a tombstone. |
| Partition keys can be modified via `UPDATE SET`. | Changing a key means a different row identity and must be handled by writing to the new key. |
| The client that sends a statement later always wins. | Cassandra compares per-cell timestamps, not just request arrival order. |
| `QUORUM` guarantees only one client can change state. | `QUORUM` governs replica acknowledgments; use LWT for concurrent conditional checks. |

## 10. Connection to Java application design

When a Java application uses prepared statements to write to Cassandra, bind the complete full primary key in the parameters of `INSERT`/`UPDATE`. Clearly distinguish which APIs have **upsert** semantics and which require **create-if-absent** or **compare-and-set**. For partial updates, separate fields omitted by the client from fields explicitly sent as `null`; otherwise, a request updating `status` can easily delete `delivery_note` by mistake.

For retries and network error handling, using a deterministic key for the same order ensures repeated writes target the same row. If you need an operation to "transition from `CREATED` to `PAID` strictly once," implement it using LWT and inspect the `applied` result rather than doing a read followed by an unconditional `UPDATE`: between the read and the write, another client can still change the state.

**Takeaway:** in Cassandra, the primary key decides *where to write*, the column list decides *which values to write*, the timestamp decides *which version wins*, TTL decides *how long a value lives*, and `IF` decides *whether the write is permitted when current state differs from expectations*. Mastering these five elements forms the foundation for understanding deletes, tombstones, compaction, repair, and consistency in the following lessons.
