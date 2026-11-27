# Implicit Commit of DDL and Its Impact on Deployment Scripts in Oracle Database

In Oracle Database, structural commands such as CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP, and TRUNCATE have an important characteristic: they trigger an **implicit commit**. This behavior directly affects how you design transactions, write deployment scripts, execute migrations, and handle errors.

A common misconception is putting multiple DML and DDL statements in the same script and assuming a ROLLBACK at the end can undo everything if an error occurs. In Oracle, that is false. Before executing DDL, Oracle commits the current transaction. When DDL succeeds, the structural change is also committed. Therefore, DDL can create transaction boundaries between DML statements within the same script.

This lesson explains the implicit commit rule, distinguishes DDL from DML, illustrates the impact on SAVEPOINT and ROLLBACK, compares DELETE with TRUNCATE, covers DDL handling in PL/SQL/JDBC, and establishes a safe schema deployment strategy when migrations involve both structural and data changes.

## 1. Transactions in Oracle and Two Common Statement Categories

A transaction is a unit of data work. With standard DML, an application can perform multiple operations and then decide:

- COMMIT: confirm the changes.
- ROLLBACK: discard uncommitted changes.
- ROLLBACK TO SAVEPOINT: return to a savepoint inside the current transaction.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

-- Only when all operations are valid:
COMMIT;
~~~

If validation detects an error before COMMIT, ROLLBACK can undo both UPDATEs.

However, Oracle clearly distinguishes two command categories:

| Category | Examples | Typical Transaction Behavior |
|---|---|---|
| DML (Data Manipulation Language) | INSERT, UPDATE, DELETE, MERGE | Modifies data within a transaction; can be COMMITted or ROLLBACKed |
| DDL (Data Definition Language) | CREATE, ALTER, DROP, TRUNCATE, RENAME, COMMENT | Oracle performs an implicit commit before running DDL and commits the DDL change when the command succeeds |

SELECT only reads data and does not automatically commit pending DML changes in a transaction. Transaction control statements such as COMMIT, ROLLBACK, and SAVEPOINT have their own semantics.

## 2. The Implicit Commit Rule for DDL

### 2.1 Commit Before and After DDL

Oracle performs implicit commits around a DDL statement:

1. **Before executing DDL:** commits the session's current transaction, including uncommitted DML changes.
2. **Executing DDL:** Oracle applies metadata/structural changes per the statement.
3. **After DDL succeeds:** the DDL change is committed.

You can visualize this as:

~~~text
Transaction A
    |
    +-- Uncommitted INSERT / UPDATE / DELETE
    |
    v
Execute a DDL statement
    |
    +-- Oracle COMMITs Transaction A before DDL
    |
    +-- Execute CREATE / ALTER / DROP / TRUNCATE ...
    |
    +-- If DDL succeeds: commit DDL changes
    |
    v
New transaction
    |
    +-- Subsequent DML
    |
    +-- Separate COMMIT or ROLLBACK
~~~

The most important point: the pre-DDL implicit commit can commit **all uncommitted DML of the session**, not merely data belonging to the object the DDL is altering.

### 2.2 Example: DDL Commits Preceding DML

Suppose you have a lab table:

~~~sql
CREATE TABLE ddl_commit_demo (
    id   NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

Then run:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (1, 'DML before DDL');

CREATE TABLE ddl_marker (
    id NUMBER
);

ROLLBACK;
~~~

Result:

~~~sql
SELECT *
FROM ddl_commit_demo
WHERE id = 1;
~~~

The row with ID=1 still exists. Why:

- INSERT created an uncommitted DML change.
- `CREATE TABLE ddl_marker` triggered an implicit commit before execution.
- INSERT was committed at that moment.
- ROLLBACK after `CREATE TABLE` only affects changes still in the current transaction; it cannot undo the already committed INSERT.

This is a classic example showing that a DDL statement unrelated to the DML table can still commit preceding DML data.

### 2.3 What If the DDL Fails?

Suppose:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (2, 'DML before failed DDL');

CREATE TABLE ddl_commit_demo (
    id NUMBER
);
~~~

`CREATE TABLE` fails because the object already exists, yet the preceding DML transaction was already committed before Oracle attempted to execute the DDL. The `CREATE TABLE` error does not revert the INSERT back to an uncommitted state.

You must distinguish two things:

- **DML before DDL:** already committed by the implicit commit step before the DDL ran.
- **Failed DDL:** the structural change of the failing statement is not completed; the DDL error does not restore the prior transaction.

Therefore, never rely on the assumption that "if DDL fails, the whole script rolls back."

### 2.4 DML After DDL Can Still Roll Back

After DDL succeeds, a new transaction can start:

~~~sql
CREATE TABLE ddl_after_demo (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

INSERT INTO ddl_after_demo VALUES (1, 'after DDL');

ROLLBACK;
~~~

The INSERT after `CREATE TABLE` has not been committed by another DDL or explicit COMMIT, so ROLLBACK can discard row ID=1. The table still exists because `CREATE TABLE` was committed.

A single script can thus contain both changes that cannot be rolled back via normal transactions and DML changes that are still rollbackable. You must know precisely where transaction boundaries fall.

## 3. Common DDL Commands That Trigger Implicit Commit

Common DDL commands used in schema development and deployment include:

| Command | Example | Effect |
|---|---|---|
| CREATE TABLE | Create a new table | Creates table metadata and structure |
| ALTER TABLE | Add columns, modify constraints | Alters table definition |
| DROP TABLE | Drop a table | Removes table object from schema |
| TRUNCATE TABLE | Remove all rows via truncate mechanism | DDL; does not roll back like DELETE |
| CREATE INDEX | Create an index | Modifies access structures |
| DROP INDEX | Drop an index | Removes an index |
| CREATE SEQUENCE | Create a sequence | Creates a sequence generator object |
| ALTER SEQUENCE | Modify sequence settings | Alters sequence metadata |
| RENAME | Rename an object | Alters metadata |
| COMMENT ON | Annotate an object/column | Alters metadata |
| CREATE VIEW | Create a view | Creates view metadata |
| CREATE OR REPLACE PROCEDURE | Create/replace a procedure | Alters PL/SQL object |

Do not merely memorize a list of command names. Whenever putting a schema administration command into a script, identify whether it is DDL or DML and check the SQL Language Reference for your Oracle version if unsure.

### 3.1 CREATE TABLE AS SELECT (CTAS)

CTAS is DDL:

~~~sql
CREATE TABLE sales_snapshot AS
SELECT *
FROM sales
WHERE sale_date >= DATE '2026-01-01';
~~~

Even though the statement contains SELECT, `CREATE TABLE AS SELECT` is still DDL and triggers an implicit commit. Never treat CTAS as a pure SELECT that can roll back alongside prior DML.

### 3.2 CREATE INDEX Is Also DDL

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Creating an index can commit an open transaction before the command executes. If a script already ran an UPDATE without COMMITting, the following `CREATE INDEX` can commit that UPDATE as well.

### 3.3 TRUNCATE Is DDL, Not DELETE

~~~sql
TRUNCATE TABLE staging_orders;
~~~

TRUNCATE deletes data via a DDL mechanism. It triggers an implicit commit and cannot be undone with a standard ROLLBACK. If you need rollbackable deletion, use DELETE inside an appropriate transaction:

~~~sql
DELETE FROM staging_orders;

-- Inspect the result:
SELECT COUNT(*) FROM staging_orders;

-- Choose one:
-- COMMIT;
-- ROLLBACK;
~~~

DELETE generates undo and can roll back; TRUNCATE is a structural/segment operation with different semantics.

## 4. DDL Erases SAVEPOINTs and Limits ROLLBACK

### 4.1 SAVEPOINT Does Not Survive Across a DDL Boundary

Example:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (3, 'before savepoint');

SAVEPOINT before_ddl;

CREATE TABLE ddl_savepoint_demo (
    id NUMBER
);

ROLLBACK TO before_ddl;
~~~

`ROLLBACK TO` will raise an error because the pre-DDL implicit commit ended the transaction containing that SAVEPOINT. Savepoints from the old transaction are no longer valid.

### 4.2 ROLLBACK Cannot Go Back Past Committed DDL

Suppose a script runs:

~~~sql
INSERT INTO deployment_log (message)
VALUES ('start deployment');

ALTER TABLE customers ADD (segment_code VARCHAR2(20));

UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

ROLLBACK;
~~~

When the script reaches ROLLBACK:

- The INSERT into `DEPLOYMENT_LOG` was committed before `ALTER TABLE`.
- `ALTER TABLE` was committed upon success.
- The UPDATE after `ALTER TABLE` was not committed by another DDL, so ROLLBACK can discard the UPDATE.

The outcome can be a schema that already has column `SEGMENT_CODE` and a saved deployment-start log, while the backfill was rolled back. This partial state must be anticipated in deployment workflows.

### 4.3 DDL Is Not Part of a Rollbackable DML Transaction

Do not design around this model:

~~~text
BEGIN TRANSACTION
    DML 1
    DDL 1
    DML 2
    DDL 2
    DML 3
ROLLBACK on error
~~~

This model does not exist as a single ACID transaction encompassing all Oracle DDL. Each DDL introduces its own commit boundary.

## 5. Comparing DELETE, TRUNCATE, and DROP

All three commands can make data or tables disappear from normal queries, yet their semantics differ:

| Criterion | DELETE | TRUNCATE | DROP TABLE |
|---|---|---|---|
| Command group | DML | DDL | DDL |
| Scope | Can delete partially via WHERE | Removes all rows of the table | Drops the table object |
| WHERE clause | Yes | No | No |
| Can ROLLBACK in a normal transaction? | Yes, before COMMIT | No | No |
| DELETE triggers | May fire row/statement DELETE triggers per definition | Does not fire DELETE triggers like DELETE | Not row-by-row DELETE |
| Table structure afterward | Remains | Remains | Dropped |
| Implicit commit | Does not auto-commit like DDL | Yes | Yes |

Example of deleting a subset:

~~~sql
DELETE FROM orders
WHERE status = 'CANCELLED';
~~~

You can verify the row count and roll back if not committed yet.

TRUNCATE:

~~~sql
TRUNCATE TABLE orders_stage;
~~~

Cannot filter with WHERE and cannot roll back like DELETE.

DROP:

~~~sql
DROP TABLE orders_stage;
~~~

Removes the table object. Recycle bin or flashback table mechanisms may offer recovery paths under some configurations, but those are not normal transaction ROLLBACK and must not replace backup/recovery planning.

## 6. DDL Inside PL/SQL Still Triggers Implicit Commit

### 6.1 Dynamic DDL with EXECUTE IMMEDIATE

PL/SQL does not allow writing many static DDL commands directly in a block body like DML statements. Dynamic DDL can be run via:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE dynamic_ddl_demo (id NUMBER)';
END;
/
~~~

Wrapping DDL inside `BEGIN...END` does not turn it into DML and does not remove implicit commit. DDL executed via `EXECUTE IMMEDIATE` retains DDL commit semantics.

### 6.2 Exception Handlers Cannot Roll Back DML Before DDL

~~~sql
BEGIN
    INSERT INTO deployment_log (message)
    VALUES ('before dynamic DDL');

    EXECUTE IMMEDIATE
        'CREATE TABLE dynamic_table_demo (id NUMBER)';

    RAISE_APPLICATION_ERROR(-20001, 'Simulated failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The INSERT into `DEPLOYMENT_LOG` was committed before `EXECUTE IMMEDIATE` executed `CREATE TABLE`. If an error occurs afterward and the handler runs ROLLBACK, that INSERT is still not undone. ROLLBACK only applies to the current transaction after the DDL boundary.

This is why you should never place DDL between DML steps and rely on a single exception handler with ROLLBACK as though the entire block were atomic.

### 6.3 Bind Variables and Object Names in Dynamic DDL

In dynamic SQL, bind variables can supply data values in supported positions, but cannot substitute table/column names as identifiers:

~~~sql
-- Cannot bind a table name this way:
EXECUTE IMMEDIATE 'CREATE TABLE :table_name (id NUMBER)'
USING p_table_name;
~~~

If an object name must be dynamic, validate/whitelist the identifier and quote it properly per Oracle rules, such as using `DBMS_ASSERT` where appropriate. Never concatenate user-supplied table name strings directly into DDL due to SQL injection risk and creating unintended objects.

## 7. Impact on Deployment Scripts

A deployment script typically combines:

- Creating or altering tables, columns, constraints, and indexes.
- Loading or transforming data.
- Creating views, procedures, triggers, and sequences.
- Validating data and recording the deployment version.

Without recognizing implicit commit boundaries, a script can leave a partially deployed state after a failure.

### 7.1 Example of a Misleading Script

~~~sql
UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'FEATURE_X';

ALTER TABLE customers
ADD (new_code VARCHAR2(20));

UPDATE customers
SET new_code = 'DEFAULT'
WHERE new_code IS NULL;

-- Author assumes everything can roll back if the validation step fails:
ROLLBACK;
~~~

Reality:

1. The `APPLICATION_CONFIG` UPDATE was committed before `ALTER TABLE`.
2. `ALTER TABLE` was committed upon success.
3. The `CUSTOMERS` UPDATE is DML after DDL; if no subsequent commit occurred, ROLLBACK can undo it.

The script cannot revert to its initial state merely via ROLLBACK.

### 7.2 Separate Phases Clearly

A controllable deployment workflow can be split into:

~~~text
Preflight / precondition checks
          |
          v
Additive DDL (create/add compatible structures)
          |
          v
Backfill / data transformation via DML
          |
          v
Validation / data reconciliation
          |
          v
Application switch / cutover
          |
          v
Cleanup DDL (drop old structures once safe)
~~~

Each step needs clear preconditions, expected outcomes, and its own recovery path. Never assume all phases can roll back together.

### 7.3 Execute DDL Before DML Groups Needing Rollback

Whenever possible, finish required DDL before starting a DML group that needs atomicity:

~~~sql
-- Phase 1: DDL; implicit commit forms a clear boundary.
ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- Phase 2: begin the DML group.
UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

-- Verify:
SELECT COUNT(*)
FROM customers
WHERE segment_code IS NULL;

-- Commit only when verification passes:
COMMIT;
~~~

If the backfill fails before COMMIT, the DML group can be ROLLBACKed. The added column still exists and must be handled per the deployment plan.

### 7.4 Avoid DDL in the Middle of a DML Transaction

Avoid:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + 5
WHERE product_id = 10;

CREATE INDEX idx_inventory_product
ON inventory(product_id);

UPDATE inventory
SET reserved_qty = reserved_qty + 3
WHERE product_id = 20;
~~~

`CREATE INDEX` commits the first UPDATE. If the second UPDATE fails and the script rolls back, the first UPDATE is already committed. If both UPDATEs must succeed or fail together, move DDL before or after the DML transaction according to the deployment schedule.

## 8. Designing Migrations with Both DDL and Backfill

A schema-changing migration often contains both DDL and DML. Design it so the application can operate safely across transition states.

### 8.1 Example: Adding a New Column

Requirement: table `CUSTOMERS` has legacy column `FULL_NAME`; the new application wants to use `DISPLAY_NAME`.

A multi-stage rollout approach:

**Stage A — Expand**

~~~sql
ALTER TABLE customers
ADD (display_name VARCHAR2(200));
~~~

This is DDL and causes an implicit commit. The new column is created; the old application can continue operating if the change is compatible.

**Stage B — Backfill**

~~~sql
UPDATE customers
SET display_name = full_name
WHERE display_name IS NULL;

COMMIT;
~~~

For large tables, backfill can be batched by ascending key or partition, recording checkpoints and committing per batch. Account for live application writes occurring during the backfill window.

**Stage C — Validate**

~~~sql
SELECT COUNT(*) AS missing_display_names
FROM customers
WHERE display_name IS NULL;
~~~

Check counts, lengths, anomalous data, and consistency with the source column.

**Stage D — Switch**

Deploy application code reading/writing `DISPLAY_NAME` using a compatible strategy. Dual-write during a transition period may be needed depending on architecture.

**Stage E — Contract**

Only after no application depends on `FULL_NAME` should you consider dropping the old column:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

This is a separate DDL step with an implicit commit and requires a recovery/forward-fix plan. Do not bundle column deletion into a transaction expecting to roll it back if the application throws errors.

### 8.2 Expand-and-Contract Reduces Risk

The expand-and-contract pattern:

1. Expand the schema with backward-compatible changes (add new columns/tables).
2. Deploy applications capable of reading/writing old and new structures.
3. Backfill data in batches and validate.
4. Switch all applications to the new structure.
5. Verify no old dependencies remain.
6. Remove the old structure in a separate migration.

These steps decouple non-rollbackable schema changes from application and data changes. While not mandatory for every migration, it is highly effective for systems requiring continuous delivery or minimal downtime.

## 9. Error Handling and Recovery After DDL

### 9.1 Do Not Use ROLLBACK as a DDL Undo Mechanism

Once `CREATE TABLE`, `ALTER TABLE`, or `DROP` succeeds, a subsequent COMMIT/ROLLBACK does not return the schema to its pre-DDL state.

To reverse a structural change, you need a **compensating DDL** statement or a pre-designed recovery method:

- Added column: may `DROP COLUMN` if safe and no dependencies exist.
- Renamed column: may rename back if applications do not yet depend on it.
- Created index: may `DROP INDEX`.
- Dropped column or table: data cannot always be restored merely via reverse DDL; backups, appropriate recycle bin/flashback, or data copies are needed.

Compensating DDL is a brand-new operation with its own implicit commit. It is not a rollback of the prior DDL.

### 9.2 DDL Succeeds and a Subsequent Step Fails

Example:

~~~sql
ALTER TABLE orders
ADD (source_code VARCHAR2(30));

UPDATE orders
SET source_code = 'WEB'
WHERE channel = 'ONLINE';

-- A later validation step detects an error:
RAISE_APPLICATION_ERROR(-20010, 'Validation failed');
~~~

Column `SOURCE_CODE` is already created and committed. If the UPDATE is uncommitted, it can roll back on error handling; the schema still retains the column. When re-running the script, `CREATE`/`ALTER` may fail because the column already exists.

Therefore migration scripts need:

- Clear preconditions.
- Object state checks before execution.
- Steps that are safely re-runnable where appropriate.
- Migration progress tracking.
- Guidance for handling partially applied state.

### 9.3 Script Idempotency

An idempotent migration can be re-run without causing unintended side effects, or detect an already-applied state and stop safely.

For example, before adding a column, query `USER_TAB_COLUMNS` by normalized `TABLE_NAME` and `COLUMN_NAME`:

~~~sql
SELECT COUNT(*)
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'SEGMENT_CODE';
~~~

If the column already exists, the script must determine:

- Was the column created by a prior run with the exact expected definition?
- Or did it already exist with a different data type/length?
- Can backfill safely continue?
- Should it stop so an operator resolves schema drift?

Checking only for name existence is insufficient; verify that the actual structure matches expectations.

### 9.4 Migration History Table

A history table can record version, start/end timestamps, checksum, status, and deployer. However, because DDL causes an implicit commit, the migration history record and the DDL are not automatically in a single atomic transaction.

Runner designs must account for this scenario:

1. DDL succeeded and committed.
2. Process stopped before recording migration completion.
3. Next run detects that the schema changed while history is not marked done.

Clear reconcile/repair rules are needed rather than blindly re-running all DDL assuming initial state.

## 10. DDL and Script Execution Tools

### 10.1 SQL*Plus and SQLcl

SQL*Plus/SQLcl provide script control directives such as:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
~~~

This instructs the client to exit upon a SQL error and execute the specified ROLLBACK behavior for the current transaction. It cannot undo DML that was already implicitly committed before a DDL statement.

Example:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'FEATURE_X';

ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- If an error occurs here, rollback cannot undo the UPDATE committed before ALTER.
~~~

`WHENEVER SQLERROR` is useful for halting scripts and returning error codes, yet it does not turn DDL into transactional DML.

### 10.2 SQL Developer and Script Execution Modes

SQL Developer offers different statement/script execution modes alongside commit/autocommit options depending on configuration. Even when the client is in manual commit mode, Oracle DDL's implicit commit still executes on the server.

Never rely on a client's Rollback button to undo succeeded DDL. That button can only roll back uncommitted changes in the current transaction.

### 10.3 JDBC Auto-Commit

Java applications can configure:

~~~java
connection.setAutoCommit(false);
~~~

This lets the application manage DML transactions with commit/rollback. However, it **does not prevent Oracle's implicit commit when executing DDL**.

Example:

~~~java
connection.setAutoCommit(false);

try (Statement statement = connection.createStatement()) {
    statement.executeUpdate(
        "UPDATE application_config " +
        "SET config_value = 'new' " +
        "WHERE config_key = 'FEATURE_X'"
    );

    statement.execute(
        "ALTER TABLE customers ADD (segment_code VARCHAR2(20))"
    );

    connection.rollback();
}
~~~

The UPDATE may already have been committed when Oracle executed `ALTER TABLE`. The subsequent rollback call cannot undo that UPDATE. JDBC `autoCommit=false` does not alter server-side database transaction rules.

If `autoCommit=true`, the driver normally commits DML per JDBC rules after each successful statement, introducing additional client-side commit boundaries. That is a different behavior from DDL-triggered implicit commits. When writing migrations, understand both driver settings and Oracle server semantics.

### 10.4 Flyway, Liquibase, and Migration Runners

Migration tools can organize migrations around transactions, record history, and halt on error. However, no tool can turn an Oracle DDL statement with implicit commit into a statement rollbackable like ordinary DML.

When using migration tools:

- Check documentation on transaction handling for your tool version and Oracle driver.
- Identify which migrations contain DDL and which contain only DML.
- Do not expect a migration mixing multiple DDL/DML statements to roll back atomically if a middle step fails.
- Design migrations to inspect and recover from partially applied states.
- Inspect the history table if a script fails after DDL has committed.

Some tools include DDL detection or non-transactional migration modes; exact behavior depends on version and configuration, so verify against your tool's documentation.

## 11. Impact on Locks and Other Sessions

### 11.1 Pre-DDL Commit Releases Transaction Locks

Uncommitted DML may hold row locks. When Oracle performs an implicit commit before DDL, transaction locks are released according to commit rules.

This can change when other sessions see committed data or proceed with updating rows.

### 11.2 DDL May Still Require Metadata Locks

After the implicit commit, DDL may require object or metadata locks. If another session is using the object in a conflicting manner, DDL may wait or fail due to lock timeout/locking conditions.

Implicit commit does not mean DDL always executes instantaneously; it only defines the transaction boundary of the executing session.

### 11.3 Do Not Use DDL to Arbitrarily Release Locks

Running a DDL statement to force a transaction commit can inadvertently commit unvalidated business data. To release locks, manage transactions and COMMIT/ROLLBACK according to business rules, rather than using DDL as a disguised commit command.

## 12. Deployment Script Patterns to Avoid and Prefer

### 12.1 Pattern to Avoid: Mixing Unconfirmed DML with DDL

~~~sql
UPDATE invoices
SET status = 'READY'
WHERE invoice_date < DATE '2026-01-01';

CREATE INDEX idx_invoices_status
ON invoices(status);

-- Operator spots an error in the next step and runs ROLLBACK:
ROLLBACK;
~~~

The first UPDATE was already committed before `CREATE INDEX`. If the UPDATE condition was wrong, rolling back at the end cannot fix the committed data.

### 12.2 Clearer Pattern: Separate DDL and DML

~~~sql
-- Phase A: structural change.
CREATE INDEX idx_invoices_status
ON invoices(status);

-- Phase B: data change.
UPDATE invoices
SET status = 'READY'
WHERE invoice_date < DATE '2026-01-01';

-- Verify before confirming data:
SELECT COUNT(*)
FROM invoices
WHERE invoice_date < DATE '2026-01-01'
  AND status <> 'READY';

-- COMMIT when requirements pass; ROLLBACK if not.
~~~

DDL was committed before starting the DML group. The DML group can be rolled back independently if validation fails.

### 12.3 Checkpoint-Based Deployment Pattern

~~~sql
-- 1. Preflight: inspect existing objects/columns/indexes and data.

-- 2. Additive DDL: run separately, verify success.
ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- 3. Backfill: single transaction or controlled batches.
UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

-- 4. Validate.
SELECT COUNT(*) AS rows_missing_segment
FROM customers
WHERE segment_code IS NULL;

-- 5. Only COMMIT data when validation passes.
COMMIT;

-- 6. Cleanup DDL in a separate migration/release once dependencies are gone.
~~~

Each checkpoint should be recorded so operators know which steps completed and which require continuation or recovery.

## 13. Designing Re-Runnable Scripts

### 13.1 Check Before CREATE

Before creating an object, you can query dictionary views:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'DEPLOYMENT_STAGE';
~~~

If the object already exists, do not blindly skip without checking its definition. A table with the same name but different columns or constraints could indicate schema drift.

### 13.2 Check Columns Before ALTER

~~~sql
SELECT column_name,
       data_type,
       data_length,
       nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'SEGMENT_CODE';
~~~

Verify data type, length, and nullability to confirm actual state. If the exact expected structure already exists, the script can move to the next step per migration policy; if it differs, stop and require drift resolution.

### 13.3 Controlled Handling of Already-Exists Errors

You can write PL/SQL checking the dictionary before DDL or catching exact object-exists error codes. Avoid using:

~~~sql
WHEN OTHERS THEN NULL;
~~~

to swallow all errors. Doing so can hide privilege, tablespace, syntax, locking, or dependency errors. If catching exceptions, handle only the expected condition and `RAISE` all other errors.

Note: even when DDL is inside `EXECUTE IMMEDIATE` wrapped in an exception handler, the pre-DDL implicit commit still takes effect.

## 14. Lab: Observing Implicit Commit

Run this lab in a dedicated practice schema with table-creation privileges. Do not use business tables or a production schema. DDL in the lab still commits the current transaction, so use test data only.

### 14.1 Create the Table

~~~sql
CREATE TABLE lab_ddl_txn (
    id   NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

### 14.2 Insert DML Without Committing

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (1, 'insert before create table');
~~~

Within the same session, you can SELECT to see row ID=1. Other sessions under default isolation do not yet see uncommitted changes.

### 14.3 Run Unrelated DDL

~~~sql
CREATE TABLE lab_ddl_marker (
    id NUMBER
);
~~~

The `CREATE TABLE` statement triggers an implicit commit. The DML inserting ID=1 has now been committed.

### 14.4 Attempt ROLLBACK

~~~sql
ROLLBACK;

SELECT *
FROM lab_ddl_txn
WHERE id = 1;
~~~

Row ID=1 still exists because it committed before `CREATE TABLE`.

### 14.5 Try DML After DDL

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (2, 'insert after create table');

ROLLBACK;

SELECT *
FROM lab_ddl_txn
ORDER BY id;
~~~

Row ID=2 is rolled back; row ID=1 remains. This demonstrates the new transaction after the DDL boundary.

### 14.6 Try SAVEPOINT

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (3, 'before savepoint');

SAVEPOINT sp_before_ddl;

CREATE TABLE lab_ddl_savepoint_marker (
    id NUMBER
);

ROLLBACK TO sp_before_ddl;
~~~

`ROLLBACK TO` cannot revert to the pre-DDL savepoint because the transaction was committed.

### 14.7 Compare DELETE and TRUNCATE

Recreate data if needed, then:

~~~sql
DELETE FROM lab_ddl_txn
WHERE id = 1;

ROLLBACK;
~~~

Row ID=1 is restored because DELETE is DML and was uncommitted.

In another lab table:

~~~sql
TRUNCATE TABLE lab_ddl_txn;

ROLLBACK;
~~~

TRUNCATE cannot be undone with a standard ROLLBACK.

### 14.8 Clean Up Lab Tables

Only drop tables you created in the lab schema after confirming you no longer need the data:

~~~sql
DROP TABLE lab_ddl_savepoint_marker;
DROP TABLE lab_ddl_marker;
DROP TABLE lab_ddl_txn;
~~~

`DROP TABLE` is also DDL and triggers an implicit commit. Do not run cleanup commands on tables outside your lab.

## 15. Pre-Execution Checklist for Deployment Scripts

Before running a script containing DDL, verify:

1. Which commands are DDL and which are DML?
2. Is there any uncommitted DML preceding a DDL statement?
3. If DDL fails, will preceding DML already have committed?
4. Which SAVEPOINTs will be lost when DDL executes?
5. Is anyone expecting ROLLBACK to undo CREATE, ALTER, DROP, or TRUNCATE?
6. Does the script separate schema-change phases from data-migration phases?
7. Does each DDL have preconditions, postconditions, and a recovery plan?
8. If the script halts midway, can current object states be determined?
9. Are dictionary checks used to detect existing objects or schema drift?
10. Can DML backfill be safely re-run? Are checkpoints/batches used for large datasets?
11. Does migration history handle the case where DDL committed but history logging did not complete?
12. Does the client/driver have its own auto-commit setting?
13. Are exception handlers or `WHENEVER SQLERROR` being mistaken for full DDL rollback?
14. Do DROP/TRUNCATE operations have backups, scope verification, and appropriate recovery plans?
15. Might DDL wait on locks or disrupt sessions using the target object?

## 16. Summary

In Oracle Database, DDL creates transaction boundaries through implicit commits:

- Oracle commits the current transaction before executing DDL.
- When DDL succeeds, structural changes are also committed.
- Uncommitted DML prior to DDL cannot be restored by a subsequent ROLLBACK, even if the DDL fails.
- SAVEPOINTs from transactions prior to DDL cease to be valid.
- DML after DDL can still COMMIT/ROLLBACK in a new transaction until another commit boundary occurs.
- TRUNCATE and DROP are DDL; DELETE is DML and can roll back before COMMIT.
- DDL inside `EXECUTE IMMEDIATE`, stored procedures, or client scripts remains subject to Oracle's commit semantics.
- JDBC `autoCommit=false`, SQL Developer manual commit, or `WHENEVER SQLERROR ROLLBACK` cannot prevent server-side implicit commits.

When deploying, separate structural changes from DML groups needing rollbackability, use clear checkpoints, check schema state before re-running, prepare forward-fix/compensating DDL, and never treat an entire migration containing DDL as a single atomically rollbackable transaction. Understanding implicit commit prevents accidental commits of business data and helps build recoverable deployment pipelines when failures happen mid-flight.
