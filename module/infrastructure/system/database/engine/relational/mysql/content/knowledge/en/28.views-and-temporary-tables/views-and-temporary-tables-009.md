# Transactions, CREATE/DROP TEMPORARY TABLE, and Rollback Limits

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, authorization, backup, and handling relational database operational issues. Temporary tables are often used to collect intermediate data, normalize multi-step results, prepare key sets for processing, or stage data for reporting. When combining temporary tables with transactions, you must distinguish table lifecycle, data rollback capability, and commit boundaries introduced by each SQL statement.

In MySQL, an InnoDB transaction can roll back transactional data modifications, but it cannot roll back creating or dropping a temporary table. A common point of confusion is that CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not trigger an implicit commit, yet the creation/dropping of the temporary table itself cannot be undone by ROLLBACK. DML data inside an InnoDB temporary table can be rolled back just like ordinary InnoDB data. To design safe workflows, you must separately understand three layers: transactions, session-scoped temporary objects, and the table's storage engine.

## 1. Transactions in MySQL and Rollback Scope

A transaction is a group of data operations processed as a single logical unit. With InnoDB, transactions provide ACID properties:

- **Atomicity:** transactional changes commit together or roll back together.
- **Consistency:** the application and data constraints must transition the database from one valid state to another.
- **Isolation:** concurrent transactions observe and affect data according to the isolation level.
- **Durability:** committed changes are protected according to MySQL and storage system durability settings.

Example transferring funds between two accounts:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

COMMIT;
~~~

If the second operation fails due to an application-handled error, the application can ROLLBACK to undo the first debit operation. A transaction only protects changes belonging to a transactional storage engine and still within the current transaction.

### 1.1. Autocommit

MySQL usually enables autocommit per session:

~~~sql
SELECT @@SESSION.autocommit;
~~~

When autocommit = 1, each standalone transactional statement commits upon successful completion if no explicit transaction is open. When multiple statements must be grouped together, start a transaction:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 501, 1);

COMMIT;
~~~

START TRANSACTION starts an explicit transaction. COMMIT confirms changes; ROLLBACK discards uncommitted transactional changes. Do not confuse creating a temporary table with starting or ending a transaction.

### 1.2. COMMIT and ROLLBACK

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

ROLLBACK;
~~~

After ROLLBACK, the uncommitted status change in the InnoDB transaction is undone. If COMMIT is used instead of ROLLBACK, the change becomes confirmed data.

A transaction can end because:

- The application issues COMMIT or ROLLBACK.
- A statement triggers an implicit commit.
- The session ends or the connection closes; uncommitted transactions are typically rolled back by the server.
- The server crashes; InnoDB recovery restores transactional state based on redo/undo logs and commit status.

Applications must still handle connection errors with unknown commit outcomes: if the connection drops immediately after sending COMMIT, the client may not know whether the server committed or not. Design idempotent retries or business state lookups.

## 2. Temporary Tables Are Session-Scoped Objects

Temporary tables in MySQL are created with CREATE TEMPORARY TABLE. The table is visible only within the session that created it and disappears automatically when the session ends.

~~~sql
CREATE TEMPORARY TABLE tmp_selected_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_tmp_customer (customer_id)
) ENGINE = InnoDB;
~~~

Points to remember:

- The session that created the table can read and write to it.
- Other sessions cannot see this temporary table, even when using the same database.
- Two sessions can create temporary tables with the same name without conflict because each table belongs to its own session.
- The table is automatically dropped when the session closes.
- A temporary table can persist across multiple transactions within the same session.
- Running COMMIT or ROLLBACK does not automatically end a temporary table's lifecycle.

### 2.1. Transactions and Sessions Are Two Distinct Scopes

One session can run multiple consecutive transactions while keeping the same temporary table:

~~~sql
CREATE TEMPORARY TABLE tmp_work (
    item_id BIGINT NOT NULL PRIMARY KEY,
    state VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;
INSERT INTO tmp_work (item_id, state)
VALUES (1, 'READY');
COMMIT;

START TRANSACTION;
UPDATE tmp_work
SET state = 'DONE'
WHERE item_id = 1;
ROLLBACK;

SELECT item_id, state
FROM tmp_work;
~~~

The final result still contains the row (1, 'READY'): the first transaction committed; the second transaction rolled back; the temporary table remains in the session.

### 2.2. Temporary Tables Can Shadow Regular Tables of the Same Name

If a session creates a temporary table with the same name as a permanent table, within that session the table name points to the temporary table. Other sessions still see the permanent table.

For example, if the schema already has a regular table orders, a session can create:

~~~sql
CREATE TEMPORARY TABLE orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    note VARCHAR(100)
) ENGINE = InnoDB;
~~~

