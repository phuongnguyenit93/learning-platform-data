# Writing Static Column Values in Apache Cassandra

In an Apache Cassandra table where multiple rows belong to the same partition, all rows sometimes need to share a piece of information: the monthly billing currency, a group classification label, or a partition-wide configuration. A **static column** is a mechanism for storing a value **at the partition level** instead of repeating it as independent values in every clustering row.

This lesson belongs to the **CQL Writes and Deletes** chapter in module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, focusing on declaring, writing, reading, and deleting static columns with CQL while explaining the effects of partition keys, replication, consistency levels, TTL, and concurrent updates. The Java Driver examples at the end help turn these concepts into safe operations in Java applications.

After this lesson, you should be able to:

- Distinguish **partition key**, **clustering column**, **regular column**, and **static column**.
- Accurately predict which rows see a static value when written via `INSERT` or `UPDATE`.
- Write a mutation **with only the partition key** when updating only static columns.
- Understand what happens when writing a static value before a partition has any clustering rows.
- Distinguish deleting a single row, deleting a static column, and deleting an entire partition.
- Apply best practices for TTL, timestamps, LWT, and the Java Driver with partition-level data.

## 1. Why use a static column?

Suppose a retail application needs to read **a customer's orders by month**. Each order has its own status, yet all orders for the same customer in a given month share a reporting currency and a reconciliation note.

If `billing_currency` were stored on each order row, the same value would be repeated many times. Whenever the monthly reporting currency changed, the application would have to find and update every order row in the partition. A **static column** solves the case where data genuinely belongs to the **partition**.

```text
Partition: (customer A, 2026-11)
|
+-- Static: billing_currency = "VND"
|           month_note = "Reconciling"
|
+-- Row order X: status = CREATED, total = 250000
+-- Row order Y: status = PAID,    total = 750000

Partition: (customer A, 2026-12)
|
+-- Static: billing_currency = "USD"
|           month_note = "December orders"
|
+-- Row order Z: status = CREATED, total = 40
```

**One static value** is attached to each logical partition, even though multiple rows inside the partition observe that value on reads. A static column is **not** a global column shared across the entire table.

## 2. Declaring a table with static columns

Assume the `shop` keyspace already exists. Create a table modeled for the query "list a customer's orders by month":

```sql
CREATE TABLE shop.orders_by_customer_month (
    customer_id      uuid,
    order_month      text,
    order_id         uuid,
    ordered_at       timestamp,
    order_status     text,
    total            decimal,
    billing_currency text static,
    month_note       text static,
    month_budget     decimal static,
    PRIMARY KEY ((customer_id, order_month), order_id)
);
```

Schema breakdown:

| Component | Columns | Meaning |
| --- | --- | --- |
| **Composite partition key** | `(customer_id, order_month)` | Identifies the partition; replicas responsible for the partition are chosen using the partition key's token. |
| **Clustering column** | `order_id` | Distinguishes order rows within the same partition. |
| **Regular columns** | `ordered_at`, `order_status`, `total` | Each order row has its own values. |
| **Static columns** | `billing_currency`, `month_note`, `month_budget` | Each partition has shared values independent of `order_id`. |

Two orders with the same `customer_id` and `order_month` but different `order_id` values are **two distinct rows** sharing static values. Two orders with different `order_month` values belong to **two different partitions**, so static values are **not shared** between them.

### Declaration rules

- Only declare `static` on **non-primary-key columns**.
- The table must have **at least one clustering column** to distinguish partition-level data from row-level data. A table with only a partition key, such as `PRIMARY KEY (customer_id)` and no clustering columns, cannot use static columns in this manner.
- Static columns can store scalar types like `text`, `decimal`, and many other CQL types subject to schema constraints; this example uses scalars to keep write semantics clear.
- `static` is **not a replication directive**: replication is configured at the keyspace level and applies to partition data through standard replica placement.

