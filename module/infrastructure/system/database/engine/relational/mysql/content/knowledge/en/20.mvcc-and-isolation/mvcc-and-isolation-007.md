# SERIALIZABLE and Its Impact on Locks and Concurrency

## Objectives

After this lesson, you will be able to:

- Explain the meaning of the `SERIALIZABLE` isolation level and the read anomalies it aims to prevent.
- Describe how InnoDB implements `SERIALIZABLE`, specifically converting plain `SELECT` into a shared locking read inside an explicit transaction.
- Distinguish behavior when `autocommit` is enabled versus when multiple statements are inside the same transaction.
- Understand how shared locks, record locks, gap locks, and next-key locks affect write operations.
- Identify scenarios where range queries can block INSERTs and cause lock waits.
- Evaluate the impact of indexes, access order, and transaction duration on concurrency.
- Compare `SERIALIZABLE` with `REPEATABLE READ` and `READ COMMITTED` in InnoDB.
- Choose an isolation level based on consistency requirements, read/write load, and deadlock handling capability.
- Configure isolation levels in SQL and Java JDBC, and verify behavior using two sessions.

## 1. What Is SERIALIZABLE?

`SERIALIZABLE` is the highest isolation level among the four standard isolation levels provided by InnoDB. Its goal is to make the outcome of concurrent transactions equivalent to some serial execution order: each transaction can be viewed as running completely before or after another transaction, rather than producing results unexplainable by any serial order.

This level aims to prevent anomalies such as:

- **Dirty read:** reading data written by another transaction that has not committed yet.
- **Non-repeatable read:** reading the same row multiple times in one transaction and receiving different values because another transaction committed changes.
- **Phantom read:** rerunning a range condition and seeing matching rows appear or disappear because another transaction executed INSERT/DELETE.
- Read/write outcomes that cannot be ordered into a valid serial schedule.

In return, `SERIALIZABLE` typically requires more locks, makes conflicting transactions wait on one another, and reduces concurrency. It does not mean MySQL only allows one transaction to run on the entire server at a time. Transactions can still run in parallel if they do not conflict on the data or resources requiring locks.

## 2. How Does SERIALIZABLE Work in InnoDB?

InnoDB uses MVCC for consistent reads and locking mechanisms for locking reads, UPDATE, DELETE, and other operations needing data protection. At lower isolation levels, an ordinary plain `SELECT` can read from a snapshot without locking the rows being read.

With `SERIALIZABLE`, the behavior of a plain `SELECT` changes depending on how the transaction is used:

- When `autocommit` is disabled or the statement is inside an explicit transaction, InnoDB implicitly converts a plain `SELECT` into a locking read equivalent to `SELECT ... FOR SHARE`.
- When `autocommit = 1` and a plain `SELECT` is its own sole transaction, that read statement is an isolated read-only transaction; InnoDB can serialize this read transaction without holding shared locks across multiple statements.

This is a critical point when testing `SERIALIZABLE`: merely setting the isolation level and running a single standalone SELECT statement does not demonstrate the locking behavior of a multi-statement transaction. To test locking impact in a transaction, start an explicit transaction.

### 2.1. Plain SELECT in an Explicit Transaction

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;

-- Under SERIALIZABLE, this plain SELECT behaves as a shared locking read.
SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Other business statements...

COMMIT;
```

The shared lock is held for the lifetime of the transaction. Other transactions can still read the same row using shared locks, but operations needing an exclusive lock such as UPDATE/DELETE on that row must wait until the shared lock is released.

### 2.2. Comparison with REPEATABLE READ

With `REPEATABLE READ` (InnoDB's common default level), a plain `SELECT` is a consistent read and reads from the transaction's snapshot. Ordinary reads in the same transaction see the same snapshot, without placing shared locks on rows just for reading them.

With `SERIALIZABLE`, a plain `SELECT` inside an explicit transaction is converted into a shared locking read. Therefore, a reading transaction can block a transaction writing to the rows or ranges it locks.

Do not think `REPEATABLE READ` has no locks: `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, UPDATE, and DELETE still use locks according to InnoDB rules. The primary difference here is how plain SELECTs are handled.

## 3. Configuring the SERIALIZABLE Isolation Level

MySQL lets you set the isolation level at different scopes. Configure it before starting the transaction.