Thereafter, SELECT * FROM orders in the current session reads the temporary table. This naming practice easily causes confusion while debugging and can make statements accidentally modify the wrong object. Use a clear prefix like tmp_ or work_, and avoid colliding with business table names.

### 2.3. DROP TEMPORARY TABLE

Drop the temporary table explicitly with:

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_selected_orders;
~~~

The TEMPORARY keyword limits the operation to temporary tables. Using IF EXISTS makes cleanup safe when the table may not have been created or was already dropped in an earlier branch.

Do not rely on connection closure for cleanup in applications using connection pools. Connections may be reused for other requests before the session actually closes. Actively drop temporary tables in both success and failure paths.

## 3. Storage Engine Determines DML Rollback

A temporary table is a session-scoped temporary object; rollback capability for data inside it depends on its storage engine.

### 3.1. InnoDB

Explicitly declare ENGINE = InnoDB when transactional DML is needed:

~~~sql
CREATE TEMPORARY TABLE tmp_batch (
    row_id BIGINT NOT NULL PRIMARY KEY,
    result_value DECIMAL(14,2) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_batch (row_id, result_value)
VALUES (1, 10.00), (2, 20.00);

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM tmp_batch;
~~~

The remaining_rows result is 0 because the INSERT belonged to an InnoDB transaction that rolled back. The tmp_batch table still exists because creating the temporary table is not rolled back.

### 3.2. MEMORY

Temporary tables can also use MEMORY:

~~~sql
CREATE TEMPORARY TABLE tmp_lookup (
    lookup_id BIGINT NOT NULL PRIMARY KEY,
    lookup_value VARCHAR(100) NOT NULL
) ENGINE = MEMORY;
~~~

MEMORY does not provide transaction rollback like InnoDB. DML on MEMORY tables is not undone by ROLLBACK. MEMORY tables store data in RAM and have limitations on size, data types, indexes, and behavior upon server shutdown. Only use it when the workload fits and data can be regenerated.

### 3.3. Do Not Let the Default Engine Dictate Unintended Semantics

If a workflow relies on rollback, explicitly specify InnoDB instead of assuming the default storage engine or server configuration is always identical. Check the engine:

~~~sql
SHOW CREATE TABLE tmp_batch;
~~~

A workflow might work properly with an InnoDB temporary table yet behave differently with a MEMORY temporary table. The engine is part of transaction design.

## 4. CREATE/DROP TEMPORARY TABLE and Implicit Commit

This is the most important rule of the lesson:

**CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not cause an implicit commit, yet creating/dropping a temporary table cannot be rolled back.**

This exception differs from regular CREATE TABLE or DROP TABLE statements. Regular DDL statements can trigger an implicit commit and alter transaction boundaries.

### 4.1. CREATE TEMPORARY TABLE Does Not Commit an Open Transaction

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

CREATE TEMPORARY TABLE tmp_transaction_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;
~~~

CREATE TEMPORARY TABLE does not automatically commit the change to accounts. ROLLBACK still undoes the UPDATE. However, the temporary table was created and continues to exist in the session after ROLLBACK.

### 4.2. DROP TEMPORARY TABLE Does Not Commit an Open Transaction

~~~sql
CREATE TEMPORARY TABLE tmp_drop_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_drop_probe (probe_id)
VALUES (1);

DROP TEMPORARY TABLE tmp_drop_probe;

ROLLBACK;
~~~

DROP TEMPORARY TABLE does not trigger an implicit commit, yet dropping the table cannot be rolled back. After ROLLBACK, the table remains dropped; the object cannot be restored simply via ROLLBACK.

### 4.3. Regular CREATE TABLE Triggers an Implicit Commit

Compare:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

CREATE TABLE permanent_probe (
    probe_id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;
~~~

A regular CREATE TABLE triggers an implicit commit. The UPDATE prior to the DDL has already been committed before CREATE TABLE executes. The subsequent ROLLBACK cannot undo the committed change, nor does it remove the newly created permanent table.

Do not place permanent DDL in the middle of a business transaction if the application expects to roll back all prior changes.

### 4.4. Other DDL Statements Can Still Trigger Implicit Commits

The exception for CREATE/DROP TEMPORARY TABLE does not make all DDL involving temporary tables transactional. Statements such as ALTER TABLE, CREATE INDEX, DROP INDEX, and TRUNCATE TABLE belong to the group requiring attention regarding implicit commits under MySQL rules.

Before placing DDL inside a transaction, verify the semantics of the exact statement and MySQL version. Do not infer that an operation is transaction-safe on temporary tables merely because CREATE/DROP TEMPORARY TABLE does not implicitly commit.

### 4.5. Atomic DDL Is Not User-Transaction Rollback

MySQL supports atomic DDL for supported operations and storage engines, ensuring a DDL statement either completes intact or recovers cleanly after a crash. That does not mean users can place CREATE TABLE or ALTER TABLE inside a transaction and use ROLLBACK to undo the DDL. Atomic DDL and transaction rollback are two different mechanisms.

## 5. Behavior Matrix to Distinguish

| Operation | Implicit Commit? | Does ROLLBACK Undo the Object? | Notes |
|---|---|---|---|
| INSERT into InnoDB temporary | No, if transaction is open | Not applicable | DML is rolled back |
| UPDATE InnoDB temporary | No, if transaction is open | Not applicable | DML is rolled back |
| DELETE from InnoDB temporary | No, if transaction is open | Not applicable | DML is rolled back |
| CREATE TEMPORARY TABLE | No | No | Table remains after rollback |
| DROP TEMPORARY TABLE | No | No | Table remains dropped after rollback |
| Regular CREATE TABLE | Yes | No | DDL and commit boundary |
| Regular DROP TABLE | Yes | No | DDL and commit boundary |
| ALTER TABLE | Yes | No | Check specific statement |
| CREATE INDEX / DROP INDEX | Yes | No | Not treated as DML |
| TRUNCATE TABLE | Yes | No | Do not use like transactional DELETE |
| INSERT into MEMORY table | Not in the transactional DML commit sense | No | Engine does not support DML rollback |

This matrix is a quick reference. When designing migrations or complex transactions, consult the implicit commit list for the running MySQL version and actual engine.

## 6. Creating Temporary Tables from Query Data

Temporary tables are commonly used to store intermediate results across multiple statements.

### 6.1. Create Structure Then INSERT

~~~sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(18,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_customer_totals (
    customer_id,
    order_count,
    revenue
)
SELECT
    customer_id,
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

This allows defining data types, keys, and indexes explicitly before loading data.

### 6.2. CREATE TEMPORARY TABLE ... AS SELECT

You can create a temporary table from a SELECT result:

~~~sql
CREATE TEMPORARY TABLE tmp_paid_orders
ENGINE = InnoDB
AS
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID';
~~~

This is concise for materializing a result set. Do not assume the created table automatically gets a primary key or optimal indexes for subsequent steps. If later queries join on customer_id, you may need to add indexes:

~~~sql
ALTER TABLE tmp_paid_orders
ADD PRIMARY KEY (order_id),
ADD KEY ix_tmp_paid_customer (customer_id);
~~~

Note: ALTER TABLE and similar DDL have their own implicit commit semantics. Do not place them mid-way inside a business transaction needing rollback without evaluating the impact.

### 6.3. CREATE TEMPORARY TABLE LIKE

You can copy a table's structure:

~~~sql
CREATE TEMPORARY TABLE tmp_orders LIKE orders;
~~~

LIKE copies the structure and indexes of the source table according to MySQL rules. It does not copy data rows. The temporary table still belongs to the current session.

Do not use LIKE blindly if the source table has complex structures, generated columns, partitioning, or attributes that temporary tables do not support identically. Inspect SHOW CREATE TABLE when verification is needed.

## 7. Batch Processing Workflow with Temporary Tables

A common pattern is building a set of keys to process, validating data, and then updating main tables inside a transaction.

### 7.1. Prepare the Key Set

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;

CREATE TEMPORARY TABLE tmp_order_batch (
    order_id BIGINT NOT NULL PRIMARY KEY,
    expected_status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_order_batch (order_id, expected_status)
VALUES
    (9001, 'PENDING'),
    (9002, 'PENDING'),
    (9003, 'PENDING');
~~~

The batch set has a primary key to avoid duplicate order_ids. If batch data comes from a file or staging table, it can be loaded via INSERT ... SELECT and row counts verified before processing.

### 7.2. Validate Before Updating

~~~sql
SELECT
    b.order_id,
    b.expected_status,
    o.status AS current_status
FROM tmp_order_batch AS b
LEFT JOIN orders AS o
  ON o.order_id = b.order_id;
~~~

Check for missing keys, mismatched statuses, or data failing business conditions. If the batch is invalid, halt before updating.

### 7.3. Conditional Update Inside a Transaction

~~~sql
START TRANSACTION;

UPDATE orders AS o
JOIN tmp_order_batch AS b
  ON b.order_id = o.order_id
SET o.status = 'PROCESSING'
WHERE o.status = b.expected_status;

COMMIT;
~~~

The expected old status condition prevents updating a row that changed since the batch was prepared. The application should check affected row counts and define a policy if fewer rows are updated than exist in the batch.

### 7.4. Cleanup

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
~~~

Perform cleanup after completion. On error, clean up in the application's finally branch or appropriate handler. Never leave temporary tables lingering in a connection pool to be accidentally used by the next request.

## 8. Temporary Tables and SAVEPOINT

SAVEPOINT allows rolling back a portion of transactional changes within the same transaction:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

SAVEPOINT after_inventory;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 501, 1);

ROLLBACK TO SAVEPOINT after_inventory;

COMMIT;
~~~

After ROLLBACK TO SAVEPOINT, the INSERT after the savepoint is undone; the UPDATE before the savepoint still commits. SAVEPOINT controls only transactional changes. It cannot restore a DROPped temporary table or remove a temporary table created after the savepoint.

### 8.1. Example Combining SAVEPOINT and Temporary Tables

~~~sql
CREATE TEMPORARY TABLE tmp_savepoint_demo (
    id INT NOT NULL PRIMARY KEY,
    value_text VARCHAR(30) NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO tmp_savepoint_demo VALUES (1, 'before');
SAVEPOINT sp_one;
INSERT INTO tmp_savepoint_demo VALUES (2, 'after');

ROLLBACK TO SAVEPOINT sp_one;
COMMIT;

SELECT * FROM tmp_savepoint_demo;
~~~

The result contains row id 1 and not row id 2. The temporary table still exists because SAVEPOINT and COMMIT do not drop the object.

## 9. Isolation and Temporary Table Visibility

Isolation levels control how transactions observe transactional data across sessions. They do not change the session-scoping rules of temporary tables.

### 9.1. Only the Creating Session Sees the Table

Session A:

~~~sql
CREATE TEMPORARY TABLE tmp_private_data (
    id INT NOT NULL PRIMARY KEY,
    note VARCHAR(50) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_private_data VALUES (1, 'session A');
SELECT * FROM tmp_private_data;
~~~

Session A can read the created row.

### 9.2. Other Sessions Cannot See the Temporary Table

Session B:

~~~sql
SELECT * FROM tmp_private_data;
~~~

Session B cannot see Session A's temporary table. If a permanent table with the same name exists in the schema, Session B reads that permanent table. Thus, the exact same SQL query can access different objects in two sessions.

### 9.3. Temporary Tables Are Not a Cross-Worker Data Sharing Mechanism

If two application connections need to share a dataset, temporary tables are unsuitable because each session has its own private table. Consider a permanent staging table with batch_id, a queue table, or another shared mechanism with proper locks and privileges.

### 9.4. Transaction Isolation Still Applies to InnoDB Tables

DML on InnoDB temporary tables participates in the session's transaction. For permanent InnoDB tables, consistent reads and locking reads obey the active isolation level. Temporary tables do not expose session-private data to other transactions.

Check isolation level:

~~~sql
SELECT @@SESSION.transaction_isolation;
~~~

Do not use temporary tables to replace locks, constraints, or isolation when multiple sessions concurrently update shared business data.

## 10. Common Mistakes When Combining Transactions and Temporary Tables

### 10.1. Thinking ROLLBACK Drops a Newly Created Table

~~~sql
START TRANSACTION;
CREATE TEMPORARY TABLE tmp_example (id INT) ENGINE = InnoDB;
ROLLBACK;
~~~

The tmp_example table remains in the session. To remove it, explicitly call DROP TEMPORARY TABLE.

### 10.2. Thinking DROP TEMPORARY TABLE Can Be Undone

~~~sql
START TRANSACTION;
DROP TEMPORARY TABLE tmp_example;
ROLLBACK;
~~~

ROLLBACK does not restore a dropped table. If temporary data must be retained for retries, defer DROP until the workflow completes.

### 10.3. Using MEMORY and Expecting Rollback

If a temporary table uses MEMORY, DML rollback does not restore data state like InnoDB. Choose the engine based on transaction requirements, not merely the label "temporary table".

### 10.4. Using Regular CREATE TABLE Inside a Business Transaction

Permanent DDL can commit an open transaction. A CREATE TABLE statement can commit earlier changes, rendering a later ROLLBACK ineffective for those changes.

### 10.5. Using TRUNCATE to Clear Data Mid-Transaction

TRUNCATE TABLE has DDL semantics and triggers an implicit commit under MySQL rules. If you need to clear rows in an InnoDB temporary table while retaining rollback capability, use DELETE inside the transaction instead of assuming TRUNCATE is DML.

~~~sql
START TRANSACTION;
DELETE FROM tmp_order_batch;
ROLLBACK;
~~~

With InnoDB, the DELETEd rows are restored after ROLLBACK.

### 10.6. CREATE TEMPORARY TABLE IF NOT EXISTS Does Not Clean an Old Table

If a table of the same name already exists in the session, CREATE TEMPORARY TABLE IF NOT EXISTS neither rebuilds a new structure nor clears old data. It can cause the next request to mistakenly use leftover data from a previous run.

Safer pattern:

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_request_items;

CREATE TEMPORARY TABLE tmp_request_items (
    request_item_id BIGINT NOT NULL PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;
~~~

Only use this pattern when the current session legitimately owns that temporary table name and the application controls the connection lifecycle.

### 10.7. Connection Pools Reusing Sessions

Temporary tables are tied to physical connections, not logical requests. If Request A creates a table and returns the connection to the pool without cleanup, Request B may receive that exact session and see the old table.

Measures:

- Use a dedicated naming convention for temporary names and avoid colliding with business table names.
- Drop the table before creating if the workflow guarantees name ownership.
- Clean up in `finally`, even when a transaction rolls back or throws an exception.
- Do not assume returning a connection to the pool closes the session.
- Clarify whether the pool resets session state; still perform explicit cleanup proactively.

## 11. Error Handling in Stored Procedures and Applications

A workflow using temporary tables typically spans multiple statements. If one statement fails, DML must be rolled back and objects cleaned up in the proper order.

### 11.1. Application Handling Pattern

Pseudocode:

~~~text
borrow one physical connection
try:
    DROP TEMPORARY TABLE IF EXISTS tmp_job_rows
    CREATE TEMPORARY TABLE tmp_job_rows (...) ENGINE=InnoDB
    load rows into tmp_job_rows

    START TRANSACTION
    validate and update permanent InnoDB tables
    COMMIT
catch error:
    if transaction is active:
        ROLLBACK
    rethrow or map the error
finally:
    DROP TEMPORARY TABLE IF EXISTS tmp_job_rows
    return connection to pool
~~~

Cleanup must run on the exact physical connection that created the table. If the connection drops, the session ends and temporary tables are automatically removed; however, the application must still verify whether commit succeeded before retrying business logic.

### 11.2. Handlers in Stored Procedures

A stored procedure can use an EXIT HANDLER to roll back a transaction on error:

~~~sql
DELIMITER //

CREATE PROCEDURE process_order_batch()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
        RESIGNAL;
    END;

    DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;

    CREATE TEMPORARY TABLE tmp_order_batch (
        order_id BIGINT NOT NULL PRIMARY KEY
    ) ENGINE = InnoDB;

    INSERT INTO tmp_order_batch (order_id)
    SELECT order_id
    FROM orders
    WHERE status = 'PENDING';

    START TRANSACTION;

    UPDATE orders AS o
    JOIN tmp_order_batch AS b
      ON b.order_id = o.order_id
    SET o.status = 'PROCESSING'
    WHERE o.status = 'PENDING';

    COMMIT;

    DROP TEMPORARY TABLE IF EXISTS tmp_order_batch;
END//

DELIMITER ;
~~~

This example illustrates error-handling structure; production procedures must explicitly define privileges, transaction ownership, nesting behavior, and whether the session already has a caller-opened transaction. A procedure should not arbitrarily COMMIT/ROLLBACK a transaction managed by its caller.

### 11.3. Do Not Swallow Errors After ROLLBACK

Handlers should use RESIGNAL when errors need to be propagated to the caller. Merely rolling back and returning as if successful can trick the application into thinking the batch was processed when data was never committed.

## 12. Locks, Deadlocks, and Retries

Temporary tables do not eliminate contention on permanent tables. Two sessions can still update the same orders or inventory rows.

Example:

~~~sql
START TRANSACTION;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501
  AND available_quantity > 0;

COMMIT;
~~~

If multiple transactions update rows in different orders, a deadlock can occur. InnoDB picks one transaction as the victim and rolls it back. The application must:

1. Detect deadlock or lock wait timeout errors.
2. Roll back any remaining transaction if the session is still open.
3. Retry the entire business unit with bounded attempts and backoff.
4. Ensure retries are idempotent or guarded by business keys.
5. Clean up temporary tables on the same connection before reuse.

Do not retry only the final statement if prior steps already rolled back or commit outcome is unclear.

## 13. Safe Design Workflow

When combining temporary tables and transactions, follow this checklist:

1. Identify which tables are temporary and which are permanent.
2. Identify the physical session owning the temporary table.
3. Choose the InnoDB engine if DML rollback is needed.
4. Create temporary tables before the business transaction when possible to separate data preparation from updates.
5. If creating or dropping a temporary table inside a transaction, remember object changes cannot be rolled back even though they do not trigger an implicit commit.
6. Avoid permanent DDL inside an open business transaction.
7. Check all statements for implicit commits, especially ALTER, CREATE/DROP INDEX, and TRUNCATE.
8. Use SAVEPOINT only for transactional DML; do not expect it to restore objects.
9. Validate intermediate data and row counts before updating main tables.
10. Commit when all business conditions are met; roll back on error.
11. Clean up temporary tables in both success and error branches.
12. Ensure connection pools do not return sessions with lingering temporary tables or open transactions.
13. Design retries for deadlocks, timeouts, and connections lost right after COMMIT.

## 14. Hands-on Practice: Observing Rollback Limits

Perform this on MySQL 8.0 in a lab database. The exercises use dedicated temporary tables; do not run on production business tables.

### 14.1. Create an InnoDB Temporary Table

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_rollback_lab;

CREATE TEMPORARY TABLE tmp_rollback_lab (
    row_id INT NOT NULL PRIMARY KEY,
    row_value VARCHAR(40) NOT NULL
) ENGINE = InnoDB;
~~~

### 14.2. Roll Back Data While Keeping the Table

~~~sql
START TRANSACTION;

INSERT INTO tmp_rollback_lab (row_id, row_value)
VALUES (1, 'inserted in transaction');

ROLLBACK;

SELECT COUNT(*) AS row_count
FROM tmp_rollback_lab;

SHOW CREATE TABLE tmp_rollback_lab;
~~~

Observations:

- row_count equals 0 because INSERT rolled back.
- SHOW CREATE TABLE still displays the structure because the temporary table still exists.

### 14.3. Commit Part of the Data Then Roll Back the Next Part

~~~sql
START TRANSACTION;
INSERT INTO tmp_rollback_lab VALUES (2, 'committed row');
COMMIT;

START TRANSACTION;
INSERT INTO tmp_rollback_lab VALUES (3, 'rolled back row');
ROLLBACK;

SELECT *
FROM tmp_rollback_lab
ORDER BY row_id;
~~~

The result contains row_id 2 and not row_id 3. Transactions do not drop the temporary table upon completion.

### 14.4. Create a Temporary Table Inside a Transaction Then Roll Back

~~~sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_created_inside_tx (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO tmp_created_inside_tx VALUES (10);

ROLLBACK;

SHOW CREATE TABLE tmp_created_inside_tx;
SELECT COUNT(*) AS row_count
FROM tmp_created_inside_tx;
~~~

Observations:

- The temporary table still exists after ROLLBACK.
- The transactional INSERT row was rolled back, so row_count equals 0.

This is a direct test separating object lifecycle from DML rollback.

### 14.5. DROP a Temporary Table Inside a Transaction Then Roll Back

~~~sql
START TRANSACTION;
DROP TEMPORARY TABLE tmp_created_inside_tx;
ROLLBACK;

SHOW TABLES LIKE 'tmp_created_inside_tx';
~~~

SHOW TABLES is not a reliable check for temporary tables in all contexts. Confirm by attempting to access it:

~~~sql
SELECT *
FROM tmp_created_inside_tx;
~~~

The query reports that the table does not exist because DROP TEMPORARY TABLE cannot be rolled back. Use a new lab table name if you need to re-run this step.

### 14.6. Compare Regular CREATE TABLE

Run only in the lab schema:

~~~sql
CREATE TABLE lab_permanent_ddl_probe (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO lab_permanent_ddl_probe (id)
VALUES (1);

CREATE TABLE lab_ddl_commit_probe (
    id INT NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;

SELECT *
FROM lab_permanent_ddl_probe;

SHOW TABLES LIKE 'lab_ddl_commit_probe';
~~~

Observe that row id 1 remains because regular CREATE TABLE triggers an implicit commit before the DDL. The lab_ddl_commit_probe table also remains after ROLLBACK.

### 14.7. Clean Up Lab Data

~~~sql
DROP TEMPORARY TABLE IF EXISTS tmp_rollback_lab;
DROP TEMPORARY TABLE IF EXISTS tmp_created_inside_tx;
DROP TABLE IF EXISTS lab_ddl_commit_probe;
DROP TABLE IF EXISTS lab_permanent_ddl_probe;
~~~

Only run the permanent table DROP statements if you created those two lab tables yourself in the lab schema.

### 14.8. Self-Check Questions

1. Why does ROLLBACK undo an INSERT into an InnoDB temporary table without dropping the temporary table?
2. Does CREATE TEMPORARY TABLE cause an implicit commit?
3. Can DROP TEMPORARY TABLE be undone with ROLLBACK?
4. What changes if the temporary table uses MEMORY?
5. Why can a regular CREATE TABLE mid-transaction commit prior DML?
6. Why must a connection pool clean up temporary tables before returning connections?
7. Can SAVEPOINT restore a dropped temporary table?
8. When a connection drops immediately after COMMIT, how should an application verify the business outcome before retrying?

## 15. Quick Comparison Table

| Concept | Scope | When Does It End? | Effect of ROLLBACK |
|---|---|---|---|
| Session | One physical connection | Connection closes | Does not remove objects outside session semantics |
| Transaction | One unit of data changes | COMMIT, ROLLBACK, or implicit commit | Undoes uncommitted transactional DML |
| Temporary table | Creating session | DROP TEMPORARY TABLE or session closes | Does not undo CREATE/DROP object |
| InnoDB temporary table | Session-scoped temporary data | Object dropped / session closes | Transactional DML can be rolled back |
| MEMORY temporary table | Session and RAM temporary data | Dropped / session closes or server restarts | DML has no transactional rollback |
| Permanent table | Database schema | DDL or schema administration | DDL is not rolled back by user transactions |

## 16. Principles to Remember

- Transactions and sessions are two different scopes. Ending a transaction does not make a temporary table disappear.
- Temporary tables are visible only in the session that created them and drop automatically when the session ends.
- Temporary tables can shadow permanent tables of the same name in a session; use a distinct prefix like tmp_ to avoid confusion.
- CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not trigger an implicit commit, yet creation/dropping itself cannot be rolled back.
- DML on InnoDB temporary tables can roll back; DML on MEMORY lacks InnoDB-style transaction rollback.
- Specify ENGINE = InnoDB if a workflow depends on rolling back temporary data.
- Regular CREATE TABLE and DROP TABLE cause implicit commits; avoid permanent DDL inside business transactions when full rollback is required.
- ALTER TABLE, CREATE/DROP INDEX, and TRUNCATE TABLE must be evaluated under their own implicit commit rules.
- SAVEPOINT controls only transactional changes; it does not restore dropped temporary tables or remove objects created after the savepoint.
- CREATE TEMPORARY TABLE IF NOT EXISTS does not automatically clear stale data in a session.
- Connection pools reuse physical sessions; clean up temporary tables in finally and never assume returning a connection to the pool closes the session.
- Check row counts, current status, and business conditions before updating permanent tables.
- Handle deadlocks, lock timeouts, and dropped connections with idempotent retries; verify COMMIT outcome before re-running business logic.
- Atomic DDL protects DDL integrity across crashes; it does not make DDL rollbackable by user transactions.

When designing workflows with temporary tables, clearly decide which data needs rollback, which objects must survive across multiple transactions, and which session owns the table. Use InnoDB for DML needing rollback, keep permanent DDL outside business transactions, understand the implicit commit exception of CREATE/DROP TEMPORARY TABLE, and always clean up on the exact same connection. This allows temporary tables to support multi-step batch processing without introducing false assumptions about data atomicity and table structure.
