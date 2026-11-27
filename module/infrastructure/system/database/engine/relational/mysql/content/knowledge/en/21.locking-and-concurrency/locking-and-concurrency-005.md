# Locking and concurrency

## SELECT FOR UPDATE and SELECT FOR SHARE

InnoDB supports two common forms of locking reads: `SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE`. They allow a transaction to read current rows while placing locks on the rows read. This is useful when an application needs to inspect a state before deciding whether to update it, keep a row stable while executing business logic, or distribute work across multiple workers.

The two statements serve different purposes. `FOR UPDATE` acquires an exclusive lock, suitable when the transaction intends to modify or delete rows. `FOR SHARE` acquires a shared lock, allowing other transactions to also perform shared locking reads while preventing conflicting modifications until the transaction finishes. They are row-level concurrency control tools; using them properly requires understanding transaction scope, index-based lock scope, isolation levels, and lock-wait handling.

### 1. How do locking reads differ from a regular SELECT?

A regular `SELECT` in InnoDB is a consistent read. It reads the version matching its MVCC read view and acquires no row locks simply for reading. If another transaction holds an exclusive lock on a row, a consistent read can usually still read the previously committed version without waiting for the writing transaction to finish.

`SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking reads. They read the current data and place locks on the accessed rows/index records. If a conflicting lock is held by another transaction, the statement must wait—or return an error or skip rows if using `NOWAIT`/`SKIP LOCKED`.

| Characteristic | Regular `SELECT` | `SELECT ... FOR SHARE` | `SELECT ... FOR UPDATE` |
| --- | --- | --- | --- |
| Read type | Consistent read via MVCC | Current/locking read | Current/locking read |
| Row locks | Acquires no row locks just for reading | Shared lock (S) | Exclusive lock (X) |
| Other transactions' regular reads | Usually reads committed version without waiting on row locks | Regular reads can still use MVCC | Regular reads can still use MVCC |
| Other transactions' locking reads | Places no row locks to block | `FOR SHARE` is compatible; `FOR UPDATE` conflicts | Both `FOR SHARE` and `FOR UPDATE` conflict |
| Purpose | Reading reports or consistent snapshots | Keeping rows stable during coordinated reads | Reading rows to be updated/deleted or claimed |

Locks from a locking read are normally held until the transaction runs `COMMIT` or `ROLLBACK`. Thus, a transaction can read a current value and keep that row protected while running additional related statements.

### 2. Syntax of FOR UPDATE and FOR SHARE

Basic syntax in MySQL 8.0:

```sql
SELECT column_list
FROM table_name
WHERE condition
FOR UPDATE;

SELECT column_list
FROM table_name
WHERE condition
FOR SHARE;
```

They can be combined with `JOIN`, `ORDER BY`, `LIMIT`, and lock-handling options:

```sql
SELECT id, status
FROM orders
WHERE status = 'pending'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

In MySQL 8.0, `FOR SHARE` is the modern syntax replacing the older `LOCK IN SHARE MODE`. For multi-table joins, MySQL supports the `OF` syntax to specify which table to lock, e.g., `FOR UPDATE OF o`. If no target is specified, the locking clause applies to the tables referenced in the query block according to MySQL's rules.

These two clauses must be placed inside a transaction with sufficient scope. The clearest pattern is to use `START TRANSACTION`, execute the locking read and related operations, and then end with `COMMIT` or `ROLLBACK`:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE;

-- Perform related checks and business logic here.

COMMIT;
```

If you run a locking read as a standalone statement in autocommit mode, the implicit transaction ends immediately after the statement and the lock is released; subsequent statements are no longer protected by that lock. Never open a transaction and leave it open while waiting for user input, calling external services, or running long tasks.

### 3. SELECT ... FOR UPDATE: exclusive lock to prepare for writing

`FOR UPDATE` asks InnoDB to acquire an exclusive lock on the rows read. Other transactions cannot concurrently acquire conflicting shared or exclusive locks on the same rows until the lock is released. However, regular consistent reads can still read an older committed version thanks to MVCC.

For example, an application needs to check inventory quantity and then deduct one unit:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (id, sku, quantity)
VALUES (1, 'KB-100', 5);
```

