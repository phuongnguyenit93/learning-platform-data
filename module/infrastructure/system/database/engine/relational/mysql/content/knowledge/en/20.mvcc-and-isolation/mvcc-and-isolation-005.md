# READ COMMITTED and Statement-Level Snapshots

## Lesson Objectives

After this lesson, you will be able to:

- Explain READ COMMITTED in InnoDB and how MVCC creates a read view for a SELECT statement.
- Distinguish statement-level snapshots in READ COMMITTED from transaction-level snapshots in REPEATABLE READ.
- Predict results when two sessions read and write the same row.
- Distinguish consistent nonlocking reads from locking reads such as SELECT ... FOR SHARE and SELECT ... FOR UPDATE.
- Identify non-repeatable reads and phantom reads that can occur under READ COMMITTED.
- Understand the impact of READ COMMITTED on gap locks, UPDATE, DELETE, and replication.
- Choose an appropriate isolation level for reporting, business workflows, and concurrency requirements.
- Configure and inspect isolation levels at session or transaction scope.

In InnoDB, an ordinary SELECT statement generally does not lock the rows it reads. Instead, MVCC (Multi-Version Concurrency Control) allows a query to see a data version corresponding to a specific point in time. This mechanism lets read and write transactions proceed concurrently without blocking each other solely because a query is reading.

The defining characteristic of READ COMMITTED is that each consistent read receives a new read view. If another transaction commits data after the first SELECT statement, a second SELECT statement in the same transaction can see that newly committed data. This lesson focuses on how this behavior works, its consequences, and how to use it in MySQL applications.

## 1. What Is READ COMMITTED?

READ COMMITTED is a transaction isolation level supported by InnoDB. For an ordinary SELECT statement without a locking clause, InnoDB creates a logical snapshot (read view) for that read statement.

A statement's snapshot allows the query to:

- See changes committed before the read view was created.
- Not see uncommitted changes from other transactions.
- Not see changes from other transactions committed after the read view was created.
- See changes made by the current transaction itself in earlier statements.

With READ COMMITTED, each consistent read creates a new snapshot, even when the SELECT statements are in the same transaction.

For example, transaction A runs two SELECT statements:

1. The first SELECT reads an inventory quantity of 10.
2. Transaction B updates inventory to 8 and COMMITs.
3. A's second SELECT reads the new data, 8.

Both SELECTs belong to the same transaction A. The results differ because each read statement uses its own read view.

### 1.1. Not READ UNCOMMITTED

READ COMMITTED does not allow reading uncommitted data from other transactions. If B is running an UPDATE but has not COMMITted, A's ordinary SELECT still reads the previously committed version.

READ UNCOMMITTED can read uncommitted versions and therefore carries the risk of dirty reads. READ COMMITTED eliminates dirty reads by only providing committed versions matching the read view.

### 1.2. InnoDB Defaults to REPEATABLE READ

InnoDB's default isolation level is REPEATABLE READ. At this level, consistent reads within the same transaction share the snapshot created by the first consistent read.

Therefore, if you want to observe statement-level fresh snapshot behavior, you need to set the isolation level to READ COMMITTED for the session or transaction before starting your test.

When autocommit is enabled and there is no explicit transaction, each statement is its own transaction. The difference between READ COMMITTED and REPEATABLE READ is clearest when an application opens a transaction with START TRANSACTION and runs multiple SELECT statements before COMMIT.

## 2. MVCC and Statement-Level Read Views

MVCC maintains multiple logical versions of a row so transactions can read an appropriate version without necessarily waiting for writing transactions to finish.

When a transaction updates an InnoDB row, the old version is preserved through the undo log as long as it is needed for consistent reads and rollbacks. When a SELECT statement creates a read view, InnoDB determines which transactions had committed before that point and which row versions are allowed to be displayed.

Under READ COMMITTED:

- Each consistent read creates a new read view.
- The new read view can include transactions that committed since the previous read statement.
- Transactions still uncommitted when the read view is created remain excluded from the SELECT statement's view.
- A transaction can see committed changes from other sessions between two SELECT statements.

Do not think of a new snapshot as a physical copy of the entire database rebuilt for each SELECT. It is a logical view constructed by InnoDB from row versions and transaction metadata.

### 2.1. Preparing Data Used in This Lesson

The following examples use three InnoDB tables. Create them in a practice database:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(40) NOT NULL,
    available_qty INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;

CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_status_amount (order_status, total_amount),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO inventory (sku, available_qty, unit_price)
VALUES ('KB-01', 10, 1250000.00);

INSERT INTO customer (customer_id, full_name)
VALUES
    (101, 'Nguyễn An'),
    (102, 'Trần Bình');

INSERT INTO sales_order (
    order_id, customer_id, order_status, total_amount
)
VALUES
    (1001, 101, 'completed', 1250000.00),
    (1002, 101, 'completed', 5200000.00),
    (1003, 101, 'pending',    890000.00),
    (1004, 101, 'completed', 1500000.00),
    (1005, 102, 'completed', 3400000.00);
~~~

The JOIN and order-counting queries later on use this exact structure. With the condition completed and total amount from 1 million to under 5 million, the initial data has three matching orders.

### 2.2. One SELECT Statement Has One Read View

A SELECT statement can read multiple tables, JOIN, filter, and aggregate. With a consistent nonlocking read, the entire statement uses one consistent read view, rather than each table in the JOIN receiving an independent point in time.

Example:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    SUM(o.total_amount) AS total_spending
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name;
~~~

Under READ COMMITTED, this SELECT reads customer and sales_order using the same statement read view. If another transaction commits an order while the SELECT is running, the current SELECT does not mix pre-commit and post-commit versions simply because it reads two different tables. A subsequent SELECT statement can receive a new read view and see the newly committed order.

### 2.3. Changes by the Current Transaction Remain Visible

The snapshot rule does not hide changes made by the transaction itself.

Example:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 2
WHERE sku = 'KB-01';

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

The SELECT sees the value updated by the current transaction, even though the transaction has not COMMITted yet. This is an intentional exception to the rule of only seeing committed changes from other transactions.

If a transaction updates some rows and then SELECTs a broader set of rows, the result can combine the new rows written by itself with older versions of other rows. Do not view a read view as a uniform physical snapshot of all changes created by the current transaction.

## 3. Configuring READ COMMITTED

There are three configuration scopes you usually need to distinguish: session, next transaction, and global.

### 3.1. Setting for All Subsequent Transactions in a Session

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@autocommit AS autocommit;
~~~

The command above sets READ COMMITTED as the isolation level for subsequent transactions in the current session. It does not change the isolation level of other sessions.

If a transaction is already running, a session change applies to subsequent transactions, not the currently active transaction. For easier testing and to avoid confusion, configure it before START TRANSACTION.

### 3.2. Setting Only for the Next Transaction

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT *
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

Without the SESSION or GLOBAL keyword, SET TRANSACTION applies only to the next transaction in the session. After that transaction finishes, subsequent transactions revert to using the session isolation level.

A scoped-less SET TRANSACTION statement must not be run while a transaction is active.

### 3.3. Setting the Default for New Sessions

~~~sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

A GLOBAL setting affects sessions created afterward. Existing sessions do not automatically change their isolation level.

This operation requires appropriate administrative privileges, typically CONNECTION_ADMIN or the deprecated SUPER privilege. Do not change the server-wide default just to test a query. In applications, configuring per session or per transaction is usually easier to control.

### 3.4. Checking the Effective Value

~~~sql
SELECT
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.transaction_isolation AS session_isolation,
    @@autocommit AS autocommit;
~~~

MySQL typically displays isolation level names in hyphenated form, such as READ-COMMITTED or REPEATABLE-READ.

You can check separately:

~~~sql
SHOW VARIABLES LIKE 'transaction_isolation';
SHOW SESSION VARIABLES LIKE 'transaction_isolation';
~~~

Do not confuse the GLOBAL value with the SESSION value. A session can use READ COMMITTED even while the server-wide default remains REPEATABLE READ.

## 4. Two-Session Experiment: Second SELECT Sees New Commit

The inventory table was created in section 2.1. If rerunning the experiment, reset the quantity to 10 before opening two sessions:

~~~sql
UPDATE inventory
SET available_qty = 10
WHERE sku = 'KB-01';

SELECT *
FROM inventory
WHERE sku = 'KB-01';
~~~

Open two independent MySQL connections, called Session A and Session B. Do not share a single connection because two concurrent transactions are needed.

### 4.1. Session A Starts a READ COMMITTED Transaction

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Result:

~~~text
available_qty
--------------
10
~~~

Keep transaction A open.

### 4.2. Session B Updates and Commits

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 8
WHERE sku = 'KB-01';

COMMIT;
~~~

Session B has committed the new value of 8.

### 4.3. Session A Reads Again

Switch back to Session A, still inside the existing transaction:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Result:

~~~text
available_qty
--------------
8
~~~

The second SELECT creates a new read view after B committed and therefore sees the value 8. Transaction A is still a single transaction; the snapshot is refreshed at the SELECT statement level.

Finish:

~~~sql
COMMIT;
~~~

### 4.4. What Does A Read If B Has Not Committed?

Repeat with an initial value of 8.

Session A:

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Initial result is 8. Keep transaction A open.

Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 6
WHERE sku = 'KB-01';

-- Not COMMITted yet.
~~~

A runs SELECT while B has not committed:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

A still reads the previously committed value of 8. A does not read 6 because B has not committed.

After B runs COMMIT, A runs again:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

The result is now 6. End transaction A with COMMIT.

This experiment confirms two distinct characteristics:

- READ COMMITTED does not read uncommitted data.
- READ COMMITTED gets a new snapshot on each consistent read, so it sees new commits between SELECT statements.

## 5. Comparison with REPEATABLE READ

Repeat the same experiment, but switch Session A to REPEATABLE READ.

Reset the data to state 8 before opening two transactions:

~~~sql
UPDATE inventory
SET available_qty = 8
WHERE sku = 'KB-01';
~~~

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

Suppose the result is 8. This SELECT creates the snapshot for consistent reads in the transaction.

Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_qty = 6
WHERE sku = 'KB-01';

COMMIT;
~~~

Session A reads again:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

A still sees 8 because the subsequent consistent read uses the snapshot created on the first read. After A COMMITs and starts a new transaction, SELECT will see 6.

### 5.1. Comparison Table

| Characteristic | READ COMMITTED | REPEATABLE READ |
|---|---|---|
| Consistent read snapshot | New for each SELECT statement | Created at the first consistent read in the transaction |
| Two SELECTs in the same transaction | Can see newly committed data between the two statements | Both see the established snapshot |
| Dirty read | No | No |
| Non-repeatable read | Possible | Does not occur between consistent reads in the same transaction |
| Phantom with repeated consistent reads | Possible | Does not appear because the snapshot is kept stable |
| Gap locks for ordinary searches | Disabled, except for FK and duplicate key checks | Can use gap/next-key locks for range locking operations |
| InnoDB default level | No | Yes |

READ COMMITTED prioritizes each read statement seeing the latest committed data as of the time the read statement starts. REPEATABLE READ prioritizes a stable view for multiple consistent read statements within the same transaction.

Neither level is always better in every case. The choice depends on whether the application needs the latest data on each read or needs multiple reads to observe the same stable logical state.

## 6. Non-Repeatable Read and Phantom Read

READ COMMITTED prevents dirty reads, but permits two other phenomena because the snapshot is refreshed between SELECT statements.

### 6.1. Non-Repeatable Read

