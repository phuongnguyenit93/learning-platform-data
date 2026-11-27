# AUTO-INC locks, innodb_autoinc_lock_mode, and concurrent key allocation

An AUTO_INCREMENT column lets MySQL automatically assign identifier values on INSERT. When multiple transactions insert rows into a table concurrently, InnoDB must coordinate number generation to avoid duplicate values and satisfy replication determinism requirements. The mechanism involved is called the AUTO-INC lock; its locking behavior depends on the `innodb_autoinc_lock_mode` variable.

InnoDB has three modes:

- 0 (traditional): uses an AUTO-INC table lock for every insert-like statement needing auto-generated values; the lock is held until the end of the statement.
- 1 (consecutive): uses an AUTO-INC table lock for bulk inserts; simple inserts hold only a lightweight synchronization mechanism for as long as needed to allocate numbers.
- 2 (interleaved): does not use statement-level AUTO-INC table locks; multiple statements can allocate numbers interleaved.

MySQL 8.0 and 8.4 default to mode 2. This mode increases concurrency and pairs well with row-based replication. If statement-based replication is used, mode 2 does not guarantee that AUTO_INCREMENT assignment order can be reproduced identically on replicas.

This lesson belongs to the DATABASE_MYSQL scope: understanding InnoDB's locking mechanism, predicting concurrent INSERT behavior, choosing a configuration compatible with replication, and designing identifier keys without assuming gapless sequential IDs.

## 1. AUTO_INCREMENT and the need for synchronization during concurrent writes

An AUTO_INCREMENT column asks the storage engine to assign a new value when an INSERT does not supply a suitable explicit value.

