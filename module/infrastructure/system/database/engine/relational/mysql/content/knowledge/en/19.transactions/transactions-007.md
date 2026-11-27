# Atomic DDL, Implicit Commit, and DDL Rollback Limitations

In MySQL, many statements that modify schema structure such as CREATE TABLE, ALTER TABLE, DROP TABLE, and TRUNCATE TABLE are DDL (Data Definition Language). They follow different transactional rules from DML statements such as INSERT, UPDATE, and DELETE. A DDL statement usually creates an implicit commit boundary, so you cannot place multiple schema changes into a single transaction and use ROLLBACK to undo all of them.

Starting in MySQL 8.0, Atomic DDL adds the ability to execute certain DDL operations under an all-or-nothing principle when the server encounters an error or crash. However, **Atomic DDL does not mean transactional DDL**: it protects the integrity of the DDL operation itself during execution and recovery, but does not make DDL undoable via a user transaction's ROLLBACK.

This lesson falls within the scope of DATABASE_MYSQL: understanding transaction boundaries, operating schema changes, planning migrations, reducing data loss risks, and distinguishing crash recovery from business rollback capability.

## 1. DDL, DML, and Transactions Serve Different Roles

### 1.1. DDL Changes Database Structure

DDL modifies database objects or metadata:

- CREATE TABLE: creates a table.
- ALTER TABLE: alters table structure.
- DROP TABLE: drops a table.
- RENAME TABLE: renames a table.
- CREATE INDEX and DROP INDEX: creates or drops an index.
- TRUNCATE TABLE: deletes all rows using a DDL operation.

Example:

~~~sql
CREATE TABLE account (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    balance DECIMAL(15, 2) NOT NULL
) ENGINE = InnoDB;

ALTER TABLE account
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';

CREATE INDEX idx_account_status
    ON account(status);
~~~

These commands alter the table's schema and metadata.

### 1.2. DML Changes Data Within Tables

DML operates on rows:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

With InnoDB, DML changes inside a transaction can be COMMITted or ROLLBACKed. If an error occurs before COMMIT, the application can roll back to return data to its pre-transaction state.

### 1.3. Do Not Infer That DDL Can Roll Back Like DML

The following example does not create a single transaction wrapping both data and structural changes:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE account_id = 1;

ALTER TABLE account
    ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
~~~

ALTER TABLE causes an implicit commit. The preceding UPDATE is committed before the DDL executes. After ALTER completes, ROLLBACK cannot undo the added column or revert the committed transaction.

This is a rule to remember when writing migrations: never place DDL in the middle of a DML sequence and assume a final ROLLBACK will restore everything.

## 2. What Is Implicit Commit?

Implicit commit is when MySQL automatically ends an active transaction without requiring the application to call COMMIT.

Some statements trigger an implicit commit before executing; many statements also cause a commit after successful execution. This creates transaction boundaries that applications must be aware of.

Example:

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('Starting schema change');

ALTER TABLE account
    ADD COLUMN source_code VARCHAR(30) NULL;

INSERT INTO audit_log(message)
VALUES ('Added source_code');

ROLLBACK;
~~~

Suppose ALTER TABLE succeeds:

1. The first INSERT is implicitly committed before ALTER TABLE.
2. ALTER TABLE executes and completes according to DDL rules.
3. The second INSERT belongs to a new transaction (if autocommit is off).
4. The final ROLLBACK only rolls back the second INSERT.
5. The first audit row and the schema change still remain.

If you want audit logging and schema changes to share the same lifecycle, design a separate migration process rather than relying on a single SQL transaction.

## 3. Statements That Commonly Cause Implicit Commit

Common DDL groups that trigger implicit commit include:

| Group | Examples |
|---|---|
| Database | CREATE DATABASE, ALTER DATABASE, DROP DATABASE |
| Table | CREATE TABLE, ALTER TABLE, DROP TABLE |
| Table name | RENAME TABLE |
| Index | CREATE INDEX, DROP INDEX |
| Table data via DDL | TRUNCATE TABLE |
| View | CREATE VIEW, ALTER VIEW, DROP VIEW |
| Trigger | CREATE TRIGGER, DROP TRIGGER |
| Stored routine | CREATE PROCEDURE, ALTER PROCEDURE, DROP PROCEDURE; CREATE/DROP FUNCTION |
| Event | CREATE EVENT, ALTER EVENT, DROP EVENT |
| Tablespace/server object | Certain CREATE/ALTER/DROP TABLESPACE or SERVER commands |