A non-repeatable read occurs when the same SELECT statement is run again within a transaction and a row's value has changed due to another transaction committing.

Example:

1. A SELECTs the inventory quantity of KB-01 and receives 10.
2. B UPDATEs the quantity to 8 and COMMITs.
3. A reruns the same SELECT and receives 8.

A read the same primary key with the same condition, yet received a different value.

This is expected behavior under READ COMMITTED. If business logic needs to read the same value across multiple steps of a transaction, consider REPEATABLE READ or an appropriate locking strategy.

### 6.2. Phantom Read

A phantom read occurs when a range-condition query is run again and rows appear or disappear due to another transaction committing.

Suppose A counts completed orders with total amount from 1 million to under 5 million:

To rerun the experiment, delete the test row with order_id = 1006 if it was inserted in a previous run:

~~~sql
DELETE FROM sales_order
WHERE order_id = 1006;
~~~

Session A:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 5000000;
~~~

The initial result is 3. Session B inserts a new matching order and COMMITs:

~~~sql
START TRANSACTION;

INSERT INTO sales_order (
    order_id, customer_id, order_status, total_amount
)
VALUES (1006, 102, 'completed', 2000000.00);

COMMIT;
~~~

Session A reruns the same SELECT:

~~~sql
SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 5000000;
~~~

The result is now 4. End transaction A with COMMIT.

The new row is a phantom relative to the previous read. READ COMMITTED allows this because the second SELECT receives a new read view.

### 6.3. Two-Session Illustration

~~~mermaid
sequenceDiagram
    participant A as Session A (READ COMMITTED)
    participant B as Session B
    A->>A: SELECT COUNT(*) WHERE total_amount >= 1000000
    Note over A: Result 3
    B->>B: INSERT new matching order
    B->>B: COMMIT
    A->>A: Rerun the same SELECT
    Note over A: Result 4
~~~

If you need a multi-SELECT report with a single shared view of the data, READ COMMITTED may not be appropriate. Consider a REPEATABLE READ transaction for the consistent reads, or combine the calculations into a single SELECT if possible.

## 7. Consistent Read and Locking Read Are Two Different Mechanisms

Not every SELECT uses snapshots in the same way.

### 7.1. Consistent Nonlocking Read

An ordinary SELECT in InnoDB under READ COMMITTED is a consistent read:

~~~sql
SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';
~~~

It reads the version matching the read view and does not place row locks on the read rows. Other transactions can still UPDATE or DELETE that row while the read executes.

This mechanism is suitable for display, reporting, and reading data without needing to retain row-modification locks after reading.

### 7.2. Locking Read with FOR SHARE

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01'
FOR SHARE;

-- Perform work that needs to protect the read row.

COMMIT;
~~~

FOR SHARE places shared locks on the read rows. Other sessions can read, but cannot modify the shared-locked rows until the transaction ends.

If a row is currently being modified by another uncommitted transaction, SELECT ... FOR SHARE may have to wait for that transaction to finish before reading the latest value.

### 7.3. Locking Read with FOR UPDATE

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01'
FOR UPDATE;

UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01';

COMMIT;
~~~

FOR UPDATE locks the index records found by the query in a manner similar to an UPDATE operation. It fits a read-then-update-same-row flow when you must prevent other sessions from modifying that row before the current transaction completes.

Locking reads require an open transaction; with autocommit enabled, use START TRANSACTION so the lock is held across the work requiring protection.

### 7.4. Comparing the Two Read Types

| Criterion | Ordinary SELECT | SELECT ... FOR SHARE / FOR UPDATE |
|---|---|---|
| Mechanism | Consistent read via MVCC | Locking read, reads current state |
| Row lock | Does not place row locks | Places shared or exclusive locks |
| Can wait for writers? | Typically does not wait on writer row locks | Can wait on transactions holding conflicting locks |
| Purpose | Reading without locking rows | Reading and protecting rows for subsequent operations |
| Lock hold duration | No row locks from consistent read | Until COMMIT or ROLLBACK |

