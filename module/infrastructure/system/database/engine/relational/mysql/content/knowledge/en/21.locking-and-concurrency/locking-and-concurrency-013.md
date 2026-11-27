# LOCK TABLES and boundaries with InnoDB transactional locking

MySQL has multiple locking mechanisms with different scopes and lifecycles. LOCK TABLES places table-level locks for the current session; meanwhile, InnoDB has record locks, gap locks, and intention locks to coordinate transactions. These mechanisms are not interchangeable. If you treat LOCK TABLES as though it were part of an InnoDB transaction, an application can accidentally commit data prematurely, lose SAVEPOINTs, or block other sessions longer than expected.

LOCK TABLES is commonly used in administrative tasks or workflows requiring table-level access control. For standard transactional applications using InnoDB, row-level locking via UPDATE, DELETE, SELECT ... FOR UPDATE, or SELECT ... FOR SHARE is usually more appropriate. This lesson explains READ/WRITE syntax, session scope, locking multiple tables, transaction boundaries, and the differences among table locks, row locks, intention locks, and metadata locks.

## Learning objectives

After this lesson, you will be able to:

- Explain LOCK TABLES, UNLOCK TABLES, and session-scoped locking.
- Distinguish READ, READ LOCAL, and WRITE table locks.
- Lock multiple tables and use aliases properly.
- Predict whether other sessions can read or write a locked table.
- Understand why LOCK TABLES triggers an implicit commit before acquiring locks.
- Recognize the effects of UNLOCK TABLES, START TRANSACTION, COMMIT, ROLLBACK, and autocommit.
- Distinguish SQL-layer table locks from InnoDB record and gap locks.
- Understand that intention locks and metadata locks are not data locks for the same purpose.
- Use SELECT ... FOR UPDATE or FOR SHARE inside a transaction when row locking is needed.
- Observe lock waits, deadlocks, and metadata locks.
- Choose the appropriate locking mechanism for a task and design short lock durations.

## 1. Four locking concepts to keep separate

When referring to "table locks" or "row locks," identify the exact lock type and target:

| Mechanism | Scope / function | Typical lifecycle |
|---|---|---|
| LOCK TABLES | Table lock at the SQL layer, restricting read/write access by other sessions | Session-scoped, normally until UNLOCK TABLES or session termination |
| InnoDB record/gap/next-key lock | Protects records or index intervals against conflicting operations | Transaction-scoped, released on COMMIT or ROLLBACK |
| InnoDB intention lock | Signals a transaction's intent to lock records inside a table | Transaction-scoped, coordinates with table-level locks |
| Metadata lock (MDL) | Protects table definitions, views, and metadata against conflicting changes | Typically tied to statement or transaction duration depending on access type |

These locks can appear together in a single operation. For instance, an UPDATE on an InnoDB row acquires a record lock and an intention lock on the table; the statement also needs a metadata lock to protect the table definition during execution. LOCK TABLES, by contrast, is a separate explicit table-locking mechanism at the SQL layer.

Never assume a query taking a "table lock" means InnoDB locked every record via the same mechanism, or that row locks prevent schema changes. Each lock type resolves a different class of conflicts.

## 2. LOCK TABLES syntax

General syntax:

    LOCK TABLES
        table_name [AS alias] lock_type
        [, table_name [AS alias] lock_type] ...;

Common lock types:

- READ: the lock-holding session can read; other sessions can also read, but must wait if they want to write.
- READ LOCAL: a READ variant allowing certain non-conflicting concurrent INSERTs on storage engines that support it, such as MyISAM. For InnoDB, READ LOCAL is equivalent to READ.
- WRITE: the lock-holding session can read and write; other sessions must wait for any conflicting table access, including regular reads.

Example:

    LOCK TABLES inventory_demo READ;

    SELECT * FROM inventory_demo;

    UNLOCK TABLES;

Write lock example:

    LOCK TABLES inventory_demo WRITE;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    UNLOCK TABLES;

READ and WRITE are explicit table-level locks. They can block far more operations than necessary if the application only needs to protect a few rows.

## 3. How do READ locks and WRITE locks differ?