The transaction holds an exclusive lock during checking and updating:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1
FOR UPDATE;

-- Application checks quantity > 0.

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity > 0;

-- Check affected row count before deciding to commit.
COMMIT;
```

If two sessions run this workflow concurrently for `id = 1`, the session acquiring the lock first proceeds. The other session must wait. Once the first session commits, the second session continues on the current state and reads the new quantity. Consequently, the two sessions do not both deduct from a stale inventory value.

In real applications, check the result of `UPDATE`. If no rows were updated, inventory may already be 0 or the business condition may no longer hold; in that case, roll back or return an appropriate out-of-stock response. `FOR UPDATE` protects the read-write window, but does not replace condition checking and result handling.

### 4. SELECT ... FOR SHARE: shared lock to keep data stable

`FOR SHARE` acquires a shared lock on the rows read. Multiple transactions can hold a shared lock on a row simultaneously. However, another transaction cannot modify or delete that row while the shared lock exists, and cannot acquire an exclusive lock to update it.

For example, a transaction reads a price configuration and needs to ensure the price is not altered during a multi-step calculation:

```sql
START TRANSACTION;

SELECT price, currency
FROM product_price
WHERE product_id = 501
FOR SHARE;

-- Run related read queries and business calculations.

COMMIT;
```

While the transaction holds the shared lock, another session attempting to update the price for `product_id = 501` must wait. Other transactions can still concurrently read the row using `FOR SHARE`.

Only use `FOR SHARE` when you genuinely need to prevent concurrent modifications. If you only need a consistent snapshot for display or reporting aggregation, a regular `SELECT` is usually more appropriate and causes less write contention.

### 5. Compatibility of shared locks and exclusive locks

For the same row, the basic compatibility rules are:

| Lock currently held | `FOR SHARE` (S) request | `FOR UPDATE` (X) request |
| --- | --- | --- |
| No conflicting lock | Granted | Granted |
| Shared lock (S) | Can coexist | Must wait |
| Exclusive lock (X) | Must wait | Must wait |

An `UPDATE` or `DELETE` also requires an exclusive lock on the rows it modifies. Therefore, it must wait if a row is currently held under a shared lock or an exclusive lock by another transaction.

Two-session example:

**Session A:**

```sql
START TRANSACTION;

SELECT balance
FROM account
WHERE id = 10
FOR SHARE;
```

**Session B:**

```sql
UPDATE account
SET balance = balance - 100
WHERE id = 10;
-- Must wait for Session A's shared lock to be released.
```

**Session A:**

```sql
COMMIT;
```

After A commits, the shared lock is released and B can proceed. If A holds its transaction open too long, related write sessions must wait just as long.

### 6. Using FOR SHARE and then upgrading to FOR UPDATE can cause deadlocks

A common design mistake is two transactions both reading a row with `FOR SHARE`, and then both attempting to upgrade the lock to exclusive for an update. Their shared locks are compatible, so both reads succeed. However, when each side requests an exclusive lock, each must wait for the shared lock held by the other. InnoDB detects the wait cycle and aborts one transaction to break the deadlock.

Simulation:

```sql
-- Session A
START TRANSACTION;
SELECT quantity FROM inventory WHERE id = 1 FOR SHARE;

-- Session B
START TRANSACTION;
SELECT quantity FROM inventory WHERE id = 1 FOR SHARE;

-- Session A: needs to upgrade to exclusive to write
UPDATE inventory SET quantity = quantity - 1 WHERE id = 1;
-- Waits for Session B.

