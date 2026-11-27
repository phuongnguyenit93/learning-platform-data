# Data Manipulation

## ORDER BY/LIMIT in DML and Statement-Form Restrictions

In MySQL, `ORDER BY` and `LIMIT` help select a subset of records in a deterministic order when updating or deleting data in batches. However, these two clauses cannot be placed arbitrarily at the end of every DML statement. Whether they are permitted depends on the exact syntax form: single-table `UPDATE` and `DELETE` support them directly; multi-table forms do not; and `INSERT ... SELECT` only allows them inside the source `SELECT` query.

Understanding these syntax boundaries prevents SQL errors and helps design controllable data-modification batches with inspectable access plans and safe execution on large tables.

### 1. Distinguishing the Position of ORDER BY and LIMIT

`ORDER BY` determines the order in which rows are evaluated or processed. `LIMIT` caps how many rows from the matching set are affected. In DML, their meaning depends on the statement form:

| MySQL Statement Form | `ORDER BY` / `LIMIT` at the DML Statement Level | Interpretation |
| --- | --- | --- |
| Single-table `UPDATE` | Both supported | Orders the rows to be updated and limits how many matching rows are affected |
| Single-table `DELETE` | Both supported | Orders the rows to be deleted and limits how many rows are deleted |
| Multi-table `UPDATE`, typically using `JOIN` | Not supported | Multi-table syntax has no `ORDER BY` or `LIMIT` clause |
| Multi-table `DELETE`, such as `DELETE t1 FROM ... JOIN ...` | Not supported | Multi-table syntax has no `ORDER BY` or `LIMIT` clause |
| `INSERT ... VALUES` or `INSERT ... SET` | Not supported | There is no source query set on which to apply `ORDER BY` / `LIMIT` |
| `INSERT ... SELECT` | Supported inside source `SELECT` | Both clauses sort and limit the rows queried for insertion |
| `REPLACE ... VALUES` or `REPLACE ... SET` | Not supported | Does not support these statement-level clauses |
| `REPLACE ... SELECT` | Supported inside source `SELECT` | Both clauses belong to the source query, not the outer `REPLACE` |
| `TRUNCATE TABLE` | Not supported | This is a DDL command that empties the entire table, not row-filtered DML |

The key point is to recognize the **syntax form** being used. An `UPDATE` that modifies only one target table via `UPDATE ... JOIN` still belongs to MySQL's multi-table update syntax; you cannot append `ORDER BY` or `LIMIT` to the end of that statement.

### 2. Single-Table UPDATE: Ordering Rows and Limiting Updated Rows

Abbreviated syntax:

```sql
UPDATE table_name
SET column = value
WHERE condition
ORDER BY sort_column [ASC | DESC], primary_key
LIMIT row_count;
```

For example, transitioning up to 200 expired orders from `pending` to `expired`:

```sql
UPDATE orders
SET status = 'expired'
WHERE status = 'pending'
  AND expires_at < CURRENT_TIMESTAMP
ORDER BY expires_at ASC, id ASC
LIMIT 200;
```

MySQL evaluates rows matching `WHERE` in `expires_at` order, then uses `id` as a tie-breaker for rows sharing the same expiration timestamp. At most 200 matching rows are updated in this run.

In `UPDATE`, `LIMIT` caps the number of **matched rows**, not the number of rows whose values actually change. If a row already holds the assigned value, it can still count toward the limit whenever it matches `WHERE`. Therefore, when batching, the `WHERE` condition should exclude already-processed rows from subsequent runs—for example, by changing status from `pending` to `expired`.

`ORDER BY` can also control update order, which is useful when updating a column with a uniqueness constraint. For instance, if `position` has a unique index, incrementing values in descending order processes larger positions first to avoid colliding with rows not yet updated:

```sql
UPDATE sequence_item
SET position = position + 1
ORDER BY position DESC;
```

This ordering applies only during execution of the statement; it creates no guarantee that subsequent `SELECT` queries will return rows in that order. Whenever ordered query results are needed, specify `ORDER BY` in the `SELECT` query itself.

### 3. Single-Table DELETE: Batched Deletion

Abbreviated syntax:

```sql
DELETE FROM table_name
WHERE condition
ORDER BY sort_column [ASC | DESC], primary_key
LIMIT row_count;
```

For example, deleting up to 500 of the oldest log entries:

```sql
DELETE FROM event_log
WHERE created_at < '2026-01-01'
ORDER BY created_at ASC, id ASC
LIMIT 500;
```

`ORDER BY` determines which rows are selected before the limit is applied. If `ORDER BY` is omitted, MySQL can delete any 500 matching rows; applications should never rely on physical table order or accidental ordering from a given execution.

Adding a unique key such as `id` as the final sort criterion stabilizes ordering when multiple rows share the same `created_at`. If you sort only by timestamp and many rows have identical timestamps, the order among those rows is underspecified, and different runs may pick different subsets.

### 4. LIMIT in UPDATE and DELETE Does Not Support OFFSET

In single-table `UPDATE` and single-table `DELETE` syntax, MySQL accepts `LIMIT row_count`:

```sql
DELETE FROM event_log
WHERE severity = 'debug'
ORDER BY id
LIMIT 1000;
```

Do not use pagination forms like `LIMIT offset, row_count` or `LIMIT row_count OFFSET offset` directly at the end of these `UPDATE` / `DELETE` statements. Those two `OFFSET` forms belong to `SELECT` query syntax.

