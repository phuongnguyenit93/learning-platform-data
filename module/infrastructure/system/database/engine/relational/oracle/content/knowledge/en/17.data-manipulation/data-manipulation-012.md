# Impact of DML on Undo, Redo, Indexes, and Locks

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Data Manipulation  
> **Objective:** Understand the internal impact of INSERT, UPDATE, DELETE, and MERGE in Oracle Database; distinguish undo from redo; explain how undo supports rollback and read consistency; understand B-tree index maintenance cost and constraint/trigger overhead; identify row locks, table locks, TX/TM enqueues, and deadlocks; and choose transaction sizing, commit strategies, and DML resource monitoring methods.

## 1. One DML Statement Modifies Multiple Structures

When running this statement:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Oracle does more than just write a new salary value into the table. The database must also manage related work:

- Write **undo** information so the change can be undone and older data versions can be reconstructed for consistent reads.
- Generate **redo** describing protected changes so instance recovery and media recovery can recover data.
- Maintain **indexes** associated with the modified rows.
- Acquire and hold **locks** to protect changes from conflicting with other transactions.
- Check constraints, fire triggers, and execute schema-defined side effects.
- Manage the transaction until COMMIT or ROLLBACK.

Thus, DML cost depends on far more than the number of columns modified. An UPDATE touching millions of rows with multiple indexes, triggers, and foreign keys can generate massive undo/redo and hold locks for a long time.

| Component | Primary role |
|---|---|
| Undo | Stores information needed to reverse changes and reconstruct older data versions |
| Redo | Records change vectors to recover changes after failures |
| Index | Secondary access structure that must stay consistent with the table |
| Lock | Controls concurrent access to data currently being modified |

## 2. Conceptual Lifecycle of a DML Statement

When executing DML, Oracle parses the SQL, locates target rows, checks appropriate privileges/constraints, acquires required locks, and modifies blocks in the buffer cache. Changes generate undo records and redo records.

~~~text
SQL INSERT / UPDATE / DELETE / MERGE
                 |
                 v
       Parse and execution plan
                 |
                 v
       Locate target rows
                 |
                 v
       Acquire required locks
                 |
                 v
     Modify blocks in buffer cache
          /             |             \
         v              v              v
      UNDO            REDO          INDEX
   old version    change vector   maintain entry
         \              |              /
          \             |             /
           v            v            v
            Transaction remains open
                   |
             COMMIT / ROLLBACK
                   |
       COMMIT: confirm transaction
       ROLLBACK: use undo to reverse changes
~~~

This is a conceptual model, not a fixed micro-order for every operation. Oracle performs varying internal steps, buffer actions, and index operations depending on DML type, access path, partitioning, logging mode, and version.

One crucial point: **COMMIT does not mean DBWR has already written every data block to datafiles.** Commit primarily requires redo protecting the transaction to be durably written per LGWR mechanics and commit configuration. DBWR can flush dirty data blocks to datafiles later.

## 3. Undo: Storing Information to Revert to the Prior Version

An undo record contains the information needed to reverse a change. Undo is stored in the undo tablespace across Oracle-managed undo segments and extents.

Example:

~~~sql
UPDATE employees
SET salary = 9000
WHERE employee_id = 100;
~~~

Suppose the old salary was 8000. To roll back, Oracle needs enough information to restore 8000. The UPDATE's undo holds the details needed to reconstruct the pre-change state.

Undo serves three main purposes:

1. **ROLLBACK:** reverses changes of an uncommitted transaction or a partial transaction back to a savepoint.
2. **Read consistency:** enables queries to read a consistent version of data at the appropriate SCN, even while another transaction modifies blocks.
3. **Flashback:** supports historical query/recovery capabilities within retained undo limits and configured features.

### 3.1. Undo Is Not a Full Table Backup Copy

Undo records what is needed to reverse changes, not a full copy of the table before every DML. Undo volume depends on:

- Actual number of rows modified.
- DML type.
- Number and data types of modified columns.
- Indexes requiring maintenance.
- Row structure, partitioning, LOBs, and other storage details.
- Triggers or side effects generating additional DML.

You cannot accurately calculate undo volume simply by multiplying row count by column byte sizes. Measure on representative workloads.

### 3.2. Undo for INSERT, UPDATE, and DELETE

| DML | Data change | Role of undo |
|---|---|---|
| INSERT | Creates new row | Keeps information needed to remove the inserted row on rollback |
| UPDATE | Changes one or more column values | Keeps old values/state needed to restore the row |
| DELETE | Deletes row | Keeps information needed to recreate the deleted row on rollback or consistent read |
| MERGE | Combines insert/update per source row | Undo generated according to actual insert or update branch taken |

DELETE can generate substantial undo because Oracle must retain enough information to reconstruct deleted rows. Multi-column or multi-row UPDATEs also produce large undo. INSERT normally needs undo to roll back row addition and maintain related structures.

