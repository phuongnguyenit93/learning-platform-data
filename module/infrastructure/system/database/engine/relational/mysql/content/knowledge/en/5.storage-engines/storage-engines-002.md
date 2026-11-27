# InnoDB and its transactional features

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privileges, backups, and operations. InnoDB is the default storage engine in modern MySQL and is the standard choice for applications requiring safe transactions. This engine combines index structures, lock management, MVCC, redo/undo logs, and crash recovery mechanisms to protect data when multiple sessions operate concurrently.

This lesson focuses on how InnoDB stores data, executes transactions, coordinates concurrent access, and maintains durability. Understanding these mechanisms helps you design appropriate tables, write concise transactions, handle deadlocks, and configure the server according to data safety requirements.

## 1. The role of InnoDB

MySQL separates the SQL layer from the storage engine. The SQL layer receives statements and builds execution plans; the storage engine performs read, write, locking, and storage operations according to its capabilities. InnoDB provides essential features for transactional systems:

- Transactions adhering to ACID properties.
- Row-level locking along with necessary range locks to protect queries.
- Multi-Version Concurrency Control (MVCC) for consistent reads.
- Primary keys organized as clustered indexes, and secondary indexes based on the primary key.
- Foreign keys and referential constraint enforcement.
- Redo logs, undo logs, doublewrite, and crash recovery.
- A buffer pool to cache data and index pages.

Check a table's engine:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

Or view the table definition:

```sql
SHOW CREATE TABLE orders;
```

Do not assume every table in a schema uses InnoDB. Some older tables may use another engine; transaction, locking, and foreign key capabilities depend on each table's actual engine.

## 2. ACID and transactions

A transaction groups one or more operations into a single unit of work. With InnoDB, transactions help applications protect related changes together.

| Property | Meaning | Example in an e-commerce system |
|---|---|---|
| Atomicity | Changes within a transaction are committed together or rolled back | Deducting inventory and creating an order must succeed together |
| Consistency | A valid transaction must preserve data constraints | Inventory quantity cannot be negative if an appropriate constraint exists |
| Isolation | Concurrent transactions must not observe intermediate states that violate the chosen isolation level | Two transactions must not arbitrarily overwrite the same balance |
| Durability | After a successful commit, changes are protected according to durability settings | A confirmed order must persist after the server restarts |

ACID is the goal of transactions, but Consistency also depends on application logic and declared constraints. For example, InnoDB cannot automatically understand a business rule such as "each customer may have at most three orders in progress" if that rule has not been modeled with appropriate constraints or transaction logic.

### 2.1. Autocommit

By default, MySQL typically enables `autocommit`. When enabled, each successful statement creates and commits its own transaction if no explicit transaction is open.

```sql
SELECT @@autocommit;
```

Disable autocommit for the current session:

```sql
SET autocommit = 0;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501;

COMMIT;
```

When `autocommit = 0`, subsequent statements can remain inside a transaction until committed or rolled back. Manage this state carefully in connection pools; when returning a connection to the pool, the application must ensure the transaction has ended and the session state is restored.

### 2.2. Explicit transactions

A transaction can be started with `START TRANSACTION` or `BEGIN`:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 250000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 250000
WHERE account_id = 202;

COMMIT;
```

If an operation fails to meet a business condition, the application can cancel everything:

```sql
ROLLBACK;
```

Only call `COMMIT` after all required steps succeed. If you update a balance without checking the affected row count or verifying sufficient funds, the transaction can still commit a business-invalid result even though the SQL syntax is valid.

### 2.3. Savepoints

A savepoint marks a position within a transaction for partial rollback:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

SAVEPOINT after_order_update;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 501;

-- If you need to cancel only the inventory update:
ROLLBACK TO SAVEPOINT after_order_update;

-- Continue processing or cancel the entire transaction.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` does not end the transaction. Savepoints are useful when part of a workflow can be retried or canceled independently, but they do not replace clear transaction design. Savepoints are released when the transaction ends; `RELEASE SAVEPOINT` can be used to remove a marker that is no longer needed.

### 2.4. DDL and transaction boundaries