Cassandra versions may differ in details regarding data types and CQL features. When applying this to another schema, verify the syntax for your deployed version.

## 3. Writing static columns via UPDATE with only the partition key

This is the most important property of static columns. For regular columns, you typically must identify **a complete row**, including clustering keys. For **static columns**, providing all **partition key** components is sufficient:

```sql
UPDATE shop.orders_by_customer_month
SET billing_currency = 'VND',
    month_note = 'Reconciling'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

The statement omits `order_id`. It updates the shared data of the partition:

```text
Full partition key = (11111111-1111-4111-8111-111111111111, '2026-11')
    billing_currency = 'VND'
    month_note = 'Reconciling'
```

If the partition already holds order rows X and Y, **both X and Y will see** `billing_currency = 'VND'` and the new note when read. Cassandra does not execute N separate `UPDATE`s for N orders; the mutation writes the static cells at the partition level.

### Writing regular columns requires locating the row

To update the status of **one order**, the full key is required:

```sql
UPDATE shop.orders_by_customer_month
SET order_status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Conversely, the following statement is **invalid** when trying to update a regular column:

```sql
-- INVALID: missing clustering key order_id for regular column order_status.
UPDATE shop.orders_by_customer_month
SET order_status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

A common misconception is treating a partition-key-only static write as "update all rows." The true meaning is: **write a value at the partition level**. If you need to change `order_status` across multiple orders, construct per-row operations or design a different table and workflow; you cannot apply static-write syntax to regular columns.

### When only part of the partition key is known

In this example, the partition key is the composite `(customer_id, order_month)`. Knowing only `customer_id` is still **insufficient** to identify a partition:

```sql
-- INVALID: missing order_month component of composite partition key.
UPDATE shop.orders_by_customer_month
SET billing_currency = 'VND'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

A static column's scope is **one full partition key**, not a partial key and certainly not all partitions for a customer.

## 4. Writing static columns via INSERT

Cassandra's `INSERT` can also write static columns. When writing an order row alongside monthly metadata, specify the **full primary key** and the corresponding columns:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    ordered_at, order_status, total,
    billing_currency, month_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    '2026-11-21 10:15:00+0700',
    'CREATED',
    250000.00,
    'VND',
    'Reconciling'
);
```

This single mutation writes two groups of data:

- `order_status`, `total`, and `ordered_at` belong to the row with that specific `order_id`.
- `billing_currency` and `month_note` belong to **the month's partition**, shared across all orders with the same partition key.

If a second order is added afterward:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    ordered_at, order_status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    33333333-3333-4333-8333-333333333333,
    '2026-11-21 10:30:00+0700',
    'PAID',
    750000.00
);
```

The second `INSERT` **does not mention** static columns, so it neither deletes nor overwrites the partition metadata. Reading both rows still yields `billing_currency = 'VND'`.

### INSERT containing only partition key and static columns

An important exception compared to regular-column `INSERT`: **when writing only static columns**, you may omit the clustering key.

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, billing_currency, month_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    'USD',
    'Preparing month close'
);
```

This statement is valid because all non-key columns being written are **strictly static columns**. It creates or updates metadata for the `2026-12` partition **without creating an actual order row with an `order_id`**. You cannot omit `order_id` in the same way when `INSERT`ing a regular column such as `order_status`.

Invalid example:

```sql
-- INVALID: regular column order_status requires a row key with order_id.
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    'CREATED'
);
```

This is why your application must distinguish static columns from regular columns before generating statements.

## 5. Static-only partitions: writing before any clustering rows exist

Consider the `2026-12` partition just created using only static columns. No row with a concrete `order_id` exists yet. Cassandra can still store the partition's static metadata.

Read with:

```sql
SELECT customer_id, order_month, order_id,
       billing_currency, month_note, order_status
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

For a partition containing only static data and no clustering rows, Cassandra can return a **result row representing the static-only partition**, where **the clustering column `order_id` and regular column `order_status` read as null**. This is how CQL result sets represent partition-level metadata, **not a business order with a null `order_id`**.