### 3.3. Rollback Uses Undo

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

ROLLBACK;
~~~

After ROLLBACK, transaction changes are reversed. If the transaction executed multiple DML statements, Oracle undoes all uncommitted changes of that transaction.

You can roll back to a savepoint:

~~~sql
SAVEPOINT before_adjustment;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Wrong update scope detected
ROLLBACK TO before_adjustment;
~~~

Rolling back to a savepoint reverses only changes after the savepoint; the transaction stays open and applicable locks remain held until the transaction ends.

### 3.4. Undo and Read Consistency

Oracle uses multiversion read consistency. A standard SELECT reads data consistent with a statement SCN in READ COMMITTED. If a block was modified by another transaction after that SCN, Oracle uses undo to reconstruct the older version the query needs.

Example:

1. Session A starts a SELECT and establishes a statement SCN.
2. Session B updates a row without committing.
3. Session A reads that row.
4. Session A does not see B's uncommitted change; Oracle reconstructs the appropriate consistent version.
5. After B commits, a new SELECT by A in READ COMMITTED sees the new value.

This explains why standard SELECT queries normally do not wait on row locks held by UPDATEs. Readers read consistent versions; writers continue modifying data.

### 3.5. Statement-Level and Transaction-Level Consistency

In the default READ COMMITTED isolation level, each SQL statement gets a snapshot as of when that statement begins. Two SELECTs in the same transaction can observe different states if another transaction commits in between.

In SERIALIZABLE or READ ONLY transactions, Oracle provides transaction-level consistent views per their respective semantics. On write conflicts, SERIALIZABLE can raise serialization errors such as ORA-08177; applications must have a transaction retry strategy.

Do not confuse read consistency with locking an entire table. Oracle uses undo and SCNs to deliver snapshots rather than blocking writers.

## 4. Undo Retention and ORA-01555

Undo must be retained long enough for transaction rollbacks and long-running queries needing older versions. Oracle manages undo extent reuse based on transaction state, consistent-read needs, undo settings, and space pressure.

### 4.1. UNDO_RETENTION

The `UNDO_RETENTION` parameter sets a target retention duration for committed undo, in seconds. It is a target; actual retention depends on undo tablespace size, workload, and configuration.

If space is insufficient, undo can be overwritten earlier than the target in certain configurations. `RETENTION GUARANTEE` instructs Oracle to prioritize retaining undo per the retention setting, though if space runs out, new DML fails due to no reusable undo space. Never enable guarantee arbitrarily.

### 4.2. ORA-01555: Snapshot Too Old

A long-running query may need an older version of a block whose required undo was overwritten/reused. When Oracle no longer has enough undo to reconstruct the snapshot, the query fails with:

~~~text
ORA-01555: snapshot too old
~~~

Common contributing factors:

- Long-running queries on tables undergoing continuous DML.
- Undo tablespace undersized relative to undo generation rate and query duration.
- Target undo retention too short for the workload.
- Access patterns requiring excessive historical block reconstruction.
- Certain PL/SQL patterns keeping a cursor open while updating source data in the same loop.

Remediation should target root causes:

- Reduce query runtime via better SQL, indexes, and plans.
- Avoid oversized DML transactions or split batches by design.
- Allocate adequate undo space, checking autoextend and retention.
- Avoid holding read cursors open too long over rapidly changing datasets.
- Consider `RETENTION GUARANTEE` only if you accept DML failures when the undo tablespace fills up.

Do not treat simply raising `UNDO_RETENTION` as a guaranteed fix; without enough space, that parameter cannot preserve undo.

### 4.3. Monitoring Undo

DBA views available (access depends on environment privileges):

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

Useful columns:

- `UNDOBLKS`: undo blocks generated in the statistics interval.
- `TXNCOUNT`: transaction count in the interval.
- `MAXQUERYLEN`: longest query duration recorded in the interval.
- `TUNED_UNDORETENTION`: retention tuned for the workload.
- `SSOLDERRCNT`: snapshot-too-old error count recorded in the interval.

To see transactions currently consuming undo:

~~~sql
SELECT s.sid,
       s.serial#,
       t.used_ublk,
       t.used_urec,
       t.start_time
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
~~~

`USED_UBLK` and `USED_UREC` help identify transactions generating or holding large undo. Do not conclude a transaction is "leaking" solely from high undo numbers; examine open duration, workload, progress, and transaction owner.

## 5. Redo: Recording Changes for Recovery

Redo logs record change vectors describing modifications to database blocks. Redo is the foundation for instance recovery, media recovery, archived logs, and Data Guard.

When a data block changes, Oracle generates corresponding redo. Undo changes are also protected by redo so that during recovery, Oracle can consistently recover both data and transaction state.

### 5.1. Redo vs. Undo