The exact list can vary by version and statement category. Aside from DDL, certain administrative operations also create commit boundaries, such as LOCK TABLES and several table-maintenance commands.

Check the manual for your exact version before placing an administrative statement inside a transaction.

### 3.1. START TRANSACTION and BEGIN Can Also End a Previous Transaction

MySQL does not support nested transactions where a new START TRANSACTION creates a child transaction inside an active transaction.

Example:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

START TRANSACTION;

UPDATE account
SET balance = balance + 50
WHERE account_id = 2;

ROLLBACK;
~~~

The second START TRANSACTION ends the previously active transaction. Thus, the first UPDATE was committed; ROLLBACK only affects the second transaction.

To split a workflow into rollback points within the same transaction, use SAVEPOINT instead of nested START TRANSACTION:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE account
SET balance = balance + 50
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

COMMIT;
~~~

SAVEPOINT only applies to transactions supporting rollback. It does not protect DDL from implicit commit.

### 3.2. Changing autocommit

When autocommit is off and you switch it on:

~~~sql
SET autocommit = 0;

UPDATE account
SET balance = balance + 10
WHERE account_id = 1;

SET autocommit = 1;
~~~

Switching autocommit from 0 to 1 commits the active transaction. Do not treat SET autocommit = 1 as a harmless configuration operation mid-transaction.

If the application uses a connection pool, manage autocommit explicitly and restore connection state before returning the connection to the pool.

## 4. Exception for TEMPORARY TABLE

Two statements for creating and dropping temporary tables have special behavior:

- CREATE TEMPORARY TABLE does not cause an implicit commit.
- DROP TEMPORARY TABLE does not cause an implicit commit.

However, creating or dropping a temporary table **cannot be rolled back** like regular DML changes.

Example:

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('This row can be rolled back');

CREATE TEMPORARY TABLE temp_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);

ROLLBACK;
~~~

After ROLLBACK:
- The audit_log INSERT is rolled back.
- The temporary table still exists in the current session.

This is a commonly misunderstood exception: the statement does not commit the transaction, yet the temporary table change itself is still not rolled back.

A temporary table only exists in the connection that created it and disappears automatically when the session ends. Do not use temporary tables to store data that needs long-term persistence or as a transaction-guarantee mechanism.

Note: the exception above applies to CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE. Other DDL statements acting on tables must still be checked for their implicit commit rules.

## 5. What Is Atomic DDL?

Atomic DDL is the ability to execute a DDL operation under the principle that the entire operation either completes or is recovered to its pre-operation state if an error or crash occurs within the supported scope.

Before MySQL 8.0, certain DDL operations could leave inconsistent metadata or intermediate files if the server crashed at an unfortunate moment. MySQL 8.0 introduced a transactional data dictionary and the Atomic DDL mechanism to coordinate metadata changes, storage engine operations, and binary log writes for supported operations.

This can be understood via an ALTER TABLE example:

~~~sql
ALTER TABLE account
    ADD COLUMN loyalty_level INT NOT NULL DEFAULT 0;
~~~

With a supported Atomic DDL operation on InnoDB:
- If the DDL completes, the new schema is recorded.
- If the server crashes during the operation, recovery brings the system to a consistent state: the DDL change is either completed or rolled back under the atomic mechanism.
- The table is not left in a half-old, half-new state where only part of the metadata and part of the data were applied.

Atomic DDL protects operation integrity at the server/storage engine level. It does not turn ALTER TABLE into a statement that can be ROLLBACKed after succeeding.

## 6. Atomic DDL Is Not Transactional DDL

These two concepts solve two different problems:

| Criterion | Atomic DDL | User-Level Transactional DDL |
|---|---|---|
| Goal | Ensure a single DDL operation executes completely or recovers completely on error/crash | Allow placing DDL inside a transaction and undoing it with ROLLBACK |
| When DDL succeeds | DDL is finished and committed at the DDL boundary | May still wait for transaction COMMIT |
| ROLLBACK after DDL | Does not undo completed DDL | Can undo if the DBMS supports transactional DDL |
| Crash recovery | Atomic guarantees for supported operations | Depends on transaction mechanism |
| MySQL | Has Atomic DDL for supported operations starting in MySQL 8.0 | Regular DDL still triggers implicit commit |