Once a December order is added:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    order_status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    44444444-4444-4444-8444-444444444444,
    'CREATED',
    40.00
);
```

The real order row is added to the same partition and reads alongside `billing_currency = 'USD'`.

**Note for Java code:** When reading an order list, do not turn a **static-only** result with a null clustering key into a phantom order. Check for the presence of the clustering key when mapping rows, or separate the metadata-read API from the order-list API.

## 6. Reading static columns: values appear alongside multiple rows

With the two November orders, execute:

```sql
SELECT order_id, order_status, total,
       billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Illustrative output:

| order_id (short) | order_status | total | billing_currency | month_note |
| --- | --- | ---: | --- | --- |
| `2222...2222` | CREATED | 250000.00 | VND | Reconciling |
| `3333...3333` | PAID | 750000.00 | VND | Reconciling |

Because both rows belong to the same partition, both result rows display the static metadata. **Repetition in the SELECT output does not mean the value is stored as two separate regular cells.**

You can read partition-level data using `SELECT DISTINCT` on the partition key and static columns:

```sql
SELECT DISTINCT customer_id, order_month,
       billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

`DISTINCT` in CQL has specific rules: selected columns must match the **partition key and static columns**; do not use it as an arbitrary `SELECT DISTINCT` over regular columns like in relational SQL.

### Static columns do not apply across all partitions of a customer

Example changing December's metadata:

```sql
UPDATE shop.orders_by_customer_month
SET billing_currency = 'EUR'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

This does not change `billing_currency` for `2026-11`, nor does it affect other customers. A static column's scope is **strictly one full partition key**.

## 7. Deleting static columns, deleting rows, and deleting partitions

The three operations below have different scopes, even though all target the same table.

### A. Deleting a single static value

```sql
DELETE month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

This deletes `month_note` at the partition level. When reading November orders, `month_note` reads as `null` once the tombstone is observed, while `billing_currency`, `order_status`, and `total` are untouched by this statement.

For a scalar static column, deletion intent can also be expressed via `UPDATE ... SET month_note = NULL`:

```sql
UPDATE shop.orders_by_customer_month
SET month_note = NULL
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Both statements express the same **intent to delete a static column**; only one needs to be executed. Cassandra writes a tombstone to ensure stale static versions do not reappear during reads or reconciliation.

### B. Deleting a single row by clustering key

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

This deletes **order row X**. It does not automatically delete `billing_currency` or `month_budget` for the partition. Order Y can still read the same static metadata, because static data exists independently of individual clustering rows.

### C. Deleting an entire partition

```sql
-- ONLY run when you truly want to delete the entire month for this customer.
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

A `DELETE` with no column list and only the partition key is a **partition delete**: it invalidates both all order rows and the static data of that partition. This is a critical distinction from an `UPDATE` that modifies static columns by partition key.

| Statement | Order rows | Static columns |
| --- | --- | --- |
| `DELETE month_note ... WHERE <partition key>` | Not automatically deleted | Deletes `month_note` |
| `DELETE FROM ... WHERE <partition key + order_id>` | Deletes one row | Not automatically deleted |
| `DELETE FROM ... WHERE <partition key>` | Deletes all rows in the partition | Deletes all static values in the partition |

Delete statements create **tombstones** of the corresponding scope. Compaction can purge deleted data when safe; repair helps replicas converge. A successful `DELETE` should not be viewed as immediately removing data from all SSTable files.

## 8. Timestamps, TTL, and concurrent updates on static columns

Static columns use the same version reconciliation mechanism as regular cells. The winning value is determined by the cell's **write timestamp**; improper clocks or custom timestamps can produce unpredictable conflicts.

Example of two clients updating `month_note` for the same partition:

```text
Client A: month_note = 'Reconciling', timestamp 1000000
Client B: month_note = 'Closed',      timestamp 2000000