Not every SQL statement participates in transactions the same way `INSERT`, `UPDATE`, or `DELETE` do. Many DDL statements, such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE`, trigger an implicit commit under MySQL's rules. Do not mix schema changes with business transactions and expect a `ROLLBACK` to undo all DDL. Before running DDL in a shared environment, check implicit commit rules and metadata locking impacts.

## 3. InnoDB storage and index structures

### 3.1. Pages and B-trees

InnoDB organizes data in pages. The default page size is typically 16 KB, though it can be specified at instance initialization and is not an arbitrary setting that can be changed for an existing table. Pages are linked in B-tree index structures for efficient key-based lookup.

A page is the unit of data that InnoDB manages in the buffer pool and reads/writes with storage. A query may require one or more pages depending on the access path, row size, fragmentation, and number of rows that must be read.

### 3.2. Clustered index

In InnoDB, table data is stored in the clustered index. Typically:

- If a table has a `PRIMARY KEY`, the primary key is used as the clustered index.
- If no primary key is declared, InnoDB selects the first `UNIQUE` index whose columns are all `NOT NULL` as the clustered index, if available.
- If neither exists, InnoDB creates a hidden clustered index with an internal row ID.

Because rows are organized by the clustered key, lookups by primary key generally go directly to the record. A primary key should be short, stable, and unique. Changing a primary key can trigger updates to secondary indexes because the primary key is stored in every secondary index entry.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
```

### 3.3. Secondary indexes

A secondary index is a separate B-tree containing the indexed columns along with the primary key value to locate the row in the clustered index. When a query only needs columns already present in the secondary index, InnoDB can use a covering index and avoid reading the full record again.

Example:

```sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date);
```

This composite index can support queries filtering by `customer_id` and sorting or further filtering by `order_date` under certain conditions. The leftmost prefix rule means queries typically leverage the leading part of the index; an index on `(customer_id, order_date)` is not equivalent to an index on `order_date` alone.

Do not create an index on every column. Each index consumes disk space, increases the cost of `INSERT`, `UPDATE`, and `DELETE`, and adds maintenance overhead. Design indexes from actual queries, then verify using `EXPLAIN` and operational metrics.

### 3.4. Tablespaces

InnoDB stores pages in tablespaces. Common types include:

| Tablespace | Role |
|---|---|
| System tablespace | Stores InnoDB system data and may hold user data depending on configuration |
| File-per-table tablespace | Each table has its own tablespace, typically an `.ibd` file |
| General tablespace | A single tablespace that can hold multiple specified tables |
| Undo tablespace | Stores undo records for rollback and MVCC |
| Temporary tablespace | Serves InnoDB temporary data |

With `innodb_file_per_table` commonly enabled, new InnoDB tables usually have their own tablespace file. Dropping a table can reclaim its corresponding tablespace file, whereas the size of the system tablespace does not necessarily shrink automatically after internal data is deleted. Tablespace administration requires monitoring disk usage, paths, and storage planning.

## 4. Buffer pool and the data path

The buffer pool is a RAM area used to cache data and index pages. When a page is needed, InnoDB looks for it in the buffer pool; if not present, the engine reads the page from the tablespace. Modified pages are marked dirty and written to disk by background threads through checkpoint and flushing mechanisms.

Related components:

- **Free list:** unused pages available to receive new data.
- **LRU list:** manages cached pages under a least-recently-used policy, tuned to prevent large scans from evicting all hot pages from the cache.
- **Flush list:** tracks dirty pages that need to be written to storage.
- **Read-ahead:** can prefetch pages when sequential access or matching access patterns are detected.

The buffer pool helps reduce physical I/O when the working set fits in memory. Increasing `innodb_buffer_pool_size` is not a cure-all for every slow query: if a query scans too many rows, lacks suitable indexes, or CPU is saturated, adding RAM may not yield significant improvement.

View buffer pool configuration and status variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool%';
```

Compare counters over time intervals and actual traffic rather than reading a single point-in-time snapshot. Also leave memory for the operating system, connections, sorts, temporary tables, and other services on the host.

## 5. Undo logs and MVCC

### 5.1. Undo logs

The undo log stores information needed to revert changes and construct older row versions for consistent reads. When a transaction updates a row, InnoDB records undo information before or alongside the update so it can roll back if the transaction does not commit.

Undo records are organized into version chains. Consistent reads use a read view to determine which version is visible. Once no active transaction needs an older version, purge threads can clean up obsolete undo records.

Long-running open transactions can hold old read views, preventing purge from cleaning up certain versions and causing undo history to grow. Therefore, do not open a transaction and leave a connection idle for a long time.

### 5.2. MVCC and consistent reads

MVCC allows regular read queries to read a logical snapshot without necessarily locking rows being updated by other transactions. In InnoDB, consistent nonlocking read is the default behavior for regular `SELECT` queries under isolation levels that support snapshots.

For example, transaction A reads a balance at a point in time; transaction B updates and commits the balance. Transaction A can continue seeing the old version according to its read view, depending on the isolation level and when the read view was created. This enables concurrent reads and writes with reduced contention.

MVCC does not mean every read query is lock-free. `SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking reads; they acquire locks to coordinate with write operations. `UPDATE` and `DELETE` operations must also lock affected records.