| Aspect | Undo | Redo |
|---|---|---|
| Purpose | Reversing changes and building old versions | Recovering recorded changes |
| General content | Information needed to undo changes | Change vectors describing modifications |
| Supports ROLLBACK | Yes | Not directly used for logical rollback |
| Supports consistent read | Yes | Not the primary query snapshot mechanism |
| Supports crash/media recovery | Undo itself is recovered and applied during recovery | Source replaying changes after checkpoints/backups |

Undo and redo are closely linked yet never replace each other. Redo protects changes to undo blocks too; undo lets Oracle roll back uncommitted transactions and reconstruct prior versions.

### 5.2. Online Redo Logs and LGWR

Redo is placed into the redo log buffer in the SGA. LGWR flushes redo from the buffer to online redo log files under operational triggers, such as:

- When a transaction executes COMMIT.
- When the redo buffer needs flushing.
- Periodically or on other internal triggers.
- Before DBWR writes a dirty data block whose corresponding redo has not yet been flushed, per write-ahead logging.

For a normal commit, Oracle guarantees required transaction redo up through the commit record is durably written before reporting commit success, per `COMMIT WRITE` settings and chosen semantics.

DBWR writes dirty buffers to datafiles on checkpoints and buffer pressure; it does not need to flush every data block immediately at commit time. This makes commits much faster than writing whole datafiles.

### 5.3. COMMIT and Durability

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

COMMIT;
~~~

COMMIT ends the transaction, confirms changes, and releases transaction locks. Required redo for commit is written by LGWR according to commit policy.

If a client loses connection after sending COMMIT before receiving the reply, the application cannot tell whether commit succeeded. For financial operations or external integrations, use a transaction ID/idempotency key to query state rather than blindly re-running the operation.

Oracle offers `COMMIT WRITE WAIT/NOWAIT` and `IMMEDIATE/BATCH` options. `NOWAIT` can return control before redo is durably flushed depending on settings and semantics; applications must not alter durability policies without accepting the risk of losing committed transactions on instance failure.

### 5.4. Redo Log Switches and Archived Logs

Online redo logs are organized into log groups. When one fills up, Oracle switches to another group via a log switch. In `ARCHIVELOG` mode, filled redo log groups are archived before they can be reused per operational rules.

Archived redo logs let media recovery replay changes after backups. If required archived logs are missing or lost, point-in-time recovery capabilities can be restricted.

Monitoring log switches and archiving is a database operations duty; DML applications should avoid generating abnormal redo spikes from oversized batches or redundant updates.

## 6. How Do DML Operations Generate Redo/Undo?

Descriptions below are general principles; actual volume depends on storage, data types, indexes, constraints, logging mode, and execution paths.

### 6.1. INSERT

~~~sql
INSERT INTO employees (
    employee_id, first_name, salary, department_id
)
VALUES (1001, 'An', 8000, 50);
~~~

Impact:

- Adds a new row inside a table block.
- Generates undo required to roll back the insert.
- Generates redo for block changes and related structures.
- Inserts entries into every index referencing relevant columns/expressions.
- Checks NOT NULL, CHECK, UNIQUE, FOREIGN KEY, and triggers.
- Acquires necessary transaction and object locks.

Inserting into a table with many indexes costs more than an unindexed table, especially in large volumes. B-tree indexes must locate leaf blocks, insert entries, and occasionally split blocks.

### 6.2. UPDATE

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Impact:

- Locates matching rows.
- Acquires row locks on updated rows.
- Writes undo to restore old values.
- Writes redo for block modifications.
- If an indexed column changes, corresponding index entries must be maintained.
- Triggers/constraints may add further work.

If UPDATE only modifies unindexed columns, Oracle normally does not need to update entries in unrelated indexes. If an indexed column changes, the database must maintain old and new entries per index structure.

An UPDATE setting a column to its exact current value is still DML and can generate work, locks, and redo/undo depending on execution. If the application knows values have not changed, WHERE predicates can skip unchanged rows, reducing write amplification.

Example:

~~~sql
UPDATE employees
SET status = :p_status
WHERE employee_id = :p_employee_id
  AND (status <> :p_status OR status IS NULL);
~~~

This predicate illustrates skipping rows already holding the target value while accounting for NULLs (assuming `:p_status` is non-NULL). For multiple columns, write proper null-safe conditions; do not assume inequality checks handle NULLs automatically.

### 6.3. DELETE

~~~sql
DELETE FROM employees
WHERE employee_id = 1001;
~~~

Impact:

- Locates rows and acquires locks.
- Writes enough undo to roll back or reconstruct old versions.
- Writes redo for row and index changes.
- Removes/marks corresponding entries in indexes.
- Checks foreign keys, ON DELETE CASCADE if configured, triggers, and constraints.