When versions converge, 'Closed' wins due to the higher timestamp.
```

These timestamps merely illustrate ordering; actual Cassandra timestamps use **microseconds since the Unix epoch**. Writing `month_note` for November does not contend on the same cell as `month_note` for December, as those are two distinct partitions.

### TTL on a static column

You can write a static column with a TTL in seconds:

```sql
UPDATE shop.orders_by_customer_month USING TTL 3600
SET month_note = 'Temporary note'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

This sets a TTL on the `month_note` value just written. **It does not automatically apply a TTL to `billing_currency`, `month_budget`, or any regular order columns**, because those columns are absent from the mutation.

Inspect cell metadata:

```sql
SELECT DISTINCT customer_id, order_month,
       month_note, billing_currency
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';

SELECT month_note, TTL(month_note), WRITETIME(month_note)
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

`TTL(month_note)` shows remaining seconds if the cell has a TTL; `WRITETIME(month_note)` shows the write timestamp. For partitions with order rows, standard queries can repeat static values across each selected row. Once the TTL expires, the static value is no longer live and can read as `null`.

If the keyspace/table experiences concurrent changes, read results depend on the consistency level and replicas queried. `CONSISTENCY QUORUM` in `cqlsh` (with an appropriate replication factor) may require more replicas to respond than `ONE`, but **it does not turn a static update into a transactional lock across all order rows**.

### When a precondition is needed before writing

If business logic states "only close the note while it is still `Reconciling`," a normal `SELECT` followed by `UPDATE` leaves a race window. You can use a **lightweight transaction (LWT)** on the static column:

```sql
UPDATE shop.orders_by_customer_month
SET month_note = 'Closed'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
IF month_note = 'Reconciling';
```

The result reports `[applied]` as `true` or `false`. LWT relies on consensus and incurs higher coordination cost than regular writes, so use it when concurrent conditions genuinely matter. Note: the `IF` condition above protects only **the checked value**; it does not automatically ensure every `order_status` in the partition is reconciled.

### Repeated writes and timeouts

If a client receives a timeout while updating `billing_currency` or `month_note`, you cannot conclude with certainty that the mutation reached zero replicas. On retry, a write to the same key with a new timestamp may beat a concurrent mutation just applied by another client. For business-critical transitions such as "closing monthly books," design explicit state transitions and LWT conditions rather than retrying an unconditional upsert indefinitely.

## 9. Java Driver: writing partition metadata

A Java application typically has two distinct write flows:

1. Save/update an **order** by full primary key `(customer_id, order_month, order_id)`.
2. Save/update **monthly metadata** by partition key `(customer_id, order_month)`.

Express these two operations with prepared statements that specify clear keys and column lists, so editing monthly info does not accidentally require or overwrite order-level data.

### Prepared UPDATE touching only static columns

Apache Cassandra Java Driver 4.x example, assuming an existing `CqlSession session` and `UUID customerId`:

```java
PreparedStatement updateMonth = session.prepare(
    "UPDATE shop.orders_by_customer_month " +
    "SET billing_currency = :currency, month_note = :note " +
    "WHERE customer_id = :customer_id AND order_month = :month"
);

BoundStatementBuilder builder = updateMonth.boundStatementBuilder()
    .setUuid("customer_id", customerId)
    .setString("month", "2026-11")
    .setString("currency", "VND")
    .unset("note");  // Do not modify month_note

session.execute(builder.build());
```

There is no `order_id` marker because this statement writes only static columns. `unset("note")` keeps the partition's `month_note` untouched; calling `setToNull("note")` would **delete the static value** via a tombstone. This is critical for partial metadata update APIs.

If an API accepts JSON from a client:

```json
{
  "billingCurrency": "USD"
}
```

the request means "change `billing_currency`, leave `month_note` alone." Distinguish an **absent field** from a field **explicitly sent as null**, for example via `JsonNode.has(...)`/`isNull()` or another field-presence mechanism. For mandatory metadata such as currency, reject null via validation instead of allowing deletion.

### Prepared INSERT creating metadata before orders arrive

```java
PreparedStatement insertMonth = session.prepare(
    "INSERT INTO shop.orders_by_customer_month " +
    "(customer_id, order_month, billing_currency, month_budget) " +
    "VALUES (?, ?, ?, ?)"
);