### 3.1. Checking the Current Level

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.autocommit AS session_autocommit;
```

`SESSION` is the value applied to the current connection. `GLOBAL` is the default value for new connections; changing GLOBAL does not automatically change the isolation level of already open sessions.

### 3.2. Setting the Default for the Current Session

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;
SELECT * FROM accounts WHERE account_id = 101;
COMMIT;
```

Subsequent transactions on the current connection use `SERIALIZABLE` until the session's isolation level is changed.

### 3.3. Setting Only for the Next Transaction

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

`SET TRANSACTION` without `GLOBAL` or `SESSION` sets characteristics for the next transaction. This is a good choice when only one unit of business work needs an isolation level different from the connection's default.

### 3.4. Setting the Server-Wide Default

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

This operation affects sessions created afterward and requires appropriate administrative privileges. Do not change GLOBAL just to handle a single query. If changing the server default, assess the impact on the entire workload and how applications open connections.

### 3.5. Do Not Change Isolation Level Mid-Transaction

Set the isolation level before `START TRANSACTION`. MySQL does not allow changing transaction characteristics once a transaction has started. If a different level is needed, end the current transaction with `COMMIT` or `ROLLBACK`, then configure it for the next transaction.

The variable name `transaction_isolation` is used in MySQL 8.0; some older versions use the deprecated `tx_isolation` name. Always verify the target server version.

## 4. Shared Locks and Impact on Write Operations

In a `SERIALIZABLE` transaction, a plain SELECT is treated as a shared locking read. A shared lock allows other transactions to hold compatible shared locks on that data simultaneously, but conflicts with the exclusive lock required by write operations.

Session A example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Not COMMITted or ROLLBACKed yet; shared lock is still held.
```

Meanwhile, Session B:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

The UPDATE in Session B needs an exclusive lock on the account row. It must wait for Session A to finish its transaction and release the shared lock.

When Session A runs:

```sql
COMMIT;
```

Session B can then proceed, depending on transaction state and other locks.

### 4.1. Shared Locks Do Not Block All Read Operations

Multiple shared locks can coexist on the same row. Thus, one reading transaction does not necessarily block another reading transaction. Conflicts primarily arise when another transaction needs an exclusive lock to modify a row or needs to lock a range protected by the current transaction.

### 4.2. Two Transactions Both Read and Then Both Try to Write

A classic deadlock-prone scenario:

1. Session A reads row X and holds a shared lock.
2. Session B also reads row X and holds a shared lock.
3. Session A wants to UPDATE X and needs to upgrade to an exclusive lock, but must wait for B's shared lock.
4. Session B also wants to UPDATE X, but must wait for A's shared lock.

InnoDB detects the deadlock and rolls back one transaction as the victim. If you know from the outset that the business flow will read and then modify a row, consider an explicit locking read with `SELECT ... FOR UPDATE` instead of both transactions acquiring shared locks and then attempting to write.

`FOR UPDATE` also increases contention; only use it when reading and updating in the same transaction is genuinely needed.

## 5. Gap Locks and Next-Key Locks: Why Can INSERTs Be Blocked?

To prevent phantom reads, InnoDB can lock not only existing index records but also the gaps between records during a range scan.

- **Record lock:** locks a single index record.
- **Gap lock:** locks a gap between index records, preventing other transactions from inserting index records into that gap.
- **Next-key lock:** combines a lock on an index record with a lock on the gap immediately preceding that record.

In locking reads under `REPEATABLE READ` and `SERIALIZABLE`, InnoDB can use next-key locks for index range scans. This protects the query's condition range against additional matching rows appearing before the transaction ends.

### 5.1. Range Query Example

Suppose we have a table:

```sql
CREATE TABLE products (
    product_id BIGINT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_price (price)
) ENGINE = InnoDB;
```

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT product_id, price, product_name
FROM products
WHERE price >= 100
  AND price < 200
ORDER BY price, product_id;

-- Keep transaction open to observe locks.
```

Because Session A is under `SERIALIZABLE` in an explicit transaction, the plain SELECT acts as a shared locking read. With an access path using the `idx_products_price` index, InnoDB can lock records and gaps associated with the scanned range.

Session B tries to add a product whose price falls in the range:

```sql
INSERT INTO products (product_id, price, product_name)
VALUES (90001, 150, 'New product');
```

The INSERT may have to wait because it needs to insert an index record into a gap locked by Session A. After Session A executes `COMMIT` or `ROLLBACK`, Session B can proceed if no other conflicts remain.