The table below describes general table lock behavior:

| Situation | Session holding READ | Other sessions when table has READ | Session holding WRITE | Other sessions when table has WRITE |
|---|---|---|---|---|
| SELECT | Allowed | Allowed | Allowed | Must wait |
| INSERT | Disallowed by READ lock permissions | Must wait | Allowed | Must wait |
| UPDATE | Disallowed by READ lock permissions | Must wait | Allowed | Must wait |
| DELETE | Disallowed by READ lock permissions | Must wait | Allowed | Must wait |

A READ lock fits when a session needs table-level read stability during a task and can accept blocking writes from other sessions. A WRITE lock is more exclusive: the lock-holding session can read and write, while other sessions must wait on conflicting accesses.

Exact behavior is also affected by storage engine, statement type, privileges, and other locking mechanisms. Specifically for InnoDB, LOCK TABLES should not be treated as the default way to protect rows in business flows. Later sections compare this with row-level locking.

## 4. Locking multiple tables in one statement

If a task needs access to multiple tables, list all needed tables in a single LOCK TABLES statement:

    LOCK TABLES
        account_demo READ,
        transfer_audit_demo WRITE;

    SELECT account_id, balance
    FROM account_demo
    WHERE account_id = 1;

    INSERT INTO transfer_audit_demo
        (transfer_id, description)
    VALUES
        (9001, 'Manual reconciliation');

    UNLOCK TABLES;

Do not lock tables piecemeal via multiple separate LOCK TABLES calls assuming old locks always remain held. A new LOCK TABLES statement can replace the session's current set of explicit locks. Determine all required tables upfront and lock them in one call using a consistent order.

When locking a view, MySQL includes the view's underlying base tables in the lock set. When operating through triggers or foreign key relationships, MySQL also automatically opens and locks related tables per trigger and foreign key rules. Account for these indirect accesses when assessing lock scope and privileges. For complex business workflows, InnoDB transactions and row-level locking are usually easier to manage.

### 4.1. Locking tables with aliases

If a query uses an alias, declare the alias in LOCK TABLES and use that exact alias:

    LOCK TABLES
        inventory_demo AS i WRITE,
        warehouse_demo AS w READ;

    SELECT i.product_id, i.available_quantity, w.warehouse_name
    FROM inventory_demo AS i
    JOIN warehouse_demo AS w
        ON w.warehouse_id = i.warehouse_id;

    UNLOCK TABLES;

After locking with an alias, reference the table through its corresponding alias in the session's statements. Do not assume locking the original table name automatically covers any alias a query might use.

### 4.2. Avoid locking the same table multiple times with different aliases

LOCK TABLES has its own alias management rules. Do not lock the same table repeatedly under different aliases to simulate a self-join. If a query must self-join a table, construct the LOCK TABLES statement and aliases according to exact MySQL syntax rules; if uncertain, prefer an InnoDB transaction with a clearly aliased query.

Example of a regular read-only self-join without needing LOCK TABLES:

    SELECT
        child.employee_id,
        manager.employee_id AS manager_id
    FROM employee_demo AS child
    LEFT JOIN employee_demo AS manager
        ON manager.employee_id = child.manager_id;

Only add explicit table locks when there is a specific operational reason and you have verified your server version's alias rules.

## 5. Scope and lifecycle of table locks

LOCK TABLES creates locks for the current session. Another session cannot release locks on behalf of the holding session. Normally locks are held until:

- The session executes UNLOCK TABLES.
- The session ends or the connection closes.
- Another transaction/DDL operation releases table locks per MySQL rules.

This means an application using a connection pool that forgets UNLOCK TABLES can leave locks active longer than the request duration. If the connection is reused, the next request may inherit an unintended session state.

Always use explicit cleanup in application code:

1. Acquire connection.
2. Execute LOCK TABLES.
3. Run the required short operation.
4. In both success and error branches, ensure UNLOCK TABLES runs while the session is still alive.
5. Return the connection to the pool only after verifying session state is clean.

If a connection drops, the server releases locks tied to that session when the session actually terminates. Do not assume the server closed the connection instantaneously just because the application timed out.