## 6. Isolation levels

InnoDB supports the four standard SQL isolation levels. The default in MySQL InnoDB is typically `REPEATABLE READ`.

| Isolation level | General behavior | Important considerations |
|---|---|---|
| `READ UNCOMMITTED` | Can read uncommitted data from other transactions | Risk of dirty reads |
| `READ COMMITTED` | Each consistent read creates a fresh snapshot at the start of the statement | The same transaction may see newly committed data between two reads |
| `REPEATABLE READ` | Consistent reads within a transaction generally use the same read view created at the first consistent read | InnoDB uses next-key locking for certain locking reads and range operations to prevent phantoms where needed |
| `SERIALIZABLE` | Increases isolation; in an uncommitted transaction, plain SELECTs may be converted into locking reads depending on autocommit | Lower concurrency and potentially higher lock waits |

Set the isolation level for a session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Check the configuration:

```sql
SELECT @@transaction_isolation;
```

Choose the isolation level based on business requirements. Do not lower the isolation level just to reduce lock waits without understanding the data anomalies the application might observe. Under `READ COMMITTED`, each consistent read gets a fresh snapshot, but locking reads and write operations can still hold locks.

## 7. Locking mechanisms in InnoDB

### 7.1. Record locks

A record lock locks a specific index record. `UPDATE`, `DELETE`, or locking reads can place record locks on the index records that need protection. InnoDB row locks are actually attached to index records; query predicates and the chosen index affect the range of records locked.

Example:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

COMMIT;
```

`FOR UPDATE` acquires the lock so the transaction can safely inspect and then update the row. Without a suitable index, the server may have to scan and lock more records than expected, increasing contention.

### 7.2. Gap locks and next-key locks

A gap lock locks the gap between index records, preventing other transactions from inserting records into that range. A next-key lock combines a record lock with a gap lock on the preceding gap. These range locks help InnoDB protect query predicates during certain locking reads or DML operations, especially under `REPEATABLE READ`.

For example, a transaction queries orders within a key range using `FOR UPDATE`; InnoDB can lock the index records and adjacent gaps to prevent another transaction from inserting rows that would alter the protected result set.

The exact lock scope depends on the isolation level, query type, index used, and predicate uniqueness. A lookup on a unique index with a unique matching condition may only require a record lock; a range query may require next-key locks. Do not deduce the exact number of locked rows from the SQL text alone; inspect execution plans and lock states when needed.

### 7.3. Intention locks

An intention lock is a table-level lock indicating that a transaction intends to acquire row-level locks. Common types are intention shared (`IS`) and intention exclusive (`IX`). They help InnoDB coordinate row locks with operations requiring table locks, such as `LOCK TABLES`, via a compatibility matrix.

### 7.4. Insert intention and AUTO-INC locks

An insert intention lock is a specialized form of gap lock used when inserting a record into an index position. It allows transactions to insert into different positions within the same gap without necessarily blocking each other.

An AUTO-INC lock relates to generating `AUTO_INCREMENT` values. Locking behavior depends on `innodb_autoinc_lock_mode` and the type of insert statement; do not assume every insert always locks the entire table in the same way.

## 8. Deadlocks and lock waits

### 8.1. What is a deadlock?

A deadlock occurs when transactions hold locks that others need, forming a wait cycle that cannot progress on its own. For example:

- Transaction A locks account row 10 and then requests a lock on account 20.
- Transaction B locks account row 20 and then requests a lock on account 10.
- A waits for B and B waits for A, creating a deadlock cycle.

InnoDB detects the deadlock and selects one transaction as the victim to roll back, allowing the remaining transaction to proceed. The application must catch the deadlock error and may retry the entire transaction under a bounded policy.

### 8.2. Example of two transactions creating a deadlock

Session A:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE account_id = 10;
-- Wait briefly for Session B to update row 20.
UPDATE accounts SET balance = balance + 10 WHERE account_id = 20;
```

Session B:

```sql
START TRANSACTION;
UPDATE accounts SET balance = balance - 20 WHERE account_id = 20;
-- Then update row 10.
UPDATE accounts SET balance = balance + 20 WHERE account_id = 10;
```

