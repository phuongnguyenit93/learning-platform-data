# DDL Implicit Commit and Exceptions to Verify

InnoDB transactions allow grouping multiple data operations into a single unit: either `COMMIT` all of them, or `ROLLBACK` uncommitted changes. However, not every SQL statement stays within a transaction that way. In MySQL, many DDL statements such as ALTER TABLE, CREATE TABLE, DROP TABLE, TRUNCATE TABLE, and CREATE INDEX cause an **implicit commit**. When running such a statement while a transaction is open, MySQL automatically ends the current transaction according to the statement's rules.

This has a direct impact on migrations and production operations. If a transaction updates data and then runs ALTER TABLE, the DML part before the DDL may already have been committed before ALTER TABLE executes. A subsequent ROLLBACK command cannot undo the committed data and also does not turn DDL into an operation that can be rolled back like regular DML.

Several exceptions must be clearly understood: CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not cause an implicit commit under standard rules, yet creating or dropping a temporary table itself cannot be rolled back either. CREATE TABLE ... SELECT has its own rules and still causes an implicit commit. Additionally, MySQL 8.0 has Atomic DDL for supported operations and storage engines; Atomic DDL protects the integrity of a single statement if the server crashes, but does not make DDL rollbackable within a user's transaction.

## Learning Objectives

After this lesson, you will be able to:

- Explain implicit commit and identify transaction boundaries created by DDL.
- Distinguish DDL, DML, and administrative statements that can cause an implicit commit.
- Recognize common DDL statements such as ALTER, CREATE, DROP, RENAME, TRUNCATE, and CREATE/DROP INDEX.
- Understand the exception for CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE.
- Explain why temporary tables cannot be rolled back even though creating/dropping them does not commit the transaction.
- Distinguish CREATE TABLE ... SELECT from a plain CREATE TEMPORARY TABLE.
- Understand the differences between implicit commit, Atomic DDL, and InnoDB's rollback capability.
- Predict the impact of DDL on pending DML, SAVEPOINT, and ROLLBACK.
- Plan migrations with checks, backups, metadata locks, and recovery capabilities.
- Know which operations to verify by MySQL version and storage engine type.

## 1. Transactions and DDL Solve Two Different Problems

Transactions manage the integrity of data changes. With InnoDB, INSERT, UPDATE, and DELETE statements can usually be committed with COMMIT or rolled back with ROLLBACK inside a transaction.

Example:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 100.00
    WHERE account_id = 1;

    UPDATE bank_account_demo
    SET balance = balance + 100.00
    WHERE account_id = 2;

    COMMIT;

Both balance changes are committed together. If an error occurs before COMMIT, the application can ROLLBACK to undo both changes, provided the tables use a transaction-capable storage engine such as InnoDB.

DDL changes database structure or objects, for example:

    ALTER TABLE bank_account_demo
        ADD COLUMN account_label VARCHAR(80) NULL;

    CREATE INDEX idx_bank_account_label
        ON bank_account_demo (account_label);

These statements have their own transaction rules. For many DDL statements in MySQL, the server automatically commits any open transaction before execution. Some DDL statements also end a transaction after completion. Therefore, you cannot treat DDL like another UPDATE statement and expect a final ROLLBACK to undo everything.

### 1.1. DDL, DML, and Administrative Statements

| Category | Purpose | Examples | Transaction behavior |
|---|---|---|---|
| DML | Read or modify data rows | SELECT, INSERT, UPDATE, DELETE | DML on InnoDB can participate in a transaction |
| DDL | Create or alter structure/objects | CREATE TABLE, ALTER TABLE, DROP TABLE, TRUNCATE | Many statements cause an implicit commit |
| DCL/account management | Manage privileges and accounts | GRANT, REVOKE, CREATE USER, ALTER USER | Certain statements cause an implicit commit |
| Administrative | Maintain or manage server/tables | ANALYZE TABLE, OPTIMIZE TABLE, FLUSH | Certain statements cause an implicit commit |
| Transaction control | Control transactions and locks | START TRANSACTION, COMMIT, ROLLBACK, LOCK TABLES | Have their own rules for ending or opening transactions |