The exact lock scope depends on the execution plan, chosen index, and existing values. This example illustrates the mechanism; when testing in a real environment, inspect the actual indexes and lock state.

### 5.2. Unique Key Lookup Differs from Range Scan

If a query uses an equality condition on an entire unique index to locate a single record, InnoDB typically only needs a record lock on the found record, without locking the gap before it.

Example:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 101;
```

If `account_id` is the primary key, the query is a unique point lookup. It typically has a narrower lock footprint than a range scan on a non-unique column.

Conversely, a condition such as:

```sql
SELECT product_id, price
FROM products
WHERE price BETWEEN 100 AND 200;
```

can scan many index records and their associated gaps. If the `price` column is non-unique, a single value can match multiple products.

Do not deduce locks from the SQL text alone. Inspect which index the optimizer uses and which index records/gaps InnoDB actually locked.

## 6. Indexes Determine Lock Scope and Concurrency

Indexes do not only affect query speed. For locking reads and write operations, the access path can significantly affect how many records and gaps InnoDB must lock.

### 6.1. Suitable Indexes Enable More Precise Locking

Suppose a query frequently reads ranges by `warehouse_id` and `product_id`:

```sql
SELECT product_id, quantity
FROM inventory
WHERE warehouse_id = 10
  AND product_id BETWEEN 1000 AND 1100;
```

A suitable index could be:

```sql
CREATE INDEX idx_inventory_warehouse_product
ON inventory (warehouse_id, product_id);
```

The composite index helps InnoDB locate the range pertaining to a single warehouse and product range. Without a suitable index, the optimizer may have to scan more records, enlarging the lock scope and increasing the chance of blocking unrelated transactions.

Index column order must be based on filter predicates, selectivity, and actual queries. Do not create indexes blindly from an example; verify with `EXPLAIN` and measure workload.

### 6.2. Excessive Indexes Also Have Costs

Adding indexes helps queries locate rows more efficiently, but increases storage usage, INSERT/UPDATE/DELETE overhead, and the number of structures to maintain. Create indexes for important access paths, not every conceivable column combination.

### 6.3. Inspecting the Access Path

```sql
EXPLAIN
SELECT product_id, price, product_name
FROM products
WHERE price >= 100
  AND price < 200
ORDER BY price, product_id;
```

Observe `key`, `type`, estimated rows, and the filtered condition. If the server supports it, `EXPLAIN FORMAT=TREE` can help read the execution flow. `EXPLAIN ANALYZE` actually runs the query, so only use it with appropriate statements and environments.

## 7. SERIALIZABLE Prevents Phantoms but Can Cause Lock Waits

A phantom read occurs when a transaction reruns a query with the same range condition and sees matching rows appear or disappear due to another transaction modifying that set of rows.

Example business flow checking available slots:

```sql
SELECT reservation_id
FROM reservations
WHERE room_id = 20
  AND reserved_at >= '2026-12-01'
  AND reserved_at < '2026-12-02';
```

If business logic relies on the existing row count to decide whether a new reservation can be added, merely reading a snapshot without locking the range may be insufficient. Inside a `SERIALIZABLE` transaction, shared locking reads and next-key locking can prevent another transaction from inserting matching records into the protected range.

However, range locking can cause independent booking requests that sit near each other in the same index to wait. If index design is poor, the lock footprint can be larger than expected.

### 7.1. SERIALIZABLE Does Not Replace Business Constraints

If a rule can be expressed with a unique key or constraint, use constraints to enforce protection at the database level. For example, if each user can only have one reservation for a unique slot, a unique index on the appropriate identifying columns can be a more direct layer of protection.

Not every anti-duplication rule can be expressed as a unique key, especially with overlapping time intervals. In such cases, combine transactions, locking strategies, data modeling, and appropriate business checks.

### 7.2. Consider Explicit Locking Reads at Lower Levels

If only one part of a workflow needs range locking or row locking, you can keep the default isolation level and use `SELECT ... FOR UPDATE` or `SELECT ... FOR SHARE` at the exact spot needed. This lets you explicitly choose the locking read scope instead of turning every plain SELECT in the transaction into a shared locking read.

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Check and update the same row inside the transaction.

COMMIT;
```

This option is not strictly equivalent to `SERIALIZABLE` for all queries and all anomalies. It fits when the application can pinpoint the exact data requiring locks.

## 8. Impact on Concurrency and Performance

`SERIALIZABLE` generally reduces concurrency compared to `REPEATABLE READ` because plain SELECTs in explicit transactions hold shared locks. The impact depends on data overlap and how long transactions remain open.