Example:

~~~sql
START TRANSACTION;

ALTER TABLE account
    ADD COLUMN migration_flag TINYINT NOT NULL DEFAULT 0;

ROLLBACK;
~~~

If ALTER TABLE succeeds, the migration_flag column still exists after ROLLBACK. Atomic DDL does not change this rule.

Remember: **Atomic describes the integrity of a single DDL operation; ROLLBACK describes the ability to undo a user's transaction.**

## 7. Atomic DDL Support Scope

MySQL 8.0 supports Atomic DDL for many operations on InnoDB objects, including common ones such as:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- RENAME TABLE.
- TRUNCATE TABLE.
- CREATE INDEX.
- DROP INDEX.

Specific capability depends on statement type, storage engine, and object. You must not infer that every DDL in MySQL is atomic merely because the server is MySQL 8.x.

### 7.1. Storage Engine Plays a Decisive Role

InnoDB supports transactions and is the primary foundation for Atomic DDL on InnoDB tables. Storage engines without the same transaction/DDL recovery mechanism may not provide the same level of guarantee.

For example, do not assume DDL operations on MyISAM tables have the same atomicity as InnoDB. If a system still uses multiple engines, list all tables and engines before evaluating a migration plan.

Check engines:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

### 7.2. Temporary Tables Do Not Share the Same Guarantee

CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE are exceptions regarding implicit commit, yet temporary table changes cannot be rolled back. Do not apply conclusions about regular InnoDB table Atomic DDL to temporary tables.

### 7.3. Verify the Exact Version

~~~sql
SELECT VERSION();
~~~

When operating MySQL 5.7, MySQL 8.0, MySQL 8.4, or MySQL-compatible services, check documentation for your exact version and provider. Syntax may look identical while atomic DDL support or storage engine behavior differs.

## 8. What Happens When DDL Fails?

Three situations must be distinguished:

### 8.1. DDL Fails Before Completion

For example, ALTER TABLE cannot add a unique index because existing data has duplicates:

~~~sql
ALTER TABLE customer
    ADD UNIQUE KEY uq_customer_email (email);
~~~

If duplicate emails exist, MySQL rejects creating the unique index. With a supported Atomic DDL operation, metadata and table state are restored to the consistent state prior to the operation. Old data remains intact; the ALTER command does not leave a half-built index.

### 8.2. DDL Succeeds

If ALTER TABLE succeeds, the schema change is complete. A subsequent ROLLBACK command does not remove the newly created index or column.

### 8.3. Client Disconnects or Times Out While DDL Is Running

If the client times out or loses connection, you cannot conclude from the application side alone that the DDL failed. The server may have completed the operation while the response failed to reach the client.

Check the actual state:

~~~sql
SHOW CREATE TABLE customer\G
~~~

Or inspect metadata:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer'
ORDER BY ORDINAL_POSITION;
~~~

Before resending DDL, verify whether the column/index already exists. If a migration is blindly retried, the application may encounter "duplicate column name" or "duplicate key name" errors.

Atomic DDL keeps database state consistent after a crash; it does not guarantee the client always knows the final outcome of a sent request.

## 9. TRUNCATE, DELETE, and DROP Have Different Rollback Limits

These three commands all appear to remove data, yet their semantics differ greatly.

| Command | Type | Rollbackable via InnoDB Transaction? | Effect |
|---|---|---|---|
| DELETE FROM table | DML | Yes, before COMMIT | Deletes rows matching condition; can use WHERE |
| TRUNCATE TABLE table | DDL | No | Deletes all rows, usually resets AUTO_INCREMENT |
| DROP TABLE table | DDL | No | Removes both table structure and data |

### 9.1. DELETE Can Be Rolled Back

~~~sql
START TRANSACTION;

DELETE FROM audit_log
WHERE created_at < '2024-01-01';

-- Verify results before deciding.
ROLLBACK;
~~~

With InnoDB, if not yet COMMITted, ROLLBACK can restore the deleted rows.

### 9.2. TRUNCATE Causes Implicit Commit

~~~sql
START TRANSACTION;

INSERT INTO audit_log(message)
VALUES ('Before truncate');

TRUNCATE TABLE staging_import;

ROLLBACK;
~~~