Do not add FOR UPDATE just to "read the latest data." It changes concurrency behavior by taking locks and can make other sessions wait. When you need a fresh snapshot on each SELECT, READ COMMITTED already provides that behavior for consistent reads.

## 8. Gap Locks and Phantoms in READ COMMITTED

Under READ COMMITTED, InnoDB disables gap locking for ordinary search and index scan operations. For locking reads, UPDATE, and DELETE, InnoDB locks index records rather than locking the gaps before records. Gap locks are still used for foreign key and duplicate key checks.

This has an important consequence: another transaction can insert new rows into the gap a range query cares about. Thus, phantom rows can appear between two SELECT statements.

Session A example:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;

SELECT *
FROM sales_order
WHERE order_status = 'completed'
  AND total_amount >= 1000000
  AND total_amount < 2000000
FOR UPDATE;
~~~

Session B can insert a new row with total_amount = 1500000 if no other constraint or conflicting lock prevents it. A does not hold a gap lock for that value range simply because the isolation level is READ COMMITTED.

This does not mean READ COMMITTED uses no locks. Matching rows found by UPDATE/DELETE or a locking read can still be locked. The difference is that gaps between index records are not locked as in the next-key locking mechanism commonly seen in REPEATABLE READ.

If business logic must prevent new inserts into a data range, re-evaluate the isolation level, locking query type, indexes, and constraints. Do not assume FOR UPDATE under READ COMMITTED will prevent all phantom inserts.

## 9. How READ COMMITTED Affects UPDATE and DELETE

READ COMMITTED does not only alter SELECT consistent reads. It also affects how InnoDB holds row locks during UPDATE and DELETE.

### 9.1. Locking Rows Actually Modified

For UPDATE or DELETE, InnoDB keeps locks for the rows that are updated or deleted. Record locks on rows not matching the WHERE condition are released after MySQL evaluates the condition.

This can reduce the number of held locks and reduce deadlock likelihood compared to REPEATABLE READ in some workloads. However, deadlocks can still occur if transactions lock multiple rows in different orders.

### 9.2. Semi-Consistent Read in UPDATE

When an UPDATE encounters a row currently locked by another transaction, InnoDB can perform a semi-consistent read under READ COMMITTED. It provides the latest committed version to MySQL to evaluate whether the row matches WHERE.

- If the row does not match WHERE, InnoDB can skip it and not hold a lock on that row.
- If the row matches WHERE, MySQL re-reads the row and InnoDB acquires the required lock or waits for the lock.

This is an important internal detail when analyzing concurrent UPDATEs. It does not mean UPDATE is allowed to overwrite uncommitted data or bypass lock control.

### 9.3. UPDATE and DELETE Are Not Ordinary Consistent Reads

Do not infer that UPDATE/DELETE will use the same snapshot as an earlier ordinary SELECT in the transaction. DML statements must locate current rows and acquire locks to modify data.

Example:

~~~sql
START TRANSACTION;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

-- Another transaction can update and COMMIT here.

UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01';

COMMIT;
~~~

SELECT and UPDATE are not an automatically protected check-then-write operation. If business logic depends on the initially read value, use a locking read or write an atomic conditional UPDATE:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 1
WHERE sku = 'KB-01'
  AND available_qty >= 1;
~~~

Then check the number of affected rows. If no rows were updated, stock was insufficient or the condition was no longer true at UPDATE time. This approach avoids the gap between a checking SELECT and a writing UPDATE.

## 10. READ COMMITTED and WITH CONSISTENT SNAPSHOT

MySQL supports:

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;
~~~

This option only takes effect to create a consistent snapshot with InnoDB when the current isolation level is REPEATABLE READ. It does not change the isolation level.

If you are using READ COMMITTED, the WITH CONSISTENT SNAPSHOT clause is ignored and MySQL emits a warning. It does not turn SELECT statements in the transaction into a shared snapshot.