Common consequences:

- UPDATE/DELETE must wait when rows are held under shared locks by another transaction.
- INSERT may wait when needing to insert into a locked gap.
- Transactions reading the same data can hold shared locks simultaneously.
- Transactions that read and then switch to writing can hit deadlocks due to lock upgrades.
- Long transactions hold locks longer, increasing lock waits and reducing throughput.
- Broad range scans or missing indexes can lock more records/gaps than necessary.
- Many transactions accessing the same hot index region can form wait queues.

### 8.1. SERIALIZABLE Does Not Mean Locking the Entire Database

InnoDB locks records and index ranges per access path, rather than placing a server-wide mutex by default. Two transactions operating on independent rows can still run concurrently. However, a broad range scan or missing index can create a large lock scope and affect transactions that are unrelated at the business level.

### 8.2. Keep Transactions Short

Example of what not to do:

1. Open a `SERIALIZABLE` transaction.
2. Read many rows and hold shared locks.
3. Call an HTTP service or wait for user confirmation.
4. Update and commit several seconds later.

During the wait, write operations can be blocked. Perform calculations or external service calls before opening the transaction when safe; then open a short transaction, re-read/lock the required data, verify conditions, and write.

Do not move read steps outside the transaction if doing so breaks consistency guarantees. Redesign the workflow so that the part needing protection is still verified inside a short transaction.

### 8.3. Monitor Lock Waits and Deadlocks

When a system uses `SERIALIZABLE`, monitor:

- Lock wait times and lock wait timeout rates.
- Deadlock counts and rolled-back transactions.
- Long-lived transactions and connections holding open transactions.
- Range-scan queries touching large row counts.
- Chosen indexes and execution plan changes as data grows.

You can investigate using `SHOW ENGINE INNODB STATUS` and the `performance_schema` tables related to data locks/lock waits on supported versions. Appropriate privileges are required, and you must pick the right observability tools for the server version.

## 9. Comparing SERIALIZABLE, REPEATABLE READ, and READ COMMITTED

| Aspect | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Ordinary plain SELECT | Consistent read with per-statement snapshot | Consistent read with transaction snapshot | In an explicit transaction, converted to a shared locking read |
| Re-reading the same row | Can see new commits in later statements | Typically keeps the same snapshot within the transaction | Read locks force conflicting write transactions to wait |
| Phantoms with plain consistent read | Can see a different row set in later statements | Transaction snapshot keeps the visible set stable | Range locks in locking reads prevent phantom changes in the scanned range |
| Gap/next-key locking | Reduced gap locking for many ordinary operations; exceptions remain such as FK/duplicate checks | Used in many locking reads and write operations | Used for locking reads resulting from plain SELECTs inside a transaction |
| Concurrency | Generally higher | Balances consistency and concurrency | Generally lower when multiple transactions read/write the same data region |
| Suitable use cases | Workloads needing fresh data per statement and high concurrency | Common OLTP workloads needing a stable snapshot within a transaction | Business flows requiring strict serial order and tolerating locking overhead |

The table above describes common InnoDB behavior. Exact locking details depend on statement type, indexes, access paths, isolation level, autocommit, and MySQL version.

## 10. Two-Session Practical Verification

The following lab lets you observe how a plain SELECT under `SERIALIZABLE` holds shared locks and can block UPDATE/INSERT.

### 10.1. Prepare the Data

Run once in a test schema:

```sql
DROP TABLE IF EXISTS serializable_demo;

CREATE TABLE serializable_demo (
    item_id BIGINT NOT NULL,
    item_value INT NOT NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_item_value (item_value)
) ENGINE = InnoDB;

INSERT INTO serializable_demo (item_id, item_value, description)
VALUES
    (1, 10, 'A'),
    (2, 20, 'B'),
    (3, 30, 'C'),
    (4, 40, 'D');
```

### 10.2. Session A: Read and Hold the Transaction

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT item_id, item_value, description
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

Keep Session A open without committing yet.

### 10.3. Session B: Try Updating a Row Being Read

Open another connection and run:

```sql
UPDATE serializable_demo
SET description = 'Changed'
WHERE item_id = 2;
```

The UPDATE may be blocked because Session A holds a shared lock on the matching row. While Session B is waiting, return to Session A:

```sql
COMMIT;
```

Once Session A commits, Session B can proceed.