-- Session B: also needs to upgrade to exclusive
UPDATE inventory SET quantity = quantity - 1 WHERE id = 1;
-- The two sessions form a wait cycle; one transaction may be rolled back due to deadlock.
```

If you know from the start that you will update or delete the row, use `FOR UPDATE` instead of `FOR SHARE`. If you only need to check a condition and adjust a value, consider a single atomic DML statement with the condition in `WHERE` to avoid splitting the operation into multiple steps.

### 7. Lock scope depends on indexes and isolation level

A locking read does not necessarily lock only the exact number of rows returned. InnoDB typically locks the index records scanned during execution; the exact scope depends on predicates, the chosen index, the access plan, and the isolation level.

- If the search predicate uses the primary key or a unique index with an equality check for an existing row, InnoDB usually only needs to lock the corresponding record.
- If the predicate scans a range or uses a non-unique index under `REPEATABLE READ`, InnoDB may use next-key locks, combining record locks with gap locks on the preceding index intervals.
- Under `READ COMMITTED`, gap locking for normal searches and scans is generally disabled; exceptions remain for foreign key checks and duplicate-key checks.
- Without a suitable index, MySQL may have to scan more index records than expected, increasing both lock scope and the number of waiting transactions.

Example locking one order by primary key:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE;

COMMIT;
```

An equality predicate on the primary key identifies a single specific record. Conversely, a query filtering by status may have to lock many matching records across an index range:

```sql
START TRANSACTION;

SELECT id
FROM orders
WHERE status = 'pending'
ORDER BY created_at
FOR UPDATE;

COMMIT;
```

If the table has many pending orders, the second query can hold a huge number of locks. A suitable index such as `(status, created_at, id)` can reduce the amount of data scanned and make access order more predictable. Even so, an index does not limit the row count locked; if you only need a small batch, design `LIMIT` and appropriate selection predicates.

With secondary indexes, InnoDB also needs to lock the corresponding record in the clustered index to protect the data row. Therefore, lock scope cannot be understood solely from the column names appearing in `WHERE`.

### 8. NOWAIT and SKIP LOCKED when you do not want to wait for locks

MySQL supports two options for locking reads:

- `NOWAIT`: if a row to be locked already has a conflicting lock from another transaction, the statement immediately returns an error instead of waiting.
- `SKIP LOCKED`: skips rows with conflicting locks and returns rows that can be locked immediately.

`NOWAIT` example:

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 1001
FOR UPDATE NOWAIT;

COMMIT;
```

If another session holds a conflicting lock on `id = 1001`, the application immediately receives an error and can return a busy notice, retry later, or choose another workflow. Avoid unbounded tight retries, as they can increase load and lock contention.

`SKIP LOCKED` is often useful for queue tables where multiple workers claim jobs concurrently:

```sql
START TRANSACTION;

SELECT id
FROM job_queue
WHERE status = 'pending'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Application takes the id list and updates those rows.
UPDATE job_queue
SET status = 'processing', claimed_by = 'worker-A'
WHERE id IN (101, 102, 103);

COMMIT;
```

The `id` list in the `UPDATE` statement must be the actual values returned by the `SELECT`; the example above illustrates the statement pattern. When worker A has locked certain rows, worker B can run the same `SKIP LOCKED` query and claim unlocked rows instead of waiting for A.

In return, `SKIP LOCKED` results are not a complete consistent snapshot of all matching rows: currently locked rows are skipped. Use it only for job-claiming workflows or cases where temporary skipping is acceptable. Do not use it to generate reports requiring complete data. `NOWAIT` and `SKIP LOCKED` handle row-lock conflicts; table-level or metadata locks can still cause statements to wait.

For production queues, update the claim status and worker metadata inside the same transaction as the locking read, then commit quickly. Long processing work should happen after claiming; include a lease or claim expiration mechanism to recover abandoned rows if a worker crashes. If you commit before marking the status, another worker can claim the same row once the lock is released.

### 9. Locking clauses in JOINs and subqueries

In multi-table queries, a locking clause can lock rows read from all joined tables. If you only want to lock the target table, use `OF` when your MySQL version supports it:

```sql
START TRANSACTION;

SELECT o.id, o.status, c.name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.id = 1001
FOR UPDATE OF o;

