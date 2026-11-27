# Shared locks, exclusive locks, and intention locks

When two employees process the same order or two transactions update the same inventory quantity concurrently, MySQL must coordinate access so that data is not overwritten unexpectedly. InnoDB accomplishes this using multiple lock types. The three foundational concepts are shared locks (S), exclusive locks (X), and intention locks (IS/IX).

A shared lock allows multiple transactions to read a record in locking mode simultaneously, while preventing other transactions from modifying that record. An exclusive lock reserves exclusive write access to a record and conflicts with both shared locks and other exclusive locks. Intention locks are placed at the table level to indicate that a transaction is currently locking or intends to lock records inside the table; they coordinate row-level locks with table-level locks.

Understanding the scope and compatibility of each lock helps you design safe transactions, reduce deadlocks, and investigate lock waits in MySQL systems.

## 1. What problem do locks in InnoDB solve?

One transaction may read or modify data while another transaction is also accessing the same data. Without a coordination mechanism, the following issues can occur:

- Two transactions deduct inventory concurrently and cause the quantity to go negative.
- One transaction reads a status and decides to update it while another transaction has already changed that status.
- One transaction reads a row for processing, but the row is deleted before the first transaction finishes.
- Transactions overwrite each other's changes or violate business rules.

InnoDB combines MVCC (Multi-Version Concurrency Control) and locking. MVCC allows multiple consistent reads to read the appropriate version without acquiring shared locks on rows. Locks are used when data must be protected during write operations or locking reads.

The S, X, IS, and IX locks covered in this lesson belong to InnoDB's locking mechanism. They differ from metadata locks (MDL), which protect table definitions during DDL execution, and from internal mutexes/latches, which protect the engine's in-memory structures.

## 2. Shared lock (S lock)

A shared lock, commonly denoted as S, is a shared lock on a record or index record. Multiple transactions can hold an S lock on the same record concurrently. While a transaction holds an S lock, another transaction cannot acquire an X lock on that record until the S locks are released.

Key points:

- Multiple transactions can simultaneously hold an S lock on a record.
- An S lock prevents other transactions from modifying or acquiring an exclusive lock on the same record.
- A transaction holding an S lock can still read the locked value.
- An S lock is typically used when you need to read a row and ensure it is not updated by another transaction before the current transaction ends.

### 2.1. Acquiring a shared lock with SELECT ... FOR SHARE

MySQL 8.0 supports the syntax:

    START TRANSACTION;

    SELECT id, status, total_amount
    FROM orders
    WHERE id = 1001
    FOR SHARE;

    -- Perform related read/validation steps.

    COMMIT;

FOR SHARE requests a shared lock on the index records read according to the execution plan; the actual scope may be broader than the final rows returned in the result set if the engine must scan additional records or ranges. The lock is held until the transaction commits or rolls back. Another transaction can also execute FOR SHARE on the same record, whereas UPDATE or SELECT ... FOR UPDATE must wait while the S lock remains held.

The older LOCK IN SHARE MODE syntax is still supported in MySQL 8.0 but is deprecated; FOR SHARE is the recommended syntax for modern locking reads.

### 2.2. Two transactions reading concurrently with a shared lock

Suppose sessions A and B both run:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Both A and B can acquire an S lock on the same record. Neither session has to wait for the other just because both are requesting an S lock. If session C runs:

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

The UPDATE statement requires an X lock and must wait until the S locks are released.

### 2.3. When should you use a shared lock?

Use FOR SHARE when a transaction needs to read a value and rely on that value across a multi-step workflow, while preventing other transactions from modifying the record before the workflow completes.

For example, a workflow that verifies a configuration before creating a dependent record may need to keep the configuration state stable during the transaction. However, you should not use an S lock for every SELECT. If you only need to read consistent data, InnoDB's consistent read is usually sufficient and causes less contention.

## 3. Exclusive lock (X lock)

An exclusive lock, denoted as X, is an exclusive lock on a record. When a transaction holds an X lock:

- Another transaction cannot acquire an S lock on the same record.
- Another transaction cannot acquire an X lock on the same record.
- The transaction holding the X lock can read and modify the record within its transaction.
- The X lock is held until the transaction commits or rolls back.

### 3.1. DML automatically acquires an exclusive lock

Data modification statements such as UPDATE, DELETE, and INSERT require appropriate locks to protect the changes. For example:

    START TRANSACTION;

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

    -- Subsequent business logic steps.

    COMMIT;