DELETE does not immediately shrink segment size. Deleted rows leave reusable free space inside the segment; reclaiming space back to the tablespace requires separate operations and operational evaluation.

### 6.4. MERGE

MERGE does not use an entirely separate storage engine. Each row flowing through the UPDATE or INSERT branch incurs the corresponding impact:

- MATCHED rows updated: undo/redo, index maintenance, and row locks like UPDATE.
- NOT MATCHED rows inserted: undo/redo, index maintenance, and checks like INSERT.

Duplicate MERGE sources or join fanouts can cause statement failures or process unexpectedly many rows. Normalize the source by target key before estimating costs.

## 7. Indexes Increase DML Cost

Indexes speed up SELECT lookups, yet every DML must maintain affected indexes. A heavily indexed table reads quickly but pays higher insert/update/delete overhead.

### 7.1. INSERT and B-Tree Indexes

When adding a row, Oracle inserts an entry into each associated B-tree index. Each entry stores the index key and a ROWID pointing to the table row.

If index keys increase sequentially, inserts concentrate on the rightmost leaf blocks of the index. Under very heavy concurrent writes, buffer/latch contention or hot blocks can occur depending on configuration and workload.

Index splits happen when a leaf block runs out of space. A split does not mean the index is corrupted; it is normal B-tree behavior, though it carries redo, undo, and I/O overhead.

### 7.2. Updating Indexed Columns

~~~sql
CREATE INDEX ix_employees_salary
ON employees(salary);
~~~

When running:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100;
~~~

Oracle must maintain the entry in the salary index because the index key changed. If you only update FIRST_NAME and the index does not include FIRST_NAME or an expression depending on it, the salary index needs no entry maintenance.

Therefore, adding an index increases UPDATE cost even when the UPDATE does not use that index to locate rows, if the modified column belongs to the index.

### 7.3. DELETE and Index Entries

DELETE must maintain every index covering deleted rows. Removing entries from indexes adds extra work and redo. Never treat DELETE as a zero-cost "mark row nonexistent" flag.

### 7.4. Composite and Function-Based Indexes

Composite indexes and function-based indexes must also be maintained whenever any input column or expression changes. Example:

~~~sql
CREATE INDEX ix_customer_email_upper
ON customers(UPPER(email));
~~~

Updating EMAIL alters `UPPER(email)`, requiring maintenance on this index.

Indexes on virtual columns or partitioned indexes likewise carry DML overhead corresponding to their design.

### 7.5. Bitmap Indexes and Concurrent DML

Bitmap indexes suit certain analytical workloads with low concurrent DML and low-cardinality columns. In concurrent OLTP write environments, bitmap indexes can cause much broader lock/contention ranges than standard B-tree indexes.

Do not default to bitmap indexes for every status column in transactional tables. Choose index types based on read/write patterns and concurrency.

### 7.6. Should Indexes Be Dropped Before Batch DML?

For very large bulk loads, some architectures load into staging or a new partition, then build/rebuild indexes under a controlled procedure. However:

- Dropped/unusable indexes make queries and dependent constraints unusable.
- UNIQUE indexes may be enforcing data integrity.
- Rebuilding indexes also consumes I/O, TEMP, CPU, and generates redo depending on logging.
- The index-less window must fit within a maintenance window.
- Concurrent DML and live applications can be impacted.

Never drop production indexes just to speed up a batch without assessing constraints and downtime impact.

## 8. Constraints, Triggers, and Secondary DML

An INSERT/UPDATE/DELETE statement can trigger additional work:

- PRIMARY KEY/UNIQUE: checks and maintains uniqueness-enforcing indexes.
- FOREIGN KEY: checks parent-child integrity; parent operations may need to inspect child tables.
- CHECK/NOT NULL: validates row data.
- Triggers: execute PL/SQL and may write to audit or related tables.
- ON DELETE CASCADE: deletes child rows per FK rules.
- Generated/virtual columns and index expressions: compute values and maintain structures.

Secondary operations also generate undo, redo, and locks. Always benchmark DML on a realistic schema with full triggers, constraints, and indexes rather than on a bare lab table.

### 8.1. Indexes on Foreign Keys

Oracle does not automatically create indexes for foreign keys. When a parent key is deleted or updated, if the child foreign key lacks a suitable index, Oracle may need to lock the child table to ensure integrity during checks. This can block concurrent DML on the child table.

An index on FK columns is often considered when the system frequently deletes/updates parent keys or runs concurrent DML on the child table:

~~~sql
CREATE INDEX ix_order_items_order_id
ON order_items(order_id);
~~~

Not every FK requires an index. Decide based on workload, child table size, parent-key modification frequency, and locking behavior.

## 9. Locks in Oracle DML

Locks protect integrity when multiple sessions access the same data.

Oracle uses several enqueue/lock types. Two common concepts in DML are:

- **TX enqueue:** tied to transactions and row-level locking.
- **TM enqueue:** table-level DML lock protecting compatible table structure/access modes.

DML typically acquires a Row Exclusive table lock (TM mode 3) on the modified table and row locks on the actual modified rows. Exact details depend on the operation, constraints, and relationships.

### 9.1. Row Locks

When updating a row:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
~~~

The session holds a row lock on the updated row until COMMIT or ROLLBACK. Another session wanting to UPDATE/DELETE that same row must wait for the lock-holding transaction to finish.

DML on different rows of the same table normally proceeds concurrently, provided there is no conflict via indexes, constraints, parent-child locks, or shared resources.

Oracle does not routinely escalate row locks into table locks via lock escalation like some other DBMSs. Even when one transaction modifies many rows, it continues holding individual row locks; the corresponding table DML lock is managed separately.

### 9.2. Table Locks (TM)

DML on a table normally acquires a TM Row Exclusive lock to permit other compatible DML while blocking conflicting DDL. A table lock does not mean every row in the table is exclusively locked.

Other TM modes can appear from `LOCK TABLE`, DDL, constraints, or specialized operations. When diagnosing blocking, inspect the object, lock mode, session, and blocker.

### 9.3. Standard SELECT vs. SELECT FOR UPDATE

Standard SELECT does not acquire row locks to block UPDATEs; it reads a consistent snapshot using undo.

If an application must read and lock rows before updating per business decision, use:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE;
~~~

Selected rows stay locked until the transaction ends. Other sessions attempting to lock/modify those rows wait.

You can use `NOWAIT` or `WAIT n` to control waiting behavior:

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE WAIT 5;
~~~

`SKIP LOCKED` suits certain queue/worker patterns where sessions skip rows already locked by another session:

~~~sql
SELECT task_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` is not a universal fix to dodge every lock; design claiming states, commits, and retries so jobs are never silently dropped.

### 9.4. Locks Persist Until the Transaction Ends

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;

-- Row remains locked here.
-- Other sessions may have to wait.

COMMIT;
~~~

Do not commit after every single row just to release locks if the business requires atomicity across the whole batch. Conversely, overly long transactions hold locks too long and increase blocking. Choose transaction boundaries matching the business unit of work.

## 10. Blocking and Deadlocks

### 10.1. Blocking

Session A:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
-- Not yet committed
~~~

Session B:

~~~sql
UPDATE accounts
SET balance = balance + 50
WHERE account_id = 10;
~~~

B must wait because A holds the row lock. Once A commits or rolls back, B proceeds according to the resulting state and predicate.

Blocking is normal lock waiting, not automatically a bug. Identify the blocker, wait duration, active SQL, and why the holding transaction has not finished.

### 10.2. Deadlocks

A deadlock occurs when sessions wait on locked resources in a cycle.

Session A:
~~~sql
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;
~~~

Session B:
~~~sql
UPDATE accounts SET balance = balance - 10 WHERE account_id = 2;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 1;
~~~

One possible interleaving:

1. A locks account 1.
2. B locks account 2.
3. A waits for account 2 held by B.
4. B waits for account 1 held by A.
5. Oracle detects the wait cycle and aborts one statement with `ORA-00060`.

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

Oracle rolls back only the statement causing the deadlock, not automatically the application's entire transaction. The application must handle the transaction state properly, roll back if needed, and retry the entire unit of work under a safe policy.

### 10.3. Reducing Deadlock Risk

- Update multiple tables/rows in a consistent lock order.
- Keep transactions short; avoid waiting for user input or calling external APIs while holding locks.
- Identify the exact blocker and conflicting SQL statements.
- Sort ID lists into a deterministic order before locking/updating.
- Partition batches so workers do not contend on the same business keys.
- Use bounded retries with backoff and idempotency; never loop infinitely.
- Never scatter mid-workflow COMMITs inside an atomic business operation just to dodge deadlocks.

## 11. DML Cost When Tables Have Many Indexes

Suppose ORDERS has:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);

CREATE INDEX ix_orders_status_date
ON orders(status, created_at);

CREATE INDEX ix_orders_external_ref
ON orders(external_reference);
~~~

When inserting an order, Oracle maintains all three indexes. When updating STATUS, the status/date index updates. When updating CUSTOMER_ID, the customer index updates. When updating a column outside all indexes and unrelated to expressions/constraints, these indexes need no entry updates.

| Change | Table block | Customer index | Status/date index | External ref index |
|---|---|---|---|---|
| INSERT new row | Yes | Add entry | Add entry | Add entry |
| UPDATE STATUS | Yes | Normally unchanged | Update entry | Normally unchanged |
| UPDATE CUSTOMER_ID | Yes | Update entry | Normally unchanged | Normally unchanged |
| UPDATE unindexed note | Yes | Unchanged | Unchanged | Unchanged |
| DELETE row | Delete/mark row | Maintain entry removal | Maintain entry removal | Maintain entry removal |

This table only illustrates direct column-based indexes; triggers, function-based indexes, virtual columns, partitioning, and constraints can add extra work.

### 11.1. More Indexes Are Not Always Better

Indexes cut SELECT cost at the expense of higher DML cost. Every index adds storage, redo/undo, CPU, buffer usage, and maintenance.

When evaluating an index, weigh query read frequency and latency, INSERT/UPDATE/DELETE frequency, frequently mutated columns, selectivity, redundant/prefix indexes, storage size, and whether the index enforces a constraint.

Do not drop an index solely because DML looks slow; confirm the index is truly unneeded and does not back an integrity constraint.

## 12. Batch DML, Transaction Size, and COMMIT

An oversized transaction generates excessive undo/redo and holds locks too long. Conversely, committing row-by-row creates many tiny transactions, inflating round-trip/commit overhead and destroying batch atomicity.

### 12.1. Avoid Row-by-Row COMMIT

Anti-pattern:

~~~sql
BEGIN
    FOR r IN (SELECT employee_id FROM stage_employees) LOOP
        UPDATE employees
        SET status = 'PROCESSED'
        WHERE employee_id = r.employee_id;

        COMMIT;
    END LOOP;
END;
/
~~~

For a 100,000-row batch, this creates 100,000 transactions. It causes heavy overhead and, if a mid-batch failure occurs, leaves the batch partially committed without atomicity.

If business logic demands all-or-nothing, commit once after completion and verification. If the batch is too huge, split it into identifiable, resumable commit chunks.

### 12.2. Use Set-Based DML

Usually prefer a single UPDATE over a row-by-row loop:

~~~sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login_at < :p_cutoff_date
  AND status <> 'INACTIVE';
~~~

Set-based DML minimizes parse/execute calls and round trips, letting the optimizer process the dataset. The status predicate also skips rows already in the desired state; handle NULL explicitly if the column is nullable.

### 12.3. FORALL and BULK COLLECT

When PL/SQL collection processing is required, `BULK COLLECT` and `FORALL` reduce context switches between PL/SQL and SQL:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM stage_employee_ids
    WHERE batch_id = :p_batch_id;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'PROCESSED'
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

This is a basic example. For large datasets, unbounded `BULK COLLECT` consumes substantial PGA memory; use `LIMIT` inside a fetch loop to bound memory. `FORALL` can pair with `SAVE EXCEPTIONS` to capture per-element errors, provided transaction and error handling are explicitly designed.

If an operation can be expressed in a single set-based SQL statement, that is usually simpler.

### 12.4. Choosing Batch Size

There is no single optimal batch size for every system. Weigh row count and size, undo/redo generated, lock hold duration, recovery time on failure, PGA/TEMP/I/O, commit frequency, atomicity needs, restartability, and concurrent worker count.

Benchmark with representative batches, monitoring undo/redo, elapsed time, waits, and blocking. Pick a balance between throughput, recoverability, and application impact.

## 13. Direct-Path INSERT and NOLOGGING

For massive data loads, Oracle supports direct-path INSERT under certain conditions:

~~~sql
INSERT /*+ APPEND */ INTO sales_archive
SELECT *
FROM sales_stage
WHERE batch_id = :p_batch_id;
~~~

Direct path writes via a separate path, bypassing standard buffer-cache operations and reducing bulk-load overhead. Exact behavior depends on tables, partitions, constraints, triggers, parallelism, and Oracle version.

### 13.1. LOGGING and NOLOGGING

`NOLOGGING` is not a global switch disabling redo for every UPDATE/DELETE. It only reduces redo for eligible operations, such as certain direct-path loads or object creations/rebuilds, depending on mode and configuration.

Notes:

- `FORCE LOGGING` at database/tablespace level overrides `NOLOGGING`.
- A `NOLOGGING` operation can render affected data blocks unrecoverable from redo/archived logs for that operation window.
- Take an appropriate backup immediately after `NOLOGGING` operations per recovery policy.
- Indexes and related metadata can still generate redo.
- `NOLOGGING` does not universally eliminate undo, transaction, or constraint requirements.

Never use `NOLOGGING` on transactional tables needing full media recovery unless approved by DBAs and backup/recovery procedures.

### 13.2. Direct Path Does Not Mean "Zero Undo, Redo, or Locks"

Direct-path INSERT changes how data blocks are written and alters undo/redo volume compared to conventional inserts, yet rules for transactions, metadata, indexes, constraints, and logging still apply. Never generalize that `APPEND` eliminates all undo or redo. Check your exact operation, version, and logging mode.

## 14. Mid-Flight DML Errors and Atomicity

A single DML statement is atomic at the statement level: if the statement errors, Oracle undoes that statement's changes. Earlier statements in the transaction remain unless the transaction rolls back.

Example:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 999999;
~~~

If the second statement updates zero rows, that is not automatically a SQL error. If the second statement raises a constraint violation, the second statement rolls back while the first remains in the transaction. The application must decide whether to COMMIT or ROLLBACK the transaction.

Use `SAVEPOINT` to scope partial rollbacks:

~~~sql
SAVEPOINT before_second_step;

-- Next DML
-- If this step fails:
ROLLBACK TO before_second_step;
~~~

### 14.1. LOG ERRORS for Certain Row-Level DML Errors

Oracle supports DML error logging in eligible scenarios, recording individual row failures while continuing with remaining rows when syntax/conditions permit:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'CUSTOMERS',
        err_log_table_name => 'ERR$_CUSTOMERS'
    );
END;
/
~~~

Then:

~~~sql
INSERT INTO customers(customer_id, customer_name)
SELECT customer_id, customer_name
FROM stage_customers
LOG ERRORS INTO err$_customers ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

DML error logging does not capture every error type and does not replace batch validation. Check supported constraint types, statement-level errors, triggers, and exact operations in Oracle documentation. Error log tables also require management and reconciliation.

## 15. Monitoring Locks and Blocking

When an application reports a hung UPDATE, identify the waiting session and blocking session.

### 15.1. Viewing Waiting Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

These columns identify the waiting session, wait event, wait duration, blocker, and SQL ID.

### 15.2. Viewing Locked Objects

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

`LOCKED_MODE` is a numeric lock-mode code; consult Oracle documentation to interpret each lock type accurately. `DBA_OBJECTS` and `V$LOCKED_OBJECT` may require higher privileges than application accounts hold.

### 15.3. Viewing TX/TM Locks

~~~sql
SELECT l.sid,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
WHERE l.type IN ('TX', 'TM')
ORDER BY l.type, l.sid;
~~~

`TX`/`TM` are enqueues typically tied to transactions and table DML. `LMODE`/`REQUEST` show held vs. requested modes. To diagnose a specific lock, combine `V$SESSION`, object IDs, active SQL, and blocker chains.

Never kill a session solely because you see a lock. First identify the transaction owner, uncommitted work, business impact, and operational runbooks.

## 16. Monitoring Redo and DML Performance

Useful metrics:

- Redo size/redo entries: amount of redo generated.
- Logical reads and physical reads.
- Buffer gets and elapsed time.
- Undo blocks/records.
- Wait events related to `log file sync`, `log file parallel write`, `buffer busy waits`, `enq: TX`, and `enq: TM`.
- Rows processed, constraint error counts, and retry counts.
- Index/trigger counts and runtime per batch stage.

Inspect system-wide statistics:

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'user commits',
    'user rollbacks',
    'db block changes'
)
ORDER BY name;
~~~

These are cumulative counters since instance startup or statistics reset. To measure a batch, take before/after snapshots over the interval while remembering other workloads also contribute to system totals. In shared environments, use appropriate session monitoring/SQL trace tools for accurate attribution.

### 16.1. LOG FILE SYNC

Foreground sessions typically wait for LGWR to finish flushing commit redo during WAIT-mode commits. `log file sync` waits can rise if commits happen too frequently, redo I/O is slow, or LGWR is heavily loaded.

Do not automatically blame every `log file sync` wait on row-by-row commits. Compare wait times, commit counts, LGWR write latency, redo generation, and overall workload.

### 16.2. Enqueue Waits

Events like `enq: TX - row lock contention` typically indicate a session waiting for another transaction to release a row lock or related TX enqueue condition. `enq: TM - contention` involves table enqueues. Always inspect the blocker and specific SQL; not all TX waits share the same root cause.

## 17. Lab Example: Observing Undo, Redo, and Row Locks

Run only in an authorized lab schema. Never perform lock tests on production tables.

### 17.1. Create Test Table

~~~sql
CREATE TABLE lab_dml_account (
    account_id NUMBER PRIMARY KEY,
    balance NUMBER(12,2) NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL
);

INSERT INTO lab_dml_account VALUES (1, 1000, 'OPEN');
INSERT INTO lab_dml_account VALUES (2, 2000, 'OPEN');
COMMIT;
~~~

### 17.2. Session A: Update Without Committing

~~~sql
UPDATE lab_dml_account
SET balance = balance - 100
WHERE account_id = 1;
~~~

Transaction A holds a row lock on account 1. Undo allows rolling back to balance 1000 and lets readers reconstruct the consistent pre-change version.

### 17.3. Session B: Read and Write

In Session B, run a normal SELECT:

~~~sql
SELECT balance
FROM lab_dml_account
WHERE account_id = 1;
~~~

Under READ COMMITTED, B reads the prior committed value (1000), not A's uncommitted change.

Next, try updating the same row:

~~~sql
UPDATE lab_dml_account
SET balance = balance + 50
WHERE account_id = 1;
~~~

B waits for A to end its transaction.

### 17.4. End Session A

~~~sql
COMMIT;
~~~

After A commits, B proceeds and updates using the latest state per statement execution semantics. If A runs `ROLLBACK`, B proceeds against the restored state.

### 17.5. Observe Rollback

In another session, run:

~~~sql
UPDATE lab_dml_account
SET balance = 0
WHERE account_id = 2;

ROLLBACK;
~~~

Verify account 2's balance remains 2000.

### 17.6. Clean Up Lab Table

~~~sql
DROP TABLE lab_dml_account PURGE;
~~~

Only drop the lab table you created.

## 18. Workflow for Evaluating a Batch DML Job

Before running a large batch, use this checklist:

1. **Scope target rows.** Run SELECT with the same predicate to estimate row counts and verify conditions.
2. **Inspect the plan.** Check access paths, indexes, cardinality estimates, and access counts.
3. **Assess indexes.** Identify which columns change and which indexes require maintenance.
4. **Assess constraints/triggers.** Account for cascades, audits, and secondary DML.
5. **Estimate undo/redo.** Test a representative sample batch while watching `V$UNDOSTAT`, `V$TRANSACTION`, and redo statistics.
6. **Choose transaction boundaries.** Preserve business atomicity while avoiding excessive lock durations.
7. **Pick set-based or bulk.** Prefer set-based; use `FORALL` only when collection processing is truly required.
8. **Handle errors and retries.** Include savepoints, error logging, or quarantine per requirements.
9. **Monitor blocking.** Watch TX/TM waits, blockers, and transaction durations.
10. **Reconcile results.** Check row counts, sums, and write batch audit records.
11. **Verify recovery.** For direct path/`NOLOGGING`, verify logging modes and backup/recovery policies.

## 19. Common Misconceptions

| Misconception | Reality |
|---|---|
| COMMIT writes all data blocks to datafiles | COMMIT requires durable commit redo per config; DBWR can flush data blocks later |
| Undo and redo are the same log | Undo reverses/reconstructs old versions; redo recovers changes |
| SELECT always waits on UPDATE | Consistent read uses undo and normally does not wait on writer row locks |
| Updating an unindexed column creates no redo | Table block modifications still generate undo/redo; unrelated index entries simply avoid updates |
| Having many indexes only affects SELECT | Every affected index increases DML work |
| DELETE immediately returns space to the tablespace | Freed space is reusable inside the segment; reclaiming to tablespace is separate |
| Row-by-row COMMIT is always faster | It increases commit overhead and breaks atomicity |
| Undo retention is guaranteed by UNDO_RETENTION | It is a target; actual retention depends on space and retention guarantee |
| NOLOGGING disables redo for all DML | Applies only to specific eligible operations; FORCE LOGGING and recovery policy affect it |
| Oracle escalates row locks to table locks on bulk updates | Oracle does not normally escalate row locks; row locks and TM locks are distinct |
| MERGE incurs only one write cost | Every inserted/updated row still incurs undo, redo, index, constraint, and lock costs |

## 20. Core Takeaways

- DML modifies tables and incurs undo, redo, index maintenance, locks, constraints, and triggers.
- **Undo** serves rollback and consistent reads; **redo** protects changes for recovery.
- Standard readers use multiversion read consistency; writers colliding on the same row wait on the lock-holding transaction.
- COMMIT confirms the transaction and writes redo per commit semantics; DBWR may flush data blocks to datafiles later.
- INSERT/UPDATE/DELETE each carry corresponding undo/redo and index costs; MERGE combines those impacts per branch taken.
- More indexes improve certain queries while increasing write and storage overhead.
- TX enqueues relate to transaction/row locking; TM enqueues protect table-level DML operations.
- Long transactions hold locks longer and can build up large undo; overly frequent commits add commit overhead.
- Use set-based DML or `FORALL` appropriately; choose batch sizes from measurements and business boundaries.
- Direct-path/`NOLOGGING` carries limits and recovery implications; it does not eliminate all undo/redo.
- Monitor undo, redo, lock waits, blocking, execution plans, and row reconciliation to understand real DML cost.

### Oracle Reference Documentation

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, undo, redo, locking, and read consistency.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Undo management, redo log files, ARCHIVELOG, and recovery.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — INSERT, UPDATE, DELETE, MERGE, SELECT FOR UPDATE, and DML error logging.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Wait events, redo, buffer activity, and execution plans.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — FORALL, BULK COLLECT, and exception handling.

Exact behavior of direct path, NOLOGGING, undo retention, lock modes, and commit writes can vary by Oracle version and configuration. Consult documentation for your exact release and benchmark on a schema with matching indexes, constraints, triggers, and production-like workloads.