Do not categorize statements solely by name. When executing inside a transaction, check the implicit commit list for your exact MySQL version and operation type.

## 2. How Does Implicit Commit Work?

An implicit commit occurs when MySQL automatically ends an active transaction without requiring the application to send an explicit COMMIT command. For regular DDL, the current transaction is committed before the DDL statement executes. Many DDL statements also create a commit boundary after completion; the exact details depend on the statement type.

Example:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 100.00
    WHERE account_id = 1;

    ALTER TABLE bank_account_demo
        ADD COLUMN note VARCHAR(100) NULL;

    ROLLBACK;

An application might think the final ROLLBACK will undo both the UPDATE and the ALTER TABLE. In reality, ALTER TABLE triggers an implicit commit for the open transaction before executing. Consequently, the UPDATE before ALTER TABLE has already been committed. Nor is the DDL undone by the final ROLLBACK. ROLLBACK only affects a new transaction if transactional changes were performed after the DDL boundary and that transaction is still open.

Diagram:

    START TRANSACTION
           |
           v
    UPDATE account
           |
           v
    ALTER TABLE
           |
           +---- implicit commit of the transaction before DDL
           |
           +---- DDL executes under its own mechanism
           |
           v
    ROLLBACK
           |
           +---- does not undo the committed UPDATE
           +---- does not undo ALTER TABLE

### 2.1. Does Implicit Commit Happen Even If DDL Fails?

This is a very important point when planning. Committing the transaction prior to DDL occurs as part of the statement's execution rules. If the DDL subsequently fails due to a schema error, privilege error, metadata lock timeout, or another condition, the previously committed DML still does not revert automatically.

Illustrative example in a sandbox:

    START TRANSACTION;

    UPDATE bank_account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    -- Suppose column account_id already exists; this ALTER will fail.
    ALTER TABLE bank_account_demo
        ADD COLUMN account_id BIGINT NULL;

    ROLLBACK;

Even though ALTER TABLE fails due to a duplicate column name, the earlier UPDATE has already crossed the implicit commit boundary. You cannot rely on a DDL failure to expect the preceding transaction to be restored.

### 2.2. ROLLBACK After DDL Is Not a Migration Undo

DDL such as ALTER TABLE, CREATE TABLE, or DROP TABLE is not placed into a user's transaction undo log in a way that allows ROLLBACK to restore the old schema. You need a reverse migration plan, backup, snapshot, or dedicated recovery procedure if a structural change causes an error.

Do not run a sequence of DDL and DML inside one transaction and treat a final ROLLBACK as a general recovery plan. Treat each DDL statement as an independently planned boundary.

## 3. DDL Statements That Commonly Cause Implicit Commit

The following groups commonly cause an implicit commit in MySQL:

### 3.1. CREATE

Common object creation commands:

- CREATE DATABASE
- CREATE TABLE
- CREATE INDEX
- CREATE VIEW
- CREATE TRIGGER
- CREATE PROCEDURE and CREATE FUNCTION
- CREATE EVENT
- CREATE USER and CREATE ROLE

Example:

    START TRANSACTION;
    INSERT INTO migration_audit_demo (message)
    VALUES ('before create table');

    CREATE TABLE migration_created_demo (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        description VARCHAR(100) NOT NULL
    ) ENGINE = InnoDB;

The open transaction is ended before CREATE TABLE executes. Do not place CREATE TABLE in the middle of a DML sequence that the application needs to roll back as a single unit.

### 3.2. ALTER

ALTER commands that modify structure or object attributes:

- ALTER TABLE
- ALTER DATABASE
- ALTER VIEW
- ALTER EVENT
- ALTER USER
- ALTER PROCEDURE or ALTER FUNCTION
- ALTER INSTANCE and certain other administrative operations

Example:

    ALTER TABLE migration_created_demo
        ADD COLUMN created_at DATETIME(6) NULL;