TRUNCATE causes an implicit commit. The earlier INSERT is committed before TRUNCATE executes; ROLLBACK cannot restore staging_import.

TRUNCATE is usually faster than DELETE without WHERE because it does not remove rows individually in the standard DML way. However, it is a DDL operation, can reset AUTO_INCREMENT, and is restricted when the table is referenced by foreign keys.

### 9.3. DROP TABLE Is Not a Undoable Data Deletion Method

~~~sql
DROP TABLE old_import;
~~~

DROP TABLE deletes the table object. With supported Atomic DDL operations, the server guarantees operation integrity during recovery; however, once DROP succeeds, ROLLBACK cannot restore the table.

To recover, you need backups, point-in-time recovery, replicas, or a process to recreate the schema and data.

## 10. SAVEPOINT Cannot Survive Implicit Commit

SAVEPOINT helps roll back part of a DML transaction:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT before_second_update;

UPDATE account
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT before_second_update;

COMMIT;
~~~

However, if DDL is inserted:

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT before_schema_change;

ALTER TABLE account
    ADD COLUMN remark VARCHAR(100) NULL;

ROLLBACK TO SAVEPOINT before_schema_change;
~~~

ALTER TABLE causes an implicit commit. The prior transaction and savepoint are no longer valid. ROLLBACK TO SAVEPOINT will report an error because the savepoint was released or no longer belongs to the current transaction.

Do not use SAVEPOINT to try to make DDL transactional.

## 11. DDL and Metadata Locks

Even when DDL is atomic, it may still have to wait for a metadata lock (MDL).

When a transaction accesses a table, MySQL can hold a metadata lock on that table until the transaction ends. DDL such as ALTER TABLE requires an exclusive metadata lock during certain phases. If another transaction holds a compatible lock and has not ended yet, ALTER TABLE may have to wait.

Example:

**Connection A**

~~~sql
START TRANSACTION;

SELECT *
FROM account
WHERE account_id = 1;

-- Keep transaction open.
~~~

**Connection B**

~~~sql
ALTER TABLE account
    ADD COLUMN note VARCHAR(100) NULL;
~~~

Connection B may wait on Connection A's metadata lock. If many queries queue behind the waiting DDL, application latency can spike.

### 11.1. Ways to Reduce Metadata Lock Risk

- Avoid long transactions or idle-in-transaction sessions during migrations.
- Check connections holding transactions before running DDL.
- Test migrations on a replica with near-production size.
- Choose low-traffic windows if operations may need strong locks.
- Set appropriate timeouts and monitor the process list / metadata locks.
- Have an operational procedure to cancel or handle DDL waiting too long.

Inspect active transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Inspect metadata locks if Performance Schema is enabled:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, LOCK_STATUS;
~~~

Atomic DDL protects post-crash/error state; it does not eliminate metadata locks or guarantee ALTER TABLE always runs non-blocking.

## 12. Online DDL Does Not Mean Transactional DDL

Some ALTER TABLE operations support different algorithms or lock levels:

| Option | General Meaning |
|---|---|
| ALGORITHM=INSTANT | Instant metadata change for supported operations |
| ALGORITHM=INPLACE | Storage engine performs change in place; may still rebuild or consume significant resources |
| ALGORITHM=COPY | Creates/copies data to a new structure, typically taking more time and I/O |
| LOCK=NONE | Allows concurrent DML during supported phases |
| LOCK=SHARED | Allows reads but restricts writes during operation scope |
| LOCK=EXCLUSIVE | Requires stronger lock, potentially blocking both reads and writes |

Example requesting a change only execute if MySQL supports a non-write-locking algorithm:

~~~sql
ALTER TABLE account
    ADD COLUMN source_tag VARCHAR(30) NULL,
    ALGORITHM=INSTANT,
    LOCK=NONE;
~~~

Not every change supports INSTANT or LOCK=NONE. If the requested option is unsupported, MySQL can return an error instead of silently falling back to another algorithm. This is useful to avoid accidentally running an unexpectedly heavy DDL.

### 12.1. Online Does Not Mean Lock-Free

Even online DDL still needs metadata locks at certain moments, usually at the start and end. It can also generate I/O, CPU, redo/undo load, temporary space usage, and replication impact.

### 12.2. Atomic and Online Are Two Independent Axes