~~~sql
CREATE TABLE event_log_demo (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(40) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;

INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN'), ('LOGOUT'), ('PURCHASE');
~~~

InnoDB allocates an `event_id` value for each row. When only one session writes data, allocation looks simple. However, when multiple sessions insert concurrently, they must coordinate so they never receive the same value.

Example of two transactions writing concurrently:

~~~sql
-- Session A
INSERT INTO event_log_demo (event_type)
VALUES ('A-1'), ('A-2'), ('A-3');

-- Session B
INSERT INTO event_log_demo (event_type)
VALUES ('B-1');
~~~

Depending on `innodb_autoinc_lock_mode` and the statement type, Session B's ID may have to wait for Session A to finish, or it may be allocated interleaved among Session A's IDs.

The AUTO-INC lock is a special internal InnoDB mechanism for coordinating AUTO_INCREMENT value allocation. It differs from row locks that protect data rows and metadata locks that protect table definitions.

## 2. What is an AUTO-INC lock?

An AUTO-INC lock is a special table-level lock that InnoDB uses during certain types of INSERTs into tables with an AUTO_INCREMENT column.

The goal of this lock is to coordinate number generation across concurrent statements. This lock does not mean the entire table is locked against all operations:

- Regular SELECTs can still read under MVCC rules.
- An UPDATE on a row that does not allocate AUTO_INCREMENT values does not necessarily wait on an AUTO-INC lock.
- Other insert-like statements needing ID allocation may have to wait depending on the mode.
- Row locks are still used separately to protect row data and constraints.

An important point is that how long the AUTO-INC lock is held differs across modes. In mode 0 and for bulk inserts in mode 1, the table-level lock is held until the statement finishes, not until the transaction commits. The transaction may still hold row locks and other locks until COMMIT/ROLLBACK.

Do not refer to an AUTO-INC lock as a general-purpose table lock. It is an internal lock dedicated to AUTO_INCREMENT allocation.

## 3. Simple inserts and bulk inserts

InnoDB distinguishes statement types based on whether the number of rows to be inserted can be determined in advance.

### 3.1. Simple insert

A simple insert is a statement whose expected row count is known before the statement begins executing. Examples:

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN');

INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN'), ('LOGOUT'), ('PURCHASE');

REPLACE INTO event_log_demo (event_id, event_type)
VALUES (10, 'REPLACED');
~~~

With a multi-row `INSERT ... VALUES`, InnoDB knows the row count in the list ahead of time and can preallocate a range of values.

### 3.2. Bulk insert

A bulk insert is a statement where the number of rows to be inserted cannot be trivially determined when execution starts. Examples:

~~~sql
INSERT INTO event_log_demo (event_type)
SELECT source_event_type
FROM incoming_event;

REPLACE INTO event_log_demo (event_id, event_type)
SELECT source_id, source_type
FROM legacy_event;

LOAD DATA INFILE '/var/lib/mysql-files/events.csv'
INTO TABLE event_log_demo
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
(event_type);
~~~

For `INSERT ... SELECT` or `LOAD DATA`, the actual row count depends on read results or input data. Thus, the allocation mechanism differs from simple inserts.

### 3.3. Mixed-mode insert

A statement can supply explicit AUTO_INCREMENT values for some rows while asking MySQL to auto-generate values for other rows.

~~~sql
INSERT INTO event_log_demo (event_id, event_type)
VALUES
    (NULL, 'AUTO-1'),
    (5000, 'EXPLICIT-5000'),
    (NULL, 'AUTO-2');
~~~

This is a mixed-mode insert. Preallocating values can reserve more numbers than are ultimately used, producing gaps in the sequence. Never assume every allocated ID appears in the table.

## 4. The three innodb_autoinc_lock_mode modes

The `innodb_autoinc_lock_mode` variable controls InnoDB's AUTO_INCREMENT locking strategy.

| Value | Name | Main behavior |
|---:|---|---|
| 0 | traditional | AUTO-INC table lock for every insert-like statement needing allocation; held until end of statement |
| 1 | consecutive | Simple inserts use a brief allocation mechanism; bulk inserts use an AUTO-INC table lock until end of statement |
| 2 | interleaved | No statement-level AUTO-INC table lock; statements can allocate numbers interleaved |

This is a global server setting determined at MySQL startup. Check the current value:

~~~sql
SELECT @@GLOBAL.innodb_autoinc_lock_mode;
~~~

Or:

~~~sql
SHOW VARIABLES LIKE 'innodb_autoinc_lock_mode';
~~~

Do not confuse this setting with autocommit or transaction isolation level. `innodb_autoinc_lock_mode` governs auto-increment ID generation; it does not decide when a transaction commits and does not replace row locking.

## 5. Mode 0: traditional

In mode 0, InnoDB uses an AUTO-INC table lock for all insert-like statements that need to generate AUTO_INCREMENT values. The lock is held until the statement finishes.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 0
~~~

Characteristics:

- Insert-like statements requiring ID allocation on the same table are serialized per statement.
- Values allocated by a single statement remain consecutive under traditional mode rules.
- Another INSERT needing IDs must wait until the statement holding the AUTO-INC lock finishes.
- Concurrency is lower, especially when long bulk inserts run.

Mode 0 can be useful in legacy environments relying on deterministic allocation order with statement-based replication. For new systems, mode 0 is rarely necessary when using row-based replication without special compatibility requirements.

The AUTO-INC lock remains strictly an allocation lock. Transactions may still hold row locks after the statement ends until COMMIT or ROLLBACK.

## 6. Mode 1: consecutive

Mode 1 was commonly used prior to MySQL 8.0. It attempts to keep IDs consecutive within each statement while allowing higher concurrency for simple inserts.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 1
~~~

### 6.1. Simple inserts in mode 1

For simple inserts, the number of rows to insert is known. InnoDB can preallocate a block of IDs via a brief synchronization mechanism and release it without holding an AUTO-INC table lock until the end of the statement.

Therefore, multiple simple inserts can progress more concurrently than in mode 0.

Example:

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('A-1'), ('A-2'), ('A-3');
~~~

InnoDB can allocate a block of three values for statement A. Statement B can allocate the next block while A continues processing its remaining steps, depending on scheduling.

### 6.2. Bulk inserts in mode 1

For bulk inserts, InnoDB does not know in advance exactly how many rows will need IDs. It uses an AUTO-INC table lock and holds it until the statement completes so that values allocated for the statement are not interleaved by other insert-like statements.

Example:

~~~sql
INSERT INTO event_log_demo (event_type)
SELECT event_type
FROM staging_event;
~~~

While this bulk statement holds the AUTO-INC lock, another simple insert needing an AUTO_INCREMENT value on the same table must wait until the bulk statement finishes.

Mode 1 balances per-statement ID contiguity and concurrency. However, long bulk inserts can still make other inserts wait.

## 7. Mode 2: interleaved

Mode 2 uses no statement-level AUTO-INC table lock. Multiple insert-like statements can allocate AUTO_INCREMENT values concurrently, and values may be interleaved.

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 2
~~~

Example of two statements:

~~~sql
-- Session A
INSERT INTO event_log_demo (event_type)
SELECT event_type
FROM staging_event_a;

-- Session B
INSERT INTO event_log_demo (event_type)
VALUES ('B-1'), ('B-2');
~~~

In mode 2, Session B's IDs can appear between IDs received by Session A. There is no guarantee that IDs generated by one statement will form a contiguous block when multiple statements run concurrently.

Advantages:
- Eliminates serialization from AUTO-INC table locks.
- Increases concurrency for insert workloads.
- Pairs well with row-based replication.
- Default starting in MySQL 8.0.

Limitations:
- Does not guarantee consecutive IDs per statement.
- Unsafe for statement-based replication when exact allocation order must be reproduced.
- AUTO_INCREMENT must not be used as a gapless business sequence number.

Mode 2 does not mean IDs can collide. InnoDB still coordinates the counter to issue unique values. The difference lies in allowing statements to interleave allocation order.

## 8. Comparing modes 0, 1, and 2 by statement type

| Statement type | Mode 0 | Mode 1 | Mode 2 |
|---|---|---|---|
| Simple INSERT ... VALUES | AUTO-INC lock until end of statement | Allocates ID block via brief mechanism; no full-statement table lock | Can allocate interleaved |
| Multi-row INSERT ... VALUES | AUTO-INC lock until end of statement | Simple insert; allocates known count upfront | Can allocate interleaved with other statements |
| INSERT ... SELECT | AUTO-INC lock until end of statement | AUTO-INC lock until end of statement | No statement-level table lock |
| REPLACE ... SELECT | AUTO-INC lock until end of statement | AUTO-INC lock until end of statement | No statement-level table lock |
| LOAD DATA | AUTO-INC lock until end of statement | AUTO-INC lock until end of statement | No statement-level table lock |

This table summarizes InnoDB's primary behavior when a statement needs AUTO_INCREMENT allocation. Specific details also depend on input data, explicit values, duplicates, rollbacks, and statement predicates.

## 9. Two-session example: observing interleaved allocation

Create the table and data source:

~~~sql
CREATE TABLE auto_inc_target (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(40) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE auto_inc_source_a (
    label VARCHAR(40) NOT NULL
) ENGINE = InnoDB;

INSERT INTO auto_inc_source_a(label)
VALUES
    ('A-01'), ('A-02'), ('A-03'), ('A-04'), ('A-05'),
    ('A-06'), ('A-07'), ('A-08'), ('A-09'), ('A-10');
~~~

### 9.1. Session A

Run a bulk insert:

~~~sql
INSERT INTO auto_inc_target(label)
SELECT label
FROM auto_inc_source_a;
~~~

On a large table, this statement can run long enough for Session B to execute another INSERT while A is still processing.

### 9.2. Session B

~~~sql
INSERT INTO auto_inc_target(label)
VALUES ('B-01');
~~~

### 9.3. Observing the results

~~~sql
SELECT id, label
FROM auto_inc_target
ORDER BY id;
~~~

- Mode 0: B must wait for A's AUTO-INC lock to finish; IDs assigned to A remain contiguous per statement.
- Mode 1: A is a bulk insert so it holds the AUTO-INC lock until end of statement; B waits.
- Mode 2: B can receive an ID while A is still running; B's row may sit in the middle of A's ID sequence.

Actual order depends on timing and server scheduling. Do not treat a single lab outcome as a guarantee across every run. The goal is to observe interleaving capability and wait behavior, not to force a fixed ID sequence.

To retest with a different mode, update the server configuration and restart MySQL. You cannot change this variable using `SET SESSION`.

## 10. Is the AUTO-INC lock held per statement or per transaction?

This is a common point of confusion.

In mode 0, and for bulk inserts in mode 1, the AUTO-INC table lock is held until the end of the statement. Once the statement completes, the AUTO-INC lock is released even if the transaction has not committed yet.

Example:

~~~sql
START TRANSACTION;

INSERT INTO event_log_demo(event_type)
VALUES ('A-1'), ('A-2');

-- The INSERT statement has finished.
-- The transaction is still open.

-- Other operations of transaction A continue here.

COMMIT;
~~~

After the INSERT ends, the statement-level AUTO-INC lock is not held until COMMIT. However, the transaction may still hold row locks, foreign key locks, or other locks until it finishes.

Therefore, if another session is waiting on an insert, determine whether it is waiting on an AUTO-INC lock or another lock type. Do not assume every waiting INSERT is blocked by an uncommitted previous transaction's AUTO-INC lock.

## 11. AUTO_INCREMENT can have gaps

AUTO_INCREMENT produces monotonically increasing identifiers, not gapless sequences.

Common causes:
- An INSERT transaction rolls back after IDs were allocated.
- A statement errors after some IDs were allocated.
- `INSERT IGNORE` skips duplicate rows.
- `INSERT ... ON DUPLICATE KEY UPDATE` takes the UPDATE branch after already consuming an AUTO_INCREMENT value.
- `REPLACE` or mixed-mode inserts allocate values and then alter execution flow.
- A previously inserted row is later deleted.
- A bulk insert preallocates more values than the final number of rows inserted.
- Server restarts or recovery follow counter rules from older versions.

Example:

~~~sql
START TRANSACTION;

INSERT INTO event_log_demo(event_type)
VALUES ('WILL_ROLLBACK');

ROLLBACK;

INSERT INTO event_log_demo(event_type)
VALUES ('AFTER_ROLLBACK');

SELECT *
FROM event_log_demo
ORDER BY event_id;
~~~

IDs allocated to rolled-back rows are typically not reused immediately. Gaps are normal.

Never use `COUNT(*)` to infer the next ID, and never assume `MAX(id)+1` is a safe way to allocate IDs manually. Let InnoDB manage AUTO_INCREMENT.

### 11.1. AUTO_INCREMENT is not a gapless invoice number

If business rules require gapless invoice numbers with legal or audit constraints, AUTO_INCREMENT is not a tool for guaranteeing a gapless sequence.

Technical identifiers:
- Serve to identify rows.
- May contain gaps.
- Do not guarantee commit order.
- Should not carry external business meaning.

If sequential business numbers are required, design a dedicated allocator with transactions/locking and void-handling rules. Forcing AUTO_INCREMENT to be gapless reduces concurrency and still fails to handle all rollback or deletion cases.

## 12. ID order is not commit order

Suppose:
- Transaction A is assigned ID 100 but runs for a long time.
- Transaction B is assigned ID 101 and commits first.
- Transaction A commits afterward.

When reading the table, ID 101 can appear before ID 100. The ID value reflects relative allocation time, not commit order or exact event time.

If business ordering is needed:
- Store `created_at`/`occurred_at` separately.
- Use sequences or event timestamps as required.
- Add a unique key as a tie-breaker when sorting.
- Do not use `MAX(id)` as a commit watermark in concurrent write environments.

In distributed systems, commit order is even more complex due to replication, retries, and multiple write sources.

## 13. Impact on replication and binary logs

The AUTO-INC lock mode relates to reproducing results on replicas when binary logs use statement format.

### 13.1. Statement-based replication

Statement-based replication writes SQL statements into the binary log. Replicas re-execute those statements. If two concurrent statements receive differently interleaved IDs on the source versus the replica, the results can diverge.

With mode 2, ID allocation can interleave depending on execution scheduling. Statement-based replication cannot guarantee reproducing that exact allocation order.

If using statement-based replication, choose mode 0 or mode 1 to preserve deterministic per-statement ID allocation as required by InnoDB.

### 13.2. Row-based replication

Row-based replication logs actual row changes to the binary log. Replicas apply the recorded row values without needing to re-run the same AUTO_INCREMENT allocation schedule.

Therefore, mode 2 pairs well with row-based replication. MySQL 8.0 defaults to `binlog_format=ROW` and `innodb_autoinc_lock_mode=2`.

Check configuration:

~~~sql
SELECT
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.innodb_autoinc_lock_mode AS autoinc_lock_mode;
~~~

If using `MIXED`, the server may choose row format for certain statements unsafe for statement logging. Check rules for your exact version and workload rather than relying solely on the name `MIXED`.

### 13.3. Never change lock mode independently of replication

Before choosing a mode:
1. Check `binlog_format`.
2. Determine whether statement-based replication is used.
3. Inspect replication topology and tooling.
4. Evaluate simple insert vs. bulk insert workloads.
5. Test in a staging environment.
6. Monitor lock waits and throughput after the change.

Do not switch lock modes just to make INSERTs faster if binary logs use statement format.

## 14. AUTO_INCREMENT in multi-writer environments

MySQL provides the variables:
- `auto_increment_increment`: step interval between generated values.
- `auto_increment_offset`: starting point/offset of the sequence.

Check:

~~~sql
SELECT
    @@GLOBAL.auto_increment_increment,
    @@GLOBAL.auto_increment_offset,
    @@SESSION.auto_increment_increment,
    @@SESSION.auto_increment_offset;
~~~

Example with two writers avoiding collisions in a legacy multi-primary setup:

Node A:
~~~sql
SET SESSION auto_increment_increment = 2;
SET SESSION auto_increment_offset = 1;
~~~

Node B:
~~~sql
SET SESSION auto_increment_increment = 2;
SET SESSION auto_increment_offset = 2;
~~~

One node generates odd numbers and the other even numbers. Actual configurations must be applied uniformly across the entire topology with sufficient distinct offsets.

These two variables do not replace unique keys and do not automatically resolve all distributed conflicts. In modern architectures, consider UUID/UUIDv7, ULID, or shard-scoped keys instead of relying on shared numeric IDs across multiple writers.

## 15. Explicit IDs and the AUTO_INCREMENT counter

You can provide an explicit value for an AUTO_INCREMENT column:

~~~sql
INSERT INTO event_log_demo(event_id, event_type)
VALUES (10000, 'IMPORTED');
~~~

If the explicit value exceeds the current counter, the counter can be adjusted upward so subsequent auto-generated values do not collide with the used value. If the value is smaller and does not conflict, it can be inserted without lowering the counter.

To ask MySQL to auto-assign, omit the AUTO_INCREMENT column from the INSERT list or pass `NULL`. Passing `0` is also normally treated as an auto-generation request, unless the `NO_AUTO_VALUE_ON_ZERO` SQL mode is enabled.

Never compute new values manually with `MAX(id)+1`:

~~~sql
-- Unsafe when multiple writers exist:
SELECT MAX(event_id) + 1
FROM event_log_demo;
~~~

Two sessions can read the same `MAX` and both try inserting the next value. Use `AUTO_INCREMENT` and unique constraints so the server coordinates allocation.


### Requirements for declaring an AUTO_INCREMENT column

A table can have only one AUTO_INCREMENT column. This column must use an integer data type and must be the first column in an index; if inside a composite index, it must be in the leading position. The index does not strictly have to be PRIMARY KEY or UNIQUE, though standard design uses a primary or unique key to guarantee row identity semantics.

~~~sql
CREATE TABLE invoice_records (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (invoice_id)
) ENGINE = InnoDB;
~~~

You can verify definitions and indexes using:

~~~sql
SHOW CREATE TABLE invoice_records;
SHOW INDEX FROM invoice_records;
~~~

Passed values are also affected by SQL mode:

- Omitting the AUTO_INCREMENT column from INSERT or passing `NULL`: MySQL assigns a value automatically.
- Passing `0`: normally requests automatic number generation as well.
- When `NO_AUTO_VALUE_ON_ZERO` is enabled, `0` is treated as an explicit literal value instead of requesting number generation.
- Passing an explicit positive value: MySQL uses that value if it violates no keys; if it exceeds the current counter, future auto-generated values continue from the appropriate level.

Check the connection's SQL mode before relying on `0` behavior:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### Retrieving newly generated keys with LAST_INSERT_ID()

After an INSERT that generates an AUTO_INCREMENT value, `LAST_INSERT_ID()` returns the first auto-generated value produced by the most recent statement on the current connection.

~~~sql
INSERT INTO event_log_demo (event_type)
VALUES ('LOGIN');

SELECT LAST_INSERT_ID();
~~~

This value is scoped to the connection. Another session inserting concurrently does not alter `LAST_INSERT_ID()` in the current session; therefore, the application must fetch generated keys on the exact same connection that ran the INSERT.

For a multi-row INSERT, `LAST_INSERT_ID()` returns only the first generated ID, not a list of all IDs. Especially in mode 2, concurrent statements can interleave values, so never infer all IDs of a batch by adding consecutively from the first ID. When you need all new keys, use your driver/connector's generated-keys API or query by a unique business key inserted with the batch.

## 16. Configuring and inspecting innodb_autoinc_lock_mode

### 16.1. Reading the current value

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_autoinc_lock_mode';
~~~

Or:

~~~sql
SELECT @@GLOBAL.innodb_autoinc_lock_mode;
~~~

This variable has GLOBAL scope, not SESSION scope. It is configured at server startup; do not use `SET SESSION` to change it for a single connection.

### 16.2. Configuring in server configuration files

Configuration example:

~~~ini
[mysqld]
innodb_autoinc_lock_mode = 2
~~~

On Linux, configuration usually resides in a MySQL config file such as `my.cnf` or an included file. On Windows, location depends on the installation and `my.ini`. After making changes, restart MySQL following operational procedures.

Never edit production configuration directly without:
- Checking replication format.
- Assessing impact on insert workloads.
- Having a maintenance window and rollback plan.
- Checking the MySQL version and current default.

### 16.3. Checking binlog format and version

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.innodb_autoinc_lock_mode AS autoinc_lock_mode,
    @@GLOBAL.binlog_format AS binlog_format;
~~~

MySQL 8.0/8.4 defaults to mode 2. Earlier versions, notably MySQL 5.7, defaulted to mode 1. Always read runtime values rather than assuming from another version's documentation.

## 17. Observing AUTO-INC locks during waits

In environments supporting Performance Schema, you can query `data_locks` for the `AUTO_INC` lock mode:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    THREAD_ID
FROM performance_schema.data_locks
WHERE LOCK_MODE LIKE '%AUTO_INC%';
~~~

Column names and granularity depend on MySQL version. If no rows appear, that does not conclusively prove zero waits occurred; the statement may have finished quickly or instrumentation may not display it as expected.

You can check InnoDB status:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

And active transactions:

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

When diagnosing, distinguish:
- Waiting on an AUTO-INC lock.
- Waiting on a record lock or gap/next-key lock.
- Waiting on a metadata lock.
- Waiting on I/O or other resources.

Not every slow INSERT is caused by `innodb_autoinc_lock_mode`.

## 18. Common misconceptions

| Misconception | Reality |
|---|---|
| AUTO_INCREMENT always increases without gaps | Gaps can occur due to rollbacks, deletes, duplicates, or preallocation |
| A larger ID means a later commit | IDs reflect allocation, not commit order |
| Mode 2 can produce duplicate IDs | InnoDB still coordinates the counter; mode 2 allows interleaving without dropping uniqueness |
| Mode 0 locks the whole table for all operations | An AUTO-INC lock is a special allocation lock, not a general table lock |
| An AUTO-INC lock is held until COMMIT | Where table locks are used, the lock is held until the end of the statement |
| Mode 1 never locks the table | Bulk inserts in mode 1 still use an AUTO-INC table lock |
| Mode 2 is safe with statement-based replication | Interleaving can make allocation results non-deterministic on replay |
| autoinc_lock_mode is a session variable | It is a GLOBAL setting configured at the server level |
| MAX(id)+1 can be used to allocate IDs | Unsafe when concurrent writers exist |
| AUTO_INCREMENT is suitable for gapless invoice numbers | It does not guarantee gaplessness or business order |
| Setting mode 0 eliminates all gaps | Mode 0 does not prevent rollbacks, deletes, or other gap causes |
| INSERT ON DUPLICATE KEY UPDATE consumes no ID when updating | It can consume an AUTO_INCREMENT value even if it ultimately updates an existing row |

## 19. Workflow for selecting the right mode

When evaluating `innodb_autoinc_lock_mode`:

1. Identify the MySQL version and table storage engine.
2. Check the current `innodb_autoinc_lock_mode` value.
3. Check `binlog_format` and replication topology.
4. Classify workload: simple INSERT, multi-row INSERT, INSERT ... SELECT, LOAD DATA.
5. Measure bulk insert frequency and per-statement duration.
6. Check whether sessions wait on AUTO-INC locks.
7. Evaluate statement-based replication requirements.
8. If using row-based replication and needing high concurrency, mode 2 is usually suitable.
9. If using statement-based replication, consider mode 0 or 1 depending on workload.
10. Never change settings without testing in staging and planning a restart.
11. Monitor throughput, lock waits, deadlocks, and replication lag after deployment.
12. Confirm applications do not assume gapless IDs or commit ordering.

## 20. Practice exercises

### Exercise 1: Observing IDs after rollback

Create an AUTO_INCREMENT table, INSERT a row inside a transaction, and then ROLLBACK. INSERT another row and observe the ID. Explain why allocated IDs may not be reused.

### Exercise 2: Comparing simple inserts and bulk inserts

Create a source table and target table. Run multi-row `INSERT ... VALUES` and `INSERT ... SELECT`. Classify each statement as simple insert or bulk insert.

### Exercise 3: Two sessions in mode 0

Configure `innodb_autoinc_lock_mode=0` in a lab environment and restart. Have Session A run a long-enough bulk insert while Session B runs a simple insert into the same table. Observe B waiting until statement A ends.

### Exercise 4: Two sessions in mode 1

Repeat the experiment with mode 1. Test both cases:
- Both A and B are simple inserts.
- A is a bulk insert and B is a simple insert.

Record the differences in concurrency.

### Exercise 5: Two sessions in mode 2

Configure mode 2 and repeat with a bulk insert and simple insert. Observe the possibility of IDs from the two statements interleaving. Do not expect a fixed ID order across every run.

### Exercise 6: Statement-based vs. row-based replication

On a test topology, check `binlog_format`. Compare the requirements of modes 0/1 with mode 2. Never alter production settings just for testing.

### Exercise 7: AUTO_INCREMENT and secondary unique keys

Create a table with an AUTO_INCREMENT PRIMARY KEY and a secondary UNIQUE key. Try `INSERT ON DUPLICATE KEY UPDATE` with an existing secondary key. Observe that an ID can still be consumed even though the UPDATE branch executes.

### Exercise 8: Increment and offset

Set `auto_increment_increment=2`, `offset=1` in one session, and `offset=2` in another session in a suitable lab environment. Observe the ID sequence. Explain why this setting does not replace unique constraints.

### Exercise 9: Reading lock instrumentation

Run two sessions with a bulk insert and simple insert. Check `performance_schema.data_locks` and `SHOW ENGINE INNODB STATUS` while waiting occurs. Distinguish AUTO-INC locks from record locks.

### Exercise 10: Designing business keys

Propose a schema for invoice numbers managed per year and per branch. Explain why you should not rely on AUTO_INCREMENT to guarantee gapless invoice numbers; propose a dedicated transaction/allocator if business rules strictly require it.

## 21. Pre-deployment checklist

- [ ] Identified the table's AUTO_INCREMENT column and unique keys.
- [ ] Understood how AUTO-INC locks differ from row locks and metadata locks.
- [ ] Classified simple inserts, bulk inserts, and mixed-mode inserts.
- [ ] Understood mode 0, mode 1, and mode 2.
- [ ] Known that mode 1 still uses table locks for bulk inserts.
- [ ] Known that mode 2 allows interleaved allocation.
- [ ] Checked MySQL version and runtime defaults.
- [ ] Checked `binlog_format` and replication requirements.
- [ ] Understood that mode 2 is unsuitable for statement-based replication requiring determinism.
- [ ] Understood that AUTO-INC locks (when table-level) are held until end of statement.
- [ ] Accepted that IDs can have gaps after rollbacks, duplicates, or deletes.
- [ ] Never used `MAX(id)+1` to manually allocate IDs.
- [ ] Never treated IDs as commit order or gapless business numbers.
- [ ] Evaluated `auto_increment_increment` and `auto_increment_offset` when multiple writers exist.
- [ ] Inspected lock waits via Performance Schema/InnoDB Status.
- [ ] Tested configuration in staging prior to restarting production.
- [ ] Monitored throughput, lock waits, and replication lag after changes.

## 22. Conclusion

The AUTO-INC lock coordinates AUTO_INCREMENT value allocation when multiple statements write to an InnoDB table concurrently. `innodb_autoinc_lock_mode` controls serialization: mode 0 locks until the end of every insert-like statement needing allocation; mode 1 holds a table lock for bulk inserts while letting simple inserts allocate using a shorter mechanism; mode 2 allows statements to interleave allocation and boosts concurrency.

MySQL 8.0/8.4 defaults to mode 2, which works well with row-based replication. If statement-based replication is used, mode 0 or 1 is needed to maintain deterministic allocation behavior. Regardless of mode, AUTO_INCREMENT can still contain gaps and does not reflect commit order. Treat IDs as technical keys, verify replication format, measure lock waits, and design a dedicated allocator if business logic truly demands gapless sequential numbers.

## Official references

- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Lock Modes](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html#innodb-auto-increment-lock-modes)
- [MySQL 8.4 Reference Manual – AUTO_INCREMENT Handling in InnoDB](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – Replication Formats](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)
- [MySQL 8.4 Reference Manual – Binary Log Formats](https://dev.mysql.com/doc/refman/8.4/en/binary-log-formats.html)
- [MySQL 8.4 Reference Manual – Performance Schema data_locks](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-locks-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction and Locking Information](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-examples.html)
- [MySQL 8.4 Reference Manual – System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)