ALTER TABLE may use the INSTANT, INPLACE, or COPY algorithm depending on the change and version. Even when DDL runs online or with reduced locking, that does not make it a rollbackable transactional operation.

### 3.3. DROP

DROP commands that remove objects:

- DROP TABLE
- DROP DATABASE
- DROP INDEX
- DROP VIEW
- DROP TRIGGER
- DROP PROCEDURE and DROP FUNCTION
- DROP EVENT
- DROP USER or DROP ROLE

Example:

    DROP TABLE migration_created_demo;

DROP TABLE is DDL and cannot be recovered by a user transaction's ROLLBACK. Verify the exact schema, exact table, backups, and dependencies before executing.

### 3.4. RENAME and TRUNCATE

RENAME TABLE renames an object:

    RENAME TABLE old_customer TO customer_archive;

TRUNCATE TABLE deletes all rows using a DDL operation:

    TRUNCATE TABLE staging_import_demo;

TRUNCATE is usually faster than a DELETE without WHERE on large tables, but has different semantics:

- TRUNCATE is DDL and causes an implicit commit.
- TRUNCATE cannot be undone by a user transaction's ROLLBACK.
- TRUNCATE usually resets the table's AUTO_INCREMENT counter.
- DELETE is DML; with InnoDB, DELETE can be rolled back if the transaction has not committed.
- DELETE can use WHERE to delete a subset of data; TRUNCATE deletes all rows of the table.

Comparison:

    START TRANSACTION;
    DELETE FROM staging_import_demo;
    ROLLBACK;

With an InnoDB table, rows removed by DELETE can be restored by ROLLBACK.

    START TRANSACTION;
    TRUNCATE TABLE staging_import_demo;
    ROLLBACK;

TRUNCATE created an implicit commit boundary; ROLLBACK does not restore the truncated rows.

### 3.5. CREATE INDEX and DROP INDEX

Creating or dropping an index is also DDL:

    CREATE INDEX idx_order_created_at
    ON sales_order (created_at);

    DROP INDEX idx_order_created_at
    ON sales_order;

Online indexing or adding an index with LOCK=NONE if supported still follows implicit commit rules. Online DDL describes the level of concurrent reads/writes allowed during the change; it does not mean the DDL resides inside a rollbackable transaction.

## 4. Non-Pure-DDL Statements That Can Commit

Not only DDL causes an implicit commit. Certain transaction control, account management, and server administration statements can also end an open transaction.

### 4.1. START TRANSACTION and BEGIN

START TRANSACTION or BEGIN starts a new transaction. If the session already has an active transaction, the command starting the new transaction ends the current transaction first.

    START TRANSACTION;
    UPDATE account_demo SET balance = balance - 5 WHERE account_id = 1;

    START TRANSACTION;

The second START TRANSACTION command does not create a nested transaction. The first transaction is ended before the new transaction begins.

MySQL does not support nested transactions of the form START TRANSACTION inside START TRANSACTION. If you need a rollback point within a transaction, use SAVEPOINT.

### 4.2. SET autocommit

Check the mode:

    SELECT @@SESSION.autocommit;

If the session has autocommit = 0 and switches to 1:

    SET autocommit = 1;

switching from 0 to 1 commits any open transaction. Setting autocommit = 0 does not have this same commit effect.

Do not change autocommit mid-flow without understanding the current transaction state. In applications using a connection pool, ensure sessions are returned to the pool in a standardized state.

### 4.3. LOCK TABLES and UNLOCK TABLES

LOCK TABLES triggers an implicit commit before locking the tables. UNLOCK TABLES can commit if the session currently holds table locks created by LOCK TABLES. Exact behavior depends on lock type and the locking mechanism used.

Example:

    LOCK TABLES sales_order WRITE;
    -- operations while holding lock
    UNLOCK TABLES;

This is a table-locking mechanism and does not replace InnoDB's transactional row-level locking. Do not use LOCK TABLES as a way to create nested transactions or group DDL/DML into a single rollback unit.

### 4.4. Account Management and Privileges

Account/privilege management statements can cause an implicit commit:

- CREATE USER
- ALTER USER
- DROP USER
- RENAME USER
- GRANT
- REVOKE
- SET PASSWORD

Example:

    GRANT SELECT ON reporting_db.* TO 'report_reader'@'%';

Do not run GRANT or ALTER USER in the middle of a data transaction expecting ROLLBACK to undo the privilege change or revert earlier DML.

### 4.5. Certain Administrative Commands

Commands such as ANALYZE TABLE, OPTIMIZE TABLE, REPAIR TABLE, FLUSH, CACHE INDEX, LOAD INDEX INTO CACHE, and RESET may have implicit commit rules. The exact list and details can change by version and operation type.

When writing migrations or operational scripts, check the list of statements causing an implicit commit in the documentation for your exact MySQL version. Never assume a command is "read-only" or "maintenance-only" and therefore will not affect a transaction.

## 5. Exception: CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE

MySQL has an important exception: CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not trigger an implicit commit under standard rules.

Example:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    CREATE TEMPORARY TABLE tmp_account_check (
        account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        observed_balance DECIMAL(14,2) NOT NULL
    ) ENGINE = InnoDB;

    ROLLBACK;

The transaction can still roll back the UPDATE because CREATE TEMPORARY TABLE did not commit the active transaction. However, the newly created temporary table still exists in the session after ROLLBACK.

This is a common point of confusion:

- CREATE TEMPORARY TABLE does not implicitly commit.
- However, creating the temporary table itself is not rolled back.
- ROLLBACK undoes uncommitted transactional DML, not the newly created temporary table.
- A temporary table automatically disappears when the session ends or when dropped with DROP.

Similarly, DROP TEMPORARY TABLE does not cause an implicit commit, yet dropping the temporary table cannot be undone with ROLLBACK.

### 5.1. Temporary Tables Are Not Tables With Rollbackable DDL