A DDL operation can be:
- Atomic yet require strong locks.
- Online for most of its duration yet still require brief metadata locks.
- Unable to run online with the desired algorithm.
- Atomic at the crash-recovery level yet impossible to roll back once completed.

Evaluate separately:
1. Does the operation have Atomic DDL?
2. Does it cause an implicit commit?
3. Which ALGORITHM/LOCK options are supported?
4. How long might it block queries?
5. Are temporary space and resources sufficient?

## 13. Why Can't ROLLBACK Restore Committed DDL?

A DDL operation typically modifies multiple components:
- Database metadata.
- Column, index, and constraint definitions.
- Physical structure of tables and indexes.
- Related files/tablespaces.
- Information in the data dictionary and binary log.

Atomic DDL coordinates these components so the server does not leave an incomplete state on crash. Once the operation finishes, it is recorded as a committed schema change.

A user transaction's ROLLBACK only undoes transactional changes still within the current transaction. It does not reverse a completed DDL and does not automatically restore data removed by DROP or TRUNCATE.

Example:

~~~sql
ALTER TABLE customer
    DROP COLUMN legacy_secret;
~~~

After the statement succeeds, legacy_secret and the data in that column are removed. ROLLBACK cannot recreate the column contents. Restoring requires another data source such as backups, binlogs, or a replica.

Therefore, before destructive DDL, confirm:
- Whether the column/table is still used by the application.
- Whether data needs to be archived or migrated before deletion.
- Whether backups can be restored and have been tested.
- Whether deployment can be phased via expand-and-contract.

## 14. Designing Safe Migrations with DDL

You cannot rely on a single transaction to wrap DDL, so migrations must be organized into observable and recoverable steps.

### 14.1. Preparation Phase

1. Identify current schema and target schema.
2. Check MySQL version, storage engine, and Atomic DDL capability.
3. Check for duplicates, NULLs, foreign keys, and invalid data.
4. Estimate duration, storage space, and lock impact.
5. Take backups and test restore.
6. Dry-run the migration on an environment close to production.
7. Define stop conditions, retry rules, and recovery plans.

### 14.2. Deployment Phase

- Stop or coordinate concurrent migrations.
- Check for long transactions and metadata locks.
- Run each DDL independently.
- Verify schema state after each step.
- Perform DML backfills in batches if needed.
- Monitor errors, replication lag, and system load.
- Only switch the application to use the new structure after verification.

### 14.3. Expand-and-Contract

When large changes risk impacting the application, deploy across multiple compatible versions:

**Expand**
- Add new columns or tables.
- Keep old structure so the current application version continues working.
- Backfill data from old to new in batches.

**Migrate**
- Application writes concurrently or gradually transitions to the new structure.
- Compare data between both structures.
- Switch read queries to the new columns/tables.

**Contract**
- Only after confirming no application version depends on the old structure, drop old columns or tables in a separate migration.

Each DDL remains its own commit boundary. The advantage of this workflow is having time for verification and transition, not DDL rollback capability.

## 15. Migration Rollback and Forward Fix

Because committed DDL cannot be ROLLBACKed like DML, the concept of migration rollback usually means running a new migration to return the schema close to its prior structure.

Example:
- Migration A adds a status column.
- Migration B renames a column.
- Migration C drops an old column.

If B has an issue, you can write a new migration renaming it back if data and application allow. But if C already deleted data, recreating the column does not automatically restore old values.

### 15.1. Reverse Migrations Do Not Always Lose Data

Some changes can be reversed relatively safely:
- Adding an index then dropping the index.
- Adding a nullable column then dropping the column if no critical data exists yet.
- Adding a constraint then removing the constraint.

Some changes can lose data:
- DROP COLUMN.
- DROP TABLE.
- TRUNCATE TABLE.
- Narrowing data types causing precision loss or truncation.
- Charset/collation conversions altering data or causing conflicts.

### 15.2. Forward Fix

In production environments, sometimes the safer path is fixing the schema forward via a new migration:
- Keep newly written data.
- Fix column/index/constraint definitions.
- Update the application to a compatible version.
- Avoid restoring the entire database if only one schema change was wrong and new data remains valid.

Choosing rollback versus forward fix depends on whether data was already modified/lost and on recovery capability.

## 16. Hands-On Example: DML Before DDL and ROLLBACK

Create table:

~~~sql
CREATE TABLE transaction_demo (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO transaction_demo (id, amount)
VALUES (1, 100.00), (2, 200.00);
~~~

Execute:

~~~sql
START TRANSACTION;

UPDATE transaction_demo
SET amount = amount + 10
WHERE id = 1;

ALTER TABLE transaction_demo
    ADD COLUMN note VARCHAR(100) NULL;

UPDATE transaction_demo
SET amount = amount + 20
WHERE id = 2;

ROLLBACK;
~~~

Verify:

~~~sql
SELECT *
FROM transaction_demo
ORDER BY id;

SHOW CREATE TABLE transaction_demo\G
~~~

Expected result:
- Row id = 1 has amount = 110.00 because the first UPDATE was implicitly committed before ALTER.
- Column note still exists because ALTER completed.
- Row id = 2 still has amount = 200.00 because the UPDATE after ALTER belonged to a new transaction and was ROLLBACKed.

This exercise directly demonstrates that implicit commit splits a sequence of commands into multiple independent transactions.

## 17. Hands-On Example: Temporary Table and ROLLBACK

~~~sql
START TRANSACTION;

INSERT INTO transaction_demo (id, amount)
VALUES (3, 300.00);

CREATE TEMPORARY TABLE temp_ids (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
);

INSERT INTO temp_ids (id)
VALUES (1), (2);

ROLLBACK;
~~~

After ROLLBACK:
- Row id = 3 in transaction_demo does not exist.
- Temporary table temp_ids still exists in the session.
- Data INSERTed into temp_ids is also not undone like a transactional schema change; DML operations on temporary tables must be evaluated according to the engine and active transaction.

To drop the temporary table:

~~~sql
DROP TEMPORARY TABLE temp_ids;
~~~

DROP TEMPORARY TABLE does not trigger an implicit commit, yet the drop operation itself is not rolled back.

## 18. Common Mistakes

| Mistake or Misconception | Cause | How to Handle |
|---|---|---|
| UPDATE before ALTER gets ROLLBACKed yet data remains | ALTER TABLE implicitly committed the earlier transaction | Separate DDL from DML transactions |
| ROLLBACK does not remove newly added column | DDL already completed and committed | Use reverse migration or forward fix |
| Thinking Atomic DDL is transactional DDL | Confusing crash atomicity with user rollback | Distinguish the two concepts |
| Thinking every DDL is atomic | Atomic DDL only applies to supported operations/engines | Check manual and storage engine |
| Temporary table still exists after ROLLBACK | CREATE/DROP TEMPORARY TABLE does not commit but does not roll back | Manage temporary table lifecycle separately |
| TRUNCATE cannot be recovered | TRUNCATE is DDL and causes implicit commit | Use DELETE inside a transaction if rollback is needed |
| DDL waits for a very long time | Metadata lock from another transaction | Find lock-holding transactions, shorten transactions |
| Online DDL still causes blocking | Online does not eliminate metadata locks | Check LOCK/ALGORITHM and MDL |
| Client times out yet schema changed | Server may have finished before response was lost | Re-read SHOW CREATE TABLE before retrying |
| Migration rollback recreates column without data | Reverse DDL does not restore DROPped data | Backups, binlog, expand-and-contract |
| Second START TRANSACTION loses savepoints | MySQL does not support nested transactions | Use SAVEPOINT within the same transaction |
| AUTO_INCREMENT resets after TRUNCATE | TRUNCATE can reset the counter | Do not use TRUNCATE if sequence must be preserved |

## 19. Pre- and Post-DDL Verification Procedure

### Before Running

~~~sql
SELECT VERSION();

SHOW CREATE TABLE account\G

SELECT
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account';
~~~

Next:
- Check if existing data violates new constraints.
- Check for long transactions and metadata locks.
- Estimate capacity and duration.
- Verify backup/restore.
- Choose ALGORITHM and LOCK if supported by the operation.

### After Running

~~~sql
SHOW CREATE TABLE account\G

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account'
ORDER BY ORDINAL_POSITION;
~~~

If adding an index:

~~~sql
SHOW INDEX FROM account;
~~~

If changing constraints:

~~~sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.table_constraints
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'account';
~~~

Compare the actual schema against the expected migration before allowing the application to use it.

## 20. Atomic DDL and Implicit Commit Operations Checklist

- [ ] Distinguished DDL from DML.
- [ ] Identified which statements cause an implicit commit.
- [ ] Checked whether any transaction is active before running DDL.
- [ ] Understood that completed DDL cannot be ROLLBACKed like DML.
- [ ] Distinguished Atomic DDL from transactional DDL.
- [ ] Verified MySQL version and storage engine.
- [ ] Checked whether the specific operation supports Atomic DDL.
- [ ] Understood the CREATE/DROP TEMPORARY TABLE exception.
- [ ] Distinguished DELETE, TRUNCATE, and DROP.
- [ ] Checked metadata locks and long transactions.
- [ ] Evaluated ALGORITHM and LOCK for Online DDL.
- [ ] Verified backups and tested restore.
- [ ] Tested migration on representative data.
- [ ] Verified schema state after DDL.
- [ ] Prepared reverse migration or forward fix.
- [ ] Avoided blind retries on client timeout.
- [ ] Established procedures for replication lag, lock timeout, and deadlock if relevant to migration.

## 21. Practice Exercises

### Exercise 1: Observe Implicit Commit

Create a demo table, START TRANSACTION, INSERT a row, then ALTER TABLE to add a column and run ROLLBACK. Inspect the INSERTed row and schema. Explain which part was committed.

### Exercise 2: DDL and SAVEPOINT

Create a transaction, UPDATE a row, place a SAVEPOINT, run ALTER TABLE, and try ROLLBACK TO SAVEPOINT. Record the error and explain why the savepoint is no longer valid.

### Exercise 3: Temporary Table

Inside a transaction, INSERT into an InnoDB table and CREATE TEMPORARY TABLE. Run ROLLBACK, then inspect the InnoDB row and the temporary table. Explain the temporary table's no-implicit-commit yet non-rollbackable exception.

### Exercise 4: DELETE vs. TRUNCATE

Create two InnoDB tables with data. Run DELETE in a transaction and ROLLBACK. Run TRUNCATE in another transaction and ROLLBACK. Compare the results and AUTO_INCREMENT.

### Exercise 5: Atomic DDL on Constraint Error

Create a table with duplicate data and try ALTER TABLE to add a UNIQUE index. Verify the command fails and the schema remains consistent. Clean up duplicates and re-run.

### Exercise 6: Metadata Lock

Open two connections. Connection A starts a transaction and reads a table without committing. Connection B runs ALTER TABLE on that table. Observe wait time and metadata_locks. Commit Connection A and watch DDL proceed.

### Exercise 7: Online DDL

Try adding a column with ALGORITHM=INSTANT on a supported version. Then try a change that does not support INSTANT and note the error. Explain why checking the algorithm before production is necessary.

### Exercise 8: Client Timeout

In a lab environment, simulate a client disconnect while DDL runs. Reconnect, use SHOW CREATE TABLE and INFORMATION_SCHEMA to determine state before deciding to retry.

### Exercise 9: Expand-and-Contract

Design a migration to rename the email column to contact_email without immediately breaking older application versions. Split into steps: add column, backfill, dual-write, switch reads, and drop old column.

## 22. Conclusion

DDL in MySQL usually causes an implicit commit, so you cannot group CREATE, ALTER, DROP, or TRUNCATE into a single transaction and use ROLLBACK to undo them. DML on InnoDB can roll back while a transaction is uncommitted; completed DDL cannot.

Atomic DDL from MySQL 8.0 onward ensures supported DDL operations either complete or recover to a consistent state on server error/crash. It does not turn DDL into transactional DDL. When designing migrations, verify engine and version, understand implicit commit, check metadata locks, evaluate online DDL, take backups, and prepare reverse migrations or forward fixes. In particular, when a client times out, always re-read the actual schema before re-running the statement.

## Official References

- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual – Atomic DDL](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual – InnoDB and Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual – Online DDL Performance and Concurrency](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-performance.html)
- [MySQL 8.4 Reference Manual – Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – InnoDB and Transaction Management](https://dev.mysql.com/doc/refman/8.4/en/innodb-autocommit-commit-rollback.html)
- [MySQL 8.4 Reference Manual – TRUNCATE TABLE](https://dev.mysql.com/doc/refman/8.4/en/truncate-table.html)
- [MySQL 8.4 Reference Manual – CREATE TEMPORARY TABLE](https://dev.mysql.com/doc/refman/8.4/en/create-temporary-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Recovery](https://dev.mysql.com/doc/refman/8.4/en/innodb-recovery.html)