LOCK TABLES also acquires metadata locks to protect locked objects. Certain DDL statements are disallowed while table locks are active, and ALTER TABLE on a locked table can unlock the table per MySQL rules. Therefore, do not use table locks as a way to retain access across schema migrations.

LOCK TABLES and UNLOCK TABLES cannot be called inside stored programs. If locking is needed inside a stored procedure or trigger, redesign operation boundaries using transactions and appropriate InnoDB locks.

## 6. LOCK TABLES and transaction boundaries

This is the most critical point of the lesson: LOCK TABLES is not a statement that begins a transaction. MySQL commits any currently active transaction before attempting to acquire explicit table locks.

Example:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 20.00
    WHERE account_id = 1;

    LOCK TABLES account_demo WRITE;

    ROLLBACK;

The UPDATE before LOCK TABLES was already committed by LOCK TABLES's implicit commit. The subsequent ROLLBACK does not undo that balance change.

Diagram:

    START TRANSACTION
           |
           v
    UPDATE account_demo
           |
           v
    LOCK TABLES account_demo WRITE
           |
           +---- implicit commit of the open transaction
           |
           +---- then acquires explicit table lock
           |
           v
    ROLLBACK
           |
           +---- cannot undo the already-committed UPDATE

Therefore, never place LOCK TABLES in the middle of a DML sequence that the application expects to roll back together.

### 6.1. UNLOCK TABLES can commit a transaction

UNLOCK TABLES releases locks acquired via LOCK TABLES. If a session used LOCK TABLES to acquire table locks, UNLOCK TABLES can implicitly commit an active transaction per MySQL rules.

This means UNLOCK TABLES is also a boundary to watch closely. Never treat it as a "just release locks" command without checking transaction state.

Exception to distinguish: UNLOCK TABLES does not commit a transaction merely because the session is releasing a global read lock created by FLUSH TABLES WITH READ LOCK. The global read lock is a distinct mechanism from locks created by LOCK TABLES.

### 6.2. START TRANSACTION releases existing table locks

Starting a new transaction via START TRANSACTION or BEGIN ends the current transaction if any and releases currently held table locks per MySQL rules.

Thus, never write:

    LOCK TABLES account_demo WRITE;
    START TRANSACTION;
    UPDATE account_demo
    SET balance = balance - 10
    WHERE account_id = 1;

and assume the WRITE lock remains held. START TRANSACTION alters the boundary and releases existing explicit table locks. If transactional data protection is required, use InnoDB transactions and row-level locking rather than trying to mix both mechanisms.

### 6.3. COMMIT and ROLLBACK are not substitutes for UNLOCK TABLES

COMMIT or ROLLBACK ends the InnoDB transaction and releases row locks as well as internal InnoDB table locks belonging to the transaction. Explicit table locks at the MySQL layer managed by LOCK TABLES have their own lifecycle. Use UNLOCK TABLES to release table locks and COMMIT/ROLLBACK to end transactions according to their respective purposes.

Never design code assuming COMMIT is always equivalent to UNLOCK TABLES or vice versa. These commands interact per MySQL rules, so separate them clearly:

- Table locks are managed by LOCK TABLES / UNLOCK TABLES.
- Transactions are managed by START TRANSACTION, COMMIT, and ROLLBACK.
- InnoDB row locks are held per transaction.

ROLLBACK does not release table locks acquired via LOCK TABLES. If you roll back a transaction while holding table locks, you must still call UNLOCK TABLES to release locks at the MySQL layer.

### 6.4. Autocommit and LOCK TABLES

Check the session's autocommit setting:

    SELECT @@SESSION.autocommit;

With autocommit = 1, regular DML is committed as soon as the statement completes. Explicit table locks at the MySQL layer may remain held per session until UNLOCK TABLES, but InnoDB does not acquire internal table locks for LOCK TABLES in this mode. That prevents InnoDB from fully coordinating table locks with other transactions' row locks; deadlocks spanning both lock layers can become undetectable. Therefore, do not use LOCK TABLES on InnoDB tables with autocommit = 1 as a transaction synchronization mechanism.