BoundStatement statement = insertMonth.bind(
    customerId,
    "2027-01",
    "VND",
    new java.math.BigDecimal("20000000.00")
);

session.execute(statement);
```

The CQL inside writes only the **partition key and static columns**, so `order_id` is unnecessary. If month initialization requires "create only if metadata does not exist yet" by business rules, carefully define what "already exists" means for a static-only partition and choose an appropriate LWT condition; never assume regular `INSERT` rejects an existing partition key.

### Reading and mapping results

```java
PreparedStatement readMonth = session.prepare(
    "SELECT DISTINCT customer_id, order_month, " +
    "billing_currency, month_note, month_budget " +
    "FROM shop.orders_by_customer_month " +
    "WHERE customer_id = ? AND order_month = ?"
);

Row row = session.execute(
    readMonth.bind(customerId, "2026-11")
).one();

if (row != null) {
    String currency = row.getString("billing_currency");
    String note = row.getString("month_note");
    java.math.BigDecimal budget = row.getBigDecimal("month_budget");
    // Process metadata according to the API contract.
}
```

Imports, session configuration, validation, and network error handling are omitted to focus on CQL. This `SELECT DISTINCT` selects the partition key and static columns so it does not accidentally return one metadata object per order. Handle empty results or unwritten static columns (returning null) according to your application's business rules.

## 10. Step-by-step lab: one static value across multiple rows

Run in a learning environment against the `shop.orders_by_customer_month` table created in section 2. Use a dedicated partition key for customer `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` in month `2027-02` to keep it independent from earlier examples.

### Step 1 — Create a static-only partition

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, billing_currency, month_note
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    'VND',
    'Newly initialized'
);

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** partition-level metadata can appear even when no real `order_id` row exists yet; if you see a row with a null clustering key, that represents the static-only partition.

### Step 2 — Add two orders without rewriting static columns

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id, order_status, total
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    'CREATED',
    100000.00
);

INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id, order_status, total
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    cccccccc-cccc-4ccc-8ccc-cccccccccccc,
    'PAID',
    200000.00
);

SELECT order_id, order_status, total, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** two real order rows appear with `billing_currency = 'VND'` and `month_note = 'Newly initialized'`. Metadata is not cleared even though both `INSERT`s list only regular columns.

### Step 3 — Change a static value and observe both rows

```sql
UPDATE shop.orders_by_customer_month
SET month_note = 'Under review'
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** both result rows show `month_note = 'Under review'`. There is no per-`order_id` update loop.

### Step 4 — Change a regular column on just one order

```sql
UPDATE shop.orders_by_customer_month
SET order_status = 'SHIPPING'
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02'
  AND order_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb;
```

**Prediction:** only order `bbbb...`'s status changes. The partition's `month_note` remains unchanged.

### Step 5 — Delete one row; metadata remains

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02'
  AND order_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb;

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** order `cccc...` still exists and still sees the static metadata.

### Step 6 — Delete only one static column