If each session locks its first row before the other updates that row, one of the subsequent operations can trigger deadlock detection. This experiment should only be run on lab tables.

### 8.3. Reducing deadlocks

- Update multiple rows in the same consistent order across all business flows, such as always ascending by primary key.
- Keep transactions short; do not wait on network calls, user input, or external processing while holding locks.
- Create appropriate indexes so statements locate exact rows and minimize scan/lock scope.
- Avoid updating the same set of rows in different orders across code paths.
- Implement application-level retries with bounded attempts, backoff, and appropriate idempotency guarantees.

A deadlock is not necessarily a configuration bug. A system with concurrent writes can encounter deadlocks; what matters is that transactions are designed to roll back and retry safely.

### 8.4. Investigating lock waits and deadlocks

Inspect waiting transactions and locks using Performance Schema tables, depending on the MySQL version:

```sql
SELECT *
FROM performance_schema.data_lock_waits;

SELECT *
FROM performance_schema.data_locks;
```

An overview of the most recent deadlock can be viewed with:

```sql
SHOW ENGINE INNODB STATUS\G
```

Locate the `LATEST DETECTED DEADLOCK` section to read the involved transactions, statements, and locks. If deadlock details need to be logged to the error log, consider `innodb_print_all_deadlocks`; enable it as needed for investigation while controlling log volume.

## 9. Foreign keys and referential integrity

InnoDB supports foreign keys to enforce relationships between parent and child tables. When inserting or updating a foreign key, the referenced value must match an indexed key in the parent table; when deleting or updating a key in the parent table, behavior depends on `ON DELETE` and `ON UPDATE`.

Example:

```sql
CREATE TABLE departments (
    department_id INT UNSIGNED NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE=InnoDB;

CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT UNSIGNED NULL,
    employee_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY ix_employees_department (department_id),
    CONSTRAINT fk_employees_department
      FOREIGN KEY (department_id)
      REFERENCES departments (department_id)
      ON UPDATE CASCADE
      ON DELETE SET NULL
) ENGINE=InnoDB;
```

Common actions:

- `RESTRICT` or `NO ACTION`: rejects operations that violate referential integrity; in InnoDB, `NO ACTION` behaves like `RESTRICT`.
- `CASCADE`: propagates updates or deletes to matching child rows.
- `SET NULL`: sets the foreign key column in the child table to `NULL`; that column must allow `NULL`.

Related columns must have compatible data types; for numeric types, attributes such as signed/unsigned must match. InnoDB requires an index on the foreign key column in the child table and can create one automatically if no suitable index exists. Even though foreign keys protect integrity, delete/update rules must still be designed carefully to avoid unintended cascades.

## 10. Redo log, doublewrite, and crash recovery

### 10.1. Redo log and write-ahead logging

The redo log records information needed to recover page modifications after a crash. Under write-ahead logging, log records must be durably written according to policy before the corresponding data pages are considered safe to write to their final locations. As a result, InnoDB does not need to flush every modified page immediately when a transaction commits.

On commit, InnoDB writes redo log entries according to the active flush policy. Dirty pages can be written to tablespaces later by background threads. Checkpoints mark how far changes have been written to storage, bounding the amount of redo that must be processed during crash recovery.

### 10.2. Doublewrite buffer

Doublewrite protects against partial page writes (torn pages) if the OS or server crashes while writing a page. InnoDB writes pages to the doublewrite area first before writing them to their final tablespace locations. During recovery, the intact page copy in doublewrite can be used to repair a torn page.

Doublewrite is not a backup and does not protect against accidental deletes, application logic bugs, or total storage device loss. Independent backups and tested restore procedures are still required.

### 10.3. Redo, undo, and binary logs

| Mechanism | Purpose | Scope |
|---|---|---|
| Undo log | Rollback and providing older versions for MVCC | InnoDB |
| Redo log | Recovering page changes after a crash | InnoDB |
| Binary log | Recording changes for replication and point-in-time recovery | MySQL Server |

The redo log does not replace the binary log. When point-in-time recovery is required, the procedure typically combines a suitable backup with complete binary logs retained after the backup point.

### 10.4. Durability configuration

Two configuration variables commonly require review:

```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN
  ('innodb_flush_log_at_trx_commit', 'sync_binlog');
```

`innodb_flush_log_at_trx_commit` controls how the redo log is written and flushed per transaction:

| Value | General behavior |
|---|---|
| `1` | Writes and flushes redo log to storage at every commit; typically the choice when prioritizing high durability |
| `2` | Writes redo log to the file at every commit, but flushes to storage on a background schedule; power loss or OS crash can lose the most recent unflushed transactions |
| `0` | Writes and flushes redo log on a background schedule; a crash can lose the most recent transactions even if only the MySQL process fails |

`sync_binlog=1` requires synchronizing the binary log after every transaction commit per MySQL rules; higher values or `0` change synchronization frequency and the durability/performance trade-off. End-to-end durability also depends on whether the operating system, filesystem, controller, and storage devices honor flush requests properly.

Do not lower durability settings in production solely to increase throughput. Define an acceptable RPO, verify storage hardware behavior, and test recovery before making changes.

## 11. InnoDB limitations and operational notes

- **Long transactions:** retain undo history and locks for extended periods, hindering purge or causing other transactions to wait.
- **Redundant indexes:** increase storage footprint and write overhead; review them against actual queries.
- **Overly wide primary keys:** enlarge secondary indexes because every secondary index entry includes the primary key.
- **Missing suitable indexes:** can force statements to scan many rows and lock broader ranges.
- **Deadlocks:** must be handled in the application with safe rollback/retry, alongside consistent update ordering.
- **Oversized buffer pool:** can starve the operating system of RAM needed for other operations.
- **Low durability settings:** can lose recent transactions during OS or server failures.
- **Untested backups:** having backups that cannot be restored remains an operational risk.

InnoDB helps protect transactions, but it cannot fix business logic bugs, prevent all application errors, or replace backup, monitoring, and disaster recovery plans.

## 12. Practice lab: testing InnoDB transactions and locking

Perform this in a lab database using two separate sessions. Create the test table:

```sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_lab_balance CHECK (balance >= 0)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES (1, 1000.00), (2, 500.00);
```

`CHECK` constraints are enforced starting in MySQL 8.0.16. If using an older version, do not rely on `CHECK` to protect balances; check the version and apply appropriate logic.

**Step 1 — Observe autocommit.** Run `SELECT @@autocommit;`. Execute a standalone `UPDATE` and check the change from a second session to see the default commit behavior.

**Step 2 — Test rollback.** Start a transaction, decrease account 1's balance, read it back in the same session, and then run `ROLLBACK`. Check from the other session to confirm the change was discarded.

**Step 3 — Test locking reads.** Session A runs:

```sql
START TRANSACTION;
SELECT balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;
```

Session B attempts to update the same row. Observe that Session B must wait until Session A commits or rolls back. End Session A with `ROLLBACK` to preserve the initial data.

**Step 4 — Observe isolation.** Choose `READ COMMITTED` or `REPEATABLE READ` for both sessions. In sequence, run a read query in Session A, update and commit from Session B, and then read again in A. Record how snapshots behave according to the isolation level and read view creation timing.

**Step 5 — Inspect lock status.** While a session is waiting, query `performance_schema.data_lock_waits` and `performance_schema.data_locks` if available, or use `SHOW ENGINE INNODB STATUS\G` to observe InnoDB status details.

**Step 6 — Test a controlled deadlock.** Use two rows and two sessions updating in opposite orders as in the deadlock example. Record the deadlock error, identify which transaction was rolled back, and perform a manual retry after ending the remaining transaction.

**Step 7 — Clean up lab data.** When finished, roll back any open transactions and drop the test table if no longer needed:

```sql
DROP TABLE lab_accounts;
```

**Expected outcomes:** be able to explain ACID, autocommit, commit/rollback, MVCC snapshots, row locking, and deadlocks; know how to inspect lock wait information and distinguish undo, redo, and binary logs.

## 13. Checklist for designing applications with InnoDB

1. Choose InnoDB for business tables requiring transactions, foreign keys, and crash recovery.
2. Declare short, stable primary keys and clearly define relationships between tables.
3. Design secondary indexes based on filter, join, and sort predicates of real queries.
4. Keep transactions short and terminate transactions in every success or error branch.
5. Update multiple rows in a consistent order to reduce deadlocks.
6. Choose isolation levels based on data requirements, not performance alone.
7. Monitor the buffer pool, long-running transactions, lock waits, deadlocks, and tablespace usage.
8. Configure redo/binlog durability policies according to RPO, then test backups and restores.

When you understand how InnoDB organizes pages, indexes, transactions, MVCC, and logs, you can design MySQL applications that are safer under concurrent access, handle transaction errors deliberately, and make operational decisions grounded in actual data requirements.