InnoDB acquires an X lock on the records/index records to be modified. Other transactions attempting to acquire an S or X lock on the same record must wait.

### 3.2. SELECT ... FOR UPDATE

If you need to read data before deciding to update it, you can acquire an X lock directly during the read step:

    START TRANSACTION;

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Check quantity in the application or stored routine.
    -- Update if conditions are met.

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

    COMMIT;

FOR UPDATE is a locking read that requests an exclusive lock on the accessed records. It prevents other transactions from modifying or acquiring shared locks on those records while the current transaction holds the lock.

When you know for sure that a transaction will read and then modify the same record, FOR UPDATE is generally preferable to acquiring FOR SHARE and later upgrading to an X lock. Upgrading a lock from S to X concurrently across multiple transactions can cause a deadlock.

### 3.3. An X lock does not mean locking the entire table

In InnoDB, an X lock typically locks only the necessary records/index records, rather than automatically locking the entire table. An UPDATE by primary key may lock only a single record, whereas an UPDATE with a range condition may lock multiple records or index ranges depending on the isolation level and execution plan.

Therefore, you cannot determine the lock scope just by looking at an UPDATE statement. You must consider the index used, the number of records scanned, range conditions, and the lock types placed by InnoDB.

## 4. Compatibility between S and X on the same record

The matrix below describes whether a new lock can be granted when another transaction already holds a lock on the same record:

| Lock currently held | New S request | New X request |
|---|---:|---:|
| S | Granted | Wait |
| X | Wait | Wait |

Interpretation:

- S with S is compatible: multiple transactions can perform locking reads concurrently.
- S with X is incompatible: X must wait for S to be released.
- X with S is incompatible: S must wait for X to be released.
- X with X is incompatible: only one transaction can hold an X lock on a record at a time.

Locks are released when the transaction ends via COMMIT or ROLLBACK. You should not assume a lock disappears immediately after a SELECT/UPDATE statement if the transaction remains open.

## 5. What is an intention lock?

An intention lock is a table-level lock indicating that a transaction intends to acquire or currently holds row locks inside the table. InnoDB uses two main types:

- **IS (Intention Shared):** the transaction intends to acquire or currently holds an S lock on a record in the table.
- **IX (Intention Exclusive):** the transaction intends to acquire or currently holds an X lock on a record in the table.

Before acquiring an S lock on a record, InnoDB places an IS lock at the table level. Before acquiring an X lock on a record, InnoDB places an IX lock at the table level.

An intention lock does not lock all rows in the table. It serves as a coordination signal between the row-level locking mechanism and operations requesting a table-level lock.

### 5.1. IS example

Transaction A:

    START TRANSACTION;

    SELECT *
    FROM orders
    WHERE id = 1001
    FOR SHARE;

InnoDB places an IS lock at the table level on orders and an S lock on the corresponding record. IS indicates that transaction A is using a shared row lock inside the table.

### 5.2. IX example

Transaction B:

    START TRANSACTION;

    UPDATE orders
    SET status = 'PROCESSING'
    WHERE id = 1001;

InnoDB places an IX lock at the table level on orders and an X lock on the record to be modified. IX indicates that transaction B is using an exclusive row lock inside the table.

Multiple transactions can hold IX on the same table simultaneously if they lock different records. This allows InnoDB to maintain row-level concurrency instead of forcing every write operation to lock the entire table exclusively.

## 6. Compatibility matrix of IS, IX, S, and X at the table level

At the table level, intention modes coordinate with table-level S/X locks as follows:

| Lock currently held | IS request | IX request | S request | X request |
|---|---:|---:|---:|---:|
| IS | Granted | Granted | Granted | Wait |
| IX | Granted | Granted | Wait | Wait |
| S | Granted | Wait | Granted | Wait |
| X | Wait | Wait | Wait | Wait |

Key points:

- IS and IX are mutually compatible. Multiple transactions can signal their intent to lock records simultaneously.
- A table-level S lock is compatible with IS because a shared table lock can coexist with shared row locks.
- A table-level S lock conflicts with IX because IX indicates a transaction needs an exclusive row lock.
- A table-level X lock conflicts with all other intention locks and table locks.

This matrix applies to InnoDB's table-level lock modes. It does not mean a regular SELECT statement acquires a table-level S lock; regular consistent reads do not acquire S row locks.

## 7. Why are intention locks needed?