COMMIT;
```

In this example, the goal is to lock the order row in `o`; the `customers` table is only read to retrieve the name. If `OF o` is omitted, the locking clause applies more broadly according to query block rules and can lock rows across multiple referenced tables.

An easy detail to overlook is that a locking clause in an outer query block does not automatically lock rows read inside a subquery. If you need to lock a table inside a subquery as well, place a locking clause inside that subquery itself:

```sql
START TRANSACTION;

SELECT o.id
FROM orders AS o
WHERE o.customer_id = (
    SELECT c.id
    FROM customers AS c
    WHERE c.email = 'buyer@example.com'
    FOR SHARE
)
FOR UPDATE;

COMMIT;
```

Here, `FOR UPDATE` locks the order rows in the outer query, while `FOR SHARE` locks the customer row in the inner query. Only lock the tables that truly need protection to reduce contention and avoid holding unnecessary locks.

### 10. Deadlocks, lock wait timeouts, and handling

Locking reads help coordinate transactions, but they do not eliminate deadlocks. Deadlocks can occur when transactions lock multiple rows in different orders, upgrade shared locks to exclusive locks, or hold locks too long while waiting on other resources.

Principles to reduce risk:

1. Access multiple rows in a consistent order across all business flows.
2. Use indexed search predicates to narrow the number of records scanned and locked.
3. Keep transactions short; do not make HTTP calls, send emails, or wait on users while holding locks.
4. Use `FOR UPDATE` from the beginning if you are certain you will modify the row; avoid unnecessary upgrades from `FOR SHARE`.
5. Handle deadlock errors by retrying the entire transaction after rollback, with a retry cap and appropriate backoff.
6. Distinguish deadlocks from lock wait timeouts; log enough information to investigate transactions, queries, and lock order.

InnoDB automatically detects deadlocks and chooses one transaction as the victim to roll back. A lock wait timeout occurs when waiting for a lock exceeds the configured timeout; depending on configuration, either only the failing statement or the entire transaction is rolled back. Applications should explicitly manage transaction state and never continue using a transaction that has been unexpectedly rolled back.

### 11. Inspecting transactions and waiting locks

When a locking read waits for a long time, determine which transaction holds the lock, which transaction is waiting, and which query caused the conflict. You can start with:

```sql
SELECT CONNECTION_ID();
SELECT @@autocommit, @@transaction_isolation;
SHOW ENGINE INNODB STATUS;
```

`SHOW ENGINE INNODB STATUS` provides details about the latest deadlock and InnoDB state. In MySQL 8.0, system tables in `performance_schema` and `sys` views help inspect transactions, data locks, and lock waits; column names and access permissions depend on version/configuration. Example overview query for open transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
```

Combine transaction info with `EXPLAIN` on the query to find causes of overly broad scans or poor index selection. During incident response, do not rush to `KILL` a session before verifying the business context and rollback impact.

### 12. Checklist for choosing locking reads

1. Use a regular `SELECT` if you only need a consistent snapshot and do not need to block concurrent updates.
2. Use `SELECT ... FOR UPDATE` when the transaction will modify/delete rows or needs to claim rows exclusively.
3. Use `SELECT ... FOR SHARE` when multiple transactions may read concurrently but conflicting updates must be prevented briefly.
4. Wrap the locking read and dependent statements in the same transaction; commit or roll back promptly.
5. Check indexes and scan scope to avoid locking more records/gaps than necessary.
6. Use `NOWAIT` if the business flow needs immediate failure when busy; use `SKIP LOCKED` for queues where skipping rows held by other workers is acceptable.
7. Prepare to handle deadlocks, timeouts, and safe retries; never retry infinitely.
8. For multi-table queries or subqueries, clearly identify the query block and tables that actually require locking.

`FOR UPDATE` and `FOR SHARE` turn a read into a locking operation, enabling transactions to coordinate on current data. Choosing the right lock type, limiting access scope, and ending transactions promptly protects business correctness while preserving InnoDB concurrency.