Example:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION WITH CONSISTENT SNAPSHOT;

SHOW WARNINGS;

SELECT available_qty
FROM inventory
WHERE sku = 'KB-01';

COMMIT;
~~~

To have a stable snapshot across multiple consistent reads, use REPEATABLE READ and create the read view appropriately. Do not rely on WITH CONSISTENT SNAPSHOT when the transaction is under READ COMMITTED.

## 11. READ COMMITTED and Binary Log / Replication

When using READ COMMITTED with InnoDB and binary logging, MySQL only supports row-based binary logging.

If binlog_format is configured as MIXED, the server automatically uses row-based logging for READ COMMITTED. Statement-based logging is not supported for this isolation level.

Check configuration:

~~~sql
SELECT
    @@GLOBAL.log_bin AS log_bin,
    @@GLOBAL.binlog_format AS global_binlog_format,
    @@SESSION.binlog_format AS session_binlog_format;
~~~

In MySQL 8.4, binlog_format has been deprecated and row-based logging is the recommended choice for new replication setups. When changing the isolation level in an environment with replication, verify source/replica configuration, binlog format, and operational procedures before deploying.

Do not simply change the isolation level on one server and ignore binary log compatibility. Replication configuration must align with the system's version and logging policy.

## 12. When Should You Choose READ COMMITTED?

READ COMMITTED is useful when an application wants each read statement to see the latest committed changes without maintaining the same snapshot across multiple SELECT statements in a transaction.

Cases worth considering:

- Short transactions that read data multiple times and want to see new commits between reads.
- Workloads with many UPDATE/DELETE statements wanting to reduce lock hold duration on non-matching rows.
- Status display queries needing updates per request or per statement.
- Systems where non-repeatable reads and phantom reads are acceptable per business requirements.

Exercise caution with:

- Multi-SELECT reports requiring a single shared view of the data.
- Workflows checking multiple rows before deciding to update.
- Tasks needing to prevent phantom inserts into a data range.
- Business flows depending on a value read earlier in the transaction.

### 12.1. Multi-Step Reports

Suppose a report runs two SELECT statements:

~~~sql
START TRANSACTION;

SELECT SUM(total_amount) AS revenue
FROM sales_order
WHERE order_status = 'completed';

SELECT COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed';

COMMIT;
~~~

Under READ COMMITTED, another transaction can commit a completed order between the two SELECT statements. revenue and order_count can be calculated on two different data sets.

If the report requires both metrics to reflect the exact same point in time, you can combine them into one SELECT:

~~~sql
SELECT
    SUM(total_amount) AS revenue,
    COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed';
~~~

Or use REPEATABLE READ for multi-step read transactions requiring the same snapshot. Choose the solution based on the report's consistency requirements.

### 12.2. Read-Then-Write Workflows

If an application follows this pattern:

1. SELECT inventory quantity.
2. Check if quantity is sufficient.
3. UPDATE to deduct inventory.

then READ COMMITTED does not automatically lock the row after SELECT. Another transaction can change the quantity before the UPDATE step.

There are two common approaches:

- Use SELECT ... FOR UPDATE inside the transaction to lock the row to be checked and updated.
- Use a conditional UPDATE in a single statement and check affected rows.

Example:

~~~sql
UPDATE inventory
SET available_qty = available_qty - 2
WHERE sku = 'KB-01'
  AND available_qty >= 2;
~~~

The UPDATE only deducts stock when the condition still holds at execution time. If affected rows equals 0, the application handles the insufficient-stock or missing-SKU case.

## 13. Verification and Diagnostics During Deployment

Before changing the isolation level, check the current values:

~~~sql
SELECT
    @@GLOBAL.transaction_isolation,
    @@SESSION.transaction_isolation,
    @@autocommit;
~~~

Check binary logging if enabled:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
~~~