If you genuinely need LOCK TABLES with transactional tables like InnoDB, MySQL instructs starting with SET autocommit = 0, followed by LOCK TABLES; never use START TRANSACTION right before LOCK TABLES. Example:

    SET autocommit = 0;

    LOCK TABLES
        inventory_demo WRITE,
        warehouse_demo READ;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    SELECT warehouse_id, warehouse_name
    FROM warehouse_demo;

    COMMIT;
    UNLOCK TABLES;
    SET autocommit = 1;

With autocommit = 0 and innodb_table_locks = 1 (the default), LOCK TABLES acquires locks at the MySQL layer and corresponding internal locks in InnoDB. COMMIT releases InnoDB's transaction locks; the MySQL-layer table lock remains until UNLOCK TABLES. Thus, the safe order is to commit the transaction first and only then unlock tables. If the transaction must be aborted, run ROLLBACK followed by UNLOCK TABLES; ROLLBACK does not automatically release MySQL-layer table locks.

Switching autocommit from 0 to 1 can commit an active transaction. In applications using connection pools, restore autocommit and lock state after completion, including in error branches. Use this workflow only with clear justification; for standard InnoDB applications, row-level locking remains the preferred choice.

## 7. How does InnoDB row-level locking work?

InnoDB uses locks at the index record level and needed index intervals to protect operations. When a transaction updates or deletes rows, InnoDB locks the involved records. A locking read like SELECT ... FOR UPDATE requests exclusive locks on read records; SELECT ... FOR SHARE requests shared locks.

Example:

    START TRANSACTION;

    SELECT product_id, available_quantity
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100
      AND available_quantity > 0;

    COMMIT;

The transaction locks the product row before checking and updating inventory. Another session attempting to update the same record must wait for the lock to be released or receive a timeout/deadlock error depending on circumstances.

Locks are held until COMMIT or ROLLBACK. This is a fundamental difference from session-scoped explicit table locks.

### 7.1. Record locks are actually based on indexes

InnoDB organizes row locks around index records, rather than an abstract lock attached purely to a user-visible "row." Queries filtering on a primary key usually lock a very specific scope. Queries with conditions lacking a suitable index may have to scan and lock more records than expected.

Example:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

If product_id is the primary key, InnoDB can locate the exact record via the index. If a filter predicate lacks an appropriate index, the scanned and locked record range can broaden, increasing contention.

Thus, indexes affect not only read speed, but also lock scope and concurrency.

### 7.2. Record lock, gap lock, and next-key lock

- A record lock locks a single index record.
- A gap lock locks the empty space between index records, preventing certain insert operations into that interval.
- A next-key lock combines a record lock with the gap immediately preceding the record, commonly used to prevent phantoms under applicable predicates and isolation levels.

Not every SELECT ... FOR UPDATE locks exactly one row. With range queries, the isolation level and execution plan can cause InnoDB to lock entire index intervals. Always examine predicates, indexes, and isolation level when analyzing lock contention.

### 7.3. Locking reads and consistent reads

A regular SELECT in InnoDB is usually an MVCC-based consistent read; it reads a snapshot matching the isolation level without acquiring row locks simply to read.

SELECT ... FOR UPDATE and SELECT ... FOR SHARE are locking reads. They request locks to protect read rows from conflicting modifications within the transaction.

Do not add FOR UPDATE to every SELECT. Use it only when a transaction must protect a decision or update based on newly read data.

## 8. SELECT ... FOR UPDATE and FOR SHARE

Two common syntaxes:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR SHARE;

FOR UPDATE acquires an exclusive lock for a locking read; FOR SHARE acquires a shared lock. Other transactions can concurrently hold compatible shared locks, but any attempt to modify the record must wait until shared locks are released.

FOR SHARE is MySQL 8.0 syntax. On MySQL 5.7, the corresponding syntax commonly used is LOCK IN SHARE MODE. Choose the syntax matching your supported server version.

In MySQL 8.0, syntax can include NOWAIT or SKIP LOCKED:

    SELECT *
    FROM job_queue
    WHERE job_status = 'READY'
    ORDER BY created_at, job_id
    LIMIT 10
    FOR UPDATE SKIP LOCKED;