Imagine transaction A holds an X lock on a record in the orders table. Transaction B requests a table-level S lock on the entire table. Without intention locks, the engine would have to inspect every single record to check whether any X row lock exists.

With IX, InnoDB already has a signal that transaction A holds or intends to hold an X lock inside the table. B's table-level S lock request conflicts with IX and must wait. This mechanism makes table-level compatibility checks much more efficient without scanning all row locks.

Intention locks are primarily managed automatically by the engine. Applications generally do not need to issue explicit statements to place IS or IX locks.

## 8. Distinguishing intention locks from row locks and table locks

| Lock type | Scope | Meaning |
|---|---|---|
| S record lock | Record/index record | Allows multiple transactions to perform locking reads, blocks other X locks |
| X record lock | Record/index record | Exclusive on the record, blocks other S/X locks |
| IS intention lock | Table | Signals that a transaction holds or intends to acquire an S row lock |
| IX intention lock | Table | Signals that a transaction holds or intends to acquire an X row lock |
| Table-level S/X | Table | Locks at the table scope, coordinated via the compatibility matrix |
| Metadata lock (MDL) | Metadata object | Protects table definitions during access/DDL |

Do not confuse IS/IX with table-level S/X. IX does not mean the transaction has exclusively locked the entire table; it only signals the intent to exclusively lock at the record level.

## 9. Consistent read and locking read

A regular SELECT in InnoDB is usually a consistent nonlocking read. It reads a snapshot according to the isolation level and does not acquire an S lock on each record merely because the statement is reading.

For example:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42;

Under REPEATABLE READ, consistent reads within the same transaction typically use the same read view established by the first consistent read. Under READ COMMITTED, each consistent read can create a fresh read view per statement.

Conversely:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

and:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

are locking reads. They request an S or X lock respectively on the accessed records. Locking reads read the latest committed version in accordance with locking semantics rather than only reading an older snapshot like consistent reads.

Choose a consistent read when you only need to read consistent data. Choose a locking read when a transaction needs to protect a record from concurrent modifications across a multi-step workflow.

## 10. Locking reads must be inside an appropriate transaction

A locking read is useful when the lock is held while the application executes related steps. For example:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Check quantity and record the order.

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42;

    COMMIT;

If you run a locking read in autocommit mode without explicitly opening a transaction, the statement's transaction ends as soon as the SELECT finishes; the lock no longer protects subsequent statements. Therefore, when you need to hold locks across multiple statements, you must open a transaction and commit/roll back at the appropriate time.

Keep transactions as short as possible. Do not call HTTP services, wait for user input, or perform time-consuming tasks while holding row locks.

## 11. Two-session interaction scenarios

### 11.1. S and S can coexist

Session A:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Session B:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Both can acquire an S lock. If session C runs an UPDATE on that record, C must wait.

### 11.2. X blocks both S and X

Session A:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

Session B:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

B must wait for A to commit or roll back. If B requests FOR UPDATE, B must also wait because X and X conflict.

### 11.3. Two transactions upgrading S to X concurrently

Sessions A and B both acquire FOR SHARE on the same record, and then both attempt an UPDATE. Each transaction holds S and waits for X; X is incompatible with the other transaction's S lock. InnoDB can detect a deadlock and roll back one of the transactions.

If you know for certain that you need to modify a record, acquire FOR UPDATE from the start instead of acquiring FOR SHARE and upgrading later. This reduces the risk of lock conversion deadlocks.

## 12. Deadlocks and lock waits

### 12.1. Lock wait

A lock wait occurs when a transaction requests a lock that is incompatible with an existing lock. The requesting transaction must wait until the lock is released or times out.

You may encounter a lock wait timeout error when another transaction holds a lock for too long. The application should roll back the transaction according to a clear policy, log the event, and retry with a bounded limit if the operation is safe to retry.

### 12.2. Deadlock

A deadlock occurs when transactions wait for one another in a circular dependency cycle. For example:

1. A holds an X lock on row 1.
2. B holds an X lock on row 2.
3. A requests an X lock on row 2 and waits for B.
4. B requests an X lock on row 1 and waits for A.

InnoDB detects the wait cycle and selects one transaction as the deadlock victim to roll back. The application must retry the entire victim transaction, not just re-run the last statement.

### 12.3. Reducing deadlocks