Inspect running transactions and their lifetimes:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

If you need to inspect waiting locks, you can query Performance Schema:

~~~sql
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
FROM performance_schema.data_locks
ORDER BY OBJECT_SCHEMA, OBJECT_NAME, LOCK_STATUS;
~~~

Diagnostic queries require the corresponding metadata read privileges. Do not conclude a transaction is hung solely from its start time; cross-reference the query, wait state, owning application connection, and related locks.

### 13.1. Checking Actual Sessions of a Connection Pool

Applications typically use a connection pool. Isolation level is a session property, so each connection can hold its own session setting.

If an application only configures one connection while the pool creates multiple connections, requests can run under different isolation levels. Configure it upon initializing each connection or set explicit transaction characteristics before each transaction according to application policy.

Do not assume changing GLOBAL will update open pooled connections. Existing sessions keep their session values until explicitly changed or the connections are recreated.

## 14. Common Errors and Misconceptions

| Misconception or Error | Consequence | How to Handle |
|---|---|---|
| Thinking READ COMMITTED only creates one snapshot at START TRANSACTION | Overlooking the fresh snapshot on each SELECT | Remember each consistent read gets its own read view |
| Thinking a second SELECT must return the same result as the first SELECT | Failing to recognize non-repeatable reads | Check if another transaction committed between the two statements |
| Thinking READ COMMITTED allows dirty reads | Misunderstanding uncommitted data | READ COMMITTED only reads appropriate committed versions |
| Thinking ordinary SELECT locks rows | Expecting writers to wait on readers | Consistent reads do not place row locks |
| Using FOR UPDATE just to read the latest data | Creates unnecessary locks and reduces concurrency | Use READ COMMITTED for fresh snapshots; locking reads only when rows need protection |
| Thinking FOR UPDATE prevents all phantoms in READ COMMITTED | May miss inserts into gaps | Gap locking for ordinary searches is disabled under READ COMMITTED |
| Setting isolation level after a transaction starts expecting it to change the current transaction | Unexpected test results | Set before START TRANSACTION; SESSION setting applies only to subsequent transactions |
| Using WITH CONSISTENT SNAPSHOT in READ COMMITTED | Receives a warning and gets no transaction-wide snapshot | Use REPEATABLE READ if a shared snapshot is needed |
| Changing isolation level without checking binlog | May be incompatible with statement-based logging | Verify row-based logging and replication |
| Assuming READ COMMITTED uses no locks | Underestimating UPDATE/DELETE conflicts | DML and locking reads still acquire record locks |
| Using multiple SELECTs to build a consistent report | Metrics may see different snapshots | Combine into one SELECT or use REPEATABLE READ |

## 15. Testing Procedure for READ COMMITTED

When you need to verify behavior on a MySQL instance, follow this sequence:

1. Create a small InnoDB table with one row accessed by two sessions.
2. Confirm the isolation level of each session using @@SESSION.transaction_isolation.
3. Set Session A to READ COMMITTED and start a transaction.
4. A SELECTs a row to record the initial value.
5. B UPDATEs the same row without COMMITting.
6. A SELECTs again to confirm it does not read uncommitted data.
7. B COMMITs.
8. A SELECTs once more to confirm the new snapshot sees the commit.
9. Repeat with REPEATABLE READ to compare.
10. Try INSERTing a new row matching a range condition and observe phantoms.
11. Try SELECT ... FOR UPDATE in a separate transaction to observe locking reads.
12. End all transactions and restore the practice data.

You can use the following diagram to remember the selection process:

~~~mermaid
flowchart TD
    A[Application needs to read data] --> B{Must multiple SELECTs share the same snapshot?}
    B -->|Yes| C[REPEATABLE READ or a single SELECT]
    B -->|No| D{Need to lock rows before writing?}
    D -->|Yes| E[READ COMMITTED with locking read or conditional UPDATE]
    D -->|No| F[READ COMMITTED consistent read]
    C --> G[Verify business consistency]
    E --> G
    F --> G