### 10.4. Try INSERTing into the Read Range

Repeat Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT item_id, item_value
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

In Session B:

```sql
INSERT INTO serializable_demo (item_id, item_value, description)
VALUES (5, 25, 'Inserted in range');
```

If the access path uses the `idx_item_value` index and the corresponding gap range is locked, the INSERT may wait for Session A to end its transaction. After `COMMIT` or `ROLLBACK` in Session A, verify Session B proceeds and the row is inserted.

Detailed results depend on access paths and indexes. Use `EXPLAIN` before testing and do not run practice exercises on production data.

### 10.5. Comparison with REPEATABLE READ

Set Session A back to `REPEATABLE READ`, then run the plain SELECT inside a transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT item_id, item_value
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

A plain consistent read under `REPEATABLE READ` does not acquire shared locks just for reading. Session B can typically UPDATE rows or INSERT new matching values without waiting on a plain SELECT's shared lock. Session A continues reading from its snapshot within the transaction.

End Session A with `COMMIT` or `ROLLBACK` before repeating another test.

## 11. Using SERIALIZABLE in Java JDBC

JDBC provides the `Connection.TRANSACTION_SERIALIZABLE` constant to request an isolation level for a connection:

```java
try (Connection connection = dataSource.getConnection()) {
    int originalIsolation = connection.getTransactionIsolation();
    boolean originalAutoCommit = connection.getAutoCommit();
    boolean reusable = false;
    Throwable primaryFailure = null;

    try {
        connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
        connection.setAutoCommit(false);

        // All business statements use the same connection.
        // Read, verify conditions, and write required data.

        connection.commit();
        reusable = true;
    } catch (SQLException | RuntimeException ex) {
        primaryFailure = ex;
        try {
            connection.rollback();
            reusable = true;
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        if (reusable) {
            try {
                connection.setAutoCommit(originalAutoCommit);
                connection.setTransactionIsolation(originalIsolation);
            } catch (SQLException resetError) {
                poolAdapter.invalidate(connection);
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(resetError);
                } else {
                    throw resetError;
                }
            }
        } else {
            poolAdapter.invalidate(connection);
        }
    }
}
```

`poolAdapter.invalidate(connection)` in the example is an illustrative call to the active pool's connection eviction API; it is not a standard JDBC API. If rollback fails, do not reset `autocommit` by turning it back on because that operation could commit a transaction in an indeterminate state. Discard the connection before it is returned to the pool. If resetting attributes fails, evict the connection as well. When `commit()` throws an error due to connection loss, the commit status may be uncertain; use an idempotency key or a way to query business state before retrying.

### 11.1. Use SERIALIZABLE Only for Transactions That Need It

You do not need to set every application connection to `SERIALIZABLE`. You can keep the standard isolation level for most of the workload and only raise isolation for transactions with clear requirements.

For example, a business operation checking multiple rows in a range before deciding to write may need to evaluate `SERIALIZABLE`; ordinary product-listing read queries usually do not need to hold shared range locks across the transaction.

### 11.2. Handling Deadlocks and Timeouts

Applications must be prepared for concurrency errors:

- If InnoDB detects a deadlock, one transaction is chosen as the victim and rolled back.
- If a lock wait timeout occurs, rollback scope depends on configuration; the application should roll back the entire transaction before retrying or returning the connection to the pool.
- Only retry when the business operation is safe to re-execute; use an idempotency key or unique request identifier if duplicate operations could occur.
- Retry the entire transaction on a clean connection, with bounded attempts and appropriate backoff.

Do not retry infinitely. If errors repeat, examine lock ordering, indexes, transaction duration, and the data model.

## 12. When Should You Choose SERIALIZABLE?

`SERIALIZABLE` fits when business correctness requirements are difficult to guarantee with constraints or narrower locking strategies, and the system accepts the concurrency cost.

Consider it when:

- A write decision depends on the result of a range query and you must prevent other transactions from altering that set of rows before commit.
- A business rule spans multiple rows and cannot be fully expressed with a unique constraint or a single atomic update.
- Result correctness outweighs maximum throughput and data contention is relatively low.
- Lock waits, deadlocks, and throughput have been tested under representative load.

Do not choose it merely to feel "safer" without identifying the anomaly to prevent. For many workflows, the following options can be more effective:

- Unique keys or CHECK constraints to enforce invariants directly.
- Conditional UPDATEs, such as `UPDATE ... WHERE quantity >= ?`.
- `SELECT ... FOR UPDATE` to lock rows that need to be read and then modified.
- `SELECT ... FOR SHARE` when an explicit shared locking read is needed.
- `REPEATABLE READ` with consistent snapshots when only stable reads are required.
- Redesigning transactions to shrink data scope and lock hold time.

## 13. Common Misconceptions

| Misconception | Reality | How to Handle |
|---|---|---|
| SERIALIZABLE locks the entire database | InnoDB locks records/index ranges per access path; independent data can still process concurrently | Inspect lock scope and actual queries |
| Every SELECT in SERIALIZABLE always locks | With autocommit enabled, a standalone SELECT is a read-only transaction and does not need to hold locks across statements | Check autocommit and use explicit transactions when testing locking behavior |
| Shared locks block all read transactions | Shared locks are compatible with other shared locks | Distinguish read-read conflicts from read-write conflicts |
| SERIALIZABLE only locks existing rows | Range scans can take next-key/gap locks to prevent phantom INSERTs | Check indexes and range conditions |
| Having an index eliminates lock waits | Indexes narrow the access path, but protected records/gaps can still contend | Design indexes and transactions around business needs |
| SERIALIZABLE eliminates deadlocks | Shared lock upgrades, differing lock orders, and multiple transactions can still create deadlocks | Handle deadlocks and retry the full transaction |
| REPEATABLE READ does not use gap locks | Locking reads and write operations under REPEATABLE READ can still use next-key locks | Distinguish plain consistent reads from locking reads |
| Raising isolation level alone suffices to protect invariants | Isolation does not replace constraints, business checks, and idempotency | Use appropriate defense in depth |

## 14. Evaluation Checklist Before Enabling SERIALIZABLE

1. **Describe the anomaly to prevent:** dirty read, non-repeatable read, phantom, or a write decision based on a range of data?
2. **Check constraints:** can a unique key, CHECK, or conditional UPDATE protect the invariant?
3. **Determine transaction scope:** which SELECT statements need protection and until when must the transaction hold locks?
4. **Check autocommit:** standalone plain SELECTs and SELECTs in explicit transactions behave differently.
5. **Inspect indexes and access paths:** which records/gaps might a range scan lock; does a missing index widen the scan scope?
6. **Simulate with two sessions:** test reads, UPDATEs, and INSERTs across overlapping lock regions.
7. **Measure under load:** track throughput, latency, lock wait timeouts, and deadlocks.
8. **Design retries:** roll back failed transactions and perform bounded retries of the entire business unit.
9. **Roll out narrowly:** raise isolation only for necessary transactions and monitor before expanding.

## 15. Production Checklist

- [ ] Identified the specific data anomaly to prevent.
- [ ] Confirmed participating tables use InnoDB.
- [ ] Isolation level is set before the transaction begins.
- [ ] Verified `@@SESSION.transaction_isolation` and `@@SESSION.autocommit`.
- [ ] Understood that plain SELECT inside an explicit transaction under SERIALIZABLE is a shared locking read.
- [ ] Accounted for autocommit behavior of standalone SELECTs.
- [ ] Range queries have suitable indexes and lock footprints have been inspected.
- [ ] Assessed the possibility of gap/next-key locks blocking INSERTs.
- [ ] Transactions are short and do not wait on HTTP calls, users, or external non-database tasks while holding locks.
- [ ] Implemented handling for deadlocks, lock wait timeouts, and bounded retries.
- [ ] Compared against REPEATABLE READ, explicit locking reads, or constraints.
- [ ] Measured throughput and latency under representative workloads.
- [ ] Connections reset isolation/autocommit or are evicted from the pool if reset fails.

## 16. Conclusion

`SERIALIZABLE` requires transactions to produce results equivalent to a serial execution order. In InnoDB, when `autocommit` is disabled or a plain SELECT is inside an explicit transaction, ordinary SELECTs are converted into shared locking reads. For range queries, InnoDB can use next-key/gap locks to prevent phantom INSERTs. When autocommit is enabled and a SELECT is a standalone read transaction, that read can be serialized without holding locks across multiple statements.

This isolation level strengthens consistency guarantees but also increases lock waits, deadlocks, and concurrency overhead. Indexes determine access paths and lock scope; long transactions prolong contention. Choose `SERIALIZABLE` when business requirements genuinely demand it, test with multiple sessions, prefer constraints or narrower locking strategies when sufficient, and measure performance before broad adoption.