- Access tables and records in the same consistent order across transactions.
- Keep transactions short.
- Use appropriate indexes to minimize the number of records/ranges scanned and locked.
- Lock only the rows that are actually needed.
- Use FOR UPDATE from the outset when you know a modification will follow.
- Retry deadlocks with randomized backoff and a maximum retry count.
- Log the transaction, SQL statements, and involved locks to identify the root cause.

## 13. NOWAIT and SKIP LOCKED

MySQL 8.0.1 and later support options for locking reads:

- NOWAIT: if the record to be locked is already locked by another transaction, the statement immediately returns an error instead of waiting.
- SKIP LOCKED: skips records that are already locked and returns the remaining records that can be locked.

NOWAIT example:

    START TRANSACTION;

    SELECT *
    FROM jobs
    WHERE id = 10
    FOR UPDATE NOWAIT;

SKIP LOCKED example:

    START TRANSACTION;

    SELECT id
    FROM jobs
    WHERE status = 'READY'
    ORDER BY id
    LIMIT 10
    FOR UPDATE SKIP LOCKED;

SKIP LOCKED is useful when multiple workers dequeue jobs concurrently, but the result is not a complete consistent view of all matching rows: currently locked rows are skipped. The application must implement claim statuses, leases, and a recovery mechanism for jobs abandoned by workers. Do not use SKIP LOCKED if business requirements demand reading every matching row.

## 14. Lock scope depends on indexes and isolation level

InnoDB locks index records, not merely the application-level concept of a row. For a query looking up an exact primary key, the lock scope is usually narrow. With range conditions, the engine may lock multiple index records and the gaps between records.

For example:

    START TRANSACTION;

    SELECT *
    FROM orders
    WHERE customer_id = 120
      AND created_at >= '2026-01-01'
    FOR UPDATE;

If a suitable index does not exist, MySQL may have to scan more records, and the lock footprint can be wider than expected. An index starting with appropriate filtering/joining columns helps limit the access range.

Under REPEATABLE READ, InnoDB typically uses next-key locks for many locking searches/range scans to prevent phantoms within the locked range. A next-key lock combines a record lock with a gap lock on the index interval. Under READ COMMITTED, gap locking is generally disabled for locking searches/index scans, except for cases such as foreign key checks and duplicate key checks. Exact behavior depends on the statement, index, and execution plan.

Do not confuse gap locks/next-key locks with pure S/X record locks. They are range-related locks associated with index gaps that must be considered when analyzing blocked inserts or locking range queries.

## 15. Foreign key and unique checks can also acquire locks

When inserting or updating a child row, InnoDB must check whether the referenced parent row exists. This foreign key check can require locks on the referenced record to ensure integrity during the operation.

When inserting a row into a unique index, the engine must check for duplicates. This check can also interact with locks and cause a transaction to wait on another transaction that is inserting or deleting a conflicting value.

Consequently, a simple INSERT statement can still wait on locks even if the application never wrote FOR UPDATE. When investigating, examine foreign keys, unique indexes, and competing transactions rather than only explicit locking reads.

## 16. Observing locks with Performance Schema

MySQL 8.0 provides Performance Schema tables to observe data locks:

- performance_schema.data_locks: locks currently held or requested.
- performance_schema.data_lock_waits: relationships between waiting locks and blocking locks.
- performance_schema.threads: maps threads to connection/processlist IDs.

View locks:

    SELECT
        ENGINE_TRANSACTION_ID,
        THREAD_ID,
        OBJECT_SCHEMA,
        OBJECT_NAME,
        INDEX_NAME,
        LOCK_TYPE,
        LOCK_MODE,
        LOCK_STATUS,
        LOCK_DATA
    FROM performance_schema.data_locks;

View wait relationships:

    SELECT
        waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
        waiting.OBJECT_SCHEMA,
        waiting.OBJECT_NAME,
        waiting.INDEX_NAME,
        waiting.LOCK_MODE AS waiting_lock_mode,
        blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
        blocking.LOCK_MODE AS blocking_lock_mode
    FROM performance_schema.data_lock_waits AS waits
    JOIN performance_schema.data_locks AS waiting
      ON waiting.ENGINE = waits.ENGINE
     AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
    JOIN performance_schema.data_locks AS blocking
      ON blocking.ENGINE = waits.ENGINE
     AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;