~~~

## 16. Practice Exercises

### Exercise 1: Set Session Isolation Level

Set the session to READ COMMITTED. Query @@SESSION.transaction_isolation and verify the value. Start a new transaction and run a SELECT.

### Exercise 2: Observe Fresh Snapshots

Open two sessions. A reads inventory quantity; B updates and COMMITs; A reads again in the existing transaction. Record both results and explain the new read view.

### Exercise 3: No Reading Dirty Data

B updates a row without COMMITting. A runs an ordinary SELECT. Confirm A still sees the previously committed value. Then B ROLLBACKs and verify again.

### Exercise 4: Compare REPEATABLE READ

Rerun Exercise 2 under REPEATABLE READ. Confirm both SELECTs in the same transaction share the same snapshot. COMMIT A, then open a new transaction to see the new value.

### Exercise 5: Observe Non-Repeatable Read

A reads the same row twice. B updates the value between the two reads and COMMITs. Explain why the results differ without being a dirty read.

### Exercise 6: Observe Phantom Read

A counts orders within a total_amount range. B inserts a new matching order and COMMITs. A reruns the query and notes the row count changed.

### Exercise 7: Compare Consistent Read and Locking Read

A runs an ordinary SELECT, then B UPDATEs the same row and COMMITs. Repeat using SELECT ... FOR SHARE inside a transaction. Observe the differences in locking and read timing.

### Exercise 8: Inspect Gap Locks

Under READ COMMITTED, A runs SELECT ... FOR UPDATE on a value range. B tries to INSERT a row into that gap. Observe that gap locking for ordinary searches is disabled, while also checking that constraints and indexes can create other locks.

### Exercise 9: Safe Inventory Deduction

Write two approaches: SELECT ... FOR UPDATE followed by UPDATE; and a conditional UPDATE with available_qty >= quantity. Compare affected rows and how two concurrent requests are handled.

### Exercise 10: Multi-SELECT Reports

Create a transaction that reads SUM and COUNT in two SELECT statements. Have another session commit an order between the two statements. Observe that the two metrics can diverge across snapshots. Rewrite it as a single SELECT returning both SUM and COUNT.

### Exercise 11: Check Replication Configuration

Query log_bin and binlog_format. Explain why READ COMMITTED requires row-based logging and how MIXED is handled.

### Exercise 12: Evaluate Isolation Level for an Application

Choose a real business workflow. Determine whether it needs a fresh snapshot per read, a stable snapshot within the transaction, or row locking before writing. Recommend an appropriate isolation level and locking approach, explaining which anomalies are acceptable.

## Conclusion

READ COMMITTED uses MVCC so each consistent read receives a new read view. A transaction can see committed changes between two SELECT statements, yet still never read uncommitted data. This behavior suits applications needing current data per statement that can accept non-repeatable reads or phantom reads.

When multiple read statements must see the same stable data state, REPEATABLE READ is usually more appropriate. When rows must be protected for read-then-update, use a locking read or a conditional UPDATE statement. READ COMMITTED still uses record locks for write operations and locking reads; it only disables gap locking for ordinary searches, except for foreign key and duplicate key checks. Finally, verify session isolation levels and row-based binary logging before deploying in an environment with replication.

## References

- MySQL 8.4 Reference Manual — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 Reference Manual — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
- MySQL 8.4 Reference Manual — Locking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- MySQL 8.4 Reference Manual — SET TRANSACTION Statement: https://dev.mysql.com/doc/refman/8.4/en/set-transaction.html
- MySQL 8.4 Reference Manual — START TRANSACTION, COMMIT, and ROLLBACK: https://dev.mysql.com/doc/refman/8.4/en/commit.html
- MySQL 8.4 Reference Manual — Binary Logging Options and Variables: https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html
- MySQL 8.4 Reference Manual — InnoDB Locking: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html