```sql
DELETE month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';

SELECT order_id, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** `month_note` reads as null; `billing_currency` remains VND and order `cccc...` still exists.

### Step 7 — Distinguish partition deletion

Only on disposable practice data, try:

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Prediction:** this deletes the **entire partition**, including all clustering rows and static metadata. Never run this form of delete on a partition containing data you need to preserve.

### Expected results table

| After step | Live order rows | `billing_currency` | `month_note` |
| --- | --- | --- | --- |
| 1 | No real orders yet | VND | Newly initialized |
| 2 | `bbbb...`, `cccc...` | VND (same for both orders) | Newly initialized |
| 3 | `bbbb...`, `cccc...` | VND | Under review |
| 4 | `bbbb...`, `cccc...` | VND | Under review |
| 5 | `cccc...` | VND | Under review |
| 6 | `cccc...` | VND | null |
| 7 | None left | None left | None left |

Expectations assume no competing writes, other TTLs, or unusual timestamps. Deletion markers may remain in physical storage until eligible for collection.

## 11. When to use static columns and common pitfalls

A static column fits when an attribute **genuinely depends on the partition key, not the clustering key**, and is read alongside or separately from rows in that partition.

| Scenario | Use a static column? | Reason |
| --- | --- | --- |
| Each customer and month has one reporting currency | Likely suitable | Depends on `(customer_id, order_month)` |
| Each order has its own delivery status | No | Status depends on `order_id` |
| Unit price of different products in a cart | No, if each product is a row | Price belongs to each clustering row |
| A shared note for all events in a session | Likely suitable | Note belongs to the session/partition |
| A global config applied to every customer in the table | Not suitable merely via `static` | Static is **per partition**, not table-wide |

### Common mistakes

1. **Confusing static with regular columns.** Using a `WHERE` clause missing the clustering key to modify a regular column fails; only static writes have the partition-key exception.
2. **Confusing static with table-wide fields.** Writing November metadata does not alter December or other customers.
3. **Assuming INSERT always requires a clustering key.** An `INSERT` with only the partition key and static columns can be valid; `INSERT`ing regular columns still requires identifying the row.
4. **Treating a static-only result as a real business row.** A row displaying `order_id = null` represents metadata, not a valid order.
5. **Deleting a row and expecting static columns to disappear.** Deleting a clustering row leaves static metadata intact; only deleting the whole partition removes both.
6. **Relying on static columns to solve oversized partitions.** Static columns reduce duplicated metadata values but **do not** shrink row counts or transactional data volume inside a partition; partition key design, load distribution, and row counts still require control.
7. **Changing static values with unconditional upserts under contention.** Multiple clients can write concurrently; use `IF`/LWT when old-state checks are required.
8. **Binding null for omitted fields in PATCH APIs.** `NULL` deletes static data and generates tombstones, whereas `UNSET` preserves unwritten static cells.

### Self-check

**Q1.** A partition has 10,000 rows and a `billing_currency static` column. Will running `UPDATE ... SET billing_currency = 'USD' WHERE <full partition key>` write 10,000 separate regular cells?

**Answer:** No. The mutation writes the static value at the partition level; all 10,000 rows observe that value when read.

**Q2.** Is an `INSERT` containing only the partition key and `month_note static`, without `order_id`, valid?

**Answer:** Yes, when all non-key columns being written are static columns and the table has a valid static schema definition.

**Q3.** If you run `DELETE FROM ... WHERE <partition key + order_id>`, is the partition's static column deleted?

**Answer:** Not by that row deletion itself. Deleting only a static column or deleting the entire partition are distinct operations.

**Q4.** Does changing November's `month_note` affect December's orders?

**Answer:** No. The two months correspond to two distinct partition keys.

**Q5.** One client wants to change `month_note` only while it is still `Reconciling`, while another client may edit the same field concurrently. What should be done?

**Answer:** Use a conditional update `IF month_note = 'Reconciling'` and inspect the `[applied]` result if that constraint matters.

**Takeaway:** **Static columns belong to the partition key, whereas regular columns belong to the row identified by the full primary key.** With static columns, you can write via `UPDATE` using only the full partition key or `INSERT` without a clustering key when writing solely static data. Every row in the same partition sees that static value; reads, deletes, TTLs, timestamps, and LWT still follow Cassandra's distributed data mechanics. Understanding the boundary between partition level and row level helps you model tables cleanly around queries and avoid mutations whose scope is broader than your Java application intended.