Creating a temporary table and inserting data into it are two separate operations:

    START TRANSACTION;

    CREATE TEMPORARY TABLE tmp_work (
        id INT NOT NULL PRIMARY KEY,
        note VARCHAR(100) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tmp_work (id, note)
    VALUES (1, 'temporary row');

    ROLLBACK;

After ROLLBACK:

- The tmp_work table still exists in the session because CREATE TEMPORARY TABLE is not rolled back.
- The row INSERTed into tmp_work can be rolled back because the temporary table uses InnoDB and DML participates in the transaction.

This illustrates that the lifecycle of the temporary table object and transactional data inside the table are two separate layers.

### 5.2. Temporary Tables Have Session Scope

A temporary table is visible only within the connection that created it. Other connections cannot access a temporary table of the same name in the current session. When the connection closes, MySQL automatically drops that session's temporary tables.

With a connection pool, a connection may be reused. If an application creates a temporary table and fails to DROP it, the next checkout of that connection may encounter a table-already-exists error or accidentally use leftover temporary data in the same session. Always DROP TEMPORARY TABLE when finished or use controlled naming and management procedures.

### 5.3. The Exception Does Not Apply to All DDL on Temporary Tables

Do not generalize that every operation on a temporary table avoids committing. The exception is stated for CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE. Other DDL commands such as ALTER TABLE still have implicit commit rules to check, even when the modified object is a temporary table.

For example, do not assume ALTER TABLE tmp_work can run mid-transaction while preserving transaction boundaries. Check the exact statement in the MySQL documentation and test in a sandbox.

### 5.4. CREATE TEMPORARY TABLE ... SELECT Is a Special Case

CREATE TABLE ... SELECT has its own implicit commit rules. Do not infer from the plain CREATE TEMPORARY TABLE exception that every variant with SELECT avoids committing. CREATE TABLE ... SELECT causes an implicit commit per that statement's rules; check version documentation and use an explicit step-separated approach if transaction boundaries matter.

Example creating a temporary table from a query:

    CREATE TEMPORARY TABLE tmp_paid_orders AS
    SELECT order_id, customer_id, amount
    FROM sales_order
    WHERE order_status = 'PAID';

When using this form, do not rely on the assumption that a prior transaction remains intact. If preserving the transaction boundary is necessary, test on your exact version and separate creating the structure from INSERT ... SELECT according to verified rules.

## 6. Atomic DDL in MySQL 8.0 Does Not Mean Transactional DDL

MySQL 8.0 introduced Atomic DDL for supported operations and storage engines. Atomic DDL coordinates data dictionary changes, storage engine operations, and related binary log writes so that a single DDL statement is atomic if the server crashes.

Operationally, this means if the server crashes mid-way through a supported DDL statement, recovery brings the operation to either the completed state or the unapplied state under the Atomic DDL mechanism. It prevents certain half-finished metadata and storage engine states.

However, Atomic DDL **does not** mean:

- You can put ALTER TABLE in a transaction and ROLLBACK to revert to the old schema.
- You can group multiple DDLs and DMLs into a single transaction.
- A failing DDL will automatically undo DML that was implicitly committed earlier.
- Every statement, every storage engine, and every administrative operation has Atomic DDL.

Distinguish:

| Concept | What Does It Protect? | Can User ROLLBACK Undo It? |
|---|---|---|
| InnoDB Transactional DML | Groups of data row changes | Yes, before COMMIT |
| Implicit commit | Ends open transaction per statement rules | Cannot revert the committed part |
| Atomic DDL | Integrity of a supported DDL during execution/recovery | No; it is not transactional DDL |
| Backup/restore or reverse migration | Recovery capability after schema/data changes | Depends on the recovery process |

Thus, Atomic DDL makes DDL safer against crashes but does not alter the transaction rules that applications must follow.

## 7. SAVEPOINT Does Not Protect DDL

SAVEPOINT creates a rollback point inside a transaction. It is useful for DML:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SAVEPOINT after_debit;

    UPDATE account_demo
    SET balance = balance + 10.00
    WHERE account_id = 2;

    ROLLBACK TO SAVEPOINT after_debit;
    COMMIT;

ROLLBACK TO SAVEPOINT undoes changes after the savepoint while keeping earlier changes in the transaction.

If DDL is executed after SAVEPOINT:

    START TRANSACTION;
    UPDATE account_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SAVEPOINT before_ddl;

    ALTER TABLE account_demo
        ADD COLUMN audit_note VARCHAR(100) NULL;

The implicit commit ends the transaction and removes that transaction's savepoints. After the DDL, SAVEPOINT before_ddl no longer exists; ROLLBACK TO SAVEPOINT will fail reporting that the savepoint does not exist.

Do not place DDL in the middle of a sequence of operations relying on SAVEPOINT. Split the workflow into phases with clear boundaries.

## 8. DDL and Storage Engines

DML rollback capability depends on the storage engine. InnoDB supports transactions; MyISAM does not support transactions the way InnoDB does.

Check a table's engine:

    SHOW TABLE STATUS LIKE 'account_demo';

Or:

    SELECT
        TABLE_NAME,
        ENGINE
    FROM information_schema.tables
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'account_demo';

If a transaction updates an InnoDB table and a MyISAM table, ROLLBACK cannot undo changes already written to MyISAM. Do not assume that merely running START TRANSACTION makes every table transactional.

For production tables, check the engine before designing rollbacks, backups, migrations, and recovery workflows.

## 9. TRUNCATE TABLE vs. DELETE: Differences at Transaction Boundaries

DELETE removes rows by condition and is DML:

    START TRANSACTION;

    DELETE FROM session_event
    WHERE created_at < '2025-01-01';

    -- Inspect remaining row counts and data
    ROLLBACK;

If session_event uses InnoDB, the DELETE operation can be undone before COMMIT.

TRUNCATE removes all rows and is DDL:

    TRUNCATE TABLE session_event;

It triggers an implicit commit and cannot be undone with ROLLBACK. Additionally, TRUNCATE usually resets AUTO_INCREMENT. Before using it, verify the exact table, schema, foreign key dependencies, privileges, and backups.

| Criterion | DELETE | TRUNCATE |
|---|---|---|
| Statement group | DML | DDL |
| WHERE | Yes | No |
| Can delete a subset of rows | Yes | No |
| InnoDB rollback inside transaction | Yes, before COMMIT | No |
| Implicit commit | Not per DDL rules | Yes |
| AUTO_INCREMENT | Does not auto-reset to start like truncate | Usually reset |
| DELETE triggers | Fires DELETE triggers for deleted rows | Does not fire per-row DELETE triggers |

Choose DELETE when you need transactions, filter conditions, or per-row triggers. Choose TRUNCATE when you want to empty the entire table and have accepted DDL semantics.

## 10. DDL, Metadata Locks, and Deployment Timing

DDL may require a metadata lock (MDL) to ensure the schema does not change while the statement is running. A long query or open transaction holding a metadata lock can force ALTER TABLE to wait. Conversely, a waiting DDL can cause other queries to queue behind it depending on the situation.

Before migrating, check:

- Long open transactions on the target table.
- Running queries or sessions holding metadata locks.
- Table and index sizes.
- Available ALTER algorithms: INSTANT, INPLACE, or COPY.
- Read/write availability while DDL runs.
- Execution duration and impact on replication.
- Temporary space and I/O needed if the table must be rebuilt.

Example requesting an algorithm/lock if supported by the version and operation:

    ALTER TABLE sales_order
        ADD COLUMN source_code VARCHAR(30) NULL,
        ALGORITHM = INSTANT;

Not every change supports INSTANT. If the server rejects it, inspect the error message and version documentation; do not automatically fall back to COPY in production without evaluating lock duration and capacity.

Online DDL does not eliminate implicit commit. It only changes how MySQL performs the schema operation and the level of concurrency that can be maintained.

## 11. Designing Safe Migrations

A production migration should be designed as a multi-step process rather than a single transaction assumed to cover both DDL and DML.

### 11.1. Before Running DDL

1. Identify the exact database, table, columns, and indexes to change.
2. Read SHOW CREATE TABLE and check the MySQL version.
3. Determine whether the statement triggers an implicit commit or whether any exceptions apply.
4. Check engines and active transactions.
5. Check for long transactions, metadata locks, and system load.
6. Verify backup/restore and reverse migration capability.
7. Test on staging with data sizes close to production.
8. Estimate execution time, storage capacity, and replication impact.
9. Determine how the application stays compatible with the schema before, during, and after the migration.

### 11.2. Splitting Migrations into Phases

A common strategy when adding a new column:

1. Add a nullable column or one with an appropriate default via DDL.
2. Deploy an application version that can read/write the new schema while staying compatible during the transition phase.
3. Backfill data in batches using monitorable and controllable DML.
4. Verify backfilled row counts, remaining NULL values, and consistency.
5. Add constraints or indexes in a separate DDL step once data meets requirements.
6. Deploy the application removing legacy compatibility paths once all nodes are updated.

Each DDL step is its own boundary. DML backfills can be split into batched transactions to limit undo log growth, lock duration, and rollback time.

### 11.3. Reverse Migration Is Not SQL ROLLBACK

If a migration adds a column and the application fails, a reverse migration might be ALTER TABLE DROP COLUMN. However, that operation is a new DDL statement, which also triggers an implicit commit and carries its own risks.

If the migration already wrote data into the new column, DROP COLUMN can cause data loss. Therefore, application rollback and schema rollback must be designed separately. In some cases it is safer to keep the new column, restore a compatible application version, and handle the data afterward.

## 12. Hands-On Practice Observing Transaction Boundaries

The examples below should be run on a sandbox database, not on production.

### 12.1. Create a Test Table

    CREATE TABLE tx_ddl_demo (
        account_id INT NOT NULL PRIMARY KEY,
        balance DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tx_ddl_demo (account_id, balance)
    VALUES (1, 100.00), (2, 200.00);

### 12.2. Rollbackable DML

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

    ROLLBACK;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

After ROLLBACK, account 1's balance returns to 100.00.

### 12.3. DDL Commits Prior DML

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 10.00
    WHERE account_id = 1;

    ALTER TABLE tx_ddl_demo
        ADD COLUMN note VARCHAR(100) NULL;

    ROLLBACK;

    SELECT * FROM tx_ddl_demo ORDER BY account_id;

After ALTER TABLE, the earlier UPDATE was committed. The final ROLLBACK neither restores balance to its old value nor removes the note column.

### 12.4. Temporary Tables Do Not Commit, Yet Creation Is Not Rolled Back

    START TRANSACTION;

    UPDATE tx_ddl_demo
    SET balance = balance - 5.00
    WHERE account_id = 1;

    CREATE TEMPORARY TABLE tmp_tx_check (
        account_id INT NOT NULL PRIMARY KEY,
        observed_balance DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO tmp_tx_check (account_id, observed_balance)
    SELECT account_id, balance
    FROM tx_ddl_demo;

    ROLLBACK;

    SHOW TABLES LIKE 'tmp_tx_check';
    SELECT * FROM tmp_tx_check;
    SELECT * FROM tx_ddl_demo ORDER BY account_id;

After ROLLBACK, tmp_tx_check still exists, but the INSERT into the temporary table belonged to the rolled-back transaction so the inserted rows are gone. The UPDATE on tx_ddl_demo is also rolled back because CREATE TEMPORARY TABLE did not commit the transaction.

Cleanup:

    DROP TEMPORARY TABLE IF EXISTS tmp_tx_check;

### 12.5. Temporary Tables and CREATE TABLE ... SELECT

Test CREATE TEMPORARY TABLE ... SELECT separately in a sandbox if you need to confirm behavior on your deployment version. Do not mix this test into a transaction holding important data; the ... SELECT form has its own implicit commit rules compared to an empty CREATE TEMPORARY TABLE.

## 13. Inspecting Sessions and Transaction State

Some useful information:

    SELECT
        VERSION() AS mysql_version,
        @@SESSION.autocommit AS autocommit_mode,
        @@SESSION.sql_mode AS session_sql_mode;

You can view active InnoDB transactions:

    SELECT *
    FROM information_schema.innodb_trx;

This metadata table is helpful for detecting long-running transactions, though viewing permissions and details may depend on version. In MySQL 8.0, Performance Schema also provides information on threads, statements, and locks; monitoring tools should use sources matching available privileges.

Before running DDL, check:

- Does the current session have an open transaction?
- Is there uncommitted DML that needs to stay inside the transaction?
- Does the DDL cause an implicit commit?
- Is another session holding a metadata lock on the object?
- After the DDL, is the application assuming the old transaction is still active?

Do not inspect only the migration session's transactions. Long transactions from other sessions can also affect metadata locks and DDL completion time.

## 14. Cases to Verify by Version

The list of statements causing implicit commit and their exceptions is documented by MySQL per version. Before putting a command into an automated migration, verify:

- The actual MySQL server version, not just the client version.
- The table's storage engine.
- The exact statement, including TEMPORARY or SELECT if present.
- Whether the DDL is within the supported Atomic DDL group.
- Whether the DDL algorithm and lock level are supported for the specific structure.
- Whether the statement is prohibited inside an XA transaction or current stored program.
- Whether behavior differs across MySQL Community, older versions, and MySQL-compatible services.

Rules to specifically verify:

| Statement/Scenario | Point to Verify |
|---|---|
| CREATE TABLE / DROP TABLE | DDL usually causes implicit commit |
| CREATE TEMPORARY TABLE / DROP TEMPORARY TABLE | Exception with no implicit commit; creation/deletion itself cannot be rolled back |
| CREATE TABLE ... SELECT | Has its own implicit commit rules; do not generalize the temporary table exception |
| ALTER TABLE on regular table | DDL causes implicit commit |
| ALTER TABLE on temporary table | Do not generalize CREATE/DROP TEMPORARY exception; check ALTER rules |
| CREATE INDEX / DROP INDEX | DDL, causes implicit commit |
| TRUNCATE TABLE | DDL, does not roll back like DELETE |
| START TRANSACTION while transaction is open | Ends prior transaction before starting new transaction |
| SET autocommit = 1 when changing from 0 | Commits open transaction |
| LOCK TABLES / UNLOCK TABLES | Has commit rules before/until unlock depending on lock |
| GRANT / REVOKE / account management | Can cause implicit commit |
| ANALYZE / OPTIMIZE / FLUSH | Verify by statement and version |

This is a checklist for common cases, not an exhaustive copy of the reference documentation. For uncommon commands or version-specific changes, consult the official list before deploying.

## 15. DDL in XA Transactions

XA transactions coordinate distributed transactions across multiple resource managers. Statements causing an implicit commit are disallowed in the XA ACTIVE state under MySQL's XA rules; the server may reject the statement rather than silently allowing the transaction to continue.

If an application uses XA, do not place DDL or account-management statements with implicit commit inside an XA processing branch. Perform migrations outside the XA lifecycle and coordinate with the transaction coordinator.

Do not confuse XA with regular InnoDB transactions. XA has its own states and prepare/commit protocol; statement errors inside XA must be handled according to XA state and coordinator recovery mechanisms.

## 16. Common Mistakes

- Putting ALTER TABLE between START TRANSACTION and ROLLBACK and assuming all changes will be undone.
- Thinking that if DDL fails, DML committed earlier will automatically roll back.
- Confusing Atomic DDL with transactional DDL.
- Thinking online DDL or ALGORITHM=INPLACE/INSTANT does not trigger an implicit commit.
- Thinking CREATE TEMPORARY TABLE not committing means temporary table creation can be rolled back.
- Thinking DROP TEMPORARY TABLE can be rolled back with ROLLBACK to restore the table.
- Generalizing the temporary table exception to all ALTER or CREATE ... SELECT statements.
- Using TRUNCATE when rollback capability like DELETE is needed.
- Using SAVEPOINT to protect changes prior to DDL.
- Assuming START TRANSACTION creates nested transactions.
- Switching autocommit from 0 to 1 without realizing an open transaction will be committed.
- Running GRANT, REVOKE, or ALTER USER in the middle of a data transaction.
- Checking only the migration session while ignoring long transactions and metadata locks from other sessions.
- Assuming all tables are transactional even though some may use MyISAM or another engine.
- Deploying production DDL without backups, a reverse migration plan, and compatibility testing.

## 17. Checklist Before Running DDL in a Transactional System

- Verified whether the statement is DDL, DML, account management, administrative, or transaction control.
- Checked whether the statement causes an implicit commit before or after execution.
- Determined whether any exceptions apply precisely to the syntax being used.
- Verified MySQL version and storage engine.
- Confirmed there is no uncommitted DML that the application expects to roll back after DDL.
- Understood that SAVEPOINTs will be lost when a transaction undergoes an implicit commit.
- Distinguished Atomic DDL from user transaction rollback.
- Checked metadata locks, long transactions, and system load.
- Evaluated DDL algorithm, locking, storage capacity, and replication.
- Prepared appropriate backup/restore or reverse migration plans.
- Tested on staging with schema and data close to production.
- Split DDL and DML backfills into phases with clear boundaries.
- Determined how the application maintains compatibility throughout the migration.
- Verified CREATE/DROP TEMPORARY and CREATE TABLE ... SELECT exceptions if applicable.
- Tested results and verified schema after migration.

Implicit commit is an important boundary between data transactions and structural changes in MySQL. Many DDL commands such as ALTER, CREATE, DROP, RENAME, TRUNCATE, and CREATE/DROP INDEX will terminate an open transaction; several administrative, privilege management, and transaction control commands can do the same. CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE are exceptions regarding implicit commit, yet creating/dropping a temporary table cannot be rolled back; CREATE TABLE ... SELECT must be evaluated separately. Atomic DDL in MySQL 8.0 increases single-statement crash safety but does not turn DDL into transactional DDL. Treat every DDL as an independent migration boundary, verify the exact version and engine, protect uncommitted DML, control metadata locks, and prepare recovery plans before deploying.