These tables require Performance Schema to be enabled and the account to have privileges to view the data. LOCK_MODE may show modes such as S, X, IS, IX, or variants related to gaps/records. Read it together with OBJECT_NAME, INDEX_NAME, LOCK_TYPE, and LOCK_DATA to understand the actual scope.

You can check running transaction status:

    SELECT *
    FROM information_schema.innodb_trx;

Combine transaction age, connection ID, and currently running queries to locate sessions holding locks for a long time. Do not kill a connection based on a single lock row alone; verify the exact transaction, business owner, and rollback impact before taking action.

## 17. Business example: safely deducting inventory

Suppose we have the table:

    CREATE TABLE inventory (
        product_id BIGINT UNSIGNED NOT NULL,
        available_quantity INT NOT NULL,
        PRIMARY KEY (product_id),
        CONSTRAINT chk_inventory_nonnegative
            CHECK (available_quantity >= 0)
    ) ENGINE=InnoDB;

CHECK constraints are enforced by MySQL starting from version 8.0.16. If running on an older version, do not assume the CHECK condition in this example will protect the data; use a supported version or another validation mechanism.

You can use a conditional UPDATE to deduct inventory:

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42
      AND available_quantity >= 2;

After the statement, the application checks affected rows. If it equals 1, the requested quantity was deducted. If it equals 0, either the product does not exist or inventory is insufficient; further checks should be made per business requirements.

If you need to read the quantity first for multi-step calculations, use a transaction and FOR UPDATE:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Proceed only when the quantity is sufficient.

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42;

    COMMIT;

The two approaches have slightly different trade-offs. A conditional UPDATE is usually shorter and reduces lock-holding duration. FOR UPDATE is suitable when you need to read and make decisions based on the locked value across multiple steps. Do not read with a regular SELECT, check in the application, and then run an unconditional UPDATE, because another transaction may modify inventory between the two statements.

## 18. Common misconceptions

| Misconception | Reality |
|---|---|
| Shared locks block all other transactions | A shared lock is compatible with other shared locks on the same record |
| Exclusive locks only block writes | An X lock conflicts with both S and X locks from other transactions on the same record |
| IX is an exclusive lock on the entire table | IX only signals the intent to acquire X row locks inside the table |
| IS/IX prevent other transactions from locking rows | IS/IX are generally compatible with other intention locks; they coordinate with table-level locks |
| A regular SELECT always acquires an S lock | InnoDB normally uses a consistent nonlocking read for regular SELECT statements |
| UPDATE always locks the whole table | Lock scope depends on indexes, conditions, and the execution plan |
| Locking reads hold locks across multiple HTTP requests | Locks exist per transaction/connection and are released when the transaction ends |
| COMMIT does not affect row locks | COMMIT/ROLLBACK releases the transaction's locks |
| FOR SHARE and FOR UPDATE behave like a regular SELECT | They are locking reads that can acquire S/X locks and block other transactions |
| Foreign keys ensure a tree has no cycles | Foreign keys verify reference existence, not acyclicity of relationships |

## 19. Checklist for designing transactions and investigating locks

- Is a consistent read sufficient, or is a locking read required?
- If a modification is needed, can FOR UPDATE be used from the start?
- Are transactions opened explicitly and ended promptly?
- Do transactions access tables/records in the same consistent order?
- Do indexes restrict the number of records and ranges scanned?
- Are IS/IX being confused with table-level S/X?
- Is any transaction holding locks too long or waiting on external services?
- Are there gap/next-key locks caused by range scans and the isolation level?
- Could foreign key or unique checks be a source of waits?
- Are NOWAIT/SKIP LOCKED appropriate for the business semantics?
- Are data_locks, data_lock_waits, and innodb_trx being monitored during investigation?
- Does the application roll back transactions cleanly and retry deadlocks with a bounded limit?

## Conclusion

Shared locks (S) allow multiple transactions to perform locking reads on a record concurrently while blocking X locks. Exclusive locks (X) grant exclusive access on a record and conflict with both other S and X locks. Intention locks (IS/IX) are placed at the table level to indicate that a transaction intends to lock records inside; they allow InnoDB to coordinate row locks with table-level locks without turning every operation into a full-table lock. Regular SELECT statements are normally nonlocking consistent reads; FOR SHARE and FOR UPDATE are locking reads and require properly managed transactions. Lock scope also depends on indexes, isolation levels, range scans, foreign keys, and unique checks. Mastering these rules helps reduce contention, avoid deadlocks, and diagnose concurrency issues in MySQL more accurately.