SKIP LOCKED skips rows currently locked by other transactions, which is useful when multiple workers claim jobs from a queue. Results do not represent a complete consistent view of matching rows because locked rows are skipped. Do not use it for reports requiring complete reads.

NOWAIT tells the query to return an error immediately if a lock cannot be acquired rather than waiting:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE NOWAIT;

NOWAIT and SKIP LOCKED have version requirements; verify your deployed MySQL server version before using them.

### 8.1. Explicit transactions are required

To hold row locks across multiple statements, open a transaction:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    -- Application checks and updates in the same connection.

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    COMMIT;

If using autocommit without opening an explicit transaction, the statement ending can terminate the implicit transaction and release locks immediately afterward. When locks are needed across multiple steps, control transaction boundaries explicitly.

## 9. InnoDB intention locks are not LOCK TABLES

InnoDB uses table-level intention locks to signal that a transaction currently locks or intends to lock records inside the table:

- IS (intention shared): the transaction intends to acquire shared locks at the record level.
- IX (intention exclusive): the transaction intends to acquire exclusive locks at the record level.

For example, updating a record typically needs an intention exclusive lock on the table and an exclusive record lock on the corresponding index record.

Intention locks allow InnoDB to coordinate row locks with operations needing table-level locks. They do not mean the entire table is locked against all reads/writes from other sessions. Multiple transactions can simultaneously hold IX on a table while locking distinct records.

Distinguish:

| Lock | Who requests it? | Meaning |
|---|---|---|
| IX/IS | Managed automatically by InnoDB transactions | Signals intent to lock records |
| LOCK TABLES ... WRITE | Explicitly requested by a session | Locks the table at the SQL layer, blocking conflicting accesses from other sessions |
| Record lock | InnoDB transaction | Locks a specific index record |

Do not confuse intention locks with explicit WRITE locks. Intention locks are part of InnoDB's internal lock coordination system, not administrative commands locking the entire table.

## 10. Metadata locks differ from table locks and row locks

Metadata locks (MDL) protect database object definitions. A SELECT or DML query needs an appropriate metadata lock to ensure the table structure cannot be altered unsafely while the statement uses it.

Example:

- Session A opens a transaction and queries a table.
- A's transaction retains the required metadata lock for the duration of the transaction.
- Session B runs ALTER TABLE on the same table and must wait for a compatible metadata lock.

This is why an ALTER TABLE can wait even when zero row locks exist on the rows DDL needs to touch. MDL protects metadata, not individual row values.

| Mechanism | Protects | Conflict example |
|---|---|---|
| Metadata lock | Table/view definitions | ALTER TABLE waits for a transaction using the table |
| Table lock | Table access at the SQL layer | WRITE lock blocks other sessions from reading/writing |
| InnoDB row/index lock | Records or index intervals | Two transactions updating the same row |

When investigating "the database is locked," identify which lock type is waiting before choosing a remedy. Killing a transaction holding MDL, dropping a table lock, or reducing row-lock contention are distinct actions with different data impacts.

## 11. Comparing LOCK TABLES with InnoDB transactional locking

| Criterion | LOCK TABLES | InnoDB row-level locking |
|---|---|---|
| Scope | Table | Index records and potentially intervals |
| How requested | LOCK TABLES READ/WRITE | UPDATE/DELETE or SELECT ... FOR UPDATE/FOR SHARE |
| Lifecycle | Session-scoped and governed by UNLOCK/transaction/DDL rules | Transaction-scoped |
| Transaction interaction | LOCK TABLES triggers an implicit commit before acquiring locks | Designed to operate inside transactions |
| Concurrency level | Typically coarse and easily blocks many sessions | Allows other transactions to work on non-conflicting records |
| Best suited for | Administrative tasks or special workflows needing table locks | Application transactional flows |
| Risks | Long lock holds block broadly; easily breaks transaction boundaries | Deadlocks, lock waits, and broad lock scope without proper indexes |

For InnoDB tables, prefer transactions and row-level locking for business logic. LOCK TABLES is not a simpler version of SELECT ... FOR UPDATE; it has different commit semantics and blocking scope.