To process the next batch, repeat the same statement if the operation causes processed rows to stop matching `WHERE` (for example, deleting rows or changing their status). If you need to advance from a key bookmark, place a key condition in `WHERE`, such as `id > last_id_value`, paired with `ORDER BY id LIMIT row_count`. This avoids skipping large numbers of rows via offset and provides a clear continuation point.

### 5. INSERT ... SELECT: Limits Belong Inside the Source Query

`INSERT ... VALUES` and `INSERT ... SET` do not have statement-level `ORDER BY` or `LIMIT`. The following example inserts the two specified values directly with no limit clause:

```sql
INSERT INTO tag (name)
VALUES ('database'), ('mysql');
```

With `INSERT ... SELECT`, you can sort and limit the row set produced by `SELECT`:

```sql
INSERT INTO archived_orders (id, customer_id, created_at)
SELECT id, customer_id, created_at
FROM orders
WHERE created_at < '2025-01-01'
ORDER BY created_at ASC, id ASC
LIMIT 500;
```

In this example, `ORDER BY` and `LIMIT` belong to the `SELECT` query. They determine at most 500 source rows fed into the insert operation. Do not mistake this for a standalone `LIMIT` placed after the entire `INSERT` statement.

The same placement rule applies to `REPLACE ... SELECT`. With `INSERT ... ON DUPLICATE KEY UPDATE`, the duplicate-update clause has no separate `ORDER BY` / `LIMIT`; if the statement uses `INSERT ... SELECT`, those clauses still belong to the source query.

### 6. Multi-Table UPDATE / DELETE Do Not Accept ORDER BY or LIMIT

MySQL provides multi-table update syntax, commonly combining the target table with other tables via `JOIN`:

```sql
UPDATE orders AS o
JOIN customers AS c ON c.id = o.customer_id
SET o.review_flag = 1
WHERE c.segment = 'business';
```

This is multi-table `UPDATE` syntax. Even though only columns of `orders` are assigned, you cannot append `ORDER BY` or `LIMIT` to the end of the statement. Multi-table `DELETE` has the same restriction:

```sql
DELETE o
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.segment = 'inactive';
```

Do not add `ORDER BY ... LIMIT ...` to `DELETE ... FROM ... JOIN ...` or `DELETE ... USING ...`. If you need to limit the number of keys selected from a join, perform the key selection in a separate query first, then pass that key set to the multi-table operation.

Example using a temporary table to limit to the oldest 100 orders by creation time, then deleting the selected orders:

```sql
CREATE TEMPORARY TABLE batch_order_ids (
    id BIGINT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO batch_order_ids (id)
SELECT o.id
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE c.segment = 'inactive'
ORDER BY o.created_at ASC, o.id ASC
LIMIT 100;

DELETE o
FROM orders AS o
JOIN batch_order_ids AS b ON b.id = o.id;

DROP TEMPORARY TABLE batch_order_ids;
```

The data type of `batch_order_ids.id` must match the type and signedness of `orders.id`. The limit of 100 sits inside `INSERT ... SELECT`; the multi-table `DELETE` simply joins against the selected list of keys and thus stays within syntax rules. If concurrent sessions modify the same data, design appropriate transactions and locking/claiming mechanisms so the selected key set cannot change unexpectedly between selection and deletion.

### 7. Choosing Indexes and Operating DML Batches

`ORDER BY` and `LIMIT` help only when the target rows can be located at reasonable cost. For the order-expiration update above, an index starting with the equality filter column followed by the sort columns can help MySQL locate rows in order more efficiently—for example, considering an index on `(status, expires_at, id)`. Actual index choices must account for data distribution, other queries, and extra write overhead; do not create an index solely because one statement uses `LIMIT`.

You can inspect the query selecting the same key set with `EXPLAIN`:

```sql
EXPLAIN
SELECT id
FROM orders
WHERE status = 'pending'
  AND expires_at < CURRENT_TIMESTAMP
ORDER BY expires_at ASC, id ASC
LIMIT 200;
```

This query shows which index MySQL expects to use, estimates how many rows must be read, and reveals whether an extra sort is required. At large data volumes, watch out for cases where MySQL must scan many rows only to discard most of them, or sort a huge set before applying `LIMIT`.

When running batched DML in InnoDB, choose a batch size appropriate for lock duration, undo/redo volume, and recovery requirements. Smaller batches are usually easier to control than a single statement modifying millions of records in one long transaction. However, `LIMIT` alone does not guarantee safe queue processing across multiple workers: concurrent sessions can see the same candidates or data can change between steps. When exactly-once processing is required, combine transactions, row locking or state claiming, and idempotent operation design.

### 8. Pre-Execution Checklist

1. Identify whether the statement uses single-table or multi-table syntax; `UPDATE ... JOIN` and `DELETE ... FROM ... JOIN` are multi-table forms.
2. Place `ORDER BY` / `LIMIT` only where the statement syntax permits. For `INSERT ... SELECT`, they belong inside the source `SELECT`.
3. When using `LIMIT` to pick a batch, append a unique key at the end of `ORDER BY` so selection is deterministic.
4. For single-table `UPDATE` / `DELETE`, use `LIMIT row_count`; do not put an offset at the DML level.
5. Verify `WHERE` conditions, indexes, and access plans before running on large tables.
6. When batching, ensure processed rows are not unintentionally re-selected and use appropriate transaction and concurrency handling.

Understanding where `ORDER BY` and `LIMIT` belong enables writing valid SQL statements, targeting exact record sets, and chunking data modifications for safer MySQL operations.