## 12. Two-session practice: observing READ and WRITE locks

Run these examples in a sandbox database using two independent connections. Never run on production tables.

The steps in this section demonstrate MySQL-layer table lock blocking. For production InnoDB, if you must coordinate table locks with internal engine locks, use the exact autocommit = 0 workflow in section 6.4; do not treat default autocommit examples here as a transaction design template.

### 12.1. Creating the test table

    CREATE TABLE lock_table_demo (
        item_id INT NOT NULL PRIMARY KEY,
        item_name VARCHAR(80) NOT NULL,
        quantity INT NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO lock_table_demo (item_id, item_name, quantity)
    VALUES
        (1, 'Keyboard', 10),
        (2, 'Mouse', 20);

Ensure both sessions connect to the same database.

### 12.2. Session A acquires a READ lock

    LOCK TABLES lock_table_demo READ;

    SELECT * FROM lock_table_demo;

Keep session A in this state and switch to session B.

### 12.3. Session B tries reading and writing

Read from session B:

    SELECT * FROM lock_table_demo;

A READ lock lets other sessions read, so the SELECT completes.

Write from session B:

    UPDATE lock_table_demo
    SET quantity = quantity + 1
    WHERE item_id = 1;

The UPDATE must wait because session A holds a READ lock. Do not leave session B waiting indefinitely in the lab; after observing the state, return to session A and run:

    UNLOCK TABLES;

Session B proceeds once the lock is released.

### 12.4. Session A acquires a WRITE lock

In session A:

    LOCK TABLES lock_table_demo WRITE;

    UPDATE lock_table_demo
    SET quantity = quantity - 1
    WHERE item_id = 1;

    SELECT * FROM lock_table_demo;

Session A can read and write the table. In session B, try:

    SELECT * FROM lock_table_demo;

B's read query must wait on the WRITE lock. After A runs:

    UNLOCK TABLES;

only then can B proceed. This experiment demonstrates that a WRITE lock blocks both reads and writes from other sessions while held.

## 13. Two-session practice: InnoDB row locking

Create the inventory table:

    CREATE TABLE row_lock_demo (
        product_id INT NOT NULL PRIMARY KEY,
        available_quantity INT NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO row_lock_demo (product_id, available_quantity)
    VALUES (100, 5), (200, 8);

### 13.1. Session A locks one row

    START TRANSACTION;

    SELECT product_id, available_quantity
    FROM row_lock_demo
    WHERE product_id = 100
    FOR UPDATE;

Keep the transaction open. Record product_id = 100 is exclusively locked by A.

### 13.2. Session B updates a different row

    UPDATE row_lock_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 200;

Because B updates a different record, the operation completes if there are no other conflicts.

### 13.3. Session B updates the same row

    UPDATE row_lock_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

B must wait for A's lock. Return to A:

    COMMIT;

After A commits, B proceeds and updates the record.

Compare with a WRITE table lock: a WRITE lock blocks table access much more broadly; row locks protect only the involved records and index intervals. This is why InnoDB maintains higher concurrency when transactions touch non-conflicting rows.

## 14. Row-level locking does not always lock just one row

A query with the condition:

    SELECT *
    FROM row_lock_demo
    WHERE product_id >= 100
    FOR UPDATE;

can lock multiple records and index intervals depending on indexes, isolation level, and execution plan. Without an appropriate index for the condition, the scan scope can be broad.

To reduce lock contention:

- Use primary keys or suitable indexes for locking predicates.
- Keep transactions short.
- Lock only the rows actually needed.
- Access rows in a consistent order across transactions to reduce deadlocks.
- Never call external APIs or wait for users while holding a transaction.
- Commit/roll back as soon as data work completes.

Do not add FOR UPDATE to read-only reporting queries. An unnecessary locking read lowers concurrency and creates wait queues.

## 15. READ LOCAL and storage engines

READ LOCAL is a READ lock variant allowing certain non-conflicting concurrent INSERTs on storage engines that support this behavior, such as MyISAM. For InnoDB, READ LOCAL behaves like READ and does not enable concurrent writes while a table lock is held.

Before using LOCK TABLES, check the storage engine:

    SELECT
        TABLE_NAME,
        ENGINE
    FROM information_schema.tables
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'lock_table_demo';

InnoDB provides transactions, MVCC, and row-level locking. MyISAM does not support transactions the way InnoDB does; MyISAM writes rely heavily on table-level locking. Thus, the same LOCK TABLES statement can have different operational impacts depending on the engine.

Never pick READ LOCAL or LOCK TABLES solely by lock name. Check engine, version, and actual workload.

## 16. Required privileges

To use LOCK TABLES, an account needs the LOCK TABLES privilege and the SELECT privilege on each locked object. Statements executed while holding the lock still require their respective SELECT, INSERT, UPDATE, or DELETE privileges.

Example of how an administrator might grant required privileges in a test environment:

    GRANT LOCK TABLES, SELECT, UPDATE
    ON inventory_lab.*
    TO 'inventory_operator'@'%';

Do not grant broader privileges than necessary. LOCK TABLES can affect other sessions and should only be granted to operational accounts or tasks with specific justification. Verify effective privileges with SHOW GRANTS:

    SHOW GRANTS FOR CURRENT_USER();

Account name and host in GRANT must match a created account; the example above illustrates syntax only.

## 17. Observing lock waits and deadlocks

When a statement waits, first identify the waiting session and the lock-holding session.

Session info:

    SHOW FULL PROCESSLIST;

InnoDB transaction info:

    SELECT *
    FROM information_schema.innodb_trx;

In MySQL 8.0, Performance Schema provides helpful tables:

    SELECT *
    FROM performance_schema.data_locks;

    SELECT *
    FROM performance_schema.data_lock_waits;

    SELECT *
    FROM performance_schema.metadata_locks;

Column names and read privileges can depend on version/configuration. Use these tables to identify lock type, object, thread, and blocker/waiter relationships.

To inspect the latest deadlock in InnoDB:

    SHOW ENGINE INNODB STATUS;

The LATEST DETECTED DEADLOCK section describes transactions participating in the deadlock, involved statements, and the transaction chosen as the victim. When a deadlock occurs and InnoDB detects the cycle, InnoDB automatically picks a victim transaction to roll back; the application must handle the error and may retry the entire transaction under a bounded policy. Deadlocks spanning MySQL-layer table locks and row locks may not be detected by InnoDB if internal table locks were not acquired.

### 17.1. Differences among lock wait timeouts and deadlocks

- Lock wait timeout: a transaction waits for a lock longer than permitted. Depending on configuration and statement, the error may roll back the statement or transaction per InnoDB rules.
- Deadlock: two or more transactions form a lock wait cycle; InnoDB detects the cycle and chooses one transaction as the victim.
- Metadata lock wait: a statement waits for an object's metadata lock; usually involves transactions or DDL using the table.
- Table lock wait: a session waits for an explicit table lock or another table-level lock.

Never treat every situation by simply increasing timeouts. First identify the root cause, lock hold duration, indexes, and data access order.

## 18. FLUSH TABLES WITH READ LOCK is not LOCK TABLES READ

A command frequently confused with LOCK TABLES is:

    FLUSH TABLES WITH READ LOCK;

This statement acquires a global read lock, broadly affecting write operations across the server and commonly used in certain backup/snapshot workflows coordinated with the binary log. It is not the same as a READ lock on a single table.

Release the global read lock with:

    UNLOCK TABLES;

Although both use UNLOCK TABLES, the two mechanisms have different transaction rules. Specifically, UNLOCK TABLES after FLUSH TABLES WITH READ LOCK does not carry the same implicit commit behavior as releasing table locks acquired via LOCK TABLES.

A global read lock heavily impacts workloads. Never run it in production without understanding backup procedures, replication, lock duration, and write impact.

## 19. When should you use LOCK TABLES?

LOCK TABLES can be useful for:

- Legacy administrative tasks requiring brief whole-table protection.
- Special read/write workflows with table-locking storage engines.
- Certain export or maintenance tasks requiring coordinated table locks that are clearly designed.
- Operational tooling ensuring no other session alters a table during a controlled sequence of operations.

For InnoDB transactional applications, prefer:

- Atomic conditional UPDATEs instead of unlocked SELECT-then-UPDATE.
- SELECT ... FOR UPDATE when needing to read and decide to update in the same transaction.
- SELECT ... FOR SHARE when protecting read data from conflicting writes.
- Unique constraints or foreign keys to enforce data invariants in the database.
- Optimistic concurrency via a version column when suitable.

Example reducing race conditions without LOCK TABLES:

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100
      AND available_quantity > 0;

    SELECT ROW_COUNT();

If ROW_COUNT() equals 1, one unit of inventory was deducted. If it equals 0, either the product does not exist or stock is insufficient; the application can inspect the cause as needed. This is an atomic conditional update, avoiding an unlocked SELECT followed by a racy UPDATE.

## 20. Common mistakes

- Thinking LOCK TABLES starts a transaction.
- Running UPDATE then LOCK TABLES and expecting a later ROLLBACK to undo the UPDATE.
- Thinking UNLOCK TABLES only releases locks and cannot affect transactions.
- Running START TRANSACTION while holding a table lock and assuming the lock stays held.
- Confusing COMMIT/ROLLBACK with UNLOCK TABLES.
- Holding table locks long inside a connection pool and returning connections without cleanup.
- Locking only one table while statements access other tables, different aliases, or tables used by triggers.
- Using a WRITE lock when only a single record needs locking.
- Assuming an InnoDB row lock always corresponds to exactly one logical row.
- Failing to add proper indexes, causing locking reads to scan and lock broad ranges.
- Using SELECT ... FOR UPDATE for read-only queries.
- Confusing intention locks with explicit table locks.
- Confusing metadata locks with row locks and targeting the wrong blocker.
- Using READ LOCAL as a concurrency mechanism for InnoDB.
- Confusing FLUSH TABLES WITH READ LOCK with LOCK TABLES READ.
- Increasing lock wait timeouts without investigating root cause.
- Failing to retry transactions after deadlocks in a bounded, safe manner.

## 21. Pre-use checklist for LOCK TABLES

- Identified why table-level locking is needed instead of record-level locking.
- Checked storage engine and MySQL version.
- Clarified whether READ, READ LOCAL, or WRITE is required.
- Listed all tables, aliases, and indirectly accessed objects.
- Understood that LOCK TABLES triggers an implicit commit before acquiring locks.
- Verified there is no uncommitted DML needing rollback.
- Implemented an UNLOCK TABLES release path in both success and error branches.
- Ensured the connection pool never reuses sessions still holding locks.
- Kept lock duration short with appropriate timeouts/monitoring.
- Distinguished table locks, InnoDB row locks, intention locks, and metadata locks.
- Considered SELECT ... FOR UPDATE/FOR SHARE or atomic UPDATEs for InnoDB business flows.
- Checked indexes and potential record lock scope.
- Know how to observe blockers, waiters, and deadlocks.
- Checked the impact of FLUSH TABLES WITH READ LOCK if backup workflows use it.
- Used SET autocommit = 0 before LOCK TABLES if table locks must truly coordinate with InnoDB, and ran COMMIT before UNLOCK TABLES.
- Tested in a sandbox with at least two sessions before applying in production.

LOCK TABLES creates session-scoped table locks and can block far more broadly than InnoDB transactional locking. LOCK TABLES triggers an implicit commit before acquiring locks; START TRANSACTION releases existing table locks; UNLOCK TABLES can commit a transaction if locks were acquired via LOCK TABLES; and ROLLBACK does not automatically release table locks. If you genuinely use LOCK TABLES with InnoDB, follow the sequence SET autocommit = 0, LOCK TABLES, data operations, COMMIT, and then UNLOCK TABLES. For normal InnoDB applications, prefer short transactions, record locking with SELECT ... FOR UPDATE/FOR SHARE, or atomic conditional UPDATEs. Only use explicit table locks when there is a clear operational need and you understand commit boundaries, lock scope, release mechanics, and impact on other sessions.
